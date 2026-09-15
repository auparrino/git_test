#!/usr/bin/env python3
"""Descarga las series argentinas que este entorno no puede alcanzar.

Este script está pensado para correr en TU máquina (no en el entorno del
agente, donde `api.worldbank.org`, `imf.org`, `indec.gob.ar`, `bcra.gob.ar` y
`datos.gob.ar` están bloqueados). No inventa ningún número: cada función pega
contra un endpoint oficial documentado y escribe el mismo formato tidy que el
resto de `data/countries/argentina/history/` (`date,value,unit,source_id`).

Uso:

    uv run --with requests python scripts/fetch_argentina_local.py --all
    uv run --with requests python scripts/fetch_argentina_local.py --list
    uv run --with requests python scripts/fetch_argentina_local.py \
        --series inflation_deflator_annual

No se corrió nunca contra la red real (bloqueada desde este entorno): cada
función fue escrita contra la documentación pública de cada API al 2026-09,
pero conviene revisar el JSON de respuesta la primera vez que se corre, por si
alguna API cambió de forma.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "countries" / "argentina" / "history"

WB_API = "https://api.worldbank.org/v2/country/ARG/indicator/{code}?format=json&per_page=20000"
DATOS_GOB_API = "https://apis.datos.gob.ar/series/api/series?ids={series_id}&limit=5000&format=json"
BCRA_MONETARIAS = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias/{id_variable}?limit=5000"
BCRA_CAMBIARIAS = (
    "https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones/{moneda}"
    "?fechadesde={desde}&fechahasta={hasta}&limit=5000"
)
MECON_DEUDA = "https://www.argentina.gob.ar/sites/default/files/deuda_publica_{dd}-{mm}-{yyyy}.xlsx"
# Microdatos EPH, series historicas (sin API, hay que descargar a mano):
INDEC_EPH_BASE = "https://www.indec.gob.ar/ftp/cuadros/sociedad/"


def _write_tidy(path: Path, rows: list[tuple[str, float, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value", "unit", "source_id"])
        for r in sorted(rows):
            w.writerow(r)
    print(f"escrito {path} ({len(rows)} filas)")


def fetch_inflation_deflator_annual():
    """Deflactor del PIB, % anual. datasets/inflation en GitHub no tiene Argentina;
    el dato SÍ existe en la API del Banco Mundial (bloqueada desde el agente).
    Indicador: NY.GDP.DEFL.KD.ZG (deflactor del PIB, % de variación anual).
    """
    import requests

    url = WB_API.format(code="NY.GDP.DEFL.KD.ZG")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    rows = []
    for entry in data[1]:
        if entry.get("value") is None:
            continue
        year = int(entry["date"])
        rows.append(
            (
                f"{year:04d}-01-01",
                float(entry["value"]),
                "% anual (deflactor del PIB, World Bank NY.GDP.DEFL.KD.ZG)",
                "wb_inflation_deflator",
            )
        )
    _write_tidy(OUT_DIR / "inflation_deflator_annual.csv", rows)


def fetch_exchange_rate_annual_pre1992():
    """Tipo de cambio anual 1810-1991 (previo a la cobertura de BCRA_Data /
    DiLoretoT, que arranca en 1992). No hay una única fuente moderna con toda
    esta historia (austral, peso ley 18.188, peso moneda nacional, distintos
    regímenes cambiarios). Fuente recomendada: series históricas del BCRA
    ("Series estadísticas") o CEPAL/MECON. Este fetcher intenta la API de
    cotizaciones históricas del BCRA, que en la práctica solo llega hasta
    1992 (después de eso, ya está cubierto por reserves/exchange_rate del
    resto del pipeline) -- se deja documentado el intento y el resultado se
    debe revisar a mano.
    """
    import requests

    url = BCRA_CAMBIARIAS.format(moneda="USD", desde="1810-01-01", hasta="1991-12-31")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    rows = []
    for det in data.get("results", {}).get("detalle", []):
        rows.append(
            (
                det["fecha"][:7] + "-01",
                det["tipoCotizacion"],
                "ARS/USD (BCRA cotizaciones historicas)",
                "bcra_cambiarias_pre1992",
            )
        )
    if not rows:
        print(
            "BCRA solo publica cotizaciones desde ~1992 vía esta API; para 1810-1991 "
            "hace falta digitalizar series históricas (CEPAL, 'Series históricas del "
            "Banco Central', o Della Paolera & Taylor 'Straining at the Anchor'). "
            "No se escribe ningún archivo -- no hay endpoint oficial descargable."
        )
        return
    _write_tidy(OUT_DIR / "exchange_rate_annual.csv", rows)


def fetch_unemployment_pre2003():
    """Desocupación EPH puntual 1974-2003 (la serie continua de datos.gob.ar
    usada en unemployment.csv arranca en 2003, cuando la EPH pasa a ser
    continua). La EPH puntual (onda mayo/octubre) previa está en microdatos
    históricos de INDEC, sin API; hay que descargar los cuadros XLS de
    'Series históricas EPH puntual' a mano.
    """
    print(
        "La EPH puntual (1974-2003) no tiene API: descargar manualmente los cuadros "
        "de 'Mercado de trabajo. Principales indicadores' en "
        f"{INDEC_EPH_BASE} y normalizar a mano. No hay endpoint que este script "
        "pueda pegarle automáticamente."
    )


def fetch_datos_gob_ar_series(series_id: str, out_name: str, unit: str, source_id: str):
    """Genérico: cualquier serie de la API de series de datos.gob.ar por su id."""
    import requests

    r = requests.get(DATOS_GOB_API.format(series_id=series_id), timeout=30)
    r.raise_for_status()
    data = r.json()
    rows = []
    for date, value in data.get("data", []):
        if value is None:
            continue
        rows.append((date, float(value), unit, source_id))
    _write_tidy(OUT_DIR / out_name, rows)


def fetch_public_debt_breakdown():
    """Deuda pública por acreedor (FMI, organismos, títulos) más allá del
    total ya cubierto en public_debt.csv. Fuente: Excel oficial de MECON,
    un archivo por trimestre/mes, sin API -- hay que iterar fechas y parsear
    la hoja 'A.2.5' con pandas/openpyxl. Se deja el patrón de URL y una
    función de ejemplo para un mes; recorrer el rango deseado a mano.
    """
    import io

    import pandas as pd
    import requests

    # Ejemplo: deuda pública a fin de diciembre de 2023.
    url = MECON_DEUDA.format(dd="31", mm="12", yyyy="2023")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(r.content))
    print("Hojas disponibles:", xls.sheet_names)
    print(
        "Buscar la hoja 'A.2.5' (o el nombre vigente) y parsear a mano; "
        "el formato del Excel cambia de tanto en tanto. Repetir por cada "
        "fecha de publicación (trimestral) para tener la serie completa."
    )


SERIES = {
    "inflation_deflator_annual": fetch_inflation_deflator_annual,
    "exchange_rate_annual": fetch_exchange_rate_annual_pre1992,
    "unemployment_pre2003": fetch_unemployment_pre2003,
    "public_debt_breakdown": fetch_public_debt_breakdown,
}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--all", action="store_true", help="corre todas las series")
    ap.add_argument("--series", choices=sorted(SERIES), help="corre una sola serie")
    ap.add_argument("--list", action="store_true", help="lista las series disponibles")
    args = ap.parse_args()

    if args.list or not (args.all or args.series):
        print("Series disponibles:")
        for name in sorted(SERIES):
            print(f"  - {name}")
        if not (args.all or args.series):
            return

    if args.all:
        for name, fn in SERIES.items():
            print(f"=== {name} ===")
            try:
                fn()
            except Exception as exc:  # pragma: no cover - script manual
                print(f"FALLÓ {name}: {exc}", file=sys.stderr)
    elif args.series:
        SERIES[args.series]()


if __name__ == "__main__":
    main()
