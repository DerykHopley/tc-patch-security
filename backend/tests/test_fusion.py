"""Moved from proto with its module (old ids kept in the names). Check id: A06.1."""
import pytest

from app.rag.fusion import rrf


def test_a06_1_qt2_score_formula():
    fused = dict(rrf([["x", "y"]]))
    assert fused["x"] == pytest.approx(1 / 61)
    assert fused["y"] == pytest.approx(1 / 62)


def test_a06_1_qt2_chunk_in_many_lists_beats_single_first_place():
    lists = [["solo", "multi"], ["other", "multi"], ["another", "multi"]]
    ranked = [cid for cid, _ in rrf(lists)]
    assert ranked[0] == "multi"


def test_a06_1_qt2_ties_keep_first_seen_order():
    ranked = [cid for cid, _ in rrf([["a"], ["b"]])]
    assert ranked == ["a", "b"]


def test_a06_1_qt2_empty_lists():
    assert rrf([[], []]) == []
