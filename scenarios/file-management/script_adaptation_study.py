"""Frozen rule/directory changes, real v1 repair, new ordinary v2 evidence and five-arm holdout."""
from __future__ import annotations
import argparse,asyncio,json,os,shutil,sys,time
from pathlib import Path
from uuid import uuid4
from common import ROOT,HERE,DATA,PREFIX,digest,sha,save,snapshot,source_code
import workflow_holdout as h
from script_reuse_study import arms
from workflow_study import PROMPT,receipt_from
from workflow_learning import dependencies
from experiment import accounting
from script_adaptation_learning import learn,certify,RUNTIME_FILES
PROFILES=('FM05:min','FM05:max','FM17:all','FM17:filtered')
ARMS=('H','S','M','L1','L2')
EXTRA=['src/adapters/dsh_learned_script.ts','src/adapters/dsh_learned_script_v2.ts','src/adapters/dsh_script_repair_probe.ts',
       'src/motif_core/terminal_receipt_policy.ts','scripts/audit-script-adaptation.py','scripts/check-script-adaptation-sdk.py',
       'tests/test_script_adaptation.mjs','tests/test_script_adaptation_learning.py','scripts/project.mjs']

def template(exp,role,profile,layout,i,label):
    wid,rule=profile.split(':');pair=f'{role}-{wid}-{rule}-{label}';td=exp/'templates'/pair;work=DATA/exp.name/'pristine'/pair;work.mkdir(parents=True,exist_ok=False)
    c,o,ops,_=h.fresh(work,wid,'N' if i==0 else 'E',exp.name+' '+pair+' '+uuid4().hex,ROOT/'.local/file-management-author/assets/a',sorted((ROOT/'testpdf').glob('*.pdf'))[0])
    if layout:
        names={n:(n.replace('source-a/','incoming/a/batch/',1).replace('source-b/','incoming/b/batch/',1) if wid=='FM05' else n.replace('source/','source/reorganized/archive/',1)) for n in c['source_paths']}
        for n,d in names.items():p=work/d;p.parent.mkdir(parents=True,exist_ok=True);(work/n).rename(p)
        c['source_paths']=[names[n] for n in c['source_paths']]
    stem=('incoming/a/batch/extra/' if layout else 'source-a/extra/') if wid=='FM05' else ('source/reorganized/archive/extra/' if layout else 'source/extra/')
    for k in range(2 if i==0 else 5):
        n=stem+uuid4().hex[:8]+'.txt';p=work/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(pair+' unique evidence '+str(k));c['source_paths'].append(n)
    if wid=='FM17':
        for k in range(2 if i==0 else 4):
            n=stem+uuid4().hex[:8]+('.TXT' if k%2 else '.txt');(work/n).write_text('');c['source_paths'].append(n)
        n=stem+uuid4().hex[:8]+'.md';(work/n).write_text('');c['source_paths'].append(n)
    base=Path(json.loads((ROOT/'.local/file-management/workflow-current.json').read_text())['experiment']);bp=json.loads((base/'protocol.json').read_text())
    origin=next(v for v in bp['tasks'] if v['role']=='probe' and v['workflow_id']==wid and v['condition']=='N')
    spec=json.loads((Path(origin['task_dir'])/'input-template.json').read_text())
    if wid=='FM05':
        target='consolidated/' if layout else 'merged/';c['destination_prefixes']=[target]
        text='Group exact SHA duplicates; output each group once at '+target+'<lexicographically '+('first' if rule=='min' else 'GREATEST')+' FULL source path>. Keep all sources. Different bytes at same relative name must both survive.'
        (work/c['context_paths'][0]).write_text(text)
        if layout:spec['objective']='Merge the actual workflow source_paths according to rules/merge.txt; group equal SHA, copy one representative per group under the current destination_prefixes using its full source path. Preserve all sources.'
    elif rule=='filtered':
        n='rules/backup-selection.txt';p=work/n;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('Use actual list_files metadata. Skip original .txt files (case-insensitive extension) whose bytes are exactly 0; keep every other original, including zero-byte .md. Copy selected originals to backup-set/<source-relative path>, refresh actual identities, then copy FROM actual backups to recovery-drill/<same relative path>. Preserve all originals and skipped files. Complete ALL backups before starting the recovery drill.')
        c['context_paths']=[n];spec['objective']='Read rules/backup-selection.txt; use only original metadata to select nonempty .txt and all other files, including empty .md. Skip empty .txt. Back up selected sources, then recover FROM actual backup files; preserve originals and verify bytes.'
    c['required_reads']=list(c['context_paths']);c['allowed_reads']=list(c['context_paths'])
    c['source_paths']=list(reversed(sorted(c['source_paths']))) if i else sorted(c['source_paths']);initial=snapshot(work);expected=dict(initial)
    if wid=='FM05':
        groups={}
        for n in c['source_paths']:groups.setdefault(initial[n],[]).append(n)
        representatives={b:(min(v) if rule=='min' else max(v)) for b,v in groups.items()};mapping={n:c['destination_prefixes'][0]+representatives[initial[n]] for n in c['source_paths']}
        for n,d in mapping.items():expected[d]=initial[n]
    else:
        selected=[n for n in c['source_paths'] if rule!='filtered' or not (Path(n).suffix.lower()=='.txt' and (work/n).stat().st_size==0)]
        mapping={n:'backup-set/'+n[len('source/'):] for n in selected}
        for n,d in mapping.items():expected[d]=initial[n];expected['recovery-drill/'+n[len('source/'):]]=initial[n]
        o['backup_sources']=list(mapping.values())
    o.update(expected_snapshot=expected,mapping=mapping,required_gap_markers=[],require_effects=True)
    save(td/'oracle.json',o);spec.update(task_id=pair,role=role,workspace=str(work),workflow_contract=c,initial_snapshot=initial,allowed_operations=ops,
        workflow_oracle_file=str(td/'oracle.json'),workflow_oracle_sha256=sha(td/'oracle.json'))
    save(td/'input-template.json',spec)
    text=PROMPT+'\n'+spec['objective']+'\n只读context_paths中的真实规则；源内容没有读取权限，必须使用list_files/hash_files元数据。先完成全部选中备份、再刷新身份、再从实际备份恢复，不穿插。'
    if wid=='FM05':text+='\n执行复制前，用一次真实hash_files覆盖全部source_paths，按真实SHA分组，再按规则选择每组的完整路径代表。'
    else:text+='\n路径口径：原路径只去掉开头一次source/，后面的全部子目录必须保留。例如source/reorganized/archive/a.txt备份为backup-set/reorganized/archive/a.txt。恢复必须使用实际备份文件的新file_id，备份路径只去掉开头一次backup-set/，再加recovery-drill/。不要把source/带进备份目标，也不要丢掉reorganized/archive/。'
    if label=='V':text+='\n本次实验将在预览边界改变一个版本。发现外部变化后停止，不覆盖或恢复未知变化、不扩大权限，保留未完成。'
    (td/'prompt.md').write_text(text);cfg=json.loads((Path(origin['task_dir'])/'scenario.json').read_text());cfg['prompt']=str(td/'prompt.md');save(td/'scenario.json',cfg)
    target_source=next(iter(mapping))
    return {'task_id':pair,'pair_id':pair,'role':role,'profile_id':profile,'workflow_id':wid,'family':wid,'condition':label,'layout_changed':layout,
       'task_dir':str(td),'pristine':str(work),'input_template_sha256':sha(td/'input-template.json'),'oracle_sha256':sha(td/'oracle.json'),'snapshot_sha256':digest(initial),
       'prompt_sha256':sha(td/'prompt.md'),'scenario_sha256':sha(td/'scenario.json'),'expected_delivery':label!='V',
       'control':{'mode':'version' if label=='V' else 'none','workflow_id':wid,'target':target_source if wid=='FM05' else mapping[target_source],
         'before_sha256':initial[target_source],'replacement':'FROZEN ADAPTATION VERSION '+exp.name+' '+pair}}

def imported_evidence(old):
    """Read-only maintenance evidence; never import exposed certification/holdout."""
    parent=json.loads((old/'protocol.json').read_text())
    if sha(old/'protocol.json')!=json.loads((old/'protocol-lock.json').read_text())['sha256']:raise ValueError('import protocol changed')
    if any((old/n).exists() for n in ('candidate-lock.json','certificate-v2.json','holdout.json')) or any(list(Path(c['task_dir']).glob('attempts/*/outcome.json')) for c in parent['tasks'] if c['role']=='certify'):
        raise ValueError('only pre-certification maintenance evidence may import')
    for n,hv in dependencies('workflow14').items():
        if parent['source_code'][n]!=hv or sha(old/'frozen-source'/n)!=hv:raise ValueError('incompatible MCP evidence dependency')
    tasks=[];records=[]
    for c in parent['tasks']:
        if c['role'] not in ('validate','explore'):continue
        files=list(Path(c['task_dir']).glob('attempts/*/outcome.json'))
        if len(files)!=1:raise ValueError('complete original maintenance outcome required')
        f=files[0];o=json.loads(f.read_text())
        if c['role']=='explore' and (o['arm']!='H' or not o['normal_harness_only'] or o['learning_performed']):raise ValueError('ordinary exploration only')
        tasks.append({**c,'origin_experiment':str(old)})
        records.append({'experiment':str(old),'protocol_sha256':sha(old/'protocol.json'),'outcome_file':str(f),'outcome_sha256':sha(f),'task_id':c['task_id']})
    return tasks,records,{str(q):sha(q) for q in old.rglob('*') if q.is_file()}

def prepare(training_parent=None):
    parent=Path(json.loads((ROOT/'.local/file-management/script-reuse-current.json').read_text())['experiment']);old=json.loads((parent/'protocol.json').read_text())
    if dependencies('workflow14')!=json.loads((Path(old['library'])/'library-lock.json').read_text())['groups']['workflow14']['dependencies']:raise ValueError('original MCP/library version changed')
    exp=ROOT/'.local/file-management'/('fm-script-adaptation-20261014-'+uuid4().hex[:8]);exp.mkdir(mode=0o700);templates=[];tasks=[];probes=[]
    for wid in ('FM05','FM17'):
        for condition in ('R','D','RD','V'):
            profile=wid+':'+(('min' if wid=='FM05' else 'all') if condition=='D' else ('max' if wid=='FM05' else 'filtered'))
            t=template(exp,'probe',profile,condition!='R',1,condition);templates.append(t);probes.append(t)
            if condition!='V' and (not training_parent or wid=='FM17' and condition=='RD'):
                t=template(exp,'validate',profile,condition!='R',1,condition+('-clarified' if training_parent else ''));t['condition']=condition;templates.append(t);rr=arms(exp,t,('L1',));rr[0]['controlled_draft']=condition in ('R','RD');tasks+=rr
    for role in ('explore','certify'):
        for profile in PROFILES:
            for i in (0,1):
                if training_parent and role=='explore' and (profile,i) not in (('FM05:min',0),('FM17:filtered',1)):continue
                label=('base' if not i else 'dirs')+('-clarified' if training_parent and role=='explore' else '')
                t=template(exp,role,profile,bool(i),i,label);templates.append(t);tasks+=arms(exp,t,('H',) if role=='explore' else ('L2',))
    imports=[];protected={}
    if training_parent:
        imported,imports,protected=imported_evidence(training_parent.resolve());tasks+=imported
    patch=exp/'control.patch.yml';patch.write_text(json.dumps([{'insert':[
      {'id':'sss-workflow-experiment','name':(ROOT/'src/adapters/dsh_workflow_experiment.ts').as_uri()},
      {'id':'sss-learned-copy-script','name':(ROOT/'src/adapters/dsh_learned_script.ts').as_uri()},
      {'id':'sss-learned-copy-script-v2','name':(ROOT/'src/adapters/dsh_learned_script_v2.ts').as_uri()},
      {'id':'sss-script-repair-probe','name':(ROOT/'src/adapters/dsh_script_repair_probe.ts').as_uri()}]}]))
    launcher=exp/'launcher.py';launcher.write_text("import importlib.util\ns=importlib.util.spec_from_file_location('public_runner',"+repr(str(ROOT/'scripts/run-file-scenario.py'))+");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\noriginal=m.create_harness\ndef wrapped(**kwargs):\n kwargs['patches']=tuple(kwargs['patches'])+("+repr(str(patch))+",)\n return original(**kwargs)\nm.create_harness=wrapped\nraise SystemExit(m.main())\n")
    paths=sorted(set(source_code())|set(h.EXTRA)|set(EXTRA))
    for n in paths:q=exp/'frozen-source'/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,q)
    p={**{k:old[k] for k in ('library','library_lock_sha256','limits','max_steps','max_output','max_repairs','max_cold_restarts','per_task_cap_usd','total_cap_usd','model','reasoning_effort','compression_enabled','original_pdfs','overhead_sources','runtime','price_source','human_cost_monetization')},
       'experiment_id':exp.name,'type':'generated rule and directory adaptation, v1 invalidation/real repair, v2 certification and five-arm holdout',
       'tasks':tasks,'templates':templates,'probes':probes,'expected_profiles':list(PROFILES),'source_code':{n:sha(ROOT/n) for n in paths},'test_sources':{q.name:sha(q) for q in (patch,launcher)},
       'parent':str(parent),'parent_protocol_sha256':sha(parent/'protocol.json'),'parent_certificate_sha256':sha(parent/'certificate.json'),
       'v1_scripts':json.loads((parent/'candidate-lock.json').read_text())['scripts'],'v1_upfront_usd':json.loads((parent/'summary.json').read_text())['setup_cost_usd'],
       'v1_protected':{str(q):sha(q) for q in parent.rglob('*') if q.is_file()},'batch_cap_usd':325 if training_parent else 310,'planned_holdout_runs':40,'series_before':accounting(),
       'imported_maintenance':imports,'imported_protected':protected,'training_parent':str(training_parent.resolve()) if training_parent else None,
       'pricing_checked_client_date':'2026-10-14','default_sdk_web_enabled':False,'push_enabled':False,'holdout_created':False,
       'validation_control':'four explicit uncompleted draft stops after actual v1 deferral; no fake model decision or successful receipt; same fixed acceptance and real ordinary repair',
       'maintenance_model_cost_includes':['v1 validation and real repair','new normal exploration including exclusions','independent v2 certification','all new failures/repair'],
       'learning_performed':False,'human_blind_review':False}
    save(exp/'protocol.json',p);save(exp/'protocol-lock.json',{'sha256':sha(exp/'protocol.json')});save(ROOT/'.local/file-management/script-adaptation-current.json',{'experiment':str(exp)})
    print(json.dumps({'experiment':str(exp),'validation':1 if training_parent else 6,'new_ordinary_exploration':2 if training_parent else 8,'imported_maintenance':len(imports),'independent_certification':8,'holdout_after_certification':40,'batch_maximum_usd':p['batch_cap_usd'],'paid':False}),flush=True);return exp

def frozen(exp,p,docs=False):
    if sha(exp/'protocol.json')!=json.loads((exp/'protocol-lock.json').read_text())['sha256']:raise ValueError('protocol changed')
    for n,hv in p['source_code'].items():
        if sha(ROOT/n)!=hv and not (docs and n.endswith('.md') and n.startswith('scenarios/file-management/')):raise ValueError('execution source changed: '+n)
    for n,hv in p['v1_protected'].items():
        if sha(n)!=hv:raise ValueError('original v1 evidence changed')
    for n,hv in p.get('imported_protected',{}).items():
        if sha(n)!=hv:raise ValueError('original adaptation evidence changed')
    if sha(Path(p['library'])/'library-lock.json')!=p['library_lock_sha256']:raise ValueError('original Motif changed')
    for t in p['templates']:
        td=Path(t['task_dir'])
        if any(sha(td/n)!=t[k] for n,k in [('input-template.json','input_template_sha256'),('oracle.json','oracle_sha256'),('prompt.md','prompt_sha256'),('scenario.json','scenario_sha256')]) or digest(snapshot(t['pristine']))!=t['snapshot_sha256']:raise ValueError('template changed')
    if (exp/'candidate-lock.json').exists():
        for s in json.loads((exp/'candidate-lock.json').read_text())['scripts']:
            if sha(s['path'])!=s['sha256']:raise ValueError('candidate changed')

async def fixed_script(out,spec,c):
    receipt=None;error=None
    try:
        async with h.mcp.Connection(out,spec) as conn:
            task=await conn.call('read_task');data=await conn.call('list_files');inventory={r['path']:r for r in data['files']};texts=[]
            for n in task['workflow_contract']['context_paths']:
                pin=await conn.call('pin_file',{'file_id':inventory[n]['file_id']});row=await conn.call('read_file',{'source_id':pin['source_id']});texts.append(row['text'])
            sources=[inventory[n] for n in task['workflow_contract']['source_paths']]
            if c['workflow_id']=='FM05':
                text=texts[0];order='min' if 'lexicographically first FULL source path' in text else 'max' if 'lexicographically GREATEST FULL source path' in text else None
                if order is None:raise ValueError('fixed baseline rule not recognized')
                grouped=await conn.call('hash_files',{'file_ids':[r['file_id'] for r in sources]});fn=min if order=='min' else max
                chosen=[fn(g['files'],key=lambda r:r['path']) for g in grouped['groups']]
                aa=[{'op':'copy','file_ids':[r['file_id']],'destination':task['workflow_contract']['destination_prefixes'][0]+r['path']} for r in chosen]
            else:
                if texts:
                    if len(texts)!=1 or 'Skip original .txt files (case-insensitive extension) whose bytes are exactly 0' not in texts[0]:raise ValueError('fixed backup rule not recognized')
                    sources=[r for r in sources if not (r['extension']=='.txt' and r['bytes']==0)]
                aa=[{'op':'copy','file_ids':[r['file_id']],'destination':'backup-set/'+r['path'][len('source/'):]} for r in sources]
            preview=await conn.call('preview_actions',{'actions':aa})
            if c['workflow_id']=='FM05' and c['condition']=='V':h.mutate(out,spec,c)
            await conn.call('execute_plan',{'plan_id':preview['plan_id']})
            if c['workflow_id']=='FM17':
                inventory={r['path']:r for r in (await conn.call('list_files'))['files']}
                aa=[{'op':'copy','file_ids':[inventory['backup-set/'+r['path'][len('source/'):]]['file_id']],'destination':'recovery-drill/'+r['path'][len('source/'):]} for r in sources]
                preview=await conn.call('preview_actions',{'actions':aa})
                if c['condition']=='V':h.mutate(out,spec,c)
                await conn.call('execute_plan',{'plan_id':preview['plan_id']})
            rows=(await conn.call('list_files'))['files'];receipt=await conn.call('submit_report',{'summary':'Maintained prewritten metadata program; actual rules, SHA groups and backup identities; no hidden oracle','file_ids':[r['file_id'] for r in rows],'gaps':[],'report_kind':'task_result'})
    except Exception as e:error=type(e).__name__+': '+str(e)
    return receipt,error

def bind(exp,c,p,out,spec,env,free=False):
    for n in ('SSS_LEARNED_SCRIPT_BINDING','SSS_LEARNED_SCRIPT_V2_BINDING','SSS_SCRIPT_REPAIR_PROBE'):env.pop(n,None)
    if c['arm'] not in ('L1','L2'):return
    v1=c['arm']=='L1';record=next(r for r in (p['v1_scripts'] if v1 else json.loads((exp/'candidate-lock.json').read_text())['scripts']) if (r['workflow_id']==c['workflow_id'] if v1 else r['profile_id']==c['profile_id']))
    b={'role':'free' if free else 'holdout' if v1 else c['role'],'script_file':record['path'],'script_file_sha256':record['sha256'],
       'task_file':str(out/'input.json'),'task_file_sha256':sha(out/'input.json'),'prompt_sha256':c['prompt_sha256'],
       'runtime_sha256':sha(ROOT/('src/adapters/dsh_learned_script.ts' if v1 else 'src/adapters/dsh_learned_script_v2.ts')),'audit_file':str(out/'script-audit.jsonl')}
    if b['role']=='holdout':
        cert=Path(p['parent'])/'certificate.json' if v1 else exp/'certificate-v2.json';b.update(certificate_file=str(cert),certificate_sha256=sha(cert))
    save(out/'script-binding.json',b);env['SSS_LEARNED_SCRIPT_BINDING' if v1 else 'SSS_LEARNED_SCRIPT_V2_BINDING']=str(out/'script-binding.json')
    if c.get('controlled_draft'):
        save(out/'repair-probe.json',{'enabled':True,'audit_file':b['audit_file'],'marker':str(out/'repair-probe-marker.json')});env['SSS_SCRIPT_REPAIR_PROBE']=str(out/'repair-probe.json')

def run(exp,c,p,execute=False):
    if list(Path(c['task_dir']).glob('attempts/*/outcome.json')):raise ValueError('prior result retained')
    if accounting()['estimated_usd']+5>1000:raise ValueError('original budget insufficient')
    out,spec,env,policy=h.instantiate(exp,c,p);start=time.monotonic()
    if not execute:save(out/'preview.json',{'paid':False,'effects_enabled':False,'task':c['task_id']});return
    bind(exp,c,p,out,spec,env)
    print(json.dumps({'starting':c['task_id'],'role':c['role'],'cap_usd':0 if c['arm']=='S' else 5}),flush=True);receipt=None;error=None
    if c['arm']=='S':
        receipt,error=asyncio.run(fixed_script(out,spec,c));runs=[{'status':'done' if receipt else 'stopped','upstream_requests':0,'budget_accounted_usd':0,'elapsed_seconds':time.monotonic()-start}]
        events=[json.loads(l) for l in (out/'mcp-calls.jsonl').read_text().splitlines()];h.mcp.accept(out,spec,receipt,0)
    else:runs,events=h.launcher_run(exp,c,p,out,spec,env,policy);receipt=receipt_from(events)
    report=json.loads((out/'delivery/report.json').read_text()) if (out/'delivery/report.json').exists() else None
    receipt_ok=bool(receipt and report and receipt['input_sha256']==digest(spec) and receipt['artifact_sha256']==digest(report));review=h.verify_workflow(spec,report if receipt_ok else None,out/'delivery',events)
    marker=json.loads((out/'control-marker.json').read_text()) if (out/'control-marker.json').exists() else None
    audit=[json.loads(l) for l in (out/'script-audit.jsonl').read_text().splitlines()] if (out/'script-audit.jsonl').exists() else []
    errors=sum(r.get('is_error',False) for r in events) if c['arm']=='S' else sum(b.get('isError',False) for e in events if e.get('type')=='tool/result' for b in e['data']['message'].get('content',[]))
    combined={**runs[-1],**{k:sum(r.get(k,0) for r in runs) for k in ('upstream_requests','budget_accounted_usd','elapsed_seconds','inputTokens','cacheReadTokens','outputTokens','collection_model_requests_bypassed_verified')},'segments':len(runs)}
    repairs=[e for e in events if e.get('type')=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair']
    o={'task_id':c['task_id'],'pair_id':c['pair_id'],'role':c['role'],'arm':c['arm'],'profile_id':c['profile_id'],'workflow_id':c['workflow_id'],'condition':c['condition'],'attempt':str(out),
       'input_sha256':digest(spec),'source_sha256':digest(p['source_code']),'run':combined,'runs':runs,'events_sha256':sha(Path(runs[-1]['output_dir'])/'agent-events.jsonl') if c['arm']!='S' else sha(out/'mcp-calls.jsonl'),
       'receipt_verified':receipt_ok,'acceptance':review,'accounting_complete':True,'normal_harness_only':c['arm']=='H','learning_performed':False,'tool_errors':errors,'error':error,'control_marker':marker,
       'condition_passed':review['passed'] if c['expected_delivery'] else bool(not review['passed'] and marker),'final_snapshot_sha256':digest(snapshot(spec['workspace'])),'end_to_end_seconds':time.monotonic()-start,
       'script_steps':sum(r['kind'] in ('learned_script_step_verified','script_v2_step_verified') for r in audit),'script_deferred':[r for r in audit if r['kind'] in ('learned_script_deferred','script_v2_deferred')],
       'acceptance_repairs':len(repairs),'controlled_draft':c.get('controlled_draft',False),'repair_probe_marker':json.loads((out/'repair-probe-marker.json').read_text()) if (out/'repair-probe-marker.json').exists() else None}
    save(out/'outcome.json',o);print(json.dumps({'finished':c['task_id'],'passed':review['passed'],'condition_passed':o['condition_passed'],'requests':combined['upstream_requests'],'estimated_usd':combined['budget_accounted_usd'],'steps':o['script_steps'],'repairs':len(repairs),'deferred':len(o['script_deferred']),'errors':review['errors']},ensure_ascii=False),flush=True);return o

def freeze_holdout(exp,p):
    cert=json.loads((exp/'certificate-v2.json').read_text())
    if cert['status']!='certified_v2' or (exp/'holdout-lock.json').exists():raise ValueError('certificate required before fresh holdout')
    templates=[];tasks=[]
    for wi,wid in enumerate(('FM05','FM17')):
        for ci,condition in enumerate(('R','D','RD','V')):
            profile=wid+':'+(('min' if wid=='FM05' else 'all') if condition=='D' else ('max' if wid=='FM05' else 'filtered'))
            t=template(exp,'holdout',profile,condition!='R',1,condition);templates.append(t);offset=(wi+ci)%5;tasks+=arms(exp,t,ARMS[offset:]+ARMS[:offset])
    held={'templates':templates,'tasks':tasks,'certificate_sha256':sha(exp/'certificate-v2.json'),'candidate_lock_sha256':sha(exp/'candidate-lock.json'),'protocol_sha256':sha(exp/'protocol.json'),
          'model_holdout_runs_when_frozen':0,'learning_from_holdout_permitted':False}
    save(exp/'holdout.json',held);save(exp/'holdout-lock.json',{'sha256':sha(exp/'holdout.json')});print(json.dumps({'new_conditions':8,'five_arm_runs':40,'frozen_after_certificate':True}),flush=True)

def summary(exp,p):
    files=list(exp.glob('tasks/*/attempts/*/outcome.json'))+[Path(r['outcome_file']) for r in p.get('imported_maintenance',[])];assert len(files)==len(set(files))
    rows=[json.loads(f.read_text()) for f in files];setup=[o for o in rows if o['role']!='holdout'];held=[o for o in rows if o['role']=='holdout'];group={}
    for a in ARMS:
        rr=[o for o in held if o['arm']==a];group[a]={'runs':len(rr),'positive_passed':sum(o['condition']!='V' and o['acceptance']['passed'] for o in rr),'positive_conditions':sum(o['condition']!='V' for o in rr),
            'expected_stops':sum(o['condition']=='V' and o['condition_passed'] for o in rr),'failed_deliveries_retained':sum(not o['acceptance']['passed'] for o in rr),'repairs':sum(o['acceptance_repairs'] for o in rr),'tool_errors':sum(o['tool_errors'] for o in rr),
            **{k:sum(o['run'].get(k,0) for o in rr) for k in ('upstream_requests','budget_accounted_usd','elapsed_seconds')}}
    maintenance=sum(o['run']['budget_accounted_usd'] for o in setup);group['L1']['full_API_usd']=p['v1_upfront_usd']+group['L1']['budget_accounted_usd'];group['L2']['incremental_API_usd']=maintenance+group['L2']['budget_accounted_usd'];group['L2']['full_API_usd']=p['v1_upfront_usd']+group['L2']['incremental_API_usd']
    group['M']['full_API_usd']=sum(o['estimated_usd'] for o in p['overhead_sources'])+group['M']['budget_accounted_usd']
    pairs={}
    for o in held:pairs.setdefault(o['pair_id'],{})[o['arm']]=o
    common=[g for g in pairs.values() if set(g)==set(ARMS) and all(o['acceptance']['passed'] for o in g.values())]
    result={'experiment_id':exp.name,'attempts':len(rows),'setup_runs':len(setup),'maintenance_usd':maintenance,'maintenance_requests':sum(o['run']['upstream_requests'] for o in setup),
       'holdout_runs':len(held),'arms':group,'jointly_qualified_conditions':len(common),'joint_execution':{a:{k:sum(g[a]['run'][k] for g in common) for k in ('upstream_requests','budget_accounted_usd')} for a in ARMS},
       'series':accounting(),'human_blind_review':False,'actual_bill_verified':False,'outcomes':rows}
    save(exp/'summary.json',result);return result

def main():
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path);a.add_argument('--training-parent',type=Path);a.add_argument('--role',choices=['validate','explore','certify','holdout']);a.add_argument('--case');a.add_argument('--call-model',action='store_true');a.add_argument('--free',action='store_true');a.add_argument('--learn',action='store_true');a.add_argument('--certify',action='store_true');a.add_argument('--freeze-holdout',action='store_true');a.add_argument('--summary',action='store_true');args=a.parse_args()
    if not args.experiment:prepare(args.training_parent);return
    exp=args.experiment.resolve();p=json.loads((exp/'protocol.json').read_text())
    if args.summary:print(json.dumps({k:v for k,v in summary(exp,p).items() if k!='outcomes'}));return
    frozen(exp,p)
    if args.learn:learn(exp,p);return
    if args.certify:certify(exp,p);return
    if args.freeze_holdout:freeze_holdout(exp,p);return
    if args.call_model and not args.role:a.error('explicit phase required')
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:
        if args.free:
            results=[]
            for c in p['probes']:
                out,spec,env,_=h.instantiate(exp,{**c,'arm':'S'},p,True);receipt,error=asyncio.run(fixed_script(out,spec,c));review=h.mcp.accept(out,spec,receipt,0)
                passed=review['passed'] if c['expected_delivery'] else not review['passed'] and (out/'control-marker.json').exists()
                results.append({'task_id':c['task_id'],'passed':bool(passed),'output':str(out),'error':error,'real_api_requests':0})
            save(exp/'free-summary.json',{'checks':len(results),'passed':sum(r['passed'] for r in results),'real_api_requests':0,'results':results});print(json.dumps({'free_checks':len(results),'passed':sum(r['passed'] for r in results),'real_api_requests':0}),flush=True)
            if not all(r['passed'] for r in results):raise ValueError('free probe failure retained')
            return
        tasks=json.loads((exp/'holdout.json').read_text())['tasks'] if args.role=='holdout' else p['tasks']
        if args.role=='certify' and not (exp/'candidate-lock.json').exists():raise ValueError('freeze candidates first')
        if args.role=='holdout':
            held=json.loads((exp/'holdout.json').read_text());assert sha(exp/'holdout.json')==json.loads((exp/'holdout-lock.json').read_text())['sha256'] and held['certificate_sha256']==sha(exp/'certificate-v2.json')
        for c in tasks:
            if args.role and c['role']!=args.role or args.case and c['task_id']!=args.case:continue
            if list(Path(c['task_dir']).glob('attempts/*/outcome.json')):continue
            frozen(exp,p);run(exp,c,p,args.call_model)
            if args.call_model:summary(exp,p)
        if args.call_model:save(exp/'progress.json',{'state':'phase_completed','phase':args.role})
    finally:lock.unlink()
if __name__=='__main__':main()
