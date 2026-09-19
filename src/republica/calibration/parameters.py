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

ADR 017 secc. 1 corrige el grupo `"coefficients"` en modo macro: se
EXCLUYEN los 8 campos que solo lee el motor legacy `step_economy` (ver
`MACRO_UNUSED_LEGACY_COEFFICIENTS`), porque con `features.macro_regime`
prendido la simulacion nunca los usa y CMA-ES los dejaba en cualquier lado
-- `rho_pi = 2.298` en `a5b_macro`, que despues desbordaba el modo anual.
Vector de modo macro: 89 (`Coefficients`) + 58 (`MacroCoefficients`) = 147.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

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

#: ADR 017 secc. 1: coeficientes de `Coefficients` que el motor LEGACY
#: (`world/economy.py::step_economy`) lee y el motor MACRO
#: (`step_macro_economy`) NO. Lista obtenida comparando las referencias
#: `coeff.<campo>` del cuerpo de las dos funciones (`step_economy` lee 44
#: campos, `step_macro_economy` 36, y los 36 son un subconjunto de los 44),
#: y verificada contra el resto del motor: ningun otro modulo
#: (`society.py`/`politics.py`/`elections.py`/`perception.py`) los lee, asi
#: que con `features.macro_regime` prendido estos 8 NO TOCAN la simulacion
#: y, por lo tanto, no cambian la funcion objetivo ni una decima.
#:
#: Consecuencia medida en `a5b_macro` (ver el hallazgo de `docs/
#: ADR_014_rolling_backtest.md`): CMA-ES los movio libre (solo los frenaba
#: la L2 debil de `lambda_reg=0.01`) hasta `rho_pi = 2.298` -- un AR(1) de
#: precios con coeficiente 2.3, explosivo por construccion. Eso no importa
#: en modo mensual con macro (nunca se ejecuta `step_economy`) pero rompe
#: `world/annual.py`, que usa SIEMPRE el motor legacy: las 135 ventanas
#: anuales 1916-1960 del backtest `b1_a5b` perdieron el 100 % de sus
#: semillas calibradas por `OverflowError` en `(1 + g_m/100)**12`.
#:
#: Cada uno, y de que bloque legacy es:
#: - `rho_pi`, `c_e`, `c_r`, `c_g`, `c_f`: ecuacion de precios legacy
#:   (secc. 4.3 del spec), reemplazada entera por ADR 012 secc. 2.
#: - `k_w`: canal salarial legacy (4.4). `k_tb`: balanza comercial legacy
#:   (4.5). `k_conf`: confianza institucional legacy (4.6).
#: Los 36 que SI comparten los dos motores (`a_*`, `b_*`, `p_*`, `w_*`,
#: `d_*`, `f_*`, `k_k`, ...) se QUEDAN en el vector: la calibracion con
#: macro les da senal real.
MACRO_UNUSED_LEGACY_COEFFICIENTS = (
    "rho_pi",
    "c_e",
    "c_r",
    "c_g",
    "c_f",
    "k_w",
    "k_tb",
    "k_conf",
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

#: Parametro -> variable de `WorldState` contra la que se COMPARA (una
#: referencia, un objetivo de reversion o un umbral). El rango de esos
#: parametros tiene que caer DENTRO del rango fisico de esa variable, que
#: `clamp_state` hace cumplir: es la misma razon que ya acotaba
#: `default_risk_threshold` a [0,1], aplicada a una clase entera que se
#: habia pasado por alto.
#:
#: Por que importa, con los numeros de `a7_by_regime` (ADR 018, y la sonda
#: de ADR 020): la calibracion dejo `approval_reversion = 135.0` en el grupo
#: `peg` y `tension_threshold = 117.0`, para variables acotadas a [0, 100].
#: Las dos formas de romperse:
#:
#: - **Objetivo por encima del techo** (`approval_reversion = 135`,
#:   `tension_base = 140..208`): el termino `rec * (objetivo - x)` NUNCA
#:   cambia de signo, asi que empuja a la variable contra su cota y la deja
#:   clavada ahi para siempre. Ningun termino de recuperacion puede
#:   despegarla -- ADR 018 lo midio: +14.4/mes de empuje contra -3.9/mes de
#:   recuperacion. La saturacion que la sonda encontro es, en buena parte,
#:   un artefacto de calibracion, no una propiedad del modelo.
#: - **Umbral por encima del techo** (`tension_threshold = 110.7/117.0`):
#:   `pos(x - umbral)` vale SIEMPRE 0, asi que el termino esta muerto y el
#:   coeficiente que lo multiplica no significa nada. El canal
#:   tension->aprobacion de ADR 016 no existia bajo esta calibracion.
#:
#: En los dos casos CMA-ES no hace nada malo: minimiza la perdida en un
#: espacio donde esas regiones son alcanzables. El arreglo es no ofrecerselas.
COMPARED_AGAINST_STATE_VAR: dict[str, str] = {
    "approval_ref": "government_approval",
    "approval_reversion": "government_approval",
    "tension_base": "social_tension",
    "tension_threshold": "social_tension",
    "protest_ref": "protest_level",
    "crime_base": "crime_perception",
    "stability_base": "political_stability",
}


def _state_var_ranges() -> dict[str, tuple[float, float]]:
    """Rangos fisicos de `WorldState` segun Aurora (`ranges` de
    `country.json`), que es la misma tabla que usa `clamp_state`."""
    from republica.world.config import load_country

    return {k: (float(lo), float(hi)) for k, (lo, hi) in load_country().ranges.items()}


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


@lru_cache(maxsize=1)
def excluded_legacy_values() -> dict[str, float]:
    """Valor FIJO de cada coeficiente de `MACRO_UNUSED_LEGACY_COEFFICIENTS`
    (ADR 017 secc. 1): el de Aurora en el `country.json` del paquete
    (mismo `aurora_value` que tendrian si siguieran en el vector). Se
    aplica sobre el `base` en `coefficients_from_vector` cuando el vector
    es de modo macro, para que el `coefficients.json` de la corrida (y la
    simulacion misma) traigan estos 8 en un valor sensato en vez de en lo
    que haya quedado en `base` -- `calibration/run.py` usa
    `load_country().coefficients` (Aurora generico) como `base`, no el
    `country.json` de Argentina.

    Cacheado (`lru_cache`): se llama una vez por evaluacion de candidato en
    cada worker y leer el JSON cada vez seria caro sin ninguna razon (el
    archivo no cambia durante una corrida)."""
    aurora = load_aurora_coefficients()
    return {name: aurora[name] for name in MACRO_UNUSED_LEGACY_COEFFICIENTS}


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
    var = COMPARED_AGAINST_STATE_VAR.get(name)
    if var is not None:
        rango = _state_var_ranges().get(var)
        if rango is not None:
            var_lo, var_hi = rango
            return max(lo, var_lo), min(hi, var_hi)
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

    `include_macro=True` (A5, ADR 012 secc. 6; revisado por ADR 017 secc. 1):
    89 de `Coefficients` + `MACRO_TUNABLE` (58) = 147 -- SIN
    `BIMONETARY_TUNABLE` (`engine/simulation.py::run` desactiva el canal
    bimonetario viejo en cuanto hay `macro_coefficients`, ver Notas de
    implementacion del ADR 012, asi que tunear esos 10 coeficientes en modo
    macro gastaria presupuesto de CMA-ES en dimensiones sin ningun efecto
    sobre la simulacion) y SIN los 8 de
    `MACRO_UNUSED_LEGACY_COEFFICIENTS` (mismo argumento, medido: con macro
    activo la simulacion nunca llama a `step_economy`, asi que esos 8 no
    cambian la perdida y CMA-ES los deja en cualquier lado -- ver el
    comentario de esa constante)."""
    aurora_coeff = load_aurora_coefficients()
    params: list[Parameter] = []
    excluded = set(MACRO_UNUSED_LEGACY_COEFFICIENTS) if include_macro else set()
    for name in Coefficients.model_fields:
        if name in excluded:
            continue
        value = aurora_coeff[name]
        lo, hi = _default_bounds(value)
        # El grupo `coefficients` no pasaba por `_apply_physical_bounds`:
        # era la unica de las tres ramas sin ese paso, y es justo donde
        # viven los objetivos y umbrales de `COMPARED_AGAINST_STATE_VAR`.
        lo, hi = _apply_physical_bounds(name, lo, hi)
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
    usar `Parameter.from_unit` antes).

    ADR 017 secc. 1: si `params` es un espacio de modo MACRO (tiene grupo
    `"macro"`), los 8 de `MACRO_UNUSED_LEGACY_COEFFICIENTS` -- que ya no
    estan en el vector -- se fijan explicitamente en el valor de Aurora del
    paquete (`excluded_legacy_values()`) en vez de heredar lo que traiga
    `base`. Asi el `Coefficients` resultante (el que se simula Y el que se
    escribe en `coefficients.json`) queda completo y en una zona sensata
    para el motor legacy de `world/annual.py`, que SI los lee."""
    updates = {}
    for p, v in zip(params, x, strict=True):
        if p.group == "coefficients":
            updates[p.name] = p.clip(v)
    if any(p.group == "macro" for p in params):
        updates.update(excluded_legacy_values())
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
        "#",
        "# ADR 017 secc. 1: en modo macro (grupo `macro` presente) NO aparecen aca los 8",
        "# coeficientes que solo lee el motor legacy `step_economy` (rho_pi, c_e, c_r, c_g,",
        "# c_f, k_w, k_tb, k_conf): la funcion objetivo con macro activo nunca los ejercita,",
        "# asi que quedan FIJOS en el valor de Aurora en vez de en el vector de CMA-ES.",
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
