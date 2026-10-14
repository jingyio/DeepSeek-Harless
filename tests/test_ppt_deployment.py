import hashlib
from src.adapters.harless_ppt_deployment import configure_ppt_rendering


def test_ppt_reading_is_available_without_falsely_claiming_rendering(monkeypatch):
    monkeypatch.delenv('HARLESS_PPT_RENDERER_ROOT',raising=False)
    monkeypatch.delenv('HARLESS_PPT_FONT_ROOT',raising=False)
    scene={};configure_ppt_rendering(scene)
    assert scene['output_unavailable_reason']=='ppt_rendering_dependencies_not_deployed'
    assert 'unavailable_reason' not in scene


def test_rendering_environment_and_binary_versions_are_bound(tmp_path,monkeypatch):
    renderer=tmp_path/'office';program=renderer/'program';program.mkdir(parents=True)
    (program/'soffice').write_text('launcher');(program/'soffice.bin').write_bytes(b'fixed binary')
    fonts=tmp_path/'fonts';fonts.mkdir()
    (fonts/'fonts-static.conf').write_text('fixed config');(fonts/'NotoSansCJKsc-Regular.otf').write_bytes(b'font')
    monkeypatch.setenv('HARLESS_PPT_RENDERER_ROOT',str(renderer));monkeypatch.setenv('HARLESS_PPT_FONT_ROOT',str(fonts))
    before=__import__('os').environ['PATH']
    scene={'config_sha256':'0'*64,'mcp_rows':[{'config':{'env':{}}}]}
    configure_ppt_rendering(scene)
    assert scene['mcp_rows'][0]['config']['env']['FONTCONFIG_FILE']==str(fonts/'fonts-static.conf')
    assert scene['runtime_file_locks'][str(program/'soffice.bin')]==hashlib.sha256(b'fixed binary').hexdigest()
    assert scene['config_sha256']!='0'*64
    assert __import__('os').environ['PATH']==before
