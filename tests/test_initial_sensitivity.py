"""Tests de ADR 019 (`docs/ADR_019_initial_state_sensitivity.md`):
sensibilidad no monotona al estado inicial y la indexacion como ESTADO.

En orden de la seccion 6 del ADR:

1. Flag off (`indexation_state = False`): `step_macro_economy` devuelve
   exactamente la `rho_eff` de ADR 012 y una corrida completa es bit a bit
   la de antes de ADR 019 (los goldens de Aurora viven en
   `test_country_pack_argentina.py`/`test_macro_regime.py` y siguen
   corriendo igual).
2. El filo: `pi* = pi_hi·(1 + (1 - rho_pi)/rho_slope)` es el punto donde el
   mapa de precios pasa de convergente a explosivo, y esta a 0.28 pp del
   dato inicial de 1983-12 de antes de ADR 019.
3. Inercia: con el flag prendido, UN mes por encima del umbral ya no
   cambia el regimen del mapa.
4. La semilla desde la historia real ordena 1988-06 por encima de 1983-12
   (ADR 019 secc. 3B), y la ordena SOLO por la aceleracion.
5. El dato inicial de las dos fechas es el mensual real (ADR 019 secc. 3C).
6. C1/C2 del ADR secc. 4, y C3 (la sensibilidad a `pi0` alrededor del
   umbral baja con el flag prendido).
7. Los campos estructurales sobreviven al cambio de vector por regimen
   cambiario de ADR 017 secc. 3.6.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import replace

import pytest

from republica.engine.policy import PassivePolicy
from republica.engine.simulation import run
from republica.world.config import load_country
from republica.world.countries import (
    country_pack_dir,
    indexation_seed_history,
    load_country_pack,
)
from republica.world.economy import (
    DEFAULT_X0_M0_USD_M,
    INDEXATION_FIELDS,
    LEGITIMACY_FIELDS,
    MacroCoefficients,
    init_macro_state,
    merge_structural_coefficients,
    seed_indexation,
    step_macro_economy,
)
from republica.world.events import ShockAggregate
from republica.world.state import clamp

HYPER_THRESHOLD = 20.0  # `country.json -> terminal.hyper_inflation`
HYPER_MONTHS = 3  # `country.json -> terminal.hyper_months`

#: Vector `peg`/`crawl` de la calibracion `a7_by_regime`, que es el que sale
#: para cualquier arranque entre 1983-12 y 1991-03 (`fx_regimes.csv` dice
#: `crawl` y `regime_group_map` manda `crawl` al grupo `peg`). Son los tres
#: numeros que fijan el umbral del filo -- ADR 019 secc. 1.3.
A7_PEG_RHO_PI = 0.5814706427397387
A7_PEG_RHO_SLOPE = 0.23506295621505566
A7_PEG_PI_HI = 6.285679661213015


def _threshold(coeff: MacroCoefficients) -> float:
    """`pi*`: el `inflation_lag1` con el que `rho_eff` vale exactamente 1
    (ADR 019 secc. 1.3)."""
    return coeff.pi_hi * (1.0 + (1.0 - coeff.rho_pi) / coeff.rho_slope)


def _one_month(state, coeff: MacroCoefficients, macro=None, fx_regime: str = "float"):
    """Un mes aislado de `step_macro_economy`, sin shocks ni politica
    activa: devuelve `(new_state, macro_aux, new_macro)`."""
    country = load_country()
    if macro is None:
        macro = init_macro_state(
            coeff,
            fx_regime=fx_regime,
            initial_inflation=state.inflation,
            external_debt_usd_init=30000.0,
            x0=DEFAULT_X0_M0_USD_M,
            m0=DEFAULT_X0_M0_USD_M,
        )
    new_state, _aux, macro_aux, new_macro, _events, _pending = step_macro_economy(
        state,
        country.exogenous,
        country.exogenous,
        country.default_policy,
        ShockAggregate(),
        country.structure,
        country.coefficients,
        coeff,
        macro,
        frozenset(),
        random.Random(0),
    )
    return new_state, macro_aux, new_macro


def _a7_peg_coefficients(**overrides) -> MacroCoefficients:
    base = MacroCoefficients(rho_pi=A7_PEG_RHO_PI, rho_slope=A7_PEG_RHO_SLOPE, pi_hi=A7_PEG_PI_HI)
    return replace(base, **overrides) if overrides else base


#: Calibracion con la que se miden C1/C2/C3 (la misma de la sonda de
#: `docs/EMERGENCE_LOG.md` y de la validacion `a8_a7`). Los umbrales del
#: filo que documenta ADR 019 secc. 1.3 son los de ESTE vector: con los
#: coeficientes del paquete (sin calibrar) el umbral esta en 12.50 %/mes y
#: los dos arranques quedan del mismo lado, que es justamente por que el
#: test 2a de ADR 012 pasa 20/20 y la V1 de `a8_a7` da 0/50.
CALIBRATION_RUN_ID = "a7_by_regime"


def _calibrated_run_kwargs(start: str, months: int, indexation_state: bool = True) -> dict:
    """Exactamente lo que arma `republica run --country argentina --start
    <start> --calibration a7_by_regime --regime-transitions` antes de
    llamar a `run()`. Se replica entero (features del paquete, epoca de
    partidos, bimonetario, vectores por grupo) porque el resultado de C1/C2
    depende de todo eso -- en particular de `dollar_demand_init`, que
    alimenta `de_raw` via `x_d`."""
    from dataclasses import replace as dc_replace

    from republica.calibration.run import (
        load_calibrated_country,
        load_calibrated_vectors_by_group,
    )

    pack = load_country_pack("argentina", start, months, regime_transitions=True)
    coeff, bimonetary, calibrated_macro = load_calibrated_country(
        "argentina", CALIBRATION_RUN_ID, start=start
    )
    country = pack.country.model_copy(update={"coefficients": coeff})
    bimonetary = dc_replace(bimonetary, fx_regime_default=pack.fx_regime_auto)
    macro = merge_structural_coefficients(calibrated_macro, pack.macro_coefficients)
    macro = dc_replace(macro, indexation_state=indexation_state)
    era_actors = era_loyalty = None
    era_gov: dict[str, str] = {}
    if pack.era is not None and pack.era.parties is not None:
        era_actors = pack.era.actors
        era_loyalty = pack.era.loyalty_table
        if pack.era.governance_path is not None and pack.era.governance_path.exists():
            from republica.world.eras import era_governance_overrides

            era_gov = era_governance_overrides(pack.era.governance_path)
    f = country.features
    policy_rule = PassivePolicy(
        country.default_policy,
        country.structure.r_neutral,
        country.policy_ranges["interest_rate_target"],
    )
    return {
        "months": months,
        "policy_rule": policy_rule,
        "country": country,
        "actors_enabled": f.get("actors", True),
        "actors": era_actors,
        "congress_enabled": f.get("congress", True),
        "negotiation_enabled": f.get("negotiation", True),
        "cohorts_enabled": f.get("cohorts", True),
        "media_enabled": f.get("media", True),
        "memory_enabled": f.get("memory", True),
        "elections_enabled": f.get("elections", True),
        "loyalty_table": era_loyalty,
        "governance_overrides": era_gov or None,
        "regime_calendar": pack.regime_calendar,
        "bimonetary_coefficients": bimonetary,
        "macro_coefficients": macro,
        "macro_x0": pack.macro_x0,
        "macro_m0": pack.macro_m0,
        "fx_regime": pack.fx_regime_auto,
        "coefficients_by_fx_regime": load_calibrated_vectors_by_group(CALIBRATION_RUN_ID),
    }


# ---------------------------------------------------------------------------
# 1. Flag off: ADR 019 es un no-op.
# ---------------------------------------------------------------------------


def test_flag_off_rho_eff_is_exactly_the_adr_012_ramp() -> None:
    coeff = _a7_peg_coefficients()
    assert coeff.indexation_state is False
    country = load_country()
    for pi in (3.0, 8.0, 17.0, 25.0, 40.0):
        state = country.initial_state.model_copy(update={"inflation": pi, "inflation_lag1": pi})
        _, macro_aux, new_macro = _one_month(state, coeff)
        esperado = coeff.rho_pi + coeff.rho_slope * clamp(
            (pi - coeff.pi_hi) / coeff.pi_hi, 0.0, 2.0
        )
        assert macro_aux.rho_eff == pytest.approx(esperado)
        # Sin el flag, el estado nuevo no arrastra ningun stock de ADR 019.
        assert new_macro.indexation is None
        assert macro_aux.indexation is None


def test_flag_off_full_run_is_bit_identical_to_the_same_run_without_adr_019_fields() -> None:
    """Una corrida con `indexation_state=False` es identica a la misma con
    los otros campos de ADR 019 en cualquier valor: con el flag apagado no
    los lee nadie."""
    pack = load_country_pack("argentina", "1988-06", 24)
    apagado = replace(pack.macro_coefficients, indexation_state=False)
    otro = replace(apagado, idx_adj=0.5, idx_accel_k=7.0, idx_seed_months=3)
    corridas = []
    for coeff in (apagado, otro):
        corridas.append(
            run(
                seed=3,
                months=24,
                country=pack.country,
                actors_enabled=True,
                regime_calendar=pack.regime_calendar,
                macro_coefficients=coeff,
                macro_x0=pack.macro_x0,
                macro_m0=pack.macro_m0,
                fx_regime=pack.fx_regime_auto,
            ).to_jsonl()
        )
    assert corridas[0] == corridas[1]


def test_adr_019_fields_are_not_calibrable() -> None:
    """Los campos de ADR 019 son ESTRUCTURALES: no entran en el vector de
    CMA-ES, y `MACRO_TUNABLE` sigue en 58 campos (mismo contrato que los
    `lf_*` de ADR 016)."""
    from republica.calibration.parameters import MACRO_TUNABLE

    assert len(MACRO_TUNABLE) == 58
    assert not set(INDEXATION_FIELDS) & set(MACRO_TUNABLE)


# ---------------------------------------------------------------------------
# 2. El filo de ADR 012: `rho_eff` cruza 1 en un punto.
# ---------------------------------------------------------------------------


def test_rho_eff_crosses_one_at_the_analytic_threshold() -> None:
    """ADR 019 secc. 1.3: con el vector `peg`/`crawl` de `a7_by_regime` el
    umbral esta en 17.4773 %/mes, y el dato inicial de 1983-12 de ANTES de
    ADR 019 (17.7604) lo cruzaba por 0.28 pp -- mientras que el de 1988-06
    (13.9893) quedaba 3.49 pp abajo. Mismo mecanismo, veredicto opuesto."""
    coeff = _a7_peg_coefficients()
    pi_star = _threshold(coeff)
    assert pi_star == pytest.approx(17.4773, abs=1e-3)

    country = load_country()
    for pi, esperado_mayor in ((pi_star - 0.5, False), (pi_star + 0.5, True)):
        state = country.initial_state.model_copy(update={"inflation": pi, "inflation_lag1": pi})
        _, macro_aux, _ = _one_month(state, coeff)
        assert (macro_aux.rho_eff > 1.0) is esperado_mayor

    viejo_1983_12 = 17.76035988773017
    viejo_1988_06 = 13.989265074886625
    assert viejo_1983_12 > pi_star
    assert viejo_1988_06 < pi_star
    assert viejo_1983_12 - pi_star == pytest.approx(0.283, abs=0.01)


def test_the_measured_transition_band_sits_below_the_analytic_threshold() -> None:
    """El umbral analitico (`rho_eff = 1`, 17.48 %/mes) es exacto pero NO
    es donde el modelo COMPLETO cambia de comportamiento: `c_e·de` y el
    canal de tasa suman persistencia, asi que la banda de transicion medida
    esta por debajo. Con ADR 012 puro y 24 meses: 12 %/mes no cruza en
    ninguna semilla, 17.7 %/mes cruza en todas. Ese es el escalon que ADR
    019 viene a aplanar."""
    kwargs = _calibrated_run_kwargs("1983-12", 24, indexation_state=False)
    base = kwargs["country"]
    cruces = {}
    for pi0 in (12.0, 17.7):
        estado = base.initial_state.model_copy(update={"inflation": pi0, "inflation_lag1": pi0})
        kw = dict(kwargs)
        kw["country"] = base.model_copy(update={"initial_state": estado})
        cruces[pi0] = sum(_hyper_month(run(seed=seed, **kw)) is not None for seed in range(1, 7))
    assert cruces[12.0] == 0
    assert cruces[17.7] == 6


# ---------------------------------------------------------------------------
# 3. Inercia: un mes no cambia el regimen del mapa.
# ---------------------------------------------------------------------------


def test_one_month_above_the_threshold_no_longer_flips_the_map() -> None:
    """ADR 019 secc. 3A: con el flag prendido, `rho_eff` se mueve como
    mucho `idx_adj·rho_slope·2` por mes (0.056 con los defaults), asi que
    un solo mes por encima del umbral no puede llevarla de 0.58 a > 1."""
    coeff = _a7_peg_coefficients(indexation_state=True)
    country = load_country()
    # Estado con una inflacion MUY por encima del umbral, pero con el stock
    # todavia sin sembrar (peor caso para la inercia: el primer mes cae al
    # valor sin memoria, asi que se mide a partir del segundo).
    state = country.initial_state.model_copy(update={"inflation": 3.0, "inflation_lag1": 3.0})
    _, _, macro = _one_month(state, coeff)
    assert macro.indexation is not None
    arranque = macro.indexation

    estallido = country.initial_state.model_copy(update={"inflation": 60.0, "inflation_lag1": 3.0})
    _, macro_aux, macro2 = _one_month(estallido, coeff, macro=macro)
    assert macro2.indexation - arranque <= coeff.idx_adj * 2.0 + 1e-9
    assert macro_aux.rho_eff < 1.0


def test_indexation_converges_to_its_target_with_the_documented_half_life() -> None:
    """`idx_adj = 0.12` -> media vida 5.4 meses (ADR 019 secc. 3A)."""
    coeff = MacroCoefficients(indexation_state=True)
    media_vida = math.log(2.0) / (-math.log(1.0 - coeff.idx_adj))
    assert media_vida == pytest.approx(5.42, abs=0.05)


# ---------------------------------------------------------------------------
# 4. La semilla desde la historia real (ADR 019 secc. 3B).
# ---------------------------------------------------------------------------


def _seed_for(start: str, coeff: MacroCoefficients) -> float:
    pack_dir = country_pack_dir("argentina")
    history = indexation_seed_history(pack_dir, start, coeff)
    seeded = seed_indexation(history, coeff)
    assert seeded is not None, start
    return seeded


def _idx_target(pi: float, lag: float, coeff: MacroCoefficients) -> float:
    hat = pi + (coeff.idx_accel_k - 1.0) * (pi - lag)
    return clamp((hat - coeff.pi_hi) / coeff.pi_hi, 0.0, 2.0)


def test_no_backward_looking_statistic_orders_1988_06_above_1983_12() -> None:
    """ADR 019 secc. 2, medido: TODO observable de NIVEL dice que 1983-12
    es el arranque mas inflacionario. La semilla de ADR 019 secc. 3B, que
    es un promedio ponderado de 24 meses de nivel, tampoco los ordena al
    reves -- y no se la fuerza a hacerlo."""
    coeff = _a7_peg_coefficients(indexation_state=True)
    assert _seed_for("1983-12", coeff) > _seed_for("1988-06", coeff)


def test_the_acceleration_is_the_only_observable_that_orders_them() -> None:
    """Lo que SI los ordena al reves es el objetivo forward-looking
    (`idx_target`, ADR 019 secc. 3A): con `idx_accel_k = 2` (extrapolacion
    lineal a un mes) 1988-06 sale en la cota (2.0) y 1983-12 en 1.577. Con
    `idx_accel_k = 0` -- el mecanismo SIN MEMORIA de ADR 012, que mira el
    rezago -- el orden es el contrario. El coeficiente no esta elegido para
    que de: es el signo de la aceleracion (19.2 -> 17.7 desacelerando contra
    15.7 -> 18.0 acelerando)."""
    pi_1983, lag_1983 = 17.7, 19.2
    pi_1988, lag_1988 = 18.0, 15.7

    sin_accel = _a7_peg_coefficients(indexation_state=True, idx_accel_k=0.0)
    assert _idx_target(pi_1983, lag_1983, sin_accel) > _idx_target(pi_1988, lag_1988, sin_accel)

    con_accel = _a7_peg_coefficients(indexation_state=True, idx_accel_k=2.0)
    t_1983 = _idx_target(pi_1983, lag_1983, con_accel)
    t_1988 = _idx_target(pi_1988, lag_1988, con_accel)
    assert t_1988 > t_1983
    assert t_1983 == pytest.approx(1.577, abs=0.01)
    assert t_1988 == pytest.approx(2.0, abs=0.01)


def test_idx_accel_k_two_is_exactly_a_one_month_linear_extrapolation() -> None:
    """`idx_accel_k = 2` no es un numero ajustado: `idx_hat = inflation +
    1·(inflation - inflation_lag1)` es la extrapolacion lineal a un mes.
    Con 1 mira el mes corriente y con 0 el rezago (ADR 012)."""
    coeff = MacroCoefficients(indexation_state=True)
    assert coeff.idx_accel_k == 2.0
    pi, lag = 18.0, 15.7
    for k, esperado in ((0.0, lag), (1.0, pi), (2.0, pi + (pi - lag))):
        c = replace(coeff, idx_accel_k=k)
        hat = pi + (c.idx_accel_k - 1.0) * (pi - lag)
        assert hat == pytest.approx(esperado)


def test_seed_is_none_without_enough_real_history() -> None:
    coeff = MacroCoefficients(indexation_state=True, idx_seed_months=24)
    assert seed_indexation((), coeff) is None
    assert seed_indexation((10.0, 11.0, 12.0), coeff) is None
    assert seed_indexation(tuple([10.0] * 24), coeff) is not None


def test_seed_history_is_the_real_series_of_the_previous_months() -> None:
    coeff = MacroCoefficients(indexation_state=True, idx_seed_months=3)
    history = indexation_seed_history(country_pack_dir("argentina"), "1983-12", coeff)
    assert history == (21.4, 17.0, 19.2)  # 1983-09/10/11, reales
    history_1988 = indexation_seed_history(country_pack_dir("argentina"), "1988-06", coeff)
    assert history_1988[-1] == pytest.approx(15.7)


# ---------------------------------------------------------------------------
# 5. El dato inicial es el mensual REAL (ADR 019 secc. 3C).
# ---------------------------------------------------------------------------


def test_initial_inflation_of_the_two_dates_is_the_real_monthly_datum() -> None:
    """`history/inflation_cpi_monthly_linked.csv` (BCRA/INDEC, 1943-03+)
    estaba en el repo y no lo leia nadie: todo arranque anterior a 1997-02
    recibia una tasa ANUAL convertida. El error para 1988-06 era de 4.01
    pp."""
    from republica.calibration.initial_states import initial_state_for

    esperado = {
        "1983-12": (17.7, 19.2),
        "1988-06": (18.0, 15.7),
    }
    raw = json.loads((country_pack_dir("argentina") / "country.json").read_text(encoding="utf-8"))
    for date, (pi, lag) in esperado.items():
        hito = raw["initial_states"][date]
        assert hito["inflation"]["value"] == pytest.approx(pi)
        assert hito["inflation_lag1"]["value"] == pytest.approx(lag)
        assert "source" in hito["inflation"]
        assert "monthly_linked" in hito["inflation"]["source"]
        # El otro constructor del proyecto tiene que decir lo mismo: antes
        # de ADR 019 diferian en 11.95 pp para 1988-06 (ADR 019 secc. 1.2).
        construido = initial_state_for(date)
        assert construido["inflation"]["value"] == pytest.approx(pi)
        assert construido["inflation_lag1"]["value"] == pytest.approx(lag)


# ---------------------------------------------------------------------------
# 6. C1 / C2 / C3 de ADR 019 secc. 4.
# ---------------------------------------------------------------------------


def _hyper_month(history) -> int | None:
    streak = 0
    for rec in history.records:
        if rec.state["inflation"] > HYPER_THRESHOLD:
            streak += 1
            if streak >= HYPER_MONTHS:
                return rec.month_index
        else:
            streak = 0
    return None


def _run_from(start: str, months: int, seeds: int, indexation_state: bool = True):
    kwargs = _calibrated_run_kwargs(start, months, indexation_state=indexation_state)
    return [run(seed=seed, **kwargs) for seed in range(1, seeds + 1)]


#: Mes en que la serie mensual REAL cumple el criterio terminal del propio
#: modelo (`> 20 %/mes` durante 3 meses seguidos), contado desde cada fecha.
#: NO es el mes de la hiperinflacion de junio de 1989: es el criterio que el
#: modelo usa para terminar una corrida, evaluado sobre el dato
#: (`inflation_cpi_monthly_linked.csv`). Desde 1983-12 la Argentina real lo
#: cumple en 1985-01/02/03 (25.1, 20.7, 26.5) = mes 15; desde 1988-06 en
#: 1989-04/05/06 (33.4, 78.5, 114.5) = mes 12. Ver ADR 019 secc. 7.
REAL_CRITERION_MONTH = {"1983-12": 15, "1988-06": 12}


def test_c1_hyperinflation_from_1983_12_is_no_longer_a_seven_month_affair() -> None:
    """C1 de ADR 019 secc. 4, reformulado en secc. 7: el enunciado original
    pedia "despues del mes 48" tomando como referencia junio de 1989 (mes
    66), pero eso es el EPISODIO de hiperinflacion, no el criterio terminal
    del modelo. Sobre la serie real, el criterio del modelo (3 meses
    seguidos > 20 %/mes) se cumple en el mes 15 desde 1983-12. La linea de
    base era mes 6-7."""
    historias = _run_from("1983-12", 36, 10)
    meses = [m for m in (_hyper_month(h) for h in historias) if m is not None]
    assert len(meses) >= 5, "la hiperinflacion tiene que seguir siendo alcanzable desde 1983-12"
    mediana = statistics.median(meses)
    assert mediana >= 12, f"mediana {mediana}: sigue explotando tan rapido como antes de ADR 019"
    assert mediana <= 2 * REAL_CRITERION_MONTH["1983-12"], (
        f"mediana {mediana}: ahora tarda mas del doble que el dato real "
        f"({REAL_CRITERION_MONTH['1983-12']})"
    )


def test_c2_hyperinflation_still_reachable_from_1988_06() -> None:
    """C2 de ADR 019 secc. 4 = V1 de ADR 011 secc. 8 / test 2a de ADR 012
    secc. 7: >= 50 % de las semillas cruzan 20 %/mes en 24 meses desde
    1988-06. Con `a7_by_regime` la linea de base era 0/50."""
    historias = _run_from("1988-06", 24, 20)
    cruzan = sum(any(r.state["inflation"] > HYPER_THRESHOLD for r in h.records) for h in historias)
    assert cruzan / len(historias) >= 0.5, (
        f"solo {cruzan}/{len(historias)} semillas cruzan {HYPER_THRESHOLD} %/mes desde 1988-06"
    )


def test_c2_is_not_spurious_from_2003_06() -> None:
    """El control de ADR 012 secc. 7 test 2b sigue valiendo con ADR 019
    prendido: desde 2003-06 ninguna semilla cruza."""
    historias = _run_from("2003-06", 24, 10)
    cruzan = sum(any(r.state["inflation"] > HYPER_THRESHOLD for r in h.records) for h in historias)
    assert cruzan == 0, f"{cruzan} semillas hiperinflacionan desde 2003-06"


def test_c3_sensitivity_to_the_initial_inflation_drops_with_the_flag_on() -> None:
    """C3: la enfermedad medida. Se mueve SOLO `inflation`/`inflation_lag1`
    del estado de 1983-12 en una banda de 2 pp alrededor del umbral
    (17.0-19.0 %/mes) y se mira cuanto se mueve el mes mediano de
    hiperinflacion. Con ADR 012 puro el rango es de varios meses (el filo);
    con ADR 019 la respuesta es casi plana."""
    banda = [17.0, 17.5, 18.0, 18.5, 19.0]
    rangos = {}
    for flag in (False, True):
        kwargs = _calibrated_run_kwargs("1983-12", 24, indexation_state=flag)
        base = kwargs["country"]
        medianas = []
        for pi0 in banda:
            estado = base.initial_state.model_copy(update={"inflation": pi0, "inflation_lag1": pi0})
            kw = dict(kwargs)
            kw["country"] = base.model_copy(update={"initial_state": estado})
            meses = []
            for seed in range(1, 7):
                m = _hyper_month(run(seed=seed, **kw))
                meses.append(25 if m is None else m)
            medianas.append(statistics.median(meses))
        rangos[flag] = max(medianas) - min(medianas)
    assert rangos[True] < rangos[False], (
        f"ADR 019 no aplano la respuesta: rango con flag {rangos[True]} contra "
        f"{rangos[False]} sin flag"
    )


# ---------------------------------------------------------------------------
# 7. Los campos estructurales sobreviven al cambio de vector de ADR 017.
# ---------------------------------------------------------------------------


def test_structural_fields_survive_the_fx_regime_vector_swap() -> None:
    """Bug encontrado en el camino (ADR 019 secc. 7): `engine/simulation.py
    ::_swap_fx_regime_vector` reemplaza `sim.macro_coefficients` por el
    vector del grupo nuevo, y ese vector sale de un `coefficients.json` que
    NO trae los campos estructurales -- ni los `lf_*` de ADR 016 ni los
    `idx_*` de ADR 019. Como `active_fx_regime_group` arranca en `None`, el
    primer swap ocurre en el MES 1: sin el merge, ADR 019 quedaba apagado
    en cualquier corrida con `--calibration --by-regime`."""
    pack = load_country_pack("argentina", "1983-12", 6)
    coeff = replace(pack.macro_coefficients, indexation_state=True)
    # Un vector "calibrado" por grupo que, como los reales, no trae ninguno
    # de los campos estructurales.
    por_grupo = {
        grupo: (pack.country.coefficients, MacroCoefficients())
        for grupo in ("peg", "float", "control")
    }
    history = run(
        seed=1,
        months=6,
        country=pack.country,
        actors_enabled=True,
        regime_calendar=pack.regime_calendar,
        macro_coefficients=coeff,
        macro_x0=pack.macro_x0,
        macro_m0=pack.macro_m0,
        fx_regime=pack.fx_regime_auto,
        coefficients_by_fx_regime=por_grupo,
    )
    assert history.records[0].macro["indexation"] is not None


def test_merge_structural_coefficients_carries_both_adrs() -> None:
    calibrado = MacroCoefficients()
    paquete = MacroCoefficients(
        lf_base=33.0,
        indexation_state=True,
        idx_adj=0.2,
        idx_accel_k=3.0,
        idx_seed_months=18,
        idx_seed_history=(1.0, 2.0, 3.0),
    )
    merged = merge_structural_coefficients(calibrado, paquete)
    for name in LEGITIMACY_FIELDS + INDEXATION_FIELDS:
        assert getattr(merged, name) == getattr(paquete, name), name
