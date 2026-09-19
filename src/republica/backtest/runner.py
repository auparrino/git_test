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
from republica.world.regime import (
    RegimeCalendar,
    coup_propensity_by_decade,
    initial_regime_state,
)

ARMS: tuple[str, str] = ("calibrated", "aurora")

#: Hallazgo real, encontrado corriendo el backtest completo por primera vez
#: (b1_a5b, calibracion `a5b_macro`): con coeficientes calibrados contra el
#: objetivo MACRO (ADR 012), el grupo de `Coefficients` "viejo" (sin macro)
#: puede quedar sin restriccion util (la funcion objetivo con
#: `features.macro_regime=True` nunca ejercita `step_economy`, solo
#: `step_macro_economy` -- ver `calibration/objective.py`) y terminar en
#: valores que, usados en el motor LEGACY (`world/annual.py`, que SIEMPRE
#: usa `step_economy`, nunca el macro), producen un crecimiento mensual
#: `g_m` tan grande que `(1+g_m/100)**12` desborda un `float` de Python
#: (`OverflowError`). Una sola semilla con esta patologia numerica no debe
#: tirar abajo las otras 29 ni las demas 320 ventanas: se descarta esa
#: semilla (se loguea, `n_seeds` de esa ventana/brazo queda mas chico) en
#: vez de propagar la excepcion. Documentado en el ADR ("Resultados").
_NUMERIC_FAILURE_EXCEPTIONS: tuple[type[Exception], ...] = (
    OverflowError,
    ValueError,
    ZeroDivisionError,
    ArithmeticError,
)


def backtest_regime_calendar(
    pack_dir: Path,
    y0: int,
    m0: int,
    months: int,
    regime_transitions: bool = False,
) -> RegimeCalendar:
    """`RegimeCalendar` con `forced_coup_months` SIEMPRE vacio (ADR 014
    secc. 1: el golpe es el objetivo, no un dato que se le regala al
    modelo) pero con la propension endogena real por decada
    (`world/regime.py::coup_propensity_by_decade`, la misma que usa
    `--regime-mode auto`) -- asi el modelo SI puede producir un golpe
    endogeno (`political_stability`/`institutional_confidence` bajos +
    sorteo), simplemente no se le fuerza ninguno real.

    `regime_transitions` (ADR 015): prende el modelo de riesgo mensual y
    siembra el modo inicial del regimen con el dato real de
    `politics/regimes.csv` en `t0`. `forced_coup_months` sigue vacio: el
    mecanismo corre SIN golpes forzados, como pide la nota "Desviacion
    deliberada del calendario" del ADR 014. Lo que se siembra es el modo en
    `t0` (un dato de entrada, igual que el `initial_state` economico real);
    lo que se predice es el modo en `t0 + h`."""
    propensity_by_decade = coup_propensity_by_decade(pack_dir / "politics" / "events.csv")
    seed_state = (
        initial_regime_state(pack_dir / "politics" / "regimes.csv", y0, m0)
        if regime_transitions
        else None
    )
    cal = RegimeCalendar(
        endogenous_transitions=regime_transitions,
        initial_mode=seed_state.mode if seed_state is not None else "democracy",
        initial_months_in_mode=seed_state.months_in_mode if seed_state is not None else 0,
        initial_de_facto_months=seed_state.de_facto_months if seed_state is not None else 0,
    )
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
    window: Window,
    arm: str,
    calibration_run_id: str,
    seeds: int,
    seed_base: int,
    regime_transitions: bool = False,
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
    pack.regime_calendar = backtest_regime_calendar(
        pack.pack_dir, y0, m0, window.h, regime_transitions=regime_transitions
    )

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
    n_failed = 0
    for i in range(seeds):
        seed = seed_base + i
        try:
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
        except _NUMERIC_FAILURE_EXCEPTIONS as exc:
            n_failed += 1
            print(
                f"[backtest] {window.t0} h={window.h} arm={arm} seed={seed}: "
                f"{type(exc).__name__}: {exc} -- semilla descartada.",
                flush=True,
            )
            continue
        outcomes.append(_history_to_outcome(seed, history))
    if n_failed:
        print(
            f"[backtest] {window.t0} h={window.h} arm={arm}: {n_failed}/{seeds} semillas "
            f"descartadas por falla numerica ({len(outcomes)} usables).",
            flush=True,
        )
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
    window: Window,
    arm: str,
    calibration_run_id: str,
    seeds: int,
    seed_base: int,
    regime_transitions: bool = False,
) -> list[SeedOutcome]:
    # `regime_transitions` se acepta por simetria de firma con
    # `run_monthly_arm` y se IGNORA: en modo anual `regime_mode` se lee
    # directo de `regimes.csv` (ADR 011 secc. 6) y `scoring.py` no puntua
    # `regime`/`coup` ahi, asi que el modelo de riesgo de ADR 015 no tiene
    # nada que decidir.
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
    n_failed = 0
    for i in range(seeds):
        seed = seed_base + i
        try:
            history = run_annual(
                seed=seed,
                years=years,
                country=country,
                policy_rule=policy_rule,
                start_year=year0,
                annual_regime=regime_lookup,
                forced_shocks=forced,
            )
        except _NUMERIC_FAILURE_EXCEPTIONS as exc:
            n_failed += 1
            print(
                f"[backtest] {window.t0} h={window.h} arm={arm} seed={seed}: "
                f"{type(exc).__name__}: {exc} -- semilla descartada.",
                flush=True,
            )
            continue
        outcomes.append(_annual_history_to_outcome(seed, history))
    if n_failed:
        print(
            f"[backtest] {window.t0} h={window.h} arm={arm}: {n_failed}/{seeds} semillas "
            f"descartadas por falla numerica ({len(outcomes)} usables).",
            flush=True,
        )
    return outcomes


def run_window(
    window: Window,
    calibration_run_id: str,
    seeds: int,
    seed_base: int = 1,
    regime_transitions: bool = False,
) -> dict[str, list[SeedOutcome]]:
    runner_fn = run_monthly_arm if window.frequency == "monthly" else run_annual_arm
    return {
        arm: runner_fn(window, arm, calibration_run_id, seeds, seed_base, regime_transitions)
        for arm in ARMS
    }


def process_window(
    window: Window,
    calibration_run_id: str,
    seeds: int,
    seed_base: int,
    regime_transitions: bool = False,
) -> tuple[str, list[dict], float]:
    """Funcion de un solo argumento-por-proceso (picklable, para
    `ProcessPoolExecutor`): corre, calcula caracteristicas, puntua, y
    devuelve `(window.key, filas, segundos de pared)`.

    Red de seguridad de ULTIMA instancia (ademas del try/except por semilla
    de `run_monthly_arm`/`run_annual_arm`): si algo imprevisto revienta la
    ventana ENTERA (los dos brazos, o `compute_window_features`/
    `score_window`), esa ventana queda con 0 filas puntuadas y el resto de
    la corrida (320 ventanas restantes) sigue -- una ventana rota no puede
    tirar abajo 6-8 minutos de computo ya hecho. Se loguea igual, para que
    no quede en silencio."""
    t0 = time.perf_counter()
    try:
        runs_by_arm = run_window(window, calibration_run_id, seeds, seed_base, regime_transitions)
        features = compute_window_features(window, calibration_run_id)
        rows = score_window(window, features, runs_by_arm)
    except Exception as exc:  # noqa: BLE001 - red de seguridad deliberada, ver docstring
        print(
            f"[backtest] {window.t0} h={window.h}: ventana DESCARTADA entera "
            f"({type(exc).__name__}: {exc}).",
            flush=True,
        )
        return window.key, [], time.perf_counter() - t0
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
    regime_transitions: bool = False,
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
                key, rows, wall = process_window(
                    window, calibration_run_id, seeds, seed_base, regime_transitions
                )
                _handle_result(key, rows, wall)
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        process_window,
                        window,
                        calibration_run_id,
                        seeds,
                        seed_base,
                        regime_transitions,
                    ): window
                    for window in pending
                }
                for future in as_completed(futures):
                    key, rows, wall = future.result()
                    _handle_result(key, rows, wall)

    return csv_path
