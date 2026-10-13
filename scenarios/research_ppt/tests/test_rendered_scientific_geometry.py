"""实际PDF字形边界反例：文字完整保留仍可能侵入科研出处。"""
import json
from pathlib import Path
import unittest
from uuid import uuid4
import fitz
from scenarios.research_ppt.service import ROOT
from scenarios.research_ppt.validation import _check_scientific_footer


class ScientificFooterGeometryTests(unittest.TestCase):
    def test_actual_painted_text_rejects_overlap_but_accepts_spaced_body(self):
        directory = ROOT / '.local/research-ppt/scientific-geometry-tests' / uuid4().hex
        directory.mkdir(parents=True)
        citation = '[1] Public source.pdf p.2'
        for name, baseline, should_fail in [('spaced', 420, False), ('overlap', 500, True)]:
            pdf = directory / (name + '.pdf')
            with fitz.open() as document:
                page = document.new_page(width=960, height=540)
                page.insert_text((60, baseline), 'All body text remains present.', fontsize=20)
                page.insert_text((60, 500), citation, fontsize=10)
                document.save(pdf)
            with fitz.open(pdf) as document:
                report = {'errors': [], 'warnings': []}
                checked = _check_scientific_footer(document[0], [citation], report, 1)
                self.assertTrue(checked['checked'])
                self.assertEqual(bool(report['errors']), should_fail)
                self.assertEqual(checked['intruding_body_characters'] > 0, should_fail)
                (directory / (name + '.json')).write_text(json.dumps(report), encoding='utf-8')

    def test_missing_painted_source_rejects_and_legacy_page_is_unaffected(self):
        with fitz.open() as document:
            page = document.new_page(width=960, height=540)
            page.insert_text((60, 500), 'A body only', fontsize=20)
            report = {'errors': [], 'warnings': []}
            self.assertFalse(_check_scientific_footer(page, [], report, 1)['checked'])
            self.assertEqual(report['errors'], [])
            self.assertFalse(_check_scientific_footer(page, ['[1] Missing source'], report, 1)['checked'])
            self.assertEqual(report['errors'][0]['code'], 'render_visible_source_unlocated')
