"""Offline real-file/tool regression only; example decisions are TEST fixtures.

These helpers are not an agent, learned motifs or evidence of LLM capability.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.research_report_agent_v2 import common as c
from benchmarks.research_report_agent_v2.generate_cases import generate
from benchmarks.research_report_agent_v3 import workflow_tools as w


def example_analysis(design='independent_groups', allow=True):
    study = c.get_study()
    analysis = {'design': design, 'outcome_column': 'value', 'missing_policy': 'complete_case',
        'confidence': .95, 'hypothesis': 'Two-sided effect and uncertainty',
        'design_evidence': {'source': 'study_description', 'quote': study['description']}}
    if design == 'regression':
        analysis['predictor_column'] = 'predictor'
    else:
        paired = design == 'paired'
        analysis.update(group_column='condition' if paired else 'group',
                        reference_group='before' if paired else 'control',
                        comparison_group='after' if paired else 'treatment')
        if paired:
            analysis['subject_column'] = 'subject'
    return {'analysis': analysis, 'allow_deterministic_continuation': allow}


def example_presentation(design='independent_groups', allow=True):
    study = c.get_study()
    report = {'title': '真实工具回归测试报告', 'style': 'technical', 'page_mode': 'auto', 'pages': None,
        'outline': [{'heading': '方法', 'roles': ['methods']},
                    {'heading': '结果', 'roles': ['results']},
                    {'heading': '诊断与限制', 'roles': ['diagnostics', 'limitations', 'next_steps']}]}
    report.update({k: v for k, v in study.get('report_requirements', {}).items() if k in {'style','page_mode','pages'}})
    if study.get('user_outline'):
        report['outline'] = [{'heading': heading, 'roles': roles} for heading,roles in zip(
            w.reusable._user_headings(study['user_outline']), [['summary'], ['methods'], ['results'], ['diagnostics','limitations','next_steps']])]
    kind = {'independent_groups': 'distribution_ci', 'paired': 'paired_change', 'regression': 'scatter_fit'}[design]
    return {'figures': [{'kind': kind, 'reason': '展示本次实际有效观测与批准的效应方向。'}],
            'tables': [], 'report': report, 'reason': '根据实际统计效应和不确定性选择原始观测图，便于核对数据与结果。',
            'allow_deterministic_continuation': allow}


def to_evidence(design='independent_groups', allow=True):
    approved = w.approve_analysis(c.get_study()['study_id'], example_analysis(design, allow))
    if not approved['ok']:
        raise AssertionError(approved)
    calculated = w.run_analysis(approved['plan_id'])
    verified = w.verify_analysis(calculated['analysis_id'])
    return w.build_evidence(verified['verified_id']), approved, calculated, verified


def to_packet(design='independent_groups', allow=True):
    evidence, approved, _, _ = to_evidence(design)
    presentation = w.approve_presentation(evidence['evidence_id'], example_presentation(design, allow))
    if not presentation['ok']:
        raise AssertionError(presentation)
    bundle = w.render_figures(presentation['presentation_id'])
    packet = w.verify_figures(bundle['figure_bundle_id'])
    return packet, presentation, evidence, bundle


def example_text(packet_id, allow=True):
    packet = c.get_record(packet_id)['payload']
    presentation = c.get_record(packet['presentation_id'])['payload']['presentation']
    texts = {
        'summary': '本报告讨论给定输入中的效应与不确定性，使用真实统计和图件。',
        'methods': '使用{{method_name}}，方向为{{contrast_name}}；完整案例纳入{{n}}个{{sample_unit}}，排除{{excluded_rows}}行，不插补，缺失机制未知。',
        'results': '效应为{{estimate}} {{effect_unit}}，{{confidence_pct}}%置信区间[{{ci_low}}, {{ci_high}}]，双侧p={{p_value}}。区间描述参数不确定性，并非观测或预测范围。',
        'diagnostics': 'Shapiro–Wilk p={{shapiro_p}}，不能证明所有模型假设成立。',
        'limitations': '本输入为合成数据，仅用于流程演示，不构成真实发现；本分析不能证明因果关系。',
        'next_steps': '进一步采样需按科学目标、成本与有效独立信息进行设计，不能保证增加样本就解决模型偏差。',
        'provenance': '来源文件及分析记录保留在本次交付旁证中。'}
    sections = []
    for item in presentation['report']['outline']:
        section = {'heading': item['heading'], 'paragraphs': [texts[role] for role in item['roles']], 'figure_indices': []}
        if 'results' in item['roles']:
            section['figure_indices'] = list(range(len(presentation['figures'])))
        sections.append(section)
    return {'sections': sections, 'allow_deterministic_continuation': allow}


def to_delivery(packet_id):
    approved = w.submit_report_text(packet_id, example_text(packet_id))
    if not approved['ok']:
        raise AssertionError(approved)
    draft = w.compose_report(approved['text_id'])
    layout = w.layout_report(draft['draft_id'])
    audited = w.audit_layout(layout['layout_id'])
    verified = w.verify_report(audited['report_id'])
    return w.deliver_report(verified['verification_id']), approved, draft, layout, verified


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.data = cls.root/'data'
        generate(cls.data)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.env = patch.dict(os.environ, {'RRA_DATA_ROOT': str(self.data),
            'RRA_RUN_ROOT': str(self.root/'runs'/self._testMethodName), 'RRA_CASE': 'v2_train_materials'})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_three_statistical_designs_stop_before_presentation(self):
        for case, design in [('v2_train_materials','independent_groups'), ('v2_train_ml','paired'), ('v2_cert_environment','regression')]:
            with self.subTest(design=design):
                os.environ['RRA_CASE'] = case
                evidence, approved, calculated, verified = to_evidence(design)
                self.assertEqual(approved['_provenance']['authorized_tools'], ['run_analysis'])
                self.assertEqual(calculated['_provenance']['authorized_tools'], ['verify_analysis'])
                self.assertEqual(verified['_provenance']['authorized_tools'], ['build_evidence'])
                self.assertEqual(evidence['_provenance']['authorized_tools'], [])
                self.assertTrue(evidence['semantic_handoff_required'])
                self.assertNotIn('data', evidence)
                self.assertEqual(evidence['results']['unit_increment']['value'], 1)
                self.assertEqual(c.get_record(approved['plan_id'])['payload']['semantic_approval']['arguments'],
                                 {'study_id': case, 'plan': example_analysis(design)})
                if design == 'paired':
                    self.assertEqual(evidence['results']['retained_rows']['value'], 2*evidence['results']['n']['value'])

    def test_analysis_cannot_preapprove_figures_or_guess_context(self):
        plan = example_analysis(); plan['figures'] = [{'kind': 'distribution_ci'}]
        self.assertFalse(w.approve_analysis(c.get_study()['study_id'], plan)['ok'])
        plan = example_analysis(); plan['analysis']['design_evidence']['quote'] = 'Invented design context'
        self.assertFalse(w.approve_analysis(c.get_study()['study_id'], plan)['ok'])
        with self.assertRaises(ValueError):
            w.approve_presentation('rra-evidence-'+'0'*32, example_presentation())

    def test_permissions_are_phase_scoped_and_optional_false_does_not_skip_model(self):
        evidence, approved, calculated, verified = to_evidence(allow=False)
        for item in (approved, calculated, verified, evidence):
            self.assertEqual(item['_provenance']['authorized_tools'], [])
        submission = example_presentation(allow=False)
        presentation = w.approve_presentation(evidence['evidence_id'], submission)
        self.assertTrue(presentation['ok'])
        self.assertEqual(presentation['_provenance']['authorized_tools'], [])
        semantic = c.get_record(presentation['presentation_id'])['payload']['semantic_approval']
        self.assertEqual(semantic['arguments'], {'evidence_id': evidence['evidence_id'], 'presentation': submission})

    def test_wrong_design_plots_and_missing_result_reasons_rejected(self):
        evidence, *_ = to_evidence()
        for modification in ('kind', 'reason', 'table'):
            presentation = example_presentation()
            if modification == 'kind': presentation['figures'][0]['kind'] = 'scatter_fit'
            if modification == 'reason': presentation['figures'][0].pop('reason')
            if modification == 'table': presentation['tables'] = [{'kind':'key_metrics','metrics':['invented'],'reason':'Invalid statistic cannot be shown'}]
            self.assertFalse(w.approve_presentation(evidence['evidence_id'], presentation)['ok'])

    def test_exact_user_outline_preserved(self):
        os.environ['RRA_CASE'] = 'v2_eval_outline'
        evidence, *_ = to_evidence('paired')
        plan = example_presentation('paired')
        self.assertTrue(w.approve_presentation(evidence['evidence_id'], plan)['ok'])
        plan['report']['outline'][0]['heading'] = '擅自替换'
        self.assertFalse(w.approve_presentation(evidence['evidence_id'], plan)['ok'])

    def test_figure_checkpoint_requires_complete_model_text(self):
        packet, presentation, evidence, _ = to_packet()
        self.assertTrue(packet['quality_passed'])
        self.assertTrue(packet['semantic_handoff_required'])
        self.assertEqual(packet['_provenance']['authorized_tools'], [])
        with self.assertRaises(ValueError):
            w.compose_report(packet['packet_id'])
        body = example_text(packet['packet_id'], allow=False)
        result = w.submit_report_text(packet['packet_id'], body)
        self.assertTrue(result['ok'])
        self.assertEqual(result['_provenance']['authorized_tools'], [])
        record = c.get_record(result['text_id'])['payload']
        self.assertEqual(record['semantic_approval']['arguments'], {'packet_id': packet['packet_id'], 'report_text': body})
        self.assertEqual(record['submitted_report_text'], body)
        draft = w.compose_report(result['text_id'])
        document = c.get_record(draft['draft_id'])['payload']['document']
        self.assertEqual(document['sections'], record['rendered_sections'])
        self.assertEqual(sum(len(s['paragraphs']) for s in document['sections']),sum(len(s['paragraphs']) for s in body['sections']))
        self.assertEqual(draft['_provenance']['authorized_tools'], [])

    def test_precise_text_errors_and_valid_same_packet_recovery(self):
        packet, *_ = to_packet()
        body = example_text(packet['packet_id'])
        body['sections'][1]['paragraphs'].append('p=0.01与未知量{{made_up}}以及错误花括号{estimate}。')
        result = w.submit_report_text(packet['packet_id'], body)
        self.assertFalse(result['ok'])
        self.assertEqual({e['code'] for e in result['validation_errors']}, {'unbound_number','unknown_placeholder','malformed_placeholder'})
        self.assertTrue(all(e['field'] == 'sections[1].paragraphs[1]' for e in result['validation_errors']))
        self.assertTrue(w.submit_report_text(packet['packet_id'], example_text(packet['packet_id']))['ok'])

    def test_full_llm_body_actual_one_page_pdf_cache_and_tamper(self):
        os.environ['RRA_CASE'] = 'v2_eval_brief'
        packet, *_ = to_packet('regression')
        delivered, approved, draft, layout, verified = to_delivery(packet['packet_id'])
        self.assertTrue(delivered['delivered'])
        self.assertEqual(delivered['page_count'], 1)
        self.assertFalse(delivered['scientific_prose_verified'])
        with patch.object(w.document_engine, 'build_document', side_effect=AssertionError('unchanged draft rendered again')):
            cached = w.layout_report(draft['draft_id'])
        self.assertTrue(cached['cache_reused'])
        self.assertEqual(cached['layout_id'], layout['layout_id'])
        pdf = Path(delivered['path']); pdf.write_bytes(pdf.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError, 'PDF changed'):
            w.deliver_report(verified['verification_id'])

    def test_one_page_capacity_failure_keeps_original_packet_and_evidence(self):
        os.environ['RRA_CASE'] = 'v2_eval_brief'
        packet, *_ = to_packet('regression')
        body = example_text(packet['packet_id'])
        body['sections'][2]['paragraphs'].append('这段模型自由讨论不断补充未验证的解释并明确所有方案均需独立验证。'*50)
        result = w.submit_report_text(packet['packet_id'], body)
        self.assertFalse(result['ok'])
        self.assertIn('capacity_preflight', result)
        self.assertFalse(result['capacity_preflight']['fits_one_page'])
        self.assertTrue(w.submit_report_text(packet['packet_id'], example_text(packet['packet_id']))['ok'])

    def test_failed_layout_is_cached_without_deleting_body_or_padding(self):
        packet, *_ = to_packet()
        old_packet = c.get_record(packet['packet_id'])['payload']
        old_presentation = c.get_record(old_packet['presentation_id'])['payload']
        proposed = copy.deepcopy(old_presentation['presentation'])
        proposed['report'].update(page_mode='exact', pages=6)
        presentation = w.approve_presentation(old_packet['evidence_id'], proposed)
        bundle = w.render_figures(presentation['presentation_id'])
        packet = w.verify_figures(bundle['figure_bundle_id'])
        approved = w.submit_report_text(packet['packet_id'], example_text(packet['packet_id']))
        draft = w.compose_report(approved['text_id'])
        with patch.object(w.document_engine, 'build_document', wraps=w.document_engine.build_document) as render:
            first = w.layout_report(draft['draft_id'])
            second = w.layout_report(draft['draft_id'])
        self.assertEqual(render.call_count, 1)
        self.assertFalse(first['quality_passed'])
        self.assertTrue(second['cache_reused'])
        self.assertEqual(first['layout_id'], second['layout_id'])
        self.assertEqual(second['_provenance']['authorized_tools'], [])
        self.assertIn('Do not retry', second['next_step'])
        audit = w.audit_layout(first['layout_id'])
        checked = w.verify_report(audit['report_id'])
        with self.assertRaisesRegex(ValueError, 'failed report'):
            w.deliver_report(checked['verification_id'])

    def test_no_silent_discard_of_extra_model_prose(self):
        packet, *_ = to_packet()
        text = example_text(packet['packet_id'])
        text['extra_discussion'] = 'This entire paragraph must never silently disappear.'
        rejected = w.submit_report_text(packet['packet_id'], text)
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['validation_errors'][0]['code'], 'extra_forbidden')
        text = example_text(packet['packet_id'])
        text['comparison_summary'] = 'A model supplied comparison with no structured alternatives.'
        self.assertFalse(w.submit_report_text(packet['packet_id'], text)['ok'])

    def test_research_options_are_model_text_with_auditable_insertions(self):
        os.environ['RRA_CASE'] = 'v2_eval_technical'
        packet, *_ = to_packet('regression')
        body = example_text(packet['packet_id'])
        self.assertFalse(w.submit_report_text(packet['packet_id'], body)['ok'])
        body.update(research_options=[
            {'name':'范围内补样','rationale':'根据本次{{estimate}}与置信区间评估目标精度，具体收益仍需采样设计计算。','tradeoff':'有效信息取决于独立性、解释变量分布及资源。'},
            {'name':'跨环境验证','rationale':'另行采集不同环境的独立数据，检查当前关联的推广性。','tradeoff':'环境异质性可能需要分层模型，不能保证因果识别。'}],
            comparison_summary='若关注当前范围内精度，评估补样；若关注推广性，评估跨环境验证。选择取决于预算和目标，仍属待检验方案。')
        result = w.submit_report_text(packet['packet_id'], body)
        self.assertTrue(result['ok'])
        text = c.get_record(result['text_id'])['payload']
        self.assertEqual(text['submitted_report_text'], body)
        self.assertEqual(len(text['rendered_sections']), len(body['sections']))
        self.assertEqual(text['transformations'][1]['operation'], 'append_model_research_options_to_existing_section')

    def test_source_task_change_invalidates_old_receipt(self):
        evidence, *_ = to_evidence()
        task = c.get_case_dir()/'task.txt'; previous = task.read_bytes()
        try:
            task.write_bytes(previous+b' changed')
            with self.assertRaisesRegex(ValueError, 'source data changed'):
                w.approve_presentation(evidence['evidence_id'], example_presentation())
        finally:
            task.write_bytes(previous)

    def test_no_prefilled_workflow_and_no_missing_permission_default(self):
        study_path = c.get_case_dir()/'study.json'; previous = study_path.read_bytes()
        try:
            study = json.loads(previous); study['benchmark_frozen_decisions'] = {}
            study_path.write_text(json.dumps(study), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'frozen_decisions'):
                w.inspect_study()
            self.assertFalse(w.approve_analysis(study['study_id'], example_analysis())['ok'])
        finally:
            study_path.write_bytes(previous)
        plan = example_analysis(); del plan['allow_deterministic_continuation']
        self.assertFalse(w.approve_analysis(c.get_study()['study_id'], plan)['ok'])

    def test_contract_has_three_semantic_approvals_and_single_id_determinism(self):
        contracts = json.loads((Path(w.__file__).parent/'tool_contracts.json').read_text())
        self.assertEqual(len(contracts), 14)
        for name, entry in contracts.items():
            if entry['execution'] == 'workspace_idempotent':
                self.assertEqual(len(entry['required_params']), 1, name)
                self.assertEqual(len(entry['output_fields']), 1, name)
        self.assertEqual([name.removeprefix('mcp__research_report__') for name,e in contracts.items()
                          if e['execution'] == 'semantic'], ['inspect_study','approve_analysis','approve_presentation','submit_report_text'])

    def test_report_text_schema_exposes_required_fields_and_forbids_extras(self):
        from typing import get_type_hints
        schema = w.ReportText.model_json_schema()
        self.assertIs(get_type_hints(w.submit_report_text)['report_text'], w.ReportText)
        self.assertEqual(set(schema['required']), {'sections','allow_deterministic_continuation'})
        self.assertNotIn('default', schema['properties']['allow_deterministic_continuation'])
        self.assertEqual(schema['properties']['allow_deterministic_continuation']['type'], 'boolean')
        self.assertFalse(schema['additionalProperties'])
        section = schema['$defs']['ReportSection']
        self.assertEqual(set(section['required']), {'heading','paragraphs','figure_indices'})
        self.assertFalse(section['additionalProperties'])
        self.assertEqual(section['properties']['figure_indices']['items']['minimum'], 0)

    def test_all_structure_errors_together_and_raw_input_is_preserved(self):
        packet, *_ = to_packet()
        body = example_text(packet['packet_id'])
        del body['allow_deterministic_continuation']
        del body['sections'][0]['figure_indices']
        body['sections'][0]['roles'] = ['methods']
        rejected = w.submit_report_text(packet['packet_id'], body)
        self.assertFalse(rejected['ok'])
        self.assertEqual({e['field'] for e in rejected['validation_errors']}, {
            'report_text.allow_deterministic_continuation', 'report_text.sections.0.figure_indices',
            'report_text.sections.0.roles'})
        body = example_text(packet['packet_id'])
        for wrong in ('true', 1):
            body['allow_deterministic_continuation'] = wrong
            self.assertFalse(w.submit_report_text(packet['packet_id'], body)['ok'])
        body['allow_deterministic_continuation'] = True
        typed = w.ReportText.model_validate(body)
        approved = w.submit_report_text(packet['packet_id'], typed)
        self.assertTrue(approved['ok'])
        payload = c.get_record(approved['text_id'])['payload']
        self.assertEqual(payload['semantic_approval']['arguments']['report_text'], body)
        self.assertNotIn('research_options', payload['submitted_report_text'])

    def test_known_figure_labels_and_ordered_inline_lists_are_not_scientific_numbers(self):
        evidence, *_ = to_evidence()
        payload = c.get_record(evidence['evidence_id'])['payload']
        cases = [
            '图1展示有效观测，Figure 2说明不确定性，Fig. 3展示分布。',
            '图1/2/3的解释需结合图注；图1、2、3不能证明因果。',
            '研究建议：（1）明确科学目标；（2）核验缺失机制；（3）比较不同采样设计。',
            '建议：1）核查设计；2）记录成本；3）评估采样相关性。',
            '先做两步：1. 核查设计；2. 明确科学问题。',
        ]
        for text in cases:
            with self.subTest(text=text):
                errors, bindings = [], []
                rendered = w._bind(text, 'paragraph', payload, errors, bindings, figure_count=3)
                self.assertEqual(errors, [])
                self.assertEqual(rendered, text)
                self.assertTrue(bindings[0]['formatting_references'])

    def test_unknown_figures_and_bare_scientific_values_still_rejected(self):
        evidence, *_ = to_evidence()
        payload = c.get_record(evidence['evidence_id'])['payload']
        errors, bindings = [], []
        w._bind('图1显示均值5.5而非6.2，p=0.0177，零假设为0。图2不存在。',
                'paragraph', payload, errors, bindings, figure_count=1)
        self.assertEqual({e['code'] for e in errors}, {'unknown_figure_reference','unbound_number'})
        numbers = next(e['literals'] for e in errors if e['code']=='unbound_number')
        self.assertEqual(numbers, ['5.5','6.2','0.0177','0'])
        for text in ('估计值为（1）。', '建议：（1）核查；（3）比较。', '1.5为本次均值。'):
            errors, bindings = [], []
            w._bind(text, 'paragraph', payload, errors, bindings, figure_count=1)
            self.assertTrue(any(e['code']=='unbound_number' for e in errors))

    def test_valid_figure_reference_in_actual_report_and_disclosures_remain_required(self):
        packet, *_ = to_packet()
        body = example_text(packet['packet_id'])
        body['sections'][1]['paragraphs'].append('图1呈现本次有效观测，应结合估计的不确定性而不是只看散点判断。')
        approved = w.submit_report_text(packet['packet_id'], body)
        self.assertTrue(approved['ok'])
        original = copy.deepcopy(body)
        body['sections'][1]['paragraphs'][-1] = '图2并没有对应的实际图件。'
        rejected = w.submit_report_text(packet['packet_id'], body)
        self.assertTrue(any(e['code']=='unknown_figure_reference' for e in rejected['validation_errors']))
        body = original
        body['sections'][2]['paragraphs'][1] = '来源信息不讨论。'
        rejected = w.submit_report_text(packet['packet_id'], body)
        self.assertEqual({e['code'] for e in rejected['validation_errors']}, {'missing_source_disclosure','missing_causal_boundary'})


if __name__ == '__main__':
    unittest.main()
