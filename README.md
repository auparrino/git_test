# República Artificial

Laboratorio político jugable y framework de experimentación con agentes IA.

Un país ficticio (la República de Aurora) donde **Python decide qué pasa en el mundo** y **la IA decide qué quieren hacer los actores**, sin que la IA pueda tocar el estado directamente. Se puede jugar como presidente, observar cómo actúan todos los agentes, o lanzar cientos de simulaciones automáticas y analizar por qué algunos gobiernos sobreviven y otros colapsan.

Objetivo final: un sistema computacional para explorar y evaluar instituciones políticas, con acciones restringidas, permisos, memoria, observabilidad y evals sistemáticos.

## Estado

Fase de planificación. El plan de construcción por fases, con criterios de "listo" y el modelo a usar en cada etapa, está en [`docs/PLAN.md`](docs/PLAN.md).

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
