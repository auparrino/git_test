"""Modo de regimen (ADR 011 secc. 3, `features.regime`).

Cuatro modos: `democracy`, `coup` (1 mes), `dictatorship`, `transition`
(<=24 meses). Todo lo de este modulo es aditivo y sin efecto alguno mientras
nadie lo invoque: `engine/simulation.py::run()` solo lo consulta cuando se le
pasa un `RegimeCalendar` explicito (default `None` = comportamiento de
siempre, ver Notas de implementacion del ADR 011).

Alcance deliberadamente acotado (ver ADR 011, Notas de implementacion, para
la lista completa de deviaciones): el "reemplazo del presidente por la junta"
y la restriccion de `write` a partidos/sindicatos (ADR 011 secc. 3, columna
`Actores`) NO se instancian como cambios al `ActorEngine` -- se modelan como
suspension de elecciones/Congreso mas la variable `repression`, que empuja
`protest_level`/`social_tension`/`institutional_confidence` con la misma
mecanica que un shock (ver `regime_effects_on_state`).

ADR 015 (`features.regime_endogenous_transitions`, default `False`) agrega
un QUINTO modo (`restricted_democracy`) y reemplaza los umbrales duros de
arriba por un modelo de riesgo (hazard) mensual Weibull por transicion, con
las tasas base estimadas por maxima verosimilitud de las duraciones reales
1916-1983 (`scripts/fit_regime_hazards.py`). Todo eso esta detras del flag:
con el flag apagado (`RegimeCalendar.endogenous_transitions = False`, el
default) `step_regime` devuelve EXACTAMENTE lo mismo que antes de ADR 015 y
no consume ningun valor del RNG nuevo.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from republica.world.state import WorldState

REGIME_MODES = ("democracy", "coup", "dictatorship", "transition")

#: Modo nuevo de ADR 015 secc. 2(b): "hay elecciones pero con fraude o
#: proscripcion" (74 de los 214 años de `politics/regimes.csv`, el modo mas
#: frecuente de la serie argentina). Es un modo PROPIO y no un alias de
#: `democracy` porque `REGIME_CROSSCHECK.md` secc. 3 ya establecio que la
#: binarizacion correcta lo cuenta como autocracia electoral (V-Dem
#: `v2x_regime = 1`), igual que `backtest/scoring.py`, que puntua
#: `mode == "democracy"`. Inalcanzable con el flag apagado.
RESTRICTED_DEMOCRACY = "restricted_democracy"

#: Los cinco modos con `features.regime_endogenous_transitions` prendido.
#: `REGIME_MODES` (los cuatro de ADR 011) queda intacto a proposito: es
#: superficie publica y con el flag apagado sigue siendo la lista completa.
REGIME_MODES_ENDOGENOUS = (*REGIME_MODES, RESTRICTED_DEMOCRACY)

#: Umbrales del golpe endogeno (ADR 011 secc. 3, columna "Como se entra").
COUP_STABILITY_THRESHOLD = 20.0
COUP_CONFIDENCE_THRESHOLD = 30.0

#: Umbral de salida de la dictadura (ADR 011 secc. 3, columna "Como se sale").
DICTATORSHIP_TENSION_THRESHOLD = 70.0

#: Tope de duracion de una transicion (ADR 011 secc. 3): pasado este numero
#: de meses en `transition` sin que haya corrido una eleccion, se fuerza la
#: vuelta a `democracy` el mes siguiente (con una eleccion ese mismo mes).
TRANSITION_MAX_MONTHS = 24

#: Efecto de `repression` sobre el estado (ADR 011 secc. 3: "baja
#: protest_level y sube social_tension latente y baja institutional_
#: confidence"), coeficientes de diseno (no calibrados -- ver Notas de
#: implementacion del ADR 011).
REPRESSION_PROTEST_COEF = -8.0
REPRESSION_TENSION_COEF = 5.0
REPRESSION_CONFIDENCE_COEF = -3.0

#: `repression` por modo (ADR 011 secc. 3: la variable solo tiene sentido
#: bajo `dictatorship`; se modela tambien un nivel menor bajo `coup`/
#: `transition` porque las instituciones todavia no se restablecieron del
#: todo, con 0 en `democracy`).
REPRESSION_BY_MODE = {
    "democracy": 0.0,
    "coup": 0.6,
    "dictatorship": 0.85,
    "transition": 0.25,
    # ADR 015 secc. 2(b): hay elecciones y Congreso, pero con proscripcion,
    # fraude y estado de sitio recurrente -- un nivel de represion bajo pero
    # no nulo. Coeficiente de DISEÑO (como los otros cuatro de este dict,
    # ver Notas de implementacion del ADR 011); solo alcanzable con
    # `features.regime_endogenous_transitions`.
    RESTRICTED_DEMOCRACY: 0.35,
}


@dataclass
class RegimeState:
    """Estado del regimen, persistente mes a mes (mutado por `step_regime`)."""

    mode: str = "democracy"
    months_in_mode: int = 0
    #: ADR 015 secc. 3.4: meses acumulados del REGIMEN DE FACTO en curso
    #: (`coup` + `dictatorship` + `transition`), para decidir el destino de
    #: la salida. Vuelve a 0 apenas el regimen es civil. Sin
    #: `features.regime_endogenous_transitions` nadie lo lee ni lo escribe.
    de_facto_months: int = 0


@dataclass
class RegimeStepResult:
    mode: str
    repression: float
    event: str | None
    forced_next_election: bool = False


# ---------------------------------------------------------------------------
# ADR 015: modelo de riesgo (hazard) mensual por transicion.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeTransitionCoefficients:
    """Coeficientes del modelo de riesgo de ADR 015.

    Dos familias distintas, y la diferencia importa para leer cualquier
    resultado (ADR 015 secc. 3 y 4):

    * las ESCALAS/FORMAS Weibull (`*_scale`, `*_shape`) estan ESTIMADAS por
      maxima verosimilitud de las duraciones reales 1916-2023
      (`scripts/fit_regime_hazards.py`, que las imprime);
    * los `*_beta_*` son coeficientes de DISEÑO: con 6 golpes y 6 dictaduras
      no hay grados de libertad para estimar un modelo con cinco
      covariables, asi que solo su SIGNO esta justificado.

    Todo es un dataclass propio (y no constantes de modulo) justamente para
    que `calibration/` pueda tomarlo como vector de parametros mas adelante
    sin tocar este archivo.
    """

    # -- tasas base, ESTIMADAS (ADR 015 secc. 3.2) ----------------------
    #: Escala Weibull (meses) del golpe desde `democracy`. MLE sobre 4
    #: periodos de democracia plena (3 golpes, 792 meses de exposicion, el
    #: periodo 1983-12 -> 2023-12 censurado).
    coup_democracy_scale: float = 263.17
    #: Forma Weibull del golpe desde `democracy` (mismo ajuste). `k < 1` =
    #: riesgo decreciente con la edad del periodo democratico. OJO: el test
    #: de razon de verosimilitud NO rechaza `k = 1` (LR 0,06 vs. 3,84).
    coup_democracy_shape: float = 0.893
    #: Escala Weibull (meses) del golpe desde `restricted_democracy`. MLE
    #: sobre los 3 periodos de democracia restringida (1932-43, 1958-62,
    #: 1963-66): los tres terminaron en golpe, en 216 meses.
    coup_restricted_scale: float = 81.49
    #: Forma Weibull del golpe desde `restricted_democracy` (mismo ajuste).
    coup_restricted_shape: float = 1.705
    #: Escala Weibull (meses) de la salida de `dictatorship` hacia
    #: `transition`. MLE sobre las 6 dictaduras 1930/1943/1955/1962/1966/
    #: 1976, con la duracion NETA del traspaso final (266 meses de
    #: exposicion) para no contar dos veces los mismos meses.
    dictatorship_exit_scale: float = 49.51
    #: Forma Weibull de la salida de `dictatorship` (mismo ajuste).
    dictatorship_exit_shape: float = 1.514
    #: Escala Weibull (meses) del traspaso final (`transition` -> gobierno
    #: civil). MLE sobre los 6 lapsos eleccion->asuncion reales (3,3,2,3,2,1
    #: meses).
    handover_scale: float = 2.59
    #: Forma Weibull del traspaso final (mismo ajuste). Es la unica de las
    #: cuatro transiciones donde el LR SI rechaza el hazard constante (8,97).
    handover_shape: float = 3.803

    # -- covariables del golpe, DISEÑO (ADR 015 secc. 4) ----------------
    #: Efecto de `(political_stability - 50)/50` sobre el log-hazard de
    #: golpe. Negativo: mas estabilidad, menos riesgo.
    coup_beta_stability: float = -1.6
    #: Efecto de `(institutional_confidence - 50)/50` sobre el log-hazard de
    #: golpe. Negativo.
    coup_beta_confidence: float = -1.2
    #: Efecto de `(social_tension - 50)/50` sobre el log-hazard de golpe.
    #: Positivo.
    coup_beta_tension: float = 0.8
    #: Efecto de `clamp(inflation, -5, 50)/10` (inflacion MENSUAL en %)
    #: sobre el log-hazard de golpe. Positivo.
    coup_beta_inflation: float = 0.25
    #: Efecto de `clamp(gdp_growth, -20, 20)/10` sobre el log-hazard de
    #: golpe. Negativo.
    coup_beta_growth: float = -0.2
    #: Termino constante del log-hazard de golpe DESDE `democracy`.
    #: NO es 0: la tasa base de arriba es una tasa INCONDICIONAL (el MLE
    #: sobre toda la historia), asi que el multiplicador tiene que valer 1
    #: en el estado TIPICO, no en un 50/50/50 arbitrario. Este valor es
    #: `-(suma de betas por el estado tipico)`, con el estado tipico MEDIDO:
    #: la mediana que produce el motor bajo `democracy` en las ventanas
    #: t0 = 1961..1983, h = 48, 5 semillas (stability 30,4; confidence 0,0;
    #: tension 59,3; inflacion 11,9; crecimiento 1,9).
    coup_log_offset_democracy: float = -2.236
    #: Idem para `restricted_democracy` (estado tipico medido: stability
    #: 42,6; confidence 8,2; tension 54,9; inflacion 6,0; crecimiento 1,8).
    #: Hace falta uno propio porque el estado tipico de los dos modos NO es
    #: el mismo y un solo offset no puede centrar los dos.
    coup_log_offset_restricted: float = -1.434

    # -- covariables de la salida de dictadura, DISEÑO ------------------
    #: Efecto de `(social_tension - 50)/50` sobre el log-hazard de salida de
    #: `dictatorship`. Positivo (ADR 011 secc. 3 ya usaba `social_tension >
    #: 70` como UNICA salida).
    exit_beta_tension: float = 0.9
    #: Efecto de `repression - 0.85` sobre el log-hazard de salida.
    #: Negativo: mas represion, mas capacidad de permanecer. Con
    #: `REPRESSION_BY_MODE["dictatorship"] = 0.85` esta covariable vale 0
    #: hoy siempre; se deja expuesta para calibracion.
    exit_beta_repression: float = -1.0
    #: Efecto de la inflacion mensual normalizada sobre el log-hazard de
    #: salida. Positivo.
    exit_beta_inflation: float = 0.25
    #: Efecto del crecimiento normalizado sobre el log-hazard de salida.
    #: Negativo.
    exit_beta_growth: float = -0.25
    #: Efecto de la confianza institucional normalizada sobre el log-hazard
    #: de salida. 0: sin signo claro a priori.
    exit_beta_confidence: float = 0.0
    #: Termino constante del log-hazard de salida de `dictatorship`, por el
    #: mismo motivo que `coup_log_offset_democracy` (estado tipico medido
    #: bajo `dictatorship`: stability 24,2; confidence 0,0; tension 66,6;
    #: inflacion 8,1; crecimiento 1,3).
    exit_log_offset: float = -0.471

    # -- destino de la salida (ADR 015 secc. 3.4) -----------------------
    #: Punto medio (meses) de la logistica que decide si el regimen de facto
    #: entrega el poder a `restricted_democracy` (corto) o a `democracy`
    #: (largo). 34 = punto medio de la separacion PERFECTA observada en las
    #: 6 salidas reales (17/19/32 -> restringida; 36/83/93 -> plena).
    #: ADVERTENCIA: separacion perfecta sobre n=6, no es un resultado
    #: estadistico (ver ADR 015 secc. 3.4).
    restricted_duration_midpoint: float = 34.0
    #: Suavizado (meses) de esa logistica. ELEGIDO A MANO, no ajustado: la
    #: MLE de una logistica perfectamente separada diverge (escalon).
    #: `-> infinito` recupera el 50/50 constante que darian los 3/6 crudos.
    restricted_duration_smoothing: float = 8.0

    # -- transiciones que los datos NO sostienen (ADR 015 secc. 3.5) ----
    #: Probabilidad mensual de pasar de `democracy` a `restricted_democracy`
    #: sin golpe. 0,0: ocurrio UNA vez en 1008 meses (1948 -> 1949), lo que
    #: no sostiene una tasa. Campo (y no constante) para que calibracion
    #: pueda revisarlo.
    democracy_to_restricted_monthly: float = 0.0
    #: Probabilidad mensual de liberalizar (`restricted_democracy` ->
    #: `democracy`). 0,0: NUNCA ocurrio en la serie -- los cuatro periodos
    #: de democracia restringida terminaron los cuatro en golpe.
    restricted_to_democracy_monthly: float = 0.0

    # -- guardas numericas ----------------------------------------------
    #: Piso del multiplicador `exp(offset + sum(beta*z))`.
    min_multiplier: float = 0.01
    #: Techo del multiplicador (el motor puede llevar `social_tension` a 100
    #: bajo represion; sin techo el hazard se dispararia).
    max_multiplier: float = 5.0
    #: Techo de la probabilidad mensual de CUALQUIER transicion por hazard.
    max_monthly_hazard: float = 0.5


#: Instancia por defecto (ADR 015 secc. 3): la que usa el flag si nadie pasa
#: coeficientes propios.
DEFAULT_REGIME_TRANSITION_COEFFICIENTS = RegimeTransitionCoefficients()


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else (hi if value > hi else value)


def _covariates(world: WorldState, repression: float) -> dict[str, float]:
    """Covariables centradas del estado (ADR 015 secc. 2(c)): 0 == estado
    "neutro" de Aurora (50/50/50, inflacion 0, crecimiento 0) y
    `repression` centrada en el nivel de `dictatorship`."""
    return {
        "stability": (world.political_stability - 50.0) / 50.0,
        "confidence": (world.institutional_confidence - 50.0) / 50.0,
        "tension": (world.social_tension - 50.0) / 50.0,
        "inflation": _clamp(world.inflation, -5.0, 50.0) / 10.0,
        "growth": _clamp(world.gdp_growth, -20.0, 20.0) / 10.0,
        "repression": repression - 0.85,
    }


def _multiplier(log_linear: float, coeffs: RegimeTransitionCoefficients) -> float:
    return _clamp(math.exp(log_linear), coeffs.min_multiplier, coeffs.max_multiplier)


def weibull_month_hazard(
    months_in_mode: int,
    scale: float,
    shape: float,
    multiplier: float,
    cap: float,
) -> float:
    """Probabilidad de que la transicion ocurra DURANTE este mes, dado que
    no ocurrio antes (ADR 015 secc. 2(c)).

    Version discreta exacta del Weibull: `1 - exp(-(H(t+1) - H(t)) * m)` con
    `H(t) = (t/scale)**shape`. Usar la diferencia del hazard ACUMULADO (y no
    la densidad instantanea) es lo que hace que la forma `shape != 1` de
    verdad dependa de la duracion sin depender del paso de tiempo.
    `months_in_mode` es la cantidad de meses COMPLETOS ya pasados en el modo,
    asi que el mes que se esta por correr cubre `[t, t+1]`.
    """
    if scale <= 0.0 or shape <= 0.0 or multiplier <= 0.0:
        return 0.0
    t = max(0, months_in_mode)
    delta = ((t + 1) / scale) ** shape - (t / scale) ** shape
    if delta <= 0.0:
        return 0.0
    return min(cap, 1.0 - math.exp(-delta * multiplier))


def coup_hazard(
    mode: str,
    world: WorldState,
    months_in_mode: int,
    coeffs: RegimeTransitionCoefficients,
) -> float:
    """Riesgo mensual de golpe desde `democracy` o `restricted_democracy`
    (ADR 015 secc. 2(d)). Las dos comparten covariables y difieren solo en
    la tasa base: la democracia restringida tiene 3,7 veces el riesgo de la
    plena (0,01389 vs. 0,00379 mensual, secc. 3.2)."""
    z = _covariates(world, REPRESSION_BY_MODE.get(mode, 0.0))
    offset = (
        coeffs.coup_log_offset_restricted
        if mode == RESTRICTED_DEMOCRACY
        else coeffs.coup_log_offset_democracy
    )
    log_linear = (
        offset
        + coeffs.coup_beta_stability * z["stability"]
        + coeffs.coup_beta_confidence * z["confidence"]
        + coeffs.coup_beta_tension * z["tension"]
        + coeffs.coup_beta_inflation * z["inflation"]
        + coeffs.coup_beta_growth * z["growth"]
    )
    if mode == RESTRICTED_DEMOCRACY:
        scale, shape = coeffs.coup_restricted_scale, coeffs.coup_restricted_shape
    else:
        scale, shape = coeffs.coup_democracy_scale, coeffs.coup_democracy_shape
    return weibull_month_hazard(
        months_in_mode, scale, shape, _multiplier(log_linear, coeffs), coeffs.max_monthly_hazard
    )


def dictatorship_exit_hazard(
    world: WorldState,
    months_in_mode: int,
    coeffs: RegimeTransitionCoefficients,
) -> float:
    """Riesgo mensual de que la dictadura pase a `transition` (ADR 015
    secc. 2(d)). Reemplaza el umbral duro `social_tension > 70` de ADR 011
    secc. 3 por un hazard con dependencia de la duracion."""
    z = _covariates(world, REPRESSION_BY_MODE["dictatorship"])
    log_linear = (
        coeffs.exit_log_offset
        + coeffs.exit_beta_tension * z["tension"]
        + coeffs.exit_beta_repression * z["repression"]
        + coeffs.exit_beta_inflation * z["inflation"]
        + coeffs.exit_beta_growth * z["growth"]
        + coeffs.exit_beta_confidence * z["confidence"]
    )
    return weibull_month_hazard(
        months_in_mode,
        coeffs.dictatorship_exit_scale,
        coeffs.dictatorship_exit_shape,
        _multiplier(log_linear, coeffs),
        coeffs.max_monthly_hazard,
    )


def handover_hazard(months_in_mode: int, coeffs: RegimeTransitionCoefficients) -> float:
    """Riesgo mensual de que el traspaso (`transition`) se complete (ADR 015
    secc. 3.2). Sin covariables: los seis traspasos reales duraron entre 1 y
    3 meses y no hay variacion que explicar."""
    return weibull_month_hazard(
        months_in_mode,
        coeffs.handover_scale,
        coeffs.handover_shape,
        1.0,
        coeffs.max_monthly_hazard,
    )


def restricted_on_exit_probability(
    de_facto_months: int, coeffs: RegimeTransitionCoefficients
) -> float:
    """Probabilidad de que el regimen de facto entregue el poder a
    `restricted_democracy` (y no a `democracy`), como logistica DECRECIENTE
    en la duracion total del regimen de facto (ADR 015 secc. 3.4).

    Las 6 salidas reales se separan perfectamente por duracion (17/19/32 ->
    restringida; 36/83/93 -> plena). Es una separacion perfecta sobre SEIS
    observaciones: una regularidad descriptiva con una historia detras (un
    regimen corto entrega en sus propios terminos; uno largo llega agotado),
    NO un resultado estadistico. Ver la advertencia del ADR."""
    smoothing = coeffs.restricted_duration_smoothing
    if smoothing <= 0.0:
        return 1.0 if de_facto_months < coeffs.restricted_duration_midpoint else 0.0
    exponent = (de_facto_months - coeffs.restricted_duration_midpoint) / smoothing
    if exponent > 700.0:  # evita OverflowError en math.exp
        return 0.0
    return 1.0 / (1.0 + math.exp(exponent))


def step_regime(
    state: RegimeState,
    world: WorldState,
    rng: random.Random,
    forced_coup: bool,
    coup_propensity: float,
    transition_coefficients: RegimeTransitionCoefficients | None = None,
) -> RegimeStepResult:
    """Avanza `state` un mes (lo muta) y devuelve el resultado del mes.

    `forced_coup`: hay un evento `coup` en `politics/events.csv` para este
    mes (calendario). `coup_propensity`: probabilidad mensual de golpe
    endogeno cuando `political_stability < 20` e `institutional_confidence <
    30` (ADR 011 secc. 3); 0.0 con `--regime-mode democracy` o fuera de una
    era con golpes historicos (test de la seccion 9, item 4: "con propension
    0, nunca").

    `transition_coefficients` (ADR 015, `features.regime_endogenous_
    transitions`): `None` (el default) = comportamiento EXACTO de ADR 011,
    sin consumir un solo valor extra del RNG. Con coeficientes, corre el
    modelo de riesgo mensual de `_step_regime_endogenous` en su lugar.
    """
    if transition_coefficients is not None:
        return _step_regime_endogenous(
            state, world, rng, forced_coup, coup_propensity, transition_coefficients
        )

    event: str | None = None
    forced_election = False
    mode = state.mode

    if mode == "democracy":
        endogenous = (
            coup_propensity > 0.0
            and world.political_stability < COUP_STABILITY_THRESHOLD
            and world.institutional_confidence < COUP_CONFIDENCE_THRESHOLD
            and rng.random() < coup_propensity
        )
        if forced_coup or endogenous:
            mode = "coup"
            event = "coup"
    elif mode == "coup":
        # Dura exactamente 1 mes (ADR 011 secc. 3): el mes siguiente a la
        # activacion pasa a `dictatorship` sin condicion adicional.
        mode = "dictatorship"
        event = "regime_to_dictatorship"
    elif mode == "dictatorship":
        if world.social_tension > DICTATORSHIP_TENSION_THRESHOLD:
            mode = "transition"
            event = "regime_transition"
    elif mode == "transition":
        if state.months_in_mode >= TRANSITION_MAX_MONTHS:
            mode = "democracy"
            event = "regime_democracy_restored"
            forced_election = True

    if mode == state.mode:
        state.months_in_mode += 1
    else:
        state.months_in_mode = 0
    state.mode = mode

    return RegimeStepResult(
        mode=mode,
        repression=REPRESSION_BY_MODE[mode],
        event=event,
        forced_next_election=forced_election,
    )


def _step_regime_endogenous(
    state: RegimeState,
    world: WorldState,
    rng: random.Random,
    forced_coup: bool,
    coup_propensity: float,
    coeffs: RegimeTransitionCoefficients,
) -> RegimeStepResult:
    """Un mes del modelo de riesgo de ADR 015 (solo con el flag prendido).

    Diferencias con el camino de ADR 011, todas documentadas en el ADR 015:

    * `democracy`/`restricted_democracy` -> `coup` por hazard Weibull con
      covariables, en vez de por el gate `stability < 20 and confidence <
      30 and rng < coup_propensity`. `coup_propensity == 0.0` (lo que
      produce `--regime-mode democracy`) sigue APAGANDO el golpe endogeno
      por completo: se conserva la garantia de ADR 011 secc. 9 item 4.
    * `dictatorship` -> `transition` por hazard con dependencia de la
      duracion, en vez del umbral `social_tension > 70`.
    * `transition` -> gobierno civil por hazard de traspaso (1-4 meses),
      con `TRANSITION_MAX_MONTHS` todavia como tope duro; el destino
      (`democracy` o `restricted_democracy`) se sortea segun la duracion
      total del regimen de facto.
    * Un golpe FORZADO del calendario sigue teniendo prioridad sobre todo
      esto (en el backtest nunca hay: ver ADR 014, "Desviacion deliberada
      del calendario").

    Sorteos: se consumen SIEMPRE 2 valores de `rng` por mes (0 en `coup`,
    que es determinista), pasen o no las transiciones y valgan lo que valgan
    los coeficientes -- asi dos vectores de calibracion distintos ven la
    misma secuencia de shocks debajo.
    """
    event: str | None = None
    forced_election = False
    mode = state.mode
    de_facto = state.de_facto_months

    if mode in ("democracy", RESTRICTED_DEMOCRACY):
        u_coup = rng.random()
        u_degrade = rng.random()
        endogenous = coup_propensity > 0.0 and u_coup < coup_hazard(
            mode, world, state.months_in_mode, coeffs
        )
        if forced_coup or endogenous:
            mode = "coup"
            event = "coup"
        elif mode == "democracy" and u_degrade < coeffs.democracy_to_restricted_monthly:
            mode = RESTRICTED_DEMOCRACY
            event = "regime_restricted"
        elif mode == RESTRICTED_DEMOCRACY and u_degrade < coeffs.restricted_to_democracy_monthly:
            mode = "democracy"
            event = "regime_democracy_restored"
    elif mode == "coup":
        # Dura exactamente 1 mes, igual que en ADR 011 secc. 3.
        mode = "dictatorship"
        event = "regime_to_dictatorship"
    elif mode == "dictatorship":
        u_exit = rng.random()
        rng.random()  # reservado (ver docstring: el consumo no depende de los coeficientes)
        if u_exit < dictatorship_exit_hazard(world, state.months_in_mode, coeffs):
            mode = "transition"
            event = "regime_transition"
    elif mode == "transition":
        u_done = rng.random()
        u_dest = rng.random()
        done = u_done < handover_hazard(state.months_in_mode, coeffs) or (
            state.months_in_mode >= TRANSITION_MAX_MONTHS
        )
        if done:
            to_restricted = u_dest < restricted_on_exit_probability(de_facto, coeffs)
            mode = RESTRICTED_DEMOCRACY if to_restricted else "democracy"
            event = "regime_restricted" if to_restricted else "regime_democracy_restored"
            forced_election = True

    if mode in ("coup", "dictatorship", "transition"):
        state.de_facto_months = de_facto + 1
    else:
        state.de_facto_months = 0

    if mode == state.mode:
        state.months_in_mode += 1
    else:
        state.months_in_mode = 0
    state.mode = mode

    return RegimeStepResult(
        mode=mode,
        repression=REPRESSION_BY_MODE[mode],
        event=event,
        forced_next_election=forced_election,
    )


def regime_effects_on_state(state: WorldState, repression: float) -> WorldState:
    """Aplica `repression` a `protest_level`/`social_tension`/
    `institutional_confidence` (ADR 011 secc. 3), antes de correr el mes
    (mismo lugar en el orden de turno que un shock: ver `engine/
    simulation.py::run`). `repression == 0` devuelve `state` sin tocar
    (evita un `model_copy` de mas cuando el regimen esta en `democracy`)."""
    if repression <= 0.0:
        return state
    return state.model_copy(
        update={
            "protest_level": state.protest_level + REPRESSION_PROTEST_COEF * repression,
            "social_tension": state.social_tension + REPRESSION_TENSION_COEF * repression,
            "institutional_confidence": (
                state.institutional_confidence + REPRESSION_CONFIDENCE_COEF * repression
            ),
        }
    )


def elections_allowed(mode: str) -> bool:
    """`democracy`/`transition` permiten eleccion programada; `coup`/
    `dictatorship` la suspenden (ADR 011 secc. 3).

    `restricted_democracy` (ADR 015) TAMBIEN permite eleccion: 1931, 1937 y
    1963 fueron elecciones reales, con fraude o proscripcion pero
    celebradas. Lo que distingue a ese modo de `democracy` en el motor es
    `repression > 0` y un riesgo de golpe 3,7 veces mayor, no la ausencia
    de comicios."""
    return mode in ("democracy", "transition", RESTRICTED_DEMOCRACY)


def congress_active(mode: str) -> bool:
    """`democracy`/`transition` tienen Congreso; `coup`/`dictatorship` lo
    tienen disuelto (ADR 011 secc. 3). `restricted_democracy` (ADR 015) lo
    tiene activo, por el mismo motivo que `elections_allowed`."""
    return mode in ("democracy", "transition", RESTRICTED_DEMOCRACY)


# ---------------------------------------------------------------------------
# Calendario: golpes forzados (politics/events.csv) + propension por era
# (politics/regimes.csv, frecuencia observada de golpes por decada).
# ---------------------------------------------------------------------------


@dataclass
class RegimeCalendar:
    """Calendario de golpes forzados y propension endogena por mes de la
    corrida (ADR 011 secc. 3), ya resuelto contra el `--start`/`months` de
    esta corrida (indices de mes de la corrida, no fechas de calendario)."""

    forced_coup_months: set[int] = field(default_factory=set)
    #: mes de la corrida -> propension mensual de golpe endogeno.
    coup_propensity: dict[int, float] = field(default_factory=dict)
    #: ADR 015 (`features.regime_endogenous_transitions`): `False` (default)
    #: = maquina de estados de ADR 011 tal cual. El flag viaja aca adentro y
    #: no como parametro nuevo de `engine/simulation.py::run()`, que ya
    #: tiene 17 opcionales (ver Notas de implementacion del ADR 015).
    endogenous_transitions: bool = False
    #: Coeficientes del modelo de riesgo. `None` con el flag prendido =
    #: `DEFAULT_REGIME_TRANSITION_COEFFICIENTS`.
    transition_coefficients: RegimeTransitionCoefficients | None = None
    #: Modo del regimen en el mes 1 de la corrida. Default `"democracy"` =
    #: exactamente lo que hacia `RegimeState()` antes de ADR 015.
    initial_mode: str = "democracy"
    #: Meses ya transcurridos en `initial_mode` al arrancar la corrida (el
    #: hazard depende de la duracion, asi que sembrar esto con el dato real
    #: es la mitad del mecanismo: ver ADR 015 secc. 2(a)).
    initial_months_in_mode: int = 0
    #: Meses ya transcurridos del REGIMEN DE FACTO en curso (0 si el modo
    #: inicial es civil), ver `RegimeState.de_facto_months`.
    initial_de_facto_months: int = 0

    def resolved_coefficients(self) -> RegimeTransitionCoefficients | None:
        """Coeficientes a pasarle a `step_regime` (`None` = camino de ADR
        011, sin tocar el RNG)."""
        if not self.endogenous_transitions:
            return None
        return self.transition_coefficients or DEFAULT_REGIME_TRANSITION_COEFFICIENTS

    def initial_regime_state(self) -> RegimeState:
        """`RegimeState` del mes 1. Con los defaults devuelve
        `RegimeState()`, identico a lo de siempre."""
        return RegimeState(
            mode=self.initial_mode,
            months_in_mode=self.initial_months_in_mode,
            de_facto_months=self.initial_de_facto_months,
        )


def _ym(date: str) -> tuple[int, int]:
    y, m = int(date[:4]), int(date[5:7])
    return y, m


#: Marcas de golpe FALLIDO en `title`/`notes` de `politics/events.csv` (P1,
#: A3: antes de esta correccion, un golpe fallido -- p.ej. los tres
#: alzamientos "carapintada" de 1987-1990 -- tambien movia `regime_mode` a
#: `coup` por 1 mes, exactamente igual que uno exitoso; ese era un bug, no
#: una simplificacion deliberada: el propio `notes` de esas filas dice
#: "FALLIDO" en mayusculas). Case-insensitive.
FAILED_COUP_MARKERS = ("fallido", "failed")


def _is_failed_coup_row(row: dict[str, str]) -> bool:
    haystack = f"{row.get('title', '')} {row.get('notes', '')}".lower()
    return any(marker in haystack for marker in FAILED_COUP_MARKERS)


def load_coup_dates(events_csv: Path) -> list[tuple[int, int]]:
    """`(year, month)` de cada fila `kind == "coup"` EXITOSA (P1, A3: un
    golpe fallido -- `title`/`notes` marcados "FALLIDO"/"fallido"/"failed",
    p.ej. los tres alzamientos "carapintada" de 1987-1990 -- no entra en el
    calendario de golpes: ver `load_failed_coup_dates` para esas filas, que
    se tratan como un shock de un mes en vez de un cambio de `regime_mode`)."""
    if not events_csv.exists():
        return []
    out = []
    with events_csv.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("kind") == "coup" and not _is_failed_coup_row(row):
                out.append(_ym(row["date"]))
    return out


def load_failed_coup_dates(events_csv: Path) -> list[tuple[int, int]]:
    """`(year, month)` de cada golpe FALLIDO de `politics/events.csv` (P1,
    A3): estos NO mueven `regime_mode` -- se traducen a un shock de 1 mes
    (`failed_coup` en `shocks.json`: `stability -5, institutional_confidence
    -3`) via `world/countries.py::historical_shocks_calendar`, que los suma
    al mismo `forced_shocks` que ya usa `--historical-shocks`."""
    if not events_csv.exists():
        return []
    out = []
    with events_csv.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("kind") == "coup" and _is_failed_coup_row(row):
                out.append(_ym(row["date"]))
    return out


def coup_propensity_by_decade(events_csv: Path) -> dict[int, float]:
    """Propension mensual de golpe por decada (ADR 011 secc. 3: "la
    propension es la frecuencia observada de golpes por decada"):
    (cantidad de golpes con `date` en la decada) / 120 meses."""
    dates = load_coup_dates(events_csv)
    counts: dict[int, int] = {}
    for y, _m in dates:
        decade = (y // 10) * 10
        counts[decade] = counts.get(decade, 0) + 1
    return {decade: n / 120.0 for decade, n in counts.items()}


#: Traduccion de los `regime_mode` de `politics/regimes.csv` a los modos del
#: motor (ADR 015 secc. 2(a)). `civil_war_or_state_building` (28 años, todos
#: <= 1861) se mapea a `dictatorship`: sin elecciones ni Congreso es el mas
#: cercano de los cinco. No afecta a ninguna ventana puntuada del backtest
#: (`regime` solo se puntua desde 1961, ADR 014).
REGIMES_CSV_TO_ENGINE_MODE: dict[str, str] = {
    "democracy": "democracy",
    "restricted_democracy": RESTRICTED_DEMOCRACY,
    "coup": "coup",
    "dictatorship": "dictatorship",
    "transition": "transition",
    "civil_war_or_state_building": "dictatorship",
}


def load_regimes_by_year(regimes_csv: Path) -> dict[int, str]:
    """`year -> regime_mode` de `politics/regimes.csv` (valores crudos del
    archivo, sin traducir a modos del motor)."""
    out: dict[int, str] = {}
    if not regimes_csv.exists():
        return out
    with regimes_csv.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            out[int(row["year"])] = row["regime_mode"]
    return out


def initial_regime_state(regimes_csv: Path, year: int, month: int) -> RegimeState:
    """Modo del motor y meses ya transcurridos en el, al mes `year-month`,
    segun el dato REAL de `politics/regimes.csv` (ADR 015 secc. 2(a)).

    `regimes.csv` es ANUAL, asi que `months_in_mode` se cuenta desde enero
    del primer año del bloque contiguo del mismo modo. Unica excepcion: un
    bloque `dictatorship` se extiende hacia atras sobre el año `coup` que lo
    precede -- si no, el Proceso "arrancaria" en 1977-01 en vez de 1976-01 y
    a una ventana de 1982-01 le faltarian 12 meses de edad del regimen,
    justo la variable de la que depende el hazard de salida.

    Sin dato para `year` devuelve `RegimeState()` (democracia, 0 meses):
    el mismo default de siempre."""
    by_year = load_regimes_by_year(regimes_csv)
    raw = by_year.get(year)
    if raw is None:
        return RegimeState()
    mode = REGIMES_CSV_TO_ENGINE_MODE.get(raw, "democracy")

    first_year = year
    while True:
        prev = by_year.get(first_year - 1)
        if prev is None:
            break
        prev_mode = REGIMES_CSV_TO_ENGINE_MODE.get(prev, "democracy")
        same = prev_mode == mode
        after_coup = mode == "dictatorship" and prev_mode == "coup"
        if not (same or after_coup):
            break
        first_year -= 1

    months_in_mode = (year - first_year) * 12 + (month - 1)
    de_facto = months_in_mode if mode in ("coup", "dictatorship", "transition") else 0
    if mode == "coup":
        # `coup` dura 1 mes en el motor: sembrarlo con meses acumulados no
        # tiene sentido (el paso siguiente lo lleva a `dictatorship` igual).
        months_in_mode = 0
    return RegimeState(mode=mode, months_in_mode=months_in_mode, de_facto_months=de_facto)


def build_regime_calendar(
    events_csv: Path,
    start_year: int,
    start_month: int,
    months: int,
    mode: str,
    endogenous_transitions: bool = False,
    transition_coefficients: RegimeTransitionCoefficients | None = None,
    regimes_csv: Path | None = None,
) -> RegimeCalendar:
    """`mode`: `"auto"` (calendario + propension real por decada) o
    `"democracy"` (siempre democracia: propension 0 y sin golpes forzados,
    equivalente a jugar en un pais sin historia de golpes -- test de la
    seccion 9, item 4).

    `endogenous_transitions` (ADR 015): prende el modelo de riesgo y, si hay
    `regimes_csv`, siembra el modo inicial con el dato real de `start_year`/
    `start_month`. Con `mode == "democracy"` el modo inicial NO se siembra
    (ese modo significa "este pais nunca sale de democracia")."""
    seed_state = (
        initial_regime_state(regimes_csv, start_year, start_month)
        if endogenous_transitions and regimes_csv is not None and mode != "democracy"
        else RegimeState()
    )
    cal = RegimeCalendar(
        endogenous_transitions=endogenous_transitions,
        transition_coefficients=transition_coefficients,
        initial_mode=seed_state.mode,
        initial_months_in_mode=seed_state.months_in_mode,
        initial_de_facto_months=seed_state.de_facto_months,
    )
    if mode == "democracy":
        return cal
    coup_dates = load_coup_dates(events_csv)
    propensity_by_decade = coup_propensity_by_decade(events_csv)
    for y, m in coup_dates:
        idx = (y - start_year) * 12 + (m - start_month) + 1
        if 1 <= idx <= months:
            cal.forced_coup_months.add(idx)
    for month_idx in range(1, months + 1):
        total_months = (start_month - 1) + (month_idx - 1)
        y = start_year + total_months // 12
        decade = (y // 10) * 10
        cal.coup_propensity[month_idx] = propensity_by_decade.get(decade, 0.0)
    return cal
