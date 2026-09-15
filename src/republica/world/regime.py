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
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

from republica.world.state import WorldState

REGIME_MODES = ("democracy", "coup", "dictatorship", "transition")

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
}


@dataclass
class RegimeState:
    """Estado del regimen, persistente mes a mes (mutado por `step_regime`)."""

    mode: str = "democracy"
    months_in_mode: int = 0


@dataclass
class RegimeStepResult:
    mode: str
    repression: float
    event: str | None
    forced_next_election: bool = False


def step_regime(
    state: RegimeState,
    world: WorldState,
    rng: random.Random,
    forced_coup: bool,
    coup_propensity: float,
) -> RegimeStepResult:
    """Avanza `state` un mes (lo muta) y devuelve el resultado del mes.

    `forced_coup`: hay un evento `coup` en `politics/events.csv` para este
    mes (calendario). `coup_propensity`: probabilidad mensual de golpe
    endogeno cuando `political_stability < 20` e `institutional_confidence <
    30` (ADR 011 secc. 3); 0.0 con `--regime-mode democracy` o fuera de una
    era con golpes historicos (test de la seccion 9, item 4: "con propension
    0, nunca").
    """
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
    `dictatorship` la suspenden (ADR 011 secc. 3)."""
    return mode in ("democracy", "transition")


def congress_active(mode: str) -> bool:
    """`democracy`/`transition` tienen Congreso; `coup`/`dictatorship` lo
    tienen disuelto (ADR 011 secc. 3)."""
    return mode in ("democracy", "transition")


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


def _ym(date: str) -> tuple[int, int]:
    y, m = int(date[:4]), int(date[5:7])
    return y, m


def load_coup_dates(events_csv: Path) -> list[tuple[int, int]]:
    """`(year, month)` de cada fila `kind == "coup"` de `politics/events.csv`
    (fallidos incluidos: `notes` los marca "FALLIDO" pero `world/regime.py`
    no distingue -- ver Notas de implementacion del ADR 011: un golpe
    fallido tambien mueve `regime_mode` a `coup` por 1 mes en este modelo
    simplificado, ya que el motor no tiene una nocion de "intento" separada
    de "ocurrencia")."""
    if not events_csv.exists():
        return []
    out = []
    with events_csv.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("kind") == "coup":
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


def build_regime_calendar(
    events_csv: Path,
    start_year: int,
    start_month: int,
    months: int,
    mode: str,
) -> RegimeCalendar:
    """`mode`: `"auto"` (calendario + propension real por decada) o
    `"democracy"` (siempre democracia: propension 0 y sin golpes forzados,
    equivalente a jugar en un pais sin historia de golpes -- test de la
    seccion 9, item 4)."""
    cal = RegimeCalendar()
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
