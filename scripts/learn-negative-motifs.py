#!/usr/bin/env python3
"""Private negative-Motif compiler; reads real failures as well as successes."""
import argparse
import json
from pathlib import Path
import sys
import importlib.util
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.script_negative_compiler import collect_negative, compile_negative, RUNTIME_FILES, sha, digest
from src.adapters.negative_field_compiler import certify_field_guard, UnsupportedGuard


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', type=Path, action='append', required=True)
    p.add_argument('--implementation-file', action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--field-profile', type=Path, help='显式受信、只读校验器与私有状态/对照；不执行模型提供的代码')
    a = p.parse_args()
    locks = {}
    for name in a.implementation_file:
        path = ROOT / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.is_file():
            raise ValueError('relative_implementation_file_required')
        locks[name] = sha(path.read_bytes())
    rows = []
    for task in a.task:
        task = task.resolve(strict=True)
        if not task.is_relative_to(ROOT / '.local'): raise ValueError('private_trace_required')
        run = task.parent.parent.name
        snapshot = json.loads((ROOT / '.local/script-motif-experiments' / run / 'source-snapshot.json').read_text())
        if any(snapshot.get(k) != v for k, v in locks.items()):
            raise ValueError('historical_tool_implementation_changed')
        rows.extend(collect_negative(task))
    library = compile_negative(rows, locks, {k: sha((ROOT / k).read_bytes()) for k in RUNTIME_FILES})
    field_report = []
    if a.field_profile:
        profile_path = a.field_profile.resolve(strict=True)
        if not profile_path.is_relative_to(ROOT / '.local'): raise ValueError('private_field_profile_required')
        for profile in json.loads(profile_path.read_text())['profiles']:
            name, function_name = profile['validator'].split(':')
            if name not in locks or not function_name.isidentifier(): raise ValueError('validator_not_implementation_locked')
            spec = importlib.util.spec_from_file_location('negative_readonly_validator', ROOT / name)
            module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            function = getattr(module, function_name)
            def states(key):
                result = []
                for value in profile[key]:
                    path = Path(value).resolve(strict=True)
                    if not path.is_relative_to(ROOT / '.local') or path.stat().st_size > 2_000_000: raise ValueError('private_bounded_state_required')
                    result.append(json.loads(path.read_text()))
                return result
            failures, contrasts = states('states'), states('contrasts')
            for rule in library['rules']:
                if rule['tool'] != profile['tool'] or rule['retry_policy'] == 'prompt_only' or len(rule['version_slots']) != 1: continue
                try:
                    field = certify_field_guard(function, rule['failure_code'], failures, contrasts)
                    field['validator'] = profile['validator'];field['validator_sha256'] = locks[name]
                    rule['field_guard'] = field;rule['retry_policy'] = 'warn_then_field_guard'
                    rule['id'] = 'negative_' + digest({k: v for k, v in rule.items() if k != 'id'})[:16]
                    field_report.append({'failure_code': rule['failure_code'], 'status': 'field_guard', 'read_paths': field['read_paths']})
                except (UnsupportedGuard, KeyError, TypeError) as error:
                    field_report.append({'failure_code': rule['failure_code'], 'status': 'unchanged', 'reason': str(error)})
        library['digest'] = digest({k: v for k, v in library.items() if k != 'digest'})
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'library.json').write_text(json.dumps(library, ensure_ascii=False, indent=2) + '\n')
    (a.output / 'library.json').chmod(0o600)
    (a.output / 'field-compilation.json').write_text(json.dumps(field_report, ensure_ascii=False, indent=2))
    print(json.dumps({'rules': len(library['rules']), 'digest': library['digest'], 'model_requests': 0}))


if __name__ == '__main__': main()
