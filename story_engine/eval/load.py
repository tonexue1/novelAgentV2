"""从 walk run 目录 / telemetry JSONL 加载评估输入。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.script import ChapterScript
from story_engine.schemas.stores.violation import Violation
from story_engine.telemetry.runrecord import RunRecord


def load_jsonl(model: type, path: Path) -> list:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(model.model_validate_json(line))
    return out


def load_run_records(path: Path) -> list[RunRecord]:
    return load_jsonl(RunRecord, path)


def chapter_num(chapter: str | int | None) -> int | None:
    if chapter is None:
        return None
    if isinstance(chapter, int):
        return chapter
    s = str(chapter).strip().lstrip("c")
    try:
        return int(s)
    except ValueError:
        return None


def infer_as_of(scripts: list[ChapterScript]) -> int | None:
    nums = [chapter_num(s.chapter) for s in scripts]
    nums = [n for n in nums if n is not None]
    return max(nums) if nums else None


@dataclass
class RunArtifacts:
    """一次 walk（或拷贝）的评估输入。"""

    run_dir: Path
    runs_path: Path | None = None
    records: list[RunRecord] = field(default_factory=list)
    arcs: list[ArcRecord] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    scripts: list[ChapterScript] = field(default_factory=list)
    has_runs: bool = False
    has_arc: bool = False
    has_violation: bool = False
    has_script: bool = False


def load_run(
    run_dir: str | Path,
    *,
    runs_path: str | Path | None = None,
) -> RunArtifacts:
    root = Path(run_dir)
    stores = root / "stores"
    # telemetry：显式 --runs > <run>/runs.jsonl > 无
    rp: Path | None
    if runs_path is not None:
        rp = Path(runs_path)
    elif (root / "runs.jsonl").exists():
        rp = root / "runs.jsonl"
    else:
        rp = None

    art = RunArtifacts(run_dir=root, runs_path=rp)
    if rp is not None and rp.exists():
        art.records = load_run_records(rp)
        art.has_runs = True

    arc_p = stores / "arc.jsonl"
    if arc_p.exists():
        art.arcs = load_jsonl(ArcRecord, arc_p)
        art.has_arc = True

    vio_p = stores / "violation.jsonl"
    if vio_p.exists():
        art.violations = load_jsonl(Violation, vio_p)
        art.has_violation = True

    script_p = stores / "script.jsonl"
    if script_p.exists():
        art.scripts = load_jsonl(ChapterScript, script_p)
        art.has_script = True

    return art
