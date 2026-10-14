"""Free actual MCP and original SDK checks; local mock is never learning evidence."""
import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
from uuid import uuid4
from mcp import Client,StdioServerParameters
from pdf_tools import ROOT,digest,save_private
from pdf_catalog_tools import CatalogScene,HERE
from catalog_entry import entry_task,private_policy
sys.path.insert(0,str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State,create_server
from src.adapters.native_budget import NativeBudgetGuard
from src.motif_core.offline.entry_compiler import navigation_projection


async def mcp_smoke(out,task,previous):
    env={**os.environ,'SSS_PDF_TASK_FILE':str(out/'task.json'),'SSS_PDF_CATALOG_OUTPUT':str(out/'mcp-delivery'),
         'SSS_PDF_CATALOG_PREVIOUS':str(previous) if previous else ''};env.pop('DEEPSEEK_API_KEY',None)
    async with Client(StdioServerParameters(command=sys.executable,args=[str(HERE/'pdf_catalog_tools.py')],cwd=ROOT,env=env)) as client:
        schemas=await client.list_tools();plan_result=await client.call_tool('read_catalog_plan',{})
        assert not plan_result.is_error
        plan=json.loads(plan_result.content[0].text)
        entries=[];packets=[];call_count=1;negative_checks=[]
        for row in plan['work']:
            packet=await client.call_tool('read_catalog_packet',{'paper_id':row['paper_id']});assert not packet.is_error
            value=json.loads(packet.content[0].text)
            packets.append(value);call_count+=1
            entries.append({'paper_id':row['paper_id'],'authors':[], 'year':{'candidate_id':None},
                'author_coverage':{'status':'partial' if value['author_regions'] else 'unavailable',
                    'region_ids':[r['region_id'] for r in value['author_regions']],
                    'reason':'explicit free null fixture; no semantic metadata extraction'},
                **{k:{'value':None,'anchor':''} for k in ('title','doi','arxiv')}})
        for i,value in enumerate(packets):
            if value['author_regions'] and 'visible_author_omission' not in negative_checks:
                invalid=copy.deepcopy(entries)
                invalid[i]['author_coverage']['status']='covered'
                failed=await client.call_tool('submit_catalog',{'entries':invalid});call_count+=1
                assert failed.is_error and 'uncovered_name_tokens' in failed.content[0].text
                negative_checks.append('visible_author_omission')
            unsupported=next((c for c in value['date_candidates'] if not c['eligible_bibliography_year']),None)
            if unsupported and 'administrative_year' not in negative_checks:
                invalid=copy.deepcopy(entries);invalid[i]['year']['candidate_id']=unsupported['candidate_id']
                failed=await client.call_tool('submit_catalog',{'entries':invalid});call_count+=1
                assert failed.is_error and 'never received/accepted/copyright' in failed.content[0].text
                negative_checks.append('administrative_year')
        result=await client.call_tool('submit_catalog',{'entries':entries});assert not result.is_error
        call_count+=1
        receipt=json.loads(result.content[0].text)
        assert receipt['entry_count']==len(task['sources']['papers']) and receipt['processed_count']==len(plan['work'])
        return {'tool_count':len(schemas.tools),'actual_mcp_calls':call_count,'negative_guards_verified':negative_checks,
                'scope':'explicit partial/null fixture, not semantic extraction or learning','receipt_status':receipt['status']}


def check(task_path,previous=None,policy=None,stale_plan=False):
    out=ROOT/'.local/catalog-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
    task=json.loads(task_path.read_text());save_private(out/'task.json',task)
    scene=CatalogScene(task['sources']['root'],task,out/'delivery',previous=previous)
    report={'output':str(out),'real_api_requests':0,'mcp':asyncio.run(mcp_smoke(out,task,previous))}
    if not policy:save_private(out/'outcome.json',report);print(json.dumps(report));return
    private_policy(policy)
    prompt='Read the current catalog work metadata packets and stop; free protocol diagnostic.'
    frozen={**entry_task(scene,out.name),'session_id':'catalog-check-'+uuid4().hex,
            'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
    if stale_plan:frozen['source_result_sha256']='a'*64
    save_private(out/'entry-task.json',frozen);(out/'prompt.md').write_text(prompt)
    config=json.loads((HERE/'pdf-catalog-scenario.json').read_text());config.pop('completion_guard');config['prompt']=str(out/'prompt.md')
    save_private(out/'scenario.json',config);prepared=prepare_scenario(out/'scenario.json',entry_motif=True)
    spec=importlib.util.spec_from_file_location('catalog_mock',ROOT/'scripts/motif-example.py')
    mock=importlib.util.module_from_spec(spec);spec.loader.exec_module(mock)
    mock.next_fixture_action=lambda _values,_case:(None,{'scope':'free-protocol-only'})
    handler=mock.provider_handler('catalog-probe',with_usage=True,request_limit=8)
    provider=ThreadingHTTPServer(('127.0.0.1',0),handler);state=State(cap_usd=.25,output_cap=2000,record=out/'ledger.jsonl',request_limit=8)
    gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{provider.server_port}',state)
    for server in (provider,gate):threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with create_harness(root=ROOT,patches=(prepared['patch'],),env={
            'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1',
            'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_SCENARIO_PRESENTATION':'native',
            'SSS_PDF_TASK_FILE':str(out/'task.json'),'SSS_PDF_CATALOG_OUTPUT':str(out/'delivery'),
            'SSS_PDF_CATALOG_PREVIOUS':str(previous) if previous else '',
            'SSS_ENTRY_MOTIF_POLICY':str(policy),'SSS_ENTRY_MOTIF_TASK':str(out/'entry-task.json'),
            'SSS_TERMINAL_MOTIF_POLICY':'','SSS_TERMINAL_MOTIF_TASK':'',
            'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':'','SSS_BUDGET_GATE_ACTIVE':'1',
            'SSS_BUDGET_CAP_USD':'.25','SSS_BUDGET_LEDGER':str(state.record)},cwd=str(out),runtime_cwd=str(out),
            provider='deepseek-official',model='deepseek-flash',max_tokens=2000,request_timeout_seconds=120) as client:
            result=client.run(prompt,session_id=frozen['session_id'],on_notification=NativeBudgetGuard(max_model_requests=8,max_observed_input_tokens=None).on_notification)
        save_private(out/'events.json',result.events);outputs=[]
        for event in result.events:
            if event['type']=='tool/result':
                for block in event['data']['message']['content']:
                    assert not block.get('isError');outputs.append(json.loads(block['content'][0]['text']))
        assert outputs[0]==scene.read_catalog_plan()
        assert len(handler.calls)==1
        audit=out/'.local/online-motif'/(hashlib.sha256(frozen['session_id'].encode()).hexdigest()+'.jsonl')
        rows=[json.loads(l) for l in audit.read_text().splitlines()]
        skips=sum(r['kind']=='entry_model_request_bypassed_verified' for r in rows)
        if stale_plan:
            assert len(outputs)==1 and skips==0 and any(r['kind']=='entry_motif_deferred' for r in rows)
        else:
            assert len(outputs)==1+len(frozen['target_ids']) and skips==2
            for packet in outputs[1:]:assert navigation_projection(packet)==navigation_projection(scene.read_catalog_packet(packet['paper_id']))
        report.update(mock_provider_requests=len(handler.calls),actual_sdk_tool_calls=len(outputs),
                      verified_runtime_batches=skips,stale_plan_fallback=stale_plan,packet_replay_equal=not stale_plan)
        save_private(out/'outcome.json',report);print(json.dumps(report))
    finally:
        for server in (provider,gate):server.shutdown();server.server_close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',type=Path,required=True);p.add_argument('--previous',type=Path)
    p.add_argument('--policy',type=Path);p.add_argument('--stale-plan',action='store_true');a=p.parse_args()
    check(a.task.resolve(),a.previous.resolve() if a.previous else None,a.policy.resolve() if a.policy else None,a.stale_plan)
