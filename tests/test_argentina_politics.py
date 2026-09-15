"""Tests estructurales para data/countries/argentina/politics/ (fase A1, ver
docs/PLAN_ARGENTINA.md §0/§1/§2 fila A1).

No valida el contenido histórico (eso es tarea del revisor independiente, ver
PENDING_FACTCHECK.md dentro de la carpeta) sino que los archivos parsean, que
regimes.csv tiene exactamente una fila por año 1810-2023, que toda
presidency_start tiene su presidency_end (o es la actual), que las fechas son
monótonas dentro de cada `kind` y que cada parties/<era>.json valida contra un
modelo pydantic mínimo.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel, Field, ValidationError

POLITICS_DIR = Path(__file__).resolve().parents[1] / "data" / "countries" / "argentina" / "politics"

EVENT_KINDS = {
    "presidency_start", "presidency_end", "coup", "election_presidential",
    "election_legislative", "constitutional_reform", "default", "imf_agreement",
    "hyperinflation", "crisis_banking", "war", "pandemic", "currency_regime_change", "other",
}
REGIME_MODES = {
    "democracy", "restricted_democracy", "coup", "dictatorship", "transition",
    "civil_war_or_state_building",
}
HOW_SELECTED_VALUES = {"election", "coup", "succession", "congress", "junta"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
DATE_PRECISION_VALUES = {"day", "month", "year"}

PARTY_ERAS = [
    "1916-1930", "1946-1955", "1958-1966", "1973-1976",
    "1983-2001", "2003-2015", "2015-2023",
]


def read_csv(name: str) -> list[dict]:
    path = POLITICS_DIR / name
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# events.csv
# ---------------------------------------------------------------------------

class EventModel(BaseModel):
    date: date
    date_precision: str
    kind: str
    title: str
    actor: str
    notes: str = ""
    source: str
    confidence: str

    @property
    def is_valid(self) -> bool:
        return (
            self.date_precision in DATE_PRECISION_VALUES
            and self.kind in EVENT_KINDS
            and self.confidence in CONFIDENCE_VALUES
        )


def load_events() -> list[EventModel]:
    rows = read_csv("events.csv")
    events = []
    for row in rows:
        ev = EventModel(**row)
        assert ev.date_precision in DATE_PRECISION_VALUES, row
        assert ev.kind in EVENT_KINDS, row
        assert ev.confidence in CONFIDENCE_VALUES, row
        events.append(ev)
    return events


def test_events_csv_parses_and_is_well_formed() -> None:
    events = load_events()
    assert len(events) > 100
    for ev in events:
        assert ev.title.strip()
        assert ev.actor.strip()
        assert ev.source.strip()


def test_events_dates_monotonic_within_kind() -> None:
    events = load_events()
    by_kind: dict[str, list[date]] = {}
    for ev in events:
        by_kind.setdefault(ev.kind, []).append(ev.date)
    for kind, dates in by_kind.items():
        assert dates == sorted(dates), f"dates not monotonic for kind={kind}"


def test_every_presidency_start_has_matching_end_or_is_current() -> None:
    events = load_events()
    starts = sorted((ev for ev in events if ev.kind == "presidency_start"), key=lambda e: e.date)
    ends = sorted((ev for ev in events if ev.kind == "presidency_end"), key=lambda e: e.date)
    assert len(starts) >= 1
    # every end must come after some start, and there is at most one "dangling"
    # start (the incumbent at the end of the chronology, i.e. the most recent one)
    assert len(starts) - len(ends) in (0, 1)
    if len(starts) - len(ends) == 1:
        # the dangling start must be the last (most recent) one chronologically
        last_start = starts[-1]
        assert all(e.date <= last_start.date for e in ends)
    # each end date must not precede its era's start date (paired by chronological order)
    paired = list(zip(starts, ends, strict=False))
    for s, e in paired:
        assert e.date >= s.date, (s, e)


# ---------------------------------------------------------------------------
# regimes.csv
# ---------------------------------------------------------------------------

def test_regimes_csv_one_row_per_year_1810_2023() -> None:
    rows = read_csv("regimes.csv")
    years = [int(r["year"]) for r in rows]
    assert years == list(range(1810, 2024))
    assert len(years) == len(set(years)) == 2023 - 1810 + 1


def test_regimes_csv_values_well_formed() -> None:
    rows = read_csv("regimes.csv")
    for r in rows:
        assert r["regime_mode"] in REGIME_MODES, r
        assert r["how_selected"] in HOW_SELECTED_VALUES, r
        assert r["elections_held"] in ("True", "False")
        assert r["head_of_state"].strip()
        # vdem_regime is intentionally left empty for the reviewer to fill in
        assert r["vdem_regime"] == ""


# ---------------------------------------------------------------------------
# provinces.csv / regions.csv
# ---------------------------------------------------------------------------

def test_provinces_csv_has_24_jurisdictions() -> None:
    rows = read_csv("provinces.csv")
    assert len(rows) == 24
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    valid_regions = {
        "CABA", "GBA", "Pampeana", "Córdoba–Santa Fe",
        "NOA", "NEA", "Cuyo", "Patagonia",
    }
    for r in rows:
        assert r["region"] in valid_regions, r
        assert int(r["population_2022"]) > 0
        dep = float(r["dependence_on_transfers"])
        assert 0.0 <= dep <= 1.0


def test_regions_csv_aggregates_provinces() -> None:
    provinces = read_csv("provinces.csv")
    regions = read_csv("regions.csv")
    assert len(regions) == 8
    pop_by_region: dict[str, int] = {}
    for p in provinces:
        pop_by_region[p["region"]] = pop_by_region.get(p["region"], 0) + int(p["population_2022"])
    total_share = 0.0
    for r in regions:
        assert int(r["population_2022"]) == pop_by_region[r["region"]]
        share = float(r["gdp_share_approx"])
        assert 0.0 <= share <= 1.0
        total_share += share
    assert abs(total_share - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# shocks_calendar.csv
# ---------------------------------------------------------------------------

def test_shocks_calendar_csv_well_formed() -> None:
    rows = read_csv("shocks_calendar.csv")
    assert len(rows) >= 10
    for r in rows:
        date.fromisoformat(r["date"])
        assert int(r["duration_months"]) > 0
        mag = float(r["magnitude"])
        assert 0.0 <= mag <= 1.0
        assert r["confidence"] in CONFIDENCE_VALUES


# ---------------------------------------------------------------------------
# parties/<era>.json — pydantic validation
# ---------------------------------------------------------------------------

class PartyModel(BaseModel):
    id: str
    name: str
    economic: float = Field(ge=-1.0, le=1.0)
    social: float = Field(ge=-1.0, le=1.0)
    assessment: str
    federalism: float = Field(ge=-1.0, le=1.0)
    seats_share: float | None = Field(default=None, ge=0.0, le=1.0)
    in_government: bool
    notes: str = ""


@pytest.mark.parametrize("era", PARTY_ERAS)
def test_party_era_files_exist_and_validate(era: str) -> None:
    path = POLITICS_DIR / "parties" / f"{era}.json"
    assert path.exists(), f"missing {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) >= 1
    ids = []
    for entry in data:
        party = PartyModel(**entry)
        assert party.assessment == "analyst"
        ids.append(party.id)
    assert len(ids) == len(set(ids)), f"duplicate party ids in {era}"


def test_party_era_invalid_axis_is_rejected() -> None:
    bad = {
        "id": "x", "name": "x", "economic": 5.0, "social": 0.0,
        "assessment": "analyst", "federalism": 0.0, "in_government": False,
    }
    with pytest.raises(ValidationError):
        PartyModel(**bad)


# ---------------------------------------------------------------------------
# README / PENDING_FACTCHECK presence
# ---------------------------------------------------------------------------

def test_readme_and_pending_factcheck_exist() -> None:
    assert (POLITICS_DIR / "README.md").exists()
    pending = POLITICS_DIR / "PENDING_FACTCHECK.md"
    assert pending.exists()
    assert pending.stat().st_size > 0
