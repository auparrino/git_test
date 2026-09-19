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


def _n_header(tables: dict) -> str:
    n = tables["n_start_months"]
    if n == 0:
        return (
            "n = 0 meses de arranque en esta ventana: el grupo no tiene ningun mes de arranque "
            "aca (se imprime igual, con 'sin dato', para que la ausencia sea visible -- ADR 017 "
            "secc. 4)."
        )
    weighted = tables.get("n_weighted_pre_1997")
    if weighted is None:
        return f"n = {n} meses de arranque."
    return (
        f"n = {n} meses de arranque ({weighted} con peso 0.5: series mensuales interpoladas "
        "de anuales antes de 1997, A5/ADR 012 secc. 6)."
    )


def _metric_table(tables: dict, suffix: str, title: str) -> str:
    """Una tabla por METRICA (`suffix`: `""` = RMSE normalizada, `"_heavy"`
    = perdida cola pesada, A5/ADR 012 secc. 6): calibrado vs. persistencia
    vs. Aurora sin calibrar vs. `a3_main` (columna extra solo si `tables`
    la trae -- `a3_main` es sin macro, no tiene metrica `_heavy` propia mas
    alla de la misma formula aplicada a sus errores crudos, asi que se
    muestra igual en las dos tablas)."""
    has_a3 = "a3_main" in tables
    header = "| variable | horizonte | calibrado | persistencia | Aurora sin calibrar |"
    sep = "|---|---|---|---|---|"
    if has_a3:
        header += " `a3_main` (sin macro) |"
        sep += "---|"
    lines = [f"### {title}", "", header, sep]
    for var in VARIABLES:
        for h in HORIZONS:
            key = f"{var}_h{h}{suffix}"
            cal_v = _fmt(tables["calibrated"].get(key, float("nan")))
            row = (
                f"| {VARIABLE_LABEL[var]} | {h} | {cal_v} "
                f"| {_fmt(tables['persistence'].get(key, float('nan')))} "
                f"| {_fmt(tables['aurora'].get(key, float('nan')))} |"
            )
            if has_a3:
                row += f" {_fmt(tables['a3_main'].get(key, float('nan')))} |"
            lines.append(row)
    if suffix == "":
        lines.append("")
        regime_row = (
            f"| regimen (acierto democracia/no) | - | "
            f"{_fmt(tables['calibrated'].get('regime_accuracy', float('nan')))} | - | "
            f"{_fmt(tables['aurora'].get('regime_accuracy', float('nan')))} |"
        )
        election_row = (
            f"| elecciones (acierto reelegido/derrotado) | - | "
            f"{_fmt(tables['calibrated'].get('election_accuracy', float('nan')))} | - | "
            f"{_fmt(tables['aurora'].get('election_accuracy', float('nan')))} |"
        )
        if has_a3:
            regime_row += f" {_fmt(tables['a3_main'].get('regime_accuracy', float('nan')))} |"
            election_row += f" {_fmt(tables['a3_main'].get('election_accuracy', float('nan')))} |"
        lines.append(regime_row)
        lines.append(election_row)
    return "\n".join(lines)


def _ended_before_table(tables: dict) -> str:
    """Fraccion de meses de arranque cuya corrida termino ANTES de cada
    horizonte (A5b, ADR 012 secc. 6: fix del bug de `a5_macro` -- antes de
    esto una corrida que hiperinflacionaba/colapsaba temprano no aportaba
    NINGUN error a los horizontes que no alcanzaba, y CMA-ES quedaba
    premiado por eso). `persistencia` no tiene nocion de "terminar antes"
    (no corre una simulacion), se omite."""
    has_a3 = "a3_main" in tables
    header = "| horizonte | calibrado | Aurora sin calibrar |"
    sep = "|---|---|---|"
    if has_a3:
        header += " `a3_main` (sin macro) |"
        sep += "---|"
    lines = [
        "### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)",
        "",
        header,
        sep,
    ]
    for h in HORIZONS:
        key = f"ended_before_h{h}"
        row = (
            f"| {h} | {_fmt(tables['calibrated'].get(key, float('nan')))} "
            f"| {_fmt(tables['aurora'].get(key, float('nan')))} |"
        )
        if has_a3:
            row += f" {_fmt(tables['a3_main'].get(key, float('nan')))} |"
        lines.append(row)
    return "\n".join(lines)


def _both_metric_tables(tables: dict) -> str:
    return "\n\n".join(
        [
            _n_header(tables),
            "",
            _metric_table(tables, "", "RMSE normalizada (misma formula que `a3_main`)"),
            "",
            _metric_table(
                tables,
                "_heavy",
                "Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)",
            ),
            "",
            _ended_before_table(tables),
        ]
    )


def _by_regime_sections(by_regime: dict, params: list[Parameter]) -> list[str]:
    """Una seccion por GRUPO de regimen cambiario (ADR 017 secc. 4), con
    las mismas tablas que las secciones agregadas de train/holdout, mas el
    drift del vector de ESE grupo. Las secciones agregadas van arriba, en
    `## Train`/`## Holdout`: esto es el detalle."""
    lines: list[str] = [
        "",
        "## Por grupo de regimen cambiario",
        "",
        "Particion de los meses de arranque por el `fx_regime` REAL de `fx_regimes.csv` en `t0` "
        "(ADR 017 secc. 3). Cada grupo tiene su propio CMA-ES y su propio vector; las tablas "
        "agregadas de arriba puntuan cada mes con el vector de SU grupo.",
        "",
        "| grupo | meses de arranque (train) | meses de arranque (holdout) |",
        "|---|---:|---:|",
    ]
    for group in by_regime["groups"]:
        lines.append(
            f"| `{group}`"
            f"{' (default)' if group == by_regime['default_group'] else ''} "
            f"| {by_regime['n_by_group_train'].get(group, 0)} "
            f"| {by_regime['n_by_group_holdout'].get(group, 0)} |"
        )
    for group in by_regime["groups"]:
        lines += [
            "",
            f"### Grupo `{group}` -- Train",
            "",
            _both_metric_tables(by_regime["train"][group]),
            "",
            f"### Grupo `{group}` -- Holdout",
            "",
            _both_metric_tables(by_regime["holdout"][group]),
            "",
            f"### Grupo `{group}` -- Drift de parametros (Aurora -> calibrado)",
            "",
            _drift_table(params, by_regime["x_by_group"][group]),
        ]
    return lines


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
    extra_notes: list[str] | None = None,
    by_regime: dict | None = None,
) -> None:
    from republica.calibration.run import input_data_hash

    include_macro = any(p.group == "macro" for p in params)
    loss = getattr(cfg, "loss", "rmse")
    weights = getattr(cfg, "weights", None)
    macro_note = (
        "Vector de calibracion CON el grupo `macro` (A5, ADR 012 secc. 6): simula con "
        "`step_macro_economy` (regimen cambiario efectivo + balance de pagos), "
        "`fx_regime=pack.fx_regime_auto` (regimen real de cada fecha, `fx_regimes.csv`) y el "
        "bloque bimonetario viejo DESACTIVADO (`engine/simulation.py::run` lo apaga en cuanto "
        "hay `macro_coefficients`, ver Notas de implementacion del ADR 012)."
        if include_macro
        else "Vector de calibracion SIN el grupo `macro` (bloque bimonetario viejo, ADR 011): "
        "compatibilidad con `a3_main`."
    )
    holdout_order_note = (
        "El holdout (`" + cfg.holdout_start + ":" + cfg.holdout_end + "`) es ANTERIOR en el "
        "calendario al train (`" + cfg.train_start + ":" + cfg.train_end + "`) -- a proposito "
        "(A5, ADR 012 secc. 6): el holdout es la hiperinflacion/convertibilidad temprana "
        "(1983-1991), nunca vista por esta estructura de precios/regimen cambiario; el orden "
        "cronologico no importa para el protocolo de honestidad, solo que el holdout se corra "
        "UNA sola vez, DESPUES de fijar los coeficientes con train."
        if cfg.holdout_start < cfg.train_start
        else "Holdout corrido UNA SOLA VEZ, al final, despues de fijar los coeficientes con "
        "train -- protocolo de honestidad, PLAN_ARGENTINA.md #0.3/#4."
    )
    weights_note = (
        "Pesos por variable del objetivo (`--weights`, ADR 017 secc. 5): `"
        + ", ".join(f"{k}={v}" for k, v in sorted(weights.items()))
        + "`. Afectan SOLO el escalar que minimiza CMA-ES; las tablas de abajo muestran cada "
        "variable SIN ponderar. Una corrida con pesos no es comparable con una sin pesos."
        if weights
        else "Pesos por variable del objetivo: todos en 1.0 (default, `--weights` sin usar)."
    )
    by_regime_note = (
        "Calibracion POR REGIMEN CAMBIARIO (`--by-regime`, ADR 017 secc. 3): un CMA-ES por "
        f"grupo ({', '.join('`' + g + '`' for g in by_regime['groups'])}), con "
        f"{by_regime['budget_per_group']} evaluaciones de presupuesto CADA UNO, particionando "
        "los meses de arranque por el `fx_regime` real de `fx_regimes.csv` en `t0` (`crawl` va "
        "con `peg`: `world/economy.py::step_macro_economy` los trata en la MISMA rama). Vector "
        f"`default` = el del grupo con mas meses de arranque de train: `"
        f"{by_regime['default_group']}`."
        if by_regime is not None
        else "Calibracion con UN SOLO vector para toda la ventana (sin `--by-regime`)."
    )
    budget_line = (
        f"Presupuesto: {by_regime['budget_per_group']} evaluaciones POR GRUPO "
        f"({len(by_regime['groups'])} grupos; usadas en total: {result.evaluations}). "
        if by_regime is not None
        else f"Presupuesto: {cfg.budget} evaluaciones (usadas: {result.evaluations}). "
    )

    lines = [
        f"# Calibracion Argentina -- run `{cfg.run_id}`",
        "",
        f"Pais: `{cfg.country_id}`. Train: `{cfg.train_start}:{cfg.train_end}`. "
        f"Holdout: `{cfg.holdout_start}:{cfg.holdout_end}`. {holdout_order_note}",
        budget_line
        + f"Stride: {cfg.stride} meses. lambda_reg: {cfg.lambda_reg}. Semilla: {cfg.seed}. "
        f"Perdida optimizada por CMA-ES: `{loss}` (el reporte muestra ambas metricas, RMSE y "
        "cola pesada, para cualquier corrida -- A5, ADR 012 secc. 6).",
        f"Tiempo de pared del optimizador: {result.wall_seconds:.1f}s.",
        f"Hash de los datos de entrada (`history/*.csv` + `politics/*.csv`): "
        f"`{input_data_hash(cfg.country_id)}`.",
        "",
        macro_note,
        "",
        by_regime_note,
        "",
        weights_note,
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
        "## Train" + (" (AGREGADO: cada mes con el vector de su grupo)" if by_regime else ""),
        "",
        _both_metric_tables(train_tables),
        "",
        "## Holdout" + (" (AGREGADO: cada mes con el vector de su grupo)" if by_regime else ""),
        "",
        _both_metric_tables(holdout_tables),
    ]
    if by_regime is not None:
        lines += _by_regime_sections(by_regime, params)
    lines += [
        "",
        "## Drift de parametros (Aurora -> calibrado)",
        "",
        "Top 15 por magnitud de drift, en unidades del RANGO permitido de cada parametro "
        "(`(calibrado - aurora) / (hi - lo)`; +-0.5 es la mitad del rango explorable). "
        "Tabla completa en `coefficients.json`.",
        "",
        _drift_table(params, calibrated_x),
    ]
    if extra_notes:
        lines += ["", "## Notas adicionales de esta corrida", ""]
        lines += [f"- {note}" for note in extra_notes]
    lines += [
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
