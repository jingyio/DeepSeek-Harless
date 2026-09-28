"""Local Python and Quarto tools exposed to DeepSeek Harness through MCP.

All generated files stay below .local/python-workspace. On macOS, executed
programs run under sandbox-exec with writes and network access denied outside
that directory. No shell command supplied by the model is executed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from src.mcp.structured_research_tools import (
    aggregate_records, compare_results, compare_sources, inspect_records,
    list_research_sources, mcp_safe, pin_source, rank_grouped_result,
)


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("SSS_PYTHON_WORKSPACE", str(ROOT / ".local" / "python-workspace"))).resolve()
if not WORKSPACE.is_relative_to((ROOT / ".local").resolve()):
    raise ValueError("Python workspace must stay under SSS/.local")
WORKSPACE.mkdir(parents=True, exist_ok=True)
QUARTO = shutil.which("quarto") or "/usr/local/bin/quarto"
SANDBOX = shutil.which("sandbox-exec")
server = MCPServer(
    "sss-local-research-tools",
    instructions="Work in the private Python/Quarto workspace. Python and Quarto may read local inputs, "
    "but their subprocesses cannot write outside this workspace or use the network. "
    "Use write_workspace_text to create a script or .qmd, then run_python or "
    "preview_quarto/render_quarto. For auditable read-only work on frozen task "
    "files, pin_source then inspect_records and aggregate_records using returned "
    "IDs; compare_sources/compare_results check versions. Generated outputs are "
    "drafts for human review.",
)


def _path(relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("Use a relative path inside the Python workspace")
    target = (WORKSPACE / relative_path).resolve()
    if not target.is_relative_to(WORKSPACE.resolve()):
        raise ValueError("Path leaves the Python workspace")
    return target


def _sandboxed(command: list[str], timeout_seconds: int) -> dict[str, Any]:
    if not SANDBOX:
        raise RuntimeError("This host needs a filesystem sandbox before code execution")
    private = (ROOT / ".local" / "obsidian-api-key",
               ROOT / ".local" / "sealed",
               ROOT / ".local" / "google-calendar",
               ROOT / ".local" / "google-gmail",
               ROOT / ".local" / "dsh",
               Path.home() / ".ssh", Path.home() / ".aws",
               Path.home() / ".gnupg", Path.home() / ".config",
               Path.home() / "Library" / "Keychains",
               Path.home() / "Library" / "Application Support" / "obsidian",
               Path.home() / "Library" / "Application Support" / "Zotero")
    read_denials = " ".join(f'(deny file-read* (subpath "{path}"))' for path in private)
    profile = ("(version 1) (allow default) " + read_denials + " "
               f'(allow file-read* (subpath "{WORKSPACE}")) '
               '(deny file-write*) (deny network*) '
               '(allow file-write* (literal "/dev/null")) '
               f'(allow file-write* (subpath "{WORKSPACE}"))')
    temp = WORKSPACE / "tmp"
    temp.mkdir(exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "TMPDIR": str(temp),
        "MPLCONFIGDIR": str(WORKSPACE / ".matplotlib"),
        "XDG_CACHE_HOME": str(WORKSPACE / ".cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    try:
        result = subprocess.run(
            [SANDBOX, "-p", profile, *command], cwd=WORKSPACE, env=env,
            capture_output=True, text=True, errors="replace", timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "timed_out": True, "seconds": timeout_seconds,
                "stdout": (exc.stdout or b"").decode("utf-8", "replace")[:12000]
                if isinstance(exc.stdout, bytes) else (exc.stdout or "")[:12000]}
    return {"ok": result.returncode == 0, "exit_code": result.returncode,
            "stdout": result.stdout[:12000], "stderr": result.stderr[:4000],
            "output_truncated": len(result.stdout) > 12000 or len(result.stderr) > 4000}


def python_environment() -> dict[str, Any]:
    """Show the local Python version, common analysis packages and output folder."""
    from importlib import metadata

    packages = {}
    for name in ("numpy", "pandas", "matplotlib", "scipy", "pypdf"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": sys.version.split()[0], "packages": packages,
            "workspace": str(WORKSPACE), "sandbox_available": bool(SANDBOX)}


def write_workspace_text(path: str, content: str) -> dict[str, Any]:
    """Create or replace a text script, dataset or Quarto document in the private workspace."""
    if len(content.encode("utf-8")) > 200_000:
        raise ValueError("Text exceeds 200 KB")
    target = _path(path)
    if target.suffix.lower() not in {".py", ".qmd", ".md", ".txt", ".csv", ".tsv", ".json"}:
        raise ValueError("Unsupported text file extension")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": str(target), "bytes": target.stat().st_size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def run_python(code: str, timeout_seconds: int = 30) -> dict[str, Any]:
    """Run Python analysis in the private workspace with bounded time and output."""
    if not 1 <= timeout_seconds <= 120:
        raise ValueError("timeout_seconds must be 1–120")
    if len(code.encode("utf-8")) > 50_000:
        raise ValueError("Code exceeds 50 KB")
    script = WORKSPACE / "_latest_run.py"
    script.write_text(code, encoding="utf-8")
    result = _sandboxed([sys.executable, str(script)], timeout_seconds)
    result["workspace"] = str(WORKSPACE)
    result["script_sha256"] = hashlib.sha256(code.encode()).hexdigest()
    return result


def list_workspace_files() -> list[dict[str, Any]]:
    """List generated files in the private analysis workspace."""
    files = []
    for path in sorted(WORKSPACE.rglob("*")):
        if path.is_file() and not path.is_symlink():
            files.append({"path": str(path.relative_to(WORKSPACE)), "bytes": path.stat().st_size})
        if len(files) >= 100:
            break
    return files


def preview_quarto(path: str, output_format: str = "html") -> dict[str, Any]:
    """Check a Quarto source and describe the planned local render."""
    if output_format not in {"html", "pdf", "docx", "revealjs", "pptx"}:
        raise ValueError("Unsupported Quarto output format")
    source = _path(path)
    if source.suffix.lower() != ".qmd" or not source.is_file():
        raise ValueError("Existing .qmd file required in the Python workspace")
    return {"source": str(source), "format": output_format,
            "output_directory": str(WORKSPACE / "rendered"),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "quarto_available": Path(QUARTO).is_file(),
            "note": "Quarto can execute code cells in this source; output stays in the private workspace."}


def render_quarto(path: str, output_format: str = "html", timeout_seconds: int = 120) -> dict[str, Any]:
    """Render a private Quarto draft to HTML, PDF, Word, slides or PowerPoint."""
    preview = preview_quarto(path, output_format)
    if not preview["quarto_available"]:
        raise RuntimeError("Quarto is not installed")
    if not 1 <= timeout_seconds <= 300:
        raise ValueError("timeout_seconds must be 1–300")
    output_dir = WORKSPACE / "rendered"
    output_dir.mkdir(exist_ok=True)
    result = _sandboxed([QUARTO, "render", str(_path(path)), "--to", output_format,
                         "--output-dir", str(output_dir)], timeout_seconds)
    result["source_sha256"] = preview["source_sha256"]
    result["output_directory"] = str(output_dir)
    return result


for function, read_only in (
    (python_environment, True), (write_workspace_text, False),
    (run_python, False), (list_workspace_files, True),
    (preview_quarto, True), (render_quarto, False),
    (list_research_sources, True), (pin_source, True), (inspect_records, True),
    (aggregate_records, True), (rank_grouped_result, True), (compare_sources, True),
    (compare_results, True),
):
    exposed = mcp_safe(function) if function in (list_research_sources, pin_source, inspect_records,
                                                rank_grouped_result,
                                                aggregate_records, compare_sources,
                                                compare_results) else function
    server.add_tool(exposed, name=function.__name__,
                    annotations=ToolAnnotations(readOnlyHint=read_only,
                                                destructiveHint=False, openWorldHint=False))


if __name__ == "__main__":
    server.run(transport="stdio")
