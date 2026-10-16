from scenarios.research_ppt.numeric_evidence import check_numeric_evidence, claims
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
    from pathlib import Path
    from scenarios.research_ppt.cli import prepare
    from scenarios.research_ppt.service import ROOT, PPTService
    from scenarios.research_ppt.tests.test_service import write_pdf
    area = ROOT / '.local'
    area.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=area) as temp:
        source = Path(temp) / 'study.pdf'
        write_pdf(source, 'Raw observations only. No computed statistical results.')
        service = PPTService(prepare([source], 'Make one slide', 1, True, persistent_library=False))
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
