"""Load an administrator-selected, byte-bound runtime bundle, not raw experiments."""
import hashlib
import json
import re
from pathlib import Path


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def load_ppt_bundle(root: Path, directory: Path):
    base=directory.resolve(strict=True)
    cert_path=base/'certification.json'
    if cert_path.is_symlink() or cert_path.stat().st_size>1000000: raise ValueError('invalid certification')
    cert=json.loads(cert_path.read_text())
    if (not isinstance(cert,dict) or cert.get('schema_version')!=1 or cert.get('scene')!='ppt' or
        cert.get('binding_policy')!='ppt_uploaded_sources_v1' or cert.get('matching_policy')!='structural_only' or
        cert.get('certification_scope')!='independent_trace_structure' or not isinstance(cert.get('code_locks'),dict) or
        not 1<=len(cert['code_locks'])<=512 or not isinstance(cert.get('file_locks'),dict) or
        any(not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v) for v in
            [*cert['code_locks'].values(),*cert['file_locks'].values(),cert.get('source_evidence_sha256'),cert.get('learning_report_sha256')])):
        raise ValueError('unsupported runtime certification')
    code_locks={}
    for name,expected in cert['code_locks'].items():
        if not isinstance(name,str):raise ValueError('invalid code lock')
        p=(root/name).resolve(strict=True)
        if Path(name).is_absolute() or '..' in Path(name).parts or not p.is_relative_to(root.resolve()) or sha(p)!=expected:
            raise ValueError('certified runtime code changed')
        code_locks[str(p)]=expected
    names={'manifest':'online-manifest.json','task':'task.json','tool_schemas':'tool-schemas.json'}
    for name in (*names.values(),'library.json'):
        p=base/name
        if p.is_symlink() or p.stat().st_size>4000000 or sha(p)!=cert['file_locks'].get(name):
            raise ValueError('runtime artifact changed')
    schemas=json.loads((base/'tool-schemas.json').read_text())
    if not isinstance(schemas,list) or not schemas:raise ValueError('certified whole schemas required')
    return {**{key:str(base/name) for key,name in names.items()},
            'certified_tool_schemas':schemas,'certified_tool_schemas_sha256':sha(base/'tool-schemas.json'),
            'matching_policy':cert['matching_policy'],'binding_policy':cert['binding_policy'],
            'certification_path':str(cert_path),'certification_sha256':sha(cert_path),
            'certified_code_locks':code_locks,'certification_scope':cert['certification_scope'],
            'quality_cost_promoted':False}
