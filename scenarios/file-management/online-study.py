"""Frozen paired normal Harness / certified read continuation study."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4
from common import ROOT,HERE,DATA,PREFIX,digest,sha,save,snapshot,source_code
from experiment import run_one,accounting,outcomes

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

class RejectEmbedding(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.server.calls+=1
        self.send_response(503);self.end_headers();self.wfile.write(b'No semantic vectors in this study')

def source_versions(spec):
    return sorted({digest({'path':n,'sha':s,'parser':'fm-parser-v1'})
                   for n,s in spec['initial_snapshot'].items() if n!='.experiment-copy'})

def structured_task(spec,stale=False):
    versions=['0'*64] if stale else source_versions(spec)
    return {'schema_version':1,'task_id':spec['task_id'],'session_id':'fm-online-'+uuid4().hex,
            'intent':spec['objective'],'input_version':digest(spec),'bindings':{},
            'source_versions':{PREFIX+'pin_file':versions,PREFIX+'read_file':versions}}

def prepare(parent,families=()):
    original=json.loads((parent/'protocol.json').read_text())
    name='fm-online-20261013-'+uuid4().hex[:8]
    out=ROOT/'.local/file-management'/name;data=DATA/name;out.mkdir(parents=True,mode=0o700)
    data.mkdir(parents=True,mode=0o700)
    old=json.loads((parent/'learned/online-manifest.json').read_text())
    learning=module('fm_online_learning',HERE/'learn.py')
    schema_path=next((Path(original['tasks'][0]['task_dir'])/'attempts').glob('*/tool-schemas.json'))
    schemas=json.loads(schema_path.read_text());raw=learning.contracts(schemas)
    raw={k:{**v,'description':old['contracts'][k]['description'] if k in old['contracts'] else v['description']} for k,v in raw.items()}
    exporter=module('fm_online_export',ROOT/'scripts/export-online-motif-manifest.py')
    library=json.loads((parent/'learned/library.json').read_text())
    manifest=exporter.export_manifest(library,raw,version_fields=old['version_fields'],source_dereferences=(PREFIX+'read_file',))
    without=json.loads(json.dumps(manifest));without['contracts'][PREFIX+'read_file'].pop('source_dereference')
    without['manifest_digest']=digest({k:v for k,v in without.items() if k!='manifest_digest'})
    if without!=old:raise ValueError('capability export changed certified artifacts or other contracts')
    save(out/'online-manifest.json',manifest)
    subprocess.run(['node','--input-type=module','-e',
        "import fs from 'node:fs';import {validateOnlineManifest} from './src/motif_core/online_skill_runtime.mjs';validateOnlineManifest(JSON.parse(fs.readFileSync(process.argv[1])));",str(out/'online-manifest.json')],cwd=ROOT,check=True,capture_output=True)
    tasks=[]
    for i,origin in enumerate(c for c in original['tasks'] if c['role']=='evaluate' and (not families or c['family'] in families)):
        source=json.loads((Path(origin['task_dir'])/'input.json').read_text())
        if snapshot(source['workspace'])!=source['initial_snapshot']:raise ValueError('held-out source changed')
        pair=origin['task_id'];pristine=data/'pristine'/pair;workspace=data/'workspaces'/pair
        shutil.copytree(source['workspace'],pristine);shutil.copytree(pristine,workspace)
        spec={**source,'task_id':pair,'workspace':str(workspace),'task_spec_revision':2}
        if source['family']=='content_search':
            spec['objective']+=' submit_report.file_ids 只列最终命中的结果文件，不列仅处理过或排除的文件；正文说明依据。'
        if source['family']=='rename':
            spec['objective']+=' 编号覆盖全部 inbox 文件，跨扩展名共用一个计数器，不按扩展名重置。'
        spec['rules']={**spec['rules'],'report_file_ids':'selected results for content_search; current relevant files otherwise',
                       'rename_numbering':'one global counter over sorted original inbox paths'}
        for arm in (('H','M') if i%2==0 else ('M','H')):
            tid=pair+'-'+arm;taskdir=out/'tasks'/tid;save(taskdir/'input.json',spec)
            prompt=(HERE/'prompt.md').read_text()+f'\n本次任务 {pair}\n{spec["objective"]}\n'
            taskdir.joinpath('prompt.md').write_text(prompt);taskdir.joinpath('prompt.md').chmod(0o600)
            config=json.loads((Path(origin['task_dir'])/'scenario.json').read_text());config['prompt']=str(taskdir/'prompt.md')
            save(taskdir/'scenario.json',config);save(taskdir/'motif-task.json',structured_task(spec))
            tasks.append({'task_id':tid,'pair_id':pair,'role':'evaluate','family':spec['family'],'variant':spec['variant'],
                          'arm':arm,'input_sha256':digest(spec),'task_dir':str(taskdir),'pristine':str(pristine),
                          'workspace':str(workspace),'initial_snapshot':spec['initial_snapshot']})
    protocol={'experiment_id':name,'state':'frozen','parent':str(parent),'tasks':tasks,
              'model':original['model'],'reasoning_effort':'off','compression_enabled':False,
              'total_cap_usd':1000,'per_task_cap_usd':5,'max_steps':48,'max_output':4000,
              'planned_runs':len(tasks),'study_max_budget_usd':len(tasks)*5,'source_code':source_code(),
              'selected_families':list(families),'selection_reason':'13-source history retention follow-up' if families else 'all 12 workflows',
              'source_library_digest':old['source_library_digest'],'old_manifest_digest':old['manifest_digest'],
              'manifest_digest':manifest['manifest_digest'],'manifest_sha256':sha(out/'online-manifest.json'),
              'task_spec_revision':2,'embedding_policy':'reject every request; no fake vectors',
              'paired_conditions':'byte-identical input/prompt/schema; same workspace path reset from pristine; alternating arms',
              'pricing_checked_url':'https://api-docs.deepseek.com/quick_start/pricing/',
              'accounting':'proxy conservative peak estimate; actual bill unknown',
              'primary_acceptance':'independent file postconditions and actual receipt; no human blind review',
              'limitations':['generated held-out office/PDF files','one run per pair','no arbitrary graph or autonomous writes']}
    save(out/'protocol.json',protocol)
    for filename in protocol['source_code']:
        target=out/'frozen-source'/filename;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/filename,target);target.chmod(0o600)
    save(ROOT/'.local/file-management/online-current.json',{'experiment':str(out)})
    print(json.dumps({'experiment':str(out),'pairs':len(tasks)//2,'planned_runs':len(tasks),'paid':False}),flush=True);return out

def summarize(out):
    rows=[r for r in outcomes() if str(out) in r['attempt']]
    body={'experiment_id':out.name,'attempts':len(rows),'accounting':accounting(),'arms':{},'pairs':[]}
    fields=('upstream_requests','outputTokens','inputTokens','cacheReadTokens',
            'budget_accounted_usd','elapsed_seconds','model_requests_skipped_verified')
    for arm in ('H','M'):
        selected=[r for r in rows if r['arm']==arm]
        body['arms'][arm]={'runs':len(selected),'passed':sum(r['acceptance']['passed'] for r in selected),
                          'completed':sum(r['receipt_verified'] for r in selected),'tool_errors':sum(r['tool_errors'] for r in selected)}
        for field in fields:
            values=[r['run'].get(field,0) for r in selected if r['run']]
            body['arms'][arm][field]={'sum':sum(values),'mean':statistics.mean(values) if values else None}
    for pair in sorted({r['pair_id'] for r in rows}):
        arms={r['arm']:r for r in rows if r['pair_id']==pair}
        if set(arms)!= {'H','M'}:continue
        body['pairs'].append({'pair_id':pair,'family':arms['H']['family'],
            'both_passed':all(r['acceptance']['passed'] for r in arms.values()),
            'H_passed':arms['H']['acceptance']['passed'],'M_passed':arms['M']['acceptance']['passed'],
            'M_minus_H':{f:(arms['M']['run'] or {}).get(f,0)-(arms['H']['run'] or {}).get(f,0) for f in fields}})
    body['paired_runs']=len(body['pairs']);body['qualified_pairs']=sum(r['both_passed'] for r in body['pairs'])
    body['qualified_delta']={f:sum(r['M_minus_H'][f] for r in body['pairs'] if r['both_passed']) for f in fields}
    save(out/'summary.json',body);return body

def main():
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path);p.add_argument('--experiment',type=Path)
    p.add_argument('--call-model',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--summary',action='store_true')
    p.add_argument('--families',nargs='+',choices=['inventory','index','content_search'])
    args=p.parse_args();out=args.experiment.resolve() if args.experiment else prepare(args.parent.resolve(),args.families or ())
    protocol=json.loads((out/'protocol.json').read_text())
    if args.summary:
        result=summarize(out);print(json.dumps({k:v for k,v in result.items() if k!='pairs'},ensure_ascii=False));return
    if not args.call_model:return
    if source_code()!=protocol['source_code'] or sha(out/'online-manifest.json')!=protocol['manifest_sha256']:
        raise ValueError('frozen execution sources changed; prepare another study')
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as stream:stream.write(out.name)
    endpoint=ThreadingHTTPServer(('127.0.0.1',0),RejectEmbedding);endpoint.calls=0
    worker=threading.Thread(target=endpoint.serve_forever,daemon=True);worker.start()
    pending=[c for c in protocol['tasks'] if not list((Path(c['task_dir'])/'attempts').glob('*/outcome.json'))]
    if args.limit:pending=pending[:args.limit]
    try:
        for case in pending:
            root=Path(case['workspace']);pristine=Path(case['pristine'])
            if not root.is_relative_to(DATA/out.name) or not (root/'.experiment-copy').is_file():raise ValueError('unsafe reset scope')
            if snapshot(pristine)!=case['initial_snapshot']:raise ValueError('pristine copy changed')
            shutil.rmtree(root);shutil.copytree(pristine,root)
            before=endpoint.calls
            outcome=run_one(out,case,protocol,call_model=True,
                manifest=out/'online-manifest.json' if case['arm']=='M' else None,
                motif_task=Path(case['task_dir'])/'motif-task.json' if case['arm']=='M' else None,
                embedding_endpoint=f'http://127.0.0.1:{endpoint.server_port}/v1/embeddings')
            retained=DATA/out.name/'retained-final'/case['task_id'];shutil.copytree(root,retained)
            save(Path(outcome['attempt'])/'final-state.json',{'retained':str(retained),'snapshot':snapshot(retained),
                                                          'embedding_requests':endpoint.calls-before})
            result=summarize(out)
            print(json.dumps({'pairs_finished':result['paired_runs'],'qualified_pairs':result['qualified_pairs'],
                              'series_estimated_usd':result['accounting']['estimated_usd'],'embedding_requests':endpoint.calls}),flush=True)
    finally:endpoint.shutdown();endpoint.server_close();worker.join(timeout=5);lock.unlink()

if __name__=='__main__':main()
