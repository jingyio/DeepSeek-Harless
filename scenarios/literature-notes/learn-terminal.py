"""Certify only original receipt -> final response -> stop decisions, with current source replay."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from mcp import Client, StdioServerParameters
from pdf_tools import ROOT, PdfScene, digest, save_private
from pdf_dependencies import private_file
from pdf_repair_tools import RepairScene
from terminal_entry import TOOL, entry_task, execution_version
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.terminal_compiler import terminal_witness, compile_terminal, certify_terminal
from src.motif_core.offline.library_builder import library_from_certified

CONTRACTS = parse_tool_contracts({TOOL: {'read_only': True, 'replay_stable': False,
    'required_params': ['decisions', 'synthesis_hypothesis']}})


def load_witness(output):
    output = private_file(Path(output) / 'outcome.json').parent
    result = json.loads((output / 'outcome.json').read_text())
    snapshot = json.loads((output / 'input-snapshot.json').read_text())
    run = private_file(Path(result['run']['output_dir']) / 'preview.json').parent
    preview = json.loads((run / 'preview.json').read_text())
    if (preview['mode'] != 'baseline' or preview.get('tool_presentation', 'native') != 'native'
            or preview.get('entry_policy_digest') or preview.get('terminal_policy_digest') or preview.get('manifest_digest')
            or not preview['model_call_enabled'] or result.get('receipt_origin') != 'native_tool_submission'
            or snapshot.get('terminal_execution_version_sha256') != execution_version()):
        raise ValueError('current original native producer/stop decisions required')
    scene = RepairScene(Path(snapshot['original_input']), output)
    task = entry_task(scene, run.name)
    events_path = run / 'agent-events.jsonl'
    events = [json.loads(l) for l in events_path.read_text().splitlines()]
    witness = terminal_witness(events, TOOL, trace_id=run.name,
        task_fingerprint=digest({'task': scene.task, 'input': scene.input_digest, 'request': scene.request_digest}),
        input_version=scene.input_digest, request_version=scene.request_digest, target_ids=scene.targets)
    if witness['receipt'] != result['receipt']: raise ValueError('collected receipt differs from original tool event')
    checker = "import fs from 'node:fs';import {verifyRepairReceipt} from './src/motif_core/terminal_receipt_policy.ts';const x=JSON.parse(fs.readFileSync(0,'utf8'));if(!verifyRepairReceipt(x.receipt,x.task))throw Error('unbound terminal source');"
    subprocess.run(['node', '--input-type=module', '-e', checker], input=json.dumps({'receipt': witness['receipt'], 'task': task}),
        cwd=ROOT, text=True, check=True, capture_output=True)
    payload = json.loads(private_file(witness['receipt']['artifact']).read_text())
    replay = PdfScene(scene.scene.root, scene.scene.cache, scene.task)
    for c in payload['citation_checks']:
        p = replay.pin_pdf_context(c['paper_id'], str(c['page']), c['start'], c['end'] - c['start'])
        if p['source_id'] != c['source_id'] or p['version_sha256'] != c['version_sha256']:
            raise ValueError('published quote source changed')
        replay.read_pinned_pdf_context(p['source_id'])
    checked = replay.preview_research_notes(payload['draft'])
    if checked['citation_checks'] != payload['citation_checks'] or checked['gaps'] != payload['gaps']:
        raise ValueError('current published citations or gaps differ')
    ledger = [json.loads(l) for l in (run / 'cost-ledger.jsonl').read_text().splitlines()]
    witness.update(events_sha256=hashlib.sha256(events_path.read_bytes()).hexdigest(), source_replay_equal=True,
        historical_stage_requests=len(ledger), historical_stage_estimated_usd=sum(v.get('observed_peak_usd', 0) for v in ledger),
        terminal_estimated_usd=ledger[-1].get('observed_peak_usd', 0))
    return witness, scene


async def schema(scene):
    env = {**os.environ, 'SSS_PDF_REPAIR_RUN': str(scene.run), 'SSS_PDF_REPAIR_OUTPUT': str(scene.output)}
    env.pop('DEEPSEEK_API_KEY', None)
    async with Client(StdioServerParameters(command=sys.executable, args=[str(HERE / 'pdf_repair_tools.py')], cwd=ROOT, env=env)) as client:
        tool = next(t for t in (await client.list_tools()).tools if t.name == 'submit_claim_repair')
        if not tool.annotations.read_only_hint: raise ValueError('terminal source must be declared read-only')
        return tool.model_dump(mode='json', by_alias=True)['inputSchema']


def learn(output, split):
    if output.is_symlink() or not output.resolve().is_relative_to(ROOT / '.local'): raise ValueError('private output required')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    s = json.loads(private_file(split).read_text())
    if len(s['training_runs']) != 2: raise ValueError('two original training tasks required')
    cases = [load_witness(r) for r in s['training_runs'] + [s['certification_run']]]
    actual = asyncio.run(schema(cases[0][1]))
    if any(asyncio.run(schema(c[1])) != actual for c in cases[1:]): raise ValueError('producer schemas differ')
    compiled = compile_terminal([c[0] for c in cases[:2]], CONTRACTS, tool=TOOL, schema=actual)
    artifact = certify_terminal(compiled, cases[-1][0], CONTRACTS)
    library = library_from_certified([artifact])
    policy = {'schema_version': 1, 'format': 'sss-terminal-receipt-v1', 'source_library_digest': library['library_digest'],
        'execution_version_sha256': execution_version(), 'artifact': artifact}
    policy['policy_digest'] = digest(policy)
    verifier = "import fs from 'node:fs';import {validateTerminalPolicy} from './src/motif_core/terminal_receipt_policy.ts';validateTerminalPolicy(JSON.parse(fs.readFileSync(0,'utf8')));"
    subprocess.run(['node', '--input-type=module', '-e', verifier], input=json.dumps(policy), text=True, cwd=ROOT, check=True, capture_output=True)
    for name, value in [('entry-policy.json', policy), ('library.json', library), ('witnesses.json', [c[0] for c in cases])]: save_private(output / name, value)
    report = {'policy_digest': policy['policy_digest'], 'training_counts': [c[0]['target_count'] for c in cases[:2]],
        'certification_count': cases[-1][0]['target_count'], 'statuses': artifact['terminal']['statuses'],
        'original_terminal_requests': sum(c[0]['provider_requests'] for c in cases),
        'historical_stage_requests': sum(c[0]['historical_stage_requests'] for c in cases),
        'historical_stage_estimated_usd': sum(c[0]['historical_stage_estimated_usd'] for c in cases),
        'source_and_quote_replay_equal': True, 'new_compilation_requests': 0}
    save_private(output / 'outcome.json', report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); p.add_argument('--split', type=Path, required=True)
    a = p.parse_args(); print(json.dumps(learn(a.output.resolve(), a.split.resolve())))
