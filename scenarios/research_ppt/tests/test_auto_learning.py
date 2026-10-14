"""No-model diagnostics for bounded automatic read-only learning."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scenarios.research_ppt import auto_learning
from scenarios.research_ppt.feedback_learning import FeedbackStore
from scenarios.research_ppt.service import ROOT


class AutoLearningTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.local').mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=ROOT / '.local')
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.store = FeedbackStore(self.area / 'feedback')

    def test_empty_store_does_not_learn_or_activate(self):
        result = auto_learning.tick(self.store)
        self.assertEqual(result['promotion']['stage'], 'waiting_for_two_user_approved_canaries')
        self.assertEqual(result['learning']['stage'], 'waiting_for_three_independent_user_approved_tasks')
        self.assertEqual(result['model_requests'], 0)
        self.assertIsNone(self.store.status()['active_version'])

    def test_failed_old_configuration_does_not_block_new_learning_group(self):
        rows = [{'record_id': f'{i:032x}', 'pair_id': f'pair-{i}',
                 'task_identity': f'decision-{i}'} for i in range(6)]
        groups = [rows[:3], rows[3:]]
        plan = self.area / 'plan.json'
        schema = self.area / 'schema.json'
        schema.write_text('{}', encoding='utf-8')
        with patch.object(auto_learning, '_learning_record_groups', return_value=groups), \
             patch.object(auto_learning, '_private', return_value=schema), \
             patch.object(self.store, 'status', return_value={'active_version': None, 'candidates': []}), \
             patch.object(self.store, '_auto_task_key', side_effect=lambda row: row['task_identity']), \
             patch.object(self.store, 'preview', side_effect=[ValueError('old version rejected'),
                                                              {'plan_path': str(plan)}]) as preview, \
             patch.object(self.store, 'learn', return_value={
                 'version': 'a' * 32, 'learning_cost': {'model_requests': 0}}):
            result = auto_learning._learn_once(self.store)
        self.assertEqual(preview.call_count, 2)
        self.assertEqual(result['stage'], 'candidate_certified')
        self.assertEqual(result['version'], 'a' * 32)

    def test_automatic_scope_cannot_use_unreviewed_pair(self):
        rows = [{'record_id': f'{i:032x}', 'pair_id': f'pair-{i}', 'task_identity': f'decision-{i}',
                 'run_id': f'run-{i}'} for i in range(3)]
        for row in rows:
            record = self.store.path / 'records' / (row['record_id'] + '.json')
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(json.dumps(row), encoding='utf-8')
        with patch.object(self.store, '_record', side_effect=rows), \
             patch.object(self.store, '_eligibility', return_value=(True, 'eligible')), \
             patch.object(self.store, '_auto_training_pair', side_effect=ValueError('missing user review')):
            with self.assertRaisesRegex(ValueError, 'missing user review'):
                self.store.preview([rows[0]['record_id'], rows[1]['record_id']],
                                   [rows[2]['record_id']], contracts=self.area / 'contracts.json',
                                   version_fields=self.area / 'versions.json',
                                   tool_schema=self.area / 'schema.json', auto_structural=True)
        self.assertEqual(list((self.store.path / 'plans').glob('*.json')), [])

    def test_two_unreviewed_canaries_pause_rollout(self):
        fake_root = self.area / 'checkout'
        trials = fake_root / '.local/research-ppt/trials'
        for index in range(2):
            directory = trials / f'trial-{index}'
            directory.mkdir(parents=True)
            (directory / 'trial.json').write_text(json.dumps({
                'trial_id': f'trial-{index}', 'candidate_evaluation': True, 'rsi_enabled': True,
                'active_learning': {'version': 'a' * 32}}), encoding='utf-8')
            (directory / 'execution-started.json').write_text('{}', encoding='utf-8')
        with patch.object(auto_learning, 'ROOT', fake_root), \
             patch.object(self.store, 'status', return_value={
                 'active_version': None, 'candidates': [{'version': 'a' * 32,
                     'valid': True, 'learning_scope': 'auto_structural'}]}), \
             patch.object(self.store, 'candidate_manifest', return_value={'version': 'a' * 32}):
            self.assertIsNone(auto_learning.candidate_for_next_trial(self.store))

    def test_failed_user_review_blocks_candidate_selection(self):
        failed = {'candidate_version': 'a' * 32, 'group': 'optimized', 'pair_id': 'failed-pair',
                  'quality': {'delivery': 'passed', 'scientific': 'failed',
                              'visual': 'passed', 'reviewer': 'user'}}
        with patch.object(auto_learning, 'ROOT', self.area / 'checkout'), \
             patch.object(self.store, 'status', return_value={
                 'active_version': None, 'candidates': [{'version': 'a' * 32,
                     'valid': True, 'learning_scope': 'auto_structural'}]}), \
             patch.object(self.store, '_records', return_value=[failed]):
            self.assertIsNone(auto_learning.candidate_for_next_trial(self.store))

    def test_more_expensive_reviewed_canary_retires_candidate(self):
        version = 'a' * 32
        baseline = {'group': 'baseline', 'pair_id': 'pair',
                    'cost': {'requests': 10, 'proxy_usd': 0.01}}
        optimized = {'group': 'optimized', 'pair_id': 'pair', 'candidate_version': version,
                     'quality': {'delivery': 'passed', 'scientific': 'passed', 'visual': 'passed',
                                 'reviewer': 'user', 'revision_minutes': 0},
                     'cost': {'requests': 11, 'proxy_usd': 0.02}}
        with patch.object(auto_learning, 'ROOT', self.area / 'checkout'), \
             patch.object(self.store, '_records', return_value=[baseline, optimized]), \
             patch.object(self.store, 'status', return_value={
                 'active_version': None, 'candidates': [{'version': version,
                     'valid': True, 'learning_scope': 'auto_structural'}]}):
            self.assertIsNone(auto_learning.candidate_for_next_trial(self.store))

    def test_invalid_active_does_not_block_certified_successor_trial(self):
        version = 'a' * 32
        with patch.object(self.store, 'status', return_value={
                 'active_version': 'b' * 32, 'candidates': [{
                     'version': version, 'valid': True, 'learning_scope': 'auto_structural'}]}), \
             patch.object(self.store, 'active_manifest', side_effect=ValueError('stale active')), \
             patch.object(self.store, 'candidate_manifest', return_value={'version': version}), \
             patch.object(auto_learning, 'ROOT', self.area / 'checkout'):
            self.assertEqual(auto_learning.candidate_for_next_trial(self.store), version)

    def test_valid_active_blocks_uncertified_successor(self):
        with patch.object(self.store, 'status', return_value={
                 'active_version': 'b' * 32, 'candidates': []}), \
             patch.object(self.store, 'active_manifest', return_value={'version': 'b' * 32}):
            self.assertIsNone(auto_learning.candidate_for_next_trial(self.store))
            self.assertEqual(auto_learning._learn_once(self.store)['stage'], 'candidate_or_active_exists')

    def test_user_review_must_name_the_same_trial_and_delivered_pptx(self):
        from scenarios.research_ppt.documents import file_hash

        directory = self.area / 'pair'
        directory.mkdir()
        trial = directory / 'trial.json'
        trial.write_text('{}', encoding='utf-8')
        receipt = directory / 'delivery.json'
        receipt.write_text(json.dumps({'files': [{'kind': 'pptx', 'sha256': 'a' * 64}]}), encoding='utf-8')
        review = directory / 'review.json'
        review.write_text(json.dumps({'trial': str(trial), 'trial_sha256': file_hash(trial),
            'pptx_sha256': 'b' * 64, 'learning_consent': True,
            'quality': {'scientific_facts': True, 'figures_and_citations': True,
                        'usable_presentation': True}, 'revision_minutes': 0}), encoding='utf-8')
        row = {'pair_id': 'pair', 'consent': {'learn': True},
               'review_evidence': {'path': str(review), 'sha256': file_hash(review)},
               'delivery_evidence': {'path': str(receipt)},
               'evidence_lock': {str(review): file_hash(review)},
               'quality': {'reviewer': 'user', 'scientific': 'passed',
                           'visual': 'passed', 'revision_minutes': 0}}
        with self.assertRaisesRegex(ValueError, '不一致'):
            self.store._web_user_review(row)

    def test_auto_release_requires_two_new_pairs_and_auto_scope(self):
        with patch.object(self.store, '_candidate', return_value={'learning_scope': 'auto_structural'}):
            with self.assertRaisesRegex(ValueError, '两个独立新任务'):
                self.store.activate_auto('a' * 32, ['one'])
        with patch.object(self.store, '_candidate', return_value={'learning_scope': 'evaluation_only'}):
            with self.assertRaisesRegex(ValueError, '只读结构'):
                self.store.activate_auto('a' * 32, ['one', 'two'])


if __name__ == '__main__':
    unittest.main()
