"""LLMClient + MockProvider：结构化输出 + 成本记账。"""

from pydantic import BaseModel

from story_engine.llm.base import LLMClient
from story_engine.llm.mock import MockProvider
from story_engine.telemetry.runrecord import Telemetry


class Answer(BaseModel):
    verdict: str
    score: int


def test_structured_output_and_accounting():
    provider = MockProvider(default_json='{"verdict": "PASS", "score": 7}')
    tel = Telemetry()
    client = LLMClient(provider, telemetry=tel)

    ans = client.complete_structured("judge this", Answer, node="critic", chapter=3)
    assert ans.verdict == "PASS" and ans.score == 7

    recs = tel.all()
    assert len(recs) == 1
    assert recs[0].node == "critic"
    assert recs[0].chapter == 3
    assert recs[0].total_tokens > 0
    assert recs[0].cost_usd > 0
    assert recs[0].verdict == "PASS"


def test_parse_failure_retries_then_raises():
    provider = MockProvider(default_json="not json")
    tel = Telemetry()
    client = LLMClient(provider, telemetry=tel, max_retries=1)

    import pytest

    with pytest.raises(ValueError):
        client.complete_structured("bad", Answer, node="critic")
    # 1 次初试 + 1 次重试 = 2 条 PARSE_FAIL 留痕
    assert len(tel.all()) == 2


def test_telemetry_summary():
    provider = MockProvider(default_json='{"verdict": "PASS", "score": 1}')
    tel = Telemetry()
    client = LLMClient(provider, telemetry=tel)
    client.complete_structured("x", Answer, node="n1")
    client.complete_structured("y", Answer, node="n2")
    assert tel.verdict_counts().get("PASS") == 2
    assert tel.total_cost() > 0
