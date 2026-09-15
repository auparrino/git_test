"""Orquestacion de `republica calibrate` (A3, ADR 011 secc. 7 punto 5):
parsea `--train`/`--holdout`, arma el pool de workers, corre CMA-ES,
evalua el holdout UNA VEZ al final, y escribe `calibration/<run_id>/`."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
from dataclasses import dataclass
from pathlib import Path

from republica.calibration.objective import start_months
from republica.calibration.optimizer import ParallelEvaluator, run_cma
from republica.calibration.optimizer import _worker_init as optimizer_worker_init
from republica.calibration.parameters import (
    bimonetary_from_vector,
    build_parameter_space,
    coefficients_from_vector,
    write_parameters_yaml,
)
from republica.world.bimonetary import BimonetaryCoefficients
from republica.world.config import DEFAULT_DATA_DIR, load_country

CALIBRATION_ROOT = DEFAULT_DATA_DIR / "countries" / "argentina" / "calibration"

#: Frase fija del protocolo de honestidad (PLAN_ARGENTINA.md #4), tal cual,
#: para que aparezca literal en todo reporte de A3.
HONESTY_SENTENCE = (
    "Estos resultados describen el comportamiento de República Artificial "
    "calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado."
)


def parse_range(spec: str) -> tuple[str, str]:
    """`"1993-01:2015-12"` -> `("1993-01", "2015-12")`."""
    a, b = spec.split(":")
    return a.strip(), b.strip()


def input_data_hash(country_id: str = "argentina") -> str:
    """sha256 de todos los `history/*.csv` + `politics/*.csv` del paquete,
    concatenados en orden de nombre de archivo -- "el hash de los datos de
    entrada" que pide la tarea A3 punto 5, para que el reporte pueda
    probar que corrio contra ESTOS datos."""
    pack_dir = DEFAULT_DATA_DIR / "countries" / country_id
    h = hashlib.sha256()
    files = sorted((pack_dir / "history").glob("*.csv")) + sorted(
        (pack_dir / "politics").glob("*.csv")
    )
    for f in files:
        h.update(f.name.encode("utf-8"))
        h.update(f.read_bytes())
    return h.hexdigest()


@dataclass
class CalibrationRunConfig:
    country_id: str
    run_id: str
    train_start: str
    train_end: str
    holdout_start: str
    holdout_end: str
    budget: int
    stride: int
    lambda_reg: float
    workers: int
    seed: int


def run_calibration(cfg: CalibrationRunConfig) -> Path:
    run_dir = CALIBRATION_ROOT / cfg.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    params = build_parameter_space()
    write_parameters_yaml(params, CALIBRATION_ROOT / "parameters.yaml")

    train_dates = start_months(cfg.train_start, cfg.train_end, horizon=12, stride=cfg.stride)
    holdout_dates = start_months(cfg.holdout_start, cfg.holdout_end, horizon=12, stride=cfg.stride)
    if not train_dates:
        raise ValueError(f"Ventana de train vacia: {cfg.train_start}:{cfg.train_end}")

    all_dates = sorted(set(train_dates) | set(holdout_dates))
    base_coeff = load_country().coefficients
    base_bimon = BimonetaryCoefficients()

    pool = mp.Pool(
        cfg.workers, initializer=optimizer_worker_init, initargs=(cfg.country_id, all_dates)
    )
    try:
        train_eval = ParallelEvaluator(pool, train_dates, params, cfg.workers)
        holdout_eval = ParallelEvaluator(pool, holdout_dates, params, cfg.workers)

        result = run_cma(
            train_eval,
            params,
            base_coeff,
            base_bimon,
            budget=cfg.budget,
            lambda_reg=cfg.lambda_reg,
            checkpoint_dir=run_dir,
            seed=cfg.seed,
            resume=True,
        )
        calibrated_coeff_vec = result.best_x

        def table_for(evaluator: ParallelEvaluator, dates: list[str]) -> dict:
            calibrated = evaluator.evaluate_one(
                calibrated_coeff_vec, base_coeff, base_bimon, cfg.lambda_reg
            )
            aurora_x = [p.aurora_value for p in params]
            aurora = evaluator.evaluate_one(aurora_x, base_coeff, base_bimon, cfg.lambda_reg)
            persistence = evaluator.evaluate_one(
                aurora_x, base_coeff, base_bimon, cfg.lambda_reg, persistence=True
            )
            return {
                "n_start_months": len(dates),
                "calibrated": calibrated.metrics,
                "aurora": aurora.metrics,
                "persistence": persistence.metrics,
            }

        train_tables = table_for(train_eval, train_dates)
        holdout_tables = table_for(holdout_eval, holdout_dates)
    finally:
        pool.close()
        pool.join()

    coeff = coefficients_from_vector(params, calibrated_coeff_vec, base_coeff)
    bimon = bimonetary_from_vector(params, calibrated_coeff_vec, base_bimon)

    coefficients_json = {
        "run_id": cfg.run_id,
        "country_id": cfg.country_id,
        "train": [cfg.train_start, cfg.train_end],
        "holdout": [cfg.holdout_start, cfg.holdout_end],
        "budget": cfg.budget,
        "evaluations": result.evaluations,
        "stride": cfg.stride,
        "lambda_reg": cfg.lambda_reg,
        "seed": cfg.seed,
        "wall_seconds": result.wall_seconds,
        "input_data_hash": input_data_hash(cfg.country_id),
        "coefficients": coeff.model_dump(),
        "bimonetary": {name: getattr(bimon, name) for name in bimon.__dataclass_fields__},
    }
    (run_dir / "coefficients.json").write_text(
        json.dumps(coefficients_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    import csv as _csv

    with (run_dir / "history.csv").open("w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(
            [
                "evaluations",
                "generation",
                "popsize",
                "best_scalar_this_gen",
                "mean_scalar_this_gen",
                "best_scalar_so_far",
                "wall_seconds",
            ]
        )
        for row in result.history_rows:
            w.writerow(
                [
                    row["evaluations"],
                    row["generation"],
                    row["popsize"],
                    row["best_scalar_this_gen"],
                    row["mean_scalar_this_gen"],
                    row["best_scalar_so_far"],
                    row["wall_seconds"],
                ]
            )

    from republica.calibration.report import write_report

    write_report(
        run_dir=run_dir,
        cfg=cfg,
        params=params,
        calibrated_x=calibrated_coeff_vec,
        train_tables=train_tables,
        holdout_tables=holdout_tables,
        result=result,
    )
    return run_dir


def load_calibrated_country(country_id: str, run_id: str):
    """Para `republica run --calibration <run_id>`: `(Coefficients,
    BimonetaryCoefficients)` calibrados, leidos de `coefficients.json`."""
    from republica.world.config import Coefficients

    path = CALIBRATION_ROOT / run_id / "coefficients.json"
    if not path.exists():
        raise FileNotFoundError(f"No existe la calibracion '{run_id}' en {path}.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    coeff = Coefficients(**raw["coefficients"])
    bimon = BimonetaryCoefficients(**raw["bimonetary"])
    return coeff, bimon
