"""Deterministic admission diagnostics; not paid task quality evidence."""
import pytest
from src.adapters.script_motif_compiler import compile_script,extract,file_contract

def test_parameterizes_current_file_names(tmp_path):
    a=tmp_path/'first.json';b=tmp_path/'renamed.json'
    a.write_text('{"items":[1,2]}');b.write_text('{"items":[9]}')
    source='import json\nx=json.load(open("%s"))\nprint(len(x["items"]))'
    first=compile_script(source%'first.json',{'first.json':file_contract(a)})
    second=compile_script(source%'renamed.json',{'renamed.json':file_contract(b)})
    assert first['id']==second['id']
    assert 'first.json' not in first['template']
    assert '__MOTIF_INPUT_0__' in first['template']

@pytest.mark.parametrize('source',[
    'import subprocess\nsubprocess.run(["true"])',
    'open("x.json","w").write("bad")',
    'from pathlib import Path\nPath("x.json").unlink()',
    'import zipfile\nzipfile.ZipFile("x.json").extractall("/tmp")',
    'getattr(open,"__call__")("x.json")',
    '_sm_expected.clear()',
    'print(open("/etc/passwd").read()); print(open("x.json").read())',
])
def test_rejects_effectful_or_unbound_programs(source):
    with pytest.raises(ValueError):compile_script(source,{'x.json':{'suffix':'.json','format':'json'}})

def test_does_not_strip_unmodeled_shell_steps():
    for command in ['python3 -c "print(1)" | head','echo before && python3 -c "print(1)"',"python3 - <<'PY'\nprint(1)\nPY\nrm x"]:
        with pytest.raises(ValueError):extract(command)
    assert extract("cd /work && python3 - <<'PY'\nprint(1)\nPY")==('/work','print(1)')

def test_readonly_regex_script_does_not_require_json_ir():
    p=compile_script('import re\ns=open("references.bib").read()\nprint(len(re.findall(r"@article",s)))',{'references.bib':{'suffix':'.bib','format':'text'}})
    assert p['language']=='python'


def test_new_saved_source_is_bound_to_current_command_not_old_file(tmp_path):
    (tmp_path/'code').mkdir()
    command="cat > read.py <<'PY'\nprint(open('inputs/current.bib').read())\nPY\npython3 read.py"
    assert extract(command,tmp_path)[1]=="print(open('inputs/current.bib').read())"
    for tail in [' | head','; rm x',' && echo extra']:
        with pytest.raises(ValueError):extract(command+tail,tmp_path)


def test_real_heredoc_forms_keep_body_and_reject_shell_expansion_or_tail():
    for prefix in ["python3 << 'EOF'","python3 - << 'EOF'",'python <<EOF']:
        assert extract(prefix+'\nprint(1)\nEOF')==('/work','print(1)')
    for command in ["python3 <<EOF\nprint('$HOME')\nEOF", "python3 << 'EOF\"\nprint(1)\nEOF", "python3 << 'EOF'\nprint(1)\nEOF\nrm data"]:
        with pytest.raises(ValueError):extract(command)
