#!/usr/bin/env python3
"""原生命令与场景切换协议验收；--real-model 在服务器使用已授权真实 API。"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('web_checks', ROOT / 'scripts/check-web-tasks.py')
web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-model', action='store_true')
    parser.add_argument('--port', type=int, default=3093)
    args = parser.parse_args()
    os.umask(0o077)
    run_id = uuid4().hex
    output = ROOT / '.local/web/runs' / run_id
    checks = ROOT / '.local/harless-controls'; checks.mkdir(parents=True, exist_ok=True)
    base = f'http://127.0.0.1:{args.port}'
    def settings(body=None, session=None, expected=200):
        path = '/api/harless/settings' + ('?session_id=' + session if session else '')
        status, value = web.request(opener, base, path, body)
        assert status == expected, (status, value)
        return value
    def command(session, line):
        envelope = {'type': 'client-request', 'rpcId': str(uuid4()), 'method': 'commands/execute',
                    'payload': {'args': {'agentId': session, 'line': line, 'submittedAttachments': []}}}
        status, value = web.request(opener, base, '/api/commands/execute', envelope)
        assert status == 200 and value['result']['ok'], value
        return value['result']['value']['result']
    groups = []
    with (checks / (run_id + '.log')).open('w') as log:
        child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/harness-web.py'), '--scenario', 'example', '--scene-registry', 'config/harless-diagnostics.json', '--port', str(args.port),
            '--run-id', run_id, '--mode', 'shadow', '--budget-usd', '0.03', '--run-budget-usd', '0.06',
            '--request-limit', '24', '--run-request-limit', '32' if args.real_model else '64', *(['--real-model'] if args.real_model else [])], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(300):
                if (output / 'access-url.txt').exists(): break
                if child.poll() is not None: raise RuntimeError('启动失败：' + str(checks / (run_id + '.log')))
                time.sleep(.1)
            else: raise RuntimeError('启动超时')
            opener = web.client()
            status, _ = web.request(opener, base, '/api/harless/settings'); assert status == 401
            opener.open((output / 'access-url.txt').read_text().strip(), timeout=20).close()
            value = settings(); assert len(value['scenes']) == 3
            created = web.native_rpc(opener, base, 'session/create', {}); assert created['ok'], created
            session = created['value']['sessionId']
            for line in ['/harless', '/harless list', '/harless mode', '/harless rsi', '/harless status']:
                assert command(session, line)['kind'] == 'success'
            for line in ['/harless off', '/harless mode wrong', '/harless rsi perhaps', '/harless missing']:
                assert command(session, line)['kind'] == 'error'
            assert command(session, '/harless rsi off')['kind'] == 'success'
            assert settings(session=session)['selection']['mode'] == 'shadow'
            assert command(session, '/harless rsi on')['kind'] == 'success'
            assert settings(session=session)['selection']['mode'] == 'shadow'
            assert command(session, '/harless portfolio-v1')['kind'] == 'success'
            assert settings(session=session)['selection']['scene'] == 'portfolio-v1'
            # Preview after native recomposition must capture only the selected tools.
            draft = web.api(opener, base, {'action':'preview', 'session_id':session, 'request':'仅检查场景工具快照，不运行模型。'})
            snapshot = json.loads((output / 'tasks' / draft['task_id'] / 'effective-config.json').read_text())
            assert snapshot['tools'] and all(tool['name'].startswith('mcp__research_portfolio_fixture__') for tool in snapshot['tools'])
            changed = settings({'action':'select', 'session_id':session, 'selection':{'scene':'example','rsi':False}})
            assert changed['applies_to'] == 'next_task' and changed['current_task']['scene'] == 'portfolio-v1'
            assert web.api(opener, base, task_id=draft['task_id'])['confirmation_digest'] == draft['confirmation_digest']
            inherited = settings({'action':'new_session','inherit_session':session})
            assert inherited['session_id'] != session and inherited['selection']['scene'] == 'example'
            web.api(opener, base, {'action':'cancel','task_id':draft['task_id']})
            assert not web.api(opener, base)['aggregate'].get('upstream_requests')
            assert settings({'action':'select','selection':{'mode':'execute'}},expected=400)['error']['code'] == 'execute_unavailable'
            groups.append({'group':'commands-modes-presets-frozen-preview-inheritance','passed':True,'model_requests':0})
            # Two genuine independent tasks on different tool surfaces, same run ledger.
            task_inputs = [('example','读取 note:alpha 和 note:beta，简短说明两次试验能否直接比较，并引用 source_id 与 version_sha256。'),
                                       ('portfolio-v1',(ROOT / 'benchmarks/research_decision_portfolio_v1/cases/l_retrieval_persistence/task.md').read_text().strip())]
            if not args.real_model: task_inputs.append(('portfolio-v2',(ROOT / 'benchmarks/research_decision_portfolio_v2/cases/e_state_vs_retrieval/task.md').read_text().strip()))
            for scene, instruction in task_inputs:
                settings({'action':'select','selection':{'scene':scene,'mode':'shadow'}})
                draft = web.api(opener, base, {'action':'preview','request':instruction})
                assert draft['scene'] == scene and draft['mode'] == 'shadow'
                assert draft['stats']['upstream_requests'] == 0
                web.submit(opener, base, draft)
                result = web.wait_task(opener, base, draft['task_id'], seconds=120)
                stats = result['stats']; assert stats['upstream_requests'] > 0 and stats['tool_calls'] > 0
                assert stats['tool_errors'] == 0 and stats['verified_skips'] == 0
                groups.append({'group':scene+'-shadow','task_id':result['task_id'],'session_id':result['session_id'], 'status':result['status'], 'stats':stats,'fallback_reason':result['fallback_reason']})
            assert len({group['session_id'] for group in groups if 'session_id' in group}) == len(task_inputs)
        finally:
            if child.poll() is None: child.send_signal(signal.SIGTERM)
            try: child.wait(timeout=15)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
    report = {'run_id':run_id,'provider_mode':'real' if args.real_model else 'mock', 'browser_verified':False,
              'model':'deepseek-flash','reasoning_effort':'off','mode':'shadow','run_budget_usd':.06,'task_budget_usd':.03,
              'task_request_limit':24,'run_request_limit':32 if args.real_model else 64,'max_output_tokens':1000,'groups':groups,'quality_reviewed':False}
    (checks / (run_id + '.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (checks / 'latest.json').write_text(json.dumps({'run_id':run_id,'report':run_id+'.json'}))
    print(json.dumps(report,ensure_ascii=False))
if __name__ == '__main__': main()
