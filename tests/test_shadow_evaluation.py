import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('shadow_evaluation', ROOT/'scripts/evaluate-shadow-continuation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ShadowEvaluationTests(unittest.TestCase):
    def fixture(self, base, text=False, mixed=False, failure=False, missing=False, child=False):
        run=Path(base)/'exp/runs/shadow';run.mkdir(parents=True)
        def save(name,value):
            p=run/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))
        save('manifest.json',{})
        save('metrics.json',{'status':'completed','actual_requests':3,'verified_skips':0,'unverified_bypasses':0})
        save('parameter-config.json',{'mode':'shadow','work':'/work','session_id':'root','binding_path':'selection.json'})
        (run.parents[1]/'library.json').write_text(json.dumps({'motifs':[{'motif_id':'m','prototype':{'tool':'read'}}]}))
        items=[{'item_id':'a','file_path':'a.tex'},{'item_id':'b','file_path':'b.tex'}]
        binding={'motif_id':'m','items':items}
        calls=[{'type':'tool-call','id':key,'name':'read','arguments':{'file_path':'/work/'+key+'.tex'}} for key in ['a','b']]
        if mixed:calls.append({'type':'tool-call','name':'bash','arguments':{'command':'inspect'}})
        if text:calls.insert(0,{'type':'text','text':'This may be a semantic decision.'})
        events=[{'session_id':'root','event':{'type':'tool/call','data':{'name':'write','callId':'write','arguments':{'file_path':'selection.json','content':json.dumps(binding)}}}},
                {'session_id':'root','event':{'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':'write','isError':False}]}}}}]
        if child: events.append({'session_id':'child','event':{'type':'assistant/message','data':{'turn':1,'step':99,'message':{'content':[]},'usage':{}}}})
        events.append({'session_id':'root','event':{'type':'assistant/message','data':{'turn':1,'step':2,'message':{'content':calls},'usage':{'inputTokens':100,'cacheReadTokens':80,'outputTokens':10}}}})
        (run/'session-events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
        audits=[{'kind':'selection_accepted','binding_digest':module.digest(binding),'motif_id':'m','item_ids':['a','b']},
                {'kind':'shadow_candidate','tool_count':2},
                {'kind':'shadow_result','item_id':'a','verified':True}]
        if not missing:audits.append({'kind':'shadow_result','item_id':'b','verified':not failure})
        (run/'parameter-motif').mkdir();(run/'parameter-motif/audit.jsonl').write_text('\n'.join(json.dumps(e) for e in audits))
        return run

    def test_whole_tool_only_request_is_opportunity_not_real_savings(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=module.evaluate(self.fixture(tmp,child=True))
            self.assertEqual(r['strict_tool_only_opportunities'],1)
            self.assertEqual(r['actual_skipped_requests'],0)
            self.assertEqual(r['actual_skip_savings_usd'],0)
            self.assertIsNone(r['counterfactual_cost_savings_usd'])
    def test_matching_tools_with_text_need_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=module.evaluate(self.fixture(tmp,text=True))
            self.assertEqual(r['strict_tool_only_opportunities'],0)
            self.assertEqual(r['batches'][0]['request_classification'],'matching_tools_requires_semantic_review')
    def test_unicode_paragraph_separators_do_not_split_json_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(tmp, text=True)
            path = run / 'session-events.jsonl'
            path.write_text(path.read_text().replace('This may be a semantic decision.',
                            'Source\u2028with\u2029paragraphs') + '\n\n', encoding='utf-8')
            r = module.evaluate(run)
            self.assertEqual(r['complete_batches'], 1)
            self.assertEqual(r['strict_tool_only_opportunities'], 0)
    def test_matching_subgraph_does_not_authorize_skipping_mixed_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=module.evaluate(self.fixture(tmp,mixed=True))
            self.assertEqual(r['strict_tool_only_opportunities'],0)
            self.assertEqual(r['batches'][0]['request_classification'],'mixed_or_different_actions')
    def test_failed_or_missing_result_does_not_validate_opportunity(self):
        for kwargs in [{'failure':True},{'missing':True}]:
            with self.subTest(kwargs=kwargs),tempfile.TemporaryDirectory() as tmp:
                r=module.evaluate(self.fixture(tmp,**kwargs))
                self.assertEqual(r['complete_batches'],0)
                self.assertEqual(r['strict_tool_only_opportunities'],0)
    def test_execute_trace_cannot_be_presented_as_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=self.fixture(tmp);p=run/'parameter-config.json';c=json.loads(p.read_text());c['mode']='execute';p.write_text(json.dumps(c))
            with self.assertRaises(ValueError):module.evaluate(run)

    def test_unbound_web_and_script_outputs_are_not_certified_skips(self):
        events = [{'type':'assistant/message','data':{'turn':1,'step':i,'message':{'content':[
            {'type':'tool-call','name':name,'arguments':args}]},'usage':{}}}
            for i,name,args in [(1,'web_fetch',{'url':'https://doi.org/10.123/example'}),
                                (2,'bash',{'command':'python generated.py'})]]
        r = module.request_inventory(events, [], {'work':'/work','binding_path':'selection.json'})
        self.assertEqual(r['pure_tool_output_responses'],2)
        self.assertEqual(r['scope_counts']['unbound_collection_needs_intent_and_contract'],1)
        self.assertEqual(r['scope_counts']['script_or_command_needs_compilation_and_contract'],1)
        self.assertTrue(all(not row['execution_authorized_by_inventory'] for row in r['responses']))
        self.assertEqual(r['responses'][0]['web_domains'],['doi.org'])

    def test_binding_protocol_overhead_and_cached_input_are_explicit(self):
        e = {'type':'assistant/message','data':{'turn':1,'step':1,'message':{'content':[
            {'type':'tool-call','name':'write','arguments':{'file_path':'selection.json','content':'{}'}}]},
            'usage':{'inputTokens':20,'cacheReadTokens':80,'cacheWriteTokens':5,'outputTokens':10}}}
        r = module.request_inventory([e], [], {'work':'/work','binding_path':'selection.json'})
        self.assertEqual(r['selection_protocol_responses'],1)
        self.assertEqual(r['responses'][0]['observed_prompt_tokens'],105)
        self.assertEqual(r['responses'][0]['observed_output_tokens'],10)

    def test_crossref_match_uses_the_pinned_library_template_and_query(self):
        proto={'contract':'crossref-search-fetch-v1','arguments':{'url':{'base':'https://api.crossref.org/works',
          'query':[{'name':'query.title','slot':'query'},{'name':'rows','value':'3'},{'name':'select','value':'DOI,title'}]}}}
        call={'name':'web_fetch','arguments':{'url':'https://api.crossref.org/works?query.title=A+Study&rows=3&select=DOI%2Ctitle'}}
        self.assertTrue(module.matched_call(call,{'query':'A Study'},'web_fetch','/work',proto))
        self.assertFalse(module.matched_call(call,{'query':'A Different Study'},'web_fetch','/work',proto))
