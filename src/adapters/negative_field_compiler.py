"""Lower witnessed validator preconditions to a bounded data-only field IR.

Only unconditional top-level raise guards in a function with no return/yield
are eligible. Unsupported syntax stays a prompt-only candidate. There is no
error-name, manuscript-field or task-specific extraction rule.
"""
import ast
import copy
import inspect
import textwrap
import builtins
from src.adapters.script_motif_compiler import digest


class UnsupportedGuard(ValueError): pass


def lower(node, env):
    if isinstance(node, ast.Name):
        if node.id not in env or env[node.id] is None: raise UnsupportedGuard('unbound_name')
        return copy.deepcopy(env[node.id])
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, bool, type(None))):
        if type(node.value) is int and abs(node.value) > 9007199254740991: raise UnsupportedGuard('integer_precision')
        return {'op': 'const', 'value': node.value}
    if isinstance(node, ast.Subscript):
        key = lower(node.slice, env)
        if key['op'] != 'const' or not isinstance(key['value'], str): raise UnsupportedGuard('dynamic_key')
        return {'op': 'get', 'base': lower(node.value, env), 'key': key['value']}
    if isinstance(node, ast.ListComp) and len(node.generators) == 1:
        gen = node.generators[0]
        if gen.ifs or gen.is_async or not isinstance(gen.target, ast.Name): raise UnsupportedGuard('conditional_map')
        if any(isinstance(n, (ast.ListComp, ast.GeneratorExp)) for n in ast.walk(node.elt)): raise UnsupportedGuard('nested_map_scope')
        return {'op': 'map', 'input': lower(gen.iter, env),
                'body': lower(node.elt, {**env, gen.target.id: {'op': 'item'}})}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('len', 'set') and len(node.args) == 1 and not node.keywords:
        return {'op': node.func.id, 'value': lower(node.args[0], env)}
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        op = {ast.Eq: 'eq', ast.NotEq: 'ne', ast.Lt: 'lt', ast.LtE: 'le', ast.Gt: 'gt', ast.GtE: 'ge'}.get(type(node.ops[0]))
        if op: return {'op': 'compare', 'cmp': op, 'left': lower(node.left, env), 'right': lower(node.comparators[0], env)}
    raise UnsupportedGuard('unsupported_guard_syntax')


def field_paths(expr, item=None):
    def path(node, context):
        if node['op'] == 'root': return []
        if node['op'] == 'item' and context is not None: return context
        if node['op'] == 'get': return [*path(node['base'], context), node['key']]
        raise UnsupportedGuard('computed_field_path')
    op = expr['op']
    if op == 'get': return [path(expr, item)]
    if op == 'map': return field_paths(expr['body'], [*path(expr['input'], item), '*'])
    if op in ('len', 'set'): return field_paths(expr['value'], item)
    if op == 'compare': return field_paths(expr['left'], item) + field_paths(expr['right'], item)
    return []


def extract_guards(source, function_name):
    tree = ast.parse(textwrap.dedent(source))
    function = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function_name), None)
    if function is None or len(function.args.args) != 1 or any(isinstance(n, (ast.Return, ast.Yield, ast.YieldFrom)) for n in ast.walk(function)):
        raise UnsupportedGuard('non_conjunctive_validator')
    if any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id in ('len', 'set', 'ValueError') for n in ast.walk(function)):
        raise UnsupportedGuard('shadowed_local_builtin')
    if any(isinstance(n, (ast.AugAssign, ast.Delete)) or
           isinstance(n, (ast.Subscript, ast.Attribute)) and isinstance(n.ctx, ast.Store) or
           isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr not in ('keys', 'values', 'items', 'get')
           for n in ast.walk(function)):
        raise UnsupportedGuard('validator_mutation_or_unknown_method')
    env = {function.args.args[0].arg: {'op': 'root'}}
    guards = {}
    for statement in function.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            try:
                if isinstance(target, ast.Name): env[target.id] = lower(statement.value, env)
                elif isinstance(target, ast.Tuple) and isinstance(statement.value, ast.GeneratorExp):
                    gen = statement.value.generators[0]
                    if len(statement.value.generators) != 1 or gen.ifs or gen.is_async or not isinstance(gen.target, ast.Name) or not isinstance(gen.iter, (ast.Tuple, ast.List)) or len(gen.iter.elts) != len(target.elts):
                        raise UnsupportedGuard('unpack_not_static')
                    values = [lower(statement.value.elt, {**env, gen.target.id: lower(v, env)}) for v in gen.iter.elts]
                    for name, value in zip(target.elts, values):
                        if not isinstance(name, ast.Name): raise UnsupportedGuard('unpack_target')
                        env[name.id] = value
            except UnsupportedGuard:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name): env[name.id] = None
        else:
            # A name assigned in an unsupported control block cannot retain an
            # earlier alias. Never silently compile a stale def-use chain.
            for node in ast.walk(statement):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store): env[node.id] = None
        if not isinstance(statement, ast.If) or statement.orelse or len(statement.body) != 1 or not isinstance(statement.body[0], ast.Raise): continue
        exception = statement.body[0].exc
        if not isinstance(exception, ast.Call) or not isinstance(exception.func, ast.Name) or exception.func.id != 'ValueError' or len(exception.args) != 1 or not isinstance(exception.args[0], ast.Constant) or not isinstance(exception.args[0].value, str): continue
        try:
            predicate = lower(statement.test, env)
            paths = sorted({tuple(p) for p in field_paths(predicate)})
            if paths: guards[exception.args[0].value] = {'predicate': predicate, 'read_paths': [list(p) for p in paths]}
        except UnsupportedGuard: pass
    return guards


def evaluate(expr, root, item=None):
    op = expr['op']
    if op == 'root': return root
    if op == 'item': return item
    if op == 'const': return expr['value']
    if op == 'get':
        base = evaluate(expr['base'], root, item)
        if not isinstance(base, dict): raise UnsupportedGuard('object_required')
        return base[expr['key']]
    if op == 'map':
        value = evaluate(expr['input'], root, item)
        if not isinstance(value, list) or len(value) > 10000: raise UnsupportedGuard('bounded_array_required')
        return [evaluate(expr['body'], root, v) for v in value]
    if op in ('len', 'set'):
        value = evaluate(expr['value'], root, item)
        if op == 'set':
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value): raise UnsupportedGuard('string_set_required')
            return list(set(value))
        if not isinstance(value, (str, list)): raise UnsupportedGuard('length_type')
        return len(value)
    if op == 'compare':
        a, b = evaluate(expr['left'], root, item), evaluate(expr['right'], root, item)
        if type(a) is not int or type(b) is not int: raise UnsupportedGuard('integer_compare_required')
        return {'eq': a == b, 'ne': a != b, 'lt': a < b, 'le': a <= b, 'gt': a > b, 'ge': a >= b}[expr['cmp']]
    raise UnsupportedGuard('unknown_op')


def certify_field_guard(function, code, states, contrasts):
    if any(function.__globals__.get(name, getattr(builtins, name)) is not getattr(builtins, name) for name in ('len', 'set', 'ValueError')):
        raise UnsupportedGuard('shadowed_builtin')
    extracted = extract_guards(inspect.getsource(function), function.__name__).get(code)
    if not extracted: raise UnsupportedGuard('no_supported_failure_slice')
    def outcome(value):
        try: function(value); return None
        except ValueError as error: return str(error)
    candidates = []
    def visit(value, path=(), depth=0):
        if isinstance(value, dict):
            try:
                if evaluate(extracted['predicate'], value) is True and outcome(value) == code: candidates.append((list(path), value))
            except (ValueError, KeyError, TypeError): pass
            if depth < 3:
                for key, child in value.items():
                    if isinstance(child, dict): visit(child, (*path, key), depth + 1)
    for state in states: visit(state)
    roots = {tuple(path) for path, _ in candidates}
    if len(roots) != 1: raise UnsupportedGuard('ambiguous_or_missing_state_root')
    positives = []
    for value in contrasts:
        if outcome(value) is None and evaluate(extracted['predicate'], value) is False: positives.append(digest(value))
    if not positives: raise UnsupportedGuard('no_successful_contrast')
    outside = []
    # Independently replay harmless type-preserving edits outside the slice.
    # This is a diagnostic intervention, not a new real task or semantic repair.
    sample = candidates[0][1]
    def edits(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items(): yield from edits(child, (*path, key))
        elif isinstance(value, list):
            for i, child in enumerate(value[:4]): yield from edits(child, (*path, i))
        elif isinstance(value, str): yield path
    for path in list(edits(sample))[:256]:
        related = any(len(path) >= len(p) and all(k == '*' or k == str(v) for k, v in zip(p, path)) for p in extracted['read_paths'])
        if related: continue
        changed = copy.deepcopy(sample);parent = changed
        for key in path[:-1]: parent = parent[key]
        parent[path[-1]] += ' '
        if outcome(changed) == code and evaluate(extracted['predicate'], changed) is True: outside.append(list(path))
        if len(outside) >= 8: break
    if len(outside) < 2: raise UnsupportedGuard('insufficient_unrelated_interventions')
    return {'version': 1, **extracted, 'state_root': list(next(iter(roots))),
            'certification': {'scope': 'source_sliced_required_precondition_with_real_state_and_local_interventions',
                'failure_state_sha256': [digest(v) for _, v in candidates], 'success_state_sha256': positives,
                'unrelated_edit_paths': outside, 'model_requests': 0}}
