"""Gobernanza por actor (ADR 007 secc. 6): ficha `data/governance.yaml`,
aplicada por el motor (no documentacion). `authorize()` (`engine/permissions.py`)
consulta `for_actor(actor.id)` ANTES de la matriz de rol; `read` filtra la
`Perception` de un actor; `write`/`execute` (mas `autonomy`) restringen que
tipos de accion puede intentar; `budget` corta acciones/tokens por turno.

Reemplaza al `Governance(central_bank_autonomy: int)` de ADR 003 secc. 6.4:
`central_bank_autonomy` sigue existiendo como propiedad de compatibilidad
(`Governance.central_bank_autonomy`, usada por `actors/rule_based.py`), pero
la fuente de verdad ahora es una ficha completa por actor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from republica.actors.sheet import ActorSheet
from republica.engine.actions import ActionType
from republica.engine.perception import Perception

DEFAULT_GOVERNANCE_PATH = Path(__file__).resolve().parents[3] / "data" / "governance.yaml"

#: Las 9 categorias de `read` (ADR 007 secc. 6, deliverable 5: "implementar
#: un pequeno mapa clave -> categoria"). Cubren `public_indicators` (todas
#: `economic_indicators`) y cada bloque de `private_indicators` por rol
#: (ADR 004 secc. 5), mas `proposal` (`government_announcements`).
ALL_CATEGORIES: tuple[str, ...] = (
    "economic_indicators",
    "monetary_history",
    "government_announcements",
    "provincial_finances",
    "party_polls",
    "labour_market",
    "sector",
    "media_events",
    "cohort_view",
)

#: Tipos de accion "de ejecucion" (ADR 007 secc. 6, tabla de `autonomy`,
#: niveles 3/4): requieren `autonomy >= N` ademas de estar en `execute`.
#: Nivel 3 ("ejecutar sin efecto fiscal"): `SET_RATE`/`STRIKE`/`PUBLISH_STORY`
#: son los 3 ejemplos literales del ADR; `WITHHOLD_INVESTMENT`/`INVEST` se
#: agregan por el mismo criterio (accion unilateral con efecto de estado
#: directo, sin pasar por el presidente). Nivel 4 ("efecto fiscal acotado"):
#: `GRANT_CONCESSION` (presidente, "concesiones <= 0.3 pp PIB" del ADR) y
#: `ENACT_POLICY` (efecto fiscal directo sobre `Policy`). El resto del
#: catalogo (declarar/proponer/negociar) no esta en este mapa: solo necesita
#: `autonomy >= 1` (ver `EXECUTE_TIER.get(tipo, 1)` en `required_tier`).
EXECUTE_TIER: dict[ActionType, int] = {
    ActionType.SET_RATE: 3,
    ActionType.STRIKE: 3,
    ActionType.PUBLISH_STORY: 3,
    ActionType.WITHHOLD_INVESTMENT: 3,
    ActionType.INVEST: 3,
    ActionType.GRANT_CONCESSION: 4,
    ActionType.ENACT_POLICY: 4,
}


def required_tier(action_type: ActionType) -> int:
    """`autonomy` minima para `action_type` (ADR 007 secc. 6): 0 para
    `NO_ACTION` (siempre permitido), 1 para declarar (`PUBLIC_STATEMENT`),
    2 para el resto de "declarar/proponer/negociar" (default de este mapa),
    y lo que diga `EXECUTE_TIER` para las acciones de ejecucion."""
    if action_type is ActionType.NO_ACTION:
        return 0
    if action_type is ActionType.PUBLIC_STATEMENT:
        return 1
    return EXECUTE_TIER.get(action_type, 2)


@dataclass(frozen=True)
class GovernanceBudget:
    """`budget` de una ficha (ADR 007 secc. 6). `None` = sin tope propio
    (se apoya en el presupuesto generico del motor,
    `engine/permissions.py::ACTION_BUDGET_PER_TURN`, o en nada para
    tokens): ver `Notas de implementacion` sobre por que el default no debe
    ser MAS estricto que ese generico (repriduccion del comportamiento
    default, DoD 5 de Fase 7)."""

    actions_per_turn: int | None = None
    tokens_per_turn: int | None = None


@dataclass(frozen=True)
class ActorGovernance:
    """Ficha de gobernanza de un actor (ADR 007 secc. 6, literal)."""

    actor_id: str
    model: str = "rules"
    autonomy: int = 5
    read: tuple[str, ...] = ALL_CATEGORIES
    write: tuple[str, ...] = ()
    execute: tuple[str, ...] = ()
    human_approval_required: bool = False
    max_authority: str = "full_catalog"
    budget: GovernanceBudget = field(default_factory=GovernanceBudget)

    def allows_type(self, action_type: ActionType) -> bool:
        """`True` si `action_type` esta declarado en `write` o `execute` de
        esta ficha (independiente de `autonomy`: eso lo chequea
        `meets_autonomy`)."""
        value = action_type.value
        return value in self.write or value in self.execute

    def meets_autonomy(self, action_type: ActionType) -> bool:
        return self.autonomy >= required_tier(action_type)


#: Ficha default para un actor sin entrada explicita en `governance.yaml`
#: (test que arma actores sueltos, o una ficha nueva agregada sin tocar el
#: YAML todavia): autonomy 5 (catalogo completo, ver `EXECUTE_TIER`) y
#: `read`/`write`/`execute` sin restringir -- equivalente a "sin gobernanza"
#: (el actor pasa por la matriz de rol tal cual antes de ADR 007).
_UNRESTRICTED_WRITE = tuple(t.value for t in ActionType)


def _default_governance(actor_id: str) -> ActorGovernance:
    return ActorGovernance(
        actor_id=actor_id,
        autonomy=5,
        read=ALL_CATEGORIES,
        write=_UNRESTRICTED_WRITE,
        execute=_UNRESTRICTED_WRITE,
        max_authority="full_catalog",
    )


@dataclass(frozen=True)
class Governance:
    """`data/governance.yaml` cargado (ADR 007 secc. 6): una `ActorGovernance`
    por actor. Un actor sin entrada explicita cae a `_default_governance`
    (sin restriccion, ver arriba)."""

    actors: dict[str, ActorGovernance] = field(default_factory=dict)

    def for_actor(self, actor_id: str) -> ActorGovernance:
        return self.actors.get(actor_id) or _default_governance(actor_id)

    @property
    def central_bank_autonomy(self) -> int:
        """Compatibilidad con ADR 003 secc. 6.4 (`actors/rule_based.py`,
        que decide si SIQUIERA intenta `SET_RATE` mirando esta propiedad,
        antes de que `authorize()` la vuelva a chequear via gobernanza)."""
        return self.for_actor("central_bank").autonomy


def _parse_budget(raw: dict[str, Any] | None) -> GovernanceBudget:
    raw = raw or {}
    return GovernanceBudget(
        actions_per_turn=raw.get("actions_per_turn"),
        tokens_per_turn=raw.get("tokens_per_turn"),
    )


def _parse_actor_governance(actor_id: str, raw: dict[str, Any]) -> ActorGovernance:
    return ActorGovernance(
        actor_id=actor_id,
        model=str(raw.get("model", "rules")),
        autonomy=int(raw.get("autonomy", 5)),
        read=tuple(raw.get("read", ALL_CATEGORIES)),
        write=tuple(raw.get("write", ())),
        execute=tuple(raw.get("execute", ())),
        human_approval_required=bool(raw.get("human_approval_required", False)),
        max_authority=str(raw.get("max_authority", "full_catalog")),
        budget=_parse_budget(raw.get("budget")),
    )


def _apply_override(raw: dict[str, dict[str, Any]], dotted_key: str, value: Any) -> None:
    """Aplica UN override `<actor_id>.<campo>[.<subcampo>]=valor` (ADR 007
    deliverable 6: `--governance-override central_bank.autonomy=4`) sobre el
    `dict` crudo recien leido del YAML, antes de parsear a `ActorGovernance`
    (mas simple que mutar dataclasses frozen despues)."""
    parts = dotted_key.split(".")
    if len(parts) not in (2, 3):
        raise ValueError(
            f"override de gobernanza mal formado: {dotted_key!r} "
            "(usar actor.campo o actor.budget.campo)"
        )
    actor_id = parts[0]
    entry = raw.setdefault(actor_id, {})
    if len(parts) == 2:
        field_name = parts[1]
        if field_name == "autonomy":
            entry["autonomy"] = int(value)
        elif field_name == "human_approval_required":
            truthy = ("1", "true", "si", "sí")
            entry["human_approval_required"] = str(value).strip().lower() in truthy
        elif field_name in ("read", "write", "execute"):
            entry[field_name] = [v.strip() for v in str(value).split(",") if v.strip()]
        elif field_name == "model":
            entry["model"] = str(value)
        elif field_name == "max_authority":
            entry["max_authority"] = str(value)
        else:
            raise ValueError(f"campo de gobernanza desconocido: {field_name!r}")
    else:
        _, budget_key, sub = parts
        if budget_key != "budget":
            raise ValueError(f"override de gobernanza mal formado: {dotted_key!r}")
        budget = entry.setdefault("budget", {})
        budget[sub] = int(value)


def parse_governance_overrides(specs: list[str]) -> dict[str, str]:
    """`["central_bank.autonomy=4", ...]` -> `{"central_bank.autonomy": "4"}`
    (CLI `--governance-override`, deliverable 6): parsea el `=` una sola vez
    por entrada, el valor queda como texto (lo tipa `_apply_override`)."""
    out: dict[str, str] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"override de gobernanza mal formado: {spec!r} (usar campo=valor)")
        key, _, value = spec.partition("=")
        out[key.strip()] = value.strip()
    return out


def load_governance(
    path: str | Path | None = None, overrides: dict[str, str] | None = None
) -> Governance:
    """Carga `data/governance.yaml` (ADR 007 secc. 6). `overrides`
    (deliverable 6, `--governance-override actor.campo=valor`) se aplica
    sobre el `dict` crudo antes de tipar cada ficha."""
    p = Path(path) if path is not None else DEFAULT_GOVERNANCE_PATH
    raw: dict[str, dict[str, Any]] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    raw = {actor_id: dict(entry or {}) for actor_id, entry in raw.items()}
    for dotted_key, value in (overrides or {}).items():
        _apply_override(raw, dotted_key, value)
    actors = {actor_id: _parse_actor_governance(actor_id, entry) for actor_id, entry in raw.items()}
    return Governance(actors=actors)


# ---------------------------------------------------------------------------
# Filtro de `read` sobre `Perception` (ADR 007 secc. 6: "una clave fuera de
# `read` no se renderiza"). Mapa clave -> categoria, uno por rol (espeja los
# `_private_*` de `engine/perception.py`, ADR 004 secc. 5): una clave de
# `private_indicators` que no figura en el mapa de su rol cae a
# `"economic_indicators"` (categoria que todo actor deberia poder leer,
# nunca deja un campo huerfano sin categoria asignable).
# ---------------------------------------------------------------------------

_ROLE_PRIVATE_CATEGORIES: dict[str, dict[str, str]] = {
    "central_bank": {
        "reserves_exact": "monetary_history",
        "exchange_rate": "monetary_history",
        "inflation_lag1": "monetary_history",
        "intervention_usd": "monetary_history",
        "public_debt": "monetary_history",
        "interest_rate": "monetary_history",
    },
    "governor": {
        "unemployment_p": "provincial_finances",
        "income_p": "provincial_finances",
        "dependence": "provincial_finances",
        "transfers_received": "provincial_finances",
        "affected_by_shocks": "provincial_finances",
    },
    "party": {
        "seats": "party_polls",
        "congress_support": "party_polls",
        "approval": "party_polls",
        "months_to_election": "party_polls",
        "poll_approval": "party_polls",
    },
    "union": {
        "real_wage": "labour_market",
        "unemployment": "labour_market",
        "inflation": "labour_market",
        "protest_level": "labour_market",
        "public_employment": "labour_market",
    },
    "business": {
        "gdp_growth": "sector",
        "interest_rate": "sector",
        "exchange_rate": "sector",
        "tax_rate": "sector",
        "consumer_confidence": "sector",
        "sector_affected_by_shocks": "sector",
    },
    "media": {
        "approval": "media_events",
        "protest_level": "media_events",
        "institutional_confidence": "media_events",
        "events_this_month": "media_events",
    },
    "social_bloc": {
        "real_wage": "cohort_view",
        "unemployment": "cohort_view",
        "poverty": "cohort_view",
        "inflation": "cohort_view",
        "crime_perception": "cohort_view",
        "approval_c": "cohort_view",
        "government_approval": "cohort_view",
    },
}

#: `president`/`economy_minister` ven todo el estado (ADR 004 secc. 5): se
#: reparte entre las categorias existentes en vez de inventar una decima
#: (documentado en Notas de implementacion de ADR 007).
_PRESIDENT_PRIVATE_CATEGORIES: dict[str, str] = {
    "inflation": "economic_indicators",
    "unemployment": "economic_indicators",
    "gdp_growth": "economic_indicators",
    "gdp": "economic_indicators",
    "government_approval": "economic_indicators",
    "congress_support": "party_polls",
    "protest_level": "media_events",
    "consumer_confidence": "sector",
    "institutional_confidence": "media_events",
    "crime_perception": "cohort_view",
    "real_wage": "labour_market",
    "poverty": "cohort_view",
    "tax_rate": "sector",
    "primary_spending": "provincial_finances",
    "provincial_transfers": "provincial_finances",
    "interest_rate": "monetary_history",
    "exchange_rate": "monetary_history",
    "reserves": "monetary_history",
    "public_debt": "monetary_history",
    "fiscal_balance": "provincial_finances",
    "inflation_lag1": "monetary_history",
    "political_stability": "economic_indicators",
    "policy_tax_rate": "sector",
    "policy_primary_spending": "provincial_finances",
    "policy_provincial_transfers": "provincial_finances",
    "policy_interest_rate_target": "monetary_history",
    "deficit": "provincial_finances",
    "reserves_exact": "monetary_history",
    "intervention_usd": "monetary_history",
}
_ROLE_PRIVATE_CATEGORIES["president"] = _PRESIDENT_PRIVATE_CATEGORIES
_ROLE_PRIVATE_CATEGORIES["economy_minister"] = _PRESIDENT_PRIVATE_CATEGORIES


def category_for_private_key(role: str, key: str) -> str:
    return _ROLE_PRIVATE_CATEGORIES.get(role, {}).get(key, "economic_indicators")


def filter_perception(
    actor: ActorSheet, perception: Perception, gov: ActorGovernance
) -> Perception:
    """Aplica `gov.read` a `perception` (ADR 007 secc. 6): `public_indicators`
    completo cuenta como `economic_indicators`; cada clave de
    `private_indicators` cae en su categoria via `category_for_private_key`;
    `proposal` cuenta como `government_announcements`. El resto de la
    `Perception` (relaciones, memorias, objetivos, shocks/eventos) no es
    parte de las 9 categorias del ADR y no se filtra (documentado en Notas
    de implementacion: acotar el alcance a lo que el DoD 5 efectivamente
    prueba). Con `gov.read` conteniendo las 9 categorias (default de
    `data/governance.yaml`) esta funcion es un no-op -- reproduce
    exactamente la `Perception` de antes de ADR 007."""
    allowed = set(gov.read)
    public = dict(perception.public_indicators) if "economic_indicators" in allowed else {}
    private = {
        k: v
        for k, v in perception.private_indicators.items()
        if category_for_private_key(actor.role, k) in allowed
    }
    proposal = perception.proposal if "government_announcements" in allowed else None
    return perception.model_copy(
        update={
            "public_indicators": public,
            "private_indicators": private,
            "proposal": proposal,
        }
    )
