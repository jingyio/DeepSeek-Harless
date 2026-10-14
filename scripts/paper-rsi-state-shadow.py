"""Learn continuation state from existing normal traces, then prospective Shadow.

No execute mode, no new training payments, no changes to the tool or prompt.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.trace_rsi_state_compiler import ADDITIONS,compile_stateful_trace_motifs
from src.adapters.trace_rsi_motif_compiler import CONFIG_FIELDS
spec=importlib.util.spec_from_file_location('state_task_base',ROOT/'scripts/paper-rsi-generated-task.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
EXP=ROOT/'.local/paper-reference/paper-rsi-state-shadow-20261011-v1'
TRAIN=ROOT/'.local/paper-reference/paper-rsi-generated-task-shadow-20261011-v3/runs'
base.EXP=EXP
FILES=[*base.FILES,*ADDITIONS]
save,load,sha=base.save,base.load,base.sha

def compile_library():
    target=EXP/'shadow-library.json'
    if target.exists():raise ValueError('preserve_frozen_state_library')
    library=compile_stateful_trace_motifs([TRAIN/'baseline-main',TRAIN/'baseline-abstract'],
      {str(ROOT/p):sha(ROOT/p) for p in ADDITIONS},root=ROOT)
    save(target,library)
    print(json.dumps({'manifest_digest':library['manifest_digest'],'training_paid_requests':0,
      'guards':[{k:g[k] for k in ['motif_id','status','condition','positive_count','negative_count']} for g in library['guards']]}),flush=True)

def shadow(case,label):
    library=load(EXP/'shadow-library.json');config=base.prepare(case)
    config.update(mode='shadow',shadow_library=str(EXP/'shadow-library.json'),state_library_digest=library['manifest_digest'])
    config['code_files']={str(ROOT/p):sha(ROOT/p) for p in FILES}
    if config['code_files']!=library['derived_library']['code_files_sha256']:raise ValueError('state_library_code_drift')
    path=EXP/'runs'/label/'config.json'
    policy='\n- insert:\n    - name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: paper_trace_rsi\n        transport: stdio\n        failOnStartupError: true\n        command: '+json.dumps(shutil.which('node'))+'\n        args: '+json.dumps(['--experimental-strip-types',str(ROOT/'scenarios/paper-submission/trace-rsi-task-server.ts')])+'\n        cwd: '+json.dumps(str(ROOT))+'\n        env:\n          SSS_TRACE_RSI_TASK_CONFIG: '+json.dumps(str(path))+'\n    - name: '+json.dumps((ROOT/'src/adapters/dsh_trace_rsi_state_shadow.ts').as_uri())+'\n'
    base.parent.EXP=EXP;base.parent.FILES=FILES
    run=base.parent.paid(label,base.PROMPT,policy,config,['SSS_TRACE_RSI_TASK_CONFIG'])
    effective=load(run/'config.json');manifest=load(run/'manifest.json')
    manifest.update({k:effective[k] for k in CONFIG_FIELDS})
    manifest.update(state_library_digest=effective['state_library_digest'],binding_snapshot_stage='post_run_effective_config')
    save(run/'manifest.json',manifest);base.verify(run)
    if (run/'events.jsonl').exists():base.score(run)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['preview','compile','shadow','verify','score'])
    parser.add_argument('--case',default='t03_subset_a');parser.add_argument('--label');args=parser.parse_args()
    EXP.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.phase=='preview':
        print(json.dumps({'experiment':EXP.name,'model':'deepseek-flash','reasoning_effort':'off','output_cap':8192,
          'request_limit':None,'compression':False,'cumulative_cap_usd':base.parent.rsi.load_budget_record(base.parent.AUTH)['cap_usd'],
          'training':'two_verified_existing_normal_sessions','mode':'shadow_only_no_execute','prompt_changed':False}));return
    if args.phase=='compile':compile_library();return
    if not args.label:parser.error('--label required')
    if args.phase in ['verify','score']:(base.verify if args.phase=='verify' else base.score)(EXP/'runs'/args.label);return
    lock=ROOT/'.local/paper-motif/.budget.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(lock) as stream:
        shadow(args.case,args.label)
if __name__=='__main__':main()
