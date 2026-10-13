"""Fixed read-only file acceptance and immutable per-round evidence archive."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import DATA,digest,save,snapshot
from report_study import verify_report,benchmark_targets
from verify import verify as legacy_verify

def private(path):
    p=Path(path)
    if p.is_symlink() or not p.resolve().is_relative_to((ROOT/'.local').resolve()):raise ValueError('private acceptance path outside scope')
    return p.resolve()

def check(task_file,task_sha,delivery_root,archive_root,round_no,payload):
    task_file=private(task_file);delivery=private(delivery_root);archive=private(archive_root)
    if hashlib.sha256(task_file.read_bytes()).hexdigest()!=task_sha:raise ValueError('frozen task changed; permissions cannot widen')
    spec=json.loads(task_file.read_text());workspace=Path(spec['workspace'])
    if workspace.is_symlink() or not workspace.resolve().is_relative_to(DATA.resolve()) or not (workspace/'.experiment-copy').is_file():
        raise ValueError('workspace outside authorized experimental copies')
    current=snapshot(workspace)
    if archive.is_relative_to(delivery) or delivery.is_relative_to(archive):raise ValueError('archive and delivery must be disjoint')
    stage=archive/f'round-{round_no:02d}';stage.mkdir(parents=True,exist_ok=False,mode=0o700)
    save(stage/'task.json',spec);save(stage/'events.json',payload.get('events',[]));save(stage/'receipt.json',payload.get('receipt'))
    if delivery.exists():snapshot(delivery);shutil.copytree(delivery,stage/'delivery')
    shutil.copytree(workspace,stage/'workspace')
    ledger=os.environ.get('SSS_BUDGET_LEDGER')
    if ledger and private(ledger).is_file():shutil.copyfile(ledger,stage/'cost-ledger.jsonl')
    report_path=delivery/'report.json';report=json.loads(report_path.read_text()) if report_path.is_file() else None
    receipt=payload.get('receipt');receipt_ok=bool(isinstance(receipt,dict) and report and
        receipt.get('status') in ('delivered','delivered_with_gaps') and receipt.get('artifact_sha256')==digest(report)
        and receipt.get('input_sha256')==digest(spec) and Path(receipt.get('artifact','')).resolve()==report_path.resolve())
    verify=verify_report if spec.get('report_contract') else legacy_verify
    review=verify(spec,report if receipt_ok else None,delivery,payload.get('events',[]))
    if not receipt_ok and 'no actual submit_report receipt' not in review['errors']:review['errors'].append('no verified current submit_report receipt')
    if report and report.get('final_snapshot')!=current:review['errors'].append('published report snapshot differs from current workspace; publish current results again')
    review['passed']=not review['errors']
    repairable=True
    if spec.get('report_contract') and spec.get('role')=='benchmark':
        required=benchmark_targets(spec)
        read_paths={json.loads(p.read_text())['path'] for p in (delivery/'reads').glob('*.json')}
        if required and not read_paths<=required:repairable=False
    result={'version':'sss-file-acceptance-v1','round':round_no,'passed':review['passed'],'errors':review['errors'],
        'repairable':repairable,'receipt_verified':receipt_ok,'task_sha256':task_sha,'task_input_sha256':digest(spec),
        'workspace_snapshot_sha256':digest(current),'archive':str(stage),'human_blind_review':False}
    save(stage/'result.json',result)
    if snapshot(workspace)!=current:raise ValueError('workspace changed during read-only acceptance')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--task-file',type=Path,required=True);p.add_argument('--task-sha256',required=True)
    p.add_argument('--delivery-root',type=Path,required=True);p.add_argument('--archive-root',type=Path,required=True);p.add_argument('--round',type=int,required=True)
    a=p.parse_args()
    try:
        if not 0<=a.round<=2:raise ValueError('acceptance round limit')
        raw=sys.stdin.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:raise ValueError('acceptance events too large')
        print(json.dumps(check(a.task_file,a.task_sha256,a.delivery_root,a.archive_root,a.round,json.loads(raw)),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'fatal':True,'passed':False,'errors':['acceptance verifier '+type(exc).__name__+': '+str(exc)],'repairable':False}))
        return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
