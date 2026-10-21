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


@pytest.mark.parametrize('outcome',['published','empty','failed','description_updated'])
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
        (output/'library.json').write_text(json.dumps({'programs':[{'id':'new'}] if outcome in ['published','description_updated'] else [],'digest':'new','heldout_task_id':'held'}))
        return SimpleNamespace(returncode=1 if outcome=='failed' else 0,stdout='',stderr='')
    monkeypatch.setattr(worker.subprocess,'run',compile)
    if outcome=='description_updated':
        (store/'description-learning.json').write_text('{}')
        previous={'programs':[]};previous['digest']=worker.digest(previous)
        (store/'round-aaa').mkdir()
        (store/'round-aaa/library.json').write_text(json.dumps(previous))
        parent['digest']=previous['digest']
        (store/'latest.json').write_text(json.dumps(parent))
        def update(library,store,output):
            return {**library,'digest':'description-version'}, {'status':'updated','model_requests':2}
        monkeypatch.setattr(worker,'learn_descriptions',update)
        monkeypatch.setattr(worker,'retain_previous_descriptions',lambda library,status,*args:(library,status))
    monkeypatch.setattr(sys,'argv',['advance','--task',str(task),'--store',str(store),'--user','owner'])
    worker.main()
    status=json.loads((task/'script-learning-status.json').read_text())
    pointer=json.loads((store/'latest.json').read_text())
    if outcome in ['published','description_updated']:
        assert pointer['digest']==('description-version' if outcome=='description_updated' else 'new') and pointer['parent_digest']==parent['digest']
        for key in ['file','reuse_file']:
            assert pointer[key].startswith(status['round']+'/') and '\\' not in pointer[key]
        assert status['training_task_ids']==['task'] and status['heldout_task_id']=='held'
        assert status['compilation_model_requests']==(2 if outcome=='description_updated' else 0)
        if outcome=='description_updated':
            assert json.loads((store/status['round']/'description-base-library.json').read_text())['digest']=='new'
        lineage=json.loads((store/status['round']/'lineage.json').read_text())
        assert lineage['evidence'][1]['task_id']=='task'
    else:
        assert pointer==parent
        assert status['status']==('failed' if outcome=='failed' else 'no_qualified_programs')


@pytest.mark.parametrize('state',['failed','cancelled'])
def test_negative_opt_in_accepts_settled_failures_without_teaching_positive_success(tmp_path,monkeypatch,state):
    path=Path(__file__).parents[1]/'scripts/advance-script-motifs.py'
    spec=importlib.util.spec_from_file_location('negative_worker_test',path)
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    monkeypatch.setattr(worker,'ROOT',tmp_path)
    task=tmp_path/'.local/task';store=tmp_path/'.local/store'
    task.mkdir(parents=True);store.mkdir(parents=True)
    for name,value in [('task-state.json',{'user_id':'owner','mode':'baseline','status':state}),
                       ('effective-config.json',{'user_id':'owner','provider_mode':'real'})]:
        (task/name).write_text(json.dumps(value))
    (task/'events.jsonl').write_text('{}\n')
    (store/'negative-learning.json').write_text('{}')
    lib={'rules':[{'retry_policy':'prompt_only'}]};lib['digest']=worker.digest(lib)
    monkeypatch.setattr(worker,'compile_positive',lambda *a:pytest.fail('failed task entered positive compiler'))
    monkeypatch.setattr(worker,'learn_negatives',lambda tasks,*a:(lib,{'status':'reviewed','model_requests':2}))
    monkeypatch.setattr(sys,'argv',['advance','--task',str(task),'--store',str(store),'--user','owner'])
    worker.main()
    assert json.loads((store/'history.json').read_text())['tasks']==[]
    assert json.loads((store/'negative-history.json').read_text())['tasks']==[str(task)]
    pointer=json.loads((store/'latest.json').read_text())
    assert 'file' not in pointer and pointer['negative_digest']==lib['digest']
    assert pointer['negative_file'].endswith('/negative-library.json') and '\\' not in pointer['negative_file']
    assert json.loads((task/'script-learning-status.json').read_text())['compilation_model_requests']==2
    monkeypatch.setattr(worker,'certify_library',lambda *a:None)
    monkeypatch.setattr(worker,'learn_negatives',lambda *a:(None,{'status':'failed','model_requests':1,'reason':'rejected_review'}))
    worker.main()
    retained=json.loads((store/'latest.json').read_text())
    assert retained['negative_digest']==lib['digest']
    assert json.loads((task/'script-learning-status.json').read_text())['inherited_assets']==['negative_file']
    (store/'negative-learning.json').unlink()
    with pytest.raises(ValueError,match='settled_owner'):
        worker.main()
