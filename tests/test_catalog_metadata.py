"""Metadata kind/coverage boundaries, without private PDFs or semantic quality claims."""
from pathlib import Path
import sys
import pytest
from mcp.server.mcpserver.exceptions import ToolError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scenarios/literature-notes'))
from catalog_metadata import metadata_candidates,resolve_year,check_author_coverage


def packet(text,version='a'*64):return {'text':text,**metadata_candidates(text,version)}


@pytest.mark.parametrize('label',['Accepted','Received','Copyright','©'])
def test_administrative_dates_are_visible_but_cannot_be_bibliography_year(label):
    p=packet(label+': 14 August 2026')
    assert len(p['date_candidates'])==1 and not p['date_candidates'][0]['eligible_bibliography_year']
    with pytest.raises(ToolError,match='never received/accepted/copyright'):
        resolve_year({'candidate_id':p['date_candidates'][0]['candidate_id']},p)
    assert resolve_year({'candidate_id':None},p)['value'] is None


@pytest.mark.parametrize('text', ['Published online: 15 September 2026','发表日期：2026年9月15日',
                                'arXiv:2609.00001v2 [cs.AI] 9 Sep 2026'])
def test_only_explicit_eligible_dates_auto_project_without_model_year_copy(text):
    p=packet(text);v=resolve_year({'candidate_id':None},p)
    assert v['value']=='2026' and v['selection_origin']=='runtime_unambiguous_date'
    assert v['anchor']==text


def test_placeholder_and_identifier_do_not_infer_year_and_stale_candidates_fail():
    text='Received: 13 October 2025\nAccepted: 14 August 2026\nPublished online: xx xx xxxx\n10.1038/example-026-foo\narXiv:2609.00001v2'
    p=packet(text)
    assert all(not c['eligible_bibliography_year'] for c in p['date_candidates'])
    assert resolve_year({'candidate_id':None},p)['value'] is None
    old=packet('Published: 2026')['date_candidates'][0]['candidate_id']
    with pytest.raises(ToolError):resolve_year({'candidate_id':old},packet('Published: 2026','b'*64))


def test_conflicting_date_years_remain_gap_until_explicit_candidate_selected():
    p=packet('arXiv:2409.00001v1 [cs.AI] 9 Sep 2024\nPublished online: 12 March 2026')
    assert resolve_year({'candidate_id':None},p)['selection_origin']=='runtime_ambiguous_dates'
    c=next(c for c in p['date_candidates'] if c['kind']=='publication')
    assert resolve_year({'candidate_id':c['candidate_id']},p)['value']=='2026'


def test_same_year_dates_choose_publication_without_model_and_unlabelled_numbers_stay_unknown():
    p=packet('arXiv:2609.00001v1 [cs.AI] 9 Sep 2026\nPublished: 12 March 2026')
    assert resolve_year({'candidate_id':None},p)['kind']=='publication'
    assert not packet('A 2026 method evaluated in 2025')['date_candidates']


@pytest.mark.parametrize('layout',[
    'A Paper Title\nAlice Smith∗ Bob Jones† Yi Ding James Liu\nAbstract: a study',
    'Article\nA Paper Title\nAlice Smith1,2 ✉, Bob Jones1 & Yi Ding3\nReceived: 2025',
    'A Paper Title\nAlice Smith\nExample University\nalice@example.org\n\nBob Jones\nExample University\nbob@example.org\nAbstract: a study'])
def test_marked_or_profile_regions_block_silent_empty_author_list(layout):
    p=packet(layout);assert p['author_regions']
    c={'status':'covered','region_ids':[r['region_id'] for r in p['author_regions']],'reason':''}
    with pytest.raises(ToolError,match='uncovered_name_tokens'):check_author_coverage(c,[],p)
    with pytest.raises(ToolError,match='cannot be declared unavailable'):
        check_author_coverage({'status':'unavailable','region_ids':[],'reason':''},[],p)


def test_covered_names_partial_real_gap_and_candidate_identity_are_distinct():
    p=packet('A Paper Title\nAlice Smith∗ Bob Jones† Yi Ding James Liu\nAbstract: study')
    ids=[r['region_id'] for r in p['author_regions']]
    authors=[{'value':n} for n in ['Alice Smith','Bob Jones','Yi Ding','James Liu']]
    result=check_author_coverage({'status':'covered','region_ids':ids,'reason':''},authors,p)
    assert not result['uncovered_name_tokens'] and not result['complete_author_list_certified']
    with pytest.raises(ToolError):check_author_coverage({'status':'covered','region_ids':ids,'reason':''},authors[:-1],p)
    partial=check_author_coverage({'status':'partial','region_ids':ids,'reason':'candidate may be truncated'},authors[:-1],p)
    assert partial['uncovered_name_tokens']==['James','Liu'] and not partial['candidate_regions_covered']
    for bad in [ids+ids,['authors-forged']]:
        with pytest.raises(ToolError):check_author_coverage({'status':'covered','region_ids':bad,'reason':''},authors,p)


def test_ambiguous_unmarked_nonlatin_layout_is_not_inferred_as_complete_author_table():
    p=packet('科研研究\n张三，李四\nAbstract: study')
    assert not p['author_regions'] and not p['complete_author_list_certified']
