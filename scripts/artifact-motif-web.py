#!/usr/bin/env python3
"""Opt-in native Web experiment; production services and bundles stay frozen."""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('artifact_native_web', ROOT / 'scripts/harness-web.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)
original_prepare = web.prepare


def prepare(args, output, endpoint):
    original_prepare(args, output, endpoint)
    path = output / 'host.patch.yml'
    patch = json.loads(path.read_text(encoding='utf-8'))
    replacements = {
        (ROOT / 'src/adapters/harless_web_client/index.mjs').as_uri(): (ROOT / 'src/adapters/artifact_motif_web.ts').as_uri(),
        (ROOT / 'src/adapters/geneloop_shell.ts').as_uri(): (ROOT / 'src/adapters/artifact_motif_shell.ts').as_uri(),
    }
    for row in patch:
        for plugin in row.get('insert', []):
            if plugin.get('name') in replacements:
                plugin['name'] = replacements[plugin['name']]
    web.save(path, patch)
    snapshot = json.loads((output / 'effective-config.json').read_text(encoding='utf-8'))
    snapshot['artifact_motif_experiment'] = {'enabled': True, 'model_owned_selection': True, 'production_promoted': False}
    web.save(output / 'effective-config.json', snapshot)


web.prepare = prepare
# A supplied private canonical ledger remains append-only. No experiment reset.
if os.environ.get('GENELOOP_ARTIFACT_LEDGER'):
    original_state = web.State

    def state(*args, **kwargs):
        kwargs['record'] = Path(os.environ['GENELOOP_ARTIFACT_LEDGER'])
        return original_state(*args, **kwargs)
    web.State = state

if __name__ == '__main__':
    web.main()
