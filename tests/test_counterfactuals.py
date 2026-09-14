"""Tests de aceptacion 4, 5 y 6 (secc. 11): sequia, suba de tasa, emision."""

from __future__ import annotations

from republica.engine.narrate import annualized_inflation
from republica.engine.policy import ConstantPolicy, PolicyRule
from republica.engine.simulation import run
from republica.world.config import load_country
from republica.world.state import Policy, WorldState

COUNTRY = load_country()


def test_drought_lowers_reserves_and_approval() -> None:
    """Test 4: `--force-shock drought@5` vs. misma semilla sin forzar."""
    base = run(seed=7, months=12)
    forced = run(seed=7, months=12, forced_shocks={5: ["drought"]})

    for month in range(6, 10):
        base_reserves = base.records[month - 1].state["reserves"]
        forced_reserves = forced.records[month - 1].state["reserves"]
        assert forced_reserves < base_reserves, f"mes {month}: reservas no bajaron"

    assert any(
        forced.records[month - 1].state["government_approval"]
        < base.records[month - 1].state["government_approval"]
        for month in range(6, 10)
    )


class _RateHikeOnceThenDefault:
    """Sube la tasa 15pp solo en el mes 1, despues vuelve al default."""

    def __init__(self, default_policy: Policy, delta: float):
        self._default = default_policy
        self._hiked = default_policy.model_copy(
            update={"interest_rate_target": default_policy.interest_rate_target + delta}
        )

    def decide(self, state: WorldState, month: int) -> Policy:
        return self._hiked.model_copy() if month == 1 else self._default.model_copy()


def test_rate_hike_lowers_inflation_and_raises_unemployment() -> None:
    """Test 5: +15pp de tasa en el mes 1 vs. constante, misma semilla, sin shocks."""
    base_rule: PolicyRule = ConstantPolicy(COUNTRY.default_policy)
    hike_rule: PolicyRule = _RateHikeOnceThenDefault(COUNTRY.default_policy, 15.0)

    base = run(seed=42, months=12, policy_rule=base_rule, shocks_enabled=False)
    hike = run(seed=42, months=12, policy_rule=hike_rule, shocks_enabled=False)

    assert hike.records[11].state["inflation"] < base.records[11].state["inflation"]
    assert hike.records[11].state["unemployment"] > base.records[11].state["unemployment"]


def test_deficit_spending_is_far_more_inflationary() -> None:
    """Test 6: `primary_spending=32` (deficit ~10% PIB) vs. default, sin shocks.

    Desviacion documentada: con este nivel de gasto el pais entra en
    hiperinflacion bastante antes del mes 24 (la emision es tan fuerte que el
    juego termina la partida), lo cual es una confirmacion mas fuerte del
    efecto que la comparacion puntual al mes 24 que pide el spec literalmente.
    Si por algun motivo llegara sano hasta el mes 24, se exige la diferencia
    de >=15pp de inflacion anualizada que pide el spec.
    """
    big_spend = COUNTRY.default_policy.model_copy(update={"primary_spending": 32.0})

    base = run(
        seed=11, months=24, policy_rule=ConstantPolicy(COUNTRY.default_policy), shocks_enabled=False
    )
    deficit = run(seed=11, months=24, policy_rule=ConstantPolicy(big_spend), shocks_enabled=False)

    if len(deficit.records) < 24:
        assert deficit.outcome == "hyperinflation"
        return

    base_ann = annualized_inflation(base.records[23].state["inflation"])
    deficit_ann = annualized_inflation(deficit.records[23].state["inflation"])
    assert deficit_ann - base_ann >= 15.0
