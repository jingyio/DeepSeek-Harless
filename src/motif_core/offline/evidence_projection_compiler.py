"""Compile output views only from independent successful tool observations.

The certificate records format and evidence-retention checks, not private
tool text. It is sealed into the same immutable Motif artifact as parameter
flow. Codecs must preserve task-visible evidence and fail closed at runtime.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from src.motif_core.output_view_codecs import CODECS


def compile_evidence_projections(
    artifact: Mapping[str, Any],
    traces: Mapping[str, Any],
    samples: Mapping[str, Mapping[str, Mapping[str, str]]],
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
        codec = CODECS.get(codec_id)
        if codec is None:
            raise ValueError(f"unknown evidence-preserving output codec: {codec_id}")
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
            view, stats = codec(raw)
            if (not isinstance(view, str) or not view
                    or stats["visible_fragments"] < 2
                    or stats["view_bytes"] >= stats["original_bytes"] * 0.75):
                raise ValueError("output projection did not preserve useful evidence")
            proofs.append({"trace_id": trace_id,
                           "observation_sha256": rows[0].observation_sha256,
                           "original_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                           "view_sha256": hashlib.sha256(view.encode()).hexdigest(),
                           **stats})
        if len({proof["original_sha256"] for proof in proofs}) != len(proofs):
            raise ValueError("output projection support repeats the same result")
        compiled[tool] = {"codec": codec_id,
                          "training_trace_ids": list(sources),
                          "validation_trace_id": validation,
                          "evidence_retention": "all_visible_text_and_headers",
                          "restore": "exact_original",
                          "proofs": proofs}
    return compiled
