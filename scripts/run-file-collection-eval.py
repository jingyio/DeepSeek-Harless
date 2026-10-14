"""Balance paired evaluation order without changing frozen training/scene/library."""
import argparse
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import DATA,HERE,digest,sha,save,snapshot,source_code
from collection_tools import execution_version
from collection_study import verify_collection,summarize
from experiment import run_one

def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--call-model',action='store_true');args=p.parse_args()
    exp=args.experiment.resolve();protocol=json.loads((exp/'protocol.json').read_text())
    grouped={}
    for c in protocol['tasks']:
        if c['role']=='evaluate':grouped.setdefault(c['pair_id'],{})[c['arm']]=c
    schedule=[]
    for i,pair in enumerate(grouped):
        schedule.extend(grouped[pair][arm] for arm in (('H','M') if i%2==0 else ('M','H')))
    record={'kind':'evaluation_order_amendment_before_any_evaluation','reason':'preparer used total task count parity and failed to alternate paired order',
            'original_protocol_sha256':sha(exp/'protocol.json'),'schedule':[c['task_id'] for c in schedule],
            'driver_sha256':sha(Path(__file__)),'scene_training_policy_unchanged':True}
    dest=exp/'evaluation-schedule.json'
    if dest.exists():
        if json.loads(dest.read_text())!=record:raise ValueError('frozen evaluation schedule changed')
    else:
        if any((Path(c['task_dir'])/'attempts').exists() for c in schedule):raise ValueError('cannot change order after evaluation began')
        save(dest,record);archive=exp/'evaluation-driver.py';shutil.copyfile(Path(__file__),archive);archive.chmod(0o600)
    print(json.dumps({'planned_runs':len(schedule),'schedule':record['schedule'],'call_model':args.call_model}),flush=True)
    if not args.call_model:return
    if source_code()!=protocol['source_code'] or execution_version()!=protocol['execution_version_sha256']:raise ValueError('frozen execution changed')
    policy=exp/'learned/policy.json'
    if not policy.is_file():raise ValueError('certified policy required')
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:
        for c in schedule:
            td=Path(c['task_dir'])
            if list((td/'attempts').glob('*/outcome.json')):continue
            root=Path(c['workspace']);pristine=Path(c['pristine'])
            if not root.resolve().is_relative_to((DATA/exp.name).resolve()) or not (root/'.experiment-copy').is_file():raise ValueError('unsafe copy reset')
            if snapshot(pristine)!=c['initial_snapshot']:raise ValueError('pristine changed')
            shutil.rmtree(root);shutil.copytree(pristine,root)
            outcome=run_one(exp,c,protocol,call_model=True,server_path=HERE/'collection_tools.py',verify_result=verify_collection,
                collection_policy=policy if c['arm']=='M' else None,collection_task=td/'collection-task.json' if c['arm']=='M' else None)
            retained=DATA/exp.name/'retained-final'/c['task_id'];shutil.copytree(root,retained)
            save(Path(outcome['attempt'])/'final-state.json',{'retained':str(retained),'snapshot':snapshot(retained)})
            save(Path(outcome['attempt'])/'scheduler-config.json',record)
            body=summarize(exp);print(json.dumps({'completed':body['attempts'],'arms':body['arms'],'series':body['series_accounting']}),flush=True)
    finally:lock.unlink()

if __name__=='__main__':main()
