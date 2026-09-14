"""Modelos pydantic del estado del mundo (SPEC_v0.1.md secc. 2 y 9).

`WorldState` tiene las 20 variables de estado del pais mas `inflation_lag1`,
un campo interno usado por la indexacion salarial (seccion 4.5) que no forma
parte de las 20 variables publicas pero se persiste igual.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict


def pos(x: float) -> float:
    """`pos(z) = max(0, z)` (notacion de la seccion 1)."""
    return x if x > 0.0 else 0.0


def clamp(value: float, lo: float, hi: float) -> float:
    """Recorta `value` al rango `[lo, hi]`."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


class WorldState(BaseModel):
    """Las 20 variables de estado del pais (seccion 2) + `inflation_lag1`.

    `frozen=True` (ADR 003 secc. 1): fuera de `engine/` nadie puede mutar el
    estado por asignacion de atributo (`state.gdp = 1` lanza `ValidationError`).
    La unica via para cambiar el estado del mundo es `engine.authorize()` +
    `engine.consequences()`, que producen un `WorldState` *nuevo* via
    `model_copy`/`model_construct` (que no pasan por `__setattr__`).
    """

    model_config = ConfigDict(validate_assignment=False, frozen=True)

    # economia
    gdp: float
    gdp_growth: float
    inflation: float
    unemployment: float
    real_wage: float
    interest_rate: float
    exchange_rate: float
    reserves: float
    public_debt: float
    fiscal_balance: float
    poverty: float
    # politica
    government_approval: float
    congress_support: float
    political_stability: float
    social_tension: float
    institutional_confidence: float
    # sociedad
    consumer_confidence: float
    protest_level: float
    inequality: float
    crime_perception: float
    # interno (no es una de las 20, pero se persiste)
    inflation_lag1: float


class Exogenous(BaseModel):
    """Variables exogenas (seccion 2.1): no son estado del pais pero se persisten."""

    commodity_price: float
    world_demand: float


class Policy(BaseModel):
    """Instrumentos de politica (seccion 2.3): input del mes, no estado."""

    interest_rate_target: float
    tax_rate: float
    primary_spending: float
    provincial_transfers: float
    fx_intervention: float


def raise_if_invalid(value: float, name: str) -> None:
    """Levanta `ValueError` si `value` es NaN o infinito."""
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} produjo un valor invalido (NaN/inf): {value!r}")


def clamp_state(
    state: WorldState, ranges: dict[str, tuple[float, float]]
) -> tuple[WorldState, dict[str, float]]:
    """Recorta todas las variables de `state` a `ranges` (seccion 7, paso 7).

    Devuelve el estado recortado y un diccionario `{variable: overflow}` con
    cuanto se paso cada variable de su rango *antes* de recortar (0 si no se
    paso). Levanta `ValueError` si alguna variable es NaN/inf.
    """
    data = state.model_dump()
    overflow: dict[str, float] = {}
    for key, value in data.items():
        raise_if_invalid(value, key)
        lo, hi = ranges[key]
        if value < lo:
            overflow[key] = lo - value
        elif value > hi:
            overflow[key] = value - hi
        data[key] = clamp(value, lo, hi)
    return WorldState.model_construct(**data), overflow
