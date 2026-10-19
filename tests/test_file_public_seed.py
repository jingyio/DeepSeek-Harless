"""Free public release checks; original private certification is not required."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def test_seeds_install_per_account_without_cloud_or_reactivating_disabled_entries():
    base=ROOT/'.local/file-seed-tests'/uuid4().hex
    code="""import json,sys;sys.path.insert(0,'scenarios/file-management')
from management_web import default_config
from src.adapters.continuous_rsi import load_config,initialize
from src.motif_core.offline.experience_registry import ExperienceRegistry
p=default_config(True);cfg=load_config(p);r=ExperienceRegistry(__import__('pathlib').Path(cfg['state_root'])/'registry')
state=r.load();assert len([e for e in state['entries'] if e['state']=='active'])>=1
entry=state['entries'][0]['entry_id'];r.publish(disable=[entry],reason='free disable diagnostic')
initialize(cfg);state=r.load();assert next(e for e in state['entries'] if e['entry_id']==entry)['state']=='disabled'
assert not list((__import__('pathlib').Path(cfg['state_root'])/'records').glob('*.json'))
print(json.dumps({'state':cfg['state_root'],'entries':len(state['entries']),'paid_calls':0}))"""
    results=[]
    for account in ['one','two']:
        env={**os.environ,'HARLESS_MANAGEMENT_PRIVATE_ROOT':str(base/account),'DEEPSEEK_API_KEY':''}
        results.append(json.loads(subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,env=env,text=True)))
    assert results[0]['state']!=results[1]['state']
    assert all(row['paid_calls']==0 for row in results)


def test_seed_release_contains_only_policies_and_sanitized_certification():
    release=ROOT/'motif-libraries/file-v3';manifest=json.loads((release/'entry.json').read_text())
    assert manifest['raw_private_evidence_published'] is False
    for name in manifest['files']:
        raw=(release/name).read_text()
        assert '/Users/' not in raw and '/home/' not in raw and 'record_file' not in raw
        assert name.startswith(('policies/','certificates/'))
    for entry in manifest['entries']:
        cert=json.loads((release/entry['certificate']).read_text())
        assert cert['grants_execution'] is False and cert['holdout_used'] is False
        assert all(w['accepted'] and not w['repairs'] and w['observed_usage_complete'] for w in cert['witnesses'])
