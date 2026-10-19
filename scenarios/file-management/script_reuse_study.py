"""New ordinary traces -> frozen copy templates -> independent certification -> new H/S/M/L holdout."""
from __future__ import annotations
import argparse,asyncio,json,os,shutil,sys,time
from pathlib import Path
from uuid import uuid4
from common import ROOT,HERE,DATA,PREFIX,digest,sha,save,snapshot,source_code
import workflow_holdout as h
from workflow_study import PROMPT,receipt_from
from workflow_tools import workflow_version
from workflow_learning import dependencies
from experiment import accounting
from script_reuse_learning import learn,certify
WORKFLOWS=('FM05','FM17')
EXTRA=['src/adapters/dsh_learned_script.ts','scripts/audit-script-reuse.py','scripts/check-script-reuse-sdk.py',
       'tests/test_learned_script.mjs','tests/test_script_reuse_learning.py','scripts/project.mjs']

def make_template(exp,role,wid,condition,index=0):
    pair=f'{role}-{wid}-{condition}-{index}';td=exp/'templates'/pair;pristine=DATA/exp.name/'pristine'/pair;pristine.mkdir(parents=True,exist_ok=False)
    assets=ROOT/'.local/file-management-author/assets/a';pdf=sorted((ROOT/'testpdf').glob('*.pdf'))[0]
    c,o,ops,initial=h.fresh(pristine,wid,condition,exp.name+' '+pair+' '+uuid4().hex,assets,pdf)
    if condition=='E':
        for i in range(3):
            n=('source-a/extra/' if wid=='FM05' else 'source/extra/')+uuid4().hex[:9]+f'-{i}.txt'
            p=pristine/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(pair+' distinct bytes '+str(i));c['source_paths'].append(n)
            if wid=='FM05':c['allowed_reads'].append(n)
        c['source_paths']=sorted(c['source_paths']);initial=snapshot(pristine);expected=dict(initial)
        if wid=='FM05':
            groups={}
            for n in c['source_paths']:groups.setdefault(initial[n],n)
            mapping={n:'merged/'+groups[initial[n]] for n in c['source_paths']}
            for n,d in mapping.items():expected[d]=initial[n]
        else:
            mapping={n:'backup-set/'+n[len('source/'):] for n in c['source_paths']}
            for n,d in mapping.items():expected[d]=initial[n];expected['recovery-drill/'+n[len('source/'):]]=initial[n]
            o['backup_sources']=list(mapping.values())
        o.update(mapping=mapping,expected_snapshot=expected)
    # Vary public enumeration order too. The learned representative must derive
    # lexical order from actual hash members, not inherit fixture insertion order.
    c['source_paths']=list(reversed(c['source_paths'])) if index%2 or role=='certify' else c['source_paths']
    base=Path(json.loads((ROOT/'.local/file-management/workflow-current.json').read_text())['experiment']);bp=json.loads((base/'protocol.json').read_text())
    origin=next(v for v in bp['tasks'] if v['role']=='probe' and v['workflow_id']==wid and v['condition']=='N')
    spec=json.loads((Path(origin['task_dir'])/'input-template.json').read_text());save(td/'oracle.json',o)
    spec.update(task_id=pair,role=role,workspace=str(pristine),workflow_contract=c,initial_snapshot=initial,allowed_operations=ops,
                workflow_oracle_file=str(td/'oracle.json'),workflow_oracle_sha256=sha(td/'oracle.json'))
    save(td/'input-template.json',spec)
    extra='\n'+h.READ_PROMPT
    if condition=='V':extra+='\n实验程序将在预览边界改变一个文件版本。发现变化后停止，保留失败，不覆盖、不回滚未知变化、不扩大权限。'
    (td/'prompt.md').write_text(PROMPT+'\n'+spec['objective']+extra)
    cfg=json.loads((Path(origin['task_dir'])/'scenario.json').read_text());cfg['prompt']=str(td/'prompt.md');save(td/'scenario.json',cfg)
    target='backup-set/'+c['source_paths'][0][len('source/'):] if wid=='FM17' else c['source_paths'][0]
    info={'task_id':pair,'pair_id':pair,'role':role,'workflow_id':wid,'family':wid,'condition':condition,'task_dir':str(td),'pristine':str(pristine),
          'input_template_sha256':sha(td/'input-template.json'),'oracle_sha256':sha(td/'oracle.json'),'snapshot_sha256':digest(initial),'prompt_sha256':sha(td/'prompt.md'),
          'scenario_sha256':sha(td/'scenario.json'),'control':{'mode':'version' if condition=='V' else 'none','workflow_id':wid,'target':target,
              'before_sha256':initial[c['source_paths'][0]],'replacement':'FROZEN SCRIPT REUSE VERSION '+exp.name+' '+pair},'expected_delivery':condition!='V'}
    return info

def arms(exp,template,order):
    result=[]
    for arm in order:
        tid=template['task_id']+'-'+arm;td=exp/'tasks'/tid;td.mkdir(parents=True)
        for n in ('input-template.json','scenario.json'):shutil.copyfile(Path(template['task_dir'])/n,td/n)
        result.append({**template,'task_id':tid,'arm':arm,'template_dir':template['task_dir'],'task_dir':str(td)})
    return result

def prepare(training_parent=None):
    library=Path(json.loads((ROOT/'.local/file-management/workflow-learning-current.json').read_text())['experiment']);lock=json.loads((library/'library-lock.json').read_text())
    if dependencies('workflow14')!=lock['groups']['workflow14']['dependencies']:raise ValueError('existing library dependency changed')
    exp=ROOT/'.local/file-management'/('fm-script-reuse-20261014-'+uuid4().hex[:8]);exp.mkdir(mode=0o700)
    templates=[];tasks=[];probes=[]
    for role in ('probe','explore','certify'):
        for wid in WORKFLOWS:
            for condition in ('NEV' if role=='probe' else 'NE'):
                t=make_template(exp,role,wid,condition);templates.append(t)
                if role=='probe':probes.append(t)
                else:tasks+=arms(exp,t,('H',) if role=='explore' else ('H','L'))
    imports=[]
    if training_parent:
        old=training_parent.resolve();parent=json.loads((old/'protocol.json').read_text())
        if (old/'certificate.json').exists() or (old/'holdout.json').exists() or any(list(Path(c['task_dir']).glob('attempts/*/outcome.json')) for c in parent['tasks'] if c['role']=='certify'):
            raise ValueError('only unexposed ordinary exploration may be imported')
        for n,hv in dependencies('workflow14').items():
            if parent['source_code'][n]!=hv or sha(old/'frozen-source'/n)!=hv:raise ValueError('incompatible ordinary source dependency')
        selected=next(c for c in tasks if c['role']=='explore' and c['workflow_id']=='FM05' and c['condition']=='E')
        selected['task_id']+='-supplement';td=Path(selected['template_dir']);spec=json.loads((td/'input-template.json').read_text())
        spec['workflow_contract']['allowed_reads']=list(spec['workflow_contract']['context_paths']);save(td/'input-template.json',spec)
        with (td/'prompt.md').open('a') as f:f.write('\n此次探索只允许读取required_reads中的规则文本；源文件只使用实际目录和hash_files元数据，不能pin/read源内容。')
        template=next(t for t in templates if t['task_dir']==str(td));template.update(input_template_sha256=sha(td/'input-template.json'),prompt_sha256=sha(td/'prompt.md'))
        selected.update(input_template_sha256=template['input_template_sha256'],prompt_sha256=template['prompt_sha256']);shutil.copyfile(td/'input-template.json',Path(selected['task_dir'])/'input-template.json')
        tasks=[c for c in tasks if c['role']!='explore']+[selected]
        for c in parent['tasks']:
            if c['role']!='explore':continue
            f=next(Path(c['task_dir']).glob('attempts/*/outcome.json'));o=json.loads(f.read_text())
            if o['arm']!='H' or not o['normal_harness_only'] or o['learning_performed']:raise ValueError('only normal original model exploration may import')
            rec={'experiment':str(old),'protocol_sha256':sha(old/'protocol.json'),'outcome_file':str(f),'outcome_sha256':sha(f),'task_id':c['task_id']}
            imports.append(rec);tasks.append({**c,'origin_experiment':str(old)})
    patch=exp/'control.patch.yml';patch.write_text(json.dumps([{'insert':[{'id':'sss-workflow-experiment','name':(ROOT/'src/adapters/dsh_workflow_experiment.ts').as_uri()},
          {'id':'sss-learned-copy-script','name':(ROOT/'src/adapters/dsh_learned_script.ts').as_uri()}]}]))
    launcher=exp/'launcher.py';launcher.write_text("import importlib.util\ns=importlib.util.spec_from_file_location('public_runner',"+repr(str(ROOT/'scripts/run-file-scenario.py'))+");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\noriginal=m.create_harness\ndef wrapped(**kwargs):\n kwargs['patches']=tuple(kwargs['patches'])+("+repr(str(patch))+",)\n return original(**kwargs)\nm.create_harness=wrapped\nraise SystemExit(m.main())\n")
    old=Path(json.loads((ROOT/'.local/file-management/workflow-holdout-current.json').read_text())['experiment']);op=json.loads((old/'protocol.json').read_text())
    paths=sorted(set(source_code())|set(h.EXTRA)|set(EXTRA))
    for n in paths:q=exp/'frozen-source'/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,q)
    p={'experiment_id':exp.name,'type':'bounded trace-derived script reuse, generated development experiment','workflows':list(WORKFLOWS),'tasks':tasks,'templates':templates,'probes':probes,
       'source_code':{n:sha(ROOT/n) for n in paths},'test_sources':{f.name:sha(f) for f in (patch,launcher)},'library':str(library),'library_lock_sha256':sha(library/'library-lock.json'),
       'limits':h.LIMITS,'max_steps':96,'max_output':4000,'max_repairs':2,'max_cold_restarts':0,'per_task_cap_usd':5,'total_cap_usd':1000,'batch_cap_usd':180,
       'model':'deepseek-flash','reasoning_effort':'off','compression_enabled':False,'series_before':accounting(),'original_pdfs':op['original_pdfs'],'overhead_sources':op['overhead_sources'],
       'old_holdout':str(old),'old_protocol_sha256':sha(old/'protocol.json'),'old_holdout_protected':[{k:c[k] for k in ('task_dir','pristine','input_template_sha256','oracle_sha256','snapshot_sha256','prompt_sha256')} for c in op['templates']],
       'price_source':op['price_source'],'pricing_checked_client_date':'2026-10-14','runtime':op['runtime'],'human_cost_monetization':'excluded at explicit user request',
       'default_sdk_web_enabled':False,'push_enabled':False,'holdout_materials_created':False,'script_generation':'offline bounded induction from new real ordinary model tool decisions; no arbitrary code generation',
       'limits_of_claim':['two deterministic copy workflows only','known binary containers with new paths/text/rules/counts','existing Motif FM17 is ordinary fallback','human blind quality and actual bill unknown']}
    p['imported_exploration']=imports;p['training_parent']=str(training_parent.resolve()) if training_parent else None
    save(exp/'protocol.json',p);save(exp/'protocol-lock.json',{'sha256':sha(exp/'protocol.json'),'source_sha256':digest(p['source_code']),'library_lock_sha256':p['library_lock_sha256']})
    save(ROOT/'.local/file-management/script-reuse-current.json',{'experiment':str(exp)});print(json.dumps({'experiment':str(exp),'new_exploration':1 if training_parent else 4,'imported_exploration':len(imports),'independent_certification':8,'new_probes':6,'holdout_created':False,'batch_maximum_usd':180,'paid':False}),flush=True);return exp

def freeze_holdout(exp,p):
    cert=json.loads((exp/'certificate.json').read_text())
    if cert['status']!='certified' or (exp/'holdout-lock.json').exists():raise ValueError('certification must precede a fresh holdout freeze')
    templates=[];tasks=[]
    for wi,wid in enumerate(WORKFLOWS):
        for ci,condition in enumerate('NEV'):
            t=make_template(exp,'holdout',wid,condition,index=1);templates.append(t);order=('H','S','M','L');offset=(wi+ci)%4;tasks+=arms(exp,t,order[offset:]+order[:offset])
    record={'templates':templates,'tasks':tasks,'certificate_sha256':sha(exp/'certificate.json'),'candidate_lock_sha256':sha(exp/'candidate-lock.json'),
            'protocol_sha256':sha(exp/'protocol.json'),'model_holdout_runs_when_frozen':0,'learning_from_holdout_permitted':False}
    save(exp/'holdout.json',record);save(exp/'holdout-lock.json',{'sha256':sha(exp/'holdout.json')});print(json.dumps({'new_holdout_conditions':6,'four_arm_runs':24,'frozen_after_independent_certification':True}),flush=True)

def frozen(exp,p):
    h.frozen(exp,p)
    for t in p['templates']:
        if sha(Path(t['task_dir'])/'scenario.json')!=t['scenario_sha256']:raise ValueError('frozen scenario changed')
    for rec in p.get('imported_exploration',[]):
        if sha(Path(rec['experiment'])/'protocol.json')!=rec['protocol_sha256'] or sha(rec['outcome_file'])!=rec['outcome_sha256']:raise ValueError('imported original exploration changed')
    if (exp/'candidate-lock.json').exists():
        lock=json.loads((exp/'candidate-lock.json').read_text())
        for s in lock['scripts']:
            if sha(s['path'])!=s['sha256']:raise ValueError('frozen candidate changed')

def run(exp,c,p,execute=False):
    if list(Path(c['task_dir']).glob('attempts/*/outcome.json')):raise ValueError('prior attempt retained')
    if accounting()['estimated_usd']+5>1000:raise ValueError('original series budget insufficient')
    if c['arm']=='L' and not (exp/'candidate-lock.json').exists():raise ValueError('freeze candidates before execution')
    if c['role']=='holdout':
        if sha(exp/'holdout.json')!=json.loads((exp/'holdout-lock.json').read_text())['sha256']:raise ValueError('holdout changed')
        held=json.loads((exp/'holdout.json').read_text());assert held['certificate_sha256']==sha(exp/'certificate.json')
    out,spec,env,policy=h.instantiate(exp,c,p);start=time.monotonic();env.pop('SSS_LEARNED_SCRIPT_BINDING',None)
    if not execute:save(out/'preview.json',{'paid':False,'effects_enabled':False,'task':c['task_id']});return
    if c['arm']=='L':
        rec=next(r for r in json.loads((exp/'candidate-lock.json').read_text())['scripts'] if r['workflow_id']==c['workflow_id'])
        b={'role':c['role'],'script_file':rec['path'],'script_file_sha256':rec['sha256'],'task_file':str(out/'input.json'),'task_file_sha256':sha(out/'input.json'),
           'runtime_sha256':sha(ROOT/'src/adapters/dsh_learned_script.ts'),'prompt_sha256':sha(Path(c['template_dir'])/'prompt.md'),'audit_file':str(out/'learned-script-audit.jsonl')}
        if c['role']=='holdout':b.update(certificate_file=str(exp/'certificate.json'),certificate_sha256=sha(exp/'certificate.json'))
        save(out/'learned-binding.json',b);env['SSS_LEARNED_SCRIPT_BINDING']=str(out/'learned-binding.json')
    zero=c['arm']=='S';receipt=None;error=None
    print(json.dumps({'starting':c['task_id'],'role':c['role'],'cap_usd':0 if zero else 5}),flush=True)
    if zero:
        receipt,error=asyncio.run(h.zero_script(out,spec,c));runs=[{'status':'done' if receipt else 'stopped','upstream_requests':0,'budget_accounted_usd':0,'elapsed_seconds':time.monotonic()-start}]
        events=[json.loads(l) for l in (out/'mcp-calls.jsonl').read_text().splitlines()];h.mcp.accept(out,spec,receipt,0)
    else:runs,events=h.launcher_run(exp,c,p,out,spec,env,policy);receipt=receipt_from(events)
    report=json.loads((out/'delivery/report.json').read_text()) if (out/'delivery/report.json').exists() else None
    receipt_ok=bool(receipt and report and receipt['input_sha256']==digest(spec) and receipt['artifact_sha256']==digest(report));review=h.verify_workflow(spec,report if receipt_ok else None,out/'delivery',events)
    marker=json.loads((out/'control-marker.json').read_text()) if (out/'control-marker.json').exists() else None
    audit=[json.loads(l) for l in (out/'learned-script-audit.jsonl').read_text().splitlines()] if (out/'learned-script-audit.jsonl').exists() else []
    errors=sum(r.get('is_error',False) for r in events) if zero else sum(b.get('isError',False) for e in events if e.get('type')=='tool/result' for b in e['data']['message'].get('content',[]))
    fields=('upstream_requests','budget_accounted_usd','elapsed_seconds','inputTokens','cacheReadTokens','outputTokens','collection_model_requests_bypassed_verified','collection_script_batches_verified')
    combined={**runs[-1],**{k:sum(r.get(k,0) for r in runs) for k in fields},'segments':len(runs)}
    o={'task_id':c['task_id'],'pair_id':c['pair_id'],'role':c['role'],'arm':c['arm'],'workflow_id':c['workflow_id'],'condition':c['condition'],'attempt':str(out),
       'input_sha256':digest(spec),'source_sha256':digest(p['source_code']),'run':combined,'runs':runs,'events_sha256':sha(Path(runs[-1]['output_dir'])/'agent-events.jsonl') if not zero else sha(out/'mcp-calls.jsonl'),
       'receipt_verified':receipt_ok,'acceptance':review,'accounting_complete':True,'normal_harness_only':c['arm']=='H','learning_performed':False,'tool_errors':errors,'error':error,
       'zero_model':combined['upstream_requests']==0,'control_marker':marker,'condition_passed':review['passed'] if c['expected_delivery'] else bool(not review['passed'] and marker),
       'final_snapshot_sha256':digest(snapshot(spec['workspace'])),'end_to_end_seconds':time.monotonic()-start,
       'learned_script_steps':sum(r['kind']=='learned_script_step_verified' for r in audit),'learned_script_deferred':[r for r in audit if r['kind']=='learned_script_deferred']}
    save(out/'outcome.json',o);print(json.dumps({'finished':c['task_id'],'passed':review['passed'],'condition_passed':o['condition_passed'],'requests':combined['upstream_requests'],'estimated_usd':combined['budget_accounted_usd'],'script_steps':o['learned_script_steps'],'errors':review['errors']},ensure_ascii=False),flush=True);return o

def summary(exp,p):
    rows=[json.loads(f.read_text()) for f in exp.glob('tasks/*/attempts/*/outcome.json')]+[json.loads(Path(r['outcome_file']).read_text()) for r in p.get('imported_exploration',[])];setup=[r for r in rows if r['role']!='holdout'];held=[r for r in rows if r['role']=='holdout'];arms_summary={}
    for a in 'HSML':
        rr=[r for r in held if r['arm']==a];arms_summary[a]={'runs':len(rr),'delivery_passed':sum(r['acceptance']['passed'] for r in rr),'positive_passed':sum(r['condition']!='V' and r['acceptance']['passed'] for r in rr),
          'positive_conditions':sum(r['condition']!='V' for r in rr),'expected_stops':sum(r['condition']=='V' and r['condition_passed'] for r in rr),'tool_errors':sum(r['tool_errors'] for r in rr),
          **{k:sum(r['run'].get(k,0) for r in rr) for k in ('upstream_requests','budget_accounted_usd','elapsed_seconds')}}
    upfront=sum(r['run']['budget_accounted_usd'] for r in setup);arms_summary['L']['full_model_cost_usd']=upfront+arms_summary['L']['budget_accounted_usd']
    arms_summary['M']['full_model_cost_usd']=sum(r['estimated_usd'] for r in p['overhead_sources'])+arms_summary['M']['budget_accounted_usd']
    groups={}
    for o in held:groups.setdefault(o['pair_id'],{})[o['arm']]=o
    common=[g for g in groups.values() if set(g)==set('HSML') and all(o['acceptance']['passed'] for o in g.values())]
    result={'experiment_id':exp.name,'attempts':len(rows),'setup_runs':len(setup),'setup_cost_usd':upfront,'setup_requests':sum(r['run']['upstream_requests'] for r in setup),'holdout_runs':len(held),
      'arms':arms_summary,'jointly_qualified_conditions':len(common),'jointly_qualified_execution':{a:{k:sum(g[a]['run'].get(k,0) for g in common) for k in ('upstream_requests','budget_accounted_usd')} for a in 'HSML'},
      'series':accounting(),'human_blind_review':False,'actual_bill_verified':False,'outcomes':rows}
    save(exp/'summary.json',result);return result

def main():
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path);a.add_argument('--training-parent',type=Path);a.add_argument('--role',choices=['explore','certify','holdout']);a.add_argument('--case');a.add_argument('--call-model',action='store_true');a.add_argument('--free',action='store_true');a.add_argument('--learn',action='store_true');a.add_argument('--certify',action='store_true');a.add_argument('--freeze-holdout',action='store_true');a.add_argument('--summary',action='store_true');args=a.parse_args()
    if not args.experiment:prepare(args.training_parent);return
    exp=args.experiment.resolve();p=json.loads((exp/'protocol.json').read_text())
    if args.summary:print(json.dumps({k:v for k,v in summary(exp,p).items() if k!='outcomes'}));return
    frozen(exp,p)
    if args.learn:learn(exp,p);return
    if args.certify:certify(exp,p);return
    if args.freeze_holdout:freeze_holdout(exp,p);return
    if args.call_model and not args.role:a.error('explicit phase required for authorized execution')
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:
        if args.free:
            rows=[asyncio.run(h.mcp.probe(exp,c)) for c in p['probes']];save(exp/'free-summary.json',{'checks':len(rows),'passed':sum(r['status']=='passed' for r in rows),'real_api_requests':0,'results':rows})
            if any(r['status']!='passed' for r in rows):raise ValueError('free probe failed')
            print(json.dumps({'free_checks':len(rows),'passed':len(rows),'real_api_requests':0}),flush=True);return
        if args.role=='certify' and not (exp/'candidate-lock.json').exists():raise ValueError('freeze candidates first')
        if args.role=='holdout':tasks=json.loads((exp/'holdout.json').read_text())['tasks']
        else:tasks=p['tasks']
        for c in tasks:
            if args.role and c['role']!=args.role or args.case and args.case!=c['task_id']:continue
            if list(Path(c['task_dir']).glob('attempts/*/outcome.json')):continue
            frozen(exp,p);run(exp,c,p,args.call_model)
            if args.call_model:summary(exp,p)
    finally:lock.unlink()
if __name__=='__main__':main()
