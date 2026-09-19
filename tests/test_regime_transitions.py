"""ADR 015 — transiciones de regimen endogenas (`features.regime_endogenous_
transitions`), DoD de la seccion 6 del ADR.

1. Flag apagado: `step_regime` identico a ADR 011 (referencia reimplementada
   aca abajo) y la corrida del paquete de pais byte a byte igual. Los golden
   hashes de Aurora viven en `tests/test_country_pack_argentina.py` y
   `tests/test_macro_regime.py`, que siguen corriendo sin cambios.
2. Desde `dictatorship` con `months_in_mode` grande: P(salida a 8 años) > 80 %.
3. Desde `democracy` con estabilidad alta: P(golpe a 4 años) < 5 %.
4. Ventana 1976-03 -> 1984 sin golpes forzados: >= 50 % de semillas vuelven a
   `democracy` antes de 1984-12.
5. Ventana que arranca en 1930-09 (`coup`): el modo a +24 meses no es `coup`.

Las pruebas 2-5 corren la maquina de estados (`step_regime`) directamente,
con el estado del mundo sostenido en un nivel declarado, en vez de la
simulacion completa: el objetivo es medir el MECANISMO de transicion, y una
corrida completa de esa epoca termina por `collapse`/`hyperinflation` a los
10-12 meses (comportamiento previo del motor, ajeno a este ADR) antes de que
el hazard llegue a jugarse. Todo el archivo corre en pocos segundos.
"""

from __future__ import annotations

import random

import pytest

from republica.backtest.runner import backtest_regime_calendar
from republica.world.countries import country_pack_dir, load_country_pack
from republica.world.regime import (
    COUP_CONFIDENCE_THRESHOLD,
    COUP_STABILITY_THRESHOLD,
    DEFAULT_REGIME_TRANSITION_COEFFICIENTS,
    DICTATORSHIP_TENSION_THRESHOLD,
    REGIME_MODES,
    REGIME_MODES_ENDOGENOUS,
    REGIMES_CSV_TO_ENGINE_MODE,
    REPRESSION_BY_MODE,
    RESTRICTED_DEMOCRACY,
    TRANSITION_MAX_MONTHS,
    RegimeState,
    RegimeStepResult,
    build_regime_calendar,
    initial_regime_state,
    load_regimes_by_year,
    regime_effects_on_state,
    step_regime,
)
from republica.world.state import WorldState, clamp

REGIMES_CSV = country_pack_dir("argentina") / "politics" / "regimes.csv"
EVENTS_CSV = country_pack_dir("argentina") / "politics" / "events.csv"

#: Estado base "neutro" para los Monte Carlo; cada prueba sobreescribe lo que
#: le importa.
_BASE_STATE = dict(
    gdp=100.0,
    gdp_growth=1.0,
    inflation=2.0,
    unemployment=8.0,
    real_wage=100.0,
    interest_rate=10.0,
    exchange_rate=100.0,
    reserves=100.0,
    public_debt=50.0,
    fiscal_balance=-2.0,
    poverty=25.0,
    government_approval=45.0,
    congress_support=45.0,
    political_stability=45.0,
    social_tension=45.0,
    institutional_confidence=40.0,
    consumer_confidence=45.0,
    protest_level=30.0,
    inequality=45.0,
    crime_perception=45.0,
    inflation_lag1=2.0,
)


def world(**overrides) -> WorldState:
    return WorldState(**{**_BASE_STATE, **overrides})


def _clamped(state: WorldState) -> WorldState:
    """Recorta a [0, 100] las tres variables que toca `regime_effects_on_
    state`, igual que hace `clamp_state` dentro del motor."""
    return state.model_copy(
        update={
            "protest_level": clamp(state.protest_level, 0.0, 100.0),
            "social_tension": clamp(state.social_tension, 0.0, 100.0),
            "institutional_confidence": clamp(state.institutional_confidence, 0.0, 100.0),
        }
    )


def run_regime_months(
    seed: int,
    months: int,
    initial: RegimeState,
    state: WorldState,
    coup_propensity: float = 0.006,
    coefficients=DEFAULT_REGIME_TRANSITION_COEFFICIENTS,
) -> list[str]:
    """Modos mes a mes de una corrida SOLO de la maquina de regimen, con la
    realimentacion de `repression` sobre el estado (lo unico que el motor le
    hace al estado desde el regimen) y sin ningun golpe forzado."""
    rng = random.Random(seed)
    regime = RegimeState(
        mode=initial.mode,
        months_in_mode=initial.months_in_mode,
        de_facto_months=initial.de_facto_months,
    )
    current = state
    modes: list[str] = []
    for _ in range(months):
        result = step_regime(
            regime,
            current,
            rng,
            forced_coup=False,
            coup_propensity=coup_propensity,
            transition_coefficients=coefficients,
        )
        current = _clamped(regime_effects_on_state(current, result.repression))
        modes.append(result.mode)
    return modes


# ---------------------------------------------------------------------------
# 1. Flag apagado == ADR 011, exactamente
# ---------------------------------------------------------------------------


def _step_regime_adr011_reference(
    state: RegimeState,
    world_state: WorldState,
    rng: random.Random,
    forced_coup: bool,
    coup_propensity: float,
) -> RegimeStepResult:
    """Reimplementacion literal de `step_regime` TAL COMO ERA antes de ADR
    015 (copiada del ADR 011 secc. 3). Es el golden de la prueba 1: si
    alguien cambia el camino sin flag de `world/regime.py`, esto lo caza."""
    event: str | None = None
    forced_election = False
    mode = state.mode
    if mode == "democracy":
        endogenous = (
            coup_propensity > 0.0
            and world_state.political_stability < COUP_STABILITY_THRESHOLD
            and world_state.institutional_confidence < COUP_CONFIDENCE_THRESHOLD
            and rng.random() < coup_propensity
        )
        if forced_coup or endogenous:
            mode, event = "coup", "coup"
    elif mode == "coup":
        mode, event = "dictatorship", "regime_to_dictatorship"
    elif mode == "dictatorship":
        if world_state.social_tension > DICTATORSHIP_TENSION_THRESHOLD:
            mode, event = "transition", "regime_transition"
    elif mode == "transition":
        if state.months_in_mode >= TRANSITION_MAX_MONTHS:
            mode, event = "democracy", "regime_democracy_restored"
            forced_election = True
    if mode == state.mode:
        state.months_in_mode += 1
    else:
        state.months_in_mode = 0
    state.mode = mode
    return RegimeStepResult(
        mode=mode,
        repression={
            "democracy": 0.0,
            "coup": 0.6,
            "dictatorship": 0.85,
            "transition": 0.25,
        }[mode],
        event=event,
        forced_next_election=forced_election,
    )


@pytest.mark.parametrize("start_mode", REGIME_MODES)
def test_flag_off_step_regime_matches_adr011_reference(start_mode: str) -> None:
    """Prueba 1: sin `transition_coefficients`, `step_regime` produce el mismo
    modo, la misma `repression`, el mismo evento y CONSUME LA MISMA cantidad
    de valores del RNG que antes de ADR 015."""
    for seed in range(8):
        rng_a = random.Random(seed)
        rng_b = random.Random(seed)
        state_a = RegimeState(mode=start_mode, months_in_mode=3)
        state_b = RegimeState(mode=start_mode, months_in_mode=3)
        current = world(political_stability=12.0, institutional_confidence=9.0)
        for month in range(60):
            forced = month == 17 and seed % 3 == 0
            got = step_regime(state_a, current, rng_a, forced, 0.02)
            want = _step_regime_adr011_reference(state_b, current, rng_b, forced, 0.02)
            assert (got.mode, got.repression, got.event, got.forced_next_election) == (
                want.mode,
                want.repression,
                want.event,
                want.forced_next_election,
            )
            assert state_a.mode == state_b.mode
            assert state_a.months_in_mode == state_b.months_in_mode
            current = _clamped(regime_effects_on_state(current, got.repression))
        # Mismo consumo de RNG: si no, el resto de la corrida divergiria.
        assert rng_a.random() == rng_b.random()


def test_flag_off_country_pack_calendar_is_unchanged() -> None:
    """Prueba 1 (bis): el `RegimeCalendar` que arma el paquete sin el flag es
    el de siempre -- modo inicial `democracy`, 0 meses, sin coeficientes."""
    cal = build_regime_calendar(EVENTS_CSV, 1976, 3, 24, "auto")
    assert cal.endogenous_transitions is False
    assert cal.resolved_coefficients() is None
    assert (cal.initial_mode, cal.initial_months_in_mode, cal.initial_de_facto_months) == (
        "democracy",
        0,
        0,
    )
    assert cal.initial_regime_state() == RegimeState()

    pack_off = load_country_pack("argentina", "1983-12", 12, regime_mode="auto")
    assert pack_off.regime_calendar.endogenous_transitions is False
    assert pack_off.regime_calendar.initial_mode == "democracy"


def test_flag_on_seeds_initial_mode_from_regimes_csv() -> None:
    """El flag prendido siembra el modo inicial REAL (y su antiguedad), que es
    la mitad del mecanismo: el hazard depende de la duracion."""
    cal = build_regime_calendar(
        EVENTS_CSV,
        1977,
        1,
        24,
        "auto",
        endogenous_transitions=True,
        regimes_csv=REGIMES_CSV,
    )
    assert cal.endogenous_transitions is True
    assert cal.resolved_coefficients() is DEFAULT_REGIME_TRANSITION_COEFFICIENTS
    assert cal.initial_mode == "dictatorship"
    # El bloque `dictatorship` se extiende hacia atras sobre el año `coup`
    # (1976), asi que a enero de 1977 el Proceso tiene 12 meses, no 0.
    assert cal.initial_months_in_mode == 12

    # `--regime-mode democracy` NO siembra (ese modo significa "este pais
    # nunca sale de democracia", ADR 011 secc. 9 item 4).
    cal_dem = build_regime_calendar(
        EVENTS_CSV,
        1977,
        1,
        24,
        "democracy",
        endogenous_transitions=True,
        regimes_csv=REGIMES_CSV,
    )
    assert cal_dem.initial_mode == "democracy"
    assert cal_dem.coup_propensity == {}


def test_every_csv_mode_maps_to_an_engine_mode() -> None:
    """Los 6 `regime_mode` de `regimes.csv` tienen que caer en los 5 modos del
    motor, y el quinto modo NO puede estar en `REGIME_MODES` (que sigue siendo
    la lista de ADR 011, alcanzable con el flag apagado)."""
    assert set(load_regimes_by_year(REGIMES_CSV).values()) == set(REGIMES_CSV_TO_ENGINE_MODE)
    assert set(REGIMES_CSV_TO_ENGINE_MODE.values()) <= set(REGIME_MODES_ENDOGENOUS)
    assert RESTRICTED_DEMOCRACY not in REGIME_MODES
    assert set(REPRESSION_BY_MODE) == set(REGIME_MODES_ENDOGENOUS)


def test_initial_regime_state_maps_restricted_democracy() -> None:
    """`restricted_democracy` de `regimes.csv` llega al motor como el quinto
    modo (ADR 015 secc. 2(b)), no como `democracy`."""
    assert initial_regime_state(REGIMES_CSV, 1964, 1).mode == RESTRICTED_DEMOCRACY
    assert initial_regime_state(REGIMES_CSV, 1930, 9).mode == "coup"
    assert initial_regime_state(REGIMES_CSV, 1983, 1).mode == "democracy"
    # Año fuera de la serie: default de siempre.
    assert initial_regime_state(REGIMES_CSV, 2500, 1) == RegimeState()


# ---------------------------------------------------------------------------
# 2-3. Probabilidades acumuladas del hazard
# ---------------------------------------------------------------------------


def test_dictatorship_exits_within_8_years_in_more_than_80pct() -> None:
    """Prueba 2: desde `dictatorship` con `months_in_mode` grande (72 meses,
    la edad del Proceso en 1982-01), la probabilidad acumulada de salir del
    modo a 8 años supera el 80 %."""
    initial = RegimeState(mode="dictatorship", months_in_mode=72, de_facto_months=72)
    state = world(
        political_stability=24.0,
        institutional_confidence=0.0,
        social_tension=67.0,
        inflation=8.0,
        gdp_growth=1.3,
    )
    exits = 0
    n = 300
    for seed in range(n):
        modes = run_regime_months(seed, 96, initial, state)
        if any(m != "dictatorship" for m in modes):
            exits += 1
    assert exits / n > 0.80, f"solo {exits}/{n} salieron de la dictadura en 8 años"


def test_stable_democracy_coup_probability_under_4_years_below_5pct() -> None:
    """Prueba 3: desde `democracy` con estabilidad alta, la probabilidad de
    golpe a 4 años queda por debajo del 5 %."""
    initial = RegimeState(mode="democracy", months_in_mode=0)
    state = world(
        political_stability=85.0,
        institutional_confidence=75.0,
        social_tension=20.0,
        inflation=1.0,
        gdp_growth=3.0,
    )
    coups = 0
    n = 600
    for seed in range(n):
        modes = run_regime_months(seed, 48, initial, state)
        if "coup" in modes:
            coups += 1
    assert coups / n < 0.05, f"{coups}/{n} semillas con golpe en 4 años de democracia estable"


def test_unstable_democracy_is_riskier_than_stable_one() -> None:
    """Contraparte de la prueba 3 (que sola se cumpliria con un hazard
    identicamente 0): con el estado en crisis el golpe SI aparece."""
    initial = RegimeState(mode="democracy", months_in_mode=0)
    state = world(
        political_stability=12.0,
        institutional_confidence=5.0,
        social_tension=85.0,
        inflation=20.0,
        gdp_growth=-5.0,
    )
    coups = sum(1 for seed in range(200) if "coup" in run_regime_months(seed, 48, initial, state))
    assert coups / 200 > 0.20


def test_restricted_democracy_is_riskier_than_full_democracy() -> None:
    """La diferencia empirica central de ADR 015 secc. 3.2 (3,7 veces el
    riesgo de golpe) tiene que verse en el motor."""
    state = world(
        political_stability=42.0,
        institutional_confidence=8.0,
        social_tension=55.0,
        inflation=6.0,
        gdp_growth=1.8,
    )
    n = 400
    restricted = sum(
        1
        for seed in range(n)
        if "coup" in run_regime_months(seed, 96, RegimeState(mode=RESTRICTED_DEMOCRACY), state)
    )
    full = sum(
        1
        for seed in range(n)
        if "coup" in run_regime_months(seed, 96, RegimeState(mode="democracy"), state)
    )
    assert restricted > full, f"restringida {restricted}/{n} vs. plena {full}/{n}"


# ---------------------------------------------------------------------------
# 4-5. Ventanas historicas
# ---------------------------------------------------------------------------


def test_backtest_calendar_with_transitions_never_forces_a_coup() -> None:
    """ADR 014, "Desviacion deliberada del calendario": el mecanismo de ADR
    015 tiene que correr SIN golpes forzados, incluso sobre una ventana que
    cruza golpes reales (1976-03 cruza el del 24 de marzo de 1976)."""
    cal = backtest_regime_calendar(
        country_pack_dir("argentina"), 1976, 3, 105, regime_transitions=True
    )
    assert cal.forced_coup_months == set()
    assert cal.endogenous_transitions is True
    assert cal.initial_mode == "coup"


def test_window_1976_03_returns_to_democracy_before_1984_12() -> None:
    """Prueba 4: arrancando en 1976-03 (`coup` real, sembrado de
    `regimes.csv`) y SIN ningun golpe forzado, al menos la mitad de las
    semillas vuelven a `democracy` antes de 1984-12 (105 meses)."""
    cal = backtest_regime_calendar(
        country_pack_dir("argentina"), 1976, 3, 105, regime_transitions=True
    )
    assert cal.forced_coup_months == set()
    initial = cal.initial_regime_state()
    assert initial.mode == "coup"
    state = world(
        political_stability=24.0,
        institutional_confidence=0.0,
        social_tension=67.0,
        inflation=8.0,
        gdp_growth=1.3,
    )
    n = 300
    back = sum(
        1 for seed in range(n) if "democracy" in run_regime_months(seed, 105, initial, state)
    )
    assert back / n >= 0.50, f"solo {back}/{n} semillas volvieron a democracia antes de 1984-12"


def test_window_starting_1930_09_is_not_coup_24_months_later() -> None:
    """Prueba 5: una ventana que arranca en 1930-09 (`coup` en `regimes.csv`)
    no esta en `coup` a los +24 meses.

    Dos aserciones distintas, porque el enunciado admite un caso de borde
    real: el `coup` INICIAL no persiste nunca (dura exactamente 1 mes, ADR
    011 secc. 3, y eso se verifica semilla por semilla), pero el modelo si
    puede producir un golpe NUEVO dentro de la ventana despues de haber
    vuelto a un gobierno civil -- justamente lo que antes de ADR 015 no
    podia pasar. Medido: 4 de 400 semillas (1 %) caen en ese caso, asi que
    el modo mayoritario (el criterio con el que `backtest/scoring.py`
    resuelve una ventana) nunca es `coup`.
    """
    initial = initial_regime_state(REGIMES_CSV, 1930, 9)
    assert initial.mode == "coup"
    state = world(
        political_stability=24.0,
        institutional_confidence=0.0,
        social_tension=67.0,
        inflation=8.0,
        gdp_growth=1.3,
    )
    n = 400
    at_24: list[str] = []
    for seed in range(n):
        modes = run_regime_months(seed, 24, initial, state)
        # El `coup` inicial dura exactamente 1 mes: al mes 1 ya es dictadura.
        assert modes[0] == "dictatorship", f"semilla {seed}: el coup inicial persistio"
        at_24.append(modes[23])
    coup_at_24 = at_24.count("coup")
    majority = max(set(at_24), key=at_24.count)
    assert majority != "coup"
    assert coup_at_24 / n < 0.05, f"{coup_at_24}/{n} semillas en `coup` a +24 meses"
