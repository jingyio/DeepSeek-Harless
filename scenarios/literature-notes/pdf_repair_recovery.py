"""Offline validation of a native model final JSON proposal; never synthesize native tool events."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from mcp.server.mcpserver.exceptions import ToolError
from pdf_dependencies import private_file
from pdf_repair_tools import RepairScene
from pdf_tools import ROOT, digest, save_private

READ_TOOLS = {'read_claim_repair_packet', 'search_claim_evidence', 'read_claim_evidence', 'read_claim_evidence_plan', 'submit_claim_repair'}


def recover_final_proposal(model_run, output, run, input_digest):
    model_run, output = Path(model_run).resolve(), Path(output).resolve()
    if not model_run.is_relative_to(ROOT / '.local/runs') or not output.is_relative_to(ROOT / '.local'):
        raise ValueError('unexpected recovery directory')
    events_path = private_file(model_run / 'agent-events.jsonl')
    events_bytes = events_path.read_bytes()
    events = [json.loads(line) for line in events_bytes.splitlines()]
    messages = [e for e in events if e.get('type') == 'assistant/message'
                and e['data'].get('message', {}).get('source', {}).get('kind') == 'model']
    if not messages: return None
    final = messages[-1]['data']
    content = final['message']['content']
    if not content or any(c.get('type') != 'text' for c in content): return None
    text = ''.join(c['text'] for c in content)
    if len(text) > 200_000: return None
    try: proposal = json.loads(text)
    except ValueError: return None
    if not isinstance(proposal, dict) or set(proposal) != {'decisions', 'synthesis_hypothesis'}:
        return None
    # Refuse final text mixed with later actions, incomplete targets, or unsupported plan shapes.
    calls = [e['data'] for e in events if e.get('type') == 'tool/call']
    if any(c['step'] >= final['step'] for c in calls): return None
    scene = RepairScene(Path(run), output)
    if scene.input_digest != input_digest: raise ValueError('recovery input changed')
    values = proposal['decisions']
    if (not isinstance(values, list) or len(values) != len(scene.targets)
            or any(not isinstance(v, dict) or not isinstance(v.get('claim_id'), str) for v in values)
            or len({v['claim_id'] for v in values}) != len(values)
            or {v['claim_id'] for v in values} != set(scene.targets)):
        return None
    if (output / 'revised-evidence.json').exists() or (output / 'claim-review.json').exists():
        raise ValueError('recovery never overwrites an existing artifact')
    call_by_id = {c['callId']: c for c in calls}
    witnessed = []
    for event in events:
        if event.get('type') != 'tool/result': continue
        for block in event['data'].get('message', {}).get('content', []):
            if block.get('type') != 'tool-result': continue
            call = call_by_id.get(block.get('toolCallId'))
            if not call: raise ValueError('tool result lacks a native call')
            prefix = 'mcp__literature_pdf_repair__'
            if not call['name'].startswith(prefix): raise ValueError('unexpected tool in proposal history')
            name = call['name'][len(prefix):]
            if name not in READ_TOOLS: raise ValueError('unexpected repair operation')
            args = json.loads(call['arguments'])
            try: actual = getattr(scene, name)(**args)
            except ToolError:
                if not block.get('isError'): raise ValueError('previous successful read failed current replay') from None
                continue
            if block.get('isError'): raise ValueError('failed tool no longer matches frozen replay')
            expected = json.loads(''.join(c['text'] for c in block['content'] if c.get('type') == 'text'))
            if digest(actual) != digest(expected): raise ValueError('native tool observation differs from replay')
            witnessed.append({'call_id': call['callId'], 'tool': name, 'observation_sha256': digest(expected)})
    scene.proposal_provenance = {'kind': 'validated_model_final_json_recovery',
        'native_run': model_run.name, 'native_events_sha256': hashlib.sha256(events_bytes).hexdigest(),
        'model_message_id': final['message'].get('id'), 'proposal_sha256': digest(proposal),
        'replayed_tools': witnessed, 'synthetic_native_events': False, 'additional_model_requests': 0}
    receipt = scene.submit_claim_repair(**proposal)
    rejected = []
    if receipt.get('status') == 'pending_claim_decisions':
        issues = {v['claim_id']: v['error'] for v in receipt['issues']}
        rejected = receipt['pending_claim_ids']
        # Technical admission failure is not a scientific verdict or a fake model decision.
        scene.runtime_gap_claim_ids = rejected
        receipt = scene.submit_claim_repair([
            {'claim_id': cid, 'verdict': 'not_extracted',
             'reason': 'Runtime未接纳模型提案：' + issues.get(cid, '没有有效决定')[:300]}
            for cid in rejected], proposal['synthesis_hypothesis'])
    if 'artifact' not in receipt: raise ValueError('recovered proposal was not completely admitted')
    recovery = {'schema_version': 1, 'receipt_origin': 'validated_model_final_json_recovery',
                'receipt': receipt, 'runtime_gap_claim_ids': rejected, **scene.proposal_provenance}
    save_private(output / 'proposal-recovery.json', recovery)
    evidence = json.loads(Path(receipt['artifact']).read_text())
    notes = output / 'revised-research-notes.md'
    notes.write_text(evidence['markdown']); notes.chmod(0o600)
    return {'receipt': receipt, 'receipt_origin': recovery['receipt_origin'],
            'runtime_gap_claim_ids': rejected, 'notes': str(output / 'revised-research-notes.md')}
