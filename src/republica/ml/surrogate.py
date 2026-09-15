"""Modelo sustituto (ADR 009 secc. 3): un pipeline sklearn por rol que
predice `position`/`intensity`/el multilabel de tipos de accion, mas
`SurrogateActor.decide(perception, rng) -> list[Action]`, la misma interfaz
que `RuleBasedActor`/`LLMActor` (ADR 003 secc. 6/ADR 004 secc. 1).

`scikit-learn`/`joblib` (extra `[ml]`) se importan de forma perezosa, DENTRO
de cada funcion que los necesita: `import republica.ml.surrogate` sin el
extra instalado no falla; recien falla `train_surrogate`/`SurrogateActor`
con un mensaje en castellano (ver `_sklearn`/`_joblib` abajo).

Alcance de los 9 roles (deliverable 2, "un pipeline por rol (9 modelos)"):
`president` nunca decide via `decision_actors` (ADR 003 secc. 7: el
presidente es una regla/humano aparte, `engine/scheduler.py::
build_actor_engine` lo excluye explicitamente) -- no hay filas de
entrenamiento para ese rol, asi que no hay pipeline de `president`.
`media`/`central_bank` (ADR 003 secc. 6.3/6.4) deciden con una formula
CERRADA sin ruido (umbrales de aprobacion/inflacion/PIB, regla de Taylor):
entrenar un clasificador para aproximar una funcion ya determinista y barata
de evaluar no aporta fidelidad (el techo de agreement es 1.0 de cualquier
forma) y complica el pipeline sin necesidad -- se entrenan sus 3 modelos
igual (para que el manifest reporte metricas de los 9 roles, deliverable
completo), pero `SurrogateActor.decide()` los ignora y delega esos 2 roles a
un `RuleBasedActor` interno (agreement exacto = 1.0, documentado como
decision de diseno, no un recorte oportunista). Los 6 roles restantes
(`economy_minister`, `governor`, `party`, `union`, `business`,
`social_bloc`) SI usan las predicciones de ML: `SurrogateActor` arma la
`Action` de la misma forma determinista que `RuleBasedActor._decide_generic`
(ADR 003 secc. 6) a partir de `position`/`intensity` PREDICHOS en vez de
`score.total` computado -- esto reproduce mejor `rules` que usar el
multilabel para elegir acciones (que es lo que mide el DoD: "agreement rate
... contra rules", accion a accion sobre `position`); el multilabel SI se
entrena y se reporta (Jaccard) porque es un deliverable explicito del ADR,
pero no gobierna la construccion de acciones."""

from __future__ import annotations

import json
import platform
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from republica import __version__
from republica.actors.rule_based import (
    _NEGOTIATE_CONCESSION as NEGOTIATE_CONCESSION,
)
from republica.actors.rule_based import (
    ACTION_BUDGET_PER_TURN,
    NEGOTIATE_CAPABLE_ROLES,
    STATEMENT_MIN_INTENSITY,
    RuleBasedActor,
    _escalate,
)
from republica.actors.sheet import ActorSheet, load_actors
from republica.engine.actions import Action, ActionType, ConcessionType
from republica.ml import dataset as ml_dataset
from republica.world.config import Country, load_country

_MISSING_SKLEARN_MSG = (
    "scikit-learn no esta instalado en este entorno. Instalar el extra "
    "opcional `ml` con `uv sync --group dev --extra ml` (o `pip install "
    "'republica-artificial[ml]'`) para usar `republica ml train|evaluate|"
    "retrain` o el brain `surrogate:<path>`."
)

#: Roles cuya decision SI usa el modelo de ML (ver docstring del modulo).
ML_ROLES: tuple[str, ...] = (
    "economy_minister",
    "governor",
    "party",
    "union",
    "business",
    "social_bloc",
)
#: Roles con formula cerrada (ADR 003 secc. 6.3/6.4): `SurrogateActor` los
#: delega a un `RuleBasedActor` interno.
RULE_PASSTHROUGH_ROLES: tuple[str, ...] = ("media", "central_bank")

MANIFEST_NAME = "manifest.json"


def _sklearn():
    try:
        import sklearn  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depende de que falte el extra
        raise RuntimeError(_MISSING_SKLEARN_MSG) from exc
    return sklearn


def _joblib():
    try:
        import joblib  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(_MISSING_SKLEARN_MSG) from exc
    return joblib


def _split_seeds(seeds: list[int]) -> tuple[list[int], list[int], list[int]]:
    """70/15/15 por semilla (ADR 009 secc. 3, deliverable 2), secuencial (no
    mezclado) sobre las semillas ORDENADAS -- reproducible sin depender de
    una semilla propia de split. Con pocas semillas (tests), cada tramo
    minimo es 1 si hay al menos 3 semillas."""
    seeds = sorted(set(seeds))
    n = len(seeds)
    if n <= 2:
        return seeds, seeds, seeds
    n_train = max(1, round(n * 0.7))
    n_val = max(1, round(n * 0.15))
    n_train = min(n_train, n - 2)
    n_val = min(n_val, n - n_train - 1)
    train = seeds[:n_train]
    val = seeds[n_train : n_train + n_val]
    test = seeds[n_train + n_val :]
    return train, val, test


def _vectorize(rows: list[dict[str, Any]], columns: list[str]):
    import numpy as np  # noqa: PLC0415

    return np.array([[float(r.get(c, float("nan"))) for c in columns] for r in rows], dtype=float)


@dataclass
class RoleMetrics:
    n_train: int
    n_val: int
    n_test: int
    position_accuracy_val: float
    position_f1_macro_val: float
    intensity_mae_val: float
    multilabel_jaccard_val: float
    position_accuracy_test: float
    position_f1_macro_test: float
    intensity_mae_test: float
    multilabel_jaccard_test: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n_train": self.n_train,
            "n_val": self.n_val,
            "n_test": self.n_test,
            "position_accuracy_val": self.position_accuracy_val,
            "position_f1_macro_val": self.position_f1_macro_val,
            "intensity_mae_val": self.intensity_mae_val,
            "multilabel_jaccard_val": self.multilabel_jaccard_val,
            "position_accuracy_test": self.position_accuracy_test,
            "position_f1_macro_test": self.position_f1_macro_test,
            "intensity_mae_test": self.intensity_mae_test,
            "multilabel_jaccard_test": self.multilabel_jaccard_test,
        }


def _fit_role(
    role: str,
    train_rows: list[dict[str, Any]],
    val_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    feature_cols: list[str],
    *,
    random_state: int,
) -> tuple[dict[str, Any], RoleMetrics]:
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.metrics import accuracy_score, f1_score, jaccard_score, mean_absolute_error
    from sklearn.multiclass import OneVsRestClassifier

    x_train = _vectorize(train_rows, feature_cols)

    # OOD (ADR 009 secc. 4): distancia de Mahalanobis DIAGONAL sobre las
    # features numericas de train -- media/varianza por columna, ignorando
    # NaN (`nanmean`/`nanvar`); una columna sin varianza (constante, o
    # enteramente NaN para este rol -- las `pi_*` de OTRO rol, siempre NaN
    # dentro del subconjunto de un rol) se excluye de la distancia (no
    # aporta senal, y dividir por varianza ~0 dispara la distancia sin
    # sentido). El umbral es el percentil 99 de la distancia EN TRAIN.
    all_nan_cols = np.all(np.isnan(x_train), axis=0)
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        col_mean = np.nan_to_num(np.nanmean(x_train, axis=0), nan=0.0)
        col_var = np.nan_to_num(np.nanvar(x_train, axis=0), nan=0.0)
    valid_dims = [i for i in range(x_train.shape[1]) if not all_nan_cols[i] and col_var[i] > 1e-9]
    train_distances = [_mahalanobis(row, col_mean, col_var, valid_dims) for row in x_train]
    ood_threshold = float(np.percentile(train_distances, 99)) if train_distances else 0.0
    ood_info = {
        "mean": col_mean.tolist(),
        "var": col_var.tolist(),
        "valid_dims": valid_dims,
        "threshold": ood_threshold,
    }

    # Columnas sin varianza (constantes o enteramente NaN dentro de este
    # rol) se DESCARTAN de la matriz que ve el clasificador: ademas de no
    # aportar senal, `HistGradientBoostingClassifier` no puede binarizar una
    # columna con menos de 2 valores distintos (revienta con muestras chicas
    # -- tipico en tests con pocas semillas). Se reusa `valid_dims` (mismo
    # criterio que el calculo de OOD arriba) como las columnas "activas" del
    # modelo; `SurrogateActor` selecciona las mismas en inferencia.
    active_idx = valid_dims if valid_dims else list(range(x_train.shape[1]))

    def _select(x):
        return x[:, active_idx]

    y_pos_train = [r["position"] for r in train_rows]
    y_int_train = [float(r["intensity"]) for r in train_rows]
    y_multi_train = _vectorize(train_rows, [f"action_{t}" for t in ml_dataset.ACTION_TYPES])

    position_clf = HistGradientBoostingClassifier(random_state=random_state)
    position_clf.fit(_select(x_train), y_pos_train)

    intensity_reg = HistGradientBoostingRegressor(random_state=random_state)
    intensity_reg.fit(_select(x_train), y_int_train)

    active_labels = [i for i in range(y_multi_train.shape[1]) if len(set(y_multi_train[:, i])) > 1]
    multilabel_clf = None
    if active_labels:
        multilabel_clf = OneVsRestClassifier(
            HistGradientBoostingClassifier(random_state=random_state)
        )
        multilabel_clf.fit(_select(x_train), y_multi_train[:, active_labels])

    def _predict_multilabel(rows: list[dict[str, Any]]):
        import numpy as np  # noqa: PLC0415

        n = len(rows)
        out = np.zeros((n, len(ml_dataset.ACTION_TYPES)), dtype=int)
        if multilabel_clf is not None and n:
            x = _select(_vectorize(rows, feature_cols))
            pred = multilabel_clf.predict(x)
            for j, i in enumerate(active_labels):
                out[:, i] = pred[:, j]
        return out

    def _eval(rows: list[dict[str, Any]]) -> tuple[float, float, float, float]:
        if not rows:
            return float("nan"), float("nan"), float("nan"), float("nan")
        x = _select(_vectorize(rows, feature_cols))
        y_pos = [r["position"] for r in rows]
        y_int = [float(r["intensity"]) for r in rows]
        y_multi = _vectorize(rows, [f"action_{t}" for t in ml_dataset.ACTION_TYPES])
        pred_pos = position_clf.predict(x)
        pred_int = intensity_reg.predict(x)
        pred_multi = _predict_multilabel(rows)
        acc = accuracy_score(y_pos, pred_pos)
        f1 = f1_score(y_pos, pred_pos, average="macro", zero_division=0)
        mae = mean_absolute_error(y_int, pred_int)
        jac = jaccard_score(y_multi, pred_multi, average="samples", zero_division=0)
        return float(acc), float(f1), float(mae), float(jac)

    val_metrics = _eval(val_rows)
    test_metrics = _eval(test_rows)
    metrics = RoleMetrics(
        n_train=len(train_rows),
        n_val=len(val_rows),
        n_test=len(test_rows),
        position_accuracy_val=val_metrics[0],
        position_f1_macro_val=val_metrics[1],
        intensity_mae_val=val_metrics[2],
        multilabel_jaccard_val=val_metrics[3],
        position_accuracy_test=test_metrics[0],
        position_f1_macro_test=test_metrics[1],
        intensity_mae_test=test_metrics[2],
        multilabel_jaccard_test=test_metrics[3],
    )
    bundle = {
        "position_clf": position_clf,
        "intensity_reg": intensity_reg,
        "multilabel_clf": multilabel_clf,
        "active_labels": active_labels,
        "active_idx": active_idx,
        "action_types": list(ml_dataset.ACTION_TYPES),
        "ood": ood_info,
    }
    return bundle, metrics


def _mahalanobis(x_row, mean, var, valid_dims: list[int]) -> float:
    """Distancia de Mahalanobis DIAGONAL de `x_row` contra `(mean, var)` de
    train, restringida a `valid_dims` (ADR 009 secc. 4); una dimension `NaN`
    en `x_row` se ignora (no todo actor tiene todas las `pi_*` -- ver
    `dataset.PRIVATE_COLUMNS`)."""
    import math as _math

    total = 0.0
    for i in valid_dims:
        v = x_row[i]
        if v != v:  # NaN
            continue
        total += (v - mean[i]) ** 2 / var[i]
    return _math.sqrt(total)


def train_surrogate(
    sources: list[str | Path],
    out_path: str | Path,
    *,
    brain: str = "rules",
    actors: dict[str, ActorSheet] | None = None,
    country: Country | None = None,
    random_state: int = 0,
    queue_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """`republica ml train --runs <dir|jsonl...> --brain rules --out
    data/ml/surrogate_rules.joblib` (ADR 009 secc. 3/8). `queue_rows` (ADR
    009 secc. 4, usado por `ml/active.py::retrain_with_queue`): filas extra
    del formato de `dataset.rows_from_run` (de `active_queue.jsonl`) que se
    agregan al split de ENTRENAMIENTO (nunca a val/test: son casos donde el
    sustituto ya fallo, reentrenar sobre ellos no debe inflar la metrica de
    generalizacion)."""
    _sklearn()
    joblib = _joblib()
    actors = actors if actors is not None else load_actors()
    country = country if country is not None else load_country()

    paths = ml_dataset._iter_jsonl_paths(sources)  # noqa: SLF001 - mismo paquete
    if not paths:
        raise ValueError(f"ningun .jsonl encontrado en {sources!r}")
    rows: list[dict[str, Any]] = []
    n_runs = 0
    for p in paths:
        run = ml_dataset.load_run_jsonl(p)
        rows.extend(ml_dataset.rows_from_run(run, actors, country))
        n_runs += 1

    seeds = sorted({r["seed"] for r in rows})
    train_seeds, val_seeds, test_seeds = _split_seeds(seeds)
    train_rows = [r for r in rows if r["seed"] in train_seeds]
    val_rows = [r for r in rows if r["seed"] in val_seeds]
    test_rows = [r for r in rows if r["seed"] in test_seeds]
    if queue_rows:
        train_rows = train_rows + list(queue_rows)

    feature_cols = ml_dataset.feature_columns(country)
    roles_present = sorted({r["role"] for r in rows})

    models: dict[str, Any] = {}
    metrics: dict[str, dict[str, float | int]] = {}
    for role in roles_present:
        role_train = [r for r in train_rows if r["role"] == role]
        role_val = [r for r in val_rows if r["role"] == role]
        role_test = [r for r in test_rows if r["role"] == role]
        if len(role_train) < 2 or len({r["position"] for r in role_train}) < 2:
            continue
        bundle, role_metrics = _fit_role(
            role, role_train, role_val, role_test, feature_cols, random_state=random_state
        )
        models[role] = bundle
        metrics[role] = role_metrics.as_dict()

    manifest = {
        "brain": brain,
        "package_version": __version__,
        "sklearn_version": _sklearn().__version__,
        "python_version": platform.python_version(),
        "generated_at": datetime.now(UTC).isoformat(),
        "n_source_runs": n_runs,
        "n_rows": len(rows),
        "n_queue_rows": len(queue_rows or []),
        "seeds": {"train": train_seeds, "val": val_seeds, "test": test_seeds},
        "roles": roles_present,
        "feature_columns": feature_cols,
        "metrics": metrics,
        "random_state": random_state,
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "manifest": manifest,
            "models": models,
            "feature_columns": feature_cols,
            "country_config_hash": country.config_hash,
        },
        out,
    )
    manifest_path = out.parent / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"out": str(out), "manifest_path": str(manifest_path), **manifest}


@lru_cache(maxsize=8)
def _load_surrogate_bundle_cached(path_str: str, mtime_ns: int) -> dict[str, Any]:  # noqa: ARG001
    joblib = _joblib()
    return joblib.load(Path(path_str))


def load_surrogate_bundle(path: str | Path) -> dict[str, Any]:
    """`joblib.load(path)`, cacheado por `(ruta, mtime)` (ADR 009 secc. 3:
    "la inferencia se hace por lote de 29 actores por mes" -- sin esto,
    `build_actor_engine` construye un `SurrogateActor` por actor (28 no
    presidente) y cada uno releia el `.joblib` COMPLETO del disco
    (deserializando los 8 x 3 modelos sklearn cada vez): medido, dominaba
    por completo el tiempo de una corrida -- ver Notas de implementacion de
    ADR 009). Cachear solo por ruta bastaria DENTRO de una corrida (el spec
    de un brain es la misma ruta para todos los actores), pero no entre
    corridas del mismo proceso Python largo-vivo (`republica ui`, un
    notebook): `republica ml retrain` puede reescribir el mismo archivo, y
    sin el `mtime` en la clave un actor seguiria viendo el bundle VIEJO. Se
    incluye `mtime_ns` (no el contenido: un `.joblib` de sklearn pesa varios
    MB, hashearlo entero seria mas lento que el problema que resuelve) como
    parte de la clave de `lru_cache` para que un archivo reescrito invalide
    la entrada."""
    p = Path(path)
    return _load_surrogate_bundle_cached(str(p), p.stat().st_mtime_ns)


@dataclass
class SurrogateActor:
    """`decide(perception, rng) -> list[Action]` (ADR 009 secc. 3), misma
    interfaz que `RuleBasedActor`/`LLMActor`. `confidence` (probabilidad
    maxima de `position` del ultimo turno) queda en `self.last_confidence`
    para que `ml/active.py` decida si hace falta el respaldo."""

    sheet: ActorSheet
    bundle: dict[str, Any]
    country: Country
    parties_by_id: dict[str, Any] = field(default_factory=dict)
    #: Ruta del modelo (informativa: ADR 009 secc. 9 deliverable 3, "produce
    #: `ActionRecord` con `brain = surrogate`"), fijada por
    #: `build_surrogate_actor`. Vacia si se construyo con un `bundle` en
    #: memoria (tests) sin pasar por esa fabrica.
    model_path: str = ""
    _rule_fallback: RuleBasedActor | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.parties_by_id:
            self.parties_by_id = {p.id: p for p in self.country.parties}
        self.last_score = None  # paridad de interfaz (ADR 003 secc. 11 punto 27)
        self.last_confidence: float = 1.0
        self.last_ood: bool = False

    @property
    def role(self) -> str:
        return self.sheet.role

    @property
    def brain_name(self) -> str:
        return f"surrogate:{self.model_path}" if self.model_path else "surrogate"

    def _rule_actor(self) -> RuleBasedActor:
        if self._rule_fallback is None:
            self._rule_fallback = RuleBasedActor(
                self.sheet,
                self.country.parties,
                self.country.taylor,
                self.country.structure.r_neutral,
                self.country.policy_ranges["interest_rate_target"],
            )
        return self._rule_fallback

    def decide(self, perception: Any, rng: Any) -> list[Action]:
        role = self.sheet.role
        if role in RULE_PASSTHROUGH_ROLES or role not in self.bundle["models"]:
            self.last_confidence = 1.0
            self.last_ood = False
            return self._rule_actor().decide(perception, rng)

        model = self.bundle["models"][role]
        feature_cols = self.bundle["feature_columns"]
        row = ml_dataset.perception_features(
            self.sheet, perception, self.country, self.parties_by_id
        )
        x_full = _vectorize([row], feature_cols)

        ood = model.get("ood")
        if ood is not None and ood["valid_dims"]:
            distance = _mahalanobis(x_full[0], ood["mean"], ood["var"], ood["valid_dims"])
            self.last_ood = distance > ood["threshold"]
        else:
            self.last_ood = False

        active_idx = model.get("active_idx") or list(range(x_full.shape[1]))
        x = x_full[:, active_idx]

        proba = model["position_clf"].predict_proba(x)[0]
        classes = model["position_clf"].classes_
        best = int(proba.argmax())
        position = str(classes[best])
        confidence = float(proba[best])
        self.last_confidence = confidence

        intensity = float(model["intensity_reg"].predict(x)[0])
        intensity = max(0.0, min(1.0, intensity))

        reason = (
            f"sustituto (rol {role}): position={position} intensity={intensity:.2f} "
            f"(confianza {confidence:.2f})"
        )
        actions: list[Action] = []
        actor = self.sheet
        if position == "support":
            actions.append(
                Action(
                    type=ActionType.SUPPORT_POLICY,
                    actor_id=actor.id,
                    params={"intensity": intensity},
                    reason=reason,
                )
            )
        elif position == "oppose":
            actions.append(
                Action(
                    type=ActionType.OPPOSE_POLICY,
                    actor_id=actor.id,
                    params={"intensity": intensity},
                    reason=reason,
                )
            )
            if rng.random() < actor.personality.risk_tolerance * intensity:
                actions.extend(_escalate(actor, intensity, reason))
        elif position == "negotiate" and role in NEGOTIATE_CAPABLE_ROLES:
            concession = NEGOTIATE_CONCESSION.get(role, ConcessionType.DELAY_POLICY)
            actions.append(
                Action(
                    type=ActionType.NEGOTIATE,
                    actor_id=actor.id,
                    target="president",
                    params={
                        "requested_concession": concession,
                        "offer": "apoyo condicionado (sustituto)",
                    },
                    reason=reason,
                )
            )
        else:
            actions.append(Action(type=ActionType.NO_ACTION, actor_id=actor.id, reason=reason))

        if intensity >= STATEMENT_MIN_INTENSITY and (
            actor.personality.ambition > 0.5 or intensity > 0.6
        ):
            stance = position if position in ("support", "oppose") else "neutral"
            actions.append(
                Action(
                    type=ActionType.PUBLIC_STATEMENT,
                    actor_id=actor.id,
                    params={"stance": stance, "intensity": intensity},
                    reason=reason,
                )
            )

        if len(actions) > ACTION_BUDGET_PER_TURN:
            actions = [a for a in actions if a.type is not ActionType.PUBLIC_STATEMENT]
            while len(actions) > ACTION_BUDGET_PER_TURN:
                actions.pop()
        return actions


def build_surrogate_actor(
    path: str | Path, sheet: ActorSheet, country: Country, *, bundle: dict[str, Any] | None = None
) -> SurrogateActor:
    """Usado por `ai/brains.py` para el spec `surrogate:<path>`."""
    b = bundle if bundle is not None else load_surrogate_bundle(path)
    return SurrogateActor(sheet=sheet, bundle=b, country=country, model_path=str(path))


def evaluate_surrogate(
    model_path: str | Path,
    seeds: list[int],
    *,
    months: int = 48,
    country: Country | None = None,
    fallback: str | None = None,
) -> dict[str, Any]:
    """`republica ml evaluate --model ... --seeds 100:130` (ADR 009 secc.
    3/8): re-simula cada semilla con `default_brain = "rules"` y de nuevo
    con `default_brain = "surrogate:<path>[+fallback:...]"`, y compara
    `position` (derivada, `dataset._derive_position`) accion a accion, actor
    a actor, mes a mes -- las dos corridas DIVERGEN mes a mes (las acciones
    distintas realimentan el mundo), asi que esto mide fidelidad de
    comportamiento sobre una trayectoria completa, no solo la exactitud del
    clasificador en un dataset fijo (esa la reporta `manifest['metrics']`)."""
    from republica.engine.simulation import run as run_simulation

    country = country if country is not None else load_country()
    brain_spec = (
        f"surrogate:{model_path}" if not fallback else f"surrogate:{model_path}+fallback:{fallback}"
    )
    actors_by_id = load_actors()

    total = 0
    matches = 0
    per_role_total: dict[str, int] = {}
    per_role_matches: dict[str, int] = {}
    for seed in seeds:
        rules_history = run_simulation(
            seed=seed,
            months=months,
            country=country,
            actors_enabled=True,
            default_brain="rules",
            congress_enabled=True,
            negotiation_enabled=True,
            cohorts_enabled=True,
            media_enabled=True,
            memory_enabled=True,
            elections_enabled=True,
        )
        surrogate_history = run_simulation(
            seed=seed,
            months=months,
            country=country,
            actors_enabled=True,
            default_brain=brain_spec,
            congress_enabled=True,
            negotiation_enabled=True,
            cohorts_enabled=True,
            media_enabled=True,
            memory_enabled=True,
            elections_enabled=True,
        )
        rules_by_am: dict[tuple[int, str], set[str]] = {}
        for a in rules_history.action_records:
            rules_by_am.setdefault((a.month, a.actor), set()).add(a.type)
        sur_by_am: dict[tuple[int, str], set[str]] = {}
        for a in surrogate_history.action_records:
            sur_by_am.setdefault((a.month, a.actor), set()).add(a.type)
        for key, r_types in rules_by_am.items():
            s_types = sur_by_am.get(key)
            if s_types is None:
                continue
            actor_sheet = actors_by_id.get(key[1])
            role = actor_sheet.role if actor_sheet is not None else "unknown"
            r_pos = ml_dataset._derive_position(r_types)  # noqa: SLF001
            s_pos = ml_dataset._derive_position(s_types)  # noqa: SLF001
            total += 1
            per_role_total[role] = per_role_total.get(role, 0) + 1
            if r_pos == s_pos:
                matches += 1
                per_role_matches[role] = per_role_matches.get(role, 0) + 1

    agreement = matches / total if total else float("nan")
    per_role_agreement = {
        role: per_role_matches.get(role, 0) / n for role, n in per_role_total.items()
    }
    return {
        "seeds": seeds,
        "n_actor_months": total,
        "agreement_rate": agreement,
        "per_role_agreement": per_role_agreement,
    }


__all__ = [
    "ML_ROLES",
    "RULE_PASSTHROUGH_ROLES",
    "SurrogateActor",
    "build_surrogate_actor",
    "evaluate_surrogate",
    "load_surrogate_bundle",
    "train_surrogate",
]

# Reexportado para `ml/active.py` (distancia OOD sobre una fila ya vectorizada).
mahalanobis_distance = _mahalanobis
