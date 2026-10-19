"""无模型诊断：真实离线编译器，合成事件，不作为云效果/用户人评证据。"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from uuid import uuid4
import zipfile

import fitz
import pytest
from tests.test_trace_compiled_read_motif import event_pair
from src.adapters.harless_rsi_bundle import load_product_bundle

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('auto_ppt',ROOT/'scripts/learn-web-ppt-tasks.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
PIN,CONVERT,READ=worker.compiler.CHAIN
USER='diagnostic-user';SCOPE='a'*64
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


@pytest.fixture
def owned():
    out=ROOT/'.local/auto-ppt-tests'/uuid4().hex;out.mkdir(parents=True)
    store=out/'learning'/('ppt-'+hashlib.sha256((USER+'\0'+SCOPE).encode()).hexdigest());store.mkdir(parents=True)
    req=store/'request.json';save(req,{'schema_version':1,'output':str(out),'user':USER,'scope':SCOPE,'task_ids':[],'automatic_structural_learning':True})
    save(out/'comparisons.json',{'version':1,'principal':USER,'turns':[]})
    yield out,store,req
    shutil.rmtree(out)


def task(owned,index,*,mode='baseline',source=None,version=None,cost=.002,requests=2,old_only=False,question=None):
    out,store,req=owned;identity=f'{index:032x}';directory=out/'tasks'/identity;directory.mkdir(parents=True)
    source_index=source or index;source_id='source-'+f'{source_index:032x}';converted='result-'+f'{source_index:032x}'
    source_version=hashlib.sha256(str(source_index).encode()).hexdigest()
    rows=event_pair(1,PIN,{'name':f'paper-{source_index}.pdf','sha256':source_version},{'source_id':source_id,'version_sha256':source_version})
    rows+=event_pair(2,CONVERT,{'source_id':source_id},{'converted_id':converted,'version_sha256':source_version})
    rows+=event_pair(3,READ,{'converted_id':converted},{'version_sha256':source_version,'text':f'Current source {source_index}'})
    (directory/'events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    (directory/'answer.md').write_text('Synthetic diagnostic, not a real user review',encoding='utf-8')
    usage={'prompt_tokens':12,'prompt_cache_hit_tokens':2,'prompt_cache_miss_tokens':10,'completion_tokens':3,'total_tokens':15}
    stats={'upstream_requests':requests,'usage_complete':True,'pending_requests':0,'unknown_usage_requests':0,'verified_skips':1 if mode=='execute' else 0,
        **{key:value*requests for key,value in usage.items()}}
    common={'task_id':identity,'session_id':'session-'+identity,'user_id':USER,'mode':mode,'scene':'ppt','status':'completed','stats':stats,
        'source_task_id':identity,'scene_inputs':[{'version_sha256':source_version}]}
    schemas=json.loads((ROOT/'motif-libraries/ppt-master-v8/tool-schemas.json').read_text(encoding='utf-8'))
    effective={**common,'provider_mode':'real','tools':schemas,'trace_start_index':len(rows) if old_only else 0,'ppt_execution_strategy':'ppt_master',
        'skill_package_sha256':worker.compiler.read_lock()['package_sha256'],'model':'diagnostic','provider':'diagnostic','reasoning_effort':'off',
        'instructions_sha256':'b'*64,'compression':False,'learning_version':version}
    if version:effective['library_sha256']=worker.read(store/version/'admission.json')['runtime']['runtime_library_sha256']
    save(directory/'task-state.json',common);save(directory/'effective-config.json',effective)
    save(directory/'task.json',{**common,'content':[{'type':'text','text':question or f'Explain independent paper {source_index}'}]})
    save(directory/'budget-route.json',{'budget_session_id':'budget-'+identity})
    receipts=[{'task_id':identity,'global_request_id':index*100+n,'response_status':200,'response_usage':usage,'observed_peak_usd':cost/requests} for n in range(requests)]
    save(directory/'learning-accounting.json',{'task_id':identity,'session_id':'budget-'+identity,'request_receipts':receipts})
    (directory/'motif-audit.jsonl').write_text(json.dumps({'kind':'model_request_skipped_verified'})+'\n' if mode=='execute' else '',encoding='utf-8')
    request=worker.read(req);request['task_ids'].append(identity);save(req,request)
    return directory


def artifacts(owned,comparison,lane):
    out=owned[0];folder=out/'comparison-artifacts'/comparison/lane/'0';folder.mkdir(parents=True)
    pdf=fitz.open();pdf.new_page().insert_text((20,30),'Diagnostic only');pdfbytes=pdf.tobytes();png=pdf[0].get_pixmap().tobytes('png');pdf.close()
    import io
    deck=io.BytesIO()
    with zipfile.ZipFile(deck,'w') as z:
        z.writestr('ppt/slides/slide1.xml','<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Diagnostic</a:t></p:sld>')
        z.writestr('ppt/notesSlides/notesSlide1.xml','<notes/>')
    rows=[]
    for index,(ext,data) in enumerate([('pptx',deck.getvalue()),('pdf',pdfbytes),('png',png)]):
        h=hashlib.sha256(data).hexdigest();identifier=h[:32]+'-'+str(index);(folder/identifier).write_bytes(data)
        rows.append({'id':identifier,'name':'outputs/test.'+ext,'sha256':h,'bytes':len(data),'attempt':0})
    return rows


def pair(owned,index,baseline,motif=None,*,review=True):
    out,store,_=owned;identity=f'comparison-{index}';lanes={}
    for name,directory in [('baseline',baseline),('motif',motif)]:
        if directory is None:continue
        request=worker.read(directory/'task.json')
        request['request_id']='compare-'+hashlib.sha256(json.dumps([identity,name,0],separators=(',',':')).encode()).hexdigest()[:48]
        save(directory/'task.json',request)
        lanes[name]={'task_id':request['task_id'],'status':'completed','attempt':0,'output_sha256':hashlib.sha256((identity+name).encode()).hexdigest(),
            'artifacts':artifacts(owned,identity,name),'feedback':None}
        if review:
            row={'schema_version':1,'id':uuid4().hex,'user':USER,'scope':SCOPE,'comparison_id':identity,'lane':name,'output_sha256':lanes[name]['output_sha256'],
                'quality':{'scientific':True,'visual':True,'usable':True},'allow_learning':True,'human_minutes':1}
            with (store/'reviews.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    value={'id':identity,'scene':'ppt','status':'completed','presentation':'paired' if motif else 'single','lanes':lanes}
    state=worker.read(out/'comparisons.json');state['turns'].append(value);save(out/'comparisons.json',state)
    return value


def seed(owned):
    for n in range(1,4):pair(owned,n,task(owned,n))
    worker.advance(owned[2]);assert worker.read(owned[1]/'status.json')['status']=='probation'


def test_existing_user_traces_certify_then_two_future_reviewed_pairs_promote(owned):
    seed(owned);out,store,req=owned
    release=store/'round-0001/release';assert load_product_bundle(ROOT,release,'ppt',private_root=store)['runtime_kind']=='ppt_master_v2'
    before=worker.sha(release/'entry.json');worker.advance(req);assert worker.sha(release/'entry.json')==before
    for n in (4,5):
        pair(owned,n,task(owned,n*10,source=n,cost=.003),task(owned,n*10+1,source=n,mode='execute',version='round-0001',cost=.001,requests=1))
        worker.advance(req)
        assert worker.read(store/'status.json')['status']==('probation' if n==4 else 'active')
    status=worker.read(store/'status.json');assert status['quality_cost_promoted'] is True and status['extra_provider_requests']==0
    assert worker.read(store/'selected.json')['phase']=='active'
    assert worker.read(release/'entry.json')['quality_cost_promoted'] is False


@pytest.mark.parametrize('issue',['no-consent','negative-quality','execute','pending','history-only','same-source','same-question','foreign'])
def test_unreviewed_non_native_or_non_independent_inputs_cannot_certify(owned,issue):
    for n in range(1,4):
        path=task(owned,n,mode='execute' if issue=='execute' and n==3 else 'baseline',old_only=issue=='history-only' and n==3,
            source=1 if issue=='same-source' else None,question='same' if issue=='same-question' else None)
        pair(owned,n,path)
    if issue in ('no-consent','negative-quality'):
        p=owned[1]/'reviews.jsonl';rows=[json.loads(line) for line in p.read_text().splitlines()]
        if issue=='no-consent':rows[-1]['allow_learning']=False
        else:rows[-1]['quality']['scientific']=False
        p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    if issue in ('pending','foreign'):
        p=path/'task-state.json';state=worker.read(p)
        if issue=='pending':state['stats']['pending_requests']=1
        else:state['user_id']='other-user'
        save(p,state)
    worker.advance(owned[2]);assert not (owned[1]/'candidate.json').exists()


@pytest.mark.parametrize('issue',['higher-cost','wrong-library','no-skip','missing-audit','different-model','changed-output','withdrawal','negative-feedback'])
def test_regression_or_invalid_execution_never_promotes(owned,issue):
    seed(owned);out,store,req=owned
    for n in (4,5):
        base=task(owned,n*10,source=n,cost=.003)
        opt=task(owned,n*10+1,source=n,mode='execute',version='round-0001',cost=.004 if issue=='higher-cost' else .001,requests=1)
        turn=pair(owned,n,base,opt)
        if n==5:
            if issue in ('wrong-library','different-model'):
                p=opt/'effective-config.json';v=worker.read(p);v['library_sha256' if issue=='wrong-library' else 'model']='wrong';save(p,v)
            if issue=='no-skip':
                p=opt/'task-state.json';v=worker.read(p);v['stats']['verified_skips']=0;save(p,v)
            if issue=='missing-audit':(opt/'motif-audit.jsonl').write_text('')
            if issue=='changed-output':(out/'comparison-artifacts'/turn['id']/'motif'/'0'/turn['lanes']['motif']['artifacts'][0]['id']).write_bytes(b'changed')
            if issue=='withdrawal':
                p=store/'reviews.jsonl';v=json.loads(p.read_text().splitlines()[-1]);v['allow_learning']=False
                with p.open('a') as f:f.write(json.dumps(v)+'\n')
            if issue=='negative-feedback':
                p=out/'comparisons.json';v=worker.read(p);v['turns'][-1]['lanes']['motif']['feedback']='down';save(p,v)
        worker.advance(req)
    assert worker.read(store/'selected.json')['phase']!='active'


def test_private_release_cannot_be_loaded_as_another_user_or_scene(owned):
    seed(owned);out,store,_=owned;other=out/'other-store';other.mkdir()
    with pytest.raises(ValueError):load_product_bundle(ROOT,store/'round-0001/release','ppt',private_root=other)
    with pytest.raises(ValueError):load_product_bundle(ROOT,store/'round-0001/release','paper-proofreading',private_root=store)


def test_compilation_failure_is_retained_and_not_retried_without_new_evidence(owned):
    for n in range(1,4):pair(owned,n,task(owned,n,old_only=True))
    worker.advance(owned[2]);assert worker.read(owned[1]/'status.json')['status']=='certification_rejected'
    worker.advance(owned[2]);assert worker.read(owned[1]/'status.json')['status']=='rejected_unchanged_evidence'
    assert len(list(owned[1].glob('round-*')))==1


def test_automatic_learning_needs_no_review_and_keeps_scientific_quality_unknown(owned):
    for n in range(1,4):pair(owned,n,task(owned,n),review=False)
    worker.advance(owned[2]);assert worker.read(owned[1]/'selected.json')['phase']=='probation'
    for n in (4,5):
        pair(owned,n,task(owned,n*10,source=n,cost=.003),task(owned,n*10+1,source=n,mode='execute',version='round-0001',cost=.001),review=False)
        worker.advance(owned[2])
    status=worker.read(owned[1]/'status.json')
    assert status['status']=='active' and status['mechanical_cost_promoted'] is True
    assert status['quality_cost_promoted'] is False and status['extra_provider_requests']==0
    evaluation=worker.read(owned[1]/'round-0001/evaluation.json')
    assert all(p['scientific_quality_reviewed'] is False and p['motif_human_minutes'] is None for p in evaluation['pairs'])
    assert not (owned[1]/'reviews.jsonl').exists()


def test_operator_can_disable_automatic_learning(owned):
    for n in range(1,4):pair(owned,n,task(owned,n),review=False)
    config=worker.read(owned[2]);config['automatic_structural_learning']=False;save(owned[2],config)
    worker.advance(owned[2]);assert worker.read(owned[1]/'status.json')['status']=='disabled_by_operator'
    assert not (owned[1]/'candidate.json').exists()


def test_paid_failed_retry_is_included_in_the_whole_task_cost(owned):
    seed(owned)
    base=task(owned,40,source=4,cost=.003)
    opt=task(owned,41,source=4,mode='execute',version='round-0001',cost=.001)
    turn=pair(owned,4,base,opt,review=False)
    prior=task(owned,42,source=4,mode='execute',version='round-0001',cost=.004)
    # Current successful attempt 1 follows a paid failed attempt 0.
    prior_req=worker.read(prior/'task.json');prior_req['request_id']=worker.read(opt/'task.json')['request_id'];save(prior/'task.json',prior_req)
    state=worker.read(prior/'task-state.json');state['status']='failed';save(prior/'task-state.json',state)
    request=worker.read(opt/'task.json');request['request_id']='compare-'+hashlib.sha256(json.dumps([turn['id'],'motif',1],separators=(',',':')).encode()).hexdigest()[:48];save(opt/'task.json',request)
    comparisons=worker.read(owned[0]/'comparisons.json');comparisons['turns'][-1]['lanes']['motif']['attempt']=1;save(owned[0]/'comparisons.json',comparisons)
    worker.advance(owned[2]);report=worker.read(owned[1]/'round-0001/evaluation.json')
    assert report['pairs'][0]['motif']['attempts']==2
    assert report['pairs'][0]['motif']['proxy_usd']==pytest.approx(.005)
    assert worker.read(owned[1]/'selected.json')['phase']=='disabled'


def test_final_failed_candidate_without_receipts_cannot_disappear(owned):
    seed(owned)
    base=task(owned,40,source=4);opt=task(owned,41,source=4,mode='execute',version='round-0001')
    pair(owned,4,base,opt,review=False);(opt/'learning-accounting.json').unlink()
    comparisons=worker.read(owned[0]/'comparisons.json');comparisons['turns'][-1]['lanes']['motif']['status']='failed';save(owned[0]/'comparisons.json',comparisons)
    worker.advance(owned[2]);assert worker.read(owned[1]/'selected.json')['phase']=='disabled'


def test_running_comparison_does_not_revoke_before_other_side_finishes(owned):
    seed(owned)
    base=task(owned,40,source=4);opt=task(owned,41,source=4,mode='execute',version='round-0001')
    pair(owned,4,base,opt,review=False);(base/'learning-accounting.json').unlink()
    comparisons=worker.read(owned[0]/'comparisons.json');comparisons['turns'][-1]['status']='running';save(owned[0]/'comparisons.json',comparisons)
    worker.advance(owned[2]);assert worker.read(owned[1]/'selected.json')['phase']=='probation'


def test_changed_model_configuration_can_use_its_own_independent_evidence(owned):
    for n in range(1,5):
        path=task(owned,n)
        if n>1:
            config=worker.read(path/'effective-config.json');config['model']='diagnostic-new-model';save(path/'effective-config.json',config)
        pair(owned,n,path,review=False)
    worker.advance(owned[2])
    store=owned[1]
    assert worker.read(store/'status.json')['status']=='probation'
    admission=worker.read(store/'round-0001/admission.json')
    assert set(admission['support']['decision_id'])=={'web-'+f'{n:032x}' for n in (2,3,4)}


def test_feedback_during_compilation_cannot_reenable_the_stale_candidate(owned,monkeypatch):
    for n in range(1,4):pair(owned,n,task(owned,n),review=False)
    store=owned[1];original=worker.compiler.main
    def veto_during_compile(*args,**kwargs):
        result=original(*args,**kwargs)
        comparisons=worker.read(owned[0]/'comparisons.json');comparisons['turns'][-1]['lanes']['baseline']['feedback']='down'
        save(owned[0]/'comparisons.json',comparisons)
        save(store/'suspended.json',{'reason':'negative_feedback'})
        save(store/'feedback-version.json',{'version':'changed-during-compilation'})
        return result
    monkeypatch.setattr(worker.compiler,'main',veto_during_compile)
    worker.advance(owned[2])
    assert (store/'suspended.json').exists()
    assert worker.read(store/'selected.json')['feedback_version']!=worker.sha(store/'feedback-version.json')
    worker.advance(owned[2]);assert worker.read(store/'selected.json')['phase']=='disabled'
