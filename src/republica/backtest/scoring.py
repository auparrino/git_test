"""Objetivos y aciertos del backtest (ADR 014 secc. 2).

`score_window` produce, para una ventana ya corrida (ambos brazos), una
fila por `(arm, objetivo)` REALMENTE puntuado -- un objetivo sin dato real
en `t0+h` simplemente no genera fila (ADR 014 secc. 2 in fine: "solo se
puntuan objetivos con dato real en t0+h"; ADR 014 secc. 6 test 2). Nunca se
escribe `hit=NaN`: si no hay dato, no hay fila."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from republica.backtest.features import (
    _load_coup_dates,
    _load_election_dates,
    _load_events,
    _load_regimes_by_year,
    decade_inflation_std,
    real_inflation_monthly_equiv,
)
from republica.backtest.windows import Window
from republica.calibration.objective import REAL_ELECTION_OUTCOMES

OBJECTIVES: tuple[str, ...] = (
    "inflation_direction",
    "inflation_magnitude",
    "regime",
    "election",
    "crisis",
    "coup",
)

#: `events.csv` `kind` que cuentan como "crisis" (ADR 014 secc. 2, junto con
#: el `outcome` `hyperinflation`/`collapse` del modelo y `sovereign_default`
#: activo -- ver `_model_crisis_flags`).
CRISIS_EVENT_KINDS = frozenset({"hyperinflation", "default", "crisis_banking"})
CRISIS_SEED_THRESHOLD = 0.3
COUP_SEED_THRESHOLD = 0.3
#: Rango de origen `t0` para el objetivo "golpe" (ADR 014 secc. 2: "Golpe
#: (1916-1983)").
COUP_WINDOW_MAX_T0_YEAR = 1983


@dataclass
class SeedOutcome:
    """Lo que `scoring.py` necesita de UNA semilla de UN brazo (ver
    `runner.py::_history_to_outcome`/`_annual_history_to_outcome`)."""

    seed: int
    outcome: str
    months_run: int
    inflation_monthly: list[float]
    reserves: list[float]
    unemployment: list[float]
    regime_modes: list[str]
    shocks_active_union: frozenset[str]
    elections: list[dict]


def _sign(x: float, eps: float = 1e-9) -> int:
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0


def _iqr(values: list[float | None]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n < 2:
        return None

    def pct(q: float) -> float:
        pos = q * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        frac = pos - lo
        return vals[lo] * (1.0 - frac) + vals[hi] * frac

    return pct(0.75) - pct(0.25)


def _disagreement(flags: list[bool]) -> float | None:
    """Dispersion entre semillas para un objetivo BINARIO (ADR 014 secc. 3,
    "dispersion entre semillas (IQR)"): sin una magnitud continua, se usa
    la fraccion de semillas que NO acompaña a la mayoria (0 = unanime,
    0.5 = maxima discordia) como analogo declarado de la IQR."""
    if not flags:
        return None
    frac = sum(1 for f in flags if f) / len(flags)
    majority = frac >= 0.5
    return sum(1 for f in flags if f != majority) / len(flags)


def _last_value(values: list[float]) -> float | None:
    return values[-1] if values else None


def _real_crisis_in_window(t0: str, t_target: str) -> bool:
    y0, m0 = int(t0[:4]), int(t0[5:7])
    ty, tm = int(t_target[:4]), int(t_target[5:7])
    for row in _load_events():
        if row.get("kind") not in CRISIS_EVENT_KINDS:
            continue
        y, m = int(row["date"][:4]), int(row["date"][5:7])
        if (y0, m0) <= (y, m) <= (ty, tm):
            return True
    return any((y0, m0) <= (y, m) <= (ty, tm) for y, m in _load_coup_dates())


def _real_coup_in_window(t0: str, t_target: str) -> bool:
    y0, m0 = int(t0[:4]), int(t0[5:7])
    ty, tm = int(t_target[:4]), int(t_target[5:7])
    return any((y0, m0) <= (y, m) <= (ty, tm) for y, m in _load_coup_dates())


def _real_election_outcome_in_window(t0: str, t_target: str) -> tuple[int, str] | None:
    """Primera eleccion presidencial REAL dentro de `[t0, t_target]` cuyo
    año tiene resultado curado en `calibration/objective.py::
    REAL_ELECTION_OUTCOMES` (1989-2019 -- antes de 1989 no hay un mapeo
    confiable de "el ganador es/no es el oficialismo" en el repo, ver
    docstring de esa constante; se documenta como cobertura parcial, no
    se inventa un juicio de continuidad de coalicion para 1916-1988)."""
    y0, m0 = int(t0[:4]), int(t0[5:7])
    ty, tm = int(t_target[:4]), int(t_target[5:7])
    for y, m in sorted(_load_election_dates()):
        if (y0, m0) <= (y, m) <= (ty, tm) and y in REAL_ELECTION_OUTCOMES:
            return y, REAL_ELECTION_OUTCOMES[y]
    return None


def _model_election_outcome(runs: list[SeedOutcome], h: int) -> str | None:
    votes: list[str] = []
    for r in runs:
        held = [e for e in r.elections if e["month"] <= h]
        if held:
            votes.append(sorted(held, key=lambda e: e["month"])[0]["outcome_type"])
    if not votes:
        return None
    counts = {v: votes.count(v) for v in set(votes)}
    return max(counts, key=counts.get)


def _model_crisis_flags(runs: list[SeedOutcome]) -> list[bool]:
    return [
        r.outcome in ("hyperinflation", "collapse")
        or "sovereign_default" in r.shocks_active_union
        or "coup" in r.regime_modes
        for r in runs
    ]


def _model_coup_flags(runs: list[SeedOutcome]) -> list[bool]:
    return ["coup" in r.regime_modes for r in runs]


def score_window(
    window: Window,
    features: dict,
    runs_by_arm: dict[str, list[SeedOutcome]],
) -> list[dict]:
    y0, m0 = int(window.t0[:4]), int(window.t0[5:7])
    ty, tm = int(window.t_target[:4]), int(window.t_target[5:7])
    monthly = window.frequency == "monthly"

    real_t0 = real_inflation_monthly_equiv(y0, m0)
    real_target = real_inflation_monthly_equiv(ty, tm)
    decade_std = decade_inflation_std(y0)

    real_regime_target = _load_regimes_by_year().get(ty)
    real_crisis = _real_crisis_in_window(window.t0, window.t_target)
    real_coup = _real_coup_in_window(window.t0, window.t_target)
    real_election = _real_election_outcome_in_window(window.t0, window.t_target)

    rows: list[dict] = []
    for arm, runs in runs_by_arm.items():
        base = dict(features)
        base.update({"t0": window.t0, "h": window.h, "arm": arm})

        # -- direccion / magnitud de la inflacion ---------------------
        if real_t0 is not None and real_target is not None and runs:
            deltas = [
                _last_value(r.inflation_monthly) - r.inflation_monthly[0]
                for r in runs
                if r.inflation_monthly
            ]
            model_finals = [_last_value(r.inflation_monthly) for r in runs if r.inflation_monthly]
            if deltas:
                real_dir = _sign(real_target - real_t0)
                model_dir = _sign(statistics.median(deltas))
                rows.append(
                    {
                        **base,
                        "objective": "inflation_direction",
                        "hit": int(model_dir == real_dir),
                        "error": None,
                        "n_seeds": len(deltas),
                        "iqr_seeds": _iqr(deltas),
                    }
                )
            if model_finals:
                model_error = abs(statistics.median(model_finals) - real_target) / decade_std
                persistence_error = abs(real_t0 - real_target) / decade_std
                rows.append(
                    {
                        **base,
                        "objective": "inflation_magnitude",
                        "hit": int(model_error < persistence_error),
                        "error": model_error,
                        "n_seeds": len(model_finals),
                        "iqr_seeds": _iqr(model_finals),
                    }
                )

        # -- regimen (solo mensual: en modo anual regime_mode se lee
        # directo de `regimes.csv`, ver `runner.py` -- puntuarlo ahi seria
        # tautologico, no una prediccion) -----------------------------
        if monthly and real_regime_target is not None and runs:
            flags = [(_last_value(r.regime_modes) == "democracy") for r in runs]
            real_dem = real_regime_target == "democracy"
            model_majority = (sum(flags) / len(flags)) >= 0.5
            rows.append(
                {
                    **base,
                    "objective": "regime",
                    "hit": int(model_majority == real_dem),
                    "error": None,
                    "n_seeds": len(flags),
                    "iqr_seeds": _disagreement(flags),
                }
            )

        # -- eleccion dentro de la ventana ------------------------------
        if monthly and real_election is not None:
            model_outcome = _model_election_outcome(runs, window.h)
            if model_outcome is not None:
                rows.append(
                    {
                        **base,
                        "objective": "election",
                        "hit": int(model_outcome == real_election[1]),
                        "error": None,
                        "n_seeds": sum(
                            1 for r in runs if any(e["month"] <= window.h for e in r.elections)
                        ),
                        "iqr_seeds": None,
                    }
                )

        # -- crisis dentro de la ventana (incluye "no crisis") ----------
        if runs:
            flags = _model_crisis_flags(runs)
            frac = sum(flags) / len(flags)
            rows.append(
                {
                    **base,
                    "objective": "crisis",
                    "hit": int((frac >= CRISIS_SEED_THRESHOLD) == real_crisis),
                    "error": None,
                    "n_seeds": len(flags),
                    "iqr_seeds": _disagreement(flags),
                }
            )

            # -- golpe 1916-1983 (solo mensual: idem regimen) -----------
            if monthly and y0 <= COUP_WINDOW_MAX_T0_YEAR:
                coup_flags = _model_coup_flags(runs)
                coup_frac = sum(coup_flags) / len(coup_flags)
                rows.append(
                    {
                        **base,
                        "objective": "coup",
                        "hit": int((coup_frac >= COUP_SEED_THRESHOLD) == real_coup),
                        "error": None,
                        "n_seeds": len(coup_flags),
                        "iqr_seeds": _disagreement(coup_flags),
                    }
                )
    return rows
