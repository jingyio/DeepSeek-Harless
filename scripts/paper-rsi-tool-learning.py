"""Server RSI: native Cordis generation -> heldout promotion -> MCP -> live Shadow.

Explicit paid phases; never resets the cumulative paper budget or runs execute.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
import os
import platform
import importlib.metadata
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State,create_server
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
rsi=module('rsi_tool_parent',ROOT/'scripts/paper-citation-rsi.py')
save,sha=rsi.save,rsi.sha
EXP=ROOT/'.local/paper-reference/paper-rsi-tool-learning-20261011-v1'
AUTH=ROOT/'.local/paper-reference/paper-rsi-overnight-20261011-v1/authorized-budget.json'
FILES=['scripts/paper-rsi-tool-learning.py','scripts/paper-rsi-program-check.mjs',
 'src/adapters/paper_rsi_program.ts','src/adapters/dsh_paper_rsi_learning.ts','src/adapters/dsh_paper_rsi_shadow.ts',
 'scenarios/paper-submission/rsi-server.ts','scenarios/paper-submission/rsi-learning.prompt.md',
 'src/adapters/paper_triage_validation.ts','src/adapters/dsh_online_motif.mjs']
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def fixtures():
    def case(label,expected,rows,scope='cited_arxiv_version_triage',current='source-A',version='source-A'):
        return {'id':label,'input':{'expected_pairs':expected,'report':{'scope':scope,'references':rows},
           'current_source_version':current,'expected_source_version':version}}
    def ref(k,i):return {'key':k,'arxiv_id':i}
    train=[case('train-valid',[['a','2501.00001']],[ref('a','2501.00001')]),
      case('train-combined',[['a','2501.00001'],['b','2501.00002']],
       [ref('a','2501.00001'),ref('a','2501.00001'),ref('extra','2501.00003')],current='source-B'),
      case('train-malformed',[],[{'key':'a'}],scope='wrong')]
    held=[case('empty',[],[]),case('different-ids',[['gamma','2310.03714']],[ref('gamma','2310.03714')],current='new',version='new'),
      case('missing',[['x','2409.00001'],['y','2409.00002']],[ref('y','2409.00002')]),
      case('duplicates',[['u','2502.00012']],[ref('u','2502.00012')]*3),
      case('unexpected',[],[ref('z','2410.00007'),ref('z','2410.00007')]),
      case('version-and-scope',[],[],scope='bad',current='changed'),
      case('invalid-array',[],None),case('invalid-entry',[],[None,{'key':42,'arxiv_id':'x'},ref('ok','2601.12345')]),
      case('ordering',[['second','0002'],['first','0001']],[]),
      case('id-conflict',[['samekey','2501.12345']],[ref('samekey','2501.99999')]),
      case('no-report',[],[])]
    held[-1]['input']['report']=None
    for f in train+held:
        i=f['input'];report=i['report'];valid=isinstance(report,dict);rows=report.get('references') if valid else None
        good=[];malformed=not isinstance(rows,list)
        for row in rows if isinstance(rows,list) else []:
            if not isinstance(row,dict) or not all(isinstance(row.get(k),str) for k in ('key','arxiv_id')):malformed=True;continue
            good.append([row['key'],row['arxiv_id']])
        unique=lambda values:list(dict.fromkeys(tuple(x) for x in values))
        expected=[tuple(x) for x in i['expected_pairs']];actual=[tuple(x) for x in good]
        f['expected']={'missing_pairs':[list(p) for p in unique(i['expected_pairs']) if p not in actual],
          'unexpected_pairs':[list(p) for p in unique(good) if p not in expected],
          'duplicate_pairs':[list(p) for p in unique(good) if actual.count(p)>1],
          'source_mismatch':i['current_source_version']!=i['expected_source_version'],
          'scope_mismatch':not valid or report.get('scope')!='cited_arxiv_version_triage','malformed':malformed}
    return train,held
def node(*args):
    return subprocess.run([shutil.which('node'),'--experimental-strip-types',*map(str,args)],cwd=ROOT,check=True,text=True,capture_output=True)
def setup():
    EXP.mkdir(parents=True,exist_ok=True,mode=0o700)
    train,held=fixtures()
    for name,data in [('training.json',train),('heldout.json',held)]:
        path=EXP/name
        if path.exists() and json.loads(path.read_text())!=data:raise ValueError('preserve fixture version')
        if not path.exists():save(path,data)
    return train,held
def paid(label,prompt,policy,config,env_extra):
    auth=rsi.load_budget_record(AUTH);cap=auth['cap_usd']
    record=auth['record']
    local_allowed=(record.get('execution_environment')=='local' and
                   record.get('authorized_root')==str(ROOT.resolve()))
    if (ROOT!=Path('/root/autodl-tmp/jjy') and not local_allowed) or not os.environ.get('DEEPSEEK_API_KEY'):
        raise ValueError('configured_authorized_execution_host_required')
    if config.get('mode')=='execute' and record.get('execute_allowed') is not True:
        raise ValueError('execute_requires_explicit_authorization_record')
    out=EXP/'runs'/label
    if out.exists():raise ValueError('preserve run; use a new explicit label for a retry')
    work=out/'work';work.mkdir(parents=True,mode=0o700)
    config.update(session_id='paper-tool-rsi-'+uuid4().hex,work=str(work),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
    if config.get('seed_report') is not None:save(work/'triage.json',config.pop('seed_report'))
    save(out/'config.json',config);save(out/'patch.yml',rsi.reference.POLICY+policy);save(out/'prompt.md',prompt)
    rows,prior,ledger_snapshots=rsi.reference.budget.account(EXP)
    # A relocation must never lose older server expenditure from its budget.
    prior=max(prior,record.get('prior_estimated_usd',0))
    if prior>=cap:raise ValueError('cumulative paper budget exhausted')
    class Recorded(State):
        def book(self,body):
            result=super().book(body)
            if result:save(out/f'requests/{result[0]:04d}.json',body.decode())
            return result
    state=Recorded(cap_usd=cap,output_cap=8192,request_limit=None,record=out/'cost-ledger.jsonl')
    state.request_count=len(rows);state.reserved_usd=prior
    gate=create_server('127.0.0.1',0,'https://api.deepseek.com',state)
    worker=threading.Thread(target=gate.serve_forever,daemon=True);worker.start()
    env={'DSH_HOME':str(out/'dsh'),'DSH_TELEMETRY_MODE':'none','DSH_MAX_TOKENS_AS_SUCCESS':'false',
      'DSH_PERMISSION_MODE':'danger-full-access','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1',
      'SSS_BUDGET_GATE_ACTIVE':'1','SSS_BUDGET_CAP_USD':str(cap),'SSS_BUDGET_LEDGER':str(out/'cost-ledger.jsonl'),
      **{k:str(out/'config.json') for k in env_extra}}
    versions={'os':platform.platform(),'python':platform.python_version(),
      'python_sdk':importlib.metadata.version('deepseek-harness-sdk'),
      'node':subprocess.check_output([shutil.which('node'),'--version'],text=True).strip(),
      'harness':json.loads((ROOT/'node_modules/@deepseek-ai/dsh/package.json').read_text())['version']}
    save(out/'manifest.json',{'session_id':config['session_id'],'label':label,'model':'deepseek-flash','reasoning_effort':'off',
      'mode':config['mode'],'output_cap':8192,'request_limit':None,'compression':False,'cap_usd':cap,'prior_usd':prior,
      'versions':versions,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
      'authorization':auth,'code_sha256':{p:sha(ROOT/p) for p in FILES},'prior_ledger_sha256':ledger_snapshots,
      'prompt_sha256':config['prompt_sha256'],'config_sha256':sha(out/'config.json'),'patch_sha256':sha(out/'patch.yml')})
    def observe(n):
        if n.method=='session.event':
            with (out/'events.jsonl').open('a') as f:f.write(json.dumps(n.payload,ensure_ascii=False)+'\n')
    start=time.monotonic();print(json.dumps({'starting':label,'prior_usd':prior,'cap_usd':cap,'request_limit':None,'output_cap':8192}),flush=True)
    status='error'
    try:
        with create_harness(root=ROOT,patches=(out/'patch.yml',),env=env,provider='deepseek-official',model='deepseek-flash',
          max_tokens=8192,cwd=str(work),runtime_cwd=str(work),request_timeout_seconds=600) as harness:
            result=harness.run(prompt,session_id=config['session_id'],on_notification=observe)
        save(out/'answer.md',result.final_response);status=result.finish_reason
    except Exception as exc:save(out/'error-private.txt',repr(exc))
    finally:gate.shutdown();gate.server_close();worker.join(timeout=5)
    metrics={'status':status,'actual_requests':state.request_count-len(rows),'new_estimated_usd':state.reserved_usd-prior,
      'cumulative_estimated_usd':state.reserved_usd,'elapsed_seconds':time.monotonic()-start,'actual_model_skips':0,'semantic_quality':'not_reviewed'}
    save(out/'metrics.json',metrics);print(json.dumps({'finished':label,**metrics}),flush=True)
    return out
def learn(label):
    train,_=setup();template=(ROOT/'scenarios/paper-submission/rsi-learning.prompt.md').read_text()
    prompt=template.replace('{{TRAINING}}',json.dumps(train,ensure_ascii=False))
    policy='\n- insert:\n    - name: "@deepseek-ai/dsh-cordis-host-runner"\n      config:\n        vmTimeoutMs: 5000\n    - name: "@deepseek-ai/dsh-tool-cordis"\n    - name: '+json.dumps((ROOT/'src/adapters/dsh_paper_rsi_learning.ts').as_uri())+'\n'
    return paid(label,prompt,policy,{'mode':'learning','training':train},['SSS_PAPER_RSI_LEARNING'])
def events(run):
    return [r['event'] for line in (run/'events.jsonl').read_text().splitlines()
      if (r:=json.loads(line)).get('sessionId')==json.loads((run/'config.json').read_text())['session_id']]
def freeze(label):
    setup();run=EXP/'runs'/label
    if json.loads((run/'metrics.json').read_text())['status']!='completed':raise ValueError('learning did not complete')
    candidate=json.loads((run/'work/current-candidate.json').read_text());ch=digest(candidate)
    audit=[json.loads(s) for s in (run/'work/learning.jsonl').read_text().splitlines()]
    definitions=[]
    for e in events(run):
        if e['type']=='tool/call' and e['data']['name']=='cordis_define':
            args=e['data']['arguments'];args=json.loads(args) if isinstance(args,str) else args
            if args.get('code',{}).get('host'):definitions.append(args['code']['host'])
    train,_=fixtures()
    provenance={'learning_run':label,'session_id':json.loads((run/'config.json').read_text())['session_id'],
      'candidate_sha256':ch,'cordis_source_sha256':digest(definitions),'cordis_definition_count':len(definitions),
      'events_sha256':sha(run/'events.jsonl'),'training_input_sha256':[digest(f['input']) for f in train],
      'development_passed':any(a['kind']=='development_test' and a['candidate_sha256']==ch and a['passed'] for a in audit),
      'trial_observed':any(a['kind']=='trial' and a['candidate_sha256']==ch for a in audit)}
    if not definitions:raise ValueError('model-authored Cordis source missing')
    save(EXP/'provenance.json',provenance)
    result=node(ROOT/'scripts/paper-rsi-program-check.mjs',run/'work/current-candidate.json',EXP/'heldout.json',EXP/'frozen-tool.json',EXP/'provenance.json')
    save(EXP/'heldout-validation.json',json.loads(result.stdout));save(EXP/'cordis-definitions.json',definitions)
    print(result.stdout)
def task(case,mode,label):
    origin=ROOT/'.local/paper-reference/paper-rsi-overnight-20261011-v2'
    inputs=json.loads((origin/'inputs.json').read_text());row=inputs[case];source=Path(row['root'])/'source'
    report=json.loads((origin/'runs'/('baseline-'+case)/'work/triage.json').read_text())
    expected=rsi.scope(inputs,case)[1]
    # Controlled corruption of a private copy, not a claim about the native report.
    if report['references']:report['references']=report['references'][1:]+[copy.deepcopy(report['references'][-1])]
    lib=json.loads((EXP/'frozen-tool.json').read_text())
    prompt='''请修订本任务的论文参考文献分诊报告副本，目标是结构完整、配对覆盖与当前稿件范围一致、没有重复或范围外条目。尽量保留已有科研判断；缺失条目只填明确“待进一步核验”的占位记录，不凭空生成事实、网址、正式版本或修复建议。自行检查修订结果。只操作本任务副本，不检查完整文献真实性，不联网。需要工具时只输出工具调用，最终简短说明结构检查和语义限制。'''
    config={'mode':mode,'library_path':str(EXP/'frozen-tool.json'),'tool_digest':lib['manifest_digest'],
      'candidate_sha256':lib['candidate_sha256'],'expected_pairs':expected,'source_root':str(source),
      'source_files':{str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()},
      'code_files':{str(ROOT/p):sha(ROOT/p) for p in FILES},
      'source_version':rsi.checks.PaperEvidence(inputs,ROOT/'.local').version(case),'seed_report':report}
    if mode=='shadow':config['shadow_library']=str(EXP/'shadow-library.json')
    policy='\n- insert:\n    - name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: paper_rsi\n        transport: stdio\n        failOnStartupError: true\n        command: '+json.dumps(shutil.which('node'))+'\n        args: '+json.dumps(['--experimental-strip-types',str(ROOT/'scenarios/paper-submission/rsi-server.ts')])+'\n        cwd: '+json.dumps(str(ROOT))+'\n        env:\n          SSS_PAPER_RSI_CONFIG: '+json.dumps(str(EXP/'runs'/label/'config.json'))+'\n    - name: '+json.dumps((ROOT/'src/adapters/dsh_paper_rsi_shadow.ts').as_uri())+'\n'
    run=paid(label,prompt,policy,config,['SSS_PAPER_RSI_CONFIG'])
    print(node(ROOT/'scripts/check-paper-rsi-task.mjs',run/'config.json').stdout)
    return run
def compile_shadow():
    witnesses=[];tools=None
    for label in ['baseline-main','baseline-abstract']:
        run=EXP/'runs'/label
        if json.loads((run/'metrics.json').read_text())['status']!='completed' or not json.loads((run/'structural-validation.json').read_text())['passed']:raise ValueError('normal successful baselines required')
        requests=sorted((run/'requests').glob('*.json'));schemas=json.loads(requests[0].read_text())['tools']
        view=[{'name':t['function']['name'],'parameters':t['function']['parameters']} for t in schemas]
        if tools is not None and tools!=view:raise ValueError('tool schema/order drift')
        tools=view
        es=events(run);assistant=[e for e in es if e['type']=='assistant/message'];results={}
        for e in es:
            if e['type']!='tool/result':continue
            for block in e['data']['message']['content']:
                if block.get('type')!='tool-result' or block.get('isError'):continue
                try:results[block['toolCallId']]=json.loads(''.join(c.get('text','') for c in block.get('content',[]) if c.get('type')=='text'))
                except (ValueError,KeyError):continue
        for a,b in zip(assistant,assistant[1:]):
            anchor_content=a['data']['message']['content'];next_content=b['data']['message']['content']
            calls=[c for c in anchor_content if c['type']=='tool-call'];nxt=[c for c in next_content if c['type']=='tool-call']
            if len(calls)==1 and calls[0]['type']=='tool-call' and calls[0]['name']=='mcp__paper_rsi__write_report' and len(nxt)==1 and nxt[0]['type']=='tool-call' and nxt[0]['name']=='mcp__paper_rsi__check_report_structure':
                args=nxt[0]['arguments'];args=json.loads(args) if isinstance(args,str) else args
                written=results.get(calls[0]['id'],{});checked=results.get(nxt[0]['id'],{})
                cfg=json.loads((run/'config.json').read_text())
                if args=={} and written.get('source_version')==checked.get('source_version')==cfg['source_version'] and \
                   written.get('candidate_sha256')==checked.get('candidate_sha256')==cfg['candidate_sha256'] and \
                   written.get('report_sha256')==checked.get('report_sha256') and written.get('report_sha256'):
                    witnesses.append({'run':label,'session_id':cfg['session_id'],'input_sha256':digest(cfg['expected_pairs']),
                     'anchor_step':a['data']['step'],'next_step':b['data']['step'],'report_sha256':written['report_sha256'],
                     'check_output_sha256':digest(checked['output']),'events_sha256':sha(run/'events.jsonl'),
                     'next_has_visible_text':any(c['type']=='text' and c.get('text','').strip() for c in next_content)})
    if len({w['session_id'] for w in witnesses})<2:raise ValueError('no repeated model-request boundary; keep tool but do not invent Motif')
    graph={'anchor':'mcp__paper_rsi__write_report','next':'mcp__paper_rsi__check_report_structure','arguments':{}}
    body={'schema_version':1,'execution_policy':'shadow_only','tool_digest':json.loads((EXP/'frozen-tool.json').read_text())['manifest_digest'],
      'tools':tools,'motifs':[dict(graph,motif_id='learned-check-'+digest(graph)[:12],witnesses=witnesses)]}
    path=EXP/'shadow-library.json'
    if path.exists():raise ValueError('preserve frozen Shadow library')
    save(path,dict(body,manifest_digest=digest(body)));print(json.dumps({'motifs':1,'witnesses':len(witnesses)}))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['preview','learn','freeze','baseline','compile','shadow'],default='preview')
    ap.add_argument('--label',default='learn-v01');ap.add_argument('--case',choices=['t01_main','t02_abstract','t03_subset_a'],default='t01_main');ap.add_argument('--call-model',action='store_true');a=ap.parse_args()
    if a.phase=='preview':
        _,prior,_=rsi.reference.budget.account(EXP);print(json.dumps({'paid_enabled':False,'cap_usd':rsi.load_budget_record(AUTH)['cap_usd'],'cumulative_estimated_usd':prior}));return
    if a.phase=='freeze':freeze(a.label);return
    if a.phase=='compile':compile_shadow();return
    if not a.call_model:raise ValueError('paid phase requires --call-model')
    lock=ROOT/'.local/paper-motif/.budget.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(lock) as f:
        if a.phase=='learn':learn(a.label)
        else:task(a.case,a.phase,a.label)
if __name__=='__main__':main()
