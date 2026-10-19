"""Real MCP and Docker diagnostics; no cloud model or benefit evidence."""
import asyncio,json
from pathlib import Path
from uuid import uuid4
import pytest
from src.adapters.general_tools import Gateway,ROOT,FORMAT,save

@pytest.fixture
def work():
    w=ROOT/'.local/general-tools-tests'/uuid4().hex/'work';(w/'inputs').mkdir(parents=True)
    import hashlib
    (w/'inputs/note.txt').write_text('alpha beta alpha')
    save(w/'approved-inputs.json',{'files':{'note.txt':hashlib.sha256((w/'inputs/note.txt').read_bytes()).hexdigest()}})
    save(w/'job.json',{'allow_output':True});return w

def test_real_mcp_schema_edit_and_idempotent_receipt(work):
    async def run():
        g=Gateway(work,{'task_id':'one'})
        try:
            schema=await g.describe_tool('workspace-runtime','edit_text')
            assert schema['tool']['name']=='edit_text' and not schema['motif_required']
            h=json.loads((work/'approved-inputs.json').read_text())['files']['note.txt']
            q=await g.prepare_tool_call('workspace-runtime','edit_text',{'name':'note.txt','sha256':h,
                'replacements':[{'old':'alpha','new':'gamma','expected_count':2}],'destination':'edited/note.txt'})
            r=await g.execute_tool_call(q['request_id']);assert r['status']=='completed'
            assert await g.execute_tool_call(q['request_id'])==r
            result=g.inspect_tool_result(r['receipt_id'])
            artifacts=list((work/'outputs').rglob('note.txt'))
            assert len(artifacts)==1 and artifacts[0].read_text()=='gamma beta gamma'
            assert (work/'inputs/note.txt').read_text()=='alpha beta alpha'
            assert result['actual_mcp_result'] and result['cost']['model_requests']==0
            with pytest.raises(Exception,match='schema'):
                await g.prepare_tool_call('workspace-runtime','edit_text',{'invented':'argument'})
            state,_=g.request(q['request_id']);state['arguments']['destination']='../../escape'
            save(g.home/'requests'/f"{q['request_id']}.json",state)
            with pytest.raises(Exception,match='changed'):await g.execute_tool_call(q['request_id'])
        finally:await g.close()
    asyncio.run(run())

def test_permissions_and_unknown_effects_are_not_replayed(work):
    async def run():
        g=Gateway(work,{'task_id':'one','read_only':True})
        try:
            with pytest.raises(Exception,match='read-only'):
                await g.prepare_tool_call('workspace-runtime','create_text',{'destination':'x.txt','text':'x'})
            q=await g.prepare_tool_call('workspace-runtime','runtime_capabilities',{})
            state,p=g.request(q['request_id']);state['status']='executing';save(p,state)
            with pytest.raises(Exception,match='outcome unknown'):await g.execute_tool_call(q['request_id'])
            with pytest.raises(Exception,match='host registry'):await g.describe_tool('model-invented-shell','exec')
        finally:await g.close()
    asyncio.run(run())

def test_provider_registry_is_extensible_without_scene_or_motif_adapter(work):
    async def run():
        config=work/'providers.json';save(config,{'format':FORMAT,'providers':[{
            'id':'custom-text-reader','transport':'stdio','command':'${PYTHON}',
            'args':['${PROJECT_ROOT}/scenarios/general/server.py','${SESSION_WORKSPACE}/inputs'],
            'policy':'read_only','cost':'local_no_model'}]})
        g=Gateway(work,{'task_id':'external'},config=config)
        try:
            t=await g.describe_tool('custom-text-reader','list_files')
            assert t['tool']['name']=='list_files'
            q=await g.prepare_tool_call('custom-text-reader','list_files',{})
            r=await g.execute_tool_call(q['request_id'])
            assert r['status']=='completed' and g.inspect_tool_result(r['receipt_id'])['actual_mcp_result']
        finally:await g.close()
    asyncio.run(run())

def test_actual_isolated_code_reads_only_approved_inputs(work):
    import subprocess,shutil
    if not shutil.which('docker'):pytest.skip('isolated Docker runtime unavailable')
    if subprocess.run(['docker','image','inspect','node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e'],capture_output=True).returncode:
        pytest.skip('isolated Docker image not installed')
    from importlib.util import spec_from_file_location,module_from_spec
    p=ROOT/'scenarios/general/runtime.py';s=spec_from_file_location('general_runtime',p);m=module_from_spec(s);s.loader.exec_module(m)
    async def run():
        from mcp import Client
        async with Client(m.create_server(work)) as c:
            cap=await c.call_tool('runtime_capabilities',{})
            data=cap.model_dump(mode='json',by_alias=True)
            # Explicit optional Docker check; never count absence as code readiness.
            structured=data.get('structuredContent') or data.get('structured_content') or json.loads(data['content'][0]['text'])
            assert structured['code']['available']
            result=await c.call_tool('execute_code',{'program':
                'const x=await inputs.read_text({name:"note.txt"}); await outputs.write_text({name:"stats.json",text:JSON.stringify({words:x.text.split(" ").length})}); console.log("done");'})
            raw=result.model_dump(mode='json',by_alias=True)
            assert not raw.get('isError',raw.get('is_error',False))
            files=list((work/'outputs/code').rglob('stats.json'));assert len(files)==1 and json.loads(files[0].read_text())=={'words':3}
            assert (work/'inputs/note.txt').read_text()=='alpha beta alpha'
    asyncio.run(run())
