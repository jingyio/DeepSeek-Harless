"""Pinned skill reads, ordered integrity gate, and no legacy writer fallback."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import pytest
from scenarios.ppt_master import package,server


@pytest.fixture
def installed(tmp_path,monkeypatch):
    files={'SKILL.md':'official entry','workflows/routing.md':'routing','scripts/attribution_guard.py':'guard'}
    for name,text in files.items():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    versions={k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()}
    lock={'schema_version':1,'version':'6.6.0','files':versions,'package_sha256':hashlib.sha256(json.dumps(versions,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    monkeypatch.setattr(server,'read_lock',lambda:lock)
    monkeypatch.setattr(package,'read_lock',lambda:lock)
    monkeypatch.setattr(server.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0))
    return tmp_path,server.SkillReader(tmp_path)


def test_exact_entry_and_routing_bytes(installed):
    root,reader=installed
    entry=reader.read_skill_entry()
    routing=reader.read_pinned_routing(entry['source_id'])
    assert entry['text']=='official entry' and routing['text']=='routing'
    assert entry['version_sha256']==routing['version_sha256'] and routing['guard_exit_code']==0
    assert entry['skill_dir']=='/opt/geneloop/ppt-master'


@pytest.mark.parametrize('name',['SKILL.md','workflows/routing.md','scripts/attribution_guard.py'])
def test_changed_bytes_cannot_continue(installed,name):
    root,reader=installed;entry=reader.read_skill_entry()
    (root/name).write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='changed'):reader.read_pinned_routing(entry['source_id'])


def test_guard_failure_does_not_return_route(installed,monkeypatch):
    _,reader=installed
    monkeypatch.setattr(server.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1))
    with pytest.raises(ValueError,match='guard_failed'):reader.read_pinned_routing(reader.source_id)


def test_wrong_handle_and_extra_package_file_rejected(installed):
    root,reader=installed
    with pytest.raises(ValueError,match='version_mismatch'):reader.read_pinned_routing('source-'+'0'*32)
    (root/'injected.py').write_text('bad',encoding='utf-8')
    with pytest.raises(ValueError,match='unregistered'):package.verify_installation(root)


def test_registry_replaces_old_writer_but_preserves_old_library():
    root=Path(__file__).resolve().parents[1]
    row=next(x for x in json.loads((root/'config/harless-scenes.json').read_text())['scenes'] if x['id']=='ppt')
    scenario=json.loads((root/row['scenario']).read_text())
    assert row['ppt_execution_strategy']=='ppt_master'
    assert scenario['allowed_tools']==['mcp__ppt_master__read_skill_entry','mcp__ppt_master__pin_source','mcp__ppt_master__read_source_page','mcp__ppt_master__convert_source','mcp__ppt_master__read_converted_source']
    assert (root/'motif-libraries/ppt-web-v2-r13/entry.json').is_file()
    assert (root/'scenarios/research_ppt/web-scenario.json').is_file()


def test_source_pin_is_session_local_and_version_checked(tmp_path):
    from pypdf import PdfWriter
    folder=tmp_path/'inputs';folder.mkdir()
    pdf=folder/'article.pdf';writer=PdfWriter();writer.add_blank_page(width=200,height=300)
    with pdf.open('wb') as stream:writer.write(stream)
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    manifest=tmp_path/'approved-inputs.json';manifest.write_text(json.dumps({'files':{pdf.name:digest}}))
    reader=server.SourceReader(folder)
    anchor=reader.pin(pdf.name,digest)
    page=reader.document(anchor['source_id'])
    assert page['page']==1 and page['page_count']==1 and not page['visual_checked']
    assert page['version_sha256']==digest
    with pytest.raises(ValueError,match='source_not_in_session'):
        server.SourceReader(folder).document(anchor['source_id'])
    with pytest.raises(ValueError,match='page_not_in_document'):reader.document(anchor['source_id'],2)
    manifest.write_text(json.dumps({'files':{}}))
    with pytest.raises(ValueError,match='admission'):reader.document(anchor['source_id'])
    manifest.write_text(json.dumps({'files':{pdf.name:digest}}));pdf.write_bytes(b'changed')
    with pytest.raises(ValueError,match='admission'):reader.document(anchor['source_id'])
