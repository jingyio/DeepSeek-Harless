"""Free original Harness/MCP preparation dispatch, with a local mock provider."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
from uuid import uuid4
from pdf_tools import ROOT,PdfScene,digest,save_private
from inventory_entry import entry_task,HERE
sys.path.insert(0,str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State,create_server
from src.adapters.native_budget import NativeBudgetGuard
from src.motif_core.offline.entry_compiler import navigation_projection

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def check(task_path,policy,incremental_run=None):
    out=ROOT/'.local/inventory-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
    source=json.loads(task_path.read_text())
    if incremental_run:
        from pdf_incremental_tools import IncrementalScene
        from incremental_entry import entry_task as freeze_entry
        scene=IncrementalScene(incremental_run/'dependencies.json',Path(source['sources']['root']),source,out/'delivery',
            revoked_path=incremental_run/'revoked-claims.json')
    else:
        scene=PdfScene(Path(source['sources']['root']),ROOT/'.local/literature-notes/pdf-cache',source)
        freeze_entry=entry_task
    prompt='Prepare all frozen selected PDFs and return; free protocol diagnostic.'
    task={**freeze_entry(scene,out.name),'session_id':'inventory-check-'+uuid4().hex,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
    save_private(out/'entry-task.json',task);save_private(out/'task.json',source)
    (out/'prompt.md').write_text(prompt);(out/'prompt.md').chmod(0o600)
    config=json.loads((HERE/('pdf-incremental-scenario.json' if incremental_run else 'pdf-scenario.json')).read_text());config.pop('completion_guard',None);config['prompt']=str(out/'prompt.md');save_private(out/'scenario.json',config)
    prepared=prepare_scenario(out/'scenario.json',entry_motif=True)
    mock=load(ROOT/'scripts/motif-example.py','inventory_mock');mock.next_fixture_action=lambda _values,_case:(None,{'scope':'free-protocol-only'})
    handler=mock.provider_handler('inventory-probe',with_usage=True,request_limit=8)
    provider=ThreadingHTTPServer(('127.0.0.1',0),handler);state=State(cap_usd=.25,output_cap=2000,record=out/'ledger.jsonl',request_limit=8)
    gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{provider.server_port}',state)
    for server in (provider,gate):threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with create_harness(root=ROOT,patches=(prepared['patch'],),env={
            'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1',
            'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_SCENARIO_PRESENTATION':'native',
            'SSS_PDF_ROOT':str(scene.root),'SSS_PDF_TASK_FILE':str(out/'task.json'),'SSS_PDF_CACHE':str(scene.cache),
            'SSS_PDF_DELIVERY':str(out/'delivery'),'SSS_PDF_SCRIPT_READ':'0','SSS_PDF_CACHE_POLICY':'reuse',
            'SSS_PDF_DEPENDENCIES':str(incremental_run/'dependencies.json') if incremental_run else '',
            'SSS_PDF_REVOKED':str(incremental_run/'revoked-claims.json') if incremental_run else '',
            'SSS_PDF_INCREMENTAL_OUTPUT':str(out/'delivery'),
            'SSS_ENTRY_MOTIF_POLICY':str(policy),'SSS_ENTRY_MOTIF_TASK':str(out/'entry-task.json'),
            'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':'','SSS_BUDGET_GATE_ACTIVE':'1',
            'SSS_BUDGET_CAP_USD':'.25','SSS_BUDGET_LEDGER':str(state.record)},cwd=str(out),runtime_cwd=str(out),
            provider='deepseek-official',model='deepseek-flash',max_tokens=2000,request_timeout_seconds=120) as client:
            result=client.run(prompt,session_id=task['session_id'],on_notification=NativeBudgetGuard(max_model_requests=8,max_observed_input_tokens=None).on_notification)
        save_private(out/'events.json',result.events);outputs=[]
        for e in result.events:
            if e['type']=='tool/result':
                for b in e['data']['message']['content']:
                    assert not b.get('isError');outputs.append(json.loads(b['content'][0]['text']))
        assert outputs[0]==(scene.read_update_plan() if incremental_run else scene.list_pdfs())
        assert len(outputs)==1+len(task['target_ids'])
        assert {v['paper_id'] for v in outputs[1:]}==set(task['target_ids'])
        for v in outputs[1:]:assert navigation_projection(v)==navigation_projection(scene.prepare_pdf(v['paper_id']))
        assert len(handler.calls)==1
        audit_path=out/'.local/online-motif'/(hashlib.sha256(task['session_id'].encode()).hexdigest()+'.jsonl')
        audits=[json.loads(l) for l in audit_path.read_text().splitlines()]
        report={'output':str(out),'real_api_requests':0,'mock_provider_requests':1,'actual_tool_calls':len(outputs),
            'navigation_replay_equal':True,'retained_pdfs_not_prepared':bool(incremental_run),
            'verified_runtime_batches':sum(a['kind']=='entry_model_request_bypassed_verified' for a in audits)}
        save_private(out/'outcome.json',report);print(json.dumps(report))
    finally:
        for server in (provider,gate):server.shutdown();server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',type=Path,required=True);p.add_argument('--policy',type=Path,required=True)
    p.add_argument('--incremental-run',type=Path);a=p.parse_args();check(a.task.resolve(),a.policy.resolve(),a.incremental_run.resolve() if a.incremental_run else None)
