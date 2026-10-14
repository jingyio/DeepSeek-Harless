"""Compile a three-node evidence chain from normal, source-reviewed Harness traces."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from pdf_tools import ROOT, digest, save_private
from pdf_evidence_tools import PREFIX

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance, mine_witnessed_parameter_edges
from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.motif_core.offline.chain_compiler import compile_witnessed_chain_motif, certify_witnessed_chain_motif
from src.motif_core.offline.library_builder import library_from_certified


def read(path):
    return json.loads(Path(path).read_text())


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


async def schemas(run):
    snapshot = read(run / 'evidence-input-snapshot.json')
    task_file = run / 'evidence-learning-task.json'
    save_private(task_file, snapshot['task'])
    env = {**os.environ, 'SSS_PDF_ROOT': snapshot['task']['sources']['root'],
           'SSS_PDF_TASK_FILE': str(task_file), 'SSS_PDF_CACHE': str(run / 'learning-cache'),
           'SSS_PDF_CACHE_POLICY': 'reuse', 'SSS_PDF_DELIVERY': str(run / 'learning-delivery'),
           'SSS_EVIDENCE_SCRIPT_CHAIN': '0'}
    async with Client(StdioServerParameters(command=sys.executable, args=[str(HERE / 'pdf_evidence_tools.py')],
                                            cwd=ROOT, env=env)) as client:
        return [{**tool.model_dump(mode='json', by_alias=True), 'name': PREFIX + tool.name}
                for tool in (await client.list_tools()).tools]


def learn(split, output):
    rows = read(split)
    if not isinstance(rows, list) or len(rows) != 3 or [r['role'] for r in rows] != ['train', 'train', 'certify']:
        raise ValueError('two training decisions and one independent certification decision required')
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / '.local') or output.exists():
        raise ValueError('learning output must be a new private directory')
    contracts_raw = read(HERE / 'pdf-evidence-contracts.json')
    contracts = parse_tool_contracts(contracts_raw)
    freezer = module(ROOT / 'scripts/freeze-dsh-task-identity.py', 'evidence_freezer')
    identities, traces, reviews = [], [], []
    for row in rows:
        run = Path(row['run']).resolve()
        if not run.is_relative_to(ROOT / '.local/runs'):
            raise ValueError('learning requires original shared-runner events')
        snapshot = read(run / 'evidence-input-snapshot.json')
        options = snapshot['execution_options']
        if options.get('tool_presentation', 'native') != 'native' or options.get('mode') != 'baseline' or options.get('script_chain') is not False or options.get('model_call_enabled') is not True:
            raise ValueError('only normal real-model baseline decisions can train this library')
        packet = read(run / 'evidence-packet.json')
        events_path = run / 'agent-events.jsonl'
        review = read(run / 'evidence-structural-review.json')
        if (review.get('packet_sha256') != digest(packet)
                or review.get('events_sha256') != hashlib.sha256(events_path.read_bytes()).hexdigest()
                or review.get('structural_chain_safe') is not True):
            raise ValueError('missing or stale source-bound structural review')
        # Independently replay current source windows, not the model's final status.
        from pdf_evidence_tools import EvidenceScene
        scene = EvidenceScene(Path(snapshot['task']['sources']['root']), run / 'learning-check-cache',
                              snapshot['task'], delivery=run / 'learning-check-delivery')
        scene.validate_packet(packet)
        identity = freezer.freeze(run, row['decision_id'], 'agent-events.jsonl')
        lock = load_trace_identity(identity, events_path, ROOT / '.local')
        identities.append(lock)
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        traces.append(extract_dsh_trace(events, contracts, trace_id=run.name,
                       task_fingerprint=lock['research_decision_id'],
                       provenance_by_call_id=infer_dsh_provenance(events, contracts)))
        reviews.append({'run': str(run), 'role': row['role'], 'review': review})
    require_distinct_decisions(identities)
    actual_schemas = asyncio.run(schemas(Path(rows[0]['run'])))
    contracts = bind_mcp_descriptions(contracts, actual_schemas)
    candidates = mine_witnessed_parameter_edges(traces[:2])
    tools = [PREFIX + name for name in ('extract_evidence_windows', 'verify_evidence_windows', 'build_evidence_packet')]
    pairs = [(a, b) for a in candidates for b in candidates
             if (a['from_tool'], a['to_tool'], b['from_tool'], b['to_tool']) == (tools[0], tools[1], tools[1], tools[2])]
    artifacts = [certify_witnessed_chain_motif(compile_witnessed_chain_motif(a, b, traces[:2], contracts),
                                             traces[2], contracts) for a, b in pairs]
    if len(artifacts) != 1:
        raise ValueError('expected one unambiguous, connected and independently witnessed evidence chain')
    library = library_from_certified(artifacts)
    exporter = module(ROOT / 'scripts/export-online-motif-manifest.py', 'evidence_exporter')
    manifest = exporter.export_manifest(library, contracts_raw,
                                       version_fields=read(HERE / 'pdf-evidence-version-fields.json'))
    verifier = 'import fs from "node:fs"; import {validateOnlineManifest} from "./src/motif_core/online_skill_runtime.mjs"; validateOnlineManifest(JSON.parse(fs.readFileSync(0,"utf8")));'
    subprocess.run(['node', '--input-type=module', '-e', verifier], input=json.dumps(manifest),
                   cwd=ROOT, text=True, capture_output=True, check=True)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    save_private(output / 'library.json', library)
    save_private(output / 'online-manifest.json', manifest)
    save_private(output / 'mcp-schemas.json', actual_schemas)
    save_private(output / 'learning-provenance.json', {'identities': identities, 'reviews': reviews,
                 'mined_candidates': candidates, 'scope': 'bounded source preparation parameter chain',
                 'decision_ids_authority': 'agent-designed distinct questions, not independent consumers',
                 'scientific_quality_certified': False, 'heldout_corpus_generalization_established': False,
                 'limits': ['model still selects the plan', 'bounded window iteration lives in prebuilt tools',
                            'no learned parser selection, relevance, entailment or complete workflow discovery']})
    return {'output': str(output), 'certified_motifs': 1, 'tool_nodes': 3,
            'manifest_digest': manifest['manifest_digest'], 'scientific_quality_certified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/literature-notes' / ('evidence-library-' + uuid4().hex))
    args = parser.parse_args()
    print(json.dumps(learn(args.split, args.output), ensure_ascii=False))
