import json,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from script_adaptation_learning import load_witness,learn
from script_adaptation_study import imported_evidence,summary
from common import sha,save
class Version2Evidence(unittest.TestCase):
    def test_only_new_ordinary_exploration_can_train(self):
        for role,arm in [('validate','L1'),('certify','L2'),('holdout','H'),('explore','L1')]:
            with tempfile.TemporaryDirectory() as d:
                a=Path(d)/'attempts'/'one';a.mkdir(parents=True);(a/'outcome.json').write_text(json.dumps({'role':role,'arm':arm,'normal_harness_only':arm=='H','learning_performed':False}))
                with self.assertRaisesRegex(ValueError,'only new ordinary'):load_witness({'role':role,'task_dir':d})
    def test_certification_exposure_blocks_candidate_learning(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'cert'/'attempts'/'one';a.mkdir(parents=True);(a/'outcome.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'before certification'):learn(Path(d),{'tasks':[{'role':'certify','task_dir':str(a.parents[1])}]})
    def fixture(self,d):
        old=Path(d)/'old';old.mkdir();a=old/'tasks/explore/attempts/one';a.mkdir(parents=True)
        save(a/'outcome.json',{'role':'explore','arm':'H','normal_harness_only':True,'learning_performed':False,'acceptance':{'passed':False},'run':{'upstream_requests':3,'budget_accounted_usd':0.02}})
        save(old/'protocol.json',{'source_code':{},'tasks':[{'role':'explore','task_id':'explore-H','task_dir':str(a.parents[1])}]})
        save(old/'protocol-lock.json',{'sha256':sha(old/'protocol.json')});return old,a
    def test_failed_import_remains_charged_once_without_rewriting_evidence(self):
        with tempfile.TemporaryDirectory() as d,patch('script_adaptation_study.dependencies',return_value={}),patch('script_adaptation_study.accounting',return_value={}):
            old,a=self.fixture(d);before=sha(a/'outcome.json');tasks,records,protected=imported_evidence(old)
            self.assertEqual(tasks[0]['origin_experiment'],str(old));self.assertEqual(records[0]['outcome_sha256'],before)
            exp=Path(d)/'new';exp.mkdir();result=summary(exp,{'imported_maintenance':records,'v1_upfront_usd':0.1,'overhead_sources':[]})
            self.assertEqual(result['attempts'],1);self.assertEqual(result['maintenance_usd'],0.02);self.assertEqual(result['maintenance_requests'],3)
            self.assertFalse(result['outcomes'][0]['acceptance']['passed']);self.assertEqual(sha(a/'outcome.json'),before);self.assertEqual(protected[str(a/'outcome.json')],before)
    def test_exposed_holdout_blocks_maintenance_import(self):
        with tempfile.TemporaryDirectory() as d:
            old,_=self.fixture(d);save(old/'holdout.json',{})
            with self.assertRaisesRegex(ValueError,'pre-certification'):imported_evidence(old)
    def test_changed_mcp_dependency_blocks_maintenance_import(self):
        with tempfile.TemporaryDirectory() as d,patch('script_adaptation_study.dependencies',return_value={'mcp.py':'expected'}):
            old,_=self.fixture(d);p=json.loads((old/'protocol.json').read_text());p['source_code']={'mcp.py':'wrong'};save(old/'protocol.json',p);save(old/'protocol-lock.json',{'sha256':sha(old/'protocol.json')})
            with self.assertRaisesRegex(ValueError,'incompatible MCP'):imported_evidence(old)
if __name__=='__main__':unittest.main()
