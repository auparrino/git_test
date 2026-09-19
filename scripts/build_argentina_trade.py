#!/usr/bin/env python3
"""Construye `exports_annual_usd.csv` e `imports_annual_usd.csv` (bienes y
servicios, USD corrientes, anual) desde los indicadores `NE.EXP.GNFS.CD` y
`NE.IMP.GNFS.CD` del World Development Indicators del Banco Mundial, vía el
mirror `ronnywang/worldbank` (el mismo de las fuentes 17 y 22).

Por qué hacía falta (sonda exploratoria, `docs/EMERGENCE_LOG.md`): ADR 012
§4 define `X0`/`M0` —el nivel base de exportaciones e importaciones del
balance de pagos— como "se leen del estado inicial real cuando existen" y,
mientras tanto, un proxy `0.18 · gdp_usd / 12`. Ese proxy nunca se
reemplazó, y sobreestima las importaciones argentinas de 1991 por un factor
de 3 (2 850 contra 961 USD M/mes reales). Como `R_min`, el piso de reservas
que dispara la salida forzada de un `peg`, es *3 meses de importaciones*,
el proxy lo ponía en 8 550 USD M contra reservas reales de 7 844: **el peg
de la convertibilidad salía en el mes 1**, en abril de 1991, el mes en que
la convertibilidad empezó. Con el dato real, `R_min` es 2 883 y no sale.

No inventa ningún número: cada fila es la celda del CSV crudo para
`Country Code == "ARG"`, sin transformar. Cobertura 1962–2012 (el snapshot
del mirror es de diciembre de 2013).

Uso:

    uv run python scripts/build_argentina_trade.py

o desde el mirror recién bajado:

    curl -sSL -o /tmp/NE.EXP.GNFS.CD_WDI.csv \\
      https://raw.githubusercontent.com/ronnywang/worldbank/master/WDI_bundle/parsed/NE.EXP.GNFS.CD_WDI.csv
    uv run python scripts/build_argentina_trade.py --raw-dir /tmp
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = REPO_ROOT / "data" / "countries" / "argentina" / "history"
RAW_DEFAULT = HISTORY_DIR / "raw" / "worldbank_mirror"

SERIES = {
    "NE.EXP.GNFS.CD": (
        "exports_annual_usd.csv",
        "USD corrientes, exportaciones anuales de bienes y servicios "
        "(WDI NE.EXP.GNFS.CD, via ronnywang/worldbank snapshot 2013-12)",
        "wb_exports_mirror",
    ),
    "NE.IMP.GNFS.CD": (
        "imports_annual_usd.csv",
        "USD corrientes, importaciones anuales de bienes y servicios "
        "(WDI NE.IMP.GNFS.CD, via ronnywang/worldbank snapshot 2013-12)",
        "wb_imports_mirror",
    ),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def argentina_row(wdi_csv: Path, indicator: str) -> dict[int, str]:
    with open(wdi_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("Country Code") != "ARG":
                continue
            got = r.get("Indicator Code")
            if got != indicator:
                raise SystemExit(
                    f"{wdi_csv}: indicador inesperado {got!r}, se esperaba {indicator!r}"
                )
            return {int(k): v.strip() for k, v in r.items() if k and k.isdigit() and v}
    raise SystemExit(f"{wdi_csv}: no hay fila con Country Code == ARG")


def write_tidy(out: Path, rows: dict[int, str], unit: str, source_id: str) -> None:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "value", "unit", "source_id"])
        for y in sorted(rows):
            w.writerow([f"{y:04d}-01-01", rows[y], unit, source_id])
    years = sorted(rows)
    print(f"escrito {out.relative_to(REPO_ROOT)} ({len(rows)} filas, {years[0]} -> {years[-1]})")


def check(exports: dict[int, str], imports: dict[int, str]) -> int:
    """Cruces de `consistency.md` seccion 15."""
    x = {y: float(v) for y, v in exports.items()}
    m = {y: float(v) for y, v in imports.items()}
    fallas = 0

    print("\n[importaciones mensuales reales vs el proxy 0.18*PIB/12 que reemplazan]")
    gdp_path = HISTORY_DIR / "gdp_usd.csv"
    gdp: dict[int, float] = {}
    if gdp_path.is_file():
        with open(gdp_path, newline="", encoding="utf-8") as f:
            gdp = {int(r["date"][:4]): float(r["value"]) for r in csv.DictReader(f)}
    for y in (1991, 1998, 2003, 2010):
        if y not in m:
            continue
        real = m[y] / 1e6 / 12.0
        linea = f"  {y}: real {real:8.1f} USD M/mes"
        if y in gdp:
            proxy = 0.18 * (gdp[y] / 1e6) / 12.0
            linea += f" | proxy {proxy:8.1f} | factor {proxy / real:.2f}x"
        print(linea)

    print("\n[balanza comercial: signo contra episodios conocidos]")
    esperado = {1991: "+", 1998: "-", 2003: "+", 2009: "+"}
    for y, signo in esperado.items():
        if y not in x or y not in m:
            continue
        saldo = (x[y] - m[y]) / 1e9
        ok = (saldo > 0) == (signo == "+")
        fallas += not ok
        print(f"  {y}: {saldo:+7.2f} bn USD, esperado {signo} -> {'OK' if ok else 'FALLA'}")

    print("\n[apertura: (X+M)/PIB, Argentina es una economia relativamente cerrada]")
    for y in (1991, 1998, 2003, 2010):
        if y in x and y in m and y in gdp:
            ap = 100.0 * (x[y] + m[y]) / gdp[y]
            fuera = not (5.0 <= ap <= 50.0)
            fallas += fuera
            print(f"  {y}: {ap:5.1f} % del PIB{'  <- FUERA DE [5, 50]' if fuera else ''}")
    return int(fallas > 0)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--raw-dir", type=Path, default=RAW_DEFAULT)
    ap.add_argument("--no-check", action="store_true")
    args = ap.parse_args()

    tablas: dict[str, dict[int, str]] = {}
    for indicator, (nombre, unit, source_id) in SERIES.items():
        raw = args.raw_dir / f"{indicator}_WDI.csv"
        if not raw.is_file():
            print(f"falta {raw}", file=sys.stderr)
            return 1
        print(f"crudo {raw.name}: sha256={sha256(raw)}")
        rows = argentina_row(raw, indicator)
        write_tidy(HISTORY_DIR / nombre, rows, unit, source_id)
        tablas[indicator] = rows

    if args.no_check:
        return 0
    rc = check(tablas["NE.EXP.GNFS.CD"], tablas["NE.IMP.GNFS.CD"])
    print("\ncruces: " + ("OK" if rc == 0 else "FALLO (ver arriba)"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
