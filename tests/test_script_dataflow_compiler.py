"""AST dependency diagnostics, not model/cost experiments."""
import ast
import json
from src.adapters.script_dataflow_compiler import slices, observe_slices, literal_result_fields


def test_literal_default_fields_are_not_presented_as_completed_computation():
    source = "result={'count':len(rows),'missing':{'name':[]},'groups':[]}\nprint(result)"
    assert literal_result_fields(source, 'result') == ['/value/missing/name', '/value/groups']
    assert literal_result_fields("result={'groups':[]}\nresult['groups'].append(x)", 'result') == []
    assert literal_result_fields("result=compute(rows)\nprint(result)", 'result') == []


SOURCE = '''import json
rows=json.load(open('rows.json'))
lines=['number|status']
for r in rows:
    lines.append(str(r['number'])+'|'+r['status'])
table='\\n'.join(lines)
sections=[{'heading':'A specific paper and its current scientific conclusion', 'paragraphs':[table]}]
json.dump(sections,open('report.json','w'))
'''


def test_mines_a_table_inside_one_effectful_tool_call_without_caching_conclusions(tmp_path):
    (tmp_path/'code').mkdir()
    (tmp_path/'code/rows.json').write_text(json.dumps([{'number':1,'status':'unknown'}]))
    command="python3 - <<'PY'\n"+SOURCE+'PY'
    rows=observe_slices(command,'make current report',tmp_path,'', 'task','call')
    table=next(r for r in rows if r['expression_witness']['target']=='table')
    assert 'A specific paper' not in table['template']
    assert 'report.json' not in table['template']
    assert 'append' in table['template']
    assert table['inputs'][0]['format']=='json'
    assert table['interface']['input_fields']==['number','status']
    assert '__MOTIF_INPUT_0__' in table['template']
    assert 'value' not in table['literal_selectors'], 'compiler JSON wrapper is not historical task data'


def test_original_literals_keep_binding_guards_even_when_equal_to_compiler_labels(tmp_path):
    (tmp_path/'code').mkdir()
    (tmp_path/'code/rows.json').write_text(json.dumps({'value': 3}))
    source="import json\nrows=json.load(open('rows.json'))\nselected=rows['value']\nprint(selected)\n"
    rows=observe_slices("python3 - <<'PY'\n"+source+'PY','select',tmp_path,'','task','call')
    assert 'value' in next(r for r in rows if r['expression_witness']['target']=='selected')['literal_selectors']


def test_mutating_loops_and_imports_preserved_but_unrelated_data_excluded():
    table=next(r for r in slices(SOURCE) if r['target']=='table')
    nodes=list(ast.walk(ast.parse(table['source'])))
    assert any(isinstance(n,ast.For) for n in nodes)
    assert any(isinstance(n,ast.Import) for n in nodes)
    assert 'sections' not in table['source']


def test_unsupported_alias_and_control_scope_is_not_guessed():
    assert slices('def transform(x):\n def nested(y):\n  return y\n return nested(x)\ny=transform(1)\nprint(y)')==[]
    assert slices('try:\n x=1\nexcept Exception:\n x=2\nprint(x)')==[]


def test_pure_parser_function_and_completed_mutating_loop_are_lifted(tmp_path):
    (tmp_path/'inputs').mkdir();(tmp_path/'code').mkdir()
    (tmp_path/'inputs/current.txt').write_text('a\nb\n')
    source="""def parse(line):
    return {'title':line.upper()}
raw=open('inputs/current.txt').read()
records=[]
for line in raw.splitlines():
    records.append(parse(line))
import json
json.dump(records,open('records.json','w'))
"""
    rows=observe_slices("python3 - <<'PY'\n"+source+'PY','parse',tmp_path,'','task','call')
    completed=[r for r in rows if r['expression_witness']['target']=='records' and 'for line in' in r['template']]
    assert len(completed)==1
    assert 'def parse' in completed[0]['template']
    assert 'json.dump(' not in completed[0]['template']
    assert "'w'" not in completed[0]['template']


def test_slice_still_requires_registered_inputs_and_existing_readonly_admission(tmp_path):
    (tmp_path/'code').mkdir()
    commands=['import subprocess\nx=subprocess.check_output(["ls"])\nprint(x)',
              'x="old scientific judgment"\nprint(x)',
              'x=open("/etc/passwd").read()\nprint(x)']
    for source in commands:
        assert observe_slices("python3 - <<'PY'\n"+source+'\nPY','',tmp_path,'','task','call')==[]
