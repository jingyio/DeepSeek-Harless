import importlib.util,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('management_entry',ROOT/'scripts/management.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

@pytest.mark.parametrize('args',[['--budget-usd','6'],['--request-limit=97'],['--max-output','4001'],['--run-budget-usd=26'],['--run-request-limit','4001'],['--scenario=portfolio-v1'],['--frozen'],['--budget-usd'],['--mock','--real-model']])
def test_entry_rejects_scope_or_budget_expansion_without_launch(args,monkeypatch):
    monkeypatch.setattr(entry.subprocess,'run',lambda *a,**kw:pytest.fail('unapproved process launched'))
    with pytest.raises(ValueError):entry.main(args)

def test_daily_entry_defaults_to_real_and_keeps_original_caps(monkeypatch):
    calls=[]
    def launch(args,**kw):
        calls.append(args)
        assert kw['env']['DEEPSEEK_API_KEY']=='fixture-only-placeholder'
        return type('Done',(),{'returncode':0})()
    monkeypatch.setenv('DEEPSEEK_API_KEY','fixture-only-placeholder');monkeypatch.setattr(entry.subprocess,'run',launch)
    assert entry.main(['--port','3093'])==0
    assert '--real-model' in calls[0]
    for name,value in [('--scenario','files'),('--budget-usd','5'),('--request-limit','96'),('--max-output','4000')]:assert calls[0][calls[0].index(name)+1]==value
    assert entry.main(['--mock'])==0 and '--real-model' not in calls[1]

def test_damaged_zip_command_retains_failure_without_creating_import(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(entry,'ROOT',tmp_path)
    archive=tmp_path/'damaged.zip';archive.write_bytes(b'not a zip archive')
    assert entry.run(['migrate','--archive',str(archive),'--destination',str(tmp_path/'new')])==2
    assert not (tmp_path/'new').exists()
    rows=[json.loads(p.read_text()) for p in (tmp_path/'.local/management-backup-logs').glob('*.json')]
    assert rows[0]['action']=='command_failed' and rows[0]['error_type']=='BadZipFile'
    assert archive.read_bytes()==b'not a zip archive'
