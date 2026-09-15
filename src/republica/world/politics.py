"""Etapa 2 (parte politica): secciones 5.6 a 5.9, usan la economia y la
sociedad ya en `t+1`."""

from __future__ import annotations

from republica.world.config import Coefficients
from republica.world.economy import MacroCoefficients
from republica.world.events import ShockAggregate
from republica.world.state import WorldState, clamp, pos


def step_politics(
    prev: WorldState,
    new: WorldState,
    demand_gap: float,
    coalition_seats: float,
    shocks: ShockAggregate,
    coeff: Coefficients,
    macro_coeff: MacroCoefficients | None = None,
    months_since_crisis: int = 0,
) -> WorldState:
    """`prev` es el snapshot `t`; `new` ya tiene economia y sociedad en `t+1`
    (salida de `step_society`). Devuelve `new` con government_approval,
    congress_support, institutional_confidence y political_stability
    actualizados.

    `macro_coeff`/`months_since_crisis` (ADR 012 secc. 5, default `None`/`0`
    = comportamiento de siempre): con un `MacroCoefficients`, (a) el piso de
    reversion de `government_approval` deja de ser el `approval_reversion`
    fijo de `coeff` y pasa a `approval_reversion + e_rev_sentiment_k ·
    (consumer_confidence/100)` -- "el desgaste tiene piso si la economia va
    bien" (literal) usando `consumer_confidence` (ya en `new`, calculado por
    `step_society` antes que este modulo corra) como proxy de
    `economic_sentiment` (el ADR no define esa variable en ningun otro lado
    del motor, ver Notas de implementacion); y (b) `institutional_confidence`
    recupera hacia `ic_target = ic_target_base + ic_target_bonus ·
    [months_since_crisis >= ic_crisis_free_months]`.
    """
    # 5.6 aprobacion del gobierno
    delta_wage_pct = (new.real_wage - prev.real_wage) / prev.real_wage * 100.0
    delta_unemployment = new.unemployment - prev.unemployment
    approval_reversion_target = coeff.approval_reversion
    if macro_coeff is not None:
        approval_reversion_target = coeff.approval_reversion + macro_coeff.e_rev_sentiment_k * (
            new.consumer_confidence / 100.0
        )
    approval_new = (
        prev.government_approval
        + coeff.e_w * delta_wage_pct
        - coeff.e_u * delta_unemployment
        - coeff.e_pi * pos(new.inflation - coeff.pi_ref)
        + coeff.e_pi_low * (coeff.pi_ref - clamp(new.inflation, 0.0, coeff.pi_ref))
        + coeff.e_g * demand_gap
        - coeff.e_t * pos(new.social_tension - coeff.tension_threshold) / 10.0
        + coeff.e_rev * (approval_reversion_target - prev.government_approval)
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
    if macro_coeff is not None:
        ic_target = macro_coeff.ic_target_base + (
            macro_coeff.ic_target_bonus
            if months_since_crisis >= macro_coeff.ic_crisis_free_months
            else 0.0
        )
        institutional_confidence_new += macro_coeff.ic_rec * pos(
            ic_target - institutional_confidence_new
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
