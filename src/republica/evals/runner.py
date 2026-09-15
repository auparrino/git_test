"""`run_suite()` (ADR 007 secc. 4): junta los 10 `MetricResult` de
`evals/metrics.py` en un `Report` (`evals/report.py`). Punto de entrada de
`republica eval --suite all|<id> --brain ... --judge ... --out ...`."""

from __future__ import annotations

from republica.evals import metrics as m
from republica.evals.cases import load_cases
from republica.evals.judge import build_judge
from republica.evals.report import Report

#: `id`s de las 10 metricas de la suite (ADR secc. 2, orden de la tabla).
METRIC_IDS: tuple[str, ...] = (
    "ideological_consistency",
    "interest_consistency",
    "authority_violation",
    "parse_rate",
    "strategic_adaptation",
    "diversity",
    "temporal_consistency",
    "memory_recall",
    "hallucination",
    "political_realism",
)

#: Alias cortos que acepta `--suite` ademas del `id` completo (ADR secc. 4:
#: `--suite all|ideological|interest|...` -- el docstring del ADR usa la
#: forma corta de las dos metricas de casos, no el `id` completo de la
#: tabla de secc. 2).
_SUITE_ALIASES: dict[str, str] = {
    "ideological": "ideological_consistency",
    "interest": "interest_consistency",
}


def _normalize_suite(suite: str) -> str:
    if suite == "all":
        return "all"
    normalized = _SUITE_ALIASES.get(suite, suite)
    if normalized not in METRIC_IDS:
        raise ValueError(
            f"suite desconocida: {suite!r} (usar 'all' o una de {METRIC_IDS}, "
            f"o los alias {sorted(_SUITE_ALIASES)})"
        )
    return normalized


def run_suite(*, suite: str, brain: str, judge: str, seed: int) -> Report:
    """Corre `suite` (`"all"` o el `id`/alias de UNA metrica) contra `brain`,
    con `judge` para las 4 metricas que lo necesitan (ADR secc. 1/4: "todo
    eval corre igual contra rules, fake:rules y cualquier llm:*"). La regla
    dura del juez (secc. 3) se chequea una sola vez aca, antes de correr
    nada: si `--judge llm:X` y `--brain llm:X` son el mismo modelo,
    `build_judge` levanta `ValueError` (el runner no corre metricas a
    medias)."""
    normalized = _normalize_suite(suite)
    judge_obj = build_judge(judge, actor_brain=brain)

    cases = load_cases()
    ideological_cases = [c for c in cases if c.kind == "ideological"]
    interest_cases = [c for c in cases if c.kind == "interest"]

    want = METRIC_IDS if normalized == "all" else (normalized,)
    results = []
    for metric_id in want:
        if metric_id == "ideological_consistency":
            results.append(m.ideological_consistency(ideological_cases, brain, seed))
        elif metric_id == "interest_consistency":
            results.append(m.interest_consistency(interest_cases, brain, seed))
        elif metric_id == "authority_violation":
            results.append(m.authority_violation(brain, seed))
        elif metric_id == "parse_rate":
            results.append(m.parse_rate(brain, seed))
        elif metric_id == "strategic_adaptation":
            results.append(m.strategic_adaptation(brain, seed))
        elif metric_id == "diversity":
            results.append(m.diversity(ideological_cases, brain, seed))
        elif metric_id == "temporal_consistency":
            results.append(m.temporal_consistency(brain, judge_obj, seed))
        elif metric_id == "memory_recall":
            results.append(m.memory_recall(brain, judge_obj, seed))
        elif metric_id == "hallucination":
            results.append(m.hallucination(brain, judge_obj, seed))
        elif metric_id == "political_realism":
            results.append(m.political_realism(brain, judge_obj, seed))

    return Report(brain=brain, judge=judge, seed=seed, suite=suite, metrics=results)
