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
from republica.ai.memory import MemoryStore
from republica.ai.tracing import DecisionTrace, make_run_id
from republica.engine.actions import Action, ActionType
from republica.engine.consequences import (
    ConsequenceContext,
    RelationshipDelta,
    Relationships,
    apply_consequences,
    load_concessions,
    load_consequences,
    resolve_pending_requests,
)
from republica.engine.negotiation import (
    Agreement,
    NegotiationRecord,
    check_actor_compliance,
    run_month_negotiations,
)
from republica.engine.perception import PolicyProposal, build_perception, build_provinces_table
from republica.engine.permissions import (
    Allowed,
    AuthContext,
    Denied,
    Governance,
    authorize_all,
    load_governance,
    load_permissions,
    to_record_dict,
)
from republica.governance import filter_perception
from republica.world.config import Country
from republica.world.economy import Aux
from republica.world.events import ShockAggregate

#: Tipos de accion que generan un pedido pendiente para el mes siguiente
#: (ADR 003 secc. 6/secc. 7: "GRANT_CONCESSION a pedidos del mes anterior").
#: `REQUEST_FUNDS` sigue este camino siempre (ADR 005 no lo toca: solo
#: reemplaza el `NEGOTIATE` simple de Fase 3 por el protocolo de
#: `engine/negotiation.py`, ver `run_actor_turn`); `NEGOTIATE` solo cae aca
#: cuando `features.negotiation = False` (agregado dinamicamente mas abajo).
REQUEST_ACTION_TYPES = (ActionType.REQUEST_FUNDS,)

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
    #: Estado de negociacion (ADR 005 secc. 2), vacio/no usado con
    #: `features.negotiation = False`: todos los `Agreement` alguna vez
    #: formados (`vigente`/`honored`/`broken_*`, ver `engine/negotiation.py`)
    #: y el enfriamiento de 6 meses por actor tras un `broken_by_actor`.
    agreements: list[Agreement] = field(default_factory=list)
    no_renegotiate_until: dict[str, int] = field(default_factory=dict)
    #: `random.Random` propio del subsistema de Congreso (ADR 005 secc. 1.2:
    #: el ruido del `rule_score`), sembrado igual que `actor_rngs` pero con
    #: un id sintetico ("congress") para no compartir secuencia con ningun
    #: actor real.
    congress_rng: random.Random = field(default_factory=lambda: random.Random(0))
    #: `MemoryStore` de todos los actores (ADR 006 secc. 1.2), persistente
    #: mes a mes igual que `relationships`/`agreements`; vacio/no usado con
    #: `features.memory = False`.
    memory_store: MemoryStore = field(default_factory=MemoryStore)
    #: Eventos `agreement_broken:*:actor` de este mes (`check_actor_compliance`,
    #: ADR 005 secc. 2): efecto de lado leido por `engine/simulation.py`
    #: (mismo patron que `last_score`/`last_trace`) para sumarlos a
    #: `MonthRecord.events`.
    last_compliance_events: list[str] = field(default_factory=list)
    #: `Action` de este mes retenidas por `human_approval_required` (ADR 007
    #: secc. 6, deliverable 6): acciones EXECUTE de un actor cuya ficha de
    #: gobernanza pide aprobacion humana, con `auto_approve_execute=False`
    #: (solo en `play`, ver `engine/game.py::Game.pending_human_approvals`).
    #: No pasaron por `authorize_all` este mes (ni autorizadas ni denegadas:
    #: quedan pendientes, mismo patron que `pending_requests`); si el
    #: jugador las aprueba, se re-emiten el mes que viene via
    #: `grant_actions` (`Game.set_human_approvals`).
    last_pending_approvals: list[Action] = field(default_factory=list)


def build_actor_engine(
    seed: int,
    country: Country,
    actors: dict[str, ActorSheet] | None = None,
    *,
    brain_map: dict[str, str] | None = None,
    default_brain: str = DEFAULT_BRAIN,
    llm_temperature: float = 0.4,
    llm_cache_dir: str | None = None,
    memory_enabled: bool = False,
    governance_overrides: dict[str, str] | None = None,
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
    build_decision_actor`).

    `governance_overrides` (ADR 007 secc. 6, deliverable 6): overrides
    `actor.campo=valor` sobre `data/governance.yaml` (`--governance-override`
    de `republica run`, `republica.governance.parse_governance_overrides`),
    p.ej. `{"central_bank.autonomy": "4"}` para el experimento canonico de
    Fase 7 (autonomy 2 vs. 4)."""
    actors = actors if actors is not None else load_actors()
    brain_map = brain_map or {}
    # Se carga ANTES que `decision_actors` (ADR 007 secc. 6, deliverable 6):
    # `RuleBasedActor` necesita la MISMA `Governance` (con overrides ya
    # aplicados) que va a consultar `authorize()`, para que
    # `--governance-override central_bank.autonomy=4` autorice `SET_RATE`
    # Y el actor lo proponga (ver `ai/brains.py::build_decision_actor`,
    # Notas de implementacion).
    governance = load_governance(overrides=governance_overrides)
    decision_actors: dict[str, DecisionActor] = {
        actor_id: build_decision_actor(
            brain_map.get(actor_id, default_brain),
            sheet,
            country,
            seed=seed,
            temperature=llm_temperature,
            cache_dir=llm_cache_dir,
            memory_enabled=memory_enabled,
            governance=governance,
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
        governance=governance,
        permissions=load_permissions(),
        consequence_coeffs=load_consequences(),
        concessions=load_concessions(),
        run_id=make_run_id(seed, country.config_hash),
        congress_rng=make_actor_rng(seed, "congress"),
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
    *,
    date: str = "",
    negotiation_enabled: bool = False,
    congress_enabled: bool = False,
    bloc_cohort_views: dict[str, dict[str, float]] | None = None,
    media_perception_active: bool = False,
    memory_enabled: bool = False,
    term_length: int = 48,
    auto_approve_execute: bool = True,
) -> tuple[list[ActionRecord], dict[str, float], list[NegotiationRecord]]:
    """Pasos 3-5 de ADR 003 secc. 7 (percepciones/decide/authorize/
    consequences), mas la negociacion de ADR 005 secc. 2 (paso 4 de su orden
    de turno, secc. 5): `grant_actions` son las `GRANT_CONCESSION` ya
    decididas por el presidente (regla o humano) para los pedidos del mes
    anterior (`engine.pending_requests`); se autorizan y aplican junto con
    el resto. Devuelve los `ActionRecord` del mes (tambien guardados en
    `engine.last_records`), los `pending_terms` (`shock_*`/`policy_*`) para
    el mes siguiente, y los `NegotiationRecord` de este mes (vacio si
    `negotiation_enabled=False`).

    `negotiation_enabled`/`congress_enabled` (ADR 005, default `False` a
    nivel de funcion para no romper llamadores existentes que no los piden:
    ver `engine/simulation.py`, que los resuelve desde `country.features`):
    con `negotiation_enabled=False`, `NEGOTIATE` sigue el camino simple de
    Fase 3 (queda en `engine.pending_requests`, `RuleBasedPresident.
    decide_grants` lo resuelve el mes que viene). `congress_enabled` solo
    afecta si una concesion otorgada por negociacion requiere ley (ADR 005
    secc. 1.1): sin Congreso, se ejecuta directo (sin votacion), igual que
    Fase 3.

    `date` (hallazgo #12 de REVIEW_001, keyword-only con default `""` para
    no romper llamadores/tests que arman un `ActorEngine` suelto sin fecha
    a mano): la fecha `AAAA-MM` de este mes, para `Perception.date`.

    `bloc_cohort_views`/`media_perception_active` (ADR 005 secc. 3/4,
    default `None`/`False` = sin cohortes: comportamiento identico a antes
    de ADR 005): `bloc_cohort_views` es `{actor_id: cohort_view}` (ver
    `engine/perception.py::build_perception`) para los `social_bloc` con
    cohorte propia -- se arma con el `cohort_state` de *inicio* de mes (ADR
    005 secc. 5 paso 3, antes de que este mismo mes lo actualice medios/
    cohortes en los pasos 8-9). `media_perception_active` pasa a
    `ConsequenceContext` (ver `engine/consequences.py`).

    `auto_approve_execute` (ADR 007 secc. 6, deliverable 6, default `True`):
    con `True` (siempre en `run()`/eval -- no hay jugador que responda un
    dilema), una accion EXECUTE de un actor con `human_approval_required`
    se autoriza en el mismo mes, igual que cualquier otra (comportamiento
    identico a antes de ADR 007). Con `False` (solo `play`, via
    `Simulation.auto_approve_governance`), esas acciones se retienen en
    `engine.last_pending_approvals` en vez de pasar a `authorize_all` este
    mes; `Game`/`cli.py::play` las presenta como un dilema Si/No."""
    provinces_table = build_provinces_table(state, policy, country.provinces, agg)
    parties_by_id = {p.id: p for p in country.parties}

    all_actions: list[Action] = list(grant_actions)
    pending_approvals: list[Action] = []
    scores: dict[str, dict[str, float]] = {}
    traces: list[DecisionTrace] = []

    for actor_id, sheet in engine.actors.items():
        if sheet.role == "president":
            continue
        cohort_view = (
            (bloc_cohort_views or {}).get(actor_id) if sheet.role == "social_bloc" else None
        )
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
            date=date,
            relationships=engine.relationships,
            agg=agg,
            cohort_view=cohort_view,
            memory_store=engine.memory_store if memory_enabled else None,
            memory_enabled=memory_enabled,
        )
        # ADR 007 secc. 6: `read` filtra la `Perception` ANTES de que el
        # actor decida (regla o LLM por igual) -- con el `read` default de
        # `data/governance.yaml` (todas las categorias del rol) esto es un
        # no-op, ver `republica.governance.filter_perception`.
        gov = engine.governance.for_actor(actor_id)
        perception = filter_perception(sheet, perception, gov)
        decision_actor = engine.decision_actors[actor_id]
        actions = decision_actor.decide(perception, engine.actor_rngs[actor_id])
        last_score = getattr(decision_actor, "last_score", None)
        if last_score is not None:
            scores[actor_id] = last_score.as_dict()
        last_trace = getattr(decision_actor, "last_trace", None)
        if last_trace is not None:
            last_trace.run_id = engine.run_id
            traces.append(last_trace)
        if not auto_approve_execute and gov.human_approval_required:
            for action in actions:
                if action.type.value in gov.execute:
                    pending_approvals.append(action)
                else:
                    all_actions.append(action)
        else:
            all_actions.extend(actions)

    engine.last_pending_approvals = pending_approvals

    auth_ctx = AuthContext(
        state=state,
        month=month,
        parties_by_id=parties_by_id,
        governance=engine.governance,
        cooldowns=engine.cooldowns,
        permissions=engine.permissions,
        term_length=term_length,
    )
    allowed, denied = authorize_all(all_actions, engine.actors, auth_ctx)

    cons_ctx = ConsequenceContext(
        state=state,
        policy=policy,
        parties_by_id=parties_by_id,
        coeffs=engine.consequence_coeffs,
        concessions=engine.concessions,
        media_perception_active=media_perception_active,
    )
    # Una sola pasada (hallazgo #9 de REVIEW_001): antes se llamaba
    # `apply_consequences` una vez para todas las `allowed` (el agregado
    # "real", `pending_terms`/`rel_deltas`) y de nuevo, accion por accion,
    # solo para loguear el desglose de cada `ActionRecord.consequences`. Como
    # `apply_consequences` es lineal -- cada accion aporta sus terminos
    # independientemente, via `add()` -- calcularlo accion por accion una
    # sola vez y sumar da exactamente el mismo agregado, sin recomputar cada
    # accion dos veces ni depender de `id(action)` (fragil: un `id()` de
    # Python puede reciclarse) para saber cual resultado es de cual accion:
    # `per_action_results` queda alineado por posicion con `allowed`.
    pending_terms: dict[str, float] = {}
    rel_deltas: list[RelationshipDelta] = []
    per_action_results: list[tuple[dict[str, float], list[RelationshipDelta]]] = []
    for al in allowed:
        one_pending, one_rel, _ = apply_consequences([al.action], engine.actors, cons_ctx)
        for term, value in one_pending.items():
            pending_terms[term] = pending_terms.get(term, 0.0) + value
        rel_deltas.extend(one_rel)
        per_action_results.append((one_pending, one_rel))

        if al.action.type is ActionType.GRANT_CONCESSION:
            # Cooldown de 6 meses por (actor, concesion) despues de una
            # concesion otorgada (hallazgo #5 de REVIEW_001, documentado en
            # `RuleBasedActor`): sin esto, un actor podia volver a pedir en
            # `NEGOTIATE` la misma concesion que acaba de recibir.
            recipient = engine.decision_actors.get(al.action.params["to"])
            note_grant = getattr(recipient, "note_concession_granted", None)
            if note_grant is not None:
                note_grant(al.action.params["concession"], month)

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

    def _make_record(result: Allowed | Denied, per_action: dict) -> ActionRecord:
        action = result.action
        return ActionRecord(
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

    records: list[ActionRecord] = []
    for al, (one_pending, one_rel) in zip(allowed, per_action_results, strict=True):
        # El efecto relacional de una accion no siempre tiene a su actor del
        # lado `a` del par (hallazgo #9): un `GRANT_CONCESSION` lo emite
        # `president`, pero el delta de relacion es `(destinatario,
        # president, +N)` -- `president` esta del lado `b`. Se matchea
        # `action.actor_id` contra cualquiera de los dos lados y se guarda
        # "la otra punta" como clave.
        rel_for_action: dict[str, float] = {}
        for a2, b, d in one_rel:
            if a2 == al.action.actor_id:
                rel_for_action[b] = d
            elif b == al.action.actor_id:
                rel_for_action[a2] = d
        per_action = {**one_pending}
        if rel_for_action:
            per_action["relationships"] = rel_for_action
        records.append(_make_record(al, per_action))
    for den in denied:
        records.append(_make_record(den, {}))

    request_types = (
        REQUEST_ACTION_TYPES
        if negotiation_enabled
        else (*REQUEST_ACTION_TYPES, ActionType.NEGOTIATE)
    )
    engine.pending_requests = [a.action for a in allowed if a.action.type in request_types]
    # `engine.last_aux` se actualiza desde `advance_month` con el `Aux` real
    # de este mes (recien se conoce despues de `step_economy`), para que el
    # mes que viene las percepciones lo vean (ver Notas de implementacion).
    engine.last_records = records

    # Negociacion (ADR 005 secc. 2, paso 4 del orden de turno secc. 5):
    # corre sobre los `NEGOTIATE` autorizados este mes (con
    # `negotiation_enabled=False`, ya quedaron en `engine.pending_requests`
    # arriba, camino de Fase 3). El cumplimiento de un actor
    # (`broken_by_actor`) se chequea aca tambien, con los `records` de este
    # mismo mes ya completos (necesita saber si el actor voto en contra
    # igual pese a tener un acuerdo vigente).
    negotiation_records: list[NegotiationRecord] = []
    if negotiation_enabled:
        negotiate_requests = [a.action for a in allowed if a.action.type is ActionType.NEGOTIATE]
        negotiation_records, negotiation_pending = run_month_negotiations(
            engine, negotiate_requests, country, month, congress_enabled
        )
        for term, value in negotiation_pending.items():
            pending_terms[term] = pending_terms.get(term, 0.0) + value
        engine.last_compliance_events = check_actor_compliance(engine, records, month)
    else:
        engine.last_compliance_events = []

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

    return records, pending_terms, negotiation_records
