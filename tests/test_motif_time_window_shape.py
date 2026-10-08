"""Calendar windows may be a bounded, typed Motif entry slot."""

import pytest

from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.trace_compiler import _valid_param


def test_time_window_shape_accepts_only_bounded_explicit_instants():
    valid = [{"start": "2026-10-16T09:00:00+08:00",
              "end": "2026-10-16T12:00:00+08:00"}]
    assert _valid_param(valid, collection=False, shape="time_window_list")
    assert not _valid_param([], collection=False, shape="time_window_list")
    assert not _valid_param(valid * 9, collection=False, shape="time_window_list")
    assert not _valid_param([{"start": "tomorrow", "end": valid[0]["end"]}],
                            collection=False, shape="time_window_list")
    assert not _valid_param([{**valid[0], "unexpected": "value"}],
                            collection=False, shape="time_window_list")


def test_contract_parser_requires_declared_shape():
    name = "mcp__calendar_fixture__find-available-slots"
    spec = {name: {"required_params": ["timeWindows"], "read_only": True,
                   "replay_stable": True,
                   "parameter_shapes": [["timeWindows", "time_window_list"]]}}
    contracts = parse_tool_contracts(spec)
    assert dict(contracts[name].parameter_shapes) == {"timeWindows": "time_window_list"}
    spec[name]["parameter_shapes"][0][1] = "arbitrary_json"
    with pytest.raises(ValueError):
        parse_tool_contracts(spec)
