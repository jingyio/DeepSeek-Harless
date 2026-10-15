import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from script_reuse_learning import load_witness,learn

class ScriptEvidenceBoundary(unittest.TestCase):
    def case(self,root,role='explore',arm='H',passed=True):
        a=root/'attempts'/'one';a.mkdir(parents=True)
        (a/'outcome.json').write_text(json.dumps({'role':role,'arm':arm,'normal_harness_only':arm=='H','learning_performed':False,
            'acceptance':{'passed':passed},'receipt_verified':passed,'run':{'status':'done'}}))
        return {'task_dir':str(root),'role':role}
    def test_holdout_and_automatic_evidence_cannot_train(self):
        for role,arm in [('holdout','H'),('certify','H'),('explore','L'),('probe','H')]:
            with tempfile.TemporaryDirectory() as d:
                c=self.case(Path(d),role,arm)
                with self.assertRaisesRegex(ValueError,'only new ordinary'):load_witness(c)
    def test_failed_exploration_retained_but_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.case(Path(d),passed=False)
            with self.assertRaisesRegex(ValueError,'failed exploration'):load_witness(c)
    def test_candidate_cannot_be_rewritten_after_certification_exposure(self):
        with tempfile.TemporaryDirectory() as d:
            exp=Path(d);c=self.case(exp/'certification','certify')
            with self.assertRaisesRegex(ValueError,'before certification'):learn(exp,{'tasks':[c]})

if __name__=='__main__':unittest.main()
