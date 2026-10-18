"""Version-bound presentation declarations and rendered slides, never authoring.

OOXML is evidence of stored settings, not a fully resolved style or proof that
fonts/effects rendered faithfully. Pixels are separately reviewed by the model.
"""
from __future__ import annotations

import hashlib


def presentation_structure(data: bytes):
    try:
        from .harless_attachment_text import _archive, _xml, _require_part, _relationships, _paragraphs, P, A, R
    except ImportError:
        from harless_attachment_text import _archive, _xml, _require_part, _relationships, _paragraphs, P, A, R

    digest = hashlib.sha256(data).hexdigest()
    with _archive(data) as archive:
        main = 'ppt/presentation.xml'
        root = _require_part(_xml(archive.read(main)), P, 'presentation')
        relations = _relationships(archive, main)
        order = root.find('{' + P + '}sldIdLst')
        if order is None:
            raise ValueError('presentation_order_unavailable')
        size = root.find('{' + P + '}sldSz')
        style = {'source_sha256': digest, 'coverage': 'stored_declarations_not_resolved_rendering',
                 'canvas_emu': dict(size.attrib) if size is not None else None,
                 'themes': [], 'masters': [], 'layouts': []}
        # These are declarations, retaining scheme references instead of guessing
        # inherited colors, transforms or font substitution.
        def paint(element):
            return [{'kind': node.tag.split('}')[-1], **node.attrib}
                    for node in element.iter() if node.tag in {
                        '{' + A + '}' + name for name in ('srgbClr', 'schemeClr', 'sysClr',
                        'tint', 'shade', 'alpha', 'lumMod', 'lumOff', 'gradFill', 'gs', 'noFill')}]

        def shape(node):
            props = next(node.iter('{' + P + '}cNvPr'), None)
            ph = next(node.iter('{' + P + '}ph'), None)
            fonts = [{'kind': x.tag.split('}')[-1], **x.attrib} for x in node.iter()
                     if x.tag in {'{' + A + '}' + n for n in ('rPr', 'defRPr', 'endParaRPr', 'latin', 'ea', 'cs')}]
            return {'kind': node.tag.split('}')[-1], 'name': props.get('name') if props is not None else None,
                    'placeholder': dict(ph.attrib) if ph is not None else None,
                    'text': _paragraphs(node, A), 'fonts': fonts, 'paint': paint(node),
                    'geometry': [{'kind': x.tag.split('}')[-1], **x.attrib} for x in node.iter()
                                 if x.tag in {'{' + A + '}' + n for n in ('xfrm', 'off', 'ext', 'chOff', 'chExt', 'prstGeom')}]}

        pages, used = [], set()
        def dependencies(part):
            if part in used:
                return
            used.add(part)
            directory, leaf = part.rsplit('/', 1)
            if directory + '/_rels/' + leaf + '.rels' not in archive.namelist():
                return
            for target in _relationships(archive, part).values():
                if not target or target not in archive.namelist():
                    continue
                if target.startswith('ppt/slideLayouts/') or target.startswith('ppt/slideMasters/'):
                    item = _xml(archive.read(target))
                    kind = 'layouts' if target.startswith('ppt/slideLayouts/') else 'masters'
                    if target not in used:
                        style[kind].append({'part': target, 'name': item.get('name'),
                            'paint': paint(item), 'shapes': [shape(x) for x in item.findall('.//{' + P + '}spTree/*')]})
                    dependencies(target)
                elif target.startswith('ppt/theme/') and target not in used:
                    used.add(target)
                    theme = _xml(archive.read(target))
                    style['themes'].append({'part': target, 'name': theme.get('name'), 'paint': paint(theme),
                        'color_scheme': {x.tag.split('}')[-1]: paint(x) for x in theme.findall('.//{' + A + '}clrScheme/*')},
                        'font_scheme': {x.tag.split('}')[-1]: [dict(f.attrib) for f in x] for x in theme.findall('.//{' + A + '}fontScheme/*')},
                        'fonts': [{'kind': x.tag.split('}')[-1], **x.attrib} for x in theme.iter()
                                  if x.tag in {'{' + A + '}' + n for n in ('majorFont', 'minorFont', 'latin', 'ea', 'cs', 'font')}]})

        for number, slide in enumerate(order, 1):
            part = relations.get(slide.get('{' + R + '}id'))
            if slide.tag != '{' + P + '}sldId' or not part or not part.startswith('ppt/slides/'):
                raise ValueError('presentation_order_unavailable')
            item = _require_part(_xml(archive.read(part)), P, 'sld')
            dependencies(part)
            pages.append({'page': number, 'source_id': f'pptx:{digest}:slide:{number}', 'part': part,
                          'text': _paragraphs(item, A), 'text_method': 'ooxml', 'ocr_performed': False,
                          'visual_present': True, 'visual_content_reviewed': False,
                          'style': {'paint': paint(item), 'shapes': [shape(x) for x in item.findall('.//{' + P + '}spTree/*')]}})
        return {'pipeline_version': 'presentation-input-v1', 'page_count': len(pages), 'slide_count': len(pages),
                'pages': pages, 'presentation_style': style,
                'coverage': 'stored_text_and_style_declarations',
                'warnings': ['OOXML font/color/geometry declarations are not resolved visual observations. Native objects, animations and exact font rendering require original-file inspection.']}


def read_presentation(data: bytes, *, suffix='.pptx', rendered_pdf=None, slide_number=None):
    digest = hashlib.sha256(data).hexdigest()
    if suffix == '.pptx':
        result = presentation_structure(data)
    else:
        if suffix != '.ppt' or not data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
            raise ValueError('presentation_format_invalid')
        result = {'pipeline_version': 'presentation-input-v1', 'pages': [],
                  'coverage': 'metadata_only', 'warnings': ['Legacy PPT requires isolated Office conversion; no native theme declarations extracted.']}
    if rendered_pdf is not None:
        try:
            from .geneloop_pdf import read_pdf
        except ImportError:
            from geneloop_pdf import read_pdf
        rendered = read_pdf(rendered_pdf, visuals=True, force_visuals=True)
        if result['pages'] and len(result['pages']) != rendered['page_count']:
            raise ValueError('presentation_render_page_count_mismatch')
        if not result['pages']:
            result['page_count'] = rendered['page_count']
            result['pages'] = [{'page': x['page'], 'text': x['text'], 'text_method': 'office_render_text',
                               'source_id': f'ppt:{digest}:slide:{x["page"]}'} for x in rendered['pages']]
        for page, visual in zip(result['pages'], rendered['pages']):
            for key in ('image', 'ocr_performed', 'warning', 'ocr_language'):
                if key in visual:
                    page[key] = visual[key]
            page.update(visual_present=True, visual_content_reviewed=False)
            if visual['ocr_performed']:
                page['rendered_ocr_text'] = visual['text']
            if 'image' in page:
                page['image']['scope'] = 'entire_rendered_slide'
        result['rendered_pdf_sha256'] = hashlib.sha256(rendered_pdf).hexdigest()
        result['coverage'] = 'stored_style_and_rendered_slides'
        result['warnings'].append('Rendering uses installed fonts and Office engine; missing fonts, effects, linked content, video and animations may differ. A still image does not certify playback.')
    else:
        result['warnings'].append('Slide rendering unavailable: do not claim to have seen the visual style.')
    if slide_number is not None:
        if type(slide_number) is not int or not 1 <= slide_number <= len(result['pages']):
            raise ValueError('page_not_in_document')
        result['pages'] = [result['pages'][slide_number - 1]]
    result['text'] = '\n\n'.join('[Slide ' + str(p['page']) + ']\n' + p['text'] for p in result['pages'])
    result['ocr_performed'] = any(p.get('ocr_performed') for p in result['pages'])
    return result
