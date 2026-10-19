#!/usr/bin/env python3
"""Post-task learning worker. No model calls, no writes to production libraries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.reuse_compiler import collect as collect_reuse, compile_library as compile_reuse

def read(path):return json.loads(path.read_text())
def save(path,value):
    temp=path.with_suffix('.'+uuid4().hex+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',type=Path,required=True);p.add_argument('--store',type=Path,required=True);p.add_argument('--user',required=True);a=p.parse_args()
    task=a.task.resolve(strict=True);store=a.store.resolve();store.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not task.is_relative_to(ROOT/'.local') or not store.is_relative_to(ROOT/'.local'):raise ValueError('private_learning_scope_required')
    state,effective=[read(task/name) for name in ['task-state.json','effective-config.json']]
    if any(row['user_id']!=a.user for row in [state,effective]) or state['status']!='completed' or state['mode']!='baseline' or effective['provider_mode']!='real':raise ValueError('completed_owner_baseline_required')
    # Optimized tasks may contain new native model-written work. Both compilers
    # exclude synthetic dispatch IDs; our own executions cannot certify a new
    # semantic choice. This is still explicit, private opt-in learning.
    with exclusive_lock(store/'learning.lock'):
        history=read(store/'history.json') if (store/'history.json').exists() else {'user':a.user,'tasks':[],'reset_history':False}
        if history['user']!=a.user:raise ValueError('foreign_learning_store')
        if str(task) not in history['tasks']:history['tasks'].append(str(task))
        save(store/'history.json',history)
        if len(history['tasks'])<2:
            save(task/'script-learning-status.json',{'status':'waiting_for_distinct_task_inputs'});return
        round_dir=store/('round-'+uuid4().hex)
        command=[sys.executable,str(ROOT/'scripts/learn-script-motifs.py'),*[x for t in history['tasks'] for x in ['--task',t]],'--output',str(round_dir)]
        started=__import__('time').monotonic()
        try:
            result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=300)
        except subprocess.TimeoutExpired:
            save(task/'script-learning-status.json',{'status':'failed','reason':'compilation_timeout','round':round_dir.name});return
        save(round_dir/'worker.json',{'exit_code':result.returncode,'stdout':result.stdout[-16000:],'stderr':result.stderr[-4000:]})
        if result.returncode:save(task/'script-learning-status.json',{'status':'failed','round':round_dir.name});return
        library=read(round_dir/'library.json')
        reuse=compile_reuse([r for t in history['tasks'] for r in collect_reuse(Path(t))],ROOT)
        save(round_dir/'reuse-library.json',reuse)
        published=bool(library['programs'] or reuse['contracts'])
        status={'status':'published' if published else 'no_qualified_programs','round':round_dir.name,'programs':len(library['programs']),'digest':library['digest'],
                'reuse_contracts':len(reuse['contracts']),'reuse_digest':reuse['digest'],'compilation_model_requests':0,'elapsed_seconds':__import__('time').monotonic()-started}
        if published:save(store/'latest.json',{'file':str((round_dir/'library.json').relative_to(store)),'digest':library['digest'],'user':a.user,
                                             'reuse_file':str((round_dir/'reuse-library.json').relative_to(store)),'reuse_digest':reuse['digest']})
        save(task/'script-learning-status.json',status)
if __name__=='__main__':main()
