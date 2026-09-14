"""Consecuencias de acciones autorizadas (ADR 003 secc. 5).

Las acciones producen deltas que entran como terminos `shock_*` del mes
siguiente (misma via que shocks y dilemas: `Simulation.pending_terms`, ver
`world/events.py`) mas cambios de relaciones. Los terminos con prefijo
`policy_` son un caso especial (`GRANT_CONCESSION`/`SET_RATE`): no son un
`shock_*` de una formula del motor sino un ajuste directo al instrumento de
`Policy` homonimo, que `engine/scheduler.py` aplica al mes siguiente (ver
Notas de implementacion de ADR 003: los instrumentos de `Policy` no tienen un
mecanismo `shock_*` propio, a diferencia de las 20 variables de `WorldState`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from republica.actors.sheet import ActorSheet
from republica.engine.actions import Action, ActionType
from republica.world.config import Party
from republica.world.state import Policy, WorldState, clamp

DEFAULT_CONSEQUENCES_PATH = Path(__file__).resolve().parents[3] / "data" / "consequences.yaml"
DEFAULT_CONCESSIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "concessions.yaml"

#: Campo de `WorldState` -> termino `shock_*` que consumen las formulas del
#: motor (los mismos que usan los dilemas, `dilemmas.EFFECT_TERM_MAP`).
STATE_TERM = {
    "government_approval": "shock_approval",
    "congress_support": "shock_congress",
    "protest_level": "shock_protest",
    "social_tension": "shock_tension",
    "consumer_confidence": "shock_cc",
    "institutional_confidence": "shock_conf",
    "gdp": "shock_gdp",
    "reserves": "shock_reserves",
    "fiscal_balance": "shock_fiscal",
}

#: Bump de relacion invento para `ENDORSE`/`CRITICIZE` (ADR 003 secc. 5 no
#: tabula un valor para estos dos tipos): +-5, simetrico y mas chico que
#: `FORM_ALLIANCE`/`BREAK_ALLIANCE` (+10/-15) por ser un gesto, no un pacto.
ENDORSE_RELATIONSHIP_DELTA = 5.0
CRITICIZE_RELATIONSHIP_DELTA = -5.0


@lru_cache(maxsize=4)
def _load_yaml(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_consequences(path: str | Path | None = None) -> dict[str, Any]:
    return _load_yaml(str(path) if path is not None else str(DEFAULT_CONSEQUENCES_PATH))


def load_concessions(path: str | Path | None = None) -> dict[str, Any]:
    return _load_yaml(str(path) if path is not None else str(DEFAULT_CONCESSIONS_PATH))


@dataclass
class ConsequenceContext:
    state: WorldState
    policy: Policy
    parties_by_id: dict[str, Party]
    coeffs: dict[str, Any] = field(default_factory=load_consequences)
    concessions: dict[str, Any] = field(default_factory=load_concessions)


RelationshipDelta = tuple[str, str, float]


@dataclass
class Relationships:
    """`relationships[a][b]` (ADR 003 secc. 5): en el motor se guarda un
    unico valor simetrico por par `{a, b}` (las fichas declaran relaciones
    direccionales, pero el ADR trata los efectos como si movieran "la"
    relacion entre dos actores, sin distinguir sentido; ver Notas de
    implementacion). Decae hacia `target` a razon de `rate`/mes."""

    values: dict[frozenset[str], float] = field(default_factory=dict)

    @classmethod
    def from_actors(cls, actors: dict[str, ActorSheet]) -> Relationships:
        raw: dict[frozenset[str], list[float]] = {}
        for actor_id, sheet in actors.items():
            for other_id, value in sheet.relationships.items():
                if other_id not in actors or other_id == actor_id:
                    continue
                key = frozenset((actor_id, other_id))
                raw.setdefault(key, []).append(float(value))
        merged = {key: sum(vals) / len(vals) for key, vals in raw.items()}
        return cls(values=merged)

    def get(self, a: str, b: str) -> float:
        if a == b:
            return 100.0
        return self.values.get(frozenset((a, b)), 50.0)

    def bump(self, a: str, b: str, delta: float) -> None:
        if a == b or not delta:
            return
        key = frozenset((a, b))
        current = self.values.get(key, 50.0)
        self.values[key] = clamp(current + delta, 0.0, 100.0)

    def decay(self, rate: float = 0.5, target: float = 50.0) -> None:
        for key, value in list(self.values.items()):
            if value > target:
                self.values[key] = max(target, value - rate)
            elif value < target:
                self.values[key] = min(target, value + rate)

    def view_of(self, actor_id: str) -> dict[str, int]:
        """Todas las relaciones que involucran a `actor_id`, para
        `Perception.relationships` ("solo las propias", ADR 003 secc. 3)."""
        out: dict[str, int] = {}
        for key, value in self.values.items():
            if actor_id not in key:
                continue
            others = key - {actor_id}
            other = next(iter(others)) if others else actor_id
            out[other] = round(value)
        return out

    def snapshot(self) -> dict[str, dict[str, int]]:
        """Vista completa (para el `kind: "relationships"` del log)."""
        out: dict[str, dict[str, int]] = {}
        for key, value in self.values.items():
            a, b = tuple(key) if len(key) == 2 else (next(iter(key)), next(iter(key)))
            out.setdefault(a, {})[b] = round(value)
            out.setdefault(b, {})[a] = round(value)
        return out


def _business_actor_ids(actors: dict[str, ActorSheet]) -> list[str]:
    return [aid for aid, sheet in actors.items() if sheet.role == "business"]


def apply_consequences(
    actions: list[Action],
    actors: dict[str, ActorSheet],
    ctx: ConsequenceContext,
) -> tuple[dict[str, float], list[RelationshipDelta], list[str]]:
    """Aplica la tabla de ADR 003 secc. 5 a `actions` (ya autorizadas).
    Devuelve `(pending_terms, relationship_deltas, events)`: `pending_terms`
    son `shock_*`/`policy_*` para el mes siguiente, `relationship_deltas` una
    lista `(a, b, delta)` a sumar a `Relationships`, `events` texto legible
    (para `narrate`/el log)."""
    coeffs = ctx.coeffs
    pending: dict[str, float] = {}
    rel_deltas: list[RelationshipDelta] = []
    events: list[str] = []

    def add(term: str, value: float) -> None:
        if value:
            pending[term] = pending.get(term, 0.0) + value

    for action in actions:
        actor = actors.get(action.actor_id)
        if actor is None or action.type is ActionType.NO_ACTION:
            continue
        infl = actor.influence
        p = action.params
        t = action.type

        if t is ActionType.PUBLIC_STATEMENT:
            cfg = coeffs["public_statement"][p["stance"]]
            intensity = p["intensity"]
            scale = getattr(infl, cfg["scale_by"]) if "scale_by" in cfg else 1.0
            for f, coef in cfg["state"].items():
                add(STATE_TERM[f], coef * intensity * scale)
            rel_deltas.append((actor.id, "president", cfg["relationship_president"] * intensity))
            events.append(f"{actor.id} PUBLIC_STATEMENT({p['stance']})")

        elif t is ActionType.LOBBY_CONGRESS:
            cfg = coeffs["lobby_congress"][p["direction"]]
            intensity = p["intensity"]
            scale = getattr(infl, cfg["scale_by"])
            for f, coef in cfg["state"].items():
                add(STATE_TERM[f], coef * intensity * scale)
            events.append(f"{actor.id} LOBBY_CONGRESS({p['direction']})")

        elif t is ActionType.CALL_PROTEST:
            cfg = coeffs["call_protest"]
            intensity = p["intensity"]
            scale = getattr(infl, cfg["scale_by"])
            for f, coef in cfg["state"].items():
                value = coef * intensity
                if f in cfg["scaled_fields"]:
                    value *= scale
                add(STATE_TERM[f], value)
            rel_deltas.append((actor.id, "president", cfg["relationship_president"] * intensity))
            events.append(f"{actor.id} CALL_PROTEST")

        elif t is ActionType.STRIKE:
            cfg = coeffs["strike"][p["sector"]]
            days = p["days"]
            add("shock_gdp", cfg["gdp_per_day"] * days)
            add("shock_protest", cfg["protest"])
            add("shock_approval", cfg["approval"])
            rel_deltas.append((actor.id, "president", cfg["relationship_president"]))
            if cfg["relationship_business"]:
                for biz_id in _business_actor_ids(actors):
                    rel_deltas.append((actor.id, biz_id, cfg["relationship_business"]))
            events.append(f"{actor.id} STRIKE({p['sector']}, {days}d)")

        elif t in (ActionType.WITHHOLD_INVESTMENT, ActionType.INVEST):
            key = "withhold_investment" if t is ActionType.WITHHOLD_INVESTMENT else "invest"
            cfg = coeffs[key]
            intensity = p["intensity"]
            scale = getattr(infl, cfg["scale_by"])
            add("shock_gdp", cfg["gdp"] * intensity * scale)
            add("shock_cc", cfg["consumer_confidence"] * intensity * scale)
            rel_deltas.append((actor.id, "president", cfg["relationship_president"] * intensity))
            events.append(f"{actor.id} {t.value}")

        elif t is ActionType.PUBLISH_STORY:
            cfg = coeffs["publish_story"].get(p["frame"]) or {}
            scale = getattr(infl, cfg.get("scale_by", "public"))
            if "consumer_confidence" in cfg:
                add("shock_cc", cfg["consumer_confidence"] * scale)
            if "institutional_confidence" in cfg:
                add("shock_conf", cfg["institutional_confidence"] * scale)
            if "approval" in cfg:
                add("shock_approval", cfg["approval"] * scale)
            if p["frame"] == "scandal" and action.target:
                rel_deltas.append((actor.id, action.target, cfg.get("relationship_target", 0.0)))
            events.append(f"{actor.id} PUBLISH_STORY({p['frame']})")

        elif t is ActionType.ENDORSE:
            rel_deltas.append((actor.id, p["target"], ENDORSE_RELATIONSHIP_DELTA))
            events.append(f"{actor.id} ENDORSE({p['target']})")

        elif t is ActionType.CRITICIZE:
            rel_deltas.append((actor.id, p["target"], CRITICIZE_RELATIONSHIP_DELTA))
            events.append(f"{actor.id} CRITICIZE({p['target']})")

        elif t is ActionType.REQUEST_FUNDS:
            # Sin efecto propio: se resuelve el mes que viene, cuando el
            # presidente conceda o no (`resolve_pending_requests`).
            events.append(f"{actor.id} REQUEST_FUNDS({p['amount_pct_gdp']:.2f} pp PIB)")

        elif t is ActionType.NEGOTIATE:
            events.append(f"{actor.id} NEGOTIATE({p['requested_concession']})")

        elif t is ActionType.FORM_ALLIANCE:
            rel_deltas.append((actor.id, p["with"], coeffs["form_alliance"]["relationship_with"]))
            events.append(f"{actor.id} FORM_ALLIANCE({p['with']})")

        elif t is ActionType.BREAK_ALLIANCE:
            rel_deltas.append((actor.id, p["with"], coeffs["break_alliance"]["relationship_with"]))
            events.append(f"{actor.id} BREAK_ALLIANCE({p['with']})")

        elif t in (ActionType.SUPPORT_POLICY, ActionType.OPPOSE_POLICY):
            intensity = p["intensity"]
            sign = 1.0 if t is ActionType.SUPPORT_POLICY else -1.0
            party = (
                ctx.parties_by_id.get(actor.id.removeprefix("party_"))
                if actor.role == "party"
                else None
            )
            if party is not None:
                coef = coeffs["support_oppose_policy"]["congress_coef"]
                add("shock_congress", sign * coef * intensity * party.seats / 100.0)
            rel_coef = coeffs["support_oppose_policy"]["relationship_president_coef"]
            rel_deltas.append((actor.id, "president", sign * rel_coef * intensity))
            events.append(f"{actor.id} {t.value}")

        elif t is ActionType.RECOMMEND_RATE:
            events.append(f"{actor.id} RECOMMEND_RATE({p['delta_pp']:+.1f})")

        elif t is ActionType.SET_RATE:
            add("policy_interest_rate_target", p["delta_pp"])
            events.append(f"{actor.id} SET_RATE({p['delta_pp']:+.1f})")

        elif t is ActionType.GRANT_CONCESSION:
            cfg = ctx.concessions[p["concession"]]
            add("shock_fiscal", -cfg["fiscal_cost_pct_gdp"])
            if cfg.get("policy_field"):
                add(f"policy_{cfg['policy_field']}", cfg["policy_bump"])
            rel_deltas.append((p["to"], "president", coeffs["grant_concession"]["relationship_to"]))
            events.append(f"president GRANT_CONCESSION({p['concession']}) -> {p['to']}")

        elif t in (ActionType.PROPOSE_POLICY, ActionType.ENACT_POLICY):
            events.append(f"{actor.id} {t.value}")

    return pending, rel_deltas, events


def resolve_pending_requests(
    pending_requests: list[Action],
    granted_actor_ids: set[str],
    coeffs: dict[str, Any] | None = None,
) -> list[RelationshipDelta]:
    """`REQUEST_FUNDS`/`NEGOTIATE` del mes pasado que el presidente NO
    concedio este mes: `relationships.president -1` (ADR 003 secc. 5)."""
    coeffs = coeffs if coeffs is not None else load_consequences()
    delta = coeffs["request_funds"]["relationship_president_if_denied"]
    return [
        (req.actor_id, "president", delta)
        for req in pending_requests
        if req.actor_id not in granted_actor_ids
    ]
