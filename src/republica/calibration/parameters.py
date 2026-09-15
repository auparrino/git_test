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

Recalibracion A5 (ADR 012 secc. 6) agrega un cuarto grupo, `"macro"`: los
campos NUMERICOS de `world/economy.py::MacroCoefficients` que son
coeficientes de formula (secc. 2-5 del ADR) -- se excluyen
`banking_crisis_months`/`ic_crisis_free_months` (enteros: duraciones
institucionales fijas, no un coeficiente continuo de una formula, mismo
criterio que excluye `*_init`/`fx_regime_default` de arriba) y las dos
constantes de balance de pagos que NO son coeficientes de formula sino que
se resuelven de datos reales por fecha (`macro_x0`/`macro_m0`,
`world/countries.py::x0_m0_from_gdp_usd`, fuera de `MacroCoefficients`).
Rango default igual que arriba (`[v/3, 3v]`), salvo siete con una razon
FISICA (documentadas en `TIGHTER_BOUNDS_REASON`, mismo dict):

- `w_adapt`: peso de una combinacion convexa (`pi_exp = w_adapt*inflation_lag1
  + (1-w_adapt)*pi_anchor`, ADR 012 secc. 2) -- fuera de `[0, 1]` la
  "expectativa" deja de ser un promedio ponderado. Se acota a `[0, 1]`.
- `rho_pi`: persistencia BASE de la inflacion (antes de sumar `rho_slope`,
  ADR 012 secc. 2); valores muy bajos (< 0.5) contradicen la evidencia de
  alta inercia inflacionaria de cualquier episodio argentino, y valores
  cerca de o sobre 1 saturan `rho_eff` incluso sin inflacion alta (rompe la
  propiedad "converge con deficit financiable" que el ADR pide). Se acota a
  `[0.5, 1.0]` (pedido explicito de la tarea A5).
- `rho_slope`: cuanto sube la persistencia por encima de `pi_hi` (ADR 012
  secc. 2); un valor grande satura `rho_eff` de inmediato con cualquier
  inflacion mensual moderada, sin margen para el regimen "financiable ->
  converge" que motiva la formula. Se acota a `[0, 0.3]` (pedido explicito).
- `rm`: meses de importaciones que definen `R_min` (ADR 012 secc. 3); fuera
  de `[1, 6]` el ancla de reservas deja de ser un multiplo de importaciones
  con interpretacion economica razonable (1 mes es el piso operativo
  minimo citado en la literatura de reservas internacionales, 6 meses ya
  excede el maximo historico argentino declarado). Se acota a `[1, 6]`
  (pedido explicito).
- `default_risk_threshold` (macro): se compara contra `default_risk` de
  `MacroState`, que `world/economy.py::step_macro_economy` ya acota a
  `[0, 1]` (es una probabilidad, formula sigmoide de ADR 012 secc. 4) --
  mismo argumento que el homonimo bimonetario de arriba. Se acota a
  `[0, 1]`.
- `peg_default_risk_ceiling`: umbral de `default_risk` (idem, `[0, 1]`) que
  habilita `peg_capital_boost` (ADR 012 secc. 3, columna `peg`). Se acota a
  `[0, 1]`.
- `exit_banking_crisis_p`: PROBABILIDAD de que la salida de un `peg`
  dispare `banking_crisis` (ADR 012 secc. 3, columna "Salida"). Se acota a
  `[0, 1]`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from republica.world.bimonetary import BimonetaryCoefficients
from republica.world.config import DEFAULT_DATA_DIR, Coefficients
from republica.world.economy import MacroCoefficients

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

#: Coeficientes macro (ADR 012) AJUSTABLES: todos los campos de
#: `MacroCoefficients` salvo los dos enteros de duracion (ver docstring del
#: modulo). Orden = orden de declaracion en `MacroCoefficients` (secc.
#: 2 -> 3 -> 4 -> 5 del ADR), igual criterio de determinismo que
#: `Coefficients.model_fields`/`BIMONETARY_TUNABLE` de arriba.
MACRO_TUNABLE = tuple(
    name for name, f in MacroCoefficients.__dataclass_fields__.items() if f.type in ("float", float)
)

TIGHTER_BOUNDS_REASON: dict[str, str] = {
    "dd_persistence": "AR(1) de dollar_demand: persistencia >= 1 es no estacionaria (explota).",
    "default_risk_threshold": "se compara contra default_risk, acotado a [0,1] (es una "
    "probabilidad); un umbral fuera de [0,1] nunca o siempre dispara el default endogeno.",
    "gap_control": "fraccion de la brecha cambiaria trasladada a inflacion percibida: no puede "
    "superar 1 por construccion.",
    "w_adapt": "peso de una combinacion convexa (pi_exp = w_adapt*inflation_lag1 + "
    "(1-w_adapt)*pi_anchor, ADR 012 secc. 2): fuera de [0,1] deja de ser un promedio ponderado.",
    "rho_pi": "persistencia base de la inflacion (ADR 012 secc. 2): < 0.5 contradice la inercia "
    "inflacionaria observada, >= 1 satura rho_eff sin inflacion alta. Acotado a [0.5, 1.0] "
    "(pedido explicito de la recalibracion A5).",
    "rho_slope": "cuanto sube la persistencia por encima de pi_hi (ADR 012 secc. 2): un valor "
    "grande satura rho_eff con cualquier inflacion moderada. Acotado a [0, 0.3] (pedido "
    "explicito de la recalibracion A5).",
    "rm": "meses de importaciones que definen R_min (ADR 012 secc. 3): fuera de [1,6] deja de "
    "ser un multiplo de importaciones con interpretacion razonable de reservas. Acotado a "
    "[1, 6] (pedido explicito de la recalibracion A5).",
    "peg_default_risk_ceiling": "umbral de default_risk (probabilidad, acotada a [0,1] por "
    "step_macro_economy) que habilita peg_capital_boost (ADR 012 secc. 3).",
    "exit_banking_crisis_p": "probabilidad de que la salida de un peg dispare banking_crisis "
    "(ADR 012 secc. 3, columna 'Salida'): es una probabilidad, acotada a [0,1].",
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


def load_aurora_macro() -> dict[str, float]:
    """Valores de referencia de `MACRO_TUNABLE`: `country.json -> macro ->
    coefficients` de Argentina (los del ADR 012, algunos retuneados
    respecto del literal del ADR -- ver `docs/ADR_012_argentine_macro.md`
    seccion "Notas de implementacion") con fallback a `MacroCoefficients()`
    para cualquier campo que el paquete no traiga explicito (mismo patron
    que `load_aurora_bimonetary`)."""
    raw = json.loads(ARGENTINA_COUNTRY_JSON.read_text(encoding="utf-8"))
    macro = raw.get("macro") or {}
    coeffs = dict(macro.get("coefficients", {}))
    defaults = MacroCoefficients()
    return {name: coeffs.get(name, getattr(defaults, name)) for name in MACRO_TUNABLE}


def load_aurora_macro_coefficients() -> MacroCoefficients:
    """`MacroCoefficients` completo (los `MACRO_TUNABLE` de
    `load_aurora_macro` mas los dos campos enteros no ajustables) -- el
    objeto BASE sobre el que `macro_from_vector` aplica el vector de CMA-ES
    (mismo rol que `load_country().coefficients` para `coefficients_from_
    vector`: los campos NO tuneados (`banking_crisis_months`,
    `ic_crisis_free_months`) quedan en el valor de Argentina/ADR 012, no en
    el default generico, aunque hoy coincidan)."""
    raw = json.loads(ARGENTINA_COUNTRY_JSON.read_text(encoding="utf-8"))
    return MacroCoefficients.from_dict(raw.get("macro"))


#: Overrides de rango FISICO (ver docstring del modulo) por nombre de
#: parametro, dentro del grupo que corresponda: `(lo, hi)` reemplaza al
#: default `[v/3, 3v]` tal cual (no se intersecta con el).
_PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    # `dd_persistence` NO esta aca: su override (solo el HI, no el LO) se
    # aplica antes, en `_apply_physical_bounds` -- un `(lo, hi)` fijo aca
    # pisaria el LO default (`v/3`), que si tiene que preservarse.
    "default_risk_threshold": (0.0, 1.0),
    "gap_control": (0.0, 1.0),
    "w_adapt": (0.0, 1.0),
    "rho_pi": (0.5, 1.0),
    "rho_slope": (0.0, 0.3),
    "rm": (1.0, 6.0),
    "peg_default_risk_ceiling": (0.0, 1.0),
    "exit_banking_crisis_p": (0.0, 1.0),
}


def _apply_physical_bounds(name: str, lo: float, hi: float) -> tuple[float, float]:
    if name == "dd_persistence":
        return lo, min(hi, 0.99)
    if name in _PHYSICAL_BOUNDS:
        return _PHYSICAL_BOUNDS[name]
    return lo, hi


def build_parameter_space(include_macro: bool = False) -> list[Parameter]:
    """Los parametros de calibracion, en un orden fijo -- el orden es lo
    que define el vector `x` que ve CMA-ES, asi que tiene que ser
    deterministico entre corridas (y entre el checkpoint y el
    `coefficients.json` final).

    `include_macro=False` (default, compatibilidad con `a3_main`/ADR 011
    secc. 7): los ~107 parametros de siempre (97 de `Coefficients` +
    `BIMONETARY_TUNABLE`), orden `Coefficients.model_fields` seguido de
    `BIMONETARY_TUNABLE`.

    `include_macro=True` (A5, ADR 012 secc. 6): 97 de `Coefficients` +
    `MACRO_TUNABLE` (54) -- SIN `BIMONETARY_TUNABLE`: `engine/simulation.py
    ::run` desactiva el canal bimonetario viejo en cuanto hay
    `macro_coefficients` (ver Notas de implementacion del ADR 012), asi que
    tunear esos 10 coeficientes en modo macro gastaria presupuesto de
    CMA-ES en dimensiones sin ningun efecto sobre la simulacion."""
    aurora_coeff = load_aurora_coefficients()
    params: list[Parameter] = []
    for name in Coefficients.model_fields:
        value = aurora_coeff[name]
        lo, hi = _default_bounds(value)
        params.append(Parameter(name=name, group="coefficients", aurora_value=value, lo=lo, hi=hi))
    if include_macro:
        aurora_macro = load_aurora_macro()
        for name in MACRO_TUNABLE:
            value = aurora_macro[name]
            lo, hi = _default_bounds(value)
            reason = TIGHTER_BOUNDS_REASON.get(name)
            lo, hi = _apply_physical_bounds(name, lo, hi)
            params.append(
                Parameter(
                    name=name,
                    group="macro",
                    aurora_value=value,
                    lo=lo,
                    hi=hi,
                    tighter_reason=reason,
                )
            )
        return params
    aurora_bimon = load_aurora_bimonetary()
    for name in BIMONETARY_TUNABLE:
        value = aurora_bimon[name]
        lo, hi = _default_bounds(value)
        reason = TIGHTER_BOUNDS_REASON.get(name)
        lo, hi = _apply_physical_bounds(name, lo, hi)
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


def macro_from_vector(
    params: list[Parameter], x: list[float], base: MacroCoefficients
) -> MacroCoefficients:
    """Analogo a `bimonetary_from_vector` para el grupo `"macro"` (A5, ADR
    012 secc. 6). `base` sin actualizaciones (`params` sin grupo `"macro"`,
    p.ej. `build_parameter_space(include_macro=False)`) se devuelve tal
    cual."""
    from dataclasses import replace

    updates = {}
    for p, v in zip(params, x, strict=True):
        if p.group == "macro":
            updates[p.name] = p.clip(v)
    return replace(base, **updates) if updates else base


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
