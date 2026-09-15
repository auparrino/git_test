"""Early-warning (ADR 009 secc. 5): probabilidad de `collapse`|
`hyperinflation` dentro de los 12 meses siguientes al mes `t`, calibrada
(isotonica) y con las 6 features mas importantes (permutation importance).

`scikit-learn` (extra `[ml]`) se importa perezosamente, igual que el resto
de `ml/`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from republica.world.config import Country, load_country

_MISSING_SKLEARN_MSG = (
    "scikit-learn no esta instalado en este entorno. Instalar el extra "
    "opcional `ml` con `uv sync --group dev --extra ml` para usar "
    "`republica ml early-warning train|predict`."
)

#: Horizonte del target (ADR 009 secc. 5, literal: "dentro de los 12 meses
#: siguientes").
HORIZON_MONTHS = 12
#: Ventanas de tendencia (ADR 009 secc. 5, literal: "tendencias a 3 y 6 meses").
TREND_WINDOWS = (3, 6)

#: El "estado completo en t" (ADR 009 secc. 5): las 20 variables de
#: `WorldState` (ADR 003 secc. 1) + `inflation_lag1`.
STATE_VARS: tuple[str, ...] = (
    "gdp",
    "gdp_growth",
    "inflation",
    "unemployment",
    "real_wage",
    "interest_rate",
    "exchange_rate",
    "reserves",
    "public_debt",
    "fiscal_balance",
    "poverty",
    "government_approval",
    "congress_support",
    "political_stability",
    "social_tension",
    "institutional_confidence",
    "consumer_confidence",
    "protest_level",
    "inequality",
    "crime_perception",
    "inflation_lag1",
)
#: Variables sobre las que se calcula tendencia a 3/6 meses (ADR secc. 5 no
#: pide tendencia de las 20 -- se usan las mas relevantes a una crisis:
#: inflacion, reservas, estabilidad, aprobacion, desempleo).
TREND_VARS: tuple[str, ...] = (
    "inflation",
    "reserves",
    "political_stability",
    "government_approval",
    "unemployment",
)

CRISIS_OUTCOMES = ("collapse", "hyperinflation")


def _sklearn():
    try:
        import sklearn  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(_MISSING_SKLEARN_MSG) from exc
    return sklearn


def _herfindahl(seats: dict[str, int]) -> float:
    total = sum(seats.values())
    if total <= 0:
        return 0.0
    return sum((s / total) ** 2 for s in seats.values())


def _trend(states: list[dict[str, float]], var: str, t_idx: int, window: int) -> float:
    if t_idx - window < 0:
        return 0.0
    return (states[t_idx][var] - states[t_idx - window][var]) / window


def build_early_warning_rows(
    path: str | Path, *, country: Country | None = None
) -> list[dict[str, Any]]:
    """Una fila por mes `t` de la corrida en `path` (ADR 009 secc. 5).
    `crisis_12m` (target) se deriva de `outcome`/longitud de `records`: la
    corrida corta en el mes de la crisis (`engine/simulation.py::run`), asi
    que "crisis dentro de los 12 meses de t" es simplemente "el outcome es
    de crisis Y el mes final cae en `[t+1, t+12]`"."""
    from republica.engine import narrate as narrate_mod
    from republica.ml.dataset import load_run_jsonl

    country = country if country is not None else load_country()
    seats_by_party = {p.id: p.seats for p in country.parties}
    fragmentation = _herfindahl(seats_by_party)

    run = load_run_jsonl(path)
    # `PerceptionRecord` (ADR 005 secc. 4) no lo agrupa `dataset.
    # load_run_jsonl` (solo le interesan `action`/`memory`): se relee con
    # `narrate.load_jsonl` para `perception_gap` (vacio/0.0 con
    # `features.cohorts=False`, mismo criterio que `experiments/runner.py::
    # extract_run_metrics`).
    perceptions_by_month = narrate_mod.load_jsonl(path).perceptions_by_month
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    summary = json.loads(lines[-1])
    outcome = summary.get("outcome")
    is_crisis_run = outcome in CRISIS_OUTCOMES
    final_month = run.records[-1]["month_index"] if run.records else 0

    states = [r["state"] for r in run.records]

    agreements_broken_cum = 0
    events_by_month: dict[int, list[str]] = {
        r["month_index"]: r.get("events", []) for r in run.records
    }

    rows: list[dict[str, Any]] = []
    for idx, rec in enumerate(run.records):
        month = rec["month_index"]
        agreements_broken_cum += sum(
            1 for ev in events_by_month.get(month, []) if ev.startswith("agreement_broken:")
        )
        row: dict[str, Any] = {"run_id": run.run_id, "seed": run.seed, "month": month}
        for var in STATE_VARS:
            row[f"state_{var}"] = states[idx].get(var, 0.0)
        for var in TREND_VARS:
            for window in TREND_WINDOWS:
                row[f"trend_{var}_{window}m"] = _trend(states, var, idx, window)
        row["protest_level"] = states[idx].get("protest_level", 0.0)
        row["congress_support"] = states[idx].get("congress_support", 0.0)
        row["fragmentation_herfindahl"] = fragmentation
        row["agreements_broken_cum"] = agreements_broken_cum
        month_perceptions = perceptions_by_month.get(month, [])
        row["perception_gap"] = (
            month_perceptions[0].get("perception_gap", 0.0) if month_perceptions else 0.0
        )
        row["crisis_12m"] = int(is_crisis_run and month < final_month <= month + HORIZON_MONTHS)
        #: Grupo para el split 70/15/15 de `ml/surrogate.py::
        #: _split_group_seeds` (hallazgo #2 de REVIEW_003): el directorio
        #: padre del `.jsonl` (`<experimento>/<brazo>`), para no mezclar
        #: semillas de experimentos distintos que reusan los mismos
        #: numeros (ej. `fiscal_rule` 0-19 y `central_bank_independence`
        #: 0-49 combinados en un mismo entrenamiento).
        row["source"] = str(Path(path).parent)
        rows.append(row)
    return rows


def feature_columns() -> list[str]:
    cols = [f"state_{v}" for v in STATE_VARS]
    cols += [f"trend_{v}_{w}m" for v in TREND_VARS for w in TREND_WINDOWS]
    cols += [
        "protest_level",
        "congress_support",
        "fragmentation_herfindahl",
        "agreements_broken_cum",
        "perception_gap",
    ]
    return cols


def _vectorize(rows: list[dict[str, Any]], columns: list[str]):
    import numpy as np  # noqa: PLC0415

    return np.array([[float(r.get(c, 0.0)) for c in columns] for r in rows], dtype=float)


def _iter_jsonl_paths(sources: list[str | Path]) -> list[Path]:
    from republica.ml.dataset import _iter_jsonl_paths as _impl  # noqa: PLC0415

    return _impl(sources)


@dataclass
class EarlyWarningModel:
    model: Any
    feature_columns: list[str]
    top_features: list[tuple[str, float]]
    manifest: dict[str, Any]


def train_early_warning(
    sources: list[str | Path],
    out_path: str | Path,
    *,
    country: Country | None = None,
    random_state: int = 0,
    allow_in_sample: bool = False,
) -> dict[str, Any]:
    """`republica ml early-warning train --runs <dir> --out ...` (ADR 009
    secc. 5/8). Split 70/15/15 por `(fuente, semilla)` -- `ml/surrogate.py::
    _split_group_seeds`, hallazgo #2 de REVIEW_003: agrupar por FUENTE (el
    directorio `<experimento>/<brazo>` de cada `.jsonl`) antes de partir es
    lo que evita que, al combinar `fiscal_rule` (semillas 0-19) con
    `central_bank_independence` (semillas 0-49), los numeros de semilla
    coincidentes entre las dos fuentes degeneren el split (ver el docstring
    de `_split_group_seeds`). `allow_in_sample` (hallazgo #11): igual que
    `train_surrogate`, permite entrenar con una fuente de <=2 semillas
    (queda `manifest['in_sample'] = True`) en vez de levantar `ValueError`."""
    _sklearn()
    import joblib
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import roc_auc_score

    from republica.ml.surrogate import _sorted_pairs, _split_group_seeds

    country = country if country is not None else load_country()
    paths = _iter_jsonl_paths(sources)
    if not paths:
        raise ValueError(f"ningun .jsonl encontrado en {sources!r}")

    rows: list[dict[str, Any]] = []
    n_runs = 0
    for p in paths:
        try:
            rows.extend(build_early_warning_rows(p, country=country))
            n_runs += 1
        except (ValueError, KeyError, IndexError):
            continue

    pairs = sorted({(r["source"], r["seed"]) for r in rows})
    train_keys, val_keys, test_keys, in_sample_sources = _split_group_seeds(
        pairs, allow_in_sample=allow_in_sample
    )
    train_rows = [r for r in rows if (r["source"], r["seed"]) in train_keys]
    val_rows = [r for r in rows if (r["source"], r["seed"]) in val_keys]
    test_rows = [r for r in rows if (r["source"], r["seed"]) in test_keys]

    cols = feature_columns()
    x_train = _vectorize(train_rows, cols)
    y_train = [r["crisis_12m"] for r in train_rows]

    base = HistGradientBoostingClassifier(random_state=random_state)
    n_pos = sum(y_train)
    if n_pos >= 3 and len(y_train) - n_pos >= 3:
        clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
    else:
        clf = base
    clf.fit(x_train, y_train)

    def _auc(rows_split: list[dict[str, Any]]) -> float:
        if not rows_split:
            return float("nan")
        y = [r["crisis_12m"] for r in rows_split]
        if len(set(y)) < 2:
            return float("nan")
        x = _vectorize(rows_split, cols)
        proba = clf.predict_proba(x)[:, 1]
        return float(roc_auc_score(y, proba))

    auc_val = _auc(val_rows)
    auc_test = _auc(test_rows)

    top_features: list[tuple[str, float]] = []
    if test_rows and len(set(r["crisis_12m"] for r in test_rows)) > 1:
        x_test = _vectorize(test_rows, cols)
        y_test = [r["crisis_12m"] for r in test_rows]
        imp = permutation_importance(
            clf, x_test, y_test, n_repeats=5, random_state=random_state, scoring="roc_auc"
        )
        ranked = sorted(zip(cols, imp.importances_mean, strict=True), key=lambda kv: -kv[1])
        top_features = [(name, float(val)) for name, val in ranked[:6]]

    manifest = {
        "n_source_runs": n_runs,
        "n_rows": len(rows),
        "n_positive": sum(r["crisis_12m"] for r in rows),
        #: `[fuente, semilla]` por tramo (hallazgo #2 de REVIEW_003).
        "seeds": {
            "train": _sorted_pairs(train_keys),
            "val": _sorted_pairs(val_keys),
            "test": _sorted_pairs(test_keys),
        },
        "in_sample": bool(in_sample_sources),
        "in_sample_sources": sorted(in_sample_sources),
        "auc_val": auc_val,
        "auc_test": auc_test,
        "top_features": top_features,
        "horizon_months": HORIZON_MONTHS,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": clf, "feature_columns": cols, "manifest": manifest}, out)
    manifest_path = out.parent / "early_warning_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"out": str(out), "manifest_path": str(manifest_path), **manifest}


def load_early_warning(path: str | Path) -> dict[str, Any]:
    import joblib  # noqa: PLC0415

    return joblib.load(Path(path))


def predict_crisis_risk(
    bundle: dict[str, Any], row: dict[str, Any]
) -> tuple[float, list[tuple[str, float]]]:
    """Probabilidad de crisis a 12 meses + los top-6 drivers ya guardados en
    el manifest (ADR 009 secc. 5: "probabilidad y las 6 features mas
    importantes")."""
    x = _vectorize([row], bundle["feature_columns"])
    proba = float(bundle["model"].predict_proba(x)[0, 1])
    return proba, bundle["manifest"].get("top_features", [])


def predict_from_run(
    model_path: str | Path, run_path: str | Path, month: int, *, country: Country | None = None
) -> dict[str, Any]:
    """`republica ml early-warning predict --run run.jsonl --month N`."""
    bundle = load_early_warning(model_path)
    rows = build_early_warning_rows(run_path, country=country)
    row = next((r for r in rows if r["month"] == month), None)
    if row is None:
        raise ValueError(f"el mes {month} no esta en {run_path}")
    proba, drivers = predict_crisis_risk(bundle, row)
    return {"month": month, "probability": proba, "top_features": drivers}


def risk_sentence(probability: float, drivers: list[tuple[str, float]]) -> str:
    """ "Riesgo de crisis a 12 meses: 73 %" + drivers (ADR 009 secc. 5, hook
    de `narrate`/UI, texto literal del ADR)."""
    pct = round(probability * 100)
    line = f"Riesgo de crisis a 12 meses: {pct} %"
    if drivers:
        names = ", ".join(name for name, _ in drivers[:3])
        line += f" (principales factores: {names})"
    return line


__all__ = [
    "CRISIS_OUTCOMES",
    "HORIZON_MONTHS",
    "STATE_VARS",
    "TREND_VARS",
    "build_early_warning_rows",
    "feature_columns",
    "load_early_warning",
    "predict_crisis_risk",
    "predict_from_run",
    "risk_sentence",
    "train_early_warning",
]
