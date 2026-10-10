"""真实 PDF 图注几何目录及固定功能 oracle；不包含模型生成代码。"""
from __future__ import annotations
import copy
import math
from pathlib import Path
from .documents import file_hash, parse_document, pdf_page_geometry


def catalog_input(path: Path, source_id: str, expected_sha256: str) -> dict:
    if file_hash(path) != expected_sha256:
        raise ValueError('输入版本已变化，请重新准备任务')
    parsed = parse_document(path)
    if parsed['format'] != 'pdf':
        raise ValueError('图件目录仅支持真实 PDF')
    pages = []
    for page in range(1, parsed['page_count'] + 1):
        geometry = pdf_page_geometry(path, page, expected_sha256)
        pages.append({'page': page, 'figure_candidates': [
            {key: copy.deepcopy(row[key]) for key in ('candidate_id', 'caption', 'bbox')}
            for row in geometry['figure_candidates']]})
    if file_hash(path) != expected_sha256:
        raise ValueError('输入版本已变化，请重新准备任务')
    return {'source_id': source_id, 'version_sha256': expected_sha256, 'pages': pages}


def expected_catalog(payload: dict) -> dict:
    """独立、固定的全部真实候选保持标准，不授权选图或科学解释。"""
    figures = []
    seen = set()
    for page in payload['pages']:
        if type(page['page']) is not int or page['page'] < 1:
            raise ValueError('图件目录页码无效')
        for candidate in page['figure_candidates']:
            if candidate['candidate_id'] in seen:
                raise ValueError('图件候选 ID 重复')
            seen.add(candidate['candidate_id'])
            bbox = candidate['bbox']
            if (not isinstance(bbox, list) or len(bbox) != 4 or any(
                    type(x) not in (float, int) or not math.isfinite(x) or not 0 <= x <= 1 for x in bbox)
                    or not bbox[0] < bbox[2] or not bbox[1] < bbox[3]):
                raise ValueError('图件候选边界无效')
            figures.append({'page': page['page'], **copy.deepcopy(candidate)})
    figures.sort(key=lambda item: (item['page'], item['candidate_id']))
    return {'source_id': payload['source_id'], 'version_sha256': payload['version_sha256'], 'figures': figures}


def verify_catalog(payload: dict, result: dict):
    if result != expected_catalog(payload):
        raise ValueError('生成目录与真实图件候选不一致，拒绝使用')
