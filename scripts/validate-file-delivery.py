"""Fixed read-only file acceptance and immutable per-round evidence archive."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import DATA,digest,save,snapshot
from report_study import verify_report,benchmark_targets
from operation_contract import verify_operations
from operation_contract_v2 import verify_operations_v2
from management_contract import verify_management
from verify import verify as legacy_verify
from task_contract import verify_task,scope_errors
from workflow_contract import verify_workflow

def private(path):
    p=Path(path)
    if p.is_symlink() or not p.resolve().is_relative_to((ROOT/'.local').resolve()):raise ValueError('private acceptance path outside scope')
    return p.resolve()

def recorded_crash_restart(spec,delivery,current):
    """Fixed frozen probe only; an unknown footprint never permits a cold retry."""
    if not spec.get('recovery_crash_after_publish') or spec.get('workflow_contract',{}).get('workflow_id')!='FM38':return False
    path=delivery/'plan-state.json'
    if not path.is_file():return False
    state=json.loads(path.read_text());unsigned={k:v for k,v in state.items() if k!='state_sha256'}
    from plan_tools import execution_version
    if state.get('state_sha256')!=digest(unsigned) or state.get('input_sha256')!=digest(spec) or state.get('execution_version_sha256')!=execution_version():return False
    live=[j for j in state['journals'].values() if j['status']=='executing' and current!=j['before'] and current in j.get('inflight_states',[])]
    return len(live)==1

def check(task_file,task_sha,delivery_root,archive_root,round_no,payload):
    task_file=private(task_file);delivery=private(delivery_root);archive=private(archive_root)
    if hashlib.sha256(task_file.read_bytes()).hexdigest()!=task_sha:raise ValueError('frozen task changed; permissions cannot widen')
    spec=json.loads(task_file.read_text());workspace=Path(spec['workspace'])
    management=spec.get('management_contract')=='sss-management-v3'
    # Daily web accounts have their own persistent copy root. Its location is
    # supplied by the trusted host environment, never by model/task arguments.
    account_home=private(os.environ.get('HARLESS_MANAGEMENT_PRIVATE_ROOT',ROOT/'.local'))
    if any(p.is_symlink() for p in (account_home,*account_home.parents)):
        raise ValueError('management account root redirected')
    valid_root=workspace.resolve().is_relative_to(DATA.resolve()) or management and workspace.resolve().is_relative_to(account_home/'management-copies')
    if workspace.is_symlink() or not valid_root or not (workspace/'.experiment-copy').is_file():
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
    verify=verify_operations_v2 if spec.get('operation_contract',{}).get('validation_version')=='sss-file-operation-quality-v2' else verify_operations if spec.get('operation_contract') else verify_workflow if spec.get('workflow_contract') else verify_task if spec.get('task_contract') else verify_report if spec.get('report_contract') else legacy_verify
    review=verify_management(spec,report if receipt_ok else {},delivery,events=payload.get('events',[])) if management else verify(spec,report if receipt_ok else None,delivery,payload.get('events',[]))
    if not receipt_ok and 'no actual submit_report receipt' not in review['errors']:review['errors'].append('no verified current submit_report receipt')
    if report and (report.get('final_tree',{}).get('workspace',{}).get('files') if management else report.get('final_snapshot'))!=current:review['errors'].append('published report snapshot differs from current workspace; publish current results again')
    review['passed']=not review['errors']
    repairable=True
    if spec.get('workflow_contract'):
        repairable=not any(error.startswith(('read outside','original read version')) for error in review['errors'])
        save(delivery/'workflow-manifest.json',review['manifest'])
        job=os.environ.get('FM_JOB_FILE')
        if job and private(job).is_file():shutil.copyfile(job,stage/'task-job-state.json')
    elif spec.get('task_contract'):
        scope,_=scope_errors(spec,delivery)
        if any(error.startswith(('read outside','original input read version')) for error in scope):repairable=False
    elif spec.get('report_contract') and spec.get('role')=='benchmark':
        required=benchmark_targets(spec)
        read_paths={json.loads(p.read_text())['path'] for p in (delivery/'reads').glob('*.json')}
        if required and not read_paths<=required:repairable=False
    result={'version':'sss-file-acceptance-v1','round':round_no,'passed':review['passed'],'errors':review['errors'],
        'repairable':repairable,'receipt_verified':receipt_ok,'task_sha256':task_sha,'task_input_sha256':digest(spec),
        'workspace_snapshot_sha256':digest(current),'archive':str(stage),'human_blind_review':False}
    if management:
        result['management_review']=review
        save(delivery/'acceptance.json',review)
    if not result['passed'] and recorded_crash_restart(spec,delivery,current):result['restart_required']=True
    if spec.get('workflow_contract'):result.update(workflow_contract_version=review['contract_version'],workflow_review=review)
    elif spec.get('task_contract'):result.update(task_contract_version=review['contract_version'],reading_scope=review)
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
