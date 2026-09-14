"""Etapa 2 (parte social): secciones 5.1 a 5.5, usan la economia ya en `t+1`."""

from __future__ import annotations

from republica.world.config import Coefficients
from republica.world.events import ShockAggregate
from republica.world.state import Policy, WorldState, pos


def step_society(
    prev: WorldState, new: WorldState, policy: Policy, shocks: ShockAggregate, coeff: Coefficients
) -> WorldState:
    """`prev` es el snapshot `t`; `new` ya tiene el bloque economico en `t+1`
    (salida de `step_economy`). Devuelve `new` con consumer_confidence,
    inequality, social_tension, protest_level y crime_perception actualizados.
    """
    # 5.1 confianza del consumidor
    cc_target = (
        coeff.cc_base
        + coeff.s_g * (new.gdp_growth - coeff.growth_ref)
        - coeff.s_u * (new.unemployment - coeff.u_ref)
        - coeff.s_pi * pos(new.inflation - coeff.pi_ref)
        + coeff.s_w * (new.real_wage - coeff.wage_ref)
    )
    consumer_confidence_new = (
        prev.consumer_confidence
        + coeff.s_adj * (cc_target - prev.consumer_confidence)
        + shocks.field_bumps.get("consumer_confidence", 0.0)
    )

    # 5.2 desigualdad (lenta)
    inequality_new = (
        prev.inequality
        + coeff.q_pi * pos(new.inflation - coeff.pi_ref)
        + coeff.q_u * (new.unemployment - coeff.u_ref) / 10.0
        - coeff.q_w * (new.real_wage - coeff.wage_ref) / 100.0
        - coeff.q_t * (policy.provincial_transfers - coeff.transfers_ref) / 10.0
        + shocks.term("shock_ineq")
    )

    # 5.3 tension social
    tension_target = (
        coeff.tension_base
        + coeff.t_u * (new.unemployment - coeff.u_ref)
        + coeff.t_p * (new.poverty - coeff.poverty_ref)
        + coeff.t_pi * pos(new.inflation - coeff.pi_ref)
        - coeff.t_w * (new.real_wage - coeff.wage_ref)
        - coeff.t_c * (prev.institutional_confidence - coeff.conf_ref)
        + coeff.t_pr * (prev.protest_level - coeff.protest_ref)
    )
    social_tension_new = (
        prev.social_tension
        + coeff.t_adj * (tension_target - prev.social_tension)
        + shocks.term("shock_tension")
    )

    # 5.4 protesta
    protest_target = (
        coeff.protest_ref
        + coeff.pr_t * (social_tension_new - coeff.tension_base)
        - coeff.pr_a * (prev.government_approval - coeff.approval_ref)
    )
    protest_level_new = (
        prev.protest_level
        + coeff.pr_adj * (protest_target - prev.protest_level)
        + shocks.term("shock_protest")
    )

    # 5.5 percepcion de inseguridad (lenta)
    crime_target = (
        coeff.crime_base
        + coeff.cr_u * (new.unemployment - coeff.u_ref)
        + coeff.cr_p * (new.poverty - coeff.poverty_ref)
        + coeff.cr_t * (social_tension_new - coeff.tension_base)
    )
    crime_perception_new = prev.crime_perception + coeff.cr_adj * (
        crime_target - prev.crime_perception
    )

    return new.model_copy(
        update={
            "consumer_confidence": consumer_confidence_new,
            "inequality": inequality_new,
            "social_tension": social_tension_new,
            "protest_level": protest_level_new,
            "crime_perception": crime_perception_new,
        }
    )
