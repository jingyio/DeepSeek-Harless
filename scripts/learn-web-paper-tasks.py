#!/usr/bin/env python3
"""Use existing owned Web tasks to compile the next private Paper read release.

No model requests, tool execution, user source copies or second trajectory store.
The original Baseline files, settled receipts and ordinary compiler remain the
only learning inputs. The first qualifying decision is permanently held out.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.harless_rsi_bundle import load_product_bundle
spec = importlib.util.spec_from_file_location('paper_learning', ROOT/'scripts/learn-web-paper-document-motif.py')
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path, value):
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.chmod(0o600);temporary.replace(path)
def file(parent, path):
    path=Path(path)
    if path.is_symlink() or path.resolve(strict=True)!=path.absolute() or not path.resolve().is_relative_to(parent) or not path.is_file():
        raise ValueError('learning input escapes owning output')
    return path


def advance(request_path):
    request_path=Path(request_path).absolute();request=read(request_path)
    output=Path(request['output']).resolve(strict=True);store=request_path.parent
    if (not output.is_relative_to((ROOT/'.local').resolve()) or not store.is_relative_to(output)
            or request_path.is_symlink() or store.resolve()!=store or request.get('schema_version')!=1
            or not isinstance(request.get('user'),str) or not isinstance(request.get('scope'),str)
            or not re.fullmatch('[a-f0-9]{64}',request['scope'])):
        raise ValueError('invalid owning learning request')
    expected=hashlib.sha256((request['user']+'\0'+request['scope']).encode()).hexdigest()
    if store!=output/'learning'/expected:raise ValueError('learning store identity mismatch')
    task_ids=request.get('task_ids')
    if not isinstance(task_ids,list) or any(not isinstance(x,str) or not re.fullmatch('[a-f0-9]{32}',x) for x in task_ids):
        raise ValueError('invalid existing task index')
    with exclusive_lock(store/'.lock'):
        candidates=[];excluded=[];seen_questions=set();seen_sources=set()
        contracts=compiler.parse_tool_contracts(compiler.read(compiler.CONTRACTS))
        allowed=compiler.read(compiler.SCENE/'scenario.json')['allowed_tools']
        for identity in dict.fromkeys(task_ids):
            task=output/'tasks'/identity
            try:
                state,effective,req=[read(file(output,task/name)) for name in ('task-state.json','effective-config.json','task.json')]
                if state.get('user_id')!=request['user'] or effective.get('user_id')!=request['user']:
                    raise ValueError('foreign task')
                if any(row.get('task_id')!=identity for row in (state,effective,req)) or state.get('session_id')!=req.get('session_id'):
                    raise ValueError('task identity changed')
                if state.get('scene')!='paper-proofreading' or state.get('mode')!='baseline' or state.get('status')!='completed':continue
                if effective.get('provider_mode')!='real' or effective.get('mode')!='baseline' or req.get('mode')!='baseline':continue
                if state.get('failure') or state.get('stats',{}).get('verified_skips',0):raise ValueError('non-native training')
                accounting=read(file(output,task/'learning-accounting.json'))
                if accounting.get('task_id')!=identity or accounting.get('session_id')!=read(file(output,task/'budget-route.json')).get('budget_session_id'):
                    raise ValueError('accounting identity mismatch')
                compiler.reconcile(state,req,accounting['request_receipts'],qualifying=True)
                for name in ['events.jsonl','answer.md']:file(output,task/name)
                review=compiler.structural_review(task,req,contracts)
                if not review['observed_parameter_edge_present']:raise ValueError('no_original_read_edge')
                tools=compiler.native_schemas(effective['tools']);schemas=[row for row in tools if row['name'] in allowed]
                if len(schemas)!=len(allowed):raise ValueError('incomplete_scene_schema')
                question=' '.join(part['text'] for part in req['content'] if part['type']=='text').casefold().split()
                question=' '.join(question)
                # Same conversation/source decision and exact paraphrase-free
                # repeats cannot become an independent held-out witness.
                source=state.get('source_task_id',identity)
                if question in seen_questions or source in seen_sources:continue
                seen_questions.add(question);seen_sources.add(source)
                candidates.append({'task_dir':str(task),'decision_id':'web-'+source,'task_id':identity,'schemas':schemas,
                    'accounting':accounting['request_receipts'],'events_sha256':sha(task/'events.jsonl')})
            except (ValueError,KeyError,OSError,TypeError) as error:
                excluded.append({'task_id':identity,'reason':str(error)[:160]})
        if len(candidates)<3:
            save(store/'status.json',{'status':'waiting_for_evidence','eligible_tasks':len(candidates),'minimum_tasks':3,'excluded':excluded});return
        # Keep the held-out decision reserved; select the latest two compatible
        # training decisions, never an Execute result or the held-out itself.
        pointer_path=store/'latest.json';pointer=read(pointer_path) if pointer_path.exists() else None
        reserved=pointer.get('heldout_task_id') if pointer else None
        holdout=next((row for row in candidates if row['task_id']==reserved),None) if reserved else candidates[0]
        if holdout is None:
            save(store/'status.json',{'status':'waiting_for_reserved_holdout','excluded':excluded});return
        training=[row for row in candidates if row is not holdout and row['schemas']==holdout['schemas']][-2:]
        if len(training)<2:
            save(store/'status.json',{'status':'waiting_for_compatible_schema','excluded':excluded});return
        selected=[*training,holdout]
        signature=compiler.digest({'traces':[(r['task_id'],r['events_sha256'],compiler.digest(r['schemas'])) for r in selected],
            'code':[(str(path.relative_to(ROOT)),sha(path)) for path in compiler.code_paths()]})
        if pointer and pointer.get('evidence_signature')==signature:
            save(store/'status.json',{'status':'unchanged','round':pointer['round'],'eligible_tasks':len(candidates)});return
        index=(int(pointer['round'].split('-')[1])+1) if pointer else 1
        folder=store/f'round-{index:04d}'
        # Failed/incomplete rounds are evidence too; do not overwrite them.
        while folder.exists():index+=1;folder=store/f'round-{index:04d}'
        folder.mkdir(mode=0o700)
        dataset={'train':[{k:r[k] for k in ('task_dir','decision_id')} for r in training],
                 'heldout':[{k:holdout[k] for k in ('task_dir','decision_id')}], 'ledger':str(folder/'ledger.json')}
        save(folder/'dataset.json',dataset);save(folder/'schemas.json',holdout['schemas'])
        save(folder/'ledger.json',[row for item in selected for row in item['accounting']])
        save(store/'status.json',{'status':'compiling','round':folder.name,'excluded':excluded})
        compiler.main(['--dataset',str(folder/'dataset.json'),'--schemas',str(folder/'schemas.json'),
            '--out',str(folder/'compile'),'--publish',str(folder/'release')],private_publish_root=store,reuse_task_files=True)
        runtime=load_product_bundle(ROOT,folder/'release','paper-proofreading',private_root=store)
        save(folder/'admission.json',{'user':request['user'],'scope':request['scope'],'runtime':runtime})
        # Publish last: old readers retain their byte-bound immutable release.
        save(pointer_path,{'schema_version':1,'user':request['user'],'scope':request['scope'],
            'round':folder.name,'heldout_task_id':holdout['task_id'],'admission_sha256':sha(folder/'admission.json'),'evidence_signature':signature})
        save(store/'status.json',{'status':'published','round':folder.name,'eligible_tasks':len(candidates),
            'change_scope':'new_independent_evidence_not_claimed_coverage_or_cost_gain','compilation_model_requests':0,'excluded':excluded})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',type=Path,required=True)
    advance(parser.parse_args().request)
