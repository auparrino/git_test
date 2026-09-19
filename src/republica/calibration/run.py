"""Orquestacion de `republica calibrate` (A3, ADR 011 secc. 7 punto 5):
parsea `--train`/`--holdout`, arma el pool de workers, corre CMA-ES,
evalua el holdout UNA VEZ al final, y escribe `calibration/<run_id>/`."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
from dataclasses import dataclass
from pathlib import Path

from republica.calibration.objective import start_month_weight, start_months
from republica.calibration.optimizer import CalibrationResult, ParallelEvaluator, run_cma
from republica.calibration.optimizer import _worker_init as optimizer_worker_init
from republica.calibration.parameters import (
    bimonetary_from_vector,
    build_parameter_space,
    coefficients_from_vector,
    load_aurora_macro_coefficients,
    macro_from_vector,
    write_parameters_yaml,
)
from republica.world.bimonetary import BimonetaryCoefficients
from republica.world.config import DEFAULT_DATA_DIR, Coefficients, load_country
from republica.world.countries import (
    FX_REGIME_GROUP_MAP,
    FX_REGIME_GROUPS,
    country_pack_dir,
    fx_regime_for,
    fx_regime_group,
)
from republica.world.economy import MacroCoefficients

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
    #: A5 (ADR 012 secc. 6): `"rmse"` (default, igual que antes) o `"heavy"`
    #: (cola pesada, `calibration/objective.py::HEAVY_TAIL_POWER`) -- cual
    #: de las dos metricas por `(var, horizonte)` suma `scalar_objective`
    #: para el escalar que minimiza CMA-ES. El reporte siempre muestra
    #: AMBAS, independientemente de cual se optimizo (ver `report.py`).
    loss: str = "rmse"
    #: ADR 017 secc. 3: `True` = un CMA-ES POR GRUPO de regimen cambiario
    #: (`peg`/`float`/`control`, ver `world/countries.py::
    #: FX_REGIME_GROUP_MAP`), particionando los meses de arranque de train
    #: por el `fx_regime` real de `fx_regimes.csv` en `t0`. `False`
    #: (default) = un solo vector para toda la ventana, igual que A3/A5.
    by_regime: bool = False
    #: Presupuesto de evaluaciones POR GRUPO cuando `by_regime` (ADR 017
    #: secc. 8). `None` = usar `budget` para cada grupo. Ignorado sin
    #: `by_regime`.
    budget_per_group: int | None = None
    #: ADR 017 secc. 5: pesos por variable del objetivo para el escalar que
    #: minimiza CMA-ES. `None` (default) = todos 1.0 = el escalar de
    #: siempre, byte a byte.
    weights: dict[str, float] | None = None


def _country_raw(country_id: str) -> dict:
    from republica.world.countries import country_pack_dir

    path = country_pack_dir(country_id) / "country.json"
    return json.loads(path.read_text(encoding="utf-8"))


def group_start_months(country_id: str, dates: list[str]) -> dict[str, list[str]]:
    """ADR 017 secc. 3: parte `dates` (meses de arranque) por GRUPO de
    regimen cambiario, segun el `fx_regime` REAL de `fx_regimes.csv` en
    cada fecha (`world/countries.py::fx_regime_for` +
    `fx_regime_group`). Devuelve solo los grupos con al menos una fecha,
    en el orden fijo de `FX_REGIME_GROUPS` (determinismo del reporte y del
    `coefficients.json`)."""
    pack_dir = country_pack_dir(country_id)
    out: dict[str, list[str]] = {}
    for date in dates:
        group = fx_regime_group(fx_regime_for(pack_dir, date))
        out.setdefault(group, []).append(date)
    return {g: out[g] for g in FX_REGIME_GROUPS if g in out}


def _vector_payload(
    params,
    x: list[float],
    base_coeff: Coefficients,
    base_bimon: BimonetaryCoefficients,
    base_macro: MacroCoefficients | None,
) -> dict:
    """El bloque `{coefficients, bimonetary, macro?}` que se escribe en
    `coefficients.json` para UN vector (ADR 017 secc. 3.4: el formato viejo
    lo tiene en la raiz, el nuevo lo repite dentro de `by_regime`/
    `default`)."""
    coeff = coefficients_from_vector(params, x, base_coeff)
    bimon = bimonetary_from_vector(params, x, base_bimon)
    payload = {
        "coefficients": coeff.model_dump(),
        "bimonetary": {name: getattr(bimon, name) for name in bimon.__dataclass_fields__},
    }
    if base_macro is not None:
        macro = macro_from_vector(params, x, base_macro)
        payload["macro"] = {name: getattr(macro, name) for name in macro.__dataclass_fields__}
    return payload


def _write_history_csv(path: Path, history_rows: list[dict]) -> None:
    import csv as _csv

    with path.open("w", encoding="utf-8", newline="") as fh:
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
        for row in history_rows:
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


def run_calibration(cfg: CalibrationRunConfig) -> Path:
    run_dir = CALIBRATION_ROOT / cfg.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # A5 (ADR 012 secc. 6): el vector de calibracion incluye el grupo
    # "macro" cuando el paquete tiene `features.macro_regime` prendido
    # (Argentina, desde el ADR 012) -- mismo gate que usa `republica run`
    # (`cli.py`) para decidir si arma `macro_coefficients`, asi que un
    # `republica calibrate` normal de un pais con macro SIEMPRE calibra
    # macro (no hay una forma de pedir "sin macro" para un pais que lo
    # tiene -- `a3_main`, corrido antes del ADR 012, sigue siendo el
    # unico run "sin macro" de Argentina, y no se re-corre).
    include_macro = bool(_country_raw(cfg.country_id).get("features", {}).get("macro_regime"))
    params = build_parameter_space(include_macro=include_macro)
    write_parameters_yaml(params, CALIBRATION_ROOT / "parameters.yaml")

    train_dates = start_months(cfg.train_start, cfg.train_end, horizon=12, stride=cfg.stride)
    holdout_dates = start_months(cfg.holdout_start, cfg.holdout_end, horizon=12, stride=cfg.stride)
    if not train_dates:
        raise ValueError(f"Ventana de train vacia: {cfg.train_start}:{cfg.train_end}")

    all_dates = sorted(set(train_dates) | set(holdout_dates))
    base_coeff = load_country().coefficients
    base_bimon = BimonetaryCoefficients()
    base_macro = load_aurora_macro_coefficients() if include_macro else None

    # `a3_main` (A3, sin macro): re-evaluado en la ventana train/holdout
    # de ESTA corrida (no se reusan los numeros de su propio report.md,
    # calculados sobre OTRA ventana -- 1993-2015/2016-2023 -- para que
    # la comparacion del punto 4 de la tarea A5 sea apples-to-apples,
    # mismos meses de arranque, misma pérdida). `None` si no existe.
    a3_path = CALIBRATION_ROOT / "a3_main" / "coefficients.json"
    a3_arm: tuple[Coefficients, BimonetaryCoefficients] | None = None
    if a3_path.exists():
        a3_raw = json.loads(a3_path.read_text(encoding="utf-8"))
        a3_arm = (
            Coefficients(**a3_raw["coefficients"]),
            BimonetaryCoefficients(**a3_raw["bimonetary"]),
        )

    def make_evaluator(dates: list[str]) -> ParallelEvaluator:
        return ParallelEvaluator(
            pool,
            dates,
            params,
            cfg.workers,
            base_macro=base_macro,
            loss=cfg.loss,
            weights=cfg.weights,
        )

    def baseline_tables(evaluator: ParallelEvaluator, dates: list[str]) -> dict:
        """Las columnas que NO dependen del vector calibrado (persistencia,
        Aurora sin calibrar, `a3_main`) mas el encabezado `n`."""
        aurora_x = [p.aurora_value for p in params]
        out = {
            "n_start_months": len(dates),
            "n_weighted_pre_1997": sum(1 for d in dates if start_month_weight(d) < 1.0),
            "aurora": evaluator.evaluate_one(
                aurora_x, base_coeff, base_bimon, cfg.lambda_reg
            ).metrics,
            "persistence": evaluator.evaluate_one(
                aurora_x, base_coeff, base_bimon, cfg.lambda_reg, persistence=True
            ).metrics,
        }
        if a3_arm is not None:
            a3_coeff, a3_bimon = a3_arm
            out["a3_main"] = evaluator.evaluate_raw(a3_coeff, a3_bimon, macro=None)
        return out

    def empty_tables() -> dict:
        """Grupo sin meses de arranque en esta ventana (tipicamente el
        holdout): se imprime igual, con todo en `nan`, para que la ausencia
        sea VISIBLE en el reporte (ADR 017 secc. 4)."""
        nan_metrics: dict[str, float] = {}
        return {
            "n_start_months": 0,
            "n_weighted_pre_1997": 0,
            "calibrated": nan_metrics,
            "aurora": nan_metrics,
            "persistence": nan_metrics,
        }

    pool = mp.Pool(
        cfg.workers, initializer=optimizer_worker_init, initargs=(cfg.country_id, all_dates)
    )
    by_regime_report: dict | None = None
    try:
        if cfg.by_regime:
            groups_train = group_start_months(cfg.country_id, train_dates)
            groups_holdout = group_start_months(cfg.country_id, holdout_dates)
            budget_per_group = cfg.budget_per_group or cfg.budget
            results_by_group: dict[str, CalibrationResult] = {}
            for group, dates_g in groups_train.items():
                results_by_group[group] = run_cma(
                    make_evaluator(dates_g),
                    params,
                    base_coeff,
                    base_bimon,
                    budget=budget_per_group,
                    lambda_reg=cfg.lambda_reg,
                    checkpoint_dir=run_dir / "groups" / group,
                    seed=cfg.seed,
                    resume=True,
                )
            # ADR 017 secc. 3.3: `default` = el vector del grupo con MAS
            # meses de arranque de train (no un promedio de los tres: el
            # punto medio entre dos optimos de ramas de codigo distintas no
            # optimiza ninguna de las dos).
            default_group = max(groups_train, key=lambda g: (len(groups_train[g]), g))
            calibrated_coeff_vec = results_by_group[default_group].best_x

            train_by_group: dict[str, dict] = {}
            holdout_by_group: dict[str, dict] = {}
            for group, dates_g in groups_train.items():
                ev = make_evaluator(dates_g)
                tables = baseline_tables(ev, dates_g)
                tables["calibrated"] = ev.evaluate_one(
                    results_by_group[group].best_x, base_coeff, base_bimon, cfg.lambda_reg
                ).metrics
                train_by_group[group] = tables
                dates_h = groups_holdout.get(group, [])
                if not dates_h:
                    holdout_by_group[group] = empty_tables()
                    continue
                ev_h = make_evaluator(dates_h)
                tables_h = baseline_tables(ev_h, dates_h)
                tables_h["calibrated"] = ev_h.evaluate_one(
                    results_by_group[group].best_x, base_coeff, base_bimon, cfg.lambda_reg
                ).metrics
                holdout_by_group[group] = tables_h

            # Tablas AGREGADAS (ADR 017 secc. 4): cada mes de arranque con
            # el vector de SU grupo, todos juntos. Un mes de holdout cuyo
            # grupo no se entreno (no puede pasar hoy -- el holdout es
            # entero `crawl` -> `peg` -- pero el codigo no lo asume) usa el
            # vector `default`.
            def mixed_x(dates: list[str], groups: dict[str, list[str]]) -> dict[str, list[float]]:
                by_date: dict[str, list[float]] = {}
                for group, dates_g in groups.items():
                    res = results_by_group.get(group)
                    x = res.best_x if res is not None else calibrated_coeff_vec
                    for d in dates_g:
                        by_date[d] = x
                return {d: by_date.get(d, calibrated_coeff_vec) for d in dates}

            train_eval = make_evaluator(train_dates)
            train_tables = baseline_tables(train_eval, train_dates)
            train_tables["calibrated"] = train_eval.evaluate_mixed(
                mixed_x(train_dates, groups_train), base_coeff, base_bimon
            )
            if holdout_dates:
                holdout_eval = make_evaluator(holdout_dates)
                holdout_tables = baseline_tables(holdout_eval, holdout_dates)
                holdout_tables["calibrated"] = holdout_eval.evaluate_mixed(
                    mixed_x(holdout_dates, groups_holdout), base_coeff, base_bimon
                )
            else:
                holdout_tables = empty_tables()

            by_regime_report = {
                "groups": list(groups_train),
                "default_group": default_group,
                "n_by_group_train": {g: len(d) for g, d in groups_train.items()},
                "n_by_group_holdout": {g: len(groups_holdout.get(g, [])) for g in groups_train},
                "train": train_by_group,
                "holdout": holdout_by_group,
                "x_by_group": {g: r.best_x for g, r in results_by_group.items()},
                "budget_per_group": budget_per_group,
            }
            result = CalibrationResult(
                best_x=calibrated_coeff_vec,
                best_scalar=results_by_group[default_group].best_scalar,
                evaluations=sum(r.evaluations for r in results_by_group.values()),
                # El grafico de convergencia y la `history.csv` de la raiz
                # son las del grupo `default`; cada grupo tiene ademas su
                # propia `history_<grupo>.csv` (mezclar las tres en una sola
                # serie daria una curva sin sentido: son optimizaciones
                # independientes con escalares no comparables).
                history_rows=results_by_group[default_group].history_rows,
                wall_seconds=sum(r.wall_seconds for r in results_by_group.values()),
            )
        else:
            train_eval = make_evaluator(train_dates)
            holdout_eval = make_evaluator(holdout_dates)
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
            train_tables = baseline_tables(train_eval, train_dates)
            train_tables["calibrated"] = train_eval.evaluate_one(
                calibrated_coeff_vec, base_coeff, base_bimon, cfg.lambda_reg
            ).metrics
            holdout_tables = baseline_tables(holdout_eval, holdout_dates)
            holdout_tables["calibrated"] = holdout_eval.evaluate_one(
                calibrated_coeff_vec, base_coeff, base_bimon, cfg.lambda_reg
            ).metrics
    finally:
        pool.close()
        pool.join()

    coefficients_json = {
        "run_id": cfg.run_id,
        "country_id": cfg.country_id,
        "train": [cfg.train_start, cfg.train_end],
        "holdout": [cfg.holdout_start, cfg.holdout_end],
        "budget": cfg.budget,
        "evaluations": result.evaluations,
        "stride": cfg.stride,
        "lambda_reg": cfg.lambda_reg,
        "loss": cfg.loss,
        "weights": cfg.weights,
        "seed": cfg.seed,
        "wall_seconds": result.wall_seconds,
        "input_data_hash": input_data_hash(cfg.country_id),
    }
    if by_regime_report is not None:
        # ADR 017 secc. 3.4: formato NUEVO. `load_calibrated_country` elige
        # por la clave `"by_regime"`; el formato viejo (un solo vector en la
        # raiz) se sigue leyendo tal cual.
        coefficients_json.update(
            {
                "by_regime_groups": by_regime_report["groups"],
                "default_group": by_regime_report["default_group"],
                "regime_group_map": dict(FX_REGIME_GROUP_MAP),
                "n_start_months_by_group": by_regime_report["n_by_group_train"],
                "budget_per_group": by_regime_report["budget_per_group"],
                "by_regime": {
                    g: _vector_payload(params, x, base_coeff, base_bimon, base_macro)
                    for g, x in by_regime_report["x_by_group"].items()
                },
                "default": _vector_payload(
                    params, calibrated_coeff_vec, base_coeff, base_bimon, base_macro
                ),
            }
        )
    else:
        coefficients_json.update(
            _vector_payload(params, calibrated_coeff_vec, base_coeff, base_bimon, base_macro)
        )
    (run_dir / "coefficients.json").write_text(
        json.dumps(coefficients_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    _write_history_csv(run_dir / "history.csv", result.history_rows)
    if by_regime_report is not None:
        for group in by_regime_report["groups"]:
            rows = json.loads(
                (run_dir / "groups" / group / "checkpoint.json").read_text(encoding="utf-8")
            )["history_rows"]
            _write_history_csv(run_dir / f"history_{group}.csv", rows)

    from republica.calibration.report import write_report

    write_report(
        run_dir=run_dir,
        cfg=cfg,
        params=params,
        calibrated_x=calibrated_coeff_vec,
        train_tables=train_tables,
        holdout_tables=holdout_tables,
        result=result,
        by_regime=by_regime_report,
    )
    return run_dir


def _payload_to_arm(
    payload: dict,
) -> tuple[Coefficients, BimonetaryCoefficients, MacroCoefficients | None]:
    """Un bloque `{coefficients, bimonetary, macro?}` de `coefficients.json`
    (la raiz en el formato viejo, una entrada de `by_regime`/`default` en el
    nuevo) -> los objetos que consume el motor."""
    coeff = Coefficients(**payload["coefficients"])
    bimon = BimonetaryCoefficients(**payload.get("bimonetary", {}))
    macro = MacroCoefficients(**payload["macro"]) if payload.get("macro") else None
    return coeff, bimon, macro


def load_calibration_json(run_id: str) -> dict:
    path = CALIBRATION_ROOT / run_id / "coefficients.json"
    if not path.exists():
        raise FileNotFoundError(f"No existe la calibracion '{run_id}' en {path}.")
    return json.loads(path.read_text(encoding="utf-8"))


def calibration_vector_for(country_id: str, raw: dict, start: str | None) -> tuple[dict, str]:
    """ADR 017 secc. 3.5: elige el bloque `{coefficients, bimonetary,
    macro?}` que corresponde a `start` y devuelve `(payload, motivo)`, donde
    `motivo` es una frase corta para loguear.

    - `coefficients.json` VIEJO (un solo vector en la raiz): ese, siempre
      (`start` se ignora) -- compatibilidad con `a3_main`/`a5_macro`/
      `a5b_macro`.
    - NUEVO (`by_regime`) con `start`: `fx_regime_for(start)` ->
      `fx_regime_group(...)` -> ese vector; si el grupo no esta en el
      archivo, `default`.
    - NUEVO sin `start`: `default`."""
    if "by_regime" not in raw:
        return raw, "vector unico (formato pre-ADR 017)"
    by_regime = raw["by_regime"]
    default_group = raw.get("default_group", "")
    if start is None:
        return raw["default"], f"default (sin --start; grupo '{default_group}')"
    fx_regime = fx_regime_for(country_pack_dir(country_id), start)
    group = fx_regime_group(fx_regime)
    if group in by_regime:
        return by_regime[group], f"grupo '{group}' (fx_regime '{fx_regime}' en {start})"
    return raw["default"], (
        f"default (grupo '{group}', fx_regime '{fx_regime}' en {start}, sin vector propio; "
        f"grupo default '{default_group}')"
    )


def load_calibrated_country(
    country_id: str, run_id: str, start: str | None = None
) -> tuple[Coefficients, BimonetaryCoefficients, MacroCoefficients | None]:
    """Para `republica run --calibration <run_id>`/`republica validate
    --calibration <run_id>`/`backtest/runner.py`: `(Coefficients,
    BimonetaryCoefficients, MacroCoefficients | None)` calibrados, leidos de
    `coefficients.json`. El tercer elemento es `None` para una calibracion
    SIN macro (`a3_main`, corrida antes del ADR 012: `coefficients.json` no
    tiene clave `"macro"`) -- A5, ADR 012 secc. 6.

    `start` (`"YYYY-MM"`, ADR 017 secc. 3.5): fecha de arranque de la
    corrida, usada SOLO por el formato nuevo (`--by-regime`) para elegir el
    vector del grupo de regimen cambiario correspondiente. Sin `start` (o
    con un `coefficients.json` viejo) el comportamiento es exactamente el
    de antes."""
    raw = load_calibration_json(run_id)
    payload, _why = calibration_vector_for(country_id, raw, start)
    return _payload_to_arm(payload)


def load_calibrated_vectors_by_group(
    run_id: str,
) -> dict[str, tuple[Coefficients, MacroCoefficients | None]] | None:
    """Todos los vectores de una calibracion `--by-regime`, por grupo (ADR
    017 secc. 3.6): lo que `engine/simulation.py::run(
    coefficients_by_fx_regime=...)` necesita para cambiar de vector en
    caliente cuando el regimen SIMULADO cambia (`fx_regime_exit`). `None`
    para un `coefficients.json` del formato viejo (un solo vector: no hay
    nada que intercambiar).

    Devuelve `(Coefficients, MacroCoefficients | None)` y NO el
    `BimonetaryCoefficients` del grupo: con macro activo (el unico caso en
    que esto tiene sentido) `engine/simulation.py::run` desactiva el canal
    bimonetario viejo, asi que intercambiarlo a mitad de corrida no
    cambiaria nada -- y `bimonetary_coefficients` ademas lleva
    `fx_regime_default`, estado inicial de la corrida, que NO se debe
    pisar a mitad de camino."""
    raw = load_calibration_json(run_id)
    if "by_regime" not in raw:
        return None
    out = {}
    for group, payload in raw["by_regime"].items():
        coeff, _bimon, macro = _payload_to_arm(payload)
        out[group] = (coeff, macro)
    return out
