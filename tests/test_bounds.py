"""Test de aceptacion 2 (secc. 11): cotas y NaN sobre muchas semillas.

`clamp_state` levanta `ValueError` si aparece NaN/inf, asi que si `run()`
termina sin excepcion ya se cumplio "cero NaN/inf". Ademas se verifica que
ninguna variable se paso de su rango, antes del clamp, por mas de 3 anchos de
rango (`overflow` que guarda cada `MonthRecord`).
"""

from __future__ import annotations

import pytest

from republica.engine.simulation import run
from republica.world.config import load_country

_COUNTRY = load_country()
_RANGE_WIDTHS = {k: hi - lo for k, (lo, hi) in _COUNTRY.ranges.items()}


def _check_bounds(seeds: range) -> None:
    for seed in seeds:
        history = run(seed=seed, months=48)  # no lanza -> sin NaN/inf
        for record in history.records:
            for key, overflow in record.overflow.items():
                assert overflow <= 3 * _RANGE_WIDTHS[key], (
                    f"seed={seed} mes={record.month_index} {key} se paso "
                    f"{overflow} (> 3 rangos de {_RANGE_WIDTHS[key]})"
                )


def test_bounds_and_no_nan_300_seeds() -> None:
    _check_bounds(range(300))


@pytest.mark.slow
def test_bounds_and_no_nan_1000_seeds() -> None:
    _check_bounds(range(1000))
