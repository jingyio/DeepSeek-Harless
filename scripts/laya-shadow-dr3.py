#!/usr/bin/env python3
"""Shadow-only local Laya relevance audit on a fixed DR3 source snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.laya_decision import LayaDecisionPort  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / ".local/benchmarks/dr3-zh003/sources")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sources = sorted(args.source_dir.resolve(strict=True).glob("web-*.txt"))
    if not sources:
        raise ValueError("no DR3 web sources found")
    port = LayaDecisionPort()
    rows = []
    for path in sources:
        data = path.read_bytes()
        text = data.decode("utf-8")
        state = text[:900]
        decision = port.choose(
            state=state, question_id="source_role",
            instructions="这份材料对比较 3D 高斯溅射重定位的粗定位与精优化方法有什么作用？",
            criteria={
                "direct": "直接讨论 3DGS、位姿估计、重定位或配准方法，可用于方法比较",
                "background": "提供相关技术背景，但没有直接比较 3DGS 重定位方法",
                "unrelated": "主题无关，不应作为该方法比较的证据",
            },
        )
        rows.append({"file": path.name, "sha256": hashlib.sha256(data).hexdigest(),
                     "title": text.splitlines()[0], "choice": decision.choice,
                     "probability": decision.probability, "confidence": decision.confidence,
                     "model": decision.model, "input_characters": len(state),
                     "usage": decision.raw.get("usage"),
                     "all_probabilities": decision.raw["answers"]["source_role"].get("probabilities")})
        print(f"{path.name}: {decision.choice} p={decision.probability:.3f} confidence={decision.confidence}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise ValueError("output already exists")
    args.out.write_text(json.dumps({"mode": "shadow", "question": "DR3-zh003 source role",
                                   "model_requests": len(rows), "rows": rows}, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
