"""Freeze fresh ordinary materials, run real learning, retain every failed attempt."""
import argparse,importlib.util,json,os,shutil,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
from common import ROOT,save,sha,snapshot
sys.path.insert(0,str(ROOT))
from management_prepare import prepare as material
from management_web import default_config
from src.adapters.continuous_rsi import load_config,source_map,records
from src.adapters.persistent_file_rsi import status
from src.motif_core.offline.experience_registry import read
from experiment import accounting

def prepare():
    exp=ROOT/'.local/management-studies'/('management-native-'+uuid4().hex[:8]);exp.mkdir(parents=True,mode=0o700)
    cfgfile=default_config(True);cfg=load_config(cfgfile);tasks=[]
    from zipfile import ZipFile
    from xml.sax.saxutils import escape
    from openpyxl import Workbook
    from PIL import Image
    original=sorted((ROOT/'testpdf').glob('*.pdf'))[0]
    for label,op in [('discover-a','copy'),('discover-b','copy'),('reuse-new','move')]:
        directory=exp/'tasks'/label;w=Path(cfg['workspace_roots'][0])/'ordinary'/exp.name/label;w.mkdir(parents=True,mode=0o700)
        name=label.replace('-','_');(w/(name+'.txt')).write_text('New notes for '+label+'\nVersion '+uuid4().hex)
        with ZipFile(w/(name+'.docx'),'w') as z:
            z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+escape('New research office memo '+label)+'</w:t></w:r></w:p></w:body></w:document>')
        d=Workbook();d.active.append(['experiment','value']);d.active.append([label,13 if op=='copy' else 27]);d.save(w/(name+'.xlsx'))
        Image.new('RGB',(31,25),(39,96,150)).save(w/(name+'.png'));shutil.copyfile(original,w/(name+'.pdf'))
        folders={'.pdf':'documents','.docx':'documents','.xlsx':'tables','.png':'images','.txt':'notes'}
        quality=[]
        for f in w.iterdir():
            quality.append({'kind':'file','source':f.name,'path':'organized/'+folders[f.suffix]+'/'+f.name})
            quality.append({'kind':'unchanged' if op=='copy' else 'missing','path':f.name})
        objective=('按文件类型自主整理全部资料到organized/的documents、tables、images、notes子目录。PDF和Word放documents，Excel放tables，图片放images，文本放notes。保留文件名和内容。'+('保留全部原件，通过复制整理。' if op=='copy' else '移动整理，原位置不留副本。')+'另创建organized/empty空目录。完成后核验实际文件并提交报告。')
        quality.append({'kind':'directory','path':'organized/empty'})
        spec=material(directory,w,task_id=uuid4().hex,objective=objective,owner='study-operator',workspace_id=label,quality=quality)
        tasks.append({'label':label,'directory':str(directory),'workspace':str(w),'task_sha256':sha(directory/'input.json'),'scenario_sha256':sha(directory/'scenario.json'),'snapshot':snapshot(w)})
    protocol={'experiment_id':exp.name,'tasks':tasks,'config_file':str(cfgfile),'config_sha256':sha(cfgfile),'state_root':cfg['state_root'],'source_code':source_map(),'driver_sha256':sha(__file__),'records_before':[r['session_id'] for r in records(cfg['state_root'])],
      'original_pdfs':{p.name:sha(p) for p in (ROOT/'testpdf').glob('*.pdf')},'series_before':accounting(),'final_used_for_learning':False,'provider':'DeepSeek Flash','reasoning_effort':'off','limits':cfg['limits'],'bill_verified':False}
    save(exp/'protocol.json',protocol);save(exp/'protocol-lock.json',{'sha256':sha(exp/'protocol.json')});save(ROOT/'.local/management-study-current.json',{'experiment':str(exp)});return {'experiment':str(exp),'paid':False}

def summary(exp,p):
    rr=[r for r in records(p['state_root']) if r['session_id'] not in p['records_before']]
    result={'tasks':[{k:r[k] for k in ('session_id','role','accepted','lifecycle_verified','cost_usd','upstream_requests','verified_motif_batches','failure_class')} for r in rr],'requests':sum(r['upstream_requests'] for r in rr),'cost_usd':sum(r['cost_usd'] for r in rr),'library':status(p['config_file']),'final_used_for_learning':False,'bill_verified':False,'source_unchanged':source_map()==p['source_code']}
    save(exp/'summary.json',result);return result

def execute(exp):
    p=read(exp/'protocol.json')
    if sha(exp/'protocol.json')!=read(exp/'protocol-lock.json')['sha256'] or source_map()!=p['source_code'] or sha(__file__)!=p['driver_sha256'] or sha(p['config_file'])!=p['config_sha256']:raise ValueError('frozen real protocol changed')
    loader=importlib.util.spec_from_file_location('key',ROOT/'scenarios/literature-notes/run-live.py');m=importlib.util.module_from_spec(loader);loader.loader.exec_module(m)
    env={**os.environ,'DEEPSEEK_API_KEY':m.load_key(m.KEY_FILE,os.environ)};state=Path(p['state_root'])
    for t in p['tasks']:
        td=Path(t['directory'])
        if (td/'result.json').exists():continue
        if sha(td/'input.json')!=t['task_sha256'] or sha(td/'scenario.json')!=t['scenario_sha256']:raise ValueError('frozen material changed')
        before={r['session_id'] for r in records(state)};pending=[q for q in (state/'runs').glob('*/enrollment.json') if read(q)['task_file']==str(td/'input.json')]
        args=[sys.executable,str(ROOT/'scripts/run-file-scenario.py'),'--scenario',str(td/'scenario.json'),'--rsi-config',p['config_file'],'--budget-usd','5','--max-steps','96','--max-output','4000','--call-model']
        if pending:args=[sys.executable,str(ROOT/'scripts/run-file-scenario.py'),'--rsi-resume',str(pending[0].parent),'--call-model']
        elif snapshot(t['workspace'])!=t['snapshot']:raise ValueError('frozen new source bytes changed')
        env.update(FM_TASK_FILE=str(td/'input.json'),FM_OUTPUT=str(td/'delivery'));log=td/('stdout-'+uuid4().hex[:8]+'.log')
        print(json.dumps({'starting':t['label'],'real_model':True}),flush=True)
        with log.open('xb') as f:rc=subprocess.run(args,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
        rr=[r for r in records(state) if r['role']=='ordinary' and r['session_id'] not in before]
        if len(rr)!=1:raise ValueError('original task interrupted or not sealed; preserve and resume its original enrollment')
        save(td/'result.json',{'exit_code':rc,'record_file':str(state/'records'/(rr[0]['session_id']+'.json'))})
        # Wait for the existing worker without duplicating certification.
        deadline=time.monotonic()+900
        time.sleep(1)
        while (state/'worker.lock').exists():
            if time.monotonic()>deadline:raise RuntimeError('original certification remains running')
            time.sleep(.5)
        print(json.dumps({'finished':t['label'],'accepted':rr[0]['accepted'],'requests':rr[0]['upstream_requests'],'skips':rr[0]['verified_motif_batches'],'active':status(p['config_file'])['active_motifs']}),flush=True)
        summary(exp,p)
        if not rr[0]['accepted']:break
    return summary(exp,p)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--experiment',type=Path);ap.add_argument('--call-model',action='store_true');a=ap.parse_args()
    print(json.dumps(execute(a.experiment) if a.experiment and a.call_model else prepare() if not a.experiment else summary(a.experiment,read(a.experiment/'protocol.json')),ensure_ascii=False),flush=True)
