#!/usr/bin/env python3
"""Budget-gated DSH arm for one frozen synthetic meeting decision."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402
from src.adapters.versioned_evidence_guard import audit_versioned_seed_claims  # noqa: E402


BASE = ROOT / "benchmarks/meeting_decision_chain_v1"
V2_BASE = ROOT / "benchmarks/meeting_decision_chain_v2"
V3_BASE = ROOT / "benchmarks/meeting_decision_chain_v3"
V4_BASE = ROOT / "benchmarks/meeting_decision_chain_v4"
V5_BASE = ROOT / "benchmarks/meeting_decision_chain_v5"
CASE_IDS = frozenset(("family_shift", "label_audit", "hardware_latency",
                      "novel_queries", "site_transfer", "tail_terms",
                      "lot_stability", "model_rsi_state", "aidd_mutation",
                      "agent_tool_transfer", "rna_batch", "retrieval_language",
                      "robot_protocol", "battery_cold", "corpus_shift",
                      "remote_assay", "microscopy_vendor", "chemistry_substrate",
                      "materials_scaleup"))
PROSPECTIVE_CASE_IDS = frozenset(("site_transfer", "tail_terms", "lot_stability",
                                  "model_rsi_state", "aidd_mutation",
                                  "agent_tool_transfer", "rna_batch",
                                  "retrieval_language", "robot_protocol",
                                  "battery_cold", "corpus_shift", "remote_assay",
                                  "microscopy_vendor", "chemistry_substrate",
                                  "materials_scaleup"))
PATCH = ROOT / "config/meeting-decision-chain.patch.yml"
CONTRACTS = ROOT / "config/meeting-decision-chain-contracts.json"
OUT = ROOT / ".local/benchmarks/meeting-decision-chain-v3"
CAP_USD = 1.0
MAX_REQUESTS = 15
MAX_OUTPUT_TOKENS = 8000
MAX_EVIDENCE_REPAIRS = 2
DELIVERY_CONTRACT = ("\n\n交付格式：只输出可直接渲染的 Markdown 正文，不要 YAML 页头、"
                     "代码围栏、额外前言或尾声。约 600–900 字；必要的证据表格可以另计。"
                     "不得为遵守字数而省略关键数字、来源版本和限制。"
                     "事件的 changed_fields 只说明哪些列的数值变化，不能据此推断修订原因、"
                     "测量口径或上游流程发生了什么；分组标签也不能证明组内有多少独立对象。"
                     "这些信息缺失时请明确写为待核实，不要补造。")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_for(case: str) -> Path:
    return (V5_BASE if case in {"microscopy_vendor", "chemistry_substrate",
                                "materials_scaleup"} else
            V4_BASE if case in {"battery_cold", "corpus_shift", "remote_assay"} else
            V3_BASE if case in {"rna_batch", "retrieval_language",
                                "robot_protocol"} else
            V2_BASE if case in {"model_rsi_state", "aidd_mutation",
                                "agent_tool_transfer"} else BASE)


def prompt_for(case: str) -> str:
    return ((base_for(case) / "tasks" / f"{case}.md")
            .read_text(encoding="utf-8") + DELIVERY_CONTRACT)


def private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def deliverable_body(raw: str) -> str:
    """Remove a stray preamble while preserving the raw response in the trace."""
    content = raw.strip()
    heading = re.search(r"(?m)^# ", content)
    return content[heading.start():].strip() if heading else content


def preview(case: str, arm: str, online_manifest: Path | None,
            online_task: Path | None, similarity_threshold: float | None,
            output_root: Path = OUT) -> dict:
    base = base_for(case)
    case_dir = base / "sources" / case
    task = base / "tasks" / f"{case}.md"
    files = [task, PATCH, CONTRACTS,
             BASE / "mock_apps_server.py", Path(__file__).resolve(),
             ROOT / "src/adapters/versioned_evidence_guard.py",
             *sorted(path for path in case_dir.iterdir() if path.is_file())]
    if arm == "motif":
        if not online_manifest or not online_task:
            raise ValueError("Motif arm needs a certified online manifest and task")
        files += [online_manifest.resolve(strict=True), online_task.resolve(strict=True),
                  ROOT / "src/adapters/dsh_online_motif.mjs",
                  ROOT / "src/motif_core/online_skill_runtime.mjs"]
    elif online_manifest or online_task:
        raise ValueError("baseline must not receive a Motif manifest")
    return {"task_id": f"meeting-decision-{case}", "case": case, "arm": arm,
            "benchmark_version": (7 if base == V5_BASE else 6 if base == V4_BASE
                                  else 5 if base == V3_BASE
                                  else 4 if base == V2_BASE else 3),
            "frozen_min_similarity": similarity_threshold if arm == "motif" else None,
            "classification": "synthetic_development_trial",
            "model": "deepseek-flash", "reasoning_effort": "off",
            "budget_cap_usd": CAP_USD, "max_model_requests": MAX_REQUESTS,
            "max_evidence_repair_requests": MAX_EVIDENCE_REPAIRS,
            "max_output_tokens_per_request": MAX_OUTPUT_TOKENS,
            "read_only": True,
            "input_sha256": {str(path.resolve().relative_to(ROOT)) if
                             path.resolve().is_relative_to(ROOT) else str(path): sha(path)
                             for path in files},
            "output_dir": str(output_root / case / arm)}


def _online_prepare(manifest: Path, task: Path) -> dict:
    script = ROOT / "scripts/prepare-online-motif.py"
    spec = importlib.util.spec_from_file_location("meeting_online_prepare", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("online Motif preparer is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare(manifest, task)


def check_local_embedding(endpoint: str, model: str) -> None:
    """Avoid a paid run when the local Motif selector cannot respond."""
    parsed = urlparse(endpoint)
    if (parsed.scheme != "http" or parsed.hostname not in
            {"127.0.0.1", "localhost", "::1"} or
            parsed.path != "/v1/embeddings" or not model):
        raise ValueError("Motif needs the approved local embedding endpoint")
    payload = json.dumps({"model": model,
                          "input": ["SSS preflight", "versioned source"]}).encode()
    request = urllib.request.Request(endpoint, data=payload,
                                     headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=20) as response:
        body = json.load(response)
    rows = body.get("data")
    if (not isinstance(rows, list) or len(rows) != 2 or
            any(not isinstance(row.get("embedding"), list) or
                not row["embedding"] for row in rows)):
        raise ValueError("local embedding preflight returned no vector")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(CASE_IDS), required=True)
    parser.add_argument("--arm", choices=("baseline", "motif"), required=True)
    parser.add_argument("--online-manifest", type=Path)
    parser.add_argument("--online-task", type=Path)
    parser.add_argument("--embedding-endpoint", default="http://127.0.0.1:8776/v1/embeddings")
    parser.add_argument("--embedding-model", default="Qwen/Qwen3-Embedding-0.6B")
    parser.add_argument("--output-root", type=Path, default=OUT,
                        help="private run root under .local; use a fresh root for a retest")
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    if args.arm == "motif" and args.case not in PROSPECTIVE_CASE_IDS:
        parser.error("Motif arm is reserved for independent prospective cases")
    output_root = args.output_root.resolve()
    if not output_root.is_relative_to((ROOT / ".local").resolve()):
        parser.error("trial output must stay under .local")
    out = output_root / args.case / args.arm
    online = _online_prepare(args.online_manifest, args.online_task) if args.arm == "motif" else None
    threshold = (float(os.environ.get("SSS_MOTIF_MIN_SIMILARITY", "0.8"))
                 if args.arm == "motif" else None)
    if threshold is not None and not 0 <= threshold <= 1:
        parser.error("Motif similarity threshold must be in [0, 1]")
    current = preview(args.case, args.arm, args.online_manifest, args.online_task,
                      threshold, output_root)
    saved = out / "PREVIEW.json"
    approval = out / "APPROVAL.json"
    print(json.dumps({**current, "paid_api_requested": args.call_model},
                     ensure_ascii=False), flush=True)
    if not args.call_model:
        if approval.exists() and (not saved.exists() or
                                  json.loads(saved.read_text(encoding="utf-8")) != current):
            parser.error("approved preview changed")
        private(saved, current)
        return 0
    if not saved.is_file() or json.loads(saved.read_text(encoding="utf-8")) != current:
        parser.error("frozen preview is missing or changed")
    if not approval.is_file():
        parser.error("frozen run needs the user's task authorization record")
    record = json.loads(approval.read_text(encoding="utf-8"))
    if (record.get("approved") is not True or
        record.get("preview_sha256") != sha(saved) or
        record.get("budget_cap_usd") != CAP_USD or
        record.get("authorization_basis") not in {"可以运行真实试验", "再测试一下",
                                                  "可以，开始吧"}):
        parser.error("authorization does not match the frozen preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("local cost gate exceeds the task cap")
    from deepseek_harness import DeepSeekHarness
    if online:
        check_local_embedding(args.embedding_endpoint, args.embedding_model)
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one authorized paid trial reserved\n")
    marker.chmod(0o600)
    session_id = (json.loads(args.online_task.read_text(encoding="utf-8"))["session_id"]
                  if online else f"sss-meeting-{args.case}-{uuid4().hex}")
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_MEETING_CASE": args.case,
                       "DSH_PERMISSION_MODE": "read-only"})
    patches = [str(PATCH)]
    if online:
        os.environ.update({
            "SSS_ONLINE_MOTIF_MANIFEST": online["manifest"],
            "SSS_ONLINE_MOTIF_TASK": online["task"],
            "SSS_ONLINE_MOTIF_MODE": "execute",
            "SSS_MOTIF_EMBEDDING_ENDPOINT": args.embedding_endpoint,
            "SSS_MOTIF_EMBEDDING_MODEL": args.embedding_model,
            "SSS_ONLINE_MOTIF_PROMPT_SHA256": hashlib.sha256(
                prompt_for(args.case).encode("utf-8")).hexdigest(),
        })
        patches.append(online["patch"])
    guard = NativeBudgetGuard(max_model_requests=MAX_REQUESTS,
                              max_observed_input_tokens=300_000)
    events_file = out / "agent-events.jsonl"

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_file.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        def evidence_check(draft: str) -> dict:
            if not draft or not events_file.is_file():
                return {"status": "insufficient_evidence", "reason": "no_answer_or_trace"}
            events = [json.loads(line) for line in
                      events_file.read_text(encoding="utf-8").splitlines()]
            audit = audit_versioned_seed_claims(events, draft)
            if audit["status"] == "checked" and not draft.startswith("# "):
                audit = {**audit, "status": "conflict", "conflicts": [{
                    "kind": "delivery_format", "message":
                    "交付正文必须从一级 Markdown 标题开始；不要加入思考过程或额外前言"}]}
            return audit

        repair_requests = 0
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="off", max_tokens=MAX_OUTPUT_TOKENS,
            cwd=str(out), runtime_cwd=str(out),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=tuple(patches), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=600,
        ) as harness:
            result = harness.run(prompt_for(args.case),
                session_id=session_id, on_notification=observe)
            evidence_audit = evidence_check(deliverable_body(result.final_response))
            while repair_requests < MAX_EVIDENCE_REPAIRS:
                repair_prompt = None
                if evidence_audit["status"] == "conflict":
                    facts = [(
                        f"{row['version']} {row['group']}: 正确的逐种子值是 {row['expected']}"
                        if row.get("kind") == "seed_series" else row["message"])
                        for row in evidence_audit["conflicts"]]
                    repair_prompt = (
                        "上一份待审报告与已读取的原始数据冲突。请按以下经工具核验的事实"
                        "重新输出完整 Markdown，核对版本、分组与统计术语：\n" +
                        "\n".join(facts))
                elif evidence_audit["status"] == "insufficient_evidence":
                    reason = evidence_audit.get("reason")
                    guidance = {
                        "previous_version_mismatch":
                            "上一版实验尚未以事件给出的对象 ID 固定并核对版本。"
                            "请读取该对象和完整逐行数据，再与当前版逐行复算。",
                        "full_row_pair_missing":
                            "当前版和上一版的完整逐行数据尚未都读取。"
                            "请分别读取两版完整记录并核对版本，再复算。",
                        "metric_contract_missing":
                            "当前实验的指标口径尚未读取。请固定并读取当前实验对象，"
                            "依据返回的指标契约复算。",
                        "row_version_mismatch":
                            "逐行数据与已固定版本不符。请重新固定相关对象、核对版本，"
                            "再读取数据；若无法一致，明确停在待复核。",
                    }.get(reason)
                    if guidance:
                        repair_prompt = (
                            "上一份稿件缺少交付所需的原始证据，当前不能通过版本核验。"
                            + guidance + "不要只凭旧稿或哈希猜上一版数值；"
                            "只有严格满足分层与总体反向时才能称辛普森悖论。"
                            "完成工具核查后重新输出完整的一页 Markdown。")
                if repair_prompt is None:
                    break
                attempt = repair_requests + 1
                private(out / f"EVIDENCE_AUDIT_ATTEMPT_{attempt}.json", evidence_audit)
                draft = out / f"agent-answer.attempt-{attempt}.unverified.md"
                draft.write_text(result.final_response.strip() + "\n", encoding="utf-8")
                draft.chmod(0o600)
                result = harness.run(repair_prompt, session_id=session_id,
                                     on_notification=observe)
                repair_requests += 1
                evidence_audit = evidence_check(deliverable_body(result.final_response))
        answer = deliverable_body(result.final_response)
        if answer != result.final_response.strip():
            raw_path = out / "agent-raw-final.txt"
            raw_path.write_text(result.final_response.strip() + "\n", encoding="utf-8")
            raw_path.chmod(0o600)
        evidence_audit = evidence_check(answer)
        private(out / "EVIDENCE_AUDIT.json", evidence_audit)
        if answer:
            verified = evidence_audit["status"] == "checked"
            target = out / ("agent-answer.md" if verified else "agent-answer.unverified.md")
            target.write_text(answer + "\n", encoding="utf-8")
            target.chmod(0o600)
            if verified:
                qmd = out / "agent-answer.qmd"
                qmd.write_text('---\ntitle: "合成组会待审决定"\nformat: html\n---\n\n'
                               + answer + "\n", encoding="utf-8")
                qmd.chmod(0o600)
                subprocess.run(["quarto", "render", str(qmd), "--to", "html",
                                "--no-execute"], check=True, capture_output=True, text=True)
        status = ("done" if answer and result.finish_reason == "completed" and
                  evidence_audit["status"] == "checked" else
                  "evidence_conflict" if evidence_audit["status"] == "conflict" else
                  "evidence_unverified" if evidence_audit["status"] == "insufficient_evidence"
                  else "incomplete")
        report = {"status": status, "finish_reason": result.finish_reason,
                  "answer_characters": len(answer),
                  "evidence_audit_status": evidence_audit["status"],
                  "evidence_repair_requests": repair_requests}
    except Exception as exc:
        report = {"status": "error", "error_type": type(exc).__name__,
                  "error": str(exc)[:300]}
    report.update({"case": args.case, "arm": args.arm, "session_id": session_id,
                   "git_head": subprocess.check_output(
                       ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests,
                   "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                   **_usage(guard.events)})
    private(out / "agent-metrics.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
