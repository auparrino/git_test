"""Memoria de actores (ADR 006 secc. 1): `MemoryEvent`, `MemoryStore` por
actor (in-memory + JSONL `kind: "memory"`), reglas de generacion (tabla de
la secc. 1.1), recuperacion (secc. 1.2) y consolidacion (secc. 1.4).

Gateado por `features.memory` (default `True`, solo con `features.actors`
tambien activo): con `features.memory = False` este modulo no se llama desde
`engine/simulation.py` y el comportamiento es identico al de antes de ADR
006 (ver `docs/ADR_006_memory_elections.md`, Notas de implementacion).

Diseno: en vez de esparcir un `store.add(...)` en cada lugar del motor que
genera un evento de la tabla de la secc. 1.1 (Congreso, negociacion,
consequences, shocks...), `generate_month_memories()` es un unico punto de
entrada que `engine/simulation.py::advance_month` llama una vez por mes, ya
con los `ActionRecord`/eventos de acuerdo/`VoteRecord`/shocks de ese mes a
mano (todos ya calculados por los subsistemas de ADR 003/005). Cubre las 11
filas de la tabla igual, con menos superficie de cambio en el resto del
motor y sin duplicar logica de "quien es la contraparte" que esos modulos
ya resuelven."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from republica.actors.sheet import ActorSheet
    from republica.engine.scheduler import ActionRecord
    from republica.world.config import Party
    from republica.world.events import ShockAggregate

#: Media vida de la recencia (ADR 006 secc. 1.2, literal: `exp(-(turn_now -
#: turn)/12)`), reusada tambien por el termino de memoria de secc. 1.3 y por
#: `trust_president`.
RECENCY_HALF_LIFE = 12.0

#: `k` de la recuperacion (secc. 1.2, literal).
RETRIEVAL_K = 5
#: Presupuesto de caracteres (secc. 1.2, literal: "400" tokens -- se
#: aproxima 1 token ~ 1 caracter recortado, documentado en Notas de
#: implementacion: no hay tokenizer en el proyecto).
CHAR_BUDGET = 400

#: Cada 12 turnos se consolida (secc. 1.4, literal).
CONSOLIDATION_EVERY = 12
#: Importancia bajo la cual una memoria es candidata a resumirse (secc. 1.4).
CONSOLIDATION_IMPORTANCE_MAX = 0.5
#: Ninguna memoria con `importance >= 0.8` se resume nunca (secc. 1.4, literal).
NEVER_SUMMARIZE_IMPORTANCE = 0.8


class MemoryEvent(BaseModel):
    """`MemoryEvent` (ADR 006 secc. 1.1, literal). `actor` es el DUEÑO de la
    memoria (quien la recuerda), no quien la protagonizo -- ver la tabla:
    "actores que lo reciben"."""

    model_config = ConfigDict(extra="forbid")

    turn: int
    actor: str
    about: str | None = None
    kind: str
    summary: str
    importance: float = Field(ge=0.0, le=1.0)
    sentiment: float = Field(ge=-1.0, le=1.0)

    def to_dict(self) -> dict[str, Any]:
        """Linea JSONL `kind: "memory"`. El `kind` propio del evento (p.ej.
        `"agreement_honored"`) viaja como `event_kind`, para no chocar con el
        `"kind": "memory"` del sidecar (mismo patron que `vote`/`negotiation`)."""
        return {
            "kind": "memory",
            "month": self.turn,
            "owner": self.actor,
            "about": self.about,
            "event_kind": self.kind,
            "summary": self.summary,
            "importance": round(self.importance, 3),
            "sentiment": round(self.sentiment, 3),
        }


#: `(importance, sentiment)` por defecto de cada `kind` (tabla de secc.
#: 1.1). `promise_broken` no esta en la tabla de memoria (esta en secc. 2.5)
#: pero comparte el mismo mecanismo de `MemoryEvent`.
MEMORY_DEFAULTS: dict[str, tuple[float, float]] = {
    "agreement_honored": (0.6, 0.6),
    "agreement_broken_by_government": (0.9, -0.8),
    "agreement_broken_by_actor": (0.8, -0.7),
    "concession_received": (0.5, 0.5),
    "request_refused": (0.5, -0.4),
    "voted_for": (0.5, 0.4),
    "voted_against": (0.5, -0.4),
    "strike_called": (0.6, -0.5),
    "protest_called": (0.6, -0.5),
    "criticized_by": (0.4, -0.4),
    "endorsed_by": (0.4, 0.4),
    "shock_hit": (0.7, -0.5),
    "forced_devaluation": (0.8, -0.6),
    "promised": (0.6, 0.0),
    "promise_broken": (0.8, -0.7),
    "summary": (0.3, 0.0),
}


def recency(now_turn: int, turn: int) -> float:
    """`exp(-(turn_now - turn)/12)` (secc. 1.2, literal)."""
    return math.exp(-max(0, now_turn - turn) / RECENCY_HALF_LIFE)


@dataclass
class MemoryStore:
    """Todas las memorias de la corrida, agrupadas por dueño (secc. 1.2:
    "`MemoryStore` por actor"). Un unico `dict` en vez de 29 instancias
    separadas: mas simple de pasar por el motor y de serializar completo al
    JSONL (`all_events`), sin cambiar la semantica (`for_owner` es la vista
    "por actor" que pide el ADR)."""

    events_by_owner: dict[str, list[MemoryEvent]] = field(default_factory=dict)

    def add(self, event: MemoryEvent) -> None:
        self.events_by_owner.setdefault(event.actor, []).append(event)

    def for_owner(self, owner: str) -> list[MemoryEvent]:
        return self.events_by_owner.get(owner, [])

    def all_events(self) -> list[MemoryEvent]:
        return [e for events in self.events_by_owner.values() for e in events]

    def relabel_about(self, old_about: str, new_about: str) -> int:
        """Re-etiqueta `about == old_about -> new_about` en TODAS las
        memorias de TODOS los dueños (ADR 006 secc. 2.4: transicion de
        gobierno, `about=president -> about=former_president_<party>`).
        Devuelve cuantas se re-etiquetaron."""
        count = 0
        for owner, events in self.events_by_owner.items():
            updated = []
            for e in events:
                if e.about == old_about:
                    updated.append(e.model_copy(update={"about": new_about}))
                    count += 1
                else:
                    updated.append(e)
            self.events_by_owner[owner] = updated
        return count

    def retrieve(
        self,
        owner: str,
        now_turn: int,
        *,
        relevant_actors: set[str] | None = None,
        situation_kind: str | None = None,
        k: int = RETRIEVAL_K,
        char_budget: int = CHAR_BUDGET,
    ) -> list[str]:
        """Recuperacion (ADR 006 secc. 1.2): `score = 0.5*importance +
        0.3*recency + 0.2*relevance`, top `k`, devueltas como frases
        ordenadas por turno, recortadas al presupuesto de caracteres."""
        scored: list[tuple[float, MemoryEvent]] = []
        for e in self.for_owner(owner):
            rec = recency(now_turn, e.turn)
            if relevant_actors and e.about in relevant_actors:
                relevance = 1.0
            elif situation_kind is not None and e.kind == situation_kind:
                relevance = 0.5
            else:
                relevance = 0.0
            score = 0.5 * e.importance + 0.3 * rec + 0.2 * relevance
            scored.append((score, e))
        scored.sort(key=lambda t: t[0], reverse=True)
        top = [e for _, e in scored[:k]]
        top.sort(key=lambda e: e.turn)

        phrases: list[str] = []
        budget = char_budget
        for e in top:
            if budget <= 0:
                break
            phrase = e.summary
            if len(phrase) > budget:
                phrase = phrase[: max(0, budget - 1)].rstrip() + "…"
            phrases.append(phrase)
            budget -= len(phrase)
        return phrases

    def memory_term(self, owner: str, now_turn: int, about: str = "president") -> float:
        """`Σ sentiment_i · importance_i · recency_i` sobre memorias con
        `about == about` (ADR 006 secc. 1.3, base de `w_mem` y de
        `trust_president`)."""
        total = 0.0
        for e in self.for_owner(owner):
            if e.about != about:
                continue
            total += e.sentiment * e.importance * recency(now_turn, e.turn)
        return total

    def trust_president(
        self, owner: str, now_turn: int, base: float = 50.0, scale: float = 30.0
    ) -> float:
        """`trust_president = 50 + 30*tanh(Σ...)` (ADR 006 secc. 1.3).
        Reemplaza el decaimiento hacia 50 de `Relationships` (ADR 003 secc.
        5) SOLO en la vista de percepcion del actor sobre el presidente, no
        en el valor guardado de `Relationships` (ver docstring de
        `engine/perception.py::build_perception` y Notas de implementacion
        de ADR 006: las dos cosas se mantienen consistentes a proposito,
        `Relationships` sigue siendo el unico store persistente)."""
        return base + scale * math.tanh(self.memory_term(owner, now_turn, "president"))

    def consolidate(self, now_turn: int, window: int = CONSOLIDATION_EVERY) -> list[MemoryEvent]:
        """Consolidacion (ADR 006 secc. 1.4): por dueño y por `about`, junta
        las memorias con `importance < 0.5` y `turn < now - 12` en una sola
        `MemoryEvent(kind="summary")` (por reglas: conteo de signos ->
        frase plantilla). Nunca toca memorias `kind == "summary"` ya
        existentes (quedan como un resumen acumulado permanente, ver
        docstring de la clase) ni `importance >= 0.8` (filtradas por el
        propio umbral `< 0.5`)."""
        created: list[MemoryEvent] = []
        for owner, events in list(self.events_by_owner.items()):
            candidates: dict[str | None, list[MemoryEvent]] = {}
            keep: list[MemoryEvent] = []
            for e in events:
                eligible = (
                    e.kind != "summary"
                    and e.importance < CONSOLIDATION_IMPORTANCE_MAX
                    and (now_turn - e.turn) >= window
                )
                if eligible:
                    candidates.setdefault(e.about, []).append(e)
                else:
                    keep.append(e)
            for about, evs in candidates.items():
                pos = sum(1 for e in evs if e.sentiment > 0.05)
                neg = sum(1 for e in evs if e.sentiment < -0.05)
                neu = len(evs) - pos - neg
                avg_sentiment = sum(e.sentiment for e in evs) / len(evs)
                avg_importance = min(0.5, sum(e.importance for e in evs) / len(evs))
                who = about or "distintos actores"
                summary_event = MemoryEvent(
                    turn=now_turn,
                    actor=owner,
                    about=about,
                    kind="summary",
                    summary=(
                        f"Resumen de {len(evs)} interacciones menores con {who}: "
                        f"{pos} positivas, {neg} negativas, {neu} neutras."
                    ),
                    importance=avg_importance,
                    sentiment=avg_sentiment,
                )
                keep.append(summary_event)
                created.append(summary_event)
            self.events_by_owner[owner] = keep
        return created


# ---------------------------------------------------------------------------
# Generacion (ADR 006 secc. 1.1)
# ---------------------------------------------------------------------------

#: Verbos/expresiones de compromiso en espanol (ADR 006 secc. 1.1: "de
#: `public_message` con verbo de compromiso"). Lista chica e inventada
#: (documentada en Notas de implementacion), suficiente para detectar una
#: promesa explicita sin falsos positivos obvios.
COMMITMENT_VERBS: tuple[str, ...] = (
    "prometo",
    "prometemos",
    "me comprometo",
    "nos comprometemos",
    "garantizo",
    "garantizamos",
    "aseguro",
    "aseguramos",
    "juro",
    "juramos",
    "voy a bajar",
    "vamos a bajar",
    "voy a subir",
    "vamos a subir",
    "no voy a permitir",
    "no vamos a permitir",
)

_COMMITMENT_RE = re.compile("|".join(re.escape(v) for v in COMMITMENT_VERBS), re.IGNORECASE)


def extract_promise(text: str) -> bool:
    """`True` si `text` contiene un verbo de compromiso (ADR 006 secc. 1.1)."""
    return bool(text) and _COMMITMENT_RE.search(text) is not None


@dataclass
class MemoryContext:
    """Todo lo que `generate_month_memories` necesita de este mes, ya
    calculado por `engine/simulation.py::advance_month` (ver docstring del
    modulo: un unico punto de entrada en vez de hooks esparcidos)."""

    month: int
    actors: dict[str, ActorSheet]
    parties: list[Party]
    action_records: list[ActionRecord]
    agreement_events: list[str]
    refused_actor_ids: set[str]
    vote_party_results: dict[str, bool]  # party_id -> aprobo (True) / no (False)
    shock_agg: ShockAggregate
    new_shock_ids: list[str]
    forced_devaluation: bool
    cohort_ids: list[str] = field(default_factory=list)


def _add(
    events: list[MemoryEvent],
    month: int,
    owner: str,
    about: str | None,
    kind: str,
    summary: str,
) -> None:
    importance, sentiment = MEMORY_DEFAULTS[kind]
    events.append(
        MemoryEvent(
            turn=month,
            actor=owner,
            about=about,
            kind=kind,
            summary=summary,
            importance=importance,
            sentiment=sentiment,
        )
    )


def generate_month_memories(ctx: MemoryContext) -> list[MemoryEvent]:
    """Genera los `MemoryEvent` de este mes (tabla de ADR 006 secc. 1.1)."""
    events: list[MemoryEvent] = []
    m = ctx.month
    actors = ctx.actors

    allied_party_ids = [
        f"party_{p.id}" for p in ctx.parties if p.is_ally and f"party_{p.id}" in actors
    ]

    # -- Acuerdos (de las strings de `engine/negotiation.py`) --------------
    for s in ctx.agreement_events:
        parts = s.split(":")
        if parts[0] == "agreement_honored" and len(parts) == 3:
            _, actor_id, concession = parts
            _add(
                events,
                m,
                actor_id,
                "president",
                "agreement_honored",
                f"El gobierno cumplio el acuerdo de {concession} con {actor_id}.",
            )
        elif parts[0] == "agreement_broken" and len(parts) == 4:
            _, actor_id, concession, who = parts
            if who == "government":
                _add(
                    events,
                    m,
                    actor_id,
                    "president",
                    "agreement_broken_by_government",
                    f"El gobierno no cumplio el acuerdo de {concession} con {actor_id}.",
                )
                for ally_id in allied_party_ids:
                    _add(
                        events,
                        m,
                        ally_id,
                        "president",
                        "agreement_broken_by_government",
                        f"El gobierno rompio su acuerdo con {actor_id} ({concession}).",
                    )
            else:
                if "president" in actors:
                    _add(
                        events,
                        m,
                        "president",
                        actor_id,
                        "agreement_broken_by_actor",
                        f"{actor_id} rompio su acuerdo pese a haber recibido {concession}.",
                    )
                if "minister_economy" in actors:
                    _add(
                        events,
                        m,
                        "minister_economy",
                        actor_id,
                        "agreement_broken_by_actor",
                        f"{actor_id} rompio su acuerdo de {concession}.",
                    )

    # -- Concesion recibida / pedido rechazado ------------------------------
    for rec in ctx.action_records:
        if not rec.authorized:
            continue
        if rec.type == "GRANT_CONCESSION":
            to = rec.params.get("to")
            if to:
                _add(
                    events,
                    m,
                    to,
                    "president",
                    "concession_received",
                    f"El gobierno le otorgo la concesion {rec.params.get('concession')}.",
                )
    for actor_id in ctx.refused_actor_ids:
        _add(
            events,
            m,
            actor_id,
            "president",
            "request_refused",
            "El gobierno rechazo su pedido de fondos.",
        )

    # -- Voto de leyes clave (secc. 1.1: presidente, partido, gobernadores) -
    governors_by_party: dict[str, list[str]] = {}
    for aid, sheet in actors.items():
        if sheet.role == "governor" and sheet.party:
            governors_by_party.setdefault(sheet.party, []).append(aid)
    for party_id, approved in ctx.vote_party_results.items():
        kind = "voted_for" if approved else "voted_against"
        verb = "a favor de" if approved else "en contra de"
        if "president" in actors:
            _add(events, m, "president", party_id, kind, f"{party_id} voto {verb} la ley del mes.")
        party_actor = f"party_{party_id}"
        if party_actor in actors:
            _add(events, m, party_actor, None, kind, f"Mi bloque voto {verb} la ley del mes.")
        for gov_id in governors_by_party.get(party_id, []):
            _add(events, m, gov_id, party_id, kind, f"{party_id} voto {verb} la ley del mes.")

    # -- Huelga / protesta / criticas / endosos / promesas ------------------
    business_ids = [aid for aid, s in actors.items() if s.role == "business"]
    media_ids = [aid for aid, s in actors.items() if s.role == "media"]
    for rec in ctx.action_records:
        if not rec.authorized:
            continue
        if rec.type == "STRIKE":
            for owner in ("president", *business_ids, *media_ids):
                if owner in actors:
                    _add(
                        events,
                        m,
                        owner,
                        rec.actor,
                        "strike_called",
                        f"{rec.actor} convoco una huelga.",
                    )
        elif rec.type == "CALL_PROTEST":
            for owner in ("president", *business_ids, *media_ids):
                if owner in actors:
                    _add(
                        events,
                        m,
                        owner,
                        rec.actor,
                        "protest_called",
                        f"{rec.actor} convoco una protesta.",
                    )
        elif rec.type == "CRITICIZE":
            target = rec.params.get("target") or rec.target
            if target and target in actors:
                _add(
                    events,
                    m,
                    target,
                    rec.actor,
                    "criticized_by",
                    f"{rec.actor} lo/la critico publicamente.",
                )
        elif rec.type == "ENDORSE":
            target = rec.params.get("target") or rec.target
            if target and target in actors:
                _add(
                    events,
                    m,
                    target,
                    rec.actor,
                    "endorsed_by",
                    f"{rec.actor} lo/la respaldo publicamente.",
                )
        elif rec.type == "PUBLIC_STATEMENT" and extract_promise(rec.reason):
            _add(
                events,
                m,
                rec.actor,
                None,
                "promised",
                f'{rec.actor} declaro: "{rec.reason[:140]}"',
            )
        elif rec.type == "PROMISE":
            target = rec.target or rec.params.get("target")
            text = str(rec.params.get("text", ""))[:140]
            _add(events, m, rec.actor, target, "promised", f'{rec.actor} prometio: "{text}"')
            if target:
                _add(events, m, target, rec.actor, "promised", f'{rec.actor} prometio: "{text}"')

    # -- Shock golpeo su provincia/sector/cohorte ---------------------------
    for province_id in ctx.shock_agg.province_id:
        for aid, sheet in actors.items():
            if sheet.role == "governor" and sheet.province == province_id:
                _add(
                    events,
                    m,
                    aid,
                    None,
                    "shock_hit",
                    f"Un shock golpeo a la provincia {province_id}.",
                )
    for sector in ctx.shock_agg.province_sector:
        for aid, sheet in actors.items():
            if sheet.role == "business" and sheet.sector == sector:
                _add(events, m, aid, None, "shock_hit", f"Un shock golpeo al sector {sector}.")
    if ctx.new_shock_ids:
        for cohort_id in ctx.cohort_ids:
            _add(
                events,
                m,
                cohort_id,
                None,
                "shock_hit",
                f"Un shock golpeo a la economia este mes ({', '.join(ctx.new_shock_ids)}).",
            )

    # -- Devaluacion forzada (todos) ----------------------------------------
    if ctx.forced_devaluation:
        for aid in (*actors, *ctx.cohort_ids):
            _add(
                events,
                m,
                aid,
                None,
                "forced_devaluation",
                "El banco central devaluo de forma forzada.",
            )

    return events
