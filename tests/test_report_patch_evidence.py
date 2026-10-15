from src.adapters.report_patch_evidence import observed_revision_plan,patch_input,patch_expectation,patch_cases

def test_normal_diff_extracts_plan_without_rewriting_research_fields():
    a={'key':'a','arxiv_id':'old','source_urls':['one','two']}
    before={'references':[a,a.copy(),{'key':'b','arxiv_id':'b'}]}
    after={'references':[{**a,'arxiv_id':'new'},{'key':'b','arxiv_id':'b'},{'key':'c','arxiv_id':'c','status':'待进一步核验'}]}
    plan=observed_revision_plan(before,after)
    assert plan=={'set_ids':[{'key':'a','arxiv_id':'new'}],'keep_once_keys':['a'],'remove_keys':[],
                  'add_records':[{'key':'c','arxiv_id':'c','status':'待进一步核验'}]}
    assert patch_expectation(before,plan)['removals']==['/references/1']
    assert patch_input(before,plan)['rows_reverse'][0]['path']=='/references/2'

def test_field_damage_is_not_accepted_as_a_training_transform():
    import pytest
    before={'references':[{'key':'a','arxiv_id':'old','source_urls':['one']}]}
    after={'references':[{'key':'a','arxiv_id':'new','source_urls':['invented']}]}
    with pytest.raises(ValueError,match='protected'):observed_revision_plan(before,after)

def test_fixed_independent_cases_cover_multi_digit_indices_and_empty_inputs():
    p={'packet_id':'s','before_report':{'references':[{'key':'a','arxiv_id':'old'}]},
       'after_report':{'references':[{'key':'a','arxiv_id':'new'}]}}
    dev,held=patch_cases([p])
    assert len(dev)==3 and len(held)==18
    case=next(c for c in held if c['id']=='heldout-23-mixed')
    assert '/references/22' in case['expected']['removals']
    assert case['expected']['removals'][0]=='/references/22'
