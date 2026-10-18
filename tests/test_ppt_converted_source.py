from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import pytest
from scenarios.ppt_master.server import SourceReader
from scenarios.ppt_master.converted_source import ConvertedSources


@pytest.fixture
def source(tmp_path, monkeypatch):
    import scenarios.ppt_master.converted_source as module
    inputs=tmp_path/'inputs';inputs.mkdir();(tmp_path/'code').mkdir()
    pdf=inputs/'paper.pdf';pdf.write_bytes(b'%PDF-test')
    version=hashlib.sha256(pdf.read_bytes()).hexdigest()
    (tmp_path/'approved-inputs.json').write_text(json.dumps({'files':{pdf.name:version}}))
    reader=SourceReader(inputs)
    monkeypatch.setattr(module,'read_verified',lambda *args:b'verified')
    def run(args,**kwargs):
        path=Path(args[-1]);assert path.read_bytes()==pdf.read_bytes()
        assert 'DEEPSEEK_API_KEY' not in kwargs['env']
        path.with_suffix('.md').write_text('Full text with figure ![](image.png)',encoding='utf-8')
        (path.parent/'image.png').write_bytes(b'figure')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess,'run',run)
    skill=SimpleNamespace(root=tmp_path/'skill',lock={'files':{'scripts/source_to_md.py':'hash'}})
    api=ConvertedSources(reader,skill)
    pin=reader.pin(pdf.name,version)
    return tmp_path,reader,api,pin,pdf


def test_conversion_receipt_preserves_source_and_returns_complete_text(source):
    root,reader,api,pin,pdf=source
    before=pdf.read_bytes();converted=api.convert(pin['source_id']);out=api.read(converted['converted_id'])
    assert pdf.read_bytes()==before and out['version_sha256']==pin['version_sha256']
    assert out['text']=='Full text with figure ![](image.png)' and out['truncated'] is False
    assert out['markdown_path'].startswith('/work/ppt-source-') and not out['visual_checked']
    with pytest.raises(ValueError,match='unknown_session'):
        ConvertedSources(reader,api.skill).read(converted['converted_id'])


@pytest.mark.parametrize('mutation',['source','permission','derivative','new_file'])
def test_changed_source_or_derivative_never_reused(source,mutation):
    root,reader,api,pin,pdf=source;converted=api.convert(pin['source_id']);receipt=converted['converted_id']
    directory=api.receipts[receipt][3]
    if mutation=='source':pdf.write_bytes(b'changed')
    elif mutation=='permission':(root/'approved-inputs.json').write_text('{"files":{}}')
    elif mutation=='derivative':(directory/'source.md').write_text('changed')
    else:(directory/'extra.md').write_text('injected')
    with pytest.raises(ValueError):api.read(receipt)


def test_converter_failure_returns_no_receipt(source,monkeypatch):
    import scenarios.ppt_master.converted_source as module
    root,reader,api,pin,pdf=source
    monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=2))
    with pytest.raises(ValueError,match='failed_exit_2'):api.convert(pin['source_id'])
    assert api.receipts=={}


def test_markdown_change_after_tree_check_is_not_returned(source,monkeypatch):
    root,reader,api,pin,pdf=source;converted=api.convert(pin['source_id'])
    checked=api._files
    def change_after_hash(directory):
        hashes=checked(directory)
        (directory/'source.md').write_text('changed after tree check',encoding='utf-8')
        return hashes
    monkeypatch.setattr(api,'_files',change_after_hash)
    with pytest.raises(ValueError,match='version_changed'):api.read(converted['converted_id'])


def test_new_derivative_hardlink_is_rejected(source):
    import os
    root,reader,api,pin,pdf=source;converted=api.convert(pin['source_id'])
    directory=api.receipts[converted['converted_id']][3]
    os.link(directory/'source.md',directory/'alias.md')
    with pytest.raises(ValueError,match='hardlink'):api.read(converted['converted_id'])
