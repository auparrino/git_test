"""Clustering de regimenes (ADR 009 secc. 6): un vector de trayectoria por
corrida, estandarizado -> PCA -> k-means con `k` elegido por silhouette en
`[3, 8]`. Lee de la tabla `runs`/`months`/`negotiations`/`actions`/
`perception`/`elections` de un DuckDB ya cargado (`republica experiment
load`, ADR 008 secc. 3) -- `republica ml regimes --db ...` no toma
`--runs`: opera sobre lo que ya este en la base, para poder correrlo sobre
la UNION de varios experimentos cargados en el mismo `.duckdb`.

`duckdb` (extra `[analysis]`) y `scikit-learn` (extra `[ml]`) se importan
perezosamente, igual que el resto de `ml/`."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from republica.engine.permissions import AUTHORITY_VIOLATION_MARKER
from republica.experiments.store import open_db

#: Las 8 variables clave (ADR 009 secc. 6: "8 variables clave" -- las mismas
#: 8 del tablero, `narrate.KEY_INDICATORS`, ya establecidas como "las 8" en
#: el proyecto).
TRAJECTORY_VARS: tuple[str, ...] = (
    "gdp_growth",
    "inflation",
    "unemployment",
    "exchange_rate",
    "reserves",
    "government_approval",
    "political_stability",
    "poverty",
)

REGIMES_TABLE_SQL = """CREATE TABLE IF NOT EXISTS regimes (
    run_id VARCHAR PRIMARY KEY,
    cluster INTEGER,
    pc1 DOUBLE,
    pc2 DOUBLE,
    features_json VARCHAR
)"""


def _percentiles(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    s = sorted(values)

    def pct(p: float) -> float:
        if len(s) == 1:
            return s[0]
        idx = p * (len(s) - 1)
        lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
        frac = idx - lo
        return s[lo] * (1 - frac) + s[hi] * frac

    return pct(0.10), pct(0.50), pct(0.90)


def _slope(values: list[float]) -> float:
    """Pendiente OLS simple de `values` contra `0..n-1` (sin numpy: pocas
    decenas de puntos por corrida, no justifica la dependencia aca)."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(values)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=True))
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den if den else 0.0


def build_vectors_from_db(con: Any) -> list[dict[str, Any]]:
    """Un vector de trayectoria (ADR 009 secc. 6) por `run_id` presente en
    `runs`."""
    runs = con.execute("SELECT run_id, experiment, arm, outcome FROM runs").fetchall()
    vectors: list[dict[str, Any]] = []
    for run_id, experiment, arm, outcome in runs:
        months = con.execute(
            "SELECT month, state_json FROM months WHERE run_id = ? ORDER BY month", [run_id]
        ).fetchall()
        if not months:
            continue
        states = [json.loads(s) for _, s in months]
        row: dict[str, Any] = {
            "run_id": run_id,
            "experiment": experiment,
            "arm": arm,
            "outcome": outcome,
        }
        for var in TRAJECTORY_VARS:
            series = [s.get(var, 0.0) for s in states]
            p10, p50, p90 = _percentiles(series)
            row[f"{var}_p10"] = p10
            row[f"{var}_p50"] = p50
            row[f"{var}_p90"] = p90
            row[f"{var}_slope"] = _slope(series)

        neg = con.execute("SELECT result FROM negotiations WHERE run_id = ?", [run_id]).fetchall()
        row["n_agreements"] = sum(1 for (r,) in neg if r == "agreement")
        row["n_broken"] = sum(
            1 for (r,) in neg if r in ("walk_away", "broken_by_actor", "broken_by_president")
        )

        gaps = con.execute(
            "SELECT json_extract_string(real_json, '$.perception_gap') FROM perception "
            "WHERE run_id = ?",
            [run_id],
        ).fetchall()
        gap_values = [float(g) for (g,) in gaps if g is not None]
        row["perception_gap_mean"] = statistics.mean(gap_values) if gap_values else 0.0

        actions = con.execute(
            "SELECT authorized, denied_reason FROM actions WHERE run_id = ?", [run_id]
        ).fetchall()
        row["authority_violations"] = sum(
            1
            for authorized, denied_reason in actions
            if not authorized and denied_reason and AUTHORITY_VIOLATION_MARKER in denied_reason
        )

        elections = con.execute(
            "SELECT result_json FROM elections WHERE run_id = ? ORDER BY month", [run_id]
        ).fetchall()
        turnovers = 0
        for (result_json,) in elections:
            result = json.loads(result_json)
            if result.get("winner") != result.get("incumbent_party"):
                turnovers += 1
        row["electoral_turnover"] = turnovers

        vectors.append(row)
    return vectors


#: `outcome` -> valor numerico para el vector (ADR secc. 6: "outcome" es
#: parte del vector de trayectoria; se codifica como severidad de crisis,
#: 0 = sin crisis, 1 = crisis, para que aporte a la distancia euclidea del
#: clustering sin necesitar one-hot).
_OUTCOME_SEVERITY = {
    "collapse": 1.0,
    "hyperinflation": 1.0,
    "defeated": 0.3,
    "reelected": 0.0,
    "survived": 0.0,
}


def _feature_columns() -> list[str]:
    cols: list[str] = []
    for var in TRAJECTORY_VARS:
        cols += [f"{var}_p10", f"{var}_p50", f"{var}_p90", f"{var}_slope"]
    cols += [
        "outcome_severity",
        "n_agreements",
        "n_broken",
        "perception_gap_mean",
        "authority_violations",
        "electoral_turnover",
    ]
    return cols


@dataclass
class RegimeResult:
    k: int
    silhouette: float
    labels: list[int]
    centroids: list[dict[str, float]]
    pc1: list[float]
    pc2: list[float]


def fit_regimes(
    vectors: list[dict[str, Any]], *, k_range: tuple[int, int] = (3, 8)
) -> RegimeResult:
    """Estandariza -> PCA(2) -> k-means con `k` elegido por silhouette en
    `k_range` (ADR 009 secc. 6)."""
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    for row in vectors:
        row["outcome_severity"] = _OUTCOME_SEVERITY.get(row.get("outcome"), 0.0)

    cols = _feature_columns()
    x = np.array([[float(row.get(c, 0.0)) for c in cols] for row in vectors], dtype=float)
    x_scaled = StandardScaler().fit_transform(x)

    pca = PCA(n_components=min(2, x_scaled.shape[1]))
    coords = pca.fit_transform(x_scaled)
    pc1 = coords[:, 0].tolist()
    pc2 = coords[:, 1].tolist() if coords.shape[1] > 1 else [0.0] * len(pc1)

    n = len(vectors)
    lo, hi = k_range
    hi = min(hi, max(lo, n - 1))
    best_k, best_score, best_labels = lo, -2.0, None
    for k in range(lo, hi + 1):
        if k >= n:
            break
        km = KMeans(n_clusters=k, random_state=0, n_init=10)
        labels = km.fit_predict(x_scaled)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(x_scaled, labels)
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels

    if best_labels is None:
        best_k = 1
        best_labels = [0] * n
        best_score = 0.0

    centroids: list[dict[str, float]] = []
    for cluster_id in sorted(set(best_labels)):
        members = [row for row, lbl in zip(vectors, best_labels, strict=True) if lbl == cluster_id]
        centroid = {c: statistics.mean(float(m.get(c, 0.0)) for m in members) for c in cols}
        centroid["n_runs"] = len(members)
        centroid["cluster"] = cluster_id
        centroids.append(centroid)

    return RegimeResult(
        k=best_k,
        silhouette=float(best_score),
        labels=[int(v) for v in best_labels],
        centroids=centroids,
        pc1=pc1,
        pc2=pc2,
    )


def describe_cluster(centroid: dict[str, float]) -> str:
    """Frase plantilla por cluster (ADR 009 secc. 6: "una frase plantilla
    por cluster"), armada de los rasgos mas salientes del centroide -- NO es
    un nombre elegido a mano: eso lo hace quien lee la tabla (`republica ml
    regimes --describe`), ADR literal "los clusters reciben un nombre
    DESPUES, por sus centroides"."""
    infl = centroid.get("inflation_p50", 0.0)
    growth = centroid.get("gdp_growth_p50", 0.0)
    approval = centroid.get("government_approval_p50", 0.0)
    severity = centroid.get("outcome_severity", 0.0)
    stability = centroid.get("political_stability_p50", 0.0)
    parts = [
        f"inflacion mediana {infl:.1f} %/mes",
        f"crecimiento mediano {growth:.1f} %",
        f"aprobacion mediana {approval:.0f}",
        f"estabilidad mediana {stability:.0f}",
    ]
    crisis_note = " (con crisis en el camino)" if severity > 0.3 else " (sin crisis)"
    return f"{int(centroid.get('n_runs', 0))} corridas -- " + ", ".join(parts) + crisis_note


def run_regimes(
    db_path: str | Path,
    *,
    k_range: tuple[int, int] = (3, 8),
    describe: bool = False,
) -> dict[str, Any]:
    """`republica ml regimes --db simulations/republica.duckdb [--describe]`
    (ADR 009 secc. 6/8): lee `runs`/`months`/... de `db_path`, agrupa en
    regimenes, y escribe la tabla `regimes` (idempotente: `DELETE` + insert,
    ya que un re-cluster puede cambiar `k`/las etiquetas de corridas viejas
    -- a diferencia de `experiment load`, ADR 008 secc. 3, esto no es un
    log append-only)."""
    con = open_db(db_path)
    con.execute(REGIMES_TABLE_SQL)
    vectors = build_vectors_from_db(con)
    if not vectors:
        con.close()
        return {"n_runs": 0, "k": 0, "silhouette": None, "centroids": []}

    result = fit_regimes(vectors, k_range=k_range)

    con.execute("DELETE FROM regimes")
    rows = [
        (
            v["run_id"],
            int(result.labels[i]),
            float(result.pc1[i]),
            float(result.pc2[i]),
            json.dumps({c: v.get(c) for c in _feature_columns()}, ensure_ascii=False),
        )
        for i, v in enumerate(vectors)
    ]
    for row in rows:
        con.execute("INSERT INTO regimes VALUES (?, ?, ?, ?, ?)", list(row))
    con.close()

    out = {
        "n_runs": len(vectors),
        "k": result.k,
        "silhouette": result.silhouette,
        "centroids": result.centroids,
    }
    if describe:
        out["descriptions"] = [
            {"cluster": c["cluster"], "sentence": describe_cluster(c)} for c in result.centroids
        ]
    return out


__all__ = [
    "TRAJECTORY_VARS",
    "RegimeResult",
    "build_vectors_from_db",
    "describe_cluster",
    "fit_regimes",
    "run_regimes",
]
