#!/usr/bin/env python3
"""Mine actually executed native Python programs with explicit data/output argv.

No model calls, no hand-authored renderers, no final evaluation inputs. Source
bytes must be present at the exact pre-call boundary captured by the wrapper.
"""
import argparse
import json
import shlex
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.artifact_motif_compiler import program_from_witness, sha, digest


def host(workspace, virtual):
    if not virtual.startswith('/work/') or '..' in virtual.split('/'):
        raise ValueError('artifact_path_not_current')
    rel = virtual[6:]
    return workspace / (rel if rel.startswith('inputs/') else 'outputs/code/' + rel[8:] if rel.startswith('outputs/') else 'code/' + rel)


def native_program_invocation(command):
    """Parse the complete small shell envelope; never drop an unknown pipeline.

    A witnessed mkdir/echo/cat envelope is common in normal Agent traces. It is
    only admissible with one program, no alternatives/redirections/substitution,
    and later evidence of fresh program output at this exact tool boundary.
    """
    if any(token in command for token in ('`', '$(', '${', '\\n')):
        raise ValueError('artifact_shell_expansion_not_admitted')
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|<>')
    lexer.whitespace_split = True
    lexer.commenters = ''
    segments, current = [], []
    for token in lexer:
        if token in (';', '&&'):
            if not current:
                raise ValueError('artifact_empty_shell_segment')
            segments.append(current)
            current = []
        elif token in ('|', '||', '&', '<', '>', '>>', '<<'):
            raise ValueError('artifact_shell_operator_not_admitted')
        else:
            current.append(token)
    if current:
        segments.append(current)
    program = None
    for segment in segments:
        if segment[:1] in (['python'], ['python3']):
            if program is not None or len(segment) < 4 or not segment[1].endswith('.py'):
                raise ValueError('artifact_one_explicit_program_required')
            program = segment
        elif segment == ['cd', '/work']:
            if program is not None:
                raise ValueError('artifact_late_directory_change')
        elif segment[:2] == ['mkdir', '-p']:
            if program is not None or len(segment) != 3 or not segment[2].startswith(('outputs/', '/work/outputs/')) or '..' in segment[2].split('/'):
                raise ValueError('artifact_mkdir_outside_fresh_output')
        elif segment[:1] == ['echo']:
            if program is None:
                raise ValueError('artifact_echo_before_program')
        elif segment[:1] == ['cat']:
            if program is None or any(not s.startswith(('outputs/', '/work/outputs/')) or '..' in s.split('/') for s in segment[1:]):
                raise ValueError('artifact_cat_outside_program_output')
        else:
            raise ValueError('artifact_unknown_shell_segment')
    if program is None:
        raise ValueError('artifact_explicit_program_required')
    return program


def collect(task):
    effective = json.loads((task / 'effective-config.json').read_text(encoding='utf-8'))
    state = json.loads((task / 'task-state.json').read_text(encoding='utf-8'))
    if effective.get('provider_mode') != 'real' or effective.get('mode') != 'baseline' or state.get('status') != 'completed':
        raise ValueError('completed_real_baseline_required')
    workspace = Path(effective['workspace'])
    boundaries = {r['call_id']: r for r in map(json.loads, (task / 'reuse-boundaries.jsonl').read_text(encoding='utf-8').splitlines())}
    calls, candidates, rejected = {}, [], []
    events_raw = (task / 'events.jsonl').read_bytes()
    for event in map(json.loads, events_raw.decode().splitlines()):
        data = event.get('data', {})
        if event.get('type') == 'tool/call':
            args = data['arguments']
            calls[data['callId']] = (data['name'], json.loads(args) if isinstance(args, str) else args)
        if event.get('type') != 'tool/result':
            continue
        for block in data.get('message', {}).get('content', []):
            cid = block.get('toolCallId')
            if block.get('type') != 'tool-result' or cid not in calls:
                continue
            name, args = calls[cid]
            if name != 'bash' or block.get('isError'):
                continue
            try:
                stdout = ''.join(c.get('text', '') for c in block.get('content', []) if c.get('type') == 'text')
                if re.search(r'\[exit(?: code:)?\s*[1-9][0-9]*\]', stdout) or 'Traceback (most recent call last)' in stdout:
                    raise ValueError('artifact_native_nonzero_exit')
                parts = native_program_invocation(args['command'])
                virtual = parts[1] if parts[1].startswith('/work/') else '/work/' + parts[1]
                path = host(workspace, virtual)
                boundary = boundaries[cid]
                source_raw = path.read_bytes()
                rel = path.relative_to(workspace).as_posix()
                if boundary['is_error'] or boundary['arguments_sha256'] != digest(args) or boundary['before']['files'].get(rel, {}).get('sha256') != sha(source_raw):
                    raise ValueError('artifact_native_source_boundary_changed')
                inputs, outputs = {}, []
                for i, value in enumerate(parts[2:]):
                    if value.startswith('-'):
                        raise ValueError('artifact_positional_path_interface_required')
                    v = value if value.startswith('/work/') else '/work/' + value
                    actual = host(workspace, v)
                    if actual.is_file():
                        version = boundary['before']['files'].get(actual.relative_to(workspace).as_posix(), {})
                        if version.get('sha256') != sha(actual.read_bytes()):
                            raise ValueError('artifact_input_boundary_changed')
                        inputs[i] = actual
                    elif v.startswith('/work/outputs/'):
                        outputs.append(i)
                    else:
                        raise ValueError('artifact_current_file_or_output_required')
                if len(outputs) != 1:
                    raise ValueError('artifact_one_output_directory_required')
                output_virtual = parts[2 + outputs[0]]
                output_host = host(workspace, output_virtual if output_virtual.startswith('/work/') else '/work/' + output_virtual)
                prefix = output_host.relative_to(workspace).as_posix() + '/'
                before, after = boundary['before']['files'], boundary['after']['files']
                if not any(key.startswith(prefix) and before.get(key) != value for key, value in after.items()):
                    raise ValueError('artifact_fresh_native_output_evidence_required')
                witness = {'task_id': task.name, 'call_id': cid, 'events_sha256': sha(events_raw), 'description': args.get('description', ''),
                           'boundary_sha256': digest(boundary), 'input_paths': {str(i): str(p) for i, p in inputs.items()},
                           'input_sha256': {str(i): sha(p.read_bytes()) for i, p in inputs.items()},
                           'original_output': str(output_host),
                           'stdout': stdout}
                candidates.append(program_from_witness(source_raw.decode('utf-8'), parts[2:], inputs, outputs[0], witness))
            except (ValueError, KeyError, OSError, SyntaxError) as error:
                rejected.append({'call_id': cid, 'reason': str(error)[:180]})
    return {'task_id': task.name, 'scene': state['scene'], 'workspace': str(workspace),
            'approved_inputs': json.loads((workspace / 'approved-inputs.json').read_text(encoding='utf-8'))['files'],
            'candidates': candidates, 'rejected': rejected}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump([collect(t.resolve()) for t in args.task], stream, ensure_ascii=False, indent=2)
