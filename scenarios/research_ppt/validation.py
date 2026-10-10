"""真实 PPTX 渲染与交付完整性检查；不认证科研结论，不改写内容。"""
from __future__ import annotations

import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import time
import unicodedata
from uuid import uuid4
import zipfile

from defusedxml import ElementTree as ET

from .documents import file_hash, safe_zip

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


def _expected(value, count: int, name: str):
    if value is None:
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != count
            or any(not isinstance(row, (list, tuple)) or len(row) > 300 for row in value)
            or any(not isinstance(text, str) or len(text) > 10000
                   for row in value for text in row)):
        raise ValueError(f'{name} 需要与页数一致的逐页字符串列表')
    return [[text for text in row if text.strip()] for row in value]


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


def _read_package(path: Path, report: dict) -> tuple[list[list[str]], list[str]]:
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

        slide_names = sorted(
            (name for name in names if re.fullmatch(r'ppt/slides/slide\d+\.xml', name)),
            key=lambda name: int(re.search(r'(\d+)\.xml$', name).group(1)),
        )
        if not 1 <= len(slide_names) <= MAX_SLIDES:
            raise ValueError(f'验收仅支持 1–{MAX_SLIDES} 页')
        presentation = ET.fromstring(archive.read('ppt/presentation.xml'))
        size = presentation.find('p:sldSz', NS)
        if size is None:
            raise ValueError('PPTX 缺少页面尺寸')
        width, height = int(size.attrib['cx']), int(size.attrib['cy'])
        if width <= 0 or height <= 0 or width > 30 * 914400 or height > 30 * 914400:
            raise ValueError('PPTX 页面尺寸无效')

        texts, notes, text_counts = [], [], []
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
            if rel_name in names:
                for rel in ET.fromstring(archive.read(rel_name)):
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
                      timeout_seconds: int = 120) -> dict:
    """返回可 JSON 序列化报告，保留真实 PDF/PNG 和失败证据。

    ``expected_texts`` / ``expected_sources`` 为逐页字符串列表。前者检查
    提交内容在 PPTX 与 PDF 中保留；后者仅检查 notes 中的来源字符串保留。
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
    directory = _private(ROOT / '.local/research-ppt/validation' / uuid4().hex)
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
        texts, notes = _read_package(source, report)
        structure = report['structure']
        if structure['slide_count'] != expected_slides:
            _issue(report, 'slide_count_mismatch', 'PPTX 页数不符合提交计划')
        if not structure['each_slide_has_editable_text']:
            _issue(report, 'editable_text_missing', '部分页面没有原生可编辑文字')
        if structure['notes_count'] != expected_slides:
            _issue(report, 'notes_missing', '部分页面缺少讲者备注或来源')
        submitted = expected_texts if expected_texts is not None else texts
        report['text_retention'] = {'mode': 'submitted_plan' if expected_texts is not None else 'pptx_native_text', 'pages': []}
        for index, expected in enumerate(submitted):
            pptx_text = _normal(''.join(texts[index])) if index < len(texts) else ''
            missing = [text for text in expected if _normal(text) not in pptx_text]
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
        with fitz.open(pdf_path) as document:
            report['pdf_page_count'] = document.page_count
            if document.page_count != expected_slides:
                _issue(report, 'pdf_page_count_mismatch', '实际渲染 PDF 页数不符合提交计划')
            if not 1 <= document.page_count <= MAX_SLIDES:
                raise ValueError('实际渲染页数超出安全范围')
            for index, page in enumerate(document):
                if page.rect.width > 2160 or page.rect.height > 2160:
                    raise ValueError('PDF 页面尺寸超出预览安全范围')
                actual = _normal(page.get_text('text'))
                wanted = submitted[index] if index < len(submitted) else []
                missing = [text for text in wanted if _normal(text) not in actual]
                report['text_retention']['pages'].append({'page': index + 1, 'expected_items': len(wanted), 'missing_items': len(missing), 'pdf_text_chars': len(actual)})
                if missing:
                    _issue(report, 'text_missing_in_render', '部分提交文字未出现在真实渲染 PDF 中，可能被裁切或字体渲染异常', page=index + 1, missing_count=len(missing))
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
