"""Create reproducible synthetic inputs and separate, agent-inaccessible oracles."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


CASES = [
    dict(id="train_materials", split="train", seed=12017, design="independent_groups",
         title="热处理对合成材料拉伸强度的影响", domain="materials science", pages=2,
         figures=2, baseline=72.0, effect=5.0, noise=5.0, unit="MPa", label="Tensile strength"),
    dict(id="train_ml", split="train", seed=23129, design="paired",
         title="同一数据划分下两种算法准确率的配对比较", domain="machine learning", pages=3,
         figures=3, baseline=0.79, effect=0.018, noise=0.021, unit="fraction", label="Accuracy"),
    dict(id="cert_environment", split="certification", seed=34031, design="regression",
         title="温度与合成水质氧含量的线性关系", domain="environmental science", pages=3,
         figures=2, baseline=11.5, effect=-0.16, noise=0.65, unit="mg/L", label="Dissolved oxygen"),
    dict(id="eval_biology", split="evaluation", seed=45007, design="independent_groups",
         title="营养处理对独立培养样本生物量的影响", domain="biology", pages=4,
         figures=3, baseline=8.0, effect=1.1, noise=1.4, unit="g", label="Biomass"),
    dict(id="eval_education", split="evaluation", seed=56101, design="paired",
         title="同一学习者训练前后测验成绩的配对分析", domain="education", pages=2,
         figures=2, baseline=67.0, effect=4.5, noise=6.0, unit="points", label="Test score"),
    dict(id="eval_energy", split="evaluation", seed=67003, design="regression",
         title="负载与合成设备能耗的关系", domain="energy engineering", pages=4,
         figures=3, baseline=18.0, effect=0.82, noise=4.0, unit="kWh", label="Energy use"),
]


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def generate_case(root: Path, case: dict, seed_offset: int = 0) -> dict:
    seed = case["seed"] + seed_offset
    rng = np.random.default_rng(seed)
    rows = []
    if case["design"] == "independent_groups":
        for group in ("control", "treatment"):
            values = rng.normal(case["baseline"] + (case["effect"] if group == "treatment" else 0),
                                case["noise"], 28)
            for index, value in enumerate(values):
                rows.append({"sample_id": f"{group[0]}{index + 1:03d}", "group": group,
                             "value": round(float(value), 6)})
        columns = {"sample_id": "独立实验单元编号", "group": "control 对照或 treatment 处理",
                   "value": "连续型主要结局"}
        design_description = "两组独立实验单元，每个样本只测量一次；组间方差未知，不假设相等。"
    elif case["design"] == "paired":
        baseline = rng.normal(case["baseline"], case["noise"] * 1.8, 32)
        changes = rng.normal(case["effect"], case["noise"] * 0.8, 32)
        for index, (before, change) in enumerate(zip(baseline, changes, strict=True)):
            for condition, value in (("before", before), ("after", before + change)):
                rows.append({"subject": f"unit{index + 1:03d}", "condition": condition,
                             "value": round(float(value), 6)})
        columns = {"subject": "配对实验单元（同一人或同一数据划分）", "condition": "before / after",
                   "value": "连续型主要结局"}
        design_description = "同一实验单元在两个条件下重复测量，必须按 subject 对齐，不能当作独立样本。"
    else:
        low, high = (10, 32) if case["id"] == "cert_environment" else (10, 95)
        xs = np.linspace(low, high, 52) + rng.normal(0, (high - low) / 150, 52)
        ys = case["baseline"] + case["effect"] * xs + rng.normal(0, case["noise"], 52)
        for index, (x, y) in enumerate(zip(xs, ys, strict=True)):
            rows.append({"sample_id": f"obs{index + 1:03d}", "predictor": round(float(x), 6),
                         "value": round(float(y), 6)})
        columns = {"sample_id": "独立观测编号", "predictor": "连续型解释变量", "value": "连续型响应变量"}
        design_description = "独立的连续型解释变量与响应变量观测；拟合带截距的一元线性关系，不能推断因果。"
    missing_indices = sorted(rng.choice(len(rows), size=2, replace=False).tolist())
    for index in missing_indices:
        rows[index]["value"] = ""
    folder = root / "cases" / case["id"]
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "data.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    study = {
        "schema_version": "research-report-study-v1", "study_id": case["id"],
        "title": case["title"], "domain": case["domain"], "split": case["split"],
        "synthetic": True, "data_file": "data.csv", "row_count": len(rows),
        "description": design_description,
        "research_question": case["title"] + "；请估计效应及不确定性，并检查数据和模型假设。",
        "columns": columns, "column_labels": {"value": case["label"],
             "predictor": "Temperature" if case["id"] == "cert_environment" else "Load"},
        "units": {"value": case["unit"], "predictor": "deg C" if case["id"] == "cert_environment" else "%"},
        "sampling_unit_column": "subject" if case["design"] == "paired" else "sample_id",
        "missingness_note": "存在少量缺失值。必须显式选择处理策略，报告删除量与潜在偏差，不得虚构或零填充。",
        "report_requirements": {"language": "zh", "pages": case["pages"],
                                "figure_count": case["figures"], "formats": ["pdf"],
                                "confidence": 0.95, "style": "journal"},
        "scope_note": "全部观测值由独立随机种子生成，仅用于软件实验，不能作为真实学科证据。",
    }
    _write_json(folder / "study.json", study)
    task = (f"请完成科研数据分析与报告任务 {case['id']}：{case['title']}。\n"
            f"先使用 inspect_study 读取元数据和真实 CSV 摘要，自己判断合适的统计设计、列名和缺失处理。\n"
            f"生成中文 {case['pages']} 页 PDF 报告，含 {case['figures']} 张不同且适合本研究的高质量图。"
            "图中可使用英文避免字体问题。报告需说明问题、设计、数据与缺失处理、效应/95%置信区间/p值、"
            "图表解读、诊断、局限及下一步，清楚注明这是合成数据；不能把相关解释成因果。\n"
            "你负责分析方案、图型与叙述等语义决定。每次 plan 工具明确设置 allow_deterministic_continuation=true，"
            "授权已批准计划内的确定性计算/渲染及验证；授权不允许插件代替你选择新方案或撰写结论。"
            "按工具结果中的可用 ID 操作。出现验证失败先解释和修订，不宣称成功。"
            "所有验证通过后返回交付文件位置和重要限制。\n")
    (folder / "task.txt").write_text(task, encoding="utf-8")
    oracle = {"study_id": case["id"], "synthetic": True, "seed": seed,
              "data_generating_design": case["design"], "population_effect": case["effect"],
              "population_baseline": case["baseline"], "noise_sd": case["noise"],
              "injected_missing_rows_zero_based": missing_indices,
              "required_pages": case["pages"], "required_figures": case["figures"],
              "expected_effect_direction": "positive" if case["effect"] > 0 else "negative",
              "not_for_agent": True}
    _write_json(root / "oracles" / f"{case['id']}.json", oracle)
    return {"study_id": case["id"], "split": case["split"], "rows": len(rows),
            "data_sha256": hashlib.sha256((folder / "data.csv").read_bytes()).hexdigest()}


def generate(root: Path, seed_offset: int = 0) -> dict:
    root = root.resolve()
    manifest = {"synthetic": True, "generator": "research_report_agent_v1",
                "seed_offset": seed_offset, "cases": [generate_case(root, case, seed_offset) for case in CASES]}
    _write_json(root / "dataset_manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed-offset", type=int, default=0)
    arguments = parser.parse_args()
    print(json.dumps(generate(arguments.output, arguments.seed_offset), ensure_ascii=False, indent=2))
