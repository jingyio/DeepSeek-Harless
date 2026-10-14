"""Small controlled comparison; this is experiment orchestration, not an Agent loop."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pdf_tools import ROOT, digest, inventory, save_private
from pdf_dependencies import private_file
from runpy import run_path

HERE = Path(__file__).resolve().parent


def compare(experiment, manifest, *, call_model=False):
    experiment = Path(experiment).resolve()
    plan = json.loads(private_file(experiment / 'experiment-plan.json').read_text())
    papers = experiment / 'changed-pdfs'
    if inventory(papers) != plan['input_inventory']:
        raise ValueError('comparison input changed')
    if (experiment / 'comparison.json').exists():
        raise ValueError('comparison exists; preserve it and start a new experiment')
    module = run_path(str(HERE / 'compare-pdf.py'))
    handler = module['ClosedReadOnly']; handler.calls = 0
    rows, spent = [], 0.0
    with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        try:
            for arm in plan['run_order']:
                if inventory(papers) != plan['input_inventory']:
                    raise ValueError('comparison sources changed between arms')
                cap = 100 - spent
                command = [sys.executable, str(HERE / ('run-pdf.py' if arm == 'full_harness' else 'run-incremental.py')),
                           '--papers-dir', str(papers), '--question', plan['question'],
                           '--budget-usd', str(cap), '--max-steps', str(plan['max_steps']), '--max-output', str(plan['max_output'])]
                if arm != 'full_harness': command += ['--dependencies', str(experiment / 'dependencies.json')]
                else: command += ['--rate-retries', '0']
                if arm == 'incremental_motif':
                    command += ['--mode', 'execute', '--manifest', str(manifest),
                                '--embedding-endpoint', f'http://127.0.0.1:{server.server_port}/v1/embeddings',
                                '--embedding-model', 'disabled-closed-source-proof-only']
                if call_model: command.append('--call-model')
                print(json.dumps({'arm': arm, 'remaining_technical_budget_usd': cap, 'model_enabled': call_model}), flush=True)
                started = time.monotonic()
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
                elapsed = time.monotonic() - started
                stdout = experiment / (arm + '-stdout.txt'); stdout.write_text(result.stdout); stdout.chmod(0o600)
                stderr = experiment / (arm + '-stderr.txt'); stderr.write_text(result.stderr); stderr.chmod(0o600)
                print(result.stdout, end='', flush=True)
                if result.stderr: print(result.stderr, file=sys.stderr, end='')
                values = []
                for line in result.stdout.splitlines():
                    try:
                        value = json.loads(line)
                        if isinstance(value, dict): values.append(value)
                    except ValueError: pass
                summaries = [v for v in values if 'output_dir' in v]
                costs_complete = all(isinstance(v.get('budget_accounted_usd'), (int, float))
                                     and 0 <= v['budget_accounted_usd'] <= cap for v in summaries)
                arm_cost = sum(v['budget_accounted_usd'] for v in summaries) if costs_complete else None
                if call_model and (not summaries or not costs_complete):
                    rows.append({'arm': arm, 'exit_code': result.returncode, 'accounted_usd': arm_cost,
                                 'cost_complete': False, 'end_to_end_launcher_seconds': elapsed})
                    save_private(experiment / 'comparison.json', {'plan': plan, 'arms': rows,
                        'accounted_usd': spent, 'cost_complete': False, 'quality_equivalence_established': False})
                    raise ValueError('missing actual usage; remaining arms stopped')
                spent += arm_cost or 0
                task_dirs = [v.get('pdf_task_directory') or v.get('incremental_directory') for v in values
                             if v.get('pdf_task_directory') or v.get('incremental_directory')]
                rows.append({'arm': arm, 'attempts': summaries, 'accounted_usd': arm_cost or 0,
                             'cost_complete': costs_complete, 'exit_code': result.returncode,
                             'end_to_end_launcher_seconds': elapsed,
                             'task_directory': task_dirs[0] if task_dirs else None,
                             'quality': 'independent_support_review_pending'})
                if call_model:
                    save_private(experiment / 'comparison.json', {'plan': plan, 'arms': rows, 'accounted_usd': spent,
                        'embedding_requests': handler.calls, 'cost_complete': True,
                        'quality_equivalence_established': False, 'efficiency_claim_qualified': False})
                if result.returncode: break
            return {'experiment': str(experiment), 'arms_completed': len(rows), 'accounted_usd': spent,
                    'embedding_requests': handler.calls, 'model_enabled': call_model,
                    'quality_equivalence_established': False}
        finally:
            server.shutdown(); worker.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    print(json.dumps(compare(args.experiment, args.manifest, call_model=args.call_model), ensure_ascii=False))
