"""Percepcion de un actor (ADR 003 secc. 3, completa en ADR 004 secc. 5).

`Perception` es lo unico que un actor recibe: nunca el estado completo (salvo
para `president`/`economy_minister`, que lo tienen todo por rol explicitamente
en la tabla de visibilidad). `build_perception` arma una por actor y mes.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from republica.actors.sheet import ActorSheet
from republica.ai.memory import MemoryStore
from republica.engine.consequences import Relationships
from republica.engine.narrate import KEY_INDICATORS, annualized_inflation
from republica.world.config import Party, Province
from republica.world.economy import Aux
from republica.world.events import ShockAggregate
from republica.world.provinces import compute_provinces
from republica.world.state import Policy, WorldState

#: Redondeo de `public_indicators` (ADR 004 secc. 5): "un actor real no ve
#: mas precision de la que veria". Solo inflacion y reservas estan
#: especificadas en el ADR; el resto se redondea a 1 decimal por
#: consistencia (documentado en Notas de implementacion de ADR 003).
_ROUNDING: dict[str, int] = {
    "inflation": 1,
    "reserves": -2,  # a centenas
}


def _round_indicator(key: str, value: float) -> float:
    digits = _ROUNDING.get(key, 1)
    return round(value, digits)


class PolicyProposal(BaseModel):
    """Lo que el gobierno propone este mes (ADR 003 secc. 3): delta de
    `Policy` respecto de la vigente + etiqueta legible."""

    model_config = ConfigDict(extra="forbid")

    delta: dict[str, float] = Field(default_factory=dict)
    label: str = ""


class Perception(BaseModel):
    """ADR 003 secc. 3."""

    model_config = ConfigDict(extra="forbid")

    month: int
    date: str
    months_to_election: int
    public_indicators: dict[str, float]
    private_indicators: dict[str, float]
    proposal: PolicyProposal | None
    active_shocks: list[str]
    recent_events: list[str]
    relationships: dict[str, int]
    memories: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    #: `Σ sentiment_i · importance_i · recency_i` sobre memorias `about =
    #: "president"` (ADR 006 secc. 1.3), SIN escalar por `w_mem`: lo escala
    #: `actors/rule_based.py::compute_score`. `0.0` (default, memoria
    #: apagada o sin memorias) reproduce el score de antes de ADR 006 --
    #: ver `MemoryStore.memory_term`.
    memory_score: float = 0.0


#: Frases derivadas de `interests` (ADR 003 secc. 3: "goals derivados de
#: interests"). Cubre los 16 intereses usados en `data/actors/*.yaml`.
INTEREST_GOALS: dict[str, str] = {
    "provincial_transfers": "recuperar las transferencias a su provincia",
    "agricultural_exports": "proteger las exportaciones agropecuarias",
    "real_wages": "recuperar el salario real",
    "employment": "bajar el desempleo",
    "price_stability": "contener la inflacion",
    "fiscal_balance": "equilibrar las cuentas fiscales",
    "low_taxes": "bajar los impuestos",
    "cheap_credit": "sostener el credito barato",
    "public_employment": "proteger el empleo publico",
    "reelection": "ganar la reeleccion",
    "audience": "captar audiencia",
    "social_programs": "sostener los programas sociales",
    "industrial_protection": "proteger a la industria de la competencia externa",
    "financial_stability": "preservar la estabilidad financiera",
    "law_and_order": "bajar la conflictividad y la inseguridad",
    "party_unity": "mantener unido al partido",
}


def goals_from_interests(interests: list[str]) -> list[str]:
    """`goals` derivados de `interests` (ADR 003 secc. 3), via el mapa de
    frases de arriba. Un interes sin frase mapeada cae a una generica en vez
    de levantar excepcion (una ficha nueva no deberia romper la percepcion)."""
    return [INTEREST_GOALS.get(i, f"avanzar su interes en {i}") for i in interests]


@dataclass(frozen=True)
class ProvinceView:
    """Vista de una provincia para `private_indicators` de un `governor`
    (ADR 004 secc. 5): deriva de `world/provinces.py` (`unemployment_p`,
    `income_p`) mas `dependence` (estatica, `provinces.csv`) y
    `transfers_received` (proxy inventado: `provincial_transfers * dependence`,
    documentado en Notas de implementacion)."""

    id: str
    unemployment_p: float
    income_p: float
    dependence: float
    transfers_received: float
    affected_by_shocks: int


def build_provinces_table(
    state: WorldState,
    policy: Policy,
    provinces: list[Province],
    shocks: ShockAggregate,
) -> dict[str, ProvinceView]:
    """Arma el `provinces_table` que consume `build_perception` para
    `governor`: una `ProvinceView` por provincia."""
    records = {r.id: r for r in compute_provinces(state, policy, provinces, 0.5, 6.0, shocks)}
    # `province_transfer_sensitivity`/`transfers_ref` reales los pasa el
    # llamador via `country.coefficients`; los defaults de arriba solo
    # cubren el caso en que `build_provinces_table` se use sin country a
    # mano (tests). Ver `engine/scheduler.py` para el uso real.
    table: dict[str, ProvinceView] = {}
    for p in provinces:
        rec = records.get(p.id)
        unemployment_p = rec.unemployment_p if rec else state.unemployment + p.u_offset
        income_p = rec.income_p if rec else 100.0
        affected = int(
            bool(shocks.province_id.get(p.id, 0.0))
            or bool(shocks.province_sector.get(p.main_sector, 0.0))
        )
        table[p.id] = ProvinceView(
            id=p.id,
            unemployment_p=unemployment_p,
            income_p=income_p,
            dependence=p.dependence,
            transfers_received=policy.provincial_transfers * p.dependence,
            affected_by_shocks=affected,
        )
    return table


def _public_indicators(state: WorldState) -> dict[str, float]:
    """Los 8 del tablero (`narrate.KEY_INDICATORS`, ya establecidos como "los
    8 indicadores" en el proyecto: ver Notas de implementacion) + `inflation_annual`."""
    values = {key: _round_indicator(key, getattr(state, key)) for key, _, _ in KEY_INDICATORS}
    values["inflation_annual"] = round(annualized_inflation(state.inflation), 1)
    return values


def _private_president(state: WorldState, policy: Policy, aux: Aux) -> dict[str, float]:
    values = state.model_dump()
    values.update({f"policy_{k}": v for k, v in policy.model_dump().items()})
    values["deficit"] = -state.fiscal_balance
    values["reserves_exact"] = state.reserves
    values["intervention_usd"] = aux.intervention_usd
    return values


def _private_central_bank(state: WorldState, aux: Aux) -> dict[str, float]:
    return {
        "reserves_exact": state.reserves,
        "exchange_rate": state.exchange_rate,
        "inflation_lag1": state.inflation_lag1,
        "intervention_usd": aux.intervention_usd,
        "public_debt": state.public_debt,
        # `interest_rate` no esta en la tabla de ADR 004 secc. 5, pero un
        # Banco Central que recomienda/fija la tasa necesita saber la tasa
        # vigente (ver Notas de implementacion de ADR 003): se agrega.
        "interest_rate": state.interest_rate,
    }


def _private_governor(
    actor: ActorSheet, provinces_table: dict[str, ProvinceView]
) -> dict[str, float]:
    view = provinces_table.get(actor.province or "")
    if view is None:
        return {}
    return {
        "unemployment_p": view.unemployment_p,
        "income_p": view.income_p,
        "dependence": view.dependence,
        "transfers_received": view.transfers_received,
        "affected_by_shocks": float(view.affected_by_shocks),
    }


def _private_party(
    actor: ActorSheet, state: WorldState, months_to_election: int, parties_by_id: dict[str, Party]
) -> dict[str, float]:
    party_id = actor.id.removeprefix("party_")
    party = parties_by_id.get(party_id)
    values = {
        "seats": float(party.seats) if party else 0.0,
        "congress_support": state.congress_support,
        "approval": state.government_approval,
        "months_to_election": float(months_to_election),
        # "encuestas" (ADR 004 secc. 5: `approval +- ruido 3`): sin ruido,
        # `build_perception` no recibe `rng` en su firma (ver Notas de
        # implementacion); se expone el valor exacto como proxy.
        "poll_approval": state.government_approval,
    }
    return values


def _private_union(actor: ActorSheet, state: WorldState, policy: Policy) -> dict[str, float]:
    values = {
        "real_wage": state.real_wage,
        "unemployment": state.unemployment,
        "inflation": state.inflation,
        "protest_level": state.protest_level,
    }
    if actor.id == "union_public":
        # `public_employment` no es una variable de estado (ADR 004 secc. 5
        # la pide igual): se usa `primary_spending` como proxy del tamano
        # del empleo publico (documentado en Notas de implementacion).
        values["public_employment"] = policy.primary_spending
    return values


def _private_business(
    actor: ActorSheet, state: WorldState, agg: ShockAggregate
) -> dict[str, float]:
    values = {
        "gdp_growth": state.gdp_growth,
        "interest_rate": state.interest_rate,
        "exchange_rate": state.exchange_rate,
        "tax_rate": 0.0,  # placeholder: `tax_rate` viaja via `policy`, ver abajo
        "consumer_confidence": state.consumer_confidence,
    }
    if actor.sector:
        # `sector` (ficha, ADR 003 secc. 2) no llegaba a `private_indicators`
        # (hallazgo #12 de REVIEW_001): una empresa deberia poder ver si su
        # propio sector esta afectado por los shocks de este mes, igual que
        # un `governor` ve `affected_by_shocks` de su provincia.
        affected = agg.province_sector.get(actor.sector, 0.0)
        values["sector_affected_by_shocks"] = float(bool(affected))
    return values


def _private_media(state: WorldState, recent_events: list[str]) -> dict[str, float]:
    return {
        "approval": state.government_approval,
        "protest_level": state.protest_level,
        "institutional_confidence": state.institutional_confidence,
        "events_this_month": float(len(recent_events)),
    }


def _private_social_bloc(
    state: WorldState, cohort_view: dict[str, float] | None
) -> dict[str, float]:
    """`private_indicators` de un `social_bloc` (ADR 003 secc. 5). Con
    `cohort_view` (ADR 005 secc. 3, ultimo parrafo: bloque social <-> su
    cohorte via `bloc_actor`): `unemployment`/`inflation` pasan a ser los
    percibidos por su cohorte (`world/perception.py`) en vez de los reales,
    y se agrega `approval_c` (tambien como `government_approval`, para que
    `interest_impact`/`_impact_reelection` -- que leen esa clave del
    `indicators` fusionado, ver `compute_score` -- usen la aprobacion de la
    cohorte y no la agregada: "su `interest_impact` usa `approval_c`")."""
    values = {
        "real_wage": state.real_wage,
        "unemployment": state.unemployment,
        "poverty": state.poverty,
        "inflation": state.inflation,
        "crime_perception": state.crime_perception,
    }
    if cohort_view is not None:
        values["unemployment"] = cohort_view["perceived_unemployment"]
        values["inflation"] = cohort_view["perceived_inflation"]
        values["approval_c"] = cohort_view["approval"]
        values["government_approval"] = cohort_view["approval"]
    return values


#: Instrumento dominante de la `PolicyProposal` de este mes -> `kind` de
#: `ai/memory.py::MemoryEvent` topicamente relacionado (hallazgo #7 de
#: REVIEW_002: `retrieve(situation_kind=...)` nunca se pasaba, quedaba
#: `None` siempre). Solo los instrumentos con un `kind` de memoria analogo
#: tienen entrada: una propuesta de `fx_intervention` es del mismo tema que
#: una memoria `forced_devaluation` (crisis cambiaria); una propuesta fiscal
#: (`tax_rate`/`primary_spending`/`provincial_transfers`) es del mismo tema
#: que una memoria `concession_received` (las concesiones negociadas de ADR
#: 005 secc. 2 son todas fiscales -- `restore_transfers`->
#: `provincial_transfers`, `tax_exemption`->`tax_rate`, ver `data/
#: concessions.yaml`). `interest_rate_target` no tiene un `kind` analogo en
#: `MEMORY_DEFAULTS` (`ai/memory.py`): queda sin mapear, mismo
#: comportamiento que antes (`situation_kind=None`, sin boost de relevancia
#: por `kind`).
_INSTRUMENT_SITUATION_KIND: dict[str, str] = {
    "fx_intervention": "forced_devaluation",
    "tax_rate": "concession_received",
    "primary_spending": "concession_received",
    "provincial_transfers": "concession_received",
}


def _proposal_situation_kind(proposal: PolicyProposal | None) -> str | None:
    """`situation_kind` (ADR 006 secc. 1.2: `relevance = 0.5` con memorias
    del mismo `kind` que "la situacion") derivado del instrumento dominante
    (mayor `|delta|`) de la `PolicyProposal` de este mes."""
    if proposal is None or not proposal.delta:
        return None
    dominant = max(proposal.delta.items(), key=lambda kv: abs(kv[1]))[0]
    return _INSTRUMENT_SITUATION_KIND.get(dominant)


def build_perception(
    actor: ActorSheet,
    state: WorldState,
    aux: Aux,
    policy_proposal: PolicyProposal | None,
    active_shocks: list[str],
    recent_events: list[str],
    month: int,
    months_to_election: int,
    provinces_table: dict[str, ProvinceView],
    parties: list[Party],
    *,
    policy: Policy,
    date: str = "",
    relationships: Relationships | None = None,
    agg: ShockAggregate | None = None,
    cohort_view: dict[str, float] | None = None,
    memory_store: MemoryStore | None = None,
    memory_enabled: bool = False,
) -> Perception:
    """Arma la `Perception` de `actor` para este mes (ADR 003 secc. 3,
    visibilidad por rol en ADR 004 secc. 5).

    `policy` (la `Policy` vigente este mes, keyword-only) no esta en la firma
    literal de ADR 003 secc. 3, pero hace falta para `private_indicators` de
    `president`/`economy_minister` ("policy actual") y para `tax_rate` de
    `business`/`public_employment` de `union_public"; ver Notas de
    implementacion de ADR 003.

    `relationships` (hallazgo #1 de REVIEW_001, ADR 003 secc. 5/7): las
    `Relationships` *vivas* del motor (consecuencias, decaimiento), no la
    ficha estatica. `view_of(actor.id)` es lo unico que un actor deberia ver
    ("solo las propias", ADR 003 secc. 3). `None` (default, uso en tests que
    arman una `Perception` suelta sin `ActorEngine` a mano) cae a la ficha,
    igual que antes de este fix: solo semilla, no hay motor que la actualice.

    `agg` (hallazgo #12): el `ShockAggregate` de este mes, para que una
    `business` pueda ver si su propio `sector` esta afectado (ver
    `_private_business`); `None` (default) cae a un agregado vacio.

    `cohort_view` (ADR 005 secc. 3, keyword-only, default `None` = sin
    cohortes: comportamiento identico a antes de ADR 005): la `CohortState`
    de la cohorte de este actor, ya resuelta a un `dict` plano por el
    llamador (`engine/scheduler.py`) para no acoplar este modulo a
    `world/cohorts.py`. Solo se usa si `actor.role == "social_bloc"`."""
    parties_by_id = {p.id: p for p in parties}
    public = _public_indicators(state)
    agg = agg if agg is not None else ShockAggregate()

    if actor.role in ("president", "economy_minister"):
        private = _private_president(state, policy, aux)
    elif actor.role == "central_bank":
        private = _private_central_bank(state, aux)
    elif actor.role == "governor":
        private = _private_governor(actor, provinces_table)
    elif actor.role == "party":
        private = _private_party(actor, state, months_to_election, parties_by_id)
    elif actor.role == "union":
        private = _private_union(actor, state, policy)
    elif actor.role == "business":
        private = _private_business(actor, state, agg)
        private["tax_rate"] = policy.tax_rate
    elif actor.role == "media":
        private = _private_media(state, recent_events)
    else:  # social_bloc
        private = _private_social_bloc(state, cohort_view)

    relationships_view = (
        relationships.view_of(actor.id) if relationships is not None else dict(actor.relationships)
    )

    memories: list[str] = []
    memory_score = 0.0
    if memory_enabled and memory_store is not None:
        # ADR 006 secc. 1.3: `trust_president` REEMPLAZA, solo en esta
        # vista de percepcion, el valor de `relationships["president"]`
        # que decae hacia 50 (ADR 003 secc. 5). `Relationships` (el store
        # del motor) no se toca: sigue siendo la unica fuente persistente,
        # `w_rel` (ADR 003 secc. 6) automaticamente usa `trust_president` en
        # vez del valor crudo porque lee de `perception.relationships`, no
        # de `Relationships` directo (ver Notas de implementacion de ADR
        # 006: "memoria agrega un modificador a la vista, no un segundo
        # store").
        if "president" in relationships_view:
            relationships_view = dict(relationships_view)
            relationships_view["president"] = round(memory_store.trust_president(actor.id, month))
        memories = memory_store.retrieve(
            actor.id,
            month,
            relevant_actors={"president"},
            situation_kind=_proposal_situation_kind(policy_proposal),
        )
        memory_score = memory_store.memory_term(actor.id, month, "president")

    return Perception(
        month=month,
        date=date,
        months_to_election=months_to_election,
        public_indicators=public,
        private_indicators=private,
        proposal=policy_proposal,
        active_shocks=list(active_shocks),
        recent_events=list(recent_events),
        relationships=relationships_view,
        memories=memories,
        goals=goals_from_interests(actor.interests),
        memory_score=memory_score,
    )
