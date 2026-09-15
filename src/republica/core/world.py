"""Mundo del hito 1 (ADR 010 secc. 7): configuracion (`CoreConfig`, agentes,
regiones, tabla de bienes, produccion/necesidades por turno) y el estado
vectorizado (`CoreWorld`, arrays de numpy) que `core.exchange` muta turno a
turno.

Fisica fija (ADR 010 secc. 2), nada de esto se decide en tiempo de corrida:
K bienes con durabilidad/divisibilidad/costo de transporte fijos, R
regiones con especializacion productiva fija al inicio, necesidades
homogeneas por region (v2.0, ADR secc. 2 "supuestos discutibles"). Lo que SI
varia por agente y evoluciona es `acceptability` (el genoma de que bienes
acepta como intermedio, ADR secc. 7 "estrategia evolutiva")."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

#: Los 6 bienes del hito 1 (ADR 010 secc. 7, orden fijo = indice en los
#: arrays [N, K]).
GOOD_NAMES: tuple[str, ...] = ("grano", "pescado", "tela", "herramienta", "sal", "conchas")


class GoodSpec(BaseModel):
    """Atributos fisicos de un bien (ADR secc. 2: "durabilidad, divisibilidad,
    costo de transporte/almacenamiento, y utilidad directa")."""

    name: str
    #: Fraccion del stock que sobrevive cada turno (decay = 1 - durability).
    durability: float = Field(ge=0.0, le=1.0)
    #: Unidad minima intercambiable/producible.
    divisibility: float = Field(gt=0.0)
    #: Fraccion que se pierde al moverse de region (ademas del costo de
    #: transporte general entre regiones, `CoreConfig.transport_cost`, que es
    #: el parametro que barre la hipotesis H4).
    transport_cost: float = Field(ge=0.0, le=1.0)
    #: "all" = todos lo necesitan (posiblemente "poco", ver `need_qty`);
    #: "producers" = solo bonifica produccion de quien lo tiene; "none" =
    #: nadie lo consume (candidato puro a intermediario, ADR: conchas).
    consumed_by: str = "all"
    #: Cantidad necesitada por turno si `consumed_by == "all"` (0 si no).
    need_qty: float = 0.0


class RegionSpec(BaseModel):
    """Especializacion productiva de una region (ADR secc. 2 "Produccion":
    "cada agente produce por turno una canasta segun su region y su
    especializacion, fija al inicio")."""

    name: str
    production_goods: tuple[str, str]
    production_rate: float = 1.2


#: Tabla de bienes por defecto (ADR 010 secc. 7, valores literales del ADR;
#: `need_qty`/`consumed_by` son la interpretacion operativa documentada en
#: "Notas de implementacion" al pie del ADR).
DEFAULT_GOODS: tuple[GoodSpec, ...] = (
    GoodSpec(
        name="grano",
        durability=0.90,
        divisibility=1.0,
        transport_cost=0.05,
        consumed_by="all",
        need_qty=1.0,
    ),
    GoodSpec(
        name="pescado",
        durability=0.60,
        divisibility=1.0,
        transport_cost=0.10,
        consumed_by="all",
        need_qty=1.0,
    ),
    GoodSpec(
        name="tela",
        durability=0.98,
        divisibility=1.0,
        transport_cost=0.05,
        consumed_by="all",
        need_qty=1.0,
    ),
    # ADR: "quien lo consume: productores". En este mundo TODO agente es
    # productor (de los 2 bienes de su region, ADR secc. 2 "Produccion"),
    # asi que se modela como una necesidad mas -- ver "Notas de
    # implementacion" al pie del ADR para la discusion de esta lectura.
    GoodSpec(
        name="herramienta",
        durability=0.99,
        divisibility=1.0,
        transport_cost=0.10,
        consumed_by="all",
        need_qty=0.3,
    ),
    GoodSpec(
        name="sal",
        durability=0.995,
        divisibility=0.1,
        transport_cost=0.01,
        consumed_by="all",
        need_qty=0.2,
    ),
    GoodSpec(
        name="conchas",
        durability=1.00,
        divisibility=0.01,
        transport_cost=0.01,
        consumed_by="none",
        need_qty=0.0,
    ),
)

#: 4 regiones (ADR secc. 7), cada una especializada en 2 bienes; entre las 4
#: cubren los 6 bienes (grano/pescado repetidos, ver Notas de implementacion
#: para la razon de este reparto).
DEFAULT_REGIONS: tuple[RegionSpec, ...] = (
    RegionSpec(name="llanura", production_goods=("grano", "sal")),
    RegionSpec(name="costa", production_goods=("pescado", "conchas")),
    RegionSpec(name="valle", production_goods=("tela", "herramienta")),
    RegionSpec(name="sierra", production_goods=("herramienta", "sal")),
)


class CoreConfig(BaseModel):
    """Configuracion completa de una corrida del hito 1. Todo lo que varia
    entre corridas (agentes, turnos, semilla, y los parametros que barren
    H3/H4) vive aca; nada de esto se decide en `exchange.py`."""

    n_agents: int = 10_000
    turns: int = 500
    seed: int = 7

    regions: tuple[RegionSpec, ...] = DEFAULT_REGIONS
    goods: tuple[GoodSpec, ...] = DEFAULT_GOODS

    #: Vecinos locales muestreados por turno (ADR: 12).
    neighbours_per_turn: int = 12
    #: `OFFER`s emitidas por agente por turno (ADR: hasta 3).
    max_offers_per_turn: int = 3
    #: Probabilidad de que un vecino muestreado sea de la misma region (ADR:
    #: 0.8 misma region, 0.2 otras regiones "menos costo de transporte").
    same_region_prob: float = 0.8
    #: Costo de transporte GENERAL entre regiones (adicional al de cada bien):
    #: reduce la probabilidad efectiva de ver vecinos de otra region. Este es
    #: el parametro que barre H4.
    transport_cost: float = 0.05
    #: Cantidad fija de cada `OFFER` (unidad de trueque; se redondea al
    #: multiplo de `divisibility` del bien al ejecutar).
    offer_qty: float = 1.0
    #: Cuanto por encima de la necesidad debe tener un agente de un bien para
    #: considerarlo "excedente" (surplus) ofrecible.
    reserve_buffer: float = 1.2

    #: Turnos de privacion acumulada (necesidad incumplida) antes de morir.
    deprivation_threshold: int = 12
    #: Recuperacion de privacion por turno en que TODAS las necesidades se
    #: cubrieron.
    deprivation_recovery: int = 2
    #: Bono multiplicativo a la produccion propia por tener >=1 herramienta.
    tool_bonus: float = 0.25

    #: Genoma de aceptabilidad (ADR secc. 7 "estrategia evolutiva"):
    #: probabilidad inicial de aceptar un bien que no se necesita a cambio de
    #: uno que si, y como se refuerza/muta.
    acceptability_init: float = 0.05
    acceptability_up: float = 0.20
    acceptability_down: float = 0.03
    #: Turnos dentro de los cuales un intermediario aceptado debe
    #: reintercambiarse por algo necesitado para contar como "exito" (ADR:
    #: "en <= 3 turnos").
    retrade_window: int = 3
    #: Desvio estandar de la mutacion gaussiana de `acceptability` al
    #: reproducirse (ADR: "Mutacion al reproducirse").
    mutation_std: float = 0.05

    #: Multiplicador sobre la tasa de produccion de conchas (bien sin
    #: utilidad propia, ADR H3): 1.0 = abundancia por defecto; <1 = escasas.
    #: Es el parametro que barre H3.
    shell_abundance: float = 1.0
    #: Bien "escaso" al que aplica `shell_abundance` (por defecto conchas,
    #: el unico bien `consumed_by == "none"` del hito 1).
    scarce_good: str = "conchas"

    #: Inventario inicial (mismo valor para todos los bienes al arrancar).
    initial_stock: float = 1.0

    model_config = {"frozen": True}

    def good_index(self) -> dict[str, int]:
        return {g.name: i for i, g in enumerate(self.goods)}

    def n_goods(self) -> int:
        return len(self.goods)

    def n_regions(self) -> int:
        return len(self.regions)


@dataclass
class CoreWorld:
    """Estado vectorizado de una corrida (arrays `[N, K]`/`[N]`, ADR secc.
    7 "vectorizado por turno"). No es pydantic (los arrays de numpy no
    encajan bien ahi); es un contenedor mutable que `exchange.step` actualiza
    in-place cada turno."""

    inventories: Any  # NDArray[float64] [N, K]
    region: Any  # NDArray[int64] [N]
    production: Any  # NDArray[float64] [N, K] -- fijo por agente (region)
    needs: Any  # NDArray[float64] [N, K] -- homogeneo por region
    deprivation: Any  # NDArray[int64] [N]
    acceptability: Any  # NDArray[float64] [N, K] -- evoluciona
    #: turno (int) en que se acepto por ultima vez cada bien SIN necesitarlo
    #: (para `classify.acceptance_rate`, ventana de 50 turnos); -1 = nunca.
    last_accept_turn: Any  # NDArray[int64] [N, K]
    #: turno en que se acepto un intermediario aun sin reintercambiar (para
    #: el refuerzo de `evolve.py`); -1 = ninguno pendiente.
    pending_turn: Any  # NDArray[int64] [N, K]
    region_pools: list[Any] = field(default_factory=list)  # indices por region


def init_world(config: CoreConfig, seed: int | None = None) -> CoreWorld:
    """Construye el estado inicial: agentes repartidos parejo entre
    regiones, produccion fija segun la especializacion de su region,
    necesidades homogeneas por region, inventario inicial parejo,
    aceptabilidad inicial uniforme."""
    import numpy as np

    rng = np.random.default_rng(seed if seed is not None else config.seed)
    n = config.n_agents
    k = config.n_goods()
    r = config.n_regions()
    idx = config.good_index()

    region = rng.integers(0, r, size=n).astype(np.int64)
    region_pools = [np.nonzero(region == ri)[0] for ri in range(r)]

    production = np.zeros((n, k), dtype=np.float64)
    for ri, spec in enumerate(config.regions):
        mask = region == ri
        rate = spec.production_rate
        for good_name in spec.production_goods:
            gi = idx[good_name]
            eff_rate = rate
            if good_name == config.scarce_good:
                eff_rate = rate * config.shell_abundance
            production[mask, gi] = eff_rate

    needs = np.zeros((n, k), dtype=np.float64)
    for good in config.goods:
        if good.consumed_by == "all" and good.need_qty > 0:
            needs[:, idx[good.name]] = good.need_qty

    inventories = np.full((n, k), config.initial_stock, dtype=np.float64)
    deprivation = np.zeros(n, dtype=np.int64)
    acceptability = np.full((n, k), config.acceptability_init, dtype=np.float64)
    # No tiene sentido "aceptar como intermedio" un bien que ya se necesita
    # directamente: esos siempre se toman con gusto, no son una apuesta.
    acceptability[needs > 0] = 1.0
    last_accept_turn = np.full((n, k), -1, dtype=np.int64)
    pending_turn = np.full((n, k), -1, dtype=np.int64)

    return CoreWorld(
        inventories=inventories,
        region=region,
        production=production,
        needs=needs,
        deprivation=deprivation,
        acceptability=acceptability,
        last_accept_turn=last_accept_turn,
        pending_turn=pending_turn,
        region_pools=region_pools,
    )


__all__ = [
    "GOOD_NAMES",
    "GoodSpec",
    "RegionSpec",
    "DEFAULT_GOODS",
    "DEFAULT_REGIONS",
    "CoreConfig",
    "CoreWorld",
    "init_world",
]
