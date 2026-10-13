"""真实 PPTX 渲染与交付完整性检查；不认证科研结论，不改写内容。"""
from __future__ import annotations

import importlib.metadata
import base64
from collections import Counter
import hashlib
from decimal import Decimal, InvalidOperation
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import signal
import subprocess
import time
import unicodedata
from uuid import uuid4
import zipfile

from defusedxml import ElementTree as ET

from .documents import file_hash, safe_zip, pptx_slide_paths

ROOT = Path(__file__).resolve().parents[2]
NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
MAX_SLIDES = 30


def _private(path: Path) -> Path:
    root = ROOT.resolve()
    private = (root / '.local').resolve()
    resolved = path.resolve()
    if not private.is_relative_to(root) or not resolved.is_relative_to(private):
        raise ValueError('验收输入和产物必须位于仓库 .local，不能通过链接越界')
    return resolved


def _normal(text: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', text).split())


def _missing_texts(expected: list[str], actual: str) -> list[str]:
    """保留重复项，并禁止短数字被更长数值覆盖；仍非科学语义认证。"""
    actual = unicodedata.normalize('NFKC', actual)
    available, used, missing = {}, {}, []
    for text in expected:
        wanted = _normal(text)
        if not wanted:
            continue
        if wanted not in available:
            # 容许渲染产生换行，保留实际token边界，避免相邻数值合成一串。
            pattern = r'\s*'.join(re.escape(character) for character in wanted)
            if re.match(r'^[+-]?(?:\d|\.\d)', wanted):
                pattern = r'(?<![\d.+\-])' + pattern
            if wanted[-1].isdigit():
                pattern += r'(?![\d.]|[eE][+\-]?\d)'
            available[wanted] = sum(1 for _ in re.finditer(pattern, actual))
        used[wanted] = used.get(wanted, 0) + 1
        if used[wanted] > available[wanted]:
            missing.append(text)
    return missing


def _cjk_characters(text: str) -> Counter:
    """核汉字（含扩展/兼容）、假名及韩文；NFKC归一化兼容字和组合字。"""
    ranges = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
              (0x20000, 0x2FA1F), (0x30000, 0x3347F),
              (0x3040, 0x30FF), (0x31F0, 0x31FF), (0x1AFF0, 0x1AFFF), (0x1B000, 0x1B16F),
              (0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F),
              (0xAC00, 0xD7AF), (0xD7B0, 0xD7FF))
    return Counter(character for character in unicodedata.normalize('NFKC', text)
                   if any(first <= ord(character) <= last for first, last in ranges))


def _check_rendered_glyphs(page, wanted: list[str], report: dict, page_number: int) -> dict:
    """核实际绘制字形；PDF ToUnicode文字存在不证明字体能够正确画出文字。

    对照计划与可见texttrace的CJK字符数量，捕捉缺字及Unicode/GID坍缩；
    全文另拒绝可见非空白的.notdef（GID0）。不认证字体轮廓、遮挡或美观。
    Type3/路径化字体可能通过独立图形路径画字，却只给出ignored-text记录；
    此时当前oracle无法自动确认绘制覆盖，严格拒绝，不断言PNG中真的缺字。
    """
    expected = _cjk_characters('\n'.join(wanted))
    painted, notdef, ignored = [], [], 0
    for span in page.get_texttrace():
        if span.get('type') == 3 or span.get('opacity', 1) <= 0:
            ignored += 1
            continue
        for character in span['chars']:
            codepoint, glyph_id, _, box = character
            if not isinstance(codepoint, int) or not 0 <= codepoint <= 0x10FFFF:
                continue
            text = chr(codepoint)
            if text.isspace() or unicodedata.category(text) in ('Cc', 'Cf'):
                continue
            x0, y0, x1, y1 = box
            if x1 <= page.rect.x0 or y1 <= page.rect.y0 or x0 >= page.rect.x1 or y0 >= page.rect.y1:
                continue
            painted.append(text)
            if glyph_id == 0:
                notdef.append({'unicode': f'U+{codepoint:04X}', 'font': span.get('font', 'unknown')})
    observed = _cjk_characters(''.join(painted))
    missing = expected - observed
    result = {'page': page_number, 'expected_cjk_characters': sum(expected.values()),
              'painted_cjk_characters': sum(observed.values()), 'missing_cjk_characters': sum(missing.values()),
              'missing_cjk_codepoints': [{'unicode': f'U+{ord(character):04X}', 'count': count}
                                         for character, count in sorted(missing.items())][:20],
              'visible_notdef_glyphs': len(notdef), 'notdef_examples': notdef[:20],
              'ignored_invisible_spans': ignored}
    if missing:
        _issue(report, 'render_cjk_glyph_missing_or_collapsed',
               '计划CJK文字的实际绘制覆盖无法自动确认：可能缺字、字形坍缩或Type3/路径化字体，拒绝交付',
               page=page_number, missing_count=sum(missing.values()))
    if notdef:
        _issue(report, 'render_visible_notdef_glyph', '实际PDF含可见缺字字形（GID0），拒绝交付',
               page=page_number, glyph_count=len(notdef))
    return result


def _expected(value, count: int, name: str):
    if value is None:
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != count
            or any(not isinstance(row, (list, tuple)) or len(row) > 300 for row in value)
            or any(not isinstance(text, str) or len(text) > 10000
                   for row in value for text in row)):
        raise ValueError(f'{name} 需要与页数一致的逐页字符串列表')
    return [[text for text in row if text.strip()] for row in value]


def _check_scientific_footer(page, visible_sources: list[str], report: dict, page_number: int) -> dict:
    """只核科研页实际绘制正文是否侵入来源栏，不替代完整视觉审阅。

    来源位置从PDF中实际绘制的完整出处找回，不能只相信预估文本框。
    大于12pt的可见字符属于标题/主体/图轴/模块，10pt来源不计入正文。
    原图内文字是图片像素，此检查不能判断其可读性。
    """
    if not visible_sources:
        return {'page': page_number, 'checked': False}
    characters, boxes, sizes = [], [], []
    for span in page.get_texttrace():
        if span.get('type') == 3 or span.get('opacity', 1) <= 0:
            continue
        for codepoint, _, _, box in span['chars']:
            if not isinstance(codepoint, int) or not 0 <= codepoint <= 0x10FFFF:
                continue
            text = _normal(chr(codepoint))
            for character in text:
                characters.append(character)
                boxes.append(box)
                sizes.append(span.get('size', 0))
    actual = ''.join(characters)
    footer_boxes = []
    for source in visible_sources:
        wanted = _normal(source)
        start = actual.find(wanted)
        if start < 0:
            _issue(report, 'render_visible_source_unlocated', '不能定位实际绘制的科研出处，拒绝交付', page=page_number)
            return {'page': page_number, 'checked': False, 'reason': 'source_glyphs_unlocated'}
        footer_boxes.extend(boxes[start:start + len(wanted)])
    footer_top = min(box[1] for box in footer_boxes)
    # 要求至少3pt可见间距，捕捉完全保留文字却覆盖/贴近来源的真实失败。
    collisions = [box for box, size in zip(boxes, sizes)
                  if size > 12 and box[3] > footer_top - 3]
    result = {'page': page_number, 'checked': True, 'footer_top_points': round(footer_top, 2),
              'required_gap_points': 3, 'intruding_body_characters': len(collisions)}
    if collisions:
        _issue(report, 'render_body_intrudes_source_footer',
               '实际绘制正文侵入科研来源栏；需重新安排版面，不能以文字保留替代可读性',
               page=page_number, character_count=len(collisions))
    return result


def plan_expectations(plan: dict) -> dict:
    """从完整生成计划提取可见正文和独立图表数据，不以产物反推期望。

    图表数值保存在原生图表缓存中，showValue=False 时不要求 PDF 显示
    每个点；轴标题、分类和实际显示的系列图例则必须出现在渲染中。
    普通 notes/sources 不是页面正文，来源继续用 expected_sources 单独核验。
    opt-in 科研页型的证据说明与宿主派生可见出处属于页面正文，须完整核验；
    source_notes 是证据索引绑定的独立备注期望，不能从生成后的 PPTX 反推。
    """
    if not isinstance(plan, dict) or not isinstance(plan.get('slides'), list) or not 1 <= len(plan['slides']) <= MAX_SLIDES:
        raise ValueError('完整计划需要 1–30 个页面')
    texts, charts, tables, images, source_notes = [], [], [], [], []
    for slide in plan['slides']:
        if not isinstance(slide, dict):
            raise ValueError('完整计划的页面必须是对象')
        row = []

        def add(value):
            if not isinstance(value, str):
                raise ValueError('完整计划的可见文字必须是字符串')
            if value.strip():
                row.append(value)

        add(slide['title'])
        for bullet in slide.get('bullets', []):
            add(bullet)
        if slide.get('takeaway') is not None:
            add(slide['takeaway'])
        for cells in slide.get('table', []):
            for cell in cells:
                add(cell)
        if slide.get('comparison') is not None:
            for side in ('left', 'right'):
                column = slide['comparison'][side]
                add(column['title'])
                for bullet in column['bullets']:
                    add(bullet)
        if slide.get('process') is not None:
            for step in slide['process']['steps']:
                add(step['label'])
                add(step['detail'])
        note_bindings = []
        if slide.get('archetype') is not None:
            if not isinstance(slide['archetype'], str) or slide['archetype'] not in {'evidence-focus', 'result-summary', 'method-map'}:
                raise ValueError('完整计划包含未知科研页型')
            notes = slide.get('evidence_notes', [])
            sources = slide.get('sources')
            visible = slide.get('visible_sources')
            if (not isinstance(notes, list) or len(notes) > 3 or not isinstance(sources, list)
                    or not sources or not isinstance(visible, list) or not visible or len(visible) > len(sources)):
                raise ValueError('科研页型需要合法证据说明、原来源及宿主派生可见出处')
            for note in notes:
                if (not isinstance(note, dict) or set(note) != {'label', 'text', 'source_index'}
                        or not isinstance(note['label'], str) or not note['label'].strip()
                        or len(note['label']) > 24 or not isinstance(note['text'], str)
                        or not note['text'].strip() or len(note['text']) > 110
                        or type(note['source_index']) is not int
                        or not 1 <= note['source_index'] <= len(visible)):
                    raise ValueError('科研页型证据说明或原来源索引无效')
                # 页面标题必须保留来源索引；仅核原label会漏掉可见绑定被篡改。
                add(f"{note['label']} [{note['source_index']}]")
                add(note['text'])
                note_bindings.append(f"证据说明 [{note['source_index']}] {note['label']}：{note['text']}")
            for citation in visible:
                add(citation)
        elif 'evidence_notes' in slide or 'visible_sources' in slide:
            raise ValueError('科研证据说明和可见出处仅适用于显式科研页型')
        source_notes.append(note_bindings)
        texts.append(row)
        charts.append(slide.get('chart'))
        tables.append(slide.get('table'))
        images.append(_image_expectation(slide['image']) if slide.get('image') is not None else None)
    return {'texts': _expected(texts, len(texts), 'expected_texts'),
            'charts': _expected_charts(charts, len(texts)),
            'tables': _expected_tables(tables, len(texts)),
            'images': _expected_images(images, len(texts)),
            'source_notes': _expected(source_notes, len(texts), 'source_notes')}


def _image_signature(raw: bytes) -> dict:
    from PIL import Image
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError('图片数据超出验收大小限制')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in {'PNG', 'JPEG'} or not 1 <= image.width <= 10000 or not 1 <= image.height <= 10000:
            raise ValueError('生成计划图片格式或尺寸无效')
        result = {'sha256': hashlib.sha256(raw).hexdigest(), 'format': image.format,
                  'width': image.width, 'height': image.height}
        image.verify()
    return result


def _image_expectation(image: dict) -> dict:
    if not isinstance(image, dict) or set(image) != {'data', 'width', 'height'}:
        raise ValueError('完整计划图片须为宿主解析的 data/width/height')
    data = image['data']
    if not isinstance(data, str) or len(data) > 16_000_000 or not re.fullmatch(r'image/(png|jpeg);base64,[A-Za-z0-9+/=]+', data):
        raise ValueError('完整计划图片编码无效')
    result = _image_signature(base64.b64decode(data.split(',', 1)[1], validate=True))
    if image['width'] != result['width'] or image['height'] != result['height']:
        raise ValueError('完整计划图片尺寸与原字节不一致')
    return result


def _expected_images(value, count: int):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError('expected_images 需要与页数一致的逐页图片摘要或 null 列表')
    result = []
    for image in value:
        if image is None:
            result.append(None)
            continue
        if (not isinstance(image, dict) or set(image) != {'sha256', 'format', 'width', 'height'}
                or not isinstance(image['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', image['sha256'])
                or image['format'] not in {'PNG', 'JPEG'}
                or any(type(image[key]) is not int or not 1 <= image[key] <= 10000 for key in ('width', 'height'))):
            raise ValueError('expected_images 需要合法原图字节 SHA、格式和尺寸')
        result.append(dict(image))
    return result


def _native_images(root, archive, slide_name: str, relations: list, width: int, height: int) -> list[dict]:
    result = []
    pictures = root.findall('p:cSld/p:spTree/p:pic', NS)
    if len(pictures) != len(root.findall('.//p:pic', NS)):
        raise ValueError('计划原图位于未支持的组合变换中，不能证明目标页原样可见')
    for picture in pictures:
        blip = picture.find('p:blipFill/a:blip', NS)
        if blip is None or '{' + NS['r'] + '}link' in blip.attrib:
            raise ValueError('计划图片缺少包内嵌入引用或含外链')
        rid = blip.attrib.get('{' + NS['r'] + '}embed')
        matches = [rel for rel in relations if rel.attrib.get('Id') == rid]
        if len(matches) != 1 or not matches[0].attrib.get('Type', '').endswith('/image'):
            raise ValueError('计划图片关系缺失或不唯一')
        relation = matches[0]
        target = relation.attrib.get('Target', '')
        if relation.attrib.get('TargetMode', '').lower() == 'external' or '\\' in target or ':' in target:
            raise ValueError('计划图片关系含外部或不安全路径')
        path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else
                                 posixpath.join(posixpath.dirname(slide_name), target))
        if not re.fullmatch(r'ppt/media/[^/]+', path) or path not in archive.namelist():
            raise ValueError('计划图片引用缺失或越界媒体')
        for element in picture.findall('p:blipFill/a:srcRect', NS) + picture.findall('p:blipFill/a:stretch/a:fillRect', NS):
            if any(element.attrib.get(key, '0') != '0' for key in ('l', 't', 'r', 'b')):
                raise ValueError('计划原图被裁剪，不能证明完整保留')
        if picture.find('p:blipFill/a:tile', NS) is not None or list(blip):
            raise ValueError('计划原图含重复填充或像素效果，不能证明原样可见')
        nonvisual = picture.find('p:nvPicPr/p:cNvPr', NS)
        if nonvisual is None or nonvisual.attrib.get('hidden', '0') not in {'0', 'false'}:
            raise ValueError('计划图片被隐藏或缺少可见属性')
        transform = picture.find('p:spPr/a:xfrm', NS)
        if transform is None or any(transform.attrib.get(key, '0') not in {'0', 'false'} for key in ('rot', 'flipH', 'flipV')):
            raise ValueError('计划原图缺少位置或被旋转翻转')
        offset, extent = transform.find('a:off', NS), transform.find('a:ext', NS)
        if offset is None or extent is None:
            raise ValueError('计划原图缺少可见尺寸')
        x, y, w, h = (int(offset.attrib['x']), int(offset.attrib['y']), int(extent.attrib['cx']), int(extent.attrib['cy']))
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width + 12700 or y + h > height + 12700:
            raise ValueError('计划原图位于页面外或尺寸无效')
        signature = _image_signature(archive.read(path))
        if abs(w * signature['height'] - h * signature['width']) > max(signature['width'], signature['height']) * 2:
            raise ValueError('计划原图纵横比被改变')
        result.append(signature)
    return result


def _check_image_plan(actual: list[dict], expected: dict | None, report: dict, page: int):
    # 无原图计划的页面不受此窄oracle限制；restyle另由包保留检查承担。
    if expected is None:
        return
    if len(actual) != 1:
        _issue(report, 'planned_image_count_mismatch', '计划原图没有对应目标页唯一可见的图片引用', page=page)
    elif actual[0] != expected:
        _issue(report, 'planned_image_missing_or_changed', '目标页图片格式、尺寸或原字节摘要与计划不符', page=page)


def _expected_tables(value, count: int):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError('expected_tables 需要与页数一致的逐页表格或 null 列表')
    result = []
    for table in value:
        if table is None:
            result.append(None)
            continue
        if (not isinstance(table, list) or not 2 <= len(table) <= 6
                or not isinstance(table[0], list) or not 1 <= len(table[0]) <= 4
                or any(not isinstance(row, list) or len(row) != len(table[0])
                       or any(not isinstance(cell, str) or not cell.strip() or len(cell) > 45
                              for cell in row) for row in table)):
            raise ValueError('expected_tables 需要 2–6 行、1–4 列的非空短文本单元格')
        result.append([list(row) for row in table])
    return result


def _native_tables(root) -> list[list[list[str]]]:
    """按实际 OOXML 行列读取；生成协议未支持的合并单元格拒绝比较。"""
    tables = []
    for table in root.findall('.//a:tbl', NS):
        rows = []
        grid = table.find('a:tblGrid', NS)
        width = len(grid.findall('a:gridCol', NS)) if grid is not None else 0
        if not 1 <= width <= 4:
            raise ValueError('原生表格列数与受限生成协议不符')
        for row in table.findall('a:tr', NS):
            cells = row.findall('a:tc', NS)
            if len(cells) != width or any(any(cell.attrib.get(key, '1' if key in {'gridSpan', 'rowSpan'} else '0')
                                                != ('1' if key in {'gridSpan', 'rowSpan'} else '0')
                                            for key in ('gridSpan', 'rowSpan', 'hMerge', 'vMerge')) for cell in cells):
                raise ValueError('原生表格行列或合并状态与受限生成协议不符')
            rows.append([''.join(part.text or '' for part in cell.findall('a:txBody/.//a:t', NS)) for cell in cells])
        if not 2 <= len(rows) <= 6:
            raise ValueError('原生表格行数与受限生成协议不符')
        tables.append(rows)
    return tables


def _check_table_plan(actual: list[list[list[str]]], expected: list[list[str]] | None,
                      report: dict, page: int):
    if expected is None:
        if actual:
            _issue(report, 'unexpected_native_table', '计划中无表格，但页面包含原生表格', page=page)
        return
    if len(actual) != 1:
        _issue(report, 'native_table_count_mismatch', '计划表格没有对应唯一的原生表格', page=page)
        return
    found = actual[0]
    if len(found) != len(expected) or any(len(a) != len(b) for a, b in zip(found, expected)):
        _issue(report, 'table_shape_missing_or_changed', '原生表格行列数与提交计划不符', page=page)
        return
    changed = [(r + 1, c + 1) for r, row in enumerate(expected) for c, cell in enumerate(row)
               if _normal(found[r][c]) != _normal(cell)]
    if changed:
        _issue(report, 'table_cell_missing_or_changed', '原生表格单元格文字或数值与对应行列计划不符',
               page=page, cells=[{'row': r, 'column': c} for r, c in changed])


def _expected_charts(value, count: int):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError('expected_charts 需要与页数一致的逐页图表或 null 列表')
    checked = []
    for chart in value:
        if chart is None:
            checked.append(None)
            continue
        if (not isinstance(chart, dict) or set(chart) - {'type', 'categories', 'series', 'x_label', 'y_label', 'unit'}
                or chart.get('type') not in {'bar', 'line'}):
            raise ValueError('expected_charts 仅支持原生 bar/line 图表')
        categories, series = chart.get('categories'), chart.get('series')
        if (not isinstance(categories, list) or not 2 <= len(categories) <= 10
                or any(not isinstance(item, str) or not item.strip() or len(item) > 25 for item in categories)
                or len(set(categories)) != len(categories) or not isinstance(series, list) or not 1 <= len(series) <= 3):
            raise ValueError('expected_charts 分类和系列无效')
        for item in series:
            if (not isinstance(item, dict) or set(item) != {'name', 'values'}
                    or not isinstance(item['name'], str) or not item['name'].strip() or len(item['name']) > 30
                    or not isinstance(item['values'], list) or len(item['values']) != len(categories)
                    or any(type(number) not in (int, float) or not math.isfinite(number) for number in item['values'])):
                raise ValueError('expected_charts 需要有限数值和对应系列名称')
        for key in ('x_label', 'y_label', 'unit'):
            if key in chart and (not isinstance(chart[key], str) or not chart[key].strip() or len(chart[key]) > 40):
                raise ValueError('expected_charts 轴标题和单位必须是短文字')
        checked.append(json.loads(json.dumps(chart, ensure_ascii=False, allow_nan=False)))
    return checked


def _chart_visible_texts(chart: dict) -> list[str]:
    result = list(chart['categories'])
    if chart.get('x_label'):
        result.append(chart['x_label'])
    y_title = ' / '.join(chart[key] for key in ('y_label', 'unit') if chart.get(key))
    if y_title:
        result.append(y_title)
    if len(chart['series']) > 1:
        result.extend(item['name'] for item in chart['series'])
    return result


def _chart_points(element, path: str) -> list[str]:
    cache = element.find(path, NS)
    if cache is None:
        raise ValueError('原生图表缺少对应的文字或数据缓存')
    count = cache.find('c:ptCount', NS)
    if cache.tag.rsplit('}', 1)[-1] == 'multiLvlStrCache':
        levels = cache.findall('c:lvl', NS)
        if len(levels) != 1:
            raise ValueError('生成计划仅支持单层图表分类，缓存层级不符')
        points = levels[0].findall('c:pt', NS)
    else:
        points = cache.findall('c:pt', NS)
    if count is None or int(count.attrib['val']) != len(points):
        raise ValueError('原生图表缓存数量与数据不符')
    indexed = {}
    for point in points:
        index = int(point.attrib['idx'])
        number = point.find('c:v', NS)
        if index in indexed or number is None:
            raise ValueError('原生图表缓存索引或数值缺失')
        indexed[index] = number.text or ''
    if set(indexed) != set(range(len(points))):
        raise ValueError('原生图表缓存索引不连续')
    return [indexed[index] for index in range(len(points))]


def _native_chart(root) -> dict:
    plot = root.find('c:chart/c:plotArea', NS)
    if plot is None:
        raise ValueError('原生图表缺少 plotArea')
    kinds = [(kind, plot.find('c:' + kind + 'Chart', NS)) for kind in ('bar', 'line')]
    kinds = [(kind, element) for kind, element in kinds if element is not None]
    if len(kinds) != 1:
        return {'type': 'unsupported', 'series': []}
    kind, element = kinds[0]
    series = []
    for item in element.findall('c:ser', NS):
        names = _chart_points(item, 'c:tx/c:strRef/c:strCache')
        if len(names) != 1:
            raise ValueError('原生图表系列名称缓存不唯一')
        values = _chart_points(item, 'c:val/c:numRef/c:numCache')
        try:
            if any(not Decimal(number).is_finite() for number in values):
                raise ValueError('原生图表含非有限数值')
        except InvalidOperation as error:
            raise ValueError('原生图表含非法数值') from error
        category_path = ('c:cat/c:multiLvlStrRef/c:multiLvlStrCache'
            if item.find('c:cat/c:multiLvlStrRef', NS) is not None else 'c:cat/c:strRef/c:strCache')
        series.append({'name': names[0], 'categories': _chart_points(item, category_path), 'values': values})

    def axis_title(axis):
        item = plot.find('c:' + axis + 'Ax', NS)
        if item is None or item.find('c:delete', NS) is not None and item.find('c:delete', NS).attrib.get('val') == '1':
            return ''
        return ''.join(part.text or '' for part in item.findall('c:title/.//a:t', NS))

    return {'type': kind, 'series': series, 'x_title': axis_title('cat'), 'y_title': axis_title('val')}


def _check_chart_plan(actual: list[dict], expected: dict | None, report: dict, page: int):
    if expected is None:
        if actual:
            _issue(report, 'unexpected_native_chart', '计划中无图表，但页面包含原生图表', page=page)
        return
    if len(actual) != 1:
        _issue(report, 'native_chart_count_mismatch', '计划图表没有对应唯一的原生图表', page=page)
        return
    chart = actual[0]
    x_title, y_title = expected.get('x_label', ''), ' / '.join(expected[key] for key in ('y_label', 'unit') if expected.get(key))
    if _normal(chart.get('x_title', '')) != _normal(x_title) or _normal(chart.get('y_title', '')) != _normal(y_title):
        _issue(report, 'chart_axis_title_missing_or_changed', '图表轴变量或单位未完整保留在原生图表中', page=page)
    series = chart['series']
    equal = chart['type'] == expected['type'] and len(series) == len(expected['series'])
    if equal:
        for found, wanted in zip(series, expected['series']):
            equal = (found['name'] == wanted['name'] and found['categories'] == expected['categories']
                and len(found['values']) == len(wanted['values'])
                and all(Decimal(got) == Decimal(str(want)) for got, want in zip(found['values'], wanted['values'])))
            if not equal:
                break
    if not equal:
        _issue(report, 'chart_data_missing_or_changed', '原生图表类型、分类、系列名称或数值与提交计划不符', page=page)


def _issue(report: dict, code: str, message: str, *, warning=False, **details):
    report['warnings' if warning else 'errors'].append(
        {'code': code, 'message': message, **details})


def _check_embedded_workbook(raw: bytes):
    """只允许图表使用的无宏、无公式、无外部资源的原生数据工作簿。"""
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('图表工作簿超出大小限制')
    with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
        members = workbook.infolist()
        names = [item.filename for item in members]
        if len(members) > 1000 or sum(item.file_size for item in members) > 50 * 1024 * 1024:
            raise ValueError('图表工作簿展开大小超出限制')
        if len(names) != len(set(names)) or 'xl/workbook.xml' not in names:
            raise ValueError('图表工作簿结构无效')
        for item in members:
            name = item.filename
            member = PurePosixPath(name)
            if member.is_absolute() or '..' in member.parts or '\\' in name or ':' in name or item.flag_bits & 1:
                raise ValueError('图表工作簿包含不安全路径或加密文件')
            if ('vba' in name.lower() or name.lower().endswith('.bin')
                    or name.startswith(('xl/embeddings/', 'xl/externalLinks/', 'xl/queryTables/'))
                    or name == 'xl/connections.xml'):
                raise ValueError('图表工作簿包含宏、执行对象或外部链接')
            if name.endswith('.rels'):
                for rel in ET.fromstring(workbook.read(name)):
                    if rel.attrib.get('TargetMode', '').lower() == 'external':
                        raise ValueError('图表工作簿包含外部资源关系')
            elif name.startswith('xl/worksheets/') and name.endswith('.xml'):
                root = ET.fromstring(workbook.read(name))
                if any(element.tag.rsplit('}', 1)[-1] == 'f' for element in root.iter()):
                    raise ValueError('图表工作簿含公式，验收仅打开原生图表的静态数据')
        content_types = workbook.read('[Content_Types].xml').lower()
        if b'macroenabled' in content_types or b'vbaproject' in content_types:
            raise ValueError('图表工作簿声明宏类型')


def _read_package(path: Path, report: dict, *, include_chart_data=False,
                  include_table_data=False, expected_images=None) -> tuple[list[list[str]], list[str]]:
    """不展开 ZIP，读取文字、备注、图片及明确的页面边界问题。"""
    with safe_zip(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('PPTX 包含重复路径')
        content_types = archive.read('[Content_Types].xml').lower()
        if any(kind in content_types for kind in (b'macroenabled', b'vbaproject', b'activex', b'oleobject')):
            raise ValueError('PPTX 声明宏、活动控件或嵌入执行对象')
        chart_workbooks = set()
        chart_names = [name for name in names if re.fullmatch(r'ppt/charts/chart\d+\.xml', name)]
        for chart_name in chart_names:
            chart = ET.fromstring(archive.read(chart_name))
            external = chart.find('c:externalData', NS)
            if external is None:
                continue
            relationship_id = external.attrib.get('{' + NS['r'] + '}id')
            relation_path = chart_name.replace('charts/', 'charts/_rels/') + '.rels'
            if relation_path not in names:
                raise ValueError('原生图表缺少数据工作簿关系')
            relations = [rel for rel in ET.fromstring(archive.read(relation_path))
                         if rel.attrib.get('Id') == relationship_id]
            if len(relations) != 1:
                raise ValueError('原生图表数据工作簿关系不唯一')
            relation = relations[0]
            target = relation.attrib.get('Target', '')
            if (not relation.attrib.get('Type', '').endswith('/package')
                    or relation.attrib.get('TargetMode', '').lower() == 'external'
                    or not re.fullmatch(r'\.\./embeddings/[^/]+\.xlsx', target, re.IGNORECASE)):
                raise ValueError('原生图表只允许包内 XLSX 数据工作簿')
            workbook_name = 'ppt/' + target[3:]
            if workbook_name not in names:
                raise ValueError('原生图表引用缺失的 XLSX 工作簿')
            _check_embedded_workbook(archive.read(workbook_name))
            chart_workbooks.add(workbook_name)
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or '..' in member.parts or '\\' in name or ':' in name:
                raise ValueError('PPTX 包含不安全的包路径')
            if (name.lower().endswith('vbaproject.bin') or name.startswith('ppt/activeX/') or
                    (name.startswith('ppt/embeddings/') and not name.endswith('/') and name not in chart_workbooks)):
                raise ValueError('验收不打开宏或嵌入执行对象')
            if name.endswith('.rels'):
                for rel in ET.fromstring(archive.read(name)):
                    if rel.attrib.get('TargetMode', '').lower() == 'external':
                        raise ValueError('验收不打开含外部资源关系的 PPTX')
                    if rel.attrib.get('Type', '').rsplit('/', 1)[-1].lower() in {'oleobject', 'vbaproject', 'control'}:
                        raise ValueError('验收不打开宏、活动控件或嵌入执行对象')

        slide_names = pptx_slide_paths(archive)
        if not 1 <= len(slide_names) <= MAX_SLIDES:
            raise ValueError(f'验收仅支持 1–{MAX_SLIDES} 页')
        presentation = ET.fromstring(archive.read('ppt/presentation.xml'))
        size = presentation.find('p:sldSz', NS)
        if size is None:
            raise ValueError('PPTX 缺少页面尺寸')
        width, height = int(size.attrib['cx']), int(size.attrib['cy'])
        if width <= 0 or height <= 0 or width > 30 * 914400 or height > 30 * 914400:
            raise ValueError('PPTX 页面尺寸无效')

        texts, notes, text_counts, page_charts, page_tables, page_images = [], [], [], [], [], []
        for page, name in enumerate(slide_names, 1):
            root = ET.fromstring(archive.read(name))
            parts = [part.text or '' for part in root.findall('.//a:t', NS)]
            texts.append([text for text in parts if text.strip()])
            text_counts.append(len(texts[-1]))
            # 部分出界只提示。旋转/组合对象的最终边界由真实 PDF 检查承担。
            for shape in root.findall('p:cSld/p:spTree/p:sp', NS):
                if not shape.findall('.//a:t', NS):
                    continue
                transform = shape.find('p:spPr/a:xfrm', NS)
                if transform is None or transform.attrib.get('rot', '0') != '0':
                    continue
                offset, extent = transform.find('a:off', NS), transform.find('a:ext', NS)
                if offset is None or extent is None:
                    continue
                x, y = int(offset.attrib['x']), int(offset.attrib['y'])
                w, h = int(extent.attrib['cx']), int(extent.attrib['cy'])
                if w <= 0 or h <= 0 or x >= width or y >= height or x + w <= 0 or y + h <= 0:
                    _issue(report, 'text_shape_off_canvas', '文字框完全位于页面外或尺寸无效', page=page)
                elif x < -12700 or y < -12700 or x + w > width + 12700 or y + h > height + 12700:
                    _issue(report, 'text_shape_partial_outside', '文字框部分超出页面，请检查预览', warning=True, page=page)

            rel_name = name.replace('slides/', 'slides/_rels/') + '.rels'
            note_text = ''
            relations = []
            if rel_name in names:
                relations = list(ET.fromstring(archive.read(rel_name)))
                for rel in relations:
                    if not rel.attrib.get('Type', '').endswith('/notesSlide'):
                        continue
                    target = rel.attrib.get('Target', '')
                    if not re.fullmatch(r'\.\./notesSlides/notesSlide\d+\.xml', target):
                        raise ValueError('备注关系路径不支持')
                    note_name = 'ppt/' + target[3:]
                    if note_name not in names:
                        raise ValueError('备注关系指向缺失文件')
                    note_root = ET.fromstring(archive.read(note_name))
                    note_text = '\n'.join(part.text or '' for part in note_root.findall('.//a:t', NS))
            notes.append(note_text)
            charts = []
            if include_chart_data:
                for chart_ref in root.findall('.//c:chart', NS):
                    rid = chart_ref.attrib.get('{' + NS['r'] + '}id')
                    matches = [rel for rel in relations if rel.attrib.get('Id') == rid]
                    if len(matches) != 1 or not matches[0].attrib.get('Type', '').endswith('/chart'):
                        raise ValueError('页面图表关系缺失或不唯一')
                    relation = matches[0]
                    target = relation.attrib.get('Target', '')
                    if relation.attrib.get('TargetMode', '').lower() == 'external' or '\\' in target or ':' in target:
                        raise ValueError('页面图表关系含外部或不安全路径')
                    chart_path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else
                        posixpath.join(posixpath.dirname(name), target))
                    if not re.fullmatch(r'ppt/charts/[^/]+\.xml', chart_path) or chart_path not in names:
                        raise ValueError('页面图表关系指向缺失或不安全部件')
                    charts.append(_native_chart(ET.fromstring(archive.read(chart_path))))
            page_charts.append(charts)
            if include_table_data:
                page_tables.append(_native_tables(root))
            if expected_images is not None:
                page_images.append(_native_images(root, archive, name, relations, width, height)
                                   if page <= len(expected_images) and expected_images[page - 1] is not None else [])

        images = []
        from PIL import Image
        for name in names:
            if not name.startswith('ppt/media/') or name.endswith('/'):
                continue
            try:
                with Image.open(io.BytesIO(archive.read(name))) as image:
                    image_width, image_height = image.size
                    images.append({'package_path': name, 'width': image_width, 'height': image_height})
                    if image_width > 10000 or image_height > 10000:
                        raise RuntimeError('图片尺寸超出安全范围')
                    if image_width < 80 or image_height < 80:
                        _issue(report, 'small_image', '图片尺寸较小，需目视检查科研图可读性', warning=True, package_path=name)
            except (OSError, ValueError):
                images.append({'package_path': name, 'dimensions': 'unavailable'})
                _issue(report, 'image_dimensions_unavailable', '不能直接读取图片尺寸；可能是矢量格式', warning=True, package_path=name)
        report['structure'] = {
            'slide_count': len(slide_names), 'editable_text_runs': sum(text_counts),
            'each_slide_has_editable_text': all(text_counts),
            'notes_count': sum(bool(note.strip()) for note in notes),
            'slide_size_emu': [width, height], 'images': images,
            'editable_chart_count': len(chart_names),
            'checked_chart_workbooks': sorted(chart_workbooks),
        }
        if include_chart_data:
            report['native_chart_data'] = page_charts
        if include_table_data:
            report['native_table_data'] = page_tables
        if expected_images is not None:
            report['planned_image_data'] = page_images
        return texts, notes


def _convert(binary: str, source: Path, directory: Path, timeout: int):
    profile = directory / 'profile'
    profile.mkdir()
    command = [binary, f'-env:UserInstallation={profile.as_uri()}', '--headless',
               '--nologo', '--nodefault', '--norestore', '--nofirststartwizard',
               '--convert-to', 'pdf:impress_pdf_Export', '--outdir', str(directory), str(source)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=os.name == 'posix')
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        stdout, stderr = process.communicate()
    (directory / 'libreoffice.stdout.log').write_bytes(stdout)
    (directory / 'libreoffice.stderr.log').write_bytes(stderr)
    return process.returncode, timed_out


def validate_delivery(pptx_path: str | Path, expected_slides: int,
                      expected_texts=None, expected_sources=None, *,
                      expected_charts=None,
                      expected_tables=None,
                      expected_images=None,
                      expected_visible_sources=None,
                      timeout_seconds: int = 120,
                      validation_root: Path | None = None) -> dict:
    """返回可 JSON 序列化报告，保留真实 PDF/PNG 和失败证据。

    ``expected_texts`` / ``expected_sources`` 为逐页字符串列表。前者检查
    提交内容在 PPTX 与 PDF 中保留；后者仅检查 notes 中的来源字符串保留。
    ``expected_tables`` 对照逐页单元格行列；``expected_images`` 对照目标页
    未裁剪图片的嵌入原字节摘要。二者均不证明科学事实或像素级视觉质量。
    路径或调用参数越界抛出 ValueError；文件/依赖/渲染失败返回 passed=False。
    """
    source = _private(Path(pptx_path))
    if source.suffix.lower() != '.pptx':
        raise ValueError('验收输入必须为 PPTX')
    if type(expected_slides) is not int or not 1 <= expected_slides <= MAX_SLIDES:
        raise ValueError(f'expected_slides 必须为 1–{MAX_SLIDES} 的整数')
    if type(timeout_seconds) is not int or not 10 <= timeout_seconds <= 300:
        raise ValueError('渲染超时须为 10–300 秒的整数')
    expected_texts = _expected(expected_texts, expected_slides, 'expected_texts')
    expected_sources = _expected(expected_sources, expected_slides, 'expected_sources')
    expected_charts = _expected_charts(expected_charts, expected_slides)
    expected_tables = _expected_tables(expected_tables, expected_slides)
    expected_images = _expected_images(expected_images, expected_slides)
    expected_visible_sources = _expected(expected_visible_sources, expected_slides, 'expected_visible_sources')
    directory = _private((validation_root if validation_root is not None else ROOT / '.local/research-ppt/validation') / uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {
        'schema_version': 1, 'validation_id': directory.name, 'passed': False,
        'status': 'failed', 'scope': 'package_render_and_text_integrity_only',
        'scientific_quality': 'not_reviewed', 'human_visual_review_required': True,
        'pptx_path': str(source), 'expected_slides': expected_slides,
        'errors': [], 'warnings': [], 'artifacts': [], 'dependencies': {},
        'report_path': str(directory / 'report.json'),
    }
    try:
        report['pptx_sha256'] = file_hash(source)
        texts, notes = _read_package(source, report, include_chart_data=expected_charts is not None,
                                     include_table_data=expected_tables is not None, expected_images=expected_images)
        structure = report['structure']
        if structure['slide_count'] != expected_slides:
            _issue(report, 'slide_count_mismatch', 'PPTX 页数不符合提交计划')
        if not structure['each_slide_has_editable_text']:
            _issue(report, 'editable_text_missing', '部分页面没有原生可编辑文字')
        if structure['notes_count'] != expected_slides:
            _issue(report, 'notes_missing', '部分页面缺少讲者备注或来源')
        submitted = expected_texts if expected_texts is not None else texts
        report['text_retention'] = {'mode': 'submitted_plan' if expected_texts is not None else 'pptx_native_text', 'pages': []}
        if expected_charts is not None:
            report['chart_retention'] = {'scope': 'native_cached_data_and_rendered_labels_not_scientific_truth', 'pages': []}
            for index, expected_chart in enumerate(expected_charts):
                found = report['native_chart_data'][index] if index < len(report['native_chart_data']) else []
                _check_chart_plan(found, expected_chart, report, index + 1)
                report['chart_retention']['pages'].append({'page': index + 1,
                    'expected_chart': expected_chart is not None, 'native_chart_count': len(found)})
        if expected_tables is not None:
            report['table_retention'] = {'scope': 'native_positional_cells_not_scientific_truth', 'pages': []}
            for index, expected_table in enumerate(expected_tables):
                found = report['native_table_data'][index] if index < len(report['native_table_data']) else []
                _check_table_plan(found, expected_table, report, index + 1)
                report['table_retention']['pages'].append({'page': index + 1,
                    'expected_table': expected_table is not None, 'native_table_count': len(found)})
        if expected_images is not None:
            report['image_retention'] = {'scope': 'target_page_uncropped_embedded_bytes_not_scientific_truth', 'pages': []}
            for index, expected_image in enumerate(expected_images):
                found = report['planned_image_data'][index] if index < len(report['planned_image_data']) else []
                _check_image_plan(found, expected_image, report, index + 1)
                report['image_retention']['pages'].append({'page': index + 1,
                    'expected_image': expected_image is not None, 'verified_image_count': len(found)})
        for index, expected in enumerate(submitted):
            pptx_text = '\n'.join(texts[index]) if index < len(texts) else ''
            missing = _missing_texts(expected, pptx_text)
            if missing:
                _issue(report, 'submitted_text_missing_in_pptx', '提交文字未完整保留在可编辑 PPTX 中', page=index + 1, missing_count=len(missing))
            if expected_sources is not None:
                note_text = _normal(notes[index]) if index < len(notes) else ''
                missing_sources = [text for text in expected_sources[index] if _normal(text) not in note_text]
                if missing_sources:
                    _issue(report, 'source_notes_missing', '提交的来源标识未完整保留在备注中', page=index + 1, missing_count=len(missing_sources))

        binary = shutil.which('libreoffice') or shutil.which('soffice')
        if binary is None:
            _issue(report, 'libreoffice_missing', '缺少 LibreOffice，无法执行真实渲染；不以结构检查代替')
            return _finish(report, directory, started)
        try:
            import fitz
        except ImportError:
            _issue(report, 'pymupdf_missing', '缺少 PyMuPDF，无法检查真实 PDF 或生成预览')
            return _finish(report, directory, started)
        report['dependencies']['libreoffice_binary'] = binary
        report['dependencies']['pymupdf'] = importlib.metadata.version('PyMuPDF')
        version = subprocess.run([binary, '--version'], capture_output=True, timeout=10)
        report['dependencies']['libreoffice_version'] = version.stdout.decode('utf-8', errors='replace').strip()[:200]
        returncode, timed_out = _convert(binary, source, directory, timeout_seconds)
        if timed_out:
            _issue(report, 'render_timeout', '真实渲染超时，已停止进程；失败产物保留')
            return _finish(report, directory, started)
        if returncode:
            _issue(report, 'render_failed', 'LibreOffice 渲染失败，详见本次运行日志', returncode=returncode)
            return _finish(report, directory, started)
        pdf_path = directory / (source.stem + '.pdf')
        if not pdf_path.is_file() or not pdf_path.stat().st_size:
            _issue(report, 'render_pdf_missing', 'LibreOffice 未产生有效 PDF')
            return _finish(report, directory, started)
        report['artifacts'].append({'kind': 'pdf', 'path': str(pdf_path), 'sha256': file_hash(pdf_path)})
        report['pdf_geometry'] = {'tolerance_points': 1.0, 'pages': []}
        report['rendered_glyphs'] = {'scope': 'painted_cjk_coverage_and_notdef_not_full_visual_quality', 'pages': []}
        if expected_visible_sources is not None:
            report['scientific_footer_geometry'] = {'scope': 'painted_body_vs_source_footer_only', 'pages': []}
        with fitz.open(pdf_path) as document:
            report['pdf_page_count'] = document.page_count
            if document.page_count != expected_slides:
                _issue(report, 'pdf_page_count_mismatch', '实际渲染 PDF 页数不符合提交计划')
            if not 1 <= document.page_count <= MAX_SLIDES:
                raise ValueError('实际渲染页数超出安全范围')
            for index, page in enumerate(document):
                if page.rect.width > 2160 or page.rect.height > 2160:
                    raise ValueError('PDF 页面尺寸超出预览安全范围')
                actual = page.get_text('text')
                wanted = list(submitted[index]) if index < len(submitted) else []
                if expected_charts is not None and index < len(expected_charts) and expected_charts[index] is not None:
                    wanted.extend(_chart_visible_texts(expected_charts[index]))
                missing = _missing_texts(wanted, actual)
                report['text_retention']['pages'].append({'page': index + 1, 'expected_items': len(wanted), 'missing_items': len(missing), 'pdf_text_chars': len(_normal(actual))})
                if missing:
                    _issue(report, 'text_missing_in_render', '部分提交文字未出现在真实渲染 PDF 中，可能被裁切或字体渲染异常', page=index + 1, missing_count=len(missing))
                report['rendered_glyphs']['pages'].append(_check_rendered_glyphs(page, wanted, report, index + 1))
                if expected_visible_sources is not None:
                    report['scientific_footer_geometry']['pages'].append(_check_scientific_footer(
                        page, expected_visible_sources[index] if index < len(expected_visible_sources) else [], report, index + 1))
                outside = []
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines', []):
                        for span in line.get('spans', []):
                            if not span.get('text', '').strip():
                                continue
                            x0, y0, x1, y1 = span['bbox']
                            if x0 < -1 or y0 < -1 or x1 > page.rect.width + 1 or y1 > page.rect.height + 1:
                                outside.append([round(n, 2) for n in span['bbox']])
                report['pdf_geometry']['pages'].append({'page': index + 1, 'size_points': [round(page.rect.width, 2), round(page.rect.height, 2)], 'outside_text_spans': outside})
                if outside:
                    _issue(report, 'render_text_outside_page', '实际 PDF 文字边界超出页面，请检查预览', warning=True, page=index + 1, span_count=len(outside))
                image_path = directory / f'slide-{index + 1:02d}.png'
                page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(image_path)
                report['artifacts'].append({'kind': 'preview', 'page': index + 1, 'path': str(image_path), 'sha256': file_hash(image_path)})
        if file_hash(source) != report['pptx_sha256']:
            _issue(report, 'pptx_changed_during_validation', '验收期间 PPTX 版本变化，请重新生成并核验')
    except Exception as exc:
        _issue(report, 'validation_failed', str(exc)[:1000])
    return _finish(report, directory, started)


def _finish(report: dict, directory: Path, started: float) -> dict:
    report['passed'] = not report['errors']
    report['status'] = 'passed' if report['passed'] else 'failed'
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    report['libreoffice_log_paths'] = [str(path) for path in directory.glob('libreoffice.*.log')]
    (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
