"""分步走查 —— 每步独立文件夹：context/（喂给 LLM 的上下文）+ out/（产物）。

目录示例：
  data/walk/
    steps/
      00_g0/out/seed.json
      01_g1/context/001_architect.txt
            out/l0.json  l1.json
      07_plan/context/001_planner.txt
             out/plan.json
    stores/          # 共享 Script/Memory/Arc JSONL
    README.txt       # 进度速览

用法：
  uv run python scripts/walk.py status
  uv run python scripts/walk.py run g0
  uv run python scripts/walk.py show g1.context
  uv run python scripts/walk.py auto --chapters 3
      # 干净重跑 1…N（重种 stores）；章末写 checkpoints/c{n}/
  uv run python scripts/walk.py rollback --to 1
      # 世界回到第 1 章末；--to 0 = 回到 G5、清全部章
  uv run python scripts/walk.py continue --chapters 10
      # 从下一章接到 10（不重种）
  uv run python scripts/walk.py continue --from 2 --chapters 10
      # 先 rollback 到 1，再跑 2…10
  uv run python scripts/walk.py reset

需要 .env：STORY_LLM_PROVIDER=openai + STORY_OPENAI_API_KEY（g0/g3/script 除外）。
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from story_engine.config import load_settings
from story_engine.llm.factory import build_llm_client
from story_engine.nodes.base import NodeContext
from story_engine.nodes.consumption.writer import Writer
from story_engine.nodes.planning.architect import Architect
from story_engine.nodes.planning.planner import Planner
from story_engine.nodes.planning.worldbuilder import Worldbuilder
from story_engine.nodes.production.character import Character
from story_engine.nodes.production.director import DirectorDispatch, DirectorSetup
from story_engine.nodes.recorder.extractor import Extractor
from story_engine.nodes.recorder.reconciler import Reconciler
from story_engine.nodes.system.applier import Applier
from story_engine.nodes.system.assembler import Assembler
from story_engine.nodes.validation.faithfulness_check import FaithfulnessCheck
from story_engine.nodes.validation.genesis_gate import check_closure
from story_engine.orchestrator.loop import (
    _DEFAULT_MAX_BEATS,
    _brief_memories,
    _due_foreshadows,
    _recent_tails,
    _related_memories,
    _to_scene,
    run_chapter,
)
from story_engine.primitives.ids import mint_chapter
from story_engine.schemas.artifacts.chapter_plan import ChapterPlan
from story_engine.schemas.artifacts.genesis_gap import GenesisGap
from story_engine.schemas.artifacts.recorder_output import RecorderOutput
from story_engine.schemas.artifacts.scene_script import SceneScript
from story_engine.schemas.artifacts.seed import Seed
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.manuscript import Manuscript
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.plan import L0, L1, L2
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene
from story_engine.schemas.stores.world import WorldEntity
from story_engine.stores.json_backend import JsonStore
from story_engine.telemetry.runrecord import Telemetry

ROOT = Path("data/walk")
STEPS_DIR = ROOT / "steps"
STORES_DIR = ROOT / "stores"
CHAPTERS_DIR = ROOT / "chapters"
CHECKPOINTS_DIR = ROOT / "checkpoints"
CHAPTER = 1
GENESIS_STEPS = ("g0", "g1", "g2", "g3", "g4", "g5")
_STORE_FILES = (
    "script.jsonl",
    "mem.jsonl",
    "arc.jsonl",
    "manuscript.jsonl",
    "violation.jsonl",
)

# (step_id, folder_name, description)
STEPS: list[tuple[str, str, str]] = [
    ("g0", "00_g0", "种子摄入（写默认 Seed，不打 LLM）"),
    ("g1", "01_g1", "Architect：seed → L0 + L1"),
    ("g2", "02_g2", "Worldbuilder + Genesis Gate"),
    ("g3", "03_g3", "整包收口（M2 自动放行）"),
    ("g4", "04_g4", "Architect：L1 → L2[卷1]"),
    ("g5", "05_g5", "Arc 台账 + tier0/1 seed 画像"),
    ("plan", "07_plan", "Planner → ChapterPlan（第 1 章）"),
    ("setup", "08_setup", "Director·setup → SceneScript"),
    ("act", "09_act", "dispatch⇄Character → 各场 beats"),
    ("script", "10_script", "定序 + 落 ScriptStore（flagged）"),
    ("write", "11_write", "Writer → 散文"),
    ("extract", "12_extract", "Extractor → 记忆候选"),
    ("faithful", "13_faithful", "Faithfulness Check"),
    ("reconcile", "14_reconcile", "Reconciler → 落 Memory/Arc"),
]

STEP_META = {sid: (folder, desc) for sid, folder, desc in STEPS}
# 完成标记：该步 out/ 下这个文件存在即算完成
DONE_FILE = {
    "g0": "seed.json",
    "g1": "l1.json",
    "g2": "gap.json",
    "g3": "ack.json",
    "g4": "l2.json",
    "g5": "profiles.json",
    "plan": "plan.json",
    "setup": "scene_script.json",
    "act": "beats.json",
    "script": "script.json",
    "write": "manuscript.json",
    "extract": "candidates.json",
    "faithful": "verified.json",
    "reconcile": "reconciled.json",
}

DEFAULT_SEED = Seed(
    logline="辍学青年从社会底层起步，一步步登顶黑道教父的故事",
    genre=["都市", "黑道", "成长", "权力博弈"],
    tone=["冷硬", "克制", "残酷中带人情"],
    ending_intent=(
        "主角登顶黑道金字塔，却发现王座上只剩孤立与代价——"
        "权力到手，人情、自由与旧日自我都被抵押干净"
    ),
    protagonist_intent=[
        "从被人踩的辍学少年变成能定生死的人",
        "护住几个真正在乎的人，哪怕手段脏",
        "在刀口上活下去，并学会把规矩握在自己手里",
        "搞清楚登顶到底是为了报复、生存，还是证明自己",
    ],
    hard_rules=[
        "权力推进靠具体利益、人情债与暴力后果，不靠突然开挂或无代价逆袭",
        "反派与对手有自己的地盘逻辑，不写成单一脸谱；主角自己的贪婪与恐惧也是阻力",
        "暴力若出现，服务于人物选择与势力消长，不作猎奇堆尸",
        "主题（权力的代价）晚于具体生存与攀爬亮相：先写街头、饭碗与小局",
    ],
    refs=["都市黑道成长：先底层生存与小局站队，登顶与代价压到中后段"],
)

# 当前正在跑的步骤（供 prompt hook 落盘）
_ACTIVE_STEP: str | None = None
_PROMPT_SEQ: int = 0
# auto 批跑时直接指定 context 目录（不经 STEP_META）
_PROMPT_CTX_DIR: Path | None = None


# ── 路径 ────────────────────────────────────────────────────────


def _step_dir(step: str) -> Path:
    folder, _ = STEP_META[step]
    return STEPS_DIR / folder


def _ctx_dir(step: str) -> Path:
    return _step_dir(step) / "context"


def _out_dir(step: str) -> Path:
    return _step_dir(step) / "out"


def _done(step: str) -> bool:
    return (_out_dir(step) / DONE_FILE[step]).exists()


def _prepare_step(step: str) -> None:
    """开跑前：建目录；清空本步旧 context（避免和上次调用混在一起）。"""
    global _ACTIVE_STEP, _PROMPT_SEQ
    _ACTIVE_STEP = step
    _PROMPT_SEQ = 0
    ctx = _ctx_dir(step)
    out = _out_dir(step)
    if ctx.exists():
        shutil.rmtree(ctx)
    ctx.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)


def _finish_step(step: str, note: str = "") -> None:
    global _ACTIVE_STEP
    meta = {
        "step": step,
        "folder": STEP_META[step][0],
        "desc": STEP_META[step][1],
        "prompt_files": sorted(p.name for p in _ctx_dir(step).glob("*.txt")),
        "out_files": sorted(p.name for p in _out_dir(step).iterdir() if p.is_file()),
        "note": note,
    }
    (_step_dir(step) / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _ACTIVE_STEP = None
    _write_readme()


def _on_prompt(node: str, prompt: str) -> None:
    global _PROMPT_SEQ
    ctx_root = _PROMPT_CTX_DIR
    if ctx_root is None:
        if _ACTIVE_STEP is None:
            return
        ctx_root = _ctx_dir(_ACTIVE_STEP)
    _PROMPT_SEQ += 1
    path = ctx_root / f"{_PROMPT_SEQ:03d}_{node}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt, encoding="utf-8")
    print(f"  ↳ context/{path.name}  ({len(prompt)} 字)")


def _save_out(step: str, name: str, obj: Any) -> Path:
    path = _out_dir(step) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, BaseModel):
        text = obj.model_dump_json(indent=2, exclude_none=True)
    elif isinstance(obj, list) and obj and isinstance(obj[0], BaseModel):
        text = json.dumps(
            [o.model_dump(mode="json", exclude_none=True) for o in obj],
            ensure_ascii=False,
            indent=2,
        )
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    print(f"  ↳ out/{name}")
    return path


def _save_ctx_note(step: str, name: str, text: str) -> Path:
    """非 LLM 的上下文说明（如 g3 人工审阅清单）。"""
    path = _ctx_dir(step) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"  ↳ context/{name}")
    return path


def _load_out(step: str, name: str, model: type[BaseModel]):
    path = _out_dir(step) / name
    if not path.exists():
        raise SystemExit(f"缺产物 {path} —— 请先跑前置步骤（walk.py status）")
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _load_out_list(step: str, name: str, model: type[BaseModel]) -> list:
    path = _out_dir(step) / name
    if not path.exists():
        raise SystemExit(f"缺产物 {path}")
    return [model.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def _load_out_json(step: str, name: str) -> Any:
    path = _out_dir(step) / name
    if not path.exists():
        raise SystemExit(f"缺产物 {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _preview(path: Path, max_chars: int = 2000) -> None:
    text = path.read_text(encoding="utf-8")
    print(f"── {path.relative_to(ROOT)}（{len(text)} 字）──")
    if len(text) <= max_chars:
        print(text)
    else:
        print(text[:max_chars] + f"\n… 截断，全文见 {path}")


def _write_readme() -> None:
    lines = [
        "Story Engine 走查目录",
        f"根路径：{ROOT.resolve()}",
        "",
        "每步：steps/<NN_step>/context/  = 喂给 LLM 的 prompt",
        "      steps/<NN_step>/out/      = 该步产物",
        "",
        "进度：",
    ]
    for sid, folder, desc in STEPS:
        mark = "✓" if _done(sid) else "·"
        lines.append(f"  {mark} {folder:<12} {desc}")
    pending = [s for s, _, _ in STEPS if not _done(s)]
    lines.append("")
    if pending:
        lines.append(f"下一步：uv run python scripts/walk.py run {pending[0]}")
    else:
        lines.append("全部完成。")
    (ROOT / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── LLM / stores ────────────────────────────────────────────────


def _ctx() -> tuple[NodeContext, Telemetry]:
    settings = load_settings()
    if settings.llm_provider != "openai" or not settings.openai_api_key:
        raise SystemExit(
            "请在 .env 设 STORY_LLM_PROVIDER=openai 和 STORY_OPENAI_API_KEY"
        )
    tel = Telemetry(settings.telemetry_path)
    llm = build_llm_client(settings, telemetry=tel)
    llm._on_prompt = _on_prompt  # noqa: SLF001 — 走查专用钩子
    return NodeContext(llm=llm, telemetry=tel), tel


def _mem_arc_stores() -> tuple[JsonStore, JsonStore]:
    STORES_DIR.mkdir(parents=True, exist_ok=True)
    mem = JsonStore(MemoryEntry, STORES_DIR / "mem.jsonl", key_field="id")
    arc = JsonStore(ArcRecord, STORES_DIR / "arc.jsonl", key_field="id")
    return mem, arc


def _script_ms_stores() -> tuple[JsonStore, JsonStore]:
    STORES_DIR.mkdir(parents=True, exist_ok=True)
    script = JsonStore(ChapterScript, STORES_DIR / "script.jsonl", key_field="chapter")
    ms = JsonStore(Manuscript, STORES_DIR / "manuscript.jsonl", key_field="chapter")
    return script, ms


# ── 各步 ────────────────────────────────────────────────────────


def step_g0() -> None:
    _prepare_step("g0")
    _save_ctx_note(
        "g0",
        "000_note.txt",
        "G0 无 LLM。人工/默认种子即全部输入。可直接编辑 out/seed.json 后再跑 g1。",
    )
    path = _save_out("g0", "seed.json", DEFAULT_SEED)
    _finish_step("g0")
    print("G0 种子已写入（可改 steps/00_g0/out/seed.json 后再跑 g1）")
    _preview(path, 1200)


def step_g1() -> None:
    _prepare_step("g1")
    ctx, tel = _ctx()
    seed = _load_out("g0", "seed.json", Seed)
    print("调用 Architect.bootstrap …")
    l0, l1 = Architect().bootstrap(ctx, seed)
    _save_out("g1", "l0.json", l0)
    _save_out("g1", "l1.json", l1)
    _finish_step("g1")
    print(f"L0 核心问题：{l0.core_dramatic_question}")
    print(f"L1 threads={len(l1.threads)} arcs={len(l1.character_arcs)} "
          f"world_refs={l1.world_refs}")
    _preview(_out_dir("g1") / "l0.json", 1500)
    print()
    _preview(_out_dir("g1") / "l1.json", 2000)
    print("telemetry:", tel.summary())


def step_g2() -> None:
    _prepare_step("g2")
    ctx, tel = _ctx()
    settings = load_settings()
    l0 = _load_out("g1", "l0.json", L0)
    l1 = _load_out("g1", "l1.json", L1)
    print("调用 Worldbuilder.build_for …")
    world = Worldbuilder().build_for(ctx, l1, l0)
    gap = check_closure(l0, l1, world, iteration=0, max_iter=settings.genesis_max_iter - 1)
    for i in range(1, settings.genesis_max_iter):
        if gap.verdict.value != "REITERATE":
            break
        print(f"Gate=REITERATE，第 {i} 轮重补 canon …")
        world = Worldbuilder().build_for(ctx, l1, l0)
        gap = check_closure(l0, l1, world, iteration=i, max_iter=settings.genesis_max_iter - 1)
    _save_out("g2", "world.json", world)
    _save_out("g2", "gap.json", gap)
    _finish_step("g2")
    print(f"Gate verdict={gap.verdict.value}  dangling={gap.dangling}")
    _preview(_out_dir("g2") / "gap.json", 800)
    print()
    _preview(_out_dir("g2") / "world.json", 2000)
    print("telemetry:", tel.summary())


def step_g3() -> None:
    _prepare_step("g3")
    gap = _load_out("g2", "gap.json", GenesisGap)
    note = (
        "G3 人工共创触点（M2 自动放行）。\n"
        "请审阅：\n"
        "  steps/01_g1/out/l0.json\n"
        "  steps/01_g1/out/l1.json\n"
        "  steps/02_g2/out/world.json\n"
        "  steps/02_g2/out/gap.json\n"
        f"当前 Gate={gap.verdict.value}\n"
        "可手改 world/l1 后再跑 g4（g4 会读磁盘上的最新文件）。\n"
    )
    _save_ctx_note("g3", "000_review_checklist.txt", note)
    ack = {
        "status": "auto_pass",
        "note": "M2 人工共创触点暂缓；你现在等于在做人工审阅",
        "gate_verdict": gap.verdict.value,
    }
    _save_out("g3", "ack.json", ack)
    _finish_step("g3")
    print(note)


def step_g4() -> None:
    _prepare_step("g4")
    ctx, tel = _ctx()
    l0 = _load_out("g1", "l0.json", L0)
    l1 = _load_out("g1", "l1.json", L1)
    print("调用 Architect.expand_volume …")
    l2 = Architect().expand_volume(ctx, l0, l1)
    _save_out("g4", "l2.json", l2)
    _finish_step("g4")
    spine = l2.volume_spine
    print(f"L2 vol={l2.vol_id} goal={l2.goal}")
    if spine:
        print(f"spine.pressure={spine.shared_pressure[:60]}…")
        print(f"spine.inciting={spine.inciting[:60]}…")
    print(f"beats={len(l2.chapter_beats)} "
          f"touches={[b.touches_spine for b in l2.chapter_beats]}")
    _preview(_out_dir("g4") / "l2.json", 2400)
    print("telemetry:", tel.summary())


def step_g5() -> None:
    _prepare_step("g5")
    ctx, tel = _ctx()
    seed = _load_out("g0", "seed.json", Seed)
    l0 = _load_out("g1", "l0.json", L0)
    l1 = _load_out("g1", "l1.json", L1)
    print("调用 Architect.seed_profiles + Applier.init_arcs …")
    profiles = Architect().seed_profiles(ctx, seed, l0, l1)
    arcs = Applier().init_arcs(l1)
    for p in (STORES_DIR / "mem.jsonl", STORES_DIR / "arc.jsonl"):
        if p.exists():
            p.unlink()
    mem, arc_store = _mem_arc_stores()
    for a in arcs:
        arc_store.append(a)
    for p in profiles:
        mem.append(p)
    _save_out("g5", "arcs.json", arcs)
    _save_out("g5", "profiles.json", profiles)
    _finish_step("g5")
    print(f"arcs={len(arcs)} profiles={len(profiles)}")
    _preview(_out_dir("g5") / "profiles.json", 2000)
    print("telemetry:", tel.summary())
    print("S₀ 就绪。下一步 run plan")


def step_plan() -> None:
    _prepare_step("plan")
    ctx, tel = _ctx()
    l0 = _load_out("g1", "l0.json", L0)
    l1 = _load_out("g1", "l1.json", L1)
    l2 = _load_out("g4", "l2.json", L2)
    _, arc_store = _mem_arc_stores()
    script_store, _ = _script_ms_stores()
    due = _due_foreshadows(arc_store, CHAPTER)
    recent = _recent_tails(script_store, CHAPTER)
    _save_ctx_note(
        "plan",
        "000_inputs.txt",
        "非 prompt 正文、但参与装配的输入摘要：\n"
        f"- due_foreshadows = {json.dumps(due, ensure_ascii=False)}\n"
        f"- recent_summaries = {json.dumps(recent, ensure_ascii=False)}\n"
        f"- arcs count = {len(arc_store.all())}\n"
        "完整 LLM prompt 见同目录 001_planner.txt（调用时自动写入）。\n",
    )
    print("调用 Planner.plan …")
    plan = Planner().plan(
        ctx,
        chapter=CHAPTER,
        l0=l0,
        l1=l1,
        l2=l2,
        arcs=arc_store.all(),
        due_foreshadows=due,
        recent_summaries=recent,
    )
    _save_out("plan", "plan.json", plan)
    _finish_step("plan")
    print(f"chapter_goal={plan.chapter_goal}")
    print(f"story_beats={[b.gist for b in plan.story_beats]}")
    _preview(_out_dir("plan") / "plan.json", 2400)
    print("telemetry:", tel.summary())


def step_setup() -> None:
    _prepare_step("setup")
    ctx, tel = _ctx()
    plan = _load_out("plan", "plan.json", ChapterPlan)
    world = _load_out_list("g2", "world.json", WorldEntity)
    print("调用 DirectorSetup.split_scenes …")
    script = DirectorSetup().split_scenes(ctx, chapter=CHAPTER, plan=plan, world=world)
    _save_out("setup", "scene_script.json", script)
    _finish_step("setup")
    for s in script.scenes:
        print(f"  {s.scene_id} @ {s.location}  obligations="
              f"{[o.obligation_id for o in s.obligations]}")
    _preview(_out_dir("setup") / "scene_script.json", 2800)
    print("telemetry:", tel.summary())


def step_act() -> None:
    _prepare_step("act")
    ctx, tel = _ctx()
    scene_script = _load_out("setup", "scene_script.json", SceneScript)
    mem, _ = _mem_arc_stores()
    dispatcher, actor = DirectorDispatch(), Character()
    scenes_out: list[dict] = []
    print("现场调度循环…")
    for contract in scene_script.scenes:
        buffer: list[Beat] = []
        limit = contract.budget.max_beats or _DEFAULT_MAX_BEATS
        while len(buffer) < limit:
            dispatch = dispatcher.next_beat(
                ctx, chapter=CHAPTER, contract=contract, done_beats=buffer
            )
            if dispatch is None:
                break
            beat = actor.act(
                ctx,
                chapter=CHAPTER,
                dispatch=dispatch,
                contract=contract,
                known_facts=Assembler().known_facts(
                    char=dispatch.owner, chapter=CHAPTER, mem_store=mem,
                    focus=dispatch.dramatic_goal,
                ),
                buffer=buffer,
            )
            buffer.append(beat)
            print(f"  {contract.scene_id} beat#{len(buffer)} "
                  f"owner={beat.owner} → {beat.as_text()[:60]}")
        scenes_out.append({
            "scene_id": contract.scene_id,
            "beats": [b.model_dump(mode="json", exclude_none=True) for b in buffer],
        })
    _save_out("act", "beats.json", scenes_out)
    _finish_step("act", note=f"prompts={_PROMPT_SEQ}（每拍 dispatch+character）")
    _preview(_out_dir("act") / "beats.json", 2800)
    print("telemetry:", tel.summary())


def step_script() -> None:
    _prepare_step("script")
    _save_ctx_note(
        "script",
        "000_note.txt",
        "本步无 LLM。输入：08_setup/out/scene_script.json + 09_act/out/beats.json\n"
        "确定性：铸 beat id、拼 ChapterScript、consistency_status=flagged。\n",
    )
    plan = _load_out("plan", "plan.json", ChapterPlan)
    scene_script = _load_out("setup", "scene_script.json", SceneScript)
    beats_raw = _load_out_json("act", "beats.json")
    beats_by_scene = {
        s["scene_id"]: [Beat.model_validate(b) for b in s["beats"]] for s in beats_raw
    }
    scenes: list[Scene] = []
    for contract in scene_script.scenes:
        scenes.append(_to_scene(contract, beats_by_scene.get(contract.scene_id, [])))
    script = ChapterScript(
        chapter=mint_chapter(CHAPTER),
        volume=plan.derived_from.l2_vol_id if plan.derived_from else "v1",
        theme=plan.theme,
        tone=plan.tone,
        covered_threads=[t.thread_id for t in plan.thread_advances],
        consistency_status="flagged",
        derived_from=plan.chapter,
        scenes=scenes,
    )
    Applier().assign_beat_ids(script)
    sp = STORES_DIR / "script.jsonl"
    if sp.exists():
        sp.unlink()
    script_store, _ = _script_ms_stores()
    script_store.append(script)
    _save_out("script", "script.json", script)
    _finish_step("script")
    print(f"落库 {script.chapter} status={script.consistency_status}")
    _preview(_out_dir("script") / "script.json", 2800)


def step_write() -> None:
    _prepare_step("write")
    ctx, tel = _ctx()
    script = _load_out("script", "script.json", ChapterScript)
    print("调用 Writer.render …")
    ms = Writer().render(ctx, chapter=CHAPTER, script=script)
    mp = STORES_DIR / "manuscript.jsonl"
    if mp.exists():
        mp.unlink()
    _, ms_store = _script_ms_stores()
    ms_store.append(ms)
    _save_out("write", "manuscript.json", ms)
    _finish_step("write")
    print("── 散文 ──")
    print(ms.text)
    print("telemetry:", tel.summary())


def step_extract() -> None:
    _prepare_step("extract")
    ctx, tel = _ctx()
    script = _load_out("script", "script.json", ChapterScript)
    mem, _ = _mem_arc_stores()
    print("调用 Extractor.extract …")
    out = Extractor().extract(
        ctx, chapter=CHAPTER, script=script,
        related_memories=_brief_memories(mem, CHAPTER),
    )
    _save_out("extract", "candidates.json", out)
    _finish_step("extract")
    print(f"mem_ops={len(out.mem_ops)} arc_ops={len(out.arc_ops)}")
    _preview(_out_dir("extract") / "candidates.json", 2800)
    print("telemetry:", tel.summary())


def step_faithful() -> None:
    _prepare_step("faithful")
    ctx, tel = _ctx()
    candidates = _load_out("extract", "candidates.json", RecorderOutput)
    script_store, _ = _script_ms_stores()
    print("调用 FaithfulnessCheck.verify …")
    res = FaithfulnessCheck().verify(
        ctx, chapter=CHAPTER, candidates=candidates, script_store=script_store
    )
    _save_out("faithful", "verified.json", res.passed)
    _save_out("faithful", "rejected.json", res.rejected)
    _finish_step("faithful")
    print(f"通过 mem={len(res.passed.mem_ops)}  拒={res.reject_count}")
    if res.rejected:
        for r in res.rejected:
            print(f"  拒: {r}")
    _preview(_out_dir("faithful") / "verified.json", 2000)
    print("telemetry:", tel.summary())


def step_reconcile() -> None:
    _prepare_step("reconcile")
    ctx, tel = _ctx()
    verified = _load_out("faithful", "verified.json", RecorderOutput)
    mem, arc = _mem_arc_stores()
    print("调用 Reconciler.reconcile + Applier …")
    res = Reconciler().reconcile(
        ctx, chapter=CHAPTER, candidates=verified,
        related=_related_memories(mem, CHAPTER),
        arcs=arc.all(),
    )
    apply_result = Applier().apply_recorder_output(res.output, mem, arc)
    _save_out("reconcile", "reconciled.json", res.output)
    _save_out("reconcile", "coerced.json", res.coerced)
    _save_out(
        "reconcile",
        "apply_result.json",
        {
            "added_mem": apply_result.added_mem,
            "reinforced_mem": apply_result.reinforced_mem,
            "invalidated_mem": apply_result.invalidated_mem,
            "arc_transitions": apply_result.arc_transitions,
            "noops": apply_result.noops,
        },
    )
    _finish_step("reconcile")
    print(f"coerced={res.coerced}")
    print(f"apply: +{apply_result.added_mem} reinforce={apply_result.reinforced_mem}")
    _preview(_out_dir("reconcile") / "reconciled.json", 2400)
    print("telemetry:", tel.summary())
    print("第 1 章走查完成。")


HANDLERS = {
    "g0": step_g0,
    "g1": step_g1,
    "g2": step_g2,
    "g3": step_g3,
    "g4": step_g4,
    "g5": step_g5,
    "plan": step_plan,
    "setup": step_setup,
    "act": step_act,
    "script": step_script,
    "write": step_write,
    "extract": step_extract,
    "faithful": step_faithful,
    "reconcile": step_reconcile,
}


# ── CLI ─────────────────────────────────────────────────────────


def cmd_status() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    _write_readme()
    print(f"工作目录：{ROOT.resolve()}")
    print("每步 = context/（LLM 输入）+ out/（产物）")
    print()
    for i, (sid, folder, desc) in enumerate(STEPS, 1):
        mark = "✓" if _done(sid) else "·"
        print(f"  {mark} {i:2d}. {sid:<10} {folder:<12} {desc}")
    print()
    pending = [s for s, _, _ in STEPS if not _done(s)]
    if pending:
        print(f"下一步：uv run python scripts/walk.py run {pending[0]}")
        print(f"审视上下文：uv run python scripts/walk.py show {pending[0]}.context")
        print(f"         或直接打开 steps/{STEP_META[pending[0]][0]}/context/")
    else:
        print("创世/分步走查：全部完成。")
    last_cp = _latest_checkpoint()
    last_script = _latest_script_chapter()
    print()
    cp_label = f"c{last_cp}" if last_cp else "无"
    sc_label = f"c{last_script}" if last_script else "无"
    print(f"章进度：stores 最大章={sc_label}  检查点={cp_label}")
    print("接续：  uv run python scripts/walk.py continue --chapters 10")
    if last_cp:
        print(f"回滚：  uv run python scripts/walk.py rollback --to {last_cp}")
    elif last_script:
        print(
            f"无检查点；可先 seal：uv run python scripts/walk.py checkpoint --seal {last_script}"
        )


def cmd_run(step: str) -> None:
    if step not in HANDLERS:
        raise SystemExit(f"未知步骤 {step!r}")
    names = [s for s, _, _ in STEPS]
    idx = names.index(step)
    missing = [s for s in names[:idx] if not _done(s)]
    if missing:
        print(f"⚠ 前置未完成：{missing}（仍继续）")
    print(f"══ 跑 {step}：{STEP_META[step][1]} ══")
    print(f"目录：{_step_dir(step)}")
    HANDLERS[step]()
    print()
    print(f"看上下文：steps/{STEP_META[step][0]}/context/")
    print(f"看产物：  steps/{STEP_META[step][0]}/out/")


def cmd_show(name: str) -> None:
    """show g1 | show g1.context | show g1.out | show plan.context"""
    part = "all"
    step = name
    if "." in name:
        step, part = name.split(".", 1)
    if step not in STEP_META:
        raise SystemExit(f"未知步骤 {step!r}。可选：{', '.join(STEP_META)}")
    base = _step_dir(step)
    if not base.exists():
        raise SystemExit(f"尚未跑过：{base}")
    targets: list[Path] = []
    if part in ("all", "context"):
        targets.extend(sorted(_ctx_dir(step).glob("*")))
    if part in ("all", "out"):
        targets.extend(sorted(_out_dir(step).glob("*")))
    if part not in ("all", "context", "out"):
        raise SystemExit("用法：show <step> | show <step>.context | show <step>.out")
    if not targets:
        print("(空)")
        return
    for p in targets:
        if p.is_file():
            _preview(p, 6000)
            print()


def cmd_reset() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
        print(f"已清空 {ROOT}")
    else:
        print("没什么可清的。")
    ROOT.mkdir(parents=True, exist_ok=True)
    _write_readme()


def _ensure_genesis(*, do_genesis: bool) -> None:
    missing = [s for s in GENESIS_STEPS if not _done(s)]
    if not missing:
        return
    if not do_genesis:
        raise SystemExit(
            f"创世未齐：缺 {missing}。先跑完 g0–g5，或加 --genesis 自动补跑。"
        )
    print(f"创世未齐，自动补跑：{missing}")
    for sid in missing:
        cmd_run(sid)


def _reseed_stores_from_g5() -> None:
    """章批跑前：清 Script/正文，Mem/Arc 重置为 G5 创世态（避免旧章污染）。"""
    STORES_DIR.mkdir(parents=True, exist_ok=True)
    for name in _STORE_FILES:
        p = STORES_DIR / name
        if p.exists():
            p.unlink()
    mem, arc = _mem_arc_stores()
    for profile in _load_out_list("g5", "profiles.json", MemoryEntry):
        mem.append(profile)
    for a in _load_out_list("g5", "arcs.json", ArcRecord):
        arc.append(a)
    print("stores 已重置为 G5（清 Script/正文，重种 profiles+arcs）")


def _chapter_dump_dir(n: int) -> Path:
    d = CHAPTERS_DIR / mint_chapter(n)
    d.mkdir(parents=True, exist_ok=True)
    (d / "context").mkdir(exist_ok=True)
    (d / "out").mkdir(exist_ok=True)
    return d


def _has_complete_chapter_dump(n: int) -> bool:
    """章产物齐全：out/script.json 在才算完整（防半章脏状态被 auto-seal）。"""
    return (CHAPTERS_DIR / mint_chapter(n) / "out" / "script.json").is_file()


def _recovery_hint(*, failed_chapter: int) -> str:
    last_cp = _latest_checkpoint()
    if last_cp is not None:
        return (
            f"恢复：uv run python scripts/walk.py rollback --to {last_cp}\n"
            f"然后：uv run python scripts/walk.py continue --from {last_cp + 1} "
            f"--chapters …"
        )
    return (
        f"无检查点可回。stores 可能已半写入 c{failed_chapter}。\n"
        f"干净重来：uv run python scripts/walk.py rollback --to 0\n"
        f"或：uv run python scripts/walk.py auto --chapters …"
    )


# ── 检查点 / 回滚 / 接续 ───────────────────────────────────────


def _checkpoint_dir(n: int) -> Path:
    return CHECKPOINTS_DIR / mint_chapter(n)


def _latest_checkpoint() -> int | None:
    if not CHECKPOINTS_DIR.exists():
        return None
    nums = []
    for d in CHECKPOINTS_DIR.iterdir():
        if d.is_dir() and d.name.startswith("c") and (d / "meta.json").exists():
            try:
                nums.append(int(d.name[1:]))
            except ValueError:
                continue
    return max(nums) if nums else None


def _latest_script_chapter() -> int | None:
    path = STORES_DIR / "script.jsonl"
    if not path.exists():
        return None
    nums = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ch = json.loads(line).get("chapter") or ""
        if isinstance(ch, str) and ch.startswith("c"):
            try:
                nums.append(int(ch[1:]))
            except ValueError:
                continue
    return max(nums) if nums else None


def _save_checkpoint(n: int, *, consistency_status: str | None = None) -> Path:
    """把当前 stores 整份拷到 checkpoints/c{n}/（章末过闸后调用）。"""
    dest = _checkpoint_dir(n)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    STORES_DIR.mkdir(parents=True, exist_ok=True)
    for name in _STORE_FILES:
        src = STORES_DIR / name
        if src.exists():
            shutil.copy2(src, dest / name)
        else:
            (dest / name).write_text("", encoding="utf-8")
    meta = {
        "chapter": n,
        "consistency_status": consistency_status,
        "files": [f for f in _STORE_FILES if (dest / f).stat().st_size > 0],
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ↳ checkpoint c{n}/")
    return dest


def _restore_checkpoint(n: int) -> None:
    src = _checkpoint_dir(n)
    if not (src / "meta.json").exists():
        raise SystemExit(
            f"没有检查点 checkpoints/c{n}/。\n"
            f"若 stores 已停在 c{n} 末，可：uv run python scripts/walk.py checkpoint --seal {n}\n"
            f"或重跑 auto 让章末自动打点。"
        )
    STORES_DIR.mkdir(parents=True, exist_ok=True)
    for name in _STORE_FILES:
        dst = STORES_DIR / name
        piece = src / name
        if piece.exists() and piece.stat().st_size > 0:
            shutil.copy2(piece, dst)
        elif dst.exists():
            dst.unlink()
    print(f"stores 已恢复为 checkpoint c{n}")


def _purge_chapters_after(n: int) -> list[str]:
    """删掉 chapters/c{n+1}… 与 checkpoints/c{n+1}…。n=0 时全清。"""
    removed: list[str] = []
    for base in (CHAPTERS_DIR, CHECKPOINTS_DIR):
        if not base.exists():
            continue
        for d in list(base.iterdir()):
            if not d.is_dir() or not d.name.startswith("c"):
                continue
            try:
                num = int(d.name[1:])
            except ValueError:
                continue
            if num > n:
                shutil.rmtree(d)
                removed.append(str(d.relative_to(ROOT)))
    return removed


def _seal_checkpoint_from_stores(n: int) -> Path:
    """把当前 stores 封成 c{n} 检查点（迁移旧跑、手动对齐用）。"""
    last = _latest_script_chapter()
    if last != n:
        raise SystemExit(
            f"拒绝 seal c{n}：stores 最大章是 c{last or 0}，须恰好为 c{n}"
        )
    return _save_checkpoint(n, consistency_status="sealed")


def cmd_checkpoint(*, seal: int | None) -> None:
    if seal is None:
        last = _latest_checkpoint()
        print(f"最近检查点：c{last or 0}（目录 {CHECKPOINTS_DIR}）")
        print("封存当前 stores：uv run python scripts/walk.py checkpoint --seal N")
        return
    if seal < 1:
        raise SystemExit("--seal 须 ≥ 1")
    _seal_checkpoint_from_stores(seal)
    print(f"已 seal checkpoint c{seal}")


def cmd_rollback(*, to: int, keep_dumps: bool) -> None:
    """回到第 to 章末。to=0 → 重种 G5，清全部章与检查点。"""
    if to < 0:
        raise SystemExit("--to 须 ≥ 0")
    _ensure_genesis(do_genesis=False)
    if to == 0:
        _reseed_stores_from_g5()
        removed = _purge_chapters_after(0)
        print("已回滚到 G5（无章）")
        if removed:
            print("已删：", ", ".join(removed))
        return
    _restore_checkpoint(to)
    if not keep_dumps:
        removed = _purge_chapters_after(to)
        if removed:
            print("已删：", ", ".join(removed))
    print(f"世界停在 c{to} 末。下一步可：continue --from {to + 1}")


def cmd_continue(
    *,
    chapters: int,
    no_writer: bool,
    from_chapter: int | None,
    no_critic: bool = False,
) -> None:
    """接续重跑。--from K 隐含 rollback 到 K-1 再跑 K…chapters。"""
    if chapters < 1:
        raise SystemExit("--chapters 至少为 1")
    _ensure_genesis(do_genesis=False)

    if from_chapter is not None:
        if from_chapter < 1:
            raise SystemExit("--from 须 ≥ 1")
        start = from_chapter
        # 隐含：先回到上一章末（from=1 → G5）
        cmd_rollback(to=start - 1, keep_dumps=False)
    else:
        last = _latest_script_chapter() or 0
        start = last + 1
        if start > 1 and not (_checkpoint_dir(start - 1) / "meta.json").exists():
            # stores 已在 start-1 末且无检查点 → 仅完整章可 auto-seal
            if last == start - 1:
                if not _has_complete_chapter_dump(last):
                    raise SystemExit(
                        f"stores 有 c{last} 但 chapters/c{last}/out/script.json 缺失"
                        f"（半章脏状态），拒绝 auto-seal。\n"
                        + _recovery_hint(failed_chapter=last)
                    )
                print(f"无 checkpoint c{last}，自动 seal 当前 stores …")
                _seal_checkpoint_from_stores(last)
            else:
                raise SystemExit(
                    f"接续需要 checkpoint c{start - 1}（stores 最大章=c{last}）。\n"
                    f"可：rollback --to N 或 checkpoint --seal {last}"
                )
        if start > chapters:
            print(f"已到 c{last}，--chapters {chapters} 无需再跑。")
            return

    if start > chapters:
        raise SystemExit(f"--from {start} 已超过 --chapters {chapters}")

    print(
        f"接续：从 c{start} 跑到 c{chapters}"
        f"（不重种 stores；critic={'off' if no_critic else 'on'}）"
    )
    _run_chapter_range(
        start=start, chapters=chapters, no_writer=no_writer, no_critic=no_critic
    )


def cmd_auto(
    *, chapters: int, no_writer: bool, genesis: bool, no_critic: bool = False
) -> None:
    """干净连跑 1…N：重种 G5 后开跑；产物在 chapters/c{n}/，章末写 checkpoint。"""
    if chapters < 1:
        raise SystemExit("--chapters 至少为 1")
    _ensure_genesis(do_genesis=genesis)
    _reseed_stores_from_g5()
    _purge_chapters_after(0)
    _run_chapter_range(
        start=1, chapters=chapters, no_writer=no_writer, no_critic=no_critic
    )


def _run_chapter_range(
    *, start: int, chapters: int, no_writer: bool, no_critic: bool = False
) -> None:
    """跑 start…chapters（含）。假定 stores 已就位。异常/挂起不跳章，退出非 0。"""
    global _PROMPT_CTX_DIR, _PROMPT_SEQ, _ACTIVE_STEP

    l0 = _load_out("g1", "l0.json", L0)
    l1 = _load_out("g1", "l1.json", L1)
    l2 = _load_out("g4", "l2.json", L2)
    world = _load_out_list("g2", "world.json", WorldEntity)

    script_store, ms_store = _script_ms_stores()
    mem_store, arc_store = _mem_arc_stores()
    from story_engine.schemas.stores.violation import Violation

    vio_path = STORES_DIR / "violation.jsonl"
    vio_store: JsonStore[Violation] = JsonStore(Violation, vio_path, key_field="id")
    stores = {
        "script": script_store,
        "mem": mem_store,
        "arc": arc_store,
        "manuscript": ms_store,
        "violation": vio_store,
    }

    aborted = False
    for n in range(start, chapters + 1):
        dump = _chapter_dump_dir(n)
        ctx_dir = dump / "context"
        if ctx_dir.exists():
            shutil.rmtree(ctx_dir)
        ctx_dir.mkdir(parents=True, exist_ok=True)
        out = dump / "out"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)
        _PROMPT_CTX_DIR = ctx_dir
        _PROMPT_SEQ = 0
        _ACTIVE_STEP = None

        ctx, tel = _ctx()
        print(
            f"\n══ 第 {n}/{chapters} 章"
            f"（skip_writer={no_writer}, critic={'off' if no_critic else 'on'}）══"
        )
        try:
            result = run_chapter(
                ctx,
                n,
                l0=l0,
                l1=l1,
                l2=l2,
                world=world,
                stores=stores,
                skip_writer=no_writer,
                enable_critic=not no_critic,
            )
        except Exception as exc:
            tb = traceback.format_exc()
            _dump_json(
                out / "error.json",
                {
                    "chapter": n,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": tb,
                },
            )
            print(f"✗ c{n} 未预期异常——不写 checkpoint，中止后续章")
            print(tb)
            print(_recovery_hint(failed_chapter=n))
            _PROMPT_CTX_DIR = None
            raise SystemExit(1) from exc

        _dump_model(out / "plan.json", result.plan)
        _dump_model(out / "scene_script.json", result.scene_script)
        _dump_model(out / "script.json", result.script)
        if result.manuscript is not None:
            _dump_model(out / "manuscript.json", result.manuscript)
        _dump_json(out / "rejected.json", result.rejected)
        _dump_json(out / "coerced.json", result.coerced)
        _dump_json(out / "trace.json", result.trace)
        _dump_json(
            out / "violations.json",
            [v.model_dump(mode="json", exclude_none=True) for v in result.violations],
        )
        if result.blocked:
            print(f"⚠ {result.chapter} 挂起（未入库）——不写 checkpoint，中止后续章")
            print("trace:", " | ".join(result.trace))
            print("telemetry:", tel.summary())
            print(_recovery_hint(failed_chapter=n))
            aborted = True
            break
        print(f"consistency_status={result.consistency_status}")
        _save_checkpoint(n, consistency_status=result.consistency_status)
        print("trace:", " | ".join(result.trace))
        print("telemetry:", tel.summary())
        print(f"产物：{dump}/out/")

    _PROMPT_CTX_DIR = None
    print(f"\n完成。章节目录：{CHAPTERS_DIR.resolve()}")
    print(f"检查点：{CHECKPOINTS_DIR.resolve()}")
    print("共享库：", STORES_DIR.resolve())
    if aborted:
        raise SystemExit(1)


def _dump_model(path: Path, obj: BaseModel | None) -> None:
    if obj is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    print(f"  ↳ {path.relative_to(ROOT)}")


def _dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ↳ {path.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Story Engine 分步走查（context+out）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="看进度")
    p_run = sub.add_parser("run", help="跑一步")
    p_run.add_argument("step", choices=list(HANDLERS))
    p_show = sub.add_parser("show", help="回看某步 context/out")
    p_show.add_argument("name", help="g1 | g1.context | g1.out | plan.context …")
    p_auto = sub.add_parser("auto", help="干净重跑 1…N（重种 stores；默认跳过 Writer）")
    p_auto.add_argument("--chapters", type=int, default=3, help="章数（默认 3）")
    p_auto.add_argument(
        "--with-writer",
        action="store_true",
        help="渲染散文（默认跳过 Writer）",
    )
    p_auto.add_argument(
        "--genesis",
        action="store_true",
        help="创世未齐时自动补跑 g0–g5",
    )
    p_auto.add_argument(
        "--no-critic",
        action="store_true",
        help="场收束只跑硬检，跳过 Continuity Critic（走查加速）",
    )
    p_roll = sub.add_parser("rollback", help="回到第 N 章末（--to 0 = G5）")
    p_roll.add_argument("--to", type=int, required=True, help="目标章号；0=G5")
    p_roll.add_argument(
        "--keep-dumps",
        action="store_true",
        help="只还原 stores，不删 chapters/checkpoints",
    )
    p_cont = sub.add_parser("continue", help="接续重跑（不重种；--from K 先回滚到 K-1）")
    p_cont.add_argument("--chapters", type=int, required=True, help="跑到第几章（含）")
    p_cont.add_argument(
        "--from",
        dest="from_chapter",
        type=int,
        default=None,
        help="从第 K 章重来（隐含 rollback --to K-1）",
    )
    p_cont.add_argument(
        "--with-writer",
        action="store_true",
        help="渲染散文（默认跳过 Writer）",
    )
    p_cont.add_argument(
        "--no-critic",
        action="store_true",
        help="场收束只跑硬检，跳过 Continuity Critic（走查加速）",
    )
    p_cp = sub.add_parser("checkpoint", help="查看/封存检查点")
    p_cp.add_argument(
        "--seal",
        type=int,
        default=None,
        help="把当前 stores 封成 cN（须恰好停在第 N 章末）",
    )
    sub.add_parser("reset", help="清空 data/walk")

    args = parser.parse_args(argv)
    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "run":
        cmd_run(args.step)
    elif args.cmd == "show":
        cmd_show(args.name)
    elif args.cmd == "auto":
        cmd_auto(
            chapters=args.chapters,
            no_writer=not args.with_writer,
            genesis=args.genesis,
            no_critic=args.no_critic,
        )
    elif args.cmd == "rollback":
        cmd_rollback(to=args.to, keep_dumps=args.keep_dumps)
    elif args.cmd == "continue":
        cmd_continue(
            chapters=args.chapters,
            no_writer=not args.with_writer,
            from_chapter=args.from_chapter,
            no_critic=args.no_critic,
        )
    elif args.cmd == "checkpoint":
        cmd_checkpoint(seal=args.seal)
    elif args.cmd == "reset":
        cmd_reset()


if __name__ == "__main__":
    main()
