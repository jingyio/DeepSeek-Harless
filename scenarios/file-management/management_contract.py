"""Frozen objective predicates and actual effect/approval/directory provenance."""
import json,copy
from pathlib import Path
from common import digest,sha
VERSION='sss-management-quality-v7'
def verify_management(spec,report,output,*,root_paths=None,events=None):
    from management_tools import tree,execution_version
    out=Path(output);errors=[];report=report or {}
    paths={'workspace':spec['workspace'],**{k:v['path'] for k,v in spec.get('external_roots',{}).items()}}
    actual={k:tree((root_paths or paths)[k]) for k in paths}
    if not report or report.get('task_id')!=spec['task_id'] or report.get('input_sha256')!=digest(spec) or report.get('final_tree')!=actual:errors.append('actual report identity/tree differs')
    state=json.loads((out/'management-state.json').read_text())
    if state.get('state_sha256')!=digest({k:v for k,v in state.items() if k!='state_sha256'}):errors.append('state integrity differs')
    if state['execution_version']!=execution_version() or state['expected_tree']!=actual:errors.append('actual state/version differs')
    if spec.get('quality',{}).get('version')!=VERSION:errors.append('frozen quality version differs')
    from management_tools import RESERVED
    files={k+'/'+p:h for k,t in actual.items() for p,h in t['files'].items() if p not in RESERVED and (k=='workspace' or k+'/'+p in state.get('external_read_grants',[]))}
    ids={'file:local:'+digest({'path':p,'sha':h})[:24] for p,h in files.items()}
    if len(report.get('file_ids',[]))!=len(ids) or set(report.get('file_ids',[]))!=ids:errors.append('report file identities differ from actual authorized files')
    expected=spec['initial_tree']
    for p,j in state['journals'].items():
        if j['before']!=expected:errors.append('journal chain differs')
        if j['status']=='restored_verified':
            plan=state['plans'][p];chain=j['restore_before']
            if len(j.get('restore_boundaries',[]))!=len(j['completed']):errors.append('incomplete restoration boundaries')
            for b in j.get('restore_boundaries',[]):
                if b['before']!=chain:errors.append('restoration boundary chain differs')
                chain=b['after']
            if chain!=j['before']:errors.append('restoration final boundary differs')
            if plan['risks']:
                f=out/'restore-approvals'/f'{p}.json'
                if not f.exists():errors.append('missing actual restoration approval')
                else:
                    a=json.loads(f.read_text());key=digest({'plan_sha256':plan['plan_sha256'],'direction':'restore','before':j['restore_before']})
                    if a['plan_sha256']!=key or a['proof'].get('task_sha256')!=digest(spec) or a['proof'].get('outcome')!='allowed-once':errors.append('restoration approval differs')
            expected=j['before'];continue
        if j['status']!='executed_verified':errors.append('unfinished management operation');continue
        plan=state['plans'][p]
        if plan['task_sha256']!=digest(spec) or plan['plan_sha256']!=digest({k:v for k,v in plan.items() if k!='plan_sha256'}):errors.append('plan identity/integrity differs')
        if plan['risks']:
            f=out/'approvals'/f'{p}.json'
            if not f.is_file():errors.append('missing actual one-plan approval')
            else:
                a=json.loads(f.read_text())
                if a['plan_sha256']!=plan['plan_sha256'] or a['proof'].get('task_sha256')!=digest(spec) or a['proof'].get('outcome')!='allowed-once':errors.append('approval differs from actual task/plan')
        chain=j['before']
        if len(j['completed'])!=len(j['effects']) or len(j['boundaries'])!=len(j['completed']):errors.append('incomplete actual effect boundaries')
        if j['completed']!=j['effects']:errors.append('actual effect sequence differs')
        for e,b in zip(j['effects'],j['boundaries']):
            legal=copy.deepcopy(b['before']);t=legal[e['root']]
            if e['kind']=='mkdir':t['directories']=sorted(set(t['directories'])|{e['path']})
            elif e['kind']=='unlink':t['files'].pop(e['path'],None)
            elif e['kind'] in ('publish','replace'):t['files'][e['path']]=e['sha256']
            else:errors.append('unknown effect primitive')
            if legal!=b['after']:errors.append('effect changed files beyond recorded primitive')
            if b['before']!=chain:errors.append('effect boundary chain differs')
            chain=b['after']
        if chain!=j['after']:errors.append('effect final boundary differs')
        expected=j['after']
    if expected!=actual:errors.append('unrequested filesystem changes')
    from management_reading import verify_documents,verify_visual_reads,coverage
    errors.extend(verify_documents(spec,state,out))
    errors.extend(verify_visual_reads(spec,state,out))
    integrity_errors=list(errors)
    requirements=spec.get('quality',{}).get('requirements',[])
    goal=spec.get('quality',{}).get('goal',{})
    from management_goals import compile_goal
    if not goal:goal=compile_goal(spec['objective'],spec['initial_tree']['workspace'],requirements if requirements else None,initial_roots=spec['initial_tree'])
    if goal and goal.get('objective_sha256')!=digest(spec['objective']):errors.append('frozen goal differs from original user objective')
    if goal.get('state')=='frozen':
        fresh=compile_goal(spec['objective'],spec['initial_tree']['workspace'],requirements if goal.get('source')=='explicit_frozen_checks' else None,initial_roots=spec['initial_tree'])
        # Temporal predicates are frozen alongside file predicates, including
        # explicit contracts; supplying file checks cannot erase language timing.
        if any(fresh.get(k)!=goal.get(k) for k in ('format','state','expected_tree','expected_roots','expected_origins','intermediate_sources','temporal')):errors.append('frozen complete goal contract differs')
        if goal.get('expected_roots')!=actual:errors.append('goal file/directory coverage differs from frozen objective')
    if goal.get('state')=='frozen' and 'expected_tree' in goal and actual['workspace']!=goal['expected_tree']:errors.append('goal file/directory coverage differs from frozen objective')
    from management_provenance import lineage_history,read_origin
    try:
        origins=lineage_history(spec,state)[-1]['origins']
        if goal.get('state')=='frozen' and any(origins.get(n)!=v for n,v in goal.get('expected_origins',{}).items()):errors.append('goal original source lineage differs')
        for r in state.get('reads',{}).values():
            if r['path'].startswith('workspace/'):read_origin(spec,r,state)
    except (ValueError,KeyError) as error:errors.append('read/source provenance rejected: '+str(error))
    for r in requirements:
        if r.get('kind')=='temporal':continue
        if r.get('kind') not in ('directory','empty_directory','missing','file','unchanged','read') or r.get('root_id','workspace') not in actual:errors.append('unknown frozen predicate');continue
        t=actual[r.get('root_id','workspace')];kind=r['kind'];p=r['path']
        if kind=='directory' and p not in t['directories']:errors.append('required directory missing: '+p)
        elif kind=='empty_directory' and (p not in t['directories'] or any(n.startswith(p+'/') for n in [*t['files'],*t['directories']])):errors.append('required empty directory differs: '+p)
        elif kind=='missing' and (p in t['files'] or p in t['directories']):errors.append('required removal missing: '+p)
        elif kind=='file':
            original=spec['initial_tree'][r.get('source_root','workspace')]['files'][r['source']]
            if t['files'].get(p)!=original:errors.append('required file/bytes differ: '+p)
        elif kind=='unchanged' and t['files'].get(p)!=spec['initial_tree'][r.get('root_id','workspace')]['files'].get(p):errors.append('unrelated file changed: '+p)
        elif kind=='read':
            n=r.get('root_id','workspace')+'/'+p;source=r.get('source',p);source_root=r.get('source_root',r.get('root_id','workspace'))
            original=spec['initial_tree'][source_root]['files'].get(source)
            reads=[v for v in state.get('reads',{}).values() if v.get('path')==n and v.get('sha256')==original]
            if r.get('source'):reads=[v for v in reads if v.get('provenance',{}).get('origin')==source_root+'/'+source]
            documents=[d for d in state.get('documents',{}).values() if d['anchor']['path']==n and d['anchor']['sha256']==original]
            if r.get('source'):documents=[d for d in documents if d['anchor'].get('provenance',{}).get('origin')==source_root+'/'+source]
            if r.get('mode'):documents=[d for d in documents if d['mode']==r['mode']]
            full_document=any(coverage(d)['complete'] for d in documents)
            if not full_document and not any(not r.get('mode') and v.get('status')=='readable' and v.get('truncated') is False and not v.get('metadata',{}).get('preview_only') for v in reads):errors.append('required complete read missing: '+p)
    from management_temporal import verify_temporal
    timing=verify_temporal(goal.get('temporal',{'state':'not_requested'}),events,state,
        __import__('src.adapters.mcp_learning',fromlist=['adapter']).adapter('management_v3').scope(spec))
    errors.extend(timing['errors'])
    verified=not errors and goal.get('state')=='frozen' and timing['verified']
    return {'passed':not errors,'errors':errors,'quality_version':VERSION,'effect_integrity_verified':not integrity_errors,
            'semantic_quality_verified':verified,'goal_status':'verified' if verified else 'failed' if errors else 'review_required',
            'goal_checks':goal.get('checks',[]),'goal_review_reason':goal.get('reason'),'temporal':timing,
            'human_blind_review':False,'actual_approval_required':True}
