"""Identify durable DSH tool observations across context replacements."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def is_original_tool_result(event: Mapping[str, Any]) -> bool:
    """Exclude result events appended only to replace model-visible context.

    DSH compaction can append a replacement with the same callId as an earlier
    result. That replacement changes the model's context, not the tool's
    original observation. Older event streams have no surfaceOp marker.
    """
    if event.get("type") != "tool/result":
        return False
    operation = event.get("surfaceOp")
    return operation is None or operation == "append" or (
        isinstance(operation, Mapping) and operation.get("op") == "append")


def project_ptc_dispatches(events):
    """Derived analysis view of paired ORIGINAL PTC sub-dispatches; never rewrite logs.

    The source markers identify this projection. It is not an original tool/call
    recording, a fabricated model decision, or a training/skip witness by itself.
    Root, parent, arguments and unique start/settled pairing must agree.
    """
    import hashlib
    import json
    rows = list(events)
    roots, starts, settled, output = {}, {}, set(), []
    for index, event in enumerate(rows):
        output.append(event)
        data = event.get('data', {})
        if event.get('type') == 'tool/call' and data.get('name') == 'run_code':
            identity = data.get('callId')
            if not isinstance(identity, str) or identity in roots:
                raise ValueError('ambiguous PTC root')
            roots[identity] = index
        if event.get('type') not in ('tool/ptc-dispatch-start', 'tool/ptc-dispatch'):
            continue
        root, parent, sub = (data.get(k) for k in ('rootCallId', 'parentCallId', 'subCallId'))
        if (root not in roots or parent != root or not isinstance(sub, str) or not sub.startswith(root + ':ptc:')
                or not isinstance(data.get('name'), str) or not isinstance(data.get('arguments'), dict)):
            raise ValueError('unwitnessed PTC dispatch')
        marker = {'kind': 'derived_ptc_analysis', 'source_type': event['type'],
                  'source_seq': event.get('seq', index), 'root_call_id': root,
                  'source_sha256': hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False,
                                                           separators=(',', ':')).encode()).hexdigest()}
        if event['type'] == 'tool/ptc-dispatch-start':
            if sub in starts: raise ValueError('duplicate PTC start')
            starts[sub] = data
            output.append({'type': 'tool/call', 'seq': event.get('seq', index),
                'ptc_analysis_source': marker, 'data': {'callId': sub, 'name': data['name'],
                'arguments': json.dumps(data['arguments'], ensure_ascii=False)}})
        else:
            start = starts.get(sub)
            if (sub in settled or start is None or any(data.get(k) != start.get(k) for k in
                    ('rootCallId', 'parentCallId', 'name', 'arguments'))
                    or type(data.get('isError')) is not bool or not isinstance(data.get('content'), list)):
                raise ValueError('PTC start/settled mismatch')
            settled.add(sub)
            output.append({'type': 'tool/result', 'seq': event.get('seq', index), 'ptc_analysis_source': marker,
                'data': {'message': {'source': {'kind': 'tool', 'callId': sub}, 'content': [
                    {'type': 'tool-result', 'toolCallId': sub, 'isError': data['isError'], 'content': data['content']}]}}})
    if set(starts) != settled: raise ValueError('unsettled PTC dispatch')
    return output
