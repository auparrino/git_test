"""Tabla derivada de provincias (seccion 7, fin). Solo para narracion en v0.1."""

from __future__ import annotations

from dataclasses import dataclass

from republica.world.config import Province
from republica.world.events import ShockAggregate
from republica.world.state import Policy, WorldState


@dataclass(frozen=True)
class ProvinceRecord:
    id: str
    unemployment_p: float
    income_p: float


def compute_provinces(
    state: WorldState,
    policy: Policy,
    provinces: list[Province],
    province_transfer_sensitivity: float,
    transfers_ref: float,
    shocks: ShockAggregate,
) -> list[ProvinceRecord]:
    """`unemployment_p = unemployment + u_offset`,
    `income_p = 100*(1 + sector_effect + transfers_effect)`."""
    records = []
    for p in provinces:
        unemployment_p = state.unemployment + p.u_offset
        transfers_effect = (
            province_transfer_sensitivity
            * (policy.provincial_transfers - transfers_ref)
            / transfers_ref
            * p.dependence
        )
        sector_effect = shocks.province_sector.get(p.main_sector, 0.0) / 100.0
        sector_effect += shocks.province_id.get(p.id, 0.0) / 100.0
        income_p = 100.0 * (1.0 + sector_effect + transfers_effect)
        records.append(ProvinceRecord(id=p.id, unemployment_p=unemployment_p, income_p=income_p))
    return records
