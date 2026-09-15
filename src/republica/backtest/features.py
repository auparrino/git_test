"""Caracteristicas candidatas de una ventana (ADR 014 secc. 3).

`compute_window_features(window, calibration_run_id)` devuelve un `dict`
plano (listo para una fila de `windows.csv`) con las seis columnas del ADR:
Datos, Regimen, Economia, Politica, Shocks, Modelo. Todo lo que se puede
leer sin correr ninguna simulacion (la unica excepcion de verdad es
`in_sample`, que depende de `calibration_run_id`; `iqr_seeds` -- la unica
caracteristica que depende de los RESULTADOS de una corrida -- se calcula
aparte, en `scoring.py`, y se agrega a la fila ahi).

Todas las series reales se leen de `data/countries/argentina/history/` y
`politics/` -- las mismas fuentes que ya usa `calibration/initial_states.py`
y `validation/argentina.py`, sin inventar ningun numero nuevo
(PLAN_ARGENTINA.md #0.1)."""

from __future__ import annotations

import csv
import functools
import json

from republica.backtest.windows import Window
from republica.calibration.initial_states import initial_state_for
from republica.world.countries import country_pack_dir
from republica.world.eras import list_eras, load_era_parties
from republica.world.regime import load_coup_dates

PACK_DIR = country_pack_dir("argentina")
HISTORY_DIR = PACK_DIR / "history"
POLITICS_DIR = PACK_DIR / "politics"

#: Tramos de inflacion mensual, ADR 014 secc. 3 literal.
INFLATION_BUCKET_EDGES: tuple[tuple[float, str], ...] = (
    (1.0, "<1"),
    (3.0, "1-3"),
    (10.0, "3-10"),
    (float("inf"), ">10"),
)


def inflation_bucket(pct: float | None) -> str | None:
    if pct is None:
        return None
    for edge, label in INFLATION_BUCKET_EDGES:
        if pct < edge:
            return label
    return ">10"


def _provenance_kind(prov: dict) -> str:
    """Mismo criterio que `world/countries.py::_provenance_kind`
    (funcion privada de ese modulo, no importada a proposito: evita
    acoplarse a un simbolo `_`-prefijado de un archivo que este paquete no
    edita)."""
    if prov.get("assumed"):
        return "assumed"
    if "source" in prov:
        return "source"
    if "proxy" in prov:
        return "proxy"
    return "?"


@functools.lru_cache(maxsize=8)
def _load_annual_series(name: str) -> dict[int, float]:
    path = HISTORY_DIR / f"{name}.csv"
    out: dict[int, float] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out[int(row["date"][:4])] = float(row["value"])
            except (ValueError, KeyError):
                continue
    return out


@functools.lru_cache(maxsize=8)
def _load_monthly_series(name: str) -> dict[tuple[int, int], float]:
    path = HISTORY_DIR / f"{name}.csv"
    out: dict[tuple[int, int], float] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                y, m = int(row["date"][:4]), int(row["date"][5:7])
                out[(y, m)] = float(row["value"])
            except (ValueError, KeyError):
                continue
    return out


@functools.lru_cache(maxsize=1)
def _load_events() -> list[dict]:
    path = POLITICS_DIR / "events.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@functools.lru_cache(maxsize=1)
def _load_regimes_by_year() -> dict[int, str]:
    path = POLITICS_DIR / "regimes.csv"
    out: dict[int, str] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            out[int(row["year"])] = row["regime_mode"]
    return out


@functools.lru_cache(maxsize=1)
def _load_coup_dates() -> list[tuple[int, int]]:
    return sorted(load_coup_dates(POLITICS_DIR / "events.csv"))


@functools.lru_cache(maxsize=1)
def _load_default_dates() -> list[tuple[int, int]]:
    return sorted(
        (int(row["date"][:4]), int(row["date"][5:7]))
        for row in _load_events()
        if row.get("kind") == "default"
    )


@functools.lru_cache(maxsize=1)
def _load_election_dates() -> list[tuple[int, int]]:
    return sorted(
        (int(row["date"][:4]), int(row["date"][5:7]))
        for row in _load_events()
        if row.get("kind") == "election_presidential"
    )


def real_inflation_monthly_equiv(y: int, m: int) -> float | None:
    """Serie combinada de inflacion mensual, misma logica que
    `validation/argentina.py::real_series_for(..., "inflation_monthly_implied")`
    para V1: IPC MENSUAL real si existe (desde 1997-02), si no la variacion
    ANUAL (`inflation_cpi_annual_linked`, cubre 1915-2023) convertida a
    mensual equivalente `(1+a/100)^(1/12) - 1) * 100` -- un proxy DERIVADO
    para los años sin serie mensual, declarado como tal."""
    monthly = _load_monthly_series("inflation_cpi_monthly").get((y, m))
    if monthly is not None:
        return monthly
    annual = _load_annual_series("inflation_cpi_annual_linked").get(y)
    if annual is None:
        return None
    return ((1.0 + annual / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0


def decade_inflation_std(year: int) -> float:
    decade = (year // 10) * 10
    values = []
    for y in range(decade, decade + 10):
        for m in range(1, 13):
            v = real_inflation_monthly_equiv(y, m)
            if v is not None:
                values.append(v)
    if len(values) < 2:
        return 1.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return var**0.5 or 1.0


def _years_since(year: int, month: int, dates: list[tuple[int, int]]) -> float | None:
    """Años (fraccion) desde el evento mas reciente en `dates` con
    `(y, m) <= (year, month)`, `None` si no hay ninguno anterior."""
    before = [d for d in dates if d <= (year, month)]
    if not before:
        return None
    ly, lm = max(before)
    return (year - ly) + (month - lm) / 12.0


def months_to_next_election(t0: str) -> int | None:
    y0, m0 = int(t0[:4]), int(t0[5:7])
    future = [(y, m) for y, m in _load_election_dates() if (y, m) >= (y0, m0)]
    if not future:
        return None
    y, m = min(future)
    return (y - y0) * 12 + (m - m0)


def herfindahl_seats(era_id: str | None) -> float | None:
    """Herfindahl de bancas (suma de `(seats_share)^2`) de la epoca
    (ADR 013 secc. 2), `None` sin epoca (fallback a Aurora: los 5 partidos
    fijos de Aurora no traen `seats` reales por epoca, no corresponde
    calcular este indice para ellos)."""
    if era_id is None:
        return None
    for era in list_eras("argentina"):
        if era.id == era_id:
            parties = load_era_parties(era)
            total = sum(float(p.get("seats", 0) or 0) for p in parties)
            if total <= 0:
                return None
            return sum((float(p.get("seats", 0) or 0) / total) ** 2 for p in parties)
    return None


def _calibration_window(calibration_run_id: str | None) -> dict[str, tuple[str, str]] | None:
    """`train`/`holdout` de `calibration/<run_id>/coefficients.json`, misma
    idea que `validation/argentina.py::_calibration_window` (no se importa
    de ahi para no acoplarse a un archivo que otro agente edita en
    paralelo -- son 8 lineas, se duplican)."""
    if not calibration_run_id:
        return None
    from republica.world.config import DEFAULT_DATA_DIR

    path = DEFAULT_DATA_DIR / "countries" / "argentina" / "calibration" / calibration_run_id
    coeff_path = path / "coefficients.json"
    if not coeff_path.exists():
        return None
    raw = json.loads(coeff_path.read_text(encoding="utf-8"))
    train, holdout = raw.get("train"), raw.get("holdout")
    if not train:
        return None
    return {"train": (train[0], train[1]), "holdout": tuple(holdout) if holdout else None}


def in_sample(window: Window, calibration_run_id: str | None) -> bool | None:
    win = _calibration_window(calibration_run_id)
    if win is None:
        return None
    t0, target = win["train"]
    return t0 <= window.t0 and window.t_target <= target


def compute_window_features(window: Window, calibration_run_id: str | None) -> dict:
    y0, m0 = int(window.t0[:4]), int(window.t0[5:7])
    monthly = window.frequency == "monthly"

    if monthly:
        state = initial_state_for(window.t0)
        counts = {"source": 0, "proxy": 0, "assumed": 0}
        for prov in state.values():
            kind = _provenance_kind(prov)
            counts[kind] = counts.get(kind, 0) + 1
        approval = state["government_approval"]["value"]
    else:
        # Modo anual (ADR 011 secc. 6): usa el `initial_state` de Aurora
        # entero, no hay `source`/`proxy` real para ninguna variable.
        counts = {"source": 0, "proxy": 0, "assumed": 20}
        approval = None

    reserves_series = _load_monthly_series("reserves_monthly")
    unemployment_series = _load_monthly_series("unemployment")
    has_reserves = any((y0, m) in reserves_series for m in range(1, 13))
    has_unemployment = any((y0, m) in unemployment_series for m in range(1, 13))

    regimes_by_year = _load_regimes_by_year()
    regime_mode_initial = regimes_by_year.get(y0)
    vdem_polyarchy = _load_annual_series_vdem_polyarchy().get(y0)
    years_since_coup = _years_since(y0, m0, _load_coup_dates())
    years_since_default = _years_since(y0, m0, _load_default_dates())

    fx_regime = _fx_regime_for(window.t0)

    infl_now = real_inflation_monthly_equiv(y0, m0)
    infl_prev12 = real_inflation_monthly_equiv(*_sub_12(y0, m0))
    inflation_trend_12m = (
        infl_now - infl_prev12 if infl_now is not None and infl_prev12 is not None else None
    )

    reserves = reserves_series.get((y0, m0))
    public_debt = _load_monthly_series("public_debt").get((y0, m0))
    gdp_usd = _load_annual_series("gdp_usd").get(y0)
    debt_over_gdp = (
        (public_debt * 1.0e6 / gdp_usd) * 100.0 if public_debt is not None and gdp_usd else None
    )
    # Proxy de "meses de importaciones" (ADR 012 secc. 3, R_min = rm *
    # importaciones mensuales): usa `M0` (importaciones USD M/mes) de
    # `world/countries.py::x0_m0_from_gdp_usd`, mismo mecanismo que
    # `CountryPack.macro_m0` -- se recalcula aca en vez de cargar un
    # `CountryPack` completo solo para esto.
    reserves_over_imports = None
    if reserves is not None and gdp_usd:
        from republica.world.countries import x0_m0_from_gdp_usd
        from republica.world.economy import MacroCoefficients

        _, m0_usd = x0_m0_from_gdp_usd(PACK_DIR, window.t0, MacroCoefficients().x0_m0_pct_gdp)
        if m0_usd:
            reserves_over_imports = reserves / (3.0 * m0_usd)

    return {
        "t0": window.t0,
        "h": window.h,
        "t_target": window.t_target,
        "frequency": window.frequency,
        "has_era": window.era_id is not None,
        "era_id": window.era_id or "",
        "n_source": counts.get("source", 0),
        "n_proxy": counts.get("proxy", 0),
        "n_assumed": counts.get("assumed", 0),
        "has_reserves_series": has_reserves,
        "has_unemployment_series": has_unemployment,
        "regime_mode_initial": regime_mode_initial or "",
        "vdem_polyarchy": vdem_polyarchy,
        "years_since_last_coup": years_since_coup,
        "fx_regime": fx_regime,
        "inflation_now": infl_now,
        "inflation_bucket": inflation_bucket(infl_now),
        "inflation_trend_12m": inflation_trend_12m,
        "reserves_over_imports_3m": reserves_over_imports,
        "debt_over_gdp_pct": debt_over_gdp,
        "years_since_last_default": years_since_default,
        "months_to_next_election": months_to_next_election(window.t0),
        "approval_proxy": approval,
        "fragmentation_herfindahl": herfindahl_seats(window.era_id),
        "n_exogenous_shocks": window.forced_plan.count,
        "shocks_magnitude_sum": window.forced_plan.magnitude_sum,
        "in_sample": in_sample(window, calibration_run_id),
    }


@functools.lru_cache(maxsize=1)
def _load_annual_series_vdem_polyarchy() -> dict[int, float]:
    path = HISTORY_DIR / "vdem_argentina.csv"
    out: dict[int, float] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out[int(row["date"][:4])] = float(row["v2x_polyarchy"])
            except (ValueError, KeyError):
                continue
    return out


def _sub_12(y: int, m: int) -> tuple[int, int]:
    total = y * 12 + (m - 1) - 12
    return total // 12, total % 12 + 1


@functools.lru_cache(maxsize=1)
def _fx_regimes_table() -> list[tuple[str, str, str]]:
    path = PACK_DIR / "fx_regimes.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [(row["date_from"], row["date_to"], row["fx_regime"]) for row in csv.DictReader(fh)]


def _fx_regime_for(t0: str) -> str:
    for date_from, date_to, regime in _fx_regimes_table():
        if date_from <= t0 <= date_to:
            return regime
    return "float"
