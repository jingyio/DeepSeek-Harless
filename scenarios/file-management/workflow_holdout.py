"""Frozen new H/S/M holdout. No training, no hidden answers in any execution arm."""
from __future__ import annotations
import argparse,asyncio,importlib.util,json,os,shutil,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
from collections import Counter
from common import ROOT,HERE,DATA,PREFIX,digest,sha,save,snapshot,source_code
sys.path.insert(0,str(ROOT))
from workflow_prepare import IDS,fixture
from workflow_study import PROMPT,receipt_from
from workflow_learning import dependencies,READ_PROMPT
from workflow_online import RUNTIME
from workflow_tools import workflow_version
from recovery_tools import recovery_version
from plan_tools import execution_version as plan_version
from file_tools import FileScene
from workflow_contract import verify_workflow
from experiment import accounting,inspect_schema,outcomes
from src.adapters.file_job_budget import job_command

sp=importlib.util.spec_from_file_location('holdout_mcp_helpers',ROOT/'scripts/check-file-workflows.py');mcp=importlib.util.module_from_spec(sp);sp.loader.exec_module(mcp)
LIMITS={'budget_usd':5,'max_requests':96,'max_steps':96,'max_output':4000,'max_repairs':2}
ZERO_MODEL={'FM05','FM17','FM38'}
EXTRA=['src/adapters/dsh_workflow_experiment.ts','src/adapters/dsh_job_plan_gate.ts','src/adapters/file_workflow_job.ts','src/adapters/file_job_budget.py','src/adapters/file_acceptance_guard.ts',
       'src/adapters/file_scenario.py','src/adapters/file_cost_gate.py','src/adapters/harness_runtime.py','src/adapters/native_budget.py','src/motif_core/authorized_plan_policy.ts',
       'src/motif_core/collection_batch_script.ts','scripts/run-file-scenario.py','scripts/validate-file-delivery.py','scripts/check-file-workflows.py','scripts/check-file-workflow-holdout-sdk.py','config/semantic-sdk.patch.yml','package.json','package-lock.json','requirements.txt']

def fresh(work,wid,condition,tag,assets,pdf):
    c,o,ops,_=fixture(work,wid,'N' if condition=='V' else condition,tag,assets,pdf)
    stamp=digest(tag)[:7];renamed={}
    for n in c['source_paths']:
        # Keep the explicit required approval path; vary other source names and layouts.
        new=n if n.endswith('/approval.txt') else str(Path(n).with_name(stamp+'-'+Path(n).name))
        if new!=n:(work/n).rename(work/new)
        renamed[n]=new
    for key in ('source_paths','allowed_reads','required_reads'):c[key]=[renamed.get(n,n) for n in c[key]]
    extras=1+(int(stamp,16)%3)
    if wid=='FM38':extras=1 if condition!='V' else 0
    prefix={'FM01':'inbox/','FM05':'source-b/','FM13':'versions/','FM17':'source/nested/','FM21':'materials/package/','FM38':'inbox/'}[wid]
    for i in range(extras):
        n=prefix+stamp+f'-fresh-{i}.txt';p=work/n;p.parent.mkdir(parents=True,exist_ok=True)
        text=(('PROJECT_A ' if i%2 else 'PROJECT_B ') if wid=='FM01' else 'fresh version data ')+tag+' '+str(i)
        p.write_text(text);c['source_paths'].append(n)
        if wid in ('FM01','FM13','FM21'):c['allowed_reads'].append(n);c['required_reads'].append(n)
        elif wid=='FM05':c['allowed_reads'].append(n)
    c['source_paths']=sorted(c['source_paths']);initial=snapshot(work);expected=dict(initial);mapping={};gaps=[]
    if wid=='FM01':
        parser=FileScene.__new__(FileScene)
        for i,n in enumerate(c['source_paths'],1):
            try:status,text,_=parser.parse(work/n)
            except Exception:status,text='unreadable',''
            a,b='PROJECT_A' in text,'PROJECT_B' in text
            if status=='readable' and (a^b):mapping[n]=f'organized/project-{"a" if a else "b"}/item_{i:02d}{Path(n).suffix.lower()}'
            else:gaps.append(n)
        for n,d in mapping.items():expected[d]=expected.pop(n)
    elif wid=='FM05':
        groups={}
        for n in c['source_paths']:groups.setdefault(initial[n],n)
        mapping={n:'merged/'+groups[initial[n]] for n in c['source_paths']}
        for n,d in mapping.items():expected[d]=initial[n]
    elif wid=='FM13':
        chosen=c['source_paths'][int(stamp,16)%len(c['source_paths'])]
        notice={'published_versions':c['source_paths'][:2] if condition=='E' else [chosen],
                'ambiguous':condition=='E','basis':('conflicting reviewer approvals; none confirmed' if condition=='E' else 'explicit reviewed release')+' '+tag}
        (work/'context/release.txt').write_text(json.dumps(notice,ensure_ascii=False));initial=snapshot(work);expected=dict(initial)
        if condition=='E':gaps=['context/release.txt']
        else:mapping={chosen:'selected/'+Path(chosen).name};expected[mapping[chosen]]=initial[chosen]
    elif wid=='FM17':
        mapping={n:'backup-set/'+n[len('source/'):] for n in c['source_paths']}
        for n,d in mapping.items():expected[d]=initial[n];expected['recovery-drill/'+n[len('source/'):]]=initial[n]
    elif wid=='FM21':
        gaps=['materials/package/approval.txt',next(n for n in c['source_paths'] if n.endswith('-broken.docx'))] if condition=='E' else []
    else:
        mapping={n:f'normalized/txt/item_{i:02d}.txt' for i,n in enumerate(c['source_paths'],1)}
        c['recovery_goal']='rollback' if condition in ('E','V') else 'complete'
        if condition=='N':
            for n,d in mapping.items():expected[d]=expected.pop(n)
    o.update(expected_snapshot=expected,mapping=mapping,required_gap_markers=gaps,require_effects=bool(mapping or wid in ('FM17','FM21')),require_restore=wid=='FM38' and condition in ('E','V'))
    if wid=='FM17':o['backup_sources']=list(mapping.values())
    if wid=='FM21':o['zip_members']={n:initial[n] for n in c['source_paths'] if n.startswith('materials/package/')}
    return c,o,ops,initial

def prepare():
    library=Path(json.loads((ROOT/'.local/file-management/workflow-learning-current.json').read_text())['experiment']);lock=json.loads((library/'library-lock.json').read_text())
    for group in ('workflow14','recovery15'):
        if dependencies(group)!=lock['groups'][group]['dependencies']:raise ValueError('certified service dependency changed')
    base=Path(json.loads((ROOT/'.local/file-management/workflow-current.json').read_text())['experiment']);bp=json.loads((base/'protocol.json').read_text())
    exp=ROOT/'.local/file-management'/('fm-workflow-holdout-20261014-'+uuid4().hex[:8]);exp.mkdir(mode=0o700);tasks=[];probes=[];templates=[]
    assets=ROOT/'.local/file-management-author/assets/a';pdfs=sorted((ROOT/'testpdf').glob('*.pdf'))
    for role in ('probe','holdout'):
        for wi,wid in enumerate(IDS):
            for ci,condition in enumerate('NEV'):
                pair=f'{role}-{wid}-{condition}';td=exp/'templates'/pair;pristine=DATA/exp.name/'pristine'/pair;pristine.mkdir(parents=True,exist_ok=False)
                c,o,ops,initial=fresh(pristine,wid,condition,exp.name+' '+pair+' '+uuid4().hex,assets,pdfs[wi%3]);save(td/'oracle.json',o)
                origin=next(t for t in bp['tasks'] if t['workflow_id']==wid and t['condition']==('E' if condition in ('E','V') and wid=='FM38' else condition) and t['role']=='probe')
                spec=json.loads((Path(origin['task_dir'])/'input-template.json').read_text());spec.update(task_id=pair,role=role,workspace=str(pristine),workflow_contract=c,initial_snapshot=initial,allowed_operations=ops,
                    workflow_oracle_file=str(td/'oracle.json'),workflow_oracle_sha256=sha(td/'oracle.json'))
                if wid=='FM38':spec['write_grant'].update(source_paths=c['source_paths'],max_actions=len(c['source_paths']));spec['recovery_crash_after_publish']=condition in ('E','V')
                save(td/'input-template.json',spec)
                extra='\n先独立pin/read实际context_paths，然后select_files选择需要的完整原件集合；不得先读完再选集合，选择后先完成collect_reads再做效果。summary最多1000字符。'
                if wid=='FM38':extra='\n若read_task.recovery_state已有executed_verified，则只对同plan_id/authorization_id重复execute_plan核验幂等并交付；partial_failure只能原授权restore_plan。禁止另建计划重放部分执行，不能读取内容。'
                if condition=='V':extra+='\n本例将在冻结的预览/备份/部分计划边界由实验程序改变一个文件版本。版本变化后停止，不覆盖、不回滚未知外部变化，也不申请扩大权限；如实保留失败。'
                (td/'prompt.md').write_text(PROMPT+'\n'+spec['objective']+extra)
                cfg=json.loads((Path(origin['task_dir'])/'scenario.json').read_text());cfg['prompt']=str(td/'prompt.md');save(td/'scenario.json',cfg)
                mode='version' if condition=='V' else ('cold_success' if condition=='N' else 'cold_crash') if wid=='FM38' else 'none'
                target=('backup-set/'+c['source_paths'][0][len('source/'):] if wid=='FM17' else c['source_paths'][0])
                before=initial[c['source_paths'][0]]
                info={'task_id':pair,'role':role,'family':wid,'workflow_id':wid,'condition':condition,'task_dir':str(td),'pristine':str(pristine),
                      'input_template_sha256':sha(td/'input-template.json'),'oracle_sha256':sha(td/'oracle.json'),'snapshot_sha256':digest(initial),'prompt_sha256':sha(td/'prompt.md'),
                      'control':{'mode':mode,'workflow_id':wid,'target':target,'before_sha256':before,'replacement':'FROZEN EXTERNAL VERSION '+exp.name+' '+pair},'expected_delivery':condition!='V'}
                templates.append(info)
                if role=='probe':probes.append(info)
                else:
                    order=('H','S','M');offset=(wi+ci)%3
                    for arm in order[offset:]+order[:offset]:
                        entry={**info,'pair_id':pair,'task_id':pair+'-'+arm,'arm':arm,'task_dir':str(exp/'tasks'/(pair+'-'+arm)),'template_dir':str(td)}
                        taskdir=Path(entry['task_dir']);taskdir.mkdir(parents=True);shutil.copyfile(td/'input-template.json',taskdir/'input-template.json');shutil.copyfile(td/'oracle.json',taskdir/'oracle.json')
                        # All arms refer to the same frozen pair prompt and oracle; neither is exposed as an answer.
                        shutil.copyfile(td/'scenario.json',taskdir/'scenario.json');entry['oracle_sha256']=sha(td/'oracle.json');tasks.append(entry)
    patch=exp/'control.patch.yml';patch.write_text(json.dumps([{'insert':[{'id':'sss-workflow-experiment','name':(ROOT/'src/adapters/dsh_workflow_experiment.ts').as_uri()}]}]))
    launcher=exp/'launcher.py';launcher.write_text("import importlib.util\ns=importlib.util.spec_from_file_location('public_runner',"+repr(str(ROOT/'scripts/run-file-scenario.py'))+");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\noriginal=m.create_harness\ndef wrapped(**kwargs):\n kwargs['patches']=tuple(kwargs['patches'])+("+repr(str(patch))+",)\n return original(**kwargs)\nm.create_harness=wrapped\nraise SystemExit(m.main())\n")
    paths=sorted(set(source_code())|set(EXTRA))
    for n in paths:q=exp/'frozen-source'/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,q)
    acquisition=[ROOT/'.local/file-management'/e for e in ('fm-workflow-explore-20261014-03260edc','fm-workflow-explore-20261014-bbefcf67','fm-workflow-learning-20261014-e2c37141','fm-workflow-learning-20261014-d93e4c44')]
    validation=[ROOT/'.local/file-management'/e for e in ('fm-workflow-online-20261014-9ecabaa2','fm-workflow-online-20261014-65ac206a','fm-workflow-online-20261014-bcb96582')]
    overhead=[]
    for category,parents in [('acquisition',acquisition),('online_validation',validation)]:
        for parent in parents:
            for f in parent.glob('tasks/*/attempts/*/outcome.json'):
                o=json.loads(f.read_text());overhead.append({'category':category,'path':str(f),'sha256':sha(f),'requests':o['run']['upstream_requests'],'estimated_usd':o['run']['budget_accounted_usd']})
    p={'experiment_id':exp.name,'type':'frozen new six-workflow H/S/M holdout; no learning','tasks':tasks,'probes':probes,'templates':templates,
       'source_code':{n:sha(ROOT/n) for n in paths},'test_sources':{f.name:sha(f) for f in (patch,launcher)},'library':str(library),'library_lock_sha256':sha(library/'library-lock.json'),
       'limits':LIMITS,'max_steps':96,'max_output':4000,'max_repairs':2,'max_cold_restarts':1,'per_task_cap_usd':5,'total_cap_usd':1000,'batch_cap_usd':270,
       'model':'deepseek-flash','reasoning_effort':'off','compression_enabled':False,'series_before':accounting(),'overhead_sources':overhead,'original_pdfs':bp['original_pdfs'],'parent':str(base),
       'parent_protected':{c['task_id']:{'template_sha256':c['input_template_sha256'],'oracle_sha256':c['oracle_sha256'],'snapshot_sha256':c['snapshot_sha256']} for c in bp['tasks']},
       'runtime':json.loads((library/'protocol.json').read_text())['runtime'],'price_source':'https://api-docs.deepseek.com/quick_start/pricing/','pricing_checked_client_date':'2026-10-14',
       'human_cost_monetization':'excluded at explicit user request; no fabricated human amount','human_blind_review':False,'learning_performed':False,
       'script_profile':{'semantic_model_batch_reads':['FM01','FM13','FM21'],'deterministic_zero_model':sorted(ZERO_MODEL),'no_hidden_oracle':True},
       'motif_profile':{'collection':['FM01','FM05','FM13','FM21'],'plan_job':['FM38'],'ordinary_fallback_no_applicable_graph':['FM17']},
       'frozen_before_any_holdout_runs':True,'model_holdout_runs_when_frozen':0,'default_sdk_web_enabled':False,'push_enabled':False}
    save(exp/'protocol.json',p);save(exp/'protocol-lock.json',{'sha256':sha(exp/'protocol.json'),'source_sha256':digest(p['source_code']),'library_lock_sha256':p['library_lock_sha256']})
    save(ROOT/'.local/file-management/workflow-holdout-current.json',{'experiment':str(exp)})
    print(json.dumps({'experiment':str(exp),'holdout_conditions':18,'arms':54,'new_free_probes':18,'maximum_usd':270,'series_before':p['series_before'],'paid':False}),flush=True);return exp

def frozen(exp,p):
    if sha(exp/'protocol.json')!=json.loads((exp/'protocol-lock.json').read_text())['sha256']:raise ValueError('frozen protocol changed')
    if any(sha(ROOT/n)!=h for n,h in p['source_code'].items()):raise ValueError('frozen source changed')
    if sha(Path(p['library'])/'library-lock.json')!=p['library_lock_sha256']:raise ValueError('frozen library changed')
    for c in p['templates']:
        td=Path(c['task_dir'])
        if sha(td/'input-template.json')!=c['input_template_sha256'] or sha(td/'oracle.json')!=c['oracle_sha256'] or sha(td/'prompt.md')!=c['prompt_sha256'] or digest(snapshot(c['pristine']))!=c['snapshot_sha256']:raise ValueError('frozen material changed')

def instantiate(exp,c,p,free=False):
    out=(exp/'free-runs'/c['task_id'] if free else Path(c['task_dir'])/'attempts')/uuid4().hex[:12];out.mkdir(parents=True,mode=0o700)
    td=Path(c.get('template_dir',c['task_dir']));spec=json.loads((td/'input-template.json').read_text());work=DATA/exp.name/('free' if free else 'actual')/c['task_id']/out.name
    shutil.copytree(c['pristine'],work);spec['workspace']=str(work);save(out/'input.json',spec)
    if c['workflow_id']=='FM38':job_command(out/'job.json','init',{'task_file':str(out/'input.json'),'delivery_root':str(out/'delivery'),'execution_version_sha256':recovery_version(),'limits':LIMITS})
    control={**c['control'],'marker':str(out/'control-marker.json')};save(out/'control.json',control)
    env={**os.environ,'FM_TASK_FILE':str(out/'input.json'),'FM_OUTPUT':str(out/'delivery'),'FM_WORKFLOW_CONTROL':str(out/'control.json')}
    if c['workflow_id']=='FM38':env['FM_JOB_FILE']=str(out/'job.json')
    schemas=asyncio.run(inspect_schema(env,HERE/('recovery_tools.py' if c['workflow_id']=='FM38' else 'workflow_tools.py')));save(out/'tool-schemas.json',schemas);save(out/'source-code.json',p['source_code'])
    lock=json.loads((Path(p['library'])/'library-lock.json').read_text());record=next(a for a in lock['artifacts'] if a['kind']==('plan' if c['workflow_id']=='FM38' else 'collection'));policy=Path(p['library'])/'libraries'/record['path']
    rows=[{'file_id':'file:local:'+digest({'path':n,'sha':h})[:24],'path':n,'extension':Path(n).suffix.lower(),'sha256':h,'bytes':(work/n).stat().st_size,'source_version':digest({'path':n,'sha':h,'parser':'fm-parser-v1'})}
          for n,h in spec['initial_snapshot'].items() if n!='.experiment-copy']
    scope={'schema_version':1,'task_id':spec['task_id'],'session_id':'holdout-'+uuid4().hex,'input_version':digest(spec),'snapshot_sha256':digest(spec['initial_snapshot']),
           'initial_snapshot':spec['initial_snapshot'],'inventory':rows,'inventory_sha256':digest(rows),'execution_version_sha256':plan_version() if c['workflow_id']=='FM38' else workflow_version()}
    if c['workflow_id']=='FM38':
        scope.update(grant=spec['write_grant'],grant_sha256=digest(spec['write_grant']));state=job_command(out/'job.json','state')['state']
        save(out/'binding.json',{'format':'sss-durable-plan-binding-v1','schema_version':1,'job_file':str(out/'job.json'),'task_sha256':state['task_sha256'],'delivery_root':state['delivery_root'],
             'service_execution_version_sha256':state['execution_version_sha256'],'limits_sha256':digest(state['limits']),'library_lock_file':str(Path(p['library'])/'library-lock.json'),
             'library_lock_sha256':p['library_lock_sha256'],'policy_sha256':record['sha256'],'runtime_source':{n:p['source_code'][n] for n in RUNTIME}})
    save(out/'scope.json',scope)
    # Script reads the same actual selected members with the same guards; no learned certificate.
    names=[PREFIX+n for n in ('select_files','pin_file','read_file','collect_reads')]
    schemas_by_name={PREFIX+r['name']:r.get('inputSchema',r.get('input_schema')) for r in schemas}
    if c['workflow_id']!='FM38':
        graph={'source_tool':names[0],'pin_tool':names[1],'read_tool':names[2],'gather_tool':names[3],
               'selection':'actual_model_selected_members','array_field':'files','identity_field':'file_id','pin_param':'file_id',
               'read_param':'source_id','gather_param':'source_ids','max_targets':32,'max_batch':8,'stop':'semantic_handoff_after_complete_gather'}
        script={'schema_version':1,'format':'sss-collection-script-v1','origin':'handwritten_no_library','execution_version_sha256':workflow_version(),
                'graph':graph,'tools':names,'tool_schema_sha256':{n:digest(schemas_by_name[n]) for n in names}}
        script['script_digest']=digest(script);save(out/'script.json',script)
    save(out/'config.json',{'protocol_sha256':sha(exp/'protocol.json'),'input_sha256':digest(spec),'schemas_sha256':digest(schemas),'arm':c.get('arm','free'),'limits':LIMITS,
         'model':p['model'],'reasoning_effort':'off','compression_enabled':False,'library_lock_sha256':p['library_lock_sha256'],'zero_model':c.get('arm')=='S' and c['workflow_id'] in ZERO_MODEL})
    return out,spec,env,policy

def mutate(out,spec,c):
    path=Path(spec['workspace'])/c['control']['target'];assert sha(path)==c['control']['before_sha256'];path.write_text(c['control']['replacement'])
    save(out/'control-marker.json',{'mode':'version','target':c['control']['target'],'before_sha256':c['control']['before_sha256'],'after_sha256':sha(path),'interrupted':True,'origin':'fixed ordinary script control'})

async def zero_script(out,spec,c):
    """Ordinary fixed rules, actual read_task/hash/plan capabilities only. Never reads oracle."""
    wid=c['workflow_id'];receipt=None;error=None;token=None;executed=None
    try:
        async with mcp.Connection(out,spec) as conn:
            task=await conn.call('read_task');ids=await mcp.listing(conn)
            if wid=='FM05':
                for n in task['workflow_contract']['context_paths']:
                    pin=await conn.call('pin_file',{'file_id':ids[n]});packet=await conn.call('read_file',{'source_id':pin['source_id']})
                    if 'lexicographically first FULL source path' not in packet['text']:raise ValueError('unrecognized merge rule; requires model, no guessed policy')
                hashed=await conn.call('hash_files',{'file_ids':[ids[n] for n in task['workflow_contract']['source_paths']]})
                representatives=[min(group['files'],key=lambda r:r['path']) for group in hashed['groups']]
                actions=[{'op':'copy','file_ids':[row['file_id']],'destination':'merged/'+row['path']} for row in representatives]
            elif wid=='FM17':actions=[{'op':'copy','file_ids':[ids[n]],'destination':'backup-set/'+n[len('source/'):]} for n in task['workflow_contract']['source_paths']]
            else:actions=[{'op':'move','file_ids':[ids[r['source']]],'destination':r['destination']} for r in task['rename_targets']]
            plan=await conn.call('preview_actions',{'actions':actions})
            if wid=='FM05' and c['condition']=='V':mutate(out,spec,c);await conn.call('execute_plan',{'plan_id':plan['plan_id']});raise AssertionError('changed version executed')
            if wid=='FM38':token=await conn.call('authorize_plan',{'plan_id':plan['plan_id']})
            try:executed=await conn.call('execute_plan',{'plan_id':plan['plan_id'],**({'authorization_id':token['authorization_id']} if token else {})})
            except Exception:
                if wid!='FM38' or c['condition'] not in ('E','V'):raise
            if wid=='FM17':
                ids=await mcp.listing(conn);aa=[{'op':'copy','file_ids':[ids['backup-set/'+n[len('source/'):]]],'destination':'recovery-drill/'+n[len('source/'):]} for n in task['workflow_contract']['source_paths']]
                restore=await conn.call('preview_actions',{'actions':aa})
                if c['condition']=='V':mutate(out,spec,c)
                await conn.call('execute_plan',{'plan_id':restore['plan_id']})
            if wid!='FM38':
                ids=await mcp.listing(conn);receipt=await conn.call('submit_report',{'summary':'Ordinary fixed batch script; actual SHA and current files; no model semantics fabricated','file_ids':list(ids.values()),'gaps':[],'report_kind':'task_result'})
        if wid=='FM38':
            if c['condition']=='V':mutate(out,spec,c)
            state=job_command(out/'job.json','state')['state'];save(out/'script-cold-before.json',state)
            if c['condition']=='E':
                rd=job_command(out/'job.json','begin-check')['round'];failed=mcp.accept(out,spec,None,rd);assert failed.get('restart_required');job_command(out/'job.json','repair',{'reason':'fixed interrupted boundary failed acceptance'})
            async with mcp.Connection(out,spec) as conn:
                recovered=await conn.call('read_task');record=next(r for r in recovered['recovery_state'] if r['plan_id']==plan['plan_id']);kw={'plan_id':record['plan_id'],'authorization_id':record['authorization_id']}
                if c['condition']=='N':again=await conn.call('execute_plan',kw);assert again==executed
                else:await conn.call('restore_plan',kw)
                ids=await mcp.listing(conn);receipt=await conn.call('submit_report',{'summary':'Ordinary state script cold MCP restart with the same original authorization and limits','file_ids':list(ids.values()),'gaps':[],'report_kind':'task_result'})
            save(out/'script-cold-after.json',job_command(out/'job.json','state')['state'])
    except Exception as e:error=type(e).__name__+': '+str(e)
    return receipt,error

def launcher_run(exp,c,p,out,spec,env,policy):
    loader_spec=importlib.util.spec_from_file_location('holdout_key_loader',ROOT/'scenarios/literature-notes/run-live.py');loader=importlib.util.module_from_spec(loader_spec);loader_spec.loader.exec_module(loader);env['DEEPSEEK_API_KEY']=loader.load_key(loader.KEY_FILE,env)
    cmd=[sys.executable,str(exp/'launcher.py'),'--scenario',str(Path(c['task_dir'])/'scenario.json'),'--model',p['model'],'--mode','baseline','--budget-usd','5','--max-steps','96','--max-output','4000','--call-model']
    if c['workflow_id']=='FM38':cmd+=['--file-job',str(out/'job.json')]
    if c['arm']=='M':
        if c['workflow_id']=='FM38':cmd+=['--plan-policy',str(policy),'--plan-task',str(out/'scope.json'),'--file-plan-binding',str(out/'binding.json')]
        elif c['workflow_id']!='FM17':cmd+=['--collection-policy',str(policy),'--collection-task',str(out/'scope.json')]
    elif c['arm']=='S':cmd+=['--collection-script',str(out/'script.json'),'--collection-script-task',str(out/'scope.json')]
    runs=[];events=[]
    for segment in range(2):
        save(exp/'progress.json',{'task_id':c['task_id'],'segment':segment,'attempt':str(out),'state':'running'});r=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)
        save(out/f'segment-{segment}.process.json',{'returncode':r.returncode})
        for n,v in [('stdout',r.stdout),('stderr',r.stderr)]:(out/f'segment-{segment}.{n}.txt').write_text(v)
        summary=None
        for line in r.stdout.splitlines():
            try:
                v=json.loads(line)
                if isinstance(v,dict) and 'output_dir' in v:summary=v
            except ValueError:pass
        if summary is None:raise RuntimeError('no cost summary; reconcile before further paid calls')
        runs.append(summary);save(out/f'segment-{segment}.run.json',summary);f=Path(summary['output_dir'])/'agent-events.jsonl';part=[json.loads(l) for l in f.read_text().splitlines()] if f.exists() else [];events+=part
        marker=json.loads((out/'control-marker.json').read_text()) if (out/'control-marker.json').exists() else None
        if segment or c['workflow_id']!='FM38' or not marker or marker['mode'] not in ('cold_success','cold_crash') or not marker['interrupted']:break
        state=job_command(out/'job.json','state')['state']
        if state['status']!='running':break
        if marker['mode']=='cold_crash':
            rd=job_command(out/'job.json','begin-check')['round'];archive=ROOT/'.local/task-acceptance'/digest(str(out/'job.json'))
            # The archive key is SHA of the raw path, as in the authoritative guard.
            import hashlib
            archive=ROOT/'.local/task-acceptance'/hashlib.sha256(str(out/'job.json').encode()).hexdigest()
            failed=mcp.validator.check(out/'input.json',sha(out/'input.json'),out/'delivery',archive,rd,{'receipt':None,'events':part})
            if not failed.get('restart_required'):
                ps=json.loads((out/'delivery/plan-state.json').read_text());j=ps['journals'][marker['plan_id']]
                if not (j['status']=='partial_failure' and snapshot(spec['workspace'])==j['after']):raise ValueError('unknown crash footprint; cold repair prohibited')
                save(out/'known-partial-boundary.json',{'reason':'native MCP reconnected before controlled transport stop','journal':marker['plan_id'],'snapshot_sha256':digest(j['after']),'not_task_success':True})
            job_command(out/'job.json','repair',{'round':rd,'errors':failed['errors'],'reason':'same recorded crash boundary; ordinary cold repair'})
        save(out/'cold-restart.json',{'before':state,'after_allocated_repair':job_command(out/'job.json','state')['state'],'same_task_and_budget':True,'mode':marker['mode']})
    return runs,events

def run_one(exp,c,p,call_model=False,free=False):
    if not free and (c['role']!='holdout' or list(Path(c['task_dir']).glob('attempts/*/outcome.json'))):raise ValueError('only unrun frozen holdout allowed')
    if accounting()['estimated_usd']+5>1000:raise ValueError('original series cap insufficient')
    out,spec,env,policy=instantiate(exp,c,p,free);start=time.monotonic();runs=[];events=[];receipt=None;error=None
    zero=c.get('arm')=='S' and c['workflow_id'] in ZERO_MODEL
    if not call_model and not free:
        save(out/'preview.json',{'preview':c['task_id'],'paid':False,'effects_enabled':False,'zero_model_script_available':zero})
        return {'preview':c['task_id'],'paid':False}
    print(json.dumps({'starting':c['task_id'],'zero_model':zero,'cap_usd':0 if zero else 5}),flush=True)
    if zero:
        receipt,error=asyncio.run(zero_script(out,spec,c));runs=[{'status':'done' if receipt else 'stopped','upstream_requests':0,'budget_accounted_usd':0,'elapsed_seconds':time.monotonic()-start,'collection_model_requests_bypassed_verified':0,'plan_model_requests_bypassed_verified':0,'collection_script_batches_verified':0}]
        events=[json.loads(l) for l in (out/'mcp-calls.jsonl').read_text().splitlines()]
    else:
        runs,events=launcher_run(exp,c,p,out,spec,env,policy);last=Path(runs[-1]['output_dir'])/'agent-events.jsonl';last_events=[json.loads(l) for l in last.read_text().splitlines()] if last.exists() else [];receipt=receipt_from(last_events)
    report_file=out/'delivery/report.json';report=json.loads(report_file.read_text()) if report_file.exists() else None
    receipt_ok=bool(receipt and report and receipt['artifact_sha256']==digest(report) and receipt['input_sha256']==digest(spec));review=verify_workflow(spec,report if receipt_ok else None,out/'delivery',events)
    if zero:
        rd=job_command(out/'job.json','begin-check')['round'] if c['workflow_id']=='FM38' else 0
        fixed=mcp.accept(out,spec,receipt,rd)
        if c['workflow_id']=='FM38':job_command(out/'job.json','accept' if fixed['passed'] else 'fail',{'round':rd})
    marker=json.loads((out/'control-marker.json').read_text()) if (out/'control-marker.json').exists() else None
    final_files=snapshot(spec['workspace']);condition=review['passed'] if c['expected_delivery'] else bool(not review['passed'] and marker and marker['mode']=='version')
    if marker and marker['mode']=='version':
        assert final_files.get(marker['target'])==marker['after_sha256'];initial_source='source/'+marker['target'][len('backup-set/'):] if marker['target'].startswith('backup-set/') else marker['target']
        assert spec['initial_snapshot'][initial_source]==marker['before_sha256']
        if c['workflow_id']=='FM38' and job_command(out/'job.json','state')['state']['status']=='running':job_command(out/'job.json','fail',{'reason':'frozen external version; no retry'})
    fields=['upstream_requests','budget_accounted_usd','inputTokens','cacheReadTokens','outputTokens','elapsed_seconds','collection_model_requests_bypassed_verified','plan_model_requests_bypassed_verified','collection_script_batches_verified']
    combined={**runs[-1],**{k:sum(r.get(k,0) for r in runs) for k in fields},'segments':len(runs)}
    tool_errors=sum(r.get('is_error',False) for r in events) if zero else sum(b.get('isError',False) for e in events if e.get('type')=='tool/result' for b in e['data'].get('message',{}).get('content',[]))
    o={'task_id':c['task_id'],'pair_id':c['pair_id'],'role':'holdout','workflow_id':c['workflow_id'],'condition':c['condition'],'arm':c['arm'],'attempt':str(out),'input_sha256':digest(spec),'run':combined,'runs':runs,
       'receipt_verified':receipt_ok,'acceptance':review,'condition_passed':condition,'expected_delivery':c['expected_delivery'],'control_marker':marker,'zero_model':zero,'tool_errors':tool_errors,'error':error,
       'accounting_complete':True,'normal_harness_only':c['arm']=='H','learning_performed':False,'source_sha256':digest(p['source_code']),'final_snapshot_sha256':digest(final_files),
       'end_to_end_seconds':time.monotonic()-start,'job_final':job_command(out/'job.json','state')['state'] if c['workflow_id']=='FM38' else None}
    save(out/'outcome.json',o);print(json.dumps({'finished':c['task_id'],'delivery':review['passed'],'condition_passed':condition,'requests':combined['upstream_requests'],'estimated_usd':combined['budget_accounted_usd'],'segments':len(runs),'tool_errors':tool_errors,'errors':review['errors']},ensure_ascii=False),flush=True);return o

def summarize(exp):
    p=json.loads((exp/'protocol.json').read_text());rows=[json.loads(f.read_text()) for f in exp.glob('tasks/*/attempts/*/outcome.json')]
    fields=['upstream_requests','budget_accounted_usd','elapsed_seconds','collection_model_requests_bypassed_verified','plan_model_requests_bypassed_verified','collection_script_batches_verified']
    arms={}
    for arm in ('H','S','M'):
        rr=[o for o in rows if o['arm']==arm];arms[arm]={'runs':len(rr),'delivery_passed':sum(o['acceptance']['passed'] for o in rr),'conditions_passed':sum(o['condition_passed'] for o in rr),
          'failed_retained':sum(not o['acceptance']['passed'] for o in rr),'positive_conditions':sum(o['expected_delivery'] for o in rr),'positive_passed':sum(o['expected_delivery'] and o['acceptance']['passed'] for o in rr),
          'zero_model_runs':sum(o['zero_model'] for o in rr),'tool_errors':sum(o['tool_errors'] for o in rr),**{k:sum(o['run'].get(k,0) for o in rr) for k in fields}}
    setup=sum(o['estimated_usd'] for o in p['overhead_sources']);arms['M']['full_model_cost_usd_including_acquisition_and_online_validation']=arms['M']['budget_accounted_usd']+setup
    groups={}
    for o in rows:groups.setdefault(o['pair_id'],{})[o['arm']]=o
    common=[g for g in groups.values() if len(g)==3 and all(o['acceptance']['passed'] for o in g.values())]
    pairs={a:{k:sum(g[a]['run'].get(k,0) for g in common) for k in ('upstream_requests','budget_accounted_usd')} for a in ('H','S','M')}
    r={'experiment_id':exp.name,'attempts':len(rows),'planned_runs':54,'arms':arms,'all_three_jointly_qualified_conditions':len(common),'jointly_qualified_execution':pairs,
       'setup_cost_usd':setup,'overhead_sources':p['overhead_sources'],'series':accounting(),'holdout_runs':len(rows),'learning_performed':False,'human_blind_review':False,'actual_bill_verified':False,'outcomes':rows}
    save(exp/'summary.json',r);return r

def main():
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path);a.add_argument('--case');a.add_argument('--free',action='store_true');a.add_argument('--call-model',action='store_true');a.add_argument('--summary',action='store_true');args=a.parse_args()
    if not args.experiment:prepare();return
    exp=args.experiment.resolve();p=json.loads((exp/'protocol.json').read_text())
    if args.summary:print(json.dumps({k:v for k,v in summarize(exp).items() if k not in ('outcomes','overhead_sources')}));return
    frozen(exp,p);lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:
        if args.free:
            results=[]
            for c in p['probes']:
                r=asyncio.run(mcp.probe(exp,c));results.append(r);print(json.dumps({'probe':c['task_id'],'status':r['status'],'output':r['output']},ensure_ascii=False),flush=True)
            save(exp/'free-summary.json',{'passed':sum(r['status']=='passed' for r in results),'checks':len(results),'real_api_requests':0,'results':results})
            if any(r['status']!='passed' for r in results):raise ValueError('free probe failed; preserve and diagnose before holdout')
        else:
            for c in p['tasks']:
                if args.case and c['task_id']!=args.case:continue
                if list(Path(c['task_dir']).glob('attempts/*/outcome.json')):continue
                frozen(exp,p);run_one(exp,c,p,args.call_model);summarize(exp)
    finally:lock.unlink()

if __name__=='__main__':main()
