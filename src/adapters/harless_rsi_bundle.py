"""Load administrator-selected, byte-bound scene bundles, not raw experiments."""
import hashlib
import json
import re
from pathlib import Path


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def load_product_bundle(root: Path, directory: Path, scene: str, *, private_root: Path | None = None):
    base = directory.resolve(strict=True)
    if private_root is not None:
        private = private_root.resolve(strict=True)
        if (scene != 'paper-proofreading' or private_root.is_symlink()
                or not private.is_relative_to((root / '.local').resolve())
                or not base.is_relative_to(private) or directory.is_symlink()):
            raise ValueError('private learning release escapes its owning store')
    elif not base.is_relative_to((root / 'motif-libraries').resolve()):
        raise ValueError('product bundles must be registered repository artifacts')
    entry_path = base / 'entry.json'
    entry = json.loads(entry_path.read_text(encoding='utf-8'))
    if not isinstance(entry,dict) or not isinstance(entry.get('files'),dict):
        raise ValueError('invalid product library entry')
    expected = {'ppt': 'ppt_read_v1', 'research-data-analysis': 'data_receipts_v3', 'paper-proofreading': 'paper_shadow_v1'}
    learned_ppt=scene=='ppt' and entry.get('runtime_kind')=='ppt_read_v2'
    learned_paper=scene=='paper-proofreading' and entry.get('runtime_kind')=='paper_document_read_v1'
    learned_master=scene=='ppt' and entry.get('runtime_kind')=='ppt_master_v1'
    if private_root is not None and not learned_paper:
        raise ValueError('private learning only admits the existing paper document protocol')
    learned=learned_ppt or learned_paper or learned_master
    if entry.get('schema_version') != 1 or entry.get('scene') != scene or (not learned and entry.get('runtime_kind') != expected.get(scene)) or entry.get('new_training') is not learned:
        raise ValueError('invalid existing product library')
    for name, version in entry['files'].items():
        if (not isinstance(name,str) or not isinstance(version,str) or
                not re.fullmatch(r'[a-f0-9]{64}',version)):
            raise ValueError('invalid product library artifact lock')
        p = base / name
        if Path(name).name != name or p.is_symlink() or p.stat().st_size > 4_000_000 or sha(p) != version:
            raise ValueError('product library artifact changed')
    info = {'runtime_kind': entry['runtime_kind'], 'runtime_mode': entry['mode'],
            'runtime_library': str(base / 'library.json'), 'runtime_library_sha256': sha(base / 'library.json')}
    if learned_master:
        return {**info, **_load_ppt_master_bundle(root, base, entry)}
    if learned_paper:
        return {**info, **_load_paper_document_bundle(root, base, entry)}
    if learned_ppt:
        required={'certification.json','library.json','online-manifest.json','task.json','tool-schemas.json','source-evidence.json','learning-report.json'}
        if not required.issubset(entry['files']) or entry.get('mode')!='execute':
            raise ValueError('learned PPT release lacks locked evidence')
        cert=json.loads((base/'certification.json').read_text(encoding='utf-8'))
        evidence=json.loads((base/'source-evidence.json').read_text(encoding='utf-8'))
        if (cert.get('binding_policy')!='ppt_uploaded_sources_v2' or
                cert.get('source_evidence_sha256')!=sha(base/'source-evidence.json') or
                cert.get('learning_report_sha256')!=sha(base/'learning-report.json') or
                len(evidence.get('train',[]))<2 or len(evidence.get('heldout',[]))<1):
            raise ValueError('learned PPT independent evidence missing')
        from .task_identity import require_distinct_decisions
        require_distinct_decisions([*evidence['train'],*evidence['heldout']])
        report=json.loads((base/'learning-report.json').read_text(encoding='utf-8'))
        schemas=json.loads((base/'tool-schemas.json').read_text(encoding='utf-8'))
        if (report.get('new_training') is not True or report.get('quality_cost_promoted') is not False or
                report.get('training_tasks')!=len(evidence['train']) or report.get('heldout_tasks')!=len(evidence['heldout']) or
                len(schemas)!=21 or len({s['name'] for s in schemas})!=21 or
                'tool-schema-variants.json' not in entry['files']):
            raise ValueError('learned PPT release metadata or whole schemas invalid')
        return {**info,**load_uploaded_bundle(root,base,'ppt')}
    if scene == 'ppt':
        # Original training certificate stays immutable. Current-code admission
        # is a separate, reviewed compatibility record, never a new training run.
        cert = json.loads((base / 'certification.json').read_text(encoding='utf-8'))
        binding_path = base / 'runtime-bindings.json'
        binding = json.loads(binding_path.read_text(encoding='utf-8'))
        if (binding.get('schema_version') != 1 or binding.get('original_certification_sha256') != sha(base / 'certification.json')
                or binding.get('mode') != 'compatible_existing_read_library' or not binding.get('code_locks')):
            raise ValueError('existing PPT deployment compatibility missing')
        locks = {}
        for name, version in binding['code_locks'].items():
            p = (root / name).resolve(strict=True)
            if Path(name).is_absolute() or '..' in Path(name).parts or not p.is_relative_to(root.resolve()) or sha(p) != version:
                raise ValueError('existing PPT runtime code changed')
            locks[str(p)] = version
        schemas = json.loads((base / 'tool-schemas.json').read_text(encoding='utf-8'))
        variants_path = base / 'tool-schema-variants.json'
        if variants_path.name not in entry['files']: raise ValueError('missing verified whole schema variants')
        variants = json.loads(variants_path.read_text(encoding='utf-8'))
        if not isinstance(variants,list) or not variants or any(not isinstance(v,list) or not v for v in variants):
            raise ValueError('invalid whole schema variants')
        info.update(manifest=str(base / 'online-manifest.json'), task=str(base / 'task.json'),
            tool_schemas=str(base / 'tool-schemas.json'),certified_tool_schemas_sha256=sha(base / 'tool-schemas.json'),
            certified_tool_schemas=schemas,certified_tool_schema_variants=variants,
            matching_policy='structural_only', binding_policy='ppt_uploaded_sources_v1',
            certification_path=str(binding_path), certification_sha256=sha(binding_path), certified_code_locks=locks,
            certification_scope=cert['certification_scope'], quality_cost_promoted=False)
    return info


def _load_paper_document_bundle(root: Path, base: Path, entry: dict):
    """Admit only the independently witnessed, fixed first-page read edge."""
    required={'certification.json','library.json','online-manifest.json','task.json',
              'tool-schemas.json','source-evidence.json','learning-report.json'}
    if not required.issubset(entry['files']) or entry.get('mode')!='execute':
        raise ValueError('learned paper release lacks locked evidence')
    cert=json.loads((base/'certification.json').read_text(encoding='utf-8'))
    evidence=json.loads((base/'source-evidence.json').read_text(encoding='utf-8'))
    training=evidence.get('train',[]) if isinstance(evidence,dict) else []
    heldout=evidence.get('heldout',[]) if isinstance(evidence,dict) else []
    if (not isinstance(cert,dict) or cert.get('binding_policy')!='approved_uploaded_reads_v1' or
            cert.get('source_evidence_sha256')!=sha(base/'source-evidence.json') or
            cert.get('learning_report_sha256')!=sha(base/'learning-report.json') or
            not isinstance(training,list) or not isinstance(heldout,list) or
            len(training)<2 or not heldout):
        raise ValueError('learned paper independent evidence missing')
    from .task_identity import DECISION_ID, require_distinct_decisions
    identities=[*training,*heldout]
    if any(not isinstance(row,dict) or not isinstance(row.get('research_decision_id'),str) or
           not DECISION_ID.fullmatch(row['research_decision_id']) or
           not isinstance(row.get('task_id'),str) or not row['task_id'] or
           any(not isinstance(row.get(key),str) or not re.fullmatch(r'[a-f0-9]{64}',row[key])
               for key in ('question_sha256','manifest_sha256','events_sha256','identity_sha256'))
           for row in identities):
        raise ValueError('learned paper trace identities invalid')
    require_distinct_decisions(identities)
    schemas=json.loads((base/'tool-schemas.json').read_text(encoding='utf-8'))
    allowed=json.loads((root/'scenarios/paper_proofreading/scenario.json').read_text(encoding='utf-8'))['allowed_tools']
    if (not isinstance(schemas,list) or len(schemas)!=len(allowed) or
            any(not isinstance(row,dict) or not isinstance(row.get('name'),str) or
                not isinstance(row.get('description'),str) or
                not isinstance(row.get('parameters'),dict) for row in schemas) or
            sorted(row.get('name','') for row in schemas)!=sorted(allowed)):
        raise ValueError('learned paper complete tool schemas invalid')
    read_schema=next(row['parameters'] for row in schemas
                     if row['name']=='mcp__paper_checks__read_pinned_document')
    if not isinstance(read_schema.get('properties'),dict) or not isinstance(read_schema.get('required',[]),list):
        raise ValueError('learned paper native first-page default changed')
    page_schema=read_schema['properties'].get('page',{})
    if (not isinstance(page_schema,dict) or page_schema.get('type')!='integer' or
            type(page_schema.get('default')) is not int or page_schema['default']!=1 or
            'page' in read_schema.get('required',[])):
        raise ValueError('learned paper native first-page default changed')
    report=json.loads((base/'learning-report.json').read_text(encoding='utf-8'))
    library=json.loads((base/'library.json').read_text(encoding='utf-8'))
    manifest=json.loads((base/'online-manifest.json').read_text(encoding='utf-8'))
    pair=['mcp__paper_checks__pin_document','mcp__paper_checks__read_pinned_document']
    if (not all(isinstance(row,dict) for row in (report,library,manifest)) or
            any(not isinstance(row.get('artifacts'),list) or len(row['artifacts'])!=1 or
                not isinstance(row['artifacts'][0],dict) for row in (library,manifest))):
        raise ValueError('learned paper release metadata or read edge invalid')
    if (report.get('schema_version')!=1 or report.get('new_training') is not True or
            report.get('quality_cost_promoted') is not False or
            report.get('training_tasks')!=len(training) or report.get('heldout_tasks')!=len(heldout) or
            report.get('artifacts')!=1 or report.get('library_digest')!=library.get('library_digest') or
            report.get('manifest_digest')!=manifest.get('manifest_digest') or
            report.get('evidence_sha256')!=sha(base/'source-evidence.json') or
            cert.get('manifest_digest')!=manifest.get('manifest_digest') or
            manifest.get('source_library_digest')!=library.get('library_digest') or
            library['artifacts'][0].get('tools')!=pair or manifest['artifacts'][0].get('tools')!=pair or
            library['artifacts'][0].get('certified_digest')!=manifest['artifacts'][0].get('certified_digest')):
        raise ValueError('learned paper release metadata or read edge invalid')
    artifact=library['artifacts'][0]
    witnessed=artifact.get('source_task_fingerprints',[])
    from src.motif_core.offline.trace_compiler import artifact_signature
    edge=artifact.get('transfer_evidence',[])
    if (not isinstance(witnessed,list) or len(witnessed)<2 or
            any(not isinstance(value,str) for value in witnessed) or len(set(witnessed))!=len(witnessed) or
            not set(witnessed).issubset(row['research_decision_id'] for row in training) or
            artifact.get('validation_task_fingerprint') not in {row['research_decision_id'] for row in heldout} or
            artifact.get('certified_digest')!=artifact_signature(artifact) or
            manifest['artifacts'][0].get('supporting_task_count')!=len(witnessed) or
            manifest['artifacts'][0].get('transfer_evidence')!=edge or
            artifact.get('code_nodes') or manifest['artifacts'][0].get('code_nodes') or
            not isinstance(edge,list) or len(edge)!=1 or not isinstance(edge[0],dict) or
            any(edge[0].get(key)!=value for key,value in {
                'from_tool':pair[0],'to_tool':pair[1],'from_field':'source_id','to_param':'source_id'}.items()) or
            edge[0].get('version_relation','same_source')!='same_source'):
        raise ValueError('learned paper read edge lacks independent witnessed bindings')
    contracts=manifest.get('contracts',{})
    if (not isinstance(contracts,dict) or set(contracts)!=set(pair) or
            any(not isinstance(row,dict) for row in contracts.values()) or
            manifest.get('version_fields')!={tool:'version_sha256' for tool in pair} or
            contracts[pair[0]].get('read_only') is not True or
            contracts[pair[0]].get('observed_anchor') is not True or
            contracts[pair[0]].get('required_params')!=['name','sha256'] or
            contracts[pair[0]].get('default_params')!={} or
            contracts[pair[1]].get('read_only') is not True or
            contracts[pair[1]].get('required_params')!=['source_id'] or
            contracts[pair[1]].get('default_params')!={'page':1} or
            type(contracts[pair[1]]['default_params']['page']) is not int):
        raise ValueError('learned paper first-page read contract invalid')
    from src.motif_core.offline.library_builder import validate_read_motif_library
    validate_read_motif_library(library)
    return load_uploaded_bundle(root,base,'paper-proofreading',approved_read=True)


def _load_ppt_master_bundle(root: Path, base: Path, entry: dict):
    required={'certification.json','library.json','online-manifest.json','task.json','tool-schemas.json','source-evidence.json','learning-report.json'}
    if not required.issubset(entry['files']) or entry.get('mode')!='execute':
        raise ValueError('ppt-master release lacks locked evidence')
    cert=json.loads((base/'certification.json').read_text(encoding='utf-8'))
    evidence=json.loads((base/'source-evidence.json').read_text(encoding='utf-8'))
    report=json.loads((base/'learning-report.json').read_text(encoding='utf-8'))
    lock=json.loads((root/'scenarios/ppt_master/skill-lock.json').read_text(encoding='utf-8'))
    if (cert.get('source_evidence_sha256')!=sha(base/'source-evidence.json') or
            cert.get('learning_report_sha256')!=sha(base/'learning-report.json') or
            report.get('skill_package_sha256')!=lock['package_sha256'] or
            report.get('new_training') is not True or report.get('quality_cost_promoted') is not False or
            len(evidence.get('train',[]))<2 or len(evidence.get('heldout',[]))!=1 or
            report.get('training_tasks')!=len(evidence['train']) or report.get('heldout_tasks')!=1):
        raise ValueError('ppt-master independent evidence or skill version invalid')
    from .task_identity import require_distinct_decisions
    require_distinct_decisions([*evidence['train'],*evidence['heldout']])
    manifest=json.loads((base/'online-manifest.json').read_text(encoding='utf-8'))
    pair=['mcp__ppt_master__pin_source', 'mcp__ppt_master__read_source_page']
    if (len(manifest.get('artifacts',[]))!=1 or manifest['artifacts'][0].get('tools')!=pair or
            set(manifest.get('contracts',{}))!=set(pair) or
            manifest['contracts'][pair[0]].get('required_params')!=['name','sha256'] or
            manifest['contracts'][pair[1]].get('required_params')!=['source_id'] or
            manifest['contracts'][pair[0]].get('default_params')!={} or
            manifest['contracts'][pair[0]].get('observed_anchor') is not True or
            manifest['contracts'][pair[1]].get('default_params')!={'page':1} or
            any(manifest['contracts'][t].get('read_only') is not True for t in pair) or
            manifest.get('version_fields')!=dict.fromkeys(pair,'version_sha256')):
        raise ValueError('ppt-master continuation exceeds the certified skill read')
    schemas=json.loads((base/'tool-schemas.json').read_text(encoding='utf-8'))
    if [t.get('name') for t in schemas]!=sorted([*pair,'mcp__ppt_master__read_skill_entry']):
        raise ValueError('ppt-master complete schema mismatch')
    library=json.loads((base/'library.json').read_text(encoding='utf-8'))
    from src.motif_core.offline.trace_compiler import artifact_signature
    from src.motif_core.offline.library_builder import validate_read_motif_library
    validate_read_motif_library(library)
    if (report.get('artifacts')!=1 or len(library.get('artifacts',[]))!=1 or
            report.get('library_digest')!=library.get('library_digest') or
            report.get('manifest_digest')!=manifest.get('manifest_digest') or
            manifest.get('source_library_digest')!=library.get('library_digest')):
        raise ValueError('ppt-master compilation digests disagree')
    artifact=library['artifacts'][0]; online=manifest['artifacts'][0]
    witnessed=artifact.get('source_task_fingerprints',[])
    edge=artifact.get('transfer_evidence',[])
    if (artifact.get('tools')!=pair or artifact.get('code_nodes') or online.get('code_nodes') or
            artifact.get('certified_digest')!=artifact_signature(artifact) or
            online.get('certified_digest')!=artifact.get('certified_digest') or
            len(witnessed)<2 or len(witnessed)!=len(set(witnessed)) or
            not set(witnessed).issubset(row['research_decision_id'] for row in evidence['train']) or
            artifact.get('validation_task_fingerprint') not in {row['research_decision_id'] for row in evidence['heldout']} or
            online.get('supporting_task_count')!=len(witnessed) or online.get('transfer_evidence')!=edge or
            len(edge)!=1 or any(edge[0].get(k)!=v for k,v in {
                'from_tool':pair[0],'to_tool':pair[1],'from_field':'source_id','to_param':'source_id'}.items()) or
            edge[0].get('version_relation','same_source')!='same_source' or
            any(row.get('skill_package_sha256')!=lock['package_sha256'] for row in [*evidence['train'],*evidence['heldout']])):
        raise ValueError('ppt-master continuation lacks independent witnessed bindings')
    return load_uploaded_bundle(root,base,'ppt',skill_read=True)


def load_uploaded_bundle(root: Path, directory: Path, scene: str, *, approved_read: bool = False, skill_read: bool = False):
    if scene not in ('ppt', 'paper-proofreading', 'research-data-analysis', 'literature'):
        raise ValueError('unsupported uploaded scene')
    policies = ('ppt_master_sources_v1',) if skill_read else ('approved_uploaded_reads_v1',) if approved_read else (('ppt_uploaded_sources_v1','ppt_uploaded_sources_v2') if scene == 'ppt' else ('uploaded_source_handles_v1',))
    base=directory.resolve(strict=True)
    cert_path=base/'certification.json'
    if cert_path.is_symlink() or cert_path.stat().st_size>1000000: raise ValueError('invalid certification')
    cert=json.loads(cert_path.read_text(encoding='utf-8'))
    if (not isinstance(cert,dict) or cert.get('schema_version')!=1 or cert.get('scene')!=scene or
        cert.get('binding_policy') not in policies or cert.get('matching_policy')!='structural_only' or
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
    schemas=json.loads((base/'tool-schemas.json').read_text(encoding='utf-8'))
    if not isinstance(schemas,list) or not schemas:raise ValueError('certified whole schemas required')
    variants = None
    if 'tool-schema-variants.json' in cert['file_locks']:
        p = base / 'tool-schema-variants.json'
        if p.is_symlink() or p.stat().st_size > 4_000_000 or sha(p) != cert['file_locks'][p.name]:
            raise ValueError('runtime schema variants changed')
        variants = json.loads(p.read_text(encoding='utf-8'))
        if scene != 'ppt' or not isinstance(variants, list) or not 1 <= len(variants) <= 32 or any(not isinstance(v, list) or not v for v in variants):
            raise ValueError('unsupported whole schema variants')
    return {**{key:str(base/name) for key,name in names.items()},
            'runtime_library':str(base/'library.json'),
            'runtime_library_sha256':sha(base/'library.json'),
            'certified_tool_schemas':schemas,'certified_tool_schemas_sha256':sha(base/'tool-schemas.json'),
            **({'certified_tool_schema_variants': variants} if variants else {}),
            'matching_policy':cert['matching_policy'],'binding_policy':cert['binding_policy'],
            'certification_path':str(cert_path),'certification_sha256':sha(cert_path),
            'certified_code_locks':code_locks,'certification_scope':cert['certification_scope'],
            'quality_cost_promoted':False}


def load_ppt_bundle(root: Path, directory: Path):
    """Keep the existing PPT loader API for callers and certificate tests."""
    return load_uploaded_bundle(root,directory,'ppt')


def load_scene_bundle(root: Path, directory: Path, scene_id: str):
    """Load a private reviewed read-pair bundle for this exact scene."""
    if scene_id not in ('ppt', 'paper-proofreading', 'research-data-analysis'):
        raise ValueError('unsupported Motif scene')
    return load_uploaded_bundle(root, directory, scene_id, approved_read=scene_id != 'ppt')
