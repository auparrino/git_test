"""Motor de simulacion: orden de turno determinista (seccion 7 del spec)."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field

from republica.engine.policy import ConstantPolicy, PolicyRule
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
from republica.world.state import Exogenous, WorldState, clamp_state

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
    """El resultado completo de `run(seed)` (seccion 9)."""

    records: list[MonthRecord]
    outcome: str
    seed: int
    config_hash: str

    def to_jsonl(self) -> str:
        lines = [json.dumps(r.to_dict(), ensure_ascii=False) for r in self.records]
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


def _new_simulation(
    seed: int,
    policy_rule: PolicyRule | None,
    forced_shocks: dict[int, list[str]] | None,
    country: Country | None,
    shocks_enabled: bool,
    exogenous_noise: bool,
) -> Simulation:
    country = country or load_country()
    catalog = ShockCatalog(build_catalog(country.shocks))
    return Simulation(
        country=country,
        catalog=catalog,
        rng=random.Random(seed),
        policy_rule=policy_rule or ConstantPolicy(country.default_policy),
        forced_shocks=forced_shocks or {},
        shocks_enabled=shocks_enabled,
        exogenous_noise=exogenous_noise,
        state=country.initial_state.model_copy(),
        exo=country.exogenous.model_copy(),
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
        agg.terms[name] = agg.terms.get(name, 0.0) + value
    sim.pending_terms = {}

    exo_new = finalize_exogenous(commodity_base, world_base, agg)

    # 3. politica
    policy = sim.policy_rule.decide(sim.state, month)

    # 4. economia (4.1 -> 4.8)
    econ_state, aux = step_economy(
        sim.state, sim.exo, exo_new, policy, agg, country.structure, coeff
    )

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
) -> History:
    """Corre `months` meses (o hasta un fin de partida temprano) y devuelve la `History`."""
    sim = _new_simulation(
        seed, policy_rule, forced_shocks, country, shocks_enabled, exogenous_noise
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
    )
