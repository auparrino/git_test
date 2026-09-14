"""Orquesta el turno de los actores (ADR 003 secc. 7, pasos 3-6): perceptions
-> decide -> authorize -> consequences. Se llama desde
`engine/simulation.py::advance_month` cuando `Simulation.actors_enabled`,
justo despues de que el presidente (regla o humano) decide la `Policy` del
mes (paso 2) y antes de la economia (paso 7)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from republica.actors.llm_based import LLMActor
from republica.actors.rule_based import RuleBasedActor, make_actor_rng
from republica.actors.sheet import ActorSheet, load_actors
from republica.ai.brains import DEFAULT_BRAIN, build_decision_actor
from republica.ai.tracing import DecisionTrace, make_run_id
from republica.engine.actions import Action, ActionType
from republica.engine.consequences import (
    ConsequenceContext,
    Relationships,
    apply_consequences,
    load_concessions,
    load_consequences,
    resolve_pending_requests,
)
from republica.engine.perception import PolicyProposal, build_perception, build_provinces_table
from republica.engine.permissions import (
    AuthContext,
    Governance,
    authorize_all,
    load_governance,
    load_permissions,
    to_record_dict,
)
from republica.world.config import Country
from republica.world.economy import Aux
from republica.world.events import ShockAggregate

#: Tipos de accion que generan un pedido pendiente para el mes siguiente
#: (ADR 003 secc. 6/secc. 7: "GRANT_CONCESSION a pedidos del mes anterior").
REQUEST_ACTION_TYPES = (ActionType.REQUEST_FUNDS, ActionType.NEGOTIATE)

_ZERO_AUX = Aux(
    r_real=0.0,
    r_gap=0.0,
    g_m=0.0,
    demand_gap=0.0,
    deficit=0.0,
    u_gap=0.0,
    reserves_gap=0.0,
    interest_cost=0.0,
    de=0.0,
    excess=0.0,
    intervention_usd=0.0,
    revenue=0.0,
    spending=0.0,
)


@dataclass
class ActionRecord:
    """`ActionRecord` del log (ADR 003 secc. 8), una por accion (autorizada
    o denegada)."""

    month: int
    actor: str
    type: str
    params: dict
    target: str | None
    reason: str
    authorized: bool
    denied_reason: str | None
    score: dict[str, float] | None
    consequences: dict

    def to_dict(self) -> dict:
        return {
            "kind": "action",
            "month": self.month,
            "actor": self.actor,
            "type": self.type,
            "params": self.params,
            "target": self.target,
            "reason": self.reason,
            "authorized": self.authorized,
            "denied_reason": self.denied_reason,
            "score": self.score,
            "consequences": self.consequences,
        }


#: Un actor "de decision" implementa `decide(perception, rng) ->
#: list[Action]` (ADR 003 secc. 6 / ADR 004 secc. 1): o bien por reglas, o
#: bien respaldado por un LLM (real u otro `FakeBackend`, ADR 004).
DecisionActor = RuleBasedActor | LLMActor


@dataclass
class ActorEngine:
    """Estado persistente del subsistema de actores: construido una vez por
    partida/corrida y reusado mes a mes (los `random.Random` por actor y las
    `Relationships` mutan con el tiempo; el resto es config cacheada).

    `decision_actors` (ADR 004 secc. 7, deliverable 6: "cada actor obtiene
    el cerebro de la tabla") reemplaza al antiguo `rule_actors`: cada valor
    es un `RuleBasedActor` o un `LLMActor` segun `brains.yaml`/`--brain`,
    pero ambos comparten la misma interfaz `decide(perception, rng)` asi que
    `run_actor_turn` no distingue el tipo."""

    actors: dict[str, ActorSheet]
    decision_actors: dict[str, DecisionActor]
    actor_rngs: dict[str, random.Random]
    relationships: Relationships
    governance: Governance
    permissions: dict
    consequence_coeffs: dict
    concessions: dict
    run_id: str = ""
    cooldowns: dict[tuple[str, ActionType], int] = field(default_factory=dict)
    pending_requests: list[Action] = field(default_factory=list)
    last_aux: Aux = field(default_factory=lambda: _ZERO_AUX)
    last_records: list[ActionRecord] = field(default_factory=list)
    #: `DecisionTrace` de los `LLMActor` que decidieron el ultimo mes (ADR
    #: 004 secc. 6); vacio si todos los actores son por reglas (default:
    #: `RuleBasedActor` no produce trazas, no llama a ningun backend).
    last_traces: list[DecisionTrace] = field(default_factory=list)


def build_actor_engine(
    seed: int,
    country: Country,
    actors: dict[str, ActorSheet] | None = None,
    *,
    brain_map: dict[str, str] | None = None,
    default_brain: str = DEFAULT_BRAIN,
    llm_temperature: float = 0.4,
    llm_cache_dir: str | None = None,
) -> ActorEngine:
    """Arma un `ActorEngine` nuevo: carga las 29 fichas (o las que se pasen,
    para tests), un actor de decision por rol no-`president` y un RNG propio
    por actor (ADR 003 secc. 7: `random.Random(hash(seed, actor_id))`, ver
    `rule_based.make_actor_rng`), y siembra `Relationships` desde las
    fichas.

    `brain_map`/`default_brain` (ADR 004 secc. 7, default `"rules"` para
    todos -- cero LLM, comportamiento identico a antes de ADR 004): que
    cerebro usa cada actor. `llm_temperature`/`llm_cache_dir` solo importan
    para actores cuyo cerebro no sea `"rules"` (`ai/brains.py::
    build_decision_actor`)."""
    actors = actors if actors is not None else load_actors()
    brain_map = brain_map or {}
    decision_actors: dict[str, DecisionActor] = {
        actor_id: build_decision_actor(
            brain_map.get(actor_id, default_brain),
            sheet,
            country,
            seed=seed,
            temperature=llm_temperature,
            cache_dir=llm_cache_dir,
        )
        for actor_id, sheet in actors.items()
        if sheet.role != "president"
    }
    actor_rngs = {actor_id: make_actor_rng(seed, actor_id) for actor_id in actors}
    return ActorEngine(
        actors=actors,
        decision_actors=decision_actors,
        actor_rngs=actor_rngs,
        relationships=Relationships.from_actors(actors),
        governance=load_governance(),
        permissions=load_permissions(),
        consequence_coeffs=load_consequences(),
        concessions=load_concessions(),
        run_id=make_run_id(seed, country.config_hash),
    )


def run_actor_turn(
    engine: ActorEngine,
    country: Country,
    state,
    policy,
    agg: ShockAggregate,
    active_shock_ids: list[str],
    recent_events: list[str],
    month: int,
    months_to_election: int,
    proposal: PolicyProposal,
    grant_actions: list[Action],
) -> tuple[list[ActionRecord], dict[str, float]]:
    """Pasos 3-6 de ADR 003 secc. 7. `grant_actions` son las
    `GRANT_CONCESSION` ya decididas por el presidente (regla o humano) para
    los pedidos del mes anterior (`engine.pending_requests`); se autorizan y
    aplican junto con el resto. Devuelve los `ActionRecord` del mes (tambien
    guardados en `engine.last_records`) y los `pending_terms`
    (`shock_*`/`policy_*`) para el mes siguiente."""
    provinces_table = build_provinces_table(state, policy, country.provinces, agg)
    parties_by_id = {p.id: p for p in country.parties}

    all_actions: list[Action] = list(grant_actions)
    scores: dict[str, dict[str, float]] = {}
    traces: list[DecisionTrace] = []

    for actor_id, sheet in engine.actors.items():
        if sheet.role == "president":
            continue
        perception = build_perception(
            sheet,
            state,
            engine.last_aux,
            proposal,
            active_shock_ids,
            recent_events,
            month,
            months_to_election,
            provinces_table,
            country.parties,
            policy=policy,
        )
        decision_actor = engine.decision_actors[actor_id]
        actions = decision_actor.decide(perception, engine.actor_rngs[actor_id])
        last_score = getattr(decision_actor, "last_score", None)
        if last_score is not None:
            scores[actor_id] = last_score.as_dict()
        last_trace = getattr(decision_actor, "last_trace", None)
        if last_trace is not None:
            last_trace.run_id = engine.run_id
            traces.append(last_trace)
        all_actions.extend(actions)

    auth_ctx = AuthContext(
        state=state,
        month=month,
        parties_by_id=parties_by_id,
        governance=engine.governance,
        cooldowns=engine.cooldowns,
        permissions=engine.permissions,
    )
    allowed, denied = authorize_all(all_actions, engine.actors, auth_ctx)
    allowed_ids = {id(a.action) for a in allowed}

    cons_ctx = ConsequenceContext(
        state=state,
        policy=policy,
        parties_by_id=parties_by_id,
        coeffs=engine.consequence_coeffs,
        concessions=engine.concessions,
    )
    allowed_actions = [a.action for a in allowed]
    pending_terms, rel_deltas, _events = apply_consequences(
        allowed_actions, engine.actors, cons_ctx
    )

    granted_ids = {
        a.action.params["to"] for a in allowed if a.action.type is ActionType.GRANT_CONCESSION
    }
    rel_deltas = rel_deltas + resolve_pending_requests(
        engine.pending_requests, granted_ids, engine.consequence_coeffs
    )

    for a, b, delta in rel_deltas:
        engine.relationships.bump(a, b, delta)
    decay_cfg = engine.consequence_coeffs["relationships"]
    engine.relationships.decay(decay_cfg["decay_rate"], decay_cfg["decay_target"])

    records: list[ActionRecord] = []
    for result in [*allowed, *denied]:
        action = result.action
        per_action: dict = {}
        if id(action) in allowed_ids:
            one_pending, one_rel, _ = apply_consequences([action], engine.actors, cons_ctx)
            rel_for_action = {b: d for a2, b, d in one_rel if a2 == action.actor_id}
            per_action = {**one_pending}
            if rel_for_action:
                per_action["relationships"] = rel_for_action
        records.append(
            ActionRecord(
                month=month,
                actor=action.actor_id,
                type=action.type.value,
                params=action.params,
                target=action.target,
                reason=action.reason,
                score=scores.get(action.actor_id),
                consequences=per_action,
                **to_record_dict(result),
            )
        )

    engine.pending_requests = [a.action for a in allowed if a.action.type in REQUEST_ACTION_TYPES]
    # `engine.last_aux` se actualiza desde `advance_month` con el `Aux` real
    # de este mes (recien se conoce despues de `step_economy`), para que el
    # mes que viene las percepciones lo vean (ver Notas de implementacion).
    engine.last_records = records

    # Completa cada `DecisionTrace` (ADR 004 secc. 6) con lo que solo se supo
    # despues de `authorize_all`/`apply_consequences`: cada actor con un
    # `LLMActor` decide una sola vez por mes, asi que todos los
    # `ActionRecord` de ese `actor_id` este mes vienen de esa unica llamada
    # (ver `ai/tracing.py::DecisionTrace`).
    if traces:
        records_by_actor: dict[str, list[ActionRecord]] = {}
        for rec in records:
            records_by_actor.setdefault(rec.actor, []).append(rec)
        for trace in traces:
            for rec in records_by_actor.get(trace.actor_id, []):
                rec_dict = rec.to_dict()
                if rec.authorized:
                    trace.actions_authorized.append(rec_dict)
                    if rec.consequences:
                        trace.consequences[rec.type] = rec.consequences
                else:
                    trace.actions_denied.append(rec_dict)
    engine.last_traces = traces

    return records, pending_terms
