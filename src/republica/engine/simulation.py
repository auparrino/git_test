"""Motor de simulacion: orden de turno determinista (seccion 7 del spec)."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from republica.actors.president_rules import (
    RuleBasedPresident,
    apply_pending_policy_delta,
    compute_policy_proposal,
)
from republica.actors.rule_based import economic_policy_direction, load_signatures
from republica.actors.sheet import ActorSheet
from republica.ai.brains import DEFAULT_BRAIN
from republica.ai.memory import MemoryContext, MemoryEvent, generate_month_memories
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
from republica.engine.scheduler import (
    ActionRecord,
    ActorEngine,
    build_actor_engine,
    refresh_decision_actor_parties,
    run_actor_turn,
)
from republica.world.bimonetary import (
    BimonetaryCoefficients,
    init_external_state,
    step_bimonetary,
)
from republica.world.cohorts import (
    Cohort,
    CohortState,
    cohort_by_bloc_actor,
    init_cohort_state,
    load_cohorts,
    step_cohorts,
    weighted_perceived_inflation,
)
from republica.world.config import Country, load_country
from republica.world.economy import (
    apply_historical_shock_effects,
    finalize_exogenous,
    step_economy,
    step_exogenous,
)
from republica.world.elections import (
    PROMISE_WINDOW_MONTHS,
    ElectionResult,
    LoyaltyTable,
    build_post_election_actors,
    build_post_election_parties,
    honeymoon_approval,
    is_election_month,
    load_loyalty,
    load_province_weights,
    reseed_president_relationships,
    run_election,
)
from republica.world.events import (
    ActiveShock,
    EndogenousTracker,
    ShockAggregate,
    ShockCatalog,
    build_catalog,
    check_forced_devaluation,
    check_termination,
)
from republica.world.perception import (
    AUDIENCE_MAX,
    AUDIENCE_MIN,
    TREND_WINDOW_MONTHS,
    MediaAction,
    PerceptionRecord,
    compute_bias,
    drift_audience,
    load_media_consumption,
    reputation_penalty,
    step_perception,
    sync_to_real,
    update_contradiction_streak,
)
from republica.world.perception import (
    perception_gap as compute_perception_gap,
)
from republica.world.politics import step_politics
from republica.world.provinces import ProvinceRecord, compute_provinces
from republica.world.regime import (
    RegimeCalendar,
    RegimeState,
    congress_active,
    elections_allowed,
    regime_effects_on_state,
    step_regime,
)
from republica.world.society import step_society
from republica.world.state import Exogenous, Policy, WorldState, clamp, clamp_state

OUTCOMES = ("survived", "collapse", "hyperinflation", "reelected", "defeated")


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
    #: Estado de cada cohorte al cierre del mes (ADR 005 secc. 3, deliverable
    #: 1): `{cohort_id: {approval_c, sentiment_c, perceived_inflation_c,
    #: perceived_unemployment_c}}` (`world/cohorts.py::CohortState.to_dict`).
    #: Vacio con `features.cohorts = False` -- y, por `to_dict()` (abajo),
    #: NI SIQUIERA aparece como clave en ese caso: mismo patron que
    #: `action_records`/`vote_records` (ADR 003/005), para que el JSONL siga
    #: siendo byte a byte identico al de antes de este commit con la
    #: feature apagada (ver Notas de implementacion).
    cohorts: dict[str, dict[str, float]] = field(default_factory=dict)
    #: `regime_mode` (ADR 011 secc. 3, `features.regime`): `""` (y AUSENTE de
    #: `to_dict()`, mismo patron que `cohorts`) sin `regime_calendar` en
    #: `run()` -- JSONL identico al de antes del ADR 011 con el feature
    #: apagado. Con el feature prendido: uno de `world/regime.py::
    #: REGIME_MODES`.
    regime_mode: str = ""
    #: Bloque bimonetario (ADR 011 secc. 5, `features.bimonetary`):
    #: `world/bimonetary.py::ExternalState.to_dict()`. `{}` (AUSENTE de
    #: `to_dict()`) sin `bimonetary_coefficients` en `run()`.
    external: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        if not d["cohorts"]:
            del d["cohorts"]
        if not d["regime_mode"]:
            del d["regime_mode"]
        if not d["external"]:
            del d["external"]
        return d


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
    #: `PerceptionRecord` (ADR 005 secc. 4, `kind: "perception"`), vacio con
    #: `features.cohorts` apagado (mismo patron que `vote_records`/
    #: `negotiation_records`: con todos los sidecars vacios, `to_jsonl()`
    #: produce el mismo texto que antes de este commit).
    perception_records: list[PerceptionRecord] = field(default_factory=list)
    #: `MemoryEvent` (ADR 006 secc. 1.2, `kind: "memory"`), acumuladas mes a
    #: mes igual que `perception_records`; vacio con `features.memory`
    #: apagado (mismo patron: con todos los sidecars vacios, `to_jsonl()`
    #: produce el mismo texto que antes de ADR 006).
    memory_records: list[MemoryEvent] = field(default_factory=list)
    #: `ElectionResult` (ADR 006 secc. 2.4, `kind: "election"`), vacio con
    #: `features.elections` apagado.
    election_records: list[ElectionResult] = field(default_factory=list)

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
        perceptions_by_month: dict[int, list[PerceptionRecord]] = {}
        for p in self.perception_records:
            perceptions_by_month.setdefault(p.month, []).append(p)
        memories_by_month: dict[int, list[MemoryEvent]] = {}
        for me in self.memory_records:
            memories_by_month.setdefault(me.turn, []).append(me)
        elections_by_month: dict[int, list[ElectionResult]] = {}
        for er in self.election_records:
            elections_by_month.setdefault(er.month, []).append(er)

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
            for p in perceptions_by_month.get(r.month_index, []):
                lines.append(json.dumps(p.to_dict(), ensure_ascii=False))
            for me in memories_by_month.get(r.month_index, []):
                lines.append(json.dumps(me.to_dict(), ensure_ascii=False))
            for er in elections_by_month.get(r.month_index, []):
                lines.append(json.dumps(er.to_dict(), ensure_ascii=False))
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
            "perception_records": [p.to_dict() for p in self.perception_records],
            "memory_records": [m.to_dict() for m in self.memory_records],
            "election_records": [e.to_dict() for e in self.election_records],
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
    #: ADR 005 secc. 3/4 (default `False`, mismo criterio que arriba):
    #: `cohorts_enabled` es independiente de `actors_enabled` (a diferencia
    #: de `congress`/`negotiation`) -- es una extension de las formulas de
    #: `world/`, no del subsistema de actores institucionales; corre igual
    #: sin actores (ver Notas de implementacion, homogeneidad con v0.1).
    #: `media_enabled` solo tiene efecto si `cohorts_enabled` Y
    #: `actors_enabled` tambien lo estan (sin cohortes no hay donde sesgar
    #: percepcion; sin actores no hay `PUBLISH_STORY` que emitir).
    cohorts_enabled: bool = False
    media_enabled: bool = False
    cohorts: list[Cohort] = field(default_factory=list)
    cohort_state: dict[str, CohortState] = field(default_factory=dict)
    #: `{cohort_id: {outlet_id: share}}` (`data/media_consumption.csv`).
    media_consumption: dict[str, dict[str, float]] = field(default_factory=dict)
    #: `influence.public` de cada medio, mutable (ADR 005 secc. 4.5: "no en
    #: la ficha" -- la ficha estatica sigue sirviendo para el resto de los
    #: mecanismos de ADR 003, p.ej. el `scale_by` de `PUBLIC_STATEMENT`).
    outlet_influence: dict[str, float] = field(default_factory=dict)
    #: Racha de meses consecutivos que cada medio publico un frame
    #: contradictorio (ADR 005 secc. 4.5, revisado v0.8 -- ver
    #: `world/perception.py::update_contradiction_streak`). `{}` con
    #: `media_enabled=False` (nunca se llena).
    outlet_contradiction_streak: dict[str, int] = field(default_factory=dict)
    #: Deuda de reputacion ACUMULADA (suma de todos los `-0.03` cobrados en
    #: la corrida, nunca decrece -- ADR 005 secc. 4.5, revisado v0.8): un
    #: medio que mintio 3+ meses seguidos no vuelve a su techo original de
    #: `AUDIENCE_MAX` aunque despues se alinee siempre con la realidad (ver
    #: `world/perception.py::reputation_penalty`/Notas de implementacion --
    #: sin esto, la deriva de audiencia normal (secc. 4.5) termina
    #: reconvergiendo a `AUDIENCE_MAX` de nuevo en unos pocos meses de
    #: alineacion, borrando cualquier diferencia entre medios). `{}` con
    #: `media_enabled=False`.
    outlet_reputation_debt: dict[str, float] = field(default_factory=dict)
    #: Ventana movil (ultimos `TREND_WINDOW_MONTHS` meses, mas viejo primero)
    #: de inflacion/desempleo/crecimiento REALES, para el chequeo de
    #: contradiccion de secc. 4.5 (revisado v0.8): un solo mes de delta es
    #: demasiado ruidoso (con `exogenous_noise=True` un mes de inflacion
    #: "subiendo" seguido de uno "bajando" es la norma, no la excepcion --
    #: ver Notas de implementacion) para sostener una racha de 3+ meses
    #: consecutivos. Vacio con `media_enabled=False`.
    recent_inflation: list[float] = field(default_factory=list)
    recent_unemployment: list[float] = field(default_factory=list)
    recent_gdp_growth: list[float] = field(default_factory=list)
    perception_records: list[PerceptionRecord] = field(default_factory=list)
    #: ADR 006 (default `False`, mismo criterio que el resto de las
    #: features): `memory_enabled` solo tiene efecto si `actors_enabled`
    #: tambien lo esta (el `MemoryStore` vive en `ActorEngine`).
    #: `elections_enabled` ademas requiere `cohorts_enabled` (el modelo de
    #: intencion de voto de ADR 006 secc. 2.2 esta construido sobre
    #: cohortes) -- ver `new_simulation`.
    memory_enabled: bool = False
    elections_enabled: bool = False
    memory_records: list[MemoryEvent] = field(default_factory=list)
    election_records: list[ElectionResult] = field(default_factory=list)
    loyalty_table: LoyaltyTable = field(default_factory=LoyaltyTable)
    #: `{cohort_id: {province_id: peso}}` (calibracion: `data/
    #: cohort_provinces.csv`, opcional) para `regional_bonus_c,p` (secc.
    #: 2.2, `world/elections.py::compute_regional_bonus`); `{}` deja
    #: `regional_bonus_c,p = 0` para todas (mismo comportamiento que antes
    #: de la calibracion).
    province_weights_table: dict[str, dict[str, float]] = field(default_factory=dict)
    #: `campaign_p` acumulado por partido y foco (ADR 006 secc. 2.5:
    #: `CAMPAIGN(focus, intensity)` -> `campaign_p += 0.5 * intensity`),
    #: reseteado en cada transicion de gobierno.
    campaign_state: dict[str, dict[str, float]] = field(default_factory=dict)
    #: `PROMISE` activas (ADR 006 secc. 2.5): `{month, actor, target, text,
    #: direction}`, se van del todo (`promise_broken` o expiracion de la
    #: ventana de 6 meses) en `_check_promises`.
    promises: list[dict[str, Any]] = field(default_factory=list)
    #: `loyalty -0.1` por `promise_broken` (ADR 006 secc. 2.5, literal):
    #: ajuste que se SUMA a `cohorts_loyalty.csv` en tiempo de lectura
    #: (`world/elections.py::compute_vote_intention(loyalty_adjustments=...)`),
    #: sin reescribir el CSV.
    loyalty_adjustments: dict[tuple[str, str], float] = field(default_factory=dict)
    #: ADR 007 secc. 6, deliverable 6 (default `True`): si las acciones
    #: EXECUTE de un actor con `human_approval_required` se autorizan solas
    #: (`run()`, sin jugador) o se retienen para un dilema Si/No
    #: (`engine/game.py::Game.new()` lo pone en `False`; ver
    #: `engine/scheduler.py::run_actor_turn(auto_approve_execute=...)`).
    auto_approve_governance: bool = True


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
    cohorts_enabled: bool = False,
    media_enabled: bool = False,
    cohorts: list[Cohort] | None = None,
    media_consumption: dict[str, dict[str, float]] | None = None,
    memory_enabled: bool = False,
    elections_enabled: bool = False,
    loyalty_table: LoyaltyTable | None = None,
    province_weights_table: dict[str, dict[str, float]] | None = None,
    governance_overrides: dict[str, str] | None = None,
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
    `actors_enabled` tambien lo esta.

    `cohorts_enabled` (ADR 005 secc. 3, default `False` a nivel de funcion):
    a diferencia de `congress_enabled`/`negotiation_enabled`, NO se apaga
    automaticamente si `actors_enabled=False` (ver Notas de implementacion:
    es una extension de `world/`, corre sobre `cohorts`/`Policy`/`WorldState`
    solos). `cohorts`/`media_consumption` (`None` = cargar de `data/`, para
    tests que quieren una tabla homogenea sin tocar el disco) solo se leen
    si `cohorts_enabled`. `media_enabled` (ADR 005 secc. 4) se resuelve
    contra `cohorts_enabled AND actors_enabled` (sin cohortes no hay donde
    sesgar percepcion; sin actores no hay `PUBLISH_STORY`)."""
    country = country or load_country()
    catalog = ShockCatalog(build_catalog(country.shocks))
    resolved_policy_rule = policy_rule or ConstantPolicy(country.default_policy)
    resolved_memory_enabled = memory_enabled and actors_enabled
    actor_engine = (
        build_actor_engine(
            seed,
            country,
            actors,
            brain_map=brain_map,
            default_brain=default_brain,
            llm_temperature=llm_temperature,
            llm_cache_dir=llm_cache_dir,
            memory_enabled=resolved_memory_enabled,
            governance_overrides=governance_overrides,
        )
        if actors_enabled
        else None
    )
    president_rule = (
        RuleBasedPresident(policy_rule=resolved_policy_rule)
        if actors_enabled and rule_based_president
        else None
    )
    resolved_cohorts = (
        (cohorts if cohorts is not None else load_cohorts()) if cohorts_enabled else []
    )
    resolved_media_enabled = media_enabled and cohorts_enabled and actors_enabled
    # ADR 006 secc. 2: el modelo de intencion de voto (secc. 2.2) esta
    # construido sobre cohortes; sin `cohorts_enabled` no hay `CohortState`
    # que alimentarle (ver Notas de implementacion).
    resolved_elections_enabled = elections_enabled and actors_enabled and cohorts_enabled
    resolved_loyalty_table = (
        (loyalty_table if loyalty_table is not None else load_loyalty())
        if resolved_elections_enabled
        else LoyaltyTable()
    )
    resolved_province_weights_table = (
        (province_weights_table if province_weights_table is not None else load_province_weights())
        if resolved_elections_enabled
        else {}
    )
    resolved_consumption = (
        (media_consumption if media_consumption is not None else load_media_consumption())
        if cohorts_enabled
        else {}
    )
    outlet_influence = (
        {
            aid: clamp(sheet.influence.public, AUDIENCE_MIN, AUDIENCE_MAX)
            for aid, sheet in actor_engine.actors.items()
            if sheet.role == "media"
        }
        if actor_engine is not None
        else {}
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
        cohorts_enabled=cohorts_enabled,
        media_enabled=resolved_media_enabled,
        cohorts=resolved_cohorts,
        cohort_state=init_cohort_state(resolved_cohorts, country.initial_state)
        if cohorts_enabled
        else {},
        media_consumption=resolved_consumption,
        outlet_influence=outlet_influence,
        memory_enabled=resolved_memory_enabled,
        elections_enabled=resolved_elections_enabled,
        loyalty_table=resolved_loyalty_table,
        province_weights_table=resolved_province_weights_table,
    )


def _format_date(start_year: int, start_month: int, month_index: int) -> str:
    total = (start_month - 1) + (month_index - 1)
    year = start_year + total // 12
    month = total % 12 + 1
    return f"{year:04d}-{month:02d}"


def _run_election(
    sim: Simulation,
    clamped: WorldState,
    month: int,
    country: Country,
    provinces: list[ProvinceRecord],
) -> tuple[WorldState, ElectionResult]:
    """Corre la eleccion de este mes (ADR 006 secc. 2.2/2.3) y aplica la
    transicion de gobierno (secc. 2.4). Muta `sim.actor_engine`/
    `sim.country`/`sim.cohort_state`/`sim.campaign_state` segun corresponda;
    devuelve el `WorldState` con la aprobacion de luna de miel/continuidad
    ya aplicada (secc. 2.4, literal) y el `ElectionResult`.

    `provinces` (calibracion, secc. 2.2 `regional_bonus_c,p`):
    `income_p`/`unemployment_p` de este mes (`world/provinces.py::
    compute_provinces`, ya calculado por el llamador). Junto con
    `country.provinces` (gobernador de cada una) y `sim.province_weights_table`
    (`data/cohort_provinces.csv`) arma el bono regional; si
    `province_weights_table` esta vacio (sin el CSV) el bono queda en 0 para
    todos, mismo comportamiento que antes de esta calibracion.

    `Δreal_wage_12m`/`Δunemployment_12m` (secc. 2.2) se calculan contra el
    `MonthRecord` de 12 meses atras si hay suficiente historia (si no, deltas
    en 0 -- una eleccion en los primeros 12 meses de una corrida corta no
    tiene "12 meses atras" reales, documentado en Notas de implementacion)."""
    assert sim.actor_engine is not None
    if len(sim.records) >= 12:
        then = sim.records[-12].state
        then_wage = then["real_wage"]
        delta_real_wage_pct_12m = (
            (clamped.real_wage - then_wage) / then_wage * 100.0 if then_wage else 0.0
        )
        delta_unemployment_12m = clamped.unemployment - then["unemployment"]
    else:
        delta_real_wage_pct_12m = 0.0
        delta_unemployment_12m = 0.0

    result = run_election(
        month,
        sim.cohorts,
        sim.cohort_state,
        country.parties,
        clamped.government_approval,
        sim.loyalty_table,
        sim.rng,
        delta_real_wage_pct_12m=delta_real_wage_pct_12m,
        delta_unemployment_12m=delta_unemployment_12m,
        campaign_state=sim.campaign_state,
        memory_store=sim.actor_engine.memory_store if sim.memory_enabled else None,
        loyalty_adjustments=sim.loyalty_adjustments,
        provinces=country.provinces,
        province_records=provinces,
        province_weights=sim.province_weights_table,
        national_unemployment=clamped.unemployment,
    )

    # Bancas/`in_government` de la proxima temporada, siempre (ADR 006 secc.
    # 2.4, literal: "las bancas de la eleccion reemplazan las de
    # parties.json para el proximo mandato") -- pase lo que pase con el
    # presidente.
    new_parties = build_post_election_parties(result, country.parties)
    new_coalition_seats = next(
        (p.seats for p in new_parties if p.in_government), country.coalition_seats
    )
    sim.country = country.model_copy(
        update={"parties": new_parties, "coalition_seats": new_coalition_seats}
    )
    # Hallazgo #1 de REVIEW_002: refresca `parties_by_id` de cada
    # `decision_actor` con las `new_parties` recien calculadas -- SIEMPRE,
    # no solo cuando cambia el partido gobernante (las bancas cambian en
    # toda eleccion). Sin esto, `_in_government()` seguia viendo el partido
    # pre-transicion todo el mandato siguiente.
    refresh_decision_actor_parties(sim.actor_engine, new_parties)

    changed = result.winner != result.incumbent_party
    if changed:
        # "Los demas actores persisten con su memoria. Memorias
        # about=president se re-etiquetan" (ADR 006 secc. 2.4, literal):
        # ANTES de reemplazar la ficha de `president`, para que la
        # re-etiqueta apunte al presidente SALIENTE.
        sim.actor_engine.memory_store.relabel_about(
            "president", f"former_president_{result.incumbent_party}"
        )
        new_actors = build_post_election_actors(result, sim.actor_engine.actors)
        reseed_president_relationships(sim.actor_engine.relationships, new_actors["president"])
        minister_actor = sim.actor_engine.decision_actors.get("minister_economy")
        if minister_actor is not None:
            minister_actor.sheet = new_actors["minister_economy"]
        sim.actor_engine.actors = new_actors
        # "la Policy arranca en el default" / agreements cleared (secc. 2.4).
        sim.actor_engine.agreements = []
        sim.actor_engine.no_renegotiate_until = {}
        sim.last_policy = sim.country.default_policy.model_copy()
        sim.last_effective_policy = sim.country.default_policy.model_copy()
        sim.concessions_delta = {}

    approval = clamp(honeymoon_approval(result), 0.0, 100.0)
    clamped = clamped.model_copy(update={"government_approval": approval})
    if sim.cohorts_enabled:
        sim.cohort_state = {
            cid: replace(cs, approval=approval) for cid, cs in sim.cohort_state.items()
        }
    sim.campaign_state = {}
    return clamped, result


def compute_months_to_election(
    month: int, total_months: int, term_length: int, elections_enabled: bool
) -> int:
    """`months_to_election` (hallazgo #3 de REVIEW_002, antes inline en
    `advance_month`): con `elections_enabled`, la presion electoral real de
    ESTE mandato (`term_length`) -- `T = term_length;
    ((month−1)//T + 1)·T − month` -- en vez del placeholder de ADR 003
    secc. 11 punto 7 (`total_months − month + 1`, que cuenta hasta el FIN DE
    LA CORRIDA, no hasta la proxima eleccion: en una corrida de 96 meses
    nadie sentia presion electoral antes del mes 48). Sin
    `elections_enabled` (o `term_length <= 0`), el placeholder de siempre
    (golden hashes de corridas sin elecciones intactos: ver docs/
    REVIEW_002_fases_4-7.md hallazgo #3)."""
    if elections_enabled and term_length > 0:
        return ((month - 1) // term_length + 1) * term_length - month
    return max(total_months - month + 1, 0)


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
    #: `{party_id: aprobo}` del `Bill` de este mes, si hubo uno (ADR 006
    #: secc. 1.1, ver mas abajo). Vacio sin Congreso o sin `Bill` este mes.
    vote_party_results: dict[str, bool] = {}
    #: Se calcula siempre (no solo con actores) porque `derive_congress_support`
    #: (mas abajo) tambien la necesita.
    months_to_election = compute_months_to_election(
        month, country.months, country.term_length, sim.elections_enabled
    )
    #: `ActionRecord` de este mes (vacio sin actores), para el sesgo de
    #: medios (ADR 005 secc. 4, mas abajo, pasos 8-9): se extrae de aca en
    #: vez de cambiar la firma de `run_actor_turn` para devolver los
    #: `PUBLISH_STORY` sueltos (ya vienen en el `ActionRecord`, con
    #: `authorized`/`params` incluidos).
    month_action_records: list[ActionRecord] = []
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

        # ADR 006 secc. 1.1 ("Pedido rechazado"): pedidos de `REQUEST_FUNDS`
        # del mes pasado que el presidente NO concede este mes (capturado
        # ANTES de que `run_actor_turn` pise `pending_requests` con los
        # pedidos nuevos de este mes).
        granted_this_month = {g.params.get("to") for g in grants}
        refused_actor_ids = {
            req.actor_id
            for req in sim.actor_engine.pending_requests
            if req.type.value == "REQUEST_FUNDS" and req.actor_id not in granted_this_month
        }

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
        # ADR 005 secc. 3, ultimo parrafo: `private_indicators`/`interest_impact`
        # de un `social_bloc` usan la percepcion/aprobacion de SU cohorte, tal
        # como esta al *inicio* de este mes (`sim.cohort_state` todavia no lo
        # actualizaron medios/cohortes de este mismo mes: eso corre recien en
        # los pasos 8-9, despues de la economia).
        bloc_cohort_views = (
            {
                actor_id: {
                    "perceived_inflation": cs.perceived_inflation,
                    "perceived_unemployment": cs.perceived_unemployment,
                    "approval": cs.approval,
                }
                for actor_id, cs in cohort_by_bloc_actor(sim.cohorts, sim.cohort_state).items()
            }
            if sim.cohorts_enabled
            else None
        )
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
            bloc_cohort_views=bloc_cohort_views,
            media_perception_active=sim.media_enabled,
            memory_enabled=sim.memory_enabled,
            term_length=country.term_length,
            auto_approve_execute=sim.auto_approve_governance,
        )
        month_action_records = action_records
        sim.action_records.extend(action_records)
        sim.trace_records.extend(sim.actor_engine.last_traces)
        sim.negotiation_records.extend(negotiation_records)
        agreement_events.extend(sim.actor_engine.last_compliance_events)

        # ADR 006 secc. 2.5: acumula `campaign_p` (`CAMPAIGN`) y registra las
        # promesas activas (`PROMISE`) de este mes. Ambas se autorizan solo
        # dentro de la ventana de campana (`engine/permissions.py`), pero el
        # escaneo no necesita repetir ese chequeo: solo mira `authorized`.
        if sim.elections_enabled:
            incumbent_party_id = next((p.id for p in country.parties if p.in_government), None)
            for ar in month_action_records:
                if not ar.authorized:
                    continue
                actor_party = (
                    incumbent_party_id
                    if ar.actor == "president"
                    else ar.actor.removeprefix("party_")
                )
                if ar.type == "CAMPAIGN" and actor_party:
                    bucket = sim.campaign_state.setdefault(actor_party, {})
                    focus = str(ar.params.get("focus", "all"))
                    bucket[focus] = bucket.get(focus, 0.0) + 0.5 * float(
                        ar.params.get("intensity", 0.0)
                    )
                elif ar.type == "PROMISE":
                    sim.promises.append(
                        {
                            "month": month,
                            "actor": ar.actor,
                            "target": ar.params.get("target"),
                            "text": str(ar.params.get("text", "")),
                            "direction": ar.params.get("direction", "expansive"),
                        }
                    )
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
            # Hallazgo #5 de REVIEW_002: se pasan TODOS los acuerdos, no
            # solo los `vigente` -- `_concession_bonus_for_party`
            # (`engine/congress.py`) ya filtra por `vigente` o por
            # `honored` otorgado este mismo `bill.month`.
            vote_record = congress_vote(
                bill,
                country.parties,
                sim.actor_engine.actors,
                allowed_actions_this_month,
                sim.state,
                sim.actor_engine.relationships,
                sim.actor_engine.agreements,
                months_to_election,
                sim.actor_engine.congress_rng,
            )
            sim.vote_records.append(vote_record)
            # ADR 006 secc. 1.1 ("Ley clave votada"): `voted_for`/
            # `voted_against` por partido, para `ai/memory.py::
            # generate_month_memories` mas abajo.
            vote_party_results = {
                pv.party_id: (pv.yes_seats / pv.seats) >= 0.5
                for pv in vote_record.parties
                if pv.seats > 0
            }
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

    # ADR 005 secc. 3: `policy_direction`/`Δprovincial_transfers`/`Δtax_rate`
    # de `world/cohorts.py::step_cohorts` (mas abajo) comparan la `Policy`
    # efectiva de este mes contra la del mes PASADO -- se guarda antes de
    # pisar `sim.last_effective_policy` con la de este mes (misma logica que
    # el `base = sim.last_effective_policy or country.default_policy` de
    # arriba, para el primer mes).
    prev_effective_policy = sim.last_effective_policy or country.default_policy
    sim.last_effective_policy = policy.model_copy()

    # 4. economia (4.1 -> 4.8)
    # P2 (A3, ADR 011 secc. 4): `sovereign_default`/`imf_program` activos
    # este mes (`sim.active_shocks`, ya actualizado arriba por
    # `ShockCatalog.apply_month`) ajustan `coeff`/`policy` de forma
    # proporcional (k_k=0, debt_interest_rate*0.5, primary_spending-1.5)
    # ANTES de pasarselos a `step_economy` -- su firma no cambia, solo los
    # valores que recibe. Sin ninguno de los dos shocks activos, `coeff`/
    # `policy` vuelven identicos (mismo objeto): golden hash de Aurora y de
    # cualquier corrida sin esos shocks, intacto.
    econ_coeff, econ_policy = apply_historical_shock_effects(coeff, policy, set(sim.active_shocks))
    econ_state, aux = step_economy(
        sim.state, sim.exo, exo_new, econ_policy, agg, country.structure, econ_coeff
    )
    if sim.actors_enabled:
        assert sim.actor_engine is not None
        # Las percepciones del mes que viene ven el `Aux` de este mes (el de
        # este mes recien se conoce aca, despues de que los actores ya
        # decidieron con el snapshot `t`: ver Notas de implementacion).
        sim.actor_engine.last_aux = aux

    # 8. medios -> percepcion por cohorte (ADR 005 secc. 4/5): corre ANTES
    # de la sociedad/politica de este mes (secc. 5, pasos 8-9: "sociedad y
    # politica restantes" van despues de cohortes) porque `step_society`
    # necesita `perceived_inflation_c` ya en `t+1` para `consumer_confidence`
    # (secc. 3) y `step_cohorts` necesita lo mismo para `approval_c`.
    if sim.cohorts_enabled:
        media_actions: list[MediaAction] = []
        if sim.media_enabled:
            for ar in month_action_records:
                if ar.type != "PUBLISH_STORY" or not ar.authorized:
                    continue
                influence = sim.outlet_influence.get(ar.actor)
                if influence is None:
                    continue
                media_actions.append(
                    MediaAction(
                        outlet_id=ar.actor,
                        frame=ar.params.get("frame", "neutral"),
                        target_bloc=ar.params.get("target_bloc", "all"),
                        influence_public=influence,
                    )
                )
            bias = compute_bias(sim.cohorts, media_actions, sim.media_consumption)
            sim.cohort_state = step_perception(
                sim.cohorts, sim.cohort_state, bias, econ_state.inflation, econ_state.unemployment
            )
        else:
            # `features.media = False` (con `features.cohorts = True`):
            # `perceived_* = real` cada mes, sin el retraso de q=0.4/0.3 de
            # `step_perception` (ver `world/perception.py::sync_to_real`).
            sim.cohort_state = sync_to_real(
                sim.cohorts, sim.cohort_state, econ_state.inflation, econ_state.unemployment
            )
        gap = compute_perception_gap(sim.cohorts, sim.cohort_state, econ_state.inflation)
        if sim.media_enabled:
            # ADR 005 secc. 4.5 (revisado v0.8): costo de reputacion cuando
            # el frame contradice la macro real 3+ meses SEGUIDOS (ver
            # `world/perception.py::update_contradiction_streak`/
            # `reputation_penalty`). El "cayendo"/"subiendo" del chequeo se
            # mide contra el valor de hace `TREND_WINDOW_MONTHS` meses (no
            # contra el mes inmediato anterior): con `exogenous_noise=True`
            # el delta mes a mes cambia de signo todo el tiempo, asi que casi
            # nunca sostiene una racha de 3+ meses SEGUIDOS -- una ventana
            # mas ancha (y el crecimiento promediado sobre la misma ventana)
            # sigue el criterio literal del ADR pero filtra ese ruido, igual
            # que ya hace `q` en `step_perception` (secc. 4.4) con el sesgo
            # de medios. `sim.recent_*` guarda los reales de los ultimos
            # meses (mas viejo primero); se actualiza TODOS los meses con
            # `media_enabled` (no solo los que publican), para que la
            # ventana no tenga huecos.
            window = sim.recent_inflation[-TREND_WINDOW_MONTHS:]
            inflation_ago = window[0] if len(window) >= TREND_WINDOW_MONTHS else sim.state.inflation
            window_u = sim.recent_unemployment[-TREND_WINDOW_MONTHS:]
            unemployment_ago = (
                window_u[0] if len(window_u) >= TREND_WINDOW_MONTHS else sim.state.unemployment
            )
            gdp_window = [
                *sim.recent_gdp_growth[-(TREND_WINDOW_MONTHS - 1) :],
                econ_state.gdp_growth,
            ]
            trend_gdp_growth = sum(gdp_window) / len(gdp_window)
            inflation_delta = econ_state.inflation - inflation_ago
            unemployment_delta = econ_state.unemployment - unemployment_ago
            if media_actions:
                # Hallazgo #6 de REVIEW_002: antes se armaba
                # `{outlet_id: frame}` (un dict por outlet), asi que un
                # medio que publica DOS `PUBLISH_STORY` el mismo mes (con
                # frames distintos, p.ej. uno `all` y otro dirigido a un
                # `target_bloc`) solo drifteaba audiencia con el ULTIMO --
                # el primero se perdia sin efecto. Se recorre
                # `media_actions` sin deduplicar: cada historia de este mes
                # aplica su propio `drift_audience` en secuencia (compuesto
                # sobre la influencia ya actualizada por la historia
                # anterior del mismo medio), acumulando todos los frames.
                published_outlets = {ma.outlet_id for ma in media_actions}
                for outlet_id in sim.outlet_influence:
                    if outlet_id not in published_outlets:
                        # Sin `PUBLISH_STORY` este mes no hay afirmacion
                        # que contradiga nada: corta la racha (tiene que
                        # ser 3+ meses SEGUIDOS publicando el frame
                        # contradictorio).
                        sim.outlet_contradiction_streak[outlet_id] = 0
                for ma in media_actions:
                    current = sim.outlet_influence.get(ma.outlet_id)
                    if current is None:
                        continue
                    current = drift_audience(
                        ma.frame,
                        ma.outlet_id,
                        current,
                        sim.cohorts,
                        sim.cohort_state,
                        sim.media_consumption,
                    )
                    streak = update_contradiction_streak(
                        sim.outlet_contradiction_streak,
                        ma.outlet_id,
                        ma.frame,
                        trend_gdp_growth,
                        inflation_delta,
                        unemployment_delta,
                    )
                    penalty = reputation_penalty(streak)
                    if penalty:
                        # La deuda de reputacion es ACUMULATIVA y no se
                        # perdona (ver campo en la dataclass, mas arriba):
                        # un medio que mintio 3+ meses seguidos no vuelve a
                        # `AUDIENCE_MAX` aunque se alinee siempre despues --
                        # sin este piso permanente, la deriva de audiencia
                        # normal de mas arriba reconverge a `AUDIENCE_MAX`
                        # en unos pocos meses de alineacion y borra
                        # cualquier diferencia entre medios (el bug
                        # original que reporta docs/EMERGENCE_LOG.md, solo
                        # que retrasado).
                        sim.outlet_reputation_debt[ma.outlet_id] = (
                            sim.outlet_reputation_debt.get(ma.outlet_id, 0.0) + penalty
                        )
                        current -= penalty
                    ceiling = clamp(
                        AUDIENCE_MAX - sim.outlet_reputation_debt.get(ma.outlet_id, 0.0),
                        AUDIENCE_MIN,
                        AUDIENCE_MAX,
                    )
                    sim.outlet_influence[ma.outlet_id] = clamp(current, AUDIENCE_MIN, ceiling)
            sim.recent_inflation.append(econ_state.inflation)
            sim.recent_unemployment.append(econ_state.unemployment)
            sim.recent_gdp_growth.append(econ_state.gdp_growth)
            if len(sim.recent_inflation) > TREND_WINDOW_MONTHS:
                sim.recent_inflation.pop(0)
            if len(sim.recent_unemployment) > TREND_WINDOW_MONTHS:
                sim.recent_unemployment.pop(0)
            if len(sim.recent_gdp_growth) > TREND_WINDOW_MONTHS - 1:
                sim.recent_gdp_growth.pop(0)
        sim.perception_records.append(
            PerceptionRecord(
                month=month,
                real_inflation=econ_state.inflation,
                real_unemployment=econ_state.unemployment,
                perception_gap=gap,
                cohorts={
                    c.id: {
                        "perceived_inflation": round(sim.cohort_state[c.id].perceived_inflation, 3),
                        "perceived_unemployment": round(
                            sim.cohort_state[c.id].perceived_unemployment, 3
                        ),
                        "sentiment": round(sim.cohort_state[c.id].sentiment, 3),
                    }
                    for c in sim.cohorts
                },
                outlet_influence=dict(sim.outlet_influence),
            )
        )

    # 5. sociedad (5.1 -> 5.5)
    perceived_inflation_agg = (
        weighted_perceived_inflation(sim.cohorts, sim.cohort_state) if sim.cohorts_enabled else None
    )
    soc_state = step_society(
        sim.state, econ_state, policy, agg, coeff, perceived_inflation_agg=perceived_inflation_agg
    )

    # 9. cohortes -> approval agregada (ADR 005 secc. 3), antes del resto de
    # la politica (secc. 5, paso 9: "cohortes -> approval agregada; sociedad
    # y politica restantes").
    cohort_approval: float | None = None
    # Hoisted fuera del `if sim.cohorts_enabled:` (ADR 006): `_check_promises`
    # (mas abajo) tambien necesita la firma economica del delta de politica
    # de este mes para comparar una `PROMISE` contra lo que el gobierno
    # efectivamente hizo, sin depender de `features.cohorts`.
    policy_delta_for_direction = compute_policy_proposal(policy, prev_effective_policy).delta
    policy_direction = economic_policy_direction(policy_delta_for_direction, load_signatures())
    if sim.cohorts_enabled:
        sim.cohort_state, cohort_approval = step_cohorts(
            sim.cohorts,
            sim.cohort_state,
            sim.state,
            soc_state,
            policy,
            prev_effective_policy,
            aux.demand_gap,
            policy_direction,
            coeff,
            shock_approval=agg.term("shock_approval"),
        )

    # 6. politica (5.6 -> 5.9)
    full_state = step_politics(
        sim.state, soc_state, aux.demand_gap, country.coalition_seats, agg, coeff
    )
    if cohort_approval is not None:
        # `government_approval` pasa a ser la agregada por cohorte (secc. 3):
        # mismo patron que `congress_support` derivado un poco mas abajo --
        # `step_politics` corre igual (su `political_stability`/
        # `institutional_confidence` de ESTE mes usan el `approval_new` de
        # v0.1, no el de cohortes: simplificacion documentada en Notas de
        # implementacion), y se pisa solo el campo publicado.
        full_state = full_state.model_copy(update={"government_approval": cohort_approval})

    # 6.bis Congreso: `congress_support` derivado (ADR 005 secc. 1.3), en vez
    # de la formula de v0.1 (`step_politics` arriba, sin tocar: sigue siendo
    # el fallback con `features.congress = False`).
    if sim.actors_enabled and sim.congress_enabled:
        assert sim.actor_engine is not None
        # Hallazgo #5 de REVIEW_002: idem `congress_vote` arriba, se pasan
        # TODOS los acuerdos (`_concession_bonus_for_party` filtra).
        derived_support = derive_congress_support(
            country.parties,
            sim.actor_engine.actors,
            full_state,
            sim.actor_engine.relationships,
            sim.actor_engine.agreements,
            month,
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

    # -- ADR 006 secc. 1: memoria (generacion + consolidacion) -------------
    # Corre con el `ActionRecord`/eventos de acuerdo/voto/shocks YA
    # calculados de este mes (ver docstring de `ai/memory.py`: un unico
    # punto de entrada). `refused_actor_ids`/`vote_party_results` se
    # capturaron mas arriba, en los puntos del turno donde el motor ya
    # resuelve esa informacion.
    if sim.actors_enabled and sim.memory_enabled:
        assert sim.actor_engine is not None
        mem_ctx = MemoryContext(
            month=month,
            actors=sim.actor_engine.actors,
            parties=country.parties,
            action_records=month_action_records,
            agreement_events=agreement_events,
            refused_actor_ids=refused_actor_ids,
            vote_party_results=vote_party_results,
            shock_agg=agg,
            new_shock_ids=new_ids,
            forced_devaluation=dev_event is not None,
            cohort_ids=[c.id for c in sim.cohorts],
        )
        new_memories = generate_month_memories(mem_ctx)
        for me in new_memories:
            sim.actor_engine.memory_store.add(me)
        sim.memory_records.extend(new_memories)
        if month % 12 == 0:
            consolidated = sim.actor_engine.memory_store.consolidate(month)
            sim.memory_records.extend(consolidated)

    # -- ADR 006 secc. 2.5: `promise_broken` --------------------------------
    if sim.actors_enabled and sim.memory_enabled and sim.promises:
        assert sim.actor_engine is not None
        parties_by_id = {p.id: p for p in country.parties}
        still_active: list[dict[str, Any]] = []
        for pr in sim.promises:
            if month - pr["month"] > PROMISE_WINDOW_MONTHS:
                continue  # expiro sin incumplirse: se descarta sin generar memoria
            contradicted = (pr["direction"] == "expansive" and policy_direction > 0.15) or (
                pr["direction"] == "restrictive" and policy_direction < -0.15
            )
            if not contradicted:
                still_active.append(pr)
                continue
            target = pr["target"]
            if target:
                sim.actor_engine.memory_store.add(
                    MemoryEvent(
                        turn=month,
                        actor=target,
                        about=pr["actor"],
                        kind="promise_broken",
                        summary=(f'{pr["actor"]} incumplio su promesa: "{pr["text"][:100]}"'),
                        importance=0.8,
                        sentiment=-0.7,
                    )
                )
                actor_party = (
                    next((p.id for p in country.parties if p.in_government), None)
                    if pr["actor"] == "president"
                    else pr["actor"].removeprefix("party_")
                )
                if actor_party and actor_party in parties_by_id:
                    key = (target, actor_party)
                    sim.loyalty_adjustments[key] = sim.loyalty_adjustments.get(key, 0.0) - 0.1
            # una promesa incumplida no se re-evalua (ADR 006 secc. 2.5:
            # es un evento de una sola vez, no uno que se repita cada mes
            # mientras la firma economica siga contradiciendola).
        sim.promises = still_active

    # `income_p`/`unemployment_p` por provincia de ESTE mes (calculado antes
    # de la eleccion -- calibracion, secc. 2.2 `regional_bonus_c,p`: la
    # eleccion los necesita para el bono regional; se reusa mas abajo para
    # el registro de la seccion 9, sin recalcularlo -- `clamped`/`policy`/
    # `agg` no cambian entre este punto y ahi salvo `government_approval`,
    # que `compute_provinces` no usa).
    provinces = compute_provinces(
        clamped,
        policy,
        country.provinces,
        coeff.province_transfer_sensitivity,
        coeff.transfers_ref,
        agg,
    )

    # -- ADR 006 secc. 2: elecciones -----------------------------------------
    election_window = sim.actors_enabled and sim.elections_enabled
    if election_window and is_election_month(month, country.term_length):
        assert sim.actor_engine is not None
        clamped, election_result = _run_election(sim, clamped, month, country, provinces)
        sim.election_records.append(election_result)
        events.append(f"election:{election_result.winner}")
        if outcome == "survived":
            outcome = election_result.outcome_type

    if outcome is not None:
        events.append(
            f"term_end:{outcome}" if outcome in ("survived", "reelected", "defeated") else outcome
        )
        sim.outcome = outcome

    # 9. registro
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
        cohorts={c.id: sim.cohort_state[c.id].to_dict() for c in sim.cohorts}
        if sim.cohorts_enabled
        else {},
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
    cohorts_enabled: bool = False,
    media_enabled: bool = False,
    cohorts: list[Cohort] | None = None,
    media_consumption: dict[str, dict[str, float]] | None = None,
    memory_enabled: bool = False,
    elections_enabled: bool = False,
    loyalty_table: LoyaltyTable | None = None,
    province_weights_table: dict[str, dict[str, float]] | None = None,
    governance_overrides: dict[str, str] | None = None,
    regime_calendar: RegimeCalendar | None = None,
    bimonetary_coefficients: BimonetaryCoefficients | None = None,
    fx_regime: str | None = None,
    historical_exogenous: dict[int, tuple[float, float]] | None = None,
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
    (`--no-congress`/`--no-negotiation` los apagan).

    `cohorts_enabled`/`media_enabled`/`cohorts`/`media_consumption` (ADR
    005 secc. 3/4): idem `new_simulation`.

    `regime_calendar`/`bimonetary_coefficients` (ADR 011 secc. 3/5, default
    `None` = comportamiento de siempre, byte a byte identico): activan
    `features.regime`/`features.bimonetary` para esta corrida. Se resuelven
    ENVOLVIENDO el loop de meses de siempre (no tocan `advance_month`): antes
    de cada mes, si hay `regime_calendar`, se avanza el regimen y se le
    aplican sus efectos a `sim.state` (repression) y a `sim.congress_enabled`/
    `sim.elections_enabled` (suspension de Congreso/elecciones); despues de
    cada mes, si hay `bimonetary_coefficients`, se avanza el bloque externo
    con el `Aux.r_real` de ese mes (ver Notas de implementacion del ADR 011
    para el porque de este disenio: cero cambios a `advance_month`/
    `step_economy`, asi que Aurora sin estos parametros es imposible de
    afectar)."""
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
        cohorts_enabled=cohorts_enabled,
        media_enabled=media_enabled,
        cohorts=cohorts,
        media_consumption=media_consumption,
        memory_enabled=memory_enabled,
        elections_enabled=elections_enabled,
        loyalty_table=loyalty_table,
        province_weights_table=province_weights_table,
        governance_overrides=governance_overrides,
    )
    sim.country = sim.country.model_copy(update={"months": months})

    base_congress_enabled = sim.congress_enabled
    base_elections_enabled = sim.elections_enabled
    regime_state = RegimeState() if regime_calendar is not None else None
    external_state = (
        init_external_state(bimonetary_coefficients, fx_regime)
        if bimonetary_coefficients is not None
        else None
    )

    for _ in range(months):
        next_month = sim.month + 1

        if historical_exogenous is not None and next_month in historical_exogenous:
            # `--historical-exogenous` (ADR 011 secc. 5): ancla `sim.exo`
            # (el nivel de PARTIDA del AR(1)+ruido de este mes, `world/
            # economy.py::step_exogenous`) al nivel real de este mes -- no
            # reemplaza `exo_new` del mes en si (eso exigiria tocar
            # `advance_month`), asi que la serie resultante sigue de cerca
            # (no exactamente) a la real, dejando el mismo proceso
            # estocastico de Aurora encima (ver Notas de implementacion).
            commodity, world_demand = historical_exogenous[next_month]
            sim.exo = Exogenous(commodity_price=commodity, world_demand=world_demand)

        regime_result = None
        if regime_calendar is not None:
            assert regime_state is not None
            forced_coup = next_month in regime_calendar.forced_coup_months
            propensity = regime_calendar.coup_propensity.get(next_month, 0.0)
            regime_result = step_regime(regime_state, sim.state, sim.rng, forced_coup, propensity)
            sim.state = regime_effects_on_state(sim.state, regime_result.repression)
            sim.congress_enabled = base_congress_enabled and congress_active(regime_result.mode)
            sim.elections_enabled = base_elections_enabled and elections_allowed(regime_result.mode)

        advance_month(sim)

        if regime_result is not None:
            sim.records[-1].regime_mode = regime_result.mode

        if external_state is not None:
            aux = sim.records[-1].aux
            external_state = step_bimonetary(
                external_state, sim.state, aux["r_real"], bimonetary_coefficients
            )
            sim.records[-1].external = external_state.to_dict()
            if (
                external_state.default_risk >= bimonetary_coefficients.default_risk_threshold
                and "imf_program" not in sim.active_shocks
                and "sovereign_default" not in sim.active_shocks
            ):
                sim.forced_shocks.setdefault(sim.month + 1, []).append("sovereign_default")

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
        perception_records=sim.perception_records,
        memory_records=sim.memory_records,
        election_records=sim.election_records,
    )
