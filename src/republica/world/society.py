"""Etapa 2 (parte social): secciones 5.1 a 5.5, usan la economia ya en `t+1`."""

from __future__ import annotations

from republica.world.config import Coefficients
from republica.world.economy import MacroCoefficients
from republica.world.events import ShockAggregate
from republica.world.recovery import (
    RecoveryContext,
    recover_crime,
    recover_protest,
    recover_tension,
)
from republica.world.state import Policy, WorldState, pos


def step_society(
    prev: WorldState,
    new: WorldState,
    policy: Policy,
    shocks: ShockAggregate,
    coeff: Coefficients,
    perceived_inflation_agg: float | None = None,
    macro_coeff: MacroCoefficients | None = None,
    recovery: RecoveryContext | None = None,
) -> WorldState:
    """`prev` es el snapshot `t`; `new` ya tiene el bloque economico en `t+1`
    (salida de `step_economy`). Devuelve `new` con consumer_confidence,
    inequality, social_tension, protest_level y crime_perception actualizados.

    `perceived_inflation_agg` (ADR 005 secc. 3, default `None` = comportamiento
    de v0.1 sin tocar): con `features.cohorts`, `engine/simulation.py` pasa
    `Σ pop_share_c · perceived_inflation_c` (`world/cohorts.py::
    weighted_perceived_inflation`) para que `consumer_confidence` use la
    inflacion percibida en vez de la real en el termino `s_pi`.

    `macro_coeff` (ADR 012 secc. 5, default `None` = comportamiento de
    siempre): con un `MacroCoefficients`, la tension social recupera hacia
    `tension_base` (`t_rec · pos(tension − tension_base)`) los meses en que
    la inflacion y el desempleo estan bajos -- unico cambio de este modulo
    bajo el flag, el resto de secc. 5.1-5.5 queda igual.

    `recovery` (ADR 018, `features.political_recovery`, default `None` =
    comportamiento de siempre): con un `RecoveryContext` ENGANCHADO (tres
    meses consecutivos de alivio macro sin ruptura aguda), `social_tension`
    y `protest_level` reciben el termino de recuperacion hacia su valor de
    referencia (`world/recovery.py::recover_social`), aplicado sobre el
    valor ya calculado de secc. 5.3/5.4 y ANTES del `clamp` del motor. Es
    independiente de `macro_coeff`: el canal `t_rec` de ADR 012 secc. 5
    sigue corriendo igual, con sus umbrales absolutos (ver ADR 018 secc. 1.5
    sobre por que ese canal no alcanza)."""
    # 5.1 confianza del consumidor
    inflation_for_cc = (
        perceived_inflation_agg if perceived_inflation_agg is not None else new.inflation
    )
    cc_target = (
        coeff.cc_base
        + coeff.s_g * (new.gdp_growth - coeff.growth_ref)
        - coeff.s_u * (new.unemployment - coeff.u_ref)
        - coeff.s_pi * pos(inflation_for_cc - coeff.pi_ref)
        + coeff.s_w * (new.real_wage - coeff.wage_ref)
    )
    consumer_confidence_new = (
        prev.consumer_confidence
        + coeff.s_adj * (cc_target - prev.consumer_confidence)
        + shocks.field_bumps.get("consumer_confidence", 0.0)
        + shocks.term("shock_cc")
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
    if macro_coeff is not None:
        # ADR 012 secc. 5, literal: recuperacion de largo plazo, solo si la
        # inflacion y el desempleo de ESTE mes (`new`, ya con el bloque
        # economico de `t+1`) estan por debajo de los umbrales.
        recovering = (
            new.inflation < macro_coeff.recovery_inflation_max
            and new.unemployment < macro_coeff.recovery_unemployment_max
        )
        if recovering:
            social_tension_new -= macro_coeff.t_rec * pos(social_tension_new - coeff.tension_base)
    # ADR 018 secc. 2.1: el termino de recuperacion de la tension va ANTES
    # de la seccion 5.4, para que la protesta de ESTE mes vea la tension ya
    # aliviada por su termino `pr_t * (tension - tension_base)`.
    social_tension_new = recover_tension(social_tension_new, recovery)

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
    protest_level_new = recover_protest(protest_level_new, recovery)

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
    # ADR 018: quinta variable, APAGADA por default (`crime_rec = 0.0`).
    crime_perception_new = recover_crime(crime_perception_new, recovery)

    return new.model_copy(
        update={
            "consumer_confidence": consumer_confidence_new,
            "inequality": inequality_new,
            "social_tension": social_tension_new,
            "protest_level": protest_level_new,
            "crime_perception": crime_perception_new,
        }
    )
