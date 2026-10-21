"""Lift bounded pure expressions out of mixed code/data/report scripts.

The outer Bash sequence is not the mining unit. A candidate is a dependency
slice ending at a value consumed later in the observed Python program. It stays
unpublished until source-prefix equivalence and distinct-input sandbox replay.
No generated scientific prose is turned into a reusable answer.
"""
import ast
from .script_motif_compiler import compile_script, digest, observe, extract


def roots(node):
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return {node.id} if isinstance(node, ast.Name) else set()


def literal_result_fields(source, target):
    """Expose literal defaults, not a claim that the corresponding work ran."""
    body = ast.parse(source).body
    assignments = [(i, n) for i, n in enumerate(body) if isinstance(n, ast.Assign)
                   and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == target]
    if not assignments:
        return []
    index, assignment = assignments[-1]
    if any(target in access(n)[1] | access(n)[2] for n in body[index + 1:]):
        return []  # Later updates make a literal initializer insufficient evidence.
    fields = []
    def visit(node, path):
        if isinstance(node, ast.Dict) and all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in node.keys):
            for key, value in zip(node.keys, node.values):
                visit(value, path + '/' + key.value.replace('~', '~0').replace('/', '~1'))
        else:
            try:
                ast.literal_eval(node)
                fields.append(path)
            except (ValueError, TypeError, SyntaxError):
                pass
    visit(assignment.value, '/value')
    return fields[:64]


def access(statement):
    reads = {n.id for n in ast.walk(statement) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    writes = {n.id for n in ast.walk(statement) if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))}
    mutations = set()
    if isinstance(statement, ast.FunctionDef):
        # Only module-level pure functions are admitted below. Locals/parameters
        # do not become global dependencies or overwrite the caller's variables.
        parameters={n.arg for n in ast.walk(statement) if isinstance(n,ast.arg)}
        return reads-writes-parameters-{statement.name}, {statement.name}, set()
    for node in ast.walk(statement):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            mutations |= roots(node.func.value)
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, (ast.Attribute, ast.Subscript)):
                    mutations |= roots(target)
        if isinstance(node, ast.Import):
            writes |= {a.asname or a.name.split('.')[0] for a in node.names}
        if isinstance(node, ast.ImportFrom):
            writes |= {a.asname or a.name for a in node.names}
    return reads, writes, mutations


def slices(source):
    tree = ast.parse(source)
    if any(isinstance(n, (ast.ClassDef, ast.AsyncFunctionDef, ast.Try, ast.With)) for n in ast.walk(tree)):
        return []  # Alias/function/control-effect analysis is not yet certified.
    if any(isinstance(n,ast.FunctionDef) and (n not in tree.body or n.decorator_list or n.args.defaults or any(n.args.kw_defaults)) for n in ast.walk(tree)):
        return []
    result = []
    for end, statement in enumerate(tree.body):
        targets=set()
        if isinstance(statement, ast.Assign) and len(statement.targets)==1 and isinstance(statement.targets[0],ast.Name):
            targets.add(statement.targets[0].id)
        if isinstance(statement,(ast.For,ast.If,ast.AugAssign)):
            targets |= access(statement)[2]
        for target in sorted(targets):
            if not any(isinstance(n, ast.Name) and n.id == target and isinstance(n.ctx, ast.Load)
                       for later in tree.body[end+1:] for n in ast.walk(later)):
                continue
            needed, chosen = {target}, []
            for index in range(end, -1, -1):
                row = tree.body[index]
                reads, writes, mutations = access(row)
                if needed & (writes | mutations):
                    chosen.append(index)
                    needed = (needed - writes) | reads
            if any(isinstance(tree.body[i], (ast.Raise, ast.Assert, ast.Delete)) for i in chosen):
                continue
            # Preserve aliases/functions/loops as complete statements; both
            # prefixes still need static read-only admission and sandbox replay.
            tail = ast.parse('import json as motif_json\nprint(motif_json.dumps({"value": '+target+'}, ensure_ascii=False))').body
            selected = ast.unparse(ast.Module(body=[tree.body[i] for i in sorted(chosen)] + tail, type_ignores=[]))
            original = ast.unparse(ast.Module(body=tree.body[:end+1] + tail, type_ignores=[]))
            result.append({'target': target, 'source': selected, 'prefix_source': original,
                           'lines': sorted({tree.body[i].lineno for i in chosen}),
                           'original_source_sha256': digest(source)})
    return result[-16:]


def observe_slices(command, description, workspace, stdout, task_id, call_id):
    extracted = extract(command, workspace)
    cwd, source = extracted[:2]
    if len(extracted) > 2 and extracted[2]:
        return []  # Explicit argv stays with the existing compiler.
    candidates = []
    original_strings = {n.value for n in ast.walk(ast.parse(source))
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for fragment in slices(source):
        try:
            # Both the selected dependency slice and the original source prefix
            # must pass the existing read-only static admission independently.
            wrap = lambda body: "cd " + cwd + " && python3 - <<'MOTIF_SLICE'\n" + body + '\nMOTIF_SLICE'
            selected = observe(wrap(fragment['source']), description, workspace, stdout, task_id, call_id)
            prefix = observe(wrap(fragment['prefix_source']), description, workspace, stdout, task_id, call_id)
            if selected.get('network_policy') or selected.get('argv_contract'):
                continue
            selected['expression_witness'] = {k:v for k,v in fragment.items() if k != 'source'}
            selected['expression_witness']['prefix_program'] = {k:prefix[k] for k in ('id','version','language','template','inputs')}
            # Compiler-owned JSON envelope labels are not copied task data.
            # Every literal actually present in the original program retains
            # the existing cross-input binding check, even with the same text.
            selected['literal_selectors'] = [s for s in selected['literal_selectors'] if s in original_strings]
            selected['interface']['produces_json'] = {'value': fragment['target']}
            constants = literal_result_fields(fragment['prefix_source'], fragment['target'])
            if constants:
                selected['interface']['literal_output_fields'] = constants
            selected['interface']['input_fields'] = sorted({n.slice.value for n in ast.walk(ast.parse(fragment['source']))
                if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)})
            selected['description'] = 'Read-only dependency slice producing JSON value '+fragment['target']+'; current input fields: '+', '.join(selected['interface']['input_fields'])
            candidates.append(selected)
        except (ValueError, SyntaxError, KeyError, TypeError, OSError):
            continue
    return candidates
