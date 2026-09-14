"""Motor de simulacion: orden de turno determinista (seccion 7 del spec)."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from republica.actors.president_rules import (
    RuleBasedPresident,
    apply_pending_policy_delta,
    compute_policy_proposal,
)
from republica.actors.sheet import ActorSheet
from republica.engine.actions import Action
from republica.engine.policy import ConstantPolicy, PolicyRule
from republica.engine.scheduler import ActionRecord, ActorEngine, build_actor_engine, run_actor_turn
from republica.world.config import Country, load_country
from republica.world.economy import finalize_exogenous, step_economy, step_exogenous
from republica.world.events import (
    ActiveShock,
    EndogenousTracker,
    ShockAggregate,
    ShockCatalog,
    build_catalog,
    check_forced_devaluation,
    check_termination,
)
from republica.world.politics import step_politics
from republica.world.provinces import compute_provinces
from republica.world.society import step_society
from republica.world.state import Exogenous, Policy, WorldState, clamp_state

OUTCOMES = ("survived", "collapse", "hyperinflation")


@dataclass
class MonthRecord:
    """Un mes de historia (seccion 9): estado, exogenas, politica, shocks,
    eventos y auxiliares, listo para serializar a una linea JSONL."""

    month_index: int
    date: str
    state: dict
    exo: dict
    policy: dict
    aux: dict
    shocks_new: list[str]
    shocks_active: list[str]
    events: list[str]
    provinces: list[dict]
    overflow: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class History:
    """El resultado completo de `run(seed)` (seccion 9).

    `action_records` (ADR 003 secc. 8, vacio si `features.actors` esta
    apagado) se intercala en `to_jsonl()` justo despues del `MonthRecord` de
    su mes, cada uno como su propia linea `{"kind": "action", ...}`. Con
    `action_records` vacio, `to_jsonl()` produce exactamente el mismo texto
    que antes de ADR 003 (test de bytes identicos con `--no-actors`): esto,
    y no agregar un campo a `MonthRecord`, es la razon por la que las
    acciones viven en un dataclass aparte (ver Notas de implementacion).
    """

    records: list[MonthRecord]
    outcome: str
    seed: int
    config_hash: str
    action_records: list[Any] = field(default_factory=list)

    def to_jsonl(self) -> str:
        by_month: dict[int, list[Any]] = {}
        for rec in self.action_records:
            by_month.setdefault(rec.month, []).append(rec)

        lines = []
        for r in self.records:
            lines.append(json.dumps(r.to_dict(), ensure_ascii=False))
            for action_rec in by_month.get(r.month_index, []):
                lines.append(json.dumps(action_rec.to_dict(), ensure_ascii=False))
        lines.append(
            json.dumps(
                {"outcome": self.outcome, "seed": self.seed, "config_hash": self.config_hash},
                ensure_ascii=False,
            )
        )
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict:
        return {
            "records": [r.to_dict() for r in self.records],
            "outcome": self.outcome,
            "seed": self.seed,
            "config_hash": self.config_hash,
            "action_records": [a.to_dict() for a in self.action_records],
        }


@dataclass
class Simulation:
    """Estado interactivo de una corrida en curso (para uso desde Fase 2 con
    `advance_month`); `run()` lo consume mes a mes."""

    country: Country
    catalog: ShockCatalog
    rng: random.Random
    policy_rule: PolicyRule
    forced_shocks: dict[int, list[str]]
    shocks_enabled: bool
    exogenous_noise: bool
    state: WorldState
    exo: Exogenous
    active_shocks: dict[str, ActiveShock] = field(default_factory=dict)
    pending_terms: dict[str, float] = field(default_factory=dict)
    tracker: EndogenousTracker = field(default_factory=EndogenousTracker)
    month: int = 0
    outcome: str | None = None
    records: list[MonthRecord] = field(default_factory=list)
    # -- ADR 003 (actores): todo default-off para no tocar el comportamiento
    # de Fase 1/2 salvo que se pida explicitamente (ver Notas de
    # implementacion: `actors_enabled` default `False` a nivel de funcion/
    # `Simulation`, distinto del default `True` de `features.actors` que usa
    # la CLI `republica run`).
    actors_enabled: bool = False
    actor_engine: ActorEngine | None = None
    president_rule: RuleBasedPresident | None = None
    last_policy: Policy | None = None
    pending_policy_delta: dict[str, float] = field(default_factory=dict)
    pending_grant_override: list[Action] | None = None
    action_records: list[ActionRecord] = field(default_factory=list)


def new_simulation(
    seed: int,
    policy_rule: PolicyRule | None,
    forced_shocks: dict[int, list[str]] | None,
    country: Country | None,
    shocks_enabled: bool,
    exogenous_noise: bool,
    actors_enabled: bool = False,
    actors: dict[str, ActorSheet] | None = None,
    rule_based_president: bool = False,
) -> Simulation:
    """Construye una `Simulation` nueva sin correrla (uso interactivo, Fase 2:
    ver `engine/game.py`, que llama `advance_month` mes a mes).

    `actors_enabled` (ADR 003, default `False` a nivel de funcion: ver
    Notas de implementacion) arma un `ActorEngine` (29 fichas por defecto,
    o `actors` para tests) que corre `engine/scheduler.py::run_actor_turn`
    cada mes. `rule_based_president=True` (uso de `run`, no de `play`) hace
    que el presidente tambien sea por reglas: envuelve `policy_rule` en un
    `RuleBasedPresident` que ademas concede pedidos pendientes."""
    country = country or load_country()
    catalog = ShockCatalog(build_catalog(country.shocks))
    resolved_policy_rule = policy_rule or ConstantPolicy(country.default_policy)
    actor_engine = build_actor_engine(seed, country, actors) if actors_enabled else None
    president_rule = (
        RuleBasedPresident(policy_rule=resolved_policy_rule)
        if actors_enabled and rule_based_president
        else None
    )
    return Simulation(
        country=country,
        catalog=catalog,
        rng=random.Random(seed),
        policy_rule=resolved_policy_rule,
        forced_shocks=forced_shocks or {},
        shocks_enabled=shocks_enabled,
        exogenous_noise=exogenous_noise,
        state=country.initial_state.model_copy(),
        exo=country.exogenous.model_copy(),
        actors_enabled=actors_enabled,
        actor_engine=actor_engine,
        president_rule=president_rule,
        last_policy=country.default_policy.model_copy(),
    )


def _format_date(start_year: int, start_month: int, month_index: int) -> str:
    total = (start_month - 1) + (month_index - 1)
    year = start_year + total // 12
    month = total % 12 + 1
    return f"{year:04d}-{month:02d}"


def advance_month(sim: Simulation) -> MonthRecord:
    """Avanza un mes siguiendo el orden de la seccion 7. Muta `sim` y devuelve
    el `MonthRecord` (ya agregado a `sim.records`)."""
    sim.month += 1
    month = sim.month
    country = sim.country
    coeff = country.coefficients

    # 1. exogenas (AR1 + ruido)
    commodity_base, world_base = step_exogenous(
        sim.exo, country.exogenous_process, sim.rng, sim.exogenous_noise
    )

    # 2. shocks: sorteo por catalogo en orden, activacion, efectos del mes
    if sim.shocks_enabled:
        forced = sim.forced_shocks.get(month)
        new_ids = sim.catalog.roll(sim.state, sim.rng, sim.active_shocks, month, forced=forced)
        agg = sim.catalog.apply_month(sim.active_shocks, new_ids)
    else:
        new_ids = []
        agg = ShockAggregate()

    for name, value in sim.pending_terms.items():
        # Los terminos `policy_*` (ADR 003 secc. 5: `GRANT_CONCESSION`/
        # `SET_RATE` que tocan un instrumento de `Policy`, no una variable de
        # `WorldState`) no son un `shock_*` de una formula del motor: se
        # acumulan aparte y se aplican a la `Policy` del paso 3, no a `agg`.
        if name.startswith("policy_"):
            field_name = name.removeprefix("policy_")
            sim.pending_policy_delta[field_name] = (
                sim.pending_policy_delta.get(field_name, 0.0) + value
            )
        else:
            agg.terms[name] = agg.terms.get(name, 0.0) + value
    sim.pending_terms = {}

    exo_new = finalize_exogenous(commodity_base, world_base, agg)

    # 3. politica: presidente decide Policy (+ PROPOSE_POLICY/GRANT_CONCESSION
    # si `actors_enabled`, ADR 003 secc. 7 paso 2) y, si hay actores, corren
    # perceptions -> decide -> authorize -> consequences (pasos 3-6).
    policy = sim.policy_rule.decide(sim.state, month)
    if sim.actors_enabled:
        assert sim.actor_engine is not None
        policy = apply_pending_policy_delta(policy, sim.pending_policy_delta, country.policy_ranges)
        sim.pending_policy_delta = {}
        proposal = compute_policy_proposal(policy, sim.last_policy)

        if sim.pending_grant_override is not None:
            grants = sim.pending_grant_override
            sim.pending_grant_override = None
        elif sim.president_rule is not None:
            grants = sim.president_rule.decide_grants(
                sim.actor_engine.pending_requests, sim.actor_engine.relationships
            )
        else:
            grants = []

        active_shock_ids = sorted(sim.active_shocks.keys())
        recent_events = sim.records[-1].events if sim.records else []
        # ADR 003 no define elecciones (Fase 6): se usa `months_left` de
        # SPEC_v0.2_play como placeholder (ver Notas de implementacion).
        months_to_election = max(country.months - month + 1, 0)

        action_records, actor_pending = run_actor_turn(
            sim.actor_engine,
            country,
            sim.state,
            policy,
            agg,
            active_shock_ids,
            recent_events,
            month,
            months_to_election,
            proposal,
            grants,
        )
        sim.action_records.extend(action_records)
        # `actor_pending` (shock_*/policy_*) se guarda tal cual en
        # `sim.pending_terms`: el mismo split policy_/shock_* de arriba lo
        # procesa el mes que viene, al principio de `advance_month` (misma
        # via que `check_forced_devaluation`/dilemas).
        for name, value in actor_pending.items():
            sim.pending_terms[name] = sim.pending_terms.get(name, 0.0) + value
        sim.last_policy = policy.model_copy()

    # 4. economia (4.1 -> 4.8)
    econ_state, aux = step_economy(
        sim.state, sim.exo, exo_new, policy, agg, country.structure, coeff
    )
    if sim.actors_enabled:
        assert sim.actor_engine is not None
        # Las percepciones del mes que viene ven el `Aux` de este mes (el de
        # este mes recien se conoce aca, despues de que los actores ya
        # decidieron con el snapshot `t`: ver Notas de implementacion).
        sim.actor_engine.last_aux = aux

    # 5. sociedad (5.1 -> 5.5)
    soc_state = step_society(sim.state, econ_state, policy, agg, coeff)

    # 6. politica (5.6 -> 5.9)
    full_state = step_politics(
        sim.state, soc_state, aux.demand_gap, country.coalition_seats, agg, coeff
    )

    # 7. clamp
    clamped, overflow = clamp_state(full_state, country.ranges)

    # 8. eventos endogenos y fin de partida
    events: list[str] = []
    clamped, pending, dev_event = check_forced_devaluation(
        clamped, month, country.terminal, sim.tracker
    )
    if dev_event is not None:
        clamped, _ = clamp_state(clamped, country.ranges)
        sim.pending_terms.update(pending)
        events.append(dev_event.kind)

    outcome = check_termination(clamped, country.terminal, sim.tracker, month, country.months)
    if outcome is not None:
        events.append(f"term_end:{outcome}" if outcome == "survived" else outcome)
        sim.outcome = outcome

    # 9. registro
    provinces = compute_provinces(
        clamped,
        policy,
        country.provinces,
        coeff.province_transfer_sensitivity,
        coeff.transfers_ref,
        agg,
    )
    record = MonthRecord(
        month_index=month,
        date=_format_date(country.start["year"], country.start["month"], month),
        state=clamped.model_dump(),
        exo=exo_new.model_dump(),
        policy=policy.model_dump(),
        aux=asdict(aux),
        shocks_new=new_ids,
        shocks_active=sorted(sim.active_shocks.keys()),
        events=events,
        provinces=[asdict(p) for p in provinces],
        overflow=overflow,
    )
    sim.records.append(record)

    # 10. month += 1 (ya incrementado al inicio)
    sim.state = clamped
    sim.exo = exo_new
    return record


def run(
    seed: int,
    months: int = 48,
    policy_rule: PolicyRule | None = None,
    forced_shocks: dict[int, list[str]] | None = None,
    country: Country | None = None,
    shocks_enabled: bool = True,
    exogenous_noise: bool = True,
    actors_enabled: bool = False,
    actors: dict[str, ActorSheet] | None = None,
) -> History:
    """Corre `months` meses (o hasta un fin de partida temprano) y devuelve
    la `History`.

    `actors_enabled` (default `False`, ADR 003): activa los 29 actores por
    reglas + un presidente por reglas (`RuleBasedPresident`) que envuelve
    `policy_rule`. El default de esta *funcion* se mantiene apagado a
    proposito para no romper ningun llamador existente (los 46 tests de
    Fase 1/2 corren `run()`/`Game.new()` sin pedir actores); es
    `republica run` (la CLI) la que activa `features.actors` por defecto y
    ofrece `--no-actors` para apagarlo (ver Notas de implementacion)."""
    sim = new_simulation(
        seed,
        policy_rule,
        forced_shocks,
        country,
        shocks_enabled,
        exogenous_noise,
        actors_enabled=actors_enabled,
        actors=actors,
        rule_based_president=actors_enabled,
    )
    sim.country = sim.country.model_copy(update={"months": months})
    for _ in range(months):
        advance_month(sim)
        if sim.outcome is not None:
            break
    return History(
        records=sim.records,
        outcome=sim.outcome or "survived",
        seed=seed,
        config_hash=sim.country.config_hash,
        action_records=sim.action_records,
    )
