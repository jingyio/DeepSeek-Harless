"""Timing checks use actual completion and native message batches, not final files."""
import sys,copy,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scenarios/file-management'))
from management_goals import compile_goal
from management_temporal import compile_temporal,verify_temporal
INITIAL={'files':{'alpha.pdf':'a','beta.pdf':'b','memo.txt':'m'},'directories':[]}
SCOPE={'permission':'original'}

def events(rows):
    result=[]
    for i,(tool,batch,call,end,path) in enumerate(rows):
        cid='native-'+str(i);out={'_sss_scope':SCOPE,'path':'workspace/'+path,'status':'readable','truncated':False,**({'complete':True} if tool=='document_coverage' else {})}
        result += [{'seq':batch,'type':'assistant/message','data':{'usage':{'inputTokens':1},'message':{'source':{'kind':'model'},'content':[{'type':'tool-call','id':cid}]}}},
            {'seq':call,'type':'tool/call','data':{'name':'mcp__file_management__'+tool,'callId':cid,'arguments':'{}'}},
            {'seq':end,'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':cid,'content':[{'type':'text','text':json.dumps(out)}]}]}}}]
    return result

def test_language_freezes_same_batch_and_does_not_allow_file_checks_to_erase_unknown_timing():
    g=compile_goal('时序要求：在同一条工具调用消息中依次打开 alpha.pdf、beta.pdf 并完整读取 memo.txt。',INITIAL,[{'kind':'unchanged','path':'memo.txt'}])
    assert g['temporal']['state']=='frozen' and len(g['temporal']['predicates'])==2
    unknown=compile_goal('先按照重要性处理，然后在适当时间归档',INITIAL,[{'kind':'unchanged','path':'memo.txt'}])
    assert unknown['temporal']['state']=='review_required'

def test_same_batch_requires_one_actual_model_message_and_declared_order():
    c=compile_temporal('时序要求：在同一条工具调用消息中依次打开 alpha.pdf、beta.pdf 并完整读取 memo.txt。',INITIAL)
    rows=[('open_document',1,2,3,'alpha.pdf'),('open_document',1,4,5,'beta.pdf'),('read_file',1,6,7,'memo.txt'),('read_document_chunk',8,9,10,'alpha.pdf')]
    assert verify_temporal(c,events(rows),{},SCOPE)['verified']
    for changed in [[*rows[:2],('read_file',5,6,7,'memo.txt'),rows[3]], [rows[1],rows[0],rows[2],rows[3]]]:
        if changed[0]==rows[1]:changed=[('open_document',1,4,5,'alpha.pdf'),('open_document',1,2,3,'beta.pdf'),*rows[2:]]
        assert not verify_temporal(c,events(changed),{},SCOPE)['verified']
    forged=events(rows)
    for e in forged:
        if e['type']=='assistant/message':e['data']['message']['source']['kind']='motif'
    assert not verify_temporal(c,forged,{},SCOPE)['verified']

def test_before_requires_result_completion_and_cannot_be_repaired_by_later_duplicate_reads():
    c=compile_temporal('时序要求：先完整读取 memo.txt，再完整读取 alpha.pdf。',INITIAL)
    rows=[('read_file',1,2,10,'memo.txt'),('document_coverage',3,4,11,'alpha.pdf')]
    assert not verify_temporal(c,events(rows),{},SCOPE)['verified']
    good=[('read_file',1,2,3,'memo.txt'),('document_coverage',4,5,6,'alpha.pdf')]
    assert verify_temporal(c,events(good),{},SCOPE)['verified']
    assert verify_temporal(c,events([*good,('read_file',7,8,9,'memo.txt')]),{},SCOPE)['verified']
    wrong=[('document_coverage',1,2,3,'alpha.pdf'),('read_file',4,5,6,'memo.txt'),('document_coverage',7,8,9,'alpha.pdf')]
    assert not verify_temporal(c,events(wrong),{},SCOPE)['verified']
    assert not verify_temporal(c,events(good),{},{} )['verified']
    assert verify_temporal(c,None,{},SCOPE)['state']=='trace_pending'

def test_parallel_preparation_minimum_count_and_before_any_execution():
    c=compile_temporal('时序要求：先在同一条工具调用消息中准备 2 个工具请求，再执行任何工具请求。',INITIAL)
    rows=[('prepare_tool_call',1,2,3,''),('prepare_tool_call',1,4,5,''),('execute_tool_call',6,7,8,'')]
    assert verify_temporal(c,events(rows),{},SCOPE)['verified']
    assert not verify_temporal(c,events([rows[0],rows[2]]),{},SCOPE)['verified']
    assert not verify_temporal(c,events([rows[0],('prepare_tool_call',9,10,11,''),rows[2]]),{},SCOPE)['verified']

def test_daily_quality_requires_host_trace_and_exposes_provisional_report(tmp_path):
    from uuid import uuid4
    from management_prepare import prepare
    from management_tools import ManagementScene
    from management_contract import verify_management
    w=tmp_path/'work';w.mkdir();(w/'a.txt').write_text('first');(w/'b.txt').write_text('second')
    h=Path(__file__).resolve().parents[1]/'.local/temporal-quality-tests'/uuid4().hex
    spec=prepare(h,w,task_id=uuid4().hex,objective='时序要求：先完整读取 a.txt，再完整读取 b.txt。',owner='test',workspace_id='test',quality=[{'kind':'read','path':n} for n in ['a.txt','b.txt']])
    s=ManagementScene(spec,h/'delivery');s.read_task();listing=s.list_files();out=[]
    for n in ['a.txt','b.txt']:
        f=next(r for r in listing['files'] if r['path']==n);source=s.pin_file(f['file_id'])['source_id'];out.append(s.read_file(source))
    receipt=s.submit_report('actual two reads',list(s.files()),[])
    assert receipt['semantic_quality_verified'] is False
    report=json.loads((s.output/'report.json').read_text())
    assert not verify_management(spec,report,s.output,events=[])['passed']
    trace=events([('read_file',1,2,3,'a.txt'),('read_file',4,5,6,'b.txt')])
    results=[e for e in trace if e['type']=='tool/result']
    for e,v in zip(results,out):e['data']['message']['content'][0]['content'][0]['text']=json.dumps(v)
    assert verify_management(spec,report,s.output,events=trace)['semantic_quality_verified']

def test_web_collection_rechecks_temporal_trace_from_enrollment(tmp_path,monkeypatch):
    from uuid import uuid4
    import management_web
    from management_prepare import prepare
    from management_tools import ManagementScene
    root=Path(__file__).resolve().parents[1];h=root/'.local/temporal-web-tests'/uuid4().hex;w=tmp_path/'work';w.mkdir();(w/'a.txt').write_text('first');(w/'b.txt').write_text('second')
    td=h/'host/management';spec=prepare(td,w,task_id=uuid4().hex,objective='时序要求：先完整读取 a.txt，再完整读取 b.txt。',owner='test',workspace_id='test',quality=[{'kind':'read','path':n} for n in ['a.txt','b.txt']])
    s=ManagementScene(spec,td/'delivery');s.read_task();listing=s.list_files();out=[]
    for n in ['a.txt','b.txt']:
        f=next(r for r in listing['files'] if r['path']==n);out.append(s.read_file(s.pin_file(f['file_id'])['source_id']))
    s.submit_report('actual two reads',list(s.files()),[])
    (td/'enrollment.json').write_text(json.dumps({'out':str(h/'host')}))
    trace=events([('read_file',1,2,3,'a.txt'),('read_file',4,5,6,'b.txt')])
    for e,v in zip([e for e in trace if e['type']=='tool/result'],out):e['data']['message']['content'][0]['content'][0]['text']=json.dumps(v)
    (h/'host/events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in trace))
    monkeypatch.setattr(management_web,'load_config',lambda _: {'adapter':'management_v3','provider_mode':'mock'})
    value={'action':'collect','rsi_config':str(h/'fixture.json'),'provider_mode':'mock','directory':str(td),'native_workspace':str(h/'native')}
    rows=management_web.dispatch(value);report=next(r for r in rows if r['name']=='management-report.json')
    assert report['goal_status']=='verified'
    (h/'host/events.jsonl').write_text('')
    import pytest
    with pytest.raises(ValueError,match='delivery changed'):management_web.dispatch(value)


def test_daily_readonly_timing_language_freezes_file_checks_without_explicit_template():
    g=compile_goal('时序要求：先完整读取 memo.txt，再完整读取 alpha.pdf。不修改任何文件。完成后核验并提交报告。',INITIAL)
    assert g['state']=='frozen' and g['source']=='bounded_temporal_reading'
    assert g['requirements']==[{'kind':'read','path':'memo.txt'},{'kind':'read','path':'alpha.pdf'}]
    assert g['temporal']['predicates'][0]['events'][1]['tool']=='document_coverage'
    unknown=compile_goal('时序要求：先完整读取 memo.txt，再完整读取 alpha.pdf。之后按照重要性删除文件',INITIAL)
    assert unknown['state']=='review_required'
