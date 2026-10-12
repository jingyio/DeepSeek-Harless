"""V9 记账/预览边界；账本夹具不作真实 API 费用证据。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scenarios.research_ppt import experiment_v9 as experiment


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n', encoding='utf-8')


class V9AccountingTests(unittest.TestCase):
    def setUp(self):
        (experiment.ROOT / '.local').mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=experiment.ROOT / '.local')
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)

    def run_ledger(self, name, metrics, rows):
        run = self.area / name; run.mkdir()
        if metrics is not None:
            write(run / 'metrics.json', metrics)
        (run / 'cost-ledger.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        return run

    def test_complete_ledger_counts_all_requests_and_keeps_invoice_unknown(self):
        run = self.run_ledger('complete', {'upstream_requests': 1, 'budget_accounted_usd': 0.01}, [{
            'request_id': 1, 'response_status': 200, 'observed_peak_usd': 0.01,
            'response_usage': {'prompt_cache_miss_tokens': 10, 'prompt_cache_hit_tokens': 5, 'completion_tokens': 4, 'total_tokens': 19}}])
        row = experiment.collect_accounting(run)
        self.assertEqual(row['paid_model_requests'], 1)
        self.assertEqual(row['tokens']['total_tokens'], 19)
        self.assertEqual(row['proxy_observed_estimate_usd'], 0.01)
        self.assertIsNone(row['actual_invoice_usd'])
        self.assertIn('cost-ledger.jsonl', row['raw_file_sha256'])

    def test_crashed_or_incomplete_run_keeps_partial_evidence_unknown_cost(self):
        run = self.run_ledger('crashed', None, [{'request_id': 1, 'response_status': 502, 'observed_peak_usd': None, 'response_usage': {}}])
        row = experiment.collect_accounting(run)
        self.assertIsNone(row['paid_model_requests'])
        self.assertEqual(row['observed_request_subtotal'], 1)
        self.assertIsNone(row['proxy_observed_estimate_usd'])
        self.assertFalse(row['request_accounting_complete'])
        self.assertEqual(row['upstream_failures'], 1)

    def test_seed_revision_and_failed_attempts_are_all_aggregated(self):
        for name, phase, requests, dollars in [('seed', 'seed', 3, 0.02), ('revision-one', 'revision', 2, 0.01), ('revision-failed', 'revision', 1, 0.03)]:
            write(self.area / name / 'result.json', {'phase': phase, 'model_call_enabled': True, 'returncode': 0 if name != 'revision-failed' else 2,
                'status': 'failed_attempt' if name == 'revision-failed' else 'runtime_completed_quality_not_reviewed', 'elapsed_seconds': 2,
                'accounting_complete': True, 'accounting': [{'paid_model_requests': requests, 'observed_request_subtotal': requests,
                    'proxy_observed_estimate_usd': dollars, 'proxy_budget_accounted_usd': dollars,
                    'tokens': {'prompt_cache_miss_tokens': 10, 'prompt_cache_hit_tokens': 5, 'completion_tokens': 4, 'total_tokens': 19}}]})
        value = experiment.aggregate_attempts(self.area)
        self.assertEqual(value['paid_model_requests'], 6)
        self.assertAlmostEqual(value['proxy_observed_estimate_usd'], 0.06)
        self.assertEqual(value['all_attempts_elapsed_seconds'], 6)
        self.assertEqual(value['tokens']['total_tokens'], 57)
        self.assertEqual(len(value['phase_attempts']), 3)
        self.assertEqual(value['quality'], 'not_reviewed')

    def test_preview_is_separate_and_unknown_paid_attempt_is_not_zero(self):
        write(self.area / 'preview' / 'result.json', {'phase': 'seed', 'status': 'preview', 'returncode': 0,
            'model_call_enabled': False, 'elapsed_seconds': 1, 'accounting': [], 'accounting_complete': True})
        value = experiment.aggregate_attempts(self.area)
        self.assertEqual(value['paid_model_requests'], 0)
        self.assertEqual(value['phase_attempts'][0]['status'], 'preview')
        write(self.area / 'failed' / 'result.json', {'phase': 'revision', 'status': 'failed_attempt', 'returncode': -11,
            'model_call_enabled': True, 'elapsed_seconds': 1, 'accounting': [], 'accounting_complete': False})
        value = experiment.aggregate_attempts(self.area)
        self.assertIsNone(value['paid_model_requests'])
        self.assertIsNone(value['proxy_observed_estimate_usd'])
        self.assertFalse(value['accounting_complete'])


class V9RuntimeSnapshotTests(unittest.TestCase):
    def test_wrapper_and_actual_node_are_distinct_and_provenance_is_hashed(self):
        # 私有兼容运行时夹具，仅验证配置快照，不作服务器兼容性或费用证据。
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / '.local/node-compat/bin/node'
            preload = root / '.local/node-compat/warm-report.cjs'
            actual = root / '.local/node-runtimes/test/bin/node'
            for path, contents in [(wrapper, 'wrapper-recipe'), (preload, 'private-preload'), (actual, 'actual-node')]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding='utf-8')
            evidence = root / '.local/research-ppt/v9-quality-20261012/harness-diagnosis/node-wrapper-evidence.json'
            write(evidence, {'scope': 'project-private-node-wrapper', 'node': 'test-runtime',
                'reason': 'private compatibility recipe', 'changes': ['project PATH wrapper'],
                'not_changed': ['global environment'], 'wrapper_sha256': experiment.file_hash(wrapper),
                'preload_sha256': experiment.file_hash(preload), 'environment': {'SECRET': 'must-not-be-copied'}})
            result = SimpleNamespace(returncode=0, stdout=json.dumps({'execPath': str(actual), 'version': 'v22.23.2'}))
            with patch.object(experiment, 'ROOT', root), patch.object(experiment.shutil, 'which', return_value=str(wrapper)), patch.object(experiment.subprocess, 'run', return_value=result):
                observed = experiment.node_runtime_snapshot()
                provenance = experiment.node_compat_provenance()
                self.assertEqual(observed['path_selected']['sha256'], experiment.file_hash(wrapper))
                self.assertEqual(observed['process_executable']['sha256'], experiment.file_hash(actual))
                self.assertTrue(observed['selection_differs_from_process'])
                self.assertEqual(observed['process_version'], 'v22.23.2')
                self.assertEqual(provenance['evidence_sha256'], experiment.file_hash(evidence))
                self.assertTrue(provenance['files']['preload']['matches_declared_sha256'])
                self.assertNotIn('must-not-be-copied', json.dumps(provenance))
                preload.write_text('changed-recipe', encoding='utf-8')
                changed = experiment.node_compat_provenance()
                self.assertFalse(changed['files']['preload']['matches_declared_sha256'])


if __name__ == '__main__':
    unittest.main()
