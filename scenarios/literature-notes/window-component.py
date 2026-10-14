"""Same actual model-selected windows in both arms; isolate read continuation from semantic drift."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import threading
from http.server import ThreadingHTTPServer
from uuid import uuid4
from pdf_tools import ROOT,digest,save_private
from pdf_window_tools import HERE,WindowScene,window_version
from pdf_dependencies import private_file

def module(path):
    spec=importlib.util.spec_from_file_location('window_component_study',path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
study=module(HERE/'window-study.py')


def prepare(parent):
    out=ROOT/'.local/literature-notes'/('window-component-20261013-'+uuid4().hex[:8]);out.mkdir(mode=0o700,parents=True)
    save_private(out/'protocol.json',{'experiment_id':out.name,'state':'preparing','purpose':'fixed-window mechanical component, not full agent quality',
        'budget_per_task_usd':.25,'max_steps':32,'planned_runs':6,'budget_total_cap_usd':1.50,'model':'deepseek-flash','reasoning_effort':'off'})
    origin=parent/'eval-orchestration-1-H';events,run,counts=study.replay(origin)
    spec=json.loads((origin/'input.json').read_text());queries={};selected={};result_ids={}
    for event in events:
        if event['type']=='tool/result':
            for block in event['data']['message']['content']:
                result_ids[block['toolCallId']]=not block.get('isError')
    for event in events:
        if event['type']!='tool/call' or not result_ids.get(event['data']['callId']):continue
        data=event['data'];args=json.loads(data['arguments'])
        if data['name']==study.PREFIX+'search_pdf_text':queries.setdefault(args['paper_id'],args)
        if data['name']==study.PREFIX+'pin_pdf_context':selected.setdefault(args['paper_id'],args)
    ids=[p['paper_id']for p in spec['task']['sources']['papers']]
    if set(selected)!=set(ids) or set(queries)!=set(ids):raise ValueError('real origin lacks complete explicit selected windows')
    plan={'searches':[queries[p]for p in ids],'windows':[selected[p]for p in ids]}
    spec['task']['question']='执行已有真实模型选定的逐篇窗口阅读计划，确认指定窗口已读取，报告物理页位置；不解释科学结论。'
    expected_scene=WindowScene(spec,out/'expected-only');expected_scene.read_workflow_input();expected={}
    for args in plan['searches']:expected_scene.search_pdf_text(**args)
    for args in plan['windows']:
        pin=expected_scene.pin_pdf_context(**args);expected[pin['source_id']]=expected_scene.read_pinned_pdf_context(pin['source_id'])
    save_private(out/'expected-sources.json',expected)
    prompt=(HERE/'pdf-window-task.md').read_text()+'\n本次为有冻结计划的证据读取组件：\n'+spec['task']['question']+'\n'
    prompt+='下面计划来自前一普通Harness任务的实际成功调用，只执行列出的searches和windows，不扩检索词或窗口，不作科学推断；返回实际已读句柄。\n'+json.dumps(plan,ensure_ascii=False)+'\n'
    (out/'prompt.md').write_text(prompt);(out/'prompt.md').chmod(0o600)
    config=json.loads((HERE/'pdf-window-scenario.json').read_text());config['prompt']=str(out/'prompt.md')
    schedule=[]
    for repeat in range(1,4):
        for arm in (['H','M']if repeat%2 else ['M','H']):
            name=str(repeat)+'-'+arm;work=out/name;work.mkdir(mode=0o700)
            save_private(work/'input.json',spec);save_private(work/'scenario.json',config)
            schedule.append({'name':name,'repeat':repeat,'arm':arm})
    manifest=private_file(parent/'learned/online-manifest.json')
    protocol=json.loads((out/'protocol.json').read_text());protocol.update(state='frozen',parent_experiment=parent.name,
        original_selection_run=str(run),selection_cost_usd=json.loads((origin/'outcome.json').read_text())['run']['budget_accounted_usd'],
        selection_cost_scope='already counted in full-task study, excluded equally from component timing',
        original_events_sha256=hashlib.sha256((run/'agent-events.jsonl').read_bytes()).hexdigest(),plan=plan,
        window_version=window_version(),manifest=str(manifest),manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        code_sha256=study.code_snapshot(),component_driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256=digest(spec),expected_sources_sha256=digest(expected),schedule=schedule,
        runtime=study.module('component_runtime',HERE/'run-pdf.py').runtime_snapshot(),scientific_support_verified=False)
    save_private(out/'protocol.json',protocol);save_private(ROOT/'.local/literature-notes/window-component-current.json',{'experiment':str(out)})
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path);p.add_argument('--experiment',type=Path);p.add_argument('--call-model',action='store_true');a=p.parse_args()
    out=private_file(a.experiment/'protocol.json').parent if a.experiment else prepare(private_file(a.parent/'protocol.json').parent)
    protocol=json.loads((out/'protocol.json').read_text());manifest=private_file(Path(protocol['manifest']))
    if (study.code_snapshot()!=protocol['code_sha256'] or window_version()!=protocol['window_version']
            or hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=protocol['component_driver_sha256']
            or hashlib.sha256(manifest.read_bytes()).hexdigest()!=protocol['manifest_sha256']):raise ValueError('component code/library changed')
    print(json.dumps({'experiment':str(out),'model_call_enabled':a.call_model,'component_only':True,'budget_total_cap_usd':1.50}),flush=True)
    if not a.call_model:return
    endpoint=ThreadingHTTPServer(('127.0.0.1',0),study.RejectEmbedding);endpoint.calls=[]
    threading.Thread(target=endpoint.serve_forever,daemon=True).start();rows=[]
    try:
        for item in protocol['schedule']:
            work=out/item['name'];spec=json.loads((work/'input.json').read_text())
            if digest(spec)!=protocol['input_sha256']:raise ValueError('component input changed')
            outcome=study.runner.run(work,protocol,scene_class=WindowScene,server_path=HERE/'pdf_window_tools.py',
                manifest=manifest if item['arm']=='M'else None,embedding_endpoint=f'http://127.0.0.1:{endpoint.server_port}/v1/embeddings')
            report=json.loads(Path(outcome['receipt']['artifact']).read_text())if outcome['receipt']else {'sources':{}}
            rows.append({**item,'run':outcome['run'],'source_packet_equal':digest(report['sources'])==protocol['expected_sources_sha256'],
                         'complete':outcome['run']['status']=='done'and bool(outcome['receipt']),'receipt':outcome['receipt']})
            summary={'experiment_id':out.name,'rows':rows,'embedding_requests':len(endpoint.calls),'fake_vectors_used':False,
                     'upstream_requests':sum(r['run']['upstream_requests']for r in rows),
                     'budget_accounted_usd':sum(r['run']['budget_accounted_usd']for r in rows),'scientific_support_verified':False,'arms':{}}
            for arm in ('H','M'):
                selected=[r for r in rows if r['arm']==arm];summary['arms'][arm]={'runs':len(selected),'packet_equal':sum(r['source_packet_equal']for r in selected),'complete':sum(r['complete']for r in selected)}
                for field in ('upstream_requests','outputTokens','budget_accounted_usd','elapsed_seconds','model_requests_skipped_verified'):
                    if selected:summary['arms'][arm][field]=statistics.mean(r['run'][field]for r in selected)
            save_private(out/'summary.json',summary)
            print(json.dumps({k:v for k,v in summary.items()if k!='rows'}),flush=True)
    finally:endpoint.shutdown();endpoint.server_close()


if __name__=='__main__':main()
