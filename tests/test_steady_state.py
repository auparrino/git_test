"""Test de aceptacion 3 (secc. 11): estado estacionario con shocks/ruido apagados."""

from __future__ import annotations

from republica.engine.simulation import run


def test_month_one_is_close_to_steady_state() -> None:
    history = run(seed=1, months=3, shocks_enabled=False, exogenous_noise=False)
    state = history.records[0].state
    assert abs(state["inflation"] - 2.0) < 0.15
    assert abs(state["unemployment"] - 8.0) < 0.1
    assert abs(state["government_approval"] - 50.0) < 1.0


def test_steady_state_holds_across_seeds() -> None:
    """El apagado de shocks/ruido hace que el resultado no dependa de la semilla
    (no se consume RNG cuando `shocks_enabled=False` y `exogenous_noise=False`)."""
    h1 = run(seed=1, months=3, shocks_enabled=False, exogenous_noise=False)
    h2 = run(seed=999, months=3, shocks_enabled=False, exogenous_noise=False)
    assert [r.to_dict() for r in h1.records] == [r.to_dict() for r in h2.records]
