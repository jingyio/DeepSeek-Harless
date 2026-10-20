#!/usr/bin/env python3
"""PPT 用户轨迹闭环：账户内原始任务→独立认证→两项后续对照→晋级/停用。

后台只调用现有离线编译器，不调用模型、不重跑任务、不复制用户来源。
结构证书和质量/费用晋级分别保存；原始失败及被拒候选均保留。
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import subprocess
import time
from uuid import uuid4
import zipfile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.harless_rsi_bundle import load_product_bundle
spec=importlib.util.spec_from_file_location('ppt_master_compiler',ROOT/'scripts/learn-ppt-master-motif.py')
compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
SHA=re.compile(r'[a-f0-9]{64}')
TASK=re.compile(r'[a-f0-9]{32}')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def save(path,value):
    temp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');temp.chmod(0o600);temp.replace(path)
def file(parent,path):
    path=Path(path)
    if path.is_symlink() or path.absolute()!=path.resolve(strict=True) or not path.is_relative_to(parent) or not path.is_file() or path.stat().st_nlink!=1:
        raise ValueError('learning path escapes owning output')
    return path
def finite(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


def delivery(output,turn,lane,locks):
    """Verify actual immutable download bytes, not the model's success claim."""
    row=turn['lanes'][lane]
    if row.get('status')!='completed' or not SHA.fullmatch(row.get('output_sha256','')):raise ValueError('delivery not completed')
    files={}
    for artifact in row.get('artifacts',[]):
        if not re.fullmatch(r'[a-f0-9]{32}-[0-9]+',artifact.get('id','')) or type(artifact.get('attempt')) is not int:
            raise ValueError('invalid immutable artifact identity')
        path=file(output,output/'comparison-artifacts'/turn['id']/lane/str(artifact['attempt'])/artifact['id'])
        if sha(path)!=artifact.get('sha256') or path.stat().st_size!=artifact.get('bytes'):raise ValueError('delivery bytes changed')
        locks[path.relative_to(output).as_posix()]=sha(path)
        files.setdefault(Path(artifact['name']).suffix.lower(),[]).append(path)
    if not all(files.get(ext) for ext in ('.pptx','.pdf','.png')):raise ValueError('PPTX/PDF/PNG delivery missing')
    import fitz
    with zipfile.ZipFile(files['.pptx'][-1]) as archive:
        slides=[name for name in archive.namelist() if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml',name)]
        notes=[name for name in archive.namelist() if re.fullmatch(r'ppt/notesSlides/notesSlide[0-9]+\.xml',name)]
        if not slides or len(notes)<len(slides):raise ValueError('slides or speaker notes missing')
        if not any(ET.fromstring(archive.read(name)).find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t') is not None for name in slides):
            raise ValueError('editable text missing')
        with fitz.open(stream=files['.pdf'][-1].read_bytes(),filetype='pdf') as pdf:
            if pdf.page_count!=len(slides):raise ValueError('rendered page count differs')
    if any(not path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for path in files['.png']):raise ValueError('invalid PNG preview')
    return {ext:len(paths) for ext,paths in files.items()}


def reviews(output,store,request,turns):
    path=store/'reviews.jsonl';latest={}
    if not path.exists():return latest
    for line in file(output,path).read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        if row.get('user')!=request['user'] or row.get('scope')!=request['scope']:raise ValueError('foreign review')
        turn=turns.get(row.get('comparison_id'));lane=row.get('lane')
        if not turn or lane not in ('baseline','motif') or row.get('output_sha256')!=turn['lanes'][lane].get('output_sha256'):continue
        latest[(turn['id'],lane)]=row
    return latest


def positive(review,turn,lane):
    # Service-level account-local learning is enabled by the operator. Optional
    # reviews/ordinary downvotes can veto it; no questionnaire is required.
    if turn['lanes'][lane].get('feedback')=='down':return False
    if review is None:return True
    return bool(review.get('allow_learning') is True and
        review.get('quality')=={'scientific':True,'visual':True,'usable':True} and
        finite(review.get('human_minutes')) and turn['lanes'][lane].get('feedback')!='down')


def task_info(output,identity,request,*,baseline=False):
    if not TASK.fullmatch(identity):raise ValueError('invalid task identity')
    task=output/'tasks'/identity
    names=['task-state.json','effective-config.json','task.json','budget-route.json','learning-accounting.json','events.jsonl','answer.md']
    locks={file(output,task/name).relative_to(output).as_posix():sha(task/name) for name in names}
    state,effective,req,route,accounting=[read(task/name) for name in names[:5]]
    if any(row.get('task_id')!=identity for row in (state,effective,req,accounting)) or any(row.get('user_id')!=request['user'] for row in (state,effective)):
        raise ValueError('task ownership or identity changed')
    if (state.get('scene')!='ppt' or effective.get('provider_mode')!='real' or effective.get('ppt_execution_strategy')!='ppt_master' or
        state.get('session_id')!=req.get('session_id') or accounting.get('session_id')!=route.get('budget_session_id')):
        raise ValueError('not an owned real ppt-master task')
    if baseline and (any(row.get('mode')!='baseline' for row in (state,effective,req)) or state.get('status')!='completed' or state.get('failure') or state.get('stats',{}).get('verified_skips',0)):
        raise ValueError('training requires a successful original Baseline')
    totals=compiler.accounting.reconcile(state,req,accounting['request_receipts'],qualifying=baseline)
    if (not totals['usage_complete'] or not finite(totals['proxy_peak_usd']) or
        any(type(v) is not int or v<0 for v in totals['tokens'].values())):raise ValueError('unsettled accounting')
    schemas=compiler.accounting.native_schemas(effective['tools'])
    sources=sorted(row.get('version_sha256','') for row in state.get('scene_inputs',[]))
    if not sources or any(not SHA.fullmatch(v) for v in sources):raise ValueError('missing frozen source versions')
    question=' '.join(' '.join(p['text'] for p in req['content'] if p.get('type')=='text').casefold().split())
    decision=state.get('source_task_id') or state['session_id']
    return {'task_id':identity,'task_dir':str(task),'state':state,'effective':effective,'request':req,'schemas':schemas,'totals':totals,'locks':locks,
        'decision_id':'web-'+decision,'source_signature':digest(sources),'question_sha256':digest(question),
        'compatibility':digest({'tools':schemas,'model':effective.get('model'),'provider':effective.get('provider'),
            'reasoning':effective.get('reasoning_effort'),'skill':effective.get('skill_package_sha256'),
            'instructions':effective.get('instructions_sha256'),'compression':effective.get('compression')})}


def validate_admission(output,store,pointer,request):
    if not re.fullmatch(r'round-[0-9]{4,}',pointer.get('round','')):raise ValueError('invalid candidate pointer')
    folder=store/pointer['round'];path=file(output,folder/'admission.json')
    if sha(path)!=pointer.get('admission_sha256'):raise ValueError('candidate admission changed')
    admission=read(path)
    if admission.get('user')!=request['user'] or admission.get('scope')!=request['scope']:raise ValueError('foreign candidate')
    for name,version in admission['evidence_locks'].items():
        if sha(file(output,output/name))!=version:raise ValueError('candidate evidence changed')
    load_product_bundle(ROOT,folder/'release','ppt',private_root=store)
    return folder,admission


def evaluate(output,store,pointer,request,turns,reviewed,infos):
    folder,admission=validate_admission(output,store,pointer,request)
    support=admission['support'];pairs=[];blocked=[];seen={key:set() for key in support}
    for turn in turns.values():
        if turn.get('scene')!='ppt' or turn.get('presentation')=='single':continue
        if turn.get('status') not in ('completed','failed','cancelled'):continue
        motif=turn['lanes']['motif'];identity=motif.get('task_id')
        info=infos.get(identity)
        if not info:
            # An incomplete, paid candidate run must not disappear from the
            # decision merely because receipt/delivery validation excluded it.
            if identity and TASK.fullmatch(identity):
                effective=read(file(output,output/'tasks'/identity/'effective-config.json'))
                if effective.get('learning_version')==pointer['round'] and motif.get('status') in ('completed','failed','cancelled'):
                    blocked.append({'id':turn['id'],'reason':'candidate_accounting_incomplete'})
            continue
        if info['effective'].get('learning_version')!=pointer['round']:continue
        if motif.get('status') not in ('completed','failed','cancelled'):continue
        if info['effective'].get('library_sha256')!=admission['runtime']['runtime_library_sha256']:raise ValueError('candidate execution library differs')
        base_review=reviewed.get((turn['id'],'baseline'));opt_review=reviewed.get((turn['id'],'motif'))
        if motif.get('feedback')=='down' or (opt_review and not positive(opt_review,turn,'motif')):
            blocked.append({'id':turn['id'],'reason':'negative_or_withdrawn_review'});continue
        if not all(positive(review,turn,lane) for lane,review in [('baseline',base_review),('motif',opt_review)]):continue
        base=infos.get(turn['lanes']['baseline'].get('task_id'))
        if not base:raise ValueError('baseline accounting missing')
        if (base['compatibility']!=info['compatibility'] or base['effective'].get('mode')!='baseline' or info['effective'].get('mode')!='execute' or
            base['state'].get('status')!='completed' or info['state'].get('status')!='completed' or motif.get('fallback_reason') or
            base['question_sha256']!=info['question_sha256'] or base['source_signature']!=info['source_signature']):
            blocked.append({'id':turn['id'],'reason':'non_matching_comparison'});continue
        if any(base[key] in support[key] for key in ('decision_id','source_signature','question_sha256')):continue
        if any(base[key] in seen[key] for key in seen):continue
        for key in seen:seen[key].add(base[key])
        locks={**base['locks'],**info['locks']}
        delivery(output,turn,'baseline',locks);delivery(output,turn,'motif',locks)
        # Every prior paid attempt belongs to this comparison's full cost.
        attempts={}
        for lane in ('baseline','motif'):
            expected={'compare-'+hashlib.sha256(json.dumps([turn['id'],lane,i],separators=(',',':')).encode()).hexdigest()[:48] for i in range(turn['lanes'][lane]['attempt']+1)}
            runs=[item for item in infos.values() if item['request'].get('request_id') in expected]
            if {item['request'].get('request_id') for item in runs}!=expected:raise ValueError('retry accounting incomplete')
            for item in runs:locks.update(item['locks'])
            attempts[lane]={'requests':sum(item['totals']['requests'] for item in runs),'proxy_usd':sum(item['totals']['proxy_peak_usd'] for item in runs),
                'tokens':sum(item['totals']['tokens']['total_tokens'] for item in runs),'attempts':len(runs)}
        bypass=info['state'].get('stats',{}).get('verified_skips',0)
        audit=file(output,Path(info['task_dir'])/'motif-audit.jsonl')
        rows=[json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines() if line.strip()]
        if type(bypass) is not int or bypass<1 or not any(row.get('kind')=='model_request_skipped_verified' for row in rows):
            blocked.append({'id':turn['id'],'reason':'no_verified_candidate_execution'});continue
        locks[audit.relative_to(output).as_posix()]=sha(audit)
        human_reviewed=base_review is not None and opt_review is not None
        good=attempts['motif']['proxy_usd']<attempts['baseline']['proxy_usd'] and (not human_reviewed or opt_review['human_minutes']<=base_review['human_minutes'])
        pairs.append({'comparison_id':turn['id'],'baseline':attempts['baseline'],'motif':attempts['motif'],
            'baseline_human_minutes':base_review['human_minutes'] if base_review else None,'motif_human_minutes':opt_review['human_minutes'] if opt_review else None,
            'verified_skips':bypass,'mechanical_quality_passed':True,'scientific_quality_reviewed':human_reviewed,'cost_passed':good,'evidence_locks':locks,
            'review_ids':[review['id'] for review in (base_review,opt_review) if review]})
        if not good:blocked.append({'id':turn['id'],'reason':'cost_or_human_revision_regression'})
    return folder,admission,pairs,blocked


def advance(request_path):
    started=time.monotonic();request_path=Path(request_path).absolute();request=read(request_path)
    output=Path(request['output']).resolve(strict=True);store=request_path.parent
    if (request.get('schema_version')!=1 or not isinstance(request.get('user'),str) or not SHA.fullmatch(request.get('scope','')) or
        not output.is_relative_to((ROOT/'.local').resolve()) or store.resolve()!=store or request_path.is_symlink() or
        store!=output/'learning'/('ppt-'+hashlib.sha256((request['user']+'\0'+request['scope']).encode()).hexdigest())):
        raise ValueError('invalid owning PPT learning request')
    ids=request.get('task_ids')
    if not isinstance(ids,list) or any(not isinstance(v,str) or not TASK.fullmatch(v) for v in ids):raise ValueError('invalid owned task index')
    with exclusive_lock(store/'.lock'):
        report={'schema_version':1,'compilation_model_requests':0,'extra_provider_requests':0,'actual_paid_usd':None,'cpu_cost_usd':None}
        def status(value):save(store/'status.json',{**report,**value,'worker_seconds':time.monotonic()-started})
        feedback_path=store/'feedback-version.json'
        def current_feedback():return sha(file(output,feedback_path)) if feedback_path.exists() else None
        feedback_version=current_feedback()
        def resume():
            if current_feedback()==feedback_version:(store/'suspended.json').unlink(missing_ok=True)
        comparison_path=output/'comparisons.json'
        if request.get('automatic_structural_learning') is not True:
            status({'status':'disabled_by_operator'});return
        if not comparison_path.exists():status({'status':'waiting_for_eligible_tasks','eligible_tasks':0});return
        comparisons=read(file(output,comparison_path))
        if comparisons.get('principal')!=request['user']:raise ValueError('foreign comparison store')
        turns={turn['id']:turn for turn in comparisons['turns'] if turn.get('scene')=='ppt'}
        reviewed=reviews(output,store,request,turns);infos={};excluded=[]
        for identity in dict.fromkeys(ids):
            try:infos[identity]=task_info(output,identity,request)
            except (ValueError,KeyError,OSError,TypeError) as error:excluded.append({'task_id':identity,'reason':str(error)[:160]})
        selected_path=store/'selected.json';candidate_path=store/'candidate.json'
        candidate=read(candidate_path) if candidate_path.exists() else None
        if candidate:
            candidate={**candidate,'feedback_version':feedback_version}
            try:
                folder,admission,pairs,blocked=evaluate(output,store,candidate,request,turns,reviewed,infos)
                # Withdrawal or negative feedback on training/heldout evidence
                # also revokes the candidate. A structural certificate is insufficient.
                for ref in admission['support_reviews']:
                    turn=turns.get(ref['comparison_id']);review=reviewed.get((ref['comparison_id'],'baseline'))
                    if not turn or not positive(review,turn,'baseline') or ref['review_id'] is not None and (not review or review['id']!=ref['review_id']):
                        blocked.append({'id':ref['comparison_id'],'reason':'support_review_changed'})
                quality_promoted=len(pairs)>=2 and not blocked and all(pair['scientific_quality_reviewed'] for pair in pairs)
                save(folder/'evaluation.json',{'pairs':pairs,'blocked':blocked,'required_independent_pairs':2,'quality_cost_promoted':quality_promoted,
                    'mechanical_cost_promoted':len(pairs)>=2 and not blocked,'quality_scope':'mechanical_delivery_and_guarded_structure; scientific quality unknown unless explicitly reviewed'})
                if blocked:
                    save(selected_path,{**candidate,'phase':'disabled','reason':blocked[0]['reason']})
                    save(folder/'retired.json',{'reason':blocked[0]['reason'],'blocked':blocked});candidate_path.unlink()
                    status({'status':'disabled','round':candidate['round'],'blocked':blocked});return
                if len(pairs)>=2:
                    save(folder/'promotion.json',{'schema_version':1,'round':candidate['round'],'evaluation_sha256':sha(folder/'evaluation.json'),
                        'evidence_locks':{name:version for pair in pairs for name,version in pair['evidence_locks'].items()},'review_ids':[v for pair in pairs for v in pair['review_ids']]})
                    save(selected_path,{**candidate,'phase':'active','quality_cost_promoted':quality_promoted,'mechanical_cost_promoted':True,'promotion_sha256':sha(folder/'promotion.json')})
                    resume()
                    status({'status':'active','round':candidate['round'],'independent_evaluations':len(pairs),
                        'observed_proxy_savings_usd':sum(p['baseline']['proxy_usd']-p['motif']['proxy_usd'] for p in pairs),
                        'quality_cost_promoted':quality_promoted,'mechanical_cost_promoted':True,'scope':'these_tasks_guarded_structure_and_mechanical_delivery_only','excluded':excluded});return
                phase='probation'
                save(selected_path,{**candidate,'phase':phase,'quality_cost_promoted':False});resume()
                status({'status':phase,'round':candidate['round'],'independent_evaluations':len(pairs),'required_independent_pairs':2,'excluded':excluded});return
            except (ValueError,KeyError,OSError,TypeError) as error:
                save(selected_path,{**candidate,'phase':'disabled','reason':'candidate_evidence_invalid'})
                # Never use an invalid pointer as a write path during recovery.
                if isinstance(candidate.get('round'),str) and re.fullmatch(r'round-[0-9]{4,}',candidate['round']):
                    folder=store/candidate['round']
                    if folder.is_dir() and folder.resolve()==folder:save(folder/'retired.json',{'reason':str(error)[:160]})
                candidate_path.unlink()
                status({'status':'disabled','round':candidate['round'],'reason':str(error)[:160]});return
        candidates=[];seen={key:set() for key in ('decision_id','source_signature','question_sha256')}
        for turn in turns.values():
            review=reviewed.get((turn['id'],'baseline'))
            if not positive(review,turn,'baseline'):continue
            identity=turn['lanes']['baseline'].get('task_id')
            try:
                info=task_info(output,identity,request,baseline=True);delivery(output,turn,'baseline',info['locks'])
                if any((info['compatibility'],info[key]) in seen[key] for key in seen):continue
                for key in seen:seen[key].add((info['compatibility'],info[key]))
                info['support_review']={'comparison_id':turn['id'],'review_id':review['id'] if review else None};candidates.append(info)
            except (ValueError,KeyError,OSError,TypeError) as error:excluded.append({'task_id':identity,'reason':str(error)[:160]})
        if len(candidates)<3:status({'status':'waiting_for_eligible_tasks','eligible_tasks':len(candidates),'minimum_tasks':3,'excluded':excluded});return
        groups={}
        for row in candidates:groups.setdefault(row['compatibility'],[]).append(row)
        compatible=next((rows for rows in reversed(list(groups.values())) if len(rows)>=3),None)
        if compatible is None:status({'status':'waiting_for_compatible_evidence','eligible_tasks':len(candidates)});return
        heldout=compatible[0];training=compatible[-2:]
        selected=[*training,heldout]
        signature=digest({'tasks':[(r['task_id'],r['locks']) for r in selected],
            'code':{p.relative_to(ROOT).as_posix():sha(p) for p in compiler.code_paths()}})
        attempted_path=store/'attempted.json';attempted=read(attempted_path) if attempted_path.exists() else []
        if signature in attempted:status({'status':'rejected_unchanged_evidence','excluded':excluded});return
        save(attempted_path,[*attempted,signature])
        index=1
        while (store/f'round-{index:04d}').exists():index+=1
        folder=store/f'round-{index:04d}';folder.mkdir(mode=0o700)
        dataset={split:[{'task_dir':item['task_dir'],'decision_id':item['decision_id']} for item in rows] for split,rows in [('train',training),('heldout',[heldout])]}
        dataset['ledger']=str(folder/'ledger.json')
        save(folder/'dataset.json',dataset);save(folder/'ledger.json',[row for item in selected for row in read(Path(item['task_dir'])/'learning-accounting.json')['request_receipts']])
        status({'status':'compiling','round':folder.name})
        try:
            compiler.main(['--dataset',str(folder/'dataset.json'),'--out',str(folder/'compile'),'--publish',str(folder/'release')],private_publish_root=store)
            runtime=load_product_bundle(ROOT,folder/'release','ppt',private_root=store)
            admission={'schema_version':1,'user':request['user'],'scope':request['scope'],'runtime':runtime,
                'evidence_locks':{name:version for item in selected for name,version in item['locks'].items()},
                'support':{key:[row[key] for row in selected] for key in seen},'support_reviews':[row['support_review'] for row in selected],
                'trace_collection_proxy_usd':sum(r['totals']['proxy_peak_usd'] for r in selected),'incremental_compilation_model_requests':0}
            save(folder/'admission.json',admission)
            pointer={'schema_version':1,'user':request['user'],'scope':request['scope'],'round':folder.name,
                'admission_sha256':sha(folder/'admission.json'),'evidence_signature':signature,'phase':'probation','quality_cost_promoted':False,'feedback_version':feedback_version}
            save(candidate_path,pointer);save(selected_path,pointer);resume()
            status({'status':'probation','round':folder.name,'independent_evaluations':0,'required_independent_pairs':2,'quality_cost_promoted':False,'excluded':excluded})
        except (ValueError,KeyError,OSError,TypeError,subprocess.SubprocessError) as error:
            status({'status':'certification_rejected','round':folder.name,'reason':str(error)[:160],'excluded':excluded})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',type=Path,required=True)
    advance(parser.parse_args().request)
