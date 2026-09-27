"""Build three deterministic, explicitly synthetic meeting-decision fixtures.

The generated workbooks are WPS-compatible local .xlsx files. This builder is
for fixture maintenance, never an Agent tool or a source of benchmark credit.
"""

from __future__ import annotations

import json
import hashlib
import io
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parent

CASES = {
    "family_shift": {
        "title": "新目标家族上的改进是否成立",
        "metric": {"id": "correct_rate", "numerator": "correct", "denominator": "cases",
                   "allowed_groups": ["variant", "cohort"]},
        "rows": [
            ("baseline", "seen", 1, 40, 25), ("baseline", "seen", 2, 40, 24),
            ("baseline", "seen", 3, 40, 23), ("baseline", "unseen", 1, 40, 24),
            ("baseline", "unseen", 2, 40, 24), ("baseline", "unseen", 3, 40, 24),
            ("candidate", "seen", 1, 40, 30), ("candidate", "seen", 2, 40, 30),
            ("candidate", "seen", 3, 40, 30), ("candidate", "unseen", 1, 40, 23),
            ("candidate", "unseen", 2, 40, 22), ("candidate", "unseen", 3, 40, 21),
        ],
        "prior_adjustment": {("candidate", "unseen"): 5},
        "note": {
            "claim_id": "claim:family_shift:generalization",
            "text": "旧判断：候选方法整体正确率较高，可能改善新目标家族泛化。组会前需确认新家族是否也受益；不能把总体均值当作分组结论。",
            "decision_options": ["补新家族重复实验", "先审计家族划分", "维持旧判断并注明边界"],
            "depends_on": "wps:family_shift:run_2026w39",
        },
        "annotation": {
            "title": "合成文献批注：分布外评测",
            "text": "虚构方法说明：总体提升可由已见家族主导；报告新家族指标前须固定家族划分并排除同源样本重叠。这里不是本实验的观测结果。",
        },
        "event": {"changed_fields": ["correct"],
                  "message": "新一轮结果进入实验表；请检查总体与新目标家族的旧判断。"},
    },
    "label_audit": {
        "title": "正确率提升是否依赖待审标签",
        "metric": {"id": "correct_rate", "numerator": "correct", "denominator": "cases",
                   "allowed_groups": ["variant", "label_status"]},
        "rows": [
            ("baseline", "verified", 1, 40, 32), ("baseline", "verified", 2, 40, 32),
            ("baseline", "verified", 3, 40, 32), ("baseline", "unreviewed", 1, 40, 18),
            ("baseline", "unreviewed", 2, 40, 18), ("baseline", "unreviewed", 3, 40, 18),
            ("candidate", "verified", 1, 40, 33), ("candidate", "verified", 2, 40, 33),
            ("candidate", "verified", 3, 40, 33), ("candidate", "unreviewed", 1, 40, 26),
            ("candidate", "unreviewed", 2, 40, 26), ("candidate", "unreviewed", 3, 40, 26),
        ],
        "prior_adjustment": {("candidate", "verified"): 3},
        "note": {
            "claim_id": "claim:label_audit:robust_gain",
            "text": "旧判断：候选方法总体正确率更高。待审标签比例较高，尚不能说提升在已核验标签上同样明显。下一步资源只够做一次小范围审计或一次重复实验。",
            "decision_options": ["先审计标签", "先做重复实验", "保留总体提升但收窄主张"],
            "depends_on": "wps:label_audit:run_2026w39",
        },
        "annotation": {
            "title": "合成文献批注：噪声标签",
            "text": "虚构研究提醒：模型对待审标签的表现可能随审计口径改变；不能将未审子集的分数自动解释为已验证泛化。",
        },
        "event": {"changed_fields": ["correct", "label_status"],
                  "message": "本周补录按标签审计状态划分的结果；请检查旧的总体提升表述。"},
    },
    "hardware_latency": {
        "title": "候选方法的延迟优势是否来自设备构成",
        "metric": {"id": "mean_latency_ms", "numerator": "latency_total_ms",
                   "denominator": "requests", "allowed_groups": ["variant", "hardware"]},
        "rows": [
            ("baseline", "fast", 1, 100, 10000),
            ("baseline", "slow", 1, 100, 20000),
            ("baseline", "slow", 2, 100, 20000),
            ("baseline", "slow", 3, 100, 20000),
            ("candidate", "fast", 1, 100, 10500),
            ("candidate", "fast", 2, 100, 10500),
            ("candidate", "fast", 3, 100, 10500),
            ("candidate", "slow", 1, 100, 20500),
        ],
        "prior_adjustment": {("candidate", "fast"): -1000,
                             ("candidate", "slow"): -1000},
        "note": {
            "claim_id": "claim:hardware_latency:speedup",
            "text": "旧判断：候选方法汇总平均延迟更低。两组运行的设备构成不同，尚未通过同设备配对测量，不应直接归因于算法。",
            "decision_options": ["做同设备配对测试", "先检查计时口径", "暂时只报告描述统计"],
            "depends_on": "wps:hardware_latency:run_2026w39",
        },
        "annotation": {
            "title": "合成文献批注：延迟比较",
            "text": "虚构方法说明：跨设备池的总平均延迟不等于每种设备上的速度优势；比较前应对齐硬件、负载和计时范围。",
        },
        "event": {"changed_fields": ["latency_total_ms", "hardware"],
                  "message": "新一轮基准测试汇总已更新；请核查候选方法的延迟优势。"},
    },
}


def build() -> None:
    for case_id, spec in CASES.items():
        case_dir = ROOT / "sources" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        metric = spec["metric"]
        group = metric["allowed_groups"][1]
        columns = ["variant", group, "seed", metric["denominator"], metric["numerator"]]
        def write_book(path: Path, rows: list[tuple]) -> None:
            book = Workbook()
            book.properties.created = datetime(2026, 9, 27)
            book.properties.modified = datetime(2026, 9, 27)
            sheet = book.active
            sheet.title = "实验记录"
            sheet.append(columns)
            for row in rows:
                sheet.append(row)
            book.save(path)
            # XLSX is a ZIP archive. Fix member timestamps so rebuilding the
            # same synthetic source does not spuriously invalidate its version.
            stable = io.BytesIO()
            with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
                stable, "w", compression=zipfile.ZIP_DEFLATED
            ) as target:
                for name in source.namelist():
                    member = zipfile.ZipInfo(name, (2026, 9, 27, 0, 0, 0))
                    member.compress_type = zipfile.ZIP_DEFLATED
                    member.external_attr = 0o600 << 16
                    target.writestr(member, source.read(name))
            path.write_bytes(stable.getvalue())

        write_book(case_dir / "experiment.xlsx", spec["rows"])
        prior_rows = []
        for row in spec["rows"]:
            adjustment = spec["prior_adjustment"].get((row[0], row[1]), 0)
            prior_rows.append((*row[:-1], row[-1] + adjustment))
        prior_path = case_dir / "previous_experiment.xlsx"
        write_book(prior_path, prior_rows)
        (case_dir / "metric.json").write_text(
            json.dumps(metric, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (case_dir / "note.json").write_text(
            json.dumps(spec["note"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (case_dir / "annotation.json").write_text(
            json.dumps(spec["annotation"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        event = {"event_id": f"event:{case_id}:w39", "experiment_id": spec["note"]["depends_on"],
                 "previous_experiment_id": f"wps:{case_id}:run_2026w38",
                 "previous_version_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
                 "title": spec["title"], **spec["event"]}
        (case_dir / "event.json").write_text(
            json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
