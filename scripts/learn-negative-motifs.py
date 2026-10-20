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
from src.adapters.negative_constraint_compiler import constraint_observations, certify_current_constraint, recertify_current_constraints


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', type=Path, action='append', required=True)
    p.add_argument('--implementation-file', action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--field-profile', type=Path, help='显式受信、只读校验器与私有状态/对照；不执行模型提供的代码')
    p.add_argument('--constraint-validator',help='经审阅的纯当前目标结构校验器：相对文件:函数；只在真实回执与双向认证一致时编译')
    p.add_argument('--recertify-current-constraints', action='store_true',
                   help='显式跨实现重新认证：只保留当前纯校验器双向认证通过的条件规则；不迁移旧工具执行认证或prompt-only规则')
    a = p.parse_args()
    if a.recertify_current_constraints and (not a.constraint_validator or a.field_profile):
        p.error('重新认证仅支持显式--constraint-validator，不支持field-profile')
    locks = {}
    for name in a.implementation_file:
        path = ROOT / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.is_file():
            raise ValueError('relative_implementation_file_required')
        locks[name] = sha(path.read_bytes())
    rows = []
    historical_sources = []
    for task in a.task:
        task = task.resolve(strict=True)
        if not task.is_relative_to(ROOT / '.local'): raise ValueError('private_trace_required')
        run = task.parent.parent.name
        snapshot_raw = (ROOT / '.local/script-motif-experiments' / run / 'source-snapshot.json').read_bytes()
        snapshot = json.loads(snapshot_raw)
        historical_locks = {k: snapshot[k] for k in locks}
        if not a.recertify_current_constraints and historical_locks != locks:
            raise ValueError('historical_tool_implementation_changed')
        rows.extend(collect_negative(task))
        historical_sources.append({'task_id': task.name, 'events_sha256': sha((task / 'events.jsonl').read_bytes()),
                                   'source_snapshot_sha256': sha(snapshot_raw), 'implementation_locks': historical_locks})
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
    if a.constraint_validator:
        name,function_name=a.constraint_validator.split(':')
        if name not in locks or not function_name.isidentifier():raise ValueError('constraint_validator_not_locked')
        spec=importlib.util.spec_from_file_location('negative_current_constraint',ROOT/name)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);validator=getattr(module,function_name)
        observations=[r for task in a.task for r in constraint_observations(task)]
        if a.recertify_current_constraints:
            library = recertify_current_constraints(library, observations, validator, a.constraint_validator, historical_sources)
        for rule in ([] if a.recertify_current_constraints else library['rules']):
            if rule.get('failure_source')!='failed_checks':continue
            try:
                guard=certify_current_constraint(rule,observations,validator)
                guard.update(validator=a.constraint_validator,validator_sha256=locks[name])
                rule['argument_guard']=guard;rule['retry_policy']='warn_then_current_constraint'
                rule['id']='negative_'+digest({k:v for k,v in rule.items() if k!='id'})[:16]
                field_report.append({'failure_code':rule['failure_code'],'status':'current_constraint','witnesses':len(guard['certification']['failures'])})
            except (ValueError,KeyError,TypeError) as error:
                field_report.append({'failure_code':rule['failure_code'],'status':'prompt_only','reason':str(error)})
        library['digest']=digest({k:v for k,v in library.items() if k!='digest'})
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'library.json').write_text(json.dumps(library, ensure_ascii=False, indent=2) + '\n')
    (a.output / 'library.json').chmod(0o600)
    (a.output / 'field-compilation.json').write_text(json.dumps(field_report, ensure_ascii=False, indent=2))
    print(json.dumps({'rules': len(library['rules']), 'digest': library['digest'], 'model_requests': 0}))


if __name__ == '__main__': main()
