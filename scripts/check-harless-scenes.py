#!/usr/bin/env python3
"""实际 Harness 场景/MCP 配置验收；模型执行仅限显式 --real-model。"""
from __future__ import annotations
import argparse
import base64
from contextlib import contextmanager
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('checks', ROOT / 'scripts/check-web-tasks.py')
web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)


@contextmanager
def launch(port, principal, real=False, run_budget=.06, run_limit=24):
    run_id = uuid4().hex
    output = ROOT / '.local/web/runs' / run_id
    logs = ROOT / '.local/harless-scenes'; logs.mkdir(parents=True, exist_ok=True)
    with (logs / (run_id + '.log')).open('w') as log:
        child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/harness-web.py'), '--port', str(port),
            '--run-id', run_id, '--user-id', principal, '--budget-usd', str(min(.03, run_budget)), '--run-budget-usd', str(run_budget),
            '--request-limit', str(min(12, run_limit)), '--run-request-limit', str(run_limit), *(['--real-model'] if real else [])],
            stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        try:
            for _ in range(400):
                if (output / 'access-url.txt').exists(): break
                if child.poll() is not None: raise RuntimeError('启动失败；查看私有 harless-scenes 日志')
                time.sleep(.1)
            else: raise RuntimeError('启动超时')
            opener = web.client(); base = f'http://127.0.0.1:{port}'
            opener.open((output / 'access-url.txt').read_text().strip()).close()
            yield opener, base, output
        finally:
            if child.poll() is None: child.send_signal(signal.SIGTERM)
            try: child.wait(timeout=15)
            except subprocess.TimeoutExpired: child.kill(); child.wait()


def settings(opener, base, body=None, session=None, expected=200):
    status, value = web.request(opener, base, '/api/harless/settings' + ('?session_id=' + session if session else ''), body)
    assert status == expected, (status, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-model', action='store_true')
    parser.add_argument('--port', type=int, default=3096)
    parser.add_argument('--run-budget-usd', type=float, default=.06)
    parser.add_argument('--run-request-limit', type=int, default=24)
    parser.add_argument('--scenes', nargs='+', choices=['new-scene','ppt','paper-proofreading','research-data-analysis'],
                        default=['new-scene','ppt','paper-proofreading','research-data-analysis'])
    parser.add_argument('--mode', choices=['baseline','shadow','execute'], default='shadow')
    args = parser.parse_args(); os.umask(0o077)
    groups = []
    # Bob stays model-free; separate Connection tokens, DSH_HOME, policy and Session storage.
    with launch(args.port, 'scene-check-alice', args.real_model, args.run_budget_usd, args.run_request_limit) as (alice, base, output), \
         launch(args.port + 1, 'scene-check-bob') as (bob, bob_base, bob_output):
        value = settings(alice, base)
        assert [scene['id'] for scene in value['scenes']] == ['ppt', 'paper-proofreading', 'research-data-analysis', 'new-scene']
        assert value['selection']['scene'] == 'new-scene'
        ppt = next(scene for scene in value['scenes'] if scene['id'] == 'ppt')
        assert ppt['available'], ppt
        for scene in value['scenes']:
            for mode in ('baseline', 'shadow', 'execute'):
                for rsi in (False, True):
                    wanted = {'scene': scene['id'], 'mode': mode, 'rsi': rsi}
                    rejected = mode == 'execute' and rsi and not scene['execute_available']
                    result = settings(alice, base, {'action': 'select', 'selection': wanted},
                        expected=400 if rejected else 200)
                    if rejected:
                        assert result['error']['code'] == 'execute_unavailable'; continue
                    assert result['selection'] == wanted
                    if not scene['available']:
                        status, denied = web.request(alice, base, '/api/harless/tasks', {'action': 'preview', 'request': '不得用样例代替'})
                        assert status == 409 and denied['error']['code'] == 'scene_not_connected'
        assert web.api(alice, base)['aggregate'].get('upstream_requests', 0) == 0
        groups.append({'group': '24-menu-combinations-and-missing-backend-rejection', 'model_requests': 0})

        settings(bob, bob_base, {'action': 'select', 'selection': {'scene': 'ppt', 'mode': 'baseline'}})
        bob_draft = web.api(bob, bob_base, {'action': 'preview', 'request': 'Bob private draft'})
        drafts = []
        for scene in args.scenes:
            settings(alice, base, {'action': 'select', 'selection': {'scene': scene, 'mode': args.mode, 'rsi': True}})
            text = {'new-scene':'列出上传的文件，读取文件文本，引用真实文件名和 SHA256；不要猜路径。',
                    'ppt':'调用 list_inputs，pin_source 并 read_source 读取 doc_1，简短概括其文本，引用来源句柄与 SHA256。只读检查，不生成幻灯片。',
                    'paper-proofreading':'调用 list_inputs，按实际文件名和 SHA256 使用 pin_document、read_pinned_document 阅读论文文本，给出一句措辞修改建议并引用来源版本。',
                    'research-data-analysis':'调用 list_inputs，按实际文件名和 SHA256 使用 pin_dataset、read_pinned_dataset_summary 计算 x 的均值和缺失数，简短回答并引用来源版本。'}[scene]
            if scene=='ppt' and args.mode=='execute':
                text='当前已上传 doc_1。请直接调用 pin_source(document_id="doc_1") 固定它，再读取其内容，用一句话概括并引用真实来源句柄和版本。只读检查，不生成幻灯片。'
            draft = web.api(alice, base, {'action': 'preview', 'request': {'instruction': text,
                **({'scene_options': {'slides': 1, 'allow_output': False}} if scene == 'ppt' else {})}})
            if scene == 'ppt':
                from reportlab.pdfgen.canvas import Canvas
                buffer = io.BytesIO(); pdf = Canvas(buffer); pdf.drawString(80, 700, 'Experiment A used 2 seeds. Independent replication is needed.'); pdf.save()
                name, data = 'source.pdf', buffer.getvalue()
            elif scene == 'paper-proofreading': name, data = 'paper.md', b'We proves the result using two independent seeds. Further replication is needed.'
            elif scene == 'research-data-analysis': name, data = 'data.csv', b'x,y\n1,2\n2,4\n,6\n3,8\n'
            else: name, data = 'note.txt', b'Experiment A used 2 seeds. Independent replication is needed.'
            draft = web.api(alice, base, {'action': 'upload', 'task_id': draft['task_id'], 'name': name,
                'data': base64.b64encode(data).decode()})
            frozen = json.loads((output / 'tasks' / draft['task_id'] / 'effective-config.json').read_text())
            prefix = {'ppt':'mcp__ppt__','new-scene':'mcp__workspace__','paper-proofreading':'mcp__paper_checks__','research-data-analysis':'mcp__data_analysis__'}[scene]
            assert frozen['tools'] and all(tool['name'].startswith(prefix) for tool in frozen['tools'])
            assert frozen['instructions'] and frozen['instructions_sha256']
            assert frozen['user_id'] == 'scene-check-alice' and frozen['selection']['mode'] == args.mode
            assert frozen['workspace'].startswith(str(output)) and draft['scene_inputs']
            other = 'ppt' if scene == 'new-scene' else 'new-scene'
            next_choice = settings(alice, base, {'action': 'select', 'session_id': draft['session_id'],
                'selection': {'scene': other, 'mode': 'execute', 'rsi': False}})
            assert next_choice['current_task']['scene'] == scene
            assert web.api(alice, base, task_id=draft['task_id'])['confirmation_digest'] == draft['confirmation_digest']
            assert settings(bob, bob_base, session=draft['session_id'], expected=404)['error']['code'] == 'session_not_owned'
            status, value = web.request(alice, base, '/api/harless/tasks?task_id=' + bob_draft['task_id'])
            assert status == 404
            # Foreign receipt is rejected by official Agent scope, before register/LLM.
            request = json.loads((output / 'tasks' / draft['task_id'] / 'task.json').read_text())
            receipt = next(part for part in request['content'] if part['type'] == 'file')
            empty = settings(alice, base, {'action': 'new_session'})
            status, value = web.request(alice, base, '/api/harless/tasks', {'action': 'preview', 'session_id': empty['session_id'],
                'request': {'content': [receipt]}})
            assert status == 400
            if args.real_model:
                web.submit(alice, base, draft); result = web.wait_task(alice, base, draft['task_id'], seconds=180)
                assert result['status'] == 'completed' and result['stats']['tool_calls'] > 0
                assert result['stats']['tool_errors'] == 0
                if args.mode=='execute':
                    assert result['stats']['verified_skips']>0 and result['fallback_reason'] is None
                else:
                    assert result['stats']['verified_skips']==0
                    if not frozen.get('binding_policy'):
                        assert result['fallback_reason'] in ('no_certified_library','runtime_bundle_not_deployed')
                groups.append({'group': scene + '-real-harness', 'task_id': draft['task_id'], 'stats': result['stats']})
            else:
                web.api(alice, base, {'action': 'cancel', 'task_id': draft['task_id']})
                groups.append({'group': scene + '-actual-mcp-config-and-upload', 'model_requests': 0})
            drafts.append(draft)
        assert len({draft['session_id'] for draft in drafts}) == len(drafts)
        web.api(bob, bob_base, {'action': 'cancel', 'task_id': bob_draft['task_id']})
        groups.append({'group': 'two-principal-processes-and-foreign-session-task-receipt-denial', 'model_requests': 0})
        run_id = output.name
    report = {'run_id': run_id, 'code_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'provider_mode': 'real' if args.real_model else 'no_model', 'budget_usd': args.run_budget_usd, 'request_limit': args.run_request_limit,
              'max_output_tokens': 1000, 'model': 'deepseek-flash', 'reasoning_effort': 'off',
              'quality_reviewed': False, 'browser_verified': False, 'groups': groups}
    directory = ROOT / '.local/harless-scenes'
    (directory / (run_id + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (directory / 'latest.json').write_text(json.dumps({'run_id': run_id}))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__': main()
