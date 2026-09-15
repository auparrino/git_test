"""Tests de ADR 012 secc. 7: macro con regimen (`features.macro_regime`).

Cubre, en orden de la tabla de la seccion 7 del ADR:
1. Flag off: Aurora golden byte a byte (referencia -- el test autoritativo
   vive en `tests/test_country_pack_argentina.py::
   test_aurora_without_country_matches_golden_hash_pre_a2`, que ya corre
   siempre; aca solo se confirma que la firma de `run()` con
   `macro_coefficients=None` es un no-op bit a bit).
2. Hiperinflacion alcanzable desde 1988-06 real (>= 50 % de 20 semillas,
   <= 18 meses, sin shocks forzados) y NO espuria desde 2003-06 real (0 %).
3. `peg` != `float` (trayectorias distintas) y salida forzada con reservas
   bajas -- mecanismo directo (unit) + replay historico 1998-01 (>= 50 % de
   20 semillas salen antes del mes 54).
4. Balance de pagos: commodities +20 % sube reservas; devaluacion real
   (rer mas alto) sube exportaciones.
5. Recuperacion: 2003-06 -> 2015-12 sin colapso en >= 80 % de 20 semillas.
6. Calibracion quick sobre sintetico: recupera >= 50 % de 10 coeficientes
   perturbados (CMA-ES, `cma` -- mismo paquete opcional que
   `tests/test_calibration_argentina.py`, se salta el test si no esta
   instalado).

Los coeficientes NUEVOS de ADR 012 que se retunearon respecto del valor
literal del ADR (`c_s`, y el split `k_flight`/`k_flight_peg`) estan
documentados en `docs/ADR_012_argentine_macro.md` seccion "Notas de
implementacion", con el barrido que los sostiene.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace

import pytest

from republica.engine.simulation import run
from republica.world.config import load_country
from republica.world.countries import load_country_pack
from republica.world.economy import (
    DEFAULT_X0_M0_USD_M,
    MacroCoefficients,
    init_macro_state,
    step_macro_economy,
)
from republica.world.events import ShockAggregate
from tests.test_country_pack_argentina import GOLDEN_SEED7_NO_COUNTRY_SHA256, _strip_config_hash

# ---------------------------------------------------------------------------
# 1. Flag off: no-op bit a bit (el golden completo de 91 aserciones vive en
#    test_country_pack_argentina.py, ya cubierto por la suite general).
# ---------------------------------------------------------------------------


def test_flag_off_is_bit_identical_to_omitting_macro_coefficients() -> None:
    country = load_country()
    with_none = run(
        seed=7, months=48, country=country, actors_enabled=True, macro_coefficients=None
    )
    without_arg = run(seed=7, months=48, country=country, actors_enabled=True)
    assert with_none.to_jsonl() == without_arg.to_jsonl()


def test_flag_off_golden_hash_still_matches_pre_adr_012() -> None:
    """El golden completo (91 aserciones: actores, congreso, cohortes,
    media, memoria, elecciones) con la firma EXACTA del test autoritativo
    de `test_country_pack_argentina.py` -- ADR 012 no le agrego ninguna
    rama al camino sin `macro_coefficients`, asi que esto es una llamada
    identica, repetida aca para que el suite de ADR 012 la traiga sin
    depender de otro archivo."""
    import hashlib

    country = load_country()
    history = run(
        seed=7,
        months=48,
        country=country,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
    )
    digest = hashlib.sha256(_strip_config_hash(history.to_jsonl()).encode("utf-8")).hexdigest()
    assert digest == GOLDEN_SEED7_NO_COUNTRY_SHA256


# ---------------------------------------------------------------------------
# 2. Hiperinflacion alcanzable (secc. 2) y no espuria.
# ---------------------------------------------------------------------------

HYPER_THRESHOLD = 20.0  # `country.json` terminal.hyper_inflation
HORIZON_MONTHS = 18
N_SEEDS = 20


def _crosses_hyperinflation(start: str, seed: int, months: int = HORIZON_MONTHS) -> bool:
    pack = load_country_pack("argentina", start, months)
    history = run(
        seed=seed,
        months=months,
        country=pack.country,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=False,
        regime_calendar=pack.regime_calendar,
        macro_coefficients=pack.macro_coefficients,
        macro_x0=pack.macro_x0,
        macro_m0=pack.macro_m0,
        fx_regime=pack.fx_regime_auto,
        # sin `forced_shocks`: "sin shocks forzados" (ADR 012 secc. 2, test).
    )
    return any(r.state["inflation"] > HYPER_THRESHOLD for r in history.records[:months])


def test_hyperinflation_reachable_from_1988_06_without_forced_shocks() -> None:
    crossed = sum(_crosses_hyperinflation("1988-06", seed) for seed in range(1, N_SEEDS + 1))
    assert crossed / N_SEEDS >= 0.5, (
        f"solo {crossed}/{N_SEEDS} semillas cruzan {HYPER_THRESHOLD}% mensual "
        f"en <= {HORIZON_MONTHS} meses desde 1988-06 (ADR 012 secc. 2: >= 50 %)"
    )


def test_hyperinflation_not_spurious_from_2003_06() -> None:
    crossed = sum(_crosses_hyperinflation("2003-06", seed) for seed in range(1, N_SEEDS + 1))
    assert crossed == 0, (
        f"{crossed}/{N_SEEDS} semillas cruzan {HYPER_THRESHOLD}% mensual desde 2003-06 "
        "(ADR 012 secc. 2: ninguna -- no deberia ser espuria)"
    )


# ---------------------------------------------------------------------------
# 3. `peg` != `float`, y salida forzada con reservas bajas.
# ---------------------------------------------------------------------------


def test_peg_and_float_trajectories_diverge() -> None:
    pack = load_country_pack("argentina", "1998-01", 24)
    peg = run(
        seed=3,
        months=24,
        country=pack.country,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=False,
        regime_calendar=pack.regime_calendar,
        macro_coefficients=pack.macro_coefficients,
        macro_x0=pack.macro_x0,
        macro_m0=pack.macro_m0,
        fx_regime="peg",
    )
    flt = run(
        seed=3,
        months=24,
        country=pack.country,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=False,
        regime_calendar=pack.regime_calendar,
        macro_coefficients=pack.macro_coefficients,
        macro_x0=pack.macro_x0,
        macro_m0=pack.macro_m0,
        fx_regime="float",
    )
    peg_ex_rate = [r.state["exchange_rate"] for r in peg.records]
    float_ex_rate = [r.state["exchange_rate"] for r in flt.records]
    peg_inflation = [r.state["inflation"] for r in peg.records]
    float_inflation = [r.state["inflation"] for r in flt.records]
    # Mismo seed/shocks, mismo mes de arranque: `peg` y `float` tienen que
    # producir trayectorias DISTINTAS (secc. 3: `de` se gobierna distinto
    # por regimen) tanto en el tipo de cambio como en la inflacion que
    # `de` alimenta (secc. 2, `c_e · de`).
    assert peg_ex_rate != float_ex_rate
    assert peg_inflation != float_inflation


def test_peg_forced_exit_mechanism_when_reserves_below_r_min() -> None:
    """Unit (secc. 3, directo sobre `step_macro_economy`): con reservas ya
    por debajo de `R_min` al empezar el mes, un `peg` salta a `float` ESE
    mes (`de = de_raw`, `fx_regime_exit` en `events`) y deja el
    `shock_conf` negativo en `pending` (ADR 012 secc. 3, columna "Salida"
    de la fila `peg`: literal)."""
    country = load_country()
    macro_coeff = MacroCoefficients()
    state = country.initial_state
    # Reservas muy por debajo de cualquier `R_min` razonable (`rm=3` meses
    # de importaciones con `m0` del orden de cientos/miles de USD M): fuerza
    # la rama "no alcanza para defender" sin depender de que el resto de la
    # dinamica erosione reservas primero.
    state = state.model_copy(update={"reserves": 1.0})
    macro = init_macro_state(
        macro_coeff,
        fx_regime="peg",
        initial_inflation=state.inflation,
        external_debt_usd_init=30000.0,
        x0=DEFAULT_X0_M0_USD_M,
        m0=DEFAULT_X0_M0_USD_M,
    )
    rng = random.Random(0)
    _, _, _, new_macro, events, pending = step_macro_economy(
        state,
        country.exogenous,
        country.exogenous,
        country.default_policy,
        ShockAggregate(),
        country.structure,
        country.coefficients,
        macro_coeff,
        macro,
        frozenset(),
        rng,
    )
    assert "fx_regime_exit" in events
    assert new_macro.fx_regime == "float"
    assert new_macro.exit_count == 1
    assert pending.get("shock_conf", 0.0) == pytest.approx(macro_coeff.exit_shock_conf)


def test_peg_exits_before_month_54_from_1998_01_in_most_seeds() -> None:
    """Replay historico (ADR 012 secc. 4, test): desde 1998-01 real con
    `peg`, reservas caen y el peg sale antes del mes 54 en >= 50 % de
    semillas. Usa `k_flight_peg` (ver Notas de implementacion del ADR 012:
    separado de `k_flight` de `float`/`control` porque un solo coeficiente
    para los cuatro regimenes fuerza a elegir entre este test y el test 5)."""
    months = 54
    pack = load_country_pack("argentina", "1998-01", months)
    exited = 0
    for seed in range(1, N_SEEDS + 1):
        history = run(
            seed=seed,
            months=months,
            country=pack.country,
            actors_enabled=True,
            congress_enabled=True,
            negotiation_enabled=True,
            cohorts_enabled=True,
            media_enabled=True,
            memory_enabled=True,
            elections_enabled=True,
            regime_calendar=pack.regime_calendar,
            macro_coefficients=pack.macro_coefficients,
            macro_x0=pack.macro_x0,
            macro_m0=pack.macro_m0,
            fx_regime="peg",
        )
        if any("fx_regime_exit" in r.events for r in history.records):
            exited += 1
    assert exited / N_SEEDS >= 0.5, (
        f"solo {exited}/{N_SEEDS} semillas salen del peg antes del mes {months} "
        "desde 1998-01 (ADR 012 secc. 4: >= 50 %)"
    )


# ---------------------------------------------------------------------------
# 4. Balance de pagos (secc. 4): commodities +20 % sube reservas;
#    devaluacion real (rer mas alto) sube exportaciones. Unit, directo sobre
#    `step_macro_economy`, todo lo demas igual salvo la variable en juego.
# ---------------------------------------------------------------------------


def _base_macro_scenario():
    country = load_country()
    macro_coeff = MacroCoefficients()
    state = country.initial_state
    macro = init_macro_state(
        macro_coeff,
        fx_regime="float",
        initial_inflation=state.inflation,
        external_debt_usd_init=30000.0,
        x0=DEFAULT_X0_M0_USD_M,
        m0=DEFAULT_X0_M0_USD_M,
    )
    return country, macro_coeff, state, macro


def test_commodity_price_plus_20_percent_raises_reserves() -> None:
    country, macro_coeff, state, macro = _base_macro_scenario()
    exo = country.exogenous

    def step(commodity_price: float):
        exo_new = exo.model_copy(update={"commodity_price": commodity_price})
        return step_macro_economy(
            state,
            exo,
            exo_new,
            country.default_policy,
            ShockAggregate(),
            country.structure,
            country.coefficients,
            macro_coeff,
            macro,
            frozenset(),
            random.Random(0),
        )

    baseline_state, _, _, _, _, _ = step(exo.commodity_price)
    shocked_state, _, _, _, _, _ = step(exo.commodity_price * 1.2)
    assert shocked_state.reserves > baseline_state.reserves


def test_real_devaluation_raises_exports() -> None:
    country, macro_coeff, state, macro = _base_macro_scenario()
    exo = country.exogenous

    def step(rer: float):
        m = replace(macro, rer=rer)
        _, _, macro_aux, _, _, _ = step_macro_economy(
            state,
            exo,
            exo,
            country.default_policy,
            ShockAggregate(),
            country.structure,
            country.coefficients,
            macro_coeff,
            m,
            frozenset(),
            random.Random(0),
        )
        return macro_aux.exports

    exports_baseline = step(100.0)
    exports_depreciated = step(130.0)  # rer mas alto = tipo de cambio real mas depreciado
    assert exports_depreciated > exports_baseline


# ---------------------------------------------------------------------------
# 5. Recuperacion de largo plazo (secc. 5): 2003-06 -> 2015-12 sin colapso
#    en >= 80 % de semillas.
# ---------------------------------------------------------------------------


def test_recovery_from_2003_06_to_2015_12() -> None:
    months = (2015 - 2003) * 12 + (12 - 6)  # 150
    pack = load_country_pack("argentina", "2003-06", months)
    survived = 0
    for seed in range(1, N_SEEDS + 1):
        history = run(
            seed=seed,
            months=months,
            country=pack.country,
            actors_enabled=True,
            congress_enabled=True,
            negotiation_enabled=True,
            cohorts_enabled=True,
            media_enabled=True,
            memory_enabled=True,
            elections_enabled=True,
            regime_calendar=pack.regime_calendar,
            macro_coefficients=pack.macro_coefficients,
            macro_x0=pack.macro_x0,
            macro_m0=pack.macro_m0,
            fx_regime=pack.fx_regime_auto,
        )
        if history.outcome == "survived":
            survived += 1
    assert survived / N_SEEDS >= 0.8, (
        f"solo {survived}/{N_SEEDS} semillas llegan de 2003-06 a 2015-12 sin colapso "
        "(ADR 012 secc. 5: >= 80 %)"
    )


# ---------------------------------------------------------------------------
# 6. Calibracion quick sobre sintetico (secc. 6): recupera >= 50 % de 10
#    coeficientes perturbados. CMA-ES directo sobre `MacroCoefficients`
#    (independiente del pipeline de `calibration/` -- ese esta hecho para
#    `Coefficients`/`BimonetaryCoefficients`, no para `MacroCoefficients`),
#    sobre un escenario sintetico deterministico (sin shocks/ruido: mismo
#    criterio de reproducibilidad que
#    `test_identifiability_recovers_half_of_perturbed_coefficients` en
#    `tests/test_calibration_argentina.py`, que tambien corre `pool=None`
#    por la misma razon).
# ---------------------------------------------------------------------------

PARAM_NAMES = [
    "w_adapt",
    "rho_pi",
    "rho_slope",
    "c_e",
    "c_g",
    "c_r",
    "md_0",
    "md_pi",
    "x_d",
    "im_y",
]
SYNTH_MONTHS = 30


def _simulate_macro_path(macro_coeff: MacroCoefficients) -> tuple[list[float], list[float]]:
    country = load_country()
    state = country.initial_state
    macro = init_macro_state(
        macro_coeff,
        fx_regime="float",
        initial_inflation=state.inflation,
        external_debt_usd_init=30000.0,
        x0=DEFAULT_X0_M0_USD_M,
        m0=DEFAULT_X0_M0_USD_M,
    )
    rng = random.Random(0)
    inflation_path: list[float] = []
    reserves_path: list[float] = []
    for _ in range(SYNTH_MONTHS):
        state, _, _, macro, _, _ = step_macro_economy(
            state,
            country.exogenous,
            country.exogenous,
            country.default_policy,
            ShockAggregate(),
            country.structure,
            country.coefficients,
            macro_coeff,
            macro,
            frozenset(),
            rng,
        )
        inflation_path.append(state.inflation)
        reserves_path.append(state.reserves)
    return inflation_path, reserves_path


def _perturb_macro_params(seed: int, fraction: float = 0.4) -> dict[str, float]:
    rng = random.Random(seed)
    defaults = MacroCoefficients()
    perturbed = {}
    for name in PARAM_NAMES:
        base = getattr(defaults, name)
        sign = rng.choice([-1.0, 1.0])
        perturbed[name] = base * (1.0 + sign * fraction)
    return perturbed


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_quick_synthetic_identifiability_recovers_half_of_perturbed_coefficients() -> None:
    # CMA-ES explora combinaciones de coeficientes lejos de cualquier
    # calibracion razonable (esperado: es lo que hace identificable a los
    # que SI se recuperan) -- algunas producen desbordes de punto flotante
    # transitorios en `step_economy`/`step_macro_economy` que `loss()` ya
    # atrapa y castiga con 1e6; silenciados aca para no ensuciar la salida
    # del test (no son un fallo, `loss()` los maneja).
    cma = pytest.importorskip(
        "cma", reason="dependencia opcional de calibracion (grupo 'calibration')"
    )

    defaults = MacroCoefficients()
    true_values = _perturb_macro_params(seed=3, fraction=0.4)
    true_coeff = replace(defaults, **true_values)
    obs_inflation, obs_reserves = _simulate_macro_path(true_coeff)
    scale_inflation = max(1.0, max(obs_inflation) - min(obs_inflation))
    scale_reserves = max(1.0, max(obs_reserves) - min(obs_reserves))

    def loss(vector: list[float]) -> float:
        kwargs = dict(zip(PARAM_NAMES, vector, strict=False))
        mc = replace(defaults, **kwargs)
        try:
            inflation, reserves = _simulate_macro_path(mc)
        except (OverflowError, ValueError):
            return 1e6
        total = 0.0
        for a, b in zip(inflation, obs_inflation, strict=False):
            total += ((a - b) / scale_inflation) ** 2
        for a, b in zip(reserves, obs_reserves, strict=False):
            total += ((a - b) / scale_reserves) ** 2
        result = total / len(inflation)
        return result if math.isfinite(result) else 1e6

    x0 = [getattr(defaults, name) for name in PARAM_NAMES]
    stds = [abs(getattr(defaults, name)) * 0.5 + 0.01 for name in PARAM_NAMES]
    es = cma.CMAEvolutionStrategy(
        x0, 1.0, {"CMA_stds": stds, "seed": 5, "verbose": -9, "maxfevals": 500}
    )
    es.optimize(loss)
    best = es.result.xbest

    moved_toward_truth = 0
    for name, calibrated_v in zip(PARAM_NAMES, best, strict=False):
        aurora_v = getattr(defaults, name)
        true_v = true_values[name]
        if true_v == aurora_v:
            continue
        frac_recovered = (calibrated_v - aurora_v) / (true_v - aurora_v)
        if frac_recovered >= 0.2:
            moved_toward_truth += 1
    assert moved_toward_truth >= len(PARAM_NAMES) // 2, (
        f"solo {moved_toward_truth}/{len(PARAM_NAMES)} coeficientes se movieron "
        ">= 20% del perturbado hacia la verdad (ADR 012 secc. 6: >= 50 %)"
    )
