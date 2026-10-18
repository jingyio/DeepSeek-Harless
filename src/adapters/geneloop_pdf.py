"""Read exact PDF bytes: native text, per-page OCR, and source-bound page pixels.

No API calls, executable uploads, external resources, or cached model judgments.
OCR is transcription, never a claim that figures have been understood.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re

PIPELINE_VERSION = 'pdf-input-v1'


def tessdata_directory():
    root = os.environ.get('GENELOOP_PDF_OCR_ROOT')
    if not root:
        return None
    path = Path(root) / 'tessdata'
    for name in ('eng', 'chi_sim'):
        item = path / (name + '.traineddata')
        if item.is_symlink() or not item.is_file():
            raise ValueError('pdf_ocr_languages_unavailable')
    return str(path)


def read_pdf(data: bytes, *, visuals=False, page_number=None):
    import pymupdf as fitz
    digest = hashlib.sha256(data).hexdigest()
    with fitz.open(stream=data, filetype='pdf') as pdf:
        if pdf.needs_pass:
            raise ValueError('pdf_encrypted')
        if page_number is not None and (type(page_number) is not int or not 1 <= page_number <= len(pdf)):
            raise ValueError('page_not_in_document')
        pages = []
        selected = range(len(pdf)) if page_number is None else [page_number - 1]
        for index in selected:
            page = pdf[index]
            native = page.get_text(sort=True)
            images = page.get_image_info()
            # A small footer/header does not make a scanned body a text page.
            scan = any(fitz.Rect(image['bbox']).get_area() > page.rect.get_area() * .65 for image in images)
            needs_ocr = not native.strip() or (scan and len(re.sub(r'\s', '', native)) < 160)
            method, text, warning = 'text_layer', native, None
            if needs_ocr:
                try:
                    tessdata = tessdata_directory()
                    if not tessdata:
                        raise ValueError('pdf_ocr_languages_unavailable')
                    # Partial mode retains native text and OCRs image regions.
                    tp = page.get_textpage_ocr(language='chi_sim', dpi=200,
                                             full=not native.strip(), tessdata=tessdata)
                    text = page.get_text(textpage=tp, sort=True)
                    # Some supported MuPDF/Tesseract builds bias combined
                    # eng+chi_sim heavily toward Latin, even on clean Chinese.
                    # The Chinese model includes Latin/digits. Use the English
                    # model when its first transcript contains no CJK at all.
                    ocr_language = 'chi_sim'
                    if not re.search(r'[\u3400-\u9fff]', text):
                        tp = page.get_textpage_ocr(language='eng', dpi=200,
                                                 full=not native.strip(), tessdata=tessdata)
                        text = page.get_text(textpage=tp, sort=True)
                        ocr_language = 'eng'
                    method = 'ocr' if not native.strip() else 'text_layer_and_ocr'
                except Exception:
                    method, text, warning = 'text_layer', native, 'pdf_page_ocr_failed_or_unavailable'
            # Include vector diagrams as well as embedded raster figures. A
            # scanned page also needs pixels; OCR does not interpret its plots.
            visual = bool(images or page.get_drawings())
            row = {'page': index + 1, 'source_id': f'pdf:{digest}:page:{index+1}',
                   'text': text, 'text_method': method, 'ocr_performed': 'ocr' in method,
                   'ocr_needed': needs_ocr, 'visual_present': visual,
                   'visual_content_reviewed': False,
                   'captions': re.findall(r'(?im)^\s*(?:fig(?:ure)?\.?\s*\d+|图\s*\d+)[^\n]*(?:\n[^\n]+)?', text)}
            if warning:
                row['warning'] = warning
            if row['ocr_performed']:
                row['ocr_language'] = ocr_language
            if visuals and visual:
                scale = min(200 / 72, 2400 / max(page.rect.width, page.rect.height))
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                raw = pix.tobytes('jpeg', jpg_quality=90)
                row['image'] = {'media_type': 'image/jpeg', 'data': base64.b64encode(raw).decode('ascii'),
                                'sha256': hashlib.sha256(raw).hexdigest(),
                                'width': pix.width, 'height': pix.height,
                                'scope': 'whole_page_including_figures_captions_and_body'}
            pages.append(row)
        return {'pipeline_version': PIPELINE_VERSION, 'sha256': digest, 'page_count': len(pdf),
                'pages': pages, 'text': '\n\f\n'.join(row['text'] for row in pages),
                'ocr_performed': any(row['ocr_performed'] for row in pages),
                'coverage': 'page_text_and_ocr', 'visual_content_reviewed': False,
                'warnings': ['OCR may misread formulas, labels and numbers; verify critical claims against source pixels.',
                             'Page pixels require separate visual analysis; extracted text alone does not interpret figures.']}
