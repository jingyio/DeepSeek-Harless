#!/usr/bin/env python3
"""Recover the real generated renderer and create a private review package."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from adapters.paper_renderer import prepare_renderer, publish_generated_renderer, render_renderer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--run", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    publish = commands.add_parser("freeze-generated", help="冻结真实生成修订，等待人工源码审阅")
    publish.add_argument("--package", type=Path, required=True)
    publish.add_argument("--run", type=Path, required=True)
    publish.add_argument("--output", type=Path, required=True)
    render = commands.add_parser("replay-current", help="只重放原报告，不代表通用工具或质量通过")
    render.add_argument("--package", type=Path, required=True)
    render.add_argument("--manifest-sha256", required=True)
    render.add_argument("--task", type=Path, required=True)
    render.add_argument("--audit-sha256", required=True)
    render.add_argument("--python", type=Path, required=True)
    render.add_argument("--review", type=Path)
    render.add_argument("--review-sha256")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_renderer(args.run, args.output)
    elif args.command == "freeze-generated":
        result = publish_generated_renderer(args.package, args.run, args.output)
    else:
        result = render_renderer(args.package, args.manifest_sha256, args.task,
                                 args.audit_sha256, args.python, review_path=args.review,
                                 expected_review_sha256=args.review_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
