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
from republica.ai.brains import DEFAULT_BRAIN
from republica.ai.tracing import DecisionTrace
from republica.engine.actions import Action
from republica.engine.congress import Bill, VoteRecord, derive_congress_support, requires_law
from republica.engine.congress import vote as congress_vote
from republica.engine.negotiation import (
    NegotiationRecord,
    apply_execution_results,
    sum_queue_delta,
)
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
    #: `DecisionTrace` de los actores IA (ADR 004 secc. 6), vacio si ningun
    #: actor usa un cerebro `llm:*`/`fake:*` (`RuleBasedActor` no traza
    #: nada): con `action_records` vacio Y `trace_records` vacio,
    #: `to_jsonl()` sigue produciendo el mismo texto que antes de ADR 004,
    #: igual que ya garantizaba ADR 003 secc. 11 punto 6 para `action_records`.
    trace_records: list[DecisionTrace] = field(default_factory=list)
    #: `VoteRecord`/`NegotiationRecord` (ADR 005 secc. 1/2, `kind: "vote"`/
    #: `"negotiation"`), vacios con `features.congress`/`features.negotiation`
    #: apagados (mismo patron que `action_records`/`trace_records`: con
    #: ambos vacios, `to_jsonl()` produce el mismo texto que antes de ADR 005).
    vote_records: list[VoteRecord] = field(default_factory=list)
    negotiation_records: list[NegotiationRecord] = field(default_factory=list)

    def to_jsonl(self) -> str:
        by_month: dict[int, list[Any]] = {}
        for rec in self.action_records:
            by_month.setdefault(rec.month, []).append(rec)
        traces_by_month: dict[int, list[DecisionTrace]] = {}
        for trace in self.trace_records:
            traces_by_month.setdefault(trace.month, []).append(trace)
        negotiations_by_month: dict[int, list[NegotiationRecord]] = {}
        for neg in self.negotiation_records:
            negotiations_by_month.setdefault(neg.month, []).append(neg)
        votes_by_month: dict[int, list[VoteRecord]] = {}
        for v in self.vote_records:
            votes_by_month.setdefault(v.month, []).append(v)

        lines = []
        for r in self.records:
            lines.append(json.dumps(r.to_dict(), ensure_ascii=False))
            for action_rec in by_month.get(r.month_index, []):
                lines.append(json.dumps(action_rec.to_dict(), ensure_ascii=False))
            for trace in traces_by_month.get(r.month_index, []):
                lines.append(json.dumps(trace.to_dict(), ensure_ascii=False))
            for neg in negotiations_by_month.get(r.month_index, []):
                lines.append(json.dumps(neg.to_dict(), ensure_ascii=False))
            for v in votes_by_month.get(r.month_index, []):
                lines.append(json.dumps(v.to_dict(), ensure_ascii=False))
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
            "trace_records": [t.to_dict() for t in self.trace_records],
            "vote_records": [v.to_dict() for v in self.vote_records],
            "negotiation_records": [n.to_dict() for n in self.negotiation_records],
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
    #: `Policy` que devolvio `policy_rule.decide()` el mes pasado, *antes* de
    #: sumarle `concessions_delta` (hallazgo #5 de REVIEW_001): sirve de
    #: base para la `PolicyProposal` de este mes (`compute_policy_proposal`),
    #: para que una concesion ya otorgada no aparezca como una propuesta de
    #: recorte fantasma el mes que viene (ver `advance_month`).
    last_policy: Policy | None = None
    #: Bump acumulativo y persistente por instrumento de `Policy`, de las
    #: concesiones `policy_*` otorgadas (`GRANT_CONCESSION`/`SET_RATE`,
    #: hallazgo #5 de REVIEW_001): a diferencia de un `shock_*`, que dura lo
    #: que dure el efecto, una concesion sobre un instrumento queda "pegada"
    #: (se suma a la `Policy` de la regla vigente TODOS los meses, hasta que
    #: una concesion nueva sobre el mismo campo la cambie) -- antes se
    #: aplicaba una vez y se descartaba, lo que producia un "recorte"
    #: fantasma al mes siguiente (ver `advance_month`).
    concessions_delta: dict[str, float] = field(default_factory=dict)
    pending_grant_override: list[Action] | None = None
    action_records: list[ActionRecord] = field(default_factory=list)
    #: `DecisionTrace` de los `LLMActor` (ADR 004 secc. 6), acumuladas mes a
    #: mes igual que `action_records`; vacio con el `default_brain`
    #: `"rules"` (comportamiento identico a antes de ADR 004).
    trace_records: list[DecisionTrace] = field(default_factory=list)
    #: `VoteRecord`/`NegotiationRecord` (ADR 005), acumulados igual que
    #: `action_records`; vacios con `features.congress`/`features.negotiation`
    #: apagados.
    vote_records: list[VoteRecord] = field(default_factory=list)
    negotiation_records: list[NegotiationRecord] = field(default_factory=list)
    #: `Policy` efectivamente vigente el mes pasado (post-bump de concesiones
    #: Y post-veto de Congreso, ADR 005 secc. 1.3): distinta de `last_policy`
    #: (la que *propuso* la regla/el jugador, pre-bump/pre-veto, usada para
    #: calcular la `PolicyProposal` de este mes). Sirve para revertir un
    #: instrumento al valor del mes pasado cuando el Congreso rechaza el
    #: `Bill` que lo tocaba (ver `advance_month`).
    last_effective_policy: Policy | None = None
    #: `features.congress`/`features.negotiation` resueltos para esta
    #: corrida (ADR 005): copiados de `Country.features` al construir la
    #: `Simulation` (ver `new_simulation`), no se releen mes a mes.
    congress_enabled: bool = False
    negotiation_enabled: bool = False


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
    brain_map: dict[str, str] | None = None,
    default_brain: str = DEFAULT_BRAIN,
    llm_temperature: float = 0.4,
    llm_cache_dir: str | None = None,
    congress_enabled: bool = False,
    negotiation_enabled: bool = False,
) -> Simulation:
    """Construye una `Simulation` nueva sin correrla (uso interactivo, Fase 2:
    ver `engine/game.py`, que llama `advance_month` mes a mes).

    `actors_enabled` (ADR 003, default `False` a nivel de funcion: ver
    Notas de implementacion) arma un `ActorEngine` (29 fichas por defecto,
    o `actors` para tests) que corre `engine/scheduler.py::run_actor_turn`
    cada mes. `rule_based_president=True` (uso de `run`, no de `play`) hace
    que el presidente tambien sea por reglas: envuelve `policy_rule` en un
    `RuleBasedPresident` que ademas concede pedidos pendientes.

    `brain_map`/`default_brain`/`llm_temperature`/`llm_cache_dir` (ADR 004
    secc. 7) solo importan si `actors_enabled`: que cerebro usa cada actor
    (default `"rules"` para todos, comportamiento identico a antes de ADR
    004) y los parametros de los cerebros LLM.

    `congress_enabled`/`negotiation_enabled` (ADR 005, default `False` a
    nivel de funcion, mismo criterio que `actors_enabled`: quien resuelve
    `country.features` es la CLI, no esta funcion) solo tienen efecto si
    `actors_enabled` tambien lo esta."""
    country = country or load_country()
    catalog = ShockCatalog(build_catalog(country.shocks))
    resolved_policy_rule = policy_rule or ConstantPolicy(country.default_policy)
    actor_engine = (
        build_actor_engine(
            seed,
            country,
            actors,
            brain_map=brain_map,
            default_brain=default_brain,
            llm_temperature=llm_temperature,
            llm_cache_dir=llm_cache_dir,
        )
        if actors_enabled
        else None
    )
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
        last_effective_policy=country.default_policy.model_copy(),
        congress_enabled=congress_enabled and actors_enabled,
        negotiation_enabled=negotiation_enabled and actors_enabled,
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
    # Calculada temprano (hallazgo #12 de REVIEW_001): antes solo se
    # calculaba al final, al armar el `MonthRecord` (paso 9), asi que
    # `Perception.date` (paso 3, actores) siempre quedaba vacio -- no habia
    # fecha todavia con que poblarla.
    date = _format_date(country.start["year"], country.start["month"], month)

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
        # acumulan aparte, en `concessions_delta` -- de forma persistente
        # (hallazgo #5 de REVIEW_001: antes se aplicaban una vez y se
        # descartaban, ver el campo en `Simulation`) -- y se suman a la
        # `Policy` del paso 3 cada mes, no a `agg`.
        if name.startswith("policy_"):
            field_name = name.removeprefix("policy_")
            sim.concessions_delta[field_name] = sim.concessions_delta.get(field_name, 0.0) + value
        else:
            agg.terms[name] = agg.terms.get(name, 0.0) + value
    sim.pending_terms = {}

    exo_new = finalize_exogenous(commodity_base, world_base, agg)

    # 3. politica: presidente decide Policy (+ PROPOSE_POLICY/GRANT_CONCESSION
    # si `actors_enabled`, ADR 003 secc. 7 paso 2) y, si hay actores, corren
    # perceptions -> decide -> authorize -> consequences (pasos 3-6).
    raw_policy = sim.policy_rule.decide(sim.state, month)
    policy = raw_policy
    #: Eventos de Congreso/negociacion de este mes (ADR 005: `agreement_broken`
    #: y afines, "para memoria de Fase 6"), sumados a `MonthRecord.events`
    #: (paso 8/11) mas abajo. Vacio si `actors_enabled` esta apagado.
    agreement_events: list[str] = []
    #: Igual que en ADR 003 secc. 11 punto 7: placeholder de elecciones.
    # Se calcula siempre (no solo con actores) porque `derive_congress_support`
    # (mas abajo) tambien la necesita.
    months_to_election = max(country.months - month + 1, 0)
    if sim.actors_enabled:
        assert sim.actor_engine is not None
        # `policy` (lo que efectivamente rige este mes) le suma a
        # `raw_policy` (lo que la regla/el jugador decidio, sin concesiones)
        # el bump persistente de `concessions_delta`. La `PolicyProposal`
        # (hallazgo #5) se calcula entre `raw_policy` y `sim.last_policy`
        # (el `raw_policy` del mes pasado, tambien pre-bump): comparar dos
        # valores post-bump haria aparecer como "propuesta" el bump en si
        # mismo, y con `concessions_delta` ahora persistente (no se resetea)
        # ya no hay una "reversion" fantasma que generarle a nadie.
        policy = apply_pending_policy_delta(
            raw_policy, sim.concessions_delta, country.policy_ranges
        )
        proposal = compute_policy_proposal(raw_policy, sim.last_policy)

        if sim.pending_grant_override is not None:
            grants = sim.pending_grant_override
            sim.pending_grant_override = None
        elif sim.president_rule is not None:
            grants = sim.president_rule.decide_grants(
                sim.actor_engine.pending_requests, sim.actor_engine.relationships
            )
        else:
            grants = []

        # Los shocks de duracion 1 se borran de `sim.active_shocks` en el
        # mismo mes en que se sortean (`ShockCatalog.apply_month`, arriba):
        # sin sumar `new_ids`, la percepcion de este mes nunca los veia
        # (hallazgo #3 de REVIEW_001 -- el frame `scandal` de medios nunca
        # se disparaba porque `corruption_scandal` dura 1 mes).
        active_shock_ids = sorted(set(sim.active_shocks) | set(new_ids))
        recent_events = sim.records[-1].events if sim.records else []

        # ADR 005 secc. 1: parte del `Bill` que viene de la propuesta del mes
        # (deltas de instrumentos que requieren ley) mas la que viene de
        # concesiones de negociacion ya acordadas y todavia no ejecutadas
        # (`pre_queue_agreements`, tomada ANTES de correr las negociaciones
        # de este mes: una concesion acordada este mes recien puede votarse
        # el mes que viene, ver Notas de implementacion). Ambas gateadas por
        # `congress_enabled`: sin Congreso, ninguna concesion "requiere ley"
        # (`negotiation.negotiate_one` decide `law_required=False` siempre),
        # asi que `pre_queue_agreements` nunca tiene nada que aportar.
        pre_queue_agreements = [
            a
            for a in sim.actor_engine.agreements
            if a.status == "vigente" and a.law_required and not a.executed
        ]
        pre_queue_delta = (
            sum_queue_delta(pre_queue_agreements, sim.actor_engine.concessions)
            if sim.congress_enabled
            else {}
        )
        proposal_law_delta = requires_law(proposal.delta) if sim.congress_enabled else {}
        bill_delta = dict(pre_queue_delta)
        for field_name, value in proposal_law_delta.items():
            bill_delta[field_name] = bill_delta.get(field_name, 0.0) + value
        bill = (
            Bill(id=f"bill_{month}", month=month, policy_delta=bill_delta) if bill_delta else None
        )

        # ADR 005 secc. 2: el protocolo de negociacion multironda solo corre
        # con un presidente por reglas (`run`): con un humano jugando
        # (`play`), una negociacion sincronica dentro del mismo turno no es
        # viable en una CLI, asi que `NEGOTIATE` sigue el camino de un mes de
        # desfasaje (`engine.pending_requests` + `Game.set_grant_decisions`,
        # con la opcion "Contraoferta 50%" agregada, ver `engine/game.py` y
        # Notas de implementacion).
        negotiation_enabled = sim.negotiation_enabled and sim.president_rule is not None
        action_records, actor_pending, negotiation_records = run_actor_turn(
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
            date=date,
            negotiation_enabled=negotiation_enabled,
            congress_enabled=sim.congress_enabled,
        )
        sim.action_records.extend(action_records)
        sim.trace_records.extend(sim.actor_engine.last_traces)
        sim.negotiation_records.extend(negotiation_records)
        agreement_events.extend(sim.actor_engine.last_compliance_events)
        # `actor_pending` (shock_*/policy_*) se guarda tal cual en
        # `sim.pending_terms`: el mismo split policy_/shock_* de arriba lo
        # procesa el mes que viene, al principio de `advance_month` (misma
        # via que `check_forced_devaluation`/dilemas).
        for name, value in actor_pending.items():
            sim.pending_terms[name] = sim.pending_terms.get(name, 0.0) + value
        sim.last_policy = raw_policy.model_copy()

        if bill is not None:
            assert sim.congress_enabled
            allowed_actions_this_month = [ar for ar in action_records if ar.authorized]
            vigente_agreements = [a for a in sim.actor_engine.agreements if a.status == "vigente"]
            vote_record = congress_vote(
                bill,
                country.parties,
                sim.actor_engine.actors,
                allowed_actions_this_month,
                sim.state,
                sim.actor_engine.relationships,
                vigente_agreements,
                months_to_election,
                sim.actor_engine.congress_rng,
            )
            sim.vote_records.append(vote_record)
            if not vote_record.passed:
                # ADR 005 secc. 1.3: la parte legislativa del delta no se
                # aplica -- se revierte al valor efectivamente vigente el mes
                # pasado (no al `raw_policy` de este mes) -- y el sistema
                # "funciono": `approval -1`, `institutional_confidence +0.5`,
                # diferido al mes que viene (misma via que toda consecuencia).
                base = sim.last_effective_policy or country.default_policy
                reverted = {
                    field_name: getattr(base, field_name) for field_name in bill.policy_delta
                }
                policy = policy.model_copy(update=reverted)
                sim.pending_terms["shock_approval"] = (
                    sim.pending_terms.get("shock_approval", 0.0) - 1.0
                )
                sim.pending_terms["shock_conf"] = sim.pending_terms.get("shock_conf", 0.0) + 0.5
            exec_pending, exec_events = apply_execution_results(
                sim.actor_engine,
                vote_record.passed,
                pre_queue_agreements,
                sim.actor_engine.concessions,
                month,
            )
            for name, value in exec_pending.items():
                sim.pending_terms[name] = sim.pending_terms.get(name, 0.0) + value
            agreement_events.extend(exec_events)

    sim.last_effective_policy = policy.model_copy()

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

    # 6.bis Congreso: `congress_support` derivado (ADR 005 secc. 1.3), en vez
    # de la formula de v0.1 (`step_politics` arriba, sin tocar: sigue siendo
    # el fallback con `features.congress = False`).
    if sim.actors_enabled and sim.congress_enabled:
        assert sim.actor_engine is not None
        vigente_agreements = [a for a in sim.actor_engine.agreements if a.status == "vigente"]
        derived_support = derive_congress_support(
            country.parties,
            sim.actor_engine.actors,
            full_state,
            sim.actor_engine.relationships,
            vigente_agreements,
            months_to_election,
            sim.actor_engine.congress_rng,
        )
        full_state = full_state.model_copy(update={"congress_support": derived_support})

    # 7. clamp
    clamped, overflow = clamp_state(full_state, country.ranges)

    # 8. eventos endogenos y fin de partida
    events: list[str] = list(agreement_events)
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
        date=date,
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
    brain_map: dict[str, str] | None = None,
    default_brain: str = DEFAULT_BRAIN,
    llm_temperature: float = 0.4,
    llm_cache_dir: str | None = None,
    congress_enabled: bool = False,
    negotiation_enabled: bool = False,
) -> History:
    """Corre `months` meses (o hasta un fin de partida temprano) y devuelve
    la `History`.

    `actors_enabled` (default `False`, ADR 003): activa los 29 actores por
    reglas + un presidente por reglas (`RuleBasedPresident`) que envuelve
    `policy_rule`. El default de esta *funcion* se mantiene apagado a
    proposito para no romper ningun llamador existente (los 46 tests de
    Fase 1/2 corren `run()`/`Game.new()` sin pedir actores); es
    `republica run` (la CLI) la que activa `features.actors` por defecto y
    ofrece `--no-actors` para apagarlo (ver Notas de implementacion).

    `brain_map`/`default_brain`/`llm_temperature`/`llm_cache_dir` (ADR 004
    secc. 7): idem `new_simulation`, default `"rules"` para todos (cero LLM,
    corrida identica a antes de ADR 004).

    `congress_enabled`/`negotiation_enabled` (ADR 005): default `False` a
    nivel de funcion, mismo criterio que `actors_enabled` de arriba;
    `republica run` los activa por defecto via `country.features`
    (`--no-congress`/`--no-negotiation` los apagan)."""
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
        brain_map=brain_map,
        default_brain=default_brain,
        llm_temperature=llm_temperature,
        llm_cache_dir=llm_cache_dir,
        congress_enabled=congress_enabled,
        negotiation_enabled=negotiation_enabled,
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
        trace_records=sim.trace_records,
        vote_records=sim.vote_records,
        negotiation_records=sim.negotiation_records,
    )
