"""Admission counterexamples; no cloud model or learned scientific conclusions."""
import pytest
from src.adapters.artifact_motif_compiler import validate_source, file_contract, program_from_witness


def test_data_driven_renderer_admitted_and_identity_changes_with_code(tmp_path):
    path = tmp_path / 'content.json'
    path.write_text('{"title":"new source","slides":[{"heading":"current"}]}', encoding='utf-8')
    source = '''import sys,json
from pathlib import Path
if __name__ == '__main__':
    data=json.load(open(sys.argv[1]))
    Path(sys.argv[2], 'result.txt').write_text(data['title'])
'''
    a = program_from_witness(source, ['content.json','out'], {0:path}, 1, {})
    b = program_from_witness(source.replace('result.txt','new.txt'), ['content.json','out'], {0:path}, 1, {})
    assert a['id'] != b['id']
    assert a['input_argument_indices'] == [0]
    assert a['output_argument_index'] == 1


@pytest.mark.parametrize('source', [
    'import subprocess\nsubprocess.run(sys.argv)',
    'import sys\neval(sys.argv[1])',
    'import os,sys\nprint(os.environ)',
    'import sys\nopen("/etc/passwd").read()',
    'import sys\nprint(sys.__dict__)',
    'from os import system\nimport sys\nsystem(sys.argv[1])',
    'import sys\nprint("old document answer")',
])
def test_unsafe_or_constant_program_rejected(source):
    with pytest.raises(ValueError):
        validate_source(source)


def test_duplicate_headers_and_invalid_utf8_fail_closed(tmp_path):
    p = tmp_path / 'rows.csv'
    p.write_text('x,x\n1,2\n', encoding='utf-8')
    with pytest.raises(ValueError, match='unique_header'):
        file_contract(p)
    p.write_bytes(b'\xff')
    with pytest.raises(UnicodeError):
        file_contract(p)


def test_declared_predicate_is_distinguished_from_copied_output_literal(tmp_path):
    p = tmp_path / 'content.json'
    p.write_text('{"verdict":"未通过"}', encoding='utf-8')
    source = '''"""The verdict label 未通过 denotes a failing row."""
import sys,json
d=json.load(open(sys.argv[1]))
ok='未通过' not in d['verdict']
print('DeltaBatch cached title',ok)
'''
    result = program_from_witness(source, ['content.json','out'], {0:p}, 1, {})
    assert result['interface_comparison_literals'] == ['未通过']
    assert 'DeltaBatch cached title' in result['literal_selectors']
    again = program_from_witness(source + "print('未通过')\n", ['content.json','out'], {0:p}, 1, {})
    assert '未通过' not in again['interface_comparison_literals']
