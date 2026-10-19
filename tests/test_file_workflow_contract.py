"""Independent acceptance rejects wrong bytes, archive members and silently widened scopes."""
import importlib.util,json,sys,zipfile
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parents[1]/'scenarios/file-management'

@pytest.fixture
def factory(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(HERE));mods={}
    for name in ('common','file_tools','collection_tools','report_tools','task_contract','workflow_contract','workflow_delivery','workflow_tools'):
        s=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));m=importlib.util.module_from_spec(s);monkeypatch.setitem(sys.modules,name,m);s.loader.exec_module(m);mods[name]=m
    monkeypatch.setattr(mods['file_tools'],'ROOT',tmp_path);monkeypatch.setattr(mods['file_tools'],'DATA',tmp_path/'data');monkeypatch.setattr(mods['workflow_contract'],'ROOT',tmp_path)
    def make(wid='FM05',ops=None,duplicate=False,empty=False):
        root=tmp_path/'data/copy';root.mkdir(parents=True);(root/'.experiment-copy').write_text('test')
        for n,v in [('source/a.txt','first'),('source/b.txt','second'),('keep.txt','unchanged')]:
            p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v)
        if duplicate:(root/'source/b.txt').write_text('first')
        if empty:(root/'source/b.txt').write_text('')
        out=tmp_path/'.local/delivery';oracle=tmp_path/'.local/oracle.json';oracle.parent.mkdir()
        initial=mods['common'].snapshot(root);expected={**initial,'merged/a.txt':initial['source/a.txt'],'merged/b.txt':initial['source/b.txt']}
        payload={'expected_snapshot':expected,'mapping':{'source/a.txt':'merged/a.txt','source/b.txt':'merged/b.txt'},'require_effects':True}
        mods['common'].save(oracle,payload)
        spec={'task_id':'test','family':'workflow','objective':'copy','rules':{},'workspace':str(root),'initial_snapshot':initial,'allowed_operations':ops or ['copy'],
              'report_contract':{'version':'sss-file-report-v3','kind':'task_result'},'workflow_contract':{'version':'sss-file-workflow-v1','workflow_id':wid,
                'source_paths':['source/a.txt','source/b.txt'],'destination_prefixes':['merged/'],'allowed_reads':['source/a.txt'],'required_reads':[],'context_paths':[]},
              'workflow_oracle_file':str(oracle),'workflow_oracle_sha256':mods['common'].sha(oracle)}
        scene=mods['workflow_tools'].WorkflowScene(spec,out);scene.read_task();return scene,mods,payload,oracle
    return make

def complete(scene):
    ids={r['path']:r['file_id'] for r in scene.list_files()['files']}
    p=scene.preview_actions([{'op':'copy','file_ids':[ids[n]],'destination':'merged/'+Path(n).name} for n in ('source/a.txt','source/b.txt')]);scene.execute_plan(p['plan_id'])
    scene.submit_report('actual result',list(scene.files()),[],'task_result')
    return json.loads((scene.output/'report.json').read_text())

def test_acceptance_reads_actual_bytes_and_unselected_files(factory):
    s,m,_,_=factory();report=complete(s);verify=m['workflow_contract'].verify_workflow
    assert verify(s.spec,report,s.output)['passed']
    (s.root/'merged/a.txt').write_text('wrong bytes');assert not verify(s.spec,report,s.output)['passed']

def test_private_oracle_and_report_identity_cannot_be_substituted(factory):
    s,m,p,oracle=factory();report=complete(s);report['file_ids']=[]
    assert not m['workflow_contract'].verify_workflow(s.spec,report,s.output)['passed']
    report=json.loads((s.output/'report.json').read_text());report['workflow_execution_version_sha256']='0'*64
    assert 'workflow execution version differs' in m['workflow_contract'].verify_workflow(s.spec,report,s.output)['errors']
    m['common'].save(oracle,{**p,'require_effects':False})
    with pytest.raises(ValueError,match='oracle changed'):m['workflow_contract'].verify_workflow(s.spec,report,s.output)

def test_read_scope_rejects_before_observation(factory):
    s,m,_,_=factory();fid=next(r['file_id'] for r in s.list_files()['files'] if r['path']=='keep.txt')
    with pytest.raises(m['file_tools'].ToolError,match='outside workflow'):s.pin_file(fid)
    assert not s.handles

def test_zip_extra_member_fails_despite_successful_crc(factory):
    s,m,p,oracle=factory(wid='FM21');zip_name='merged/package.zip';p['expected_snapshot']=s.spec['initial_snapshot'];p.update(zip_path=zip_name,zip_members={'source/a.txt':s.spec['initial_snapshot']['source/a.txt']},require_effects=False)
    m['common'].save(oracle,p);s.spec['workflow_oracle_sha256']=m['common'].sha(oracle)
    dest=s.root/zip_name;dest.parent.mkdir()
    with zipfile.ZipFile(dest,'w') as z:z.write(s.root/'source/a.txt','source/a.txt');z.write(s.root/'keep.txt','keep.txt')
    s.expected=m['common'].snapshot(s.root);s.input_digest=m['common'].digest(s.spec);s.submit_report('archive',list(s.files()),[],'task_result')
    report=json.loads((s.output/'report.json').read_text());result=m['workflow_contract'].verify_workflow(s.spec,report,s.output)
    assert not result['passed'] and 'ZIP membership differs' in result['errors']

def copy_action(scene, source, target):
    return {'op':'copy','file_ids':[scene.file_id(source)],'destination':target}

def test_merge_rejects_equal_bytes_in_one_plan_before_any_effect(factory):
    s,m,_,_=factory(duplicate=True);before=dict(s.expected)
    with pytest.raises(m['file_tools'].ToolError,match='duplicate SHA group'):
        s.preview_actions([copy_action(s,'source/a.txt','merged/a.txt'),copy_action(s,'source/b.txt','merged/b.txt')])
    assert m['common'].snapshot(s.root)==before and not s.plans and not list((s.output/'journals').glob('*'))

def test_merge_uniqueness_spans_plans_and_restoration_releases_output(factory):
    s,m,_,_=factory(duplicate=True)
    plan=s.preview_actions([copy_action(s,'source/a.txt','merged/a.txt')]);receipt=s.execute_plan(plan['plan_id'])
    assert s.execute_plan(plan['plan_id'])==receipt
    with pytest.raises(m['file_tools'].ToolError,match='duplicate SHA group'):
        s.preview_actions([copy_action(s,'source/b.txt','merged/b.txt')])
    assert not (s.root/'merged/b.txt').exists()
    s.restore_plan(plan['plan_id'])
    replacement=s.preview_actions([copy_action(s,'source/b.txt','merged/b.txt')]);s.execute_plan(replacement['plan_id'])
    assert (s.root/'merged/b.txt').read_text()=='first' and not (s.root/'merged/a.txt').exists()

def test_merge_execution_rechecks_plan_without_allocating_backups(factory):
    s,m,_,_=factory(duplicate=True)
    plan=s.preview_actions([copy_action(s,'source/a.txt','merged/a.txt')])
    s.plans[plan['plan_id']]['actions'].append({**copy_action(s,'source/b.txt','merged/b.txt'),'format':'none'})
    with pytest.raises(m['file_tools'].ToolError,match='duplicate SHA group'):
        s.execute_plan(plan['plan_id'])
    assert not (s.output/'backups').exists() and not (s.output/'journals').exists()

def test_merge_guard_does_not_choose_representative_or_read_oracle(factory,monkeypatch):
    s,m,_,oracle=factory(duplicate=True)
    old=Path.read_text
    def checked(path,*args,**kwargs):
        if path==oracle:raise AssertionError('effect guard must not read acceptance answers')
        return old(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',checked)
    plan=s.preview_actions([copy_action(s,'source/b.txt','merged/b.txt')]);s.execute_plan(plan['plan_id'])
    assert (s.root/'merged/b.txt').read_text()=='first'

def test_merge_keeps_different_bytes_with_same_basename(factory):
    s,m,_,_=factory()
    plan=s.preview_actions([copy_action(s,'source/a.txt','merged/one/data.txt'),copy_action(s,'source/b.txt','merged/two/data.txt')])
    s.execute_plan(plan['plan_id'])
    assert (s.root/'merged/one/data.txt').read_text()!='second' and (s.root/'merged/two/data.txt').read_text()=='second'

def test_backup_allows_equal_bytes_in_different_originals(factory):
    s,m,_,_=factory(wid='FM17',duplicate=True)
    s.workflow=m['workflow_contract'].WorkflowContract.model_validate({**s.workflow.model_dump(),'destination_prefixes':['backup-set/','recovery-drill/']})
    plan=s.preview_actions([copy_action(s,'source/a.txt','backup-set/a.txt'),copy_action(s,'source/b.txt','backup-set/b.txt')])
    s.execute_plan(plan['plan_id'])
    assert (s.root/'backup-set/a.txt').read_bytes()==(s.root/'backup-set/b.txt').read_bytes()

def test_merge_submission_requires_missing_group_even_if_empty(factory):
    s,m,_,_=factory(empty=True)
    plan=s.preview_actions([copy_action(s,'source/a.txt','merged/a.txt')]);s.execute_plan(plan['plan_id'])
    with pytest.raises(m['file_tools'].ToolError,match='missing original SHA groups') as error:
        s.submit_report('done',list(s.files()),[],'task_result')
    assert 'source/b.txt' in str(error.value) and not (s.output/'report.json').exists()
    plan=s.preview_actions([copy_action(s,'source/b.txt','merged/b.txt')]);s.execute_plan(plan['plan_id'])
    s.submit_report('all actual groups',list(s.files()),[],'task_result')
    assert (s.root/'merged/b.txt').read_bytes()==b''

def test_merge_submission_does_not_require_each_duplicate_original(factory):
    s,m,_,_=factory(duplicate=True)
    plan=s.preview_actions([copy_action(s,'source/b.txt','merged/b.txt')]);s.execute_plan(plan['plan_id'])
    s.submit_report('one actual group',list(s.files()),[],'task_result')
    assert (s.output/'report.json').exists()

@pytest.mark.parametrize('hint', [[], ['file:local:obsolete'] * 2])
def test_task_result_structure_comes_from_current_mcp_state(factory, hint, monkeypatch):
    s,m,_,oracle=factory();complete(s)
    old=Path.read_text
    def checked(path,*args,**kwargs):
        if path==oracle:raise AssertionError('report serializer must not read acceptance answers')
        return old(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',checked)
    receipt=s.submit_report('model summary',hint,['model gap'],'task_result')
    report=json.loads((s.output/'report.json').read_text());p=report['structural_provenance']
    assert report['file_ids']==sorted(s.files()) and report['final_snapshot']==s.expected
    assert report['receipts']==list(s.receipts.values()) and report['summary']=='model summary' and report['gaps']==['model gap']
    assert receipt['artifact_sha256']==m['common'].digest(report)
    assert p['generator']=='current_mcp_state' and p['snapshot_sha256']==m['common'].digest(s.expected)
    assert p['receipts_sha256']==m['common'].digest(report['receipts']) and p['legacy_hint']['count']==len(hint)
    assert p['legacy_hint']['missing_count']==len(s.files())

def test_report_serializer_does_not_certify_missing_effects(factory):
    s,m,_,_=factory(wid='FM13')
    s.submit_report('semantic assertion of completion',[],[],'task_result')
    report=json.loads((s.output/'report.json').read_text())
    result=m['workflow_contract'].verify_workflow(s.spec,report,s.output)
    assert not result['passed'] and report['receipts']==[]

def test_report_serializer_retains_kind_summary_and_external_state_guards(factory):
    s,m,_,_=factory();complete(s)
    previous=(s.output/'report.json').read_bytes()
    for summary,kind,search in [('ok','inspection',None),('x'*2001,'task_result',None),('ok','task_result','invented')]:
        with pytest.raises(m['file_tools'].ToolError):s.submit_report(summary,[],[],kind,search)
        assert (s.output/'report.json').read_bytes()==previous
    (s.root/'keep.txt').write_text('external mutation')
    with pytest.raises(m['file_tools'].ToolError,match='outside this session'):
        s.submit_report('ok',[],[],'task_result')
    assert (s.output/'report.json').read_bytes()==previous
