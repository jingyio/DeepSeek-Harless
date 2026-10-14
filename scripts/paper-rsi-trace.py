"""Trace -> model-chosen tool -> source replay acceptance -> frozen pure MCP.

Private data and paid learning run on the configured server; no new execute.
Historical shell is never executed. Independent fixtures are not sent to LLM.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.trace_tool_evidence import (SourceReplay, bounded_read, digest, trace_run,
    counterfactuals, project_inputs, project_outputs)

DEFAULT_EXP = '.local/paper-reference/paper-rsi-trace-tools-20261011-v3'
DEFAULT_RUNS = ['.local/paper-reference/paper-rsi-sequential-20261010-v1/runs/continuation-shadow-round-2-shadow',
                '.local/paper-reference/paper-rsi-sequential-20261010-v1/runs/continuation-shadow-round-3-shadow']
FILES = ['scripts/paper-rsi-trace.py', 'scripts/check-trace-rsi-tool.mjs',
         'src/adapters/trace_tool_evidence.py', 'src/adapters/trace_rsi_program.ts',
         'src/adapters/paper_rsi_program.ts', 'src/adapters/dsh_trace_rsi_learning.ts',
         'scenarios/paper-submission/trace-rsi-learning.prompt.md', 'scenarios/paper-submission/trace-rsi-server.ts']

def parent():
    spec = importlib.util.spec_from_file_location('trace_rsi_parent', ROOT/'scripts/paper-rsi-tool-learning.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

def private_path(value):
    path = ROOT / value
    if path.is_symlink() or not path.resolve().is_relative_to((ROOT/'.local').resolve()):
        raise ValueError('private_experiment_required')
    return path

def save_once(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    path.chmod(0o600)

def load(path): return json.loads(bounded_read(path, 4_000_000))

def infer_schema(values, path='root', depth=0):
    """Infer only JSON structure, never current identifiers or research verdicts.

    Heterogeneous values require an explicit model contract or a narrower
    projection. Empty-only arrays have no supported item-type evidence.
    """
    if not values or depth > 16: raise ValueError('schema_inference_no_type_evidence:'+path)
    def kind(v):
        if v is None: return 'null'
        if isinstance(v,bool): return 'boolean'
        if isinstance(v,int): return 'integer'
        if isinstance(v,float): return 'number'
        if isinstance(v,str): return 'string'
        if isinstance(v,list): return 'array'
        if isinstance(v,dict): return 'object'
        raise ValueError('schema_inference_non_json:'+path)
    types = {kind(v) for v in values}
    if types <= {'number','integer'}: types = {'number' if 'number' in types else 'integer'}
    if len(types) != 1: raise ValueError('schema_inference_mixed_types_use_projection_or_explicit_schema:'+path)
    typ = next(iter(types)); schema = {'type':typ}
    if typ == 'object':
        keys = sorted({k for v in values for k in v})
        if len(keys)>64: raise ValueError('schema_inference_object_fields_limit:'+path)
        schema.update(properties={k:infer_schema([v[k] for v in values if k in v],path+'/'+k,depth+1) for k in keys},
            required=[k for k in keys if all(k in v for v in values)],additionalProperties=False)
    elif typ == 'array':
        items = [item for v in values for item in v]
        schema.update(items=infer_schema(items,path+'/*',depth+1),maxItems=2000)
    return schema

def require_derived_output(cases):
    """Reject a constant or a renaming/copy of a stable input JSON path only.

    This is a utility floor, not an equivalence or cross-task quality proof.
    """
    def paths(value, target, path=()):
        if digest(value)==target: yield path
        if isinstance(value,dict):
            for key,child in value.items(): yield from paths(child,target,path+(key,))
        elif isinstance(value,list):
            for index,child in enumerate(value): yield from paths(child,target,path+(index,))
    def at(value,path):
        for key in path: value=value[key]
        return digest(value)
    for output_key in cases[0]['expected']:
        series = [digest(c['expected'][output_key]) for c in cases]
        if len(set(series)) < 2: continue
        echo=False
        for path in paths(cases[0]['input'],series[0]):
            try:
                if series==[at(c['input'],path) for c in cases]: echo=True;break
            except (KeyError,IndexError,TypeError): pass
        if not echo: return
    raise ValueError('derived_output_required_not_only_constant_or_input_echo')

def bundle(exp, runs):
    if (exp/'trace-bundle.json').exists():
        old = load(exp/'trace-bundle.json')
        if runs and old['source_runs'] != runs: raise ValueError('preserve_source_split')
        for relative in old['source_runs']:
            current = trace_run(ROOT, relative)
            expected = [r for r in old['entries'] if r['run_id'] == relative]
            if digest(current) != digest(expected): raise ValueError('source_trace_or_snapshot_changed')
        return old
    entries = [entry for run in runs for entry in trace_run(ROOT, run)]
    if not any(row['replay_status'] == 'observed_replay_match' for row in entries):
        raise ValueError('no_observed_replayable_source')
    body = {'schema_version':1,'source_runs':runs,'entries':entries,
            'scope':'same_paper_normal_sessions_not_cross_paper', 'historical_shell_executed':False}
    save_once(exp/'trace-bundle.json', body)
    return body

def prepare_proposal(exp, proposal):
    data = load(exp/'trace-bundle.json')
    active = load(exp/'active-learning.json')
    work = Path(active['work'])
    if work.is_symlink() or not work.resolve().is_relative_to(exp.resolve()): raise ValueError('invalid_learning_work')
    if (exp/'accepted-proposal.json').exists(): raise ValueError('proposal_already_frozen_do_not_change_test_target')
    contract = dict(proposal['contract'])
    if set(contract) not in ({'name','description'},{'name','description','input_schema','output_schema'}):
        raise ValueError('invalid_contract_keys_use_name_description_and_optional_both_schemas')
    source = proposal['source']
    matches = [r for r in data['entries'] if r['run_id'] == source['run_id'] and r['call_id'] == source['call_id']]
    if len(matches) != 1 or matches[0]['replay_status'] != 'observed_replay_match': raise ValueError('source_not_independently_replayable')
    row = matches[0]
    inputs, outputs = proposal['input_bindings'], proposal['output_bindings']
    if not isinstance(inputs, dict) or not inputs or len(inputs) > 16 or not isinstance(outputs, dict) or not outputs or len(outputs) > 12:
        raise ValueError('bounded_bindings_required')
    if any(not re.fullmatch('[a-z][a-z0-9_]{0,31}',key) for key in outputs):
        raise ValueError('output_field_must_be_safe_snake_case_map_to_original_label_as_value')
    if 'input_schema' in contract and (set(inputs) != set(contract['input_schema'].get('properties', {})) or
        set(outputs) != set(contract['output_schema'].get('properties', {}))):
        raise ValueError('schema_binding_fields_mismatch')
    for key, binding in inputs.items():
        if not re.fullmatch('[a-z][a-z0-9_]{0,63}',key) or set(binding)-{'file','pointer','fields'}:
            raise ValueError('invalid_input_binding')
        if binding.get('file') not in row['memory_files'] or not binding['file'].endswith('.json'):
            raise ValueError('unregistered_json_input')
        if 'fields' in binding and (not isinstance(binding['fields'], list) or not binding['fields'] or len(binding['fields']) > 32 or
             any(not isinstance(k,str) or k in ('__proto__','prototype','constructor') for k in binding['fields'])):
            raise ValueError('invalid_field_projection')
    if any(label not in row['output_labels'] for label in outputs.values()): raise ValueError('unobserved_output_label')
    originals = row['memory_files']
    cases, errors, seen = [], [], {}
    for label, files in [('original-observed', originals)] + counterfactuals(originals):
        try:
            replay = SourceReplay(files).run(row['source'])
            case = {'id':label,'input':project_inputs(files,inputs), 'expected':project_outputs(replay['outputs'],outputs)}
            h = digest(case['input'])
            if h in seen and seen[h] != digest(case['expected']):
                raise RuntimeError('input_projection_loses_output_dependencies_add_input_bindings')
            if h not in seen:
                seen[h] = digest(case['expected']); cases.append(case)
        except (ValueError, KeyError, TypeError, IndexError, RecursionError) as error:
            if label=='original-observed':
                raise ValueError('invalid_original_source_projection:'+str(error)[:200]) from error
            errors.append({'id':label,'reason':str(error)[:200]})
    if len(cases) < 5 or len({digest(c['expected']) for c in cases}) < 2:
        raise ValueError('insufficient_nonconstant_independent_source_cases')
    require_derived_output(cases)
    schema_origin = 'model_supplied'
    if 'input_schema' not in contract:
        schema_origin = 'generic_structure_inference_before_implementation'
        contract.update(input_schema=infer_schema([c['input'] for c in cases],'input'),
            output_schema=infer_schema([c['expected'] for c in cases],'output'))
    # Check both schemas against every original/source-counterfactual value
    # before freezing. A failed proposal returns paths, never hidden values.
    validated = subprocess.run([shutil.which('node'),'--experimental-strip-types','--input-type=module','-e',
        "import {validateTraceContractValues} from './src/adapters/trace_rsi_program.ts';"
        "let s='';for await(const c of process.stdin)s+=c;const x=JSON.parse(s);"
        "try{for(const r of x.cases)validateTraceContractValues(x.contract,r.input,r.expected)}"
        "catch(e){process.stderr.write(e.message);process.exitCode=1}",
        ],cwd=ROOT,input=json.dumps({'contract':contract,'cases':cases},ensure_ascii=False),
        text=True,capture_output=True,timeout=10)
    if validated.returncode: raise ValueError('contract_does_not_cover_source_cases:'+validated.stderr[-400:])
    # Deterministic split made before implementation; hidden cases never enter
    # the learning prompt/feedback. No retries after failed promotion.
    ordered = sorted(cases[1:], key=lambda c: digest([digest(proposal), c['id']]))
    training = [cases[0], *ordered[:2]]
    heldout = ordered[2:14]
    if len(heldout) < 2: raise ValueError('insufficient_heldout_source_cases')
    accepted = {'schema_version':1,'proposal_sha256':digest(proposal),'contract':contract,
        'proposal':proposal,'schema_origin':schema_origin,'trace_bundle_sha256':digest(data),
        'source_witnesses':[{k:row[k] for k in ('run_id','session_id','call_id','events_sha256','line','result_line','stdout_match_kind')}],
        'source_program_sha256':hashlib.sha256(row['source'].encode()).hexdigest(),
        'source_files_sha256':row['file_sha256'],'case_scope':'same_source_counterfactual_not_independent_papers',
        'training_input_sha256':[digest(c['input']) for c in training],
        'heldout_input_sha256':[digest(c['input']) for c in heldout], 'oracle_errors':errors}
    accepted.update(training_sha256=digest(training),heldout_sha256=digest(heldout))
    for name, value in [('accepted-proposal.json',accepted),('training.json',training)]:
        save_once(work/name,value)
    save_once(exp/'heldout.json',heldout)
    save_once(exp/'oracle-counterfactuals.json',{'cases':cases,'rejected':errors})
    save_once(exp/'accepted-proposal.json',accepted)
    return {'proposal_sha256':accepted['proposal_sha256'],'contract':contract,'training':training,
            'heldout_cases':len(heldout),'source_replay_kind':accepted['case_scope']}

def learn(exp, label):
    data = bundle(exp, [])
    if (exp/'accepted-proposal.json').exists(): raise ValueError('use_new_learning_version_for_new_target')
    legacy = parent(); legacy.EXP = exp; legacy.FILES = FILES
    work = exp/'runs'/label/'work'
    save_once(exp/'active-learning.json',{'work':str(work),'run_label':label,'trace_bundle_sha256':digest(data)})
    template = (ROOT/'scenarios/paper-submission/trace-rsi-learning.prompt.md').read_text()
    config = {'mode':'learning','experiment_path':str(exp),'trace_bundle_path':str(exp/'trace-bundle.json'),
        'trace_bundle_sha256':digest(data),'python_command':sys.executable,'controller_path':str(ROOT/'scripts/paper-rsi-trace.py')}
    policy = '\n- insert:\n    - name: "@deepseek-ai/dsh-cordis-host-runner"\n      config:\n        vmTimeoutMs: 5000\n    - name: "@deepseek-ai/dsh-tool-cordis"\n    - name: '+json.dumps((ROOT/'src/adapters/dsh_trace_rsi_learning.ts').as_uri())+'\n'
    return legacy.paid(label,template,policy,config,['SSS_TRACE_RSI_LEARNING'])

def freeze(exp, label):
    run = exp/'runs'/label
    if load(run/'metrics.json')['status'] != 'completed': raise ValueError('learning_not_completed')
    accepted = load(exp/'accepted-proposal.json')
    candidate_path = run/'work/current-candidate.json'
    candidate = load(candidate_path); candidate_hash = digest(candidate)
    if {k:candidate[k] for k in accepted['contract']} != accepted['contract']: raise ValueError('candidate_contract_changed')
    audit = [json.loads(l) for l in (run/'work/learning.jsonl').read_text().splitlines() if l]
    if not any(r['kind']=='development_test' and r.get('passed') and r.get('candidate_sha256')==candidate_hash for r in audit):
        raise ValueError('development_not_passed')
    if not any(r['kind']=='trial' and r.get('candidate_sha256')==candidate_hash and
               not r.get('error') and r.get('output_sha256') for r in audit): raise ValueError('no_successful_real_trial')
    definitions = []
    for line in (run/'events.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row.get('sessionId') != load(run/'config.json')['session_id']: continue
        event = row['event']
        if event['type']=='tool/call' and event['data']['name']=='cordis_define':
            args = event['data']['arguments']; args = json.loads(args) if isinstance(args,str) else args
            if args.get('code',{}).get('host'): definitions.append(args['code']['host'])
    if not definitions: raise ValueError('model_generated_definition_missing')
    # Recheck source provenance and split integrity before using private oracle.
    data = bundle(exp, [])
    if digest(data)!=accepted['trace_bundle_sha256']: raise ValueError('trace_bundle_changed')
    heldout = load(exp/'heldout.json')
    if digest(heldout) != accepted['heldout_sha256'] or digest(load(run/'work/training.json')) != accepted['training_sha256']:
        raise ValueError('oracle_expected_values_changed')
    if [digest(c['input']) for c in heldout] != accepted['heldout_input_sha256'] or set(accepted['training_input_sha256']) & set(accepted['heldout_input_sha256']):
        raise ValueError('heldout_split_changed')
    result = subprocess.run([shutil.which('node'),'--experimental-strip-types',str(ROOT/'scripts/check-trace-rsi-tool.mjs'),
        str(candidate_path),str(exp/'heldout.json')],cwd=ROOT,capture_output=True,text=True,timeout=30)
    checked = json.loads(result.stdout)
    save_once(exp/'heldout-validation.json',checked)
    if result.returncode or not checked['passed']: raise ValueError('independent_source_replay_failed_preserve_failure')
    provenance = {**accepted,'learning_run':label,'learning_session_id':load(run/'config.json')['session_id'],
        'cordis_source_sha256':digest(definitions),'cordis_definition_count':len(definitions),
        'learning_events_sha256':hashlib.sha256((run/'events.jsonl').read_bytes()).hexdigest()}
    certification = {'status':'passed','kind':'source_replay','heldout_cases':len(heldout),
        'fixture_sha256':digest(heldout),'results_sha256':digest(checked),
        'scope':'selected_observed_pure_operations_same_source_counterfactuals','semantic_quality':'not_reviewed'}
    body = {'schema_version':1,'kind':'model_generated_trace_tool','candidate':candidate,'candidate_sha256':candidate_hash,
        'provenance':provenance,'provenance_sha256':digest(provenance),'certification':certification,'certification_sha256':digest(certification)}
    frozen = {**body,'manifest_digest':digest(body)}
    save_once(exp/'frozen-tool.json',frozen)
    save_once(exp/'cordis-definitions.json',definitions)
    return {'name':candidate['name'],'heldout_cases':len(heldout),'passed':True,'actual_model_skips':0}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['preview','prepare','learn','prepare-proposal','freeze'],default='preview')
    parser.add_argument('--experiment',default=DEFAULT_EXP)
    parser.add_argument('--train-run',action='append',default=[])
    parser.add_argument('--label',default='learn-v01')
    parser.add_argument('--call-model',action='store_true')
    args = parser.parse_args(); exp = private_path(args.experiment)
    if args.phase == 'prepare':
        data = bundle(exp,args.train_run or DEFAULT_RUNS)
        print(json.dumps({'entries':len(data['entries']),'replayable':sum(r['replay_status']=='observed_replay_match' for r in data['entries']),
            'trace_bundle_sha256':digest(data),'model_calls':0})); return
    if args.phase == 'prepare-proposal':
        text = sys.stdin.read(128001)
        if len(text)>128000: raise ValueError('proposal_too_large')
        print(json.dumps(prepare_proposal(exp,json.loads(text)),ensure_ascii=False)); return
    if args.phase == 'freeze': print(json.dumps(freeze(exp,args.label),ensure_ascii=False)); return
    legacy = parent()
    _, prior, _ = legacy.rsi.reference.budget.account(exp)
    if args.phase == 'preview':
        print(json.dumps({'paid_enabled':False,'model':'deepseek-flash','reasoning_effort':'off','output_cap':8192,
            'request_limit':None,'cumulative_cap_usd':legacy.rsi.load_budget_record(legacy.AUTH)['cap_usd'],
            'cumulative_estimated_usd':prior})); return
    if not args.call_model: raise ValueError('paid_phase_requires_call_model')
    lock = ROOT/'.local/paper-motif/.budget.lock'; lock.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with exclusive_lock(lock) as stream:
        learn(exp,args.label)

if __name__=='__main__': main()
