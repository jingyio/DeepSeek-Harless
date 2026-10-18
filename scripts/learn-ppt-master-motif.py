#!/usr/bin/env python3
"""从真实 GeneLoop Baseline 轨迹编译 ppt-master 只读衔接；不写图、不训练模型权重。"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scenarios.research_ppt.motif_v6 import learn,validate_compilation
from scenarios.ppt_master.package import read_lock
from src.adapters.task_identity import load_trace_identity,require_distinct_decisions
spec=importlib.util.spec_from_file_location('web_evidence',ROOT/'scripts/learn-web-paper-document-motif.py')
accounting=importlib.util.module_from_spec(spec);spec.loader.exec_module(accounting)
SCENE=ROOT/'scenarios/ppt_master'
CHAIN=['mcp__ppt_master__pin_source', 'mcp__ppt_master__convert_source', 'mcp__ppt_master__read_converted_source']
ALL_MCP=sorted([*CHAIN,'mcp__ppt_master__read_skill_entry','mcp__ppt_master__read_source_page'])


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def private(p):
    p=Path(p)
    if p.is_symlink() or not p.resolve().is_relative_to((ROOT/'.local').resolve()):
        raise ValueError('raw evidence must stay in private .local')
    return p.resolve()
def write(p,v):
    with Path(p).open('x',encoding='utf-8') as f: json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')


def code_paths():
    files=[p for p in SCENE.iterdir() if p.is_file() and p.name!='README.md']
    files += [ROOT/p for p in ('src/adapters/dsh_web_tasks.ts','src/adapters/harless_scenarios.py',
        'src/adapters/harless_settings.ts','src/adapters/harless_task_scope.ts','src/adapters/harless_rsi_binding.ts','src/adapters/session_files.py','src/adapters/harless_rsi_bundle.py',
        'src/adapters/dsh_online_motif.mjs','src/motif_core/online_skill_runtime.mjs','src/adapters/ppt_master_recovery.ts',
        'src/adapters/geneloop_skill_installation.mjs','src/adapters/geneloop_shell.ts',
        'src/adapters/geneloop_command_broker.ts','src/adapters/geneloop_capabilities.ts',
        'scripts/harless_gateway.mjs','scripts/harless_member_scenes.mjs','scripts/install-ppt-master.py','scenarios/research_ppt/motif_v6.py',
        'config/geneloop-capabilities.json','config/geneloop-capabilities.md')]
    return sorted(set(files+[Path(__file__).resolve()]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--publish',type=Path)
    a=p.parse_args();data=read(private(a.dataset));out=private(a.out)
    if len(data.get('train',[]))!=2 or len(data.get('heldout',[]))!=1:
        raise ValueError('two independent train tasks and one heldout required')
    ledger=accounting.real_ledger(private(data['ledger']))
    out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    lock=read_lock();evidence={};runs={};schemas=None;full_schemas=None
    for split in ('train','heldout'):
        evidence[split]=[];runs[split]=[]
        for i,row in enumerate(data[split]):
            task=private(row['task_dir']);state=read(task/'task-state.json');req=read(task/'task.json');effective=read(task/'effective-config.json')
            if (state.get('status')!='completed' or req.get('mode')!='baseline' or
                    effective.get('provider_mode')!='real' or effective.get('ppt_execution_strategy')!='ppt_master' or
                    effective.get('skill_package_sha256')!=lock['package_sha256']):
                raise ValueError('requires a real completed ppt-master Baseline task at the pinned version')
            totals=accounting.reconcile(state,req,ledger,qualifying=True)
            current=accounting.native_schemas(effective['tools'])
            mcp=[t for t in current if t['name'].startswith('mcp__')]
            if [t['name'] for t in mcp]!=ALL_MCP or (full_schemas is not None and current!=full_schemas):
                raise ValueError('complete actual tool schema/order changed across collection')
            full_schemas=current;schemas=mcp
            dest=out/(split+'-'+str(i+1));dest.mkdir()
            lines=(task/'events.jsonl').read_bytes().splitlines(keepends=True)
            start=effective.get('trace_start_index',0)
            if type(start) is not int or not 0<=start<=len(lines): raise ValueError('invalid event boundary')
            (dest/'agent-events.jsonl').write_bytes(b''.join(lines[start:]))
            question='\n'.join(x['text'] for x in req['content'] if x['type']=='text')
            write(dest/'manifest.json',{'task_id':req['task_id'],'question':question,
                'effective_sha256':sha(task/'effective-config.json'),'original_events_sha256':sha(task/'events.jsonl'),
                'trace_start_index':start,'skill_package_sha256':lock['package_sha256'],'stats':totals})
            write(dest/'task-identity.json',{'schema_version':1,'research_decision_id':row['decision_id'],
                'manifest_sha256':sha(dest/'manifest.json'),'events_sha256':sha(dest/'agent-events.jsonl')})
            identity=load_trace_identity(dest/'task-identity.json',dest/'agent-events.jsonl',ROOT/'.local')
            evidence[split].append({**identity,**totals,'skill_package_sha256':lock['package_sha256'],
                'effective_config_sha256':sha(task/'effective-config.json')})
            runs[split].append(str(dest))
    identities=evidence['train']+evidence['heldout'];require_distinct_decisions(identities)
    write(out/'dataset.json',runs)
    write(out/'schema.json',{'tools':[{'name':t['name'],'description':t['description'],'inputSchema':t['parameters']} for t in schemas]})
    manifest_path=learn(out/'dataset.json',contracts_path=SCENE/'contracts.json',version_fields_path=SCENE/'version-fields.json',
        tool_schema_path=out/'schema.json',out_dir=out/'compiled',guard_paths=tuple(code_paths()),mining='witnessed_edges',admit_edges_only=True)
    validate_compilation(manifest_path);manifest=read(manifest_path);library=read(manifest_path.parent/'library.json')
    if {tuple(a['tools']) for a in manifest['artifacts']}!={tuple(CHAIN[:2]),tuple(CHAIN[1:])}:
        raise ValueError('actual traces did not certify the supported continuation; never invent a graph')
    excluded=[]
    for value in data.get('excluded_task_dirs',[]):
        task=private(value);req=read(task/'task.json');state=read(task/'task-state.json')
        if req['task_id'] in {x['task_id'] for x in identities+excluded}:raise ValueError('duplicate cost identity')
        excluded.append({'task_id':req['task_id'],'status':state['status'],**accounting.reconcile(state,req,ledger,qualifying=False)})
    report={'schema_version':1,'new_training':True,'method':'existing_witnessed_edge_compiler',
        'training_tasks':2,'heldout_tasks':1,'artifacts':len(manifest['artifacts']),
        'skill_package_sha256':lock['package_sha256'],'library_digest':library['library_digest'],'manifest_digest':manifest['manifest_digest'],
        'model_weights_trained':False,'quality_cost_promoted':False,'scientific_quality_reviewed':False,
        'compilation_model_requests':0,'compilation_seconds':time.monotonic()-started,
        'trace_collection_requests':sum(x['requests'] for x in identities),
        'trace_collection_proxy_usd':sum(x['proxy_peak_usd'] for x in identities),
        'excluded_collection':excluded,'actual_paid_usd':None,
        'total_collection_requests':sum(x['requests'] for x in identities+excluded),
        'total_collection_proxy_usd':sum(x['proxy_peak_usd'] for x in identities+excluded),
        'scope':'Model-selected PDF pin, official source conversion in private derivative cache, and exact converted text read; no slide authoring or scientific interpretation.'}
    write(out/'source-evidence.json',evidence);write(out/'learning-report.json',report)
    if a.publish:
        target=a.publish.resolve()
        if not target.is_relative_to((ROOT/'motif-libraries').resolve()):raise ValueError('publish under motif-libraries only')
        target.mkdir(exist_ok=False)
        for name in ('library.json','online-manifest.json'):shutil.copyfile(manifest_path.parent/name,target/name)
        for name in ('source-evidence.json','learning-report.json'):shutil.copyfile(out/name,target/name)
        write(target/'tool-schemas.json',schemas)
        write(target/'task.json',{'schema_version':1,'task_id':'ppt-master-admission','session_id':'ppt-master-admission',
            'intent':'Convert and read the exact model-selected uploaded PDF using official version-locked tools.','input_version':lock['package_sha256'],
            'bindings':{},'source_versions':{CHAIN[0]:'@observed',CHAIN[1]:lock['package_sha256'],CHAIN[2]:lock['package_sha256']}})
        write(target/'certification.json',{'schema_version':1,'scene':'ppt','binding_policy':'ppt_master_sources_v1',
            'matching_policy':'structural_only','certification_scope':'independent_trace_structure','quality_cost_promoted':False,
            'source_evidence_sha256':sha(target/'source-evidence.json'),'learning_report_sha256':sha(target/'learning-report.json'),
            'file_locks':{p.name:sha(p) for p in target.iterdir()},'code_locks':{p.relative_to(ROOT).as_posix():sha(p) for p in code_paths()}})
        write(target/'entry.json',{'schema_version':1,'scene':'ppt','runtime_kind':'ppt_master_v2','mode':'execute','new_training':True,
            'files':{p.name:sha(p) for p in target.iterdir()},'quality_cost_promoted':False})
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
