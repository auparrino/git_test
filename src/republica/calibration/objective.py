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

from republica.calibration.initial_states import flat_initial_state, load_series
from republica.calibration.parameters import (
    Parameter,
    bimonetary_from_vector,
    coefficients_from_vector,
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
from republica.world.regime import build_regime_calendar
from republica.world.state import WorldState

HORIZONS = (1, 3, 6, 12)
MAX_HORIZON = 12
VARIABLES = ("inflation", "gdp_growth", "unemployment", "exchange_rate", "reserves")

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
    unemployment: dict[tuple[int, int], float] = field(default_factory=dict)
    reserves: dict[tuple[int, int], float] = field(default_factory=dict)
    fx_official: dict[tuple[int, int], float] = field(default_factory=dict)
    emae: dict[tuple[int, int], float] = field(default_factory=dict)
    gdp_pc_by_year: dict[int, float] = field(default_factory=dict)
    regimes_by_year: dict[int, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> RealData:
        def as_dict(name):
            return {(y, m): v for y, m, v, _sid in load_series(name)}

        gdp_pc_rows = load_series("gdp_per_capita_real")
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
            unemployment=as_dict("unemployment"),
            reserves=as_dict("reserves_monthly"),
            fx_official=as_dict("exchange_rate_official_monthly"),
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

    def value(self, var: str, y: int, m: int) -> float | None:
        if var == "inflation":
            return self.inflation_monthly.get((y, m))
        if var == "unemployment":
            return self.unemployment.get((y, m))
        if var == "reserves":
            return self.reserves.get((y, m))
        if var == "gdp_growth":
            return self.gdp_growth(y, m)
        raise ValueError(var)

    def fx_log(self, y: int, m: int) -> float | None:
        v = self.fx_official.get((y, m))
        if v is None or v <= 0:
            return None
        return math.log(v)

    def std(self, var: str) -> float:
        if var == "exchange_rate":
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
):
    country = ctx.pack.country.model_copy(
        update={"coefficients": coeff, "initial_state": ctx.initial_state, "months": months}
    )
    regime_calendar = build_regime_calendar(
        ctx.pack.pack_dir / "politics" / "events.csv", *_ym(ctx.date), months, mode="auto"
    )
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
    )


@dataclass
class MonthScore:
    """Errores CRUDOS (sin normalizar) de un mes de arranque: se agregan
    entre meses ANTES de dividir por el desvio de cada serie (`score_batch`)
    para que el RMSE final sea sobre todos los pares (mes, horizonte), no un
    promedio de RMSEs por mes."""

    sq_errors: dict[tuple[str, int], list[float]]
    regime_hits: list[bool]
    election_hits: list[bool]


def score_start_month(
    ctx: StartMonthContext,
    real: RealData,
    coeff: Coefficients,
    bimon: BimonetaryCoefficients,
    persistence: bool,
    seed: int = 0,
) -> MonthScore:
    y0, m0 = _ym(ctx.date)
    sq: dict[tuple[str, int], list[float]] = {(v, h): [] for v in VARIABLES for h in HORIZONS}
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
    if persistence:
        state_by_h = None
        fx0_model = None
    else:
        history = simulate_from(ctx, coeff, bimon, seed=seed)
        state_by_h = {r.month_index: r.state for r in history.records}
        fx0_model = (
            math.log(ctx.initial_state.exchange_rate)
            if ctx.initial_state.exchange_rate > 0
            else None
        )
        modes_by_h = {r.month_index: r.regime_mode for r in history.records}
        elections_by_h = {r.month_index: r for r in history.election_records}

    for h in HORIZONS:
        ty, tm = _add_months(y0, m0, h)
        for var in VARIABLES:
            if var == "exchange_rate":
                if fx0_real is None:
                    continue
                real_now = real.fx_official.get((ty, tm))
                if real_now is None or real_now <= 0:
                    continue
                real_target = math.log(real_now) - fx0_real
                model_target = (
                    0.0
                    if persistence
                    else (
                        (math.log(state_by_h[h]["exchange_rate"]) - fx0_model)
                        if h in state_by_h and fx0_model is not None
                        else None
                    )
                )
            else:
                real_v = real.value(var, ty, tm)
                if real_v is None:
                    continue
                real_target = real_v
                if persistence:
                    real0 = real.value(var, y0, m0)
                    model_target = real0 if real0 is not None else None
                else:
                    model_target = state_by_h.get(h, {}).get(var) if h in state_by_h else None
            if model_target is None:
                continue
            sq[(var, h)].append((model_target - real_target) ** 2)

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

    return MonthScore(sq_errors=sq, regime_hits=regime_hits, election_hits=election_hits)


def aggregate_scores(scores: list[MonthScore], real: RealData) -> dict[str, float]:
    """RMSE normalizado por `(var, horizonte)` mas los terminos de regimen/
    elecciones (tasa de acierto). Devuelve un dict plano listo para el
    reporte (`calibration/report.py`)."""
    out: dict[str, float] = {}
    for var in VARIABLES:
        sigma = real.std(var)
        for h in HORIZONS:
            all_sq = [e for s in scores for e in s.sq_errors[(var, h)]]
            if not all_sq:
                out[f"{var}_h{h}"] = float("nan")
                continue
            rmse = math.sqrt(sum(all_sq) / len(all_sq))
            out[f"{var}_h{h}"] = rmse / sigma if sigma else rmse
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
) -> float:
    """Escalar que minimiza CMA-ES: suma de los RMSE normalizados (NaN
    ignorado -- variable/horizonte sin dato real en esta ventana) + (1 -
    regime_accuracy) + (1 - election_accuracy) + regularizacion L2 hacia
    Aurora (en unidades `[0,1]` de cada parametro, para que todos pesen
    parecido sin importar la escala nativa del coeficiente)."""
    total = 0.0
    for var in VARIABLES:
        for h in HORIZONS:
            v = metrics.get(f"{var}_h{h}", float("nan"))
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
    lambda_reg: float = 0.01,
    persistence: bool = False,
    seed: int = 0,
) -> tuple[float, dict[str, float]]:
    """Evalua UN candidato `x` (vector en unidades nativas, ya clippeado)
    sobre todos los `contexts` (secuencial: la paralelizacion por mes de
    arranque vive en `calibration/optimizer.py`, que llama a
    `score_start_month` directamente en cada worker)."""
    coeff = coefficients_from_vector(params, x, base_coeff)
    bimon = bimonetary_from_vector(params, x, base_bimon)
    scores = [
        score_start_month(ctx, real, coeff, bimon, persistence=persistence, seed=seed)
        for ctx in contexts
    ]
    metrics = aggregate_scores(scores, real)
    scalar = scalar_objective(metrics, params, x, lambda_reg) if not persistence else float("nan")
    return scalar, metrics
