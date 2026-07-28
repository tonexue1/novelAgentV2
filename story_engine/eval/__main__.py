"""CLI：python -m story_engine.eval report|compare"""

from __future__ import annotations

import argparse
import sys

from story_engine.eval.compare import compare_json, compare_scorecards, render_compare
from story_engine.eval.scorecard import (
    render_scorecard,
    scorecard_from_run,
    scorecard_json,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m story_engine.eval",
        description="M5a 离线 scorecard / A-B compare（见 docs/EVALUATION.md §3.0）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_report = sub.add_parser("report", help="对一次 walk run 打分")
    p_report.add_argument("--run", required=True, help="run 根目录（含 stores/）")
    p_report.add_argument(
        "--runs",
        default=None,
        help="runs.jsonl 路径（默认 <run>/runs.jsonl）",
    )
    p_report.add_argument("--as-of", type=int, default=None, help="覆写 as-of 章号")
    p_report.add_argument("--json", action="store_true", help="JSON 输出")

    p_cmp = sub.add_parser("compare", help="两次 run 并排 Δ")
    p_cmp.add_argument("--a", required=True, help="baseline run 目录")
    p_cmp.add_argument("--b", required=True, help="变体 run 目录")
    p_cmp.add_argument("--runs-a", default=None, help="A 的 runs.jsonl")
    p_cmp.add_argument("--runs-b", default=None, help="B 的 runs.jsonl")
    p_cmp.add_argument("--as-of", type=int, default=None)
    p_cmp.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "report":
        sc = scorecard_from_run(args.run, runs_path=args.runs, as_of=args.as_of)
        print(scorecard_json(sc) if args.json else render_scorecard(sc))
        return

    if args.cmd == "compare":
        a = scorecard_from_run(args.a, runs_path=args.runs_a, as_of=args.as_of)
        b = scorecard_from_run(args.b, runs_path=args.runs_b, as_of=args.as_of)
        rep = compare_scorecards(a, b)
        print(compare_json(rep) if args.json else render_compare(rep))
        return

    parser.error(f"unknown cmd {args.cmd}")
    sys.exit(2)


if __name__ == "__main__":
    main()
