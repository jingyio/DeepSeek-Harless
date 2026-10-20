"""Local delivery and evidence checks; these are not model effectiveness results."""
import hashlib
import json
from pathlib import Path
import pytest
from src.adapters import evidence_report as module
from src.adapters.session_files import SessionFiles


def setup(tmp_path):
    root=tmp_path/'inputs';root.mkdir()
    data=b'Current real source bytes.';(root/'source.txt').write_bytes(data)
    versions={'source.txt':hashlib.sha256(data).hexdigest()}
    (tmp_path/'approved-inputs.json').write_text(json.dumps({'files':versions}))
    (tmp_path/'paper-output-grant.json').write_text(json.dumps({'schema_version':1,'task_id':'current','allow_output':True}))
    return root,versions,{'title':'Review','sections':[{'heading':'Check','paragraphs':['Keep the full source interpretation and its limitations.']}],'source_versions':versions}


def test_same_report_reuses_real_files_across_instances_but_modified_file_rebuilds(tmp_path,monkeypatch):
    pytest.importorskip('reportlab');pytest.importorskip('fitz')
    root,versions,args=setup(tmp_path);calls=[];build=module.build_document
    def count(*a,**kw):calls.append(1);return build(*a,**kw)
    monkeypatch.setattr(module,'build_document',count)
    first=module.SessionReport(SessionFiles(root),'paper-review').export(**args)
    assert first['exported'] and not first['artifact_reused']
    again=module.SessionReport(SessionFiles(root),'paper-review').export(**args)
    assert again['artifact_reused'] and first['artifacts']==again['artifacts'] and len(calls)==1
    (tmp_path/first['artifacts'][0]['name']).write_bytes(b'changed')
    third=module.SessionReport(SessionFiles(root),'paper-review').export(**args)
    assert third['exported'] and not third['artifact_reused'] and len(calls)==2


def test_content_configuration_task_and_permission_changes_invalidate_success(tmp_path,monkeypatch):
    pytest.importorskip('reportlab');pytest.importorskip('fitz')
    root,versions,args=setup(tmp_path)
    def export():return module.SessionReport(SessionFiles(root),'paper-review').export(**args)
    first=export();assert first['exported']
    args['title']='Revised';assert not export()['artifact_reused']
    config=module.rendering_config()
    monkeypatch.setattr(module,'rendering_config',lambda:{**config,'new_config':True})
    assert not export()['artifact_reused']
    path=tmp_path/'paper-output-grant.json';path.write_text(json.dumps({'schema_version':1,'task_id':'new','allow_output':True}))
    assert not export()['artifact_reused']
    path.write_text(json.dumps({'schema_version':1,'task_id':'new','allow_output':False}))
    with pytest.raises(ValueError,match='not_authorized'):export()
    (root/'source.txt').write_bytes(b'changed original')
    with pytest.raises(ValueError,match='version_changed'):export()


def test_failed_field_evidence_is_exact_and_does_not_become_a_success_cache(tmp_path,monkeypatch):
    root,versions,args=setup(tmp_path);calls=[]
    def fail(*a,**kw):
        calls.append(1)
        return {'quality_passed':False,'audit':{'checks':{'all_text_preserved':False},'missing_text':['section-0-paragraph-0']}}
    monkeypatch.setattr(module,'build_document',fail)
    report=module.SessionReport(SessionFiles(root),'paper-review')
    failure=report.export(**args);report.export(**args)
    issue=failure['argument_issues'][0]
    assert issue['pointer']=='/sections/0/paragraphs/0'
    assert issue['value_sha256']==hashlib.sha256(args['sections'][0]['paragraphs'][0].encode()).hexdigest()
    assert failure['execution_evidence']['arguments_sha256']==module.digest(args)
    assert failure['execution_evidence']['source_versions']==versions and len(calls)==2
    assert not (tmp_path/'outputs').exists()


def test_explicit_current_recovery_scope_rejects_subset_before_render_but_accepts_leaf_revision(tmp_path,monkeypatch):
    root,versions,args=setup(tmp_path)
    args['sections']*=2
    scope={'version':1,'kind':'current_review_recovery_scope','task_id':'current','source_versions':versions,'arguments':args,'policy':'preserve_structure_allow_semantic_leaf_revisions'}
    (tmp_path/'review-recovery-scope.json').write_text(json.dumps(scope))
    calls=[]
    monkeypatch.setattr(module,'build_document',lambda *a,**kw:calls.append(1))
    subset={**args,'sections':args['sections'][:1]}
    failure=module.SessionReport(SessionFiles(root),'paper-review').export(**subset)
    assert failure['failed_checks']==['recovery_structure_preserved'] and not calls
    assert failure['scope_issues'][0]['expected_items']==2
    assert module.structure_issues(args,{**args,'title':'Necessary revised title'})==[]


def test_natural_length_contract_removes_only_the_benchmark_page_cap(tmp_path):
    pytest.importorskip('reportlab');pytest.importorskip('fitz')
    payload={'title':'Full report','sections':[{'heading':'Complete records','paragraphs':[
        f'Record {i}: Preserve the original interpretation, all source evidence and the limitations. '*4 for i in range(110)]}],
        'figures':[],'metrics':[],'requirements':{'style':'brief','page_mode':'auto','pages':None}}
    built=module.build_document(payload,tmp_path/'natural',repair=False)
    assert built['page_count']>6 and built['quality_passed']
    assert built['audit']['acceptance_policy']['auto_page_limit'] is None
    capped=module._benchmark_audit(Path(built['path']),built['manifest_path'])
    assert not capped['checks']['page_constraint_satisfied']
    for key,value in built['audit']['checks'].items():
        if key!='page_constraint_satisfied':assert capped['checks'][key]==value
    explicit=module.engine.audit_document(Path(built['path']),built['manifest_path'],
        {'page_mode':'max','pages':6})
    assert not explicit['checks']['page_constraint_satisfied']
    assert module.rendering_config()['auto_page_limit'] is None
    assert explicit['quality_passed'] is False


def test_input_contract_failures_return_exact_fields_without_losing_report(tmp_path):
    root,versions,args=setup(tmp_path)
    args['sections']=[{'heading':f'Part {i}','paragraphs':[f'Unique evidence {i}']} for i in range(13)]
    failure=module.SessionReport(SessionFiles(root),'paper-review').export(**args)
    assert failure['exported'] is False and failure['failed_checks']==['report_input_contract']
    issue=failure['argument_issues'][0]
    assert issue['pointer']=='/sections' and issue['max_items']==12
    assert issue['value_sha256']==module.digest(args['sections'])
    assert not (tmp_path/'outputs').exists()


def test_live_capture_binds_actual_valid_operation_and_rejects_later_subset(tmp_path):
    root,versions,args=setup(tmp_path)
    args['sections']=[{'heading':'Complete records','paragraphs':['Record one','Record two']}]
    policy={'version':1,'kind':'capture_current_report_policy','task_id':'current',
        'source_versions':versions,'tool':'mcp__paper_checks__export_review_report',
        'schema_sha256':'a'*64,'user_envelope_sha256':'b'*64}
    (tmp_path/'report-state-policy.json').write_text(json.dumps(policy))
    report=module.SessionReport(SessionFiles(root),'paper-review')
    report.capture_current(args,report.context(args))
    path=tmp_path/'review-recovery-scope.json';raw=path.read_bytes();goal=json.loads(raw)
    assert goal['arguments']==args and goal['coverage_status']=='not_verified'
    assert goal['semantic_quality_accepted'] is False
    assert goal['origin']=='observed_current_export_operation_not_semantic_approval'
    assert not goal.get('execution_obligation')
    subset={**args,'sections':[{'heading':'Summary','paragraphs':['Record one']} ]}
    failure=report.export(**subset)
    assert failure['failed_checks']==['recovery_structure_preserved']
    assert path.read_bytes()==raw
    assert module.structure_issues(goal['arguments'],{**args,'title':'Necessary correction'})==[]


def test_live_capture_requires_current_task_and_never_replaces_prior_scope(tmp_path):
    root,versions,args=setup(tmp_path)
    policy={'version':1,'kind':'capture_current_report_policy','task_id':'foreign','source_versions':versions}
    (tmp_path/'report-state-policy.json').write_text(json.dumps(policy))
    report=module.SessionReport(SessionFiles(root),'paper-review')
    with pytest.raises(ValueError,match='not_authorized'):report.capture_current(args,report.context(args))
    assert not (tmp_path/'review-recovery-scope.json').exists()


def test_automatic_input_recovery_rejects_lost_text_then_accepts_lossless_regrouping(tmp_path):
    root,versions,args=setup(tmp_path)
    args['sections']=[{'heading':f'Part {i}','paragraphs':[f'Original unique record {i}']} for i in range(13)]
    policy={'version':1,'kind':'capture_current_report_policy','task_id':'current','source_versions':versions,'tool':'mcp__paper_checks__export_review_report','schema_sha256':'a'*64,'user_envelope_sha256':'b'*64}
    (tmp_path/'report-state-policy.json').write_text(json.dumps(policy))
    report=module.SessionReport(SessionFiles(root),'paper-review');first=report.export(**args)
    assert first['failed_checks']==['report_input_contract']
    scope=json.loads((tmp_path/'review-recovery-scope.json').read_text());assert scope['arguments']==args
    lossy={**args,'sections':args['sections'][:12]}
    failure=report.export(**lossy)
    assert failure['failed_checks']==['recovery_content_preserved']
    assert failure['argument_issues'][0]['missing_paragraphs']==1
    import copy
    corrected=copy.deepcopy(lossy);corrected['sections'][-1]['paragraphs']+=args['sections'][-1]['paragraphs']
    assert report.preserved_input_text(corrected,report.context(corrected)) is None
    final=json.loads((tmp_path/'review-recovery-scope.json').read_text())
    assert final['arguments']==corrected and final['policy']=='preserve_structure_allow_semantic_leaf_revisions'
    assert final['semantic_quality_accepted'] is False
    assert final['initial_arguments']==args and final['initial_arguments_sha256']==module.digest(args)


@pytest.mark.parametrize('windows',[True] if module.sys.platform=='win32' else [False,True])
def test_scope_publication_keeps_readonly_and_replaces_without_deleting_current_file(tmp_path,monkeypatch,windows):
    import stat
    target=tmp_path/'review-recovery-scope.json';old=b'previous protected scope';target.write_bytes(old);target.chmod(0o400)
    replace=module.os.replace;calls=[]
    def checked(source,destination):
        assert destination.read_bytes()==old  # No unlink-before-replace window.
        if windows:
            assert destination.stat().st_mode&stat.S_IWRITE
            assert source.stat().st_mode&stat.S_IWRITE
        calls.append(1);return replace(source,destination)
    monkeypatch.setattr(module.os,'replace',checked)
    # Windows' native branch is already checked by the integration test above;
    # POSIX can exercise both contracts without changing os.name/sys.platform.
    module._replace_recovery_scope(tmp_path,b'current protected scope',hashlib.sha256(old).hexdigest(),windows=windows)
    assert calls==[1] and target.read_bytes()==b'current protected scope'
    assert not target.stat().st_mode&stat.S_IWRITE
    assert not list(tmp_path.glob('report-scope-*.tmp'))


def test_failed_windows_scope_replacement_preserves_old_version_protection_and_cleans_temporary(tmp_path,monkeypatch):
    import stat
    target=tmp_path/'review-recovery-scope.json';old=b'unchanged scope';target.write_bytes(old);target.chmod(0o400)
    def refuse(*args):raise PermissionError('simulated replacement refused')
    monkeypatch.setattr(module.os,'replace',refuse)
    with pytest.raises(PermissionError,match='simulated replacement refused'):
        module._replace_recovery_scope(tmp_path,b'new scope',hashlib.sha256(old).hexdigest(),windows=True)
    assert target.read_bytes()==old and not target.stat().st_mode&stat.S_IWRITE
    assert not list(tmp_path.glob('report-scope-*.tmp'))


def test_windows_scope_replacement_rejects_stale_evidence_before_changing_target(tmp_path,monkeypatch):
    import stat
    target=tmp_path/'review-recovery-scope.json';target.write_bytes(b'newer current version');target.chmod(0o400)
    def forbidden(*args):pytest.fail('stale scope must not be replaced')
    monkeypatch.setattr(module.os,'replace',forbidden)
    with pytest.raises(ValueError,match='current_recovery_scope_changed'):
        module._replace_recovery_scope(tmp_path,b'stale candidate','0'*64,windows=True)
    assert target.read_bytes()==b'newer current version' and not target.stat().st_mode&stat.S_IWRITE
    assert not list(tmp_path.glob('report-scope-*.tmp'))
