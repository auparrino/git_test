"""Test de aceptacion 1 (SPEC_v0.1.md secc. 11): `run(7) == run(7)`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from republica.engine.simulation import run


def test_same_seed_produces_identical_history() -> None:
    h1 = run(seed=7, months=48)
    h2 = run(seed=7, months=48)
    assert h1.to_jsonl() == h2.to_jsonl()


def test_different_seeds_diverge() -> None:
    h1 = run(seed=1, months=12)
    h2 = run(seed=2, months=12)
    assert h1.to_jsonl() != h2.to_jsonl()


# REVIEW_001 hallazgo #7: determinismo con actores, entre PYTHONHASHSEED ----

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SUBPROCESS_SCRIPT = (
    "from republica.engine.simulation import run\n"
    "h = run(seed=7, months=12, actors_enabled=True)\n"
    "print(h.to_jsonl(), end='')\n"
)


def test_actors_enabled_determinism_across_python_hash_seeds() -> None:
    """El test de determinismo original (arriba) corre con `actors_enabled`
    apagado (default de `run()`): nunca se aserto que la corrida CON actores
    sea reproducible entre procesos con distinto `PYTHONHASHSEED` (ADR 003
    secc. 7 usa `zlib.crc32`, no el `hash()` builtin, justamente para no
    depender de el -- `make_actor_rng`/`actor_seed`, `actors/rule_based.py`).
    Se corre en 2 subprocesos separados con `PYTHONHASHSEED` distinto (no
    alcanza con setear la variable en este proceso: ya arranco)."""
    outputs = []
    for hash_seed in ("0", "1337"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        result = subprocess.run(
            [sys.executable, "-c", _SUBPROCESS_SCRIPT],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(_REPO_ROOT),
            env=env,
            timeout=60,
        )
        outputs.append(result.stdout)

    assert outputs[0], "la corrida no produjo salida"
    assert outputs[0] == outputs[1]
