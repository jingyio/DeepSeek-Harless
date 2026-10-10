from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from benchmarks.research_report_agent_v31.prepare_experiment import prepare, sha, HERE


class PreparationTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='v31-input-test-',dir=ROOT/'.local')
        self.addCleanup(self.tmp.cleanup)
        self.output=Path(self.tmp.name)/'experiment'
        self.before={path:sha(path) for path in (HERE.parent/'research_report_agent_v3').glob('*') if path.is_file()}
        self.result=prepare(self.output)

    def test_shared_policy_fresh_seed_real_hashes_and_no_semantic_answers(self):
        policy=(HERE/'statistics_continuation_policy.txt').read_text(encoding='utf8').strip()
        manifest=json.loads((self.output/'data/dataset_manifest.json').read_text(encoding='utf8'))
        self.assertEqual(len(manifest['cases']),7)
        for case in manifest['cases']:
            folder=self.output/'data/cases'/case['case_id']
            study=json.loads((folder/'study.json').read_text(encoding='utf8'))
            self.assertEqual(case['seed'],case['base_seed']+2000000)
            self.assertEqual(case['source_sha256'],{name:sha(folder/name) for name in ('data.csv','study.json','task.txt')})
            for file in ('task.txt','request.txt'):
                self.assertEqual((folder/file).read_text(encoding='utf8').count(policy),1)
            self.assertTrue(study['user_request'].endswith(policy))
            self.assertNotIn('benchmark_frozen_decisions',study)
            self.assertEqual(study['benchmark_execution_policy'],case['execution_policy'])
            self.assertNotIn('plan',study['benchmark_execution_policy'])
        self.assertTrue(manifest['execution_policy']['false_remains_valid_and_unchanged'])
        self.assertEqual(self.result['api_calls'],0)
        self.assertEqual(self.before,{path:sha(path) for path in self.before})

    def test_balanced_matrix_preview_uses_unchanged_v3_runtime(self):
        training=json.loads((self.output/'training-matrix.json').read_text(encoding='utf8'))
        evaluations=json.loads((self.output/'evaluation-matrix.json').read_text(encoding='utf8'))
        self.assertEqual(len(training),3)
        self.assertEqual(len(evaluations),16)
        for row in training+evaluations:
            self.assertTrue(row['name'].startswith('v31_'))
            self.assertTrue(row['case'].startswith('v3_'))
        for case in {row['case'] for row in evaluations}:
            rows=[row for row in evaluations if row['case']==case]
            self.assertEqual([row['mode'] for row in rows[:2]],list(reversed([row['mode'] for row in rows[2:]])))
        result=subprocess.run([sys.executable,str(HERE/'run_matrix.py'),'--matrix',str(self.output/'training-matrix.json'),
            '--data-root',str(self.output/'data'),'--experiment',str(self.output),
            '--budget-ledger',str(self.output/'unused-ledger.jsonl')],capture_output=True,text=True,check=True,encoding='utf8')
        preview=json.loads(result.stdout)
        self.assertEqual(preview['api_calls'],0)
        for command in preview['commands']:
            self.assertEqual(Path(command[1]).resolve(),(HERE.parent/'research_report_agent_v3/runner.py').resolve())
            self.assertEqual(command[command.index('--experiment-id')+1],'research-report-agent-v31-20261010')

    def test_refuse_overwrite_and_freeze_policy(self):
        with self.assertRaisesRegex(ValueError,'fresh'):
            prepare(self.output)
        protocol=json.loads((self.output/'preregistration.json').read_text(encoding='utf8'))
        self.assertEqual(protocol['runtime_benchmark_version'],3)
        self.assertEqual(protocol['main_runs_denominator'],16)
        self.assertEqual(protocol['dataset_manifest_sha256'],sha(self.output/'data/dataset_manifest.json'))
        self.assertEqual(protocol['training_matrix_sha256'],sha(self.output/'training-matrix.json'))


if __name__=='__main__':
    unittest.main()
