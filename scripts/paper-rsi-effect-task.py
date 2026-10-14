"""同题面/工具的新版状态守卫诊断，复用原控制器、模型与预算链。"""
import importlib.util
import copy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('effect_patch_task',ROOT/'scripts/paper-rsi-patch-task.py')
task=importlib.util.module_from_spec(spec);spec.loader.exec_module(task)
EXP=ROOT/'.local/paper-reference/paper-rsi-effect-task-20261012-v5'
LEARN=ROOT/'.local/paper-reference/paper-rsi-effect-guards-20261012-v1'
task.AUDIT=LEARN/'adapted-frozen-tool.json'
task.FILES.extend(['src/adapters/dsh_trace_rsi_effect_guard.ts','src/adapters/trace_rsi_effect_guards.py',
 'src/adapters/trace_rsi_schema_adaptation.py','scripts/paper-rsi-effect-task.py',str(LEARN/'guard-library.json')])
original_prepare=task.prepare
def prepare(case,protocol):
    alias=case in ('t11_already_covered','t12_id_only_no_add')
    config=original_prepare('t10_incremental' if alias else case,protocol)
    if alias:
        previous=task.load(ROOT/'.local/paper-reference/paper-rsi-patch-task-20261012-v4/runs/execute-incremental/config.json')
        report=task.load(Path(previous['work'])/'triage.json')
        catalog=task.load(config['catalog_path']);catalog['initial_report']=copy.deepcopy(report)
        if case=='t12_id_only_no_add':
            report['references'][0]['arxiv_id']='0000.00000'
            catalog['initial_report']=copy.deepcopy(report)
        folder=task.EXP/'cases'/case;folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=folder/'catalog.json'
        if path.exists() and task.load(path)!=catalog:raise ValueError('preserve_new_scope_catalog')
        if not path.exists():task.save(path,catalog)
        config['source_files'].pop(config['catalog_path']);config['source_files'][str(path)]=task.sha(path)
        fixture=task.load(config['fixture_path']);fixture['seed_report']=copy.deepcopy(report);fp=folder/'fixture.json'
        if not fp.exists():task.save(fp,fixture)
        config.update(case_id=case,seed_report=report,catalog_path=str(path),catalog_sha256=task.sha(path),fixture_path=str(fp),
            source_version=task.digest({'source_files':config['source_files'],'case_id':case}),
            task_type='same_paper_prior_completed_review' if case=='t11_already_covered' else 'same_paper_identifier_fault_without_addition')
    config.update(effect_guard_path=str(LEARN/'guard-library.json'),effect_guard_sha256=task.sha(LEARN/'guard-library.json'))
    return config
task.prepare=prepare
original_paid=task.paid.paid
def paid(label,prompt,policy,config,*args):
    mode=config['mode']
    if mode in ('shadow','execute'):
        old=(ROOT/f'src/adapters/dsh_trace_rsi_batch_{mode}.ts').as_uri()
        new=(ROOT/'src/adapters/dsh_trace_rsi_effect_guard.ts').as_uri()
        if policy.count(old)!=1:raise ValueError('single_public_plugin_slot_required')
        policy=policy.replace(old,new)
    return original_paid(label,prompt,policy,config,*args)
task.paid.paid=paid
if __name__=='__main__':
    sys.argv.extend(['--experiment',str(EXP.relative_to(ROOT)),'--context-view','--private-export','--strict-tool-channel'])
    task.main()
