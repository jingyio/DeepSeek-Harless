"""Mine and certify local PDF read edges from reviewed, frozen real Harness events."""
from __future__ import annotations
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
from uuid import uuid4
from pdf_tools import ROOT, digest, save_private
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance, mine_witnessed_parameter_edges
from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.motif_core.offline.edge_compiler import compile_witnessed_edge_motif, certify_witnessed_edge_motif
from src.motif_core.offline.library_builder import library_from_certified
PREFIX = 'mcp__literature_pdf__'

def read(path):
    return json.loads(Path(path).read_text())

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

async def schemas(run):
    snapshot = read(run / 'pdf-input-snapshot.json')
    task = snapshot['task']
    task_file = run / 'learning-task.json'; save_private(task_file, task)
    env = os.environ.copy()
    env.update(SSS_PDF_ROOT=task['sources']['root'], SSS_PDF_TASK_FILE=str(task_file),
               SSS_PDF_CACHE=str(ROOT / '.local/literature-notes/pdf-cache'), SSS_PDF_SCRIPT_READ='0')
    env.pop('SSS_PDF_DELIVERY', None)
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / 'pdf_tools.py')], env=env, cwd=ROOT)
    async with Client(params) as client:
        return [{**tool.model_dump(mode='json', by_alias=True), 'name': PREFIX + tool.name}
                for tool in (await client.list_tools()).tools]

def learn(split, output):
    """Certifies execution dependency only; never certifies scientific entailment."""
    rows = read(split)
    if len(rows) != 3 or [r['role'] for r in rows] != ['train', 'train', 'certify']:
        raise ValueError('exactly two training decisions and one held-out certification required')
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / '.local'):
        raise ValueError('learning artifacts must be private')
    contracts_raw = read(HERE / 'pdf-contracts.json')
    contracts = parse_tool_contracts(contracts_raw)
    freezer = module(ROOT / 'scripts/freeze-dsh-task-identity.py', 'pdf_freezer')
    identities, traces, reviews = [], [], []
    for row in rows:
        run = Path(row['run']).resolve()
        if not run.is_relative_to(ROOT / '.local/runs'):
            raise ValueError('only original local run events accepted')
        evidence = read(run / 'evidence.json'); events_path = run / 'agent-events.jsonl'
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        review = read(run / 'quality-review.json')
        import hashlib
        if (review['evidence_sha256'] != digest(evidence)
                or review['events_sha256'] != hashlib.sha256(events_path.read_bytes()).hexdigest()
                or review.get('structural_read_safe') is not True):
            raise ValueError('missing or stale independent structural review')
        if read(run / 'pdf-input-snapshot.json')['execution_options']['mode'] != 'baseline':
            raise ValueError('training must use normal baseline events')
        identity = freezer.freeze(run, row['decision_id'], 'agent-events.jsonl')
        lock = load_trace_identity(identity, events_path, ROOT / '.local'); identities.append(lock)
        traces.append(extract_dsh_trace(events, contracts, trace_id=run.name,
            task_fingerprint=lock['research_decision_id'], provenance_by_call_id=infer_dsh_provenance(events, contracts)))
        reviews.append({'run': str(run), 'role': row['role'], 'review': review})
    require_distinct_decisions(identities)
    actual_schemas = asyncio.run(schemas(Path(rows[0]['run'])))
    contracts = bind_mcp_descriptions(contracts, actual_schemas)
    # Only this read dependency has a closed argument set. Page selection remains semantic.
    candidates = [c for c in mine_witnessed_parameter_edges(traces[:2])
                  if c['from_tool'] == PREFIX + 'pin_pdf_context' and c['to_tool'] == PREFIX + 'read_pinned_pdf_context']
    artifacts = [certify_witnessed_edge_motif(compile_witnessed_edge_motif(c, traces[:2], contracts), traces[2], contracts)
                 for c in candidates]
    if not artifacts:
        raise ValueError('no witnessed, independently certified closed PDF read edge')
    library = library_from_certified(artifacts)
    exporter = module(ROOT / 'scripts/export-online-motif-manifest.py', 'pdf_exporter')
    manifest = exporter.export_manifest(library, contracts_raw, version_fields=read(HERE / 'pdf-version-fields.json'))
    import subprocess
    verifier = 'import fs from \"node:fs\"; import {validateOnlineManifest} from \"./src/motif_core/online_skill_runtime.mjs\"; validateOnlineManifest(JSON.parse(fs.readFileSync(0,\"utf8\")));'
    subprocess.run(['node', '--input-type=module', '-e', verifier], input=json.dumps(manifest), text=True, cwd=ROOT, check=True, capture_output=True)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    save_private(output / 'library.json', library); save_private(output / 'online-manifest.json', manifest)
    save_private(output / 'mcp-schemas.json', actual_schemas)
    save_private(output / 'learning-provenance.json', {
        'scope': 'controlled_real_model_same_private_PDF_corpus', 'identities': identities, 'reviews': reviews,
        'decision_ids_authority': 'agent-designed experimental distinctions, not individually human-confirmed',
        'candidates': candidates, 'certification_scope': 'parameter provenance, read-only dependency and version guards',
        'human_blind_review_completed': False, 'production_quality_qualified': False,
        'limits': ['read edge only; no automatic relevance, claim entailment or summary reuse',
                   'runtime only bypasses anchors whose optional parameters equal contract defaults',
                   'document-level version scopes, with exact issued-window source_id binding; custom windows still defer']})
    return {'output': str(output), 'certified_motifs': len(artifacts), 'manifest_digest': manifest['manifest_digest'],
            'scientific_quality_certified': False}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/literature-notes' / ('learned-' + uuid4().hex))
    args = parser.parse_args(); print(json.dumps(learn(args.split, args.output), ensure_ascii=False))
