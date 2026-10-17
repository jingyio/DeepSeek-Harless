"""Synthetic compiler/lifecycle diagnostics, never a real provider acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from tests.test_trace_compiled_read_motif import event_pair
from src.adapters.harless_rsi_bundle import load_product_bundle

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('auto_paper',ROOT/'scripts/learn-web-paper-tasks.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
PIN,READ=worker.compiler.PAIR


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


@pytest.fixture
def owned():
    out=ROOT/'.local/auto-paper-tests'/uuid4().hex;out.mkdir(parents=True)
    scope='a'*64;user='diagnostic-user'
    store=out/'learning'/hashlib.sha256((user+'\0'+scope).encode()).hexdigest();store.mkdir(parents=True)
    req=store/'request.json';save(req,{'schema_version':1,'output':str(out),'user':user,'scope':scope,'task_ids':[]})
    yield out,store,req
    shutil.rmtree(out)


def task(owned,index,*,mode='baseline',user='diagnostic-user',old_only=False,question=None):
    out,store,request=owned;identity=f'{index:032x}';directory=out/'tasks'/identity;directory.mkdir(parents=True)
    source='source-'+f'{index:032x}';version=hashlib.sha256(str(index).encode()).hexdigest()
    rows=event_pair(1,PIN,{'name':f'paper-{index}.txt','sha256':version},{'source_id':source,'version_sha256':version})+event_pair(2,READ,{'source_id':source,'page':1},{'source_id':source,'version_sha256':version,'text':f'Current source {index}'})
    (directory/'events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
    (directory/'answer.md').write_text('Synthetic diagnostic only',encoding='utf-8')
    budget='turn-'+identity
    usage={'prompt_tokens':12,'prompt_cache_hit_tokens':2,'prompt_cache_miss_tokens':10,'completion_tokens':3,'total_tokens':15}
    stats={'upstream_requests':1,'usage_complete':True,'pending_requests':0,'unknown_usage_requests':0,'verified_skips':0,**usage}
    common={'task_id':identity,'session_id':'sss-'+identity,'user_id':user,'mode':mode,'scene':'paper-proofreading','status':'completed','stats':stats,'source_task_id':identity}
    entry=json.loads((ROOT/'config/harless-scenes.json').read_text())['scenes'][1]['rsi']['runtime_bundle']
    tools=json.loads((ROOT/entry/'tool-schemas.json').read_text())
    save(directory/'task-state.json',common)
    save(directory/'effective-config.json',{**common,'provider_mode':'real','tools':tools,'trace_start_index':len(rows) if old_only else 0})
    save(directory/'task.json',{**common,'content':[{'type':'text','text':question or f'Check the literal records in independent document {index}'}]})
    save(directory/'budget-route.json',{'budget_session_id':budget})
    save(directory/'learning-accounting.json',{'task_id':identity,'session_id':budget,'request_receipts':[{'task_id':identity,'global_request_id':index,'response_status':200,'response_usage':usage,'observed_peak_usd':.001}]})
    req=json.loads(request.read_text());req['task_ids'].append(identity);save(request,req)
    return directory


def test_existing_traces_compile_and_publish_next_private_version_without_changing_tasks(owned):
    out,store,request=owned
    for index in range(1,4):task(owned,index)
    before={str(path):worker.sha(path) for path in (out/'tasks').rglob('*') if path.is_file()}
    worker.advance(request)
    pointer=json.loads((store/'latest.json').read_text());assert pointer['round']=='round-0001'
    release=store/pointer['round']/'release'
    admitted=load_product_bundle(ROOT,release,'paper-proofreading',private_root=store)
    assert admitted['runtime_kind']=='paper_document_read_v1'
    assert len(json.loads((release/'library.json').read_text())['artifacts'])==1
    assert json.loads((release/'learning-report.json').read_text())['compilation_model_requests']==0
    assert before=={str(path):worker.sha(path) for path in (out/'tasks').rglob('*') if path.is_file()}
    first=worker.sha(release/'entry.json');worker.advance(request)
    assert json.loads((store/'status.json').read_text())['status']=='unchanged'
    task(owned,4);worker.advance(request)
    assert json.loads((store/'latest.json').read_text())['round']=='round-0002'
    assert worker.sha(release/'entry.json')==first
    held=json.loads((store/'round-0002/release/source-evidence.json').read_text())['heldout'][0]
    assert held['task_id']==f'{1:032x}'


@pytest.mark.parametrize('issue',['execute','foreign','history-only','duplicate-question','pending'])
def test_non_independent_or_incomplete_inputs_never_publish(owned,issue):
    task(owned,1);task(owned,2)
    directory=task(owned,3,mode='execute' if issue=='execute' else 'baseline',user='other' if issue=='foreign' else 'diagnostic-user',old_only=issue=='history-only',question='Check the literal records in independent document 1' if issue=='duplicate-question' else None)
    if issue=='pending':
        p=directory/'task-state.json';s=json.loads(p.read_text());s['stats']['pending_requests']=1;save(p,s)
    worker.advance(owned[2]);assert not (owned[1]/'latest.json').exists()
    assert json.loads((owned[1]/'status.json').read_text())['status']=='waiting_for_evidence'


def test_private_release_cannot_be_read_as_another_store_or_as_another_scene(owned):
    for index in range(1,4):task(owned,index)
    worker.advance(owned[2]);release=owned[1]/'round-0001/release'
    other=owned[0]/'other-store';other.mkdir()
    with pytest.raises(ValueError):load_product_bundle(ROOT,release,'paper-proofreading',private_root=other)
    with pytest.raises(ValueError):load_product_bundle(ROOT,release,'ppt',private_root=owned[1])
