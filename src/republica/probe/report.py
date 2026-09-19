"""`report.md` de la sonda exploratoria (ADR 020 secc. 5).

Solo LEE el payload que devuelve `runner.py::run_probe` (el mismo que se
guarda en `summary.json`) y lo escribe en markdown. No corre nada ni
calcula nada nuevo: lo que no esta en el payload no entra al reporte.
"""

from __future__ import annotations

from pathlib import Path

from republica.calibration.run import HONESTY_SENTENCE

#: Lo que la sonda NO mide (ADR 020 secc. 3), impreso en cada reporte: sin
#: esto es muy facil leer estas tablas como si fueran un backtest.
NOT_MEASURED = [
    "**No puntúa aciertos.** No hay `hit`, no hay error, no hay tasa. La columna «qué pasó de "
    "verdad» es texto para un humano; el comando no la compara programáticamente con nada.",
    "**No tiene hipótesis previa.** No hay `registration.json`. No reemplaza a `republica "
    "validate` (ADR 011 §8), cuyo valor está en el registro previo de la hipótesis.",
    "**No mide predictibilidad ni generaliza.** Unos pocos arranques elegidos a mano no son una "
    "muestra: no hay ventanas rodantes ni intervalos de confianza. Para eso está `republica "
    "backtest` (ADR 014); la sonda no lo reemplaza ni lo resume.",
    "**No compara calibraciones ni brazos.** Corre un solo brazo, sin control Aurora.",
    "**No prueba causalidad.** Que una variable sature en el mes 5 y el país termine en el 25 es "
    "una pista sobre el mecanismo, no una explicación.",
]


def _fmt(x: float | None, digits: int = 0) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def _outcomes_cell(outcomes: dict[str, int]) -> str:
    if not outcomes:
        return "-"
    return ", ".join(f"`{k}` {v}" for k, v in outcomes.items())


def _scenario_section(sc: dict) -> list[str]:
    lines: list[str] = [
        f"### `{sc['label']}` — arranque {sc['start']}, {sc['months_requested']} meses pedidos",
        "",
    ]
    lines.append(f"**Qué pasó de verdad:** {sc['expected'] or '(sin descripción)'}")
    lines.append("")
    if sc["error"]:
        lines.append(
            f"**ERROR — el escenario no corrió:** `{sc['error']}`. Los demás escenarios "
            "corrieron igual (ADR 020 §5)."
        )
        lines.append("")
        return lines

    lines.append(
        f"Semillas usables: **{sc['seeds_run']}**"
        + (f" ({sc['seeds_failed']} con excepción)" if sc.get("seeds_failed") else "")
        + f". Outcomes: {_outcomes_cell(sc['outcomes'])}."
    )
    lines.append("")
    lines.append(
        "| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |"
    )
    lines.append("|---:|---:|---:|---:|---:|")
    lines.append(
        f"| **{_fmt(sc['end_month_median'])}** | {_fmt(sc['end_month_min'])} | "
        f"{_fmt(sc['end_month_max'])} | {sc['months_requested']} | "
        f"{sc['seeds_full_horizon']}/{sc['seeds_run']} |"
    )
    lines.append("")

    lines.append("**Saturación contra la cota** (ADR 020 §2.2):")
    lines.append("")
    if not sc["saturation"]:
        lines.append("Ninguna variable toca su cota en ninguna semilla.")
    else:
        lines.append(
            "| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | "
            "% de la corrida |"
        )
        lines.append("|---|---|---:|---:|---:|---:|")
        for row in sc["saturation"]:
            lines.append(
                f"| `{row['variable']}` | {row['bound']} = {row['bound_value']:g} | "
                f"{row['seeds']}/{row['seeds_total']} | {_fmt(row['first_month_median'], 1)} | "
                f"{_fmt(row['months_at_bound_median'], 1)} | "
                f"{row['share_at_bound_median'] * 100:.0f} % |"
            )
    lines.append("")

    lines.append("**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):")
    lines.append("")
    if not sc["violations"]:
        lines.append("Ninguno.")
    else:
        lines.append("| semilla | variable | mes | valor | rango físico |")
        lines.append("|---:|---|---:|---:|---|")
        for v in sc["violations"]:
            lines.append(
                f"| {v['seed']} | `{v['variable']}` | {v['month']} | {v['value']:g} | "
                f"[{v['lo']:g}, {v['hi']:g}] |"
            )
    lines.append("")

    events = sc.get("events", [])[:10]
    lines.append("**Eventos más frecuentes:**")
    lines.append("")
    if not events:
        lines.append("Ninguno.")
    else:
        lines.append("| evento | semillas | 1ra aparición (mes mediano) |")
        lines.append("|---|---:|---:|")
        for ev in events:
            lines.append(
                f"| `{ev['event']}` | {ev['seeds']}/{ev['seeds_total']} | "
                f"{_fmt(ev['first_month_median'], 1)} |"
            )
    lines.append("")

    if sc.get("exceptions"):
        lines.append("**Excepciones:**")
        lines.append("")
        for e in sc["exceptions"]:
            lines.append(f"- semilla {e['seed']}: `{e['error']}`")
        lines.append("")
    return lines


def build_report(payload: dict) -> str:
    """El markdown completo, como string."""
    scen = payload["scenarios"]
    lines: list[str] = [
        "# Sonda exploratoria (ADR 020)",
        "",
        f"País: **{payload['country']}** · "
        f"calibración: **{payload['calibration'] or 'sin calibrar (paquete)'}** · "
        f"semillas: **{payload['seeds']}** (desde {payload['seed_base']}) · "
        f"transiciones de régimen: **{'sí' if payload['regime_transitions'] else 'no'}** · "
        f"{payload['wall_seconds']:.1f} s",
        "",
        f"Escenarios: `{payload['scenarios_file']}` ({len(scen)} filas).",
        "",
        "Esto **no es un backtest ni una validación**. El backtest (ADR 014) puntúa objetivos "
        "contra series reales en ventanas rodantes; la validación (ADR 011 §8) puntúa hipótesis "
        "registradas antes de correr. La sonda **no puntúa nada**: corre unos pocos arranques "
        "históricos con muchas semillas y describe el comportamiento del modelo, buscando "
        "síntomas de que algo esté mal mecánicamente.",
        "",
        "---",
        "",
        "## Resumen",
        "",
        "| escenario | arranque | pedidos | fin (mediana) | mín–máx | outcomes | "
        "variables saturadas | fuera de rango |",
        "|---|---|---:|---:|---|---|---:|---:|",
    ]
    for sc in scen:
        if sc["error"]:
            lines.append(
                f"| `{sc['label']}` | {sc['start']} | {sc['months_requested']} | **ERROR** | - | "
                f"{sc['error'][:60]} | - | - |"
            )
            continue
        lines.append(
            f"| `{sc['label']}` | {sc['start']} | {sc['months_requested']} | "
            f"**{_fmt(sc['end_month_median'])}** | "
            f"{_fmt(sc['end_month_min'])}–{_fmt(sc['end_month_max'])} | "
            f"{_outcomes_cell(sc['outcomes'])} | {len(sc['saturation'])} | "
            f"{len(sc['violations'])} |"
        )
    lines.append("")

    lines.append("## Escenarios y lo que pasó de verdad")
    lines.append("")
    lines.append("| escenario | arranque | meses | qué pasó de verdad |")
    lines.append("|---|---|---:|---|")
    for sc in scen:
        lines.append(
            f"| `{sc['label']}` | {sc['start']} | {sc['months_requested']} | "
            f"{sc['expected'] or '(sin descripción)'} |"
        )
    lines.append("")
    lines.append(
        "La comparación con esa columna la hace un humano: la sonda la imprime al lado del "
        "resultado y **no la puntúa** (ADR 020 §2.1)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Detalle por escenario")
    lines.append("")
    for sc in scen:
        lines.extend(_scenario_section(sc))

    lines.append("---")
    lines.append("")
    lines.append("## Qué no se puede concluir de esto")
    lines.append("")
    for item in NOT_MEASURED:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(HONESTY_SENTENCE)
    lines.append("")
    return "\n".join(lines)


def write_report(out_dir: Path, payload: dict) -> Path:
    """Escribe `report.md` en `out_dir` y devuelve su ruta."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.md"
    path.write_text(build_report(payload), encoding="utf-8")
    return path
