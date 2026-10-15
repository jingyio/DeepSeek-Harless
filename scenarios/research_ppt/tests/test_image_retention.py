"""原图必须由目标页可见pic引用，不能凭全包存在同SHA通过；实际PPTX负例。"""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import unittest
from uuid import uuid4
import zipfile

from PIL import Image, ImageDraw

from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.service import PPTService
from scenarios.research_ppt.validation import ROOT, _read_package, _check_image_plan, plan_expectations, validate_delivery


def figure_bytes(color):
    image = Image.new('RGB', (180, 120), 'white')
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((10, 10, 165, 105), outline='black', width=3)
    drawing.line((15, 90, 50, 30, 100, 75, 160, 20), fill=color, width=5)
    data = io.BytesIO()
    image.save(data, 'PNG')
    return data.getvalue()


class ImageRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = ROOT / '.local/research-ppt/image-retention-tests' / uuid4().hex
        cls.area.mkdir(parents=True, exist_ok=False)
        cls.images = [figure_bytes('blue'), figure_bytes('red')]
        cls.plan = {'title': 'Independent figure retention', 'slides': [
            {'title': f'Original figure {index + 1}', 'bullets': [],
             'image': {'data': 'image/png;base64,' + base64.b64encode(raw).decode('ascii'), 'width': 180, 'height': 120},
             'sources': ['Public synthetic figure source page 1; fixture-only SHA']}
            for index, raw in enumerate(cls.images)
        ]}
        cls.expected = plan_expectations(cls.plan)
        plan_path = cls.area / 'plan.json'
        plan_path.write_text(json.dumps(cls.plan), encoding='utf-8')
        cls.pptx = cls.area / 'original.pptx'
        subprocess.run(['node', str(ROOT / 'scenarios/research_ppt/dist/render.js'), str(plan_path), str(cls.pptx)],
                       check=True, capture_output=True, timeout=90)

    def changed(self, name, change, extra=None):
        target = self.area / name
        modified = False
        with zipfile.ZipFile(self.pptx) as original, zipfile.ZipFile(target, 'w') as result:
            for item in original.infolist():
                raw = original.read(item.filename)
                altered = change(item.filename, raw)
                modified |= raw != altered
                result.writestr(item, altered)
            if extra:
                result.writestr(*extra)
        self.assertTrue(modified, '负例必须修改实际PPTX')
        return target

    def checked(self, target):
        return validate_delivery(target, 2, expected_texts=self.expected['texts'],
                                 expected_images=self.expected['images'],
                                 expected_sources=[slide['sources'] for slide in self.plan['slides']])

    def test_renderer_embeds_exact_png_bytes_and_target_page_binding_matches(self):
        report = {'errors': [], 'warnings': []}
        _read_package(self.pptx, report, expected_images=self.expected['images'])
        for index, expected in enumerate(self.expected['images']):
            self.assertEqual(expected['sha256'], hashlib.sha256(self.images[index]).hexdigest())
            self.assertEqual(report['planned_image_data'][index], [expected])
            _check_image_plan(report['planned_image_data'][index], expected, report, index + 1)
        self.assertEqual(report['errors'], [])

    def test_deleted_pic_is_rejected_while_original_media_still_exists(self):
        target = self.changed('deleted-pic.pptx', lambda name, raw:
                              re.sub(rb'<p:pic>[\s\S]*?</p:pic>', b'', raw, count=1)
                              if name == 'ppt/slides/slide1.xml' else raw)
        report = self.checked(target)
        self.assertFalse(report['passed'])
        self.assertIn('planned_image_count_mismatch', {row['code'] for row in report['errors']})

    def test_replaced_target_media_fails_even_with_unused_original_hash_in_package(self):
        target = self.changed('replaced-media.pptx', lambda name, raw:
                              self.images[1] if name.startswith('ppt/media/') and raw == self.images[0] else raw,
                              extra=('ppt/media/unused-original.png', self.images[0]))
        report = self.checked(target)
        self.assertFalse(report['passed'])
        self.assertIn('planned_image_missing_or_changed', {row['code'] for row in report['errors']})

    def test_cropped_or_hidden_target_pic_is_rejected(self):
        changes = {
            'cropped': lambda raw: raw.replace(b'<a:stretch>', b'<a:srcRect l="10000" t="0" r="0" b="0"/><a:stretch>', 1),
            'hidden': lambda raw: re.sub(rb'<p:pic>[\s\S]*?</p:pic>', lambda picture:
                                        re.sub(rb'(<p:cNvPr\b[^>]*?)(/?>)', rb'\1 hidden="1"\2', picture.group(), count=1), raw, count=1),
        }
        for label, change in changes.items():
            with self.subTest(change=label):
                target = self.changed(label + '.pptx', lambda name, raw:
                                      change(raw) if name == 'ppt/slides/slide1.xml' else raw)
                report = self.checked(target)
                self.assertFalse(report['passed'])
                self.assertIn('validation_failed', {row['code'] for row in report['errors']})

    def test_service_passes_original_image_expectation_to_independent_validation(self):
        import fitz
        source = self.area / 'synthetic-image-paper.pdf'
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((40, 40), 'Public synthetic original figure source.')
            page.insert_image(fitz.Rect(40, 80, 400, 320), stream=self.images[0])
            page.insert_text((40, 340), 'Figure 1: Synthetic figure for original-image retention checks.')
            pdf.save(source)
        service = PPTService(prepare([source], '保留原图', 1, True))
        handle = service.pin_source('doc_1')['source_id']
        service.read_source(handle)
        candidates = service.read_page(handle, 1)['figure_candidates']
        self.assertEqual(len(candidates), 1)
        figure = service.extract_figure(handle, 1, candidate_id=candidates[0]['candidate_id'])
        self.assertEqual(figure['evidence_scope'], 'caption_geometry_candidate')
        image_id = figure['image_id']
        plan = {'title': 'Original figure', 'slides': [
            {'title': 'Original figure', 'bullets': [], 'image': {'source_id': handle, 'image_id': image_id},
             'sources': [{'source_id': handle, 'page': 1}]}]}
        rendered = service.render_deck(plan)
        target = Path(rendered['path'])
        candidate = target.with_suffix('.missing-image.pptx')
        modified = False
        with zipfile.ZipFile(target) as original, zipfile.ZipFile(candidate, 'w') as result:
            for item in original.infolist():
                raw = original.read(item.filename)
                if item.filename == 'ppt/slides/slide1.xml':
                    altered = re.sub(rb'<p:pic>[\s\S]*?</p:pic>', b'', raw, count=1)
                    modified = raw != altered
                    raw = altered
                result.writestr(item, raw)
        self.assertTrue(modified)
        candidate.replace(target)
        service.deck_records[rendered['deck_id']]['sha256'] = file_hash(target)
        report = service.validate_deck(rendered['deck_id'])
        self.assertFalse(report['passed'])
        self.assertIn('planned_image_count_mismatch', {row['code'] for row in report['errors']})
        with self.assertRaisesRegex(ValueError, '未通过真实渲染'):
            service.deliver_deck(report['validation_id'])


if __name__ == '__main__':
    unittest.main()
