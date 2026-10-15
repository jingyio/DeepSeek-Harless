"""Real PDF geometry diagnostics; these synthetic cases do not measure task quality."""
from pathlib import Path
import json
import tempfile
import unittest
import fitz
from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash, pdf_page_geometry
from scenarios.research_ppt.service import ROOT, PPTService
from scenarios.research_ppt.server import _safe_failure


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
        self.job = prepare([self.path], 'Test actual geometric crop boundaries', 1, True, persistent_library=False)
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

    def diagnostic_page(self, name, *, independent_caption=False, body_between=False):
        path = Path(self.temp.name) / name
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.draw_rect(fitz.Rect(65, 150, 280, 300), color=(0, 0, 0))
            page.draw_line((65, 150), (280, 300), color=(0, 0, 0))
            page.draw_rect(fitz.Rect(320, 150, 550, 300), color=(0, 0, 0))
            page.draw_line((320, 300), (550, 150), color=(0, 0, 0))
            page.insert_text((70, 138), '(a) left panel')
            page.insert_text((325, 138), '(b) right panel')
            page.insert_text((65, 325), 'Figure 3: Two panels.')
            if independent_caption:
                page.insert_text((320, 325), 'Figure 4: An independent panel.')
            if body_between:
                page.insert_textbox(fitz.Rect(285, 150, 317, 310),
                                    'This is unrelated body prose between figures. ' * 5, fontsize=4)
            pdf.save(path)
        return path

    def test_short_caption_does_not_truncate_composite_right_panel_or_labels(self):
        path = self.diagnostic_page('composite.pdf')
        result = pdf_page_geometry(path, 1, file_hash(path))
        self.assertEqual(result['geometry_version'], 2)
        self.assertEqual(len(result['figure_candidates']), 1)
        candidate = result['figure_candidates'][0]
        self.assertGreater(candidate['bbox'][2], 550 / 600)
        self.assertLess(candidate['bbox'][1], 138 / 800)
        self.assertFalse(candidate['semantic_verified'])

    def test_aligned_independent_figures_are_not_silently_merged(self):
        path = self.diagnostic_page('independent.pdf', independent_caption=True)
        result = pdf_page_geometry(path, 1, file_hash(path))
        self.assertEqual(result['figure_candidates'], [])
        self.assertEqual(result['figure_localization'], 'abstained')
        self.assertTrue(result['unresolved_captions'])

    def test_composite_expansion_cannot_swallow_unrelated_prose(self):
        path = self.diagnostic_page('prose.pdf', body_between=True)
        result = pdf_page_geometry(path, 1, file_hash(path))
        self.assertEqual(result['figure_candidates'], [])
        self.assertTrue(result['unresolved_captions'])

    def test_same_line_independent_captions_abstain(self):
        path = Path(self.temp.name) / 'same-line-captions.pdf'
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.draw_rect(fitz.Rect(65, 150, 550, 300))
            page.insert_text((65, 325), 'Figure 3: Left. Figure 4: Right.')
            pdf.save(path)
        result = pdf_page_geometry(path, 1, file_hash(path))
        self.assertEqual(result['figure_candidates'], [])
        self.assertTrue(result['unresolved_captions'])

    def test_direct_geometry_reader_rejects_invalid_page_and_stale_version(self):
        with self.assertRaisesRegex(ValueError, '页码越界'):
            pdf_page_geometry(self.path, 0, file_hash(self.path))
        with self.assertRaisesRegex(ValueError, '版本已变化'):
            pdf_page_geometry(self.path, 1, '0' * 64)

    def test_publisher_caption_without_punctuation_retains_all_geometry_guards(self):
        path = Path(self.temp.name) / 'publisher-caption.pdf'
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.draw_rect(fitz.Rect(100, 150, 400, 300))
            page.insert_text((100, 320), 'Figure 12 Complete drawing without punctuation after number.')
            empty = pdf.new_page(width=600, height=800)
            empty.insert_text((100, 320), 'Figure 13 Mention with no adjacent drawing.')
            pdf.save(path)
        value = pdf_page_geometry(path, 1, file_hash(path))
        self.assertEqual(len(value['figure_candidates']), 1)
        self.assertTrue(value['figure_candidates'][0]['caption'].startswith('Figure 12 '))
        self.assertEqual(pdf_page_geometry(path, 2, file_hash(path))['figure_candidates'], [])

    def figure_plan(self, image, *, title='Figure 1', page=1):
        return {'title': 'Geometry check', 'template': 'lab', 'slides': [{
            'title': title, 'layout': 'image', 'bullets': [], 'sources': [{'source_id': self.source, 'page': page}],
            'image': {'source_id': self.source, 'image_id': image['image_id']}, 'notes': 'Synthetic geometry diagnostic.'}]}

    def test_new_pdf_jobs_require_complete_figure_evidence_and_matching_page_number(self):
        self.assertEqual(self.service.job['figure_evidence_policy'], 'caption-geometry-v1')
        candidate = self.service.read_page(self.source, 1)['figure_candidates'][0]
        crop = self.service.extract_figure(self.source, 1, candidate_id=candidate['candidate_id'])
        with self.assertRaisesRegex(ValueError, '真实来源页'):
            self.service.render_deck(self.figure_plan(crop, page=2))
        with self.assertRaisesRegex(ValueError, '图号'):
            self.service.render_deck(self.figure_plan(crop, title='原文图 2'))
        rendered = self.service.render_deck(self.figure_plan(crop))
        self.assertEqual(rendered['slide_count'], 1)
        self.assertTrue(rendered['each_slide_has_editable_text'])

    def test_whole_page_and_same_page_embedded_assets_cannot_impersonate_figures(self):
        whole = self.service.extract_figure(self.source, 1, [0, 0, 1, 1])
        with self.assertRaisesRegex(ValueError, '完整原图'):
            self.service.render_deck(self.figure_plan(whole))
        # A real image byte payload with its trust metadata removed models an
        # embedded asset; page equality alone cannot authorize a figure claim.
        asset = dict(self.service.source(self.source)['parsed']['images'][-1])
        asset['image_id'] = 'embedded-diagnostic'
        asset.pop('evidence_scope', None)
        self.service.source(self.source)['parsed']['images'].append(asset)
        with self.assertRaisesRegex(ValueError, '完整原图'):
            self.service.render_deck(self.figure_plan(asset))

    def minimum_service(self, minimum=2, *, duplicate_source=False, same_page=False):
        path = Path(self.temp.name) / ('same-page-figures.pdf' if same_page else 'two-figures.pdf')
        with fitz.open() as pdf:
            if same_page:
                page = pdf.new_page(width=600, height=800)
                for number, top in ((1, 100), (2, 450)):
                    page.draw_rect(fitz.Rect(100, top, 400, top + 100))
                    page.insert_text((100, top + 120), f'Figure {number}: Synthetic complete drawing.')
            else:
                for number in (1, 2):
                    page = pdf.new_page(width=600, height=800)
                    page.draw_rect(fitz.Rect(100, 150, 400, 300))
                    page.insert_text((100, 320), f'Figure {number}: Synthetic complete drawing.')
            pdf.save(path)
        job = prepare([path, path] if duplicate_source else [path], '显式两张完整原图合同', 2, True,
                      persistent_library=False, minimum_original_figures=minimum)
        service = PPTService(job)
        handles = [service.pin_source(row['document_id'])['source_id'] for row in service.job['inputs']]
        for handle in handles:
            service.read_source(handle)
        return service, handles

    @staticmethod
    def original_figure_plan(rows):
        return {'title': 'Distinct original figures', 'template': 'lab', 'slides': [
            {'title': 'Original figure evidence', 'layout': 'image', 'bullets': [],
             'sources': [{'source_id': handle, 'page': image['page']}],
             'image': {'source_id': handle, 'image_id': image['image_id']}}
            for handle, image in rows]}

    def test_minimum_original_figures_is_explicit_frozen_and_zero_compatible(self):
        data = json.loads(self.job.read_text(encoding='utf-8'))
        self.assertEqual(data['minimum_original_figures'], 0)
        data.pop('minimum_original_figures')
        self.job.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(PPTService(self.job).list_inputs()['minimum_original_figures'], 0)
        for value in (True, -1, 1.5, '1', 3):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'minimum_original_figures'):
                prepare([self.path], 'Invalid explicit minimum', 2, minimum_original_figures=value)
        with self.assertRaisesRegex(ValueError, 'restyle'):
            prepare([self.path], 'Restyle keeps its existing contract', 2,
                    operation='restyle', minimum_original_figures=1)
        with self.assertRaisesRegex(ValueError, 'PDF 输入'):
            prepare([Path(self.temp.name) / 'only.pptx'], 'PPTX cannot supply PDF candidates', 2,
                    minimum_original_figures=1)
        service, _ = self.minimum_service()
        self.assertEqual(service.job['minimum_original_figures'], 2)
        self.assertEqual(service.list_inputs()['minimum_original_figures'], 2)

    def test_missing_original_figures_rejects_before_creating_output_with_safe_feedback(self):
        service, handles = self.minimum_service()
        plan = {'title': 'No source figures', 'slides': [
            {'title': 'Actual source text', 'bullets': ['Synthetic text-only diagnostic.'],
             'sources': [{'source_id': handles[0], 'page': page}]} for page in (1, 2)]}
        with self.assertRaisesRegex(ValueError, '完整原图数量') as failure:
            service.render_deck(plan)
        self.assertFalse(service.output.exists())
        self.assertEqual(service.decks, {})
        self.assertEqual(_safe_failure(failure.exception)['error'], 'insufficient_original_figures')
        hidden = _safe_failure(ValueError(str(failure.exception) + ' credential=secret'))
        self.assertEqual(hidden['error'], 'internal_processing_failed')
        self.assertNotIn('secret', json.dumps(hidden))

    def test_repeated_extractions_and_identical_source_aliases_cannot_meet_minimum(self):
        for duplicate_source in (False, True):
            with self.subTest(duplicate_source=duplicate_source):
                service, handles = self.minimum_service(duplicate_source=duplicate_source)
                rows = []
                for handle in (handles if duplicate_source else [handles[0], handles[0]]):
                    candidate = service.read_page(handle, 1)['figure_candidates'][0]
                    rows.append((handle, service.extract_figure(handle, 1, candidate_id=candidate['candidate_id'])))
                self.assertNotEqual(rows[0][1]['image_id'], rows[1][1]['image_id'])
                with self.assertRaisesRegex(ValueError, '完整原图数量'):
                    service.render_deck(self.original_figure_plan(rows))
                self.assertFalse(service.output.exists())

    def test_two_distinct_candidates_render_validate_and_revisions_preserve_minimum(self):
        for same_page in (False, True):
            with self.subTest(same_page=same_page):
                service, handles = self.minimum_service(same_page=same_page)
                rows = []
                for page in ([1] if same_page else [1, 2]):
                    for candidate in service.read_page(handles[0], page)['figure_candidates']:
                        rows.append((handles[0], service.extract_figure(handles[0], page,
                            candidate_id=candidate['candidate_id'])))
                self.assertEqual(len(rows), 2)
                self.assertNotEqual(rows[0][1]['candidate_id'], rows[1][1]['candidate_id'])
                rendered = service.render_deck(self.original_figure_plan(rows))
                checked = service.validate_deck(rendered['deck_id'])
                self.assertTrue(checked['passed'], checked['errors'])
                before = set(service.output.iterdir())
                with self.assertRaisesRegex(ValueError, '完整原图数量'):
                    service.revise_deck(rendered['deck_id'], [{'page': 2, 'changes': {'image': None, 'layout': 'content'}}])
                self.assertEqual(set(service.output.iterdir()), before)
                self.assertTrue(service.checked_deck(rendered['deck_id']).is_file())

    def test_plan_cannot_lower_a_frozen_minimum(self):
        service, handles = self.minimum_service()
        candidate = service.read_page(handles[0], 1)['figure_candidates'][0]
        image = service.extract_figure(handles[0], 1, candidate_id=candidate['candidate_id'])
        plan = self.original_figure_plan([(handles[0], image)] * 2)
        plan['minimum_original_figures'] = 0
        with self.assertRaisesRegex(ValueError, '计划需要'):
            service.render_deck(plan)
        self.assertFalse(service.output.exists())


if __name__ == '__main__':
    unittest.main()
