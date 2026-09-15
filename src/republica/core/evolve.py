"""Evolucion de la estrategia de aceptabilidad (ADR 010 secc. 7, "estrategia
evolutiva por agente"): refuerzo (sube si un bien aceptado como intermediario
se pudo reintercambiar en <= `retrade_window` turnos por algo necesitado, baja
si se "pudrio" -- se le vencio la ventana sin reintercambiarse) y mutacion al
reproducirse (un agente muerto se reemplaza por una copia mutada de un
sobreviviente de su region).

Todas las funciones mutan/leen arrays de `CoreWorld` in-place; `numpy` se
importa perezosamente en cada funcion (ver `republica.core.__init__`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from republica.core.world import CoreConfig, CoreWorld


def register_intermediate_acceptance(world: CoreWorld, agents: Any, goods: Any, turn: int) -> None:
    """Un agente acepto un bien que no necesita (posible intermediario):
    marca `last_accept_turn` (para `classify.acceptance_rate`) y, si no
    tenia ya una apuesta pendiente en ese bien, abre una en `pending_turn`
    (para el refuerzo -- ADR: "sube si se pudo reintercambiar en <= 3
    turnos")."""
    if len(agents) == 0:
        return
    world.last_accept_turn[agents, goods] = turn
    fresh = world.pending_turn[agents, goods] < 0
    if fresh.any():
        world.pending_turn[agents[fresh], goods[fresh]] = turn


def register_retrade_success(world: CoreWorld, agents: Any, goods: Any, config: CoreConfig) -> None:
    """El bien `goods[i]` que `agents[i]` tenia pendiente se acaba de dar a
    cambio de algo que necesitaba: exito, sube `acceptability` y cierra la
    apuesta pendiente."""
    if len(agents) == 0:
        return
    pending = world.pending_turn[agents, goods] >= 0
    if not pending.any():
        return
    a, g = agents[pending], goods[pending]
    world.acceptability[a, g] = (world.acceptability[a, g] + config.acceptability_up).clip(0.0, 1.0)
    world.pending_turn[a, g] = -1


def decay_stale_pending(world: CoreWorld, config: CoreConfig, turn: int) -> None:
    """Cierra las apuestas pendientes que superaron `retrade_window` sin
    reintercambiarse: "baja si se pudrio o quedo sin uso"."""
    import numpy as np

    stale = (world.pending_turn >= 0) & (turn - world.pending_turn > config.retrade_window)
    if not stale.any():
        return
    agents, goods = np.nonzero(stale)
    world.acceptability[agents, goods] = (
        world.acceptability[agents, goods] - config.acceptability_down
    ).clip(0.0, 1.0)
    world.pending_turn[agents, goods] = -1


def replace_dead(world: CoreWorld, config: CoreConfig, rng: Any, turn: int) -> int:
    """Reemplaza a los agentes con `deprivation >= deprivation_threshold`
    por una copia mutada de un sobreviviente al azar de la MISMA region
    (ADR: "es reemplazado" + secc. 7 "mutacion al reproducirse"). Devuelve
    cuantos murieron este turno."""
    import numpy as np

    dead = np.nonzero(world.deprivation >= config.deprivation_threshold)[0]
    if len(dead) == 0:
        return 0
    alive_mask = np.ones(len(world.region), dtype=bool)
    alive_mask[dead] = False

    for region_id, pool in enumerate(world.region_pools):
        dead_here = dead[world.region[dead] == region_id]
        if len(dead_here) == 0:
            continue
        survivors = pool[alive_mask[pool]]
        if len(survivors) == 0:
            survivors = np.nonzero(alive_mask)[0]
        if len(survivors) == 0:
            # Extincion total: no hay de quien copiar: reinicia desde cero.
            world.inventories[dead_here] = config.initial_stock
            world.deprivation[dead_here] = 0
            fresh_acc = np.full(world.acceptability[dead_here].shape, config.acceptability_init)
            fresh_acc[world.needs[dead_here] > 0] = 1.0
            world.acceptability[dead_here] = fresh_acc
            continue
        parents = survivors[rng.integers(0, len(survivors), size=len(dead_here))]
        world.acceptability[dead_here] = _mutate(
            world.acceptability[parents], rng, config.mutation_std
        )
        world.inventories[dead_here] = config.initial_stock
        world.deprivation[dead_here] = 0
        world.pending_turn[dead_here] = -1

    return len(dead)


def _mutate(rows: Any, rng: Any, std: float) -> Any:
    noise = rng.normal(0.0, std, size=rows.shape)
    return (rows + noise).clip(0.0, 1.0)


__all__ = [
    "register_intermediate_acceptance",
    "register_retrade_success",
    "decay_stale_pending",
    "replace_dead",
]
