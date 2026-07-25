"""Token 计数 —— 借 tiktoken 精确计数，装不上时回退启发式。

Retriever 预算 / Chunker 都用它。抽象成一个函数，便于未来换 tokenizer。
"""

from __future__ import annotations

from functools import lru_cache

try:
    import tiktoken

    _HAS_TIKTOKEN = True
except Exception:  # pragma: no cover - 环境无 tiktoken 时回退
    _HAS_TIKTOKEN = False


@lru_cache(maxsize=1)
def _encoder():  # pragma: no cover - 依赖外部库
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """估算文本 token 数。tiktoken 优先，否则按字符粗估（中文≈1字1token）。"""
    if not text:
        return 0
    if _HAS_TIKTOKEN:
        try:
            return len(_encoder().encode(text))
        except Exception:  # pragma: no cover
            pass
    # 回退：ASCII 词按 ~4 字符/token，非 ASCII（中文等）按 1 字符/token
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    non_ascii = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii)
