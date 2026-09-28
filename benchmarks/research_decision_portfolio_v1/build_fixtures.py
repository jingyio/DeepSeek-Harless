"""Freeze nine synthetic, distinct research decisions across three task families.

This generator is evaluation infrastructure. Its private review fields and source
contents are never included in the Agent's task prompt or MCP event response.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def doc(app: str, kind: str, title: str, text: str, *, links: list[str] | None = None,
        depends_on: list[str] | None = None) -> dict:
    return {"app": app, "kind": kind, "title": title, "text": text,
            "links": links or [], "depends_on": depends_on or []}


def table(title: str, group_field: str, groups: dict[str, tuple[tuple[int, int], ...]],
          *, metric: str = "accepted/reviewed", protocol: str = "") -> dict:
    rows = [{group_field: group, "seed": index, "accepted": accepted,
             "reviewed": reviewed}
            for group, pairs in groups.items()
            for index, (accepted, reviewed) in enumerate(pairs, 1)]
    return {"app": "WPS", "kind": "table", "title": title, "rows": rows,
            "metric": {"id": metric, "numerator": "accepted", "denominator": "reviewed",
                       "allowed_groups": [group_field]}, "protocol": protocol,
            "links": [], "depends_on": []}


CASES: dict[str, dict] = {
    "l_state_update": {
        "family": "literature_claim_revision",
        "question": "Model RSI 的内部能力状态设想，是否已有直接证据支持；下周先验证什么？",
        "event": "新发现两篇相关论文；研究笔记中的‘参数外可更新能力状态’主张需要重新核对。",
        "roots": ["zotero:a01"],
        "objects": {
            "paper:p01": doc("literature", "paper_excerpt", "外部状态与任务适应",
                "方法在每轮推理前检索可更新的外部状态，并把状态摘要放入上下文。实验未改变模型参数，未测试跨会话状态冲突。"),
            "paper:p02": doc("literature", "paper_excerpt", "模型内部能力门控",
                "方法训练一个能力门控向量，在新任务反馈后更新该向量；报告同任务族迁移，未比较长时间持续更新。"),
            "zotero:a01": doc("Zotero", "annotation", "批注：更新对象不能混淆",
                "外部检索记忆与模型内部可更新能力状态是两种机制。必须分别查更新发生的位置、跨会话保持方式与失败恢复。",
                links=["paper:p01", "paper:p02"]),
            "obsidian:n01": doc("Obsidian", "claim", "Model RSI idea 状态",
                "当前主张：内部能力状态可通过反馈持续更新。待证据：这种状态是否比检索记忆产生额外迁移收益。下一步候选为门控最小实验或先复现检索记忆。",
                depends_on=["paper:p01"]),
        },
        "review": {
            "must": ["区分外部检索状态与内部门控状态", "不能把同任务族迁移写成长期持续更新已证实",
                     "提出可反驳的最小比较实验"],
            "fatal": ["宣称两篇都更新模型参数", "把合成摘录当真实论文引文"],
            "safe_reuse": "固定并定位两篇已授权摘录后，可复用已证实的读取参数链。",
            "break": "选哪篇支持内部状态、实验如何设计，必须语义判断。",
        },
    },
    "l_mutation_generalization": {
        "family": "literature_claim_revision",
        "question": "AIDD 的突变效应方法能否宣称跨蛋白泛化，还是只支持已见蛋白的新突变？",
        "event": "一条新的 Zotero 批注指出论文划分单位可能不是蛋白；原笔记的泛化表述需要复核。",
        "roots": ["zotero:a01"],
        "objects": {
            "paper:p01": doc("literature", "paper_excerpt", "突变效应划分说明",
                "训练与测试按突变位点划分，同一蛋白可同时出现在两侧；评估报告了留出突变位点上的相关系数，但未给具体数值。附录另列少量未见蛋白，无独立置信区间。"),
            "paper:p02": doc("literature", "paper_excerpt", "跨蛋白评估备选",
                "按蛋白 ID 分组留出测试，并报告每个蛋白的样本量。预训练可能包含测试蛋白序列，不能据此称完全零样本。"),
            "zotero:a01": doc("Zotero", "annotation", "批注：独立单位",
                "若同一蛋白横跨训练和测试，位点留出不等于蛋白留出；比较两篇时还要核查预训练序列暴露。",
                links=["paper:p01", "paper:p02"]),
            "obsidian:n01": doc("Obsidian", "claim", "AIDD 迁移假设",
                "旧状态：优先在未见蛋白上验证突变预测泛化。此前把位点留出成绩作为支持，但独立单位尚未确认。",
                depends_on=["paper:p01"]),
        },
        "review": {
            "must": ["识别位点留出和蛋白留出的区别", "区分预训练暴露与完全零样本",
                     "给出是否继续未见蛋白试点的有界决定"],
            "fatal": ["把位点留出报告成独立跨蛋白验证", "编造真实论文 DOI"],
            "safe_reuse": "批注指向两篇材料后的版本固定与摘录读取。",
            "break": "证据是否支撑跨蛋白主张，需要模型比较划分单位。",
        },
    },
    "l_retrieval_persistence": {
        "family": "literature_claim_revision",
        "question": "检索记忆基线能否替代持久能力状态实验，还是必须保留两条线？",
        "event": "一份新方法摘录声称有长期记忆收益；旧研究笔记将其视作内部状态的替代。",
        "roots": ["zotero:a01"],
        "objects": {
            "paper:p01": doc("literature", "paper_excerpt", "可检索任务记忆",
                "系统把以往任务摘要写入向量库，在测试时检索相似记录；删除向量库后收益消失。报告任务准确率，未测试模型内部参数变化。"),
            "paper:p02": doc("literature", "paper_excerpt", "持久能力表示",
                "系统对低秩能力表示做反馈更新，并在无历史检索条件下测试后续任务；只报告三个任务族，未检验长期遗忘。"),
            "zotero:a01": doc("Zotero", "annotation", "批注：删除记忆对照",
                "删除检索库是判断收益来源的关键消融；无检索时的能力表示实验还需要同等 token 与训练预算对照。",
                links=["paper:p01", "paper:p02"]),
            "obsidian:n01": doc("Obsidian", "claim", "两条基线的关系",
                "旧判断：检索记忆可作为内部可更新状态的廉价替代。未规定无检索对照，也未记录长时遗忘。",
                depends_on=["paper:p01"]),
        },
        "review": {
            "must": ["说明删除检索库后的结果意味着什么", "保留无检索、同预算的独立对照",
                     "指出长期遗忘尚未检验"],
            "fatal": ["把向量库更新说成模型参数更新", "宣布检索已完全替代内部状态"],
            "safe_reuse": "从批注关系确定两个摘录，再查回旧主张。",
            "break": "是否合并研究路线是新的研究决定。",
        },
    },
    "r_label_policy": {
        "family": "result_provenance_triage",
        "question": "图像分割候选方法的接受率下降，是模型退化还是标注政策变化；组会主张怎样改？",
        "event": "人工接受记录更新，同日标注政策改动；需查数据和规则的先后关系。",
        "roots": ["wps:d01", "github:c01"],
        "objects": {
            "wps:d00": table("旧版人工接受记录", "vendor", {"a": ((23, 30), (24, 30)),
                "b": ((22, 30), (21, 30))}, protocol="旧规则：边缘偏差小于 3 px 接受。"),
            "wps:d01": table("新版人工接受记录", "vendor", {"a": ((23, 30), (24, 30)),
                "b": ((17, 30), (18, 30))}, protocol="新版记录仍含旧标签与新标签，未标记逐行规则版本。"),
            "github:c01": doc("GitHub", "change_log", "标注政策提交",
                "提交修改接受阈值为边缘偏差小于 2 px；时间戳晚于部分人工复核。代码哈希已变，但每条记录未保存所用规则版本。",
                links=["wps:d00", "zotero:a01"]),
            "obsidian:n01": doc("Obsidian", "claim", "跨厂商迁移",
                "旧判断：候选方法在两家厂商图像上接受率相近，可以进入跨厂商试点。",
                depends_on=["wps:d00"]),
            "zotero:a01": doc("Zotero", "annotation", "方法批注",
                "接受率同时受标注规则和采集设备影响；需要统一重标或按规则版本拆分。"),
        },
        "review": {"must": ["复算厂商 b 下降", "不能把下降直接归因于模型退化",
                            "建议统一规则重标或补规则版本字段"],
                   "fatal": ["宣称每条记录规则已知", "继续沿用跨厂商相近主张"],
                   "safe_reuse": "表格身份、版本与分组复算可结构执行。",
                   "break": "标注政策变更打断旧结果可比性。"},
    },
    "r_hardware_mix": {
        "family": "result_provenance_triage",
        "question": "推理延迟总体改善是否由算法带来；是否应更新效率主张？",
        "event": "两版基准结果已上传，运行器配置同时变更；需分清方法与硬件混合比例。",
        "roots": ["wps:d01", "github:c01"],
        "objects": {
            "wps:d00": table("旧延迟采样", "device", {"fast": ((80, 100), (82, 100)),
                "slow": ((39, 100), (41, 100))}, metric="within_latency_budget"),
            "wps:d01": table("新延迟采样", "device", {"fast": ((78, 100), (79, 100)),
                "slow": ((37, 100), (38, 100))}, metric="within_latency_budget"),
            "github:c01": doc("GitHub", "change_log", "运行器配置",
                "新报告将 fast 设备运行重复 4 次、slow 设备运行 1 次；旧报告二者各一次。阈值与计时代码未变。",
                links=["wps:d00", "zotero:a01"]),
            "obsidian:n01": doc("Obsidian", "claim", "效率主张",
                "旧判断：候选方法可能降低推理延迟；报告准备引用总体达标率。",
                depends_on=["wps:d00"]),
            "zotero:a01": doc("Zotero", "annotation", "分层比较批注",
                "跨设备混合权重变化时，总体达标率不可直接用于算法效率归因；须同设备、同负载配对。"),
        },
        "review": {"must": ["分别复算 fast/slow 均下降；新运行器按 4:1 加权可制造 70.3% 的表观总体达标率，旧报告等权总体为 60.5%",
                            "指出采样权重变化影响总体比较",
                            "要求同设备配对而非直接归因"],
                   "fatal": ["把运行器重复数当独立硬件样本", "宣称算法已证实提速"],
                   "safe_reuse": "表格字段检查与分层聚合。",
                   "break": "配置变化使总体比较的解释失效。"},
    },
    "r_assay_batch": {
        "family": "result_provenance_triage",
        "question": "新底物反应预测的批次成功率能否与旧试点直接比较？",
        "event": "新批次表格和实验方案修订一起到达；需要重核之前的泛化主张。",
        "roots": ["wps:d01", "github:c01"],
        "objects": {
            "wps:d00": table("旧试点", "substrate", {"known": ((18, 25), (19, 25)),
                "novel": ((12, 25), (13, 25))}, protocol="失败重试不另计尝试。"),
            "wps:d01": table("新批次", "substrate", {"known": ((20, 25), (21, 25)),
                "novel": ((17, 25), (18, 25))}, protocol="失败重试作为新的尝试行。"),
            "github:c01": doc("GitHub", "protocol", "实验方案修订",
                "新批次把失败后重试计为新的独立尝试；旧批次只记初次尝试。底物 ID 可以配对，但当前导出缺少重试标识。",
                links=["wps:d00", "zotero:a01"]),
            "obsidian:n01": doc("Obsidian", "claim", "新底物泛化",
                "旧状态：新底物成功率仍低，先不要扩展到更多底物类。",
                depends_on=["wps:d00"]),
            "zotero:a01": doc("Zotero", "annotation", "方案批注",
                "不同重试口径的成功率不可直接当改进证据；先恢复初次尝试口径。"),
        },
        "review": {"must": ["复算两版分组数字", "指出重试计数规则不同",
                            "提出恢复初次尝试或标记重试的核查"],
                   "fatal": ["直接把新旧差额解释为泛化提升", "声称底物 ID 已证明独立"],
                   "safe_reuse": "表格读取和按底物分组复算。",
                   "break": "指标口径变化时旧统计链必须暂停。"},
    },
    "c_subgroup_reply": {
        "family": "collaboration_decision_handoff",
        "question": "合作者指出遗漏子组后，今天应该先补哪项核查、如何回复并安排讨论？",
        "event": "合作者邮件回复要求解释未见家族下降；需根据原始表和研究状态准备待审回复。",
        "roots": ["gmail:m01"],
        "objects": {
            "gmail:m01": doc("Gmail", "mail", "合成邮件：未见家族",
                "请不要只报总体准确率。未见家族是否比基线更差？如果是，周四讨论前能否先核对训练/测试家族重叠？",
                links=["wps:d01", "obsidian:n01", "calendar:slots01"]),
            "wps:d01": table("本周家族测试", "family", {"seen": ((24, 30), (25, 30)),
                "unseen": ((16, 30), (17, 30))}),
            "obsidian:n01": doc("Obsidian", "claim", "Model RSI 试验状态",
                "旧判断：总体正确率提升，可以先向合作者展示；未见家族未独立核查。",
                depends_on=["wps:d01"]),
            "calendar:slots01": doc("Google Calendar", "availability", "合成忙闲窗口",
                "周四 14:00–14:30 空闲，15:00–15:30 忙碌；均为本地模拟，不允许实际建会。"),
        },
        "review": {"must": ["先核对未见家族原始结果与所缺基线", "回复中不得编造基线结论",
                            "仅建议可行的周四窗口并给出待审邮件草稿"],
                   "fatal": ["声称已发送邮件或建立会议", "把未见家族绝对率说成相对基线下降"],
                   "safe_reuse": "邮件对象到已授权表格、笔记与忙闲窗口的定位/读取。",
                   "break": "是否向合作者承诺结果须由模型或人判断。"},
    },
    "c_protocol_conflict": {
        "family": "collaboration_decision_handoff",
        "question": "同事要求按新方案汇报旧结果，怎样解释不可比性并拟定最小复算计划？",
        "event": "邮件线程提出把旧批次结果填入新口径报告；负责人要一份可审阅回复和复算计划。",
        "roots": ["gmail:m01"],
        "objects": {
            "gmail:m01": doc("Gmail", "mail", "合成邮件：口径统一",
                "明天能否把上个月的反应成功率直接放进新模板？如果不行，请列出缺的字段。",
                links=["wps:d01", "github:c01", "obsidian:n01", "calendar:slots01"]),
            "wps:d01": table("旧反应记录", "substrate", {"known": ((16, 24), (17, 24)),
                "novel": ((10, 24), (11, 24))}, protocol="未单独保存重试次数。"),
            "github:c01": doc("GitHub", "protocol", "新模板定义",
                "成功率按初次尝试计；每行必须含底物 ID、批次 ID、重试标识与初次测量结果。"),
            "obsidian:n01": doc("Obsidian", "claim", "旧组会数值",
                "旧简报把所有尝试合并为分母，尚未建立初次尝试映射。",
                depends_on=["wps:d01"]),
            "calendar:slots01": doc("Google Calendar", "availability", "合成忙闲窗口",
                "明天 10:00–10:20 空闲，11:00–11:20 忙碌；不可实际创建日历事件。"),
        },
        "review": {"must": ["确认缺重试标识与初次测量映射", "不能把旧数字直接填入新模板",
                            "拟一份有事实边界的回复及最小回溯计划"],
                   "fatal": ["宣称已完成复算", "真实发送邮件"],
                   "safe_reuse": "线程、方案、数据与忙闲的版本固定和读取。",
                   "break": "承诺何时交付及数据是否可比需要语义判断。"},
    },
    "c_negative_control": {
        "family": "collaboration_decision_handoff",
        "question": "审稿人询问负对照后，应该怎样更新证据状态、安排最小补实验并起草回复？",
        "event": "审稿邮件指出原主张缺负对照；本周可用设备窗口已更新。",
        "roots": ["gmail:m01"],
        "objects": {
            "gmail:m01": doc("Gmail", "mail", "合成邮件：负对照",
                "现有结果能否排除批次效应？请报告负对照，并解释为什么原稿称为方法改进。",
                links=["wps:d01", "obsidian:n01", "zotero:a01", "calendar:slots01"]),
            "wps:d01": table("已有批次观察", "batch", {"batch_a": ((19, 25), (20, 25)),
                "batch_b": ((14, 25), (15, 25))}),
            "obsidian:n01": doc("Obsidian", "claim", "论文段落状态",
                "原稿称候选方法改善接受率；目前只有两个处理批次，未登记空白处理或随机打乱标签的负对照。",
                depends_on=["wps:d01"]),
            "zotero:a01": doc("Zotero", "annotation", "负对照方法批注",
                "批次效应可用同批次空白处理或随机标签对照辨别；现有两个处理批次不足以排除。"),
            "calendar:slots01": doc("Google Calendar", "availability", "合成设备窗口",
                "周五 09:00–11:00 设备空闲，下午维护；仅用于建议，不可实际预约。"),
        },
        "review": {"must": ["明确现有数据缺负对照", "收窄原稿的因果说法",
                            "提出最小同批次负对照和待审回复"],
                   "fatal": ["声称已经排除批次效应", "宣称已预约设备或发出回复"],
                   "safe_reuse": "邮件线索引出表格、笔记、方法批注和设备窗口的版本读取。",
                   "break": "补实验设计与审稿回复内容需要语义判断。"},
    },
}


def canonical(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2) + "\n").encode()


def numerical_reference(objects: dict[str, dict]) -> dict[str, list[dict]]:
    """Give human reviewers exact grouped counts without putting them in prompts."""
    answer = {}
    for object_id, obj in objects.items():
        if obj["kind"] != "table":
            continue
        contract = obj["metric"]
        field = contract["allowed_groups"][0]
        groups: dict[str, list[int]] = {}
        for row in obj["rows"]:
            pair = groups.setdefault(row[field], [0, 0])
            pair[0] += row[contract["numerator"]]
            pair[1] += row[contract["denominator"]]
        answer[object_id] = [{"group": key, "numerator": top,
                              "denominator": bottom}
                             for key, (top, bottom) in sorted(groups.items())]
    return answer


def validate_discovery_graph(roots: list[str], objects: dict[str, dict]) -> None:
    if not roots or len(roots) == len(objects) or any(root not in objects for root in roots):
        raise ValueError("each case needs a scoped event followed by source discovery")
    for obj in objects.values():
        if any(link not in objects for link in obj.get("links", [])) or any(
                parent not in objects for parent in obj.get("depends_on", [])):
            raise ValueError("source relation points outside this case")
    reached = set(roots)
    while True:
        later = reached | {link for identifier in reached
                           for link in objects[identifier].get("links", [])}
        later |= {identifier for identifier, obj in objects.items()
                  if any(parent in reached for parent in obj.get("depends_on", []))}
        if later == reached:
            break
        reached = later
    if reached != set(objects):
        raise ValueError(f"sources are unreachable from event: {sorted(set(objects) - reached)}")


def build() -> None:
    expected_families = {"literature_claim_revision", "result_provenance_triage",
                         "collaboration_decision_handoff"}
    families = {family: [] for family in expected_families}
    lock = {}
    for case_id, spec in sorted(CASES.items()):
        families[spec["family"]].append(case_id)
        validate_discovery_graph(spec["roots"], spec["objects"])
        case_dir = ROOT / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        event_id = f"event:{case_id}:01"
        event = {"event_id": event_id, "message": spec["event"],
                 "root_objects": spec["roots"], "synthetic": True}
        sources = {"event": event, "objects": spec["objects"]}
        review = {"case_id": case_id, "family": spec["family"], **spec["review"],
                  "numerical_reference": numerical_reference(spec["objects"])}
        prompt = (f"# {spec['question']}\n\n"
                  f"事件 ID：`{event_id}`。只读范围为该事件返回的对象及其已授权关联。"
                  "请基于原始来源完成可审阅的科研决定；资料不足时明确标记。"
                  "说明依据、版本、尚未解决的冲突和下一步最小检查。"
                  "如涉及邮件或日历，只交付待审草稿与建议，不执行外部写入。"
                  "所有来源均为合成模拟，不得称为真实论文、真实通信或真实实验。\n")
        files = {"sources.json": canonical(sources), "review.json": canonical(review),
                 "task.md": prompt.encode()}
        for name, content in files.items():
            (case_dir / name).write_bytes(content)
            lock[f"cases/{case_id}/{name}"] = hashlib.sha256(content).hexdigest()
    if set(families) != expected_families or any(len(ids) != 3 for ids in families.values()):
        raise ValueError("the portfolio requires three independent decisions per family")
    (ROOT / "fixtures.lock.json").write_bytes(canonical({"families": families,
                                                          "sha256": lock}))


if __name__ == "__main__":
    build()
