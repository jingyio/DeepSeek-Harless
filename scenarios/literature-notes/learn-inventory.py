"""Certify list-result array traversal from original unassisted PDF tasks."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from mcp import Client, StdioServerParameters
from pdf_tools import ROOT,PdfScene,digest,save_private
from inventory_entry import entry_task,execution_version,SOURCE,PREPARE,HERE
sys.path.insert(0,str(ROOT))
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.entry_compiler import inventory_witness,compile_inventory_motif,certify_entry_motif,navigation_projection
from src.motif_core.offline.library_builder import library_from_certified

def load_witness(rid):
    run=ROOT/'.local/runs'/rid
    if run.resolve().parent != (ROOT/'.local/runs').resolve():raise ValueError('native run ID required')
    preview=json.loads((run/'preview.json').read_text());snapshot=json.loads((run/'pdf-input-snapshot.json').read_text())
    if (preview['mode']!='baseline' or preview.get('tool_presentation','native')!='native'
            or preview.get('entry_policy_digest') or preview.get('manifest_digest') or not preview['model_call_enabled']
            or snapshot.get('execution_options',{}).get('script_read')):
        raise ValueError('original unassisted native task required')
    task=snapshot['task'];scene=PdfScene(Path(task['sources']['root']),ROOT/'.local/literature-notes/pdf-cache',task)
    frozen=entry_task(scene,rid);events_path=run/'agent-events.jsonl'
    events=[json.loads(l) for l in events_path.read_text().splitlines()]
    witness=inventory_witness(events,frozen,SOURCE,PREPARE,trace_id=rid,task_fingerprint=digest(task))
    for ref in witness['references']:
        out=scene.list_pdfs() if ref['role']=='source' else navigation_projection(scene.prepare_pdf(ref['target_id']))
        if digest(out)!=ref['projection_sha256']:raise ValueError('current source/navigation replay differs from original')
    ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()]
    witness.update(events_sha256=hashlib.sha256(events_path.read_bytes()).hexdigest(),
        input_snapshot_sha256=digest(snapshot),source_replay_equal=True,
        historical_stage_requests=len(ledger),historical_stage_estimated_usd=sum(r.get('observed_peak_usd',0) for r in ledger))
    return witness,scene

async def schemas(scene,output):
    save_private(output/'schema-task.json',scene.task)
    env={**os.environ,'SSS_PDF_ROOT':str(scene.root),'SSS_PDF_TASK_FILE':str(output/'schema-task.json'),
        'SSS_PDF_CACHE':str(scene.cache),'SSS_PDF_DELIVERY':str(output/'schema-delivery'),'SSS_PDF_SCRIPT_READ':'0'}
    env.pop('DEEPSEEK_API_KEY',None)
    async with Client(StdioServerParameters(command=sys.executable,args=[str(HERE/'pdf_tools.py')],cwd=ROOT,env=env)) as client:
        return {'mcp__literature_pdf__'+t.name:t.model_dump(mode='json',by_alias=True)['inputSchema']
            for t in (await client.list_tools()).tools if t.name in ('list_pdfs','prepare_pdf')}

def learn(output,split):
    if output.is_symlink() or not output.resolve().is_relative_to(ROOT/'.local'):raise ValueError('private output required')
    output.mkdir(parents=True,mode=0o700,exist_ok=False);s=json.loads(split.read_text())
    runs=s['training_runs']+[s['certification_run']];cases=[load_witness(r) for r in runs]
    contracts=parse_tool_contracts(json.loads((HERE/'pdf-contracts.json').read_text()))
    actual=asyncio.run(schemas(cases[0][1],output));compiled=compile_inventory_motif([c[0] for c in cases[:2]],contracts,
        source_tool=SOURCE,prepare_tool=PREPARE,schemas=actual)
    artifact=certify_entry_motif(compiled,cases[-1][0],contracts);library=library_from_certified([artifact])
    policy={'schema_version':1,'format':'sss-entry-inventory-v1','source_library_digest':library['library_digest'],
        'execution_version_sha256':execution_version(),'artifact':artifact};policy['policy_digest']=digest(policy)
    verifier="import fs from 'node:fs';import {validateEntryPolicy} from './src/motif_core/entry_read_policy.ts';validateEntryPolicy(JSON.parse(fs.readFileSync(0,'utf8')));"
    subprocess.run(['node','--input-type=module','-e',verifier],input=json.dumps(policy),text=True,cwd=ROOT,check=True,capture_output=True)
    for name,value in [('entry-policy.json',policy),('library.json',library),('witnesses.json',[c[0] for c in cases]),('schemas.json',actual)]:save_private(output/name,value)
    report={'policy_digest':policy['policy_digest'],'training_counts':[c[0]['target_count'] for c in cases[:2]],
        'certification_count':cases[-1][0]['target_count'],'entry_requests_in_original_traces':[c[0]['provider_requests'] for c in cases],
        'historical_stage_requests':sum(c[0]['historical_stage_requests'] for c in cases),
        'historical_stage_estimated_usd':sum(c[0]['historical_stage_estimated_usd'] for c in cases),
        'source_and_navigation_replay_equal':True,'projection_exception':['cache_stats'],'new_compilation_requests':0}
    save_private(output/'outcome.json',report);return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--split',type=Path,required=True);a=p.parse_args()
    print(json.dumps(learn(a.output.resolve(),a.split.resolve())))
