#!/usr/bin/env python3
"""Private post-task compilation, with opt-in description and Negative RSI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import re
import time
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.probe_motif_compiler import collect as collect_probes
from src.adapters.reuse_compiler import collect as collect_reuse, compile_library as compile_reuse
from src.adapters.script_description_learning import learn_descriptions, retain_previous_descriptions, save
from src.adapters.script_negative_learning import learn_negatives, certify_library
from src.adapters.script_motif_compiler import digest

def read(path):return json.loads(path.read_text())

def parent_library(store,parent,key,filename):
    name=parent.get(key,'')
    if not isinstance(name,str) or not re.fullmatch(r'round-[a-f0-9]+/'+re.escape(filename),name):raise ValueError('invalid_learning_parent_path')
    path=store/name
    if path.resolve()!=path:raise ValueError('learning_parent_symlink')
    library=read(path)
    digest_key={'file':'digest','reuse_file':'reuse_digest','negative_file':'negative_digest'}[key]
    if library.get('digest')!=parent.get(digest_key) or digest({k:v for k,v in library.items() if k!='digest'})!=library['digest']:raise ValueError('learning_parent_digest_changed')
    return library,path

def compile_positive(history,store,output,parent):
    command=[sys.executable,str(ROOT/'scripts/learn-script-motifs.py'),*[x for t in history for x in ['--task',t]],'--output',str(output)]
    try:result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=300)
    except subprocess.TimeoutExpired:return None,None,{'status':'failed','reason':'compilation_timeout','model_requests':0}
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    save(output/'worker.json',{'exit_code':result.returncode,'stdout':result.stdout[-16000:],'stderr':result.stderr[-4000:]})
    if result.returncode:return None,None,{'status':'failed','reason':'structural_compilation_failed','model_requests':0}
    library=read(output/'library.json')
    if (store/'description-learning.json').exists():save(output/'description-base-library.json',library)
    library,status=learn_descriptions(library,store,output)
    if (store/'description-learning.json').exists() and parent and parent.get('file'):
        previous,path=parent_library(store,parent,'file','library.json')
        metadata=path.parent/'description-learning.json'
        library,status=retain_previous_descriptions(library,status,previous,read(metadata) if metadata.exists() else {})
        save(output/'description-learning.json',status)
    save(output/'library.json',library)
    reuse=compile_reuse([r for t in history for r in collect_reuse(Path(t))],ROOT,[r for t in history for r in collect_probes(Path(t))])
    save(output/'reuse-library.json',reuse)
    return library,reuse,status

def history_for(store,name,user,task):
    path=store/name
    history=read(path) if path.exists() else {'user':user,'tasks':[],'reset_history':False}
    if history['user']!=user:raise ValueError('foreign_learning_store')
    if task and str(task) not in history['tasks']:history['tasks'].append(str(task))
    save(path,history)
    return history['tasks']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',type=Path,required=True);p.add_argument('--store',type=Path,required=True);p.add_argument('--user',required=True);a=p.parse_args()
    task=a.task.resolve(strict=True);store=a.store.resolve();store.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not task.is_relative_to(ROOT/'.local') or not store.is_relative_to(ROOT/'.local'):raise ValueError('private_learning_scope_required')
    state,effective=[read(task/name) for name in ['task-state.json','effective-config.json']]
    negative_enabled=(store/'negative-learning.json').exists()
    completed=state['status']=='completed'
    if (any(row['user_id']!=a.user for row in [state,effective]) or state['mode']!='baseline' or effective['provider_mode']!='real'
            or not completed and not (negative_enabled and state['status'] in ('failed','cancelled'))):
        raise ValueError('settled_owner_baseline_required')
    with exclusive_lock(store/'learning.lock'):
        history=history_for(store,'history.json',a.user,task if completed else None)
        negative_history=history_for(store,'negative-history.json',a.user,task) if negative_enabled else []
        if len(history)<2 and not negative_enabled:
            save(task/'script-learning-status.json',{'status':'waiting_for_distinct_task_inputs'});return
        parent=read(store/'latest.json') if (store/'latest.json').exists() else None
        if parent and parent.get('user')!=a.user:raise ValueError('foreign_learning_store')
        output=store/('round-'+uuid4().hex);started=time.monotonic()
        library,reuse,description=None,None,{'status':'not_run','model_requests':0}
        if completed and len(history)>=2:
            library,reuse,description=compile_positive(history,store,output,parent)
        output.mkdir(parents=True,exist_ok=True,mode=0o700)
        negative,negative_status=learn_negatives(negative_history,store,output,ROOT,a.user)
        save(output/'negative-learning.json',negative_status)
        assets={}
        if library and (library['programs'] or reuse['contracts']):
            assets.update(file=('library.json',library),reuse_file=('reuse-library.json',reuse))
        if negative:assets['negative_file']=('negative-library.json',negative)
        # Rejected review cannot erase an already reviewed library. Copy to the
        # same generation after checking digest, source locks and authority.
        inherited=[];rejected_parent=[]
        if negative_enabled and parent:
            for key,filename in [('file','library.json'),('reuse_file','reuse-library.json'),('negative_file','negative-library.json')]:
                if key in assets or not parent.get(key):continue
                try:
                    old,_=parent_library(store,parent,key,filename)
                    locks=old.get('runtime_locks',{})|old.get('implementation_locks',{})|old.get('code_locks',{})
                    if any(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()!=v for k,v in locks.items()):raise ValueError('parent_implementation_changed')
                    if key=='negative_file':
                        if any(r['retry_policy']!='prompt_only' for r in old['rules']):raise ValueError('automatic_negative_authority_denied')
                        save(output/filename,old);certify_library(output/filename,ROOT)
                    assets[key]=(filename,old);inherited.append(key)
                except (ValueError,OSError,KeyError):rejected_parent.append(key)
        published=bool(assets)
        status={'status':'published' if published else 'failed' if description['status']=='failed' or negative_status['status']=='failed' else 'no_qualified_programs',
                'round':output.name,'programs':len(library['programs']) if library else 0,'digest':library['digest'] if library else None,
                'reuse_contracts':len(reuse['contracts']) if reuse else 0,'reuse_digest':reuse['digest'] if reuse else None,
                'negative_rules':len(assets['negative_file'][1]['rules']) if 'negative_file' in assets else 0,
                'negative_digest':assets.get('negative_file',('',{}))[1].get('digest'),
                'compilation_model_requests':description['model_requests']+negative_status['model_requests'],
                'description_learning':description,'negative_learning':negative_status,'inherited_assets':inherited,'rejected_parent_assets':rejected_parent,
                'elapsed_seconds':time.monotonic()-started,'triggered_by_task':task.name,'parent_digest':parent.get('digest') if parent else None,
                'heldout_task_id':library['heldout_task_id'] if library else None,'training_task_ids':[Path(t).name for t in history[1:]]}
        evidence=list(dict.fromkeys(history+negative_history))
        save(output/'lineage.json',{**status,'evidence':[{'task_id':Path(t).name,'events_sha256':hashlib.sha256((Path(t)/'events.jsonl').read_bytes()).hexdigest()} for t in evidence]})
        if published:
            pointer={'user':a.user,'triggered_by_task':task.name,'parent_digest':status['parent_digest'],
                     'parent_negative_digest':parent.get('negative_digest') if parent else None}
            for key,(filename,value) in assets.items():
                save(output/filename,value)
                pointer[key]=str((output/filename).relative_to(store))
                pointer[{'file':'digest','reuse_file':'reuse_digest','negative_file':'negative_digest'}[key]]=value['digest']
            save(store/'latest.json',pointer)
        save(task/'script-learning-status.json',status)
if __name__=='__main__':main()
