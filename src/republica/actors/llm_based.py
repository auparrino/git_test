"""Actor respaldado por un LLM (ADR 004 secc. 1): `LLMActor.decide(perception,
rng) -> list[Action]`, la misma interfaz que `actors/rule_based.py::
RuleBasedActor`. El LLM nunca ve `WorldState`, solo la `Perception` de su
rol (via `ai/prompts.py`); nunca devuelve acciones directamente, solo un
`ActorDecision` validado (via `ai/schemas.py`), convertido de forma
determinista por el motor."""

from __future__ import annotations

import random
import zlib

import pydantic

from republica.actors.sheet import ActorSheet
from republica.ai.backends import LLMBackend
from republica.ai.prompts import PROMPT_VERSION, render_system, render_user
from republica.ai.schemas import ActorDecision, to_actions
from republica.ai.tracing import DecisionTrace
from republica.engine.actions import Action, ActionType
from republica.engine.perception import Perception
from republica.engine.permissions import load_permissions

_ACTOR_DECISION_SCHEMA = ActorDecision.model_json_schema()


def _derive_call_seed(seed_base: int, month: int) -> int:
    """Semilla deterministica para `backend.complete(seed=...)`, derivada de
    `(seed_base, month)` -- SIN consumir el `rng` propio del actor (ver
    docstring de `LLMActor.decide`: es clave para que `FakeBackend(policy=
    "rules")` reproduzca exactamente la misma secuencia de azar que
    `RuleBasedActor.decide()` corrido directo, mes a mes)."""
    return zlib.crc32(f"{seed_base}:{month}".encode()) & 0x7FFFFFFF


class LLMActor:
    """`decide(perception, rng) -> list[Action]` (ADR 004 secc. 1). Misma
    interfaz que `RuleBasedActor`, para que `engine/scheduler.py` pueda usar
    cualquiera de los dos sin distinguir el tipo."""

    def __init__(
        self,
        sheet: ActorSheet,
        backend: LLMBackend,
        temperature: float = 0.4,
        seed_base: int = 0,
        permissions: dict[str, set[ActionType]] | None = None,
    ) -> None:
        self.sheet = sheet
        self.backend = backend
        self.temperature = temperature
        self.seed_base = seed_base
        self._permissions = permissions if permissions is not None else load_permissions()
        #: Paridad de interfaz con `RuleBasedActor.last_score` (ADR 003
        #: secc. 11 punto 27): `engine/scheduler.py` lo lee con `getattr`,
        #: siempre `None` aca (un `LLMActor` no calcula un `ScoreBreakdown`).
        self.last_score = None
        #: Efecto de lado leido por `engine/scheduler.py` despues de
        #: `decide()` (mismo patron que `last_score`): la `DecisionTrace` de
        #: la ultima llamada, con `run_id`/`actions_authorized`/
        #: `actions_denied`/`consequences` todavia sin completar (eso solo
        #: se sabe despues de `authorize_all`/`apply_consequences`).
        self.last_trace: DecisionTrace | None = None
        #: `ActorDecision.negotiation_reply`/`counter_concession` de la
        #: ultima llamada (ADR 005 secc. 2/deliverable 4), leidos por
        #: `engine/negotiation.py` si este actor pidio `NEGOTIATE` este mes:
        #: `None` (default, o si `decide()` nunca corrio -- rol sin
        #: propuesta, parseo fallido, etc.) hace que la negociacion caiga a
        #: la formula de aceptacion por reglas, igual que un `RuleBasedActor`.
        self.last_negotiation_reply: str | None = None
        self.last_counter_concession: str | None = None

    @property
    def brain_name(self) -> str:
        return f"llm:{getattr(self.backend, 'name', 'unknown')}"

    def decide(self, perception: Perception, rng: random.Random) -> list[Action]:
        """`rng` se pasa tal cual a `backend.complete()` (para que
        `FakeBackend(policy="rules")` pueda usarlo) pero `LLMActor` mismo no
        lo consume: la semilla del pedido al LLM sale de
        `_derive_call_seed(seed_base, perception.month)`, no de `rng.
        getrandbits(...)`. Si consumiera `rng` aca, la secuencia de azar que
        ve `RuleBasedActor.decide()` dentro de `FakeBackend("rules")` se
        correria un paso de mas respecto de una corrida `rules` pura, y
        divergirian a partir del segundo mes (ver Notas de implementacion)."""
        actor = self.sheet
        allowed_types = sorted(self._permissions.get(actor.role, set()), key=lambda t: t.value)
        system = render_system(actor)
        user = render_user(perception, allowed_types)
        seed = _derive_call_seed(self.seed_base, perception.month)

        result = self.backend.complete(
            system=system,
            user=user,
            schema=_ACTOR_DECISION_SCHEMA,
            temperature=self.temperature,
            seed=seed,
            actor_id=actor.id,
            perception=perception,
            rng=rng,
        )

        parse_error: str | None = None
        decision: ActorDecision | None = None
        if result.parsed is not None:
            try:
                decision = ActorDecision.model_validate(result.parsed)
            except pydantic.ValidationError as exc:
                parse_error = f"ActorDecision invalida: {exc}"
        else:
            parse_error = "no se pudo parsear JSON tras reintentos"

        if decision is None:
            actions: list[Action] = [
                Action(
                    type=ActionType.NO_ACTION,
                    actor_id=actor.id,
                    reason=f"fallo de parseo del LLM ({parse_error})",
                )
            ]
        else:
            actions = to_actions(decision, actor)

        self.last_negotiation_reply = decision.negotiation_reply if decision else None
        self.last_counter_concession = (
            decision.counter_concession.value if decision and decision.counter_concession else None
        )

        self.last_trace = DecisionTrace(
            run_id="",  # lo completa engine/scheduler.py (conoce el run_id de la corrida)
            month=perception.month,
            actor_id=actor.id,
            brain=self.brain_name,
            prompt_version=PROMPT_VERSION,
            model=result.model,
            digest=result.digest,
            temperature=self.temperature,
            seed=seed,
            perception=perception.model_dump(),
            system=system,
            user=user,
            raw_response=result.text,
            parsed=result.parsed,
            parse_error=parse_error,
            attempts=result.attempts,
            actions_emitted=[_action_summary(a) for a in actions],
            latency_ms=result.latency_ms,
            tokens={"prompt": result.prompt_tokens, "completion": result.completion_tokens},
        )
        return actions


def _action_summary(action: Action) -> dict[str, object]:
    type_value = action.type.value if isinstance(action.type, ActionType) else str(action.type)
    return {"type": type_value, "target": action.target, "params": action.params}
