"""Use composed RSI-generated coverage/count branches, then frozen Shadow.

Reuses the unchanged MCP/observer/compiler. Only current data binding and
independent acceptance differ from the preceding catalog-coverage experiment.
"""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('revision_batch_base',ROOT/'scripts/paper-rsi-batch-shadow.py')
batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch)
base=batch.base
from src.adapters.revision_tool_evidence import revision_facts
from src.adapters.trace_tool_evidence import digest

EXP=ROOT/'.local/paper-reference/paper-rsi-revision-task-shadow-20261011-v6'
FROZEN=ROOT/'.local/paper-reference/paper-rsi-revision-counts-20261011-v5/frozen-tool.json'
base.EXP=batch.EXP=EXP;base.FROZEN=FROZEN
base.FILES=[*base.FILES,'scripts/paper-rsi-revision-task.py','src/adapters/revision_tool_evidence.py']
batch.FILES=[*base.FILES,*batch.ADDITIONS]
original_prepare=base.prepare

def prepare(case):
    # Harness normalizes long MCP global names; the current observer requires
    # the literal registered name. Reject incompatible names before model use.
    if len('mcp__paper_trace_rsi__'+base.load(FROZEN)['candidate']['name'])>64:
        raise ValueError('short_mcp_name_required_for_current_trace_observer')
    # The legacy fixture stores tuple pairs as JSON arrays. Compare decoded
    # pairs in its original in-memory shape, without touching historical files.
    original_load=base.load
    def fixture_load(path):
        value=original_load(path)
        if Path(path).name=='fixture.json' and value.get('controlled_corruption') is True:
            value={**value,'expected_pairs':[tuple(pair) for pair in value['expected_pairs']]}
        return value
    try:
        base.load=fixture_load;config=original_prepare(case)
    finally:base.load=original_load
    # Keep the base catalog immutable; a separate snapshot adds the task-start
    # report. Repeated prepares preserve both versions without overriding either.
    original=Path(config['catalog_path']);catalog=base.load(original)
    path=original.parent/'initial-state'/'catalog.json'
    catalog['initial_report']=config['seed_report']
    if path.exists() and base.load(path)!=catalog:raise ValueError('revision_initial_report_changed')
    if not path.exists():base.save(path,catalog)
    config['catalog_path']=str(path)
    # Actual task-start state is data, not the fixture's hidden original gold.
    if 'initial_report' in catalog and catalog['initial_report']!=config['seed_report']:
        raise ValueError('revision_initial_report_changed')
    if 'initial_report' not in catalog:raise ValueError('task_initial_report_snapshot_required')
    config['catalog_sha256']=base.sha(path)
    config['source_files'][str(path)]=config['catalog_sha256']
    config['source_version']=digest({'source_files':config['source_files'],'case_id':case})
    return config

def verify(run):
    config=base.load(run/'config.json');report=base.load(Path(config['work'])/'triage.json');catalog=base.load(config['catalog_path'])
    facts=revision_facts(catalog['initial_report'],report,catalog);m=facts['metrics']
    source_ok=all(base.sha(Path(p))==h for p,h in {**config['source_files'],**config['code_files']}.items())
    quality={'completed':base.load(run/'metrics.json')['status']=='completed','normal_case_valid':True,
        'source_unchanged':source_ok,'stage_output_passed':all(m[k] for k in ('coverage_valid','existing_fields_preserved','top_level_preserved','placeholders_valid')),
        'coverage_passed':m['coverage_valid'],'existing_judgments_preserved':m['existing_fields_preserved'],
        'report_context_preserved':m['top_level_preserved'],'placeholders_only':m['placeholders_valid'],
        'semantic_quality':'not_reviewed','cross_paper_validation':False,'actual_model_skips':0}
    base.save(run/'verification.json',quality);base.save(run/'revision-facts.json',facts)
    print(json.dumps({'run':run.name,'verification':quality,'counts_and_differences':m}),flush=True)
    return quality

base.prepare=prepare;base.verify=verify
batch.PROTOCOL_VERSION='tool-channel-v2';batch.PROTOCOL=batch.PROTOCOLS['tool-channel-v2']
batch.PROMPT=base.PROMPT+batch.PROTOCOL+'''
当前工具组合了 RSI 从轨迹生成的目录配对覆盖、计数、字段保留代码。before_count/after_count是实际对象数；added_key_count/removed_key_count是相对任务开始新增/移除的唯一key数；before_duplicate_key_count只计算任务开始的重复key种类数，修订后仍表示初始状态，不能声称它下降或代表当前重复对象数。新增或删除对象数不能直接拿唯一key变化代替。existing_fields_preserved检查已有非arxiv_id字段，top_level_preserved检查references之外全部顶层字段；任一false时修复副本或明确未合格，不得声称保留通过。依据已检查版本组织最终说明，不重新口算已提供的指标，仍完整保留修订依据和限制。本工具不核验文献事实或正式版本。工具选择和顺序由你决定。'''
batch.PROMPT+='''
工具参数约定仅复述实际schema，不预设调用顺序：read_task_state参数为空对象；生成检查工具只接受input_id；write_report只接受report_sha256和report两个字段，禁止携带input_id或其他字段。写入返回的新input_id用于后续检查，旧句柄失效。若工具拒绝参数，应按其schema修正参数，不能重复发送同一个非法对象。'''
batch.PROMPT+='''
changed_existing_records返回确实违反非arxiv_id字段保留要求的当前对象，不包括新增占位；去重本身不会造成这个检查失败。若列表非空，对照input.before_report中同key的旧对象，恢复违规字段和数组原值，保留已获依据的arxiv_id修正，再验证。若旧版本之间有实质冲突，明确交回语义判断，不能凭空猜测"占位/去重导致false"或宣称没有改写。新增占位仍严格只包含key、arxiv_id、status="待进一步核验"，不填任何其他字段。'''
batch.PROMPT+='''
after_duplicate_key_count是当前报告中重复key的种类数，目标为0。若该值大于0或keys_match_query_items=false，尚未完成配对覆盖/去重修订，不能把对象数多于唯一key数解释为无重复，也不能把目录比较口径猜成工具异常；继续依据实际报告、目录与工具结果修复或如实说明具体阻塞。'''

def main():
    global EXP,FROZEN
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['preview','baseline','compile','shadow','verify','score'])
    parser.add_argument('--case',default='t01_main');parser.add_argument('--label');parser.add_argument('--training',nargs='+',default=['baseline-main','baseline-abstract'])
    parser.add_argument('--experiment',default=str(EXP.relative_to(ROOT)))
    parser.add_argument('--tool-library',default=str(FROZEN.relative_to(ROOT)))
    args=parser.parse_args()
    def private(value):
        p=ROOT/value
        if p.is_symlink() or not p.resolve().is_relative_to((ROOT/'.local').resolve()):raise ValueError('private_experiment_and_tool_required')
        return p
    EXP=private(args.experiment);FROZEN=private(args.tool_library)
    base.EXP=batch.EXP=EXP;base.FROZEN=FROZEN;EXP.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.phase=='preview':
        _,prior,_=base.parent.rsi.reference.budget.account(EXP)
        print(json.dumps({'experiment':EXP.name,'paid_enabled':False,'model':'deepseek-flash','reasoning_effort':'off',
            'output_cap':8192,'request_limit':None,'compression':False,'cumulative_cap_usd':8,'cumulative_estimated_usd':prior,
            'mode':'shadow_only_no_execute','same_prompt_for_baseline_and_shadow':True,
            'tool_ready':FROZEN.is_file(),'field_preservation_tool':FROZEN.is_file() and
                'existing_fields_preserved' in base.load(FROZEN)['candidate']['output_schema']['properties']}));return
    if args.phase=='compile':batch.compile_library(args.training);return
    if not args.label:parser.error('--label required')
    if args.phase in ('verify','score'):(verify if args.phase=='verify' else batch.score)(EXP/'runs'/args.label);return
    with (ROOT/'.local/paper-motif/.budget.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);batch.task(args.case,args.phase,args.label)

if __name__=='__main__':main()
