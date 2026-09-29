#!/usr/bin/env python3
"""Create private, unlabeled A/B review packets for the three v2 Gmail tasks."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local/benchmarks/research-weekly-loop/gmail-alert-motif-20260928"


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag in {"div", "tr", "p", "h2", "h3", "br"}:
            self.parts.append("\n")


def save(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", choices=("motif", "projection",
                                                 "baseline-projection",
                                                 "new-paired-projection"),
                        default="motif")
    args = parser.parse_args()
    out = BASE / {"motif": "blind-review-v2",
                  "projection": "blind-review-evidence-projection",
                  "baseline-projection": "blind-review-baseline-projection",
                  "new-paired-projection": "blind-review-new-paired-projection"}[
                      args.comparison]
    mapping = {}
    index = ["# Gmail 论文提醒匿名 A/B 审阅", "",
             "每题请分别检查：是否误把相邻工作列为直接相关；论文标题和线索是否出自邮件；阅读建议是否有用；是否符合 450 汉字上限。",
             "本组额外比较编译证据视图是否改变必要的研究判断。" if
             args.comparison != "motif" else "",
             "邮件只作为发现线索，勿把其中摘要当成论文原文。", ""]
    cases = (("alert-j", "alert-k", "alert-l") if args.comparison == "new-paired-projection"
             else ("alert-g", "alert-h", "alert-i"))
    for case in cases:
        source_events = BASE / case / "baseline/agent-events.jsonl"
        events = [json.loads(line) for line in source_events.read_text().splitlines()]
        results = [row for row in events if row.get("type") == "tool/result"]
        if len(results) != 2:
            raise ValueError(f"{case} does not have one search and one read")
        raw = results[-1]["data"]["message"]["content"][0]["content"][0]["text"]
        body = raw.split("<!doctype html>", 1)
        if len(body) != 2:
            raise ValueError(f"{case} lacks the original Gmail HTML")
        parser = VisibleText()
        parser.feed("<!doctype html>" + body[1])
        source = html.unescape(" ".join(parser.parts))
        source = "\n".join(line.strip() for line in source.splitlines() if line.strip())
        save(out / case / "source.txt", source + "\n")
        choices = ({"motif": ("baseline", "motif"),
                    "projection": ("motif", "motif-retry-1" if case == "alert-i"
                                   else "motif-retry-2"),
                    "baseline-projection": ("baseline", "baseline-retry-1"),
                    "new-paired-projection": ("baseline-retry-1", "motif-retry-1")})[
                        args.comparison]
        order = choices if hashlib.sha256(case.encode()).digest()[0] % 2 else choices[::-1]
        mapping[case] = {"A": order[0], "B": order[1]}
        for label, mode in mapping[case].items():
            answer = (BASE / case / mode / "answer.md").read_text()
            save(out / case / f"answer-{label}.md", answer)
        index.extend([f"## {case}", "",
                      f"- [邮件原始可见文字]({case}/source.txt)",
                      f"- [答案 A]({case}/answer-A.md)",
                      f"- [答案 B]({case}/answer-B.md)", ""])
    save(out / "review.md", "\n".join(index))
    save(out / "sealed-mapping.json",
         json.dumps(mapping, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"review": str(out / "review.md"), "tasks": len(mapping),
                      "mapping_separate": True}))


if __name__ == "__main__":
    main()
