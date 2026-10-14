"""Server paper Motif diagnostic: real traces -> mined edges -> shadow/execute.

Defaults to preview. Controlled fixtures certify protocol only, never scientific
quality or independent human research decisions. All data remains in .local.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State, create_server, reservation
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.dsh_client import _usage
from src.adapters.scenario import prepare_scenario
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance, mine_witnessed_parameter_edges
from src.motif_core.offline.edge_compiler import compile_witnessed_edge_motif, certify_witnessed_edge_motif
from src.motif_core.offline.library_builder import library_from_certified, _digest

PREFIX = 'mcp__paper_checks__'
KINDS = ('sources', 'build', 'pdf')
PRIOR = ['paper-native-baseline-20261009-v1/cost-ledger.jsonl',
         'paper-native-baseline-20261009-v2/cost-ledger.jsonl',
         'paper-native-baseline-20261009-v2/cost-ledger-finish.jsonl',
         'paper-ptc-baseline-20261009-v1/cost-ledger.jsonl',
         'paper-ptc-baseline-20261009-v1/cost-ledger-finish.jsonl']


def load(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.write_text(text); path.chmod(0o600)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


CHECKS = module('paper_checks', ROOT/'scenarios/paper-submission/checks.py')


def contracts():
    rows = {}
    for kind in KINDS:
        for pin in (True, False):
            name = PREFIX + (f'pin_paper_{kind}' if pin else f'read_pinned_paper_{kind}')
            rows[name] = {'required_params': ['case_id' if pin else 'source_id'],
                          'read_only': True, 'replay_stable': True,
                          'output_fields': ['source_id', 'version_sha256'] if pin else ['version_sha256'],
                          'provenance_params': [] if pin else ['source_id'],
                          'description': ('固定已授权论文的版本化' if pin else '读取固定论文的只读') + kind + '诊断视图。'}
    return rows


def prepare(exp: Path, private_case: Path | None):
    if (exp/'inputs.json').exists(): return load(exp/'inputs.json')
    inputs = {}
    template = r'''\documentclass{article}
\title{TITLE}\author{Diagnostic Fixture}
\begin{document}\maketitle
BODY
\bibliographystyle{plain}\bibliography{references}
\end{document}
'''
    bodies = {'fixture_clear': r'Known source~\cite{known}. Equation~\ref{eq:a}.\begin{equation}\label{eq:a}x=1\end{equation}',
              'fixture_missing': r'Compare known~\cite{known} and missing~\cite{unknown}.',
              'fixture_labels': r'Source~\cite{known}; Equation~\ref{eq:a}.\begin{equation}\label{eq:a}x=1\end{equation}\begin{equation}\label{eq:a}y=2\end{equation}'}
    for case, body in bodies.items():
        directory = exp/'inputs'/case; source = directory/'source'; build = directory/'build'
        source.mkdir(parents=True, mode=0o700); build.mkdir(mode=0o700)
        save(source/'main.tex', template.replace('TITLE', case).replace('BODY', body))
        save(source/'references.bib', '@article{known, author={Fixture, A.}, title={Controlled evidence}, journal={Fixture Journal}, year={2026}, volume={1}, pages={1--2}}\n')
        for file in source.iterdir(): shutil.copyfile(file, build/file.name)
        steps = []
        for index, command in enumerate([['pdflatex', '-no-shell-escape', '-interaction=nonstopmode', 'main.tex'],
                                         ['bibtex', 'main'],
                                         ['pdflatex', '-no-shell-escape', '-interaction=nonstopmode', 'main.tex'],
                                         ['pdflatex', '-no-shell-escape', '-interaction=nonstopmode', 'main.tex']]):
            result = subprocess.run(command, cwd=build, capture_output=True, text=True, timeout=120)
            save(build/f'step-{index}.txt', result.stdout+result.stderr)
            steps.append({'engine': command[0], 'command': command, 'exit_code': result.returncode})
        if not (build/'main.pdf').exists(): raise ValueError('fixture did not produce a PDF')
        save(directory/'build-record.json', {'kind':'controlled_fixture_preparation','steps':steps})
        inputs[case] = {'root':str(directory), 'source_dir':'source', 'main':'main.tex',
                        'pdf':'build/main.pdf','log':'build/main.log','bbl':'build/main.bbl',
                        'build_record':'build-record.json','task_kind':'controlled_fixture'}
    if private_case:
        private_case = private_case.resolve(strict=True)
        if not private_case.is_relative_to(ROOT/'.local'): raise ValueError('private input must be under .local')
        # Prepared PTC evidence is copied, not executed, repaired or used to train.
        directory = exp/'inputs/private_paper'; directory.mkdir(mode=0o700)
        shutil.copytree(private_case/'work/build/extracted', directory/'source')
        for src, dst in [('work/build/out/main.pdf','main.pdf'),
                         ('work/artifacts/logs/final-main.log','main.log'),
                         ('work/artifacts/logs/final-main.bbl','main.bbl')]:
            shutil.copyfile(private_case/src, directory/dst)
        inputs['private_paper']={'root':str(directory),'source_dir':'source','main':'main.tex',
                                 'pdf':'main.pdf','log':'main.log','bbl':'main.bbl',
                                 'task_kind':'private_prepared_evidence'}
        # Exit codes are not invented from log/PDF existence; unavailable here.
    save(exp/'inputs.json',inputs);save(exp/'contracts.json',contracts())
    return inputs


def account(exp):
    # A new experiment ID must not reset the cumulative paper budget.
    paths = [ROOT/'.local/experiments'/name for name in PRIOR]
    for category in ('paper-motif', 'paper-reference'):
        base = ROOT/'.local'/category
        runs = {p.parent for p in base.glob('*/runs/*/cost-ledger.jsonl')}
        runs.update(p.parent.parent for p in base.glob('*/runs/*/requests/*.json')
                    if p.stem.isdigit())
        paths.extend(run/'cost-ledger.jsonl' for run in sorted(runs))
    # A recorded request is durable proof of booking even if the process died
    # before its terminal usage row was written. Never release that reservation
    # merely because a new experiment ID is selected.
    rows = []; snapshots = {}
    for path in paths:
        booked = {}
        for line in (path.read_text().split('\n') if path.exists() else []):
            if not line.strip(): continue
            row = json.loads(line); request_id = row.get('request_id')
            if request_id is None: continue
            previous = booked.get(request_id)
            if previous is None or row.get('observed_peak_usd') is not None:
                booked[request_id] = row
        if path.exists(): snapshots[str(path.relative_to(ROOT))] = sha(path)
        # Only these controllers name durable receipts with State.book IDs.
        # Older experiments have local sequence numbers in request filenames;
        # their preserved ledgers remain authoritative, not these filenames.
        receipts = (sorted((path.parent/'requests').glob('*.json'))
                    if path.is_relative_to(ROOT/'.local/paper-reference')
                    or path.is_relative_to(ROOT/'.local/paper-motif') else [])
        for request in receipts:
            if not request.stem.isdigit(): continue
            request_id = int(request.stem)
            if request_id in booked: continue
            body = request.read_bytes(); payload = json.loads(body)
            model, upper, _ = reservation(body, max_output=payload['max_tokens'])
            booked[request_id] = {'request_id': request_id, 'model': model,
                'observed_peak_usd': None, 'reserved_upper_usd': upper,
                'accounting_status': 'booked_without_terminal_usage'}
            snapshots[str(request.relative_to(ROOT))] = sha(request)
        rows.extend(booked.values())
    cost = sum(row.get('observed_peak_usd') if row.get('observed_peak_usd') is not None
               else row['reserved_upper_usd'] for row in rows)
    return rows, cost, snapshots


def question(case):
    goal = {'fixture_clear':'判断干净合成短稿的引用、编译与 PDF 字体证据是否完整。',
            'fixture_missing':'定位合成短稿未知引用键，并核对其编译与 PDF 结果。',
            'fixture_labels':'核对另一份合成稿的重复公式标签，以及编译与 PDF 字体证据。',
            'private_paper':'检查私人论文既有编译产物、活动源码引用/标签及 PDF 字体诊断。'}[case]
    return f'''{goal} 当前唯一授权 case_id 是 {case}。
请自主使用提供的只读 MCP 获取 sources、build、pdf 三类证据，依据事实给出简洁中文报告。
这些是已准备的版本化证据：本轮不重新编译、不修改原稿、不判断会议合规或文献真实性。
明确区分未知退出码、日志事实与视觉判断；没有页面视觉工具，不得声称视觉验收。
不要推测未读取的视图；source_id 必须来自实际工具返回。最终答复列出关键诊断及覆盖限制，控制在 1500 字内。'''


def run(exp, inputs, case, mode, label):
    out=exp/'runs'/label
    if out.exists(): raise ValueError('run ID already exists; do not reset budget or overwrite results')
    out.mkdir(parents=True,mode=0o700)
    rows, prior_cost, ledger_hashes = account(exp)
    if prior_cost >= 1: raise ValueError('cumulative paper budget exhausted')
    row=inputs[case];save(out/'inputs.json',{case:row});save(out/'prompt.md',question(case))
    allowed=list(contracts())
    scenario={'schema_version':1,'name':'paper_checks','prompt':str(out/'prompt.md'),
              'servers':[{'server_name':'paper_checks','transport':'stdio','command':'${PYTHON}',
                          'args':['${PROJECT_ROOT}/scenarios/paper-submission/server.py'],
                          'cwd':'${PROJECT_ROOT}', 'env':{'SSS_PAPER_INPUTS':str(out/'inputs.json')}}],
              'allowed_tools':allowed}
    save(out/'scenario.json',scenario); prepared=prepare_scenario(out/'scenario.json')
    version=CHECKS.PaperEvidence({case:row},ROOT/'.local').version(case)
    session='paper-motif-'+uuid4().hex
    policy='''- id: tools
  config:
    mode: native
- id: compaction-basic
  disabled: true
- id: command-compact
  disabled: true
- id: tool-result-pruner
  disabled: true
'''
    save(out/'policy.patch.yml',policy)
    patches=[prepared['patch'],str(out/'policy.patch.yml')]
    env={'DSH_HOME':str(out/'dsh'),'DSH_TELEMETRY_MODE':'none','DSH_MAX_TOKENS_AS_SUCCESS':'false',
         'SSS_SCENARIO_TOOLS':json.dumps(allowed),'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':''}
    if mode!='baseline':
        task={'schema_version':1,'task_id':label,'session_id':session,'intent':question(case).splitlines()[0],
              'input_version':version,'bindings':{PREFIX+f'pin_paper_{k}':{'case_id':case} for k in KINDS},
              'source_versions':{name:version for name in allowed}}
        save(out/'task.json',task)
        patch='- insert:\n    - id: paper-motif\n      name: '+json.dumps((ROOT/'src/adapters/dsh_paper_motif.ts').as_uri())+'\n'
        save(out/'motif.patch.yml',patch);patches.append(str(out/'motif.patch.yml'))
        env.update(SSS_PAPER_MOTIF_DIAGNOSTIC='1',SSS_ONLINE_MOTIF_MANIFEST=str(exp/'online-manifest.json'),
                   SSS_ONLINE_MOTIF_TASK=str(out/'task.json'),SSS_ONLINE_MOTIF_MODE=mode,
                   SSS_ONLINE_MOTIF_PROMPT_SHA256=prepared['prompt_sha256'])
    snapshot={'task_id':label,'question':question(case),'case_id':case,'task_kind':row['task_kind'],
              'mode':mode,'session_id':session,'input_version':version,'reasoning_effort':'off',
              'provider':'deepseek-official','model':'deepseek-flash','output_cap':3000,'request_limit':None,
              'compression':False,'execution_scope':'read_only_prepared_evidence',
              'budget_cap_usd':1.0,'prior_accounted_usd':prior_cost,'prior_requests':len(rows),
              'prior_ledger_sha256':ledger_hashes,'tool_order':allowed,'prompt_sha256':prepared['prompt_sha256'],
              'patches':{str(Path(x).relative_to(ROOT)):sha(x) for x in patches},
              'python':platform.python_version(),'node':subprocess.check_output(['node','--version'],text=True).strip(),
              'dsh_version':load(ROOT/'node_modules/@deepseek-ai/dsh/package.json')['version'],
              'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'worktree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
              'code_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'scenarios/paper-submission/checks.py',ROOT/'scenarios/paper-submission/server.py',ROOT/'src/adapters/dsh_paper_motif.ts',ROOT/'src/adapters/dsh_online_motif.mjs']},
              'motif_manifest_sha256':sha(exp/'online-manifest.json') if mode!='baseline' else None}
    save(out/'manifest.json',snapshot)
    class RecordedState(State):
        def book(self, body):
            booked=super().book(body)
            if booked:save(out/f'requests/{booked[0]:04d}.json',body.decode())
            return booked
    state=RecordedState(cap_usd=1.0,output_cap=3000,request_limit=None,record=out/'cost-ledger.jsonl')
    state.reserved_usd=prior_cost;state.request_count=len(rows)
    gate=create_server('127.0.0.1',0,'https://api.deepseek.com',state)
    worker=threading.Thread(target=gate.serve_forever,daemon=True);worker.start()
    env.update(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',SSS_BUDGET_GATE_ACTIVE='1',
               SSS_BUDGET_CAP_USD='1.0',SSS_BUDGET_LEDGER=str(out/'cost-ledger.jsonl'))
    guard=NativeBudgetGuard(max_model_requests=None,max_observed_input_tokens=None)
    def observe(notification):
        if notification.method=='session.event' and isinstance(notification.payload.get('event'),dict):
            with (out/'agent-events.jsonl').open('a') as f:f.write(json.dumps(notification.payload['event'],ensure_ascii=False)+'\n')
            (out/'agent-events.jsonl').chmod(0o600)
        guard.on_notification(notification)
    print(json.dumps({'run':label,'mode':mode,'model':'deepseek-flash','reasoning_effort':'off',
                      'request_limit':None,'output_cap':3000,'prior_usd':prior_cost,'cap_usd':1.0}),flush=True)
    start=time.monotonic()
    try:
        with create_harness(root=ROOT,patches=tuple(patches),env=env,provider='deepseek-official',
                            model='deepseek-flash',max_tokens=3000,cwd=str(out),runtime_cwd=str(out),
                            request_timeout_seconds=600) as harness:
            result=harness.run(question(case),session_id=session,on_notification=observe)
        save(out/'answer.md',result.final_response)
        metrics={'status':'completed' if result.finish_reason=='completed' and result.final_response.strip() else 'incomplete',
                 'finish_reason':result.finish_reason}
    except Exception as exc:
        save(out/'error-private.txt',repr(exc));metrics={'status':'error','error_type':type(exc).__name__}
    finally:
        gate.shutdown();gate.server_close();worker.join(timeout=5)
    audit=out/'.local/online-motif'/f'{hashlib.sha256(session.encode()).hexdigest()}.jsonl'
    decisions=[json.loads(l) for l in audit.read_text().splitlines()] if audit.exists() else []
    trace=extract_dsh_trace(guard.events,parse_tool_contracts(contracts()),trace_id=label,
                            task_fingerprint='diagnostic-'+version,
                            provenance_by_call_id=infer_dsh_provenance(guard.events,parse_tool_contracts(contracts())))
    read_names={r.name for r in trace.records if r.eligible and 'read_pinned' in r.name}
    pin_cases=[r.arguments.get('case_id') for r in trace.records if r.eligible and r.name.startswith(PREFIX+'pin_')]
    metrics.update(elapsed_seconds=round(time.monotonic()-start,3),actual_model_requests=state.request_count-len(rows),
                   prior_requests=len(rows),cumulative_requests=state.request_count,
                   new_estimated_usd=state.reserved_usd-prior_cost,cumulative_estimated_usd=state.reserved_usd,
                   actual_paid_usd=None,usage=_usage(guard.events),
                   motif_skips_verified=sum(r['kind']=='model_request_skipped_verified' for r in decisions),
                   shadow_candidates=sum(r['kind']=='shadow_candidate' for r in decisions),
                   tool_calls=dict(Counter(r.name for r in trace.records)),
                   all_views_read=read_names=={PREFIX+f'read_pinned_paper_{k}' for k in KINDS},
                   only_requested_case=bool(pin_cases) and all(v==case for v in pin_cases),
                   source_unchanged=CHECKS.PaperEvidence({case:row},ROOT/'.local').version(case)==version,
                   quality_review='not_blind_reviewed')
    save(out/'metrics.json',metrics);print(json.dumps({'run':label,**metrics}),flush=True)
    if metrics['status']!='completed' or not metrics['all_views_read'] or not metrics['only_requested_case']:
        raise ValueError('run incomplete or evidence coverage failed; preserve and inspect before continuing')


def compile_library(exp):
    trace_rows=[];identities=[];parsed=parse_tool_contracts(contracts())
    for case in ('fixture_clear','fixture_missing','fixture_labels'):
        directory=exp/'runs'/('collect-'+case);manifest=load(directory/'manifest.json')
        if manifest['task_kind']!='controlled_fixture': raise ValueError('controlled fixture scope required')
        events=[json.loads(l) for l in (directory/'agent-events.jsonl').read_text().splitlines()]
        identities.append({'case_id':case,'input_version':manifest['input_version'],
                           'question_sha256':hashlib.sha256(manifest['question'].encode()).hexdigest(),
                           'events_sha256':sha(directory/'agent-events.jsonl')})
        trace_rows.append(extract_dsh_trace(events,parsed,trace_id=directory.name,
                         task_fingerprint='diagnostic-'+manifest['input_version'],
                         provenance_by_call_id=infer_dsh_provenance(events,parsed)))
    if len({r['input_version'] for r in identities})!=3 or len({r['question_sha256'] for r in identities})!=3:
        raise ValueError('controlled cases must have distinct source and task identities')
    schemas={}
    for case in ('fixture_clear','fixture_missing','fixture_labels'):
        request_files=sorted((exp/'runs'/('collect-'+case)/'requests').glob('*.json'))
        if not request_files:raise ValueError('real model request schemas missing')
        for request_file in request_files:
            for tool in load(request_file).get('tools',[]):
                function=tool.get('function',{});name=function.get('name')
                hashed=_digest(function.get('parameters'))
                if name not in parsed or (name in schemas and schemas[name]!=hashed):
                    raise ValueError('unknown or changed tool schema in training')
                schemas[name]=hashed
    if set(schemas)!=set(parsed):raise ValueError('incomplete real tool schema evidence')
    candidates=mine_witnessed_parameter_edges(trace_rows[:2]);artifacts=[];rejected=[]
    for candidate in candidates:
        try:
            artifacts.append(certify_witnessed_edge_motif(
                compile_witnessed_edge_motif(candidate,trace_rows[:2],parsed),trace_rows[2],parsed))
        except ValueError as exc:rejected.append({'candidate':candidate,'reason':str(exc)})
    if not artifacts:raise ValueError('no witnessed edge passed controlled heldout validation')
    library=library_from_certified(artifacts)
    library.update(certification_scope='protocol_diagnostic',controlled_identity_evidence=identities,
                   tool_schema_hashes=schemas)
    library['library_digest']=_digest({k:v for k,v in library.items() if k!='library_digest'})
    exporter=module('paper_export',ROOT/'scripts/export-online-motif-manifest.py')
    online=exporter.export_manifest(library,contracts(),
             slot_rules={PREFIX+f'pin_paper_{k}':{'case_id':'[a-z][a-z0-9_]{1,39}'} for k in KINDS},
             version_fields={name:'version_sha256' for name in contracts()})
    save(exp/'library.json',library);save(exp/'online-manifest.json',online)
    save(exp/'mining.json',{'candidates':candidates,'rejected':rejected,'certification_scope':'protocol_diagnostic'})
    print(json.dumps({'compiled_motifs':len(artifacts),'scope':'protocol_diagnostic',
                      'library_digest':library['library_digest']}),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--experiment-id',required=True)
    parser.add_argument('--phase',choices=['preview','prepare','collect','compile','compare'],default='preview')
    parser.add_argument('--private-case',type=Path);parser.add_argument('--call-model',action='store_true')
    args=parser.parse_args()
    if not __import__('re').fullmatch(r'[a-z0-9][a-z0-9-]{2,80}',args.experiment_id):parser.error('invalid experiment ID')
    exp=ROOT/'.local/paper-motif'/args.experiment_id;exp.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.phase=='preview':
        print(json.dumps({'experiment_id':args.experiment_id,'scope':'protocol_diagnostic','model':'deepseek-flash',
                          'reasoning_effort':'off','cap_usd':1,'request_limit':None,'output_cap':3000,
                          'phases':['prepare','collect','compile','compare'],'paid_enabled':False}));return 0
    with exclusive_lock((exp.parent/'.budget.lock')) as lock:
        if args.phase=='prepare':prepare(exp,args.private_case);return 0
        inputs=load(exp/'inputs.json')
        if args.phase=='compile':compile_library(exp);return 0
        if not args.call_model:parser.error('real API phase requires explicit --call-model')
        if not os.environ.get('DEEPSEEK_API_KEY'):raise ValueError('missing server credential; value is never printed')
        if args.phase=='collect':
            for case in ('fixture_clear','fixture_missing','fixture_labels'):run(exp,inputs,case,'baseline','collect-'+case)
        else:
            if 'private_paper' not in inputs:raise ValueError('private paper evaluation input not prepared')
            for mode in ('baseline','shadow','execute'):run(exp,inputs,'private_paper',mode,'eval-'+mode)
    return 0

if __name__=='__main__':raise SystemExit(main())
