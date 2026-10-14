"""Actual fixed-verifier rejection, immutable evidence and corrected file postconditions."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1]
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def snapshot(root):return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}
@pytest.fixture
def case():
 name='acceptance-test-'+uuid4().hex;private=ROOT/'.local'/name;work=ROOT/'testpdf/file-management-experiment'/name
 (work/'inbox').mkdir(parents=True);private.mkdir();(work/'.experiment-copy').write_text(name);(work/'inbox/a.txt').write_text('original bytes')
 spec={'workspace':str(work),'task_id':name,'family':'rename','objective':'Global numbering','rules':{},'allowed_operations':['move'],'initial_snapshot':snapshot(work)}
 task=private/'task.json';task.write_text(json.dumps(spec));delivery=private/'delivery';delivery.mkdir()
 yield {'private':private,'work':work,'task':task,'spec':spec,'delivery':delivery,'sha':hashlib.sha256(task.read_bytes()).hexdigest()}
 shutil.rmtree(private);shutil.rmtree(work)
def receipt(case):
 body={'task_id':case['spec']['task_id'],'summary':'claimed done','file_ids':[],'gaps':[],'final_snapshot':snapshot(case['work'])}
 p=case['delivery']/'report.json';p.write_text(json.dumps(body))
 return {'status':'delivered','artifact':str(p),'artifact_sha256':digest(body),'input_sha256':digest(case['spec'])}
def check(case,round_no,value):
 result=subprocess.run([sys.executable,str(ROOT/'scripts/validate-file-delivery.py'),'--task-file',str(case['task']),'--task-sha256',case['sha'],'--delivery-root',str(case['delivery']),'--archive-root',str(case['private']/'archive'),'--round',str(round_no)],input=json.dumps({'receipt':value,'events':[]}),text=True,capture_output=True)
 return result.returncode,json.loads(result.stdout)
def move_correct(case):
 dest=case['work']/'normalized/txt/item_01.txt';dest.parent.mkdir(parents=True);(case['work']/'inbox/a.txt').rename(dest)
def test_failed_first_stage_is_retained_after_corrected_second_stage(case):
 value=receipt(case);code,first=check(case,0,value);assert code==0 and not first['passed']
 move_correct(case);code,second=check(case,1,receipt(case));assert code==0 and second['passed']
 prior=case['private']/'archive/round-00';assert json.loads((prior/'result.json').read_text())['passed'] is False
 assert (prior/'workspace/inbox/a.txt').read_text()=='original bytes'
 assert (case['private']/'archive/round-01/workspace/normalized/txt/item_01.txt').read_text()=='original bytes'
def test_permission_change_cannot_become_a_repair(case):
 value=receipt(case);case['task'].write_text(json.dumps({**case['spec'],'allowed_operations':['move','quarantine']}))
 code,result=check(case,0,value);assert code==2 and result['fatal'] and 'frozen task changed' in str(result['errors'])
def test_correct_files_with_forged_receipt_still_fail(case):
 move_correct(case);value=receipt(case);value['artifact_sha256']='0'*64
 code,result=check(case,0,value);assert code==0 and not result['passed'] and not result['receipt_verified']
def test_prior_failure_archive_cannot_be_overwritten(case):
 value=receipt(case);check(case,0,value);prior=(case['private']/'archive/round-00/result.json').read_bytes()
 code,result=check(case,0,value);assert code==2 and result['fatal'];assert (case['private']/'archive/round-00/result.json').read_bytes()==prior
def test_round_outside_bound_cannot_execute(case):
 code,result=check(case,3,receipt(case));assert code==2 and result['fatal'];assert not (case['private']/'archive').exists()

def test_old_report_cannot_complete_new_file_effects(case):
 value=receipt(case);move_correct(case);code,result=check(case,0,value)
 assert code==0 and not result['passed'];assert any('snapshot differs' in error for error in result['errors'])
