"""Visor HTML autocontenido de una corrida (`republica viewer run.jsonl --out viewer.html`).

Reproduce mes a mes: indicadores con variacion, shocks, eventos, reacciones de los actores,
votos y negociaciones, con cuatro graficos sincronizados y una linea de tiempo. No requiere
servidor ni red: el JSONL va embebido como JSON y el HTML es un archivo unico.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).with_name("viewer_template.html")

KEY_INDICATORS: list[tuple[str, str, str, int]] = [
    # clave, etiqueta, unidad, decimales
    ("gdp_growth", "PIB (anual)", "%", 1),
    ("inflation_annual", "Inflación (anual)", "%", 0),
    ("unemployment", "Desempleo", "%", 1),
    ("real_wage", "Salario real", "", 1),
    ("reserves", "Reservas", "USD M", 0),
    ("exchange_rate", "Tipo de cambio", "", 1),
    ("fiscal_balance", "Resultado fiscal", "% PIB", 1),
    ("public_debt", "Deuda", "% PIB", 0),
    ("government_approval", "Aprobación", "", 1),
    ("political_stability", "Estabilidad", "", 1),
    ("social_tension", "Tensión social", "", 1),
    ("poverty", "Pobreza", "%", 1),
]

# Indicadores que "mejoran" cuando bajan (la flecha se pinta al reves).
LOWER_IS_BETTER = {
    "inflation_annual",
    "unemployment",
    "exchange_rate",
    "public_debt",
    "social_tension",
    "poverty",
}


def _annual(monthly: float) -> float:
    return ((1.0 + monthly / 100.0) ** 12 - 1.0) * 100.0


def load_run(path: Path) -> dict[str, Any]:
    """Lee el JSONL y lo reorganiza por mes para el visor."""
    months: list[dict[str, Any]] = []
    actions: dict[int, list[dict[str, Any]]] = {}
    votes: dict[int, list[dict[str, Any]]] = {}
    negotiations: dict[int, list[dict[str, Any]]] = {}
    perceptions: dict[int, list[dict[str, Any]]] = {}
    elections: dict[int, list[dict[str, Any]]] = {}
    memories: dict[int, list[dict[str, Any]]] = {}
    #: `MemoryEvent`/`ElectionResult` (ADR 006, `kind: "memory"`/`"election"`),
    #: agrupados por mes igual que el resto de los sidecars -- extension
    #: minima para que el visor (editado aparte) pueda mostrarlos si quiere;
    #: no se toca `viewer_template.html` en este commit.
    summary: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        kind = rec.get("kind", "month")
        if "outcome" in rec and "month_index" not in rec and kind == "month":
            summary = rec
        elif kind == "month" or ("month_index" in rec and kind not in {"action", "trace"}):
            if "month_index" in rec:
                months.append(rec)
        elif kind == "action":
            actions.setdefault(int(rec["month"]), []).append(rec)
        elif kind == "vote":
            votes.setdefault(int(rec.get("month", 0)), []).append(rec)
        elif kind == "negotiation":
            negotiations.setdefault(int(rec.get("month", 0)), []).append(rec)
        elif kind == "perception":
            perceptions.setdefault(int(rec.get("month", 0)), []).append(rec)
        elif kind == "election":
            rec = {k: v for k, v in rec.items() if k != "intention"}
            elections.setdefault(int(rec.get("month", 0)), []).append(rec)
        elif kind == "memory":
            memories.setdefault(int(rec.get("month", 0)), []).append(rec)
    out_months = []
    # `month_index` es 0-based en v0.1 y 1-based desde Fase 6; los registros laterales
    # (`action`, `vote`, ...) usan siempre `month` 1-based. Se normaliza por la base real.
    base = min((int(r["month_index"]) for r in months), default=0)
    for rec in months:
        idx = int(rec["month_index"])
        month_no = idx - base + 1
        state = dict(rec["state"])
        state["inflation_annual"] = _annual(float(state["inflation"]))
        acts = [a for a in actions.get(month_no, []) if a.get("type") != "NO_ACTION"]
        acts.sort(
            key=lambda a: (
                bool(a.get("authorized", True)),
                float((a.get("params") or {}).get("intensity", 0.0) or 0.0),
            ),
            reverse=True,
        )
        out_months.append(
            {
                "i": idx,
                "date": rec.get("date", ""),
                "state": state,
                "policy": rec.get("policy", {}),
                "shocks_new": rec.get("shocks_new") or [],
                "shocks_active": rec.get("shocks_active") or rec.get("active_shocks") or [],
                "events": rec.get("events") or [],
                "actions": [
                    {
                        "actor": a.get("actor"),
                        "type": a.get("type"),
                        "authorized": a.get("authorized", True),
                        "reason": a.get("reason", ""),
                        "intensity": (a.get("params") or {}).get("intensity"),
                        "params": a.get("params") or {},
                    }
                    for a in acts[:8]
                ],
                "denied": sum(
                    1 for a in actions.get(month_no, []) if not a.get("authorized", True)
                ),
                "votes": votes.get(month_no, []),
                "negotiations": negotiations.get(month_no, []),
                "cohorts": rec.get("cohorts") or {},
                "perceptions": perceptions.get(month_no, []),
                "elections": elections.get(month_no, []),
                "memories": sorted(
                    memories.get(month_no, []),
                    key=lambda m: float(m.get("importance", 0.0)),
                    reverse=True,
                )[:4],
            }
        )
    return {
        "seed": summary.get("seed"),
        "outcome": summary.get("outcome", "?"),
        "config_hash": summary.get("config_hash", ""),
        "months": out_months,
        "indicators": [
            {"key": k, "label": lbl, "unit": u, "dec": d, "lower_better": k in LOWER_IS_BETTER}
            for k, lbl, u, d in KEY_INDICATORS
        ],
    }


def build_html(run: dict[str, Any], title: str | None = None) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = json.dumps(run, ensure_ascii=False).replace("</", "<\\/")
    page_title = title or f"Aurora · semilla {run.get('seed')}"
    return template.replace("__RUN_JSON__", payload).replace("__TITLE__", page_title)


def export(jsonl_path: Path, out_path: Path, title: str | None = None) -> Path:
    run = load_run(jsonl_path)
    out_path.write_text(build_html(run, title), encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 1:
        print("uso: python -m republica.ui.viewer run.jsonl [salida.html]")
        return 2
    src = Path(args[0])
    dst = Path(args[1]) if len(args) > 1 else src.with_suffix(".html")
    export(src, dst)
    print(f"OK -> {dst}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
