"""Real default Web task API/MCP, mock Provider; all source copies stay intact."""
import importlib.util,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
sp=importlib.util.spec_from_file_location('web_checks',ROOT/'scripts/check-web-tasks.py');check=importlib.util.module_from_spec(sp);sp.loader.exec_module(check)
from src.adapters.continuous_rsi import records,snapshot
from src.motif_core.offline.experience_registry import read

def main():
    results=[]
    with check.launch('file-management') as (client,base,out):
        listing=check.api(client,base);assert listing['scene_input_policy']=='registered_file_directory'
        policy=read(out/'policy.json');binding=policy['task_binding']['config'];source_before=snapshot(binding['files_dir']);before={r['session_id'] for r in records(read(binding['rsi_config'])['state_root'])}
        for bad in [
          {'op':'copy','source':'../notes.txt','destination':'out.txt','format':'none'},
          {'op':'convert','source':'notes.txt','destination':'out.jpg','format':'jpg'},
          {'op':'copy','source':'notes.txt','destination':'out.txt','format':'csv'}]:
            check.denied(client,base,{'action':'preview','request':{'instruction':json.dumps({'actions':[bad]})}})
        for op,dest,required in [('copy','results/web-copy.txt',True),('move','renamed/web-note.txt',False)]:
            goal={'objective':'验证文件目标、实际产物和任务间数据隔离','actions':[{'op':op,'source':'notes.txt','destination':dest,'format':'none'}],'require_result_read':required}
            draft=check.api(client,base,{'action':'preview','request':{'instruction':json.dumps(goal,ensure_ascii=False),'mode':'execute'}})
            assert draft['continuous_learning']['provider_mode']=='mock'
            check.submit(client,base,draft);task=check.wait_task(client,base,draft['task_id'])
            assert task['continuous_learning']['record_file'] and task['delivery']['mechanical_acceptance_passed']
            assert snapshot(binding['files_dir'])==source_before
            results.append({'task_id':task['task_id'],'status':task['status'],'requests':task['stats']['upstream_requests'],
                            'queue_record':task['continuous_learning']['record_file']})
        cfg=read(binding['rsi_config']);rr=[r for r in records(cfg['state_root']) if r['session_id'] not in before];assert len(rr)==2 and all(r['accepted'] and r['lifecycle_verified'] for r in rr)
        assert all(r['provider_mode']=='mock' for r in rr)
        value={'status':'passed','actual_default_Web_API_MCP':True,'tasks':results,'source_preserved':True,'actual_cloud_requests':0,
               'sealed_queue':True,'mock_not_training':True,'output':str(out)}
        (out/'operation-web-check.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(json.dumps(value,ensure_ascii=False))
    with check.launch('file-management','delay') as (client,base,out):
        goal={'actions':[{'op':'copy','source':'notes.txt','destination':'cancelled.txt','format':'none'}],'require_result_read':False}
        draft=check.api(client,base,{'action':'preview','request':{'instruction':json.dumps(goal),'mode':'execute'}})
        check.submit(client,base,draft);time.sleep(.2)
        check.api(client,base,{'action':'cancel','task_id':draft['task_id']})
        for _ in range(80):
            task=check.api(client,base,task_id=draft['task_id'])
            if task['continuous_learning'].get('record_file'):break
            time.sleep(.15)
        assert task['status']=='cancelled' and task['continuous_learning'].get('record_file'),task
        r=read(task['continuous_learning']['record_file']);assert not r['accepted'] and r['failure_class']=='cancelled' and r['accounting_complete'],r
        assert not task['stats']['pending_requests'],task
        print(json.dumps({'cancel_inflight_sealed':True,'cancelled_not_training':True,'actual_cloud_requests':0,'output':str(out)}))

if __name__=='__main__':main()
