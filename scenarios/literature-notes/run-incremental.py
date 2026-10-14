"""Run changed-only PDF work through the original Harness, Motif and budget entry."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
from pdf_tools import ROOT, digest, inventory, save_private
from pdf_dependencies import private_file
from pdf_incremental_tools import IncrementalScene

HERE = Path(__file__).resolve().parent
TOOL = 'mcp__literature_pdf__submit_incremental_update'


def load_entry(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def collect_incremental(model_run, scene):
    sys.path.insert(0, str(ROOT))
    from src.adapters.dsh_trajectory import extract_dsh_trace
    from src.adapters.tool_contract_loader import parse_tool_contracts
    contracts = parse_tool_contracts({TOOL: {'required_params': ['update'], 'read_only': True, 'replay_stable': False}})
    events = [json.loads(line) for line in (Path(model_run) / 'agent-events.jsonl').read_text().splitlines()]
    trace = extract_dsh_trace(events, contracts, trace_id=Path(model_run).name)
    receipts = [r.observation for r in trace.records if r.name == TOOL and r.observation]
    if not receipts: return None
    receipt = receipts[-1]
    artifact = private_file(receipt['artifact'])
    if artifact != scene.output / 'incremental-evidence.json':
        raise ValueError('unexpected incremental receipt location')
    payload = json.loads(artifact.read_text())
    if (digest(payload) != receipt['artifact_sha256'] or receipt['task_sha256'] != digest(scene.task)
            or receipt['plan_sha256'] != digest(scene._plan())):
        raise ValueError('incremental receipt or dependencies changed')
    for c in payload['citation_checks']:
        pin = scene.pin_pdf_context(c['paper_id'], str(c['page']), c['start'], c['end'] - c['start'])
        if pin['source_id'] != c['source_id'] or pin['version_sha256'] != c['version_sha256']:
            raise ValueError('published citation changed')
        scene.read_pinned_pdf_context(pin['source_id'])
    scene.read_update_plan()
    checked = scene.publish(payload['incremental_audit']['submitted_update'], persist=False)
    if checked != payload:
        raise ValueError('incremental merge or audit differs')
    return receipt


def save_notes(scene):
    payload = json.loads((scene.output / 'incremental-evidence.json').read_text())
    notes = scene.output / 'incremental-research-notes.md'
    notes.write_text(payload['markdown']); notes.chmod(0o600)
    return str(notes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--question')
    parser.add_argument('--revoked-claims', type=Path)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--budget-usd', type=float, default=100)
    parser.add_argument('--max-steps', type=int, default=32)
    parser.add_argument('--max-output', type=int, default=6000)
    parser.add_argument('--mode', choices=['baseline', 'shadow', 'execute'], default='baseline')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--embedding-endpoint')
    parser.add_argument('--embedding-model')
    parser.add_argument('--script-read', action='store_true')
    parser.add_argument('--entry-policy', type=Path)
    args = parser.parse_args(argv)
    if not 0 < args.budget_usd <= 100 or not 1 <= args.max_steps <= 100 or not 1 <= args.max_output <= 8000:
        parser.error('invalid budget/step/output limits')
    if args.mode != 'baseline' and not all((args.manifest, args.embedding_endpoint, args.embedding_model)):
        parser.error('Motif execution requires a certified manifest and local embedding configuration')
    if args.mode == 'baseline' and any((args.manifest, args.embedding_endpoint, args.embedding_model)):
        parser.error('Motif parameters require shadow or execute mode')
    if args.script_read and args.mode != 'baseline':
        parser.error('script composition is a separate baseline')
    if args.entry_policy and (args.mode != 'baseline' or args.script_read):
        parser.error('incremental entry policy requires native baseline without legacy Motif or script composition')
    started = time.monotonic()
    envelope_path = private_file(args.dependencies)
    graph = json.loads(envelope_path.read_text())['graph']
    question = args.question if args.question is not None else graph['task']['question']
    task = {'schema_version': 1, 'question': question, 'sources': inventory(args.papers_dir)}
    output = ROOT / '.local/literature-notes/incremental-runs' / uuid4().hex
    revoked_path = private_file(args.revoked_claims) if args.revoked_claims else output / 'revoked-claims.json'
    if not args.revoked_claims: save_private(revoked_path, {'revoked_claim_ids': []})
    frozen_envelope = output / 'dependencies.json'
    save_private(frozen_envelope, json.loads(envelope_path.read_text()))
    scene = IncrementalScene(frozen_envelope, args.papers_dir, task, output, revoked_path=revoked_path)
    plan = scene.read_update_plan()
    entry_policy = None
    if args.entry_policy:
        from incremental_entry import private_policy
        entry_policy = private_policy(args.entry_policy)
    save_private(output / 'plan.json', plan)
    save_private(output / 'task.json', task)
    runtime = load_entry('incremental_runtime_snapshot', 'run-pdf.py')
    snapshot = {'task': task, 'task_sha256': digest(task), 'graph_sha256': scene.envelope['graph_sha256'],
                'plan_sha256': plan['plan_sha256'], 'runtime': runtime.runtime_snapshot(),
                'mode': args.mode, 'script_read': args.script_read,
                'manifest_sha256': digest(json.loads(args.manifest.read_text())) if args.manifest else None,
                'embedding_endpoint': args.embedding_endpoint, 'embedding_model': args.embedding_model,
                'budget_cap_usd': args.budget_usd, 'max_steps': args.max_steps, 'max_output': args.max_output,
                'learned_motif': False, 'cloud_enabled': args.call_model}
    snapshot['entry_policy_digest'] = entry_policy['policy_digest'] if entry_policy else None
    save_private(output / 'input-snapshot.json', snapshot)
    print(json.dumps({'incremental_directory': str(output), 'retained_field_count': len(plan['retained_claim_ids']),
                      'fields_to_review': sum(len(w['fields_to_review']) for w in plan['work']),
                      'budget_cap_usd': args.budget_usd, 'model_call_enabled': args.call_model,
                      'user_file_writes_enabled': False, 'mode': args.mode}, ensure_ascii=False), flush=True)
    if not plan['work'] and not plan['synthesis_requires_review']:
        if not args.call_model: return 0
        receipt = scene.publish({'papers': [], 'synthesis_hypothesis': ''}, automatic=True)
        outcome = {'status': receipt['status'], 'receipt': receipt, 'notes': save_notes(scene),
                   'model_requests': 0, 'budget_accounted_usd': 0, 'learned_motif': False,
                   'elapsed_seconds': round(time.monotonic() - started, 3),
                   'scope': 'deterministic reuse of previously source-checked artifacts'}
        save_private(output / 'outcome.json', outcome); print(json.dumps(outcome, ensure_ascii=False))
        return 0
    scenario = json.loads((HERE / 'pdf-incremental-scenario.json').read_text())
    prompt = (HERE / 'pdf-incremental-task.md').read_text() + '\n' + (HERE / 'research-checklist.md').read_text()
    prompt_path = output / 'prompt.md'; prompt_path.write_text(prompt); prompt_path.chmod(0o600)
    scenario['prompt'] = str(prompt_path); save_private(output / 'scenario.json', scenario)
    env = os.environ.copy()
    env.update(SSS_PDF_ROOT=str(scene.root), SSS_PDF_TASK_FILE=str(output / 'task.json'),
               SSS_PDF_DEPENDENCIES=str(frozen_envelope), SSS_PDF_INCREMENTAL_OUTPUT=str(output),
               SSS_PDF_REVOKED=str(revoked_path),
               SSS_PDF_SCRIPT_READ='1' if args.script_read else '0')
    command = [sys.executable, str(ROOT / 'scripts/run-scenario.py'), '--scenario', str(output / 'scenario.json'),
               '--model', 'deepseek-flash', '--budget-usd', str(args.budget_usd), '--max-steps', str(args.max_steps),
               '--max-output', str(args.max_output), '--mode', args.mode]
    if entry_policy and plan['work']:
        from incremental_entry import entry_task
        frozen_entry = output / 'entry-task.json'
        save_private(frozen_entry, {**entry_task(scene, output.name), 'session_id': 'incremental-' + uuid4().hex})
        command.extend(['--entry-policy', str(args.entry_policy), '--entry-task', str(frozen_entry)])
    if args.mode != 'baseline':
        versions = [scene.prepare_pdf(pid)['document_version_sha256'] for pid in scene.rows]
        motif_task = output / 'motif-task.json'
        save_private(motif_task, {'schema_version': 1, 'task_id': output.name, 'session_id': 'incremental-' + uuid4().hex,
                     'intent': question, 'input_version': digest(task), 'bindings': {},
                     'source_versions': {'mcp__literature_pdf__pin_pdf_context': versions,
                                         'mcp__literature_pdf__read_pinned_pdf_context': versions}})
        command.extend(['--manifest', str(args.manifest), '--task', str(motif_task),
                        '--embedding-endpoint', args.embedding_endpoint, '--embedding-model', args.embedding_model])
    if args.call_model:
        key = load_entry('incremental_key_loader', 'run-live.py')
        env['DEEPSEEK_API_KEY'] = key.load_key(key.KEY_FILE, env)
        command.append('--call-model')
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    print(result.stdout, end='', flush=True)
    if result.stderr: print(result.stderr, file=sys.stderr, end='')
    if not args.call_model: return result.returncode
    summaries = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict) and 'output_dir' in row: summaries.append(row)
        except ValueError: pass
    receipt, summary = None, summaries[-1] if summaries else None
    if summary:
        model_run = Path(summary['output_dir']).resolve()
        if not model_run.is_relative_to(ROOT / '.local/runs'):
            raise ValueError('unexpected runner directory')
        receipt = collect_incremental(model_run, scene)
    outcome = {'status': receipt['status'] if receipt else 'missing_update', 'receipt': receipt,
               'run': summary, 'elapsed_seconds': round(time.monotonic() - started, 3),
               'notes': save_notes(scene) if receipt else None, 'input': snapshot}
    save_private(output / 'outcome.json', outcome)
    print(json.dumps({'incremental_directory': str(output), 'status': outcome['status'],
                      'receipt': receipt, 'notes': outcome['notes'], 'elapsed_seconds': outcome['elapsed_seconds']},
                     ensure_ascii=False))
    return result.returncode or (0 if receipt else 2)


if __name__ == '__main__':
    raise SystemExit(main())
