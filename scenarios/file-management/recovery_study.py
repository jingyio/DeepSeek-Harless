"""New bounded acceptance-repair validation; old benchmark outcomes stay frozen."""
from __future__ import annotations
import argparse,json,shutil,sys
from pathlib import Path
from uuid import uuid4
from common import ROOT,HERE,DATA,digest,sha,save,snapshot,source_code
from report_study import PROMPT,task_scope,verify_report
from experiment import accounting,run_one

def prepare():
    parent=Path(json.loads((ROOT/'.local/file-management/report-current.json').read_text())['experiment'])
    old=json.loads((parent/'protocol.json').read_text());name='fm-acceptance-repair-20261013-'+uuid4().hex[:8]
    exp=ROOT/'.local/file-management'/name;exp.mkdir(mode=0o700);cases=[]
    plans=[('rename-fault-H','rename','H',True,False,0),('index-fault-L2','index','L2',True,False,0),
           ('rename-natural-H','rename','H',False,False,1),('rename-natural-L2','rename','L2',False,False,0),
           ('permission-exhaustion-H','rename','H',False,True,1)]
    for label,family,arm,fault,denied,variant in plans:
        c=next(c for c in old['tasks'] if c['role']=='benchmark' and c['family']==family and c['arm']=='H' and c['condition_id']==f'benchmark-v3-{variant}-{family}')
        spec=json.loads((Path(c['task_dir'])/'input.json').read_text());pristine=DATA/name/'pristine'/label;work=DATA/name/'workspaces'/label
        shutil.copytree(c['pristine'],pristine)
        # A fresh text version and workspace, separated from the frozen benchmark.
        (pristine/'inbox/minutes.txt').write_text(label+' research project graph workflow meeting\n')
        (pristine/'.experiment-copy').write_text(name+'-'+label);shutil.copytree(pristine,work)
        spec.update(task_id=name+'-'+label,workspace=str(work),initial_snapshot=snapshot(work),task_spec_revision=9)
        if denied:spec['allowed_operations']=[]
        td=exp/'tasks'/label;save(td/'input.json',spec)
        prompt=PROMPT+'\n原任务目标：'+spec['objective']
        if family=='rename':prompt+='\n编号必须按初始inbox全部文件的路径字典序统一计数，不得按扩展名重新从1编号。'
        if fault and family=='rename':prompt+='\n这是有标签的验收恢复故障注入：首轮先不移动文件，直接按当前身份submit_report，然后停止。系统给出任务程序验收失败通知后，再执行原目标并重新submit_report。不能伪造修改回执。'
        if fault and family=='index':prompt+='\n这是有标签的验收恢复故障注入，不作为任务准确率基准。首轮禁止调用build_index，无论原题如何要求，必须选择并实际读取全部文件、完整collect_reads，随后submit_report并立即停止，不主动补齐索引。只有收到系统“任务程序验收未通过”的Runtime消息后才能调用build_index，按原目标补齐索引并重新submit_report。'
        if denied:prompt+='\n本次没有任何文件写权限。只能如实报告不能完成，不得申请扩大权限或通过其他工具修改文件。'
        (td/'prompt.md').write_text(prompt);(td/'prompt.md').chmod(0o600)
        config=json.loads((Path(c['task_dir'])/'scenario.json').read_text());config['prompt']=str(td/'prompt.md');config['acceptance_guard']={'kind':'file_management','max_repairs':2};config.pop('completion_guard',None)
        save(td/'scenario.json',config);save(td/'scope.json',task_scope(spec))
        cases.append({'task_id':label,'task_dir':str(td),'workspace':str(work),'pristine':str(pristine),'initial_snapshot':spec['initial_snapshot'],
                      'input_sha256':digest(spec),'family':family,'arm':arm,'role':'recovery_validation','fault_injected':fault,'expected_terminal_failure':denied})
    (exp/'L2').mkdir();shutil.copyfile(parent/'L2/policy.json',exp/'L2/policy.json');(exp/'L2/policy.json').chmod(0o600)
    code=source_code()
    for n in ['src/adapters/scenario.py','src/adapters/dsh_entry_motif.ts','src/adapters/dsh_acceptance_guard.ts','src/adapters/dsh_online_motif.mjs','scripts/validate-file-delivery.py']:
        code[n]=sha(ROOT/n)
    protocol={'experiment_id':name,'parent':str(parent),'tasks':cases,'model':'deepseek-flash','reasoning_effort':'off','compression_enabled':False,
        'per_task_cap_usd':5,'total_cap_usd':1000,'max_steps':96,'max_output':4000,'max_repairs':2,'source_code':code,'L2_sha256':sha(exp/'L2/policy.json'),
        'series_before':accounting(),'old_outcomes_modified':False,'fault_injection_not_task_accuracy_benchmark':True}
    save(exp/'protocol.json',protocol)
    for n in code:
        target=exp/'frozen-source'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,target)
    save(ROOT/'.local/file-management/recovery-current.json',{'experiment':str(exp)})
    print(json.dumps({'experiment':str(exp),'tasks':len(cases),'maximum_additional_usd':25,'paid':False},ensure_ascii=False))
    return exp

def run(exp,case_name=None):
    p=json.loads((exp/'protocol.json').read_text())
    if any(sha(ROOT/n)!=h for n,h in p['source_code'].items()):raise ValueError('frozen recovery source changed')
    if sha(exp/'L2/policy.json')!=p['L2_sha256']:raise ValueError('frozen library changed')
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as stream:stream.write(exp.name)
    try:
        for c in p['tasks']:
            td=Path(c['task_dir'])
            if case_name and c['task_id']!=case_name:continue
            if list(td.glob('attempts/*/outcome.json')):continue
            o=run_one(exp,c,p,call_model=True,server_path=HERE/'report_tools.py',verify_result=verify_report,
                reentry_policy=exp/'L2/policy.json' if c['arm']=='L2' else None,reentry_task=td/'scope.json' if c['arm']=='L2' else None)
            attempt=Path(o['attempt']);save(attempt/'execution-source-code.json',p['source_code'])
            shutil.copytree(c['workspace'],attempt/'retained-final')
            trace=Path((o.get('run') or {}).get('acceptance_trace_dir','/no-trace'))
            checks=[json.loads(x.read_text()) for x in sorted(trace.glob('round-*/result.json'))]
            validation={'task':c['task_id'],'checks':checks,'initial_failed':bool(checks and not checks[0]['passed']),
                'final_passed':o['acceptance']['passed'],'expected_terminal_failure':c['expected_terminal_failure'],
                'closed_loop_verified':bool(o.get('run') and o['run'].get('acceptance_repairs',0)>0 and checks and checks[-1]['passed']),
                'same_task_permission_and_budget':True,'new_real_requests':(o.get('run') or {}).get('upstream_requests'),'new_estimated_usd':(o.get('run') or {}).get('budget_accounted_usd')}
            save(attempt/'recovery-validation.json',validation)
            print(json.dumps({k:v for k,v in validation.items() if k!='checks'},ensure_ascii=False),flush=True)
        rows=[json.loads(x.read_text()) for x in exp.glob('tasks/*/attempts/*/recovery-validation.json')]
        save(exp/'summary.json',{'experiment':exp.name,'tasks_completed':len(rows),'rows':rows,'series':accounting()})
    finally:lock.unlink()

def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path);p.add_argument('--case');p.add_argument('--call-model',action='store_true');a=p.parse_args()
    if a.call_model:
        exp=a.experiment or Path(json.loads((ROOT/'.local/file-management/recovery-current.json').read_text())['experiment']);run(exp,a.case)
    else:prepare()
if __name__=='__main__':main()
