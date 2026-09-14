"""Carga de configuracion del pais desde `data/` (seccion 8 del spec).

Todo coeficiente, estado inicial, parametro estructural, umbral terminal y
politica default vive en estos archivos de datos, nunca hardcodeado en el
codigo de las transiciones.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from republica.world.state import Exogenous, Policy, WorldState

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class Structure(BaseModel):
    """Parametros estructurales (seccion 2.2)."""

    g_trend: float
    r_neutral: float
    pi_world: float
    u_nat: float
    reserves_target: float
    fx_debt_share: float


class ExogenousProcess(BaseModel):
    """Proceso AR(1) de las exogenas (seccion 2.1)."""

    commodity_persistence: float
    commodity_noise_std: float
    world_persistence: float
    world_noise_std: float


class TaylorParams(BaseModel):
    """Coeficientes de la regla de Taylor (seccion 2.3)."""

    pi_coef: float
    response: float
    pi_target: float


class Terminal(BaseModel):
    """Umbrales de fin de partida y de la devaluacion forzada (seccion 6.1)."""

    collapse_stability: float
    collapse_months: int
    hyper_inflation: float
    hyper_months: int
    devaluation_reserves: float
    devaluation_cooldown_months: int
    devaluation_fx_multiplier: float
    devaluation_reserve_injection: float
    devaluation_pi_shock: float
    devaluation_conf_shock: float


class Coefficients(BaseModel):
    """Todos los coeficientes de las secciones 4 y 5, mas las referencias/umbrales
    (`*_ref`, `*_base`, `*_threshold`, `*_neutral`) que las formulas restan o
    comparan. Los divisores puramente de escala (/100, /10, /12) se mantienen
    como literales en el codigo por ser forma de formula, no calibracion.
    """

    # 4.1 actividad
    a_r: float
    r_gap_min: float
    r_gap_max: float
    a_f: float
    a_c: float
    a_x: float
    a_w: float
    a_t: float
    # 4.2 tipo de cambio
    b_res: float
    b_r: float
    b_conf: float
    b_x: float
    b_band: float
    b_int: float
    # 4.3 inflacion
    rho_pi: float
    c_e: float
    c_g: float
    c_f: float
    c_r: float
    # 4.4 desempleo
    d_g: float
    d_n: float
    d_w: float
    # 4.5 salario real
    w_idx: float
    w_prod: float
    w_g: float
    w_u: float
    # 4.6 fiscal y deuda
    f_rev: float
    f_u: float
    debt_interest_rate: float
    # 4.7 reservas
    k_tb: float
    k_w: float
    k_k: float
    k_conf: float
    # 4.8 pobreza
    p_u: float
    p_w: float
    p_i: float
    p_adj: float
    # 5.1 confianza del consumidor
    s_g: float
    s_u: float
    s_pi: float
    s_w: float
    s_adj: float
    # 5.2 desigualdad
    q_pi: float
    q_u: float
    q_w: float
    q_t: float
    # 5.3 tension social
    t_u: float
    t_p: float
    t_pi: float
    t_w: float
    t_c: float
    t_pr: float
    t_adj: float
    # 5.4 protesta
    pr_t: float
    pr_a: float
    pr_adj: float
    # 5.5 percepcion de inseguridad
    cr_u: float
    cr_p: float
    cr_t: float
    cr_adj: float
    # 5.6 aprobacion
    e_w: float
    e_u: float
    e_pi: float
    e_pi_low: float
    e_g: float
    e_t: float
    e_rev: float
    # 5.7 congreso
    cg_a: float
    cg_adj: float
    # 5.8 confianza institucional
    ic_rev: float
    ic_pi: float
    ic_s: float
    # 5.9 estabilidad politica
    st_a: float
    st_c: float
    st_t: float
    st_i: float
    st_adj: float
    # provincias (fin seccion 7)
    province_transfer_sensitivity: float
    # referencias / umbrales compartidos entre formulas
    u_ref: float
    pi_ref: float
    pi_ref_conf: float
    wage_ref: float
    growth_ref: float
    inequality_ref: float
    poverty_ref: float
    tension_base: float
    tension_threshold: float
    protest_ref: float
    conf_ref: float
    conf_neutral: float
    approval_ref: float
    approval_reversion: float
    congress_ref: float
    cc_base: float
    crime_base: float
    stability_base: float
    transfers_ref: float


class Province(BaseModel):
    """Una fila de `provinces.csv` (seccion 8)."""

    id: str
    name: str
    population_k: float
    gdp_share: float
    main_sector: str
    governor_party: str
    u_offset: float
    dependence: float


class Party(BaseModel):
    """Una entrada de `parties.json` (seccion 8)."""

    id: str
    name: str
    seats: int
    economic: float
    social: float
    in_government: bool
    is_ally: bool = False
    coalition_weight: float = 1.0


class Country(BaseModel):
    """Configuracion completa del pais: todo lo que el motor necesita para correr."""

    name: str
    start: dict[str, int]
    months: int
    initial_state: WorldState
    exogenous: Exogenous
    structure: Structure
    exogenous_process: ExogenousProcess
    taylor: TaylorParams
    coefficients: Coefficients
    default_policy: Policy
    policy_ranges: dict[str, tuple[float, float]]
    ranges: dict[str, tuple[float, float]]
    terminal: Terminal
    provinces: list[Province]
    parties: list[Party]
    coalition_seats: float
    shocks: list[dict[str, Any]]
    config_hash: str
    #: `features.actors` (ADR 003 secc. 7): default `True` si `country.json`
    #: no trae la clave (la CLI `republica run` prende actores por defecto;
    #: `--no-actors` la apaga). No confundir con el default `False` de
    #: `engine.simulation.run()`/`Game.new()` como *funciones* (ver Notas de
    #: implementacion): ese default se mantiene apagado para no romper
    #: llamadores existentes que no piden actores explicitamente.
    features: dict[str, bool] = {"actors": True}


def _load_provinces(path: Path) -> list[Province]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [
            Province(
                id=row["id"],
                name=row["name"],
                population_k=float(row["population_k"]),
                gdp_share=float(row["gdp_share"]),
                main_sector=row["main_sector"],
                governor_party=row["governor_party"],
                u_offset=float(row["u_offset"]),
                dependence=float(row["dependence"]),
            )
            for row in reader
        ]


def _load_parties(path: Path) -> list[Party]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Party.model_validate(item) for item in raw]


def _coalition_seats(parties: list[Party]) -> float:
    """`coalition_seats` (seccion 8): bancas propias + aliadas ponderadas."""
    total = 0.0
    for p in parties:
        if p.in_government:
            total += p.seats
        elif p.is_ally:
            total += p.coalition_weight * p.seats
    return total


def load_country(data_dir: Path | str | None = None) -> Country:
    """Carga `country.json`, `provinces.csv`, `parties.json` y `shocks.json`."""
    d = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    country_path = d / "country.json"
    raw = json.loads(country_path.read_text(encoding="utf-8"))
    config_hash = hashlib.sha256(country_path.read_bytes()).hexdigest()

    provinces = _load_provinces(d / "provinces.csv")
    parties = _load_parties(d / "parties.json")
    shocks = json.loads((d / "shocks.json").read_text(encoding="utf-8"))

    return Country(
        name=raw["name"],
        start=raw["start"],
        months=raw["months"],
        initial_state=WorldState.model_validate(raw["initial_state"]),
        exogenous=Exogenous.model_validate(raw["exogenous"]),
        structure=Structure.model_validate(raw["structure"]),
        exogenous_process=ExogenousProcess.model_validate(raw["exogenous_process"]),
        taylor=TaylorParams.model_validate(raw["taylor"]),
        coefficients=Coefficients.model_validate(raw["coefficients"]),
        default_policy=Policy.model_validate(raw["default_policy"]),
        policy_ranges={k: tuple(v) for k, v in raw["policy_ranges"].items()},
        ranges={k: tuple(v) for k, v in raw["ranges"].items()},
        terminal=Terminal.model_validate(raw["terminal"]),
        provinces=provinces,
        parties=parties,
        coalition_seats=_coalition_seats(parties),
        shocks=shocks,
        config_hash=config_hash,
        features=raw.get("features", {"actors": True}),
    )
