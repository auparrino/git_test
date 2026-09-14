"""Etapa 2 (parte politica): secciones 5.6 a 5.9, usan la economia y la
sociedad ya en `t+1`."""

from __future__ import annotations

from republica.world.config import Coefficients
from republica.world.events import ShockAggregate
from republica.world.state import WorldState, clamp, pos


def step_politics(
    prev: WorldState,
    new: WorldState,
    demand_gap: float,
    coalition_seats: float,
    shocks: ShockAggregate,
    coeff: Coefficients,
) -> WorldState:
    """`prev` es el snapshot `t`; `new` ya tiene economia y sociedad en `t+1`
    (salida de `step_society`). Devuelve `new` con government_approval,
    congress_support, institutional_confidence y political_stability
    actualizados.
    """
    # 5.6 aprobacion del gobierno
    delta_wage_pct = (new.real_wage - prev.real_wage) / prev.real_wage * 100.0
    delta_unemployment = new.unemployment - prev.unemployment
    approval_new = (
        prev.government_approval
        + coeff.e_w * delta_wage_pct
        - coeff.e_u * delta_unemployment
        - coeff.e_pi * pos(new.inflation - coeff.pi_ref)
        + coeff.e_pi_low * (coeff.pi_ref - clamp(new.inflation, 0.0, coeff.pi_ref))
        + coeff.e_g * demand_gap
        - coeff.e_t * pos(new.social_tension - coeff.tension_threshold) / 10.0
        + coeff.e_rev * (coeff.approval_reversion - prev.government_approval)
        + shocks.term("shock_approval")
    )

    # 5.7 apoyo en el congreso
    congress_target = coalition_seats + coeff.cg_a * (approval_new - coeff.approval_ref)
    congress_new = (
        prev.congress_support
        + coeff.cg_adj * (congress_target - prev.congress_support)
        + shocks.term("shock_congress")
    )

    # 5.8 confianza institucional (lenta)
    institutional_confidence_new = (
        prev.institutional_confidence
        + coeff.ic_rev * (coeff.conf_neutral - prev.institutional_confidence)
        - coeff.ic_pi * pos(new.inflation - coeff.pi_ref_conf)
        + coeff.ic_s * (prev.political_stability - coeff.stability_base) / 10.0
        + shocks.term("shock_conf")
    )

    # 5.9 estabilidad politica
    stability_target = (
        coeff.stability_base
        + coeff.st_a * (approval_new - coeff.approval_ref)
        + coeff.st_c * (congress_new - coeff.congress_ref)
        - coeff.st_t * (new.social_tension - coeff.tension_base)
        + coeff.st_i * (institutional_confidence_new - coeff.conf_ref)
    )
    stability_new = (
        prev.political_stability
        + coeff.st_adj * (stability_target - prev.political_stability)
        + shocks.term("shock_stability")
    )

    return new.model_copy(
        update={
            "government_approval": approval_new,
            "congress_support": congress_new,
            "institutional_confidence": institutional_confidence_new,
            "political_stability": stability_new,
        }
    )
