"""`python -m republica.probe ...` (ADR 020 secc. 5).

Mismo comando que `republica probe` (ver `cli.py`, que delega aca), para
poder correr la sonda sin la CLI completa:

    python -m republica.probe \\
        --country argentina --calibration a7_by_regime \\
        --seeds 10 --run-id <run_id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from republica.probe.report import write_report
from republica.probe.runner import run_probe, scenarios_path
from republica.world.config import DEFAULT_DATA_DIR


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m republica.probe",
        description="Sonda exploratoria del modelo (ADR 020): NO es un backtest ni una "
        "validacion -- no puntua nada, describe el comportamiento del modelo.",
    )
    p.add_argument("--country", default="argentina", help="Paquete de pais.")
    p.add_argument(
        "--calibration",
        default=None,
        dest="calibration_run_id",
        help="run_id de `republica calibrate` (sin esto: coeficientes del paquete).",
    )
    p.add_argument("--seeds", type=int, default=10, help="Semillas por escenario (default 10).")
    p.add_argument("--seed-base", type=int, default=1, dest="seed_base", help="Primera semilla.")
    p.add_argument("--run-id", required=True, dest="run_id", help="Nombre de la corrida.")
    p.add_argument(
        "--scenarios",
        type=Path,
        default=None,
        help="CSV de escenarios (default `data/countries/<pais>/probe_scenarios.csv`).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Directorio de salida (default `data/countries/<pais>/probe/<run-id>/`).",
    )
    p.add_argument(
        "--regime-transitions",
        dest="regime_transitions",
        action="store_true",
        default=False,
        help="Transiciones de regimen endogenas (ADR 015).",
    )
    p.add_argument(
        "--no-regime-transitions",
        dest="regime_transitions",
        action="store_false",
        help="Apaga ADR 015 (default).",
    )
    p.add_argument(
        "--no-series",
        dest="write_series",
        action="store_false",
        default=True,
        help="No escribe el CSV por semilla-escenario.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = args.out or (DEFAULT_DATA_DIR / "countries" / args.country / "probe" / args.run_id)
    scen_file = args.scenarios or scenarios_path(args.country)

    print(
        f"Sonda exploratoria (ADR 020) {args.country} run_id={args.run_id} "
        f"calibracion={args.calibration_run_id or 'paquete'} seeds={args.seeds} "
        f"escenarios={scen_file} -> {out_dir}"
    )
    try:
        payload = run_probe(
            out_dir,
            country_id=args.country,
            calibration_run_id=args.calibration_run_id,
            seeds=args.seeds,
            seed_base=args.seed_base,
            scenarios_file=scen_file,
            regime_transitions=args.regime_transitions,
            write_series=args.write_series,
            progress=lambda msg: print(f"  {msg}", flush=True),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    report_path = write_report(out_dir, payload)
    failed = [s["label"] for s in payload["scenarios"] if s["error"]]
    if failed:
        print(f"Escenarios con ERROR (no tumbaron la corrida): {failed}")
    print(f"OK ({payload['wall_seconds']:.1f}s) -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
