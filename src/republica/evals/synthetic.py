"""Corridas sinteticas chicas para las metricas que necesitan una corrida de
verdad (no un caso aislado): `authority_violation`, `parse_rate`,
`strategic_adaptation`, `temporal_consistency`, `memory_recall`,
`hallucination`, `political_realism` (ADR 007 secc. 2). Todas offline (sin
red, `rules`/`fake:*` por defecto en los tests) y chicas a proposito (pocos
meses): un eval no necesita 48 meses de historia para medir si el agente
alucina o respeta su rol, y una corrida chica corre en milisegundos."""

from __future__ import annotations

import tempfile
from pathlib import Path

from republica.engine import emergence as emergence_mod
from republica.engine.narrate import Loaded, load_jsonl
from republica.engine.policy import TaylorPolicy
from republica.engine.simulation import History
from republica.engine.simulation import run as run_simulation
from republica.world.config import load_country

#: Meses de una corrida sintetica "corta" (metricas mecanicas: `authority_
#: violation`/`parse_rate`/`diversity`) -- alcanza con un par de meses para
#: que los 29 actores emitan acciones varias veces.
SHORT_MONTHS = 4

#: Meses de una corrida sintetica "larga" (metricas que necesitan ver un
#: ANTES/DESPUES de un shock: `strategic_adaptation`/`temporal_consistency`)
#: o una historia con algo de emergencia politica (`political_realism`).
LONG_MONTHS = 10

#: Mes en el que se fuerza el shock de la corrida larga (ADR secc. 2:
#: "shock fuerte en t"): a mitad de camino, para tener margen `t-3..t-1` y
#: `t+1..t+3` completos dentro de `LONG_MONTHS`.
SHOCK_MONTH = 5


def tiny_run(
    brain: str,
    seed: int,
    *,
    months: int = SHORT_MONTHS,
    forced_shocks: dict[int, list[str]] | None = None,
    memory_enabled: bool = False,
    congress_enabled: bool = False,
    negotiation_enabled: bool = False,
) -> History:
    """Corrida sintetica chica con TODOS los actores en `brain` (ADR secc.
    2/4: el eval corre "igual contra rules, fake:rules y cualquier llm:*").
    Cohortes/medios/elecciones quedan apagados (no los necesita ninguna
    metrica de la suite, y cada feature de mas suma tiempo de corrida).

    Politica: `TaylorPolicy` (no `ConstantPolicy`, el default de `run()`
    cuando no se pasa `policy_rule`): con la tasa fija, la propuesta nunca
    cambia mes a mes y casi ningun actor cruza el umbral de `SUPPORT_POLICY`/
    `OPPOSE_POLICY` en 4-14 meses (metricas como `temporal_consistency`/
    `political_realism` quedarian con `N=0` siempre) -- documentado en Notas
    de implementacion de ADR 007."""
    country = load_country()
    policy_rule = TaylorPolicy(
        country.default_policy,
        country.taylor,
        country.structure.r_neutral,
        country.policy_ranges["interest_rate_target"],
    )
    return run_simulation(
        seed=seed,
        months=months,
        country=country,
        policy_rule=policy_rule,
        actors_enabled=True,
        default_brain=brain,
        forced_shocks=forced_shocks,
        congress_enabled=congress_enabled,
        negotiation_enabled=negotiation_enabled,
        cohorts_enabled=False,
        media_enabled=False,
        memory_enabled=memory_enabled,
        elections_enabled=False,
    )


def loaded_from_history(history: History) -> Loaded:
    """`Loaded` (`engine/narrate.py`) de una `History` en memoria, via un
    archivo temporal (mismo formato que produce `republica run`, asi se
    reusa `engine/emergence.py::detect` tal cual en vez de reimplementar la
    deteccion de alianzas/coaliciones a mano para evals)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        f.write(history.to_jsonl())
        path = Path(f.name)
    try:
        return load_jsonl(path)
    finally:
        path.unlink(missing_ok=True)


def emergence_report(history: History) -> emergence_mod.EmergenceReport:
    return emergence_mod.detect(loaded_from_history(history))
