"""Congreso (ADR 005 secc. 1): que necesita ley, voto por partido, resultado.

Todo el subsistema esta gateado por `features.congress` (default `True`,
solo tiene efecto si `features.actors` tambien lo esta: sin actores no hay
partidos-actor que votar). Con `features.congress = False` este modulo
simplemente no se llama (ver `engine/simulation.py`): `congress_support`
sigue la formula de v0.1 (`world/politics.py::step_politics`, sin tocar) y
nunca se crea un `Bill`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from republica.actors.rule_based import (
    electoral_pressure_raw,
    ideological_fit,
    interest_impact,
    load_interests_config,
    load_signatures,
    load_weights,
)
from republica.actors.sheet import ActorSheet
from republica.engine.actions import ActionType
from republica.engine.consequences import Relationships
from republica.world.config import Party
from republica.world.state import WorldState, clamp

#: Bancas necesarias para aprobar una ley (ADR 005 secc. 1.1, literal).
LAW_THRESHOLD = 51

#: Instrumentos que requieren ley sin importar la magnitud del delta (ADR 005
#: secc. 1.1): `tax_rate`/`provincial_transfers`. `primary_spending` solo si
#: `|delta| > PRIMARY_SPENDING_LAW_THRESHOLD`; `interest_rate_target`/
#: `fx_intervention` nunca (Ejecutivo/Banco Central).
ALWAYS_LAW_INSTRUMENTS = frozenset({"tax_rate", "provincial_transfers"})
PRIMARY_SPENDING_LAW_THRESHOLD = 0.5
_NEVER_LAW_INSTRUMENTS = frozenset({"interest_rate_target", "fx_intervention"})

#: +25 a la presion de un partido con un acuerdo vigente que lo involucra
#: (ADR 005 secc. 1.2/2, literal).
CONCESSION_BONUS = 25.0
#: Umbrales de afinidad actor-partido (ADR 005 secc. 1.2, literal).
AFFINITY_HIGH_RELATIONSHIP = 65
AFFINITY_MID_RELATIONSHIP = 50


def requires_law(policy_delta: dict[str, float]) -> dict[str, float]:
    """Subconjunto de `policy_delta` que requiere ley (ADR 005 secc. 1.1)."""
    out: dict[str, float] = {}
    for instrument, delta in policy_delta.items():
        if not delta or instrument in _NEVER_LAW_INSTRUMENTS:
            continue
        if instrument == "primary_spending":
            if abs(delta) > PRIMARY_SPENDING_LAW_THRESHOLD:
                out[instrument] = delta
        elif instrument in ALWAYS_LAW_INSTRUMENTS:
            out[instrument] = delta
    return out


@dataclass(frozen=True)
class Bill:
    """Un proyecto de ley (ADR 005 secc. 1.1): `policy_delta` es solo la
    parte de la propuesta del mes (mas, en su caso, concesiones de
    negociacion pendientes: ver `engine/negotiation.py`) que requiere ley."""

    id: str
    month: int
    policy_delta: dict[str, float]
    threshold: int = LAW_THRESHOLD


def sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _party_actor(party: Party, actors: dict[str, ActorSheet]) -> ActorSheet | None:
    return actors.get(f"party_{party.id}")


def affinity(actor: ActorSheet, party: Party, relationships: Relationships) -> float:
    """`affinity(a, p)` (ADR 005 secc. 1.2, literal): 1 si el actor
    pertenece al partido (gobernador de ese partido, o el propio actor
    partido), 0.5/0.2 segun su relacion con el actor-partido de `p`
    (`party_<id>`, ver `data/actors/party_*.yaml`: ya declaran relaciones
    entre si y con gobernadores)."""
    if actor.role == "governor" and actor.party == party.id:
        return 1.0
    if actor.role == "party" and actor.id == f"party_{party.id}":
        return 1.0
    rel = relationships.get(actor.id, f"party_{party.id}")
    if rel > AFFINITY_HIGH_RELATIONSHIP:
        return 1.0
    if rel > AFFINITY_MID_RELATIONSHIP:
        return 0.5
    return 0.2


def _pressure(
    party: Party,
    actors: dict[str, ActorSheet],
    lobby_actions: list[Any],
    state: WorldState,
    relationships: Relationships,
    concession_bonus: float,
) -> float:
    """`pressure_p` (ADR 005 secc. 1.2, literal)."""
    total = 0.0
    for rec in lobby_actions:
        actor = actors.get(rec.actor)
        if actor is None:
            continue
        sign = 1.0 if rec.params.get("direction") == "for" else -1.0
        total += (
            sign
            * rec.params.get("intensity", 0.0)
            * actor.influence.congress
            * affinity(actor, party, relationships)
            * 20.0
        )
    total += 0.2 * (state.government_approval - 50.0)
    total += concession_bonus
    return total


def _concession_bonus_for_party(
    party: Party, actors: dict[str, ActorSheet], agreements: list[Any], month: int
) -> float:
    """+25 si hay un acuerdo vigente con un actor de este partido (ADR 005
    secc. 1.2: "gobernador" o el actor-partido mismo).

    Hallazgo #5 de REVIEW_002: una concesion que NO requiere ley se ejecuta
    de inmediato y pasa a `honored` en el mismo mes en que se otorgo
    (`engine/negotiation.py::run_month_negotiations`) -- antes, como esta
    funcion solo miraba `status == "vigente"`, esa concesion nunca llegaba a
    comprar el voto por el que se negocio (22 de 56 acuerdos en una corrida
    de 96 meses). Un acuerdo `honored` cuenta igual que uno `vigente` SOLO
    si se otorgo este mismo `month` (el mes del `Bill`/`derive_congress_
    support` que se esta votando): un `honored` de un mes anterior ya
    "cobro" su voto (o nunca lo iba a cobrar, si nunca hubo Congreso ese
    mes) y no debe seguir sumando presion para siempre."""
    for agreement in agreements:
        status = getattr(agreement, "status", None)
        granted_month = getattr(agreement, "granted_month", None)
        honored_this_month = status == "honored" and granted_month == month
        if status != "vigente" and not honored_this_month:
            continue
        actor = actors.get(agreement.actor_id)
        if actor is None:
            continue
        if actor.role == "governor" and actor.party == party.id:
            return CONCESSION_BONUS
        if actor.role == "party" and actor.id == f"party_{party.id}":
            return CONCESSION_BONUS
    return 0.0


def _rule_score(
    party_actor: ActorSheet,
    delta: dict[str, float],
    state: WorldState,
    relationships: Relationships,
    months_to_election: int,
    in_government: bool,
    rng: random.Random,
    weights: dict[str, dict[str, float]],
    signatures: dict[str, dict[str, float]],
    interests_cfg: dict[str, dict[str, float]],
) -> float:
    """`rule_score(p, bill)` (ADR 005 secc. 1.2 -> ADR 003 secc. 6), aplicado
    directamente sobre `delta` en vez de una `Perception` completa: mismos 4
    terminos (ideo/interes/relacion/electoral) mas ruido, evaluados sobre el
    `policy_delta` del `Bill` (no el de la propuesta completa del mes, que
    puede incluir instrumentos que no requieren ley)."""
    indicators = state.model_dump()
    ideo = ideological_fit(delta, party_actor, signatures)
    interest = interest_impact(party_actor, delta, indicators, 0.5, in_government, interests_cfg)
    rel_president = relationships.get(party_actor.id, "president")
    rel = (rel_president - 50.0) * 2.0
    elec = electoral_pressure_raw(in_government, months_to_election, state.government_approval)
    w = weights.get(party_actor.role, weights["default"])
    sigma = 5.0 * (1.0 - party_actor.personality.pragmatism)
    noise = rng.gauss(0.0, sigma) if sigma > 0.0 else 0.0
    total = (
        w["w_ideo"] * ideo + w["w_int"] * interest + w["w_rel"] * rel + w["w_elec"] * elec + noise
    )
    return clamp(total, -100.0, 100.0)


@dataclass
class PartyVote:
    party_id: str
    seats: int
    score: float
    pressure: float
    yes_prob: float
    yes_seats: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "party_id": self.party_id,
            "seats": self.seats,
            "score": round(self.score, 2),
            "pressure": round(self.pressure, 2),
            "yes_prob": round(self.yes_prob, 3),
            "yes_seats": self.yes_seats,
        }


@dataclass
class VoteRecord:
    """`VoteRecord` (JSONL `kind: "vote"`, ADR 005 secc. 1.3)."""

    month: int
    bill_id: str
    policy_delta: dict[str, float]
    threshold: int
    parties: list[PartyVote] = field(default_factory=list)
    yes_total: int = 0
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "vote",
            "month": self.month,
            "bill_id": self.bill_id,
            "policy_delta": self.policy_delta,
            "threshold": self.threshold,
            "parties": [p.to_dict() for p in self.parties],
            "yes_total": self.yes_total,
            "passed": self.passed,
        }


def _lobby_records(actions: list[Any]) -> list[Any]:
    return [a for a in actions if a.type == ActionType.LOBBY_CONGRESS.value]


def vote(
    bill: Bill,
    parties: list[Party],
    actors: dict[str, ActorSheet],
    actions_this_month: list[Any],
    state: WorldState,
    relationships: Relationships,
    agreements: list[Any],
    months_to_election: int,
    rng: random.Random,
    *,
    weights: dict[str, dict[str, float]] | None = None,
    signatures: dict[str, dict[str, float]] | None = None,
    interests_cfg: dict[str, dict[str, float]] | None = None,
) -> VoteRecord:
    """Voto de un `Bill` (ADR 005 secc. 1.2/1.3).

    `actions_this_month`: `ActionRecord`-like (atributos `actor`, `type`,
    `params`) autorizados del mes, para extraer los `LOBBY_CONGRESS`.
    `agreements`: acuerdos vigentes o recien `honored` este mismo mes
    (`engine/negotiation.py::Agreement`, hallazgo #5 de REVIEW_002), para
    `concession_bonus_p`."""
    weights = weights if weights is not None else load_weights()
    signatures = signatures if signatures is not None else load_signatures()
    interests_cfg = interests_cfg if interests_cfg is not None else load_interests_config()
    lobby_actions = _lobby_records(actions_this_month)

    party_votes: list[PartyVote] = []
    yes_total = 0
    for party in parties:
        party_actor = _party_actor(party, actors)
        bonus = _concession_bonus_for_party(party, actors, agreements, bill.month)
        pressure = _pressure(party, actors, lobby_actions, state, relationships, bonus)
        if party_actor is None:
            score = 0.0
        else:
            score = _rule_score(
                party_actor,
                bill.policy_delta,
                state,
                relationships,
                months_to_election,
                party.in_government,
                rng,
                weights,
                signatures,
                interests_cfg,
            )
        yes_prob = sigmoid((score + pressure) / 25.0)
        bloc = 1.0 if yes_prob >= 0.5 else 0.0
        yes_seats_f = party.seats * (party.discipline * bloc + (1.0 - party.discipline) * yes_prob)
        yes_seats = round(yes_seats_f)
        yes_total += yes_seats
        party_votes.append(
            PartyVote(
                party_id=party.id,
                seats=party.seats,
                score=score,
                pressure=pressure,
                yes_prob=yes_prob,
                yes_seats=yes_seats,
            )
        )

    return VoteRecord(
        month=bill.month,
        bill_id=bill.id,
        policy_delta=bill.policy_delta,
        threshold=bill.threshold,
        parties=party_votes,
        yes_total=yes_total,
        passed=yes_total >= bill.threshold,
    )


#: `policy_delta` del "bill generico de gasto +1" usado para derivar
#: `congress_support` (ADR 005 secc. 1.3, literal).
_GENERIC_SPENDING_DELTA = {"primary_spending": 1.0}


def derive_congress_support(
    parties: list[Party],
    actors: dict[str, ActorSheet],
    state: WorldState,
    relationships: Relationships,
    agreements: list[Any],
    month: int,
    months_to_election: int,
    rng: random.Random,
    *,
    weights: dict[str, dict[str, float]] | None = None,
    signatures: dict[str, dict[str, float]] | None = None,
    interests_cfg: dict[str, dict[str, float]] | None = None,
) -> float:
    """`congress_support' = Sigma seats_p * yes_prob_p(bill generico de gasto
    +1)` (ADR 005 secc. 1.3): reemplaza la formula de v0.1 cuando
    `features.congress` esta activo (ver `engine/simulation.py`).

    `month` (hallazgo #5 de REVIEW_002): mes de ESTE `congress_support`
    generico, para que `_concession_bonus_for_party` acepte tambien un
    acuerdo `honored` otorgado este mismo mes (ver su docstring)."""
    weights = weights if weights is not None else load_weights()
    signatures = signatures if signatures is not None else load_signatures()
    interests_cfg = interests_cfg if interests_cfg is not None else load_interests_config()
    total = 0.0
    for party in parties:
        party_actor = _party_actor(party, actors)
        bonus = _concession_bonus_for_party(party, actors, agreements, month)
        pressure = _pressure(party, actors, [], state, relationships, bonus)
        if party_actor is None:
            score = 0.0
        else:
            score = _rule_score(
                party_actor,
                _GENERIC_SPENDING_DELTA,
                state,
                relationships,
                months_to_election,
                party.in_government,
                rng,
                weights,
                signatures,
                interests_cfg,
            )
        yes_prob = sigmoid((score + pressure) / 25.0)
        total += party.seats * yes_prob
    return total
