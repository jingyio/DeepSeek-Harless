import json
from pathlib import Path
import sys
import tempfile
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import make_pdf,POPPLER
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/literature-notes'))
from pdf_tools import inventory,digest
from pdf_window_tools import WindowScene,decimal


@pytest.mark.parametrize('value',[1,True,'01','-1','1.5',' 1','1e3','10000000',''])
def test_noncanonical_locators_rejected(value):
    with pytest.raises(ToolError):decimal(value,minimum=0,maximum=12000)


@POPPLER
def test_custom_window_reads_identical_original_text_and_rejects_changed_source():
    with tempfile.TemporaryDirectory(dir=ROOT/'.local') as tmp:
        base=Path(tmp);papers=base/'papers';papers.mkdir();make_pdf(papers/'a.pdf',['Methods use deterministic verification and preserve evidence.'])
        spec={'schema_version':1,'kind':'topic_search','task':{'schema_version':1,'question':'methods','sources':inventory(papers)},'citations':[]}
        s=WindowScene(spec,base/'delivery');pid=s.read_workflow_input()['papers'][0]['paper_id']
        s.search_pdf_text(pid,'Methods')
        pin=s.pin_pdf_context(pid,'1','10','1000');context=s.read_pinned_pdf_context(pin['source_id'])
        assert context['text']==s._document(pid)['pages'][0][10:1010] and context['start']==10
        receipt=s.publish([{'target_id':pid,'status':'located','explanation':'source fixture','references':[pin['source_id']]}])
        assert digest(json.loads(Path(receipt['artifact']).read_text()))==receipt['artifact_sha256']
        for args in [('1','0','12001'),('0','0','100'),('1','1000001','100')]:
            with pytest.raises(ToolError):s.pin_pdf_context(pid,*args)
        make_pdf(papers/'a.pdf',['Changed PDF'])
        with pytest.raises(ToolError):s.read_pinned_pdf_context(pin['source_id'])
