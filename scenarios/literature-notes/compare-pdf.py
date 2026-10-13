"""Run a paid, matched PDF pilot against Harness and ordinary script baselines."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
from pdf_tools import ROOT, save_private
HERE = Path(__file__).resolve().parent

class ClosedReadOnly(BaseHTTPRequestHandler):
    calls = 0
    def log_message(self, *_args):
        pass
    def do_POST(self):
        type(self).calls += 1
        # No fake vectors: this pilot must use the existing closed-read proof path.
        self.send_error(503, 'Semantic embeddings unavailable: closed read experiment only')

def compare(args):
    if not 0 < args.budget_usd <= 100:
        raise ValueError('comparison total cap must be in (0, 100]')
    output = args.resume.resolve() if args.resume else ROOT / '.local/literature-notes' / ('comparison-' + uuid4().hex)
    if not output.is_relative_to(ROOT / '.local'):
        raise ValueError('comparison output must be private')
    if not args.resume:
        output.mkdir(mode=0o700, parents=True)
    plan = {'question': args.question, 'papers_directory': str(args.papers_dir.resolve()), 'manifest': str(args.manifest.resolve()),
            'arms': ['baseline', 'execute', 'script'], 'budget_cap_usd': args.budget_usd,
            'max_output': args.max_output, 'max_steps': args.max_steps, 'cache_policy': 'reuse',
            'reasoning_effort': 'off', 'human_blind_review_completed': False,
            'scope': 'controlled one-decision pilot; all arms need independent quality review'}
    rows, spent = [], 0.0
    if args.resume:
        prior = json.loads((output / 'comparison.json').read_text())
        for key in ('question', 'papers_directory', 'max_output', 'max_steps', 'cache_policy', 'budget_cap_usd'):
            if prior['plan'][key] != plan[key]:
                raise ValueError('resumed comparison must preserve workload and total budget')
        rows = prior['arms']
        if any(row['exit_code'] != 0 for row in rows):
            raise ValueError('cannot resume a failed paid arm')
        spent = sum(row['accounted_usd'] for row in rows)
        plan['resume_from_manifest'] = prior['plan']['manifest']
        save_private(output / 'resume-plan.json', plan)
    else:
        save_private(output / 'plan.json', plan)
    ClosedReadOnly.calls = 0
    with ThreadingHTTPServer(('127.0.0.1', 0), ClosedReadOnly) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        try:
            for arm in plan['arms']:
                if any(row['arm'] == arm for row in rows):
                    continue
                cap = args.budget_usd - spent
                if cap < 0.002:
                    break
                command = [sys.executable, str(HERE / 'run-pdf.py'), '--call-model',
                    '--question', args.question, '--papers-dir', str(args.papers_dir), '--budget-usd', str(cap), '--max-output', str(args.max_output),
                    '--max-steps', str(args.max_steps), '--rate-retries', '1', '--retry-delay', '30']
                if arm == 'script':
                    command.append('--script-read')
                elif arm == 'execute':
                    command += ['--mode', 'execute', '--manifest', str(args.manifest), '--auto-motif-task',
                                '--embedding-endpoint', f'http://127.0.0.1:{server.server_port}/v1/embeddings',
                                '--embedding-model', 'disabled-closed-source-proof-only']
                started = time.monotonic()
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                launcher_seconds = time.monotonic() - started
                print(result.stdout, end='', flush=True)
                if result.stderr:
                    print(result.stderr, file=sys.stderr, end='')
                (output / (arm + '-stdout.txt')).write_text(result.stdout); (output / (arm + '-stdout.txt')).chmod(0o600)
                values = []
                for line in result.stdout.splitlines():
                    try:
                        value = json.loads(line)
                        if isinstance(value, dict): values.append(value)
                    except ValueError:
                        pass
                summaries = [v for v in values if 'output_dir' in v]
                if not summaries or any(not isinstance(v.get('budget_accounted_usd'), (int,float)) for v in summaries):
                    raise ValueError('missing cost accounting; remaining paid arms stopped')
                arm_cost = sum(v['budget_accounted_usd'] for v in summaries)
                if not 0 <= arm_cost <= cap + 1e-12:
                    raise ValueError('inconsistent cost accounting; remaining arms stopped')
                spent += arm_cost
                rows.append({'arm': arm, 'attempts': summaries, 'accounted_usd': arm_cost,
                             'end_to_end_launcher_seconds': launcher_seconds,
                             'exit_code': result.returncode, 'quality': 'unreviewed'})
                save_private(output / 'comparison.json', {'plan': plan, 'arms': rows, 'accounted_usd': spent,
                             'embedding_requests': ClosedReadOnly.calls,
                             'quality_equivalence_established': False, 'efficiency_claim_qualified': False})
                if result.returncode != 0:
                    # A failed baseline invalidates this paired comparison. Keep its real costs.
                    break
            return {'output': str(output), 'arms_completed': len(rows), 'accounted_usd': spent,
                    'embedding_requests': ClosedReadOnly.calls, 'quality_equivalence_established': False}
        finally:
            server.shutdown(); worker.join(timeout=5)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--question', required=True)
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--budget-usd', type=float, default=0.09)
    parser.add_argument('--max-output', type=int, default=3500)
    parser.add_argument('--max-steps', type=int, default=40)
    args = parser.parse_args(); print(json.dumps(compare(args), ensure_ascii=False))
