"""双路试用的费用与质量门槛；无模拟Provider，不在本机执行。"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scenarios.research_ppt import trial


class TrialAccountingTest(unittest.TestCase):
    def test_effectful_delivery_result_is_counted_without_read_only_contract(self):
        name = 'mcp__ppt__render_delivery'
        value = {'delivered': True, 'validation_id': 'actual', 'path': '/private/deck.pptx',
                 'file_sha256': '0' * 64}
        events = [{'seq': 1, 'type': 'tool/call', 'data': {'callId': 'call-1', 'name': name, 'arguments': '{}'}},
                  {'seq': 2, 'type': 'tool/result', 'data': {'message': {'source': {'callId': 'call-1'},
                   'content': [{'type': 'tool-result', 'isError': False,
                                'content': [{'type': 'text', 'text': json.dumps(value)}]}]}}}]
        summary, receipts = trial.summarize_tools(events, [name])
        self.assertEqual(summary['tool_calls'], 1)
        self.assertEqual(summary['failed_or_unparseable_tool_results'], 0)
        self.assertEqual(receipts, [value])

    def test_success_and_failed_request_remain_in_budget(self):
        ledger = [
            {'request_id': 1, 'response_status': 200, 'observed_peak_usd': .1,
             'reserved_upper_usd': .4, 'response_usage': {
                 'prompt_tokens': 100, 'prompt_cache_miss_tokens': 20,
                 'prompt_cache_hit_tokens': 80, 'completion_tokens': 10, 'total_tokens': 110}},
            {'request_id': 2, 'response_status': 502, 'observed_peak_usd': None,
             'reserved_upper_usd': .4, 'response_usage': {}},
        ]
        value = trial.summarize_ledger(ledger, {'upstream_requests': 2, 'budget_accounted_usd': .5})
        self.assertEqual(value['upstream_requests'], 2)
        self.assertEqual(value['upstream_failed_requests'], 1)
        self.assertFalse(value['usage_complete'])
        self.assertIsNone(value['observed_proxy_usd'])
        self.assertEqual(value['observed_proxy_subtotal_usd'], .1)
        self.assertEqual(value['budget_accounted_usd'], .5)
        self.assertEqual(value['budget_accounted_observed_subtotal_usd'], .5)
        self.assertIsNone(value['recovery_cost_usd'])
        self.assertIsNone(value['provider_bill_usd'])

    def test_cache_miss_hit_and_output_do_not_get_merged(self):
        ledger = [{'request_id': 1, 'response_status': 200, 'observed_peak_usd': .1,
                   'reserved_upper_usd': .4, 'response_usage': {
                       'prompt_tokens': 100, 'prompt_cache_miss_tokens': 20,
                       'prompt_cache_hit_tokens': 80, 'completion_tokens': 10, 'total_tokens': 110}}]
        value = trial.summarize_ledger(ledger, {'upstream_requests': 1, 'budget_accounted_usd': .1})
        self.assertTrue(value['usage_complete'])
        self.assertEqual(value['prompt_cache_miss_tokens'], 20)
        self.assertEqual(value['prompt_cache_hit_tokens'], 80)
        self.assertEqual(value['completion_tokens'], 10)
        self.assertEqual(value['observed_proxy_usd'], .1)

    def test_missing_final_metrics_cannot_claim_total_cost(self):
        ledger = [{'request_id': 1, 'response_status': 200, 'observed_peak_usd': .1,
                   'reserved_upper_usd': .4, 'response_usage': {
                       'prompt_cache_miss_tokens': 20, 'prompt_cache_hit_tokens': 80,
                       'completion_tokens': 10, 'total_tokens': 110}}]
        value = trial.summarize_ledger(ledger, {})
        self.assertIsNone(value['upstream_requests'])
        self.assertFalse(value['request_count_matches_ledger'])
        self.assertIsNone(value['observed_proxy_usd'])
        self.assertIsNone(value['budget_accounted_usd'])
        self.assertEqual(value['ledger_requests'], 1)

    def test_budget_must_be_finite_and_output_bounded(self):
        for budget, steps, output in ((float('nan'), 40, 8000), (0, 40, 8000),
                                      (21, 40, 8000), (3, 61, 8000), (3, 40, 8001)):
            with self.subTest(budget=budget, steps=steps, output=output):
                with self.assertRaises(ValueError):
                    trial.validate_options(budget, steps, output)
        trial.validate_options(3, 60, 8000)

    def test_candidate_and_active_are_mutually_exclusive_before_preparing_jobs(self):
        with self.assertRaisesRegex(ValueError, '不能同时'):
            trial.prepare_trial([], '科研汇报', 4, use_active_learning=True, candidate_version='a' * 32)

    def test_invalid_explicit_figure_contract_is_rejected_before_preparing_jobs(self):
        for minimum in (True, -1, 1.5, '2', 5):
            with self.subTest(minimum=minimum), self.assertRaisesRegex(ValueError, 'minimum_original_figures'):
                trial.prepare_trial([], '科研汇报', 4, minimum_original_figures=minimum)

    def test_host_delivery_is_counted_only_with_matching_script_audit(self):
        name = 'mcp__ppt__render_deck'
        args = {'plan': {'title': '合成回执守卫诊断', 'slides': []}}
        execution = {'schema_version': 1, 'strategy': 'host_delivery', 'policy_sha256': 'a' * 64,
                     'script_execution_id': 'diagnostic-host-call', 'request_tool': 'render_deck',
                     'host_script': 'render_delivery', 'arguments_sha256': trial.digest(args),
                     'mechanism': 'ordinary_bounded_host_script', 'model_selected_script': False}
        value = {'delivered': True, 'validation_id': 'diagnostic', 'path': '/private/deck.pptx',
                 'file_sha256': '0' * 64}
        receipt = {**value, 'execution_policy': execution}
        events = [{'type': 'tool/call', 'data': {'callId': 'call-1', 'name': name, 'arguments': json.dumps(args)}},
                  {'type': 'tool/result', 'data': {'message': {'source': {'callId': 'call-1'},
                   'content': [{'type': 'tool-result', 'isError': False,
                                'content': [{'type': 'text', 'text': json.dumps(receipt)}]}]}}}]
        summary, receipts = trial.summarize_tools(events, [name])
        self.assertEqual(receipts, [])
        policy = {'strategy': 'host_delivery', 'policy_sha256': 'a' * 64,
                  'events': [{'kind': 'host_script_started', **execution},
                             {'kind': 'host_script_completed', **execution,
                              'delivered': True, 'result_sha256': trial.digest(value)}]}
        summary, receipts = trial.summarize_tools(events, [name], policy)
        self.assertEqual(receipts, [receipt])
        self.assertEqual(summary['host_script_delivered_count'], 1)
        self.assertEqual(summary['successful_model_selected_composed_calls'], 0)

    def test_repaired_delivery_binds_both_host_and_final_adapter_receipts(self):
        import copy
        name = 'mcp__ppt__repair_pending_plan'
        args = {'draft_id': 'diagnostic-draft', 'version_sha256': 'b' * 64,
                'updates': [{'page': 2, 'changes': {'title': '明确局部修改'}}]}
        execution = {'schema_version': 1, 'strategy': 'host_delivery', 'policy_sha256': 'a' * 64,
                     'script_execution_id': 'diagnostic-repair', 'request_tool': 'repair_pending_plan',
                     'host_script': 'render_delivery', 'arguments_sha256': trial.digest(args),
                     'mechanism': 'ordinary_bounded_host_script', 'model_selected_script': False}
        host_result = {'delivered': True, 'validation_id': 'diagnostic', 'path': '/private/deck.pptx',
                       'file_sha256': '0' * 64}
        receipt = {**host_result, 'execution_policy': execution,
                   'pending_plan': {'draft_id': args['draft_id'], 'status': 'delivered'},
                   'local_repair': {'changed_pages': [2]}, 'automatic_retry': False}
        events = [{'type': 'tool/call', 'data': {'callId': 'repair-1', 'name': name, 'arguments': json.dumps(args)}},
                  {'type': 'tool/result', 'data': {'message': {'source': {'callId': 'repair-1'},
                   'content': [{'type': 'tool-result', 'isError': False,
                                'content': [{'type': 'text', 'text': json.dumps(receipt)}]}]}}}]
        policy = {'strategy': 'host_delivery', 'policy_sha256': 'a' * 64,
                  'events': [{'kind': 'host_script_started', **execution},
                             {'kind': 'host_script_completed', **execution, 'delivered': True,
                              'result_sha256': trial.digest(host_result)}]}
        self.assertEqual(trial.summarize_tools(events, [name], policy)[1], [])
        policy['events'].append({'kind': 'adapter_tool', 'name': 'repair_pending_plan',
                                 'arguments': copy.deepcopy(args), 'result': copy.deepcopy(receipt)})
        summary, receipts = trial.summarize_tools(events, [name], policy)
        self.assertEqual(receipts, [receipt])
        self.assertEqual(summary['host_script_delivered_count'], 1)
        for field, changed in [('file_sha256', 'f' * 64), ('pending_plan', {'status': 'pending'}),
                               ('local_repair', {'changed_pages': [3]}), ('automatic_retry', True)]:
            with self.subTest(field=field):
                altered = {**receipt, field: changed}
                self.assertFalse(trial._host_receipt(altered, name, args, policy))
        for kind in ('host_script_started', 'host_script_completed', 'adapter_tool'):
            with self.subTest(missing=kind):
                incomplete = {**policy, 'events': [row for row in policy['events'] if row['kind'] != kind]}
                self.assertFalse(trial._host_receipt(receipt, name, args, incomplete))
        forged_policy = copy.deepcopy(policy)
        forged_policy['events'][-1]['result']['file_sha256'] = 'f' * 64
        self.assertFalse(trial._host_receipt({**receipt, 'file_sha256': 'f' * 64}, name, args, forged_policy))


class TrialQualityTest(unittest.TestCase):
    def setUp(self):
        (trial.ROOT / '.local').mkdir(exist_ok=True)
        self.area = tempfile.TemporaryDirectory(prefix='trial-regression-', dir=trial.ROOT / '.local')
        self.addCleanup(self.area.cleanup)
        self.directory = Path(self.area.name)

    def test_existing_ppt_file_is_not_delivery_evidence(self):
        (self.directory / 'orphan.pptx').write_bytes(b'existing-but-not-delivered')
        self.assertEqual(trial.verified_artifacts([], self.directory), [])

    def test_explicit_figure_contract_is_shared_frozen_and_prompt_schema_stays_compatible(self):
        import fitz
        source = self.directory / 'figure-contract.pdf'
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((50, 70), 'Real PDF bytes for a no-model contract preview.')
            pdf.save(source)
        path = trial.prepare_trial([source], '不从这句话猜图数', 2,
                                   feedback_store=self.directory / 'figure-contract-feedback',
                                   minimum_original_figures=2)
        _, data = trial.checked_trial(path)
        self.assertEqual(data['task']['minimum_original_figures'], 2)
        for group in trial.GROUPS:
            row = data['groups'][group]
            self.assertEqual(trial.read_json(Path(row['job']))['minimum_original_figures'], 2)
            self.assertEqual(trial.read_json(Path(row['invocation']))['minimum_original_figures'], 2)
            prompt = Path(row['prompt']).read_text(encoding='utf-8')
            task_text = prompt.split('\n本次任务：\n', 1)[1].split('\n本次执行方式：', 1)[0]
            task = json.loads(task_text)
            self.assertEqual(set(task), {'instruction', 'slides', 'template', 'operation', 'inputs'})
            self.assertIn('至少 2 张不同完整原图', task['instruction'])
        changed = trial.read_json(Path(data['groups']['optimized']['job']))
        changed['minimum_original_figures'] = 0
        trial.cli.save(Path(data['groups']['optimized']['job']), changed)
        data['groups']['optimized']['job_sha256'] = trial.file_hash(Path(data['groups']['optimized']['job']))
        changed_path = self.directory / 'changed-contract-trial.json'
        trial.save_new(changed_path, data)
        with self.assertRaisesRegex(ValueError, '冻结值'):
            trial.checked_trial(changed_path)

    def prompt_row(self, filename, task, strategy):
        path = self.directory / filename
        shared = '真实稳定科研指导\n本次任务：\n' + json.dumps(task, ensure_ascii=False)
        path.write_text(shared + '\n本次执行方式：' + strategy, encoding='utf-8')
        return {'prompt': str(path), 'prompt_sha256': trial.file_hash(path),
                'shared_prompt_sha256': hashlib.sha256(shared.encode()).hexdigest(), 'execution': strategy}

    def test_different_tasks_keep_stable_prefix_and_distinct_full_hash(self):
        first = self.prompt_row('first.md', {'instruction': '论文A'}, 'steps')
        second = self.prompt_row('second.md', {'instruction': '论文B'}, 'steps')
        first_evidence = trial.prompt_feedback_evidence(first)
        second_evidence = trial.prompt_feedback_evidence(second)
        self.assertEqual(first_evidence['prefix_sha256'], second_evidence['prefix_sha256'])
        self.assertNotEqual(first_evidence['sha256'], second_evidence['sha256'])
        self.assertNotEqual(first_evidence['shared_prompt_sha256'], second_evidence['shared_prompt_sha256'])

    def test_paired_strategies_share_actual_task_hash(self):
        first = self.prompt_row('baseline.md', {'instruction': '同一任务'}, 'steps')
        second = self.prompt_row('optimized.md', {'instruction': '同一任务'}, 'composed')
        first_evidence = trial.prompt_feedback_evidence(first)
        second_evidence = trial.prompt_feedback_evidence(second)
        self.assertEqual(first_evidence['shared_prompt_sha256'], second_evidence['shared_prompt_sha256'])
        self.assertNotEqual(first_evidence['sha256'], second_evidence['sha256'])
        Path(second['prompt']).write_text('替换后的提示', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '版本'):
            trial.prompt_feedback_evidence(second)

    def test_feedback_retains_candidate_and_prompt_evidence(self):
        row = self.prompt_row('optimized.md', {'instruction': '同一任务'}, 'composed')
        evidence = self.directory / 'receipt.json'
        evidence.write_text('{}', encoding='utf-8')
        data = {'trial_id': 'trial-pair', 'task': {'inputs': [{'document_id': 'doc_1', 'version_sha256': '1' * 64}]},
                'groups': {'optimized': row}, 'model': 'deepseek-flash', 'provider': 'deepseek-official',
                'code': {'sha256': '2' * 64, 'files': {}}, 'active_learning': None}
        data['task']['template'] = 'lab'
        result = {'model_run_directory': None, 'tool_schema_sha256': '3' * 64,
                  'mechanical_delivery_verified': False, 'elapsed_seconds': 1,
                  'candidate_version': 'candidate-new', 'effective_mode': 'execute'}
        record = trial.feedback_record(data, 'optimized', result, evidence)
        self.assertEqual(record['candidate_version'], 'candidate-new')
        self.assertEqual(record['execution_strategy'], 'composed')
        self.assertEqual(record['versions']['prompt_sha256'], trial.file_hash(Path(row['prompt'])))
        self.assertEqual(record['versions']['prompt_prefix_sha256'], record['prompt_evidence']['prefix_sha256'])
        self.assertEqual(record['shared_prompt_sha256'], record['prompt_evidence']['shared_prompt_sha256'])
        self.assertEqual(record['quality']['scientific'], 'pending')
        self.assertFalse(record['consent']['learn'])

    def test_tampered_delivered_file_rejects_receipt(self):
        target = self.directory / 'deck.pptx'
        target.write_bytes(b'changed')
        receipt = {'validation_id': 'validation-actual', 'path': str(target),
                   'file_sha256': '0' * 64, 'artifacts': []}
        report = {'passed': True, 'deck_id': None, 'file_sha256': '0' * 64,
                  'input_version': None, 'artifacts': []}
        self.assertEqual(trial.verified_artifacts([receipt], self.directory, {'validation-actual': report}), [])

    def test_failed_validation_does_not_accept_matching_files(self):
        target = self.directory / 'deck.pptx'
        target.write_bytes(b'unchanged')
        receipt = {'validation_id': 'validation-actual', 'path': str(target),
                   'file_sha256': trial.file_hash(target), 'artifacts': []}
        report = {'passed': False, 'deck_id': None, 'file_sha256': trial.file_hash(target),
                  'input_version': None, 'artifacts': []}
        self.assertEqual(trial.verified_artifacts([receipt], self.directory, {'validation-actual': report}), [])

    def prepared_review(self, *, mechanical=True, pending=False):
        path = self.directory / 'trial.json'
        trial.save_new(path, {'trial_id': 'review-task'})
        account = {'usage_complete': True, 'unsettled_request_count': 0, 'observed_proxy_usd': .1}
        report = {'trial_sha256': trial.file_hash(path), 'results': {
            group: {'mechanical_delivery_verified': mechanical, 'accounting': dict(account)} for group in trial.GROUPS}}
        report['results']['optimized']['accounting']['observed_proxy_usd'] = .08
        trial.save_new(self.directory / 'comparison.json', report)
        review = {'trial_id': 'review-task', 'reviewer': '课题组评审人', 'groups': {
            group: {**{field: True for field in trial.REVIEW_FIELDS}, 'revision_minutes': None} for group in trial.GROUPS}}
        if pending:
            review['groups']['optimized']['scientific_facts'] = None
        review_path = self.directory / 'review.json'
        trial.save_new(review_path, review)
        return path, review_path

    def test_pending_science_prevents_same_quality_claim(self):
        path, review = self.prepared_review(pending=True)
        result = trial.read_json(trial.review_trial(path, review))
        self.assertFalse(result['qualified']['optimized'])
        self.assertIsNone(result['same_quality_model_cost_comparison'])
        self.assertFalse(result['automatic_rsi_promotion'])

    def test_manual_true_cannot_override_missing_mechanical_evidence(self):
        path, review = self.prepared_review(mechanical=False)
        with self.assertRaisesRegex(ValueError, '机械交付'):
            trial.review_trial(path, review)

    def test_qualified_proxy_comparison_keeps_original_and_unknowns(self):
        path, review = self.prepared_review()
        original = trial.file_hash(self.directory / 'comparison.json')
        result = trial.read_json(trial.review_trial(path, review))
        self.assertAlmostEqual(result['same_quality_model_cost_comparison']['proxy_cost_reduction_fraction'], .2)
        self.assertEqual(original, trial.file_hash(self.directory / 'comparison.json'))
        self.assertIsNone(result['manual_revision_minutes']['baseline'])

    def test_ai_review_comparison_cannot_be_labelled_independent_human(self):
        path, review_path = self.prepared_review()
        review = trial.read_json(review_path)
        review.update(reviewer='ai-assisted', reviewer_kind='ai-assisted')
        review_path.write_text(json.dumps(review), encoding='utf-8')
        result = trial.read_json(trial.review_trial(path, review_path))
        self.assertFalse(result['independent_human_review'])
        self.assertIn('AI辅助', result['same_quality_model_cost_comparison']['scope'])
        self.assertFalse(result['automatic_rsi_promotion'])

    def test_ai_reviewer_cannot_override_kind_to_human(self):
        path, review_path = self.prepared_review()
        review = trial.read_json(review_path)
        review.update(reviewer='ai-assisted', reviewer_kind='human')
        review_path.write_text(json.dumps(review), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '改称独立人评'):
            trial.review_trial(path, review_path)

    def test_candidate_checked_preview_uses_staging_not_active(self):
        # Private protocol fixtures check bootstrap only, never cloud quality.
        source = self.directory / 'source.pdf'; source.write_bytes(b'fixture-not-a-real-pdf')
        candidate = {'version': 'a' * 32, 'manifest': 'unused', 'manifest_sha256': 'b' * 64,
                     'stage': 'candidate_evaluation', 'quality_cost_promoted': False}
        groups = {}
        for group, execution in [('baseline', 'baseline_steps'), ('optimized', 'host_delivery')]:
            folder = self.directory / group; folder.mkdir()
            job = folder / 'job.json'
            trial.save_new(job, {'allow_output': True, 'allow_rsi': False,
                                'document_cache': True, 'execution_policy': {'schema_version': 1, 'strategy': execution},
                                'inputs': [{'path': str(source), 'version_sha256': trial.file_hash(source)}]})
            scenario = folder / 'scenario.json'; trial.save_new(scenario, {'allowed_tools': []})
            prompt = folder / 'prompt.md'; prompt.write_text('fixture', encoding='utf-8')
            invocation = folder / 'invocation.json'; trial.save_new(invocation, {})
            groups[group] = {'budget_cap_usd': 1.5, 'execution': execution, 'configured_tool_order': []}
            for key, file in [('job', job), ('scenario', scenario), ('prompt', prompt), ('invocation', invocation)]:
                groups[group].update({key: str(file), key + '_sha256': trial.file_hash(file)})
        data = {'schema_version': 1, 'groups': groups, 'order': list(trial.GROUPS), 'rsi_enabled': True,
                'reasoning_effort': 'off', 'context_compression': 'off', 'budget_cap_usd_total': 3,
                'max_agent_steps_per_group': 60, 'max_output_tokens_per_request': 8000,
                'allow_output': True, 'document_cache': True, 'execution_policy': 'controlled',
                'code': {'sha256': 'c' * 64}, 'active_learning': candidate,
                'feedback_store': str(self.directory / 'feedback'), 'candidate_evaluation': True}
        path = self.directory / 'candidate-trial.json'; trial.save_new(path, data)
        with patch.object(trial, 'code_snapshot', return_value={'sha256': 'c' * 64}), \
                patch.object(trial.FeedbackStore, 'candidate_manifest', return_value=candidate) as staging, \
                patch.object(trial.FeedbackStore, 'active_manifest', side_effect=AssertionError('must not load active')):
            _, frozen = trial.checked_trial(path)
            self.assertTrue(frozen['candidate_evaluation'])
            staging.assert_called_once_with('a' * 32)


if __name__ == '__main__':
    unittest.main()
