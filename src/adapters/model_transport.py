"""Versioned HTTP envelope capacity, independent of model or spending limits."""
from __future__ import annotations

import json
from pathlib import Path


def model_request_max_bytes() -> int:
    value = json.loads((Path(__file__).resolve().parents[2] /
                        'config/geneloop-transport.json').read_text(encoding='utf-8'))
    if (not isinstance(value, dict) or
            set(value) != {'schema_version', 'model_request_max_bytes'} or
            type(value['schema_version']) is not int or value['schema_version'] != 1 or
            type(value['model_request_max_bytes']) is not int or
            not 0 < value['model_request_max_bytes'] <= 2**53 - 1):
        raise ValueError('invalid versioned model HTTP transport capacity')
    return value['model_request_max_bytes']


MODEL_REQUEST_MAX_BYTES = model_request_max_bytes()
MODEL_REQUEST_TOO_LARGE = 'GENELOOP_MODEL_REQUEST_TOO_LARGE'
