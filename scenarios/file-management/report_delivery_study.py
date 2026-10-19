"""Fresh report serialization diagnosis, then a fixed RSI quality/cost horizon."""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
from uuid import uuid4
import auto_rsi as rsi
import continual_rsi as continual
import fallback_rsi as fresh
from common import ROOT,save,sha
from script_reuse_study import arms
from src.motif_core.offline.experience_registry import ExperienceRegistry


def prior_learning(parent,p):
    files={Path(f) for f in p['prior_nonholdout_learning_cost']['outcomes']}
    for part in p['seeds']:
        for c in part['origins']:files.add(next(Path(c['task_dir']).glob('attempts/*/outcome.json')))
    for pattern in ('exploration-*-materials.json','supplemental-exploration-*-materials.json',
                    'certification-*-materials.json','seed-supplement-*-materials.json'):
        for f in parent.glob(pattern):
            for c in rsi.read(f)['tasks']:
                if c['role'] in ('explore','certify'):files.add(next(Path(c['task_dir']).glob('attempts/*/outcome.json')))
    rows=[rsi.read(f) for f in files]
    if any(o['role'] not in ('explore','certify') for o in rows):raise ValueError('historical costs cannot import evaluation evidence')
    return {'cost_usd':sum(o['run']['budget_accounted_usd'] for o in rows),
            'outcomes':{str(f):sha(f) for f in sorted(files)}}


def prepare(parent,diagnostic):
    old=rsi.read(parent/'protocol.json');diagnosis=rsi.read(diagnostic/'summary.json')
    if diagnosis['attempts']!=12 or any(diagnosis['arms'][a]['passed']!=6 for a in 'HF'):
        raise ValueError('finish fresh report diagnosis before preparing the quality/cost study')
    exp=ROOT/'.local/file-management'/('fm-report-rsi-20261014-'+uuid4().hex[:8]);exp.mkdir(mode=0o700)
    shutil.copytree(parent/'registry',exp/'registry')
    for n in ('launcher.py','control.patch.yml'):shutil.copyfile(parent/n,exp/n)
    reg=ExperienceRegistry(exp/'registry');reg.publish(disable=[e['entry_id'] for e in reg.load()['entries'] if e['state']=='active'],
        reason='report serializer service version changed; immutable old artifacts retained, fresh learning/certification required')
    templates,seeds,tasks=[],[],[]
    for n,business in enumerate(('FM05:min','FM17:all','FM05:max','FM17:filtered'),1):
        origins=[]
        for i in (0,1):
            t,rr=rsi.make(exp,'explore',business,bool(i),i,'report-seed-'+str(n)+'-'+str(i),('H',))
            templates.append(t);origins.extend(rr)
        seeds.append({'round':n,'origins':origins})
    stream=[('FM05:max',False,0),('FM05:max',True,1),('FM05:max',False,1),
            ('FM17:filtered',False,0),('FM17:filtered',True,1),('FM17:filtered',True,0)]
    for i,(business,layout,size) in enumerate(stream):
        t,_=rsi.make(exp,'observe',business,layout,size,'report-stream-'+str(i),())
        fresh.rewrite_goal(t,continual.NOVEL_GOALS[business]);templates.append(t)
        order=tuple('HSFR');offset=i%4;tasks.extend(arms(exp,t,order[offset:]+order[:offset]))
    diagnostics=[*old['diagnostic_cost_sources'],{'experiment':str(diagnostic),'summary_sha256':sha(diagnostic/'summary.json'),
                 'cost_usd':sum(v['cost_usd'] for v in diagnosis['arms'].values())}]
    p={**old,'experiment_id':exp.name,'type':'current-state report serializer; fresh frozen operational/final H/S/F/R horizon',
       'templates':templates,'tasks':tasks,'seeds':seeds,'probes':[],'imported_pre_certification_evidence':[],
       'batch_cap_usd':100,'seed_relearning_due_to_service_change':True,'seed_roles':['explore','certify'],
       'prior_nonholdout_learning_cost':prior_learning(parent,old),'diagnostic_cost_sources':diagnostics,
       'operational_pairs':len(stream),'automatic_upgrade_rounds':[5,6],'upgrade_after_stream_indices':[1,4],
       'old_final_holdout_opened':False,'final_holdout_learning_permitted':False,
       'final_materials_created_only_after_upgrades':True,'structural_report_improvement_common_to_all_arms':True,
       'equal_quality_gate':{'operational_passed_each':len(stream),'positive_final_passed_each':8,'version_stops_each':2},
       'series_before':rsi.accounting(),'test_sources':{n:sha(exp/n) for n in ('control.patch.yml','launcher.py')}}
    fresh.freeze_sources(exp,p);save(exp/'protocol.json',p);save(exp/'protocol-lock.json',{'sha256':sha(exp/'protocol.json')})
    save(ROOT/'.local/file-management/report-rsi-current.json',{'experiment':str(exp)})
    rsi.state_event(exp,'prepared',{'stream_pairs':len(stream),'final_pairs':10,'batch_usd':100,'old_final_not_opened':True})
    print(json.dumps({'experiment':str(exp),'paid':False,'operational_pairs':len(stream),'batch_cap_usd':100}),flush=True)
    return exp


def summarize(exp,p):
    value=continual.summarize(exp,p);f,r=value['arms']['F'],value['arms']['R'];g=p['equal_quality_gate']
    equal=all(v['operational_tasks']==v['operational_passed']==g['operational_passed_each'] and
              v['positive_final_conditions']==v['positive_final_passed']==g['positive_final_passed_each'] and
              v['version_stops']==g['version_stops_each'] for v in (f,r))
    value.update(equal_delivery_quality_F_R=equal,observed_net_API_benefit=equal and r['full_api_cost_usd']<f['full_api_cost_usd'],
                 structural_report_improvement_common_to_all_arms=True)
    save(exp/'summary.json',value);return value


def execute(exp,p):
    seed=continual.build_seed(exp,p);current=lambda:exp/'registry'/rsi.read(exp/'registry/current.json')['file']
    grouped={};observed=[]
    for c in p['tasks']:grouped.setdefault(c['pair_id'],[]).append(c)
    for i,cases in enumerate(grouped.values()):
        for c in cases:
            o=rsi.run_task(exp,c,p,Path(seed['registry_file']) if c['arm']=='F' else current() if c['arm']=='R' else None)
            if c['arm']=='R':observed.append((c,o))
            summarize(exp,p)
        if i in p['upgrade_after_stream_indices']:
            n=5+p['upgrade_after_stream_indices'].index(i);rsi.cycle(exp,p,n,[c for c,o in observed[-2:]])
        if i in (2,5):
            c,o=observed[-1]
            if not o['script_steps'] or not o['acceptance']['passed'] or o['run']['upstream_requests']:
                raise ValueError('certified operational upgrade did not execute on its next independent task')
            rsi.state_event(exp,'prior_upgrade_executed_in_next_round',{'outcome_file':str(Path(o['attempt'])/'outcome.json'),'requests':0})
    held=continual.final_materials(exp,p)
    if sha(exp/'final-materials.json')!=rsi.read(exp/'final-lock.json')['sha256'] or sha(held['registry_file'])!=held['registry_sha256']:
        raise ValueError('final freeze changed')
    for c in held['tasks']:
        rsi.run_task(exp,c,p,Path(seed['registry_file']) if c['arm']=='F' else Path(held['registry_file']) if c['arm']=='R' else None)
        summarize(exp,p)
    rsi.state_event(exp,'complete',{'operational_pairs':len(grouped),'final_pairs':10,'new_operational_upgrades':2,'final_learning':False})
    return summarize(exp,p)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--parent',type=Path);parser.add_argument('--diagnostic',type=Path)
    parser.add_argument('--experiment',type=Path);parser.add_argument('--call-model',action='store_true');args=parser.parse_args()
    if not args.experiment:
        if not args.parent or not args.diagnostic:parser.error('--parent and --diagnostic required')
        prepare(args.parent.resolve(),args.diagnostic.resolve());return
    exp=args.experiment.resolve();p=rsi.read(exp/'protocol.json')
    if not args.call_model:print(json.dumps({'experiment':str(exp),'paid':False,'batch_usd':p['batch_cap_usd']}));return
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:print(json.dumps(execute(exp,p)),flush=True)
    except BaseException as error:
        rsi.state_event(exp,'stopped_with_failure',{'type':type(error).__name__,'message':str(error),'failures_retained':True});summarize(exp,p);raise
    finally:lock.unlink()


if __name__=='__main__':main()
