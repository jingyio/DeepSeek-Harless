"""Explicit legacy translations; old bytes propose programs, never authorize them."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from uuid import uuid4
from src.motif_core.offline.experience_registry import digest,read,sha,durable,ExperienceRegistry,check_motif_certificate

FORMAT='sss-management-legacy-adapter-v1'
PROGRAM='sss-management-program-v1'
PREFIX='mcp__file_management__'


def node(tool, **bindings):
    return {'tool':PREFIX+tool,'bindings':{k:{'node':v[0],'path':v[1]} for k,v in bindings.items()}}


def graph_nodes(family):
    if family in ('collection','reentry'):
        return [node('select_files'),node('pin_files',file_ids=(0,'files[].file_id')),
                node('read_files',source_ids=(1,'source_ids')),
                node('collect_reads',collection_id=(0,'collection_id'),source_ids=(1,'source_ids'))]
    if family=='read_library':return [node('pin_file'),node('read_file',source_id=(0,'source_id'))]
    if family=='plan':return [node('preview_actions'),node('execute_plan',plan_id=(0,'plan_id'))]
    raise ValueError('unregistered legacy graph family')


def unsigned(value,field):return {k:v for k,v in value.items() if k!=field}


def validate_steps(steps):
    if not isinstance(steps,list) or not 1<=len(steps)<=3:raise ValueError('bounded copy program required')
    copies=0;hashed=False
    for s in steps:
        if s=={'op':'hash_representatives','order':'min'} or s=={'op':'hash_representatives','order':'max'}:
            if copies or hashed:raise ValueError('hash instruction order changed')
            hashed=True;continue
        if (set(s)!={'op','source','strip_prefix','destination_slot'} or s['op']!='copy_map'
                or s['source'] not in ('task_sources','nonempty_txt_sources','hash_representatives','prior_targets')
                or s['destination_slot']!=copies or s['source']=='hash_representatives' and not hashed
                or s['source']=='prior_targets' and copies!=1):raise ValueError('unsupported learned copy instruction')
        safe_prefix(s['strip_prefix'],allow_empty=True);copies+=1
    if not 1<=copies<=2:raise ValueError('copy stage bounds changed')
    return steps


def safe_prefix(value,allow_empty=False):
    if value=='' and allow_empty:return value
    if (not isinstance(value,str) or not value.endswith('/') or value.startswith('/') or '\\' in value
            or any(p in ('','.','..') for p in value[:-1].split('/'))):raise ValueError('unsafe relative prefix')
    return value


def script_bindings(policy):
    """Recover explicit goal/rule and source-root bindings from training only."""
    from .continuous_rsi import ROOT
    from .experience_library import bounded_file
    rawsteps=copy.deepcopy(policy['steps']);guards=policy.get('guard_cases') or [{k:policy[k] for k in ('objective_sha256','context_text_sha256','destination_prefixes')}]
    results=[]
    for guard in guards:
        for witness in policy['training']:
            outcome=bounded_file(ROOT,witness['outcome_file'])
            if witness.get('role')!='explore' or sha(outcome)!=witness['outcome_sha256'] or read(outcome).get('role')!='explore':continue
            spec=read(bounded_file(ROOT,outcome.parents[2]/'input-template.json'));contract=spec['workflow_contract']
            if spec.get('role') in ('holdout','evaluate','benchmark') or spec.get('learning_eligible') is False:continue
            if digest(spec['objective'])!=guard['objective_sha256'] or contract['destination_prefixes']!=guard['destination_prefixes']:continue
            contexts=contract['context_paths']
            if len(contexts)>1:continue
            rule=None
            if contexts:
                if not outcome.is_relative_to(ROOT/'.local'):continue
                reads=[read(bounded_file(ROOT,p)) for p in (outcome.parent/'delivery/reads').glob('*.json')]
                matching=[v for v in reads if v.get('path')==contexts[0] and v.get('status')=='readable' and v.get('truncated') is False
                          and digest(v.get('text'))==guard['context_text_sha256']]
                if len(matching)!=1:continue
                rule=matching[0]['text']
            if (digest(rule) if rule is not None else None)!=guard['context_text_sha256']:continue
            steps=[];copies=0
            for s in rawsteps:
                if s['op']=='hash_representatives':steps.append({'op':s['op'],'order':s.get('order','min')});continue
                step={k:v for k,v in s.items() if k!='destination_prefix'}
                step['destination_slot']=s.get('destination_slot',copies)
                if 'destination_prefix' in s and s['destination_prefix']!=guard['destination_prefixes'][step['destination_slot']]:raise ValueError('legacy fixed destination changed')
                steps.append(step);copies+=1
            validate_steps(steps)
            prefixes=sorted({n.split('/')[0]+'/' for n in contract['source_paths']})
            for p in [*prefixes,*guard['destination_prefixes']]:safe_prefix(p)
            if len(prefixes)>4 or any(a.startswith(b) or b.startswith(a) for a in prefixes for b in guard['destination_prefixes']):raise ValueError('ambiguous source/destination roots')
            results.append({'steps':steps,'guard':guard,'source_prefixes':prefixes,'context_paths':contexts,
                            'objective':spec['objective'],'rule':rule,'source_training_sha256':sha(outcome)})
            break
    if len(results)!=len(guards):raise ValueError('original training goal/rule binding unavailable; do not infer from final tasks')
    return results


def proposals(root,entries=None):
    from .experience_library import load
    root=Path(root);groups={};rejected=[]
    for item in load(root)['entries'] if entries is None else entries:
        kind=item['kind']
        if kind not in ('collection','reentry','read_library','plan','script_v1','script_v2'):continue
        try:
            p=read(root/'experience'/item['payload'])
            if kind.startswith('script_'):
                variants=script_bindings(p);training=[r['task_fingerprint'] for r in p['training']]
            else:
                if kind=='read_library':training=[f for a in p['artifacts'] for f in a['source_task_fingerprints']]
                else:training=p['artifact']['source_task_fingerprints']
                variants=[{'nodes':graph_nodes(kind)}]
                if kind=='read_library':variants[0]['alternatives']=[graph_nodes(kind),[node('pin_files'),node('read_files',source_ids=(0,'source_ids'))]]
            for variant in variants:
                family='copy_program' if kind.startswith('script_') else kind
                structure={k:v for k,v in variant.items() if k not in ('objective','rule','source_training_sha256')}
                key=digest({'format':FORMAT,'family':family,**structure})
                row=groups.setdefault(key,{'key':key,'family':family,**variant,'aliases':[], 'training':[]})
                row['aliases'].append({'kind':kind,'digest':item['artifact_digest'],'sha256':item['sha256'],'payload':item['payload']})
                row['training']=sorted(set(row['training'])|set(training))
        except (ValueError,KeyError,OSError) as error:rejected.append({'key':item['key'],'reason':str(error)})
    for row in groups.values():row['aliases']=sorted(row['aliases'],key=digest)
    return list(sorted(groups.values(),key=lambda p:(p['family'],p['key']))),rejected


def program_actions(proposal,inventory,groups=None,prior=(),stage=0):
    """Pure reference interpreter, consuming actual metadata, never quality answers."""
    steps=[s for s in proposal['steps'] if s['op']=='copy_map'];step=steps[stage]
    rows=[r for r in inventory if r.get('root_id','workspace')=='workspace' and any(r['path'].startswith(p) for p in proposal['source_prefixes'])
          and ('current_source_paths' not in proposal or r['path'] in proposal['current_source_paths'])]
    if step['source']=='prior_targets':rows=[next(r for r in inventory if r['path']==n) for n in prior]
    elif step['source']=='nonempty_txt_sources':rows=[r for r in rows if not (r['path'].lower().endswith('.txt') and r['bytes']==0)]
    elif step['source']=='hash_representatives':
        if groups is None:raise ValueError('actual hash observation required')
        available={r['file_id']:r for r in rows};seen=[];chosen=[]
        for g in groups:
            members=[]
            for f in g['files']:
                r=available.get(f['file_id'])
                if not r or f['path']!='workspace/'+r['path'] or r['sha256']!=g['sha256']:raise ValueError('actual hash membership differs')
                seen.append(r['file_id']);members.append(r)
            chosen.append(sorted(members,key=lambda r:r['path'])[0 if proposal['steps'][0]['order']=='min' else -1])
        if len(seen)!=len(set(seen)) or set(seen)!=set(available):raise ValueError('incomplete actual hash roster')
        rows=chosen
    if not 1<=len(rows)<=32:raise ValueError('copy roster outside old bounds')
    prefix=step['strip_prefix'];dest=proposal['guard']['destination_prefixes'][step['destination_slot']]
    result=[]
    for r in rows:
        if not r['path'].startswith(prefix):raise ValueError('original strip prefix differs')
        target=dest+r['path'][len(prefix):]
        if any(v['path']==target for v in inventory):raise ValueError('destination already exists; ordinary confirmation required')
        result.append({'op':'copy','file_ids':[r['file_id']],'destination':target})
    return result


def program_output_contract(recipe,inventory):
    """Reference acceptance from original byte identities, not model prose."""
    current=copy.deepcopy(inventory);originals={r['file_id']:r['path'] for r in inventory};outputs=[];prior=[];possible=[];parents=set()
    sources=[r for r in inventory if any(r['path'].startswith(p) for p in recipe['source_prefixes'])
             and ('current_source_paths' not in recipe or r['path'] in recipe['current_source_paths'])]
    groups={}
    for r in sources:groups.setdefault(r['sha256'],[]).append({'file_id':r['file_id'],'path':'workspace/'+r['path']})
    groups=[{'sha256':h,'files':rows} for h,rows in groups.items()]
    for i,s in enumerate(v for v in recipe['steps'] if v['op']=='copy_map'):
        inputs=possible if s['source']=='prior_targets' else [r['path'] for r in sources]
        possible=[recipe['guard']['destination_prefixes'][s['destination_slot']]+n[len(s['strip_prefix']):] for n in inputs if n.startswith(s['strip_prefix'])]
        for n in possible:
            parts=n.split('/');parents.update('/'.join(parts[:j]) for j in range(1,len(parts)))
        actions=program_actions(recipe,current,groups,prior,i)
        selected={a['destination'] for a in actions}
        for a in actions:
            source=next(r for r in current if r['file_id']==a['file_ids'][0]);original=originals[source['file_id']]
            outputs.append({'kind':'file','source':original,'path':a['destination']})
            fid='file:local:'+digest({'path':'workspace/'+a['destination'],'sha':source['sha256']})[:24]
            current.append({**source,'file_id':fid,'path':a['destination']});originals[fid]=original
        prior=[a['destination'] for a in actions]
        outputs.extend({'kind':'missing','path':n} for n in possible if n not in selected)
    return {'requirements':outputs,'parent_directories':sorted(parents)}


def verify_program_delivery(recipe,record):
    from .continuous_rsi import snapshot
    origin=Path(record['origin']);spec=read(origin/'task.json')
    if sha(origin/'task.json')!=record['task_sha256'] or snapshot(origin/'pristine')!=spec['initial_snapshot']:raise ValueError('program original material changed')
    recipe={**recipe}
    if spec.get('approved_inputs'):recipe['current_source_paths']=[v['path'] for v in spec['approved_inputs']]
    initial=spec['initial_tree']['workspace']['files']
    inventory=[{'file_id':'file:local:'+digest({'path':'workspace/'+n,'sha':h})[:24],'path':n,'root_id':'workspace','sha256':h,'bytes':(origin/'pristine'/n).stat().st_size} for n,h in initial.items() if n!='.experiment-copy']
    expected=copy.deepcopy(initial);contract=program_output_contract(recipe,inventory)
    for r in contract['requirements']:
        if r['kind']=='file':expected[r['path']]=initial[r['source']]
    actual=snapshot(origin/'final-workspace')
    if actual!=expected:raise ValueError('program final files/bytes differ from original plus exact copied roster; no extra duplicates allowed')
    return {'format':'sss-exact-management-program-delivery-v1','expected_snapshot_sha256':digest(expected),'actual_snapshot_sha256':digest(actual),'record_sha256':sha(origin.parent.parent/'records'/(record['session_id']+'.json'))}


def native_program_proof(proposal,f):
    if digest(f['spec']['objective'])!=proposal['guard']['objective_sha256']:raise ValueError('native program goal differs')
    inventories=[r for r in f['rows'] if r['name']==PREFIX+'list_files' and not r['generated']]
    plans=[r for r in f['rows'] if r['name']==PREFIX+'preview_actions' and not r['generated']]
    if any(not isinstance(r['out'],dict) or r['result_seq'] is None for r in f['rows']
           if not r['generated'] and r['name'] in (PREFIX+'preview_actions',PREFIX+'list_files',PREFIX+'hash_files')):
        raise ValueError('failed native preview, inventory or hash call is a certification barrier')
    copyplans=[r for r in plans if any(a.get('op')=='copy' for a in r['out'].get('actions',[]))]
    rule_ref=None
    if proposal['context_paths']:
        for row in f['rows']:
            if row['generated'] or not row['out'] or not copyplans or row['result_seq']>=copyplans[0]['call_seq']:continue
            reads=[row['out']] if row['name']==PREFIX+'read_file' else row['out'].get('reads',[]) if row['name']==PREFIX+'read_files' else []
            for i,v in enumerate(reads):
                if (v.get('path')=='workspace/'+proposal['context_paths'][0] and v.get('status')=='readable' and v.get('truncated') is False
                        and digest(v.get('text'))==proposal['guard']['context_text_sha256']):rule_ref={'call_id':row['call_id'],'tool':row['name'],'read_index':i,'body_sha256':digest(v['text'])}
        if rule_ref is None:raise ValueError('native rule read missing, incomplete or after copy planning')
    count=sum(s['op']=='copy_map' for s in proposal['steps'])
    prior=[];proof=[];cursor=0
    for stage in range(count):
        if cursor>=len(plans):raise ValueError('native copy program stage missing')
        plan=plans[cursor]
        preceding=[r for r in inventories if r['result_seq']<plan['call_seq']]
        if not preceding:raise ValueError('native refreshed inventory required')
        inv=preceding[-1];hashes=[r for r in f['rows'] if r['name']==PREFIX+'hash_files' and not r['generated'] and r['result_seq']<plan['call_seq']]
        recipe={**proposal}
        if f['spec'].get('approved_inputs'):recipe['current_source_paths']=[v['path'] for v in f['spec']['approved_inputs']]
        actions=program_actions(recipe,inv['out']['files'],hashes[-1]['out']['groups'] if hashes else None,prior,stage)
        allowed_dirs=set(program_output_contract(recipe,inventories[0]['out']['files'])['parent_directories'])
        if stage and inv['call_seq']<=proof[-1]['execute_result_seq']:raise ValueError('recovery did not refresh actual backup identities')
        remaining={digest(a):a for a in actions};calls=[];end=0
        while remaining:
            if cursor>=len(plans):raise ValueError('native copy map incomplete')
            plan=plans[cursor];packet=plan['out']
            if packet.get('risks') or not packet.get('actions'):raise ValueError('native program cannot inherit high-risk approval')
            for a in packet['actions']:
                if a['op']=='mkdir':
                    if a.get('destination_root')!='workspace' or a.get('source_root')!='workspace' or a.get('destination') not in allowed_dirs:raise ValueError('native directory is not a necessary program parent')
                    continue
                if a['op']!='copy' or a['source_root']!='workspace' or a['destination_root']!='workspace':raise ValueError('native program effect outside copy workspace')
                source=next((r for r in inv['out']['files'] if r['path']==a['source'] and r['sha256']==a['source_sha256']),None)
                if source is None:raise ValueError('native copy source lacks actual inventory provenance')
                canonical={'op':'copy','file_ids':[source['file_id']],'destination':a['destination']}
                if digest(canonical) not in remaining:raise ValueError('native choices do not demonstrate proposed copy stage')
                del remaining[digest(canonical)]
            executed=[r for r in f['rows'] if r['name']==PREFIX+'execute_plan' and not r['generated'] and r['out'] and r['out'].get('plan_id')==packet.get('plan_id') and r['out'].get('_sss_authorized') is True]
            if len(executed)!=1:raise ValueError('native verified execution required for every copy plan')
            end=max(end,executed[0]['result_seq']);calls.append({'preview_call_id':plan['call_id'],'execute_call_id':executed[0]['call_id']});cursor+=1
        prior=[a['destination'] for a in actions]
        proof.append({'inventory_call_id':inv['call_id'],'native_plans':calls,'execute_result_seq':end,'actions_sha256':digest(actions),'rule_read':rule_ref})
    if cursor!=len(plans):raise ValueError('extra native copy plans outside proposed program')
    return proof


def make_template(cfg,proposal,job):
    """New diagnostic material; never read historical final/holdout materials."""
    from .continuous_rsi import ROOT
    import sys
    sys.path.insert(0,str(ROOT/'scenarios/file-management'))
    from management_prepare import prepare
    directory=job/'material-template'
    if (directory/'template-lock.json').exists():
        lock=read(directory/'template-lock.json')
        if lock!={str(p.relative_to(directory)):sha(p) for p in directory.rglob('*') if p.is_file() and p.name!='template-lock.json'}:raise ValueError('legacy template changed')
        return directory
    if directory.exists():directory.rename(job/('interrupted-template-'+uuid4().hex))
    work=directory/'pristine';work.mkdir(parents=True,mode=0o700)
    nonce=uuid4().hex;family=proposal['family'];quality=[]
    if family=='copy_program':
        for i,prefix in enumerate(proposal['source_prefixes']):
            for name,content in [('a.txt','Identical original '+nonce),('nested/b.md','Identical original '+nonce),('c.txt','Unique '+str(i)+nonce),('empty.txt',''),('empty.md','')]:
                p=work/(prefix+name);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
            if any(s.get('source')=='nonempty_txt_sources' for s in proposal['steps']):
                for name in ('EMPTY.TXT','EMPTY.MD'):(work/(prefix+name)).write_text('')
        for context in proposal['context_paths']:
            p=work/context;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(proposal['rule'])
        inventory=[{'file_id':n,'path':n,'root_id':'workspace','sha256':sha(p),'bytes':p.stat().st_size} for p in work.rglob('*') if p.is_file() for n in [p.relative_to(work).as_posix()]]
        # This reference generates only the frozen oracle, never runtime inputs.
        quality=program_output_contract(proposal,inventory)['requirements']
        quality += [{'kind':'unchanged','path':p.relative_to(work).as_posix()} for p in work.rglob('*') if p.is_file()]
        goal=proposal['objective']
    elif family=='plan':
        (work/'original.txt').write_text('Independent original '+nonce)
        goal='把 original.txt 复制到 organized/original.txt，保持原件不变，核验实际产物后提交报告。'
        quality=[{'kind':'file','source':'original.txt','path':'organized/original.txt'},{'kind':'unchanged','path':'original.txt'}]
    else:
        names=['note.txt'] if family=='read_library' else ['scope.md','scope-extra.md','body-a.txt','body-b.md'] if family=='reentry' else ['alpha.txt','beta.md','table.csv']
        for name in names:(work/name).write_text(('本次第二批阅读 body-a.txt 和 body-b.md。\n' if name=='scope.md' else '')+'New source '+nonce+' '+name)
        goal=('先声明 scope.md 和 scope-extra.md 为第一批阅读集合并完整读取、汇集结果；按其正文确定第二批集合，再完整读取 body-a.txt 和 body-b.md 并汇集第二批实际读取结果，保持全部原件不变。' if family=='reentry' else
              '完整阅读 note.txt 的正文，使用它自己的实际单文件来源句柄，保留文件不变，核验后提交报告。' if family=='read_library' else
              '先声明 alpha.txt、beta.md 和 table.csv 为本次阅读集合，完整读取后汇集该集合的实际读取结果。保持全部原件不变，提交覆盖清单。')
        quality=[q for name in names for q in [{'kind':'read','path':name},{'kind':'unchanged','path':name}]]
    spec=prepare(directory,work,task_id='legacy-'+job.name,objective=goal,owner='legacy-local-certification',workspace_id=proposal['key'],quality=quality,role='native_certification')
    if family in ('collection','reentry','read_library'):spec['rules']['read_only']=True
    if family=='copy_program':
        spec['certification_fixed_sources']=proposal['context_paths']
        spec['approved_inputs']=[{'root_id':'workspace','path':p.relative_to(work).as_posix()} for p in work.rglob('*') if p.is_file() and any(p.relative_to(work).as_posix().startswith(n) for n in proposal['source_prefixes'])]
    durable(directory/'task.json',spec,exclusive=True)
    durable(directory/'enrollment.json',{'prompt':(directory/'prompt.md').read_text(),'scenario_file':str(directory/'scenario.json'),'template_only':True},exclusive=True)
    durable(directory/'template-lock.json',{str(p.relative_to(directory)):sha(p) for p in directory.rglob('*') if p.is_file()},exclusive=True)
    return directory


def certify_proposal(cfg,proposal,job):
    from .continuous_rsi import source_map,state_event
    from .continuous_motif_learning import frame,run_material,verify_operation_execution,RecoveryPending
    from .management_recertification import native_view,rebuild
    from .experience_library import sources
    from src.motif_core.offline.operation_graph import certify_graph,witnesses
    root=Path(cfg['state_root']);job=Path(job)
    import os
    if not (root/'worker.lock').exists() or read(root/'worker.lock').get('pid')!=os.getpid():raise ValueError('legacy certification requires original worker lock')
    for name in ('activation.json','failure.json'):
        if (job/name).exists():return read(job/name)
    request=read(job/'request.json')
    frozen={'format':FORMAT,'proposal':proposal,'request_sha256':sha(job/'request.json'),'source':source_map(),'config_sha256':cfg['config_sha256'],'final_holdouts_used':False}
    lock=job/'candidate-lock.json'
    if not lock.exists():durable(lock,frozen,exclusive=True)
    elif read(lock)!=frozen:raise ValueError('original legacy candidate/source/config changed')
    def guard():
        if source_map()!=frozen['source'] or sha(cfg['config_file'])!=frozen['config_sha256']:raise ValueError('legacy certification source/config changed')
    try:
        if request.get('seed_origin'):
            if sha(request['seed_record_file'])!=request['seed_record_sha256']:raise ValueError('original new ordinary seed changed')
            frame(read(request['seed_record_file']));template=Path(request['seed_origin'])
        else:template=make_template(cfg,proposal,job)
        guard();training=sorted(set(proposal['training'])|({request['seed']} if request.get('seed_origin') else set()))
        empty=job/'native-empty-registry.json'
        if not empty.exists():
            manifest={'format':'sss-experience-registry-v1','schema_version':1,'generation':0,'parent_digest':None,'entries':[],'automatic_selection_uses_profile_id':False,'reason':'current native legacy certification'}
            durable(empty,{**manifest,'registry_digest':digest(manifest)},exclusive=True)
        origin={'origin':str(template)};native=run_material(cfg,job,'native-cert',origin,'native_certification',empty);f=frame(native)
        legacy={'format':FORMAT,'key':proposal['key'],'family':proposal['family'],'aliases':proposal['aliases'],'permissions_expanded':False}
        if proposal['family']=='copy_program':
            delivery=verify_program_delivery(proposal,native)
            if not (job/'native-program-delivery.json').exists():durable(job/'native-program-delivery.json',delivery,exclusive=True)
            proof=native_program_proof(proposal,f);durable(job/'native-program-proof.json',proof,exclusive=True) if not (job/'native-program-proof.json').exists() else None
            artifact={'kind':'learned_management_copy_program','status':'trace_validated_effectful','source_task_fingerprints':training,
                      'validation_task_fingerprint':f['fingerprint'],'certification_contract':'sss-management-program-certification-v1',
                      'delivery_contract':'sss-exact-management-program-delivery-v1',
                      'recipe':{k:proposal[k] for k in ('steps','guard','source_prefixes','context_paths','objective')},'tool_contracts':f['tools'],'legacy_adapter':legacy}
            artifact['certified_digest']=digest(artifact)
            policy={'schema_version':1,'format':PROGRAM,'artifact':artifact,'execution_version_sha256':f['scope']['execution_version']};policy['policy_digest']=digest(policy)
            kind='management_program'
        else:
            variants=proposal.get('alternatives',[proposal['nodes']]);matched=[]
            for candidate_nodes in variants:
                try:matched.append((candidate_nodes,*native_view(f,candidate_nodes)))
                except ValueError:pass
            if not matched:raise ValueError('current native decisions did not demonstrate any declared equivalent legacy graph')
            nodes,view,proof=matched[0]
            if proposal['family']=='reentry' and len([w for w in witnesses(f['rows'],f['tools'],f['scope']) if w['nodes'][:len(nodes)]==nodes])!=2:raise ValueError('native second semantic reading selection required')
            old={'artifact':{'nodes':nodes,'source_task_fingerprints':training,'witnesses':[]}}
            compiled=rebuild(old,f,{'legacy_proposal_key':proposal['key'],'candidate_lock_sha256':sha(lock)})
            compiled['legacy_adapter']=legacy;policy=certify_graph(compiled,view);kind='operation_graph'
            if not (job/'compiled.json').exists():durable(job/'compiled.json',compiled,exclusive=True)
        file=job/'policy.json'
        if not file.exists():durable(file,policy,exclusive=True)
        elif read(file)!=policy:raise ValueError('resumed legacy policy changed')
        registry=ExperienceRegistry(root/'registry');relative,raw=registry.object(file);runtime=sources()
        manifest={'format':'sss-experience-registry-v1','schema_version':1,'generation':0,'parent_digest':None,'automatic_selection_uses_profile_id':False,'reason':'isolated current legacy candidate',
                  'entries':[{'entry_id':policy['policy_digest'],'artifact_digest':policy['policy_digest'],'kind':kind,'payload':relative,'sha256':raw,'runtime_source':runtime,'state':'candidate','activated_generation':1}]}
        candidate=job/'certification-registry.json'
        if not candidate.exists():durable(candidate,{**manifest,'registry_digest':digest(manifest)},exclusive=True)
        reviews=[];failures=[]
        for i in range(2):
            guard();record=run_material(cfg,job,'execute-cert-'+str(i),origin,'candidate_certification',candidate);frame(record)
            if kind=='management_program':verify_program_delivery(proposal,record)
            audit=Path(record['run_dir'])/'experience-audit.jsonl';rows=[json.loads(l) for l in audit.read_text().splitlines()]
            complete=sum(r['kind']=='operation_graph_complete' and r.get('entry_id')==policy['policy_digest'] for r in rows)
            program=sum(r['kind']=='management_program_complete' and r.get('entry_id')==policy['policy_digest'] for r in rows)
            valid=program==1 if kind=='management_program' else verify_operation_execution(policy,record,rows) and (complete==2 if proposal['family']=='reentry' else complete>=1)
            if not valid or record['deferred'] or record['policy_digest']!=policy['policy_digest']:failures.append({'session_id':record['session_id'],'reason':'complete guarded candidate execution required'})
            rf=root/'records'/(record['session_id']+'.json')
            reviews.append({'role':'candidate_certification','task_fingerprint':record['task_fingerprint'],'record_file':str(rf),'record_sha256':sha(rf),'audit_sha256':sha(audit),'completion_count':complete})
        nativefile=root/'records'/(native['session_id']+'.json')
        cert={'status':'rejected' if failures else 'certified_motif_v1' if kind=='management_program' else 'certified_motif_v2','kind':kind,'policy_digest':policy['policy_digest'],'payload_sha256':raw,
              'candidate_lock_file':str(lock),'candidate_lock_sha256':sha(lock),'native_review':{'role':'native_certification','task_fingerprint':native['task_fingerprint'],'record_file':str(nativefile),'record_sha256':sha(nativefile)},
              'reviews':reviews,'failures':failures,'holdout_used':False,'quality_and_permission_required':True,'net_benefit_required':False,'runtime_source':runtime,
              'material_quality_contract':'sss-management-quality-v7','certification_contract':policy['artifact']['certification_contract']}
        if kind=='management_program':cert.update(native_program_proof_file=str(job/'native-program-proof.json'),native_program_proof_sha256=sha(job/'native-program-proof.json'),
                                                 native_program_delivery_file=str(job/'native-program-delivery.json'),native_program_delivery_sha256=sha(job/'native-program-delivery.json'))
        if not (job/'certificate.json').exists():durable(job/'certificate.json',cert,exclusive=True)
        if failures:raise ValueError('independent actual legacy certification failed')
        guard();entry=registry.entry(kind,file,runtime,job/'certificate.json');state=registry.load()
        existing=next((e for e in state['entries'] if e['entry_id']==entry['entry_id']),None)
        if existing is None:version=registry.publish([entry],expected=state['generation'],reason='legacy adapter current native and independent actual certification')
        elif existing['state']=='active':version=root/'registry'/read(root/'registry/current.json')['file']
        else:raise ValueError('disabled legacy artifact cannot be silently reactivated')
        result={'status':'activated','kind':kind,'policy_digest':policy['policy_digest'],'legacy_key':proposal['key'],'registry_file':str(version),'registry_sha256':sha(version),'holdout_used':False}
        durable(job/'activation.json',result,exclusive=True);state_event(root,'legacy_adapter_activated',result);return result
    except RecoveryPending:raise
    except (ValueError,KeyError,RuntimeError,OSError,StopIteration) as error:
        failure={'status':'rejected','reason':type(error).__name__+': '+str(error),'candidate_inactive':True,'failures_and_costs_retained':True,'holdout_used':False}
        if not (job/'failure.json').exists():durable(job/'failure.json',failure,exclusive=True)
        state_event(root,'legacy_adapter_rejected',{'job':str(job),**failure});return failure


def job_key(proposal,target,seed='original-training-proposal'):
    return digest({'adapter':FORMAT,'proposal':proposal['key'],'target':target,'seed':seed})


def certification_target(runtime):
    from .experience_library import target_version
    return digest({'runtime_and_catalog':target_version(runtime),'legacy_compiler_sha256':sha(__file__),'format':FORMAT})


def current_legacy_keys(root,runtime):
    from .experience_library import policy_current
    state=ExperienceRegistry(Path(root)/'registry').load();result=set()
    for e in state['entries']:
        if e['state']=='active' and e['runtime_source']==runtime:
            p=read(Path(root)/'registry'/e['payload'])
            if policy_current(p,runtime):
                key=p.get('artifact',{}).get('legacy_adapter',{}).get('key')
                if key:result.add(key)
    return result


def opportunity(cfg,proposal,target):
    """Same failure needs genuinely new ordinary evidence, never a fresh nonce."""
    from .continuous_rsi import records,source_map
    from .continuous_motif_learning import frame
    from .experience_library import material_graph_observed
    root=Path(cfg['state_root']);base=root/'experience/jobs'/job_key(proposal,target)
    for request in sorted((root/'experience/jobs').glob('*/request.json')):
        original=read(request);job=request.parent
        if (original.get('adapter_format')==FORMAT and original.get('key')==proposal['key']
                and not (job/'failure.json').exists() and not (job/'activation.json').exists()):
            return job,{k:original[k] for k in ('seed','seed_origin','seed_record_file','seed_record_sha256') if k in original}
    if not (base/'failure.json').exists() and not (base/'activation.json').exists():return base,{}
    stamp=max(p.stat().st_mtime_ns for p in [base/'failure.json',base/'activation.json'] if p.exists())
    candidates=[r for r in records(root) if r['role']=='ordinary' and r.get('source_sha256')==digest(source_map())]
    candidates.sort(key=lambda r:(root/'records'/(r['session_id']+'.json')).stat().st_mtime_ns,reverse=True)
    for r in candidates:
        file=root/'records'/(r['session_id']+'.json')
        if file.stat().st_mtime_ns<=stamp:continue
        job=root/'experience/jobs'/job_key(proposal,target,r['task_fingerprint'])
        if (job/'failure.json').exists() or (job/'activation.json').exists():continue
        try:
            f=frame(r)
            if f['spec'].get('external_roots') or f['spec'].get('quality',{}).get('goal',{}).get('state')!='frozen':continue
            if proposal['family']=='copy_program':native_program_proof(proposal,f)
            else:
                if not any(material_graph_observed(f,n) for n in proposal.get('alternatives',[proposal['nodes']])):continue
                if proposal['family']=='reentry' and sum(row['name']==PREFIX+'select_files' and not row['generated'] for row in f['rows'])!=2:continue
            return job,{'seed':r['task_fingerprint'],'seed_origin':r['origin'],'seed_record_file':str(file),'seed_record_sha256':sha(file)}
        except (ValueError,KeyError,OSError,StopIteration):continue
    return None,{}


def pending(cfg):
    from .experience_library import sources
    from .continuous_rsi import source_map
    root=Path(cfg['state_root']);runtime=sources();target=certification_target(runtime);current=current_legacy_keys(root,runtime)
    candidates,_=proposals(root)
    for p in candidates:
        if p['key'] in current:continue
        job,seed=opportunity(cfg,p,target)
        if job is not None:
            request=read(job/'request.json') if (job/'request.json').exists() else None
            if request is None or request['target']==target and request['source']==source_map() and request['config_sha256']==cfg['config_sha256']:return True
    return False


def maintain(cfg,remaining):
    from .experience_library import sources
    from .continuous_rsi import source_map,ROOT
    from .continuous_motif_learning import RecoveryPending
    from .management_backup import budget_snapshot
    root=Path(cfg['state_root']);runtime=sources();target=certification_target(runtime);active=current_legacy_keys(root,runtime)
    candidates,issues=proposals(root);attempted=[];deferred=[]
    for p in candidates:
        if p['key'] in active:continue
        job,seed=opportunity(cfg,p,target)
        if job is None:
            deferred.append({'key':p['key'],'state':'awaiting_new_evidence'});continue
        if len(attempted)>=remaining:
            deferred.append({'key':p['key'],'state':'queued'});continue
        request={'adapter_format':FORMAT,'key':p['key'],'target':target,'proposal':p,'source':source_map(),
                 'config_sha256':cfg['config_sha256'],'original_budgets_retained':True,'holdout_used':False,**seed}
        if (job/'request.json').exists():
            original=read(job/'request.json')
            if any(original[k]!=request[k] for k in ('target','source','config_sha256')):
                deferred.append({'key':p['key'],'state':'source_version_blocked','job':str(job)});continue
            request=original
        else:
            budget=budget_snapshot(ROOT)
            if (budget['learning_spent_usd']+budget['learning_reserved_usd']+cfg['limits']['budget_usd']>cfg['learning_cap_usd']
                    or budget['series']['estimated_usd']+budget['pending_usd']+cfg['limits']['budget_usd']>cfg['series_cap_usd']):
                deferred.append({'key':p['key'],'state':'budget_blocked'});continue
            durable(job/'request.json',request,exclusive=True)
        try:result=certify_proposal(cfg,request['proposal'],job)
        except RecoveryPending as error:result={'status':'pending','reason':str(error)}
        attempted.append({'key':p['key'],'job':str(job),**result})
    return {'format':FORMAT,'attempted':attempted,'deferred':deferred,'issues':issues,'original_budgets_retained':True}
