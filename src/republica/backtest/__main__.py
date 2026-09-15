"""`python -m republica.backtest ...` (ADR 014 secc. 5): CLI standalone,
NO un subcomando de `republica` (`cli.py` no se toca en esta tarea -- ver
`docs/ADR_014_rolling_backtest.md`, "Notas de implementación", para la
línea exacta que falta agregar ahí).

    python -m republica.backtest \\
        --country argentina --calibration <run_id> \\
        --from 1916 --to 2022 --horizons 12,24,48 \\
        --seeds 30 --workers 4 --run-id <run_id> [--resume]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from republica.backtest.report import write_report
from republica.backtest.runner import run_backtest
from republica.backtest.windows import DEFAULT_HORIZONS, FIRST_ORIGIN_YEAR, LAST_ORIGIN_YEAR
from republica.world.config import DEFAULT_DATA_DIR


def _parse_horizons(spec: str) -> tuple[int, ...]:
    return tuple(int(x) for x in spec.split(",") if x.strip())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m republica.backtest",
        description="Backtest secuencial 1916-2023 y análisis de predictibilidad (ADR 014).",
    )
    p.add_argument("--country", default="argentina", help="Paquete de país (hoy solo 'argentina').")
    p.add_argument(
        "--calibration",
        required=True,
        dest="calibration_run_id",
        help="run_id de `republica calibrate`.",
    )
    p.add_argument(
        "--from", type=int, default=FIRST_ORIGIN_YEAR, dest="from_year", help="Primer año de t0."
    )
    p.add_argument(
        "--to", type=int, default=LAST_ORIGIN_YEAR, dest="to_year", help="Último año de t0."
    )
    p.add_argument(
        "--horizons",
        type=_parse_horizons,
        default=DEFAULT_HORIZONS,
        help="Horizontes en meses, separados por coma (default 12,24,48).",
    )
    p.add_argument(
        "--seeds", type=int, default=30, help="Semillas por ventana y brazo (default 30)."
    )
    p.add_argument("--workers", type=int, default=4, help="Procesos en paralelo (default 4).")
    p.add_argument("--seed-base", type=int, default=1, dest="seed_base", help="Primera semilla.")
    p.add_argument("--run-id", required=True, dest="run_id", help="Nombre de la corrida de salida.")
    p.add_argument(
        "--resume", action="store_true", help="Retoma desde `checkpoint.json` si existe."
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Directorio de salida (default `data/countries/<country>/backtest/<run-id>/`).",
    )
    p.add_argument(
        "--no-plots", action="store_true", help="No genera `plots/` (mas rapido, sin `analysis`)."
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.country != "argentina":
        print(f"Solo 'argentina' esta soportado (se pidio {args.country!r}).", file=sys.stderr)
        return 2

    out_dir = args.out or (DEFAULT_DATA_DIR / "countries" / args.country / "backtest" / args.run_id)

    n_windows = (args.to_year - args.from_year + 1) * len(args.horizons)
    print(
        f"Backtest {args.country} run_id={args.run_id} calibracion={args.calibration_run_id} "
        f"t0={args.from_year}..{args.to_year} horizontes={list(args.horizons)} "
        f"({n_windows} ventanas) seeds={args.seeds} workers={args.workers} -> {out_dir}"
    )

    t0 = time.perf_counter()
    windows_csv = run_backtest(
        out_dir,
        calibration_run_id=args.calibration_run_id,
        from_year=args.from_year,
        to_year=args.to_year,
        horizons=args.horizons,
        seeds=args.seeds,
        workers=args.workers,
        seed_base=args.seed_base,
        resume=args.resume,
        progress=print,
    )
    wall = time.perf_counter() - t0

    report_path = write_report(
        out_dir,
        windows_csv,
        args.calibration_run_id,
        from_year=args.from_year,
        to_year=args.to_year,
        horizons=args.horizons,
        seeds=args.seeds,
        wall_seconds=wall,
        make_plots=not args.no_plots,
    )
    print(f"OK: {windows_csv} ({wall:.1f}s) -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
