"""Build a second unseen set for prospective cross-object Motif evaluation."""

from __future__ import annotations

from pathlib import Path

from benchmarks.meeting_decision_chain_v3.build_fixtures import build_cases


ROOT = Path(__file__).resolve().parent
CASES = {
    "battery_cold": {
        "title": "电池寿命预测能否迁移到低温批次",
        "metric": {"id": "cycle_prediction_rate", "numerator": "valid_predictions",
                   "denominator": "tested_cells", "allowed_groups": ["variant", "temperature"]},
        "rows": [
            ("baseline", "room", 1, 40, 31), ("baseline", "room", 2, 40, 30),
            ("baseline", "room", 3, 40, 32), ("baseline", "cold", 1, 40, 23),
            ("baseline", "cold", 2, 40, 22), ("baseline", "cold", 3, 40, 24),
            ("candidate", "room", 1, 40, 36), ("candidate", "room", 2, 40, 35),
            ("candidate", "room", 3, 40, 37), ("candidate", "cold", 1, 40, 20),
            ("candidate", "cold", 2, 40, 19), ("candidate", "cold", 3, 40, 21),
        ],
        "prior_adjustment": {("candidate", "cold"): 8},
        "note": {
            "claim_id": "claim:battery_cold:transfer",
            "text": "旧判断：候选预测器在室温电池上表现更好，或可用于低温批次。"
                    "低温结果须分开报告，且不能把循环次数当独立电芯数。",
            "decision_options": ["暂停低温迁移表述", "核查低温测量口径", "直接沿用总体增益"],
        },
        "annotation": {
            "title": "合成方法批注：电池批次",
            "text": "室温和低温批次的电芯来源、循环终止条件可能不同；"
                    "单靠正确率变化无法确定老化机理。",
        },
        "event": {"changed_fields": ["valid_predictions"],
                  "message": "低温批次预测核验数修订，请复核跨温度结论。"},
    },
    "corpus_shift": {
        "title": "新兴领域论文检索是否获得可迁移收益",
        "metric": {"id": "screening_recall", "numerator": "relevant_found",
                   "denominator": "relevant_total", "allowed_groups": ["variant", "field_group"]},
        "rows": [
            ("baseline", "established", 1, 45, 31),
            ("baseline", "established", 2, 45, 30),
            ("baseline", "established", 3, 45, 32),
            ("baseline", "emerging", 1, 45, 21),
            ("baseline", "emerging", 2, 45, 20),
            ("baseline", "emerging", 3, 45, 22),
            ("candidate", "established", 1, 45, 37),
            ("candidate", "established", 2, 45, 36),
            ("candidate", "established", 3, 45, 38),
            ("candidate", "emerging", 1, 45, 26),
            ("candidate", "emerging", 2, 45, 25),
            ("candidate", "emerging", 3, 45, 27),
        ],
        "prior_adjustment": {("candidate", "emerging"): -7},
        "note": {
            "claim_id": "claim:corpus_shift:recall",
            "text": "旧判断：新检索器在成熟领域找回更多相关论文；"
                    "新兴领域证据不足，不能用总体召回率替代分领域结果。",
            "decision_options": ["补独立的新兴领域主题", "有限收窄旧主张", "宣称所有领域都受益"],
        },
        "annotation": {
            "title": "合成方法批注：新兴领域文献检索",
            "text": "同一主题的多篇论文不等于独立研究领域；"
                    "主题划分和相关性标注版本需固定后才能比较召回率。",
        },
        "event": {"changed_fields": ["relevant_found"],
                  "message": "新兴领域筛选结果已更新，请复核检索器迁移主张。"},
    },
    "remote_assay": {
        "title": "远程自动化测定的成功率能否支持自主运行",
        "metric": {"id": "assay_success_rate", "numerator": "successful_assays",
                   "denominator": "scheduled_assays", "allowed_groups": ["variant", "site_type"]},
        "rows": [
            ("baseline", "local", 1, 38, 28), ("baseline", "local", 2, 38, 27),
            ("baseline", "local", 3, 38, 29), ("baseline", "remote", 1, 38, 24),
            ("baseline", "remote", 2, 38, 23), ("baseline", "remote", 3, 38, 25),
            ("candidate", "local", 1, 38, 33), ("candidate", "local", 2, 38, 32),
            ("candidate", "local", 3, 38, 34), ("candidate", "remote", 1, 38, 27),
            ("candidate", "remote", 2, 38, 26), ("candidate", "remote", 3, 38, 28),
        ],
        "prior_adjustment": {("candidate", "remote"): 5},
        "note": {
            "claim_id": "claim:remote_assay:autonomy",
            "text": "旧判断：自动化测定在本地成功率较高，远程场地亦可能稳定。"
                    "需要区分无人值守完成与人工远程救援。",
            "decision_options": ["先取人工救援日志", "补远程场地重复实验", "宣称远程自主运行可靠"],
        },
        "annotation": {
            "title": "合成方法批注：远程自动化",
            "text": "成功率可能包含人工远程救援，不能直接解释为自主完成率；"
                    "场地网络和仪器状态也需记录。",
        },
        "event": {"changed_fields": ["successful_assays"],
                  "message": "远程场地测定成功数被修订，请复核自主运行主张。"},
    },
}


def build() -> None:
    build_cases(ROOT, CASES)


if __name__ == "__main__":
    build()
