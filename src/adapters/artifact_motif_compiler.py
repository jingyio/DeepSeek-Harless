"""Offline admission for data-driven programs witnessed in native Agent calls.

Programs remain private. This validator never executes them; certification must
replay them in the namespace sandbox against separate, versioned input files.
The online path reads the resulting versioned library without a Python learner.
"""
import ast
import csv
import hashlib
import io
import json
import re
from pathlib import Path


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))


MODULES = {
    'argparse', 'collections', 'contextlib', 'copy', 'csv', 'html', 'io', 'itertools', 'json',
    'math', 'os', 'os.path', 'pathlib', 're', 'statistics', 'sys', 'textwrap',
    'xml.etree.ElementTree', 'zipfile', 'numpy', 'pandas', 'scipy', 'scipy.stats',
    'matplotlib', 'matplotlib.pyplot', 'matplotlib.font_manager', 'matplotlib.ticker', 'matplotlib.patches',
    'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont',
    '__future__', 'xml.sax.saxutils', 'text_measure', 'preset_shape_svg',
}
FORBIDDEN = {
    'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr', 'delattr',
    'globals', 'locals', 'vars', 'breakpoint', 'input', 'system', 'popen',
    'spawn', 'fork', 'execv', 'execve', 'kill', 'environ', 'getenv',
    'read_pickle', 'to_pickle', 'load_module', 'ctypes', 'urlopen', 'socket',
}


def validate_source(source):
    if not isinstance(source, str) or not 1 <= len(source.encode()) <= 100_000:
        raise ValueError('bounded_program_required')
    tree = ast.parse(source)
    if len(list(ast.walk(tree))) > 12_000:
        raise ValueError('bounded_program_ast_required')
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            if getattr(node, 'level', 0) or any(m not in MODULES for m in modules):
                raise ValueError('program_import_not_admitted')
            if isinstance(node, ast.ImportFrom) and any(a.name == '*' or a.name in FORBIDDEN or a.name.startswith('_') for a in node.names):
                raise ValueError('program_import_symbol_not_admitted')
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN or node.id.startswith('__') and node.id not in ('__name__', '__doc__')):
            raise ValueError('program_name_not_admitted')
        if isinstance(node, ast.Attribute) and (node.attr in FORBIDDEN or node.attr.startswith('_')):
            raise ValueError('program_attribute_not_admitted')
        if isinstance(node, (ast.AsyncFunctionDef, ast.Await)):
            raise ValueError('program_statement_not_admitted')
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.strip() not in ('/', '/opt/geneloop/ppt-master/scripts') and re.match(r'^(?:/|\.\.?/|[A-Za-z]:[\\/]|https?://)', node.value.strip()):
                raise ValueError('program_unbound_external_literal')
    # There must be an explicit current-data interface, not cached slide prose.
    if not any(isinstance(n, ast.Attribute) and n.attr in ('argv', 'parse_args') for n in ast.walk(tree)):
        raise ValueError('program_current_arguments_required')
    return tree


def file_contract(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_000_000:
        raise ValueError('program_fixed_input_required')
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig')
    contract = {'suffix': path.suffix.lower(), 'encoding': 'utf-8'}
    if path.suffix.lower() in ('.csv', '.tsv'):
        dialect = '\t' if path.suffix.lower() == '.tsv' else ','
        rows = csv.reader(io.StringIO(text), delimiter=dialect)
        header = next(rows)
        if not header or len(header) != len(set(header)):
            raise ValueError('program_unique_header_required')
        contract.update(format='delimited', header=header)
    elif path.suffix.lower() == '.json':
        def shape(value, depth=0):
            if isinstance(value, dict):
                return {'object': {k: shape(v, depth + 1) for k, v in sorted(value.items())}} if depth < 2 else 'object'
            if isinstance(value, list):
                return {'array': shape(value[0], depth + 1)} if value and depth < 2 else 'array'
            return 'null' if value is None else 'boolean' if isinstance(value, bool) else 'number' if isinstance(value, (int, float)) else 'string'
        contract.update(format='json', shape=shape(json.loads(text)))
    else:
        contract['format'] = 'text'
    return contract


def program_from_witness(source, arguments, input_paths, output_index, witness):
    tree = validate_source(source)
    if not input_paths or output_index in input_paths or not 0 <= output_index < len(arguments):
        raise ValueError('program_distinct_io_arguments_required')
    if set(input_paths) | {output_index} != set(range(len(arguments))):
        raise ValueError('program_all_arguments_must_be_bound')
    contracts = [{**file_contract(input_paths[i]), 'source_origin': 'uploaded_input' if Path(input_paths[i]).parent.name == 'inputs' else 'model_artifact'} for i in sorted(input_paths)]
    dependencies = {}
    if any(isinstance(n, (ast.Import, ast.ImportFrom)) and any(m in ('text_measure', 'preset_shape_svg') for m in ([n.module] if isinstance(n, ast.ImportFrom) else [a.name for a in n.names])) for n in ast.walk(tree)):
        lock = Path(__file__).resolve().parents[2] / 'scenarios/ppt_master/skill-lock.json'
        dependencies['ppt_master_package_sha256'] = json.loads(lock.read_text(encoding='utf-8'))['package_sha256']
    body = {'version': 1, 'source': source, 'inputs': contracts, 'dependencies': dependencies,
            'input_argument_indices': sorted(input_paths), 'output_argument_index': output_index,
            'argument_count': len(arguments), 'language': 'python',
            'execution_policy': 'fresh_output_network_disabled_v1'}
    interface = ast.get_docstring(tree) or witness.get('description') or 'Witnessed data-driven program'
    if len(interface.encode()) > 16000:
        raise ValueError('artifact_complete_interface_exceeds_protocol_bound')
    return {**body, 'id': 'artifact_' + digest(body)[:24],
            'interface': interface,
            'literal_selectors': sorted({n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and 3 <= len(n.value) <= 1000}),
            'source_sha256': sha(source), 'witness': witness}
