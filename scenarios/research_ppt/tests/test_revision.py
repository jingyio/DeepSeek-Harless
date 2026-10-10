"""服务器真实 PPTX 的局部修订回归；不使用模拟 Provider 或固定工具返回值。"""
import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image

from scenarios.research_ppt.revision import merge_slide_updates, verify_unmodified_slides


ROOT = Path(__file__).resolve().parents[3]
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def image_data(color):
    out = io.BytesIO()
    Image.new('RGB', (240, 120), color).save(out, format='PNG')
    return out.getvalue()


def write_changed_package(source, target, change):
    with zipfile.ZipFile(source) as archive:
        parts = {info.filename: archive.read(info.filename)
                 for info in archive.infolist() if not info.is_dir()}
    change(parts)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def change_xml(parts, path, mutate):
    root = ET.fromstring(parts[path])
    mutate(root)
    parts[path] = ET.tostring(root, encoding='utf-8', xml_declaration=True)


class MergeRevisionTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'title': 'Existing deck', 'template': 'lab', 'slides': [
            {'title': 'First', 'bullets': ['Keep body'], 'sources': ['paper.pdf page 2'],
             'notes': 'Conditions and limitations', 'image': {'source_id': 'source-a', 'image_id': 'fig-1'}},
            {'title': 'Second', 'bullets': ['Do not change'], 'sources': ['paper.pdf page 3'],
             'notes': 'Keep this note'}]}

    def test_only_explicit_page_fields_change_and_no_input_aliases(self):
        original = copy.deepcopy(self.plan)
        updates = [{'page': 1, 'changes': {'title': 'Corrected', 'bullets': ['New claim']}}]
        merged = merge_slide_updates(self.plan, updates)
        self.assertEqual(self.plan, original)
        self.assertEqual(merged['slides'][1], original['slides'][1])
        self.assertEqual(merged['slides'][0]['sources'], original['slides'][0]['sources'])
        self.assertEqual(merged['slides'][0]['notes'], original['slides'][0]['notes'])
        self.assertEqual(merged['slides'][0]['image'], original['slides'][0]['image'])
        merged['slides'][1]['bullets'].append('No alias')
        updates[0]['changes']['bullets'].append('No update alias')
        self.assertEqual(self.plan, original)
        self.assertEqual(merged['slides'][0]['bullets'], ['New claim'])

    def test_sources_notes_and_media_removal_must_be_explicit(self):
        new_sources = [{'source_id': 'source-b', 'page': 4}]
        merged = merge_slide_updates(self.plan, [{'page': 1, 'changes': {
            'image': None, 'layout': 'content', 'sources': new_sources, 'notes': 'Updated conditions'}}])
        self.assertNotIn('image', merged['slides'][0])
        self.assertEqual(merged['slides'][0]['sources'], new_sources)
        self.assertEqual(merged['slides'][0]['notes'], 'Updated conditions')
        self.assertEqual(len(merged['slides']), len(self.plan['slides']))
        # Changing a layout does not implicitly remove an existing image.
        incompatible = merge_slide_updates(self.plan, [{'page': 1, 'changes': {'layout': 'table'}}])
        self.assertIn('image', incompatible['slides'][0])

    def test_rejects_duplicate_out_of_range_boolean_and_unknown_fields_atomically(self):
        original = copy.deepcopy(self.plan)
        invalid = [[], {}, [{'page': 0, 'changes': {'title': 'x'}}],
            [{'page': 3, 'changes': {'title': 'x'}}], [{'page': True, 'changes': {'title': 'x'}}],
            [{'page': 1, 'changes': {'title': 'x'}}, {'page': 1, 'changes': {'title': 'y'}}],
            [{'page': 1, 'changes': {}}], [{'page': 1, 'changes': {'filename': 'outside'}}],
            [{'page': 1, 'changes': {'title': 'x'}, 'slides': []}],
            [{'page': 1, 'changes': {'title': 'valid'}}, {'page': 2, 'changes': {'notes': None}}]]
        for updates in invalid:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                merge_slide_updates(self.plan, updates)
            self.assertEqual(self.plan, original)

    def test_rejects_invalid_nested_types_control_characters_and_nonfinite_data(self):
        invalid = [{'title': 3}, {'title': 'bad\x00text'}, {'bullets': 'text'},
            {'bullets': [None]}, {'sources': []}, {'sources': [{'source_id': 's', 'page': True}]},
            {'sources': [{'source_id': 's', 'page': 1, 'path': 'unsafe'}]}, {'notes': None},
            {'table': [['a', 'b'], ['c']]},
            {'chart': {'type': 'bar', 'categories': ['A', 'B'],
                       'series': [{'name': 'x', 'values': [1, float('nan')]}]}},
            {'chart': {'type': 'bar', 'categories': ['A', 'B'],
                       'series': [{'name': 'x', 'values': [True, 2]}]}},
            {'image': {'data': 'image/png;base64,AA==', 'width': True, 'height': 2}},
            {'comparison': {'left': {'title': 'A', 'bullets': []},
                            'right': {'title': 'B', 'bullets': [], 'extra': True}}},
            {'process': {'steps': [{'label': 'One', 'detail': 'x'}]}}, {'layout': 'unknown'}]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                merge_slide_updates(self.plan, [{'page': 1, 'changes': changes}])


class RealOOXMLRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        area = ROOT / '.local/research-ppt/revision-tests'
        area.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=area)
        cls.directory = Path(cls.temporary.name)
        cls.plan = {'title': 'Real revision regression', 'template': 'academic', 'slides': [
            {'title': 'Target page', 'bullets': ['Original claim'],
             'sources': ['paper.pdf page 1'], 'notes': 'Original target note'},
            {'title': 'Keep table', 'bullets': [], 'table': [['Metric', 'Value'], ['Observed', '12']],
             'sources': ['paper.pdf page 2'], 'notes': 'Keep table conditions'},
            {'title': 'Keep chart', 'bullets': [], 'chart': {'type': 'bar', 'categories': ['A', 'B'],
                'series': [{'name': 'Measured', 'values': [1.2, 2.4]}]},
             'sources': ['paper.pdf page 3'], 'notes': 'Keep chart conditions'},
            {'title': 'Keep image', 'bullets': [], 'image': {
                'data': 'image/png;base64,' + base64.b64encode(image_data('navy')).decode(),
                'width': 240, 'height': 120},
             'sources': ['paper.pdf page 4'], 'notes': 'Keep original image source'}]}
        cls.before = cls.directory / 'before.pptx'
        cls.after = cls.directory / 'after.pptx'
        changed = merge_slide_updates(cls.plan, [{'page': 1, 'changes': {
            'title': 'Corrected target page', 'bullets': ['Corrected claim'], 'notes': 'Corrected conditions'}}])
        for name, plan, target in [('before', cls.plan, cls.before), ('after', changed, cls.after)]:
            plan_path = cls.directory / f'{name}.json'
            plan_path.write_text(json.dumps(plan), encoding='utf-8')
            subprocess.run(['node', str(ROOT / 'scenarios/research_ppt/dist/render.js'),
                            str(plan_path), str(target)], check=True, capture_output=True, timeout=90)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tamper(self, name, mutate, expected='非目标'):
        changed = self.directory / (name + '.pptx')
        write_changed_package(self.after, changed, mutate)
        with self.assertRaisesRegex(ValueError, expected):
            verify_unmodified_slides(self.before, changed, [1])

    def test_real_rerender_preserves_non_target_table_chart_image_notes_and_styles(self):
        report = verify_unmodified_slides(self.before, self.after, [1])
        self.assertTrue(report['passed'])
        self.assertEqual(report['checked_pages'], [2, 3, 4])
        self.assertEqual(report['slide_count'], 4)
        self.assertTrue(all(len(row['semantic_sha256']) == 64 for row in report['page_evidence']))
        self.assertIn('chart_xml_and_embedded_workbook', report['checks'])

    def test_container_timestamps_part_names_and_relationship_ids_are_not_content(self):
        def rename(parts):
            relpath = 'ppt/slides/_rels/slide4.xml.rels'
            rels = ET.fromstring(parts[relpath])
            image_rel = next(rel for rel in rels if rel.get('Type').endswith('/image'))
            original_id = image_rel.get('Id')
            original_target = image_rel.get('Target')
            original_name = 'ppt/' + original_target.removeprefix('../')
            new_name = 'ppt/media/renumbered-preserved.png'
            parts[new_name] = parts.pop(original_name)
            image_rel.set('Id', 'renumbered-image')
            image_rel.set('Target', '../media/renumbered-preserved.png')
            parts[relpath] = ET.tostring(rels, encoding='utf-8')
            def update(root):
                for item in root.iter():
                    if item.get('{' + R + '}embed') == original_id:
                        item.set('{' + R + '}embed', 'renumbered-image')
            change_xml(parts, 'ppt/slides/slide4.xml', update)
            def content_types(root):
                for item in root:
                    if item.get('PartName') == '/' + original_name:
                        item.set('PartName', '/' + new_name)
            change_xml(parts, '[Content_Types].xml', content_types)
        renamed = self.directory / 'renumbered.pptx'
        write_changed_package(self.after, renamed, rename)
        self.assertTrue(verify_unmodified_slides(self.before, renamed, [1])['passed'])

    def test_non_target_text_table_geometry_and_notes_changes_are_rejected(self):
        def replace_text(root):
            next(node for node in root.iter('{' + A + '}t') if node.text == '12').text = '99'
        self.tamper('table-data', lambda parts: change_xml(parts, 'ppt/slides/slide2.xml', replace_text))
        def shift(root):
            node = next(root.iter('{' + A + '}off'))
            node.set('x', str(int(node.get('x')) + 914400))
        self.tamper('geometry', lambda parts: change_xml(parts, 'ppt/slides/slide2.xml', shift))
        def notes(root):
            next(node for node in root.iter('{' + A + '}t') if node.text and 'Keep table conditions' in node.text).text = 'Tampered conditions'
        self.tamper('notes', lambda parts: change_xml(parts, 'ppt/notesSlides/notesSlide2.xml', notes))

    def test_non_target_media_chart_cache_and_embedded_workbook_changes_are_rejected(self):
        def media(parts):
            name = next(name for name in parts if name.startswith('ppt/media/') and name.endswith('.png'))
            parts[name] = image_data('red')
        self.tamper('media', media)
        def chart(parts):
            name = next(name for name in parts if name.startswith('ppt/charts/') and name.endswith('.xml'))
            def value(root):
                next(node for node in root.iter('{' + C + '}v') if node.text == '1.2').text = '99'
            change_xml(parts, name, value)
        self.tamper('chart-cache', chart)
        def workbook(parts):
            name = next(name for name in parts if name.startswith('ppt/embeddings/') and name.endswith('.xlsx'))
            changed = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(parts[name])) as archive, zipfile.ZipFile(changed, 'w') as out:
                for inner in archive.infolist():
                    raw = archive.read(inner.filename)
                    if inner.filename == 'xl/worksheets/sheet1.xml':
                        root = ET.fromstring(raw)
                        next(node for node in root.iter('{' + S + '}v') if node.text == '1.2').text = '99'
                        raw = ET.tostring(root, encoding='utf-8')
                    out.writestr(inner, raw)
            parts[name] = changed.getvalue()
        self.tamper('chart-workbook', workbook)

    def test_shared_theme_and_global_dimensions_changes_are_rejected(self):
        def theme(parts):
            name = next(name for name in parts if name.startswith('ppt/theme/') and name.endswith('.xml'))
            def mutate(root):
                next(root.iter('{' + A + '}srgbClr')).set('val', '123456')
            change_xml(parts, name, mutate)
        self.tamper('theme', theme, '共享')
        self.tamper('global-size', lambda parts: change_xml(parts, 'ppt/presentation.xml',
            lambda root: root.find('{' + P + '}sldSz').set('cx', '9000000')), '共享')

    def test_page_count_invalid_page_sets_and_malformed_relationships_are_rejected(self):
        self.tamper('removed-page', lambda parts: change_xml(parts, 'ppt/presentation.xml',
            lambda root: root.find('{' + P + '}sldIdLst').remove(
                list(root.find('{' + P + '}sldIdLst'))[-1])), '总页数')
        for pages in ([], [True], [1, 1], [0], [5], '1'):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                verify_unmodified_slides(self.before, self.after, pages)
        def external(parts):
            def mutate(root):
                root.append(ET.Element('{' + PKG + '}Relationship', {
                    'Id': 'external', 'Type': R + '/image', 'Target': 'https://example.com/image.png',
                    'TargetMode': 'External'}))
            change_xml(parts, 'ppt/slides/_rels/slide1.xml.rels', mutate)
        self.tamper('external', external, '外部')
        def missing(parts):
            def mutate(root):
                next(rel for rel in root if rel.get('Type').endswith('/image')).set('Target', '../media/missing.png')
            change_xml(parts, 'ppt/slides/_rels/slide4.xml.rels', mutate)
        self.tamper('missing-media', missing, '缺失')


if __name__ == '__main__':
    unittest.main()
