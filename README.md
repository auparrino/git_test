# República Artificial

Laboratorio político jugable y framework de experimentación con agentes IA.

Un país ficticio (la República de Aurora) donde **Python decide qué pasa en el mundo** y **la IA decide qué quieren hacer los actores**, sin que la IA pueda tocar el estado directamente. Se puede jugar como presidente, observar cómo actúan todos los agentes, o lanzar cientos de simulaciones automáticas y analizar por qué algunos gobiernos sobreviven y otros colapsan.

Objetivo final: un sistema computacional para explorar y evaluar instituciones políticas, con acciones restringidas, permisos, memoria, observabilidad y evals sistemáticos.

## Estado

| Hito | Qué hay | Estado |
|---|---|---|
| v0.1 | Mundo determinista de 48 meses: 20 variables, 12 shocks, tres reglas de política, `run`/`narrate`/`batch`, 24 tests de aceptación | ✅ |
| v0.2 | Modo juego: `play` con tablero, 14 dilemas disparados por estado, consejero por reglas, guardado, contrafáctico | ✅ |
| v0.3 | 29 actores con fichas (ideología ≠ intereses ≠ personalidad), catálogo cerrado de acciones, permisos por rol, consecuencias | 🔨 |
| v0.3 | Capa de IA: esquemas JSON, prompts por rol, cliente Ollama, backend falso para CI | diseño listo (ADR 004) |
| v0.5 | Congreso, negociación, cohortes, medios y percepción; memoria y elecciones | diseño listo (ADR 005, 006) |
| v0.8 | Evals, trazas, gobernanza; experimentos en lote con DuckDB | diseño listo (ADR 007, 008) |

Plan completo, criterios de "listo" y modelo a usar en cada etapa: [`docs/PLAN.md`](docs/PLAN.md).
Checklist operativa: [`docs/PASO_A_PASO.md`](docs/PASO_A_PASO.md). Especificación del mundo:
[`docs/SPEC_v0.1.md`](docs/SPEC_v0.1.md). Calibración y sus razones: [`docs/CALIBRATION_LOG.md`](docs/CALIBRATION_LOG.md).

## Probarlo

```bash
uv sync --group dev
uv run republica run --seed 7 --out simulations/run_7.jsonl   # simula 48 meses
uv run republica narrate simulations/run_7.jsonl               # la historia, mes a mes
uv run republica batch --seeds 300 --policy passive            # distribución de outcomes
uv run republica play --seed 7                                 # vos sos el presidente
uv run pytest -q
```

Orden de construcción:

```
Mundo → reglas → decisiones humanas → actores simples → IA → memoria → interacción → evals → autonomía
```

## Principios

- **Mundo determinista.** Misma semilla, misma historia.
- **La IA propone, el motor dispone.** Los actores devuelven JSON validado; el motor chequea permisos y aplica reglas.
- **Catálogo cerrado de acciones por rol.** Todo lo que está fuera de catálogo se rechaza y se registra.
- **Realidad ≠ percepción.** Los medios mueven la percepción, no el PIB.
- **Baseline siempre.** Cada actor IA tiene un gemelo por reglas contra el que se mide.
- **Todo queda registrado.** Cada decisión es una traza reconstruible.

## Stack previsto

Python 3.12 · uv · pydantic · typer · pytest · DuckDB · Ollama · Promptfoo · Langfuse · Streamlit
