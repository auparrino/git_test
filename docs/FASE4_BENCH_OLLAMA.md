# Fase 4 — `bench-parse` con Ollama local, por rol

**Estado: NO EJECUTADO.** En el entorno donde se intentó (contenedor remoto, 4 vCPU sin GPU, Ollama
v0.12.0 levantado) no se pudo bajar ningún modelo: `registry.ollama.ai`, Hugging Face, ModelScope y
los blobs de Docker Hub/ghcr están bloqueados por la política de red. El detalle de lo intentado está
en `docs/FASE4_RESULTS_OLLAMA.md`, sección "Entorno y bloqueo". Este archivo queda como plantilla
con los comandos exactos y el formato de la tabla; **no contiene ningún número de un LLM**.

## Cómo generarlo

```bash
ollama pull qwen3:8b                      # o qwen3:4b; anotar cuál
uv sync --all-extras
STEPS=bench MODEL=qwen3:8b ./scripts/fase4_ollama.sh
# equivale a, para cada rol:
uv run republica bench-parse --brain llm:ollama:qwen3:8b --n 50 --role governor --seed 7
uv run republica bench-parse --brain llm:ollama:qwen3:8b --n 50 --role president --seed 7
uv run republica bench-parse --brain llm:ollama:qwen3:8b --n 50 --role union --seed 7
uv run republica bench-parse --brain llm:ollama:qwen3:8b --n 50 --role media --seed 7
```

Salidas en `simulations/fase4_logs/bench_<rol>.txt`. `bench-parse` corre 50 meses reales de Aurora
con todos los actores por reglas salvo el primer actor (orden alfabético de id) del rol pedido, que
usa el LLM (ADR 004 secc. 10 punto 21); por eso `n=50` son 50 llamadas por rol y el actor medido es
`gov_capital`, `president`, `union_cgt` y `media_mercado` respectivamente.

## Modelo y máquina

| | |
|---|---|
| modelo (`ollama show`) | pendiente |
| máquina (CPU/GPU/RAM) | pendiente |
| `OllamaBackend` | timeout 60 s, `num_predict` 800, reintento ×2 en error de parseo (ADR 004 secc. 2) |

## Métricas por rol (n = 50, seed 7)

| rol (actor) | parse_rate (JSON válido) | authority_violation_rate (fuera de rol / emitidas) | latencia p50 / p90 (ms) | tokens prompt / completion (media) | tiempo total |
|---|---:|---:|---:|---:|---:|
| governor (`gov_capital`) | pendiente | pendiente | pendiente | pendiente | pendiente |
| president (`president`) | pendiente | pendiente | pendiente | pendiente | pendiente |
| union (`union_cgt`) | pendiente | pendiente | pendiente | pendiente | pendiente |
| media (`media_mercado`) | pendiente | pendiente | pendiente | pendiente | pendiente |

Umbral de Fase 4 (ADR 004 secc. 8): `parse_rate >= 0.95` en cada rol. `bench-parse` imprime
`OK`/`AVISO` según el umbral. `parse_rate` cuenta la traza como válida si el JSON final (tras hasta 2
reintentos) parsea y valida contra `ActorDecision`; `authority_violation_rate` cuenta acciones
denegadas con motivo "no tiene permitido" sobre el total emitido por el actor.

Nota sobre la tasa de acciones autorizadas: `bench-parse` reporta la tasa de *violaciones de rol*, no
la tasa de autorizadas. La complementaria (autorizadas / emitidas, que además descuenta cooldowns,
presupuesto por turno y `invalid_params`) sale de las trazas de la corrida completa con
`scripts/fase4_compare_runs.py` (sección "Acciones denegadas por `authorize()`").

## Ejemplos de fallos

Pendiente. Fuente: trazas con `parse_error != null` en la corrida de `bench-parse` (el comando no
las guarda; para verlas, correr en su lugar
`uv run republica run --seed 7 --months 50 --brains <yaml con solo ese actor en llm:...> --out simulations/bench_<rol>.jsonl`
y pasar el JSONL por `scripts/fase4_compare_runs.py`, que lista hasta 5 fallos con `raw_response`
recortado).

Tipos de fallo a distinguir al completarlo:

- JSON roto (no parsea): `parse_error` con `JSONDecodeError`; `attempts` = 3.
- JSON válido pero fuera de esquema (`ActorDecision` rechaza: `intensity` > 1, `position` fuera del
  `Literal`, `public_message` > 280): `parse_error` con `ValidationError`.
- JSON válido, decisión fuera de rol (`STRIKE` de un gobernador): **no** es fallo de parseo; se
  cuenta en `authority_violation_rate` y aparece en `actions_denied`.

## Verificación del comando sin LLM

`uv run republica bench-parse --brain fake:rules --n 3 --role governor --seed 7` corre de punta a
punta en este entorno (`parse_rate` 1.00, 0 violaciones, ~316 tokens de prompt): el comando y la
tubería están bien; lo que falta es el modelo.
