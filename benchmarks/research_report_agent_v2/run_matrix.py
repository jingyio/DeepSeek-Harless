"""Run an explicitly listed experiment matrix with one shared budget ledger.

The key is read once from stdin and inherited only by runner subprocesses.
No key is saved in commands, configuration, logs, or experiment artifacts.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix',type=Path,required=True)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--experiment',type=Path,required=True)
    p.add_argument('--budget-ledger',type=Path,required=True)
    p.add_argument('--workers',type=int,default=1,choices=(1,2,3))
    p.add_argument('--key-stdin',action='store_true')
    args=p.parse_args()
    jobs=json.loads(args.matrix.read_text(encoding='utf-8'))
    if not isinstance(jobs,list) or not jobs:raise ValueError('Nonempty explicit matrix required')
    names=[job.get('name') for job in jobs]
    if any(not isinstance(name,str) or not re.fullmatch(r'[a-z0-9_]{1,80}',name) for name in names) or len(set(names))!=len(names):
        raise ValueError('Run names must be unique scoped identifiers')
    api_key=sys.stdin.readline().strip() if args.key_stdin else os.environ.get('DEEPSEEK_API_KEY','')
    if not api_key:raise ValueError('A key is required')
    runner=Path(__file__).with_name('runner.py')
    args.experiment.mkdir(exist_ok=True,parents=True)
    log_dir=args.experiment/'execution-logs';log_dir.mkdir(exist_ok=True)
    for job in jobs:
        target=args.experiment/'runs'/job['name']
        if target.exists():raise ValueError('Refusing to overwrite a prior run: '+job['name'])
    def execute(job):
        started=time.time()
        out=args.experiment/'runs'/job['name']
        cmd=[sys.executable,str(runner),
             '--mode',job.get('mode','baseline'),'--out',str(out),'--budget-cny','100',
             '--experiment-id',args.experiment.name,
             '--budget-ledger',str(args.budget_ledger),'--max-output','6144','--max-requests','35','--call-model']
        if job.get('data'):
            cmd+=['--data',job['data'],'--request-file',job['request_file']]
            for option in ('study_json','outline_file'):
                if job.get(option):cmd+=['--'+option.replace('_','-'),job[option]]
        else:cmd+=['--data-root',str(args.data_root),'--case',job['case']]
        if job.get('library'):cmd+=['--library',job['library']]
        env=os.environ.copy();env['DEEPSEEK_API_KEY']=api_key
        env['PYTHONUTF8']='1';env['PYTHONIOENCODING']='utf-8'
        print(json.dumps({'event':'run_started','name':job['name'],'case':job.get('case','direct_user_input'),'mode':job.get('mode','baseline')},ensure_ascii=False),flush=True)
        with (log_dir/(job['name']+'.log')).open('w',encoding='utf-8') as log:
            completed=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
        row={'name':job['name'],'exit_code':completed.returncode,'elapsed_seconds':time.time()-started}
        if (out/'metrics.json').exists():
            metrics=json.loads((out/'metrics.json').read_text(encoding='utf-8'))
            row.update({k:metrics.get(k) for k in ('status','report_quality_passed','upstream_requests','tool_calls','verified_motif_bypasses','peak_estimate_cny')})
        print(json.dumps({'event':'run_finished',**row},ensure_ascii=False),flush=True)
        return row
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(execute,job) for job in jobs]
        for future in as_completed(futures):results.append(future.result())
    path=args.experiment/('matrix-result-'+args.matrix.stem+'.json')
    if path.exists():raise ValueError('Matrix result already exists')
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if all(r['exit_code']==0 and r.get('report_quality_passed') for r in results) else 2


if __name__=='__main__':raise SystemExit(main())
