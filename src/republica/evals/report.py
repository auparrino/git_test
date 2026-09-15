"""`Report` (ADR 007 secc. 4): `report.json` + `report.md` de una corrida de
`republica eval`, mas `compare_reports()` (`republica eval compare a/ b/`)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from republica.evals.metrics import MetricResult

#: Nombre de archivo fijo dentro de un directorio de reporte (ADR secc. 4,
#: literal: "Produce report.json + report.md").
JSON_NAME = "report.json"
MD_NAME = "report.md"


@dataclass
class Report:
    brain: str
    judge: str
    seed: int
    suite: str
    metrics: list[MetricResult]
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "brain": self.brain,
            "judge": self.judge,
            "seed": self.seed,
            "suite": self.suite,
            "generated_at": self.generated_at,
            "metrics": [r.to_dict() for r in self.metrics],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Reporte de eval -- suite={self.suite} brain={self.brain} "
            f"judge={self.judge} seed={self.seed}",
            "",
            f"Generado: {self.generated_at}",
            "",
            "| metrica | valor | baseline (rules) | N | IC 95% |",
            "|---|---|---|---|---|",
        ]
        for r in self.metrics:
            value = f"{r.value:.3f}" if r.value is not None else "-"
            baseline = f"{r.baseline_rules:.3f}" if r.baseline_rules is not None else "-"
            ci = f"[{r.ci95[0]:.3f}, {r.ci95[1]:.3f}]" if r.ci95 is not None else "-"
            lines.append(f"| {r.id} | {value} | {baseline} | {r.n} | {ci} |")
        lines.append("")
        for r in self.metrics:
            lines.append(f"## {r.id}")
            if r.note:
                lines.append(f"_{r.note}_")
                lines.append("")
            if r.worst_cases:
                lines.append("Peores casos:")
                for w in r.worst_cases:
                    trace = f" (trace_id=`{w.trace_id}`)" if w.trace_id else ""
                    lines.append(f"- `{w.case_id}`{trace}: {w.detail}")
            else:
                lines.append("Sin casos fallidos.")
            lines.append("")
        return "\n".join(lines)

    def write(self, out_dir: str | Path) -> list[Path]:
        """Escribe `report.json` + `report.md` en `out_dir` (ADR secc. 4,
        literal). Devuelve `[json_path, md_path]`."""
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        json_path = d / JSON_NAME
        md_path = d / MD_NAME
        json_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        return [json_path, md_path]


def load_report_dict(report_dir: str | Path) -> dict[str, Any]:
    path = Path(report_dir) / JSON_NAME
    return json.loads(path.read_text(encoding="utf-8"))


#: Sin IC (metricas mecanicas sin bootstrap, p.ej. `authority_violation`):
#: una diferencia mayor a esta se marca "difiere" igual (ADR secc. 7 punto
#: 7: "marca diferencias fuera del IC" -- sin IC, se usa este margen fijo en
#: su lugar, documentado en Notas de implementacion).
_NO_CI_MARGIN = 0.05


def compare_reports(a_dir: str | Path, b_dir: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    """`(table_rows, differing_metric_ids)` para `republica eval compare`
    (ADR secc. 4/7 punto 7): "imprime la tabla y marca diferencias fuera del
    IC". Compara metrica por `id`; una que falta en alguno de los dos
    reportes se muestra igual, con `"-"` del lado que falta, y no cuenta
    como "difiere" (no hay con que comparar)."""
    a = load_report_dict(a_dir)
    b = load_report_dict(b_dir)
    by_id_a = {r["id"]: r for r in a["metrics"]}
    by_id_b = {r["id"]: r for r in b["metrics"]}
    ids = sorted(set(by_id_a) | set(by_id_b))

    rows: list[dict[str, Any]] = []
    differing: list[str] = []
    for metric_id in ids:
        ra = by_id_a.get(metric_id)
        rb = by_id_b.get(metric_id)
        va = ra["value"] if ra else None
        vb = rb["value"] if rb else None
        ci_a = ra.get("ci95") if ra else None
        ci_b = rb.get("ci95") if rb else None
        differs = False
        if va is not None and vb is not None:
            if ci_a is not None and not (ci_a[0] <= vb <= ci_a[1]):
                differs = True
            elif ci_b is not None and not (ci_b[0] <= va <= ci_b[1]):
                differs = True
            elif ci_a is None and ci_b is None and abs(va - vb) > _NO_CI_MARGIN:
                differs = True
        rows.append(
            {
                "metric": metric_id,
                "a": va,
                "b": vb,
                "ci_a": f"[{ci_a[0]:.3f}, {ci_a[1]:.3f}]" if ci_a else "-",
                "ci_b": f"[{ci_b[0]:.3f}, {ci_b[1]:.3f}]" if ci_b else "-",
                "differs": differs,
            }
        )
        if differs:
            differing.append(metric_id)
    return rows, differing
