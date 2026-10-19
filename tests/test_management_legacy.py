"""Free diagnostics of legacy translations and independent admission boundaries."""
import copy
from pathlib import Path
import pytest
from src.adapters.management_legacy import node,graph_nodes,validate_steps,program_actions,make_template,job_key
from src.motif_core.offline.experience_registry import read,sha


def recipe(source='task_sources'):
    return {'key':'fixture','family':'copy_program','source_prefixes':['source/'],'context_paths':[],'objective':'Copy original source files to backup/, then recover them to recovery/.',
            'guard':{'destination_prefixes':['backup/','recovery/']},
            'steps':[{'op':'copy_map','source':source,'strip_prefix':'source/','destination_slot':0},
                     {'op':'copy_map','source':'prior_targets','strip_prefix':'backup/','destination_slot':1}]}


def test_native_collection_translation_keeps_selection_and_gather_dataflow():
    n=graph_nodes('collection')
    assert [v['tool'].split('__')[-1] for v in n]==['select_files','pin_files','read_files','collect_reads']
    assert n[-1]['bindings']=={'collection_id':{'node':0,'path':'collection_id'},'source_ids':{'node':1,'path':'source_ids'}}
    assert graph_nodes('reentry')==n
    assert graph_nodes('plan')==[node('preview_actions'),node('execute_plan',plan_id=(0,'plan_id'))]
    assert all('authorize_plan' not in x['tool'] for x in graph_nodes('plan'))


@pytest.mark.parametrize('change',[lambda s:s[0].update(op='exec'),lambda s:s[0].update(strip_prefix='../'),lambda s:s[1].update(destination_slot=0),lambda s:s[0].update(source='prior_targets'),lambda s:s[0].update(extra='ignored')])
def test_program_instructions_are_closed_not_arbitrary_code(change):
    r=recipe();change(r['steps'])
    with pytest.raises(ValueError):validate_steps(r['steps'])


def test_nonempty_text_filter_and_actual_backup_bindings():
    r=recipe('nonempty_txt_sources');rows=[{'file_id':n,'path':n,'root_id':'workspace','bytes':b,'sha256':'a'*64} for n,b in [('source/empty.txt',0),('source/empty.md',0),('source/nested/a.txt',8),('outside/a.txt',8)]]
    first=program_actions(r,rows)
    assert [a['destination'] for a in first]==['backup/empty.md','backup/nested/a.txt']
    with pytest.raises(StopIteration):program_actions(r,rows,prior=[a['destination'] for a in first],stage=1)
    rows += [{'file_id':'actual-backup-'+str(i),'path':a['destination'],'root_id':'workspace','bytes':3,'sha256':'a'*64} for i,a in enumerate(first)]
    second=program_actions(r,rows,prior=[a['destination'] for a in first],stage=1)
    assert [a['file_ids'] for a in second]==[['actual-backup-0'],['actual-backup-1']]
    with pytest.raises(ValueError,match='already exists'):program_actions(r,rows)


def test_original_empty_text_extension_filter_is_case_insensitive():
    r=recipe('nonempty_txt_sources');rows=[{'file_id':n,'path':n,'root_id':'workspace','bytes':0,'sha256':'a'*64} for n in ['source/EMPTY.TXT','source/empty.md']]
    assert [a['destination'] for a in program_actions(r,rows)]==['backup/empty.md']


@pytest.mark.parametrize('order,expected',[('min','source/a.txt'),('max','source/z.txt')])
def test_hash_representative_requires_complete_actual_groups(order,expected):
    r=recipe();r['steps']=[{'op':'hash_representatives','order':order},{'op':'copy_map','source':'hash_representatives','strip_prefix':'','destination_slot':0}]
    rows=[{'file_id':n,'path':n,'root_id':'workspace','bytes':2,'sha256':'a'*64} for n in ['source/z.txt','source/a.txt']]
    groups=[{'sha256':'a'*64,'files':[{'file_id':n['file_id'],'path':'workspace/'+n['path']} for n in rows]}]
    assert program_actions(r,rows,groups)[0]['file_ids']==[expected]
    groups[0]['files'].pop()
    with pytest.raises(ValueError,match='incomplete'):program_actions(r,rows,groups)


def test_new_material_template_is_immutable_and_keeps_original_goals(tmp_path):
    r=recipe();cfg={'state_root':str(tmp_path)};job=tmp_path/'new-job'
    t=make_template(cfg,r,job);spec=read(t/'task.json');original=sha(t/'task.json')
    assert spec['quality']['goal']['state']=='frozen' and spec['objective']==r['objective']
    assert not spec.get('external_roots') and not (t/'approvals').exists()
    assert make_template(cfg,r,job)==t and sha(t/'task.json')==original
    (t/'pristine/source/a.txt').write_text('modified after freeze')
    with pytest.raises(ValueError,match='template changed'):make_template(cfg,r,job)


def test_legacy_job_identity_cannot_retry_by_changing_material_nonce():
    p=recipe();same=job_key(p,'runtime')
    assert same==job_key(p,'runtime')
    assert same!=job_key(p,'new-runtime') and same!=job_key(p,'runtime','new-sealed-ordinary-evidence')


def test_known_rejection_needs_new_clean_sealed_ordinary_evidence(tmp_path,monkeypatch):
    import os
    from src.adapters import management_legacy as legacy,continuous_rsi as rsi,continuous_motif_learning as learning
    from src.motif_core.offline.experience_registry import durable,digest
    cfg={'state_root':str(tmp_path)};p=recipe();base=tmp_path/'experience/jobs'/job_key(p,'current-runtime')
    durable(base/'failure.json',{'reason':'original native proof rejected'})
    monkeypatch.setattr(rsi,'source_map',lambda:{})
    monkeypatch.setattr(rsi,'records',lambda root:[])
    assert legacy.opportunity(cfg,p,'current-runtime')==(None,{})
    record={'role':'ordinary','source_sha256':digest({}),'session_id':'fresh','task_fingerprint':'new-original-material','origin':'unchanged-original-origin'}
    file=tmp_path/'records/fresh.json';durable(file,record)
    old=base/'failure.json';os.utime(old,ns=(1,1))
    monkeypatch.setattr(rsi,'records',lambda root:[record])
    monkeypatch.setattr(learning,'frame',lambda r:{'spec':{'quality':{'goal':{'state':'frozen'}}}})
    checked=[];monkeypatch.setattr(legacy,'native_program_proof',lambda proposal,f:checked.append(proposal['key']))
    job,seed=legacy.opportunity(cfg,p,'current-runtime')
    assert job!=base and seed['seed_record_sha256']==sha(file) and checked==['fixture']
    durable(job/'failure.json',{'reason':'same fresh evidence also rejected'})
    assert legacy.opportunity(cfg,p,'current-runtime')==(None,{})


def test_new_program_admission_requires_current_independent_certificate(tmp_path):
    from src.motif_core.offline.experience_registry import ExperienceRegistry
    with pytest.raises(ValueError,match='independent actual certification'):
        ExperienceRegistry(tmp_path).entry('management_program',tmp_path/'not-an-authority.json',{})


def test_certification_cannot_start_outside_original_worker_lock(tmp_path):
    from src.adapters.management_legacy import certify_proposal
    with pytest.raises(ValueError,match='original worker lock'):
        certify_proposal({'state_root':str(tmp_path)},recipe(),tmp_path/'job')


def _native_program_fixture():
    from src.adapters.management_legacy import PREFIX
    from src.motif_core.offline.experience_registry import digest
    r=recipe();r['guard']['objective_sha256']=digest(r['objective'])
    originals=[{'file_id':'id-'+n,'path':'source/'+n,'root_id':'workspace','sha256':digest(n),'bytes':5} for n in ('a.txt','b.md')]
    backups=[{**v,'file_id':'backup-'+str(i),'path':'backup/'+v['path'].split('/',1)[1]} for i,v in enumerate(originals)]
    rows=[]
    def listing(seq,files):rows.append({'name':PREFIX+'list_files','call_id':'list-'+str(seq),'call_seq':seq,'result_seq':seq+1,'generated':False,'out':{'files':files}})
    def plan(seq,sources,prefix):
        pid='plan-'+str(seq);actions=[{'op':'copy','source_root':'workspace','source':v['path'],'source_sha256':v['sha256'],'destination_root':'workspace','destination':prefix+v['path'].split('/',1)[1]} for v in sources]
        rows.extend([{'name':PREFIX+'preview_actions','call_id':pid,'call_seq':seq,'result_seq':seq+1,'generated':False,'out':{'plan_id':pid,'actions':actions,'risks':[]}},
                     {'name':PREFIX+'execute_plan','call_id':'execute-'+pid,'call_seq':seq+2,'result_seq':seq+3,'generated':False,'out':{'plan_id':pid,'_sss_authorized':True}}])
    listing(1,originals);plan(3,originals[:1],'backup/');plan(7,originals[1:],'backup/');listing(11,originals+backups);plan(13,backups,'recovery/')
    f={'spec':{'objective':r['objective']},'rows':rows}
    return r,f


def test_native_program_proof_allows_batching_changes_but_requires_real_backup_provenance():
    from src.adapters.management_legacy import native_program_proof
    r,f=_native_program_fixture();proof=native_program_proof(r,f)
    assert len(proof)==2 and len(proof[0]['native_plans'])==2 and len(proof[1]['native_plans'])==1
    changed=copy.deepcopy(f);changed['rows'][-2]['out']['actions'][0]['source']='source/a.txt'
    with pytest.raises(ValueError,match='proposed copy stage'):native_program_proof(r,changed)


def test_failed_native_preview_is_a_rejection_barrier_not_a_worker_crash():
    from src.adapters.management_legacy import native_program_proof,PREFIX
    r,f=_native_program_fixture()
    f['rows'].insert(1,{'name':PREFIX+'preview_actions','call_id':'failed-preview','call_seq':2,'result_seq':None,'generated':False,'out':None})
    with pytest.raises(ValueError,match='failed native preview'):
        native_program_proof(r,f)


@pytest.mark.parametrize('batch',[False,True])
def test_rule_proof_accepts_actual_full_scalar_and_batch_reads_but_rejects_late_or_partial(batch):
    from src.adapters.management_legacy import native_program_proof,PREFIX
    from src.motif_core.offline.experience_registry import digest
    r,f=_native_program_fixture();r['context_paths']=['rules/notice.txt'];r['guard']['context_text_sha256']=digest('Original complete rule')
    for row in f['rows']:row['call_seq']*=10;row['result_seq']*=10
    readback={'path':'workspace/rules/notice.txt','text':'Original complete rule','status':'readable','truncated':False}
    row={'name':PREFIX+('read_files' if batch else 'read_file'),'generated':False,'call_id':'actual-rule','call_seq':21,'result_seq':22,'out':{'reads':[readback]} if batch else readback}
    f['rows'].append(row)
    assert native_program_proof(r,f)
    readback['truncated']=True
    with pytest.raises(ValueError,match='native rule read'):native_program_proof(r,f)
    readback['truncated']=False;row['result_seq']=1000
    with pytest.raises(ValueError,match='native rule read'):native_program_proof(r,f)


def test_native_preparation_only_allows_necessary_parent_directories():
    from src.adapters.management_legacy import native_program_proof
    r,f=_native_program_fixture();first=next(v for v in f['rows'] if v['name'].endswith('__preview_actions'))
    first['out']['actions'].insert(0,{'op':'mkdir','destination':'backup','source_root':'workspace','destination_root':'workspace'})
    assert native_program_proof(r,f)
    first['out']['actions'][0]['destination']='unrelated-folder'
    with pytest.raises(ValueError,match='directory'):native_program_proof(r,f)


@pytest.mark.parametrize('defect',['holdout_role','outside_archive'])
def test_script_guard_bindings_do_not_follow_mislabeled_final_or_external_records(tmp_path,monkeypatch,defect):
    from src.adapters import continuous_rsi as rsi
    from src.adapters.management_legacy import script_bindings
    from src.motif_core.offline.experience_registry import durable,digest
    root=tmp_path/'project';root.mkdir();monkeypatch.setattr(rsi,'ROOT',root)
    train=(root/'.local/file-management/train') if defect=='holdout_role' else tmp_path/'external'
    goal='Copy originals to backup/ then recover to recovery/'
    durable(train/'input-template.json',{'objective':goal,'workflow_contract':{'source_paths':['source/a.txt'],'context_paths':[],'destination_prefixes':['backup/','recovery/']}})
    outcome=train/'attempts/run/outcome.json';durable(outcome,{'role':'holdout' if defect=='holdout_role' else 'explore'})
    p={'steps':recipe()['steps'],'guard_cases':[{'objective_sha256':digest(goal),'context_text_sha256':None,'destination_prefixes':['backup/','recovery/']}],
       'training':[{'role':'explore','outcome_file':str(outcome),'outcome_sha256':sha(outcome)}]}
    with pytest.raises(ValueError):script_bindings(p)


def test_existing_pending_legacy_admission_wins_over_new_version_or_seed(tmp_path,monkeypatch):
    from src.adapters.management_legacy import opportunity,FORMAT
    from src.adapters import continuous_rsi as rsi
    from src.motif_core.offline.experience_registry import durable
    p=recipe();job=tmp_path/'experience/jobs/original-frozen'
    durable(job/'request.json',{'adapter_format':FORMAT,'key':p['key'],'target':'old-runtime','seed':'old-sealed-task','seed_origin':'old-origin'})
    monkeypatch.setattr(rsi,'records',lambda root:pytest.fail('pending request replaced by new task discovery'))
    selected,seed=opportunity({'state_root':str(tmp_path)},p,'new-runtime')
    assert selected==job and seed=={'seed':'old-sealed-task','seed_origin':'old-origin'}
    assert len(list((tmp_path/'experience/jobs').iterdir()))==1


def test_exact_program_delivery_rejects_extra_duplicate_even_after_expected_output_exists(tmp_path):
    import shutil
    from src.adapters.management_legacy import program_output_contract,verify_program_delivery
    from src.motif_core.offline.experience_registry import durable
    p=recipe();template=make_template({'state_root':str(tmp_path)},p,tmp_path/'prototype');spec=read(template/'task.json')
    origin=tmp_path/'runs/session';shutil.copytree(template/'pristine',origin/'pristine');shutil.copytree(template/'pristine',origin/'final-workspace');durable(origin/'task.json',spec)
    rows=[{'path':n,'root_id':'workspace','file_id':n,'sha256':h,'bytes':(origin/'pristine'/n).stat().st_size} for n,h in spec['initial_tree']['workspace']['files'].items() if n!='.experiment-copy']
    for requirement in program_output_contract(p,rows)['requirements']:
        if requirement['kind']=='file':
            target=origin/'final-workspace'/requirement['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin/'pristine'/requirement['source'],target)
    record={'session_id':'session','origin':str(origin),'task_sha256':sha(origin/'task.json')};durable(tmp_path/'records/session.json',record)
    assert verify_program_delivery(p,record)['expected_snapshot_sha256']==verify_program_delivery(p,record)['actual_snapshot_sha256']
    shutil.copyfile(origin/'pristine/source/a.txt',origin/'final-workspace/extra-duplicate.txt')
    with pytest.raises(ValueError,match='extra duplicates'):verify_program_delivery(p,record)


def test_frozen_program_acceptance_excludes_wrong_representatives_and_empty_text_targets():
    from src.adapters.management_legacy import program_output_contract
    r=recipe('nonempty_txt_sources');rows=[{'path':n,'root_id':'workspace','file_id':n,'sha256':'a'*64,'bytes':0} for n in ['source/EMPTY.TXT','source/empty.md']]
    rules=program_output_contract(r,rows)['requirements']
    assert {'kind':'missing','path':'backup/EMPTY.TXT'} in rules and {'kind':'missing','path':'recovery/EMPTY.TXT'} in rules
    r['steps']=[{'op':'hash_representatives','order':'min'},{'op':'copy_map','source':'hash_representatives','strip_prefix':'','destination_slot':0}]
    rules=program_output_contract(r,rows)['requirements']
    assert len([q for q in rules if q['kind']=='file'])==1 and len([q for q in rules if q['kind']=='missing'])==1


def test_legacy_certification_target_versions_the_offline_checker_without_changing_execution_contract(monkeypatch):
    from src.adapters import management_legacy as legacy,experience_library as library
    monkeypatch.setattr(library,'target_version',lambda runtime:'same-runtime-and-schema')
    monkeypatch.setattr(legacy,'sha',lambda file:'first-checker-version')
    before=legacy.certification_target({})
    monkeypatch.setattr(legacy,'sha',lambda file:'second-checker-version')
    assert before!=legacy.certification_target({}) and library.target_version({})=='same-runtime-and-schema'
