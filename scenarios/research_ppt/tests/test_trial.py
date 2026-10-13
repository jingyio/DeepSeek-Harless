"""双路试用的费用与质量门槛；无模拟Provider，不在本机执行。"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest

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
                                      (21, 40, 8000), (3, 41, 8000), (3, 40, 8001)):
            with self.subTest(budget=budget, steps=steps, output=output):
                with self.assertRaises(ValueError):
                    trial.validate_options(budget, steps, output)

    def test_candidate_and_active_are_mutually_exclusive_before_preparing_jobs(self):
        with self.assertRaisesRegex(ValueError, '不能同时'):
            trial.prepare_trial([], '科研汇报', 4, use_active_learning=True, candidate_version='a' * 32)


class TrialQualityTest(unittest.TestCase):
    def setUp(self):
        (trial.ROOT / '.local').mkdir(exist_ok=True)
        self.area = tempfile.TemporaryDirectory(prefix='trial-regression-', dir=trial.ROOT / '.local')
        self.addCleanup(self.area.cleanup)
        self.directory = Path(self.area.name)

    def test_existing_ppt_file_is_not_delivery_evidence(self):
        (self.directory / 'orphan.pptx').write_bytes(b'existing-but-not-delivered')
        self.assertEqual(trial.verified_artifacts([], self.directory), [])

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


if __name__ == '__main__':
    unittest.main()
