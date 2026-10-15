"""Meaningful artifact/decision-boundary checks; no model calls are made."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import data_tools
import generate_data
import report_ops


def approved_plan(case):
    plan = {"design": case["design"], "outcome_column": "value", "missing_policy": "complete_case",
            "confidence": 0.95, "hypothesis": "估计实际观测中的比较效应并报告不确定性。",
            "allow_deterministic_continuation": True}
    if case["design"] == "regression":
        plan["predictor_column"] = "predictor"
    elif case["design"] == "paired":
        plan.update(group_column="condition", subject_column="subject", reference_group="before", comparison_group="after")
    else:
        plan.update(group_column="group", reference_group="control", comparison_group="treatment")
    return plan


def narrative(case):
    return {"title": case["title"], "summary": "本报告分析合成实验数据，纳入有效观测或配对数为{{n}}。结果用于验证分析工具和报告流程。",
            "methods": "依据数据的独立或配对结构选择统计方法。显式采用完整案例策略，删除记录数为{{excluded_rows}}；未插补未知值。",
            "findings": "主要效应估计为{{estimate}}，置信区间为[{{ci_low}}, {{ci_high}}]，检验p值为{{p_value}}。应结合原始数据图和不确定性解释，不能仅凭显著性判断实用价值。",
            "limitations": "数据由脚本合成，不支持真实学科结论。缺失机制和独立性需要设计层面验证；相关关系不构成因果证明。",
            "next_steps": "在真实实验中预先确定主要结局，核对采样单位与测量流程；保留原始数据并进行领域专家复核。",
            "allow_deterministic_continuation": True}


class ReportToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        generate_data.generate(self.root / "inputs")
        self.environment = patch.dict(os.environ, {"RRA_DATA_ROOT": str(self.root / "inputs"),
                                                   "RRA_RUN_ROOT": str(self.root / "run"), "RRA_CASE": "train_materials"})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def analysis(self, case):
        os.environ["RRA_CASE"] = case["id"]
        os.environ["RRA_RUN_ROOT"] = str(self.root / case["id"])
        planned = data_tools.plan_analysis(case["id"], approved_plan(case))
        return data_tools.run_analysis(planned["plan_id"])["analysis_id"]

    def test_reject_incompatible_plots_and_unlinked_quantitative_claims(self):
        case = generate_data.CASES[0]
        analysis_id = self.analysis(case)
        with self.assertRaisesRegex(ValueError, "Choose distinct"):
            report_ops.plan_figures(analysis_id, {"figures": [{"kind": "scatter_fit"}, {"kind": "residuals"}]})
        metrics = common.get_record(analysis_id)["payload"]["metrics_dict"]
        text = narrative(case)
        text["findings"] += "效应达到999。"
        with self.assertRaisesRegex(ValueError, "Unlinked number"):
            report_ops._render_narrative(text, metrics)

    def test_default_authorization_is_closed(self):
        case = generate_data.CASES[0]
        analysis_id = self.analysis(case)
        response = report_ops.plan_figures(analysis_id, {"figures": [{"kind": "distribution_ci"}, {"kind": "effect_interval"}]})
        self.assertEqual(response["_provenance"]["authorized_tools"], [])

    def test_reject_single_brace_and_report_actual_illegal_number(self):
        case = generate_data.CASES[0]
        analysis_id = self.analysis(case)
        metrics = common.get_record(analysis_id)["payload"]["metrics_dict"]
        for invalid in ("{input_rows}", "{{input_rows}", "{input_rows}}", "{{{input_rows}}}"):
            with self.subTest(placeholder=invalid):
                text = narrative(case)
                text["methods"] += "原始行数为" + invalid + "。"
                with self.assertRaisesRegex(ValueError, "Malformed or unresolved placeholder.*methods"):
                    report_ops._render_narrative(text, metrics)
        text = narrative(case)
        text["methods"] += "采用0.95置信水平。"
        with self.assertRaisesRegex(ValueError, r"Unlinked number.*0\.95"):
            report_ops._render_narrative(text, metrics)
        text["methods"] = text["methods"].replace("0.95", "{{confidence}}")
        rendered, refs = report_ops._render_narrative(text, metrics)
        self.assertIn("confidence", refs)
        self.assertIn("0.95", rendered["methods"])

    def test_all_six_cases_render_pdf_and_preserve_metrics(self):
        kinds = {"independent_groups": ["distribution_ci", "effect_interval", "group_ecdf"],
                 "paired": ["paired_change", "effect_interval", "change_distribution"],
                 "regression": ["scatter_fit", "residuals", "effect_interval"]}
        for case in generate_data.CASES:
            with self.subTest(case=case["id"]):
                analysis_id = self.analysis(case)
                figures = [{"kind": kind} for kind in kinds[case["design"]][:case["figures"]]]
                plan = report_ops.plan_figures(analysis_id, {"figures": figures, "allow_deterministic_continuation": True})
                bundle = report_ops.render_figures(plan["figure_plan_id"])
                self.assertTrue(report_ops.verify_figures(bundle["figure_bundle_id"])["quality_passed"])
                report_plan = report_ops.plan_report(analysis_id, bundle["figure_bundle_id"], narrative(case), "pdf", case["pages"])
                result = report_ops.export_report(report_plan["report_plan_id"])
                verification = report_ops.verify_report(result["report_id"])
                self.assertTrue(verification["quality_passed"], verification)
                # Detect post-generation edits instead of silently certifying them.
                pdf = Path(result["path"])
                pdf.write_bytes(pdf.read_bytes() + b"\n% tampered\n")
                self.assertFalse(report_ops.verify_report(result["report_id"])["checks"]["file_hash_matches"])


if __name__ == "__main__":
    unittest.main()
