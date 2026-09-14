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


if __name__ == "__main__":
    app()
