"""Pool original cross-workflow traces; discover graphs and certify bounded read Motifs."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from common import ROOT,HERE,PREFIX,digest,save,sha
from file_tools import FileScene
sys.path.insert(0,str(ROOT))
from src.adapters.dsh_trajectory import extract_dsh_trace,infer_dsh_provenance,mine_witnessed_parameter_edges,mine_dsh_traces
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.motif_core.offline.edge_compiler import compile_witnessed_edge_motif,certify_witnessed_edge_motif
from src.motif_core.offline.library_builder import library_from_certified

REQUIREMENTS={'read_task':[],'list_files':[],'pin_file':['file_id'],'read_file':['source_id'],
 'hash_files':['file_ids'],'build_index':['source_ids'],'search_index':['query'],
 'compare_snapshot':[],'preview_actions':['actions'],'execute_plan':['plan_id'],'restore_plan':['plan_id'],
 'submit_report':['summary','file_ids','gaps']}
READS={'read_task','list_files','pin_file','read_file','hash_files','search_index','compare_snapshot'}

def contracts(schemas):
    raw={}
    for row in schemas:
        name=row['name']; fields=[]
        if name=='pin_file':fields=['source_id','file_id','source_version']
        if name=='read_file':fields=['source_id','file_id','source_version','status']
        if name=='read_task':fields=['input_sha256']
        raw[PREFIX+name]={'required_params':REQUIREMENTS[name],'output_fields':fields,
            'read_only':name in READS,'replay_stable':name not in ('list_files','search_index','compare_snapshot'),
            'description':row['description'],'provenance_params':['source_id'] if name=='read_file' else [],
            'collection_params':['file_ids'] if name=='hash_files' else [],
            'default_params':[],'parameter_shapes':[]}
    return raw

def graph(events,trace_id,family):
    calls=[];results={};sources={};edges=[];producer={};decisions=[]
    for e in events:
        if e.get('type')=='assistant/message' and e['data'].get('message',{}).get('source',{}).get('kind')=='model':
            blocks=e['data']['message'].get('content',[])
            decisions.append({'seq':e['seq'],'usage':e['data'].get('usage'),
                              'tools':[b['name'] for b in blocks if b.get('type')=='tool-call'],
                              'visible_text_chars':sum(len(b.get('text','')) for b in blocks if b.get('type')=='text')})
        if e.get('type')=='tool/result':
            for b in e['data']['message'].get('content',[]):
                if b.get('type')=='tool-result':results.setdefault(b['toolCallId'],(e['seq'],b))
    for e in events:
        if e.get('type')=='tool/call':
            data=e['data'];cid=data['callId'];args=data.get('arguments',{})
            raw_args=args; arguments_valid=True
            if isinstance(args,str):
                try:args=json.loads(args)
                except ValueError:args={};arguments_valid=False
            if not isinstance(args,dict):args={};arguments_valid=False
            node={'call_id':cid,'seq':e['seq'],'tool':data['name'],'arguments':args,'effectful':data['name'].removeprefix(PREFIX) not in READS}
            node['arguments_valid']=arguments_valid
            if not arguments_valid:node['unparsed_arguments']=raw_args
            if calls:edges.append({'from':calls[-1]['call_id'],'to':cid,'kind':'observed_order','execution_permission':False})
            for key,value in args.items():
                values=enumerate(value) if isinstance(value,list) else [(None,value)]
                for index,item in values:
                    if isinstance(item,str) and item in producer and producer[item] is not None:
                        src,field=producer[item]
                        edges.append({'from':src,'to':cid,'kind':'observed_parameter','field':field,
                                      'argument':key,'array_index':index,'execution_permission':False})
            calls.append(node)
        elif e.get('type')=='tool/result':
            for b in e['data']['message'].get('content',[]):
                if b.get('type')!='tool-result' or b.get('isError'):continue
                try:body=json.loads(b['content'][0]['text'])
                except (KeyError,ValueError,IndexError):continue
                if not isinstance(body,dict):continue
                sources[b['toolCallId']]=body
                for key,value in body.items():
                    if isinstance(value,str) and value.startswith(('source-','result-')) and len(value)==39:
                        producer[value]=(b['toolCallId'],key) if value not in producer else None
    for c in calls:
        seq,result=results.get(c['call_id'],(None,{}));body=sources.get(c['call_id'],{})
        c.update(result_seq=seq,success=bool(result and not result.get('isError')),
                 result_status=body.get('status'),result_sha256=digest(body) if body else None)
    return {'trace_id':trace_id,'family':family,'nodes':calls,'edges':edges,'model_decisions':decisions,
            'graph_status':'observed_execution_graph','arbitrary_graph_certified':False}

def replay_reads(case,outcome,spec):
    attempt=Path(outcome['attempt']);paths=[Path(spec['workspace']),Path(json.loads((case['experiment']/'protocol.json').read_text())['data_directory'])/'datasets'/spec['variant']]
    paths += list((attempt/'delivery/backups').glob('*'))
    index={}
    for root in paths:
        for p in root.rglob('*'):
            if p.is_file() and not p.is_symlink():index.setdefault(sha(p),p)
    parser=FileScene.__new__(FileScene);count=0
    for p in (attempt/'delivery/reads').glob('*.json'):
        row=json.loads(p.read_text());source=index.get(row['sha256'])
        if source is None:raise ValueError('no source bytes for replay')
        # Copies/backups retain extensions; content digests are independent of paths.
        try:
            status,text,meta=parser.parse(source)
        except Exception as exc:
            if row['status']!='unreadable':raise ValueError('formerly readable file now fails replay') from exc
            count+=1;continue
        if status!=row['status'] or text[:6000]!=row.get('text','') or meta!=row.get('metadata',{}):
            raise ValueError('original file observation differs from current parser')
        if row['source_version']!=digest({'path':row['path'],'sha':row['sha256'],'parser':'fm-parser-v1'}):
            raise ValueError('source version mismatch')
        count+=1
    return count

def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);args=p.parse_args()
    exp=args.experiment.resolve();protocol=json.loads((exp/'protocol.json').read_text());destination=exp/'learned'
    if destination.exists():raise ValueError('retain existing learning version; choose a new experiment')
    traces={'explore':[],'certify':[]};graphs=[];schema0=None;reviews=[];family_by_trace={};exclusions=[]
    for case in protocol['tasks']:
        if case['role'] not in traces:continue
        for path in (Path(case['task_dir'])/'attempts').glob('*/outcome.json'):
            out=json.loads(path.read_text())
            attempt=Path(out['attempt']);run=Path(out['run']['output_dir']);events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
            if sha(run/'agent-events.jsonl')!=out['events_sha256']:raise ValueError('original events changed')
            g=graph(events,run.name,case['family']);g['task_acceptance_passed']=out['acceptance']['passed'];graphs.append(g)
            if not out['acceptance']['passed'] or not out['receipt_verified'] or (out.get('run') or {}).get('status')!='done':
                exclusions.append({'task_id':case['task_id'],'reason':'task acceptance or actual completion failed'});continue
            if any(e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-') for e in events):
                raise ValueError('runtime-generated calls cannot train')
            spec=json.loads((Path(case['task_dir'])/'input.json').read_text())
            if digest(spec)!=case['input_sha256']:raise ValueError('task identity changed')
            if not any(e.get('type')=='assistant/message' and e['data'].get('usage') for e in events):raise ValueError('no real provider evidence')
            schemas=json.loads((attempt/'tool-schemas.json').read_text())
            if schema0 is None:schema0=schemas
            if digest(schemas)!=digest(schema0):raise ValueError('tool schemas differ; freeze another learning version')
            case['experiment']=exp
            replayed=replay_reads(case,out,spec)
            raw=contracts(schemas);ct=parse_tool_contracts(raw)
            trace=extract_dsh_trace(events,ct,trace_id=run.name,task_fingerprint=digest({'task':spec['task_id'],'objective':spec['objective'],'input':digest(spec)}),
                                    provenance_by_call_id=infer_dsh_provenance(events,ct))
            traces[case['role']].append(trace);family_by_trace[run.name]=case['family']
            reviews.append({'task_id':case['task_id'],'trace_id':run.name,'role':case['role'],
                            'events_sha256':out['events_sha256'],'replayed_reads':replayed,
                            'code_sha256':digest(json.loads((attempt/'source-code.json').read_text()))})
    if not schema0 or len(traces['explore'])<2 or not traces['certify']:raise ValueError('need independent successful exploration and certification tasks')
    if len({r['code_sha256'] for r in reviews})!=1:raise ValueError('execution versions differ; do not combine repaired pilot runs')
    raw=contracts(schema0);ct=parse_tool_contracts(raw)
    schemas=[{**r,'name':PREFIX+r['name'],'inputSchema':r.get('inputSchema',r.get('input_schema'))} for r in schema0]
    ct=bind_mcp_descriptions(ct,schemas)
    candidates=mine_witnessed_parameter_edges(traces['explore']);artifacts=[];uncompiled=[]
    for c in candidates:
        try:
            compiled=compile_witnessed_edge_motif(c,traces['explore'],ct)
            certified=None
            for trace in traces['certify']:
                try:certified=certify_witnessed_edge_motif(compiled,trace,ct);break
                except ValueError:continue
            if certified is None:raise ValueError('no independent certification witness')
            artifacts.append(certified)
        except ValueError as exc:uncompiled.append({'candidate':c,'reason':str(exc)})
    patterns=mine_dsh_traces(traces['explore'])
    boundary=Counter()
    for g in graphs:
        for a,b in zip(g['nodes'],g['nodes'][1:]):
            boundary[(a['tool'],a.get('result_status'),b['tool'])]+=1
    save(destination/'observed-graphs.json',graphs)
    save(destination/'candidates.json',{'parameter_edges':candidates,'contiguous_patterns':patterns,'uncompiled':uncompiled,
        'observed_status_transitions':[{'from_tool':a,'status':s,'next_tool':b,'count':n,'status_is_condition_proof':False}
                                      for (a,s,b),n in boundary.items()],
        'effectful_and_branch_graphs':'observations only; not autonomous write authorization'})
    if artifacts:
        library=library_from_certified(artifacts);save(destination/'library.json',library)
        modspec=importlib.util.spec_from_file_location('fm_export',ROOT/'scripts/export-online-motif-manifest.py')
        exporter=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(exporter)
        used={t for a in artifacts for t in a['tools']}
        updated={k:{**v,'description':ct[k].description} for k,v in raw.items()}
        manifest=exporter.export_manifest(library,updated,version_fields={t:'source_version' for t in used if 'source_version' in ct[t].output_fields})
        subprocess.run(['node','--input-type=module','-e',"import fs from 'node:fs';import {validateOnlineManifest} from './src/motif_core/online_skill_runtime.mjs';validateOnlineManifest(JSON.parse(fs.readFileSync(0,'utf8')));"],
                        cwd=ROOT,input=json.dumps(manifest),text=True,capture_output=True,check=True)
        save(destination/'online-manifest.json',manifest)
    result={'training_tasks':len(traces['explore']),'certification_tasks':len(traces['certify']),
            'observed_graphs':len(graphs),'certified_read_motifs':len(artifacts),
            'parameter_candidates':len(candidates),'sequence_candidates':len(patterns),
            'supporting_families':sorted({family_by_trace[t] for a in artifacts for t in a['source_trace_ids']}),
            'source_reviews':reviews,'excluded_runs':exclusions,'arbitrary_graph_learning_complete':False,
            'online_execution_tested':False,'efficiency_gain_measured':False,'shared_core_changes':False,
            'learning_source_sha256':sha(HERE/'learn.py')}
    save(destination/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_reviews','excluded_runs')},ensure_ascii=False))

if __name__=='__main__':main()
