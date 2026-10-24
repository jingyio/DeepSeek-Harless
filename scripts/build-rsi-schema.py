"""Build the v1 wire contract using the already enforced DSH schema subset."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]


def obj(**fields):
    return dict(type='object', properties=fields, required=list(fields), additionalProperties=False)


def arr(item):
    return dict(type='array', items=item)


def enum(*values):
    return dict(type='string', enum=list(values))


def build():
    s, b, n = {'type': 'string'}, {'type': 'boolean'}, {'type': 'integer'}
    nullable = {'oneOf': [s, {'type': 'null'}]}
    nullable_count = {'oneOf': [n, {'type': 'null'}]}
    nullable_cost = {'oneOf': [{'type': 'number'}, {'type': 'null'}]}
    version = obj(id=s, sha256=s)
    versions = obj(motif=version, matcher=version)
    reference = obj(id=s, sha256=s, version=s)
    refs = arr(reference)
    payloads = {
        'provider_request': obj(id=s, task_id=s, ledger_ref=s, model=s,
                        phase=enum('booked', 'completed', 'failed', 'unknown'),
                        prompt_tokens=nullable_count, cache_hit_tokens=nullable_count,
                        cache_miss_tokens=nullable_count, output_tokens=nullable_count,
                        observed_peak_usd=nullable_cost, reserved_upper_usd=nullable_cost),
        'evidence': obj(id=s, task_id=s, subject=s, sha256=s, version=s,
                        role=enum('training', 'validation', 'current', 'test'),
                        status=enum('valid', 'invalidated'), observation_id=s,
                        origin=enum('tool', 'bash', 'python', 'user')),
        'operator': obj(id=s, operation=s, description=s,
                        source_kind=enum('tool', 'bash', 'python'),
                        structure_signature=arr(s), input_schema={}, output_schema={},
                        parameter_sources=arr(obj(parameter=s, source=enum('task_input', 'evidence', 'prior_output'), ref=s, pointer=s)),
                        dependencies=refs, effect=enum('read', 'workspace_write', 'external_write', 'opaque'),
                        code_sha256=nullable, opaque=b, certificate_ref=s),
        'execution_event': obj(id=s, task_id=s, sequence=n, call_id=s,
                        source_kind=enum('tool', 'bash', 'python'), operation=s,
                        phase=enum('started', 'succeeded', 'failed'),
                        arguments_sha256=s, result_sha256=nullable,
                        dependencies=refs, permission_ref=s, versions=versions,
                        provider_call_id=nullable, error=nullable),
        'runtime_request': obj(id=s, task_id=s, operator_id=s, operation=s,
                        arguments_sha256=s, dependencies=refs, versions=versions,
                        obligation_ref=s, state_version=s),
        'runtime_decision': obj(request_id=s, task_id=s,
                        action=enum('execute', 'handoff', 'reject'), reason=s,
                        versions=versions, evidence_ids=arr(s)),
        'diagnosis': obj(id=s, component=enum('motif', 'matcher'), reason=s,
                        base_version=version, feedback=refs),
        'candidate_patch': obj(id=s, diagnosis_id=s,
                        patch_kind=enum('rule_revision', 'motif_split', 'matcher_code_patch'),
                        component=enum('motif', 'matcher'), base_version=version,
                        next_version=version, compatible_versions=versions,
                        feedback=refs, affected_operator_ids=arr(s),
                        payload_sha256=s, diff_ref=s, training_task_ids=arr(s)),
        'validation_report': obj(id=s, candidate_id=s, candidate_sha256=s,
                        base_version=version, validator=version, passed=b,
                        checks=arr(obj(name=s, passed=b)), evidence=refs,
                        independent_task_ids=arr(s)),
        'publication_receipt': obj(id=s, candidate_id=s, report_id=s,
                        previous_versions=versions, next_versions=versions,
                        manifest_sha256=s),
        'rollback_receipt': obj(id=s, publication_id=s, reason=s,
                        previous_versions=versions, restored_versions=versions,
                        manifest_sha256=s),
    }
    return {'title': 'GeneLoop RSI Protocol v1',
            'description': 'Transport validation is not execution authorization. Trusted host guards remain mandatory.',
            'oneOf': [obj(protocol={'type': 'string', 'const': 'geneloop.rsi/v1'},
                          record_type={'type': 'string', 'const': kind}, payload=payload)
                      for kind, payload in payloads.items()]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = ROOT / 'schemas/rsi-protocol-v1.schema.json'
    rendered = json.dumps(build(), ensure_ascii=False, indent=2) + '\n'
    if args.check:
        if target.read_text(encoding='utf-8') != rendered:
            raise SystemExit('RSI schema differs; run python scripts/build-rsi-schema.py')
    else:
        target.write_text(rendered, encoding='utf-8')
