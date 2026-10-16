import csv
import hashlib
import io
import json
import pytest
from scenarios.data_analysis.report_intake import ReportIntake
from src.adapters.harless_attachment_text import extract_attachment

def image_file(path, kind='PNG'):
    Image=pytest.importorskip('PIL.Image')
    image=Image.new('RGB',(320,240),'white')
    for x in range(30,180):
        for y in range(40,90): image.putpixel((x,y),(20,70,120))
    image.save(path,format=kind)
    return hashlib.sha256(path.read_bytes()).hexdigest()

@pytest.mark.parametrize('extension,kind',[('png','PNG'),('jpg','JPEG')])
def test_native_image_provenance_without_fabricating_ocr(tmp_path,extension,kind):
    from scenarios.research_ppt.documents import parse_document
    path=tmp_path/('figure.'+extension);version=image_file(path,kind)
    text=extract_attachment(path)
    assert text['status']=='visual_input' and text['sha256']==version
    assert text['text']=='' and text['ocr_performed'] is False
    parsed=parse_document(path)
    assert parsed['page_count']==1 and parsed['text_chars']==0
    assert parsed['images'][0]['evidence_scope']=='uploaded_image'

def image_intake(tmp_path):
    work=tmp_path/'work';(work/'inputs').mkdir(parents=True);(work/'report').mkdir()
    version=image_file(work/'inputs/table.png')
    (work/'approved-inputs.json').write_text(json.dumps({'files':{'table.png':version}}))
    (work/'report/request.txt').write_text('Independent synthetic observations; fit y against x.')
    return ReportIntake(work),version

def test_image_transcription_preserves_cells_and_remains_source_bound(tmp_path):
    intake,version=image_intake(tmp_path)
    assert intake.prepare()['status']=='needs_image_transcription'
    rows=[['1','2.1'],['2',''],['3','6.3'],['4','7.7']]
    with pytest.raises(ValueError,match='exact_approved_image'):
        intake.record_image_table('table.png','0'*64,['x','y'],rows)
    recorded=intake.record_image_table('table.png',version,['x','y'],rows)
    assert recorded['rows']==4 and 'not_independently_verified' in recorded['scope']
    assert intake.prepare()['report_ready']
    assert list(csv.reader(io.StringIO((intake.case/'data.csv').read_text())))==[['x','y'],*rows]
    assert intake.record_image_table('table.png',version,['x','y'],rows)==recorded
    with pytest.raises(ValueError,match='already_frozen'):
        intake.record_image_table('table.png',version,['x','y'],[['1','999'],*rows[1:]])
    (intake.work/'inputs/table.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='source version changed'): intake.prepare()

def test_image_transcription_rejects_nonrectangular_or_numeric_inference(tmp_path):
    intake,version=image_intake(tmp_path)
    for rows in ([[1,2],[3,4]],[['1','2'],['3']], [['1','2'],['3',None]]):
        with pytest.raises(ValueError,match='literal_string_cells'):
            intake.record_image_table('table.png',version,['x','y'],rows)
    assert not (intake.report/'image-table.json').exists()


def test_image_transcription_cannot_write_through_a_redirected_report_directory(tmp_path):
    intake,version=image_intake(tmp_path)
    foreign=tmp_path/'foreign-report';intake.report.rename(foreign)
    try: intake.report.symlink_to(foreign,target_is_directory=True)
    except OSError: pytest.skip('Directory symlinks unavailable')
    with pytest.raises(ValueError,match='unsafe report directory'):
        intake.record_image_table('table.png',version,['x','y'],[['1','2'],['3','4']])
    assert not (foreign/'image-table.json').exists()


@pytest.mark.parametrize('extension,kind',[('png','PNG'),('jpg','JPEG')])
def test_ruled_image_rejects_filled_or_shifted_missing_cells(tmp_path,extension,kind):
    Image=pytest.importorskip('PIL.Image')
    from PIL import ImageDraw
    from scenarios.data_analysis.image_tables import image_table_layout
    image=Image.new('RGB',(640,440),'white');draw=ImageDraw.Draw(image)
    columns=['sample','x','y'];rows=[['A','1','2.1'],['B','2',''],['C','3','6.3'],['D','4','7.7']]
    for x in (20,220,420,620):draw.line((x,70,x,370),fill='black',width=2)
    for y in range(70,371,60):draw.line((20,y,620,y),fill='black',width=2)
    for i,row in enumerate([columns,*rows]):
        for j,value in enumerate(row):draw.text((30+j*200,85+i*60),value,fill='black')
    work=tmp_path/'work';(work/'inputs').mkdir(parents=True);(work/'report').mkdir()
    name='grid.'+extension;source=work/'inputs'/name;image.save(source,format=kind)
    version=hashlib.sha256(source.read_bytes()).hexdigest()
    (work/'approved-inputs.json').write_text(json.dumps({'files':{name:version}}))
    (work/'report/request.txt').write_text('Independent synthetic samples; fit y against x.')
    layout=image_table_layout(source)
    assert layout['data_rows']==4 and layout['columns']==3 and layout['empty_cells']==[[2,3]]
    intake=ReportIntake(work)
    assert intake.prepare()['attachment_sources'][0]['image_table_layout']==layout
    for wrong in ([rows[0],['B','2','6.3'],*rows[2:]], [rows[0],['B','2','6.3'],rows[3],['D','4','']]):
        with pytest.raises(ValueError,match='image_cell_occupancy_mismatch'):
            intake.record_image_table(name,version,columns,wrong)
        assert not (intake.report/'image-table.json').exists()
    recorded=intake.record_image_table(name,version,columns,rows)
    assert recorded['rows']==4 and intake.prepare()['report_ready']


@pytest.mark.parametrize('extension,kind',[('png','PNG'),('jpg','JPEG')])
def test_ppt_image_source_survives_actual_checkpoint_restore(tmp_path,monkeypatch,extension,kind):
    from scenarios.research_ppt import web_scope
    from scenarios.research_ppt.recovery import CheckpointPPTService, CheckpointRejected
    from scenarios.research_ppt.service import SCENE
    if not (SCENE/'dist/render.js').is_file(): pytest.skip('PPT renderer build required')
    monkeypatch.setattr(web_scope,'_WEB_PRIVATE_ROOT',tmp_path)
    source=tmp_path/('source.'+extension);version=image_file(source,kind)
    job=tmp_path/'job.json'
    job.write_text(json.dumps({'schema_version':1,'job_id':'image-checkpoint','slides':3,
        'allow_output':True,'inputs':[{'document_id':'doc_1','path':str(source),
        'name':source.name,'version_sha256':version}]}))
    original=CheckpointPPTService(job)
    pinned=original.pin_source('doc_1');handle=pinned['source_id']
    expected=original.read_source(handle)
    restored=CheckpointPPTService(job)
    assert restored.restore_status['restored'] is True
    assert restored.read_source(handle)==expected
    assert restored.handles[handle]['parsed']['images'][0]['evidence_scope']=='uploaded_image'
    source.write_bytes(b'changed image')
    with pytest.raises(CheckpointRejected): CheckpointPPTService(job)


def test_image_transcription_tool_is_exposed_by_actual_mcp_and_web_policy(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    for dependency in ('mcp','numpy','pandas','scipy.stats','statsmodels.api'):
        pytest.importorskip(dependency)
    private=tmp_path/'.local'
    intake,version=image_intake(private)
    root=Path(__file__).resolve().parents[1]
    env={**os.environ,'HARLESS_PRIVATE_ROOT':str(private),'HARLESS_REPORT_WORKSPACE':str(intake.work)}
    code="import asyncio,json,runpy; m=runpy.run_path('scenarios/data_analysis/report_session.py'); print(json.dumps([t.name for t in asyncio.run(m['server'].list_tools())]))"
    result=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,text=True,
        encoding='utf-8',capture_output=True,check=True,timeout=60)
    actual=json.loads(result.stdout)
    policy=json.loads((root/'scenarios/data_analysis/report-scenario.json').read_text())['allowed_tools']
    assert 'record_image_table' in actual
    assert set(policy)=={'mcp__research_report__'+name for name in actual}
