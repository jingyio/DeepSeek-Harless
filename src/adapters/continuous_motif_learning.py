"""Discover supported parameter graphs from new task evidence; freeze, certify, activate.

This service has no business-case IDs and does not import historical final sets.
The existing collection and reentry compilers remain the graph authority.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4
from src.adapters.continuous_rsi import (ROOT, DATA, RUNTIME, source_map, snapshot, private,
                                        records, state_event, writer_lock, load_config)
from src.motif_core.offline.experience_registry import ExperienceRegistry, digest, durable, read, sha
from src.motif_core.offline.collection_compiler import collection_witness,compile_collection_motif,certify_collection_motif,export_collection_policy
from src.motif_core.offline.reentry_compiler import reentry_witness,compile_reentry,certify_reentry
from src.motif_core.offline.operation_graph import catalog,discover_graphs,certify_graph
from src.motif_core.offline.control_flow import discover_flows,certify_flow,FORMAT as FLOW_FORMAT
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from workflow_learning import contracts
from collection_study import contracts as collection_contracts, GRAPH_TOOLS
from file_tools import FileScene


def observations(events):
    calls={};results={};models={}
    for e in events:
        if e.get('ptc_analysis_source'):raise ValueError('projected evidence cannot learn')
        if e['type']=='tool/call':
            cid=e['data']['callId']
            if cid in calls:raise ValueError('duplicate call identity')
            calls[cid]=e
        elif e['type']=='tool/result':
            for b in e['data']['message'].get('content',[]):
                if b.get('type')=='tool-result':results.setdefault(b['toolCallId'],[]).append((e,b))
        elif e['type']=='assistant/message':
            for b in e['data']['message'].get('content',[]):
                if b.get('type')=='tool-call' and e['data'].get('usage') and e['data']['message'].get('source',{}).get('kind')=='model':
                    models[b['id']]=e['seq']
    rows=[]
    for cid,c in sorted(calls.items(),key=lambda v:v[1]['seq']):
        if len(results.get(cid,[]))!=1:continue
        e,b=results[cid][0];content=b.get('content',[])
        text=[v for v in content if v.get('type')=='text']
        images=[v.get('attachment') for v in content if v.get('type')=='image']
        if (b.get('isError') or len(text)!=1 or any(v.get('type') not in ('text','image') for v in content)
                or any(not isinstance(v,dict) or not str(v.get('attachmentId','')).startswith('sha256:') for v in images)):continue
        try:out=json.loads(text[0]['text'])
        except (ValueError,TypeError):continue
        rows.append({'name':c['data']['name'],'call_id':cid,'message_seq':models.get(cid),
                     'call_seq':c['seq'],'result_seq':e['seq'],'args':json.loads(c['data']['arguments']),
                     'out':out,**({'image_attachments':images} if images else {})})
    return rows


def frame(record):
    if not record['accounting_complete'] or record.get('observed_usage_complete') is False:
        raise ValueError('incomplete original provider usage cannot train or certify')
    if record['provider_mode']!='real' or not record['accepted'] or not record['lifecycle_verified']:
        raise ValueError('successful real task and sealed lifecycle required')
    if record['metrics'].get('acceptance_repairs'):raise ValueError('repaired task retained but not clean training')
    origin=private(record['origin']);run=private(record['run_dir']);spec=read(origin/'task.json')
    if spec.get('learning_eligible') is False:raise ValueError('RSI-off task retained but excluded from learning')
    root=origin.parent.parent;queue=read(root/'queue'/(record['session_id']+'.json'))
    record_path=root/'records'/(record['session_id']+'.json')
    if sha(record_path)!=queue['record_sha256'] or not queue['sealed_after_cost_and_acceptance']:
        raise ValueError('sealed task record changed')
    if spec.get('role') in ('holdout','evaluate','benchmark'):raise ValueError('final evaluation is never learning evidence')
    if sha(origin/'task.json')!=record['task_sha256'] or digest(spec)!=record['input_sha256']:
        raise ValueError('original task changed')
    ep=run/'agent-events.jsonl'
    if sha(ep)!=record['events_sha256'] or sha(origin/'tool-schemas.json')!=record['schemas_sha256']:
        raise ValueError('native evidence changed')
    sources=read(origin/'source-code.json')
    if digest(sources)!=record['source_sha256'] or sources!=source_map():raise ValueError('execution or learning source changed')
    if any(sha(origin/'frozen-source'/n)!=h for n,h in sources.items()):raise ValueError('frozen source archive changed')
    if snapshot(origin/'pristine')!=spec['initial_snapshot']:raise ValueError('original material snapshot changed')
    if record.get('adapter'):return operation_frame(record,origin,run,spec)
    events=[json.loads(l) for l in ep.read_text().splitlines()];rows=observations(events)
    task=next((r['out'] for r in rows if r['name']=='mcp__file_management__read_task'),None)
    listing=next((r['out'] for r in rows if r['name']=='mcp__file_management__list_files'),None)
    if not task or not listing or task['input_sha256']!=digest(spec):raise ValueError('actual task/inventory unavailable')
    version=task.get('workflow_execution_version_sha256') or task.get('report_execution_version_sha256') or task.get('collection_execution_version_sha256')
    inventory=[{**r,'source_version':digest({'path':r['path'],'sha':r['sha256'],'parser':'fm-parser-v1'})} for r in listing['files']]
    if listing['snapshot_sha256']!=digest(spec['initial_snapshot']):raise ValueError('initial inventory differs')
    for r in inventory:
        if r['sha256']!=spec['initial_snapshot'][r['path']] or r['file_id']!='file:local:'+digest({'path':r['path'],'sha':r['sha256']})[:24]:
            raise ValueError('actual identity differs')
    # Recompute observations from frozen material, never from expected answer files.
    parser=FileScene.__new__(FileScene)
    for p in (Path(record['delivery'])/'reads').glob('*.json'):
        readback=read(p);src=origin/'pristine'/readback['path']
        if sha(src)!=readback['sha256']:raise ValueError('read bytes differ')
        try:status,text,meta=parser.parse(src)
        except Exception:
            if readback['status']!='unreadable':raise
        else:
            if status!=readback['status'] or text[:6000]!=readback.get('text','') or meta!=readback.get('metadata',{}):
                raise ValueError('read observation replay differs')
    scope={'input_version':digest(spec),'snapshot_sha256':digest(spec['initial_snapshot']),
           'inventory':inventory,'execution_version_sha256':version}
    schemas=read(origin/'tool-schemas.json')
    audit=[json.loads(l) for l in (run/'experience-audit.jsonl').read_text().splitlines()]
    return {'record':record,'spec':spec,'scope':scope,'schemas':schemas,'events':events,'rows':rows,'audit':audit,
            'trace_id':record['session_id'],'fingerprint':record['task_fingerprint']}

def operation_observations(events):
    """Preserve failed/unsupported calls as barriers instead of erasing them."""
    valid={r['call_id']:r for r in observations(events)}
    return [valid.get(e['data']['callId'],{'name':e['data']['name'],'call_id':e['data']['callId'],
             'message_seq':None,'call_seq':e['seq'],'result_seq':None,'args':{},'out':None})
            for e in sorted(events,key=lambda e:e['seq']) if e['type']=='tool/call']

def verify_original_events(record,run,events):
    """Annotations may join attempts; every Runtime event must remain an exact native row."""
    if record.get('adapter') not in ('file_operations_v2','management_v3'):return
    files=record['metrics'].get('attempt_files',record['metrics'].get('native_session_files',[]))
    if not files:raise ValueError('original native attempt files missing')
    originals={};seen=set()
    for item in files:
        path=Path(item['file']).resolve()
        if not path.is_relative_to(run.resolve()) or sha(path)!=item['sha256']:raise ValueError('original native attempt changed')
        key=item.get('attempt',item.get('session_id'));rows=[json.loads(l) for l in path.read_text().splitlines()]
        originals[key]=rows
    offsets={k:0 for k in originals}
    for e in events:
        k=e.get('durable_attempt',e.get('actual_agent_session_id'));i=offsets.get(k)
        if i is None or i>=len(originals[k]):raise ValueError('unproven combined native event')
        native={n:v for n,v in e.items() if n not in ('original_seq','durable_attempt','actual_agent_session_id')}
        native['seq']=e['original_seq']
        if native!=originals[k][i]:raise ValueError('native event modified during recovery')
        offsets[k]+=1
    if any(offsets[k]!=len(rows) for k,rows in originals.items()):raise ValueError('native event erased during recovery')

def operation_frame(record,origin,run,spec):
    from src.adapters.mcp_learning import adapter
    from operation_contract import verify_operations
    scene=adapter(record['adapter']);events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
    verify_original_events(record,run,events)
    rows=operation_observations(events)
    for row in rows:row['generated']=row['call_id'].startswith('sss-')
    schemas=read(origin/'tool-schemas.json');normalized=catalog(schemas);scope=scene.scope(spec)
    scene.verify_record(spec,record,origin,rows,events)
    parents=[];manifest=read(record['registry_file']);base=origin.parent.parent/'registry'
    if sha(record['registry_file'])!=record['registry_sha256']:raise ValueError('in-flight operation library changed')
    for e in manifest['entries']:
        if e['kind']=='operation_graph' and e['entry_id'] in {v['entry_id'] for v in record['selected']}:
            payload=base/e['payload']
            if sha(payload)!=e['sha256']:raise ValueError('inherited operation graph changed')
            parents.append(read(payload))
    audit=[json.loads(l) for l in (run/'experience-audit.jsonl').read_text().splitlines()]
    verify_generated_provenance(rows,audit,normalized,scope,record['adapter'])
    return {'record':record,'spec':spec,'scope':scope,'schemas':schemas,'tools':normalized,'events':events,'rows':rows,'audit':audit,
            'parents':parents,'trace_id':record['session_id'],'fingerprint':record['task_fingerprint']}


def verify_generated_provenance(rows,audit,tools,scope,adapter_id):
    generated={r['call_id'] for r in rows if r['generated']}
    verified={r['call_id'] for r in audit if r['kind']=='operation_model_request_bypassed_verified'}
    probes=[r for r in audit if r['kind']=='management_program_probe_verified'];probe_ids=set()
    stages={'inventory':'mcp__file_management__list_files','pin_context':'mcp__file_management__pin_file','read_context':'mcp__file_management__read_file'}
    for proof in probes:
        row=next((r for r in rows if r['call_id']==proof['call_id']),None)
        if (adapter_id!='management_v3' or row is None or not row['generated'] or not row.get('out')
                or proof['call_id'] in probe_ids or proof['call_id'] in verified or proof.get('source_kind')!='management_program'
                or stages.get(proof.get('stage'))!=row['name'] or proof.get('tool')!=row['name']
                or tools[row['name']]['contract']['effect']!='read' or row['out'].get('_sss_scope')!=scope
                or proof.get('arguments_sha256')!=digest(row['args']) or proof.get('result_sha256')!=digest(row['out'])
                or proof.get('scope_sha256')!=digest(scope) or proof.get('model_request_bypassed') is not False):
            raise ValueError('read-only program probe lacks original actual evidence')
        probe_ids.add(proof['call_id'])
    if generated!=verified|probe_ids:raise ValueError('inherited generated calls lack original verified execution evidence')


def collection_episodes(f):
    valid=[];rejected=[]
    for row in f['rows']:
        if row['name']!=GRAPH_TOOLS[0] or row['message_seq'] is None or row['call_id'].startswith('sss-'):continue
        ends=[r for r in f['rows'] if r['name']==GRAPH_TOOLS[-1] and r['out'].get('collection_id')==row['out'].get('collection_id') and r['call_seq']>row['result_seq']]
        if len(ends)!=1:continue
        view=[e for e in f['events'] if row['message_seq']<=e['seq']<=ends[0]['result_seq']]
        try:
            w=collection_witness(view,f['scope'],GRAPH_TOOLS,trace_id=f['trace_id'],task_fingerprint=f['fingerprint'])
            w['original_events_sha256']=f['record']['events_sha256'];valid.append(w)
        except ValueError as error:rejected.append(str(error))
    return sorted(valid,key=lambda w:-w['target_count'])[:1],rejected


def parent_policy(f,root):
    picked=f['record']['selected']
    if len(picked)!=1 or picked[0]['experience_kind']!='collection':return None
    manifest=read(f['record']['registry_file'])
    if sha(f['record']['registry_file'])!=f['record']['registry_sha256']:raise ValueError('frozen task library changed')
    entry=next(r for r in manifest['entries'] if r['entry_id']==picked[0]['entry_id'])
    path=root/'registry'/entry['payload']
    if sha(path)!=entry['sha256']:raise ValueError('original parent object changed')
    return read(path)


def residual(f,parent):
    selected=[r for r in f['audit'] if r['kind']=='collection_motif_selection_verified']
    if len(selected)!=1:raise ValueError('one actual parent selection required')
    start=next(r['message_seq'] for r in f['rows'] if r['call_id']==selected[0]['call_id'])
    # Omit retrieval probes before the actual model choice, without renaming Runtime calls.
    view=[e for e in f['events'] if e['seq']>=start]
    w=reentry_witness(view,f['scope'],parent,f['audit'],f['trace_id'],f['fingerprint'])
    w['original_events_sha256']=f['record']['events_sha256'];w['view_start_seq']=start
    return w


def discover(root, all_records):
    groups={};excluded=[];operation_frames=[]
    for record in all_records:
        if record['role']!='ordinary':continue
        try:
            f=frame(record)
            if record.get('adapter'):operation_frames.append(f);continue
            parent=parent_policy(f,root)
            if parent:
                w=residual(f,parent);key=digest({'kind':'reentry','parent':parent['policy_digest'],'schemas':f['schemas']})
                groups.setdefault(key,{'kind':'reentry','parent':parent,'frames':[],'witnesses':[]})
                groups[key]['frames'].append(f);groups[key]['witnesses'].append(w)
            elif not record['selected']:
                ww,errors=collection_episodes(f)
                excluded.extend({'session_id':record['session_id'],'reason':e} for e in errors)
                if not ww:continue
                key=digest({'kind':'collection','version':f['scope']['execution_version_sha256'],'schemas':f['schemas']})
                groups.setdefault(key,{'kind':'collection','parent':None,'frames':[],'witnesses':[]})
                groups[key]['frames'].append(f);groups[key]['witnesses'].append(ww[0])
            else:
                excluded.append({'session_id':record['session_id'],
                                 'reason':'selected experience is outside supported two-episode discovery grammar'})
        except (ValueError,KeyError,StopIteration) as error:
            excluded.append({'session_id':record['session_id'],'reason':str(error)})
    candidates=[]
    for key,group in groups.items():
        distinct={}
        for f,w in zip(group['frames'],group['witnesses']):distinct.setdefault(f['fingerprint'],(f,w))
        values=list(distinct.values());group['frames']=[v[0] for v in values];group['witnesses']=[v[1] for v in values]
        try:
            if len(values)<2:raise ValueError('two independent task decisions required')
            schemas={ 'mcp__file_management__'+r['name']:r.get('inputSchema',r.get('input_schema')) for r in values[0][0]['schemas'] }
            ct=collection_contracts(values[0][0]['schemas'])
            compiled=(compile_collection_motif(group['witnesses'],ct,schemas) if group['kind']=='collection' else
                      compile_reentry(group['witnesses'],group['parent'],ct,schemas))
            candidates.append({**group,'key':key,'compiled':compiled})
        except ValueError as error:excluded.append({'opportunity_key':key,'reason':str(error)})
    discovered,rejected=discover_graphs(operation_frames)
    flows,flow_rejected=discover_flows(operation_frames)
    flow_roots={c['compiled']['root'] for c in flows}
    discovered=[c for c in discovered if c['compiled']['nodes'][0]['tool'] not in flow_roots]
    return flows+candidates+discovered,excluded+rejected+flow_rejected


def learning_job(root,candidate,active):
    """Keep an active graph; retry rejected/disabled graphs only with new evidence."""
    base=candidate['key'];compiled=digest(candidate['compiled'])
    for job in [*(Path(root)/'learning').glob('*'), *(Path(root)/'experience/jobs').glob('*')]:
        if not job.is_dir():continue
        activation=read(job/'activation.json') if (job/'activation.json').exists() else None
        opportunity=(activation or {}).get('opportunity_key',job.name)
        if activation and opportunity==base and activation['policy_digest'] in active:
            old=read(job/'compiled.json') if (job/'compiled.json').exists() else {}
            upgraded=(candidate['compiled'].get('kind')=='learned_mcp_control_flow'
                      and {digest(e) for e in old.get('edges',[])} < {digest(e) for e in candidate['compiled'].get('edges',[])})
            if not upgraded:return None
        if (job/'compiled.json').exists() and digest(read(job/'compiled.json'))==compiled:
            return job  # Immutable outcome/started markers decide whether work can resume.
    revision=digest({'opportunity_key':base,'compiled_evidence_sha256':compiled})
    return Path(root)/'learning'/revision


def material(cfg, job, label, origin, role, registry_file=None):
    """New bytes within the authorized read-only copy; keep goals and report rules."""
    if not cfg['allow_material_copy']:raise ValueError('independent material copying not authorized')
    directory=job/'materials'/label
    if (directory/'material.json').exists():return read(directory/'material.json')
    enrollment=read(Path(origin['origin'])/'enrollment.json');spec=read(Path(origin['origin'])/'task.json')
    if not cfg.get('adapter') and (spec['allowed_operations']!=[] or spec.get('workflow_contract') or spec.get('task_contract')):
        raise ValueError('no effectful certification adapter; preserve task for ordinary Harness')
    work=Path(cfg['workspace_roots'][0])/'rsi-materials'/job.name/label
    if work.exists():
        if cfg.get('adapter') not in ('file_operations_v2','management_v3'):raise ValueError('partly prepared material retained; no overwrite')
        # The complete material marker precedes any paid child. Keep the old
        # partial bytes and prepare a fresh sibling, never reuse uncertain input.
        if directory.exists():directory.rename(job/'materials'/('interrupted-preparation-'+label+'-'+uuid4().hex[:8]))
        work=work.with_name(work.name+'-prepared-'+uuid4().hex[:8])
    if cfg.get('adapter'):
        from src.adapters.mcp_learning import adapter
        adapter(cfg['adapter']).copy_material(spec,Path(origin['origin'])/'pristine',work,uuid4().hex)
    else:
        shutil.copytree(Path(origin['origin'])/'pristine',work)
        changes=0;nonce=uuid4().hex
        for p in work.rglob('*'):
            if p.is_file() and p.suffix.lower() in ('.txt','.md') and p.stat().st_size:
                # Rule/notice JSON is semantic input, not a mutable sample body.
                try:json.loads(p.read_text());continue
                except (ValueError,UnicodeError):pass
                p.write_text(p.read_text()+'\nIndependent material '+nonce+'\n');changes+=1
        if not changes:raise ValueError('adapter cannot produce independent bytes without changing task rules')
    spec.update(task_id='rsi-'+job.name+'-'+label,workspace=str(work),initial_snapshot=snapshot(work))
    if cfg.get('adapter')=='management_v3':
        from management_tools import tree
        spec.update(workspace_marker_sha256=sha(work/'.experiment-copy'),initial_tree={'workspace':tree(work)})
        if spec.get('external_roots'):raise ValueError('certification cannot automatically approve external directories')
        goal=spec.get('quality',{}).get('goal',{})
        if goal.get('state')=='frozen':
            from management_goals import compile_goal
            fresh=compile_goal(spec['objective'],spec['initial_tree']['workspace'],spec['quality']['requirements'] if goal.get('source')=='explicit_frozen_checks' else None,initial_roots=spec['initial_tree'])
            if fresh['state']!='frozen' or fresh['requirements']!=spec['quality']['requirements'] or fresh['checks']!=goal['checks']:raise ValueError('independent goal requirements changed')
            fresh.pop('requirements');spec['quality']['goal']=fresh
    durable(directory/'input.json',spec,exclusive=True)
    prompt=directory/'prompt.md';prompt.write_text(enrollment['prompt']);prompt.chmod(0o600)
    scenario=read(enrollment['scenario_file']);scenario['prompt']=str(prompt);durable(directory/'scenario.json',scenario,exclusive=True)
    child={k:v for k,v in cfg.items() if k not in ('config_file','config_sha256','registry_file','candidate_job')}
    child.update(role=role,auto_worker=False,candidate_job=str(job))
    if registry_file:child['registry_file']=str(registry_file)
    durable(directory/'rsi.json',child,exclusive=True)
    value={'directory':str(directory),'workspace':str(work),'task_fingerprint':digest({'objective':spec['objective'],
           'snapshot':{n:h for n,h in spec['initial_snapshot'].items() if n!='.experiment-copy'},'report_contract':spec['report_contract'],'operations':[]}),
           'role':role,'input_sha256':sha(directory/'input.json'),'scenario_sha256':sha(directory/'scenario.json'),'config_sha256':sha(directory/'rsi.json')}
    durable(directory/'material.json',value,exclusive=True);return value


def run_material(cfg, job, label, origin, role, registry=None):
    outcome=job/(label+'-record.json')
    if outcome.exists():return read(outcome)
    material_spec=material(cfg,job,label,origin,role,registry);directory=Path(material_spec['directory'])
    if any(sha(directory/name)!=material_spec[key] for name,key in (('input.json','input_sha256'),('scenario.json','scenario_sha256'),('rsi.json','config_sha256'))):raise ValueError('frozen certification material/config changed')
    existing=[r for r in records(cfg['state_root']) if r.get('candidate_job')==str(job) and read(Path(r['origin'])/'task.json')['task_id']=='rsi-'+job.name+'-'+label]
    if existing:
        if len(existing)!=1:raise ValueError('ambiguous certification record')
        durable(outcome,existing[0],exclusive=True);return existing[0]
    marker=job/(label+'-started.json')
    pending=[p for p in (Path(cfg['state_root'])/'runs').glob('*/enrollment.json') if read(p).get('candidate_job')==str(job) and read(p)['spec']['task_id']=='rsi-'+job.name+'-'+label]
    if marker.exists() and cfg.get('adapter') not in ('file_operations_v2','management_v3'):raise ValueError('interrupted paid task retained; no cold request/budget reset')
    if len(pending)>1:raise ValueError('ambiguous original certification enrollment')
    if not marker.exists():durable(marker,{'material_sha256':sha(directory/'material.json'),'role':role},exclusive=True)
    limits=cfg['limits'];env={**__import__('os').environ,'FM_TASK_FILE':str(directory/'input.json'),'FM_OUTPUT':str(directory/'delivery')}
    args=[sys.executable,str(ROOT/'scripts/run-file-scenario.py'),'--scenario',str(directory/'scenario.json'),
          '--rsi-config',str(directory/'rsi.json'),'--model','deepseek-flash','--budget-usd',str(limits['budget_usd'] if limits['budget_usd'] is not None else 0),
          '--max-steps',str(limits['max_steps'] if limits['max_steps'] is not None else 0),'--max-output',str(limits['max_output'] or 393216),'--call-model']
    if pending:args=[sys.executable,str(ROOT/'scripts/run-file-scenario.py'),'--rsi-resume',str(pending[0].parent),'--call-model']
    log_file=job/(label+'-stdout.log')
    if log_file.exists():log_file=job/(label+'-resume-'+uuid4().hex+'.log')
    with log_file.open('xb') as log:
        status=subprocess.run(args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    matches=[r for r in records(cfg['state_root']) if r.get('candidate_job')==str(job) and read(Path(r['origin'])/'task.json')['task_id']=='rsi-'+job.name+'-'+label]
    if len(matches)!=1:
        if cfg.get('adapter') in ('file_operations_v2','management_v3'):raise RecoveryPending('original certification interrupted; resume its enrollment and original budget')
        raise ValueError('child failed before sealing; exit '+str(status))
    durable(outcome,matches[0],exclusive=True);return matches[0]


def certify_job(cfg,root,job,candidate):
    lock=read(job/'candidate-lock.json')
    if sha(job/'compiled.json')!=lock['candidate_sha256'] or lock['source_code']!=source_map():raise ValueError('frozen candidate/source changed')
    # A resumed queue may contain more observations. Certification keeps the
    # original compiled graph and original independent training records.
    candidate={**candidate,'compiled':read(job/'compiled.json'),
               'frames':[frame(read(t['record_file'])) for t in lock['training']]}
    if any(sha(t['record_file'])!=t['record_sha256'] or f['fingerprint']!=t['task_fingerprint']
           for t,f in zip(lock['training'],candidate['frames'])):
        raise ValueError('frozen training evidence changed')
    origin=candidate['frames'][0]['record'];policy_file=job/'policy.json'
    if not policy_file.exists():
        native=run_material(cfg,job,'native-cert',origin,'native_certification',Path(origin['registry_file']) if candidate['kind'] in ('reentry','operation_graph') else None)
        f=frame(native);ct=collection_contracts(f['schemas']) if candidate['kind']!='operation_graph' else None
        if candidate['kind']=='collection':
            if native['selected']:raise ValueError('native collection certification must be ordinary')
            ww,_=collection_episodes(f)
            if not ww:raise ValueError('no independent native collection witness')
            policy=export_collection_policy(certify_collection_motif(candidate['compiled'],ww[0],ct),f['scope']['execution_version_sha256'])
        elif candidate['kind']=='reentry':
            w=residual(f,candidate['parent']);policy=certify_reentry(candidate['compiled'],w,ct)
        elif candidate['compiled'].get('kind')=='learned_mcp_control_flow':policy=certify_flow(candidate['compiled'],f)
        else:policy=certify_graph(candidate['compiled'],f)
        durable(policy_file,policy,exclusive=True)
        durable(job/'native-review.json',{'role':'native_certification','task_fingerprint':native['task_fingerprint'],
             'record_file':str(root/'records'/(native['session_id']+'.json')),'record_sha256':sha(root/'records'/(native['session_id']+'.json'))},exclusive=True)
    policy=read(policy_file);registry=ExperienceRegistry(root/'registry');relative,raw=registry.object(policy_file)
    if candidate['kind']=='operation_graph':
        from src.adapters.mcp_learning import adapter
        runtime_source=source_map(adapter(cfg['adapter']).runtime_sources())
    else:runtime_source=source_map(RUNTIME)
    view=job/'certification-registry.json'
    if not view.exists():
        manifest={'schema_version':1,'format':'sss-experience-registry-v1','generation':0,'parent_digest':None,
                  'reason':'isolated new Motif actual-execution certification','automatic_selection_uses_profile_id':False,
                  'entries':[{'entry_id':policy['policy_digest'],'artifact_digest':policy['policy_digest'],'kind':candidate['kind'],
                    'payload':relative,'sha256':raw,'runtime_source':runtime_source,'state':'candidate','activated_generation':1}]}
        manifest['registry_digest']=digest(manifest);durable(view,manifest,exclusive=True)
    reviews=[];failures=[]
    for i in (0,1):
        result=run_material(cfg,job,'execute-cert-'+str(i),candidate['frames'][i]['record'],'candidate_certification',view)
        expected=1 if candidate['kind'] in ('collection','operation_graph') else 2
        audit=[json.loads(l) for l in (Path(result['run_dir'])/'experience-audit.jsonl').read_text().splitlines()]
        complete=sum(r['kind']==('operation_graph_complete' if candidate['kind']=='operation_graph' else 'collection_motif_complete') for r in audit)
        repeated=candidate['kind']=='operation_graph' and policy.get('format') in ('sss-operation-graph-v2',FLOW_FORMAT)
        operation_ok=verify_operation_execution(policy,result,audit) if repeated else complete==expected
        if not result['accepted'] or result['policy_digest']!=policy['policy_digest'] or not operation_ok or result['metrics'].get('acceptance_repairs') or result['deferred']:
            failures.append({'session_id':result['session_id'],'reason':'candidate did not independently complete guarded graph and delivery'})
        file=root/'records'/(result['session_id']+'.json')
        reviews.append({'role':'candidate_certification','task_fingerprint':result['task_fingerprint'],'record_file':str(file),'record_sha256':sha(file),
            **({'completion_count':complete,'audit_sha256':sha(Path(result['run_dir'])/'experience-audit.jsonl')} if repeated else {})})
    v2=policy.get('format')=='sss-operation-graph-v2';v3=policy.get('format')==FLOW_FORMAT
    cert={'status':('certified_motif_v3' if v3 else 'certified_motif_v2' if v2 else 'certified_motif_v1') if not failures else 'rejected','kind':candidate['kind'],'policy_digest':policy['policy_digest'],
          'payload_sha256':sha(policy_file),'candidate_lock_file':str(job/'candidate-lock.json'),'candidate_lock_sha256':sha(job/'candidate-lock.json'),
          'native_review':read(job/'native-review.json'),'reviews':reviews,'failures':failures,'holdout_used':False,
          'quality_and_permission_required':True,'net_benefit_required':False,'runtime_source':runtime_source,
          **({'material_quality_contract':'sss-management-quality-v7'} if cfg.get('adapter')=='management_v3' else {}),
          **({'certification_contract':'sss-operation-certification-v3' if v3 else 'sss-operation-certification-v2'} if v2 or v3 else {})}
    cert_file=job/'certificate.json'
    if not cert_file.exists():durable(cert_file,cert,exclusive=True)
    if cert['status'] not in ('certified_motif_v1','certified_motif_v2','certified_motif_v3'):raise ValueError('failed Motif certificate retained; candidate inactive')
    entry=registry.entry(candidate['kind'],policy_file,runtime_source,cert_file)
    state=registry.load();existing=next((e for e in state['entries'] if e['entry_id']==entry['entry_id']),None)
    if existing:
        if existing['state']!='active' or existing['sha256']!=entry['sha256'] or existing.get('certificate')!=entry.get('certificate'):raise ValueError('existing activation differs from frozen certificate')
        file=root/'registry'/read(root/'registry/current.json')['file']
    else:file=registry.publish([entry],reason='continuous task-derived Motif independently certified; cost observed only',expected=state['generation'])
    activation={'policy_digest':policy['policy_digest'],'kind':candidate['kind'],'registry_file':str(file),'registry_sha256':sha(file),
                'certificate_sha256':sha(cert_file),'opportunity_key':candidate['key'],'net_benefit_required':False,'holdout_used':False}
    durable(job/'activation.json',activation,exclusive=True);state_event(root,'motif_activated',activation)
    return activation

class RecoveryPending(RuntimeError):pass

def verify_operation_execution(policy,record,audit):
    """V2: every repetition must finish with a real native root and checked results."""
    f=frame(record);native={r['call_id'] for r in f['rows'] if r['message_seq'] is not None and not r['generated']}
    if policy.get('format')==FLOW_FORMAT:
        from src.motif_core.offline.control_flow import verify_execution_path
        opened=set();closed=set();edges=set();used=set()
        for row in audit:
            if row.get('entry_id')!=policy['policy_digest']:continue
            if row['kind']=='operation_root_verified':
                if row['call_id'] not in native or row['call_id'] in opened|closed:return False
                opened.add(row['call_id'])
            if row['kind']=='operation_graph_complete':
                root=row['root_call_id'];calls=set(row.get('control_call_ids',[]))
                if root not in opened or used&calls or not verify_execution_path(policy,f,row):return False
                used.update(calls);edges.update(row['control_edges']);opened.remove(root);closed.add(root)
        return bool(closed) and not opened and edges=={digest(e) for e in policy['artifact']['edges']} and record['verified_motif_batches']>0 and not record['deferred']
    # Multiple request-scoped roots may be open at once. Recompute each exact
    # binding path from original events; an audit node count alone is not proof.
    from src.motif_core.offline.operation_graph import at,valid_output
    opened=set();closed=set();used=set();rows={r['call_id']:r for r in f['rows']}
    completions=[r for r in audit if r.get('entry_id')==policy['policy_digest'] and r['kind']=='operation_graph_complete']
    if not all('operation_call_ids' in r for r in completions):
        # Legacy single-root certificates retain their original verifier.
        root=None
        for r in audit:
            if r.get('entry_id')!=policy['policy_digest']:continue
            if r['kind']=='operation_root_verified':
                if root is not None or r['call_id'] not in native:return False
                root=r['call_id'];opened.add(root)
            if r['kind']=='operation_graph_complete':
                if r['root_call_id']!=root or r['nodes']!=len(policy['artifact']['nodes']):return False
                closed.add(root);root=None
        return bool(closed) and opened==closed and root is None and record['verified_motif_batches']>0 and not record['deferred']
    for event in audit:
        if event.get('entry_id')!=policy['policy_digest']:continue
        if event['kind']=='operation_root_verified':
            key=event['call_id']
            if key not in native or key in opened|closed:return False
            opened.add(key)
        if event['kind']=='operation_graph_complete':
            root=event['root_call_id'];calls=event['operation_call_ids'];nodes=policy['artifact']['nodes']
            if root not in opened or not calls or calls[0]!=root or len(calls)!=len(nodes) or len(set(calls))!=len(calls) or used.intersection(calls):return False
            path=[rows.get(cid) for cid in calls]
            for i,(node,row) in enumerate(zip(nodes,path)):
                if not row or row['name']!=node['tool'] or not valid_output(row,policy['artifact']['tool_contracts'][row['name']],f['scope']):return False
                if i and (row['args']!={k:at(path[v['node']]['out'],v['path']) for k,v in node['bindings'].items()}
                    or any(path[v['node']]['result_seq']>=row['call_seq'] for v in node['bindings'].values())):return False
            used.update(calls);opened.remove(root);closed.add(root)
    return bool(closed) and not opened and record['verified_motif_batches']>0 and not record['deferred']


def drain(config_file):
    cfg=load_config(config_file);root=Path(cfg['state_root'])
    if cfg['mode']!='learn' or cfg['provider_mode']!='real':return {'status':'observed_only','learning_performed':False}
    while True:
        with writer_lock(root,'worker'):
            while True:
                before={r['session_id'] for r in records(root) if r['role']=='ordinary'}
                result=_drain_locked(cfg,root)
                after={r['session_id'] for r in records(root) if r['role']=='ordinary'}
                if after==before:break
                # A concurrent CLI may have found this writer busy. Its sealed
                # notification remains pending, so the current owner catches up.
        # Catch a seal arriving just before lock release; later arrivals can
        # start their own writer because this process no longer owns the lock.
        if {r['session_id'] for r in records(root) if r['role']=='ordinary'}==after:return result


def _drain_locked(cfg,root):
    all_records=records(root);registry=ExperienceRegistry(root/'registry')
    disable=set()
    for r in all_records:
        if r['role']!='ordinary':continue
        if not r['accepted'] and r.get('failure_class') not in ('provider_unavailable','budget_exhausted','cancelled'):
            disable.update(v['entry_id'] for v in r['selected'])
        disable.update(v['entry_id'] for v in r['deferred'] if v.get('entry_id'))
    active={r['entry_id'] for r in registry.load()['entries'] if r['state']=='active'}
    if disable & active:
        file=registry.publish(disable=disable & active,reason='actual task failure/deferred execution; ordinary fallback retained')
        state_event(root,'motifs_disabled',{'entries':sorted(disable & active),'registry_file':str(file)})
    from .experience_library import enabled, maintain
    migration=maintain(cfg,root,all_records) if enabled(cfg) else None
    candidates,excluded=discover(root,all_records)
    state_event(root,'discovery',{'records':len(all_records),'supported_candidates':len(candidates),'excluded':excluded})
    activations=[]
    for candidate in sorted(candidates,key=lambda c:c['kind']!='reentry'):
        active={r['entry_id'] for r in registry.load()['entries'] if r['state']=='active'}
        job=learning_job(root,candidate,active)
        if job is None:continue
        if (job/'activation.json').exists() or (job/'failure.json').exists():continue
        job.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not (job/'candidate-lock.json').exists():
            durable(job/'compiled.json',candidate['compiled'],exclusive=True)
            lock={'candidate_sha256':sha(job/'compiled.json'),'kind':candidate['kind'],'opportunity_key':candidate['key'],'source_code':source_map(),
                  'training':[{'record_file':str(root/'records'/(f['trace_id']+'.json')),'record_sha256':sha(root/'records'/(f['trace_id']+'.json')),
                               'task_fingerprint':f['fingerprint']} for f in candidate['frames']],
                  'holdout_used':False,'certification_used':False,'net_benefit_required':False}
            durable(job/'candidate-lock.json',lock,exclusive=True)
            state_event(root,'candidate_frozen',{'kind':candidate['kind'],'job':str(job),'lock_sha256':sha(job/'candidate-lock.json')})
        try:activations.append(certify_job(cfg,root,job,candidate))
        except RecoveryPending as error:
            state_event(root,'certification_interrupted',{'job':str(job),'reason':str(error),'original_budget_preserved':True})
        except (ValueError,KeyError,RuntimeError,StopIteration) as error:
            failure={'reason':type(error).__name__+': '+str(error),'candidate_inactive':True,'failures_and_costs_retained':True}
            durable(job/'failure.json',failure,exclusive=True);state_event(root,'candidate_rejected',{'job':str(job),**failure})
    result={'status':'drained','records':len(records(root)),'activations':activations,'excluded':excluded,'net_benefit_required':False,
            'experience_library':migration}
    durable(root/'worker-latest.json',result);return result
