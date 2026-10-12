import json
from src.adapters.parameter_motif_compiler import compile_parameter_library


def test_parameter_prototypes_ignore_directory_and_output_bytes_but_keep_provenance(tmp_path):
    exp = tmp_path / '.local/paper-reference/evidence'
    for i in range(1, 6):
        run = exp / 'runs' / f'baseline-{i:02d}'; run.mkdir(parents=True)
        root = f'root-{i}'
        (run / 'manifest.json').write_text(json.dumps({'session_id': root}))
        path = f'variant-{i}/main.tex'
        calls = [('read', {'file_path': str(run / 'work' / path)}),
                 ('web_fetch', {'url': f'https://arxiv.org/abs/2501.{i:05d}'}),
                 ('web_fetch', {'url': f'https://arxiv.org/abs/2502.{i:05d}'})]
        events = []
        for j, (name, args) in enumerate(calls):
            cid = str(j)
            events += [{'session_id': root, 'event': {'type': 'tool/call', 'data': {
                'callId': cid, 'name': name, 'arguments': args, 'step': 1 if j else 0}}},
                {'session_id': root, 'event': {'type': 'tool/result', 'data': {'message': {'content': [{
                    'type': 'tool-result', 'toolCallId': cid, 'content': [{'type': 'text', 'text': f'dynamic-{i}-{j}'}]}]}}}}]
        # A different-session tool is never promoted into the root's provenance.
        events.append({'session_id': 'child', 'event': {'type': 'tool/call', 'data': {
            'callId': 'child', 'step': 1, 'name': 'web_fetch', 'arguments': {'url': 'https://evil.example/a'}}}})
        (run / 'session-events.jsonl').write_text('\n'.join(map(json.dumps, events)))
        (run / 'file-versions.jsonl').write_text(json.dumps({'session_id': root, 'call_id': '0',
            'snapshot': {'complete': True, 'files': {path: str(i) * 64}}}))
    lib = compile_parameter_library(exp)
    assert len(lib['motifs']) == 2
    read = next(m for m in lib['motifs'] if m['prototype']['tool'] == 'read')
    web = next(m for m in lib['motifs'] if m['prototype']['tool'] == 'web_fetch')
    assert len(read['training_witnesses']) == 3 and len(read['heldout_witnesses']) == 2
    assert len(web['parallel_witnesses']) == 5
    assert read['authorization'] == 'explicit_versioned_input_binding_only'
    assert all(w['session_id'].startswith('root') for m in lib['motifs'] for w in m['training_witnesses'])
    # Input bytes do not become part of structure identity, but remain evidence.
    assert len({w['dependency']['sha256'] for w in read['training_witnesses']}) == 3
