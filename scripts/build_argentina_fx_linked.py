#!/usr/bin/env python3
"""Construye `data/countries/argentina/history/exchange_rate_annual_linked.csv`
(tipo de cambio oficial anual, pesos convertibles por USD, 1962 →) a partir
del indicador `PA.NUS.FCRF` del Banco Mundial ("Official exchange rate, LCU
per US$, period average"; origen declarado: IMF International Financial
Statistics, promedio anual de promedios mensuales) tal como lo replica el
mirror `ronnywang/worldbank` (`WDI_bundle/parsed/PA.NUS.FCRF_WDI.csv`,
snapshot de diciembre de 2013). `api.worldbank.org` responde 403 desde este
entorno; el mirror en GitHub es la única copia alcanzable (`SOURCES.md`
fuente 22).

No inventa ningún número: cada fila es, textualmente, la celda del CSV crudo
para `Country Code == "ARG"` (celdas vacías = sin fila). No se aplica ningún
factor de conversión: el WDI ya publica la serie **enlazada** a la unidad
vigente (pesos convertibles de 1992 = ARS actuales), es decir, con las cuatro
redenominaciones (1970, 1983, 1985, 1992) ya descontadas. Por eso 1962 vale
`8.7e-12` ARS/USD (≈ 87 pesos moneda nacional por dólar) y 1991 vale `0.95`
(≈ 9 536 australes por dólar). El script solo *verifica* esa lectura (ver
`--check`): continuidad con `exchange_rate_official_monthly.csv` en 1992-01,
promedio anual de la mensual vs el dato anual 1992-2013, y orden de magnitud
contra la inflación acumulada de `inflation_cpi_annual_linked.csv`. Los
números que imprime se pegan en `consistency.md` (sección 14); ninguno se usa
para ajustar la serie.

Uso (reproducible desde el crudo ya copiado a `history/raw/`):

    uv run python scripts/build_argentina_fx_linked.py

o desde el mirror recién bajado:

    curl -sSL -o /tmp/PA.NUS.FCRF_WDI.csv \\
      https://raw.githubusercontent.com/ronnywang/worldbank/master/WDI_bundle/parsed/PA.NUS.FCRF_WDI.csv
    uv run python scripts/build_argentina_fx_linked.py --wdi-csv /tmp/PA.NUS.FCRF_WDI.csv

Convención de fechas: dato anual (promedio del año) fechado `YYYY-01-01`,
igual que el resto de las series anuales de `history/` (convención de A0;
`calibration/initial_states.py::interpolate_annual` lo trata como el valor
vigente al 1 de enero, lo que para un promedio anual introduce un corrimiento
de ~6 meses -- documentado, no corregido, para usar la MISMA regla que la
inflación anual).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = REPO_ROOT / "data" / "countries" / "argentina" / "history"
RAW_DEFAULT = HISTORY_DIR / "raw" / "worldbank_mirror" / "PA.NUS.FCRF_WDI.csv"
OUT = HISTORY_DIR / "exchange_rate_annual_linked.csv"

SOURCE_ID = "wb_fcrf_mirror"
UNIT = (
    "ARS (pesos convertibles de 1992, unidad actual) por USD, tipo de cambio oficial, "
    "promedio anual de promedios mensuales, serie ya enlazada por el Banco Mundial a traves de "
    "las redenominaciones de 1970/1983/1985/1992 (WDI PA.NUS.FCRF, origen IMF IFS, "
    "via ronnywang/worldbank snapshot 2013-12)"
)

#: Factores LEGALES de cada redenominacion (hecho publico, no un dato de la
#: serie): 1 peso convertible (Decreto 2128/1991, vigente 1992-01-01) =
#: 10 000 australes; 1 austral (Decreto 1096/1985, 1985-06-15) = 1 000 pesos
#: argentinos; 1 peso argentino (Ley 22.707, 1983-06-01) = 10 000 pesos ley
#: 18.188; 1 peso ley 18.188 (1970-01-01) = 100 pesos moneda nacional. Solo
#: se usan para IMPRIMIR la serie en la moneda de cada epoca como chequeo de
#: plausibilidad (`--check`); el CSV de salida NO los aplica.
EPOCHS: list[tuple[int, int, str, float]] = [
    (1962, 1969, "pesos moneda nacional (m$n)", 1e13),
    (1970, 1982, "pesos ley 18.188", 1e11),
    (1983, 1984, "pesos argentinos", 1e7),
    (1985, 1991, "australes", 1e4),
    (1992, 9999, "pesos convertibles (ARS)", 1.0),
]

#: Ultimo año del tramo "enlazado hacia atras": desde 1992 la serie mensual
#: `exchange_rate_official_monthly.csv` (BCRA) es la referencia; el anual
#: 1992-2013 se conserva en el archivo SOLO para el cruce con la mensual y
#: para que `interpolate_annual` tenga `y+1` en 1991.
LAST_LINKED_YEAR = 1991


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_argentina_row(wdi_csv: Path) -> dict[int, str]:
    """`{año: celda textual}` de la fila ARG, solo celdas no vacías."""
    with open(wdi_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("Country Code") != "ARG":
                continue
            if r.get("Indicator Code") != "PA.NUS.FCRF":
                raise SystemExit(f"fila ARG con indicador inesperado {r.get('Indicator Code')!r}")
            out: dict[int, str] = {}
            for k, v in r.items():
                if k and k.isdigit() and v not in (None, ""):
                    out[int(k)] = v.strip()
            return out
    raise SystemExit(f"{wdi_csv}: no hay fila con Country Code == ARG")


def write_tidy(rows: dict[int, str]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "value", "unit", "source_id"])
        for y in sorted(rows):
            w.writerow([f"{y:04d}-01-01", rows[y], UNIT, SOURCE_ID])
    years = sorted(rows)
    print(f"escrito {OUT.relative_to(REPO_ROOT)} ({len(rows)} filas, {years[0]} -> {years[-1]})")


def tidy_monthly(name: str) -> dict[tuple[int, int], float]:
    path = HISTORY_DIR / f"{name}.csv"
    if not path.is_file():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {
            (int(r["date"][:4]), int(r["date"][5:7])): float(r["value"]) for r in csv.DictReader(f)
        }


def tidy_annual(name: str) -> dict[int, float]:
    path = HISTORY_DIR / f"{name}.csv"
    if not path.is_file():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {int(r["date"][:4]): float(r["value"]) for r in csv.DictReader(f)}


def check(rows: dict[int, str]) -> int:
    """Cruces de `consistency.md` seccion 14. Devuelve 1 si alguno falla."""
    fx = {y: float(v) for y, v in rows.items()}
    failures = 0
    years = sorted(fx)
    print(
        f"\n[cobertura] {years[0]}-{years[-1]}, {len(years)} años; faltan en el crudo: "
        f"{[y for y in range(1960, years[-1] + 1) if y not in fx]}"
    )

    # (a) monotonia en el tramo enlazado hacia atras (el peso siempre se deprecio).
    linked = [y for y in years if y <= LAST_LINKED_YEAR]
    drops = [(y, fx[y - 1], fx[y]) for y in linked if (y - 1) in fx and fx[y] < fx[y - 1]]
    print(f"[monotonia {linked[0]}-{linked[-1]}] caidas año a año: {drops or 'ninguna'}")
    failures += bool(drops)

    # (b) serie en la moneda de cada epoca (solo lectura humana).
    print("[moneda de la epoca] valor WDI x factor legal acumulado:")
    for y in years:
        for y0, y1, label, factor in EPOCHS:
            if y0 <= y <= y1:
                print(f"  {y}: {fx[y]:.6g} ARS/USD = {fx[y] * factor:,.4g} {label} por USD")
                break

    # (c) continuidad con la mensual en 1992-01.
    monthly = tidy_monthly("exchange_rate_official_monthly")
    jan92 = monthly.get((1992, 1))
    if jan92 is not None and 1991 in fx:
        diff = abs(fx[1991] - jan92) / jan92 * 100
        print(
            f"[empalme] WDI 1991 = {fx[1991]:.4f} vs mensual 1992-01 = {jan92:.4f} "
            f"-> diferencia {diff:.2f} % (umbral 10 %)"
        )
        failures += diff >= 10
        if 1992 in fx:
            diff92 = abs(fx[1992] - jan92) / jan92 * 100
            print(f"[empalme] WDI 1992 = {fx[1992]:.4f} vs mensual 1992-01 -> {diff92:.2f} %")

    # (d) promedio anual de la mensual (fin de mes, BCRA) vs WDI (promedio de
    #     promedios mensuales, IFS) en los años en comun.
    by_year: dict[int, list[float]] = {}
    for (y, _m), v in monthly.items():
        by_year.setdefault(y, []).append(v)
    pairs = [
        (y, fx[y], sum(vs) / len(vs))
        for y, vs in sorted(by_year.items())
        if y in fx and len(vs) == 12
    ]
    if pairs:
        pct = [abs(a - b) / b * 100 for _, a, b in pairs]
        worst = max(zip(pairs, pct, strict=True), key=lambda t: t[1])
        print(
            f"[anual vs mensual] {pairs[0][0]}-{pairs[-1][0]}, n={len(pairs)}: diferencia "
            f"porcentual abs media {sum(pct) / len(pct):.2f} %, max {worst[1]:.2f} % en "
            f"{worst[0][0]} (WDI {worst[0][1]:.4f} vs media mensual {worst[0][2]:.4f})"
        )
        for (y, a, b), p in zip(pairs, pct, strict=True):
            print(f"  {y}: WDI {a:.4f} | media de fin de mes {b:.4f} | {p:.2f} %")

    # (e) orden de magnitud contra la inflacion acumulada.
    infl = tidy_annual("inflation_cpi_annual_linked")
    y0, y1 = linked[0], linked[-1]
    if all(y in infl for y in range(y0 + 1, y1 + 1)):
        log10_cpi = sum(math.log10(1 + infl[y] / 100) for y in range(y0 + 1, y1 + 1))
        log10_fx = math.log10(fx[y1] / fx[y0])
        brecha = log10_cpi - log10_fx
        print(
            f"[inflacion] {y0}->{y1}: precios x10^{log10_cpi:.2f} "
            f"(inflation_cpi_annual_linked, producto de 1+pi) vs tipo de cambio "
            f"x10^{log10_fx:.2f} (WDI); brecha 10^{brecha:.2f} = factor "
            f"{10**brecha:.1f} (parte es inflacion de EE.UU. en el periodo, "
            "parte apreciacion real)"
        )
        failures += abs(log10_cpi - log10_fx) > 2
    return int(failures > 0)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--wdi-csv",
        type=Path,
        default=RAW_DEFAULT,
        help="PA.NUS.FCRF_WDI.csv del mirror (default: copia en history/raw/)",
    )
    ap.add_argument("--no-check", action="store_true", help="no correr los cruces")
    args = ap.parse_args()
    if not args.wdi_csv.is_file():
        print(f"falta {args.wdi_csv}", file=sys.stderr)
        return 1
    print(f"crudo {args.wdi_csv.name}: sha256={sha256(args.wdi_csv)}")
    rows = read_argentina_row(args.wdi_csv)
    write_tidy(rows)
    if args.no_check:
        return 0
    rc = check(rows)
    print("\ncruces: " + ("OK" if rc == 0 else "FALLO (ver arriba)"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
