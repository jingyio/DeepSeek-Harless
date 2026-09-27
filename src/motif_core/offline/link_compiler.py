"""Certify a parameter edge between two independently certified read Motifs.

An observed connector is only descriptive. A link becomes executable only when
an explicitly attributed transfer repeats across independent tasks. Other
eligible reads may lie between Motifs; failed, unknown or effectful tools are
barriers. Intervening reads are never silently added to the execution plan.
"""

from __future__ import annotations

from typing import Any, Mapping

from .trace_compiler import _digest, _field_value


def link_signature(link: dict[str, Any]) -> str:
    return _digest({key: value for key, value in link.items()
                    if key != "link_digest"})


def _pair_rows(trace: Any, first: list[str], second: list[str]) -> list[Any] | None:
    rows = list(trace.records)
    matches = []
    for left in range(len(rows) - len(first) + 1):
        first_rows = rows[left:left + len(first)]
        if not all(row.eligible and row.name == name
                   for row, name in zip(first_rows, first)):
            continue
        for right in range(left + len(first), len(rows) - len(second) + 1):
            second_rows = rows[right:right + len(second)]
            if (all(row.eligible and row.name == name
                    for row, name in zip(second_rows, second))
                    and all(row.eligible for row in
                            rows[left + len(first):right])):
                matches.append(first_rows + second_rows)
    return matches[0] if len(matches) == 1 else None


def compile_read_links(training: list[Any], heldout: list[Any],
                       artifacts: list[dict[str, Any]],
                       contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return only links supported by two training tasks and one held-out task."""
    links = []
    for source in artifacts:
        source_tools = source["tools"]
        if source_tools[-1].endswith("+"):
            continue
        source_tool = source_tools[-1]
        fields = contracts[source_tool].output_fields
        for target in artifacts:
            target_tools = target["tools"]
            if (source is target or set(source_tools) & set(target_tools)
                    or target_tools[0].endswith("+")):
                continue
            target_tool = target_tools[0]
            for param in contracts[target_tool].required_params:
                candidates = []
                for field in fields:
                    support = []
                    values = []
                    contradicted = False
                    for trace in training:
                        rows = _pair_rows(trace, source_tools, target_tools)
                        if rows is None:
                            continue
                        left, right = rows[len(source_tools) - 1], rows[len(source_tools)]
                        value = _field_value(left.observation, field)
                        declared = (right.parameter_sources or {}).get(param)
                        actual = (right.arguments or {}).get(param)
                        if (value is None or type(value) is not type(actual)
                                or value != actual
                                or declared != {"from_tool": source_tool,
                                                "from_field": field}):
                            contradicted = True
                            break
                        support.append(trace)
                        values.append(value)
                    if (contradicted
                            or len({row.task_fingerprint for row in support}) < 2
                            or len({_digest(value) for value in values}) < 2):
                        continue
                    validated = []
                    heldout_contradicted = False
                    for trace in heldout:
                        rows = _pair_rows(trace, source_tools, target_tools)
                        if rows is None:
                            continue
                        left, right = rows[len(source_tools) - 1], rows[len(source_tools)]
                        value = _field_value(left.observation, field)
                        actual = (right.arguments or {}).get(param)
                        if (value is None or type(value) is not type(actual)
                                or value != actual
                                or (right.parameter_sources or {}).get(param)
                                != {"from_tool": source_tool, "from_field": field}
                                or trace.task_fingerprint in
                                {row.task_fingerprint for row in support}):
                            heldout_contradicted = True
                            break
                        validated.append(trace)
                    if validated and not heldout_contradicted:
                        candidates.append((field, support, validated[0]))
                # Ambiguous fields would make the runtime edge non-unique.
                if len(candidates) != 1:
                    continue
                field, support, validation = candidates[0]
                link = {
                    "status": "trace_validated_read_link",
                    "from_motif": source["motif_id"],
                    "to_motif": target["motif_id"],
                    "from_artifact_digest": source["certified_digest"],
                    "to_artifact_digest": target["certified_digest"],
                    "from_tool": source_tool, "from_field": field,
                    "to_tool": target_tool, "to_param": param,
                    "source_trace_ids": sorted(row.trace_id for row in support),
                    "validation_trace_id": validation.trace_id,
                }
                link["link_digest"] = link_signature(link)
                links.append(link)
    return sorted(links, key=lambda row: (row["from_motif"], row["to_motif"],
                                           row["to_param"]))


def validate_read_link(link: dict[str, Any], artifacts: Mapping[str, dict[str, Any]],
                       contracts: Mapping[str, Any]) -> None:
    source = artifacts.get(link.get("from_motif"))
    target = artifacts.get(link.get("to_motif"))
    if (link.get("status") != "trace_validated_read_link"
            or link.get("link_digest") != link_signature(link)
            or source is None or target is None or source is target
            or link.get("from_artifact_digest") != source["certified_digest"]
            or link.get("to_artifact_digest") != target["certified_digest"]
            or link.get("from_tool") != source["tools"][-1]
            or link.get("to_tool") != target["tools"][0]
            or set(source["tools"]) & set(target["tools"])
            or link.get("from_field") not in
            contracts[link["from_tool"]].output_fields
            or link.get("to_param") not in
            contracts[link["to_tool"]].required_params
            or len(set(link.get("source_trace_ids", []))) < 2
            or link.get("validation_trace_id") in link.get("source_trace_ids", [])):
        raise ValueError("cross-Motif link is stale or unsupported")
