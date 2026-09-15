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
