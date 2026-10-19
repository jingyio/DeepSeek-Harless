"""New frozen quality version: original effects plus explicitly required source reads."""
import json
from pathlib import Path
from operation_contract import verify_operations
VERSION='sss-file-operation-quality-v2'
def verify_operations_v2(spec,report,output,events):
    r=verify_operations(spec,report,output,events)
    if spec['operation_contract'].get('validation_version')!=VERSION:r['errors'].append('unknown v2 quality contract')
    if spec['operation_contract'].get('require_source_read'):
        paths={json.loads(p.read_text())['path'] for p in (Path(output)/'reads').glob('*.json')}
        if not {a['source'] for a in spec['operation_contract']['actions']}<=paths:r['errors'].append('required original sources not actually read')
    r['passed']=not r['errors'];r['validation_version']=VERSION;return r
