"""Free actual Harness/MCP check of learned entry dispatch; mock provider only."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
from uuid import uuid4
from pdf_tools import ROOT,digest,save_private
from pdf_repair_tools import RepairScene
sys.path.insert(0,str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State,create_server
from src.adapters.native_budget import NativeBudgetGuard

def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def check(run,policy):
 out=ROOT/'.local/entry-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
 loader=module(Path(__file__).parent/'learn-entry.py','entry_check_loader')
 scene=RepairScene(run,out/'scene-output');task=loader.entry_task(scene)
 prompt='Read only the frozen claim packets; this is a free protocol diagnostic, not a scientific review.'
 save_private(out/'task.json',{**task,'session_id':'entry-check-'+uuid4().hex,'prompt_sha256':__import__('hashlib').sha256(prompt.encode()).hexdigest()})
 (out/'prompt.md').write_text(prompt);(out/'prompt.md').chmod(0o600)
 config=json.loads((Path(__file__).parent/'pdf-repair-scenario.json').read_text());config.pop('completion_guard');config['prompt']=str(out/'prompt.md');save_private(out/'scenario.json',config)
 prepared=prepare_scenario(out/'scenario.json',entry_motif=True)
 mock=module(ROOT/'scripts/motif-example.py','entry_check_provider');mock.next_fixture_action=lambda _values,_case:(None,{'scope':'free-protocol-only'})
 handler=mock.provider_handler('entry-probe',with_usage=True,request_limit=8)
 provider=ThreadingHTTPServer(('127.0.0.1',0),handler);state=State(cap_usd=.25,output_cap=2000,record=out/'ledger.jsonl',request_limit=8)
 gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{provider.server_port}',state)
 for s in (provider,gate):threading.Thread(target=s.serve_forever,daemon=True).start()
 budget=NativeBudgetGuard(max_model_requests=8,max_observed_input_tokens=None)
 try:
  task=json.loads((out/'task.json').read_text())
  with create_harness(root=ROOT,patches=(prepared['patch'],),env={
   'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1',
   'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_SCENARIO_PRESENTATION':'native',
   'SSS_PDF_REPAIR_RUN':str(run),'SSS_PDF_REPAIR_OUTPUT':str(out/'scene-output'),
   'SSS_ENTRY_MOTIF_POLICY':str(policy),'SSS_ENTRY_MOTIF_TASK':str(out/'task.json'),
   'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':'',
   'SSS_BUDGET_GATE_ACTIVE':'1','SSS_BUDGET_CAP_USD':'.25','SSS_BUDGET_LEDGER':str(state.record)},
   cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=2000,request_timeout_seconds=120) as client:
   result=client.run(prompt,session_id=task['session_id'],on_notification=budget.on_notification)
  events=result.events;save_private(out/'events.json',events)
  calls=[e for e in events if e['type']=='tool/call'];outputs=[]
  for e in events:
   if e['type']=='tool/result':
    for b in e['data']['message']['content']:
     assert not b.get('isError');outputs.append(json.loads(b['content'][0]['text']))
  assert len(calls)==len(scene.targets),(len(calls),len(scene.targets))
  assert {v['claim_id'] for v in outputs}==set(scene.targets)
  for v in outputs:assert digest(v)==digest(scene.read_claim_repair_packet(v['claim_id']))
  assert len(handler.calls)==1,len(handler.calls)
  audit_path=out/'.local/online-motif'/(__import__('hashlib').sha256(task['session_id'].encode()).hexdigest()+'.jsonl')
  audits=[json.loads(l) for l in audit_path.read_text().splitlines()]
  report={'output':str(out),'scope':'free real Harness/MCP, mock provider; no scientific or paid efficiency claim',
   'real_api_requests':0,'mock_provider_requests':len(handler.calls),'actual_entry_reads':len(calls),
   'packets_equal_to_current_replay':True,'verified_runtime_batches':sum(a['kind']=='entry_model_request_bypassed_verified' for a in audits)}
  save_private(out/'outcome.json',report);print(json.dumps(report))
 finally:
  for s in (provider,gate):s.shutdown();s.server_close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--policy',type=Path,required=True);a=p.parse_args();check(a.run.resolve(),a.policy.resolve())
