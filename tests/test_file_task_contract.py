"""Mechanical contracts reject wrong effects/forged coverage without regrading old results."""
import importlib.util, json, sys, zipfile
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parents[1]/'scenarios/file-management'

@pytest.fixture
def factory(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(HERE)); modules = {}
    for name in ('common','file_tools','collection_tools','report_tools','task_contract','task_tools'):
        spec = importlib.util.spec_from_file_location(name,HERE/(name+'.py')); module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,module); spec.loader.exec_module(module); modules[name] = module
    fm = modules['file_tools']; common = modules['common']; tt = modules['task_tools']; tc = modules['task_contract']; rc = modules['report_tools']
    monkeypatch.setattr(fm,'ROOT',tmp_path); monkeypatch.setattr(fm,'DATA',tmp_path/'data')
    def make(family,files,extra=None,ops=None):
        root = tmp_path/'data'/family; root.mkdir(parents=True)
        (root/'.experiment-copy').write_text('test')
        for name,data in files.items():
            p = root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data if isinstance(data,bytes) else data.encode())
        contract = {'version':tc.VERSION,'kind':family,**(extra or {})}
        spec = {'workspace':str(root),'task_id':'test-'+family,'family':family,'objective':'test','rules':{},
                'initial_snapshot':common.snapshot(root),'allowed_operations':ops if ops is not None else ['convert' if family=='convert' else 'move'],
                'report_contract':{'version':rc.CONTRACT_VERSION,'kind':'task_result'},'task_contract':contract}
        scene = tt.TaskScene(spec,tmp_path/'.local'/family); events = []
        def call(name,**args):
            seq = len(events)+1; cid = 'c'+str(seq)
            events.append({'type':'tool/call','seq':seq,'data':{'callId':cid,'name':common.PREFIX+name,'arguments':json.dumps(args)}})
            value = getattr(scene,name)(**args)
            events.append({'type':'tool/result','seq':seq+1,'data':{'message':{'content':[{'type':'tool-result','toolCallId':cid,'isError':False,'content':[{'type':'text','text':json.dumps(value)}]}]}}})
            return value
        call('read_task')
        return scene,call,events,modules
    return make

def ids(scene): return {r['path']:r['file_id'] for r in scene.list_files()['files']}
def gather(scene,call,paths):
    current = ids(scene); packet = call('select_files',file_ids=[current[n] for n in paths]); rows = []
    for name in paths:
        pinned = call('pin_file',file_id=current[name]); rows.append(call('read_file',source_id=pinned['source_id']))
    call('collect_reads',collection_id=packet['collection_id'],source_ids=[r['source_id'] for r in rows]); return rows
def report(scene,call):
    call('submit_report',summary='Actual result',file_ids=list(ids(scene).values()),gaps=[],report_kind='task_result')
    return json.loads((scene.output/'report.json').read_text())
def verify(scene,call,events,mods): return mods['task_contract'].verify_task(scene.spec,report(scene,call),scene.output,events)

def test_global_rename_preview_rejects_per_extension_numbering_then_corrects(factory):
    scene,call,events,mods = factory('rename',{'inbox/A.TXT':'a','inbox/nested/b.md':'b','inbox/z.txt':'z','inbox/无后缀':'u','keep/unchanged.txt':'keep'})
    old = mods['common'].snapshot(scene.root); current = ids(scene)
    with pytest.raises(mods['file_tools'].ToolError,match='global rename'):
        call('preview_actions',actions=[{'op':'move','file_ids':[current['inbox/z.txt']],'destination':'normalized/txt/item_02.txt'}])
    assert mods['common'].snapshot(scene.root)==old and not scene.plans
    targets = mods['task_contract'].rename_targets(scene.spec)
    p = call('preview_actions',actions=[{'op':'move','file_ids':[current[n]],'destination':d} for n,d in targets.items()])
    call('execute_plan',plan_id=p['plan_id']); assert verify(scene,call,events,mods)['passed']
    assert (scene.root/'normalized/no-extension/item_04').read_text()=='u'

def test_empty_input_must_be_actually_read_and_gathered_before_classification(factory):
    scene,call,events,mods = factory('content_classify',{'inbox/empty.txt':'','inbox/hit.md':'NEW TOPIC here'},
        {'routes':[{'literal':'new topic','destination_prefix':'research/'}]})
    gather(scene,call,['inbox/hit.md']); current = ids(scene)
    action = [{'op':'move','file_ids':[current['inbox/hit.md']],'destination':'research/hit.md'}]
    with pytest.raises(mods['file_tools'].ToolError,match='empty text'): call('preview_actions',actions=action)
    before = mods['common'].snapshot(scene.root)
    # Reading the missing member without a complete exact collection is still insufficient.
    pinned = call('pin_file',file_id=current['inbox/empty.txt']); empty = call('read_file',source_id=pinned['source_id'])
    assert empty['status']=='readable' and empty['text']==''
    with pytest.raises(mods['file_tools'].ToolError,match='exact required'): call('preview_actions',actions=action)
    assert mods['common'].snapshot(scene.root)==before
    gather(scene,call,['inbox/empty.txt','inbox/hit.md']); p = call('preview_actions',actions=action); call('execute_plan',plan_id=p['plan_id'])
    assert verify(scene,call,events,mods)['passed'] and (scene.root/'inbox/empty.txt').is_file()

def test_conversion_allows_actual_post_conversion_read_but_rejects_unrelated_reads(factory):
    scene,call,events,mods = factory('convert',{'inbox/a.md':'converted text','keep/unrelated.txt':'do not read'},
        {'conversions':[{'source':'inbox/a.md','destination':'converted/a.txt','format':'text'}]})
    gather(scene,call,['inbox/a.md']); p = call('preview_actions',actions=[{'op':'convert','file_ids':[ids(scene)['inbox/a.md']],'destination':'converted/a.txt','format':'text'}]); call('execute_plan',plan_id=p['plan_id'])
    pinned = call('pin_file',file_id=ids(scene)['converted/a.txt']); call('read_file',source_id=pinned['source_id'])
    result = verify(scene,call,events,mods); assert result['passed'] and result['output_verification_read_paths']==['converted/a.txt']
    pinned = call('pin_file',file_id=ids(scene)['keep/unrelated.txt']); call('read_file',source_id=pinned['source_id'])
    assert any('outside declared' in e for e in verify(scene,call,events,mods)['errors'])

def test_output_read_requires_current_journal_and_real_execution_before_read(factory):
    scene,call,events,mods = factory('convert',{'inbox/a.txt':''},{'conversions':[{'source':'inbox/a.txt','destination':'converted/a.txt','format':'text'}]})
    gather(scene,call,['inbox/a.txt']); p = call('preview_actions',actions=[{'op':'convert','file_ids':[ids(scene)['inbox/a.txt']],'destination':'converted/a.txt','format':'text'}]); call('execute_plan',plan_id=p['plan_id'])
    pinned = call('pin_file',file_id=ids(scene)['converted/a.txt']); call('read_file',source_id=pinned['source_id'])
    assert verify(scene,call,events,mods)['passed']
    execute = next(e for e in events if e['type']=='tool/result' and e['data']['message']['content'][0]['toolCallId']==next(x['data']['callId'] for x in events if x['type']=='tool/call' and x['data']['name'].endswith('execute_plan')))
    execute['seq']=10000
    assert any('preceded' in e for e in verify(scene,call,events,mods)['errors'])

def test_forged_read_artifact_without_native_result_cannot_pass(factory):
    scene,call,events,mods = factory('content_classify',{'inbox/empty.md':''},{'routes':[{'literal':'topic','destination_prefix':'research/'}]})
    gather(scene,call,['inbox/empty.md']); assert verify(scene,call,events,mods)['passed']
    events[:] = [e for e in events if not(e['type']=='tool/result' and e['data']['message']['content'][0]['content'][0]['text'].find('"source_id"')>=0)]
    assert any('native tool events' in e for e in verify(scene,call,events,mods)['errors'])

def test_read_graph_version_is_unchanged_and_effect_contract_has_separate_version(factory):
    scene,call,events,mods = factory('rename',{'inbox/a.txt':'a'})
    for name in ('select_files','pin_file','read_file','collect_reads'):
        assert getattr(mods['task_tools'].TaskScene,name) is getattr(mods['report_tools'].ReportScene,name)
    task = scene.read_task()
    assert scene.execution_version == mods['report_tools'].report_version()
    assert task['task_execution_version_sha256'] != scene.execution_version
    assert task['reading_contract']['required_input_paths']==[]

def test_permissions_are_not_expanded_by_task_contract(factory):
    scene,call,events,mods = factory('rename',{'inbox/a.txt':'a'},ops=[])
    with pytest.raises(mods['file_tools'].ToolError,match='authorization'):
        call('preview_actions',actions=[{'op':'move','file_ids':[ids(scene)['inbox/a.txt']],'destination':'normalized/txt/item_01.txt'}])
    assert not scene.plans

def test_unknown_contract_versions_or_fields_are_rejected(factory):
    scene,call,events,mods = factory('rename',{'inbox/a.txt':'a'}); tc = mods['task_contract']
    for values in ({'version':'future','kind':'rename'},{'version':tc.VERSION,'kind':'rename','allow_any_reads':True},{'version':tc.VERSION,'kind':'rename','source_prefix':'../outside/'}):
        with pytest.raises(ValueError): tc.TaskContract.model_validate(values)

def test_classification_exposes_only_applicable_fields_and_actionable_paths(factory):
    scene,call,events,mods = factory('content_classify',{'inbox/nested/a.txt':'topic'},{'routes':[{'literal':'topic','destination_prefix':'research/'}]})
    task=scene.read_task();assert 'destination_prefix' not in task['task_contract'] and 'conversions' not in task['task_contract']
    assert task['classification_targets']==[{'source':'inbox/nested/a.txt','allowed_destinations':['research/nested/a.txt']}]
    gather(scene,call,['inbox/nested/a.txt'])
    with pytest.raises(mods['file_tools'].ToolError,match='research/nested/a.txt'):
        call('preview_actions',actions=[{'op':'move','file_ids':[ids(scene)['inbox/nested/a.txt']],'destination':'normalized/research/a.txt'}])

def test_all_empty_task_has_no_effect_plan_and_can_deliver_after_actual_reads(factory):
    scene,call,events,mods = factory('content_classify',{'inbox/a.txt':'','inbox/b.md':' \n\t'},{'routes':[{'literal':'topic','destination_prefix':'research/'}]})
    gather(scene,call,['inbox/a.txt','inbox/b.md'])
    with pytest.raises(mods['file_tools'].ToolError,match='stay in place'):
        call('preview_actions',actions=[{'op':'move','file_ids':[ids(scene)['inbox/a.txt']],'destination':'research/a.txt'}])
    with pytest.raises(mods['file_tools'].ToolError,match='submit_report directly'):call('preview_actions',actions=[])
    assert verify(scene,call,events,mods)['passed'] and not scene.plans

def test_explicit_optional_rename_reads_before_and_after_move_are_version_bound(factory):
    scene,call,events,mods = factory('rename',{'inbox/a.txt':'a','keep/b.txt':'b'},{'allow_optional_original_reads':True})
    for path in ['inbox/a.txt','keep/b.txt']:
        pin=call('pin_file',file_id=ids(scene)[path]);call('read_file',source_id=pin['source_id'])
    p=call('preview_actions',actions=[{'op':'move','file_ids':[ids(scene)['inbox/a.txt']],'destination':'normalized/txt/item_01.txt'}]);call('execute_plan',plan_id=p['plan_id'])
    pin=call('pin_file',file_id=ids(scene)['normalized/txt/item_01.txt']);call('read_file',source_id=pin['source_id'])
    assert verify(scene,call,events,mods)['passed']
