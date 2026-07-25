import pytest

from story_engine.primitives.evidence import EvidenceSpan


@pytest.mark.parametrize(
    "s",
    ["c12", "c12.s3", "c12.s3.b5", "c12.s3.b5-8"],
)
def test_roundtrip(s):
    span = EvidenceSpan.parse(s)
    assert span.to_str() == s


def test_parse_fields():
    span = EvidenceSpan.parse("c12.s3.b5-8")
    assert span.chapter == 12
    assert span.scene == 3
    assert span.beats == (5, 8)


def test_single_beat_roundtrip():
    span = EvidenceSpan.parse("c1.s1.b1")
    assert span.beats == (1, 1)
    assert span.to_str() == "c1.s1.b1"


def test_illegal_strings_rejected():
    for bad in ["", "x12", "c12.s", "c12..b5", "c12.s3.b8-5"]:
        with pytest.raises(ValueError):
            EvidenceSpan.parse(bad)


def test_beats_without_scene_rejected():
    with pytest.raises(ValueError):
        EvidenceSpan(chapter=1, scene=None, beats=(1, 2))
