"""Free actual SDK/MCP stale execute rejection, then local simulated ordinary stop."""
import argparse,json,sys,threading
from pathlib import Path
from uuid import uuid4
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
import workflow_holdout as h
import script_adaptation_study as s
from common import save,sha,digest,snapshot,PREFIX
from src.adapters.file_scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
parser=argparse.ArgumentParser();parser.add_argument('--experiment',type=Path,required=True);args=parser.parse_args();exp=args.experiment.resolve();p=json.loads((exp/'protocol.json').read_text())
class StopProvider(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  b=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.bodies.append(b)
  base={'id':'mock-version','created':1,'model':b['model'],'object':'chat.completion.chunk'}
  chunks=[{**base,'choices':[{'index':0,'delta':{'role':'assistant','content':'Local simulated ordinary fallback: external version changed; stop with unfinished delivery, no new writes or restored unknown bytes.'},'finish_reason':None}]},
          {**base,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]},
          {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
  data=(''.join('data: '+json.dumps(v)+'\n\n' for v in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
def check(wid):
 c=next(c for c in p['tasks'] if c['role']=='certify' and c['workflow_id']==wid and c['layout_changed'] and c['profile_id']==wid+(':'+('max' if wid=='FM05' else 'filtered')))
 out,spec,env,_=h.instantiate(exp,c,p,True);s.bind(exp,c,p,out,spec,env,True);prepared=prepare_scenario(Path(c['task_dir'])/'scenario.json')
 save(out/'stale-control.json',{'target':c['control']['target'],'before_sha256':c['control']['before_sha256'],'marker':str(out/'stale-marker.json'),'workspace':spec['workspace'],'workflow_id':wid})
 plugin=out/'stale-preview.ts';runtime=(ROOT/'src/motif_core/online_skill_runtime.mjs').as_uri()
 plugin.write_text("import {readFileSync,writeFileSync,existsSync} from 'node:fs';import {resolve,sep} from 'node:path';import {createHash} from 'node:crypto';import {observation} from '"+runtime+"';\nexport const name='sss-free-stale-preview';export const inject=['agents'];export function apply(ctx:any){const c=JSON.parse(readFileSync(process.env.SSS_FREE_STALE_CONTROL!,'utf8'));const target=resolve(c.workspace,c.target);if(!target.startsWith(resolve(c.workspace)+sep)||!existsSync(resolve(c.workspace,'.experiment-copy')))throw Error('marked copy required');ctx.on('agent/created',({agent}:any)=>agent.ctx.on('tools/result',(exec:any,result:any)=>{if(existsSync(c.marker))return;const o=observation(result,exec.name);if(exec.name!=='mcp__file_management__preview_actions'||o?.status!=='validated_copy_plan'||(c.workflow_id==='FM17'&&!o.actions.some((a:any)=>a.destination.startsWith('recovery-drill/'))))return;const hash=()=>createHash('sha256').update(readFileSync(target)).digest('hex');if(hash()!==c.before_sha256)throw Error('frozen preimage changed');writeFileSync(target,'DECLARED FREE STALE VERSION');writeFileSync(c.marker,JSON.stringify({target:c.target,before_sha256:c.before_sha256,after_sha256:hash(),boundary_call_id:exec.callId}));}));}\n")
 patch=out/'stale.patch.yml';save(patch,[{'insert':[{'id':'sss-free-stale-preview','name':plugin.as_uri()},{'id':'sss-learned-copy-script-v2','name':(ROOT/'src/adapters/dsh_learned_script_v2.ts').as_uri()}]}])
 server=ThreadingHTTPServer(('127.0.0.1',0),StopProvider);server.bodies=[];worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 env.update(DEEPSEEK_API_KEY='mock-no-key',DEEPSEEK_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',DSH_HOME=str(out/'dsh'),SSS_FREE_STALE_CONTROL=str(out/'stale-control.json'),SSS_SCENARIO_PRESENTATION='native',SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']))
 for n in ['SSS_ONLINE_MOTIF_MANIFEST','SSS_ONLINE_MOTIF_TASK','SSS_ENTRY_MOTIF_POLICY','SSS_ENTRY_MOTIF_TASK','SSS_TERMINAL_MOTIF_POLICY','SSS_TERMINAL_MOTIF_TASK','SSS_COLLECTION_MOTIF_POLICY','SSS_COLLECTION_MOTIF_TASK','SSS_COLLECTION_SCRIPT','SSS_COLLECTION_SCRIPT_TASK','SSS_REENTRY_MOTIF_POLICY','SSS_REENTRY_MOTIF_TASK','SSS_PLAN_MOTIF_POLICY','SSS_PLAN_MOTIF_TASK','SSS_DURABLE_PLAN_BINDING']:env[n]=''
 guard=NativeBudgetGuard(max_model_requests=96,max_observed_input_tokens=None);failure=None;finish=None
 try:
  try:
   with create_harness(root=ROOT,patches=(prepared['patch'],str(patch)),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=15) as client:
    result=client.run(prepared['prompt'],session_id='stale-sdk-'+uuid4().hex,on_notification=guard.on_notification);finish=result.finish_reason
  except Exception as e:failure=type(e).__name__+': '+str(e)
  save(out/'events.json',guard.events);save(out/'mock-requests.json',server.bodies)
  audit=[json.loads(l) for l in (out/'script-audit.jsonl').read_text().splitlines()];assert any(r['kind']=='script_v2_deferred' and r['reason']=='unexpected_or_failed_actual_tool' for r in audit)
  execute=[e for e in guard.events if e['type']=='tool/call' and e['data']['name']==PREFIX+'execute_plan'];last=execute[-1];cid=last['data']['callId'];assert cid.startswith('sss-script-v2-')
  rejection=next(e for e in guard.events if e['type']=='tool/result' and any(b.get('toolCallId')==cid and b.get('isError') for b in e['data']['message'].get('content',[])))
  assert not any(e['type']=='tool/call' and e['seq']>rejection['seq'] and e['data']['callId'].startswith('sss-') for e in guard.events)
  repairs=[e for e in guard.events if e['type']=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair'];assert len(repairs)==2 and len(server.bodies)==3
  assert any(e['type']=='assistant/message' and e['seq']>rejection['seq'] and e['data']['message'].get('source',{}).get('kind')=='model' for e in guard.events)
  marker=json.loads((out/'stale-marker.json').read_text());expected=dict(spec['initial_snapshot'])
  if wid=='FM17':
   for n in spec['workflow_contract']['source_paths']:
    f=Path(spec['workspace'])/n
    if f.suffix.lower()=='.txt' and f.stat().st_size==0:continue
    expected['backup-set/'+n[len('source/'):]]=spec['initial_snapshot'][n]
  expected[marker['target']]=marker['after_sha256'];assert snapshot(spec['workspace'])==expected
  review=h.verify_workflow(spec,None,out/'delivery',guard.events);assert not review['passed'] and not h.receipt_from(guard.events)
  v={'status':'passed','workflow_id':wid,'actual_sdk_and_mcp':True,'actual_stale_execute_rejected':True,'script_permanently_deferred':True,'ordinary_fallback_simulated':True,'unknown_bytes_preserved':True,'acceptance_repairs':len(repairs),'mock_http_requests':len(server.bodies),'real_api_requests':0,'delivery_completed':False,'not_training':True,'finish_reason':finish,'expected_termination':failure,'output':str(out),'plugin_sha256':sha(plugin),'patch_sha256':sha(patch),'check_source_sha256':sha(__file__)};save(out/'stale-sdk-outcome.json',v);print(json.dumps(v),flush=True);return v
 except Exception as e:save(out/'stale-sdk-outcome.json',{'status':'failed','error':str(e),'output':str(out),'real_api_requests':0});raise
 finally:server.shutdown();server.server_close();worker.join(timeout=5)
rows=[check(w) for w in ('FM05','FM17')];save(exp/'free-stale-v2-sdk-summary.json',{'checks':2,'passed':2,'real_api_requests':0,'results':rows})
