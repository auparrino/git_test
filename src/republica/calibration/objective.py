"""Funcion objetivo de la calibracion (A3, ADR 011 secc. 7 punto 2).

Para cada mes de arranque `t` de la ventana (`train`/`holdout`, stride
configurable), simula `h=12` meses con el estado inicial real de `t`
(`calibration/initial_states.py::flat_initial_state`) y los shocks/exogenas
reales de esos 12 meses (`--historical-shocks --historical-exogenous`,
`world/countries.py`), con reglas (`default_brain="rules"`, sin LLM) y todas
las features de Aurora prendidas (actores/Congreso/cohortes/medios/
elecciones) mas `regime`/`historical_shocks`/`bimonetary` (ADR 011 secc.
7). Mide, a los horizontes `1/3/6/12` y SOLO donde la serie real tiene dato
(mascara `NaN`), el RMSE normalizado (por el desvio de la serie real
completa) de `inflation` (mensual), `gdp_growth` (EMAE cuando hay, si no PBI
anual interpolado), `unemployment`, `exchange_rate` (cambio LOGARITMICO del
oficial, no nivel: `world/state.py` lo modela como indice sin unidad, ver
ADR 011 Notas de implementacion de A2) y `reserves`; mas un termino de
regimen (acierto binario `democracy`/no, contra `politics/regimes.csv`) y
uno de elecciones (acierto de reelegido/derrotado, `ElectionResult.
outcome_type`, contra `REAL_ELECTION_OUTCOMES` mas abajo, cuando cae una
eleccion dentro del horizonte) y una regularizacion L2 hacia los
coeficientes de Aurora (`lambda_reg`, configurable).

`persistence`/`aurora_baseline` (tarea A3 punto 2, "las dos baselines")
corren por el MISMO camino de codigo (`evaluate_candidate` con
`persistence=True` o con los coeficientes de Aurora sin modificar) para que
la comparacion train/holdout de `report.py` sea apples-to-apples."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from republica.calibration.initial_states import (
    flat_initial_state,
    interpolate_annual,
    load_series,
)
from republica.calibration.parameters import (
    Parameter,
    bimonetary_from_vector,
    coefficients_from_vector,
    macro_from_vector,
)
from republica.engine.simulation import run
from republica.world.bimonetary import BimonetaryCoefficients
from republica.world.config import Coefficients
from republica.world.countries import (
    failed_coup_shock_months,
    historical_exogenous_series,
    historical_shocks_calendar,
    load_country_pack,
)
from republica.world.economy import MacroCoefficients
from republica.world.regime import build_regime_calendar
from republica.world.state import WorldState

HORIZONS = (1, 3, 6, 12)
MAX_HORIZON = 12
VARIABLES = ("inflation", "gdp_growth", "unemployment", "exchange_rate", "reserves")

#: Exponente de la perdida "cola pesada" (A5, ADR 012 secc. 6): error
#: NORMALIZADO (por el desvio de la serie real, mismo `sigma` que la RMSE)
#: elevado a `HEAVY_TAIL_POWER` y agregado (media ponderada) SIN volver a
#: tomar raiz -- literal del ADR ("elevado a 1.5 antes de agregar"), a
#: proposito SIN el `**(1/1.5)` que convertiria esto en una p-norma L1.5:
#: una p-norma con `p=1.5 < 2` es MENOS sensible a un outlier que la RMSE
#: (`p=2`, implicito antes del `sqrt`) -- exactamente lo CONTRARIO de "que
#: los episodios extremos pesen mas" (ver la cuenta en el docstring de
#: `_weighted_heavy`). Sin la raiz final, un error normalizado `|e| > 1`
#: (una desviacion mayor a un sigma: el caso "episodio extremo") aporta
#: `|e|^1.5 > |e|` (mas que en una metrica ya escalada de vuelta a la
#: unidad original como la RMSE), mientras que un error tipico `|e| < 1`
#: aporta `|e|^1.5 < |e|` (menos) -- asi que la cola pesa mas y el cuerpo
#: pesa menos, en las unidades EN QUE SE AGREGA. No queda en las mismas
#: unidades que la RMSE (por eso el reporte muestra las dos por separado,
#: no una razon entre ellas).
HEAVY_TAIL_POWER = 1.5

#: Peso de un mes de arranque cuyas series MENSUALES estan interpoladas de
#: series ANUALES (A5, ADR 012 secc. 6): `inflation_cpi_monthly.csv` (la
#: serie mensual real mas relevante del objetivo) arranca en 1997-02
#: (`calibration/initial_states.py` interpola linealmente el IPC ANUAL
#: antes de esa fecha, ver `rule_inflation`) -- un mes de arranque anterior
#: a 1997 evalua su horizonte de 12 meses contra una mezcla de valores
#: mensuales reales (los meses de 1997 dentro del horizonte) e
#: interpolados (los de antes); se pondera el MES DE ARRANQUE entero (no
#: cada `(var, horizonte)` por separado, una simplificacion documentada:
#: distinguir mes a mes cual target especifico vino de una interpolacion
#: requeriria taggear la procedencia de cada punto de `RealData`, que hoy
#: no la guarda) a 0.5 en vez de 1.0.
PRE_1997_WEIGHT = 0.5
PRE_1997_WEIGHT_CUTOFF_YEAR = 1997


def start_month_weight(date: str) -> float:
    """Peso de un mes de arranque en el objetivo (A5, ADR 012 secc. 6): ver
    `PRE_1997_WEIGHT`."""
    y, _m = _ym(date)
    return PRE_1997_WEIGHT if y < PRE_1997_WEIGHT_CUTOFF_YEAR else 1.0


#: Resultado REAL de cada eleccion presidencial 1989-2019 ("reelected" =
#: la coalicion gobernante retuvo la presidencia, "defeated" = la perdio),
#: para el termino de elecciones del objetivo. Hecho publico, curado a mano
#: (PLAN_ARGENTINA.md #0.2): 2003 y 2007 se cuentan como continuidad de
#: coalicion (PJ/FPV) aunque el presidente saliente no se haya presentado
#: (Duhalde 2003, Nestor Kirchner 2007) -- una simplificacion declarada,
#: ver Notas de implementacion de A3.
REAL_ELECTION_OUTCOMES: dict[int, str] = {
    1989: "defeated",
    1995: "reelected",
    1999: "defeated",
    2003: "reelected",
    2007: "reelected",
    2011: "reelected",
    2015: "defeated",
    2019: "defeated",
}


def _ym(date: str) -> tuple[int, int]:
    y, m = date.split("-")
    return int(y), int(m)


def _add_months(y: int, m: int, k: int) -> tuple[int, int]:
    total = (y * 12 + (m - 1)) + k
    return total // 12, total % 12 + 1


def start_months(range_start: str, range_end: str, horizon: int, stride: int) -> list[str]:
    """Meses de arranque validos dentro de `[range_start, range_end]`, con
    paso `stride`, tales que `start + horizon` (el mes objetivo mas lejano)
    tambien cae dentro del rango: asi ningun mes de TRAIN necesita un dato
    real de HOLDOUT para puntuarse (protocolo de honestidad, ADR 011 secc.
    7 / tarea A3 punto 5: "el holdout se corre una vez, al final")."""
    y0, m0 = _ym(range_start)
    y1, m1 = _ym(range_end)
    out = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        ty, tm = _add_months(y, m, horizon)
        if (ty, tm) <= (y1, m1):
            out.append(f"{y:04d}-{m:02d}")
        y, m = _add_months(y, m, stride)
    return out


# ---------------------------------------------------------------------------
# Series reales (cacheadas por proceso: `RealData()` una vez por worker).
# ---------------------------------------------------------------------------


@dataclass
class RealData:
    inflation_monthly: dict[tuple[int, int], float] = field(default_factory=dict)
    #: A5b (ADR 012 secc. 6, fix del bug de `a5_macro`): `inflation_cpi_
    #: monthly.csv` arranca en 1997-02 (`PRE_1997_WEIGHT` ya asume que hay
    #: DATO antes de esa fecha, solo con menos peso) -- sin esto, el
    #: holdout ENTERO (`1983-12:1991-12`) quedaba sin NINGUN dato de
    #: inflacion, para los 4 brazos por igual (calibrado/persistencia/
    #: Aurora/`a3_main`), porque `value("inflation", ...)` solo miraba
    #: `inflation_monthly`. Filas `(year, month, value, source_id)` de
    #: `inflation_cpi_annual_linked.csv` (o `inflation_cpi_annual.csv` si
    #: la serie empalmada no existe -- mismo fallback que `calibration/
    #: initial_states.py::rule_inflation`), usadas SOLO cuando falta el
    #: mes exacto (`value()` abajo).
    inflation_annual_rows: list[tuple[int, int, float, str]] = field(default_factory=list)
    unemployment: dict[tuple[int, int], float] = field(default_factory=dict)
    reserves: dict[tuple[int, int], float] = field(default_factory=dict)
    fx_official: dict[tuple[int, int], float] = field(default_factory=dict)
    #: Cierre del pendiente "holdout sin tipo de cambio mensual antes de
    #: 1992" (PLAN_ARGENTINA secc. 7): `exchange_rate_official_monthly.csv`
    #: arranca en 1992-01, asi que `fx_log()` devolvia `None` en TODO el
    #: holdout `1983-12:1991-12` y el termino `exchange_rate` del objetivo
    #: quedaba sin puntuar ahi. Filas `(year, month, value, source_id)` de
    #: `exchange_rate_annual_linked.csv` (WDI `PA.NUS.FCRF`, promedio anual
    #: en pesos convertibles, 1962+, SOURCES.md fuente 22), usadas SOLO
    #: cuando falta el mes exacto (`fx_level()` abajo), mismo patron que
    #: `inflation_annual_rows`.
    fx_annual_rows: list[tuple[int, int, float, str]] = field(default_factory=list)
    emae: dict[tuple[int, int], float] = field(default_factory=dict)
    gdp_pc_by_year: dict[int, float] = field(default_factory=dict)
    regimes_by_year: dict[int, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> RealData:
        def as_dict(name):
            return {(y, m): v for y, m, v, _sid in load_series(name)}

        gdp_pc_rows = load_series("gdp_per_capita_real")
        inflation_annual_rows = load_series("inflation_cpi_annual_linked") or load_series(
            "inflation_cpi_annual"
        )
        regimes = {}
        import csv

        from republica.calibration.initial_states import PACK_DIR

        regimes_csv = PACK_DIR / "politics" / "regimes.csv"
        if regimes_csv.exists():
            with regimes_csv.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    regimes[int(row["year"])] = row["regime_mode"]
        return cls(
            inflation_monthly=as_dict("inflation_cpi_monthly"),
            inflation_annual_rows=inflation_annual_rows,
            unemployment=as_dict("unemployment"),
            reserves=as_dict("reserves_monthly"),
            fx_official=as_dict("exchange_rate_official_monthly"),
            fx_annual_rows=load_series("exchange_rate_annual_linked"),
            emae=as_dict("emae_monthly"),
            gdp_pc_by_year=_annual_by_year_plain(gdp_pc_rows),
            regimes_by_year=regimes,
        )

    def gdp_growth(self, y: int, m: int) -> float | None:
        now = self.emae.get((y, m))
        prev = self.emae.get((y - 1, m))
        if now is not None and prev is not None and prev != 0:
            return (now / prev - 1.0) * 100.0
        v0 = self.gdp_pc_by_year.get(y)
        v1 = self.gdp_pc_by_year.get(y + 1)
        v_1 = self.gdp_pc_by_year.get(y - 1)
        if v0 is not None and v1 is not None:
            g_this = (v1 / v0 - 1.0) * 100.0
        elif v_1 is not None and v0 is not None:
            g_this = (v0 / v_1 - 1.0) * 100.0
        else:
            return None
        return g_this

    def inflation(self, y: int, m: int) -> float | None:
        """`inflation_cpi_monthly` (mes exacto) con fallback a la serie
        ANUAL interpolada linealmente y convertida a mensual (A5b, ADR 012
        secc. 6: mismo `interpolate_annual` + formula que `calibration/
        initial_states.py::rule_inflation`, reusado tal cual para que el
        objetivo y el estado inicial usen la MISMA regla de interpolacion).
        Sin esto, el holdout `1983-12:1991-12` (todo antes de 1997-02) no
        tenia NINGUN dato de inflacion para puntuar."""
        exact = self.inflation_monthly.get((y, m))
        if exact is not None:
            return exact
        hit = interpolate_annual(self.inflation_annual_rows, y, m)
        if hit is None:
            return None
        annual_pct, _note = hit
        return ((1.0 + annual_pct / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0

    def value(self, var: str, y: int, m: int) -> float | None:
        if var == "inflation":
            return self.inflation(y, m)
        if var == "unemployment":
            return self.unemployment.get((y, m))
        if var == "reserves":
            return self.reserves.get((y, m))
        if var == "gdp_growth":
            return self.gdp_growth(y, m)
        raise ValueError(var)

    def fx_level(self, y: int, m: int) -> float | None:
        """Tipo de cambio oficial (ARS por USD) del mes: `fx_official` (mes
        exacto, 1992-01+) con fallback a la serie ANUAL enlazada
        (`fx_annual_rows`, 1962+) interpolada con el MISMO `interpolate_annual`
        que `inflation()` / `initial_states.py::rule_inflation`, pero sobre
        `log(valor)` (interpolacion geometrica): el objetivo consume esta
        serie como CAMBIO LOGARITMICO y entre 1962 y 1991 el nivel crece 11
        ordenes de magnitud (1989: x48 en un año) -- una interpolacion lineal
        en niveles concentraria casi toda la depreciacion de un año en sus
        ultimos meses. Convencion heredada de A0: el promedio anual esta
        fechado `YYYY-01-01` y se trata como el valor vigente al 1 de enero
        (corrimiento de ~6 meses, documentado en `CALIBRATION_LOG.md`). Sin
        fallback (antes de esta serie) devolvia `None` para todo el holdout
        `1983-12:1991-12`."""
        exact = self.fx_official.get((y, m))
        if exact is not None and exact > 0:
            return exact
        log_rows = [(ry, rm, math.log(v), sid) for ry, rm, v, sid in self.fx_annual_rows if v > 0]
        hit = interpolate_annual(log_rows, y, m)
        if hit is None:
            return None
        log_value, _note = hit
        return math.exp(log_value)

    def fx_log(self, y: int, m: int) -> float | None:
        v = self.fx_level(y, m)
        if v is None or v <= 0:
            return None
        return math.log(v)

    def std(self, var: str) -> float:
        if var == "exchange_rate":
            # Igual que `inflation` mas abajo: el `sigma` queda anclado a la
            # serie MENSUAL real (1992-01+, mes exacto), no a la anual
            # interpolada de `fx_level()` -- los cambios log mensuales de una
            # interpolacion geometrica de dos promedios anuales son 12 valores
            # identicos por año (ruido cero), mezclarlos correria la escala
            # de normalizacion (y 1989-1990 la haria explotar).
            series = sorted(self.fx_official)
            changes = []
            for y, m in series:
                py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
                a, b = self.fx_official.get((py, pm)), self.fx_official.get((y, m))
                if a and b and a > 0 and b > 0:
                    changes.append(math.log(b) - math.log(a))
            return _stdev(changes) or 1.0
        if var == "gdp_growth":
            values = [self.gdp_growth(y, 6) for y in range(1993, 2024)]
            return _stdev([v for v in values if v is not None]) or 1.0
        # `sigma` de "inflation" queda anclado a `inflation_monthly` (SOLO
        # el tramo 1997+, mes exacto) a proposito, aunque `inflation()`
        # arriba ya tenga fallback anual interpolado para el holdout: mezclar
        # la serie mensual real (ruido bajo) con la anual interpolada (mucho
        # mas suave, un solo numero repartido en 12 meses) correria la
        # escala de normalizacion sin una razon clara -- documentado como
        # simplificacion (A5b, ADR 012 secc. 6).
        source = {
            "inflation": self.inflation_monthly,
            "unemployment": self.unemployment,
            "reserves": self.reserves,
        }[var]
        return _stdev(list(source.values())) or 1.0

    def regime_is_democracy(self, y: int, m: int) -> bool | None:
        mode = self.regimes_by_year.get(y)
        if mode is None:
            return None
        return mode == "democracy"


def _annual_by_year_plain(rows) -> dict[int, float]:
    return {ry: v for ry, _rm, v, _sid in rows}


def _stdev(values: list[float]) -> float:
    values = [v for v in values if v is not None and not math.isnan(v)]
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


# ---------------------------------------------------------------------------
# Simulacion de un mes de arranque + puntuacion contra lo real.
# ---------------------------------------------------------------------------


@dataclass
class StartMonthContext:
    """Todo lo que NO depende del candidato (se cachea por mes de arranque:
    estado inicial real, calendario de shocks/regimen, exogenas historicas)
    -- se recalcula una sola vez por `start_months`, no por evaluacion de
    CMA-ES (ver `calibration/optimizer.py`)."""

    date: str
    pack: object
    initial_state: WorldState
    forced_shocks: dict[int, list[str]]
    historical_exogenous: dict[int, tuple[float, float]]


def build_context(country_id: str, date: str, months: int = MAX_HORIZON) -> StartMonthContext:
    y, m = _ym(date)
    flat = flat_initial_state(date)
    pack = load_country_pack(
        country_id, date, months, regime_mode="auto", initial_state_override=flat
    )
    initial_state = pack.country.initial_state
    forced = dict(historical_shocks_calendar(pack.pack_dir, y, m, months))
    for month_idx, shock_id in failed_coup_shock_months(pack.pack_dir, y, m, months).items():
        forced.setdefault(month_idx, []).append(shock_id)
    hist_exo = historical_exogenous_series(pack.pack_dir, y, m, months)
    return StartMonthContext(
        date=date,
        pack=pack,
        initial_state=initial_state,
        forced_shocks=forced,
        historical_exogenous=hist_exo,
    )


def simulate_from(
    ctx: StartMonthContext,
    coeff: Coefficients,
    bimon: BimonetaryCoefficients,
    seed: int = 0,
    months: int = MAX_HORIZON,
    macro: MacroCoefficients | None = None,
):
    country = ctx.pack.country.model_copy(
        update={"coefficients": coeff, "initial_state": ctx.initial_state, "months": months}
    )
    regime_calendar = build_regime_calendar(
        ctx.pack.pack_dir / "politics" / "events.csv", *_ym(ctx.date), months, mode="auto"
    )
    # `macro` (A5, ADR 012 secc. 6): cuando el candidato incluye el grupo
    # "macro" (`calibration/parameters.py::build_parameter_space(
    # include_macro=True)`), la simulacion usa `step_macro_economy` (regimen
    # cambiario efectivo, balance de pagos) en vez del bloque bimonetario
    # viejo -- `engine/simulation.py::run` desactiva ese canal solo con que
    # `macro_coefficients` no sea `None` (ver Notas de implementacion del
    # ADR 012), asi que pasar `bimon` igual (abajo) es inofensivo. El
    # regimen cambiario real de la fecha (`fx_regime=pack.fx_regime_auto`,
    # ADR 012 secc. 3/deliverable 5) y `X0`/`M0` resueltos de `history/
    # gdp_usd.csv` (`pack.macro_x0`/`pack.macro_m0`) vienen del `CountryPack`
    # cacheado en `ctx` (`build_context`, no dependen del candidato).
    return run(
        seed=seed,
        months=months,
        country=country,
        forced_shocks=ctx.forced_shocks or None,
        actors_enabled=True,
        default_brain="rules",
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        elections_enabled=True,
        regime_calendar=regime_calendar,
        bimonetary_coefficients=bimon,
        historical_exogenous=ctx.historical_exogenous or None,
        macro_coefficients=macro,
        macro_x0=ctx.pack.macro_x0 if macro is not None else None,
        macro_m0=ctx.pack.macro_m0 if macro is not None else None,
        fx_regime=ctx.pack.fx_regime_auto if macro is not None else None,
    )


#: Piso de la penalizacion por corrida terminada ANTES del horizonte `h`
#: (A5b, ADR 012 secc. 6 -- bug encontrado en `a5_macro`): en unidades
#: normalizadas (desvios de la serie real, mismo `sigma` que la RMSE). Ver
#: `score_start_month` para la cuenta completa: sin este piso, una corrida
#: que termina por `hyperinflation`/`collapse` antes de `h` simplemente NO
#: aporta ningun error a ese horizonte (el termino se salteaba con
#: `continue`), asi que CMA-ES quedaba premiado por hiperinflacionar: el
#: reporte de `a5_macro` mostro "sin dato" en TODOS los horizontes de 12
#: meses del brazo calibrado (0 de 124 meses de arranque llegaron al mes
#: 12), algo que ninguna otra columna (persistencia/Aurora/`a3_main`)
#: mostraba. `3.0` (3 sigma) es un piso deliberadamente severo: terminar
#: antes de tiempo tiene que costar AL MENOS tanto como estar off por un
#: outlier grande, para que el optimizador nunca prefiera terminar antes a
#: seguir corriendo con un error grande pero finito.
EARLY_TERMINATION_ERROR_FLOOR_SIGMA = 3.0


def _floor_early_termination_error(error_raw: float, sigma: float) -> float:
    """Aplica el piso de `EARLY_TERMINATION_ERROR_FLOOR_SIGMA` (en unidades
    NATIVAS, no normalizadas: `sigma` ya esta en esas unidades) preservando
    el signo de `error_raw`. `sigma <= 0` (serie sin variacion, no deberia
    ocurrir para las 5 `VARIABLES` pero se cubre) deja `error_raw` tal
    cual -- no hay unidad de sigma con la que fijar un piso."""
    if sigma <= 0:
        return error_raw
    floor_abs = EARLY_TERMINATION_ERROR_FLOOR_SIGMA * sigma
    if abs(error_raw) >= floor_abs:
        return error_raw
    return floor_abs if error_raw >= 0 else -floor_abs


@dataclass
class MonthScore:
    """Errores CRUDOS (sin normalizar, SIN elevar a ninguna potencia) de un
    mes de arranque, con el PESO del mes de arranque adjunto a cada punto
    (`start_month_weight`, A5 ADR 012 secc. 6): se agregan entre meses ANTES
    de normalizar por el desvio de cada serie y de elevar a la potencia de
    la metrica (`aggregate_scores`), para que la metrica final sea sobre
    TODOS los pares (mes, horizonte) ponderados, no un promedio de metricas
    por mes."""

    errors: dict[tuple[str, int], list[tuple[float, float]]]  # (error_crudo, peso)
    regime_hits: list[bool]
    election_hits: list[bool]
    #: `True` si la corrida (NO persistencia) termino ANTES del horizonte
    #: `h` -- A5b (ADR 012 secc. 6, fix del bug de `a5_macro`): `aggregate_
    #: scores` lo resume en `ended_before_h{h}` (fraccion de meses de
    #: arranque) para que el reporte pueda mostrar "cuantas ventanas
    #: terminaron antes de h por brazo", tal como se pidio.
    ended_before_h: dict[int, bool] = field(default_factory=dict)


def score_start_month(
    ctx: StartMonthContext,
    real: RealData,
    coeff: Coefficients,
    bimon: BimonetaryCoefficients,
    persistence: bool,
    seed: int = 0,
    macro: MacroCoefficients | None = None,
    weight: float | None = None,
) -> MonthScore:
    y0, m0 = _ym(ctx.date)
    weight = weight if weight is not None else start_month_weight(ctx.date)
    errors: dict[tuple[str, int], list[tuple[float, float]]] = {
        (v, h): [] for v in VARIABLES for h in HORIZONS
    }
    regime_hits: list[bool] = []
    election_hits: list[bool] = []

    # `fx0_real`/`fx0_model` (dos referencias DISTINTAS a proposito, bug
    # encontrado y corregido en el camino, A3): el log-cambio del modelo se
    # mide contra el `exchange_rate` (indice, base != 1 ARS/USD -- ver
    # `calibration/initial_states.py`, siempre `assumed=100`) del ESTADO
    # INICIAL DEL MODELO, mientras que el log-cambio real se mide contra el
    # oficial REAL en `y0,m0`; mezclarlos (una sola variable `fx0`) resta
    # `log(100)` contra `log(1.0 ARS/USD)` y agrega un sesgo constante de
    # ~4.6 (en unidades de log) a TODOS los meses -- invisible en el
    # sq_error de una corrida individual (domina el termino cuadratico) pero
    # gigante una vez normalizado por el desvio real (~0.07): por eso el
    # smoke test de este modulo compara el `exchange_rate` de las dos
    # baselines contra el numero que da a mano antes de confiar en el
    # resultado (ver tests).
    fx0_real = real.fx_log(y0, m0)
    ended_before_h: dict[int, bool] = {}
    if persistence:
        state_by_h = None
        fx0_model = None
        last_state = None
    else:
        history = simulate_from(ctx, coeff, bimon, seed=seed, macro=macro)
        state_by_h = {r.month_index: r.state for r in history.records}
        fx0_model = (
            math.log(ctx.initial_state.exchange_rate)
            if ctx.initial_state.exchange_rate > 0
            else None
        )
        modes_by_h = {r.month_index: r.regime_mode for r in history.records}
        elections_by_h = {r.month_index: r for r in history.election_records}
        # A5b (ADR 012 secc. 6, fix del bug de `a5_macro`): el ULTIMO estado
        # disponible antes de que la corrida terminara (por `hyperinflation`/
        # `collapse`) -- se usa para EXTRAPOLAR (mantener congelado) el
        # target del modelo en los horizontes que la corrida no llego a
        # alcanzar, en vez de saltear el termino entero (ver mas abajo).
        last_state = history.records[-1].state if history.records else None

    for h in HORIZONS:
        ty, tm = _add_months(y0, m0, h)
        # A5b: `h not in state_by_h` (solo aplica si no es persistencia: la
        # persistencia no "corre" una simulacion, no tiene nocion de
        # terminar antes) es EXACTAMENTE el bug encontrado en `a5_macro`:
        # antes de este fix, el termino de error se salteaba entero para
        # cualquier `(var, h)` de una corrida que hubiera terminado antes de
        # `h`, asi que terminar antes (hiperinflacionar/colapsar) quedaba
        # SIN CASTIGO en ese horizonte -- CMA-ES quedo premiado por eso (el
        # reporte de `a5_macro` mostro "sin dato" en TODO horizonte=12 del
        # brazo calibrado). Ahora se extrapola desde `last_state` (congelado)
        # y el error se PISA a `EARLY_TERMINATION_ERROR_FLOOR_SIGMA` sigma
        # como minimo (`_floor_early_termination_error`), documentado en el
        # docstring de esa constante.
        ended = not persistence and h not in state_by_h
        ended_before_h[h] = ended
        for var in VARIABLES:
            if var == "exchange_rate":
                if fx0_real is None:
                    continue
                real_now = real.fx_level(ty, tm)
                if real_now is None or real_now <= 0:
                    continue
                real_target = math.log(real_now) - fx0_real
                if persistence:
                    model_target = 0.0
                elif h in state_by_h and fx0_model is not None:
                    model_target = math.log(state_by_h[h]["exchange_rate"]) - fx0_model
                elif (
                    last_state is not None
                    and fx0_model is not None
                    and last_state.get("exchange_rate", 0.0) > 0
                ):
                    model_target = math.log(last_state["exchange_rate"]) - fx0_model
                else:
                    model_target = None
            else:
                real_v = real.value(var, ty, tm)
                if real_v is None:
                    continue
                real_target = real_v
                if persistence:
                    real0 = real.value(var, y0, m0)
                    model_target = real0 if real0 is not None else None
                elif h in state_by_h:
                    model_target = state_by_h[h].get(var)
                elif last_state is not None:
                    model_target = last_state.get(var)
                else:
                    model_target = None
            if model_target is None:
                continue
            error_raw = model_target - real_target
            if ended:
                error_raw = _floor_early_termination_error(error_raw, real.std(var))
            errors[(var, h)].append((error_raw, weight))

        if not persistence and 1 <= h and h in modes_by_h:
            real_dem = real.regime_is_democracy(ty, tm)
            if real_dem is not None:
                model_dem = modes_by_h[h] == "democracy"
                regime_hits.append(model_dem == real_dem)

    if not persistence:
        for h, result in elections_by_h.items():
            ty, tm = _add_months(y0, m0, h)
            real_outcome = REAL_ELECTION_OUTCOMES.get(ty)
            if real_outcome is None:
                continue
            election_hits.append(result.outcome_type == real_outcome)

    return MonthScore(
        errors=errors,
        regime_hits=regime_hits,
        election_hits=election_hits,
        ended_before_h=ended_before_h,
    )


def _weighted_rmse(pairs: list[tuple[float, float]], sigma: float) -> float:
    wsum = sum(w for _e, w in pairs)
    if wsum <= 0:
        return float("nan")
    rmse = math.sqrt(sum(w * e * e for e, w in pairs) / wsum)
    return rmse / sigma if sigma else rmse


def _weighted_heavy(pairs: list[tuple[float, float]], sigma: float) -> float:
    """Perdida con cola pesada (A5, ADR 012 secc. 6): media ponderada de
    `|error normalizado|^HEAVY_TAIL_POWER`, SIN raiz final -- ver el
    docstring de `HEAVY_TAIL_POWER` para la cuenta de por que la raiz final
    (que convertiria esto en una p-norma L1.5) haria lo CONTRARIO de lo que
    pide el ADR."""
    wsum = sum(w for _e, w in pairs)
    if wsum <= 0:
        return float("nan")
    p = HEAVY_TAIL_POWER
    if sigma:
        acc = sum(w * (abs(e) / sigma) ** p for e, w in pairs)
    else:
        acc = sum(w * abs(e) ** p for e, w in pairs)
    return acc / wsum


def aggregate_scores(scores: list[MonthScore], real: RealData) -> dict[str, float]:
    """Metricas normalizadas por `(var, horizonte)`, PONDERADAS por el peso
    de cada mes de arranque (`start_month_weight`), mas los terminos de
    regimen/eleccion (tasa de acierto, sin ponderar). Devuelve un dict plano
    listo para el reporte (`calibration/report.py`) con DOS metricas por
    `(var, horizonte)` (A5, ADR 012 secc. 6: "el reporte muestra ambas
    metricas"):

    - `{var}_h{h}`: RMSE normalizada (MISMA formula/semantica que antes de
      A5 -- con `weight=1.0` en todos los meses da byte a byte el mismo
      numero, asi que sigue siendo la clave que usaban `report.py`/
      `scalar_objective(loss="rmse")` y los tests de A3).
    - `{var}_h{h}_heavy`: perdida con cola pesada (`HEAVY_TAIL_POWER`),
      nueva en A5.

    Ademas, `ended_before_h{h}` (A5b, fix del bug de `a5_macro`): fraccion
    de meses de arranque cuya corrida (NO persistencia) termino antes de
    `h` -- `nan` si `scores` no tiene ningun `MonthScore` de una corrida
    real (p.ej. al evaluar `persistence=True`, donde `ended_before_h` queda
    `{}` en cada `MonthScore`)."""
    out: dict[str, float] = {}
    for var in VARIABLES:
        sigma = real.std(var)
        for h in HORIZONS:
            pairs = [e for s in scores for e in s.errors[(var, h)]]
            if not pairs:
                out[f"{var}_h{h}"] = float("nan")
                out[f"{var}_h{h}_heavy"] = float("nan")
                continue
            out[f"{var}_h{h}"] = _weighted_rmse(pairs, sigma)
            out[f"{var}_h{h}_heavy"] = _weighted_heavy(pairs, sigma)
    for h in HORIZONS:
        ended_flags = [s.ended_before_h[h] for s in scores if h in s.ended_before_h]
        out[f"ended_before_h{h}"] = (
            sum(ended_flags) / len(ended_flags) if ended_flags else float("nan")
        )
    regime_hits = [h for s in scores for h in s.regime_hits]
    out["regime_accuracy"] = sum(regime_hits) / len(regime_hits) if regime_hits else float("nan")
    election_hits = [h for s in scores for h in s.election_hits]
    out["election_accuracy"] = (
        sum(election_hits) / len(election_hits) if election_hits else float("nan")
    )
    return out


def scalar_objective(
    metrics: dict[str, float],
    params: list[Parameter],
    x: list[float],
    lambda_reg: float,
    loss: str = "rmse",
) -> float:
    """Escalar que minimiza CMA-ES: suma de las metricas normalizadas por
    `(var, horizonte)` (NaN ignorado -- variable/horizonte sin dato real en
    esta ventana) + (1 - regime_accuracy) + (1 - election_accuracy) +
    regularizacion L2 hacia Aurora (en unidades `[0,1]` de cada parametro,
    para que todos pesen parecido sin importar la escala nativa del
    coeficiente). `loss` (A5, ADR 012 secc. 6): `"rmse"` (default, igual que
    antes de A5) o `"heavy"` (cola pesada, `{var}_h{h}_heavy` en vez de
    `{var}_h{h}`) -- cualquier otro valor es un error del llamador."""
    if loss not in ("rmse", "heavy"):
        raise ValueError(f"loss debe ser 'rmse' o 'heavy', se pidio {loss!r}.")
    suffix = "_heavy" if loss == "heavy" else ""
    total = 0.0
    for var in VARIABLES:
        for h in HORIZONS:
            v = metrics.get(f"{var}_h{h}{suffix}", float("nan"))
            if not math.isnan(v):
                total += v
    if not math.isnan(metrics.get("regime_accuracy", float("nan"))):
        total += 1.0 - metrics["regime_accuracy"]
    if not math.isnan(metrics.get("election_accuracy", float("nan"))):
        total += 1.0 - metrics["election_accuracy"]
    if lambda_reg > 0:
        reg = 0.0
        for p, v in zip(params, x, strict=True):
            u = p.to_unit(v)
            u_aurora = p.to_unit(p.aurora_value)
            reg += (u - u_aurora) ** 2
        total += lambda_reg * reg
    return total


def evaluate(
    contexts: list[StartMonthContext],
    real: RealData,
    params: list[Parameter],
    x: list[float],
    base_coeff: Coefficients,
    base_bimon: BimonetaryCoefficients,
    base_macro: MacroCoefficients | None = None,
    lambda_reg: float = 0.01,
    persistence: bool = False,
    seed: int = 0,
    loss: str = "rmse",
) -> tuple[float, dict[str, float]]:
    """Evalua UN candidato `x` (vector en unidades nativas, ya clippeado)
    sobre todos los `contexts` (secuencial: la paralelizacion por mes de
    arranque vive en `calibration/optimizer.py`, que llama a
    `score_start_month` directamente en cada worker). `base_macro` distinto
    de `None` (A5, ADR 012 secc. 6) activa el grupo `"macro"` del vector
    (`params` debe venir de `build_parameter_space(include_macro=True)`,
    si no `macro_from_vector` devuelve `base_macro` sin cambios)."""
    coeff = coefficients_from_vector(params, x, base_coeff)
    bimon = bimonetary_from_vector(params, x, base_bimon)
    macro = macro_from_vector(params, x, base_macro) if base_macro is not None else None
    scores = [
        score_start_month(ctx, real, coeff, bimon, persistence=persistence, seed=seed, macro=macro)
        for ctx in contexts
    ]
    metrics = aggregate_scores(scores, real)
    scalar = (
        scalar_objective(metrics, params, x, lambda_reg, loss=loss)
        if not persistence
        else float("nan")
    )
    return scalar, metrics
