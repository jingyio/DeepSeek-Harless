"""Offline induction of bounded copy programs from new ordinary model decisions only."""
from __future__ import annotations
import json,sys,subprocess
from pathlib import Path,PurePosixPath
from common import ROOT,PREFIX,digest,sha,save
sys.path.insert(0,str(ROOT))
from src.motif_core.offline.plan_compiler import native_rows
NAMES=('read_task','list_files','pin_file','read_file','hash_files','preview_actions','execute_plan','submit_report')

def load_witness(case):
    f=next(Path(case['task_dir']).glob('attempts/*/outcome.json'));o=json.loads(f.read_text());a=f.parent
    if case['role']!='explore' or o['role']!='explore' or o['arm']!='H' or not o['normal_harness_only'] or o['learning_performed']:
        raise ValueError('only new ordinary exploration may induce scripts')
    if not o['acceptance']['passed'] or not o['receipt_verified'] or o['run']['status']!='done':raise ValueError('failed exploration retained but excluded')
    spec=json.loads((a/'input.json').read_text());events_file=Path(o['run']['output_dir'])/'agent-events.jsonl'
    if digest(spec)!=o['input_sha256'] or sha(events_file)!=o['events_sha256']:raise ValueError('source evidence changed')
    events=[json.loads(v) for v in events_file.read_text().splitlines()];rows=native_rows(events)
    by=lambda n:[r for r in rows if r['name']==PREFIX+n and r['out']]
    task=by('read_task')[0]['out'];c=task['workflow_contract']
    if task['allowed_operations']!=['copy'] or c['required_reads']!=c['context_paths'] or len(c['context_paths'])>1:raise ValueError('unsupported task/reading footprint')
    reads=by('read_file');context_text=None
    if c['context_paths']:
        packets=[r['out'] for r in reads if r['out']['path']==c['context_paths'][0]]
        if not packets or any(v['status']!='readable' or v.get('truncated') for v in packets) or len({digest(v['text']) for v in packets})!=1:raise ValueError('context text not actually established')
        context_text=digest(packets[0]['text'])
    if any(r['out']['path'] not in c['context_paths'] for r in reads):raise ValueError('program has unmodeled semantic reads')
    before=dict(spec['initial_snapshot']);ids=lambda:{'file:local:'+digest({'path':n,'sha':h})[:24]:n for n,h in before.items() if n!='.experiment-copy'}
    stages=[];executions=by('execute_plan');previews={r['out']['plan_id']:r for r in by('preview_actions')}
    if not executions:raise ValueError('no real successful copy execution')
    for x in executions:
        p=previews.get(x['args']['plan_id']);out=x['out']
        if not p or p['result_seq']>=x['message_seq'] or out['plan_id']!=p['out']['plan_id'] or out['status']!='executed_verified':raise ValueError('plan dataflow not established')
        actions=p['out']['actions'];known=ids()
        pairs=[]
        for v in actions:
            if v['op']!='copy' or v['format']!='none' or len(v['file_ids'])!=1 or v['file_ids'][0] not in known or v['destination'] in before:raise ValueError('unmodeled effect')
            n=known[v['file_ids'][0]];d=v['destination'];pairs.append((n,d));before[d]=before[n]
        if out['snapshot_sha256']!=digest(before) or out['operation_count']!=len(pairs):raise ValueError('actual copied bytes differ')
        # Consolidate adjacent plans with the same public destination grant; the
        # template uses one bounded batch rather than retaining temporary IDs.
        prefixes={next((d for d in c['destination_prefixes'] if b.startswith(d)),None) for _,b in pairs}
        if None in prefixes or len(prefixes)!=1:raise ValueError('ambiguous destination transform')
        prefix=prefixes.pop()
        if stages and stages[-1]['destination_prefix']==prefix:stages[-1]['pairs']+=pairs
        else:stages.append({'destination_prefix':prefix,'pairs':pairs})
    steps=[];prior=[];hashes=by('hash_files')
    for i,stage in enumerate(stages):
        pairs=stage['pairs'];src=[n for n,_ in pairs]
        if len(src)!=len(set(src)):raise ValueError('repeated source cannot become a loop')
        if set(src)==set(c['source_paths']):source='task_sources'
        elif i and set(src)==set(prior):source='prior_targets'
        elif not i and hashes:
            scopes=[r for r in hashes if {v['file_id'] for g in r['out']['groups'] for v in g['files']}==
                    {'file:local:'+digest({'path':n,'sha':spec['initial_snapshot'][n]})[:24] for n in c['source_paths']}]
            choices=[r for r in scopes if {min(g['files'],key=lambda v:v['path'])['path'] for g in r['out']['groups']}==set(src)]
            if not choices or context_text is None:raise ValueError('lexical representative hypothesis lacks actual rule/hash/action evidence')
            source='hash_representatives';steps.append({'op':'hash_representatives'})
        else:raise ValueError('copy selection cannot be generalized from native evidence')
        # Infer a prefix replacement from every witnessed source/destination.
        strips=set()
        for n,d in pairs:
            suffix=d[len(stage['destination_prefix']):]
            if not suffix or not n.endswith(suffix):raise ValueError('destination is not a parameterized source suffix')
            strips.add(n[:-len(suffix)])
        if len(strips)!=1:raise ValueError('inconsistent path transform')
        strip=strips.pop()
        if strip and not strip.endswith('/'):raise ValueError('transform must end at directory boundary')
        steps.append({'op':'copy_map','source':source,'strip_prefix':strip,'destination_prefix':stage['destination_prefix']});prior=[d for _,d in pairs]
    schema={PREFIX+r['name']:r.get('inputSchema',r.get('input_schema')) for r in json.loads((a/'tool-schemas.json').read_text())}
    fingerprint=digest({'objective':spec['objective'],'initial_snapshot':spec['initial_snapshot'],'contract':c})
    program={'schema_version':1,'format':'sss-learned-copy-script-v1','workflow_id':c['workflow_id'],
             'objective_sha256':digest(spec['objective']),'execution_version_sha256':task['workflow_execution_version_sha256'],
             'destination_prefixes':c['destination_prefixes'],'context_text_sha256':context_text,'steps':steps,
             'tool_schema_sha256':{PREFIX+n:digest(schema[PREFIX+n]) for n in NAMES}}
    witness={'role':'explore','task_id':case['task_id'],'task_fingerprint':fingerprint,'events_sha256':sha(events_file),
             'outcome_file':str(f),'outcome_sha256':sha(f),'input_sha256':digest(spec),'source_count':len(c['source_paths']),
             'executed_pairs':sum(len(s['pairs']) for s in stages),'native_tool_calls':len(rows),'runtime_nodes':0}
    return program,witness

def learn(exp,p):
    if (exp/'candidate-lock.json').exists():raise ValueError('candidate retained; new exploration version needed')
    if any(list(Path(c['task_dir']).glob('attempts/*/outcome.json')) for c in p['tasks'] if c['role']=='certify'):raise ValueError('candidate must freeze before certification exposure')
    groups={};excluded=[]
    for c in p['tasks']:
        if c['role']!='explore':continue
        try:program,witness=load_witness(c)
        except ValueError as e:excluded.append({'task_id':c['task_id'],'reason':str(e)});continue
        groups.setdefault(program['workflow_id'],[]).append((program,witness))
    scripts=[]
    for wid,values in groups.items():
        if len(values)<2 or len({digest(v[0]) for v in values})!=1 or len({v[1]['source_count'] for v in values})<2:raise ValueError('two varied, agreeing native witnesses required: '+wid)
        s={**values[0][0],'training':[v[1] for v in values]};s['script_digest']=digest(s);f=exp/'candidates'/(wid+'.json');save(f,s)
        subprocess.run(['node','--input-type=module','-e',"import fs from 'node:fs';import {validateScript} from './src/adapters/dsh_learned_script.ts';validateScript(JSON.parse(fs.readFileSync(process.argv[1],'utf8')));",str(f)],cwd=ROOT,check=True,capture_output=True)
        scripts.append({'workflow_id':wid,'path':str(f),'sha256':sha(f),'script_digest':s['script_digest']})
    if set(groups)!=set(p['workflows']):raise ValueError('not all selected workflows have usable new evidence')
    save(exp/'candidate-lock.json',{'scripts':scripts,'excluded':excluded,'source_sha256':sha(__file__),'protocol_sha256':sha(exp/'protocol.json'),
         'holdout_used':False,'certification_used':False,'model_generation_cost_usd':0,'induction':'bounded relational prefix/selection hypotheses from actual model-selected effects; no arbitrary code synthesis'})
    print(json.dumps({'scripts':len(scripts),'excluded':excluded,'holdout_used':False}),flush=True)

def certify(exp,p):
    if (exp/'certificate.json').exists():raise ValueError('certificate retained; never revise with validation data')
    lock=json.loads((exp/'candidate-lock.json').read_text());reviews=[]
    for rec in lock['scripts']:
        assert sha(rec['path'])==rec['sha256']
        s=json.loads(Path(rec['path']).read_text());training={v['task_fingerprint'] for v in s['training']}
        for c in p['tasks']:
            if c['role']!='certify' or c['workflow_id']!=rec['workflow_id']:continue
            f=next(Path(c['task_dir']).glob('attempts/*/outcome.json'));o=json.loads(f.read_text());spec=json.loads((f.parent/'input.json').read_text())
            fp=digest({'objective':spec['objective'],'initial_snapshot':spec['initial_snapshot'],'contract':spec['workflow_contract']})
            if fp in training or not o['acceptance']['passed'] or not o['receipt_verified']:raise ValueError('independent actual candidate execution failed; preserve candidate and failures')
            if c['arm']=='L' and (o['learned_script_steps']==0 or o['learned_script_deferred']):raise ValueError('ordinary fallback cannot certify a script')
            reviews.append({'task_id':c['task_id'],'arm':c['arm'],'task_fingerprint':fp,'outcome_file':str(f),'outcome_sha256':sha(f),'actual_candidate_execution':c['arm']=='L'})
    if len(reviews)!=8:raise ValueError('four ordinary reference and four actual candidate certification runs required')
    result={'status':'certified','scripts':lock['scripts'],'candidate_lock_sha256':sha(exp/'candidate-lock.json'),'reviews':reviews,
            'source_sha256':sha(__file__),'human_semantic_review':False,'holdout_used':False,'arbitrary_programs_certified':False}
    save(exp/'certificate.json',result);print(json.dumps({'status':'certified','scripts':2,'independent_runs':8,'holdout_used':False}),flush=True)
