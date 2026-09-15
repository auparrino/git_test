"""Validacion historica de Argentina (A4, ADR 011 secc. 8).

Tres pruebas con hipotesis REGISTRADAS ANTES de correr (`HYPOTHESES`, texto
literal de la tabla del ADR 011 secc. 8 -- hay un test que lo compara
caracter a caracter contra el markdown del ADR) mas un control con los
coeficientes SIN CALIBRAR de Aurora:

- `V1` 1988-06 + 24 meses, solo exogenas reales, sin ningun shock forzado
  (`hyperinflation_regime` no se fuerza NUNCA, ADR 011 secc. 4).
- `V2` 1998-01 + 54 meses, `fx_regime = peg`, crisis internacional 1998-99
  forzada desde `politics/shocks_calendar.csv`.
- `V3` 2016-01 + 96 meses, sequia 2018 / pandemia 2020 / sequia 2023
  forzadas desde el mismo calendario.
- `C` = las tres anteriores con los coeficientes de Aurora (brazo `aurora`
  de cada prueba), para medir el "valor" de la calibracion.

Protocolo (PLAN_ARGENTINA.md secc. 0.3 y 4): antes de correr una sola
simulacion se escribe `registration.json` en el directorio de salida con
(a) la hipotesis literal de cada prueba, (b) los shocks forzados PEDIDOS por
el ADR y los que el calendario real permite aplicar EFECTIVAMENTE, y (c) la
procedencia (`source`/`proxy`/`assumed`) de cada variable del estado
inicial. Recien despues se corre; el reporte no puede "elegir" la hipotesis
a posteriori.

Los shocks ALEATORIOS de Aurora (`shocks.json`) siguen activos, igual que en
cualquier `republica run`: la lista de shocks forzados no es la lista de
shocks que ocurrieron. El reporte incluye los aleatorios observados.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from republica.calibration.run import HONESTY_SENTENCE
from republica.engine.narrate import annualized_inflation
from republica.engine.policy import PassivePolicy
from republica.engine.simulation import History
from republica.engine.simulation import run as run_simulation
from republica.world.countries import (
    CountryPack,
    country_pack_dir,
    historical_exogenous_series,
    load_country_pack,
)

#: Hipotesis de la tabla de ADR 011 secc. 8, columna "Hipotesis", LITERAL.
#: `tests/test_validation_argentina.py::test_hypotheses_match_adr_text` las
#: compara caracter a caracter contra `docs/ADR_011_country_pack_argentina.md`:
#: si alguien edita el ADR despues de correr A4, el test falla y obliga a
#: re-registrar (no se puede reescribir la hipotesis para que de).
HYPOTHESES: dict[str, str] = {
    "V1": "el modelo entra en `hyperinflation` en 12–24 meses en > 50 % de semillas",
    "V2": "`sovereign_default` o `collapse` en 36–54 meses en > 50 %",
    "V3": "inflación anual final > 80 % en la mediana y el oficialismo pierde en 2019 y 2023",
    "C": "Aurora sin calibrar falla al menos una de las tres",
}

#: Columna "Metrica" de la misma tabla, tambien literal (mismo test).
METRICS: dict[str, str] = {
    "V1": "fracción de semillas, mes mediano",
    "V2": "idem + trayectoria de reservas vs real",
    "V3": "error de inflación, aciertos electorales",
    "C": 'la diferencia con el calibrado es el "valor" de la calibración',
}

#: Columna "Shocks forzados" de la misma tabla, tambien literal.
ADR_FORCED_SHOCKS: dict[str, str] = {
    "V1": "solo exógenos (commodities, mundo) — **no** se fuerza la hiper",
    "V2": "crisis internacional 1998–99 (Rusia, Brasil)",
    "V3": "sequía 2018, pandemia 2020, sequía 2023",
    "C": "los mismos",
}

#: Brazos de cada prueba: `calibrated` usa `calibration/<run_id>/`,
#: `aurora` los coeficientes de `country.json` sin tocar (la fila C del ADR).
ARMS: tuple[str, str] = ("calibrated", "aurora")

ARM_LABELS = {"calibrated": "calibrado", "aurora": "Aurora sin calibrar"}


@dataclass(frozen=True)
class ShockRequest:
    """Un shock que el ADR pide forzar, como CONSULTA al calendario real
    (`politics/shocks_calendar.csv`), no como una fila inventada: `shock_id`
    dentro de la ventana `[date_from, date_to]` (`YYYY-MM` inclusive). Si el
    calendario no tiene ninguna fila que matchee, NO se fuerza nada y el
    faltante queda registrado en `registration.json` y en el reporte (regla
    de honestidad: ningun dato historico se inventa, PLAN_ARGENTINA.md
    secc. 0.1)."""

    shock_id: str
    date_from: str
    date_to: str
    label: str


@dataclass(frozen=True)
class ValidationTest:
    test_id: str
    title: str
    start: str
    months: int
    fx_regime: str | None
    shock_requests: tuple[ShockRequest, ...]
    #: Serie real contra la que se compara la trayectoria del grafico.
    real_series: str
    real_series_label: str
    y_label: str


TESTS: tuple[ValidationTest, ...] = (
    ValidationTest(
        test_id="V1",
        title="V1 1988→1990: ¿emerge la hiperinflación?",
        start="1988-06",
        months=24,
        fx_regime=None,
        shock_requests=(),
        real_series="inflation_monthly_implied",
        real_series_label="IPC mensual implícito de la variación anual (Banco Mundial)",
        y_label="inflación mensual (%)",
    ),
    ValidationTest(
        test_id="V2",
        title="V2 1998→2002: ¿colapso con convertibilidad rígida?",
        start="1998-01",
        months=54,
        fx_regime="peg",
        shock_requests=(
            ShockRequest(
                shock_id="international_crisis",
                date_from="1998-01",
                date_to="1999-12",
                label="crisis internacional 1998–99 (Rusia, Brasil)",
            ),
        ),
        real_series="reserves_monthly",
        real_series_label="reservas del BCRA (USD M, fin de mes)",
        y_label="reservas (USD M)",
    ),
    ValidationTest(
        test_id="V3",
        title="V3 2016→2023: ¿se acelera la inflación y pierde el oficialismo?",
        start="2016-01",
        months=96,
        fx_regime=None,
        shock_requests=(
            ShockRequest("drought", "2018-01", "2018-12", "sequía 2018"),
            ShockRequest("epidemic", "2020-01", "2020-12", "pandemia 2020"),
            ShockRequest("drought", "2023-01", "2023-12", "sequía 2023"),
        ),
        real_series="inflation_annual",
        real_series_label="IPC, variación anual (Banco Mundial, serie empalmada)",
        y_label="inflación anualizada (%)",
    ),
)

TESTS_BY_ID = {t.test_id: t for t in TESTS}


# --------------------------------------------------------------------------
# Calendario de shocks: lo pedido por el ADR vs. lo que el calendario tiene
# --------------------------------------------------------------------------


def _month_index(start: str, date: str) -> int:
    sy, sm = int(start[:4]), int(start[5:7])
    y, m = int(date[:4]), int(date[5:7])
    return (y - sy) * 12 + (m - sm) + 1


def month_date(start: str, month_index: int) -> str:
    """`month_index` 1 == `start` (mismo criterio que
    `engine/simulation.py::_format_date`)."""
    sy, sm = int(start[:4]), int(start[5:7])
    total = (sm - 1) + (month_index - 1)
    return f"{sy + total // 12:04d}-{total % 12 + 1:02d}"


def _read_shocks_calendar(pack_dir: Path) -> list[dict[str, str]]:
    path = pack_dir / "politics" / "shocks_calendar.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@dataclass
class ForcedShockPlan:
    """Lo que se le pasa a `run(forced_shocks=...)` mas la traza de como se
    llego a eso (para `registration.json` y el reporte)."""

    forced: dict[int, list[str]] = field(default_factory=dict)
    requested: list[dict] = field(default_factory=list)

    @property
    def applied_rows(self) -> list[dict]:
        return [row for req in self.requested for row in req["matched"]]

    @property
    def unmatched(self) -> list[dict]:
        return [req for req in self.requested if not req["matched"]]


def resolve_forced_shocks(pack_dir: Path, test: ValidationTest, months: int) -> ForcedShockPlan:
    """Traduce los `ShockRequest` del ADR a `{mes: [shock_id]}` consultando
    `politics/shocks_calendar.csv`. Cada pedido queda registrado con las
    filas del calendario que lo satisfacen (puede ser ninguna)."""
    rows = _read_shocks_calendar(pack_dir)
    plan = ForcedShockPlan()
    for req in test.shock_requests:
        matched: list[dict] = []
        for row in rows:
            if row["shock_id"] != req.shock_id:
                continue
            date = row["date"][:7]
            if not (req.date_from <= date <= req.date_to):
                continue
            idx = _month_index(test.start, date)
            if not (1 <= idx <= months):
                continue
            matched.append(
                {
                    "shock_id": row["shock_id"],
                    "date": date,
                    "month_index": idx,
                    "title": row.get("title", ""),
                    "duration_months": row.get("duration_months", ""),
                }
            )
            plan.forced.setdefault(idx, []).append(row["shock_id"])
        plan.requested.append(
            {
                "shock_id": req.shock_id,
                "label": req.label,
                "window": f"{req.date_from}:{req.date_to}",
                "matched": matched,
            }
        )
    return plan


# --------------------------------------------------------------------------
# Corrida de una prueba
# --------------------------------------------------------------------------


@dataclass
class SeedRun:
    """Lo que el analisis necesita de UNA corrida (no se guarda el JSONL
    completo de 300 corridas: el reporte usa estas series)."""

    seed: int
    outcome: str
    months_run: int
    dates: list[str]
    inflation_monthly: list[float]
    reserves: list[float]
    political_stability: list[float]
    government_approval: list[float]
    default_active_months: list[int]
    elections: list[dict]
    random_shocks: list[str]

    @property
    def inflation_annual_final(self) -> float:
        return annualized_inflation(self.inflation_monthly[-1])


def _history_to_seed_run(seed: int, history: History, forced_ids: set[str]) -> SeedRun:
    recs = history.records
    return SeedRun(
        seed=seed,
        outcome=history.outcome,
        months_run=len(recs),
        dates=[r.date for r in recs],
        inflation_monthly=[r.state["inflation"] for r in recs],
        reserves=[r.state["reserves"] for r in recs],
        political_stability=[r.state["political_stability"] for r in recs],
        government_approval=[r.state["government_approval"] for r in recs],
        default_active_months=[
            r.month_index for r in recs if "sovereign_default" in r.shocks_active
        ],
        elections=[
            {
                "month": e.month,
                "date": recs[e.month - 1].date if e.month <= len(recs) else "",
                "outcome_type": e.outcome_type,
                "winner": e.winner,
                "incumbent_party": e.incumbent_party,
            }
            for e in history.election_records
        ],
        random_shocks=sorted({s for r in recs for s in r.shocks_new if s not in forced_ids}),
    )


def _load_pack(test: ValidationTest, months: int) -> CountryPack:
    return load_country_pack("argentina", test.start, months, regime_mode="auto")


def run_test_arm(
    test: ValidationTest,
    arm: str,
    pack: CountryPack,
    plan: ForcedShockPlan,
    months: int,
    seeds: int,
    seed_base: int,
    calibration_run_id: str,
) -> list[SeedRun]:
    """Corre `seeds` semillas de `test` con el brazo `arm`
    (`calibrated`/`aurora`). Todo lo demas (estado inicial real, calendario
    de regimen, exogenas reales, features de `country.json`) es identico
    entre brazos: la UNICA diferencia es el vector de coeficientes."""
    from dataclasses import replace as dc_replace

    country = pack.country
    bimonetary = pack.bimonetary_coefficients
    if arm == "calibrated":
        from republica.calibration.run import load_calibrated_country

        coeff, bimonetary = load_calibrated_country("argentina", calibration_run_id)
        country = country.model_copy(update={"coefficients": coeff})
    if test.fx_regime:
        bimonetary = dc_replace(bimonetary, fx_regime_default=test.fx_regime)

    exogenous = historical_exogenous_series(
        pack.pack_dir, int(test.start[:4]), int(test.start[5:7]), months
    )
    policy_rule = PassivePolicy(
        country.default_policy,
        country.structure.r_neutral,
        country.policy_ranges["interest_rate_target"],
    )
    features = country.features
    forced_ids = {sid for ids in plan.forced.values() for sid in ids}

    runs: list[SeedRun] = []
    for i in range(seeds):
        seed = seed_base + i
        history = run_simulation(
            seed=seed,
            months=months,
            policy_rule=policy_rule,
            forced_shocks={k: list(v) for k, v in plan.forced.items()} or None,
            country=country,
            actors_enabled=features.get("actors", True),
            congress_enabled=features.get("congress", True),
            negotiation_enabled=features.get("negotiation", True),
            cohorts_enabled=features.get("cohorts", True),
            media_enabled=features.get("media", True),
            memory_enabled=features.get("memory", True),
            elections_enabled=features.get("elections", True),
            regime_calendar=pack.regime_calendar,
            bimonetary_coefficients=bimonetary,
            historical_exogenous=exogenous,
        )
        runs.append(_history_to_seed_run(seed, history, forced_ids))
    return runs


# --------------------------------------------------------------------------
# Metricas y bootstrap
# --------------------------------------------------------------------------


def bootstrap_ci(
    values: list[float],
    stat,
    *,
    resamples: int = 2000,
    seed: int = 20240501,
    level: float = 0.95,
) -> tuple[float | None, float | None]:
    """IC percentil por bootstrap sobre las SEMILLAS (remuestreo con
    reemplazo del vector de resultados por semilla). Devuelve `(None, None)`
    si no hay datos suficientes."""
    clean = [v for v in values if v is not None]
    if not clean:
        return (None, None)
    rng = random.Random(seed)
    n = len(clean)
    stats: list[float] = []
    for _ in range(resamples):
        sample = [clean[rng.randrange(n)] for _ in range(n)]
        try:
            stats.append(float(stat(sample)))
        except (statistics.StatisticsError, ValueError, ZeroDivisionError):
            continue
    if not stats:
        return (None, None)
    stats.sort()
    lo_i = int((1.0 - level) / 2.0 * len(stats))
    hi_i = min(len(stats) - 1, int((1.0 + level) / 2.0 * len(stats)))
    return (stats[lo_i], stats[hi_i])


def _fraction(flags: list[bool]) -> float:
    return sum(1 for f in flags if f) / len(flags) if flags else 0.0


def _median_or_none(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


def metrics_v1(runs: list[SeedRun], months: int, resamples: int) -> dict:
    """ADR 011 secc. 8, V1: fraccion de semillas que entran en
    `hyperinflation` y mes mediano. El motor TERMINA la corrida cuando
    dispara `hyperinflation` (`world/events.py::check_termination`), asi que
    el mes del evento es el ultimo mes simulado."""
    hyper = [r.outcome == "hyperinflation" for r in runs]
    months_hyper = [float(r.months_run) for r in runs if r.outcome == "hyperinflation"]
    frac = _fraction(hyper)
    lo, hi = bootstrap_ci([1.0 if h else 0.0 for h in hyper], statistics.mean, resamples=resamples)
    m_lo, m_hi = bootstrap_ci(months_hyper, statistics.median, resamples=resamples)
    return {
        "hyperinflation_fraction": frac,
        "hyperinflation_fraction_ci": [lo, hi],
        "hyperinflation_median_month": _median_or_none(months_hyper),
        "hyperinflation_median_month_ci": [m_lo, m_hi],
        "n_hyperinflation": len(months_hyper),
        "outcomes": _outcome_counts(runs),
        "inflation_monthly_final_median": statistics.median(
            [r.inflation_monthly[-1] for r in runs]
        ),
        "inflation_annual_final_median": statistics.median(
            [r.inflation_annual_final for r in runs]
        ),
        "passes": frac > 0.5,
    }


def metrics_v2(runs: list[SeedRun], months: int, resamples: int, real: dict[str, float]) -> dict:
    """ADR 011 secc. 8, V2: `sovereign_default` o `collapse` en los meses
    36-54, mas el RMSE de la trayectoria de reservas contra la serie real.

    `sovereign_default` NO es un `outcome` del motor (los outcomes son
    `survived/collapse/hyperinflation/reelected/defeated`): es un SHOCK, que
    en esta corrida solo puede activarse por el disparo ENDOGENO del bloque
    bimonetario (`default_risk >= default_risk_threshold`), porque el
    calendario de 1998-2002 no fuerza ninguno."""
    lo_m, hi_m = 36, min(54, months)
    window = range(lo_m, hi_m + 1) if hi_m >= lo_m else range(0)
    flags: list[bool] = []
    for r in runs:
        defaulted = any(m in window for m in r.default_active_months)
        collapsed = r.outcome == "collapse" and r.months_run in window
        flags.append(defaulted or collapsed)
    frac = _fraction(flags)
    lo, hi = bootstrap_ci([1.0 if f else 0.0 for f in flags], statistics.mean, resamples=resamples)

    rmses: list[float] = []
    for r in runs:
        errs = [(r.reserves[i] - real[d]) ** 2 for i, d in enumerate(r.dates) if d in real]
        if errs:
            rmses.append((sum(errs) / len(errs)) ** 0.5)
    r_lo, r_hi = bootstrap_ci(rmses, statistics.median, resamples=resamples)

    # Baseline ingenuo: reservas constantes en el nivel real del mes de
    # arranque (persistencia), el mismo criterio de baseline que A3.
    base_rmse = None
    if runs and real:
        d0 = runs[0].dates[0]
        if d0 in real:
            errs = [(real[d0] - real[d]) ** 2 for d in runs[0].dates if d in real]
            if errs:
                base_rmse = (sum(errs) / len(errs)) ** 0.5

    return {
        "default_or_collapse_fraction": frac,
        "default_or_collapse_fraction_ci": [lo, hi],
        "window_months": [lo_m, hi_m] if hi_m >= lo_m else [],
        "window_empty": hi_m < lo_m,
        "n_default": sum(1 for r in runs if any(m in window for m in r.default_active_months)),
        "n_collapse_in_window": sum(
            1 for r in runs if r.outcome == "collapse" and r.months_run in window
        ),
        "outcomes": _outcome_counts(runs),
        "reserves_rmse_median": _median_or_none(rmses),
        "reserves_rmse_ci": [r_lo, r_hi],
        "reserves_rmse_persistence": base_rmse,
        "passes": frac > 0.5,
    }


#: Elecciones reales del periodo de V3 y su resultado (hecho publico:
#: 2019 Macri pierde ante Fernandez, 2023 Massa -- oficialismo -- pierde
#: ante Milei). El motor pone sus elecciones en multiplos de `term_length`
#: desde `--start` (ADR 011, Notas de implementacion A2: no calza las fechas
#: reales de octubre), asi que con `--start 2016-01` y mandato de 4 años
#: caen en 2019-12 y 2023-12.
V3_REAL_ELECTIONS: dict[str, str] = {"2019-12": "defeated", "2023-12": "defeated"}


def metrics_v3(runs: list[SeedRun], months: int, resamples: int) -> dict:
    """ADR 011 secc. 8, V3: mediana de la inflacion anualizada final y
    acierto electoral en 2019 y 2023."""
    finals = [r.inflation_annual_final for r in runs]
    med = statistics.median(finals)
    lo, hi = bootstrap_ci(finals, statistics.median, resamples=resamples)

    elections: dict[str, dict] = {}
    for date, real_outcome in V3_REAL_ELECTIONS.items():
        held = [r for r in runs if any(e["date"] == date for e in r.elections)]
        hits = [
            any(e["date"] == date and e["outcome_type"] == real_outcome for e in r.elections)
            for r in runs
        ]
        frac = _fraction(hits)
        e_lo, e_hi = bootstrap_ci(
            [1.0 if h else 0.0 for h in hits], statistics.mean, resamples=resamples
        )
        elections[date] = {
            "real_outcome": real_outcome,
            "n_held": len(held),
            "hit_fraction": frac,
            "hit_fraction_ci": [e_lo, e_hi],
            "passes": frac > 0.5,
        }

    inflation_ok = med > 80.0
    elections_ok = all(e["passes"] for e in elections.values())
    return {
        "inflation_annual_final_median": med,
        "inflation_annual_final_ci": [lo, hi],
        "inflation_threshold": 80.0,
        "inflation_passes": inflation_ok,
        "elections": elections,
        "outcomes": _outcome_counts(runs),
        "median_months_run": statistics.median([float(r.months_run) for r in runs]),
        "passes": inflation_ok and elections_ok,
    }


def _outcome_counts(runs: list[SeedRun]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in runs:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    return dict(sorted(counts.items()))


# --------------------------------------------------------------------------
# Series reales
# --------------------------------------------------------------------------


def _load_history_csv(pack_dir: Path, name: str) -> list[tuple[str, float]]:
    path = pack_dir / "history" / f"{name}.csv"
    if not path.exists():
        return []
    out: list[tuple[str, float]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out.append((row["date"][:7], float(row["value"])))
            except (TypeError, ValueError):
                continue
    return out


def real_series_for(pack_dir: Path, test: ValidationTest, dates: list[str]) -> dict[str, float]:
    """La serie real con la que se compara la trayectoria del modelo, ya
    alineada a los meses de la corrida. Vacia si no hay dato para el
    periodo (V1: no hay IPC MENSUAL descargado antes de 1997-02, asi que se
    usa la variacion anual del Banco Mundial convertida a mensual
    equivalente `(1+a)^(1/12)-1` -- un proxy DERIVADO, declarado como tal,
    no una serie mensual medida)."""
    if test.real_series == "reserves_monthly":
        table = dict(_load_history_csv(pack_dir, "reserves_monthly"))
        return {d: table[d] for d in dates if d in table}
    annual = {d[:4]: v for d, v in _load_history_csv(pack_dir, "inflation_cpi_annual_linked")}
    if test.real_series == "inflation_annual":
        return {d: annual[d[:4]] for d in dates if d[:4] in annual}
    if test.real_series == "inflation_monthly_implied":
        return {
            d: ((1.0 + annual[d[:4]] / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
            for d in dates
            if d[:4] in annual
        }
    return {}


def model_series_for(test: ValidationTest, run: SeedRun) -> list[float]:
    if test.real_series == "reserves_monthly":
        return run.reserves
    if test.real_series == "inflation_annual":
        return [annualized_inflation(x) for x in run.inflation_monthly]
    return run.inflation_monthly


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------


@dataclass
class ValidationResult:
    test_id: str
    months: int
    plan: ForcedShockPlan
    runs_by_arm: dict[str, list[SeedRun]]
    metrics_by_arm: dict[str, dict]
    real: dict[str, float]
    wall_seconds: float
    diagnostics: dict = field(default_factory=dict)


def inflation_persistence() -> dict[str, float]:
    """`rho_pi + c_e`, el coeficiente TOTAL sobre la inflacion del mes
    anterior en `world/economy.py` (§4.3 + §4.2: `de` arranca en `π_t`), leido
    de disco para Aurora y para la calibracion. > 1 seria una dinamica
    explosiva (hiperinflacion endogena posible); < 1 es una contraccion."""
    from republica.calibration.run import CALIBRATION_ROOT
    from republica.world.config import DEFAULT_DATA_DIR

    aurora = json.loads((DEFAULT_DATA_DIR / "country.json").read_text(encoding="utf-8"))[
        "coefficients"
    ]
    out = {"aurora_rho_pi": aurora["rho_pi"], "aurora_c_e": aurora["c_e"]}
    out["aurora_total"] = out["aurora_rho_pi"] + out["aurora_c_e"]
    path = CALIBRATION_ROOT / "a3_main" / "coefficients.json"
    if path.exists():
        cal = json.loads(path.read_text(encoding="utf-8"))["coefficients"]
        out["calibrated_rho_pi"] = cal["rho_pi"]
        out["calibrated_c_e"] = cal["c_e"]
        out["calibrated_total"] = cal["rho_pi"] + cal["c_e"]
    return out


def fx_regime_inertness_check(
    test: ValidationTest,
    pack: CountryPack,
    plan: ForcedShockPlan,
    months: int,
    calibration_run_id: str,
    seeds: int = 3,
) -> dict:
    """Comprueba EMPIRICAMENTE si `--fx-regime <test.fx_regime>` cambia algo:
    corre las mismas semillas con el regimen pedido y con `float` y compara
    las 20 variables mes a mes. El reporte de V2 se apoya en este resultado,
    no en una lectura del codigo."""
    if not test.fx_regime:
        return {}
    from dataclasses import replace as dc_replace

    variant = dc_replace(test, fx_regime="float")
    a = run_test_arm(test, "calibrated", pack, plan, months, seeds, 1, calibration_run_id)
    b = run_test_arm(variant, "calibrated", pack, plan, months, seeds, 1, calibration_run_id)
    identical = all(
        ra.inflation_monthly == rb.inflation_monthly
        and ra.reserves == rb.reserves
        and ra.political_stability == rb.political_stability
        and ra.outcome == rb.outcome
        for ra, rb in zip(a, b, strict=True)
    )
    return {
        "compared_regimes": [test.fx_regime, "float"],
        "seeds": seeds,
        "trajectories_identical": identical,
    }


def initial_state_provenance(pack: CountryPack, start: str) -> dict:
    coverage = pack.initial_states_coverage.get(start, {})
    counts: dict[str, int] = {"source": 0, "proxy": 0, "assumed": 0}
    by_kind: dict[str, list[str]] = {"source": [], "proxy": [], "assumed": []}
    for var, kind in sorted(coverage.items()):
        counts[kind] = counts.get(kind, 0) + 1
        by_kind.setdefault(kind, []).append(var)
    return {"counts": counts, "variables": by_kind, "n_variables": len(coverage)}


def build_registration(
    tests: list[ValidationTest], months_cap: int | None, calibration_run_id: str, seeds: int
) -> dict:
    """El registro que se escribe ANTES de correr nada (hipotesis, shocks
    forzados pedidos vs. efectivamente aplicables, procedencia del estado
    inicial). Ver docstring del modulo."""
    pack_dir = country_pack_dir("argentina")
    entries = []
    for test in tests:
        months = min(test.months, months_cap) if months_cap else test.months
        plan = resolve_forced_shocks(pack_dir, test, months)
        pack = _load_pack(test, months)
        entries.append(
            {
                "test_id": test.test_id,
                "title": test.title,
                "hypothesis": HYPOTHESES[test.test_id],
                "metric": METRICS[test.test_id],
                "adr_forced_shocks": ADR_FORCED_SHOCKS[test.test_id],
                "start": test.start,
                "months": months,
                "months_adr": test.months,
                "fx_regime": test.fx_regime,
                "forced_shocks_requested": plan.requested,
                "forced_shocks_applied": {str(k): v for k, v in sorted(plan.forced.items())},
                "initial_state_provenance": initial_state_provenance(pack, test.start),
                "random_shocks_enabled": True,
            }
        )
    return {
        "adr": "ADR 011 secc. 8 (A4)",
        "registered_before_running": True,
        "country": "argentina",
        "calibration_run_id": calibration_run_id,
        "seeds": seeds,
        "months_cap": months_cap,
        "arms": list(ARMS),
        "control_hypothesis": HYPOTHESES["C"],
        "control_metric": METRICS["C"],
        "honesty_sentence": HONESTY_SENTENCE,
        "tests": entries,
    }


def run_validation(
    out_dir: Path,
    *,
    seeds: int = 50,
    seed_base: int = 1,
    months_cap: int | None = None,
    calibration_run_id: str = "a3_main",
    test_ids: list[str] | None = None,
    resamples: int = 2000,
    make_plots: bool = True,
    progress=None,
) -> dict:
    """Corre A4 completo y escribe `registration.json`, `results.json`,
    `report.md` y `plots/` en `out_dir`."""
    tests = [TESTS_BY_ID[t] for t in (test_ids or [t.test_id for t in TESTS])]
    out_dir.mkdir(parents=True, exist_ok=True)

    registration = build_registration(tests, months_cap, calibration_run_id, seeds)
    (out_dir / "registration.json").write_text(
        json.dumps(registration, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    pack_dir = country_pack_dir("argentina")
    results: list[ValidationResult] = []
    t_start = time.perf_counter()
    for test in tests:
        months = min(test.months, months_cap) if months_cap else test.months
        plan = resolve_forced_shocks(pack_dir, test, months)
        pack = _load_pack(test, months)
        t0 = time.perf_counter()
        runs_by_arm: dict[str, list[SeedRun]] = {}
        for arm in ARMS:
            if progress:
                progress(f"{test.test_id} ({ARM_LABELS[arm]}) x{seeds} semillas")
            runs_by_arm[arm] = run_test_arm(
                test, arm, pack, plan, months, seeds, seed_base, calibration_run_id
            )
        all_dates = [month_date(test.start, i) for i in range(1, months + 1)]
        real = real_series_for(pack_dir, test, all_dates)
        metrics_by_arm = {}
        for arm, runs in runs_by_arm.items():
            if test.test_id == "V1":
                metrics_by_arm[arm] = metrics_v1(runs, months, resamples)
            elif test.test_id == "V2":
                metrics_by_arm[arm] = metrics_v2(runs, months, resamples, real)
            else:
                metrics_by_arm[arm] = metrics_v3(runs, months, resamples)
        diagnostics: dict = {}
        if test.fx_regime:
            if progress:
                progress(f"{test.test_id} (diagnóstico) fx-regime {test.fx_regime} vs float")
            diagnostics["fx_regime_inertness"] = fx_regime_inertness_check(
                test, pack, plan, months, calibration_run_id, seeds=min(3, seeds)
            )
        results.append(
            ValidationResult(
                test_id=test.test_id,
                months=months,
                plan=plan,
                runs_by_arm=runs_by_arm,
                metrics_by_arm=metrics_by_arm,
                real=real,
                wall_seconds=time.perf_counter() - t0,
                diagnostics=diagnostics,
            )
        )
    wall = time.perf_counter() - t_start

    plots: dict[str, str] = {}
    if make_plots:
        plots = write_plots(out_dir, results)

    payload = {
        "registration": registration,
        "wall_seconds": wall,
        "tests": [
            {
                "test_id": r.test_id,
                "months": r.months,
                "wall_seconds": r.wall_seconds,
                "metrics": r.metrics_by_arm,
                "diagnostics": r.diagnostics,
                "random_shocks_observed": {
                    arm: sorted({s for run in runs for s in run.random_shocks})
                    for arm, runs in r.runs_by_arm.items()
                },
            }
            for r in results
        ],
        "control_verdict": control_verdict(results),
        "inflation_persistence": inflation_persistence(),
        "honesty_sentence": HONESTY_SENTENCE,
    }
    (out_dir / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_report(out_dir, registration, results, wall, plots, calibration_run_id, seeds)
    return payload


def control_verdict(results: list[ValidationResult]) -> dict:
    """Fila C del ADR: "Aurora sin calibrar falla al menos una de las tres"."""
    failed = [r.test_id for r in results if not r.metrics_by_arm["aurora"]["passes"]]
    passed_calibrated = [r.test_id for r in results if r.metrics_by_arm["calibrated"]["passes"]]
    return {
        "aurora_failed_tests": failed,
        "calibrated_passed_tests": passed_calibrated,
        "passes": len(failed) >= 1,
    }


# --------------------------------------------------------------------------
# Graficos
# --------------------------------------------------------------------------


def _percentile(sorted_values: list[float], q: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo_i = int(pos)
    hi_i = min(lo_i + 1, len(sorted_values) - 1)
    frac = pos - lo_i
    return sorted_values[lo_i] * (1.0 - frac) + sorted_values[hi_i] * frac


def _quantile_bands(series: list[list[float]], months: int) -> tuple[list, list, list]:
    """Mediana e IQR mes a mes sobre las semillas VIVAS en ese mes (las
    corridas que terminaron antes -- `collapse`/`hyperinflation` -- dejan de
    contribuir: no se rellenan con su ultimo valor, que inventaria una
    trayectoria que el motor nunca simulo)."""
    med: list[float | None] = []
    lo: list[float | None] = []
    hi: list[float | None] = []
    for i in range(months):
        vals = sorted(s[i] for s in series if i < len(s))
        if not vals:
            med.append(None)
            lo.append(None)
            hi.append(None)
            continue
        med.append(_percentile(vals, 0.5))
        lo.append(_percentile(vals, 0.25))
        hi.append(_percentile(vals, 0.75))
    return med, lo, hi


def write_plots(out_dir: Path, results: list[ValidationResult]) -> dict[str, str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - extra `analysis` no instalado
        return {}

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    made: dict[str, str] = {}
    for res in results:
        test = TESTS_BY_ID[res.test_id]
        fig, ax = plt.subplots(figsize=(9, 5.2))
        x = list(range(1, res.months + 1))
        colors = {"calibrated": "#1f77b4", "aurora": "#ff7f0e"}
        for arm, runs in res.runs_by_arm.items():
            series = [model_series_for(test, r) for r in runs]
            med, lo, hi = _quantile_bands(series, res.months)
            xs = [xi for xi, m in zip(x, med, strict=False) if m is not None]
            ms = [m for m in med if m is not None]
            los = [v for v in lo if v is not None]
            his = [v for v in hi if v is not None]
            ax.plot(xs, ms, label=f"modelo {ARM_LABELS[arm]} (mediana)", color=colors[arm], lw=2)
            ax.fill_between(
                xs,
                los,
                his,
                alpha=0.18,
                color=colors[arm],
                label=f"IQR {ARM_LABELS[arm]} (semillas vivas)",
            )
        if res.real:
            dates = [month_date(test.start, i) for i in range(1, res.months + 1)]
            rx = [i + 1 for i, d in enumerate(dates) if d in res.real]
            ry = [res.real[d] for d in dates if d in res.real]
            ax.plot(rx, ry, color="black", ls="--", lw=2, label=f"real: {test.real_series_label}")
        ax.set_xlabel(f"mes de la corrida (1 = {test.start})")
        ax.set_ylabel(test.y_label)
        ax.set_title(f"{test.test_id} — {test.start} + {res.months} meses")
        if res.test_id in ("V1", "V3"):
            ax.set_yscale("symlog", linthresh=1)
        ax.grid(alpha=0.25)
        # Leyenda DEBAJO del eje: con escalas log y series que se cruzan,
        # cualquier `loc` de adentro tapaba una de las trayectorias.
        ax.legend(
            fontsize=7,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.16),
            ncol=3,
            frameon=False,
        )
        fig.tight_layout()
        name = f"{res.test_id.lower()}.png"
        fig.savefig(plots_dir / name, dpi=120)
        plt.close(fig)
        made[res.test_id] = f"plots/{name}"
    return made


# --------------------------------------------------------------------------
# Reporte
# --------------------------------------------------------------------------


def _fmt(value, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "sin dato"
    return f"{value:,.{digits}f}{suffix}".replace(",", " ")


def _fmt_ci(ci, digits: int = 2, suffix: str = "") -> str:
    lo, hi = ci
    if lo is None or hi is None:
        return "sin dato"
    return f"[{_fmt(lo, digits, suffix)}, {_fmt(hi, digits, suffix)}]"


def _fmt_pct(fraction, digits: int = 1) -> str:
    return "sin dato" if fraction is None else f"{fraction * 100:.{digits}f} %"


def _fmt_pct_ci(ci, digits: int = 1) -> str:
    lo, hi = ci
    if lo is None or hi is None:
        return "sin dato"
    return f"[{_fmt_pct(lo, digits)}, {_fmt_pct(hi, digits)}]"


def _verdict_plain(passes: bool) -> str:
    return "CUMPLIDA" if passes else "NO CUMPLIDA"


def _verdict(passes: bool) -> str:
    return f"**{_verdict_plain(passes)}**"


def _forced_shocks_block(entry: dict) -> list[str]:
    lines: list[str] = []
    lines.append(f"- Shocks forzados que pide el ADR: *{entry['adr_forced_shocks']}*.")
    if not entry["forced_shocks_requested"]:
        lines.append(
            "- Shocks forzados efectivamente aplicados: **ninguno** (el ADR no pide forzar "
            "ninguno en esta prueba)."
        )
    else:
        for req in entry["forced_shocks_requested"]:
            if req["matched"]:
                rows = "; ".join(
                    f"`{m['shock_id']}` {m['date']} (mes {m['month_index']}, "
                    f"duración {m['duration_months']} meses — {m['title']})"
                    for m in req["matched"]
                )
                lines.append(f"- `{req['label']}` → {rows}")
            else:
                lines.append(
                    f"- `{req['label']}` → **NO APLICADO**: `politics/shocks_calendar.csv` no "
                    f"tiene ninguna fila `{req['shock_id']}` en la ventana "
                    f"`{req['window']}`. No se inventa la fila "
                    "(PLAN_ARGENTINA.md §0.1); queda registrado como faltante."
                )
        applied = entry["forced_shocks_applied"]
        lines.append(
            f"- `forced_shocks` pasado al motor: `{applied if applied else '{}'}` "
            "(índice de mes → shock)."
        )
    lines.append(
        "- Además siguen activos los shocks **aleatorios** de `shocks.json` "
        "(`shocks_enabled=True`, igual que en cualquier `republica run`): la lista de forzados "
        "no es la lista de shocks que ocurrieron."
    )
    return lines


def _provenance_block(entry: dict) -> list[str]:
    prov = entry["initial_state_provenance"]
    counts = prov["counts"]
    lines = [
        f"- Estado inicial `{entry['start']}` ({prov['n_variables']} variables): "
        f"**{counts.get('source', 0)} `source`**, **{counts.get('proxy', 0)} `proxy`**, "
        f"**{counts.get('assumed', 0)} `assumed`**.",
    ]
    for kind in ("source", "proxy", "assumed"):
        names = prov["variables"].get(kind) or []
        if names:
            lines.append(f"  - `{kind}`: {', '.join(f'`{n}`' for n in names)}")
    return lines


def _comparison_table(results: list[ValidationResult]) -> list[str]:
    lines = [
        "| prueba | métrica principal | calibrado (`a3_main`) | Aurora sin calibrar | "
        "veredicto calibrado | veredicto Aurora |",
        "|---|---|---|---|---|---|",
    ]
    for res in results:
        cal = res.metrics_by_arm["calibrated"]
        aur = res.metrics_by_arm["aurora"]
        if res.test_id == "V1":
            label = "fracción de semillas en `hyperinflation`"
            cv = (
                f"{_fmt_pct(cal['hyperinflation_fraction'])} "
                f"IC95 {_fmt_pct_ci(cal['hyperinflation_fraction_ci'])}"
            )
            av = (
                f"{_fmt_pct(aur['hyperinflation_fraction'])} "
                f"IC95 {_fmt_pct_ci(aur['hyperinflation_fraction_ci'])}"
            )
        elif res.test_id == "V2":
            label = "fracción con `sovereign_default`/`collapse` en meses 36–54"
            cv = (
                f"{_fmt_pct(cal['default_or_collapse_fraction'])} "
                f"IC95 {_fmt_pct_ci(cal['default_or_collapse_fraction_ci'])}"
            )
            av = (
                f"{_fmt_pct(aur['default_or_collapse_fraction'])} "
                f"IC95 {_fmt_pct_ci(aur['default_or_collapse_fraction_ci'])}"
            )
        else:
            label = "mediana de la inflación anualizada final (umbral 80 %)"
            cv = (
                f"{_fmt(cal['inflation_annual_final_median'], 1, ' %')} "
                f"IC95 {_fmt_ci(cal['inflation_annual_final_ci'], 1, ' %')}"
            )
            av = (
                f"{_fmt(aur['inflation_annual_final_median'], 1, ' %')} "
                f"IC95 {_fmt_ci(aur['inflation_annual_final_ci'], 1, ' %')}"
            )
        lines.append(
            f"| {res.test_id} | {label} | {cv} | {av} | "
            f"{_verdict(cal['passes'])} | {_verdict(aur['passes'])} |"
        )
    return lines


def _test_section(res: ValidationResult, entry: dict, plot: str | None) -> list[str]:
    test = TESTS_BY_ID[res.test_id]
    cal = res.metrics_by_arm["calibrated"]
    aur = res.metrics_by_arm["aurora"]
    lines = [
        f"## {test.title}",
        "",
        f"**Hipótesis registrada antes de correr (ADR 011 §8, literal):** *{entry['hypothesis']}*",
        "",
        f"**Métrica (ADR 011 §8, literal):** *{entry['metric']}*",
        "",
        f"Corrida: `--country argentina --start {test.start}` × "
        f"{entry['months']} meses × {len(res.runs_by_arm['calibrated'])} semillas por brazo"
        + (f", `--fx-regime {test.fx_regime}`" if test.fx_regime else "")
        + ", `--historical-exogenous`, `--regime-mode auto`, política `passive`.",
        "",
        "### Shocks forzados",
        "",
    ]
    lines += _forced_shocks_block(entry)
    lines += ["", "### Procedencia del estado inicial", ""]
    lines += _provenance_block(entry)
    lines += ["", "### Resultado", ""]

    if res.test_id == "V1":
        lines += [
            "| brazo | fracción en `hyperinflation` | IC95 (bootstrap sobre semillas) | "
            "mes mediano | inflación mensual final (mediana) | outcomes |",
            "|---|---|---|---|---|---|",
        ]
        for arm, m in (("calibrated", cal), ("aurora", aur)):
            lines.append(
                f"| {ARM_LABELS[arm]} | {_fmt_pct(m['hyperinflation_fraction'])} | "
                f"{_fmt_pct_ci(m['hyperinflation_fraction_ci'])} | "
                f"{_fmt(m['hyperinflation_median_month'], 1)} | "
                f"{_fmt(m['inflation_monthly_final_median'], 2, ' %')} | "
                f"{m['outcomes']} |"
            )
    elif res.test_id == "V2":
        lines += [
            "| brazo | fracción `sovereign_default`/`collapse` en meses "
            + (
                "36–54 (ventana VACÍA con `--months-cap`)"
                if cal.get("window_empty")
                else f"{cal['window_months'][0]}–{cal['window_months'][1]}"
            )
            + " | IC95 | RMSE reservas vs real (USD M, mediana) | IC95 | outcomes |",
            "|---|---|---|---|---|---|",
        ]
        for arm, m in (("calibrated", cal), ("aurora", aur)):
            lines.append(
                f"| {ARM_LABELS[arm]} | {_fmt_pct(m['default_or_collapse_fraction'])} | "
                f"{_fmt_pct_ci(m['default_or_collapse_fraction_ci'])} | "
                f"{_fmt(m['reserves_rmse_median'], 0)} | "
                f"{_fmt_ci(m['reserves_rmse_ci'], 0)} | {m['outcomes']} |"
            )
        lines += [
            "",
            "Baseline ingenuo de reservas (persistencia: reservas reales congeladas en el nivel "
            f"real de {test.start}): RMSE {_fmt(cal['reserves_rmse_persistence'], 0)} USD M.",
        ]
    else:
        lines += [
            "| brazo | inflación anualizada final (mediana) | IC95 | meses simulados (mediana) "
            "| outcomes |",
            "|---|---|---|---|---|",
        ]
        for arm, m in (("calibrated", cal), ("aurora", aur)):
            lines.append(
                f"| {ARM_LABELS[arm]} | {_fmt(m['inflation_annual_final_median'], 1, ' %')} | "
                f"{_fmt_ci(m['inflation_annual_final_ci'], 1, ' %')} | "
                f"{_fmt(m['median_months_run'], 0)} | {m['outcomes']} |"
            )
        lines += [
            "",
            "| elección | resultado real | brazo | semillas en que la elección ocurrió | "
            "aciertos | IC95 |",
            "|---|---|---|---|---|---|",
        ]
        for date in V3_REAL_ELECTIONS:
            for arm, m in (("calibrated", cal), ("aurora", aur)):
                e = m["elections"][date]
                lines.append(
                    f"| {date} | oficialismo derrotado | {ARM_LABELS[arm]} | "
                    f"{e['n_held']} | {_fmt_pct(e['hit_fraction'])} | "
                    f"{_fmt_pct_ci(e['hit_fraction_ci'])} |"
                )

    lines += [
        "",
        f"**Veredicto (calibrado): {_verdict_plain(cal['passes'])}.** "
        f"**Veredicto (Aurora sin calibrar): {_verdict_plain(aur['passes'])}.**",
        "",
    ]
    if plot:
        lines += [
            f"![{res.test_id}]({plot})",
            "",
            "*Trayectoria mediana con banda intercuartil por brazo contra "
            f"{test.real_series_label}. "
            "La banda se calcula solo sobre las semillas VIVAS en cada mes: una corrida terminada "
            "por `collapse`/`hyperinflation` deja de contribuir en vez de repetir su "
            "último valor.*",
            "",
        ]
    return lines


def _v2_rmse_note(results: list[ValidationResult]) -> str:
    v2 = next((r for r in results if r.test_id == "V2"), None)
    if not v2:
        return "sin dato"
    c = v2.metrics_by_arm["calibrated"]
    a = v2.metrics_by_arm["aurora"]
    cal, aur, base = (
        c["reserves_rmse_median"],
        a["reserves_rmse_median"],
        c["reserves_rmse_persistence"],
    )
    if cal is None or aur is None or not base:
        return "sin dato"
    return (
        f"{(1 - cal / aur) * 100:.1f} % respecto de Aurora y {(1 - cal / base) * 100:.1f} % "
        "respecto del baseline ingenuo de persistencia"
    )


def _v2_reserves_range(v2: ValidationResult) -> str:
    runs = v2.runs_by_arm["calibrated"]
    first = statistics.median([r.reserves[0] for r in runs])
    last = statistics.median([r.reserves[-1] for r in runs])
    return f"mediana {first:,.0f} → {last:,.0f} USD M".replace(",", " ")


def _v3_election_note(results: list[ValidationResult]) -> str:
    v3 = next((r for r in results if r.test_id == "V3"), None)
    if not v3:
        return "sin dato"
    c = v3.metrics_by_arm["calibrated"]["elections"]["2019-12"]["hit_fraction"]
    a = v3.metrics_by_arm["aurora"]["elections"]["2019-12"]["hit_fraction"]
    return (
        f"el acierto de la elección de 2019 pasa de {_fmt_pct(a)} a {_fmt_pct(c)} de las semillas"
    )


def _v3_collapse_note(results: list[ValidationResult]) -> str:
    v3 = next((r for r in results if r.test_id == "V3"), None)
    if not v3:
        return "sin dato"
    m = v3.metrics_by_arm["calibrated"]
    total = sum(m["outcomes"].values())
    n = m["outcomes"].get("collapse", 0)
    return (
        f"{n} de {total} semillas calibradas de V3 terminan en `collapse` antes del mes "
        f"{v3.months} y la elección de 2023 se celebra en "
        f"{m['elections']['2023-12']['n_held']} de {total}"
    )


def _value_of_calibration_table(results: list[ValidationResult]) -> list[str]:
    """Fila C del ADR 011 secc. 8: "la diferencia con el calibrado es el
    'valor' de la calibracion". Se compara metrica por metrica contra el
    dato historico (columna `real`), porque ningun brazo cumple ninguna
    hipotesis y comparar veredictos no distinguiria nada."""
    by_id = {r.test_id: r for r in results}
    rows: list[tuple[str, str, float | None, float | None, float | None, bool]] = []
    v1 = by_id.get("V1")
    if v1:
        c, a = v1.metrics_by_arm["calibrated"], v1.metrics_by_arm["aurora"]
        rows.append(
            (
                "V1",
                "fracción de semillas en `hyperinflation` (%)",
                100.0,
                c["hyperinflation_fraction"] * 100.0,
                a["hyperinflation_fraction"] * 100.0,
                False,
            )
        )
        rows.append(
            (
                "V1",
                "inflación mensual al mes 24 (%) — real jul-1989 ≈ 33 %/mes",
                33.0,
                c["inflation_monthly_final_median"],
                a["inflation_monthly_final_median"],
                False,
            )
        )
    v2 = by_id.get("V2")
    if v2:
        c, a = v2.metrics_by_arm["calibrated"], v2.metrics_by_arm["aurora"]
        rows.append(
            (
                "V2",
                "fracción con `sovereign_default`/`collapse` en meses 36–54 (%)",
                100.0,
                c["default_or_collapse_fraction"] * 100.0,
                a["default_or_collapse_fraction"] * 100.0,
                False,
            )
        )
        rows.append(
            (
                "V2",
                "RMSE de reservas vs real (USD M; baseline persistencia "
                f"{_fmt(c['reserves_rmse_persistence'], 0)})",
                0.0,
                c["reserves_rmse_median"],
                a["reserves_rmse_median"],
                False,
            )
        )
    v3 = by_id.get("V3")
    if v3:
        c, a = v3.metrics_by_arm["calibrated"], v3.metrics_by_arm["aurora"]
        rows.append(
            (
                "V3",
                "inflación anualizada final (%) — real 2023: 135 % (BM)",
                135.0,
                c["inflation_annual_final_median"],
                a["inflation_annual_final_median"],
                False,
            )
        )
        for date in V3_REAL_ELECTIONS:
            rows.append(
                (
                    "V3",
                    f"acierto electoral {date} (oficialismo derrotado, % de semillas)",
                    100.0,
                    c["elections"][date]["hit_fraction"] * 100.0,
                    a["elections"][date]["hit_fraction"] * 100.0,
                    True,
                )
            )

        def _survival(m: dict) -> float:
            total = max(1, sum(m["outcomes"].values()))
            return 100.0 * (1.0 - m["outcomes"].get("collapse", 0) / total)

        rows.append(
            (
                "V3",
                "semillas que llegan al mes 96 sin `collapse` (%)",
                100.0,
                _survival(c),
                _survival(a),
                False,
            )
        )

    lines = [
        "| prueba | métrica | real | calibrado (`a3_main`) | Aurora sin calibrar | más cerca "
        "de la historia |",
        "|---|---|---|---|---|---|",
    ]
    for test_id, label, real, cal, aur, _is_pct in rows:
        if cal is None or aur is None or real is None:
            winner = "sin dato"
        elif abs(cal - real) < abs(aur - real):
            winner = "**calibrado**"
        elif abs(aur - real) < abs(cal - real):
            winner = "**Aurora**"
        else:
            winner = "empate"
        lines.append(
            f"| {test_id} | {label} | {_fmt(real, 1)} | {_fmt(cal, 1)} | {_fmt(aur, 1)} | "
            f"{winner} |"
        )
    return lines


def write_report(
    out_dir: Path,
    registration: dict,
    results: list[ValidationResult],
    wall_seconds: float,
    plots: dict[str, str],
    calibration_run_id: str,
    seeds: int,
) -> Path:
    entries = {e["test_id"]: e for e in registration["tests"]}
    control = control_verdict(results)
    lines: list[str] = [
        "# Validación histórica de Argentina (A4) — ADR 011 §8",
        "",
        f"País: `argentina`. Calibración: `{calibration_run_id}` (A3, train `1993-01:2015-12`, "
        "holdout `2016-01:2023-12`). Brazos: calibrado y **Aurora sin calibrar** (fila C del ADR).",
        f"Semillas por prueba y brazo: **{seeds}**. Tiempo de pared total: "
        f"**{wall_seconds:.1f} s** "
        f"({', '.join(f'{r.test_id} {r.wall_seconds:.1f} s' for r in results)}).",
        "",
        "Las hipótesis, los shocks forzados y la procedencia del estado inicial se registraron "
        "en `registration.json` **antes** de correr la primera simulación; este reporte solo "
        "las lee. Métricas crudas por prueba y brazo: `results.json`.",
        "",
        "## Resumen: los cuatro veredictos",
        "",
    ]
    lines += _comparison_table(results)
    lines += [
        "",
        f"**C Control.** Hipótesis registrada (ADR 011 §8, literal): *{HYPOTHESES['C']}*. "
        f"Métrica: *{METRICS['C']}*. Aurora sin calibrar falla "
        f"{len(control['aurora_failed_tests'])} de {len(results)} pruebas "
        f"({', '.join(control['aurora_failed_tests']) or 'ninguna'}): "
        f"{_verdict(control['passes'])}.",
        "",
        '### El "valor" de la calibración (fila C del ADR)',
        "",
        "Ninguno de los dos brazos cumple ninguna de las tres hipótesis, así que la fila C se "
        "decide por la distancia a la historia métrica por métrica, no por veredictos. La "
        "columna «real» es el dato histórico correspondiente y la última marca el brazo más "
        "cercano a ese dato.",
        "",
    ]
    lines += _value_of_calibration_table(results)
    lines += [
        "",
        "Leído en conjunto: **la calibración de A3 casi no compró nada en el bloque "
        "económico** (V1 y V3 quedan más lejos de la historia que Aurora sin calibrar; en V2 "
        f"el RMSE de reservas mejora {_v2_rmse_note(results)}) **y compró mucho en el bloque "
        f"político**: {_v3_election_note(results)}. El precio de ese mismo ajuste político es "
        f"que {_v3_collapse_note(results)}.",
        "",
    ]
    for res in results:
        lines += _test_section(res, entries[res.test_id], plots.get(res.test_id))

    lines += _lessons_section(results)
    lines += _cannot_conclude_section(results)
    lines += [
        "## Limitaciones",
        "",
        f"> {HONESTY_SENTENCE}",
        "",
    ]
    text = "\n".join(lines)
    path = out_dir / "report.md"
    path.write_text(text, encoding="utf-8")
    return path


def _lessons_section(results: list[ValidationResult]) -> list[str]:
    """Explicacion MECANICA de por que el modelo reprodujo (o no) cada
    episodio. Los numeros que se citan salen de los coeficientes en disco
    (`country.json` vs `calibration/a3_main/coefficients.json`) y de las
    ecuaciones de `world/economy.py`, no de la narrativa del resultado."""
    by_id = {r.test_id: r for r in results}
    persist = inflation_persistence()
    lines = ["## Qué aprendimos del modelo", "", "### V1 — por qué NO hay hiperinflación", ""]
    v1 = by_id.get("V1")
    if v1:
        cal = v1.metrics_by_arm["calibrated"]
        aur = v1.metrics_by_arm["aurora"]
        lines += [
            "La ecuación de inflación de `world/economy.py::step_economy` (§4.3) es "
            "`π_{t+1} = ρ_π·π_t + c_e·de_t + c_g·demand_gap + c_f·pos(déficit−2) − c_r·r_gap/100`, "
            "y el tipo de cambio (§4.2) es `de_t ≈ π_t − π_mundo + b_res·reserves_gap − "
            "b_r·r_gap/100 + b_conf·(...)`. Sustituyendo, **el coeficiente total sobre la "
            "inflación del mes anterior es `ρ_π + c_e`**: "
            f"{persist['aurora_rho_pi']:.3f} + {persist['aurora_c_e']:.3f} = "
            f"**{persist['aurora_total']:.3f}** en Aurora y "
            f"{persist.get('calibrated_rho_pi', float('nan')):.3f} + "
            f"{persist.get('calibrated_c_e', float('nan')):.3f} = "
            f"**{persist.get('calibrated_total', float('nan')):.3f}** con los coeficientes "
            "calibrados. Los dos son < 1, así que "
            "la ecuación es una *contracción*: desde cualquier estado inicial la inflación "
            "converge monótonamente a un punto fijo en vez de explotar. Una hiperinflación "
            "endógena es **algebraicamente imposible** en este motor sin un `shock_pi` grande y "
            "sostenido; el único camino al `outcome = hyperinflation` (π > 20 %/mes tres meses "
            "seguidos) es forzar un shock — exactamente lo que el ADR prohíbe en V1.",
            "",
            "Empíricamente: arrancando de 13.99 %/mes real de 1988-06, la inflación mensual "
            f"mediana al mes {v1.months} es "
            f"{_fmt(cal['inflation_monthly_final_median'], 2, ' %')} "
            f"(calibrado) y {_fmt(aur['inflation_monthly_final_median'], 2, ' %')} (Aurora); "
            "la real de 1989 fue ~33 %/mes (3046 % anual, Banco Mundial). El término que domina "
            "no es ninguno de los canales de crisis: es la **reversión a la media de la propia "
            "inercia inflacionaria**, con `de` siguiendo pasivamente a π y `r_gap` clavado cerca "
            "de 0 porque `PassivePolicy` ajusta la tasa nominal para sostener la tasa real "
            "neutral (r_real ≈ 6 %, r_gap ≈ 2 en el mes 1) — es decir, el modelo supone un banco "
            "central que indexa la tasa a la inflación, lo contrario de la Argentina de 1988.",
            "",
            "**La calibración empeora esto.** A3 movió `ρ_π` de "
            f"{persist['aurora_rho_pi']:.3f} a "
            f"{persist.get('calibrated_rho_pi', float('nan')):.3f} (el mayor cambio "
            "estructural de todo el vector), porque se ajustó sobre 1993–2015: convertibilidad "
            "más post-2003, un período en el que la inflación mensual *es* fuertemente reversiva. "
            "El resultado es un modelo que revierte todavía más rápido y queda todavía más "
            "lejos de 1989: ninguno de los dos brazos llega a `hyperinflation` "
            f"({_fmt_pct(cal['hyperinflation_fraction'])} de semillas calibradas y "
            f"{_fmt_pct(aur['hyperinflation_fraction'])} de Aurora), pero el calibrado termina "
            f"en {_fmt(cal['inflation_monthly_final_median'], 2, ' %')}/mes contra "
            f"{_fmt(aur['inflation_monthly_final_median'], 2, ' %')}/mes de Aurora, con la "
            "real en ~33 %/mes. Es el mismo sobreajuste que el reporte de A3 ya había "
            "detectado en el "
            "holdout de inflación (RMSE normalizado 1.26 calibrado vs 0.71 persistencia a 12 "
            "meses), visto desde otro ángulo.",
            "",
        ]
    lines += ["### V2 — por qué el peg no hace caer las reservas", ""]
    v2 = by_id.get("V2")
    if v2:
        cal = v2.metrics_by_arm["calibrated"]
        inert = v2.diagnostics.get("fx_regime_inertness", {})
        verdict = (
            "idénticas estado a estado con la misma semilla"
            if inert.get("trajectories_identical")
            else "NO idénticas (ver `results.json`)"
        )
        lines += [
            "**`--fx-regime peg` es inerte en esta implementación.** `fx_regime` solo se lee en "
            "un lugar del motor, `world/bimonetary.py::step_bimonetary`, y solo para decidir si "
            '`fx_gap > 0` (`fx_regime == "control"`). No entra en `step_economy`: no fija `de`, '
            "no obliga a intervenir, no consume reservas. El ADR 011 §5 decía que «la "
            "convertibilidad es `peg` con `fx_intervention = 1` y `k_k` alto mientras haya "
            "reservas», y eso **no se implementó** en A2. Verificado empíricamente en esta "
            f"corrida ({inert.get('seeds', 0)} semillas, diagnóstico `fx_regime_inertness` de "
            f"`results.json`): las trayectorias con `--fx-regime peg` y con `--fx-regime float` "
            f"son {verdict}. La pregunta «¿colapsa con convertibilidad rígida?» no "
            "se puede responder porque el modelo no tiene convertibilidad.",
            "",
            "Tampoco hay realimentación del bloque bimonetario hacia el núcleo: el ADR 011 §5 "
            "pedía `de_raw += x_d · dollar_demand`, y ese término no existe en `world/economy.py`. "
            "`dollar_demand`, `fx_gap`, `external_debt_usd` y `default_risk` se calculan "
            "*después* de `advance_month` y nunca vuelven a entrar en las 20 variables. El bloque "
            "externo es hoy un **lector**, no un mecanismo.",
            "",
            "Las reservas (§4.7) son "
            "`R_{t+1} = R_t + k_tb·(commodity−100) + k_w·(wd−100) + k_k·clamp(r_gap) − "
            "k_conf·pos(conf_neutral−conf) − intervención`: una **caminata con deriva, sin ancla "
            "de nivel**. `reserves_target` (10 000 USD M, valor de Aurora) solo entra vía "
            "`reserves_gap = pos(target − R)/target`, que con las reservas reales de 1998 "
            "(27 914 USD M) vale **0 todos los meses**: no hay ningún término que empuje las "
            "reservas hacia abajo cuando están «altas». Con `r_gap ≈ 2` sostenido por "
            "`PassivePolicy`, `k_k·r_gap ≈ +24 USD M/mes` es deriva positiva. Por eso el modelo "
            f"deja las reservas casi planas ({_v2_reserves_range(v2)}) mientras la serie real "
            "cae de 27 914 (1998-01) a ~10 000 (2002-06): RMSE mediano "
            f"{_fmt(cal['reserves_rmse_median'], 0)} USD M contra "
            f"{_fmt(cal['reserves_rmse_persistence'], 0)} USD M del baseline ingenuo de "
            "congelar el nivel real de 1998-01 — es decir, después de calibrar 107 "
            "coeficientes el modelo describe la caída de las reservas de la convertibilidad "
            "apenas mejor que suponer que no pasó nada.",
            "",
            "Y el `sovereign_default` endógeno nunca se dispara: `default_risk = "
            "0.55·pos(deuda/reservas − 1) + 0.011·pos(déficit)` se queda en ~0.03–0.10 contra un "
            "umbral de 0.54, justamente porque las reservas no caen. El canal existe, pero su "
            "entrada nunca se mueve.",
            "",
        ]
    lines += ["### V3 — la inflación no se acelera, pero el modelo sí castiga al oficialismo", ""]
    v3 = by_id.get("V3")
    if v3:
        cal = v3.metrics_by_arm["calibrated"]
        aur = v3.metrics_by_arm["aurora"]
        applied = (
            ", ".join(f"`{row['shock_id']}` {row['date']}" for row in v3.plan.applied_rows)
            or "ninguno"
        )
        v3_runs = v3.runs_by_arm["calibrated"]
        appr0 = statistics.median([r.government_approval[0] for r in v3_runs])
        appr_last = statistics.median([r.government_approval[-1] for r in v3_runs])
        n_collapse = cal["outcomes"].get("collapse", 0)
        end_date = month_date("2016-01", int(cal["median_months_run"]))
        lines += [
            "Mismo mecanismo que V1 por el lado de los precios: con `ρ_π + c_e = "
            f"{persist.get('calibrated_total', float('nan')):.2f}` la "
            f"inflación no puede acelerarse sola, y los shocks que sí se aplicaron ({applied}) "
            "son shocks de **actividad y fiscales**, no "
            "de precios. La mediana de inflación anualizada final es "
            f"{_fmt(cal['inflation_annual_final_median'], 1, ' %')} (calibrado) y "
            f"{_fmt(aur['inflation_annual_final_median'], 1, ' %')} (Aurora) contra 135 % anual "
            "real en 2023 (Banco Mundial; ~211 % diciembre contra diciembre según INDEC). Otra "
            "vez la calibración se aleja más de la historia que Aurora.",
            "",
            "**Lo que sí funciona es el castigo electoral.** En 2019-12 (mes 48, el múltiplo de "
            "`term_length` que el motor usa; no la fecha real de octubre) el oficialismo pierde "
            f"en {_fmt_pct(cal['elections']['2019-12']['hit_fraction'])} de las semillas "
            f"calibradas contra {_fmt_pct(aur['elections']['2019-12']['hit_fraction'])} en "
            "Aurora, y no por la inflación sino por el canal aprobación→cohortes→voto: la "
            f"aprobación de gobierno (mediana) cae de {appr0:.0f} en 2016-01 a "
            f"{appr_last:.0f} al final de la corrida, arrastrada por "
            "`social_tension` creciente y `protest_level` alto, y las cohortes votan contra el "
            "oficialismo. Es el resultado del que más se puede decir que el modelo «acertó».",
            "",
            "El precio de ese mismo canal es que **la corrida calibrada casi no llega a 2023**: "
            "la espiral aprobación↓ → tensión↑ → estabilidad↓ cruza el umbral terminal "
            "(`political_stability < 15` tres meses seguidos) alrededor del mes "
            f"{_fmt(cal['median_months_run'], 0)} (mediana), es decir {end_date}, y la "
            f"simulación termina en `collapse` en {n_collapse} de "
            f"{sum(cal['outcomes'].values())} semillas. Donde hay `collapse` la elección de 2023 "
            "nunca ocurre, así que ese «acierto electoral» mide supervivencia, no elección del "
            f"ganador: la elección de 2023-12 se celebró en "
            f"{cal['elections']['2023-12']['n_held']} de {sum(cal['outcomes'].values())} "
            "semillas calibradas y en "
            f"{aur['elections']['2023-12']['n_held']} de {sum(aur['outcomes'].values())} de "
            f"Aurora, que acierta 2023 en "
            f"{_fmt_pct(aur['elections']['2023-12']['hit_fraction'])} de las semillas.",
            "",
        ]
    lines += [
        "### Lo transversal",
        "",
        "Los tres episodios que definen la macro argentina —hiperinflación, corrida con tipo de "
        "cambio fijo y default— dependen de **no linealidades y de restricciones de balance** "
        "(indexación explosiva, una regla cambiaria que se rompe, un stock de reservas que se "
        "agota) que este motor no tiene: sus 20 variables se mueven con ecuaciones lineales, "
        "estables y con reversión a la media, y los únicos saltos discretos son los shocks del "
        "catálogo, que hay que forzar desde afuera. Calibrar los ~107 coeficientes sobre "
        "1993–2015 no cambia esa arquitectura: mueve el punto fijo, no la estabilidad del "
        "sistema. Lo que el modelo sí reproduce es **dinámica política lenta**: desgaste de "
        "aprobación, tensión social acumulada y alternancia electoral.",
        "",
    ]
    return lines


def _cannot_conclude_section(results: list[ValidationResult]) -> list[str]:
    by_id: dict[str, ValidationResult] = {r.test_id: r for r in results}
    lines = [
        "## Qué NO se puede concluir",
        "",
        "1. **Nada sobre la Argentina real.** Estas corridas dicen cómo se comporta un motor de "
        "20 ecuaciones con coeficientes ajustados a series argentinas. Una hipótesis NO CUMPLIDA "
        "es evidencia sobre el modelo, no sobre la historia.",
        "2. **Que «el modelo no puede tener hiperinflación» sea un hecho sobre la inflación "
        "argentina.** Es un hecho sobre `ρ_π + c_e < 1` en `world/economy.py`, una propiedad de "
        "la especificación elegida en Aurora (ADR 001/002) y heredada sin revisión por el "
        "paquete de país.",
        "3. **Que la convertibilidad «no importaba».** V2 no testeó la convertibilidad: "
        "`--fx-regime peg` no tiene ningún efecto en el motor de hoy (verificado: `peg` y "
        "`float` dan trayectorias idénticas). El resultado de V2 es un resultado sobre un "
        "régimen de flotación con el estado inicial de 1998.",
    ]
    v2 = by_id.get("V2")
    if v2 and v2.plan.unmatched:
        lines.append(
            "4. **Que el modelo «no reprodujo 2001 pese a la crisis rusa/brasileña».** Esa crisis "
            "**no se aplicó**: `politics/shocks_calendar.csv` (dato de A1) no tiene ninguna fila "
            "entre 1995-01 y 2003-01 — ni la crisis internacional de 1998–99 que pide el ADR, ni "
            "el corralito/default de diciembre de 2001 que `PLAN_ARGENTINA.md` §1 lista como "
            "shock histórico. No se agregó la fila para que la prueba «diera» "
            "(PLAN_ARGENTINA.md §0.1): V2 corrió con cero shocks forzados y eso es lo que mide."
        )
    else:
        lines.append(
            "4. **Que los shocks forzados expliquen el resultado.** Los forzados están listados "
            "prueba por prueba arriba; un episodio reproducido en un mes con shock forzado no es "
            "mérito de la dinámica interna."
        )
    lines += [
        "5. **Que el modelo «falle» la elección de 2023 en el brazo calibrado.** En las "
        "semillas que terminan en `collapse` antes del mes 96 la elección no llega a ocurrir: "
        "ese acierto mide supervivencia, no capacidad predictiva electoral.",
        "6. **Que las elecciones del modelo sean las elecciones reales.** El motor las pone en "
        "múltiplos de `term_length` desde `--start` (2019-12 y 2023-12), no en octubre de 2019 y "
        "2023, y no tiene noción de qué partido sintético corresponde a qué lista real: se "
        "compara sólo `reelected`/`defeated` (misma simplificación declarada en A3).",
        "7. **Que estos números se generalicen a otras semillas o ventanas.** Los IC 95 % son "
        "bootstrap sobre las semillas de ESTA corrida: cubren la variabilidad de Monte Carlo, no "
        "la incertidumbre del estado inicial (con 9–15 de 21 variables `assumed`), ni la de los "
        "coeficientes, ni la del calendario de shocks.",
        "8. **Que un `collapse` del motor sea «una crisis argentina».** `collapse` es "
        "`political_stability < 15` durante 3 meses, un umbral de diseño de Aurora sin "
        "calibración contra ningún evento histórico.",
        "",
    ]
    return lines
