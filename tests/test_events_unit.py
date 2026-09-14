"""Tests unitarios de `world/events.py`: sorteo de shocks y `world/state.py`: clamp."""

from __future__ import annotations

import random

import pytest

from republica.world.config import load_country
from republica.world.events import (
    MAX_NEW_SHOCKS_PER_MONTH,
    ActiveShock,
    ShockCatalog,
    build_catalog,
)
from republica.world.state import WorldState, clamp, clamp_state

COUNTRY = load_country()
CATALOG = ShockCatalog(build_catalog(COUNTRY.shocks))


def _base_state() -> WorldState:
    return COUNTRY.initial_state.model_copy()


def test_forced_shock_activates_without_rolling() -> None:
    """Un shock forzado se activa aunque su probabilidad natural sea ~0 y sin
    necesitar que el RNG lo sortee."""
    rng = random.Random(12345)
    active: dict[str, ActiveShock] = {}
    new_ids = CATALOG.roll(_base_state(), rng, active, month=5, forced=["energy_discovery"])
    assert "energy_discovery" in active
    assert "energy_discovery" in new_ids


def test_active_shock_does_not_reactivate() -> None:
    """Mientras un shock esta activo, sortearlo de nuevo no lo reactiva (no
    reinicia su contador ni aparece de nuevo en `new_ids`)."""
    rng = random.Random(1)
    active: dict[str, ActiveShock] = {}
    CATALOG.roll(_base_state(), rng, active, month=1, forced=["drought"])
    astate = active["drought"]
    astate.months_active = 1  # simula que ya paso un mes

    new_ids = CATALOG.roll(_base_state(), rng, active, month=2)
    assert "drought" not in new_ids
    assert active["drought"].months_active == 1  # no se toco


def test_at_most_two_new_shocks_per_month() -> None:
    """Con probabilidad 1 para todo el catalogo, como maximo se activan
    `MAX_NEW_SHOCKS_PER_MONTH` shocks nuevos organicamente en un mes."""

    class AlwaysOne(random.Random):
        def random(self) -> float:  # type: ignore[override]
            return 0.0  # siempre < cualquier probabilidad

    rng = AlwaysOne()
    active: dict[str, ActiveShock] = {}
    new_ids = CATALOG.roll(_base_state(), rng, active, month=1)
    assert len(new_ids) == MAX_NEW_SHOCKS_PER_MONTH
    assert len(active) == MAX_NEW_SHOCKS_PER_MONTH


def test_forced_shocks_do_not_count_against_the_cap() -> None:
    """Los shocks forzados se activan ademas del limite organico de 2/mes."""

    class AlwaysOne(random.Random):
        def random(self) -> float:  # type: ignore[override]
            return 0.0

    rng = AlwaysOne()
    active: dict[str, ActiveShock] = {}
    forced_id = CATALOG.defs[-1].id  # uno que no sea de los 2 primeros organicos
    new_ids = CATALOG.roll(_base_state(), rng, active, month=1, forced=[forced_id])
    assert forced_id in new_ids
    assert len(active) == MAX_NEW_SHOCKS_PER_MONTH + 1


def test_conditional_probability_adds_when_condition_holds() -> None:
    general_strike = CATALOG.by_id["general_strike"]
    calm = _base_state().model_copy(update={"social_tension": 10.0})
    tense = _base_state().model_copy(update={"social_tension": 90.0})
    assert general_strike.probability(tense) > general_strike.probability(calm)
    assert general_strike.probability(calm) == pytest.approx(0.02)
    assert general_strike.probability(tense) == pytest.approx(0.02 + 0.05)


def test_clamp_scalar() -> None:
    assert clamp(5.0, 0.0, 10.0) == 5.0
    assert clamp(-5.0, 0.0, 10.0) == 0.0
    assert clamp(15.0, 0.0, 10.0) == 10.0


def test_clamp_state_recorts_y_reporta_overflow() -> None:
    state = COUNTRY.initial_state.model_copy(update={"unemployment": 999.0, "inflation": -50.0})
    clamped, overflow = clamp_state(state, COUNTRY.ranges)
    lo, hi = COUNTRY.ranges["unemployment"]
    assert clamped.unemployment == hi
    assert overflow["unemployment"] == pytest.approx(999.0 - hi)
    lo_i, _hi_i = COUNTRY.ranges["inflation"]
    assert clamped.inflation == lo_i
    assert "inflation" in overflow


def test_clamp_state_raises_on_nan() -> None:
    state = COUNTRY.initial_state.model_copy(update={"gdp": float("nan")})
    with pytest.raises(ValueError, match="NaN"):
        clamp_state(state, COUNTRY.ranges)


def test_clamp_state_raises_on_inf() -> None:
    state = COUNTRY.initial_state.model_copy(update={"reserves": float("inf")})
    with pytest.raises(ValueError, match="NaN"):
        clamp_state(state, COUNTRY.ranges)
