import hashlib
import os
from pathlib import Path

import pymupdf as fitz
import pytest

from src.adapters.geneloop_pdf import read_pdf
from src.adapters.harless_attachment_text import extract_attachment


def fixture_pdf():
    """Synthetic chart values exist only in pixels, not the text/caption."""
    drawing = fitz.open()
    chart = drawing.new_page(width=480, height=260)
    chart.insert_text((20, 25), 'Synthetic experiment: score', fontsize=15)
    chart.draw_rect((65, 150, 150, 225), color=(0, .3, .8), fill=(0, .3, .8))
    chart.draw_rect((270, 60, 355, 225), color=(.65, .1, .7), fill=(.65, .1, .7))
    chart.insert_text((90, 145), '17', fontsize=22)
    chart.insert_text((295, 55), '43', fontsize=22)
    chart.insert_text((85, 245), 'Alpha', fontsize=15)
    chart.insert_text((290, 245), 'Beta', fontsize=15)
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((40, 50), 'NATIVE-TEXT-90210: This is an exact native text layer.', fontsize=12)
    page.insert_text((40, 80), 'Figure 1: Comparison of two synthetic groups. Read bar values from pixels.', fontsize=11)
    page.insert_image((40, 140, 550, 416), stream=chart.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png'))
    source = drawing.new_page(width=595, height=842)
    source.insert_text((60, 100), 'SCANNED-ONLY-314159', fontsize=26)
    source.insert_text((60, 160), 'OCR scan document: sample size 2718.', fontsize=20)
    source.insert_text((60, 230), '扫描页中文识别测试', fontsize=24, fontname='china-s')
    page = pdf.new_page()
    page.insert_image(page.rect, stream=source.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png'))
    page = pdf.new_page()
    page.insert_text((40, 50), 'Figure 2: Vector diagram with a teal arrow.', fontsize=12)
    page.draw_line((80, 200), (430, 200), color=(0, .7, .6), width=8)
    page.draw_line((430, 200), (390, 170), color=(0, .7, .6), width=8)
    page.draw_line((430, 200), (390, 230), color=(0, .7, .6), width=8)
    data = pdf.tobytes()
    pdf.close(); drawing.close()
    return data


def test_native_scan_vector_coverage_and_exact_source(tmp_path, monkeypatch):
    monkeypatch.delenv('GENELOOP_PDF_OCR_ROOT', raising=False)
    data = fixture_pdf()
    result = read_pdf(data, visuals=True)
    assert result['sha256'] == hashlib.sha256(data).hexdigest()
    assert result['page_count'] == 3
    first, scan, vector = result['pages']
    assert first['text_method'] == 'text_layer' and not first['ocr_performed']
    assert '90210' in first['text'] and '43' not in first['text']
    assert scan['ocr_needed'] and scan['warning'] and not scan['ocr_performed']
    assert vector['visual_present'] and vector['image']['scope'].startswith('whole_page')
    assert all(page['image']['width'] <= 2400 and not page['visual_content_reviewed'] for page in result['pages'])
    path = tmp_path / 'test.pdf'; path.write_bytes(data)
    extracted = extract_attachment(path, pdf_visuals=True)
    assert extracted['status'] == 'extracted' and extracted['sha256'] == result['sha256']
    assert len(extracted['pages']) == 3 and path.read_bytes() == data


def test_real_ocr_only_on_scanned_page():
    if not os.environ.get('GENELOOP_PDF_OCR_ROOT'):
        pytest.skip('Install pinned languages for real OCR integration test')
    result = read_pdf(fixture_pdf())
    first, scan, vector = result['pages']
    assert first['text_method'] == vector['text_method'] == 'text_layer'
    assert scan['text_method'] == 'ocr', scan
    assert '314159' in scan['text'] and '2718' in scan['text'], scan['text']
    assert '中文识别' in scan['text'].replace(' ', ''), scan['text']
    assert 'image' not in scan


def test_pdf_page_version_encryption_and_corruption_boundaries():
    data = fixture_pdf()
    with pytest.raises(ValueError, match='page_not_in_document'): read_pdf(data, page_number=4)
    with pytest.raises(Exception): read_pdf(b'%PDF-invalid')
    with fitz.open(stream=data, filetype='pdf') as pdf:
        locked = pdf.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='reader')
    with pytest.raises(ValueError, match='pdf_encrypted'): read_pdf(locked)
    page = read_pdf(data, page_number=1)
    assert len(page['pages']) == 1 and page['page_count'] == 3


def test_ocr_fallback_failure_cannot_mislabel_partial_transcription_as_native(tmp_path,monkeypatch):
    languages=tmp_path/'tessdata';languages.mkdir()
    for name in ('eng','chi_sim'):(languages/(name+'.traineddata')).write_bytes(b'fixture')
    monkeypatch.setenv('GENELOOP_PDF_OCR_ROOT',str(tmp_path))
    source=fitz.open();p=source.new_page();p.insert_text((40,50),'OCR PARTIAL TRANSCRIPTION')
    partial=p.get_textpage()
    def ocr(page,*,language,**_):
        if language=='chi_sim':return partial
        raise RuntimeError('second OCR engine failed')
    monkeypatch.setattr(fitz.Page,'get_textpage_ocr',ocr)
    page=read_pdf(fixture_pdf(),page_number=2)['pages'][0]
    assert page['text']=='' and page['text_method']=='text_layer' and not page['ocr_performed']
    assert page['warning']=='pdf_page_ocr_failed_or_unavailable'
    source.close()
