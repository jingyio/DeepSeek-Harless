"""Fresh v2 ordinary tasks use the daily library; certification never touches final sets."""
import argparse,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
from common import ROOT,DATA,save,sha,snapshot
sys.path.insert(0,str(ROOT))
from operation_prepare_v2 import prepare as material
from src.adapters.persistent_file_rsi import default_config,status
from src.adapters.continuous_rsi import load_config,source_map,records
from src.motif_core.offline.experience_registry import read
from experiment import accounting

def prepare():
    exp=ROOT/'.local/file-management'/('fm-persistent-rsi-20261015-'+uuid4().hex[:8]);exp.mkdir(mode=0o700)
    cfgfile=default_config(True);cfg=load_config(cfgfile);tasks=[]
    for label,op,count in [('learn-two','copy',2),('learn-three','copy',3),('reuse-move','move',3)]:
        directory=exp/'tasks'/label;work=Path(cfg['workspace_roots'][0])/'ordinary'/exp.name/label
        spec=material(directory,work,label=label,op=op,count=count)
        tasks.append({'label':label,'directory':str(directory),'workspace':str(work),'task_sha256':sha(directory/'input.json'),
          'scenario_sha256':sha(directory/'scenario.json'),'snapshot':snapshot(work)})
    protocol={'experiment_id':exp.name,'tasks':tasks,'config_file':str(cfgfile),'config_sha256':sha(cfgfile),'state_root':cfg['state_root'],
      'source_code':source_map(),'driver_sha256':sha(__file__),'series_before':accounting(),'records_before':[r['session_id'] for r in records(cfg['state_root'])],
      'original_pdfs':{p.name:sha(p) for p in (ROOT/'testpdf').glob('*.pdf')},'final_used_for_learning':False,'paid':False}
    save(exp/'protocol.json',protocol);save(exp/'protocol-lock.json',{'sha256':sha(exp/'protocol.json')});(exp/'frozen-driver.py').write_bytes(Path(__file__).read_bytes())
    save(ROOT/'.local/file-management/persistent-operation-current.json',{'experiment':str(exp)});print(json.dumps({'experiment':str(exp),'paid':False,'tasks':3}),flush=True)

def summarize(exp,p):
    rr=[r for r in records(p['state_root']) if r['session_id'] not in p['records_before']]
    result={'tasks':[{k:r[k] for k in ('session_id','role','accepted','lifecycle_verified','cost_usd','upstream_requests','verified_motif_batches','failure_class')} for r in rr],
      'attempts_including_certification':len(rr),'requests':sum(r['upstream_requests'] for r in rr),'cost_usd':sum(r['cost_usd'] for r in rr),
      'daily_library':status(p['config_file']),'final_used_for_learning':False,'actual_bill_verified':False,'source_code_unchanged':source_map()==p['source_code']}
    save(exp/'summary.json',result);return result

def execute(exp):
    p=read(exp/'protocol.json')
    if sha(exp/'protocol.json')!=read(exp/'protocol-lock.json')['sha256'] or source_map()!=p['source_code'] or sha(__file__)!=p['driver_sha256'] or sha(p['config_file'])!=p['config_sha256']:raise ValueError('frozen study changed')
    loader=importlib.util.spec_from_file_location('key',ROOT/'scenarios/literature-notes/run-live.py');m=importlib.util.module_from_spec(loader);loader.loader.exec_module(m)
    env={**os.environ,'DEEPSEEK_API_KEY':m.load_key(m.KEY_FILE,os.environ)};state=Path(p['state_root'])
    for t in p['tasks']:
        td=Path(t['directory'])
        if (td/'result.json').exists():continue
        if sha(td/'input.json')!=t['task_sha256'] or sha(td/'scenario.json')!=t['scenario_sha256'] or snapshot(t['workspace'])!=t['snapshot']:raise ValueError('frozen ordinary material changed')
        before={r['session_id'] for r in records(state)};pending=[q for q in (state/'runs').glob('*/enrollment.json') if read(q)['task_file']==str(td/'input.json')]
        args=[sys.executable,str(ROOT/'scripts/run-scenario.py'),'--scenario',str(td/'scenario.json'),'--budget-usd','5','--max-steps','96','--max-output','4000','--call-model']
        if pending:args=[sys.executable,str(ROOT/'scripts/run-scenario.py'),'--rsi-resume',str(pending[0].parent),'--call-model']
        log=td/('stdout-'+uuid4().hex[:8]+'.log');env.update(FM_TASK_FILE=str(td/'input.json'),FM_OUTPUT=str(td/'delivery'))
        print(json.dumps({'starting':t['label'],'daily_library_without_rsi_config':True}),flush=True)
        with log.open('xb') as f:rc=subprocess.run(args,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
        rr=[r for r in records(state) if r['role']=='ordinary' and r['session_id'] not in before]
        if len(rr)!=1:raise ValueError('original ordinary task interrupted; resume its enrollment; raw log retained')
        save(td/'result.json',{'exit_code':rc,'record_file':str(state/'records'/(rr[0]['session_id']+'.json'))})
        time.sleep(1);deadline=time.monotonic()+900
        while (state/'worker.lock').exists():
            if time.monotonic()>deadline:raise RuntimeError('original certification still running')
            time.sleep(.5)
        result=summarize(exp,p);print(json.dumps({'finished':t['label'],'accepted':rr[0]['accepted'],'requests':rr[0]['upstream_requests'],'skips':rr[0]['verified_motif_batches'],'active':result['daily_library']['active_motifs']}),flush=True)
        if not rr[0]['accepted']:break
    return summarize(exp,p)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path);a.add_argument('--call-model',action='store_true');v=a.parse_args()
    if not v.experiment:prepare()
    elif v.call_model:print(json.dumps(execute(v.experiment)),flush=True)
    else:print(json.dumps({'paid':False,'task_cap':5,'learning_cap':25}))
