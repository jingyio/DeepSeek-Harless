"""Producer/consumer configuration diagnostics; no paid calls."""
import importlib.util
from pathlib import Path
import pytest
import json
import sys
from types import SimpleNamespace

def module():
    path=Path(__file__).parents[1]/'scripts/run-script-motif-experiment.py'
    spec=importlib.util.spec_from_file_location('script_experiment_learning',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

def test_one_store_binds_both_learning_and_loading():
    m=module();store=m.ROOT/'.local/test-rsi-config'
    original={'mode':'execute'}
    result,selected=m.learning_config(original,store)
    assert result['learningStore']==str(selected)==str(store)
    assert 'learningStore' not in original
    assert m.learning_config(result,None)==(result,store)

def test_mismatched_or_public_stores_are_rejected():
    m=module();store=m.ROOT/'.local/test-rsi-config'
    with pytest.raises(ValueError,match='producer_consumer_mismatch'):
        m.learning_config({'learningStore':str(store)},store/'other')
    with pytest.raises(ValueError,match='private_learning_scope'):
        m.learning_config({},m.ROOT/'public-store')


@pytest.mark.parametrize('outcome',['published','empty','failed'])
def test_worker_publication_retains_parent_and_failure_does_not_replace_pointer(tmp_path,monkeypatch,outcome):
    path=Path(__file__).parents[1]/'scripts/advance-script-motifs.py'
    spec=importlib.util.spec_from_file_location('advance_script_learning_test',path)
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    monkeypatch.setattr(worker,'ROOT',tmp_path)
    task=tmp_path/'.local/task';held=tmp_path/'.local/held';store=tmp_path/'.local/store'
    for p in [task,held,store]:p.mkdir(parents=True)
    (task/'task-state.json').write_text(json.dumps({'user_id':'owner','mode':'baseline','status':'completed'}))
    (task/'effective-config.json').write_text(json.dumps({'user_id':'owner','provider_mode':'real'}))
    for p in [task,held]:(p/'events.jsonl').write_text('{}\n')
    (store/'history.json').write_text(json.dumps({'user':'owner','tasks':[str(held)],'reset_history':False}))
    parent={'user':'owner','digest':'parent','file':'round-aaa/library.json'}
    (store/'latest.json').write_text(json.dumps(parent))
    monkeypatch.setattr(worker,'collect_reuse',lambda _:[])
    monkeypatch.setattr(worker,'collect_probes',lambda _:[])
    monkeypatch.setattr(worker,'compile_reuse',lambda *args:{'contracts':[],'digest':'reuse'})
    def compile(command,**kwargs):
        output=Path(command[command.index('--output')+1]);output.mkdir()
        (output/'library.json').write_text(json.dumps({'programs':[{'id':'new'}] if outcome=='published' else [],'digest':'new','heldout_task_id':'held'}))
        return SimpleNamespace(returncode=1 if outcome=='failed' else 0,stdout='',stderr='')
    monkeypatch.setattr(worker.subprocess,'run',compile)
    monkeypatch.setattr(sys,'argv',['advance','--task',str(task),'--store',str(store),'--user','owner'])
    worker.main()
    status=json.loads((task/'script-learning-status.json').read_text())
    pointer=json.loads((store/'latest.json').read_text())
    if outcome=='published':
        assert pointer['digest']=='new' and pointer['parent_digest']=='parent'
        assert status['training_task_ids']==['task'] and status['heldout_task_id']=='held'
        assert status['compilation_model_requests']==0
        lineage=json.loads((store/status['round']/'lineage.json').read_text())
        assert lineage['evidence'][1]['task_id']=='task'
    else:
        assert pointer==parent
        assert status['status']==('failed' if outcome=='failed' else 'no_qualified_programs')
