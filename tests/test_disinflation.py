"""ADR 021 — desinflación por credibilidad del programa.

Cubre los seis puntos de la sección 6 del ADR. El test central es
`test_disinflation_path_matches_the_three_real_episodes`: con la compuerta
cumplida, la trayectoria simulada desde ~25 %/mes tiene que caer dentro de la
banda que marcan los tres episodios reales medidos sobre el dato del repo
(Austral 1985, Convertibilidad 1991 y la estabilización de 2024).
"""

from __future__ import annotations

import random

from republica.world.config import load_country
from republica.world.economy import (
    DEFAULT_X0_M0_USD_M,
    MacroCoefficients,
    init_macro_state,
    step_macro_economy,
)
from republica.world.events import ShockAggregate

#: Meses que cada episodio real tardó en caer a la mitad de su inflación
#: inicial (ADR 021 secc. 3, medido sobre `inflation_cpi_monthly_linked.csv`):
#: Austral 1985 → 2, Convertibilidad 1991 → 1, estabilización 2024 → 3.
#: La banda observada es [1, 3]; se pide que el modelo caiga dentro de [1, 6],
#: laxa hacia el lado lento porque no tiene congelamiento de precios ni
#: desindexación por decreto, que es lo que hizo tan rápidos a 1985 y 1991.
HALVING_MONTHS_OBSERVED = (1, 3)
HALVING_MONTHS_ALLOWED = (1, 6)

INFLACION_INICIAL = 25.0


def _escenario(*, credibility_channel: bool, fiscal_balance: float, fx_regime: str = "crawl"):
    """Estado de arranque con inflación alta, y la compuerta de ADR 021
    cumplida o no según `fiscal_balance` (positivo = superávit)."""
    country = load_country()
    macro_coeff = MacroCoefficients(
        credibility_channel=credibility_channel,
        indexation_state=False,
    )
    state = country.initial_state.model_copy(
        update={
            "inflation": INFLACION_INICIAL,
            "inflation_lag1": INFLACION_INICIAL,
            "fiscal_balance": fiscal_balance,
            # Reservas holgadas a proposito: con las de Aurora el `crawl`
            # sale por `fx_regime_exit` al tercer mes y la credibilidad se
            # derrumba por una razon (el ancla se rompio) que NO es la que
            # este archivo mide. Que el ancla se rompa sin reservas ya lo
            # cubre `test_credibility_collapses_when_the_anchor_breaks`.
            "reserves": 400000.0,
        }
    )
    macro = init_macro_state(
        macro_coeff,
        fx_regime=fx_regime,
        initial_inflation=state.inflation,
        external_debt_usd_init=30000.0,
        x0=DEFAULT_X0_M0_USD_M,
        m0=DEFAULT_X0_M0_USD_M,
    )
    return country, macro_coeff, state, macro


def _trayectoria(*, credibility_channel: bool, fiscal_balance: float, meses: int = 12):
    country, macro_coeff, state, macro = _escenario(
        credibility_channel=credibility_channel, fiscal_balance=fiscal_balance
    )
    rng = random.Random(0)
    inflaciones = [state.inflation]
    credibilidades = []
    for _ in range(meses):
        state, _aux, macro_aux, macro, _ev, _pend = step_macro_economy(
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
        # El superávit es la política del escenario: se sostiene, que es
        # justamente lo que la compuerta exige.
        state = state.model_copy(update={"fiscal_balance": fiscal_balance})
        inflaciones.append(state.inflation)
        credibilidades.append(macro_aux.credibility)
    return inflaciones, credibilidades


# ---------------------------------------------------------------------------
# 1. Flag apagado: no-op exacto (ADR 021 secc. 6 punto 1 / H7).
# ---------------------------------------------------------------------------


def test_flag_off_is_a_byte_for_byte_noop() -> None:
    """Con el canal apagado no se calcula credibilidad, y con el canal
    prendido pero la compuerta cerrada (déficit) la trayectoria es IDÉNTICA
    a la del canal apagado. Ojo: el flag apagado no hace que el resultado
    fiscal deje de importar —el déficit entra por señoreaje, ADR 012 §2—,
    así que la comparación correcta es apagado contra prendido-sin-crédito,
    no superávit contra déficit."""
    apagado, creds_off = _trayectoria(credibility_channel=False, fiscal_balance=-4.0)
    prendido, creds_on = _trayectoria(credibility_channel=True, fiscal_balance=-4.0)
    assert all(c is None for c in creds_off), "no debe calcularse con el flag apagado"
    assert max(creds_on) == 0.0, f"con déficit no puede haber credibilidad: {creds_on}"
    assert apagado == prendido


# ---------------------------------------------------------------------------
# 2. La compuerta (ADR 021 secc. 6 punto 2).
# ---------------------------------------------------------------------------


def test_credibility_needs_both_anchor_and_surplus() -> None:
    """Ninguna de las dos condiciones alcanza sola."""
    _, solo_ancla = _trayectoria(credibility_channel=True, fiscal_balance=-4.0, meses=6)
    assert max(solo_ancla) == 0.0, f"déficit de 4 puntos no puede dar credibilidad: {solo_ancla}"

    country, macro_coeff, state, macro = _escenario(
        credibility_channel=True, fiscal_balance=2.0, fx_regime="float"
    )
    rng = random.Random(0)
    creds = []
    for _ in range(6):
        state, _a, macro_aux, macro, _e, _p = step_macro_economy(
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
        state = state.model_copy(update={"fiscal_balance": 2.0})
        creds.append(macro_aux.credibility)
    assert max(creds) == 0.0, f"sin ancla nominal (`float`) no puede haber credibilidad: {creds}"


def test_credibility_is_hard_to_gain_and_fast_to_lose() -> None:
    """La asimetría de `cred_adj` (0.25) contra `cred_adj_down` (0.60): es lo
    que impide que un mes fiscal bueno suelto compre credibilidad. Sin ella,
    el 1988 argentino —déficits de 4-5 puntos con episodios sueltos abajo de
    2— recibía 0.07-0.12 y rompía el discriminante H4."""
    mc = MacroCoefficients(credibility_channel=True)
    assert mc.cred_adj < mc.cred_adj_down
    # Misma brecha en los dos sentidos: 0.5 -> 1.0 contra 0.5 -> 0.0.
    brecha = 0.5
    sube = mc.cred_adj * brecha
    baja = mc.cred_adj_down * brecha
    assert baja > sube, (
        f"con la misma brecha, perder ({baja:.3f}) tiene que ser más rápido que ganar ({sube:.3f})"
    )


# ---------------------------------------------------------------------------
# 3. Forma de `rho_eff` (ADR 021 secc. 6 puntos 3 y 6).
# ---------------------------------------------------------------------------


def test_more_credibility_never_raises_persistence() -> None:
    """Monotonía: `rho_eff` no puede subir cuando sube la credibilidad."""
    mc = MacroCoefficients(credibility_channel=True)
    valores = [mc.rho_pi * (1.0 - mc.cred_rho * c) for c in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert valores == sorted(valores, reverse=True), valores
    assert valores[0] == mc.rho_pi
    assert abs(valores[-1] - mc.rho_pi * (1.0 - mc.cred_rho)) < 1e-12


# ---------------------------------------------------------------------------
# 4. El test central: la trayectoria contra los tres episodios reales.
# ---------------------------------------------------------------------------


def test_disinflation_path_matches_the_three_real_episodes() -> None:
    """Con ancla y superávit sostenido desde ~25 %/mes, la inflación tiene que
    caer a la mitad dentro de la banda de los tres episodios reales, y seguir
    bajando. Es la propiedad que el modelo NO tenía: antes de ADR 021 toda
    trayectoria desde ese nivel era explosiva (`docs/EMERGENCE_LOG.md`)."""
    inflaciones, creds = _trayectoria(credibility_channel=True, fiscal_balance=2.0, meses=12)
    assert max(creds) > 0.5, f"la compuerta no enganchó: credibilidades {creds}"

    objetivo = inflaciones[0] / 2.0
    mes_mitad = next((i for i, v in enumerate(inflaciones) if v <= objetivo), None)
    assert mes_mitad is not None, f"no cae a la mitad en 12 meses: {inflaciones}"
    lo, hi = HALVING_MONTHS_ALLOWED
    assert lo <= mes_mitad <= hi, (
        f"cae a la mitad en el mes {mes_mitad}; los tres episodios reales lo hicieron en "
        f"{HALVING_MONTHS_OBSERVED[0]}-{HALVING_MONTHS_OBSERVED[1]} y la banda aceptada es "
        f"{lo}-{hi}. Trayectoria: {[round(v, 1) for v in inflaciones]}"
    )
    assert inflaciones[-1] < inflaciones[mes_mitad], "tiene que seguir bajando después de halvarse"


def test_without_the_mechanism_the_same_scenario_does_not_disinflate() -> None:
    """El contraste que le da sentido al test anterior: el mismo escenario,
    mismo superávit, sin el canal, no desinflaciona."""
    con, _ = _trayectoria(credibility_channel=True, fiscal_balance=2.0, meses=12)
    sin, _ = _trayectoria(credibility_channel=False, fiscal_balance=2.0, meses=12)
    assert con[-1] < sin[-1], (
        f"con el canal la inflación final es {con[-1]:.1f} y sin él {sin[-1]:.1f}: "
        "el mecanismo no está haciendo nada"
    )


def test_credibility_collapses_when_the_anchor_breaks() -> None:
    """Un ancla que se rompe se lleva la credibilidad puesta, aunque el
    superávit siga. Es el caso que separa 2001 de 2024: la convertibilidad
    tenía ancla hasta que las reservas no alcanzaron. Medido con las
    reservas de Aurora, que no alcanzan para sostener el `crawl`."""
    country, macro_coeff, state, macro = _escenario(credibility_channel=True, fiscal_balance=2.0)
    rng = random.Random(0)
    creds, salio = [], False
    for mes in range(1, 9):
        if mes == 4:
            # A mitad de camino se le saca el respaldo al ancla, con el
            # superavit intacto: lo unico que cambia es que el regimen ya no
            # se puede defender.
            state = state.model_copy(update={"reserves": 1.0})
        state, _a, macro_aux, macro, ev, _p = step_macro_economy(
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
        state = state.model_copy(update={"fiscal_balance": 2.0})
        salio = salio or "fx_regime_exit" in ev
        creds.append(macro_aux.credibility)
    assert salio, "el escenario tiene que romper el ancla para que el test signifique algo"
    assert max(creds[:3]) > 0.2, f"la credibilidad tenía que construirse primero: {creds}"
    assert creds[-1] < max(creds) / 2.0, (
        f"la credibilidad no se derrumbó tras romperse el ancla, con el superávit intacto: {creds}"
    )
