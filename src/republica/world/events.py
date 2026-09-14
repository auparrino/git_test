"""Catalogo de shocks sorteados y eventos endogenos (seccion 6 del spec).

Formato de `shocks.json`: `id, name, base_p, conditional_p, duration, effects`.
Cada efecto tiene `target, value, when ("each"|"first")` y opcionalmente
`duration` (si un efecto dura mas que la ventana nominal del shock, como
`flood`/`epidemic` con su `shock_fiscal` a 3 meses aunque el shock dure 2:
ver seccion 6, filas `flood`/`epidemic`). El `target` puede ser:
  - `shock_<algo>`: termino aditivo que consumen las formulas de economia/
    sociedad/politica (`ShockAggregate.term(...)`).
  - `commodity_price` / `world_demand` / `consumer_confidence`: modificacion
    directa de una exogena o de una variable de estado.
  - `province_sector:<sector>` / `province_id:<id>`: efecto sobre el ingreso
    provincial derivado (seccion 7, fin).

Un shock no puede reactivarse mientras esta activo y se permiten como maximo
2 shocks nuevos por mes (seccion 6). El orden de sorteo es el orden del
catalogo (`shocks.json`), consumiendo un `U(0,1)` por shock siempre, para que
el consumo de RNG sea fijo independientemente del resultado.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from republica.world.state import WorldState

MAX_NEW_SHOCKS_PER_MONTH = 2

_OPS = {
    ">": lambda x, v: x > v,
    "<": lambda x, v: x < v,
    ">=": lambda x, v: x >= v,
    "<=": lambda x, v: x <= v,
    "==": lambda x, v: x == v,
}


@dataclass(frozen=True)
class ShockEffect:
    target: str
    value: float
    when: str
    duration: int | None = None


@dataclass(frozen=True)
class ConditionalP:
    add: float
    clauses: tuple[tuple[str, str, float], ...]


@dataclass(frozen=True)
class ShockDef:
    id: str
    name: str
    base_p: float
    conditional_p: tuple[ConditionalP, ...]
    duration: int
    effects: tuple[ShockEffect, ...]

    def probability(self, state: WorldState) -> float:
        p = self.base_p
        for cond in self.conditional_p:
            if any(_OPS[op](getattr(state, fld), val) for fld, op, val in cond.clauses):
                p += cond.add
        return p

    def effect_duration(self, effect: ShockEffect) -> int:
        return effect.duration if effect.duration is not None else self.duration


def build_catalog(raw: list[dict[str, Any]]) -> list[ShockDef]:
    """Construye el catalogo tipado (preserva el orden del JSON)."""
    out = []
    for item in raw:
        conditional = tuple(
            ConditionalP(
                add=c["add"],
                clauses=tuple((cl["field"], cl["op"], cl["value"]) for cl in c["any"]),
            )
            for c in item.get("conditional_p", [])
        )
        effects = tuple(
            ShockEffect(
                target=e["target"], value=e["value"], when=e["when"], duration=e.get("duration")
            )
            for e in item["effects"]
        )
        out.append(
            ShockDef(
                id=item["id"],
                name=item["name"],
                base_p=item["base_p"],
                conditional_p=conditional,
                duration=item["duration"],
                effects=effects,
            )
        )
    return out


@dataclass
class ActiveShock:
    """Un shock actualmente activo: cuenta regresiva independiente por efecto."""

    id: str
    started_month: int
    months_active: int = 0
    effects_remaining: dict[int, int] = field(default_factory=dict)


@dataclass
class ShockAggregate:
    """Suma de todos los efectos de los shocks activos este mes."""

    terms: dict[str, float] = field(default_factory=dict)
    field_bumps: dict[str, float] = field(default_factory=dict)
    province_sector: dict[str, float] = field(default_factory=dict)
    province_id: dict[str, float] = field(default_factory=dict)

    def add(self, target: str, value: float) -> None:
        if target.startswith("shock_"):
            self.terms[target] = self.terms.get(target, 0.0) + value
        elif target.startswith("province_sector:"):
            key = target.split(":", 1)[1]
            self.province_sector[key] = self.province_sector.get(key, 0.0) + value
        elif target.startswith("province_id:"):
            key = target.split(":", 1)[1]
            self.province_id[key] = self.province_id.get(key, 0.0) + value
        else:
            self.field_bumps[target] = self.field_bumps.get(target, 0.0) + value

    def term(self, name: str) -> float:
        return self.terms.get(name, 0.0)


class ShockCatalog:
    """Envuelve el catalogo y sabe rolear/aplicar un mes de shocks."""

    def __init__(self, defs: list[ShockDef]):
        self.defs = defs
        self.by_id = {d.id: d for d in defs}

    def roll(
        self,
        state: WorldState,
        rng: random.Random,
        active: dict[str, ActiveShock],
        month: int,
        forced: list[str] | None = None,
    ) -> list[str]:
        """Sortea el catalogo en orden (siempre consume 1 uniforme por shock),
        activa hasta `MAX_NEW_SHOCKS_PER_MONTH` nuevos, y fuerza los `forced`
        (sin consumir RNG, sin contar para el limite). Devuelve los ids nuevos.
        """
        new_ids: list[str] = []
        activated = 0
        for d in self.defs:
            u = rng.random()
            if d.id in active or activated >= MAX_NEW_SHOCKS_PER_MONTH:
                continue
            if u < d.probability(state):
                active[d.id] = ActiveShock(id=d.id, started_month=month)
                new_ids.append(d.id)
                activated += 1
        for shock_id in forced or []:
            if shock_id not in active:
                active[shock_id] = ActiveShock(id=shock_id, started_month=month)
            if shock_id not in new_ids:
                new_ids.append(shock_id)
        return new_ids

    def apply_month(self, active: dict[str, ActiveShock], new_ids: list[str]) -> ShockAggregate:
        """Aplica los efectos de este mes, decrementa contadores y desactiva
        los shocks cuyos efectos ya se agotaron todos.
        """
        agg = ShockAggregate()
        to_remove = []
        for shock_id, astate in active.items():
            d = self.by_id[shock_id]
            is_first_month = astate.months_active == 0
            if is_first_month:
                astate.effects_remaining = {
                    i: d.effect_duration(e) for i, e in enumerate(d.effects)
                }
            for i, e in enumerate(d.effects):
                remaining = astate.effects_remaining.get(i, 0)
                if remaining <= 0:
                    continue
                fires = e.when == "each" or (e.when == "first" and is_first_month)
                if fires:
                    agg.add(e.target, e.value)
                astate.effects_remaining[i] = remaining - 1
            astate.months_active += 1
            if all(v <= 0 for v in astate.effects_remaining.values()):
                to_remove.append(shock_id)
        for shock_id in to_remove:
            del active[shock_id]
        return agg


@dataclass
class Event:
    """Un evento endogeno (seccion 6.1) ocurrido este mes."""

    kind: str
    detail: str = ""


@dataclass
class EndogenousTracker:
    """Contadores que persisten entre meses para los eventos endogenos."""

    consecutive_low_stability: int = 0
    consecutive_high_inflation: int = 0
    last_devaluation_month: int | None = None


def check_forced_devaluation(
    state: WorldState, month: int, terminal, tracker: EndogenousTracker
) -> tuple[WorldState, dict[str, float], Event | None]:
    """`forced_devaluation` (seccion 6.1): reservas < umbral, cooldown de
    `devaluation_cooldown_months`. Ajusta `exchange_rate`/`reserves` de este
    mes y devuelve terminos pendientes (`shock_pi`, `shock_conf`) para el
    mes siguiente.
    """
    if state.reserves >= terminal.devaluation_reserves:
        return state, {}, None
    if (
        tracker.last_devaluation_month is not None
        and month - tracker.last_devaluation_month < terminal.devaluation_cooldown_months
    ):
        return state, {}, None
    old_reserves = state.reserves
    adjusted = state.model_copy(
        update={
            "exchange_rate": state.exchange_rate * terminal.devaluation_fx_multiplier,
            "reserves": state.reserves + terminal.devaluation_reserve_injection,
        }
    )
    tracker.last_devaluation_month = month
    pending = {
        "shock_pi": terminal.devaluation_pi_shock,
        "shock_conf": terminal.devaluation_conf_shock,
    }
    event = Event(kind="forced_devaluation", detail=f"reservas caen a USD {old_reserves:.0f} M")
    return adjusted, pending, event


def check_termination(
    state: WorldState, terminal, tracker: EndogenousTracker, month: int, months_total: int
) -> str | None:
    """Chequea `government_collapse`, `hyperinflation` y `term_end` (seccion 6.1)."""
    tracker.consecutive_low_stability = (
        tracker.consecutive_low_stability + 1
        if state.political_stability < terminal.collapse_stability
        else 0
    )
    tracker.consecutive_high_inflation = (
        tracker.consecutive_high_inflation + 1 if state.inflation > terminal.hyper_inflation else 0
    )
    if tracker.consecutive_low_stability >= terminal.collapse_months:
        return "collapse"
    if tracker.consecutive_high_inflation >= terminal.hyper_months:
        return "hyperinflation"
    if month >= months_total:
        return "survived"
    return None
