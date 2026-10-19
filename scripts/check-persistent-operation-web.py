"""Free default-profile restart: same library, task, budget and journaled effects."""
import importlib.util,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
sp=importlib.util.spec_from_file_location('checks',ROOT/'scripts/check-web-tasks.py');c=importlib.util.module_from_spec(sp);sp.loader.exec_module(c)
from src.motif_core.offline.experience_registry import read,durable
def main():
    goal={'objective':'复制两个文件并核验全部实际产物','require_result_read':True,'actions':[
      {'op':'copy','source':'notes.txt','destination':'recovered/note.txt','format':'none'},
      {'op':'copy','source':'brief.docx','destination':'recovered/brief.docx','format':'none'}]}
    with c.launch('file-management','delay') as (client,base,out):
        listing=c.api(client,base);assert listing['learning_status']['persistent'];cfg=read(out/'policy.json')['task_binding']['config']['rsi_config']
        draft=c.api(client,base,{'action':'preview','request':{'instruction':json.dumps(goal),'mode':'execute'}});c.submit(client,base,draft)
        output=out/'tasks'/draft['task_id'];deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            state_file=output/'scene/delivery/operation-state-v2.json'
            if state_file.exists() and any(j['status']=='executed_verified' for j in read(state_file)['journals'].values()):break
            time.sleep(.05)
        else:raise AssertionError('first process did not reach a recorded effect boundary')
        before=read(output/'operation-job.json');assert before['requests']>0
    with c.launch('file-management') as (client,base,out2):
        assert read(out2/'policy.json')['task_binding']['config']['rsi_config']==cfg
        listing=c.api(client,base);assert any(t['task_id']==draft['task_id'] for t in listing['tasks'])
        task=c.api(client,base,task_id=draft['task_id']);assert task['status']=='interrupted',task
        c.api(client,base,{'action':'resume','task_id':draft['task_id'],'confirmation_digest':draft['confirmation_digest']})
        task=c.wait_task(client,base,draft['task_id'],seconds=60);assert task['continuous_learning']['record_file'] and task['delivery']['mechanical_acceptance_passed']
        after=read(output/'operation-job.json');s=read(output/'scene/delivery/operation-state-v2.json')
        assert before['limits']==after['limits'] and before['requests']<after['requests']<=before['limits']['max_requests']
        assert len(s['journals'])==1 and sum(len(j['completed']) for j in s['journals'].values())==2
        assert before['task_sha256']==after['task_sha256'] and after['accepted']
        value={'status':'passed','same_default_config_across_restart':True,'original_task':draft['task_id'],'requests_before':before['requests'],
            'requests_after':after['requests'],'original_limits_preserved':True,'one_plan_two_effects_no_duplicates':True,
            'actual_cloud_requests':0,'output':str(out2)};durable(out2/'persistent-recovery-check.json',value,exclusive=True);print(json.dumps(value))
if __name__=='__main__':main()
