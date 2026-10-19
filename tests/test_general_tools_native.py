"""Actual native MCP wrapper turns retain one underlying provider session."""
import asyncio,json,sys,os
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_prepare import prepare
from src.adapters.general_tools import save

def unpack(result):
    row=result.model_dump(mode='json',by_alias=True)
    assert not row.get('isError'),row.get('content')
    return row.get('structuredContent') or json.loads(next(c['text'] for c in row['content'] if c['type']=='text'))

def test_native_gateway_across_independent_tool_turns():
    from mcp import Client,StdioServerParameters
    h=ROOT/'.local/general-native-tests'/uuid4().hex;w=h/'workspace';w.mkdir(parents=True);(w/'source.txt').write_text('verified source')
    prepare(h/'task',w,task_id=uuid4().hex,objective='整理资料并创建中文备忘录',owner='free-probe',workspace_id='probe')
    save(h/'native/management-binding.json',{'task_file':str(h/'task/input.json'),'delivery':str(h/'task/delivery'),'job_file':''})
    async def run():
        async with Client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'scenarios/file-management/management_native.py')],
            cwd=str(ROOT),env={'PATH':os.environ['PATH'],'FM_WEB_WORKSPACE':str(h/'native'),'PYTHONUTF8':'0'})) as c:
            unpack(await c.call_tool('read_task',{}))
            schema=unpack(await c.call_tool('describe_tool',{'provider_id':'workspace-runtime','tool_name':'create_text'}))
            assert schema['tool']['name']=='create_text'
            q=unpack(await c.call_tool('prepare_tool_call',{'provider_id':'workspace-runtime','tool_name':'create_text','arguments':{'destination':'note.txt','text':'已核验的中文产物'}}))
            r=unpack(await c.call_tool('execute_tool_call',{'request_id':q['request_id']}))
            result=unpack(await c.call_tool('inspect_tool_result',{'receipt_id':r['receipt_id']}))
            assert result['status']=='completed'
            assert unpack(await c.call_tool('execute_tool_call',{'request_id':q['request_id']}))==r
            files=list((h/'task/delivery/general/work/outputs').rglob('note.txt'));assert len(files)==1
            assert files[0].read_text(encoding='utf-8')=='已核验的中文产物'
    asyncio.run(run())
