"""本场景生成 PPT 的局部修订：显式字段合并与真实 OOXML 保持核验。

不编辑任意用户母版。工具调用者仍须验证来源权限，并对新文件完成真实渲染。
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from .documents import safe_zip


SLIDE_FIELDS = frozenset({'title', 'bullets', 'sources', 'notes', 'image', 'table',
                         'chart', 'layout', 'comparison', 'process', 'takeaway'})
REMOVABLE_FIELDS = frozenset({'image', 'table', 'chart', 'layout', 'comparison',
                             'process', 'takeaway'})
LAYOUTS = frozenset({'title', 'content', 'image', 'table', 'chart', 'section',
                     'comparison', 'process'})
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
TIME_FIELDS = {'{http://purl.org/dc/terms/}created', '{http://purl.org/dc/terms/}modified'}


def _text(value, *, empty=False):
    return (isinstance(value, str) and (empty or bool(value.strip())) and
            not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', value))


def _object(value, required, optional=()):
    return (isinstance(value, dict) and set(required) <= set(value) and
            not set(value) - set(required) - set(optional))


def _strings(value):
    return isinstance(value, list) and all(_text(item) for item in value)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _validate_field(key, value):
    valid = False
    if key in {'title', 'takeaway'}:
        valid = _text(value)
    elif key == 'notes':
        valid = _text(value, empty=True)
    elif key == 'bullets':
        valid = _strings(value)
    elif key == 'sources':
        valid = isinstance(value, list) and bool(value) and all(
            _text(item) or (_object(item, {'source_id', 'page'}) and
                            _text(item['source_id']) and type(item['page']) is int and
                            item['page'] >= 1) for item in value)
    elif key == 'layout':
        valid = isinstance(value, str) and value in LAYOUTS
    elif key == 'image':
        valid = ((_object(value, {'source_id', 'image_id'}) and
                  _text(value['source_id']) and _text(value['image_id'])) or
                 (_object(value, {'data', 'width', 'height'}) and
                  _text(value['data']) and _number(value['width']) and
                  _number(value['height']) and value['width'] > 0 and value['height'] > 0))
    elif key == 'table':
        valid = (isinstance(value, list) and len(value) >= 2 and
                 all(_strings(row) and bool(row) for row in value) and
                 len({len(row) for row in value}) == 1)
    elif key == 'chart':
        valid = (_object(value, {'type', 'categories', 'series'}, {'x_label', 'y_label', 'unit'}) and
                 value['type'] in ('bar', 'line') and _strings(value['categories']) and
                 len(value['categories']) >= 2 and
                 len(set(value['categories'])) == len(value['categories']) and
                 isinstance(value['series'], list) and bool(value['series']) and
                 all(_object(series, {'name', 'values'}) and _text(series['name']) and
                     isinstance(series['values'], list) and
                     len(series['values']) == len(value['categories']) and
                     all(_number(number) for number in series['values'])
                     for series in value['series']) and
                 all(_text(value[field]) for field in ('x_label', 'y_label', 'unit') if field in value))
    elif key == 'comparison':
        valid = (_object(value, {'left', 'right'}) and all(
            _object(value[side], {'title', 'bullets'}) and
            _text(value[side]['title']) and _strings(value[side]['bullets'])
            for side in ('left', 'right')))
    elif key == 'process':
        valid = (_object(value, {'steps'}) and isinstance(value['steps'], list) and
                 2 <= len(value['steps']) <= 5 and all(
                     _object(step, {'label', 'detail'}) and _text(step['label']) and _text(step['detail'])
                     for step in value['steps']))
    if not valid:
        raise ValueError(f'修订字段 {key} 的类型或结构无效')


def _validate_slide(slide):
    if not _object(slide, {'title', 'bullets', 'sources'}, SLIDE_FIELDS):
        raise ValueError('幻灯片必须包含 title/bullets/sources，且不能有未知字段')
    for key, value in slide.items():
        _validate_field(key, value)


def merge_slide_updates(plan: dict, updates: list[dict]) -> dict:
    """深复制 plan；updates=[{page: 1, changes: {...}}] 仅替换显式字段。

    sources/notes 未出现时原样保留。可选布局/媒体字段只有显式传 null 才移除；
    完整渲染器负责容量和布局一致性检查，不自动删掉旧媒体来适配新 layout。
    """
    if (not _object(plan, {'title', 'slides'}, {'template', 'layout_policy'}) or
            not _text(plan['title']) or not isinstance(plan['slides'], list) or
            not 1 <= len(plan['slides']) <= 30):
        raise ValueError('局部修订需要已有完整的生成计划')
    if 'template' in plan and plan['template'] not in ('academic', 'lab'):
        raise ValueError('模板无效')
    if 'layout_policy' in plan and not isinstance(plan['layout_policy'], dict):
        raise ValueError('布局策略类型无效')
    for slide in plan['slides']:
        _validate_slide(slide)
    if not isinstance(updates, list) or not updates:
        raise ValueError('updates 必须是非空列表')
    revised = copy.deepcopy(plan)
    seen = set()
    for update in updates:
        if not _object(update, {'page', 'changes'}):
            raise ValueError('每项修订仅接受 page 和 changes')
        page, changes = update['page'], update['changes']
        if type(page) is not int or not 1 <= page <= len(plan['slides']):
            raise ValueError('修订页码必须是有效的 1-based 整数')
        if page in seen:
            raise ValueError('修订页码重复')
        seen.add(page)
        if not isinstance(changes, dict) or not changes or set(changes) - SLIDE_FIELDS:
            raise ValueError('changes 必须包含合法的幻灯片字段，不能有未知字段')
        for key, value in changes.items():
            if value is None and key in REMOVABLE_FIELDS:
                revised['slides'][page - 1].pop(key, None)
            else:
                _validate_field(key, value)
                revised['slides'][page - 1][key] = copy.deepcopy(value)
        _validate_slide(revised['slides'][page - 1])
    return revised


def _xml(raw):
    if re.search(br'<!\s*(DOCTYPE|ENTITY)\b', raw, re.I):
        raise ValueError('OOXML 不接受 DTD/实体声明')
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise ValueError('PPTX 中的 XML 无效') from None


def _canonical(element, relationships=None):
    """保留全部属性、文本、子节点顺序，仅忽略格式化缩进与命名空间前缀。"""
    attributes = []
    for key, value in element.attrib.items():
        if key.startswith('{' + R + '}') and relationships is not None:
            if value not in relationships:
                raise ValueError('OOXML 引用了缺失的 relationship')
            value = relationships[value]
        attributes.append((key, value))
    text = element.text or ''
    if not text.strip() and element.tag not in {
            '{http://schemas.openxmlformats.org/drawingml/2006/main}t',
            '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'}:
        text = ''
    return [element.tag, sorted(attributes), text,
            [_canonical(child, relationships) for child in element],
            element.tail if element.tail and element.tail.strip() else '']


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _target(source, target):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or '\\' in target:
        raise ValueError('OOXML 包含外部或不支持的关联目标')
    decoded = unquote(parsed.path)
    destination = posixpath.normpath(decoded.lstrip('/') if decoded.startswith('/') else
                                     posixpath.join(posixpath.dirname(source), decoded))
    if destination in ('', '.', '..') or destination.startswith('../'):
        raise ValueError('OOXML 关联目标越界')
    return destination


class _Package:
    def __init__(self, archive):
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        if len(names) != len(set(names)) or any(
                name.startswith('/') or '\\' in name or posixpath.normpath(name) != name or
                name == '..' or name.startswith('../') for name in names):
            raise ValueError('PPTX 包条目重复或路径无效')
        self.parts = {name: archive.read(name) for name in names}
        self.rels = {}
        for name, raw in self.parts.items():
            if not name.endswith('.rels'):
                continue
            parent, filename = posixpath.split(name)
            if posixpath.basename(parent) != '_rels':
                raise ValueError('OOXML relationships 路径无效')
            source = posixpath.join(posixpath.dirname(parent), filename[:-5])
            relationships = {}
            root = _xml(raw)
            if root.tag != '{' + PKG + '}Relationships':
                raise ValueError('OOXML relationships 命名空间无效')
            for rel in root:
                if (rel.tag != '{' + PKG + '}Relationship' or
                        not {'Id', 'Type', 'Target'} <= set(rel.attrib) or
                        set(rel.attrib) - {'Id', 'Type', 'Target', 'TargetMode'} or
                        rel.get('TargetMode', 'Internal') != 'Internal'):
                    raise ValueError('OOXML 不接受外部或无效 relationship')
                rid, kind = rel.get('Id'), rel.get('Type')
                if not rid or not kind or rid in relationships:
                    raise ValueError('OOXML relationship ID 无效或重复')
                destination = _target(source, rel.get('Target'))
                if destination not in self.parts:
                    raise ValueError('OOXML 关联资源缺失')
                relationships[rid] = (kind, destination)
            self.rels[source] = relationships
        if '[Content_Types].xml' not in self.parts:
            raise ValueError('PPTX 缺少 Content Types')
        self.overrides, self.defaults = {}, {}
        types = _xml(self.parts['[Content_Types].xml'])
        if types.tag != '{' + CT + '}Types':
            raise ValueError('PPTX Content Types 命名空间无效')
        for entry in types:
            if entry.tag == '{' + CT + '}Override':
                name = entry.get('PartName', '').lstrip('/')
                if (set(entry.attrib) != {'PartName', 'ContentType'} or not name or
                        not entry.get('ContentType') or name in self.overrides):
                    raise ValueError('PPTX Content Type 重复或无效')
                self.overrides[name] = entry.get('ContentType')
            elif entry.tag == '{' + CT + '}Default':
                extension = entry.get('Extension')
                if (set(entry.attrib) != {'Extension', 'ContentType'} or not extension or
                        not entry.get('ContentType') or extension in self.defaults):
                    raise ValueError('PPTX Content Type 重复或无效')
                self.defaults[extension] = entry.get('ContentType')
            else:
                raise ValueError('PPTX Content Type 条目无效')

    def content_type(self, name):
        return self.overrides.get(name, self.defaults.get(name.rsplit('.', 1)[-1], ''))

    def slides(self):
        name = 'ppt/presentation.xml'
        if name not in self.parts:
            raise ValueError('PPTX 缺少 presentation')
        root = _xml(self.parts[name])
        items = root.find('{' + P + '}sldIdLst')
        if root.tag != '{' + P + '}presentation' or items is None:
            raise ValueError('PPTX 缺少合法的幻灯片顺序')
        slides, identifiers = [], set()
        for item in items:
            rel = self.rels.get(name, {}).get(item.get('{' + R + '}id'))
            identifier = item.get('id')
            if (item.tag != '{' + P + '}sldId' or rel is None or not rel[0].endswith('/slide') or
                    not identifier or not identifier.isdecimal() or identifier in identifiers):
                raise ValueError('PPTX 幻灯片关联无效')
            identifiers.add(identifier)
            slides.append(rel[1])
        if not slides or len(slides) != len(set(slides)):
            raise ValueError('PPTX 幻灯片顺序重复或为空')
        return slides

    def _binary(self, name):
        raw = self.parts[name]
        if not name.lower().endswith('.xlsx'):
            return {'sha256': hashlib.sha256(raw).hexdigest()}
        # PptxGenJS 每次重建 workbook 会写新的创建/修改时间；它不是数据变化。
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if (len(archive.infolist()) > 5000 or
                        sum(info.file_size for info in archive.infolist()) > 150 * 1024 * 1024):
                    raise ValueError('嵌入 workbook 展开大小超限')
                workbook = _Package(archive)
        except zipfile.BadZipFile:
            raise ValueError('嵌入 workbook 无效') from None
        items = []
        for path, content in sorted(workbook.parts.items()):
            if path.endswith(('.xml', '.rels')):
                root = _xml(content)
                if path == 'docProps/core.xml':
                    for element in list(root):
                        if element.tag in TIME_FIELDS:
                            root.remove(element)
                value = _canonical(root)
            else:
                value = {'sha256': hashlib.sha256(content).hexdigest()}
            items.append([path, value])
        return {'workbook_parts': items}

    def snapshot(self, start, *, global_presentation=False):
        nodes, indices = [], {}

        def visit(name):
            if name in indices:
                return indices[name]
            index = len(nodes)
            indices[name] = index
            node = {'content_type': self.content_type(name)}
            nodes.append(node)
            relationships = dict(self.rels.get(name, {}))
            root = _xml(self.parts[name]) if name.endswith('.xml') else None
            if global_presentation and name == start:
                # 页序另行核验；共享母版、全局字号/尺寸和其他依赖仍纳入核验。
                for child in list(root):
                    if child.tag == '{' + P + '}sldIdLst':
                        root.remove(child)
                relationships = {rid: rel for rid, rel in relationships.items()
                                 if not rel[0].endswith('/slide')}
            referenced = []
            if root is not None:
                for element in root.iter():
                    for key, rid in sorted(element.attrib.items()):
                        if key.startswith('{' + R + '}') and rid not in referenced:
                            if rid not in relationships:
                                raise ValueError('OOXML 引用了缺失的 relationship')
                            referenced.append(rid)

            def order_key(rid):
                kind, target = relationships[rid]
                raw = self.parts[target]
                if target.endswith('.xml'):
                    element = _xml(raw)
                    placeholders = {value: 'relationship' for item in element.iter()
                                    for key, value in item.attrib.items() if key.startswith('{' + R + '}')}
                    local = _digest(_canonical(element, placeholders))
                else:
                    local = _digest(self._binary(target))
                return kind, local

            ordered = referenced + sorted(set(relationships) - set(referenced), key=order_key)
            labels = {rid: f'relationship-{number}' for number, rid in enumerate(ordered)}
            node['value'] = _canonical(root, labels) if root is not None else self._binary(name)
            node['relationships'] = [[relationships[rid][0], visit(relationships[rid][1])]
                                     for rid in ordered]
            return index

        visit(start)
        return nodes


def verify_unmodified_slides(before_pptx, after_pptx, changed_pages) -> dict:
    """按真实页序核验非目标页及其 notes/媒体/图表/workbook/母版依赖。

    资源文件名和 relationship ID 可重新编号；XML 实际结构、样式、几何、
    文本与二进制媒体必须保持。ZIP 时间戳及 workbook 的 created/modified
    元数据不参与比较。任何不一致抛 ValueError，不能只返回失败后继续交付。
    """
    if not isinstance(changed_pages, (list, tuple, set, frozenset)) or not changed_pages:
        raise ValueError('changed_pages 必须是非空页码集合')
    pages = list(changed_pages)
    if any(type(page) is not int for page in pages) or len(pages) != len(set(pages)):
        raise ValueError('changed_pages 页码类型无效或重复')
    try:
        with safe_zip(Path(before_pptx)) as archive:
            before = _Package(archive)
        with safe_zip(Path(after_pptx)) as archive:
            after = _Package(archive)
    except (OSError, zipfile.BadZipFile):
        raise ValueError('局部修订核验需要两份真实可读的 PPTX') from None
    original, revised = before.slides(), after.slides()
    if len(original) != len(revised):
        raise ValueError('局部修订改变了总页数，拒绝交付')
    if any(not 1 <= page <= len(original) for page in pages):
        raise ValueError('changed_pages 页码越界')
    if before.snapshot('ppt/presentation.xml', global_presentation=True) != after.snapshot(
            'ppt/presentation.xml', global_presentation=True):
        raise ValueError('局部修订改变了共享母版、全局样式或尺寸，拒绝交付')
    audit = []
    for page, (old, new) in enumerate(zip(original, revised), 1):
        if page in pages:
            continue
        first, second = before.snapshot(old), after.snapshot(new)
        if first != second:
            raise ValueError(f'局部修订改变了非目标第 {page} 页的 OOXML 或关联资源，拒绝交付')
        audit.append({'page': page, 'semantic_sha256': _digest(first),
                      'dependency_parts': len(first)})
    return {'passed': True, 'slide_count': len(original), 'changed_pages': sorted(pages),
            'checked_pages': [item['page'] for item in audit], 'page_evidence': audit,
            'non_target_slides_preserved': True, 'shared_styles_preserved': True,
            'checks': ['slide_xml_text_geometry_tables', 'notes', 'media_bytes',
                       'chart_xml_and_embedded_workbook', 'relationship_graph', 'masters_and_themes'],
            'normalization': ['zip_container_timestamps', 'relationship_and_part_numbering',
                              'embedded_workbook_created_modified_metadata'],
            'scope': '仅本场景从保存计划生成的 PPT；科研事实与真实 PDF/PNG 仍须另行验收'}
