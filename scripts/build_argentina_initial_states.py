#!/usr/bin/env python3
"""Genera `data/countries/argentina/country.json -> initial_states` (ADR 011 secc. 2).

Lee las series tidy de `data/countries/argentina/history/*.csv` (y, solo para
el proxy de `government_approval`, los resultados electorales ya publicados
en `data/countries/argentina/politics/sources/electorAr_presi/*.csv` -- un
archivo de solo lectura de otro agente, este script NUNCA escribe ahi) y
construye, para cada fecha de arranque soportada, las 21 variables de
`WorldState` (las 20 publicas + `inflation_lag1`) con su procedencia:

- `source`: viene de una serie de `history/`, con la transformacion aplicada
  en el propio string (para que quede autocontenido en el JSON).
- `proxy`: no hay serie pero hay una regla razonable (ADR 011 secc. 2, ej.
  `government_approval` a partir del resultado de la ultima eleccion).
- `assumed: true`: ni serie ni proxy razonable -- arranca en el valor de
  Aurora (`data/country.json -> initial_state`) sin pretender que sea un dato
  real de esa fecha.

Regla de oro del proyecto (PLAN_ARGENTINA.md #0.1): ningun numero se inventa.
Cada valor con `source`/`proxy` sale de una formula reproducible sobre un
archivo real; lo que no se puede fundamentar así quiere `assumed: true`.

Uso:
    uv run python scripts/build_argentina_initial_states.py [--out PATH] [--check]

`--check` no escribe nada: solo corre y muestra un resumen de cobertura por
variable (cuantas de las 8 fechas tienen `source`, cuantas `proxy`, cuantas
`assumed`) -- pensado para CI/tests.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = REPO_ROOT / "data" / "countries" / "argentina" / "history"
ELECTIONS_DIR = (
    REPO_ROOT / "data" / "countries" / "argentina" / "politics" / "sources" / "electorAr_presi"
)
COUNTRY_PACK_DIR = REPO_ROOT / "data" / "countries" / "argentina"
AURORA_COUNTRY_JSON = REPO_ROOT / "data" / "country.json"

#: Las 8 fechas de arranque soportadas (ADR 011 secc. 2 del enunciado de la
#: tarea): hitos historicos con un régimen y una economía bien identificados.
TARGET_DATES = [
    "1983-12",
    "1988-06",
    "1991-04",
    "1998-01",
    "2003-06",
    "2016-01",
    "2019-12",
    "2023-12",
]

#: Para el proxy de `government_approval` (ADR 011 secc. 2): la ultima
#: eleccion presidencial ANTES (o en el mismo mes de asuncion) de cada fecha
#: de arranque, con el archivo de resultados y el patron para reconocer al
#: ganador/oficialismo en la columna `lista`.
LAST_ELECTION_BEFORE: dict[str, tuple[str, str]] = {
    "1983-12": ("arg_presi_gral1983.csv", "Alfonsin"),
    "1988-06": ("arg_presi_gral1983.csv", "Alfonsin"),
    "1991-04": ("arg_presi_gral1989.csv", "Menem"),
    "1998-01": ("arg_presi_gral1995.csv", "Menem"),
    "2003-06": ("arg_presi_gral2003.csv", "Kirchner"),
    "2016-01": ("arg_presi_balota2015.csv", "Macri"),
    "2019-12": ("arg_presi_gral2019.csv", "Fernández"),
    # 2023: no hay arg_presi_gral2023.csv / balota2023.csv descargado en
    # `politics/sources/` a la fecha de este script -- assumed (ver abajo).
}


def _ym(date: str) -> tuple[int, int]:
    y, m = date.split("-")
    return int(y), int(m)


def _months_between(y1: int, m1: int, y2: int, m2: int) -> int:
    return (y2 - y1) * 12 + (m2 - m1)


def load_series(name: str) -> list[tuple[int, int, float, str, str]]:
    """`(year, month, value, source_id, unit)` ordenados, o `[]` si no existe
    el archivo (otro agente puede estar agregando/renombrando series en
    paralelo -- ver docstring del modulo)."""
    path = HISTORY_DIR / f"{name}.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                y, m = _ym(row["date"][:7])
                v = float(row["value"])
            except (ValueError, KeyError):
                continue
            rows.append((y, m, v, row.get("source_id", ""), row.get("unit", "")))
    rows.sort()
    return rows


def nearest(
    rows: list[tuple[int, int, float, str, str]], y: int, m: int, max_months: int
) -> tuple[int, float, str, str] | None:
    """El punto de `rows` mas cercano a `(y, m)` dentro de `max_months`, o
    `None`. Devuelve `(distancia_en_meses, valor, source_id, unit)`."""
    best = None
    for ry, rm, v, sid, unit in rows:
        dist = _months_between(y, m, ry, rm)
        if best is None or abs(dist) < abs(best[0]):
            best = (dist, v, sid, unit, ry, rm)
    if best is None or abs(best[0]) > max_months:
        return None
    dist, v, sid, unit, ry, rm = best
    return dist, v, sid, unit


def exact_month(rows: list[tuple[int, int, float, str, str]], y: int, m: int):
    for ry, rm, v, sid, unit in rows:
        if ry == y and rm == m:
            return v, sid, unit
    return None


def load_aurora_defaults() -> dict[str, float]:
    raw = json.loads(AURORA_COUNTRY_JSON.read_text(encoding="utf-8"))
    return dict(raw["initial_state"])


# ---------------------------------------------------------------------------
# Reglas por variable (documentadas en linea: cada funcion es la fuente de
# verdad de COMO se calcula esa variable para TODAS las fechas -- no hay
# valores por fecha tipeados a mano en ningun lado de este script).
# ---------------------------------------------------------------------------


def rule_inflation(y: int, m: int, monthly, annual, default: float) -> dict[str, Any]:
    exact = exact_month(monthly, y, m)
    if exact is not None:
        v, sid, unit = exact
        return {
            "value": v,
            "source": f"inflation_cpi_monthly.csv ({sid}), mes exacto {y}-{m:02d}: "
            "valor mensual tal cual (misma escala que WorldState.inflation, "
            "2.0 = 2%/mes).",
        }
    hit = nearest(annual, y, m, max_months=6)
    if hit is not None:
        dist, v, sid, unit = hit
        monthly_pct = ((1.0 + v / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
        return {
            "value": monthly_pct,
            "source": f"inflation_cpi_annual.csv ({sid}), a {dist:+d} meses de la fecha "
            f"objetivo: (1 + ipc_anual/100)^(1/12) - 1, expresado en puntos "
            "porcentuales (ADR 011 secc. 2, escala de WorldState.inflation).",
        }
    return {"value": default, "assumed": True}


def rule_inflation_lag1(
    y: int, m: int, monthly, annual, current_inflation: float
) -> dict[str, Any]:
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    exact = exact_month(monthly, py, pm)
    if exact is not None:
        v, sid, unit = exact
        return {
            "value": v,
            "source": f"inflation_cpi_monthly.csv ({sid}), mes exacto {py}-{pm:02d} "
            "(mes anterior a la fecha de arranque).",
        }
    hit = nearest(annual, py, pm, max_months=6)
    if hit is not None:
        dist, v, sid, unit = hit
        monthly_pct = ((1.0 + v / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
        return {
            "value": monthly_pct,
            "source": f"inflation_cpi_annual.csv ({sid}), mes anterior {py}-{pm:02d} "
            f"(a {dist:+d} meses): misma transformacion que `inflation`.",
        }
    return {
        "value": current_inflation,
        "proxy": "igual a `inflation` del mes de arranque (no hay dato mensual ni anual "
        "utilizable del mes anterior): aproximacion declarada, no un dato real distinto.",
    }


def rule_nearest_direct(
    y: int, m: int, rows, default: float, series_name: str, max_months: int, unit_note: str = ""
) -> dict[str, Any]:
    hit = nearest(rows, y, m, max_months=max_months)
    if hit is None:
        return {"value": default, "assumed": True}
    dist, v, sid, unit = hit
    note = f" ({unit_note})" if unit_note else ""
    return {
        "value": v,
        "source": f"{series_name}.csv ({sid}), a {dist:+d} meses de la fecha objetivo, "
        f"valor tal cual{note}.",
    }


def rule_gdp_growth(y: int, m: int, gdp_usd, gdp_pc, default: float) -> dict[str, Any]:
    """`gdp_growth` (ADR: variacion anualizada, magnitud REAL -- no nominal).
    Prioriza `gdp_per_capita_real` (Maddison, PPP constantes: crecimiento
    real per capita, aproximacion razonable al crecimiento real agregado ya
    que el crecimiento poblacional argentino es lento, <1.5%/año, sesgo
    documentado). Recien si Maddison no cubre la fecha usa `gdp_usd`
    (USD corrientes) como *ultimo recurso*: al ser nominal en dolares,
    mezcla crecimiento real + inflacion en dolares + variacion del tipo de
    cambio, asi que sobreestima/subestima el crecimiento real en periodos de
    fuerte devaluacion o inflacion en USD (ver Notas de implementacion).

    Usa el año CALENDARIO del arranque (`y`) contra `y - 1`, con match EXACTO
    de año (no "el punto mas cercano en meses"): con series anuales fechadas
    al 1-ene, una fecha de arranque tardía en el año (ej. diciembre) queda mas
    cerca en meses del 1-ene del año SIGUIENTE que del propio, así que un
    `nearest` por distancia en meses agarraría el crecimiento del año que
    todavía no paso -- se busca en cambio el crecimiento y/(y-1) tal cual,
    con hasta 1 año de tolerancia hacia atrás si falta el dato exacto."""
    for rows, name in ((gdp_pc, "gdp_per_capita_real"), (gdp_usd, "gdp_usd")):
        by_year = {ry: v for ry, rm, v, sid, unit in rows}
        sid_by_year = {ry: sid for ry, rm, v, sid, unit in rows}
        for end_year in (y, y - 1):
            if end_year in by_year and (end_year - 1) in by_year:
                v_now, v_prev = by_year[end_year], by_year[end_year - 1]
                if v_prev == 0:
                    continue
                growth_pct = (v_now / v_prev - 1.0) * 100.0
                lag = y - end_year
                lag_note = "" if lag == 0 else f" (año mas reciente cubierto, {lag} año(s) antes)"
                return {
                    "value": growth_pct,
                    "source": f"{name}.csv ({sid_by_year[end_year]}), variacion interanual "
                    f"{end_year - 1}->{end_year}{lag_note}: "
                    "(valor_año / valor_año_anterior - 1) * 100.",
                }
    return {"value": default, "assumed": True}


def rule_public_debt_pct_gdp(y: int, m: int, debt_musd, gdp_usd, default: float) -> dict[str, Any]:
    hit_debt = nearest(debt_musd, y, m, max_months=12)
    if hit_debt is None:
        return {"value": default, "assumed": True}
    dist_d, debt_v, debt_sid, _ = hit_debt
    debt_year = None
    for ry, _rm, vv, sid2, _unit2 in debt_musd:
        if vv == debt_v and sid2 == debt_sid:
            debt_year = ry
            break
    hit_gdp = nearest(gdp_usd, debt_year or y, 6, max_months=18) if debt_year else None
    if hit_gdp is None:
        return {"value": default, "assumed": True}
    _, gdp_v, gdp_sid, _ = hit_gdp
    if gdp_v == 0:
        return {"value": default, "assumed": True}
    pct = (debt_v * 1_000_000.0) / gdp_v * 100.0
    return {
        "value": pct,
        "source": f"public_debt.csv ({debt_sid}, a {dist_d:+d} meses) / gdp_usd.csv "
        f"({gdp_sid}): deuda_usd_millones * 1e6 / pib_usd_corriente * 100.",
    }


def rule_government_approval(date: str, default: float) -> dict[str, Any]:
    entry = LAST_ELECTION_BEFORE.get(date)
    if entry is None:
        return {
            "value": default,
            "assumed": True,
        }
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
                # no son candidaturas: no entran al numerador ni cambian que
                # se identifique al ganador, pero SI al total de votos
                # validos+blanco+nulo emitidos (denominador de la participacion).
                total += votos
                continue
            total += votos
            if pattern.lower() in label.lower():
                winner += votos
                winner_label = label
    if total <= 0 or winner_label is None:
        return {"value": default, "assumed": True}
    share = winner / total
    # ADR 011 secc. 2: 50 + 20*(voto oficialismo - 0.45)/0.15, acotado a [0,100]
    value = 50.0 + 20.0 * (share - 0.45) / 0.15
    value = max(0.0, min(100.0, value))
    return {
        "value": value,
        "proxy": f"50 + 20*(voto_oficialismo - 0.45)/0.15, acotado a [0,100] (ADR 011 secc. 2). "
        f"voto_oficialismo = {share:.4f} ({winner_label!r} / total de votos validos+blanco+nulo, "
        f"{filename}).",
    }


def rule_index_baseline(default: float, why: str) -> dict[str, Any]:
    return {"value": default, "assumed": True, "note": why}


def rule_vdem_scaled(
    y: int, m: int, vdem_rows, field_index: int, default: float, series_label: str, formula: str
) -> dict[str, Any]:
    hit = nearest(vdem_rows, y, m, max_months=18)
    if hit is None:
        return {"value": default, "assumed": True}
    dist, v, sid, unit = hit
    if v is None:
        return {"value": default, "assumed": True}
    scaled = max(0.0, min(100.0, v * 100.0))
    return {
        "value": scaled,
        "source": f"vdem_argentina.csv ({series_label}, a {dist:+d} meses): {formula}",
    }


def load_vdem_field(field: str) -> list[tuple[int, int, float, str, str]]:
    path = HISTORY_DIR / "vdem_argentina.csv"
    if not path.exists():
        return []
    rows = []
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
            rows.append((y, m, v, row.get("source_id", "vdem"), field))
    rows.sort()
    return rows


def build_entry(date: str, aurora: dict[str, float]) -> dict[str, Any]:
    y, m = _ym(date)

    inflation_monthly = load_series("inflation_cpi_monthly")
    inflation_annual = load_series("inflation_cpi_annual")
    unemployment = load_series("unemployment")
    interest = load_series("policy_rate_monthly")
    reserves = load_series("reserves_monthly")
    debt = load_series("public_debt")
    gdp_usd = load_series("gdp_usd")
    gdp_pc = load_series("gdp_per_capita_real")
    fiscal = load_series("fiscal_balance")
    poverty = load_series("poverty")
    v2x_libdem = load_vdem_field("v2x_libdem")
    v2x_civlib = load_vdem_field("v2x_civlib")

    inflation_entry = rule_inflation(y, m, inflation_monthly, inflation_annual, aurora["inflation"])
    entry: dict[str, Any] = {
        # -- indices sin anclaje real posible: ver notas del modulo/ADR notas de
        # implementacion. Se documentan con `note` ademas de `assumed`.
        "gdp": rule_index_baseline(
            aurora["gdp"],
            "indice de nivel sin unidad real en Aurora (base=100); no hay forma de "
            "mapear un nivel de PBI real a esa escala sin fijar una normalizacion "
            "arbitraria por fecha (rompe comparabilidad entre fechas). Se usa 100 "
            "(neutral) en todas las fechas; `gdp_growth` sí lleva la serie real.",
        ),
        "real_wage": rule_index_baseline(
            aurora["real_wage"],
            "indice de nivel (base=100 en Aurora); `real_wage.csv` (RIPTE real) no "
            "esta en esa base. Se usa 100 (neutral) en todas las fechas.",
        ),
        "exchange_rate": rule_index_baseline(
            aurora["exchange_rate"],
            "indice de nivel (base=100 en Aurora), no un tipo de cambio literal en "
            "ARS/USD: entre 1810 y 2023 Argentina tuvo 5 monedas distintas "
            "(peso moneda nacional, ley 18.188, argentino, austral, convertible), asi "
            "que un nivel nominal de una fecha no es comparable con el de otra sin "
            "una normalizacion arbitraria. Se usa 100 (neutral) en todas las fechas.",
        ),
        "gdp_growth": rule_gdp_growth(y, m, gdp_usd, gdp_pc, aurora["gdp_growth"]),
        "inflation": inflation_entry,
        "inflation_lag1": rule_inflation_lag1(
            y, m, inflation_monthly, inflation_annual, inflation_entry["value"]
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
        "institutional_confidence": rule_vdem_scaled(
            y,
            m,
            v2x_libdem,
            0,
            aurora["institutional_confidence"],
            "v2x_libdem",
            "v2x_libdem (indice de democracia liberal, 0-1) * 100, acotado a [0,100]. "
            "Proxy: mas garantias liberales/institucionales ~ mas confianza "
            "institucional esperada -- correlato, no una medicion directa.",
        ),
        "political_stability": rule_vdem_scaled(
            y,
            m,
            v2x_civlib,
            0,
            aurora["political_stability"],
            "v2x_civlib",
            "v2x_civlib (indice de libertades civiles, 0-1) * 100, acotado a [0,100]. "
            "Proxy: mas libertades civiles protegidas ~ mayor estabilidad "
            "institucional de base -- correlato, no una medicion directa.",
        ),
        # -- sin serie ni proxy razonable dentro del alcance de A2 (ADR 011 secc. 2):
        "congress_support": rule_index_baseline(
            aurora["congress_support"],
            "no hay serie de composicion legislativa mensual en `history/`; requeriria "
            "cruzar `politics/` con bancas por bloque, fuera de alcance de A2.",
        ),
        "social_tension": rule_index_baseline(
            aurora["social_tension"],
            "no hay serie de conflictividad social continua descargada (protestas, "
            "huelgas) para todo el periodo 1983-2023.",
        ),
        "consumer_confidence": rule_index_baseline(
            aurora["consumer_confidence"],
            "no hay serie libre de confianza del consumidor pre-2001.",
        ),
        "protest_level": rule_index_baseline(
            aurora["protest_level"], "no hay serie de nivel de protesta descargada."
        ),
        "inequality": rule_index_baseline(
            aurora["inequality"], "no hay serie de Gini/desigualdad descargada en `history/`."
        ),
        "crime_perception": rule_index_baseline(
            aurora["crime_perception"], "no hay serie de percepcion de inseguridad descargada."
        ),
    }
    return entry


def build_all() -> dict[str, Any]:
    aurora = load_aurora_defaults()
    return {date: build_entry(date, aurora) for date in TARGET_DATES}


def coverage_summary(initial_states: dict[str, Any]) -> str:
    lines = ["Cobertura de initial_states por variable (source / proxy / assumed):"]
    all_vars = sorted(next(iter(initial_states.values())).keys())
    for var in all_vars:
        counts = {"source": 0, "proxy": 0, "assumed": 0}
        for entry in initial_states.values():
            v = entry[var]
            if v.get("assumed"):
                counts["assumed"] += 1
            elif "source" in v:
                counts["source"] += 1
            elif "proxy" in v:
                counts["proxy"] += 1
        lines.append(
            f"  {var:26s} source={counts['source']:>2} proxy={counts['proxy']:>2} "
            f"assumed={counts['assumed']:>2}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=COUNTRY_PACK_DIR / "_initial_states_generated.json",
        help="Donde escribir el bloque initial_states generado (JSON).",
    )
    parser.add_argument(
        "--check", action="store_true", help="No escribe nada; solo imprime cobertura."
    )
    args = parser.parse_args()

    initial_states = build_all()
    print(coverage_summary(initial_states))

    for date in TARGET_DATES:
        for var, entry in initial_states[date].items():
            has_prov = entry.get("assumed") or "source" in entry or "proxy" in entry
            if not has_prov:
                raise SystemExit(f"{date}/{var}: sin source/proxy/assumed -- no debe pasar")

    if not args.check:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(initial_states, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nEscrito: {args.out}")


if __name__ == "__main__":
    main()
