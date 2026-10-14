"""Independent revision facts from witnessed JSON versions, never proposed code.

This is an acceptance oracle and trace-data adapter, not the production tool.
Failed normal revisions can teach a tool; they cannot certify a Motif edge.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re

from .trace_tool_evidence import bounded_read, digest
from .trace_rsi_motif_compiler import (_actions, _root_events, load_provider_tools,
    _registered_hashes, file_sha256, PREFIX)


def rebind_generated_input(expression, aliases):
    """Specialize entry-input field bindings; literal data and locals stay intact."""
    if not isinstance(expression, list) or not expression: raise ValueError('expression_array_required')
    if expression[0] == 'lit': return copy.deepcopy(expression)
    if expression[0] == 'let' and expression[1] == 'input':
        raise ValueError('shadowed_entry_input_cannot_be_rebound')
    if expression[0] == 'get' and expression[1] == ['var', 'input'] and expression[2][0] == 'lit':
        key=expression[2][1]
        if key in aliases: return ['get', ['var', 'input'], ['lit', aliases[key]]]
    if expression[0] == 'object':
        return ['object', {key: rebind_generated_input(value, aliases) for key,value in expression[1].items()}]
    return [copy.deepcopy(value) if not isinstance(value, list) else rebind_generated_input(value, aliases)
            for value in expression]


def project_generated_outputs(candidate, outputs, inputs, *, name, description):
    """Keep verbatim branches and let bindings of a model-generated expression.

    This deliberately supports only independently evaluable object branches.
    It never repairs an algorithm or promotes the rejected parent candidate.
    """
    program = candidate['program']; wrappers = []
    while isinstance(program, list) and len(program) == 4 and program[0] == 'let':
        wrappers.append(copy.deepcopy(program[:3])); program = program[3]
    if not isinstance(program, list) or len(program) != 2 or program[0] != 'object' or not isinstance(program[1], dict):
        raise ValueError('independent_object_branches_required')
    if not outputs or len(outputs) != len(set(outputs)) or not set(outputs) <= set(program[1]):
        raise ValueError('existing_unique_output_branches_required')
    if not inputs or len(inputs) != len(set(inputs)) or not set(inputs) <= set(candidate['input_schema']['properties']):
        raise ValueError('existing_unique_input_fields_required')
    selected = {key: copy.deepcopy(program[1][key]) for key in outputs}
    def dependencies(expr):
        if not isinstance(expr, list) or not expr: raise ValueError('expression_array_required')
        if expr[0] == 'lit': return
        if expr[0] == 'var' and expr[1] == 'input':
            raise ValueError('whole_input_dependency_cannot_be_projected')
        if expr[0] == 'get' and expr[1] == ['var', 'input']:
            if expr[2][0] != 'lit' or expr[2][1] not in inputs:
                raise ValueError('unselected_input_dependency')
            return
        if expr[0] == 'object':
            for child in expr[1].values(): dependencies(child)
            return
        for child in expr[1:]:
            if isinstance(child, list): dependencies(child)
    for wrapper in wrappers: dependencies(wrapper[2])
    for expr in selected.values(): dependencies(expr)
    input_schema = copy.deepcopy(candidate['input_schema'])
    input_schema['properties'] = {key: input_schema['properties'][key] for key in inputs}
    input_schema['required'] = [key for key in input_schema.get('required', []) if key in inputs]
    output_schema = copy.deepcopy(candidate['output_schema'])
    output_schema['properties'] = {key: output_schema['properties'][key] for key in outputs}
    output_schema['required'] = [key for key in output_schema.get('required', []) if key in outputs]
    projected = ['object', selected]
    for wrapper in reversed(wrappers): projected = [*wrapper, projected]
    return {**copy.deepcopy(candidate), 'name': name, 'description': description,
            'input_schema': input_schema, 'output_schema': output_schema, 'program': projected}


def compose_generated_candidates(candidates, *, name, description):
    """Compose pure programs; shared inputs need identical schemas, outputs disjoint.

    Schema and AST leaves are copied, never replaced with domain computations.
    Fresh wrapper variables avoid capture of any original program identifier.
    """
    schemas = {kind: {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
               for kind in ('input_schema', 'output_schema')}
    expressions, bindings = [], []
    occupied = set()
    def strings(value):
        if isinstance(value, str): occupied.add(value)
        elif isinstance(value, list):
            for child in value: strings(child)
        elif isinstance(value, dict):
            for key, child in value.items(): occupied.add(key); strings(child)
    for candidate in candidates: strings(candidate['program'])
    for index, candidate in enumerate(candidates):
        for kind, schema in schemas.items():
            source = candidate[kind]
            if source['type'] != 'object' or source['additionalProperties'] is not False:
                raise ValueError('closed_object_component_schema_required')
            overlap = set(schema['properties']) & set(source['properties'])
            if overlap and (kind != 'input_schema' or any(
                    schema['properties'][key] != source['properties'][key] or
                    (key in schema['required']) != (key in source.get('required', [])) for key in overlap)):
                raise ValueError('component_field_collision')
            schema['properties'].update(copy.deepcopy(source['properties']))
            schema['required'] = list(dict.fromkeys([*schema['required'], *source.get('required', [])]))
        variable = f'rsi_compiled_part_{index}'
        while variable in occupied: variable += '_'
        occupied.add(variable); bindings.append((variable, copy.deepcopy(candidate['program'])))
        expressions.extend((key, ['get', ['var', variable], ['lit', key]])
                           for key in candidate['output_schema']['properties'])
    program = ['object', dict(expressions)]
    for variable, expression in reversed(bindings): program = ['let', variable, expression, program]
    return {'schema_version': 1, 'name': name, 'description': description, **schemas, 'program': program}


def strict_revision_pointer(value, path):
    if not isinstance(path, str) or (path and not path.startswith('/')):
        raise ValueError('invalid_revision_pointer')
    for raw in path.split('/')[1:] if path else []:
        if re.search(r'~(?![01])', raw):
            raise ValueError('invalid_pointer_escape')
        key = raw.replace('~1', '/').replace('~0', '~')
        if key in ('__proto__', 'prototype', 'constructor'):
            raise ValueError('unsafe_revision_pointer')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', key) or int(key) >= len(value):
                raise ValueError('invalid_revision_array_index')
            value = value[int(key)]
        elif isinstance(value, dict) and key in value:
            value = value[key]
        else:
            raise ValueError('missing_revision_pointer')
    return copy.deepcopy(value)


def revision_facts(before, after, catalog, *, allowlist=('arxiv_id',),
                   placeholder_status='待进一步核验'):
    def rows(report):
        values = report.get('references') if isinstance(report, dict) else None
        if not isinstance(values, list) or any(not isinstance(r, dict) or
                not isinstance(r.get('key'), str) or not isinstance(r.get('arxiv_id'), str) for r in values):
            raise ValueError('well_formed_revision_rows_required')
        return values
    a, b = rows(before), rows(after)
    expected = [(r['key'], ident) for r in catalog['cited_records'] for ident in r['arxiv_ids']]
    if len(expected) != len(set(k for k, _ in expected)):
        raise ValueError('one_catalog_identifier_per_key_required')
    ids = dict(expected)
    ca, cb = Counter(r['key'] for r in a), Counter(r['key'] for r in b)
    before_by_key = {k: [r for r in a if r['key'] == k] for k in ca}
    without = lambda r: {k: v for k, v in r.items() if k not in allowlist}
    changed = sorted({r['key'] for r in b if r['key'] in ca and
        not any(without(r) == without(old) for old in before_by_key[r['key']])})
    added = [r for r in b if r['key'] not in ca]
    missing, extra = sorted(set(ids)-set(cb)), sorted(set(cb)-set(ids))
    mismatches = sorted({r['key'] for r in b if r['key'] in ids and r['arxiv_id'] != ids[r['key']]})
    top = lambda r: {k: v for k, v in r.items() if k != 'references'}
    conflicts = sorted(k for k, values in before_by_key.items() if len({digest(without(r)) for r in values}) > 1)
    # Recursive pointer differences are diagnostic evidence. Array order and
    # missing-vs-null are significant. Never silently select a duplicate version.
    diffs = []
    def compare(old, new, path):
        if type(old) is not type(new):
            diffs.append(path); return
        if isinstance(old, dict):
            for k in sorted(set(old) | set(new)):
                p = path+'/'+k.replace('~','~0').replace('/','~1')
                if k not in old or k not in new: diffs.append(p)
                else: compare(old[k], new[k], p)
        elif isinstance(old, list):
            for i in range(max(len(old), len(new))):
                p = path+'/'+str(i)
                if i >= len(old) or i >= len(new): diffs.append(p)
                else: compare(old[i], new[i], p)
        elif old != new: diffs.append(path)
    compare(before, after, '')
    metrics = {
        'before_count': len(a), 'after_count': len(b),
        'before_unique_key_count': len(ca), 'after_unique_key_count': len(cb),
        'before_duplicate_key_count': sum(n > 1 for n in ca.values()),
        'after_duplicate_key_count': sum(n > 1 for n in cb.values()),
        'added_key_count': len(set(cb)-set(ca)), 'removed_key_count': len(set(ca)-set(cb)),
        'missing_key_count': len(missing), 'extra_key_count': len(extra),
        'id_mismatch_key_count': len(mismatches), 'changed_key_count': len(changed),
        'existing_fields_preserved': not changed,
        'top_level_preserved': top(before) == top(after),
        'placeholders_valid': all(set(r) == {'key','arxiv_id','status'} and
            r['status'] == placeholder_status and ids.get(r['key']) == r['arxiv_id'] for r in added),
        'coverage_valid': not missing and not extra and not mismatches and all(n == 1 for n in cb.values()),
        'duplicate_conflict_key_count': len(conflicts),
    }
    return {'metrics': metrics, 'changed_keys': changed, 'missing_keys': missing,
            'extra_keys': extra, 'id_mismatch_keys': mismatches,
            'duplicate_conflict_keys': conflicts, 'json_pointer_differences': diffs,
            'scope': 'structural_revision_only_not_bibliographic_truth'}


def build_revision_packets(runs, *, root, path_map=None, verify_registered_files=True):
    root = Path(root); packets = []
    mapped = lambda p: Path((path_map or {}).get(str(p), str(p)))
    for relative in runs:
        run = root/relative
        read = lambda p: json.loads(bounded_read(mapped(p), 32_000_000))
        config, manifest, metrics = [read(run/n) for n in ('config.json','manifest.json','metrics.json')]
        if metrics['status'] != 'completed' or config['mode'] != 'baseline':
            raise ValueError('completed_normal_baseline_required')
        if manifest['config_sha256'] != file_sha256(run/'config.json'):
            raise ValueError('revision_config_digest_changed')
        if verify_registered_files:
            if path_map:
                # Relocation preserves original event/config bytes. Each mapped
                # dependency must still match the recorded source/code hash.
                for group in ('source_files', 'code_files'):
                    for name, expected in config[group].items():
                        path = mapped(name)
                        if (path.is_symlink() or not path.is_file() or
                                not path.resolve().is_relative_to(root.resolve()) or
                                file_sha256(path) != expected):
                            raise ValueError('relocated_revision_dependency_changed')
            else:
                _registered_hashes(config['source_files'], root)
                _registered_hashes(config['code_files'], root)
        else:
            # Local forensic copies may lack the remote source files. They do
            # not authorize promotion; this limitation is persisted in provenance.
            if not config.get('source_files') or not config.get('code_files'):
                raise ValueError('registered_source_code_hashes_required')
        catalog = read(config['catalog_path'])
        if file_sha256(mapped(config['catalog_path'])) != config['catalog_sha256']:
            raise ValueError('revision_catalog_changed')
        request_paths = sorted((run/'requests').glob('*.json'))
        if len(request_paths) != metrics['actual_requests']:
            raise ValueError('revision_provider_requests_missing')
        tools = load_provider_tools(request_paths[0])
        if any(load_provider_tools(p) != tools for p in request_paths[1:]):
            raise ValueError('revision_provider_tools_changed')
        actions = _actions(_root_events(run/'events.jsonl', config['session_id']), tools, metrics['actual_requests'])
        previous = None
        for action in actions:
            if not action['ok']: continue
            if action['name'] == PREFIX+'read_task_state':
                previous = action
            elif action['name'] == PREFIX+'write_report':
                if previous is None or not isinstance(previous['value'], dict):
                    raise ValueError('write_without_witnessed_before')
                before, after = previous['value']['report'], action['arguments']['report']
                if action['arguments']['report_sha256'] != previous['value']['report_sha256']:
                    raise ValueError('revision_compare_and_swap_mismatch')
                # On-disk serialized JSON SHA is carried by the receipt. Check
                # actual after bytes using the same host serializer (2 spaces/LF).
                after_sha = hashlib.sha256((json.dumps(after,ensure_ascii=False,indent=2)+'\n').encode()).hexdigest()
                if after_sha != action['value']['report_sha256']:
                    raise ValueError('revision_after_receipt_mismatch')
                checks = [r for r in actions if r['ok'] and r['call_order'] > action['call_order'] and
                    isinstance(r['value'], dict) and r['value'].get('report_sha256') == after_sha]
                if not checks: raise ValueError('revision_after_not_observed')
                facts = revision_facts(before, after, catalog)
                passed = all(facts['metrics'][k] for k in ('coverage_valid','existing_fields_preserved','top_level_preserved','placeholders_valid'))
                witness = {'run_id': str(relative), 'session_id': config['session_id'],
                    'call_id': action['call_id'], 'events_sha256': file_sha256(run/'events.jsonl')}
                packets.append({'packet_id': digest(witness)[:24], **witness,
                    'case_id': config['case_id'], 'classification': 'normal_success' if passed else 'normal_failed_tool_counterexample',
                    'learning_eligible': True, 'motif_training_eligible': passed,
                    'before_report': before, 'after_report': after, 'catalog': catalog,
                    'before_report_sha256': digest(before), 'after_report_sha256': digest(after),
                    'catalog_sha256': digest(catalog), 'oracle_facts': facts,
                    'trace_records': [previous, action, checks[0]],
                    'provenance': {'source_files': config['source_files'], 'code_files': config['code_files'],
                        'registered_bytes_verified': verify_registered_files,
                        **({'relocation_map_sha256': digest(path_map)} if path_map else {}),
                        'config_sha256': file_sha256(run/'config.json'),
                        'manifest_sha256': file_sha256(run/'manifest.json'),
                        'request_sha256': {p.name:file_sha256(p) for p in request_paths}}})
                previous = {'value': {**action['value'],'report':after}, **{k:v for k,v in action.items() if k!='value'}}
    if not packets: raise ValueError('no_witnessed_revisions')
    return {'schema_version':1,'kind':'revision_tool_trace_packets','source_runs':list(runs),'packets':packets,'entries':[]}


def revision_counterfactuals(packet):
    """Independent fault injections derived from a witnessed before/after pair."""
    seed = {k: copy.deepcopy(packet[k]) for k in ('before_report','after_report','catalog')}
    yield 'observed-'+packet['packet_id'], seed
    for name in ('unchanged','extra-copy','missing-row','wrong-id','changed-url','reordered-url',
                 'null-field','deleted-field','changed-top','new-top','illegal-placeholder','conflicting-duplicate'):
        x = copy.deepcopy(seed); a=x['before_report']['references']; b=x['after_report']['references']
        if name == 'unchanged': x['after_report']=copy.deepcopy(x['before_report'])
        elif name == 'extra-copy': b.append(copy.deepcopy(b[-1]))
        elif name == 'missing-row': b.pop(0)
        elif name == 'wrong-id': b[-1]['arxiv_id']='diagnostic-wrong'
        elif name in ('changed-url','reordered-url','null-field','deleted-field'):
            old = next(r for r in a if r.get('source_urls'))
            row = next(r for r in b if r['key']==old['key'])
            if name == 'changed-url': row['source_urls'][0]+='?unrequested=1'
            elif name == 'reordered-url': row['source_urls']=list(reversed(row['source_urls']))
            elif name == 'null-field': row['source_urls']=None
            else: del row['source_urls']
        elif name == 'changed-top': x['after_report']['scope']='unexpected-change'
        elif name == 'new-top': x['after_report']['diagnostic_note']='new-unrequested-field'
        elif name == 'illegal-placeholder':
            row=next(r for r in b if r['key'] not in {q['key'] for q in a});row['source_urls']=['invented']
        elif name == 'conflicting-duplicate':
            old=copy.deepcopy(a[0]);old['status']='conflicting-judgment';a.append(old)
        yield name+'-'+packet['packet_id'], x
