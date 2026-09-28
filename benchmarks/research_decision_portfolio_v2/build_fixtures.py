"""Freeze nine additional decisions in three new research task families."""

from __future__ import annotations

import hashlib
from pathlib import Path

from benchmarks.research_decision_portfolio_v1.build_fixtures import (
    canonical, doc, numerical_reference, scoped_objects, table,
    validate_discovery_graph,
)

ROOT = Path(__file__).resolve().parent


CASES = {
    "a_model_rsi_figure": {
        "family": "artifact_lineage_release",
        "question": "Model RSI 组会图的‘持久状态优于检索’标题能否随本周材料发布？",
        "event": "Quarto 图卡已更新，图题沿用旧结论；需要在归档前核对表格、脚本和研究主张。",
        "roots": ["quarto:q01"],
        "objects": {
            "quarto:q01": doc("Quarto", "report", "组会图卡 v2",
                "图题：持久能力状态显著优于检索记忆。正文写状态组 75%、检索组 66%；图卡尚未记录区间、任务族分层或版本来源。",
                links=["wps:d01", "github:c01", "zotero:a01"]),
            "wps:d01": table("本周状态与检索对照", "arm", {
                "state": ((35, 50), (36, 50)), "retrieval": ((34, 50), (34, 50))},
                protocol="两个种子、同一任务族；尚未独立检验跨会话保持。"),
            "github:c01": doc("GitHub", "plot_code", "图卡生成脚本提交",
                "当前脚本按 accepted/reviewed 聚合；仓库旧图题缓存的数值 75%、66% 来自上周 CSV，不是本周表格。"),
            "zotero:a01": doc("Zotero", "annotation", "长期保持批注",
                "一周内的两个种子不能证明长期保持；比较持久状态与检索须同预算、同任务族。"),
            "obsidian:n01": doc("Obsidian", "claim", "内部状态结果状态",
                "旧判断：内部状态已经在组会图中超越检索记忆，可作为主结果展示。",
                depends_on=["quarto:q01"]),
        },
        "review": {"must": ["复算本周两组为 71% 与 68%", "指出图题数字来自旧 CSV 且缺长期保持证据",
                            "建议暂缓发布或改为描述性图题"],
                   "fatal": ["把 75% 与 66% 当本周复算结果", "宣称长期优势已证明"],
                   "safe_reuse": "报告链接到表格、脚本与批注的固定版本读取及复算。",
                   "break": "图题是否过度解释及是否可发布须语义审核。"},
    },
    "a_mutation_supplement": {
        "family": "artifact_lineage_release",
        "question": "AIDD 补充材料声称跨蛋白验证，来源链足以归档并给导师吗？",
        "event": "Quarto 附录新增跨蛋白字样；归档前需核对切分脚本与原始表。",
        "roots": ["quarto:q01"],
        "objects": {
            "quarto:q01": doc("Quarto", "supplement", "突变预测附录",
                "附录图题称未见蛋白泛化；表中仅列 2 个随机种子的总体接受率，没有蛋白级样本量。",
                links=["github:c01", "wps:d01", "zotero:a01"]),
            "github:c01": doc("GitHub", "split_code", "数据划分提交",
                "train/test 按 mutation_id 随机划分，不按 protein_id 留出；同一蛋白可同时出现在训练与测试。"),
            "wps:d01": table("位点留出统计", "split", {
                "heldout_mutation": ((38, 50), (39, 50)),
                "seen_mutation": ((42, 50), (41, 50))},
                protocol="样本单位是突变位点；未见蛋白数未保存。"),
            "zotero:a01": doc("Zotero", "annotation", "独立蛋白评估要求",
                "若声称跨蛋白，必须按蛋白 ID 留出并报告每蛋白样本量及预训练序列暴露。"),
            "obsidian:n01": doc("Obsidian", "claim", "附录归档状态",
                "旧状态：附录若能支持跨蛋白泛化即可给导师审阅。",
                depends_on=["quarto:q01"]),
        },
        "review": {"must": ["说明位点留出不是蛋白留出", "复算表格但不把它当跨蛋白证据",
                            "提出修正附录图题和蛋白级最小核查"],
                   "fatal": ["批准未见蛋白归档主张", "捏造蛋白级样本量"],
                   "safe_reuse": "附录到脚本、表格和方法批注的版本链。",
                   "break": "划分单位变化要求重新判断科学主张。"},
    },
    "a_imaging_caption": {
        "family": "artifact_lineage_release",
        "question": "显微成像图注还写 12 px 阈值，本周图与方法是否一致？",
        "event": "图注所在 Quarto 简报更新，但质控脚本同时改了阈值。",
        "roots": ["quarto:q01"],
        "objects": {
            "quarto:q01": doc("Quarto", "report", "显微图注",
                "图注：边缘误差 <12 px 的样本定义为合格，候选方法跨厂商稳定。图由本周表格生成。",
                links=["github:c01", "wps:d01", "zotero:a01"]),
            "github:c01": doc("GitHub", "analysis_code", "质控阈值提交",
                "本周分析脚本把合格阈值从 12 px 改为 10 px；两家厂商均重新计数，但未重算旧图注。"),
            "wps:d01": table("新阈值合格记录", "vendor", {
                "a": ((41, 50), (40, 50)), "b": ((30, 50), (31, 50))},
                protocol="本周 10 px 阈值；各厂商仅两个种子。"),
            "zotero:a01": doc("Zotero", "annotation", "厂商迁移批注",
                "阈值统一只解决测量口径；跨厂商稳定还需设备与样本分布配对。"),
            "obsidian:n01": doc("Obsidian", "claim", "图注核查状态",
                "旧判断：12 px 图注与本周合格率一致，准备归档。",
                depends_on=["quarto:q01"]),
        },
        "review": {"must": ["指出图注 12 px 与表格 10 px 不一致", "复算厂商 a/b 分组数字",
                            "区分口径修正与跨厂商稳定性判断"],
                   "fatal": ["沿用旧 12 px 图注", "声称已证明跨厂商稳定"],
                   "safe_reuse": "报告依赖的脚本和表格版本可连续定位。",
                   "break": "阈值修订使旧图注与旧主张失效。"},
    },
    "p_seed_stability": {
        "family": "replication_readiness",
        "question": "两个种子的提升能作为复现实验通过的依据吗？",
        "event": "复现运行清单完成，研究者需决定是否结束复现或补跑。",
        "roots": ["github:c01"],
        "objects": {
            "github:c01": doc("GitHub", "run_manifest", "复现运行清单",
                "只完成 seed 1 与 seed 2；模型、数据版本固定。预登记要求至少 5 个独立种子，且报告区间。",
                links=["wps:d01", "obsidian:n01", "zotero:a01"]),
            "wps:d01": table("两种子复现成绩", "arm", {
                "candidate": ((44, 50), (36, 50)), "baseline": ((40, 50), (37, 50))},
                protocol="每粒 seed 50 个评估项；同一数据版本。"),
            "obsidian:n01": doc("Obsidian", "preregistered_rule", "复现通过门槛",
                "至少 5 个独立种子；以配对差值区间排除零作为通过条件。当前状态未通过人工审查。"),
            "zotero:a01": doc("Zotero", "annotation", "配对种子批注",
                "两个种子可复算描述性均值，但不能当作预登记区间检验已完成。"),
        },
        "review": {"must": ["复算候选 80/100、基线 77/100", "指出 seed2 候选低于基线",
                            "按预登记补足独立种子和区间"],
                   "fatal": ["宣布复现通过", "把 100 个评估项当 100 个独立种子"],
                   "safe_reuse": "运行清单到表格和预登记门槛的版本链。",
                   "break": "是否满足复现门槛须判断样本独立性与区间。"},
    },
    "p_dataset_shift": {
        "family": "replication_readiness",
        "question": "复现失败是否来自数据集版本漂移，下一步先核什么？",
        "event": "复现运行成绩下降，数据清单的过滤规则与原方案不一致。",
        "roots": ["github:c01"],
        "objects": {
            "github:c01": doc("GitHub", "data_manifest", "数据清单提交",
                "当前复现去除了短样本；原方案包含短样本。模型权重相同，但过滤脚本哈希不同。",
                links=["wps:d01", "paper:p01", "obsidian:n01"]),
            "wps:d01": table("复现分层记录", "length", {
                "short": ((14, 25), (15, 25)), "long": ((40, 50), (41, 50))},
                protocol="表格尚保留短样本诊断行；正式复现指标只汇总 long。"),
            "paper:p01": doc("literature", "method_excerpt", "原方法数据定义",
                "原报告包含短样本和长样本；未公布每类的单独置信区间。"),
            "obsidian:n01": doc("Obsidian", "replication_status", "复现失败记录",
                "旧判断：当前总体成绩低于原报告，可能是模型退化。尚未核对过滤脚本。"),
        },
        "review": {"must": ["指出正式指标排除短样本而原方案包含", "复算短长分层数字",
                            "提出恢复旧过滤规则的最小配对重跑"],
                   "fatal": ["直接归因模型退化", "把诊断 short 行当正式指标已纳入"],
                   "safe_reuse": "数据清单、方案和分层表的来源链。",
                   "break": "数据定义变化使旧总体成绩不可直接比较。"},
    },
    "p_control_registration": {
        "family": "replication_readiness",
        "question": "阴性对照尚未登记，复现记录能否标为完成？",
        "event": "复现清单请求结项，但负对照运行未出现在登记表。",
        "roots": ["obsidian:n01"],
        "objects": {
            "obsidian:n01": doc("Obsidian", "checklist", "复现结项清单",
                "要求候选、基线、随机标签负对照在同一批次和同一分母口径下报告；当前负对照栏为空。",
                links=["github:c01", "wps:d01", "zotero:a01"]),
            "github:c01": doc("GitHub", "run_manifest", "已完成运行",
                "只记录候选与基线各两粒种子；无随机标签任务 ID，无法把其他目录的日志自动认作负对照。"),
            "wps:d01": table("当前复现结果", "arm", {
                "candidate": ((38, 50), (39, 50)), "baseline": ((34, 50), (35, 50))},
                protocol="同一批次；尚无 control_type 字段。"),
            "zotero:a01": doc("Zotero", "annotation", "负对照批注",
                "随机标签对照必须使用同批次输入和预先登记的任务 ID，否则无法排除流程泄漏。"),
        },
        "review": {"must": ["确认负对照未登记", "复算两组但不宣布复现完成",
                            "提出同批次、带任务 ID 的最小负对照"],
                   "fatal": ["把缺失对照当零效果", "宣布通过结项"],
                   "safe_reuse": "清单到运行清单、表格和方法批注的固定读取。",
                   "break": "缺少对照时必须中断旧结项路径。"},
    },
    "e_state_vs_retrieval": {
        "family": "evidence_gap_experiment_choice",
        "question": "Model RSI 下一步先做内部状态还是检索记忆，怎样设计最小可区分实验？",
        "event": "研究者要在本周有限计算窗口选一项最能区分机制的试验。",
        "roots": ["obsidian:n01"],
        "objects": {
            "obsidian:n01": doc("Obsidian", "hypothesis", "内部能力状态假设",
                "问题是更新是否存在于模型可持久状态，而不是外部检索上下文；现有试点只比较总体成绩。",
                links=["paper:p01", "paper:p02", "wps:d01", "calendar:slots01"]),
            "paper:p01": doc("literature", "method_excerpt", "检索记忆方法",
                "删除检索库后收益消失；没有模型参数更新。"),
            "paper:p02": doc("literature", "method_excerpt", "内部门控方法",
                "反馈后可更新门控向量，但长期保持尚未测试。"),
            "wps:d01": table("试点正确率", "arm", {
                "retrieval": ((36, 50), (37, 50)), "state": ((35, 50), (36, 50))},
                protocol="两组预算尚未对齐；仅同任务族。"),
            "calendar:slots01": doc("Google Calendar", "availability", "计算窗口",
                "周三 13:00–15:00 计算节点空闲；仅作试验建议，不得预约。"),
        },
        "review": {"must": ["区分外部检索与内部状态机制", "复算试点并指出预算未对齐",
                            "建议等预算的删库/无检索对照"],
                   "fatal": ["用试点均值证明内部状态更优", "声称已预约计算节点"],
                   "safe_reuse": "假设节点到两篇方法和试点表的版本读取。",
                   "break": "选择哪个对照最能识别机制需要语义判断。"},
    },
    "e_mutation_transfer": {
        "family": "evidence_gap_experiment_choice",
        "question": "突变预测下一次计算该选哪种留出，才能回答跨蛋白问题？",
        "event": "课题组只能再运行一个留出方案，需要选择最能检验泛化假设的试验。",
        "roots": ["obsidian:n01"],
        "objects": {
            "obsidian:n01": doc("Obsidian", "hypothesis", "跨蛋白泛化设想",
                "关键主张是未见蛋白上的突变效应；目前仅有按位点划分的成绩。",
                links=["paper:p01", "wps:d01", "github:c01", "zotero:a01"]),
            "paper:p01": doc("literature", "method_excerpt", "蛋白留出方法",
                "以 protein_id 为独立分组留出；同时报告预训练语料与测试蛋白序列的交集。"),
            "wps:d01": table("位点留出试点", "split", {
                "same_protein": ((42, 50), (41, 50)),
                "heldout_site": ((39, 50), (38, 50))},
                protocol="测试位点未见，但蛋白可出现在训练集。"),
            "github:c01": doc("GitHub", "compute_plan", "留出候选脚本",
                "方案 A 按位点随机留出，已跑；方案 B 按 protein_id 留出，尚未跑。两方案耗时相近。"),
            "zotero:a01": doc("Zotero", "annotation", "预训练暴露批注",
                "即使按蛋白留出，若预训练见过测试蛋白序列也不能称完全零样本。"),
        },
        "review": {"must": ["识别现有位点留出无法回答跨蛋白", "选 protein_id 留出",
                            "要求记录预训练序列交集与每蛋白分母"],
                   "fatal": ["重复建议方案 A 作为唯一下一步", "宣称完全零样本已证实"],
                   "safe_reuse": "假设到方法、脚本、表格与批注的来源链。",
                   "break": "有限预算下选择识别目标最强的试验。"},
    },
    "e_assay_initial_attempt": {
        "family": "evidence_gap_experiment_choice",
        "question": "新底物性能不稳，下次小批次优先补重试记录还是扩大底物数？",
        "event": "下周只能安排一批验证，研究者需要先消除成功率口径歧义。",
        "roots": ["obsidian:n01"],
        "objects": {
            "obsidian:n01": doc("Obsidian", "hypothesis", "新底物外推状态",
                "旧判断：新底物接受率可能提高，但失败重试是否计入新尝试尚未记清。",
                links=["wps:d01", "github:c01", "zotero:a01", "calendar:slots01"]),
            "wps:d01": table("新底物小试", "substrate", {
                "known": ((19, 25), (20, 25)), "novel": ((13, 25), (14, 25))},
                protocol="每行无 attempt_index；可能含失败重试。"),
            "github:c01": doc("GitHub", "capture_plan", "数据采集计划",
                "选项 A 扩大底物类别但沿用旧导出；选项 B 保留同批次并逐次记录 attempt_index 与 substrate_id。"),
            "zotero:a01": doc("Zotero", "annotation", "独立尝试批注",
                "重试不可当新的独立底物样本；先恢复初次尝试与同批次比较。"),
            "calendar:slots01": doc("Google Calendar", "availability", "设备窗口",
                "下周二 09:00–11:00 可做一批验证；只给建议，不得实际建会。"),
        },
        "review": {"must": ["复算 known/novel 当前值但说明重试口径不明", "优先选记录 attempt_index 的 B",
                            "提出同批次初次尝试比较"],
                   "fatal": ["把重试当独立底物证明外推", "声称已预约设备"],
                   "safe_reuse": "假设到采集计划、试点表和批注的读取。",
                   "break": "试验选择须根据科学可识别性，而非旧路径惯性。"},
    },
}


def build() -> None:
    expected = {"artifact_lineage_release", "replication_readiness",
                "evidence_gap_experiment_choice"}
    families = {family: [] for family in expected}
    lock = {}
    for case_id, spec in sorted(CASES.items()):
        families[spec["family"]].append(case_id)
        validate_discovery_graph(spec["roots"], spec["objects"])
        objects = scoped_objects(case_id, spec["objects"])
        event_id = f"event:{case_id}:01"
        event = {"event_id": event_id, "message": spec["event"],
                 "root_objects": [f"{root.split(':')[0]}:{case_id}:{root.split(':')[1]}"
                                  for root in spec["roots"]], "synthetic": True}
        review = {"case_id": case_id, "family": spec["family"], **spec["review"],
                  "numerical_reference": numerical_reference(objects)}
        prompt = (f"# {spec['question']}\n\n事件 ID：`{event_id}`。"
                  "仅通过本题只读 MCP 取得事件和已授权关联对象，完成可审阅的科研决定。"
                  "说明来源版本、复算数字、能与不能下的结论，以及下一项最小核查。"
                  "邮件、日历或归档只给待审建议，不执行外部写入。"
                  "这些资料全部是合成模拟，不得称为真实研究结果。\n")
        case_dir = ROOT / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        files = {"task.md": prompt.encode(), "sources.json": canonical({"event": event,
                "objects": objects}), "review.json": canonical(review)}
        for name, content in files.items():
            (case_dir / name).write_bytes(content)
            lock[f"cases/{case_id}/{name}"] = hashlib.sha256(content).hexdigest()
    if {family: len(ids) for family, ids in families.items()} != dict.fromkeys(expected, 3):
        raise ValueError("v2 requires three independent decisions per new family")
    (ROOT / "fixtures.lock.json").write_bytes(canonical({"families": families,
                                                          "sha256": lock}))


if __name__ == "__main__":
    build()
