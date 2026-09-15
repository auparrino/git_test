"""Tests del backtest secuencial (ADR 014 secc. 6).

Cubre los 4 puntos del ADR: (1) `python -m republica.backtest` corre y
`windows.csv` sale con las columnas de secc. 2-3 sin `NaN` en `hit`; (2)
una ventana en 1930 no puntúa objetivos sin dato real; (3) el análisis
corre sobre un `windows.csv` sintético y produce el árbol (<=3 niveles) y
la tabla estratificada; (4) ningún shock prohibido aparece como forzado
(sobre el calendario real).

Usa la calibración `a3_main` (ya en disco, terminada) -- NUNCA `a5_macro`,
que otro agente puede estar corriendo/escribiendo en paralelo."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from republica.backtest import analysis, runner, scoring, windows

CALIBRATION_RUN_ID = "a3_main"
REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. `python -m republica.backtest`: corre y produce `windows.csv` completo.
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_cli_runs_and_produces_windows_csv_without_nan_hit(tmp_path: Path) -> None:
    out_dir = tmp_path / "smoke_2000_2003"
    cmd = [
        sys.executable,
        "-m",
        "republica.backtest",
        "--country",
        "argentina",
        "--calibration",
        CALIBRATION_RUN_ID,
        "--from",
        "2000",
        "--to",
        "2003",
        "--horizons",
        "12",
        "--seeds",
        "2",
        "--workers",
        "1",
        "--run-id",
        "smoke_2000_2003",
        "--out",
        str(out_dir),
        "--no-plots",
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr

    csv_path = out_dir / "windows.csv"
    assert csv_path.exists()
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "windows.csv no tiene filas"

    # Columnas de ADR 014 secc. 2 (objetivo/hit/error) y secc. 3
    # (caracteristicas de cada grupo: Datos, Regimen, Economia, Politica,
    # Shocks, Modelo).
    required_columns = {
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
        "n_source",
        "n_proxy",
        "n_assumed",
        "has_reserves_series",
        "has_unemployment_series",
        "regime_mode_initial",
        "vdem_polyarchy",
        "years_since_last_coup",
        "fx_regime",
        "inflation_bucket",
        "inflation_trend_12m",
        "months_to_next_election",
        "approval_proxy",
        "fragmentation_herfindahl",
        "n_exogenous_shocks",
        "shocks_magnitude_sum",
        "has_era",
        "in_sample",
    }
    assert required_columns <= set(rows[0].keys())

    for row in rows:
        assert row["hit"] not in ("", "nan", "NaN", None)
        assert int(row["hit"]) in (0, 1)
        assert row["objective"] in scoring.OBJECTIVES
        assert row["arm"] in ("calibrated", "aurora")

    assert (out_dir / "report.md").exists()
    assert (out_dir / "checkpoint.json").exists()


def test_run_backtest_resume_skips_completed_windows(tmp_path: Path) -> None:
    """`--resume` no repite una ventana que ya esta en `checkpoint.json`
    (ADR 014 secc. 1: "checkpoint por ventana para poder retomar")."""
    out_dir = tmp_path / "resume_test"
    runner.run_backtest(
        out_dir,
        calibration_run_id=CALIBRATION_RUN_ID,
        from_year=2001,
        to_year=2001,
        horizons=(12,),
        seeds=1,
        workers=1,
    )
    first_rows = (out_dir / "windows.csv").read_text(encoding="utf-8")

    # Segunda corrida, resume=True: sin ventanas pendientes, no debe
    # agregar filas nuevas (mismo contenido).
    runner.run_backtest(
        out_dir,
        calibration_run_id=CALIBRATION_RUN_ID,
        from_year=2001,
        to_year=2001,
        horizons=(12,),
        seeds=1,
        workers=1,
        resume=True,
    )
    second_rows = (out_dir / "windows.csv").read_text(encoding="utf-8")
    assert first_rows == second_rows


# ---------------------------------------------------------------------------
# 2. Ventana en 1930: no se puntuan objetivos sin dato real en t0+h.
# ---------------------------------------------------------------------------


def test_1930_window_does_not_score_objectives_without_real_data() -> None:
    """1930 corre en modo anual (`frequency="annual_interpolated"`, ADR 011
    secc. 6: `regime_mode` se lee DIRECTO de `politics/regimes.csv`, no es
    una prediccion): `scoring.py` excluye `regime`/`election`/`coup` para
    ventanas anuales -- puntuarlos seria tautologico, no "sin dato real"."""
    ws = windows.generate_windows(1930, 1930, (12,))
    window = ws[0]
    assert window.frequency == "annual_interpolated"

    runs_by_arm = runner.run_window(window, CALIBRATION_RUN_ID, seeds=1, seed_base=1)
    features = {
        "t0": window.t0,
        "h": window.h,
        "frequency": window.frequency,
        "has_era": False,
        "era_id": "",
        "n_source": 0,
        "n_proxy": 0,
        "n_assumed": 20,
        "in_sample": None,
    }
    rows = scoring.score_window(window, features, runs_by_arm)
    objectives_scored = {r["objective"] for r in rows}

    assert "regime" not in objectives_scored
    assert "election" not in objectives_scored
    assert "coup" not in objectives_scored
    # "crisis" siempre tiene un dato real (incluye "no crisis"): se puntua
    # aun en modo anual.
    assert "crisis" in objectives_scored
    for row in rows:
        assert row["hit"] in (0, 1)


def test_score_window_skips_inflation_objectives_without_real_series() -> None:
    """Si no hay NINGUN dato real de inflacion en `t0` ni en `t_target`
    (fuera del rango de `inflation_cpi_annual_linked`, que arranca en
    1915), el objetivo de inflacion no genera fila -- se simula con un
    `Window` fuera de rango a mano, sin correr el motor (mas rapido, prueba
    solo `scoring.py`)."""
    fake_window = windows.Window(
        t0="1500-01",
        h=12,
        t_target="1501-01",
        frequency="annual_interpolated",
        era_id=None,
        forced_plan=windows.ForcedShockPlan(),
    )
    fake_run = scoring.SeedOutcome(
        seed=1,
        outcome="survived",
        months_run=12,
        inflation_monthly=[5.0] * 12,
        reserves=[100.0] * 12,
        unemployment=[10.0] * 12,
        regime_modes=["democracy"] * 12,
        shocks_active_union=frozenset(),
        elections=[],
    )
    features = {"t0": fake_window.t0, "h": fake_window.h}
    runs_by_arm = {"calibrated": [fake_run], "aurora": [fake_run]}
    rows = scoring.score_window(fake_window, features, runs_by_arm)
    objectives_scored = {r["objective"] for r in rows}
    assert "inflation_direction" not in objectives_scored
    assert "inflation_magnitude" not in objectives_scored
    # "crisis" no depende de la serie de inflacion: si se puntua igual.
    assert "crisis" in objectives_scored


# ---------------------------------------------------------------------------
# 3. Analisis sobre un `windows.csv` sintetico: arbol <=3 niveles + tabla.
# ---------------------------------------------------------------------------


def _synthetic_windows_csv(path: Path) -> None:
    """`windows.csv` sintetico con una relacion CLARA entre
    `inflation_bucket`/`n_assumed` y `hit`, para que el arbol/regresion
    tengan algo real que encontrar (no ruido puro) y para que la CV por
    decada tenga >= 3 grupos."""
    rows = []
    decades = [1990, 2000, 2010, 2020]
    buckets = ["<1", "1-3", "3-10", ">10"]
    i = 0
    for dec in decades:
        for year_offset in range(0, 8, 2):
            for bucket_idx, bucket in enumerate(buckets):
                i += 1
                t0 = f"{dec + year_offset:04d}-01"
                # senal fuerte: inflacion alta + muchas variables asumidas
                # -> falla mas seguido.
                n_assumed = 2 if bucket_idx < 2 else 14
                hit = 1 if (bucket_idx < 2 and n_assumed < 10) else (i % 5 != 0)
                rows.append(
                    {
                        "t0": t0,
                        "h": 12,
                        "t_target": t0,
                        "arm": "calibrated" if i % 2 == 0 else "aurora",
                        "objective": "inflation_direction",
                        "hit": int(hit),
                        "error": "",
                        "n_seeds": 5,
                        "iqr_seeds": 0.5 + (bucket_idx * 0.3),
                        "frequency": "monthly",
                        "has_era": True,
                        "era_id": "2003-2015",
                        "n_source": 20 - n_assumed,
                        "n_proxy": 0,
                        "n_assumed": n_assumed,
                        "has_reserves_series": True,
                        "has_unemployment_series": True,
                        "regime_mode_initial": "democracy",
                        "vdem_polyarchy": 0.6,
                        "years_since_last_coup": 30.0,
                        "fx_regime": "float",
                        "inflation_now": [0.5, 2.0, 6.0, 15.0][bucket_idx],
                        "inflation_bucket": bucket,
                        "inflation_trend_12m": 0.1,
                        "reserves_over_imports_3m": 2.0,
                        "debt_over_gdp_pct": 40.0,
                        "years_since_last_default": 10.0,
                        "months_to_next_election": 24,
                        "approval_proxy": 45.0,
                        "fragmentation_herfindahl": 0.3,
                        "n_exogenous_shocks": 0,
                        "shocks_magnitude_sum": 0.0,
                        "in_sample": True,
                    }
                )
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=runner.WINDOWS_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_analysis_on_synthetic_csv_produces_shallow_tree_and_stratified_table(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "windows.csv"
    _synthetic_windows_csv(csv_path)
    rows = analysis.load_windows(csv_path)
    assert rows and all(r["hit"] in (0, 1) for r in rows)

    table = analysis.stratified_table(rows, "inflation_direction", "inflation_bucket")
    assert len(table) >= 2
    assert all(0.0 <= t["hit_rate"] <= 1.0 for t in table)
    assert all(t["n"] > 0 for t in table)

    model = analysis.fit_predictability_model(rows, "inflation_direction")
    assert "skipped_reason" not in model, model.get("skipped_reason")

    try:
        from sklearn.tree import DecisionTreeClassifier  # noqa: F401
    except ImportError:
        pytest.skip("extra `ml` no instalado")

    assert len(model["tree_rules_plain"]) >= 1
    assert len(model["tree_rules_plain"]) <= 3
    assert "≤" in model["tree_text"] or ">" in model["tree_text"] or "=" in model["tree_text"]
    # profundidad <= 3: el texto de sklearn indenta 2 espacios por nivel
    # con "|" al inicio de cada linea de decision.
    max_indent = max(
        (line.count("|") for line in model["tree_text"].splitlines() if line.strip()),
        default=0,
    )
    assert max_indent <= 3


def test_iqr_vs_error_spearman_on_synthetic_data() -> None:
    rows = [
        {
            "t0": "2000-01",
            "objective": "inflation_magnitude",
            "iqr_seeds": float(i),
            "error": float(i) * 0.5 + 1.0,
            "hit": 1,
        }
        for i in range(1, 12)
    ]
    result = analysis.iqr_vs_error(rows)
    assert result["n"] == 11
    assert result["spearman_rho"] is not None
    assert result["spearman_rho"] > 0.9  # relacion monotona perfecta por construccion


def test_calibrated_vs_aurora_by_decade_table() -> None:
    rows = [
        {"t0": "1995-01", "objective": "crisis", "arm": "calibrated", "hit": 1},
        {"t0": "1996-01", "objective": "crisis", "arm": "calibrated", "hit": 0},
        {"t0": "1995-01", "objective": "crisis", "arm": "aurora", "hit": 0},
        {"t0": "2005-01", "objective": "crisis", "arm": "calibrated", "hit": 1},
    ]
    table = analysis.calibrated_vs_aurora_by_decade(rows, ["crisis"])
    by_decade = {row["decade"]: row for row in table}
    assert by_decade[1990]["n_calibrated"] == 2
    assert by_decade[1990]["n_aurora"] == 1
    assert by_decade[2000]["n_aurora"] == 0
    assert by_decade[2000]["hit_rate_aurora"] is None


# ---------------------------------------------------------------------------
# 4. Ningun shock prohibido aparece jamas como forzado.
# ---------------------------------------------------------------------------


def test_exogenous_only_never_overlaps_forbidden_shocks() -> None:
    assert windows.EXOGENOUS_ONLY.isdisjoint(windows.FORBIDDEN_SHOCK_IDS)


def test_no_forbidden_shock_forced_across_full_real_calendar() -> None:
    """Resuelve TODOS los shocks forzados del backtest completo (107
    origenes x 3 horizontes, sin correr ninguna simulacion: solo lee
    `politics/shocks_calendar.csv`) y verifica que ninguno este en
    `FORBIDDEN_SHOCK_IDS` (ADR 014 secc. 6 test 4)."""
    all_windows = windows.generate_windows()
    seen_ids: set[str] = set()
    total_forced = 0
    for window in all_windows:
        for ids in window.forced_plan.forced.values():
            for shock_id in ids:
                seen_ids.add(shock_id)
                total_forced += 1
                assert shock_id not in windows.FORBIDDEN_SHOCK_IDS
                assert shock_id in windows.EXOGENOUS_ONLY
    assert total_forced > 0, "el calendario real no forzo NINGUN shock: sospechoso"
    assert seen_ids <= windows.EXOGENOUS_ONLY


def test_backtest_regime_calendar_never_forces_a_coup() -> None:
    """`runner.backtest_regime_calendar` (ADR 014 secc. 1: el golpe es el
    objetivo) nunca fuerza un golpe real, a diferencia de
    `load_country_pack(..., regime_mode="auto")` -- se verifica sobre una
    ventana que SI cruza un golpe real (1930-09, Uriburu)."""
    from republica.world.countries import country_pack_dir
    from republica.world.regime import build_regime_calendar

    pack_dir = country_pack_dir("argentina")
    # `build_regime_calendar` (el que usa `republica run`/A4) SI fuerza el
    # golpe real de 1930 dentro de esta ventana (1928-01 + 36 meses).
    real_calendar = build_regime_calendar(pack_dir / "politics" / "events.csv", 1928, 1, 36, "auto")
    assert real_calendar.forced_coup_months, "sanity: el calendario real SI deberia forzar 1930"

    backtest_calendar = runner.backtest_regime_calendar(pack_dir, 1928, 1, 36)
    assert backtest_calendar.forced_coup_months == set()
    # pero la propension endogena de la decada de 1930 sigue > 0 (el
    # modelo SI puede producir un golpe por su cuenta).
    assert any(p > 0 for p in backtest_calendar.coup_propensity.values())


def test_annual_forced_exogenous_shock_does_not_crash(monkeypatch) -> None:
    """Regresion del bug real encontrado en `world/annual.py::run_annual`
    (catalogo vacio + shock forzado -> `KeyError`, corregido en esta
    tarea): una ventana anual con un shock exogeno forzado corre sin
    excepcion."""
    ws = windows.generate_windows(1930, 1930, (12,))
    window = ws[0]
    assert window.forced_plan.forced, "sanity: 1930 deberia forzar la crisis del 30"
    runs = runner.run_annual_arm(window, "aurora", CALIBRATION_RUN_ID, seeds=1, seed_base=1)
    assert len(runs) == 1
    # modo anual: un registro por AÑO, no por mes (`years = window.h // 12`).
    assert runs[0].months_run == window.h // 12


def test_numerical_overflow_in_one_seed_does_not_crash_the_window(monkeypatch) -> None:
    """Regresion de un fallo real de la corrida completa (b1_a5b, ADR 014
    "Resultados"): `world/economy.py::step_economy` puede desbordar
    (`OverflowError`) con ciertos coeficientes calibrados en modo anual
    (legacy). Una semilla que desborda se descarta, no tira abajo la
    ventana entera."""

    def _boom(*args, **kwargs):
        raise OverflowError("(34, 'Numerical result out of range')")

    monkeypatch.setattr(runner, "run_annual", _boom)
    ws = windows.generate_windows(1950, 1950, (12,))
    window = ws[0]
    runs = runner.run_annual_arm(window, "aurora", CALIBRATION_RUN_ID, seeds=3, seed_base=1)
    assert runs == []  # las 3 semillas fallaron, la funcion no propaga la excepcion


def test_process_window_never_raises_even_on_unexpected_failure(monkeypatch) -> None:
    """Red de seguridad de ultima instancia: si `run_window` revienta con
    CUALQUIER excepcion, `process_window` devuelve 0 filas en vez de
    propagar (para que `ProcessPoolExecutor` no tire abajo toda la
    corrida, ADR 014 "Resultados")."""

    def _boom(*args, **kwargs):
        raise RuntimeError("algo totalmente inesperado")

    monkeypatch.setattr(runner, "run_window", _boom)
    ws = windows.generate_windows(2000, 2000, (12,))
    window = ws[0]
    key, rows, wall = runner.process_window(window, CALIBRATION_RUN_ID, seeds=1, seed_base=1)
    assert key == window.key
    assert rows == []
    assert wall >= 0.0
