"""Free public CLI/SDK/MCP: v2 arrays and repeated graph execution; mock stays isolated."""
import argparse,asyncio,importlib.util,json,os,sys,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import DATA,save
from operation_prepare_v2 import prepare
from src.adapters.continuous_rsi import load_config,initialize,actual_schemas,source_map,records
from src.adapters.mcp_learning import adapter
from src.adapters.file_scenario import prepare_scenario
from src.motif_core.offline.operation_graph import catalog
from src.motif_core.offline.experience_registry import ExperienceRegistry,digest,read

def run(fixture,crash=False):
    uid='free-persistent-sdk-'+uuid4().hex[:8];out=ROOT/'.local/persistent-checks'/uid;work=DATA/uid/'source';spec=prepare(out,work)
    if crash:spec['recovery_crash_after_publish']=True;save(out/'input.json',spec)
    state=ROOT/'.local/rsi'/uid;cfg={'schema_version':1,'format':'sss-continuous-rsi-v1','adapter':'file_operations_v2',
       'state_root':str(state),'workspace_roots':[str(work.parent)],'mode':'observe','provider_mode':'mock','series_cap_usd':1000,
       'learning_cap_usd':25,'auto_worker':False,'allow_material_copy':True,'limits':{'budget_usd':5,'max_steps':96,'max_output':4000,'max_repairs':2}}
    save(out/'rsi.json',cfg)
    if fixture:
        ct=catalog(asyncio.run(actual_schemas(prepare_scenario(out/'scenario.json'),out/'input.json',out/'probe','file_operations_v2',{'FM_JOB_FILE':str(out/'unused-probe-job.json')})))
        names=['mcp__file_management__pin_files','mcp__file_management__read_files'];nodes=[{'tool':names[0],'bindings':{}},{'tool':names[1],'bindings':{'source_ids':{'node':0,'path':'source_ids'}}}]
        a={'kind':'learned_mcp_operation_dag','status':'trace_validated_read_only','certification_contract':'sss-operation-certification-v2',
          'execution_version':adapter(cfg['adapter']).scope(spec)['execution_version'],'max_nodes':8,'nodes':nodes,'tool_contracts':{n:ct[n] for n in names},
          'source_task_fingerprints':['explicit-mock-one','explicit-mock-two'],'validation_task_fingerprint':'explicit-mock-cert'}
        a['certified_digest']=digest(a);p={'schema_version':1,'format':'sss-operation-graph-v2','execution_version_sha256':a['execution_version'],'artifact':a};p['policy_digest']=digest(p)
        save(out/'mock-interpreter-fixture.json',p);initialize(load_config(out/'rsi.json'));reg=ExperienceRegistry(state/'registry');relative,h=reg.object(out/'mock-interpreter-fixture.json')
        view={'schema_version':1,'format':'sss-experience-registry-v1','generation':0,'parent_digest':None,'reason':'explicit mock only',
          'automatic_selection_uses_profile_id':False,'entries':[{'entry_id':p['policy_digest'],'kind':'operation_graph','payload':relative,'sha256':h,'artifact_digest':p['policy_digest'],
          'runtime_source':source_map(adapter(cfg['adapter']).runtime_sources()),'state':'candidate','activated_generation':1}]};view['registry_digest']=digest(view)
        save(state/'fixture-registry.json',view);cfg.update(role='candidate_certification',registry_file=str(state/'fixture-registry.json'));save(out/'rsi.json',cfg)
    sp=importlib.util.spec_from_file_location('fixture',ROOT/'scripts/operation-v2-fixture.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
    server=ThreadingHTTPServer(('127.0.0.1',0),m.Provider);server.requests=[];thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    os.environ.update(SSS_MOCK_ENDPOINT=f'http://127.0.0.1:{server.server_port}',DEEPSEEK_API_KEY='mock',FM_TASK_FILE=str(out/'input.json'),FM_OUTPUT=str(out/'delivery'))
    sp=importlib.util.spec_from_file_location('runner',ROOT/'scripts/run-file-scenario.py');runner=importlib.util.module_from_spec(sp);sp.loader.exec_module(runner)
    sys.argv=['scenario','--scenario',str(out/'scenario.json'),'--rsi-config',str(out/'rsi.json'),'--budget-usd','5','--max-steps','96','--max-output','4000','--call-model']
    try:
        status=runner.main()
        if crash:
            origins=list((state/'runs').glob('*/enrollment.json'));assert len(origins)==1,origins
            context=read(origins[0]);before=read(context['job_file']);assert not before['accepted'] and before['status']=='paused',before
            sys.argv=['scenario','--rsi-resume',str(origins[0].parent),'--call-model'];status=runner.main()
            after=read(context['job_file']);assert before['limits']==after['limits'] and before['requests']<after['requests']<=96 and after['accepted']
        rr=records(state);assert len(rr)==1 and status==0 and rr[0]['accepted'] and rr[0]['lifecycle_verified'],{'status':status,'records':rr}
        r=rr[0];aud=[json.loads(l) for l in (Path(r['run_dir'])/'experience-audit.jsonl').read_text().splitlines()]
        if fixture:assert r['verified_motif_batches']==2 and sum(v['kind']=='operation_graph_complete' for v in aud)==2
        checkpoint=False
        if not fixture and not crash:
            from src.adapters.continuous_motif_learning import run_material
            job=state/'learning/free-certificate-checkpoint';job.mkdir(parents=True)
            child=run_material(load_config(out/'rsi.json'),job,'native-cert',r,'native_certification')
            calls=len(server.requests);cached=job/'native-cert-record.json';cached.rename(job/'pre-interruption-cache-snapshot.json')
            resumed=run_material(load_config(out/'rsi.json'),job,'native-cert',r,'native_certification')
            assert resumed==child and len(server.requests)==calls;checkpoint=True
        value={'status':'passed','fixture':fixture,'process_crash_recovered':crash,'repeated_graph_completions':sum(v['kind']=='operation_graph_complete' for v in aud),
          'verified_skips':r['verified_motif_batches'],'requests':r['upstream_requests'],'delivery_passed':True,'certification_checkpoint_no_duplicate_requests':checkpoint,
          'actual_cloud_requests':0,'mock_not_training':True,'output':str(out)}
        save(out/'outcome.json',value);print(json.dumps(value),flush=True)
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
if __name__=='__main__':run('--fixture' in sys.argv,'--crash' in sys.argv)
