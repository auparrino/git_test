"""Esquema de salida del LLM (ADR 004 secc. 3): `ActorDecision`/`ActionRequest`
tal cual el ADR, y `to_actions(decision, actor) -> list[Action]`, la
conversion determinista que vive en el motor (nunca en el prompt)."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from republica.actors.sheet import ActorSheet
from republica.engine.actions import Action, ActionType, ConcessionType

logger = logging.getLogger(__name__)

#: Maximo de acciones por turno (ADR 003 secc. 4, reafirmado en ADR 004
#: secc. 3): las que sobren se descartan y se registran (log, no excepcion).
MAX_ACTIONS_PER_TURN = 3


class ActionRequest(BaseModel):
    """ADR 004 secc. 3. `type` es un `str` libre a proposito: se valida
    contra el catalogo del rol DESPUES, en `authorize()` (no aca) -- asi se
    puede *medir* cuantas veces el modelo pide algo fuera de su rol
    (`authority_violation`, metrica de Fase 7) en vez de impedirselo por
    construccion."""

    model_config = ConfigDict(extra="forbid")

    type: str
    params: dict[str, float | str | int] = Field(default_factory=dict)
    target: str | None = None


class ActorDecision(BaseModel):
    """ADR 004 secc. 3, tal cual (es lo que se envia a Ollama como
    `format=ActorDecision.model_json_schema()`)."""

    model_config = ConfigDict(extra="forbid")

    position: Literal["support", "oppose", "negotiate", "neutral"]
    # `description` viaja DENTRO del JSON Schema que se le manda al modelo
    # (`format=ActorDecision.model_json_schema()`), asi que es el unico lugar
    # del esquema donde se puede explicar un rango que la gramatica de Ollama
    # no verifica (ver PROMPT_VERSION v4.2 en `ai/prompts.py`).
    intensity: float = Field(
        ge=0.0, le=1.0, description="Decimal entre 0 y 1 (0.75), no un porcentaje (75)."
    )
    public_message: str = Field(default="", max_length=280)
    private_strategy: Literal["cooperate", "pressure", "wait", "escalate"]
    actions: list[ActionRequest] = Field(default_factory=list, max_length=3)
    requested_concession: ConcessionType | None = None
    confidence: float = Field(
        ge=0.0, le=1.0, description="Decimal entre 0 y 1 (0.85), no un porcentaje (85)."
    )
    reasoning: str = Field(default="", max_length=600)
    #: ADR 005 secc. 2/deliverable 4: como responderia el actor a un
    #: `COUNTER` del presidente sobre SU propio pedido de este mes (mismo
    #: turno: el LLM ya sabe que concesion pidio, asi que puede anticipar su
    #: respuesta a una contraoferta sin una segunda llamada). `None` (no
    #: declarado) dice "sin preferencia": `engine/negotiation.py` cae a la
    #: formula de aceptacion por reglas (ADR 005 secc. 2), igual que para
    #: cualquier `RuleBasedActor` -- ver Notas de implementacion (alcance
    #: minimo: no hay una segunda ronda de prompts al LLM todavia).
    negotiation_reply: Literal["accept", "counter", "walk_away"] | None = None
    #: Concesion alternativa si `negotiation_reply == "counter"` (ADR 005
    #: secc. 2: "COUNTER(concession'')"). `None` = mantiene la misma
    #: `requested_concession`.
    counter_concession: ConcessionType | None = None


#: `position` -> `stance` de `PUBLIC_STATEMENT` (`support|oppose|neutral`,
#: `engine/actions.py::PublicStatementParams`): "negotiate" no es un valor
#: valido de `stance`, se declara "neutral" (mismo mapeo que hace
#: `RuleBasedActor._decide_generic`, que marca `stance = "neutral"` tanto
#: para el caso sin propuesta clara como para el caso "negocia" -- ver ADR
#: 003 secc. 6 y Notas de implementacion punto 20/23).
_POSITION_TO_STANCE: dict[str, str] = {
    "support": "support",
    "oppose": "oppose",
    "negotiate": "neutral",
    "neutral": "neutral",
}

#: Concesion por defecto si el LLM pide `position="negotiate"` sin llenar
#: `requested_concession` (el schema lo permite, `| None`): no hay una
#: concesion "generica" en ADR 003/004, se elige la misma usada por
#: `RuleBasedActor` para `economy_minister` (`_NEGOTIATE_CONCESSION`), la
#: mas neutral de las 6 (no le da nada a nadie en particular, solo demora).
_DEFAULT_NEGOTIATE_CONCESSION = ConcessionType.DELAY_POLICY

_DEFAULT_REASON = "sin razon declarada por el modelo"


def _public_statement(decision: ActorDecision, actor: ActorSheet) -> Action | None:
    """Regla 1 (ADR 004 secc. 3): `PUBLIC_STATEMENT(stance=position,
    intensity)` si `public_message` no esta vacio."""
    if not decision.public_message.strip():
        return None
    return Action(
        type=ActionType.PUBLIC_STATEMENT,
        actor_id=actor.id,
        params={
            "stance": _POSITION_TO_STANCE[decision.position],
            "intensity": decision.intensity,
        },
        reason=decision.public_message,
    )


def _position_action(decision: ActorDecision, actor: ActorSheet) -> Action | None:
    """Regla 2 (ADR 004 secc. 3): `SUPPORT_POLICY`/`OPPOSE_POLICY`/
    `NEGOTIATE(requested_concession)` segun `position`. `position="neutral"`
    no genera nada aca (paridad con `RuleBasedActor`, que en ese caso solo
    emite `NO_ACTION`; `to_actions` agrega ese `NO_ACTION` mas abajo si al
    final no quedo ninguna accion)."""
    reason = decision.reasoning.strip() or _DEFAULT_REASON
    if decision.position == "support":
        return Action(
            type=ActionType.SUPPORT_POLICY,
            actor_id=actor.id,
            params={"intensity": decision.intensity},
            reason=reason,
        )
    if decision.position == "oppose":
        return Action(
            type=ActionType.OPPOSE_POLICY,
            actor_id=actor.id,
            params={"intensity": decision.intensity},
            reason=reason,
        )
    if decision.position == "negotiate":
        concession = decision.requested_concession or _DEFAULT_NEGOTIATE_CONCESSION
        offer = decision.public_message.strip() or reason
        return Action(
            type=ActionType.NEGOTIATE,
            actor_id=actor.id,
            target="president",
            params={"requested_concession": concession, "offer": offer},
            reason=reason,
        )
    return None


def _request_actions(decision: ActorDecision, actor: ActorSheet) -> list[Action]:
    """Regla 3 (ADR 004 secc. 3): cada `ActionRequest` -> `Action`.

    `Action.model_construct` (no el constructor normal) a proposito: el
    constructor normal valida `params` contra `PARAM_SCHEMAS[type]` al
    crearse y levanta `pydantic.ValidationError` si no validan
    (`engine/actions.py::Action._validate_params`), pero el ADR pide que una
    `ActionRequest` con params invalidos "se genere igual" para que
    `authorize()` la deniegue con `reason="invalid_params"` en vez de romper
    la corrida. Un `type` que ni siquiera es un `ActionType` del catalogo
    (alucinacion total, no solo "accion fuera de rol") no se puede
    representar asi -- `ActionRecord` (ADR 003 secc. 8) asume
    `action.type.value`, que no existe en un `str` -- asi que esos se
    descartan y se loguean aca en vez de llegar a `authorize()` (ver Notas
    de implementacion)."""
    reason = decision.reasoning.strip() or _DEFAULT_REASON
    out: list[Action] = []
    for req in decision.actions:
        try:
            action_type = ActionType(req.type)
        except ValueError:
            logger.info(
                "to_actions: %s pidio un tipo de accion inexistente %r (se descarta)",
                actor.id,
                req.type,
            )
            continue
        out.append(
            Action.model_construct(
                type=action_type,
                actor_id=actor.id,
                target=req.target,
                params=dict(req.params),
                reason=reason,
            )
        )
    return out


def to_actions(decision: ActorDecision, actor: ActorSheet) -> list[Action]:
    """`ActorDecision` -> `list[Action]` (ADR 004 secc. 3), determinista.

    Orden de salida: `[accion de posicion, *pedidos de accion, declaracion
    publica]` -- no el orden 1/2/3 literal del ADR (que solo describe *que*
    accion sale de cada regla, no en que orden final quedan) sino el mismo
    orden en que `RuleBasedActor._decide_generic` arma su propia lista
    (postura primero, escalada despues, `PUBLIC_STATEMENT` al final). Importa
    para el tope de 3: si sobran acciones se descartan por la cola, y con
    este orden la accion que se descarta primero es la declaracion publica
    -- igual que en `authorize_all` cuando un actor por reglas supera el
    presupuesto de turno (ver ADR 003 secc. 4/9, `permissions.py::
    ACTION_BUDGET_PER_TURN`). Documentado en Notas de implementacion."""
    ordered: list[Action] = []
    pos_action = _position_action(decision, actor)
    if pos_action is not None:
        ordered.append(pos_action)
    ordered.extend(_request_actions(decision, actor))
    statement = _public_statement(decision, actor)
    if statement is not None:
        ordered.append(statement)

    if not ordered:
        ordered.append(
            Action(
                type=ActionType.NO_ACTION,
                actor_id=actor.id,
                reason=decision.reasoning.strip() or "sin comentarios",
            )
        )

    if len(ordered) > MAX_ACTIONS_PER_TURN:
        dropped = ordered[MAX_ACTIONS_PER_TURN:]
        ordered = ordered[:MAX_ACTIONS_PER_TURN]
        dropped_types = [
            a.type.value if isinstance(a.type, ActionType) else str(a.type) for a in dropped
        ]
        logger.info(
            "to_actions: %s supero el presupuesto de %d acciones este turno, se descartan %d (%s)",
            actor.id,
            MAX_ACTIONS_PER_TURN,
            len(dropped),
            dropped_types,
        )
    return ordered
