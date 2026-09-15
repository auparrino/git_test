# República Artificial — Plan de construcción

> Laboratorio político jugable y framework de experimentación con agentes IA.
> Python decide qué pasa en el mundo. La IA decide qué quieren hacer los actores.
> La IA nunca modifica directamente el estado del mundo.

Este documento fija **el orden de construcción**, **qué se entrega en cada fase**,
**cuándo una fase está terminada** y **qué modelo usar en cada etapa**, en dos sentidos:

1. **Modelo de Claude Code** para *construir* cada fase (Fable 5.1, Opus 5, Sonnet 5, Haiku 4.5).
2. **Modelo en runtime** que corre *dentro* de la simulación (reglas sin LLM, Ollama local, API cuando hace falta).

---

## 0. Principios que no se negocian

| Principio | Qué significa en código |
|---|---|
| **Mundo determinista** | `world.advance_month()` es una función pura de `(state, actions, shocks, seed)`. Misma semilla, misma historia. |
| **La IA propone, el motor dispone** | Un actor devuelve un JSON validado contra un esquema. El motor chequea permisos, aplica reglas y recién ahí muta el estado. |
| **Catálogo cerrado de acciones** | Cada rol tiene una lista de acciones permitidas. Cualquier acción fuera de catálogo se rechaza y se registra como *authority violation*. |
| **Realidad ≠ percepción** | Los indicadores reales y los percibidos son variables distintas. Los medios tocan percepción, nunca el PIB. |
| **Baseline siempre** | Todo actor IA tiene un gemelo por reglas. Sin baseline no hay eval. |
| **Todo queda registrado** | Cada turno, decisión, prompt, respuesta, chequeo de permisos y consecuencia se persiste (JSONL primero, DuckDB después). |
| **Pocas variables bien conectadas** | ~20 variables de estado en v0.1. No se agrega una variable sin una fórmula que la conecte a otras dos. |
| **Physics vs. Institutions** | Lo que no cambia dentro de una corrida (agentes, recursos, información, acciones primitivas) es *physics*. Todo lo demás debe poder emerger o evolucionar (v2). |

Orden de construcción, sin saltos:

```
Mundo → reglas → decisiones humanas → actores simples → IA → memoria → interacción → evals → autonomía
```

---

## 1. Stack técnico

| Capa | Elección | Por qué |
|---|---|---|
| Lenguaje | Python 3.12, `uv`, `pyproject.toml` | Simple, rápido de instalar, un solo lockfile |
| Modelos de datos | `pydantic` v2 | Validación de estado y de salidas JSON del LLM con el mismo mecanismo |
| CLI / juego | `typer` + `rich` | Interfaz de texto del presidente sin tocar UI web |
| Tests | `pytest` + `hypothesis` | Tests de propiedades sobre el motor (no explota, acotado, determinista) |
| Calidad | `ruff` (lint + format), `mypy` opcional | Un solo tool |
| Persistencia | JSONL por corrida → DuckDB para análisis | Cero infraestructura, SQL local |
| LLM local | Ollama (structured outputs / JSON schema, tool calling) | Sin costo por token |
| Evals | evals propios (`src/evals/`) + Promptfoo para comparar prompts/modelos | Promptfoo corre local |
| Observabilidad | Langfuse self-hosted (Docker Compose) | Trazas por decisión |
| UI | Streamlit (v0.5+) | Tablero rápido; la UI "final" viene después |
| ABM avanzado | Mesa (solo si hace falta en v2) | No antes |

Estructura de carpetas objetivo (se crea en Fase 0, se llena por fases):

```
republica-artificial/
├── README.md
├── pyproject.toml
├── docs/                 # PLAN.md, SPEC_v0.1.md, ADRs
├── src/republica/
│   ├── world/            # state.py, economy.py, politics.py, society.py, events.py
│   ├── actors/           # actor.py, sheets (YAML), rule_based.py, llm_based.py
│   ├── engine/           # simulation.py, actions.py, permissions.py, consequences.py, scheduler.py
│   ├── ai/               # ollama_client.py, prompts.py, schemas.py, memory.py
│   ├── evals/
│   ├── governance/
│   ├── experiments/
│   └── ui/
├── data/                 # country.json, provinces.csv, parties.json, actors/, scenarios/
├── simulations/          # salidas (gitignored salvo ejemplos)
├── tests/
└── notebooks/
```

---

## 2. Roadmap por fases

Cada fase tiene: objetivo, entregables, *definition of done* (DoD), modelo de Claude Code, modelo en runtime.
El esfuerzo está en "sesiones" de trabajo enfocado (~2–4 h con Claude Code), como orden de magnitud.

### Fase 0 — Scaffold del repo (1 sesión)

**Objetivo.** Que `uv run pytest` y `uv run republica --help` funcionen desde el primer commit.

**Entregables**
- `pyproject.toml`, `uv.lock`, `ruff.toml`, `.gitignore`, `.pre-commit-config.yaml`.
- Estructura de carpetas vacía con `__init__.py`.
- CI mínima (GitHub Actions: ruff + pytest).
- `docs/SPEC_v0.1.md` vacío con secciones a completar en Fase 1.

**DoD.** CI verde en un commit con un test trivial.

**Modelo Claude Code.** Sonnet 5 (Haiku 4.5 sirve igual: es mecánico).
**Runtime.** —

---

### Fase 1 — v0.1: el mundo sin IA (4–6 sesiones)

**Objetivo.** La República de Aurora simula 48 meses y produce una historia económica y política *internamente coherente*, sin un solo LLM.

**Entregables**
1. `docs/SPEC_v0.1.md` completa: variables, rangos, fórmulas, datos iniciales, shocks, reglas de transición.
2. `world/state.py`: modelo pydantic del estado (~20 variables).
3. `world/economy.py`, `politics.py`, `society.py`: transiciones mensuales.
4. `world/events.py`: catálogo de shocks con probabilidad y efectos objetivos.
5. `engine/simulation.py`: `run(seed, months=48, policy=None) -> History`.
6. `data/country.json`, `provinces.csv`, `parties.json`.
7. CLI: `republica run --seed 7 --months 48 --out simulations/run_7.jsonl`.
8. Tests de propiedades: determinismo, cotas (inflación no negativa, aprobación en [0, 100]), sin NaN, sin explosión numérica en 1.000 semillas.

**Variables de estado v0.1**

| Bloque | Variables |
|---|---|
| Economía | `gdp`, `gdp_growth`, `inflation`, `unemployment`, `real_wage`, `interest_rate`, `exchange_rate`, `reserves`, `public_debt`, `fiscal_balance`, `poverty` |
| Política | `government_approval`, `congress_support`, `political_stability`, `social_tension`, `institutional_confidence` |
| Sociedad | `consumer_confidence`, `protest_level`, `inequality`, `crime_perception` |

Las fórmulas son de la forma "inercia + presiones − amortiguadores", con coeficientes en `data/country.json` para poder calibrarlos sin tocar código:

```
inflation[t+1] = a·inflation[t] + b·Δexchange_rate + c·demand_gap − d·(interest_rate − inflation) + shock
approval[t+1]  = approval[t] + e·Δreal_wage − f·Δunemployment − g·Δperceived_inflation + events
```

**Shocks iniciales (12):** sequía, boom de commodities, escándalo de corrupción, huelga, crisis internacional, inundación, descubrimiento energético, epidemia, crisis bancaria, protestas, crecimiento inesperado, caída de un socio comercial. Cada uno con efectos numéricos objetivos y duración.

**DoD.**
- 100 corridas con semillas distintas producen trayectorias distintas, acotadas y sin NaN.
- Un shock de sequía en el mes 5 se ve en reservas y en aprobación en los meses 6–9.
- Un revisor humano lee la historia de una corrida (`republica narrate run_7.jsonl`) y no encuentra incoherencias evidentes.

**Modelo Claude Code.**
- Diseño de fórmulas, estabilidad numérica, calibración de coeficientes: **Fable 5.1** (o Opus 5). Es la parte donde un error de diseño se paga durante todo el proyecto.
- Implementación de módulos, CLI y tests: **Sonnet 5**.
- Datos iniciales (CSV/JSON de provincias, partidos): **Haiku 4.5**.

**Runtime.** Ninguno. Reglas puras.

---

### Fase 2 — El primer juego: vos sos el presidente (2 sesiones)

**Objetivo.** Que ya sea divertido sin IA.

**Entregables**
- `engine/actions.py`: catálogo inicial de decisiones del presidente (tasa, gasto, impuestos, transferencias, tipo de cambio, negociar/no negociar).
- Loop interactivo: `republica play --seed 7`. Cada mes muestra indicadores, 1–3 situaciones y opciones A/B/C.
- Un "consejero" por reglas (Banco Central recomienda, Ministro advierte) para que el jugador tenga información.
- Guardado de partida y resumen final (¿sobrevivió el gobierno? ¿por qué?).

**DoD.** Tres partidas completas jugadas por una persona. Cada decisión tiene consecuencias visibles en los 3 meses siguientes.

**Modelo Claude Code.** Sonnet 5. Diseño de las situaciones/dilemas: Opus 5 si querés que sean buenos.
**Runtime.** Ninguno.

---

### Fase 3 — Actores por reglas + permisos (3–4 sesiones)

**Objetivo.** Existen todos los actores, deciden por scoring, y el motor ya tiene la capa de permisos que después va a gobernar a la IA.

**Entregables**
- Fichas YAML en `data/actors/`: ideología, personalidad, intereses, relaciones (presidente, ministro, BCRA, 8 gobernadores, 5 partidos, 2 sindicatos, 3 sectores, 3 medios, 5 bloques sociales).
- `actors/rule_based.py`: decisión por suma ponderada (compatibilidad ideológica + beneficio propio + relación + presión electoral → SUPPORT/OPPOSE/NEGOTIATE…).
- `engine/permissions.py`: catálogo cerrado de acciones **por rol**; toda acción pasa por `authorize(actor, action) -> Allowed | Denied(reason)`.
- `engine/consequences.py`: efecto de cada acción sobre el estado y sobre relaciones.
- `scheduler.py`: orden de turno (shocks → actores → presidente → resolución → transiciones).
- Log JSONL por turno con acciones propuestas, autorizadas y rechazadas.

**DoD.**
- Una reforma que perjudica a una provincia hace que su gobernador se oponga aunque comparta ideología.
- Un intento de que un medio "suba tasas" es rechazado y registrado.
- Tests: cada rol tiene ≥1 test de acción permitida y ≥1 de acción prohibida.

**Modelo Claude Code.**
- Diseño del esquema de acciones/permisos y del scoring: **Opus 5** (es la "constitución" del sistema).
- Implementación y tests: **Sonnet 5**.
- Fichas YAML de 25 actores: **Haiku 4.5** con revisión.

**Runtime.** Reglas. Este es el **baseline** contra el que se mide todo lo que sigue.

---

### Fase 4 — Primeros tres agentes con Ollama (3–4 sesiones)

**Objetivo.** Presidente, Ministro de Economía y un Gobernador opositor deciden con un LLM local, con salida JSON validada, sin tocar el estado.

**Entregables**
- `ai/ollama_client.py`: cliente con `format=<json schema>`, reintentos, timeout, cache por hash de prompt.
- `ai/schemas.py`: `ActorDecision` (position, intensity, public_message, private_strategy, requested_concession, confidence, reason).
- `ai/prompts.py`: el actor recibe *solo* lo que razonablemente conocería (visibilidad por rol).
- `actors/llm_based.py`: misma interfaz que `rule_based.py`. Se elige por config: `actor.brain = "rules" | "ollama:<modelo>"`.
- Trazas: prompt, respuesta cruda, JSON parseado, veredicto de permisos, consecuencia.
- Modo mixto: 3 actores IA + 22 por reglas.

**DoD.**
- 48 meses con los 3 agentes IA corren sin una sola mutación de estado fuera del motor.
- ≥95 % de respuestas parsean al esquema al primer intento con el modelo elegido.
- Una corrida `rules` y una `ollama` con la misma semilla se pueden comparar lado a lado.

**Modelo Claude Code.**
- Prompts, esquemas y política de visibilidad: **Opus 5**.
- Cliente, cache, trazas: **Sonnet 5**.

**Runtime (Ollama).**
- Agentes en partida interactiva: un modelo de **8–14B** con buen seguimiento de JSON schema (por ejemplo `qwen3:8b`, `llama3.1:8b`, `gemma3:12b`; verificar tags en ollama.com/library y cuánto entra en tu GPU/RAM).
- Para iterar prompts rápido: **3–4B** (`qwen3:4b`, `llama3.2:3b`, `gemma3:4b`).
- Regla: fijar `temperature` y `seed` en cada llamada y guardar `model + digest` en la traza.

---

### Fase 5 — Interacción: negociación, Congreso, medios, cohortes (5–7 sesiones)

**Objetivo.** Que aparezca política emergente: rosca, alianzas, percepción distinta de la realidad.

**Entregables**
- **Negociación agente-agente**: protocolo de ofertas/contraofertas con máximo de rondas; todo el diálogo se guarda.
- **Congreso**: partidos con `seats`, `discipline`, `electoral_pressure`; una ley necesita N votos; presión de partido, gobernador, opinión, sindicatos, empresarios.
- **Percepción**: `perceived_inflation`, `perceived_unemployment`, `economic_sentiment`; los medios publican y mueven percepción por bloque social según `media_consumption`.
- **Cohortes sociales**: 8 grupos (clase trabajadora urbana, productores rurales, clase media alta, empleados públicos, jóvenes profesionales, informales, jubilados, estudiantes) con población, ingreso, desempleo, preferencias, confianza institucional.
- Todo con gemelo por reglas.

**DoD.**
- El presidente necesita 9 votos y consigue (o no) los votos negociando concesiones registradas.
- Dos medios que ven los mismos números producen percepciones distintas en cohortes distintas.
- Una alianza no programada explícitamente aparece en al menos una corrida (documentarla).

**Modelo Claude Code.**
- Diseño del protocolo de negociación y del modelo de percepción: **Fable 5.1** (interacción entre subsistemas, fácil de romper).
- Implementación: **Sonnet 5**. Revisión de PR de cada subsistema: **Opus 5**.

**Runtime.** Ollama 8–14B para actores que negocian; 3–4B para medios y cohortes (decisiones más simples, muchas llamadas).

---

### Fase 6 — Memoria y elecciones (3–4 sesiones)

**Objetivo.** Las relaciones tienen historia y el gobierno puede cambiar.

**Entregables**
- `ai/memory.py`: memorias como `{turn, actor, event, importance, sentiment}`; recuperación por relevancia + recencia + importancia; presupuesto de tokens por prompt.
- Decaimiento y consolidación (resúmenes cada 12 turnos).
- **Elecciones**: voto económico + afinidad ideológica + aprobación + lealtad partidaria + efectos regionales + campaña + eventos recientes + ruido. Resultado por provincia y nacional.
- Transición de gobierno: los actores persisten, recuerdan al gobierno anterior.

**DoD.**
- Un acuerdo roto en el turno 17 aparece en el prompt del gobernador en el turno 20 y baja su disposición a negociar.
- 100 elecciones simuladas con semillas distintas dan distribuciones plausibles (no siempre gana el mismo, no es ruido puro).

**Modelo Claude Code.** Sonnet 5 para implementar; Opus 5 para diseñar el modelo electoral y la política de recuperación de memoria.
**Runtime.** Igual que Fase 5. La memoria se resume con el mismo modelo local de 8B.

---

### Fase 7 — Evals, observabilidad y gobernanza (4–6 sesiones)

**Objetivo.** Poder afirmar con datos si los agentes son coherentes, y explicar cualquier decisión absurda.

**Entregables**
- **Evals** (`src/evals/`), cada uno con dataset y métrica:
  - *Ideological consistency*: 100 casos con resultado esperado (ej. actor anti-impuestos vs. duplicar impuestos → OPPOSE).
  - *Interest consistency*: ¿protege sus intereses declarados?
  - *Temporal consistency*: prometió X, hizo no-X, ¿hay razón registrada?
  - *Memory recall*: ¿menciona el evento importante cuando corresponde?
  - *Hallucination*: ¿menciona hechos que no están en el log?
  - *Authority violation*: tasa de acciones fuera de catálogo.
  - *Strategic adaptation*: ¿cambia estrategia al cambiar la situación?
  - *Diversity*: distancia entre respuestas de actores distintos ante el mismo estímulo.
- Promptfoo: configuración para correr el mismo dataset contra varios prompts/modelos y comparar.
- **Langfuse** self-hosted: cada decisión es una traza (input → memorias → prompt → modelo → respuesta → parseo → permisos → consecuencia → score).
- **Gobernanza** (`src/governance/`): ficha por actor con `READ / WRITE / EXECUTE`, `autonomy_level 0–5`, `human_approval_required`, `max_authority`. El motor la aplica; no es documentación.

**DoD.**
- `republica eval --suite all --brain ollama:qwen3:8b` produce un reporte con las 8 métricas y compara contra `--brain rules`.
- Cualquier decisión de cualquier corrida se puede abrir en Langfuse y reconstruir.
- Subir `autonomy_level` del Banco Central de 2 a 4 cambia comportamiento observable y queda registrado.

**Modelo Claude Code.**
- Diseño de los evals (qué medir, cómo evitar que el eval mida el prompt y no al agente): **Fable 5.1**. Es la parte más difícil y más valiosa del portfolio.
- Generación de casos de eval: **Sonnet 5** (con revisión humana de una muestra).
- Plumbing de Langfuse/Promptfoo: **Sonnet 5**.

**Runtime.**
- Agentes evaluados: Ollama (los mismos de Fase 4–5).
- **Juez** (LLM-as-judge para coherencia, alucinación, calidad de razón): un modelo **distinto y más fuerte** que el evaluado. Opciones: Claude Sonnet 5 vía API (volumen bajo, costo acotado) o un local grande (`qwen3:32b` o similar) si querés cero API. Nunca el mismo modelo que juzga y actúa.
- Métricas mecánicas (authority violation, parse rate, diversity) no usan LLM.

---

### Fase 8 — Experimentos en lote y comparación de modelos (3–4 sesiones)

**Objetivo.** `republica experiment --config exp/bc_independence.yaml --runs 100` y análisis en SQL.

**Entregables**
- `src/experiments/`: definición declarativa (variables a variar, N corridas, semillas, brains por actor), ejecución paralela (multiprocessing; Ollama en cola), salida a DuckDB.
- Tablas: `runs`, `turns`, `state`, `decisions`, `negotiations`, `elections`, `evals`.
- Notebooks de análisis: supervivencia del gobierno, inflación, estabilidad, credibilidad del BC.
- Experimento canónico 1: Banco Central independiente vs. no (50/50).
- Experimento canónico 2: mismo país, mismo shock, brains distintos (`rules`, `ollama:A`, `ollama:B`): ¿cuál es más consistente, inventa menos, negocia mejor, produce más diversidad?

**DoD.** Dos experimentos con reporte reproducible (semillas fijas) commiteado en `notebooks/`.

**Modelo Claude Code.** Sonnet 5 para el runner y el esquema DuckDB; **Opus 5** para el análisis estadístico y la redacción de conclusiones (y para que te discuta si la conclusión no se sostiene).
**Runtime.** Ollama **3–4B** para lotes grandes (100+ corridas × 48 meses × N actores es mucho token); 8B solo para el experimento de comparación de modelos.

---

### Fase 9 — Modelo sustituto, active learning y UI (5–8 sesiones)

**Objetivo.** Escalar de cientos a millones de corridas sin LLM en cada decisión.

**Entregables**
- Dataset `(contexto_del_actor → decisión)` extraído de todas las corridas con LLM.
- Modelo sustituto barato (gradient boosting o red pequeña) que imita al actor IA; se usa como `brain = "surrogate"`.
- Active learning: cuando el sustituto tiene baja confianza o el contexto está fuera de distribución, consulta al LLM y agrega el caso al dataset.
- Early-warning: modelo que predice colapso a 12 meses a partir del turno t; importancia de variables.
- Clustering de trayectorias/regímenes (embeddings + reducción de dimensión).
- UI Streamlit: pestañas World / Politics / Economy / Congress / Actors / Relations / Media / Events / AI traces / Evals / Experiments.

**DoD.**
- 10.000 corridas con `surrogate` en menos de una hora en una laptop.
- El sustituto reproduce ≥85 % de las decisiones del LLM en un test set held-out; los desacuerdos se pueden inspeccionar.

**Modelo Claude Code.**
- Diseño del sustituto y del criterio de active learning: **Fable 5.1**.
- Entrenamiento, pipeline, Streamlit: **Sonnet 5**; componentes de UI repetitivos: **Haiku 4.5**.

**Runtime.** `surrogate` para volumen; Ollama 8B para consultas de active learning; sin LLM en la UI.

---

### Fase 10 — República Artificial v2: la CPU social mínima (investigación, sin fecha)

**Objetivo.** Dejar de hardcodear instituciones. Definir las 10–20 primitivas con las que agentes autónomos pueden inventar sus propias reglas, y ver qué emerge.

Esta fase vive en un paquete separado (`src/republica/core/` o un repo hermano) para no romper v1, que sigue siendo el juego/laboratorio calibrado.

**Entregables**
- ADR "Physics vs. Institutions": qué queda fijo (agentes, recursos, espacio, producción, información, comunicación, memoria, acciones primitivas) y qué debe poder emerger (moneda, Estado, partidos, sindicatos, bancos, cargos).
- Lenguaje institucional mínimo: `GRANT, REVOKE, TRANSFER, DELEGATE, SELECT, AGGREGATE, CONDITION, EXPIRE, SANCTION, CREATE_GROUP, MODIFY_RULE` (+ metarreglas). Intérprete en Python; una "constitución" es un programa.
- Representación de constituciones como genoma; operadores de mutación/recombinación; loop evolutivo bajo shocks.
- Clasificación *a posteriori*: convertir estructuras institucionales finales en grafos/vectores, clustering, y recién después ponerles nombre.
- Frontera de Pareto sobre {prosperidad, igualdad, libertad, estabilidad, capacidad de respuesta}; nunca una sola función objetivo.
- "Investigador IA": agente externo que lee resultados, propone hipótesis, diseña experimentos, los ejecuta y reformula.
- Batería epistemológica obligatoria antes de publicar cualquier hallazgo: stress testing, ablations, sensibilidad, out-of-distribution, y validación contra datos reales (World Bank, IMF, V-Dem, Polity).

**DoD (primer hito).** Un mundo de 10.000 agentes sin Estado ni moneda en el que, en una fracción medible de corridas, emerge un medio de intercambio dominante. Documentado con semillas.

**Modelo Claude Code.**
- Definición de las primitivas y del ADR: **Fable 5.1**, sin excepción. Es la decisión conceptual más importante del proyecto y la más fácil de contaminar con supuestos escondidos (presidencialismo, capitalismo, partidos).
- Intérprete y loop evolutivo: **Opus 5** diseña, **Sonnet 5** implementa.

**Runtime.**
- Agentes de base: reglas / sustituto (volumen enorme).
- Agentes que inventan reglas: Ollama 8–14B con tool calling.
- Investigador IA: **Claude Opus 5 o Fable 5.1 vía API** (pocas llamadas, razonamiento largo, es donde más rinde el modelo fuerte).

---

## 3. Resumen: qué modelo en cada etapa

### 3.1 Claude Code (para construir)

Regla general: **decisiones de diseño irreversibles → modelo más fuerte; implementación con spec y tests → Sonnet 5; tareas mecánicas → Haiku 4.5; revisión de cada PR de fase → Opus 5.**

| Fase | Diseño / decisiones | Implementación | Mecánico |
|---|---|---|---|
| 0 Scaffold | — | Sonnet 5 | Haiku 4.5 |
| 1 Mundo sin IA | Fable 5.1 (fórmulas, estabilidad) | Sonnet 5 | Haiku 4.5 (datos) |
| 2 Juego humano | Opus 5 (dilemas) | Sonnet 5 | — |
| 3 Actores por reglas + permisos | Opus 5 (esquema de acciones/permisos) | Sonnet 5 | Haiku 4.5 (fichas YAML) |
| 4 Primeros agentes Ollama | Opus 5 (prompts, esquemas, visibilidad) | Sonnet 5 | — |
| 5 Negociación, Congreso, medios, cohortes | Fable 5.1 | Sonnet 5 | — |
| 6 Memoria y elecciones | Opus 5 | Sonnet 5 | — |
| 7 Evals, observabilidad, gobernanza | Fable 5.1 (diseño de evals) | Sonnet 5 | — |
| 8 Experimentos y comparación de modelos | Opus 5 (análisis) | Sonnet 5 | — |
| 9 Sustituto, active learning, UI | Fable 5.1 | Sonnet 5 | Haiku 4.5 (UI repetitiva) |
| 10 CPU social (v2) | Fable 5.1 | Opus 5 → Sonnet 5 | — |

Cómo usarlo en la práctica: abrir la fase en *plan mode* con el modelo de diseño, dejar la spec y los tests escritos en `docs/`, y recién ahí cambiar a Sonnet para implementar contra esa spec. Antes de mergear, una pasada de `/code-review` con Opus.

### 3.2 Runtime (dentro de la simulación)

| Rol en la simulación | Modelo | Por qué |
|---|---|---|
| Baseline de todo actor | Reglas (sin LLM) | Sin baseline no hay eval ni comparación |
| Actores principales en partida interactiva (presidente, ministro, gobernadores) | Ollama 8–14B (`qwen3:8b`, `llama3.1:8b`, `gemma3:12b` o equivalente) | Mejor seguimiento de esquema y razón legible |
| Actores secundarios y lotes grandes (medios, cohortes, 100+ corridas) | Ollama 3–4B | Muchas llamadas, decisiones simples |
| Resumen de memoria | El mismo local de 8B | Sin costo, calidad suficiente |
| Juez en evals (coherencia, alucinación) | Claude Sonnet 5 vía API, o local ≥30B | Distinto y más fuerte que el evaluado |
| Millones de corridas | Modelo sustituto (GBM/red pequeña) | Sin LLM por decisión |
| Consulta de active learning | Ollama 8B | Solo casos fuera de distribución |
| Investigador IA (hipótesis, diseño experimental) | Claude Opus 5 / Fable 5.1 vía API | Pocas llamadas, razonamiento largo |

Notas:
- Los tags de Ollama cambian; antes de fijar uno, verificar en ollama.com/library y medir *parse rate* al esquema con 50 prompts reales. Ese número decide, no el benchmark.
- Con 16 GB de RAM y sin GPU, el techo práctico es 8B cuantizado. Con 8 GB, 3–4B.
- Siempre guardar `model`, `digest`, `temperature`, `seed` en la traza. Sin eso el experimento de Fase 8 no es reproducible.

---

## 4. Hitos públicos (lo que se muestra)

| Hito | Fases | Qué se puede mostrar |
|---|---|---|
| **v0.1** | 0–1 | Un país que simula 48 meses coherentes. `README` con una corrida narrada. |
| **v0.2** | 2 | Se puede jugar como presidente en terminal. |
| **v0.3** | 3–4 | 3 agentes IA con permisos, comparados contra reglas. Primer tweet/post técnico. |
| **v0.5** | 5–6 | Congreso, negociación, medios, elecciones, memoria. Streamlit básico. |
| **v0.8** | 7–8 | Evals + Langfuse + gobernanza + dos experimentos reproducibles. README "portfolio". |
| **v1.0** | 9 | Sustituto + 10.000 corridas + early-warning + clustering de regímenes. |
| **v2 (research)** | 10 | CPU social mínima y emergencia institucional. Posible paper/preprint. |

---

## 5. Riesgos y cómo se mitigan

| Riesgo | Mitigación |
|---|---|
| Empezar por los agentes y terminar con una demo incontrolable | El orden de fases es obligatorio. Fase 4 no arranca sin DoD de Fase 3. |
| Modelo económico que explota o es trivial | Tests de propiedades en 1.000 semillas desde Fase 1; coeficientes en datos, no en código. |
| El LLM "hace trampa" tocando estado | El estado solo se muta en `engine/`; los actores devuelven datos, nunca funciones. Test que lo verifica. |
| Evals que miden el prompt y no al agente | Datasets con resultado esperado fijado *antes* de escribir el prompt; juez distinto del actor. |
| Costo/lentitud de Ollama en lotes | 3–4B para lotes, cache por hash de prompt, sustituto desde Fase 9. |
| Confundir "en mi modelo pasa X" con "en el mundo pasa X" | Sección obligatoria de limitaciones en cada reporte; batería epistemológica de Fase 10 antes de cualquier afirmación. |
| Supuestos escondidos en v2 (democracia, capitalismo, partidos) | ADR de primitivas revisado explícitamente contra esa lista antes de escribir código. |

---

## 6. Próximo paso concreto

Fase 0 y el arranque de Fase 1: escribir `docs/SPEC_v0.1.md` (variables con valores iniciales y rangos, fórmulas con coeficientes, 8 provincias, 5 partidos, 12 shocks, reglas de turno) y dejarla aprobada antes de implementar. Esa spec se escribe con el modelo de diseño (Fable 5.1 / Opus 5) en plan mode; la implementación de `world/` y los tests con Sonnet 5.

---

## 7. Estado al cierre de la primera ejecución (septiembre 2026)

| Fase | Estado | Evidencia |
|---|---|---|
| 0 Scaffold | ✅ | CI con ruff + pytest |
| 1 Mundo sin IA | ✅ | `SPEC_v0.1.md`, 5 rondas de calibración documentadas, `batch` 300 semillas |
| 2 Juego humano | ✅ | `play`, 14 dilemas, contrafáctico; **pendiente del usuario: jugar tres partidas** |
| 3 Actores por reglas + permisos | ✅ | 29 fichas, catálogo, `authorize()`; Revisión 001 cerrada |
| 4 Agentes Ollama | ✅ código, ⏳ verificación | Todo probado con `fake:*`; **pendiente del usuario: `bench-parse` con Ollama local** |
| 5 Negociación, Congreso, medios, cohortes | ✅ | Revisión 002 cerrada; regla de audiencia recalibrada |
| 6 Memoria y elecciones | ✅ | Calibración electoral (lealtad, τ, bono regional) |
| 7 Evals, trazas, gobernanza | ✅ parcial | 32 casos generados; **pendiente del usuario: 20 casos `author: human`**; Langfuse sin verificar (sin Docker) |
| 8 Experimentos | ✅ | BC independiente (50×2), regla fiscal (3×3×20), `brain_comparison` sin brazos Ollama |
| 9 Sustituto, early-warning, regímenes, UI | ✅ con reservas | Revisión 003: acuerdo del sustituto reportado con baseline; inferencia por lote pendiente (34× más lento que reglas) |
| 10 CPU social | ✅ hito 1 | ADR 010; `core/` con moneda emergente (H1, H2, H4 cumplidas, H3 refutada); hitos 2–5 sin implementar |

Tres revisiones de código independientes (32 hallazgos verificados, todos cerrados salvo los que
quedaron como tareas explícitas). Suite: 194 tests (188 rápidos). Ningún resultado se corrió contra
un LLM real: ese es el primer paso del usuario con el repo en su máquina (`docs/OLLAMA_SETUP.md`).
