"""Etapa 1: transiciones economicas, desde el snapshot `t` (seccion 3-4 del spec)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from republica.world.config import Coefficients, ExogenousProcess, Structure
from republica.world.events import ShockAggregate
from republica.world.state import Exogenous, Policy, WorldState, clamp, pos


@dataclass(frozen=True)
class Aux:
    """Variables auxiliares del mes (seccion 3), para narracion/tests."""

    r_real: float
    r_gap: float
    g_m: float
    demand_gap: float
    deficit: float
    u_gap: float
    reserves_gap: float
    interest_cost: float
    de: float
    excess: float
    intervention_usd: float
    revenue: float
    spending: float


def step_exogenous(
    exo: Exogenous,
    process: ExogenousProcess,
    rng: random.Random,
    noise_enabled: bool,
) -> tuple[float, float]:
    """Parte AR(1) + ruido de las exogenas (seccion 2.1, paso 1 de la seccion 7).

    Consume 2 `gauss` de `rng` (uno por exogena) cuando `noise_enabled`. Los
    bumps directos de shocks (`commodity_price +20`, etc.) se suman despues,
    una vez roleados los shocks (paso 2), para respetar el orden de consumo
    de RNG de la seccion 7 sin perder el efecto del mismo mes.
    """
    noise_c = rng.gauss(0.0, process.commodity_noise_std) if noise_enabled else 0.0
    noise_w = rng.gauss(0.0, process.world_noise_std) if noise_enabled else 0.0
    commodity_price = (
        100.0 + process.commodity_persistence * (exo.commodity_price - 100.0) + noise_c
    )
    world_demand = 100.0 + process.world_persistence * (exo.world_demand - 100.0) + noise_w
    return commodity_price, world_demand


def finalize_exogenous(
    commodity_price: float, world_demand: float, shocks: ShockAggregate
) -> Exogenous:
    """Suma los bumps directos de shocks sobre las exogenas ya calculadas."""
    return Exogenous(
        commodity_price=commodity_price + shocks.field_bumps.get("commodity_price", 0.0),
        world_demand=world_demand + shocks.field_bumps.get("world_demand", 0.0),
    )


def step_economy(
    state: WorldState,
    exo: Exogenous,
    exo_new: Exogenous,
    policy: Policy,
    shocks: ShockAggregate,
    structure: Structure,
    coeff: Coefficients,
) -> tuple[WorldState, Aux]:
    """Secciones 4.1 a 4.8, en orden. Devuelve el estado con el bloque
    economico actualizado (el resto de los campos queda igual que `state`,
    listo para que `step_society`/`step_politics` los completen) y `Aux`.
    """
    interest_rate_new = policy.interest_rate_target

    r_real = interest_rate_new - 12.0 * state.inflation
    r_gap = r_real - structure.r_neutral
    deficit = -state.fiscal_balance
    u_gap = state.unemployment - structure.u_nat
    reserves_gap = pos(structure.reserves_target - state.reserves) / structure.reserves_target
    interest_cost = state.public_debt * coeff.debt_interest_rate
    delta_commodity = exo_new.commodity_price - exo.commodity_price

    # 4.1 actividad
    g_m = (
        structure.g_trend
        - coeff.a_r * clamp(r_gap, coeff.r_gap_min, coeff.r_gap_max) / 100.0
        + coeff.a_f * (deficit - 3.0)
        + coeff.a_c * (state.consumer_confidence - coeff.cc_base) / 100.0
        + coeff.a_x * delta_commodity / 100.0
        + coeff.a_w * (exo_new.world_demand - 100.0) / 100.0
        - coeff.a_t * pos(state.social_tension - coeff.tension_threshold) / 100.0
        + shocks.term("shock_gdp")
    )
    demand_gap = g_m - structure.g_trend
    gdp_new = state.gdp * (1.0 + g_m / 100.0)
    annualized = ((1.0 + g_m / 100.0) ** 12 - 1.0) * 100.0
    gdp_growth_new = 0.7 * state.gdp_growth + 0.3 * annualized

    # 4.2 tipo de cambio
    de_raw = (
        state.inflation
        - structure.pi_world
        + coeff.b_res * reserves_gap
        - coeff.b_r * r_gap / 100.0
        + coeff.b_conf * (coeff.conf_neutral - state.institutional_confidence) / 100.0
        - coeff.b_x * delta_commodity / 100.0
        + shocks.term("shock_fx")
    )
    cap = state.inflation + coeff.b_band
    excess = pos(de_raw - cap)
    intervention_usd = coeff.b_int * policy.fx_intervention * excess * (state.gdp / 100.0)
    if state.reserves < intervention_usd:
        de = de_raw
        intervention_usd = 0.0
    else:
        de = de_raw - policy.fx_intervention * excess
    exchange_rate_new = state.exchange_rate * (1.0 + de / 100.0)

    # 4.3 inflacion
    inflation_new = (
        coeff.rho_pi * state.inflation
        + coeff.c_e * de
        + coeff.c_g * demand_gap
        + coeff.c_f * pos(deficit - 2.0)
        - coeff.c_r * r_gap / 100.0
        + shocks.term("shock_pi")
    )

    # 4.4 desempleo
    unemployment_new = (
        state.unemployment
        - coeff.d_g * demand_gap
        - coeff.d_n * (state.unemployment - structure.u_nat)
        + coeff.d_w * pos(state.real_wage - coeff.wage_ref) / 100.0
        + shocks.term("shock_u")
    )

    # 4.5 salario real (usa inflation_lag1, la inflacion del mes anterior al snapshot)
    wage_growth_nominal = (
        coeff.w_idx * state.inflation_lag1
        + coeff.w_prod
        + coeff.w_g * demand_gap
        - coeff.w_u * u_gap / 10.0
    )
    real_wage_new = state.real_wage * (1.0 + (wage_growth_nominal - inflation_new) / 100.0)

    # 4.6 resultado fiscal y deuda
    revenue = policy.tax_rate * (1.0 + coeff.f_rev * demand_gap)
    spending = policy.primary_spending + coeff.f_u * pos(u_gap)
    fiscal_balance_new = revenue - spending - interest_cost + shocks.term("shock_fiscal")
    deficit_new = -fiscal_balance_new
    public_debt_new = (
        state.public_debt
        + deficit_new / 12.0
        - state.public_debt * g_m / 100.0
        + state.public_debt * structure.fx_debt_share * (de - inflation_new) / 100.0
        + shocks.term("shock_debt")
    )

    # 4.7 reservas
    reserves_new = (
        state.reserves
        + coeff.k_tb * (exo_new.commodity_price - 100.0)
        + coeff.k_w * (exo_new.world_demand - 100.0)
        + coeff.k_k * r_gap
        - coeff.k_conf * pos(coeff.conf_neutral - state.institutional_confidence)
        - intervention_usd
        + shocks.term("shock_reserves")
    )

    # 4.8 pobreza
    poverty_target = (
        coeff.poverty_ref
        + coeff.p_u * (unemployment_new - coeff.u_ref)
        - coeff.p_w * (real_wage_new - coeff.wage_ref)
        + coeff.p_i * (state.inequality - coeff.inequality_ref)
    )
    poverty_new = state.poverty + coeff.p_adj * (poverty_target - state.poverty)

    new_state = state.model_copy(
        update={
            "gdp": gdp_new,
            "gdp_growth": gdp_growth_new,
            "inflation": inflation_new,
            "unemployment": unemployment_new,
            "real_wage": real_wage_new,
            "interest_rate": interest_rate_new,
            "exchange_rate": exchange_rate_new,
            "reserves": reserves_new,
            "public_debt": public_debt_new,
            "fiscal_balance": fiscal_balance_new,
            "poverty": poverty_new,
            "inflation_lag1": state.inflation,
        }
    )
    aux = Aux(
        r_real=r_real,
        r_gap=r_gap,
        g_m=g_m,
        demand_gap=demand_gap,
        deficit=deficit,
        u_gap=u_gap,
        reserves_gap=reserves_gap,
        interest_cost=interest_cost,
        de=de,
        excess=excess,
        intervention_usd=intervention_usd,
        revenue=revenue,
        spending=spending,
    )
    return new_state, aux
