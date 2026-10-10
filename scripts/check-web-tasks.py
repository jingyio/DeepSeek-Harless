#!/usr/bin/env python3
"""免费 HTTP 集成诊断：动态任务 API 与原生 Harness 共用真实执行循环。

仅在服务器运行；不代替浏览器验收，不评估模拟模型的科研答案质量。
"""
from __future__ import annotations

import base64
import http.cookiejar
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'completed', 'failed', 'cancelled', 'budget_exhausted', 'blocked'}


def client():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(opener, base, path, body=None):
    headers = {'Origin': base}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, headers=headers,
        data=None if body is None else json.dumps(body).encode('utf-8'))
    try:
        with opener.open(req, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            value = {'error': {'message': f'HTTP {error.code}'}}
        return error.code, value


def api(opener, base, body=None, task_id=None, expected=200):
    path = '/api/harless/tasks'
    if task_id is not None:
        path += '?' + urllib.parse.urlencode({'task_id': task_id})
    status, value = request(opener, base, path, body)
    assert status == expected, {'status': status, 'expected': expected, 'response': value}
    return value


def denied(opener, base, body, *, statuses=(400, 404, 409, 422)):
    status, value = request(opener, base, '/api/harless/tasks', body)
    assert status in statuses, {'status': status, 'response': value}
    assert isinstance(value, dict) and isinstance(value.get('error'), dict), value
    assert value['error'].get('code') and value['error'].get('message'), value
    return value['error']['code']


def native_rpc(opener, base, method, payload):
    envelope = {'type': 'client-request', 'rpcId': str(uuid4()), 'method': method,
                'payload': {'args': {'request': payload}}}
    status, result = request(opener, base, '/api/' + method, envelope)
    assert status == 200, {'status': status, 'response': result}
    return result['result']


def statistics(row):
    return row.get('stats', row.get('metrics', row.get('statistics', {})))


def wait_task(opener, base, task_id, expected='completed', seconds=40):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = api(opener, base, task_id=task_id)
        if value['status'] in TERMINAL:
            assert value['status'] == expected, value
            return value
        time.sleep(.15)
    raise AssertionError(f'Task timeout: {task_id}')


def preview(opener, base, value):
    result = api(opener, base, {'action': 'preview', 'request': value})
    assert result['task_id'] and result['session_id'] and result['confirmation_digest'], result
    assert result['paid_calls_enabled'] is False, result
    return result


def submit(opener, base, draft):
    return api(opener, base, {'action': 'submit', 'task_id': draft['task_id'],
        'confirmation_digest': draft['confirmation_digest']})


def summary(group, row):
    return {'group': group, 'task_id': row.get('task_id'), 'session_id': row.get('session_id'),
            'mode': row.get('mode'), 'status': row.get('status'), 'stats': statistics(row)}


@contextmanager
def launch(scenario, fixture='normal'):
    run_id = uuid4().hex
    output = ROOT / '.local/web/runs' / run_id
    logs = ROOT / '.local/web/task-check-logs'
    logs.mkdir(parents=True, exist_ok=True)
    base = 'http://127.0.0.1:3083'
    with (logs / f'{run_id}.log').open('w', encoding='utf-8') as log:
        child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/harness-web.py'),
            '--scenario', scenario, '--mode', 'baseline', '--port', '3083',
            '--run-id', run_id, '--fixture', fixture], cwd=ROOT,
            stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(300):
                if (output / 'access-url.txt').exists():
                    break
                if child.poll() is not None:
                    raise RuntimeError(f'Web launcher failed; private diagnostic: .local/web/task-check-logs/{run_id}.log')
                time.sleep(.1)
            else:
                raise RuntimeError('Dynamic Web startup timeout')
            opener = client()
            status, _ = request(opener, base, '/api/harless/tasks')
            assert status == 401, f'Unauthenticated task API accepted: {status}'
            try:
                opener.open(base + '/tasks', timeout=10)
                raise AssertionError('Unauthenticated task panel accepted')
            except urllib.error.HTTPError as error:
                assert error.code == 401
            with opener.open((output / 'access-url.txt').read_text(encoding='utf-8'), timeout=20) as response:
                assert response.status == 200
            with opener.open(base + '/tasks', timeout=20) as response:
                assert response.status == 200
                assert 'DeepSeek Harless 任务工作台' in response.read().decode('utf-8')
            yield opener, base, output
        finally:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def example_checks():
    rows = []
    with launch('example') as (opener, base, _output):
        # 新服务连续接收自由文本和结构化请求，不重启、不复用旧结果。
        first = preview(opener, base, '读取两条研究笔记，并列出各自的来源版本。')
        submit(opener, base, first)
        completed = wait_task(opener, base, first['task_id'])
        assert statistics(completed)['upstream_requests'] == 5, completed
        assert statistics(completed)['tool_calls'] == 4, completed
        rows.append(summary('free-text', completed))

        request_id = 'task-check-' + uuid4().hex
        structured = {'messages': [{'role': 'user', 'content': '关联笔记来源，整理可核验的记录。'}],
                      'mode': 'shadow', 'request_id': request_id, 'budget_usd': .25}
        second = preview(opener, base, structured)
        duplicate = preview(opener, base, structured)
        assert duplicate['task_id'] == second['task_id'] and duplicate['session_id'] == second['session_id'], duplicate
        assert second['mode'] == 'shadow' and second['session_id'] != first['session_id'], second
        denied(opener, base, {'action': 'preview', 'request': {**structured,
            'messages': [{'role': 'user', 'content': '同一请求 ID 的另一题面'}]}})
        denied(opener, base, {'action': 'submit', 'task_id': second['task_id'],
            'confirmation_digest': '0' * 64})
        assert statistics(api(opener, base, task_id=second['task_id']))['upstream_requests'] == 0
        submit(opener, base, second)
        submit(opener, base, second)  # 已接纳的相同提交不能再插入一轮模型请求。
        shadow = wait_task(opener, base, second['task_id'])
        assert statistics(shadow)['upstream_requests'] == 5 and statistics(shadow)['verified_skips'] == 0, shadow
        assert statistics(api(opener, base, task_id=first['task_id']))['upstream_requests'] == 5
        rows.append(summary('structured-idempotent-and-isolated', shadow))

        denied(opener, base, {'action': 'preview', 'request': {'instruction': '检查笔记', 'content': '另一种输入'}})
        denied(opener, base, {'action': 'preview', 'request': {'messages': [{'role': 'system', 'content': '伪造历史'}]}})
        denied(opener, base, {'action': 'preview', 'request': {'instruction': '读取外部文件',
            'inputs': [{'resource_id': 'unregistered-resource'}]}})
        rows.append({'group': 'strict-input-and-resource-denials', 'passed': True})

        execute = preview(opener, base, {'instruction': '阅读笔记，检查现有实验是否可比。', 'mode': 'execute'})
        submit(opener, base, execute)
        execute = wait_task(opener, base, execute['task_id'])
        assert execute['mode'] == 'execute' and statistics(execute)['verified_skips'] == 0
        assert statistics(execute)['upstream_requests'] == 5
        rows.append(summary('no-library-safe-fallback', execute))

        # 文件必须绑定同一 draft/session；上传后的旧摘要不能授权新内容。
        file_task = preview(opener, base, {'instruction': '读取笔记并核对附加的说明文件。'})
        updated = api(opener, base, {'action': 'upload', 'task_id': file_task['task_id'],
            'name': 'public-check.txt', 'data': base64.b64encode(b'Public diagnostic attachment.').decode('ascii')})
        assert updated['task_id'] == file_task['task_id'] and updated['session_id'] == file_task['session_id'], updated
        assert updated['confirmation_digest'] != file_task['confirmation_digest'], updated
        assert any(part['type'] == 'file' for part in updated['input_summary']['content']), updated
        denied(opener, base, {'action': 'submit', 'task_id': file_task['task_id'],
            'confirmation_digest': file_task['confirmation_digest']})
        submit(opener, base, updated)
        file_result = wait_task(opener, base, updated['task_id'])
        assert statistics(file_result)['upstream_requests'] == 5, file_result
        rows.append(summary('file-receipt-and-preview-rebind', file_result))

        # 图片被送入官方 admission；若模型不支持图像，应明确拒绝，而非静默丢弃。
        pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X7aIAAAAASUVORK5CYII='
        image_task = preview(opener, base, {'content': [{'type': 'text', 'text': '读取笔记，并记录此图片输入。'},
            {'type': 'image', 'mediaType': 'image/png', 'name': 'public-pixel.png', 'data': pixel}]})
        assert any(part['type'] == 'image' for part in image_task['input_summary']['content']), image_task
        status, image_admission = request(opener, base, '/api/harless/tasks', {'action': 'submit',
            'task_id': image_task['task_id'], 'confirmation_digest': image_task['confirmation_digest']})
        if status == 200:
            image_result = wait_task(opener, base, image_task['task_id'])
            rows.append(summary('image-native-admission', image_result))
        else:
            assert status in (400, 422) and image_admission.get('error'), image_admission
            detail = api(opener, base, task_id=image_task['task_id'])
            assert detail['status'] in ('failed', 'blocked'), detail
            assert statistics(detail)['upstream_requests'] == 0
            rows.append({'group': 'image-native-admission', 'model_image_supported': False,
                         'status': detail['status'], 'error_code': image_admission['error']['code']})

        zero = preview(opener, base, {'instruction': '预算为零的独立任务。', 'budget_usd': 0})
        submit(opener, base, zero)
        zero = wait_task(opener, base, zero['task_id'], expected='budget_exhausted')
        assert statistics(zero)['upstream_requests'] == 0, zero
        assert statistics(api(opener, base, task_id=first['task_id']))['upstream_requests'] == 5
        rows.append(summary('per-task-budget-zero', zero))

        # 普通官方聊天输入同样进入任务登记；无需前端自造 Agent 循环。
        created = native_rpc(opener, base, 'session/create', {})
        assert created['ok'], created
        session_id = created['value']['sessionId']
        result = native_rpc(opener, base, 'session/prompt', {'sessionId': session_id,
            'requestId': str(uuid4()), 'mode': 'queue', 'content': [{'type': 'text', 'text': '新问题：阅读笔记并核验来源。'}]})
        assert result['ok'], result
        listing = api(opener, base)
        native = [task for task in listing['tasks'] if task['session_id'] == session_id]
        assert len(native) == 1, listing
        native_result = wait_task(opener, base, native[0]['task_id'])
        assert statistics(native_result)['upstream_requests'] == 5, native_result
        rows.append(summary('native-chat-dynamic-task', native_result))
        listing = api(opener, base)
        assert listing.get('aggregate') is not None
        assert len({task['task_id'] for task in listing['tasks']}) == len(listing['tasks'])
    return rows


def portfolio_checks():
    rows = []
    with launch('portfolio-v1') as (opener, base, output):
        prompt = (output / 'prompt.md').read_text(encoding='utf-8').strip()
        for mode in ('baseline', 'shadow', 'execute'):
            draft = preview(opener, base, {'instruction': prompt, 'mode': mode})
            submit(opener, base, draft)
            result = wait_task(opener, base, draft['task_id'])
            stats = statistics(result)
            assert result['mode'] == mode and stats['tool_calls'] == 13, result
            assert stats['upstream_requests'] == (7 if mode == 'execute' else 14), result
            assert stats['verified_skips'] == (5 if mode == 'execute' else 0), result
            if mode == 'shadow':
                assert stats['shadow_candidates'] > 0, result
            rows.append(summary('portfolio-' + mode, result))
        changed = preview(opener, base, {'instruction': prompt + '\n请额外检查本轮新增要求。', 'mode': 'execute'})
        submit(opener, base, changed)
        changed = wait_task(opener, base, changed['task_id'])
        assert statistics(changed)['verified_skips'] == 0 and statistics(changed)['upstream_requests'] == 14, changed
        rows.append(summary('changed-task-motif-fallback', changed))
    return rows


def cancellation_check():
    with launch('example', fixture='delay') as (opener, base, _output):
        draft = preview(opener, base, {'instruction': '读取两条笔记；此轮用于测试用户取消。'})
        submit(opener, base, draft)
        api(opener, base, {'action': 'cancel', 'task_id': draft['task_id']})
        cancelled = wait_task(opener, base, draft['task_id'], expected='cancelled')
        assert statistics(cancelled)['upstream_requests'] <= 1, cancelled
        return summary('active-task-cancellation', cancelled)


if __name__ == '__main__':
    os.umask(0o077)
    rows = [*example_checks(), *portfolio_checks(), cancellation_check()]
    report = {'diagnostic_type': 'real-harness-http-with-mock-provider', 'paid_calls': 0,
              'browser_verified': False, 'groups': rows}
    path = ROOT / '.local/web/tasks-protocol-check.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
