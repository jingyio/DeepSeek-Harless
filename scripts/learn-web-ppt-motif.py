#!/usr/bin/env python3
"""Compile reviewed ordinary Web traces using the existing independent edge miner.

No model calls and no hand-authored graph. Raw traces stay private; publishing
exports only certificates, schemas and anonymous evidence. It never promotes a
quality/cost claim or overwrites an existing release.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scenarios.research_ppt.motif_v6 import learn,validate_compilation
from src.adapters.task_identity import load_trace_identity,require_distinct_decisions

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def private(p):
    path=Path(p).resolve(strict=True)
    if not path.is_relative_to((ROOT/'.local').resolve()) or Path(p).is_symlink():raise ValueError('private evidence must remain in this project')
    return path
def write(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
def export_run(row,ledger,out):
    task=private(row['task_dir']);effective=read(task/'effective-config.json');state=read(task/'task-state.json');request=read(task/'task.json')
    if state.get('status')!='completed' or request.get('mode')!='baseline' or effective.get('ppt_execution_strategy')!='host_delivery':
        raise ValueError('training requires a completed ordinary host-script Web run')
    tools=effective.get('tools',[])
    if len(tools)!=21 or len({x['name'] for x in tools})!=21 or any(not x['name'].startswith('mcp__ppt__') for x in tools):
        raise ValueError('actual complete 21-tool schema required')
    review_path=private(row['review']);review=read(review_path)
    if review.get('reviewer_kind') not in ('human','ai-assisted') or any(review.get(k) is not True for k in
            ('mechanical','scientific_review_complete','visual_review_complete','readonly_provenance')) or any(type(review.get(k)) is not bool for k in ('scientific','visual')):
        raise ValueError('complete artifact review and valid read provenance required')
    if review.get('task_id')!=request['task_id'] or not review.get('files'):raise ValueError('review must identify this actual task and files')
    for f in review['files']:
        if sha(private(f['path']))!=f['sha256']:raise ValueError('reviewed file changed')
    rows=[x for x in ledger if x.get('task_id')==request['task_id'] and 'response_status' in x]
    stats=state['stats']
    if not rows or len(rows)!=stats.get('upstream_requests') or not stats.get('usage_complete'):
        raise ValueError('full real paid ledger required')
    for field in ('prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens','total_tokens'):
        if any(x.get('response_status')!=200 or not isinstance(x.get('response_usage',{}).get(field),int) for x in rows):raise ValueError('missing provider usage')
        if sum(x['response_usage'][field] for x in rows)!=stats[field]:raise ValueError('task/ledger totals differ')
    question='\n'.join(p['text'] for p in request['content'] if p['type']=='text')
    if not question.strip() or not effective.get('design_skill_sha256'):raise ValueError('full Skill and actual task question required')
    out.mkdir()
    shutil.copyfile(task/'events.jsonl',out/'agent-events.jsonl')
    manifest={'task_id':request['task_id'],'question':question,'source_effective_sha256':sha(task/'effective-config.json'),
              'original_events_sha256':sha(task/'events.jsonl'),'review_sha256':sha(review_path),
              'provider_mode':effective.get('provider_mode'),'model':state.get('model'),'stats':stats,
              'skill_sha256':effective['design_skill_sha256'],'tools_sha256':effective.get('tool_schemas_sha256')}
    write(out/'manifest.json',manifest)
    write(out/'task-identity.json',{'schema_version':1,'research_decision_id':row['decision_id'],
          'manifest_sha256':sha(out/'manifest.json'),'events_sha256':sha(out/'agent-events.jsonl')})
    identity=load_trace_identity(out/'task-identity.json',out/'agent-events.jsonl',ROOT/'.local')
    evidence={**identity,'reviewer_kind':review['reviewer_kind'],'review_sha256':sha(review_path),
              'scientific_passed':review['scientific'],'visual_passed':review['visual'],'readonly_provenance_passed':True,
              'effective_config_sha256':sha(task/'effective-config.json'),'skill_sha256':effective['design_skill_sha256'],
              'whole_schema_sha256':effective.get('tool_schemas_sha256'),'requests':len(rows),
              'tokens':{k:stats[k] for k in ('prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens','total_tokens')},
              'proxy_peak_usd':stats['estimated_cost_usd'],'actual_paid_usd':None}
    return tools,evidence

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--publish',type=Path,help='New repository motif-libraries directory; never overwrites')
    a=p.parse_args();dataset=read(private(a.dataset));ledger_path=Path(dataset['ledger']).resolve(strict=True)
    ledger=[json.loads(x) for x in ledger_path.read_text().split('\n') if x.strip()]
    if len(dataset['train'])!=2 or len(dataset['heldout'])!=1:raise ValueError('freeze two independent train decisions and one heldout')
    out=a.out.resolve()
    if not out.is_relative_to((ROOT/'.local').resolve()):raise ValueError('private compilation output required')
    out.mkdir(parents=True,exist_ok=False);start=time.monotonic();schemas=None;evidence={};runs={};identities=[]
    for split in ('train','heldout'):
        runs[split]=[];evidence[split]=[]
        for i,row in enumerate(dataset[split]):
            dest=out/(split+'-'+str(i+1));tools,e=export_run(row,ledger,dest)
            if schemas is not None and tools!=schemas:
                capture=read(private(dataset['schema_variants']))
                if tools not in capture.get('variants',[]) or schemas not in capture.get('variants',[]):
                    raise ValueError('effective whole schema not independently captured')
                for name in read(ROOT/'scenarios/research_ppt/web-read-contracts.json'):
                    if next(t for t in tools if t['name']==name)!=next(t for t in schemas if t['name']==name):
                        raise ValueError('candidate read schema changed across decisions')
            if schemas is None:schemas=tools
            runs[split].append(str(dest));evidence[split].append(e);identities.append(e)
    require_distinct_decisions(identities)
    if len({x['skill_sha256'] for x in identities})!=1:raise ValueError('Skill changed across decisions')
    write(out/'dataset.json',runs)
    write(out/'schema.json',{'tools':[{'name':t['name'],'description':t['description'],'inputSchema':t['parameters']} for t in schemas]})
    # The ordinary traces determine every candidate, parameter edge and rejection.
    guards=[ROOT/'src/adapters'/n for n in ('harless_task_scope.ts','harless_ppt_recovery.ts','dsh_web_tasks.ts','harless_scenarios.py','harless_rsi_binding.ts','harless_rsi_bundle.py')]
    manifest=learn(out/'dataset.json',contracts_path=ROOT/'scenarios/research_ppt/web-read-contracts.json',
        version_fields_path=ROOT/'scenarios/research_ppt/web-read-version-fields.json',tool_schema_path=out/'schema.json',
        out_dir=out/'compiled',guard_paths=tuple(guards),mining='witnessed_edges')
    learned=validate_compilation(manifest);data=read(manifest)
    if not data['artifacts']:raise ValueError('normal traces did not support a certified candidate')
    report={'schema_version':1,'new_training':True,'method':'existing_witnessed_edge_compiler','training_tasks':2,'heldout_tasks':1,
            'artifacts':len(data['artifacts']),'library_digest':read(manifest.parent/'library.json')['library_digest'],
            'manifest_digest':data['manifest_digest'],'evidence_sha256':hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest(),
            'compilation_model_requests':0,'compilation_seconds':time.monotonic()-start,
            'trace_collection_requests':sum(x['requests'] for x in identities),'trace_collection_proxy_usd':sum(x['proxy_peak_usd'] for x in identities),
            'scientific_review_kind':'ai-assisted' if any(x['reviewer_kind']=='ai-assisted' for x in identities) else 'human',
            'all_collection_decks_quality_passed':all(x['scientific_passed'] and x['visual_passed'] for x in identities),
            'quality_cost_promoted':False,'actual_paid_usd':None,'scope':'structural_read_reuse_not_slide_content_or_host_script_learning'}
    excluded=[]
    for value in dataset.get('excluded_task_dirs',[]):
        task=private(value);state=read(task/'task-state.json');request=read(task/'task.json');stats=state['stats']
        rows=[x for x in ledger if x.get('task_id')==request['task_id'] and 'response_status' in x]
        if request['task_id'] in {x['task_id'] for x in identities} or len(rows)!=stats.get('upstream_requests') or not stats.get('usage_complete'):
            raise ValueError('excluded collection cost must be complete and disjoint')
        excluded.append({'task_id':request['task_id'],'status':state['status'],'events_sha256':sha(task/'events.jsonl'),
                         'requests':len(rows),'denials':stats.get('denials',0),'proxy_peak_usd':stats['estimated_cost_usd'],'actual_paid_usd':None})
    report['excluded_collection']=excluded
    report['learning_total_requests']=report['trace_collection_requests']+sum(x['requests'] for x in excluded)
    report['learning_total_proxy_usd']=report['trace_collection_proxy_usd']+sum(x['proxy_peak_usd'] for x in excluded)
    variants=None
    if dataset.get('schema_variants'):
        capture=read(private(dataset['schema_variants']))
        if capture.get('method')!='actual_mcp_initialize_list_tools' or capture.get('model_requests')!=0:
            raise ValueError('schema variants need actual model-free MCP capture')
        variants=capture.get('variants')
        if not isinstance(variants,list) or len(variants)!=30 or schemas not in variants:
            raise ValueError('capture must cover actual complete schemas for all 1..30 page jobs')
        names=[t['name'] for t in schemas]
        if any([t.get('name') for t in v]!=names for v in variants):raise ValueError('whole tool order changed')
        report['schema_capture_sha256']=sha(private(dataset['schema_variants']))
    write(out/'source-evidence.json',evidence);write(out/'public-learning-report.json',report)
    if a.publish:
        if variants is None:raise ValueError('publishing requires actual whole schema variants')
        target=a.publish.resolve()
        if not target.is_relative_to((ROOT/'motif-libraries').resolve()) or target.exists():raise ValueError('new registered release directory required')
        target.mkdir()
        for name in ('library.json','online-manifest.json'):shutil.copyfile(manifest.parent/name,target/name)
        write(target/'tool-schemas.json',schemas)
        if variants:write(target/'tool-schema-variants.json',variants)
        write(target/'task.json',{'schema_version':1,'task_id':'ppt-web-v2-admission','session_id':'ppt-web-v2-admission',
            'intent':'Read current approved sources and explicitly selected current deck pages.','input_version':'0'*64,'bindings':{},
            'source_versions':{name:'0'*64 for name in data['version_fields']}})
        write(target/'source-evidence.json',evidence);write(target/'learning-report.json',report)
        code=list(guards)+[ROOT/'src/adapters/dsh_online_motif.mjs',ROOT/'src/motif_core/online_skill_runtime.mjs',ROOT/'scripts/learn-web-ppt-motif.py']
        code += [f for f in (ROOT/'scenarios/research_ppt').rglob('*') if f.is_file() and f.suffix in ('.py','.ts','.js') and not {'node_modules','tests','__pycache__'}&set(f.parts)]
        write(target/'certification.json',{'schema_version':1,'scene':'ppt','binding_policy':'ppt_uploaded_sources_v2',
            'matching_policy':'structural_only','certification_scope':'independent_trace_structure','quality_cost_promoted':False,
            'source_evidence_sha256':sha(target/'source-evidence.json'),'learning_report_sha256':sha(target/'learning-report.json'),
            'file_locks':{f.name:sha(f) for f in target.iterdir()},'code_locks':{str(f.relative_to(ROOT)):sha(f) for f in sorted(set(code))}})
        write(target/'entry.json',{'schema_version':1,'scene':'ppt','runtime_kind':'ppt_read_v2','mode':'execute','new_training':True,
            'files':{f.name:sha(f) for f in target.iterdir()},'scientific_quality_reviewed':'ai-assisted','quality_cost_promoted':False})
    print(json.dumps({'compiled_manifest':str(manifest),'published':str(a.publish) if a.publish else None,**report}))
if __name__=='__main__':main()
