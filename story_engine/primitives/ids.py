"""ID 体系 —— 对应 docs/schema/primitives/ids.md。

三类 id：
  ① 位置 ID：寻址进 ScriptStore，层级、提交后不可变（c{n} / c{n}.s{m} / c{n}.s{m}.b{k}）。
  ② 实体 ID：跨全书持久命名实体（{type}.{slug}）。
  ③ 不透明 ID：系统生成（m.{ulid} / vio.{ulid}）。

统一纪律：id 不可变、显示名可变；生产者先于消费者铸造。
本模块提供正则校验 + 铸造 helper。
"""

from __future__ import annotations

import re

from ulid import ULID

# ── 正则（校验用）──────────────────────────────────────────────
CHAPTER_RE = re.compile(r"^c\d+$")
SCENE_RE = re.compile(r"^c\d+\.s\d+$")
BEAT_RE = re.compile(r"^c\d+\.s\d+\.b\d+$")
VOLUME_RE = re.compile(r"^v\d+$")
SAGA_RE = re.compile(r"^sg\d+$")

_ENTITY_PREFIXES = ("char", "th", "fs", "sec", "concept", "art", "loc", "org", "item", "race")
ENTITY_RE = re.compile(rf"^({'|'.join(_ENTITY_PREFIXES)})\.[a-z0-9_]+$")

MEMORY_RE = re.compile(r"^m\.[0-9A-HJKMNP-TV-Z]{26}$")
VIOLATION_RE = re.compile(r"^vio\.[0-9A-HJKMNP-TV-Z]{26}$")


# ── ULID（不透明 id 用，python-ulid：时间有序、26 位 Crockford base32）──
def new_ulid() -> str:
    return str(ULID())


# ── 铸造 helper ────────────────────────────────────────────────
def mint_saga(k: int) -> str:
    return f"sg{k}"


def mint_volume(n: int) -> str:
    return f"v{n}"


def mint_chapter(n: int) -> str:
    """章 id，同时是 as-of 主时钟。"""
    return f"c{n}"


def mint_scene(chapter: str, m: int) -> str:
    if not CHAPTER_RE.match(chapter):
        raise ValueError(f"非法章 id: {chapter!r}")
    return f"{chapter}.s{m}"


def mint_beat(scene: str, k: int) -> str:
    if not SCENE_RE.match(scene):
        raise ValueError(f"非法场 id: {scene!r}")
    return f"{scene}.b{k}"


def mint_entity(kind: str, slug: str) -> str:
    if kind not in _ENTITY_PREFIXES:
        raise ValueError(f"未知实体前缀: {kind!r}（合法: {_ENTITY_PREFIXES}）")
    if not re.match(r"^[a-z0-9_]+$", slug):
        raise ValueError(f"非法 slug: {slug!r}（只允许小写字母/数字/下划线）")
    return f"{kind}.{slug}"


def mint_memory_id() -> str:
    return f"m.{new_ulid()}"


def mint_violation_id() -> str:
    return f"vio.{new_ulid()}"


# ── 校验 helper ────────────────────────────────────────────────
def is_chapter(s: str) -> bool:
    return bool(CHAPTER_RE.match(s))


def is_scene(s: str) -> bool:
    return bool(SCENE_RE.match(s))


def is_beat(s: str) -> bool:
    return bool(BEAT_RE.match(s))


def is_entity(s: str) -> bool:
    return bool(ENTITY_RE.match(s))


def chapter_num(chapter: str) -> int:
    """从章 id 取整数（as-of 比较用）。"""
    if not CHAPTER_RE.match(chapter):
        raise ValueError(f"非法章 id: {chapter!r}")
    return int(chapter[1:])
