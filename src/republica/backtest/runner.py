"""Corre el backtest: N semillas x 2 brazos por ventana (ADR 014 secc. 1),
con checkpoint por ventana (`--resume`) y paralelismo por proceso
(`--workers`).

Sigue el mismo patron que `validation/argentina.py::run_test_arm` (estado
inicial real, calendario de regimen, exogenas reales, coeficientes del
paquete o de `--calibration <id>`), con dos diferencias deliberadas (ADR
014 secc. 1, documentadas tambien en el ADR):

1. Los shocks forzados son SOLO los de `windows.py::EXOGENOUS_ONLY`
   (windows.py ya filtro esto al armar `window.forced_plan`).
2. El calendario de regimen NUNCA fuerza un golpe real (`backtest_regime_
   calendar`, mas abajo) -- a diferencia de `load_country_pack(...,
   regime_mode="auto")`, que fuerza los golpes de `politics/events.csv`
   (correcto para A4, no para el objetivo "golpe" de este backtest: ver
   `windows.py`).
"""

from __future__ import annotations

import csv
import dataclasses
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from republica.backtest.features import compute_window_features
from republica.backtest.scoring import SeedOutcome, score_window
from republica.backtest.windows import Window, generate_windows
from republica.calibration.initial_states import flat_initial_state
from republica.calibration.run import load_calibrated_country
from republica.engine.policy import PassivePolicy
from republica.engine.simulation import run as run_simulation
from republica.world.annual import load_annual_regime, run_annual
from republica.world.countries import (
    country_pack_dir,
    historical_exogenous_series,
    load_country_pack,
    load_country_pack_annual,
)
from republica.world.eras import era_governance_overrides
from republica.world.regime import RegimeCalendar, coup_propensity_by_decade

ARMS: tuple[str, str] = ("calibrated", "aurora")


def backtest_regime_calendar(pack_dir: Path, y0: int, m0: int, months: int) -> RegimeCalendar:
    """`RegimeCalendar` con `forced_coup_months` SIEMPRE vacio (ADR 014
    secc. 1: el golpe es el objetivo, no un dato que se le regala al
    modelo) pero con la propension endogena real por decada
    (`world/regime.py::coup_propensity_by_decade`, la misma que usa
    `--regime-mode auto`) -- asi el modelo SI puede producir un golpe
    endogeno (`political_stability`/`institutional_confidence` bajos +
    sorteo), simplemente no se le fuerza ninguno real."""
    propensity_by_decade = coup_propensity_by_decade(pack_dir / "politics" / "events.csv")
    cal = RegimeCalendar()
    for month_idx in range(1, months + 1):
        total_months = (m0 - 1) + (month_idx - 1)
        y = y0 + total_months // 12
        decade = (y // 10) * 10
        cal.coup_propensity[month_idx] = propensity_by_decade.get(decade, 0.0)
    return cal


def _history_to_outcome(seed: int, history) -> SeedOutcome:
    recs = history.records
    return SeedOutcome(
        seed=seed,
        outcome=history.outcome,
        months_run=len(recs),
        inflation_monthly=[r.state["inflation"] for r in recs],
        reserves=[r.state["reserves"] for r in recs],
        unemployment=[r.state["unemployment"] for r in recs],
        regime_modes=[r.regime_mode for r in recs],
        shocks_active_union=frozenset(s for r in recs for s in r.shocks_active),
        elections=[
            {
                "month": e.month,
                "outcome_type": e.outcome_type,
                "winner": e.winner,
                "incumbent_party": e.incumbent_party,
            }
            for e in history.election_records
        ],
    )


def run_monthly_arm(
    window: Window, arm: str, calibration_run_id: str, seeds: int, seed_base: int
) -> list[SeedOutcome]:
    y0, m0 = int(window.t0[:4]), int(window.t0[5:7])
    pack = load_country_pack(
        "argentina",
        window.t0,
        window.h,
        regime_mode="auto",
        initial_state_override=flat_initial_state(window.t0),
    )
    # Reemplaza el calendario de regimen del paquete (que SI fuerza golpes
    # reales, `regime_mode="auto"`) por uno sin golpes forzados, ver
    # `backtest_regime_calendar`.
    pack.regime_calendar = backtest_regime_calendar(pack.pack_dir, y0, m0, window.h)

    country = pack.country
    bimonetary = pack.bimonetary_coefficients
    macro_active = country.features.get("macro_regime", False)
    macro = pack.macro_coefficients if macro_active else None
    if arm == "calibrated":
        coeff, bimonetary_cal, macro_cal = load_calibrated_country("argentina", calibration_run_id)
        country = country.model_copy(update={"coefficients": coeff})
        bimonetary = bimonetary_cal
        if macro_active and macro_cal is not None:
            macro = macro_cal
    bimonetary = dataclasses.replace(bimonetary, fx_regime_default=pack.fx_regime_auto)

    era_actors = None
    era_loyalty_table = None
    gov_overrides = None
    if pack.era is not None and pack.era.parties is not None:
        era_actors = pack.era.actors
        era_loyalty_table = pack.era.loyalty_table
        if pack.era.governance_path is not None and pack.era.governance_path.exists():
            gov_overrides = era_governance_overrides(pack.era.governance_path)

    exogenous = historical_exogenous_series(pack.pack_dir, y0, m0, window.h)
    policy_rule = PassivePolicy(
        country.default_policy,
        country.structure.r_neutral,
        country.policy_ranges["interest_rate_target"],
    )
    features_flags = country.features
    forced = {k: list(v) for k, v in window.forced_plan.forced.items()} or None

    outcomes: list[SeedOutcome] = []
    for i in range(seeds):
        seed = seed_base + i
        history = run_simulation(
            seed=seed,
            months=window.h,
            policy_rule=policy_rule,
            forced_shocks=forced,
            country=country,
            actors_enabled=features_flags.get("actors", True),
            actors=era_actors,
            congress_enabled=features_flags.get("congress", True),
            negotiation_enabled=features_flags.get("negotiation", True),
            cohorts_enabled=features_flags.get("cohorts", True),
            media_enabled=features_flags.get("media", True),
            memory_enabled=features_flags.get("memory", True),
            elections_enabled=features_flags.get("elections", True),
            loyalty_table=era_loyalty_table,
            governance_overrides=gov_overrides,
            regime_calendar=pack.regime_calendar,
            bimonetary_coefficients=bimonetary,
            historical_exogenous=exogenous,
            macro_coefficients=macro,
            macro_x0=pack.macro_x0 if macro is not None else None,
            macro_m0=pack.macro_m0 if macro is not None else None,
            fx_regime=pack.fx_regime_auto if macro is not None else None,
        )
        outcomes.append(_history_to_outcome(seed, history))
    return outcomes


def _annual_history_to_outcome(seed: int, history) -> SeedOutcome:
    recs = history.records
    return SeedOutcome(
        seed=seed,
        outcome=history.outcome,
        months_run=len(recs),
        inflation_monthly=[r.state["inflation"] for r in recs],
        reserves=[r.state["reserves"] for r in recs],
        unemployment=[r.state["unemployment"] for r in recs],
        regime_modes=[r.regime_mode for r in recs],
        shocks_active_union=frozenset(s for r in recs for s in r.shocks_active),
        elections=[],
    )


def run_annual_arm(
    window: Window, arm: str, calibration_run_id: str, seeds: int, seed_base: int
) -> list[SeedOutcome]:
    year0 = int(window.t0[:4])
    years = window.h // 12
    country = load_country_pack_annual("argentina", year0, years)
    if arm == "calibrated":
        coeff, _bimon, _macro = load_calibrated_country("argentina", calibration_run_id)
        country = country.model_copy(update={"coefficients": coeff})
    regime_lookup = load_annual_regime(country_pack_dir("argentina") / "politics" / "regimes.csv")
    policy_rule = PassivePolicy(
        country.default_policy,
        country.structure.r_neutral,
        country.policy_ranges["interest_rate_target"],
    )
    forced = {k: list(v) for k, v in window.forced_plan.forced.items()} or None

    outcomes: list[SeedOutcome] = []
    for i in range(seeds):
        seed = seed_base + i
        history = run_annual(
            seed=seed,
            years=years,
            country=country,
            policy_rule=policy_rule,
            start_year=year0,
            annual_regime=regime_lookup,
            forced_shocks=forced,
        )
        outcomes.append(_annual_history_to_outcome(seed, history))
    return outcomes


def run_window(
    window: Window, calibration_run_id: str, seeds: int, seed_base: int = 1
) -> dict[str, list[SeedOutcome]]:
    runner_fn = run_monthly_arm if window.frequency == "monthly" else run_annual_arm
    return {arm: runner_fn(window, arm, calibration_run_id, seeds, seed_base) for arm in ARMS}


def process_window(
    window: Window, calibration_run_id: str, seeds: int, seed_base: int
) -> tuple[str, list[dict], float]:
    """Funcion de un solo argumento-por-proceso (picklable, para
    `ProcessPoolExecutor`): corre, calcula caracteristicas, puntua, y
    devuelve `(window.key, filas, segundos de pared)`."""
    t0 = time.perf_counter()
    runs_by_arm = run_window(window, calibration_run_id, seeds, seed_base)
    features = compute_window_features(window, calibration_run_id)
    rows = score_window(window, features, runs_by_arm)
    return window.key, rows, time.perf_counter() - t0


WINDOWS_CSV_COLUMNS: tuple[str, ...] = (
    "t0",
    "h",
    "t_target",
    "arm",
    "objective",
    "hit",
    "error",
    "n_seeds",
    "iqr_seeds",
    "frequency",
    "has_era",
    "era_id",
    "n_source",
    "n_proxy",
    "n_assumed",
    "has_reserves_series",
    "has_unemployment_series",
    "regime_mode_initial",
    "vdem_polyarchy",
    "years_since_last_coup",
    "fx_regime",
    "inflation_now",
    "inflation_bucket",
    "inflation_trend_12m",
    "reserves_over_imports_3m",
    "debt_over_gdp_pct",
    "years_since_last_default",
    "months_to_next_election",
    "approval_proxy",
    "fragmentation_herfindahl",
    "n_exogenous_shocks",
    "shocks_magnitude_sum",
    "in_sample",
)


def _checkpoint_path(out_dir: Path) -> Path:
    return out_dir / "checkpoint.json"


def _load_checkpoint(out_dir: Path) -> set[str]:
    path = _checkpoint_path(out_dir)
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("done", []))


def _save_checkpoint(out_dir: Path, done: set[str]) -> None:
    _checkpoint_path(out_dir).write_text(
        json.dumps({"done": sorted(done)}, indent=2), encoding="utf-8"
    )


def run_backtest(
    out_dir: Path,
    *,
    calibration_run_id: str,
    from_year: int,
    to_year: int,
    horizons: tuple[int, ...],
    seeds: int,
    workers: int = 1,
    seed_base: int = 1,
    resume: bool = False,
    progress=None,
) -> Path:
    """Orquesta el backtest completo: genera las ventanas, las corre (con
    `workers` procesos), escribe `windows.csv` INCREMENTALMENTE (una fila
    por objetivo puntuado, apenas termina cada ventana) y un `checkpoint.json`
    con las ventanas ya hechas, para poder retomar con `resume=True`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    windows = generate_windows(from_year, to_year, horizons)
    done = _load_checkpoint(out_dir) if resume else set()
    csv_path = out_dir / "windows.csv"
    write_header = not (resume and csv_path.exists())
    mode = "a" if resume and csv_path.exists() else "w"

    pending = [w for w in windows if w.key not in done]
    if progress:
        progress(
            f"{len(windows)} ventanas totales, {len(done)} ya hechas, "
            f"{len(pending)} pendientes (workers={workers})."
        )

    with csv_path.open(mode, encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=WINDOWS_CSV_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        def _handle_result(key: str, rows: list[dict], wall: float) -> None:
            for row in rows:
                writer.writerow(row)
            fh.flush()
            done.add(key)
            _save_checkpoint(out_dir, done)
            if progress:
                progress(f"{key}: {len(rows)} filas, {wall:.1f}s ({len(done)}/{len(windows)})")

        if workers <= 1:
            for window in pending:
                key, rows, wall = process_window(window, calibration_run_id, seeds, seed_base)
                _handle_result(key, rows, wall)
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        process_window, window, calibration_run_id, seeds, seed_base
                    ): window
                    for window in pending
                }
                for future in as_completed(futures):
                    key, rows, wall = future.result()
                    _handle_result(key, rows, wall)

    return csv_path
