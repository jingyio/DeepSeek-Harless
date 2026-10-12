"""Local matched full-write / RSI-plan / frozen Shadow / read-only execute.

All old fees remain in the shared ledger. Controlled same-paper revision only;
this does not claim full bibliography or PDF quality.
"""
import argparse
import copy
import fcntl
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
revision=module('patch_task_revision','scripts/paper-rsi-revision-task.py')
batch=revision.batch;base=batch.base;paid=base.parent
from src.adapters.trace_rsi_motif_compiler import CONFIG_FIELDS
from src.adapters.trace_rsi_batch_compiler import compile_trace_rsi_batches
from src.adapters.trace_tool_evidence import digest
EXP=ROOT/'.local/paper-reference/paper-rsi-patch-task-20261012-v1'
CONTEXT_VIEW=False
PRIVATE_EXPORT=False
OLD=ROOT/'.local/paper-reference/paper-rsi-revision-task-shadow-20261011-v6'
PATCH=ROOT/'.local/paper-reference/paper-rsi-patch-20261012-v1/frozen-tool.json'
AUDIT=ROOT/'.local/paper-reference/paper-rsi-revision-counts-20261011-v5/frozen-tool.json'
AUTH=ROOT/'.local/paper-reference/paper-rsi-local-20261012-v1/authorized-budget.json'
FILES=list(dict.fromkeys([*base.FILES,'src/adapters/report_patch_protocol.ts','src/adapters/revision_export_receipt.ts','scenarios/paper-submission/patch-rsi-task-server.ts',
 'scripts/paper-rsi-patch-task.py','src/adapters/dsh_trace_rsi_batch_execute.ts']))
PROMPT=base.PROMPT+batch.PROTOCOLS['tool-channel-v2']+'''
当前只进行报告结构修订，文献真实性和正式版本不在范围内。根据实际工具schema选择整份报告写入或局部计划入口：局部计划包含set_ids、keep_once_keys、remove_keys、add_records；计划里的值是你的当前修订决定，未变字段由工具保留，不把全部报告字段重复写入计划。新增仍是最小占位，不补科研结论。若旧重复版本的非标识字段冲突，明确交回判断而非猜测。
需要交付完整结构修订报告，使用提供的导出能力保存完整当前字段、来源、修订前快照和检查结果；最终答复只给产物名称、三类修订依据及真实性/正式版本未核验的限制，不重复粘贴完整JSON。导出结果的output是当前检查，存在false时不得声称成功。检查字段before_count/after_count是实际条目数，added_key_count/removed_key_count是唯一key变化，before_duplicate_key_count是初始重复key种类，after_duplicate_key_count是当前重复key种类；不要混淆这些口径。existing_fields_preserved和top_level_preserved分别检查已有条目的非arxiv_id字段及报告顶层字段。
read_task_state参数为空；检查和导出只接受当前input_id；写入接受当前report_sha256和相应的report或plan。旧句柄写入后失效。自行选择工具、顺序、数量，不预设流程。'''
save,load,sha=base.save,base.load,base.sha
paid.AUTH=AUTH;paid.EXP=base.EXP=batch.EXP=EXP
revision.EXP=EXP;batch.PROMPT=PROMPT

def prepare(case,protocol):
    fixture=load(OLD/'cases'/case/'fixture.json')
    seed=copy.deepcopy(fixture['seed_report'])
    catalog=load(OLD/'cases'/case/'initial-state/catalog.json')
    catalog['initial_report']=copy.deepcopy(seed)
    folder=EXP/'cases'/case;folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    cp=folder/'catalog.json'
    if cp.exists() and load(cp)!=catalog:raise ValueError('preserve_local_task_catalog')
    if not cp.exists():save(cp,catalog)
    fp=folder/'fixture.json'
    if not fp.exists():save(fp,fixture)
    source=ROOT/'.local/paper-reference/paper-rsi-overnight-20261011-v1/cases/t01_main/source'
    sources={str(p):sha(p) for p in source.rglob('*') if p.is_file()}
    if len(sources)!=14:raise ValueError('relocated_original_source_snapshot_required')
    sources[str(cp)]=sha(cp)
    frozen=load(AUDIT)
    code={str(ROOT/p):sha(ROOT/p) for p in FILES};code[str(PATCH)]=sha(PATCH)
    return {'case_id':case,'library_path':str(AUDIT),'tool_digest':frozen['manifest_digest'],
      'candidate_sha256':frozen['candidate_sha256'],'catalog_path':str(cp),'catalog_sha256':sha(cp),
      'source_files':sources,'source_version':digest({'source_files':sources,'case_id':case}),
      'code_files':code,'seed_report':seed,'fixture_path':str(fp),'patch_library_path':str(PATCH),
      'patch_library_sha256':sha(PATCH),'check_name':frozen['candidate']['name'],'write_protocol':protocol,
      'task_type':'same_paper_controlled_revision_recovery','execute_authorization_path':str(AUTH),
      **({'read_context_protocol':'revision_view_v1'} if CONTEXT_VIEW and protocol!='full_report' else {}),
      **({'private_export_policy':'current_task_revision_report_only'} if PRIVATE_EXPORT else {}),
      'execute_authorization_sha256':sha(AUTH)}

def verify(run):
    result=revision.verify(run)
    c=load(run/'config.json');artifact=Path(c['work'])/'revision-report.md';report=load(Path(c['work'])/'triage.json')
    catalog=load(c['catalog_path']);text=artifact.read_text() if artifact.is_file() else ''
    # Full data coverage, not typography or semantic approval.
    result['complete_structural_artifact']=bool(text and json.dumps(report,ensure_ascii=False,indent=2) in text and
      json.dumps(catalog['initial_report'],ensure_ascii=False,indent=2) in text and '未核验文献真实性' in text)
    result['stage_output_passed']=result['stage_output_passed'] and result['complete_structural_artifact']
    audit=Path(c['work'])/'execute.jsonl'
    rows=[json.loads(s) for s in audit.read_text().splitlines()] if audit.exists() else []
    skips=sum(r['kind']=='model_request_skipped_verified' for r in rows)
    unverified=sum(r['kind']=='model_request_skip_unverified' for r in rows)
    result.update(actual_model_skips=skips,unverified_skips=unverified)
    if unverified:result['stage_output_passed']=False
    save(run/'verification.json',result)
    metrics=load(run/'metrics.json');metrics.update(actual_model_skips=skips,verified_skips=skips,unverified_skips=unverified)
    save(run/'metrics.json',metrics)
    print(json.dumps({'artifact_and_execute_verification':result}),flush=True);return result

def task(case,mode,label):
    protocol='full_report' if mode=='full' else 'compact_plan'
    config=prepare(case,protocol);config['mode']='baseline' if mode in ['full','baseline'] else mode
    plugin=ROOT/'src/adapters/dsh_trace_rsi_shadow.ts';files=FILES
    if mode in ['shadow','execute']:
        library=load(EXP/'shadow-library.json')
        config.update(shadow_library=str(EXP/'shadow-library.json'),batch_library_digest=library['manifest_digest'],
          execute_library_digest=library['manifest_digest'])
        config['code_files'].update({str(ROOT/p):sha(ROOT/p) for p in batch.ADDITIONS})
        if config['code_files']!={**library['code_files_sha256'],**library['code_additions_sha256']}:
            raise ValueError('frozen_local_batch_code_drift')
        files=[*FILES,*batch.ADDITIONS]
        plugin=ROOT/('src/adapters/dsh_trace_rsi_batch_shadow.ts' if mode=='shadow' else 'src/adapters/dsh_trace_rsi_batch_execute.ts')
        if mode=='execute':
            scores=list((EXP/'runs').glob('shadow-*/shadow-score.json'))
            if not scores or not any(load(p)['strict_whole_request']>0 and load(p.parent/'verification.json')['stage_output_passed'] for p in scores):
                raise ValueError('successful_frozen_shadow_required_before_execute')
    path=EXP/'runs'/label/'config.json'
    policy='\n- id: spill-policy\n  config:\n    maxInlineBytes: 200000\n- insert:\n    - name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: paper_trace_rsi\n        transport: stdio\n        failOnStartupError: true\n        command: '+json.dumps(shutil.which('node'))+'\n        args: '+json.dumps(['--experimental-strip-types',str(ROOT/'scenarios/paper-submission/patch-rsi-task-server.ts')])+'\n        cwd: '+json.dumps(str(ROOT))+'\n        env:\n          SSS_TRACE_RSI_TASK_CONFIG: '+json.dumps(str(path))+'\n    - name: '+json.dumps(plugin.as_uri())+'\n'
    paid.EXP=EXP;paid.FILES=files
    run=paid.paid(label,PROMPT,policy,config,['SSS_TRACE_RSI_TASK_CONFIG'])
    effective,manifest=load(run/'config.json'),load(run/'manifest.json')
    manifest.update({k:effective[k] for k in CONFIG_FIELDS})
    manifest.update({k:v for k,v in effective.items() if 'policy' in k})
    manifest.update(binding_snapshot_stage='post_run_effective_config',control_protocol_version='compact-report-v1',
      control_protocol_sha256=digest(PROMPT),comparison_condition=mode,tool_result_inline_cap_bytes=200000)
    save(run/'manifest.json',manifest);verify(run)
    if mode=='shadow':batch.score(run)

def compile_library(labels):
    if (EXP/'shadow-library.json').exists():raise ValueError('preserve_frozen_local_library')
    runs=[EXP/'runs'/label for label in labels]
    if any(load(p/'config.json').get('write_protocol')!='compact_plan' or (p/'prompt.md').read_text()!=PROMPT for p in runs):
        raise ValueError('matched_compact_normal_training_required')
    library=compile_trace_rsi_batches(runs,root=ROOT,code_additions={str(ROOT/p):sha(ROOT/p) for p in batch.ADDITIONS})
    save(EXP/'shadow-library.json',library)
    print(json.dumps({'manifest_digest':library['manifest_digest'],'motifs':[
      {'anchor':m['anchor'],'batch':m['batch'],'sessions':m['training_session_count']} for m in library['motifs']]}),flush=True)

def main():
    global EXP,CONTEXT_VIEW,PROMPT,PRIVATE_EXPORT,AUTH
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['preview','full','baseline','compile','shadow','execute','verify','score'])
    parser.add_argument('--case',default='t02_abstract');parser.add_argument('--label');parser.add_argument('--training',nargs='+',default=['baseline-abstract','baseline-main'])
    parser.add_argument('--experiment',default=str(EXP.relative_to(ROOT)));parser.add_argument('--context-view',action='store_true')
    parser.add_argument('--private-export',action='store_true')
    parser.add_argument('--strict-tool-channel',action='store_true')
    a=parser.parse_args();EXP=ROOT/a.experiment
    if EXP.is_symlink() or not EXP.resolve().is_relative_to((ROOT/'.local/paper-reference').resolve()):raise ValueError('private_experiment_required')
    CONTEXT_VIEW=a.context_view
    PRIVATE_EXPORT=a.private_export
    if PRIVATE_EXPORT:
        AUTH=ROOT/'.local/paper-reference/paper-rsi-local-export-20261012-v1/authorized-budget.json';paid.AUTH=AUTH
    if CONTEXT_VIEW:
        PROMPT+='\n若读取返回view，这是本结构修订任务的完整决策视图：current_rows是当前key/arxiv_id，source_records/query_items是当前源稿目录配对，audit是同一input_id的RSI审计结果。完整原字段由局部计划工具保留并进入完整导出，不需要重读或重写。只依据当前视图做配对修订；缺科研证据或版本冲突仍交回判断。本视图与完整读取均未核验文献事实。'
    if a.strict_tool_channel:
        PROMPT+='\n消息格式再次明确：正常工具调度消息仅含tool-call块，不写“现在检查/接着导出”等控制旁白。所有修订决定、依据与限制留在完整最终答复；出现实质冲突、依据不足、失败恢复或需要授权时，照常说明，不得省略。这仅约束消息格式，不规定工具选择、顺序或数量。'
    paid.EXP=base.EXP=batch.EXP=revision.EXP=EXP;batch.PROMPT=PROMPT
    EXP.mkdir(parents=True,exist_ok=True,mode=0o700)
    if a.phase=='preview':
        _,prior,_=paid.rsi.reference.budget.account(EXP)
        print(json.dumps({'model':'deepseek-flash','reasoning_effort':'off','output_cap':8192,'request_limit':None,
          'compression':False,'execution_environment':'local','cumulative_cap_usd':10,'cumulative_estimated_usd':prior,
          'paid_enabled':False,'patch_ready':PATCH.is_file(),'execute_after_successful_frozen_shadow':True}));return
    if a.phase=='compile':compile_library(a.training);return
    if not a.label:parser.error('--label required')
    if a.phase in ['verify','score']:(verify if a.phase=='verify' else batch.score)(EXP/'runs'/a.label);return
    with (ROOT/'.local/paper-motif/.budget.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);task(a.case,a.phase,a.label)
if __name__=='__main__':main()
