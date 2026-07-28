"""A/B：baseline（setup=pro）vs director_setup flash。

把两次 walk 快照到 data/ab/<label>/，再跑 eval compare。
walk 仍写 data/walk；每次变体用独立 STORY_TELEMETRY_PATH，避免 runs 串味。

用法（仓库根目录）：
  uv run python scripts/ab_setup_flash.py                  # 默认 3 章 + genesis
  uv run python scripts/ab_setup_flash.py --chapters 5
  uv run python scripts/ab_setup_flash.py --only compare   # 只比已有快照
  uv run python scripts/ab_setup_flash.py --only a         # 只跑 baseline
  uv run python scripts/ab_setup_flash.py --dry-run

注意：
  - 需已配好 .env（STORY_LLM_PROVIDER=openai + key）。
  - 本脚本会用 env 整表覆盖 STORY_LLM_NODE_MODELS / THINKING（不与 .env 合并），
    只钉死 setup 两节点，其余走 node_profiles 默认档。
  - 不修改 node_profiles.py；确认后再手冻默认档。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WALK_DIR = ROOT / "data" / "walk"
DEFAULT_OUT = ROOT / "data" / "ab"

LABEL_A = "base"
LABEL_B = "setup-flash"

# 钉死这两节点，避免 .env 里残留覆盖污染对照
BASELINE_MODELS = {
    "director_setup": "deepseek-v4-pro",
    "director_setup_redirect": "deepseek-v4-pro",
}
BASELINE_THINKING = {
    "director_setup": "inherit",
    "director_setup_redirect": "inherit",
}
FLASH_MODELS = {
    "director_setup": "deepseek-v4-flash",
    "director_setup_redirect": "deepseek-v4-flash",
}
FLASH_THINKING = {
    "director_setup": "disabled",
    "director_setup_redirect": "disabled",
}


def _run(cmd: list[str], *, env: dict[str, str], dry_run: bool) -> None:
    print("\n>>", " ".join(cmd))
    tel = env.get("STORY_TELEMETRY_PATH", "")
    models = env.get("STORY_LLM_NODE_MODELS", "")
    thinking = env.get("STORY_LLM_NODE_THINKING", "")
    if tel:
        print(f"  STORY_TELEMETRY_PATH={tel}")
    if models:
        print(f"  STORY_LLM_NODE_MODELS={models}")
    if thinking:
        print(f"  STORY_LLM_NODE_THINKING={thinking}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def _variant_env(
    *,
    runs_path: Path,
    models: dict[str, str],
    thinking: dict[str, str],
) -> dict[str, str]:
    env = os.environ.copy()
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    if runs_path.exists():
        runs_path.unlink()
    env["STORY_TELEMETRY_PATH"] = str(runs_path)
    env["STORY_LLM_NODE_MODELS"] = json.dumps(models, ensure_ascii=False)
    env["STORY_LLM_NODE_THINKING"] = json.dumps(thinking, ensure_ascii=False)
    return env


def _snapshot(dest: Path, *, runs_path: Path, meta: dict, dry_run: bool) -> None:
    """runs_path 必须在 dest 之外（staging），否则 rmtree(dest) 会删掉刚写的 telemetry。"""
    print(f"\n>> snapshot -> {dest}")
    if dry_run:
        return
    if not WALK_DIR.exists():
        raise SystemExit(f"walk 目录不存在：{WALK_DIR}")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    # stores 是 scorecard 必需；chapters/checkpoints 便于事后翻
    for name in ("stores", "chapters", "checkpoints", "steps"):
        src = WALK_DIR / name
        if src.exists():
            shutil.copytree(src, dest / name)
    if runs_path.exists():
        shutil.copy2(runs_path, dest / "runs.jsonl")
    else:
        print(f"  !! no telemetry: {runs_path}")
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _walk_auto(
    *,
    chapters: int,
    genesis: bool,
    no_critic: bool,
    with_writer: bool,
    env: dict[str, str],
    dry_run: bool,
) -> None:
    cmd = [
        "uv",
        "run",
        "python",
        "scripts/walk.py",
        "auto",
        "--chapters",
        str(chapters),
    ]
    if genesis:
        cmd.append("--genesis")
    if no_critic:
        cmd.append("--no-critic")
    if with_writer:
        cmd.append("--with-writer")
    _run(cmd, env=env, dry_run=dry_run)


def _compare(out_dir: Path, *, dry_run: bool) -> None:
    a = out_dir / LABEL_A
    b = out_dir / LABEL_B
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "story_engine.eval",
        "compare",
        "--a",
        str(a),
        "--b",
        str(b),
    ]
    _run(cmd, env=os.environ.copy(), dry_run=dry_run)
    # 顺带各打一份 report
    for label in (LABEL_A, LABEL_B):
        rcmd = [
            "uv",
            "run",
            "python",
            "-m",
            "story_engine.eval",
            "report",
            "--run",
            str(out_dir / label),
        ]
        _run(rcmd, env=os.environ.copy(), dry_run=dry_run)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="director_setup pro vs flash A/B")
    p.add_argument("--chapters", type=int, default=3, help="连跑章数（默认 3）")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="快照根目录")
    p.add_argument(
        "--only",
        choices=("all", "a", "b", "compare"),
        default="all",
        help="只跑某一段（默认 all）",
    )
    p.add_argument("--no-genesis", action="store_true", help="不传 --genesis")
    p.add_argument("--no-critic", action="store_true", help="跳过 Continuity Critic")
    p.add_argument("--with-writer", action="store_true", help="渲染散文")
    p.add_argument("--dry-run", action="store_true", help="只打印命令")
    args = p.parse_args(argv)

    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    genesis = not args.no_genesis
    do_a = args.only in ("all", "a")
    do_b = args.only in ("all", "b")
    do_cmp = args.only in ("all", "compare")

    print(f"repo={ROOT}")
    print(f"out={out_dir}")
    print(f"chapters={args.chapters}  only={args.only}")

    tel_dir = out_dir / "_telemetry"

    if do_a:
        runs_a = tel_dir / f"{LABEL_A}.jsonl"
        env_a = _variant_env(
            runs_path=runs_a,
            models=BASELINE_MODELS,
            thinking=BASELINE_THINKING,
        )
        print("\n=== A: baseline (director_setup=pro) ===")
        t0 = time.time()
        _walk_auto(
            chapters=args.chapters,
            genesis=genesis,
            no_critic=args.no_critic,
            with_writer=args.with_writer,
            env=env_a,
            dry_run=args.dry_run,
        )
        _snapshot(
            out_dir / LABEL_A,
            runs_path=runs_a,
            meta={
                "label": LABEL_A,
                "chapters": args.chapters,
                "models": BASELINE_MODELS,
                "thinking": BASELINE_THINKING,
                "elapsed_s": None if args.dry_run else round(time.time() - t0, 1),
            },
            dry_run=args.dry_run,
        )

    if do_b:
        runs_b = tel_dir / f"{LABEL_B}.jsonl"
        env_b = _variant_env(
            runs_path=runs_b,
            models=FLASH_MODELS,
            thinking=FLASH_THINKING,
        )
        print("\n=== B: setup-flash ===")
        t0 = time.time()
        _walk_auto(
            chapters=args.chapters,
            genesis=genesis,
            no_critic=args.no_critic,
            with_writer=args.with_writer,
            env=env_b,
            dry_run=args.dry_run,
        )
        _snapshot(
            out_dir / LABEL_B,
            runs_path=runs_b,
            meta={
                "label": LABEL_B,
                "chapters": args.chapters,
                "models": FLASH_MODELS,
                "thinking": FLASH_THINKING,
                "elapsed_s": None if args.dry_run else round(time.time() - t0, 1),
            },
            dry_run=args.dry_run,
        )

    if do_cmp:
        print("\n=== compare ===")
        _compare(out_dir, dry_run=args.dry_run)

    print("\nDone. Check cost down vs d2/violations up or c2.core_overdue up.")
    print("Freeze into story_engine/llm/node_profiles.py only after numbers look good.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\nFAILED: exit={e.returncode}", file=sys.stderr)
        raise SystemExit(e.returncode)
