"""Five fresh native reference audits, then two frozen Motif evaluations.

Server-only laboratory entry. Default is preview; private input/trajectories stay
in .local. Repeated sessions on one paper do not certify cross-task transfer.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.dsh_client import _usage

OUTPUT_CAP = 32768
PROMPT = ROOT/'scenarios/paper-submission/reference-audit.prompt.md'

def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

budget = load_module('paper_reference_budget',ROOT/'scripts/paper-motif-experiment.py')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    path.chmod(0o600)

POLICY = '''- id: tools
  config:
    mode: native
- id: compaction-basic
  disabled: true
- id: command-compact
  disabled: true
- id: tool-result-pruner
  disabled: true
- id: llm-retry
  disabled: true
- id: session-title-llm
  disabled: true
- id: session-log-deepseek
  disabled: true
- id: session-telemetry-otel
  disabled: true
- id: agent-instructions
  disabled: true
- id: approval
  config:
    policy: never
- id: sandbox-policy
  config:
    mode: danger-full-access
- id: tool-web
  config:
    search: false
    fetch: true
- id: permission
  config:
    defaultPreset: danger-full-access
    presets:
      danger-full-access:
        sandbox: danger-full-access
        approval: never
'''

def snapshot_files(work):
    # For later native read guards, record bytes at actual tool boundaries.
    # Exclude large rendered raster images; no auto-replay of read_image.
    selected={};size=0
    for p in sorted(work.rglob('*')):
        if p.is_symlink():continue
        if not p.is_file() or p.suffix.lower() not in {'.tex','.bib','.cls','.bst','.pdf','.bbl','.log','.md','.txt','.zip','.json','.py'}:continue
        size+=p.stat().st_size
        if len(selected)>=2048 or size>200_000_000:
            return {'complete':False,'files':selected}
        selected[str(p.relative_to(work))]=sha(p)
    return {'complete':True,'files':selected}

def inspect_reports(work):
    found=[]
    for p in sorted(work.rglob('*.pdf')):
        if p.is_symlink():continue
        result=subprocess.run(['pdftotext','-layout',str(p),'-'],capture_output=True,text=True,timeout=30)
        text=result.stdout
        if '参考文献检查报告' in text:
            found.append({'path':str(p.relative_to(work)),'sha256':sha(p),
                          'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                          'text_has_replacement_character':'\ufffd' in text,
                          'text_extraction_exit_code':result.returncode,
                          'pages':text.count('\f'), 'quality_review':'not_reviewed','candidate_only':True,'font_test_only':'测试中文渲染' in text})
    return found

def run(exp, source, index, mode, cap_usd=1):
    label=f'{mode}-{index:02d}';out=exp/'runs'/label
    if out.exists():raise ValueError('run already exists; preserve ledger and use a new run ID')
    rows,prior,ledger_hashes=budget.account(exp)
    if prior>=cap_usd:raise ValueError('cumulative paper budget exhausted')
    work=out/'work';work.mkdir(parents=True,mode=0o700)
    shutil.copyfile(source,work/'submission.zip');(work/'submission.zip').chmod(0o600)
    prompt=PROMPT.read_text();save(out/'prompt.md',prompt);save(out/'native.patch.yml',POLICY)
    session='paper-reference-'+uuid4().hex
    patches=[str(out/'native.patch.yml')]
    env={'DSH_HOME':str(out/'dsh'),'DSH_TELEMETRY_MODE':'none','DSH_MAX_TOKENS_AS_SUCCESS':'false',
         'DSH_PERMISSION_MODE':'danger-full-access','SSS_ONLINE_MOTIF_MANIFEST':'',
         'SSS_ONLINE_MOTIF_TASK':'','SSS_NATIVE_MOTIF_MANIFEST':''}
    if mode=='execute':
        manifest=exp/'native-motifs.json'
        if not manifest.exists():raise ValueError('compile frozen native Motif candidates before evaluation')
        save(out/'motif.patch.yml','- insert:\n    - id: native-paper-motif\n      name: '+json.dumps((ROOT/'src/adapters/dsh_native_motif.ts').as_uri())+'\n')
        patches.append(str(out/'motif.patch.yml'))
        env.update(SSS_NATIVE_MOTIF_MANIFEST=str(manifest),SSS_NATIVE_MOTIF_WORK=str(work),
                   SSS_NATIVE_MOTIF_SESSION=session,SSS_NATIVE_MOTIF_PROMPT_SHA256=sha(PROMPT),
                   SSS_NATIVE_MOTIF_INPUT_SHA256=sha(source))
    config={'experiment_id':exp.name,'run_id':label,'mode':mode,'session_id':session,
            'task_type':'same_paper_repeated_runs','model':'deepseek-flash','provider':'deepseek-official',
            'reasoning_effort':'off','request_limit':None,'output_cap':OUTPUT_CAP,'compression':False,
            'cap_usd':cap_usd,'prior_requests':len(rows),'prior_usd':prior,'prior_ledger_sha256':ledger_hashes,
            'input_sha256':sha(source),'prompt_sha256':sha(PROMPT),'fresh_workspace':True,
            'sandbox':'danger-full-access','approval':'never','patches':{str(Path(p).relative_to(ROOT)):sha(p) for p in patches},
            'python':platform.python_version(),'node':subprocess.check_output(['node','--version'],text=True).strip(),
            'dsh_version':json.loads((ROOT/'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'],
            'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
            'code_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'scripts/paper-motif-experiment.py',ROOT/'src/adapters/harness_runtime.py',ROOT/'src/adapters/deepseek_cost_gate.py',ROOT/'src/adapters/native_motif_compiler.py',ROOT/'src/adapters/dsh_native_motif.ts',ROOT/'src/adapters/dsh_online_motif.mjs',ROOT/'src/motif_core/online_skill_runtime.mjs',ROOT/'package-lock.json']},
            'native_manifest_sha256':sha(exp/'native-motifs.json') if mode=='execute' else None}
    save(out/'manifest.json',config)
    class RecordedState(State):
        def book(self,body):
            row=super().book(body)
            if row:save(out/f'requests/{row[0]:04d}.json',body.decode())
            return row
    state=RecordedState(cap_usd=cap_usd,output_cap=OUTPUT_CAP,request_limit=None,record=out/'cost-ledger.jsonl')
    state.request_count=len(rows);state.reserved_usd=prior
    gate=create_server('127.0.0.1',0,'https://api.deepseek.com',state)
    worker=threading.Thread(target=gate.serve_forever,daemon=True);worker.start()
    guard=NativeBudgetGuard(max_model_requests=None,max_observed_input_tokens=None)
    calls={}
    def observe(n):
        if n.method=='session.event' and isinstance(n.payload.get('event'),dict):
            e=n.payload['event'];p=out/'agent-events.jsonl'
            with p.open('a') as f:f.write(json.dumps(e,ensure_ascii=False)+'\n')
            p.chmod(0o600)
            sid=n.payload.get('sessionId')
            p=out/'session-events.jsonl'
            with p.open('a') as f:f.write(json.dumps({'session_id':sid,'event':e},ensure_ascii=False)+'\n')
            p.chmod(0o600)
            if e['type']=='tool/call':calls[e['data']['callId']]=e['data']
            if e['type']=='tool/result':
                for block in e['data'].get('message',{}).get('content',[]):
                    if block.get('type')=='tool-result':
                        row={'session_id':sid,'call_id':block['toolCallId'],'snapshot':snapshot_files(work)}
                        p=out/'file-versions.jsonl'
                        with p.open('a') as f:f.write(json.dumps(row)+'\n')
                        p.chmod(0o600)
            if e['type']=='step/start':print(json.dumps({'run':label,'step':e['data'].get('step'),'upstream_requests':state.request_count-len(rows),'cumulative_reserved_usd':round(state.reserved_usd,6)}),flush=True)
        guard.on_notification(n)
    env.update(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',SSS_BUDGET_GATE_ACTIVE='1',
               SSS_BUDGET_CAP_USD=str(cap_usd),SSS_BUDGET_LEDGER=str(out/'cost-ledger.jsonl'))
    print(json.dumps({'starting':label,'model':'deepseek-flash','reasoning_effort':'off','prompt_sha256':sha(PROMPT),
                      'cap_usd':cap_usd,'prior_usd':prior,'request_limit':None,'output_cap':OUTPUT_CAP}),flush=True)
    start=time.monotonic();metrics={}
    try:
        with create_harness(root=ROOT,patches=tuple(patches),env=env,provider='deepseek-official',
                            model='deepseek-flash',max_tokens=OUTPUT_CAP,cwd=str(work),runtime_cwd=str(work),
                            request_timeout_seconds=3600) as harness:
            result=harness.run(prompt,session_id=session,on_notification=observe)
        save(out/'answer.md',result.final_response)
        metrics={'status':'completed' if result.finish_reason=='completed' else 'incomplete','finish_reason':result.finish_reason}
    except Exception as exc:
        save(out/'error-private.txt',repr(exc));metrics={'status':'error','error_type':type(exc).__name__}
    finally:
        gate.shutdown();gate.server_close();worker.join(timeout=5)
    reports=inspect_reports(work)
    metrics.update(actual_requests=state.request_count-len(rows),prior_requests=len(rows),
                   cumulative_requests=state.request_count,new_estimated_usd=state.reserved_usd-prior,
                   cumulative_estimated_usd=state.reserved_usd,actual_paid_usd=None,
                   elapsed_seconds=round(time.monotonic()-start,3),usage=_usage(guard.events),
                   tool_calls=dict(Counter(c['name'] for c in calls.values())),reports=reports,
                   input_unchanged=sha(work/'submission.zip')==config['input_sha256'],quality_review='not_reviewed')
    save(out/'metrics.json',metrics);print(json.dumps({'finished':label,**metrics},ensure_ascii=False),flush=True)
    # A model "completed" result does not imply a PDF or qualified audit.
    return metrics

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--experiment-id',required=True)
    parser.add_argument('--phase',choices=['preview','collect','compile','compare'],default='preview')
    parser.add_argument('--call-model',action='store_true');parser.add_argument('--start-index',type=int,default=1)
    parser.add_argument('--budget-usd',type=float,default=1)
    args=parser.parse_args()
    if not 0<args.budget_usd<=10:parser.error('budget-usd must be within (0, 10] and explicitly authorized for paid use')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,80}',args.experiment_id):parser.error('invalid experiment ID')
    exp=ROOT/'.local/paper-reference'/args.experiment_id;exp.mkdir(parents=True,exist_ok=True,mode=0o700)
    source=ROOT/'.local/experiments/paper-native-baseline-20261009-v2/work/submission.zip'
    if args.phase=='preview':
        rows,cost,_=budget.account(exp)
        print(json.dumps({'experiment_id':args.experiment_id,'planned_baselines':5,'planned_execute':2,
                          'model':'deepseek-flash','reasoning_effort':'off','output_cap':OUTPUT_CAP,'request_limit':None,
                          'cap_usd':args.budget_usd,'prior_usd':cost,'prior_requests':len(rows),'input_sha256':sha(source),
                          'prompt_sha256':sha(PROMPT),'paid_enabled':False,'scope':'same_paper_repeated_runs'}));return
    lockdir=ROOT/'.local/paper-motif';lockdir.mkdir(exist_ok=True)
    with exclusive_lock((lockdir/'.budget.lock')) as lock:
        if args.phase=='compile':
            from src.adapters.native_motif_compiler import compile_native_runs
            save(exp/'native-motifs.json',compile_native_runs(exp,sha(PROMPT),sha(source)));return
        if not args.call_model:parser.error('explicit --call-model required')
        if not os.environ.get('DEEPSEEK_API_KEY'):raise ValueError('server credential missing')
        end=5 if args.phase=='collect' else 2
        if not 1<=args.start_index<=end:parser.error('start-index out of range')
        for i in range(args.start_index,end+1):
            metrics=run(exp,source,i,'baseline' if args.phase=='collect' else 'execute',args.budget_usd)
            if metrics['status']!='completed':raise ValueError('run incomplete; inspect before continuing')

if __name__=='__main__':main()
