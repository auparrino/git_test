"""Test de aceptacion 7 (secc. 11): distribucion de outcomes con ConstantPolicy y PassivePolicy."""

from __future__ import annotations

import pytest

from republica.engine.policy import ConstantPolicy, PassivePolicy
from republica.engine.simulation import run
from republica.world.config import load_country

COUNTRY = load_country()


def _rule(name: str):
    if name == "passive":
        return PassivePolicy(
            COUNTRY.default_policy,
            COUNTRY.structure.r_neutral,
            COUNTRY.policy_ranges["interest_rate_target"],
        )
    return ConstantPolicy(COUNTRY.default_policy)


def _survived_fraction(n: int, rule: str = "constant") -> float:
    survived = 0
    for seed in range(n):
        history = run(seed=seed, months=48, policy_rule=_rule(rule))
        if history.outcome == "survived":
            survived += 1
    return survived / n


def test_outcome_distribution_within_range_300_seeds() -> None:
    fraction = _survived_fraction(300)
    assert 0.50 <= fraction <= 0.95, f"survived={fraction:.2%} fuera de [50%, 95%]"


def test_passive_baseline_is_calmer_than_constant() -> None:
    passive = _survived_fraction(300, "passive")
    constant = _survived_fraction(300, "constant")
    assert 0.50 <= passive <= 0.95, f"survived(passive)={passive:.2%} fuera de [50%, 95%]"
    assert passive >= constant


@pytest.mark.slow
def test_outcome_distribution_within_range_1000_seeds() -> None:
    fraction = _survived_fraction(1000)
    assert 0.50 <= fraction <= 0.95, f"survived={fraction:.2%} fuera de [50%, 95%]"
