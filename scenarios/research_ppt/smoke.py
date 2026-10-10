"""免费验证真实 Harness/MCP、PPTX、轨迹编译与有界 RSI；Provider 为显式模拟。"""
from __future__ import annotations
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import threading
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scenarios.research_ppt.cli import prepare, scenario_for, save, learn, structural_only_endpoint
from scenarios.research_ppt.tests.test_service import write_pdf
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.native_budget import NativeBudgetGuard


def script(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/name)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def observations(messages):
    result=[]
    for message in messages:
        if message.get('role')!='tool': continue
        try: value=json.loads(message.get('content',''))
        except (TypeError,ValueError): continue
        if isinstance(value,dict): result.append(value)
    return result


def fixture_provider(improve=False):
    class Provider(BaseHTTPRequestHandler):
        calls=[]
        failures=[]
        def log_message(self,*_): pass
        def do_POST(self):
            try:
                if self.path!='/v1/chat/completions' or len(self.calls)>=12:
                    raise ValueError('unexpected fixture request or request limit')
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.calls.append(body)
                values=observations(body['messages'])
                name,args=None,{}
                if improve:
                    status=next((x for x in values if 'candidate_schema' in x),None)
                    proposals=[x for x in values if 'proposal_id' in x]
                    if status is None: name='rsi_status'
                    elif not proposals: name,args='propose_guard',{'program':{'schema_version':1,'formats':['pdf','pptx'],'min_text_chars':100,'max_pages':200}}
                    elif not proposals[-1]['accepted']: name,args='propose_guard',{'program':{'schema_version':1,'formats':['pdf','pptx'],'min_text_chars':20,'max_pages':200}}
                    else: args={'guard_accepted':True,'program_digest':proposals[-1]['program_digest']}
                else:
                    pin=next((x for x in values if 'source_id' in x and 'text_chars' in x),None)
                    read=next((x for x in values if 'pages' in x),None)
                    rendered=next((x for x in values if 'deck_id' in x),None)
                    # render/inspect 都携带 deck_id；用检查结果的实际 scope 区分。
                    inspected=next((x for x in values if 'editable_text_runs' in x
                        and x.get('scope') == 'package_and_editability_checks; visual_and_scientific_quality_not_certified'),None)
                    if pin is None: name,args='pin_source',{'document_id':'doc_1'}
                    elif read is None: name,args='read_source',{'source_id':pin['source_id']}
                    elif rendered is None:
                        source={'source_id':read['source_id'],'page':1}
                        plan={'title':'Protocol fixture','slides':[
                            {'title':'Source evidence','bullets':[read['pages'][0]['text'].strip()[:140]],'sources':[source]},
                            {'title':'Validation scope','bullets':['This fixture checks editable output and execution protocol.'],'sources':[source]}]}
                        name,args='render_deck',{'plan':plan}
                    elif inspected is None: name,args='inspect_deck',{'deck_id':rendered['deck_id']}
                    else: args={'path':rendered['path'],'slides':inspected['slide_count'],'editable':inspected['each_slide_has_editable_text'],
                                'source_version':pin['version_sha256']}
                delta={'role':'assistant'}
                if name:
                    delta['tool_calls']=[{'index':0,'id':'fixture-'+str(len(self.calls)),'type':'function',
                        'function':{'name':'mcp__ppt__'+name,'arguments':json.dumps(args)}}]
                else: delta['content']=json.dumps(args)
                base={'id':'fixture','created':1,'model':body['model'],'object':'chat.completion.chunk'}
                chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                        {**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if name else 'stop'}]},
                        {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':30,'total_tokens':130}}]
                answer=(''.join('data: '+json.dumps(chunk)+'\n\n' for chunk in chunks)+'data: [DONE]\n\n').encode()
                self.send_response(200); self.send_header('Content-Type','text/event-stream')
                self.send_header('Content-Length',str(len(answer))); self.end_headers(); self.wfile.write(answer)
            except Exception as exc:
                self.failures.append(str(exc)); self.send_error(500)
    return Provider


def acceptance(workspace:Path, job:Path, *, mode='baseline', manifest=None, stale=False, improve=False):
    out=workspace/('run-'+uuid4().hex); out.mkdir()
    prepared=prepare_scenario(scenario_for(job,improve))
    handler=fixture_provider(improve)
    session='ppt-fixture-'+uuid4().hex
    save(out/'manifest.json',{'task_id':session,'question':prepared['prompt'],'fixture':True})
    # 每个 fixture 含完整的 list/pin/read/render/inspect 循环；测试桩仍需有界，
    # 但 12 次不足以覆盖单次 Harness 会话的所有重试与工具回合。
    guard=NativeBudgetGuard(max_model_requests=32,max_observed_input_tokens=None)
    state=State(cap_usd=1,output_cap=2000,record=out/'cost-ledger.jsonl')
    with ThreadingHTTPServer(('127.0.0.1',0),handler) as provider, structural_only_endpoint() as embeddings:
        gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{provider.server_port}',state)
        servers=(provider,gate)
        workers=[threading.Thread(target=s.serve_forever,daemon=True) for s in servers]
        for worker in workers: worker.start()
        env={'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'local-fixture-only','SSS_PPT_JOB':str(job),
             'DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1',
             'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),
             'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':''}
        patches=[prepared['patch']]
        try:
            if mode!='baseline':
                expected_version = json.loads(job.read_text(encoding='utf-8'))['inputs'][0]['version_sha256']
                task={'schema_version':1,'task_id':session,'session_id':session,'intent':'Read the supplied research document to prepare slides',
                      'input_version':hashlib.sha256(job.read_bytes()).hexdigest(),'bindings':{},
                      'source_versions':{'mcp__ppt__pin_source':'0'*64 if stale else expected_version,
                                         'mcp__ppt__read_source':'0'*64 if stale else expected_version}}
                save(out/'task.json',task)
                online=script('prepare-online-motif.py').prepare(manifest,out/'task.json')
                patches.append(online['patch'])
                env.update(SSS_ONLINE_MOTIF_MANIFEST=online['manifest'],SSS_ONLINE_MOTIF_TASK=online['task'],
                           SSS_ONLINE_MOTIF_MODE=mode,SSS_ONLINE_MOTIF_PROMPT_SHA256=prepared['prompt_sha256'],
                           SSS_MOTIF_EMBEDDING_ENDPOINT=embeddings,SSS_MOTIF_EMBEDDING_MODEL='structural-only')
            with create_harness(root=ROOT,patches=tuple(patches),env=env,cwd=str(out),runtime_cwd=str(out),
                                provider='deepseek-official',model='deepseek-flash',max_tokens=2000,request_timeout_seconds=120) as harness:
                result=harness.run(prepared['prompt'],session_id=session,on_notification=guard.on_notification)
            (out/'agent-events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in result.events),encoding='utf-8')
            if handler.failures or result.finish_reason!='completed':
                raise ValueError('Harness fixture failed; inspect private events at '+str(out))
            answer=json.loads(result.final_response)
            if any({t['function']['name'] for t in body['tools']} != set(prepared['allowed_tools']) for body in handler.calls):
                raise AssertionError('unexpected tool surface')
            audit=out/'.local/online-motif'/(hashlib.sha256(session.encode()).hexdigest()+'.jsonl')
            decisions=[json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
            metrics={'mode':mode,'stale':stale,'improve':improve,'run_dir':str(out),'model_requests':state.request_count,
                'verified_bypasses':sum(row['kind']=='model_request_skipped_verified' for row in decisions),
                'shadow_candidates':sum(row['kind']=='shadow_candidate' for row in decisions),
                'paid_model_requests':0,'provider':'local_fixture','answer':answer}
            save(out/'metrics.json',metrics)
            return metrics
        finally:
            for server in servers: server.shutdown()
            gate.server_close()
            for worker in workers: worker.join(timeout=2)


def main():
    workspace=ROOT/'.local/research-ppt/smoke'/uuid4().hex
    workspace.mkdir(parents=True)
    jobs=[]
    for index in range(4):
        source=workspace/f'fixture-{index+1}.pdf'
        write_pdf(source,f'Research fixture {index+1}: evidence must retain source version {index+1}.')
        job=prepare([source],f'Protocol fixture {index+1}: present this independent synthetic evidence.',2,True,True)
        data=json.loads(job.read_text()); data['rsi_dir']=str(workspace/'rsi'); save(job,data)
        jobs.append(job)
    training=[acceptance(workspace,job) for job in jobs[:3]]
    freeze=script('freeze-dsh-task-identity.py').freeze
    for index,row in enumerate(training):
        freeze(Path(row['run_dir']),f'ppt-protocol-fixture-{index+1}','agent-events.jsonl')
    dataset=workspace/'dataset.json'
    save(dataset,{'train':[x['run_dir'] for x in training[:2]],'heldout':[training[2]['run_dir']]})
    manifest=learn(dataset)
    baseline=acceptance(workspace,jobs[3])
    execute=acceptance(workspace,jobs[3],mode='execute',manifest=manifest)
    shadow=acceptance(workspace,jobs[3],mode='shadow',manifest=manifest)
    stale=acceptance(workspace,jobs[3],mode='execute',manifest=manifest,stale=True)
    rsi=acceptance(workspace,jobs[3],improve=True)
    assert execute['verified_bypasses']>0 and execute['model_requests']<baseline['model_requests'],(baseline,execute)
    assert shadow['shadow_candidates']>0 and shadow['verified_bypasses']==0
    assert stale['verified_bypasses']==0 and stale['model_requests']==baseline['model_requests']
    for row in (baseline,execute,shadow,stale):
        assert row['answer']['editable'] and row['answer']['slides']==2
        assert row['answer']['source_version']==baseline['answer']['source_version']
    assert rsi['answer']['guard_accepted']
    feedback=[json.loads(line) for line in (workspace/'rsi/feedback.jsonl').read_text().splitlines()]
    assert [row['accepted'] for row in feedback]==[False,True]
    report={'status':'passed','scope':'synthetic_protocol_only','paid_model_requests':0,
            'workspace':str(workspace),'manifest':str(manifest),'checks':[baseline,execute,shadow,stale,rsi]}
    save(workspace/'report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
