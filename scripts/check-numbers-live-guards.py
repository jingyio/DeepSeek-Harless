#!/usr/bin/env python3
"""Exercise real Numbers state changes on a disposable experiment-owned copy."""
from __future__ import annotations
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '.local/benchmarks/numbers-live-v1'
spec = importlib.util.spec_from_file_location('digits',ROOT/'.local/numbers-digits-upstream/server/digits_server.py')
digits = importlib.util.module_from_spec(spec); spec.loader.exec_module(digits)


async def main():
    work = BASE/'guards';work.mkdir(exist_ok=True)
    target = work/'boundary.numbers'
    if target.exists():
        raise ValueError('guard copy already exists; preserve its evidence')
    shutil.copy2(BASE/'workbooks/test_calendar_b.numbers',target)
    doc=digits.open_document({'path':str(target)})
    scope_path=work/'scope.json'
    def fresh_scope():
        scope={'path':str(target),'document':doc,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        scope_path.write_text(json.dumps(scope));return scope
    scope=fresh_scope()
    async def invoke(name,args):
        env={**os.environ,'SSS_NUMBERS_SCOPE':str(scope_path)}
        async with Client(StdioServerParameters(command=str(ROOT/'.venv312/bin/python'),
            args=['scripts/numbers-live-read-mcp.py'],cwd=ROOT,env=env),read_timeout_seconds=45) as client:
            return await client.call_tool(name,args)
    digits.set_cells({'document':doc,'updates':[{'cell':'B2','value':1.0}]})
    unsaved=await invoke('numbers_read_table',{'document':doc})
    assert unsaved.is_error and 'unsaved' in str(unsaved)
    digits.save_document({'document':doc})
    changed=await invoke('numbers_read_table',{'document':doc})
    assert changed.is_error and 'revision changed' in str(changed)
    scope=fresh_scope()
    recovered=await invoke('numbers_read_table',{'document':doc,'include_formulas':True})
    assert not recovered.is_error
    sheet=digits.list_sheets({'document':doc})[0]
    digits._run('tell application "Numbers"\n'
                f'tell sheet {digits._q(sheet)} of document {digits._q(doc)}\n'
                'make new table at end of tables with properties {name:"Review notes", row count:2, column count:2}\n'
                'end tell\nend tell')
    digits.save_document({'document':doc});scope=fresh_scope()
    inputs=[('numbers_open_document',{'path':str(target)}),
            ('numbers_list_sheets',{'document':doc}),
            ('numbers_list_tables',{'document':doc,'sheet':sheet})]
    history=[]
    for index,(name,args) in enumerate(inputs):
        reply=await invoke(name,args)
        assert not reply.is_error
        output=json.loads(reply.content[0].text)
        history.append({'name':'mcp__numbers_live__'+name,'callId':str(index),'ok':True,
                        'arguments':args,'output':output,'sourceVersion':scope['sha256'],
                        'inputVersion':scope['sha256']})
    assert history[-1]['output']['only_table'] is None
    (work/'multiple-table-history.json').write_text(json.dumps(history))
    js="""
import fs from 'node:fs';
import {proposeReadyBatch} from './src/motif_core/online_skill_runtime.mjs';
const root='.local/benchmarks/numbers-live-v1/';
const manifest=JSON.parse(fs.readFileSync(root+'online-manifest.json'));
const history=JSON.parse(fs.readFileSync(root+'guards/multiple-table-history.json'));
const availableTools=new Map(Object.entries(manifest.contracts).map(([name,c])=>[name,{name,parameters:{type:'object',required:[],properties:Object.fromEntries([...c.required_params,...Object.keys(c.default_params)].map(k=>[k,{}]))}}]));
const task={intent:'Read the selected Numbers spreadsheet table and its formulas to audit the expense totals.',input_version:history[0].inputVersion,bindings:{},source_versions:Object.fromEntries(Object.keys(manifest.contracts).map(k=>[k,history[0].sourceVersion]))};
const proposals=await proposeReadyBatch({manifest,task,history,availableTools,similarity:async(q,ds)=>ds.map(()=>1),minSimilarity:0.8,minMargin:0.1});
if(proposals.length)throw Error('ambiguous table incorrectly auto-selected');
console.log(JSON.stringify({multiple_tables_defer:true,candidate_count:proposals.length,semantic_score:1,kind:'offline_guard_replay_on_live_app_results'}));
"""
    guard=json.loads(subprocess.check_output(['node','--input-type=module','-e',js],cwd=ROOT,text=True))
    result={'unsaved_change_rejected':unsaved.is_error,'saved_revision_change_rejected':changed.is_error,
            'fresh_scope_read_succeeded':not recovered.is_error,**guard,'paid_requests':0}
    (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    asyncio.run(main())
