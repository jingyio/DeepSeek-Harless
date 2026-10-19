import importlib.util,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('management_entry',ROOT/'scripts/management.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

@pytest.mark.parametrize('args',[['--budget-usd','6'],['--request-limit=97'],['--max-output','4001'],['--max-output-tokens=4001'],['--run-budget-usd=26'],['--run-request-limit','4001'],['--scenario=portfolio-v1'],['--frozen'],['--budget-usd'],['--mock','--real-model']])
def test_entry_rejects_scope_or_budget_expansion_without_launch(args,monkeypatch):
    monkeypatch.setattr(entry.subprocess,'run',lambda *a,**kw:pytest.fail('unapproved process launched'))
    with pytest.raises(ValueError):entry.main(args)

def test_daily_entry_defaults_to_real_and_keeps_original_caps(monkeypatch):
    calls=[]
    maintenance=[];monkeypatch.setattr(entry,'start_maintenance',lambda env:maintenance.append(env['DEEPSEEK_API_KEY']))
    def launch(args,**kw):
        calls.append(args)
        assert kw['env']['DEEPSEEK_API_KEY']=='fixture-only-placeholder'
        return type('Done',(),{'returncode':0})()
    monkeypatch.setenv('DEEPSEEK_API_KEY','fixture-only-placeholder');monkeypatch.setattr(entry.subprocess,'run',launch)
    assert entry.main(['--port','3093'])==0
    assert '--real-model' in calls[0]
    for name,value in [('--scenario','new-scene'),('--budget-usd','5'),('--request-limit','96'),('--max-output-tokens','4000')]:assert calls[0][calls[0].index(name)+1]==value
    assert entry.main(['--mock'])==0 and '--real-model' not in calls[1]
    assert maintenance==[], 'web launch must not run an unrelated legacy learning profile'
    assert calls[0][1].endswith('scripts/harness-web.py')

def test_damaged_zip_command_retains_failure_without_creating_import(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(entry,'ROOT',tmp_path)
    archive=tmp_path/'damaged.zip';archive.write_bytes(b'not a zip archive')
    assert entry.run(['migrate','--archive',str(archive),'--destination',str(tmp_path/'new')])==2
    assert not (tmp_path/'new').exists()
    rows=[json.loads(p.read_text()) for p in (tmp_path/'.local/management-backup-logs').glob('*.json')]
    assert rows[0]['action']=='command_failed' and rows[0]['error_type']=='BadZipFile'
    assert archive.read_bytes()==b'not a zip archive'


@pytest.mark.parametrize('mode,automatic',[('observe',True),('learn',False)])
def test_automatic_startup_honors_observe_and_disabled_worker(mode,automatic,monkeypatch):
    sys.path.insert(0,str(ROOT/'scenarios/file-management'))
    import management_web
    from src.adapters import continuous_rsi,experience_library
    monkeypatch.setattr(management_web,'default_config',lambda real:Path('.local/fixture.json'))
    monkeypatch.setattr(continuous_rsi,'load_config',lambda _: {'adapter':'management_v3','provider_mode':'real','mode':mode,
                                                            'auto_worker':automatic,'state_root':'.local/rsi/fixture'})
    monkeypatch.setattr(experience_library,'needs_maintenance',lambda cfg:True)
    monkeypatch.setattr(continuous_rsi,'launch_worker',lambda *a,**k:pytest.fail('disabled automatic learning launched a worker'))
    assert entry.start_maintenance({'DEEPSEEK_API_KEY':'fixture-only-placeholder'}) is None


def test_automatic_startup_passes_existing_private_environment_to_enabled_worker(monkeypatch):
    sys.path.insert(0,str(ROOT/'scenarios/file-management'))
    import management_web
    from src.adapters import continuous_rsi,experience_library
    cfgfile=Path('.local/fixture.json');calls=[]
    monkeypatch.setattr(management_web,'default_config',lambda real:cfgfile)
    monkeypatch.setattr(continuous_rsi,'load_config',lambda _: {'adapter':'management_v3','provider_mode':'real','mode':'learn',
                                                            'auto_worker':True,'state_root':'.local/rsi/fixture'})
    monkeypatch.setattr(experience_library,'needs_maintenance',lambda cfg:True)
    monkeypatch.setattr(continuous_rsi,'launch_worker',lambda *a,**k:calls.append((a,k)) or 123)
    env={'DEEPSEEK_API_KEY':'fixture-only-placeholder'}
    assert entry.start_maintenance(env)==123
    assert calls==[((cfgfile,'.local/rsi/fixture'),{'environment':env})]
