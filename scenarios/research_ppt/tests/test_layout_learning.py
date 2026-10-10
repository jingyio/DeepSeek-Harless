"""服务器上的真实 Node/LibreOffice 布局闭环回归；不调用模型。

本文件的图与任务为合成工程夹具，不是论文实验或美学成绩。保留本次
创建的 .local 目录和真实渲染证据，服务器测试日志由运行入口保存。
"""
from __future__ import annotations

import base64
import copy
import io
import json
from pathlib import Path
import unittest
from uuid import uuid4

from PIL import Image, ImageDraw

from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt import layout_learning as learning
from scenarios.research_ppt.service import ROOT, PPTService, node


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def freeze_json(path: Path, value: dict):
    write_json(path, value)
    path.with_name(path.name + '.sha256').write_text(file_hash(path), encoding='ascii')


class LayoutLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / '.local/research-ppt/layout-tests' / uuid4().hex
        cls.directory.mkdir(parents=True, exist_ok=False)
        print('布局回归证据目录：' + str(cls.directory), flush=True)
        # 宽图使 media_fraction 的实际面积变化可测；不猜测或模拟渲染结果。
        image = Image.new('RGB', (1200, 400), 'white')
        drawing = ImageDraw.Draw(image)
        drawing.line((60, 340, 1140, 340), fill='#17345C', width=5)
        for index, height in enumerate((100, 170, 240)):
            x = 180 + index * 300
            drawing.rectangle((x, 340 - height, x + 140, 338), fill='#117D88')
        content = io.BytesIO()
        image.save(content, format='PNG')
        encoded = 'image/png;base64,' + base64.b64encode(content.getvalue()).decode('ascii')
        cls.cases = []
        for identity, split in (('train_a', 'train'), ('train_b', 'train'),
                                ('heldout_secret', 'heldout')):
            directory = cls.directory / identity
            directory.mkdir()
            plan = {'title': 'Synthetic layout fixture ' + identity, 'slides': [{
                'title': 'Native editable evidence ' + identity,
                'bullets': ['Identical editable text.'],
                'sources': ['Synthetic fixture ' + identity + '; page 1'],
                'notes': 'Synthetic engineering fixture; scientific quality is not evaluated.',
                'image': {'data': encoded, 'width': 1200, 'height': 400},
            }]}
            path = directory / 'plan.json'
            write_json(path, plan)
            pptx = directory / 'presentation.pptx'
            node('render.js', {}, str(path), str(pptx))
            if not pptx.is_file():
                raise AssertionError('真实 Node 渲染未产生原生 PPTX 夹具')
            cls.cases.append({'id': identity, 'split': split, 'plan': str(path),
                              'sha256': file_hash(path), 'run_id': 'synthetic-fixture-' + identity})
        cls.input = cls.directory / 'train_a/presentation.pptx'

    def suite(self, cases=None) -> Path:
        path = self.directory / ('suite-' + uuid4().hex + '.json')
        write_json(path, {'schema_version': 1, 'cases': copy.deepcopy(cases or self.cases)})
        return path

    def job(self, *, suite=None, allow_output=True, allow_rsi=True) -> Path:
        return prepare([self.input], 'Synthetic layout regression; no scientific quality claim.', 1,
                       allow_output=allow_output, allow_rsi=allow_rsi,
                       layout_suite=suite or self.suite())

    def test_real_policy_schema_permissions_and_persistent_failed_attempt_limit(self):
        checked = node('layout-policy-cli.js', learning.DEFAULT)
        self.assertTrue(checked['valid'])
        self.assertFalse(checked['certified'])
        self.assertEqual(set(checked['policy']), set(checked['schema']['required']))
        self.assertFalse(node('layout-policy-cli.js', {**learning.DEFAULT, 'code': 'forbidden'})['valid'])

        denied = self.job(allow_rsi=False)
        with self.assertRaisesRegex(ValueError, '明确允许 RSI'):
            learning.propose(read_json(denied), denied, learning.DEFAULT)
        self.assertFalse((denied.parent / 'layout-rsi').exists())

        job_path = self.job()
        job = read_json(job_path)
        before = set(job_path.parent.rglob('*'))
        state = learning.status(job, job_path)
        self.assertEqual(set(job_path.parent.rglob('*')), before, '只读 status 不能创建训练或认证产物')
        self.assertFalse(state['training_prepared'])
        self.assertNotIn('heldout_secret', json.dumps(state))

        candidates = ({'schema_version': 1}, learning.DEFAULT,
                      {**learning.DEFAULT, 'allow_output': True})
        for expected, candidate in enumerate(candidates, 1):
            result = learning.propose(job, job_path, candidate)
            self.assertEqual(result['attempt'], expected)
            self.assertEqual(result['attempts_remaining'], 3 - expected)
            self.assertFalse(result['training_passed'])
            self.assertFalse(result['mechanical_certified'])
            self.assertTrue(result['diagnostics'])
        # 第二次策略合法，但没有显式训练基线，同样失败且不能由 schema 晋级。
        restarted = PPTService(job_path)
        self.assertEqual(restarted.layout_policy_status()['attempts_used'], 3)
        with self.assertRaisesRegex(ValueError, '3 次提案上限'):
            restarted.propose_layout_policy(learning.DEFAULT)
        self.assertFalse((job_path.parent / 'layout-rsi/active-policy.json').exists())
        self.assertFalse((job_path.parent / 'layout-rsi/heldout-baseline.json').exists())

    def test_frozen_source_changes_and_cross_split_run_identity_are_rejected(self):
        cases = copy.deepcopy(self.cases)
        cases[-1]['run_id'] = cases[0]['run_id']
        job_path = self.job(suite=self.suite(cases))
        with self.assertRaisesRegex(ValueError, '同一模型运行'):
            learning.prepare_training(job_path)

        cases = copy.deepcopy(self.cases)
        altered = self.directory / ('altered-' + uuid4().hex) / 'plan.json'
        original = read_json(Path(cases[0]['plan']))
        write_json(altered, original)
        cases[0]['plan'] = str(altered)
        job_path = self.job(suite=self.suite(cases))
        original['slides'][0]['title'] = 'Changed source after freezing'
        write_json(altered, original)
        with self.assertRaisesRegex(ValueError, '历史模型计划版本变化'):
            learning.status(read_json(job_path), job_path)
        self.assertFalse((job_path.parent / 'layout-rsi/heldout-baseline.json').exists())

    def test_real_training_independent_certification_loading_and_evidence_guards(self):
        job_path = self.job()
        job = read_json(job_path)
        area = job_path.parent / 'layout-rsi'
        prepared = learning.prepare_training(job_path)
        self.assertEqual(prepared['training']['cases'], 2)
        self.assertEqual(prepared['training']['failed'], 0, read_json(Path(prepared['baseline_path'])))
        baseline_sha = file_hash(Path(prepared['baseline_path']))
        self.assertEqual(learning.prepare_training(job_path), prepared)
        self.assertEqual(file_hash(Path(prepared['baseline_path'])), baseline_sha)
        state = learning.status(job, job_path)
        self.assertEqual([row['id'] for row in state['training_diagnostics']], ['train_a', 'train_b'])
        self.assertNotIn('heldout_secret', json.dumps(state))
        self.assertFalse((area / 'heldout-baseline.json').exists())

        candidate = {**learning.DEFAULT, 'media_fraction': 0.70}
        proposed = learning.propose(job, job_path, candidate)
        self.assertTrue(proposed['training_passed'], proposed)
        self.assertFalse(proposed['mechanical_certified'])
        self.assertGreaterEqual(proposed['training']['image_area_gain'], 0.10)
        self.assertTrue(proposed['training']['content_unchanged'])
        proposal_path = Path(proposed['proposal_path'])
        self.assertEqual(proposal_path.with_name(proposal_path.name + '.sha256').read_text(),
                         file_hash(proposal_path))
        self.assertFalse((area / 'active-policy.json').exists())

        certification = learning.certify(job_path, proposal_path)
        self.assertTrue(certification['mechanical_certified'], certification)
        self.assertFalse(certification['visual_quality_certified'])
        certificate_path = Path(certification['certificate_path'])
        certificate = learning.validate_certificate(certificate_path)
        self.assertFalse(certificate['scientific_quality_certified'])
        self.assertIn('layout_learning.py', certificate['renderer_version'])
        self.assertEqual([row['id'] for row in certificate['heldout_candidate']], ['heldout_secret'])
        for row in [*certificate['heldout_baseline'], *certificate['heldout_candidate']]:
            self.assertTrue(row['passed'], row['diagnostics'])
            self.assertTrue(row['validation']['passed'])
            self.assertTrue({'pptx', 'pdf', 'preview', 'manifest', 'replay_record'}.issubset(
                {artifact['kind'] for artifact in row['files']}))
            for artifact in row['files']:
                self.assertEqual(file_hash(Path(artifact['path'])), artifact['sha256'])
        # 留出反馈不能反向进入模型 status；有效证书仍不宣称视觉认证。
        state = learning.status(job, job_path)
        self.assertNotIn('heldout_secret', json.dumps(state))
        self.assertFalse(state['mechanical_certified'])

        loaded_job = prepare([self.input], 'Native policy loading regression.', 1,
                             allow_output=True, layout_policy=certificate_path)
        loaded = read_json(loaded_job)
        self.assertEqual(loaded['layout_policy_digest'], certificate['policy_digest'])
        service = PPTService(loaded_job)
        handle = service.pin_source('doc_1')['source_id']
        service.read_source(handle)
        plan = {'title': 'Certified layout loading', 'slides': [{
            'title': 'Native editable delivery', 'bullets': ['Content remains editable.'],
            'sources': [{'source_id': handle, 'page': 1}],
            'notes': 'Synthetic loading regression only.',
        }]}
        rendered = service.render_deck(plan)
        manifest = read_json(Path(rendered['path']).with_suffix('.layout.json'))
        self.assertEqual(manifest['layout_policy_sha256'], certificate['policy_digest'])

        # 同一留出集已经绑定第一候选；另一真实训练通过的候选也不能重试认证。
        reservation_bytes = (area / 'heldout-reservation.json').read_bytes()
        active_bytes = Path(certification['active_policy_path']).read_bytes()
        alternative = learning.propose(job, job_path, {**candidate, 'media_fraction': 0.68})
        self.assertTrue(alternative['training_passed'], alternative)
        with self.assertRaisesRegex(ValueError, '认证集已用于其他候选'):
            learning.certify(job_path, Path(alternative['proposal_path']))
        self.assertEqual((area / 'heldout-reservation.json').read_bytes(), reservation_bytes)
        self.assertEqual(Path(certification['active_policy_path']).read_bytes(), active_bytes)

        forged = self.directory / ('forged-' + uuid4().hex + '.json')
        freeze_json(forged, {'policy': candidate, 'policy_digest': certificate['policy_digest'],
                            'mechanical_certified': True, 'visual_quality_certified': False})
        with self.assertRaises(ValueError):
            prepare([self.input], 'Reject schema-only certificate.', 1,
                    allow_output=True, layout_policy=forged)

        old_version = copy.deepcopy(certificate)
        old_version['renderer_version']['dist/render.js'] = '0' * 64
        outdated = self.directory / ('outdated-' + uuid4().hex + '.json')
        freeze_json(outdated, old_version)
        with self.assertRaisesRegex(ValueError, '依赖代码已变化'):
            learning.validate_certificate(outdated)

        preview = next(artifact for artifact in certificate['heldout_candidate'][0]['files']
                       if artifact['kind'] == 'preview')
        preview_path = Path(preview['path'])
        original_bytes = preview_path.read_bytes()
        try:
            preview_path.write_bytes(original_bytes + b'changed-preview')
            with self.assertRaisesRegex(ValueError, '版本已变化'):
                learning.validate_certificate(certificate_path)
            with self.assertRaisesRegex(ValueError, '版本已变化'):
                prepare([self.input], 'Reject changed certified evidence.', 1,
                        allow_output=True, layout_policy=certificate_path)
            with self.assertRaisesRegex(ValueError, '版本已变化'):
                service.render_deck(plan)
        finally:
            preview_path.write_bytes(original_bytes)
        self.assertEqual(learning.validate_certificate(certificate_path)['policy_digest'],
                         certificate['policy_digest'])


if __name__ == '__main__':
    unittest.main()
