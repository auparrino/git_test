"""Prompts del juez (ADR 007 secc. 3): un `.md` por tarea (`fact_check.md`/
`rubric_score.md`, el system prompt) mas el render del `user` prompt de cada
metrica con juez. Solo los usa `Judge` (un `LLMBackend` real): `FakeJudge`
no arma prompts, decide por reglas de strings/numeros directamente sobre los
datos (`evals/judge.py`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent

FACT_CHECK_SYSTEM = (_DIR / "fact_check.md").read_text(encoding="utf-8")
RUBRIC_SCORE_SYSTEM = (_DIR / "rubric_score.md").read_text(encoding="utf-8")

REALISM_RUBRIC_PATH = (
    Path(__file__).resolve().parents[4] / "data" / "evals" / "rubrics" / "realism.md"
)


def render_fact_check_prompt(perception_numbers: list[float], text: str) -> tuple[str, str]:
    """`(system, user)` para `hallucination`/verificacion de hechos (ADR
    secc. 3)."""
    user = f"PERCEPCION (numeros validos): {json.dumps(perception_numbers)}\n\nTEXTO:\n{text}"
    return FACT_CHECK_SYSTEM, user


def render_realism_prompt(
    emergence: dict[str, Any], negotiations: list[dict[str, Any]]
) -> tuple[str, str]:
    """`(system, user)` para `political_realism` (ADR secc. 2/3): el
    `system` incluye la rubrica completa de `data/evals/rubrics/realism.md`."""
    rubric = REALISM_RUBRIC_PATH.read_text(encoding="utf-8") if REALISM_RUBRIC_PATH.exists() else ""
    system = f"{RUBRIC_SCORE_SYSTEM}\n\n---\n{rubric}"
    user = (
        f"EMERGENCE REPORT:\n{json.dumps(emergence, ensure_ascii=False, indent=2)}\n\n"
        f"NEGOCIACIONES (hasta 10):\n{json.dumps(negotiations, ensure_ascii=False, indent=2)}"
    )
    return system, user
