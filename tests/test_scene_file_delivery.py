"""Cross-format inputs preserve actual data; review exports are real checked files."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
import pytest
from scenarios.data_analysis.table_inputs import extract_tables
from scenarios.data_analysis.report_intake import ReportIntake
from src.adapters.harless_attachment_text import extract_attachment

ROWS = [['sample','x','y'],['A','1','2.1'],['B','2',''],['C','3','6.3'],['D','4','7.7']]

def word(rows):
    from xml.sax.saxutils import escape
    data = io.BytesIO()
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>'
    xml += ''.join('<w:tr>'+''.join('<w:tc><w:p><w:r><w:t>'+escape(v)+'</w:t></w:r></w:p></w:tc>' for v in row)+'</w:tr>' for row in rows)
    with zipfile.ZipFile(data,'w') as z: z.writestr('word/document.xml',xml+'</w:tbl></w:body></w:document>')
    return data.getvalue()

@pytest.mark.parametrize('extension',['csv','docx','pdf','json','txt'])
def test_five_formats_preserve_rows_and_missing_cells(tmp_path, extension):
    import csv
    raw = 'sample,x,y\nA,1,2.1\nB,2,\nC,3,6.3\nD,4,7.7\n'.encode()
    if extension=='docx': raw=word(ROWS)
    elif extension=='json': raw=json.dumps([dict(zip(ROWS[0],r)) for r in ROWS[1:]]).encode()
    elif extension=='pdf':
        pytest.importorskip('fitz');pytest.importorskip('reportlab')
        from reportlab.platypus import SimpleDocTemplate,Table,TableStyle
        out=io.BytesIO();table=Table(ROWS)
        table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),1,'black')]))
        SimpleDocTemplate(out).build([table]);raw=out.getvalue()
    work=tmp_path/'work';(work/'inputs').mkdir(parents=True);(work/'report').mkdir()
    name='observations.'+extension;(work/'inputs'/name).write_bytes(raw)
    (work/'approved-inputs.json').write_text(json.dumps({'files':{name:hashlib.sha256(raw).hexdigest()}}))
    (work/'report/request.txt').write_text('Independent observations; fit y against x with an intercept.')
    intake=ReportIntake(work);assert intake.prepare()['report_ready']
    assert list(csv.reader(io.StringIO((intake.case/'data.csv').read_text())))==ROWS
    assert (work/'inputs'/name).read_bytes()==raw
    assert intake.prepare()['report_ready']

def test_table_summary_reports_actual_cells_without_assigning_identifier_meaning(tmp_path):
    from scenarios.data_analysis.table_inputs import summarize_tables
    path=tmp_path/'observations.csv'
    text='sample,x,y\nA,1,2.1\nB,2,\nC,3,6.3\nD,4,7.8\n'
    [summary]=summarize_tables(path,{'text':text})
    assert summary['data_rows']==4
    assert 'numeric' not in summary['columns']['sample']
    assert summary['columns']['y']['empty_data_rows']==[2]
    assert summary['columns']['y']['numeric']['sum']==pytest.approx(16.2)
    assert summary['columns']['y']['numeric']['median']==6.3
    assert summary['columns']['y']['numeric']['count']==3


def test_prose_and_nested_json_never_become_observations(tmp_path):
    for name,text in [('notes.txt','We recruited 40 people, including 2 missing outcomes.\nNo table, no observations.'),
                      ('metadata.json',json.dumps({'synthetic':True,'units':{'x':'days'}}))]:
        path=tmp_path/name;path.write_text(text)
        assert extract_tables(path,extract_attachment(path))==[]

def test_source_bound_review_exports_pdf_and_markdown_without_changing_input(tmp_path):
    pytest.importorskip('reportlab');pytest.importorskip('fitz')
    from src.adapters.session_report import SessionReport
    from src.adapters.session_files import SessionFiles
    root=tmp_path/'work'/'inputs';root.mkdir(parents=True)
    raw=b'40 minus 2 is 39. This proves causation.';(root/'paper.txt').write_bytes(raw)
    files=SessionFiles(root);versions={'paper.txt':hashlib.sha256(raw).hexdigest()}
    report=SessionReport(files,'paper-review')
    result=report.export('Source review', [{'heading':'Numerical consistency','paragraphs':['The source states 40 minus 2 is 39; the correct count is 38. This arithmetic does not establish causation.']}],versions)
    assert result['exported'] and result['page_count']>=1
    for row in result['artifacts']:
        path=root.parent/row['name'];assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    import fitz
    pdf=next(root.parent/r['name'] for r in result['artifacts'] if r['name'].endswith('.pdf'))
    with fitz.open(pdf) as document: assert 'correct count is 38' in ''.join(p.get_text() for p in document)
    assert (root/'paper.txt').read_bytes()==raw
    before=set((root.parent/'outputs/documents').iterdir())
    for proposed in ({'paper.txt':'0'*64},{'display-paper.txt':versions['paper.txt']}):
        rejected=report.export('Invalid', [{'heading':'Check','paragraphs':['Content']}],proposed)
        assert rejected['exported'] is False and rejected['reason']=='source_versions_mismatch'
        assert rejected['required_source_versions']==versions
    assert set((root.parent/'outputs/documents').iterdir())==before

def test_source_context_cannot_override_or_invent_evidence():
    pytest.importorskip('scipy');pytest.importorskip('statsmodels')
    from benchmarks.research_report_agent_v3.workflow_tools import _source_context
    study={'user_request':'x is measured in days; y in MPa. These are synthetic data.', 'units':{}}
    context={'units':{'x':{'value':'days','quote':'x is measured in days'}},
             'synthetic':{'value':True,'quote':'These are synthetic data.'}}
    bound=_source_context(context,study,['x','y'])
    assert bound=={'units':{'x':'days'},'synthetic':True} and study['units']=={}
    with pytest.raises(ValueError,match='conflict'):
        _source_context(context,{**study,'units':{'x':'seconds'}},['x','y'])
    with pytest.raises(ValueError,match='exact supplied'):
        _source_context({'synthetic':{'value':True,'quote':'not actually supplied'}},study,['x'])

@pytest.mark.parametrize('name,raw', [('notes.txt',b'Actual source words. '*1700),
                                    ('data.csv',b'x,y\n1,2\n3,4\n'),
                                    ('study.json',b'{"description":"Supplied research context"}'),
                                    ('source.docx',word(ROWS))],ids=['txt-long','csv','json','docx'])
def test_ppt_reads_non_pdf_sources_completely_and_binds_actual_bytes(tmp_path,name,raw):
    pytest.importorskip('defusedxml')
    from scenarios.research_ppt.documents import parse_document
    path=tmp_path/name;path.write_bytes(raw)
    parsed=parse_document(path)
    assert parsed['page_count']>=1 and parsed['text_chars']>0
    assert all(not p['truncated'] and len(p['text'])<=12000 for p in parsed['pages'])
    expected=extract_attachment(path)['text']
    assert ''.join(p['text'] for p in parsed['pages'])==expected
    assert path.read_bytes()==raw


def test_review_write_failure_never_publishes_partial_files(tmp_path,monkeypatch):
    pytest.importorskip('reportlab');pytest.importorskip('fitz')
    from src.adapters.session_report import SessionReport
    from src.adapters.session_files import SessionFiles
    root=tmp_path/'work'/'inputs';root.mkdir(parents=True)
    raw=b'Source manuscript.';(root/'paper.txt').write_bytes(raw)
    original=Path.write_text
    def fail_receipt(path,*args,**kwargs):
        if path.name=='delivery.json': raise OSError('simulated interrupted receipt write')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',fail_receipt)
    with pytest.raises(OSError,match='interrupted'):
        SessionReport(SessionFiles(root),'paper-review').export('Review',
            [{'heading':'Scope','paragraphs':['Only the uploaded manuscript was reviewed.']}],
            {'paper.txt':hashlib.sha256(raw).hexdigest()})
    assert list((root.parent/'outputs/documents').iterdir())==[]
