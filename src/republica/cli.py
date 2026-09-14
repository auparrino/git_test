"""CLI de Republica Artificial (Fase 1: `run`, `narrate`, `batch`)."""

from __future__ import annotations

import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from republica import __version__
from republica.engine import narrate as narrate_mod
from republica.engine.advisor import advise
from republica.engine.dilemmas import compute_aux_vars, render_text
from republica.engine.game import MONTHLY_CAPS, Game
from republica.engine.narrate import EVENT_LABELS, annualized_inflation
from republica.engine.policy import ConstantPolicy, PassivePolicy, PolicyRule, TaylorPolicy
from republica.engine.simulation import History
from republica.engine.simulation import run as run_simulation
from republica.world.config import load_country

app = typer.Typer(help="Republica Artificial - laboratorio politico jugable.")
console = Console()


@app.command()
def version() -> None:
    """Muestra la version instalada de Republica Artificial."""
    console.print(__version__)


def _parse_force_shock(spec: str) -> tuple[int, str]:
    if "@" not in spec:
        raise typer.BadParameter(f"formato esperado id@mes, recibido: {spec!r}")
    shock_id, _, month_str = spec.partition("@")
    try:
        month = int(month_str)
    except ValueError as exc:
        raise typer.BadParameter(f"mes invalido en {spec!r}") from exc
    return month, shock_id


def _build_policy_rule(name: str, country) -> PolicyRule:
    if name == "constant":
        return ConstantPolicy(country.default_policy)
    if name == "passive":
        return PassivePolicy(
            country.default_policy,
            country.structure.r_neutral,
            country.policy_ranges["interest_rate_target"],
        )
    if name == "taylor":
        return TaylorPolicy(
            country.default_policy,
            country.taylor,
            country.structure.r_neutral,
            country.policy_ranges["interest_rate_target"],
        )
    raise typer.BadParameter(f"politica desconocida: {name!r} (usar constant|passive|taylor)")


@app.command()
def run(
    seed: Annotated[int, typer.Option(help="Semilla del generador aleatorio.")],
    out: Annotated[Path, typer.Option(help="Archivo JSONL de salida.")],
    months: Annotated[int, typer.Option(help="Cantidad de meses a simular.")] = 48,
    policy: Annotated[
        str, typer.Option(help="Regla de politica: constant|passive|taylor.")
    ] = "passive",
    force_shock: Annotated[
        list[str],
        typer.Option("--force-shock", help="Fuerza un shock: id@mes (repetible, ej. drought@5)."),
    ] = [],  # noqa: B006 - typer clona la lista, no se muta
) -> None:
    """Corre una simulacion de `months` meses y la guarda en `out` (JSONL)."""
    country = load_country()
    policy_rule = _build_policy_rule(policy, country)
    forced_shocks: dict[int, list[str]] = {}
    for spec in force_shock:
        month, shock_id = _parse_force_shock(spec)
        forced_shocks.setdefault(month, []).append(shock_id)

    history = run_simulation(
        seed=seed,
        months=months,
        policy_rule=policy_rule,
        forced_shocks=forced_shocks or None,
        country=country,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(history.to_jsonl(), encoding="utf-8")
    console.print(
        f"[green]OK[/green] seed={seed} months={len(history.records)} "
        f"outcome={history.outcome} -> {out}"
    )


@app.command()
def narrate(
    path: Annotated[Path, typer.Argument(help="Archivo JSONL de una corrida (`republica run`).")],
) -> None:
    """Narra mes a mes una corrida guardada en JSONL (seccion 10 del spec)."""
    loaded = narrate_mod.load_jsonl(path)
    narrate_mod.render(loaded.records, loaded.summary, console)


def _percentiles(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return (float("nan"),) * 3
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0], ordered[0], ordered[0]
    quantiles = statistics.quantiles(ordered, n=10, method="inclusive")
    # quantiles[0] = p10 ... quantiles[8] = p90 (method="inclusive", n=10)
    return quantiles[0], statistics.median(ordered), quantiles[8]


@app.command()
def batch(
    seeds: Annotated[int, typer.Option(help="Cantidad de semillas a correr (0..seeds-1).")] = 1000,
    months: Annotated[int, typer.Option(help="Cantidad de meses por corrida.")] = 48,
    policy: Annotated[
        str, typer.Option(help="Regla de politica: constant|passive|taylor.")
    ] = "passive",
) -> None:
    """Corre `seeds` semillas y muestra distribucion de outcomes y percentiles."""
    country = load_country()
    t0 = time.perf_counter()

    outcomes: Counter[str] = Counter()
    annualized_inflations: list[float] = []
    final_unemployments: list[float] = []
    final_approvals: list[float] = []
    min_reserves: list[float] = []

    for seed in range(seeds):
        policy_rule = _build_policy_rule(policy, country)
        history: History = run_simulation(
            seed=seed, months=months, policy_rule=policy_rule, country=country
        )
        outcomes[history.outcome] += 1
        last = history.records[-1].state
        annualized_inflations.append(narrate_mod.annualized_inflation(last["inflation"]))
        final_unemployments.append(last["unemployment"])
        final_approvals.append(last["government_approval"])
        min_reserves.append(min(r.state["reserves"] for r in history.records))

    elapsed = time.perf_counter() - t0

    console.print(f"[bold]{seeds} corridas de {months} meses ({policy}) en {elapsed:.1f}s[/bold]")

    table = Table(title="Distribucion de outcomes")
    table.add_column("Outcome")
    table.add_column("N", justify="right")
    table.add_column("%", justify="right")
    for outcome, count in outcomes.most_common():
        table.add_row(outcome, str(count), f"{100 * count / seeds:.1f}")
    console.print(table)

    metrics = Table(title="Percentiles (p10 / p50 / p90)")
    metrics.add_column("Metrica")
    metrics.add_column("p10", justify="right")
    metrics.add_column("p50", justify="right")
    metrics.add_column("p90", justify="right")
    for label, values in (
        ("Inflacion anualizada final (%)", annualized_inflations),
        ("Desempleo final (%)", final_unemployments),
        ("Aprobacion final", final_approvals),
        ("Reservas minimas (USD M)", min_reserves),
    ):
        p10, p50, p90 = _percentiles(values)
        metrics.add_row(label, f"{p10:.1f}", f"{p50:.1f}", f"{p90:.1f}")
    console.print(metrics)


MESES_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

INSTRUMENT_LABELS = (
    ("interest_rate_target", "Tasa de interes"),
    ("tax_rate", "Impuestos (% PIB)"),
    ("primary_spending", "Gasto primario (% PIB)"),
    ("provincial_transfers", "Transferencias a provincias (% PIB)"),
    ("fx_intervention", "Intervencion cambiaria (0-1)"),
)


def _month_label(country, month_index: int) -> str:
    total = (country.start["month"] - 1) + (month_index - 1)
    year = country.start["year"] + total // 12
    month = total % 12
    return f"{MESES_ES[month].upper()} {year}"


def _play_arrow(delta: float) -> str:
    if delta > 1e-9:
        return "[green]▲[/green]"
    if delta < -1e-9:
        return "[red]▼[/red]"
    return "→"


def _render_dashboard(console: Console, game: Game, prev_state: dict | None) -> None:
    state = game.sim.state.model_dump()
    month = game.sim.month + 1

    def d(key: str) -> float:
        return state[key] - prev_state[key] if prev_state else 0.0

    ann = annualized_inflation(state["inflation"])
    console.rule(
        f"[bold]{game.country.name.upper()} · {_month_label(game.country, month)} · "
        f"mes {month}/{game.country.months}[/bold]"
    )
    console.print(
        f"Inflacion {state['inflation']:.1f} % m/m ({ann:.0f} % anual) "
        f"{_play_arrow(d('inflation'))}"
    )
    console.print(
        f"Desempleo {state['unemployment']:.1f} % {_play_arrow(d('unemployment'))}   "
        f"Reservas USD {state['reserves']:.0f} M {_play_arrow(d('reserves'))}"
    )
    console.print(
        f"Aprobacion {state['government_approval']:.0f} {_play_arrow(d('government_approval'))}   "
        f"Estabilidad {state['political_stability']:.0f} {_play_arrow(d('political_stability'))}"
    )
    console.print(
        f"PIB (anual) {state['gdp_growth']:.1f} % {_play_arrow(d('gdp_growth'))}   "
        f"Salario real {state['real_wage']:.1f} {_play_arrow(d('real_wage'))}"
    )
    console.print(
        f"Deficit {-state['fiscal_balance']:.1f} % PIB   Deuda {state['public_debt']:.0f} % PIB"
    )

    if game.sim.active_shocks:
        parts = []
        for shock_id, astate in game.sim.active_shocks.items():
            shock_def = game.sim.catalog.by_id[shock_id]
            parts.append(f"⚠ {shock_def.name} (mes {astate.months_active} de {shock_def.duration})")
        console.print("  ".join(parts))

    if game.sim.records:
        last_events = game.sim.records[-1].events
        if last_events:
            labels = [EVENT_LABELS.get(e.split(":")[0], e) for e in last_events]
            console.print("● " + "  ".join(labels))

    aux = compute_aux_vars(game.sim.state, month, game.country.months)
    for adv in advise(game.sim.state, aux, game.policy, game.country):
        console.print(f"[cyan]{adv.source}:[/cyan] {adv.text}")

    for dilemma in game.pending_dilemmas:
        console.print(f"[bold yellow]DILEMA: {dilemma.title}[/bold yellow]")
        console.print(f"  {render_text(dilemma, game.sim.state, aux, month)}")
        for opt in dilemma.options:
            console.print(f"   {opt.key}) {opt.label}")


def _collect_choices(game: Game, auto: bool) -> dict[str, str]:
    choices: dict[str, str] = {}
    for dilemma in game.pending_dilemmas:
        keys = [o.key for o in dilemma.options]
        if auto:
            choices[dilemma.id] = keys[0]
            console.print(f"[dim]--auto: {dilemma.id} -> {keys[0]}[/dim]")
            continue
        answer = typer.prompt(f"  {dilemma.title} [{'/'.join(keys)}]", default=keys[0])
        answer = answer.strip().upper()
        choices[dilemma.id] = answer if answer in keys else keys[0]
    return choices


def _prompt_instruments(game: Game) -> dict[str, float]:
    edits: dict[str, float] = {}
    for field_name, label in INSTRUMENT_LABELS:
        current = getattr(game.policy, field_name)
        cap = MONTHLY_CAPS.get(field_name)
        cap_txt = f"cambio maximo +-{cap:g}" if cap is not None else "sin limite mensual"
        raw = typer.prompt(f"{label} (actual {current:.2f}, {cap_txt})", default=f"{current:.2f}")
        try:
            value = float(raw)
        except ValueError:
            console.print(f"[red]Valor invalido para {label}, se mantiene {current:.2f}.[/red]")
            continue
        if abs(value - current) > 1e-9:
            edits[field_name] = value
    return edits


def _menu(game: Game, save_path: Path, auto: bool) -> tuple[dict[str, float], bool]:
    """Devuelve `(instrument_edits, quit)`. Cualquier respuesta que no sea
    exactamente I/S/Q se toma como Enter (seguir)."""
    if auto:
        return {}, False
    edits: dict[str, float] = {}
    while True:
        action = typer.prompt(
            "[I] instrumentos  [S] guardar  [Q] salir  (Enter = continuar)", default=""
        )
        action = action.strip().upper()
        if action == "I":
            edits.update(_prompt_instruments(game))
        elif action == "S":
            game.save(save_path)
            console.print(f"[green]Partida guardada en {save_path}[/green]")
        elif action == "Q":
            return edits, True
        else:
            return edits, False


def _render_final(console: Console, game: Game) -> None:
    console.rule("[bold]Fin de la partida[/bold]")
    outcome = game.sim.outcome or "survived"
    last = (
        game.sim.records[-1].state if game.sim.records else game.country.initial_state.model_dump()
    )
    console.print(f"Resultado: [bold]{outcome}[/bold]")
    console.print(f"Aprobacion final: {last['government_approval']:.1f}")
    console.print(f"Inflacion anualizada final: {annualized_inflation(last['inflation']):.1f} %")
    console.print(f"Desempleo final: {last['unemployment']:.1f} %")
    console.print(f"Reservas finales: USD {last['reserves']:.0f} M")

    impact = game.counterfactual_impact()
    console.print(
        "Impacto total vs. no hacer nada (Banco Central pasivo, misma semilla): "
        f"{impact['approval_diff_final']:+.1f} pts de aprobacion"
    )
    if impact["top_decisions"]:
        table = Table(title="Decisiones de mayor impacto (aprobacion a +3 meses vs. contrafactico)")
        table.add_column("Mes", justify="right")
        table.add_column("Dilema")
        table.add_column("Opcion")
        table.add_column("Delta aprobacion", justify="right")
        for dec in impact["top_decisions"]:
            table.add_row(
                str(dec["month"]),
                dec["dilemma_id"],
                dec["option"],
                f"{dec['approval_delta_3m']:+.1f}",
            )
        console.print(table)
    else:
        console.print("[dim]No hubo decisiones suficientes para medir impacto.[/dim]")


@app.command()
def play(
    seed: Annotated[int, typer.Option(help="Semilla del generador aleatorio.")] = 7,
    months: Annotated[int, typer.Option(help="Cantidad de meses a jugar.")] = 48,
    load: Annotated[
        Path | None, typer.Option("--load", help="Cargar una partida guardada.")
    ] = None,
    auto: Annotated[
        bool,
        typer.Option("--auto", help="Elige la primera opcion de cada dilema sin preguntar."),
    ] = False,
) -> None:
    """Modo juego: sos el presidente (SPEC_v0.2_play.md)."""
    if load is not None:
        game = Game.load(load)
        console.print(f"[green]Partida cargada desde {load}[/green]")
    else:
        game = Game.new(seed=seed, months=months)

    save_path = Path(f"simulations/game_{game.seed}.json")
    prev_state = game.sim.records[-1].state if game.sim.records else None

    while game.sim.outcome is None and game.sim.month < game.country.months:
        _render_dashboard(console, game, prev_state)
        choices = _collect_choices(game, auto)
        edits, quit_now = _menu(game, save_path, auto)
        if quit_now:
            game.save(save_path)
            console.print(f"[yellow]Partida guardada en {save_path}. Hasta la proxima.[/yellow]")
            return
        record = game.step(choices, edits)
        if game.clip_report:
            for instrument, (requested, applied) in game.clip_report.items():
                console.print(
                    f"[dim]{instrument}: pedido {requested:+.1f}, aplicado {applied:+.1f} "
                    "(tope mensual)[/dim]"
                )
        prev_state = record.state

    game.save(save_path)
    _render_final(console, game)


if __name__ == "__main__":
    app()
