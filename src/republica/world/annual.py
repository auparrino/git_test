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
exogenas constantes dentro del año (ADR 011 secc. 6, literal).

ADR 017 secc. 2: como esas 12 aplicaciones NO clampean el estado entre
sub-pasos (el modo mensual si clampea todos los meses), el modo anual pasa
una cota fisica para `g_m` (`G_M_PHYSICAL_RANGE`, ver mas abajo) y CUENTA
cuantas veces hizo falta."""

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

#: Guarda numerica del modo anual (ADR 017 secc. 2): rango FISICO en el que
#: se acota `g_m` (crecimiento mensual del producto, secc. 4.1) antes de
#: `(1 + g_m/100)**12`.
#:
#: Por que hace falta: este modulo aplica `step_economy` 12 veces por
#: turno-año y recien clampea el estado (`clamp_state`) al FINAL del año --
#: a diferencia del modo mensual, que clampea todos los meses. Dentro del
#: año el estado puede crecer sin cota, y con coeficientes legacy que la
#: calibracion macro dejo sin restriccion (el `rho_pi = 2.298` de
#: `a5b_macro`, ver `calibration/parameters.py::
#: MACRO_UNUSED_LEGACY_COEFFICIENTS` y el hallazgo de `docs/
#: ADR_014_rolling_backtest.md`) `g_m` llega a valores donde esa potencia
#: desborda el `float` de Python (`OverflowError`: las 135 ventanas anuales
#: 1916-1960 del backtest `b1_a5b` perdieron las 4050 semillas de su brazo
#: calibrado, todas).
#:
#: Por que +-50 % MENSUAL: compuesto, -50 % mensual es -99.8 % anual y
#: +50 % mensual es +12.875 % anual. Ninguna economia real se mueve asi ni
#: por un mes; cualquier valor fuera de este rango es ruido numerico, no
#: economia, y cortarlo ahi no puede estar tapando una dinamica que valga
#: la pena mirar. La cota se aplica SOLO en modo anual (el modo mensual
#: llama a `step_economy` sin `g_m_clamp`: cero cambios, golden hashes
#: intactos).
#:
#: No es silenciosa: cada clampeo se cuenta en `AnnualRecord.g_m_clamped`
#: (por turno-año, sobre 12 sub-pasos) y en `AnnualHistory.g_m_clamped`
#: (total, tambien en la ultima linea del JSONL). Una corrida anual con
#: `g_m_clamped > 0` esta corriendo contra la guarda, no contra el modelo,
#: y hay que leerla asi.
G_M_PHYSICAL_RANGE: tuple[float, float] = (-50.0, 50.0)


def _g_m_was_clamped(g_m: float) -> bool:
    """`True` si `g_m` (el que devuelve `Aux`, ya clampeado por
    `step_economy(g_m_clamp=...)`) quedo pegado a un borde de
    `G_M_PHYSICAL_RANGE`. Se detecta por comparacion con el borde y no con
    un flag devuelto por `step_economy` para no agregarle un campo a `Aux`
    (que se serializa en el `MonthRecord` del modo mensual y cambiaria su
    contenido). Falso positivo posible pero irrelevante: que `g_m` caiga
    EXACTAMENTE en -50.0 o +50.0 sin haber sido clampeado."""
    lo, hi = G_M_PHYSICAL_RANGE
    return g_m <= lo or g_m >= hi


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
    #: Cuantos de los 12 sub-pasos de este turno-año necesitaron la guarda
    #: numerica (`G_M_PHYSICAL_RANGE`, ADR 017 secc. 2). `0` = el año corrio
    #: entero dentro del rango fisico.
    g_m_clamped: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnnualHistory:
    records: list[AnnualRecord]
    outcome: str
    #: Total de clampeos de `g_m` de toda la corrida (suma de
    #: `AnnualRecord.g_m_clamped`, ADR 017 secc. 2). Se expone aca ademas de
    #: por año para que quien lee un backtest anual pueda descartar una
    #: corrida entera sin recorrer los registros.
    g_m_clamped: int = 0

    def to_jsonl(self) -> str:
        import json

        lines = [json.dumps(r.to_dict(), ensure_ascii=False) for r in self.records]
        lines.append(
            json.dumps(
                {"outcome": self.outcome, "mode": "annual", "g_m_clamped": self.g_m_clamped},
                ensure_ascii=False,
            )
        )
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
    # Bug real encontrado por el backtest (ADR 014): con `shocks_enabled=
    # False` (el default de este modulo) el catalogo se armaba VACIO
    # (`by_id={}`), y `ShockCatalog.apply_month` busca CUALQUIER shock
    # activo -- forzado incluido -- en `by_id`: forzar cualquier
    # `shock_id` (via `forced_shocks`, el mecanismo que el docstring de
    # esta funcion ya decia que "funciona") tiraba `KeyError` siempre. El
    # catalogo COMPLETO (`by_id`) se arma siempre, para que
    # `apply_month` pueda resolver los efectos de un shock FORZADO; solo
    # `defs` (la lista que `ShockCatalog.roll` sortea para shocks
    # ALEATORIOS) queda vacia sin `shocks_enabled=True` -- el
    # comportamiento de "sin aleatorios por default en modo anual" no
    # cambia, solo se arregla el forzado.
    from republica.world.events import build_catalog

    catalog = ShockCatalog.__new__(ShockCatalog)
    catalog.by_id = {d.id: d for d in build_catalog(country.shocks)}
    catalog.defs = list(catalog.by_id.values()) if shocks_enabled else []

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
        clamped_this_year = 0
        for i in range(12):
            sub_agg = agg_year if i == 0 else ShockAggregate()
            econ_state, aux = step_economy(
                year_state,
                sub_exo,
                exo_new,
                policy,
                sub_agg,
                structure,
                coeff,
                g_m_clamp=G_M_PHYSICAL_RANGE,
            )
            if _g_m_was_clamped(aux.g_m):
                clamped_this_year += 1
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
                g_m_clamped=clamped_this_year,
            )
        )

    return AnnualHistory(
        records=records,
        outcome="survived",
        g_m_clamped=sum(r.g_m_clamped for r in records),
    )
