"""Sequential authorized experiment stages; stop on errors/quality gate, retain every subprocess log."""
import argparse,hashlib,json,subprocess,sys,shutil
from uuid import uuid4
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--from-stage');a=p.parse_args();exp=a.experiment.resolve()
    stages=[('bootstrap',['scenarios/file-management/report_study.py','--role','bootstrap','--call-model']),('bootstrap-certify',['scenarios/file-management/report_study.py','--role','bootstrap_certify','--call-model']),
        ('learn-l1',['scenarios/file-management/report_study.py','--learn-l1']),
        ('new-l1-experience',['scenarios/file-management/report_study.py','--role','learn','--call-model']),
        ('independent-l2-certification',['scenarios/file-management/report_study.py','--role','certify','--call-model']),
        ('learn-l2',['scenarios/file-management/report_study.py','--learn-l2']),
        ('sdk-H',['scripts/check-report-sdk.py','--arm','H']),('sdk-L1',['scripts/check-report-sdk.py','--arm','L1']),
        ('sdk-L2',['scripts/check-report-sdk.py','--arm','L2']),('sdk-L2-stale',['scripts/check-report-sdk.py','--arm','L2','--stale']),
        ('pre-holdout-audit',['scripts/audit-report-study.py']),
        ('new-quality-holdout',['scenarios/file-management/report_study.py','--role','quality','--call-model']),
        ('quality-audit',['scripts/audit-report-study.py']),
        ('full-benchmark',['scenarios/file-management/report_study.py','--role','benchmark','--call-model']),
        ('summary',['scenarios/file-management/report_study.py','--summary']),('final-audit',['scripts/audit-report-study.py'])]
    if a.from_stage:
        index=next(i for i,(label,args) in enumerate(stages) if label==a.from_stage);stages=stages[index:]
    prior=exp/'pipeline-state.json';prior_hash=None
    if prior.exists():
        prior_hash=hashlib.sha256(prior.read_bytes()).hexdigest();archive=exp/('pipeline-state-before-resume-'+uuid4().hex+'.json');shutil.copyfile(prior,archive);archive.chmod(0o600)
    folder=exp/'pipeline-stages';folder.mkdir(exist_ok=True,mode=0o700);record={'orchestrator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'previous_state_sha256':prior_hash,'from_stage':a.from_stage,'stages':[]}
    for label,args in stages:
        print(json.dumps({'pipeline_start':label}),flush=True);log=folder/(label+'.txt')
        with log.open('x') as f:
            log.chmod(0o600);result=subprocess.run([sys.executable,*args,'--experiment',str(exp)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        record['stages'].append({'name':label,'returncode':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
        path=exp/'pipeline-state.json';path.write_text(json.dumps(record,indent=2));path.chmod(0o600)
        print(json.dumps({'pipeline_finished':label,'returncode':result.returncode}),flush=True)
        if result.returncode:raise SystemExit(result.returncode)
if __name__=='__main__':main()
