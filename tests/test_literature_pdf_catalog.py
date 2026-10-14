"""Real PDF catalog protocol checks; fixtures never certify learned metadata quality."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import pytest
from pydantic import ValidationError
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import make_pdf, POPPLER, module
ROOT=Path(__file__).resolve().parents[1]; HERE=ROOT/'scenarios/literature-notes'
sys.path.insert(0,str(HERE))
from pdf_tools import inventory,digest,save_private
from pdf_catalog_tools import CatalogScene,DEFAULT_CATALOG_QUESTION,CatalogEntry
from catalog_entry import entry_task


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory(dir=ROOT/'.local') as tmp:
        base=Path(tmp); papers=base/'papers';papers.mkdir()
        make_pdf(papers/'A.pdf',['Catalog Alpha by Alice Smith 2026 DOI 10.1234/alpha'])
        make_pdf(papers/'B.pdf',['Catalog Beta by Bob Jones 2025'])
        def scene(name='output',previous=None):
            return CatalogScene(papers,{'schema_version':1,'question':DEFAULT_CATALOG_QUESTION,'sources':inventory(papers)},base/name,previous=previous)
        yield base,papers,scene


def decisions(s):
    rows=[]
    for work in s.read_catalog_plan()['work']:
        packet=s.read_catalog_packet(work['paper_id']); text=packet['text'].strip()
        alpha='Alpha' in text
        def val(v):return {'value':v,'anchor':text if v else ''}
        rows.append({'paper_id':work['paper_id'],'title':val('Catalog Alpha' if alpha else 'Catalog Beta'),
                     'authors':[val('Alice Smith' if alpha else 'Bob Jones')],
                     'year':{'candidate_id':None},'author_coverage':{'status':'covered','region_ids':[], 'reason':''},
                     'doi':val('10.1234/alpha' if alpha else None),'arxiv':val(None)})
    return rows


@POPPLER
def test_catalog_delivers_all_records_and_existing_bib_parser_checked(setup):
    base,papers,new=setup; s=new(); entries=decisions(s)
    result=s.submit_catalog([CatalogEntry(**r) for r in entries])
    envelope=json.loads(Path(result['artifact']).read_text()); value=envelope['catalog']
    assert result['entry_count']==result['processed_count']==2 and result['gap_count']==0
    assert digest(value)==envelope['catalog_sha256']==result['catalog_sha256']
    assert digest(envelope)==result['artifact_sha256']
    # Exercise the actual shared completion verifier, not a mirror of its hashing rule.
    import subprocess
    check="import fs from 'node:fs';import {verifyReceipt} from './src/adapters/dsh_completion_guard.ts';const r=JSON.parse(fs.readFileSync(0,'utf8'));if(!verifyReceipt(r,process.argv[1]))process.exit(1);"
    subprocess.run(['node','--input-type=module','-e',check,str(ROOT/'.local')],input=json.dumps(result),text=True,cwd=ROOT,check=True)
    assert s.publish(entries,persist=False)==value
    assert Path(result['bibtex']).read_text()==value['bibliography']
    assert not value['metadata_verified_online'] and not value['scholarly_identity_certified']


@POPPLER
def test_unchanged_then_added_removed_and_changed_files_keep_only_current_valid_records(setup):
    base,papers,new=setup;s=new();s.publish(decisions(s));prior=base/'output/catalog.json'
    old=json.loads(prior.read_text())['catalog']['records']
    same=new('same',prior); assert not same.read_catalog_plan()['work']
    same.publish([]);assert json.loads((base/'same/catalog.json').read_text())['catalog']['records']==old
    (papers/'B.pdf').unlink();make_pdf(papers/'C.pdf',['Catalog Beta by Bob Jones 2025'])
    update=new('added',prior);plan=update.read_catalog_plan()
    assert len(plan['work'])==len(plan['retained_ids'])==len(plan['removed_ids'])==1
    out=update.publish(decisions(update));value=json.loads(Path(out['artifact']).read_text())['catalog']
    assert next(r for r in value['records'] if r['paper_id']==plan['retained_ids'][0])==old[0]
    make_pdf(papers/'A.pdf',['Catalog Alpha by Alice Smith 2026 DOI 10.1234/alpha revised'])
    assert len(new('changed',prior).read_catalog_plan()['work'])==2


@POPPLER
def test_exact_duplicate_files_are_retained_and_not_scholarly_identity_merged(setup):
    base,papers,new=setup;(papers/'Copy.pdf').write_bytes((papers/'A.pdf').read_bytes())
    s=new();plan=s.read_catalog_plan();assert len(plan['exact_duplicate_files'])==1
    result=s.publish(decisions(s));assert result['entry_count']==3
    assert not plan['duplicates_automatically_merged']


@POPPLER
@pytest.mark.parametrize('bad',['missing','duplicate','outside','anchor','invented_year','null_anchor','duplicate_author','unread'])
def test_invalid_metadata_never_publishes_receipt(setup,bad):
    base,papers,new=setup;s=new();rows=decisions(s)
    if bad=='missing':rows.pop()
    if bad=='duplicate':rows[1]=copy.deepcopy(rows[0])
    if bad=='outside':rows[0]['paper_id']='outside'
    if bad=='anchor':rows[0]['title']['anchor']='A hallucinated source anchor'
    if bad=='invented_year':rows[0]['year']['candidate_id']='date-invented'
    if bad=='null_anchor':rows[1]['doi']['anchor']='A nonempty source'
    if bad=='duplicate_author':rows[0]['authors']*=2
    if bad=='unread':s.packets={}
    with pytest.raises(ToolError):s.publish(rows)
    assert not (base/'output/catalog.json').exists()


@POPPLER
@pytest.mark.parametrize('change',['pdf','selection','previous','version'])
def test_input_or_contract_change_fails_closed(setup,change,monkeypatch):
    base,papers,new=setup;s=new();s.publish(decisions(s));prior=base/'output/catalog.json'
    active=new('active',prior);active.read_catalog_plan()
    if change=='pdf':make_pdf(papers/'A.pdf',['Changed document bytes'])
    if change=='selection':make_pdf(papers/'C.pdf',['New selected file'])
    if change=='previous':prior.write_text('{}')
    if change=='version':monkeypatch.setattr('pdf_catalog_tools.execution_version',lambda:'f'*64)
    with pytest.raises(ToolError):active.publish([])


@POPPLER
def test_low_text_missing_metadata_is_delivered_without_inventing_it(setup):
    base,papers,new=setup;make_pdf(papers/'A.pdf',[' ']);s=new();plan=s.read_catalog_plan();rows=[]
    for work in plan['work']:
        s.read_catalog_packet(work['paper_id']);rows.append({'paper_id':work['paper_id'],
            **{k:{'value':None,'anchor':''} for k in ('title','doi','arxiv')},'authors':[],
            'year':{'candidate_id':None},'author_coverage':{'status':'unavailable','region_ids':[], 'reason':''}})
    receipt=s.publish(rows);assert receipt['status']=='needs_review' and receipt['gap_count']==2


@POPPLER
def test_frozen_frontier_contains_only_changed_actual_work_and_binds_previous_catalog(setup):
    base,papers,new=setup;s=new();s.publish(decisions(s));prior=base/'output/catalog.json'
    with pytest.raises(ValueError,match='ordinary zero-model'):entry_task(new('same',prior),'t')
    make_pdf(papers/'C.pdf',['Catalog Beta by Bob Jones 2025']);updated=new('new',prior)
    frozen=entry_task(updated,'fixture');plan=updated.read_catalog_plan()
    assert frozen['target_ids']==[r['paper_id'] for r in plan['work']]
    assert len(frozen['inventory_papers'])==1 and frozen['source_result_sha256']==digest(plan)


def test_metadata_schema_rejects_extra_fields_and_renderer_keeps_literal_braces():
    from pdf_catalog_tools import escape_bib
    assert escape_bib('A {Nested} & B')==r'A \{Nested\} \& B'
    with pytest.raises(ValidationError):CatalogEntry.model_validate({'paper_id':'p','extra':True})


@POPPLER
def test_short_author_anchor_is_valid_and_spaced_title_error_identifies_field(setup):
    base,papers,new=setup;make_pdf(papers/'A.pdf',['U NIFIED P LAYERS by Yi Ding 2026']);s=new();rows=[]
    for work in s.read_catalog_plan()['work']:
        packet=s.read_catalog_packet(work['paper_id'])
        if 'Yi Ding' not in packet['text']: continue
        row={'paper_id':work['paper_id'],'title':{'value':'U NIFIED P LAYERS','anchor':'U NIFIED P LAYERS'},
             'authors':[{'value':'Yi Ding','anchor':'Yi Ding'}],
             'year':{'candidate_id':None},'author_coverage':{'status':'covered','region_ids':[], 'reason':''},
             **{k:{'value':None,'anchor':''} for k in ('doi','arxiv')}}
        assert s._checked(row,packet)['metadata']['authors'][0]['value']=='Yi Ding'
        row['title']['value']='UnifiedPlayers'
        with pytest.raises(ToolError,match='"field": "title"') as error:s._checked(row,packet)
        feedback=json.loads(str(error.value).split(': ',1)[1])
        assert feedback['paper_id']==work['paper_id'] and feedback['issues'][0]['anchor_in_source']
