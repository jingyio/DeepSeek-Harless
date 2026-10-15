"""Actual PDF/cache files for B1 correctness diagnostics, with no model calls."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import fitz
from PIL import Image, ImageDraw

from scenarios.research_ppt import document_cache as cache
from scenarios.research_ppt import documents


class DocumentCacheTests(unittest.TestCase):
    def setUp(self):
        area = cache.ROOT / '.local/research-ppt/unit-tests'
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.area = Path(self.temp.name)
        self.path = self.area / 'paper.pdf'
        self.cache_dir = self.area / 'cache'
        self.events = []
        self.create_pdf(self.path, 'Original input')

    def tearDown(self):
        self.temp.cleanup()

    def create_pdf(self, path, text):
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((50, 70), text)
            page.draw_rect(fitz.Rect(100, 150, 300, 300), color=(0, 0, 0))
            page.insert_text((100, 320), 'Figure 1: A vector diagram.')
            page = pdf.new_page(width=600, height=800)
            page.insert_text((50, 70), 'An independent second page.')
            pdf.save(path)

    def parse(self, path=None, **kwargs):
        return cache.cached_parse_document(path or self.path, self.cache_dir,
                                           audit=self.events.append, **kwargs)

    def geometry(self, page=1, path=None):
        source = path or self.path
        return cache.cached_pdf_page_geometry(source, page, documents.file_hash(source), self.cache_dir,
                                              audit=self.events.append)

    def payload_file(self):
        return self.cache_dir / (self.events[-1]['cache_key'] + '.json')

    def corrupt_with_valid_checksum(self, mutate):
        path = self.payload_file()
        envelope = json.loads(path.read_text(encoding='utf-8'))
        mutate(envelope['payload'])
        envelope['payload_sha256'] = hashlib.sha256(cache._canonical(envelope['payload'])).hexdigest()
        path.write_text(json.dumps(envelope), encoding='utf-8')

    def test_cross_path_same_bytes_hit_and_return_independent_payload(self):
        copied = self.area / 'renamed.pdf'
        shutil.copyfile(self.path, copied)
        with patch.object(documents, 'parse_document', wraps=documents.parse_document) as parse:
            first = self.parse()
            second = self.parse(copied)
            self.assertEqual(first, second)
            second['pages'][0]['text'] = 'caller mutation'
            third = self.parse(copied)
            self.assertEqual(first, third)
            self.assertEqual(parse.call_count, 1)
        self.assertEqual([event['status'] for event in self.events], ['miss', 'hit', 'hit'])

    def test_source_change_misses_and_stale_expected_version_fails(self):
        first_sha = documents.file_hash(self.path)
        self.parse(expected_sha256=first_sha)
        replacement = self.area / 'replacement.pdf'
        self.create_pdf(replacement, 'Changed scientific input')
        shutil.copyfile(replacement, self.path)
        second = self.parse()
        self.assertIn('Changed scientific input', second['pages'][0]['text'])
        self.assertEqual([event['status'] for event in self.events], ['miss', 'miss'])
        self.assertNotEqual(self.events[0]['cache_key'], self.events[1]['cache_key'])
        with self.assertRaisesRegex(ValueError, '版本已变化'):
            self.parse(expected_sha256=first_sha)

    def test_parser_schema_and_dependency_changes_have_distinct_keys(self):
        self.parse()
        original_key = self.events[-1]['cache_key']
        dependencies = cache._dependencies('parse', 'pdf')
        for name, value in [('PARSE_VERSION', 'future-parser'), ('PARSE_SCHEMA_VERSION', 2)]:
            with self.subTest(name=name), patch.object(cache, name, value):
                self.parse()
                self.assertEqual(self.events[-1]['status'], 'miss')
                self.assertNotEqual(self.events[-1]['cache_key'], original_key)
        with patch.object(cache, '_dependencies', return_value={**dependencies, 'pypdf': 'future-version'}):
            self.parse()
            self.assertEqual(self.events[-1]['status'], 'miss')
            self.assertNotEqual(self.events[-1]['cache_key'], original_key)
        self.parse()
        self.assertEqual(self.events[-1]['status'], 'hit')
        self.assertEqual(self.events[-1]['cache_key'], original_key)

    def test_invalid_json_is_rejected_then_recomputed_and_logged(self):
        expected = self.parse()
        self.payload_file().write_text('{broken-json', encoding='utf-8')
        self.assertEqual(self.parse(), expected)
        self.assertEqual([event['status'] for event in self.events], ['miss', 'rejected', 'miss'])
        self.parse()
        self.assertEqual(self.events[-1]['status'], 'hit')

    def test_permission_and_source_handle_fields_cannot_enter_cache(self):
        expected = self.parse()
        self.corrupt_with_valid_checksum(lambda value: value.update(
            {'source_id': 'old-authorized-source', 'permissions': {'read': True}}))
        self.assertEqual(self.parse(), expected)
        self.assertEqual(self.events[-2]['status'], 'rejected')
        envelope = json.loads(self.payload_file().read_text(encoding='utf-8'))
        forbidden = {'source_id', 'permissions', 'allow_output', 'document_id', 'read', 'path'}

        def keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(row) for row in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(row) for row in value))
            return set()

        self.assertFalse(forbidden & keys(envelope))


    def test_duplicate_json_keys_do_not_use_last_value(self):
        expected = self.parse()
        path = self.payload_file()
        text = path.read_text(encoding='utf-8')
        path.write_text('{"cache_format_version":1,' + text[1:], encoding='utf-8')
        self.assertEqual(self.parse(), expected)
        self.assertEqual(self.events[-2]['status'], 'rejected')

    def test_source_changed_during_parse_rejects_and_writes_no_cache(self):
        actual_parse = documents.parse_document

        def changing_parse(path):
            result = actual_parse(path)
            with path.open('ab') as stream:
                stream.write(b'\n% changed during parsing\n')
            return result

        with patch.object(documents, 'parse_document', side_effect=changing_parse):
            with self.assertRaisesRegex(ValueError, '版本已变化'):
                self.parse()
        self.assertEqual(list(self.cache_dir.glob('*.json')), [])
        self.assertEqual(self.events[-1]['status'], 'failed')

    def test_geometry_cache_is_bound_to_source_page_and_versions(self):
        copied = self.area / 'copied.pdf'
        shutil.copyfile(self.path, copied)
        with patch.object(documents, 'pdf_page_geometry', wraps=documents.pdf_page_geometry) as geometry:
            first = self.geometry()
            self.assertEqual(first, self.geometry(path=copied))
            self.assertEqual(geometry.call_count, 1)
            second = self.geometry(page=2)
            self.assertEqual(second['figure_candidates'], [])
            self.assertEqual(geometry.call_count, 2)
        with patch.object(cache, 'GEOMETRY_VERSION', 'future-geometry'):
            self.geometry()
        self.assertEqual([event['status'] for event in self.events], ['miss', 'hit', 'miss', 'miss'])

    def test_geometry_scientific_certification_or_invalid_box_is_rejected(self):
        expected = self.geometry()
        self.corrupt_with_valid_checksum(lambda value: value['figure_candidates'][0].update(
            {'semantic_verified': True}))
        self.assertEqual(self.geometry(), expected)
        self.assertEqual(self.events[-2]['status'], 'rejected')
        self.corrupt_with_valid_checksum(lambda value: value['figure_candidates'][0].update(
            {'bbox': [0.1, 0.1, 0.05, 0.9]}))
        self.assertEqual(self.geometry(), expected)
        self.assertEqual(self.events[-2]['status'], 'rejected')

    def test_real_image_payload_is_validated_and_remains_an_embedded_asset(self):
        path = self.area / 'image.pdf'
        image = Image.new('RGB', (300, 200), 'white')
        ImageDraw.Draw(image).rectangle((20, 20, 250, 160), fill='blue')
        raw = io.BytesIO()
        image.save(raw, format='PNG')
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((50, 70), 'Text with an embedded asset.')
            page.insert_image(fitz.Rect(100, 150, 300, 300), stream=raw.getvalue())
            pdf.save(path)
        first = self.parse(path)
        self.assertEqual(len(first['images']), 1)
        self.assertEqual(first['images'][0]['evidence_scope'], 'embedded_asset_not_complete_figure')
        self.assertEqual(first, self.parse(path))
        self.assertEqual(self.events[-1]['status'], 'hit')
        self.corrupt_with_valid_checksum(lambda value: value['images'][0].update({'data': 'image/png;base64,bad'}))
        self.assertEqual(first, self.parse(path))
        self.assertEqual(self.events[-2]['status'], 'rejected')

    def test_cache_outside_private_directory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '私有 .local'):
            cache.cached_parse_document(self.path, cache.ROOT / 'unapproved-cache')
        self.assertFalse((cache.ROOT / 'unapproved-cache').exists())


if __name__ == '__main__':
    unittest.main()
