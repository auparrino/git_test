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
   El último paso del script (`collect`) corre `scripts/fase4_collect_results.py`, que junta todos los
   logs en `simulations/fase4_logs/RESULTADOS.md` con las tablas en el orden de esos dos documentos:
   lo que hay que hacer después es pegar ese archivo (o sus secciones) en los docs y commitear.
   El script elige solo la mejor calibración disponible de `data/countries/argentina/calibration/`
   (`CALIBRATION=<run_id>` la fuerza).
8. Timeout por decisión: `OllamaBackend` usa 60 s (ADR 004). Si el modelo corre en CPU y aparecen
   `URLError`/timeout, `REPUBLICA_OLLAMA_TIMEOUT=180` (segundos) lo sube sin tocar código; el script
   de Fase 4 ya exporta 120 por default.
9. **Windows**: hay un puerto del script a PowerShell, `scripts/fase4_ollama.ps1`, con los mismos
   pasos, los mismos archivos de salida y el mismo formato de tiempos que lee el recolector. Desde
   la carpeta del repo:

   ```powershell
   git clone https://github.com/auparrino/git_test.git
   cd git_test
   git checkout claude/relaxed-volta-sclqi6
   uv sync --all-extras
   .\scripts\fase4_ollama.ps1
   ```

   Si PowerShell bloquea la ejecución ("no se puede cargar porque la ejecución de scripts está
   deshabilitada"), corré antes `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`: vale
   solo para esa ventana. Parámetros: `-Model qwen3:4b`, `-Steps bench`, `-TimeoutSeconds 180`,
   `-Calibration <run_id>`. Nota de sintaxis: `MODEL=qwen3:8b ./script.sh` es bash y **no** funciona
   en PowerShell; ahí las variables van como parámetros (`-Model qwen3:8b`).

   La alternativa es correr el `.sh` desde WSL o Git Bash, con Ollama nativo de Windows: desde WSL2
   se ve en `localhost:11434` solo si Ollama escucha en `0.0.0.0` (`setx OLLAMA_HOST 0.0.0.0` en
   Windows y reiniciar el servicio), y conviene exportar `OLLAMA_HOST` antes de correr.
