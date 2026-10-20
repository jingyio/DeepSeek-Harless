"""Certify a current-goal shape relation against a reviewed pure validator.

This is a data-contract primitive, not arbitrary black-box cause discovery.
No historical lengths, report text or field positions become runtime rules.
"""
import copy
import json
from pathlib import Path
from .script_motif_compiler import digest, sha
from .negative_outcome import negative_outcome

def shape_issues(expected,actual,path=''):
    if isinstance(expected,(int,float)) and not isinstance(expected,bool):
        raise ValueError('numeric_shape_not_portable')
    if type(expected) is not type(actual):
        return [{'pointer':path,'expected_type':type(expected).__name__,'actual_type':type(actual).__name__}]
    if isinstance(expected,list):
        if len(expected)!=len(actual):return [{'pointer':path,'expected_items':len(expected),'actual_items':len(actual)}]
        return [v for i,(a,b) in enumerate(zip(expected,actual)) for v in shape_issues(a,b,path+'/'+str(i))][:32]
    if isinstance(expected,dict):
        if set(expected)!=set(actual):return [{'pointer':path,'expected_keys':sorted(expected),'actual_keys':sorted(actual)}]
        return [v for k in expected for v in shape_issues(expected[k],actual[k],path+'/'+k.replace('~','~0').replace('/','~1'))][:32]
    return []

def project(value,path):
    for k in path.split('/')[1:]:
        k=k.replace('~1','/').replace('~0','~');value=value[int(k)] if isinstance(value,list) else value[k]
    return value

def replace(value,path,replacement):
    keys=[k.replace('~1','/').replace('~0','~') for k in path.split('/')[1:]]
    if not keys:return copy.deepcopy(replacement)
    parent=value
    for k in keys[:-1]:parent=parent[int(k)] if isinstance(parent,list) else parent[k]
    parent[int(keys[-1]) if isinstance(parent,list) else keys[-1]]=copy.deepcopy(replacement)
    return value

def constraint_observations(task):
    task=Path(task).resolve();cfg=json.loads((task/'effective-config.json').read_text());work=Path(cfg['workspace']).resolve()
    if not work.is_relative_to(task.parent.parent):raise ValueError('foreign_constraint_workspace')
    path=work/'review-recovery-scope.json'
    if path.resolve()!=path or not path.is_file():return []
    raw=path.read_bytes();goal=json.loads(raw)
    if goal.get('task_id')!=task.name or goal.get('policy')!='preserve_structure_allow_semantic_leaf_revisions':return []
    grant=json.loads((work/'paper-output-grant.json').read_bytes())
    if grant.get('allow_output') is not True or grant.get('task_id')!=task.name:return []
    calls={};found=[];events=(task/'events.jsonl').read_bytes()
    for event in map(json.loads,events.splitlines()):
        d=event.get('data',{})
        if event['type']=='tool/call':
            a=d['arguments'];calls[d['callId']]=(d['name'],json.loads(a) if isinstance(a,str) else a)
        if event['type']!='tool/result':continue
        for b in d.get('message',{}).get('content',[]):
            call=calls.pop(b.get('toolCallId'),None)
            if call is None or b.get('isError'):continue
            try:v=json.loads(next(c['text'] for c in b['content'] if c['type']=='text'))
            except (ValueError,KeyError,StopIteration):continue
            e=v.get('execution_evidence',{}) if isinstance(v,dict) else {};args=call[1]
            if e.get('arguments_sha256')!=digest(args) or e.get('recovery_scope_sha256')!=sha(raw) or e.get('task_id')!=task.name or e.get('grant_sha256')!=digest(grant) or e.get('source_versions')!=goal['source_versions'] or args.get('source_versions')!=goal['source_versions']:continue
            found.append({'tool':call[0],'arguments':args,'goal':goal['arguments'],'result':v,
                          'call_id':b['toolCallId'],'task_id':task.name,'events_sha256':sha(events)})
    return found

def certify_current_constraint(rule,observations,validator):
    failed_ids={(w['task_id'],w['call_id']) for w in rule['certification']['failures']}
    success_ids={(w['task_id'],w['call_id']) for w in rule['certification']['success_contrasts']}
    failures=[];successes=[];interventions=[]
    for row in observations:
        if row['tool']!=rule['tool']:continue
        key=(row['task_id'],row['call_id']);goal,args=row['goal'],row['arguments']
        actual=validator(goal,args);predicted=shape_issues(goal,args)
        if digest(actual)!=digest(predicted):raise ValueError('constraint_provider_disagreement')
        if key in success_ids and negative_outcome(row['result'])['status']=='success' and not actual:
            successes.append({k:row[k] for k in ['task_id','call_id','events_sha256']})
        if key not in failed_ids or not actual or digest(actual)!=digest(row['result'].get('scope_issues')):continue
        checks={i.get('check') for i in row['result'].get('argument_issues',[])}
        if rule['failure_code'] not in checks:continue
        repaired=copy.deepcopy(args)
        for issue in actual:repaired=replace(repaired,issue['pointer'],project(goal,issue['pointer']))
        if validator(goal,repaired) or shape_issues(goal,repaired):continue
        reintroduced=copy.deepcopy(goal)
        for issue in actual:reintroduced=replace(reintroduced,issue['pointer'],project(args,issue['pointer']))
        if not validator(goal,reintroduced) or not shape_issues(goal,reintroduced):continue
        unrelated=[]
        def strings(v,path=''):
            if isinstance(v,dict):
                for k,x in v.items():yield from strings(x,path+'/'+k.replace('~','~0').replace('/','~1'))
            elif isinstance(v,list):
                for i,x in enumerate(v):yield from strings(x,path+'/'+str(i))
            elif isinstance(v,str):yield path,v
        for path,value in strings(args):
            if any(path==i['pointer'] or path.startswith(i['pointer']+'/') for i in actual):continue
            changed=replace(copy.deepcopy(args),path,value+' diagnostic')
            if digest(validator(goal,changed))==digest(actual):unrelated.append(path)
            if len(unrelated)==2:break
        if len(unrelated)<2:continue
        failures.append({k:row[k] for k in ['task_id','call_id','events_sha256']})
        interventions.append({'failure_state_sha256':digest([goal,args]),'repair_state_sha256':digest([goal,repaired]),
            'reintroduction_state_sha256':digest([goal,reintroduced]),'unrelated_edit_paths':unrelated,
            'repair_passed':True,'reintroduction_failed':True})
    if len(failures)<2 or not successes:raise ValueError('current_constraint_witnesses_insufficient')
    return {'version':1,'kind':'current_scope_shape','scope_file':'review-recovery-scope.json','tool':rule['tool'],'failure_code':rule['failure_code'],
            'certification':{'scope':'reviewed_validator_and_real_scope_shape_not_semantic_quality',
                'failures':failures,'successes':successes,'interventions':interventions}}
