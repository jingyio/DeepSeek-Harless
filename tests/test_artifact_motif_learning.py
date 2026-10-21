"""Synthetic provenance diagnostics, not real model behavior or cost evidence."""
import importlib.util
import json
from pathlib import Path

import pytest

from src.adapters.artifact_motif_compiler import sha, digest

spec = importlib.util.spec_from_file_location('artifact_learner', Path(__file__).parents[1] / 'scripts/learn-artifact-motifs.py')
learner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(learner)


@pytest.mark.parametrize('mode', ['baseline', 'execute'])
def test_native_repair_requires_exact_pre_call_source_and_fresh_output(tmp_path, mode):
    task, workspace = tmp_path / 'task', tmp_path / 'work'
    task.mkdir()
    for directory in ['inputs', 'code', 'outputs/code/new']:
        (workspace / directory).mkdir(parents=True)
    source = 'import sys,json\nfrom pathlib import Path\nd=json.load(open(sys.argv[1]))\nPath(sys.argv[2],"result.txt").write_text(d["title"])\n'
    program = workspace / 'code/native.py'
    program.write_text(source)
    data = workspace / 'inputs/current.json'
    data.write_text('{"title":"current"}')
    result = workspace / 'outputs/code/new/result.txt'
    result.write_text('current')
    (workspace / 'approved-inputs.json').write_text(json.dumps({'files': {'current.json': sha(data.read_bytes())}}))
    (task / 'effective-config.json').write_text(json.dumps({'provider_mode': 'real', 'mode': mode, 'rsi': mode == 'execute', 'workspace': str(workspace)}))
    (task / 'task-state.json').write_text(json.dumps({'status': 'completed', 'scene': 'diagnostic'}))
    arguments = {'command': 'python3 /work/native.py /work/inputs/current.json /work/outputs/new'}
    events = [{'type': 'tool/call', 'data': {'callId': 'native', 'name': 'bash', 'arguments': arguments}},
              {'type': 'tool/result', 'data': {'message': {'content': [{'type': 'tool-result', 'toolCallId': 'native', 'isError': False,
                 'content': [{'type': 'text', 'text': '[exit code: 0]'}]}]}}}]
    (task / 'events.jsonl').write_text('\n'.join(map(json.dumps, events)))
    before = {'code/native.py': {'sha256': sha(program.read_bytes())}, 'inputs/current.json': {'sha256': sha(data.read_bytes())}}
    boundary = {'call_id': 'native', 'arguments_sha256': digest(arguments), 'is_error': False,
                'before': {'files': before}, 'after': {'files': {**before, 'outputs/code/new/result.txt': {'sha256': sha('current')}}}}
    (task / 'reuse-boundaries.jsonl').write_text(json.dumps(boundary))
    learned = learner.collect(task)
    assert len(learned['candidates']) == 1
    assert learned['candidates'][0]['witness']['source_task_mode'] == mode
    program.write_text(source + '# later replacement\n')
    assert learner.collect(task)['candidates'] == []
    program.write_text(source)
    boundary['after']['files'] = before
    (task / 'reuse-boundaries.jsonl').write_text(json.dumps(boundary))
    assert learner.collect(task)['candidates'] == []
    (task / 'task-state.json').write_text(json.dumps({'status': 'failed', 'scene': 'diagnostic'}))
    with pytest.raises(ValueError, match='completed_real_native_task'):
        learner.collect(task)
