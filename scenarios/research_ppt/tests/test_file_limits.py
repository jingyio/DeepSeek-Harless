"""文件上限与分块摘要回归；无模型，不代表大文档科研交付验收。"""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scenarios.research_ppt import documents, knowledge_library


class FileLimitTests(unittest.TestCase):
    def test_exact_limit_hashes_without_read_bytes(self):
        with tempfile.TemporaryDirectory() as area:
            source = Path(area) / 'boundary.pdf'
            with source.open('wb') as stream:
                stream.truncate(documents.MAX_BYTES)
            expected = hashlib.sha256()
            for _ in range(100):
                expected.update(b'\0' * (1024 * 1024))
            # Large files must not be buffered in one read during hashing.
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded read')):
                self.assertEqual(documents.file_hash(source), expected.hexdigest())

    def test_over_limit_rejected_before_opening(self):
        with tempfile.TemporaryDirectory() as area:
            source = Path(area) / 'too-large.pdf'
            with source.open('wb') as stream:
                stream.truncate(documents.MAX_BYTES + 1)
            with patch.object(Path, 'open', side_effect=AssertionError('must not read')):
                with self.assertRaisesRegex(ValueError, '100 MiB'):
                    documents.file_hash(source)

    def test_library_and_parser_share_the_limit(self):
        self.assertEqual(documents.MAX_BYTES, 100 * 1024 * 1024)
        self.assertEqual(knowledge_library.MAX_DOCUMENT_BYTES, documents.MAX_BYTES)

    def test_growth_during_hashing_remains_bounded(self):
        with tempfile.TemporaryDirectory() as area:
            source = Path(area) / 'growing.pdf'
            source.write_bytes(b'abcdef')
            with patch.object(documents, 'MAX_BYTES', 4), patch.object(
                    Path, 'stat', return_value=type('Size', (), {'st_size': 4, 'st_mode': 0o100600})()):
                with self.assertRaisesRegex(ValueError, '100 MiB'):
                    documents.file_hash(source)
