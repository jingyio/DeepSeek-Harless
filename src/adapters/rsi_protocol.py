"""Offline wire validation/export. Online admission belongs to rsi_protocol.ts.

No legacy certificate is upgraded by this module. A valid record is data, never
an execution grant or an independent scientific validation result.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / 'schemas/rsi-protocol-v1.schema.json').read_text(encoding='utf-8'))
VALIDATOR = Draft202012Validator(SCHEMA)
LIMIT = 1_000_000
SCHEMA_KEYS = {'type', 'oneOf', 'properties', 'required', 'additionalProperties',
               'items', 'enum', 'const', 'description', 'title', 'default', 'examples'}


def _supported_schema(schema: Any) -> None:
    if not isinstance(schema, dict) or set(schema) - SCHEMA_KEYS:
        raise ValueError('rsi_nested_schema_unsupported')
    Draft202012Validator.check_schema(schema)
    if 'type' in schema and schema['type'] not in ('object', 'array', 'string', 'number', 'integer', 'boolean', 'null'):
        raise ValueError('rsi_nested_schema_unsupported')
    if 'oneOf' in schema:
        if set(schema) - {'oneOf', 'description', 'title', 'default', 'examples'}:
            raise ValueError('rsi_nested_schema_unsupported')
        for child in schema['oneOf']:
            _supported_schema(child)
        return
    structural = set(schema) & {'properties', 'required', 'additionalProperties', 'items', 'enum', 'const'}
    permitted = ({'properties', 'required', 'additionalProperties'} if schema.get('type') == 'object'
                 else {'items'} if schema.get('type') == 'array'
                 else {'enum', 'const'} if schema.get('type') in ('string', 'number', 'integer', 'boolean', 'null') else set())
    if structural - permitted:
        raise ValueError('rsi_nested_schema_unsupported')
    if 'additionalProperties' in schema and not isinstance(schema['additionalProperties'], bool):
        raise ValueError('rsi_nested_schema_unsupported')
    if 'required' in schema and not set(schema['required']) <= set(schema.get('properties', {})):
        raise ValueError('rsi_nested_schema_unsupported')
    for child in schema.get('properties', {}).values():
        _supported_schema(child)
    if 'items' in schema:
        _supported_schema(schema['items'])
    for item in schema.get('enum', []):
        if list(Draft202012Validator({'type': schema['type']}).iter_errors(item)):
            raise ValueError('rsi_nested_schema_unsupported')
    if 'const' in schema and list(Draft202012Validator({'type': schema['type']}).iter_errors(schema['const'])):
        raise ValueError('rsi_nested_schema_unsupported')


def _wire_values(value: Any, key: str = '', depth: int = 0) -> None:
    if depth > 64:
        raise ValueError('rsi_record_too_deep')
    if key in ('input_schema', 'output_schema'):
        _supported_schema(value)
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) or abs(value) > 9007199254740991:
            raise ValueError('rsi_wire_number_out_of_range')
    if key.endswith('sha256') and value is not None and (not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value)):
        raise ValueError('rsi_wire_digest_invalid')
    if key in ('id', 'task_id', 'version', 'operation', 'state_version') and (not isinstance(value, str) or not value or len(value) > 256):
        raise ValueError('rsi_wire_identifier_invalid')
    if isinstance(value, dict):
        for child_key, child in value.items():
            _wire_values(child, child_key, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _wire_values(child, '', depth + 1)


def validate_record(record: Any) -> dict:
    try:
        _wire_values(record)
    except SchemaError as error:
        raise ValueError('rsi_nested_schema_unsupported') from error
    raw = json.dumps(record, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(raw) > LIMIT:
        raise ValueError('rsi_record_too_large')
    if list(VALIDATOR.iter_errors(record)):
        raise ValueError('rsi_record_schema_invalid')
    # The shared schema intentionally uses DSH's enforced subset. Nested tool
    # schemas must also use that subset; online validation fails closed on any
    # unsupported keyword rather than silently ignoring it.
    return record


def envelope(kind: str, payload: dict) -> dict:
    return validate_record(dict(protocol='geneloop.rsi/v1', record_type=kind, payload=payload))


def write_record(path: Path, record: dict) -> str:
    validate_record(record)
    raw = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def validate_file(path: Path) -> dict:
    if path.stat().st_size > LIMIT:
        raise ValueError('rsi_record_too_large')
    return validate_record(json.loads(path.read_text(encoding='utf-8')))


def provider_ledger_record(row: dict, *, task_id: str, ledger_ref: str) -> dict:
    """Project actual cost-gate counters; missing counters stay null, never zero.

    Deduplicate downstream by (ledger_ref, id); a terminal record replaces its
    booking. A failed/unknown request retains its reservation separately.
    """
    usage = row.get('response_usage') or {}
    observed = row.get('observed_peak_usd')
    phase = ('completed' if row.get('response_status') == 200 and observed is not None
             else 'failed' if row.get('response_status') not in (None, 200)
             else 'unknown' if 'response_status' in row else 'booked')
    return envelope('provider_request', dict(
        id=str(row['request_id']), task_id=task_id, ledger_ref=ledger_ref, model=row['model'], phase=phase,
        prompt_tokens=usage.get('prompt_tokens'), cache_hit_tokens=usage.get('prompt_cache_hit_tokens'),
        cache_miss_tokens=usage.get('prompt_cache_miss_tokens'), output_tokens=usage.get('completion_tokens'),
        observed_peak_usd=observed, reserved_upper_usd=row.get('reserved_upper_usd')))
