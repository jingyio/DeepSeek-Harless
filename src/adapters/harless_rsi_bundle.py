"""Load an administrator-selected, byte-bound runtime bundle, not raw experiments."""
import hashlib
import json
import re
from pathlib import Path


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def load_product_bundle(root: Path, directory: Path, scene: str):
    base = directory.resolve(strict=True)
    if not base.is_relative_to((root / 'motif-libraries').resolve()):
        raise ValueError('product bundles must be registered repository artifacts')
    entry_path = base / 'entry.json'
    entry = json.loads(entry_path.read_text())
    expected = {'ppt': 'ppt_read_v1', 'research-data-analysis': 'data_receipts_v3', 'paper-proofreading': 'paper_shadow_v1'}
    if entry.get('schema_version') != 1 or entry.get('scene') != scene or entry.get('runtime_kind') != expected.get(scene) or entry.get('new_training') is not False:
        raise ValueError('invalid existing product library')
    for name, version in entry['files'].items():
        p = base / name
        if Path(name).name != name or p.is_symlink() or p.stat().st_size > 4_000_000 or sha(p) != version:
            raise ValueError('product library artifact changed')
    info = {'runtime_kind': entry['runtime_kind'], 'runtime_mode': entry['mode'],
            'runtime_library': str(base / 'library.json'), 'runtime_library_sha256': sha(base / 'library.json')}
    if scene == 'ppt':
        # Original training certificate stays immutable. Current-code admission
        # is a separate, reviewed compatibility record, never a new training run.
        cert = json.loads((base / 'certification.json').read_text())
        binding_path = base / 'runtime-bindings.json'
        binding = json.loads(binding_path.read_text())
        if (binding.get('schema_version') != 1 or binding.get('original_certification_sha256') != sha(base / 'certification.json')
                or binding.get('mode') != 'compatible_existing_read_library' or not binding.get('code_locks')):
            raise ValueError('existing PPT deployment compatibility missing')
        locks = {}
        for name, version in binding['code_locks'].items():
            p = (root / name).resolve(strict=True)
            if Path(name).is_absolute() or '..' in Path(name).parts or not p.is_relative_to(root.resolve()) or sha(p) != version:
                raise ValueError('existing PPT runtime code changed')
            locks[str(p)] = version
        schemas = json.loads((base / 'tool-schemas.json').read_text())
        variants_path = base / 'tool-schema-variants.json'
        if variants_path.name not in entry['files']: raise ValueError('missing verified whole schema variants')
        variants = json.loads(variants_path.read_text())
        if not isinstance(variants,list) or not variants or any(not isinstance(v,list) or not v for v in variants):
            raise ValueError('invalid whole schema variants')
        info.update(manifest=str(base / 'online-manifest.json'), task=str(base / 'task.json'),
            tool_schemas=str(base / 'tool-schemas.json'),certified_tool_schemas_sha256=sha(base / 'tool-schemas.json'),
            certified_tool_schemas=schemas,certified_tool_schema_variants=variants,
            matching_policy='structural_only', binding_policy='ppt_uploaded_sources_v1',
            certification_path=str(binding_path), certification_sha256=sha(binding_path), certified_code_locks=locks,
            certification_scope=cert['certification_scope'], quality_cost_promoted=False)
    return info


def load_ppt_bundle(root: Path, directory: Path):
    return load_uploaded_bundle(root, directory, 'ppt')


def load_uploaded_bundle(root: Path, directory: Path, scene: str):
    if scene not in ('ppt', 'paper-proofreading', 'research-data-analysis', 'literature'):
        raise ValueError('unsupported uploaded scene')
    policy = 'ppt_uploaded_sources_v1' if scene == 'ppt' else 'uploaded_source_handles_v1'
    base=directory.resolve(strict=True)
    cert_path=base/'certification.json'
    if cert_path.is_symlink() or cert_path.stat().st_size>1000000: raise ValueError('invalid certification')
    cert=json.loads(cert_path.read_text())
    if (not isinstance(cert,dict) or cert.get('schema_version')!=1 or cert.get('scene')!=scene or
        cert.get('binding_policy')!=policy or cert.get('matching_policy')!='structural_only' or
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
    variants = None
    if 'tool-schema-variants.json' in cert['file_locks']:
        p = base / 'tool-schema-variants.json'
        if p.is_symlink() or p.stat().st_size > 4_000_000 or sha(p) != cert['file_locks'][p.name]:
            raise ValueError('runtime schema variants changed')
        variants = json.loads(p.read_text())
        if scene != 'ppt' or not isinstance(variants, list) or not 1 <= len(variants) <= 32 or any(not isinstance(v, list) or not v for v in variants):
            raise ValueError('unsupported whole schema variants')
    return {**{key:str(base/name) for key,name in names.items()},
            'certified_tool_schemas':schemas,'certified_tool_schemas_sha256':sha(base/'tool-schemas.json'),
            **({'certified_tool_schema_variants': variants} if variants else {}),
            'matching_policy':cert['matching_policy'],'binding_policy':cert['binding_policy'],
            'certification_path':str(cert_path),'certification_sha256':sha(cert_path),
            'certified_code_locks':code_locks,'certification_scope':cert['certification_scope'],
            'quality_cost_promoted':False}
