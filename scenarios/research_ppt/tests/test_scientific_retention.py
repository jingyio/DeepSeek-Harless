"""科研组合页的真实原生对象/渲染/来源绑定反例；不调用模型。"""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from uuid import uuid4
import zipfile

from PIL import Image, ImageDraw

from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.revision import verify_unmodified_slides
from scenarios.research_ppt.service import PPTService
from scenarios.research_ppt.tests.test_service import write_pdf
from scenarios.research_ppt.validation import (
    ROOT, _check_chart_plan, _check_image_plan, _check_table_plan,
    _missing_texts, _read_package, plan_expectations, validate_delivery,
)


class ScientificRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = ROOT / '.local/research-ppt/scientific-retention-tests' / uuid4().hex
        cls.area.mkdir(parents=True, exist_ok=False)
        image = Image.new('RGB', (180, 120), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 165, 105), outline='black', width=3)
        draw.line((15, 90, 50, 30, 100, 75, 160, 20), fill='blue', width=5)
        stream = io.BytesIO()
        image.save(stream, 'PNG')
        cls.image_bytes = stream.getvalue()
        cls.source = 'Public synthetic source page 2; SHA256 fixture-only'
        cls.visible = 'Public synthetic source, p. 2'
        cls.note = {'label': 'Conditions', 'text': 'Heldout split; one run, no confidence interval.', 'source_index': 1}

        def slide(archetype, **content):
            return {'title': 'Scientific fixture', 'bullets': [], 'archetype': archetype,
                    'sources': [cls.source], 'visible_sources': [cls.visible],
                    'notes': 'Keep the original speaker notes.', 'evidence_notes': [copy.deepcopy(cls.note)], **content}

        cls.plan = {'title': 'Scientific layout retention', 'slides': [
            slide('evidence-focus', image={'data': 'image/png;base64,' + base64.b64encode(cls.image_bytes).decode('ascii'),
                                         'width': 180, 'height': 120}, bullets=['One observation, with no inferred claim.']),
            slide('result-summary', table=[['Method', 'Accuracy'], ['Method A', '87.5'], ['Method B', '92.2']]),
            slide('result-summary', chart={'type': 'bar', 'categories': ['Method A', 'Method B'],
                                          'series': [{'name': 'Accuracy', 'values': [87.5, 92.2]}],
                                          'x_label': 'Method', 'y_label': 'Accuracy', 'unit': '%'}),
            slide('method-map', layout='process', process={'steps': [
                {'label': 'Read sources', 'detail': 'Keep the original figure'},
                {'label': 'Verify output', 'detail': 'Check figures and numerical data'}]}, bullets=['Read, then verify.']),
        ]}
        cls.expected = plan_expectations(cls.plan)
        cls.pptx = cls.area / 'original.pptx'
        plan_path = cls.area / 'plan.json'
        plan_path.write_text(json.dumps(cls.plan), encoding='utf-8')
        subprocess.run(['node', str(ROOT / 'scenarios/research_ppt/dist/render.js'), str(plan_path), str(cls.pptx)],
                       check=True, capture_output=True, timeout=90)

    def changed(self, name, change):
        target = self.area / name
        modifications = 0
        with zipfile.ZipFile(self.pptx) as original, zipfile.ZipFile(target, 'w') as result:
            for item in original.infolist():
                raw = original.read(item.filename)
                altered = change(item.filename, raw)
                modifications += altered != raw
                result.writestr(item, altered)
        self.assertGreater(modifications, 0, '负例必须确实改变实际 PPTX')
        return target

    def checked(self, path):
        return validate_delivery(path, 4, expected_texts=self.expected['texts'],
                                 expected_images=self.expected['images'], expected_tables=self.expected['tables'],
                                 expected_charts=self.expected['charts'], expected_sources=[
                                     slide['sources'] + self.expected['source_notes'][index]
                                     for index, slide in enumerate(self.plan['slides'])])

    def test_expectations_cover_new_visible_fields_and_index_bindings_from_plan(self):
        for row in self.expected['texts']:
            self.assertIn(f"{self.note['label']} [{self.note['source_index']}]", row)
            self.assertIn(self.note['text'], row)
            self.assertIn(self.visible, row)
            self.assertNotIn('Keep the original speaker notes.', row)
        self.assertEqual(self.expected['source_notes'][0], [
            f"证据说明 [1] {self.note['label']}：{self.note['text']}"])
        for change in ({'source_index': True}, {'source_index': 2}, {'text': None}, {'label': 'x' * 25}):
            changed = copy.deepcopy(self.plan)
            changed['slides'][0]['evidence_notes'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                plan_expectations(changed)
        legacy = copy.deepcopy(self.plan)
        legacy['slides'][0].pop('archetype')
        with self.assertRaises(ValueError):
            plan_expectations(legacy)

    def test_real_native_package_retains_exact_figure_and_positional_table_chart_data(self):
        report = {'errors': [], 'warnings': []}
        texts, notes = _read_package(self.pptx, report, include_chart_data=True, include_table_data=True,
                                     expected_images=self.expected['images'])
        for index, expected in enumerate(self.expected['texts']):
            self.assertEqual(_missing_texts(expected, '\n'.join(texts[index])), [])
            for source in self.plan['slides'][index]['sources'] + self.expected['source_notes'][index]:
                self.assertIn(source, notes[index])
            _check_image_plan(report['planned_image_data'][index], self.expected['images'][index], report, index + 1)
            _check_table_plan(report['native_table_data'][index], self.expected['tables'][index], report, index + 1)
            _check_chart_plan(report['native_chart_data'][index], self.expected['charts'][index], report, index + 1)
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['planned_image_data'][0][0]['sha256'], hashlib.sha256(self.image_bytes).hexdigest())
        self.assertEqual(report['native_table_data'][1][0], self.plan['slides'][1]['table'])
        self.assertEqual(report['native_chart_data'][2][0]['series'][0]['values'], ['87.5', '92.2'])
        self.assertEqual(len(report['structure']['checked_chart_workbooks']), 1)
        self.assertTrue(report['structure']['each_slide_has_editable_text'])

    def test_removing_new_body_or_visible_citation_is_detected_against_independent_plan(self):
        for label, needle, expected in [
            ('label', self.note['label'], f"{self.note['label']} [{self.note['source_index']}]"),
            ('condition', self.note['text'], self.note['text']), ('citation', self.visible, self.visible)]:
            target = self.changed('missing-' + label + '.pptx', lambda name, raw:
                                  raw.replace(needle.encode('utf-8'), b'') if name == 'ppt/slides/slide1.xml' else raw)
            report = {'errors': [], 'warnings': []}
            actual, _ = _read_package(target, report)
            with self.subTest(field=label):
                self.assertIn(expected, _missing_texts(self.expected['texts'][0], '\n'.join(actual[0])))

    def test_real_render_or_explicit_dependency_failure_covers_all_scientific_pages(self):
        report = self.checked(self.pptx)
        self.assertEqual(report['scientific_quality'], 'not_reviewed')
        if not (shutil.which('libreoffice') or shutil.which('soffice')):
            self.assertFalse(report['passed'])
            self.assertIn('libreoffice_missing', {row['code'] for row in report['errors']})
        else:
            self.assertTrue(report['passed'], report['errors'])
            self.assertEqual(report['pdf_page_count'], 4)
            self.assertEqual([row['missing_items'] for row in report['text_retention']['pages']], [0, 0, 0, 0])
            self.assertTrue(report['human_visual_review_required'])

    def test_wrong_note_binding_fails_even_when_all_visible_text_and_original_source_remain(self):
        original = f"证据说明 [1] {self.note['label']}：{self.note['text']}".encode('utf-8')
        wrong = original.replace(b'[1]', b'[2]', 1)
        target = self.changed('wrong-source-binding.pptx', lambda name, raw:
                              raw.replace(original, wrong) if name == 'ppt/notesSlides/notesSlide1.xml' else raw)
        report = self.checked(target)
        self.assertFalse(report['passed'])
        self.assertIn('source_notes_missing', {row['code'] for row in report['errors']})
        self.assertNotIn('submitted_text_missing_in_pptx', {row['code'] for row in report['errors']})

    def test_wrong_visible_note_index_fails_while_speaker_notes_and_footer_still_match(self):
        label = f"{self.note['label']} [1]".encode('utf-8')
        target = self.changed('wrong-visible-binding.pptx', lambda name, raw:
                              raw.replace(label, label.replace(b'[1]', b'[2]', 1))
                              if name == 'ppt/slides/slide1.xml' else raw)
        report = self.checked(target)
        self.assertFalse(report['passed'])
        self.assertIn('submitted_text_missing_in_pptx', {row['code'] for row in report['errors']})
        self.assertNotIn('source_notes_missing', {row['code'] for row in report['errors']},
                         'notes保持正确仍不能授权展示错误索引的页面')

    def test_service_revision_preserves_non_target_dependencies_and_rejects_implicit_source_rebinding(self):
        primary = self.area / 'primary.pdf'
        secondary = self.area / 'secondary.pdf'
        write_pdf(primary, 'Public synthetic original evidence and measured results.')
        write_pdf(secondary, 'Public synthetic independent replacement evidence.')
        service = PPTService(prepare([primary, secondary], 'Scientific revision fixture', 2, True))
        first = service.pin_source('doc_1')['source_id']
        second = service.pin_source('doc_2')['source_id']
        service.read_source(first)
        service.read_source(second)
        plan = {'title': 'Local scientific revision', 'slides': [
            {'title': 'Measured results', 'bullets': [], 'archetype': 'result-summary',
             'table': self.plan['slides'][1]['table'], 'sources': [{'source_id': first, 'page': 1}],
             'evidence_notes': [copy.deepcopy(self.note)]},
            {'title': 'Unchanged conclusion', 'bullets': ['Keep this original text and its source.'],
             'sources': [{'source_id': first, 'page': 1}], 'notes': 'Keep non-target notes.'},
        ]}
        rejected = copy.deepcopy(plan)
        rejected['slides'][0]['visible_sources'] = ['Invented visible citation']
        with self.assertRaises(ValueError):
            service.render_deck(rejected)
        rendered = service.render_deck(plan)
        original_hash = file_hash(Path(rendered['path']))
        request = service.read_deck_plan(rendered['deck_id'])['plan']
        self.assertNotIn('visible_sources', request['slides'][0], '宿主派生字段不得回流成为用户可写字段')
        invalid = [{'page': 1, 'changes': {'sources': [{'source_id': second, 'page': 1}]}}]
        with self.assertRaises(ValueError):
            service.revise_deck(rendered['deck_id'], invalid)
        revised = service.revise_deck(rendered['deck_id'], [{'page': 1, 'changes': {
            'evidence_notes': [{**self.note, 'text': 'Corrected explicit condition, still on the same source.'}]}}])
        audit = verify_unmodified_slides(Path(rendered['path']), Path(revised['path']), [1])
        self.assertTrue(audit['passed'])
        self.assertEqual(audit['checked_pages'], [2])
        self.assertEqual(len(audit['page_evidence'][0]['semantic_sha256']), 64)
        self.assertEqual(file_hash(Path(rendered['path'])), original_hash)
        self.assertEqual(service.read_deck_plan(revised['deck_id'])['plan']['slides'][1], plan['slides'][1])
        # 来源与说明一同显式更新才允许建立新关联；新稿需再次独立验收。
        rebound = service.revise_deck(revised['deck_id'], [{'page': 1, 'changes': {
            'sources': [{'source_id': second, 'page': 1}], 'evidence_notes': [copy.deepcopy(self.note)]}}])
        self.assertEqual(service.read_deck_plan(rebound['deck_id'])['plan']['slides'][0]['sources'],
                         [{'source_id': second, 'page': 1}])
        # 人工篡改已经生成的notes索引，更新文件版本以隔离内容oracle；服务必须独立拒绝。
        target = Path(rebound['path'])
        tampered = target.with_suffix('.wrong-binding.pptx')
        needle = f"证据说明 [1] {self.note['label']}：{self.note['text']}".encode('utf-8')
        modifications = 0
        with zipfile.ZipFile(target) as original, zipfile.ZipFile(tampered, 'w') as result:
            for item in original.infolist():
                raw = original.read(item.filename)
                if item.filename == 'ppt/notesSlides/notesSlide1.xml':
                    altered = raw.replace(needle, needle.replace(b'[1]', b'[2]', 1))
                    modifications += altered != raw
                    raw = altered
                result.writestr(item, raw)
        self.assertEqual(modifications, 1)
        tampered.replace(target)
        service.deck_records[rebound['deck_id']]['sha256'] = file_hash(target)
        validation = service.validate_deck(rebound['deck_id'])
        self.assertFalse(validation['passed'])
        self.assertIn('source_notes_missing', {row['code'] for row in validation['errors']})
        with self.assertRaises(ValueError):
            service.deliver_deck(validation['validation_id'])


if __name__ == '__main__':
    unittest.main()
