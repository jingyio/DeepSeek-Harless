"""Explicit paid default-Web verification on new registered copies and a real library."""
import argparse,importlib.util,json,os,shutil,signal,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
sp=importlib.util.spec_from_file_location('checks',ROOT/'scripts/check-web-tasks.py');checks=importlib.util.module_from_spec(sp);sp.loader.exec_module(checks)
from src.adapters.continuous_rsi import load_config,records,source_map,snapshot
from src.motif_core.offline.experience_registry import read,durable,sha

def run(config_file,paid):
    from src.adapters.persistent_file_rsi import default_config
    config_file=default_config(True);cfg=load_config(config_file)
    if cfg.get('adapter')!='file_operations_v2' or cfg['provider_mode']!='real':raise ValueError('registered real file operation configuration required')
    if not paid:return {'paid':False,'task_cap_usd':5,'HTTP_limit':96,'tasks':3,'requires_explicit_call_model':True,'default_persistent_library':True}
    runid=uuid4().hex;out=ROOT/'.local/web/runs'/runid;exp=ROOT/'.local/file-management'/('fm-persistent-web-20261015-'+runid[:8]);exp.mkdir(mode=0o700)
    source=Path(cfg['workspace_roots'][0])/('web-source-'+runid[:8]);source.mkdir(mode=0o700);(source/'.experiment-copy').write_text(runid)
    (source/'notes.txt').write_text('Independent default Web input '+uuid4().hex+'\n')
    for name in ('brief.docx','ledger.xlsx','poster.png'):shutil.copyfile(ROOT/'.local/file-management-author/assets/a'/name,source/name)
    original_pdf=next((ROOT/'testpdf').glob('*.pdf'));shutil.copyfile(original_pdf,source/'paper.pdf')
    goals=[{'label':'batch-copy','goal':{'objective':'复制两个文件，实际读取全部原件和产物，保留真实回执。','require_result_read':True,'actions':[
      {'op':'copy','source':'notes.txt','destination':'web-copy/notes.txt','format':'none'},
      {'op':'copy','source':'brief.docx','destination':'web-copy/brief.docx','format':'none'}]}},
      {'label':'batch-move','goal':{'objective':'移动两个文件并实际读取全部产物，保留真实回执。','require_result_read':True,'actions':[
      {'op':'move','source':'notes.txt','destination':'web-move/notes.txt','format':'none'},
      {'op':'move','source':'brief.docx','destination':'web-move/brief.docx','format':'none'}]}},
      {'label':'batch-convert','goal':{'objective':'转换两个文件并实际读取全部产物，保留真实回执。','require_result_read':True,'actions':[
      {'op':'convert','source':'brief.docx','destination':'converted/brief.txt','format':'text'},
      {'op':'convert','source':'ledger.xlsx','destination':'converted/ledger.csv','format':'csv'}]}}]
    protocol={'source_code':source_map(),'driver_sha256':sha(__file__),'source_snapshot':snapshot(source),'goals':goals,
        'state_root':cfg['state_root'],'config_file':str(config_file.resolve()),'config_sha256':sha(config_file),
        'task_budget_usd':5,'task_requests':96,'max_output':4000,'max_repairs':2,'run_budget_usd':25,
        'original_pdfs':{p.name:sha(p) for p in (ROOT/'testpdf').glob('*.pdf')},'final_used_for_learning':False}
    durable(exp/'protocol.json',protocol,exclusive=True);durable(exp/'protocol-lock.json',{'sha256':sha(exp/'protocol.json')},exclusive=True)
    shutil.copyfile(__file__,exp/'frozen-driver.py');before={r['session_id'] for r in records(cfg['state_root'])}
    key_sp=importlib.util.spec_from_file_location('key',ROOT/'scenarios/literature-notes/run-live.py');key=importlib.util.module_from_spec(key_sp);key_sp.loader.exec_module(key)
    env={**os.environ,'DEEPSEEK_API_KEY':key.load_key(key.KEY_FILE,os.environ)};base='http://127.0.0.1:3084';child=None;rows=[]
    with (exp/'launcher.log').open('xb') as log:
      try:
        child=subprocess.Popen([sys.executable,str(ROOT/'scripts/harness-web.py'),'--scenario','file-management','--mode','execute',
          '--real-model','--port','3084','--run-id',runid,'--files-dir',str(source),
          '--budget-usd','5','--request-limit','96','--run-budget-usd','25','--run-request-limit','256'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        for _ in range(600):
            if (out/'access-url.txt').exists():break
            if child.poll() is not None:raise RuntimeError('Web launch failed; private launcher log retained')
            time.sleep(.1)
        else:raise RuntimeError('Web launch timeout')
        client=checks.client()
        with client.open((out/'access-url.txt').read_text(),timeout=20) as r:assert r.status==200
        listing=checks.api(client,base);assert listing['scene_input_policy']=='registered_file_directory'
        for task in goals:
            if source_map()!=protocol['source_code'] or snapshot(source)!=protocol['source_snapshot']:raise ValueError('frozen code/source changed')
            print(json.dumps({'starting':task['label'],'default_Web_API':True}),flush=True)
            draft=checks.api(client,base,{'action':'preview','request':{'instruction':json.dumps(task['goal'],ensure_ascii=False),'mode':'execute','budget_usd':5}})
            durable(exp/(task['label']+'-preview.json'),draft,exclusive=True)
            checks.submit(client,base,draft);deadline=time.monotonic()+360
            while True:
                value=checks.api(client,base,task_id=draft['task_id'])
                if value['status'] in checks.TERMINAL and value['continuous_learning'].get('record_file'):break
                if time.monotonic()>deadline:raise RuntimeError('original Web task still pending; do not cold restart')
                time.sleep(.25)
            durable(exp/(task['label']+'-outcome.json'),value,exclusive=True);rows.append({'label':task['label'],'task_id':value['task_id'],
                 'status':value['status'],'requests':value['stats']['upstream_requests'],'verified_skips':value['stats']['verified_skips'],
                 'delivery_passed':value.get('delivery',{}).get('mechanical_acceptance_passed',False),'record_file':value['continuous_learning']['record_file']})
            start=time.monotonic()
            while (Path(cfg['state_root'])/'worker.lock').exists():
                if time.monotonic()-start>900:raise RuntimeError('learning remains pending; retain queue and original budget')
                time.sleep(.5)
            print(json.dumps({'finished':task['label'],**rows[-1]}),flush=True)
            if value['status']!='completed':break
        after=[r for r in records(cfg['state_root']) if r['session_id'] not in before]
        result={'tasks':rows,'attempts_including_learning':len(after),'requests':sum(r['upstream_requests'] for r in after),
           'cost_usd':sum(r['cost_usd'] for r in after),'source_preserved':snapshot(source)==protocol['source_snapshot'],
           'original_pdfs_preserved':all(sha(ROOT/'testpdf'/n)==h for n,h in protocol['original_pdfs'].items()),
           'final_used_for_learning':False,'actual_bill_verified':False,'output':str(out),'experiment':str(exp),'state_root':cfg['state_root'],'no_rsi_config_supplied':True}
        durable(exp/'summary.json',result,exclusive=True);print(json.dumps(result),flush=True);return result
      finally:
        if child and child.poll() is None:
            child.send_signal(signal.SIGTERM)
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:child.kill();child.wait()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--rsi-config',type=Path);p.add_argument('--call-model',action='store_true');a=p.parse_args()
    if not a.call_model:print(json.dumps(run(a.rsi_config,False)))
    else:run(a.rsi_config,True)
