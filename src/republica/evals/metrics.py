"""Las 10 metricas de la suite (ADR 007 secc. 2): 6 mecanicas
(`ideological_consistency`, `interest_consistency`, `authority_violation`,
`parse_rate`, `strategic_adaptation`, `diversity`) y 4 con juez
(`temporal_consistency`, `memory_recall`, `hallucination`,
`political_realism`). Cada una devuelve un `MetricResult`: valor, baseline
por reglas, N, IC 95 % (bootstrap) y los 5 peores casos con `trace_id`
(ADR secc. 4, literal)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from republica.actors.rule_based import make_actor_rng
from republica.actors.sheet import load_actors
from republica.ai.brains import build_decision_actor, parse_brain_spec
from republica.engine.actions import ActionType
from republica.evals import judge as judge_mod
from republica.evals.cases import EvalCase, build_actor, build_perception, decide_case
from republica.evals.judge import FakeJudge, Judge
from republica.evals.synthetic import LONG_MONTHS, SHOCK_MONTH, SHORT_MONTHS, tiny_run
from republica.world.config import load_country

BOOTSTRAP_ITERS = 1000


@dataclass
class WorstCase:
    """Uno de los 5 peores casos de una metrica (ADR secc. 4, literal:
    "los 5 peores casos con enlace a su traza")."""

    case_id: str
    detail: str
    trace_id: str | None = None


@dataclass
class MetricResult:
    id: str
    value: float | None
    baseline_rules: float | None
    n: int
    ci95: tuple[float, float] | None
    worst_cases: list[WorstCase] = field(default_factory=list)
    #: Aclaracion libre (ADR secc. 1: "una metrica sin baseline no se
    #: publica" -- una metrica sin datos, p.ej. `parse_rate` contra `rules`
    #: puro, se publica igual pero con `value=None` y esta nota explicando
    #: por que).
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "value": self.value,
            "baseline_rules": self.baseline_rules,
            "n": self.n,
            "ci95": list(self.ci95) if self.ci95 is not None else None,
            "worst_cases": [
                {"case_id": w.case_id, "detail": w.detail, "trace_id": w.trace_id}
                for w in self.worst_cases
            ],
            "note": self.note,
        }


def bootstrap_ci(
    samples: list[float], *, iters: int = BOOTSTRAP_ITERS, seed: int = 0
) -> tuple[float, float] | None:
    """IC 95 % por bootstrap (percentil 2.5/97.5) sobre `samples` (ADR secc.
    4, literal). `None` con menos de 2 muestras (un IC de un solo punto no
    dice nada)."""
    if len(samples) < 2:
        return None
    rng = random.Random(seed)
    n = len(samples)
    means = []
    for _ in range(iters):
        resample = [samples[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[min(iters - 1, int(0.975 * iters))]
    return (lo, hi)


def _mean(samples: list[float]) -> float | None:
    return sum(samples) / len(samples) if samples else None


# ---------------------------------------------------------------------------
# 1-2. ideological_consistency / interest_consistency (ADR secc. 2, casos)
# ---------------------------------------------------------------------------


def _run_case_trials(
    case: EvalCase, brain: str, base_seed: int, actors: dict, country
) -> list[Any]:
    """3 corridas del mismo caso con seeds distintos (ADR secc. 2: "se corre
    3 veces por caso con seeds distintos"): `base_seed + 0/1/2`, derivadas
    por `make_actor_rng` (mismo mecanismo de siempre, ADR 003 secc. 7) para
    que sean reproducibles."""
    sheet = build_actor(case, actors)
    out = []
    for i in range(3):
        trial_seed = base_seed + i
        brain_actor = build_decision_actor(brain, sheet, country, seed=trial_seed)
        rng = make_actor_rng(trial_seed, case.actor)
        out.append(decide_case(case, brain_actor, rng))
    return out


def _case_consistency_metric(
    metric_id: str, cases: list[EvalCase], brain: str, seed: int
) -> MetricResult:
    """Motor comun de `ideological_consistency`/`interest_consistency`: un
    caso "pasa" si `position` coincide con lo esperado en >= 2/3 corridas
    (ADR secc. 2, literal) y, cuando el caso declara `min_intensity`, la
    intensidad de esas corridas tambien la alcanza."""
    actors = load_actors()
    country = load_country()

    def score_with(b: str) -> tuple[list[float], list[WorstCase]]:
        samples: list[float] = []
        worst: list[WorstCase] = []
        for case in cases:
            trials = _run_case_trials(case, b, seed, actors, country)
            hits = sum(
                1
                for t in trials
                if t.position == case.expected.position
                and t.intensity >= case.expected.min_intensity
            )
            passed = hits >= 2
            samples.append(1.0 if passed else 0.0)
            if not passed:
                detail = (
                    f"esperado {case.expected.position} (min_intensity="
                    f"{case.expected.min_intensity}), obtuvo "
                    f"{[(t.position, round(t.intensity, 2)) for t in trials]}"
                )
                worst.append(WorstCase(case_id=case.id, detail=detail))
        return samples, worst

    samples, worst = score_with(brain)
    baseline_samples, _ = score_with("rules") if brain != "rules" else (samples, worst)
    value = _mean(samples)
    baseline = _mean(baseline_samples)
    return MetricResult(
        id=metric_id,
        value=value,
        baseline_rules=baseline,
        n=len(cases),
        ci95=bootstrap_ci(samples, seed=seed),
        worst_cases=worst[:5],
    )


def ideological_consistency(cases: list[EvalCase], brain: str, seed: int) -> MetricResult:
    return _case_consistency_metric("ideological_consistency", cases, brain, seed)


def interest_consistency(cases: list[EvalCase], brain: str, seed: int) -> MetricResult:
    return _case_consistency_metric("interest_consistency", cases, brain, seed)


# ---------------------------------------------------------------------------
# 3. authority_violation (ADR secc. 2: "acciones denegadas por rol /
#    acciones emitidas", del log de authorize -- mecanica).
# ---------------------------------------------------------------------------


def authority_violation(brain: str, seed: int) -> MetricResult:
    def ratio_for(b: str) -> tuple[float | None, int, list[WorstCase]]:
        history = tiny_run(b, seed, months=SHORT_MONTHS)
        total = len(history.action_records)
        if total == 0:
            return None, 0, []
        denied = [a for a in history.action_records if not a.authorized]
        worst = [
            WorstCase(
                case_id=f"{a.month:03d}:{a.actor}:{a.type}",
                detail=a.denied_reason or "denegado",
            )
            for a in denied[:5]
        ]
        return len(denied) / total, total, worst

    value, n, worst = ratio_for(brain)
    baseline, _, _ = ratio_for("rules") if brain != "rules" else (value, n, worst)
    return MetricResult(
        id="authority_violation",
        value=value,
        baseline_rules=baseline,
        n=n,
        ci95=None,
        worst_cases=worst,
    )


# ---------------------------------------------------------------------------
# 4. parse_rate (ADR secc. 2: "respuestas validas al primer intento /
#    llamadas", de las trazas -- mecanica). Sin trazas (brain "rules" puro,
#    RuleBasedActor no traza nada) el valor queda en None con nota (ADR
#    secc. 1: "una metrica sin baseline no se publica" -- aca se publica
#    igual, mas explicita, ver docstring de MetricResult).
# ---------------------------------------------------------------------------


def parse_rate(brain: str, seed: int) -> MetricResult:
    def ratio_for(b: str) -> tuple[float | None, int, list[WorstCase]]:
        history = tiny_run(b, seed, months=SHORT_MONTHS)
        traces = history.trace_records
        if not traces:
            return None, 0, []
        ok = [t for t in traces if t.attempts == 1 and t.parse_error is None]
        worst = [
            WorstCase(
                case_id=t.trace_id,
                detail=t.parse_error or f"{t.attempts} intentos",
                trace_id=t.trace_id,
            )
            for t in traces
            if t not in ok
        ][:5]
        return len(ok) / len(traces), len(traces), worst

    value, n, worst = ratio_for(brain)
    kind, _ = parse_brain_spec(brain)
    note = (
        ""
        if kind in ("fake", "llm")
        else "brain sin trazas (RuleBasedActor no traza); usar fake:*/llm:*"
    )
    baseline, _, _ = ratio_for("fake:rules") if kind == "rules" else (value, n, worst)
    return MetricResult(
        id="parse_rate",
        value=value,
        baseline_rules=baseline,
        n=n,
        ci95=None,
        worst_cases=worst,
        note=note,
    )


# ---------------------------------------------------------------------------
# 5. strategic_adaptation (ADR secc. 2, simplificado -- ver Notas de
#    implementacion de ADR 007: sin `private_strategy` para `RuleBasedActor`
#    ni test de proporciones formal (sin scipy/numpy en las dependencias),
#    se mide con el CONJUNTO de tipos de accion antes/despues del shock
#    -- "adapta" el actor cuya distribucion de tipos cambia (Jaccard entre
#    los dos conjuntos < 0.5) entre `t-3..t-1` y `t+1..t+3`.
# ---------------------------------------------------------------------------


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def strategic_adaptation(brain: str, seed: int) -> MetricResult:
    def value_for(b: str) -> tuple[float | None, int, list[WorstCase]]:
        history = tiny_run(
            b,
            seed,
            months=LONG_MONTHS,
            forced_shocks={SHOCK_MONTH: ["banking_crisis"]},
        )
        before_range = range(SHOCK_MONTH - 3, SHOCK_MONTH)
        after_range = range(SHOCK_MONTH + 1, SHOCK_MONTH + 4)
        by_actor_before: dict[str, set[str]] = {}
        by_actor_after: dict[str, set[str]] = {}
        for a in history.action_records:
            if a.type == ActionType.NO_ACTION.value:
                continue
            if a.month in before_range:
                by_actor_before.setdefault(a.actor, set()).add(a.type)
            elif a.month in after_range:
                by_actor_after.setdefault(a.actor, set()).add(a.type)
        actors_with_both = sorted(set(by_actor_before) & set(by_actor_after))
        if not actors_with_both:
            return None, 0, []
        adapted = []
        worst = []
        for actor_id in actors_with_both:
            before = by_actor_before[actor_id]
            after = by_actor_after[actor_id]
            sim = _jaccard(before, after)
            did_adapt = sim < 0.5
            adapted.append(1.0 if did_adapt else 0.0)
            if not did_adapt:
                worst.append(
                    WorstCase(
                        case_id=actor_id,
                        detail=f"antes={sorted(before)} despues={sorted(after)} (sin cambio)",
                    )
                )
        return _mean(adapted), len(actors_with_both), worst[:5]

    value, n, worst = value_for(brain)
    baseline, _, _ = value_for("rules") if brain != "rules" else (value, n, worst)
    return MetricResult(
        id="strategic_adaptation",
        value=value,
        baseline_rules=baseline,
        n=n,
        ci95=None,
        worst_cases=worst,
    )


# ---------------------------------------------------------------------------
# 6. diversity (ADR secc. 2: "distancia media entre decisiones de actores
#    distintos ante la misma percepcion"; 1 - acuerdo medio en position, mas
#    distancia Jaccard de actions. Se usan los casos ideologicos como las
#    "percepciones fijas" -- 20 percepciones ya escritas a mano, en vez de
#    inventar 20 mas solo para esta metrica -- y un subconjunto de 10
#    actores de rol variado).
# ---------------------------------------------------------------------------

_DIVERSITY_ACTORS = (
    "biz_finance",
    "biz_agro",
    "union_cgt",
    "gov_norte",
    "gov_capital",
    "party_movimiento_libertad",
    "party_frente_federal",
    "bloc_urban_workers",
    "bloc_rural",
    "minister_economy",
)


def diversity(cases: list[EvalCase], brain: str, seed: int) -> MetricResult:
    actors = load_actors()
    country = load_country()
    sheets = [actors[a] for a in _DIVERSITY_ACTORS if a in actors]

    def value_for(b: str) -> tuple[float | None, int, list[WorstCase]]:
        samples: list[float] = []
        worst: list[WorstCase] = []
        for case in cases:
            perception = build_perception(case)
            decisions = []
            for sheet in sheets:
                brain_actor = build_decision_actor(b, sheet, country, seed=seed)
                rng = make_actor_rng(seed, sheet.id)
                actions = brain_actor.decide(perception, rng)
                from republica.evals.cases import position_from_actions

                pos, _ = position_from_actions(actions)
                decisions.append((sheet.id, pos, {a.type.value for a in actions}))
            pairs = list(combinations(decisions, 2))
            if not pairs:
                continue
            pos_agree = sum(1 for (_, p1, _), (_, p2, _) in pairs if p1 == p2) / len(pairs)
            action_sim = sum(_jaccard(a1, a2) for (_, _, a1), (_, _, a2) in pairs) / len(pairs)
            case_diversity = 1.0 - (pos_agree + action_sim) / 2.0
            samples.append(case_diversity)
            if case_diversity < 0.15:
                worst.append(
                    WorstCase(
                        case_id=case.id,
                        detail=f"diversidad baja ({case_diversity:.2f}): "
                        f"{[(d[0], d[1]) for d in decisions]}",
                    )
                )
        return _mean(samples), len(samples), (samples, worst)

    value, n, (samples, worst) = value_for(brain)
    if brain != "rules":
        baseline, _, _ = value_for("rules")
    else:
        baseline = value
    return MetricResult(
        id="diversity",
        value=value,
        baseline_rules=baseline,
        n=n,
        ci95=bootstrap_ci(samples, seed=seed),
        worst_cases=worst[:5],
    )


# ---------------------------------------------------------------------------
# 7-10. Metricas con juez (ADR secc. 2/3).
# ---------------------------------------------------------------------------


def temporal_consistency(brain: str, judge: FakeJudge | Judge, seed: int) -> MetricResult:
    """% de reversiones de posicion (`support`<->`oppose` entre
    `ActionRecord` consecutivos del mismo actor, a lo sumo 3 meses de
    diferencia) cuyo `reason` menciona un evento ocurrido entre medio (ADR
    secc. 2, literal, con el fallback de match de strings del ADR --
    `FakeJudge.mentions_event`/`Judge` no aplica aca porque no hay prompt
    "RubricScore" natural para esto: se documenta como desviacion en Notas
    de implementacion)."""
    history = tiny_run(
        brain,
        seed,
        months=LONG_MONTHS,
        memory_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
    )
    by_actor: dict[str, list[Any]] = {}
    for a in history.action_records:
        if a.type in (ActionType.SUPPORT_POLICY.value, ActionType.OPPOSE_POLICY.value):
            by_actor.setdefault(a.actor, []).append(a)
    events_by_month: dict[int, list[str]] = {r.month_index: list(r.events) for r in history.records}

    samples: list[float] = []
    worst: list[WorstCase] = []
    for actor_id, records in by_actor.items():
        records.sort(key=lambda r: r.month)
        for i in range(len(records) - 1):
            a, b = records[i], records[i + 1]
            if b.month - a.month > 3 or b.month == a.month:
                continue
            if a.type == b.type:
                continue
            between: list[str] = []
            for m in range(a.month, b.month + 1):
                between.extend(events_by_month.get(m, []))
            mentions = judge_mod.mentions_event(b.reason, between)
            samples.append(1.0 if mentions else 0.0)
            if not mentions:
                worst.append(
                    WorstCase(
                        case_id=f"{actor_id}@{a.month}->{b.month}",
                        detail=f"{a.type}->{b.type} sin mencion de {between}: {b.reason!r}",
                    )
                )
    return MetricResult(
        id="temporal_consistency",
        value=_mean(samples),
        baseline_rules=None,
        n=len(samples),
        ci95=bootstrap_ci(samples, seed=seed) if samples else None,
        worst_cases=worst[:5],
        note="baseline por reglas no aplica (reversiones de posicion, no una corrida completa)",
    )


def memory_recall(brain: str, judge: FakeJudge | Judge, seed: int) -> MetricResult:
    """% de memorias `importance >= 0.8` que aparecen (match de strings) en
    el `reason`/`raw_response` de una accion del MISMO actor dentro de los 3
    turnos siguientes (ADR secc. 2, literal)."""
    history = tiny_run(
        brain,
        seed,
        months=LONG_MONTHS,
        memory_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
    )
    important = [m for m in history.memory_records if m.importance >= 0.8]
    if not important:
        return MetricResult(
            id="memory_recall",
            value=None,
            baseline_rules=None,
            n=0,
            ci95=None,
            note="sin memorias importance>=0.8 en esta corrida sintetica",
        )
    texts_by_actor_month: dict[str, dict[int, list[str]]] = {}
    for a in history.action_records:
        texts_by_actor_month.setdefault(a.actor, {}).setdefault(a.month, []).append(a.reason)
    for t in history.trace_records:
        texts_by_actor_month.setdefault(t.actor_id, {}).setdefault(t.month, []).append(
            t.raw_response or ""
        )

    samples: list[float] = []
    worst: list[WorstCase] = []
    for mem in important:
        owner_texts = texts_by_actor_month.get(mem.actor, {})
        window = [
            text for m in range(mem.turn + 1, mem.turn + 4) for text in owner_texts.get(m, [])
        ]
        found = any(judge_mod.mentions_event(t, [mem.summary]) for t in window)
        samples.append(1.0 if found else 0.0)
        if not found:
            worst.append(
                WorstCase(
                    case_id=f"{mem.actor}@{mem.turn}",
                    detail=f"no recuperada: {mem.summary!r}",
                )
            )
    return MetricResult(
        id="memory_recall",
        value=_mean(samples),
        baseline_rules=None,
        n=len(samples),
        ci95=bootstrap_ci(samples, seed=seed),
        worst_cases=worst[:5],
        note="baseline por reglas no aplica (RuleBasedActor no redacta reasoning en texto libre)",
    )


def hallucination(brain: str, judge: FakeJudge | Judge, seed: int) -> MetricResult:
    """Tasa de afirmaciones numericas del `raw_response` de cada traza no
    respaldadas por su propia `perception` (ADR secc. 2/3, literal). Sin
    trazas (brain `rules` puro) no hay texto libre que chequear: `N=0`."""
    from republica.evals.judge import dump_perception_numbers

    history = tiny_run(brain, seed, months=SHORT_MONTHS)
    if not history.trace_records:
        return MetricResult(
            id="hallucination",
            value=None,
            baseline_rules=None,
            n=0,
            ci95=None,
            note="brain sin trazas (RuleBasedActor no redacta texto libre); usar fake:*/llm:*",
        )
    samples: list[float] = []
    worst: list[WorstCase] = []
    for trace in history.trace_records:
        text = trace.raw_response or ""
        if not text.strip():
            continue
        numbers = dump_perception_numbers(trace.perception)
        if isinstance(judge, FakeJudge):
            fc = judge.fact_check(numbers, text)
        else:
            from republica.evals.prompts import render_fact_check_prompt

            system, user = render_fact_check_prompt(numbers, text)
            fc = judge.fact_check(system=system, user=user)
        rate = fc.unsupported_rate
        if rate is None:
            continue
        samples.append(rate)
        if rate > 0.0:
            worst.append(
                WorstCase(
                    case_id=trace.trace_id, detail=f"tasa={rate:.2f}", trace_id=trace.trace_id
                )
            )
    worst.sort(key=lambda w: w.detail, reverse=True)
    return MetricResult(
        id="hallucination",
        value=_mean(samples),
        baseline_rules=None,
        n=len(samples),
        ci95=bootstrap_ci(samples, seed=seed) if samples else None,
        worst_cases=worst[:5],
        note="baseline por reglas no aplica (RuleBasedActor no redacta texto libre)",
    )


def political_realism(brain: str, judge: FakeJudge | Judge, seed: int) -> MetricResult:
    """Score 1-5 del juez sobre la corrida sintetica larga, via la rubrica
    de `data/evals/rubrics/realism.md` (ADR secc. 2/3)."""
    from republica.evals.prompts import render_realism_prompt
    from republica.evals.synthetic import emergence_report

    history = tiny_run(
        brain, seed, months=LONG_MONTHS, congress_enabled=True, negotiation_enabled=True
    )
    report = emergence_report(history)
    negotiations = [n.to_dict() for n in history.negotiation_records[:10]]

    if isinstance(judge, FakeJudge):
        signals = {
            "alianzas_coherentes": bool(report.alliances),
            "coaliciones_repetidas": bool(report.repeated_coalitions),
            "negociaciones_con_concesion": any(n.get("agreement") for n in negotiations),
            "diversidad_de_pedidos": len({n.get("requested_concession") for n in negotiations}) > 1,
            "sin_acuerdos_rotos_excesivos": len(report.broken_agreements)
            <= max(1, len(negotiations) // 2),
        }
        rs = judge.rubric_score(signals)
    else:
        system, user = render_realism_prompt(report.to_dict(), negotiations)
        rs = judge.rubric_score(system=system, user=user)

    return MetricResult(
        id="political_realism",
        value=float(rs.score),
        baseline_rules=None,
        n=1,
        ci95=None,
        worst_cases=[] if rs.score >= 3 else [WorstCase(case_id="run", detail=rs.justification)],
        note=rs.justification,
    )
