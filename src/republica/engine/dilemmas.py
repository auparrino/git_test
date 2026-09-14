"""Dilemas del modo juego (SPEC_v0.2_play.md secc. 2): carga del YAML,
modelos pydantic, evaluacion de disparadores y aplicacion de una opcion
elegida sobre la `Policy` y los efectos pendientes.

Los `effects` de una opcion se mapean a los mismos terminos `shock_*` que
consume el motor (ver `world/events.py` / `world/economy.py` / `world/society.py`
/ `world/politics.py`), reusando el mecanismo de `Simulation.pending_terms`.

**Nota (REVIEW_001 hallazgo #10, corrige una version anterior de este
docstring/`SPEC_v0.2_play.md` secc. 2 que decia "el mes siguiente"):** un
efecto elegido este mes se aplica dentro del mismo mes que se esta jugando
(`Game.step` consume `pending_effects` -> `sim.pending_terms` *antes* de
llamar `advance_month` para ese mes), no en el mes siguiente -- distinto de
los `pending` de `check_forced_devaluation`/las consecuencias de actores,
que si se difieren un mes. Se decidio documentar el comportamiento tal cual
esta (opcion recomendada por la revision) en vez de cambiar el codigo: nadie
depende del desfasaje de un mes, y cambiarlo correria todas las corridas
existentes. Los efectos con `months` (solo `fiscal`) se representan como una
cola de `PendingEffect` que se consume un mes a la vez, uno de esos meses ya
dentro del mismo mes jugado (ver `engine/game.py::Game._consume_pending_effects`).
"""

from __future__ import annotations

import math
import operator
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from republica.engine.narrate import annualized_inflation
from republica.world.state import Policy, WorldState

DEFAULT_DILEMMAS_PATH = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "dilemmas.yaml"

#: Mapeo `effects.<clave>` -> termino `shock_*` que consumen las formulas del
#: motor. `shock_cc` es el unico termino nuevo (agregado en `world/society.py`,
#: junto a `consumer_confidence` como bump directo); el resto ya existia.
EFFECT_TERM_MAP: dict[str, str] = {
    "approval": "shock_approval",
    "tension": "shock_tension",
    "protest": "shock_protest",
    "institutional_confidence": "shock_conf",
    "consumer_confidence": "shock_cc",
    "reserves": "shock_reserves",
    "gdp": "shock_gdp",
    "fx": "shock_fx",
    "stability": "shock_stability",
    "inequality": "shock_ineq",
    "fiscal": "shock_fiscal",
}
_VALID_EFFECT_KEYS = set(EFFECT_TERM_MAP) | {"months"}
_VALID_POLICY_FIELDS = set(Policy.model_fields)


class TriggerClause(BaseModel):
    """Una condicion `{var, gt|lt|gte|lte|eq}` (seccion 2)."""

    model_config = ConfigDict(extra="forbid")

    var: str
    gt: Any = None
    lt: Any = None
    gte: Any = None
    lte: Any = None
    eq: Any = None


class Trigger(BaseModel):
    """`trigger.all` / `trigger.any` + `cooldown`/`once`/`priority` (seccion 2)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    all_: list[TriggerClause] = Field(default_factory=list, alias="all")
    any_: list[TriggerClause] = Field(default_factory=list, alias="any")
    cooldown: int = 0
    once: bool = False
    priority: int = 0


class Option(BaseModel):
    """Una opcion de un dilema: efectos sobre `Policy`, sobre el estado del
    mismo mes jugado (ver nota del docstring del modulo, hallazgo #10 de
    REVIEW_001: no "el mes siguiente") y sobre `flags` persistentes."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    policy_delta: dict[str, float] = Field(default_factory=dict)
    policy_set: dict[str, float] = Field(default_factory=dict)
    effects: dict[str, float] = Field(default_factory=dict)
    flags: dict[str, bool] = Field(default_factory=dict)


class Dilemma(BaseModel):
    """Un dilema completo (seccion 2)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    text: str
    trigger: Trigger
    options: list[Option]


def _validate_dilemma(d: Dilemma) -> None:
    keys = [o.key for o in d.options]
    if len(keys) != len(set(keys)):
        raise ValueError(f"dilema {d.id!r}: claves de opcion repetidas ({keys})")
    for opt in d.options:
        unknown_effects = set(opt.effects) - _VALID_EFFECT_KEYS
        if unknown_effects:
            raise ValueError(f"dilema {d.id!r}/{opt.key}: efectos desconocidos {unknown_effects}")
        if "months" in opt.effects and "fiscal" not in opt.effects:
            raise ValueError(f"dilema {d.id!r}/{opt.key}: 'months' requiere 'fiscal'")
        unknown_fields = (set(opt.policy_delta) | set(opt.policy_set)) - _VALID_POLICY_FIELDS
        if unknown_fields:
            raise ValueError(
                f"dilema {d.id!r}/{opt.key}: instrumentos desconocidos {unknown_fields}"
            )


@cache
def _load_dilemmas_cached(path: str) -> tuple[Dilemma, ...]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    dilemmas = tuple(Dilemma.model_validate(item) for item in raw)
    for d in dilemmas:
        _validate_dilemma(d)
    return dilemmas


def load_dilemmas(path: str | Path | None = None) -> list[Dilemma]:
    """Carga y valida `data/scenarios/dilemmas.yaml` (o `path`). Cacheada por
    ruta: el YAML no cambia durante una corrida."""
    p = str(path) if path is not None else str(DEFAULT_DILEMMAS_PATH)
    return list(_load_dilemmas_cached(p))


@dataclass(frozen=True)
class AuxVars:
    """Las auxiliares del vocabulario de triggers que no son estado (seccion 2):
    `inflation_annual`, `deficit`, `months_left`. `month` se pasa aparte."""

    inflation_annual: float
    deficit: float
    months_left: int


def compute_aux_vars(state: WorldState, month: int, months_total: int) -> AuxVars:
    """`month` es 1-based: el mes que se esta por jugar (aun no simulado)."""
    return AuxVars(
        inflation_annual=annualized_inflation(state.inflation),
        deficit=-state.fiscal_balance,
        months_left=max(months_total - month + 1, 0),
    )


def render_text(dilemma: Dilemma, state: WorldState, aux: AuxVars, month: int) -> str:
    """Interpola `dilemma.text` con el estado, las auxiliares y `month`."""
    ctx: dict[str, Any] = state.model_dump()
    ctx.update(
        inflation_annual=aux.inflation_annual,
        deficit=aux.deficit,
        months_left=aux.months_left,
        month=month,
    )
    return dilemma.text.format(**ctx)


def _resolve_var(
    var: str,
    state: WorldState,
    aux: AuxVars,
    month: int,
    active_ids: set[str],
    last_events: list[str],
    flags: dict[str, bool],
) -> Any:
    if var.startswith("shock_active:"):
        return var.split(":", 1)[1] in active_ids
    if var.startswith("event_last:"):
        return var.split(":", 1)[1] in last_events
    if var.startswith("flag:"):
        return flags.get(var.split(":", 1)[1], False)
    if var == "month":
        return month
    if var in ("inflation_annual", "deficit", "months_left"):
        return getattr(aux, var)
    if var in WorldState.model_fields:
        return getattr(state, var)
    raise KeyError(f"variable de trigger desconocida: {var!r}")


_CMP: dict[str, Callable[[Any, Any], bool]] = {
    "gt": operator.gt,
    "lt": operator.lt,
    "gte": operator.ge,
    "lte": operator.le,
    "eq": operator.eq,
}


def _clause_holds(clause: TriggerClause, value: Any) -> bool:
    for op_name, cmp in _CMP.items():
        threshold = getattr(clause, op_name)
        if threshold is not None and not cmp(value, threshold):
            return False
    return True


def _trigger_holds(
    trigger: Trigger,
    state: WorldState,
    aux: AuxVars,
    month: int,
    active_ids: set[str],
    last_events: list[str],
    flags: dict[str, bool],
) -> bool:
    if not trigger.all_ and not trigger.any_:
        return False
    if trigger.all_ and not all(
        _clause_holds(c, _resolve_var(c.var, state, aux, month, active_ids, last_events, flags))
        for c in trigger.all_
    ):
        return False
    if trigger.any_ and not any(
        _clause_holds(c, _resolve_var(c.var, state, aux, month, active_ids, last_events, flags))
        for c in trigger.any_
    ):
        return False
    return True


def evaluate_triggers(
    state: WorldState,
    aux: AuxVars,
    month: int,
    active_shocks: Any,
    last_events: list[str],
    flags: dict[str, bool],
    cooldowns: dict[str, float],
    catalog: list[Dilemma] | None = None,
) -> list[Dilemma]:
    """Devuelve hasta 2 dilemas disparados este mes, los de mayor `priority`
    (seccion 2). Muta `cooldowns` para los dilemas devueltos: `month` si
    `once` es falso, `inf` (nunca mas elegible) si es verdadero. Los que
    dispararon pero no entraron en el tope de 2 NO consumen cooldown: pueden
    volver a aparecer (y competir por prioridad) el mes que viene.
    """
    dilemmas = catalog if catalog is not None else load_dilemmas()
    active_ids = set(active_shocks)

    eligible: list[Dilemma] = []
    for d in dilemmas:
        last_shown = cooldowns.get(d.id)
        if last_shown is not None and month - last_shown < d.trigger.cooldown:
            continue
        if _trigger_holds(d.trigger, state, aux, month, active_ids, last_events, flags):
            eligible.append(d)

    eligible.sort(key=lambda d: -d.trigger.priority)
    chosen = eligible[:2]
    for d in chosen:
        cooldowns[d.id] = math.inf if d.trigger.once else float(month)
    return chosen


@dataclass(frozen=True)
class PendingEffect:
    """Un efecto puntual todavia por aplicar: `term` es un `shock_*` del
    motor, `value` se suma cada mes que queden `remaining > 0`."""

    term: str
    value: float
    remaining: int


def apply_option(
    option: Option,
    policy: Policy,
    pending_effects: list[PendingEffect],
    flags: dict[str, bool],
) -> tuple[Policy, list[PendingEffect], dict[str, bool]]:
    """Aplica la opcion elegida: `policy_delta` (suma, persistente) y
    `policy_set` (fija) sobre `policy`; encola sus `effects` en
    `pending_effects` (se consumen mes a mes, ver `Game._consume_pending_effects`);
    y actualiza `flags`. No aplica los topes de cambio mensual (seccion 1,
    paso 3): eso lo hace `engine/game.py::Game.step`, que ve todos los
    instrumentos tocados este mes (dilemas + edicion manual) a la vez.
    """
    updates = policy.model_dump()
    for field_name, value in option.policy_delta.items():
        updates[field_name] = updates.get(field_name, 0.0) + value
    for field_name, value in option.policy_set.items():
        updates[field_name] = value
    new_policy = policy.model_copy(update=updates)

    months = int(option.effects.get("months", 1))
    new_pending = list(pending_effects)
    for key, value in option.effects.items():
        if key == "months":
            continue
        term = EFFECT_TERM_MAP[key]
        remaining = months if key == "fiscal" else 1
        new_pending.append(PendingEffect(term=term, value=float(value), remaining=remaining))

    new_flags = dict(flags)
    new_flags.update(option.flags)
    return new_policy, new_pending, new_flags
