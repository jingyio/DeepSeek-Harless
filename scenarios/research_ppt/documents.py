"""受限的 PDF/PPTX 读取。外部场景工具依赖与 Harness 在线控制分开。"""
from __future__ import annotations
import base64
import hashlib
import io
import math
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from defusedxml import ElementTree as ET

MAX_BYTES = 30 * 1024 * 1024
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PACKAGE_R = 'http://schemas.openxmlformats.org/package/2006/relationships'


def file_hash(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('输入必须是小于 30 MiB 的文件')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_zip(path: Path):
    archive = zipfile.ZipFile(path)
    infos = archive.infolist()
    if len(infos) > 5000 or sum(i.file_size for i in infos) > 150 * 1024 * 1024:
        archive.close()
        raise ValueError('PPTX 展开大小超出限制')
    return archive


def pptx_slide_paths(archive: zipfile.ZipFile) -> list[str]:
    """Return slides in presentation order, including hidden slides.

    Slide part numbers are package identities, not page numbers. Unreferenced
    slide parts are not pages; ambiguous or unsafe presentation relationships
    are rejected instead of falling back to filename order.
    """
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('PPTX 包含重复路径')
    for name in names:
        member = PurePosixPath(name)
        if member.is_absolute() or '..' in member.parts or '\\' in name or ':' in name:
            raise ValueError('PPTX 包含不安全的包路径')
    try:
        presentation = ET.fromstring(archive.read('ppt/presentation.xml'))
        relations = ET.fromstring(archive.read('ppt/_rels/presentation.xml.rels'))
    except (KeyError, ET.ParseError) as error:
        raise ValueError('PPTX 缺少合法的幻灯片顺序或关联') from error
    items = presentation.find('{' + P + '}sldIdLst')
    if (presentation.tag != '{' + P + '}presentation' or items is None or
            relations.tag != '{' + PACKAGE_R + '}Relationships'):
        raise ValueError('PPTX 缺少合法的幻灯片顺序或关联')
    by_id = {}
    for relation in relations:
        identifier = relation.get('Id')
        if (relation.tag != '{' + PACKAGE_R + '}Relationship' or not identifier or
                identifier in by_id):
            raise ValueError('PPTX 幻灯片关联无效或不唯一')
        by_id[identifier] = relation
    slides, identifiers, relationship_ids = [], set(), set()
    for item in items:
        identifier = item.get('id')
        relationship_id = item.get('{' + R + '}id')
        relation = by_id.get(relationship_id)
        if (item.tag != '{' + P + '}sldId' or not identifier or not identifier.isdecimal() or
                identifier in identifiers or relationship_id in relationship_ids or relation is None or
                not relation.get('Type', '').endswith('/slide') or
                relation.get('TargetMode', 'Internal').lower() != 'internal'):
            raise ValueError('PPTX 幻灯片关联无效或不唯一')
        target = unquote(relation.get('Target', ''))
        if (not target or target.startswith('//') or any(value in target for value in ('\\', ':', '?', '#')) or
                re.search(r'[\x00-\x1f]', target)):
            raise ValueError('PPTX 幻灯片关联路径不安全')
        target = posixpath.normpath(target.lstrip('/') if target.startswith('/')
                                   else posixpath.join('ppt', target))
        member = PurePosixPath(target)
        if (member.parent != PurePosixPath('ppt/slides') or member.suffix != '.xml' or
                target not in names):
            raise ValueError('PPTX 幻灯片关联路径不支持或文件缺失')
        identifiers.add(identifier)
        relationship_ids.add(relationship_id)
        slides.append(target)
    if not 1 <= len(slides) <= 200 or len(slides) != len(set(slides)):
        raise ValueError('PPTX 幻灯片顺序重复或页数超出 1–200 页')
    return slides


def clean_text(text: str) -> str:
    """Remove characters that JSON/PPTX text runs cannot safely carry."""
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', ' ', text)


def image_record(raw: bytes, image_id: str, page: int) -> dict | None:
    from PIL import Image
    if len(raw) > 8 * 1024 * 1024:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.width > 10000 or img.height > 10000 or img.width < 80 or img.height < 80:
                return None
            # Flatten alpha against the actual white presentation background;
            # convert('RGB') alone exposes arbitrary RGB under transparent pixels.
            if img.mode in {'RGBA', 'LA'} or 'transparency' in img.info:
                rgba = img.convert('RGBA')
                img = Image.alpha_composite(Image.new('RGBA', img.size, (255,255,255,255)), rgba).convert('RGB')
            else:
                img = img.convert('RGB')
            img.thumbnail((1800, 1800))
            probe = img.resize((min(128,img.width), min(128,img.height)))
            count = probe.width * probe.height
            colors = probe.getcolors(count) or []
            dominant = max((number for number,_ in colors), default=0) / count
            rgb_range = max(high-low for low,high in probe.getextrema())
            if rgb_range <= 2 or dominant >= 0.995:
                return None
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            if buf.tell() > 8 * 1024 * 1024:
                return None
            return {'image_id': image_id, 'page': page, 'width': img.width, 'height': img.height,
                    'pixel_check': {'rgb_range':rgb_range,'dominant_sample_fraction':round(dominant,6),
                                    'scope':'nonblank_pixels_only_not_scientific_validation'},
                    'data': 'image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')}
    except (OSError, ValueError):
        return None


def pdf_page_geometry(path: Path, page_number: int, version_sha256: str) -> dict:
    """Conservative caption/graphics candidates, not a complete figure detector.

    A caption alone never authorizes a crop. Only visible-page drawing/image
    geometry above it is considered; prose crossing a crop causes abstention.
    """
    import fitz
    if file_hash(path) != version_sha256:
        raise ValueError('输入版本已变化，请重新准备任务')
    with fitz.open(path) as pdf:
        if type(page_number) is not int or not 1 <= page_number <= len(pdf):
            raise ValueError('论文页码越界')
        sheet = pdf[page_number - 1]
        bounds = sheet.rect
        width, height = bounds.width, bounds.height
        blocks = sheet.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']
        texts = [{'rect': fitz.Rect(block['bbox']),
                  'text': clean_text('\n'.join(''.join(span['text'] for span in line['spans'])
                                             for line in block['lines']))}
                 for block in blocks if block['type'] == 0]
        captions = [block for block in texts if re.match(
            r'^\s*(?:Figure|Fig\.?|图)\s*\d+[A-Za-z]?\s*[:：.]', block['text'], re.I)]
        drawings = sheet.get_drawings()
        if len(drawings) > 5000 or len(captions) > 30:
            return {'geometry_version': 2, 'figure_candidates': [], 'figure_localization': 'abstained',
                    'geometry_warnings': ['页面图形数量超出受限定位范围；请核对原页。']}
        visuals, oversized = [], []
        for kind, rect in [('embedded_image', fitz.Rect(row['bbox'])) for row in sheet.get_image_info()] + [
                ('vector_graphic', fitz.Rect(row['rect'])) for row in drawings]:
            # Out-of-page paths may be clipped or invisible; including them can
            # swallow unrelated prose. Reject rather than assume their visibility.
            if (not all(math.isfinite(x) for x in rect) or not bounds.contains(rect)
                    or rect.width < 3 or rect.height < 3):
                continue
            if rect.get_area() > width * height * 0.30:
                oversized.append(rect)
                continue
            visuals.append((kind, rect))

        def normalized(rect):
            return [round(rect.x0 / width, 6), round(rect.y0 / height, 6),
                    round(rect.x1 / width, 6), round(rect.y1 / height, 6)]

        candidates, rejected = [], []
        for cap in captions:
            caption = cap['rect']
            # PDF text extraction may join two side-by-side captions into one
            # block. Such a block is not evidence that both panels share one
            # figure identity; do not silently merge independent figures.
            if len(re.findall(r'(?<![\w])(?:Figure|Fig\.?|图)\s*\d+[A-Za-z]?\s*[:：.]',
                              cap['text'], re.I | re.M)) > 1:
                rejected.append({'caption': cap['text'][:600], 'caption_bbox': normalized(caption),
                                 'reason': '同一文本块包含多个独立图注，无法确认图件归属'})
                continue
            # Caption text is an anchor, not the horizontal extent of a figure.
            # First find reliable graphics in its column, then include aligned
            # neighboring panels. A short caption must never cut off the right
            # column of a composite figure.
            left, right = max(0, caption.x0 - 18), min(width, caption.x1 + 18)
            top = max(0, caption.y0 - height * 0.50)
            for block in texts:
                rect = block['rect']
                overlap = max(0, min(rect.x1, right) - max(rect.x0, left))
                if (block is not cap and len(block['text']) > 120 and rect.y1 <= caption.y0
                        and overlap > min(rect.width, right - left) * 0.5):
                    top = max(top, rect.y1 + 2)
            for previous in captions:
                rect = previous['rect']
                overlap = max(0, min(rect.x1, right) - max(rect.x0, left))
                if (previous is not cap and rect.y1 <= caption.y0 and
                        overlap > min(rect.width, right - left) * 0.5):
                    top = max(top, rect.y1 + 2)
            nearby = [(kind, rect) for kind, rect in visuals
                      if rect.y0 >= top and rect.y1 <= caption.y0 + 2
                      and max(0, min(rect.x1, right) - max(rect.x0, left)) >=
                      min(rect.width, right - left) * 0.6]
            if not nearby or caption.y0 - max(rect.y1 for _, rect in nearby) > 65:
                rejected.append({'caption': cap['text'][:600], 'caption_bbox': normalized(caption),
                                 'reason': '未找到紧邻图注的可靠图形或嵌入图片边界'})
                continue
            visual = fitz.Rect(nearby[0][1])
            for _, rect in nearby[1:]:
                visual |= rect
            # Expand only across aligned graphic panels, with bounded gaps.
            # Distinct captions and prose are checked below before any crop is
            # exposed. Unrelated/ambiguous diagrams therefore remain abstentions.
            selected_rects = {id(rect) for _, rect in nearby}
            for _ in range(8):
                added = []
                for item in visuals:
                    _, rect = item
                    if id(rect) in selected_rects or rect.y0 < top or rect.y1 > caption.y0 + 2:
                        continue
                    vertical = max(0, min(rect.y1, visual.y1) - max(rect.y0, visual.y0))
                    gap = max(0, rect.x0 - visual.x1, visual.x0 - rect.x1)
                    if vertical >= min(rect.height, visual.height) * 0.5 and gap <= width * 0.10:
                        added.append(item)
                if not added:
                    break
                nearby.extend(added)
                for _, rect in added:
                    selected_rects.add(id(rect))
                    visual |= rect
            unresolved_panel = any(
                id(rect) not in selected_rects and rect.y0 >= top and rect.y1 <= caption.y0 + 2 and
                max(0, min(rect.y1, visual.y1) - max(rect.y0, visual.y0)) >=
                min(rect.height, visual.height) * 0.5 and
                max(0, rect.x0 - visual.x1, visual.x0 - rect.x1) <= width * 0.30
                for _, rect in visuals)
            competing = [other for other in captions if other is not cap and
                         other['rect'].y0 >= visual.y0 and other['rect'].y0 <= caption.y0 + 65 and
                         max(0, min(other['rect'].x1, visual.x1) -
                             max(other['rect'].x0, visual.x0)) >
                         min(other['rect'].width, visual.width) * 0.5]
            if (unresolved_panel or competing or
                    any((rect & visual).get_area() > 0 for rect in oversized)):
                rejected.append({'caption': cap['text'][:600], 'caption_bbox': normalized(caption),
                                 'reason': '存在相邻独立图注或超范围图形，无法确认完整图件归属'})
                continue
            if visual.width < 40 or visual.height < 40:
                rejected.append({'caption': cap['text'][:600], 'caption_bbox': normalized(caption),
                                 'reason': '可见图形范围过小，可能只是文字下划线或公式'})
                continue
            crop = visual | caption
            label_left, label_right = max(0, visual.x0 - 24), min(width, visual.x1 + 24)
            # Short diagram labels and headings may lie just outside image paths.
            for block in texts:
                rect = block['rect']
                if (block is not cap and len(block['text']) <= 120
                        and rect.y0 >= visual.y0 - 24 and rect.y1 <= caption.y0
                        and rect.x0 >= label_left and rect.x1 <= label_right):
                    crop |= rect
            crop = (crop + (-4, -4, 4, 4)) & bounds
            if any(block is not cap and len(block['text']) > 120
                   and (block['rect'] & crop).get_area() > block['rect'].get_area() * 0.15
                   for block in texts):
                rejected.append({'caption': cap['text'][:600], 'caption_bbox': normalized(caption),
                                 'reason': '候选区域与正文重叠，无法可靠区分完整图件'})
                continue
            bbox = normalized(crop)
            identity = version_sha256 + ':' + str(page_number) + ':' + cap['text'] + ':' + repr(bbox)
            candidates.append({'candidate_id': 'figure-' + hashlib.sha256(identity.encode()).hexdigest()[:20],
                'page': page_number, 'caption': cap['text'][:1200], 'caption_bbox': normalized(caption),
                'bbox': bbox, 'visual_bbox': normalized(visual),
                'evidence_types': sorted({kind for kind, _ in nearby}),
                'status': 'geometry_candidate', 'semantic_verified': False})
        if file_hash(path) != version_sha256:
            raise ValueError('输入版本已变化，请重新准备任务')
        return {'geometry_version': 2, 'page_size_points': [width, height],
                'figure_candidates': candidates, 'unresolved_captions': rejected,
                'figure_localization': 'candidates_available' if candidates else 'abstained',
                'geometry_warnings': ['图注和图形几何仅用于定位候选；多栏、跨页、无图注或裁剪图件可能漏检，科研含义仍需核对。']}


def parse_document(path: Path) -> dict:
    file_hash(path)
    kind = path.suffix.lower().lstrip('.')
    pages, images, warnings = [], [], []
    if kind == 'pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError('首版不处理加密 PDF')
        if not 1 <= len(reader.pages) <= 200:
            raise ValueError('首版限制 1–200 页')
        for index, page in enumerate(reader.pages, 1):
            text = clean_text(page.extract_text() or '')
            pages.append({'page': index, 'text': text[:30000], 'truncated': len(text) > 30000})
            if len(images) < 12:
                try:
                    for item in list(page.images)[:4]:
                        obj = item.indirect_reference.get_object() if item.indirect_reference else {}
                        if any(key in obj for key in ('/SMask','/Mask','/ImageMask')):
                            # Masked resources can be shadows or fragments of an
                            # assembled figure. A decoded fragment is not a figure.
                            warnings.append(f'第 {index} 页透明/遮罩嵌入素材已隐藏；它可能只是图件片段，请 read_page 后按真实图注几何 extract_figure')
                            continue
                        image = image_record(item.data, f'img_{len(images)+1}', index)
                        if image:
                            image['evidence_scope'] = 'embedded_asset_not_complete_figure'
                            images.append(image)
                        if len(images) >= 12:
                            break
                except Exception:
                    warnings.append(f'第 {index} 页部分图片无法提取')
        warnings.append('仅提取可解码的嵌入图片；矢量图和完整公式布局可能需要原文核对')
    elif kind == 'pptx':
        with safe_zip(path) as z:
            names = pptx_slide_paths(z)
            for index, name in enumerate(names, 1):
                root = ET.fromstring(z.read(name))
                text = clean_text('\n'.join(t.text or '' for t in root.findall('.//a:t', NS)))
                pages.append({'page': index, 'text': text[:30000], 'truncated': len(text) > 30000})
            # 图片按其原始幻灯片关系定位，避免把一个图归到错误页。
            for index, name in enumerate(names, 1):
                rel_path = name.replace('slides/', 'slides/_rels/') + '.rels'
                if rel_path not in z.namelist():
                    continue
                for rel in ET.fromstring(z.read(rel_path)):
                    if rel.attrib.get('TargetMode') == 'External' or not rel.attrib.get('Type', '').endswith('/image'):
                        continue
                    target = rel.attrib.get('Target', '')
                    if not re.fullmatch(r'\.\./media/[^/]+', target):
                        continue
                    image = image_record(z.read('ppt/' + target[3:]), f'img_{len(images)+1}', index)
                    if image:
                        images.append(image)
                    if len(images) >= 12:
                        break
                if len(images) >= 12:
                    break
        warnings.append('PPTX 首版读取文本、表格文字和嵌入图片后重新排版；不保留动画、母版或图表编辑数据')
    else:
        raise ValueError('首版只接收 PDF/PPTX')
    text_chars = sum(len(p['text'].strip()) for p in pages)
    if not text_chars:
        warnings.append('未提取到文本，可能是扫描文件；首版不执行 OCR')
    return {'format': kind, 'page_count': len(pages), 'text_chars': text_chars,
            'pages': pages, 'images': images, 'warnings': warnings}


def inspect_pptx(path: Path) -> dict:
    with safe_zip(path) as z:
        slides = pptx_slide_paths(z)
        text_counts = [len(ET.fromstring(z.read(n)).findall('.//a:t', NS)) for n in slides]
        notes = [n for n in z.namelist() if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', n)]
        return {'slide_count': len(slides), 'editable_text_runs': sum(text_counts),
                'each_slide_has_editable_text': bool(slides) and all(text_counts),
                'notes_count': len(notes), 'file_sha256': file_hash(path),
                'scope': 'package_and_editability_checks; visual_and_scientific_quality_not_certified'}
