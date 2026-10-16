"""拒绝没有来源摘录的常见统计量；不是通用事实或科学正确性认证。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
import unicodedata

NUMBER = r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
ASSIGN = r"\s*(?:(?:约为|约|为|是|等于|is|of)\s*)?[:=≈]?\s*"
PATTERNS = {
    "mean": re.compile(r"(?:均值|平均值|\bmean\b)" + ASSIGN + NUMBER, re.I),
    "slope": re.compile(r"(?:斜率|\bslope\b)" + ASSIGN + NUMBER, re.I),
    "correlation": re.compile(r"(?:相关系数|\bcorrelation(?:\s+coefficient)?\b|(?<![\w])r(?!\s*[²2]))" + ASSIGN + NUMBER, re.I),
    "r_squared": re.compile(r"(?:R\s*(?:²|2|\^2)|R[- ]squared|决定系数)" + ASSIGN + NUMBER, re.I),
    "sd": re.compile(r"(?:标准差|\bstandard deviation\b|\bSD\b)" + ASSIGN + NUMBER, re.I),
    "se": re.compile(r"(?:标准误|\bstandard error\b|\bSE\b)" + ASSIGN + NUMBER, re.I),
    "confidence_interval": re.compile(r"(?:置信区间|\bCI\b)" + ASSIGN + r"[\[(]?\s*" + NUMBER + r"\s*[,，~～至–—]\s*" + NUMBER, re.I),
}
for kind, operator in {'equal': r'[:=为]', 'below': r'<(?![=])', 'above': r'>(?![=])',
                       'at_most': r'(?:<=|≤)', 'at_least': r'(?:>=|≥)'}.items():
    PATTERNS['p_value_' + kind] = re.compile(r'(?:\bp(?:[- ]?value)?\b|p值)\s*' + operator + r'\s*' + NUMBER, re.I)


def claims(text: str) -> list[tuple[str, tuple[Decimal, ...]]]:
    text = unicodedata.normalize('NFKC', text).replace('−', '-')
    found = []
    for metric, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            try:
                family = metric
                if metric == 'confidence_interval':
                    level = re.search(r'(\d+(?:\.\d+)?)%\s*$', text[:match.start()])
                    family += ':' + (str(Decimal(level[1])) if level else 'unspecified')
                found.append((family, tuple(Decimal(value) for value in match.groups())))
            except InvalidOperation:
                continue
    return found


def _rounded_match(value: Decimal, source: Decimal) -> bool:
    if value == source:
        return True
    if value == 0:
        return False
    # 可忠实减少小数位，不容许伪造来源没有给出的精度。
    try:
        return (value.as_tuple().exponent >= source.as_tuple().exponent
                and source.quantize(Decimal(1).scaleb(value.as_tuple().exponent)) == value)
    except InvalidOperation:
        return False


def _statements(slide: dict):
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)
    for key, value in slide.items():
        if key not in {'sources', 'image', 'table'}:
            yield from strings(value)
    table = slide.get('table')
    if isinstance(table, list):
        for row in table:
            if isinstance(row, list):
                yield ' '.join(str(cell) for cell in row)
        # 支持“指标为列名，数值在下一行”的原生表格。
        if table and isinstance(table[0], list):
            for row in table[1:]:
                if isinstance(row, list):
                    for label, value in zip(table[0], row):
                        yield f'{label}: {value}'


def check_numeric_evidence(slide: dict, source_pages: list[dict]) -> dict:
    requested = list(dict.fromkeys(claim for text in _statements(slide) for claim in claims(text)))
    available = [claim for page in source_pages for claim in claims(page.get('text', ''))]
    missing = []
    for metric, values in requested:
        if not any(metric == kind and len(values) == len(source_values)
                   and all(_rounded_match(value, original) for value, original in zip(values, source_values))
                   for kind, source_values in available):
            missing.append({'metric': metric, 'values': [str(value) for value in values]})
    # 图片原文无确定性文字抽取，不拿“无文本”证明原图不存在该数值。
    visual_only = bool(source_pages) and all(page.get('visual_input') for page in source_pages)
    return {'scope': 'common_statistic_source_quote_only', 'scientific_quality_certified': False,
            'checked_claims': len(requested), 'unsupported': missing,
            'status': 'visual_review_required' if visual_only and missing else 'rejected' if missing else 'passed'}
