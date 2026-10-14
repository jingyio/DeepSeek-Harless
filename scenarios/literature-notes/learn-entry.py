"""Learn the entry read frontier from two normal jobs; certify a third job."""
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
from pdf_repair_tools import RepairScene
sys.path.insert(0,str(ROOT))
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.entry_compiler import entry_witness, compile_entry_motif, certify_entry_motif
from src.motif_core.offline.library_builder import library_from_certified

HERE=Path(__file__).resolve().parent
TOOL='mcp__literature_pdf_repair__read_claim_repair_packet'
CONTRACTS={TOOL:{'required_params':['claim_id'],'read_only':True,'replay_stable':True,
 'output_fields':['claim_id','input_sha256','document_version_sha256'],
 'description':'Read a frozen target claim and current source-bound evidence; no scientific verdict.'}}


def execution_version():
    names=['pdf_repair_tools.py','pdf_review_tools.py','pdf_tools.py','pdf_layout.py','pdf_read_plan.py','claim_coverage.py','pdf_dependencies.py']
    return digest({n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in names})


def entry_task(scene):
    if scene.synthesis_only:raise ValueError('aggregate synthesis has no per-target document version guard')
    return {'schema_version':1,'task_id':scene.output.name,'input_version':scene.input_digest,
      'execution_version_sha256':execution_version(),'target_ids':scene.targets,'target_ids_sha256':digest(scene.targets),
      'target_versions':{cid:scene.scene.document_version(scene.claims[cid][0]) for cid in scene.targets}}


async def schema(input_directory,output):
    env={**os.environ,'SSS_PDF_REPAIR_RUN':str(input_directory),'SSS_PDF_REPAIR_OUTPUT':str(output)}
    env.pop('DEEPSEEK_API_KEY',None)
    async with Client(StdioServerParameters(command=sys.executable,args=[str(HERE/'pdf_repair_tools.py')],cwd=ROOT,env=env)) as client:
        return next(t.model_dump(mode='json',by_alias=True)['inputSchema'] for t in (await client.list_tools()).tools if t.name=='read_claim_repair_packet')


def load_witness(job_id,output):
    job=json.loads((ROOT/'.local/literature-notes/agent-jobs'/job_id/'job.json').read_text())
    if job.get('diagnostic_provenance') or job.get('selected_claim_ids') or job.get('options',{}).get('manifest'):
        raise ValueError('only normal non-diagnostic unassisted jobs can train')
    stage=next(s for s in job['stages'] if s['stage']=='repair-1')
    run=Path(stage['summaries'][0]['output_dir']);preview=json.loads((run/'preview.json').read_text())
    if preview['mode']!='baseline' or preview.get('tool_presentation','native')!='native' or not preview['model_call_enabled']:
        raise ValueError('normal real-model native events required')
    repair=Path(job['repair_rounds'][0]['output_directory'])
    snapshot=json.loads((repair/'input-snapshot.json').read_text())
    if snapshot.get('source_feedback_sha256'):raise ValueError('independent feedback cannot train entry policy')
    source=Path(snapshot['original_input']);scene=RepairScene(source,output/('replay-'+job_id))
    task=entry_task(scene);events_path=run/'agent-events.jsonl'
    events=[json.loads(l) for l in events_path.read_text().splitlines()]
    fingerprint=digest({'task':scene.task,'target_ids':scene.targets,'review_mode':scene.evidence_first})
    witness=entry_witness(events,task,TOOL,'claim_id',trace_id=run.name,task_fingerprint=fingerprint)
    for ref in witness['references']:
        actual=scene.read_claim_repair_packet(ref['target_id'])
        if digest(actual)!=ref['observation_sha256']:raise ValueError('actual source/reader replay differs from witnessed result')
    witness.update(events_sha256=hashlib.sha256(events_path.read_bytes()).hexdigest(),
       input_snapshot_sha256=digest(snapshot),source_replay_equal=True,job_id=job_id,
       original_input=str(source),historical_training_stage_estimated_usd=stage['cost'],
       historical_training_stage_model_requests=stage['summaries'][0]['upstream_requests'])
    return witness,source


def learn(output,split):
    output=output.resolve();output.mkdir(mode=0o700,parents=True,exist_ok=False)
    rows=json.loads(split.read_text())
    if len(rows)!=3 or [r['role'] for r in rows]!=['train','train','certify']:raise ValueError('two training jobs and one independent certification job required')
    ids=[r['job_id'] for r in rows]
    cases=[load_witness(i,output) for i in ids]
    tool_schema=asyncio.run(schema(cases[0][1],output/'schema-output'))
    contracts=parse_tool_contracts(CONTRACTS)
    compiled=compile_entry_motif([c[0] for c in cases[:2]],contracts,tool=TOOL,param='claim_id',schema_sha256=digest(tool_schema))
    artifact=certify_entry_motif(compiled,cases[2][0],contracts);library=library_from_certified([artifact])
    policy={'schema_version':1,'format':'sss-entry-read-v1','source_library_digest':library['library_digest'],
      'execution_version_sha256':execution_version(),'artifact':artifact};policy['policy_digest']=digest(policy)
    verifier="import fs from 'node:fs';import {validateEntryPolicy} from './src/motif_core/entry_read_policy.ts';validateEntryPolicy(JSON.parse(fs.readFileSync(0,'utf8')));"
    subprocess.run(['node','--input-type=module','-e',verifier],input=json.dumps(policy),text=True,cwd=ROOT,check=True,capture_output=True)
    for name,value in [('library.json',library),('entry-policy.json',policy),('tool-schema.json',tool_schema),('witnesses.json',[c[0] for c in cases])]:save_private(output/name,value)
    return {'library':str(output),'policy_digest':policy['policy_digest'],'training_target_counts':[c[0]['target_count'] for c in cases[:2]],
      'certification_target_count':cases[2][0]['target_count'],'new_model_requests_for_learning':0,
      'historical_training_and_certification_requests':sum(c[0]['historical_training_stage_model_requests'] for c in cases),
      'historical_training_and_certification_estimated_usd':sum(c[0]['historical_training_stage_estimated_usd'] for c in cases),
      'scope':'three distinct known-corpus workflow decisions; not new-paper generalization'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--split',type=Path,required=True);a=p.parse_args();print(json.dumps(learn(a.output,a.split),ensure_ascii=False))
