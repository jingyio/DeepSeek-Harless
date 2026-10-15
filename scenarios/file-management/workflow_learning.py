"""Version-bound offline learning and independent ordinary certification. No holdout runs."""
from __future__ import annotations
import argparse,asyncio,importlib.util,json,os,shutil,subprocess,sys
from collections import Counter
from pathlib import Path
from uuid import uuid4
from common import ROOT,HERE,DATA,PREFIX,digest,sha,save,snapshot
sys.path.insert(0,str(ROOT))
from workflow_prepare import fixture,IDS
from workflow_study import PROMPT,check_frozen,run_task,summarize
from workflow_tools import workflow_version
from recovery_tools import recovery_version
from plan_tools import execution_version as plan_version
from experiment import accounting
from file_tools import FileScene
from collection_tools import CollectionScene
from workflow_contract import verify_workflow
from src.adapters.file_job_budget import job_command
from collection_study import contracts as collection_contracts,GRAPH_TOOLS as COLLECTION_TOOLS
from plan_study import scope as original_plan_scope,GRAPH_TOOLS as PLAN_TOOLS
from src.adapters.dsh_trajectory import extract_dsh_trace,infer_dsh_provenance,mine_witnessed_parameter_edges
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.motif_core.offline.edge_compiler import compile_witnessed_edge_motif,certify_witnessed_edge_motif
from src.motif_core.offline.collection_compiler import collection_witness,compile_collection_motif,certify_collection_motif,export_collection_policy
from src.motif_core.offline.plan_compiler import native_rows,plan_witness,compile_plan,certify_plan
from src.motif_core.offline.library_builder import library_from_certified

DEPENDENCIES=['common.py','file_tools.py','collection_tools.py','report_tools.py','workflow_contract.py','workflow_delivery.py','workflow_tools.py']
RECOVERY_DEPENDENCIES=['task_tools.py','task_contract.py','plan_tools.py','recovery_tools.py']
RECOVERY_SHARED=['src/adapters/file_workflow_job.ts','src/adapters/file_job_budget.py','src/adapters/dsh_acceptance_guard.ts']
READ_ONLY={'read_task','list_files','select_files','pin_file','read_file','collect_reads','hash_files','search_index','compare_snapshot'}
READ_PROMPT='''需要读取多个文件时，先select_files声明本次实际待读集合，再pin/read成员，最后collect_reads；不能用先读完再选集合代替此顺序。必须先读的业务上下文可以独立pin/read，再选择接下来的集合。没有内容读取权限时仅用目录和哈希，不对未读集合collect_reads。summary最多1000字符，完整路径缺口写入gaps。'''

def dependencies(group):
    names=['scenarios/file-management/'+n for n in DEPENDENCIES]
    if group=='recovery15':names+=['scenarios/file-management/'+n for n in RECOVERY_DEPENDENCIES]+RECOVERY_SHARED
    return {n:sha(ROOT/n) for n in names}

def ordinary(case,out):
    if case['role'] not in ('explore','certify') or out['role']!=case['role']:raise ValueError('probe/holdout or relabeled evidence cannot train/certify')
    if out['arm']!='H' or not out['normal_harness_only'] or out['learning_performed']:raise ValueError('ordinary original Harness evidence required')
    return bool(out['acceptance']['passed'] and out['receipt_verified'] and out['run']['status']=='done')

def prepare(training_parent=None):
    parent=Path(json.loads((ROOT/'.local/file-management/workflow-current.json').read_text())['experiment'])
    base=json.loads((parent/'protocol.json').read_text())
    dataset=Path(json.loads((ROOT/'.local/file-management/workflow-observations-current.json').read_text())['dataset'])
    pooled=json.loads((dataset/'summary.json').read_text());name='fm-workflow-learning-20261014-'+uuid4().hex[:8]
    exp=ROOT/'.local/file-management'/name;exp.mkdir(mode=0o700);tasks=[]
    conditions=[] if training_parent else [('explore','FM01','N',None),('explore','FM01','E',None),('explore','FM38','N',2)]
    conditions += [('certify',wid,'N',None) for wid in IDS]+[('certify','FM38','E',None)]
    assets=ROOT/'.local/file-management-author/assets/a';pdfs=sorted((ROOT/'testpdf').glob('*.pdf'))
    for role,wid,condition,count in conditions:
        tid=f'{role}-{wid}-{condition}'+(f'-count{count}' if count else '')
        td=exp/'tasks'/tid;pristine=DATA/name/'pristine'/tid;pristine.mkdir(parents=True,exist_ok=False)
        c,oracle,ops,initial=fixture(pristine,wid,condition,name+' '+tid+' '+uuid4().hex[:12],assets,pdfs[IDS.index(wid)%3])
        if count:
            for n in c['source_paths'][count:]:(pristine/n).unlink()
            c['source_paths']=c['source_paths'][:count];initial=snapshot(pristine);mapping={n:d for n,d in oracle['mapping'].items() if n in c['source_paths']}
            expected=dict(initial)
            for n,d in mapping.items():expected[d]=expected.pop(n)
            oracle.update(mapping=mapping,expected_snapshot=expected)
        save(td/'oracle.json',oracle)
        origin=next(t for t in base['tasks'] if t['workflow_id']==wid and t['condition']==condition and t['role']=='explore')
        spec=json.loads((Path(origin['task_dir'])/'input-template.json').read_text())
        spec.update(task_id=tid,role=role,workspace=str(pristine),initial_snapshot=initial,workflow_contract=c,allowed_operations=ops,
                    workflow_oracle_file=str(td/'oracle.json'),workflow_oracle_sha256=sha(td/'oracle.json'))
        if wid=='FM38':spec['write_grant'].update(source_paths=c['source_paths'],destination_prefixes=c['destination_prefixes'],max_actions=len(c['source_paths']))
        save(td/'input-template.json',spec);(td/'prompt.md').write_text(PROMPT+'\n'+READ_PROMPT+'\n'+spec['objective'],encoding='utf-8')
        cfg=json.loads((Path(origin['task_dir'])/'scenario.json').read_text());cfg['prompt']=str(td/'prompt.md');save(td/'scenario.json',cfg)
        tasks.append({'task_id':tid,'role':role,'family':wid,'workflow_id':wid,'condition':condition,'task_dir':str(td),'pristine':str(pristine),
                      'input_template_sha256':sha(td/'input-template.json'),'oracle_sha256':sha(td/'oracle.json'),'snapshot_sha256':digest(initial)})
    code=[*HERE.glob('*.py'),*HERE.glob('*.md'),*HERE.glob('*.json')]
    code += [ROOT/n for n in ('scripts/run-scenario.py','scripts/validate-file-delivery.py','scripts/audit-workflow-exploration.py',
        'scripts/replay-file-workflow-motif.mjs','scripts/replay-file-workflow-motif.py','scripts/export-online-motif-manifest.py',
        'src/adapters/file_job_budget.py','src/adapters/file_workflow_job.ts','src/adapters/dsh_acceptance_guard.ts','src/adapters/scenario.py',
        'src/adapters/deepseek_cost_gate.py','src/adapters/harness_runtime.py','src/adapters/dsh_trajectory.py','src/adapters/tool_contract_loader.py',
        'src/motif_core/offline/edge_compiler.py','src/motif_core/offline/collection_compiler.py','src/motif_core/offline/plan_compiler.py',
        'src/motif_core/offline/library_builder.py','src/motif_core/collection_read_policy.ts','src/motif_core/authorized_plan_policy.ts',
        'src/motif_core/online_skill_runtime.mjs','config/semantic-sdk.patch.yml','package.json','package-lock.json','requirements.txt')]
    for p in code:
        dest=exp/'frozen-source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);dest.chmod(0o600)
    origins=[]
    for eid in pooled['experiments']:
        old=ROOT/'.local/file-management'/eid;op=json.loads((old/'protocol.json').read_text())
        for case in op['tasks']:
            outcome=next(Path(case['task_dir']).glob('attempts/*/outcome.json'))
            origins.append({'experiment':str(old),'case':case,'outcome_file':str(outcome),'outcome_sha256':sha(outcome),'protocol_sha256':sha(old/'protocol.json')})
    if training_parent:
        old=training_parent.resolve();op=json.loads((old/'protocol.json').read_text())
        if any(list(Path(c['task_dir']).glob('attempts/*/outcome.json')) for c in op['tasks'] if c['role']=='certify'):raise ValueError('cannot import a parent already exposed to paid certification')
        for case in op['tasks']:
            if case['role']!='explore':continue
            outcome=next(Path(case['task_dir']).glob('attempts/*/outcome.json'))
            origins.append({'experiment':str(old),'case':case,'outcome_file':str(outcome),'outcome_sha256':sha(outcome),'protocol_sha256':sha(old/'protocol.json')})
    p={'experiment_id':name,'type':'offline learning and independent ordinary certification; no holdout','parent':str(parent),
       'tasks':tasks,'source_code':{str(q.relative_to(ROOT)):sha(q) for q in code},'origins':origins,'origin_dataset_sha256':sha(dataset/'summary.json'),
       'versions':{'workflow':workflow_version(),'recovery':recovery_version(),'plan_component':plan_version()},
       'groups':{'workflow14':{'execution_version_sha256':workflow_version(),'dependencies':dependencies('workflow14')},
                 'recovery15':{'execution_version_sha256':recovery_version(),'plan_component_version_sha256':plan_version(),'dependencies':dependencies('recovery15')}},
       'original_pdfs':base['original_pdfs'],'parent_protected':{t['task_id']:{'snapshot_sha256':t['snapshot_sha256'],'template_sha256':t['input_template_sha256'],'oracle_sha256':t['oracle_sha256']} for t in base['tasks']},
       'total_cap_usd':1000,'per_task_cap_usd':5,'batch_cap_usd':5*len(tasks),'max_steps':96,'max_output':4000,'max_repairs':2,'max_cold_restarts':1,
       'model':'deepseek-flash','reasoning_effort':'off','compression_enabled':False,'mode':'baseline','series_before':accounting(),
       'edge_certification_priority':['certify-FM21-N','certify-FM01-N','certify-FM13-N','certify-FM05-N'],
       'collection_certification_priority':['certify-FM21-N','certify-FM01-N','certify-FM13-N','certify-FM05-N'],
       'plan_certification_case':'certify-FM38-N','collection_episode_selection':'largest complete episode then earliest; at most one witness per task',
       'semantic_review':False,'holdout_runs':0,'runtime':json.loads((ROOT/'.local/file-management'/pooled['experiments'][-1]/'protocol.json').read_text())['runtime'],
       'price_source':'https://api-docs.deepseek.com/quick_start/pricing/','pricing_checked_client_date':'2026-10-14',
       'training_parent':str(training_parent.resolve()) if training_parent else None,
       'description_metadata_rule':'actual nonempty MCP docs bound exactly; empty wrapper docs use frozen base-class docs without changing actual schema'}
    save(exp/'protocol.json',p);save(ROOT/'.local/file-management/workflow-learning-current.json',{'experiment':str(exp)})
    print(json.dumps({'experiment':str(exp),'new_training_tasks':sum(c['role']=='explore' for c in tasks),'independent_certification_tasks':7,'cap_usd':5*len(tasks),'paid':False,'series':accounting()}));return exp

def outcome_sources(exp,p,role):
    rows=[]
    if role=='explore':
        for origin in p['origins']:
            file=Path(origin['outcome_file']);old=Path(origin['experiment'])
            if sha(file)!=origin['outcome_sha256'] or sha(old/'protocol.json')!=origin['protocol_sha256']:raise ValueError('historical training evidence changed')
            rows.append((origin['case'],file,old))
    for c in p['tasks']:
        if c['role']==role:
            matches=list(Path(c['task_dir']).glob('attempts/*/outcome.json'))
            if len(matches)!=1:raise ValueError('one retained completed attempt required for '+c['task_id'])
            rows.append((c,matches[0],exp))
    return rows

def contracts(schemas):
    fields={'pin_file':['source_id','file_id','source_version'],'read_file':['source_id','file_id','source_version','status'],
            'read_task':['input_sha256'],'select_files':['collection_id','files'],'collect_reads':['coverage_sha256']}
    raw={}
    for row in schemas:
        name=row['name'];ss=row.get('inputSchema',row.get('input_schema'))
        method=getattr(CollectionScene,name,None);base_doc=(getattr(method,'__doc__',None) or name.replace('_',' ')).strip()
        raw[PREFIX+name]={'required_params':ss.get('required',[]),'output_fields':fields.get(name,[]),'read_only':name in READ_ONLY,
                         'replay_stable':name not in ('list_files','select_files','search_index','compare_snapshot'),'description':row['description'] or base_doc,
                         'provenance_params':['source_id'] if name=='read_file' else [],'collection_params':[n for n in ss.get('required',[]) if n.endswith('_ids')]}
    ct=parse_tool_contracts(raw)
    # Display metadata cannot authorize execution. Preserve the real schema,
    # and bind only docs actually present; fallback docs are explicitly offline.
    actual={PREFIX+r['name']:ct[PREFIX+r['name']] for r in schemas if r['description']}
    if actual:ct.update(bind_mcp_descriptions(actual,[{**r,'name':PREFIX+r['name'],'inputSchema':r.get('inputSchema',r.get('input_schema'))} for r in schemas]))
    return raw,ct

def fingerprint(spec):return digest({'objective':spec['objective'],'bytes':{n:h for n,h in spec['initial_snapshot'].items() if n!='.experiment-copy'},'workflow':spec['workflow_contract'],'grant':spec.get('write_grant')})

def load_case(case,path,origin,p):
    out=json.loads(path.read_text())
    if not ordinary(case,out):return None,{'task_id':case['task_id'],'reason':'failed acceptance/completion; retained but not used'}
    group='recovery15' if case['workflow_id']=='FM38' else 'workflow14';source=json.loads((origin/'protocol.json').read_text())
    a=Path(out['attempt']);spec=json.loads((a/'input.json').read_text());schemas=json.loads((a/'tool-schemas.json').read_text())
    if digest(spec)!=out['input_sha256'] or out['source_sha256']!=digest(source['source_code']):raise ValueError('task/source binding changed')
    if json.loads((a/'source-code.json').read_text())!=source['source_code']:raise ValueError('actual source snapshot differs')
    for n,h in p['groups'][group]['dependencies'].items():
        if source['source_code'].get(n)!=h or sha(origin/'frozen-source'/n)!=h or sha(ROOT/n)!=h:raise ValueError('incompatible service dependency: '+n)
    if source['versions']['recovery' if group=='recovery15' else 'workflow']!=p['groups'][group]['execution_version_sha256']:raise ValueError('service version differs')
    run=Path(out['run']['output_dir']);ep=run/'agent-events.jsonl'
    if sha(ep)!=out['events_sha256']:raise ValueError('native events changed')
    events=[json.loads(l) for l in ep.read_text().splitlines()]
    if any(e.get('ptc_analysis_source') or (e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-')) for e in events):raise ValueError('Runtime/projected evidence cannot train or certify')
    rows=native_rows(events);parser=FileScene.__new__(FileScene);replays=0
    for rp in (a/'delivery/reads').glob('*.json'):
        r=json.loads(rp.read_text());src=Path(case['pristine'])/r['path']
        if not src.is_file() or sha(src)!=r['sha256'] or r['source_version']!=digest({'path':r['path'],'sha':r['sha256'],'parser':'fm-parser-v1'}):raise ValueError('original read bytes/version changed')
        try:status,text,meta=parser.parse(src)
        except Exception:
            if r['status']!='unreadable':raise
        else:
            if status!=r['status'] or text[:6000]!=r.get('text','') or meta!=r.get('metadata',{}):raise ValueError('read observation replay differs')
        replays+=1
    return {'case':case,'outcome':out,'spec':spec,'schemas':schemas,'events':events,'rows':rows,'group':group,'fingerprint':fingerprint(spec),
            'trace_id':run.name,'source_reviews':{'task_id':case['task_id'],'trace_id':run.name,'role':case['role'],'group':group,'input_sha256':out['input_sha256'],
                'events_sha256':sha(ep),'source_snapshot_sha256':out['source_sha256'],'dependencies_sha256':digest(p['groups'][group]['dependencies']),
                'service_execution_version_sha256':p['groups'][group]['execution_version_sha256'],'replayed_reads':replays}},None

def collection_episodes(item,p):
    spec=item['spec'];valid=[];errors=[];rows=item['rows']
    inventory={n:{'file_id':'file:local:'+digest({'path':n,'sha':h})[:24],'path':n,'extension':Path(n).suffix.lower(),
                  'sha256':h,'bytes':(Path(item['case']['pristine'])/n).stat().st_size,'source_version':digest({'path':n,'sha':h,'parser':'fm-parser-v1'})}
               for n,h in spec['initial_snapshot'].items() if n!='.experiment-copy'}
    scope={'input_version':digest(spec),'snapshot_sha256':digest(spec['initial_snapshot']),'inventory':list(inventory.values()),'execution_version_sha256':p['versions']['workflow']}
    for row in rows:
        if row['name']!=COLLECTION_TOOLS[0] or not row['out']:continue
        packet=row['out'];ends=[r for r in rows if r['name']==COLLECTION_TOOLS[-1] and r['out'] and r['out'].get('collection_id')==packet['collection_id'] and r['call_seq']>row['result_seq']]
        if not ends:errors.append({'selection_call_id':row['call_id'],'reason':'no successful complete gather'});continue
        end=ends[0]['result_seq'];view=[e for e in item['events'] if row['message_seq']<=e['seq']<=end]
        try:
            w=collection_witness(view,scope,COLLECTION_TOOLS,trace_id=item['trace_id'],task_fingerprint=item['fingerprint'])
            w['family']=item['case']['workflow_id'];w['episode_boundary']={'first_seq':row['message_seq'],'last_seq':end,'original_events_sha256':item['outcome']['events_sha256']};valid.append(w)
        except ValueError as e:errors.append({'selection_call_id':row['call_id'],'reason':str(e)})
    return sorted(valid,key=lambda w:(-w['target_count'],w['episode_boundary']['first_seq']))[:1],errors

def witnesses(exp,p,role):
    traces=[];collections=[];plans=[];reviews=[];excluded=[];schemas_by_group={};raw0=None;ct0=None
    for case,path,origin in outcome_sources(exp,p,role):
        item,error=load_case(case,path,origin,p)
        if error:excluded.append(error);continue
        group=item['group'];ss=item['schemas']
        if group in schemas_by_group and schemas_by_group[group]!=ss:raise ValueError('same service group has different schemas')
        schemas_by_group[group]=ss;reviews.append(item['source_reviews'])
        if group=='workflow14':
            raw,ct=contracts(ss);raw0=raw;ct0=ct
            t=extract_dsh_trace(item['events'],ct,trace_id=item['trace_id'],task_fingerprint=item['fingerprint'],provenance_by_call_id=infer_dsh_provenance(item['events'],ct));traces.append(t)
            cc,errors=collection_episodes(item,p);collections+=cc
            if errors:excluded.append({'task_id':case['task_id'],'candidate':'collection','episode_rejections':errors})
        else:
            # PlanScene's capability packets bind its component version. The outer
            # RecoveryScene/TaskScene/job version is separately pinned by the group lock.
            sc=original_plan_scope(item['spec']);sc['execution_version_sha256']=p['versions']['plan_component']
            try:
                w=plan_witness(item['events'],sc,PLAN_TOOLS,item['trace_id'],item['fingerprint']);w.update(task_id=case['task_id'],service_execution_version_sha256=p['versions']['recovery']);plans.append(w)
            except ValueError as e:excluded.append({'task_id':case['task_id'],'candidate':'authorized_plan','reason':str(e)})
    return {'traces':traces,'collections':collections,'plans':plans,'reviews':reviews,'excluded':excluded,'schemas':schemas_by_group,'raw':raw0,'contracts':ct0}

def learn(exp,p):
    destination=exp/'compiled'
    if destination.exists():raise ValueError('compiled version retained; never overwrite it using certification data')
    if any(list(Path(c['task_dir']).glob('attempts/*/outcome.json')) for c in p['tasks'] if c['role']=='certify'):raise ValueError('freeze training candidates before the first independent certification run')
    w=witnesses(exp,p,'explore');edges=[];rejected=[]
    for candidate in mine_witnessed_parameter_edges(w['traces']):
        try:edges.append(compile_witnessed_edge_motif(candidate,w['traces'],w['contracts']))
        except ValueError as e:rejected.append({'candidate':candidate,'reason':str(e)})
    schemas14={PREFIX+r['name']:r.get('inputSchema',r.get('input_schema')) for r in w['schemas']['workflow14']}
    schemas15={PREFIX+r['name']:r.get('inputSchema',r.get('input_schema')) for r in w['schemas']['recovery15']}
    candidates={'edge':edges,'collection':None,'plan':None};failures=[]
    for kind,fn in [('collection',lambda:compile_collection_motif(w['collections'],collection_contracts(w['schemas']['workflow14']),schemas14)),('plan',lambda:compile_plan(w['plans'],schemas15))]:
        try:candidates[kind]=fn()
        except ValueError as e:failures.append({'candidate':kind,'reason':str(e)})
    save(destination/'candidates.json',candidates);save(destination/'learning-result.json',{'training_reviews':w['reviews'],'excluded':w['excluded'],'edge_rejections':rejected,'compiler_failures':failures,
         'training_count':len(w['reviews']),'edge_candidates':len(edges),'collection_witness_sizes':[v['target_count'] for v in w['collections']],
         'plan_witness_counts':[v['operation_count'] for v in w['plans']],'holdout_used':False,'certification_used':False,'source_sha256':sha(__file__)})
    save(exp/'candidate-lock.json',{'candidate_sha256':sha(destination/'candidates.json'),'learning_result_sha256':sha(destination/'learning-result.json'),
         'protocol_sha256':sha(exp/'protocol.json'),'learning_source_sha256':sha(__file__),'certification_runs_when_frozen':0})
    print(json.dumps({'compiled_edges':len(edges),'compiled_collection':candidates['collection'] is not None,'compiled_plan':candidates['plan'] is not None,'failures':failures,'certification_used':False}));return candidates

def candidate_lock(exp):
    lock=json.loads((exp/'candidate-lock.json').read_text())
    for name,key in [('compiled/candidates.json','candidate_sha256'),('compiled/learning-result.json','learning_result_sha256'),('protocol.json','protocol_sha256')]:
        if sha(exp/name)!=lock[key]:raise ValueError('frozen pre-certification candidate changed')
    if sha(__file__)!=lock['learning_source_sha256']:raise ValueError('learning/certification procedure changed; freeze a new version')

def node_validate(kind,path):
    modules={'collection':('collection_read_policy.ts','validateCollectionPolicy'),'plan':('authorized_plan_policy.ts','validatePlanPolicy'),'edge':('online_skill_runtime.mjs','validateOnlineManifest')}
    module,function=modules[kind]
    code="import fs from 'node:fs';import {"+function+"} from './src/motif_core/"+module+"';"+function+"(JSON.parse(fs.readFileSync(process.argv[1],'utf8')));"
    subprocess.run(['node','--input-type=module','-e',code,str(path)],cwd=ROOT,text=True,capture_output=True,check=True)

def certify(exp,p):
    candidate_lock(exp);destination=exp/'libraries'
    if destination.exists():raise ValueError('certification result retained; prepare a new version for revisions')
    w=witnesses(exp,p,'certify');c=json.loads((exp/'compiled/candidates.json').read_text());results=[];failed=[]
    reviews_by_trace={r['trace_id']:r for r in w['reviews']}
    def prioritized(values,priority):
        def order(v):
            tid=reviews_by_trace[v.trace_id if hasattr(v,'trace_id') else v['trace_id']]['task_id']
            return priority.index(tid) if tid in priority else len(priority)
        return sorted(values,key=order)
    edges=[]
    for edge in c['edge']:
        found=None
        for t in prioritized(w['traces'],p['edge_certification_priority']):
            try:found=certify_witnessed_edge_motif(edge,t,w['contracts']);break
            except ValueError as e:failed.append({'kind':'edge','trace_id':t.trace_id,'reason':str(e)})
        if found:edges.append(found)
    if edges:
        library=library_from_certified(edges);save(destination/'workflow14/edge-library.json',library)
        sp=importlib.util.spec_from_file_location('workflow_edge_exporter',ROOT/'scripts/export-online-motif-manifest.py');ex=importlib.util.module_from_spec(sp);sp.loader.exec_module(ex)
        used={t for a in edges for t in a['tools']};raw={k:{**v,'description':w['contracts'][k].description} for k,v in w['raw'].items()}
        manifest=ex.export_manifest(library,raw,version_fields={t:'source_version' for t in used if 'source_version' in w['contracts'][t].output_fields})
        save(destination/'workflow14/online-manifest.json',manifest);node_validate('edge',destination/'workflow14/online-manifest.json');results.append({'kind':'read_edge','group':'workflow14','artifacts':len(edges),'path':'workflow14/online-manifest.json'})
    for kind in ('collection','plan'):
        if not c[kind]:failed.append({'kind':kind,'reason':'no compiled training candidate'});continue
        values=w['collections'] if kind=='collection' else [v for v in w['plans'] if v['task_id']==p['plan_certification_case']]
        if kind=='collection':values=prioritized(values,p['collection_certification_priority'])
        policy=None
        for v in values:
            try:
                policy=(export_collection_policy(certify_collection_motif(c[kind],v,collection_contracts(w['schemas']['workflow14'])),p['versions']['workflow']) if kind=='collection' else certify_plan(c[kind],v));break
            except ValueError as e:failed.append({'kind':kind,'trace_id':v['trace_id'],'reason':str(e)})
        if policy:
            group='workflow14' if kind=='collection' else 'recovery15';path=destination/group/(kind+'-policy.json');save(path,policy);node_validate(kind,path)
            results.append({'kind':kind,'group':group,'artifacts':1,'path':str(path.relative_to(destination)),'policy_digest':policy['policy_digest']})
        else:failed.append({'kind':kind,'reason':'no independent successful certification witness'})
    lock={'schema_version':1,'groups':p['groups'],'candidate_lock_sha256':sha(exp/'candidate-lock.json'),'certification_source_sha256':sha(__file__),
          'artifacts':[{**r,'sha256':sha(destination/r['path'])} for r in results],
          'activation':'offline fixed-source certification only; default SDK/Web unchanged; durable plan CLI still disabled',
          'recovery_branch_certified':False,'holdout_runs':0}
    save(exp/'library-lock.json',lock)
    result={'certified_artifacts':results,'certification_failures':failed,'certification_reviews':w['reviews'],'excluded':w['excluded'],
            'successful_independent_tasks':len(w['reviews']),'holdout_used':False,'arbitrary_graphs_certified':False,'autonomous_restore_certified':False,
            'human_semantic_review':False,'source_sha256':sha(__file__)}
    save(destination/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('certification_reviews','excluded')},ensure_ascii=False));return result

def audit(exp,p):
    candidate_lock(exp);lock=json.loads((exp/'library-lock.json').read_text());assert lock['groups']==p['groups']
    for group in p['groups']:assert dependencies(group)==p['groups'][group]['dependencies']
    for r in lock['artifacts']:assert sha(exp/'libraries'/r['path'])==r['sha256'];node_validate('edge' if r['kind']=='read_edge' else r['kind'],exp/'libraries'/r['path'])
    parent=json.loads((Path(p['parent'])/'protocol.json').read_text())
    for t in parent['tasks']:
        before=p['parent_protected'][t['task_id']]
        assert digest(snapshot(t['pristine']))==before['snapshot_sha256'];assert sha(Path(t['task_dir'])/'input-template.json')==before['template_sha256'];assert sha(Path(t['task_dir'])/'oracle.json')==before['oracle_sha256']
    for n,h in p['original_pdfs'].items():assert sha(ROOT/'testpdf'/n)==h
    request_count=0;fees=0;tokens=Counter();rows=[]
    for c in p['tasks']:
        o=json.loads(next(Path(c['task_dir']).glob('attempts/*/outcome.json')).read_text());a=Path(o['attempt']);assert o['role']==c['role']
        item,error=load_case(c,a/'outcome.json',exp,p)
        spec=json.loads((a/'input.json').read_text());rp=a/'delivery/report.json';report=json.loads(rp.read_text()) if rp.exists() and o['receipt_verified'] else None
        review=verify_workflow(spec,report,a/'delivery');assert review['passed']==o['acceptance']['passed']
        assert o['accounting_complete'];actual=0;cost=0
        for r in o['runs']:
            run=Path(r['output_dir']);ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()]
            paid=[v for v in ledger if 'request_id' in v and 'response_status' in v];assert len(paid)==r['upstream_requests']
            amt=sum(v['observed_peak_usd'] if v.get('observed_peak_usd') is not None else v['reserved_upper_usd'] for v in paid);assert abs(amt-r['budget_accounted_usd'])<1e-6
            actual+=len(paid);cost+=amt
            for v in paid:tokens.update(v.get('response_usage',{}))
            raw=json.loads((run/'metrics.json').read_text());assert all(raw.get(k,0)==0 for k in ('model_requests_skipped_verified','collection_model_requests_bypassed_verified','plan_model_requests_bypassed_verified','reentry_epoch_batches_verified'))
        assert actual==o['run']['upstream_requests'] and abs(cost-o['run']['budget_accounted_usd'])<1e-6 and cost<=p['per_task_cap_usd']
        if c['workflow_id']=='FM38':
            state=job_command(a/'job.json','state')['state'];assert state['requests']==actual and abs(state['spent_units']/1e9-cost)<1e-6
            assert state['repairs']<=p['max_repairs'] and state['checks']<=p['max_repairs']+1
        rows.append({'task_id':c['task_id'],'role':c['role'],'passed':o['acceptance']['passed'],'requests':actual,'estimated_usd':o['run']['budget_accounted_usd'],'tool_errors':o['tool_errors'],'elapsed_seconds':o['run']['elapsed_seconds']})
        request_count+=actual;fees+=o['run']['budget_accounted_usd']
    result={'status':'passed','rows':rows,'new_model_tasks':len(rows),'machine_passed':sum(r['passed'] for r in rows),'requests':request_count,'estimated_usd':round(fees,9),'tokens':dict(tokens),
            'certified_artifact_count':sum(a['artifacts'] for a in lock['artifacts']),'service_groups':len(p['groups']),'parent_54_pristine_and_holdout_unchanged':True,'original_pdfs_unchanged':True,
            'library_lock_sha256':sha(exp/'library-lock.json'),'source_sha256':sha(__file__),'accounting':accounting(),'human_semantic_review':False,'holdout_runs':0}
    save(exp/'independent-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k!='rows'}));return result

def main():
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path);a.add_argument('--training-parent',type=Path);a.add_argument('--role',choices=['explore','certify']);a.add_argument('--call-model',action='store_true');a.add_argument('--learn',action='store_true');a.add_argument('--certify',action='store_true');a.add_argument('--audit',action='store_true');a.add_argument('--summary',action='store_true');args=a.parse_args()
    if not args.experiment:prepare(args.training_parent);return
    exp=args.experiment.resolve();p=json.loads((exp/'protocol.json').read_text())
    if args.summary:print(json.dumps({k:v for k,v in summarize(exp).items() if k!='outcomes'}));return
    if args.learn:learn(exp,p);return
    if args.certify:certify(exp,p);return
    if args.audit:audit(exp,p);return
    if args.call_model and not args.role:a.error('paid runs require an explicit explore/certify phase; certification cannot precede the candidate lock')
    check_frozen(exp,p)
    if args.role=='certify' and args.call_model:candidate_lock(exp)
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:
        for c in p['tasks']:
            if args.role and c['role']!=args.role:continue
            if list(Path(c['task_dir']).glob('attempts/*/outcome.json')):continue
            check_frozen(exp,p);run_task(exp,c,p,args.call_model)
            if args.call_model:summarize(exp)
    finally:lock.unlink()
if __name__=='__main__':main()
