"""Juez de evals (ADR 007 secc. 3): `FakeJudge` (reglas de strings/numeros,
sin red, la que corre en CI) y `Judge(backend)` (cualquier `LLMBackend` de
`ai/backends.py` -- Ollama real, o cualquier otro que se agregue despues --
con salida siempre tipada por `FactCheck`/`RubricScore`).

Regla dura (ADR 007 secc. 3, literal): "el juez es un modelo distinto al
evaluado" -- `build_judge()` la hace cumplir comparando el modelo del juez
contra el `brain` del actor evaluado y aborta (`ValueError`) si coinciden.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from republica.ai.backends import LLMBackend
from republica.ai.brains import build_backend, parse_brain_spec

ClaimKind = Literal["numeric", "event", "opinion"]
Verdict = Literal["supported", "unsupported"]


class Claim(BaseModel):
    """ADR 007 secc. 3, literal."""

    model_config = ConfigDict(extra="forbid")

    text: str
    kind: ClaimKind
    verdict: Verdict


class FactCheck(BaseModel):
    """ADR 007 secc. 3, literal: usado por `hallucination`."""

    model_config = ConfigDict(extra="forbid")

    claims: list[Claim] = Field(default_factory=list)

    @property
    def unsupported_rate(self) -> float | None:
        """`unsupported / (supported + unsupported)` (ADR secc. 2, formula
        literal de `hallucination`); `None` (sin afirmaciones factuales, o
        solo `opinion`) para que el llamador lo excluya del promedio en vez
        de contarlo como 0 % de alucinacion."""
        numeric = [c for c in self.claims if c.kind in ("numeric", "event")]
        if not numeric:
            return None
        unsupported = sum(1 for c in numeric if c.verdict == "unsupported")
        return unsupported / len(numeric)


class RubricScore(BaseModel):
    """ADR 007 secc. 3, literal: usado por `political_realism` (y por
    `temporal_consistency`/`memory_recall` como juez de si una `reasoning`
    "menciona" un evento -- ver `evals/metrics.py`)."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5)
    justification: str = ""


# ---------------------------------------------------------------------------
# FakeJudge: reglas de strings/numeros (ADR 007 secc. 3, literal: "en CI
# corre con FakeJudge (reglas de strings) para que la tuberia este
# testeada"). Sin LLM, sin red, determinista.
# ---------------------------------------------------------------------------

#: Numeros con hasta 2 decimales (ADR secc. 3, test 4: "detecta una
#: afirmacion numerica inventada"): cubre enteros y decimales, con o sin
#: signo, tal como aparecen en `reasoning`/`public_message` (p.ej. "8.5",
#: "-3", "48%").
_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")

#: Tolerancia relativa para considerar que un numero del texto "esta
#: respaldado" por un numero de la percepcion (ADR no da una cifra: un
#: actor redondea/aproxima, no cita el dato con precision infinita --
#: documentado en Notas de implementacion). 5 % o 0.5 unidades absolutas,
#: lo que sea mayor (para que un numero chico como "2.1" de inflacion no
#: exija una tolerancia ridicula de 0.1).
_REL_TOLERANCE = 0.05
_ABS_TOLERANCE = 0.5


@dataclass
class FakeJudge:
    """ADR 007 secc. 3: reglas de strings/numeros, sin backend. `name` se
    compara contra el `brain` evaluado en `build_judge` (nunca coincide con
    un `rules`/`fake:*`/`llm:*`: la regla dura solo aplica entre DOS
    backends de LLM, ver docstring de `build_judge`)."""

    name: str = "fake"

    def fact_check(self, perception_numbers: list[float], text: str) -> FactCheck:
        """Extrae cada numero de `text` como una `Claim` `kind="numeric"`:
        `supported` si algun numero de `perception_numbers` cae dentro de
        tolerancia, `unsupported` si no (ADR secc. 2: "numero que no esta en
        la percepcion" -- test 4 de ADR secc. 7 literal)."""
        claims: list[Claim] = []
        for match in _NUMBER_RE.finditer(text):
            raw = match.group().replace(",", ".")
            try:
                value = float(raw)
            except ValueError:
                continue
            supported = any(
                abs(value - p) <= max(_ABS_TOLERANCE, abs(p) * _REL_TOLERANCE)
                for p in perception_numbers
            )
            claims.append(
                Claim(
                    text=raw,
                    kind="numeric",
                    verdict="supported" if supported else "unsupported",
                )
            )
        return FactCheck(claims=claims)

    def mentions_event(self, text: str, event_summaries: list[str]) -> bool:
        """`True` si `text` menciona (substring, case-insensitive, por
        palabra clave de >= 4 letras) alguno de `event_summaries` -- fallback
        de string matching de `temporal_consistency`/`memory_recall` (ADR
        secc. 2, literal: "match por `MemoryEvent.summary`...")."""
        low = text.lower()
        for summary in event_summaries:
            found_words = re.findall(r"[a-zA-ZñÑáéíóúÁÉÍÓÚ]+", summary.lower())
            words = [w for w in found_words if len(w) >= 4]
            if words and sum(1 for w in words if w in low) >= max(1, len(words) // 3):
                return True
        return False

    def rubric_score(self, signals: dict[str, bool]) -> RubricScore:
        """Puntaje 1-5 = 1 + cuantas senales de `signals` son `True` (ADR
        secc. 3: rubrica de 5 puntos, ver `data/evals/rubrics/realism.md`).
        Heuristica, no un juicio real -- documentado en Notas de
        implementacion: sirve para probar la tuberia (ADR secc. 3, literal),
        no para calificar realismo politico de verdad."""
        score = 1 + sum(1 for v in signals.values() if v)
        justification = "FakeJudge (heuristica de banderas): " + ", ".join(
            f"{k}={'si' if v else 'no'}" for k, v in signals.items()
        )
        return RubricScore(score=min(5, score), justification=justification)


# ---------------------------------------------------------------------------
# Judge: cualquier LLMBackend real (ADR 007 secc. 3).
# ---------------------------------------------------------------------------


@dataclass
class Judge:
    """`Judge(backend)` (ADR 007 secc. 3, literal): pide `FactCheck`/
    `RubricScore` via `backend.complete(schema=...)` (mismo mecanismo que
    `LLMActor` usa para `ActorDecision`, ADR 004 secc. 2) y valida la
    respuesta contra el esquema pydantic correspondiente."""

    backend: LLMBackend

    @property
    def name(self) -> str:
        return getattr(self.backend, "name", "llm")

    def fact_check(self, system: str, user: str, *, seed: int = 0) -> FactCheck:
        result = self.backend.complete(
            system=system,
            user=user,
            schema=FactCheck.model_json_schema(),
            temperature=0.0,
            seed=seed,
        )
        if result.parsed is None:
            return FactCheck(claims=[])
        return FactCheck.model_validate(result.parsed)

    def rubric_score(self, system: str, user: str, *, seed: int = 0) -> RubricScore:
        result = self.backend.complete(
            system=system,
            user=user,
            schema=RubricScore.model_json_schema(),
            temperature=0.0,
            seed=seed,
        )
        if result.parsed is None:
            return RubricScore(score=1, justification="el juez no devolvio JSON valido")
        return RubricScore.model_validate(result.parsed)


def _judge_model_name(spec: str) -> str:
    kind, rest = parse_brain_spec(spec)
    return rest or kind


def build_judge(spec: str, *, actor_brain: str) -> FakeJudge | Judge:
    """`spec` en `fake|llm:ollama:<modelo>|llm:anthropic:<modelo>` (ADR
    secc. 3). Regla dura (secc. 3, literal): "el juez es un modelo distinto
    al evaluado" -- si `spec` y `actor_brain` son AMBOS `llm:*` con el mismo
    modelo, aborta. `fake` (default, el que corre en CI) nunca choca: no es
    un modelo real, es la tuberia de reglas que prueba que el resto del
    sistema funciona (ADR secc. 3, literal)."""
    if spec == "fake":
        return FakeJudge()
    judge_kind, _ = parse_brain_spec(spec)
    actor_kind, _ = parse_brain_spec(actor_brain)
    if judge_kind == "llm" and actor_kind == "llm" and _judge_model_name(spec) == _judge_model_name(
        actor_brain
    ):
        raise ValueError(
            f"juez invalido: --judge {spec!r} usa el MISMO modelo que --brain {actor_brain!r} "
            "(ADR 007 secc. 3: el juez debe ser un modelo distinto al evaluado)"
        )
    if judge_kind != "llm":
        raise ValueError(f"--judge desconocido: {spec!r} (usar fake|llm:ollama:<modelo>)")
    backend = build_backend(spec, cache_dir=None)
    return Judge(backend)


def mentions_event(text: str, event_summaries: list[str]) -> bool:
    """Match de strings, libre de juez (ADR secc. 2, literal: fallback
    explicito de `temporal_consistency`/`memory_recall` -- "pasa si
    `reasoning` ... menciona un evento ... (fallback: match de strings)").
    Se usa siempre para estas dos metricas, tenga `--judge` el valor que
    tenga: el ADR mismo las excluye de necesitar un LLM de verdad."""
    return FakeJudge().mentions_event(text, event_summaries)


def dump_perception_numbers(perception_dict: dict) -> list[float]:
    """Todos los numeros de `public_indicators`/`private_indicators` de una
    `Perception` serializada (ADR secc. 3: lo que el juez de `hallucination`
    recibe como "la percepcion" para chequear afirmaciones numericas)."""
    out: list[float] = []
    for key in ("public_indicators", "private_indicators"):
        for value in (perception_dict.get(key) or {}).values():
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                continue
    return out


def perception_numbers_json(perception_dict: dict) -> str:
    return json.dumps(dump_perception_numbers(perception_dict))
