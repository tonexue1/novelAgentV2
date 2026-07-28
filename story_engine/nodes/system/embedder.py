"""Embedder —— 对应 docs/nodes/system/embedder.md。

文本 → 定长 L2 归一向量。协议可插拔：FakeEmbedder（UT 确定性）/
OpenAIEmbedder（STORY_* env OpenAI 兼容 /embeddings）。
按 hash(text) 缓存，同文本不重复调用。
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class CachingEmbedder:
    """按 hash(text) 缓存的装饰器。"""

    def __init__(self, inner: Embedder) -> None:
        self._inner = inner
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float] | None] = [None] * len(texts)
        missing: list[str] = []
        missing_idx: list[int] = []
        for i, t in enumerate(texts):
            key = hashlib.sha256((t or "").encode("utf-8")).hexdigest()
            if key in self._cache:
                out[i] = self._cache[key]
            else:
                missing.append(t or "")
                missing_idx.append(i)
        if missing:
            vectors = self._inner.embed(missing)
            for i, vec in zip(missing_idx, vectors):
                key = hashlib.sha256((texts[i] or "").encode("utf-8")).hexdigest()
                self._cache[key] = vec
                out[i] = vec
        return [v if v is not None else [] for v in out]


class FakeEmbedder:
    """确定性假 embedding：字符 n-gram 哈希到固定维 + L2 归一。无网络。"""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_l2_normalize(self._one(t)) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        t = text or ""
        # unigram + bigram hashes
        for i, ch in enumerate(t):
            h = int(hashlib.md5(ch.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 1.0
            if i + 1 < len(t):
                bg = (ch + t[i + 1]).encode("utf-8")
                h2 = int(hashlib.md5(bg).hexdigest(), 16)
                vec[h2 % self.dim] += 0.5
        if all(v == 0 for v in vec):
            vec[0] = 1.0
        return vec


class OpenAIEmbedder:
    """OpenAI 兼容 /embeddings（DeepSeek 等）。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "text-embedding-3-small",
    ) -> None:
        if not api_key:
            raise ValueError("OpenAIEmbedder 需要 api_key（STORY_OPENAI_API_KEY）")
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self.model, input=texts)
        # 按 index 排序保证对齐
        data = sorted(resp.data, key=lambda d: d.index)
        return [_l2_normalize(list(d.embedding)) for d in data]


def build_embedder(settings=None) -> Embedder:
    from story_engine.config import load_settings

    s = settings or load_settings()
    provider = getattr(s, "embedder_provider", "fake") or "fake"
    if provider == "fake":
        inner: Embedder = FakeEmbedder(dim=getattr(s, "embedder_dim", 64) or 64)
    elif provider == "openai":
        inner = OpenAIEmbedder(
            api_key=s.openai_api_key or "",
            base_url=s.openai_base_url,
            model=getattr(s, "embedder_model", None) or "text-embedding-3-small",
        )
    else:
        raise ValueError(f"未知 embedder_provider: {provider}")
    return CachingEmbedder(inner)
