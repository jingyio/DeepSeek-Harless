"""真实 Node/LibreOffice 基线公平性回归；工程夹具，不调用模型，不认证审美。"""
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
from scenarios.research_ppt.service import ROOT, node


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


class LayoutBaselineModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / '.local/research-ppt/layout-baseline-tests' / uuid4().hex
        cls.directory.mkdir(parents=True, exist_ok=False)
        print('布局基线公平性证据目录：' + str(cls.directory), flush=True)
        image = Image.new('RGB', (1200, 400), 'white')
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((50, 50, 1150, 350), outline='#17345C', width=5)
        drawing.text((100, 150), 'All evidence must remain visible', fill='#17345C')
        content = io.BytesIO(); image.save(content, format='PNG')
        encoded = 'image/png;base64,' + base64.b64encode(content.getvalue()).decode('ascii')
        cls.cases = []
        for identity, split in (('train', 'train'), ('independent', 'heldout')):
            directory = cls.directory / identity
            directory.mkdir()
            plan = {'title': 'Baseline fairness ' + identity, 'slides': [{
                'title': 'Full figure ' + identity,
                'bullets': ['Identical editable content.'],
                'sources': ['Synthetic fixture ' + identity + '; page 1'],
                'notes': 'Synthetic engineering fixture; not a scientific quality evaluation.',
                'image': {'data': encoded, 'width': 1200, 'height': 400},
            }]}
            path = directory / 'plan.json'; write_json(path, plan)
            node('render.js', {}, str(path), str(directory / 'presentation.pptx'))
            cls.cases.append({'id': identity, 'split': split, 'plan': str(path),
                              'sha256': file_hash(path), 'run_id': 'baseline-fixture-' + identity})
        cls.input = cls.directory / 'train/presentation.pptx'

    def job(self, mode='fixed-policy'):
        suite = self.directory / ('suite-' + uuid4().hex + '.json')
        write_json(suite, {'schema_version': 1, 'cases': copy.deepcopy(self.cases)})
        return prepare([self.input], 'Baseline fairness regression only.', 1,
                       allow_output=True, allow_rsi=True, layout_suite=suite,
                       layout_baseline_mode=mode)

    def test_real_candidate_beats_fixed_but_loses_to_product_default_and_is_rejected(self):
        job_path = self.job('renderer-default'); job = read_json(job_path)
        prepared = learning.prepare_training(job_path)
        self.assertEqual(prepared['layout_baseline_mode'], 'renderer-default')
        self.assertEqual(prepared['training']['failed'], 0)
        baseline = read_json(Path(prepared['baseline_path']))
        self.assertIsNone(baseline['policy'])
        actual = next(item for item in baseline['rows'][0]['files'] if item['kind'] == 'plan')
        self.assertNotIn('layout_policy', read_json(Path(actual['path'])))
        self.assertFalse(baseline['rows'][0]['layout_policy_applied'])
        candidate = learning.propose(job, job_path, {**learning.DEFAULT, 'media_fraction': 0.70})
        proposal = read_json(Path(candidate['proposal_path']))
        self.assertFalse(candidate['training_passed'], candidate)
        self.assertEqual(proposal['candidate'][0]['passed'], True)
        self.assertTrue(proposal['candidate'][0]['layout_policy_applied'])
        fixed = learning._replay(self.cases[0], learning.DEFAULT, job_path.parent / 'layout-rsi', learning._version())
        self.assertTrue(fixed['passed'], fixed['diagnostics'])
        self.assertTrue(learning._gate([fixed], proposal['candidate'], improvement=True)['passed'],
                        '同一候选原本可胜旧显式基线')
        self.assertFalse(learning._gate(baseline['rows'], proposal['candidate'], improvement=True)['passed'],
                         '候选不能只胜旧基线而回退当前普通确定性规则')
        self.assertEqual(fixed['semantic_content_sha256'], baseline['rows'][0]['semantic_content_sha256'])
        self.assertEqual(fixed['semantic_content_sha256'], proposal['candidate'][0]['semantic_content_sha256'])
        self.assertFalse((job_path.parent / 'layout-rsi/heldout-reservation.json').exists())
        with self.assertRaisesRegex(ValueError, '未通过冻结训练'):
            learning.certify(job_path, Path(candidate['proposal_path']))

    def test_runtime_enum_supplied_job_and_baseline_cache_are_mode_bound(self):
        for invalid in (None, True, {}, 'auto', 'code'):
            with self.assertRaisesRegex(ValueError, 'layout_baseline_mode'):
                learning.baseline_mode({'layout_baseline_mode': invalid})
        with self.assertRaisesRegex(ValueError, 'layout_baseline_mode'):
            prepare([self.input], 'Invalid mode cannot create a job.', 1, layout_baseline_mode='invalid')
        job_path = self.job(); job = read_json(job_path)
        prepared = learning.prepare_training(job_path)
        baseline_path = Path(prepared['baseline_path'])
        # 缺字段的旧job/基线继续表示fixed-policy，不修改旧suite schema。
        job.pop('layout_baseline_mode'); write_json(job_path, job)
        self.assertEqual(learning.prepare_training(job_path), prepared)
        original_hash = file_hash(baseline_path)
        altered = {**job, 'layout_baseline_mode': 'renderer-default'}; write_json(job_path, altered)
        with self.assertRaisesRegex(ValueError, '基线模式已变化'):
            learning._job(job_path, job)
        suite, digest = learning._suite(altered)
        self.assertIsNone(learning._baseline(altered, job_path.parent / 'layout-rsi', suite, digest,
                                            learning._version(), 'train'))
        self.assertEqual(file_hash(baseline_path), original_hash, '读取不能偷偷重写旧基线')
        altered['layout_baseline_mode'] = None; write_json(job_path, altered)
        with self.assertRaisesRegex(ValueError, 'layout_baseline_mode'):
            learning._job(job_path)

    def test_certification_and_certificate_reject_changed_comparison_mode(self):
        job_path = self.job(); job = read_json(job_path)
        learning.prepare_training(job_path)
        proposed = learning.propose(job, job_path, {**learning.DEFAULT, 'media_fraction': 0.70})
        self.assertTrue(proposed['training_passed'], proposed)
        write_json(job_path, {**job, 'layout_baseline_mode': 'renderer-default'})
        with self.assertRaisesRegex(ValueError, '未通过冻结训练'):
            learning.certify(job_path, Path(proposed['proposal_path']))
        self.assertFalse((job_path.parent / 'layout-rsi/heldout-reservation.json').exists())
        write_json(job_path, job)
        certified = learning.certify(job_path, Path(proposed['proposal_path']))
        self.assertTrue(certified['mechanical_certified'], certified)
        certificate = learning.validate_certificate(Path(certified['certificate_path']))
        self.assertEqual(certificate['layout_baseline_mode'], 'fixed-policy')
        self.assertFalse(certificate['visual_quality_certified'])
        forged = job_path.parent / 'layout-rsi/mode-mismatch-certificate.json'
        write_json(forged, {**certificate, 'layout_baseline_mode': 'renderer-default'})
        forged.with_name(forged.name + '.sha256').write_text(file_hash(forged), encoding='ascii')
        with self.assertRaisesRegex(ValueError, '基线模式不一致'):
            learning.validate_certificate(forged)


if __name__ == '__main__':
    unittest.main()
