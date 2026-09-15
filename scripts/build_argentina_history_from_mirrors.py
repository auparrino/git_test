#!/usr/bin/env python3
"""Construye series tidy de `data/countries/argentina/history/` a partir de
mirrors públicos en GitHub (única red alcanzable desde el entorno del agente:
`api.worldbank.org`, `api.bcra.gob.ar`, `datos.gob.ar`, `indec.gob.ar` y
`argentina.gob.ar` responden 403 en el proxy de egreso, ver `coverage.md`).

No inventa ningún número: cada fila sale de un CSV de uno de estos dos repos,
clonados a un commit fijo (documentado en `SOURCES.md`, fuentes 18-19):

- `thomasriveros/BCRA_Data` (`data/bcra_monetary.csv`): snapshot diario de las
  "Principales Variables" de la API oficial del BCRA. Se usa la variable
  `id_variable=27` "Inflación mensual" (IPC, % mensual, 1943-03 → hoy).
- `argendatafundar/data` (Fundar, CC BY-NC-SA 4.0): tablas de CEDLAS
  "Indicadores Sociales de Argentina" (pobreza 1974-2025) y el desempleo
  modelado OIT del Banco Mundial (`SL.UEM.TOTL.ZS`, 1991-2023).

Salidas (todas `date,value,unit,source_id`, fechas ISO, una fila por fecha):

- `inflation_cpi_monthly_linked.csv`: BCRA 1943-03 → 1997-01 + copia literal
  de `inflation_cpi_monthly.csv` (1997-02 →). No toca el archivo base.
- `poverty_linked.csv`: EPH puntual nacional (CEDLAS ISA) 2001-05 → 2003-05 +
  copia literal de `poverty.csv` (2003-07 →). No toca el archivo base.
- `poverty_gba.csv`: pobreza GBA (% personas) 1988-05 → 2006 S2, INDEC vía
  CEDLAS ISA.
- `poverty_gba_households_beccaria.csv` / `poverty_gba_households_arakaki.csv`:
  pobreza GBA (% hogares) 1974-1989, dos estimaciones académicas distintas
  (no coinciden en los años en común, por eso van en archivos separados).
- `poverty_cedlas_homogeneous.csv` / `indigence_cedlas_homogeneous.csv`:
  serie nacional homogénea de CEDLAS 1992-05 → 2025 S1 (metodología propia,
  NO es la serie oficial de INDEC; ver `consistency.md` sección 11).
- `unemployment_annual_modelled.csv`: desempleo modelado OIT (Banco Mundial
  `SL.UEM.TOTL.ZS`) 1991-2022.

Además copia a `history/raw/` los CSV crudos chicos usados (y un extracto de
`bcra_monetary.csv` con solo la variable 27) e imprime el sha256 de cada
archivo crudo leído, para pegarlo en `SOURCES.md`.

Uso:

    git clone --depth 1 https://github.com/thomasriveros/BCRA_Data /tmp/m/BCRA_Data
    git clone --depth 1 https://github.com/argendatafundar/data /tmp/m/argendata
    uv run python scripts/build_argentina_history_from_mirrors.py \
        --bcra-data /tmp/m/BCRA_Data --argendata /tmp/m/argendata

Convención de fechas (la misma que ya usa `poverty.csv`, verificada en
`consistency.md` sección 11): un dato semestral se fecha al **cierre** del
semestre (1er semestre de 2003 → `2003-07-01`, 2do semestre → `2004-01-01`);
un dato mensual (onda mayo/octubre de la EPH puntual, o IPC mensual) se
fecha al día 1 del mes de la observación.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = REPO_ROOT / "data" / "countries" / "argentina" / "history"
RAW_DIR = HISTORY_DIR / "raw"

Row = tuple[str, str, str, str]  # date, value (texto literal), unit, source_id


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def write_tidy(path: Path, rows: list[Row]) -> None:
    rows = sorted(rows)
    dates = [r[0] for r in rows]
    if len(dates) != len(set(dates)):
        dup = sorted({d for d in dates if dates.count(d) > 1})
        raise SystemExit(f"{path.name}: fechas duplicadas {dup[:5]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "value", "unit", "source_id"])
        for r in rows:
            w.writerow(r)
    rel = path.relative_to(REPO_ROOT)
    print(f"escrito {rel} ({len(rows)} filas, {rows[0][0]} -> {rows[-1][0]})")


def existing_rows_verbatim(path: Path) -> list[Row]:
    """Filas del archivo base tal cual están (value como texto, sin
    reparsear): la garantía "no se toca el archivo existente" de las series
    `_linked` (ver tests/test_argentina_data.py)."""
    return [(r["date"], r["value"], r["unit"], r["source_id"]) for r in read_csv(path)]


def semester_date(year: int, semester: int) -> str:
    """Cierre del semestre, misma convención que `poverty.csv` (ver docstring)."""
    if semester == 1:
        return f"{year:04d}-07-01"
    if semester == 2:
        return f"{year + 1:04d}-01-01"
    raise ValueError(semester)


def month_date(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-01"


def num(text: str) -> str:
    """Normaliza el texto numérico de la fuente sin cambiar su valor
    (`"29.80000"` -> `"29.8"`), para que el CSV tidy no arrastre ceros."""
    return str(Decimal(text).normalize()) if "." in text else text


# ---------------------------------------------------------------------------
# BCRA_Data: inflación mensual 1943-03 -> (id_variable = 27)
# ---------------------------------------------------------------------------

BCRA_UNIT_CPI = (
    "% variacion mensual del IPC (BCRA 'Principales Variables' id 27 'Inflacion mensual', "
    "serie historica empalmada de INDEC, via thomasriveros/BCRA_Data)"
)


def build_inflation_monthly_linked(bcra_monetary: Path) -> None:
    base = HISTORY_DIR / "inflation_cpi_monthly.csv"
    base_rows = existing_rows_verbatim(base)
    splice = base_rows[0][0]  # primera fecha del archivo base (1997-02-01)

    new: list[Row] = []
    extract: list[dict[str, str]] = []
    with open(bcra_monetary, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["id_variable"] != "27":
                continue
            extract.append(r)
            d = month_date(int(r["fecha"][:4]), int(r["fecha"][5:7]))
            if d < splice:
                new.append((d, num(r["valor"]), BCRA_UNIT_CPI, "bcra_data_inflacion_mensual"))
    if not new:
        raise SystemExit("bcra_monetary.csv no tiene filas de id_variable=27 antes del empalme")

    # extracto crudo (solo la variable 27) para history/raw/
    RAW_DIR.joinpath("bcra_data").mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "bcra_data" / "bcra_monetary_id27_inflacion_mensual.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(extract[0].keys()))
        w.writeheader()
        w.writerows(extract)
    rel = out.relative_to(REPO_ROOT)
    print(f"extracto crudo {rel} ({len(extract)} filas) sha256={sha256(out)}")

    write_tidy(HISTORY_DIR / "inflation_cpi_monthly_linked.csv", new + base_rows)


# ---------------------------------------------------------------------------
# argendata / CEDLAS ISA: pobreza
# ---------------------------------------------------------------------------


def _it2_rows(path: Path) -> list[dict[str, str]]:
    return [r for r in read_csv(path) if r["poverty_rate"] not in ("", "NA")]


def _date_of(r: dict[str, str]) -> str:
    y, n = int(r["year"]), int(r["date"])
    return month_date(y, n) if r["period_type"] == "mes" else semester_date(y, n)


def build_poverty_linked(it2: Path) -> None:
    base = HISTORY_DIR / "poverty.csv"
    base_rows = existing_rows_verbatim(base)
    splice = base_rows[0][0]  # 2003-07-01
    unit = (
        "% de personas bajo la linea de pobreza, total aglomerados urbanos, EPH puntual "
        "onda mayo/octubre (INDEC, via CEDLAS ISA / argendatafundar)"
    )
    new: list[Row] = []
    for r in _it2_rows(it2):
        if r["region"] != "national" or r["survey"] != "EPH-Puntual":
            continue
        d = _date_of(r)
        if d < splice:
            new.append((d, num(r["poverty_rate"]), unit, "argendata_cedlas_isa_pobreza_nacional"))
    write_tidy(HISTORY_DIR / "poverty_linked.csv", new + base_rows)


def build_poverty_gba(it2: Path) -> None:
    rows: list[Row] = []
    for r in _it2_rows(it2):
        if r["region"] != "GBA":
            continue
        if r["survey"] == "EPH-Puntual":
            unit = (
                "% de personas bajo la linea de pobreza, Gran Buenos Aires, EPH puntual onda "
                "mayo/octubre (INDEC, via CEDLAS ISA / argendatafundar)"
            )
        else:
            unit = (
                "% de personas bajo la linea de pobreza, Gran Buenos Aires, EPH continua, "
                "semestre fechado a su cierre (INDEC, via CEDLAS ISA / argendatafundar)"
            )
        rows.append((_date_of(r), num(r["poverty_rate"]), unit, "argendata_cedlas_isa_pobreza_gba"))
    write_tidy(HISTORY_DIR / "poverty_gba.csv", rows)


def build_poverty_gba_households(it1: Path) -> None:
    by_author: dict[str, list[Row]] = {}
    for r in read_csv(it1):
        if r["poverty_rate"] in ("", "NA"):
            continue
        author = r["pov_type"]
        unit = (
            f"% de hogares pobres, Gran Buenos Aires, estimacion de {author.capitalize()} "
            "(CEDLAS ISA, via argendatafundar)"
        )
        by_author.setdefault(author, []).append(
            (
                f"{int(r['year']):04d}-01-01",
                num(r["poverty_rate"]),
                unit,
                f"argendata_cedlas_isa_pobreza_gba_hogares_{author}",
            )
        )
    for author, rows in sorted(by_author.items()):
        write_tidy(HISTORY_DIR / f"poverty_gba_households_{author}.csv", rows)


def build_cedlas_homogeneous(it3: Path) -> None:
    for line, fname in (("pobreza", "poverty"), ("indigencia", "indigence")):
        rows: list[Row] = []
        for r in read_csv(it3):
            if r["poverty_line"] != line or r["poverty_rate"] in ("", "NA"):
                continue
            if r["period_type"] == "mes":
                when = "EPH puntual onda mayo/octubre"
            else:
                when = "EPH continua, semestre fechado a su cierre"
            unit = (
                f"% de personas bajo la linea de {line}, total nacional, serie homogenea de "
                f"CEDLAS ISA (metodologia propia, no es la serie oficial INDEC), {when} "
                "(via argendatafundar)"
            )
            source_id = f"argendata_cedlas_isa_{line}_homogenea"
            rows.append((_date_of(r), num(r["poverty_rate"]), unit, source_id))
        write_tidy(HISTORY_DIR / f"{fname}_cedlas_homogeneous.csv", rows)


# ---------------------------------------------------------------------------
# argendata / Banco Mundial: desempleo modelado OIT
# ---------------------------------------------------------------------------


def build_unemployment_modelled(path: Path) -> None:
    # argendata declara (campo `aclaraciones` del .json) que el valor 2023 de
    # ARG fue "corregido a mano" con el dato de INDEC porque la API del Banco
    # Mundial no respondia: no es el valor de la fuente declarada, se excluye.
    excluded_years = {2023}
    rows: list[Row] = []
    for r in read_csv(path):
        if r["geocodigoFundar"] != "ARG":
            continue
        y = int(r["anio"])
        if y in excluded_years:
            continue
        pct = Decimal(r["tasa_desempleo"]) * 100  # la fuente lo trae como proporcion
        rows.append(
            (
                f"{y:04d}-01-01",
                str(pct.normalize()),
                "% de la fuerza laboral, desempleo total modelado OIT (Banco Mundial "
                "SL.UEM.TOTL.ZS, via argendatafundar)",
                "argendata_wb_ilo_desempleo",
            )
        )
    write_tidy(HISTORY_DIR / "unemployment_annual_modelled.csv", rows)


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--bcra-data", type=Path, required=True, help="clon de thomasriveros/BCRA_Data")
    ap.add_argument("--argendata", type=Path, required=True, help="clon de argendatafundar/data")
    args = ap.parse_args()

    bcra_monetary = args.bcra_data / "data" / "bcra_monetary.csv"
    it1 = args.argendata / "POBREZ" / "ISA_pobreza_monetaria_it1.csv"
    it2 = args.argendata / "POBREZ" / "ISA_pobreza_monetaria_it2.csv"
    it3 = args.argendata / "POBREZ" / "ISA_pobreza_monetaria_it3.csv"
    ilo = args.argendata / "INFDES" / "tasa_desempleo_arg_mundial_modelada.csv"

    for p in (bcra_monetary, it1, it2, it3, ilo):
        if not p.is_file():
            print(f"falta {p}", file=sys.stderr)
            return 1
        print(f"crudo {p.name}: sha256={sha256(p)}")

    RAW_DIR.joinpath("argendata").mkdir(parents=True, exist_ok=True)
    for p in (it1, it2, it3, ilo):
        shutil.copyfile(p, RAW_DIR / "argendata" / p.name)

    build_inflation_monthly_linked(bcra_monetary)
    build_poverty_linked(it2)
    build_poverty_gba(it2)
    build_poverty_gba_households(it1)
    build_cedlas_homogeneous(it3)
    build_unemployment_modelled(ilo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
