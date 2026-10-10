"""Real PDF geometry diagnostics; these synthetic cases do not measure task quality."""
from pathlib import Path
import tempfile
import unittest
import fitz
from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash, pdf_page_geometry
from scenarios.research_ppt.service import ROOT, PPTService


class FigureGeometryTests(unittest.TestCase):
    def setUp(self):
        area = ROOT / '.local/research-ppt/unit-tests'
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.path = Path(self.temp.name) / 'geometry.pdf'
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((50, 70), 'An actual vector drawing follows; these words are body text.')
            page.draw_rect(fitz.Rect(100, 150, 300, 300), color=(0, 0, 0))
            page.draw_line((100, 150), (300, 300), color=(0, 0, 0))
            page.insert_text((100, 320), 'Figure 1: A vector drawing used for geometry diagnostics.')
            second = pdf.new_page(width=600, height=800)
            second.insert_text((50, 70), 'Figure 2: This caption has no graphical content above it.')
            pdf.save(self.path)
        self.job = prepare([self.path], 'Test actual geometric crop boundaries', 1, True)
        self.service = PPTService(self.job)
        self.source = self.service.pin_source('doc_1')['source_id']

    def tearDown(self):
        self.temp.cleanup()

    def test_vector_candidate_carries_caption_and_extracts(self):
        page = self.service.read_page(self.source, 1)
        candidate = page['figure_candidates'][0]
        self.assertIn('Figure 1:', candidate['caption'])
        self.assertEqual(candidate['evidence_types'], ['vector_graphic'])
        result = self.service.extract_figure(self.source, 1, candidate_id=candidate['candidate_id'])
        self.assertEqual(result['caption'], candidate['caption'])
        self.assertEqual(result['evidence_scope'], 'caption_geometry_candidate')
        self.assertFalse(candidate['semantic_verified'])

    def test_caption_without_graphics_abstains(self):
        page = pdf_page_geometry(self.path, 2, file_hash(self.path))
        self.assertEqual(page['figure_candidates'], [])
        self.assertEqual(page['figure_localization'], 'abstained')
        self.assertTrue(page['unresolved_captions'])
        with self.assertRaisesRegex(ValueError, '几何证据'):
            self.service.extract_figure(self.source, 2, [0.05, 0.02, 0.95, 0.2])

    def test_body_crop_and_fabricated_candidate_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '几何证据'):
            self.service.extract_figure(self.source, 1, [0.02, 0.02, 0.95, 0.15])
        with self.assertRaisesRegex(ValueError, '候选不存在'):
            self.service.extract_figure(self.source, 1, candidate_id='figure-fabricated')

    def test_full_page_is_evidence_only_and_version_change_blocks(self):
        result = self.service.extract_figure(self.source, 1, [0, 0, 1, 1])
        self.assertEqual(result['evidence_scope'], 'page_evidence')
        self.assertIsNone(result['caption'])
        with self.path.open('ab') as stream:
            stream.write(b'\n% changed version\n')
        with self.assertRaisesRegex(ValueError, '版本已变化'):
            self.service.read_page(self.source, 1)


if __name__ == '__main__':
    unittest.main()
