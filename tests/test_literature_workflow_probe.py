"""Source/coverage/conditional guards; fixtures do not certify a learned Motif."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import make_pdf, POPPLER
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/literature-notes'))
from pdf_tools import inventory,digest
from workflow_probe_tools import WorkflowProbeScene,check_url


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory(dir=ROOT/'.local') as tmp:
        base=Path(tmp);papers=base/'papers';papers.mkdir()
        make_pdf(papers/'one.pdf',['Our code is at https://github.com/example/project . Methods require validation.'])
        def scene(kind='topic_search',targets=None,network=False):
            spec={'schema_version':1,'kind':kind,'task':{'schema_version':1,'question':'Find methods','sources':inventory(papers)},
                  'network_check_enabled':network,'citations':targets or []}
            return WorkflowProbeScene(spec,base/'delivery')
        yield base,papers,scene


def topic(s):
    pid=s.read_workflow_input()['papers'][0]['paper_id']
    match=s.search_pdf_text(pid,'Methods')['matches'][0]
    pin=s.pin_pdf_context(pid,str(match['page']),match['start'],1000)
    s.read_pinned_pdf_context(pin['source_id'])
    return [{'target_id':pid,'status':'located','explanation':'Literal methods evidence','references':[pin['source_id']]}]


@POPPLER
def test_topic_requires_every_target_search_and_current_read_source(setup):
    base,papers,new=setup;s=new();rows=topic(s)
    receipt=s.submit_workflow_report(rows)
    assert digest(json.loads(Path(receipt['artifact']).read_text()))==receipt['artifact_sha256']
    assert s.publish(rows,persist=False)==receipt
    for bad in ([],[rows[0],rows[0]], [{**rows[0],'references':['made-up']}], [{**rows[0],'references':[]}]):
        with pytest.raises(ToolError):s.publish(bad,persist=False)
    unread=new();unread.read_workflow_input()
    with pytest.raises(ToolError):unread.publish(rows,persist=False)


@POPPLER
def test_unknown_search_is_delivered_as_gap_without_absence_claim(setup):
    base,papers,new=setup;s=new();pid=s.read_workflow_input()['papers'][0]['paper_id']
    result=s.search_pdf_text(pid,'not-present-literal')
    assert not result['matches'] and not result['absence_claim_supported']
    receipt=s.publish([{'target_id':pid,'status':'search_inconclusive','explanation':'This query has no hit','references':[]}])
    assert receipt['gap_count']==1 and receipt['status']=='needs_review'


@POPPLER
@pytest.mark.parametrize('change',['PDF','selection','version'])
def test_source_selection_and_implementation_change_fail_closed(setup,change,monkeypatch):
    base,papers,new=setup;s=new();rows=topic(s)
    if change=='PDF':make_pdf(papers/'one.pdf',['Replacement source'])
    if change=='selection':make_pdf(papers/'two.pdf',['Additional paper'])
    if change=='version':monkeypatch.setattr('workflow_probe_tools.execution_version',lambda:'changed')
    with pytest.raises(ToolError):s.publish(rows)


@POPPLER
def test_citation_replays_real_locator_then_detects_quote_drift(setup):
    base,papers,new=setup;s=new();pid=s.read_workflow_input()['papers'][0]['paper_id']
    # Regression: original stored quote locators are page-absolute even for a nonzero window start.
    pin=s.pin_pdf_context(pid,'1',10,1000);ctx=s.read_pinned_pdf_context(pin['source_id'])
    target={'reference_id':'reference-one','paper_id':ctx['paper_id'],'page':ctx['page'],'start':ctx['start'],'end':ctx['end'],
            'quote_start':10,'quote_end':30,'quote_sha256':digest(ctx['text'][:20]),
            'expected_window_version_sha256':ctx['version_sha256'],'expected_pdf_sha256':ctx['pdf_sha256']}
    for broken in (False,True):
        value=copy.deepcopy(target)
        if broken:value['quote_sha256']='bad'
        a=new('citation_audit',[value]);a.read_workflow_input();result=a.check_citation_target('reference-one')
        assert result['status']==('stale' if broken else 'current') and not result['entailment_checked']
        row={'target_id':'reference-one','status':result['status'],'explanation':'Source locator only','references':[]}
        assert a.publish([row])['gap_count']==int(broken)
        with pytest.raises(ToolError):a.publish([{**row,'status':'unresolved'}])


@POPPLER
def test_resource_report_requires_tool_ids_and_preserves_unchecked_state(setup):
    base,papers,new=setup;s=new('resource_inventory');pid=s.read_workflow_input()['papers'][0]['paper_id']
    result=s.find_resource_links(pid);resource=result['links'][0]
    row={'target_id':pid,'status':'resources','explanation':'Code candidate; offline check','references':[resource['resource_id']]}
    with pytest.raises(ToolError):s.publish([row])
    check=s.check_resource_url(resource['resource_id']);assert check['status']=='unchecked'
    s.publish([row]);body=json.loads((base/'delivery/report.json').read_text())
    assert body['url_checks']==[check] and not body['scientific_support_verified']
    with pytest.raises(ToolError):s.check_resource_url('invented')


@pytest.mark.parametrize('url',['http://github.com/example','https://127.0.0.1/private',
    'https://github.com.evil.example/path','https://user:pw@github.com/x','https://github.com:9999/x',
    'https://github.com/x?token=private','https://github.com:bad/x'])
def test_network_policy_blocks_arbitrary_private_or_authenticated_targets(url):
    assert check_url(url)['status']=='blocked'
