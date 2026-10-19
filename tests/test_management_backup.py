import json,os,zipfile
from pathlib import Path
import pytest
from src.adapters import management_backup as b

@pytest.fixture
def case(tmp_path):
    p=tmp_path/'original';d=p/'.local/management-copies/profile/workspaces/a';d.mkdir(parents=True)
    (d/'first.txt').write_text('same user bytes');(d/'second.txt').write_text('same user bytes');(d/'empty').mkdir()
    (p/'.local/deepseek.env').write_text('DEEPSEEK_API_KEY=diagnostic-placeholder')
    arc=tmp_path/'backup.zip';receipt=b.backup(p,arc)
    return p,d,arc,receipt

def test_deduplicated_backup_verifies_but_restored_files_are_independent(case):
    p,d,arc,r=case;m=b.verify_backup(arc)
    assert r['files']==2 and r['unique_blobs']==1 and not any('deepseek.env' in x['path'] for x in m['snapshot']['files'])
    assert b.restore(p,arc,p)['restored_roots']==[]
    (d/'first.txt').unlink();(d/'second.txt').unlink();(d/'empty').rmdir();d.rmdir();d.parent.rmdir();d.parent.parent.rmdir();d.parent.parent.parent.rmdir()
    restored=b.restore(p,arc,p);assert restored['restored_roots']==['.local/management-copies']
    assert (d/'empty').is_dir() and (d/'first.txt').read_text()=='same user bytes'
    (d/'first.txt').write_text('changed after recovery');assert (d/'second.txt').read_text()=='same user bytes'
    with pytest.raises(ValueError,match='existing data differs'):b.restore(p,arc,p)

def rewrite(arc,change):
    with zipfile.ZipFile(arc) as z:rows={n:z.read(n) for n in z.namelist()}
    m=json.loads(rows['manifest.json']);change(m,rows);m['manifest_sha256']=b.digest({k:v for k,v in m.items() if k!='manifest_sha256'});rows['manifest.json']=json.dumps(m).encode()
    bad=arc.with_name('bad-'+os.urandom(4).hex()+'.zip')
    with zipfile.ZipFile(bad,'w') as z:
        for n,v in rows.items():z.writestr(n,v)
    return bad

@pytest.mark.parametrize('attack',['escape','blob','negative-budget','symlink','extra-member'])
def test_untrusted_archive_is_rejected_before_destination_writes(case,attack):
    p,d,arc,r=case
    def attack_archive(m,rows):
        if attack=='escape':m['snapshot']['files'][0]['path']='../../outside'
        elif attack=='blob':rows['blobs/'+m['snapshot']['files'][0]['sha256']]=b'changed'
        elif attack=='negative-budget':m['budget']['series']['estimated_usd']=-1
        elif attack=='symlink':m['snapshot']['directories'].append('/absolute')
        else:rows['../outside']=b'bad'
    bad=rewrite(arc,attack_archive);destination=p.parent/'new'
    with pytest.raises((ValueError,KeyError)):b.migrate(p,bad,destination)
    assert not destination.exists() and (d/'first.txt').read_text()=='same user bytes'

def test_live_owner_and_existing_output_are_not_overwritten(case):
    p,d,arc,r=case
    with pytest.raises(ValueError,match='already exists'):b.backup(p,arc)
    f=p/'.local/web/runs/active/process.json';f.parent.mkdir(parents=True);f.write_text(json.dumps({'harness_pid':os.getpid()}))
    with pytest.raises(ValueError,match='stop the native service'):b.backup(p,p.parent/'live.zip')

def test_torn_snapshot_retains_partial_and_failure_receipt(case,monkeypatch):
    p,d,arc,r=case;original=b.scan;counter=0
    def change(*a,**kw):
        nonlocal counter
        counter+=1
        if counter==2:(d/'first.txt').write_text('concurrent change')
        return original(*a,**kw)
    monkeypatch.setattr(b,'scan',change)
    target=p.parent/'torn.zip'
    with pytest.raises(ValueError,match='changed during snapshot'):b.backup(p,target)
    assert not target.exists() and list(target.parent.glob('torn.zip.partial-*'))
    assert any(json.loads(f.read_text())['action']=='backup_failed' for f in (p/'.local/management-backup-logs').glob('*.json'))

def test_cold_migration_preserves_archive_and_budget_without_old_authority(case,monkeypatch):
    p,d,arc,r=case
    def money(m,rows):m['budget']={'series':{'attempts':11,'upstream_requests':50,'estimated_usd':2.5,'actual_bill_verified':False},'pending_usd':.3,'learning_spent_usd':1.2,'learning_reserved_usd':.1}
    archive=rewrite(arc,money);target=p.parent/'different-checkout';result=b.migrate(p,archive,target)
    assert result['passed'] and not result['old_tasks_resumed'] and not result['old_candidates_automatically_activated']
    assert b.hash_file(result['archive'])==b.hash_file(archive)
    assert (Path(result['imported_user_files'])/'profile/workspaces/a/first.txt').read_text()=='same user bytes'
    assert not (target/'.local/rsi').exists()
    assert b.migrate(p,archive,target)['idempotent']
    assert b.imported_budget(target)['series']['estimated_usd']==2.5
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scenarios/file-management'))
    import experiment
    monkeypatch.setattr(experiment,'ROOT',target);monkeypatch.setattr(experiment,'outcomes',lambda:[])
    assert experiment.accounting()=={'attempts':11,'upstream_requests':50,'estimated_usd':2.8,'actual_bill_verified':False}
    marker=target/'.local/management-imports/current.json';v=json.loads(marker.read_text());v['budget']['series']['estimated_usd']=0;marker.write_text(json.dumps(v))
    with pytest.raises(ValueError,match='receipt changed'):b.imported_budget(target)
    with pytest.raises(ValueError,match='requires cold migrate'):b.restore(p,archive,target)

def test_confirmed_reused_pid_is_observed_without_stopping_unrelated_process(case,monkeypatch):
    p,d,arc,r=case
    f=p/'.local/web/runs/old/process.json';f.parent.mkdir(parents=True);f.write_text(json.dumps({'harness_pid':os.getpid(),'port':3083}))
    monkeypatch.setattr(b,'process_image',lambda pid:'/system/unrelated-daemon')
    assert b.backup(p,p.parent/'new.zip')['files']==3
    assert any(json.loads(f.read_text())['action']=='stale_service_pid' for f in (p/'.local/management-backup-logs').glob('*.json'))
    monkeypatch.setattr(b,'process_image',lambda pid:None)
    with pytest.raises(ValueError,match='stop the native service'):b.backup(p,p.parent/'unknown.zip')

def test_only_generated_runtime_dependencies_are_excluded(case):
    p,d,arc,r=case
    generated=p/'.local/web/runs/old/dsh/profiles/node_modules';generated.mkdir(parents=True)
    (generated/'sdk').symlink_to(d,target_is_directory=True)
    m=b.verify_backup(b.backup(p,p.parent/'deps.zip')['archive'])
    assert not any('/node_modules/' in f['path'] for f in m['snapshot']['files'])
    user=d/'node_modules';user.mkdir();(user/'user.txt').write_text('user data')
    assert any(f['path'].endswith('node_modules/user.txt') for f in b.scan(p)['files'])
    (user/'external').symlink_to(d,target_is_directory=True)
    with pytest.raises(ValueError,match='does not follow symlinks'):b.scan(p)

def test_current_and_legacy_provider_credential_stores_are_excluded(case):
    p,d,arc,r=case
    for relative in ('.local/web/runs/old/dsh/.credentials.yaml','.local/rsi/profile/web-dsh/.credentials.yaml'):
        f=p/relative;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('fixture credential placeholder')
    result=b.backup(p,p.parent/'without-stores.zip');m=b.verify_backup(result['archive'])
    assert not any(Path(f['path']).name=='.credentials.yaml' for f in m['snapshot']['files'])
    assert result['files']==2 and m['credentials_included'] is False
