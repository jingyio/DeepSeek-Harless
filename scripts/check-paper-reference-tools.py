"""Free real-stdio MCP diagnostic against captured paper inputs, without an LLM."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters


def save(path, value):
    with path.open('x', encoding='utf-8') as file:
        json.dump(value, file, ensure_ascii=False, indent=2); file.write('\n')
    path.chmod(0o600)


async def check(run, output):
    work = run/'work'; catalog = json.loads((work/'catalog.json').read_text())
    keys = list(dict.fromkeys(r['key'] for r in catalog['cited_records']))
    expected = [{'key':r['key'], 'raw_bibtex':(work/r['record_path']).read_text().strip()}
                for r in catalog['cited_records']]
    if not 1 <= len(keys) <= 64: raise ValueError('diagnostic requires 1..64 cited keys')
    config = output/'inputs.json'
    save(config, {'sample':{'root':str(work), 'source_dir':'source','main':'main.tex'}})
    inventories = {}; observed = None
    for enabled in [False, True]:
        params = StdioServerParameters(command=sys.executable,
            args=[str(ROOT/'scenarios/paper-submission/server.py')], cwd=ROOT,
            env={'SSS_PAPER_INPUTS':str(config), 'SSS_PAPER_REFERENCE_RECORDS':'1' if enabled else '0'})
        async with Client(params, read_timeout_seconds=60) as client:
            listed = await client.list_tools()
            inventories[str(enabled)] = listed.model_dump(mode='json', by_alias=True)
            offered = {t.name for t in listed.tools}
            assert len(offered) == (7 if enabled else 6)
            assert ('read_pinned_paper_references' in offered) == enabled
            if not enabled: continue
            pinned = await client.call_tool('pin_paper_sources', {'case_id':'sample'})
            assert not pinned.is_error
            pin = json.loads(pinned.content[0].text)
            read = await client.call_tool('read_pinned_paper_references', {'source_id':pin['source_id'],'keys':keys})
            assert not read.is_error
            observed = json.loads(read.content[0].text)
            assert observed['version_sha256'] == pin['version_sha256']
            assert [{'key':r['key'],'raw_bibtex':r['raw_bibtex']} for r in observed['records']] == expected
            assert not observed['missing_keys']
            denied = await client.call_tool('read_pinned_paper_references', {'source_id':'invented','keys':keys})
            assert denied.is_error
    unchanged = all(hashlib.sha256((work/s['path']).read_bytes()).hexdigest()==s['sha256'] for s in catalog['sources'])
    assert unchanged
    save(output/'tool-inventories.json', inventories); save(output/'reference-records.json', observed)
    result = {'kind':'real_stdio_mcp_replay_diagnostic', 'matched_original_records':len(expected),
              'legacy_tools':6, 'opt_in_tools':7, 'source_hashes_unchanged':unchanged,
              'invented_handle_rejected':True, 'real_model_requests':0, 'api_cost_usd':0,
              'agent_behavior_and_savings':'not_evaluated',
              'input_run_id':run.name,
              'input_manifest_sha256':hashlib.sha256((run/'manifest.json').read_bytes()).hexdigest(),
              'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    [Path(__file__),ROOT/'scenarios/paper-submission/server.py',ROOT/'scenarios/paper-submission/checks.py',ROOT/'src/adapters/paper_bibliography.py']}}
    save(output/'verification.json', result)
    print(json.dumps(result, ensure_ascii=False))


def main():
    p=argparse.ArgumentParser(); p.add_argument('--input-run',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path); args=p.parse_args()
    run=args.input_run.resolve(); output=args.output.resolve(); private=(ROOT/'.local').resolve()
    if not run.is_relative_to(private) or not output.is_relative_to(private): p.error('private input/output required')
    if output.exists(): p.error('preserve old diagnostics; choose a new output directory')
    output.mkdir(parents=True, mode=0o700)
    asyncio.run(check(run, output))


if __name__=='__main__': main()
