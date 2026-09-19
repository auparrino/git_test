"""Corre la sonda exploratoria (ADR 020): unos pocos arranques historicos
reales, muchas semillas, SIN hipotesis previa y SIN puntuar nada.

Arma la corrida igual que `republica run --country <pais> --start <mes>`
(estado inicial real, epoca de partidos, calendario de regimen, exogenas
historicas, coeficientes calibrados) reusando `world/countries.py`,
`calibration/` y `engine/` tal cual: este modulo NO modifica ninguno de
esos paquetes.

Lo que agrega es la medicion: saturacion contra las cotas de
`country.json -> ranges`, valores fuera de rango FISICO (mas anchos que las
cotas: una violacion es un bug, no un resultado), terminacion y eventos.

Dos niveles de tolerancia a fallas, los dos deliberados (ADR 020 secc. 2.4
y secc. 5 "Fechas fuera de rango"):

1. Una SEMILLA que revienta se registra con su excepcion y no tumba el
   escenario (mismo criterio que `backtest/runner.py`, que descarta la
   semilla con la patologia numerica).
2. Un ESCENARIO que no arranca -- tipicamente `--start` fuera del rango con
   series (`calibration/initial_states.py` cubre 1961-2023) -- se registra
   con su error y no tumba la corrida.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import math
import statistics
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from republica.engine.policy import PassivePolicy
from republica.engine.simulation import run as run_simulation
from republica.world.config import DEFAULT_DATA_DIR
from republica.world.countries import (
    historical_exogenous_series,
    load_country_pack,
)
from republica.world.economy import merge_structural_coefficients

#: Cotas FISICAS, a proposito MAS ANCHAS que las de `country.json ->
#: ranges` (ADR 020 secc. 2.3): `world/state.py::clamp_state` corre todos
#: los meses, asi que ninguna de estas se puede violar salvo que algo este
#: roto (un camino que saltea el clamp, un `model_construct` sin validar,
#: el modo anual que clampea solo al cierre del ano). Una violacion es un
#: BUG que hay que ir a buscar, no un resultado que discutir.
PHYSICAL_RANGES: dict[str, tuple[float, float]] = {
    "gdp": (0.0, 100000.0),
    "gdp_growth": (-90.0, 90.0),
    "inflation": (-100.0, 1000.0),
    "unemployment": (0.0, 40.0),
    "real_wage": (10.0, 400.0),
    "interest_rate": (0.0, 100000.0),
    "exchange_rate": (0.0, 1e12),
    "reserves": (0.0, 1e7),
    "public_debt": (0.0, 2000.0),
    "fiscal_balance": (-100.0, 100.0),
    "poverty": (0.0, 100.0),
    "government_approval": (0.0, 100.0),
    "congress_support": (0.0, 100.0),
    "political_stability": (0.0, 100.0),
    "social_tension": (0.0, 100.0),
    "institutional_confidence": (0.0, 100.0),
    "consumer_confidence": (0.0, 100.0),
    "protest_level": (0.0, 100.0),
    "inequality": (0.0, 100.0),
    "crime_perception": (0.0, 100.0),
}

#: Tolerancia relativa para decidir que un valor "toca" su cota. No se usa
#: `==` porque la cota puede ser un numero grande (`exchange_rate` hasta
#: 1e6) donde el ultimo bit de un `float` ya no es despreciable.
_BOUND_TOL = 1e-9


@dataclass(frozen=True)
class ProbeScenario:
    """Una fila de `probe_scenarios.csv` (ADR 020 secc. 4).

    `expected` es TEXTO LIBRE a proposito: describe que paso de verdad, se
    imprime al lado del resultado del modelo y **no se compara
    programaticamente con nada**. En cuanto se estructure, alguien va a
    querer puntuarlo, y entonces esto deja de ser una sonda (secc. 3)."""

    label: str
    start: str
    months: int
    expected: str


@dataclass(frozen=True)
class Saturation:
    """Una variable de estado contra su cota, en UNA semilla."""

    variable: str
    bound: str  # "lo" | "hi"
    bound_value: float
    first_month: int
    months_at_bound: int
    months_run: int

    @property
    def share_at_bound(self) -> float:
        return self.months_at_bound / self.months_run if self.months_run else 0.0


@dataclass(frozen=True)
class PhysicalViolation:
    """Un valor fuera del rango FISICO: sintoma de bug (ADR 020 secc. 2.3)."""

    variable: str
    month: int
    value: float
    lo: float
    hi: float


@dataclass
class SeedProbe:
    """El resultado de UNA semilla de UN escenario."""

    seed: int
    outcome: str = ""
    months_run: int = 0
    saturation: dict[str, Saturation] = field(default_factory=dict)
    violations: list[PhysicalViolation] = field(default_factory=list)
    first_event_month: dict[str, int] = field(default_factory=dict)
    error: str = ""

    @property
    def failed(self) -> bool:
        return bool(self.error)


@dataclass
class ScenarioResult:
    """El resultado de UN escenario: N semillas mas, si el escenario ni
    siquiera arranco, el error que lo impidio (`error`)."""

    scenario: ProbeScenario
    seeds: list[SeedProbe] = field(default_factory=list)
    error: str = ""
    wall_seconds: float = 0.0

    @property
    def failed(self) -> bool:
        return bool(self.error)

    @property
    def ok_seeds(self) -> list[SeedProbe]:
        return [s for s in self.seeds if not s.failed]


# --------------------------------------------------------------------------
# Escenarios: datos, no codigo (ADR 020 secc. 4)
# --------------------------------------------------------------------------


def scenarios_path(country_id: str, data_dir: Path | None = None) -> Path:
    """`data/countries/<pais>/probe_scenarios.csv`."""
    base = data_dir if data_dir is not None else DEFAULT_DATA_DIR
    return base / "countries" / country_id / "probe_scenarios.csv"


def _repo_relative(path: Path) -> str:
    """La ruta relativa al repo si cae adentro, absoluta si no. Una corrida
    de referencia se commitea: no puede llevar la ruta del worktree de
    quien la corrio (el diff entre rondas seria ruido puro)."""
    root = DEFAULT_DATA_DIR.parent
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def load_scenarios(path: Path) -> list[ProbeScenario]:
    """Lee el CSV de escenarios. Agregar un escenario es agregar una fila:
    no hay ninguna lista de escenarios en Python, ni siquiera como default
    (ADR 020 secc. 4)."""
    if not path.exists():
        raise FileNotFoundError(
            f"No hay archivo de escenarios en {path}. La sonda no trae escenarios por "
            "defecto: se declaran en datos (ADR 020 secc. 4), con columnas "
            "label,start,months,expected."
        )
    scenarios: list[ProbeScenario] = []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = {"label", "start", "months", "expected"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: faltan columnas {sorted(missing)}.")
        for row in reader:
            label = (row.get("label") or "").strip()
            if not label or label.startswith("#"):
                continue
            try:
                months = int((row.get("months") or "").strip())
            except ValueError as exc:
                raise ValueError(
                    f"{path}: `months` invalido en la fila {label!r}: {row.get('months')!r}."
                ) from exc
            scenarios.append(
                ProbeScenario(
                    label=label,
                    start=(row.get("start") or "").strip(),
                    months=months,
                    expected=(row.get("expected") or "").strip(),
                )
            )
    if not scenarios:
        raise ValueError(f"{path}: no hay ninguna fila de escenario utilizable.")
    return scenarios


# --------------------------------------------------------------------------
# Las tres mediciones (ADR 020 secc. 2.2 y 2.3)
# --------------------------------------------------------------------------


def detect_saturation(
    series: dict[str, Sequence[float]],
    ranges: dict[str, tuple[float, float]],
) -> dict[str, Saturation]:
    """Para cada variable de `series` con cota en `ranges`: en que mes toca
    por primera vez una cota y cuantos meses pasa ahi (ADR 020 secc. 2.2).

    Los meses son 1-based, igual que `MonthRecord.month_index`. Si una
    variable toca las dos cotas a lo largo de la corrida se reporta aquella
    en la que pasa MAS meses (y, a igualdad, la que toca primero): lo que
    interesa es donde se queda clavada, no que la haya rozado.

    Las variables que nunca tocan su cota NO aparecen en el resultado: es
    lo que hace que la tabla del reporte sea legible."""
    found: dict[str, Saturation] = {}
    for variable, values in series.items():
        bounds = ranges.get(variable)
        if bounds is None or not values:
            continue
        lo, hi = bounds
        best: Saturation | None = None
        for name, bound in (("lo", lo), ("hi", hi)):
            tol = _BOUND_TOL * max(1.0, abs(bound))
            months = [i + 1 for i, v in enumerate(values) if abs(v - bound) <= tol]
            if not months:
                continue
            candidate = Saturation(
                variable=variable,
                bound=name,
                bound_value=bound,
                first_month=months[0],
                months_at_bound=len(months),
                months_run=len(values),
            )
            if best is None or (candidate.months_at_bound, -candidate.first_month) > (
                best.months_at_bound,
                -best.first_month,
            ):
                best = candidate
        if best is not None:
            found[variable] = best
    return found


def detect_physical_violations(
    series: dict[str, Sequence[float]],
    physical: dict[str, tuple[float, float]] | None = None,
) -> list[PhysicalViolation]:
    """Valores fuera del rango FISICO (ADR 020 secc. 2.3): desempleo > 40 %,
    salario real fuera de [10, 400], NaN/inf, etc. Con `clamp_state`
    corriendo todos los meses esto no deberia poder pasar; si pasa, es un
    bug. Se devuelve la PRIMERA violacion de cada variable (no las 200 que
    siguen, que son la misma)."""
    table = physical if physical is not None else PHYSICAL_RANGES
    out: list[PhysicalViolation] = []
    for variable, values in series.items():
        bounds = table.get(variable)
        if bounds is None:
            continue
        lo, hi = bounds
        for i, v in enumerate(values):
            if math.isnan(v) or math.isinf(v) or v < lo or v > hi:
                out.append(PhysicalViolation(variable=variable, month=i + 1, value=v, lo=lo, hi=hi))
                break
    return out


# --------------------------------------------------------------------------
# Corrida
# --------------------------------------------------------------------------


def _initial_state_override(country_id: str, start: str) -> dict[str, float] | None:
    """Estado inicial real para cualquier mes con series (mismo fallback
    que `cli.py::_estado_inicial_de_cualquier_mes`). `None` si el pais no
    es Argentina o la fecha cae fuera del rango: en ese caso se deja que
    `load_country_pack` levante su propio error, que es el que el escenario
    reporta."""
    if country_id != "argentina":
        return None
    from republica.calibration.initial_states import flat_initial_state

    return flat_initial_state(start)


def _series_from_history(history) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    for rec in history.records:
        for key, value in rec.state.items():
            if isinstance(value, int | float):
                series.setdefault(key, []).append(float(value))
    return series


def _write_seed_csv(path: Path, history) -> None:
    """Un CSV por semilla-escenario (ADR 020 secc. 5): una fila por mes con
    las 21 variables de estado, el modo de regimen, los shocks activos y
    los eventos. Es lo que permite trazar a mano la corrida que mas se
    aleja sin volver a correr nada."""
    records = history.records
    if not records:
        path.write_text("month,date\n", encoding="utf-8")
        return
    state_keys = sorted(records[0].state)
    header = ["month", "date", *state_keys, "regime_mode", "shocks_active", "events"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for rec in records:
            writer.writerow(
                [
                    rec.month_index,
                    rec.date,
                    *[rec.state.get(k, "") for k in state_keys],
                    rec.regime_mode,
                    "|".join(rec.shocks_active),
                    "|".join(rec.events),
                ]
            )


def _build_run_kwargs(
    country_id: str,
    scenario: ProbeScenario,
    calibration_run_id: str | None,
    regime_transitions: bool,
) -> dict:
    """Todo lo que NO depende de la semilla, armado una sola vez por
    escenario. Replica lo que hace `cli.py::run` con `--country/--start`:
    paquete de pais, epoca, calendario de regimen, exogenas historicas,
    coeficientes calibrados (incluido el cambio de vector en caliente de
    ADR 017 secc. 3.6) y el macro de ADR 012/016."""
    pack = load_country_pack(
        country_id,
        scenario.start,
        scenario.months,
        regime_mode="auto",
        regime_transitions=regime_transitions,
        initial_state_override=_initial_state_override(country_id, scenario.start),
    )
    country = pack.country
    bimonetary = pack.bimonetary_coefficients
    macro_active = country.features.get("macro_regime", False)
    macro = pack.macro_coefficients if macro_active else None
    coefficients_by_fx_regime = None
    if calibration_run_id:
        from republica.calibration.run import (
            load_calibrated_country,
            load_calibrated_vectors_by_group,
        )

        # ADR 017 secc. 3.5: con una calibracion `--by-regime` el vector se
        # elige por el `fx_regime` real del arranque del escenario.
        coeff, bimonetary, calibrated_macro = load_calibrated_country(
            country_id, calibration_run_id, start=scenario.start
        )
        country = country.model_copy(update={"coefficients": coeff})
        if macro_active and calibrated_macro is not None:
            # ADR 016: los `lf_*` son estructurales y no viajan en el
            # vector calibrado; salen del paquete de pais.
            macro = merge_structural_coefficients(calibrated_macro, pack.macro_coefficients)
        coefficients_by_fx_regime = load_calibrated_vectors_by_group(calibration_run_id)
    bimonetary = dataclasses.replace(bimonetary, fx_regime_default=pack.fx_regime_auto)

    era_actors = None
    era_loyalty_table = None
    era_gov_overrides: dict[str, str] = {}
    if pack.era is not None and pack.era.parties is not None:
        era_actors = pack.era.actors
        era_loyalty_table = pack.era.loyalty_table
        if pack.era.governance_path is not None and pack.era.governance_path.exists():
            from republica.world.eras import era_governance_overrides

            era_gov_overrides = era_governance_overrides(pack.era.governance_path)

    exogenous = historical_exogenous_series(
        pack.pack_dir, int(scenario.start[:4]), int(scenario.start[5:7]), scenario.months
    )
    policy_rule = PassivePolicy(
        country.default_policy,
        country.structure.r_neutral,
        country.policy_ranges["interest_rate_target"],
    )
    features = country.features
    kwargs = dict(
        months=scenario.months,
        policy_rule=policy_rule,
        country=country,
        actors_enabled=features.get("actors", True),
        actors=era_actors,
        congress_enabled=features.get("congress", True),
        negotiation_enabled=features.get("negotiation", True),
        cohorts_enabled=features.get("cohorts", True),
        media_enabled=features.get("media", True),
        memory_enabled=features.get("memory", True),
        elections_enabled=features.get("elections", True),
        loyalty_table=era_loyalty_table,
        governance_overrides=era_gov_overrides or None,
        regime_calendar=pack.regime_calendar,
        bimonetary_coefficients=bimonetary,
        historical_exogenous=exogenous,
        macro_coefficients=macro,
        macro_x0=pack.macro_x0 if macro is not None else None,
        macro_m0=pack.macro_m0 if macro is not None else None,
        fx_regime=pack.fx_regime_auto if macro is not None else None,
        coefficients_by_fx_regime=coefficients_by_fx_regime,
    )
    return {"kwargs": kwargs, "ranges": country.ranges}


def run_scenario(
    scenario: ProbeScenario,
    country_id: str,
    calibration_run_id: str | None,
    seeds: int,
    seed_base: int,
    series_dir: Path | None,
    regime_transitions: bool = False,
    physical: dict[str, tuple[float, float]] | None = None,
    progress: Callable[[str], None] | None = None,
) -> ScenarioResult:
    """Corre `seeds` semillas de un escenario. Nunca levanta: un escenario
    que no arranca queda con `error` (ADR 020 secc. 5)."""
    t0 = time.perf_counter()
    result = ScenarioResult(scenario=scenario)
    try:
        built = _build_run_kwargs(country_id, scenario, calibration_run_id, regime_transitions)
    except Exception as exc:  # noqa: BLE001 - el escenario se reporta, la corrida sigue
        result.error = f"{type(exc).__name__}: {exc}"
        result.wall_seconds = time.perf_counter() - t0
        if progress:
            progress(f"{scenario.label}: ERROR -- {result.error}")
        return result

    base_kwargs = built["kwargs"]
    ranges = built["ranges"]
    for i in range(seeds):
        seed = seed_base + i
        probe = SeedProbe(seed=seed)
        try:
            history = run_simulation(seed=seed, **base_kwargs)
        except Exception as exc:  # noqa: BLE001 - la semilla se reporta, el escenario sigue
            probe.error = f"{type(exc).__name__}: {exc}"
            result.seeds.append(probe)
            if progress:
                progress(f"{scenario.label} seed={seed}: EXCEPCION -- {probe.error}")
            continue
        series = _series_from_history(history)
        probe.outcome = history.outcome
        probe.months_run = len(history.records)
        probe.saturation = detect_saturation(series, ranges)
        probe.violations = detect_physical_violations(series, physical)
        for rec in history.records:
            for ev in rec.events:
                probe.first_event_month.setdefault(ev, rec.month_index)
        if series_dir is not None:
            _write_seed_csv(series_dir / f"{scenario.label}__seed{seed}.csv", history)
        result.seeds.append(probe)
    result.wall_seconds = time.perf_counter() - t0
    if progress:
        ok = result.ok_seeds
        meses = f"{statistics.median(p.months_run for p in ok):.0f}" if ok else "-"
        progress(
            f"{scenario.label}: {len(ok)}/{seeds} semillas, mes de fin mediano {meses} "
            f"({result.wall_seconds:.1f}s)"
        )
    return result


def _summarize_scenario(result: ScenarioResult) -> dict:
    """Agrega las semillas de un escenario a lo que se imprime y se guarda
    en `summary.json`. No puntua nada (ADR 020 secc. 3): solo describe."""
    sc = result.scenario
    base = {
        "label": sc.label,
        "start": sc.start,
        "months_requested": sc.months,
        "expected": sc.expected,
        "error": result.error,
        "wall_seconds": round(result.wall_seconds, 2),
    }
    if result.failed:
        return {**base, "seeds_run": 0, "outcomes": {}, "saturation": [], "violations": []}

    ok = result.ok_seeds
    months = sorted(p.months_run for p in ok)
    outcomes: dict[str, int] = {}
    for p in ok:
        outcomes[p.outcome] = outcomes.get(p.outcome, 0) + 1

    saturation: list[dict] = []
    variables = sorted({v for p in ok for v in p.saturation})
    for variable in variables:
        hits = [p.saturation[variable] for p in ok if variable in p.saturation]
        saturation.append(
            {
                "variable": variable,
                "bound": hits[0].bound,
                "bound_value": hits[0].bound_value,
                "seeds": len(hits),
                "seeds_total": len(ok),
                "first_month_median": statistics.median(h.first_month for h in hits),
                "months_at_bound_median": statistics.median(h.months_at_bound for h in hits),
                "share_at_bound_median": statistics.median(h.share_at_bound for h in hits),
            }
        )
    # Lo mas clavado primero: es la lectura que importa.
    saturation.sort(key=lambda d: (-d["share_at_bound_median"], d["variable"]))

    events: list[dict] = []
    all_events = sorted({e for p in ok for e in p.first_event_month})
    for ev in all_events:
        firsts = [p.first_event_month[ev] for p in ok if ev in p.first_event_month]
        events.append(
            {
                "event": ev,
                "seeds": len(firsts),
                "seeds_total": len(ok),
                "first_month_median": statistics.median(firsts),
            }
        )
    events.sort(key=lambda d: (-d["seeds"], d["first_month_median"], d["event"]))

    violations = [{"seed": p.seed, **dataclasses.asdict(v)} for p in ok for v in p.violations]
    exceptions = [{"seed": p.seed, "error": p.error} for p in result.seeds if p.failed]

    return {
        **base,
        "seeds_run": len(ok),
        "seeds_failed": len(exceptions),
        "outcomes": dict(sorted(outcomes.items(), key=lambda kv: (-kv[1], kv[0]))),
        "end_month_median": statistics.median(months) if months else None,
        "end_month_min": months[0] if months else None,
        "end_month_max": months[-1] if months else None,
        "seeds_full_horizon": sum(1 for m in months if m >= sc.months),
        "saturation": saturation,
        "events": events,
        "violations": violations,
        "exceptions": exceptions,
    }


def run_probe(
    out_dir: Path,
    country_id: str = "argentina",
    calibration_run_id: str | None = None,
    seeds: int = 10,
    seed_base: int = 1,
    scenarios: Iterable[ProbeScenario] | None = None,
    scenarios_file: Path | None = None,
    regime_transitions: bool = False,
    write_series: bool = True,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Corre la sonda completa y escribe `summary.json` + `series/`.
    `report.md` lo escribe `probe/report.py::write_report` con lo que
    devuelve esta funcion."""
    path = scenarios_file if scenarios_file is not None else scenarios_path(country_id)
    scen_list = list(scenarios) if scenarios is not None else load_scenarios(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    series_dir = (out_dir / "series") if write_series else None
    if series_dir is not None:
        series_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    results: list[ScenarioResult] = []
    for sc in scen_list:
        results.append(
            run_scenario(
                sc,
                country_id=country_id,
                calibration_run_id=calibration_run_id,
                seeds=seeds,
                seed_base=seed_base,
                series_dir=series_dir,
                regime_transitions=regime_transitions,
                progress=progress,
            )
        )
    payload = {
        "tool": "probe",
        "adr": "ADR 020",
        "country": country_id,
        "calibration": calibration_run_id,
        "seeds": seeds,
        "seed_base": seed_base,
        "regime_transitions": regime_transitions,
        "scenarios_file": _repo_relative(path),
        "wall_seconds": round(time.perf_counter() - t0, 2),
        "scenarios": [_summarize_scenario(r) for r in results],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return payload
