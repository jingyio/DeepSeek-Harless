"""Private normal traces and bounded interpretation of observed data-only Python.

Never executes historical shell or generated Python. Source replay is an
independent oracle, not a proof of scientific truth or cross-paper generality.
"""
from __future__ import annotations
import ast
import hashlib
import io
import json
import math
import re
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def bounded_read(path, limit=2_000_000):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('regular_bounded_file_required')
    raw = path.read_bytes()
    if len(raw) > limit: raise ValueError('file_changed_or_too_large')
    return raw


def json_value(value):
    if isinstance(value, (set, frozenset)):
        return sorted((json_value(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError('non_json_replay_value')


def bounded_data(value):
    nodes, size = 0, 0
    def walk(v, depth):
        nonlocal nodes, size
        nodes += 1
        if nodes > 16000 or depth > 40: raise ValueError('replay_data_depth_or_nodes')
        if isinstance(v, dict):
            if len(v) > 2000: raise ValueError('replay_container_limit')
            for key, item in v.items():
                if not isinstance(key, str) or key in ('__proto__', 'constructor', 'prototype'): raise ValueError('unsafe_replay_key')
                walk(key, depth + 1); walk(item, depth + 1)
        elif isinstance(v, (list, tuple, set, frozenset)):
            if len(v) > 2000: raise ValueError('replay_container_limit')
            for item in v: walk(item, depth + 1)
        elif isinstance(v, str): size += len(v.encode()) + 2
        elif isinstance(v, float) and not math.isfinite(v): raise ValueError('non_finite_replay_number')
        elif v is None or isinstance(v, (bool, int, float)): size += 24
        else: raise ValueError('non_data_replay_value')
        if size > 192000: raise ValueError('replay_data_byte_limit')
    walk(value, 0)
    return value


def parse_json(text):
    def reject(value): raise ValueError('non_finite_json:' + value)
    try: return bounded_data(json.loads(text, parse_constant=reject))
    except RecursionError as exc: raise ValueError('replay_json_depth') from exc


class SourceReplay:
    """Small AST interpreter. No exec/eval/import, subprocess, filesystem or network.

    Only literal registered memory-file reads, simple comprehensions and the
    explicitly enumerated pure calls below are supported. Unsupported programs
    remain trace evidence and are never silently replayed as a successful tool.
    """
    def __init__(self, files):
        self.files = dict(files)
        if sum(len(v.encode()) for v in self.files.values()) > 192000: raise ValueError('replay_memory_limit')
        self.env = {}
        self.outputs = {}
        self.lines = []
        self.fuel = 200_000

    def spend(self):
        self.fuel -= 1
        if self.fuel < 0:
            raise ValueError('source_replay_operation_limit')

    def bind(self, target, value, env):
        if isinstance(target, ast.Name) and (target.id == '_' or not target.id.startswith('_')):
            env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)) and len(target.elts) == len(value):
            for t, v in zip(target.elts, value):
                self.bind(t, v, env)
        else:
            raise ValueError('unsupported_assignment')

    def comprehension(self, generators, env, index=0):
        if index == len(generators):
            yield env
            return
        gen = generators[index]
        if gen.is_async:
            raise ValueError('async_not_supported')
        values = self.ev(gen.iter, env)
        if not isinstance(values, (list, tuple, set, dict)) or len(values) > 2000:
            raise ValueError('bounded_comprehension_required')
        for value in values:
            self.spend()
            local = dict(env)
            self.bind(gen.target, value, local)
            if all(self.ev(test, local) for test in gen.ifs):
                yield from self.comprehension(generators, local, index + 1)

    def ev(self, node, env):
        self.spend()
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ValueError('unknown_source_variable')
            return env[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.Not)):
            value = self.ev(node.operand, env)
            return -value if isinstance(node.op, ast.USub) else not value
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self.ev(n, env) for n in node.elts]
            return set(values) if isinstance(node, ast.Set) else tuple(values) if isinstance(node, ast.Tuple) else values
        if isinstance(node, ast.Dict):
            return {self.ev(k, env): self.ev(v, env) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Subscript):
            value, key = self.ev(node.value, env), self.ev(node.slice, env)
            if not isinstance(value, (list, tuple, dict, str)):
                raise ValueError('data_subscript_required')
            return value[key]
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            frames = self.comprehension(node.generators, env)
            if isinstance(node, ast.DictComp):
                value = {}
                for f in frames:
                    value[self.ev(node.key, f)] = self.ev(node.value, f)
                    bounded_data(value)
                return value
            values = []
            for f in frames:
                values.append(self.ev(node.elt, f)); bounded_data(values)
            return set(values) if isinstance(node, ast.SetComp) else values
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = self.ev(node.left, env), self.ev(node.comparators[0], env)
            op = node.ops[0]
            if isinstance(op, ast.Eq): return left == right
            if isinstance(op, ast.NotEq): return left != right
            if isinstance(op, ast.In): return left in right
            if isinstance(op, ast.NotIn): return left not in right
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
            left, right = self.ev(node.left, env), self.ev(node.right, env)
            if isinstance(left, set) and isinstance(right, set): return left - right
        if isinstance(node, ast.BoolOp):
            result = self.ev(node.values[0], env)
            for child in node.values[1:]:
                if isinstance(node.op, ast.And) and not result: return result
                if isinstance(node.op, ast.Or) and result: return result
                result = self.ev(child, env)
            return result
        if isinstance(node, ast.Call) and not node.keywords:
            return self.call(node, env)
        raise ValueError('unsupported_source_ast:' + type(node).__name__)

    def call(self, node, env):
        fn = node.func
        if isinstance(fn, ast.Name):
            name = fn.id
            if name == 'open':
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    raise ValueError('literal_memory_path_required')
                args = [self.ev(n, env) for n in node.args]
                path, mode = args[0], args[1] if len(args) == 2 else 'r'
                if len(args) > 2 or path not in self.files or mode not in ('r', 'rb'):
                    raise ValueError('unregistered_or_write_path')
                raw = self.files[path].encode()
                return io.BytesIO(raw) if mode == 'rb' else io.StringIO(raw.decode())
            args = [self.ev(n, env) for n in node.args]
            if name == 'print':
                bounded_data(args)
                line = ' '.join(str(v) for v in args)
                if sum(len(v.encode()) for v in self.lines) + len(line.encode()) > 192000:
                    raise ValueError('replay_stdout_limit')
                self.lines.append(line)
                if len(args) == 3 and isinstance(args[0], str) and isinstance(args[1], str) and args[1].endswith(':'):
                    pairs = [(args[0] + ' ' + args[1], args[2])]
                elif len(args) % 2 == 0:
                    pairs = list(zip(args[::2], args[1::2]))
                else:
                    raise ValueError('labelled_print_required')
                for label, value in pairs:
                    if not isinstance(label, str) or not label.endswith(':') or label[:-1] in self.outputs:
                        raise ValueError('unique_print_label_required')
                    self.outputs[label[:-1]] = json_value(value)
                return None
            allowed = {'len': len, 'sorted': sorted, 'set': set, 'all': all, 'list': list, 'sum': sum}
            if name in allowed and len(args) == 1 and len(args[0]) <= 2000:
                return allowed[name](args[0])
        elif isinstance(fn, ast.Attribute) and not fn.attr.startswith('_'):
            args = [self.ev(n, env) for n in node.args]
            if isinstance(fn.value, ast.Name) and fn.value.id in ('json', 'hashlib'):
                if env.get(fn.value.id) != ('module', fn.value.id):
                    raise ValueError('source_module_not_imported')
                if fn.value.id == 'json' and fn.attr == 'load' and len(args) == 1 and isinstance(args[0], io.StringIO):
                    return parse_json(args[0].getvalue())
                if fn.value.id == 'hashlib' and fn.attr == 'sha256' and len(args) == 1 and isinstance(args[0], bytes):
                    return ('sha256', hashlib.sha256(args[0]).hexdigest())
            receiver = self.ev(fn.value, env)
            if isinstance(receiver, dict) and fn.attr == 'get' and len(args) in (1, 2):
                return receiver.get(*args)
            if isinstance(receiver, str) and fn.attr == 'split' and len(args) == 1 and isinstance(args[0], str) and args[0]:
                value = receiver.split(args[0])
                if len(value) <= 2000: return value
            if isinstance(receiver, str) and fn.attr == 'strip' and not args:
                return receiver.strip()
            if isinstance(receiver, (io.StringIO, io.BytesIO)) and fn.attr == 'read' and not args:
                return receiver.getvalue()
            if isinstance(receiver, tuple) and len(receiver) == 2 and receiver[0] == 'sha256' and fn.attr == 'hexdigest' and not args:
                return receiver[1]
        raise ValueError('unsupported_source_call')

    def run(self, source):
        if len(source.encode()) > 32000: raise ValueError('source_too_large')
        tree = ast.parse(source)
        def ast_depth(node, depth=0):
            if depth > 40: raise ValueError('source_ast_depth')
            for child in ast.iter_child_nodes(node): ast_depth(child, depth + 1)
        ast_depth(tree)
        if len(list(ast.walk(tree))) > 2500:
            raise ValueError('source_ast_too_large')
        def statement(stmt, env):
            self.spend()
            if isinstance(stmt, ast.Import) and all(a.name in ('json', 'hashlib') and a.asname is None for a in stmt.names):
                for alias in stmt.names: env[alias.name] = ('module', alias.name)
            elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                self.bind(stmt.targets[0], self.ev(stmt.value, env), env)
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == 'print':
                self.ev(stmt.value, env)
            elif isinstance(stmt, ast.For) and not stmt.orelse:
                values = self.ev(stmt.iter, env)
                if not isinstance(values, (list, tuple, set)) or len(values) > 2000:
                    raise ValueError('bounded_for_required')
                for value in values:
                    self.spend()
                    self.bind(stmt.target, value, env)
                    for child in stmt.body: statement(child, env)
            else:
                raise ValueError('unsupported_source_statement')
        for stmt in tree.body: statement(stmt, self.env)
        return {'outputs': self.outputs, 'stdout': '\n'.join(self.lines) + '\n'}


def extract_source(command):
    match = re.search(r"\bpython(?:3)?\s+-\s+<<['\"]?([A-Za-z_]\w*)['\"]?\n(.*?)\n\1\s*$", command, re.S)
    if not match: raise ValueError('not_supported_python_heredoc')
    return match.group(2)


def normalize_printed_dicts(text):
    # Python set iteration can change the insertion order of a printed dict.
    # Normalize only a single labelled dict value; arrays, facts and other
    # formatting must still match. Retain both original stdout hashes.
    lines = []
    for line in text.splitlines():
        prefix, separator, rest = line.partition(': ')
        if separator and rest.startswith('{') and rest.endswith('}'):
            try:
                value = ast.literal_eval(rest)
                if isinstance(value, dict): rest = json.dumps(value, ensure_ascii=False, sort_keys=True)
            except (ValueError, SyntaxError): pass
        lines.append(prefix + separator + rest)
    return '\n'.join(lines)


def stdout_match_kind(observed, replayed):
    left, right = normalize_printed_dicts(observed), normalize_printed_dicts(replayed)
    if left == right:
        return 'printed_dict_order_only' if left != observed.rstrip('\n') or right != replayed.rstrip('\n') else 'exact_bytes'
    raise ValueError('snapshot_does_not_reproduce_observed_stdout')


def memory_paths(source):
    paths = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'open':
            if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                raise ValueError('literal_memory_path_required')
            name = node.args[0].value
            if Path(name).name != name or Path(name).suffix not in ('.json', '.txt'):
                raise ValueError('unsupported_memory_filename')
            if name not in paths: paths.append(name)
    return paths


def trace_run(root, relative):
    root = Path(root).resolve()
    run = root / relative
    if run.is_symlink() or not run.resolve().is_relative_to(root / '.local'):
        raise ValueError('private_normal_run_required')
    manifest_path = run / 'manifest.json'
    if not manifest_path.exists(): manifest_path = run / 'config.json'
    manifest = json.loads(bounded_read(manifest_path))
    metrics = json.loads(bounded_read(run / 'metrics.json'))
    if manifest.get('mode') not in ('baseline', 'shadow') or metrics.get('status') != 'completed' or metrics.get('verified_skips', 0):
        raise ValueError('normal_completed_trace_required')
    session = manifest['session_id']
    event_path = run / 'session-events.jsonl'
    if not event_path.exists(): event_path = run / 'events.jsonl'
    raw = bounded_read(event_path, 32_000_000)
    events = []
    for line_no, line in enumerate(raw.decode().splitlines(), 1):
        row = json.loads(line)
        if row.get('session_id', row.get('sessionId')) == session:
            events.append((line_no, row['event']))
    calls, results = [], {}
    for line_no, event in events:
        data = event.get('data', {})
        if event['type'] == 'tool/call':
            args = data.get('arguments', {})
            if isinstance(args, str): args = json.loads(args)
            calls.append({'run_id': str(relative), 'session_id': session, 'call_id': data['callId'],
                          'line': line_no, 'step': data.get('step'), 'tool': data['name'], 'arguments': args})
        elif event['type'] == 'tool/result':
            for block in data.get('message', {}).get('content', []):
                if block.get('type') == 'tool-result':
                    results[block['toolCallId']] = {'result_line': line_no, 'ok': not block.get('isError', False),
                        'text': ''.join(x.get('text', '') for x in block.get('content', []) if x.get('type') == 'text')}
    relevant = []
    for index, call in enumerate(calls):
        if call['tool'] != 'bash': continue
        command = call['arguments'].get('command', '')
        if re.search(r'(?i)(api[_-]?key|authorization:|bearer\s|password\s*=)', command):
            raise ValueError('credential_like_command_excluded')
        entry = {**call, **results.get(call['call_id'], {'ok': False, 'text': '', 'result_line': None}),
                 'events_sha256': hashlib.sha256(raw).hexdigest(),
                 'previous_tools': [x['tool'] for x in calls[max(0, index - 2):index]],
                 'next_tools': [x['tool'] for x in calls[index + 1:index + 3]], 'replay_status': 'unsupported'}
        try:
            if not entry['ok']: raise ValueError('unsuccessful_call')
            source = extract_source(command)
            work = run / 'work'
            if work.is_symlink() or not work.resolve().is_relative_to(run.resolve()): raise ValueError('unsafe_work_directory')
            files = {}
            for name in memory_paths(source):
                path = work / name
                if not path.resolve().is_relative_to(work.resolve()): raise ValueError('memory_file_outside_work')
                files[name] = bounded_read(path, 192000).decode()
            if sum(len(v.encode()) for v in files.values()) > 192000: raise ValueError('source_input_too_large')
            replay = SourceReplay(files).run(source)
            match_kind = stdout_match_kind(entry['text'], replay['stdout'])
            entry.update(replay_status='observed_replay_match', source=source, memory_files=files,
                         file_sha256={k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()},
                         output_labels=list(replay['outputs']), observed_outputs=replay['outputs'],
                         stdout_match_kind=match_kind, replay_normalized_stdout_sha256=hashlib.sha256(normalize_printed_dicts(replay['stdout']).encode()).hexdigest(),
                         observed_stdout_sha256=hashlib.sha256(entry['text'].encode()).hexdigest())
        except (ValueError, KeyError, TypeError, IndexError, SyntaxError, RecursionError) as exc:
            entry['replay_reason'] = str(exc)[:180]
        relevant.append(entry)
    return relevant


def pointer(value, path):
    if not isinstance(path, str) or (path and not path.startswith('/')):
        raise ValueError('json_pointer_required')
    tokens = path.split('/')[1:] if path else []
    def select(current, remaining):
        if not remaining: return current
        key = remaining[0].replace('~1', '/').replace('~0', '~')
        if key in ('__proto__', 'constructor', 'prototype'): raise ValueError('unsafe_pointer')
        if key == '*':
            if not isinstance(current, list) or len(current) > 2000: raise ValueError('bounded_array_wildcard_required')
            return [select(v, remaining[1:]) for v in current]
        return select(current[int(key)] if isinstance(current, list) else current[key], remaining[1:])
    return select(value, tokens)


def project_inputs(files, bindings):
    result = {}
    for name, row in bindings.items():
        value = pointer(parse_json(files[row['file']]), row['pointer'])
        if 'fields' in row:
            if not isinstance(value, list): raise ValueError('fields_requires_array')
            value = [{key: v[key] for key in row['fields']} for v in value]
        result[name] = value
    return result


def project_outputs(outputs, bindings):
    return {name: outputs[label] for name, label in bindings.items()}


def counterfactuals(files):
    """Deterministic independent data mutations, never candidate-produced answers.

    They are same-source counterfactuals, not independent papers. Original AST
    gives every expected output. Unsupported mutations are retained as errors.
    """
    import copy
    values = {k: parse_json(v) for k, v in files.items() if k.endswith('.json')}
    changed = []
    def emit(label, data):
        updated = dict(files)
        updated.update({k: json.dumps(v, ensure_ascii=False) for k, v in data.items()})
        changed.append((label, updated))
    def rename(value, salt):
        if isinstance(value, str):
            if not value: return value
            return '/'.join(salt + hashlib.sha256(x.encode()).hexdigest()[:12] if x else '' for x in value.split('/'))
        if isinstance(value, list): return [rename(x, salt) for x in value]
        if isinstance(value, dict): return {k: rename(v, salt) for k, v in value.items()}
        return value
    for salt in ('newA_', 'newB_', 'newC_', 'newD_'):
        emit('renamed-' + salt, {k: rename(v, salt) for k, v in values.items()})
    for filename, data in values.items():
        if not isinstance(data, dict): continue
        for field, value in data.items():
            if not isinstance(value, list) or not value: continue
            for operation in ('drop-first', 'duplicate-first', 'reverse'):
                copy_values = copy.deepcopy(values)
                target = copy_values[filename][field]
                copy_values[filename][field] = target[1:] if operation == 'drop-first' else target + [copy.deepcopy(target[0])] if operation == 'duplicate-first' else target[::-1]
                emit(filename + ':' + field + ':' + operation, copy_values)
            if isinstance(value[0], dict):
                for key, sample in value[0].items():
                    if not isinstance(sample, (str, list)) or not sample: continue
                    copy_values = copy.deepcopy(values)
                    copy_values[filename][field][0][key] = '' if isinstance(sample, str) else []
                    emit(filename + ':' + field + ':empty:' + key, copy_values)
    return changed
