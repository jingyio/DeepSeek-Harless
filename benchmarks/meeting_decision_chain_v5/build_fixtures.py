"""Build four-seed held-out research decisions for quality-and-cost evaluation."""

from __future__ import annotations

from pathlib import Path

from benchmarks.meeting_decision_chain_v3.build_fixtures import build_cases


ROOT = Path(__file__).resolve().parent


def grid(denominator: int, blocks: dict[tuple[str, str], tuple[int, ...]]) -> list[tuple]:
    return [(variant, group, seed, denominator, value)
            for (variant, group), values in blocks.items()
            for seed, value in enumerate(values, start=1)]


CASES = {
    "microscopy_vendor": {
        "title": "细胞分割方法能否迁移到另一显微镜厂商",
        "metric": {"id": "segmentation_acceptance", "numerator": "accepted_masks",
                   "denominator": "reviewed_masks", "allowed_groups": ["variant", "microscope"]},
        "rows": grid(30, {
            ("baseline", "vendor_a"): (22, 21, 23, 22),
            ("baseline", "vendor_b"): (19, 18, 20, 19),
            ("candidate", "vendor_a"): (26, 25, 27, 26),
            ("candidate", "vendor_b"): (17, 16, 18, 17),
        }),
        "prior_adjustment": {("candidate", "vendor_b"): 5},
        "note": {
            "claim_id": "claim:microscopy_vendor:transfer",
            "text": "旧判断：候选分割方法在厂商 A 图像上提升人工接受率，"
                    "或可迁移到厂商 B。须分别报告厂商与人工复核口径。",
            "decision_options": ["暂停跨厂商主张", "核对人工复核规则", "直接合并两厂商结果"],
        },
        "annotation": {
            "title": "合成方法批注：跨显微镜迁移",
            "text": "人工接受率会受标注规则与图像采集协议影响；"
                    "仅凭接受率不足以判定算法失效的原因。",
        },
        "event": {"changed_fields": ["accepted_masks"],
                  "message": "厂商 B 的分割接受数修订，请复核迁移主张。"},
    },
    "chemistry_substrate": {
        "title": "反应预测器能否推广到新底物类",
        "metric": {"id": "reaction_success_rate", "numerator": "successful_reactions",
                   "denominator": "attempted_reactions", "allowed_groups": ["variant", "substrate"]},
        "rows": grid(36, {
            ("baseline", "known"): (24, 23, 25, 24),
            ("baseline", "new"): (18, 17, 19, 18),
            ("candidate", "known"): (29, 28, 30, 29),
            ("candidate", "new"): (23, 22, 24, 23),
        }),
        "prior_adjustment": {("candidate", "new"): -7},
        "note": {
            "claim_id": "claim:chemistry_substrate:generalization",
            "text": "旧判断：候选反应预测器对已见底物有效，"
                    "对新底物类尚缺独立证据，不能用总体成功率替代新类结果。",
            "decision_options": ["补独立新底物", "限定新底物初步信号", "宣称普遍泛化"],
        },
        "annotation": {
            "title": "合成方法批注：新底物泛化",
            "text": "同一骨架的多个反应不是独立底物类别；"
                    "成功率不说明失败的化学机理。",
        },
        "event": {"changed_fields": ["successful_reactions"],
                  "message": "新底物类的反应成功数更新，请复核泛化判断。"},
    },
    "materials_scaleup": {
        "title": "材料合成策略在放大批次能否维持收益",
        "metric": {"id": "synthesis_yield", "numerator": "successful_batches",
                   "denominator": "scheduled_batches", "allowed_groups": ["variant", "batch_scale"]},
        "rows": grid(32, {
            ("baseline", "pilot"): (23, 22, 24, 23),
            ("baseline", "scaleup"): (19, 18, 20, 19),
            ("candidate", "pilot"): (27, 26, 28, 27),
            ("candidate", "scaleup"): (18, 17, 19, 18),
        }),
        "prior_adjustment": {("candidate", "scaleup"): 6},
        "note": {
            "claim_id": "claim:materials_scaleup:transfer",
            "text": "旧判断：候选合成策略在小试批次成功率较高，"
                    "可能延伸到放大批次；放大时需另记设备和人工调整。",
            "decision_options": ["先查放大批次日志", "增加放大重复实验", "沿用总体收益"],
        },
        "annotation": {
            "title": "合成方法批注：放大批次",
            "text": "放大成功率可能包含人工调整；仅有成功批次数不能区分"
                    "设备、原料和策略因素。",
        },
        "event": {"changed_fields": ["successful_batches"],
                  "message": "放大批次的成功数修订，请重新判断策略迁移。"},
    },
}


def build() -> None:
    build_cases(ROOT, CASES)


if __name__ == "__main__":
    build()
