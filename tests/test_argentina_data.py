"""Tests de integridad para data/countries/argentina/history/.

No dependen de pandas/numpy: el repo base no los trae como dependencia
obligatoria, así que estos tests usan solo `csv`/`re` de la librería estándar
(ver ADR sobre dependencias perezosas en pyproject.toml).

Reglas verificadas (ver docs/PLAN_ARGENTINA.md §0 y §3):
  - cada CSV tidy parsea sin error;
  - las fechas son ISO (YYYY-MM-DD) y estrictamente crecientes (monótonas, sin
    duplicados);
  - los valores son numéricos (float parseable) en todas las columnas de dato;
  - cada `source_id` usado en algún CSV aparece documentado en SOURCES.md.
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

import pytest

HISTORY_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "countries" / "argentina" / "history"
)
SOURCES_MD = HISTORY_DIR / "SOURCES.md"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _tidy_csv_files() -> list[Path]:
    if not HISTORY_DIR.exists():
        return []
    return sorted(HISTORY_DIR.glob("*.csv"))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _documented_source_ids() -> set[str]:
    """source_id son los tokens en líneas `**source_id**: `xxx`` de SOURCES.md,
    más cualquier `source_id=xxx` mencionado en prosa (para las series
    mensuales, documentadas junto con la extracción de cada columna)."""
    text = SOURCES_MD.read_text(encoding="utf-8")
    ids = set()
    ids.update(re.findall(r"\*\*source_id\*\*:\s*`([a-zA-Z0-9_]+)`", text))
    ids.update(re.findall(r"`source_id=([a-zA-Z0-9_]+)`", text))
    # La tabla resumen tiene una columna `source_id` con backticks, a veces
    # dos ids separados por " / " en la misma celda.
    for cell in re.findall(r"\|\s*`([a-zA-Z0-9_]+(?:`\s*/\s*`[a-zA-Z0-9_]+)*)`\s*\|", text):
        for token in re.split(r"`\s*/\s*`", cell):
            ids.add(token)
    return ids


CSV_FILES = _tidy_csv_files()


def test_history_dir_has_csvs() -> None:
    assert HISTORY_DIR.is_dir(), f"falta {HISTORY_DIR}"
    assert CSV_FILES, "no hay ningun CSV tidy en data/countries/argentina/history/"


def test_sources_md_exists() -> None:
    assert SOURCES_MD.is_file(), "falta SOURCES.md junto a los CSV"


@pytest.mark.parametrize("path", CSV_FILES, ids=lambda p: p.name)
def test_csv_parses_and_has_expected_columns(path: Path) -> None:
    rows = _read_rows(path)
    assert rows, f"{path.name} no tiene filas"
    header = list(rows[0].keys())
    assert "date" in header, f"{path.name} no tiene columna 'date'"
    assert "source_id" in header, f"{path.name} no tiene columna 'source_id'"
    if path.name != "vdem_argentina.csv":
        assert "value" in header, f"{path.name} no tiene columna 'value'"
        assert "unit" in header, f"{path.name} no tiene columna 'unit'"


@pytest.mark.parametrize("path", CSV_FILES, ids=lambda p: p.name)
def test_dates_are_iso_and_monotonic_no_duplicates(path: Path) -> None:
    rows = _read_rows(path)
    dates = [r["date"] for r in rows]
    for d in dates:
        assert DATE_RE.match(d), f"{path.name}: fecha no ISO: {d!r}"
        y, m, day = (int(x) for x in d.split("-"))
        date(y, m, day)  # lanza ValueError si no es una fecha real
    assert len(dates) == len(set(dates)), f"{path.name}: hay fechas duplicadas"
    assert dates == sorted(dates), f"{path.name}: las fechas no estan en orden creciente"


@pytest.mark.parametrize("path", CSV_FILES, ids=lambda p: p.name)
def test_values_are_numeric(path: Path) -> None:
    rows = _read_rows(path)
    header = list(rows[0].keys())
    value_cols = [c for c in header if c not in ("date", "source_id", "unit")]
    assert value_cols, f"{path.name} no tiene ninguna columna de valor"
    for row in rows:
        has_any_value = False
        for col in value_cols:
            raw = row[col]
            if raw == "" or raw is None:
                continue
            has_any_value = True
            try:
                float(raw)
            except ValueError:
                pytest.fail(f"{path.name}: valor no numerico en columna {col!r}: {raw!r}")
        assert has_any_value, f"{path.name}: fila con fecha {row['date']} no tiene ningun valor"


@pytest.mark.parametrize("path", CSV_FILES, ids=lambda p: p.name)
def test_source_ids_documented_in_sources_md(path: Path) -> None:
    documented = _documented_source_ids()
    rows = _read_rows(path)
    used = {row["source_id"] for row in rows if row.get("source_id")}
    undocumented = used - documented
    assert not undocumented, (
        f"{path.name}: source_id sin documentar en SOURCES.md: {sorted(undocumented)} "
        f"(documentados: {sorted(documented)})"
    )


# ---------------------------------------------------------------------------
# Series "_linked": empalman una extensión hacia atrás (nueva, trust B) con el
# archivo tidy existente (sin tocarlo). Dos cosas hay que verificar en cada
# empalme: (a) el tramo que se supone copiado del archivo base es *idéntico*
# al archivo base (si no, "keeping the existing file untouched" se rompió), y
# (b) el empalme no da un salto absurdo justo en la fecha de corte (chequeo de
# consistencia del overlap, calculado a partir de los propios archivos, sin
# números pegados a mano).
# ---------------------------------------------------------------------------

# (archivo linked, archivo base, primera fecha ISO que viene copiada del base)
LINKED_SERIES = [
    (
        "exchange_rate_parallel_monthly_linked.csv",
        "exchange_rate_parallel_monthly.csv",
        "2011-01-01",
    ),
    (
        "inflation_cpi_annual_linked.csv",
        "inflation_cpi_annual.csv",
        "1961-01-01",
    ),
    (
        "inflation_cpi_monthly_linked.csv",
        "inflation_cpi_monthly.csv",
        "1997-02-01",
    ),
    (
        "poverty_linked.csv",
        "poverty.csv",
        "2003-07-01",
    ),
]


def _linked_pairs():
    pairs = []
    for linked_name, base_name, splice_date in LINKED_SERIES:
        linked_path = HISTORY_DIR / linked_name
        base_path = HISTORY_DIR / base_name
        if linked_path.is_file() and base_path.is_file():
            pairs.append((linked_path, base_path, splice_date))
    return pairs


LINKED_PAIRS = _linked_pairs()


@pytest.mark.parametrize(
    "linked_path,base_path,splice_date", LINKED_PAIRS, ids=lambda x: getattr(x, "name", x)
)
def test_linked_series_preserve_existing_file_verbatim(
    linked_path: Path, base_path: Path, splice_date: str
) -> None:
    """El tramo del archivo `_linked` a partir de `splice_date` debe coincidir,
    fila a fila (value + source_id), con el archivo base existente -- esa es
    la garantía de "keeping the existing file untouched" del enunciado: el
    `_linked` no reinterpreta el dato ya publicado, solo antepone una
    extensión nueva antes de `splice_date`."""
    linked_rows = {r["date"]: r for r in _read_rows(linked_path)}
    base_rows = _read_rows(base_path)

    assert base_rows, f"{base_path.name} esta vacio"
    for row in base_rows:
        assert row["date"] in linked_rows, (
            f"{linked_path.name}: falta la fecha {row['date']} de {base_path.name}"
        )
        linked_row = linked_rows[row["date"]]
        assert linked_row["value"] == row["value"], (
            f"{linked_path.name} en {row['date']}: value {linked_row['value']!r} "
            f"!= {row['value']!r} en {base_path.name}"
        )
        assert linked_row["source_id"] == row["source_id"], (
            f"{linked_path.name} en {row['date']}: source_id {linked_row['source_id']!r} "
            f"!= {row['source_id']!r} en {base_path.name}"
        )

    # Y las fechas anteriores al empalme son una extensión nueva, no una
    # duplicación de filas que ya estaban en el archivo base.
    new_dates = {d for d in linked_rows if d < splice_date}
    assert new_dates, f"{linked_path.name}: no aporta ninguna fecha nueva antes de {splice_date}"
    base_dates = {r["date"] for r in base_rows}
    assert not (new_dates & base_dates), (
        f"{linked_path.name}: hay fechas nuevas que ya estaban en {base_path.name}"
    )


@pytest.mark.parametrize(
    "linked_path,base_path,splice_date", LINKED_PAIRS, ids=lambda x: getattr(x, "name", x)
)
def test_linked_series_splice_has_no_absurd_jump(
    linked_path: Path, base_path: Path, splice_date: str
) -> None:
    """Chequeo de consistencia del empalme: el valor inmediatamente antes de
    `splice_date` y el valor en `splice_date` (fuentes distintas, unidas en el
    mismo archivo) no deberian diferir por un factor disparatado -- eso
    delataria una extension con la unidad, el signo o la escala equivocada.
    El umbral es deliberadamente laxo (10x) porque algunas series tienen
    variaciones grandes legitimas entre un dato y el siguiente (inflacion
    anual en anios de crisis); no es una prueba de precision, es una red para
    errores de empalme groseros."""
    rows = _read_rows(linked_path)
    rows_by_date = sorted(rows, key=lambda r: r["date"])
    idx_splice = next(i for i, r in enumerate(rows_by_date) if r["date"] == splice_date)
    assert idx_splice > 0, f"{linked_path.name}: {splice_date} es la primera fila, no hay empalme"
    before = float(rows_by_date[idx_splice - 1]["value"])
    after = float(rows_by_date[idx_splice]["value"])
    if before == 0 or after == 0:
        return  # división por cero: no aplica el chequeo de razón
    ratio = max(abs(before), abs(after)) / min(abs(before), abs(after))
    assert ratio < 10, (
        f"{linked_path.name}: salto de {before!r} a {after!r} justo en el empalme "
        f"({splice_date}) -- razon {ratio:.2f}x, revisar unidad/escala"
    )


def test_exchange_rate_parallel_linked_overlap_within_5_percent() -> None:
    """Reproduce el chequeo de `consistency.md` seccion 4: sobre los meses en
    comun entre el tramo nuevo pre-2011 (fuente ahierro/ipc_csv_processor) y
    el resto de la serie, la diferencia porcentual absoluta media debe seguir
    bajo el 5% pedido por el enunciado. Como el archivo `_linked` ya no
    contiene el overlap explicito (se descarta a favor del valor existente),
    este test lo mide comparando el crecimiento del ultimo tramo nuevo
    (2010) contra el primer tramo existente (2011) -- una cota de
    plausibilidad barata que no depende de re-descargar nada."""
    path = HISTORY_DIR / "exchange_rate_parallel_monthly_linked.csv"
    if not path.is_file():
        pytest.skip("exchange_rate_parallel_monthly_linked.csv no existe")
    rows = {r["date"]: float(r["value"]) for r in _read_rows(path)}
    dec_2010 = rows.get("2010-12-01")
    jan_2011 = rows.get("2011-01-01")
    assert dec_2010 is not None and jan_2011 is not None
    pct_diff = abs(jan_2011 - dec_2010) / dec_2010 * 100
    assert pct_diff < 5, (
        f"salto dic-2010 -> ene-2011 de {pct_diff:.2f}% en el dolar blue, "
        "mayor al 5% esperado para un mes calendario sin devaluacion grande registrada"
    )


# ---------------------------------------------------------------------------
# `exchange_rate_annual_linked.csv` (SOURCES.md fuente 22, WDI `PA.NUS.FCRF`):
# cierra el pendiente "holdout sin tipo de cambio mensual antes de 1992" de
# `docs/PLAN_ARGENTINA.md` seccion 7. Los cuatro tests de abajo son los cruces
# de `consistency.md` seccion 14 que se pueden verificar sin re-descargar nada
# (el script `scripts/build_argentina_fx_linked.py` corre los cinco).
# ---------------------------------------------------------------------------

FX_LINKED = "exchange_rate_annual_linked.csv"


def _fx_linked_by_year() -> dict[int, float]:
    path = HISTORY_DIR / FX_LINKED
    if not path.is_file():
        pytest.skip(f"{FX_LINKED} no existe")
    return {int(r["date"][:4]): float(r["value"]) for r in _read_rows(path)}


def test_fx_linked_covers_the_holdout_window() -> None:
    """El holdout de la calibracion (`1983-12:1991-12`, ADR 012 secc. 6) tiene
    que quedar cubierto: ese era el pendiente."""
    fx = _fx_linked_by_year()
    faltantes = [y for y in range(1983, 1993) if y not in fx]
    assert not faltantes, f"sin dato de tipo de cambio para {faltantes} (holdout 1983-1991)"


def test_fx_linked_is_monotonic_through_the_redenominations() -> None:
    """Cruce (a) de `consistency.md` seccion 14: el peso se deprecio todos los
    años de 1962 a 1991, asi que una caida año a año delataria un factor de
    redenominacion mal aplicado (1970, 1983, 1985, 1992)."""
    fx = _fx_linked_by_year()
    caidas = [
        (y, fx[y - 1], fx[y])
        for y in sorted(fx)
        if y <= 1991 and (y - 1) in fx and fx[y] < fx[y - 1]
    ]
    assert not caidas, f"caidas año a año en el tramo enlazado: {caidas}"


def test_fx_linked_splices_with_the_monthly_series() -> None:
    """Cruce (c): el valor anual de 1991 y el mensual de 1992-01 tienen que
    estar en la misma unidad (pesos convertibles), con menos de 10% de
    diferencia -- el promedio de 1991 contra el punto de enero de 1992."""
    fx = _fx_linked_by_year()
    monthly_path = HISTORY_DIR / "exchange_rate_official_monthly.csv"
    if not monthly_path.is_file():
        pytest.skip("exchange_rate_official_monthly.csv no existe")
    monthly = {r["date"]: float(r["value"]) for r in _read_rows(monthly_path)}
    jan_92 = monthly.get("1992-01-01")
    assert jan_92 is not None and 1991 in fx
    pct = abs(fx[1991] - jan_92) / jan_92 * 100
    assert pct < 10, (
        f"empalme 1991 ({fx[1991]:.4f}) vs 1992-01 ({jan_92:.4f}) con {pct:.2f}% de "
        "diferencia: posible cruce de unidad"
    )


def test_fx_linked_order_of_magnitude_matches_accumulated_inflation() -> None:
    """Cruce (e): entre 1962 y 1991 los precios y el tipo de cambio tienen que
    crecer ordenes de magnitud comparables (la brecha son la inflacion de
    EE.UU. del periodo y la apreciacion real, no un error de unidad)."""
    import math

    fx = _fx_linked_by_year()
    infl_path = HISTORY_DIR / "inflation_cpi_annual_linked.csv"
    if not infl_path.is_file():
        pytest.skip("inflation_cpi_annual_linked.csv no existe")
    infl = {int(r["date"][:4]): float(r["value"]) for r in _read_rows(infl_path)}
    if not all(y in infl for y in range(1963, 1992)):
        pytest.skip("inflation_cpi_annual_linked.csv no cubre 1963-1991 completo")
    log10_cpi = sum(math.log10(1 + infl[y] / 100) for y in range(1963, 1992))
    log10_fx = math.log10(fx[1991] / fx[1962])
    assert abs(log10_cpi - log10_fx) < 2, (
        f"precios x10^{log10_cpi:.2f} vs tipo de cambio x10^{log10_fx:.2f} 1962-1991: "
        "brecha mayor a 2 ordenes de magnitud, revisar unidades"
    )
