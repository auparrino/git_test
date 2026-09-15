"""`republica experiment report <dir>` (ADR 008 secc. 4): lee `metrics.csv`
(escrito por `experiments/runner.py`) y produce `<dir>/report.md` -- tabla
por brazo (N, outcomes, mediana e IC bootstrap 95 % de cada metrica),
diferencia entre brazos (IC de la diferencia + Cliff's delta) o, si el
experimento tiene un `sweep` de 2 dimensiones (`fiscal_rule`), una grilla
de calor en Markdown -- y graficos PNG si `matplotlib` esta instalado (si
no, la tabla ya escrita alcanza). Termina siempre con la seccion
"Limitaciones" (frase fija, ADR literal).

`matplotlib`/`pandas` se importan perezosamente DENTRO de las funciones que
los usan: `experiment report` sin el extra `[analysis]` instalado sigue
produciendo `report.md` completo (con tablas en vez de PNG)."""

from __future__ import annotations

import csv
import random
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from republica.experiments.config import ExperimentConfig
from republica.experiments.runner import META_NAME, METRICS_NAME

BOOTSTRAP_ITERS = 1000

#: Outcomes de crisis (`world/events.py::check_termination`, ADR secc. 4
#: "mapa de calor supervivencia x inflacion"): con `features.elections`
#: prendido (el default de los 3 experimentos canonicos), una corrida que
#: llega al fin del mandato SIEMPRE termina en `reelected`/`defeated` (hay
#: eleccion en el mes `term_length`, nunca en `survived` -- ver
#: `engine.simulation.OUTCOMES`), asi que "supervivencia" en el mapa de
#: calor no puede ser literalmente `outcome == "survived"` (daria 0 % en
#: cualquier corrida con elecciones): se define como "no termino en una
#: crisis" (`collapse`/`hyperinflation`), que es lo que varia de verdad
#: entre celdas del sweep de `fiscal_rule`.
_CRISIS_OUTCOMES = frozenset({"collapse", "hyperinflation"})


def _survived(outcome: str | None) -> bool:
    return outcome is not None and outcome not in _CRISIS_OUTCOMES


#: Frase fija obligatoria (ADR secc. 4, literal).
LIMITATIONS_SENTENCE = (
    "Estos resultados describen el comportamiento de República Artificial "
    "bajo sus reglas; no son evidencia sobre economías reales."
)

#: Columnas numericas de `metrics.csv` que se resumen con mediana + IC
#: (todas menos `outcome`/`election_winner`, categoricas, y
#: `election_turnover`, booleana -- se reporta aparte como tasa).
NUMERIC_METRICS: tuple[str, ...] = (
    "inflation_annual_final",
    "gdp_growth_mean",
    "unemployment_final",
    "approval_final",
    "stability_min",
    "reserves_min",
    "authority_violations",
    "perception_gap_mean",
    "agreements_broken",
)


def bootstrap_ci_median(
    samples: list[float], *, iters: int = BOOTSTRAP_ITERS, seed: int = 0
) -> tuple[float, float] | None:
    """IC 95 % por bootstrap de la MEDIANA (ADR secc. 4: "mediana e IC
    bootstrap"; `evals/metrics.py::bootstrap_ci` es del promedio, para las
    metricas de eval -- aca se resamplea y se toma la mediana de cada
    resample). `None` con menos de 2 muestras."""
    if len(samples) < 2:
        return None
    rng = random.Random(seed)
    n = len(samples)
    medians = [statistics.median(samples[rng.randrange(n)] for _ in range(n)) for _ in range(iters)]
    medians.sort()
    lo = medians[int(0.025 * iters)]
    hi = medians[min(iters - 1, int(0.975 * iters))]
    return (lo, hi)


def bootstrap_ci_diff_median(
    a: list[float], b: list[float], *, iters: int = BOOTSTRAP_ITERS, seed: int = 0
) -> tuple[float, float] | None:
    """IC 95 % por bootstrap de `mediana(b) - mediana(a)` (diferencia entre
    brazos, ADR secc. 4)."""
    if len(a) < 2 or len(b) < 2:
        return None
    rng = random.Random(seed)
    na, nb = len(a), len(b)
    diffs = []
    for _ in range(iters):
        ra = [a[rng.randrange(na)] for _ in range(na)]
        rb = [b[rng.randrange(nb)] for _ in range(nb)]
        diffs.append(statistics.median(rb) - statistics.median(ra))
    diffs.sort()
    lo = diffs[int(0.025 * iters)]
    hi = diffs[min(iters - 1, int(0.975 * iters))]
    return (lo, hi)


def cliffs_delta(a: list[float], b: list[float]) -> float | None:
    """Tamano de efecto no parametrico de Cliff (`b` vs. `a`): `(#b>a -
    #b<a) / (len(a)*len(b))`, en `[-1, 1]`. `0` = sin diferencia
    estocastica, `+-1` = separacion total (todo `b` mayor/menor que todo
    `a`). `None` si algun lado esta vacio."""
    if not a or not b:
        return None
    gt = sum(1 for y in b for x in a if y > x)
    lt = sum(1 for y in b for x in a if y < x)
    return (gt - lt) / (len(a) * len(b))


def _read_metrics_csv(out_dir: Path) -> list[dict[str, Any]]:
    path = out_dir / METRICS_NAME
    if not path.exists():
        raise FileNotFoundError(
            f"{path} no existe: correr 'republica experiment run/resume' antes de 'report' "
            "(ese comando escribe metrics.csv)."
        )
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            row: dict[str, Any] = {
                "experiment": raw["experiment"],
                "arm": raw["arm"],
                "seed": int(raw["seed"]),
                "outcome": raw.get("outcome") or None,
                "election_winner": raw.get("election_winner") or None,
            }
            for key in NUMERIC_METRICS:
                v = raw.get(key)
                row[key] = float(v) if v not in (None, "") else None
            turnover = raw.get("election_turnover")
            row["election_turnover"] = None if turnover in (None, "") else turnover == "True"
            rows.append(row)
    return rows


def _load_meta(out_dir: Path) -> dict[str, Any]:
    import json

    meta_path = out_dir / META_NAME
    if not meta_path.exists():
        raise FileNotFoundError(f"{meta_path} no existe (¿se corrio 'experiment run' antes?)")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _sweep_dims(meta: dict[str, Any]) -> list[str] | None:
    """`None` sin `sweep` (o con mas/menos de 2 dimensiones); si el
    experimento tiene exactamente 2 claves de `sweep` (compartidas por
    TODOS los brazos), devuelve esas 2 claves en orden estable -- se usan
    para la grilla de calor de `fiscal_rule` en vez de la tabla de
    diferencia entre brazos (pensada para 2, no para 9)."""
    key_sets = {frozenset(v.get("sweep_point") or {}) for v in meta["arms"].values()}
    if len(key_sets) != 1:
        return None
    keys = next(iter(key_sets))
    if len(keys) != 2:
        return None
    return sorted(keys)


def _fmt(v: float | None, nd: int = 2) -> str:
    return "-" if v is None else f"{v:.{nd}f}"


def _fmt_ci(ci: tuple[float, float] | None, nd: int = 2) -> str:
    return "-" if ci is None else f"[{ci[0]:.{nd}f}, {ci[1]:.{nd}f}]"


def _metric_columns(config: ExperimentConfig) -> list[str]:
    chosen = [m for m in config.metrics if m in NUMERIC_METRICS]
    return chosen or [m for m in NUMERIC_METRICS if m != "authority_violations"]


def _arm_table(rows: list[dict[str, Any]], arms: list[str], metric_cols: list[str]) -> str:
    lines = [
        "| brazo | N | outcomes | " + " | ".join(metric_cols) + " |",
        "|---|---|---|" + "---|" * len(metric_cols),
    ]
    for arm in arms:
        arm_rows = [r for r in rows if r["arm"] == arm]
        n = len(arm_rows)
        outcomes = Counter(r["outcome"] for r in arm_rows)
        outcomes_txt = ", ".join(f"{k}={v}" for k, v in outcomes.most_common())
        cells = []
        for col in metric_cols:
            samples = [r[col] for r in arm_rows if r[col] is not None]
            if not samples:
                cells.append("-")
                continue
            median = statistics.median(samples)
            ci = bootstrap_ci_median(samples)
            cells.append(f"{_fmt(median)} {_fmt_ci(ci)}")
        lines.append(f"| {arm} | {n} | {outcomes_txt} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _pairwise_table(rows: list[dict[str, Any]], arms: list[str], metric_cols: list[str]) -> str:
    lines = [
        "| brazos | metrica | mediana(a) | mediana(b) | IC diferencia (b-a) | Cliff's delta |",
        "|---|---|---|---|---|---|",
    ]
    for i, arm_a in enumerate(arms):
        for arm_b in arms[i + 1 :]:
            a_rows = [r for r in rows if r["arm"] == arm_a]
            b_rows = [r for r in rows if r["arm"] == arm_b]
            for col in metric_cols:
                a = [r[col] for r in a_rows if r[col] is not None]
                b = [r[col] for r in b_rows if r[col] is not None]
                if not a or not b:
                    continue
                diff_ci = bootstrap_ci_diff_median(a, b)
                delta = cliffs_delta(a, b)
                delta_txt = "-" if delta is None else f"{delta:+.2f}"
                lines.append(
                    f"| {arm_a} vs {arm_b} | {col} | {_fmt(statistics.median(a))} | "
                    f"{_fmt(statistics.median(b))} | {_fmt_ci(diff_ci)} | {delta_txt} |"
                )
    return "\n".join(lines)


def _short_dim(dim: str) -> str:
    """Nombre corto de una dimension de `sweep` para las tablas/graficos del
    reporte (`country.coefficients.c_f` -> `c_f`): el dot-path completo
    queda en `runs.meta.json`/las columnas de `overrides`, no hace falta
    repetirlo en cada encabezado de la grilla."""
    return dim.rsplit(".", 1)[-1]


def _heatmap_table(
    rows: list[dict[str, Any]], meta: dict[str, Any], dims: list[str], metric: str
) -> str:
    dim_a, dim_b = dims
    arm_points: dict[str, dict[str, Any]] = {
        name: v["sweep_point"] for name, v in meta["arms"].items()
    }
    vals_a = sorted({p[dim_a] for p in arm_points.values()})
    vals_b = sorted({p[dim_b] for p in arm_points.values()})
    grid: dict[tuple[Any, Any], list[float]] = {}
    for arm_name, point in arm_points.items():
        samples = [r[metric] for r in rows if r["arm"] == arm_name and r[metric] is not None]
        if samples:
            grid[(point[dim_a], point[dim_b])] = samples
    header = (
        f"| {_short_dim(dim_a)} \\ {_short_dim(dim_b)} | "
        + " | ".join(str(b) for b in vals_b)
        + " |"
    )
    sep = "|---|" + "---|" * len(vals_b)
    lines = [header, sep]
    for a in vals_a:
        cells = []
        for b in vals_b:
            samples = grid.get((a, b))
            cells.append(_fmt(statistics.median(samples)) if samples else "-")
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _survival_heatmap_table(
    rows: list[dict[str, Any]], meta: dict[str, Any], dims: list[str]
) -> str:
    dim_a, dim_b = dims
    arm_points: dict[str, dict[str, Any]] = {
        name: v["sweep_point"] for name, v in meta["arms"].items()
    }
    vals_a = sorted({p[dim_a] for p in arm_points.values()})
    vals_b = sorted({p[dim_b] for p in arm_points.values()})
    grid: dict[tuple[Any, Any], str] = {}
    for arm_name, point in arm_points.items():
        arm_rows = [r for r in rows if r["arm"] == arm_name]
        if arm_rows:
            survived = sum(1 for r in arm_rows if _survived(r["outcome"]))
            grid[(point[dim_a], point[dim_b])] = f"{100 * survived / len(arm_rows):.0f} %"
    header = (
        f"| {_short_dim(dim_a)} \\ {_short_dim(dim_b)} | "
        + " | ".join(str(b) for b in vals_b)
        + " |"
    )
    sep = "|---|" + "---|" * len(vals_b)
    lines = [header, sep]
    for a in vals_a:
        cells = [grid.get((a, b), "-") for b in vals_b]
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _try_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError:
        return None


def _plot_arm_comparison(
    plt: Any, rows: list[dict[str, Any]], arms: list[str], metric_cols: list[str], out_dir: Path
) -> list[Path]:
    paths = []
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    for col in metric_cols:
        medians = []
        errs_lo = []
        errs_hi = []
        for arm in arms:
            samples = [r[col] for r in rows if r["arm"] == arm and r[col] is not None]
            if not samples:
                medians.append(0.0)
                errs_lo.append(0.0)
                errs_hi.append(0.0)
                continue
            med = statistics.median(samples)
            ci = bootstrap_ci_median(samples)
            medians.append(med)
            errs_lo.append(med - ci[0] if ci else 0.0)
            errs_hi.append(ci[1] - med if ci else 0.0)
        fig, ax = plt.subplots(figsize=(5, 3.5))
        ax.bar(arms, medians, yerr=[errs_lo, errs_hi], capsize=4, color="#4C72B0")
        ax.set_title(col)
        ax.set_ylabel("mediana (IC 95 %)")
        fig.tight_layout()
        path = plots_dir / f"{col}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        paths.append(path)
    return paths


def _plot_heatmap(
    plt: Any,
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
    dims: list[str],
    metric: str,
    out_dir: Path,
    *,
    is_rate: bool = False,
) -> Path:
    dim_a, dim_b = dims
    arm_points = {name: v["sweep_point"] for name, v in meta["arms"].items()}
    vals_a = sorted({p[dim_a] for p in arm_points.values()})
    vals_b = sorted({p[dim_b] for p in arm_points.values()})
    matrix = [[float("nan")] * len(vals_b) for _ in vals_a]
    for arm_name, point in arm_points.items():
        arm_rows = [r for r in rows if r["arm"] == arm_name]
        if not arm_rows:
            continue
        ia = vals_a.index(point[dim_a])
        ib = vals_b.index(point[dim_b])
        if is_rate:
            survived = sum(1 for r in arm_rows if _survived(r["outcome"]))
            matrix[ia][ib] = 100 * survived / len(arm_rows)
        else:
            samples = [r[metric] for r in arm_rows if r[metric] is not None]
            matrix[ia][ib] = statistics.median(samples) if samples else float("nan")

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(matrix, cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(vals_b)), labels=[str(v) for v in vals_b])
    ax.set_yticks(range(len(vals_a)), labels=[str(v) for v in vals_a])
    ax.set_xlabel(dim_b)
    ax.set_ylabel(dim_a)
    title = "supervivencia (%)" if is_rate else metric
    ax.set_title(title)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    name = "survival_rate.png" if is_rate else f"{metric}.png"
    path = plots_dir / name
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def build_report(out_dir: str | Path) -> Path:
    """`republica experiment report <dir>` (ADR secc. 4): escribe
    `<dir>/report.md` (y, si `matplotlib` esta instalado, PNG en
    `<dir>/plots/`). Devuelve la ruta de `report.md`."""
    out = Path(out_dir)
    meta = _load_meta(out)
    config = ExperimentConfig.load(meta["experiment_yaml"])
    rows = _read_metrics_csv(out)
    arms = list(meta["arms"].keys())
    metric_cols = _metric_columns(config)

    plt = _try_matplotlib()
    plot_paths: list[Path] = []
    dims = _sweep_dims(meta)

    lines: list[str] = [
        f"# Reporte de experimento -- {config.name}",
        "",
        f"**Hipotesis / descripcion registrada:** {config.description or '(sin descripcion)'}",
        "",
        f"Semillas: {meta['seeds']['start']}"
        f"..{meta['seeds']['start'] + meta['seeds']['count'] - 1} "
        f"({meta['seeds']['count']} por brazo). Brazos: {len(arms)}. "
        f"Version del paquete: {meta.get('package_version', '?')}.",
        "",
        "## Por brazo",
        "",
        _arm_table(rows, arms, metric_cols),
        "",
    ]

    if dims is not None:
        lines += [
            f"## Mapa de calor ({dims[0]} x {dims[1]})",
            "",
            "Supervivencia (%):",
            "",
            _survival_heatmap_table(rows, meta, dims),
            "",
        ]
        if plt is not None:
            p = _plot_heatmap(plt, rows, meta, dims, "outcome", out, is_rate=True)
            plot_paths.append(p)
            lines.append(f"![supervivencia](plots/{p.name})")
            lines.append("")
        for col in metric_cols[:2]:
            lines += [f"{col} (mediana):", "", _heatmap_table(rows, meta, dims, col), ""]
            if plt is not None:
                p = _plot_heatmap(plt, rows, meta, dims, col, out, is_rate=False)
                plot_paths.append(p)
                lines.append(f"![{col}](plots/{p.name})")
                lines.append("")
    elif len(arms) >= 2:
        lines += [
            "## Diferencia entre brazos",
            "",
            _pairwise_table(rows, arms, metric_cols),
            "",
        ]
        if plt is not None:
            plot_paths.extend(_plot_arm_comparison(plt, rows, arms, metric_cols, out))
            lines.append("Graficos: " + ", ".join(f"`plots/{p.name}`" for p in plot_paths))
            lines.append("")

    if plt is None:
        lines += [
            "_matplotlib no esta instalado en este entorno: se omiten los PNG, las tablas de "
            "arriba tienen la misma informacion (instalar el extra `analysis` para los graficos)._",
            "",
        ]

    lines += ["## Limitaciones", "", LIMITATIONS_SENTENCE, ""]

    report_path = out / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


__all__ = [
    "LIMITATIONS_SENTENCE",
    "bootstrap_ci_diff_median",
    "bootstrap_ci_median",
    "build_report",
    "cliffs_delta",
]
