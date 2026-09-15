"""`calibration/<run_id>/report.md` + `plots/` (A3, ADR 011 secc. 7 punto 5)."""

from __future__ import annotations

from pathlib import Path

from republica.calibration.objective import HORIZONS, VARIABLES
from republica.calibration.parameters import Parameter
from republica.calibration.run import HONESTY_SENTENCE, CalibrationRunConfig

VARIABLE_LABEL = {
    "inflation": "inflacion (mensual, %)",
    "gdp_growth": "crecimiento del PBI (anualizado, %)",
    "unemployment": "desempleo (%)",
    "exchange_rate": "tipo de cambio oficial (cambio log)",
    "reserves": "reservas (USD M)",
}


def _fmt(v: float) -> str:
    if v != v:  # NaN
        return "sin dato"
    return f"{v:.3f}"


def _metric_table(tables: dict) -> str:
    lines = [
        f"n = {tables['n_start_months']} meses de arranque.",
        "",
        "| variable | horizonte | calibrado | persistencia | Aurora sin calibrar |",
        "|---|---|---|---|---|",
    ]
    for var in VARIABLES:
        for h in HORIZONS:
            key = f"{var}_h{h}"
            calibrated_v = _fmt(tables["calibrated"].get(key, float("nan")))
            persistence_v = _fmt(tables["persistence"].get(key, float("nan")))
            aurora_v = _fmt(tables["aurora"].get(key, float("nan")))
            lines.append(
                f"| {VARIABLE_LABEL[var]} | {h} | {calibrated_v} | {persistence_v} | {aurora_v} |"
            )
    lines.append("")
    lines.append(
        f"| regimen (acierto democracia/no) | - | "
        f"{_fmt(tables['calibrated'].get('regime_accuracy', float('nan')))} | - | "
        f"{_fmt(tables['aurora'].get('regime_accuracy', float('nan')))} |"
    )
    lines.append(
        f"| elecciones (acierto reelegido/derrotado) | - | "
        f"{_fmt(tables['calibrated'].get('election_accuracy', float('nan')))} | - | "
        f"{_fmt(tables['aurora'].get('election_accuracy', float('nan')))} |"
    )
    return "\n".join(lines)


def _drift_table(params: list[Parameter], calibrated_x: list[float], top_n: int = 15) -> str:
    rows = []
    for p, v in zip(params, calibrated_x, strict=True):
        span = p.hi - p.lo
        drift_units = (v - p.aurora_value) / span if span else 0.0
        rows.append((p, v, drift_units))
    rows.sort(key=lambda r: abs(r[2]), reverse=True)
    lines = [
        "| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |",
        "|---|---|---|---|---|",
    ]
    for p, v, drift in rows[:top_n]:
        lines.append(f"| {p.name} | {p.group} | {p.aurora_value:.4g} | {v:.4g} | {drift:+.3f} |")
    return "\n".join(lines)


def _write_plots(run_dir: Path, result, params: list[Parameter], calibrated_x: list[float]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    plots_dir = run_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    if result.history_rows:
        xs = [r["evaluations"] for r in result.history_rows]
        ys = [r["best_scalar_so_far"] for r in result.history_rows]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(xs, ys, marker="o")
        ax.set_xlabel("evaluaciones")
        ax.set_ylabel("mejor escalar (train)")
        ax.set_title("Convergencia de CMA-ES")
        fig.tight_layout()
        fig.savefig(plots_dir / "convergence.png", dpi=110)
        plt.close(fig)

    rows = []
    for p, v in zip(params, calibrated_x, strict=True):
        span = p.hi - p.lo
        drift = (v - p.aurora_value) / span if span else 0.0
        rows.append((p.name, drift))
    rows.sort(key=lambda r: abs(r[1]), reverse=True)
    top = rows[:15]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh([r[0] for r in reversed(top)], [r[1] for r in reversed(top)])
    ax.set_xlabel("drift (unidades del rango [-1, 1])")
    ax.set_title("Top 15 parametros con mayor drift")
    fig.tight_layout()
    fig.savefig(plots_dir / "parameter_drift.png", dpi=110)
    plt.close(fig)


def write_report(
    run_dir: Path,
    cfg: CalibrationRunConfig,
    params: list[Parameter],
    calibrated_x: list[float],
    train_tables: dict,
    holdout_tables: dict,
    result,
) -> None:
    from republica.calibration.run import input_data_hash

    lines = [
        f"# Calibracion Argentina -- run `{cfg.run_id}`",
        "",
        f"Pais: `{cfg.country_id}`. Train: `{cfg.train_start}:{cfg.train_end}`. "
        f"Holdout: `{cfg.holdout_start}:{cfg.holdout_end}` (corrido UNA SOLA VEZ, al final, "
        "despues de fijar los coeficientes con train -- protocolo de honestidad, "
        "PLAN_ARGENTINA.md #0.3/#4).",
        f"Presupuesto: {cfg.budget} evaluaciones (usadas: {result.evaluations}). "
        f"Stride: {cfg.stride} meses. lambda_reg: {cfg.lambda_reg}. Semilla: {cfg.seed}.",
        f"Tiempo de pared del optimizador: {result.wall_seconds:.1f}s.",
        f"Hash de los datos de entrada (`history/*.csv` + `politics/*.csv`): "
        f"`{input_data_hash(cfg.country_id)}`.",
        "",
        "## Shocks forzados en el periodo",
        "",
        "Cada mes de arranque simula con `--historical-shocks --historical-exogenous`: los "
        "shocks del calendario real (`politics/shocks_calendar.csv`, ADR 011 secc. 4) estan "
        "FORZADOS -- si el modelo reproduce una crisis en un mes donde hubo un shock forzado, "
        "no es merito de la dinamica interna calibrada, es el shock. Ver "
        "`data/countries/argentina/politics/shocks_calendar.csv` para la lista completa; no se "
        "repite aca fila por fila para no duplicar la fuente de verdad.",
        "",
        "## Train",
        "",
        _metric_table(train_tables),
        "",
        "## Holdout",
        "",
        _metric_table(holdout_tables),
        "",
        "## Drift de parametros (Aurora -> calibrado)",
        "",
        "Top 15 por magnitud de drift, en unidades del RANGO permitido de cada parametro "
        "(`(calibrado - aurora) / (hi - lo)`; +-0.5 es la mitad del rango explorable). "
        "Tabla completa en `coefficients.json`.",
        "",
        _drift_table(params, calibrated_x),
        "",
        "## Limitaciones",
        "",
        f"> {HONESTY_SENTENCE}",
        "",
        "Proxies usados en el estado inicial de cada mes: ver "
        "`src/republica/calibration/initial_states.py` (docstring del modulo, reglas de "
        "interpolacion) y `initial_state_for(date)` para la procedencia `source`/`proxy`/"
        "`assumed` de cada variable en cada mes de arranque.",
    ]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_plots(run_dir, result, params, calibrated_x)
