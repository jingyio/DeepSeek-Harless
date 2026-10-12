"""Real normal revision traces -> model-generated audit tool -> prospective Shadow.

Default is a free preview. Paid phases run only on the authorized server and
share the complete historical budget. This controller has no execute phase.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.revision_tool_evidence import (build_revision_packets, revision_facts,
    revision_counterfactuals, strict_revision_pointer, project_generated_outputs,
    compose_generated_candidates, rebind_generated_input)
from src.adapters.trace_tool_evidence import digest, project_inputs

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
trace=module('revision_trace_base','scripts/paper-rsi-trace.py')
EXP=ROOT/'.local/paper-reference/paper-rsi-revision-shadow-20261011-v1'
TRAIN_RUNS=[f'.local/paper-reference/paper-rsi-batch-shadow-20261011-v2/runs/{label}' for label in ('baseline-main','baseline-abstract')]+[
    '.local/paper-reference/paper-rsi-batch-training-20261011-v1/runs/baseline-main']
FILES=['scripts/paper-rsi-revision.py','src/adapters/revision_tool_evidence.py',
    'src/adapters/revision_rsi_macros.ts',
    'src/adapters/dsh_revision_rsi_learning.ts','scenarios/paper-submission/revision-rsi-learning.prompt.md',
    *trace.FILES]
save,load=trace.save_once,trace.load

def packets(exp):
    body=build_revision_packets(TRAIN_RUNS,root=ROOT)
    path=exp/'training-packets.json'
    if path.exists():
        if digest(load(path))!=digest(body):raise ValueError('revision_source_packets_changed')
    else:save(path,body)
    return body

def project(case,bindings):
    files={'catalog.json':json.dumps({**case['catalog'],'initial_report':case['before_report']},ensure_ascii=False),
           'triage.json':json.dumps(case['after_report'],ensure_ascii=False)}
    return project_inputs(files,bindings)

def prepare_proposal(exp,proposal):
    data=load(exp/'training-packets.json');active=load(exp/'active-learning.json');work=Path(active['work'])
    if (exp/'accepted-proposal.json').exists():raise ValueError('proposal_already_frozen')
    if not work.resolve().is_relative_to(exp.resolve()) or work.is_symlink():raise ValueError('invalid_learning_work')
    selected=proposal['source']['packet_id'];rows=[p for p in data['packets'] if p['packet_id']==selected]
    if len(rows)!=1 or not rows[0]['learning_eligible']:raise ValueError('registered_learning_packet_required')
    bindings,outputs=proposal['input_bindings'],proposal['output_bindings']
    if not isinstance(bindings,dict) or not 1<=len(bindings)<=16:
        raise ValueError('input_bindings_must_be_object_with_1_to_16_fields')
    if not isinstance(outputs,dict) or not 4<=len(outputs)<=6:
        raise ValueError('output_bindings_must_be_object_with_4_to_6_fields;received:'+str(len(outputs) if isinstance(outputs,dict) else type(outputs).__name__))
    for name,row in bindings.items():
        if not re.fullmatch('[a-z][a-z0-9_]{0,63}',name) or set(row)-{'file','pointer','fields'} or row.get('file') not in ('catalog.json','triage.json'):
            raise ValueError('invalid_revision_input_binding')
        # Unlike a historical Python index, JSON pointer cannot use -1 or *.
        source={**rows[0]['catalog'],'initial_report':rows[0]['before_report']} if row['file']=='catalog.json' else rows[0]['after_report']
        strict_revision_pointer(source,row['pointer'])
    facts=rows[0]['oracle_facts']
    for name,path in outputs.items():
        if not re.fullmatch('[a-z][a-z0-9_]{0,31}',name):raise ValueError('safe_output_field_required')
        strict_revision_pointer(facts,path)
    required={'/metrics/before_count','/metrics/after_count','/metrics/existing_fields_preserved','/metrics/top_level_preserved'}
    if not required<=set(outputs.values()):raise ValueError('revision_scope_requires_counts_and_field_and_context_preservation')
    if not set(outputs.values())<=required|{'/metrics/changed_key_count','/metrics/after_duplicate_key_count'}:
        raise ValueError('narrow_revision_scope_counts_and_field_differences_only')
    if not all(any(r['file']=='catalog.json' and r['pointer']==p for r in bindings.values()) for p in ('/cited_records','/query_items')):
        raise ValueError('normal_task_requires_current_catalog_cited_records_and_query_items_bindings')
    cases=[];seen={};rejected=[]
    for packet in data['packets']:
        for label,case in revision_counterfactuals(packet):
            if label.startswith('null-field-'):
                rejected.append({'id':label,'reason':'type_change_outside_closed_schema_guard_test_only'});continue
            value=project(case,bindings)
            expected={k:strict_revision_pointer(revision_facts(case['before_report'],case['after_report'],case['catalog']),path) for k,path in outputs.items()}
            h=digest(value)
            if h in seen:
                if digest(seen[h])!=digest(expected):
                    lost=[k for k in expected if digest(seen[h][k])!=digest(expected[k])]
                    raise ValueError('projection_loses_revision_dependencies_for_outputs:'+','.join(lost)+';bind_full_before_and_after_reports_for_top_level_preservation')
                continue
            seen[h]=expected;cases.append({'id':label,'input':value,'expected':expected})
    trace.require_derived_output(cases)
    contract=dict(proposal['contract'])
    if set(contract)=={'name','description'}:
        contract.update(input_schema=trace.infer_schema([c['input'] for c in cases],'input'),
            output_schema=trace.infer_schema([c['expected'] for c in cases],'output'))
    elif set(contract)!={'name','description','input_schema','output_schema'}:raise ValueError('invalid_revision_contract')
    checked=subprocess.run([shutil.which('node'),'--experimental-strip-types','--input-type=module','-e',
        "import {validateTraceContractValues} from './src/adapters/trace_rsi_program.ts';let s='';for await(const c of process.stdin)s+=c;const x=JSON.parse(s);for(const c of x.cases)validateTraceContractValues(x.contract,c.input,c.expected);"],
        cwd=ROOT,input=json.dumps({'contract':contract,'cases':cases},ensure_ascii=False),text=True,capture_output=True,timeout=15)
    if checked.returncode:raise ValueError('revision_contract_invalid:'+checked.stderr[-400:])
    originals=[c for c in cases if c['id'].startswith('observed-')]
    variants=[c for c in cases if not c['id'].startswith('observed-')]
    # Predeclared class coverage on the main training scope. Other scopes'
    # mutated inputs remain hidden. This is counterfactual transfer within the
    # same paper, not unseen failure classes or cross-paper certification.
    training=[*originals,*[c for c in variants if c['id'].endswith(data['packets'][0]['packet_id'])]]
    heldout=[c for c in variants if not c['id'].endswith(data['packets'][0]['packet_id'])]
    if len(heldout)<8:raise ValueError('insufficient_independent_revision_cases')
    accepted={'schema_version':1,'proposal_sha256':digest(proposal),'contract':contract,
        'proposal':proposal,'input_bindings':bindings,'output_bindings':outputs,
        'trace_bundle_sha256':digest(data),'source_witnesses':[{k:p[k] for k in ('run_id','session_id','call_id','events_sha256')} for p in data['packets']],
        'training_sha256':digest(training),'heldout_sha256':digest(heldout),
        'case_scope':'same_paper_witnessed_revision_and_independent_fault_injections',
        'oracle_method':'revision_facts_on_actual_before_after_not_original_report_gold',
        'oracle_code_sha256':hashlib.sha256((ROOT/'src/adapters/revision_tool_evidence.py').read_bytes()).hexdigest(),
        'guard_only_cases':rejected,'split_protocol':'all_observed_plus_main_scope_fault_classes_other_scopes_hidden'}
    for name,value in [('accepted-proposal.json',accepted),('training.json',training)]:save(work/name,value)
    save(exp/'heldout.json',heldout);save(exp/'accepted-proposal.json',accepted)
    return {'proposal_sha256':accepted['proposal_sha256'],'contract':contract,'training':training,'heldout_cases':len(heldout),
        'program_protocol':{'root':'expression_array_not_object_wrapper','entry_variable':'input',
            'bound_inputs':'get(var(input),lit(property_name)); property names are not entry variables',
            'cordis_code':'host_only_no_client_half','macro':'pairs_without(object_expression, excluded_keys_array_expression)'}}

def learn(exp,label):
    data=packets(exp)
    if (exp/'active-learning.json').exists():raise ValueError('use_new_explicit_experiment_for_learning_retry')
    work=exp/'runs'/label/'work'
    save(exp/'active-learning.json',{'work':str(work),'run_label':label,'trace_bundle_sha256':digest(data)})
    legacy=trace.parent();legacy.EXP=exp;legacy.FILES=FILES
    config={'mode':'learning','experiment_path':str(exp),'training_packets_path':str(exp/'training-packets.json'),
        'training_packets_sha256':hashlib.sha256((exp/'training-packets.json').read_bytes()).hexdigest(),
        'python_command':sys.executable,'controller_path':str(ROOT/'scripts/paper-rsi-revision.py')}
    policy='\n- insert:\n    - name: "@deepseek-ai/dsh-cordis-host-runner"\n      config:\n        vmTimeoutMs: 5000\n    - name: "@deepseek-ai/dsh-tool-cordis"\n    - name: '+json.dumps((ROOT/'src/adapters/dsh_revision_rsi_learning.ts').as_uri())+'\n'
    return legacy.paid(label,(ROOT/'scenarios/paper-submission/revision-rsi-learning.prompt.md').read_text(),policy,config,['SSS_REVISION_RSI_LEARNING'])

def freeze(exp,label):
    run=exp/'runs'/label;accepted=load(exp/'accepted-proposal.json');candidate=load(run/'work/current-candidate.json')
    if (exp/'heldout-validation.json').exists():raise ValueError('independent_acceptance_already_attempted_use_new_version')
    if load(run/'metrics.json')['status']!='completed':raise ValueError('revision_learning_not_completed')
    if {k:candidate[k] for k in accepted['contract']}!=accepted['contract']:raise ValueError('revision_contract_changed')
    if digest(packets(exp))!=accepted['trace_bundle_sha256']:raise ValueError('revision_source_changed')
    if hashlib.sha256((ROOT/'src/adapters/revision_tool_evidence.py').read_bytes()).hexdigest()!=accepted['oracle_code_sha256']:
        raise ValueError('revision_oracle_changed')
    heldout=load(exp/'heldout.json');training=load(run/'work/training.json')
    if digest(heldout)!=accepted['heldout_sha256'] or digest(training)!=accepted['training_sha256']:
        raise ValueError('revision_oracle_values_changed')
    if {digest(c['input']) for c in training}&{digest(c['input']) for c in heldout}:raise ValueError('revision_split_overlap')
    audit=[json.loads(s) for s in (run/'work/learning.jsonl').read_text().splitlines()]
    h=digest(candidate)
    if not any(r['kind']=='development_test' and r.get('passed') and r.get('candidate_sha256')==h for r in audit) or not any(
        r['kind']=='trial' and not r.get('error') and r.get('candidate_sha256')==h and r.get('output_sha256') for r in audit):
        raise ValueError('revision_development_and_trial_required')
    manifest=load(run/'manifest.json')
    if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h for name,h in manifest['code_sha256'].items()):
        raise ValueError('revision_learning_code_changed')
    checked=subprocess.run([shutil.which('node'),'--experimental-strip-types',str(ROOT/'scripts/check-trace-rsi-tool.mjs'),
        str(run/'work/current-candidate.json'),str(exp/'heldout.json')],cwd=ROOT,text=True,capture_output=True,timeout=30)
    result=json.loads(checked.stdout);save(exp/'heldout-validation.json',result)
    if checked.returncode or not result['passed']:raise ValueError('revision_independent_acceptance_failed')
    definitions=[]
    for text in (run/'events.jsonl').read_text().splitlines():
        row=json.loads(text);event=row['event']
        if row.get('sessionId')==load(run/'config.json')['session_id'] and event['type']=='tool/call' and event['data']['name']=='cordis_define':
            args=event['data']['arguments'];args=json.loads(args) if isinstance(args,str) else args
            if args.get('code',{}).get('host'):definitions.append(args['code']['host'])
    if not definitions:raise ValueError('revision_model_generation_evidence_missing')
    provenance={**accepted,'learning_run':label,'cordis_source_sha256':digest(definitions),
        'learning_events_sha256':hashlib.sha256((run/'events.jsonl').read_bytes()).hexdigest()}
    cert={'status':'passed','kind':'source_replay','replay_method':'independent_revision_fact_replay',
        'heldout_cases':len(heldout),'scope':accepted['case_scope'],'fixture_sha256':digest(heldout),
        'results_sha256':digest(result),'semantic_quality':'not_reviewed','historical_bash_equivalence':False}
    body={'schema_version':1,'kind':'model_generated_trace_tool','candidate':candidate,'candidate_sha256':h,
        'provenance':provenance,'provenance_sha256':digest(provenance),'certification':cert,'certification_sha256':digest(cert)}
    save(exp/'frozen-tool.json',{**body,'manifest_digest':digest(body)})
    save(exp/'cordis-definitions.json',definitions)
    return {'passed':True,'name':candidate['name'],'heldout_cases':len(heldout),'actual_model_skips':0}

def compile_counts(exp, *, include_retention=False, include_details=False):
    """Reuse generated count branches without repairing the rejected auditor.

    New counts are independently checked on fresh counterfactuals. Coverage's
    prior source-replay certificate is inherited; composition equivalence is a
    diagnostic, not a new independent bibliography or cross-paper certificate.
    """
    import copy
    source=ROOT/'.local/paper-reference/paper-rsi-revision-shadow-20261011-v3'
    run=source/'runs/learn-v01';accepted=load(source/'accepted-proposal.json')
    generated=load(run/'work/current-candidate.json');h=digest(generated)
    audit=[json.loads(s) for s in (run/'work/learning.jsonl').read_text().splitlines()]
    if load(run/'metrics.json')['status']!='completed' or not any(
        r['kind']=='development_test' and r.get('passed') and r.get('candidate_sha256')==h for r in audit) or not any(
        r['kind']=='trial' and not r.get('error') and r.get('candidate_sha256')==h for r in audit):
        raise ValueError('completed_model_candidate_generation_and_trial_required')
    if {k:generated[k] for k in accepted['contract']}!=accepted['contract']:
        raise ValueError('original_model_contract_changed')
    outputs=['before_count','after_count','before_duplicate_key_count','added_key_count','removed_key_count']
    inputs=['before_report','after_report']
    save(exp/'selection-plan.json',{'source_candidate_sha256':h,'retained_outputs':outputs,
        'selection_reason':'previously_requested_counting_and_revision_key_differences',
        'rejected_parent_not_promoted':True,'field_preservation_not_certified':True,
        'evaluation':'fresh_same_paper_count_counterfactuals_not_original_failed_heldout'})
    counts=project_generated_outputs(generated,outputs,inputs,name='revision_counts',
        description='模型生成代码的独立计数分支：修订前后对象数、重复key种类数及新增/移除唯一key数。')
    if include_details:
        # Apply the same generated duplicate-counter to the current report.
        # Only the entry field binding changes; no counting formula is authored.
        counts['program'][1]['after_duplicate_key_count']=rebind_generated_input(
            generated['program'][1]['before_duplicate_key_count'],{'before_report':'after_report'})
        counts['output_schema']['properties']['after_duplicate_key_count']=copy.deepcopy(
            counts['output_schema']['properties']['before_duplicate_key_count'])
        counts['output_schema']['required'].append('after_duplicate_key_count')
        outputs=[*outputs,'after_duplicate_key_count']
        save(exp/'duplicate-rebinding.json',{'source_output':'before_duplicate_key_count',
            'source_expression_sha256':digest(generated['program'][1]['before_duplicate_key_count']),
            'input_aliases':{'before_report':'after_report'},'target_output':'after_duplicate_key_count',
            'target_expression_sha256':digest(counts['program'][1]['after_duplicate_key_count'])})
    save(exp/'counts-candidate.json',counts)
    data=build_revision_packets(TRAIN_RUNS,root=ROOT)
    save(exp/'source-packets.json',data)
    bindings={key:accepted['input_bindings'][key] for key in inputs}
    cases=[]
    # Fresh mutations fixed by this plan, not disclosed to the old learner.
    # Repeated objects and key transitions matter; metadata never supplies counts.
    for packet in data['packets']:
        base_row=packet['before_report']['references'][0]
        for n, m in [(0,0),(0,3),(1,0),(1,4),(2,2),(3,7),(6,2),(11,17),(17,11)]:
            before=copy.deepcopy(packet['before_report']);after=copy.deepcopy(packet['after_report'])
            before['references']=[{**copy.deepcopy(base_row),'key':f'fresh-{i//2}'} for i in range(n)]
            after['references']=[{**copy.deepcopy(base_row),'key':f'fresh-{i//3+1}'} for i in range(m)]
            case={**packet,'before_report':before,'after_report':after}
            facts=revision_facts(before,after,packet['catalog'])
            cases.append({'id':f'fresh-count-{packet["packet_id"]}-{n}-{m}',
                'input':project(case,bindings),'expected':{key:facts['metrics'][key] for key in outputs}})
    # The former hidden tests are now historical diagnostics, never counted as
    # independent acceptance for this smaller tool.
    diagnostics=[]
    for c in load(source/'heldout.json'):
        expected={key:c['expected'][key] for key in outputs if key!='after_duplicate_key_count'}
        if include_details:
            catalog={'cited_records':c['input']['cited_records'],'query_items':c['input']['query_items']}
            expected['after_duplicate_key_count']=revision_facts(c['input']['before_report'],c['input']['after_report'],catalog)['metrics']['after_duplicate_key_count']
        diagnostics.append({'id':'historical-'+c['id'],'input':{key:c['input'][key] for key in inputs},'expected':expected})
    for name,rows in [('fresh-count-cases.json',cases),('historical-count-diagnostics.json',diagnostics)]:
        save(exp/name,rows)
        checked=subprocess.run([shutil.which('node'),'--experimental-strip-types',
            str(ROOT/'scripts/check-trace-rsi-tool.mjs'),str(exp/'counts-candidate.json'),str(exp/name)],
            cwd=ROOT,text=True,capture_output=True,timeout=30)
        result=json.loads(checked.stdout);save(exp/(name.replace('cases','validation').replace('diagnostics','results')),result)
        if checked.returncode or not result['passed']:raise ValueError('selected_count_branch_failed_preserve_result')
    coverage=load(ROOT/'.local/paper-reference/paper-rsi-trace-tools-20261011-v3/frozen-tool.json')
    components=[coverage['candidate'],counts]
    retention_provenance=None
    if include_retention:
        learning=ROOT/'.local/paper-reference/paper-rsi-revision-shadow-20261011-v6'
        work=learning/'runs/learn-v01/work'
        # Selected from development evidence only, before reading its untouched
        # independent cases. The parent learning run was interrupted; it and
        # its incorrect after-duplicate count are never marked successful.
        retention_sha='dec62f90106a80f650547285d8d0361e540cacd68338f0e69a53a17f3bb688bf'
        original=load(work/(retention_sha+'.candidate.json'))
        history=[json.loads(s) for s in (work/'learning.jsonl').read_text().splitlines()]
        if digest(original)!=retention_sha or not any(r['kind']=='candidate_installed' and
                r.get('candidate_sha256')==retention_sha for r in history):
            raise ValueError('audited_model_retention_candidate_required')
        kept=['existing_fields_preserved','top_level_preserved']
        save(exp/'retention-selection-plan.json',{'source_candidate_sha256':retention_sha,'retained_outputs':kept,
            'selection_basis':'development_test_12_of_14_full_candidate_passed_before_independent_projection',
            'parent_learning_status':'interrupted_not_promoted','rejected_duplicate_counter_not_retained':True})
        retention=project_generated_outputs(original,kept,inputs,name='revision_field_preservation',
            description='模型生成的完整字段对比：按key保留已有非arxiv_id字段；references之外顶层字段完整对比。')
        if include_details:
            # Export an already computed model binding; no comparison algorithm
            # is added or rewritten. This provides evidence for semantic repair.
            tail=retention['program'];bound=[]
            while tail[0]=='let':bound.append(tail[1]);tail=tail[3]
            if tail[0]!='object' or 'mismatched' not in bound:raise ValueError('model_computed_mismatch_binding_required')
            tail[1]['changed_existing_records']=['var','mismatched']
            retention['output_schema']['properties']['changed_existing_records']=copy.deepcopy(
                retention['input_schema']['properties']['after_report']['properties']['references'])
            retention['output_schema']['required'].append('changed_existing_records')
        save(exp/'retention-candidate.json',retention)
        checks=[]
        for name in ['training.json', '../../../heldout.json']:
            path=work/name
            rows=[{'id':c['id'],'input':{k:c['input'][k] for k in inputs},
                   'expected':{k:c['expected'][k] for k in kept}} for c in load(path)]
            if include_details:
                # Independent retention definition, never the production AST.
                for row in rows:
                    before=row['input']['before_report']['references'];after=row['input']['after_report']['references']
                    without=lambda r:{k:v for k,v in r.items() if k!='arxiv_id'}
                    row['expected']['changed_existing_records']=[r for r in after if
                        any(old['key']==r['key'] for old in before) and not any(
                            old['key']==r['key'] and without(old)==without(r) for old in before)]
            target='retention-development-cases.json' if name=='training.json' else 'retention-heldout-cases.json'
            save(exp/target,rows)
            checked=subprocess.run([shutil.which('node'),'--experimental-strip-types',
                str(ROOT/'scripts/check-trace-rsi-tool.mjs'),str(exp/'retention-candidate.json'),str(exp/target)],
                cwd=ROOT,text=True,capture_output=True,timeout=30)
            result=json.loads(checked.stdout);save(exp/target.replace('cases','validation'),result)
            if checked.returncode or not result['passed']:raise ValueError('retention_projection_failed_preserve_result')
            checks.append(len(rows))
        components.append(retention)
        retention_provenance={'source_candidate_sha256':retention_sha,'parent_status':'interrupted_not_promoted',
            'kept_outputs':kept,'development_cases':checks[0],'independent_cases':checks[1],
            'source_events_sha256':hashlib.sha256((learning/'runs/learn-v01/events.jsonl').read_bytes()).hexdigest(),
            'heldout_fixture_sha256':digest(load(exp/'retention-heldout-cases.json')),
            'retained_program_sha256':digest(retention['program']),
            'diagnostic_export':'existing_model_binding_mismatched' if include_details else None,
            'prior_independent_cases_replayed_without_new_model_learning':include_details}
    candidate=compose_generated_candidates(components,
        name='triage_revision_audit' if include_details else
            'triage_catalog_coverage_counts_fields' if include_retention else 'triage_catalog_coverage_counts',
        description=('组合模型生成程序：目录配对覆盖/缺失/多余/ID差异，修订前后对象数、重复key种类数和新增/移除唯一key数。'+
            ('另校验已有非arxiv_id字段和报告顶层字段保留。' if include_retention else '不检查字段保留。')+
            ('changed_existing_records返回违反保留要求的当前对象，不包括新增占位；对照before_report同key的旧版本修复。' if include_details else '')+
            '不核验文献真实性或正式版本。'))
    combined_bindings={**coverage['provenance']['proposal']['input_bindings'],**bindings}
    save(exp/'candidate.json',candidate)
    # Verify the composed AST preserves each component's output on live-source
    # derived cases. These expectations are equivalence diagnostics only.
    combined_cases=[]
    for packet in data['packets']:
        for label,case in revision_counterfactuals(packet):
            if label.startswith('null-field-'):continue
            value=project(case,combined_bindings)
            # Counts source schema intentionally excludes newly introduced report
            # fields: unknown fields cause semantic fallback, never silent loss.
            combined_cases.append({'id':label,'input':value})
    save(exp/'composition-inputs.json',combined_cases)
    save(exp/'components.json',components)
    script="""import{readFileSync}from'node:fs';import{runTraceTool,validateTraceFrozen}from'./src/adapters/trace_rsi_program.ts';
const [lib,components,rows]=process.argv.slice(1).map(p=>JSON.parse(readFileSync(p,'utf8')));validateTraceFrozen(lib);
const out=rows.map(r=>{const pick=c=>Object.fromEntries(Object.keys(c.input_schema.properties).map(k=>[k,r.input[k]]));
try{return{...r,expected:Object.assign({},...components.map(c=>runTraceTool(c,pick(c))))};}
catch(error){return{id:r.id,guard_only:true,error:String(error)}}});process.stdout.write(JSON.stringify(out));"""
    checked=subprocess.run([shutil.which('node'),'--experimental-strip-types','--input-type=module','-e',script,
        str(ROOT/'.local/paper-reference/paper-rsi-trace-tools-20261011-v3/frozen-tool.json'),
        str(exp/'components.json'),str(exp/'composition-inputs.json')],cwd=ROOT,text=True,capture_output=True,timeout=30)
    if checked.returncode:raise ValueError('inherited_coverage_certificate_or_components_invalid:'+checked.stderr[-300:])
    all_rows=json.loads(checked.stdout);rows=[r for r in all_rows if not r.get('guard_only')]
    save(exp/'composition-guard-only.json',[r for r in all_rows if r.get('guard_only')])
    save(exp/'composition-cases.json',rows)
    checked=subprocess.run([shutil.which('node'),'--experimental-strip-types',str(ROOT/'scripts/check-trace-rsi-tool.mjs'),
        str(exp/'candidate.json'),str(exp/'composition-cases.json')],cwd=ROOT,text=True,capture_output=True,timeout=30)
    result=json.loads(checked.stdout);save(exp/'composition-validation.json',result)
    if checked.returncode or not result['passed']:raise ValueError('generated_component_composition_failed')
    provenance={**accepted,'trace_bundle_sha256':digest(data),
        'proposal':{'input_bindings':combined_bindings},
        'compilation_kind':'verbatim_model_branch_projection_and_program_composition',
        'original_candidate_sha256':h,'original_learning_events_sha256':hashlib.sha256((run/'events.jsonl').read_bytes()).hexdigest(),
        'original_full_auditor_independent_acceptance':'failed_not_promoted',
        'retained_outputs':outputs,'retained_branch_sha256':{k:digest(generated['program'][1][k]) for k in outputs if k in generated['program'][1]},
        'duplicate_rebinding':load(exp/'duplicate-rebinding.json') if include_details else None,
        'coverage_manifest_digest':coverage['manifest_digest'],'coverage_certification':coverage['certification'],
        'counts_candidate_sha256':digest(counts),'retention':retention_provenance,
        'compiler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    cert={'status':'passed','kind':'source_replay','replay_method':'inherited_coverage_certificate_and_independent_count_facts',
        'heldout_cases':len(cases),'scope':('same_paper_counts_field_preservation_and_diagnostic_export' if include_details else
            'same_paper_counts_and_field_preservation' if include_retention else 'same_paper_fresh_count_mutations_and_inherited_coverage_only'),
        'historical_failed_heldout_reused_as_independent':False,'historical_bash_equivalence':False,
        'fixture_sha256':digest(cases),'composition_diagnostic_cases':len(rows),
        'field_preservation_certified':include_retention,'retention':retention_provenance,'semantic_quality':'not_reviewed',
        'model_task_validation_for_details':False if include_details else 'not_applicable'}
    body={'schema_version':1,'kind':'model_generated_trace_tool','candidate':candidate,'candidate_sha256':digest(candidate),
        'provenance':provenance,'provenance_sha256':digest(provenance),'certification':cert,'certification_sha256':digest(cert)}
    frozen={**body,'manifest_digest':digest(body)};save(exp/'frozen-tool.json',frozen)
    return {'passed':True,'new_model_requests':0,'fresh_count_cases':len(cases),
        'composition_diagnostics':len(rows),'name':candidate['name'],'manifest_digest':frozen['manifest_digest'],
        'field_preservation_certified':include_retention,'retention':retention_provenance,'actual_model_skips':0}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['preview','prepare','prepare-proposal','learn','freeze','compile-counts','compile-counts-fields','compile-counts-fields-details'],default='preview')
    parser.add_argument('--experiment',default=str(EXP.relative_to(ROOT)));parser.add_argument('--label',default='learn-v01');parser.add_argument('--call-model',action='store_true')
    args=parser.parse_args();exp=trace.private_path(args.experiment)
    if args.phase=='compile-counts':print(json.dumps(compile_counts(exp)));return
    if args.phase=='compile-counts-fields':print(json.dumps(compile_counts(exp,include_retention=True)));return
    if args.phase=='compile-counts-fields-details':print(json.dumps(compile_counts(exp,include_retention=True,include_details=True)));return
    if args.phase=='prepare-proposal':
        value=sys.stdin.read(128001)
        if len(value)>128000:raise ValueError('revision_proposal_too_large')
        print(json.dumps(prepare_proposal(exp,json.loads(value)),ensure_ascii=False));return
    if args.phase=='prepare':
        data=packets(exp);print(json.dumps({'packets':len(data['packets']),'failed_tool_counterexamples':sum(not p['motif_training_eligible'] for p in data['packets']),'model_calls':0}));return
    if args.phase=='freeze':print(json.dumps(freeze(exp,args.label)));return
    legacy=trace.parent();_,prior,_=legacy.rsi.reference.budget.account(exp)
    if args.phase=='preview':
        print(json.dumps({'paid_enabled':False,'model':'deepseek-flash','reasoning_effort':'off','output_cap':8192,
            'request_limit':None,'cumulative_cap_usd':legacy.rsi.load_budget_record(legacy.AUTH)['cap_usd'],
            'cumulative_estimated_usd':prior,'remaining_upper_bound_usd':8-prior,'execute':False}));return
    if not args.call_model:raise ValueError('explicit_call_model_required')
    with (ROOT/'.local/paper-motif/.budget.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);learn(exp,args.label)

if __name__=='__main__':main()
