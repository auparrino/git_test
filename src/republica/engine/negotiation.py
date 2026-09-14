"""Negociacion (ADR 005 secc. 2): protocolo de hasta 3 rondas entre el
presidente por reglas y un actor que pidio `NEGOTIATE`, ciclo de vida de un
`Agreement` y cumplimiento (ejecucion / incumplimiento).

Gateado por `features.negotiation` (default `True`, solo con
`features.actors` tambien activo): con `features.negotiation = False`,
`engine/scheduler.py` no llama nada de este modulo y `NEGOTIATE` sigue el
camino simple de Fase 3 (`actors/president_rules.py::RuleBasedPresident.
decide_grants`, un mes de desfasaje, sin rondas)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from republica.engine.actions import ActionType
from republica.engine.congress import requires_law

if TYPE_CHECKING:
    from republica.actors.sheet import ActorSheet
    from republica.engine.scheduler import ActorEngine
    from republica.world.config import Country

#: Presupuesto fiscal mensual para negociar (ADR 005 secc. 2, literal: "0.8
#: pp de PIB"), compartido por todas las negociaciones del mes. Mismo valor
#: que `actors/president_rules.py::MONTHLY_FISCAL_BUDGET_PCT_GDP` (el
#: presupuesto para conceder `REQUEST_FUNDS` de Fase 3, que sigue existiendo
#: aparte para el camino viejo).
MONTHLY_NEGOTIATION_BUDGET_PCT_GDP = 0.8

#: Umbrales de leverage del presidente (ADR 005 secc. 2, literal).
LEVERAGE_GRANT = 0.3
LEVERAGE_COUNTER = 0.15
#: Escalas de contraoferta (ADR 005 secc. 2, literal: `{0.5, 0.75}`): 0.5 en
#: la primera ronda de contraoferta, 0.75 si el actor contraoferta a su vez.
COUNTER_SCALE_ROUND1 = 0.5
COUNTER_SCALE_ROUND2 = 0.75

#: Umbral base de aceptacion del actor y sus ajustes (ADR 005 secc. 2,
#: literal): `value(offer) >= 0.6*value(request)`, bajado hasta 0.4 por
#: pragmatismo, subido a 0.75 si `ambition > 0.7`.
ACCEPT_THRESHOLD_BASE = 0.6
ACCEPT_THRESHOLD_MIN = 0.4
ACCEPT_THRESHOLD_AMBITIOUS = 0.75
AMBITION_THRESHOLD = 0.7
#: Relacion con el presidente que hace aceptar cualquier oferta (ADR 005
#: secc. 2, literal).
AUTO_ACCEPT_RELATIONSHIP = 65

#: Meses de "enfriamiento" tras un `broken_by_actor` (ADR 005 secc. 2,
#: literal: "el presidente por reglas no vuelve a negociar con el por 6
#: meses") y meses de gracia para que el gobierno ejecute una concesion
#: pactada antes de `broken_by_government` (ADR 005 secc. 2, literal: "2
#: meses").
NO_RENEGOTIATE_MONTHS = 6
EXECUTION_GRACE_MONTHS = 2

#: `in_exchange` que pide cada rol al aceptar una concesion (ADR 005 secc. 2
#: no lo tabula por rol; se elige el mas afin, documentado en Notas de
#: implementacion de ADR 005): union pide no-huelga, gobernador/partido
#: votos, el resto apoyo generico.
_IN_EXCHANGE_BY_ROLE: dict[str, str] = {
    "union": "no_strike",
    "governor": "vote_yes",
    "party": "vote_yes",
}


@dataclass
class Turn:
    """Un turno del dialogo (ADR 005 secc. 2, literal: "speaker, move,
    concession, scale, reason")."""

    speaker: str
    move: str
    concession: str
    scale: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "move": self.move,
            "concession": self.concession,
            "scale": round(self.scale, 3),
            "reason": self.reason,
        }


@dataclass
class Agreement:
    """Ciclo de vida `vigente -> honored | broken_by_government |
    broken_by_actor` (ADR 005 secc. 2)."""

    actor_id: str
    concession: str
    in_exchange: str
    scale: float
    granted_month: int
    law_required: bool
    status: str = "vigente"
    executed: bool = False
    months_pending: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "concession": self.concession,
            "in_exchange": self.in_exchange,
            "scale": round(self.scale, 3),
            "granted_month": self.granted_month,
            "law_required": self.law_required,
            "status": self.status,
            "executed": self.executed,
        }


@dataclass
class NegotiationRecord:
    """`NegotiationRecord` (JSONL `kind: "negotiation"`, ADR 005 secc. 2)."""

    month: int
    actor_id: str
    requested_concession: str
    turns: list[Turn]
    outcome: str
    agreement: Agreement | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "negotiation",
            "month": self.month,
            "actor": self.actor_id,
            "requested_concession": self.requested_concession,
            "turns": [t.to_dict() for t in self.turns],
            "outcome": self.outcome,
            "agreement": self.agreement.to_dict() if self.agreement else None,
        }


def _in_exchange_for(actor: ActorSheet) -> str:
    return _IN_EXCHANGE_BY_ROLE.get(actor.role, "support")


def _seats_controlled(actor: ActorSheet, parties_by_id: dict[str, Any]) -> float:
    if actor.role == "party":
        party = parties_by_id.get(actor.id.removeprefix("party_"))
        return float(party.seats) if party else 0.0
    if actor.role == "governor" and actor.party:
        party = parties_by_id.get(actor.party)
        return float(party.seats) if party else 0.0
    return 0.0


def leverage(actor: ActorSheet, country: Country) -> float:
    """`leverage_a` (ADR 005 secc. 2, literal)."""
    parties_by_id = {p.id: p for p in country.parties}
    seats = _seats_controlled(actor, parties_by_id)
    seats_needed = max(51.0 - country.coalition_seats, 1.0)
    return seats / seats_needed + actor.influence.streets


def _accept_threshold(actor: ActorSheet) -> float:
    if actor.personality.ambition > AMBITION_THRESHOLD:
        return ACCEPT_THRESHOLD_AMBITIOUS
    threshold = (
        ACCEPT_THRESHOLD_BASE
        - (ACCEPT_THRESHOLD_BASE - ACCEPT_THRESHOLD_MIN) * actor.personality.pragmatism
    )
    return threshold


def _cost(concessions_cfg: dict[str, Any], concession: str, scale: float) -> float:
    return concessions_cfg[concession]["fiscal_cost_pct_gdp"] * scale


def _is_law_required(
    concessions_cfg: dict[str, Any], concession: str, congress_enabled: bool
) -> bool:
    if not congress_enabled:
        return False
    cfg = concessions_cfg[concession]
    field_name = cfg.get("policy_field")
    if not field_name:
        return False
    return bool(requires_law({field_name: cfg["policy_bump"]}))


def negotiate_one(
    actor: ActorSheet,
    concession: str,
    country: Country,
    concessions_cfg: dict[str, Any],
    relationships: Any,
    budget_left: float,
    month: int,
    congress_enabled: bool,
    decision_actor: Any = None,
) -> tuple[NegotiationRecord, Agreement | None, float]:
    """El protocolo de hasta 3 rondas (ADR 005 secc. 2) para un actor y una
    `concession` (la que pidio en su `NEGOTIATE` de este mes). Devuelve el
    `NegotiationRecord`, el `Agreement` si se llego a un acuerdo (o `None`),
    y cuanto del presupuesto mensual gasto.

    `decision_actor` (ADR 005 deliverable 4, opcional): el actor de decision
    (`RuleBasedActor`/`LLMActor`) que emitio el `NEGOTIATE` este mes. Si es
    un `LLMActor` y ya declaro `last_negotiation_reply` (junto con el pedido
    original, mismo turno), esa respuesta se usa TAL CUAL en la primera
    ronda en vez de la formula de aceptacion por reglas -- alcance minimo:
    no hay una segunda llamada al LLM para las rondas 2/3, que siguen la
    formula por reglas igual que un `RuleBasedActor` (ver Notas de
    implementacion)."""
    lev = leverage(actor, country)
    rel_president = relationships.get(actor.id, "president")
    threshold = _accept_threshold(actor)
    llm_reply = getattr(decision_actor, "last_negotiation_reply", None)

    turns: list[Turn] = []
    already_countered = False
    outcome = "no_agreement"
    accepted_scale = 0.0

    for round_no in range(1, 4):
        if round_no == 1:
            if lev >= LEVERAGE_GRANT:
                candidate_scale = 1.0
            elif lev >= LEVERAGE_COUNTER:
                candidate_scale = COUNTER_SCALE_ROUND1
            else:
                candidate_scale = 0.0
        else:
            candidate_scale = COUNTER_SCALE_ROUND2

        cost = _cost(concessions_cfg, concession, candidate_scale)
        if candidate_scale <= 0.0 or cost > budget_left + 1e-9:
            turns.append(
                Turn(
                    "president",
                    "REFUSE",
                    concession,
                    0.0,
                    f"leverage={lev:.2f}, presupuesto {budget_left:.2f} pp PIB insuficiente"
                    if candidate_scale > 0.0
                    else f"leverage={lev:.2f} por debajo de {LEVERAGE_COUNTER:.2f}",
                )
            )
            break

        move = "GRANT" if candidate_scale >= 1.0 else "COUNTER"
        turns.append(
            Turn(
                "president",
                move,
                concession,
                candidate_scale,
                f"leverage={lev:.2f}, presupuesto {budget_left:.2f} pp PIB disponible",
            )
        )

        if round_no == 1 and llm_reply is not None:
            accept = llm_reply == "accept"
            forced_walk_away = llm_reply == "walk_away"
            reason = f"respuesta declarada por el modelo ({llm_reply})"
        else:
            accept = candidate_scale >= threshold or rel_president > AUTO_ACCEPT_RELATIONSHIP
            forced_walk_away = False
            reason = (
                f"oferta {candidate_scale:.0%} >= umbral {threshold:.0%}"
                if candidate_scale >= threshold
                else f"relacion con el presidente {rel_president:.0f} > {AUTO_ACCEPT_RELATIONSHIP}"
            )
        if accept:
            turns.append(Turn(actor.id, "ACCEPT", concession, candidate_scale, reason))
            outcome = "agreement"
            accepted_scale = candidate_scale
            break

        if forced_walk_away or already_countered:
            walk_reason = (
                reason
                if forced_walk_away
                else f"oferta {candidate_scale:.0%} < umbral {threshold:.0%}, "
                "ya contraoferto una vez"
            )
            turns.append(Turn(actor.id, "WALK_AWAY", concession, candidate_scale, walk_reason))
            outcome = "walk_away"
            break

        if round_no == 1 and llm_reply == "counter":
            counter_reason = reason
        else:
            counter_reason = f"oferta {candidate_scale:.0%} < umbral {threshold:.0%}, pide mas"
        turns.append(Turn(actor.id, "COUNTER", concession, candidate_scale, counter_reason))
        already_countered = True

    agreement: Agreement | None = None
    spent = 0.0
    if outcome == "agreement":
        spent = _cost(concessions_cfg, concession, accepted_scale)
        agreement = Agreement(
            actor_id=actor.id,
            concession=concession,
            in_exchange=_in_exchange_for(actor),
            scale=accepted_scale,
            granted_month=month,
            law_required=_is_law_required(concessions_cfg, concession, congress_enabled),
        )

    record = NegotiationRecord(
        month=month,
        actor_id=actor.id,
        requested_concession=concession,
        turns=turns,
        outcome=outcome,
        agreement=agreement,
    )
    return record, agreement, spent


def run_month_negotiations(
    engine: ActorEngine,
    requests: list[Any],
    country: Country,
    month: int,
    congress_enabled: bool,
) -> tuple[list[NegotiationRecord], dict[str, float]]:
    """Corre el protocolo para cada `NEGOTIATE` autorizado este mes (ADR 005
    secc. 2, paso 4 del orden de turno). `requests` son `Action` con
    `type == NEGOTIATE`. Agrega los acuerdos nuevos a `engine.agreements` y
    aplica de inmediato `relationships +8` (ADR 005 secc. 2, literal:
    "mientras este vigente ... +8 relacion").

    Los que no requieren ley (`Agreement.law_required = False`) se ejecutan
    en el acto (`executed=True`, `status="honored"`): su `policy_delta`/
    `shock_fiscal` entra al `dict` devuelto, que el llamador suma a
    `pending_terms` (mismo mecanismo de un mes de desfasaje que
    `GRANT_CONCESSION`, ver `engine/consequences.py`). Los que si la
    requieren quedan `vigente` sin ejecutar: entran a un `Bill` mas adelante
    (`engine/simulation.py`, via `sum_queue_delta`)."""
    records: list[NegotiationRecord] = []
    immediate_pending: dict[str, float] = {}
    budget_left = MONTHLY_NEGOTIATION_BUDGET_PCT_GDP

    for action in requests:
        actor = engine.actors.get(action.actor_id)
        if actor is None:
            continue
        concession = str(action.params["requested_concession"])
        cooldown_until = engine.no_renegotiate_until.get(actor.id, -1)
        if month < cooldown_until:
            records.append(
                NegotiationRecord(
                    month=month,
                    actor_id=actor.id,
                    requested_concession=concession,
                    turns=[
                        Turn(
                            "president",
                            "REFUSE",
                            concession,
                            0.0,
                            f"acuerdo roto con {actor.id}: sin renegociar hasta el mes "
                            f"{cooldown_until} (enfriamiento de {NO_RENEGOTIATE_MONTHS} meses)",
                        )
                    ],
                    outcome="no_agreement",
                )
            )
            continue

        record, agreement, spent = negotiate_one(
            actor,
            concession,
            country,
            engine.concessions,
            engine.relationships,
            budget_left,
            month,
            congress_enabled,
            decision_actor=engine.decision_actors.get(actor.id),
        )
        budget_left = max(0.0, budget_left - spent)
        records.append(record)

        if agreement is None:
            continue
        engine.agreements.append(agreement)
        engine.relationships.bump(actor.id, "president", 8.0)
        if not agreement.law_required:
            cfg = engine.concessions[agreement.concession]
            field_name = cfg.get("policy_field")
            if field_name:
                key = f"policy_{field_name}"
                immediate_pending[key] = (
                    immediate_pending.get(key, 0.0) + cfg["policy_bump"] * agreement.scale
                )
            immediate_pending["shock_fiscal"] = (
                immediate_pending.get("shock_fiscal", 0.0)
                - cfg["fiscal_cost_pct_gdp"] * agreement.scale
            )
            agreement.executed = True
            agreement.status = "honored"

    return records, immediate_pending


def sum_queue_delta(
    agreements: list[Agreement], concessions_cfg: dict[str, Any]
) -> dict[str, float]:
    """`policy_delta` acumulado de los acuerdos `vigente`, que requieren ley
    y todavia no se ejecutaron: la parte del `Bill` que viene de
    negociaciones (ADR 005 secc. 1/2, ver Notas de implementacion: por que
    esto entra al mismo `Bill` que la propuesta del mes)."""
    out: dict[str, float] = {}
    for agreement in agreements:
        if agreement.status != "vigente" or agreement.executed or not agreement.law_required:
            continue
        cfg = concessions_cfg[agreement.concession]
        field_name = cfg.get("policy_field")
        if not field_name:
            continue
        out[field_name] = out.get(field_name, 0.0) + cfg["policy_bump"] * agreement.scale
    return out


def apply_execution_results(
    engine: ActorEngine,
    passed: bool,
    agreements: list[Agreement],
    concessions_cfg: dict[str, Any],
    month: int,
) -> tuple[dict[str, float], list[str]]:
    """Cumplimiento de la parte de `agreements` que dependia del `Bill` de
    este mes (ADR 005 secc. 2, "2 meses para ejecutar la concesion"): si el
    `Bill` paso, se ejecutan (mismo mecanismo `policy_*`/`shock_fiscal` de
    `GRANT_CONCESSION`, un mes de desfasaje); si no, suman un mes de
    incumplimiento y, al segundo, `broken_by_government`."""
    pending: dict[str, float] = {}
    events: list[str] = []
    for agreement in agreements:
        if agreement.status != "vigente" or agreement.executed:
            continue
        if passed:
            cfg = concessions_cfg[agreement.concession]
            field_name = cfg.get("policy_field")
            if field_name:
                key = f"policy_{field_name}"
                pending[key] = pending.get(key, 0.0) + cfg["policy_bump"] * agreement.scale
            pending["shock_fiscal"] = (
                pending.get("shock_fiscal", 0.0) - cfg["fiscal_cost_pct_gdp"] * agreement.scale
            )
            agreement.executed = True
            agreement.status = "honored"
            events.append(f"agreement_honored:{agreement.actor_id}:{agreement.concession}")
        else:
            agreement.months_pending += 1
            if agreement.months_pending >= EXECUTION_GRACE_MONTHS:
                agreement.status = "broken_by_government"
                engine.relationships.bump(agreement.actor_id, "president", -15.0)
                events.append(
                    f"agreement_broken:{agreement.actor_id}:{agreement.concession}:government"
                )
    return pending, events


#: Tipos de accion que violan cada `in_exchange` (ADR 005 secc. 2: "si el
#: actor vota en contra igual"): no solo un voto formal (que el motor no
#: simula por actor individual, solo por partido en `engine/congress.py`),
#: tambien el gesto publico equivalente (oponerse/hacer lobby en contra/huelga).
_VIOLATION_TYPES: dict[str, frozenset[str]] = {
    "vote_yes": frozenset({ActionType.OPPOSE_POLICY.value}),
    "no_strike": frozenset({ActionType.STRIKE.value}),
    "support": frozenset({ActionType.OPPOSE_POLICY.value, ActionType.WITHHOLD_INVESTMENT.value}),
}


def check_actor_compliance(engine: ActorEngine, action_records: list[Any], month: int) -> list[str]:
    """`broken_by_actor` (ADR 005 secc. 2): un actor con un acuerdo vigente
    que igual emite la accion contraria a lo pactado este mes."""
    events: list[str] = []
    for rec in action_records:
        if not rec.authorized:
            continue
        for agreement in engine.agreements:
            if agreement.status != "vigente" or agreement.actor_id != rec.actor:
                continue
            violated = rec.type in _VIOLATION_TYPES.get(agreement.in_exchange, frozenset())
            is_lobby = rec.type == ActionType.LOBBY_CONGRESS.value
            if not violated and agreement.in_exchange == "vote_yes" and is_lobby:
                violated = rec.params.get("direction") == "against"
            if not violated:
                continue
            agreement.status = "broken_by_actor"
            engine.relationships.bump(agreement.actor_id, "president", -10.0)
            engine.no_renegotiate_until[agreement.actor_id] = month + NO_RENEGOTIATE_MONTHS
            events.append(f"agreement_broken:{agreement.actor_id}:{agreement.concession}:actor")
    return events
