from scenarios.research_ppt.numeric_evidence import check_numeric_evidence, complete_case_counts
from scenarios.research_ppt.server import _safe_failure
from scenarios.research_ppt.service import RenderFailure


def check(slide, text):
    return check_numeric_evidence(slide, [{'text': text}])


def test_public_ppt_counterexample_cannot_invent_regression_from_raw_csv():
    slide = {'title': '设计口径', 'bullets': [],
             'table': [['分析要素', '研究设定'], ['关联指标', 'r=0.970，对比原始天数 r=0.959']],
             'evidence_notes': [{'text': '完整案例 n=38，均值 27.77 MPa；斜率约 14.15 MPa/log10(天)；95%置信区间 [12.85,15.45]'}]}
    result = check(slide, 'specimen_id,x,y\nSIM-001,12,27.77\nSIM-002,14,14.15\n简单线性回归，95%置信水平')
    assert result['status'] == 'rejected'
    assert {row['metric'] for row in result['unsupported']} == {'mean', 'slope', 'confidence_interval:95', 'correlation'}
    assert not result['scientific_quality_certified']


def test_direct_results_allow_equivalent_numbers_and_faithful_rounding():
    result = check({'bullets': ['斜率 0.84381；R²=0.92746；p=4.2352e-22；均值 27.77；95% CI [0.76405,0.92358]']},
                   'slope = 0.8438145; R-squared = 0.9274577; p-value = 4.235211e-22; mean = 27.770; 95% CI [0.7640459,0.9235832]')
    assert result['status'] == 'passed'
    assert result['checked_claims'] == 5


def test_same_number_for_different_metric_or_extra_precision_does_not_pass():
    assert check({'bullets': ['斜率 0.95']}, 'r=0.95')['status'] == 'rejected'
    assert check({'bullets': ['斜率 0.951']}, 'slope=0.95')['status'] == 'rejected'
    assert check({'bullets': ['95% CI [1,3]']}, 'CI [1,2]; CI [2,3]')['status'] == 'rejected'
    assert check({'bullets': ['p=0.05']}, 'p<0.05')['status'] == 'rejected'
    assert check({'bullets': ['95% CI [1,3]']}, '90% CI [1,3]')['status'] == 'rejected'
    assert check({'bullets': ['p=0.0']}, 'p=0.001')['status'] == 'rejected'


def test_tables_and_speaker_notes_are_checked_without_treating_design_as_results():
    assert check({'table': [['指标', '均值'], ['A', '27.77']]}, '原始记录 27.77')['status'] == 'rejected'
    assert check({'notes': '斜率=14.15'}, '原始记录 14.15')['status'] == 'rejected'
    assert check({'bullets': ['n=38，排除2例；置信水平95%，双侧检验；斜率尚未计算；三页汇报']}, '')['checked_claims'] == 0


def test_visual_only_evidence_remains_unknown_not_falsely_rejected_or_certified():
    result = check_numeric_evidence({'bullets': ['r=0.95']}, [{'text': '', 'visual_input': True}])
    assert result['status'] == 'visual_review_required'
    assert not result['scientific_quality_certified']
    assert check_numeric_evidence({'bullets': ['r=0.95']}, [{'text': '', 'visual_input': True}, {'text': 'raw CSV'}])['status'] == 'rejected'


def test_public_error_is_repairable_and_does_not_reveal_private_payload():
    error = _safe_failure(RenderFailure({'code': 'unsupported_statistics', 'page': 2,
                                        'error': '/private/runtime/path', 'unsupported': ['private source']}))
    assert error['error'] == 'unsupported_statistics'
    assert error['page'] == 2
    assert '/private' not in str(error)
    assert 'private source' not in str(error)


def test_actual_service_rejects_unsupported_statistics_before_creating_deck():
    import tempfile
    import json
    from pathlib import Path
    from scenarios.research_ppt.service import ROOT, PPTService
    from scenarios.research_ppt.documents import file_hash
    area = ROOT / '.local'
    area.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=area) as temp:
        source = Path(temp) / 'study.txt'
        source.write_text('Raw observations only. No computed statistical results.', encoding='utf-8')
        job = Path(temp) / 'job.json'
        job.write_text(json.dumps({'schema_version': 1, 'job_id': 'numeric-source-test',
            'instruction': 'Make one slide', 'slides': 1, 'allow_output': True, 'allow_rsi': False,
            'inputs': [{'document_id': 'doc_1', 'name': source.name, 'path': str(source),
                        'version_sha256': file_hash(source)}]}), encoding='utf-8')
        service = PPTService(job)
        handle = service.pin_source('doc_1')['source_id']
        service.read_source(handle)
        plan = {'title': 'Design', 'slides': [{'title': 'Results', 'bullets': ['Slope=14.15'],
                                              'sources': [{'source_id': handle, 'page': 1}]}]}
        try:
            service.render_deck(plan)
        except RenderFailure as error:
            assert error.report['code'] == 'unsupported_statistics'
        else:
            raise AssertionError('Unverified statistics must not reach the renderer')
        assert not service.decks
        assert not list(service.output.glob('*/presentation.pptx'))


def count_sources():
    import json
    return [{'format': 'csv', 'text': 'id,x,y,note\na,1,5,\nb,2,,\nc,3,7,\nd,4,,\n'},
            {'format': 'json', 'text': json.dumps({'analysis_request': {
                'predictor': 'x', 'outcome': 'y', 'missing_policy': '完整案例，不填补'}})}]


def test_complete_case_counts_use_only_declared_variables_and_reject_wrong_sample():
    profile = complete_case_counts(count_sources())
    assert profile == {'total_rows': 4, 'complete_rows': 2, 'missing_rows': 2,
                       'columns': ['x', 'y'], 'missing_rule': 'empty_cells_only'}
    wrong = {'takeaway': '4 例中 2 例缺失，完整案例分析纳入 3 例',
             'bullets': ['排除2例，纳入3例']}
    result = check_numeric_evidence(wrong, [{'text': '原稿误写完整案例3例'}], sample_counts=profile)
    assert result['status'] == 'rejected'
    assert all(row['expected'] == 2 for row in result['unsupported'])
    corrected = {'bullets': ['原始总样本 n=4', '完整案例分析纳入 2 例', 'TXT原文误写完整案例3例，应纠正']}
    assert check_numeric_evidence(corrected, [], sample_counts=profile)['status'] == 'passed'


def test_sample_count_abstains_on_ambiguous_or_untyped_sources():
    sources = count_sources()
    assert complete_case_counts(sources[:1]) is None
    assert complete_case_counts(sources + sources[:1]) is None
    assert complete_case_counts(sources + sources[1:]) is None
    sources[0]['text'] = sources[0]['text'].replace('a,1,5,', 'a,1,NA,')
    assert complete_case_counts(sources) is None


def test_count_error_returns_only_validated_expected_number():
    error = _safe_failure(RenderFailure({'code': 'unsupported_statistics', 'page': 2,
                                        'expected_complete_case_n': 38}))
    assert '必须为 38' in error['next_action']
    error = _safe_failure(RenderFailure({'code': 'unsupported_statistics', 'page': 2,
                                        'expected_complete_case_n': '/private/path'}))
    assert '/private' not in str(error)
