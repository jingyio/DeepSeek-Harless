"""Fresh multi-file goals, with independent quality fixed before any model calls."""
from pathlib import Path
import shutil,sys
from common import ROOT,PREFIX,save,snapshot
from operation_prepare import prepare_case,PROMPT
from operation_tools_v2 import TOOLS
def prepare(base,work,*,label='multi',op='copy',read_sources=True,count=2):
    spec=prepare_case(base,work,label=label,read_result=True)
    names=['notes.txt']
    for i in range(1,count):
        name='note-'+str(i)+'.txt';(Path(work)/name).write_text('Independent source '+label+' '+str(i)+'\n');names.append(name)
    spec.update(initial_snapshot=snapshot(work),allowed_operations=[op],objective='先用批量读取工具实际读取全部原件，再完成明确的文件操作，并用批量读取工具核验全部实际产物。')
    spec['operation_contract'].update(validation_version='sss-file-operation-quality-v2',require_source_read=read_sources,
        actions=[{'op':op,'source':n,'destination':'quarantine/'+n if op=='quarantine' else 'results/'+n,'format':'none'} for n in names])
    save(Path(base)/'input.json',spec)
    (Path(base)/'prompt.md').write_text(PROMPT+'\n'+spec['objective']+'\n使用 pin_files(file_ids) 返回的实际 source_ids 调用 read_files；数组必须来自真实结果，完整覆盖请求集合。read_task.recovery_state 中的已执行计划只复用真实回执。')
    scenario={'schema_version':1,'name':'file_management','prompt':str(Path(base)/'prompt.md'),
        'servers':[{'server_name':'file_management','transport':'stdio','command':'${PYTHON}','args':['${PROJECT_ROOT}/scenarios/file-management/operation_tools_v2.py'],
           'cwd':'${PROJECT_ROOT}','env':{'FM_TASK_FILE':{'from_env':'FM_TASK_FILE'},'FM_OUTPUT':{'from_env':'FM_OUTPUT'},'FM_JOB_FILE':{'from_env':'FM_JOB_FILE'}}}],
        'allowed_tools':[PREFIX+n for n in TOOLS],'acceptance_guard':{'kind':'file_management','max_repairs':2,'durable_job':True,'interruptible':True}}
    save(Path(base)/'scenario.json',scenario);return spec
