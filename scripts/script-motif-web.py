#!/usr/bin/env python3
"""Opt-in experiment launcher using the unchanged native Web/Agent loop.

Only generated private host wiring changes. Existing production code, registry
and certified libraries are not edited or relocked by this entry point.
"""
import importlib.util
import json
import sys
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_web',ROOT/'scripts/harness-web.py')
web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)
# Experimental explicit output cap: keep the production CLI/certificate frozen.
# Native State and prepare receive the same cap; no accounting/admission bypass.
OUTPUT_CAP=None
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
    custom,rest=parser.parse_known_args()
    OUTPUT_CAP=custom.script_max_output_tokens
    if OUTPUT_CAP is not None and not 100<=OUTPUT_CAP<=32768:parser.error('script output cap must be 100..32768')
    sys.argv=[sys.argv[0],*rest]
    web.main()
