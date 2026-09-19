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

## Cuánto tarda (y por qué parece colgado)

Cada decisión de un actor es una llamada al modelo con un prompt de 700–800 tokens. En CPU sin
placa de video, un modelo de 8 mil millones de parámetros tarda del orden de **30 a 90 segundos por
llamada**, y la primera suma la carga de 5 GB a memoria. `bench-parse --n 50` son 50 llamadas: una
hora larga por rol, cuatro roles.

Desde la versión con progreso, cada llamada imprime una línea a stderr con su latencia y el
acumulado, así que se ve que avanza (`REPUBLICA_OLLAMA_PROGRESS=0` lo apaga). Si no aparece ninguna
línea en varios minutos, recién ahí hay algo mal.

**Para una primera pasada, no corras el plan completo.** Empezá chico y medí tu máquina:

```powershell
.\scripts\fase4_ollama.ps1 -Steps bench -NBench 5
```

Cinco llamadas por rol alcanzan para saber si el modelo respeta el esquema JSON, que es lo único
que decide si tiene sentido seguir. Con la latencia media que imprime, multiplicá para estimar el
plan completo antes de lanzarlo.

Si da demasiado lento:

- `-Model qwen3:4b` es del orden de tres veces más rápido y suele alcanzar para el parseo.
- Una placa de video cambia el orden de magnitud: de minutos a segundos por llamada.
- Las dos corridas de 48 meses (`-Steps aurora,argentina`) son cientos de llamadas cada una. Con
  CPU sola, conviene bajarlas con `-Months 12` y decirlo al reportar los números.

## Si algo falla

`republica` traduce un Ollama inalcanzable a un mensaje con los cuatro chequeos a hacer, en vez de
un traceback. Si aun así el error no se entiende, corré el paso suelto para ver la salida completa:

```powershell
uv run republica bench-parse --brain llm:ollama:qwen3:8b --n 2 --role governor --seed 7
```

Causas habituales, en orden de frecuencia:

| Síntoma | Causa | Qué hacer |
|---|---|---|
| "Connection refused" | El servicio no está levantado | `ollama list` en otra terminal; si falla, abrí la app de Ollama o corré `ollama serve` |
| "Connection refused" con el servicio andando | Escucha en otra dirección | `$env:OLLAMA_HOST = "http://127.0.0.1:11434"` antes de correr |
| "timed out" | Modelo grande en CPU | `.\scripts\fase4_ollama.ps1 -TimeoutSeconds 300`, o usá `qwen3:4b` |
| `parse_rate` por debajo de 0.95 | El modelo no respeta el esquema JSON | Probá un modelo más grande, o subí `num_predict` en `ai/backends.py` |

En Windows, el script no corta el script ante cualquier línea de stderr: los fallos reales se
detectan por el código de salida y te dicen en qué archivo quedó la salida completa.

