"""Trazas de decision de actores IA (ADR 004 secc. 6).

Cada llamada a un `LLMBackend` produce un `DecisionTrace`. Se serializa como
una linea JSONL (`kind: "trace"`) intercalada en el mismo archivo que
`MonthRecord`/`ActionRecord` (ADR 003 secc. 8), por
`engine/simulation.py::History.to_jsonl`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


def make_run_id(seed: int, config_hash: str) -> str:
    """`run_id = sha256(seed + config_hash)[:12]` (ADR 004 secc. 6/deliverable 5)."""
    return hashlib.sha256(f"{seed}{config_hash}".encode()).hexdigest()[:12]


@dataclass
class DecisionTrace:
    """Una linea `kind: "trace"` (ADR 004 secc. 6).

    `actions_authorized`/`actions_denied`/`consequences` no los conoce
    `LLMActor.decide()` (se resuelven recien en `authorize_all`/
    `apply_consequences`, despues de que el actor ya decidio): quedan en
    blanco al construir la traza y los completa `engine/scheduler.py`
    (mismo patron que `RuleBasedActor.last_score`, ver ADR 003 secc. 11
    punto 27). `run_id` tambien lo completa el scheduler (lo conoce el
    `ActorEngine`, no el actor individual)."""

    run_id: str
    month: int
    actor_id: str
    brain: str
    prompt_version: str
    model: str
    digest: str
    temperature: float
    seed: int
    perception: dict[str, Any]
    system: str
    user: str
    raw_response: str
    parsed: dict[str, Any] | None
    parse_error: str | None
    attempts: int
    actions_emitted: list[dict[str, Any]]
    latency_ms: float
    tokens: dict[str, int]
    actions_authorized: list[dict[str, Any]] = field(default_factory=list)
    actions_denied: list[dict[str, Any]] = field(default_factory=list)
    consequences: dict[str, Any] = field(default_factory=dict)
    #: Reservado para Fase 7 (Langfuse), vacio en v0.4 (ADR 004 secc. 6).
    eval_score: float | None = None
    #: Cuantas frases de `MEMORIAS RELEVANTES` traia el prompt de este actor
    #: (ADR 006 deliverable 3): `len(perception.memories)`, 0 sin memoria.
    memories_retrieved: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "trace",
            "run_id": self.run_id,
            "month": self.month,
            "actor_id": self.actor_id,
            "brain": self.brain,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "digest": self.digest,
            "temperature": self.temperature,
            "seed": self.seed,
            "perception": self.perception,
            "system": self.system,
            "user": self.user,
            "raw_response": self.raw_response,
            "parsed": self.parsed,
            "parse_error": self.parse_error,
            "attempts": self.attempts,
            "actions_emitted": self.actions_emitted,
            "actions_authorized": self.actions_authorized,
            "actions_denied": self.actions_denied,
            "consequences": self.consequences,
            "latency_ms": self.latency_ms,
            "tokens": self.tokens,
            "eval_score": self.eval_score,
            "memories_retrieved": self.memories_retrieved,
        }
