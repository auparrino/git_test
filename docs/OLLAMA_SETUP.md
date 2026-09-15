# Ollama local (Fase 4, ADR 004)

1. Instalá Ollama (https://ollama.com) y arrancá el servicio (`ollama serve`, o el instalador ya lo
   deja corriendo como servicio).
2. Bajá un modelo que soporte `format=<json schema>` (salida JSON estructurada): `ollama pull qwen3:8b`.
3. Probá el pipeline completo sin correr una simulación entera:
   `republica bench-parse --brain llm:ollama:qwen3:8b --n 50 --role governor --seed 7`.
   Mide `parse_rate`, `authority_violation_rate`, latencia p50/p90 y tokens sobre 50 percepciones
   reales de un gobernador. Umbral de Fase 4: `parse_rate >= 0.95`; si da menos, el modelo no está
   respetando el JSON Schema (probá con `num_predict` más alto en `ai/backends.py::OllamaBackend` o un
   modelo más grande).
4. Para correr una simulación completa con IA: `data/brains.yaml` (default `rules`) o
   `republica run --seed 7 --brain llm:ollama:qwen3:8b --out simulations/run_llm.jsonl` (todos los
   actores) / `--brains data/brains.yaml` (mezcla, editá `actors:` en el YAML).
5. Si Ollama corre en otro host/puerto, seteá `OLLAMA_HOST` (ej. `export OLLAMA_HOST=http://gpu-box:11434`)
   antes de correr `republica`: `OllamaBackend` lo lee del entorno si no le pasás `host=` a mano.
6. Sin Ollama a mano (como en este entorno de desarrollo): usá `--brain fake:rules` (misma tubería
   completa, cero LLM) para todo lo demás.
7. Todo el plan de Fase 4 de una vez (bench por rol, Aurora y Argentina 2019-12 con LLM y por reglas,
   evals, comparación de trazas): `MODEL=qwen3:8b ./scripts/fase4_ollama.sh`; salidas en
   `simulations/fase4_logs/`, tablas para `docs/FASE4_BENCH_OLLAMA.md` y `docs/FASE4_RESULTS_OLLAMA.md`.
