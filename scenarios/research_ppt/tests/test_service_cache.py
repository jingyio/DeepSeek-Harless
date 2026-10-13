"""Real service and renderer checks: a warm B1 cache never restores job authority."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from uuid import uuid4

from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash, parse_document
from scenarios.research_ppt.service import ROOT, PPTService
from scenarios.research_ppt.tests.test_service import write_pdf


class ServiceCacheTests(unittest.TestCase):
    def setUp(self):
        area = ROOT / '.local/research-ppt/unit-tests'
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.area = Path(self.temp.name)
        self.path = self.area / 'first-paper.pdf'
        write_pdf(self.path, 'Independent cache authority test ' + uuid4().hex)

    def tearDown(self):
        self.temp.cleanup()

    def service(self, path=None, allow_output=True):
        job = prepare([path or self.path], '检查缓存不继承任务授权', 1, allow_output,
                      document_cache=True)
        return PPTService(job)

    def cache_events(self, service):
        path = service.job_path.parent / 'feedback.jsonl'
        return [row for row in (json.loads(line) for line in path.read_text(encoding='utf-8').splitlines())
                if row['kind'] == 'document_cache']

    def plan(self, handle):
        return {'title': '缓存权限回归', 'slides': [
            {'title': '独立授权', 'bullets': ['缓存只复用数据，来源仍需本任务读取。'],
             'sources': [{'source_id': handle, 'page': 1}]}]}

    def warm(self):
        service = self.service()
        pinned = service.pin_source('doc_1')
        service.read_source(pinned['source_id'])
        self.assertEqual(self.cache_events(service)[-1]['status'], 'miss')
        return service, pinned

    def test_new_warm_job_requires_pin_and_read_before_real_render(self):
        first, pinned = self.warm()
        second = self.service()
        self.assertTrue(first.handles[pinned['source_id']]['read'])
        with self.assertRaisesRegex(ValueError, '未知 source_id'):
            second.read_source(pinned['source_id'])
        repinned = second.pin_source('doc_1')
        self.assertEqual(self.cache_events(second)[-1]['status'], 'hit')
        self.assertFalse(second.handles[repinned['source_id']]['read'])
        self.assertEqual(second.handles[repinned['source_id']]['parsed'], parse_document(self.path))
        with self.assertRaisesRegex(ValueError, '来源尚未读取'):
            second.render_deck(self.plan(repinned['source_id']))
        self.assertFalse(second.output.exists())
        second.read_source(repinned['source_id'])
        rendered = second.render_deck(self.plan(repinned['source_id']))
        self.assertEqual(rendered['slide_count'], 1)
        self.assertTrue(rendered['each_slide_has_editable_text'])
        parsed = parse_document(Path(rendered['path']))
        self.assertIn('独立授权', parsed['pages'][0]['text'])

    def test_same_bytes_different_path_share_data_but_preview_job_stays_read_only(self):
        first, pinned = self.warm()
        copied = self.area / 'second-paper.pdf'
        shutil.copyfile(self.path, copied)
        second = self.service(copied, allow_output=False)
        repinned = second.pin_source('doc_1')
        self.assertEqual(self.cache_events(second)[-1]['status'], 'hit')
        self.assertEqual(pinned['version_sha256'], repinned['version_sha256'])
        self.assertNotEqual(first.job['inputs'][0]['path'], second.job['inputs'][0]['path'])
        self.assertFalse(second.handles[repinned['source_id']]['read'])
        second.read_source(repinned['source_id'])
        self.assertFalse(second.job['allow_output'])
        with self.assertRaisesRegex(ValueError, '预览模式'):
            second.render_deck(self.plan(repinned['source_id']))
        self.assertFalse(second.output.exists())
        self.assertTrue(second.handles[repinned['source_id']]['read'])

    def test_source_version_change_rejects_warm_read_and_cached_pinning(self):
        first, _ = self.warm()
        second = self.service()
        pinned = second.pin_source('doc_1')
        self.assertEqual(self.cache_events(second)[-1]['status'], 'hit')
        before = file_hash(self.path)
        with self.path.open('ab') as stream:
            stream.write(b'\n% new source version\n')
        self.assertNotEqual(file_hash(self.path), before)
        with self.assertRaisesRegex(ValueError, '版本已变化'):
            second.read_source(pinned['source_id'])
        with self.assertRaisesRegex(ValueError, '版本已变化'):
            second.pin_source('doc_1')
        with self.assertRaisesRegex(ValueError, '版本已变化'):
            first.pin_source('doc_1')
        self.assertFalse(second.handles[pinned['source_id']]['read'])

    def test_service_restart_does_not_restore_read_or_deck_authority(self):
        original, pinned = self.warm()
        rendered = original.render_deck(self.plan(pinned['source_id']))
        restarted = PPTService(original.job_path)
        self.assertEqual(restarted.handles, {})
        self.assertEqual(restarted.decks, {})
        with self.assertRaisesRegex(ValueError, '未知 source_id'):
            restarted.read_page(pinned['source_id'], 1)
        with self.assertRaisesRegex(ValueError, '未知 deck_id'):
            restarted.inspect_deck(rendered['deck_id'])
        current = restarted.pin_source('doc_1')
        self.assertEqual(self.cache_events(restarted)[-1]['status'], 'hit')
        self.assertFalse(restarted.handles[current['source_id']]['read'])
        with self.assertRaisesRegex(ValueError, '来源尚未读取'):
            restarted.render_deck(self.plan(current['source_id']))


if __name__ == '__main__':
    unittest.main()
