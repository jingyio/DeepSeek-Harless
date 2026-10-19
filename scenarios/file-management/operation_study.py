"""New ordinary workflows trigger generic DAG discovery without a prescribed graph."""
import argparse,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
from common import ROOT,DATA,save,sha,snapshot
sys.path.insert(0,str(ROOT))
from operation_prepare import prepare_case
from experiment import accounting
from src.adapters.continuous_rsi import source_map,records
from src.motif_core.offline.experience_registry import read

def prepare():
    exp=ROOT/'.local/file-management'/('fm-operation-rsi-20261015-'+uuid4().hex[:8]);exp.mkdir(mode=0o700)
    tasks=[]
    definitions=[('copy-a','copy','notes.txt','results/a.txt','none',False),
                 ('copy-b','copy','brief.docx','results/b.docx','none',False),
                 ('reuse-move','move','notes.txt','renamed/new-note.txt','none',False),
                 ('convert-readback','convert','brief.docx','converted/brief.txt','text',True),
                 ('archive-readback','archive','notes.txt','packages/notes.zip','none',True),
                 ('new-copy-readback','copy','brief.docx','verified/new.docx','none',True)]
    for label,op,source,dest,fmt,required in definitions:
        base=exp/'tasks'/label;work=DATA/exp.name/'ordinary'/label
        spec=prepare_case(base,work,label=label,op=op,source=source,destination=dest,format=fmt,read_result=required)
        tasks.append({'label':label,'task_dir':str(base),'workspace':str(work),'snapshot':spec['initial_snapshot'],
                      'task_sha256':sha(base/'input.json'),'scenario_sha256':sha(base/'scenario.json')})
    cfg={'schema_version':1,'format':'sss-continuous-rsi-v1','adapter':'file_operations_v1','state_root':str(ROOT/'.local/rsi'/exp.name),
         'workspace_roots':[str(DATA/exp.name)],'mode':'learn','provider_mode':'real','series_cap_usd':1000,'learning_cap_usd':25,
         'auto_worker':True,'allow_material_copy':True,'limits':{'budget_usd':5,'max_steps':96,'max_output':4000,'max_repairs':2}}
    save(exp/'rsi.json',cfg);p={'experiment_id':exp.name,'tasks':tasks,'state_root':cfg['state_root'],'source_code':source_map(),
        'driver_sha256':sha(__file__),'config_sha256':sha(exp/'rsi.json'),'series_before':accounting(),'paid':False,
        'final_used_for_learning':False,'graph_route_from_native_parameter_flow':True,'task_index_triggers_learning':False,
        'original_pdfs':{f.name:sha(f) for f in (ROOT/'testpdf').glob('*.pdf')}}
    save(exp/'protocol.json',p);save(exp/'protocol-lock.json',{'sha256':sha(exp/'protocol.json')})
    (exp/'frozen-driver.py').write_bytes(Path(__file__).read_bytes());save(ROOT/'.local/file-management/operation-current.json',{'experiment':str(exp)})
    print(json.dumps({'experiment':str(exp),'ordinary_tasks':6,'learning_cap_usd':25,'task_cap_usd':5,'series_cap_usd':1000,'paid_requests':0}),flush=True)

def summarize(exp,p):
    rr=records(p['state_root']);ordinary=[r for r in rr if r['role']=='ordinary']
    a=[read(f) for f in (Path(p['state_root'])/'learning').glob('*/activation.json')]
    result={'experiment_id':exp.name,'attempts':len(rr),'ordinary_passed':sum(r['accepted'] for r in ordinary),'ordinary_tasks':len(ordinary),
        'requests':sum(r['upstream_requests'] for r in rr),'cost_usd':sum(r['cost_usd'] for r in rr),'activations':a,
        'failures':[{'session_id':r['session_id'],'class':r.get('failure_class'),'requests':r['upstream_requests']} for r in rr if not r['accepted']],
        'net_benefit_required':False,'final_used_for_learning':False,'actual_bill_verified':False}
    save(exp/'summary.json',result);return result

def execute(exp,p):
    if sha(exp/'protocol.json')!=read(exp/'protocol-lock.json')['sha256'] or source_map()!=p['source_code'] or sha(__file__)!=p['driver_sha256']:raise ValueError('frozen operation study changed')
    loader=importlib.util.spec_from_file_location('key_loader',ROOT/'scenarios/literature-notes/run-live.py');m=importlib.util.module_from_spec(loader);loader.loader.exec_module(m)
    env={**os.environ,'DEEPSEEK_API_KEY':m.load_key(m.KEY_FILE,os.environ)};state=Path(p['state_root'])
    for t in p['tasks']:
        td=Path(t['task_dir'])
        if (td/'result.json').exists():continue
        if (td/'started.json').exists():raise ValueError('incomplete original task retained; no cold restart')
        if sha(td/'input.json')!=t['task_sha256'] or sha(td/'scenario.json')!=t['scenario_sha256'] or snapshot(t['workspace'])!=t['snapshot']:raise ValueError('frozen task/material changed')
        before={r['session_id'] for r in records(state)};save(td/'started.json',{'original_task_bounds_unchanged':True})
        env.update(FM_TASK_FILE=str(td/'input.json'),FM_OUTPUT=str(td/'delivery'))
        print(json.dumps({'starting':t['label'],'ordinary_CLI':True}),flush=True)
        with (td/'stdout.log').open('xb') as log:
            status=subprocess.run([sys.executable,str(ROOT/'scripts/run-file-scenario.py'),'--scenario',str(td/'scenario.json'),'--rsi-config',str(exp/'rsi.json'),
                '--budget-usd','5','--max-steps','96','--max-output','4000','--call-model'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
        rows=[r for r in records(state) if r['role']=='ordinary' and r['session_id'] not in before]
        if len(rows)!=1:raise ValueError('ordinary task did not seal; original log retained')
        r=rows[0];save(td/'result.json',{'session_id':r['session_id'],'record_sha256':sha(state/'records'/(r['session_id']+'.json')),'exit_code':status})
        time.sleep(1);start=time.monotonic()
        while (state/'worker.lock').exists():
            if time.monotonic()-start>900:raise ValueError('learning service pending; state retained')
            time.sleep(.5)
        worker_logs=sorted(state.glob('worker-logs/*.log'),key=lambda f:f.stat().st_mtime)
        if worker_logs and 'Traceback (most recent call last)' in worker_logs[-1].read_text():
            save(exp/'learning-stop.json',{'reason':'automatic_worker_failed','log':str(worker_logs[-1]),'raw_results_retained':True})
            return summarize(exp,p)
        result=summarize(exp,p)
        print(json.dumps({'finished':t['label'],'accepted':r['accepted'],'requests':r['upstream_requests'],'graphs':len(result['activations'])}),flush=True)
        if any(v['class']=='provider_unavailable' for v in result['failures']):
            save(exp/'provider-stop.json',{'reason':'provider_unavailable_after_original_task_retries','raw_results_retained':True});return result
    return summarize(exp,p)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path);a.add_argument('--call-model',action='store_true');args=a.parse_args()
    if not args.experiment:prepare()
    elif not args.call_model:print(json.dumps({'paid':False,'ordinary_tasks':6,'task_cap_usd':5,'learning_cap_usd':25}))
    else:print(json.dumps(execute(args.experiment,read(args.experiment/'protocol.json'))),flush=True)
