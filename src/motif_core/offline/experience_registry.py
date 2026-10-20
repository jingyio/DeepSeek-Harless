"""Immutable unified experience versions. Admission never promotes a mere candidate."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def durable(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path if exclusive else path.with_suffix(path.suffix + '.tmp')
    with temporary.open('x' if exclusive else 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    if not exclusive:
        temporary.replace(path)


def check_script_certificate(program, path, raw_sha):
    cert = read(path)
    if cert.get('status') not in ('certified', 'certified_v2') or cert.get('holdout_used') is not False:
        raise ValueError('independent certificate required; holdout evidence prohibited')
    if not any(r.get('script_digest') == program['script_digest'] and r.get('sha256') == raw_sha
               for r in cert.get('scripts', [])):
        raise ValueError('certificate does not bind original candidate bytes')
    training = {r['task_fingerprint'] for r in program['training']}
    eligible = [r for r in cert.get('reviews', []) if r.get('actual_candidate_execution', True)]
    reviews = [r for r in eligible if
               (r.get('script_digest') == program['script_digest'] if 'script_digest' in r else
                r.get('workflow_id', r.get('profile_id', '')).split(':')[0] == program['workflow_id'])]
    # Historical v1 reviews label task family in task_id, not workflow_id.
    if not reviews:
        reviews = [r for r in eligible if program['workflow_id'] in r.get('task_id', '')]
    if len(reviews) < 2 or len({r['task_fingerprint'] for r in reviews}) != len(reviews):
        raise ValueError('at least two independent certification materials required')
    for r in reviews:
        if r['task_fingerprint'] in training or r.get('role', 'certify') != 'certify':
            raise ValueError('training/certification/holdout overlap')
        p = Path(r['outcome_file'])
        if sha(p) != r['outcome_sha256']:
            raise ValueError('certification outcome changed')
        outcome = read(p)
        if outcome['role'] != 'certify' or not outcome['acceptance']['passed'] or not outcome['receipt_verified']:
            raise ValueError('failed independent candidate execution')
        if outcome['run']['upstream_requests'] or outcome.get('acceptance_repairs', 0):
            raise ValueError('ordinary repair cannot certify a failed whole program')
    return cert


def check_motif_certificate(policy, path, raw_sha):
    """New continuous admission needs native graph proof and independent actual use."""
    cert = read(path)
    if cert.get('format')=='sss-management-seed-attestation-v1':
        from src.adapters.management_seed import validate_certificate
        return validate_certificate(policy,path,raw_sha)
    v2=policy.get('format')=='sss-operation-graph-v2';v3=policy.get('format')=='sss-operation-flow-v3'
    if (cert.get('status') != ('certified_motif_v3' if v3 else 'certified_motif_v2' if v2 else 'certified_motif_v1') or cert.get('holdout_used') is not False
            or cert.get('policy_digest') != policy['policy_digest'] or cert.get('payload_sha256') != raw_sha
            or cert.get('quality_and_permission_required') is not True):
        raise ValueError('independent actual Motif certificate required')
    if v2 and (cert.get('certification_contract')!='sss-operation-certification-v2' or policy['artifact'].get('certification_contract')!='sss-operation-certification-v2'):
        raise ValueError('versioned operation certification required')
    if v3 and (cert.get('certification_contract')!='sss-operation-certification-v3' or policy['artifact'].get('certification_contract')!='sss-operation-certification-v3'):
        raise ValueError('versioned control-flow certification required')
    if sha(cert['candidate_lock_file']) != cert['candidate_lock_sha256']:
        raise ValueError('Motif candidate lock changed')
    training = set(policy['artifact']['source_task_fingerprints'])
    reviews = [cert['native_review'], *cert.get('reviews', [])]
    if len(cert.get('reviews', [])) != 2 or len({r['task_fingerprint'] for r in reviews}) != len(reviews):
        raise ValueError('new native witness and two independent Motif executions required')
    for review in reviews:
        if review['task_fingerprint'] in training or sha(review['record_file']) != review['record_sha256']:
            raise ValueError('Motif evidence overlap or mutation')
        record = read(review['record_file'])
        if (record['role'] != review['role'] or not record['accepted'] or not record['lifecycle_verified']
                or record['provider_mode'] != 'real' or record['metrics'].get('acceptance_repairs')
                or record.get('observed_usage_complete') is False):
            raise ValueError('failed or repaired Motif certification')
        if review['role'] == 'candidate_certification' and (record['policy_digest'] != policy['policy_digest']
                or record['verified_motif_batches'] < 1 or record['deferred']):
            raise ValueError('candidate did not actually execute its Motif')
        if (v2 or v3) and review['role']=='candidate_certification':
            if review.get('completion_count',0)<1 or sha(Path(record['run_dir'])/'experience-audit.jsonl')!=review.get('audit_sha256'):raise ValueError('repeated operation proof changed')
    if policy.get('format')=='sss-management-program-v1':
        from src.adapters.management_legacy import verify_program_delivery
        if cert.get('certification_contract')!='sss-management-program-certification-v1' or policy['artifact'].get('certification_contract')!=cert['certification_contract']:
            raise ValueError('current bounded program certification required')
        if sha(cert['native_program_proof_file'])!=cert['native_program_proof_sha256']:raise ValueError('native program proof changed')
        if policy['artifact'].get('delivery_contract')!='sss-exact-management-program-delivery-v1' or sha(cert['native_program_delivery_file'])!=cert['native_program_delivery_sha256']:raise ValueError('exact program delivery proof required')
        for review in reviews:verify_program_delivery(policy['artifact']['recipe'],read(review['record_file']))
        for review in cert['reviews']:
            record=read(review['record_file']);audit=Path(record['run_dir'])/'experience-audit.jsonl'
            if sha(audit)!=review.get('audit_sha256'):raise ValueError('program actual audit changed')
            completions=[json.loads(l) for l in audit.read_text().splitlines() if json.loads(l).get('kind')=='management_program_complete']
            if len(completions)!=1 or completions[0]['entry_id']!=policy['policy_digest'] or completions[0]['copy_stages']!=sum(s['op']=='copy_map' for s in policy['artifact']['recipe']['steps']):
                raise ValueError('complete actual program execution required')
    legacy=policy.get('artifact',{}).get('legacy_adapter',{})
    if legacy.get('family')=='reentry':
        for review in cert['reviews']:
            if review.get('completion_count',0)!=2:raise ValueError('two independently model-selected reading episodes required')
    return cert


class ExperienceRegistry:
    """One offline writer; immutable objects/snapshots with an atomic current pointer."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def object(self, source):
        source = Path(source)
        value = source.read_bytes()
        h = hashlib.sha256(value).hexdigest()
        relative = 'objects/' + h + '.json'
        p = self.root / relative
        if p.exists():
            if p.read_bytes() != value:
                raise ValueError('immutable experience object changed')
        else:
            p.parent.mkdir(exist_ok=True, mode=0o700)
            with p.open('xb') as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            p.chmod(0o600)
        return relative, h

    def entry(self, kind, payload, runtime_source, certificate=None):
        if kind in ('operation_graph','management_program') and certificate is None:raise ValueError('operation/program requires independent actual certification')
        value = read(payload)
        field = 'script_digest' if kind.startswith('script_') else 'library_digest' if kind == 'read_library' else 'policy_digest'
        h = value.get(field)
        if h != digest({k: v for k, v in value.items() if k != field}):
            raise ValueError('invalid original experience signature')
        if kind.startswith('script_'):
            if certificate is None:
                raise ValueError('script requires independent certification')
            check_script_certificate(value, certificate, sha(payload))
            if kind == 'script_v2' and value['runtime_source'] != {n: runtime_source[n] for n in value['runtime_source']}:
                raise ValueError('script runtime closure differs from certification')
        else:
            if kind == 'read_library' and value.get('status') != 'certified_read_library':
                raise ValueError('unvalidated read library')
            artifacts = value.get('artifacts', []) if kind == 'read_library' else [value.get('artifact', {})]
            if not artifacts:
                raise ValueError('empty Motif library')
            for a in artifacts:
                training = a.get('source_task_fingerprints', [])
                if (a.get('status') not in ('trace_validated_read_only', 'trace_validated_effectful')
                        or a.get('certified_digest') != digest({k: v for k, v in a.items() if k != 'certified_digest'})
                        or len(training) < 2 or len(set(training)) != len(training)
                        or not a.get('validation_task_fingerprint') or a['validation_task_fingerprint'] in training):
                    raise ValueError('uncertified or overlapping Motif evidence')
            if certificate is not None:
                check_motif_certificate(value, certificate, sha(payload))
        relative, raw = self.object(payload)
        entry = {'entry_id': h, 'kind': kind, 'payload': relative, 'sha256': raw,
                 'artifact_digest': h, 'runtime_source': runtime_source, 'state': 'active'}
        if certificate:
            file, cert_sha = self.object(certificate)
            entry['certificate'] = {'file': file, 'sha256': cert_sha}
        return entry

    def load(self, file=None):
        if file is None:
            pointer = read(self.root / 'current.json')
            file = self.root / pointer['file']
            if sha(file) != pointer['sha256']:
                raise ValueError('registry pointer changed')
        state = read(file)
        if state['registry_digest'] != digest({k: v for k, v in state.items() if k != 'registry_digest'}):
            raise ValueError('registry signature changed')
        for entry in state['entries']:
            if sha(self.root / entry['payload']) != entry['sha256']:
                raise ValueError('experience payload changed')
        return state

    def publish(self, additions=(), disable=(), reason='independent certification', expected=None):
        previous = self.load() if (self.root / 'current.json').exists() else None
        generation = previous['generation'] if previous else 0
        if expected is not None and expected != generation:
            raise ValueError('registry writer/version conflict')
        entries = {r['entry_id']: dict(r) for r in previous['entries']} if previous else {}
        for key in disable:
            if key in entries:
                entries[key].update(state='disabled', disabled_reason=reason)
        for row in additions:
            if row['entry_id'] in entries:
                raise ValueError('cannot silently replace or reenable an old experience')
            entries[row['entry_id']] = {**row, 'activated_generation': generation + 1}
        state = {'schema_version': 1, 'format': 'sss-experience-registry-v1', 'generation': generation + 1,
                 'parent_digest': previous['registry_digest'] if previous else None, 'reason': reason,
                 'entries': list(entries.values()), 'automatic_selection_uses_profile_id': False}
        state['registry_digest'] = digest(state)
        file = self.root / 'versions' / (f'{generation + 1:06d}.json')
        durable(file, state, exclusive=True)
        durable(self.root / 'current.json', {'file': str(file.relative_to(self.root)), 'sha256': sha(file),
                                            'registry_digest': state['registry_digest']})
        return file
