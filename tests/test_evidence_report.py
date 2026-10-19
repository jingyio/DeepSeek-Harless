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
