"""Catalogo cerrado de acciones (ADR 003 secc. 4).

Todo actor interactua con el mundo *solo* emitiendo `Action` de este catalogo.
Cada tipo tiene un esquema de params propio (pydantic, `extra="forbid"`):
`Action` valida `params` contra el esquema de su `type` al construirse, asi
que una `Action` con params desconocidos o fuera de rango nunca llega a
existir (test de deliverable 10: rechaza params desconocidos).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActionType(StrEnum):
    """Los 20 tipos de accion de la tabla de ADR 003 secc. 4."""

    SUPPORT_POLICY = "SUPPORT_POLICY"
    OPPOSE_POLICY = "OPPOSE_POLICY"
    NEGOTIATE = "NEGOTIATE"
    PUBLIC_STATEMENT = "PUBLIC_STATEMENT"
    LOBBY_CONGRESS = "LOBBY_CONGRESS"
    FORM_ALLIANCE = "FORM_ALLIANCE"
    BREAK_ALLIANCE = "BREAK_ALLIANCE"
    CALL_PROTEST = "CALL_PROTEST"
    STRIKE = "STRIKE"
    REQUEST_FUNDS = "REQUEST_FUNDS"
    WITHHOLD_INVESTMENT = "WITHHOLD_INVESTMENT"
    INVEST = "INVEST"
    PUBLISH_STORY = "PUBLISH_STORY"
    ENDORSE = "ENDORSE"
    CRITICIZE = "CRITICIZE"
    RECOMMEND_RATE = "RECOMMEND_RATE"
    SET_RATE = "SET_RATE"
    PROPOSE_POLICY = "PROPOSE_POLICY"
    ENACT_POLICY = "ENACT_POLICY"
    GRANT_CONCESSION = "GRANT_CONCESSION"
    NO_ACTION = "NO_ACTION"


class ConcessionType(StrEnum):
    """`ConcessionType` (ADR 003 secc. 4), costo tabulado en `data/concessions.yaml`."""

    RESTORE_TRANSFERS = "restore_transfers"
    PUBLIC_WORKS = "public_works"
    WAGE_BONUS = "wage_bonus"
    TAX_EXEMPTION = "tax_exemption"
    CABINET_SEAT = "cabinet_seat"
    DELAY_POLICY = "delay_policy"


class _Params(BaseModel):
    """Base de todos los esquemas de params: sin campos extra."""

    model_config = ConfigDict(extra="forbid")


class NoParams(_Params):
    pass


class IntensityParams(_Params):
    intensity: float = Field(ge=0.0, le=1.0)


class NegotiateParams(_Params):
    requested_concession: ConcessionType
    offer: str


class PublicStatementParams(_Params):
    stance: str = Field(pattern="^(support|oppose|neutral)$")
    intensity: float = Field(ge=0.0, le=1.0)


class LobbyCongressParams(_Params):
    direction: str = Field(pattern="^(for|against)$")
    intensity: float = Field(ge=0.0, le=1.0)


class AllianceParams(_Params):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    with_: str = Field(alias="with")


class StrikeParams(_Params):
    sector: str = Field(pattern="^(general|public)$")
    days: int = Field(ge=1, le=5)


class RequestFundsParams(_Params):
    amount_pct_gdp: float = Field(ge=0.0, le=1.0)


class PublishStoryParams(_Params):
    frame: str = Field(pattern="^(crisis|recovery|scandal|neutral)$")
    target_bloc: str


class TargetParams(_Params):
    target: str


class RateParams(_Params):
    delta_pp: float = Field(ge=-20.0, le=20.0)


class ProposePolicyParams(_Params):
    policy_delta: dict[str, float] = Field(default_factory=dict)


class GrantConcessionParams(_Params):
    to: str
    concession: ConcessionType


#: Esquema de params por tipo (ADR 003 secc. 4).
PARAM_SCHEMAS: dict[ActionType, type[_Params]] = {
    ActionType.SUPPORT_POLICY: IntensityParams,
    ActionType.OPPOSE_POLICY: IntensityParams,
    ActionType.NEGOTIATE: NegotiateParams,
    ActionType.PUBLIC_STATEMENT: PublicStatementParams,
    ActionType.LOBBY_CONGRESS: LobbyCongressParams,
    ActionType.FORM_ALLIANCE: AllianceParams,
    ActionType.BREAK_ALLIANCE: AllianceParams,
    ActionType.CALL_PROTEST: IntensityParams,
    ActionType.STRIKE: StrikeParams,
    ActionType.REQUEST_FUNDS: RequestFundsParams,
    ActionType.WITHHOLD_INVESTMENT: IntensityParams,
    ActionType.INVEST: IntensityParams,
    ActionType.PUBLISH_STORY: PublishStoryParams,
    ActionType.ENDORSE: TargetParams,
    ActionType.CRITICIZE: TargetParams,
    ActionType.RECOMMEND_RATE: RateParams,
    ActionType.SET_RATE: RateParams,
    ActionType.PROPOSE_POLICY: ProposePolicyParams,
    ActionType.ENACT_POLICY: ProposePolicyParams,
    ActionType.GRANT_CONCESSION: GrantConcessionParams,
    ActionType.NO_ACTION: NoParams,
}


class Action(BaseModel):
    """Una accion emitida por un actor (ADR 003 secc. 4).

    `params` se valida contra `PARAM_SCHEMAS[type]` al construirse (por
    alias, por eso `FORM_ALLIANCE`/`BREAK_ALLIANCE` aceptan la clave `with`)
    y se normaliza al `dict` resultante (con defaults del esquema aplicados).
    `reason` es obligatorio y no vacio: es lo que evalua Fase 7.
    """

    model_config = ConfigDict(extra="forbid")

    type: ActionType
    actor_id: str
    target: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_params(self) -> Action:
        schema = PARAM_SCHEMAS[self.type]
        typed = schema.model_validate(self.params)
        self.params = typed.model_dump(by_alias=True)
        return self

    def typed_params(self) -> _Params:
        """Reconstruye el objeto tipado de params (esquema segun `type`)."""
        return PARAM_SCHEMAS[self.type].model_validate(self.params)
