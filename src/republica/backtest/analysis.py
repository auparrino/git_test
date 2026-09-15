"""Analisis de predictibilidad (ADR 014 secc. 4): tablas estratificadas,
modelo de predictibilidad (regresion logistica + arbol), dispersion como
senal, comparacion calibrado vs Aurora por decada.

Requiere el extra `ml` (`scikit-learn`, `joblib`) para
`fit_predictability_model`/`permutation_importance`/CV por decada; el resto
(tablas estratificadas, IQR vs error) solo necesita la libreria estandar +
`statistics` (Spearman se calcula a mano, sin `scipy`, para no atar TODO el
modulo al extra `analysis`)."""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

from republica.validation.argentina import bootstrap_ci

#: Columnas categoricas/discretas para las tablas estratificadas (ADR 014
#: secc. 3/4 punto 1).
STRATIFY_COLUMNS: tuple[str, ...] = (
    "arm",
    "h",
    "frequency",
    "has_era",
    "in_sample",
    "regime_mode_initial",
    "fx_regime",
    "inflation_bucket",
    "has_reserves_series",
    "has_unemployment_series",
)

#: Columnas numericas candidatas para el modelo de predictibilidad.
NUMERIC_FEATURES: tuple[str, ...] = (
    "h",
    "n_source",
    "n_proxy",
    "n_assumed",
    "vdem_polyarchy",
    "years_since_last_coup",
    "inflation_now",
    "inflation_trend_12m",
    "reserves_over_imports_3m",
    "debt_over_gdp_pct",
    "years_since_last_default",
    "months_to_next_election",
    "approval_proxy",
    "fragmentation_herfindahl",
    "n_exogenous_shocks",
    "shocks_magnitude_sum",
    "iqr_seeds",
)

#: Columnas categoricas candidatas (se codifican one-hot en el modelo).
CATEGORICAL_FEATURES: tuple[str, ...] = (
    "arm",
    "frequency",
    "has_era",
    "regime_mode_initial",
    "fx_regime",
    "inflation_bucket",
    "has_reserves_series",
    "has_unemployment_series",
    "in_sample",
)

FEATURE_LABELS: dict[str, str] = {
    "h": "horizonte (meses)",
    "n_source": "nº de variables con dato real (source)",
    "n_proxy": "nº de variables proxy",
    "n_assumed": "nº de variables asumidas (sin dato)",
    "vdem_polyarchy": "poliarquia V-Dem",
    "years_since_last_coup": "años desde el último golpe",
    "inflation_now": "inflación mensual inicial (%)",
    "inflation_trend_12m": "tendencia de inflación previa 12m (%)",
    "reserves_over_imports_3m": "reservas / importaciones trimestrales",
    "debt_over_gdp_pct": "deuda pública / PIB (%)",
    "years_since_last_default": "años desde el último default",
    "months_to_next_election": "meses hasta la próxima elección",
    "approval_proxy": "aprobación proxy",
    "fragmentation_herfindahl": "fragmentación (Herfindahl de bancas)",
    "n_exogenous_shocks": "nº de shocks exógenos forzados",
    "shocks_magnitude_sum": "magnitud acumulada de shocks",
    "iqr_seeds": "dispersión entre semillas (IQR)",
}


def _parse_bool(v: str) -> bool | None:
    if v in ("True", "1", "true"):
        return True
    if v in ("False", "0", "false"):
        return False
    return None


def _parse_float(v: str) -> float | None:
    if v in ("", None):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_windows(csv_path: Path) -> list[dict]:
    """Lee `windows.csv` y castea tipos (todo llega como `str` de
    `csv.DictReader`): `hit`/`n_seeds`/`h` a `int`, numericos a `float|None`,
    `has_*`/`has_era`/`in_sample` a `bool|None`."""
    rows: list[dict] = []
    with Path(csv_path).open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            row = dict(raw)
            row["hit"] = int(row["hit"])
            row["h"] = int(row["h"])
            row["n_seeds"] = int(row["n_seeds"]) if row.get("n_seeds") else 0
            for col in ("error", *NUMERIC_FEATURES):
                if col in row and col != "h":
                    row[col] = _parse_float(row[col])
            for col in ("has_era", "has_reserves_series", "has_unemployment_series", "in_sample"):
                if col in row:
                    row[col] = _parse_bool(row[col])
            rows.append(row)
    return rows


def decade(t0: str) -> int:
    return (int(t0[:4]) // 10) * 10


# --------------------------------------------------------------------------
# 1. Tablas estratificadas (ADR 014 secc. 4 punto 1)
# --------------------------------------------------------------------------


def stratified_table(
    rows: list[dict], objective: str, feature: str, resamples: int = 500
) -> list[dict]:
    """Tasa de acierto por `feature` (tramos/categorias) para `objective`,
    con IC 95% bootstrap (`validation/argentina.py::bootstrap_ci`, sobre las
    FILAS -- cada fila ya es una ventana-objetivo-brazo) y `N`."""
    subset = [r for r in rows if r["objective"] == objective]
    groups: dict[str, list[int]] = {}
    for r in subset:
        key = str(r.get(feature))
        groups.setdefault(key, []).append(r["hit"])
    out = []
    for value, hits in sorted(groups.items()):
        lo, hi = bootstrap_ci([float(h) for h in hits], statistics.mean, resamples=resamples)
        out.append(
            {
                "feature": feature,
                "value": value,
                "n": len(hits),
                "hit_rate": sum(hits) / len(hits),
                "ci_lo": lo,
                "ci_hi": hi,
            }
        )
    return out


def all_stratified_tables(
    rows: list[dict], objectives: list[str], resamples: int = 500
) -> dict[str, dict[str, list[dict]]]:
    return {
        obj: {feat: stratified_table(rows, obj, feat, resamples) for feat in STRATIFY_COLUMNS}
        for obj in objectives
    }


# --------------------------------------------------------------------------
# 3. Dispersion como señal (ADR 014 secc. 4 punto 3)
# --------------------------------------------------------------------------


def _spearman(xs: list[float], ys: list[float]) -> tuple[float | None, int]:
    """Correlacion de Spearman sin `scipy` (rangos + Pearson sobre
    rangos, formula estandar; empates con rango promedio)."""
    n = len(xs)
    if n < 3:
        return None, n

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        r = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg_rank
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    varx = sum((a - mx) ** 2 for a in rx)
    vary = sum((b - my) ** 2 for b in ry)
    if varx == 0 or vary == 0:
        return None, n
    return cov / (varx**0.5 * vary**0.5), n


def iqr_vs_error(rows: list[dict], objective: str = "inflation_magnitude") -> dict:
    """¿La IQR entre semillas predice el error? (ADR 014 secc. 4 punto 3):
    Spearman entre `iqr_seeds` y `error`, solo para el objetivo continuo
    (`inflation_magnitude`, el unico con `error` numerico -- ver
    `scoring.py`)."""
    subset = [
        r
        for r in rows
        if r["objective"] == objective
        and r.get("iqr_seeds") is not None
        and r.get("error") is not None
    ]
    rho, n = _spearman([r["iqr_seeds"] for r in subset], [r["error"] for r in subset])
    return {"objective": objective, "n": n, "spearman_rho": rho}


# --------------------------------------------------------------------------
# 4. Calibrado vs Aurora por decada (ADR 014 secc. 4 punto 4)
# --------------------------------------------------------------------------


def calibrated_vs_aurora_by_decade(rows: list[dict], objectives: list[str]) -> list[dict]:
    out = []
    decades = sorted({decade(r["t0"]) for r in rows})
    for dec in decades:
        for obj in objectives:
            cal = [
                r["hit"]
                for r in rows
                if r["objective"] == obj and decade(r["t0"]) == dec and r["arm"] == "calibrated"
            ]
            aur = [
                r["hit"]
                for r in rows
                if r["objective"] == obj and decade(r["t0"]) == dec and r["arm"] == "aurora"
            ]
            if not cal and not aur:
                continue
            out.append(
                {
                    "decade": dec,
                    "objective": obj,
                    "n_calibrated": len(cal),
                    "hit_rate_calibrated": (sum(cal) / len(cal)) if cal else None,
                    "n_aurora": len(aur),
                    "hit_rate_aurora": (sum(aur) / len(aur)) if aur else None,
                }
            )
    return out


# --------------------------------------------------------------------------
# 2. Modelo de predictibilidad (ADR 014 secc. 4 punto 2), requiere `ml`
# --------------------------------------------------------------------------


def _design_matrix(rows: list[dict]):
    """`(X, feature_names)` con imputacion simple: numericas -> mediana de
    la columna, categoricas -> one-hot con una categoria `"__missing__"`.
    Devuelve listas de Python puro (sin `numpy`/`pandas` en la firma) para
    que el caller decida si envolverlas en un array."""
    numeric_present = [c for c in NUMERIC_FEATURES if any(r.get(c) is not None for r in rows)]
    medians = {}
    for c in numeric_present:
        vals = [r[c] for r in rows if r.get(c) is not None]
        medians[c] = statistics.median(vals) if vals else 0.0

    categorical_present = [
        c for c in CATEGORICAL_FEATURES if any(r.get(c) is not None for r in rows)
    ]
    categories: dict[str, list[str]] = {}
    for c in categorical_present:
        cats = sorted({str(r.get(c)) if r.get(c) is not None else "__missing__" for r in rows})
        categories[c] = cats

    feature_names: list[str] = list(numeric_present)
    for c in categorical_present:
        # se deja UNA categoria afuera (la primera, alfabeticamente) como
        # base, para no colinealizar el modelo logistico (dummy encoding
        # estandar).
        for cat in categories[c][1:]:
            feature_names.append(f"{c}={cat}")

    X: list[list[float]] = []
    for r in rows:
        vec: list[float] = []
        for c in numeric_present:
            v = r.get(c)
            vec.append(v if v is not None else medians[c])
        for c in categorical_present:
            val = str(r.get(c)) if r.get(c) is not None else "__missing__"
            for cat in categories[c][1:]:
                vec.append(1.0 if val == cat else 0.0)
        X.append(vec)
    return X, feature_names


def fit_predictability_model(rows: list[dict], objective: str, min_rows: int = 20) -> dict:
    """Regresion logistica L2 + arbol de profundidad <= 3 sobre `hit`
    (ADR 014 secc. 4 punto 2), con importancia por permutacion y
    validacion cruzada por decada. `None` si hay muy pocas filas (`min_rows`)
    o si `hit` no tiene las dos clases (no hay nada que aprender)."""
    subset = [r for r in rows if r["objective"] == objective]
    if len(subset) < min_rows:
        return {
            "objective": objective,
            "skipped_reason": f"solo {len(subset)} filas (< {min_rows})",
        }
    y_raw = [r["hit"] for r in subset]
    if len(set(y_raw)) < 2:
        return {"objective": objective, "skipped_reason": "hit sin las dos clases (0 y 1)"}

    try:
        import numpy as np
        from sklearn.inspection import permutation_importance
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold, cross_val_score
        from sklearn.tree import DecisionTreeClassifier, export_text
    except ImportError:
        return {"objective": objective, "skipped_reason": "extra `ml` no instalado"}

    X_list, feature_names = _design_matrix(subset)
    X = np.array(X_list, dtype=float)
    y = np.array(y_raw, dtype=int)
    groups = np.array([decade(r["t0"]) for r in subset])

    tree = DecisionTreeClassifier(
        max_depth=3, min_samples_leaf=max(5, len(subset) // 20), random_state=0
    )
    tree.fit(X, y)

    # L2 (regularizada) es el default de `LogisticRegression`; se deja
    # implicito para no chocar con el FutureWarning de sklearn >= 1.8 sobre
    # el parametro `penalty` (ADR 014 secc. 4 punto 2: "regresion logistica
    # regularizada").
    logit = LogisticRegression(C=1.0, max_iter=2000)
    logit.fit(X, y)
    logit_coefs = dict(zip(feature_names, logit.coef_[0].tolist(), strict=True))

    n_groups = len(set(groups.tolist()))
    cv_scores_tree = cv_scores_logit = None
    if n_groups >= 3:
        cv = GroupKFold(n_splits=min(5, n_groups))
        cv_scores_tree = cross_val_score(
            DecisionTreeClassifier(
                max_depth=3, min_samples_leaf=max(5, len(subset) // 20), random_state=0
            ),
            X,
            y,
            groups=groups,
            cv=cv,
            scoring="accuracy",
        ).tolist()
        cv_scores_logit = cross_val_score(
            LogisticRegression(C=1.0, max_iter=2000),
            X,
            y,
            groups=groups,
            cv=cv,
            scoring="accuracy",
        ).tolist()

    perm = permutation_importance(tree, X, y, n_repeats=20, random_state=0, scoring="accuracy")
    importances = sorted(
        zip(feature_names, perm.importances_mean.tolist(), strict=True), key=lambda kv: -kv[1]
    )

    rules = tree_rules_plain_language(tree, feature_names)

    return {
        "objective": objective,
        "n": len(subset),
        "base_rate": sum(y_raw) / len(y_raw),
        "feature_names": feature_names,
        "tree_text": export_text(tree, feature_names=feature_names),
        "tree_rules_plain": rules,
        "permutation_importance": importances[:10],
        "logit_coefficients": sorted(logit_coefs.items(), key=lambda kv: -abs(kv[1]))[:10],
        "cv_accuracy_tree_by_decade": cv_scores_tree,
        "cv_accuracy_logit_by_decade": cv_scores_logit,
        "n_decades": n_groups,
    }


def tree_rules_plain_language(tree, feature_names: list[str], top_n: int = 3) -> list[str]:
    """Recorre las hojas del arbol (profundidad <= 3) y arma, para las
    `top_n` con mas muestras, una frase en lenguaje llano: "con <condicion>
    ..., el objetivo se acierta el X% (N ventanas)" -- el patron literal del
    ejemplo de ADR 014 secc. 4."""
    t = tree.tree_
    leaves: list[tuple[list[str], int, float]] = []

    def label(feat_idx: int, threshold: float, go_left: bool) -> str:
        name = feature_names[feat_idx]
        if "=" in name:
            # columna one-hot ("fx_regime=peg"): <= 0.5 es "no es esa
            # categoria" (rama izquierda), > 0.5 es "es esa categoria".
            base, cat = name.split("=", 1)
            pretty_base = FEATURE_LABELS.get(base, base)
            return f"{pretty_base} {'≠' if go_left else '='} {cat}"
        pretty = FEATURE_LABELS.get(name, name)
        op = "≤" if go_left else ">"
        return f"{pretty} {op} {threshold:.2f}"

    def walk(node: int, conditions: list[str]) -> None:
        if t.children_left[node] == t.children_right[node] == -1:
            n_samples = int(t.n_node_samples[node])
            counts = t.value[node][0]
            n_pos = float(counts[1]) if len(counts) > 1 else 0.0
            hit_rate = n_pos / n_samples if n_samples else 0.0
            leaves.append((conditions, n_samples, hit_rate))
            return
        feat, thr = t.feature[node], t.threshold[node]
        walk(t.children_left[node], [*conditions, label(feat, thr, True)])
        walk(t.children_right[node], [*conditions, label(feat, thr, False)])

    walk(0, [])
    leaves.sort(key=lambda x: -x[1])
    out = []
    for conditions, n, hit_rate in leaves[:top_n]:
        cond_text = " y ".join(conditions) if conditions else "(sin condiciones, raíz)"
        out.append(
            f"con {cond_text}: se acierta el {hit_rate * 100:.0f} % ({n} ventanas-objetivo)."
        )
    return out
