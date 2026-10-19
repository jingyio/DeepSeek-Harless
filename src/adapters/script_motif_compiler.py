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
           'statistics', 'itertools', 'csv', 'io', 'unicodedata', 'sys',
           'urllib.request', 'urllib.parse', 'xml.etree.ElementTree', 'time'}
FORBIDDEN = {'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr', 'delattr',
             'globals', 'locals', 'vars', 'input', 'breakpoint', 'exit', 'quit',
             'write', 'writelines', 'write_text', 'write_bytes', 'unlink', 'rename',
             'mkdir', 'rmdir', 'touch', 'extract', 'extractall', 'chdir'}

def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()

def digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))

def virtual_host(workspace, virtual):
    if not virtual.startswith('/work/'):
        raise ValueError('script_outside_workspace')
    relative = virtual.removeprefix('/work/')
    if relative.startswith('inputs/'):
        return Path(workspace) / relative
    if relative.startswith('outputs/'):
        return Path(workspace) / 'outputs/code' / relative.removeprefix('outputs/')
    return Path(workspace) / 'code' / relative


def extract(command, workspace=None):
    """Accept a single interpreter invocation; never silently discard a pipeline."""
    cwd = '/work'
    prefix = re.match(r'^\s*cd\s+(\S+|\x27[^\x27]+\x27|"[^"]+")\s*&&\s*', command)
    if prefix:
        cwd = shlex.split(prefix.group(1))[0]; command = command[prefix.end():]
    # A real Agent often saves code and invokes it later. Admit only an exact
    # single-file heredoc followed by that interpreter call, never arbitrary shell.
    saved = re.fullmatch(r"cat\s*>\s*(\S+)\s*<<['\"]?(\w+)['\"]?\n(.*?)\n\2\n(python3?\s+[^\n]+)", command.strip(), re.S)
    declared = None
    if saved:
        declared = (saved.group(1), saved.group(3))
        command = saved.group(4)
    match = re.fullmatch(r"\s*python(?:3)?\s+(?:-\s*)?<<\s*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_]\w*)(?P=quote)[ \t]*\n(?P<body>.*?)\n(?P=delimiter)[ \t]*\s*", command, re.S)
    if match:
        source=match.group('body')
        if not match.group('quote') and re.search(r"[$`\\]",source):
            raise ValueError('script_heredoc_expansion_requires_evidence')
        return cwd, source
    parts = shlex.split(command)
    if len(parts) == 3 and parts[0] in ('python', 'python3') and parts[1] == '-c':
        return cwd, parts[2]
    if workspace and len(parts)>=2 and parts[0] in ('python','python3') and parts[1].endswith('.py'):
        if any(p in {'|',';','&&','||','>','2>&1'} for p in parts):
            raise ValueError('script_pipeline_requires_separate_evidence')
        virtual = posixpath.normpath(posixpath.join(cwd,parts[1]))
        if not virtual.startswith('/work/'): raise ValueError('script_outside_workspace')
        path = virtual_host(workspace, virtual)
        if path.is_symlink() or not path.resolve().is_relative_to(Path(workspace).resolve()):
            raise ValueError('script_source_not_fixed')
        source = path.read_text()
        if declared and (declared[0]!=parts[1] or source.strip()!=declared[1].strip()):
            raise ValueError('saved_source_changed')
        return cwd, source, parts[2:], sha(source)
    raise ValueError('single_python_invocation_required')

def compile_script(source, registered_files, *, argv=None):
    """registered_files maps exact source literals to bounded input contracts.

    Only paths actually present at the observed tool boundary can become slots.
    Source content and output are never used as a cached answer.
    """
    if len(source.encode()) > 48000: raise ValueError('script_size_limit')
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    sys_names = {a.asname or a.name for n in nodes if isinstance(n,ast.Import) for a in n.names if a.name=='sys'}
    if len(nodes) > 4000: raise ValueError('script_ast_limit')
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            if any(m not in IMPORTS for m in modules) or getattr(node, 'level', 0):
                raise ValueError('import_not_admitted')
        if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in FORBIDDEN):
            raise ValueError('attribute_not_admitted:' + node.attr)
        if isinstance(node, ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id in sys_names and node.attr!='argv':
            raise ValueError('only_sys_argv_is_admitted')
        if isinstance(node,(ast.Assign,ast.AugAssign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            if any(isinstance(t,ast.Attribute) for t in targets):raise ValueError('attribute_mutation_not_admitted')
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
    uses_argv = any(isinstance(n,ast.Attribute) and n.attr=='argv' and isinstance(n.value,ast.Name) and n.value.id in sys_names for n in nodes)
    if (not slots and not (argv and uses_argv)) or len(slots) > 6: raise ValueError('bounded_registered_inputs_required')
    if any('__MOTIF_INPUT_' in n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)):
        raise ValueError('reserved_placeholder')
    # Paths left in a template indicate a missed dependency, not a reusable input.
    for node in ast.walk(ast.parse(template)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.match(r'^(?:/|\.\.?/|[A-Za-z]:\\)', node.value):
                raise ValueError('unbound_path_literal')
    body = {'version': VERSION, 'language': 'python', 'template': template, 'inputs': slots}
    if argv and uses_argv:
        if len(argv)>32 or any(not a or len(a)>256 or a.startswith(('/', '..')) or any(c in a for c in '\n\r\x00') for a in argv):
            raise ValueError('bounded_scalar_arguments_required')
        body['argv_contract']={'max_items':32,'max_chars':256,'kind':'explicit_model_selected_scalars'}
    network = any(isinstance(n,ast.Import) and any(a.name=='urllib.request' for a in n.names) for n in nodes)
    if network:
        # Network stays disabled in the child. The replay driver only serves
        # bounded GETs to the existing metadata services, never arbitrary URLs.
        body['network_policy']='fixed_metadata_get_v1'
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
    extracted = extract(command,workspace)
    cwd,source = extracted[:2]; argv=extracted[2] if len(extracted)>2 else None
    workspace = Path(workspace).resolve()
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
        path = virtual_host(workspace, virtual)
        try:
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(workspace): continue
        except OSError:continue
        files[name] = file_contract(path)
        witnesses[name] = {'relative': str(path.relative_to(workspace)), 'sha256': sha(path.read_bytes())}
    compiled = compile_script(source, files,argv=argv)
    literals = sorted({n.value for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Constant)
                       and isinstance(n.value,str) and 3<=len(n.value)<=200 and any(c.isalnum() for c in n.value)
                       and n.value not in files})
    outputs=[]
    for n in ast.walk(ast.parse(source)):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='print':
            outputs.extend(a.value for a in n.args if isinstance(a,ast.Constant) and isinstance(a.value,str) and len(a.value)<100)
    tree=ast.parse(source)
    modules=sorted({a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}|{n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)})
    variables=sorted({target.id for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Attribute) and x.attr=='argv' for x in ast.walk(n.value)) for target in n.targets if isinstance(target,ast.Name)})
    interface={'language':'python','imports':modules,'stdout_labels':outputs,
               'argv_variables':variables,'url_literals':sorted({n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith(('https://','http://'))})}
    semantic='Input format: '+', '.join(c['suffix'] for c in compiled['inputs'])+'. Intent: '+description+'. Observed output labels: '+'; '.join(outputs)
    return {**compiled, 'interface':interface, 'description': semantic[:1800], 'literal_selectors':literals, 'source': source, 'observed_argv':argv,
            'witness': {'task_id': task_id, 'call_id': call_id, 'workspace': str(workspace), 'cwd': cwd,
                        'files': witnesses, 'stdout': stdout, 'stdout_sha256': sha(stdout)}}
