"""StagedScriptView —— 本章工作缓冲（编排内存，未落库）。

一致性闸的纪律是「没过闸不许进 ScriptStore」，但硬检要解析 evidence span、
Critic/Assembler 要读本章已生成的场——两者互锁。这层薄视图解开它：

    get(chapter_id) 先查内存 staged 章，未命中回落真 store。

按鸭子类型满足 ScriptStore 的读协议（get / all），
故 resolve_span 等既有函数签名不动、零侵入。写口子只服务编排：
逐拍暂存 → 拍级重来丢最后一拍 → 场过闸 admit → 章末一次性落库。
"""

from __future__ import annotations

from story_engine.primitives.ids import mint_beat
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene


class StagedScriptView:
    def __init__(self, store, skeleton: ChapterScript) -> None:
        """skeleton：本章章头（scenes 应为空），Planner 之后即可铸。"""
        self._store = store
        self._skeleton = skeleton
        self._scenes: list[Scene] = []
        self._draft: Scene | None = None

    # ── 读（ScriptStore 协议）────────────────────────────────
    @property
    def chapter_id(self) -> str:
        return self._skeleton.chapter

    @property
    def draft_scene(self) -> Scene | None:
        return self._draft

    @property
    def admitted_scenes(self) -> list[Scene]:
        return list(self._scenes)

    def staged_chapter(self, *, include_draft: bool = True) -> ChapterScript:
        scenes = list(self._scenes)
        if include_draft and self._draft is not None:
            scenes.append(self._draft)
        return self._skeleton.model_copy(update={"scenes": scenes}, deep=True)

    def get(self, key: str) -> ChapterScript | None:
        if key == self.chapter_id:
            return self.staged_chapter()
        return self._store.get(key)

    def all(self) -> list[ChapterScript]:
        return [*self._store.all(), self.staged_chapter()]

    def __len__(self) -> int:
        return len(self._store) + 1

    # ── 写（只服务编排）──────────────────────────────────────
    def open_scene(self, scene: Scene) -> Scene:
        """起一场草稿。beats 里已有的拍按顺序铸 id。"""
        self._draft = scene.model_copy(deep=True)
        self._renumber(self._draft)
        return self._draft

    def stage_beat(self, beat: Beat) -> Beat:
        """追一拍进草稿场并铸 beat id（硬检要凭 id 定位）。"""
        if self._draft is None:
            raise RuntimeError("没有草稿场，先 open_scene")
        staged = beat.model_copy(deep=True)
        staged.beat_id = mint_beat(self._draft.scene_id, len(self._draft.beats) + 1)
        self._draft.beats = [*self._draft.beats, staged]
        return staged

    def drop_last_beat(self) -> Beat | None:
        """拍级重来：只撤最后一拍。"""
        if self._draft is None or not self._draft.beats:
            return None
        *rest, last = self._draft.beats
        self._draft.beats = rest
        return last

    def reset_draft_beats(self) -> None:
        """场重导：清空草稿场的拍，保留场头。"""
        if self._draft is not None:
            self._draft.beats = []

    def admit_scene(self) -> Scene:
        """草稿场过闸，拼进 staged 章。"""
        if self._draft is None:
            raise RuntimeError("没有草稿场可入")
        scene = self._draft
        self._scenes.append(scene)
        self._draft = None
        return scene

    def discard_draft(self) -> None:
        self._draft = None

    def commit(self, *, consistency_status: str) -> ChapterScript:
        """章末一次性落库；只有走到这里内容才成为主真相。"""
        if self._draft is not None:
            raise RuntimeError("还有未过闸的草稿场，不许落库")
        script = self.staged_chapter()
        script.consistency_status = consistency_status  # type: ignore[assignment]
        self._store.append(script)
        return script

    # ── 内部 ────────────────────────────────────────────────
    @staticmethod
    def _renumber(scene: Scene) -> None:
        for k, beat in enumerate(scene.beats, start=1):
            beat.beat_id = mint_beat(scene.scene_id, k)
