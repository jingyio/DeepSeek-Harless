"""Build a fresh held-out set of synthetic, versioned research decisions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.meeting_decision_chain_v2.build_fixtures import _book


ROOT = Path(__file__).resolve().parent
CASES = {
    "rna_batch": {
        "title": "RNA 校准在外部实验批次中是否仍有效",
        "metric": {"id": "call_yield", "numerator": "valid_calls",
                   "denominator": "assays", "allowed_groups": ["variant", "lab_batch"]},
        "rows": [
            ("baseline", "internal", 1, 45, 30), ("baseline", "internal", 2, 45, 31),
            ("baseline", "internal", 3, 45, 29), ("baseline", "external", 1, 45, 27),
            ("baseline", "external", 2, 45, 26), ("baseline", "external", 3, 45, 28),
            ("candidate", "internal", 1, 45, 37), ("candidate", "internal", 2, 45, 38),
            ("candidate", "internal", 3, 45, 36), ("candidate", "external", 1, 45, 24),
            ("candidate", "external", 2, 45, 23), ("candidate", "external", 3, 45, 25),
        ],
        "prior_adjustment": {("candidate", "external"): 7},
        "note": {
            "claim_id": "claim:rna_batch:transfer",
            "text": "旧判断：校准方案在内部批次提高有效调用率，可能迁移到外部实验室批次。"
                    "必须分批次复核，且先核查试剂与测定口径是否可比。",
            "decision_options": ["补外部批次重复实验", "核查试剂与批次口径", "继续宣称跨实验室迁移"],
        },
        "annotation": {
            "title": "合成方法批注：外部批次",
            "text": "内部批次的有效调用率不能替代外部批次复现；试剂和阈值变动需单独审计。"
                    "这条批注不含本次测量值。",
        },
        "event": {"changed_fields": ["valid_calls"],
                  "message": "外部实验室批次的复核结果更新，请重新审议校准迁移主张。"},
    },
    "retrieval_language": {
        "title": "检索增强是否覆盖低资源语种",
        "metric": {"id": "retrieval_accuracy", "numerator": "correct_queries",
                   "denominator": "queries", "allowed_groups": ["variant", "language_group"]},
        "rows": [
            ("baseline", "high_resource", 1, 60, 44),
            ("baseline", "high_resource", 2, 60, 43),
            ("baseline", "high_resource", 3, 60, 45),
            ("baseline", "low_resource", 1, 60, 30),
            ("baseline", "low_resource", 2, 60, 29),
            ("baseline", "low_resource", 3, 60, 31),
            ("candidate", "high_resource", 1, 60, 51),
            ("candidate", "high_resource", 2, 60, 50),
            ("candidate", "high_resource", 3, 60, 52),
            ("candidate", "low_resource", 1, 60, 34),
            ("candidate", "low_resource", 2, 60, 33),
            ("candidate", "low_resource", 3, 60, 35),
        ],
        "prior_adjustment": {("candidate", "low_resource"): -9},
        "note": {
            "claim_id": "claim:retrieval_language:coverage",
            "text": "旧判断：检索增强主要改善高资源语种；低资源覆盖证据不足。"
                    "若新增低资源评测，应重新审议而不是沿用整体均值。",
            "decision_options": ["补独立低资源语种", "维持证据不足", "直接宣称全面覆盖"],
        },
        "annotation": {
            "title": "合成方法批注：语言覆盖",
            "text": "同一语种的多个查询不等于独立语种复现；报告须区分语种数量与查询数量。",
        },
        "event": {"changed_fields": ["correct_queries"],
                  "message": "低资源语种新批次修正了检索正确数，请复核覆盖结论。"},
    },
    "robot_protocol": {
        "title": "自动化实验步骤在新协议下是否可靠",
        "metric": {"id": "trial_success_rate", "numerator": "successful_trials",
                   "denominator": "trials", "allowed_groups": ["variant", "protocol"]},
        "rows": [
            ("baseline", "familiar", 1, 35, 25), ("baseline", "familiar", 2, 35, 24),
            ("baseline", "familiar", 3, 35, 26), ("baseline", "new", 1, 35, 21),
            ("baseline", "new", 2, 35, 20), ("baseline", "new", 3, 35, 22),
            ("candidate", "familiar", 1, 35, 30), ("candidate", "familiar", 2, 35, 29),
            ("candidate", "familiar", 3, 35, 31), ("candidate", "new", 1, 35, 27),
            ("candidate", "new", 2, 35, 26), ("candidate", "new", 3, 35, 28),
        ],
        "prior_adjustment": {("candidate", "new"): 6},
        "note": {
            "claim_id": "claim:robot_protocol:reliability",
            "text": "旧判断：自动化步骤在熟悉协议上可靠，新协议亦可能沿用；"
                    "新协议结果需单列并记录人工干预次数。",
            "decision_options": ["先查新协议执行日志", "追加新协议重复实验", "直接沿用可靠性主张"],
        },
        "annotation": {
            "title": "合成方法批注：协议迁移",
            "text": "成功率无法区分机械故障、操作员补救和规划错误；"
                    "若未记录人工干预，不可把成功率当作自主可靠性。",
        },
        "event": {"changed_fields": ["successful_trials"],
                  "message": "新协议运行记录修订，请重新判断自动化可靠性主张。"},
    },
}


def build_cases(root: Path, cases: dict) -> None:
    for case, spec in cases.items():
        folder = root / "sources" / case
        folder.mkdir(parents=True, exist_ok=True)
        metric = spec["metric"]
        columns = ["variant", metric["allowed_groups"][1], "seed",
                   metric["denominator"], metric["numerator"]]
        _book(folder / "experiment.xlsx", columns, spec["rows"])
        prior = [(*row[:-1], row[-1] + spec["prior_adjustment"].get((row[0], row[1]), 0))
                 for row in spec["rows"]]
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


def build() -> None:
    build_cases(ROOT, CASES)


if __name__ == "__main__":
    build()
