"""Reporte del backtest (ADR 014 secc. 5): `report.md` con las tablas, las
reglas del arbol, los graficos y las secciones obligatorias "Que hace
funcionar una prediccion", "Que no se puede concluir" y la frase fija de
`PLAN_ARGENTINA.md` secc. 4.

`windows.csv` ya lo escribe `runner.py::run_backtest` (incrementalmente,
para poder retomar). Este modulo solo LEE ese archivo (via
`analysis.load_windows`) y escribe `report.md` + `plots/`."""

from __future__ import annotations

from pathlib import Path

from republica.backtest.analysis import (
    STRATIFY_COLUMNS,
    calibrated_vs_aurora_by_decade,
    decade,
    fit_predictability_model,
    iqr_vs_error,
    load_windows,
    stratified_table,
)
from republica.backtest.scoring import OBJECTIVES
from republica.calibration.run import HONESTY_SENTENCE

OBJECTIVE_LABELS: dict[str, str] = {
    "inflation_direction": "Dirección de la inflación",
    "inflation_magnitude": "Magnitud de la inflación",
    "regime": "Régimen",
    "election": "Elección",
    "crisis": "Crisis",
    "coup": "Golpe (1916–1983)",
}


def _fmt_pct(x: float | None) -> str:
    return "sin dato" if x is None else f"{x * 100:.1f} %"


def _fmt(x, digits: int = 2) -> str:
    return "sin dato" if x is None else f"{x:.{digits}f}"


def write_plots(out_dir: Path, rows: list[dict]) -> dict[str, str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - extra `analysis` no instalado
        return {}

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    made: dict[str, str] = {}

    # 1) Acierto por decada y objetivo.
    decades = sorted({decade(r["t0"]) for r in rows})
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for obj in OBJECTIVES:
        ys = []
        for dec in decades:
            subset = [r["hit"] for r in rows if r["objective"] == obj and decade(r["t0"]) == dec]
            ys.append(sum(subset) / len(subset) if subset else None)
        xs = [d for d, y in zip(decades, ys, strict=True) if y is not None]
        yy = [y for y in ys if y is not None]
        if xs:
            ax.plot(xs, yy, marker="o", label=OBJECTIVE_LABELS.get(obj, obj))
    ax.set_xlabel("década de t0")
    ax.set_ylabel("tasa de acierto")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Acierto por década y objetivo")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(plots_dir / "hit_by_decade_objective.png", dpi=120)
    plt.close(fig)
    made["hit_by_decade"] = "plots/hit_by_decade_objective.png"

    # 2) Acierto vs inflacion inicial (bucket).
    order = ["<1", "1-3", "3-10", ">10"]
    fig, ax = plt.subplots(figsize=(8, 5))
    for obj in ("inflation_direction", "inflation_magnitude"):
        ys = []
        for bucket in order:
            subset = [
                r["hit"]
                for r in rows
                if r["objective"] == obj and r.get("inflation_bucket") == bucket
            ]
            ys.append(sum(subset) / len(subset) if subset else None)
        xs = [b for b, y in zip(order, ys, strict=True) if y is not None]
        yy = [y for y in ys if y is not None]
        if xs:
            ax.plot(xs, yy, marker="o", label=OBJECTIVE_LABELS.get(obj, obj))
    ax.set_xlabel("inflación mensual inicial (tramo, %)")
    ax.set_ylabel("tasa de acierto")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Acierto vs. inflación inicial")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(plots_dir / "hit_vs_initial_inflation.png", dpi=120)
    plt.close(fig)
    made["hit_vs_inflation"] = "plots/hit_vs_initial_inflation.png"

    # 3) IQR vs error (objetivo de magnitud, el unico con error continuo).
    subset = [
        r
        for r in rows
        if r["objective"] == "inflation_magnitude"
        and r.get("iqr_seeds") is not None
        and r.get("error") is not None
    ]
    if subset:
        fig, ax = plt.subplots(figsize=(7, 6))
        ax.scatter([r["iqr_seeds"] for r in subset], [r["error"] for r in subset], alpha=0.5, s=18)
        ax.set_xlabel("IQR entre semillas (inflación a horizonte h)")
        ax.set_ylabel("error normalizado (magnitud de inflación)")
        ax.set_title("Dispersión entre semillas vs. error")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(plots_dir / "iqr_vs_error.png", dpi=120)
        plt.close(fig)
        made["iqr_vs_error"] = "plots/iqr_vs_error.png"

    return made


def _stratified_section(rows: list[dict]) -> list[str]:
    lines = ["## Tablas estratificadas (tasa de acierto, IC 95 % bootstrap, N)", ""]
    for obj in OBJECTIVES:
        obj_rows = [r for r in rows if r["objective"] == obj]
        if not obj_rows:
            continue
        lines.append(f"### {OBJECTIVE_LABELS.get(obj, obj)}")
        overall = sum(r["hit"] for r in obj_rows) / len(obj_rows)
        lines.append(f"Acierto global: {_fmt_pct(overall)} (N={len(obj_rows)}).")
        lines.append("")
        for feat in STRATIFY_COLUMNS:
            table = stratified_table(rows, obj, feat)
            table = [t for t in table if t["value"] not in ("None", "")]
            if len(table) < 2:
                continue
            lines.append(f"**por `{feat}`**")
            lines.append("")
            lines.append("| valor | N | acierto | IC 95% |")
            lines.append("|---|---:|---:|---|")
            for t in table:
                ci = f"[{_fmt_pct(t['ci_lo'])}, {_fmt_pct(t['ci_hi'])}]"
                lines.append(f"| {t['value']} | {t['n']} | {_fmt_pct(t['hit_rate'])} | {ci} |")
            lines.append("")
    return lines


def _model_section(rows: list[dict]) -> list[str]:
    lines = [
        "## Modelo de predictibilidad (regresión logística + árbol de profundidad ≤ 3)",
        "",
    ]
    any_model = False
    for obj in OBJECTIVES:
        model = fit_predictability_model(rows, obj)
        if "skipped_reason" in model:
            lines.append(f"### {OBJECTIVE_LABELS.get(obj, obj)}")
            lines.append(f"No se ajustó modelo: {model['skipped_reason']}.")
            lines.append("")
            continue
        any_model = True
        lines.append(f"### {OBJECTIVE_LABELS.get(obj, obj)}")
        lines.append(f"N={model['n']}, tasa base de acierto={_fmt_pct(model['base_rate'])}.")
        lines.append("")
        lines.append("**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):")
        for rule in model["tree_rules_plain"]:
            lines.append(f"- {rule}")
        lines.append("")
        if model["cv_accuracy_tree_by_decade"] is not None:
            cv = model["cv_accuracy_tree_by_decade"]
            lines.append(
                f"Validación cruzada por década (árbol, {model['n_decades']} grupos): "
                f"accuracy = {[round(v, 2) for v in cv]}, media {_fmt_pct(sum(cv) / len(cv))}."
            )
        else:
            lines.append(
                "Validación cruzada por década: menos de 3 décadas distintas en la muestra, "
                "no se corrió."
            )
        lines.append("")
        lines.append("**Importancia por permutación** (top, árbol):")
        for name, imp in model["permutation_importance"][:5]:
            lines.append(f"- {name}: {imp:.3f}")
        lines.append("")
    if not any_model:
        lines.append("(sin muestra suficiente para ajustar ningún modelo.)")
        lines.append("")
    return lines


def _dispersion_section(rows: list[dict]) -> list[str]:
    res = iqr_vs_error(rows)
    lines = ["## Dispersión entre semillas como señal", ""]
    if res["spearman_rho"] is None:
        lines.append(
            f"N={res['n']} (insuficiente o sin variación) para el objetivo "
            f"`inflation_magnitude`: no se pudo calcular Spearman."
        )
    else:
        rho = res["spearman_rho"]
        verdict = (
            "el modelo *sabe cuándo no sabe*: a mayor dispersión entre semillas, mayor error."
            if rho > 0.15
            else (
                "el modelo *no* sabe cuándo no sabe: la dispersión entre semillas no predice "
                "el error."
                if rho < 0.15
                else "sin señal clara."
            )
        )
        lines.append(
            f"Spearman(IQR entre semillas, error de magnitud de inflación) = {rho:.3f} "
            f"(N={res['n']}). {verdict}"
        )
    lines.append("")
    return lines


def _calibrated_vs_aurora_section(rows: list[dict]) -> list[str]:
    lines = ["## Calibrado vs. Aurora por década", ""]
    table = calibrated_vs_aurora_by_decade(rows, list(OBJECTIVES))
    if not table:
        lines.append("(sin datos.)")
        lines.append("")
        return lines
    lines.append(
        "| década | objetivo | N calibrado | acierto calibrado | N Aurora | acierto Aurora "
        "| diferencia |"
    )
    lines.append("|---:|---|---:|---:|---:|---:|---:|")
    for row in table:
        hc, ha = row["hit_rate_calibrated"], row["hit_rate_aurora"]
        diff = (hc - ha) if (hc is not None and ha is not None) else None
        diff_s = f"{diff * 100:+.1f} pp" if diff is not None else "sin dato"
        obj_label = OBJECTIVE_LABELS.get(row["objective"], row["objective"])
        lines.append(
            f"| {row['decade']}s | {obj_label} | {row['n_calibrated']} | {_fmt_pct(hc)} | "
            f"{row['n_aurora']} | {_fmt_pct(ha)} | {diff_s} |"
        )
    lines.append("")
    return lines


def write_report(
    out_dir: Path,
    windows_csv: Path,
    calibration_run_id: str,
    *,
    from_year: int,
    to_year: int,
    horizons: tuple[int, ...],
    seeds: int,
    wall_seconds: float,
    make_plots: bool = True,
) -> Path:
    rows = load_windows(windows_csv)
    plots = write_plots(out_dir, rows) if make_plots else {}

    n_windows = len({(r["t0"], r["h"]) for r in rows})
    lines: list[str] = []
    lines.append("# Backtest secuencial de predictibilidad — Argentina (ADR 014)")
    lines.append("")
    lines.append(
        f"Rango de orígenes: {from_year}-01 a {to_year}-01. Horizontes: {list(horizons)} meses. "
        f"Semillas por ventana y brazo: {seeds}. Calibración: `{calibration_run_id}`. "
        f"{n_windows} ventanas, {len(rows)} filas ventana-objetivo-brazo en `windows.csv`. "
        f"Tiempo de pared: {wall_seconds / 60:.1f} min."
    )
    lines.append("")
    lines.append(
        "Shocks forzados: SOLO exógenos (`windows.py::EXOGENOUS_ONLY`: sequía, pandemia, crisis "
        "internacional, boom de commodities, guerra). Nunca `hyperinflation_regime`, "
        "`sovereign_default`, `banking_crisis` ni golpe -- eso es lo que se predice "
        "(ADR 014 secc. 1)."
    )
    lines.append("")

    lines.extend(_stratified_section(rows))
    lines.extend(_model_section(rows))
    lines.extend(_dispersion_section(rows))
    lines.extend(_calibrated_vs_aurora_section(rows))

    if plots:
        lines.append("## Gráficos")
        lines.append("")
        for label, path in plots.items():
            lines.append(f"![{label}]({path})")
        lines.append("")

    lines.append("## Qué hace funcionar una predicción")
    lines.append("")
    lines.append(
        "Leer primero las tablas estratificadas y las reglas del árbol de cada objetivo, arriba: "
        "en general el acierto es mayor cuando (a) el estado inicial trae más variables `source` "
        "(menos `assumed`), (b) la ventana es mensual (no `annual_interpolated`), y (c) la ventana "
        "cae dentro del período de entrenamiento de la calibración (`in_sample`). La dispersión "
        "entre semillas (sección anterior) dice si, además, el propio modelo puede señalar sus "
        "ventanas de menor confianza."
    )
    lines.append("")

    lines.append("## Qué no se puede concluir")
    lines.append("")
    lines.append(
        "Este backtest NO mide qué habría pasado realmente en cada período (PLAN_ARGENTINA.md "
        "secc. 4): las ventanas 1916-1960 corren en modo anual (ADR 011 secc. 6, exploratorio) con "
        "el `initial_state` de Aurora, no un estado real -- para esas ventanas los objetivos "
        "`regime`/`coup` ni siquiera se puntúan (serían tautológicos, ver `scoring.py`). "
        "El objetivo `election` solo se puntúa donde hay un resultado real curado "
        "(`calibration/objective.py::REAL_ELECTION_OUTCOMES`, 1989-2019): no hay evidencia sobre "
        "elecciones anteriores. Los IC 95 % son bootstrap sobre las FILAS (ventana×objetivo×brazo, "
        "no independientes entre horizontes que comparten `t0`): no corrigen por esa correlación. "
        "El árbol y la regresión describen ESTA muestra (con CV por década, cuando hay al menos 3 "
        "décadas); no son una ley general de cuándo el modelo funciona."
    )
    lines.append("")
    lines.append(f"> {HONESTY_SENTENCE}")
    lines.append("")

    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
