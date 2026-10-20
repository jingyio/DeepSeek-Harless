"""Rehydrate bounded native pre-call evidence in a new private replay directory."""
import json
import re
from pathlib import Path, PurePosixPath
from .script_motif_compiler import sha, digest


def restore_boundary(task, boundary, output):
    task, output = Path(task).resolve(), Path(output).resolve()
    files = boundary.get('before', {}).get('files')
    if not isinstance(files, dict) or len(files) > 256:
        raise ValueError('bounded_snapshot_required')
    rows = []
    total = 0
    for name, record in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name or not any(name.startswith(p) for p in ('inputs/', 'code/', 'outputs/code/')):
            raise ValueError('unsafe_snapshot_path')
        version = record.get('sha256', '')
        if not re.fullmatch('[a-f0-9]{64}', version):
            raise ValueError('invalid_snapshot_hash')
        source = task / 'reuse-evidence' / version
        if source.resolve() != source or source.is_symlink() or not source.is_file() or source.stat().st_size > 1000000:
            raise ValueError('snapshot_blob_not_fixed')
        data = source.read_bytes(); total += len(data)
        if sha(data) != version or len(data) != record.get('bytes', len(data)) or total > 8000000:
            raise ValueError('snapshot_content_changed')
        rows.append((name, data))
    if output.exists():
        raise ValueError('snapshot_destination_must_be_new')
    output.mkdir(parents=True, mode=0o700)
    for name in ('inputs', 'code', 'outputs/code', 'command-tmp'):
        (output / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, data in rows:
        target = output / name; target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(data); target.chmod(0o600)
    manifest = {'task_id': task.name, 'call_id': boundary['call_id'],
                'boundary_sha256': digest(boundary), 'scope': 'bounded_pre_call_snapshot_not_full_workspace',
                'files': files, 'bytes': total}
    (output / 'snapshot.json').write_text(json.dumps(manifest, indent=2)); (output / 'snapshot.json').chmod(0o600)
    return output


def restore_call_records(task, output):
    """Materialize exact native argument/result records, not historical file bytes.

    These are additional held-out data, never source-file witnesses. The envelope
    matches the private recovery protocol, with provenance retained per record.
    """
    task, output = Path(task), Path(output)
    raw = (task / 'events.jsonl').read_bytes(); version = sha(raw)
    calls, workspaces = {}, []
    for event in map(json.loads, raw.splitlines()):
        d = event.get('data', {})
        if event.get('type') == 'tool/call':
            try:
                args = json.loads(d['arguments']) if isinstance(d['arguments'], str) else d['arguments']
                if d['name'].startswith('mcp__') and not d['callId'].startswith(('sss-reuse-', 'sss-script-')):
                    calls[d['callId']] = (d['name'], args)
            except (ValueError, KeyError): pass
        if event.get('type') != 'tool/result': continue
        for block in d.get('message', {}).get('content', []):
            call_id = block.get('toolCallId'); call = calls.pop(call_id, None)
            if call is None or len(workspaces) >= 128: continue
            try:
                value = json.loads(next(c['text'] for c in block['content'] if c['type'] == 'text'))
            except (ValueError, KeyError, StopIteration): continue
            record = {'kind':'native_tool_call', 'source_task_id':task.name, 'call_id':call_id,
                      'events_sha256':version, 'tool':call[0], 'arguments':call[1], 'failure':value}
            data = json.dumps(record, ensure_ascii=False).encode()
            if len(data) > 1000000: continue
            work = output / digest(call_id)[:24]
            work.mkdir(parents=True, exist_ok=False, mode=0o700)
            for name in ('code', 'inputs', 'outputs/code', 'command-tmp'):
                (work/name).mkdir(parents=True, exist_ok=True, mode=0o700)
            (work/'code/native-call.json').write_bytes(data); (work/'code/native-call.json').chmod(0o600)
            (work/'snapshot.json').write_text(json.dumps({'scope':'native_record_materialization_not_pre_call_file', 'task_id':task.name, 'call_id':call_id, 'events_sha256':version}))
            workspaces.append(str(work.resolve()))
    return workspaces
