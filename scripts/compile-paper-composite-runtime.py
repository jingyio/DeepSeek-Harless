#!/usr/bin/env python3
"""Revalidate two historical read chains against the current paper MCP schema.

The reviewed PDF renderer is packaged as a guarded model tool. It is deliberately
not promoted to an automatic read-only Motif skip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.harless_paper_renderer import configure_paper_renderer
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.motif_core.offline.library_builder import library_from_certified, validate_read_motif_library
from src.motif_core.read_executor import _validate_artifact
from src.motif_core.offline.trace_compiler import artifact_signature, contract_signature

import importlib.util
spec = importlib.util.spec_from_file_location('export_paper_motif', ROOT / 'scripts/export-online-motif-manifest.py')
exporter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(exporter)

READ_PAIR = ('mcp__paper_checks__pin_paper_sources', 'mcp__paper_checks__read_pinned_paper_sources')
CITATION_PAIR = ('mcp__paper_checks__pin_paper_citations', 'mcp__paper_checks__read_pinned_paper_citations')
# These Session-local paper tools are observed but never emitted by a Motif.
# They cannot invalidate an unrelated, versioned pin/read edge when they
# succeed; failures and the PDF write still remain barriers.
OBSERVED_READS = {
    'mcp__paper_checks__list_inputs': {
        'required_params': [], 'read_only': True, 'replay_stable': True,
        'output_fields': [], 'description': 'List approved task inputs.'},
    'mcp__paper_checks__pin_document': {
        'required_params': ['name', 'sha256'], 'read_only': True,
        'replay_stable': False, 'observed_anchor': True,
        'output_fields': [], 'description': 'Pin another approved Session file.'},
    'mcp__paper_checks__read_pinned_document': {
        'required_params': ['source_id'], 'read_only': True,
        'replay_stable': True, 'output_fields': [],
        'description': 'Read another Session-local pinned file.'},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path: Path, value: object):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)


def compile_runtime(citation_dir: Path, uploaded_dir: Path, schemas_path: Path,
                    renderer_root: Path, output: Path):
    private = (ROOT / '.local').resolve()
    sources = [citation_dir, uploaded_dir, schemas_path, renderer_root]
    sources = [p.resolve(strict=True) for p in sources]
    output = output.resolve()
    if any(not p.is_relative_to(private) for p in [*sources, output]):
        raise ValueError('paper composite sources and output must remain private')
    citation_dir, uploaded_dir, schemas_path, renderer_root = sources
    if output.exists(): raise FileExistsError(output)
    raw_schema = read(schemas_path)
    scenario = read(ROOT / 'scenarios/paper_proofreading/scenario.json')
    if (not isinstance(raw_schema, list) or len(raw_schema) != 17 or
            [row['name'] for row in raw_schema] != sorted(scenario['allowed_tools'])):
        raise ValueError('actual complete paper MCP schema required')
    schema = [{'name': row['name'], 'description': row['description'],
               'parameters': row.get('parameters', row.get('input_schema', row.get('inputSchema')))}
              for row in raw_schema]
    if any(not isinstance(row['parameters'], dict) for row in schema):
        raise ValueError('MCP schema needs actual input parameters')
    citation, uploaded = read(citation_dir / 'library.json'), read(uploaded_dir / 'library.json')
    validate_read_motif_library(citation)
    validate_read_motif_library(uploaded)
    wanted = [READ_PAIR, CITATION_PAIR]
    by_pair = {tuple(row['tools']): row for row in citation['artifacts'] + uploaded['artifacts']
               if len(row.get('tools', [])) == 2}
    if any(pair not in by_pair for pair in wanted):
        raise ValueError('historical citation or uploaded-read evidence missing')
    contracts = read(ROOT / 'scenarios/paper_proofreading/motif-contracts.json')
    contracts.update(OBSERVED_READS)
    legacy = read(citation_dir / 'contracts.json')
    _validate_artifact(by_pair[CITATION_PAIR], parse_tool_contracts(legacy))
    for name in CITATION_PAIR:
        contracts[name] = legacy[name]
    # Narrow the old fixed-case certificate: the Web Session pin must first be
    # observed after the model selects "current". The original artifact is
    # checked above before changing its contract signature and digest.
    contracts[CITATION_PAIR[0]] = {**contracts[CITATION_PAIR[0]],
                                  'replay_stable': False, 'observed_anchor': True}
    bound = bind_mcp_descriptions(parse_tool_contracts(contracts),
                                  {'tools': [{**row, 'inputSchema': row['parameters']} for row in schema]})
    contracts = {name: {**row, 'description': bound[name].description}
                 for name, row in contracts.items()}
    migrated = {**by_pair[CITATION_PAIR],
                'contract_signature': contract_signature(list(CITATION_PAIR), parse_tool_contracts(contracts))}
    migrated['certified_digest'] = artifact_signature(migrated)
    _validate_artifact(migrated, parse_tool_contracts(contracts))
    library = library_from_certified([by_pair[READ_PAIR], migrated])
    versions = {name: 'version_sha256' for pair in wanted for name in pair}
    manifest = exporter.export_manifest(library, contracts,
        {CITATION_PAIR[0]: {'case_id': 'current'}}, versions)
    scene = {'id': 'paper-proofreading', 'mcp_rows': [{'config': {'serverName': 'paper_checks', 'args': []}}],
             'config_sha256': '0' * 64}
    configure_paper_renderer(scene, renderer_root)
    output.mkdir(parents=True, mode=0o700)
    runtime = output / 'runtime'
    runtime.mkdir(mode=0o700)
    save(runtime / 'library.json', library)
    save(runtime / 'online-manifest.json', manifest)
    save(runtime / 'tool-schemas.json', schema)
    save(runtime / 'task.json', {'schema_version': 1, 'task_id': 'paper-composite-admission',
        'session_id': 'paper-composite-admission', 'intent': 'Read approved paper sources.',
        'input_version': '0' * 64, 'bindings': {}, 'source_versions': {
            READ_PAIR[0]: '@observed', READ_PAIR[1]: '@from_anchor',
            CITATION_PAIR[0]: '@observed', CITATION_PAIR[1]: '@from_anchor'}})
    save(output / 'capabilities.json', {
        'schema_version': 1, 'read_motifs': [list(pair) for pair in wanted],
        'citation_records': {'tool': 'mcp__paper_checks__read_pinned_citation_records',
                             'execution': 'model_invoked_only',
                             'historical_artifact_retained_sha256':
                                 next((row['certified_digest'] for row in citation['artifacts']
                                       if row.get('tools') == list(('mcp__paper_checks__read_pinned_paper_citations',
                                                                    'mcp__paper_checks__read_pinned_citation_records'))), None)},
        'pdf_export': {'tool': 'mcp__paper_checks__export_current_audit_pdf',
            'execution': 'model_invoked_only', 'rsi_verified_skip': False,
            'guard': 'task_grant_and_report_sha256_and_reviewed_renderer',
            'renderer_manifest_sha256': sha(renderer_root / 'package/manifest.json'),
            'renderer_review_sha256': sha(renderer_root / 'review.json')},
        'quality_cost_promoted': False})
    code = ['src/adapters/harless_rsi_binding.ts', 'src/adapters/harless_rsi_bundle.py',
            'src/adapters/harless_task_scope.ts', 'src/adapters/harless_paper_renderer.py',
            'src/adapters/paper_renderer.py', 'src/adapters/session_files.py',
            'scenarios/paper_proofreading/server.py', 'scenarios/paper-submission/checks.py',
            'src/adapters/paper_bibliography.py', 'src/adapters/arxiv_metadata.py',
            'src/adapters/crossref_metadata.py', 'src/adapters/paper_query_recovery.py',
            'src/adapters/dsh_web_tasks.ts', 'src/motif_core/online_skill_runtime.mjs']
    evidence = {'citation_library_sha256': sha(citation_dir / 'library.json'),
                'uploaded_library_sha256': sha(uploaded_dir / 'library.json'),
                'current_mcp_schema_sha256': sha(schemas_path),
                'renderer_deployment_sha256': sha(renderer_root / 'deployment.json'),
                'source_artifact_digests': [by_pair[p]['certified_digest'] for p in wanted],
                'migrated_citation_artifact_digest': migrated['certified_digest']}
    save(output / 'evidence-lock.json', evidence)
    report = {'status': 'compiled_read_subset_and_guarded_output_tool',
              'artifact_count': len(wanted), 'pdf_auto_execute': False,
              'old_shadow_rate_is_not_new_skip_rate': True,
              'renderer_quality_reviewed': False}
    save(output / 'learning-report.json', report)
    save(runtime / 'certification.json', {
        'schema_version': 1, 'scene': 'paper-proofreading',
        'certification_scope': 'independent_trace_structure',
        'binding_policy': 'approved_uploaded_reads_v1', 'matching_policy': 'structural_only',
        'quality_cost_promoted': False, 'manifest_digest': manifest['manifest_digest'],
        'source_evidence_sha256': sha(output / 'evidence-lock.json'),
        'learning_report_sha256': sha(output / 'learning-report.json'),
        'file_locks': {p.name: sha(p) for p in runtime.iterdir() if p.is_file()},
        'code_locks': {name: sha(ROOT / name) for name in sorted(code)}})
    return {'runtime': str(runtime), 'read_motifs': len(wanted),
            'pdf_export': 'guarded_model_tool', 'model_requests': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('citation-library', 'uploaded-library', 'schemas', 'renderer-deployment', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compile_runtime(args.citation_library, args.uploaded_library,
                                     args.schemas, args.renderer_deployment, args.output)))


if __name__ == '__main__': main()
