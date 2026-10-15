"""Generate seven fresh synthetic datasets for the free-semantics v3 experiment.

The generator reuses v1's numeric data distributions, not its task prompts or
report page/figure recipes. Oracles remain outside model-visible cases.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.research_report_agent_v1.generate_data import CASES as V1_CASES, generate_case


CASES = [
    {"id": "v3_train_materials", "base": "train_materials", "split": "train", "seed": 910017,
     "request": "请分析这份材料拉伸强度实验数据，估计热处理组与对照组的差异及其不确定性，制作一份便于研究组讨论的中文图文PDF。报告组织和篇幅由你根据证据决定，请解释缺失数据及主要限制。"},
    {"id": "v3_train_ml", "base": "train_ml", "split": "train", "seed": 920029,
     "request": "请比较这份两种算法在相同数据划分上的表现，给出准确率的变化及不确定性，形成中文科研PDF。请用适合配对数据的图，篇幅和章节按需要安排，并说明推广到其他数据集时的限制。"},
    {"id": "v3_cert_environment", "base": "cert_environment", "split": "certification", "seed": 930031,
     "request": "请分析温度与水中溶解氧之间的关系，给我一份中文图文PDF，帮助理解趋势、估计误差和模型诊断。请自行决定适合的组织方式与篇幅，不要把相关性写成因果。"},
    {"id": "v3_eval_auto", "base": "eval_biology", "split": "evaluation", "seed": 940007,
     "request": "我想知道营养处理是否改变培养样本的生物量。请读这份数据和研究说明，生成适合组会阅读的中文图文PDF，章节、图型和页数由你根据发现选择，完整解释不确定性和限制。"},
    {"id": "v3_eval_outline", "base": "eval_education", "split": "evaluation", "seed": 950001,
     "request": "请分析同一批学习者训练前后的测验成绩，按照我提供的大纲写中文PDF，总长度最多三页。需要展示每个人的变化，说明估计的不确定性和缺失记录的影响。",
     "outline": "研究问题\n数据与方法\n主要结果及图表\n局限与下一步", "requirements": {"page_mode": "max", "pages": 3}},
    {"id": "v3_eval_brief", "base": "eval_energy", "split": "evaluation", "seed": 960003,
     "request": "请把这份设备负载与能耗的数据整理成恰好一页的中文PDF摘要，给只看核心结果的工程研究员阅读。保留至少一张清晰图、效应及不确定性、主要限制，避免冗长技术细节。",
     "requirements": {"page_mode": "exact", "pages": 1, "style": "brief"}},
    {"id": "v3_eval_technical", "base": "cert_environment", "split": "evaluation", "seed": 970011,
     "request": "请分析这份温度与溶解氧数据，生成中文技术讨论PDF。除图表与统计结果外，请在得到实际结果之后，结合效应方向、不确定性和残差诊断，讨论它对下一轮水质采样设计意味着什么，比较至少两种后续研究选择。讨论必须针对本次结果，明确哪些只是待验证假说；篇幅按需要决定。",
     "requirements": {"page_mode": "auto", "style": "technical"}},
]


def generate(output: Path, seed_offset: int = 0) -> dict:
    selected_cases = CASES
    if type(seed_offset) is not int or any(config["seed"] + seed_offset < 0 for config in selected_cases):
        raise ValueError("seed_offset must be an integer leaving every actual seed nonnegative")
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a fresh output directory; existing synthetic inputs are immutable")
    bases = {row["id"]: row for row in V1_CASES}
    cases = []
    for config in selected_cases:
        base = dict(bases[config["base"]])
        # Generate at the original numeric-design ID, preserving temperature
        # ranges, then move the scoped synthetic files to the v3 case identity.
        scratch = output / "generator-source" / config["id"]
        base["seed"] = config["seed"] + seed_offset
        generate_case(scratch, base)
        source = scratch / "cases" / base["id"]
        target = output / "cases" / config["id"]
        target.mkdir(parents=True, exist_ok=True)
        (target / "data.csv").write_bytes((source / "data.csv").read_bytes())
        study = json.loads((source / "study.json").read_text(encoding="utf-8"))
        study.update(study_id=config["id"], split=config["split"], schema_version="research-report-input-v3",
                     report_requirements={"language": "zh", **config.get("requirements", {})})
        study["user_request"] = config["request"]
        study["semantic_protocol"] = "Decide presentation only after actual statistics; write the full report narrative after reviewing figures. No supplied frozen decisions or body templates."
        task = config["request"]
        if config.get("outline"):
            study["user_outline"] = config["outline"]
            (target / "outline.txt").write_text(config["outline"] + "\n", encoding="utf-8")
            task += "\n\n用户提供的大纲：\n" + config["outline"]
        (target / "study.json").write_text(json.dumps(study, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (target / "task.txt").write_text(task + "\n", encoding="utf-8")
        (target / "request.txt").write_text(config["request"] + "\n", encoding="utf-8")
        oracle = json.loads((scratch / "oracles" / (base["id"] + ".json")).read_text(encoding="utf-8"))
        oracle.update(study_id=config["id"], required_pages=None, required_figures=None)
        oracle["report_constraints"] = config.get("requirements", {})
        (output / "oracles").mkdir(exist_ok=True)
        (output / "oracles" / (config["id"] + ".json")).write_text(json.dumps(oracle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cases.append({"case_id": config["id"], "split": config["split"], "base_seed": config["seed"], "seed": base["seed"],
                      "synthetic": True, "request_file": str(target / "task.txt")})
    manifest = {"generator": "research_report_agent_v3", "synthetic": True, "seed_offset": seed_offset, "cases": cases,
                "dataset_group": "free_semantics_training_and_heldout",
                "note": "Independent numeric seeds; requests contain no tool-chain order or Motif route."}
    (output / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-offset", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(generate(args.output, seed_offset=args.seed_offset), ensure_ascii=False, indent=2))
