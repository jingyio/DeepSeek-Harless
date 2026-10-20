"""Persistent task/learning bounds and independent Motif admission."""
import json,os
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.adapters import continuous_rsi as rsi
from src.motif_core.offline.experience_registry import digest,sha,durable,check_motif_certificate

@pytest.fixture
def configuration(tmp_path,monkeypatch):
    monkeypatch.setattr(rsi,'ROOT',tmp_path);monkeypatch.setattr(rsi,'STATE_HOME',tmp_path/'.local/rsi')
    monkeypatch.setattr(rsi,'DATA',tmp_path/'testpdf/file-management-experiment')
    workspace=rsi.DATA/'fresh';workspace.mkdir(parents=True);(workspace/'.experiment-copy').write_text('new authorized copy')
    path=tmp_path/'.local/config.json';path.parent.mkdir(exist_ok=True)
    config={'schema_version':1,'format':rsi.FORMAT,'state_root':str(rsi.STATE_HOME/'agent'),
      'workspace_roots':[str(workspace)],'mode':'learn','provider_mode':'real','series_cap_usd':1000,
      'learning_cap_usd':10,'auto_worker':True,'allow_material_copy':True,
      'limits':{'budget_usd':5,'max_steps':96,'max_output':4000,'max_repairs':2}}
    durable(path,config);monkeypatch.setattr(rsi,'series_accounting',lambda:{'estimated_usd':7})
    return path,config

@pytest.mark.parametrize('damage',['budget','steps','repairs','mock','root','ordinary_candidate'])
def test_configuration_cannot_expand_original_grants(configuration,damage):
    path,c=configuration
    if damage=='budget':c['limits']['budget_usd']=6
    if damage=='steps':c['limits']['max_steps']=97
    if damage=='repairs':c['limits']['max_repairs']=3
    if damage=='mock':c['provider_mode']='mock'
    if damage=='root':c['workspace_roots']=[str(Path(c['workspace_roots'][0]).parent)]
    if damage=='ordinary_candidate':c['registry_file']='arbitrary-template.json'
    durable(path,c)
    with pytest.raises(ValueError):rsi.load_config(path)

def test_unsettled_and_restarted_learning_never_resets_reservation(configuration):
    path,c=configuration;c.update(role='native_certification',auto_worker=False)
    durable(path,c);cfg=rsi.load_config(path);root=rsi.initialize(cfg)
    rsi.reserve(cfg,'one',5);rsi.reserve(cfg,'two',5)
    with pytest.raises(ValueError,match='learning budget'):rsi.reserve(cfg,'third',5)
    with pytest.raises(ValueError,match='already exists'):rsi.reserve(cfg,'one',5)
    assert sum(r['cap_usd'] for r in rsi.read(root/'pool.json')['runs'].values())==10
    rsi.initialize(cfg);assert len(rsi.read(root/'pool.json')['runs'])==2

def test_series_budget_accounts_for_pending_tasks(configuration):
    path,c=configuration;c['series_cap_usd']=12;c['learning_cap_usd']=5;durable(path,c)
    cfg=rsi.load_config(path);rsi.initialize(cfg);rsi.reserve(cfg,'one',5)
    with pytest.raises(ValueError,match='series budget'):rsi.reserve(cfg,'two',5)


def test_uncapped_file_policy_preserves_prior_reservations_without_inventing_zero(configuration,monkeypatch):
    path,c=configuration
    cfg=rsi.load_config(path);root=rsi.initialize(cfg);rsi.reserve(cfg,'old-bounded',5)
    c.update(series_cap_usd=None,learning_cap_usd=None)
    c['limits']={k:None for k in c['limits']};durable(path,c);cfg=rsi.load_config(path)
    monkeypatch.setattr(rsi,'series_accounting',lambda:(_ for _ in ()).throw(AssertionError('no monetary quota to enforce')))
    for i in range(4):rsi.reserve(cfg,'unlimited-'+str(i),None)
    pool=rsi.read(root/'pool.json')['runs']
    assert pool['old-bounded']['cap_usd']==5
    assert len(pool)==5 and pool['unlimited-3']['cap_usd'] is None
    with pytest.raises(ValueError,match='already exists'):rsi.reserve(cfg,'unlimited-3',None)
    c.update(series_cap_usd=1000,learning_cap_usd=10);durable(path,c)
    monkeypatch.setattr(rsi,'series_accounting',lambda:{'estimated_usd':7})
    with pytest.raises(ValueError,match='series budget'):rsi.reserve(rsi.load_config(path),'cannot-hide-unbounded-reservation',1)

def test_cold_import_learning_spend_and_reservation_keep_original_cap(configuration,monkeypatch):
    path,c=configuration;c.update(role='native_certification',auto_worker=False)
    durable(path,c);cfg=rsi.load_config(path);root=rsi.initialize(cfg)
    from src.adapters import management_backup
    monkeypatch.setattr(management_backup,'imported_budget',lambda project:{'learning_spent_usd':4,'learning_reserved_usd':2})
    with pytest.raises(ValueError,match='learning budget'):rsi.reserve(cfg,'too-large',5)
    assert not rsi.read(root/'pool.json')['runs']
    rsi.reserve(cfg,'within-original',4)
    with pytest.raises(ValueError,match='learning budget'):rsi.reserve(cfg,'next',.01)

def test_lock_recovery_preserves_old_owner_and_budget(configuration):
    path,_=configuration;cfg=rsi.load_config(path);root=rsi.initialize(cfg);rsi.reserve(cfg,'pending',5)
    durable(root/'worker.lock',{'pid':999999999,'created':0})
    with rsi.writer_lock(root,'worker'):
        assert list((root/'stale-locks').glob('worker-*.json'))
        with pytest.raises(RuntimeError,match='active'):
            with rsi.writer_lock(root,'worker'):pass
    assert rsi.read(root/'pool.json')['runs']['pending']['status']=='reserved'

def certificate(tmp_path):
    policy={'policy_digest':'c'*64,'artifact':{'source_task_fingerprints':['a'*64,'b'*64]}}
    lock=tmp_path/'lock.json';durable(lock,{'frozen':True});reviews=[]
    for i,role in enumerate(('native_certification','candidate_certification','candidate_certification')):
        record={'role':role,'accepted':True,'lifecycle_verified':True,'provider_mode':'real','metrics':{'acceptance_repairs':0},
                'policy_digest':policy['policy_digest'],'verified_motif_batches':3,'deferred':[]}
        file=tmp_path/f'record-{i}.json';durable(file,record)
        reviews.append({'role':role,'task_fingerprint':str(i+3)*64,'record_file':str(file),'record_sha256':sha(file)})
    cert={'status':'certified_motif_v1','holdout_used':False,'policy_digest':policy['policy_digest'],'payload_sha256':'d'*64,
          'quality_and_permission_required':True,'candidate_lock_file':str(lock),'candidate_lock_sha256':sha(lock),
          'native_review':reviews[0],'reviews':reviews[1:]}
    path=tmp_path/'certificate.json';durable(path,cert);return policy,path,cert

@pytest.mark.parametrize('damage',['overlap','mutated','failed','no_actual_use','unknown_usage'])
def test_motif_activation_requires_independent_actual_candidate_use(tmp_path,damage):
    policy,path,cert=certificate(tmp_path);assert check_motif_certificate(policy,path,'d'*64)
    review=cert['reviews'][0]
    if damage=='overlap':review['task_fingerprint']='a'*64
    elif damage=='mutated':Path(review['record_file']).write_text('{}')
    else:
        record=rsi.read(review['record_file'])
        if damage=='failed':record['accepted']=False
        elif damage=='unknown_usage':record['observed_usage_complete']=False
        else:record['verified_motif_batches']=0
        durable(review['record_file'],record);review['record_sha256']=sha(review['record_file'])
    durable(path,cert)
    with pytest.raises(ValueError):check_motif_certificate(policy,path,'d'*64)

def test_failed_http_preserves_original_cost_upper_and_unknown_usage(tmp_path):
    ledger=tmp_path/'ledger.jsonl'
    ledger.write_text('\n'.join(json.dumps(r) for r in [
        {'observed_peak_usd':.001,'reserved_upper_usd':.02},
        {'observed_peak_usd':None,'reserved_upper_usd':.02,'status':503},
        {'kind':'budget_denied','reserved_upper_usd':5}]))
    review=rsi.ledger_accounting(ledger,{'upstream_requests':2,'budget_accounted_usd':.021})
    assert review['accounting_complete'] and not review['observed_usage_complete']
    assert review['missing_observed_usage_requests']==1
    assert review['cost_upper_usd']==.021
    assert not rsi.ledger_accounting(ledger,{'upstream_requests':1,'budget_accounted_usd':.021})['accounting_complete']

def test_new_evidence_can_relearn_disabled_graph_without_repeating_active_or_failed_job(tmp_path):
    from src.adapters.continuous_motif_learning import learning_job
    candidate={'key':'opportunity','compiled':{'witnesses':['first','second']}}
    original=learning_job(tmp_path,candidate,set());durable(original/'compiled.json',candidate['compiled'])
    durable(original/'failure.json',{'immutable_rejection':True})
    assert learning_job(tmp_path,candidate,set())==original
    revised={**candidate,'compiled':{'witnesses':['first','second','new-independent-decision']}}
    assert learning_job(tmp_path,revised,set())!=original
    durable(original/'activation.json',{'opportunity_key':candidate['key'],'policy_digest':'active-policy'})
    assert learning_job(tmp_path,revised,{'active-policy'}) is None
    assert learning_job(tmp_path,revised,set())!=original
    assert rsi.read(original/'failure.json')=={'immutable_rejection':True}

def test_busy_worker_catches_up_sealed_notifications(configuration,monkeypatch):
    from src.adapters import continuous_motif_learning as learner
    path,_=configuration;cfg=rsi.load_config(path);rsi.initialize(cfg)
    sealed=[{'session_id':'first','role':'ordinary'}];calls=[]
    monkeypatch.setattr(learner,'records',lambda root:list(sealed))
    def drain_once(cfg,root):
        calls.append(len(sealed))
        if len(calls)==1:sealed.append({'session_id':'arrived-while-busy','role':'ordinary'})
        return {'records':len(sealed)}
    monkeypatch.setattr(learner,'_drain_locked',drain_once)
    assert learner.drain(path)=={'records':2}
    assert calls==[1,2]
    assert not (Path(cfg['state_root'])/'worker.lock').exists()

def test_unsettled_record_is_hidden_until_the_cost_and_queue_seal(configuration):
    path,_=configuration;root=rsi.initialize(rsi.load_config(path));file=root/'records/partial.json'
    durable(file,{'session_id':'partial','role':'ordinary'})
    assert rsi.records(root)==[]
    durable(root/'queue/partial.json',{'record_sha256':sha(file),'sealed_after_cost_and_acceptance':True})
    assert [r['session_id'] for r in rsi.records(root)]==['partial']
    durable(file,{'session_id':'mutated'})
    with pytest.raises(ValueError,match='mutated'):rsi.records(root)

def test_series_admission_waits_for_short_accounting_writer(tmp_path):
    import threading,time
    from src.adapters.continuous_rsi import writer_lock
    ready=threading.Event()
    def accounting():
        with writer_lock(tmp_path,'series'):ready.set();time.sleep(.15)
    t=threading.Thread(target=accounting);t.start();ready.wait(2)
    with writer_lock(tmp_path,'series'):assert (tmp_path/'series.lock').exists()
    t.join();assert not (tmp_path/'series.lock').exists()
    with writer_lock(tmp_path,'worker'):
        with pytest.raises(RuntimeError,match='writer is active'):
            with writer_lock(tmp_path,'worker'):pass

def test_liveness_never_signals_the_current_process(monkeypatch):
    import os
    from src.adapters.process_state import process_exists
    monkeypatch.setattr(os,'kill',lambda *args:(_ for _ in ()).throw(AssertionError('must not signal self')))
    assert process_exists(os.getpid())
    assert not process_exists(-1)


@pytest.mark.parametrize('name',['management-profile','state'])
def test_file_metadata_admission_waits_for_short_live_writer(tmp_path,name):
    import threading,time
    ready=threading.Event()
    def writer():
        with rsi.writer_lock(tmp_path,name):ready.set();time.sleep(.15)
    thread=threading.Thread(target=writer);thread.start()
    try:
        assert ready.wait(2)
        with rsi.writer_lock(tmp_path,name):assert (tmp_path/(name+'.lock')).exists()
    finally:thread.join()
    assert not (tmp_path/(name+'.lock')).exists()


def test_parallel_file_initialization_keeps_seed_registry_a_single_writer(configuration,monkeypatch):
    import threading,time
    from concurrent.futures import ThreadPoolExecutor
    from src.adapters import experience_library as library,management_seed
    path,_=configuration;cfg=rsi.load_config(path)
    barrier=threading.Barrier(5);mutex=threading.Lock();active=0;peak=0;visits=[]
    monkeypatch.setattr(library,'enabled',lambda unused:True)
    monkeypatch.setattr(library,'synchronize',lambda unused:None)
    def install(unused):
        nonlocal active,peak
        with mutex:active+=1;peak=max(peak,active)
        time.sleep(.03)
        with mutex:active-=1;visits.append(True)
    monkeypatch.setattr(management_seed,'install',install)
    def initialize():barrier.wait(2);return rsi.initialize(cfg)
    with ThreadPoolExecutor(max_workers=5) as executor:
        assert list(executor.map(lambda unused:initialize(),range(5)))==[Path(cfg['state_root'])]*5
    assert len(visits)==5 and peak==1
    assert rsi.read(Path(cfg['state_root'])/'pool.json')=={'runs':{}}


@pytest.mark.parametrize('name',['management-profile','state'])
def test_busy_file_metadata_lock_times_out_without_removing_live_owner(tmp_path,monkeypatch,name):
    lock=tmp_path/(name+'.lock');durable(lock,{'pid':os.getpid(),'created':1})
    clock=iter([0,31]);monkeypatch.setattr(rsi.time,'monotonic',lambda:next(clock))
    with pytest.raises(RuntimeError,match=name+' writer is active'):
        with rsi.writer_lock(tmp_path,name):pytest.fail('must not acquire a live writer')
    assert rsi.read(lock)=={'pid':os.getpid(),'created':1}
