"""Trazas de decision de actores IA (ADR 004 secc. 6).

Cada llamada a un `LLMBackend` produce un `DecisionTrace`. Se serializa como
una linea JSONL (`kind: "trace"`) intercalada en el mismo archivo que
`MonthRecord`/`ActionRecord` (ADR 003 secc. 8), por
`engine/simulation.py::History.to_jsonl`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def make_run_id(seed: int, config_hash: str) -> str:
    """`run_id = sha256(seed + config_hash)[:12]` (ADR 004 secc. 6/deliverable 5)."""
    return hashlib.sha256(f"{seed}{config_hash}".encode()).hexdigest()[:12]


#: Los 8 spans de una decision (ADR 007 secc. 5, literal, orden fijo): un
#: `DecisionTrace` (ADR 004 secc. 6) es la traza completa de UNA decision de
#: actor; sus pasos internos son los spans. `eval_score` es el unico span
#: que puede llegar vacio (lo completa `republica eval`, ver
#: `DecisionTrace.eval_score`, reservado desde ADR 004).
SPAN_NAMES: tuple[str, ...] = (
    "perception",
    "memory_retrieval",
    "prompt",
    "llm_call",
    "parse",
    "authorize",
    "consequences",
    "eval_score",
)


@dataclass
class Span:
    """Una linea `kind: "span"` (ADR 007 secc. 5): `trace_id, span, parent,
    input, output, metadata, start, end` (esquema literal del exportador de
    trazas). `start`/`end` son un contador sintetico (0..7, indice del span
    en `SPAN_NAMES`) en vez de timestamps reales: `DecisionTrace` solo
    guarda `latency_ms` TOTAL de la llamada (ADR 004 secc. 6), no un
    desglose por paso -- medir tiempo real por span exigiria instrumentar
    `LLMActor`/`ai/backends.py` con relojes intermedios, fuera de alcance
    de Fase 7 (documentado en Notas de implementacion de ADR 007). El
    orden relativo (`start < end`, y los `parent` que encadenan los 8
    pasos) es lo que `traces show` necesita para dibujar el arbol."""

    trace_id: str
    span: str
    parent: str | None
    input: Any
    output: Any
    metadata: dict[str, Any]
    start: float
    end: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "span",
            "trace_id": self.trace_id,
            "span": self.span,
            "parent": self.parent,
            "input": self.input,
            "output": self.output,
            "metadata": self.metadata,
            "start": self.start,
            "end": self.end,
        }


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

    @property
    def trace_id(self) -> str:
        """Identificador estable de ESTA decision (ADR 007 secc. 5): un
        actor con un `LLMActor` decide una sola vez por mes
        (`engine/scheduler.py::run_actor_turn`), asi que `(run_id, month,
        actor_id)` la identifica sin ambiguedad. No es `digest` (eso
        identifica la RESPUESTA cruda del backend, no la decision: dos
        actores distintos podrian, en teoria, recibir la misma respuesta de
        un `FakeBackend` scripted y compartir `digest`)."""
        return f"{self.run_id}:{self.month:03d}:{self.actor_id}"

    def to_spans(self) -> list[Span]:
        """Los 8 spans de esta decision (ADR 007 secc. 5), encadenados en
        `SPAN_NAMES`. `authorize`/`consequences` estan vacios si esta
        traza se completo antes de `engine/scheduler.py::run_actor_turn`
        (ver ADR 004 secc. 11 puntos 13-14: el actor solo conoce
        `actions_emitted` al decidir)."""
        tid = self.trace_id
        inputs: dict[str, Any] = {
            "perception": self.perception,
            "memory_retrieval": {"actor_id": self.actor_id, "month": self.month},
            "prompt": {"system": self.system},
            "llm_call": {
                "system": self.system,
                "user": self.user,
                "model": self.model,
                "temperature": self.temperature,
                "seed": self.seed,
            },
            "parse": self.raw_response,
            "authorize": self.actions_emitted,
            "consequences": self.actions_authorized,
            "eval_score": None,
        }
        outputs: dict[str, Any] = {
            "perception": None,
            "memory_retrieval": {
                "memories": self.perception.get("memories", []),
                "memory_score": self.perception.get("memory_score"),
                "memories_retrieved": self.memories_retrieved,
            },
            "prompt": {"user": self.user},
            "llm_call": {
                "raw_response": self.raw_response,
                "digest": self.digest,
                "attempts": self.attempts,
                "latency_ms": self.latency_ms,
                "tokens": self.tokens,
            },
            "parse": {"parsed": self.parsed, "parse_error": self.parse_error},
            "authorize": {
                "actions_authorized": self.actions_authorized,
                "actions_denied": self.actions_denied,
            },
            "consequences": self.consequences,
            "eval_score": self.eval_score,
        }
        spans: list[Span] = []
        parent: str | None = None
        for i, name in enumerate(SPAN_NAMES):
            spans.append(
                Span(
                    trace_id=tid,
                    span=name,
                    parent=parent,
                    input=inputs[name],
                    output=outputs[name],
                    metadata={"actor_id": self.actor_id, "month": self.month, "brain": self.brain},
                    start=float(i),
                    end=float(i + 1),
                )
            )
            parent = name
        return spans

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


def spans_from_trace_dict(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """`DecisionTrace.to_spans()` sobre un `dict` ya leido de un JSONL
    (`kind: "trace"`, mismo esquema que `DecisionTrace.to_dict()`) en vez de
    una instancia -- lo usa `republica traces export/show` (ADR 007 secc.
    5), que lee trazas de un archivo ajeno, no las construye."""
    run_id = trace.get("run_id", "")
    month = int(trace.get("month", 0))
    actor_id = trace.get("actor_id", "")
    tid = f"{run_id}:{month:03d}:{actor_id}"
    perception = trace.get("perception") or {}
    inputs: dict[str, Any] = {
        "perception": perception,
        "memory_retrieval": {"actor_id": actor_id, "month": month},
        "prompt": {"system": trace.get("system", "")},
        "llm_call": {
            "system": trace.get("system", ""),
            "user": trace.get("user", ""),
            "model": trace.get("model", ""),
            "temperature": trace.get("temperature"),
            "seed": trace.get("seed"),
        },
        "parse": trace.get("raw_response", ""),
        "authorize": trace.get("actions_emitted", []),
        "consequences": trace.get("actions_authorized", []),
        "eval_score": None,
    }
    outputs: dict[str, Any] = {
        "perception": None,
        "memory_retrieval": {
            "memories": perception.get("memories", []),
            "memory_score": perception.get("memory_score"),
            "memories_retrieved": trace.get("memories_retrieved", 0),
        },
        "prompt": {"user": trace.get("user", "")},
        "llm_call": {
            "raw_response": trace.get("raw_response", ""),
            "digest": trace.get("digest", ""),
            "attempts": trace.get("attempts", 0),
            "latency_ms": trace.get("latency_ms", 0.0),
            "tokens": trace.get("tokens", {}),
        },
        "parse": {"parsed": trace.get("parsed"), "parse_error": trace.get("parse_error")},
        "authorize": {
            "actions_authorized": trace.get("actions_authorized", []),
            "actions_denied": trace.get("actions_denied", []),
        },
        "consequences": trace.get("consequences", {}),
        "eval_score": trace.get("eval_score"),
    }
    spans: list[dict[str, Any]] = []
    parent: str | None = None
    for i, name in enumerate(SPAN_NAMES):
        spans.append(
            {
                "kind": "span",
                "trace_id": tid,
                "span": name,
                "parent": parent,
                "input": inputs[name],
                "output": outputs[name],
                "metadata": {"actor_id": actor_id, "month": month, "brain": trace.get("brain", "")},
                "start": float(i),
                "end": float(i + 1),
            }
        )
        parent = name
    return spans


def read_traces_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Lineas `kind: "trace"` de un JSONL de `republica run` (ADR 007 secc.
    5: entrada de `republica traces export/show`)."""
    out: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") == "trace":
            out.append(row)
    return out


def export_traces_jsonl(traces: list[dict[str, Any]], out_path: str | Path) -> int:
    """Exporta los spans de `traces` (ADR 007 secc. 5, deliverable 4) a
    `out_path` como JSONL, una linea por span. Devuelve la cantidad de
    spans escritos. Es el fallback SIN Langfuse (ADR 007 secc. 5, literal:
    "sin el, exporta a traces.jsonl con el mismo esquema")."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for trace in traces:
        for span in spans_from_trace_dict(trace):
            lines.append(json.dumps(span, ensure_ascii=False))
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


def try_export_langfuse(traces: list[dict[str, Any]]) -> bool:
    """`True` si el SDK de Langfuse esta instalado y se pudieron enviar los
    spans de `traces` (ADR 007 secc. 5: "usa el SDK de Langfuse SOLO SI
    ESTA INSTALADO"). `False` si el import falla -- el llamador
    (`cli.py::traces_export`) cae a `export_traces_jsonl` en ese caso, sin
    excepcion: no hay Langfuse en este entorno (offline), asi que esta rama
    nunca corre en los tests, solo la firma/el fallback importan aca."""
    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except ImportError:
        return False
    client = Langfuse()
    for trace in traces:
        for span in spans_from_trace_dict(trace):
            client.span(
                id=f"{span['trace_id']}:{span['span']}",
                trace_id=span["trace_id"],
                parent_observation_id=(
                    f"{span['trace_id']}:{span['parent']}" if span["parent"] else None
                ),
                name=span["span"],
                input=span["input"],
                output=span["output"],
                metadata=span["metadata"],
            )
    flush = getattr(client, "flush", None)
    if callable(flush):
        flush()
    return True


def write_eval_scores(path: str | Path, scores: dict[str, float]) -> int:
    """Escribe `eval_score` en las trazas de `path` (JSONL de `republica
    run`) cuyo `trace_id` (`run_id:month:actor_id`, ver `DecisionTrace.
    trace_id`) esta en `scores` (ADR 007 secc. 5, literal: "`eval` escribe
    `eval_score` en la traza correspondiente, por `trace_id`"). Reescribe el
    archivo entero (mismas lineas, en el mismo orden, solo cambia
    `eval_score` en las que matchean) y devuelve cuantas trazas actualizo."""
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines()
    updated = 0
    out_lines: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") == "trace":
            run_id = row.get("run_id", "")
            month = int(row.get("month", 0))
            actor_id = row.get("actor_id", "")
            tid = f"{run_id}:{month:03d}:{actor_id}"
            if tid in scores:
                row["eval_score"] = scores[tid]
                updated += 1
        out_lines.append(json.dumps(row, ensure_ascii=False))
    p.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return updated


def render_trace_tree(spans: list[dict[str, Any]]) -> str:
    """Arbol de texto de UNA traza (ADR 007 secc. 7 punto 6: "`traces show`
    imprime el arbol de una decision"), en el orden de `SPAN_NAMES`."""
    if not spans:
        return "(sin spans para esta traza)"
    by_name = {s["span"]: s for s in spans}
    lines = [f"trace_id={spans[0]['trace_id']}"]
    depth = 0
    for name in SPAN_NAMES:
        span = by_name.get(name)
        if span is None:
            continue
        indent = "  " * depth
        lines.append(f"{indent}└─ {name} [{span['start']:.0f}-{span['end']:.0f}]")
        depth += 1
    return "\n".join(lines)
