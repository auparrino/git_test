"""Tests de ADR 018 secc. 5: recuperacion del bloque politico
(`features.political_recovery`).

Cubre, en orden:
1. Flag off: no-op bit a bit, y default del flag por paquete de pais.
2. Forma de los cuatro terminos (unit, sobre `world/recovery.py`): ninguno
   cruza su valor de referencia, y con el contexto no enganchado son la
   identidad.
3. La compuerta (unit): los cuatro marcadores de ruptura aguda la cierran;
   desinflacion y reactivacion la abren por separado; un mes sin alivio
   reinicia la racha; se engancha recien en `relief_months`.
4. El efecto medido sobre los arranques reales, congelado como regresion --
   INCLUIDA la prediccion NEGATIVA H6 (1991-04 no mejora), que se registro
   en el ADR antes de medir.
5. Los tres discriminantes de ADR 018 secc. 3.3: hiperinflacion alcanzable
   desde 1988-06, colapso/default desde 1998-01 con `peg`, y que los
   coeficientes de ADR 018 NO entren en el vector calibrable.

La configuracion de las corridas reales es la de ADR 018 secc. 1.1
(calibracion `a7_by_regime`, cambio de vector en caliente, todas las
features del paquete). Los discriminantes usan los coeficientes SIN calibrar
del paquete, igual que `tests/test_macro_regime.py`.
"""

from __future__ import annotations

import statistics
from dataclasses import replace

import pytest

from republica.calibration.run import load_calibrated_country, load_calibrated_vectors_by_group
from republica.engine.simulation import run
from republica.world.config import load_country
from republica.world.countries import load_country_pack
from republica.world.economy import MacroCoefficients, merge_structural_coefficients
from republica.world.recovery import (
    PoliticalRecoveryCoefficients,
    RecoveryContext,
    RecoveryTracker,
    advance_recovery,
    recover_approval,
    recover_confidence,
    recover_crime,
    recover_protest,
    recover_social,
    recover_tension,
    relief_this_month,
    track_rupture,
)

CALIBRATION = "a7_by_regime"
EPS = 1e-6


def _corrida(
    start: str,
    months: int,
    seed: int,
    *,
    political_recovery: bool | None = None,
    recovery_coeff: PoliticalRecoveryCoefficients | None = None,
    calibration: str | None = CALIBRATION,
    fx_regime: str | None = None,
    elections: bool = True,
):
    """Una corrida con la configuracion de ADR 018 secc. 1.1."""
    pack = load_country_pack("argentina", start, months)
    country = pack.country
    macro = pack.macro_coefficients
    kw: dict = {}
    if calibration is not None:
        coeff, _bimon, cal_macro = load_calibrated_country("argentina", calibration, start=start)
        country = country.model_copy(update={"coefficients": coeff})
        if cal_macro is not None:
            macro = merge_structural_coefficients(cal_macro, pack.macro_coefficients)
        kw["coefficients_by_fx_regime"] = load_calibrated_vectors_by_group(calibration)
    if political_recovery is not None:
        kw["political_recovery"] = political_recovery
    if recovery_coeff is not None:
        kw["political_recovery_coefficients"] = recovery_coeff
    return run(
        seed=seed,
        months=months,
        country=country,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=elections,
        regime_calendar=pack.regime_calendar,
        macro_coefficients=macro,
        macro_x0=pack.macro_x0,
        macro_m0=pack.macro_m0,
        fx_regime=fx_regime if fx_regime is not None else pack.fx_regime_auto,
        **kw,
    )


def _frac_saturada(history, var: str, lado: str, cota: float) -> float:
    serie = [r.state[var] for r in history.records]
    if not serie:
        return 0.0
    if lado == "piso":
        return sum(1 for v in serie if v <= cota + EPS) / len(serie)
    return sum(1 for v in serie if v >= cota - EPS) / len(serie)


# ---------------------------------------------------------------------------
# 1. Flag off y default por paquete.
# ---------------------------------------------------------------------------


def test_flag_off_is_bit_identical_to_a_country_without_the_feature() -> None:
    """Con `political_recovery=False` el motor tiene que dar exactamente lo
    mismo que un paquete que no declara el feature: ADR 018 no cambia una
    sola linea del JSONL con el flag apagado."""
    pack = load_country_pack("argentina", "1991-04", 24)
    sin_feature = pack.country.model_copy(
        update={
            "features": {
                k: v for k, v in pack.country.features.items() if k != "political_recovery"
            }
        }
    )
    apagado = run(
        seed=3,
        months=24,
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
        political_recovery=False,
    )
    sin_declarar = run(
        seed=3,
        months=24,
        country=sin_feature,
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
    assert apagado.to_jsonl() == sin_declarar.to_jsonl()


def test_aurora_does_not_declare_the_feature() -> None:
    """Aurora no declara `political_recovery`: el golden de
    `tests/test_country_pack_argentina.py` no se puede mover."""
    assert "political_recovery" not in load_country().features


def test_argentina_pack_turns_the_feature_on() -> None:
    pack = load_country_pack("argentina", "1991-04", 12)
    assert pack.country.features.get("political_recovery") is True


def test_flag_needs_macro_coefficients() -> None:
    """Doble compuerta (ADR 018 secc. 4): sin `macro_coefficients` no hay
    marcadores de ruptura que leer, asi que el mecanismo queda apagado
    aunque el flag este prendido."""
    country = load_country()
    con_flag = run(seed=5, months=12, country=country, actors_enabled=True, political_recovery=True)
    sin_flag = run(seed=5, months=12, country=country, actors_enabled=True)
    assert con_flag.to_jsonl() == sin_flag.to_jsonl()


# ---------------------------------------------------------------------------
# 2. Forma de los cuatro terminos (unit).
# ---------------------------------------------------------------------------


def _ctx(engaged: bool = True, **kw) -> RecoveryContext:
    return RecoveryContext(
        coeff=replace(PoliticalRecoveryCoefficients(), **kw),
        relief=engaged,
        streak=3 if engaged else 0,
        engaged=engaged,
    )


def test_terms_are_identity_when_not_engaged() -> None:
    ctx = _ctx(engaged=False)
    assert recover_approval(0.0, ctx) == 0.0
    assert recover_confidence(0.0, ctx) == 0.0
    assert recover_tension(100.0, ctx) == 100.0
    assert recover_protest(100.0, ctx) == 100.0
    assert recover_crime(100.0, ctx) == 100.0


def test_terms_are_identity_without_context() -> None:
    assert recover_approval(0.0, None) == 0.0
    assert recover_tension(100.0, None) == 100.0


def test_approval_moves_up_toward_the_reference_and_never_past_it() -> None:
    c = PoliticalRecoveryCoefficients()
    ctx = _ctx()
    x = 0.0
    for _ in range(500):
        x = recover_approval(x, ctx)
    assert 0.0 < x <= c.aprobacion_objetivo + EPS
    # Ya en el objetivo, el termino se apaga exactamente.
    assert recover_approval(c.aprobacion_objetivo, ctx) == pytest.approx(c.aprobacion_objetivo)
    # Por encima del objetivo no empuja hacia abajo: `pos(...)` lo apaga.
    assert recover_approval(80.0, ctx) == pytest.approx(80.0)


def test_confidence_moves_up_toward_the_reference_and_never_past_it() -> None:
    c = PoliticalRecoveryCoefficients()
    ctx = _ctx()
    x = 0.0
    for _ in range(5000):
        x = recover_confidence(x, ctx)
    assert 0.0 < x <= c.confianza_objetivo + EPS
    assert recover_confidence(90.0, ctx) == pytest.approx(90.0)


def test_tension_and_protest_move_down_toward_the_reference_and_never_past_it() -> None:
    c = PoliticalRecoveryCoefficients()
    ctx = _ctx()
    t, p = 100.0, 100.0
    for _ in range(2000):
        t, p = recover_social(t, p, ctx)
    assert c.tension_objetivo - EPS <= t < 100.0
    assert c.protesta_objetivo - EPS <= p < 100.0
    # Por debajo del objetivo no empuja hacia arriba.
    assert recover_tension(10.0, ctx) == pytest.approx(10.0)
    assert recover_protest(5.0, ctx) == pytest.approx(5.0)


def test_first_step_size_matches_the_documented_rate() -> None:
    """`x' += rec * pos(obj - x)`, literal: el primer paso desde la cota vale
    exactamente `rec * obj` (aprobacion) y `rec * (100 - obj)` (tension)."""
    c = PoliticalRecoveryCoefficients()
    ctx = _ctx()
    assert recover_approval(0.0, ctx) == pytest.approx(c.aprobacion_rec * c.aprobacion_objetivo)
    assert recover_tension(100.0, ctx) == pytest.approx(
        100.0 - c.tension_rec * (100.0 - c.tension_objetivo)
    )


def test_crime_term_is_off_by_default() -> None:
    """La quinta variable existe pero ADR 018 la deja apagada
    (`crime_rec = 0.0`): es un pendiente medido, no una decision del ADR."""
    assert PoliticalRecoveryCoefficients().crime_rec == 0.0
    assert recover_crime(100.0, _ctx()) == 100.0
    assert recover_crime(100.0, _ctx(crime_rec=0.1)) < 100.0


# ---------------------------------------------------------------------------
# 3. La compuerta (unit).
# ---------------------------------------------------------------------------


def _sin_ruptura(tracker: RecoveryTracker, inflation: float = 1.0) -> bool:
    return track_rupture(
        tracker,
        inflation=inflation,
        rupture_inflation=15.0,
        rupture_months=3,
        banking_crisis=False,
        sovereign_default=False,
        fx_exit_in_term=False,
    )


def test_rupture_needs_sustained_high_inflation() -> None:
    t = RecoveryTracker()
    assert _sin_ruptura(t, inflation=40.0) is False  # 1 mes
    assert _sin_ruptura(t, inflation=40.0) is False  # 2 meses
    assert _sin_ruptura(t, inflation=40.0) is True  # 3 meses: ruptura
    # Un mes por debajo del umbral reinicia el contador.
    assert _sin_ruptura(t, inflation=2.0) is False
    assert t.high_pi_months == 0


@pytest.mark.parametrize("marcador", ["banking_crisis", "sovereign_default", "fx_exit_in_term"])
def test_each_rupture_marker_closes_the_gate(marcador: str) -> None:
    kw = {"banking_crisis": False, "sovereign_default": False, "fx_exit_in_term": False}
    kw[marcador] = True
    assert (
        track_rupture(
            RecoveryTracker(),
            inflation=1.0,
            rupture_inflation=15.0,
            rupture_months=3,
            **kw,
        )
        is True
    )


def test_rupture_blocks_relief_even_with_a_perfect_economy() -> None:
    t = RecoveryTracker(inflation_window=[10.0] * 6)
    assert (
        relief_this_month(
            t,
            PoliticalRecoveryCoefficients(),
            inflation=0.0,
            gdp_growth=5.0,
            unemployment=5.0,
            unemployment_prev=8.0,
            rupture=True,
        )
        is False
    )


def test_disinflation_channel_opens_the_gate_with_high_inflation() -> None:
    """El caso de abril de 1990: 11,4 %/mes es inflacion ALTA, pero cae por
    debajo del 70 % de la media de los tres meses previos (78,8) y cuenta
    como alivio. Un umbral absoluto como el de ADR 012 secc. 5 lo perderia."""
    t = RecoveryTracker(inflation_window=[79.2, 61.6, 95.5])
    assert (
        relief_this_month(
            t,
            PoliticalRecoveryCoefficients(),
            inflation=11.4,
            gdp_growth=-5.0,
            unemployment=9.0,
            unemployment_prev=8.0,
            rupture=False,
        )
        is True
    )


def test_reactivation_channel_opens_the_gate_without_disinflation() -> None:
    """El caso 2009-2011: la inflacion no baja, pero el PBI crece y el
    desempleo no sube."""
    t = RecoveryTracker(inflation_window=[1.0] * 6)
    assert (
        relief_this_month(
            t,
            PoliticalRecoveryCoefficients(),
            inflation=2.0,
            gdp_growth=10.1,
            unemployment=7.2,
            unemployment_prev=8.6,
            rupture=False,
        )
        is True
    )


def test_no_relief_when_inflation_rises_and_activity_falls() -> None:
    t = RecoveryTracker(inflation_window=[1.0] * 6)
    assert (
        relief_this_month(
            t,
            PoliticalRecoveryCoefficients(),
            inflation=5.0,
            gdp_growth=-2.0,
            unemployment=11.0,
            unemployment_prev=10.0,
            rupture=False,
        )
        is False
    )


def _avanzar(tracker, coeff, inflation, gdp_growth, unemployment, unemployment_prev, rupture):
    return advance_recovery(
        tracker,
        coeff,
        inflation=inflation,
        gdp_growth=gdp_growth,
        unemployment=unemployment,
        unemployment_prev=unemployment_prev,
        rupture=rupture,
    )


def test_gate_engages_only_after_relief_months_and_resets() -> None:
    c = PoliticalRecoveryCoefficients()
    t = RecoveryTracker(inflation_window=[1.0] * 6)
    buen_mes = dict(
        inflation=1.0, gdp_growth=3.0, unemployment=8.0, unemployment_prev=9.0, rupture=False
    )
    ctxs = [_avanzar(t, c, **buen_mes) for _ in range(c.relief_months)]
    assert [x.engaged for x in ctxs] == [False] * (c.relief_months - 1) + [True]
    assert ctxs[-1].streak == c.relief_months
    # Un mes con ruptura reinicia la racha y desengancha.
    malo = _avanzar(t, c, **{**buen_mes, "rupture": True})
    assert malo.relief is False
    assert malo.streak == 0
    assert malo.engaged is False


def test_tracker_window_is_bounded() -> None:
    c = PoliticalRecoveryCoefficients()
    t = RecoveryTracker()
    for _ in range(200):
        _avanzar(
            t,
            c,
            inflation=1.0,
            gdp_growth=1.0,
            unemployment=8.0,
            unemployment_prev=8.0,
            rupture=False,
        )
    assert len(t.inflation_window) <= 24


# ---------------------------------------------------------------------------
# 4. Efecto medido sobre los arranques reales (regresion).
# ---------------------------------------------------------------------------

SEEDS = range(1, 16)


def test_mechanism_engages_in_2003_06_but_never_in_1991_04() -> None:
    """La compuerta discrimina: desde 2003-06 (economia creciendo) se
    engancha; desde 1991-04 (inflacion de 7 a 20 %/mes, nunca cayendo) no se
    engancha una sola vez. Medido en ADR 018 "Notas de implementacion":
    72 % de los meses contra 0 %."""
    enganches = {"2003-06": 0, "1991-04": 0}
    totales = {"2003-06": 0, "1991-04": 0}
    import republica.engine.simulation as simmod

    original = simmod.advance_recovery
    registro: list[tuple[str, bool]] = []

    def espia_factory(start):
        def espia(tracker, coeff, **kw):
            ctx = original(tracker, coeff, **kw)
            registro.append((start, ctx.engaged))
            return ctx

        return espia

    try:
        for start, months in (("2003-06", 150), ("1991-04", 120)):
            simmod.advance_recovery = espia_factory(start)
            for seed in (1, 2, 3):
                _corrida(start, months, seed, political_recovery=True)
    finally:
        simmod.advance_recovery = original

    for start, engaged in registro:
        totales[start] += 1
        enganches[start] += int(engaged)

    assert enganches["1991-04"] == 0, (
        f"la compuerta se engancho {enganches['1991-04']} veces desde 1991-04; "
        "ADR 018 secc. 3.2 (H6) predijo cero"
    )
    assert enganches["2003-06"] / totales["2003-06"] >= 0.5


def test_saturation_of_social_tension_falls_from_2003_06() -> None:
    """H1 de ADR 018 secc. 3.1, con el numero MEDIDO (no el umbral que se
    registro): la tension baja de 38 % a 28 % de la corrida. La hipotesis
    pedia <= 20 % y NO se cumplio; este test congela lo que si pasa, para
    que la proxima ronda sepa de donde parte."""
    antes = [
        _frac_saturada(
            _corrida("2003-06", 150, s, political_recovery=False), "social_tension", "techo", 100.0
        )
        for s in SEEDS
    ]
    despues = [
        _frac_saturada(
            _corrida("2003-06", 150, s, political_recovery=True), "social_tension", "techo", 100.0
        )
        for s in SEEDS
    ]
    m_antes, m_despues = statistics.median(antes), statistics.median(despues)
    assert m_antes > 0.30, m_antes
    assert m_despues < m_antes, (m_antes, m_despues)
    assert m_despues <= 0.32, m_despues


def test_h6_negative_prediction_1991_04_does_not_improve() -> None:
    """H6 de ADR 018 secc. 3.2, registrada ANTES de medir: desde 1991-04 la
    saturacion NO baja (la compuerta no se engancha nunca: la inflacion sube
    de 7 a 20 %/mes) y el colapso sigue ocurriendo en >= 10/15 semillas."""
    colapsos = 0
    deltas = []
    for s in SEEDS:
        off = _corrida("1991-04", 120, s, political_recovery=False)
        on = _corrida("1991-04", 120, s, political_recovery=True)
        colapsos += on.outcome == "collapse"
        for var, lado, cota in (
            ("government_approval", "piso", 0.0),
            ("social_tension", "techo", 100.0),
            ("protest_level", "techo", 100.0),
            ("institutional_confidence", "piso", 0.0),
        ):
            deltas.append(
                _frac_saturada(off, var, lado, cota) - _frac_saturada(on, var, lado, cota)
            )
    assert colapsos >= 10, colapsos
    assert max(deltas) < 0.15, max(deltas)


def test_recovery_never_pushes_a_variable_past_its_reference_in_a_real_run() -> None:
    """El mecanismo no puede inventar aprobacion: el termino se apaga en
    18,85, asi que nunca se puede atribuir una aprobacion alta al ADR 018."""
    fuerte = replace(
        PoliticalRecoveryCoefficients(),
        aprobacion_rec=0.9,
        tension_rec=0.9,
        protesta_rec=0.9,
        confianza_rec=0.9,
    )
    h = _corrida("2003-06", 60, 1, political_recovery=True, recovery_coeff=fuerte)
    # Con `rec` casi 1 el termino lleva cada variable a su referencia en un
    # paso, pero no mas alla: la tension nunca baja del 35 por este canal
    # salvo que la propia formula 5.3 la baje.
    assert all(r.state["social_tension"] >= 0.0 for r in h.records)
    assert all(r.state["government_approval"] <= 100.0 for r in h.records)


# ---------------------------------------------------------------------------
# 5. Los tres discriminantes (ADR 018 secc. 3.3).
# ---------------------------------------------------------------------------

N_DISC = 20
HYPER = 20.0


def _pack_run(start, months, seed, political_recovery, fx=None, elections=True):
    """Corrida SIN calibracion, igual que `tests/test_macro_regime.py`."""
    return _corrida(
        start,
        months,
        seed,
        political_recovery=political_recovery,
        calibration=None,
        fx_regime=fx,
        elections=elections,
    )


def test_d1_hyperinflation_still_reachable_from_1988_06() -> None:
    """Discriminante 1 (ADR 012 secc. 7 test 2a): el mecanismo no puede
    apagar la hiperinflacion de 1989."""
    cruzan = sum(
        any(
            r.state["inflation"] > HYPER
            for r in _pack_run("1988-06", 18, s, True, elections=False).records
        )
        for s in range(1, N_DISC + 1)
    )
    assert cruzan / N_DISC >= 0.5, f"{cruzan}/{N_DISC}"


def test_d1b_hyperinflation_still_not_spurious_from_2003_06() -> None:
    cruzan = sum(
        any(
            r.state["inflation"] > HYPER
            for r in _pack_run("2003-06", 18, s, True, elections=False).records
        )
        for s in range(1, N_DISC + 1)
    )
    assert cruzan == 0, f"{cruzan}/{N_DISC}"


def test_d2_collapse_or_default_still_happens_from_1998_01_with_peg() -> None:
    """Discriminante 2, el candado contra la amnistia general: desde 1998-01
    con `peg` el modelo tiene que seguir rompiendo. Si esto cae, el
    mecanismo salva a todos los gobiernos y hay que apagarlo."""
    rotas = 0
    for s in range(1, N_DISC + 1):
        h = _pack_run("1998-01", 54, s, True, fx="peg")
        if h.outcome in ("collapse", "hyperinflation") or any(
            "sovereign_default" in r.shocks_new or "sovereign_default" in r.shocks_active
            for r in h.records
        ):
            rotas += 1
    assert rotas / N_DISC >= 0.5, f"{rotas}/{N_DISC}"


def test_d2b_peg_still_exits_from_1998_01() -> None:
    salen = sum(
        any(
            "fx_regime_exit" in r.events
            for r in _pack_run("1998-01", 54, s, True, fx="peg").records
        )
        for s in range(1, N_DISC + 1)
    )
    assert salen / N_DISC >= 0.5, f"{salen}/{N_DISC}"


def test_adr_018_coefficients_stay_out_of_the_calibration_vector() -> None:
    """Los coeficientes de ADR 018 viven en su propio dataclass, NO en
    `MacroCoefficients`: `calibration/parameters.py::MACRO_TUNABLE` se arma
    con todos los campos `float` de aquel, asi que agregarlos ahi habria
    ampliado el espacio de CMA-ES de otro modulo sin avisar (ADR 018
    secc. 4)."""
    macro_fields = set(MacroCoefficients.__dataclass_fields__)
    recovery_fields = set(PoliticalRecoveryCoefficients.__dataclass_fields__)
    assert macro_fields.isdisjoint(recovery_fields)


def test_from_dict_ignores_unknown_keys_and_reads_both_shapes() -> None:
    a = PoliticalRecoveryCoefficients.from_dict({"coefficients": {"tension_rec": 0.5}})
    b = PoliticalRecoveryCoefficients.from_dict({"tension_rec": 0.5, "no_existe": 1})
    assert a.tension_rec == 0.5
    assert b.tension_rec == 0.5
    assert PoliticalRecoveryCoefficients.from_dict(None) == PoliticalRecoveryCoefficients()
