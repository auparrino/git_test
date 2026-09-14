"""Test de aceptacion 1 (SPEC_v0.1.md secc. 11): `run(7) == run(7)`."""

from __future__ import annotations

from republica.engine.simulation import run


def test_same_seed_produces_identical_history() -> None:
    h1 = run(seed=7, months=48)
    h2 = run(seed=7, months=48)
    assert h1.to_jsonl() == h2.to_jsonl()


def test_different_seeds_diverge() -> None:
    h1 = run(seed=1, months=12)
    h2 = run(seed=2, months=12)
    assert h1.to_jsonl() != h2.to_jsonl()
