"""Synthetic input parser diagnostics; no output deck is authored by the host."""
import hashlib
import io
import json
import zipfile

import pytest
from src.adapters.geneloop_presentation import read_presentation
from src.adapters.harless_attachment_text import extract_attachment, P, A, R, PACKAGE_R


def fixture_deck():
    parts = {
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldSz cx="12192000" cy="6858000"/><p:sldIdLst><p:sldId r:id="s2"/><p:sldId r:id="s1"/></p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{PACKAGE_R}"><Relationship Id="s1" Target="slides/slide1.xml"/><Relationship Id="s2" Target="slides/slide2.xml"/></Relationships>',
        'ppt/slides/_rels/slide2.xml.rels': f'<Relationships xmlns="{PACKAGE_R}"><Relationship Id="layout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="external" TargetMode="External" Target="https://never-fetch.invalid/private"/></Relationships>',
        'ppt/slideLayouts/slideLayout1.xml': f'<p:sldLayout xmlns:p="{P}" name="Title and content"/>',
        'ppt/slideLayouts/_rels/slideLayout1.xml.rels': f'<Relationships xmlns="{PACKAGE_R}"><Relationship Id="master" Target="../slideMasters/slideMaster1.xml"/></Relationships>',
        'ppt/slideMasters/slideMaster1.xml': f'<p:sldMaster xmlns:p="{P}" name="Reference master"/>',
        'ppt/slideMasters/_rels/slideMaster1.xml.rels': f'<Relationships xmlns="{PACKAGE_R}"><Relationship Id="theme" Target="../theme/theme1.xml"/></Relationships>',
        'ppt/theme/theme1.xml': f'<a:theme xmlns:a="{A}" name="Theme"><a:themeElements><a:clrScheme><a:accent1><a:srgbClr val="087F8C"/></a:accent1></a:clrScheme><a:fontScheme><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme></a:themeElements></a:theme>',
    }
    for index, text in [(1, 'Last slide'), (2, 'First slide')]:
        parts[f'ppt/slides/slide{index}.xml'] = f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="300000" y="200000"/><a:ext cx="9000000" cy="700000"/></a:xfrm><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></p:spPr><p:txBody><a:p><a:r><a:rPr sz="3200" b="1"><a:latin typeface="Aptos Display"/></a:rPr><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return stream.getvalue()


def test_slide_order_theme_master_geometry_and_unresolved_font_evidence():
    data = fixture_deck()
    result = read_presentation(data)
    assert result['text'].index('First slide') < result['text'].index('Last slide')
    style = result['presentation_style']
    assert style['source_sha256'] == hashlib.sha256(data).hexdigest()
    assert style['canvas_emu']['cx'] == '12192000'
    assert style['themes'][0]['color_scheme']['accent1'][0]['val'] == '087F8C'
    assert style['themes'][0]['font_scheme']['majorFont'][0]['typeface'] == 'Aptos Display'
    assert len(style['masters']) == len(style['layouts']) == 1
    shape = result['pages'][0]['style']['shapes'][0]
    assert shape['placeholder']['type'] == 'title'
    assert any(x.get('x') == '300000' for x in shape['geometry'])
    assert result['pages'][0]['visual_content_reviewed'] is False
    assert 'never-fetch' not in json.dumps(result)
    assert read_presentation(data, slide_number=2)['pages'][0]['text'] == 'Last slide'
    with pytest.raises(ValueError, match='page_not_in_document'):
        read_presentation(data, slide_number=3)


def test_renders_bind_original_version_and_every_slide_including_plain_text(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    pdf = fitz.open()
    for text in ['First slide', 'Last slide']:
        page = pdf.new_page(width=960, height=540)
        page.insert_text((30, 50), text)
    raw = pdf.tobytes()
    deck = tmp_path / 'reference.pptx'; deck.write_bytes(fixture_deck())
    rendered = tmp_path / 'reference.pdf'; rendered.write_bytes(raw)
    result = extract_attachment(deck, presentation_render={'path': str(rendered), 'sha256': hashlib.sha256(raw).hexdigest()})
    assert result['status'] == 'extracted'
    assert all(p['image']['scope'] == 'entire_rendered_slide' for p in result['pages'])
    assert result['pages'][0]['source_id'].startswith('pptx:' + result['sha256'])
    assert result['rendered_pdf_sha256'] != result['sha256']
    assert result['visual_content_reviewed'] is False
    result = extract_attachment(deck, presentation_render={'path': str(rendered), 'sha256': '0' * 64})
    assert result['reason'] == 'presentation_derivative_changed'
    pdf.new_page()
    with pytest.raises(ValueError, match='page_count_mismatch'):
        read_presentation(deck.read_bytes(), rendered_pdf=pdf.tobytes())


def test_legacy_and_renderer_failure_never_claim_visual_success(tmp_path):
    legacy = tmp_path / 'old.ppt'; legacy.write_bytes(b'legacy placeholder')
    result = extract_attachment(legacy)
    assert result['coverage'] == 'metadata_only' and not result['visual_content_reviewed']
    assert any('unavailable' in w for w in result['warnings'])
    path = tmp_path / 'source.pptx'; path.write_bytes(fixture_deck())
    result = extract_attachment(path)
    assert result['status'] == 'extracted' and not result['visual_content_reviewed']
    assert result['presentation_style'] and all('image' not in p for p in result['pages'])


def test_versioned_pptx_read_rechecks_admission(tmp_path):
    from scenarios.ppt_master.server import SourceReader
    inputs = tmp_path / 'inputs'; inputs.mkdir()
    path = inputs / 'ref.pptx'; data = fixture_deck(); path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    manifest = tmp_path / 'approved-inputs.json'
    manifest.write_text(json.dumps({'files': {'ref.pptx': sha}}))
    reader = SourceReader(inputs); pin = reader.pin(path.name, sha)
    page = reader.document(pin['source_id'], 2)
    assert page['page_count'] == 2 and 'Last slide' in page['text'] and page['visual_checked'] is False
    manifest.write_text(json.dumps({'files': {}}))
    with pytest.raises(ValueError, match='admission'):
        reader.document(pin['source_id'], 2)
