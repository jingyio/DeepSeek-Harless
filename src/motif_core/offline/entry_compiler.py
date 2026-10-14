"""Learn a task-entry read frontier from original model decisions and frozen targets."""
from __future__ import annotations
import hashlib
import json
from dataclasses import asdict
from .trace_compiler import artifact_signature, contract_signature


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def entry_witness(events, task, tool, param, *, trace_id, task_fingerprint):
    targets = task['target_ids']
    if (not isinstance(targets, list) or not 1 <= len(targets) <= 100
            or any(not isinstance(t, str) or not 1 <= len(t) <= 160 for t in targets)
            or len(set(targets)) != len(targets)):
        raise ValueError('entry targets must be a bounded unique frozen list')
    calls = {e['data']['callId']: e for e in events if e.get('type') == 'tool/call'}
    results = {}
    for e in events:
        if e.get('type') != 'tool/result' or e.get('ptc_analysis_source'):
            continue
        for b in e.get('data', {}).get('message', {}).get('content', []):
            if b.get('type') == 'tool-result':
                results.setdefault(b['toolCallId'], []).append((e, b))
    selected, references, request_count, output_tokens = [], [], 0, 0
    for e in events:
        if e.get('type') != 'assistant/message':
            continue
        data = e['data']; message = data.get('message', {})
        if message.get('source', {}).get('kind') != 'model':
            continue
        blocks = [b for b in message.get('content', []) if b.get('type') == 'tool-call']
        if not blocks or any(b.get('name') != tool for b in blocks):
            break
        if not data.get('usage'):
            raise ValueError('entry witness must be an actual provider message with usage')
        request_count += 1; output_tokens += data['usage'].get('outputTokens', 0)
        for block in blocks:
            cid = block.get('id', '')
            if cid.startswith('sss-') or cid not in calls or len(results.get(cid, [])) != 1:
                raise ValueError('runtime/ambiguous calls cannot witness learned entry')
            arguments = json.loads(block['arguments'])
            call = calls[cid]
            if (set(arguments) != {param} or call['data']['name'] != tool
                    or json.loads(call['data']['arguments']) != arguments):
                raise ValueError('original call differs from model decision')
            value = arguments[param]
            result, content = results[cid][0]
            if content.get('isError') or len(content.get('content', [])) != 1:
                raise ValueError('entry read failed or has ambiguous output')
            observation = json.loads(content['content'][0]['text'])
            if (value not in targets or value in selected or observation.get(param) != value
                    or observation.get('input_sha256') != task['input_version']
                    or observation.get('document_version_sha256') != task['target_versions'].get(value)):
                raise ValueError('entry read is not bound to frozen target and source')
            selected.append(value)
            references.append({'message_seq': e['seq'], 'call_seq': call['seq'], 'result_seq': result['seq'],
                               'call_id': cid, 'target_id': value, 'observation_sha256': digest(observation)})
        if selected == targets:
            break
    if selected != targets:
        raise ValueError('observed entry is not the complete ordered frozen target set')
    return {'trace_id': trace_id, 'task_fingerprint': task_fingerprint,
            'target_count': len(targets), 'target_ids_sha256': digest(targets),
            'input_version': task['input_version'], 'provider_requests': request_count,
            'output_tokens': output_tokens, 'references': references}


def compile_entry_motif(training, contracts, *, tool, param, schema_sha256):
    if len(training) < 2 or len({v['trace_id'] for v in training}) != len(training):
        raise ValueError('entry learning needs two independent traces')
    if len({v['task_fingerprint'] for v in training}) != len(training):
        raise ValueError('entry learning cannot count one task twice')
    if len({v['target_count'] for v in training}) < 2:
        raise ValueError('varying target sizes required for a repeated frontier')
    contract = contracts[tool]
    if not contract.read_only or not contract.replay_stable or contract.required_params != (param,):
        raise ValueError('entry needs one replay-stable read-only scalar argument')
    entry = {'kind': 'foreach_frozen_targets', 'selection': 'all_targets', 'tool': tool,
             'param': param, 'max_targets': 100, 'max_batch': 8,
             'result_identity_field': param, 'result_input_field': 'input_sha256',
             'result_source_field': 'document_version_sha256', 'stop': 'semantic_handoff_after_reads'}
    return {'schema_version': 1, 'kind': 'task_entry_read_frontier',
            'motif_id': 'entry_' + digest({'tool': tool, 'param': param})[:16],
            'status': 'compiled_candidate', 'tools': [tool], 'transfer_evidence': [],
            'source_trace_ids': [v['trace_id'] for v in training],
            'source_task_fingerprints': [v['task_fingerprint'] for v in training],
            'contract_signature': contract_signature([tool], contracts), 'schema_sha256': schema_sha256,
            'entry': entry, 'training_witnesses': training}


def certify_entry_motif(compiled, heldout, contracts):
    guarded = compiled.get('kind') in ('task_entry_inventory_frontier', 'task_entry_incremental_frontier')
    incremental = compiled.get('kind') == 'task_entry_incremental_frontier'
    if (compiled.get('status') != 'compiled_candidate'
            or heldout['trace_id'] in compiled['source_trace_ids']
            or heldout['task_fingerprint'] in compiled['source_task_fingerprints']
            or guarded and
                (heldout.get('kind') != ('incremental_prepare_witness' if incremental else 'inventory_prepare_witness')
                 or heldout.get('binding') != ('source.work[].paper_id' if incremental else 'source.papers[].paper_id'))
            or compiled['contract_signature'] != (inventory_contract_signature(compiled['tools'], contracts)
                if guarded else contract_signature(compiled['tools'], contracts))):
        raise ValueError('entry certification must use a new task and unchanged contracts')
    artifact = {**compiled, 'status': 'trace_validated_read_only',
                'validation_trace_id': heldout['trace_id'],
                'validation_task_fingerprint': heldout['task_fingerprint'], 'validation_witness': heldout}
    artifact['certified_digest'] = artifact_signature(artifact)
    return artifact


def navigation_projection(observation):
    """Only cache counters vary; keep every source, page and diagnostic field."""
    return {k: v for k, v in observation.items() if k != 'cache_stats'}


def inventory_contract_signature(tools, contracts):
    """Separate guarded preparation contract; never relax legacy replay rules."""
    if any(not contracts[t].read_only for t in tools):
        raise ValueError('inventory requires read-only contracts')
    return digest({'guard': 'inventory_pdf_parser_versions_v1', 'projection_exception': ['cache_stats'],
                   'contracts': {t: asdict(contracts[t]) for t in tools}})


def inventory_witness(events, task, source_tool, prepare_tool, *, trace_id, task_fingerprint, frontier='inventory'):
    """Witness actual list-result -> all selected PDF IDs -> preparation prefix."""
    if frontier not in ('inventory', 'incremental'):
        raise ValueError('unknown entry frontier')
    incremental = frontier == 'incremental'
    array_field = 'work' if incremental else 'papers'
    selection = 'all_invalidated_work' if incremental else 'all_selected_inventory'
    calls = {}
    results = {}
    for event in events:
        if event.get('ptc_analysis_source'):
            raise ValueError('projected events cannot witness inventory entry')
        if event.get('type') == 'tool/call':
            cid = event['data']['callId']
            if cid in calls:
                raise ValueError('duplicate original call')
            calls[cid] = event
        elif event.get('type') == 'tool/result':
            for block in event['data']['message'].get('content', []):
                if block.get('type') == 'tool-result':
                    results.setdefault(block['toolCallId'], []).append((event, block))

    def original(message, block):
        cid = block['id']
        if cid.startswith('sss-') or cid not in calls or len(results.get(cid, [])) != 1:
            raise ValueError('runtime or ambiguous inventory call')
        call = calls[cid]; result, output = results[cid][0]
        args = json.loads(block['arguments'])
        if (call['data']['name'] != block['name'] or json.loads(call['data']['arguments']) != args
                or not message['seq'] < call['seq'] < result['seq'] or output.get('isError')
                or len(output.get('content', [])) != 1 or output['content'][0].get('type') != 'text'):
            raise ValueError('failed or changed original inventory call/result')
        observation = json.loads(output['content'][0]['text'])
        return args, observation, {'message_seq': message['seq'], 'call_seq': call['seq'],
            'result_seq': result['seq'], 'call_id': cid, 'observation_sha256': digest(observation)}

    papers = task['inventory_papers']
    ids = [p['paper_id'] for p in papers]
    if not 1 <= len(ids) <= 20 or len(set(ids)) != len(ids):
        raise ValueError('bounded unique inventory required')
    references = []; selected = []; source = None; requests = tokens = 0
    for event in events:
        if event.get('type') != 'assistant/message':
            continue
        data = event['data']; message = data.get('message', {})
        if message.get('source', {}).get('kind') != 'model':
            raise ValueError('inventory prefix must be original model decisions')
        if not data.get('usage'):
            raise ValueError('inventory prefix requires actual provider usage')
        blocks = [b for b in message.get('content', []) if b.get('type') == 'tool-call']
        if source is None:
            if len(blocks) != 1 or blocks[0]['name'] != source_tool:
                raise ValueError('inventory is not the first decision')
            args, observation, source = original(event, blocks[0])
            source_rows = observation.get(array_field)
            if (args != {} or observation.get('task_sha256') != task['input_version']
                    or observation.get('question') != task['question']
                    or (not incremental and source_rows != papers)
                    or (incremental and (digest(observation) != task['source_result_sha256']
                        or observation.get('plan_sha256') != task['plan_sha256']
                        or not isinstance(source_rows, list) or [r.get('paper_id') for r in source_rows] != ids))):
                raise ValueError('source result differs from frozen selected inventory')
            source.update(role='source', projection_sha256=digest(observation)); references.append(source)
        else:
            if not blocks or any(b['name'] != prepare_tool for b in blocks):
                raise ValueError('semantic decision interrupts all-inventory preparation')
            if event['seq'] <= source['result_seq']:
                raise ValueError('prepare parameter precedes actual inventory result')
            for block in blocks:
                args, observation, ref = original(event, block)
                pid = args.get('paper_id')
                if (set(args) != {'paper_id'} or pid not in ids or pid in selected
                        or observation.get('paper_id') != pid
                        or observation.get('pdf_sha256') != papers[ids.index(pid)]['pdf_sha256']
                        or observation.get('document_version_sha256') != task['target_versions'].get(pid)
                        or observation.get('parser_profile_sha256') != task['parser_profile_sha256']):
                    raise ValueError('prepare is not bound to unique source-array member/version')
                selected.append(pid)
                ref.update(role='prepare', target_id=pid, source_call_id=source['call_id'],
                    source_array_index=ids.index(pid), projection_sha256=digest(navigation_projection(observation)))
                references.append(ref)
        requests += 1; tokens += data['usage'].get('outputTokens', 0)
        if len(selected) == len(ids):
            break
    if set(selected) != set(ids):
        raise ValueError('not all selected PDFs prepared before semantic handoff')
    return {'kind': 'incremental_prepare_witness' if incremental else 'inventory_prepare_witness', 'trace_id': trace_id, 'task_fingerprint': task_fingerprint,
        'target_count': len(ids), 'target_ids_sha256': digest(ids), 'input_version': task['input_version'],
        'provider_requests': requests, 'output_tokens': tokens, 'references': references,
        'binding': f'source.{array_field}[].paper_id', 'selection': selection,
        'projection_excluded_fields': ['cache_stats']}


def compile_inventory_motif(training, contracts, *, source_tool, prepare_tool, schemas, frontier='inventory'):
    if frontier not in ('inventory', 'incremental'):
        raise ValueError('unknown entry frontier')
    incremental = frontier == 'incremental'
    array_field = 'work' if incremental else 'papers'
    selection = 'all_invalidated_work' if incremental else 'all_selected_inventory'
    if (len(training) < 2 or len({v['trace_id'] for v in training}) != len(training)
            or len({v['task_fingerprint'] for v in training}) != len(training)
            or len({v['target_count'] for v in training}) < 2
            or any(v.get('kind') != ('incremental_prepare_witness' if incremental else 'inventory_prepare_witness')
                   or v.get('binding') != f'source.{array_field}[].paper_id'
                   or v.get('selection') != selection for v in training)):
        raise ValueError('inventory learning needs independent varying-size original frontiers')
    if (not contracts[source_tool].read_only or contracts[source_tool].required_params != ()
            or not contracts[prepare_tool].read_only or contracts[prepare_tool].required_params != ('paper_id',)):
        raise ValueError('inventory tools must be read-only zero/scalar contracts')
    entry = {'kind': 'update_plan_then_foreach' if incremental else 'inventory_then_foreach', 'selection': selection,
        'source_tool': source_tool, 'tool': prepare_tool, 'param': 'paper_id',
        'array_field': array_field, 'identity_field': 'paper_id', 'input_field': 'task_sha256',
        'source_field': 'pdf_sha256', 'result_version_field': 'document_version_sha256',
        'parser_field': 'parser_profile_sha256', 'max_targets': 20, 'max_batch': 8,
        'stop': 'semantic_handoff_after_reads'}
    if incremental:
        entry['plan_field'] = 'plan_sha256'
    tools = [source_tool, prepare_tool]
    return {'schema_version': 1, 'kind': 'task_entry_incremental_frontier' if incremental else 'task_entry_inventory_frontier',
        'motif_id': frontier + '_' + digest(tools)[:16], 'status': 'compiled_candidate',
        'tools': tools, 'transfer_evidence': [{'from_tool': source_tool, 'to_tool': prepare_tool,
            'from_field': f'{array_field}[].paper_id', 'to_param': 'paper_id', 'selection': selection}],
        'source_trace_ids': [v['trace_id'] for v in training],
        'source_task_fingerprints': [v['task_fingerprint'] for v in training],
        'contract_signature': inventory_contract_signature(tools, contracts), 'schema_sha256': digest(schemas),
        'tool_schema_sha256': {t: digest(schemas[t]) for t in tools}, 'entry': entry,
        'projection_excluded_fields': ['cache_stats'], 'training_witnesses': training}
