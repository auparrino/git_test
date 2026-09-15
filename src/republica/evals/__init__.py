"""Evals de agentes (ADR 007, Fase 7): mide al AGENTE (`ai/brains.py::
build_decision_actor`), no al prompt ni al motor.

- `evals/cases.py`: casos con resultado esperado (`data/evals/cases/
  {ideological,interest}/*.yaml`, ADR secc. 2).
- `evals/metrics.py`: las 10 metricas de la suite (ADR secc. 2) +
  `bootstrap_ci`.
- `evals/judge.py`: `FakeJudge` (reglas de strings/numeros, sin red) y
  `Judge(backend)` (cualquier `LLMBackend` real), con salida siempre por
  `FactCheck`/`RubricScore` (ADR secc. 3).
- `evals/synthetic.py`: corridas sinteticas chicas para las metricas que
  necesitan una corrida (no un caso aislado).
- `evals/runner.py`: `run_suite()`, el punto de entrada de `republica eval`.
- `evals/report.py`: `Report` (`report.json`/`report.md`) y
  `compare_reports()`.
- `evals/promptfoo.py`: `export_promptfoo()` (`republica eval
  export-promptfoo`).

Todo corre offline por default (`--brain rules|fake:*`, `--judge fake`); un
`--brain llm:*`/`--judge llm:*` real necesita Ollama corriendo (no
disponible en este entorno, ver `docs/OLLAMA_SETUP.md`).
"""
