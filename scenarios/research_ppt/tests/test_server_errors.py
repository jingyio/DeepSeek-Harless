"""真实 stdio MCP 的可恢复业务错误；不调用模型，未知异常内容不外泄。"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import Client, StdioServerParameters

from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.server import _safe_failure, _tool_errors
from scenarios.research_ppt.service import ROOT, RenderFailure
from scenarios.research_ppt.tests.test_service import write_pdf


class SafeErrorTests(unittest.TestCase):
    def test_revision_fields_are_recoverable_but_arbitrary_text_is_private(self):
        for message in ('修订页码重复', 'changes 必须包含合法的幻灯片字段，不能有未知字段',
                        '修订字段 notes 的类型或结构无效'):
            self.assertEqual(_safe_failure(ValueError(message))['error'], 'invalid_plan')
        for message in ('修订字段 /private/key.env 的类型或结构无效',
                        '修订字段 notes 的类型或结构无效 credential=private-value'):
            response = _safe_failure(ValueError(message))
            self.assertEqual(response['error'], 'internal_processing_failed')
            self.assertNotIn('private-value', json.dumps(response))

    def test_structured_layout_errors_preserve_only_safe_recovery_fields(self):
        for code in ('text_overflow', 'table_overflow', 'chart_label_overflow',
                     'out_of_bounds', 'content_overlap'):
            with self.subTest(code=code):
                report = {'ok': False, 'code': code, 'page': 5,
                          'role': 'process_3_detail',
                          'error': '/private/path/render.js credential=private-value',
                          'stack': '/private/key.env', 'plan': 'private-input'}
                response = _safe_failure(RenderFailure(report))
                self.assertEqual(response['error'], code)
                self.assertEqual(response['page'], 5)
                self.assertEqual(response['role'], 'process_3_detail')
                self.assertTrue(response['next_action'])
                self.assertEqual(set(response), {'error', 'message', 'next_action', 'page', 'role'})
                encoded = json.dumps(response)
                for secret in ('/private', 'credential', 'private-value', 'private-input'):
                    self.assertNotIn(secret, encoded)

    def test_structured_layout_errors_reject_unsafe_metadata(self):
        for page, role in ((True, '/private/render.js'), (0, 'body credential=private-value'),
                           (31, 'private-value'), ('1', 'x' * 65)):
            with self.subTest(page=page, role=role):
                response = _safe_failure(RenderFailure({'ok': False, 'code': 'text_overflow',
                    'page': page, 'role': role, 'error': '/private/key.env'}))
                self.assertEqual(response['error'], 'text_overflow')
                self.assertNotIn('page', response)
                self.assertNotIn('role', response)
                self.assertNotIn('/private', json.dumps(response))
                self.assertNotIn('private-value', json.dumps(response))

    def test_unknown_structured_layout_error_remains_private(self):
        response = _safe_failure(RenderFailure({'ok': False, 'code': 'private_error',
            'page': 1, 'role': 'process_1_detail',
            'error': '/private/key.env credential=private-value'}))
        self.assertEqual(response['error'], 'internal_processing_failed')
        self.assertEqual(set(response), {'error', 'message', 'next_action'})
        self.assertNotIn('/private', json.dumps(response))
        self.assertNotIn('private-value', json.dumps(response))

    def test_changed_preview_artifacts_has_safe_recovery(self):
        response = _safe_failure(ValueError('核验预览产物已缺失或变化，旧核验失效'))
        self.assertEqual(response['error'], 'preview_artifact_version_changed')
        self.assertIn('PDF/PNG', response['next_action'])
        self.assertIn('旧 validation_id', response['next_action'])

    def test_node_message_excludes_paths_and_stderr_details(self):
        error = ValueError('场景 Node 工具执行失败: /private/path/render.js\n'
                           'Error: 第 1 页：封面/章节页最多 4 条短句\n'
                           '    at render (/private/path/render.js:123)\n'
                           'credential=private-value')
        response = _safe_failure(error)
        self.assertEqual(response['error'], 'invalid_plan')
        self.assertIn('第 1 页', response['message'])
        self.assertNotIn('/private', json.dumps(response))
        self.assertNotIn('private-value', json.dumps(response))

    def test_unknown_value_error_is_redacted_even_when_logging_fails(self):
        class BrokenLog:
            def record(self, *_):
                raise OSError('private-log-location')

        def failing(plan: dict) -> dict:
            raise ValueError('/private/key.env credential=private-value')

        result = _tool_errors(failing, BrokenLog())({})
        self.assertTrue(result.model_dump(by_alias=True)['isError'])
        self.assertEqual(json.loads(result.content[0].text)['error'], 'internal_processing_failed')
        self.assertNotIn('private-value', result.content[0].text)
        self.assertNotIn('private-log-location', result.content[0].text)

    def test_known_message_with_appended_sensitive_data_is_not_public(self):
        response = _safe_failure(ValueError('图片标识不存在 credential=private-value'))
        self.assertEqual(response['error'], 'internal_processing_failed')
        self.assertNotIn('private-value', json.dumps(response))


class ServerErrorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        area = ROOT / '.local/research-ppt/server-error-tests'
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        source = Path(self.temp.name) / 'input.pdf'
        write_pdf(source)
        self.job = prepare([source], '真实 MCP 错误与恢复验收', 15, True)
        self.params = StdioServerParameters(command=sys.executable,
            args=[str(ROOT / 'scenarios/research_ppt/server.py')], cwd=ROOT,
            env=dict(os.environ, SSS_PPT_JOB=str(self.job), PYTHONPATH=str(ROOT)))

    async def read_source_and_plan(self, client):
        self.client = client
        pinned = await self.client.call_tool('pin_source', {'document_id': 'doc_1'})
        self.assertFalse(pinned.is_error)
        self.handle = json.loads(pinned.content[0].text)['source_id']
        read = await self.client.call_tool('read_source', {'source_id': self.handle})
        self.assertFalse(read.is_error)
        cite = {'source_id': self.handle, 'page': 1}
        self.plan = {'title': '业务校验与恢复', 'slides': [
            {'title': f'证据与验证 {i+1}', 'bullets': ['来自真实文件的科研证据。'],
             'sources': [copy.deepcopy(cite)]} for i in range(15)]}

    def tearDown(self):
        self.temp.cleanup()

    def error(self, result, code, expected):
        self.assertTrue(result.model_dump(by_alias=True)['isError'])
        content = json.loads(result.content[0].text)
        self.assertEqual(content['error'], code)
        self.assertIn(expected, content['message'])
        self.assertTrue(content['next_action'])
        return content

    async def test_business_errors_are_actionable_and_same_session_recovers(self):
        # anyio 的 cancel scope 必须在同一 test task 内进入和退出。
        async with Client(self.params, read_timeout_seconds=120) as client:
            await self.read_source_and_plan(client)
            await self.check_business_errors_and_recovery()

    async def check_business_errors_and_recovery(self):
        wrong_count = {**self.plan, 'slides': self.plan['slides'][:1]}
        result = await self.client.call_tool('render_deck', {'plan': wrong_count})
        self.error(result, 'invalid_plan', '15 页')

        missing_sources = copy.deepcopy(self.plan)
        missing_sources['slides'][0]['sources'] = []
        result = await self.client.call_tool('render_deck', {'plan': missing_sources})
        self.error(result, 'invalid_plan', '每页必须声明 sources')

        unknown_image = copy.deepcopy(self.plan)
        unknown_image['slides'][1]['image'] = {'source_id': self.handle, 'image_id': 'invented-image'}
        result = await self.client.call_tool('render_deck', {'plan': unknown_image})
        content = self.error(result, 'invalid_image', '图片标识不存在')
        self.assertIn('extract_figure', content['next_action'])

        bad_cover = copy.deepcopy(self.plan)
        bad_cover['slides'][0]['layout'] = 'title'
        bad_cover['slides'][0]['bullets'] = ['短句一', '短句二', '短句三', '短句四', '短句五']
        result = await self.client.call_tool('render_deck', {'plan': bad_cover})
        self.error(result, 'invalid_plan', '封面/章节页最多')

        repaired = copy.deepcopy(bad_cover)
        repaired['slides'][0]['bullets'] = ['短句一', '短句二', '短句三', '短句四']
        result = await self.client.call_tool('render_deck', {'plan': repaired})
        self.assertFalse(result.is_error)
        generated = json.loads(result.content[0].text)
        self.assertEqual(generated['slide_count'], 15)
        self.assertTrue(Path(generated['path']).is_file())
        inspection = await self.client.call_tool('inspect_deck', {'deck_id': generated['deck_id']})
        self.assertFalse(inspection.is_error)
        self.assertEqual(json.loads(inspection.content[0].text)['slide_count'], 15)
        records = [json.loads(line) for line in (self.job.parent / 'feedback.jsonl').read_text(encoding='utf-8').splitlines()]
        rejections = [row for row in records if row['kind'] == 'tool_rejected']
        self.assertEqual(len(rejections), 4)
        self.assertTrue(all(row['tool'] == 'render_deck' for row in rejections))
        self.assertTrue(all('/private/' not in row['reason'] for row in rejections))

    async def test_permissions_remain_denied_on_real_stdio_mcp(self):
        async with Client(self.params, read_timeout_seconds=120) as client:
            await self.read_source_and_plan(client)
        prepared = json.loads(self.job.read_text(encoding='utf-8'))
        job = prepare([Path(prepared['inputs'][0]['path'])], '仅预览', 15, False)
        params = StdioServerParameters(command=sys.executable,
            args=self.params.args, cwd=ROOT,
            env=dict(os.environ, SSS_PPT_JOB=str(job), PYTHONPATH=str(ROOT)))
        async with Client(params, read_timeout_seconds=120) as client:
            result = await client.call_tool('render_deck', {'plan': self.plan})
            self.error(result, 'output_permission_denied', '未授权生成文件')
        self.assertFalse((job.parent / 'outputs').exists())


if __name__ == '__main__':
    unittest.main()
