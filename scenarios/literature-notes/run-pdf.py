"""Prepare a frozen local PDF task and reuse the existing bounded Harness runner."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from uuid import uuid4

from pdf_tools import DEFAULT_QUESTION, ROOT, digest, inventory, save_private

HERE = Path(__file__).resolve().parent


def runtime_snapshot():
    return {'platform': platform.platform(), 'python': platform.python_version(),
            'node': subprocess.check_output(['node', '--version'], text=True).strip(),
            'sdk': importlib.metadata.version('deepseek-harness-sdk'),
            'mcp': importlib.metadata.version('mcp'),
            'dsh': json.loads((ROOT / 'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'],
            'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'git_status': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
            'scene_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(HERE.glob('*')) if path.suffix in ('.py', '.json', '.md', '.ts')},
            'completion_guard_sha256': hashlib.sha256((ROOT / 'src/adapters/dsh_completion_guard.ts').read_bytes()).hexdigest(),
            'compression_enabled': False, 'reasoning_effort': 'off'}


def prepare_task(directory: Path, question: str, *, cache_policy='reuse'):
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise ValueError('研究问题需要 1–4000 字符。')
    task = {'schema_version': 1, 'question': question.strip(), 'sources': inventory(directory)}
    output = ROOT / '.local/literature-notes/pdf-tasks' / uuid4().hex
    save_private(output / 'task.json', task)
    scenario = json.loads((HERE / 'pdf-scenario.json').read_text(encoding='utf-8'))
    prompt = output / 'prompt.md'
    prompt.write_text((HERE / 'pdf-task.md').read_text(encoding='utf-8')
                      + '\n' + (HERE / 'research-checklist.md').read_text(encoding='utf-8')
                      + '\n本次研究问题（仍须通过 list_pdfs 核对任务快照）：\n' + task['question'] + '\n',
                      encoding='utf-8')
    prompt.chmod(0o600)
    scenario['prompt'] = str(prompt)
    save_private(output / 'scenario.json', scenario)
    env = {'SSS_PDF_ROOT': task['sources']['root'], 'SSS_PDF_TASK_FILE': str(output / 'task.json'),
           'SSS_PDF_CACHE': str(ROOT / '.local/literature-notes/pdf-cache'),
           'SSS_PDF_CACHE_POLICY': cache_policy, 'SSS_PDF_SCRIPT_READ': '0',
           'SSS_PDF_DELIVERY': str(output / 'delivery')}
    # Shared runner already records source events/configs; bind the extra PDF task and parser policy.
    save_private(output / 'input-snapshot.json', {'task_sha256': digest(task), 'task': task,
                 'cache_policy': cache_policy, 'tools_sha256': hashlib.sha256((HERE / 'pdf_tools.py').read_bytes()).hexdigest(),
                 'runtime': runtime_snapshot(), 'paid_api_requests': 0, 'scope': 'preflight_only'})
    return output, env


def collect_preview(run_directory: Path, task_directory: Path):
    """Collect tool-authoritative artifacts, never substitute the model's final status."""
    sys.path.insert(0, str(ROOT))
    from src.adapters.dsh_trajectory import extract_dsh_trace
    from src.adapters.tool_contract_loader import parse_tool_contracts
    events_path = run_directory / 'agent-events.jsonl'
    if not events_path.is_file():
        return {'status': 'missing_preview', 'reason': 'no_original_events'}
    events = [json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines()]
    contracts = parse_tool_contracts(json.loads((HERE / 'pdf-contracts.json').read_text(encoding='utf-8')))
    trace = extract_dsh_trace(events, contracts, trace_id=run_directory.name)
    previews = [record.observation for record in trace.records
                if record.name.endswith('__preview_research_notes') and record.observation
                and record.observation.get('status') in ('preview', 'needs_review')]
    if not previews:
        result = {'status': 'missing_preview', 'reason': 'no_validated_tool_preview'}
    else:
        preview = previews[-1]
        if 'artifact' in preview:
            artifact = Path(preview['artifact'])
            if artifact.is_symlink() or artifact.resolve().parent != (task_directory / 'delivery').resolve():
                raise ValueError('untrusted delivery artifact location')
            payload = json.loads(artifact.read_text(encoding='utf-8'))
            task = json.loads((task_directory / 'task.json').read_text(encoding='utf-8'))
            if (digest(payload) != preview['artifact_sha256'] or payload.get('task_sha256') != digest(task)
                    or payload.get('status') != preview['status']):
                raise ValueError('delivery receipt content/version mismatch')
            save_private(run_directory / 'delivery-receipt.json', preview)
            preview = payload
        save_private(run_directory / 'evidence.json', preview)
        path = run_directory / 'research-notes.md'
        path.write_text(preview['markdown'], encoding='utf-8')
        path.chmod(0o600)
        result = {'status': preview['status'], 'research_quality': 'unreviewed',
                  'citation_count': len(preview['citation_checks']), 'gap_count': len(preview['gaps']),
                  'evidence': str(run_directory / 'evidence.json'), 'notes': str(path)}
    save_private(run_directory / 'pdf-input-snapshot.json',
                 json.loads((task_directory / 'input-snapshot.json').read_text(encoding='utf-8')))
    save_private(run_directory / 'pdf-delivery.json', result)
    return result


def rate_limited(run_directory):
    """Only the recorded provider RATE_LIMIT event authorizes a bounded rerun."""
    path = run_directory / 'agent-events.jsonl'
    if not path.is_file():
        return False
    ledger = run_directory / 'cost-ledger.jsonl'
    if not ledger.is_file():
        return False
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    if not rows or rows[-1].get('response_status') != 429:
        return False  # A local reservation denial also presents as HTTP 429; retry cannot fix it.
    for line in path.read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        if event.get('type') == 'turn/end':
            error = event.get('data', {}).get('reason', {}).get('error', {})
            if error.get('code') == 'RATE_LIMIT' and error.get('status') == 429:
                return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--question', default=DEFAULT_QUESTION)
    parser.add_argument('--cache-policy', choices=['off', 'reuse'], default='reuse')
    parser.add_argument('--budget-usd', type=float, default=0.25)
    parser.add_argument('--max-steps', type=int, default=32)
    parser.add_argument('--max-output', type=int, default=8000)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--script-read', action='store_true', help='ordinary deterministic pin/read composition')
    parser.add_argument('--mode', choices=['baseline', 'shadow', 'execute'], default='baseline')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--task', type=Path)
    parser.add_argument('--entry-policy', type=Path, help='certified inventory preparation frontier; default off')
    parser.add_argument('--auto-motif-task', action='store_true', help='bind a read-only experiment task to this frozen PDF input')
    parser.add_argument('--embedding-endpoint')
    parser.add_argument('--embedding-model')
    parser.add_argument('--rate-retries', type=int, default=1)
    parser.add_argument('--retry-delay', type=int, default=15)
    args = parser.parse_args(argv)
    if not 0 < args.budget_usd <= 100 or not 1 <= args.max_steps <= 100 or not 1 <= args.max_output <= 8000:
        parser.error('invalid budget/step/output limits')
    if not 0 <= args.rate_retries <= 2 or not 1 <= args.retry_delay <= 30:
        parser.error('invalid bounded retry settings')
    if args.script_read and args.mode != 'baseline':
        parser.error('script comparison is a baseline, not a Motif mode')
    if args.entry_policy and (args.mode != 'baseline' or args.script_read or args.manifest or args.task or args.auto_motif_task):
        parser.error('inventory entry requires native baseline without legacy Motif or script mode')
    env = os.environ.copy()
    try:
        output, task_env = prepare_task(args.papers_dir, args.question, cache_policy=args.cache_policy)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    env.update(task_env)
    entry_path = None
    if args.entry_policy:
        from inventory_entry import private_policy, entry_task
        from pdf_tools import PdfScene
        policy = private_policy(args.entry_policy)
        scene = PdfScene(args.papers_dir, Path(task_env['SSS_PDF_CACHE']), json.loads((output / 'task.json').read_text()))
        entry_path = output / 'entry-task.json'
        save_private(entry_path, entry_task(scene, output.name))
    if args.call_model:
        spec = importlib.util.spec_from_file_location('literature_key', HERE / 'run-live.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        try:
            env['DEEPSEEK_API_KEY'] = module.load_key(module.KEY_FILE, env)
        except ValueError as exc:
            parser.error(str(exc))
    if args.auto_motif_task:
        if args.mode == 'baseline' or not args.manifest or args.task:
            parser.error('auto motif task requires shadow/execute, a manifest, and no external task')
        task = json.loads((output / 'task.json').read_text())
        args.task = output / 'motif-task.json'
        from pdf_tools import PdfScene
        scene = PdfScene(args.papers_dir, Path(task_env['SSS_PDF_CACHE']), task)
        versions = [scene.prepare_pdf(paper['paper_id'])['document_version_sha256']
                    for paper in task['sources']['papers']]
        save_private(args.task, {'schema_version': 1, 'task_id': output.name,
            'session_id': 'pdf-motif-' + uuid4().hex, 'intent': task['question'], 'input_version': digest(task),
            'bindings': {}, 'source_versions': {'mcp__literature_pdf__pin_pdf_context': versions,
                                               'mcp__literature_pdf__read_pinned_pdf_context': versions}})
    env['SSS_PDF_SCRIPT_READ'] = '1' if args.script_read else '0'
    snapshot = json.loads((output / 'input-snapshot.json').read_text())
    snapshot['execution_options'] = {'mode': args.mode, 'script_read': args.script_read,
        'rate_retries': args.rate_retries, 'retry_delay': args.retry_delay,
        'series_budget_cap_usd': args.budget_usd, 'max_steps': args.max_steps, 'max_output': args.max_output}
    if entry_path:
        snapshot['entry_policy_digest'] = policy['policy_digest']
    save_private(output / 'input-snapshot.json', snapshot)
    print(json.dumps({'pdf_task_directory': str(output), 'paper_count': len(inventory(args.papers_dir)['papers']),
                      'question': args.question, 'mode': args.mode, 'script_read': args.script_read,
                      'cache_policy': args.cache_policy,
                      'budget_cap_usd': args.budget_usd, 'max_agent_steps': args.max_steps,
                      'max_output_tokens': args.max_output, 'model': 'deepseek-flash', 'reasoning_effort': 'off',
                      'user_file_writes_enabled': False,
                      'model_call_enabled': args.call_model}, ensure_ascii=False), flush=True)
    command = [sys.executable, str(ROOT / 'scripts/run-scenario.py'), '--scenario', str(output / 'scenario.json'),
               '--model', 'deepseek-flash', '--budget-usd', str(args.budget_usd),
               '--max-steps', str(args.max_steps), '--max-output', str(args.max_output), '--mode', args.mode]
    if entry_path:
        command.extend(['--entry-policy', str(args.entry_policy), '--entry-task', str(entry_path)])
    for flag, value in [('manifest', args.manifest), ('task', args.task),
                        ('embedding-endpoint', args.embedding_endpoint), ('embedding-model', args.embedding_model)]:
        if value is not None:
            command.extend(['--' + flag, str(value)])
    if args.call_model:
        command.append('--call-model')
    attempts, spent = [], 0.0
    for attempt in range(args.rate_retries + 1):
        remaining = args.budget_usd - spent
        if remaining <= 0:
            return 2
        command[command.index('--budget-usd') + 1] = str(remaining)
        if attempt and args.task:
            task = json.loads(args.task.read_text())
            task['session_id'] = 'pdf-retry-' + uuid4().hex
            fresh = output / ('motif-task-retry-' + str(attempt) + '.json')
            save_private(fresh, task)
            command[command.index('--task') + 1] = str(fresh)
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        print(result.stdout, end='', flush=True)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        if not args.call_model:
            return result.returncode
        summaries = []
        for line in result.stdout.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict) and 'output_dir' in value:
                    summaries.append(value)
            except ValueError:
                continue
        if not summaries:
            return result.returncode or 2
        summary = summaries[-1]
        run_directory = Path(summary['output_dir']).resolve()
        if not run_directory.is_relative_to(ROOT / '.local/runs'):
            raise ValueError('runner returned an unexpected output directory')
        delivery = collect_preview(run_directory, output)
        print(json.dumps({'pdf_delivery': delivery}, ensure_ascii=False), flush=True)
        cost = summary.get('budget_accounted_usd')
        valid_cost = isinstance(cost, (float, int)) and 0 <= cost <= remaining
        if valid_cost:
            spent += cost
        attempts.append({'run': str(run_directory), 'summary': summary, 'delivery': delivery})
        save_private(output / 'run-series.json', {'attempts': attempts, 'budget_cap_usd': args.budget_usd,
            'accounted_usd': spent, 'cost_complete': valid_cost, 'retry_scope': 'whole-run, no in-session resume'})
        if (attempt == args.rate_retries or not valid_cost or delivery['status'] != 'missing_preview'
                or not rate_limited(run_directory)):
            return result.returncode or (2 if delivery['status'] == 'missing_preview' else 0)
        print(json.dumps({'rate_limit_retry': attempt + 1, 'delay_seconds': args.retry_delay,
                          'remaining_budget_usd': args.budget_usd - spent}), flush=True)
        time.sleep(args.retry_delay)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
