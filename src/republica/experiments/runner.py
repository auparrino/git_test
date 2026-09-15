"""Runner de experimentos en lote (ADR 008 secc. 2).

`run_experiment()` corre cada `(arm, seed)` de un `ExperimentConfig`,
escribe su JSONL en `<out>/<arm>/<seed>.jsonl`, junta los fallos en
`<out>/failed.jsonl` (con traceback, sin frenar el lote) y deja
`<out>/runs.meta.json` (yaml del experimento, `config_hash` por brazo,
version del paquete, timestamp) mas `<out>/metrics.csv` (una fila por
corrida, las metricas de ADR secc. 1 extraidas de su `History`).

`multiprocessing.Pool` para los brazos `rules`/`fake:*`; los brazos
`llm:*` (Ollama serializa, deliverable 2) se corren siempre en serie, sin
importar `--workers` -- si TODOS los brazos son `llm:*`, el lote entero
corre serializado."""

from __future__ import annotations

import json
import multiprocessing
import statistics
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from republica import __version__
from republica.engine import narrate as narrate_mod
from republica.engine.permissions import AUTHORITY_VIOLATION_MARKER
from republica.engine.simulation import run as run_simulation
from republica.experiments.config import Arm, ExperimentConfig

META_NAME = "runs.meta.json"
FAILED_NAME = "failed.jsonl"
METRICS_NAME = "metrics.csv"

#: Columnas de `metrics.csv` (superset de ADR secc. 1: los 10 literales mas
#: `election_winner`/`election_turnover` "cuando esten presentes", que se
#: dejan vacias en corridas sin `features.elections`).
METRIC_COLUMNS: tuple[str, ...] = (
    "outcome",
    "inflation_annual_final",
    "gdp_growth_mean",
    "unemployment_final",
    "approval_final",
    "stability_min",
    "reserves_min",
    "authority_violations",
    "perception_gap_mean",
    "agreements_broken",
    "election_winner",
    "election_turnover",
)

#: Alias local (hallazgo #4 de REVIEW_002: constante unica en
#: `engine/permissions.py::AUTHORITY_VIOLATION_MARKER`, la misma que usan
#: `cli.py::bench_parse` y `evals/metrics.py::authority_violation`): una
#: denegacion cuya razon viene del chequeo 1 de `authorize()` ("el rol X no
#: tiene permitido Y") es especificamente una violacion de autoridad, a
#: diferencia de un cooldown/presupuesto/gobernanza.
_AUTHORITY_VIOLATION_MARKER = AUTHORITY_VIOLATION_MARKER


def _uses_llm(arm: Arm) -> bool:
    specs = [arm.brain_default, *arm.brain_map.values()]
    return any(s.startswith("llm:") for s in specs)


def extract_run_metrics(jsonl_path: Path) -> dict[str, Any]:
    """Las metricas de ADR secc. 1 para UNA corrida ya guardada en JSONL
    (reusa `engine.narrate.load_jsonl`, el mismo parser que `republica
    narrate`/`republica emergence`)."""
    loaded = narrate_mod.load_jsonl(jsonl_path)
    records = loaded.records
    if not records:
        return dict.fromkeys(METRIC_COLUMNS)
    last_state = records[-1]["state"]
    metrics: dict[str, Any] = {
        "outcome": loaded.summary.get("outcome"),
        "inflation_annual_final": narrate_mod.annualized_inflation(last_state["inflation"]),
        "gdp_growth_mean": statistics.mean(r["state"]["gdp_growth"] for r in records),
        "unemployment_final": last_state["unemployment"],
        "approval_final": last_state["government_approval"],
        "stability_min": min(r["state"]["political_stability"] for r in records),
        "reserves_min": min(r["state"]["reserves"] for r in records),
        "authority_violations": sum(
            1
            for actions in loaded.actions_by_month.values()
            for a in actions
            if not a.get("authorized", True)
            and _AUTHORITY_VIOLATION_MARKER in (a.get("denied_reason") or "")
        ),
        "perception_gap_mean": None,
        "agreements_broken": sum(
            1 for r in records for ev in r.get("events", []) if ev.startswith("agreement_broken:")
        ),
        "election_winner": None,
        "election_turnover": None,
    }
    gaps = [
        p["perception_gap"]
        for ps in loaded.perceptions_by_month.values()
        for p in ps
        if "perception_gap" in p
    ]
    if gaps:
        metrics["perception_gap_mean"] = statistics.mean(gaps)
    elections = sorted(
        (e for es in loaded.elections_by_month.values() for e in es),
        key=lambda e: e["month"],
    )
    if elections:
        last_election = elections[-1]
        metrics["election_winner"] = last_election.get("winner")
        metrics["election_turnover"] = last_election.get("outcome_type") == "defeated"
    return metrics


@dataclass(frozen=True)
class _Task:
    arm: Arm
    seed: int
    jsonl_path: Path


def _run_task(task: _Task) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        history = run_simulation(
            seed=task.seed,
            months=task.arm.months,
            country=task.arm.country,
            actors_enabled=task.arm.features["actors"],
            brain_map=task.arm.brain_map,
            default_brain=task.arm.brain_default,
            congress_enabled=task.arm.features["congress"],
            negotiation_enabled=task.arm.features["negotiation"],
            cohorts_enabled=task.arm.features["cohorts"],
            media_enabled=task.arm.features["media"],
            memory_enabled=task.arm.features["memory"],
            elections_enabled=task.arm.features["elections"],
            governance_overrides=task.arm.governance_overrides or None,
        )
    except Exception as exc:  # noqa: BLE001 - un fallo no debe frenar el lote
        return {
            "ok": False,
            "arm": task.arm.name,
            "seed": task.seed,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    task.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    task.jsonl_path.write_text(history.to_jsonl(), encoding="utf-8")
    return {
        "ok": True,
        "arm": task.arm.name,
        "seed": task.seed,
        "outcome": history.outcome,
        "elapsed": time.perf_counter() - t0,
    }


def _write_failed(out_dir: Path, results: list[dict[str, Any]], *, merge: bool) -> None:
    path = out_dir / FAILED_NAME
    existing: dict[tuple[str, int], dict[str, Any]] = {}
    if merge and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                existing[(rec["arm"], rec["seed"])] = rec
    for r in results:
        key = (r["arm"], r["seed"])
        if r["ok"]:
            existing.pop(key, None)
        else:
            existing[key] = r
    if not existing and not path.exists():
        return
    lines = [json.dumps(v, ensure_ascii=False) for v in existing.values()]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def _relative_yaml_path(source_path: Path) -> str:
    """Ruta del YAML para `runs.meta.json` (hallazgo #12 de REVIEW_003):
    RELATIVA al directorio de trabajo actual cuando es posible, no absoluta
    -- `config.source_path` (`ExperimentConfig.load`) siempre resuelve a
    absoluta, y guardarla tal cual ataba `runs.meta.json` a la ruta exacta
    de la maquina/checkout que corrio el experimento (`experiment resume`/
    `experiment status` en OTRO checkout, o el mismo repo clonado en otro
    lado, fallaba a buscar un YAML que ahi no existe). `os.path.relpath`
    puede levantar `ValueError` en Windows si terminan en unidades (drive)
    distintas -- ahi se guarda la absoluta como antes (mejor eso que
    reventar el comando)."""
    import os

    try:
        return os.path.relpath(source_path, Path.cwd())
    except ValueError:
        return str(source_path)


def _write_meta(out_dir: Path, config: ExperimentConfig, arms: list[Arm], elapsed: float) -> None:
    meta = {
        "experiment_name": config.name,
        "description": config.description,
        "experiment_yaml": _relative_yaml_path(config.source_path),
        "seeds": {"start": config.seeds.start, "count": config.seeds.count},
        "metrics": config.metrics,
        "arms": {
            a.name: {
                "overrides": a.overrides,
                "sweep_point": a.sweep_point,
                "config_hash": a.config_hash,
                "months": a.months,
            }
            for a in arms
        },
        "package_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": elapsed,
    }
    (out_dir / META_NAME).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_metrics_csv(out_dir: Path, config: ExperimentConfig, arms: list[Arm]) -> Path:
    """Recorre TODOS los JSONL ya escritos (no solo los de esta corrida --
    asi `resume`/una segunda pasada de `run` dejan `metrics.csv` completo)
    y escribe `<out>/metrics.csv`: una fila por `(arm, seed)` con las
    columnas de `METRIC_COLUMNS`. Corridas fallidas (sin JSONL) no generan
    fila."""
    rows: list[dict[str, Any]] = []
    for arm in arms:
        arm_dir = out_dir / arm.name
        if not arm_dir.exists():
            continue
        for seed in config.seeds.values:
            jsonl_path = arm_dir / f"{seed}.jsonl"
            if not jsonl_path.exists():
                continue
            row: dict[str, Any] = {"experiment": config.name, "arm": arm.name, "seed": seed}
            row.update(extract_run_metrics(jsonl_path))
            rows.append(row)

    import csv

    out_path = out_dir / METRICS_NAME
    fieldnames = ["experiment", "arm", "seed", *METRIC_COLUMNS]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return out_path


def run_experiment(
    yaml_path: str | Path,
    out_dir: str | Path,
    *,
    workers: int = 1,
    resume: bool = False,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """`republica experiment run <yaml> --workers N --out DIR` (y
    `resume_experiment`, que llama esto con `resume=True` sobre el mismo
    `out_dir`, releyendo el yaml original desde `runs.meta.json`)."""
    config = ExperimentConfig.load(yaml_path, data_dir=data_dir)
    arms = config.resolve_arms()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    tasks: list[_Task] = []
    for arm in arms:
        arm_dir = out / arm.name
        arm_dir.mkdir(parents=True, exist_ok=True)
        for seed in config.seeds.values:
            jsonl_path = arm_dir / f"{seed}.jsonl"
            if resume and jsonl_path.exists():
                continue
            tasks.append(_Task(arm=arm, seed=seed, jsonl_path=jsonl_path))

    serial_tasks = [t for t in tasks if _uses_llm(t.arm)]
    parallel_tasks = [t for t in tasks if not _uses_llm(t.arm)]

    t0 = time.perf_counter()
    results: list[dict[str, Any]] = []
    if parallel_tasks:
        if workers > 1:
            with multiprocessing.Pool(processes=workers) as pool:
                results.extend(pool.map(_run_task, parallel_tasks))
        else:
            results.extend(_run_task(t) for t in parallel_tasks)
    for t in serial_tasks:
        results.append(_run_task(t))
    elapsed = time.perf_counter() - t0

    _write_failed(out, results, merge=resume)
    _write_meta(out, config, arms, elapsed)
    metrics_path = write_metrics_csv(out, config, arms)

    n_failed = sum(1 for r in results if not r["ok"])
    return {
        "experiment": config.name,
        "out_dir": str(out),
        "arms": [a.name for a in arms],
        "n_tasks": len(tasks),
        "n_ok": len(tasks) - n_failed,
        "n_failed": n_failed,
        "elapsed_seconds": elapsed,
        "metrics_csv": str(metrics_path),
    }


def _resolve_meta_yaml_path(meta_yaml: str) -> str:
    """Resuelve `meta["experiment_yaml"]` con un fallback para archivos
    VIEJOS de `runs.meta.json` (hallazgo #12 de REVIEW_003, antes de
    `_relative_yaml_path`): si la ruta guardada (relativa a la ruta
    original, o absoluta de un checkout viejo) no existe TAL CUAL desde el
    directorio de trabajo actual, se prueba `experiments/<nombre del
    archivo>.yaml` -- todos los YAML de experimento del repo viven ahi
    (ver `experiments/*.yaml`), asi que es la ubicacion mas probable en un
    checkout distinto al que corrio el experimento originalmente. Si
    tampoco existe ahi, se devuelve la ruta original tal cual (el error de
    `ExperimentConfig.load` de mas abajo es mas claro que uno de aca)."""
    p = Path(meta_yaml)
    if p.exists():
        return meta_yaml
    fallback = Path("experiments") / p.name
    if fallback.exists():
        return str(fallback)
    return meta_yaml


def resume_experiment(
    out_dir: str | Path, *, workers: int = 1, data_dir: Path | None = None
) -> dict[str, Any]:
    """`republica experiment resume <dir>` (deliverable "resume por (arm,
    seed) faltante"): relee el yaml original desde `runs.meta.json` y
    vuelve a correr `run_experiment` con `resume=True` sobre el mismo
    directorio -- solo faltan los `(arm, seed)` sin JSONL."""
    out = Path(out_dir)
    meta_path = out / META_NAME
    if not meta_path.exists():
        raise FileNotFoundError(f"{out} no tiene {META_NAME} (¿se corrio 'experiment run' antes?)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    yaml_path = _resolve_meta_yaml_path(meta["experiment_yaml"])
    return run_experiment(yaml_path, out, workers=workers, resume=True, data_dir=data_dir)


def experiment_status(out_dir: str | Path) -> dict[str, Any]:
    """`republica experiment status <dir>`: progreso por brazo y corridas
    fallidas, leido de `runs.meta.json`/los JSONL ya escritos/`failed.jsonl`."""
    out = Path(out_dir)
    meta_path = out / META_NAME
    if not meta_path.exists():
        raise FileNotFoundError(f"{out} no tiene {META_NAME} (¿se corrio 'experiment run' antes?)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    seeds = list(range(meta["seeds"]["start"], meta["seeds"]["start"] + meta["seeds"]["count"]))
    by_arm: dict[str, dict[str, Any]] = {}
    for arm_name in meta["arms"]:
        arm_dir = out / arm_name
        have = {int(p.stem) for p in arm_dir.glob("*.jsonl")} if arm_dir.exists() else set()
        by_arm[arm_name] = {
            "done": len(have),
            "total": len(seeds),
            "missing": sorted(set(seeds) - have),
        }
    failed_path = out / FAILED_NAME
    n_failed = 0
    if failed_path.exists():
        n_failed = sum(
            1 for line in failed_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    return {
        "experiment": meta["experiment_name"],
        "seeds_per_arm": len(seeds),
        "arms": by_arm,
        "n_failed": n_failed,
    }


__all__ = [
    "METRIC_COLUMNS",
    "experiment_status",
    "extract_run_metrics",
    "resume_experiment",
    "run_experiment",
    "write_metrics_csv",
]
