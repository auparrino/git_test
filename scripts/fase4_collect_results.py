#!/usr/bin/env python3
"""Arma `simulations/fase4_logs/RESULTADOS.md` a partir de las salidas de
`scripts/fase4_ollama.sh` (Fase 4 con Ollama local, ADR 004).

Pensado para correr en TU máquina después del script: lee los logs de
`bench-parse` (una tabla `rich` por rol), los tiempos de corrida, los
reportes de comparación (`compare_*.md`, ya en Markdown) y el hardware, y
deja un solo Markdown con las tablas en el mismo orden que
`docs/FASE4_BENCH_OLLAMA.md` y `docs/FASE4_RESULTS_OLLAMA.md`, listo para
pegar en esos documentos (o para leerlo directo). No calcula nada nuevo:
solo recolecta y ordena lo que ya está en los logs. Si un log falta, la
sección queda marcada como "pendiente", nunca con un número inventado.

Uso:

    uv run python scripts/fase4_collect_results.py                # default: simulations/fase4_logs
    uv run python scripts/fase4_collect_results.py --logs otra/carpeta --out salida.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROLES = ("governor", "president", "union", "media")
ROLE_ACTOR = {
    "governor": "gov_capital",
    "president": "president",
    "union": "union_cgt",
    "media": "media_mercado",
}
BENCH_METRICS = (
    "parse_rate",
    "authority_violation_rate",
    "latencia p50 (ms)",
    "latencia p90 (ms)",
    "tokens prompt (media)",
    "tokens completion (media)",
)

_ROW_RE = re.compile(r"^\s*[│|]\s*(?P<k>[^│|]+?)\s*[│|]\s*(?P<v>[^│|]+?)\s*[│|]\s*$")
_REAL_RE = re.compile(r"^real\s+(\d+)m([\d.]+)s", re.MULTILINE)


def parse_bench(text: str) -> dict[str, str]:
    """Lee la tabla `rich` de `bench-parse` (Metrica | Valor) a un dict."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if m:
            out[m.group("k").strip()] = m.group("v").strip()
    return out


def wall_time(text: str) -> str:
    m = _REAL_RE.search(text)
    if not m:
        return "pendiente"
    minutes, seconds = int(m.group(1)), float(m.group(2))
    return f"{minutes * 60 + seconds:.1f} s"


def read_or_none(path: Path) -> str | None:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def bench_section(logs: Path, model: str) -> list[str]:
    lines = [
        "## `bench-parse` por rol (n = 50, seed 7)",
        "",
        f"Modelo: `{model}`.",
        "",
        "| rol (actor) | parse_rate | authority_violation_rate | latencia p50 / p90 (ms) "
        "| tokens prompt / completion (media) | tiempo total |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for role in ROLES:
        text = read_or_none(logs / f"bench_{role}.txt")
        if text is None:
            pend = " | ".join(["pendiente"] * 5)
            lines.append(f"| {role} (`{ROLE_ACTOR[role]}`) | {pend} |")
            continue
        metrics = parse_bench(text)

        def get(key: str, _m: dict[str, str] = metrics) -> str:
            return _m.get(key, "pendiente")

        lines.append(
            f"| {role} (`{ROLE_ACTOR[role]}`) | {get('parse_rate')} | "
            f"{get('authority_violation_rate')} | {get('latencia p50 (ms)')} / "
            f"{get('latencia p90 (ms)')} | {get('tokens prompt (media)')} / "
            f"{get('tokens completion (media)')} | {wall_time(text)} |"
        )
    lines.append("")
    return lines


def runs_section(logs: Path, model: str) -> list[str]:
    lines = [
        "## Tiempos de corrida (48 meses, seed 7)",
        "",
        "| corrida | `rules` | LLM |",
        "|---|---:|---:|",
    ]
    for label, a, b in (
        ("Aurora", "run_rules_aurora.txt", "run_llm_aurora.txt"),
        ("Argentina 2019-12", "run_rules_ar_2019.txt", "run_llm_ar_2019.txt"),
    ):
        ta = read_or_none(logs / a)
        tb = read_or_none(logs / b)
        lines.append(
            f"| {label} | {wall_time(ta) if ta else 'pendiente'} | "
            f"{wall_time(tb) if tb else 'pendiente'} |"
        )
    lines += ["", f"LLM: `{model}`.", ""]
    return lines


def passthrough_section(title: str, path: Path) -> list[str]:
    text = read_or_none(path)
    if text is None:
        return [f"## {title}", "", f"pendiente (`{path.name}` no existe)", ""]
    return [f"## {title}", "", text.rstrip(), ""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--logs", type=Path, default=Path("simulations/fase4_logs"))
    ap.add_argument("--out", type=Path, default=None, help="Default: <logs>/RESULTADOS.md")
    ap.add_argument("--model", default=None, help="Etiqueta del modelo (default: de model_*.txt)")
    args = ap.parse_args()
    logs: Path = args.logs
    out: Path = args.out or logs / "RESULTADOS.md"
    if not logs.exists():
        print(f"No existe {logs}: corré primero scripts/fase4_ollama.sh")
        return 1

    model = args.model
    if model is None:
        candidates = sorted(logs.glob("model_*.txt"))
        model = candidates[0].stem.removeprefix("model_") if candidates else "pendiente"

    doc: list[str] = ["# Fase 4 con Ollama — resultados recolectados", ""]
    doc += passthrough_section("Entorno (`hardware.txt`)", logs / "hardware.txt")
    doc += bench_section(logs, model)
    doc += runs_section(logs, model)
    doc += passthrough_section(
        "Comparación Aurora (`compare_aurora.md`)", logs / "compare_aurora.md"
    )
    doc += passthrough_section(
        "Comparación Argentina 2019-12 (`compare_ar_2019.md`)", logs / "compare_ar_2019.md"
    )
    doc += passthrough_section("Evals (`eval_compare.txt`)", logs / "eval_compare.txt")
    out.write_text("\n".join(doc) + "\n", encoding="utf-8")
    print(f"OK -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
