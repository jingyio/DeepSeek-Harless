"""Independent native training, edge certification and paired window-task experiments."""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4
from pdf_tools import ROOT,digest,inventory,save_private
from pdf_dependencies import private_file
from pdf_window_tools import HERE,WindowScene,window_version
sys.path.insert(0,str(ROOT))
from src.adapters.dsh_trajectory import extract_dsh_trace,infer_dsh_provenance,mine_witnessed_parameter_edges
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.adapters.task_identity import load_trace_identity,require_distinct_decisions
from src.motif_core.offline.edge_compiler import compile_witnessed_edge_motif,certify_witnessed_edge_motif,count_safe_edge_witnesses
from src.motif_core.offline.library_builder import library_from_certified

import importlib.util
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
runner=module('window_probe_runner',HERE/'explore-workflows.py')
PREFIX=runner.PREFIX


def code_snapshot():
    paths=[HERE/n for n in ('pdf_window_tools.py','pdf-window-contracts.json','pdf-window-scenario.json','pdf-window-task.md',
        'workflow_probe_tools.py','pdf_tools.py','pdf_layout.py','pdf_read_plan.py','explore-workflows.py','window-study.py')]
    paths += [ROOT/n for n in ('scripts/run-scenario.py','scripts/export-online-motif-manifest.py',
        'src/adapters/dsh_online_motif.mjs','src/motif_core/online_skill_runtime.mjs',
        'src/motif_core/offline/edge_compiler.py','src/adapters/dsh_trajectory.py')]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def prepare():
    out=ROOT/'.local/literature-notes'/('window-continuation-20261012-'+uuid4().hex[:8]);out.mkdir(mode=0o700,parents=True)
    save_private(out/'protocol.json',{'experiment_id':out.name,'state':'preparing','budget_per_task_usd':.25,'max_steps':32,
        'model':'deepseek-flash','reasoning_effort':'off','training':3,'evaluation_runs':12,
        'purpose':'reuse existing batched edge mechanism for new document retrieval tasks','shared_core_changes':False})
    original=inventory(ROOT/'testpdf');subsets={}
    for name,selected in [('three',original['papers']),('two',original['papers'][:2]),('one',original['papers'][2:3])]:
        papers=out/('papers-'+name);papers.mkdir(mode=0o700)
        for row in selected:
            destination=papers/row['filename'];shutil.copyfile(Path(original['root'])/row['filename'],destination);destination.chmod(0o600)
        subsets[name]=inventory(papers)
    definitions=[
        ('train-mechanisms','train','three','各篇论文如何划分模型判断、工具执行和可执行验证？找出相关方法段及其适用条件。'),
        ('train-measurements','train','two','各篇论文怎样评估工具执行的准确性或可靠性？查找实验设计与报告的限制，不将机制等同效果。'),
        ('certify-boundaries','certify','one','这篇论文的自我改进依赖哪些可验证性与可恢复性前提？找到原文依据并解释适用边界。'),
        ('eval-orchestration','evaluate','three','比较各篇论文中任务编排、执行反馈和验证器的作用，指出哪些步骤由模型选择、哪些有程序约束。'),
        ('eval-cost-evidence','evaluate','two','寻找各篇论文关于工具成本、效率或失败恢复的证据，区分测量结果、机制设计和未验证推测。'),
    ]
    cases=[]
    for name,role,subset,question in definitions:
        work=out/name;work.mkdir(mode=0o700)
        spec={'schema_version':1,'kind':'topic_search','task':{'schema_version':1,'question':question,'sources':subsets[subset]},
              'citations':[],'network_check_enabled':False}
        prompt=work/'prompt.md';prompt.write_text((HERE/'pdf-window-task.md').read_text()+'\n本次研究问题（仍须核对实际工具任务）：\n'+question+'\n');prompt.chmod(0o600)
        config=json.loads((HERE/'pdf-window-scenario.json').read_text());config['prompt']=str(prompt)
        save_private(work/'input.json',spec);save_private(work/'scenario.json',config)
        cases.append({'name':name,'role':role,'input_sha256':digest(spec),'paper_count':len(subsets[subset]['papers']),
                      'config_sha256':digest(config)})
    schedule=[]
    for case in [c for c in cases if c['role']=='evaluate']:
        for repeat in range(1,4):
            for arm in (['H','M'] if repeat%2 else ['M','H']):
                name=case['name']+'-'+str(repeat)+'-'+arm;work=out/name;work.mkdir(mode=0o700)
                for file in ('input.json','scenario.json'):shutil.copyfile(out/case['name']/file,work/file);(work/file).chmod(0o600)
                schedule.append({'name':name,'case':case['name'],'repeat':repeat,'arm':arm,'input_sha256':case['input_sha256']})
    sources=code_snapshot()
    for name,sha in sources.items():
        destination=out/'source-code'/name;destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        destination.write_bytes((ROOT/name).read_bytes());destination.chmod(0o600)
    protocol=json.loads((out/'protocol.json').read_text());protocol.update(state='frozen',cases=cases,schedule=schedule,
        sources=sources,window_version=window_version(),runtime=module('window_runtime',HERE/'run-pdf.py').runtime_snapshot(),
        original_sources=original,learned_edge_only=True,comparison='ordinary native Harness versus existing witnessed-edge Motif',
        budget_total_cap_usd=3.75,compression=False,provider_cache='uncontrolled; fixed tool set and alternating order',
        scientific_support_verified=False,corpus_scope='three known development PDFs, no independent corpus generalization')
    save_private(out/'protocol.json',protocol);save_private(ROOT/'.local/literature-notes/window-study-current.json',{'experiment':str(out)})
    return out


def validate(out):
    protocol=json.loads((out/'protocol.json').read_text())
    if code_snapshot()!=protocol['sources'] or window_version()!=protocol['window_version']:
        raise ValueError('code changed after freezing; keep prior experiment and prepare a new ID')
    for case in protocol['cases']:
        spec=json.loads((out/case['name']/'input.json').read_text())
        if digest(spec)!=case['input_sha256'] or digest(json.loads((out/case['name']/'scenario.json').read_text()))!=case['config_sha256']:
            raise ValueError('frozen task/config changed')
        if inventory(Path(spec['task']['sources']['root']))!=spec['task']['sources']:raise ValueError('corpus changed')
    return protocol


def replay(work):
    outcome=json.loads((work/'outcome.json').read_text());summary=outcome['run']
    if not summary or summary['status']!='done' or not outcome['source_replay_verified']:raise ValueError('no completed source-bound task')
    run_dir=private_file(Path(summary['output_dir'])/'metrics.json').parent
    events=[json.loads(l) for l in (run_dir/'agent-events.jsonl').read_text().splitlines()]
    spec=json.loads((work/'input.json').read_text());scene=WindowScene(spec,work/'replay-only')
    calls={e['data']['callId']:e for e in events if e['type']=='tool/call'};results={};counts=Counter()
    for event in events:
        if event['type']=='tool/result':
            for block in event['data']['message']['content']:
                results.setdefault(block['toolCallId'],[]).append((event,block))
    for event in events:
        if event['type']!='tool/call':continue
        data=event['data'];name=data['name'].removeprefix(PREFIX);args=json.loads(data['arguments'])
        matching=results.get(data['callId'],[])
        if len(matching)!=1:raise ValueError('ambiguous original result')
        observed=matching[0][1]
        if observed.get('isError'):counts['tool_errors']+=1;continue
        if name in ('read_workflow_input','search_pdf_text','pin_pdf_context','read_pinned_pdf_context'):
            value=getattr(scene,name)(**args)
            if digest(value)!=digest(json.loads(observed['content'][0]['text'])):
                raise ValueError('current source replay differs: '+name)
            counts[name]+=1
    report=json.loads(Path(outcome['receipt']['artifact']).read_text())
    replay_receipt=scene.publish(report['rows'],persist=False)
    # Path belongs to replay-only, so compare full report digest rather than receipt path.
    if replay_receipt['artifact_sha256']!=outcome['receipt']['artifact_sha256']:raise ValueError('full source-bound report differs')
    return events,run_dir,dict(counts)


def learn(out):
    protocol=validate(out);directory=out/'learned'
    if directory.exists():raise ValueError('do not overwrite a prior learning attempt')
    raw=json.loads((HERE/'pdf-window-contracts.json').read_text());contracts=parse_tool_contracts(raw)
    schema_sets=[];traces=[];identities=[];reviews=[]
    freezer=module('window_identity_freezer',ROOT/'scripts/freeze-dsh-task-identity.py')
    for case in protocol['cases'][:3]:
        work=out/case['name'];events,run,review=replay(work)
        preview=json.loads((run/'preview.json').read_text())
        if preview['mode']!='baseline' or preview.get('entry_policy_digest') or preview.get('terminal_policy_digest') or preview.get('manifest_digest'):
            raise ValueError('learning requires original normal native model decisions')
        if any(e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-') for e in events):
            raise ValueError('synthetic Runtime calls cannot train')
        if not any(e.get('type')=='assistant/message' and e['data'].get('usage') for e in events):
            raise ValueError('no real provider usage')
        schema_sets.append([{**t,'name':PREFIX+t['name'],'inputSchema':t.get('inputSchema',t.get('input_schema'))}
                            for t in json.loads((work/'tool-schemas.json').read_text())])
        identity=freezer.freeze(run,protocol['experiment_id']+'-'+case['name'],'agent-events.jsonl')
        lock=load_trace_identity(identity,run/'agent-events.jsonl',ROOT/'.local');identities.append(lock)
        traces.append(extract_dsh_trace(events,contracts,trace_id=run.name,task_fingerprint=lock['research_decision_id'],
                       provenance_by_call_id=infer_dsh_provenance(events,contracts)))
        reviews.append({'case':case['name'],'role':case['role'],'actual_replay_counts':review,
                        'events_sha256':hashlib.sha256((run/'agent-events.jsonl').read_bytes()).hexdigest()})
    require_distinct_decisions(identities)
    if not all(digest(s)==digest(schema_sets[0]) for s in schema_sets):raise ValueError('training/certification schemas differ')
    contracts=bind_mcp_descriptions(contracts,schema_sets[0])
    candidates=[c for c in mine_witnessed_parameter_edges(traces[:2]) if
        (c['from_tool'],c['from_field'],c['to_tool'],c['to_param'])==
        (PREFIX+'pin_pdf_context','source_id',PREFIX+'read_pinned_pdf_context','source_id')]
    if len(candidates)!=1:raise ValueError('expected exactly one witnessed pin/read edge')
    artifact=certify_witnessed_edge_motif(compile_witnessed_edge_motif(candidates[0],traces[:2],contracts),traces[2],contracts)
    library=library_from_certified([artifact]);exporter=module('window_manifest_exporter',ROOT/'scripts/export-online-motif-manifest.py')
    actual_raw={k:{**v,'description':contracts[k].description} for k,v in raw.items()}
    manifest=exporter.export_manifest(library,actual_raw,version_fields={t:'document_version_sha256' for t in artifact['tools']})
    subprocess.run(['node','--input-type=module','-e',
        "import fs from 'node:fs';import {validateOnlineManifest} from './src/motif_core/online_skill_runtime.mjs';validateOnlineManifest(JSON.parse(fs.readFileSync(0,'utf8')));"],
        cwd=ROOT,text=True,input=json.dumps(manifest),capture_output=True,check=True)
    directory.mkdir(mode=0o700)
    save_private(directory/'library.json',library);save_private(directory/'online-manifest.json',manifest)
    save_private(directory/'provenance.json',{'window_version':window_version(),'schema_sha256':digest(schema_sets[0]),
        'schemas':schema_sets[0],'identities':identities,'source_reviews':reviews,'candidates':candidates,
        'witness_counts':{trace.trace_id:count_safe_edge_witnesses(candidates[0],trace,contracts) for trace in traces},
        'scientific_support_verified':False,'new_core_algorithm':False,'scope':'existing interleaved edge learning and batched source reads'})
    print(json.dumps({'learned':str(directory),'manifest_digest':manifest['manifest_digest'],'certified_motifs':1,
                      'witness_counts':artifact['witness_counts'],'validation_trace_id':artifact['validation_trace_id']}),flush=True)


class RejectEmbedding(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.server.calls.append({'path':self.path,'length':self.headers.get('Content-Length')})
        self.send_response(503);self.end_headers();self.wfile.write(b'Embeddings are disabled for closed source reads')


def aggregate(out):
    protocol=json.loads((out/'protocol.json').read_text());rows=[];all_runs=[]
    for file in out.glob('*/outcome.json'):
        outcome=json.loads(file.read_text());all_runs.append(outcome)
    for item in protocol['schedule']:
        path=out/item['name']/'outcome.json'
        if not path.exists():continue
        outcome=json.loads(path.read_text());counts={};verified=False
        try:
            _,_,counts=replay(path.parent);verified=True
        except ValueError as exc:counts={'replay_failure':str(exc)}
        report=json.loads(Path(outcome['receipt']['artifact']).read_text()) if outcome['receipt'] else {'sources':{},'rows':[]}
        contexts=report['sources'];claims=[{'target_id':r['target_id'],'status':r['status'],'references':r['references']}for r in report['rows']]
        rows.append({**item,'metrics':outcome['run'],'receipt':outcome['receipt'],'actual_replay_counts':counts,
                     'read_window_count':len(contexts),'report_targets':claims,'source_read_success':verified,
                     'scientific_support_verified':False})
    arms={}
    for case in ('eval-orchestration','eval-cost-evidence'):
        arms[case]={}
        for arm in ('H','M'):
            selected=[r for r in rows if r['case']==case and r['arm']==arm]
            arms[case][arm]={'runs':len(selected),'complete_source_replays':sum(r['source_read_success']for r in selected)}
            for field in ('upstream_requests','outputTokens','inputTokens','cacheReadTokens','budget_accounted_usd','elapsed_seconds','model_requests_skipped_verified'):
                if selected:arms[case][arm][field]=statistics.mean(r['metrics'][field]for r in selected)
    body={'experiment_id':out.name,'actual_runs':len(all_runs),
          'upstream_requests':sum((r['run'] or {}).get('upstream_requests',0)for r in all_runs),
          'budget_accounted_usd':sum((r['run'] or {}).get('budget_accounted_usd',0)for r in all_runs),
          'arms':arms,'rows':rows,'scientific_support_verified':False,'independent_corpus_generalization':False}
    save_private(out/'summary.json',body)
    print(json.dumps({k:v for k,v in body.items()if k!='rows'},ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path);p.add_argument('--phase',choices=['train','learn','evaluate','summary'],default='train')
    p.add_argument('--call-model',action='store_true');a=p.parse_args()
    out=private_file(a.experiment/'protocol.json').parent if a.experiment else prepare();protocol=validate(out)
    print(json.dumps({'experiment':str(out),'phase':a.phase,'model_call_enabled':a.call_model,
                      'budget_total_cap_usd':protocol['budget_total_cap_usd'],'shared_core_changes':False}),flush=True)
    if a.phase=='learn':learn(out);return
    if a.phase=='summary':aggregate(out);return
    if not a.call_model:return
    if a.phase=='train':
        for case in protocol['cases'][:3]:
            if case.get('imported_native_run'):
                replay(out/case['name'])
                continue
            runner.run(out/case['name'],protocol,scene_class=WindowScene,server_path=HERE/'pdf_window_tools.py')
    else:
        manifest=private_file(out/'learned/online-manifest.json');provenance=json.loads((out/'learned/provenance.json').read_text())
        if provenance['window_version']!=window_version():raise ValueError('library implementation changed')
        endpoint=ThreadingHTTPServer(('127.0.0.1',0),RejectEmbedding);endpoint.calls=[]
        threading.Thread(target=endpoint.serve_forever,daemon=True).start()
        try:
            for item in protocol['schedule']:
                validate(out)
                runner.run(out/item['name'],protocol,scene_class=WindowScene,server_path=HERE/'pdf_window_tools.py',
                    manifest=manifest if item['arm']=='M'else None,
                    embedding_endpoint=f'http://127.0.0.1:{endpoint.server_port}/v1/embeddings')
                save_private(out/'embedding-observations.json',{'requests':endpoint.calls,'fake_vectors_used':False})
                aggregate(out)
        finally:endpoint.shutdown();endpoint.server_close()


if __name__=='__main__':main()
