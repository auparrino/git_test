"""CLI de Republica Artificial (Fase 1: `run`, `narrate`, `batch`)."""

from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from republica import __version__
from republica.actors.sheet import load_actors
from republica.ai.brains import BrainsConfig, load_brains_config
from republica.engine import emergence as emergence_mod
from republica.engine import narrate as narrate_mod
from republica.engine.advisor import advise
from republica.engine.dilemmas import compute_aux_vars, render_text
from republica.engine.game import MONTHLY_CAPS, Game
from republica.engine.narrate import EVENT_LABELS, annualized_inflation
from republica.engine.permissions import AUTHORITY_VIOLATION_MARKER
from republica.engine.policy import ConstantPolicy, PassivePolicy, PolicyRule, TaylorPolicy
from republica.engine.simulation import History
from republica.engine.simulation import run as run_simulation
from republica.world.annual import load_annual_regime, run_annual
from republica.world.cohorts import load_cohorts
from republica.world.config import load_country
from republica.world.countries import (
    CountryPackError,
    country_pack_dir,
    load_country_pack,
    load_country_pack_annual,
)

app = typer.Typer(help="Republica Artificial - laboratorio politico jugable.")
actors_app = typer.Typer(help="Fichas de actores (ADR 003).")
app.add_typer(actors_app, name="actors")
traces_app = typer.Typer(help="Trazas de decision de actores IA (ADR 007 secc. 5).")
app.add_typer(traces_app, name="traces")
eval_app = typer.Typer(help="Evals de agentes (ADR 007 secc. 1-4).")
app.add_typer(eval_app, name="eval")
experiment_app = typer.Typer(help="Experimentos en lote, DuckDB y comparacion (ADR 008).")
app.add_typer(experiment_app, name="experiment")
country_app = typer.Typer(help="Paquetes de pais (ADR 011).")
app.add_typer(country_app, name="country")
ml_app = typer.Typer(
    help="Sustituto, active learning, early-warning y clustering de regimenes (ADR 009)."
)
app.add_typer(ml_app, name="ml")
early_warning_app = typer.Typer(help="Early-warning de crisis (ADR 009 secc. 5).")
ml_app.add_typer(early_warning_app, name="early-warning")
core_app = typer.Typer(
    help="CPU social minima -- hito 1: emergencia de un medio de intercambio (ADR 010)."
)
app.add_typer(core_app, name="core")
console = Console()


@app.command()
def version() -> None:
    """Muestra la version instalada de Republica Artificial."""
    console.print(__version__)


@actors_app.command("list")
def actors_list() -> None:
    """Tabla de las 29 fichas de actores (`data/actors/*.yaml`, ADR 003 secc. 2)."""
    actors = load_actors()
    table = Table(title="Actores (ADR 003)")
    table.add_column("id")
    table.add_column("nombre")
    table.add_column("rol")
    table.add_column("economic", justify="right")
    table.add_column("interests")
    for actor_id in sorted(actors):
        sheet = actors[actor_id]
        table.add_row(
            sheet.id,
            sheet.name,
            sheet.role,
            f"{sheet.ideology.economic:+.2f}",
            ", ".join(sheet.interests),
        )
    console.print(table)


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


def _resolve_brains(brain: str | None, brains: Path | None) -> BrainsConfig:
    """`--brain`/`--brains` (ADR 004 secc. 7/8, deliverable 6) -> `BrainsConfig`.

    `--brains path.yaml` carga el mapeo por actor; `--brain X` (si tambien
    se pasa) pisa el `default` de ese archivo. Sin ninguno de los dos:
    `BrainsConfig()` (default `"rules"` para todos, ver `ai/brains.py`)."""
    cfg = load_brains_config(brains) if brains is not None else BrainsConfig()
    if brain is not None:
        cfg.default = brain
    return cfg


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
    actors: Annotated[
        bool | None,
        typer.Option(
            "--actors/--no-actors",
            help="Actores por reglas (ADR 003). Default: `features.actors` de country.json.",
        ),
    ] = None,
    congress: Annotated[
        bool | None,
        typer.Option(
            "--congress/--no-congress",
            help="Congreso (ADR 005 secc. 1). Default: `features.congress` de country.json.",
        ),
    ] = None,
    negotiation: Annotated[
        bool | None,
        typer.Option(
            "--negotiation/--no-negotiation",
            help="Negociacion (ADR 005 secc. 2). Default: `features.negotiation` de country.json.",
        ),
    ] = None,
    cohorts: Annotated[
        bool | None,
        typer.Option(
            "--cohorts/--no-cohorts",
            help="Cohortes sociales (ADR 005 secc. 3). Default: `features.cohorts` de "
            "country.json.",
        ),
    ] = None,
    media: Annotated[
        bool | None,
        typer.Option(
            "--media/--no-media",
            help="Medios y percepcion (ADR 005 secc. 4). Default: `features.media` de "
            "country.json.",
        ),
    ] = None,
    memory: Annotated[
        bool | None,
        typer.Option(
            "--memory/--no-memory",
            help="Memoria de actores (ADR 006 secc. 1). Default: `features.memory` de "
            "country.json.",
        ),
    ] = None,
    elections: Annotated[
        bool | None,
        typer.Option(
            "--elections/--no-elections",
            help="Elecciones cada `term_length` meses (ADR 006 secc. 2). Default: "
            "`features.elections` de country.json.",
        ),
    ] = None,
    brain: Annotated[
        str | None,
        typer.Option(
            help="Cerebro para todo actor sin entrada en --brains (ADR 004/009): "
            "rules|fake:rules|fake:malformed|fake:unauthorized|llm:ollama:<modelo>|"
            "surrogate:<path>[+fallback:<brain>[+threshold:<valor>]].",
        ),
    ] = None,
    brains: Annotated[
        Path | None,
        typer.Option(
            help="YAML con cerebro por actor (ADR 004 secc. 7, formato de data/brains.yaml)."
        ),
    ] = None,
    governance_override: Annotated[
        list[str],
        typer.Option(
            "--governance-override",
            help="Override de gobernanza actor.campo=valor (ADR 007 secc. 6, repetible; ej. "
            "central_bank.autonomy=4).",
        ),
    ] = [],  # noqa: B006 - typer clona la lista, no se muta
    country_id: Annotated[
        str | None,
        typer.Option(
            "--country",
            help="Paquete de pais (ADR 011, ej. 'argentina'). Sin esto: Aurora (data/), "
            "igual que siempre.",
        ),
    ] = None,
    start: Annotated[
        str | None,
        typer.Option("--start", help="Fecha de arranque YYYY-MM (obligatoria con --country)."),
    ] = None,
    annual_mode: Annotated[
        bool | None,
        typer.Option(
            "--annual-mode/--no-annual-mode",
            help="Modo anual (ADR 011 secc. 6, EXPLORATORIO). Default: automatico segun "
            "--start (< 1943 -> anual). Requiere --country.",
        ),
    ] = None,
    regime_mode_opt: Annotated[
        str,
        typer.Option(
            "--regime-mode",
            help="auto|democracy (ADR 011 secc. 3). 'auto': golpes de calendario + "
            "endogenos. 'democracy': el pais nunca sale de democracia. Requiere --country.",
        ),
    ] = "auto",
    historical_shocks: Annotated[
        bool,
        typer.Option(
            "--historical-shocks",
            help="Fuerza politics/shocks_calendar.csv del paquete (ADR 011 secc. 4). "
            "Requiere --country.",
        ),
    ] = False,
    historical_exogenous: Annotated[
        bool,
        typer.Option(
            "--historical-exogenous",
            help="Alimenta commodity_price/world_demand con history/ del paquete "
            "(ADR 011 secc. 5). Requiere --country.",
        ),
    ] = False,
    fx_regime_opt: Annotated[
        str | None,
        typer.Option(
            "--fx-regime",
            help="float|crawl|peg|control|auto (ADR 011 secc. 5 / ADR 012 secc. 3, "
            "bimonetario/macro). 'auto' (default con --country): resuelve el regimen segun "
            "`fx_regimes.csv` del paquete para `--start` (ADR 012 deliverable 5). Requiere "
            "--country.",
        ),
    ] = None,
    calibration_run_id: Annotated[
        str | None,
        typer.Option(
            "--calibration",
            help="run_id de `republica calibrate` (A3, ADR 011 secc. 7): reemplaza los "
            "coeficientes economicos y bimonetarios de `country.json` por "
            "`calibration/<run_id>/coefficients.json`. Requiere --country.",
        ),
    ] = None,
) -> None:
    """Corre una simulacion de `months` meses y la guarda en `out` (JSONL)."""
    from republica.governance import parse_governance_overrides

    forced_shocks: dict[int, list[str]] = {}
    for spec in force_shock:
        month, shock_id = _parse_force_shock(spec)
        forced_shocks.setdefault(month, []).append(shock_id)

    macro_coefficients = None
    macro_x0 = None
    macro_m0 = None
    if country_id is None:
        country = load_country()
        regime_calendar = None
        bimonetary_coefficients = None
        historical_exogenous_series = None
    else:
        if start is None:
            raise typer.BadParameter("--start es obligatorio junto con --country (YYYY-MM).")
        try:
            start_year = int(start.split("-")[0])
        except ValueError as exc:
            raise typer.BadParameter(f"--start invalido: {start!r} (formato YYYY-MM).") from exc
        use_annual = annual_mode if annual_mode is not None else start_year < 1943
        if use_annual:
            country_obj = load_country_pack_annual(country_id, start_year, months)
            regime_lookup = load_annual_regime(
                country_pack_dir(country_id) / "politics" / "regimes.csv"
            )
            policy_rule = _build_policy_rule(policy, country_obj)
            history_annual = run_annual(
                seed=seed,
                years=months,
                country=country_obj,
                policy_rule=policy_rule,
                start_year=start_year,
                annual_regime=regime_lookup,
                forced_shocks=forced_shocks or None,
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(history_annual.to_jsonl(), encoding="utf-8")
            console.print(
                f"[yellow]OK (modo anual, EXPLORATORIO -- ADR 011 secc. 6)[/yellow] "
                f"seed={seed} years={len(history_annual.records)} -> {out}"
            )
            return
        try:
            pack = load_country_pack(country_id, start, months, regime_mode=regime_mode_opt)
        except CountryPackError as exc:
            raise typer.BadParameter(str(exc)) from exc
        country = pack.country
        regime_calendar = pack.regime_calendar
        bimonetary_coefficients = pack.bimonetary_coefficients
        if calibration_run_id:
            from republica.calibration.run import load_calibrated_country

            try:
                calibrated_coeff, bimonetary_coefficients = load_calibrated_country(
                    country_id, calibration_run_id
                )
            except FileNotFoundError as exc:
                raise typer.BadParameter(str(exc)) from exc
            country = country.model_copy(update={"coefficients": calibrated_coeff})
            console.print(
                f"[yellow]Coeficientes calibrados (A3)[/yellow]: run_id={calibration_run_id}"
            )
        # ADR 012 deliverable 5: `--fx-regime auto` (default con --country,
        # ver `fx_regime_opt` mas abajo) resuelve el regimen segun
        # `fx_regimes.csv` del paquete para `start`; cualquier otro valor
        # (`float`/`crawl`/`peg`/`control`) se pasa literal, igual que
        # siempre (ADR 011).
        resolved_fx_regime = fx_regime_opt if fx_regime_opt is not None else "auto"
        if resolved_fx_regime == "auto":
            resolved_fx_regime = pack.fx_regime_auto
        bimonetary_coefficients = replace(
            bimonetary_coefficients, fx_regime_default=resolved_fx_regime
        )
        # ADR 012: solo se arma `macro_coefficients` (y por lo tanto solo se
        # activa la rama nueva de `advance_month`) si el paquete lo pide via
        # `features.macro_regime` -- el flag SI es el gate aca (a diferencia
        # de `features.bimonetary`/`features.regime`, que esta CLI nunca
        # leyo: ver Notas de implementacion del ADR 012 sobre por que no se
        # replico ese patron).
        if country.features.get("macro_regime", False):
            macro_coefficients = pack.macro_coefficients
            macro_x0 = pack.macro_x0
            macro_m0 = pack.macro_m0
        if historical_shocks:
            for month, ids in pack.historical_forced_shocks.items():
                forced_shocks.setdefault(month, []).extend(ids)
            console.print(
                f"[yellow]Shocks forzados por calendario (ADR 011 secc. 4)[/yellow]: "
                f"{dict(sorted(pack.historical_forced_shocks.items()))}"
            )
        historical_exogenous_series = None
        if historical_exogenous:
            from republica.world.countries import historical_exogenous_series as _hist_exo

            historical_exogenous_series = _hist_exo(
                pack.pack_dir, start_year, int(start.split("-")[1]), months
            )

    policy_rule = _build_policy_rule(policy, country)

    actors_enabled = actors if actors is not None else country.features.get("actors", True)
    congress_enabled = congress if congress is not None else country.features.get("congress", True)
    negotiation_enabled = (
        negotiation if negotiation is not None else country.features.get("negotiation", True)
    )
    # `republica run --no-actors` no debe dejar NINGUNA linea `kind: ...` en
    # el JSONL (test de aceptacion de ADR 003, deliverable 9): cohortes es
    # independiente de `actors_enabled` a nivel de `Simulation`/`run()` (ver
    # Notas de implementacion), pero la CLI las ata igual que
    # congress/negotiation -- sin actores no hay bloques sociales ni medios
    # que jugar, asi que no tiene sentido prenderlas solas desde `run`.
    cohorts_enabled = (
        cohorts if cohorts is not None else country.features.get("cohorts", True)
    ) and actors_enabled
    media_enabled = (
        media if media is not None else country.features.get("media", True)
    ) and actors_enabled
    memory_enabled = (
        memory if memory is not None else country.features.get("memory", True)
    ) and actors_enabled
    elections_enabled = (
        (elections if elections is not None else country.features.get("elections", True))
        and actors_enabled
        and cohorts_enabled
    )
    brains_cfg = _resolve_brains(brain, brains)
    history = run_simulation(
        seed=seed,
        months=months,
        policy_rule=policy_rule,
        forced_shocks=forced_shocks or None,
        country=country,
        actors_enabled=actors_enabled,
        brain_map=brains_cfg.actors,
        default_brain=brains_cfg.default,
        llm_temperature=brains_cfg.temperature,
        llm_cache_dir=brains_cfg.cache_dir,
        congress_enabled=congress_enabled,
        negotiation_enabled=negotiation_enabled,
        cohorts_enabled=cohorts_enabled,
        media_enabled=media_enabled,
        memory_enabled=memory_enabled,
        elections_enabled=elections_enabled,
        governance_overrides=parse_governance_overrides(governance_override) or None,
        regime_calendar=regime_calendar,
        bimonetary_coefficients=bimonetary_coefficients,
        historical_exogenous=historical_exogenous_series,
        macro_coefficients=macro_coefficients,
        macro_x0=macro_x0,
        macro_m0=macro_m0,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(history.to_jsonl(), encoding="utf-8")
    country_note = f" country={country_id} start={start}" if country_id else ""
    console.print(
        f"[green]OK[/green] seed={seed} months={len(history.records)} "
        f"outcome={history.outcome} actors={actors_enabled} "
        f"congress={congress_enabled} negotiation={negotiation_enabled} "
        f"cohorts={cohorts_enabled} media={media_enabled} "
        f"memory={memory_enabled} elections={elections_enabled}{country_note} -> {out}"
    )


@app.command()
def viewer(
    path: Annotated[Path, typer.Argument(help="Archivo JSONL de una corrida (`republica run`).")],
    out: Annotated[
        Path | None, typer.Option("--out", help="Salida HTML (default: mismo nombre con .html).")
    ] = None,
    title: Annotated[str | None, typer.Option("--title", help="Titulo de la pagina.")] = None,
) -> None:
    """Genera un visor HTML autocontenido de la corrida (graficos, boletin, actores)."""
    from republica.ui.viewer import export

    target = export(path, out or path.with_suffix(".html"), title)
    console.print(f"[green]OK[/green] visor -> {target}")


@app.command()
def narrate(
    path: Annotated[Path, typer.Argument(help="Archivo JSONL de una corrida (`republica run`).")],
) -> None:
    """Narra mes a mes una corrida guardada en JSONL (seccion 10 del spec)."""
    loaded = narrate_mod.load_jsonl(path)
    narrate_mod.render(
        loaded.records,
        loaded.summary,
        console,
        loaded.actions_by_month,
        loaded.votes_by_month,
        loaded.negotiations_by_month,
        loaded.elections_by_month,
    )


@app.command()
def emergence(
    path: Annotated[Path, typer.Argument(help="Archivo JSONL de una corrida (`republica run`).")],
) -> None:
    """`republica emergence` (ADR 005 secc. 6): alianzas, coaliciones de
    voto repetidas contra el score ideologico, acuerdos rotos y medios que
    cambiaron de linea. Materia prima de `docs/EMERGENCE_LOG.md`."""
    loaded = narrate_mod.load_jsonl(path)
    report = emergence_mod.detect(loaded)

    console.print(f"[bold]Alianzas formadas[/bold] ({len(report.alliances)}):")
    if not report.alliances:
        console.print("  [dim](ninguna)[/dim]")
    for a in report.alliances:
        console.print(f"  • mes {a['month']}: {a['actor']} <-> {a['with']}")

    n_coalitions = len(report.repeated_coalitions)
    console.print(f"[bold]Coaliciones de voto repetidas[/bold] ({n_coalitions}):")
    if not report.repeated_coalitions:
        console.print("  [dim](ninguna con >= 3 repeticiones -- tambien es un resultado)[/dim]")
    for c in report.repeated_coalitions:
        parties = ", ".join(c["parties"])
        bills = ", ".join(c["bills"])
        console.print(f"  • {parties} — {c['count']} veces ({bills})")

    console.print(f"[bold]Acuerdos rotos[/bold] ({len(report.broken_agreements)}):")
    if not report.broken_agreements:
        console.print("  [dim](ninguno)[/dim]")
    for b in report.broken_agreements:
        console.print(
            f"  • mes {b['month']}: {b['actor']} ({b['concession']}), roto por {b['broken_by']}"
        )

    n_media = len(report.media_line_changes)
    console.print(f"[bold]Medios que cambiaron de linea[/bold] ({n_media}):")
    if not report.media_line_changes:
        console.print("  [dim](ninguno)[/dim]")
    for m in report.media_line_changes:
        console.print(f"  • {m['outlet']}: {m['line_changes']} cambios de linea")

    console.print("[bold]Cohorte mas descontenta[/bold]:")
    if report.most_discontented_cohort is None:
        console.print("  [dim](sin cohortes -- correr con --cohorts)[/dim]")
    else:
        c = report.most_discontented_cohort
        console.print(f"  • {c['cohort']} — aprobacion promedio {c['avg_approval_c']:.1f}")

    console.print("[bold]Mes con mayor brecha de percepcion[/bold]:")
    if report.max_perception_gap_month is None:
        console.print("  [dim](sin percepcion -- correr con --cohorts --media)[/dim]")
    else:
        g = report.max_perception_gap_month
        console.print(f"  • mes {g['month']} — perception_gap {g['perception_gap']:+.2f}")


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
    country_id: Annotated[
        str | None, typer.Option("--country", help="Paquete de pais (ADR 011).")
    ] = None,
    start: Annotated[
        str | None, typer.Option("--start", help="Fecha de arranque YYYY-MM (con --country).")
    ] = None,
) -> None:
    """Corre `seeds` semillas y muestra distribucion de outcomes y percentiles."""
    if country_id is None:
        country = load_country()
    else:
        if start is None:
            raise typer.BadParameter("--start es obligatorio junto con --country (YYYY-MM).")
        try:
            country = load_country_pack(country_id, start, months).country
        except CountryPackError as exc:
            raise typer.BadParameter(str(exc)) from exc
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

    _render_actor_reactions(console, game)

    aux = compute_aux_vars(game.sim.state, month, game.country.months)
    for adv in advise(game.sim.state, aux, game.policy, game.country):
        console.print(f"[cyan]{adv.source}:[/cyan] {adv.text}")

    for dilemma in game.pending_dilemmas:
        console.print(f"[bold yellow]DILEMA: {dilemma.title}[/bold yellow]")
        console.print(f"  {render_text(dilemma, game.sim.state, aux, month)}")
        for opt in dilemma.options:
            console.print(f"   {opt.key}) {opt.label}")


def _render_actor_reactions(console: Console, game: Game) -> None:
    """Deliverable 8 de ADR 003: reacciones del mes pasado (top 6 por
    intensidad, con el mensaje publico) y cuantas se denegaron."""
    if game.sim.actor_engine is None:
        return
    records = game.sim.actor_engine.last_records
    if not records:
        return
    dicts = [r.to_dict() for r in records]
    denied = sum(1 for r in dicts if not r["authorized"])
    top = narrate_mod.top_actions(dicts, n=6)
    if not top:
        console.print(f"[dim]Sin reacciones destacadas de los actores ({denied} denegadas).[/dim]")
        return
    console.print(f"[bold]Reacciones de los actores[/bold] ({denied} denegadas este mes):")
    for action in top:
        mark = "" if action["authorized"] else " [red](denegada)[/red]"
        console.print(f"  • {action['actor']} {action['type']}{mark} — {action['reason']}")


def _collect_grant_decisions(game: Game, auto: bool) -> None:
    """Deliverable 8 de ADR 003 (`REQUEST_FUNDS`) + deliverable 5 de ADR 005
    (`NEGOTIATE`, reemplaza el dilema Conceder/Rechazar de Fase 3 por
    "Conceder / Contraoferta 50 % / Rechazar", ver `engine/game.py::
    Game.set_grant_decisions`). `--auto` elige Conceder (ADR 005, literal)."""
    requests = game.pending_actor_requests
    if not requests:
        return
    granted: set[str] = set()
    negotiation_decisions: dict[str, str] = {}
    for req in requests:
        if req.type.value == "NEGOTIATE":
            prompt = (
                f"  NEGOTIATE de {req.actor_id}: {req.reason} [Conceder/Contraoferta 50 %/Rechazar]"
            )
            if auto:
                console.print(f"[dim]--auto: {prompt} -> Conceder[/dim]")
                negotiation_decisions[req.actor_id] = "grant"
                continue
            answer = typer.prompt(prompt, default="Conceder").strip().lower()
            if answer.startswith("con") or answer.startswith("50"):
                negotiation_decisions[req.actor_id] = "counter"
            elif answer.startswith("c"):
                negotiation_decisions[req.actor_id] = "grant"
            else:
                negotiation_decisions[req.actor_id] = "refuse"
            continue
        prompt = f"  Pedido de {req.actor_id} ({req.type.value}): {req.reason} [Conceder/Rechazar]"
        if auto:
            console.print(f"[dim]--auto: {prompt} -> Rechazar[/dim]")
            continue
        answer = typer.prompt(prompt, default="Rechazar").strip().lower()
        if answer.startswith("c"):
            granted.add(req.actor_id)
    game.set_grant_decisions(granted, negotiation_decisions)


def _collect_approval_decisions(game: Game, auto: bool) -> None:
    """Dilema Si/No de gobernanza (ADR 007 secc. 6, deliverable 6): acciones
    EXECUTE del mes pasado de un actor con `human_approval_required`
    (`central_bank.SET_RATE` con `autonomy >= 3`, p.ej. via
    `--governance-override central_bank.autonomy=4`). `--auto` = Si (ADR
    007 secc. 6, literal)."""
    pending = game.pending_human_approvals
    if not pending:
        return
    approved: set[str] = set()
    for action in pending:
        prompt = f"  {action.actor_id} pide {action.type.value}: {action.reason} [Si/No]"
        if auto:
            console.print(f"[dim]--auto: {prompt} -> Si[/dim]")
            approved.add(action.actor_id)
            continue
        answer = typer.prompt(prompt, default="Si").strip().lower()
        if answer.startswith("s"):
            approved.add(action.actor_id)
    game.set_human_approvals(approved)


def _collect_campaign_decisions(game: Game, auto: bool) -> None:
    """Pantalla de campana (ADR 006 secc. 2.5, deliverable 6): en los
    ultimos 4 meses del mandato, el jugador elige un foco de `CAMPAIGN`
    (cohorte de `data/cohorts.csv` o "all") y hasta 2 `PROMISE`.
    `--auto` elige foco "all" e intensidad maxima, sin promesas (ver
    docstring de `Game.apply_campaign`)."""
    if not game.campaign_window_active:
        return
    cohort_ids = ", ".join(c.id for c in load_cohorts())
    if auto:
        console.print("[dim]--auto: CAMPAIGN(focus=all, intensity=1.0), sin promesas[/dim]")
        game.apply_campaign("all", 1.0, [])
        return
    console.rule("[bold magenta]CAMPANA[/bold magenta]")
    focus = typer.prompt(f"  Foco de campana [{cohort_ids}/all]", default="all").strip()
    try:
        intensity = float(typer.prompt("  Intensidad (0-1)", default="1.0"))
    except ValueError:
        intensity = 1.0
    promises: list[tuple[str, str, str]] = []
    for i in (1, 2):
        text = typer.prompt(f"  Promesa {i} (Enter para omitir)", default="").strip()
        if not text:
            continue
        target = typer.prompt(
            f"  Promesa {i}: cohorte destinataria [{cohort_ids}]", default=""
        ).strip()
        direction = typer.prompt(
            f"  Promesa {i}: direccion [expansive/restrictive]", default="expansive"
        ).strip()
        promises.append((text, target, direction))
    game.apply_campaign(focus, intensity, promises)


def _render_election_night(console: Console, result) -> None:
    """Pantalla de noche electoral (ADR 006 secc. 2.5, deliverable 6)."""
    console.rule("[bold magenta]NOCHE ELECTORAL[/bold magenta]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Partido")
    table.add_column("1a vuelta", justify="right")
    table.add_column("Balotaje", justify="right")
    table.add_column("Bancas", justify="right")
    runoff = result.runoff or {}
    for party_id, pct in sorted(result.first_round.items(), key=lambda kv: kv[1], reverse=True):
        table.add_row(
            party_id,
            f"{pct:.1f} %",
            f"{runoff[party_id]:.1f} %" if party_id in runoff else "-",
            str(result.seats.get(party_id, 0)),
        )
    console.print(table)
    if result.winner == result.incumbent_party:
        console.print(f"[bold green]{result.winner} revalida el mandato.[/bold green]")
    else:
        console.print(
            f"[bold red]{result.incumbent_party} pierde el gobierno.[/bold red] "
            f"Asume [bold]{result.winner}[/bold]: nuevo gabinete, la politica vuelve al "
            "default y hay luna de miel en la aprobacion."
        )


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
    actors: Annotated[
        bool,
        typer.Option(
            "--actors/--no-actors",
            help="Actores por reglas (ADR 003, deliverable 8): reacciones en el tablero "
            "y pedidos de gobernadores/sindicatos como dilema Conceder/Rechazar.",
        ),
    ] = True,
    brain: Annotated[
        str | None,
        typer.Option(
            help="Cerebro para todo actor sin entrada en --brains (ADR 004), solo con --actors.",
        ),
    ] = None,
    brains: Annotated[
        Path | None,
        typer.Option(help="YAML con cerebro por actor (ADR 004 secc. 7), solo con --actors."),
    ] = None,
    cohorts: Annotated[
        bool,
        typer.Option(
            "--cohorts/--no-cohorts",
            help="Cohortes sociales (ADR 005 secc. 3).",
        ),
    ] = True,
    media: Annotated[
        bool,
        typer.Option(
            "--media/--no-media",
            help="Medios y percepcion (ADR 005 secc. 4), solo con --actors.",
        ),
    ] = True,
    memory: Annotated[
        bool,
        typer.Option(
            "--memory/--no-memory",
            help="Memoria de actores (ADR 006 secc. 1), solo con --actors.",
        ),
    ] = True,
    elections: Annotated[
        bool,
        typer.Option(
            "--elections/--no-elections",
            help="Elecciones cada `term_length` meses (ADR 006 secc. 2), solo con --actors "
            "y --cohorts.",
        ),
    ] = True,
) -> None:
    """Modo juego: sos el presidente (SPEC_v0.2_play.md)."""
    if load is not None:
        game = Game.load(load)
        console.print(f"[green]Partida cargada desde {load}[/green]")
    else:
        brains_cfg = _resolve_brains(brain, brains)
        game = Game.new(
            seed=seed,
            months=months,
            actors_enabled=actors,
            brain_map=brains_cfg.actors,
            default_brain=brains_cfg.default,
            llm_temperature=brains_cfg.temperature,
            llm_cache_dir=brains_cfg.cache_dir,
            cohorts_enabled=cohorts,
            media_enabled=media,
            memory_enabled=memory,
            elections_enabled=elections,
        )

    save_path = Path(f"simulations/game_{game.seed}.json")
    prev_state = game.sim.records[-1].state if game.sim.records else None

    while game.sim.outcome is None and game.sim.month < game.country.months:
        _render_dashboard(console, game, prev_state)
        choices = _collect_choices(game, auto)
        _collect_grant_decisions(game, auto)
        _collect_approval_decisions(game, auto)
        _collect_campaign_decisions(game, auto)
        edits, quit_now = _menu(game, save_path, auto)
        if quit_now:
            game.save(save_path)
            console.print(f"[yellow]Partida guardada en {save_path}. Hasta la proxima.[/yellow]")
            return
        n_elections_before = len(game.sim.election_records)
        record = game.step(choices, edits)
        if game.clip_report:
            for instrument, (requested, applied) in game.clip_report.items():
                console.print(
                    f"[dim]{instrument}: pedido {requested:+.1f}, aplicado {applied:+.1f} "
                    "(tope mensual)[/dim]"
                )
        if len(game.sim.election_records) > n_elections_before:
            _render_election_night(console, game.sim.election_records[-1])
        prev_state = record.state

    game.save(save_path)
    _render_final(console, game)


#: Alias local (hallazgo #4 de REVIEW_002: constante unica en
#: `engine/permissions.py::AUTHORITY_VIOLATION_MARKER`, reusada tambien por
#: `evals/metrics.py::authority_violation` y `experiments/runner.py::
#: extract_run_metrics`). Denegaciones cuya `reason` viene del chequeo 1 de
#: `authorize()` ("el rol X no tiene permitido Y"): eso es especificamente
#: un `authority_violation` (ADR 004 secc. 8, metrica de Fase 7), a
#: diferencia de un `invalid_params`/cooldown/presupuesto/gobernanza (que
#: tambien deniegan pero no son "el modelo pidio algo fuera de su rol").
_AUTHORITY_VIOLATION_MARKER = AUTHORITY_VIOLATION_MARKER


@app.command("bench-parse")
def bench_parse(
    brain: Annotated[
        str,
        typer.Option(
            help="Cerebro a medir: fake:rules|fake:malformed|fake:unauthorized|"
            "llm:ollama:<modelo>.",
        ),
    ],
    n: Annotated[int, typer.Option("--n", help="Cantidad de meses/percepciones a generar.")] = 50,
    role: Annotated[str, typer.Option(help="Rol del actor a testear (ej. governor).")] = "governor",
    seed: Annotated[int, typer.Option(help="Semilla del generador aleatorio.")] = 7,
) -> None:
    """`bench-parse` (ADR 004 secc. 8): renderiza `n` percepciones reales
    (un actor de `role`, dentro de una corrida por reglas -- todos los demas
    actores quedan en `"rules"`, solo el elegido usa `brain`) y mide
    `parse_rate`, `authority_violation_rate`, latencia p50/p90 y tokens.
    Umbral de Fase 4 (ADR 004 secc. 8): `parse_rate >= 0.95`."""
    actors = load_actors()
    candidates = sorted((a for a in actors.values() if a.role == role), key=lambda a: a.id)
    if not candidates:
        raise typer.BadParameter(f"no hay actores con rol {role!r}")
    target = candidates[0]

    history = run_simulation(
        seed=seed,
        months=n,
        actors_enabled=True,
        actors=actors,
        brain_map={target.id: brain},
    )
    traces = [t for t in history.trace_records if t.actor_id == target.id]
    if not traces:
        console.print(
            f"[red]brain={brain!r} no genero trazas (¿es 'rules'? bench-parse necesita un "
            "cerebro fake:*/llm:*).[/red]"
        )
        raise typer.Exit(code=1)

    parse_rate = sum(1 for t in traces if t.parse_error is None) / len(traces)
    total_actions = sum(len(t.actions_emitted) for t in traces) or 1
    violations = sum(
        1
        for t in traces
        for d in t.actions_denied
        if _AUTHORITY_VIOLATION_MARKER in (d.get("denied_reason") or "")
    )
    violation_rate = violations / total_actions
    latencies = [t.latency_ms for t in traces]
    p10, p50, p90 = _percentiles(latencies)
    prompt_tokens = [t.tokens.get("prompt", 0) for t in traces]
    completion_tokens = [t.tokens.get("completion", 0) for t in traces]

    console.print(
        f"[bold]bench-parse[/bold] brain={brain} role={role} actor={target.id} "
        f"n={len(traces)} (seed={seed})"
    )
    table = Table(title="Metricas de parseo (ADR 004 secc. 8)")
    table.add_column("Metrica")
    table.add_column("Valor", justify="right")
    table.add_row("parse_rate", f"{parse_rate:.2f}")
    table.add_row("authority_violation_rate", f"{violation_rate:.2f}")
    table.add_row("latencia p50 (ms)", f"{p50:.1f}")
    table.add_row("latencia p90 (ms)", f"{p90:.1f}")
    table.add_row("tokens prompt (media)", f"{statistics.mean(prompt_tokens):.0f}")
    table.add_row("tokens completion (media)", f"{statistics.mean(completion_tokens):.0f}")
    console.print(table)

    if parse_rate >= 0.95:
        console.print("[green]OK[/green] parse_rate por encima del umbral de Fase 4 (0.95).")
    else:
        console.print("[yellow]AVISO[/yellow] parse_rate por debajo del umbral de Fase 4 (0.95).")


_POSITION_ACTION_TYPES = {
    "SUPPORT_POLICY": "support",
    "OPPOSE_POLICY": "oppose",
    "NEGOTIATE": "negotiate",
}


def _actor_month_summary(action_records: list, actor_id: str) -> dict[int, dict]:
    """Resumen mes a mes de `action_records` para un actor (usado por
    `compare`): posicion/intensidad se leen de su accion `SUPPORT_POLICY`/
    `OPPOSE_POLICY`/`NEGOTIATE` del mes (si la hubo), el resto de sus
    acciones (menos `NO_ACTION`) quedan en `actions`, marcadas con `*` si se
    denegaron. Funciona igual para una corrida por reglas o por LLM: ambas
    pasan por el mismo `to_actions`/`authorize()`."""
    by_month: dict[int, list[dict]] = {}
    for rec in action_records:
        d = rec.to_dict()
        if d["actor"] != actor_id:
            continue
        by_month.setdefault(d["month"], []).append(d)

    summary: dict[int, dict] = {}
    for month, recs in by_month.items():
        position = "neutral"
        intensity: float | None = None
        others: list[str] = []
        for d in recs:
            if d["type"] in _POSITION_ACTION_TYPES:
                position = _POSITION_ACTION_TYPES[d["type"]]
                intensity = d["params"].get("intensity")
            elif d["type"] != "NO_ACTION":
                mark = "" if d["authorized"] else "*"
                others.append(f"{d['type']}{mark}")
        summary[month] = {"position": position, "intensity": intensity, "actions": others}
    return summary


@app.command()
def compare(
    seed: Annotated[int, typer.Option(help="Semilla del generador aleatorio.")] = 7,
    a: Annotated[str, typer.Option("--a", help="Cerebro default de la corrida A.")] = "rules",
    b: Annotated[str, typer.Option("--b", help="Cerebro default de la corrida B.")] = "fake:rules",
    actor: Annotated[str, typer.Option(help="Actor a comparar (ej. gov_norte).")] = "gov_norte",
    months: Annotated[int, typer.Option(help="Cantidad de meses a simular.")] = 48,
) -> None:
    """`compare` (ADR 004 secc. 8): corre dos simulaciones completas (`--a`/
    `--b` como `default_brain` de cada una) y muestra, mes a mes, la
    posicion/intensidad/acciones de `--actor` lado a lado."""
    actors = load_actors()
    if actor not in actors:
        raise typer.BadParameter(f"actor desconocido: {actor!r}")

    history_a = run_simulation(
        seed=seed, months=months, actors_enabled=True, actors=actors, default_brain=a
    )
    history_b = run_simulation(
        seed=seed, months=months, actors_enabled=True, actors=actors, default_brain=b
    )
    summary_a = _actor_month_summary(history_a.action_records, actor)
    summary_b = _actor_month_summary(history_b.action_records, actor)

    table = Table(title=f"{actor}: {a} vs {b} (seed={seed})")
    table.add_column("Mes", justify="right")
    table.add_column(f"Posicion ({a})")
    table.add_column(f"Intensidad ({a})", justify="right")
    table.add_column(f"Acciones ({a})")
    table.add_column(f"Posicion ({b})")
    table.add_column(f"Intensidad ({b})", justify="right")
    table.add_column(f"Acciones ({b})")
    for month in range(1, months + 1):
        ra = summary_a.get(month, {"position": "-", "intensity": None, "actions": []})
        rb = summary_b.get(month, {"position": "-", "intensity": None, "actions": []})
        table.add_row(
            str(month),
            ra["position"],
            f"{ra['intensity']:.2f}" if ra["intensity"] is not None else "-",
            ", ".join(ra["actions"]) or "-",
            rb["position"],
            f"{rb['intensity']:.2f}" if rb["intensity"] is not None else "-",
            ", ".join(rb["actions"]) or "-",
        )
    console.print(table)


@traces_app.command("export")
def traces_export(
    path: Annotated[Path, typer.Argument(help="JSONL de una corrida (`republica run`).")],
    to: Annotated[
        str,
        typer.Option(help="Destino: jsonl|langfuse (ADR 007 secc. 5)."),
    ] = "jsonl",
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Salida (default: mismo nombre con .traces.jsonl)."),
    ] = None,
) -> None:
    """Exporta las trazas (`kind: "trace"`) de `path` a spans (ADR 007 secc. 5):
    `--to langfuse` usa el SDK si esta instalado (`pip install
    republica-artificial[langfuse]`); si no, cae a `--to jsonl`."""
    from republica.ai.tracing import export_traces_jsonl, read_traces_jsonl, try_export_langfuse

    if to not in ("jsonl", "langfuse"):
        raise typer.BadParameter("usar jsonl|langfuse")
    traces = read_traces_jsonl(path)
    if to == "langfuse":
        if try_export_langfuse(traces):
            console.print(f"[green]OK[/green] {len(traces)} trazas -> Langfuse")
            return
        console.print("[yellow]langfuse no esta instalado; exportando a JSONL.[/yellow]")
    out_path = out or path.with_suffix(".traces.jsonl")
    n = export_traces_jsonl(traces, out_path)
    console.print(f"[green]OK[/green] {len(traces)} trazas, {n} spans -> {out_path}")


@traces_app.command("show")
def traces_show(
    path: Annotated[Path, typer.Argument(help="JSONL de una corrida (`republica run`).")],
    trace_id: Annotated[str, typer.Argument(help="`run_id:mes:actor_id` (ver `traces export`).")],
) -> None:
    """Imprime el arbol de spans de una decision (ADR 007 secc. 5/7 punto 6)."""
    from republica.ai.tracing import read_traces_jsonl, render_trace_tree, spans_from_trace_dict

    traces = read_traces_jsonl(path)
    match = next(
        (
            t
            for t in traces
            if f"{t.get('run_id', '')}:{int(t.get('month', 0)):03d}:{t.get('actor_id', '')}"
            == trace_id
        ),
        None,
    )
    if match is None:
        console.print(f"[red]no se encontro trace_id {trace_id!r} en {path}[/red]")
        raise typer.Exit(code=1)
    console.print(render_trace_tree(spans_from_trace_dict(match)))


@eval_app.callback(invoke_without_command=True)
def eval_main(
    ctx: typer.Context,
    suite: Annotated[
        str, typer.Option("--suite", help="all|ideological|interest|... (ADR 007 secc. 2).")
    ] = "all",
    brain: Annotated[
        str, typer.Option("--brain", help="rules|fake:rules|fake:unauthorized|llm:ollama:<m>.")
    ] = "rules",
    judge: Annotated[
        str, typer.Option("--judge", help="fake|llm:ollama:<m>|llm:anthropic:<m>.")
    ] = "fake",
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Directorio de salida (default: evals/reports/<ts>/)."),
    ] = None,
    seed: Annotated[int, typer.Option(help="Semilla base de las corridas sinteticas.")] = 7,
) -> None:
    """`republica eval --suite all|<id> --brain ... --judge ... --out ...`
    (ADR 007 secc. 2/4): corre la suite y escribe `report.json` + `report.md`.
    `republica eval compare`/`republica eval export-promptfoo` son subcomandos
    aparte (ver abajo)."""
    if ctx.invoked_subcommand is not None:
        return
    from republica.evals.runner import run_suite

    out_dir = out or Path("evals/reports") / time.strftime("%Y%m%d-%H%M%S")
    report = run_suite(suite=suite, brain=brain, judge=judge, seed=seed)
    paths = report.write(out_dir)
    console.print(
        f"[green]OK[/green] suite={suite} brain={brain} judge={judge} -> {paths[0].parent}"
    )


@eval_app.command("compare")
def eval_compare(
    a: Annotated[Path, typer.Argument(help="Directorio de reporte A (`report.json`).")],
    b: Annotated[Path, typer.Argument(help="Directorio de reporte B (`report.json`).")],
) -> None:
    """Tabla lado a lado de dos reportes, marca diferencias fuera del IC 95 %
    (ADR 007 secc. 4/7 punto 7)."""
    from republica.evals.report import compare_reports

    table_rows, differing = compare_reports(a, b)
    table = Table(title=f"eval compare: {a.name} vs {b.name}")
    table.add_column("metrica")
    table.add_column("A", justify="right")
    table.add_column("B", justify="right")
    table.add_column("IC A 95%")
    table.add_column("IC B 95%")
    table.add_column("difiere")
    for row in table_rows:
        mark = "[red]si[/red]" if row["differs"] else "no"
        table.add_row(
            row["metric"],
            f"{row['a']:.3f}" if row["a"] is not None else "-",
            f"{row['b']:.3f}" if row["b"] is not None else "-",
            row["ci_a"],
            row["ci_b"],
            mark,
        )
    console.print(table)
    if differing:
        console.print(
            f"[yellow]{len(differing)} metricas difieren fuera del IC: {differing}[/yellow]"
        )


@eval_app.command("export-promptfoo")
def eval_export_promptfoo(
    out: Annotated[Path, typer.Option("--out", help="Directorio de salida.")] = Path(
        "evals/promptfoo"
    ),
) -> None:
    """Genera `evals/promptfoo/promptfooconfig.yaml` + `cases.yaml` desde los
    mismos casos de `data/evals/cases/` (ADR 007 secc. 4). Promptfoo no es
    una dependencia de Python: son archivos, nada mas."""
    from republica.evals.promptfoo import export_promptfoo

    paths = export_promptfoo(out)
    console.print(f"[green]OK[/green] promptfoo -> {', '.join(str(p) for p in paths)}")


@experiment_app.command("run")
def experiment_run(
    yaml_path: Annotated[Path, typer.Argument(help="YAML del experimento (ADR 008 secc. 1).")],
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Directorio de salida (default: simulations/exp/<nombre>/)."),
    ] = None,
    workers: Annotated[
        int, typer.Option("--workers", help="Procesos en paralelo (forzado a 1 para brazos llm:*).")
    ] = 1,
) -> None:
    """`republica experiment run <yaml> --workers N --out DIR` (ADR 008
    secc. 2): corre todas las semillas de todos los brazos, escribe
    `<out>/<arm>/<seed>.jsonl`, `runs.meta.json` y `metrics.csv`."""
    from republica.experiments.config import ExperimentConfig
    from republica.experiments.runner import run_experiment

    out_dir = out or Path("simulations/exp") / ExperimentConfig.load(yaml_path).name
    result = run_experiment(yaml_path, out_dir, workers=workers)
    console.print(
        f"[green]OK[/green] experimento={result['experiment']} brazos={len(result['arms'])} "
        f"corridas={result['n_ok']}/{result['n_tasks']} fallidas={result['n_failed']} "
        f"({result['elapsed_seconds']:.1f}s) -> {result['out_dir']}"
    )
    if result["n_failed"]:
        console.print(f"[yellow]{result['n_failed']} corridas fallidas: ver failed.jsonl[/yellow]")


@experiment_app.command("status")
def experiment_status_cmd(
    out: Annotated[Path, typer.Argument(help="Directorio de un experimento ya corrido.")],
) -> None:
    """`republica experiment status <dir>`: progreso por brazo y corridas
    fallidas (ADR 008 secc. 2)."""
    from republica.experiments.runner import experiment_status

    status = experiment_status(out)
    table = Table(title=f"Estado de {status['experiment']} ({out})")
    table.add_column("brazo")
    table.add_column("completas", justify="right")
    table.add_column("total", justify="right")
    table.add_column("faltantes")
    for arm, info in status["arms"].items():
        missing = ", ".join(str(s) for s in info["missing"]) or "-"
        table.add_row(arm, str(info["done"]), str(info["total"]), missing)
    console.print(table)
    console.print(f"Corridas fallidas registradas: {status['n_failed']}")


@experiment_app.command("resume")
def experiment_resume(
    out: Annotated[Path, typer.Argument(help="Directorio de un experimento ya corrido.")],
    workers: Annotated[
        int, typer.Option("--workers", help="Procesos en paralelo (forzado a 1 para brazos llm:*).")
    ] = 1,
) -> None:
    """`republica experiment resume <dir>` (ADR 008 secc. 2): vuelve a
    correr solo los `(brazo, semilla)` sin JSONL."""
    from republica.experiments.runner import resume_experiment

    result = resume_experiment(out, workers=workers)
    console.print(
        f"[green]OK[/green] resume {result['experiment']}: "
        f"{result['n_ok']}/{result['n_tasks']} corridas pendientes ok, "
        f"{result['n_failed']} fallidas ({result['elapsed_seconds']:.1f}s)"
    )


@experiment_app.command("load")
def experiment_load(
    out: Annotated[Path, typer.Argument(help="Directorio de un experimento ya corrido.")],
    db: Annotated[
        Path, typer.Option("--db", help="Archivo DuckDB de destino (ADR 008 secc. 3).")
    ] = Path("simulations/republica.duckdb"),
) -> None:
    """`republica experiment load <dir> --db <archivo>` (ADR 008 secc. 3):
    carga las corridas del experimento en DuckDB (idempotente). Requiere el
    extra opcional `analysis` (`uv sync --group dev --extra analysis`)."""
    # Hallazgo #6 de REVIEW_003: `experiments/store.py` importa `duckdb` de
    # forma PEREZOSA (dentro de `_duckdb()`), nunca a nivel de modulo, asi
    # que `from republica.experiments.store import load_experiment` nunca
    # levanta `ImportError` -- el guard de import de abajo era codigo
    # muerto; el extra faltante recien se nota adentro de `load_experiment`,
    # como `RuntimeError` (mensaje en castellano), que es lo que se atrapa.
    from republica.experiments.store import load_experiment

    try:
        result = load_experiment(out, db)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[green]OK[/green] {result['runs_seen']} corridas de {result['experiment']} -> {db}"
    )


@experiment_app.command("report")
def experiment_report(
    out: Annotated[Path, typer.Argument(help="Directorio de un experimento ya corrido.")],
) -> None:
    """`republica experiment report <dir>` (ADR 008 secc. 4): escribe
    `report.md` (y PNG en `plots/` si `matplotlib` esta instalado)."""
    from republica.experiments.report import build_report

    path = build_report(out)
    console.print(f"[green]OK[/green] reporte -> {path}")


def _ml_runtime_error(exc: RuntimeError) -> None:
    """Hallazgo #6 de REVIEW_003: `ml/*.py` importa sklearn/duckdb de forma
    PEREZOSA (dentro de cada funcion que los necesita), nunca a nivel de
    modulo -- `from republica.ml.X import fn` nunca levanta `ImportError`
    (por eso el viejo `try/except ImportError` alrededor del import de cada
    comando de abajo era codigo muerto: el extra faltante recien se nota
    ADENTRO de `fn(...)`, como `RuntimeError` con el mensaje en castellano
    de `_MISSING_SKLEARN_MSG`/`_MISSING_DUCKDB_MSG` -- es ESA llamada la que
    hay que envolver)."""
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(code=1) from exc


@ml_app.command("dataset")
def ml_dataset_cmd(
    sources: Annotated[
        list[Path],
        typer.Argument(help="Directorios (recorridos con **/*.jsonl) o archivos .jsonl."),
    ],
    out: Annotated[Path, typer.Option("--out", help="CSV de salida (ADR 009 secc. 2).")] = Path(
        "data/ml/decisions.csv"
    ),
) -> None:
    """`republica ml dataset <dir|jsonl...> --out data/ml/decisions.csv`
    (ADR 009 secc. 2): una fila por (actor, mes). Escribe tambien un
    `.parquet` si `pandas`+`pyarrow` estan instalados."""
    from republica.ml.dataset import build_dataset

    result = build_dataset(sources, out)
    console.print(
        f"[green]OK[/green] {result['n_rows']} filas de {result['n_runs']} corridas "
        f"({result['n_failed_runs']} ilegibles) -> {result['out_csv']}"
        + (f" (+ {result['out_parquet']})" if result["out_parquet"] else "")
    )


@ml_app.command("train")
def ml_train_cmd(
    runs: Annotated[
        list[Path], typer.Argument(help="Directorios o archivos .jsonl con corridas ya guardadas.")
    ],
    out: Annotated[Path, typer.Option("--out", help="Archivo .joblib de salida.")] = Path(
        "data/ml/surrogate_rules.joblib"
    ),
    brain: Annotated[
        str, typer.Option("--brain", help="Cerebro que imitan las corridas (metadata).")
    ] = "rules",
    allow_in_sample: Annotated[
        bool,
        typer.Option(
            "--allow-in-sample",
            help="Permitir fuentes con <=2 semillas (val/test quedan in-sample, ADR 009 secc. 3).",
        ),
    ] = False,
) -> None:
    """`republica ml train --runs <dir|jsonl...> --brain rules --out
    data/ml/surrogate_rules.joblib` (ADR 009 secc. 3): un pipeline sklearn
    por rol. Requiere el extra opcional `ml`."""
    from republica.ml.surrogate import train_surrogate

    try:
        result = train_surrogate(runs, out, brain=brain, allow_in_sample=allow_in_sample)
    except RuntimeError as exc:
        _ml_runtime_error(exc)
        return

    n_skipped = len(result["roles"]) - len(result["metrics"])
    skipped_note = f", {n_skipped} sin suficiente variedad de 'position'" if n_skipped else ""
    console.print(
        f"[green]OK[/green] sustituto de '{brain}': {len(result['metrics'])} pipelines entrenados "
        f"de {len(result['roles'])} roles{skipped_note} -> {out}"
    )
    for role, m in result["metrics"].items():
        console.print(
            f"  {role}: position_acc(val)={m['position_accuracy_val']:.3f} "
            f"intensity_mae(val)={m['intensity_mae_val']:.3f} n_train={m['n_train']}"
        )


@ml_app.command("evaluate")
def ml_evaluate_cmd(
    model: Annotated[Path, typer.Option("--model", help="Archivo .joblib de 'ml train'.")],
    seeds: Annotated[
        str, typer.Option("--seeds", help="Rango 'inicio:fin' (exclusivo), ej. 100:130.")
    ],
    months: Annotated[int, typer.Option(help="Meses por corrida.")] = 48,
    fallback: Annotated[
        str | None, typer.Option(help="Brain de respaldo (active learning), si aplica.")
    ] = None,
) -> None:
    """`republica ml evaluate --model ... --seeds 100:130` (ADR 009 secc.
    3): agreement rate en semillas held-out, re-simulando `rules` vs
    `surrogate:<model>`. Reporta las 4 metricas del hallazgo #1 de
    REVIEW_003 (`agreement_rate` solo, sin baseline, es casi trivial contra
    actores por reglas)."""
    from republica.ml.surrogate import evaluate_surrogate

    start_s, _, end_s = seeds.partition(":")
    seed_range = list(range(int(start_s), int(end_s)))
    try:
        result = evaluate_surrogate(model, seed_range, months=months, fallback=fallback)
    except RuntimeError as exc:
        _ml_runtime_error(exc)
        return
    console.print(
        f"[green]OK[/green] agreement_rate={result['agreement_rate']:.3f} "
        f"(majority_baseline={result['majority_baseline']:.3f}, "
        f"ml_roles_only={result['agreement_ml_roles_only']:.3f}, "
        f"balanced={result['balanced_agreement']:.3f}) "
        f"sobre {result['n_actor_months']} (actor, mes) de {len(seed_range)} semillas "
        f"({result['n_missing_actor_months']} sin contraparte en 'surrogate')"
    )
    for role, rate in sorted(result["per_role_agreement"].items()):
        console.print(f"  {role}: {rate:.3f}")


@ml_app.command("retrain")
def ml_retrain_cmd(
    model: Annotated[Path, typer.Option("--model", help="Modelo .joblib a reentrenar.")],
    runs: Annotated[
        list[Path],
        typer.Option("--runs", help="Mismas corridas usadas en 'ml train' (repetible)."),
    ],
    out: Annotated[Path, typer.Option("--out", help="Archivo .joblib de salida.")],
    queue: Annotated[
        Path | None,
        typer.Option(
            "--queue", help="Cola de active learning (default: data/ml/active_queue.jsonl)."
        ),
    ] = None,
) -> None:
    """`republica ml retrain --queue` (ADR 009 secc. 4): reentrena sumando
    `active_queue.jsonl` al split de entrenamiento."""
    from republica.ml.active import retrain_with_queue

    try:
        result = retrain_with_queue(model, out, queue_path=queue, sources=runs)
    except RuntimeError as exc:
        _ml_runtime_error(exc)
        return
    console.print(
        f"[green]OK[/green] reentrenado con {result['n_queue_rows_added']} filas de la cola "
        f"-> {out}"
    )


@ml_app.command("regimes")
def ml_regimes_cmd(
    db: Annotated[
        Path, typer.Option("--db", help="DuckDB ya cargado con 'experiment load'.")
    ] = Path("simulations/republica.duckdb"),
    describe: Annotated[
        bool,
        typer.Option("--describe", help="Imprime la tabla de centroides y una frase por cluster."),
    ] = False,
) -> None:
    """`republica ml regimes --db ... [--describe]` (ADR 009 secc. 6):
    clustering de regimenes sobre lo ya cargado en DuckDB."""
    from republica.ml.regimes import run_regimes

    try:
        result = run_regimes(db, describe=describe)
    except RuntimeError as exc:
        _ml_runtime_error(exc)
        return
    console.print(
        f"[green]OK[/green] {result['n_runs']} corridas, k={result['k']} "
        f"(silhouette={result['silhouette']:.3f}, "
        f"{result['n_components']} comp. PCA, {result['explained_variance']:.1%} varianza)"
        if result["n_runs"]
        else "[yellow]sin corridas[/yellow]"
    )
    if describe:
        table = Table(title="Regimenes")
        table.add_column("cluster")
        table.add_column("n")
        table.add_column("descripcion")
        for d in result.get("descriptions", []):
            centroid = next(c for c in result["centroids"] if c["cluster"] == d["cluster"])
            table.add_row(str(d["cluster"]), str(int(centroid["n_runs"])), d["sentence"])
        console.print(table)


@early_warning_app.command("train")
def ml_early_warning_train_cmd(
    runs: Annotated[list[Path], typer.Option("--runs", help="Directorios o .jsonl (repetible).")],
    out: Annotated[Path, typer.Option("--out", help="Archivo .joblib de salida.")] = Path(
        "data/ml/early_warning.joblib"
    ),
    allow_in_sample: Annotated[
        bool,
        typer.Option(
            "--allow-in-sample",
            help="Permitir fuentes con <=2 semillas (val/test quedan in-sample, ADR 009 secc. 5).",
        ),
    ] = False,
) -> None:
    """`republica ml early-warning train --runs <dir> --out ...` (ADR 009
    secc. 5)."""
    from republica.ml.early_warning import train_early_warning

    try:
        result = train_early_warning(runs, out, allow_in_sample=allow_in_sample)
    except RuntimeError as exc:
        _ml_runtime_error(exc)
        return
    console.print(
        f"[green]OK[/green] AUC(val)={result['auc_val']:.3f} AUC(test)={result['auc_test']:.3f} "
        f"sobre {result['n_rows']} filas ({result['n_positive']} positivas) -> {out}"
    )


@early_warning_app.command("predict")
def ml_early_warning_predict_cmd(
    model: Annotated[
        Path, typer.Option("--model", help="Archivo .joblib de 'early-warning train'.")
    ],
    run: Annotated[Path, typer.Option("--run", help="Archivo .jsonl de una corrida.")],
    month: Annotated[int, typer.Option(help="Mes a evaluar.")],
) -> None:
    """`republica ml early-warning predict --run run.jsonl --month N`."""
    from republica.ml.early_warning import predict_from_run, risk_sentence

    try:
        result = predict_from_run(model, run, month)
    except RuntimeError as exc:
        _ml_runtime_error(exc)
        return
    console.print(risk_sentence(result["probability"], result["top_features"]))


def _core_import_error(exc: ImportError) -> None:
    console.print(
        f"[red]{exc}[/red]\n"
        "[red]`republica core` necesita el extra opcional `core` "
        "(`uv sync --group dev --extra core`, instala `numpy`).[/red]"
    )
    raise typer.Exit(code=1) from exc


@core_app.command("run")
def core_run(
    agents: Annotated[int, typer.Option("--agents", help="Cantidad de agentes.")] = 10_000,
    turns: Annotated[int, typer.Option("--turns", help="Turnos de la corrida.")] = 500,
    seed: Annotated[int, typer.Option("--seed", help="Semilla.")] = 7,
    out: Annotated[
        Path, typer.Option("--out", help="JSON de salida (metricas por turno + clasificacion).")
    ] = Path("simulations/core/run.json"),
    config: Annotated[
        list[str] | None,
        typer.Option(
            "--config",
            help="Override `clave=valor` sobre CoreConfig (repetible, ej. transport_cost=0.1).",
        ),
    ] = None,
) -> None:
    """`republica core run --agents N --turns T --seed S --out archivo.json`
    (ADR 010 secc. 7): corre una semilla, escribe el JSON con la serie de
    metricas por turno y la clasificacion final (medio de intercambio,
    Herfindahl, privacion, Gini)."""
    try:
        from republica.core.run import apply_overrides, parse_config_overrides, simulate
        from republica.core.world import CoreConfig
    except ImportError as exc:
        _core_import_error(exc)
        return

    cfg = CoreConfig(n_agents=agents, turns=turns, seed=seed)
    if config:
        cfg = apply_overrides(cfg, parse_config_overrides(config))

    start = time.monotonic()
    result = simulate(cfg)
    elapsed = time.monotonic() - start

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result), encoding="utf-8")

    cls = result["classification"]
    medium = cls["medium_of_exchange"] or "ninguno"
    console.print(
        f"[green]OK[/green] {agents} agentes x {turns} turnos (semilla {seed}) "
        f"en {elapsed:.1f}s -> {out}"
    )
    console.print(
        f"medio de intercambio: {medium} (turno {cls['emergence_turn']}), "
        f"Herfindahl={cls['herfindahl_intermediates']:.3f}, "
        f"indirectos={cls['indirect_trade_share']:.1%}, "
        f"privacion media={cls['mean_deprivation']:.2f}, Gini={cls['inventory_gini']:.3f}"
    )


@core_app.command("batch")
def core_batch(
    seeds: Annotated[int, typer.Option("--seeds", help="Cantidad de semillas (0..N-1).")] = 100,
    agents: Annotated[int, typer.Option("--agents", help="Cantidad de agentes.")] = 10_000,
    turns: Annotated[int, typer.Option("--turns", help="Turnos por corrida.")] = 500,
    out: Annotated[
        Path, typer.Option("--out", help="Directorio de salida (un JSON por semilla).")
    ] = Path("simulations/core/batch"),
    workers: Annotated[int, typer.Option("--workers", help="Procesos en paralelo.")] = 4,
    config: Annotated[
        list[str] | None,
        typer.Option(
            "--config",
            help="Override `clave=valor` sobre CoreConfig, igual en TODAS las semillas "
            "(repetible; ADR 010 secc. 7: 'varia nada mas que la semilla' salvo que se pase esto).",
        ),
    ] = None,
) -> None:
    """`republica core batch --seeds 100 --turns 500 --out simulations/core/batch/ --workers 4`
    (ADR 010 secc. 7): corre `seeds` semillas (0..seeds-1) con la MISMA
    config salvo la semilla."""
    try:
        from republica.core.run import apply_overrides, parse_config_overrides, run_batch
        from republica.core.world import CoreConfig
    except ImportError as exc:
        _core_import_error(exc)
        return

    cfg = CoreConfig(n_agents=agents, turns=turns)
    if config:
        cfg = apply_overrides(cfg, parse_config_overrides(config))

    result = run_batch(cfg, list(range(seeds)), out, workers=workers)
    console.print(
        f"[green]OK[/green] {result['n_ok']}/{result['n_seeds']} corridas "
        f"({result['n_failed']} fallidas) en {result['elapsed_seconds']:.1f}s "
        f"-> {result['out_dir']}"
    )
    if result["n_failed"]:
        console.print(f"[yellow]fallidas: {result['failed']}[/yellow]")


@core_app.command("classify")
def core_classify(
    directory: Annotated[Path, typer.Argument(help="Directorio de una corrida de `core batch`.")],
    shell_sweep: Annotated[
        Path | None,
        typer.Option("--shell-sweep", help="Directorio del barrido de abundancia de conchas (H3)."),
    ] = None,
    transport_sweep: Annotated[
        Path | None,
        typer.Option(
            "--transport-sweep", help="Directorio del barrido de costo de transporte (H4)."
        ),
    ] = None,
) -> None:
    """`republica core classify <dir>` (ADR 010 secc. 6-7): escribe
    `<dir>/report.md` con H1-H4 marcadas CUMPLIDA/NO CUMPLIDA, IC bootstrap
    y graficos PNG si `matplotlib` esta instalado."""
    try:
        from republica.core.run import classify_directory
    except ImportError as exc:
        _core_import_error(exc)
        return

    report = classify_directory(
        directory, shell_sweep_dir=shell_sweep, transport_sweep_dir=transport_sweep
    )
    console.print(f"[green]OK[/green] report.md escrito en {directory / 'report.md'}")
    console.print(report.splitlines()[0] if report else "")


@app.command()
def ui() -> None:
    """`republica ui` (ADR 009 secc. 7): lanza la UI Streamlit
    (`ui/app.py`). Requiere el extra opcional `ui`
    (`uv sync --group dev --extra ui`)."""
    try:
        import streamlit  # noqa: F401, PLC0415
    except ImportError as exc:
        console.print(
            "[red]streamlit no esta instalado en este entorno. Instalar el extra opcional "
            "`ui` con `uv sync --group dev --extra ui` (o `pip install "
            "'republica-artificial[ui]'`) para usar `republica ui`.[/red]"
        )
        raise typer.Exit(code=1) from exc

    import subprocess
    import sys

    app_path = Path(__file__).resolve().parent / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], check=False)


@app.command()
def calibrate(
    country_id: Annotated[
        str, typer.Option("--country", help="Paquete de pais (ADR 011, ej. 'argentina').")
    ],
    train: Annotated[
        str, typer.Option(help="Ventana de entrenamiento 'YYYY-MM:YYYY-MM' (ADR 011 secc. 7).")
    ],
    holdout: Annotated[
        str,
        typer.Option(help="Ventana de holdout 'YYYY-MM:YYYY-MM', corrida UNA SOLA VEZ al final."),
    ],
    run_id: Annotated[str, typer.Option("--run-id", help="Nombre de la corrida de calibracion.")],
    budget: Annotated[
        int, typer.Option(help="Cantidad de evaluaciones de CMA-ES (A3, default 400).")
    ] = 400,
    quick: Annotated[
        bool,
        typer.Option(
            "--quick",
            help="Budget=40, stride=12 (tests/CI, ADR 011 secc. 7 punto 4): ignora --budget/"
            "--stride si se pasa.",
        ),
    ] = False,
    stride: Annotated[
        int, typer.Option(help="Meses entre arranques sucesivos (ADR 011 secc. 7).")
    ] = 3,
    lambda_reg: Annotated[
        float, typer.Option(help="Peso de la regularizacion L2 hacia Aurora.")
    ] = 0.01,
    workers: Annotated[
        int, typer.Option(help="Procesos del pool (paralelo por mes de arranque).")
    ] = 4,
    seed: Annotated[int, typer.Option(help="Semilla de CMA-ES.")] = 42,
) -> None:
    """`republica calibrate` (A3, ADR 011 secc. 7): CMA-ES sobre los
    coeficientes de `country.json` contra `history/`, con holdout evaluado
    una sola vez al final. Escribe `data/countries/<id>/calibration/<run_id>/`
    (`coefficients.json`, `report.md`, `history.csv`, `plots/`)."""
    from republica.calibration.run import CalibrationRunConfig, parse_range, run_calibration

    if quick:
        budget = 40
        stride = 12

    train_start, train_end = parse_range(train)
    holdout_start, holdout_end = parse_range(holdout)

    cfg = CalibrationRunConfig(
        country_id=country_id,
        run_id=run_id,
        train_start=train_start,
        train_end=train_end,
        holdout_start=holdout_start,
        holdout_end=holdout_end,
        budget=budget,
        stride=stride,
        lambda_reg=lambda_reg,
        workers=workers,
        seed=seed,
    )
    console.print(
        f"[cyan]Calibrando[/cyan] {country_id} train={train} holdout={holdout} "
        f"budget={budget} stride={stride} workers={workers}"
    )
    run_dir = run_calibration(cfg)
    console.print(f"[green]OK[/green] -> {run_dir}")


@app.command()
def validate(
    country_id: Annotated[
        str, typer.Option("--country", help="Paquete de pais (ADR 011; hoy solo 'argentina').")
    ],
    out: Annotated[Path, typer.Option("--out", help="Directorio de salida de la validacion.")],
    calibration_run_id: Annotated[
        str,
        typer.Option("--calibration", help="run_id de `republica calibrate` (A3), ej. 'a3_main'."),
    ] = "a3_main",
    seeds: Annotated[int, typer.Option(help="Semillas por prueba y por brazo.")] = 50,
    seed_base: Annotated[
        int, typer.Option(help="Primera semilla (las demas son consecutivas).")
    ] = 1,
    months_cap: Annotated[
        int | None,
        typer.Option(
            "--months-cap",
            help="Recorta los meses de CADA prueba (smoke tests). Sin esto: 24/54/96 del ADR.",
        ),
    ] = None,
    tests: Annotated[
        str | None,
        typer.Option(
            "--tests", help="Subconjunto separado por comas, ej. 'V1,V3'. Default: las 3."
        ),
    ] = None,
    resamples: Annotated[
        int, typer.Option(help="Remuestreos del bootstrap de los IC 95 %.")
    ] = 2000,
    plots: Annotated[
        bool, typer.Option("--plots/--no-plots", help="Graficos (requiere el extra `analysis`).")
    ] = True,
) -> None:
    """`republica validate` (A4, ADR 011 secc. 8): corre las tres pruebas de
    validacion historica (V1 1988-1990, V2 1998-2002, V3 2016-2023) con los
    coeficientes calibrados y con los de Aurora sin calibrar (control C), y
    escribe `registration.json` (hipotesis y shocks forzados REGISTRADOS
    ANTES de correr), `results.json`, `report.md` y `plots/`."""
    from republica.validation.argentina import TESTS_BY_ID, run_validation

    if country_id != "argentina":
        raise typer.BadParameter(
            f"La validacion historica (A4, ADR 011 secc. 8) esta definida solo para "
            f"'argentina'; se pidio {country_id!r}."
        )
    test_ids = None
    if tests:
        test_ids = [t.strip().upper() for t in tests.split(",") if t.strip()]
        unknown = [t for t in test_ids if t not in TESTS_BY_ID]
        if unknown:
            raise typer.BadParameter(
                f"Pruebas desconocidas: {unknown}. Disponibles: {sorted(TESTS_BY_ID)}."
            )
    console.print(
        f"[cyan]Validando[/cyan] {country_id} calibracion={calibration_run_id} "
        f"seeds={seeds} months_cap={months_cap or 'ADR'} -> {out}"
    )
    t0 = time.time()
    payload = run_validation(
        out,
        seeds=seeds,
        seed_base=seed_base,
        months_cap=months_cap,
        calibration_run_id=calibration_run_id,
        test_ids=test_ids,
        resamples=resamples,
        make_plots=plots,
        progress=lambda msg: console.print(f"  [dim]{msg}[/dim]"),
    )
    table = Table(title="Validacion historica (A4, ADR 011 secc. 8)")
    table.add_column("prueba")
    table.add_column("calibrado")
    table.add_column("Aurora sin calibrar")
    for t in payload["tests"]:
        table.add_row(
            t["test_id"],
            "CUMPLIDA" if t["metrics"]["calibrated"]["passes"] else "NO CUMPLIDA",
            "CUMPLIDA" if t["metrics"]["aurora"]["passes"] else "NO CUMPLIDA",
        )
    control = payload["control_verdict"]
    table.add_row(
        "C",
        "-",
        "CUMPLIDA" if control["passes"] else "NO CUMPLIDA",
    )
    console.print(table)
    console.print(
        f"[green]OK[/green] {time.time() - t0:.1f}s -> {out / 'report.md'} "
        f"(registro previo: {out / 'registration.json'})"
    )


@country_app.command("info")
def country_info(
    country_id: Annotated[str, typer.Argument(help="Id del paquete (ej. 'argentina').")],
) -> None:
    """`republica country info <id>` (ADR 011): fechas de arranque
    disponibles con su cobertura de estado inicial (source/proxy/assumed),
    features del paquete y golpes del calendario politico."""
    import json as _json

    from republica.world.countries import country_pack_dir
    from republica.world.regime import load_coup_dates

    pack_dir = country_pack_dir(country_id)
    raw = _json.loads((pack_dir / "country.json").read_text(encoding="utf-8"))

    console.print(f"[bold]{raw.get('name', country_id)}[/bold] ({country_id})")
    console.print(f"  paquete: {pack_dir}")

    features = raw.get("features", {})
    feat_str = ", ".join(f"{k}={v}" for k, v in features.items())
    console.print(f"  features: {feat_str}")

    table = Table(title="Estados iniciales (initial_states, ADR 011 secc. 2)")
    table.add_column("fecha")
    table.add_column("source", justify="right")
    table.add_column("proxy", justify="right")
    table.add_column("assumed", justify="right")
    initial_states = raw.get("initial_states", {})
    for date in sorted(initial_states):
        entry = initial_states[date]
        counts = {"source": 0, "proxy": 0, "assumed": 0}
        for prov in entry.values():
            if prov.get("assumed"):
                counts["assumed"] += 1
            elif "source" in prov:
                counts["source"] += 1
            elif "proxy" in prov:
                counts["proxy"] += 1
        table.add_row(date, str(counts["source"]), str(counts["proxy"]), str(counts["assumed"]))
    console.print(table)

    events_csv = pack_dir / "politics" / "events.csv"
    coups = load_coup_dates(events_csv)
    console.print(
        f"  golpes en politics/events.csv: {len(coups)} "
        f"({', '.join(f'{y}-{m:02d}' for y, m in coups[:8])}"
        f"{', ...' if len(coups) > 8 else ''})"
    )

    constitutions_csv = pack_dir / "constitutions.csv"
    if constitutions_csv.exists():
        cons_text = constitutions_csv.read_text(encoding="utf-8").strip()
        console.print(f"  constitutions.csv: {cons_text}")


if __name__ == "__main__":
    app()
