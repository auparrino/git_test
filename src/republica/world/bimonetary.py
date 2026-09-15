"""Sector externo bimonetario (ADR 011 secc. 5, `features.bimonetary`).

Bloque de variables NUEVO, fuera de las 20 de `WorldState` (que es un
`pydantic` `frozen=True` fijado por Aurora: agregarle campos cambiaria
`ranges`/`clamp_state`/el hash de cada corrida de Aurora -- ver Notas de
implementacion del ADR 011 sobre por que este bloque vive aparte, en
`MonthRecord.external`, en vez de adentro de `WorldState`). Como
`world/regime.py`, es puramente aditivo: sin invocarlo desde `engine/
simulation.py::run(bimonetary_coeffs=...)` no cambia nada.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from republica.world.state import WorldState, clamp, pos


@dataclass(frozen=True)
class BimonetaryCoefficients:
    """`country.json -> bimonetary` (Argentina; con valores de diseno por
    default para cualquier otro pais que prenda el feature sin definir el
    bloque -- ver Notas de implementacion del ADR 011: NO calibrados contra
    series reales, eso es A3)."""

    dollar_demand_init: float = 0.35
    fx_gap_init: float = 0.0
    external_debt_usd_init_pct_gdp: float = 30.0
    default_risk_init: float = 0.05
    fx_regime_default: str = "float"
    dd_pi: float = 0.01
    dd_r: float = 0.004
    dd_conf: float = 0.006
    dd_gap: float = 0.15
    dd_persistence: float = 0.9
    gap_control: float = 0.5
    debt_fx_share: float = 0.65
    default_risk_debt_reserves: float = 0.35
    default_risk_fiscal: float = 0.03
    default_risk_threshold: float = 0.7

    @classmethod
    def from_dict(cls, raw: dict | None) -> BimonetaryCoefficients:
        if not raw:
            return cls()
        coeffs = dict(raw.get("coefficients", {}))
        return cls(
            dollar_demand_init=raw.get("dollar_demand_init", 0.35),
            fx_gap_init=raw.get("fx_gap_init", 0.0),
            external_debt_usd_init_pct_gdp=raw.get("external_debt_usd_init_pct_gdp", 30.0),
            default_risk_init=raw.get("default_risk_init", 0.05),
            fx_regime_default=raw.get("fx_regime_default", "float"),
            **{k: v for k, v in coeffs.items() if k in cls.__dataclass_fields__},
        )


@dataclass
class ExternalState:
    """El bloque `external` de `MonthRecord` (ADR 011 secc. 5)."""

    dollar_demand: float
    fx_gap: float
    external_debt_usd: float
    default_risk: float
    fx_regime: str

    def to_dict(self) -> dict:
        return asdict(self)


def init_external_state(
    coeff: BimonetaryCoefficients, fx_regime: str | None = None
) -> ExternalState:
    return ExternalState(
        dollar_demand=coeff.dollar_demand_init,
        fx_gap=coeff.fx_gap_init,
        external_debt_usd=coeff.external_debt_usd_init_pct_gdp,
        default_risk=coeff.default_risk_init,
        fx_regime=fx_regime or coeff.fx_regime_default,
    )


def step_bimonetary(
    prev: ExternalState,
    state: WorldState,
    real_rate: float,
    coeff: BimonetaryCoefficients,
) -> ExternalState:
    """Un mes de la seccion 5 del ADR. `state` es el `WorldState` YA avanzado
    a `t+1` (economia/sociedad/politica del mes ya corrieron); `real_rate` es
    `r_real` de ese mismo mes (`Aux.r_real` de `world/economy.py`).

    - `dollar_demand`: sube con inflacion (anualizada, > referencia de 2%
      mensual), con confianza institucional baja y con la brecha cambiaria;
      baja con tasa real positiva (ADR 011 secc. 5). AR(1) con persistencia
      `dd_persistence` para que no salte de un mes a otro.
    - `fx_gap`: solo > 0 bajo `fx_regime == "control"` (ADR 011 secc. 5,
      literal: "brecha oficial/paralelo cuando hay control de cambios"),
      proporcional a `dollar_demand`.
    - `external_debt_usd` (% PIB): revalorizada por la devaluacion real via
      `debt_fx_share`, igual que `public_debt` en `world/economy.py` pero
      aparte (la deuda EN DOLARES no cambia de valor en dolares al devaluar
      en pesos -- lo que sube es su peso relativo sobre variables en pesos;
      se aproxima con la misma forma funcional que Aurora ya usa para
      `public_debt`, ver Notas de implementacion).
    - `default_risk`: sube con el ratio deuda/reservas y con el deficit
      fiscal, acotado a `[0, 1]`.
    """
    dd_target = clamp(
        prev.dollar_demand
        + coeff.dd_pi * pos(state.inflation - 2.0)
        - coeff.dd_r * pos(real_rate)
        + coeff.dd_conf * pos(50.0 - state.institutional_confidence) / 100.0
        + coeff.dd_gap * prev.fx_gap,
        0.0,
        1.0,
    )
    dollar_demand = clamp(
        coeff.dd_persistence * prev.dollar_demand + (1.0 - coeff.dd_persistence) * dd_target,
        0.0,
        1.0,
    )

    fx_gap = coeff.gap_control * dollar_demand if prev.fx_regime == "control" else 0.0

    external_debt_usd = max(
        0.0,
        prev.external_debt_usd
        + (-state.fiscal_balance) / 12.0 * coeff.debt_fx_share
        - prev.external_debt_usd * state.gdp_growth / 1200.0,
    )

    reserves_ratio = external_debt_usd / max(state.reserves, 1.0)
    default_risk = clamp(
        coeff.default_risk_debt_reserves * pos(reserves_ratio - 1.0)
        + coeff.default_risk_fiscal * pos(-state.fiscal_balance),
        0.0,
        1.0,
    )

    return ExternalState(
        dollar_demand=dollar_demand,
        fx_gap=fx_gap,
        external_debt_usd=external_debt_usd,
        default_risk=default_risk,
        fx_regime=prev.fx_regime,
    )
