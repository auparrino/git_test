#!/usr/bin/env python3
"""Cruces de consistencia entre fuentes de `data/countries/argentina/history/`
(secciones 8-13 de `consistency.md`). Solo lee los CSV tidy ya escritos (y,
opcionalmente, el clon de `thomasriveros/BCRA_Data` y de
`argendatafundar/data` para los cruces que comparan contra el mirror crudo);
no modifica ningún archivo. Imprime las tablas que se pegan en
`consistency.md`. Ningún número de acá se usa para ajustar series.

    uv run python scripts/check_argentina_history_consistency.py \
        [--bcra-data DIR] [--argendata DIR]
"""

from __future__ import annotations

import argparse
import collections
import csv
import math
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
H = REPO_ROOT / "data" / "countries" / "argentina" / "history"


def tidy(name: str, key: int = 7) -> dict[str, float]:
    """`{date[:key]: value}` de un CSV tidy (key=7 -> mes, key=4 -> año, 10 -> día)."""
    with open(H / f"{name}.csv", newline="", encoding="utf-8") as f:
        return {r["date"][:key]: float(r["value"]) for r in csv.DictReader(f)}


def summarize(pairs: list[tuple[str, float, float]], label: str, unit: str = "pp") -> None:
    d = [abs(a - b) for _, a, b in pairs]
    worst = max(pairs, key=lambda p: abs(p[1] - p[2]))
    print(
        f"  {label}: n={len(pairs)} ({pairs[0][0]} -> {pairs[-1][0]}), "
        f"diff abs media={statistics.mean(d):.3f} {unit}, max={max(d):.2f} {unit} en {worst[0]} "
        f"({worst[1]:.3f} vs {worst[2]:.3f}), n>0.1={sum(1 for x in d if x > 0.1)}"
    )


def section_8_bcra_vs_jmtelechea() -> None:
    print("## 8. IPC mensual BCRA (id 27) vs inflation_cpi_monthly.csv (jmtelechea)")
    bcra = {}
    with open(
        H / "raw" / "bcra_data" / "bcra_monetary_id27_inflacion_mensual.csv", newline=""
    ) as f:
        for r in csv.DictReader(f):
            bcra[r["fecha"][:7]] = float(r["valor"])
    ex = tidy("inflation_cpi_monthly")
    common = sorted(set(bcra) & set(ex))
    pairs = [(k, ex[k], bcra[k]) for k in common]
    summarize(pairs, "todo el solapamiento")
    for a, b in (("1997", "2006"), ("2007", "2015"), ("2016", "2026")):
        sel = [p for p in pairs if a <= p[0][:4] <= b]
        summarize(sel, f"{a}-{b}")
    print("  peores 6 meses:")
    for k, a, b in sorted(pairs, key=lambda p: -abs(p[1] - p[2]))[:6]:
        print(f"    {k}: jmtelechea={a:.2f} bcra={b:.2f} diff={a - b:+.2f}")


def section_9_bcra_annual_vs_argendata_and_linked(argendata: Path | None) -> None:
    print("## 9. IPC mensual BCRA compuesto a anual (dic/dic) vs series anuales")
    by = collections.defaultdict(list)
    with open(
        H / "raw" / "bcra_data" / "bcra_monetary_id27_inflacion_mensual.csv", newline=""
    ) as f:
        for r in csv.DictReader(f):
            by[r["fecha"][:4]].append(float(r["valor"]))
    ann = {
        y: (math.prod(1 + v / 100 for v in vs) - 1) * 100 for y, vs in by.items() if len(vs) == 12
    }
    if argendata is not None:
        p = argendata / "PRECIO" / "3_tasa_de_inflacion_anual_argentina_1935_2022.csv"
        with open(p, newline="", encoding="utf-8") as f:
            arg = {r["anio"]: float(r["inflacion_todos"]) for r in csv.DictReader(f, delimiter=";")}
        common = sorted(set(ann) & set(arg))
        summarize(
            [(y, arg[y], ann[y]) for y in common],
            "argendata PRECIO/3 (dic/dic, INDEC) vs BCRA compuesto",
        )
    lk = tidy("inflation_cpi_annual_linked", key=4)
    common = sorted(set(ann) & set(lk))
    pairs = [(y, lk[y], ann[y]) for y in common]
    summarize(pairs, "inflation_cpi_annual_linked (Clio/BM, promedio anual) vs BCRA compuesto")
    for a, b in (("1944", "1960"), ("1961", "1990"), ("1991", "2006"), ("2007", "2023")):
        summarize([p for p in pairs if a <= p[0] <= b], f"  {a}-{b}")
    for y in ("1959", "1975", "1989", "1990", "2002", "2023"):
        if y in ann and y in lk:
            print(f"    {y}: BCRA compuesto={ann[y]:.1f}  anual_linked={lk[y]:.1f}")


def section_10_bcra_fx_reserves(bcra_data: Path | None) -> None:
    print("## 10. Snapshot BCRA_Data 2026-09-15 vs series ya cargadas (FX A3500, reservas, BADLAR)")
    if bcra_data is None:
        print("  (sin --bcra-data: omitido)")
        return
    last_fx: dict[str, tuple[str, float]] = {}
    res: dict[str, float] = {}
    bad = collections.defaultdict(list)
    with open(bcra_data / "data" / "bcra_monetary.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = r["fecha"][:7]
            if r["id_variable"] == "5":
                last_fx[m] = (r["fecha"], float(r["valor"]))
            elif r["id_variable"] == "1":
                res[m] = float(r["valor"])
            elif r["id_variable"] == "7":
                bad[m].append(float(r["valor"]))
    fx = tidy("exchange_rate_official_monthly")
    common = sorted(set(last_fx) & set(fx))
    pairs = [(k, fx[k], last_fx[k][1]) for k in common]
    pct = [abs(a - b) / a * 100 for _, a, b in pairs]
    worst = max(range(len(pairs)), key=lambda i: pct[i])
    print(
        f"  FX A3500 (id 5, ultimo dato del mes) vs exchange_rate_official_monthly: n={len(pairs)} "
        f"({common[0]} -> {common[-1]}), diff % abs media={statistics.mean(pct):.3f}%, "
        f"max={pct[worst]:.2f}% en {pairs[worst][0]} ({pairs[worst][1]} vs {pairs[worst][2]}), "
        f"n>0.5%={sum(1 for x in pct if x > 0.5)}"
    )
    exr = tidy("reserves_monthly")
    common = sorted(set(res) & set(exr))
    diff = [(k, exr[k], res[k]) for k in common if exr[k] != res[k]]
    print(f"  reservas (id 1): {len(common)} meses en comun, {len(diff)} distintos: {diff}")
    exb = tidy("policy_rate_monthly")
    common = sorted(set(bad) & set(exb))
    diff = [
        (k, exb[k], sum(bad[k]) / len(bad[k]))
        for k in common
        if abs(exb[k] - sum(bad[k]) / len(bad[k])) > 1e-9
    ]
    print(
        f"  BADLAR (id 7, promedio mensual): {len(common)} meses en comun, "
        f"{len(diff)} distintos: {diff}"
    )


def section_11_poverty() -> None:
    print("## 11. Pobreza: CEDLAS ISA (via argendata) vs poverty.csv (INDEC via datos.gob.ar)")
    ex = tidy("poverty", key=10)
    raw = H / "raw" / "argendata" / "ISA_pobreza_monetaria_it2.csv"
    with open(raw, newline="", encoding="utf-8") as f:
        it2 = [r for r in csv.DictReader(f) if r["poverty_rate"]]
    print("  it2 nacional, semestres EPH continua (fechados a cierre) vs poverty.csv:")
    for r in it2:
        if r["region"] == "national" and r["period_type"] == "semestre":
            y, s = int(r["year"]), int(r["date"])
            d = f"{y}-07-01" if s == 1 else f"{y + 1}-01-01"
            v = float(r["poverty_rate"])
            print(f"    {y} S{s} -> {d}: cedlas={v} poverty.csv={ex.get(d)} diff={v - ex[d]:+.2f}")
    hom = tidy("poverty_cedlas_homogeneous", key=10)
    pairs = [(d, ex[d], hom[d]) for d in sorted(set(ex) & set(hom))]
    summarize(pairs, "serie homogenea CEDLAS vs poverty.csv (todo)")
    for a, b in (("2003", "2015"), ("2016", "2026")):
        summarize([p for p in pairs if a <= p[0][:4] <= b], f"  {a}-{b}")
    gba = tidy("poverty_gba", key=10)
    lk = tidy("poverty_linked", key=10)
    pairs = [(d, lk[d], gba[d]) for d in sorted(set(lk) & set(gba))]
    summarize(
        pairs,
        "GBA vs nacional (poverty_linked), mismas fechas "
        "(no deberian coincidir: geografias distintas)",
    )


def section_12_unemployment() -> None:
    print(
        "## 12. Desempleo modelado OIT (anual) vs unemployment.csv (EPH trimestral, promedio anual)"
    )
    q = collections.defaultdict(list)
    for d, v in tidy("unemployment", key=10).items():
        q[d[:4]].append(v)
    eph = {y: sum(v) / len(v) for y, v in q.items() if len(v) == 4}
    ilo = tidy("unemployment_annual_modelled", key=4)
    pairs = [(y, eph[y], ilo[y]) for y in sorted(set(eph) & set(ilo))]
    summarize(pairs, "EPH promedio anual vs OIT modelado")
    for y, a, b in pairs:
        print(f"    {y}: EPH={a:.2f} OIT={b:.2f} diff={a - b:+.2f}")


def section_13_deflator(argendata: Path | None) -> None:
    print(
        "## 13. Deflactor implicito de argendata CRECIM (corriente/constante) "
        "vs gdp_deflator_annual.csv"
    )
    if argendata is None:
        print("  (sin --argendata: omitido)")
        return
    p = argendata / "CRECIM" / "pib_corriente_constante.csv"
    with open(p, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["geocodigoFundar"] == "ARG"]
    lvl = {int(r["anio"]): float(r["pib_corriente"]) / float(r["pib_constante"]) for r in rows}
    g = {y: (lvl[y] / lvl[y - 1] - 1) * 100 for y in lvl if y - 1 in lvl}
    ex = tidy("gdp_deflator_annual", key=4)
    pairs = [(str(y), ex[str(y)], g[y]) for y in sorted(g) if str(y) in ex]
    summarize(pairs, "BM NY.GDP.DEFL.KD.ZG (mirror 2013) vs implicito argendata")
    print(
        f"    ejemplo ARG 1960: pib_corriente={rows[0]['pib_corriente']} "
        "(escala de US$ corrientes, no pesos)"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bcra-data", type=Path)
    ap.add_argument("--argendata", type=Path)
    a = ap.parse_args()
    section_8_bcra_vs_jmtelechea()
    section_9_bcra_annual_vs_argendata_and_linked(a.argendata)
    section_10_bcra_fx_reserves(a.bcra_data)
    section_11_poverty()
    section_12_unemployment()
    section_13_deflator(a.argendata)


if __name__ == "__main__":
    main()
