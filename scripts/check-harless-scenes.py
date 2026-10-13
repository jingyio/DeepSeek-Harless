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
def launch(port, principal, real=False):
    run_id = uuid4().hex
    output = ROOT / '.local/web/runs' / run_id
    logs = ROOT / '.local/harless-scenes'; logs.mkdir(parents=True, exist_ok=True)
    with (logs / (run_id + '.log')).open('w') as log:
        child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/harness-web.py'), '--port', str(port),
            '--run-id', run_id, '--user-id', principal, '--budget-usd', '.03', '--run-budget-usd', '.06',
            '--request-limit', '12', '--run-request-limit', '24', *(['--real-model'] if real else [])],
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
    args = parser.parse_args(); os.umask(0o077)
    groups = []
    # Bob stays model-free; separate Connection tokens, DSH_HOME, policy and Session storage.
    with launch(args.port, 'scene-check-alice', args.real_model) as (alice, base, output), \
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
                    result = settings(alice, base, {'action': 'select', 'selection': wanted},
                        expected=400 if mode == 'execute' and rsi else 200)
                    if mode == 'execute' and rsi:
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
        for scene in ('new-scene', 'ppt'):
            settings(alice, base, {'action': 'select', 'selection': {'scene': scene, 'mode': 'shadow', 'rsi': True}})
            text = ('列出上传的文件，读取文件文本，引用真实文件名和 SHA256；不要猜路径。' if scene == 'new-scene'
                    else '调用 list_inputs，pin_source 并 read_source 读取 doc_1，简短概括其文本，引用来源句柄与 SHA256。只读检查，不生成幻灯片。')
            draft = web.api(alice, base, {'action': 'preview', 'request': {'instruction': text,
                **({'scene_options': {'slides': 1, 'allow_output': False}} if scene == 'ppt' else {})}})
            if scene == 'ppt':
                from reportlab.pdfgen.canvas import Canvas
                buffer = io.BytesIO(); pdf = Canvas(buffer); pdf.drawString(80, 700, 'Experiment A used 2 seeds. Independent replication is needed.'); pdf.save()
                name, data = 'source.pdf', buffer.getvalue()
            else: name, data = 'note.txt', b'Experiment A used 2 seeds. Independent replication is needed.'
            draft = web.api(alice, base, {'action': 'upload', 'task_id': draft['task_id'], 'name': name,
                'data': base64.b64encode(data).decode()})
            frozen = json.loads((output / 'tasks' / draft['task_id'] / 'effective-config.json').read_text())
            prefix = 'mcp__ppt__' if scene == 'ppt' else 'mcp__workspace__'
            assert frozen['tools'] and all(tool['name'].startswith(prefix) for tool in frozen['tools'])
            assert frozen['instructions'] and frozen['instructions_sha256']
            assert frozen['user_id'] == 'scene-check-alice' and frozen['selection']['mode'] == 'shadow'
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
                assert result['stats']['tool_errors'] == 0 and result['stats']['verified_skips'] == 0
                assert result['fallback_reason'] == 'no_certified_library'
                groups.append({'group': scene + '-real-harness', 'task_id': draft['task_id'], 'stats': result['stats']})
            else:
                web.api(alice, base, {'action': 'cancel', 'task_id': draft['task_id']})
                groups.append({'group': scene + '-actual-mcp-config-and-upload', 'model_requests': 0})
            drafts.append(draft)
        assert drafts[0]['session_id'] != drafts[1]['session_id']
        web.api(bob, bob_base, {'action': 'cancel', 'task_id': bob_draft['task_id']})
        groups.append({'group': 'two-principal-processes-and-foreign-session-task-receipt-denial', 'model_requests': 0})
        run_id = output.name
    report = {'run_id': run_id, 'code_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'provider_mode': 'real' if args.real_model else 'no_model', 'budget_usd': .06, 'request_limit': 24,
              'max_output_tokens': 1000, 'model': 'deepseek-flash', 'reasoning_effort': 'off',
              'quality_reviewed': False, 'browser_verified': False, 'groups': groups}
    directory = ROOT / '.local/harless-scenes'
    (directory / (run_id + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (directory / 'latest.json').write_text(json.dumps({'run_id': run_id}))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__': main()
