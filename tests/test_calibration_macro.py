"""Tests de A5 (ADR 012 secc. 6): recalibracion con la estructura macro.

Cubre los cuatro puntos pedidos por la tarea de recalibracion:
(a) el espacio de parametros incluye el grupo "macro" con rangos validos;
(b) `--loss heavy` != `rmse` en un caso sintetico y penaliza mas un error
    extremo que `rmse`;
(c) `resolve_forced_shocks` nunca fuerza los shocks ENDOGENOS
    (`ENDOGENOUS_SHOCKS`);
(d) `load_calibrated_country("argentina", <run_id>)` devuelve los
    coeficientes macro calibrados y `run()` los usa -- con un run_id
    SINTETICO chico creado en el propio test (no `a5_macro`, pesado).

Mas el fix de A5b (bug encontrado en el reporte de `a5_macro`): una corrida
que termina ANTES del horizonte `h` (hiperinflacion/colapso) tiene que
recibir una penalizacion explicita en `h`, no que el termino se saltee
(ver `test_run_ending_before_horizon_is_penalized_not_skipped`)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from republica.calibration.objective import _weighted_heavy, _weighted_rmse
from republica.calibration.parameters import (
    MACRO_TUNABLE,
    build_parameter_space,
)
from republica.calibration.run import CALIBRATION_ROOT, load_calibrated_country
from republica.validation.argentina import (
    ENDOGENOUS_SHOCKS,
    TESTS_BY_ID,
    resolve_forced_shocks,
)
from republica.world.countries import country_pack_dir
from republica.world.economy import MacroCoefficients

# ---------------------------------------------------------------------------
# (a) Espacio de parametros con el grupo "macro".
# ---------------------------------------------------------------------------


def test_parameter_space_includes_macro_group_with_valid_bounds() -> None:
    params = build_parameter_space(include_macro=True)
    macro_params = [p for p in params if p.group == "macro"]
    assert len(macro_params) == len(MACRO_TUNABLE) == 58
    by_name = {p.name: p for p in macro_params}

    for p in macro_params:
        assert p.lo <= p.aurora_value <= p.hi, (p.name, p.lo, p.aurora_value, p.hi)
        assert p.lo <= p.hi

    # Los cuatro rangos fisicos explicitamente pedidos por la tarea A5.
    assert by_name["w_adapt"].lo == 0.0
    assert by_name["w_adapt"].hi == 1.0
    assert by_name["rho_pi"].lo == 0.5
    assert by_name["rho_pi"].hi == 1.0
    assert by_name["rho_slope"].lo == 0.0
    assert by_name["rho_slope"].hi == 0.3
    assert by_name["rm"].lo == 1.0
    assert by_name["rm"].hi == 6.0

    # Sin `include_macro`: comportamiento previo a A5 intacto (97 + 10,
    # ningun parametro de grupo "macro").
    params_default = build_parameter_space()
    assert not any(p.group == "macro" for p in params_default)
    assert len(params_default) == 107


def test_macro_bounded_params_stay_within_range_when_clipped() -> None:
    """`Parameter.clip` respeta los bordes fisicos incluso para valores
    bien fuera de rango (CMA-ES puede proponerlos)."""
    params = build_parameter_space(include_macro=True)
    by_name = {p.name: p for p in params if p.group == "macro"}
    assert by_name["rho_pi"].clip(5.0) == 1.0
    assert by_name["rho_pi"].clip(-5.0) == 0.5
    assert by_name["rm"].clip(100.0) == 6.0
    assert by_name["w_adapt"].clip(-1.0) == 0.0


# ---------------------------------------------------------------------------
# (b) `--loss heavy` vs `rmse`.
# ---------------------------------------------------------------------------


def test_heavy_loss_differs_from_rmse_and_penalizes_extreme_error_more() -> None:
    """Caso sintetico (A5, ADR 012 secc. 6): 4 meses, sigma=1. Una
    distribucion "base" con errores tipicos (1 sigma) y una "con extremo"
    que reemplaza un error tipico por uno de 10 sigma. Ambas metricas dan
    distinto numero para el caso con extremo (heavy != rmse), y el
    COCIENTE (extremo / base) es mayor bajo `heavy` que bajo `rmse`: el
    error extremo pesa relativamente MAS bajo la perdida de cola pesada
    (ver `objective.py::HEAVY_TAIL_POWER`, documentado: sin la raiz final
    de una p-norma, `|e|^1.5` amplifica `|e|>1` y achica `|e|<1` respecto
    de una metrica ya escalada de vuelta a la unidad original como RMSE)."""
    sigma = 1.0
    base = [(1.0, 1.0)] * 4
    with_extreme = [(1.0, 1.0), (1.0, 1.0), (1.0, 1.0), (10.0, 1.0)]

    rmse_base = _weighted_rmse(base, sigma)
    rmse_extreme = _weighted_rmse(with_extreme, sigma)
    heavy_base = _weighted_heavy(base, sigma)
    heavy_extreme = _weighted_heavy(with_extreme, sigma)

    assert heavy_extreme != pytest.approx(rmse_extreme)
    assert rmse_base == pytest.approx(1.0)
    assert heavy_base == pytest.approx(1.0)

    rmse_ratio = rmse_extreme / rmse_base
    heavy_ratio = heavy_extreme / heavy_base
    assert heavy_ratio > rmse_ratio, (
        f"el error extremo deberia pesar relativamente MAS bajo heavy "
        f"({heavy_ratio:.3f}x) que bajo rmse ({rmse_ratio:.3f}x)"
    )

    # Y en el otro extremo: un error TIPICO (< 1 sigma) pesa MENOS bajo
    # heavy que bajo una rmse ya escalada de vuelta a la unidad original
    # (la contracara de "la cola pesa mas, el cuerpo pesa menos").
    small = [(0.5, 1.0)]
    assert _weighted_heavy(small, sigma) < _weighted_rmse(small, sigma)


def test_scalar_objective_loss_option_selects_the_right_metric() -> None:
    from republica.calibration.objective import scalar_objective
    from republica.calibration.parameters import build_parameter_space

    params = build_parameter_space()
    x = [p.aurora_value for p in params]
    metrics = {
        "inflation_h1": 2.0,
        "inflation_h1_heavy": 9.0,
    }
    # Solo se suma lo que corresponde a VARIABLES/HORIZONS reales, pero
    # alcanza para confirmar que el sufijo cambia lo que se lee.
    for var_h in ("gdp_growth_h1", "unemployment_h1", "exchange_rate_h1", "reserves_h1"):
        metrics[var_h] = 0.0
        metrics[f"{var_h}_heavy"] = 0.0
    for h in (3, 6, 12):
        for var in ("inflation", "gdp_growth", "unemployment", "exchange_rate", "reserves"):
            metrics[f"{var}_h{h}"] = 0.0
            metrics[f"{var}_h{h}_heavy"] = 0.0

    rmse_scalar = scalar_objective(metrics, params, x, lambda_reg=0.0, loss="rmse")
    heavy_scalar = scalar_objective(metrics, params, x, lambda_reg=0.0, loss="heavy")
    assert rmse_scalar == pytest.approx(2.0)
    assert heavy_scalar == pytest.approx(9.0)

    with pytest.raises(ValueError):
        scalar_objective(metrics, params, x, lambda_reg=0.0, loss="not-a-loss")


# ---------------------------------------------------------------------------
# A5b: una corrida que termina antes del horizonte `h` se penaliza, no se
# saltea (bug encontrado en el reporte de `a5_macro`: TODOS los horizontes
# de 12 meses del brazo calibrado daban "sin dato" -- 0 de 124 meses de
# arranque llegaban al mes 12 -- porque el termino de error simplemente se
# omitia cuando la corrida terminaba antes; CMA-ES quedaba premiado por
# hiperinflacionar/colapsar en vez de castigado).
# ---------------------------------------------------------------------------


def test_run_ending_before_horizon_is_penalized_not_skipped(monkeypatch) -> None:
    from republica.calibration import objective as objective_mod
    from republica.calibration.objective import (
        EARLY_TERMINATION_ERROR_FLOOR_SIGMA,
        RealData,
        build_context,
        score_start_month,
    )
    from republica.engine.simulation import History, MonthRecord
    from republica.world.bimonetary import BimonetaryCoefficients
    from republica.world.config import load_country

    ctx = build_context("argentina", "1998-01")
    real = RealData.load()
    # 1998-01 + 12 meses = 1999-01: tiene que haber dato real de inflacion
    # mensual para que el test verifique algo (si no, el termino se saltea
    # por falta de dato real, no por el bug -- ver el `if` de abajo).
    assert real.value("inflation", 1999, 1) is not None

    # Historia CANADA que termina en el mes 5 (de los 12 pedidos): simula
    # el caso "hiperinflacion/colapso antes de tiempo" sin depender de que
    # ningun candidato real dispare esa dinamica (determinista, no depende
    # de las ecuaciones de `world/economy.py`).
    def fake_simulate_from(ctx_, coeff, bimon, seed=0, months=12, macro=None):
        records = [
            MonthRecord(
                month_index=i,
                date=f"1998-{i:02d}-01",
                state={
                    "inflation": 5.0,
                    "gdp_growth": 1.0,
                    "unemployment": 10.0,
                    "exchange_rate": 100.0,
                    "reserves": 5000.0,
                },
                exo={},
                policy={},
                aux={},
                shocks_new=[],
                shocks_active=[],
                events=[],
                provinces=[],
                overflow={},
            )
            for i in range(1, 6)
        ]
        return History(records=records, outcome="hyperinflation", seed=seed, config_hash="test")

    monkeypatch.setattr(objective_mod, "simulate_from", fake_simulate_from)

    base_coeff = load_country().coefficients
    base_bimon = BimonetaryCoefficients()
    score = score_start_month(ctx, real, base_coeff, base_bimon, persistence=False, seed=0)

    assert score.ended_before_h[12] is True
    assert score.ended_before_h[3] is False  # mes 3 SI esta disponible (la corrida llega al 5)

    errors_h12 = score.errors[("inflation", 12)]
    assert errors_h12, "el termino de h=12 no deberia saltearse: hay dato real y estado extrapolado"
    error_raw, weight = errors_h12[0]
    assert error_raw != 0.0
    sigma = real.std("inflation")
    assert abs(error_raw) >= EARLY_TERMINATION_ERROR_FLOOR_SIGMA * sigma - 1e-9
    assert weight > 0.0


def test_floor_early_termination_error_preserves_sign_and_respects_floor() -> None:
    from republica.calibration.objective import (
        EARLY_TERMINATION_ERROR_FLOOR_SIGMA,
        _floor_early_termination_error,
    )

    sigma = 2.0
    floor_abs = EARLY_TERMINATION_ERROR_FLOOR_SIGMA * sigma
    # Error crudo ya mas alla del piso: queda igual (no se recorta hacia
    # abajo, solo se garantiza un PISO).
    assert _floor_early_termination_error(floor_abs * 2, sigma) == pytest.approx(floor_abs * 2)
    assert _floor_early_termination_error(-floor_abs * 2, sigma) == pytest.approx(-floor_abs * 2)
    # Error crudo chico (p.ej. el estado congelado coincidio con lo real
    # por casualidad): se sube al piso, preservando el signo.
    assert _floor_early_termination_error(0.1, sigma) == pytest.approx(floor_abs)
    assert _floor_early_termination_error(-0.1, sigma) == pytest.approx(-floor_abs)
    assert _floor_early_termination_error(0.0, sigma) == pytest.approx(floor_abs)
    # `sigma <= 0`: no hay unidad con la que fijar un piso, se deja tal cual.
    assert _floor_early_termination_error(0.1, 0.0) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# (c) `resolve_forced_shocks` nunca fuerza los shocks ENDOGENOS.
# ---------------------------------------------------------------------------


def test_resolve_forced_shocks_never_forces_endogenous_shocks() -> None:
    from dataclasses import replace

    pack_dir = country_pack_dir("argentina")
    test = TESTS_BY_ID["V2"]

    for endogenous_id in ENDOGENOUS_SHOCKS:
        from republica.validation.argentina import ShockRequest

        poisoned = replace(
            test,
            shock_requests=(
                *test.shock_requests,
                ShockRequest(
                    shock_id=endogenous_id,
                    date_from="1998-01",
                    date_to="1999-12",
                    label=f"intento de forzar {endogenous_id} (test)",
                ),
            ),
        )
        plan = resolve_forced_shocks(pack_dir, poisoned, 54)
        forced_ids = {sid for ids in plan.forced.values() for sid in ids}
        assert endogenous_id not in forced_ids, (
            f"{endogenous_id} es ENDOGENO (ver ENDOGENOUS_SHOCKS) y no deberia poder forzarse"
        )
        assert endogenous_id in plan.excluded_endogenous


def test_endogenous_shocks_constant_matches_what_should_never_be_forced() -> None:
    """`hyperinflation_regime`/`sovereign_default`/`banking_crisis`/`coup`
    son justamente lo que V1 (hiperinflacion) y V2 (default/colapso) miden
    -- forzarlos convertiria la prediccion en un dato regalado."""
    assert "hyperinflation_regime" in ENDOGENOUS_SHOCKS
    assert "sovereign_default" in ENDOGENOUS_SHOCKS
    assert "banking_crisis" in ENDOGENOUS_SHOCKS


# ---------------------------------------------------------------------------
# (d) `load_calibrated_country` devuelve macro y `run()` lo usa.
# ---------------------------------------------------------------------------


def test_load_calibrated_country_returns_macro_and_run_uses_it(tmp_path: Path) -> None:
    """Run_id SINTETICO chico (no `a5_macro`, pesado): se escribe un
    `coefficients.json` minimo a mano, con un `macro` cuyo `w_adapt` esta
    lejos del default, y se verifica que (1) `load_calibrated_country` lo
    devuelve como `MacroCoefficients` y (2) una corrida real con esos
    coeficientes (via `cli.py`'s mismo patron: `macro_coefficients=
    calibrated_macro`) produce una trayectoria DISTINTA de una corrida con
    el macro del paquete sin calibrar -- confirma que el valor calibrado
    realmente llega a `step_macro_economy`, no solo que se lee el JSON."""
    from republica.engine.simulation import run
    from republica.world.config import load_country
    from republica.world.countries import load_country_pack

    run_id = "pytest-synthetic-macro-load"
    run_dir = CALIBRATION_ROOT / run_id
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    try:
        base_coeff = load_country().coefficients.model_dump()
        base_macro = MacroCoefficients()
        macro_dict = {name: getattr(base_macro, name) for name in base_macro.__dataclass_fields__}
        # `w_adapt` bien lejos del default (0.7): fuerza una trayectoria
        # distinta sin depender de que el resto del vector tambien cambie.
        macro_dict["w_adapt"] = 0.1
        macro_dict["c_s"] = 0.02
        coefficients_json = {
            "run_id": run_id,
            "country_id": "argentina",
            "train": ["1992-01", "1992-01"],
            "holdout": ["1983-12", "1983-12"],
            "coefficients": base_coeff,
            "bimonetary": {},
            "macro": macro_dict,
        }
        # `bimonetary` vacio: `BimonetaryCoefficients(**{})` usa sus
        # defaults, valido (mismo criterio que `load_calibrated_country`).
        (run_dir / "coefficients.json").write_text(json.dumps(coefficients_json), encoding="utf-8")

        coeff, bimon, macro = load_calibrated_country("argentina", run_id)
        assert macro is not None
        assert isinstance(macro, MacroCoefficients)
        assert macro.w_adapt == pytest.approx(0.1)
        assert macro.c_s == pytest.approx(0.02)

        pack = load_country_pack("argentina", "2003-06", 24)
        default_history = run(
            seed=1,
            months=24,
            country=pack.country,
            actors_enabled=True,
            regime_calendar=pack.regime_calendar,
            macro_coefficients=pack.macro_coefficients,
            macro_x0=pack.macro_x0,
            macro_m0=pack.macro_m0,
            fx_regime=pack.fx_regime_auto,
        )
        calibrated_history = run(
            seed=1,
            months=24,
            country=pack.country,
            actors_enabled=True,
            regime_calendar=pack.regime_calendar,
            macro_coefficients=macro,
            macro_x0=pack.macro_x0,
            macro_m0=pack.macro_m0,
            fx_regime=pack.fx_regime_auto,
        )
        default_inflation = [r.state["inflation"] for r in default_history.records]
        calibrated_inflation = [r.state["inflation"] for r in calibrated_history.records]
        assert default_inflation != calibrated_inflation
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_load_calibrated_country_macro_is_none_for_calibration_without_macro(
    tmp_path: Path,
) -> None:
    """Compatibilidad con `a3_main` (ADR 011, sin macro): un
    `coefficients.json` sin clave `"macro"` devuelve `None`, no un
    `MacroCoefficients` vacio -- `cli.py`/`validation/argentina.py` usan
    ese `None` para decidir si usar el macro del paquete en cambio."""
    run_id = "pytest-synthetic-no-macro"
    run_dir = CALIBRATION_ROOT / run_id
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    try:
        from republica.world.bimonetary import BimonetaryCoefficients
        from republica.world.config import load_country

        base_coeff = load_country().coefficients.model_dump()
        base_bimon = BimonetaryCoefficients()
        bimon_dict = {name: getattr(base_bimon, name) for name in base_bimon.__dataclass_fields__}
        coefficients_json = {
            "run_id": run_id,
            "country_id": "argentina",
            "coefficients": base_coeff,
            "bimonetary": bimon_dict,
        }
        (run_dir / "coefficients.json").write_text(json.dumps(coefficients_json), encoding="utf-8")
        coeff, bimon, macro = load_calibrated_country("argentina", run_id)
        assert macro is None
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
