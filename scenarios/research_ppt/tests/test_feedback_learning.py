"""反馈/离线发布边界的合成诊断；不代表真实模型质量或费用收益。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scenarios.research_ppt import feedback_learning as learning


class FeedbackLearningTests(unittest.TestCase):
    def setUp(self):
        (learning.ROOT / '.local').mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=learning.ROOT / '.local')
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.store = learning.FeedbackStore(self.area / 'feedback')

    def record(self, **changes):
        value = {'schema_version': 1, 'run_id': 'diagnostic-run', 'task_identity': 'diagnostic-decision',
                 'pair_id': 'diagnostic-pair', 'group': 'baseline', 'consent': {'collect': True, 'learn': False},
                 'source_evidence': [{'source_id': 'anonymous-source', 'sha256': 'a' * 64}],
                 'versions': {key: None for key in learning.VERSION_FIELDS},
                 'quality': {'delivery': 'passed', 'scientific': 'pending', 'visual': 'pending',
                             'reviewer': 'unreviewed', 'revision_minutes': None},
                 'cost': {key: None for key in learning.COST_FIELDS}, 'identity_confirmed': False}
        value.update(changes)
        return value

    def prompt_record(self, name, *, instruction='解释原论文方法', strategy='steps', prefix='固定科研设计与来源要求', task=None):
        # 实际私有文件/manifest的协议夹具，只核验配置绑定，不假称真实云调用或认证成功。
        task = task or {'instruction': instruction, 'slides': 4, 'template': 'lab', 'operation': 'generate',
                        'inputs': [{'document_id': 'doc_1', 'name': 'source.pdf', 'version_sha256': 'a' * 64}]}
        shared = prefix + learning.TASK_PROMPT_MARKER + json.dumps(task, ensure_ascii=False)
        prompt = shared + learning.EXECUTION_PROMPT_MARKER + learning.STRATEGY_SUFFIXES[(task['operation'], strategy)]
        run = self.area / name
        run.mkdir()
        prompt_file = run / 'prompt.md'
        prompt_file.write_text(prompt, encoding='utf-8', newline='\n')
        full_sha = learning._hash(prompt_file)
        prefix_sha = learning.hashlib.sha256(prefix.encode()).hexdigest()
        shared_sha = learning.hashlib.sha256(shared.encode()).hexdigest()
        manifest = {'prompt_sha256': full_sha, 'question': prompt, 'fixture': True}
        (run / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        versions = {'model': 'deepseek-flash', 'provider': 'deepseek-official', 'reasoning_effort': 'off',
                    'tool_schema_sha256': 'b' * 64, 'template_sha256': 'c' * 64, 'runtime_sha256': 'd' * 64,
                    'prompt_sha256': full_sha, 'prompt_prefix_sha256': prefix_sha}
        return self.record(run_id=name, versions=versions, run_dir=str(run), execution_strategy=strategy,
                           shared_prompt_sha256=shared_sha,
                           prompt_evidence={'path': str(prompt_file), 'sha256': full_sha,
                                            'shared_prompt_sha256': shared_sha, 'prefix_sha256': prefix_sha})

    def test_independent_tasks_compare_actual_stable_prefix_not_full_task_prompt(self):
        rows = [self.prompt_record(name, instruction=instruction) for name, instruction in
                [('training-one', '解释方法A'), ('training-two', '比较方法B'), ('heldout-one', '汇报未见论文C')]]
        self.assertEqual(len({row['versions']['prompt_sha256'] for row in rows}), 3)
        self.assertEqual(len({row['versions']['prompt_prefix_sha256'] for row in rows}), 1)
        bindings = learning._require_compatible_prompts(rows)
        self.assertEqual(len(bindings), 3)
        self.assertEqual(len({binding['shared_prompt_sha256'] for binding in bindings}), 3)
        # 仅配置绑定可比，fixture仍不符合真实运行/质量认证门槛。
        self.assertFalse(self.store._eligibility(rows[0])[0])

    def test_paired_workflows_share_actual_task_and_only_strategy_suffix_differs(self):
        baseline = self.prompt_record('paired-base')
        optimized = self.prompt_record('paired-opt', strategy='composed')
        self.assertNotEqual(baseline['versions']['prompt_sha256'], optimized['versions']['prompt_sha256'])
        bindings = learning._require_compatible_prompts([baseline, optimized], paired=True)
        self.assertEqual(bindings[0]['task'], bindings[1]['task'])
        self.assertEqual(bindings[0]['shared_prompt_sha256'], bindings[1]['shared_prompt_sha256'])
        self.assertEqual(bindings[1]['execution_strategy'], 'composed')

    def test_changed_task_or_model_schema_cannot_hide_behind_same_prefix(self):
        baseline = self.prompt_record('unaltered-base')
        changed = self.prompt_record('different-task', instruction='只写摘要省略所有实验', strategy='composed')
        with self.assertRaisesRegex(ValueError, '真实题面'):
            learning._require_compatible_prompts([baseline, changed], paired=True)
        wrong_schema = self.prompt_record('different-schema')
        wrong_schema['versions']['tool_schema_sha256'] = 'e' * 64
        with self.assertRaisesRegex(ValueError, '工具'):
            learning._require_compatible_prompts([baseline, wrong_schema])

    def test_claimed_prefix_hash_is_checked_against_actual_bytes(self):
        baseline = self.prompt_record('fixed-prefix')
        altered = self.prompt_record('altered-prefix', prefix='另外一套改变了设计要求的前缀')
        altered['versions']['prompt_prefix_sha256'] = baseline['versions']['prompt_prefix_sha256']
        altered['prompt_evidence']['prefix_sha256'] = baseline['prompt_evidence']['prefix_sha256']
        with self.assertRaisesRegex(ValueError, '实际提示文件'):
            learning._require_compatible_prompts([baseline, altered])

    def test_full_prompt_manifest_and_declared_strategy_remain_binding(self):
        record = self.prompt_record('bound-full-prompt')
        manifest_path = Path(record['run_dir']) / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['question'] += '\n未经批准的额外要求'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '运行完整提示'):
            learning._require_compatible_prompts([record])
        manifest['question'] = Path(record['prompt_evidence']['path']).read_text(encoding='utf-8')
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        record['execution_strategy'] = 'composed'
        with self.assertRaisesRegex(ValueError, '策略后缀'):
            learning._require_compatible_prompts([record])

    def test_legacy_feedback_without_prefix_is_not_silently_migrated_or_certified(self):
        record = self.prompt_record('legacy-record')
        del record['versions']['prompt_prefix_sha256']
        with self.assertRaisesRegex(ValueError, 'versions'):
            self.store.collect(record)
        record['consent']['learn'] = True
        record['quality'].update(scientific='passed', visual='passed', reviewer='human')
        record['identity_confirmed'] = True
        eligible, reason = self.store._eligibility(record)
        self.assertFalse(eligible)
        self.assertEqual(reason, 'effective_configuration_incomplete')

    def test_explicit_consent_is_required_and_no_record_is_written(self):
        for consent in ({'collect': False, 'learn': False}, {'collect': True}, {'collect': True, 'learn': 1}):
            with self.subTest(consent=consent), self.assertRaises(ValueError):
                self.store.collect(self.record(consent=consent))
        self.assertEqual(self.store.queue()['records'], [])

    def test_pending_collection_preserves_unknown_cost_without_learning(self):
        result = self.store.collect(self.record())
        self.assertFalse(result['eligible'])
        self.assertFalse(result['learning_started'])
        self.assertEqual(result['model_requests'], 0)
        stored = self.store._record(result['record_id'])
        self.assertIsNone(stored['cost']['requests'])
        self.assertIsNone(stored['cost']['proxy_usd'])
        self.assertEqual(self.store.queue()['independent_eligible_tasks'], 0)

    def test_feedback_revision_is_append_only_and_stable_run_cannot_change(self):
        record = self.record()
        first = self.store.collect(record)
        second_record = copy.deepcopy(record)
        second_record['feedback'] = '请保留原图并缩短第二页标题'
        second = self.store.collect(second_record)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(self.store._record(second['record_id'])['supersedes'], first['record_id'])
        self.assertNotIn('feedback', self.store._record(first['record_id']))
        self.assertEqual(len(self.store.queue()['records']), 1)
        for key, value in [('task_identity', 'other-decision'), ('pair_id', 'other-pair'),
                           ('source_evidence', [{'source_id': 'anonymous-source', 'sha256': 'b' * 64}])]:
            altered = copy.deepcopy(second_record); altered[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.store.collect(altered)

    def test_failed_and_optimized_feedback_never_enters_normal_learning_queue(self):
        failed = self.record(consent={'collect': True, 'learn': True})
        failed['quality'].update(scientific='failed', visual='passed', reviewer='human')
        result = self.store.collect(failed)
        self.assertEqual(result['reason'], 'quality_failed_or_not_human_reviewed')
        optimized = self.record(run_id='other-run', group='optimized', consent={'collect': True, 'learn': True})
        optimized['quality'].update(scientific='passed', visual='passed', reviewer='human')
        result = self.store.collect(optimized)
        self.assertEqual(result['reason'], 'optimized_trace_not_normal_training')

    def test_user_passed_without_frozen_evidence_cannot_certify(self):
        record = self.record(consent={'collect': True, 'learn': True}, identity_confirmed=True)
        record['quality'].update(scientific='passed', visual='passed', reviewer='user')
        result = self.store.collect(record)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['reason'], 'independent_frozen_identity_needed')
        with self.assertRaises(ValueError):
            self.store.preview([result['record_id'], result['record_id']], [result['record_id']],
                contracts=self.area / 'contracts.json', version_fields=self.area / 'versions.json',
                tool_schema=self.area / 'schema.json')

    def test_missing_or_nonfinite_cost_cannot_be_silently_zeroed(self):
        for field, value in [('proxy_usd', float('nan')), ('requests', 1.5), ('requests', True),
                              ('billed_usd', -1), ('elapsed_seconds', float('inf'))]:
            record = self.record(); record['cost'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.store.collect(record)
        record = self.record(); del record['cost']['recovery_usd']
        with self.assertRaises(ValueError):
            self.store.collect(record)

    def test_private_store_and_evidence_cannot_escape_local(self):
        with self.assertRaises(ValueError):
            learning.FeedbackStore(learning.ROOT / 'docs' / 'feedback')
        record = self.record(run_dir=str(learning.ROOT / 'scenarios'))
        with self.assertRaises(ValueError):
            self.store.collect(record)

    def test_lock_rejects_concurrent_writes_without_dropping_existing_data(self):
        first = self.store.collect(self.record())
        lock = self.store.path / '.write-lock'
        lock.write_text('{}', encoding='utf-8')
        try:
            with self.assertRaises(ValueError):
                self.store.collect(self.record(run_id='another-run'))
            self.assertTrue(lock.exists())
            self.assertEqual(self.store._record(first['record_id'])['run_id'], 'diagnostic-run')
        finally:
            lock.unlink()

    def test_pending_feedback_repeated_pair_is_not_independent_training(self):
        self.store.collect(self.record())
        self.store.collect(self.record(run_id='paired-other', group='optimized'))
        self.assertEqual(len(self.store.queue()['records']), 2)
        self.assertEqual(self.store.queue()['independent_eligible_tasks'], 0)

    def test_fake_render_pass_and_preview_manifest_do_not_establish_real_evidence(self):
        run = self.area / 'run'; run.mkdir()
        for name, value in [('manifest.json', {'model_call_enabled': False, 'reasoning_effort': 'off', 'mode': 'baseline'}),
                            ('metrics.json', {'status': 'done', 'upstream_requests': 0})]:
            (run / name).write_text(json.dumps(value), encoding='utf-8')
        (run / 'agent-events.jsonl').write_text('', encoding='utf-8')
        (run / 'cost-ledger.jsonl').write_text('', encoding='utf-8')
        receipt = self.area / 'receipts.json'
        receipt.write_text(json.dumps({'mechanical_delivery_verified': True, 'files': []}), encoding='utf-8')
        record = self.record(run_dir=str(run), delivery_evidence={'path': str(receipt), 'sha256': learning._hash(receipt)})
        stored = self.store._record(self.store.collect(record)['record_id'])
        with self.assertRaisesRegex(ValueError, '真实运行'):
            self.store._evidence(stored)

    def test_byte_changes_in_raw_run_evidence_fail_closed(self):
        run = self.area / 'run'; run.mkdir()
        (run / 'manifest.json').write_text('{}', encoding='utf-8')
        record = self.record(run_dir=str(run))
        stored = self.store._record(self.store.collect(record)['record_id'])
        (run / 'manifest.json').write_text('{"changed": true}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '变化'):
            self.store._evidence(stored)

    def test_empty_store_has_no_active_version_or_automatic_release(self):
        state = self.store.status()
        self.assertIsNone(state['active_version'])
        self.assertIsNone(self.store.active_manifest())
        self.assertFalse(state['automatic_activation'])
        with self.assertRaises(ValueError):
            self.store.rollback(confirm=True)

    def execution_record(self):
        # 协议夹具仅验证拒绝边界，不代表真实模型/候选认证。
        run = self.area / 'execution'; run.mkdir()
        manifest = self.area / 'candidate-manifest.json'
        manifest.write_text(json.dumps({'manifest_digest': 'a' * 64}), encoding='utf-8')
        candidate = {'version': 'b' * 32, 'manifest': str(manifest)}
        (run / 'manifest.json').write_text(json.dumps({'mode': 'execute', 'manifest_digest': 'a' * 64}), encoding='utf-8')
        session = 'diagnostic-session'
        (run / 'metrics.json').write_text(json.dumps({'session_id': session, 'model_requests_skipped_verified': 1}), encoding='utf-8')
        audit = run / '.local/online-motif' / (learning.hashlib.sha256(session.encode()).hexdigest() + '.jsonl')
        audit.parent.mkdir(parents=True)
        audit.write_text(json.dumps({'kind': 'model_request_skipped_verified', 'session_id': session,
                                    'batch_id': 'diagnostic-batch', 'tool_count': 1}) + '\n', encoding='utf-8')
        row = self.record(run_dir=str(run), group='optimized', candidate_version=candidate['version'],
                          evidence_lock={str(audit.resolve()): learning._hash(audit)})
        return row, candidate, audit

    def test_candidate_label_or_composed_cost_cannot_replace_real_execution(self):
        row, candidate, audit = self.execution_record()
        result = self.store._candidate_execution(row, candidate)
        self.assertEqual(result['verified_requests'], 1)
        path = Path(row['run_dir']) / 'manifest.json'
        path.write_text(json.dumps({'mode': 'baseline', 'manifest_digest': 'a' * 64}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '执行证据'):
            self.store._candidate_execution(row, candidate)

    def test_zero_verified_or_different_library_is_rejected(self):
        row, candidate, audit = self.execution_record()
        metrics = Path(row['run_dir']) / 'metrics.json'
        metrics.write_text(json.dumps({'session_id': 'diagnostic-session', 'model_requests_skipped_verified': 0}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '普通组合'):
            self.store._candidate_execution(row, candidate)
        path = Path(row['run_dir']) / 'manifest.json'
        path.write_text(json.dumps({'mode': 'execute', 'manifest_digest': 'c' * 64}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'manifest_digest'):
            self.store._candidate_execution(row, candidate)

    def test_candidate_audit_is_frozen_and_session_bound(self):
        row, candidate, audit = self.execution_record()
        audit.write_text(json.dumps({'kind': 'model_request_skipped_verified', 'session_id': 'other-session',
                                    'batch_id': 'diagnostic-batch', 'tool_count': 1}) + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '冻结'):
            self.store._candidate_execution(row, candidate)
        row['evidence_lock'][str(audit.resolve())] = learning._hash(audit)
        with self.assertRaisesRegex(ValueError, '会话'):
            self.store._candidate_execution(row, candidate)

    def test_active_consumer_rechecks_latest_promotion_gate(self):
        with patch.object(self.store, 'status', return_value={'active_version': 'a' * 32}), \
                patch.object(self.store, '_candidate', return_value={'manifest': 'unused', 'manifest_sha256': 'b' * 64}), \
                patch.object(self.store, '_release_gate', side_effect=ValueError('最新质量不合格')):
            with self.assertRaisesRegex(ValueError, '最新质量'):
                self.store.active_manifest()

    def test_candidate_staging_does_not_change_active_release(self):
        with patch.object(self.store, '_candidate', return_value={'manifest': 'unused', 'manifest_sha256': 'b' * 64}):
            staged = self.store.candidate_manifest('a' * 32)
        self.assertFalse(staged['quality_cost_promoted'])
        self.assertEqual(staged['stage'], 'candidate_evaluation')
        self.assertIsNone(self.store.status()['active_version'])


if __name__ == '__main__':
    unittest.main()
