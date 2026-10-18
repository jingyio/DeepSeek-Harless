"""Discover read-only script templates from successful native Bash observations.

Static admission is deliberately conservative; it is NOT a sandbox. Certification
and execution must also use the existing Linux namespace sandbox, with no network
and no persistent writable mounts. No source is executed in this compiler.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re
import shlex
import posixpath

VERSION = 1
IMPORTS = {'json', 're', 'collections', 'pathlib', 'zipfile', 'hashlib', 'math',
           'statistics', 'itertools', 'csv', 'io', 'unicodedata'}
FORBIDDEN = {'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr', 'delattr',
             'globals', 'locals', 'vars', 'input', 'breakpoint', 'exit', 'quit',
             'write', 'writelines', 'write_text', 'write_bytes', 'unlink', 'rename',
             'mkdir', 'rmdir', 'touch', 'extract', 'extractall', 'chdir'}

def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()

def digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))

def extract(command):
    """Accept a single interpreter invocation; never silently discard a pipeline."""
    cwd = '/work'
    prefix = re.match(r'^\s*cd\s+(\S+|\x27[^\x27]+\x27|"[^"]+")\s*&&\s*', command)
    if prefix:
        cwd = shlex.split(prefix.group(1))[0]; command = command[prefix.end():]
    match = re.fullmatch(r"\s*python(?:3)?\s+-\s+<<['\"]?([A-Za-z_]\w*)['\"]?\n(.*?)\n\1\s*", command, re.S)
    if match: return cwd, match.group(2)
    parts = shlex.split(command)
    if len(parts) == 3 and parts[0] in ('python', 'python3') and parts[1] == '-c':
        return cwd, parts[2]
    raise ValueError('single_python_invocation_required')

def compile_script(source, registered_files):
    """registered_files maps exact source literals to bounded input contracts.

    Only paths actually present at the observed tool boundary can become slots.
    Source content and output are never used as a cached answer.
    """
    if len(source.encode()) > 48000: raise ValueError('script_size_limit')
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    if len(nodes) > 4000: raise ValueError('script_ast_limit')
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            if any(m not in IMPORTS for m in modules) or getattr(node, 'level', 0):
                raise ValueError('import_not_admitted')
        if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in FORBIDDEN):
            raise ValueError('attribute_not_admitted:' + node.attr)
        if isinstance(node, ast.Name) and (node.id.startswith(('__', '_sm_')) or node.id in FORBIDDEN):
            raise ValueError('name_not_admitted:' + node.id)
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.Global, ast.Nonlocal)):
            raise ValueError('statement_not_admitted')
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            if name in ('open', 'ZipFile'):
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == 'mode'), ast.Constant('r'))
                if not isinstance(mode, ast.Constant) or mode.value not in ('r', 'rb', 'rt'):
                    raise ValueError('read_mode_required')
    slots = []; paths = []
    class Bind(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str) and node.value in registered_files:
                if node.value not in paths:
                    paths.append(node.value); slots.append(registered_files[node.value])
                return ast.copy_location(ast.Constant('__MOTIF_INPUT_' + str(paths.index(node.value)) + '__'), node)
            return node
    template = ast.unparse(Bind().visit(tree))
    if not slots or len(slots) > 6: raise ValueError('bounded_registered_inputs_required')
    if any('__MOTIF_INPUT_' in n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)):
        raise ValueError('reserved_placeholder')
    # Paths left in a template indicate a missed dependency, not a reusable input.
    for node in ast.walk(ast.parse(template)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.match(r'^(?:/|\.\.?/|[A-Za-z]:\\)', node.value):
                raise ValueError('unbound_path_literal')
    body = {'version': VERSION, 'language': 'python', 'template': template, 'inputs': slots}
    return {**body, 'id': 'script_' + digest(body)[:24], 'source_sha256': sha(source), 'original_paths': paths}

def file_contract(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_000_000:
        raise ValueError('bounded_regular_input_required')
    data = path.read_bytes(); suffix = path.suffix.lower()
    result = {'suffix': suffix, 'format': 'bytes'}
    if suffix == '.json':
        value = json.loads(data)
        def shape(v, depth=0):
            if isinstance(v, dict): return {'object': {k: shape(x, depth+1) for k,x in sorted(v.items())}} if depth < 3 else 'object'
            if isinstance(v, list): return {'array': shape(v[0], depth+1)} if v and depth < 3 else 'array'
            return 'null' if v is None else 'boolean' if isinstance(v,bool) else 'number' if isinstance(v,(int,float)) else 'string'
        result.update(format='json', shape=shape(value))
    elif suffix == '.zip':
        if not data.startswith(b'PK\x03\x04'): raise ValueError('zip_magic_mismatch')
        result['format'] = 'zip'
    else:
        data.decode('utf-8-sig'); result['format'] = 'text'
    return result

def observe(command, description, workspace, stdout, task_id, call_id):
    cwd, source = extract(command); workspace = Path(workspace).resolve()
    cwd = posixpath.normpath(posixpath.join('/work', cwd))
    if cwd != '/work' and not cwd.startswith('/work/'): raise ValueError('workspace_invocation_required')
    files = {}; witnesses = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str): continue
        name = node.value
        if not name or len(name)>1024 or any(c in name for c in ('\x00','\n','\r')) or any(len(p.encode())>255 for p in name.split('/')):continue
        virtual = posixpath.normpath(posixpath.join(cwd,name))
        if not virtual.startswith('/work/'): continue
        relative = virtual.removeprefix('/work/')
        path = workspace / relative if relative.startswith('inputs/') else workspace / 'code' / relative
        try:
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(workspace): continue
        except OSError:continue
        files[name] = file_contract(path)
        witnesses[name] = {'relative': str(path.relative_to(workspace)), 'sha256': sha(path.read_bytes())}
    compiled = compile_script(source, files)
    literals = sorted({n.value for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Constant)
                       and isinstance(n.value,str) and 3<=len(n.value)<=200 and any(c.isalnum() for c in n.value)
                       and n.value not in files})
    outputs=[]
    for n in ast.walk(ast.parse(source)):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='print':
            outputs.extend(a.value for a in n.args if isinstance(a,ast.Constant) and isinstance(a.value,str) and len(a.value)<100)
    semantic='Input format: '+', '.join(c['suffix'] for c in compiled['inputs'])+'. Intent: '+description+'. Observed output labels: '+'; '.join(outputs)
    return {**compiled, 'description': semantic[:1800], 'literal_selectors':literals, 'source': source,
            'witness': {'task_id': task_id, 'call_id': call_id, 'workspace': str(workspace), 'cwd': cwd,
                        'files': witnesses, 'stdout': stdout, 'stdout_sha256': sha(stdout)}}
