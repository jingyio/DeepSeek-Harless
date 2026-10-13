"""Certify catalog work traversal using original normal native model decisions."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from mcp import Client, StdioServerParameters
from pdf_tools import ROOT, digest, save_private
from pdf_dependencies import private_file
from pdf_catalog_tools import CatalogScene, execution_version, HERE
from catalog_entry import entry_task, SOURCE, PREPARE
sys.path.insert(0,str(ROOT))
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.entry_compiler import inventory_witness,compile_inventory_motif,certify_entry_motif,navigation_projection
from src.motif_core.offline.library_builder import library_from_certified


def load_witness(directory):
    directory=private_file(Path(directory)/'outcome.json').parent
    outcome=json.loads((directory/'outcome.json').read_text()); snapshot=json.loads((directory/'input-snapshot.json').read_text())
    run=private_file(Path(outcome['run']['output_dir'])/'preview.json').parent
    preview=json.loads((run/'preview.json').read_text())
    if (preview['mode']!='baseline' or preview.get('tool_presentation','native')!='native'
            or any(preview.get(k) for k in ('entry_policy_digest','terminal_policy_digest','manifest_digest'))
            or not preview['model_call_enabled'] or snapshot.get('entry_policy_digest')
            or snapshot['execution_version_sha256']!=execution_version() or not outcome.get('receipt')
            or outcome['run'].get('status') != 'done'):
        raise ValueError('successful original native catalog task at current version required')
    task=json.loads((directory/'task.json').read_text())
    scene=CatalogScene(task['sources']['root'],task,directory,
        previous=directory/'previous-catalog.json' if snapshot['previous_catalog_sha256'] else None)
    frozen=entry_task(scene,run.name); events_path=run/'agent-events.jsonl'
    events=[json.loads(l) for l in events_path.read_text().splitlines()]
    witness=inventory_witness(events,frozen,SOURCE,PREPARE,trace_id=run.name,
        task_fingerprint=digest({'task':task,'plan_sha256':frozen['plan_sha256']}),frontier='incremental')
    for ref in witness['references']:
        out=scene.read_catalog_plan() if ref['role']=='source' else navigation_projection(scene.read_catalog_packet(ref['target_id']))
        if digest(out)!=ref['projection_sha256']: raise ValueError('full actual catalog plan/packet replay differs')
    # Replay publication as well, without rewriting any historical artifact.
    envelope=json.loads((directory/'catalog.json').read_text()); payload=envelope['catalog']
    if digest(payload)!=envelope['catalog_sha256'] or scene.publish(payload['submitted_entries'],persist=False)!=payload:
        raise ValueError('catalog publication/source replay differs')
    ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()]
    witness.update(events_sha256=hashlib.sha256(events_path.read_bytes()).hexdigest(),input_snapshot_sha256=digest(snapshot),
        source_replay_equal=True,historical_stage_requests=len(ledger),
        historical_stage_estimated_usd=sum(r.get('observed_peak_usd',0) for r in ledger))
    return witness,scene,directory


async def schemas(scene,directory):
    env={**os.environ,'SSS_PDF_TASK_FILE':str(directory/'task.json'),'SSS_PDF_CATALOG_OUTPUT':str(directory),
         'SSS_PDF_CATALOG_PREVIOUS':str(directory/'previous-catalog.json') if scene.previous else ''}
    env.pop('DEEPSEEK_API_KEY',None)
    async with Client(StdioServerParameters(command=sys.executable,args=[str(HERE/'pdf_catalog_tools.py')],cwd=ROOT,env=env)) as client:
        return {'mcp__literature_catalog__'+t.name:t.model_dump(mode='json',by_alias=True)['inputSchema']
                for t in (await client.list_tools()).tools if 'mcp__literature_catalog__'+t.name in (SOURCE,PREPARE)}


def learn(output,split):
    if output.is_symlink() or not output.resolve().is_relative_to(ROOT/'.local'): raise ValueError('private output required')
    output.mkdir(parents=True,mode=0o700,exist_ok=False); s=json.loads(private_file(split).read_text())
    if len(s['training_runs'])!=2: raise ValueError('two independent training tasks required')
    cases=[load_witness(r) for r in s['training_runs']+[s['certification_run']]]
    contracts=parse_tool_contracts(json.loads((HERE/'pdf-catalog-contracts.json').read_text()))
    actual=[asyncio.run(schemas(c[1],c[2])) for c in cases]
    if any(v!=actual[0] for v in actual): raise ValueError('teacher/certification schema differs')
    artifact=certify_entry_motif(compile_inventory_motif([c[0] for c in cases[:2]],contracts,
        source_tool=SOURCE,prepare_tool=PREPARE,schemas=actual[0],frontier='incremental'),cases[-1][0],contracts)
    library=library_from_certified([artifact]); policy={'schema_version':1,'format':'sss-entry-incremental-v1',
        'source_library_digest':library['library_digest'],'execution_version_sha256':execution_version(),'artifact':artifact}
    policy['policy_digest']=digest(policy)
    verifier="import fs from 'node:fs';import {validateEntryPolicy} from './src/motif_core/entry_read_policy.ts';validateEntryPolicy(JSON.parse(fs.readFileSync(0,'utf8')));"
    subprocess.run(['node','--input-type=module','-e',verifier],input=json.dumps(policy),text=True,cwd=ROOT,check=True,capture_output=True)
    for name,value in [('entry-policy.json',policy),('library.json',library),('witnesses.json',[c[0] for c in cases]),('schemas.json',actual[0])]:
        save_private(output/name,value)
    report={'policy_digest':policy['policy_digest'],'training_counts':[c[0]['target_count'] for c in cases[:2]],
        'certification_count':cases[-1][0]['target_count'],'source_plan_packet_and_publication_replay_equal':True,
        'entry_requests_in_original_traces':[c[0]['provider_requests'] for c in cases],
        'historical_stage_requests':sum(c[0]['historical_stage_requests'] for c in cases),
        'historical_stage_estimated_usd':sum(c[0]['historical_stage_estimated_usd'] for c in cases),'new_compilation_requests':0}
    save_private(output/'outcome.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--split',type=Path,required=True)
    a=p.parse_args();print(json.dumps(learn(a.output.resolve(),a.split.resolve())))
