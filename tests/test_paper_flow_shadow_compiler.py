from src.adapters.paper_flow_shadow_compiler import recipe,P


def call(name,args,output=None,ok=True):return {'name':name,'arguments':args,'output':output,'ok':ok}


def test_parallel_edges_are_mined_from_current_handles_not_past_literals():
    cfg={'case':'a','input_version':'a'*64};out={'citation_id':'source-'+'b'*32,'version_sha256':'a'*64}
    prior={'calls':[call(P+'read_pinned_paper_citations',{'source_id':'source-old'},out)]}
    next={'calls':[call(P+'read_pinned_citation_records',{'citation_id':out['citation_id']},out),
                   call(P+'fetch_pinned_cited_preprint_metadata',{'citation_id':out['citation_id']},out)]}
    g=recipe(prior,next,cfg,'/private/work')
    assert len(g['nodes'])==2 and 'source-' not in str(g)
    next['calls'][0]['arguments']['citation_id']='hallucinated'
    assert recipe(prior,next,cfg,'/private/work') is None
    next['calls'][0]['arguments']['citation_id']=out['citation_id'];prior['calls'][0]['ok']=False
    assert recipe(prior,next,cfg,'/private/work') is None


def test_semantic_writes_unknown_work_and_task_inputs_are_not_compiled():
    cfg={'case':'a','input_version':'a'*64}
    assert recipe(None,{'calls':[call(P+'pin_paper_citations',{'case_id':'other'})]},cfg,'/w') is None
    assert recipe({'calls':[call('web_fetch',{'url':'https://example.org'}, {})]},
                  {'calls':[call('write',{'file_path':'triage.json','content':'semantic content'})]},cfg,'/w') is None
    assert recipe({'calls':[call('write',{'file_path':'other.json'},ok=True)]},
                  {'calls':[call('check_paper_triage',{}, {'source_version':'a'*64})]},cfg,'/w') is None


def test_repair_read_requires_failed_structure_check_and_same_current_artifact():
    cfg={'case':'a','input_version':'a'*64};v={'status':'needs_repair','source_version':'a'*64,'report_sha256':'b'*64}
    prior={'calls':[call('check_paper_triage',{},v)]};target={'calls':[call('read_current_triage',{},v)]}
    assert recipe(prior,target,cfg,'/w')['anchor_result']=='needs_repair'
    target['calls'][0]['output']={**v,'report_sha256':'c'*64}
    assert recipe(prior,target,cfg,'/w') is None
    target['calls'][0]['output']=v;prior['calls'][0]['output']={**v,'status':'passed'}
    assert recipe(prior,target,cfg,'/w') is None
