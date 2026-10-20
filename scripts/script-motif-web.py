#!/usr/bin/env python3
"""Opt-in experiment launcher using the unchanged native Web/Agent loop.

Only generated private host wiring changes. Existing production code, registry
and certified libraries are not edited or relocked by this entry point.
"""
import importlib.util
import json
import sys
import argparse
import hashlib
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_web',ROOT/'scripts/harness-web.py')
web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)
if os.environ.get('SSS_RETRIEVAL_EVIDENCE')=='1':
    from src.adapters.search_evidence_accounting import instrument_search_server
    original_server=web.create_server
    def create_server(*args,**kwargs):
        return instrument_search_server(original_server(*args,**kwargs))
    web.create_server=create_server
# Experimental explicit output cap: keep the production CLI/certificate frozen.
# Native State and prepare receive the same cap; no accounting/admission bypass.
OUTPUT_CAP=None
REPORT_EVIDENCE=False
original_scenes=web.prepare_scene_registry
def experiment_scenes(*args,**kwargs):
    scenes=original_scenes(*args,**kwargs)
    if REPORT_EVIDENCE:
        locks={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['scripts/paper-evidence-server.py','src/adapters/evidence_report.py','src/adapters/session_report.py','benchmarks/research_report_agent_v2/document_engine.py']}
        for scene in scenes:
            if scene['id']!='paper-proofreading':continue
            for row in scene['mcp_rows']:
                if row['config']['serverName']=='paper_checks':
                    row['config']['args'][0]=str(ROOT/'scripts/paper-evidence-server.py')
            scene['experimental_report_evidence']={'code_hashes':locks,'production_certified':False}
            scene['config_sha256']=hashlib.sha256(json.dumps({'prior':scene['config_sha256'],'report_evidence':locks},sort_keys=True).encode()).hexdigest()
    return scenes
web.prepare_scene_registry=experiment_scenes
original_state=web.State
def experiment_state(*args,**kwargs):
    if OUTPUT_CAP is not None:kwargs['output_cap']=OUTPUT_CAP
    return original_state(*args,**kwargs)
web.State=experiment_state
original=web.prepare
def prepare(args,output,endpoint):
    if OUTPUT_CAP is not None:args.max_output_tokens=OUTPUT_CAP
    original(args,output,endpoint)
    path=output/'host.patch.yml';patch=json.loads(path.read_text())
    replacements={
        (ROOT/'src/adapters/harless_web_client/index.mjs').as_uri():(ROOT/'src/adapters/script_motif_web.ts').as_uri(),
        (ROOT/'src/adapters/geneloop_shell.ts').as_uri():(ROOT/'src/adapters/script_motif_shell.ts').as_uri(),
    }
    if os.environ.get('SSS_RETRIEVAL_EVIDENCE')=='1':
        replacements[(ROOT/'src/adapters/geneloop_web_search.ts').as_uri()]=(ROOT/'src/adapters/retrieval_web_search.ts').as_uri()
    for row in patch:
        for plugin in row.get('insert',[]):
            if plugin.get('name') in replacements:plugin['name']=replacements[plugin['name']]
    web.save(path,patch)
    effective=output/'effective-config.json'
    if effective.exists():
        value=json.loads(effective.read_text());value['script_motif_experiment']=True;web.save(effective,value)
web.prepare=prepare
if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--script-max-output-tokens',type=int)
    parser.add_argument('--report-evidence',action='store_true')
    custom,rest=parser.parse_known_args()
    OUTPUT_CAP=custom.script_max_output_tokens
    REPORT_EVIDENCE=custom.report_evidence
    if OUTPUT_CAP is not None and not 100<=OUTPUT_CAP<=32768:parser.error('script output cap must be 100..32768')
    sys.argv=[sys.argv[0],*rest]
    web.main()
