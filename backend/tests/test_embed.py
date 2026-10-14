"""Moved from proto with its module (old ids kept in the names). Check id: A06.1."""
import numpy as np

from app.rag.embed import HashEmbedder


def test_a06_1_r2_same_text_same_vector():
    e = HashEmbedder()
    a = e.embed(["open-weight models are here"])
    b = HashEmbedder().embed(["open-weight models are here"])
    assert np.array_equal(a, b)


def test_a06_1_r2_vectors_are_unit_length():
    v = HashEmbedder().embed(["chips and memory bandwidth", "agents in production"])
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0)


def test_a06_1_r2_shared_words_give_higher_cosine():
    v = HashEmbedder().embed(["open-weight model release", "open-weight model licence", "data centre energy"])
    assert v[0] @ v[1] > v[0] @ v[2]


def test_a06_1_r2_empty_text_is_zero_vector_not_nan():
    v = HashEmbedder().embed(["the a of"])
    assert not np.isnan(v).any()
