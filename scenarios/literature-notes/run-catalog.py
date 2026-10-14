"""Create/update a PDF bibliography through the existing native Harness and budget."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
from pdf_tools import ROOT, digest, inventory, save_private
from pdf_dependencies import private_file
from pdf_catalog_tools import CatalogScene, DEFAULT_CATALOG_QUESTION, execution_version, HERE
from catalog_entry import entry_task, private_policy

TOOL = 'mcp__literature_catalog__submit_catalog'


def collect(model_run, scene):
    events = [json.loads(l) for l in (model_run/'agent-events.jsonl').read_text().splitlines()]
    receipts = []
    for event in events:
        if event['type'] != 'tool/result': continue
        for block in event['data']['message']['content']:
            if block.get('type') == 'tool-result' and block.get('toolName') == TOOL and not block.get('isError'):
                receipts.append(json.loads(block['content'][0]['text']))
    # SDK blocks may omit toolName; resolve actual call IDs without synthetic projection.
    if not receipts:
        calls = {e['data']['callId']:e['data']['name'] for e in events if e['type']=='tool/call'}
        for event in events:
            if event['type'] != 'tool/result': continue
            for block in event['data']['message']['content']:
                if calls.get(block.get('toolCallId')) == TOOL and not block.get('isError'):
                    receipts.append(json.loads(block['content'][0]['text']))
    if not receipts: return None
    receipt = receipts[-1]; artifact = private_file(receipt['artifact'])
    if artifact != scene.output/'catalog.json': raise ValueError('unexpected catalog receipt location')
    envelope = json.loads(artifact.read_text()); payload = envelope['catalog']
    if (digest(envelope) != receipt['artifact_sha256'] or digest(payload) != envelope['catalog_sha256']
            or digest(payload) != receipt['catalog_sha256']):
        raise ValueError('catalog receipt digest changed')
    scene.read_catalog_plan()
    for row in scene._plan()['work']: scene.read_catalog_packet(row['paper_id'])
    if scene.publish(payload['submitted_entries'], persist=False) != payload:
        raise ValueError('current catalog source or retained metadata differs')
    bib = private_file(receipt['bibtex'])
    import hashlib
    if (bib != scene.output/'catalog.bib' or bib.read_text() != payload['bibliography']
            or hashlib.sha256(bib.read_bytes()).hexdigest() != receipt['bibtex_sha256']):
        raise ValueError('bibliography artifact changed')
    return receipt


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--papers-dir', type=Path, default=ROOT/'testpdf')
    p.add_argument('--previous', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--question', default=DEFAULT_CATALOG_QUESTION)
    p.add_argument('--entry-policy', type=Path)
    p.add_argument('--call-model', action='store_true')
    p.add_argument('--budget-usd', type=float, default=.25)
    p.add_argument('--max-steps', type=int, default=12)
    p.add_argument('--max-output', type=int, default=6500)
    a = p.parse_args(argv)
    if not 0<a.budget_usd<=100 or not 1<=a.max_steps<=100 or not 1<=a.max_output<=8000:
        p.error('invalid budget/steps/output limits')
    out = a.output or ROOT/'.local/literature-notes/catalog-runs'/uuid4().hex
    if out.is_symlink() or not out.resolve().is_relative_to(ROOT/'.local'):
        p.error('output must remain under project .local')
    out = out.resolve(); out.mkdir(parents=True, mode=0o700, exist_ok=False)
    started = time.monotonic()
    previous = out/'previous-catalog.json' if a.previous else None
    if previous: save_private(previous, json.loads(private_file(a.previous).read_text()))
    task = {'schema_version':1, 'question':a.question, 'sources':inventory(a.papers_dir)}
    save_private(out/'task.json', task)
    scene = CatalogScene(a.papers_dir, task, out, previous=previous); plan = scene.read_catalog_plan()
    policy = private_policy(a.entry_policy) if a.entry_policy else None
    snapshot = {'task':task, 'task_sha256':digest(task), 'plan_sha256':plan['plan_sha256'],
                'execution_version_sha256':execution_version(), 'entry_policy_digest':policy['policy_digest'] if policy else None,
                'mode':'baseline', 'tool_presentation':'native', 'reasoning_effort':'off',
                'model':'deepseek-flash', 'budget_cap_usd':a.budget_usd, 'max_steps':a.max_steps,
                'max_output':a.max_output, 'model_call_enabled':a.call_model,
                'previous_catalog_sha256':plan['previous_catalog_sha256'], 'metadata_verified_online':False}
    save_private(out/'input-snapshot.json', snapshot); save_private(out/'plan.json', plan)
    print(json.dumps({'catalog_directory':str(out), 'work_count':len(plan['work']), 'retained_count':len(plan['retained_ids']),
                      'budget_cap_usd':a.budget_usd, 'model_call_enabled':a.call_model,
                      'entry_policy_digest':snapshot['entry_policy_digest'], 'user_file_writes_enabled':False}), flush=True)
    if not plan['work']:
        if not a.call_model: return 0
        receipt = scene.publish([])
        result = {'status':receipt['status'], 'receipt':receipt, 'run':None, 'model_requests':0,
                  'budget_accounted_usd':0, 'learned_motif':False, 'scope':'ordinary unchanged-catalog reuse',
                  'elapsed_seconds':round(time.monotonic()-started,3)}
        save_private(out/'outcome.json', result); print(json.dumps(result)); return 0
    config = json.loads((HERE/'pdf-catalog-scenario.json').read_text())
    if not previous:
        # from_env is required by the shared entry; omit this optional reference for first import.
        config['servers'][0]['env'].pop('SSS_PDF_CATALOG_PREVIOUS')
    config['prompt'] = str(HERE/'pdf-catalog-task.md'); save_private(out/'scenario.json', config)
    env = {**os.environ, 'SSS_PDF_TASK_FILE':str(out/'task.json'), 'SSS_PDF_CATALOG_OUTPUT':str(out),
           'SSS_PDF_CATALOG_PREVIOUS':str(previous) if previous else ''}
    command = [sys.executable, str(ROOT/'scripts/run-scenario.py'), '--scenario', str(out/'scenario.json'),
               '--model','deepseek-flash','--budget-usd',str(a.budget_usd),'--max-steps',str(a.max_steps),
               '--max-output',str(a.max_output)]
    if policy:
        save_private(out/'entry-task.json', {**entry_task(scene,out.name), 'session_id':'catalog-'+uuid4().hex})
        command += ['--entry-policy',str(a.entry_policy),'--entry-task',str(out/'entry-task.json')]
    if a.call_model:
        spec=importlib.util.spec_from_file_location('catalog_key_loader', HERE/'run-live.py')
        loader=importlib.util.module_from_spec(spec); spec.loader.exec_module(loader)
        env['DEEPSEEK_API_KEY']=loader.load_key(loader.KEY_FILE,env); command.append('--call-model')
    result = subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True)
    print(result.stdout,end='',flush=True)
    if result.stderr: print(result.stderr,file=sys.stderr,end='')
    if not a.call_model: return result.returncode
    summaries=[]
    for line in result.stdout.splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict) and 'output_dir' in row: summaries.append(row)
        except ValueError: pass
    summary=summaries[-1] if summaries else None
    receipt=collect(private_file(Path(summary['output_dir'])/'preview.json').parent,scene) if summary else None
    status = ('incomplete_catalog' if summary and summary.get('status') != 'done' else receipt['status']) if receipt else 'missing_catalog'
    outcome={'status':status,'receipt':receipt,'run':summary,
             'elapsed_seconds':round(time.monotonic()-started,3),'input':snapshot}
    save_private(out/'outcome.json',outcome)
    print(json.dumps({'catalog_directory':str(out),'status':outcome['status'],'receipt':receipt,
                      'elapsed_seconds':outcome['elapsed_seconds']}),flush=True)
    return result.returncode or (0 if receipt else 2)


if __name__=='__main__': raise SystemExit(main())
