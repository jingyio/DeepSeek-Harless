"""Safety and factual regressions for read-only paper diagnostics."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('paper_checks', Path(__file__).parents[1] /
                                             'scenarios/paper-submission/checks.py')
checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)


def test_only_active_sources_and_correct_nocite_duplicate_semantics(tmp_path):
    (tmp_path/'main.tex').write_text(r'\input{active}\nocite{missing}\bibliography{refs}')
    (tmp_path/'active.tex').write_text(r'\cite{good}\label{x}\begin{figure}[!]\label{x}')
    (tmp_path/'old.tex').write_text(r'\cite{old_missing}\label{x}')
    (tmp_path/'refs.bib').write_text('@article{good, title={G}}\n@article{unused, title={A}}\n@article{unused, title={B}}')
    result = checks.source_diagnostics(tmp_path, 'main.tex', r'\bibitem{good}')
    assert result['missing_cited_keys'] == []
    assert result['missing_nocite_keys'] == ['missing']
    assert result['nocite_places_inline_marker'] is False
    assert result['active_files'] == ['active.tex', 'main.tex']
    assert result['duplicate_bib_keys'][0]['is_cited'] is False
    assert result['duplicate_bib_keys'][0]['is_rendered'] is False
    assert len(result['duplicate_labels'][0]['locations']) == 2
    assert result['invalid_float_positions'][0]['reason'] == 'modifier_without_position'


def test_no_exit_code_inference_from_pdf_success_log():
    result = checks.build_diagnostics('Output written on main.pdf\n', None)
    assert result['output_written'] is True
    assert result['exit_codes_known'] is False
    assert result['all_exit_codes_zero'] is False
    assert result['shell_escape_disabled'] is None
    assert checks.build_diagnostics('', {'steps': [{'command':['pdflatex','-no-shell-escape'],
                                                  'exit_code': 1}]})['all_exit_codes_zero'] is False


def test_handles_are_scoped_and_changed_content_fails_closed(tmp_path):
    case = tmp_path/'case';case.mkdir();source = case/'source';source.mkdir()
    (source/'main.tex').write_text(r'\begin{document}Text\end{document}')
    (case/'main.log').write_text('Output written on main.pdf')
    evidence = checks.PaperEvidence({'clear': {'root':str(case),'source_dir':'source',
                                              'main':'main.tex','log':'main.log'}}, tmp_path)
    pin = evidence.pin('clear', 'sources')
    assert evidence.read(pin['source_id'], 'sources')['version_sha256'] == pin['version_sha256']
    with pytest.raises(ValueError, match='view'): evidence.read(pin['source_id'], 'build')
    (source/'main.tex').write_text('new content')
    with pytest.raises(ValueError, match='changed'): evidence.read(pin['source_id'], 'sources')
    with pytest.raises(ValueError): evidence.pin('../escape', 'sources')


def test_external_input_and_symlink_are_rejected(tmp_path):
    root = tmp_path/'src';root.mkdir()
    (tmp_path/'outside.tex').write_text('private')
    (root/'main.tex').write_text(r'\input{../outside}')
    with pytest.raises(ValueError, match='escapes'): checks.source_diagnostics(root, 'main.tex', None)
    (root/'linked.tex').symlink_to(tmp_path/'outside.tex')
    with pytest.raises(ValueError): checks.safe_path(root, 'linked.tex')


def test_input_cycle_is_not_silently_accepted(tmp_path):
    (tmp_path/'main.tex').write_text(r'\input{main}')
    with pytest.raises(ValueError, match='cyclic'): checks.source_diagnostics(tmp_path, 'main.tex', None)


def test_acm_bibitem_comment_does_not_hide_rendered_key(tmp_path):
    (tmp_path/'main.tex').write_text(r'\cite{known}\bibliography{refs}')
    (tmp_path/'refs.bib').write_text('@article{known, title={A}}\n@article{known, title={B}}')
    bbl = '\\bibitem[Author(2026)]%\n        {known}\nText'
    result = checks.source_diagnostics(tmp_path, 'main.tex', bbl)
    assert result['rendered_keys'] == ['known']
    assert result['duplicate_bib_keys'][0]['is_rendered'] is True


def test_new_experiment_id_does_not_reset_cumulative_paper_budget(tmp_path, monkeypatch):
    # The controller accounting must include older
    # Motif runs even when the newly selected experiment has no runs yet.
    spec = importlib.util.spec_from_file_location('paper_budget_diagnostic',
                Path(__file__).parents[1]/'scripts/paper-motif-experiment.py')
    experiment = importlib.util.module_from_spec(spec); spec.loader.exec_module(experiment)
    monkeypatch.setattr(experiment, 'ROOT', tmp_path)
    monkeypatch.setattr(experiment, 'PRIOR', ['old/ledger.jsonl'])
    prior = tmp_path/'.local/experiments/old/ledger.jsonl'; prior.parent.mkdir(parents=True)
    prior.write_text('{"request_id":1,"observed_peak_usd":0.2,"reserved_upper_usd":0.3}\n')
    previous = tmp_path/'.local/paper-motif/previous/runs/execute/cost-ledger.jsonl'
    previous.parent.mkdir(parents=True)
    previous.write_text('{"request_id":2,"observed_peak_usd":null,"reserved_upper_usd":0.4}\n')
    reference = tmp_path/'.local/paper-reference/audit/runs/baseline-01/cost-ledger.jsonl'
    reference.parent.mkdir(parents=True)
    reference.write_text('{"request_id":3,"observed_peak_usd":0.1,"reserved_upper_usd":0.2}\n')
    rows, cost, snapshots = experiment.account(tmp_path/'.local/paper-motif/new-id')
    assert len(rows) == 3
    assert cost == pytest.approx(0.7)
    assert len(snapshots) == 3


def test_booked_request_keeps_reservation_until_terminal_usage(tmp_path, monkeypatch):
    import json
    spec = importlib.util.spec_from_file_location('pending_paper_budget',
                Path(__file__).parents[1]/'scripts/paper-motif-experiment.py')
    experiment = importlib.util.module_from_spec(spec); spec.loader.exec_module(experiment)
    monkeypatch.setattr(experiment, 'ROOT', tmp_path)
    monkeypatch.setattr(experiment, 'PRIOR', [])
    run = tmp_path/'.local/paper-reference/old/runs/baseline-01'
    (run/'requests').mkdir(parents=True)
    ledger = run/'cost-ledger.jsonl'
    body = json.dumps({'model':'deepseek-flash','max_tokens':32768,
                      'messages':[{'role':'user','content':'keep\u2028unicode'}]}).encode()
    (run/'requests/0001.json').write_bytes(body)
    _, upper, _ = experiment.reservation(body,max_output=32768)
    rows, cost, _ = experiment.account(tmp_path/'new')
    assert len(rows) == 1 and cost == pytest.approx(upper)
    assert rows[0]['accounting_status'] == 'booked_without_terminal_usage'
    ledger.write_text(json.dumps({'request_id':1,'observed_peak_usd':0.001,
                                  'reserved_upper_usd':upper})+'\n')
    rows, cost, _ = experiment.account(tmp_path/'new')
    assert len(rows) == 1 and cost == pytest.approx(0.001)

    # Earlier entry points named requests by a different, local sequence.
    # Those files are not evidence of an additional State.book request.
    monkeypatch.setattr(experiment, 'PRIOR', ['old/cost-ledger.jsonl'])
    old = tmp_path/'.local/experiments/old'; (old/'requests').mkdir(parents=True)
    (old/'requests/0001.json').write_bytes(body)
    (old/'cost-ledger.jsonl').write_text(json.dumps({'request_id':8,
        'observed_peak_usd':0.002,'reserved_upper_usd':upper})+'\n')
    rows, cost, _ = experiment.account(tmp_path/'new')
    assert len(rows) == 2 and cost == pytest.approx(0.003)


@pytest.fixture
def allocated_paper_budget(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('allocated_paper_budget',
                Path(__file__).parents[1]/'scripts/paper-motif-experiment.py')
    experiment = importlib.util.module_from_spec(spec); spec.loader.exec_module(experiment)
    monkeypatch.setattr(experiment, 'ROOT', tmp_path)
    monkeypatch.setattr(experiment, 'PRIOR', [])
    return experiment


def test_cross_host_money_is_preserved_without_becoming_model_requests(tmp_path, allocated_paper_budget):
    import json
    folder = tmp_path/'.local/paper-motif/allocations'; folder.mkdir(parents=True)
    for name, kind, amount in [('remote', 'remote_budget_allocation', .25),
                               ('prior', 'historical_cost_floor', .1)]:
        (folder/(name+'.json')).write_text(json.dumps({
            'schema_version': 1, 'kind': kind, 'reserved_usd': amount}))
    ledger = tmp_path/'.local/paper-motif/previous/runs/baseline/cost-ledger.jsonl'
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({'request_id': 1, 'observed_peak_usd': .2,
                                  'reserved_upper_usd': .3})+'\n')
    for experiment_id in ('first', 'second'):
        rows, cost, snapshots = allocated_paper_budget.account(tmp_path/experiment_id)
        assert len(rows) == 1
        assert cost == pytest.approx(.55)
        assert len(snapshots) == 3
        assert snapshots[str((folder/'remote.json').relative_to(tmp_path))] == allocated_paper_budget.sha(folder/'remote.json')


@pytest.mark.parametrize('change', [
    {'reserved_usd': -1}, {'reserved_usd': True}, {'reserved_usd': '0.25'},
    {'reserved_usd': float('inf')}, {'reserved_usd': float('nan')},
    {'kind': 'unknown'}, {'schema_version': 2}])
def test_invalid_cross_host_allocations_fail_closed(tmp_path, allocated_paper_budget, change):
    import json
    path = tmp_path/'.local/paper-motif/allocations/invalid.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'schema_version': 1, 'kind': 'remote_budget_allocation',
                               'reserved_usd': .25, **change}))
    with pytest.raises(ValueError, match='invalid paper budget allocation'):
        allocated_paper_budget.account(tmp_path/'new')
