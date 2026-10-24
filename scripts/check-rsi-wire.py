"""Cross-language fixture wire check; no model or external service."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.rsi_protocol import validate_record

value = json.loads((ROOT / 'examples/rsi-protocol-v1/fixtures.json').read_text(encoding='utf-8'))
results = []
for record in value['records'] + [case['record'] for case in value['invalid']]:
    try:
        validate_record(record)
        results.append(True)
    except (ValueError, TypeError, RecursionError):
        results.append(False)
print(json.dumps(results))
