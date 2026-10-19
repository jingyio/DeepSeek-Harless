#!/usr/bin/env python3
"""离线拆分真实请求费用与接管障碍；不执行脚本、不推断可兑现节省。"""
import argparse
import ast
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.script_motif_compiler import observe, extract
from src.adapters.script_negative_compiler import collect_negative
from src.adapters.deepseek_cost_gate import PEAK_USD_PER_MILLION, CACHE_HIT_PEAK_USD_PER_MILLION

spec = importlib.util.spec_from_file_location('script_cost', ROOT / 'scripts/analyze-script-motif-cost.py')
cost = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cost)


def parse_arguments(value):
    if isinstance(value, dict):
        return value, True
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed, True
        except ValueError:
            pass
    return {}, False


def components(ledger):
    """Reconstruct configured historical estimates, never current provider bills."""
    usage = ledger.get('response_usage') or {}
    model = ledger.get('model', 'deepseek-flash')
    if model not in PEAK_USD_PER_MILLION:
        return None
    hit, miss, out = (usage.get(k, 0) or 0 for k in
                      ('prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'completion_tokens'))
    if hit + miss != usage.get('prompt_tokens', 0):
        return None
    input_rate, output_rate = PEAK_USD_PER_MILLION[model]
    values = {'cache_hit_usd': hit * CACHE_HIT_PEAK_USD_PER_MILLION[model] / 1e6,
              'cache_miss_usd': miss * input_rate / 1e6,
              'output_usd': out * output_rate / 1e6}
    estimate = ledger.get('observed_peak_usd')
    # Ledger rows serialize observed_peak_usd to eight decimal places; task
    # summaries retain the full token-derived value. Preserve this difference.
    if estimate is None or abs(sum(values.values()) - estimate) > 5.1e-9:
        return None
    return values


def shell_exit_marker(block):
    """Historical text diagnostic only; never an execution/safety credential."""
    text = '\n'.join(c.get('text', '') for c in block.get('content', []) if c.get('type') == 'text')
    match = re.search(r'\[exit code:\s*(-?\d+)\]\s*$', text)
    return int(match.group(1)) if match else None


def source_features(command):
    # For diagnostic composition only. This extractor does NOT grant admission
    # to a Python fragment embedded in a larger shell command.
    sources = [m.group(2) for m in re.finditer(
        r"<<\s*['\"]?([A-Za-z_]\w*)['\"]?\s*\n(.*?)\n\1(?=\s|$)", command, re.S)]
    if not sources:
        try:
            sources = [extract(command)[1]]
        except (ValueError, OSError):
            pass
    values = {'python_fragments': 0, 'source_chars': 0, 'string_value_chars': 0,
              'long_string_value_chars': 0, 'skeletons': [], 'imports': [], 'writes': False}
    imports = set()
    for source in sources:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        values['python_fragments'] += 1
        values['source_chars'] += len(source)
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                values['string_value_chars'] += len(n.value)
                if len(n.value) >= 200:
                    values['long_string_value_chars'] += len(n.value)
            if isinstance(n, ast.Import):
                imports.update(a.name for a in n.names)
            if isinstance(n, ast.ImportFrom) and n.module:
                imports.add(n.module)
            if isinstance(n, ast.Call):
                name = n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id if isinstance(n.func, ast.Name) else ''
                if name in ('write', 'write_text', 'write_bytes', 'writelines', 'save', 'build', 'extractall'):
                    values['writes'] = True
        class Strip(ast.NodeTransformer):
            def visit_Constant(self, node):
                return ast.copy_location(ast.Constant('<' + type(node.value).__name__ + '>'), node)
        skeleton = ast.dump(Strip().visit(deepcopy(tree)), include_attributes=False)
        values['skeletons'].append(hashlib.sha256(skeleton.encode()).hexdigest())
    values['imports'] = sorted(imports)
    values['report_rendering'] = any(m.split('.')[0] in ('reportlab', 'fpdf') for m in imports)
    return values


def diagnose_call(block, workspace, library_ids):
    args, valid = parse_arguments(block.get('arguments', {}))
    result = {'tool': block['name'], 'arguments_valid': valid}
    if not valid:
        return {**result, 'blocker': 'invalid_tool_argument_json'}
    if block['name'] != 'bash':
        # A callable tool is not automatically a certified Script Motif.
        return {**result, 'blocker': 'scene_tool_not_script_operator',
                'payload_chars': len(json.dumps(args, ensure_ascii=False)),
                'argument_fields': sorted(args)}
    command = args.get('command', '')
    if not isinstance(command, str):
        return {**result, 'blocker': 'invalid_tool_argument_json'}
    result.update(command_chars=len(command), description=args.get('description', ''), **source_features(command))
    if command.strip().startswith('geneloop-resolve '):
        return {**result, 'blocker': 'paid_semantic_activation'}
    if re.search(r'(?:^|&&\s*)geneloop-cache\s', command):
        return {**result, 'blocker': 'paid_model_selected_cache'}
    if command.strip().startswith('geneloop-script '):
        return {**result, 'blocker': 'synthetic_execution_not_paid_selection'}
    try:
        # Final workspace is a diagnostic input, NOT an execution-boundary
        # snapshot. Saved code/file versions may differ from historical bytes.
        row = observe(command, args.get('description', ''), workspace, '', 'diagnostic', 'diagnostic')
        result.update(candidate_id=row['id'], input_contracts=row['inputs'],
                      requires_semantic_scalars=bool(row.get('argv_contract')),
                      requires_network=bool(row.get('network_policy')))
        blocker = 'frozen_program_requires_current_activation' if row['id'] in library_ids else 'candidate_not_in_frozen_library'
        return {**result, 'blocker': blocker, 'admission_scope': 'end_workspace_static_diagnostic_not_certification'}
    except (ValueError, SyntaxError, KeyError, TypeError, OSError, UnicodeError) as e:
        reason = str(e).split(':')[0]
        if reason == 'single_python_invocation_required':
            blocker = 'shell_form_not_mined'
        elif reason in ('attribute_not_admitted', 'name_not_admitted', 'read_mode_required'):
            blocker = 'static_effect_or_attribute_not_admitted'
        elif reason == 'import_not_admitted':
            blocker = 'import_not_admitted'
        elif reason in ('bounded_registered_inputs_required', 'unbound_path_literal', 'bounded_scalar_arguments_required'):
            blocker = 'unbound_or_task_literal_inputs'
        else:
            blocker = 'other_static_admission_failure'
        return {**result, 'blocker': blocker, 'compiler_rejection': reason}


def summarize(rows, key):
    groups = defaultdict(lambda: {'requests': 0, 'estimated_usd': 0, 'output_tokens': 0,
                                  'cache_hit_usd': 0, 'cache_miss_usd': 0, 'output_usd': 0})
    for r in rows:
        v = groups[r[key]]
        v['requests'] += 1
        v['estimated_usd'] += r['estimated_usd'] or 0
        v['output_tokens'] += r['completion_tokens']
        for name, amount in (r.get('cost_components') or {}).items():
            v[name] += amount
    return dict(groups)


def analyze(task, library, negative_library=None):
    task = Path(task)
    breakdown = cost.analyze(task)
    events = cost.read_rows(task / 'events.jsonl')
    ledger = cost.read_rows(task / 'ledger.jsonl')
    effective = json.loads((task / 'effective-config.json').read_text())
    library_ids = {p['id'] for p in library['programs']}
    messages = [e for e in events if e['type'] == 'assistant/message' and e['data'].get('usage')]
    assigned = set()
    audit = cost.read_rows(task / 'script-motif-audit.jsonl')
    calls = {}
    shell_failures = []
    for event in events:
        data = event.get('data', {})
        if event['type'] == 'tool/call':
            calls[data['callId']] = data
        if event['type'] == 'tool/result':
            for block in data.get('message', {}).get('content', []):
                call = calls.get(block.get('toolCallId'))
                if call and call['name'] == 'bash':
                    status = shell_exit_marker(block)
                    if status is not None and status != 0:
                        shell_failures.append({'call_id': block['toolCallId'], 'time': event['time'],
                                               'textual_exit_code': status, 'native_is_error': block.get('isError', False)})
    finishes = [datetime.fromisoformat(a['at']).timestamp()*1000 for a in audit
                if a['kind'] == 'script_frontier_completed']
    by_id = {r['request_id']: r for r in ledger}
    records = []
    skeletons = Counter()
    for r in breakdown['requests']:
        record = dict(r)
        record['cost_components'] = components(by_id[r['request_id']])
        possible = [(abs(e['time']-r['completed_epoch_ms']), i, e) for i, e in enumerate(messages) if i not in assigned]
        match = min(possible, key=lambda p: p[0]) if possible else None
        call_details = []
        if match and match[0] <= 500:
            _, i, event = match
            assigned.add(i)
            for block in event['data']['message'].get('content', []):
                if block.get('type') == 'tool-call':
                    detail = diagnose_call(block, effective['workspace'], library_ids)
                    detail['call_id'] = block.get('callId', block.get('id'))
                    call_details.append(detail)
                    skeletons.update(detail.get('skeletons', []))
            blockers = {c['blocker'] for c in call_details}
            blocker = next(iter(blockers)) if len(blockers) == 1 else 'mixed_request_requires_full_boundary' if blockers else 'semantic_text_without_structural_operator'
        else:
            blocker = 'auxiliary_model_outside_script_interceptor' if r['category'] == 'web_search_internal_model' else 'unassigned_provider_request'
        record.update(blocker=blocker, calls=call_details,
                      after_frontier_completed=bool(finishes and r['completed_epoch_ms'] > min(finishes)))
        records.append(record)
    negative_rows = collect_negative(task) if negative_library else []
    coverage = Counter()
    for row in negative_rows:
        if not row['code']:
            continue
        exact = [rule for rule in negative_library['rules'] if rule['tool'] == row['tool'] and
                 rule['failure_code'] == row['code'] and rule['tools_sha256'] == row['tools_sha256'] and
                 all(p in row['false_paths'] for p in rule['failure_flags'])]
        coverage['frozen_rule_compatible' if exact else 'no_frozen_rule'] += 1
        coverage['error:' + row['code']] += 1
    after_shell = set()
    for failure in shell_failures:
        subsequent = [r for r in records if r['calls'] and r['completed_epoch_ms'] > failure['time']]
        if subsequent:
            after_shell.add(min(subsequent, key=lambda r: r['completed_epoch_ms'])['request_id'])
    reconstructed = sum(sum(r['cost_components'].values()) for r in records if r['cost_components'])
    soft_errors = breakdown['structured_validation_failures']
    first_error = min((r['time'] for r in soft_errors), default=None)
    return {'task_id': task.name, 'scope': 'historical_real_trace_diagnostic_not_counterfactual_savings',
            'library_digest': library['digest'], 'accounting': {
                'requests': len(records), 'unknown_usage_requests': breakdown['requests_without_usage'],
                'estimated_usd': sum(r['estimated_usd'] or 0 for r in records),
                'token_reconstructed_usd': reconstructed,
                'rounded_ledger_minus_reconstruction_usd': sum(r['estimated_usd'] or 0 for r in records)-reconstructed,
                'cost_components_verified_requests': sum(r['cost_components'] is not None for r in records)},
            'categories': summarize(records, 'category'), 'blockers': summarize(records, 'blocker'),
            'after_frontier_completed': summarize([r for r in records if r['after_frontier_completed']], 'category'),
            'after_first_structured_failure': summarize([r for r in records if first_error is not None and r['completed_epoch_ms'] > first_error], 'category'),
            'negative_failure_compatibility': dict(coverage),
            'shell_textual_nonzero_exits': shell_failures,
            'first_paid_dispatch_after_shell_failure': summarize([r for r in records if r['request_id'] in after_shell], 'category'),
            'repeated_ast_skeletons': {k: n for k, n in skeletons.items() if n > 1},
            'limitations': ['Visible-action costs include semantic judgment and are not fully replaceable.',
                           'Static mining reads final workspace, not historical file-boundary snapshots.',
                           'AST skeleton equality ignores literal values, not semantic or execution equivalence.',
                           'Negative rule compatibility is not verified online eligibility or a skipped request.'],
            'requests': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--negative-library', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.task, json.loads(args.library.read_text()),
                     json.loads(args.negative_library.read_text()) if args.negative_library else None)
    with args.output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    args.output.chmod(0o600)
    print(json.dumps(result['accounting']))
