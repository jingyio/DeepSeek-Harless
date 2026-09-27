"""MotifAgent contiguous tool-pattern miner, trimmed for SSS trace input.

Adapted from the frozen MotifAgent artifact's offline/motif_miner.py. This
discovers candidates only; it does not authorize executing a tool sequence.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Any


def normalize_repeated_tools(sequence: list[str]) -> list[str]:
    out: list[str] = []
    index = 0
    while index < len(sequence):
        tool = sequence[index]
        end = index + 1
        while end < len(sequence) and sequence[end] == tool:
            end += 1
        out.append(f"{tool}+" if end - index >= 2 else tool)
        index = end
    return out


def mine_motifs(sequences: list[list[str]], *, min_support: float = 0.10,
                min_len: int = 2, max_len: int = 8) -> list[dict[str, Any]]:
    if not sequences:
        return []
    if min_support <= 0 or min_len < 2 or max_len < min_len:
        raise ValueError("invalid motif mining bounds")
    threshold = (int(min_support) if min_support > 1
                 else max(1, math.ceil(min_support * len(sequences))))
    counter: Counter[tuple[str, ...]] = Counter()
    entry_counter: Counter[tuple[str, ...]] = Counter()
    for sequence in sequences:
        seen: set[tuple[str, ...]] = set()
        for length in range(min_len, min(max_len, len(sequence)) + 1):
            for offset in range(len(sequence) - length + 1):
                pattern = tuple(sequence[offset:offset + length])
                seen.add(pattern)
                if offset == 0:
                    entry_counter[pattern] += 1
        counter.update(seen)
    motifs = []
    for pattern, count in counter.items():
        if count < threshold:
            continue
        entry_count = entry_counter[pattern]
        tools = list(pattern)
        motif_id = "motif_" + hashlib.sha256("|".join(tools).encode()).hexdigest()[:8]
        motifs.append({
            "motif_id": motif_id, "tools": tools, "count": count,
            "support": count / len(sequences),
            "entry_count": entry_count,
            "entry_ratio": entry_count / count,
            "is_entry": entry_count * 2 > count,
            "status": "candidate_only",
        })
    motifs.sort(key=lambda row: (-row["support"], -row["count"],
                                 -len(row["tools"]), tuple(row["tools"])))
    return motifs
