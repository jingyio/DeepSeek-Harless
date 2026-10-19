"""Real parser/OCR diagnostics, not model or RSI benefit evidence."""
import copy,json,sys
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_prepare import prepare
from management_tools import ManagementScene
from management_reading import verify_documents
from common import digest

@pytest.fixture
def document(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    w=tmp_path/'work';w.mkdir();pdf=w/'document.pdf'
    c=PdfWriter()
    for page in range(1,5):
        p=c.add_blank_page(width=612,height=842)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        lines=[f'PAGE {page} IMPORTANT TOKEN {page}']
        if page==2:
            lines += ['Long page content '+str(row)+' X'*70 for row in range(100)]
        stream=DecodedStreamObject();stream.set_data(('BT /F1 5 Tf 7 TL 30 800 Td\n'+'\n'.join('('+line+') Tj T*' for line in lines)+'\nET').encode())
        p[NameObject('/Contents')]=c._add_object(stream)
    with pdf.open('wb') as f:c.write(f)
    h=ROOT/'.local/document-reading-tests'/uuid4().hex
    spec=prepare(h,w,task_id=uuid4().hex,objective='complete document reading',owner='reading-test',workspace_id=uuid4().hex,
                 quality=[{'kind':'read','path':'document.pdf'}])
    s=ManagementScene(spec,h/'delivery');s.read_task()
    fid=s.list_files()['files'][0]['file_id'];source=s.pin_file(fid)['source_id']
    return s,spec,h,source

def finish(s,q):
    rows=[]
    while q:
        row=s.read_document_chunk(q);rows.append(row);q=row['next_request_id']
    return rows

def test_whole_pdf_requires_actual_all_page_chunks_and_resumes(document):
    s,spec,h,source=document
    preview=s.read_file(source)
    assert preview['truncated'] and preview['metadata']['preview_only']
    with pytest.raises(Exception,match='required complete read'):s.submit_report('preview only',list(s.files()),[])
    d=s.open_document(source);assert d['page_count']==4
    assert not s.document_coverage(d['document_id'])['complete']
    first=s.read_document_chunk(d['request_id'])
    resumed=ManagementScene(spec,h/'delivery');resumed.read_task()
    assert resumed.read_document_chunk(d['request_id'])==first
    with pytest.raises(Exception,match='required complete read'):resumed.submit_report('only first page',list(s.files()),[])
    rows=finish(resumed,first['next_request_id'])
    assert any(r['page']==4 and 'IMPORTANT TOKEN 4' in r['text'] for r in rows)
    assert len([r for r in rows if r['page']==2])>1
    coverage=resumed.document_coverage(d['document_id'])
    assert coverage['complete'] and coverage['completed_pages']==[1,2,3,4]
    assert coverage['delivered_characters']>6000 and coverage['unread_pages']==[]
    assert resumed.submit_report('all physical pages read',list(resumed.files()),[])['semantic_quality_verified']
    assert resumed.search_document(d['document_id'],'IMPORTANT TOKEN 4')['matches'][0]['page']==4
    visual=resumed.view_document_page(source,4)
    assert visual.content[1].type=='image' and visual.content[1].mime_type=='image/png'
    assert visual.structured_content['page']==4

def test_coverage_tampering_rejected_by_independent_page_replay(document):
    s,spec,h,source=document;d=s.open_document(source);finish(s,d['request_id'])
    state=json.loads(s.state_file.read_text());doc=state['documents'][d['document_id']]
    first=doc['chunks'][d['request_id']];first['text']='fabricated content'
    first['response_sha256']=digest({k:v for k,v in first.items() if k!='response_sha256'})
    assert verify_documents(spec,state,s.output)
    with pytest.raises(Exception,match='unknown request_id'):s.read_document_chunk('chunk-guessed')

def test_sealed_delivery_can_be_replayed_from_another_private_archive(document):
    import shutil
    s,spec,h,source=document;d=s.open_document(source);finish(s,d['request_id'])
    archived=h/'sealed-archive';shutil.copytree(s.output,archived)
    state=json.loads((archived/'management-state.json').read_text())
    assert not Path(state['documents'][d['document_id']]['source_file']).is_absolute()
    assert verify_documents(spec,state,archived)==[]

def test_real_image_ocr_is_separate_from_metadata(tmp_path,monkeypatch):
    from PIL import Image,ImageDraw,ImageFont
    w=tmp_path/'work';w.mkdir();im=Image.new('RGB',(1200,180),'white')
    font=ImageFont.load_default(size=54)
    ImageDraw.Draw(im).text((40,50),'GENELOOP OCR 47291',fill='black',font=font);im.save(w/'scan.png')
    h=ROOT/'.local/document-reading-tests'/uuid4().hex
    spec=prepare(h,w,task_id=uuid4().hex,objective='read scanned image',owner='reading-test',workspace_id=uuid4().hex,
                 quality=[{'kind':'read','path':'scan.png','mode':'ocr'}])
    s=ManagementScene(spec,h/'delivery');s.read_task();sid=s.pin_file(s.list_files()['files'][0]['file_id'])['source_id']
    assert s.read_file(sid)['status']=='metadata_only'
    with pytest.raises(Exception,match='images require'):s.open_document(sid)
    monkeypatch.setenv('FM_OCR_LANGUAGES','eng')
    d=s.open_document(sid,'ocr');row=s.read_document_chunk(d['request_id'])
    assert '47291' in row['text'] and row['extraction']=='ocr'
    assert s.document_coverage(d['document_id'])['complete']
    assert s.submit_report('OCR read, visual semantics not claimed',list(s.files()),[])['semantic_quality_verified']
