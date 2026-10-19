"""One persistent history with an independently certified active registry view.

Importing bytes is free and grants no execution authority. Only current original
certificates or fresh independent certification can populate the active view.
"""
from __future__ import annotations
from collections import Counter
import copy
from contextlib import contextmanager
import os
import shutil
from pathlib import Path
from functools import lru_cache
from uuid import uuid4

from src.motif_core.offline.experience_registry import (
    ExperienceRegistry, check_motif_certificate, digest, durable, read, sha,
)

FORMAT = 'sss-managed-experience-v1'
QUALITY = 'sss-management-quality-v7'
CERTIFICATION = 'sss-operation-certification-v2'
TARGET_CONTRACT = 'sss-runtime-and-catalog-compatibility-v2'
MAX_AUTOMATIC_JOBS = 2


def enabled(cfg):
    return (cfg.get('adapter') == 'management_v3' and cfg.get('provider_mode') == 'real'
            and cfg.get('role', 'ordinary') == 'ordinary'
            and Path(cfg['state_root']).name == 'daily-management-real-v3')


def sources():
    from .continuous_rsi import source_map
    from .mcp_learning import adapter
    return source_map(adapter('management_v3').runtime_sources())


def target_version(runtime):
    return digest({'adapter': 'management_v3', 'runtime_source': runtime,
                   'catalog': current_contracts(runtime), 'execution_version': current_execution_version(),
                   'quality': QUALITY, 'certification': CERTIFICATION, 'target_contract': TARGET_CONTRACT})


def current_contracts(runtime):
    from importlib.metadata import version, PackageNotFoundError
    packages = {}
    for name in ('mcp', 'pydantic'):
        try:packages[name] = version(name)
        except PackageNotFoundError:packages[name] = 'unavailable'
    return _current_contracts(digest({'runtime': runtime, 'schema_packages': packages}))


def current_execution_version():
    from .continuous_rsi import ROOT
    import sys
    sys.path.insert(0, str(ROOT/'scenarios/file-management'))
    from management_tools import execution_version
    return execution_version()


@lru_cache(maxsize=4)
def _current_contracts(version):
    """Use the registered service's real MCP schema builder, without a task/call."""
    import asyncio, sys
    from concurrent.futures import ThreadPoolExecutor
    from .continuous_rsi import ROOT
    sys.path.insert(0, str(ROOT/'scenarios/file-management'))
    from management_tools import ManagementScene, TOOLS, operator_contract
    from mcp.server import MCPServer
    from src.motif_core.offline.operation_graph import catalog
    server = MCPServer('file_management'); schema_only = ManagementScene.__new__(ManagementScene)
    for name in TOOLS:
        server.tool(name=name, meta={'sss_learning': operator_contract(name)})(getattr(schema_only, name))
    async def inspect():
        return [{**t.model_dump(by_alias=True), 'server_name': 'file_management'} for t in await server.list_tools()]
    # The lifecycle caller may already have an event loop. No service method runs.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return catalog(executor.submit(lambda: asyncio.run(inspect())).result())


def graph_compatibility(policy, tools):
    try:
        from .management_recertification import rebuild
        rebuild(policy, {'tools': tools, 'scope': {'execution_version': 'compatibility-probe'}}, {})
        return None
    except (ValueError, KeyError, TypeError) as error:return str(error)


def policy_current(policy, runtime):
    tools = current_contracts(runtime); artifact = policy.get('artifact', {})
    if policy.get('format')=='sss-operation-flow-v3':
        return (policy.get('execution_version_sha256')==current_execution_version() and not graph_compatibility(policy,tools)
                and all(artifact['tool_contracts'][n['tool']]==tools[n['tool']] for n in artifact['nodes'])
                and artifact.get('interleaving_contracts',{})=={n:t for n,t in tools.items() if t['contract']['effect']=='read' and (t['contract'].get('flow_interleaving') or t['contract'].get('safe_interleaving'))})
    if policy.get('format')=='sss-management-program-v1':
        from .management_legacy import validate_steps
        try:validate_steps(artifact['recipe']['steps'])
        except (ValueError,KeyError,TypeError):return False
        return policy.get('execution_version_sha256')==current_execution_version() and artifact.get('tool_contracts')==tools
    return (policy.get('execution_version_sha256') == current_execution_version()
            and not graph_compatibility(policy, tools)
            and all(artifact['tool_contracts'][n['tool']] == tools[n['tool']] for n in artifact['nodes'])
            and artifact.get('interleaving_contracts', {}) == {n: t for n, t in tools.items()
                    if t['contract'].get('safe_interleaving') and t['contract']['effect'] == 'read'})


def material_graph_observed(f, nodes):
    """A verified inherited route can select material, never certify a native DAG."""
    from src.motif_core.offline.operation_graph import valid_output, at, bindable
    verified = {r['call_id'] for r in f['audit'] if r['kind'] == 'operation_model_request_bypassed_verified'}
    tools = f['tools']; scope = f['scope']
    for start, root in enumerate(f['rows']):
        if root['name'] != nodes[0]['tool']:continue
        used = []; native = False
        for row in f['rows'][start:start+8]:
            expected = nodes[len(used)]; tc = tools.get(row['name'])
            if not tc or not valid_output(row, tc, scope):break
            if row['name'] != expected['tool']:
                if tc['contract'].get('safe_interleaving') and tc['contract']['effect'] == 'read':continue
                break
            if row.get('generated'):
                if row['call_id'] not in verified:break
            elif row.get('message_seq') is None:break
            else:native = True
            if used:
                if not tc['contract']['auto_continue'] or set(row['args']) != set(expected['bindings']):break
                valid = True
                for param, binding in expected['bindings'].items():
                    parent = binding['node']; field = binding['path']
                    if parent >= len(used) or field not in tools[used[parent]['name']]['contract']['exports']:
                        valid = False; break
                    value = at(used[parent]['out'], field)
                    if not bindable(value, tc['schema'].get('properties', {}).get(param, {})) or value != row['args'][param]:
                        valid = False; break
                if not valid:break
            used.append(row)
            if len(used) == len(nodes):
                if native:return True
                break
    return False


def shape(kind, value):
    nodes = value.get('artifact', {}).get('nodes')
    if value.get('artifact',{}).get('kind')=='learned_mcp_control_flow':return digest({'kind':kind,'nodes':nodes,'edges':value['artifact']['edges']})
    if kind=='management_program':return digest({'kind':kind,'recipe':value.get('artifact',{}).get('recipe')})
    return digest({'kind': kind, 'nodes': nodes}) if kind == 'operation_graph' and nodes else None


def bounded_file(project, path):
    project = Path(project).resolve(); path = Path(path).absolute()
    if not any(path.is_relative_to(project/r) for r in ('.local', 'examples/motif-library')):
        raise ValueError('experience source outside registered private/public archives')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('experience archive symlink refused')
    return path


def load(root):
    base = Path(root)/'experience'
    if not (base/'current.json').exists():
        return {'format': FORMAT, 'generation': 0, 'entries': [], 'issues': [], 'jobs': []}
    pointer = read(base/'current.json'); file = base/pointer['file']
    if sha(file) != pointer['sha256']:
        raise ValueError('managed experience pointer changed')
    value = read(file)
    if value.get('format') != FORMAT or value['digest'] != digest({k: v for k, v in value.items() if k != 'digest'}):
        raise ValueError('managed experience snapshot changed')
    for entry in value['entries']:
        if sha(base/entry['payload']) != entry['sha256']:
            raise ValueError('managed historical object changed')
    return value


def summary(root):
    value = load(root)
    return {'format': FORMAT, 'generation': value['generation'], 'managed_entries': len(value['entries']),
            'sealed_records': len(value.get('evidence', [])), 'retained_failures': len(value.get('failures', [])),
            'structure_count': len({e['shape'] for e in value['entries'] if e.get('shape')}),
            'states': dict(Counter(e['compatibility']['state'] for e in value['entries'])),
            'jobs': value.get('jobs', []), 'issues': value.get('issues', []), 'cloud_requests': 0}


def publish(root, entries, issues, jobs, target, evidence=(), failures=()):
    base = Path(root)/'experience'; previous = load(root)
    body = {'entries': sorted(entries, key=lambda e: e['key']), 'issues': sorted(issues, key=digest),
            'jobs': sorted(jobs, key=digest), 'target': target,
            'target_contract': TARGET_CONTRACT,
            'evidence': sorted(evidence, key=digest), 'failures': sorted(failures, key=digest)}
    if all(previous.get(k) == v for k, v in body.items()):
        return previous
    value = {'format': FORMAT, 'schema_version': 1, 'generation': previous['generation']+1,
             'parent_digest': previous.get('digest'), **body, 'import_grants_execution': False}
    value['digest'] = digest(value)
    file = base/'versions'/('%06d.json' % value['generation'])
    durable(file, value, exclusive=True)
    durable(base/'current.json', {'file': str(file.relative_to(base)), 'sha256': sha(file)})
    return value


def legacy_files(project):
    """Artifact locations only. Final task materials/attempts are never scanned."""
    skip = {'tasks', 'attempts', 'frozen-source', 'pristine', 'delivery', 'deliveries',
            'node_modules', 'workspaces', 'rsi-materials', 'holdout', 'benchmark', 'evaluate'}
    from .continuous_rsi import ROOT,STATE_HOME
    private_home=STATE_HOME.parent if Path(project).resolve()==ROOT.resolve() else Path(project)/'.local'
    base = private_home/'file-management'
    for parent, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = sorted(n for n in dirs if n.lower() not in skip and not n.lower().startswith('holdout'))
        for n in sorted(names):
            if (n in ('policy.json', 'library.json') or n.endswith(('-policy.json', '-library.json'))
                    or n.startswith(('program-', 'script-')) and n.endswith('.json')):
                yield Path(parent)/n
    public = Path(project)/'examples/motif-library'
    for catalog in sorted(public.glob('*/catalog.json')):
        value = read(catalog)
        for item in value.get('files', []):
            if item.get('kind') in ('read_library', 'collection_policy', 'reentry_policy', 'plan_policy'):
                yield catalog.parent/item['path']


@contextmanager
def catalog_lock(root):
    from .continuous_rsi import writer_lock
    lock = writer_lock(root, 'experience')
    try:lock.__enter__()
    except RuntimeError as error:
        if 'writer is active' not in str(error):raise
        yield False
        return
    try:yield True
    finally:lock.__exit__(None, None, None)


def synchronize(cfg, project=None):
    """Append original objects/aliases, verify compatibility, never run a model."""
    from .continuous_rsi import ROOT
    project = Path(project or ROOT).resolve(); root = Path(cfg['state_root']); base = root/'experience'
    runtime = sources(); target = target_version(runtime); tools = current_contracts(runtime)
    with catalog_lock(root) as acquired:
        if not acquired:return load(root)
        previous = load(root); found = {e['key']: copy.deepcopy(e) for e in previous['entries']}; issues = []
        store = ExperienceRegistry(base)

        def ingest(path, kind, artifact_id, origin, expected=None, certificate=None, runtime_source=None):
            path = bounded_file(project, path); raw = sha(path)
            if expected and expected != raw:
                raise ValueError('original experience payload digest changed')
            value = read(path); field = 'script_digest' if kind.startswith('script_') else 'library_digest' if kind == 'read_library' else 'policy_digest'
            if value.get(field) != artifact_id or digest({k: v for k, v in value.items() if k != field}) != artifact_id:
                raise ValueError('original experience signature changed')
            # Canonical identity and original byte variants are both retained.
            key = kind+':'+artifact_id+':'+raw; relative, h = store.object(path)
            item = found.setdefault(key, {'key': key, 'kind': kind, 'artifact_digest': artifact_id,
                                         'payload': relative, 'sha256': h, 'shape': shape(kind, value),
                                         'format': value.get('format'), 'origins': [], 'certificates': []})
            if item['sha256'] != h:
                raise ValueError('same signed experience has conflicting original bytes')
            if origin not in item['origins']:
                item['origins'].append(origin)
            item['origins'].sort(key=digest)
            if certificate:
                certpath = bounded_file(project, certificate['path'])
                if sha(certpath) != certificate['sha256']:
                    raise ValueError('original certificate changed')
                certfile, certhash = store.object(certpath)
                cert = {'file': certfile, 'sha256': certhash, 'original_file': str(certpath.relative_to(project)),
                        'runtime_source': runtime_source or {}}
                if cert not in item['certificates']:
                    item['certificates'].append(cert)
                item['certificates'].sort(key=digest)

        from .continuous_rsi import STATE_HOME, PRIVATE_HOME
        pointers = sorted(STATE_HOME.glob('*/registry/current.json'))
        pointers += sorted((STATE_HOME.parent/'file-management').glob('*/registry/current.json'))
        for pointer in pointers:
            try:
                registry = ExperienceRegistry(pointer.parent); current = registry.load()
                for file in sorted((pointer.parent/'versions').glob('*.json')):
                    state = registry.load(file)
                    for entry in state['entries']:
                        cert = entry.get('certificate')
                        ingest(pointer.parent/entry['payload'], entry['kind'], entry['artifact_digest'],
                               {'registry_file': str(file.relative_to(project)), 'registry_sha256': sha(file),
                                'state': entry['state'],
                                'disabled_reason': entry.get('disabled_reason')}, entry['sha256'],
                               {'path': pointer.parent/cert['file'], 'sha256': cert['sha256']} if cert else None,
                               entry.get('runtime_source'))
            except (ValueError, KeyError, OSError) as error:
                issues.append({'source': str(pointer.relative_to(project)), 'reason': str(error)})
        for path in legacy_files(project):
            try:
                value = read(bounded_file(project, path)); kind = None; identity = None
                if 'script_digest' in value:kind = 'script_v2' if value.get('schema_version') == 2 or 'runtime_source' in value else 'script_v1'; identity = value['script_digest']
                elif 'policy_digest' in value:
                    fmt = value.get('format', '')
                    kind = 'operation_graph' if 'operation-graph' in fmt or 'operation-flow' in fmt else 'reentry' if 'reentry' in fmt else 'collection' if 'collection' in fmt else 'plan'
                    identity = value['policy_digest']
                elif 'library_digest' in value:kind = 'read_library'; identity = value['library_digest']
                if kind:
                    ingest(path, kind, identity, {'artifact_file': str(path.relative_to(project)), 'state': 'historical'})
            except (ValueError, KeyError, OSError) as error:
                issues.append({'source': str(path.relative_to(project)), 'reason': str(error)})

        active = ExperienceRegistry(root/'registry').load()
        active_ids = {e['entry_id'] for e in active['entries'] if e['state'] == 'active'
                      and e.get('runtime_source') == runtime
                      and policy_current(read(root/'registry'/e['payload']), runtime)}
        active_shapes = {shape(e['kind'], read(root/'registry'/e['payload'])) for e in active['entries'] if e['entry_id'] in active_ids}
        from .management_legacy import proposals
        translations,translation_issues=proposals(root,list(found.values()))
        translated={}
        for proposal in translations:
            for alias in proposal['aliases']:translated.setdefault(alias['digest'],set()).add(proposal['key'])
        active_translations={read(root/'registry'/e['payload']).get('artifact',{}).get('legacy_adapter',{}).get('key') for e in active['entries'] if e['entry_id'] in active_ids}
        for item in found.values():
            if any(e['entry_id'] == item['artifact_digest'] and e['sha256'] == item['sha256']
                   and e['entry_id'] in active_ids for e in active['entries']):
                state, reason = 'active', 'current active registry admission; per-task guards still required'
            elif item['shape'] and item['shape'] in active_shapes:
                state, reason = 'covered', 'same exact graph has an independently certified current version'
            elif item['artifact_digest'] in translated:
                keys=translated[item['artifact_digest']]
                state,reason=('covered','all translated goal/rule variants have current independent certificates') if keys<=active_translations else ('recertification_required','registered native adapter; current independent goal/rule proof required')
                item['adapter_keys']=sorted(keys)
            elif item['kind'] not in ('operation_graph','management_program'):
                state, reason = 'adapter_required', 'historical IR managed; no native management execution adapter'
            elif item['kind']=='operation_graph' and graph_compatibility(read(base/item['payload']), tools):
                state, reason = 'adapter_required', graph_compatibility(read(base/item['payload']), tools)
            elif not item['certificates']:
                state, reason = 'proof_required', 'historical payload is not an independent execution certificate'
            else:
                state, reason = 'recertification_required', 'current tool/runtime/quality proof required before activation'
            item['compatibility'] = {'state': state, 'reason': reason, 'target': target}
        # Completed and interrupted jobs are indexed; their original files stay immutable.
        jobs = []
        for job in sorted((base/'jobs').glob('*')):
            if not job.is_dir():continue
            stage = 'active' if (job/'activation.json').exists() else 'rejected' if (job/'failure.json').exists() else 'superseded' if (job/'preflight-superseded.json').exists() else 'pending'
            jobs.append({'job': str(job.relative_to(root)), 'state': stage})
        evidence = []; failures = []
        from .continuous_rsi import records
        for profile in sorted((project/'.local/rsi').glob('*')):
            if not profile.is_dir():continue
            try:
                for record in records(profile):
                    path = profile/'records'/(record['session_id']+'.json')
                    file, raw = store.object(bounded_file(project, path))
                    evidence.append({'record_file': str(path.relative_to(project)), 'record_copy': file, 'sha256': raw,
                                     'role': record['role'], 'provider_mode': record.get('provider_mode'),
                                     'cost_usd': record.get('cost_usd'), 'upstream_requests': record.get('upstream_requests'),
                                     'events_file': str(Path(record['run_dir'])/'agent-events.jsonl'),
                                     'events_sha256': record.get('events_sha256'), 'accounting_complete': record.get('accounting_complete')})
                for path in sorted((profile/'learning').glob('*/failure.json')) + sorted((profile/'experience/jobs').glob('*/failure.json')):
                    file, raw = store.object(bounded_file(project, path))
                    failures.append({'file': str(path.relative_to(project)), 'copy': file, 'sha256': raw})
            except (ValueError, KeyError, OSError) as error:
                issues.append({'source': str(profile.relative_to(project)), 'reason': str(error)})
        issues.extend({'source':e['key'],'reason':e['reason']} for e in translation_issues)
        value = publish(root, list(found.values()), issues, jobs, target, evidence, failures)
        return value


def eligible_certificate(root, item, runtime=None):
    """Read original proofs; a copied catalog entry alone is never authority."""
    runtime = runtime or sources(); base = Path(root)/'experience'; policy = read(base/item['payload'])
    if any(o.get('state') == 'disabled' for o in item['origins']):return None
    errors = []
    for cert in item['certificates']:
        try:
            value = check_motif_certificate(policy, base/cert['file'], item['sha256'])
            if cert['runtime_source'] != runtime or value.get('material_quality_contract') != QUALITY:
                continue
            if any(read(r['record_file']).get('adapter') != 'management_v3' for r in [value['native_review'], *value['reviews']]):continue
            if not policy_current(policy, runtime):continue
            # Original runtime guards must include every registered source.
            return cert
        except (ValueError, KeyError, OSError) as error:errors.append(str(error))
    return None


def original_template(root, item, project):
    """Find a sealed historical native review as material, never as new proof."""
    from .continuous_rsi import snapshot
    base = Path(root)/'experience'
    policy = read(base/item['payload'])
    for cert in reversed(item['certificates']):
        try:
            check_motif_certificate(policy, base/cert['file'], item['sha256'])
            review = read(base/cert['file'])['native_review']; record_file = bounded_file(project, review['record_file'])
            if sha(record_file) != review['record_sha256']:continue
            record = read(record_file); origin = bounded_file(project, record['origin']); spec = read(origin/'task.json')
            if (record.get('adapter') != 'management_v3' or spec.get('role') in ('holdout', 'evaluate', 'benchmark')
                    or spec.get('learning_eligible') is False or spec.get('external_roots')):continue
            if sha(origin/'task.json') != record['task_sha256'] or snapshot(origin/'pristine') != spec['initial_snapshot']:continue
            quality = spec.get('quality', {})
            if quality.get('version') == QUALITY:
                if quality.get('goal', {}).get('state') != 'frozen':continue
                upgrade = False
            elif quality.get('version') in ('sss-management-quality-v3','sss-management-quality-v4') and quality.get('requirements'):
                upgrade = True
            else:continue
            return {'record': record, 'origin': str(origin), 'record_sha256': sha(record_file),
                    'seed': record['task_fingerprint'], 'upgrade_quality': upgrade}
        except (ValueError, KeyError, OSError):continue
    return None


def supplemental_reads(spec, record):
    """Freeze observed complete reads against original goal byte predicates."""
    expected = spec.get('initial_tree', {}).get('workspace', {}).get('files', {})
    delivered = Path(record.get('delivery', record['origin']+'/delivery'))/'reads'
    reads = [read(p) for p in delivered.glob('*.json')]
    checks = []
    for requirement in spec.get('quality', {}).get('requirements', []):
        if requirement.get('root_id', 'workspace') != 'workspace' or requirement.get('source_root', 'workspace') != 'workspace':continue
        kind = requirement['kind']; path = requirement['path']
        if kind == 'read':source = path
        elif kind == 'file':source = requirement['source']
        else:continue
        if source not in expected:continue
        if any(r.get('path') == 'workspace/'+path and r.get('sha256') == expected[source]
               and r.get('status') == 'readable' and r.get('truncated') is False for r in reads):
            checks.append({'source': source, 'path': path})
    return checks


def material_template(seed, job):
    """Migrate supported material metadata; old predicates and grants survive."""
    from .continuous_rsi import snapshot
    original = Path(seed['origin']); spec = read(original/'task.json'); directory = job/'material-template'
    checks = supplemental_reads(spec, seed['record'])
    if not seed.get('upgrade_quality') and not checks:return original
    from management_prepare import prepare
    lock = job/'material-migration.json'
    expected = {'original_task_sha256': sha(original/'task.json'), 'original_snapshot': snapshot(original/'pristine'),
                'original_quality': spec['quality'], 'target_quality': QUALITY, 'permissions_expanded': False,
                'complete_reads': checks}
    if expected['original_snapshot'] != spec['initial_snapshot']:
        raise ValueError('original migration material changed')
    if lock.exists():
        prior = read(lock)
        if any(prior[k] != v for k, v in expected.items()) or sha(directory/'task.json') != prior['task_sha256']:
            raise ValueError('frozen material migration changed')
        return directory
    if directory.exists():directory.rename(job/('interrupted-template-'+uuid4().hex))
    work = directory/'pristine'; work.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(original/'pristine', work)
    if snapshot(work) != expected['original_snapshot']:raise ValueError('material changed while copying')
    requirements = spec['quality']['requirements']
    if seed.get('upgrade_quality'):
        fresh = prepare(directory, work, task_id='migration-'+job.name, objective=spec['objective'],
                        owner=spec['owner'], workspace_id=spec['workspace_id'], quality=requirements,
                        role='native_certification')
        fresh['rules']['read_only'] = spec.get('rules', {}).get('read_only', False)
        fresh['allowed_operations'] = sorted(set(fresh['allowed_operations']) & set(spec['allowed_operations']))
        for name in ('approved_inputs','certification_fixed_sources'):
            if name in spec:fresh[name]=copy.deepcopy(spec[name])
    else:
        fresh = copy.deepcopy(spec); fresh['workspace'] = str(work)
        enrollment = read(original/'enrollment.json'); scenario = read(enrollment['scenario_file'])
        (directory/'prompt.md').write_text(enrollment['prompt'])
        scenario['prompt'] = str(directory/'prompt.md'); durable(directory/'scenario.json', scenario, exclusive=True)
    # Never copy old approvals, effects or provider state into a fresh task.
    durable(directory/'task.json', fresh, exclusive=True)
    durable(directory/'enrollment.json', {'prompt': (directory/'prompt.md').read_text(),
                                         'scenario_file': str(directory/'scenario.json'),
                                         'template_only': True, 'original_permissions_retained': True}, exclusive=True)
    if checks:durable(directory/'recertification-checks.json', {'complete_reads': checks}, exclusive=True)
    durable(lock, {**expected, 'task_sha256': sha(directory/'task.json')}, exclusive=True)
    return directory


def prior_rejection(root, item, runtime):
    """Do not repeatedly bill known failures for the same runtime and evidence."""
    base = Path(root)/'experience'
    historical = [p.parent for p in Path(root).parent.glob('*/learning/*/failure.json')]
    for job in sorted(set(historical)) + sorted((base/'jobs').glob('*')):
        if not (job/'failure.json').exists():continue
        try:
            lock = read(job/'candidate-lock.json'); policy = read(job/'policy.json') if (job/'policy.json').exists() else None
            candidate = read(job/'compiled.json') if (job/'compiled.json').exists() else None
            if candidate is None and lock.get('old_policy_file'):candidate = read(lock['old_policy_file']).get('artifact')
            if not candidate or shape('operation_graph',{'artifact':candidate}) != item['shape']:continue
            old = read(job/'certificate.json').get('runtime_source', {}) if (job/'certificate.json').exists() else lock.get('source_code', {})
            if not all(old.get(n) == h for n, h in runtime.items()):continue
            request = read(job/'request.json') if (job/'request.json').exists() else {}
            if request.get('target_contract') == TARGET_CONTRACT:
                if request['target'] == target_version(runtime):return str(job)
                continue
            # Legacy rejections bind their actual frozen native catalog too.
            native_file = job/'native-cert-record.json'
            if native_file.exists():
                from src.motif_core.offline.operation_graph import catalog
                record = read(native_file); schema = Path(record['origin'])/'tool-schemas.json'
                if sha(schema) == record['schemas_sha256'] and catalog(read(schema)) == current_contracts(runtime):return str(job)
            elif candidate.get('tool_contracts') and all(t == current_contracts(runtime).get(n) for n, t in candidate['tool_contracts'].items()):
                return str(job)
        except (ValueError, KeyError, OSError):continue
    return None


def maintain(cfg, root, all_records):
    """Called under the original worker lock; at most two jobs per queue pass."""
    from .continuous_rsi import ROOT, source_map, state_event
    from .continuous_motif_learning import frame, RecoveryPending
    from .management_recertification import recertify
    from .management_backup import budget_snapshot
    root = Path(root); runtime = sources(); version = target_version(runtime)
    catalog = synchronize(cfg); registry = ExperienceRegistry(root/'registry'); active = registry.load()
    stale = {e['entry_id'] for e in active['entries'] if e['state'] == 'active'
             and (e.get('runtime_source') != runtime or not policy_current(read(root/'registry'/e['payload']), runtime))}
    if stale:
        registry.publish(disable=stale, reason='runtime source incompatible; managed automatic re-certification required')
        state_event(root, 'experience_versions_invalidated', {'entries': sorted(stale), 'target': version})
    imported = []; attempted = []; deferred = []; handled = set()

    def run_request(request, job):
        try:
            result = recertify(cfg['config_file'], root/request['policy'], root/request['certificate'],
                               request['template'], job, worker_locked=True)
            attempted.append({'key': request['key'], 'job': str(job), **result})
        except RecoveryPending as error:
            attempted.append({'key': request['key'], 'job': str(job), 'status': 'pending', 'reason': str(error)})
        except (ValueError, KeyError, OSError) as error:
            failure = {'status': 'rejected', 'candidate_inactive': True, 'reason': str(error), 'failures_and_costs_retained': True}
            if not (job/'failure.json').exists():durable(job/'failure.json', failure, exclusive=True)
            attempted.append({'key': request['key'], 'job': str(job), **failure})

    # Resume the same frozen request before considering newer observations.
    for request_file in sorted((root/'experience/jobs').glob('*/request.json')):
        job = request_file.parent
        if (job/'failure.json').exists() or (job/'activation.json').exists():continue
        request = read(request_file)
        if request.get('adapter_format')=='sss-management-legacy-adapter-v1':continue
        handled.add(request['shape'])
        if (request['target'] != version or request['source'] != source_map()
                or request['config_sha256'] != cfg['config_sha256']):
            deferred.append({'key': request['key'], 'job': str(job), 'state': 'source_version_blocked'});continue
        if len(attempted) >= MAX_AUTOMATIC_JOBS:
            deferred.append({'key': request['key'], 'job': str(job), 'state': 'queued'});continue
        # Its pending admission retains the original reservation. The child runner
        # performs the existing per-stage budget checks without a cold restart.
        run_request(request, job)
    def priority(item):
        certs = [c.get('runtime_source', {}) for c in item['certificates']]
        distance = min((sum(c.get(n) != h for n, h in runtime.items()) for c in certs), default=999)
        return (distance, len(read(root/'experience'/item['payload']).get('artifact', {}).get('nodes', [])), item['key'])
    for item in sorted(catalog['entries'], key=priority):
        if item['kind'] != 'operation_graph' or item['shape'] in handled or item['compatibility']['state'] in ('adapter_required', 'proof_required'):continue
        handled.add(item['shape'])
        state = registry.load()
        if any(e['state'] == 'active' and e.get('runtime_source') == runtime
               and policy_current(read(root/'registry'/e['payload']), runtime)
               and shape(e['kind'], read(root/'registry'/e['payload'])) == item['shape'] for e in state['entries']):continue
        cert = eligible_certificate(root, item, runtime)
        if cert and not any(e['entry_id'] == item['artifact_digest'] for e in state['entries']):
            base = root/'experience'; entry = registry.entry('operation_graph', base/item['payload'], runtime, base/cert['file'])
            registry.publish([entry], expected=state['generation'], reason='managed migration of original current independent certificate')
            imported.append(item['key']);continue
        # A new clean ordinary witness is a new retry opportunity, never a new budget.
        seed = None
        def arrival(pair):
            index, record = pair; file = root/'records'/(record.get('session_id', '')+'.json')
            return (file.stat().st_mtime_ns if file.exists() else 0, index)
        for _, record in sorted(enumerate(all_records), key=arrival, reverse=True):
            if record.get('role') != 'ordinary' or record.get('adapter') != 'management_v3':continue
            try:
                f = frame(record)
                if f['spec'].get('external_roots'):continue
                if f['spec'].get('quality', {}).get('goal', {}).get('state') != 'frozen':continue
                old=read(root/'experience'/item['payload'])
                if old.get('format')=='sss-operation-flow-v3':
                    from src.motif_core.offline.control_flow import episodes
                    if not any(ep['root']==old['artifact']['root'] for ep in episodes(f)):continue
                elif not material_graph_observed(f,old['artifact']['nodes']):continue
                seed_job = root/'experience/jobs'/digest({'shape': item['shape'], 'target': version, 'seed': record['task_fingerprint']})
                if (seed_job/'failure.json').exists() or (seed_job/'activation.json').exists():continue
                seed = {'record': record, 'origin': record['origin'], 'seed': record['task_fingerprint']}
                break
            except (ValueError, KeyError, OSError):continue
        rejection = prior_rejection(root, item, runtime)
        if rejection and seed is None:
            deferred.append({'key': item['key'], 'state': 'awaiting_new_evidence', 'previous_job': rejection});continue
        seed = seed or original_template(root, item, ROOT)
        if not seed:
            deferred.append({'key': item['key'], 'state': 'material_required'});continue
        key = digest({'shape': item['shape'], 'target': version, 'seed': seed['seed']})
        job = root/'experience/jobs'/key
        if (job/'activation.json').exists() or (job/'failure.json').exists():continue
        if len(attempted) >= MAX_AUTOMATIC_JOBS:
            deferred.append({'key': item['key'], 'state': 'queued', 'job': str(job)});continue
        budget = budget_snapshot(ROOT)
        if (budget['learning_spent_usd']+budget['learning_reserved_usd']+cfg['limits']['budget_usd'] > cfg['learning_cap_usd']
                or budget['series']['estimated_usd']+budget['pending_usd']+cfg['limits']['budget_usd'] > cfg['series_cap_usd']):
            deferred.append({'key': item['key'], 'state': 'budget_blocked'});continue
        job.mkdir(parents=True, exist_ok=True, mode=0o700)
        template = material_template(seed, job)
        # Original native/ordinary envelopes already contain task/pristine/enrollment.
        candidate_cert = next((c for c in item['certificates'] if _valid_old_certificate(root, item, c)), None)
        if candidate_cert is None:
            deferred.append({'key': item['key'], 'state': 'proof_required'});continue
        request = {'key': item['key'], 'shape': item['shape'], 'target': version, 'seed': seed['seed'],
                   'target_contract': TARGET_CONTRACT,
                   'template': str(template), 'policy': 'experience/'+item['payload'],
                   'certificate': 'experience/'+candidate_cert['file'], 'source': source_map(),
                   'config_sha256': cfg['config_sha256'], 'original_budgets_retained': True}
        if not (job/'request.json').exists():durable(job/'request.json', request, exclusive=True)
        elif read(job/'request.json') != request:raise ValueError('frozen automatic migration request changed')
        run_request(request, job)
    from .management_legacy import maintain as maintain_legacy
    legacy=maintain_legacy(cfg,MAX_AUTOMATIC_JOBS-len(attempted))
    result = {'format': FORMAT, 'imported': imported, 'attempted': attempted, 'deferred': deferred,'legacy':legacy,
              'original_budgets_retained': True, 'target': version}
    durable(root/'experience/maintenance.json', result)
    synchronize(cfg)
    return result


def _valid_old_certificate(root, item, certificate):
    try:
        base = Path(root)/'experience'
        check_motif_certificate(read(base/item['payload']), base/certificate['file'], item['sha256'])
        return True
    except (ValueError, KeyError, OSError):return False


def needs_maintenance(cfg):
    """Free startup probe; finished rejections do not create a restart fee loop."""
    from .continuous_rsi import ROOT, source_map
    catalog = synchronize(cfg); root = Path(cfg['state_root']); runtime = sources()
    for job in catalog.get('jobs', []):
        if job['state'] != 'pending':continue
        request_file = root/job['job']/'request.json'
        if request_file.exists():
            request = read(request_file)
            if request['target'] == target_version(runtime) and request['source'] == source_map():return True
    for item in catalog['entries']:
        if item['kind'] != 'operation_graph' or item['compatibility']['state'] != 'recertification_required':continue
        if eligible_certificate(root, item, runtime):return True
        if not prior_rejection(root, item, runtime) and original_template(root, item, ROOT):return True
    from .management_legacy import pending as legacy_pending
    return legacy_pending(cfg)


def cli(argv=None):
    import argparse, importlib.util
    from .continuous_rsi import ROOT, load_config, initialize
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'sync', 'maintain'), nargs='?', default='status')
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args(argv)
    cfgfile = ROOT/'.local/rsi/daily-management-real-v3.json'
    cfg = load_config(cfgfile); root = initialize(cfg)
    if args.action == 'maintain':
        if not args.call_model:raise ValueError('explicit maintenance execution requires --call-model; status/sync are free')
        loader = importlib.util.spec_from_file_location('management_private_key', ROOT/'scenarios/literature-notes/run-live.py')
        module = importlib.util.module_from_spec(loader); loader.loader.exec_module(module)
        os.environ['DEEPSEEK_API_KEY'] = module.load_key(module.KEY_FILE, os.environ)
        from .continuous_motif_learning import drain
        return drain(cfgfile)
    if args.action == 'sync':synchronize(cfg)
    return summary(root)
