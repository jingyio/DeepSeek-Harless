"""真实 LibreOffice/PyMuPDF 文件验收；全部在服务器运行。"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from scenarios.research_ppt.validation import ROOT, validate_delivery


class DeliveryValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        area = ROOT / '.local/research-ppt/validation-tests'
        area.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=area)
        cls.directory = Path(cls.temporary.name)
        cls.pptx = cls.directory / 'presentation.pptx'
        cls.plan = {
            'title': 'Research validation',
            'slides': [
                {'title': '真实渲染验收', 'bullets': ['论文结构必须保留来源。'],
                 'sources': ['paper.pdf 第 2 页; SHA256 test'], 'notes': '内容质量需要单独评审。'},
                {'title': 'Editable text', 'bullets': ['Evidence remains editable.'],
                 'sources': ['paper.pdf page 3; SHA256 test'],
                 'chart': {'type': 'bar', 'categories': ['A', 'B'],
                           'series': [{'name': 'Measured', 'values': [1.2, 2.4]}]}},
            ],
        }
        plan_path = cls.directory / 'plan.json'
        plan_path.write_text(json.dumps(cls.plan, ensure_ascii=False), encoding='utf-8')
        subprocess.run(['node', str(ROOT / 'scenarios/research_ppt/dist/render.js'),
                        str(plan_path), str(cls.pptx)], check=True, capture_output=True, timeout=90)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_render_preview_and_text_retention(self):
        report = validate_delivery(self.pptx, 2,
            [['真实渲染验收', '论文结构必须保留来源。'], ['Editable text', 'Evidence remains editable.']],
            [['paper.pdf 第 2 页; SHA256 test'], ['paper.pdf page 3; SHA256 test']])
        self.assertTrue(report['passed'], report['errors'])
        self.assertEqual(report['pdf_page_count'], 2)
        self.assertEqual(report['structure']['notes_count'], 2)
        self.assertTrue(report['structure']['each_slide_has_editable_text'])
        self.assertEqual(report['structure']['editable_chart_count'], 1)
        self.assertEqual(len(report['structure']['checked_chart_workbooks']), 1)
        self.assertEqual(len([x for x in report['artifacts'] if x['kind'] == 'preview']), 2)
        self.assertEqual(report['scientific_quality'], 'not_reviewed')
        for artifact in report['artifacts']:
            self.assertTrue(Path(artifact['path']).is_file())
            self.assertEqual(len(artifact['sha256']), 64)

    def test_missing_submitted_text_and_sources_fail_with_evidence(self):
        report = validate_delivery(self.pptx, 2,
            [['This text was never submitted.'], ['Editable text']],
            [['missing-paper.pdf 第 99 页'], []])
        self.assertFalse(report['passed'])
        codes = {issue['code'] for issue in report['errors']}
        self.assertIn('submitted_text_missing_in_pptx', codes)
        self.assertIn('source_notes_missing', codes)
        self.assertIn('text_missing_in_render', codes)
        self.assertTrue(Path(report['report_path']).is_file())
        self.assertTrue(any(x['kind'] == 'preview' for x in report['artifacts']))

    def test_rejects_private_path_escape_and_invalid_expected_shape(self):
        with self.assertRaisesRegex(ValueError, '.local'):
            validate_delivery(ROOT / 'README.pptx', 2)
        with self.assertRaises(ValueError):
            validate_delivery(self.pptx, 2, [['one page']])

    def test_rejects_external_resource_before_rendering(self):
        unsafe = self.directory / 'external.pptx'
        with zipfile.ZipFile(self.pptx) as original, zipfile.ZipFile(unsafe, 'w') as changed:
            for item in original.infolist():
                content = original.read(item.filename)
                if item.filename == 'ppt/slides/_rels/slide1.xml.rels':
                    content = content.replace(b'</Relationships>',
                        b'<Relationship Id="remote" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="https://example.com/image.png" TargetMode="External"/></Relationships>')
                changed.writestr(item, content)
        report = validate_delivery(unsafe, 2)
        self.assertFalse(report['passed'])
        self.assertIn('外部资源', str(report['errors']))
        self.assertEqual(report['artifacts'], [])

    def test_embedded_chart_workbook_with_external_relationship_is_rejected(self):
        unsafe = self.directory / 'external-workbook.pptx'
        with zipfile.ZipFile(self.pptx) as original, zipfile.ZipFile(unsafe, 'w') as changed:
            for item in original.infolist():
                content = original.read(item.filename)
                if item.filename.startswith('ppt/embeddings/') and item.filename.endswith('.xlsx'):
                    import io
                    altered = io.BytesIO()
                    with zipfile.ZipFile(io.BytesIO(content)) as workbook, zipfile.ZipFile(altered, 'w') as modified:
                        for inner in workbook.infolist():
                            modified.writestr(inner, workbook.read(inner.filename))
                        modified.writestr('xl/worksheets/_rels/unsafe.xml.rels',
                            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="remote" Type="image" Target="https://example.com/private" TargetMode="External"/></Relationships>')
                    content = altered.getvalue()
                changed.writestr(item, content)
        report = validate_delivery(unsafe, 2)
        self.assertFalse(report['passed'])
        self.assertIn('外部资源', str(report['errors']))
        self.assertEqual(report['artifacts'], [])


if __name__ == '__main__':
    unittest.main()
