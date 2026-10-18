#!/usr/bin/env python3
"""Opt-in experiment launcher using the unchanged native Web/Agent loop.

Only generated private host wiring changes. Existing production code, registry
and certified libraries are not edited or relocked by this entry point.
"""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_web',ROOT/'scripts/harness-web.py')
web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)
original=web.prepare
def prepare(args,output,endpoint):
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
if __name__=='__main__':web.main()
