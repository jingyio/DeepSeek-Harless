import copy
import unittest
from src.adapters.revision_tool_evidence import (revision_facts, strict_revision_pointer,
    project_generated_outputs, compose_generated_candidates, rebind_generated_input)


class RevisionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.catalog={'cited_records':[{'key':'a','arxiv_ids':['1']},{'key':'b','arxiv_ids':['2']}]}
        row={'key':'a','arxiv_id':'wrong','source_urls':['one','two'],'unknown':{'nested':None}}
        self.before={'scope':'test','references':[copy.deepcopy(row),copy.deepcopy(row)]}
        self.after={'scope':'test','references':[copy.deepcopy(self.before['references'][0]),{'key':'b','arxiv_id':'2','status':'待进一步核验'}]}
        self.after['references'][0]['arxiv_id']='1'

    def test_counts_distinguish_objects_unique_keys_and_duplicates(self):
        facts=revision_facts(self.before,self.after,self.catalog)['metrics']
        self.assertEqual((facts['before_count'],facts['before_unique_key_count'],facts['before_duplicate_key_count']),(2,1,1))
        self.assertTrue(all(facts[k] for k in ('coverage_valid','existing_fields_preserved','top_level_preserved','placeholders_valid')))

    def test_urls_order_unknown_fields_and_missing_null_are_not_normalized(self):
        for change in ('url','order','unknown','missing'):
            after=copy.deepcopy(self.after);row=after['references'][0]
            if change=='url':row['source_urls'][0]='another'
            elif change=='order':row['source_urls'].reverse()
            elif change=='unknown':row['unknown']['nested']='changed'
            else:del row['unknown']
            facts=revision_facts(self.before,after,self.catalog)
            self.assertFalse(facts['metrics']['existing_fields_preserved'])
            self.assertTrue(facts['metrics']['coverage_valid'])
            self.assertEqual(facts['changed_keys'],['a'])

    def test_duplicate_conflicting_versions_are_visible_without_choosing_first(self):
        before=copy.deepcopy(self.before);before['references'][1]['source_urls']=['different']
        facts=revision_facts(before,self.after,self.catalog)
        self.assertEqual(facts['duplicate_conflict_keys'],['a'])
        self.assertTrue(facts['metrics']['existing_fields_preserved'])

    def test_extra_placeholder_facts_and_top_level_change_fail_separately(self):
        after=copy.deepcopy(self.after);after['references'][1]['source_urls']=['invented'];after['other']=None
        facts=revision_facts(self.before,after,self.catalog)['metrics']
        self.assertTrue(facts['coverage_valid'])
        self.assertFalse(facts['placeholders_valid'])
        self.assertFalse(facts['top_level_preserved'])

    def test_pointer_rejects_negative_indices_and_bad_escapes(self):
        self.assertEqual(strict_revision_pointer({'a/b':[None]},'/a~1b/0'),None)
        for path in ('/-1','/00','/2','/~2','/constructor'):
            with self.assertRaises(ValueError):strict_revision_pointer([1],path)

    def test_projection_retains_verbatim_branches_and_rejects_hidden_dependencies(self):
        schema=lambda fields:{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
        c={'schema_version':1,'name':'synthetic','description':'diagnostic',
            'input_schema':schema({'values':{'type':'array','items':{'type':'string'}},'other':{'type':'integer'}}),
            'output_schema':schema({'n':{'type':'integer'},'bad':{'type':'integer'}}),
            'program':['object',{'n':['count',['get',['var','input'],['lit','values']]],
                                'bad':['get',['var','input'],['lit','other']]}]}
        p=project_generated_outputs(c,['n'],['values'],name='part',description='subset')
        self.assertEqual(p['program'][1]['n'],c['program'][1]['n'])
        self.assertEqual(set(p['input_schema']['properties']),{'values'})
        with self.assertRaises(ValueError):project_generated_outputs(c,['bad'],['values'],name='bad',description='bad')
        whole=copy.deepcopy(c);whole['program'][1]['n']=['var','input']
        with self.assertRaises(ValueError):project_generated_outputs(whole,['n'],['values'],name='bad',description='bad')

    def test_composition_keeps_programs_and_avoids_variable_capture(self):
        schema=lambda key:{'type':'object','properties':{key:{'type':'integer'}},'required':[key],'additionalProperties':False}
        c={'schema_version':1,'name':'synthetic','description':'diagnostic',
            'input_schema':schema('a'),'output_schema':schema('x'),
            'program':['let','rsi_compiled_part_0',['lit',7],['object',{'x':['var','rsi_compiled_part_0']}]]}
        d={**c,'input_schema':schema('b'),'output_schema':schema('y'),'program':['object',{'y':['lit',8]}]}
        merged=compose_generated_candidates([c,d],name='combined',description='diagnostic')
        self.assertNotEqual(merged['program'][1],'rsi_compiled_part_0')
        self.assertEqual(merged['program'][2],c['program'])
        self.assertEqual(merged['program'][3][2],d['program'])
        with self.assertRaises(ValueError):compose_generated_candidates([c,c],name='bad',description='bad')

    def test_projection_keeps_lexical_bindings_and_composition_shares_only_identical_inputs(self):
        schema=lambda key:{'type':'object','properties':{key:{'type':'integer'}},'required':[key],'additionalProperties':False}
        c={'schema_version':1,'name':'synthetic','description':'diagnostic',
            'input_schema':schema('a'),'output_schema':schema('x'),
            'program':['let','value',['get',['var','input'],['lit','a']],['object',{'x':['var','value']}]]}
        p=project_generated_outputs(c,['x'],['a'],name='part',description='part')
        self.assertEqual(p['program'],c['program'])
        d={**c,'output_schema':schema('y'),'program':['object',{'y':['lit',8]}]}
        merged=compose_generated_candidates([p,d],name='combined',description='diagnostic')
        self.assertEqual(merged['input_schema']['required'],['a'])
        d=copy.deepcopy(d);d['input_schema']['properties']['a']={'type':'string'}
        with self.assertRaises(ValueError):compose_generated_candidates([p,d],name='bad',description='bad')

    def test_input_rebinding_preserves_literals_locals_and_rejects_shadowing(self):
        read=['get',['var','input'],['lit','before_report']]
        expression=['array',read,['lit',read],['get',['var','local'],['lit','before_report']]]
        bound=rebind_generated_input(expression,{'before_report':'after_report'})
        self.assertEqual(bound[1],['get',['var','input'],['lit','after_report']])
        self.assertEqual(bound[2:],expression[2:])
        self.assertEqual(expression[1],read)
        with self.assertRaises(ValueError):rebind_generated_input(['let','input',['lit',{}],read],{'before_report':'after_report'})

if __name__=='__main__':unittest.main()
