"""Architect（总纲师）—— 对应 docs/nodes/planning/architect.md。

创世自上而下（ARCHITECTURE §2.6）：
  - G1/G2 `bootstrap`：seed → L0（独占，冻结）+ L1（全书结构，防漂移锚）；
  - G4 `expand_volume`：L1 → L2[卷1]（首卷铺开）；
  - G5 `seed_profiles`：L1.character_arcs → tier0/1 主角 seed 画像（evidence 指 c0=创世）。
两个实现：
  - `Architect`：真 LLM（M2），产出后做确定性 id 规整。
  - `ArchitectStub`：确定性假数据（M0 起），供无 LLM 的创世/Gate UT。
"""

from __future__ import annotations

from pydantic import Field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.primitives.enums import CharTier
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.primitives.ids import mint_entity, mint_memory_id, mint_volume
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.memory import GoalKind, MemoryEntry, MemType
from story_engine.nodes.planning.l2_continuity import (
    L2ContinuityError,
    assert_l2_continuity,
)
from story_engine.schemas.stores.plan import (
    L0,
    L1,
    L2,
    ChapterBeat,
    CharacterArc,
    Foreshadow,
    ForeshadowDue,
    Thread,
    ThreadTarget,
    Volume,
    VolumeSpine,
)

_ROLE = "你是长篇小说的总纲师，负责创世：把作者的种子拔成全书立意与结构骨架。"
_TASK = """据种子产出两样东西：
1. L0 立意（一旦定下即冻结，改 L0 等于换一本书）：核心戏剧问题、结局方向、主角弧线意图。
2. L1 全书结构：卷划分、主线 thread、伏笔总图、以及本书**承重设定的引用清单** world_refs。

硬要求（json 输出）：
- thread_id 形如 th.{slug}，fs_id 形如 fs.{slug}，world_refs 里的项形如 concept.{slug} /
  art.{slug} / loc.{slug} / org.{slug} / item.{slug} / race.{slug}，slug 用小写英文。
- world_refs 只列**撑得起 L1 的承重 canon**（3~6 个），海量细节留给正文时再长出。
- 至少一条 tier=main 的主线 thread；至少一个伏笔。
- 卷 vol_id 形如 v1。
- volumes[].goal 写本卷**戏剧局面变化**（关系/冲突推进到哪），是可检验的局面，
  不是「分别介绍各角色生活背景」式清单。"""


_SPINE_ROLE = "你是长篇小说的首卷脊骨规划师，负责定第一卷的戏剧脊骨（尚不分章）。"
_SPINE_TASK = """据 L0/L1 产出第一卷的卷目标与 volume_spine。**不要**输出 chapter_beats。

硬要求（json 输出）：
- goal：本卷把故事推进到哪（一段话，可执行的局面）。
- thread_targets：本卷要推进的每条主线给一个 target_milestone；thread_id 引用 L1
  里真实存在的 id，原样照抄。
- foreshadow_due：本卷该埋(plant)/该收(fulfill)的伏笔；fs_id 引用 L1 真实存在的 id。
  第一卷通常只埋不收。
- volume_spine：
  - shared_pressure：开卷即存在、多方都会碰到的共享压力/共时空（公司、项目、雨季……）
  - inciting：本卷不可逆发动点
  - midpoint：中段局面质变
  - climax：本卷收束局面（对齐 goal / thread_targets）
- 人物「是什么样的人」不写进 spine（那是画像的事）；只写压力与事件。"""


_BEATS_ROLE = "你是长篇小说的首卷分章规划师，负责把卷脊骨切成章事件链。"
_BEATS_TASK = """在已冻结的卷脊骨下，产出 chapter_beats（8~12 条）。

硬要求（json 输出）：
- 只输出 chapter_beats 数组；每章是事件节点，不是人设说明书。
- 字段：planned_seq（从 1 连号）、event（因果句：因 X 致 Y，留下 Z）、
  leaves_open（本章未闭合钩子，短标签）、inherits（接住前序哪条钩子）、
  touches_spine（pressure|inciting|midpoint|climax|bridge）、
  pov_focus（可选 char_id 列表）。
- 第 1 章 inherits 可空，或只引脊骨标签：spine.shared_pressure / spine.inciting 等。
- 第 2 章起 inherits 非空，且每条必须是更早章的 leaves_open 或脊骨标签。
- 卷内 touches_spine 须覆盖 inciting、midpoint、climax 各至少一次；
  inciting 落在前约 40% 章序内。
- 双人故事用共享压力与钩子接力，不要「整章只介绍 A、下一章只介绍 B」。"""


class L2SpineDraft(SchemaModel):
    """Expand-Spine 载荷：目标 + due + 脊骨，尚无分章。"""

    goal: str | None = None
    thread_targets: list[ThreadTarget] = Field(default_factory=list)
    foreshadow_due: list[ForeshadowDue] = Field(default_factory=list)
    volume_spine: VolumeSpine


class L2BeatsDraft(SchemaModel):
    """Expand-Beats 载荷。"""

    chapter_beats: list[ChapterBeat] = Field(default_factory=list)

_PROFILE_ROLE = "你是人物设计师，负责给主角与核心角色种下**创世画像**。"
_PROFILE_TASK = """为 L1.character_arcs 里的每个角色产出 seed 画像条目。

硬要求（json 输出）：
- 每个角色 3~5 条：至少一条 trait（性格）、一条 goal（长线驱动，goal_kind=long-drive）、
  一条 voice（说话风格，example 给一句典型台词）。
- scope 填该角色的 char.{slug}，原样照抄 L1 里的 id。
- text 写实、可被后文引用；不要剧透伏笔真相。
- 只写角色**开场时**的状态，不写他将来会变成什么。"""


class ArchitectOutput(SchemaModel):
    """一次调用同时出 L0 + L1（两者互相咬合，分开问容易对不上）。"""

    l0: L0
    l1: L1


class ProfileEntry(SchemaModel):
    """seed 画像条目（LLM 载荷）；id/t_valid/tier/evidence 由系统补。"""

    type: MemType
    scope: str                      # char.{slug}
    text: str
    strength: float | None = None
    goal_kind: GoalKind | None = None
    example: str | None = None


class SeedProfiles(SchemaModel):
    entries: list[ProfileEntry] = Field(default_factory=list)


def _slug_fix(value: str, prefix: str) -> str:
    """把 LLM 可能漏前缀的 id 补齐，如 'main_revenge' → 'th.main_revenge'。"""
    return value if "." in value else f"{prefix}.{value}"


class Architect:
    name = "architect"

    def bootstrap(self, ctx: NodeContext, seed) -> tuple[L0, L1]:  # noqa: ANN001 - Seed
        if ctx.llm is None:
            raise ValueError("Architect 需要 LLMClient；无 LLM 场景请用 ArchitectStub")
        prompt = build_prompt(_ROLE, _TASK, [("种子（作者唯一人工输入）", as_json(seed))])
        out = ctx.llm.complete_structured(prompt, ArchitectOutput, node=self.name, chapter=0)
        return out.l0, self._normalize(out.l1)

    def _normalize(self, l1: L1) -> L1:
        """确定性规整 id 前缀与卷号——LLM 常漏前缀，这类事不该靠重试解决。"""
        for t in l1.threads:
            t.thread_id = _slug_fix(t.thread_id, "th")
        for fs in l1.foreshadow_map:
            fs.fs_id = _slug_fix(fs.fs_id, "fs")
        for arc in l1.character_arcs:
            arc.char_id = _slug_fix(arc.char_id, "char")
        if not l1.volumes:
            l1.volumes = [Volume(vol_id=mint_volume(1), title="第一卷")]
        l1.world_refs = [r for r in l1.world_refs if "." in r]
        return l1

    # ── G4：首卷铺开（脊骨 → 分章，连续性硬检）────────────────
    def expand_volume(self, ctx: NodeContext, l0: L0, l1: L1) -> L2:
        if ctx.llm is None:
            raise ValueError("Architect 需要 LLMClient；无 LLM 场景请用 ArchitectStub")
        vol_id = l1.volumes[0].vol_id if l1.volumes else mint_volume(1)
        spine_prompt = build_prompt(
            _SPINE_ROLE,
            _SPINE_TASK,
            [
                ("立意 L0（不可违背）", as_json(l0)),
                ("全书结构 L1", as_json(l1, limit=3000)),
                ("本卷", vol_id),
            ],
        )
        draft = ctx.llm.complete_structured(
            spine_prompt, L2SpineDraft, node=self.name, chapter=0
        )
        l2 = L2(
            vol_id=vol_id,
            goal=draft.goal,
            thread_targets=draft.thread_targets,
            foreshadow_due=draft.foreshadow_due,
            volume_spine=draft.volume_spine,
        )
        l2 = self._normalize_l2(l2, l1, vol_id)

        retries = getattr(ctx.llm, "_max_retries", 2)
        last_err: L2ContinuityError | None = None
        for attempt in range(retries + 1):
            frozen = L2SpineDraft(
                goal=l2.goal,
                thread_targets=l2.thread_targets,
                foreshadow_due=l2.foreshadow_due,
                volume_spine=l2.volume_spine,
            )
            beats_prompt = build_prompt(
                _BEATS_ROLE,
                _BEATS_TASK,
                [
                    ("立意 L0（不可违背）", as_json(l0)),
                    ("本卷目标与脊骨（已冻结）", as_json(frozen)),
                    (
                        "上轮连续性错误（须修好）" if last_err else "提示",
                        str(last_err) if last_err else "首次生成，按任务硬要求输出事件链。",
                    ),
                ],
            )
            beats = ctx.llm.complete_structured(
                beats_prompt, L2BeatsDraft, node=self.name, chapter=0
            )
            l2.chapter_beats = beats.chapter_beats
            l2 = self._normalize_l2(l2, l1, vol_id)
            try:
                assert_l2_continuity(l2)
                return l2
            except L2ContinuityError as e:
                last_err = e
        raise L2ContinuityError(
            f"章事件链连续性校验失败（重试 {retries} 次）: {last_err}"
        )

    def _normalize_l2(self, l2: L2, l1: L1, vol_id: str) -> L2:
        """卷号系统写死；引用只保留 L1 真实存在的 id；planned_seq 重排连号。"""
        l2.vol_id = vol_id
        known_threads = {t.thread_id for t in l1.threads}
        known_fs = {f.fs_id for f in l1.foreshadow_map}
        known_chars = {a.char_id for a in l1.character_arcs}
        for t in l2.thread_targets:
            t.thread_id = _slug_fix(t.thread_id, "th")
        l2.thread_targets = [t for t in l2.thread_targets if t.thread_id in known_threads]
        for f in l2.foreshadow_due:
            f.fs_id = _slug_fix(f.fs_id, "fs")
        l2.foreshadow_due = [f for f in l2.foreshadow_due if f.fs_id in known_fs]
        for i, cb in enumerate(l2.chapter_beats, start=1):
            cb.planned_seq = i
            cb.inherits = [h.strip() for h in cb.inherits if h and h.strip()]
            cb.leaves_open = [h.strip() for h in cb.leaves_open if h and h.strip()]
            cb.pov_focus = [
                _slug_fix(p, "char") for p in cb.pov_focus if p
            ]
            # 只保留 L1 认识的角色；未知 id 丢掉以免污染接力 POV 检
            cb.pov_focus = [p for p in cb.pov_focus if p in known_chars]
        return l2

    # ── G5：tier0/1 seed 画像 ────────────────────────────────
    def seed_profiles(self, ctx: NodeContext, seed, l0: L0, l1: L1) -> list[MemoryEntry]:  # noqa: ANN001 - Seed
        if ctx.llm is None:
            raise ValueError("Architect 需要 LLMClient；无 LLM 场景请用 ArchitectStub")
        if not l1.character_arcs:
            return []
        prompt = build_prompt(
            _PROFILE_ROLE,
            _PROFILE_TASK,
            [
                ("种子（作者意图）", as_json(seed)),
                ("立意 L0", as_json(l0)),
                ("角色弧线（只给这些角色种画像）", as_json(l1.character_arcs)),
            ],
        )
        out = ctx.llm.complete_structured(prompt, SeedProfiles, node=self.name, chapter=0)
        return _to_seed_entries(out.entries, l1)


def _to_seed_entries(entries: list[ProfileEntry], l1: L1) -> list[MemoryEntry]:
    """LLM 载荷 → MemoryEntry：铸 id、t_valid=0、evidence 指 c0（创世）、定 tier。

    只种 L1.character_arcs 收录的角色（tier 0/1，龙套不种）；
    第一条弧线的角色视为主角（T0），其余 T1。
    """
    tiers: dict[str, CharTier] = {
        arc.char_id: (CharTier.T0 if i == 0 else CharTier.T1)
        for i, arc in enumerate(l1.character_arcs)
    }
    out: list[MemoryEntry] = []
    for e in entries:
        scope = _slug_fix(e.scope, "char")
        if scope not in tiers:
            continue
        out.append(
            MemoryEntry(
                id=mint_memory_id(),
                type=e.type,
                scope=scope,
                text=e.text,
                t_valid=0,
                strength=e.strength,
                evidence=[EvidenceSpan(chapter=0)],   # c0 = 创世（种子/L0 出处）
                goal_kind=e.goal_kind,
                example=e.example,
                tier=tiers[scope],
            )
        )
    return out


class ArchitectStub:
    """确定性最小映射：不打 LLM，只为把创世管道跑通（Gate UT 用）。"""

    name = "architect"

    def bootstrap(self, seed) -> tuple[L0, L1]:  # noqa: ANN001 - Seed
        l0 = L0(
            logline=seed.logline,
            genre=list(seed.genre),
            tone=list(seed.tone),
            core_dramatic_question=f"围绕『{seed.logline}』的核心命题",
            ending_intent=seed.ending_intent,
            protagonist_arc_intent=list(seed.protagonist_intent),
        )
        main_thread = Thread(
            thread_id=mint_entity("th", "main"),
            tier="main",
            desc=seed.logline,
        )
        l1 = L1(
            version=1,
            created_at_ch=0,
            volumes=[Volume(vol_id=mint_volume(1), title="第一卷", detail_level="detailed")],
            threads=[main_thread],
            character_arcs=[
                CharacterArc(
                    char_id=mint_entity("char", "protagonist"),
                    from_state="凡人",
                    to_state=seed.ending_intent,
                )
            ],
            foreshadow_map=[
                Foreshadow(fs_id=mint_entity("fs", "origin"), desc="主角身世伏笔")
            ],
            # 点名需要的承重 canon（stub：一个境界体系概念）
            world_refs=[mint_entity("concept", "cultivation")],
        )
        return l0, l1

    def expand_volume(self, l1: L1) -> L2:
        vol_id = l1.volumes[0].vol_id if l1.volumes else mint_volume(1)
        char = l1.character_arcs[0].char_id if l1.character_arcs else "char.protagonist"
        return L2(
            vol_id=vol_id,
            goal="首卷：主角在共享压力下踏上主线，局面不可逆",
            thread_targets=[
                ThreadTarget(thread_id=t.thread_id, target_milestone="迈出第一步")
                for t in l1.threads
            ],
            foreshadow_due=[
                ForeshadowDue(fs_id=f.fs_id, action="plant") for f in l1.foreshadow_map
            ],
            volume_spine=VolumeSpine(
                shared_pressure="宗门考核在即，外来者必须证明自己",
                inciting="主角被迫卷入考核，退路切断",
                midpoint="考核中暴露身世线索，同伴态度分裂",
                climax="获准入门，但代价与秘密同时落下",
            ),
            chapter_beats=[
                ChapterBeat(
                    planned_seq=1,
                    event="主角抵达山门，考核令已下，无法折返",
                    leaves_open=["must_enter_trial"],
                    inherits=["spine.shared_pressure"],
                    touches_spine="pressure",
                    pov_focus=[char],
                ),
                ChapterBeat(
                    planned_seq=2,
                    event="报名考核时被点名质疑身份，退路切断",
                    leaves_open=["identity_questioned"],
                    inherits=["must_enter_trial"],
                    touches_spine="inciting",
                    pov_focus=[char],
                ),
                ChapterBeat(
                    planned_seq=3,
                    event="考核中旧物被认出，同伴态度分裂",
                    leaves_open=["ally_split"],
                    inherits=["identity_questioned"],
                    touches_spine="midpoint",
                    pov_focus=[char],
                ),
                ChapterBeat(
                    planned_seq=4,
                    event="闯过终关获准入门，秘密与代价一并落下",
                    leaves_open=["secret_cost"],
                    inherits=["ally_split"],
                    touches_spine="climax",
                    pov_focus=[char],
                ),
            ],
        )

    def seed_profiles(self, seed, l1: L1) -> list[MemoryEntry]:  # noqa: ANN001 - Seed
        entries = [
            ProfileEntry(type="trait", scope=arc.char_id, text=f"{arc.from_state}，坚韧")
            for arc in l1.character_arcs
        ] + [
            ProfileEntry(
                type="goal",
                scope=arc.char_id,
                text=intent,
                goal_kind="long-drive",
            )
            for arc in l1.character_arcs[:1]
            for intent in seed.protagonist_intent
        ]
        return _to_seed_entries(entries, l1)
