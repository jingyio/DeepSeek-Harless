"""公共运行记账与依赖快照；账本夹具不作真实 API 费用证据。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scenarios.research_ppt import accounting
from scenarios.research_ppt import runtime_snapshot as runtime


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n', encoding='utf-8')


class RunAccountingTests(unittest.TestCase):
    def setUp(self):
        (accounting.ROOT / '.local').mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=accounting.ROOT / '.local')
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)

    def run_ledger(self, name, metrics, rows):
        run = self.area / name
        run.mkdir()
        if metrics is not None:
            write(run / 'metrics.json', metrics)
        (run / 'cost-ledger.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        return run

    def test_complete_ledger_counts_all_requests_and_keeps_invoice_unknown(self):
        run = self.run_ledger('complete', {'upstream_requests': 1, 'budget_accounted_usd': 0.01}, [{
            'request_id': 1, 'response_status': 200, 'observed_peak_usd': 0.01,
            'response_usage': {'prompt_cache_miss_tokens': 10, 'prompt_cache_hit_tokens': 5, 'completion_tokens': 4, 'total_tokens': 19}}])
        row = accounting.collect_accounting(run)
        self.assertEqual(row['paid_model_requests'], 1)
        self.assertEqual(row['tokens']['total_tokens'], 19)
        self.assertEqual(row['proxy_observed_estimate_usd'], 0.01)
        self.assertIsNone(row['actual_invoice_usd'])
        self.assertIn('cost-ledger.jsonl', row['raw_file_sha256'])

    def test_crashed_or_incomplete_run_keeps_partial_evidence_unknown_cost(self):
        run = self.run_ledger('crashed', None, [{'request_id': 1, 'response_status': 502, 'observed_peak_usd': None, 'response_usage': {}}])
        row = accounting.collect_accounting(run)
        self.assertIsNone(row['paid_model_requests'])
        self.assertEqual(row['observed_request_subtotal'], 1)
        self.assertIsNone(row['proxy_observed_estimate_usd'])
        self.assertFalse(row['request_accounting_complete'])
        self.assertEqual(row['upstream_failures'], 1)

    def test_partial_usage_does_not_turn_unknown_tokens_into_zero(self):
        ledger = [
            {'request_id': 1, 'response_usage': {'prompt_cache_miss_tokens': 10, 'prompt_cache_hit_tokens': 5,
                                               'completion_tokens': 4, 'total_tokens': 19}},
            {'request_id': 2, 'response_status': 502, 'response_usage': {}},
        ]
        row = accounting.token_totals(ledger, {})
        self.assertFalse(row['token_accounting_complete'])
        self.assertTrue(all(value is None for value in row['tokens'].values()))
        self.assertEqual(row['ledger_observed_subtotals']['total_tokens'], 19)
        self.assertEqual(row['ledger_observed_subtotals']['prompt_cache_hit_tokens'], 5)

    def test_seed_revision_and_failed_attempts_are_all_aggregated(self):
        for name, phase, requests, dollars in [('seed', 'seed', 3, 0.02), ('revision-one', 'revision', 2, 0.01), ('revision-failed', 'revision', 1, 0.03)]:
            write(self.area / name / 'result.json', {'phase': phase, 'model_call_enabled': True, 'returncode': 0 if name != 'revision-failed' else 2,
                'status': 'failed_attempt' if name == 'revision-failed' else 'runtime_completed_quality_not_reviewed', 'elapsed_seconds': 2,
                'accounting_complete': True, 'accounting': [{'paid_model_requests': requests, 'observed_request_subtotal': requests,
                    'proxy_observed_estimate_usd': dollars, 'proxy_budget_accounted_usd': dollars,
                    'tokens': {'prompt_cache_miss_tokens': 10, 'prompt_cache_hit_tokens': 5, 'completion_tokens': 4, 'total_tokens': 19}}]})
        value = accounting.aggregate_attempts(self.area, experiment_id='user-trial-fixture')
        self.assertEqual(value['paid_model_requests'], 6)
        self.assertAlmostEqual(value['proxy_observed_estimate_usd'], 0.06)
        self.assertEqual(value['all_attempts_elapsed_seconds'], 6)
        self.assertEqual(value['tokens']['total_tokens'], 57)
        self.assertEqual(len(value['phase_attempts']), 3)
        self.assertEqual(value['quality'], 'not_reviewed')
        self.assertEqual(value['experiment_id'], 'user-trial-fixture')

    def test_preview_is_separate_and_unknown_paid_attempt_is_not_zero(self):
        write(self.area / 'preview' / 'result.json', {'phase': 'seed', 'status': 'preview', 'returncode': 0,
            'model_call_enabled': False, 'elapsed_seconds': 1, 'accounting': [], 'accounting_complete': True})
        value = accounting.aggregate_attempts(self.area)
        self.assertEqual(value['paid_model_requests'], 0)
        self.assertEqual(value['phase_attempts'][0]['status'], 'preview')
        self.assertNotIn('experiment_id', value,'通用运行记录不绑定历史轮次')
        write(self.area / 'failed' / 'result.json', {'phase': 'revision', 'status': 'failed_attempt', 'returncode': -11,
            'model_call_enabled': True, 'elapsed_seconds': 1, 'accounting': [], 'accounting_complete': False})
        value = accounting.aggregate_attempts(self.area)
        self.assertIsNone(value['paid_model_requests'])
        self.assertIsNone(value['proxy_observed_estimate_usd'])
        self.assertFalse(value['accounting_complete'])


class RuntimeSnapshotTests(unittest.TestCase):
    def test_wrapper_and_actual_node_are_distinct_and_optional_provenance_is_hashed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / '.local/node-compat/bin/node'
            preload = root / '.local/node-compat/warm-report.cjs'
            actual = root / '.local/node-runtimes/test/bin/node'
            for path, contents in [(wrapper, 'wrapper-recipe'), (preload, 'private-preload'), (actual, 'actual-node')]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding='utf-8')
            evidence = root / '.local/run-diagnosis/node-wrapper-evidence.json'
            write(evidence, {'scope': 'project-private-node-wrapper', 'node': 'test-runtime',
                'reason': 'private compatibility recipe', 'changes': ['project PATH wrapper'],
                'not_changed': ['global environment'], 'wrapper_sha256': runtime.file_hash(wrapper),
                'preload_sha256': runtime.file_hash(preload), 'environment': {'SECRET': 'must-not-be-copied'}})
            result = SimpleNamespace(returncode=0, stdout=json.dumps({'execPath': str(actual), 'version': 'v22.23.2'}))
            with patch.object(runtime, 'ROOT', root), patch.object(runtime.shutil, 'which', return_value=str(wrapper)), patch.object(runtime.subprocess, 'run', return_value=result):
                observed = runtime.node_runtime_snapshot()
                provenance = runtime.node_compat_provenance(evidence)
                self.assertEqual(observed['path_selected']['sha256'], runtime.file_hash(wrapper))
                self.assertEqual(observed['process_executable']['sha256'], runtime.file_hash(actual))
                self.assertTrue(observed['selection_differs_from_process'])
                self.assertEqual(observed['process_version'], 'v22.23.2')
                self.assertEqual(provenance['evidence_sha256'], runtime.file_hash(evidence))
                self.assertTrue(provenance['files']['preload']['matches_declared_sha256'])
                self.assertNotIn('must-not-be-copied', json.dumps(provenance))
                self.assertEqual(runtime.node_compat_provenance()['status'], 'not_configured')
                preload.write_text('changed-recipe', encoding='utf-8')
                changed = runtime.node_compat_provenance(evidence)
                self.assertFalse(changed['files']['preload']['matches_declared_sha256'])

    def test_unconfigured_snapshot_does_not_read_a_historical_evidence_file(self):
        with patch.object(runtime, 'file_hash') as hash_file:
            value = runtime.node_compat_provenance()
            hash_file.assert_not_called()
        self.assertIsNone(value['evidence_path'])
        self.assertIsNone(value['evidence_sha256'])
        self.assertEqual(value['status'], 'not_configured')

    def test_explicit_compat_evidence_cannot_read_outside_private_project(self):
        with TemporaryDirectory() as directory, patch.object(runtime, 'ROOT', Path(directory)):
            with self.assertRaises(ValueError):
                runtime.node_compat_provenance('public-evidence.json')


if __name__ == '__main__':
    unittest.main()
