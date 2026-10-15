"""Run normal Harness tasks, retain attempts and account for the whole authorized series."""
from __future__ import annotations
import argparse
import asyncio
import importlib.util
import json
import os
import platform
import importlib.metadata
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from mcp import Client,StdioServerParameters
from common import ROOT,HERE,PREFIX,digest,save,sha,source_code
from verify import verify

async def inspect_schema(env,server_path=None):
    child=dict(env);child.pop('DEEPSEEK_API_KEY',None)
    async with Client(StdioServerParameters(command=sys.executable,args=[str(server_path or HERE/'file_tools.py')],cwd=ROOT,env=child)) as client:
        tools=await client.list_tools()
        task=await client.call_tool('read_task',{})
        if task.is_error: raise ValueError('MCP task preflight failed')
        return [t.model_dump(mode='json') for t in tools.tools]

def current():
    return Path(json.loads((ROOT/'.local/file-management/current.json').read_text())['experiment'])

def outcomes():
    return [json.loads(p.read_text()) for p in (ROOT/'.local/file-management').glob('*/tasks/*/attempts/*/outcome.json')]

def accounting():
    rows=outcomes()
    if any(r.get('accounting_complete') is not True for r in rows):
        raise ValueError('an earlier attempt has unknown cost; reconcile before further paid calls')
    legacy_runs={str(Path(v['output_dir']).resolve()) for r in rows for v in r.get('runs',[r.get('run') or {}]) if v.get('output_dir')}
    continuous=[json.loads(p.read_text()) for p in (ROOT/'.local/rsi').glob('*/records/*.json')]
    continuous=[r for r in continuous if r['provider_mode']=='real' and str(Path(r['run_dir']).resolve()) not in legacy_runs]
    for r in continuous:
        if r['accounting_complete']:continue
        path=Path(r['origin']).parent.parent/'cost-reconciliations'/(r['session_id']+'.json')
        review=json.loads(path.read_text()) if path.exists() else {}
        record_file=Path(r['origin']).parent.parent/'records'/(r['session_id']+'.json')
        ledger=Path(r['run_dir'])/'cost-ledger.jsonl'
        if (not review.get('accounting_complete') or review.get('record_sha256')!=sha(record_file)
                or review.get('ledger_sha256')!=sha(ledger)):
            raise ValueError('continuous task has unresolved API usage')
    return {'attempts':len(rows)+len(continuous),'upstream_requests':sum((r.get('run') or {}).get('upstream_requests',0) for r in rows)+sum(r['upstream_requests'] for r in continuous),
            'estimated_usd':sum((r.get('run') or {}).get('budget_accounted_usd',0) for r in rows)+sum(r['cost_usd'] for r in continuous),
            'actual_bill_verified':False}

def run_one(exp,case,protocol,*,call_model=False,manifest=None,motif_task=None,embedding_endpoint=None,
            server_path=None,verify_result=verify,collection_policy=None,collection_task=None,collection_script=None,collection_script_task=None,plan_policy=None,plan_task=None,reentry_policy=None,reentry_task=None):
    taskdir=Path(case['task_dir']); spec=json.loads((taskdir/'input.json').read_text())
    if digest(spec)!=case['input_sha256']: raise ValueError('frozen task changed')
    env={**os.environ,'FM_TASK_FILE':str(taskdir/'input.json'),'FM_OUTPUT':str(taskdir/'preflight')}
    schemas=asyncio.run(inspect_schema(env,server_path))
    if not call_model:
        print(json.dumps({'task_id':case['task_id'],'tools':len(schemas),'paid':False}));return
    earlier=list((taskdir/'attempts').glob('*/outcome.json')) if (taskdir/'attempts').is_dir() else []
    if earlier: raise ValueError('prior attempt retained; explicitly prepare a new experiment for retries')
    budget=accounting(); cap=min(protocol['per_task_cap_usd'],protocol['total_cap_usd']-budget['estimated_usd'])
    if cap<=0: raise ValueError('authorized series budget exhausted')
    attempt=taskdir/'attempts'/uuid4().hex[:12]; attempt.mkdir(parents=True,mode=0o700)
    save(attempt/'tool-schemas.json',schemas); save(attempt/'source-code.json',source_code())
    mode='execute' if manifest else 'baseline'
    save(attempt/'config.json',{'model':protocol['model'],'reasoning_effort':'off','mode':mode,
                              'arm':case.get('arm','H'),'manifest_sha256':sha(manifest) if manifest else None,
                              'motif_task_sha256':sha(motif_task) if motif_task else None,
                              'collection_policy_sha256':sha(collection_policy) if collection_policy else None,
                              'collection_task_sha256':sha(collection_task) if collection_task else None,
                              'collection_script_sha256':sha(collection_script) if collection_script else None,
                              'collection_script_task_sha256':sha(collection_script_task) if collection_script_task else None,
                              'plan_policy_sha256':sha(plan_policy) if plan_policy else None,'plan_task_sha256':sha(plan_task) if plan_task else None,
                              'reentry_policy_sha256':sha(reentry_policy) if reentry_policy else None,'reentry_task_sha256':sha(reentry_task) if reentry_task else None,
                              'embedding_model':'disabled','min_similarity':0.8,'min_margin':0.1,
                              'task_sha256':digest(spec),'schema_sha256':digest(schemas),'budget_usd':cap,
                              'series_before':budget,'max_steps':protocol['max_steps'],'max_output':protocol['max_output'],
                              'python':platform.python_version(),'os':platform.platform(),
                              'node':subprocess.check_output(['node','--version'],text=True).strip(),
                              'packages':{n:importlib.metadata.version(n) for n in ['deepseek-harness-sdk','mcp','Pillow']},
                              'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()})
    loader_spec=importlib.util.spec_from_file_location('fm_key_loader',ROOT/'scenarios/literature-notes/run-live.py')
    loader=importlib.util.module_from_spec(loader_spec);loader_spec.loader.exec_module(loader)
    env['DEEPSEEK_API_KEY']=loader.load_key(loader.KEY_FILE,env)
    env['FM_OUTPUT']=str(attempt/'delivery')
    cmd=[sys.executable,str(ROOT/'scripts/run-scenario.py'),'--scenario',str(taskdir/'scenario.json'),
         '--model',protocol['model'],'--mode',mode,'--budget-usd',str(cap),
         '--max-steps',str(protocol['max_steps']),'--max-output',str(protocol['max_output']),'--call-model']
    if manifest:
        if not motif_task or not embedding_endpoint:raise ValueError('online configuration missing')
        cmd+=['--manifest',str(manifest),'--task',str(motif_task),
              '--embedding-endpoint',embedding_endpoint,'--embedding-model','disabled']
    if collection_policy:
        if manifest or not collection_task:raise ValueError('collection configuration must be independent')
        cmd+=['--collection-policy',str(collection_policy),'--collection-task',str(collection_task)]
    if collection_script:
        if manifest or collection_policy or not collection_script_task:raise ValueError('script must be independent')
        cmd+=['--collection-script',str(collection_script),'--collection-script-task',str(collection_script_task)]
    if plan_policy:
        if manifest or collection_policy or collection_script or not plan_task:raise ValueError('plan motif must be independent')
        cmd+=['--plan-policy',str(plan_policy),'--plan-task',str(plan_task)]
    if reentry_policy:
        if manifest or collection_policy or collection_script or plan_policy or not reentry_task:raise ValueError('L2 reentry must be independent')
        cmd+=['--reentry-policy',str(reentry_policy),'--reentry-task',str(reentry_task)]
    print(json.dumps({'starting':case['task_id'],'budget_cap_usd':cap,'series_cap_usd':protocol['total_cap_usd']}),flush=True)
    result=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)
    for name,value in [('stdout.txt',result.stdout),('stderr.txt',result.stderr)]:
        p=attempt/name;p.write_text(value,encoding='utf-8');p.chmod(0o600)
    summary=None
    for line in result.stdout.splitlines():
        try:
            value=json.loads(line)
            if isinstance(value,dict) and 'output_dir' in value: summary=value
        except ValueError: pass
    events=[];receipt=None
    if summary:
        run_dir=Path(summary['output_dir'])
        p=run_dir/'agent-events.jsonl'
        if p.is_file():events=[json.loads(line) for line in p.read_text().splitlines()]
        calls={e['data']['callId']:e['data']['name'] for e in events if e.get('type')=='tool/call'}
        for e in events:
            if e.get('type')!='tool/result':continue
            for b in e['data']['message'].get('content',[]):
                if b.get('type')=='tool-result' and not b.get('isError') and calls.get(b.get('toolCallId'))==PREFIX+'submit_report':
                    receipt=json.loads(b['content'][0]['text'])
    report_path=attempt/'delivery/report.json'; report=json.loads(report_path.read_text()) if report_path.is_file() else None
    receipt_ok=bool(receipt and report and receipt.get('artifact_sha256')==digest(report)
                    and receipt.get('input_sha256')==digest(spec) and Path(receipt['artifact'])==report_path)
    try:
        review=verify_result(spec,report if receipt_ok else None,attempt/'delivery',events)
    except Exception as exc:
        review={'passed':False,'errors':['acceptance verifier raised '+type(exc).__name__],
                'verifier_exception':str(exc),'human_blind_review':False}
    tool_errors=[{'seq':e['seq'],'block':b} for e in events if e.get('type')=='tool/result'
                 for b in e['data']['message'].get('content',[]) if b.get('isError')]
    outcome={'task_id':case['task_id'],'role':case['role'],'family':case['family'],'attempt':str(attempt),
             'arm':case.get('arm','H'),'pair_id':case.get('pair_id'),
             'run':summary,'returncode':result.returncode,'receipt_verified':receipt_ok,
             'acceptance':review,'tool_errors':len(tool_errors),'accounting_complete':bool(summary),
             'events_sha256':sha(Path(summary['output_dir'])/'agent-events.jsonl') if summary and events else None}
    save(attempt/'tool-errors.json',tool_errors);save(attempt/'outcome.json',outcome)
    print(json.dumps({'finished':case['task_id'],'status':(summary or {}).get('status'),'passed':review['passed'],
                      'errors':review['errors'],'tool_errors':len(tool_errors),
                      'requests':(summary or {}).get('upstream_requests'),
                      'estimated_usd':(summary or {}).get('budget_accounted_usd')},ensure_ascii=False),flush=True)
    return outcome

def summarize(exp):
    rows=[r for r in outcomes() if str(exp) in r['attempt']]
    body={'experiment_id':exp.name,'attempts':len(rows),'completed':sum(bool(r.get('receipt_verified')) for r in rows),
          'passed':sum(r['acceptance']['passed'] for r in rows),'tool_errors':sum(r['tool_errors'] for r in rows),
          'accounting':accounting(),'outcomes':rows,'online_motif_enabled':False}
    save(exp/'summary.json',body);return body

def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path);p.add_argument('--role',choices=['explore','certify','evaluate'],default='explore')
    p.add_argument('--case');p.add_argument('--limit',type=int);p.add_argument('--call-model',action='store_true');p.add_argument('--summary',action='store_true')
    args=p.parse_args();exp=(args.experiment or current()).resolve();protocol=json.loads((exp/'protocol.json').read_text())
    if args.summary:
        s=summarize(exp);print(json.dumps({k:v for k,v in s.items() if k!='outcomes'}));return
    selected=[c for c in protocol['tasks'] if c['role']==args.role and (not args.case or c['task_id']==args.case)]
    selected=[c for c in selected if not list((Path(c['task_dir'])/'attempts').glob('*/outcome.json'))]
    if args.limit:selected=selected[:args.limit]
    if not selected:raise ValueError('no unrun tasks selected')
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:
        for case in selected:
            run_one(exp,case,protocol,call_model=args.call_model)
            if args.call_model:summarize(exp)
    finally:lock.unlink()

if __name__=='__main__':main()
