"""Intersect the authenticated provider catalog with supported, priced Web models.

Catalog discovery is a read-only request; it never calls a completion endpoint.
Credentials and provider error bodies are never returned or recorded.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

from src.adapters.deepseek_cost_gate import (
    PEAK_USD_PER_MILLION, CACHE_HIT_PEAK_USD_PER_MILLION,
    provider_output_reservation, validate_cost_cap,
)

CATALOG_URL = 'https://api.deepseek.com/models'
MODEL_LABELS = {'deepseek-flash': 'DeepSeek V4.1 Flash', 'deepseek-v4-pro': 'DeepSeek V4 Pro'}
REASONING_EFFORTS = ('off', 'low', 'high', 'max')
REASONING_LABELS = {'off': 'Off', 'low': 'Low', 'high': 'High', 'max': 'Max'}


def model_options(catalog: dict, *, budget_usd: float | None, max_output_tokens: int | None = None) -> list[dict]:
    """Keep native output defaults; annotate modes whose output alone cannot fit.

    Input and accumulated usage remain checked by the existing budget gate on
    every real request. This annotation is only an early, certain rejection.
    """
    validate_cost_cap(budget_usd)
    if max_output_tokens is not None and (type(max_output_tokens) is not int or max_output_tokens < 1):
        raise ValueError('invalid configured output limit')
    if not isinstance(catalog, dict) or not isinstance(catalog.get('data'), list):
        raise ValueError('invalid provider model catalog')
    rows = {row['id']: row for row in catalog['data'] if isinstance(row, dict) and isinstance(row.get('id'), str)}
    result = []
    for model, label in MODEL_LABELS.items():
        if model not in rows:
            continue
        row = rows[model]
        # Omitted metadata is common in the authenticated /models response.
        # Leave it absent so the installed adapter supplies native capability.
        support = row.get('supported_reasoning_efforts')
        if 'supported_reasoning_efforts' in row:
            if not isinstance(support, list) or any(not isinstance(value, str) for value in support):
                raise ValueError('invalid provider reasoning capability metadata')
            # Off is the separate thinking.disabled switch; providers may omit
            # it when listing only the strengths of enabled thinking.
            support = [effort for effort in REASONING_EFFORTS if effort == 'off' or effort in support]
        unavailable = {}
        for effort in support if support is not None else REASONING_EFFORTS:
            output = max_output_tokens or provider_output_reservation(model, {
                'thinking': {'type': 'disabled' if effort == 'off' else 'enabled'},
                **({'reasoning_effort': effort} if effort != 'off' else {}),
            })
            reserve = output * PEAK_USD_PER_MILLION[model][1] / 1_000_000
            if budget_usd is not None and reserve >= budget_usd:
                unavailable[effort] = (f'{REASONING_LABELS[effort]} 暂不可用：'
                    f'当前每任务预算 ${budget_usd:g} 不足以预留该模型的'
                    f'{"默认" if max_output_tokens is None else "已配置"}输出费用（至少 ${reserve:.6f}）。')
        if 'off' not in unavailable:
            for effort in unavailable:
                unavailable[effort] += '请先选择 Off，再选择该模型。'
        result.append({'provider': 'deepseek-official', 'model': model, 'label': label,
                       'available': True,
                       **({'supported_reasoning_efforts': support} if support is not None else {}),
                       **({'reasoning_unavailable': unavailable} if unavailable else {})})
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
