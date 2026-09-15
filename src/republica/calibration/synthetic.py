"""Generador de "historia" sintetica (A3, ADR 011 secc. 9.9): corre Aurora
con coeficientes PERTURBADOS conocidos y usa esa trayectoria como si fuera
la serie real, para verificar que `calibrate` recupera los coeficientes
perturbados (test de identificabilidad). Vive en el paquete de calibracion
(no en `tests/`) porque la tarea A3 pide reusarlo -- A4 (validacion
historica) tambien puede necesitar generar corridas sinteticas."""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, replace
from pathlib import Path

from republica.calibration.parameters import Parameter, load_aurora_macro_coefficients
from republica.engine.simulation import run
from republica.world.config import Coefficients, load_country
from republica.world.economy import MacroCoefficients


@dataclass
class SyntheticPerturbation:
    param_name: str
    aurora_value: float
    true_value: float
    fraction: float  # +-0.4 = 40%


#: Coeficientes que aparecen DIRECTAMENTE en `world/economy.py::step_economy`
#: (secciones 4.1-4.7: actividad, tipo de cambio, inflacion, desempleo,
#: salario real, fiscal/deuda, reservas) -- el subconjunto de `Coefficients`
#: que puede, en principio, dejar una huella en las 5 variables que puntua
#: `calibration/objective.py` (`inflation`, `gdp_growth`, `unemployment`,
#: `exchange_rate`, `reserves`). El test de identificabilidad (ADR 011 secc.
#: 9.9) perturba SOLO de este subconjunto: perturbar, por ejemplo, `st_i`
#: (que solo entra en `political_stability`, una variable que el objetivo
#: NO puntua) probaria si el optimizador puede recuperar un coeficiente
#: invisible para su propia funcion objetivo -- eso no es un test de
#: identificabilidad, es un test de un objetivo mal especificado. Ver Notas
#: de implementacion de A3.
IDENTIFIABLE_COEFFICIENTS = (
    "a_r",
    "a_f",
    "a_c",
    "a_x",
    "a_w",
    "a_t",
    "b_res",
    "b_r",
    "b_conf",
    "b_x",
    "b_band",
    "b_int",
    "rho_pi",
    "c_e",
    "c_g",
    "c_f",
    "c_r",
    "d_g",
    "d_n",
    "d_w",
    "w_idx",
    "w_prod",
    "w_g",
    "w_u",
    "f_rev",
    "f_u",
    "debt_interest_rate",
    "k_tb",
    "k_w",
    "k_k",
    "k_conf",
)


#: Analogo a `IDENTIFIABLE_COEFFICIENTS` para el grupo `"macro"` (A5, ADR
#: 012 secc. 6, ultimo punto: "verificar identificabilidad rapida en
#: sintetico con la nueva estructura... extendido a los coeficientes
#: macro"): subconjunto de `calibration/parameters.py::MACRO_TUNABLE` que
#: aparece DIRECTAMENTE en las formulas de `world/economy.py::
#: step_macro_economy` que alimentan las 3 variables del objetivo que la
#: capa macro efectivamente gobierna (`inflation` secc. 2, `exchange_rate`
#: secc. 3, `reserves` secc. 4 -- `gdp_growth`/`unemployment` siguen
#: viniendo de `step_economy` sin cambios, ADR 012 no los toca). Mismo
#: criterio de exclusion que `IDENTIFIABLE_COEFFICIENTS`: perturbar un
#: coeficiente invisible para el objetivo (p.ej. los de secc. 5,
#: recuperacion de largo plazo, que no entran en ninguna de las 5
#: variables puntuadas) no probaria identificabilidad, probaria un objetivo
#: mal especificado.
IDENTIFIABLE_MACRO_COEFFICIENTS = (
    "w_adapt",
    "rho_pi",
    "rho_slope",
    "c_e",
    "c_g",
    "c_s",
    "md_0",
    "md_pi",
    "x_d",
    "k_int",
    "dd_pi",
    "dd_gap",
    "ex_c",
    "ex_e",
    "im_y",
    "im_e",
    "k_flight",
    "k_k_bop",
)


def perturb_macro_parameters(
    params: list[Parameter], n: int, fraction: float, seed: int
) -> tuple[MacroCoefficients, list[SyntheticPerturbation]]:
    """Analogo a `perturb_parameters` para el grupo `"macro"` (`params`
    debe venir de `build_parameter_space(include_macro=True)`, si no
    `macro_params` queda vacio y `rng.sample` tira si `n > 0`)."""
    rng = random.Random(seed)
    macro_params = [
        p for p in params if p.group == "macro" and p.name in IDENTIFIABLE_MACRO_COEFFICIENTS
    ]
    chosen = rng.sample(macro_params, k=min(n, len(macro_params)))
    updates: dict[str, float] = {}
    perturbations: list[SyntheticPerturbation] = []
    for p in chosen:
        sign = rng.choice([-1.0, 1.0])
        true_value = p.clip(p.aurora_value * (1.0 + sign * fraction))
        updates[p.name] = true_value
        perturbations.append(
            SyntheticPerturbation(
                param_name=p.name,
                aurora_value=p.aurora_value,
                true_value=true_value,
                fraction=sign * fraction,
            )
        )
    base = load_aurora_macro_coefficients()
    return replace(base, **updates), perturbations


def perturb_parameters(
    params: list[Parameter], n: int, fraction: float, seed: int
) -> tuple[Coefficients, list[SyntheticPerturbation]]:
    """Mueve `n` coeficientes (de `IDENTIFIABLE_COEFFICIENTS`, elegidos al
    azar con `seed`) un `fraction` (p.ej. 0.4 = +-40%) de su valor de
    Aurora, con signo al azar, recortado a los bounds del parametro."""
    rng = random.Random(seed)
    coeff_params = [p for p in params if p.name in IDENTIFIABLE_COEFFICIENTS]
    chosen = rng.sample(coeff_params, k=min(n, len(coeff_params)))
    updates: dict[str, float] = {}
    perturbations: list[SyntheticPerturbation] = []
    for p in chosen:
        sign = rng.choice([-1.0, 1.0])
        true_value = p.clip(p.aurora_value * (1.0 + sign * fraction))
        updates[p.name] = true_value
        perturbations.append(
            SyntheticPerturbation(
                param_name=p.name,
                aurora_value=p.aurora_value,
                true_value=true_value,
                fraction=sign * fraction,
            )
        )
    base = load_country().coefficients
    return base.model_copy(update=updates), perturbations


def _write_history_csvs(out_dir: Path, history, start: str) -> None:
    """Escribe `history/*.csv` sinteticos (`inflation_cpi_monthly`,
    `unemployment`, `reserves_monthly`, `exchange_rate_official_monthly`,
    `emae_monthly`, `gdp_per_capita_real`) a partir de una `History` ya
    corrida, mismo formato tidy (`date,value,unit,source_id`) que
    `data/countries/argentina/history/` -- factorizado de
    `generate_synthetic_history_csvs`/`generate_synthetic_history_csvs_macro`
    (A5, ADR 012 secc. 6): la unica diferencia entre las dos es COMO se
    corre `history` (con o sin `macro_coefficients`), no como se escribe."""
    out_dir.mkdir(parents=True, exist_ok=True)
    y0, m0 = (int(x) for x in start.split("-"))

    def date_for(month_index: int) -> str:
        total = (y0 * 12 + (m0 - 1)) + (month_index - 1)
        y, m = total // 12, total % 12 + 1
        return f"{y:04d}-{m:02d}-01"

    def write(name: str, unit: str, values: list[tuple[int, float]]) -> None:
        with (out_dir / f"{name}.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "value", "unit", "source_id"])
            for month_index, value in values:
                w.writerow([date_for(month_index), value, unit, "synthetic"])

    write(
        "inflation_cpi_monthly",
        "% mensual (sintetico)",
        [(r.month_index, r.state["inflation"]) for r in history.records],
    )
    write(
        "unemployment",
        "% (sintetico)",
        [(r.month_index, r.state["unemployment"]) for r in history.records],
    )
    write(
        "reserves_monthly",
        "USD M (sintetico)",
        [(r.month_index, r.state["reserves"]) for r in history.records],
    )
    write(
        "exchange_rate_official_monthly",
        "indice (sintetico)",
        [(r.month_index, r.state["exchange_rate"] / 100.0) for r in history.records],
    )
    write(
        "emae_monthly",
        "indice (sintetico)",
        [(r.month_index, r.state["gdp"]) for r in history.records],
    )
    # gdp_per_capita_real: anual, un valor por año (ultimo mes del año).
    by_year: dict[int, float] = {}
    for r in history.records:
        total = (y0 * 12 + (m0 - 1)) + (r.month_index - 1)
        y = total // 12
        by_year[y] = r.state["gdp"]
    with (out_dir / "gdp_per_capita_real.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "value", "unit", "source_id"])
        for y, v in sorted(by_year.items()):
            w.writerow([f"{y:04d}-01-01", v, "indice (sintetico)", "synthetic"])


def generate_synthetic_history_csvs(
    out_dir: Path, coeff: Coefficients, start: str = "1993-01", months: int = 240, seed: int = 7
) -> None:
    """Corre Aurora (SIN paquete de pais, `load_country()`, reglas, sin
    actores para que sea rapido) con `coeff` durante `months` meses y
    escribe `history/*.csv` sinteticos (ver `_write_history_csvs`) -- lo que
    necesita `calibration/objective.py::RealData.load()` para tratarlos
    como si fueran reales (con `HISTORY_DIR` apuntando a `out_dir` en vez
    del paquete real, ver `calibration/optimizer.py`/tests de
    identificabilidad, que monkeypatchean `initial_states.HISTORY_DIR`/
    `objective`'s loaders)."""
    country = load_country().model_copy(update={"coefficients": coeff, "months": months})
    history = run(seed=seed, months=months, country=country, default_brain="rules")
    _write_history_csvs(out_dir, history, start)


def generate_synthetic_history_csvs_macro(
    out_dir: Path,
    macro_coeff: MacroCoefficients,
    start: str = "1992-01",
    months: int = 240,
    seed: int = 7,
    coeff: Coefficients | None = None,
) -> None:
    """Analogo a `generate_synthetic_history_csvs` para el grupo `"macro"`
    (A5, ADR 012 secc. 6, identificabilidad rapida sobre sintetico con la
    nueva estructura): corre el paquete de Argentina (`load_country_pack`,
    para tener `macro_x0`/`macro_m0`/`fx_regime_auto` reales de `start` --
    la capa macro sin esos tres numeros no tiene con que anclar el balance
    de pagos) con `macro_coeff` durante `months` meses, `coeff` (economico)
    fijo en el valor de Aurora/Argentina si no se pasa otro."""
    from republica.world.countries import load_country_pack

    pack = load_country_pack("argentina", start, months)
    country = pack.country.model_copy(
        update={"months": months, **({"coefficients": coeff} if coeff is not None else {})}
    )
    history = run(
        seed=seed,
        months=months,
        country=country,
        default_brain="rules",
        macro_coefficients=macro_coeff,
        macro_x0=pack.macro_x0,
        macro_m0=pack.macro_m0,
        fx_regime=pack.fx_regime_auto,
    )
    _write_history_csvs(out_dir, history, start)
