"""Autorizacion de acciones (ADR 003 secc. 4): `authorize()` con los 5
chequeos en orden. El motor **nunca** corrige una accion: la deniega y
registra `reason` (metrica `authority_violation` de Fase 7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from republica.actors.sheet import ActorSheet
from republica.engine.actions import PARAM_SCHEMAS, Action, ActionType
from republica.governance import (
    DEFAULT_GOVERNANCE_PATH,
    Governance,
    load_governance,
    required_tier,
)
from republica.world.config import Party
from republica.world.elections import is_campaign_month
from republica.world.state import WorldState

__all__ = [
    "ACTION_BUDGET_PER_TURN",
    "COOLDOWN_MONTHS",
    "DEFAULT_GOVERNANCE_PATH",
    "DEFAULT_PERMISSIONS_PATH",
    "Allowed",
    "AuthContext",
    "Denied",
    "Governance",
    "authorize",
    "authorize_all",
    "load_governance",
    "load_permissions",
    "to_record_dict",
]

DEFAULT_PERMISSIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "permissions.yaml"

#: Presupuesto de acciones por turno (ADR 003 secc. 4/9): la 4a accion de un
#: actor en un mes se deniega. `NO_ACTION` no consume presupuesto (no
#: modifica nada; el spec habla de "acciones" y no tendria sentido limitar
#: cuantas veces un actor "no hace nada" — ver Notas de implementacion).
ACTION_BUDGET_PER_TURN = 3

#: Cooldown en meses por tipo de accion (ADR 003 secc. 4/9): solo `STRIKE`
#: tiene uno explicito ("max 1 cada 3 meses por actor"). El resto no tiene
#: cooldown (0 = sin restriccion).
COOLDOWN_MONTHS: dict[ActionType, int] = {
    ActionType.STRIKE: 3,
}

#: Instrumentos fiscales (ADR 003 secc. 4): `PROPOSE_POLICY` del ministro de
#: economia solo puede tocar estos ("solo instrumentos fiscales"); el
#: presidente no tiene esta restriccion.
FISCAL_INSTRUMENTS = frozenset({"tax_rate", "primary_spending", "provincial_transfers"})


def load_permissions(path: str | Path | None = None) -> dict[str, set[ActionType]]:
    p = Path(path) if path is not None else DEFAULT_PERMISSIONS_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return {role: {ActionType(t) for t in types} for role, types in raw.items()}


@dataclass
class AuthContext:
    """Todo lo que `authorize()` necesita ademas de `(actor, action)`
    (ADR 003 secc. 4, chequeos 3-5)."""

    state: WorldState
    month: int
    parties_by_id: dict[str, Party]
    governance: Governance
    cooldowns: dict[tuple[str, ActionType], int] = field(default_factory=dict)
    action_counts: dict[str, int] = field(default_factory=dict)
    permissions: dict[str, set[ActionType]] = field(default_factory=dict)
    #: `term_length` (ADR 006 secc. 2.5/§5, default 48 = comportamiento sin
    #: elecciones): usado solo por el chequeo de `CAMPAIGN`/`PROMISE`.
    term_length: int = 48


@dataclass(frozen=True)
class Allowed:
    action: Action


@dataclass(frozen=True)
class Denied:
    action: Action
    reason: str


def _check_state_conditions(actor: ActorSheet, action: Action, ctx: AuthContext) -> str | None:
    """Chequeo 3 (ADR 003 secc. 4). Devuelve el motivo de denegacion, o
    `None` si la condicion se cumple (o no aplica a este tipo/rol)."""
    if action.type is ActionType.CALL_PROTEST and actor.role == "party":
        # Las fichas de rol `party` traen `party == id` (con prefijo
        # `party_`), mientras que `parties.json` usa el id sin prefijo (ver
        # Notas de implementacion de ADR 003): se resuelve por `actor.id`,
        # no por `actor.party`, para no depender de esa duplicacion.
        party_id = actor.id.removeprefix("party_")
        party = ctx.parties_by_id.get(party_id)
        if party is None or party.in_government:
            return "CALL_PROTEST solo lo puede convocar un partido de oposicion"
    if action.type is ActionType.PROPOSE_POLICY and actor.role == "economy_minister":
        delta = action.params.get("policy_delta", {})
        non_fiscal = set(delta) - FISCAL_INSTRUMENTS
        if non_fiscal:
            return f"el ministro solo puede proponer instrumentos fiscales, no {sorted(non_fiscal)}"
    if action.type in (ActionType.CAMPAIGN, ActionType.PROMISE) and not is_campaign_month(
        ctx.month, ctx.term_length
    ):
        return (
            f"{action.type.value} solo se permite en los ultimos 4 meses del mandato "
            f"(mandato de {ctx.term_length} meses)"
        )
    return None


def _check_governance(actor: ActorSheet, action: Action, ctx: AuthContext) -> str | None:
    """Chequeo de gobernanza (ADR 007 secc. 6), consultado ANTES de la
    matriz de rol -- pero solo si `action.type` YA es del rol de `actor`
    (ver `authorize`): si ni siquiera es del rol, se deja que el chequeo 1
    (matriz) produzca su propio `"no tiene permitido"`, del que depende la
    metrica `authority_violation` (ADR 004 secc. 8) -- documentado en Notas
    de implementacion de ADR 007.

    Reemplaza el chequeo puntual de `SET_RATE` (ADR 003 secc. 6.4) por el
    mecanismo general: `write`/`execute` restringen que tipos puede
    *intentar* este actor en particular, y un tipo de `execute` ademas
    necesita `autonomy >= required_tier(tipo)` (la misma regla de antes,
    generalizada: `SET_RATE` sigue pidiendo `autonomy >= 3`)."""
    gov = ctx.governance.for_actor(actor.id)
    if action.type is ActionType.NO_ACTION:
        return None
    if not gov.allows_type(action.type):
        return f"governance:write ({actor.id} no tiene {action.type.value} en write/execute)"
    if not gov.meets_autonomy(action.type):
        return (
            f"governance:autonomy ({action.type.value} requiere autonomy >= "
            f"{required_tier(action.type)}, {actor.id} tiene {gov.autonomy})"
        )
    budget = gov.budget.actions_per_turn
    if budget is not None and budget < ACTION_BUDGET_PER_TURN:
        used = ctx.action_counts.get(actor.id, 0)
        if used >= budget:
            return f"governance:budget ({actor.id} ya emitio {used} acciones, tope {budget})"
    return None


def authorize(actor: ActorSheet, action: Action, ctx: AuthContext) -> Allowed | Denied:
    """Los 5 chequeos de ADR 003 secc. 4, en orden: (1) matriz de permisos,
    (2) params validan contra el esquema de su tipo, (3) condiciones de
    estado, (4) cooldowns, (5) presupuesto de acciones por turno -- mas la
    gobernanza de ADR 007 secc. 6, consultada antes que (1) para los tipos
    que ya son del rol de `actor` (ver `_check_governance`). No muta `ctx`:
    quien llama debe actualizar `cooldowns`/`action_counts` despues de ver
    el resultado (ver `authorize_all`)."""
    if action.actor_id != actor.id:
        return Denied(action, f"actor_id {action.actor_id!r} no coincide con la ficha {actor.id!r}")

    permissions = ctx.permissions or load_permissions()
    allowed_types = permissions.get(actor.role, set())
    if action.type in allowed_types:
        gov_reason = _check_governance(actor, action, ctx)
        if gov_reason is not None:
            return Denied(action, gov_reason)
    if action.type not in allowed_types:
        return Denied(action, f"el rol {actor.role!r} no tiene permitido {action.type.value}")

    try:
        PARAM_SCHEMAS[action.type].model_validate(action.params)
    except ValidationError as exc:
        return Denied(
            action, f"params invalidos para {action.type.value}: {exc.errors()[0]['msg']}"
        )

    state_reason = _check_state_conditions(actor, action, ctx)
    if state_reason is not None:
        return Denied(action, state_reason)

    cooldown = COOLDOWN_MONTHS.get(action.type, 0)
    if cooldown > 0:
        last_month = ctx.cooldowns.get((actor.id, action.type))
        if last_month is not None and ctx.month - last_month < cooldown:
            left = cooldown - (ctx.month - last_month)
            return Denied(
                action,
                f"{action.type.value} en cooldown para {actor.id} "
                f"(ultimo uso mes {last_month}, faltan {left} meses)",
            )

    if action.type is not ActionType.NO_ACTION:
        used = ctx.action_counts.get(actor.id, 0)
        if used >= ACTION_BUDGET_PER_TURN:
            budget = ACTION_BUDGET_PER_TURN
            return Denied(
                action, f"{actor.id} ya emitio {used} acciones este mes (presupuesto {budget})"
            )

    return Allowed(action)


def authorize_all(
    actions: list[Action], actors: dict[str, ActorSheet], ctx: AuthContext
) -> tuple[list[Allowed], list[Denied]]:
    """Corre `authorize()` sobre `actions` en orden, actualizando cooldowns y
    presupuesto de `ctx` a medida que autoriza (para que la 2a/3a/4a accion
    del mismo actor vean el estado ya actualizado)."""
    if not ctx.permissions:
        ctx.permissions = load_permissions()
    allowed: list[Allowed] = []
    denied: list[Denied] = []
    for action in actions:
        actor = actors.get(action.actor_id)
        if actor is None:
            denied.append(Denied(action, f"actor desconocido: {action.actor_id!r}"))
            continue
        result = authorize(actor, action, ctx)
        if isinstance(result, Allowed):
            allowed.append(result)
            if action.type is not ActionType.NO_ACTION:
                ctx.action_counts[actor.id] = ctx.action_counts.get(actor.id, 0) + 1
            if action.type in COOLDOWN_MONTHS:
                ctx.cooldowns[(actor.id, action.type)] = ctx.month
        else:
            denied.append(result)
    return allowed, denied


def to_record_dict(result: Allowed | Denied) -> dict[str, Any]:
    """Parte comun de un `ActionRecord` (ADR 003 secc. 8) que aporta
    `authorize()`: `authorized`/`denied_reason`."""
    if isinstance(result, Allowed):
        return {"authorized": True, "denied_reason": None}
    return {"authorized": False, "denied_reason": result.reason}
