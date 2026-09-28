"""Compile output views only from independent successful tool observations.

The certificate records format and evidence-retention checks, not private
tool text. It is sealed into the same immutable Motif artifact as parameter
flow. Codecs must preserve task-visible evidence and fail closed at runtime.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from src.motif_core.output_view_codecs import CODECS, CONTEXT_CODECS


def compile_evidence_projections(
    artifact: Mapping[str, Any],
    traces: Mapping[str, Any],
    samples: Mapping[str, Mapping[str, Mapping[str, Any]]],
    codec_by_tool: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    sources = artifact.get("source_trace_ids")
    validation = artifact.get("validation_trace_id")
    if (artifact.get("status") != "trace_validated_read_only"
            or not isinstance(sources, list) or len(sources) < 2
            or len(set(sources)) != len(sources)
            or not isinstance(validation, str) or validation in sources
            or not isinstance(codec_by_tool, Mapping)
            or set(codec_by_tool) - set(artifact.get("tools", []))):
        raise ValueError("output projection needs independent certified tool traces")
    compiled: dict[str, dict[str, Any]] = {}
    for tool, codec_id in codec_by_tool.items():
        codec = CODECS.get(codec_id) or CONTEXT_CODECS.get(codec_id)
        if codec is None:
            raise ValueError(f"unknown evidence-preserving output codec: {codec_id}")
        contextual = codec_id in CONTEXT_CODECS
        locator_tool = "mcp__scoped_research_read__locate_pinned_pdf_quote"
        if contextual and (codec_id != "pdf_match_quote_window_v1"
                           or tool != "mcp__scoped_research_read__read_pinned_pdf_match"
                           or locator_tool not in artifact["tools"]
                           or not any(edge.get("from_tool") == locator_tool
                                      and edge.get("from_field") == "match_id"
                                      and edge.get("to_tool") == tool
                                      and edge.get("to_param") == "match_id"
                                      for edge in artifact.get("transfer_evidence", []))):
            raise ValueError("PDF output view requires a compiled locator-to-read edge")
        proofs = []
        for trace_id in [*sources, validation]:
            sample = samples.get(trace_id, {}).get(tool)
            trace = traces.get(trace_id)
            rows = [row for row in getattr(trace, "records", ())
                    if row.name == tool and row.eligible]
            if (not isinstance(sample, Mapping)
                    or not isinstance(sample.get("text"), str)
                    or not sample["text"] or len(rows) != 1
                    or sample.get("observation_sha256")
                    != rows[0].observation_sha256):
                raise ValueError("output projection lacks a trace-bound tool result")
            raw = sample["text"]
            context = sample.get("context") if contextual else None
            if contextual:
                read = rows[0]
                locators = [row for row in getattr(trace, "records", ())
                            if row.name == locator_tool and row.eligible
                            and isinstance(row.observation, dict)
                            and row.observation.get("match_id") == (
                                read.arguments or {}).get("match_id")]
                if (len(locators) != 1 or not isinstance(context, Mapping)
                        or context.get("quote") != (locators[0].arguments or {}).get("quote")
                        or context.get("locator") != locators[0].observation
                        or context.get("match_id") != (
                            read.arguments or {}).get("match_id")
                        or sample.get("locator_observation_sha256")
                        != locators[0].observation_sha256):
                    raise ValueError("PDF view lacks a trace-bound locator and quote")
                view, stats = codec(raw, context)
            else:
                view, stats = codec(raw)
            if (not isinstance(view, str) or not view
                    or stats["visible_fragments"] < 2
                    or stats["view_bytes"] >= stats["original_bytes"] * 0.75):
                raise ValueError("output projection did not preserve useful evidence")
            proofs.append({"trace_id": trace_id,
                           "observation_sha256": rows[0].observation_sha256,
                           "original_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                           "view_sha256": hashlib.sha256(view.encode()).hexdigest(),
                           **({"locator_observation_sha256":
                               sample["locator_observation_sha256"]} if contextual else {}),
                           **stats})
        if len({proof["original_sha256"] for proof in proofs}) != len(proofs):
            raise ValueError("output projection support repeats the same result")
        compiled[tool] = {"codec": codec_id,
                          "training_trace_ids": list(sources),
                          "validation_trace_id": validation,
                          "evidence_retention": (
                              "exact_quote_and_context" if contextual
                              else "all_visible_text_and_headers"),
                          **({"context_from_tool": locator_tool,
                              "task_scope": "quote_verification"} if contextual else {}),
                          "restore": "exact_original",
                          "proofs": proofs}
    return compiled
