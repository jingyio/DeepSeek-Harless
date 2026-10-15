"""One real Harness generation over normal traces -> heldout pure patch program.
No online execute; no request-count limit; all fees use the cumulative ledger.
"""
import argparse
import importlib.util
import json
import hashlib
import shutil
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.revision_tool_evidence import build_revision_packets
from src.adapters.report_patch_evidence import patch_cases
from src.adapters.trace_tool_evidence import digest

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
legacy=module('patch_learning_base','scripts/paper-rsi-tool-learning.py')
trace=module('patch_schema_base','scripts/paper-rsi-trace.py')
EXP=ROOT/'.local/paper-reference/paper-rsi-patch-20261012-v1'
SOURCES=[f'.local/paper-reference/paper-rsi-batch-shadow-20261011-v2/runs/{label}' for label in ['baseline-main','baseline-abstract']]
FILES=['scripts/paper-rsi-patch.py','src/adapters/report_patch_evidence.py','src/adapters/report_patch_protocol.ts',
       'src/adapters/dsh_patch_rsi_generation.ts','scenarios/paper-submission/patch-rsi-task-server.ts',
       'scenarios/paper-submission/patch-learning-server.ts','scripts/paper-rsi-tool-learning.py',
       'src/adapters/trace_rsi_program.ts','src/adapters/paper_rsi_program.ts']
save,load=trace.save_once,trace.load
legacy.AUTH=ROOT/'.local/paper-reference/paper-rsi-local-20261012-v1/authorized-budget.json'

def prepare():
    EXP.mkdir(parents=True,exist_ok=True,mode=0o700)
    relocated={}
    if ROOT!=Path('/root/autodl-tmp/jjy'):
        for label in SOURCES:
            config=load(ROOT/label/'config.json')
            for name in [*config['source_files'],*config['code_files'],config['catalog_path']]:
                if not name.startswith('/root/autodl-tmp/jjy/'):
                    raise ValueError('known_remote_source_root_required')
                relocated[name]=str(ROOT/name.removeprefix('/root/autodl-tmp/jjy/'))
            for name in config['code_files']:
                relocated[name]=str(ROOT/'.local/report-patch-rsi/source-code'/name.removeprefix('/root/autodl-tmp/jjy/'))
    data=build_revision_packets(SOURCES,root=ROOT,path_map=relocated or None)
    packets=[p for p in data['packets'] if p['motif_training_eligible']]
    if len({p['session_id'] for p in packets})<2:raise ValueError('two_normal_source_sessions_required')
    development,heldout=patch_cases(packets)
    # Schema describes structure only; independent example values stay private.
    contract={'name':'build_revision_patch','description':'由正常修订轨迹生成的局部计划转换：ID替换、等价重复去除、指定key移除与最小占位追加。',
      'input_schema':trace.infer_schema([c['input'] for c in development+heldout]),
      'output_schema':trace.infer_schema([c['expected'] for c in development+heldout])}
    for name,value in [('source-packets.json',data),('development.json',development),('heldout.json',heldout),('contract.json',contract)]:
        path=EXP/name
        if path.exists():
            if digest(load(path))!=digest(value):raise ValueError('preserve_patch_source_or_fixtures')
        else:save(path,value)
    return data,contract,development,heldout

def learn(label,repair_from=None):
    data,contract,development,_=prepare()
    prompt='''根据下面两个真实正常论文报告修订Session的局部输入与期望操作，生成可跨key/数量/顺序复用的纯JSON AST工具程序。目标/schema由实验范围预先固定，转换算法由你实现。
请调用submit_generated_program提交程序，通过开发样例后简短结束。唯一入口变量input；input.rows按当前数组顺序，rows_reverse按相反顺序，每个元素有key/path/id_path。input.plan有set_ids、keep_once_keys、remove_keys、add_records，值来自当前模型修订决定，不可写死历史key/标识/数组长度。
输出对象严格为replacements/removals/additions。replacements按rows顺序覆盖每个匹配set_ids的行，{path:该行id_path,value:计划新arxiv_id}。removals按rows_reverse顺序：移除remove_keys全部行；keep_once_keys只保留rows中该key第一行，移除其余行。additions完整保留plan.add_records。生成操作不包括科研判断、路径IO或宿主代码。
可用表达式：[lit,值]、[var,名字]、[get,对象表达式,字段表达式]、[let,名字,值表达式,主体]、[object,{字段:表达式}]、[array,...表达式]、[map,数组表达式,名字,主体]、[filter,数组表达式,名字,条件]、[if,条件,真,假]、[eq,a,b]、[not,a]、[and,...]、[or,...]、[count,数组]、[gt,a,b]、[at,数组,整数表达式]、[concat,...数组]。每个参数都必须是表达式，object字段映射和绑定名字除外。不能将input.plan属性当成入口变量；用get(var(input),lit(plan))读取。空数组/多个不同重复key/两位数索引都需支持。最大1500节点/40层，不能用JS。
契约：'''+json.dumps(contract,ensure_ascii=False)+'\n真实正常轨迹投影及开发样例：'+json.dumps(development,ensure_ascii=False)
    legacy.EXP=EXP;legacy.FILES=FILES
    if repair_from:
        previous=EXP/'runs'/repair_from/'answer.md'
        if not previous.is_file():raise ValueError('previous_generation_required_for_repair')
        try:json.loads(previous.read_text())
        except json.JSONDecodeError as error:
            prompt+='\n上一轮输出无法被标准JSON解析器读取，请自行修复括号/逗号等语法并重新输出完整裸JSON程序。\n解析器错误：'+str(error)+'\n上一轮原始输出：'+previous.read_text()
        else:raise ValueError('only_syntax_repair_supported_here')
    config_path=EXP/'runs'/label/'config.json'
    policy='\n- insert:\n    - name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: paper_patch_learning\n        transport: stdio\n        failOnStartupError: true\n        command: '+json.dumps(shutil.which('node'))+'\n        args: '+json.dumps(['--experimental-strip-types',str(ROOT/'scenarios/paper-submission/patch-learning-server.ts')])+'\n        cwd: '+json.dumps(str(ROOT))+'\n        env:\n          SSS_PATCH_RSI_GENERATION: '+json.dumps(str(config_path))+'\n    - name: '+json.dumps((ROOT/'src/adapters/dsh_patch_rsi_generation.ts').as_uri())+'\n'
    learning_files={str(ROOT/p):legacy.sha(ROOT/p) for p in FILES}
    learning_files.update({str(EXP/name):legacy.sha(EXP/name) for name in ['contract.json','development.json']})
    return legacy.paid(label,prompt,policy,{'mode':'patch_program_generation','source_packets_sha256':digest(data),
      'contract_path':str(EXP/'contract.json'),'development_path':str(EXP/'development.json'),
      'learning_files':learning_files},['SSS_PATCH_RSI_GENERATION'])

def certify(label):
    data,contract,development,heldout=prepare();run=EXP/'runs'/label
    if load(run/'metrics.json')['status']!='completed':raise ValueError('generation_not_completed')
    submitted=run/'work/passed-candidate.json'
    if submitted.is_file():program=load(submitted)['program']
    else:
        text=(run/'answer.md').read_text().strip()
        if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
        program=json.loads(text)
    candidate={'schema_version':1,**contract,'program':program}
    save(EXP/'candidate.json',candidate)
    for name,cases in [('development',development),('heldout',heldout)]:
        result=legacy.node(ROOT/'scripts/check-trace-rsi-tool.mjs',EXP/'candidate.json',EXP/(name+'.json'))
        checked=json.loads(result.stdout);save(EXP/(name+'-validation.json'),checked)
        if not checked['passed']:raise ValueError('generated_patch_failed:'+name)
    witnesses=[{'run_id':p['run_id'],'session_id':p['session_id'],'call_id':p['call_id'],
                'events_sha256':p['events_sha256']} for p in data['packets'] if p['motif_training_eligible']]
    provenance={'trace_bundle_sha256':digest(data),'source_witnesses':witnesses,
        'learning_session_id':load(run/'config.json')['session_id'],'learning_events_sha256':legacy.sha(run/'events.jsonl'),
        'candidate_sha256':digest(candidate),'algorithm_origin':'real_harness_submitted_json_ast_no_host_code_evaluation' if submitted.is_file() else 'real_harness_final_json_ast_no_host_tools',
        'source_relation':'observed_write_diff_to_parameterized_plan; existing_row_order_contract_not_full_bash_equivalence',
        'goal_and_schema_origin':'engineering_scoped_from_normal_trace_differences'}
    cert={'kind':'source_replay','status':'passed','heldout_cases':len(heldout),'development_cases':len(development),
          'fixture_sha256':digest(heldout),'semantic_quality':'not_reviewed','scope':'same_paper_plan_application_mutations_only'}
    body={'schema_version':1,'kind':'model_generated_trace_tool','candidate':candidate,'candidate_sha256':digest(candidate),
          'provenance':provenance,'provenance_sha256':digest(provenance),'certification':cert,'certification_sha256':digest(cert)}
    save(EXP/'frozen-tool.json',{**body,'manifest_digest':digest(body)})
    print(json.dumps({'passed':True,'development':len(development),'heldout':len(heldout),'manifest_digest':digest(body),'actual_model_skips':0}))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['preview','prepare','learn','certify']);parser.add_argument('--label',default='generate-v01')
    parser.add_argument('--repair-from');args=parser.parse_args()
    if args.phase=='preview':
        _,prior,_=legacy.rsi.reference.budget.account(EXP)
        print(json.dumps({'paid_enabled':False,'model':'deepseek-flash','reasoning_effort':'off','output_cap':8192,
          'request_limit':None,'cap_usd':legacy.rsi.load_budget_record(legacy.AUTH)['cap_usd'],'cumulative_estimated_usd':prior,'mode':'generation_then_frozen_shadow_and_execute'}));return
    if args.phase=='prepare':prepare();print('prepared from two normal sessions; no model calls');return
    if args.phase=='certify':certify(args.label);return
    with exclusive_lock((ROOT/'.local/paper-motif/.budget.lock')) as f:
        learn(args.label,args.repair_from)
if __name__=='__main__':main()
