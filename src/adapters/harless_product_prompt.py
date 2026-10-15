"""Trusted Web-only product persona shared with the online TypeScript adapter."""
from __future__ import annotations

import json
from pathlib import Path


def product_persona() -> dict:
    value = json.loads((Path(__file__).resolve().parents[2] / 'config/geneloop-persona.json').read_text(encoding='utf-8'))
    if (set(value) != {'prefix', 'suffix', 'includeRuntimeContext'} or
            any(not isinstance(value.get(key), str) or not value[key].strip() for key in ('prefix', 'suffix')) or
            value['includeRuntimeContext'] is not False):
        raise ValueError('invalid GeneLoop product persona')
    return value


def product_system_prompt() -> dict:
    persona = product_persona()
    return {'includeHarnessIdentity': False, 'includeRuntimeContext': False,
            'personaPrefix': persona['prefix'], 'personaSuffix': persona['suffix']}
