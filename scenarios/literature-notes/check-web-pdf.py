"""Two-question official Web/Harness/MCP acceptance; free protocol default, explicit paid option."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4
from pdf_tools import DEFAULT_QUESTION, ROOT, inventory, save_private
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod); return mod


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--port', type=int, default=3085)
    args = parser.parse_args()
    web = load('web_http_diagnostic', ROOT / 'scripts/check-web-tasks.py')
    run_id = uuid4().hex
    experiment = ROOT / '.local/literature-notes' / ('web-binding-20261012-' + run_id[:8])
    output = ROOT / '.local/web/runs' / run_id
    sources = inventory(args.papers_dir)
    questions = [DEFAULT_QUESTION, '在不改变模型权重的前提下，这三篇论文哪些操作可用于科研文献Agent的结构复用，哪些科研判断仍需模型？']
    save_private(experiment / 'protocol.json', {'schema_version': 1, 'provider': 'real' if args.call_model else 'mock',
        'questions': questions, 'sources': sources, 'mode': 'baseline', 'reasoning_effort': 'off',
        'compression': False, 'max_output_tokens': 8000, 'task_budget_usd': 3, 'run_budget_usd': 6,
        'task_request_limit': 90, 'run_request_limit': 180, 'whole_task_retries': 0,
        'human_review_required': False, 'scientific_quality': 'unverified',
        'files_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [ROOT / 'scripts/harness-web.py', ROOT / 'src/adapters/dsh_web_tasks.ts',
                      *sorted(HERE.glob('web*.*'))]}, 'run_id': run_id})
    command = [sys.executable, str(HERE / 'run-web.py'), '--papers-dir', str(args.papers_dir),
               '--port', str(args.port), '--run-id', run_id]
    if args.call_model: command.append('--real-model')
    log = (experiment / 'launcher.log').open('w'); os.chmod(log.name, 0o600)
    process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:' + str(args.port)
    rows = []
    try:
        for _ in range(300):
            if process.poll() is not None: raise RuntimeError('Web startup failed; inspect private launcher log')
            if (output / 'access-url.txt').is_file(): break
            time.sleep(.1)
        else: raise RuntimeError('Web startup timeout')
        opener = web.client(); opener.open((output / 'access-url.txt').read_text().strip()).close()
        for index, question in enumerate(questions):
            started = time.monotonic()
            draft = web.api(opener, base, {'action': 'preview', 'request': {'instruction': question,
                'request_id': run_id + '-question-' + str(index), 'budget_usd': 3, 'mode': 'baseline'}})
            duplicate = web.api(opener, base, {'action': 'preview', 'request': {'instruction': question,
                'request_id': run_id + '-question-' + str(index), 'budget_usd': 3, 'mode': 'baseline'}})
            assert draft['task_id'] == duplicate['task_id'] and draft['session_id'] == duplicate['session_id']
            assert draft['paid_calls_enabled'] == args.call_model
            assert web.denied(opener, base, {'action': 'submit', 'task_id': draft['task_id'],
                'confirmation_digest': 'changed'}) == 'confirmation_changed'
            web.submit(opener, base, draft)
            result = web.wait_task(opener, base, draft['task_id'], seconds=300)
            assert result['delivery']['question'] == question
            assert result['delivery']['claim_count'] == 5 * len(sources['papers'])
            assert result['delivery']['human_review_required'] is False
            if rows: assert result['session_id'] != rows[0]['session_id']
            taskdir = output / 'tasks' / result['task_id']
            events = [json.loads(x) for x in (taskdir / 'events.jsonl').read_text().splitlines()]
            assert sum(e['type'] == 'turn/start' for e in events) == 1
            assert any(e['type'] == 'tool/call' and e['data']['name'].endswith('__deliver_research_notes') for e in events)
            result['acceptance_elapsed_seconds'] = time.monotonic() - started
            save_private(experiment / ('question-' + str(index + 1) + '.json'), result)
            rows.append({k: result[k] for k in ('task_id', 'session_id', 'status', 'stats', 'delivery_status', 'scene_binding_sha256')})
            print(json.dumps({'experiment': experiment.name, 'question': index + 1, 'task_id': result['task_id'],
                'status': result['status'], 'gap_count': result['delivery']['gap_count'],
                'model_requests': result['stats']['model_requests'], 'estimated_cost_usd': result['stats']['estimated_cost_usd']}, ensure_ascii=False), flush=True)
        assert inventory(args.papers_dir) == sources
        if not args.call_model:
            draft = web.preview(opener, base, '取消测试；不形成科研结论')
            web.submit(opener, base, draft)
            web.api(opener, base, {'action': 'cancel', 'task_id': draft['task_id']})
            cancelled = web.wait_task(opener, base, draft['task_id'], expected='cancelled')
            save_private(experiment / 'cancel.json', cancelled)
        save_private(experiment / 'outcome.json', {'experiment': experiment.name, 'run_id': run_id, 'tasks': rows,
            'sources_unchanged': True, 'browser_verified': False, 'scientific_quality': 'automatic_unverified',
            'model_requests': sum(r['stats']['model_requests'] for r in rows),
            'estimated_cost_usd': sum(r['stats']['estimated_cost_usd'] for r in rows),
            'actual_paid_usd': None if args.call_model else 0, 'verified_skips': 0})
    except Exception as error:
        save_private(experiment / 'failure.json', {'error': str(error), 'completed_tasks': rows,
            'costs_preserved_in': str(output), 'whole_task_retry': False})
        raise
    finally:
        # The launcher forwards TERM to the actual Harness and closes admission.
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try: process.wait(timeout=20)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        log.close()


if __name__ == '__main__': main()
