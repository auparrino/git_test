"""Configuracion de cerebros de actor (ADR 004 secc. 7): que decide cada
actor -- reglas o un LLM (real o fake) -- y como se arma el objeto que
implementa `decide(perception, rng) -> list[Action]` a partir de un string
de especificacion (`"rules"`, `"fake:rules"`, `"llm:ollama:<model>"`, ...).

No forma parte de los 4 modulos que pide el deliverable 1 de ADR 004
(`ai/backends.py`/`ai/schemas.py`/`ai/prompts.py`/`ai/tracing.py`), pero
hace falta un lugar central para leer `data/brains.yaml`/`--brains` (ADR 004
secc. 7/8, deliverable 6) sin repetir el parseo de specs de cerebro entre
`engine/scheduler.py` y `cli.py`: se agrega aca, documentado en Notas de
implementacion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from republica.actors.llm_based import LLMActor
from republica.actors.rule_based import RuleBasedActor, actor_seed
from republica.actors.sheet import ActorSheet
from republica.ai.backends import CachedBackend, FakeBackend, LLMBackend, OllamaBackend
from republica.world.config import Country

DEFAULT_BRAINS_PATH = Path(__file__).resolve().parents[3] / "data" / "brains.yaml"

#: Cerebro por defecto si no se pide nada (ADR 004 secc. 7): reglas para
#: todos, cero LLM.
DEFAULT_BRAIN = "rules"

#: Specs de `FakeBackend` que acepta `--brain`/`data/brains.yaml`
#: directamente (ADR 004 secc. 7/8): `fake:<policy>`. `fake:scripted` queda
#: fuera de la CLI (necesita un guion por actor/mes que no tiene forma
#: simple de pasarse por linea de comandos); sigue disponible construyendo
#: un `FakeBackend("scripted", scripted={...})` a mano (tests).
_FAKE_POLICIES = ("rules", "malformed", "unauthorized")


@dataclass
class BrainsConfig:
    """Lo que carga `data/brains.yaml`/`--brains` (ADR 004 secc. 7)."""

    default: str = DEFAULT_BRAIN
    actors: dict[str, str] = field(default_factory=dict)
    temperature: float = 0.4
    cache_dir: str | None = None

    def brain_for(self, actor_id: str) -> str:
        return self.actors.get(actor_id, self.default)


def load_brains_config(path: str | Path | None = None) -> BrainsConfig:
    """Carga `data/brains.yaml` (o `path`). Formato (ADR 004 secc. 7):
    `{default: "rules", actors: {id: brain}, llm: {temperature, cache}}`."""
    p = Path(path) if path is not None else DEFAULT_BRAINS_PATH
    raw: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    llm_cfg = raw.get("llm") or {}
    return BrainsConfig(
        default=raw.get("default", DEFAULT_BRAIN),
        actors=dict(raw.get("actors") or {}),
        temperature=float(llm_cfg.get("temperature", 0.4)),
        cache_dir=llm_cfg.get("cache"),
    )


def parse_brain_spec(spec: str) -> tuple[str, str | None]:
    """`"rules"` -> `("rules", None)`; `"fake:rules"` -> `("fake", "rules")`;
    `"llm:ollama:qwen3:8b"` -> `("llm", "ollama:qwen3:8b")`."""
    if ":" not in spec:
        return spec, None
    kind, _, rest = spec.partition(":")
    return kind, rest


def build_backend(
    spec: str, *, cache_dir: str | Path | None, memory_enabled: bool = False
) -> LLMBackend:
    """`spec` sin el caso `"rules"` (eso no usa backend, ver
    `build_decision_actor`): `"fake:<policy>"` o `"llm:ollama:<model>"`.
    `memory_enabled` (ADR 006 secc. 1.3) solo importa para `fake:rules`, que
    envuelve un `RuleBasedActor` real."""
    kind, rest = parse_brain_spec(spec)
    backend: LLMBackend
    if kind == "fake":
        policy = rest or "rules"
        if policy not in _FAKE_POLICIES:
            raise ValueError(
                f"policy de FakeBackend desconocida en '{spec}': {policy!r} "
                f"(usar {_FAKE_POLICIES} desde la CLI, o construir FakeBackend a mano)"
            )
        backend = FakeBackend(policy=policy, memory_enabled=memory_enabled)
    elif kind == "llm":
        if not rest or ":" not in rest:
            raise ValueError(f"brain llm mal formado: {spec!r} (usar llm:ollama:<modelo>)")
        provider, _, model = rest.partition(":")
        if provider != "ollama":
            raise ValueError(f"proveedor LLM desconocido en '{spec}': {provider!r} (solo 'ollama')")
        backend = OllamaBackend(model=model)
    else:
        raise ValueError(
            f"brain desconocido: {spec!r} (usar rules|fake:<policy>|llm:ollama:<modelo>)"
        )

    if cache_dir:
        backend = CachedBackend(backend, Path(cache_dir))
    return backend


def build_decision_actor(
    spec: str,
    sheet: ActorSheet,
    country: Country,
    *,
    seed: int,
    temperature: float = 0.4,
    cache_dir: str | Path | None = None,
    memory_enabled: bool = False,
) -> RuleBasedActor | LLMActor:
    """`spec` -> el objeto `decide(perception, rng) -> list[Action]` para
    `sheet` (ADR 004 secc. 7, deliverable 6: "cada actor obtiene el cerebro
    de la tabla"). `memory_enabled` (ADR 006 secc. 1.3) solo importa para
    `RuleBasedActor` (`w_mem`/`trust_president`); un `LLMActor` ya ve las
    memorias via el prompt (`MEMORIAS RELEVANTES`), sin necesitar el flag."""
    if spec == "rules":
        return RuleBasedActor(
            sheet,
            country.parties,
            country.taylor,
            country.structure.r_neutral,
            country.policy_ranges["interest_rate_target"],
            memory_enabled=memory_enabled,
        )
    backend = build_backend(spec, cache_dir=cache_dir, memory_enabled=memory_enabled)
    return LLMActor(
        sheet,
        backend,
        temperature=temperature,
        seed_base=actor_seed(seed, sheet.id),
    )
