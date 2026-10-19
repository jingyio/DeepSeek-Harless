"""Actual local MCP edit + independent replay; free diagnostic, no model claim."""
import asyncio,copy,json,sys,shutil
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_prepare import prepare
from management_tools import ManagementScene
from src.adapters.general_tool_replay import verify_general_tools,eligible

def test_real_cross_tool_calls_require_original_scope_trace_and_exact_artifact():
    async def run():
        h=ROOT/'.local/general-replay-tests'/uuid4().hex;work=h/'workspace';work.mkdir(parents=True)
        (work/'memo.txt').write_text('old draft\n')
        spec=prepare(h/'task',work,task_id=uuid4().hex,objective='edit copy',owner='replay-test',workspace_id='one',quality=[{'kind':'unchanged','path':'memo.txt'}])
        origin=h/'origin';shutil.copytree(work,origin/'pristine')
        scene=ManagementScene(spec,h/'delivery');rows=[]
        def row(name,args,out):rows.append({'name':'mcp__file_management__'+name,'args':args,'out':out,'call_id':'native-'+str(len(rows)),'message_seq':len(rows)+1,'generated':False})
        row('read_task',{},scene.read_task())
        args={'provider_id':'workspace-runtime','tool_name':'edit_text','arguments':{'name':'memo.txt','sha256':spec['initial_snapshot']['memo.txt'],
            'replacements':[{'old':'old','new':'new'}],'destination':'nested/revised.txt'}}
        try:
            p=await scene.prepare_tool_call(**args);row('prepare_tool_call',args,p);assert p['status']=='prepared_certifiable'
            r=await scene.execute_tool_call(p['request_id']);row('execute_tool_call',{'request_id':p['request_id']},r);assert r['_sss_authorized']
            v=scene.inspect_tool_result(r['receipt_id']);row('inspect_tool_result',{'receipt_id':r['receipt_id']},v)
            record={'delivery':str(h/'delivery')};verify_general_tools(spec,record,origin,rows)
            # Real sealing copies outputs, while the original MCP receipt keeps
            # its actual execution path. The enrollment is the mapping authority.
            (origin/'enrollment.json').write_text(json.dumps({'delivery':str(h/'delivery')}))
            shutil.copytree(h/'delivery',h/'sealed/delivery')
            verify_general_tools(spec,{'delivery':str(h/'sealed/delivery')},origin,rows)
            ordinary={'provider_id':'workspace-runtime','tool_name':'runtime_capabilities','arguments':{}}
            q=await scene.prepare_tool_call(**ordinary);row('prepare_tool_call',ordinary,q)
            rr=await scene.execute_tool_call(q['request_id']);row('execute_tool_call',{'request_id':q['request_id']},rr)
            row('inspect_tool_result',{'receipt_id':rr['receipt_id']},scene.inspect_tool_result(rr['receipt_id']))
            verify_general_tools(spec,record,origin,rows)
            forged=copy.deepcopy(rows);forged[-2].update(generated=True,message_seq=None,call_id='sss-unproved')
            with pytest.raises(ValueError,match='semantic'):verify_general_tools(spec,record,origin,forged)
            bad=copy.deepcopy(rows);bad[-1]['out']['actual_mcp_result']={}
            with pytest.raises(ValueError,match='native calls'):verify_general_tools(spec,record,origin,bad)
            artifact=next((h/'delivery/general/work/outputs').rglob('revised.txt'));artifact.write_text('wrong')
            with pytest.raises(ValueError,match='independent replay'):verify_general_tools(spec,record,origin,rows)
            assert (work/'memo.txt').read_text()=='old draft\n'
        finally:
            if hasattr(scene,'_gateway'):await scene._gateway.close()
    asyncio.run(run())

def test_extra_provider_and_arbitrary_code_need_a_business_verifier():
    assert not eligible({'provider_id':'workspace-runtime','provider_contract':{},'tool_name':'edit_text'})
    public=json.loads((ROOT/'scenarios/file-management/general-tools.json').read_text())['providers'][0]
    assert not eligible({'provider_id':'workspace-runtime','provider_contract':public,'tool_name':'execute_code'})

def test_real_other_provider_preparation_is_stage_only_and_cannot_claim_execution_adapter():
    async def run():
        h=ROOT/'.local/general-other-preparation-tests'/uuid4().hex;work=h/'workspace';work.mkdir(parents=True);(work/'memo.txt').write_text('real new input')
        spec=prepare(h/'task',work,task_id=uuid4().hex,objective='prepare a real registered readonly tool',owner='test',workspace_id='test')
        scene=ManagementScene(spec,h/'delivery');scene.read_task()
        try:
            _,_,tools,_=await scene.gateway().catalog('paper-checks')
            tool=next(t for t in tools if not t.get('inputSchema',t.get('input_schema',{})).get('required'))
            p=await scene.prepare_tool_call('paper-checks',tool['name'],{})
            assert p['status']=='prepared' and p['_sss_request_lane']['stage_only'] is True and p['_sss_request_lane']['isolated_outputs'] is False
            q=scene.gateway().request(p['request_id'])[0]
            from src.adapters.general_tool_replay import lane
            assert lane(q) is None and lane(q,preparing=True)==p['_sss_request_lane']
            assert q['status']=='prepared' and not list((h/'delivery/general/work/outputs').glob('*'))
        finally:await scene._gateway.close()
    asyncio.run(run())
