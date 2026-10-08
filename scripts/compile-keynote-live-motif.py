#!/usr/bin/env python3
"""Mine and certify Keynote slide audit from independent ordinary Agent traces.

Names are native application addresses, not opaque handles. Provenance is
checked only against the host's document / singleton sheet / singleton table
receipts, in the same frozen workbook revision. Arbitrary cell text is excluded.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_trajectory import extract_dsh_trace, _observation_digest
from src.adapters.dsh_event_projection import is_original_tool_result
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.library_builder import build_read_motif_library

BASE = ROOT / '.local/benchmarks/keynote-live-v1'
PREFIX = 'mcp__keynote_live__'
NAMES = [PREFIX + x for x in ['keynote_open_document', 'keynote_list_slides', 'keynote_read_slide']]


def sha(value):
    return hashlib.sha256(value).hexdigest()


def save(name, value):
    path = BASE / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def main():
    rows = {
        NAMES[0]: {'required_params':['path'], 'output_fields':['document','source_version'],
                   'description':'Open a Keynote deck and return the exact document name.'},
        NAMES[1]: {'required_params':['document','title'], 'output_fields':['document','selected_slide','source_version'],
                   'description':'Find a slide by its exact title in the selected Keynote deck.'},
        NAMES[2]: {'required_params':['document','slide_number'], 'output_fields':['source_version'],
                   'description':'Read the selected slide visible claim and presenter notes from Keynote.'},
    }
    for value in rows.values():
        value.update(read_only=True, replay_stable=True)
    contracts = parse_tool_contracts(rows)
    traces, evidence = [], {}
    for case in ['train_a','train_position','validate']:
        attempt = 'baseline-position' if case == 'train_position' else 'baseline-receipt'
        event_file = BASE / case / attempt / 'agent-events.jsonl'
        events = [json.loads(x) for x in event_file.read_text().splitlines()]
        scope = json.loads((BASE / case / 'scope.json').read_text())
        producers, calls, provenance = {}, {}, {}
        for event in events:
            data = event.get('data',{})
            if event.get('type') == 'tool/call':
                name, call_id = data['name'], data['callId']
                calls[call_id] = name
                args = json.loads(data['arguments'])
                for param in ['document','slide_number']:
                    value = args.get(param)
                    if value in producers:
                        source_id, source_field = producers[value]
                        provenance.setdefault(call_id,{})[param] = {
                            'from_call_id':source_id,'from_field':source_field}
            elif is_original_tool_result(event):
                call_id = data['message']['source']['callId']
                name = calls[call_id]
                ok, _, output = _observation_digest(event, name)
                if not ok or output is None or output['source_version'] != scope['sha256']:
                    raise ValueError('training result lacks a stable Keynote receipt')
                for field in ['document','selected_slide']:
                    value = output.get(field)
                    if value:
                        if value in producers and field != 'document':
                            raise ValueError('ambiguous native target provenance')
                        producers[value] = (call_id,field)
        fingerprint = sha((case + scope['sha256']).encode())
        trace = extract_dsh_trace(events,contracts,trace_id=case,
                      task_fingerprint=fingerprint,provenance_by_call_id=provenance)
        if not all(x.eligible for x in trace.records):
            raise ValueError('ordinary trace has an uncertifiable call')
        traces.append(trace)
        evidence[case] = {'research_decision_id':fingerprint,
                         'manifest_sha256':sha(json.dumps(scope,sort_keys=True).encode()),
                         'events_sha256':sha(event_file.read_bytes()),
                         'identity_sha256':sha((case+':native-slide-audit').encode()),
                         'question_sha256':sha((BASE/case/'prompt.txt').read_bytes())}
        save(case+'/name-provenance.json',provenance)
    library = build_read_motif_library(traces[:2],traces[2:],contracts,
                                      task_identity_evidence=evidence)
    if not library['artifacts']:
        raise ValueError('No mined pattern passed independent certification')
    spec = importlib.util.spec_from_file_location('export',ROOT/'scripts/export-online-motif-manifest.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    manifest = module.export_manifest(library,rows,{}, {name:'source_version' for name in NAMES})
    save('contracts.json',rows); save('certified-library.json',library); save('online-manifest.json',manifest)
    print(json.dumps({'artifacts':len(library['artifacts']),
                      'patterns':[x['tools'] for x in library['artifacts']],
                      'manifest_digest':manifest['manifest_digest']},ensure_ascii=False))


if __name__ == '__main__':
    main()
