"""Modo anual (ADR 011 secc. 6, `features.annual_mode`): un turno = un año,
para arranques anteriores a 1943 (unica cobertura de datos real disponible
fuera de Maddison/V-Dem, ver `data/countries/argentina/history/coverage.md`).

Deliberadamente MINIMO (el ADR lo marca "exploratorio" en cada salida): sin
actores, sin cohortes/medios, sin Congreso, sin elecciones -- "solo el
presidente por reglas y el regimen" (ADR 011 secc. 6). El regimen de cada
año NO se deriva con la maquina de estados de `world/regime.py`: se lee
directo de `politics/regimes.csv` (dato de entrada real para ese periodo,
mas simple y mas fiel que reimplementar la logica endogena a escala anual
sin datos mensuales que la disparen -- ver Notas de implementacion del
ADR 011). Reusa las mismas funciones de `world/economy.py`/`society.py`/
`politics.py` que el modo mensual, aplicadas 12 veces por turno con
exogenas constantes dentro del año (ADR 011 secc. 6, literal)."""

from __future__ import annotations

import csv
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from republica.engine.policy import PolicyRule
from republica.world.config import Country
from republica.world.economy import Aux, finalize_exogenous, step_economy, step_exogenous
from republica.world.events import ShockAggregate, ShockCatalog
from republica.world.politics import step_politics
from republica.world.society import step_society
from republica.world.state import clamp_state

#: Regimenes de `politics/regimes.csv` fuera de `world/regime.py::
#: REGIME_MODES` (que solo cubre 1983+): se mapean a los 4 modos del motor
#: para que `AnnualRecord.regime_mode` siempre sea uno de esos 4 (ADR 011
#: secc. 3/6 comparten vocabulario).
_REGIME_MODE_MAP = {
    "democracy": "democracy",
    "restricted_democracy": "democracy",
    "transition": "transition",
    "coup": "coup",
    "dictatorship": "dictatorship",
    "civil_war_or_state_building": "dictatorship",
}


def load_annual_regime(regimes_csv: Path) -> dict[int, str]:
    """`{year: regime_mode}` de `politics/regimes.csv`, remapeado a los 4
    modos de `world/regime.py::REGIME_MODES` (ver `_REGIME_MODE_MAP`)."""
    out: dict[int, str] = {}
    if not regimes_csv.exists():
        return out
    with regimes_csv.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            year = int(row["year"])
            out[year] = _REGIME_MODE_MAP.get(row["regime_mode"], "democracy")
    return out


@dataclass
class AnnualRecord:
    year_index: int
    year: int
    state: dict
    exo: dict
    regime_mode: str
    shocks_new: list[str] = field(default_factory=list)
    shocks_active: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnnualHistory:
    records: list[AnnualRecord]
    outcome: str

    def to_jsonl(self) -> str:
        import json

        lines = [json.dumps(r.to_dict(), ensure_ascii=False) for r in self.records]
        lines.append(json.dumps({"outcome": self.outcome, "mode": "annual"}, ensure_ascii=False))
        return "\n".join(lines) + "\n"


def run_annual(
    seed: int,
    years: int,
    country: Country,
    policy_rule: PolicyRule,
    start_year: int,
    annual_regime: dict[int, str] | None = None,
    forced_shocks: dict[int, list[str]] | None = None,
    shocks_enabled: bool = False,
) -> AnnualHistory:
    """`years` turnos anuales desde `start_year` (ADR 011 secc. 6).

    `shocks_enabled` default `False`: el catalogo de `shocks.json` esta
    calibrado en duraciones de MESES: aplicado un turno anual sorteando por
    año, la probabilidad/duracion no se re-escala (mismo motivo que
    `--historical-shocks` sigue funcionando via `forced_shocks`, tratando
    cada shock forzado como si durara 1 turno-año -- ver mas abajo). Correr
    con shocks aleatorios prendidos en modo anual es valido pero no esta
    calibrado a esa escala; se documenta como deviacion.
    """
    coeff = country.coefficients
    structure = country.structure
    rng = random.Random(seed)
    catalog = ShockCatalog.__new__(ShockCatalog)  # se arma abajo si hace falta
    catalog.defs = []
    catalog.by_id = {}
    if shocks_enabled:
        from republica.world.events import build_catalog

        catalog = ShockCatalog(build_catalog(country.shocks))

    state = country.initial_state
    exo = country.exogenous
    active_shocks: dict = {}
    records: list[AnnualRecord] = []
    regime_lookup = annual_regime or {}

    for turn in range(1, years + 1):
        year = start_year + turn - 1
        commodity_base, world_base = step_exogenous(
            exo, country.exogenous_process, rng, noise_enabled=False
        )
        forced = (forced_shocks or {}).get(turn)
        new_ids: list[str] = []
        agg_year = ShockAggregate()
        if catalog.defs or forced:
            new_ids = catalog.roll(state, rng, active_shocks, turn, forced=forced)
            agg_year = catalog.apply_month(active_shocks, new_ids)
        exo_new = finalize_exogenous(commodity_base, world_base, agg_year)

        # "el presidente por reglas" (ADR 011 secc. 6): una decision de
        # `policy_rule` por TURNO (no 12: no hay actores/meses dentro del
        # año), vigente en los 12 sub-pasos.
        policy = policy_rule.decide(state, turn)

        # 12 sub-pasos mensuales, exogenas constantes dentro del año; los
        # efectos del shock (si los hay) se aplican una sola vez, en el
        # primer sub-paso (equivalente a "first"/"each" tratados a escala de
        # UN turno-año, no de 12).
        year_state = state
        aux: Aux | None = None
        sub_exo = exo
        for i in range(12):
            sub_agg = agg_year if i == 0 else ShockAggregate()
            econ_state, aux = step_economy(
                year_state, sub_exo, exo_new, policy, sub_agg, structure, coeff
            )
            soc_state = step_society(year_state, econ_state, policy, sub_agg, coeff)
            pol_state = step_politics(
                year_state, soc_state, aux.demand_gap, country.coalition_seats, sub_agg, coeff
            )
            year_state = pol_state
            sub_exo = exo_new

        clamped, _overflow = clamp_state(year_state, country.ranges)
        state = clamped
        exo = exo_new

        records.append(
            AnnualRecord(
                year_index=turn,
                year=year,
                state=clamped.model_dump(),
                exo=exo.model_dump(),
                regime_mode=regime_lookup.get(year, "democracy"),
                shocks_new=list(new_ids),
                shocks_active=sorted(active_shocks),
            )
        )

    return AnnualHistory(records=records, outcome="survived")
