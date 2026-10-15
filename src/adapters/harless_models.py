"""Intersect the authenticated provider catalog with supported, priced Web models.

Catalog discovery is a read-only request; it never calls a completion endpoint.
Credentials and provider error bodies are never returned or recorded.
"""
from __future__ import annotations

import json
import math
import urllib.request
from datetime import datetime, timezone

from src.adapters.deepseek_cost_gate import (
    PEAK_USD_PER_MILLION, CACHE_HIT_PEAK_USD_PER_MILLION,
    DEEPSEEK_OUTPUT_DEFAULTS,
)

CATALOG_URL = 'https://api.deepseek.com/models'
MODEL_LABELS = {'deepseek-flash': 'DeepSeek V4.1 Flash', 'deepseek-v4-pro': 'DeepSeek V4 Pro'}


def model_options(catalog: dict, *, budget_usd: float, max_output_tokens: int | None = None) -> list[dict]:
    """Keep native output defaults; annotate modes whose output alone cannot fit.

    Input and accumulated usage remain checked by the existing budget gate on
    every real request. This annotation is only an early, certain rejection.
    """
    if isinstance(budget_usd, bool) or not isinstance(budget_usd, (int, float)) or not math.isfinite(budget_usd) or budget_usd < 0:
        raise ValueError('invalid model task budget')
    if max_output_tokens is not None and (type(max_output_tokens) is not int or max_output_tokens < 1):
        raise ValueError('invalid configured output limit')
    if not isinstance(catalog, dict) or not isinstance(catalog.get('data'), list):
        raise ValueError('invalid provider model catalog')
    ids = {row.get('id') for row in catalog['data'] if isinstance(row, dict) and isinstance(row.get('id'), str)}
    result = []
    for model, label in MODEL_LABELS.items():
        if model not in ids:
            continue
        unavailable = {}
        for effort, native_mode in (('off', 'disabled'), ('high', 'enabled')):
            output = max_output_tokens or DEEPSEEK_OUTPUT_DEFAULTS[native_mode]
            reserve = output * PEAK_USD_PER_MILLION[model][1] / 1_000_000
            if reserve >= budget_usd:
                unavailable[effort] = (f'{"On" if effort == "high" else "Off"} 暂不可用：'
                    f'当前每任务预算 ${budget_usd:g} 不足以预留该模型的'
                    f'{"默认" if max_output_tokens is None else "已配置"}输出费用（至少 ${reserve:.6f}）。')
        if 'high' in unavailable and 'off' not in unavailable:
            unavailable['high'] += '请先选择 Off，再选择该模型。'
        result.append({'provider': 'deepseek-official', 'model': model, 'label': label,
                       'available': True, **({'reasoning_unavailable': unavailable} if unavailable else {})})
    if not result:
        raise ValueError('provider catalog contains no supported, priced DeepSeek models')
    return result


def price_basis(models: list[dict]) -> dict:
    return {row['model']: {
        'currency': 'USD', 'unit': 'million_tokens', 'reservation_basis': 'peak',
        'input_cache_hit': CACHE_HIT_PEAK_USD_PER_MILLION[row['model']],
        'input_cache_miss': PEAK_USD_PER_MILLION[row['model']][0],
        'output': PEAK_USD_PER_MILLION[row['model']][1],
        'off_peak_multiplier': .5,
        'source': 'https://api-docs.deepseek.com/quick_start/pricing/',
    } for row in models if row['provider'] == 'deepseek-official'}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def discover_deepseek_models(api_key: str, *, opener=None) -> dict:
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError('DeepSeek model discovery requires the configured server credential')
    request = urllib.request.Request(CATALOG_URL, headers={
        'Authorization': 'Bearer ' + api_key.strip(), 'Accept': 'application/json'}, method='GET')
    try:
        opener = opener or urllib.request.build_opener(_NoRedirect()).open
        with opener(request, timeout=20) as response:
            # Do not accept a credential-bearing redirect or unbounded response.
            if response.geturl() != CATALOG_URL or response.status != 200:
                raise ValueError('invalid model catalog response')
            raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ValueError('model catalog response is too large')
            payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise ValueError('invalid model catalog response')
        # Retain only public capability metadata, never arbitrary response fields.
        allowed = ('id', 'name', 'context_window', 'max_output_tokens', 'input_modalities', 'supported_reasoning_efforts')
        rows = [{key: row[key] for key in allowed if key in row} for row in payload['data']
                if isinstance(row, dict) and isinstance(row.get('id'), str)]
        return {'data': rows, 'checked_at': datetime.now(timezone.utc).isoformat(),
                'source': CATALOG_URL, 'http_status': 200, 'model_requests': 0}
    except Exception:
        raise ValueError('无法读取 DeepSeek 模型列表，请检查服务器连接和凭据配置后重试。') from None
