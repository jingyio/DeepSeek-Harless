"""Boundary evidence regression; synthetic diagnostics, no model calls."""
import importlib.util
import json
from pathlib import Path
from src.adapters.script_motif_compiler import sha, digest


def test_real_boundary_collector_checks_saved_program_without_head_filter(tmp_path):
    spec = importlib.util.spec_from_file_location('script_learning', Path(__file__).parents[1] / 'scripts/learn-script-motifs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    workspace = tmp_path / 'workspace'
    (workspace / 'code').mkdir(parents=True)
    program = "import json\nrows=json.load(open('rows.json'))\nprint(len(rows))\n"
    (workspace / 'code/read.py').write_text(program)
    (workspace / 'code/rows.json').write_text('[1,2]')
    (tmp_path / 'effective-config.json').write_text(json.dumps({'workspace': str(workspace), 'provider_mode':'real','mode':'baseline'}))
    (tmp_path / 'task-state.json').write_text('{"status":"completed"}')
    (tmp_path / 'task.json').write_text('{"content":[{"type":"text","text":"check current rows"}]}')
    arguments={'command':'python3 read.py','description':'read current rows'}
    events=[{'type':'tool/call','data':{'callId':'native','name':'bash','arguments':arguments}},
            {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':'native','content':[{'type':'text','text':'2\n'}]}]}}}]
    (tmp_path / 'events.jsonl').write_text('\n'.join(map(json.dumps,events)))
    boundary={'call_id':'native','is_error':False,'arguments_sha256':digest(arguments),'before':{'files':{'code/read.py':{'sha256':sha(program)},'code/rows.json':{'sha256':sha('[1,2]')}}}}
    (tmp_path / 'reuse-boundaries.jsonl').write_text(json.dumps(boundary))
    rows=module.collect(tmp_path)
    assert rows['candidates'], rows['rejected']
    assert all(r['witness']['input_evidence_scope']=='matching_native_pre_execution_snapshot' for r in rows['candidates'])
    (workspace / 'code/rows.json').write_text('[3]')
    changed=module.collect(tmp_path)
    assert not changed['candidates']
    assert any(r['reason']=='input_changed_since_native_boundary' for r in changed['rejected'])
