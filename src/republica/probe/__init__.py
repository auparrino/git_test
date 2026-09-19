"""Sonda exploratoria del modelo (ADR 020): `republica probe`.

Tercera herramienta de medicion, distinta del backtest (ADR 014) y de la
validacion historica (ADR 011 secc. 8):

- el backtest PUNTUA objetivos contra series reales en ventanas rodantes;
- la validacion PUNTUA cuatro hipotesis REGISTRADAS ANTES de correr;
- la sonda NO PUNTUA NADA: corre unos pocos arranques historicos con muchas
  semillas y describe el COMPORTAMIENTO del modelo, sin hipotesis previa,
  buscando sintomas de que algo esta mal mecanicamente (terminacion
  temprana, saturacion de variables contra su cota, valores fuera de rango
  fisico, excepciones).

Ver `docs/ADR_020_exploratory_probe.md` secc. 3 para la lista explicita de
lo que la sonda NO mide.

Ejecutable como `republica probe ...` (ver `cli.py`) o como
`python -m republica.probe ...` (ver `__main__.py`).
"""

from republica.probe.runner import (
    PHYSICAL_RANGES,
    ProbeScenario,
    ScenarioResult,
    SeedProbe,
    detect_physical_violations,
    detect_saturation,
    load_scenarios,
    run_probe,
    scenarios_path,
)

__all__ = [
    "PHYSICAL_RANGES",
    "ProbeScenario",
    "ScenarioResult",
    "SeedProbe",
    "detect_physical_violations",
    "detect_saturation",
    "load_scenarios",
    "run_probe",
    "scenarios_path",
]
