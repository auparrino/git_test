"""`republica emergence` (ADR 005 secc. 6): deteccion de patrones emergentes
sobre un JSONL de `republica run` -- alianzas formadas, coaliciones de voto
que se repiten contra el score ideologico, acuerdos rotos y medios que
cambiaron de linea. Materia prima de `docs/EMERGENCE_LOG.md`."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from republica.engine.narrate import Loaded

#: Coalicion de voto "repetida" a partir de esta cantidad de veces (ADR 005
#: secc. 6, literal: ">= 3").
REPEATED_COALITION_MIN = 3


@dataclass
class EmergenceReport:
    alliances: list[dict[str, Any]] = field(default_factory=list)
    repeated_coalitions: list[dict[str, Any]] = field(default_factory=list)
    broken_agreements: list[dict[str, Any]] = field(default_factory=list)
    media_line_changes: list[dict[str, Any]] = field(default_factory=list)
    #: Cohorte con menor `approval_c` promedio en toda la corrida (ADR 005
    #: secc. 3/6, deliverable 6): `None` sin `kind: "cohorts"` en el JSONL
    #: (`--no-cohorts`).
    most_discontented_cohort: dict[str, Any] | None = None
    #: Mes con mayor `|perception_gap|` (ADR 005 secc. 4/6): `None` sin
    #: `kind: "perception"` (`--no-cohorts`/`--no-media`).
    max_perception_gap_month: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "alliances": self.alliances,
            "repeated_coalitions": self.repeated_coalitions,
            "broken_agreements": self.broken_agreements,
            "media_line_changes": self.media_line_changes,
            "most_discontented_cohort": self.most_discontented_cohort,
            "max_perception_gap_month": self.max_perception_gap_month,
        }


def _detect_alliances(loaded: Loaded) -> list[dict[str, Any]]:
    out = []
    for actions in loaded.actions_by_month.values():
        for a in actions:
            if a.get("authorized") and a.get("type") == "FORM_ALLIANCE":
                out.append({"month": a["month"], "actor": a["actor"], "with": a["target"]})
    out.sort(key=lambda a: a["month"])
    return out


def _detect_repeated_coalitions(loaded: Loaded) -> list[dict[str, Any]]:
    """Conjunto de partidos que votan "contra su score ideologico" (`score <
    0` pero termino votando si -- `yes_prob >= 0.5` -- o al reves) juntos:
    si el MISMO conjunto se repite `>= REPEATED_COALITION_MIN` veces en
    distintos `Bill`, se reporta (ADR 005 secc. 6)."""
    coalition_bills: dict[frozenset[str], list[str]] = {}
    for votes in loaded.votes_by_month.values():
        for v in votes:
            against_ideology = frozenset(
                p["party_id"]
                for p in v["parties"]
                if (p["score"] < 0) == (p["yes_prob"] >= 0.5) and p["score"] != 0
            )
            if len(against_ideology) < 2:
                continue
            coalition_bills.setdefault(against_ideology, []).append(v["bill_id"])
    out = []
    for coalition, bills in coalition_bills.items():
        if len(bills) >= REPEATED_COALITION_MIN:
            out.append({"parties": sorted(coalition), "bills": bills, "count": len(bills)})
    out.sort(key=lambda c: -c["count"])
    return out


def _detect_broken_agreements(loaded: Loaded) -> list[dict[str, Any]]:
    out = []
    for record in loaded.records:
        for event in record.get("events", []):
            if event.startswith("agreement_broken:"):
                _, actor_id, concession, by = event.split(":")
                out.append(
                    {
                        "month": record["month_index"],
                        "actor": actor_id,
                        "concession": concession,
                        "broken_by": by,
                    }
                )
    return out


def _detect_media_line_changes(loaded: Loaded) -> list[dict[str, Any]]:
    """Version minima (perception/medios completo es la segunda mitad de
    Fase 5, ver ADR 005 secc. 4): usa el `frame` que cada medio elige mes a
    mes via `PUBLISH_STORY` (ya disponible desde ADR 003 secc. 6.3) y cuenta
    cuantas veces cada uno cambio de linea a lo largo de la corrida."""
    last_frame: dict[str, str] = {}
    changes: Counter[str] = Counter()
    months = sorted(loaded.actions_by_month)
    for month in months:
        for a in loaded.actions_by_month[month]:
            if a.get("type") != "PUBLISH_STORY" or not a.get("authorized"):
                continue
            outlet = a["actor"]
            frame = a["params"]["frame"]
            prev = last_frame.get(outlet)
            if prev is not None and prev != frame:
                changes[outlet] += 1
            last_frame[outlet] = frame
    return [{"outlet": outlet, "line_changes": n} for outlet, n in changes.most_common() if n > 0]


def _detect_most_discontented_cohort(loaded: Loaded) -> dict[str, Any] | None:
    """Cohorte con menor `approval_c` promediado sobre toda la corrida (ADR
    005 secc. 3/6): usa `MonthRecord.cohorts` (`records`), no un `kind`
    aparte -- `approval_c` es estado de cada mes, no un evento."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for record in loaded.records:
        for cohort_id, values in (record.get("cohorts") or {}).items():
            totals[cohort_id] = totals.get(cohort_id, 0.0) + values["approval_c"]
            counts[cohort_id] = counts.get(cohort_id, 0) + 1
    if not totals:
        return None
    averages = {cid: totals[cid] / counts[cid] for cid in totals}
    worst = min(averages, key=lambda cid: averages[cid])
    return {"cohort": worst, "avg_approval_c": round(averages[worst], 2)}


def _detect_max_perception_gap_month(loaded: Loaded) -> dict[str, Any] | None:
    """Mes con mayor `|perception_gap|` de toda la corrida (ADR 005 secc.
    4/6, `kind: "perception"`)."""
    best_month: int | None = None
    best_gap = 0.0
    best_abs = -1.0
    for month, perceptions in loaded.perceptions_by_month.items():
        for p in perceptions:
            gap = p["perception_gap"]
            if abs(gap) > best_abs:
                best_abs = abs(gap)
                best_gap = gap
                best_month = month
    if best_month is None:
        return None
    return {"month": best_month, "perception_gap": round(best_gap, 3)}


def detect(loaded: Loaded) -> EmergenceReport:
    return EmergenceReport(
        alliances=_detect_alliances(loaded),
        repeated_coalitions=_detect_repeated_coalitions(loaded),
        broken_agreements=_detect_broken_agreements(loaded),
        media_line_changes=_detect_media_line_changes(loaded),
        most_discontented_cohort=_detect_most_discontented_cohort(loaded),
        max_perception_gap_month=_detect_max_perception_gap_month(loaded),
    )
