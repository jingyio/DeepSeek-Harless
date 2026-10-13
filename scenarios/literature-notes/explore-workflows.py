"""Prepare and run independent native Harness discovery tasks, preserving every failure."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4
from mcp import Client, StdioServerParameters
from pdf_tools import ROOT, digest, inventory, save_private
from pdf_dependencies import private_file
from workflow_probe_tools import HERE, WorkflowProbeScene, execution_version, KINDS

TOOLS = {
    'topic_search': ['search_pdf_text','pin_pdf_context','read_pinned_pdf_context'],
    'citation_audit': ['check_citation_target'],
    'resource_inventory': ['find_resource_links','check_resource_url'],
}
PREFIX = 'mcp__literature_workflow_probe__'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def citation_targets(evidence_path, selected, field):
    evidence_path = private_file(evidence_path)
    evidence = json.loads(evidence_path.read_text())
    parent = json.loads(private_file(evidence_path.parent/'source-snapshot.json').read_text())
    old = {r['paper_id']: r for r in parent['task']['sources']['papers']}
    papers = {r['paper_id'] for r in selected['papers']}
    statements = {(p['paper_id'],r['name']): r['statement'] for p in evidence['draft']['papers'] for r in p['fields']}
    targets = []
    for cite in evidence['citation_checks']:
        if cite['paper_id'] not in papers or cite['field'] != field: continue
        value = {k: cite[k] for k in ('paper_id','page','start','end','quote_start','quote_end')}
        value.update(expected_pdf_sha256=old[cite['paper_id']]['pdf_sha256'],
                     expected_window_version_sha256=cite['version_sha256'], quote_sha256=digest(cite['quote']),
                     field=field, statement=statements[(cite['paper_id'],field)])
        value['reference_id'] = 'reference-' + digest(value)[:32]
        targets.append(value)
    if not targets: raise ValueError('no actual prior citations for selected field')
    return targets, {'parent_evidence_sha256': digest(evidence), 'parent_snapshot_sha256': digest(parent),
                     'scope': 'actual prior model draft; not a scientific gold answer'}


def prepare(papers_dir, evidence_path, budget):
    experiment_id = 'workflow-discovery-20261012-' + uuid4().hex[:8]
    out = ROOT/'.local/literature-notes'/experiment_id
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    # Reserve ID/protocol before collecting any experiment data or calling a model.
    save_private(out/'protocol.json', {'experiment_id': experiment_id, 'state': 'preparing',
        'purpose': 'broad workflow discovery, not Motif effectiveness comparison', 'baseline': 'ordinary native Harness',
        'model': 'deepseek-flash', 'reasoning_effort': 'off', 'budget_per_task_usd': budget,
        'task_count': 6, 'budget_total_cap_usd': 6*budget, 'learned_motif_enabled': False,
        'human_approval_required': False, 'corpus_scope': 'three known developer PDFs'})
    source = inventory(papers_dir)
    subsets = {}
    for name, count in [('three',3),('two',2)]:
        directory = out/('papers-'+name); directory.mkdir(mode=0o700)
        for row in source['papers'][:count]:
            shutil.copyfile(Path(source['root'])/row['filename'], directory/row['filename'])
            (directory/row['filename']).chmod(0o600)
        subsets[name] = inventory(directory)
    if len(source['papers']) != 3: raise ValueError('this discovery protocol requires the current three development PDFs')
    cases = [
        ('topic-methods','topic_search','three','这些论文有哪些确定性执行、工具编排或验证机制？检索相关原文，指出模型与程序各自做什么。',None),
        ('topic-evaluation','topic_search','two','这些论文如何比较性能与效率？查找基准、成本、时间或可靠性的实验依据，并保留证据覆盖限制。',None),
        ('citations-methods','citation_audit','three','检查已有方法笔记的每个引用在当前PDF里是否仍可定位，交付定位状态；不判断语义支持。','method'),
        ('citations-evaluation','citation_audit','three','检查已有实验设计笔记的每个引用在当前PDF里是否仍可定位，交付定位状态；不判断语义支持。','evaluation'),
        ('resources-project','resource_inventory','three','整理每篇论文自身的代码、模型、项目或演示资源链接；核查允许的链接是否可达，保留不可确认项。',None),
        ('resources-data','resource_inventory','two','整理每篇论文涉及的数据、可运行教程或项目资源，区分论文自身资源、复用的外部资源和普通文献引用。',None),
    ]
    specifications = []
    for name,kind,subset,question,field in cases:
        work = out/name; work.mkdir(mode=0o700)
        spec = {'schema_version': 1, 'kind': kind, 'task': {'schema_version':1,'question':question,'sources':subsets[subset]},
                'network_check_enabled': kind=='resource_inventory', 'citations': []}
        if field: spec['citations'],spec['citation_parent'] = citation_targets(evidence_path,subsets[subset],field)
        save_private(work/'input.json',spec)
        config = json.loads((HERE/'workflow-probe-scenario.json').read_text())
        config['prompt'] = str(HERE/'workflow-probe-task.md')
        config['allowed_tools'] = [PREFIX+n for n in ['read_workflow_input',*TOOLS[kind],'submit_workflow_report']]
        save_private(work/'scenario.json',config)
        specifications.append({'name':name,'kind':kind,'input_sha256':digest(spec),'config_sha256':digest(config),
                               'target_count':len(spec['citations']) if field else len(subsets[subset]['papers'])})
    runtime = module('workflow_runtime_snapshot', HERE/'run-pdf.py').runtime_snapshot()
    protocol = json.loads((out/'protocol.json').read_text())
    protocol.update(state='frozen', tasks=specifications, runtime=runtime, execution_version_sha256=execution_version(),
                    original_sources=source, prompt_sha256=hashlib.sha256((HERE/'workflow-probe-task.md').read_bytes()).hexdigest())
    save_private(out/'protocol.json',protocol)
    save_private(ROOT/'.local/literature-notes/workflow-discovery-current.json',{'experiment':str(out)})
    return out


async def schemas(work, server_path=HERE/'workflow_probe_tools.py'):
    env = {**os.environ,'SSS_WORKFLOW_PROBE_FILE':str(work/'input.json'),'SSS_WORKFLOW_PROBE_OUTPUT':str(work/'delivery')}
    env.pop('DEEPSEEK_API_KEY',None)
    async with Client(StdioServerParameters(command=sys.executable,args=[str(server_path)],cwd=ROOT,env=env)) as client:
        tools = await client.list_tools()
        save_private(work/'tool-schemas.json', [t.model_dump(mode='json') for t in tools.tools])
        result = await client.call_tool('read_workflow_input',{})
        if result.is_error: raise ValueError('actual MCP input failed')
        save_private(work/'mcp-input.json',json.loads(result.content[0].text))


def run(work, protocol, *, scene_class=WorkflowProbeScene, server_path=HERE/'workflow_probe_tools.py',
        manifest=None, embedding_endpoint=None):
    if (work/'outcome.json').exists() or (work/'stdout.txt').exists():
        raise ValueError('retain prior attempt; prepare a new experiment to retry')
    spec = json.loads((work/'input.json').read_text())
    scene = scene_class(spec,work/'delivery')
    asyncio.run(schemas(work,server_path))
    env={**os.environ,'SSS_WORKFLOW_PROBE_FILE':str(work/'input.json'),'SSS_WORKFLOW_PROBE_OUTPUT':str(work/'delivery')}
    loader=module('workflow_key_loader',HERE/'run-live.py')
    env['DEEPSEEK_API_KEY']=loader.load_key(loader.KEY_FILE,env)
    command = [sys.executable,str(ROOT/'scripts/run-scenario.py'),'--scenario',str(work/'scenario.json'),
               '--budget-usd',str(protocol['budget_per_task_usd']),'--max-steps',str(protocol.get('max_steps',16)),
               '--max-output','4000','--call-model']
    if manifest:
        versions=[scene.document_version(p['paper_id']) for p in spec['task']['sources']['papers']]
        task={'schema_version':1,'task_id':work.name,'session_id':'window-'+uuid4().hex,
              'intent':spec['task']['question'],'input_version':digest(spec),'bindings':{},
              'source_versions':{PREFIX+'pin_pdf_context':versions,PREFIX+'read_pinned_pdf_context':versions}}
        save_private(work/'motif-task.json',task)
        command += ['--mode','execute','--manifest',str(manifest),'--task',str(work/'motif-task.json'),
                    '--embedding-endpoint',embedding_endpoint,'--embedding-model','closed-source-no-embeddings']
    print(json.dumps({'case':work.name,'kind':spec['kind'],'model_call_enabled':True,
                      'budget_cap_usd':protocol['budget_per_task_usd'],'motif_enabled':bool(manifest)}),flush=True)
    result = subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
    for name,value in [('stdout.txt',result.stdout),('stderr.txt',result.stderr)]:
        (work/name).write_text(value); (work/name).chmod(0o600)
    summaries=[]
    for line in result.stdout.splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict) and 'output_dir' in row: summaries.append(row)
        except ValueError: pass
    summary = summaries[-1] if summaries else None
    receipt = None; decisions=[]; calls={}; pending={}
    if summary:
        run_dir = private_file(Path(summary['output_dir'])/'metrics.json').parent
        events = [json.loads(line) for line in (run_dir/'agent-events.jsonl').read_text().splitlines()]
        for event in events:
            if event['type']=='assistant/message' and event['data'].get('message',{}).get('source',{}).get('kind')=='model':
                message=event['data']['message']; blocks=message.get('content',[])
                tool_blocks=[b for b in blocks if b.get('type')=='tool-call']
                decisions.append({'origin_seq':event['seq'],'tool_names':[b['name'] for b in tool_blocks],
                    'arguments':[b.get('arguments') for b in tool_blocks], 'usage':event['data'].get('usage'),
                    'tool_argument_chars':sum(len(b.get('arguments','')) for b in tool_blocks),
                    'visible_text_chars':sum(len(b.get('text','')) for b in blocks if b.get('type')=='text'),
                    'has_visible_semantic_text':any(b.get('type')=='text' and b.get('text','').strip() for b in blocks),
                    'candidate_only':True,'approved_for_bypass':False})
            if event['type']=='tool/call':
                data=event['data']; calls[data['callId']]=data['name']; pending[data['callId']]=data
            if event['type']=='tool/result':
                for block in event['data']['message']['content']:
                    if calls.get(block.get('toolCallId'))==PREFIX+'submit_workflow_report' and not block.get('isError'):
                        receipt=json.loads(block['content'][0]['text'])
        if receipt:
            artifact=private_file(receipt['artifact']); body=json.loads(artifact.read_text())
            if artifact != scene.output/'report.json' or digest(body)!=receipt['artifact_sha256'] or body['input_sha256']!=digest(spec):
                raise ValueError('published probe report changed')
            # Replay actual original calls/results against current source. Network results are observations at run time.
            scene.read_workflow_input()
            successful={b['toolCallId'] for e in events if e['type']=='tool/result'
                        for b in e['data']['message']['content'] if b.get('type')=='tool-result' and not b.get('isError')}
            for event in events:
                if event['type'] != 'tool/call': continue
                data=event['data']
                if data['callId'] not in successful: continue
                name=data['name'].removeprefix(PREFIX)
                args=data.get('arguments',{})
                if isinstance(args,str): args=json.loads(args)
                if name in ('search_pdf_text','pin_pdf_context','read_pinned_pdf_context','check_citation_target','find_resource_links'):
                    getattr(scene,name)(**args)
            if spec['kind']=='resource_inventory':
                for check in body['url_checks']:
                    if check['resource_id'] not in scene.resources or check['url']!=scene.resources[check['resource_id']]['url']:
                        raise ValueError('URL check refers to a different current resource')
                    scene.url_checks[check['resource_id']]=check
            replay=scene.publish(body['rows'],persist=False)
            if replay['artifact_sha256'] != receipt['artifact_sha256']: raise ValueError('probe source replay differs')
        save_private(work/'decision-analysis.json',{'original_events_sha256':hashlib.sha256((run_dir/'agent-events.jsonl').read_bytes()).hexdigest(),
            'decisions':decisions,'calls':list(pending.values()), 'learned_motif':False})
    outcome={'case':work.name,'kind':spec['kind'],'run':summary,'receipt':receipt,'returncode':result.returncode,
             'status':('incomplete_workflow' if summary and summary.get('status')!='done' else receipt['status']) if receipt else 'missing_report',
             'source_replay_verified':bool(receipt),
             'scientific_support_verified':False,'learned_motif':bool(manifest)}
    save_private(work/'outcome.json',outcome)
    print(json.dumps(outcome,ensure_ascii=False),flush=True)
    return outcome


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--papers-dir',type=Path,default=ROOT/'testpdf')
    p.add_argument('--evidence',type=Path)
    p.add_argument('--experiment',type=Path)
    p.add_argument('--case')
    p.add_argument('--budget-usd',type=float,default=.25)
    p.add_argument('--call-model',action='store_true')
    a=p.parse_args()
    if not 0<a.budget_usd<=5: p.error('per-task cap must be in (0,5]')
    if not a.experiment and not a.evidence: p.error('prepare requires actual private --evidence from an earlier model task')
    out=private_file(a.experiment/'protocol.json').parent if a.experiment else prepare(a.papers_dir,a.evidence,a.budget_usd)
    protocol=json.loads((out/'protocol.json').read_text())
    if protocol['execution_version_sha256']!=execution_version(): raise ValueError('prepare again after probe code changes')
    selected=[c for c in protocol['tasks'] if not a.case or c['name']==a.case]
    if not selected: p.error('unknown case')
    print(json.dumps({'experiment':str(out),'cases':selected,'model_call_enabled':a.call_model,
                      'budget_total_cap_usd':sum(protocol['budget_per_task_usd'] for _ in selected),
                      'shared_core_changes':False,'learned_motif_enabled':False},ensure_ascii=False),flush=True)
    if not a.call_model: return
    outcomes=[]
    for case in selected:
        if digest(json.loads((out/case['name']/'input.json').read_text()))!=case['input_sha256']:
            raise ValueError('frozen input changed')
        outcomes.append(run(out/case['name'],protocol))
        save_private(out/'progress.json',outcomes)
    all_outcomes=[json.loads(p.read_text()) for p in out.glob('*/outcome.json')]
    save_private(out/'summary.json',{'outcomes':all_outcomes,
        'upstream_requests':sum((o['run'] or {}).get('upstream_requests',0) for o in all_outcomes),
        'budget_accounted_usd':sum((o['run'] or {}).get('budget_accounted_usd',0) for o in all_outcomes),
        'receipt_count':sum(bool(o['receipt']) for o in all_outcomes), 'efficiency_comparison_performed':False})


if __name__=='__main__': main()
