"""CMA-ES sobre `calibration/objective.py` (A3, ADR 011 secc. 7 punto 4).

`cma` optimiza en el CUBO `[0, 1]^n` (`Parameter.to_unit`/`from_unit`):
todos los parametros en la misma escala evita que el tamaño de paso de
CMA-ES quede dominado por el coeficiente de rango mas ancho. Paralelo por
`(candidato, mes de arranque)`: cada tarea de un `multiprocessing.Pool` es
UN mes de arranque de UN candidato de la poblacion (no una poblacion
entera ni un candidato entero) -- con una poblacion de ~18 (CMA-ES default,
`4 + 3*ln(107)`) y ~90 meses de arranque (stride 3, ventana 1993-2015) eso
son ~1600 tareas por generacion, repartidas entre los workers sin importar
si `popsize < workers` (paralelismo por mes, tal como pide la tarea, no
solo por candidato).

Checkpoints cada 20 evaluaciones (`checkpoint.pkl`, `pickle` del objeto
`cma.CMAEvolutionStrategy` -- la libreria lo soporta tal cual -- mas un
`checkpoint.json` con metadata legible): `resume=True` retoma desde ahi en
vez de reiniciar `es` desde cero."""

from __future__ import annotations

import json
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

from republica.calibration.objective import (
    MonthScore,
    RealData,
    StartMonthContext,
    aggregate_scores,
    build_context,
    scalar_objective,
    score_start_month,
)
from republica.calibration.parameters import (
    Parameter,
    bimonetary_from_vector,
    coefficients_from_vector,
    macro_from_vector,
)
from republica.world.bimonetary import BimonetaryCoefficients
from republica.world.config import Coefficients
from republica.world.economy import MacroCoefficients

#: Estado global de un worker de `multiprocessing.Pool` (poblado UNA vez
#: por proceso via `_worker_init`, reusado en cada tarea -- evita reconstruir
#: `StartMonthContext`/`RealData` en cada llamada, que es lo caro de
#: `load_country_pack`/lectura de `history/`).
_WORKER: dict = {}


def _worker_init(country_id: str, dates: list[str]) -> None:
    _WORKER["contexts"] = {d: build_context(country_id, d) for d in dates}
    _WORKER["real"] = RealData.load()


def _worker_score(
    task: tuple[
        str,
        list[float],
        list[Parameter],
        Coefficients,
        BimonetaryCoefficients,
        MacroCoefficients | None,
        bool,
        int,
    ],
) -> tuple[str, MonthScore]:
    date, x, params, base_coeff, base_bimon, base_macro, persistence, seed = task
    ctx: StartMonthContext = _WORKER["contexts"][date]
    real: RealData = _WORKER["real"]
    coeff = coefficients_from_vector(params, x, base_coeff)
    bimon = bimonetary_from_vector(params, x, base_bimon)
    macro = macro_from_vector(params, x, base_macro) if base_macro is not None else None
    score = score_start_month(
        ctx, real, coeff, bimon, persistence=persistence, seed=seed, macro=macro
    )
    return date, score


def _worker_score_raw(
    task: tuple[str, Coefficients, BimonetaryCoefficients, MacroCoefficients | None, bool, int],
) -> tuple[str, MonthScore]:
    """Version de `_worker_score` que NO reconstruye `coeff`/`bimon`/`macro`
    desde un vector `x` sino que los toma tal cual (A5, ADR 012 secc. 6):
    usada por `ParallelEvaluator.evaluate_raw` para re-evaluar coeficientes
    FIJOS que no viven en el espacio de parametros de la corrida actual
    (p.ej. `a3_main`, calibrado sin macro, comparado contra la ventana
    train/holdout de una corrida macro -- ver `calibration/run.py`)."""
    date, coeff, bimon, macro, persistence, seed = task
    ctx: StartMonthContext = _WORKER["contexts"][date]
    real: RealData = _WORKER["real"]
    score = score_start_month(
        ctx, real, coeff, bimon, persistence=persistence, seed=seed, macro=macro
    )
    return date, score


@dataclass
class EvalResult:
    x: list[float]
    scalar: float
    metrics: dict[str, float]


class ParallelEvaluator:
    """Envuelve un `multiprocessing.Pool` ya abierto (workers con contexto
    cacheado, `_worker_init`) para evaluar candidatos -- un `x` a la vez
    (`evaluate_one`, usado por baselines/reportes) o una poblacion entera
    de una (`evaluate_population`, usado por el loop de CMA-ES: reparte
    TODAS las tareas `(candidato, mes)` de la generacion en una sola
    llamada a `pool.map`)."""

    def __init__(
        self,
        pool,
        dates: list[str],
        params: list[Parameter],
        workers: int,
        base_macro: MacroCoefficients | None = None,
        loss: str = "rmse",
        weights: dict[str, float] | None = None,
    ):
        self.pool = pool
        self.dates = dates
        self.params = params
        self.workers = workers
        #: A5 (ADR 012 secc. 6): `None` (default, compatibilidad con A3) ->
        #: `params` sin grupo `"macro"`, cada tarea corre con
        #: `macro_coefficients=None` (bimonetario viejo, igual que siempre).
        #: Distinto de `None` -> cada tarea calcula `macro_from_vector` y
        #: corre con `step_macro_economy` (ver `_worker_score`).
        self.base_macro = base_macro
        self.loss = loss
        #: ADR 017 secc. 5: pesos por variable del objetivo (`None` =
        #: todos 1.0 = el escalar de siempre). Solo afectan el escalar que
        #: minimiza CMA-ES, no las metricas del reporte.
        self.weights = weights

    def evaluate_population(
        self,
        xs: list[list[float]],
        base_coeff: Coefficients,
        base_bimon: BimonetaryCoefficients,
        lambda_reg: float,
        seed: int = 0,
    ) -> list[EvalResult]:
        tasks = [
            (date, x, self.params, base_coeff, base_bimon, self.base_macro, False, seed)
            for x in xs
            for date in self.dates
        ]
        chunk = max(1, len(tasks) // (self.workers * 4)) if self.workers else None
        raw = (
            self.pool.map(_worker_score, tasks, chunksize=chunk)
            if self.pool is not None
            else [_worker_score(t) for t in tasks]
        )
        per_candidate: list[list[MonthScore]] = [[] for _ in xs]
        idx = 0
        for i in range(len(xs)):
            for _date in self.dates:
                per_candidate[i].append(raw[idx][1])
                idx += 1
        real = RealData.load()
        out = []
        for i, x in enumerate(xs):
            metrics = aggregate_scores(per_candidate[i], real)
            scalar = scalar_objective(
                metrics, self.params, x, lambda_reg, loss=self.loss, weights=self.weights
            )
            out.append(EvalResult(x=x, scalar=scalar, metrics=metrics))
        return out

    def evaluate_one(
        self,
        x: list[float],
        base_coeff: Coefficients,
        base_bimon: BimonetaryCoefficients,
        lambda_reg: float,
        persistence: bool = False,
        seed: int = 0,
    ) -> EvalResult:
        tasks = [
            (date, x, self.params, base_coeff, base_bimon, self.base_macro, persistence, seed)
            for date in self.dates
        ]
        raw = (
            self.pool.map(_worker_score, tasks)
            if self.pool is not None
            else [_worker_score(t) for t in tasks]
        )
        scores = [r[1] for r in raw]
        real = RealData.load()
        metrics = aggregate_scores(scores, real)
        scalar = (
            float("nan")
            if persistence
            else scalar_objective(
                metrics, self.params, x, lambda_reg, loss=self.loss, weights=self.weights
            )
        )
        return EvalResult(x=x, scalar=scalar, metrics=metrics)

    def evaluate_mixed(
        self,
        x_by_date: dict[str, list[float]],
        base_coeff: Coefficients,
        base_bimon: BimonetaryCoefficients,
        seed: int = 0,
    ) -> dict[str, float]:
        """ADR 017 secc. 4 (tabla AGREGADA de una corrida `--by-regime`):
        cada mes de arranque se puntua con el vector de SU grupo
        (`x_by_date`) y todos los `MonthScore` se agregan juntos, como si
        fueran de un unico brazo. Devuelve solo las metricas: no hay un
        escalar unico que tenga sentido (la regularizacion L2 es por vector
        y acá hay tres), igual que en `evaluate_raw`.

        Las fechas que no esten en `x_by_date` se saltean (no deberia pasar:
        `calibration/run.py` arma el dict con las MISMAS fechas)."""
        tasks = [
            (
                date,
                x_by_date[date],
                self.params,
                base_coeff,
                base_bimon,
                self.base_macro,
                False,
                seed,
            )
            for date in self.dates
            if date in x_by_date
        ]
        raw = (
            self.pool.map(_worker_score, tasks)
            if self.pool is not None
            else [_worker_score(t) for t in tasks]
        )
        scores = [r[1] for r in raw]
        real = RealData.load()
        return aggregate_scores(scores, real)

    def evaluate_raw(
        self,
        coeff: Coefficients,
        bimon: BimonetaryCoefficients,
        macro: MacroCoefficients | None,
        persistence: bool = False,
        seed: int = 0,
    ) -> dict[str, float]:
        """Evalua coeficientes FIJOS (`Coefficients`/`BimonetaryCoefficients`/
        `MacroCoefficients` concretos, no un vector `x` de este espacio de
        parametros) sobre `self.dates` -- A5 (ADR 012 secc. 6): usado para
        comparar `a3_main` (calibrado SIN macro, en otro run de CMA-ES) en
        la ventana train/holdout de la corrida actual, sin escalar (no hay
        `x`/`params` de referencia contra los que regularizar -- solo las
        metricas, no el escalar de CMA-ES, ver `calibration/run.py`)."""
        tasks = [(date, coeff, bimon, macro, persistence, seed) for date in self.dates]
        raw = (
            self.pool.map(_worker_score_raw, tasks)
            if self.pool is not None
            else [_worker_score_raw(t) for t in tasks]
        )
        scores = [r[1] for r in raw]
        real = RealData.load()
        return aggregate_scores(scores, real)


@dataclass
class CalibrationResult:
    best_x: list[float]
    best_scalar: float
    evaluations: int
    history_rows: list[dict]
    wall_seconds: float


def run_cma(
    evaluator: ParallelEvaluator,
    params: list[Parameter],
    base_coeff: Coefficients,
    base_bimon: BimonetaryCoefficients,
    budget: int,
    lambda_reg: float,
    checkpoint_dir: Path,
    seed: int = 42,
    resume: bool = True,
    sigma0: float = 0.2,
) -> CalibrationResult:
    """`budget` = cantidad de EVALUACIONES DE CANDIDATO, PISO (no techo, ver
    el comentario dentro del loop): CMA-ES pide una poblacion (`popsize`,
    default `4 + floor(3*ln(n))`) por generacion, asi que corre
    `ceil(budget / popsize)` generaciones COMPLETAS -- `evaluations` final
    puede superar `budget` en hasta `popsize - 1`."""
    import cma

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    ckpt_pkl = checkpoint_dir / "checkpoint.pkl"
    ckpt_json = checkpoint_dir / "checkpoint.json"
    history_rows: list[dict] = []
    t0 = time.time()
    evaluations = 0

    x0 = [p.to_unit(p.aurora_value) for p in params]
    if resume and ckpt_pkl.exists():
        with ckpt_pkl.open("rb") as fh:
            es = pickle.load(fh)
        meta = json.loads(ckpt_json.read_text(encoding="utf-8"))
        evaluations = meta["evaluations"]
        history_rows = meta["history_rows"]
    else:
        es = cma.CMAEvolutionStrategy(
            x0, sigma0, {"bounds": [0.0, 1.0], "seed": seed, "verbose": -9}
        )

    while evaluations < budget and not es.stop():
        # CMA-ES necesita al menos `mu` (~popsize/2) soluciones por
        # generacion para actualizar su distribucion (`tell` tira
        # ValueError con menos) -- asi que la ULTIMA generacion se evalua
        # COMPLETA aunque eso pase el `budget` en hasta `popsize - 1`
        # evaluaciones, en vez de truncarla (lo que rompia con budgets no
        # multiplos de `popsize`, como el `--quick` de 40 con `popsize=18`:
        # 18, 36, y una tercera generacion truncada a 4 < mu=9).
        popsize = es.popsize
        xs_unit = es.ask()
        xs_native = [[p.from_unit(u) for p, u in zip(params, x, strict=True)] for x in xs_unit]
        results = evaluator.evaluate_population(
            xs_native, base_coeff, base_bimon, lambda_reg, seed=0
        )
        fitnesses = [float(r.scalar) for r in results]
        es.tell(xs_unit[: len(fitnesses)], fitnesses)
        evaluations += len(fitnesses)
        best_idx = min(range(len(fitnesses)), key=lambda i: fitnesses[i])
        history_rows.append(
            {
                "evaluations": evaluations,
                "generation": len(history_rows) + 1,
                "popsize": popsize,
                "best_scalar_this_gen": fitnesses[best_idx],
                "mean_scalar_this_gen": sum(fitnesses) / len(fitnesses),
                "best_scalar_so_far": min(
                    [row["best_scalar_so_far"] for row in history_rows] + [fitnesses[best_idx]]
                ),
                "wall_seconds": time.time() - t0,
            }
        )
        if evaluations % 20 < popsize:
            with ckpt_pkl.open("wb") as fh:
                pickle.dump(es, fh)
            ckpt_json.write_text(
                json.dumps({"evaluations": evaluations, "history_rows": history_rows}, indent=2),
                encoding="utf-8",
            )

    with ckpt_pkl.open("wb") as fh:
        pickle.dump(es, fh)
    ckpt_json.write_text(
        json.dumps({"evaluations": evaluations, "history_rows": history_rows}, indent=2),
        encoding="utf-8",
    )

    best_x_unit = es.result.xbest if es.result.xbest is not None else es.best.x
    best_x_native = [float(p.from_unit(u)) for p, u in zip(params, best_x_unit, strict=True)]
    best_scalar = float(es.result.fbest if es.result.fbest is not None else es.best.f)
    return CalibrationResult(
        best_x=best_x_native,
        best_scalar=best_scalar,
        evaluations=evaluations,
        history_rows=history_rows,
        wall_seconds=time.time() - t0,
    )
