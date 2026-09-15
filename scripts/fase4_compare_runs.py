"""Compara dos corridas JSONL de `republica run` (Fase 4: actores por reglas
vs. actores LLM) y escribe tablas Markdown listas para pegar en
`docs/FASE4_RESULTS_OLLAMA.md`.

    uv run python scripts/fase4_compare_runs.py \
        simulations/run_rules_aurora.jsonl simulations/run_llm_aurora.jsonl \
        --label-a rules --label-b "llm:ollama:qwen3:8b"

Lee solo lo que ya escribe `History.to_jsonl()` (ADR 003/004): lineas de mes
(sin `kind`), `{"kind": "action"}` (una por accion, con `authorized` y
`denied_reason`) y `{"kind": "trace"}` (`DecisionTrace`, solo actores no
`rules`). No importa nada de `republica.*`: sirve para corridas de cualquier
version del motor mientras esos tres esquemas no cambien.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

#: Marcador literal de `engine/permissions.py::authorize` (chequeo 1); es el
#: mismo criterio que usa `republica bench-parse` para
#: `authority_violation_rate` (ADR 004 secc. 10 punto 22).
AUTHORITY_VIOLATION_MARKER = "no tiene permitido"

POSITION_TYPES = ("SUPPORT_POLICY", "OPPOSE_POLICY", "NEGOTIATE")
FINAL_INDICATORS = (
    "government_approval",
    "inflation",
    "unemployment",
    "real_wage",
    "reserves",
    "exchange_rate",
    "protest_level",
    "congress_support",
)


class Run:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.months: list[dict] = []
        self.actions: list[dict] = []
        self.traces: list[dict] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                kind = rec.get("kind")
                if kind is None and "month_index" in rec:
                    self.months.append(rec)
                elif kind == "action":
                    self.actions.append(rec)
                elif kind == "trace":
                    self.traces.append(rec)

    @property
    def n_months(self) -> int:
        return max((m["month_index"] for m in self.months), default=0)

    def final_state(self) -> dict:
        return self.months[-1]["state"] if self.months else {}

    def actions_by_actor(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = defaultdict(list)
        for a in self.actions:
            out[a["actor"]].append(a)
        return out

    def position_by_actor_month(self) -> dict[tuple[str, int], str]:
        """Posicion del mes por actor: SUPPORT/OPPOSE/NEGOTIATE si emitio esa
        accion (misma lectura que `cli._actor_month_summary`), si no `neutral`."""
        pos: dict[tuple[str, int], str] = {}
        for a in self.actions:
            key = (a["actor"], a["month"])
            pos.setdefault(key, "neutral")
            if a["type"] in POSITION_TYPES:
                pos[key] = a["type"].replace("_POLICY", "")
        return pos


def _pct(num: float, den: float) -> str:
    return f"{100.0 * num / den:.1f}%" if den else "-"


def _fmt(v: object) -> str:
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[idx]


def section_summary(a: Run, b: Run, la: str, lb: str) -> list[str]:
    fa, fb = a.final_state(), b.final_state()
    lines = [
        "### Resumen y estado final",
        "",
        f"| | {la} | {lb} |",
        "|---|---:|---:|",
        f"| meses simulados | {a.n_months} | {b.n_months} |",
        f"| acciones registradas | {len(a.actions)} | {len(b.actions)} |",
        f"| trazas (`DecisionTrace`) | {len(a.traces)} | {len(b.traces)} |",
    ]
    for k in FINAL_INDICATORS:
        if k in fa or k in fb:
            lines.append(f"| final `{k}` | {_fmt(fa.get(k, '-'))} | {_fmt(fb.get(k, '-'))} |")
    return lines + [""]


def section_action_types(a: Run, b: Run, la: str, lb: str) -> list[str]:
    ca = Counter(x["type"] for x in a.actions)
    cb = Counter(x["type"] for x in b.actions)
    types = sorted(set(ca) | set(cb), key=lambda t: -(ca[t] + cb[t]))
    lines = [
        "### Distribucion de tipos de accion (todas las acciones emitidas)",
        "",
        f"| tipo | {la} n | {la} % | {lb} n | {lb} % |",
        "|---|---:|---:|---:|---:|",
    ]
    for t in types:
        lines.append(
            f"| {t} | {ca[t]} | {_pct(ca[t], len(a.actions))} | "
            f"{cb[t]} | {_pct(cb[t], len(b.actions))} |"
        )
    return lines + [""]


def section_positions(a: Run, b: Run, la: str, lb: str) -> list[str]:
    pa, pb = a.position_by_actor_month(), b.position_by_actor_month()
    actors = sorted({k[0] for k in pa} | {k[0] for k in pb})
    lines = [
        "### Posicion por actor (share de meses) y coincidencia entre corridas",
        "",
        "La coincidencia compara, mes a mes, la posicion del actor en las dos corridas "
        "(mismo seed y misma configuracion). Solo el mes 1 parte de la misma percepcion: "
        "despues las corridas divergen, asi que es una medida de *parecido de conducta*, "
        "no de exactitud.",
        "",
        f"| actor | {la} SUP/OPP/NEG/neutral | {lb} SUP/OPP/NEG/neutral | coincide |",
        "|---|---|---|---:|",
    ]
    for actor in actors:
        ma = {m: p for (x, m), p in pa.items() if x == actor}
        mb = {m: p for (x, m), p in pb.items() if x == actor}

        def share(d: dict[int, str]) -> str:
            c = Counter(d.values())
            n = len(d) or 1
            return "/".join(
                f"{100 * c[k] / n:.0f}" for k in ("SUPPORT", "OPPOSE", "NEGOTIATE", "neutral")
            )

        common = sorted(set(ma) & set(mb))
        agree = sum(1 for m in common if ma[m] == mb[m])
        lines.append(f"| {actor} | {share(ma)} | {share(mb)} | {_pct(agree, len(common))} |")
    return lines + [""]


def section_denied(a: Run, b: Run, la: str, lb: str) -> list[str]:
    def stats(run: Run) -> tuple[int, int, int]:
        denied = [x for x in run.actions if not x.get("authorized", True)]
        viol = [x for x in denied if AUTHORITY_VIOLATION_MARKER in (x.get("denied_reason") or "")]
        return len(run.actions), len(denied), len(viol)

    na, da, va = stats(a)
    nb, db, vb = stats(b)
    lines = [
        "### Acciones denegadas por `authorize()`",
        "",
        f"| | {la} | {lb} |",
        "|---|---:|---:|",
        f"| emitidas | {na} | {nb} |",
        f"| denegadas (cualquier motivo) | {da} ({_pct(da, na)}) | {db} ({_pct(db, nb)}) |",
        f"| fuera de rol (`{AUTHORITY_VIOLATION_MARKER}`) | {va} ({_pct(va, na)}) | "
        f"{vb} ({_pct(vb, nb)}) |",
        "",
    ]
    reasons_b = Counter(
        (x.get("denied_reason") or "")[:60] for x in b.actions if not x["authorized"]
    )
    if reasons_b:
        lines += [f"Motivos de denegacion mas frecuentes en {lb}:", ""]
        for r, n in reasons_b.most_common(8):
            lines.append(f"- {n}× `{r}`")
        lines.append("")
    return lines


def section_traces(run: Run, label: str) -> list[str]:
    if not run.traces:
        return [f"### Trazas de {label}", "", "_Sin `DecisionTrace` (cerebro `rules`)._", ""]
    t = run.traces
    parse_ok = sum(1 for x in t if x.get("parse_error") is None)
    emitted = sum(len(x.get("actions_emitted") or []) for x in t)
    viol = sum(
        1
        for x in t
        for d in x.get("actions_denied") or []
        if AUTHORITY_VIOLATION_MARKER in (d.get("denied_reason") or "")
    )
    lat = [float(x.get("latency_ms") or 0.0) for x in t]
    ptok = [int((x.get("tokens") or {}).get("prompt", 0)) for x in t]
    ctok = [int((x.get("tokens") or {}).get("completion", 0)) for x in t]
    attempts = [int(x.get("attempts") or 1) for x in t]
    models = Counter(x.get("model") for x in t)
    lines = [
        f"### Trazas de {label}",
        "",
        "| metrica | valor |",
        "|---|---:|",
        f"| trazas | {len(t)} |",
        f"| modelo(s) | {', '.join(f'{m} ({n})' for m, n in models.items())} |",
        f"| parse_rate | {parse_ok / len(t):.3f} |",
        f"| intentos promedio | {statistics.mean(attempts):.2f} |",
        f"| authority_violation_rate (fuera de rol / emitidas) | {_pct(viol, emitted)} |",
        f"| latencia p50 / p90 (ms) | {_percentile(lat, 0.5):.0f} / {_percentile(lat, 0.9):.0f} |",
        f"| latencia total (min) | {sum(lat) / 60000:.1f} |",
        f"| tokens prompt / completion (media) | {statistics.mean(ptok):.0f} / "
        f"{statistics.mean(ctok):.0f} |",
        "",
    ]
    failures = [x for x in t if x.get("parse_error") is not None]
    if failures:
        lines += ["Ejemplos de fallos de parseo:", ""]
        for x in failures[:5]:
            raw = (x.get("raw_response") or "").replace("\n", " ")[:160]
            lines.append(
                f"- mes {x['month']} `{x['actor_id']}`: `{x['parse_error']}` -- raw: `{raw}`"
            )
        lines.append("")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_a", type=Path)
    ap.add_argument("run_b", type=Path)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument(
        "--out", type=Path, default=None, help="Archivo .md de salida (default stdout)."
    )
    args = ap.parse_args()

    a, b = Run(args.run_a), Run(args.run_b)
    la, lb = args.label_a, args.label_b
    lines = [f"## {la} vs {lb}", "", f"- A: `{a.path}`", f"- B: `{b.path}`", ""]
    lines += section_summary(a, b, la, lb)
    lines += section_action_types(a, b, la, lb)
    lines += section_positions(a, b, la, lb)
    lines += section_denied(a, b, la, lb)
    lines += section_traces(a, la)
    lines += section_traces(b, lb)
    text = "\n".join(lines)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"escrito {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
