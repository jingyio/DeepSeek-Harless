"""Build three frozen, synthetic cross-application research decisions."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parent
FROZEN_MODIFIED = b"2026-09-28T00:00:00Z"
CASES = {
    "model_rsi_state": {
        "title": "内部能力状态能否迁移到未见任务",
        "metric": {"id": "correct_rate", "numerator": "correct", "denominator": "cases",
                   "allowed_groups": ["variant", "task_family"]},
        "rows": [
            ("baseline", "seen", 1, 50, 35), ("baseline", "seen", 2, 50, 34),
            ("baseline", "seen", 3, 50, 36), ("baseline", "unseen", 1, 50, 30),
            ("baseline", "unseen", 2, 50, 29), ("baseline", "unseen", 3, 50, 31),
            ("candidate", "seen", 1, 50, 43), ("candidate", "seen", 2, 50, 42),
            ("candidate", "seen", 3, 50, 44), ("candidate", "unseen", 1, 50, 27),
            ("candidate", "unseen", 2, 50, 25), ("candidate", "unseen", 3, 50, 26),
        ],
        "prior_adjustment": {("candidate", "unseen"): 9},
        "note": {
            "claim_id": "claim:model_rsi_state:transfer",
            "text": "旧判断：可更新的内部能力状态可能提高未见任务迁移。整体正确率向好，"
                    "但训练任务与留出任务必须分别复核，不能把已见任务增益当作迁移证据。",
            "decision_options": ["补留出任务重复实验", "核查任务家族划分", "维持跨任务迁移主张"],
        },
        "annotation": {
            "title": "合成方法批注：能力状态迁移",
            "text": "训练任务上的状态更新收益不自动证明留出任务的收益；"
                    "若任务家族共享模板，还需排除泄漏。此批注是方法约束，不是本次观测。",
        },
        "event": {"changed_fields": ["correct"],
                  "message": "未见任务的新批次结果已录入，请决定是否维持迁移主张。"},
    },
    "aidd_mutation": {
        "title": "样本效率提升能否外推到新突变类型",
        "metric": {"id": "assay_yield", "numerator": "valid_predictions",
                   "denominator": "assays", "allowed_groups": ["variant", "mutation_class"]},
        "rows": [
            ("baseline", "common", 1, 40, 28), ("baseline", "common", 2, 40, 27),
            ("baseline", "common", 3, 40, 29), ("baseline", "novel", 1, 40, 23),
            ("baseline", "novel", 2, 40, 22), ("baseline", "novel", 3, 40, 24),
            ("candidate", "common", 1, 40, 34), ("candidate", "common", 2, 40, 33),
            ("candidate", "common", 3, 40, 35), ("candidate", "novel", 1, 40, 20),
            ("candidate", "novel", 2, 40, 18), ("candidate", "novel", 3, 40, 19),
        ],
        "prior_adjustment": {("candidate", "novel"): 10},
        "note": {
            "claim_id": "claim:aidd_mutation:sample_efficiency",
            "text": "旧判断：候选 AIDD 策略用相同测定预算获得更多有效预测，"
                    "可能对未见突变也更省样本。新突变类别需独立统计，且测定预算口径不能变化。",
            "decision_options": ["补新突变测定", "先审预算和类别口径", "继续外推样本效率"],
        },
        "annotation": {
            "title": "合成方法批注：突变外推",
            "text": "常见突变的单位测定收益不能直接外推到新突变类别；"
                    "比较前必须固定突变类别与测定预算。",
        },
        "event": {"changed_fields": ["valid_predictions"],
                  "message": "新突变类别复核结果已录入，请重查样本效率主张。"},
    },
    "agent_tool_transfer": {
        "title": "工具 schema 变化后链式任务是否仍可靠",
        "metric": {"id": "task_success_rate", "numerator": "successful_tasks",
                   "denominator": "attempted_tasks", "allowed_groups": ["variant", "tool_chain"]},
        "rows": [
            ("baseline", "stable", 1, 30, 21), ("baseline", "stable", 2, 30, 20),
            ("baseline", "stable", 3, 30, 22), ("baseline", "changed_schema", 1, 30, 18),
            ("baseline", "changed_schema", 2, 30, 19),
            ("baseline", "changed_schema", 3, 30, 17),
            ("candidate", "stable", 1, 30, 25), ("candidate", "stable", 2, 30, 24),
            ("candidate", "stable", 3, 30, 26),
            ("candidate", "changed_schema", 1, 30, 16),
            ("candidate", "changed_schema", 2, 30, 15),
            ("candidate", "changed_schema", 3, 30, 17),
        ],
        "prior_adjustment": {("candidate", "changed_schema"): 8},
        "note": {
            "claim_id": "claim:agent_tool_transfer:reliability",
            "text": "旧判断：候选 Agent 的跨工具链成功率稳定。工具 schema 改版后，"
                    "需要区分接口失配与模型选择错误；仅看整体成功率不能决定先修哪处。",
            "decision_options": ["先核查 schema 兼容", "补改版链任务", "沿用稳定性主张"],
        },
        "annotation": {
            "title": "合成方法批注：工具迁移",
            "text": "工具调用失败可能由 schema 改动、授权或模型参数选择造成；"
                    "成功率下降本身不能确定故障归因。",
        },
        "event": {"changed_fields": ["successful_tasks"],
                  "message": "工具 schema 更新后的链式任务结果已录入，请复核可靠性主张。"},
    },
}


def _book(path: Path, columns: list[str], rows: list[tuple]) -> None:
    book = Workbook()
    book.properties.created = datetime(2026, 9, 28)
    book.properties.modified = datetime(2026, 9, 28)
    sheet = book.active
    sheet.title = "实验记录"
    sheet.append(columns)
    for row in rows:
        sheet.append(row)
    book.save(path)
    stable = io.BytesIO()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(
            stable, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            member = zipfile.ZipInfo(name, (2026, 9, 28, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = 0o600 << 16
            content = source.read(name)
            if name == "docProps/core.xml":
                content, count = re.subn(
                    rb"(?<=<dcterms:modified xsi:type=\"dcterms:W3CDTF\">)[^<]+",
                    FROZEN_MODIFIED, content)
                if count != 1:
                    raise ValueError("workbook modified timestamp format changed")
            target.writestr(member, content)
    path.write_bytes(stable.getvalue())


def build() -> None:
    for case, spec in CASES.items():
        folder = ROOT / "sources" / case
        folder.mkdir(parents=True, exist_ok=True)
        metric = spec["metric"]
        columns = ["variant", metric["allowed_groups"][1], "seed",
                   metric["denominator"], metric["numerator"]]
        _book(folder / "experiment.xlsx", columns, spec["rows"])
        prior = [(*row[:-1], row[-1] + spec["prior_adjustment"].get(
            (row[0], row[1]), 0)) for row in spec["rows"]]
        prior_path = folder / "previous_experiment.xlsx"
        _book(prior_path, columns, prior)
        current_id = f"wps:{case}:run_2026w39"
        note = {**spec["note"], "depends_on": current_id}
        event = {"event_id": f"event:{case}:w39", "experiment_id": current_id,
                 "previous_experiment_id": f"wps:{case}:run_2026w38",
                 "previous_version_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
                 "title": spec["title"], **spec["event"]}
        for name, value in (("event", event), ("metric", metric),
                            ("note", note), ("annotation", spec["annotation"])):
            (folder / f"{name}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
