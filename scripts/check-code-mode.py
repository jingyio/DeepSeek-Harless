"""Free original Harness PTC and isolated upstream executor diagnostic."""
import importlib.util,json,sys,threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State,create_server
from src.adapters.native_budget import NativeBudgetGuard


def check(evidence_run=None):
    out=ROOT/'.local/code-mode-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
    spec=importlib.util.spec_from_file_location('ptc_mock',ROOT/'scripts/motif-example.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    extra_env={};task_directory=None;runner=None
    if evidence_run:
        sys.path.insert(0,str(ROOT/'scenarios/literature-notes'))
        spec=importlib.util.spec_from_file_location('ptc_evidence',ROOT/'scenarios/literature-notes/run-evidence.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        packet=json.loads((Path(evidence_run)/'evidence-packet.json').read_text())
        snapshot=json.loads((Path(evidence_run)/'evidence-input-snapshot.json').read_text())
        task_directory,extra_env=runner.prepare_task(Path(snapshot['task']['sources']['root']),packet['question'],frozen_plan=packet['plan'],tool_presentation='ptc')
        program='const parse=r=>JSON.parse(r.content[0].text); const t=parse(await tools.mcp__literature_evidence__list_pdfs({}));'
        program+=' const plan='+json.dumps(packet['plan'],ensure_ascii=False)+'; if(t.task_sha256!==plan.task_sha256)throw Error("task mismatch");'
        program+=' const p=parse(await tools.mcp__literature_evidence__register_reading_plan({plan:JSON.stringify(plan)}));'
        program+=' const e=parse(await tools.mcp__literature_evidence__extract_evidence_windows({plan:p.plan_id}));'
        program+=' const v=parse(await tools.mcp__literature_evidence__verify_evidence_windows({extraction_id:e.extraction_id}));'
        program+=' return parse(await tools.mcp__literature_evidence__build_evidence_packet({verification_id:v.verification_id}));'
        scenario=task_directory/'scenario.json'
    else:
        program='return await tools.mcp__demo__pin_note({object_id:"note:alpha"});'
        scenario=ROOT/'scenarios/example/scenario.json'
    m.next_fixture_action=lambda values,_: ('run_code',{'code':program,'description':'Free authorized MCP binding probe'}) if not values else (None,{'scope':'protocol_only'})
    handler=m.provider_handler('ptc-probe',with_usage=True,request_limit=8)
    provider=ThreadingHTTPServer(('127.0.0.1',0),handler)
    state=State(cap_usd=.25,output_cap=2000,record=out/'ledger.jsonl',request_limit=8)
    gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{provider.server_port}',state)
    for s in (provider,gate):threading.Thread(target=s.serve_forever,daemon=True).start()
    prepared=prepare_scenario(scenario,tool_presentation='ptc')
    guard=NativeBudgetGuard(max_model_requests=8,max_observed_input_tokens=None)
    try:
        with create_harness(root=ROOT,patches=(prepared['patch'],),env={**extra_env,
            'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key',
            'DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1',
            'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_SCENARIO_PRESENTATION':'ptc',
            'SSS_BUDGET_GATE_ACTIVE':'1','SSS_BUDGET_CAP_USD':'.25','SSS_BUDGET_LEDGER':str(state.record),
            'SSS_CODE_IMAGE':'node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e',
            'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':''},cwd=str(out),runtime_cwd=str(out),
            provider='deepseek-official',model='deepseek-flash',max_tokens=2000,request_timeout_seconds=120) as client:
            result=client.run('Read the authorized note using programmatic MCP calls.',session_id='ptc-'+uuid4().hex,on_notification=guard.on_notification)
        path=out/'events.jsonl';path.write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in result.events));path.chmod(0o600)
        calls=[e for e in result.events if e['type'].startswith('tool/')]
        (out/'requests.json').write_text(json.dumps(handler.calls,ensure_ascii=False));(out/'requests.json').chmod(0o600)
        print(json.dumps({'output':str(out),'finish':result.finish_reason,'requests':len(handler.calls),'event_types':{t:sum(e['type']==t for e in calls) for t in {e['type'] for e in calls}},'paid_calls':0}))
        for e in calls:print(json.dumps(e,ensure_ascii=False)[:1400])
        settled=[e for e in calls if e['type']=='tool/ptc-dispatch']
        assert settled and all(e['data']['isError'] is False for e in settled)
        if evidence_run:
            original=out/'agent-events.jsonl';original.write_bytes(path.read_bytes());original.chmod(0o600)
            delivery=runner.collect_packet(out,task_directory)
            assert delivery['status']=='packet_ready'
            assert json.loads((out/'evidence-packet.json').read_text())==packet
            print(json.dumps({'packet_equal':True,'nested_tool_calls':len(settled),'requests':len(handler.calls),'paid_calls':0}))
        assert result.finish_reason=='completed'
        assert all([t['function']['name'] for t in body['tools']]==['run_code'] for body in handler.calls)
    finally:
        for s in (provider,gate):s.shutdown();s.server_close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence-run',type=Path)
    check(parser.parse_args().evidence_run)
