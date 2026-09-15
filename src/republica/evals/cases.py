"""Casos de eval (ADR 007 secc. 2, formato literal): `data/evals/cases/
{ideological,interest}/*.yaml`. Un caso fija UN actor (con overrides
opcionales de ficha) y UNA percepcion sintetica (sin pasar por una corrida
completa: el eval mide la decision aislada del agente ante un estimulo
fijo), mas la posicion esperada.

Se construye la `Perception` "a mano" (no via `engine/perception.py::
build_perception`, que necesita un `WorldState` completo): un caso solo
declara los indicadores que le importan a la ideologia/interes en juego
(ADR secc. 2, formato literal: `public_indicators: {inflation, unemployment,
government_approval}`); el resto cae a los defaults de
`actors/rule_based.py` (`dict.get(key, default)` en cada `_impact_*`), que
es exactamente lo que veria un actor real si esos indicadores no vinieran
en su percepcion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from republica.actors.sheet import ActorSheet, load_actors
from republica.engine.perception import Perception, PolicyProposal

DEFAULT_CASES_DIR = Path(__file__).resolve().parents[3] / "data" / "evals" / "cases"

#: `months_to_election` default de un caso (ADR secc. 2 no lo pide en el
#: formato, pero `compute_score` lo necesita): 30 deja `electoral_pressure`
#: en 0 (`clamp(1 - 30/12, 0, 1) == 0`), asi que un caso no se contamina con
#: presion electoral salvo que declare `perception.months_to_election`
#: explicitamente (para el puñado de casos que SI quieren probarla).
DEFAULT_MONTHS_TO_ELECTION = 30

Position = Literal["support", "oppose", "neutral", "negotiate"]


class CaseOverrides(BaseModel):
    """`overrides` de un caso (ADR secc. 2, literal): parches sobre la ficha
    real del actor. `ideology`/`personality` son merges parciales (solo los
    campos declarados cambian); `interests`/`party` reemplazan el valor
    entero de la ficha."""

    model_config = ConfigDict(extra="forbid")

    ideology: dict[str, float] = Field(default_factory=dict)
    personality: dict[str, float] = Field(default_factory=dict)
    interests: list[str] | None = None
    party: str | None = None


class CaseProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_delta: dict[str, float] = Field(default_factory=dict)
    label: str = ""


class CasePerception(BaseModel):
    """`perception` de un caso (ADR secc. 2, literal, mas 2 campos optativos
    documentados arriba)."""

    model_config = ConfigDict(extra="forbid")

    proposal: CaseProposal | None = None
    public_indicators: dict[str, float] = Field(default_factory=dict)
    private_indicators: dict[str, float] = Field(default_factory=dict)
    relationships: dict[str, int] = Field(default_factory=dict)
    months_to_election: int = DEFAULT_MONTHS_TO_ELECTION
    active_shocks: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)


class CaseExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Position
    min_intensity: float = 0.0


class EvalCase(BaseModel):
    """Un caso (ADR secc. 2, formato literal)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    actor: str
    overrides: CaseOverrides = Field(default_factory=CaseOverrides)
    perception: CasePerception = Field(default_factory=CasePerception)
    expected: CaseExpected
    rationale: str = ""
    #: `human | generated` (ADR secc. 2, literal): los `author: human` estan
    #: reservados para que los agregue una persona (ver docstring del
    #: modulo `evals/runner.py`); todos los que genera este agente van con
    #: `author: generated` (instruccion de la tarea, reemplaza el test 1
    #: literal del ADR -- ver Notas de implementacion).
    author: Literal["human", "generated"] = "generated"
    #: Categoria del caso (`ideological`/`interest`), la fija `load_cases`
    #: por el subdirectorio de origen, no el YAML (evita que un caso mienta
    #: sobre en que carpeta esta).
    kind: str = ""


def _load_one(path: Path, kind: str) -> EvalCase:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw["kind"] = kind
    return EvalCase.model_validate(raw)


def load_cases(kind: str | None = None, cases_dir: str | Path | None = None) -> list[EvalCase]:
    """Carga los casos de `cases_dir` (default `data/evals/cases/`).
    `kind` en `{"ideological", "interest"}` limita a un subdirectorio; `None`
    (default) carga los dos. Orden estable por `id` (reproducibilidad de
    reportes)."""
    base = Path(cases_dir) if cases_dir is not None else DEFAULT_CASES_DIR
    kinds = [kind] if kind else ["ideological", "interest"]
    cases: list[EvalCase] = []
    for k in kinds:
        d = base / k
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.yaml")):
            cases.append(_load_one(path, k))
    return sorted(cases, key=lambda c: c.id)


def build_actor(case: EvalCase, actors: dict[str, ActorSheet] | None = None) -> ActorSheet:
    """Aplica `case.overrides` sobre la ficha real de `case.actor` (ADR
    secc. 2: "overrides ... sobre la ficha")."""
    actors = actors if actors is not None else load_actors()
    sheet = actors[case.actor]
    updates: dict[str, Any] = {}
    ov = case.overrides
    if ov.ideology:
        updates["ideology"] = sheet.ideology.model_copy(update=ov.ideology)
    if ov.personality:
        updates["personality"] = sheet.personality.model_copy(update=ov.personality)
    if ov.interests is not None:
        updates["interests"] = list(ov.interests)
    if ov.party is not None:
        updates["party"] = ov.party
    return sheet.model_copy(update=updates) if updates else sheet


def build_perception(case: EvalCase) -> Perception:
    """Arma la `Perception` sintetica de `case.perception` (ADR secc. 2)."""
    p = case.perception
    proposal = None
    if p.proposal is not None and (p.proposal.policy_delta or p.proposal.label):
        proposal = PolicyProposal(delta=dict(p.proposal.policy_delta), label=p.proposal.label)
    return Perception(
        month=1,
        date="",
        months_to_election=p.months_to_election,
        public_indicators=dict(p.public_indicators),
        private_indicators=dict(p.private_indicators),
        proposal=proposal,
        active_shocks=list(p.active_shocks),
        recent_events=list(p.recent_events),
        relationships=dict(p.relationships),
        memories=[],
        goals=[],
        memory_score=0.0,
    )


@dataclass(frozen=True)
class CaseDecision:
    """Resultado de correr un `EvalCase` contra un cerebro (ADR secc. 2):
    `position` derivada de las `Action` emitidas (no de un campo de score
    interno -- asi un `LLMActor`/`FakeBackend` cualquiera se juzga igual que
    `RuleBasedActor`, por sus acciones, que es lo unico que el motor ve de
    verdad de un actor)."""

    case_id: str
    position: Position
    intensity: float
    actions: list[str] = field(default_factory=list)
    raw_score: float | None = None


def position_from_actions(actions: list[Any]) -> tuple[Position, float]:
    """`(position, intensity)` a partir de la lista de `Action` que un actor
    emitio ante la percepcion de un caso (ADR secc. 2: `position ∈ {support,
    oppose}` para los casos "claros"; se agregan `neutral`/`negotiate` para
    no forzar un caso ambiguo a mentir). `intensity` es el maximo de
    `params["intensity"]` entre las acciones de posicion (0.0 si no hay)."""
    from republica.engine.actions import ActionType

    support_types = {ActionType.SUPPORT_POLICY}
    oppose_types = {
        ActionType.OPPOSE_POLICY,
        ActionType.STRIKE,
        ActionType.CALL_PROTEST,
        ActionType.WITHHOLD_INVESTMENT,
    }
    negotiate_types = {ActionType.NEGOTIATE}
    intensity = 0.0
    position: Position = "neutral"
    for action in actions:
        val = float(action.params.get("intensity", 0.0)) if action.params else 0.0
        if action.type in support_types:
            position = "support"
            intensity = max(intensity, val)
        elif action.type in oppose_types:
            if position != "support":
                position = "oppose"
            intensity = max(intensity, val)
        elif action.type in negotiate_types and position == "neutral":
            position = "negotiate"
    return position, intensity


def decide_case(
    case: EvalCase,
    brain_actor: Any,
    rng: Any,
) -> CaseDecision:
    """Corre `brain_actor.decide(perception, rng)` (misma interfaz que
    `RuleBasedActor`/`LLMActor`) sobre la percepcion sintetica de `case` y
    resume el resultado en un `CaseDecision`."""
    perception = build_perception(case)
    actions = brain_actor.decide(perception, rng)
    position, intensity = position_from_actions(actions)
    raw_score = None
    last_score = getattr(brain_actor, "last_score", None)
    if last_score is not None:
        raw_score = float(last_score.total)
    return CaseDecision(
        case_id=case.id,
        position=position,
        intensity=intensity,
        actions=[a.type.value for a in actions],
        raw_score=raw_score,
    )
