"""Certify a receipt -> one original final provider response -> stop frontier."""
import json
from dataclasses import asdict
from .entry_compiler import digest
from .trace_compiler import artifact_signature


def signature(tool, contracts):
    c = contracts[tool]
    if not c.read_only or c.required_params != ('decisions', 'synthesis_hypothesis'):
        raise ValueError('terminal requires the declared private claim-repair contract')
    return digest({'guard': 'claim_repair_receipt_v1', 'contract': asdict(c)})


def terminal_witness(events, tool, *, trace_id, task_fingerprint, input_version, request_version, target_ids):
    if any(e.get('ptc_analysis_source') for e in events):
        raise ValueError('projected terminal events are not original decisions')
    calls = {e['data']['callId']: e for e in events if e['type'] == 'tool/call'}
    candidates = []
    for e in events:
        if e['type'] != 'assistant/message': continue
        data = e['data']; message = data['message']; blocks = message.get('content', [])
        tb = [b for b in blocks if b['type'] == 'tool-call']
        if len(tb) != 1 or tb[0]['name'] != tool: continue
        b = tb[0]; cid = b['id']; call = calls.get(cid)
        if cid.startswith('sss-') or not call or not data.get('usage') or message.get('source', {}).get('kind') != 'model':
            continue
        args = json.loads(b['arguments'])
        if call['data']['name'] != tool or json.loads(call['data']['arguments']) != args:
            raise ValueError('original submission differs')
        matches = [(r, c) for r in events if r['type'] == 'tool/result'
            for c in r['data']['message'].get('content', []) if c.get('type') == 'tool-result' and c.get('toolCallId') == cid]
        if len(matches) != 1: raise ValueError('ambiguous original receipt')
        r, result = matches[0]
        if result.get('isError') or len(result.get('content', [])) != 1: continue
        receipt = json.loads(result['content'][0]['text'])
        if not receipt.get('artifact') or receipt.get('input_sha256') != input_version: continue
        if not e['seq'] < call['seq'] < r['seq']: raise ValueError('receipt precedes submission')
        after = [v for v in events if v['seq'] > r['seq']]
        if any(v['type'] in ('tool/call', 'tool/result', 'user/message') for v in after): continue
        finals = [v for v in after if v['type'] == 'assistant/message']
        if len(finals) != 1: continue
        final = finals[0]; fd = final['data']; fm = fd['message']
        if (fm.get('source', {}).get('kind') != 'model' or not fd.get('usage')
                or not fm.get('content') or any(v['type'] != 'text' for v in fm['content'])
                or not any(v.get('type') == 'chunk' and v.get('chunk', {}).get('type') == 'finish'
                    and v['chunk'].get('reason', {}).get('kind') == 'stop' for v in fd.get('stream', []))
                or not any(v['type'] == 'turn/end' and v['seq'] > final['seq'] for v in after)):
            continue
        candidates.append({'kind': 'receipt_finish_witness', 'trace_id': trace_id, 'task_fingerprint': task_fingerprint,
            'input_version': input_version, 'request_version': request_version, 'target_count': len(target_ids),
            'target_ids_sha256': digest(target_ids), 'status': receipt['status'], 'provider_requests': 1,
            'output_tokens': fd['usage'].get('outputTokens', 0), 'receipt': receipt,
            'references': {'submission_message_seq': e['seq'], 'call_seq': call['seq'], 'call_id': cid,
                'result_seq': r['seq'], 'receipt_sha256': digest(receipt), 'final_message_seq': final['seq'],
                'final_message_sha256': digest(fm)}})
    if len(candidates) != 1: raise ValueError('no unique successful receipt -> original final response -> stop')
    return candidates[0]


def compile_terminal(training, contracts, *, tool, schema):
    if (len(training) != 2 or len({w['trace_id'] for w in training}) != 2
            or len({w['task_fingerprint'] for w in training}) != 2
            or len({w['target_count'] for w in training}) != 2
            or any(w.get('kind') != 'receipt_finish_witness' or w['provider_requests'] != 1 for w in training)):
        raise ValueError('terminal needs independent varying-size original decisions')
    statuses = sorted({w['status'] for w in training})
    if any(s not in ('preview', 'needs_review') for s in statuses): raise ValueError('not a completed receipt status')
    return {'schema_version': 1, 'kind': 'task_terminal_receipt', 'status': 'compiled_candidate',
        'tools': [tool], 'motif_id': 'terminal_' + digest(tool)[:16], 'transfer_evidence': [],
        'schema_sha256': digest(schema), 'contract_signature': signature(tool, contracts),
        'source_trace_ids': [w['trace_id'] for w in training],
        'source_task_fingerprints': [w['task_fingerprint'] for w in training], 'training_witnesses': training,
        'terminal': {'kind': 'receipt_then_finish', 'receipt_contract': 'claim_repair_v1', 'tool': tool,
            'statuses': statuses, 'max_targets': 100, 'output': 'verified_status_json', 'provider_requests': 0}}


def certify_terminal(compiled, heldout, contracts):
    if (compiled['status'] != 'compiled_candidate' or heldout['kind'] != 'receipt_finish_witness'
            or heldout['trace_id'] in compiled['source_trace_ids'] or heldout['task_fingerprint'] in compiled['source_task_fingerprints']
            or heldout['status'] not in compiled['terminal']['statuses']
            or compiled['contract_signature'] != signature(compiled['terminal']['tool'], contracts)):
        raise ValueError('independent terminal certification and unchanged contracts required')
    a = {**compiled, 'status': 'trace_validated_read_only', 'validation_trace_id': heldout['trace_id'],
        'validation_task_fingerprint': heldout['task_fingerprint'], 'validation_witness': heldout}
    a['certified_digest'] = artifact_signature(a)
    return a
