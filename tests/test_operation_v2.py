import copy,json,sys
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
import file_tools
from common import snapshot
from operation_tools_v2 import OperationSceneV2
from src.adapters.operation_runner import initialize_job
from src.adapters.operation_budget import OperationBudget,command
from src.motif_core.offline.operation_graph import discover_graphs,certify_graph,catalog,CONTRACT

@pytest.fixture
def case(tmp_path,monkeypatch):
    monkeypatch.setattr(file_tools,'DATA',tmp_path);monkeypatch.setattr(file_tools,'ROOT',tmp_path)
    work=tmp_path/'copy';work.mkdir();(work/'.experiment-copy').write_text('authorized')
    for name in ('a.txt','b.txt'):(work/name).write_text('actual '+name)
    spec={'schema_version':1,'task_id':uuid4().hex,'role':'bootstrap','family':'inventory','objective':'two actual copies',
       'workspace':str(work),'initial_snapshot':snapshot(work),'rules':{},'allowed_operations':['copy'],
       'report_contract':{'version':'sss-file-report-v3','kind':'task_result'},'operation_contract':{'version':'sss-file-operation-contract-v1',
       'validation_version':'sss-file-operation-quality-v2','require_result_read':True,
       'actions':[{'op':'copy','source':n,'destination':'out/'+n,'format':'none'} for n in ('a.txt','b.txt')]}}
    return spec,tmp_path/'.local/delivery'

def plan(s):
    s.read_task();return s.preview_actions([{'op':a['op'],'file_ids':[s.file_id(a['source'])],'destination':a['destination'],'format':a['format']} for a in s.spec['operation_contract']['actions']])

def test_multiple_real_outputs_have_complete_batch_bindings_and_survive_restart(case):
    spec,out=case;s=OperationSceneV2(spec,out);p=plan(s);receipt=s.execute_plan(p['plan_id']);ins=s.inspect_plan_result(receipt['receipt_id'])
    assert ins['primary_file_id'] is None
    pinned=s.pin_files([r['file_id'] for r in ins['files']]);reads=s.read_files(pinned['source_ids'])
    assert reads['count']==2 and {r['path'] for r in reads['reads']}=={'out/a.txt','out/b.txt'}
    restarted=OperationSceneV2(spec,out);restarted.read_task()
    assert restarted.execute_plan(p['plan_id'])['receipt_id']==receipt['receipt_id']
    assert restarted.read_files(pinned['source_ids'])==reads
    assert len(restarted.journals[p['plan_id']]['completed'])==2

def test_publish_crash_finishes_only_remaining_boundaries_and_foreign_changes_block(case,monkeypatch):
    spec,out=case;s=OperationSceneV2(spec,out);p=plan(s)
    original=snapshot(s.root);link=__import__('os').link
    def crash(source,dest):link(source,dest);raise SystemExit('simulated process exit after no-overwrite publication')
    monkeypatch.setattr('os.link',crash)
    with pytest.raises(SystemExit):s.execute_plan(p['plan_id'])
    monkeypatch.setattr('os.link',link)
    restarted=OperationSceneV2(spec,out);restarted.read_task();r=restarted.execute_plan(p['plan_id'])
    assert r['operation_count']==2 and len(restarted.journals[p['plan_id']]['completed'])==2
    assert all((restarted.root/'out'/n).read_bytes()==(restarted.root/n).read_bytes() for n in ('a.txt','b.txt'))
    (restarted.root/'foreign.txt').write_text('not authorized')
    with pytest.raises(ValueError,match='unrecorded'):OperationSceneV2(spec,out)

def test_durable_budget_and_two_transport_retries_do_not_reset():
    root=ROOT/'.local/operation-v2-tests'/uuid4().hex;root.mkdir(parents=True);task=root/'input.json';task.write_text('{}')
    job=root/'job.json';version='a'*64
    command(job,'init',{'task_file':str(task),'delivery_root':str(root/'delivery'),'execution_version_sha256':version,
       'limits':{'budget_usd':.25,'max_requests':2,'max_steps':96,'max_output':4000,'max_repairs':2}})
    b=OperationBudget(job,root/'ledger.jsonl');body=json.dumps({'model':'deepseek-flash','max_tokens':4000,'messages':[]}).encode()
    r=b.book(body);assert r;assert b.claim_provider_retry();command(job,'pause')
    charged=b.reserved_usd;b.recover(version,__import__('os').getpid())
    assert b.request_count==1 and b.reserved_usd==charged and b.claim_provider_retry() and not b.claim_provider_retry()
    assert b.book(body) and b.book(body) is None
    rows=[json.loads(l) for l in b.record.read_text().splitlines()];assert len(rows)==1 and rows[0]['original_reservation_retained']
    command(job,'cancel')
    with pytest.raises(ValueError,match='recoverable'):b.recover(version,__import__('os').getpid())

def test_variable_array_transfer_is_learned_and_not_semantic_constants():
    frames=[]
    for k in ('one','two','cert'):
        scope={'execution_version':'e'*64,'input_sha256':k};names=['mcp__other__result','mcp__other__batch']
        tools=catalog([{'name':names[0],'inputSchema':{'type':'object','required':['receipt']},'_meta':{'sss_learning':{'format':CONTRACT,'effect':'read','auto_continue':False,'exports':['files[].id']}}},
          {'name':names[1],'inputSchema':{'type':'object','required':['ids'],'properties':{'ids':{'type':'array','items':{'type':'string'},'maxItems':40}}},
            '_meta':{'sss_learning':{'format':CONTRACT,'effect':'read','auto_continue':True,'exports':[]}}}])
        rows=[{'name':names[0],'args':{'receipt':k},'out':{'files':[{'id':k+'-a'},{'id':k+'-b'}],'_sss_scope':scope},'call_id':k+'0','message_seq':1},
              {'name':names[1],'args':{'ids':[k+'-a',k+'-b']},'out':{'_sss_scope':scope},'call_id':k+'1','message_seq':2}]
        frames.append({'tools':tools,'scope':scope,'rows':rows,'fingerprint':k,'trace_id':k,'record':{'events_sha256':k}})
    cs,_=discover_graphs(frames[:2]);assert len(cs)==1
    p=certify_graph(cs[0]['compiled'],frames[2]);assert p['format']=='sss-operation-graph-v2' and p['artifact']['nodes'][1]['bindings']['ids']['path']=='files[].id'
    for f in frames[:2]:f['rows'][1]['args']['ids'].append('semantic constant')
    assert not discover_graphs(frames[:2])[0]

def test_recovered_trace_keeps_exact_original_events(tmp_path):
    from src.adapters.continuous_motif_learning import verify_original_events
    from src.adapters.continuous_rsi import sha
    raw=tmp_path/'native.jsonl';event={'seq':8,'type':'tool/call','data':{'callId':'original','arguments':'{}'}};raw.write_text(json.dumps(event)+'\n')
    record={'adapter':'file_operations_v2','metrics':{'attempt_files':[{'file':str(raw),'sha256':sha(raw),'attempt':'first'}]}}
    joined={**event,'seq':1,'original_seq':8,'durable_attempt':'first'};verify_original_events(record,tmp_path,[joined])
    with pytest.raises(ValueError,match='modified'):verify_original_events(record,tmp_path,[{**joined,'data':{}}])
    with pytest.raises(ValueError,match='erased'):verify_original_events(record,tmp_path,[])

def test_restored_task_keeps_its_limits_when_new_task_defaults_are_lower():
    from src.adapters.deepseek_cost_gate import State
    from src.adapters.web_task_budget import TaskBudgetRegistry
    root=ROOT/'.local/operation-v2-tests'/uuid4().hex;tid=uuid4().hex;directory=root/'old'/tid;directory.mkdir(parents=True)
    task=directory/'input.json';task.write_text('{}');job=directory/'operation-job.json';ledger=directory/'ledger.jsonl'
    command(job,'init',{'task_file':str(task),'delivery_root':str(directory/'delivery'),'execution_version_sha256':'b'*64,
       'limits':{'budget_usd':5,'max_requests':96,'max_steps':96,'max_output':4000,'max_repairs':2}})
    original=TaskBudgetRegistry(run_state=State(cap_usd=25,output_cap=4000,request_limit=256,record=root/'global.jsonl'),tasks_root=root/'old',max_task_budget_usd=5,task_request_limit=96)
    original.register(tid,'sss-original',5,job_file=str(job),ledger_file=str(ledger))
    restarted=TaskBudgetRegistry(run_state=State(cap_usd=25,output_cap=4000,request_limit=256,record=root/'global.jsonl'),tasks_root=root/'new',max_task_budget_usd=.25,task_request_limit=24)
    restarted.register(tid,'sss-original',5,job_file=str(job),ledger_file=str(ledger))
    assert restarted.by_task[tid].state.cap_usd==5 and restarted.by_task[tid].state.request_limit==96
    with pytest.raises(ValueError,match='server maximum'):restarted.register(uuid4().hex,'sss-new',5)
