"""Free proposal/split diagnostics; synthetic data, no model authorship claim."""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from src.adapters.revision_tool_evidence import revision_facts
from src.adapters.trace_tool_evidence import digest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('revision_controller_diagnostic',ROOT/'scripts/paper-rsi-revision.py')
controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)

class RevisionControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.exp=Path(self.tmp.name)
        work=self.exp/'work';work.mkdir()
        before={'scope':'diagnostic','references':[{'key':'a','arxiv_id':'wrong','source_urls':['u1','u2']}]*2}
        after={'scope':'diagnostic','references':[{'key':'a','arxiv_id':'1','source_urls':['u1','u2']},
            {'key':'b','arxiv_id':'2','status':'待进一步核验'}]}
        catalog={'cited_records':[{'key':'a','arxiv_ids':['1']},{'key':'b','arxiv_ids':['2']}],
            'query_items':[{'item_id':'a:1','id':'1'},{'item_id':'b:2','id':'2'}]}
        packet={'packet_id':'synthetic','run_id':'diagnostic-run','session_id':'diagnostic-session',
            'call_id':'diagnostic-call','events_sha256':'a'*64,'learning_eligible':True,
            'before_report':before,'after_report':after,'catalog':catalog,'oracle_facts':revision_facts(before,after,catalog)}
        other=copy.deepcopy(packet);other['packet_id']='synthetic-other';other['session_id']='diagnostic-other-session'
        other['before_report']['scope']=other['after_report']['scope']='another-scope'
        controller.save(self.exp/'training-packets.json',{'packets':[packet,other]})
        controller.save(self.exp/'active-learning.json',{'work':str(work)})
        self.proposal={'source':{'packet_id':'synthetic'},'contract':{'name':'diagnostic_revision','description':'合成提案诊断'},
            'input_bindings':{'before':{'file':'catalog.json','pointer':'/initial_report'},
                'after':{'file':'triage.json','pointer':''},'catalog':{'file':'catalog.json','pointer':'/cited_records'},'query':{'file':'catalog.json','pointer':'/query_items'}},
            'output_bindings':{k:'/metrics/'+k for k in ('before_count','after_count','existing_fields_preserved','top_level_preserved')}}

    def test_independent_split_is_fixed_before_install_and_has_no_overlap(self):
        result=controller.prepare_proposal(self.exp,self.proposal)
        hidden=controller.load(self.exp/'heldout.json');training=result['training']
        self.assertGreaterEqual(len(hidden),8)
        self.assertFalse({digest(c['input']) for c in hidden}&{digest(c['input']) for c in training})
        self.assertTrue(any(not c['expected']['existing_fields_preserved'] for c in hidden+training))
        with self.assertRaisesRegex(ValueError,'already_frozen'):controller.prepare_proposal(self.exp,self.proposal)

    def test_missing_top_level_inputs_report_which_dependency_was_lost(self):
        p=copy.deepcopy(self.proposal)
        p['input_bindings']['before']['pointer']='/initial_report/references'
        p['input_bindings']['after']['pointer']='/references'
        with self.assertRaisesRegex(ValueError,'top_level_preserved'):controller.prepare_proposal(self.exp,p)
        self.assertFalse((self.exp/'accepted-proposal.json').exists())

    def test_excess_output_fields_return_count_and_preserve_target(self):
        p=copy.deepcopy(self.proposal);p['output_bindings']={f'field_{n}':'/metrics/before_count' for n in range(14)}
        with self.assertRaisesRegex(ValueError,'received:14'):controller.prepare_proposal(self.exp,p)
        self.assertFalse((self.exp/'accepted-proposal.json').exists())

if __name__=='__main__':unittest.main()
