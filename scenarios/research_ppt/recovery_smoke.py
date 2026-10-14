"""失败计划局部恢复的真实 stdio MCP 诊断；无模型，不把工程诊断当科研质量或降本结果。"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.service import private_path
from scenarios.research_ppt.delivery_smoke import params, verify_artifacts


def write(path: Path, value: object) -> None:
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def call(client: Client, out: Path, name: str, args: dict, expected_error: set[str] | None = None) -> dict:
    response = (await client.call_tool(name, args)).model_dump(mode="json", by_alias=True)
    value = response.get("structuredContent")
    if not isinstance(value, dict):
        block = next((block for block in response.get("content", []) if block.get("type") == "text"), {})
        value = json.loads(block.get("text", "{}"))
    with (out / "actual-mcp-calls.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"tool": name, "arguments": args, "response": response}, ensure_ascii=False) + "\n")
    if expected_error is None:
        if response.get("isError") is True or value.get("ok") is False:
            raise AssertionError(f"{name} unexpected failure: {value}")
    elif response.get("isError") is not True or value.get("code") not in expected_error:
        raise AssertionError(f"{name} expected {expected_error}: {value}")
    return value


async def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    import fitz
    source = out / "recovery-source.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Synthetic recovery source.\nEngineering diagnostic only.")
        page.insert_text((72, 150), "Figure 1: A bounded recovery test.")
        document.save(source)
    job = prepare([source], "两页局部失败恢复工程诊断，保留来源；不作科研质量结论。", 2,
                  allow_output=True, template="academic", execution_policy="host_delivery")
    baseline = prepare([source], "普通步骤恢复拒绝诊断；不输出。", 2,
                       allow_output=True, template="academic", execution_policy="baseline_steps")
    data = read(job)
    out_data = {"passed": False, "model_requests": 0, "checks": [], "job": str(job),
                "baseline_job": str(baseline), "scope": "real_stdio_mcp_local_recovery_no_model"}
    def check(name: str, value: bool, **evidence: object) -> None:
        row = {"name": name, "passed": bool(value), "evidence": evidence}
        out_data["checks"].append(row)
        write(out / "progress.json", out_data)
        if not value:
            raise AssertionError(name)
    started = time.monotonic()
    try:
        inputs = data["inputs"]
        async with Client(params(job), read_timeout_seconds=180) as client:
            tools = [tool.name for tool in (await client.list_tools()).tools]
            check("recovery_tools_in_frozen_order", tools[-6:] == ["render_delivery", "revise_delivery", "pin_deck_pages",
                "read_pinned_deck_pages", "read_pending_plan", "repair_pending_plan"], tools=tools)
            listed = await call(client, out, "list_inputs", {})
            pin = await call(client, out, "pin_source", {"document_id": listed["inputs"][0]["document_id"]})
            source_view = await call(client, out, "read_source", {"source_id": pin["source_id"]})
            citation = [{"source_id": pin["source_id"], "page": 1}]
            slide = lambda index: {"title": f"恢复诊断页 {index}", "bullets": ["只验证局部修复路径"],
                                   "sources": citation, "notes": source_view["pages"][0]["text"][:120]}
            original = {"title": "局部恢复测试", "template": "academic", "slides": [slide(1), slide(2)]}
            bad = {**copy.deepcopy(original), "slides": [slide(1), slide(2), slide(3)]}
            failed = await call(client, out, "render_deck", {"plan": bad}, expected_error={"slide_count_mismatch"})
            pending = failed.get("pending_plan")
            check("failed_plan_saved_without_model", isinstance(pending, dict) and pending.get("status") == "pending",
                  pending_keys=sorted(pending or {}))
            duplicate = await call(client, out, "render_deck", {"plan": bad}, expected_error={"pending_plan_exists"})
            check("full_plan_resubmission_blocked", duplicate.get("pending_plan", {}).get("draft_id") == pending["draft_id"])
            selected = await call(client, out, "read_pending_plan", {"draft_id": pending["draft_id"],
                "version_sha256": pending["version_sha256"], "pages": [1, 3]})
            check("only_explicit_failed_pages_read", [row["page"] for row in selected["slides"]] == [1, 3])
            repaired = await call(client, out, "repair_pending_plan", {"draft_id": pending["draft_id"],
                "version_sha256": pending["version_sha256"], "deletions": [3],
                "updates": [{"page": 1, "changes": {"title": "恢复后的第一页"}}]})
            check("local_patch_runs_original_delivery", repaired.get("delivered") is True and
                  verify_artifacts(repaired, 2), delivery_sha256=repaired.get("file_sha256"))
            check("non_target_slide_and_source_preserved", repaired.get("local_repair", {}).get("changed_pages") == [1]
                  and repaired.get("local_repair", {}).get("deleted_pages") == [3])
            old = await call(client, out, "read_pending_plan", {"draft_id": pending["draft_id"],
                "version_sha256": pending["version_sha256"], "pages": [1]}, expected_error={"pending_version_changed", "pending_already_delivered"})
            check("stale_version_rejected", old.get("code") in {"pending_version_changed", "pending_already_delivered"})
        async with Client(params(baseline), read_timeout_seconds=180) as client:
            listed = await call(client, out, "list_inputs", {})
            pin = await call(client, out, "pin_source", {"document_id": listed["inputs"][0]["document_id"]})
            source_view = await call(client, out, "read_source", {"source_id": pin["source_id"]})
            citation = [{"source_id": pin["source_id"], "page": 1}]
            baseline_plan = {"title": "普通路径", "template": "academic", "slides": [
                {"title": "普通页", "bullets": ["普通路径"], "sources": citation, "notes": source_view["pages"][0]["text"][:100]},
                {"title": "普通页2", "bullets": ["普通路径"], "sources": citation, "notes": source_view["pages"][0]["text"][:100]}]}
            await call(client, out, "read_pending_plan", {"draft_id": pending["draft_id"],
                "version_sha256": pending["version_sha256"], "pages": [1]}, expected_error={"execution_policy_tool_disabled"})
            check("baseline_does_not_get_host_recovery", True)
        out_data["passed"] = True
    except Exception as error:
        out_data.update(error_type=type(error).__name__, error_message=str(error)[:1200], negative_evidence_retained=True)
    out_data["elapsed_seconds"] = round(time.monotonic() - started, 3)
    write(out / "summary.json", out_data)
    print(json.dumps({"passed": out_data["passed"], "out": str(out), "model_requests": 0}, ensure_ascii=False), flush=True)
    return 0 if out_data["passed"] else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    raise SystemExit(asyncio.run(run(private_path(parser.parse_args().out))))
