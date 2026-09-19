"""Estado inicial para CUALQUIER mes (A3, generalizacion de
`scripts/build_argentina_initial_states.py`).

`scripts/build_argentina_initial_states.py` (A2) solo cubre las 8 fechas de
`data/countries/argentina/country.json -> initial_states`
(`world/countries.py::load_country_pack` las usa tal cual, sin llamar a este
modulo -- esos 8 valores NO se regeneran aca, quedan como estaban: ver Notas
de implementacion de A3 para el motivo). `initial_state_for(date)` de este
modulo es la MISMA idea (las 20 variables de `WorldState`, cada una con
`source`/`proxy`/`assumed`) pero para un mes cualquiera dentro de la
cobertura de `history/` -- lo necesita `calibration/objective.py` para poder
arrancar una simulacion desde cada mes de la ventana de entrenamiento/
holdout, no solo desde los 8 hitos.

Reglas de interpolacion (documentadas aca, ADR 011 secc. 7 / tarea A3 punto 1):

- **`inflation`/`inflation_lag1`** (ADR 019 secc. 3C): PRIMERO
  `inflation_cpi_monthly_linked.csv` (BCRA 'Principales Variables' id 27,
  serie historica empalmada de INDEC, **1943-03+**), mes exacto; despues
  `inflation_cpi_monthly.csv` (1997-02+); recien despues la anual
  interpolada. Hasta ADR 019 la primera serie estaba en `history/` y no la
  leia nadie, asi que TODO arranque anterior a 1997-02 -- la ventana entera
  de la hiperinflacion, 1983-1991 -- recibia una tasa anual convertida con
  `(1+a)^(1/12)-1`. El error medido para 1988-06 era de 4.01 pp.
- **Series mensuales** (`policy_rate_monthly`,
  `reserves_monthly`, `emae_monthly`, `unemployment`, `fiscal_balance`,
  `poverty`, `public_debt`, `gdp_usd`): mes exacto si existe; si no, el punto
  mas cercano dentro de una tolerancia (`max_months`, por variable) --
  SIN interpolar (un valor "tal cual", no un promedio): son observaciones
  discretas de una encuesta/balance, interpolar linealmente entre dos
  balances mensuales de bancos distintos no es mas fiel que tomar el mas
  cercano.
- **Series anuales** (`inflation_cpi_annual(_linked)`, `vdem_argentina`,
  `gdp_per_capita_real`): SI se interpolan linealmente. Cada punto anual
  esta fechado `YYYY-01-01` en `history/` (convencion de A0); se trata como
  el valor vigente el 1-ene de ese año, y el valor de un mes `m` de un año
  `y` es `v[y] + frac*(v[y+1]-v[y])` con `frac=(m-1)/12` (m=1 -> exacto
  `v[y]`, m=12 -> a 11/12 del camino hacia `v[y+1]`). En los bordes de la
  serie (no hay `y+1` o no hay `y`) se usa el valor mas cercano SIN
  extrapolar (plano), documentado en cada `source` (`"(borde de la serie,
  sin extrapolar)"`).
- **`gdp_growth`**: variacion interanual (t vs t-12), NO un nivel
  interpolado -- prioridad `emae_monthly` (mes exacto contra el mismo mes
  del año anterior, ambos exactos) sobre `gdp_per_capita_real`
  (interanual, año calendario) sobre `gdp_usd` (idem, ultimo recurso: ver
  motivo en `rule_gdp_growth` de `scripts/build_argentina_initial_states.py`,
  mismo criterio aca).
- **`government_approval`**: proxy de la ultima eleccion presidencial ANTES
  de la fecha pedida (`ELECTION_WINNERS`, generalizado del `dict` de 8
  entradas fijas del script de A2 a una lista de (fecha de asuncion,
  archivo, patron de ganador) valida para cualquier mes entre 1989 y 2023;
  fuera de ese rango, `assumed`).
- **`gdp`/`real_wage`/`exchange_rate`/`congress_support`/`social_tension`/
  `consumer_confidence`/`protest_level`/`inequality`/`crime_perception`**:
  siempre `assumed` (igual que en A2, ver el script: son indices sin
  anclaje real posible o sin serie descargada -- no cambia con el mes).
  `exchange_rate` sigue `assumed = 100` aunque desde 2026-09-19 exista
  `exchange_rate_annual_linked.csv` (1962+, ARS por USD): `world/economy.py`
  solo lo mueve multiplicativamente (`exchange_rate * (1 + de/100)`) y el
  objetivo compara CAMBIOS logaritmicos contra el propio nivel inicial del
  modelo (`calibration/objective.py`, `fx0_model`), asi que el nivel inicial
  no cambia ninguna trayectoria; cargar `6e-5` (australes de 1985 en ARS)
  como "indice" solo desconectaria la escala base 100 de Aurora sin ganar
  fidelidad. La regla `rule_exchange_rate_index` deja igual constancia del
  nivel real de referencia en el `note` (procedencia), para que el estado
  inicial diga de donde saldria el ancla si algun dia el motor la usara.
"""

from __future__ import annotations

import csv
from typing import Any

from republica.world.config import DEFAULT_DATA_DIR

PACK_DIR = DEFAULT_DATA_DIR / "countries" / "argentina"
HISTORY_DIR = PACK_DIR / "history"
ELECTIONS_DIR = PACK_DIR / "politics" / "sources" / "electorAr_presi"
AURORA_COUNTRY_JSON = DEFAULT_DATA_DIR / "country.json"

Row = tuple[int, int, float, str]

#: Cobertura declarada de `initial_state_for`: fuera de este rango, la
#: ausencia total de series (`history/` no cubre antes de 1961 a nivel
#: mensual, V-Dem si cubre 1789+ pero el resto no) hace que casi todo
#: termine `assumed` -- se prefiere que el llamador lo sepa de antemano
#: (`calibration/objective.py` valida el rango del `--train`/`--holdout`
#: contra esto) en vez de devolver un estado casi todo `assumed` en
#: silencio.
MIN_YEAR = 1961
MAX_YEAR = 2023


class UnsupportedDateError(ValueError):
    pass


def _ym(date: str) -> tuple[int, int]:
    y, m = date.split("-")
    return int(y), int(m)


def _months_between(y1: int, m1: int, y2: int, m2: int) -> int:
    return (y2 - y1) * 12 + (m2 - m1)


def load_series(name: str) -> list[Row]:
    path = HISTORY_DIR / f"{name}.csv"
    if not path.exists():
        return []
    rows: list[Row] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                y, m = _ym(row["date"][:7])
                v = float(row["value"])
            except (ValueError, KeyError):
                continue
            rows.append((y, m, v, row.get("source_id", "")))
    rows.sort()
    return rows


def load_vdem_field(field: str) -> list[Row]:
    path = HISTORY_DIR / "vdem_argentina.csv"
    if not path.exists():
        return []
    rows: list[Row] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            raw = row.get(field, "")
            if not raw:
                continue
            try:
                y, m = _ym(row["date"][:7])
                v = float(raw)
            except (ValueError, KeyError):
                continue
            rows.append((y, m, v, "vdem"))
    rows.sort()
    return rows


def _exact(rows: list[Row], y: int, m: int) -> tuple[float, str] | None:
    for ry, rm, v, sid in rows:
        if ry == y and rm == m:
            return v, sid
    return None


def _nearest(rows: list[Row], y: int, m: int, max_months: int) -> tuple[int, float, str] | None:
    best = None
    for ry, rm, v, sid in rows:
        dist = _months_between(y, m, ry, rm)
        if best is None or abs(dist) < abs(best[0]):
            best = (dist, v, sid)
    if best is None or abs(best[0]) > max_months:
        return None
    return best


def _annual_by_year(rows: list[Row]) -> dict[int, tuple[float, str]]:
    return {ry: (v, sid) for ry, _rm, v, sid in rows}


def interpolate_annual(rows: list[Row], y: int, m: int) -> tuple[float, str] | None:
    """Interpolacion lineal de una serie ANUAL (ver docstring del modulo):
    `v[y] + frac*(v[y+1]-v[y])`, `frac=(m-1)/12`. En los bordes (falta `y+1`
    o falta `y`) devuelve el extremo disponible mas cercano, SIN
    extrapolar, con una nota distinta en el `source`."""
    by_year = _annual_by_year(rows)
    if not by_year:
        return None
    if y in by_year and (y + 1) in by_year:
        v0, sid0 = by_year[y]
        v1, _sid1 = by_year[y + 1]
        frac = (m - 1) / 12.0
        value = v0 + frac * (v1 - v0)
        return value, f"{sid0} (interpolado linealmente entre {y} y {y + 1}, frac={frac:.3f})"
    # borde: el año mas cercano disponible, plano (sin extrapolar).
    nearest_year = min(by_year, key=lambda yy: abs(yy - y))
    if abs(nearest_year - y) > 3:
        return None
    v, sid = by_year[nearest_year]
    return v, f"{sid} (borde de la serie: {nearest_year} usado sin interpolar/extrapolar)"


def load_aurora_defaults() -> dict[str, float]:
    import json

    raw = json.loads(AURORA_COUNTRY_JSON.read_text(encoding="utf-8"))
    return dict(raw["initial_state"])


# ---------------------------------------------------------------------------
# Elecciones presidenciales: generalizacion de `LAST_ELECTION_BEFORE` (A2,
# solo 8 entradas fijas) a una lista valida para cualquier fecha entre la
# primera y la ultima eleccion cubierta. Ganador curado a mano (fuente:
# resultado publico + quien asumio la presidencia -- 2003 es el caso que
# obliga a esto: Menem saco mas votos en primera vuelta pero se bajo del
# balotaje, asumio Kirchner; "mas votos" NO alcanza como regla automatica).
# ---------------------------------------------------------------------------

#: `(fecha_de_asuncion, archivo, patron_del_ganador)`, ordenada. La fecha de
#: asuncion (no la de la eleccion) es la que separa "que gobierno esta en
#: pie" mes a mes.
ELECTION_WINNERS: list[tuple[str, str, str]] = [
    ("1946-06-04", "arg_presi_gral1946.csv", "Perón"),
    ("1958-05-01", "arg_presi_gral1958.csv", "Frondizi"),
    ("1963-10-12", "arg_presi_gral1963.csv", "Illia"),
    # 1966-1973 (dictadura "Revolucion Argentina") y 1973-1976 (gobiernos peronistas,
    # golpe de 1976) quedan SIN entrada: no hay archivo de resultados de la eleccion de
    # 1973 en politics/sources/electorAr_presi/ (regla de oro, PLAN_ARGENTINA.md #0.1: no
    # se inventa un ganador). Un mes en ese rango queda `government_approval: assumed`.
    ("1983-12-10", "arg_presi_gral1983.csv", "Alfonsin"),
    ("1989-07-08", "arg_presi_gral1989.csv", "Menem"),
    ("1995-12-10", "arg_presi_gral1995.csv", "Menem"),
    ("1999-12-10", "arg_presi_gral1999.csv", "De La Rua"),
    ("2003-05-25", "arg_presi_gral2003.csv", "Kirchner"),
    ("2007-12-10", "arg_presi_gral2007.csv", "Fernández"),
    ("2011-12-10", "arg_presi_gral2011.csv", "Fernández"),
    ("2015-12-10", "arg_presi_balota2015.csv", "Macri"),
    ("2019-12-10", "arg_presi_gral2019.csv", "Fernández"),
]


def _election_before(date: str) -> tuple[str, str] | None:
    y, m = _ym(date)
    target = (y, m)
    best: tuple[str, str] | None = None
    best_ym: tuple[int, int] | None = None
    for asuncion, filename, pattern in ELECTION_WINNERS:
        ay, am, _ = asuncion.split("-")
        ay_m = (int(ay), int(am))
        if ay_m <= target and (best_ym is None or ay_m > best_ym):
            best_ym = ay_m
            best = (filename, pattern)
    return best


def rule_government_approval(date: str, default: float) -> dict[str, Any]:
    entry = _election_before(date)
    if entry is None:
        return {"value": default, "assumed": True}
    filename, pattern = entry
    path = ELECTIONS_DIR / filename
    if not path.exists():
        return {"value": default, "assumed": True}
    total = 0.0
    winner = 0.0
    winner_label = None
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            label = row.get("lista", "")
            try:
                votos = float(row["votos"])
            except (KeyError, ValueError):
                continue
            if label.lower().startswith(("votos en blanco", "votos nulos", "partidos de distrito")):
                total += votos
                continue
            total += votos
            if pattern.lower() in label.lower():
                winner += votos
                winner_label = label
    if total <= 0 or winner_label is None:
        return {"value": default, "assumed": True}
    share = winner / total
    value = max(0.0, min(100.0, 50.0 + 20.0 * (share - 0.45) / 0.15))
    return {
        "value": value,
        "proxy": f"50 + 20*(voto_oficialismo - 0.45)/0.15, acotado a [0,100] (ADR 011 secc. 2). "
        f"voto_oficialismo = {share:.4f} ({winner_label!r} / total, {filename}).",
    }


def rule_gdp_growth(y: int, m: int, emae, gdp_pc, gdp_usd, default: float) -> dict[str, Any]:
    exact_now = _exact(emae, y, m)
    exact_prev = _exact(emae, y - 1, m)
    if exact_now is not None and exact_prev is not None and exact_prev[0] != 0:
        v_now, sid = exact_now
        v_prev, _ = exact_prev
        growth = (v_now / v_prev - 1.0) * 100.0
        return {
            "value": growth,
            "source": f"emae_monthly.csv ({sid}), variacion interanual exacta "
            f"{y - 1}-{m:02d} -> {y}-{m:02d}.",
        }
    for rows, name in ((gdp_pc, "gdp_per_capita_real"), (gdp_usd, "gdp_usd")):
        by_year = _annual_by_year(rows)
        for end_year in (y, y - 1):
            if end_year in by_year and (end_year - 1) in by_year:
                v_now, sid = by_year[end_year]
                v_prev, _ = by_year[end_year - 1]
                if v_prev == 0:
                    continue
                growth = (v_now / v_prev - 1.0) * 100.0
                lag = y - end_year
                lag_note = "" if lag == 0 else f" (año mas reciente cubierto, {lag} año(s) antes)"
                return {
                    "value": growth,
                    "source": f"{name}.csv ({sid}), variacion interanual "
                    f"{end_year - 1}->{end_year}{lag_note}.",
                }
    return {"value": default, "assumed": True}


def rule_inflation(
    y: int,
    m: int,
    monthly: list[Row],
    annual: list[Row],
    default: float,
    monthly_linked: list[Row] | None = None,
):
    """ADR 019 secc. 3C: `inflation_cpi_monthly_linked.csv` (BCRA
    'Principales Variables' id 27, serie historica empalmada de INDEC,
    **1943-03+**) tiene PRIORIDAD sobre `inflation_cpi_monthly.csv`
    (1997-02+) y sobre la anual interpolada. Antes de ADR 019 esta serie
    estaba en `history/` y no la usaba nadie, asi que todo arranque anterior
    a 1997-02 -- toda la ventana de hiperinflacion, 1983-1991 -- recibia una
    tasa ANUAL convertida con `(1+a)^(1/12)-1` en vez del dato mensual real.
    El error medido para 1988-06 era de **4.01 pp** (13.99 contra 18.0
    reales), contra un umbral de bifurcacion que 1983-12 cruzaba por 0.28 pp
    (ADR 019 secc. 1.2)."""
    for rows, name in (
        (monthly_linked or [], "inflation_cpi_monthly_linked"),
        (monthly, "inflation_cpi_monthly"),
    ):
        exact = _exact(rows, y, m)
        if exact is not None:
            v, sid = exact
            return {
                "value": v,
                "source": f"{name}.csv ({sid}), mes exacto {y}-{m:02d}.",
            }
    hit = interpolate_annual(annual, y, m)
    if hit is not None:
        v, note = hit
        monthly_pct = ((1.0 + v / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
        return {
            "value": monthly_pct,
            "source": f"inflation_cpi_annual_linked.csv ({note}): tasa anual interpolada, "
            "convertida a mensual con (1+anual/100)^(1/12)-1.",
        }
    return {"value": default, "assumed": True}


def rule_inflation_lag1(
    y: int, m: int, monthly, annual, current_inflation: float, monthly_linked=None
):
    """Mismo orden de prioridad que `rule_inflation` (ADR 019 secc. 3C),
    para el mes anterior."""
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    for rows, name in (
        (monthly_linked or [], "inflation_cpi_monthly_linked"),
        (monthly, "inflation_cpi_monthly"),
    ):
        exact = _exact(rows, py, pm)
        if exact is not None:
            v, sid = exact
            return {
                "value": v,
                "source": f"{name}.csv ({sid}), mes exacto {py}-{pm:02d}.",
            }
    hit = interpolate_annual(annual, py, pm)
    if hit is not None:
        v, note = hit
        monthly_pct = ((1.0 + v / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
        return {
            "value": monthly_pct,
            "source": f"inflation_cpi_annual_linked.csv ({note}), mes anterior.",
        }
    return {
        "value": current_inflation,
        "proxy": "igual a `inflation` del mes de arranque (sin dato mensual/anual del mes "
        "anterior).",
    }


def rule_nearest_direct(y: int, m: int, rows, default: float, series_name: str, max_months: int):
    hit = _nearest(rows, y, m, max_months)
    if hit is None:
        return {"value": default, "assumed": True}
    dist, v, sid = hit
    return {
        "value": v,
        "source": f"{series_name}.csv ({sid}), a {dist:+d} meses de la fecha objetivo, valor "
        "tal cual.",
    }


def rule_public_debt_pct_gdp(y: int, m: int, debt, gdp_usd, default: float):
    hit_debt = _nearest(debt, y, m, max_months=12)
    if hit_debt is None:
        return {"value": default, "assumed": True}
    dist_d, debt_v, debt_sid = hit_debt
    debt_year = next((ry for ry, _rm, vv, sid2 in debt if vv == debt_v and sid2 == debt_sid), None)
    hit_gdp = _nearest(gdp_usd, debt_year or y, 6, max_months=18) if debt_year else None
    if hit_gdp is None:
        return {"value": default, "assumed": True}
    _, gdp_v, gdp_sid = hit_gdp
    if gdp_v == 0:
        return {"value": default, "assumed": True}
    pct = (debt_v * 1_000_000.0) / gdp_v * 100.0
    return {
        "value": pct,
        "source": f"public_debt.csv ({debt_sid}, a {dist_d:+d} meses) / gdp_usd.csv ({gdp_sid}).",
    }


def rule_vdem_interpolated(y: int, m: int, vdem_rows, default: float, label: str, formula: str):
    hit = interpolate_annual(vdem_rows, y, m)
    if hit is None:
        return {"value": default, "assumed": True}
    v, note = hit
    scaled = max(0.0, min(100.0, v * 100.0))
    return {"value": scaled, "source": f"vdem_argentina.csv ({label}, {note}): {formula}"}


def rule_assumed(default: float, why: str) -> dict[str, Any]:
    return {"value": default, "assumed": True, "note": why}


def rule_exchange_rate_index(
    y: int, m: int, monthly: list[Row], annual: list[Row], default: float
) -> dict[str, Any]:
    """`exchange_rate` del estado inicial: SIEMPRE `assumed = 100` (indice
    de nivel de Aurora, ver docstring del modulo), pero con el nivel real
    de referencia (ARS por USD) y su procedencia en el `note`, tomado de la
    misma cadena que usa `calibration/objective.py::RealData.fx_level`:
    `exchange_rate_official_monthly.csv` (mes exacto, 1992-01+) y, si no,
    `exchange_rate_annual_linked.csv` (promedio anual, 1962+) interpolado
    geometricamente. Sin dato en ninguna de las dos, el `note` lo dice."""
    why = (
        "indice de nivel (base=100), no un tipo de cambio literal (multiples monedas "
        "1810-2023); el motor solo lo mueve multiplicativamente y el objetivo compara "
        "cambios log, asi que el nivel inicial no altera la trayectoria."
    )
    exact = _exact(monthly, y, m)
    if exact is not None:
        v, sid = exact
        ref = (
            f"nivel real de referencia {v:.6g} ARS/USD "
            f"(exchange_rate_official_monthly.csv, {sid}, mes exacto)."
        )
        return {"value": default, "assumed": True, "note": f"{why} {ref}"}
    import math

    log_rows = [(ry, rm, math.log(v), sid) for ry, rm, v, sid in annual if v > 0]
    hit = interpolate_annual(log_rows, y, m)
    if hit is not None:
        log_v, note = hit
        ref = (
            f"nivel real de referencia {math.exp(log_v):.6g} ARS/USD "
            f"(exchange_rate_annual_linked.csv, {note}, interpolacion geometrica "
            "del promedio anual)."
        )
        return {"value": default, "assumed": True, "note": f"{why} {ref}"}
    return {
        "value": default,
        "assumed": True,
        "note": f"{why} Sin nivel real de referencia para {y}-{m:02d} en history/.",
    }


def initial_state_for(date: str) -> dict[str, dict[str, Any]]:
    """Las 20 variables de `WorldState` (+ `inflation_lag1`) para `date`
    (`YYYY-MM`), con `source`/`proxy`/`assumed` por variable (mismo
    contrato que `country.json -> initial_states`, ver docstring del
    modulo). Valido para cualquier mes con `MIN_YEAR <= año <= MAX_YEAR`;
    fuera de rango, `UnsupportedDateError`."""
    y, m = _ym(date)
    if not (MIN_YEAR <= y <= MAX_YEAR):
        raise UnsupportedDateError(
            f"initial_state_for solo cubre {MIN_YEAR}-{MAX_YEAR}, se pidio {date!r}."
        )
    aurora = load_aurora_defaults()

    inflation_monthly = load_series("inflation_cpi_monthly")
    inflation_monthly_linked = load_series("inflation_cpi_monthly_linked")
    inflation_annual = load_series("inflation_cpi_annual_linked") or load_series(
        "inflation_cpi_annual"
    )
    unemployment = load_series("unemployment")
    interest = load_series("policy_rate_monthly")
    reserves = load_series("reserves_monthly")
    debt = load_series("public_debt")
    gdp_usd = load_series("gdp_usd")
    gdp_pc = load_series("gdp_per_capita_real")
    emae = load_series("emae_monthly")
    fiscal = load_series("fiscal_balance")
    poverty = load_series("poverty")
    fx_monthly = load_series("exchange_rate_official_monthly")
    fx_annual = load_series("exchange_rate_annual_linked")
    v2x_libdem = load_vdem_field("v2x_libdem")
    v2x_civlib = load_vdem_field("v2x_civlib")

    inflation_entry = rule_inflation(
        y,
        m,
        inflation_monthly,
        inflation_annual,
        aurora["inflation"],
        monthly_linked=inflation_monthly_linked,
    )
    entry: dict[str, dict[str, Any]] = {
        "gdp": rule_assumed(aurora["gdp"], "indice de nivel sin unidad real (base=100 en Aurora)."),
        "real_wage": rule_assumed(
            aurora["real_wage"],
            "indice de nivel (base=100 en Aurora), sin esa base en real_wage.csv.",
        ),
        "exchange_rate": rule_exchange_rate_index(
            y, m, fx_monthly, fx_annual, aurora["exchange_rate"]
        ),
        "gdp_growth": rule_gdp_growth(y, m, emae, gdp_pc, gdp_usd, aurora["gdp_growth"]),
        "inflation": inflation_entry,
        "inflation_lag1": rule_inflation_lag1(
            y,
            m,
            inflation_monthly,
            inflation_annual,
            inflation_entry["value"],
            monthly_linked=inflation_monthly_linked,
        ),
        "unemployment": rule_nearest_direct(
            y, m, unemployment, aurora["unemployment"], "unemployment", max_months=6
        ),
        "interest_rate": rule_nearest_direct(
            y, m, interest, aurora["interest_rate"], "policy_rate_monthly", max_months=6
        ),
        "reserves": rule_nearest_direct(
            y, m, reserves, aurora["reserves"], "reserves_monthly", max_months=6
        ),
        "public_debt": rule_public_debt_pct_gdp(y, m, debt, gdp_usd, aurora["public_debt"]),
        "fiscal_balance": rule_nearest_direct(
            y, m, fiscal, aurora["fiscal_balance"], "fiscal_balance", max_months=12
        ),
        "poverty": rule_nearest_direct(y, m, poverty, aurora["poverty"], "poverty", max_months=12),
        "government_approval": rule_government_approval(date, aurora["government_approval"]),
        "institutional_confidence": rule_vdem_interpolated(
            y,
            m,
            v2x_libdem,
            aurora["institutional_confidence"],
            "v2x_libdem",
            "v2x_libdem (0-1) * 100, proxy de confianza institucional.",
        ),
        "political_stability": rule_vdem_interpolated(
            y,
            m,
            v2x_civlib,
            aurora["political_stability"],
            "v2x_civlib",
            "v2x_civlib (0-1) * 100, proxy de estabilidad politica.",
        ),
        "congress_support": rule_assumed(
            aurora["congress_support"], "sin serie de composicion legislativa mensual."
        ),
        "social_tension": rule_assumed(
            aurora["social_tension"], "sin serie continua de conflictividad social."
        ),
        "consumer_confidence": rule_assumed(
            aurora["consumer_confidence"], "sin serie libre de confianza del consumidor."
        ),
        "protest_level": rule_assumed(
            aurora["protest_level"], "sin serie de nivel de protesta descargada."
        ),
        "inequality": rule_assumed(
            aurora["inequality"], "sin serie de Gini/desigualdad descargada."
        ),
        "crime_perception": rule_assumed(
            aurora["crime_perception"], "sin serie de percepcion de inseguridad descargada."
        ),
    }
    return entry


def flat_initial_state(date: str) -> dict[str, float]:
    """`{variable: value}` plano, listo para `WorldState(**flat)` (lo que
    necesita `calibration/objective.py` para arrancar una simulacion)."""
    return {var: prov["value"] for var, prov in initial_state_for(date).items()}
