"""Orquestacion de corridas del hito 1 (ADR 010 secc. 7): `simulate` corre
UNA semilla y devuelve el JSON completo (config + metricas por turno +
clasificacion final); `run_batch` corre N semillas en paralelo (mismo patron
que `experiments/runner.py`, ADR 008 secc. 2) variando solo la semilla salvo
que se pasen `overrides`; `classify_directory` arma `report.md` (ver
`republica.core.classify.build_report`).

CLI: `republica core run|batch|classify` (wired en `republica.cli`, import
perezoso para que la CLI base siga sin depender de `numpy`)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from republica.core.world import GOOD_NAMES, CoreConfig


def simulate(config: CoreConfig, *, seed: int | None = None) -> dict[str, Any]:
    """Corre una semilla completa: `config.turns` turnos sobre
    `config.n_agents` agentes. Devuelve un dict JSON-serializable con la
    config resuelta, la semilla, la serie de metricas por turno y la
    clasificacion final (ADR secc. 7 "por corrida: per-turn metrics + final
    classification")."""
    import numpy as np

    from republica.core import classify, exchange
    from republica.core.world import init_world

    actual_seed = config.seed if seed is None else seed
    cfg = config if seed is None else config.model_copy(update={"seed": seed})
    world = init_world(cfg, actual_seed)
    rng = np.random.default_rng(actual_seed)

    metrics: list[dict[str, Any]] = []
    for turn in range(cfg.turns):
        turn_metrics = exchange.step(world, cfg, rng, turn)
        metrics.append(turn_metrics.to_dict())

    good_names = tuple(g.name for g in cfg.goods)
    classification = classify.classify_run(metrics, good_names)

    return {
        "seed": actual_seed,
        "config": cfg.model_dump(mode="json"),
        "metrics": metrics,
        "classification": classification,
    }


def _parse_override_value(raw: str) -> Any:
    return yaml.safe_load(raw)


def parse_config_overrides(pairs: list[str]) -> dict[str, Any]:
    """`--config clave=valor` repetido (ADR 008 secc. 1 style, pero plano:
    `CoreConfig` no tiene la profundidad de `Country`, asi que el "dot-path"
    del hito 1 es un solo segmento = un campo de nivel superior de
    `CoreConfig`, p.ej. `transport_cost=0.15` o `shell_abundance=0.3`)."""
    overrides: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"override invalido (se espera clave=valor): {pair!r}")
        key, _, value = pair.partition("=")
        overrides[key.strip()] = _parse_override_value(value.strip())
    return overrides


def apply_overrides(config: CoreConfig, overrides: dict[str, Any]) -> CoreConfig:
    return config.model_copy(update=overrides)


def _run_one(args: tuple[CoreConfig, int, Path]) -> tuple[int, str | None]:
    config, seed, out_path = args
    try:
        result = simulate(config, seed=seed)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result), encoding="utf-8")
        return seed, None
    except Exception as exc:  # pragma: no cover - solo camino de error en paralelo
        return seed, f"{type(exc).__name__}: {exc}"


def run_batch(
    config: CoreConfig,
    seeds: list[int],
    out_dir: Path,
    *,
    workers: int = 1,
) -> dict[str, Any]:
    """Corre `seeds` (todas con la MISMA config salvo la semilla) y escribe
    `<out_dir>/run_<seed>.json` por cada una. `workers > 1` usa
    `multiprocessing.Pool` (mismo patron que `experiments/runner.py`)."""
    import multiprocessing

    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = [(config, seed, out_dir / f"run_{seed}.json") for seed in seeds]

    start = time.monotonic()
    failed: list[dict[str, str]] = []
    if workers > 1 and len(tasks) > 1:
        with multiprocessing.Pool(processes=workers) as pool:
            results = pool.map(_run_one, tasks)
    else:
        results = [_run_one(t) for t in tasks]
    for seed, error in results:
        if error is not None:
            failed.append({"seed": seed, "error": error})
    elapsed = time.monotonic() - start

    return {
        "n_seeds": len(seeds),
        "n_ok": len(seeds) - len(failed),
        "n_failed": len(failed),
        "failed": failed,
        "elapsed_seconds": elapsed,
        "out_dir": str(out_dir),
    }


def classify_directory(
    main_dir: Path,
    *,
    shell_sweep_dir: Path | None = None,
    transport_sweep_dir: Path | None = None,
    out_path: Path | None = None,
) -> str:
    from republica.core import classify

    report_path = out_path or (main_dir / "report.md")
    return classify.build_report(
        main_dir,
        shell_sweep_dir=shell_sweep_dir,
        transport_sweep_dir=transport_sweep_dir,
        out_path=report_path,
    )


__all__ = [
    "GOOD_NAMES",
    "simulate",
    "run_batch",
    "classify_directory",
    "parse_config_overrides",
    "apply_overrides",
]
