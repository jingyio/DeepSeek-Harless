#!/usr/bin/env python3
"""Run an isolated DSH command through Distil or the shared cost gate.

This starts no model request on its own. The child command still needs its own
task-level request limit. Never point a shared Harness process here.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISTIL = ROOT / ".local" / "distil-upstream"
PIN = "e836dc1540dd390823b26582ad137f73072d6871"
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("distil", "plain"), default="distil")
    parser.add_argument("--distil-profile", choices=("full", "context-only"), default="full",
                        help="full uses Distil's default shadow/output policy; context-only isolates compression")
    parser.add_argument("--upstream", default="https://api.deepseek.com")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--budget-usd", type=float,
                        help="required for a real DeepSeek upstream; covers Distil's internal model calls")
    parser.add_argument("--ledger", type=Path, help="private per-run budget ledger under .local")
    parser.add_argument("--budget-max-output", type=int, default=3000,
                        help="per-request output cap for the cost gate (1–8000)")
    parser.add_argument("--distil-home", type=Path,
                        help="explicit persistent Distil state; default isolates each trial")
    parser.add_argument("--motif-output-projection", type=Path,
                        help="certified compiled Motif; SSS projects the latest tool batch and owns restoration")
    parser.add_argument("--evidence-scope", choices=["quote_verification"],
                        help="explicit narrow task scope required by context-dependent evidence views")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.mode == "distil":
        if not DISTIL.is_dir():
            parser.error("missing local Distil clone; see experiments/distil_baseline.md")
        revision = subprocess.check_output(
            ["git", "-C", str(DISTIL), "rev-parse", "HEAD"], text=True
        ).strip()
        if revision != PIN:
            parser.error(f"Distil revision differs from the tested pin: {revision}")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide an isolated DSH command after --")
    if args.upstream == "https://api.deepseek.com" and args.budget_usd is None:
        parser.error("real DeepSeek requests require --budget-usd and prior research approval")
    if args.evidence_scope and args.motif_output_projection is None:
        parser.error("evidence scope requires a certified Motif output projection")
    if args.mode == "plain" and args.budget_usd is None:
        parser.error("plain mode requires a local budget gate")
    if args.budget_usd is not None and not 0 < args.budget_usd <= 100:
        parser.error("invalid dollar budget")
    if not 1 <= args.budget_max_output <= 8000:
        parser.error("invalid budget output cap")
    if not 0 <= args.port <= 65535:
        parser.error("invalid port")
    def open_port(preferred: int = 0) -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", preferred))
            return sock.getsockname()[1]

    port = open_port(args.port)
    gate_port = open_port() if args.budget_usd is not None else None
    while gate_port == port:
        gate_port = open_port()
    projection_port = open_port() if args.motif_output_projection is not None else None
    while projection_port is not None and projection_port in {port, gate_port}:
        projection_port = open_port()
    run_id = uuid4().hex
    base = ROOT / ".local" / "distil-sss"
    home = (args.distil_home or base / "homes" / run_id).resolve()
    if not home.is_relative_to(ROOT / ".local"):
        parser.error("Distil state must stay under .local")
    home.mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    ledger = (args.ledger or base / "budget-runs" / f"{run_id}.jsonl").resolve()
    if not ledger.is_relative_to(ROOT / ".local"):
        parser.error("budget ledger must stay under .local")
    env = os.environ.copy()
    dependency_paths = [str(ROOT)]
    if args.mode == "distil":
        dependency_paths.append(str(DISTIL))
    env["PYTHONPATH"] = os.pathsep.join(dependency_paths + [env.get("PYTHONPATH", "")])
    env["DISTIL_HOME"] = str(home)
    env["DISTIL_NO_UPDATE_CHECK"] = "1"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def healthy(process: subprocess.Popen[str], url: str) -> None:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(f"local proxy exited before health check: {process.stderr.read()[-500:]}")
            try:
                with opener.open(url, timeout=0.2) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(0.05)
        raise RuntimeError("local proxy health check timed out")

    gate = None
    proxy = None
    projection = None
    distil_upstream = args.upstream
    try:
        if gate_port is not None:
            gate_cmd = [sys.executable, str(ROOT / "src" / "adapters" / "deepseek_cost_gate.py"),
                        "--port", str(gate_port), "--upstream", args.upstream,
                        "--cap-usd", str(args.budget_usd), "--max-output",
                        str(args.budget_max_output), "--record", str(ledger)]
            gate = subprocess.Popen(gate_cmd, env=env, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True)
            healthy(gate, f"http://127.0.0.1:{gate_port}/budget/health")
            distil_upstream = f"http://127.0.0.1:{gate_port}"
        if args.mode == "distil":
            proxy_cmd = [sys.executable, "-c", "from distil.cli import main; raise SystemExit(main())",
                         "proxy", "--host", "127.0.0.1", "--port", str(port),
                         "--upstream", distil_upstream, "--expand", "--no-record"]
            if args.distil_profile == "context-only":
                proxy_cmd += ["--shape-output", "off", "--shadow", "0"]
            proxy = subprocess.Popen(proxy_cmd, env=env, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE, text=True)
            healthy(proxy, f"http://127.0.0.1:{port}/distil/health")
        if projection_port is not None:
            from src.adapters.motif_output_projection import load_certified_projection

            artifact_path = args.motif_output_projection.resolve()
            load_certified_projection(artifact_path)
            projection_home = (base / "projections" / run_id).resolve()
            projection_upstream = f"http://127.0.0.1:{port if proxy is not None else gate_port}"
            projection_cmd = [sys.executable, "-m", "src.adapters.motif_output_projection",
                              "--port", str(projection_port), "--upstream", projection_upstream,
                              "--artifact", str(artifact_path), "--local-dir", str(projection_home)]
            if args.evidence_scope:
                projection_cmd += ["--evidence-scope", args.evidence_scope]
            projection = subprocess.Popen(projection_cmd, env=env, cwd=ROOT,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            healthy(projection, f"http://127.0.0.1:{projection_port}/projection/health")
        child_env = env.copy()
        # DSH appends /chat/completions. /v1 is essential: Distil otherwise
        # forwards the request without compression.
        endpoint_port = projection_port if projection is not None else (port if proxy is not None else gate_port)
        child_env["DEEPSEEK_BASE_URL"] = f"http://127.0.0.1:{endpoint_port}/v1"
        child_env["SSS_CONTEXT_MODE"] = args.mode
        child_env["SSS_DISTIL_PROFILE"] = args.distil_profile if args.mode == "distil" else "none"
        child_env["SSS_DISTIL_HOME"] = str(home) if args.mode == "distil" else ""
        if projection is not None:
            child_env["SSS_PROJECTION_HOME"] = str(projection_home)
            child_env["SSS_PROJECTION_ARTIFACT_DIGEST"] = load_certified_projection(artifact_path)[0]
            child_env["SSS_EVIDENCE_SCOPE"] = args.evidence_scope or "none"
        if gate is not None:
            child_env["SSS_BUDGET_GATE_ACTIVE"] = "1"
            child_env["SSS_BUDGET_CAP_USD"] = str(args.budget_usd)
            child_env["SSS_BUDGET_LEDGER"] = str(ledger)
            print(f"budget_ledger={ledger} distil_home={home}", file=sys.stderr)
        return subprocess.call(command, env=child_env, cwd=ROOT)
    finally:
        for process in (projection, proxy, gate):
            if process is None:
                continue
            process.terminate()
            try:
                process.wait(timeout=12 if process is proxy else 5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
