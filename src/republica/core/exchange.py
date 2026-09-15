"""Motor de un turno (ADR 010 secc. 7): muestreo de vecinos locales, formacion
de hasta `max_offers_per_turn` `OFFER`s (primitiva 2, ADR secc. 4) por
ronda, aceptacion, ejecucion atomica, consumo, decaimiento por durabilidad,
produccion, actualizacion de privacion y reemplazo de muertos.

Solo las primitivas `TRANSFER`/`OFFER` estan activas (hito 1): no hay
`PROMISE`, `GRANT`, grupos ni coercion. Vectorizado con numpy (`numpy` se
importa perezosamente dentro de `step`); pensado para O(N * vecinos) por
turno, ver el benchmark de `tests/test_core.py`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from republica.core.world import CoreConfig, CoreWorld

_EPS = 1e-9
#: Ventana de turnos sobre la que se mide `acceptance_rate` en `classify.py`
#: (ADR secc. 6: "aceptaron ... en los ultimos 50 turnos").
ACCEPTANCE_WINDOW = 50


@dataclass
class TurnMetrics:
    """Metricas de un turno, ya agregadas (JSON-serializables via
    `to_dict()`). `republica.core.run.simulate` acumula una lista de estas
    como la serie de tiempo de la corrida."""

    turn: int
    trades_direct: int
    trades_indirect: int
    deaths: int
    intermediate_by_good: list[int]
    accept_no_need_by_good: list[int]
    acceptance_rate_by_good: list[float]
    acceptance_rate_by_good_region: list[list[float]]
    deprivation_mean: float
    deprivation_mean_by_region: list[float]
    gini: float
    gini_by_region: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "trades_direct": self.trades_direct,
            "trades_indirect": self.trades_indirect,
            "deaths": self.deaths,
            "intermediate_by_good": self.intermediate_by_good,
            "accept_no_need_by_good": self.accept_no_need_by_good,
            "acceptance_rate_by_good": self.acceptance_rate_by_good,
            "acceptance_rate_by_good_region": self.acceptance_rate_by_good_region,
            "deprivation_mean": self.deprivation_mean,
            "deprivation_mean_by_region": self.deprivation_mean_by_region,
            "gini": self.gini,
            "gini_by_region": self.gini_by_region,
        }


def _gini(values: Any) -> float:
    import numpy as np

    v = np.sort(np.asarray(values, dtype=np.float64))
    n = v.shape[0]
    total = v.sum()
    if n == 0 or total <= _EPS:
        return 0.0
    ranks = np.arange(1, n + 1)
    return float((2.0 * np.sum(ranks * v) - (n + 1) * total) / (n * total))


def _sample_neighbours(world: CoreWorld, config: CoreConfig, rng: Any) -> Any:
    """12 vecinos locales por agente: misma region con `same_region_prob`,
    otra region con el resto MENOS `transport_cost` (ADR secc. 7)."""
    import numpy as np

    n = world.region.shape[0]
    r = config.n_regions()
    k = config.neighbours_per_turn

    cross_total = max(0.0, (1.0 - config.same_region_prob) - config.transport_cost)
    p_same = 1.0 - cross_total

    same_candidates = np.empty((n, k), dtype=np.int64)
    for pool in world.region_pools:
        if len(pool) == 0:
            continue
        picks = rng.integers(0, len(pool), size=(len(pool), k))
        same_candidates[pool] = pool[picks]

    other_candidates = np.empty((n, k), dtype=np.int64)
    if r > 1:
        offset = rng.integers(0, r - 1, size=(n, k))
        target_region = offset + (offset >= world.region[:, None])
        for tr, pool in enumerate(world.region_pools):
            if len(pool) == 0:
                continue
            mask = target_region == tr
            count = int(mask.sum())
            if count == 0:
                continue
            picks = rng.integers(0, len(pool), size=count)
            other_candidates[mask] = pool[picks]
    else:
        other_candidates[:] = same_candidates

    same_mask = rng.random((n, k)) < p_same
    return np.where(same_mask, same_candidates, other_candidates)


def step(world: CoreWorld, config: CoreConfig, rng: Any, turn: int) -> TurnMetrics:
    """Corre un turno completo, mutando `world` in-place. Devuelve las
    metricas agregadas de ese turno."""
    import numpy as np

    from republica.core import evolve

    idx = config.good_index()
    n, k = world.inventories.shape

    unit_qty = np.array(
        [
            max(g.divisibility, round(config.offer_qty / g.divisibility) * g.divisibility)
            for g in config.goods
        ],
        dtype=np.float64,
    )
    unit_qty = np.where(unit_qty <= 0, config.offer_qty, unit_qty)

    trades_direct = 0
    trades_indirect = 0
    intermediate_by_good = np.zeros(k, dtype=np.int64)
    accept_no_need_by_good = np.zeros(k, dtype=np.int64)

    arange_n = np.arange(n)

    for round_idx in range(config.max_offers_per_turn):
        neighbours = _sample_neighbours(world, config, rng)
        j_idx = neighbours[:, round_idx % config.neighbours_per_turn]

        shortfall = np.maximum(world.needs - world.inventories, 0.0)
        surplus = np.maximum(world.inventories - world.needs * config.reserve_buffer, 0.0)

        give_good = np.where(surplus.max(axis=1) > _EPS, surplus.argmax(axis=1), -1)
        has_direct_want = shortfall.max(axis=1) > _EPS
        want_good_direct = shortfall.argmax(axis=1)

        inv_at_target = world.inventories[j_idx].copy()
        safe_give = np.clip(give_good, 0, k - 1)
        inv_at_target[arange_n, safe_give] = -1.0
        candidate = inv_at_target.argmax(axis=1)
        candidate_amount = inv_at_target[arange_n, candidate]
        willing_roll = rng.random(n) < world.acceptability[arange_n, candidate]
        want_good_indirect = np.where((candidate_amount > _EPS) & willing_roll, candidate, -1)

        want_good = np.where(has_direct_want, want_good_direct, want_good_indirect)
        is_direct = has_direct_want.copy()

        valid = (give_good >= 0) & (want_good >= 0) & (j_idx != arange_n)
        if not valid.any():
            continue

        safe_gg = np.clip(give_good, 0, k - 1)
        safe_wg = np.clip(want_good, 0, k - 1)
        gq = unit_qty[safe_gg]
        wq = unit_qty[safe_wg]

        i_has_enough = world.inventories[arange_n, safe_gg] >= gq - _EPS
        j_has_enough = world.inventories[j_idx, safe_wg] >= wq - _EPS
        j_accepts = (shortfall[j_idx, safe_gg] > _EPS) | (
            rng.random(n) < world.acceptability[j_idx, safe_gg]
        )

        valid = valid & i_has_enough & j_has_enough & j_accepts
        valid_idx = np.nonzero(valid)[0]
        if valid_idx.size == 0:
            continue

        # Como mucho una oferta EJECUTADA por contraparte por ronda (evita
        # sobre-girar el inventario de un agente elegido como blanco por
        # varios ofertantes a la vez -- simplificacion documentada, ver ADR
        # "Notas de implementacion").
        targets = j_idx[valid_idx]
        _, first_pos = np.unique(targets, return_index=True)
        keep = valid_idx[first_pos]

        i_sel = keep
        j_sel = j_idx[keep]
        gg = safe_gg[keep]
        wg = safe_wg[keep]
        gq_sel = gq[keep]
        wq_sel = wq[keep]
        direct_sel = is_direct[keep]

        np.add.at(world.inventories, (i_sel, wg), wq_sel)
        np.subtract.at(world.inventories, (i_sel, gg), gq_sel)
        np.add.at(world.inventories, (j_sel, gg), gq_sel)
        np.subtract.at(world.inventories, (j_sel, wg), wq_sel)
        np.clip(world.inventories, 0.0, None, out=world.inventories)

        trades_direct += int(direct_sel.sum())
        trades_indirect += int((~direct_sel).sum())
        if (~direct_sel).any():
            np.add.at(intermediate_by_good, wg[~direct_sel], 1)

        i_no_need = world.needs[i_sel, wg] <= _EPS
        j_no_need = world.needs[j_sel, gg] <= _EPS
        if i_no_need.any():
            np.add.at(accept_no_need_by_good, wg[i_no_need], 1)
            evolve.register_intermediate_acceptance(world, i_sel[i_no_need], wg[i_no_need], turn)
        if j_no_need.any():
            np.add.at(accept_no_need_by_good, gg[j_no_need], 1)
            evolve.register_intermediate_acceptance(world, j_sel[j_no_need], gg[j_no_need], turn)

        if direct_sel.any():
            evolve.register_retrade_success(world, i_sel[direct_sel], gg[direct_sel], config)
        j_needed_gg = world.needs[j_sel, gg] > _EPS
        if j_needed_gg.any():
            evolve.register_retrade_success(world, j_sel[j_needed_gg], wg[j_needed_gg], config)

    evolve.decay_stale_pending(world, config, turn)

    # --- consumo ---
    consumed = np.minimum(world.inventories, world.needs)
    unmet = (world.needs - consumed) > _EPS
    world.inventories -= consumed
    any_unmet = unmet.any(axis=1)
    world.deprivation[any_unmet] += 1
    recovered = ~any_unmet
    world.deprivation[recovered] = np.maximum(
        0, world.deprivation[recovered] - config.deprivation_recovery
    )

    # --- decaimiento por durabilidad ---
    durability_vec = np.array([g.durability for g in config.goods], dtype=np.float64)
    world.inventories *= durability_vec[None, :]

    # --- produccion (con bono por tener herramienta) ---
    tool_idx = idx.get("herramienta")
    if tool_idx is not None:
        has_tool = world.inventories[:, tool_idx] > _EPS
        bonus = np.where(has_tool, 1.0 + config.tool_bonus, 1.0)
    else:
        bonus = np.ones(n, dtype=np.float64)
    world.inventories += world.production * bonus[:, None]

    # --- muerte y reemplazo ---
    deaths = evolve.replace_dead(world, config, rng, turn)

    # --- metricas ---
    window_mask = (world.last_accept_turn >= 0) & (
        world.last_accept_turn >= turn - ACCEPTANCE_WINDOW + 1
    )
    acceptance_rate_by_good = window_mask.mean(axis=0).tolist()
    acceptance_rate_by_good_region = [
        (window_mask[pool].mean(axis=0).tolist() if len(pool) else [0.0] * k)
        for pool in world.region_pools
    ]

    totals = world.inventories.sum(axis=1)
    gini_global = _gini(totals)
    gini_by_region = [_gini(totals[pool]) if len(pool) else 0.0 for pool in world.region_pools]

    dep_global = float(world.deprivation.mean())
    dep_by_region = [
        float(world.deprivation[pool].mean()) if len(pool) else 0.0 for pool in world.region_pools
    ]

    return TurnMetrics(
        turn=turn,
        trades_direct=trades_direct,
        trades_indirect=trades_indirect,
        deaths=deaths,
        intermediate_by_good=intermediate_by_good.tolist(),
        accept_no_need_by_good=accept_no_need_by_good.tolist(),
        acceptance_rate_by_good=acceptance_rate_by_good,
        acceptance_rate_by_good_region=acceptance_rate_by_good_region,
        deprivation_mean=dep_global,
        deprivation_mean_by_region=dep_by_region,
        gini=gini_global,
        gini_by_region=gini_by_region,
    )


__all__ = ["TurnMetrics", "step", "ACCEPTANCE_WINDOW"]
