"""Etapa 1: transiciones economicas, desde el snapshot `t` (seccion 3-4 del spec)."""

from __future__ import annotations

import math
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


#: Efectos proporcionales de los shocks historicos de ADR 011 secc. 4 (P2,
#: A3) que un termino aditivo de `shocks.json` no puede expresar: anular un
#: coeficiente (`k_k=0`, credito cerrado) o escalar uno (`debt_interest_rate
#: *0.5`, "la deuda no se paga") en vez de sumarle una constante, y aplicar
#: un delta de POLITICA (`primary_spending -1.5`, condicionalidad del FMI)
#: que dura exactamente lo que dura el shock -- no uno persistente-
#: acumulativo como el mecanismo de `policy_*` en `pending_terms`/
#: `concessions_delta` (pensado para concesiones de ADR 003/005 que se
#: suman una vez y quedan, ver `engine/simulation.py::advance_month`).
#: `apply_historical_shock_effects` arma un `Coefficients`/`Policy`
#: modificados a partir de que shocks estan activos ESTE mes (`sim.
#: active_shocks`, ya calculado por `ShockCatalog.apply_month` antes de
#: llamar a esta funcion) y se los pasa a `step_economy` como argumentos
#: normales -- CERO cambios a la firma de `step_economy` (sigue recibiendo
#: un `Coefficients`/`Policy` cualquiera, no sabe que vinieron ajustados).
SOVEREIGN_DEFAULT_INTEREST_MULTIPLIER = 0.5
IMF_PROGRAM_PRIMARY_SPENDING_DELTA = -1.5


def apply_historical_shock_effects(
    coeff: Coefficients, policy: Policy, active_shock_ids: set[str] | frozenset[str]
) -> tuple[Coefficients, Policy]:
    """`(coeff, policy)` ajustados por `sovereign_default`/`imf_program`
    activos (ADR 011 secc. 4, P2 de A3). Sin ninguno de los dos activos,
    devuelve `coeff`/`policy` tal cual (mismo objeto, sin `model_copy`) --
    corridas sin esos shocks quedan bit a bit iguales."""
    if "sovereign_default" in active_shock_ids:
        coeff = coeff.model_copy(
            update={
                "k_k": 0.0,
                "debt_interest_rate": coeff.debt_interest_rate
                * SOVEREIGN_DEFAULT_INTEREST_MULTIPLIER,
            }
        )
    if "imf_program" in active_shock_ids:
        policy = policy.model_copy(
            update={
                "primary_spending": policy.primary_spending + IMF_PROGRAM_PRIMARY_SPENDING_DELTA
            }
        )
    return coeff, policy


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
        + coeff.k_k * clamp(r_gap, coeff.r_gap_min, coeff.r_gap_max)
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


# ---------------------------------------------------------------------------
# ADR 012 -- macro con regimen: expectativas, tipo de cambio efectivo y
# balance de pagos (`features.macro_regime`, default off).
#
# `step_macro_economy` es un WRAPPER separado, NO una rama dentro de
# `step_economy`: `step_economy` queda sin ningun cambio de codigo (la unica
# edicion de este archivo antes de este bloque es el `import math` de arriba,
# que no cambia ningun valor devuelto). `engine/simulation.py::advance_month`
# llama a `step_economy` como siempre cuando `sim.macro_state is None`
# (default) y a esta funcion en caso contrario -- ver Notas de
# implementacion del ADR 012 para el porque de este disenio (cero riesgo
# sobre el golden hash de Aurora y sobre cualquier corrida sin `macro_state`).
#
# Reusa sin cambios las secciones 4.1 (actividad), 4.4 (desempleo), 4.5
# (salario real), 4.6 (fiscal/deuda) y 4.8 (pobreza) de `step_economy`
# (duplicadas aca a proposito, ver Notas de implementacion: extraerlas a un
# helper comun arriesgaba introducir una diferencia de comportamiento en
# `step_economy` mismo). Reemplaza 4.2 (tipo de cambio), 4.3 (inflacion) y
# 4.7 (reservas) por ADR 012 secc. 2-4.
# ---------------------------------------------------------------------------


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


#: Alias de `float` usado SOLO por los campos `lf_*` de ADR 016. Es un
#: `float` en todo sentido salvo uno: `calibration/parameters.py::
#: MACRO_TUNABLE` arma el vector de CMA-ES con
#: `[name for name, f in MacroCoefficients.__dataclass_fields__.items()
#: if f.type in ("float", float)]`, y con `from __future__ import
#: annotations` ese `f.type` es la CADENA de la anotacion. Anotar los `lf_*`
#: con este alias los deja fuera del vector calibrable a proposito: son
#: parametros ESTRUCTURALES (la afirmacion historica de ADR 016 secc. 3 --
#: dos salidas anticipadas en diez mandatos, las dos con ruptura monetaria),
#: no grados de libertad para ajustar contra series. Calibrarlos convertiria
#: la hipotesis del ADR en un parametro ajustado hasta que de, que es
#: justamente lo que prohibe `PLAN_ARGENTINA.md` secc. 0 regla 3. Ademas
#: mantiene `MACRO_TUNABLE` en 58 campos, sin tocar `calibration/*` (de otro
#: agente).
StructuralFloat = float

#: Campos de ADR 016: estructurales, nunca calibrados (ver `StructuralFloat`).
#: `calibration/run.py::load_calibrated_country` reconstruye
#: `MacroCoefficients(**raw["macro"])` desde un `coefficients.json` que no
#: los trae (las calibraciones existentes, `a5b_macro` incluida, guardan 60
#: claves y ninguna `lf_*`), asi que una calibracion cargada se quedaria con
#: los DEFAULTS de esta clase en vez de los valores de
#: `country.json -> macro.coefficients`. `merge_structural_coefficients`
#: repara eso en los dos lugares que combinan una calibracion con un paquete
#: (`cli.py` y `validation/argentina.py::run_test_arm`).
LEGITIMACY_FIELDS = (
    "lf_base",
    "lf_min",
    "lf_rupture_inflation",
    "lf_rupture_months",
    "lf_exit_window_months",
)


def merge_structural_coefficients(
    calibrated: MacroCoefficients, pack: MacroCoefficients
) -> MacroCoefficients:
    """Devuelve `calibrated` con los campos ESTRUCTURALES de ADR 016
    (`LEGITIMACY_FIELDS`) tomados de `pack` (los de
    `country.json -> macro.coefficients`). Ver `LEGITIMACY_FIELDS` para el
    porque: sin esto, `--calibration <run_id>` ignoraria en silencio los
    `lf_*` del paquete de pais."""
    from dataclasses import replace

    return replace(calibrated, **{name: getattr(pack, name) for name in LEGITIMACY_FIELDS})


@dataclass(frozen=True)
class MacroCoefficients:
    """`country.json -> macro -> coefficients` (ADR 012). Todos los valores
    por default son los que trae el ADR, literales, salvo donde el ADR solo
    da la FORMA (no un numero): esos se documentan en `docs/
    ADR_012_argentine_macro.md` seccion "Notas de implementacion" con la
    razon del valor elegido. Pensado igual que `BimonetaryCoefficients`: un
    pais que prende `features.macro_regime` sin definir `macro` en su
    `country.json` recibe estos defaults."""

    # -- secc. 2: precios con expectativas y dominancia fiscal --
    w_adapt: float = 0.7
    rho_pi: float = 0.85
    rho_slope: float = 0.10
    pi_hi: float = 5.0
    md_0: float = 0.12
    md_pi: float = 0.08
    c_e: float = 0.06
    c_g: float = 0.5
    c_r: float = 1.0
    #: El ADR da `c_s = 0.06` como valor de referencia ("reemplaza a
    #: c_f·pos(deficit-2)"). Retuneado a 0.006 (documentado en detalle en
    #: `docs/ADR_012_argentine_macro.md` seccion "Notas de implementacion"):
    #: con 0.06 el termino de senioreaje, dividido por `money_demand` (~0.12
    #: en el baseline), amplifica ~8x el viejo `c_f=0.12·pos(deficit-2)` --
    #: con el deficit fiscal cronico que genera `interest_cost = public_debt
    #: · debt_interest_rate` (formula de 4.6, sin cambios, reusada tal cual)
    #: para Argentina en `financeable_normal=2`, eso hace que CUALQUIER
    #: arranque con deficit moderado (incluido 2003-06, donde la hipotesis
    #: registrada es 0 % de semillas) cruce el umbral de indexacion corta
    #: (`pi_hi`) e "hipertrofie" via `rho_eff`, violando el test 2 del ADR
    #: (no espuria desde 2003-06). Un primer barrido (18 meses, test 2 del
    #: ADR) sugeria 0.006-0.007 como limite superior, pero esos valores
    #: SI diverfen (via el mismo mecanismo, mas lento) sobre el horizonte
    #: LARGO del test de recuperacion (secc. 5/test 5: 2003-06 -> 2015-12,
    #: 150 meses): a 0.005 ya cruzan 20/20 semillas antes de 2015-12. 0.0045
    #: es el mayor valor (barrido en pasos de 0.0005 sobre 20 semillas, dos
    #: horizontes) que deja 2003-06 en 0/20 cruces de 20 % mensual en 18
    #: meses Y en 20/20 semillas sobreviviendo (`outcome == "survived"`)
    #: hasta 2015-12, con 1988-06 en 20/20 (el ADR solo pide ≥ 50 %) cruzando
    #: 20 % en 18 meses.
    c_s: float = 0.0045
    c_gap: float = 1.0
    financeable_normal: float = 2.0
    financeable_default: float = 0.0
    pi_anchor_ema_months: float = 36.0

    # -- secc. 3: regimen cambiario efectivo --
    x_d: float = 5.0
    rm: float = 3.0
    k_int: float = 20.0
    crawl_rate: float = 2.0
    control_de_admin: float = 3.0
    g1: float = 0.05
    g2: float = 0.05
    g3: float = 0.05
    k_gap: float = 5.0
    peg_capital_boost: float = 3.0
    peg_default_risk_ceiling: float = 0.3
    exit_shock_conf: float = -15.0
    exit_banking_crisis_p: float = 0.5
    banking_crisis_months: int = 6
    banking_crisis_k_k_multiplier: float = 0.0
    banking_crisis_tension_bump: float = 10.0
    gap_perception_k: float = 0.05
    dd_pi: float = 0.01
    dd_r: float = 0.004
    dd_conf: float = 0.006
    dd_gap: float = 0.15
    dd_persistence: float = 0.9

    # -- secc. 4: balance de pagos --
    x0_m0_pct_gdp: float = 0.18
    ex_c: float = 0.5
    ex_e: float = 0.5
    im_y: float = 1.0
    im_e: float = 0.5
    im_gap: float = 0.3
    debt_interest_rate_usd: float = 0.06
    k_k_bop: float = 50.0
    #: El ADR no da un numero (solo la forma `- k_flight · dollar_demand`,
    #: secc. 4), para `float`/`control`. Ver `k_flight_peg` (debajo) y Notas
    #: de implementacion del ADR 012: subir ESTE `k_flight` lo suficiente
    #: para que el test 3 (salida forzada de un `peg`) se dispare desde
    #: 1998-01 en 54 meses (`k_flight >= 3000`) rompe el test 5 (recuperacion
    #: 2003-06 -> 2015-12, `float`): de 20/20 semillas sobreviviendo a 1/20.
    #: El motivo economico del split: bajo `float`, mas `dollar_demand`
    #: presiona el PRECIO (via `de_raw`, secc. 3, ahora que `dollar_demand`
    #: lo alimenta) -- el tipo de cambio absorbe la fuga de capitales, las
    #: reservas se defienden solas. Bajo `peg`/`crawl`, `de` esta fijo por
    #: definicion: la MISMA fuga de capitales se convierte 1 a 1 en perdida
    #: de reservas (no hay ajuste de precio que la amortigue). Un solo
    #: `k_flight` para los cuatro regimenes fuerza a elegir entre "realista
    #: para `peg`" (reservas fragiles) y "realista para `float`" (reservas
    #: estables); separarlo por regimen (`k_flight_peg` abajo) evita el
    #: trade-off.
    k_flight: float = 200.0
    #: `k_flight` (arriba) pero solo para `peg`/`crawl` (ver el porque en su
    #: docstring): calibrado igual que el `k_flight` del barrido original
    #: descrito en Notas de implementacion (200/800/2000/2500/3000/3500/5000
    #: -> 0/0/2/8/14/18/20 de 20 semillas saliendo del peg de 1998-01 antes
    #: del mes 54) -- 3000.0 deja el test 3 en 14/20 (70 % >= 50 %) con
    #: meses de salida no degenerados (10-15) y, al NO tocar `float`/
    #: `control`, el test 5 queda en 20/20 (ver test de regresion en
    #: `tests/test_macro_regime.py`).
    k_flight_peg: float = 3000.0
    amort_rate: float = 0.004
    imf_disbursement: float = 300.0
    default_risk_a: float = 1.0
    default_risk_b: float = 1.0
    default_risk_c: float = 0.3
    default_risk_threshold: float = 0.5

    # -- secc. 5: recuperacion de largo plazo --
    ic_rec: float = 0.01
    ic_target_base: float = 45.0
    ic_target_bonus: float = 10.0
    ic_crisis_free_months: int = 12
    t_rec: float = 0.02
    recovery_inflation_max: float = 3.0
    recovery_unemployment_max: float = 10.0
    e_rev_sentiment_k: float = 10.0

    # -- ADR 016 secc. 3: piso de estabilidad por legitimidad democratica --
    # Solo los lee `world/events.py::legitimacy_stability_floor`, y solo
    # corren con `features.legitimacy_floor` prendido (default OFF: un pais
    # que no declara el feature no siente ninguno de estos campos).
    #: Piso de `political_stability` al INICIO del mandato, en una democracia
    #: (`repression == 0`) sin ruptura aguda. Por encima de
    #: `terminal.collapse_stability` (15 en Argentina): un gobierno recien
    #: electo no tiene salida anticipada por impopularidad.
    lf_base: StructuralFloat = 28.0
    #: Piso al FINAL del mandato (la legitimidad de origen se gasta). Sigue
    #: por encima de `collapse_stability`: mientras el mandato corre y no hay
    #: ruptura, la salida anticipada no esta disponible -- el poder
    #: discriminante del mecanismo vive en la definicion de ruptura, no aca
    #: (ADR 016 secc. 3, "riesgo declarado").
    lf_min: StructuralFloat = 18.0
    #: Inflacion mensual (%) a partir de la cual el mes cuenta como
    #: "regimen hiperinflacionario" para la compuerta de ruptura. 15 %/mes
    #: son ~435 % anuales: 1989 (tres digitos mensuales) califica; 2019-2023
    #: (maximo ~13 %/mes hasta 2023-11) no.
    lf_rupture_inflation: StructuralFloat = 15.0
    #: Meses consecutivos por encima de `lf_rupture_inflation` para que la
    #: ruptura hiperinflacionaria se considere activa (mismo criterio de
    #: persistencia que `terminal.hyper_months`).
    lf_rupture_months: int = 3
    #: Meses, contados desde un `fx_regime_exit` forzado (ADR 012 secc. 3),
    #: durante los cuales el piso queda suspendido. El default (600) es
    #: deliberadamente mayor que cualquier mandato: en la practica significa
    #: "por el resto del mandato en curso" -- el gobierno que rompio el
    #: regimen monetario (De la Rua, enero de 2002) no puede invocar su
    #: legitimidad de origen. El contador se reinicia en cada eleccion.
    lf_exit_window_months: int = 600

    @classmethod
    def from_dict(cls, raw: dict | None) -> MacroCoefficients:
        if not raw:
            return cls()
        coeffs = dict(raw.get("coefficients", {}))
        return cls(**{k: v for k, v in coeffs.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class MacroState:
    """Estado persistente entre meses de ADR 012 secc. 2-5 (fuera de las 20
    variables de `WorldState`, igual que `bimonetary.ExternalState`, del que
    es independiente: un pais puede tener `bimonetary_coefficients` y
    `macro_coefficients` a la vez -- `engine/simulation.py::run` apaga el
    canal viejo de `bimonetary` cuando el nuevo esta activo para no
    duplicar/contradecir `dollar_demand`/`fx_gap`/`default_risk`, ver Notas
    de implementacion)."""

    fx_regime: str
    pi_anchor_ema: float
    fx_gap: float
    dollar_demand: float
    rer: float
    external_debt_usd: float
    default_risk: float
    months_since_crisis: int
    banking_crisis_months_left: int
    exit_count: int
    #: `X0`/`M0` (ADR 012 secc. 4): constantes de USD/mes fijadas UNA vez al
    #: iniciar la corrida (`init_macro_state`, desde `gdp_usd` real de
    #: `history/` cuando existe -- `world/countries.py::x0_m0_from_gdp_usd`
    #: -- o el proxy `0.18*gdp_usd/12` documentado en el ADR). NO se
    #: recalculan mes a mes: las formulas de `exports`/`imports` las
    #: multiplican por factores adimensionales (`commodity_price/100`,
    #: `gdp/100`, `rer/100`), tal como esta escrito el ADR.
    x0: float
    m0: float

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)


#: Fallback generico de `X0`/`M0` (USD M/mes) para un pais/corrida sin
#: `gdp_usd` real disponible (ADR 012 secc. 4 no dice que hacer en ese caso;
#: Argentina siempre tiene `history/gdp_usd.csv` desde 1983, asi que esto
#: solo importa para un pais hipotetico sin historia -- documentado, no
#: ejercitado por los tests del ADR).
DEFAULT_X0_M0_USD_M = 1000.0


def init_macro_state(
    coeff: MacroCoefficients,
    fx_regime: str,
    initial_inflation: float,
    external_debt_usd_init: float,
    x0: float = DEFAULT_X0_M0_USD_M,
    m0: float = DEFAULT_X0_M0_USD_M,
    dollar_demand_init: float = 0.35,
) -> MacroState:
    return MacroState(
        fx_regime=fx_regime,
        pi_anchor_ema=initial_inflation,
        fx_gap=0.0,
        dollar_demand=dollar_demand_init,
        rer=100.0,
        external_debt_usd=external_debt_usd_init,
        default_risk=0.05,
        months_since_crisis=0,
        banking_crisis_months_left=0,
        exit_count=0,
        x0=x0,
        m0=m0,
    )


@dataclass(frozen=True)
class MacroAux:
    """Auxiliares propios de ADR 012 (narracion/tests), analogo a `Aux` mas
    arriba pero con lo que agrega el balance de pagos."""

    exports: float
    imports: float
    current_account: float
    capital_account: float
    r_min: float
    pi_anchor: float
    pi_exp: float
    rho_eff: float
    seigniorage_pressure: float


def step_macro_economy(
    state: WorldState,
    exo: Exogenous,
    exo_new: Exogenous,
    policy: Policy,
    shocks: ShockAggregate,
    structure: Structure,
    coeff: Coefficients,
    macro_coeff: MacroCoefficients,
    macro: MacroState,
    active_shock_ids: set[str] | frozenset[str],
    rng: random.Random,
) -> tuple[WorldState, Aux, MacroAux, MacroState, list[str], dict[str, float]]:
    """Un mes de ADR 012 secc. 2-4. Devuelve `(new_state, aux, macro_aux,
    new_macro, events, pending)`: `events` son nuevos eventos de este mes
    (`fx_regime_exit`, `banking_crisis`) para sumar a `MonthRecord.events`
    (mismo patron que `world/events.py::check_forced_devaluation`); `pending`
    son terminos que se aplican el MES QUE VIENE via `sim.pending_terms`
    (idem `check_forced_devaluation`: un `shock_conf`/`shock_approval` de la
    salida de una convertibilidad no es instantaneo per ADR, se lee "dispara"
    -- se defiere un mes para no tener que reabrir el clamp/orden de este
    mes, igual que ya hace el resto del motor con sus propios `pending`).
    """
    events: list[str] = []
    pending: dict[str, float] = {}

    interest_rate_new = policy.interest_rate_target
    r_real = interest_rate_new - 12.0 * state.inflation
    r_gap = r_real - structure.r_neutral
    deficit = -state.fiscal_balance
    u_gap = state.unemployment - structure.u_nat
    reserves_gap = pos(structure.reserves_target - state.reserves) / structure.reserves_target
    interest_cost = state.public_debt * coeff.debt_interest_rate
    delta_commodity = exo_new.commodity_price - exo.commodity_price

    # 4.1 actividad (identica a `step_economy`, ver docstring del modulo)
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

    # -- balance de pagos (secc. 4): exports/imports con el `rer`/`fx_gap`
    # DEL MES PASADO (`macro.rer`/`macro.fx_gap`, conocidos al empezar el
    # mes) y el `gdp` de ESTE mes -- necesarios ya para `R_min` antes de
    # resolver el regimen cambiario.
    exports = (
        macro.x0
        * ((max(exo_new.commodity_price, 1.0) / 100.0) ** macro_coeff.ex_c)
        * ((max(macro.rer, 1.0) / 100.0) ** macro_coeff.ex_e)
    )
    imports = (
        macro.m0
        * ((max(gdp_new, 1.0) / 100.0) ** macro_coeff.im_y)
        * ((max(macro.rer, 1.0) / 100.0) ** (-macro_coeff.im_e))
        * (1.0 + macro_coeff.im_gap * macro.fx_gap)
    )
    r_min = macro_coeff.rm * imports

    # -- secc. 3: regimen cambiario efectivo --
    # `dollar_demand` "pasa a alimentar de_raw" (ADR 012 secc. 3, prosa
    # justo debajo de la tabla, EN GENERAL -- no solo para `float`, cuya
    # fila de la tabla es el UNICO lugar con una formula explicita,
    # `de_raw + x_d · dollar_demand`): se suma aca, una sola vez, para que
    # `crawl`/`peg` (via `pressure = pos(de_raw - rate)` mas abajo) y
    # `control` (via `fx_gap`, que ya usa `dollar_demand_lag` aparte) vean
    # la MISMA presion de dolarizacion que `float`, en vez de que solo
    # `float` la sienta. Sin esto, un `peg`/`crawl` nunca gasta reservas
    # por fuga de capitales via el canal de "defensa" (`intervention_usd`)
    # -- solo via `capital_account` en el balance de pagos (secc. 4) -- y
    # el test 3 del ADR (salida forzada de un `peg` con reservas bajas)
    # nunca se dispara en absoluto desde 1998-01 real en 54 meses (ver
    # Notas de implementacion: `dollar_demand` ahi solo se mueve por
    # inflacion/confianza, `dd_pi`/`dd_conf`, y ninguna de esas dos
    # condiciones se cruza en esa ventana con los shocks tal como estan
    # calibrados).
    dollar_demand_lag = macro.dollar_demand
    de_raw = (
        state.inflation
        - structure.pi_world
        + coeff.b_res * reserves_gap
        - coeff.b_r * r_gap / 100.0
        + coeff.b_conf * (coeff.conf_neutral - state.institutional_confidence) / 100.0
        - coeff.b_x * delta_commodity / 100.0
        + macro_coeff.x_d * dollar_demand_lag
        + shocks.term("shock_fx")
    )

    fx_regime = macro.fx_regime
    fx_regime_next = fx_regime
    banking_crisis_triggered = False
    excess = 0.0

    if fx_regime == "float":
        de_pre = de_raw
        cap = state.inflation + coeff.b_band
        excess = pos(de_pre - cap)
        intervention_usd = coeff.b_int * policy.fx_intervention * excess * (gdp_new / 100.0)
        if state.reserves < intervention_usd:
            de = de_pre
            intervention_usd = 0.0
        else:
            de = de_pre - policy.fx_intervention * excess
    elif fx_regime in ("crawl", "peg"):
        rate = 0.0 if fx_regime == "peg" else macro_coeff.crawl_rate
        if state.reserves > r_min:
            pressure = pos(de_raw - rate)
            intervention_usd = macro_coeff.k_int * pressure * (gdp_new / 100.0)
            if intervention_usd >= state.reserves:
                # No alcanza para defender: devaluacion forzada de todos
                # modos, se gasta lo que queda (secc. 3, columna "Salida").
                intervention_usd = state.reserves
                de = de_raw
                fx_regime_next = "float"
                events.append("fx_regime_exit")
            else:
                de = rate
        else:
            de = de_raw
            intervention_usd = 0.0
            fx_regime_next = "float"
            events.append("fx_regime_exit")
        if fx_regime == "peg" and "fx_regime_exit" in events:
            pending["shock_conf"] = pending.get("shock_conf", 0.0) + macro_coeff.exit_shock_conf
            if rng.random() < macro_coeff.exit_banking_crisis_p:
                banking_crisis_triggered = True
    else:  # "control"
        de = macro_coeff.control_de_admin
        intervention_usd = 0.0

    if fx_regime_next == "control" or fx_regime == "control":
        fx_regime_next = "control"
        fx_gap = clamp(
            macro.fx_gap
            + macro_coeff.g1 * (dollar_demand_lag - macro_coeff.g2 * r_real)
            - macro_coeff.g3 * macro.fx_gap,
            0.0,
            200.0,
        )
    else:
        fx_gap = 0.0

    if banking_crisis_triggered:
        events.append("banking_crisis")
        banking_crisis_months_left = macro_coeff.banking_crisis_months
        pending["shock_tension"] = pending.get("shock_tension", 0.0) + (
            macro_coeff.banking_crisis_tension_bump
        )
    else:
        banking_crisis_months_left = max(0, macro.banking_crisis_months_left - 1)

    exchange_rate_new = state.exchange_rate * (1.0 + de / 100.0)

    # -- secc. 2: precios con expectativas y dominancia fiscal --
    if fx_regime == "peg":
        pi_anchor = 0.0 + structure.pi_world
    elif fx_regime == "crawl":
        pi_anchor = macro_coeff.crawl_rate + structure.pi_world
    else:
        pi_anchor = macro.pi_anchor_ema

    pi_exp = macro_coeff.w_adapt * state.inflation_lag1 + (1.0 - macro_coeff.w_adapt) * pi_anchor
    rho_eff = macro_coeff.rho_pi + macro_coeff.rho_slope * clamp(
        (state.inflation_lag1 - macro_coeff.pi_hi) / macro_coeff.pi_hi, 0.0, 2.0
    )
    money_demand = macro_coeff.md_0 * math.exp(-macro_coeff.md_pi * state.inflation_lag1)
    financeable = (
        macro_coeff.financeable_default
        if "sovereign_default" in active_shock_ids
        else macro_coeff.financeable_normal
    )
    seigniorage_pressure = pos(deficit - financeable) / max(money_demand, 1e-6)

    inflation_new = (
        rho_eff * state.inflation
        + macro_coeff.c_e * de
        + macro_coeff.c_g * demand_gap
        + macro_coeff.c_s * seigniorage_pressure
        - macro_coeff.c_r * r_gap / 100.0
        + (1.0 - rho_eff) * pi_exp
        + (macro_coeff.c_gap * fx_gap if fx_regime_next == "control" else 0.0)
        + shocks.term("shock_pi")
    )

    alpha = 2.0 / (macro_coeff.pi_anchor_ema_months + 1.0)
    pi_anchor_ema_new = macro.pi_anchor_ema + alpha * (inflation_new - macro.pi_anchor_ema)

    if fx_regime_next == "control":
        pending["shock_approval"] = pending.get("shock_approval", 0.0) - (
            macro_coeff.gap_perception_k * fx_gap
        )

    # 4.4 desempleo (identica a `step_economy`)
    unemployment_new = (
        state.unemployment
        - coeff.d_g * demand_gap
        - coeff.d_n * (state.unemployment - structure.u_nat)
        + coeff.d_w * pos(state.real_wage - coeff.wage_ref) / 100.0
        + shocks.term("shock_u")
    )

    # 4.5 salario real (identica)
    wage_growth_nominal = (
        coeff.w_idx * state.inflation_lag1
        + coeff.w_prod
        + coeff.w_g * demand_gap
        - coeff.w_u * u_gap / 10.0
    )
    real_wage_new = state.real_wage * (1.0 + (wage_growth_nominal - inflation_new) / 100.0)

    # 4.6 fiscal y deuda (identica)
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

    # -- secc. 4: balance de pagos, reemplaza 4.7 --
    interest_paid_usd = macro.external_debt_usd * macro_coeff.debt_interest_rate_usd / 12.0
    current_account = exports - imports - interest_paid_usd
    k_k_eff = macro_coeff.k_k_bop * (
        macro_coeff.peg_capital_boost
        if (fx_regime == "peg" and macro.default_risk < macro_coeff.peg_default_risk_ceiling)
        else 1.0
    )
    if banking_crisis_months_left > 0:
        k_k_eff *= macro_coeff.banking_crisis_k_k_multiplier
    amortizations = macro.external_debt_usd * macro_coeff.amort_rate
    disbursements = (
        macro_coeff.imf_disbursement
        if ("imf_program" in active_shock_ids and "sovereign_default" not in active_shock_ids)
        else 0.0
    )
    # `r_gap` recortado a `[r_gap_min, r_gap_max]` antes de multiplicarlo por
    # `k_k_eff` (igual que `coeff.k_k * clamp(r_gap, ...)` en `step_economy`
    # 4.7, y por la misma razon: con inflacion mensual alta `r_real =
    # interest_rate - 12·inflation` se va a valores muy negativos --
    # `12·inflation` anualiza una tasa MENSUAL linealmente, sin capitalizar
    # -- y sin este recorte una corrida hiperinflacionaria vacia las
    # reservas en un mes via el canal de capitales, antes de que el canal de
    # precios (secc. 2) pueda actuar).
    r_gap_clamped = clamp(r_gap, coeff.r_gap_min, coeff.r_gap_max)
    # `k_flight` vs `k_flight_peg` (secc. 4, ver docstring de ambos en
    # `MacroCoefficients`): bajo `peg`/`crawl` el tipo de cambio esta FIJO
    # (o casi), asi que la fuga de capitales que la misma `dollar_demand`
    # representa se traduce integramente en perdida de reservas -- no hay
    # ajuste de precio (`de`) que la absorba como en `float`.
    k_flight_eff = (
        macro_coeff.k_flight_peg if fx_regime_next in ("peg", "crawl") else macro_coeff.k_flight
    )
    capital_account = (
        (k_k_eff * r_gap_clamped if macro.default_risk < 0.5 else 0.0)
        - k_flight_eff * dollar_demand_lag
        - amortizations
        + disbursements
    )
    reserves_new = (
        state.reserves
        + current_account
        + capital_account
        - intervention_usd
        + shocks.term("shock_reserves")
    )

    financing_gap = pos(-(current_account + capital_account - disbursements))
    external_debt_usd_new = max(
        0.0, macro.external_debt_usd + financing_gap - amortizations + disbursements
    )
    exports_12m = max(exports * 12.0, 1.0)
    imports_3m = max(imports * 3.0, 1.0)
    default_risk_new = clamp(
        _sigmoid(
            macro_coeff.default_risk_a * (external_debt_usd_new / exports_12m)
            - macro_coeff.default_risk_b * (reserves_new / imports_3m)
            + macro_coeff.default_risk_c * pos(deficit_new - 2.0)
        ),
        0.0,
        1.0,
    )

    rer_new = macro.rer * (1.0 + (de - (inflation_new - structure.pi_world)) / 100.0)
    rer_new = max(rer_new, 1.0)

    dd_target = clamp(
        dollar_demand_lag
        + macro_coeff.dd_pi * pos(inflation_new - 2.0)
        - macro_coeff.dd_r * pos(r_real)
        + macro_coeff.dd_conf * pos(50.0 - state.institutional_confidence) / 100.0
        + macro_coeff.dd_gap * fx_gap,
        0.0,
        1.0,
    )
    dollar_demand_new = clamp(
        macro_coeff.dd_persistence * dollar_demand_lag
        + (1.0 - macro_coeff.dd_persistence) * dd_target,
        0.0,
        1.0,
    )

    # 4.8 pobreza (identica)
    poverty_target = (
        coeff.poverty_ref
        + coeff.p_u * (unemployment_new - coeff.u_ref)
        - coeff.p_w * (real_wage_new - coeff.wage_ref)
        + coeff.p_i * (state.inequality - coeff.inequality_ref)
    )
    poverty_new = state.poverty + coeff.p_adj * (poverty_target - state.poverty)

    crisis_this_month = (
        inflation_new > macro_coeff.pi_hi or "sovereign_default" in active_shock_ids or bool(events)
    )
    months_since_crisis_new = 0 if crisis_this_month else min(macro.months_since_crisis + 1, 9999)

    new_macro = MacroState(
        fx_regime=fx_regime_next,
        pi_anchor_ema=pi_anchor_ema_new,
        fx_gap=fx_gap,
        dollar_demand=dollar_demand_new,
        rer=rer_new,
        external_debt_usd=external_debt_usd_new,
        default_risk=default_risk_new,
        months_since_crisis=months_since_crisis_new,
        banking_crisis_months_left=banking_crisis_months_left,
        exit_count=macro.exit_count + (1 if "fx_regime_exit" in events else 0),
        x0=macro.x0,
        m0=macro.m0,
    )

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
    macro_aux = MacroAux(
        exports=exports,
        imports=imports,
        current_account=current_account,
        capital_account=capital_account,
        r_min=r_min,
        pi_anchor=pi_anchor,
        pi_exp=pi_exp,
        rho_eff=rho_eff,
        seigniorage_pressure=seigniorage_pressure,
    )
    return new_state, aux, macro_aux, new_macro, events, pending
