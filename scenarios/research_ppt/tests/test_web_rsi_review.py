from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scenarios.research_ppt import feedback_learning, web_bridge, web_rsi_review
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.service import ROOT


class WebRSIReviewTests(TestCase):
    def setUp(self):
        (ROOT / '.local').mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=ROOT / '.local')
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.trial = self.area / 'trial.json'
        self.trial.write_text(json.dumps({'trial_id': 'review-diagnostic',
                                          'feedback_store': str(self.area / 'feedback')}))
        self.sha = file_hash(self.trial)
        (self.area / 'comparison.json').write_text(json.dumps({'trial_sha256': self.sha}))
        self.deck = self.area / 'deck.pptx'
        self.deck.write_bytes(b'diagnostic deck')
        self.deck_sha = file_hash(self.deck)
        for group in ('baseline', 'optimized'):
            (self.area / (group + '-delivery-receipts.json')).write_text(json.dumps({'files': []}))
            result = {'mechanical_delivery_verified': True, 'strategy_adherence': True,
                      'deliveries': [{'deck_id': 'deck-1', 'files': [{'kind': 'pptx', 'path': str(self.deck),
                                                  'sha256': self.deck_sha}]}] if group == 'optimized' else []}
            (self.area / (group + '-result.json')).write_text(json.dumps(result))
        self.request = {'trial': str(self.trial), 'trial_sha256': self.sha,
                        'request_id': 'review-001', 'pptx_sha256': self.deck_sha,
                        'quality': {'scientific_facts': True, 'figures_and_citations': True,
                                    'usable_presentation': True},
                        'revision_minutes': 0, 'learning_consent': False, 'feedback': 'usable'}

    def record(self, _data, group, _result, evidence):
        return {'schema_version': 1, 'run_id': group + '-run', 'task_identity': 'decision',
                'pair_id': 'pair', 'group': group, 'consent': {'collect': True, 'learn': False},
                'source_evidence': [{'source_id': 'paper', 'sha256': 'a' * 64}],
                'versions': {key: None for key in feedback_learning.VERSION_FIELDS},
                'quality': {'delivery': 'passed', 'scientific': 'pending', 'visual': 'pending',
                            'reviewer': 'unreviewed', 'revision_minutes': None},
                'cost': {key: None for key in feedback_learning.COST_FIELDS},
                'identity_confirmed': False,
                'delivery_evidence': {'path': str(evidence), 'sha256': file_hash(evidence)}}

    def test_review_collects_two_groups_but_only_reviewed_deck_is_quality_passed(self):
        with patch.object(web_rsi_review, 'feedback_record', side_effect=self.record):
            receipt = web_rsi_review.collect_review(self.request)
            again = web_rsi_review.collect_review(self.request)
        self.assertEqual(receipt, again)
        self.assertFalse(receipt['learning_started'])
        rows = feedback_learning.FeedbackStore(self.area / 'feedback')._records()
        self.assertEqual(len(rows), 2)
        by_group = {row['group']: row for row in rows}
        self.assertEqual(by_group['optimized']['quality']['reviewer'], 'user')
        self.assertEqual(by_group['optimized']['quality']['scientific'], 'passed')
        self.assertEqual(by_group['baseline']['quality']['scientific'], 'pending')
        self.assertFalse(any(row['consent']['learn'] for row in rows))

    def test_changed_review_or_deck_cannot_replace_frozen_feedback(self):
        with patch.object(web_rsi_review, 'feedback_record', side_effect=self.record):
            web_rsi_review.collect_review(self.request)
            changed = copy.deepcopy(self.request)
            changed['feedback'] = 'different'
            with self.assertRaisesRegex(ValueError, 'reused'):
                web_rsi_review.collect_review(changed)
            self.deck.write_bytes(b'changed deck')
            with self.assertRaisesRegex(ValueError, 'deck version changed'):
                web_rsi_review.collect_review(self.request)
        self.assertEqual(len(feedback_learning.FeedbackStore(self.area / 'feedback')._records()), 2)

    def test_completed_optimized_deck_can_be_reviewed_before_baseline_finishes(self):
        (self.area / 'comparison.json').unlink()
        (self.area / 'baseline-result.json').unlink()
        (self.area / 'baseline-delivery-receipts.json').unlink()
        with patch.object(web_rsi_review, 'feedback_record', side_effect=self.record):
            receipt = web_rsi_review.collect_review(self.request)
        self.assertEqual(set(receipt['records']), {'optimized'})
        rows = feedback_learning.FeedbackStore(self.area / 'feedback')._records()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['quality']['reviewer'], 'user')

    def test_actual_feedback_record_fields_are_stored(self):
        from scenarios.research_ppt.feedback_learning import STRATEGY_SUFFIXES

        inputs = [{'document_id': 'paper', 'version_sha256': 'a' * 64}]
        task = {'instruction': 'make slides', 'slides': 8, 'template': 'lab',
                'operation': 'generate', 'inputs': inputs}
        shared = 'PPT agent\n本次任务：\n' + json.dumps(task, ensure_ascii=False) + '\n'
        groups = {}
        for group, strategy in (('baseline', 'baseline_steps'), ('optimized', 'host_delivery')):
            prompt = self.area / (group + '-prompt.md')
            prompt.write_text(shared + '本次执行方式：' +
                              STRATEGY_SUFFIXES[('generate', strategy)], encoding='utf-8')
            groups[group] = {'prompt': str(prompt), 'prompt_sha256': file_hash(prompt),
                             'shared_prompt_sha256': hashlib.sha256(
                                 shared.rstrip('\n').encode()).hexdigest(),
                             'execution': strategy}
            path = self.area / (group + '-result.json')
            result = json.loads(path.read_text())
            result.update({'tool_schema_sha256': 'b' * 64, 'elapsed_seconds': 1.0,
                           'accounting': {}, 'model_run_directory': None})
            path.write_text(json.dumps(result))
        self.trial.write_text(json.dumps({'trial_id': 'review-diagnostic', 'task': task,
                                          'groups': groups, 'model': 'deepseek-flash',
                                          'provider': 'deepseek-official',
                                          'code': {'sha256': 'c' * 64, 'files': {}},
                                          'feedback_store': str(self.area / 'feedback')}))
        self.sha = file_hash(self.trial)
        (self.area / 'comparison.json').write_text(json.dumps({'trial_sha256': self.sha}))
        request = {**self.request, 'trial_sha256': self.sha}
        receipt = web_rsi_review.collect_review(request)
        self.assertEqual(set(receipt['records']), {'baseline', 'optimized'})
        rows = feedback_learning.FeedbackStore(self.area / 'feedback')._records()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row['execution_strategy'] for row in rows},
                         {'baseline_steps', 'host_delivery'})

    def test_review_requires_explicit_ratings_and_learning_consent(self):
        for replacement in ({'learning_consent': 'yes'},
                            {'quality': {'scientific_facts': True}},
                            {'revision_minutes': float('nan')}):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                web_rsi_review.collect_review({**self.request, **replacement})

    def test_learning_consent_freezes_both_real_run_identities_before_collection(self):
        for group in ('baseline', 'optimized'):
            (self.area / (group + '-run')).mkdir()
        request = {**self.request, 'learning_consent': True}
        def record_with_run(data, group, result, evidence):
            return {**self.record(data, group, result, evidence),
                    'run_dir': str(self.area / (group + '-run'))}
        with patch.object(web_rsi_review, 'feedback_record', side_effect=record_with_run), \
             patch.object(web_rsi_review.subprocess, 'run') as freeze:
            freeze.return_value.returncode = 0
            web_rsi_review.collect_review(request)
        self.assertEqual(freeze.call_count, 2)
        rows = feedback_learning.FeedbackStore(self.area / 'feedback')._records()
        self.assertTrue(all(row['identity_confirmed'] for row in rows))
        self.assertTrue(all(row['consent']['learn'] for row in rows))

    def test_delivered_revision_revokes_original_zero_revision_learning_evidence(self):
        request = {**self.request, 'learning_consent': True}
        def record_with_trial_pair(data, group, result, evidence):
            return {**self.record(data, group, result, evidence), 'pair_id': self.area.name}
        with patch.object(web_rsi_review, 'feedback_record', side_effect=record_with_trial_pair):
            web_rsi_review.collect_review(request)
        revised = self.area / 'revised.pptx'
        revised.write_bytes(b'different deck')
        result_path = self.area / 'result.json'
        result_path.write_text(json.dumps({'status': 'delivered', 'parent_deck_id': 'deck-1',
            'deliveries': [{'files': [{'kind': 'pptx', 'path': str(revised),
                                      'sha256': file_hash(revised)}]}]}), encoding='utf-8')
        evidence = {'action': 'revision', 'trial': str(self.trial),
                    'review_request_id': request['request_id'], 'result_path': str(result_path),
                    'result_sha256': file_hash(result_path)}
        first = web_rsi_review.invalidate_revised_review(evidence)
        again = web_rsi_review.invalidate_revised_review(evidence)
        self.assertEqual(first['status'], 'invalidated')
        self.assertEqual(again['status'], 'already_invalidated')
        rows = feedback_learning.FeedbackStore(self.area / 'feedback')._records()
        optimized = next(row for row in rows if row['group'] == 'optimized')
        self.assertIsNone(optimized['quality']['revision_minutes'])
        self.assertEqual(optimized['post_review_revision']['sha256'], evidence['result_sha256'])

    def test_web_generation_inherits_only_valid_promoted_learning(self):
        with patch.object(web_bridge, 'prepare_trial', return_value=self.trial) as prepare:
            self.assertEqual(web_bridge.prepare_web_trial({
                'inputs': [str(self.deck)], 'instruction': 'make slides', 'slides': 8,
                'budget_usd': 1, 'template': 'lab', 'operation': 'generate'}), self.trial)
        self.assertTrue(prepare.call_args.kwargs['use_active_learning'])
        self.assertTrue(prepare.call_args.kwargs['use_auto_candidate'])
        self.assertEqual(prepare.call_args.kwargs['order'], 'optimized-first')
