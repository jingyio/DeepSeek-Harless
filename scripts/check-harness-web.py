#!/usr/bin/env python3
"""Official HTTP session/MCP diagnostics, distinct from required browser acceptance."""
import http.cookiejar
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def rpc(opener, base, method, request):
    body = {'type': 'client-request', 'rpcId': str(uuid4()), 'method': method,
            'payload': {'args': {'request': request}}}
    req = urllib.request.Request(base + '/api/' + method, data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'Origin': base})
    with opener.open(req, timeout=30) as response:
        return json.load(response)['result']


def run(scenario, mode, *, limit=24, budget=0.25, fixture='normal'):
    runs = ROOT / '.local/web/runs'; runs.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    output = runs / run_id
    logpath = ROOT / '.local/web/check-startup.log'
    with logpath.open('w') as log:
        child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/harness-web.py'),
            '--scenario', scenario, '--mode', mode, '--port', '3082',
            '--run-id', run_id,
            '--fixture', fixture,
            '--request-limit', str(limit), '--budget-usd', str(budget)],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(200):
                if (output / 'access-url.txt').exists(): break
                if child.poll() is not None: raise RuntimeError('Web launcher failed; see private check-startup.log')
                time.sleep(0.1)
            else: raise RuntimeError('Web startup timeout')
            base = 'http://127.0.0.1:3082'
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            try:
                rpc(opener, base, 'session/create', {})
                raise AssertionError('Unauthenticated session creation accepted')
            except urllib.error.HTTPError as error: assert error.code == 401
            with opener.open((output / 'access-url.txt').read_text()) as response: assert response.status == 200
            created = rpc(opener, base, 'session/create', {}); assert created['ok'], created
            session = created['value']['sessionId']
            assert not rpc(opener, base, 'session/create', {})['ok'], 'second session accepted'
            assert not rpc(opener, base, 'session/create', {'agentPreset': 'standard'})['ok']
            assert not rpc(opener, base, 'session/fork', {'sessionId': session})['ok']
            assert not rpc(opener, base, 'session/selectModel', {'sessionId': session,
                'provider': 'openai', 'model': 'gpt-any'})['ok']
            prompt = (output / 'prompt.md').read_text().strip()
            def submit(text, sid=session):
                return rpc(opener, base, 'session/prompt', {'sessionId': sid,
                    'requestId': str(uuid4()), 'mode': 'queue', 'content': [{'type': 'text', 'text': text}]})
            assert not submit(prompt + '\nAnother question')['ok']
            assert not submit(prompt, 'wrong-session')['ok']
            accepted = submit(prompt); assert accepted['ok'], accepted
            if fixture == 'delay':
                assert rpc(opener, base, 'session/cancel', {'sessionId': session})['ok']
            for _ in range(300):
                state = json.loads((output / 'task-state.json').read_text())
                if state['status'] not in ('ready', 'running'): break
                time.sleep(0.1)
            else: raise AssertionError('Task timeout')
            assert not submit(prompt)['ok'], 'second task admitted'
            time.sleep(.3)
            metrics = json.loads((output / 'metrics.json').read_text())
            expected = 'completed' if limit == 24 and budget > 0 else 'budget_exhausted'
            if fixture == 'tool-failure': expected = 'budget_exhausted'
            if fixture == 'provider-failure': expected = 'failed'
            if fixture == 'delay': expected = 'cancelled'
            assert state['status'] == expected, state
            if expected == 'completed':
                assert (output / 'answer.json').exists()
                events = [json.loads(line) for line in (output / 'events.jsonl').read_text().splitlines()]
                count = sum(event['type'] == 'tool/call' for event in events)
                expected_calls = (5 if fixture == 'outside-tool' else 4) if scenario == 'example' else 13
                assert count == expected_calls, {'observed': count, 'expected': expected_calls}
                observed = json.loads((output / 'effective-config.json').read_text())['observed_model_request']
                assert observed == {'model': 'deepseek-flash', 'thinking': {'type': 'disabled'}, 'max_tokens': 1000}, observed
                if scenario == 'example': assert metrics['mock_requests'] == (6 if fixture == 'outside-tool' else 5), metrics
                if mode == 'execute' and fixture != 'stale': assert metrics['verified_skips'] > 0, metrics
                if fixture == 'stale': assert metrics['verified_skips'] == 0 and metrics['mock_requests'] == 14, metrics
                if mode == 'shadow': assert metrics['shadow_candidates'] > 0 and metrics['verified_skips'] == 0, metrics
            else:
                assert metrics['mock_requests'] <= limit
            if fixture == 'tool-failure':
                assert metrics['motif_attempts'] > 0 and metrics['mock_requests'] > 14, metrics
                audits = [json.loads(line) for line in (output / 'motif-audit.jsonl').read_text().splitlines()]
                failed = {row['batch_id'] for row in audits if row.get('kind') == 'bypass_result_unverified'}
                verified = {row['batch_id'] for row in audits if row.get('kind') == 'model_request_skipped_verified'}
                assert failed and failed.isdisjoint(verified), 'a failed batch was counted as a verified skip'
            return {'run_id': output.name, 'scenario': scenario, 'mode': mode, 'fixture': fixture, **metrics, 'status': state['status']}
        finally:
            child.send_signal(signal.SIGTERM)
            try: child.wait(timeout=15)
            except subprocess.TimeoutExpired: child.kill(); child.wait()


if __name__ == '__main__':
    os.umask(0o077)
    rows = [run('example', 'baseline'), run('example', 'baseline', limit=1),
            run('example', 'baseline', budget=0),
            *[run('portfolio-v1', mode) for mode in ('baseline', 'shadow', 'execute')],
            run('portfolio-v1', 'execute', fixture='stale'),
            run('portfolio-v1', 'execute', fixture='tool-failure'),
            run('example', 'baseline', fixture='outside-tool'),
            run('example', 'baseline', fixture='provider-failure'),
            run('example', 'baseline', fixture='delay')]
    path = ROOT / '.local/web/protocol-check.json'; path.write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, ensure_ascii=False))
