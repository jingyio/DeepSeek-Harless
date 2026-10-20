"""Compile reviewed read-only validation branches, then test their causes.

This is bounded source-assisted dependency learning, not black-box causality.
Unsupported control flow remains a fallback; there are no domain/error rules.
"""
import ast
import builtins
import copy
import inspect
import textwrap
from pathlib import Path
from src.adapters.script_motif_compiler import digest


class UnsupportedGuard(ValueError): pass


BUILTINS = ('len', 'set', 'list', 'tuple', 'range', 'any', 'all', 'type', 'isinstance', 'str', 'int', 'bool', 'dict', 'ValueError')
MISSING = object()


def literal_constants(tree):
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try: constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError): pass
    return constants


def data_expr(value):
    if type(value) in (str, int, bool, type(None)):
        if type(value) is int and abs(value) > 9007199254740991: raise UnsupportedGuard('integer_precision')
        return {'op': 'const', 'value': value}
    if isinstance(value, (list, tuple)) and len(value) <= 10000:
        return {'op': 'array', 'kind': 'tuple' if isinstance(value, tuple) else 'list', 'values': [data_expr(v) for v in value]}
    raise UnsupportedGuard('nonliteral_constant')


class Lowerer:
    def __init__(self, constants):
        self.constants = constants
        self.used_constants = set()
        self.serial = 0

    def variable(self):
        self.serial += 1
        return 'v' + str(self.serial)

    def constant(self, node, env):
        # Resolve only source literals/static aliases, never invoke user code.
        if isinstance(node, ast.Name) and node.id in self.constants and node.id not in env:
            self.used_constants.add(node.id)
            return self.constants[node.id]
        if isinstance(node, ast.Subscript):
            value = self.constant(node.value, env)
            key = self.constant(node.slice, env)
            try: return value[key]
            except (KeyError, TypeError, IndexError): raise UnsupportedGuard('constant_lookup')
        if isinstance(node, ast.Name):
            expr = env.get(node.id)
            if expr and expr['op'] == 'const': return expr['value']
            if expr and expr['op'] == 'array': return evaluate(expr, {})
            raise UnsupportedGuard('nonconstant_alias')
        try: return ast.literal_eval(node)
        except (ValueError, TypeError): raise UnsupportedGuard('nonconstant')

    def lower(self, node, env):
        if isinstance(node, ast.Name):
            if node.id in env:
                if env[node.id] is None: raise UnsupportedGuard('unbound_name')
                return copy.deepcopy(env[node.id])
            return data_expr(self.constant(node, env))
        if isinstance(node, ast.Constant): return data_expr(node.value)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            expr = {'op': 'array', 'kind': 'tuple' if isinstance(node, ast.Tuple) else 'list', 'values': [self.lower(n, env) for n in node.elts]}
            return {'op': 'set', 'value': expr} if isinstance(node, ast.Set) else expr
        if isinstance(node, ast.Subscript):
            try: return data_expr(self.constant(node, env))
            except UnsupportedGuard: pass
            key = self.constant(node.slice, env)
            if not isinstance(key, str): raise UnsupportedGuard('dynamic_key')
            return {'op': 'get', 'base': self.lower(node.value, env), 'key': key}
        if isinstance(node, ast.BoolOp):
            return {'op': 'bool', 'mode': 'and' if isinstance(node.op, ast.And) else 'or', 'values': [self.lower(v, env) for v in node.values]}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not): return {'op': 'not', 'value': self.lower(node.operand, env)}
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            return {'op': 'arithmetic', 'mode': 'add' if isinstance(node.op, ast.Add) else 'sub', 'left': self.lower(node.left, env), 'right': self.lower(node.right, env)}
        if isinstance(node, ast.GeneratorExp): raise UnsupportedGuard('generator_requires_immediate_aggregate')
        if isinstance(node, (ast.ListComp, ast.SetComp)):
            if len(node.generators) != 1: raise UnsupportedGuard('multiple_generator')
            gen = node.generators[0]
            if gen.ifs or gen.is_async or not isinstance(gen.target, ast.Name): raise UnsupportedGuard('conditional_generator')
            iterable = self.lower(gen.iter, env)
            if iterable['op'] == 'array' and len(iterable['values']) <= 32:
                expr = {'op': 'array', 'values': [self.lower(node.elt, {**env, gen.target.id: v}) for v in iterable['values']]}
                return {'op': 'set', 'value': expr} if isinstance(node, ast.SetComp) else expr
            slot = self.variable()
            expr = {'op': 'map', 'binding': slot, 'input': self.lower(gen.iter, env), 'body': self.lower(node.elt, {**env, gen.target.id: {'op': 'var', 'name': slot}})}
            return {'op': 'set', 'value': expr} if isinstance(node, ast.SetComp) else expr
        if isinstance(node, ast.Call) and not node.keywords:
            if isinstance(node.func, ast.Attribute) and node.func.attr in ('keys', 'get'):
                base = self.lower(node.func.value, env)
                if node.func.attr == 'keys' and not node.args: return {'op': 'keys', 'value': base}
                if node.func.attr == 'get' and 1 <= len(node.args) <= 2:
                    key = self.constant(node.args[0], env)
                    if not isinstance(key, str): raise UnsupportedGuard('dynamic_key')
                    return {'op': 'get_default', 'base': base, 'key': key, 'default': self.lower(node.args[1], env) if len(node.args) == 2 else data_expr(None)}
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in ('len', 'set', 'any', 'all', 'list', 'tuple') and len(node.args) == 1:
                    arg = node.args[0]
                    if isinstance(arg, ast.GeneratorExp) and name != 'len': arg = ast.ListComp(elt=arg.elt, generators=arg.generators)
                    value = self.lower(arg, env)
                    if name in ('list', 'tuple'):
                        if value['op'] == 'array': return {**value, 'kind': name}
                        return {'op': 'sequence', 'kind': name, 'value': value}
                    return {'op': name, 'value': value}
                if name == 'range' and 1 <= len(node.args) <= 3: return {'op': 'range', 'values': [self.lower(v, env) for v in node.args]}
                if name == 'isinstance' and len(node.args) == 2 and isinstance(node.args[1], ast.Name) and node.args[1].id in ('str', 'bool', 'list', 'dict'):
                    return {'op': 'is_type', 'kind': node.args[1].id, 'value': self.lower(node.args[0], env)}
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            # JSON does not preserve Python int-vs-float identity: don't guess.
            op = {ast.Eq: 'eq', ast.NotEq: 'ne', ast.Lt: 'lt', ast.LtE: 'le', ast.Gt: 'gt', ast.GtE: 'ge', ast.In: 'in', ast.NotIn: 'not_in'}.get(type(node.ops[0]))
            if op: return {'op': 'compare', 'cmp': op, 'left': self.lower(node.left, env), 'right': self.lower(node.comparators[0], env)}
        raise UnsupportedGuard('unsupported_guard_syntax')


def field_paths(expr, variables=None):
    variables = variables or {}
    def path(node):
        if node['op'] == 'root': return []
        if node['op'] == 'item' and '__item' in variables: return variables['__item']
        if node['op'] == 'var' and node['name'] in variables: return variables[node['name']]
        if node['op'] in ('get', 'get_default'): return [*path(node['base']), node['key']]
        raise UnsupportedGuard('computed_field_path')
    op = expr['op']
    if op in ('root', 'var', 'item', 'get'): return [path(expr)]
    if op == 'get_default': return [path(expr)] + field_paths(expr['default'], variables)
    if op in ('map', 'exists'):
        context = [*path(expr['input']), '*']
        result = field_paths(expr['body'], {**variables, expr.get('binding', '__item'): context})
        # Iteration over an empty array is itself relevant to a quantified test.
        return result or [path(expr['input'])]
    if op in ('len', 'set', 'any', 'all', 'not', 'keys', 'is_type', 'sequence'): return field_paths(expr['value'], variables)
    if op in ('compare', 'arithmetic'): return field_paths(expr['left'], variables) + field_paths(expr['right'], variables)
    if op in ('bool', 'array', 'range'): return [p for n in expr['values'] for p in field_paths(n, variables)]
    return []


def extract_guards(source, function_name, constants=None):
    tree = ast.parse(textwrap.dedent(source))
    function = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function_name), None)
    if function is None or len(function.args.args) != 1 or function.args.vararg or function.args.kwarg:
        raise UnsupportedGuard('one_argument_validator_required')
    for n in ast.walk(function):
        if isinstance(n, (ast.Return, ast.Yield, ast.YieldFrom, ast.Break, ast.Continue, ast.Try, getattr(ast, 'TryStar', ast.Try), ast.AsyncFor, ast.While, ast.Global, ast.Nonlocal, ast.NamedExpr)):
            raise UnsupportedGuard('unsupported_control_flow')
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id in BUILTINS: raise UnsupportedGuard('shadowed_local_builtin')
        if isinstance(n, (ast.AugAssign, ast.Delete, ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)) and n is not function:
            raise UnsupportedGuard('validator_mutation_or_unknown_binding')
        if isinstance(n, (ast.Subscript, ast.Attribute)) and isinstance(n.ctx, ast.Store): raise UnsupportedGuard('validator_mutation')
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr not in ('keys', 'values', 'items', 'get'):
            raise UnsupportedGuard('validator_mutation_or_unknown_method')
    lowerer = Lowerer({**literal_constants(tree), **(constants or {})})
    lower = lowerer.lower

    def combine(mode, expressions):
        return expressions[0] if len(expressions) == 1 else {'op': 'bool', 'mode': mode, 'values': expressions}

    def bind(target, value, env):
        if isinstance(target, ast.Name): env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)) and value['op'] == 'array' and len(target.elts) == len(value['values']):
            for t, v in zip(target.elts, value['values']): bind(t, v, env)
        else: raise UnsupportedGuard('unpack_not_static')

    def invalidate(statement, env):
        for n in ast.walk(statement):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store): env[n.id] = None

    def walk(statements, incoming):
        env = copy.deepcopy(incoming); found = {}
        def add(code, predicate): found.setdefault(code, []).append(predicate)
        for statement in statements:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                try:
                    value = statement.value
                    # Python's tuple-unpack generator can be statically expanded.
                    if isinstance(statement.targets[0], ast.Tuple) and isinstance(value, ast.GeneratorExp) and len(value.generators) == 1:
                        gen = value.generators[0]
                        iterable = lower(gen.iter, env)
                        if gen.ifs or gen.is_async or not isinstance(gen.target, ast.Name) or iterable['op'] != 'array' or len(iterable['values']) > 32: raise UnsupportedGuard('unpack_not_static')
                        value = {'op': 'array', 'values': [lower(value.elt, {**env, gen.target.id: item}) for item in iterable['values']]}
                    else: value = lower(value, env)
                    bind(statement.targets[0], value, env)
                except UnsupportedGuard: invalidate(statement, env)
            elif isinstance(statement, ast.If):
                try:
                    condition = lower(statement.test, env)
                    for code, pred in walk(statement.body, env).items(): add(code, combine('and', [condition, pred]))
                    for code, pred in walk(statement.orelse, env).items(): add(code, combine('and', [{'op': 'not', 'value': condition}, pred]))
                except UnsupportedGuard: pass
                invalidate(statement, env)
            elif isinstance(statement, ast.For):
                try:
                    if statement.orelse: raise UnsupportedGuard('loop_else')
                    iterable = lower(statement.iter, env)
                    if iterable['op'] == 'array':
                        if len(iterable['values']) > 32: raise UnsupportedGuard('static_loop_limit')
                        for value in iterable['values']:
                            local = {**env};bind(statement.target, value, local)
                            for code, pred in walk(statement.body, local).items(): add(code, pred)
                    elif isinstance(statement.target, ast.Name):
                        slot = lowerer.variable()
                        for code, pred in walk(statement.body, {**env, statement.target.id: {'op': 'var', 'name': slot}}).items():
                            add(code, {'op': 'exists', 'binding': slot, 'input': iterable, 'body': pred})
                except UnsupportedGuard: pass
                invalidate(statement, env)
            elif isinstance(statement, ast.Raise):
                exc = statement.exc
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == 'ValueError' and len(exc.args) == 1 and not exc.keywords and isinstance(exc.args[0], ast.Constant) and isinstance(exc.args[0].value, str): add(exc.args[0].value, data_expr(True))
            else: invalidate(statement, env)
        return {code: combine('or', predicates) for code, predicates in found.items()}

    guards = {}
    for code, predicate in walk(function.body, {function.args.args[0].arg: {'op': 'root'}}).items():
        try:
            paths = sorted({tuple(p) for p in field_paths(predicate)})
            if paths: guards[code] = {'predicate': predicate, 'read_paths': [list(p) for p in paths]}
        except UnsupportedGuard: pass
    return guards


def evaluate(expr, root, item=None):
    """Reference evaluator; same fail-open data subset and limits as TS."""
    steps = 0
    def run(n, variables):
        nonlocal steps
        steps += 1
        if steps > 100000: raise UnsupportedGuard('step_limit')
        op = n['op']
        if op == 'root': return root
        if op == 'item': return item
        if op == 'var': return variables[n['name']]
        if op == 'const': return n['value']
        if op == 'array':
            values = [run(v, variables) for v in n['values']]
            return tuple(values) if n.get('kind') == 'tuple' else values
        if op == 'sequence':
            value = run(n['value'], variables)
            if not isinstance(value, (list, tuple, range)): raise UnsupportedGuard('sequence_type')
            return (tuple if n['kind'] == 'tuple' else list)(value)
        if op in ('get', 'get_default'):
            base = run(n['base'], variables)
            if not isinstance(base, dict): raise UnsupportedGuard('object_required')
            if op == 'get_default' and n['key'] not in base: return run(n['default'], variables)
            return base[n['key']]
        if op in ('map', 'exists'):
            values = run(n['input'], variables)
            if not isinstance(values, (list, tuple, range)) or len(values) > 10000: raise UnsupportedGuard('bounded_array_required')
            if op == 'exists': return any(run(n['body'], {**variables, n['binding']: v}) for v in values)
            return [run(n['body'], {**variables, n.get('binding', '__item'): v}) for v in values]
        if op == 'bool':
            result = True if n['mode'] == 'and' else False
            for child in n['values']:
                result = run(child, variables)
                if bool(result) == (n['mode'] == 'or'): break
            return result
        if op in ('len', 'set', 'any', 'all', 'not', 'keys', 'is_type'):
            value = run(n['value'], variables)
            if op == 'not': return not value
            if op == 'keys':
                if not isinstance(value, dict): raise UnsupportedGuard('object_required')
                return frozenset(value)
            if op == 'is_type': return type(value) is {'str': str, 'list': list, 'dict': dict, 'bool': bool}[n['kind']]
            if op == 'len':
                if not isinstance(value, (str, list, tuple, range, frozenset)): raise UnsupportedGuard('length_type')
                return len(value)
            if op == 'set' and isinstance(value, frozenset): return value
            if not isinstance(value, (list, tuple, range)): raise UnsupportedGuard('array_required')
            if op in ('any', 'all'): return (any if op == 'any' else all)(value)
            if any(not isinstance(v, str) for v in value): raise UnsupportedGuard('string_set_required')
            return frozenset(value)
        if op == 'range':
            args = [run(v, variables) for v in n['values']]
            if any(type(v) is not int or abs(v) > 10000 for v in args): raise UnsupportedGuard('range_bounds')
            result = range(*args)
            if len(result) > 10000: raise UnsupportedGuard('range_bounds')
            return result
        if op in ('compare', 'arithmetic'):
            a, b = run(n['left'], variables), run(n['right'], variables)
            if op == 'arithmetic':
                if type(a) is not int or type(b) is not int: raise UnsupportedGuard('integer_arithmetic')
                result = a + b if n['mode'] == 'add' else a - b
                if abs(result) > 9007199254740991: raise UnsupportedGuard('integer_precision')
                return result
            cmp = n['cmp']
            if cmp in ('in', 'not_in'):
                if not isinstance(a, str) or not isinstance(b, (list, tuple, frozenset)) or any(not isinstance(v, str) for v in b): raise UnsupportedGuard('membership_type')
                return (a in b) if cmp == 'in' else (a not in b)
            if cmp in ('eq', 'ne'):
                # Reject the Python bool/int cross-type equivalence ambiguity.
                if type(a) is not type(b): raise UnsupportedGuard('comparison_type')
                return (a == b) if cmp == 'eq' else (a != b)
            if isinstance(a, frozenset) and isinstance(b, frozenset): pass
            elif type(a) is not int or type(b) is not int: raise UnsupportedGuard('ordered_compare_type')
            return {'lt': lambda: a < b, 'le': lambda: a <= b, 'gt': lambda: a > b, 'ge': lambda: a >= b}[cmp]()
        raise UnsupportedGuard('unknown_op')
    return run(expr, {})


def _at(value, path):
    for key in path:
        try: value = value[key]
        except (KeyError, IndexError, TypeError): return MISSING
    return value


def _locations(value, pattern, path=()):
    if not pattern: return [path]
    key, *rest = pattern
    if key == '*':
        if not isinstance(value, list): return []
        return [p for i, v in enumerate(value[:256]) for p in _locations(v, rest, (*path, i))]
    child = value.get(key, MISSING) if isinstance(value, dict) else MISSING
    if not rest: return [(*path, key)]
    return _locations(child, rest, (*path, key))


def _changed(value, patches):
    result = copy.deepcopy(value)
    for path, replacement in patches:
        if not path: return MISSING
        parent = _at(result, path[:-1]);key = path[-1]
        if isinstance(parent, dict):
            if replacement is MISSING: parent.pop(key, None)
            else: parent[key] = copy.deepcopy(replacement)
        elif isinstance(parent, list) and isinstance(key, int) and key < len(parent) and replacement is not MISSING: parent[key] = copy.deepcopy(replacement)
        else: return MISSING
    return result


def cause_interventions(predicate, paths, failed, successes, outcome, code):
    """Contrast-derived two-way interventions; copies only, no task writes."""
    calls = 0
    def valid(patches, start, reintroduce):
        nonlocal calls
        if calls >= 96: return None
        changed = _changed(start, patches)
        if changed is MISSING: return None
        try:
            holds = evaluate(predicate, changed)
            if holds is not reintroduce: return None
            calls += 1
            error = outcome(changed)
            if (error == code) if reintroduce else (error != code):
                return {'changed_state_sha256': digest(changed), 'result_error': error, 'whole_validator_passed': error is None}
        except (ValueError, KeyError, TypeError): pass
        return None
    def minimize(patches, start, mode):
        begin = calls
        if not patches: return None
        result = valid(patches, start, mode)
        if result is None: return None
        selected = patches[:]
        granularity = 2
        while len(selected) > 1 and calls < 96 and calls - begin < 24:
            size = (len(selected) + granularity - 1) // granularity
            reduced = False
            for offset in range(0, len(selected), size):
                if calls >= 96 or calls - begin >= 24: break
                candidate = selected[:offset] + selected[offset + size:]
                if not candidate: continue
                tested = valid(candidate, start, mode)
                if tested is not None:
                    selected, result, reduced = candidate, tested, True
                    granularity = max(2, granularity - 1);break
            if not reduced:
                if granularity >= len(selected): break
                granularity = min(len(selected), granularity * 2)
        return {**result, 'base_state_sha256': digest(start), 'changed_paths': [list(p) for p, _ in selected], 'minimality': 'bounded_delta_debugging_not_global_minimum'}
    for success in successes[:4]:
        locations = sorted({p for pattern in paths for state in (failed, success) for p in _locations(state, pattern)}, key=str)
        if not locations or len(locations) > 256: continue
        # Different papers can have different row counts. Only transplant into
        # existing parents; do not create/delete records to force a contrast.
        def applicable(value, path):
            parent = _at(value, path[:-1]);key = path[-1]
            return isinstance(parent, dict) or isinstance(parent, list) and isinstance(key, int) and key < len(parent)
        differing = [p for p in locations if p and applicable(failed, p) and applicable(success, p) and _at(failed, p) != _at(success, p)]
        repair = minimize([(p, _at(success, p)) for p in differing], failed, False)
        reproduce = minimize([(p, _at(failed, p)) for p in differing], success, True)
        if repair and reproduce: return {'repair': repair, 'reintroduction': reproduce, 'validator_calls': calls, 'scope': 'local_contrast_interventions_not_new_tasks'}
    # A contrast may have fewer records or no replacement value that repairs
    # the current collection. Try domain-independent data mutations and keep
    # only ones verified by BOTH the predicate and original validator.
    def mutations(state, pattern):
        locations = _locations(state, pattern)
        strings = [(p, _at(state, p)) for p in locations if isinstance(_at(state, p), str)]
        if strings:
            yield [(p, v + '__counterfactual_' + str(i)) for i, (p, v) in enumerate(strings)]
            yield [(p, strings[0][1]) for p, _ in strings]
        for replacement in (None, 0, []):
            yield [(p, replacement) for p in locations if _at(state, p) is not MISSING]
    for pattern in paths:
        for repair_patches in mutations(failed, pattern):
            try:
                value = _changed(failed, repair_patches)
                if value is MISSING or evaluate(predicate, value) is not False: continue
            except (ValueError, KeyError, TypeError): continue
            repair = minimize(repair_patches, failed, False)
            if not repair: continue
            for success in successes[:4]:
                for reproduce_patches in mutations(success, pattern):
                    try:
                        value = _changed(success, reproduce_patches)
                        if value is MISSING or evaluate(predicate, value) is not True: continue
                    except (ValueError, KeyError, TypeError): continue
                    reproduce = minimize(reproduce_patches, success, True)
                    if reproduce: return {'repair': repair, 'reintroduction': reproduce, 'validator_calls': calls, 'scope': 'local_generic_mutations_checked_by_original_validator_not_new_tasks'}
    raise UnsupportedGuard('no_bidirectional_cause_intervention')


def certify_field_guard(function, code, states, contrasts):
    if any(function.__globals__.get(name, getattr(builtins, name)) is not getattr(builtins, name) for name in BUILTINS): raise UnsupportedGuard('shadowed_builtin')
    source_file = inspect.getsourcefile(function)
    if not source_file: raise UnsupportedGuard('validator_source_file_required')
    module_source = ast.parse(Path(source_file).read_text(encoding='utf-8'))
    constants = literal_constants(module_source)
    # Frozen names must really be the source literal, not runtime replacements.
    constants = {k: v for k, v in constants.items() if function.__globals__.get(k, MISSING) == v}
    extracted = extract_guards(inspect.getsource(function), function.__name__, constants).get(code)
    if not extracted: raise UnsupportedGuard('no_supported_failure_slice')
    nodes = 0
    def check_limits(value, depth=0):
        nonlocal nodes
        if isinstance(value, dict):
            nodes += 1
            if nodes > 256 or depth > 32: raise UnsupportedGuard('field_ir_resource_limit')
            if value.get('op') in ('get', 'get_default') and value['key'] in ('__proto__', 'prototype', 'constructor'): raise UnsupportedGuard('unsafe_field_key')
            for child in value.values():
                if isinstance(child, dict): check_limits(child, depth + 1)
                elif isinstance(child, list):
                    for item in child: check_limits(item, depth + 1)
    check_limits(extracted['predicate'])
    if len(extracted['read_paths']) > 32 or any(len(p) > 12 for p in extracted['read_paths']): raise UnsupportedGuard('field_path_resource_limit')
    def outcome(value):
        try: function(value); return None
        except ValueError as error: return str(error)
    candidates, neutral = [], []
    def visit(value, path=(), depth=0):
        if isinstance(value, dict):
            try:
                holds = evaluate(extracted['predicate'], value)
                error = outcome(value)
                if holds is True and error == code: candidates.append((list(path), value))
                elif holds is False and error != code: neutral.append((list(path), value))
            except (ValueError, KeyError, TypeError): pass
            if depth < 3:
                for key, child in value.items():
                    if isinstance(child, dict): visit(child, (*path, key), depth + 1)
    for state in states: visit(state)
    roots = {tuple(path) for path, _ in candidates}
    if len(roots) != 1: raise UnsupportedGuard('ambiguous_or_missing_state_root')
    positives = []
    for value in contrasts:
        try:
            if outcome(value) is None and evaluate(extracted['predicate'], value) is False: positives.append(value)
        except (ValueError, KeyError, TypeError): pass
    if not positives: raise UnsupportedGuard('no_successful_contrast')
    sample = candidates[0][1]
    # Other failures in the same trajectory can be better local contrasts than
    # a fully successful different paper. They still must exclude THIS error;
    # retain the remaining error instead of calling them complete repairs.
    controls = positives + [v for path, v in neutral if tuple(path) == next(iter(roots))]
    controls = list({digest(v): v for v in controls}.values())
    causes = cause_interventions(extracted['predicate'], extracted['read_paths'], sample, controls, outcome, code)
    outside = []
    def edits(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items(): yield from edits(child, (*path, key))
        elif isinstance(value, list):
            for i, child in enumerate(value[:4]): yield from edits(child, (*path, i))
        elif isinstance(value, str): yield path
    for path in list(edits(sample))[:256]:
        related = any(len(path) >= len(p) and all(k == '*' or k == str(v) for k, v in zip(p, path)) for p in extracted['read_paths'])
        if related: continue
        changed = _changed(sample, [(path, _at(sample, path) + ' ')])
        if outcome(changed) == code and evaluate(extracted['predicate'], changed) is True: outside.append(list(path))
        if len(outside) >= 8: break
    if len(outside) < 2: raise UnsupportedGuard('insufficient_unrelated_interventions')
    return {'version': 2, 'failure_code': code, **extracted, 'state_root': list(next(iter(roots))),
            'certification': {'scope': 'source_assisted_control_and_data_dependencies_with_bidirectional_interventions',
                'failure_state_sha256': [digest(v) for _, v in candidates], 'success_state_sha256': [digest(v) for v in positives],
                'unrelated_edit_paths': outside, 'cause_interventions': causes, 'model_requests': 0}}
