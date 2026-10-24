"""Public hand-authored diagnostic fixtures, not learned/real benchmark evidence."""
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.rsi_protocol import envelope


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fixtures():
    code = sha((ROOT / 'examples/rsi-protocol-v1/group_count.py').read_bytes())
    versions = {'motif': {'id': 'diagnostic-motif-v1', 'sha256': code},
                'matcher': {'id': 'f02-admission-v1', 'sha256': sha((ROOT / 'src/adapters/rsi_protocol.ts').read_bytes())}}
    args = {'rows': [{'group': 'workshop'}, {'group': 'poster'}, {'group': 'workshop'}]}
    ref = dict(id='current-table', sha256=sha(json.dumps(args, ensure_ascii=False, separators=(',', ':')).encode()), version='1')
    evidence = envelope('evidence', dict(**ref, task_id='registration-summary-B', subject='current input table',
                    role='current', status='valid', observation_id='read-table-B', origin='tool'))
    row_schema = dict(type='object', properties={'group': {'type': 'string'}}, required=['group'], additionalProperties=False)
    op = dict(id='group-count', operation='table.group_count', description='按当前选定 group 列计数；不判断哪些报名有效。',
              source_kind='python', structure_signature=['table.group_count'],
              input_schema=dict(type='object', properties={'rows': dict(type='array', items=row_schema)}, required=['rows'], additionalProperties=False),
              output_schema=dict(type='object', properties={'counts': dict(type='object', additionalProperties=True)}, required=['counts'], additionalProperties=False),
              parameter_sources=[dict(parameter='/rows', source='task_input', ref='current-table', pointer='/rows')],
              dependencies=[], effect='read', code_sha256=code, opaque=False, certificate_ref='hand-authored-diagnostic-only')
    operator = envelope('operator', op)
    tool_op = deepcopy(op)
    tool_op.update(id='tool-group-count', source_kind='tool', code_sha256=None)
    bash_op = deepcopy(op)
    bash_op.update(id='opaque-bash', source_kind='bash', effect='opaque', opaque=True,
                   code_sha256=sha(b'opaque historical bash bytes'), description='无法解析内部依赖的 Bash 保留 opaque，不能准入执行。')
    request = envelope('runtime_request', dict(id='request-B', task_id='registration-summary-B',
                       operator_id='group-count', operation=op['operation'],
                       arguments_sha256=sha(json.dumps(args, ensure_ascii=False, separators=(',', ':')).encode()),
                       dependencies=[ref], versions=versions, obligation_ref='current-semantic-choice-B', state_version='state-B-1'))
    train_ref = dict(id='training-failure', sha256=sha(b'training-counterexample'), version='1')
    valid_ref = dict(id='validation-run', sha256=sha(b'independent-diagnostic-validation'), version='1')
    training = envelope('evidence', dict(**train_ref, task_id='train-A', subject='counterexample', role='training', status='valid', observation_id='failed-A', origin='python'))
    validation = envelope('evidence', dict(**valid_ref, task_id='validation-C', subject='independent diagnostic', role='validation', status='valid', observation_id='verified-C', origin='python'))
    diagnoses = [envelope('diagnosis', dict(id='diagnosis-'+component, component=component, reason='demonstration only', base_version=versions[component], feedback=[train_ref])) for component in ('motif','matcher')]
    patches = []
    for kind in ('rule_revision', 'motif_split', 'matcher_code_patch'):
        component = 'matcher' if kind == 'matcher_code_patch' else 'motif'
        patches.append(envelope('candidate_patch', dict(id='candidate-' + kind, diagnosis_id='diagnosis-'+component, patch_kind=kind,
                    component=component, base_version=versions[component], next_version=dict(id=component+'-v2', sha256=sha(kind.encode())),
                    compatible_versions=versions, feedback=[train_ref], affected_operator_ids=['group-count'],
                    payload_sha256=sha(b'diagnostic patch bytes'), diff_ref='diagnostic.diff', training_task_ids=['train-A'])))
    candidate_sha = sha((json.dumps(patches[0], ensure_ascii=False, indent=2)+'\n').encode())
    report = envelope('validation_report', dict(id='report-1', candidate_id=patches[0]['payload']['id'],
                      candidate_sha256=candidate_sha, base_version=versions['motif'], validator=dict(id='independent-diagnostic-validator', sha256=sha(b'validator-v1')),
                      passed=True, checks=[dict(name='diagnostic contract', passed=True)], evidence=[valid_ref], independent_task_ids=['validation-C']))
    decision = envelope('runtime_decision', dict(request_id='request-B', task_id='registration-summary-B', action='execute',
                        reason='diagnostic-only', versions=versions, evidence_ids=['current-table']))
    events = [envelope('execution_event', dict(id='example-event-'+kind, task_id='registration-summary-B', sequence=0, call_id='example-call-'+kind,
                        source_kind=kind, operation='table.group_count', phase='succeeded', arguments_sha256=request['payload']['arguments_sha256'],
                        result_sha256=sha(b'diagnostic receipt'), dependencies=[ref], permission_ref='diagnostic-only-grant',
                        versions=versions, provider_call_id=None, error=None)) for kind in ('tool','bash','python')]
    next_versions = deepcopy(versions)
    next_versions['motif'] = patches[0]['payload']['next_version']
    publication = envelope('publication_receipt', dict(id='publication-1', candidate_id=patches[0]['payload']['id'], report_id='report-1',
                           previous_versions=versions, next_versions=next_versions, manifest_sha256=sha(b'diagnostic manifest v2')))
    rollback = envelope('rollback_receipt', dict(id='rollback-1', publication_id='publication-1', reason='diagnostic only',
                        previous_versions=next_versions, restored_versions=versions, manifest_sha256=sha(b'diagnostic manifest v1')))
    from src.adapters.rsi_protocol import provider_ledger_record
    provider = provider_ledger_record(dict(request_id=1, model='deepseek-flash', reserved_upper_usd=0.01), task_id='diagnostic-only', ledger_ref='synthetic-ledger')
    records = [evidence, operator, envelope('operator', tool_op), envelope('operator', bash_op), request,
               training, validation, *diagnoses, *patches, report, decision, *events, publication, rollback, provider]
    invalid = []
    for name, change in [
        ('unknown-protocol', lambda r: r.update(protocol='geneloop.rsi/v9')),
        ('unknown-field', lambda r: r['payload'].update(automatic_authorization=True)),
        ('missing-task', lambda r: r['payload'].pop('task_id')),
        ('bad-digest', lambda r: r['payload'].update(arguments_sha256='not-a-hash')),
    ]:
        r = deepcopy(request)
        change(r)
        invalid.append(dict(name=name, record=r))
    r = deepcopy(operator)
    r['payload']['input_schema']['minProperties'] = 1
    invalid.append(dict(name='unsupported-nested-schema', record=r))
    return dict(kind='hand_authored_protocol_diagnostic_not_benchmark', versions=versions,
                tasks={'A': dict(goal='科研实验数据报告', arguments={'rows': [{'group': 'control'}, {'group': 'treatment'}, {'group': 'control'}]}, expected={'counts': {'control': 2, 'treatment': 1}}),
                       'B': dict(goal='活动报名汇总', arguments=args, expected={'counts': {'poster': 1, 'workshop': 2}})},
                records=records, invalid=invalid)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = ROOT / 'examples/rsi-protocol-v1/fixtures.json'
    rendered = json.dumps(fixtures(), ensure_ascii=False, indent=2) + '\n'
    if args.check:
        if target.read_text(encoding='utf-8') != rendered:
            raise SystemExit('RSI fixtures differ; run python scripts/rsi-protocol-fixtures.py')
    else:
        target.write_text(rendered, encoding='utf-8')
