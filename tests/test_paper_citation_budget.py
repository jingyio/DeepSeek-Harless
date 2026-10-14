"""Cumulative authorization snapshots must not reset or mutate old budgets."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('paper_citation_budget',
    Path(__file__).parents[1]/'scripts/paper-citation-rsi.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_new_authorization_preserves_old_cap_and_records_exact_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    private = tmp_path/'.local'; private.mkdir()
    old = private/'old.json'; old.write_text('{"cap_usd":4.84521046}')
    before = old.read_bytes()
    new = private/'new.json'
    new.write_text(json.dumps({'cap_usd':5.84521046, 'parent_cap_usd':4.84521046,
                               'incremental_cap_usd':1, 'reset_history':False}))
    loaded = probe.load_budget_record(new)
    assert loaded['cap_usd'] == 5.84521046
    assert loaded['path'] == '.local/new.json'
    assert loaded['sha256'] == hashlib.sha256(new.read_bytes()).hexdigest()
    assert old.read_bytes() == before
    new.write_text('{"cap_usd":5.94521046}')
    assert probe.load_budget_record(new) != loaded


def test_public_symlink_and_oversized_records_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    private = tmp_path/'.local'; private.mkdir()
    public = tmp_path/'public.json'; public.write_text('{"cap_usd":1}')
    link = private/'link.json'; link.symlink_to(public)
    large = private/'large.json'; large.write_text(' '*16385)
    for path in [public, link, large, private/'missing.json']:
        with pytest.raises(ValueError): probe.load_budget_record(path)


@pytest.mark.parametrize('record', [{'cap_usd':0}, {'cap_usd':-1}, {'cap_usd':True},
    {'cap_usd':float('inf')}, {'cap_usd':float('nan')}, {'cap_usd':'5'}, {}, []])
def test_invalid_caps_fail_closed(tmp_path, monkeypatch, record):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    private = tmp_path/'.local'; private.mkdir()
    path = private/'bad.json'; path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='finite and positive'): probe.load_budget_record(path)
