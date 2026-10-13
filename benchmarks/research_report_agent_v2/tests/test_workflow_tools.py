"""Offline real-file calculations and workflow guards; no model or paid API."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.research_report_agent_v2 import common as c
from benchmarks.research_report_agent_v2 import workflow_tools as w
from benchmarks.research_report_agent_v2.generate_cases import generate


def example_plan(design, *, mode='standard', allow=True):
    """TEST-ONLY decisions; production decisions come from the actual LLM."""
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
    kind = {'regression': 'scatter_fit', 'paired': 'paired_change', 'independent_groups': 'distribution_ci'}[design]
    report = {'page_mode': 'auto', 'pages': None, 'style': 'technical'}
    report.update({k:v for k,v in study.get('report_requirements', {}).items() if k != 'language'})
    if study.get('user_outline'):
        report['outline'] = [
            {'heading': '研究问题', 'roles': ['summary']},
            {'heading': '数据与方法', 'roles': ['methods']},
            {'heading': '主要结果及图表', 'roles': ['results', 'diagnostics']},
            {'heading': '局限与下一步', 'roles': ['limitations', 'next_steps', 'provenance']},
        ]
    return {'analysis': analysis, 'figures': [{'kind': kind}], 'report': report,
            'interpretation_mode': mode, 'allow_deterministic_continuation': allow}


def to_evidence(plan):
    approved = w.approve_workflow(c.get_study()['study_id'], plan)
    if not approved['ok']:
        raise AssertionError(approved)
    calculated = w.run_analysis(approved['plan_id'])
    verified = w.verify_analysis(calculated['analysis_id'])
    return w.build_evidence(verified['verified_id']), calculated, approved


def to_delivery(evidence_id):
    figures = w.render_figures(evidence_id)
    packet = w.verify_figures(figures['figure_bundle_id'])
    draft = w.compose_report(packet['packet_id'])
    layout = w.layout_report(draft['draft_id'])
    report = w.audit_layout(layout['layout_id'])
    verified = w.verify_report(report['report_id'])
    delivered = w.deliver_report(verified['verification_id'])
    return delivered, draft, layout, verified


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.data = cls.root / 'data'
        generate(cls.data)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.env = patch.dict(os.environ, {'RRA_DATA_ROOT': str(self.data),
            'RRA_RUN_ROOT': str(self.root / 'runs' / self._testMethodName), 'RRA_CASE': 'v2_train_materials'})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def select(self, case):
        os.environ['RRA_CASE'] = case

    def test_independent_recomputation_all_three_designs_and_direction(self):
        for case, design in [('v2_train_materials','independent_groups'), ('v2_train_ml','paired'), ('v2_cert_environment','regression')]:
            with self.subTest(design=design):
                self.select(case)
                evidence, calculated, approved = to_evidence(example_plan(design))
                self.assertFalse(evidence['semantic_handoff_required'])
                self.assertEqual(evidence['_provenance']['authorized_tools'], ['render_figures'])
                self.assertGreater(calculated['diagnostics']['excluded_rows'], 0)
                self.assertEqual(calculated['_provenance']['plan_id'], approved['plan_id'])
                if design == 'paired':
                    self.assertEqual(calculated['diagnostics']['retained_rows'], 2*calculated['statistics']['n'])
                    text = ''.join(sum(w._standard_paragraphs(c.get_record(calculated['analysis_id'])['payload'], c.get_study()).values(), []))
                    self.assertIn('不同实验单元的配对差值相互独立', text)
                    self.assertIn('同一单元的两次测量允许相关', text)

    def test_brief_actual_pdf_is_one_page_and_delivery_rejects_tamper(self):
        self.select('v2_eval_brief')
        evidence, _, _ = to_evidence(example_plan('regression'))
        delivered, draft, layout, verified = to_delivery(evidence['evidence_id'])
        self.assertTrue(delivered['delivered'])
        self.assertEqual(delivered['page_count'], 1)
        engine = c.get_record(layout['layout_id'])['payload']['engine']
        self.assertTrue(engine['audit']['quality_passed'])
        document = c.get_record(draft['draft_id'])['payload']['document']
        text = ''.join(p for section in document['sections'] for p in section['paragraphs'])
        for important in ('CI', '双侧p=', '完整案例', '合成', '不建立因果'):
            self.assertIn(important, text)
        self.assertLess(len(text), 650)
        with patch.object(w._engine(),'build_document',side_effect=AssertionError('unchanged draft rendered again')):
            cached=w.layout_report(draft['draft_id'])
        self.assertTrue(cached['cache_reused'])
        self.assertEqual(cached['layout_id'],layout['layout_id'])
        pdf = Path(delivered['path'])
        pdf.write_bytes(pdf.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'changed PDF'):
            w.deliver_report(verified['verification_id'])
        with self.assertRaisesRegex(ValueError,'PDF changed'):
            w.layout_report(draft['draft_id'])

    def test_failed_layout_cached_and_engine_version_creates_separate_attempts(self):
        plan=example_plan('independent_groups')
        plan['report'].update(page_mode='exact',pages=6)
        evidence,_,_=to_evidence(plan)
        figures=w.render_figures(evidence['evidence_id'])
        packet=w.verify_figures(figures['figure_bundle_id'])
        draft=w.compose_report(packet['packet_id'])
        engine=w._engine()
        with patch.object(engine,'build_document',wraps=engine.build_document) as render:
            first=w.layout_report(draft['draft_id'])
            second=w.layout_report(draft['draft_id'])
            self.assertEqual(render.call_count,1)
        self.assertFalse(first['quality_passed'])
        self.assertTrue(second['cache_reused'])
        self.assertEqual(first['layout_id'],second['layout_id'])
        self.assertEqual(first['_provenance']['authorized_tools'],[])
        self.assertIn('Do not retry',first['next_step'])
        original=c.get_record(first['layout_id'])['payload']['engine']
        with patch.object(engine,'ENGINE_VERSION',engine.ENGINE_VERSION+'-test-next'):
            newer=w.layout_report(draft['draft_id'])
        revised=c.get_record(newer['layout_id'])['payload']['engine']
        self.assertNotEqual(original['path'],revised['path'])
        self.assertTrue(Path(original['path']).is_file())
        Path(original['manifest_path']).write_bytes(Path(original['manifest_path']).read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'manifest changed'):
            w.layout_report(draft['draft_id'])

    def test_layout_soft_warning_is_retained_and_deliverable(self):
        self.select('v2_eval_brief')
        evidence,_,_=to_evidence(example_plan('regression'))
        engine=w._engine(); original=engine.audit_document
        def warning_audit(*args,**kwargs):
            result=original(*args,**kwargs)
            result['soft_warnings']=[{'code':'test_soft_warning','message':'Benign test-only layout warning'}]
            result['acceptance_status']='accepted_with_warnings'
            return result
        with patch.object(engine,'audit_document',side_effect=warning_audit):
            delivered,_,layout,_=to_delivery(evidence['evidence_id'])
        self.assertTrue(delivered['quality_passed'])
        self.assertEqual(delivered['warnings'][0]['code'],'test_soft_warning')
        self.assertEqual(layout['warnings'],delivered['warnings'])

    def test_fixed_decisions_are_visible_and_still_require_normal_validation(self):
        self.select('v2_cert_environment')
        self.assertIsNone(w._fixed_decisions(c.get_study()))
        source=c.get_case_dir()/'study.json'; original=source.read_bytes()
        plan=example_plan('regression',mode='custom')
        commentary={'paragraphs':['每升高{{unit_increment}}个原始单位，平均变化为{{estimate}}，不应解释为因果。'],
                    'allow_deterministic_continuation':True}
        def install(frozen_commentary):
            study=json.loads(original)
            decisions={'plan':plan,'commentary':frozen_commentary}
            study['benchmark_frozen_decisions']={'protocol_version':1,**decisions,
                'decision_sha256':hashlib.sha256(c.canonical(decisions)).hexdigest()}
            source.write_text(json.dumps(study,ensure_ascii=False),encoding='utf-8')
        try:
            install(commentary)
            self.assertEqual(w.inspect_study()['benchmark_fixed_decisions']['plan'],plan)
            changed=copy.deepcopy(plan); changed['analysis']['confidence']=.90
            self.assertIn('differs',w.approve_workflow(c.get_study()['study_id'],changed)['reason'])
            evidence,_,_=to_evidence(plan)
            self.assertEqual(evidence['benchmark_fixed_commentary'],commentary)
            changed=copy.deepcopy(commentary); changed['paragraphs'][0]+='额外修改。'
            self.assertIn('differs',w.approve_interpretation(evidence['evidence_id'],changed)['reason'])
            self.assertTrue(w.approve_interpretation(evidence['evidence_id'],commentary)['ok'])
            # Even an exactly matched frozen specification cannot authorize an
            # unsupported quantitative claim or replace the real LLM submission.
            unsafe={'paragraphs':['当前斜率为987654，这个未绑定的数值即使在固定协议中也不能通过。'],
                    'allow_deterministic_continuation':True}
            install(unsafe)
            evidence,_,_=to_evidence(plan)
            rejected=w.approve_interpretation(evidence['evidence_id'],unsafe)
            self.assertIn('unbound_number',{e['code'] for e in rejected['validation_errors']})
        finally:
            source.write_bytes(original)

    def test_one_page_capacity_is_checked_before_any_analysis(self):
        self.select('v2_eval_brief')
        plan = example_plan('regression')
        plan['figures'].append({'kind': 'residuals'})
        rejected = w.approve_workflow(c.get_study()['study_id'], plan)
        self.assertTrue(rejected['clarification_required'])
        self.assertIn('at most one figure', rejected['reason'])
        self.assertFalse(list(c.get_run_dir().glob('records/rra-analysis_plan-*.json')))
        plan['figures'] = plan['figures'][:1]
        accepted = w.approve_workflow(c.get_study()['study_id'], plan)
        self.assertTrue(accepted['ok'])
        self.assertEqual(len(accepted['approved_workflow']['figures']), 1)
        # An explicit two-figure request is a genuine conflict, not permission
        # to silently replace the requested figures with a one-figure plan.
        source = c.get_case_dir() / 'study.json'
        original = source.read_bytes()
        try:
            study = json.loads(original)
            study['report_requirements']['figure_count'] = 2
            source.write_text(json.dumps(study, ensure_ascii=False), encoding='utf-8')
            self.assertTrue(w.approve_workflow(c.get_study()['study_id'], plan)['clarification_required'])
            plan['figures'].append({'kind': 'residuals'})
            self.assertIn('one-page', w.approve_workflow(c.get_study()['study_id'], plan)['reason'])
        finally:
            source.write_bytes(original)

    def test_outline_preserved_in_real_document(self):
        self.select('v2_eval_outline')
        plan = example_plan('paired',mode='custom')
        bad = copy.deepcopy(plan)
        bad['report']['outline'][0]['heading'] = 'changed'
        self.assertTrue(w.approve_workflow(c.get_study()['study_id'], bad)['clarification_required'])
        evidence, _, _ = to_evidence(plan)
        evidence = w.approve_interpretation(evidence['evidence_id'],{
            'paragraphs':['配对均值变化为{{estimate}}，仍需结合完整配对图判断个体差异；当前结果不证明训练具有因果效果。'],
            'allow_deterministic_continuation':True})
        delivered, draft, layout, _ = to_delivery(evidence['evidence_id'])
        self.assertLessEqual(delivered['page_count'], 3)
        document = c.get_record(draft['draft_id'])['payload']['document']
        self.assertEqual([s['heading'] for s in document['sections']], c.get_study()['user_outline'].splitlines())
        engine = c.get_record(layout['layout_id'])['payload']['engine']
        manifest = Path(engine['manifest_path'])
        manifest.write_bytes(manifest.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            w.audit_layout(layout['layout_id'])

    def test_one_page_heading_limit_does_not_silently_remove_user_outline(self):
        self.select('v2_eval_brief')
        plan = example_plan('regression')
        plan['report']['outline'] = copy.deepcopy(w.DEFAULT_OUTLINE)
        rejected = w.approve_workflow(c.get_study()['study_id'],plan)
        self.assertTrue(rejected['clarification_required'])
        self.assertIn('at most four headings',rejected['reason'])
        source = c.get_case_dir()/'study.json'
        original = source.read_bytes()
        try:
            study = json.loads(original)
            study['user_outline'] = '\n'.join(item['heading'] for item in w.DEFAULT_OUTLINE)
            source.write_text(json.dumps(study,ensure_ascii=False),encoding='utf-8')
            rejected = w.approve_workflow(c.get_study()['study_id'],plan)
            self.assertIn('do not silently delete',rejected['reason'])
            self.assertEqual(len(plan['report']['outline']),6)
        finally:
            source.write_bytes(original)

    def test_custom_one_page_capacity_uses_expanded_payload_and_same_evidence_retry(self):
        self.select('v2_eval_brief')
        evidence, _, _ = to_evidence(example_plan('regression',mode='custom'))
        very_long = ('本段说明仅为关联估计、不能证明因果，后续需要审查采样与缺失处理，并结合模型诊断检验假设。'*10)
        rejected = w.approve_interpretation(evidence['evidence_id'],{
            'paragraphs':[very_long,very_long],'allow_deterministic_continuation':True})
        self.assertTrue(rejected['clarification_required'])
        error = next(e for e in rejected['validation_errors'] if e['code']=='one_page_text_capacity')
        capacity = error['capacity']
        self.assertGreater(capacity['height_pt'],capacity['available_height_pt'])
        self.assertEqual(capacity['rendered_custom_characters'],len(very_long)*2)
        self.assertLess(capacity['suggested_custom_character_budget'],capacity['rendered_custom_characters'])
        self.assertFalse(list(c.get_run_dir().glob('artifacts/**/*')))
        accepted = w.approve_interpretation(evidence['evidence_id'],{
            'paragraphs':['本次斜率为{{estimate}}，只描述合成数据中的统计关联；后续应复核采样与模型条件。'],
            'allow_deterministic_continuation':True})
        self.assertTrue(accepted['ok'],accepted)
        self.assertEqual(c.get_record(accepted['evidence_id'])['payload']['analysis_id'],c.get_record(evidence['evidence_id'])['payload']['analysis_id'])
        delivery,_,_,_ = to_delivery(accepted['evidence_id'])
        self.assertEqual(delivery['page_count'],1)
        self.assertEqual(len(list(c.get_run_dir().glob('records/rra-analysis-*.json'))),1)

    def test_research_choices_require_structured_distinct_options_and_comparison(self):
        self.select('v2_eval_technical')
        evidence, _, _ = to_evidence(example_plan('regression',mode='custom'))
        self.assertEqual(evidence['interpretation_contract']['research_options']['required_minimum'],2)
        proposed={'paragraphs':['本次斜率为{{estimate}}，后续研究建议仍需要结合设计验证。'],'allow_deterministic_continuation':True}
        rejected=w.approve_interpretation(evidence['evidence_id'],proposed)
        self.assertIn('research_options_count',{e['code'] for e in rejected['validation_errors']})
        proposed=copy.deepcopy(evidence['interpretation_contract']['example']['commentary'])
        proposed['research_options'][1]['name']=proposed['research_options'][0]['name']
        proposed['research_options'][0]['tradeoff']='未经绑定的科学数值987654仍然不允许出现在研究方案中。'
        rejected=w.approve_interpretation(evidence['evidence_id'],proposed)
        self.assertIn('duplicate_research_option',{e['code'] for e in rejected['validation_errors']})
        self.assertTrue(any(e['code']=='unbound_number' and e['field']=='research_options[0].tradeoff' for e in rejected['validation_errors']))
        accepted=w.approve_interpretation(**evidence['interpretation_contract']['example'])
        self.assertTrue(accepted['ok'])
        payload=c.get_record(accepted['evidence_id'])['payload']
        self.assertEqual(len(payload['research_options']),2)
        self.assertTrue(payload['comparison_summary'])
        text='\n'.join(w._interpretation_paragraphs(payload))
        self.assertIn('方案比较：',text)
        self.assertNotIn('{{',text)

    def test_explicit_negation_does_not_require_research_comparison(self):
        for request in ['不需要比较两种后续研究方案，只要标准结果。',
                        '无需再比较两种后续研究方案。',
                        'Do not compare two research plans; provide standard results.']:
            with self.subTest(request=request):
                self.assertEqual(w._research_options_requirement({'user_request':request})['minimum'],0)
                self.assertEqual(w._research_options_requirement({'user_request':request,'report_requirements':{'research_options_min':2}})['minimum'],2)
        self.assertEqual(w._research_options_requirement({'user_request':'不需要比较两种后续研究方案；请比较两种采样方案。'})['minimum'],2)

    def test_self_effect_comparison_is_rejected_without_claiming_general_expert_review(self):
        self.select('v2_train_ml')
        evidence,_,_=to_evidence(example_plan('paired',mode='custom'))
        rejected=w.approve_interpretation(evidence['evidence_id'],{
            'paragraphs':['标准化效应量的绝对值大于{{effect_size}}所对应的量级参照，这个比较不能成立。'],
            'allow_deterministic_continuation':True})
        self.assertIn('self_effect_comparison',{e['code'] for e in rejected['validation_errors']})

    def test_custom_mode_has_real_semantic_barrier(self):
        self.select('v2_eval_technical')
        evidence, _, _ = to_evidence(example_plan('regression', mode='custom'))
        self.assertTrue(evidence['semantic_handoff_required'])
        self.assertEqual(evidence['_provenance']['authorized_tools'], [])
        with self.assertRaisesRegex(ValueError, 'interpretation'):
            w.render_figures(evidence['evidence_id'])
        invalid = w.approve_interpretation(evidence['evidence_id'], {'paragraphs':['模型错误地添加了999这一个不受支持的数值。'], 'allow_deterministic_continuation':True})
        self.assertTrue(invalid['clarification_required'])
        valid = copy.deepcopy(evidence['interpretation_contract']['example']['commentary'])
        valid['paragraphs'] = ['本次斜率为{{estimate}}，下一步可增加采样范围并检查残差结构，此建议仅为待验证的研究方向。']
        approved = w.approve_interpretation(evidence['evidence_id'], valid)
        self.assertTrue(approved['ok'])
        self.assertEqual(approved['_provenance']['authorized_tools'], ['render_figures'])
        self.assertFalse(approved['custom_prose_scientifically_verified'])

    def test_custom_contract_binds_diagnostics_and_confidence_with_trace(self):
        self.select('v2_eval_technical')
        evidence, calculated, _ = to_evidence(example_plan('regression', mode='custom'))
        catalog = evidence['available_placeholders']
        for name in ('shapiro_w','shapiro_p','confidence_pct','alpha','null_value','unit_increment','statistic','standard_error','df','residual_sd'):
            self.assertIn(name, catalog)
            self.assertEqual(catalog[name]['token'], '{{'+name+'}}')
        self.assertAlmostEqual(catalog['shapiro_p']['value'], calculated['diagnostics']['shapiro_p'])
        self.assertAlmostEqual(catalog['statistic']['value'], calculated['statistics']['statistic'])
        example = evidence['interpretation_contract']['example']
        self.assertEqual(example['evidence_id'], evidence['evidence_id'])
        approved = w.approve_interpretation(**example)
        self.assertTrue(approved['ok'])
        record = c.get_record(approved['evidence_id'])['payload']
        self.assertNotIn('{{', ''.join(record['custom_commentary']))
        self.assertIn('shapiro_p', record['custom_bindings'][0]['names'])
        self.assertEqual(record['parent_evidence_id'], evidence['evidence_id'])
        self.assertIn('{{shapiro_p}}', record['custom_commentary_template'][0])

    def test_eight_paragraphs_and_unit_increment_keep_numeric_and_resource_guards(self):
        self.select('v2_cert_environment')
        evidence,_,_=to_evidence(example_plan('regression',mode='custom'))
        paragraphs=['每升高{{unit_increment}}个原始单位，拟合平均结局变化为{{estimate}}；这不证明因果。']
        paragraphs += ['本段补充报告结构，研究解释仍需结合采样和缺失条件。']*7
        accepted=w.approve_interpretation(evidence['evidence_id'],{'paragraphs':paragraphs,'allow_deterministic_continuation':True})
        self.assertTrue(accepted['ok'],accepted)
        record=c.get_record(accepted['evidence_id'])['payload']
        self.assertEqual(len(record['custom_commentary']),8)
        self.assertIn('每升高1个原始单位',record['custom_commentary'][0])
        self.assertEqual(evidence['available_placeholders']['unit_increment']['value'],1)
        bad=w.approve_interpretation(evidence['evidence_id'],{'paragraphs':['温度每升高123个单位，这个未经绑定的数值仍然必须拒绝。'],'allow_deterministic_continuation':True})
        self.assertIn('unbound_number',{e['code'] for e in bad['validation_errors']})
        huge={'paragraphs':['谨'*800]*8,'allow_deterministic_continuation':True,
              'research_options':[{'name':'方案'+name,'rationale':'据'*500,'tradeoff':'代价仍需要研究者结合设计评估。'} for name in '甲乙丙丁'],
              'comparison_summary':'不同研究方案的资源取舍仍需通过明确设计进一步比较。'}
        rejected=w.approve_interpretation(evidence['evidence_id'],huge)
        self.assertIn('custom_text_resource_limit',{e['code'] for e in rejected['validation_errors']})

    def test_custom_validation_reports_all_issues_and_never_adds_authorization(self):
        self.select('v2_eval_technical')
        evidence, _, _ = to_evidence(example_plan('regression', mode='custom'))
        failed = w.approve_interpretation(evidence['evidence_id'], {'paragraphs':[
            '本次95%区间不跨0，但误用了{{shapiro_P}}，这些内容需要明确修复。',
            '这个段落用了不完整的{estimate}占位符，需要明确指出。',
            '另一个段落没有受支持的数值来源，写出98765仍然必须被拒绝。',
            *['额外段落用于验证资源边界，不应改变数字或授权守卫。']*6]})
        codes = {error['code'] for error in failed['validation_errors']}
        self.assertTrue({'paragraph_count','explicit_authorization_required','malformed_placeholder','unbound_number'} <= codes)
        errors = [error for error in failed['validation_errors'] if error['code']=='unbound_number']
        confidence = next(error for error in errors if error['literal']=='95%')
        self.assertIn('{{confidence_pct}}%', confidence['replacement_hints'])
        zero = next(error for error in errors if error['literal']=='0')
        self.assertIn('{{null_value}}', zero['replacement_hints'])
        self.assertIn('available_placeholders', failed)
        self.assertEqual(c.get_record(evidence['evidence_id'])['_provenance']['authorized_tools'], [])
        with self.assertRaisesRegex(ValueError, 'interpretation'):
            w.render_figures(evidence['evidence_id'])

    def test_custom_ordered_prefix_is_formatting_but_unbound_claim_still_fails(self):
        self.select('v2_train_ml')
        evidence, _, _ = to_evidence(example_plan('paired', mode='custom'))
        paragraphs = ['1. 本次配对差值为{{estimate}}，需要结合区间判断不确定性。',
                      '2. 后续可评估不同数据划分，但这项建议仍须验证。']
        approved = w.approve_interpretation(evidence['evidence_id'], {'paragraphs':paragraphs, 'allow_deterministic_continuation':True})
        self.assertTrue(approved['ok'])
        paragraphs[1] = '2. 本次配对差值为100，不能因为允许编号就允许科学数值。'
        rejected = w.approve_interpretation(evidence['evidence_id'], {'paragraphs':paragraphs, 'allow_deterministic_continuation':True})
        self.assertEqual([error['literal'] for error in rejected['validation_errors'] if error['code']=='unbound_number'], ['100'])

    def test_auxiliary_recomputation_rejects_changed_diagnostic(self):
        approved = w.approve_workflow(c.get_study()['study_id'], example_plan('independent_groups'))
        calculated = w.run_analysis(approved['plan_id'])
        altered = copy.deepcopy(c.get_record(calculated['analysis_id'])['payload'])
        altered['diagnostics']['shapiro_p'] = .123456789
        altered_id = c.put_record('analysis', altered, ['verify_analysis'])
        with self.assertRaisesRegex(ValueError, 'Auxiliary statistic/diagnostic verification failed'):
            w.verify_analysis(altered_id)

    def test_figure_title_errors_are_actionable_and_english_title_is_preserved(self):
        plan = example_plan('independent_groups')
        plan['figures'][0]['title'] = '实际中文图标题'
        rejected = w.approve_workflow(c.get_study()['study_id'], plan)
        self.assertTrue(rejected['clarification_required'])
        self.assertIn('figures[0].title', rejected['reason'])
        self.assertIn('Omit the optional title field', rejected['reason'])
        self.assertIn('rather than silently replacing', rejected['reason'])
        plan['figures'][0]['title'] = 'Observed strength by condition'
        approved = w.approve_workflow(c.get_study()['study_id'], plan)
        self.assertEqual(approved['approved_workflow']['figures'][0]['title'], plan['figures'][0]['title'])

    def test_authority_not_implicit(self):
        evidence, calculated, approved = to_evidence(example_plan('independent_groups', allow=False))
        for receipt in (evidence, calculated, approved):
            self.assertEqual(receipt['_provenance']['authorized_tools'], [])

    def test_all_source_files_bind_records_and_receipt_hash(self):
        plan = example_plan('independent_groups')
        approved = w.approve_workflow(c.get_study()['study_id'], plan)
        provenance = approved['_provenance']
        self.assertEqual(c.sha256_file(Path(provenance['record_path'])), provenance['record_sha256'])
        source = c.get_case_dir() / 'task.txt'
        original = source.read_bytes()
        try:
            source.write_bytes(original + b'\nchanged requirement')
            with self.assertRaisesRegex(ValueError, 'source data changed'):
                w.run_analysis(approved['plan_id'])
        finally:
            source.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'invalid record'):
            w.run_analysis('../../oracles/data.json')
        os.environ['RRA_RUN_ROOT'] += '_other'
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            w.run_analysis(approved['plan_id'])

    def test_unknown_origin_is_not_labeled_synthetic(self):
        source = c.get_case_dir() / 'study.json'
        original = source.read_bytes()
        try:
            study = json.loads(original)
            del study['synthetic']
            source.write_text(json.dumps(study, ensure_ascii=False), encoding='utf-8')
            _, calculated, _ = to_evidence(example_plan('independent_groups'))
            self.assertFalse(any('Observations are declared synthetic' in line for line in calculated['warnings']))
            analysis = c.get_record(calculated['analysis_id'])['payload']
            paragraph = ''.join(w._standard_paragraphs(analysis, c.get_study())['limitations'])
            self.assertIn('来源真实性', paragraph)
            self.assertNotIn('输入明确标注为合成', paragraph)
        finally:
            source.write_bytes(original)

    def test_unsupported_or_unfounded_design_returns_clarification(self):
        plan = example_plan('independent_groups')
        del plan['analysis']['design_evidence']
        self.assertTrue(w.approve_workflow(c.get_study()['study_id'], plan)['clarification_required'])
        plan = example_plan('independent_groups')
        plan['analysis']['design_evidence']['quote'] = 'invented design evidence'
        self.assertTrue(w.approve_workflow(c.get_study()['study_id'], plan)['clarification_required'])
        plan = example_plan('independent_groups')
        plan['analysis']['design'] = 'multilevel_longitudinal'
        self.assertTrue(w.approve_workflow(c.get_study()['study_id'], plan)['clarification_required'])


if __name__ == '__main__':
    unittest.main()
