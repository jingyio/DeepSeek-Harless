"""Frozen model-generated tool -> normal traces -> compiled prospective Shadow.

Paid phases are explicit and share all historical paper costs. Original papers
remain untouched. This stage validates structure, not bibliography truth.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.trace_rsi_motif_compiler import compile_trace_rsi_motifs, CONFIG_FIELDS
from src.adapters.trace_tool_evidence import digest
import importlib.util
spec=importlib.util.spec_from_file_location('trace_task_parent',ROOT/'scripts/paper-rsi-tool-learning.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
EXP=ROOT/'.local/paper-reference/paper-rsi-generated-task-shadow-20261011-v3'
ORIGIN=ROOT/'.local/paper-reference/paper-rsi-overnight-20261011-v2'
FROZEN=ROOT/'.local/paper-reference/paper-rsi-trace-tools-20261011-v3/frozen-tool.json'
FILES=['src/adapters/file_lock.py','scripts/paper-rsi-generated-task.py','scripts/check-trace-rsi-task.mjs',
 'scripts/paper-rsi-tool-learning.py','src/adapters/dsh_trace_rsi_shadow.ts',
 'src/adapters/trace_rsi_motif_compiler.py','scenarios/paper-submission/trace-rsi-task-server.ts',
 'src/adapters/trace_rsi_program.ts','src/adapters/paper_rsi_program.ts',
 'src/adapters/paper_triage_validation.ts','src/adapters/dsh_online_motif.mjs',
 'src/motif_core/online_skill_runtime.mjs','src/adapters/trace_tool_evidence.py']
PROMPT='''请修订本任务的论文参考文献分诊报告副本，目标是配对覆盖与当前稿件范围一致、没有重复或范围外条目。以当前冻结来源目录中的 query_items 为本轮范围；目录只代表源稿标识，不代表真实性已核验。已有条目除 arxiv_id 配对修正外，其余字段、字符串、数组内容和顺序必须原样保留，不重写 differences、source_urls、status、priority、formal_version 或 next_action；重复条目保留一份即可，报告其他顶层字段原样保留。缺失条目只新增 key、arxiv_id、status="待进一步核验" 的最小占位对象，不凭空生成事实、网址、正式版本或修复建议。自行检查修订结果。只操作本任务副本，不检查完整文献真实性，不联网。最终简短说明结构检查和语义限制。'''
def load(p):return json.loads(Path(p).read_text())
save,sha=parent.save,parent.sha
def prepare(case):
    inputs=load(ORIGIN/'inputs.json');row=inputs[case];source=Path(row['root'])/'source'
    diag,pairs=parent.rsi.scope(inputs,case)
    if len(pairs)<2 or len({k for k,_ in pairs})!=len(pairs):raise ValueError('one_arxiv_pair_per_key_required_for_this_stage')
    directory=EXP/'cases'/case;directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Virtual record locators link entries inside this source-derived catalog.
    # All underlying literal BibTeX files are separately hash-bound below.
    records=[];items=[]
    for index,(key,ident) in enumerate(pairs):
        path=f'records/{index:04d}.txt'
        records.append({'key':key,'record_path':path,'arxiv_ids':[ident]})
        items.append({'item_id':key+':'+ident,'id':ident,'source_path':path})
    catalog={'query_items':items,'cited_records':records,
      'provenance':{'case_id':case,'main':row['main'],'kind':'literal_bib_cited_arxiv_projection'}}
    catalog_path=directory/'catalog.json'
    if catalog_path.exists() and load(catalog_path)!=catalog:raise ValueError('preserve_catalog_version')
    if not catalog_path.exists():save(catalog_path,catalog)
    label=('baseline-' if case in ['t01_main','t02_abstract','t03_subset_a'] else 'shadow-')+case
    original=load(ORIGIN/'runs'/label/'work/triage.json')
    expected=set(map(tuple,pairs));original_pairs={(r['key'],r['arxiv_id']) for r in original['references']}
    if original_pairs!=expected or len(original['references'])!=len(pairs):raise ValueError('original_report_scope_invalid')
    seed=copy.deepcopy(original);seed['references']=seed['references'][1:]+[copy.deepcopy(seed['references'][-1])]
    seed['references'][0]['arxiv_id']='0000.00000'
    fixtures={'original_report':original,'seed_report':seed,'expected_pairs':pairs,'controlled_corruption':True}
    if (directory/'fixture.json').exists() and load(directory/'fixture.json')!=fixtures:raise ValueError('preserve_fixture_version')
    if not (directory/'fixture.json').exists():save(directory/'fixture.json',fixtures)
    frozen=load(FROZEN)
    sources={str(p):sha(p) for p in sorted(source.rglob('*')) if p.is_file()}
    sources[str(catalog_path)]=sha(catalog_path)
    return {'case_id':case,'library_path':str(FROZEN),'tool_digest':frozen['manifest_digest'],
      'candidate_sha256':frozen['candidate_sha256'],'catalog_path':str(catalog_path),'catalog_sha256':sha(catalog_path),
      'source_files':sources,'code_files':{str(ROOT/p):sha(ROOT/p) for p in FILES},
      'source_version':digest({'files':sources,'main':row['main'],'case_id':case}),
      'fixture_path':str(directory/'fixture.json'),'seed_report':seed}
def verify(run):
    c=load(run/'config.json');f=load(c['fixture_path']);report=load(Path(c['work'])/'triage.json')
    unchanged=all(sha(Path(p))==h for p,h in c['source_files'].items())
    code_unchanged=all(sha(Path(p))==h for p,h in c['code_files'].items())
    rows=report.get('references',[]);actual=[(r.get('key'),r.get('arxiv_id')) for r in rows]
    coverage=len(actual)==len(set(actual)) and set(actual)==set(map(tuple,f['expected_pairs']))
    seed_keys={r['key'] for r in f['seed_report']['references']}
    originals={r['key']:r for r in f['original_report']['references']}
    preserved=all({k:v for k,v in r.items() if k!='arxiv_id'}=={k:v for k,v in originals[r['key']].items() if k!='arxiv_id'}
      for r in rows if r.get('key') in seed_keys and r.get('key') in originals)
    additions=[r for r in rows if r.get('key') not in seed_keys]
    placeholders=all(r.get('status')=='待进一步核验' and set(r)<=set(['key','arxiv_id','status']) for r in additions)
    context={k:v for k,v in report.items() if k!='references'}=={k:v for k,v in f['seed_report'].items() if k!='references'}
    # Independent literal-source/snapshot oracle, separate from generated code.
    result={'completed':load(run/'metrics.json')['status']=='completed','normal_case_valid':True,
      'source_unchanged':unchanged and code_unchanged,'stage_output_passed':coverage and preserved and placeholders and context,
      'coverage_passed':coverage,'existing_judgments_preserved':preserved,'placeholders_only':placeholders,
      'report_context_preserved':context,'semantic_quality':'not_reviewed','cross_paper_validation':False}
    save(run/'verification.json',result)
    try:parent.node(ROOT/'scripts/check-trace-rsi-task.mjs',run/'config.json')
    except Exception as exc:save(run/'diagnostic-error.json',{'error':str(exc)[:300]})
    print(json.dumps({'run':run.name,'verification':result}),flush=True)
    return result
def task(case,mode,label):
    c=prepare(case);c['mode']=mode
    if mode=='shadow':
        c['shadow_library']=str(EXP/'shadow-library.json')
        if not Path(c['shadow_library']).is_file():raise ValueError('freeze_library_before_evaluation')
    config_path=EXP/'runs'/label/'config.json'
    policy='\n- insert:\n    - name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: paper_trace_rsi\n        transport: stdio\n        failOnStartupError: true\n        command: '+json.dumps(shutil.which('node'))+'\n        args: '+json.dumps(['--experimental-strip-types',str(ROOT/'scenarios/paper-submission/trace-rsi-task-server.ts')])+'\n        cwd: '+json.dumps(str(ROOT))+'\n        env:\n          SSS_TRACE_RSI_TASK_CONFIG: '+json.dumps(str(config_path))+'\n    - name: '+json.dumps((ROOT/'src/adapters/dsh_trace_rsi_shadow.ts').as_uri())+'\n'
    parent.EXP=EXP;parent.FILES=FILES
    run=parent.paid(label,PROMPT,policy,c,['SSS_TRACE_RSI_TASK_CONFIG'])
    # Append actually effective bindings for evidence validation. Existing
    # provider/budget snapshots are retained; config itself is not rewritten.
    manifest=load(run/'manifest.json');config=load(run/'config.json')
    manifest.update({k:config[k] for k in CONFIG_FIELDS});manifest['binding_snapshot_stage']='post_run_effective_config'
    save(run/'manifest.json',manifest);verify(run)
    if mode=='shadow' and (run/'events.jsonl').exists():score(run)
def compile_library(labels):
    target=EXP/'shadow-library.json'
    if target.exists():raise ValueError('preserve_frozen_library')
    library=compile_trace_rsi_motifs([EXP/'runs'/l for l in labels],root=ROOT)
    save(target,library)
    print(json.dumps({'manifest_digest':library['manifest_digest'],'motifs':[{'anchor':m['anchor'],'next':m['next'],'support':m['training_session_count']} for m in library['motifs']]}))
def score(run):
    es=parent.events(run);messages=[e for e in es if e['type']=='assistant/message']
    audit=[json.loads(l) for l in (run/'work/shadow.jsonl').read_text().splitlines()]
    predictions=[p for p in audit if p['kind'] in ['prediction','deferred']]
    if len(messages)!=len(predictions) or [p['request_ordinal'] for p in predictions]!=list(range(1,len(messages)+1)):
        raise ValueError('missing_prospective_request_boundaries')
    results={}
    for e in es:
        if e['type']!='tool/result':continue
        for b in e['data']['message']['content']:
            if b.get('type')=='tool-result' and not b.get('isError'):
                try:results[b['toolCallId']]=json.loads(''.join(x.get('text','') for x in b.get('content',[]) if x.get('type')=='text'))
                except ValueError:pass
    rows=[]
    for message,p in zip(messages,predictions):
        content=message['data']['message']['content'];prediction=p.get('prediction');outcome='no_prediction'
        if prediction:
            calls=[x for x in content if x['type']=='tool-call']
            actual=[{'tool':x['name'],'arguments':json.loads(x['arguments']) if isinstance(x['arguments'],str) else x['arguments']} for x in calls]
            if actual!=prediction['expected_tools']:outcome='different_next_operation'
            elif len(calls)!=1 or results.get(calls[0]['id'])!=prediction['expected_result']:outcome='different_result_or_version'
            elif not any(x['kind']=='shadow_result' and x['request_ordinal']==p['request_ordinal'] and x['verified'] for x in audit):outcome='live_result_unverified'
            elif any(x['type']!='tool-call' and not(x['type']=='text' and not x.get('text','').strip()) for x in content):outcome='local_match_text_requires_review'
            else:outcome='strict_whole_request'
        rows.append({'ordinal':p['request_ordinal'],'outcome':outcome})
    n=load(run/'metrics.json')['actual_requests'];strict=sum(x['outcome']=='strict_whole_request' for x in rows)
    local=sum(x['outcome'] in ['strict_whole_request','local_match_text_requires_review'] for x in rows)
    result={'actual_requests':n,'root_messages':len(rows),'strict_whole_request':strict,'matching_local_operation':local,
      'strict_ratio':strict/n,'actual_model_skips':0,'semantic_quality':'not_reviewed','rows':rows,
      'frozen_library_sha256':sha(EXP/'shadow-library.json')}
    save(run/'shadow-score.json',result);print(json.dumps(result),flush=True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['preview','baseline','shadow','compile','verify','score'])
    parser.add_argument('--case',default='t01_main');parser.add_argument('--label');parser.add_argument('--training',nargs='+',default=['baseline-main','baseline-abstract'])
    args=parser.parse_args();EXP.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.phase=='preview':print(json.dumps({'experiment':EXP.name,'model':'deepseek-flash','reasoning_effort':'off','output_cap':8192,'request_limit':None,'cumulative_cap_usd':parent.rsi.load_budget_record(parent.AUTH)['cap_usd'],'mode':'shadow_only_no_execute'}));return
    if args.phase=='compile':compile_library(args.training);return
    if args.phase in ['verify','score']:
        if not args.label:parser.error('--label required')
        (verify if args.phase=='verify' else score)(EXP/'runs'/args.label);return
    if not args.label:parser.error('--label required')
    lock=ROOT/'.local/paper-motif/.budget.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(lock) as stream:
        task(args.case,args.phase,args.label)
if __name__=='__main__':main()
