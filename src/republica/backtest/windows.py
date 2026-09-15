"""Ventanas del backtest secuencial (ADR 014 secc. 1).

Un `Window` es un origen `t0` ("YYYY-MM") mas un horizonte `h` (meses).
`generate_windows` arma la grilla completa (107 origenes x 3 horizontes,
ADR 014 secc. 1) resolviendo, para cada una, lo que NO depende de la
corrida en si (para eso ver `features.py`/`runner.py`): frecuencia
(mensual vs anual interpolado), epoca de partidos, regimen y `fx_regime`
reales en `t0`, y el plan de shocks forzados -- solo EXOGENOS.

Deviacion documentada respecto del texto literal del ADR (seccion 1): el
ADR distingue "1916-1943 anual" de "1943-1960 mensual interpolado", pero
`calibration/initial_states.py::initial_state_for` (la unica pieza del
repo que sabe construir un estado inicial real para un mes cualquiera)
cubre `MIN_YEAR=1961` en adelante -- no existe ningun mecanismo de
interpolacion MENSUAL para 1943-1960 en el repo (el modo anual del ADR 011
es la unica alternativa construida). Se usa el modo anual (ADR 011 secc.
6, `frequency="annual_interpolated"`) para TODO `t0` con año < 1961, no
solo hasta 1943; documentado tambien en el ADR (seccion "Notas de
implementacion").
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from republica.world.countries import country_pack_dir
from republica.world.eras import select_era

#: Horizontes del ADR 014 secc. 1.
DEFAULT_HORIZONS: tuple[int, ...] = (12, 24, 48)

#: Primer y ultimo origen `t0` (ADR 014 secc. 1: "cada 12 meses desde
#: 1916-01 hasta 2022-12" -- con paso de 12 meses desde 1916-01 el ultimo
#: origen cae en 2022-01, no en 2022-12; 2022-12 es la cota, no un origen
#: literal. 2022-1916+1 = 107 origenes, el numero que da el ADR).
FIRST_ORIGIN_YEAR = 1916
LAST_ORIGIN_YEAR = 2022

#: `calibration/initial_states.py::MIN_YEAR`: primer año con estado inicial
#: real MENSUAL. `t0` con año anterior corre en modo anual (ADR 011 secc.
#: 6), ver docstring del modulo.
MONTHLY_MIN_YEAR = 1961

#: Shocks que ADR 014 secc. 1 permite forzar ("solo exogenos: commodities,
#: mundo, guerra, pandemia, sequia"), como lista EXPLICITA de `shock_id` de
#: `data/countries/argentina/politics/shocks_calendar.csv` (unico shock_id
#: por fila de ese archivo, verificado: `banking_crisis, commodity_boom,
#: currency_run, drought, epidemic, hyperinflation_regime, imf_program,
#: international_crisis, sovereign_default, war`). `currency_run` e
#: `imf_program` quedan AFUERA aposta: son respuesta financiera/de politica
#: a una crisis, no una exogena pura en el sentido del ADR (commodities/
#: mundo/guerra/pandemia/sequia) -- forzarlos regalaria justamente la
#: dinamica financiera que golpe/hiperinflacion/default/crisis bancaria
#: miden.
EXOGENOUS_ONLY: frozenset[str] = frozenset(
    {"drought", "epidemic", "international_crisis", "commodity_boom", "war"}
)

#: Shocks que el ADR 014 secc. 1 prohibe forzar explicitamente ("nunca
#: hiperinflacion, default, golpe ni crisis bancaria: eso es lo que hay que
#: predecir"). `coup` no es un `shock_id` de `shocks.json` (es un evento de
#: `world/regime.py`, no del catalogo de shocks) -- se incluye igual en
#: esta lista por completitud/documentacion; el test 4 (ADR 014 secc. 6)
#: verifica que ninguno de los cuatro aparezca jamas como forzado, lo cual
#: se cumple POR CONSTRUCCION al usar `EXOGENOUS_ONLY` como allow-list en
#: vez de excluir de una lista mas grande.
FORBIDDEN_SHOCK_IDS: frozenset[str] = frozenset(
    {"hyperinflation_regime", "sovereign_default", "banking_crisis", "coup"}
)

#: Objetivos endogenos que ADR 014 secc. 1 prohibe forzar via
#: `regime_calendar` (golpe): ver `runner.py::backtest_regime_calendar`,
#: que arma un `RegimeCalendar` con `forced_coup_months` vacio -- a
#: diferencia de `world.countries.load_country_pack(..., regime_mode="auto")`
#: (usado por `republica run`/A4), que SI fuerza los golpes reales de
#: `politics/events.csv`. Sin este cambio el objetivo "golpe" del backtest
#: seria tautologico (el modelo "acertaria" un golpe que el propio
#: calendario le forzo).
__all__ = [
    "DEFAULT_HORIZONS",
    "EXOGENOUS_ONLY",
    "FORBIDDEN_SHOCK_IDS",
    "MONTHLY_MIN_YEAR",
    "ForcedShockPlan",
    "Window",
    "generate_windows",
    "resolve_exogenous_shocks",
    "add_months",
    "month_date",
]


def add_months(y: int, m: int, k: int) -> tuple[int, int]:
    total = (y * 12 + (m - 1)) + k
    return total // 12, total % 12 + 1


def month_date(t0: str, month_index: int) -> str:
    """Fecha del registro `month_index` de una corrida que arranca en
    `t0` (mismo criterio que `engine/simulation.py::_format_date` /
    `validation/argentina.py::month_date`: `month_index=1` == `t0`)."""
    y, m = int(t0[:4]), int(t0[5:7])
    ty, tm = add_months(y, m, month_index - 1)
    return f"{ty:04d}-{tm:02d}"


def target_date(t0: str, h: int) -> str:
    """Fecha calendario "`t0` + `h` meses" (`calibration/objective.py`
    convention: el registro con `month_index == h` de una corrida de `h`
    meses es lo que se lee como "el estado a horizonte `h`", aunque
    `month_date(t0, h)` sea literalmente `t0 + (h-1)` meses -- la misma
    convencion off-by-one que ya usa todo el resto del repo
    (`calibration/objective.py::score_start_month`), no una nueva)."""
    y, m = int(t0[:4]), int(t0[5:7])
    ty, tm = add_months(y, m, h)
    return f"{ty:04d}-{tm:02d}"


@dataclass(frozen=True)
class ForcedShockPlan:
    """Shocks EXOGENOS forzados dentro de una ventana, ya resueltos contra
    `politics/shocks_calendar.csv` (mismo patron que
    `validation/argentina.py::ForcedShockPlan`, mas simple: aca no hay
    `ShockRequest` por prueba, se toma TODO lo que haya en el calendario
    dentro de `[t0, t0+h]` cuyo `shock_id` este en `EXOGENOUS_ONLY`)."""

    forced: dict[int, list[str]] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.rows)

    @property
    def magnitude_sum(self) -> float:
        total = 0.0
        for row in self.rows:
            try:
                total += float(row.get("magnitude") or 0.0)
            except ValueError:
                continue
        return total


def resolve_exogenous_shocks(pack_dir: Path, t0: str, h: int) -> ForcedShockPlan:
    """`{month_index: [shock_id]}` para `run(forced_shocks=...)` (modo
    mensual) mas la traza de filas aplicadas, restringido a
    `EXOGENOUS_ONLY` (ADR 014 secc. 1). `month_index` sigue el criterio de
    `world/countries.py::historical_shocks_calendar` (mes 1 == `t0`)."""
    path = pack_dir / "politics" / "shocks_calendar.csv"
    forced: dict[int, list[str]] = {}
    rows: list[dict] = []
    if not path.exists():
        return ForcedShockPlan()
    y0, m0 = int(t0[:4]), int(t0[5:7])
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            shock_id = row["shock_id"]
            if shock_id not in EXOGENOUS_ONLY:
                continue
            y, m = int(row["date"][:4]), int(row["date"][5:7])
            idx = (y - y0) * 12 + (m - m0) + 1
            if 1 <= idx <= h:
                forced.setdefault(idx, []).append(shock_id)
                rows.append(row)
    return ForcedShockPlan(forced=forced, rows=rows)


def resolve_exogenous_shocks_annual(pack_dir: Path, t0_year: int, years: int) -> ForcedShockPlan:
    """Idem `resolve_exogenous_shocks` pero para el modo anual
    (`world/annual.py::run_annual`, que indexa `forced_shocks` por turno
    ANUAL: 1 = primer año de la corrida), ADR 011 secc. 6 ("shocks forzados
    ... tratando cada uno como si durara exactamente 1 turno-año")."""
    path = pack_dir / "politics" / "shocks_calendar.csv"
    forced: dict[int, list[str]] = {}
    rows: list[dict] = []
    if not path.exists():
        return ForcedShockPlan()
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            shock_id = row["shock_id"]
            if shock_id not in EXOGENOUS_ONLY:
                continue
            y = int(row["date"][:4])
            idx = (y - t0_year) + 1
            if 1 <= idx <= years:
                forced.setdefault(idx, []).append(shock_id)
                rows.append(row)
    return ForcedShockPlan(forced=forced, rows=rows)


@dataclass(frozen=True)
class Window:
    """Todo lo que describe una ventana `(t0, h)` que NO depende de correr
    ninguna simulacion (ver `features.py` para lo que si necesita el
    resultado de una corrida, y `runner.py` para la corrida en si)."""

    t0: str
    h: int
    t_target: str
    frequency: str  # "monthly" | "annual_interpolated"
    era_id: str | None
    forced_plan: ForcedShockPlan

    @property
    def key(self) -> str:
        return f"{self.t0}_h{self.h}"


def generate_windows(
    from_year: int = FIRST_ORIGIN_YEAR,
    to_year: int = LAST_ORIGIN_YEAR,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    country_id: str = "argentina",
) -> list[Window]:
    """Grilla completa `(t0, h)` (ADR 014 secc. 1): un origen `t0="YYYY-01"`
    por año en `[from_year, to_year]`, cruzado con `horizons`."""
    pack_dir = country_pack_dir(country_id)
    windows: list[Window] = []
    for year in range(from_year, to_year + 1):
        t0 = f"{year:04d}-01"
        frequency = "monthly" if year >= MONTHLY_MIN_YEAR else "annual_interpolated"
        era = select_era(country_id, t0)
        for h in horizons:
            plan = (
                resolve_exogenous_shocks(pack_dir, t0, h)
                if frequency == "monthly"
                else resolve_exogenous_shocks_annual(pack_dir, year, h // 12)
            )
            windows.append(
                Window(
                    t0=t0,
                    h=h,
                    t_target=target_date(t0, h),
                    frequency=frequency,
                    era_id=era.id if era is not None else None,
                    forced_plan=plan,
                )
            )
    return windows
