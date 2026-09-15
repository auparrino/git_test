"""Espacio de parametros de la calibracion (A3, ADR 011 secc. 7 punto 1):
los ~90 coeficientes de `country.json -> coefficients` (97 en la practica,
`world/config.py::Coefficients`) mas los 10 coeficientes AJUSTABLES del
bloque bimonetario (`world/bimonetary.py::BimonetaryCoefficients` -- los
`*_init`/`fx_regime_default` son estado inicial/categorico, no coeficientes
de una formula, y quedan fuera del vector de calibracion).

Cada parametro tiene un rango (ver `bounds_for`): por default, `[v/3, 3v]`
(signo preservado: si `v<0` el rango tambien queda negativo) -- "±3x el
valor de Aurora" del ADR, interpretado como un factor de 3 hacia arriba o
hacia abajo, no una resta/suma que cruzaria cero. Tres parametros tienen un
rango mas angosto por una razon FISICA, no de gusto (documentado en
`TIGHTER_BOUNDS_REASON`, y volcado con su razon a `parameters.yaml`):

- `dd_persistence` (bimonetario, AR(1) de `dollar_demand`): un proceso
  AR(1) con persistencia >= 1 es no estacionario (explota o queda en un
  paseo aleatorio) -- se acota a `[v/3, 0.99]`.
- `default_risk_threshold` (bimonetario): se compara contra `default_risk`,
  que `world/bimonetary.py` ya acota a `[0, 1]` (es una probabilidad) --
  un umbral fuera de `[0, 1]` no tiene sentido (nunca o siempre dispara el
  default endogeno). Se acota a `[0, 1]`.
- `gap_control`: fraccion de la brecha cambiaria que se traduce en inflacion
  percibida (`world/bimonetary.py`); por construccion no puede superar 1
  (mas que el 100% de la brecha percibida no tiene interpretacion). Se
  acota a `[0, 1]`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from republica.world.bimonetary import BimonetaryCoefficients
from republica.world.config import DEFAULT_DATA_DIR, Coefficients

ARGENTINA_COUNTRY_JSON = DEFAULT_DATA_DIR / "countries" / "argentina" / "country.json"

#: Coeficientes bimonetarios AJUSTABLES (ver docstring del modulo): excluye
#: `*_init` (estado inicial de la corrida, no un coeficiente de formula) y
#: `fx_regime_default` (categorico).
BIMONETARY_TUNABLE = (
    "dd_pi",
    "dd_r",
    "dd_conf",
    "dd_gap",
    "dd_persistence",
    "gap_control",
    "debt_fx_share",
    "default_risk_debt_reserves",
    "default_risk_fiscal",
    "default_risk_threshold",
)

TIGHTER_BOUNDS_REASON: dict[str, str] = {
    "dd_persistence": "AR(1) de dollar_demand: persistencia >= 1 es no estacionaria (explota).",
    "default_risk_threshold": "se compara contra default_risk, acotado a [0,1] (es una "
    "probabilidad); un umbral fuera de [0,1] nunca o siempre dispara el default endogeno.",
    "gap_control": "fraccion de la brecha cambiaria trasladada a inflacion percibida: no puede "
    "superar 1 por construccion.",
}


def _default_bounds(value: float) -> tuple[float, float]:
    """`[v/3, 3v]` con signo preservado (ADR: "+-3x el valor de Aurora,
    sign-preserving"). `value == 0.0` no ocurre en los coeficientes de
    Argentina (ver `parameters.yaml` generado), pero se cubre igual con un
    rango simetrico pequeño para no dividir por cero."""
    if value == 0.0:
        return (-0.1, 0.1)
    lo, hi = sorted((value / 3.0, value * 3.0))
    return (lo, hi)


@dataclass(frozen=True)
class Parameter:
    name: str
    group: str  # "coefficients" | "bimonetary"
    aurora_value: float
    lo: float
    hi: float
    tighter_reason: str | None = None

    def clip(self, x: float) -> float:
        return min(self.hi, max(self.lo, x))

    def to_unit(self, x: float) -> float:
        """Escala `x` (en las unidades del coeficiente) a `[0, 1]` (lo que
        usa CMA-ES: ver `calibration/optimizer.py` -- todos los parametros
        en la misma escala ayuda a que las step-sizes de CMA-ES no esten
        dominadas por el que tiene el rango mas ancho)."""
        span = self.hi - self.lo
        if span == 0:
            return 0.5
        return (self.clip(x) - self.lo) / span

    def from_unit(self, u: float) -> float:
        u = min(1.0, max(0.0, u))
        return self.lo + u * (self.hi - self.lo)


def load_aurora_coefficients() -> dict[str, float]:
    raw = json.loads(ARGENTINA_COUNTRY_JSON.read_text(encoding="utf-8"))
    return dict(raw["coefficients"])


def load_aurora_bimonetary() -> dict[str, float]:
    raw = json.loads(ARGENTINA_COUNTRY_JSON.read_text(encoding="utf-8"))
    bimon = raw.get("bimonetary") or {}
    coeffs = dict(bimon.get("coefficients", {}))
    defaults = BimonetaryCoefficients()
    return {name: coeffs.get(name, getattr(defaults, name)) for name in BIMONETARY_TUNABLE}


def build_parameter_space() -> list[Parameter]:
    """Los ~107 parametros (97 de `Coefficients` + 10 bimonetarios
    ajustables), en un orden fijo (mismo orden que `Coefficients.
    model_fields` seguido de `BIMONETARY_TUNABLE`) -- el orden es lo que
    define el vector `x` que ve CMA-ES, asi que tiene que ser deterministico
    entre corridas (y entre el checkpoint y el `coefficients.json` final)."""
    aurora_coeff = load_aurora_coefficients()
    aurora_bimon = load_aurora_bimonetary()
    params: list[Parameter] = []
    for name in Coefficients.model_fields:
        value = aurora_coeff[name]
        lo, hi = _default_bounds(value)
        params.append(Parameter(name=name, group="coefficients", aurora_value=value, lo=lo, hi=hi))
    for name in BIMONETARY_TUNABLE:
        value = aurora_bimon[name]
        lo, hi = _default_bounds(value)
        reason = TIGHTER_BOUNDS_REASON.get(name)
        if name == "dd_persistence":
            hi = min(hi, 0.99)
        elif name in ("default_risk_threshold", "gap_control"):
            lo, hi = 0.0, 1.0
        params.append(
            Parameter(
                name=name,
                group="bimonetary",
                aurora_value=value,
                lo=lo,
                hi=hi,
                tighter_reason=reason,
            )
        )
    return params


def coefficients_from_vector(
    params: list[Parameter], x: list[float], base: Coefficients
) -> Coefficients:
    """`x` en las unidades NATIVAS de cada parametro (no `[0,1]`; para eso
    usar `Parameter.from_unit` antes)."""
    updates = {}
    for p, v in zip(params, x, strict=True):
        if p.group == "coefficients":
            updates[p.name] = p.clip(v)
    return base.model_copy(update=updates) if updates else base


def bimonetary_from_vector(
    params: list[Parameter], x: list[float], base: BimonetaryCoefficients
) -> BimonetaryCoefficients:
    from dataclasses import replace

    updates = {}
    for p, v in zip(params, x, strict=True):
        if p.group == "bimonetary":
            updates[p.name] = p.clip(v)
    return replace(base, **updates) if updates else base


def write_parameters_yaml(params: list[Parameter], out_path) -> None:
    """`calibration/parameters.yaml` (tarea A3 punto 3): un YAML simple
    (sin depender de PyYAML para escribir -- se escribe a mano, formato
    YAML valido) con `name, group, aurora_value, lo, hi` y `reason` cuando
    el rango es mas angosto que el default ±3x."""
    lines = [
        "# Espacio de parametros de la calibracion (A3, ADR 011 secc. 7).",
        "# Generado por republica.calibration.parameters.build_parameter_space -- no editar a",
        "# mano: se re-escribe solo, al principio de cada `republica calibrate`.",
        "parameters:",
    ]
    for p in params:
        lines.append(f"  - name: {p.name}")
        lines.append(f"    group: {p.group}")
        lines.append(f"    aurora_value: {p.aurora_value}")
        lines.append(f"    lo: {p.lo}")
        lines.append(f"    hi: {p.hi}")
        if p.tighter_reason:
            lines.append(f'    reason: "{p.tighter_reason}"')
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
