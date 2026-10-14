"""Frozen real-model plan comparison; orchestrates public runners, not an Agent loop."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
from uuid import uuid4
from mcp.server.mcpserver.exceptions import ToolError

from pdf_dependencies import private_file
from pdf_evidence_tools import EvidenceScene, PREFIX
from pdf_tools import ROOT, digest, inventory, save_private

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import importlib.util


def module(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def read(path):
    return json.loads(private_file(path).read_text())


def order(repeats, include_code_mode=False):
    if type(repeats) is not int or not 1 <= repeats <= 12:
        raise ValueError('repeats must be 1–12; three rounds balance each order position')
    arms = ['baseline', 'codemode', 'script', 'motif'] if include_code_mode else ['baseline', 'script', 'motif']
    return [{'round': n + 1, 'position': k + 1, 'arm': arm}
            for n in range(repeats) for k, arm in enumerate(arms[n % len(arms):] + arms[:n % len(arms)])]


def code_version():
    return digest({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(HERE.iterdir()) if p.suffix in ('.py', '.json', '.md', '.ts')})


def approved_origin(run, directory, cache, delivery):
    """The plan must come from native successful paid events, not a typed approval flag."""
    from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance
    from src.adapters.tool_contract_loader import parse_tool_contracts
    run = Path(run).resolve()
    if not run.is_relative_to(ROOT / '.local/runs'):
        raise ValueError('plan origin must be a private shared-run directory')
    snapshot = read(run / 'evidence-input-snapshot.json')
    metrics = read(run / 'metrics.json')
    packet, receipt = read(run / 'evidence-packet.json'), read(run / 'evidence-packet-receipt.json')
    frozen = {'schema_version': 1, 'question': packet['question'], 'sources': inventory(directory)}
    if snapshot['task'] != frozen:
        raise ValueError('current corpus/task differs from plan origin')
    scene = EvidenceScene(directory, cache, frozen, delivery=delivery)
    scene.validate_packet(packet)  # Current version, exact source replay before approval normalization.
    opts = snapshot['execution_options']
    if (opts.get('model_call_enabled') is not True or opts.get('script_chain') is not False
            or metrics.get('finish_reason') != 'completed' or metrics.get('upstream_requests', 0) < 1
            or packet['plan']['allow_deterministic_continuation'] is not True
            or receipt.get('packet') != packet or receipt.get('artifact_sha256') != digest(packet)):
        raise ValueError('origin must be a completed native real-model approved packet')
    events_path = private_file(run / 'agent-events.jsonl')
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    contracts = parse_tool_contracts(json.loads((HERE / 'pdf-evidence-contracts.json').read_text()))
    trace = extract_dsh_trace(events, contracts, trace_id=run.name,
                             provenance_by_call_id=infer_dsh_provenance(events, contracts))
    matching_plan = any(r.name == PREFIX + 'register_reading_plan' and r.observation
                        and r.observation.get('status') == 'plan_approved'
                        and scene._plan(r.arguments['plan']) == packet['plan']
                        and r.observation.get('plan_sha256') == digest(packet['plan']) for r in trace.records)
    matching_packet = any(r.name == PREFIX + 'build_evidence_packet' and r.observation == receipt
                          for r in trace.records)
    if not matching_plan or not matching_packet:
        raise ValueError('native events do not witness the approved plan and exact packet receipt')
    return packet, snapshot, metrics, hashlib.sha256(events_path.read_bytes()).hexdigest()


def json_lines(stdout):
    values = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                values.append(value)
        except ValueError:
            pass
    return values


def summarize_attempt(stdout, exit_code, expected_packet, expected_prompt):
    values = json_lines(stdout)
    summaries = [v for v in values if 'output_dir' in v]
    row = {'attempts': summaries, 'exit_code': exit_code, 'cost_complete': False, 'accepted': False}
    if len(summaries) != 1:
        row['failure'] = 'missing_or_ambiguous_runner_summary'
        return row
    summary = summaries[0]
    cost = summary.get('budget_accounted_usd')
    if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
        row['failure'] = 'missing_cost_accounting'
        return row
    row.update(cost_complete=True, accounted_usd=cost)
    try:
        run = Path(summary['output_dir']).resolve()
        if not run.is_relative_to(ROOT / '.local/runs'):
            raise ValueError('unexpected shared runner directory')
        packet = read(run / 'evidence-packet.json')
        snapshot = read(run / 'evidence-input-snapshot.json')
        metadata = next(v for v in values if 'task_directory' in v)
        task_dir = Path(metadata['task_directory'])
        actual_prompt = hashlib.sha256(private_file(task_dir / 'prompt.md').read_bytes()).hexdigest()
        series = read(task_dir / 'run-series.json')
        if (exit_code or summary.get('finish_reason') != 'completed' or packet != expected_packet
                or snapshot.get('frozen_plan') != expected_packet['plan'] or actual_prompt != expected_prompt
                or series['delivery']['status'] != 'packet_ready'):
            raise ValueError('delivery, frozen plan, prompt or packet equality failed')
        row.update(accepted=True, packet_sha256=digest(packet), prompt_sha256=actual_prompt,
                   embedding_requests=series['embedding_requests'], task_directory=str(task_dir))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        row['failure'] = type(exc).__name__ + ': ' + str(exc)
    return row


def aggregate(rows):
    result = {}
    for arm in ('baseline', 'codemode', 'script', 'motif'):
        selected = [r for r in rows if r['arm'] == arm and r['accepted']]
        result[arm] = {'accepted': len(selected)}
        for field in ('budget_accounted_usd', 'elapsed_seconds', 'model_requests', 'inputTokens',
                      'cacheReadTokens', 'outputTokens', 'model_requests_skipped_verified'):
            values = [r['attempts'][0][field] for r in selected]
            if values:
                result[arm][field] = {'mean': statistics.mean(values), 'median': statistics.median(values),
                                      'min': min(values), 'max': max(values)}
    return result


def compare(args):
    if not 0 < args.budget_usd <= 100 or not 1 <= args.max_output <= 8000 or not 1 <= args.max_steps <= 100:
        raise ValueError('invalid total budget/step/output limits')
    if args.training_cost_usd is not None and (not math.isfinite(args.training_cost_usd)
                                               or args.training_cost_usd < 0 or not args.training_cost_source):
        raise ValueError('training cost needs a finite nonnegative value and explicit source')
    schedule = order(args.repeats, getattr(args, 'include_code_mode', False))
    output = ROOT / '.local/literature-notes' / ('frozen-evidence-20261010-' + uuid4().hex[:8])
    output.mkdir(mode=0o700, parents=True)
    runner = module('run-evidence.py', 'frozen_evidence_runner')
    start = time.monotonic()
    packet, origin_snapshot, origin_metrics, event_hash = approved_origin(
        args.plan_run, args.papers_dir, ROOT / '.local/literature-notes/pdf-cache', output / 'origin-replay')
    frozen_plan = output / 'frozen-plan.json'
    save_private(frozen_plan, packet['plan'])
    manifest = private_file(args.manifest)
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    manifest_body = read(manifest)
    if manifest_body['schema_version'] != 2 or not any(a.get('continuation_policy_digest')
                                                     for a in manifest_body['artifacts']):
        raise ValueError('approved-plan comparison requires a v2 continuation library')
    preview, _env = runner.prepare_task(args.papers_dir, packet['question'], frozen_plan=packet['plan'])
    snapshot = read(preview / 'input-snapshot.json')
    prompt_hash = hashlib.sha256((preview / 'prompt.md').read_bytes()).hexdigest()
    plan = {'experiment_id': output.name, 'kind': 'fixed_decision_component_comparison',
            'plan_origin_run': Path(args.plan_run).name, 'origin_native_events_sha256': event_hash,
            'origin_selection_and_delivery_usd': origin_metrics['budget_accounted_usd'],
            'origin_cost_scope': 'prior run also delivered the packet; excluded equally from every timed arm',
            'training_proxy_usd_separate': args.training_cost_usd,
            'training_cost_source': args.training_cost_source,
            'frozen_plan_sha256': digest(packet['plan']), 'expected_packet_sha256': digest(packet),
            'question': packet['question'], 'input_snapshot': snapshot,
            'prompt_sha256': prompt_hash, 'scene_code_sha256': code_version(),
            'manifest_digest': manifest_body['manifest_digest'], 'manifest_file_sha256': manifest_sha,
            'schedule': schedule, 'budget_cap_usd': args.budget_usd, 'model': 'deepseek-flash',
            'reasoning_effort': 'off', 'compression': False, 'cache_policy': 'reuse',
            'provider_prefix_cache': 'uncontrolled; rotating order, record observed hits/misses',
            'prewarm_seconds_excluded': time.monotonic() - start,
            'max_output': args.max_output, 'max_steps': args.max_steps, 'model_call_enabled': args.call_model,
            'independent_corpus_count': 1, 'independent_decision_count': 1,
            'research_quality': 'unreviewed', 'expert_blind_review': False,
            'ordinary_script': 'same MCP checks composed by hand; separate from actual Code Mode',
            'code_mode_baseline': 'actual Harness run_code/SDK/sub-dispatch, upstream WorkerThreadCodeRuntime isolated in Docker' if getattr(args, 'include_code_mode', False) else 'not included',
            'code_image': __import__('os').environ.get('SSS_CODE_IMAGE') if getattr(args, 'include_code_mode', False) else None}
    save_private(output / 'experiment-plan.json', plan)
    print(json.dumps({'output': str(output), 'planned_runs': len(schedule), 'paid_enabled': args.call_model,
                      'budget_cap_usd': args.budget_usd, 'frozen_plan_sha256': digest(packet['plan'])}), flush=True)
    if not args.call_model:
        return {'output': str(output), 'status': 'preview', 'paid_requests': 0}
    rows, spent, complete, failure = [], 0.0, True, None
    for item in schedule:
        if (inventory(args.papers_dir) != origin_snapshot['task']['sources']
                or code_version() != plan['scene_code_sha256']
                or hashlib.sha256(manifest.read_bytes()).hexdigest() != manifest_sha
                or digest(read(frozen_plan)) != plan['frozen_plan_sha256']):
            failure = 'input_code_or_manifest_drift'
            break
        cap = args.budget_usd - spent
        if cap < 0.002:
            failure = 'remaining_total_budget_insufficient'
            break
        command = [sys.executable, str(HERE / 'run-evidence.py'), '--papers-dir', str(args.papers_dir),
                   '--question', packet['question'], '--frozen-plan', str(frozen_plan), '--cache-policy', 'reuse',
                   '--call-model', '--budget-usd', str(cap), '--max-output', str(args.max_output),
                   '--max-steps', str(args.max_steps)]
        if item['arm'] == 'codemode':
            command.extend(['--tool-presentation', 'ptc'])
        if item['arm'] == 'script':
            command.append('--script-chain')
        elif item['arm'] == 'motif':
            command += ['--mode', 'execute', '--manifest', str(manifest)]
        started = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        launcher_seconds = time.monotonic() - started
        prefix = f"{item['round']}-{item['arm']}"
        for suffix, content in (('stdout', result.stdout), ('stderr', result.stderr)):
            path = output / (prefix + '-' + suffix + '.txt')
            path.write_text(content, encoding='utf-8')
            path.chmod(0o600)
        row = {**item, **summarize_attempt(result.stdout, result.returncode, packet, prompt_hash),
               'launcher_seconds': launcher_seconds}
        if row['cost_complete']:
            spent += row['accounted_usd']
            if row['accounted_usd'] > cap + 1e-12:
                row.update(accepted=False, failure='budget_accounting_exceeds_remaining_cap')
        else:
            complete = False
        if item['arm'] == 'motif' and row['accepted']:
            if row['attempts'][0]['model_requests_skipped_verified'] != 2 or row['embedding_requests'] != 0:
                row.update(accepted=False, failure='expected_verified_continuation_not_observed')
        rows.append(row)
        report = {'plan': plan, 'rows': rows, 'accounted_usd': spent, 'cost_complete': complete,
                  'status': 'running', 'aggregate': aggregate(rows), 'scientific_quality_established': False,
                  'manual_and_development_costs': 'not fully measured'}
        save_private(output / 'comparison.json', report)
        print(json.dumps({'round': item['round'], 'arm': item['arm'], 'accepted': row['accepted'],
                          'accounted_usd': row.get('accounted_usd'),
                          'model_requests': row['attempts'][0].get('model_requests') if row['attempts'] else None}), flush=True)
        if not row['accepted']:
            failure = row.get('failure', 'failed_arm')
            break  # Preserve failures and costs; no unregistered whole-run retry.
    report = {'plan': plan, 'rows': rows, 'accounted_usd': spent, 'cost_complete': complete,
              'status': 'passed' if len(rows) == len(schedule) and not failure else 'stopped',
              'failure': failure, 'aggregate': aggregate(rows), 'scientific_quality_established': False,
              'manual_and_development_costs': 'not fully measured'}
    save_private(output / 'comparison.json', report)
    return {'output': str(output), 'status': report['status'], 'runs_completed': len(rows),
            'accounted_usd': spent, 'cost_complete': complete, 'failure': failure}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--plan-run', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--include-code-mode', action='store_true', help='add actual Harness PTC strong baseline; four rounds balance four arms')
    parser.add_argument('--budget-usd', type=float, default=0.25)
    parser.add_argument('--max-output', type=int, default=3000)
    parser.add_argument('--max-steps', type=int, default=24)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--training-cost-usd', type=float, help='historical learning cost, kept separate from this budget')
    parser.add_argument('--training-cost-source', help='experiment ID supporting the supplied historical cost')
    args = parser.parse_args()
    try:
        report = compare(args)
    except (ValueError, OSError, KeyError, ToolError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] in ('preview', 'passed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
