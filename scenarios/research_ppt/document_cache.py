"""普通 B1 内容寻址缓存；只保存解析数据，不缓存任务授权或语义决定。"""
from __future__ import annotations
import base64
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import tempfile
from time import perf_counter
from typing import Callable

from . import documents

ROOT = Path(__file__).resolve().parents[2]
CACHE_FORMAT_VERSION = 1
PARSE_VERSION = 'research-ppt-document-parser-v9-1'
PARSE_SCHEMA_VERSION = 1
GEOMETRY_VERSION = 'research-ppt-caption-geometry-v9-2'
GEOMETRY_SCHEMA_VERSION = 2
MAX_CACHE_BYTES = 140 * 1024 * 1024
Audit = Callable[[dict], None]


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('缓存 JSON 字段重复')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('缓存 JSON 包含非有限数值')


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) <= set(required) | set(optional):
        raise ValueError('缓存数据字段不符合受限 schema')


def _text(value, maximum):
    if not isinstance(value, str) or len(value) > maximum or documents.clean_text(value) != value:
        raise ValueError('缓存文本无效')


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('缓存整数范围无效')


def _bbox(value):
    if (not isinstance(value, list) or len(value) != 4 or
            any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1 for x in value) or
            not value[0] < value[2] or not value[1] < value[3]):
        raise ValueError('缓存图件边界无效')


def validate_parse_payload(value, expected_format):
    """Validate every persisted field; a cache entry cannot grant a source/read permission."""
    _keys(value, ('format', 'page_count', 'text_chars', 'pages', 'images', 'warnings'))
    if value['format'] != expected_format or expected_format not in {'pdf', 'pptx'}:
        raise ValueError('缓存文件格式不一致')
    _integer(value['page_count'], 1, 200)
    _integer(value['text_chars'], 0, 6_000_000)
    pages = value['pages']
    if not isinstance(pages, list) or len(pages) != value['page_count']:
        raise ValueError('缓存页面数量不一致')
    for index, page in enumerate(pages, 1):
        _keys(page, ('page', 'text', 'truncated'))
        if type(page['page']) is not int or page['page'] != index or type(page['truncated']) is not bool:
            raise ValueError('缓存页序或截断标记无效')
        _text(page['text'], 30_000)
    if sum(len(page['text'].strip()) for page in pages) != value['text_chars']:
        raise ValueError('缓存文本计数不一致')
    images = value['images']
    if not isinstance(images, list) or len(images) > 12:
        raise ValueError('缓存图片数量超出范围')
    from PIL import Image
    for index, image in enumerate(images, 1):
        _keys(image, ('image_id', 'page', 'width', 'height', 'pixel_check', 'data'), ('evidence_scope',))
        if image['image_id'] != f'img_{index}':
            raise ValueError('缓存图片标识无效')
        _integer(image['page'], 1, value['page_count'])
        _integer(image['width'], 1, 1800)
        _integer(image['height'], 1, 1800)
        if 'evidence_scope' in image and image['evidence_scope'] != 'embedded_asset_not_complete_figure':
            raise ValueError('缓存图片不能升级证据范围')
        _keys(image['pixel_check'], ('rgb_range', 'dominant_sample_fraction', 'scope'))
        _integer(image['pixel_check']['rgb_range'], 3, 255)
        dominant = image['pixel_check']['dominant_sample_fraction']
        if type(dominant) not in (int, float) or not math.isfinite(dominant) or not 0 <= dominant <= 0.995:
            raise ValueError('缓存图片像素比例无效')
        if image['pixel_check']['scope'] != 'nonblank_pixels_only_not_scientific_validation':
            raise ValueError('缓存图片不能包含科学认证')
        data = image['data']
        if (not isinstance(data, str) or not data.startswith('image/png;base64,') or
                len(data) > 12 * 1024 * 1024):
            raise ValueError('缓存图片编码无效')
        raw = base64.b64decode(data.split(',', 1)[1], validate=True)
        if len(raw) > 8 * 1024 * 1024 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('缓存图片格式或大小无效')
        with Image.open(io.BytesIO(raw)) as decoded:
            if decoded.format != 'PNG' or decoded.size != (image['width'], image['height']) or decoded.mode != 'RGB':
                raise ValueError('缓存图片像素元数据不一致')
            decoded.verify()
        # Recompute the nonblank-pixel diagnostic rather than trusting serialized metadata.
        with Image.open(io.BytesIO(raw)) as decoded:
            probe = decoded.resize((min(128, decoded.width), min(128, decoded.height)))
            count = probe.width * probe.height
            colors = probe.getcolors(count) or []
            fraction = max((number for number, _ in colors), default=0) / count
            rgb_range = max(high - low for low, high in probe.getextrema())
        if (fraction >= 0.995 or rgb_range != image['pixel_check']['rgb_range'] or
                round(fraction, 6) != dominant):
            raise ValueError('缓存图片像素检查不一致')
    if not isinstance(value['warnings'], list) or len(value['warnings']) > 600:
        raise ValueError('缓存警告字段无效')
    for warning in value['warnings']:
        _text(warning, 1200)


def validate_geometry_payload(value, page):
    _keys(value, ('geometry_version', 'figure_candidates', 'figure_localization', 'geometry_warnings'),
          ('page_size_points', 'unresolved_captions'))
    if type(value['geometry_version']) is not int or value['geometry_version'] != GEOMETRY_SCHEMA_VERSION:
        raise ValueError('缓存几何 schema 版本不一致')
    if 'page_size_points' in value:
        size = value['page_size_points']
        if (not isinstance(size, list) or len(size) != 2 or any(
                type(x) not in (float, int) or not math.isfinite(x) or x <= 0 for x in size)):
            raise ValueError('缓存页面尺寸无效')
    candidates = value['figure_candidates']
    if not isinstance(candidates, list) or len(candidates) > 30:
        raise ValueError('缓存图件候选数量无效')
    identities = set()
    for candidate in candidates:
        _keys(candidate, ('candidate_id', 'page', 'caption', 'caption_bbox', 'bbox', 'visual_bbox',
                          'evidence_types', 'status', 'semantic_verified'))
        identity = candidate['candidate_id']
        if (not isinstance(identity, str) or not re.fullmatch(r'figure-[0-9a-f]{20}', identity) or
                identity in identities or type(candidate['page']) is not int or candidate['page'] != page):
            raise ValueError('缓存图件候选身份无效')
        identities.add(identity)
        _text(candidate['caption'], 1200)
        for key in ('caption_bbox', 'bbox', 'visual_bbox'):
            _bbox(candidate[key])
        types = candidate['evidence_types']
        if (not isinstance(types, list) or not types or
                any(kind not in {'vector_graphic', 'embedded_image'} for kind in types) or
                types != sorted(set(types)) or candidate['status'] != 'geometry_candidate' or
                candidate['semantic_verified'] is not False):
            raise ValueError('缓存图件不能升级为科学认证')
    if candidates and 'page_size_points' not in value:
        raise ValueError('缓存候选缺少页面尺寸')
    expected_status = 'candidates_available' if candidates else 'abstained'
    if value['figure_localization'] != expected_status:
        raise ValueError('缓存几何状态不一致')
    for key, maximum in (('unresolved_captions', 30), ('geometry_warnings', 30)):
        rows = value.get(key, [])
        if not isinstance(rows, list) or len(rows) > maximum:
            raise ValueError('缓存几何诊断无效')
        for row in rows:
            if key == 'geometry_warnings':
                _text(row, 1200)
            else:
                _keys(row, ('caption', 'caption_bbox', 'reason'))
                _text(row['caption'], 600)
                _text(row['reason'], 1200)
                _bbox(row['caption_bbox'])


def _dependencies(operation, file_format):
    distributions = (('pypdf', 'Pillow', 'defusedxml') if operation == 'parse' else ('PyMuPDF',))
    return {'python': platform.python_version(),
            'python_implementation': platform.python_implementation(),
            **{name: importlib.metadata.version(name) for name in distributions}}


def _request(path, operation, source_sha256, page=None):
    file_format = path.suffix.lower().lstrip('.')
    if file_format not in {'pdf', 'pptx'} or (operation == 'geometry' and file_format != 'pdf'):
        raise ValueError('缓存入口只处理合法 PDF/PPTX 解析或 PDF 几何')
    return {'operation': operation, 'source_sha256': source_sha256, 'format': file_format,
            'page': page, 'parser_version': PARSE_VERSION if operation == 'parse' else GEOMETRY_VERSION,
            'schema_version': PARSE_SCHEMA_VERSION if operation == 'parse' else GEOMETRY_SCHEMA_VERSION,
            'implementation_sha256': documents.file_hash(Path(documents.__file__)),
            'dependencies': _dependencies(operation, file_format)}


def _cache_path(cache_dir, key):
    root = Path(cache_dir)
    if root.is_symlink() or not root.resolve().is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('解析缓存必须位于仓库私有 .local 目录')
    root.mkdir(parents=True, exist_ok=True)
    target = root / f'{key}.json'
    if target.is_symlink():
        raise ValueError('解析缓存不能使用符号链接')
    return target


def _current(path, expected_sha256):
    if documents.file_hash(path) != expected_sha256:
        raise ValueError('输入版本已变化，请重新准备任务')


def _cached(path, cache_dir, request, generate, validate, audit):
    start = perf_counter()
    key = hashlib.sha256(_canonical(request)).hexdigest()
    target = _cache_path(cache_dir, key)
    source_sha256 = request['source_sha256']

    def record(status, reason=None):
        if audit is not None:
            audit({'operation': request['operation'], 'cache_key': key, 'source_sha256': source_sha256,
                   'status': status, 'reason': reason, 'elapsed_ms': round((perf_counter() - start) * 1000, 3),
                   'parser_version': request['parser_version'], 'schema_version': request['schema_version'],
                   'dependencies': request['dependencies']})

    _current(path, source_sha256)
    if target.exists():
        try:
            if target.stat().st_size > MAX_CACHE_BYTES:
                raise ValueError('缓存文件超出大小限制')
            envelope = json.loads(target.read_text(encoding='utf-8'), object_pairs_hook=_pairs,
                                  parse_constant=_invalid_constant)
            _keys(envelope, ('cache_format_version', 'request', 'payload_sha256', 'payload'))
            if (type(envelope['cache_format_version']) is not int or
                    envelope['cache_format_version'] != CACHE_FORMAT_VERSION or envelope['request'] != request or
                    envelope['payload_sha256'] != hashlib.sha256(_canonical(envelope['payload'])).hexdigest()):
                raise ValueError('缓存版本、依赖或完整性不一致')
            validate(envelope['payload'])
        except Exception as error:
            # Do not publish serialized details or restore permission-bearing state.
            record('rejected', type(error).__name__)
        else:
            _current(path, source_sha256)
            record('hit')
            return envelope['payload']
    try:
        payload = generate()
        validate(payload)
        _current(path, source_sha256)
    except Exception:
        record('failed')
        raise
    encoded = _canonical({'cache_format_version': CACHE_FORMAT_VERSION, 'request': request,
                          'payload_sha256': hashlib.sha256(_canonical(payload)).hexdigest(), 'payload': payload})
    if len(encoded) > MAX_CACHE_BYTES:
        raise ValueError('缓存文件超出大小限制')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f'.{key}-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _current(path, source_sha256)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    _current(path, source_sha256)
    record('miss')
    return payload


def cached_parse_document(path: Path, cache_dir: Path, *, expected_sha256: str | None = None,
                          audit: Audit | None = None) -> dict:
    """Return the unchanged parse schema. The caller must authorize/pin each new job."""
    path = Path(path)
    source_sha256 = documents.file_hash(path)
    if expected_sha256 is not None and source_sha256 != expected_sha256:
        raise ValueError('输入版本已变化，请重新准备任务')
    request = _request(path, 'parse', source_sha256)
    return _cached(path, cache_dir, request, lambda: documents.parse_document(path),
                   lambda value: validate_parse_payload(value, request['format']), audit)


def cached_pdf_page_geometry(path: Path, page: int, version_sha256: str, cache_dir: Path, *,
                             audit: Audit | None = None) -> dict:
    """Cache only conservative geometry; semantic_verified remains False."""
    path = Path(path)
    _integer(page, 1, 200)
    _current(path, version_sha256)
    request = _request(path, 'geometry', version_sha256, page)
    return _cached(path, cache_dir, request, lambda: documents.pdf_page_geometry(path, page, version_sha256),
                   lambda value: validate_geometry_payload(value, page), audit)
