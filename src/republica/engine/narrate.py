"""Narracion mes a mes de una `History` guardada en JSONL (seccion 10 del spec)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

#: (clave de estado, etiqueta, formato)
KEY_INDICATORS: tuple[tuple[str, str, str], ...] = (
    ("gdp_growth", "Crecimiento (% anual)", "{:.1f}"),
    ("inflation", "Inflacion (% m/m)", "{:.2f}"),
    ("unemployment", "Desempleo (%)", "{:.1f}"),
    ("exchange_rate", "Tipo de cambio", "{:.1f}"),
    ("reserves", "Reservas (USD M)", "{:.0f}"),
    ("government_approval", "Aprobacion", "{:.1f}"),
    ("political_stability", "Estabilidad", "{:.1f}"),
    ("poverty", "Pobreza (%)", "{:.1f}"),
)

EVENT_LABELS = {
    "forced_devaluation": "Devaluacion forzada del banco central.",
    "collapse": "El gobierno cae por perdida de estabilidad politica.",
    "hyperinflation": "La economia entra en hiperinflacion.",
    "term_end": "Fin del mandato: el gobierno completa su periodo.",
}


def annualized_inflation(monthly_pct: float) -> float:
    """`((1 + pi/100)^12 - 1) * 100` (seccion 1)."""
    return ((1.0 + monthly_pct / 100.0) ** 12 - 1.0) * 100.0


def _arrow(delta: float) -> str:
    if delta > 1e-9:
        return "[green]▲[/green]"
    if delta < -1e-9:
        return "[red]▼[/red]"
    return "→"


@dataclass
class Loaded:
    records: list[dict[str, Any]]
    summary: dict[str, Any]
    #: `ActionRecord` (ADR 003 secc. 8, `kind: "action"`), agrupados por
    #: `month`. Vacio si la corrida no tenia actores (`--no-actors`): esas
    #: lineas simplemente no existen en el archivo.
    actions_by_month: dict[int, list[dict[str, Any]]] = field(default_factory=dict)


def load_jsonl(path: str | Path) -> Loaded:
    """Lee un archivo JSONL producido por `republica run` (un `MonthRecord`
    por mes, `ActionRecord` intercalados si hay actores, mas una linea final
    de resumen). Las lineas con `"kind": "action"` no son `MonthRecord`: se
    separan en `actions_by_month` y no entran en `records` (ver Notas de
    implementacion de ADR 003: asi `render()` no cambia para corridas sin
    actores)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"{path} esta vacio")
    parsed = [json.loads(line) for line in lines[:-1]]
    summary = json.loads(lines[-1])
    records = [r for r in parsed if r.get("kind") != "action"]
    actions_by_month: dict[int, list[dict[str, Any]]] = {}
    for r in parsed:
        if r.get("kind") == "action":
            actions_by_month.setdefault(r["month"], []).append(r)
    return Loaded(records=records, summary=summary, actions_by_month=actions_by_month)


def threshold_sentences(record: dict[str, Any]) -> list[str]:
    """Frases automaticas por umbral (seccion 10)."""
    state = record["state"]
    sentences = []
    ann = annualized_inflation(state["inflation"])
    if ann > 50.0:
        sentences.append(f"La inflacion anualizada supera el 50 % ({ann:.0f} %).")
    if state["government_approval"] < 30.0:
        sentences.append(
            f"La aprobacion cae por debajo del 30 % ({state['government_approval']:.1f})."
        )
    if state["reserves"] < 3000.0:
        sentences.append(f"Las reservas bajan de USD 3.000 M (USD {state['reserves']:.0f} M).")
    if state["unemployment"] > 20.0:
        sentences.append(f"El desempleo supera el 20 % ({state['unemployment']:.1f} %).")
    if state["poverty"] > 50.0:
        sentences.append(f"La pobreza supera el 50 % ({state['poverty']:.1f} %).")
    if state["political_stability"] < 20.0:
        stability = state["political_stability"]
        sentences.append(f"La estabilidad politica esta al borde del colapso ({stability:.1f}).")
    if state["protest_level"] > 70.0:
        sentences.append(f"La conflictividad social es muy alta ({state['protest_level']:.1f}).")
    return sentences


def _action_intensity(action: dict[str, Any]) -> float:
    """Intensidad de un `ActionRecord` para ordenar "las 3 mas intensas"
    (deliverable 9): `params.intensity` si el tipo la tiene, si no
    `|score.total|/80` (misma escala que `rule_based.INTENSITY_SCALE`), si
    no 0 (ej. `NO_ACTION`)."""
    intensity = action.get("params", {}).get("intensity")
    if isinstance(intensity, int | float):
        return abs(intensity)
    score = action.get("score")
    if score is not None:
        return abs(score.get("total", 0.0)) / 80.0
    return 0.0


def top_actions(actions: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    """Las `n` acciones mas intensas del mes (deliverable 9 de Fase 3),
    autorizadas primero (una denegada no tuvo efecto real)."""
    visible = [a for a in actions if a.get("type") != "NO_ACTION"]
    return sorted(visible, key=lambda a: (a["authorized"], _action_intensity(a)), reverse=True)[:n]


def render(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    console: Console,
    actions_by_month: dict[int, list[dict[str, Any]]] | None = None,
) -> None:
    """Imprime la narracion completa mes a mes y el resumen final."""
    actions_by_month = actions_by_month or {}
    prev_state: dict[str, Any] | None = None
    for record in records:
        state = record["state"]
        console.rule(f"[bold]{record['date']}[/bold] (mes {record['month_index']})")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Indicador")
        table.add_column("Valor", justify="right")
        table.add_column("")
        for key, label, fmt in KEY_INDICATORS:
            value = state[key]
            delta = value - prev_state[key] if prev_state is not None else 0.0
            table.add_row(label, fmt.format(value), _arrow(delta))
        console.print(table)

        if record["shocks_new"]:
            console.print(f"[yellow]Nuevos shocks:[/yellow] {', '.join(record['shocks_new'])}")
        if record["shocks_active"]:
            console.print(f"[dim]Shocks activos: {', '.join(record['shocks_active'])}[/dim]")
        for event in record["events"]:
            kind = event.split(":")[0]
            console.print(f"[bold red]{EVENT_LABELS.get(kind, event)}[/bold red]")
        for sentence in threshold_sentences(record):
            console.print(f"  → {sentence}")

        month_actions = actions_by_month.get(record["month_index"], [])
        if month_actions:
            console.print("[bold]Actores (3 mas intensos):[/bold]")
            for action in top_actions(month_actions):
                mark = "" if action["authorized"] else " [red](denegada)[/red]"
                console.print(f"  • {action['actor']} {action['type']}{mark} — {action['reason']}")

        prev_state = state

    console.rule("[bold]Resumen final[/bold]")
    first = records[0]["state"]
    last = records[-1]["state"]
    cumulative_inflation = 1.0
    for record in records:
        cumulative_inflation *= 1.0 + record["state"]["inflation"] / 100.0
    cumulative_inflation = (cumulative_inflation - 1.0) * 100.0
    console.print(f"Outcome: [bold]{summary['outcome']}[/bold]")
    console.print(f"Inflacion acumulada del periodo: {cumulative_inflation:+.1f} %")
    console.print(f"Variacion del PIB: {last['gdp'] - first['gdp']:+.1f} puntos de indice")
    console.print(f"Desempleo final: {last['unemployment']:.1f} %")
    console.print(f"Aprobacion final: {last['government_approval']:.1f}")
