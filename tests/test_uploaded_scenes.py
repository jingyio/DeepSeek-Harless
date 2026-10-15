"""No-model diagnostics with real uploaded bytes; not scientific/model acceptance."""
from pathlib import Path
import hashlib
import math
import os
import json
import pytest
from src.adapters.session_files import SessionFiles
from scenarios.data_analysis.server import DatasetEvidence
from scenarios.paper_proofreading.server import PaperEvidence


def put(root, name, text):
    p=root/name; p.write_text(text,encoding='utf-8')
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_actual_csv_statistics_missing_pairs_and_cross_session_handle(tmp_path):
    root=tmp_path/'alice';root.mkdir();other=tmp_path/'bob';other.mkdir()
    sha=put(root,'data.csv','x,y,group\n1,2,A\n2,4,B\n,6,A\n3,,A\n')
    a,b=DatasetEvidence(root),DatasetEvidence(other)
    pin=a.pin('data.csv',sha)
    summary=a.summary(pin['source_id'])
    assert summary['rows']==4 and summary['columns'][0]['missing']==1
    assert summary['columns'][0]['numeric']['mean']==2
    assert summary['columns'][2]['kind']=='text_or_nonfinite'
    result=a.correlation(pin['source_id'],'x','y')
    assert result['pearson_r']==pytest.approx(1) and result['complete_pairs']==2
    assert result['excluded_missing_pairs']==2 and not result['causality_established']
    with pytest.raises(ValueError,match='source_not_in_session'):b.summary(pin['source_id'])
    put(root,'data.csv','x,y\n9,8\n')
    with pytest.raises(ValueError,match='version_changed'):a.summary(pin['source_id'])


@pytest.mark.parametrize('text,reason',[
    ('x,x\n1,2\n','duplicate_columns'),('x,y\n1\n','ragged_dataset'),
    ('x,y\n1,2\n1,4\n','constant_column'),('x,y\n1,2\nNaN,4\n','nonfinite_data'),
    ('x,y\n1,2\nword,4\n','numeric_columns')])
def test_data_failures_remain_errors(tmp_path,text,reason):
    s=DatasetEvidence(tmp_path);p=s.pin('d.csv',put(tmp_path,'d.csv',text))
    with pytest.raises(ValueError,match=reason):s.correlation(p['source_id'],'x','y')


def test_tsv_and_large_finite_correlation(tmp_path):
    s=DatasetEvidence(tmp_path);p=s.pin('d.tsv',put(tmp_path,'d.tsv','x\ty\n1e300\t2e300\n2e300\t4e300\n'))
    assert math.isfinite(s.correlation(p['source_id'],'x','y')['pearson_r'])


def test_paper_reuses_real_checker_and_invalidates_entire_scope(tmp_path):
    put(tmp_path,'main.tex',r'\input{section}\bibliography{references}\label{same}\label{same}')
    put(tmp_path,'section.tex',r'\cite{present,missing}')
    put(tmp_path,'references.bib','@article{present, title={Example}}\n')
    s=PaperEvidence(tmp_path);p=s.pin_sources('main.tex')
    r=s.read_sources(p['source_id']);d=r['diagnostic']
    assert d['missing_cited_keys']==['missing'] and len(d['duplicate_labels'])==1
    assert not d['reference_authenticity_checked'] and not r['compiled_by_this_task']
    put(tmp_path,'references.bib','@article{changed,title={Changed}}\n')
    with pytest.raises(ValueError,match='scope_version_changed'):s.read_sources(p['source_id'])


def test_paper_text_read_handle_views_and_no_external_inputs(tmp_path):
    s=PaperEvidence(tmp_path);p=s.pin('paper.md',put(tmp_path,'paper.md','Actual paper text.'))
    assert s.document(p['source_id'],1)['text']=='Actual paper text.'
    with pytest.raises(ValueError,match='wrong_or_unknown'):s.read_sources(p['source_id'])
    put(tmp_path,'main.tex',r'\input{../secret}')
    scope=s.pin_sources('main.tex')
    with pytest.raises(ValueError,match='escapes'):s.read_sources(scope['source_id'])


def test_paper_accepts_full_flat_source_set_without_raising_other_scene_limit(tmp_path):
    root = tmp_path/'paper'; root.mkdir()
    for index in range(16): put(root, f'section-{index}.tex', 'Text.')
    assert len(PaperEvidence(root).list_files()['files']) == 16
    with pytest.raises(ValueError, match='scene_input_limit'):
        SessionFiles(root).list_files()
    put(root, 'section-16.tex', 'Extra.')
    with pytest.raises(ValueError, match='scene_input_limit'):
        PaperEvidence(root).list_files()


def test_file_path_symlink_hardlink_and_versions(tmp_path):
    r=tmp_path/'files';r.mkdir();put(r,'a.txt','one');s=SessionFiles(r)
    with pytest.raises(ValueError,match='file_not_in_session'):s.read('../a.txt')
    with pytest.raises(ValueError,match='file_version_changed'):s.read('a.txt','0'*64)
    if os.name!='nt':
        (r/'link.txt').symlink_to(r/'a.txt')
        with pytest.raises(ValueError,match='file_not_in_session'):s.read('link.txt')
        os.link(r/'a.txt',r/'hard.txt')
        with pytest.raises(ValueError,match='private_regular'):s.read('hard.txt')


def test_task_admission_versions_cannot_be_replaced_by_a_new_pin(tmp_path):
    root=tmp_path/'inputs';root.mkdir();version=put(root,'data.csv','x\n1\n')
    (tmp_path/'approved-inputs.json').write_text(json.dumps({'files':{'data.csv':version}}))
    s=DatasetEvidence(root);new=put(root,'data.csv','x\n99\n')
    with pytest.raises(ValueError,match='task_admission'):s.pin('data.csv',new)
    with pytest.raises(ValueError,match='task_admission'):s.list_files()
