"""Clasificacion a posteriori del hito 1 (ADR 010 secc. 6-7): el UNICO lugar
del paquete `core/` donde el vocabulario institucional de la lista negra
(secc. 3 del ADR) puede aparecer como identificador -- porque etiquetar
"esto se comporta como un medio de intercambio" es, por definicion,
posterior a la corrida, nunca una entrada de `world.py`/`exchange.py`.

`classify_run` opera sobre la serie de metricas por turno que ya devuelve
`exchange.step` (ADR secc. 6): "bien con `acceptance_rate` > 0.5 sostenida
>= 50 turnos" (medio de intercambio), Herfindahl de intermediarios, fraccion
de intercambios indirectos, privacion media y Gini de inventario, global y
por region. `build_report` arma el `report.md` del hito con H1-H4."""

from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path
from typing import Any

#: Test de contaminacion (ADR secc. 3, literal): estas palabras NO pueden
#: aparecer como identificador en ningun otro archivo de `core/` -- ver
#: `tests/test_core.py::test_no_institutional_contamination`. Viven aca
#: porque este modulo es la unica excepcion permitida (etiquetado a
#: posteriori, no hardcodeado en la fisica).
BLACKLIST_WORDS: tuple[str, ...] = (
    "money",
    "price",
    "state",
    "government",
    "party",
    "union",
    "firm",
    "bank",
    "vote",
    "tax",
    "law",
    "president",
    "market",
    "property",
    "contract",
)

#: Umbral y ventana de "medio de intercambio" (ADR secc. 6, literal).
MEDIUM_THRESHOLD = 0.5
MEDIUM_SUSTAIN_TURNS = 50
#: Ultimos N turnos usados como "estado estacionario" para promediar
#: privacion/Gini/aceptacion final de una corrida (no forma parte del ADR
#: literal; documentado en "Notas de implementacion").
STEADY_STATE_WINDOW = 100

#: Frase fija obligatoria en todo reporte (ADR 010 secc. 9, remite a ADR 008
#: secc. 4 literal).
LIMITATIONS_SENTENCE = (
    "Estos resultados describen el comportamiento de República Artificial "
    "bajo sus reglas; no son evidencia sobre economías reales."
)


def _longest_sustained_streak(above: list[bool], min_len: int) -> tuple[int, int] | None:
    """Primer tramo de >= `min_len` turnos consecutivos en `True`.
    Devuelve `(turno_de_inicio, largo)` o `None` si no hay ninguno."""
    start = None
    best: tuple[int, int] | None = None
    for t, ok in enumerate(above):
        if ok:
            if start is None:
                start = t
        else:
            if start is not None and t - start >= min_len:
                length = t - start
                if best is None or start < best[0]:
                    best = (start, length)
            start = None
    if start is not None and len(above) - start >= min_len:
        length = len(above) - start
        if best is None or start < best[0]:
            best = (start, length)
    return best


def _medium_of_exchange(
    acceptance_series: list[list[float]], good_names: tuple[str, ...]
) -> tuple[str | None, int | None]:
    """`acceptance_series[t][g]` = `acceptance_rate` del bien `g` en el
    turno `t`. Devuelve `(bien, turno_de_emergencia)` -- el bien cuya racha
    sostenida `> MEDIUM_THRESHOLD` por `>= MEDIUM_SUSTAIN_TURNS` turnos
    empieza mas temprano; `(None, None)` si ninguno lo logra."""
    best: tuple[str | None, int | None] = (None, None)
    best_start = None
    for gi, name in enumerate(good_names):
        above = [row[gi] > MEDIUM_THRESHOLD for row in acceptance_series]
        streak = _longest_sustained_streak(above, MEDIUM_SUSTAIN_TURNS)
        if streak is None:
            continue
        start, _length = streak
        if best_start is None or start < best_start:
            best_start = start
            best = (name, start)
    return best


def classify_run(metrics: list[dict[str, Any]], good_names: tuple[str, ...]) -> dict[str, Any]:
    """Clasifica UNA corrida a partir de su lista de metricas por turno
    (`TurnMetrics.to_dict()` en orden). Ver el modulo para que se reporta."""
    if not metrics:
        return {
            "medium_of_exchange": None,
            "emergence_turn": None,
            "herfindahl_intermediates": 0.0,
            "indirect_trade_share": 0.0,
            "mean_deprivation": 0.0,
            "mean_deprivation_by_region": [],
            "inventory_gini": 0.0,
            "inventory_gini_by_region": [],
            "medium_of_exchange_by_region": [],
        }

    n_regions = len(metrics[0]["deprivation_mean_by_region"])
    acceptance_series = [m["acceptance_rate_by_good"] for m in metrics]
    medium, emergence_turn = _medium_of_exchange(acceptance_series, good_names)

    medium_by_region: list[str | None] = []
    for ri in range(n_regions):
        series_r = [m["acceptance_rate_by_good_region"][ri] for m in metrics]
        good_r, _turn_r = _medium_of_exchange(series_r, good_names)
        medium_by_region.append(good_r)

    total_intermediate = Counter()
    total_direct = 0
    total_indirect = 0
    for m in metrics:
        for gi, count in enumerate(m["intermediate_by_good"]):
            total_intermediate[good_names[gi]] += count
        total_direct += m["trades_direct"]
        total_indirect += m["trades_indirect"]

    intermediate_total = sum(total_intermediate.values())
    if intermediate_total > 0:
        herfindahl = sum((c / intermediate_total) ** 2 for c in total_intermediate.values())
    else:
        herfindahl = 0.0
    all_trades = total_direct + total_indirect
    indirect_share = (total_indirect / all_trades) if all_trades > 0 else 0.0

    tail = metrics[-STEADY_STATE_WINDOW:]
    mean_deprivation = statistics.fmean(m["deprivation_mean"] for m in tail)
    mean_deprivation_by_region = [
        statistics.fmean(m["deprivation_mean_by_region"][ri] for m in tail)
        for ri in range(n_regions)
    ]
    inventory_gini = statistics.fmean(m["gini"] for m in tail)
    inventory_gini_by_region = [
        statistics.fmean(m["gini_by_region"][ri] for m in tail) for ri in range(n_regions)
    ]

    return {
        "medium_of_exchange": medium,
        "emergence_turn": emergence_turn,
        "herfindahl_intermediates": herfindahl,
        "indirect_trade_share": indirect_share,
        "mean_deprivation": mean_deprivation,
        "mean_deprivation_by_region": mean_deprivation_by_region,
        "inventory_gini": inventory_gini,
        "inventory_gini_by_region": inventory_gini_by_region,
        "medium_of_exchange_by_region": medium_by_region,
    }


# --------------------------------------------------------------------------
# Reporte H1-H4 (ADR 010 secc. 7 "Hipotesis registradas antes de correr")
# --------------------------------------------------------------------------

#: H2: bienes esperados como "casi siempre" dominantes (durables,
#: divisibles, transportables) vs. los que "casi nunca" dominan.
_H2_EXPECTED = ("sal", "conchas", "tela")
_H2_UNEXPECTED = ("grano", "pescado")


def _load_runs(directory: Path) -> list[dict[str, Any]]:
    import json

    runs = []
    for p in sorted(Path(directory).glob("*.json")):
        try:
            runs.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return runs


def _emerged(run: dict[str, Any]) -> bool:
    return run.get("classification", {}).get("medium_of_exchange") is not None


def _emergence_turn(run: dict[str, Any]) -> int | None:
    return run.get("classification", {}).get("emergence_turn")


def _fmt_ci(ci: tuple[float, float] | None) -> str:
    if ci is None:
        return "s/d"
    return f"[{ci[0]:.3g}, {ci[1]:.3g}]"


def _check_h1(main_runs: list[dict[str, Any]]) -> tuple[bool, str]:
    n = len(main_runs)
    if n == 0:
        return False, "sin corridas."
    emerged = [r for r in main_runs if _emerged(r)]
    fast = [r for r in emerged if (t := _emergence_turn(r)) is not None and t < 300]
    frac = len(fast) / n
    verdict = frac > 0.6
    return verdict, (
        f"{len(fast)}/{n} corridas ({frac:.1%}) con medio de intercambio emergido en < 300 turnos "
        f"(umbral H1: > 60 %); {len(emerged)}/{n} emergieron en algun momento de la corrida."
    )


def _check_h2(main_runs: list[dict[str, Any]]) -> tuple[bool, str]:
    emerged = [r for r in main_runs if _emerged(r)]
    if not emerged:
        return False, (
            "ninguna corrida tuvo medio de intercambio: no hay bien dominante que evaluar."
        )
    counts = Counter(r["classification"]["medium_of_exchange"] for r in emerged)
    n = len(emerged)
    expected = sum(counts.get(g, 0) for g in _H2_EXPECTED)
    unexpected = sum(counts.get(g, 0) for g in _H2_UNEXPECTED)
    dist = ", ".join(f"{g}: {c}/{n} ({c / n:.1%})" for g, c in counts.most_common())
    verdict = expected / n > 0.6 and unexpected / n < 0.4 if n else False
    return verdict, f"distribucion del bien dominante: {dist}."


def _check_h3(shell_sweep: dict[str, list[dict[str, Any]]]) -> tuple[bool, str]:
    if not shell_sweep:
        return False, "sin corridas del barrido de abundancia de conchas."
    levels = sorted(shell_sweep, key=lambda k: float(k))
    rows = []
    conchas_share_by_level = {}
    for level in levels:
        runs = shell_sweep[level]
        emerged = [r for r in runs if _emerged(r)]
        conchas_wins = sum(
            1 for r in emerged if r["classification"]["medium_of_exchange"] == "conchas"
        )
        share = conchas_wins / len(runs) if runs else 0.0
        conchas_share_by_level[level] = share
        rows.append(f"abundancia={level}: conchas gano en {conchas_wins}/{len(runs)} ({share:.1%})")
    scarce = levels[0]
    abundant = levels[-1]
    verdict = conchas_share_by_level[scarce] > conchas_share_by_level[abundant]
    return verdict, "; ".join(rows) + (
        f". Escasez ({scarce}) favorece a conchas mas que abundancia ({abundant}): "
        f"{'si' if verdict else 'no'} (H3 predice que si)."
    )


def _check_h4(transport_sweep: dict[str, list[dict[str, Any]]]) -> tuple[bool, str]:
    if not transport_sweep:
        return False, "sin corridas del barrido de costo de transporte."
    levels = sorted(transport_sweep, key=lambda k: float(k))
    rows = []
    median_turn_by_level = {}
    for level in levels:
        runs = transport_sweep[level]
        turns = [t for r in runs if (t := _emergence_turn(r)) is not None]
        median = statistics.median(turns) if turns else None
        median_turn_by_level[level] = median
        rows.append(
            f"transporte={level}: mediana turno de emergencia="
            f"{median if median is not None else 's/d'} ({len(turns)}/{len(runs)} emergieron)"
        )
    known = [
        median_turn_by_level[level] for level in levels if median_turn_by_level[level] is not None
    ]
    verdict = len(known) == len(levels) and known == sorted(known) and known[0] != known[-1]
    return verdict, "; ".join(rows) + (
        f". Mediana del turno de emergencia {'crece' if verdict else 'no crece de forma monotona'} "
        "con el costo de transporte (H4 predice que si)."
    )


def build_report(
    main_dir: Path,
    *,
    shell_sweep_dir: Path | None = None,
    transport_sweep_dir: Path | None = None,
    out_path: Path | None = None,
) -> str:
    """Arma `report.md` (ADR 008 secc. 4 style + ADR 010 secc. 7 DoD): tabla
    de la corrida de 100 semillas, H1-H4 marcadas CUMPLIDA/NO CUMPLIDA con
    numeros, IC bootstrap, graficos si hay matplotlib, y la frase de
    "Limitaciones" obligatoria (ADR secc. 9)."""
    from republica.experiments.report import bootstrap_ci_median

    main_runs = _load_runs(main_dir)
    shell_sweep: dict[str, list[dict[str, Any]]] = {}
    shell_dir = shell_sweep_dir or (main_dir / "shell_sweep")
    if shell_dir.exists():
        for sub in sorted(shell_dir.iterdir()):
            if sub.is_dir():
                shell_sweep[sub.name] = _load_runs(sub)

    transport_sweep: dict[str, list[dict[str, Any]]] = {}
    transport_dir = transport_sweep_dir or (main_dir / "transport_sweep")
    if transport_dir.exists():
        for sub in sorted(transport_dir.iterdir()):
            if sub.is_dir():
                transport_sweep[sub.name] = _load_runs(sub)

    h1_ok, h1_msg = _check_h1(main_runs)
    h2_ok, h2_msg = _check_h2(main_runs)
    h3_ok, h3_msg = _check_h3(shell_sweep)
    h4_ok, h4_msg = _check_h4(transport_sweep)

    def verdict_label(ok: bool) -> str:
        return "CUMPLIDA" if ok else "NO CUMPLIDA"

    lines: list[str] = []
    lines.append("# Reporte hito 1 — ¿emerge un medio de intercambio? (ADR 010 secc. 7)")
    lines.append("")
    lines.append(f"Corridas base analizadas: {len(main_runs)}.")
    lines.append("")
    lines.append(
        "Una fila por corrida (base + barridos H3/H4) en `summary.csv`, junto a este reporte."
    )
    lines.append("")
    lines.append("## Hipotesis")
    lines.append("")
    lines.append(f"- **H1** ({verdict_label(h1_ok)}): {h1_msg}")
    lines.append(f"- **H2** ({verdict_label(h2_ok)}): {h2_msg}")
    lines.append(f"- **H3** ({verdict_label(h3_ok)}): {h3_msg}")
    lines.append(f"- **H4** ({verdict_label(h4_ok)}): {h4_msg}")
    lines.append("")

    if main_runs:
        lines.append("## Metricas de la corrida base (mediana e IC bootstrap 95 %)")
        lines.append("")
        lines.append("| Metrica | Mediana | IC 95 % |")
        lines.append("|---|---|---|")
        for key, label in (
            ("herfindahl_intermediates", "Herfindahl de intermediarios"),
            ("indirect_trade_share", "Fraccion de intercambios indirectos"),
            ("mean_deprivation", "Privacion media (estado estacionario)"),
            ("inventory_gini", "Gini de inventario (estado estacionario)"),
        ):
            samples = [r["classification"][key] for r in main_runs]
            median = statistics.median(samples)
            ci = bootstrap_ci_median(samples)
            lines.append(f"| {label} | {median:.4g} | {_fmt_ci(ci)} |")
        lines.append("")

        counts = Counter(
            r["classification"]["medium_of_exchange"] for r in main_runs if _emerged(r)
        )
        if counts:
            lines.append("## Distribucion del bien dominante (100 semillas)")
            lines.append("")
            lines.append("| Bien | Corridas | % |")
            lines.append("|---|---|---|")
            n_emerged = sum(counts.values())
            for good, c in counts.most_common():
                lines.append(f"| {good} | {c} | {c / n_emerged:.1%} |")
            lines.append("")

    if out_path is not None and main_runs:
        _write_summary_csv(main_runs, shell_sweep, transport_sweep, out_path.parent / "summary.csv")

    plot_paths = _maybe_plot(main_runs, shell_sweep, transport_sweep, out_path)
    if plot_paths:
        lines.append("## Graficos")
        lines.append("")
        for p in plot_paths:
            lines.append(f"![{p.stem}]({p.name})")
        lines.append("")

    lines.append("## Limitaciones")
    lines.append("")
    lines.append(LIMITATIONS_SENTENCE)
    lines.append("")

    report = "\n".join(lines)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    return report


def _write_summary_csv(
    main_runs: list[dict[str, Any]],
    shell_sweep: dict[str, list[dict[str, Any]]],
    transport_sweep: dict[str, list[dict[str, Any]]],
    out_path: Path,
) -> None:
    """`<dir>/summary.csv`: una fila por corrida (todos los grupos, con la
    columna `group` para distinguir la base del barrido H3/H4) -- lo que se
    versiona en `experiments/results/core_hito1/` (el JSON crudo por semilla
    NO se versiona, ver `.gitignore`)."""
    import csv

    fields = [
        "group",
        "level",
        "seed",
        "medium_of_exchange",
        "emergence_turn",
        "herfindahl_intermediates",
        "indirect_trade_share",
        "mean_deprivation",
        "inventory_gini",
    ]
    groups: list[tuple[str, str, list[dict[str, Any]]]] = [("main", "", main_runs)]
    for level, runs in shell_sweep.items():
        groups.append(("shell_sweep", level, runs))
    for level, runs in transport_sweep.items():
        groups.append(("transport_sweep", level, runs))

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for group, level, runs in groups:
            for r in runs:
                c = r.get("classification", {})
                writer.writerow(
                    {
                        "group": group,
                        "level": level,
                        "seed": r.get("seed"),
                        "medium_of_exchange": c.get("medium_of_exchange") or "",
                        "emergence_turn": c.get("emergence_turn"),
                        "herfindahl_intermediates": c.get("herfindahl_intermediates"),
                        "indirect_trade_share": c.get("indirect_trade_share"),
                        "mean_deprivation": c.get("mean_deprivation"),
                        "inventory_gini": c.get("inventory_gini"),
                    }
                )


def _maybe_plot(
    main_runs: list[dict[str, Any]],
    shell_sweep: dict[str, list[dict[str, Any]]],
    transport_sweep: dict[str, list[dict[str, Any]]],
    out_path: Path | None,
) -> list[Path]:
    """PNG si `matplotlib` esta instalado (import perezoso, ADR 008 secc.
    4); si no, el reporte ya escribio las tablas y esta funcion no hace
    nada."""
    if out_path is None or not main_runs:
        return []
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []

    plots_dir = out_path.parent / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    counts = Counter(r["classification"]["medium_of_exchange"] for r in main_runs if _emerged(r))
    if counts:
        fig, ax = plt.subplots()
        goods, values = zip(*counts.most_common(), strict=True)
        ax.bar(goods, values)
        ax.set_ylabel("corridas")
        ax.set_title("Bien dominante (100 semillas)")
        fig.tight_layout()
        p = plots_dir / "medium_of_exchange_distribution.png"
        fig.savefig(p)
        plt.close(fig)
        paths.append(p)

    if shell_sweep:
        levels = sorted(shell_sweep, key=lambda x: float(x))
        shares = []
        for level in levels:
            runs = shell_sweep[level]
            emerged = [r for r in runs if _emerged(r)]
            wins = sum(1 for r in emerged if r["classification"]["medium_of_exchange"] == "conchas")
            shares.append(wins / len(runs) if runs else 0.0)
        fig, ax = plt.subplots()
        ax.plot([float(x) for x in levels], shares, marker="o")
        ax.set_xlabel("abundancia de conchas (multiplicador)")
        ax.set_ylabel("fraccion de corridas donde conchas domina")
        ax.set_title("H3: escasez vs. abundancia")
        fig.tight_layout()
        p = plots_dir / "h3_shell_abundance.png"
        fig.savefig(p)
        plt.close(fig)
        paths.append(p)

    if transport_sweep:
        levels = sorted(transport_sweep, key=lambda x: float(x))
        medians = []
        for level in levels:
            turns = [t for r in transport_sweep[level] if (t := _emergence_turn(r)) is not None]
            medians.append(statistics.median(turns) if turns else float("nan"))
        fig, ax = plt.subplots()
        ax.plot([float(x) for x in levels], medians, marker="o")
        ax.set_xlabel("costo de transporte entre regiones")
        ax.set_ylabel("mediana turno de emergencia")
        ax.set_title("H4: costo de transporte vs. velocidad de emergencia")
        fig.tight_layout()
        p = plots_dir / "h4_transport_cost.png"
        fig.savefig(p)
        plt.close(fig)
        paths.append(p)

    return paths


__all__ = [
    "BLACKLIST_WORDS",
    "MEDIUM_THRESHOLD",
    "MEDIUM_SUSTAIN_TURNS",
    "LIMITATIONS_SENTENCE",
    "classify_run",
    "build_report",
]
