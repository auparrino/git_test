# República Artificial

**Un laboratorio computacional de política y economía donde agentes autónomos gobiernan un país ficticio,
con reglas deterministas, permisos explícitos, memoria, evals y experimentos reproducibles.**

> *República Artificial is an agent-based simulation for studying autonomous decision-making inside a
> dynamic political economy. It separates deterministic state transitions (Python) from actor behaviour
> (rules or LLMs), and implements a closed action catalogue, permissions and governance sheets,
> long-term memory, elections, structured evals, tracing and a batch experiment framework with DuckDB
> analytics. Everything runs offline; an Ollama backend plugs in without code changes.*

La República de Aurora tiene 10 millones de habitantes en 8 provincias, 5 partidos, un Congreso de 100
bancas, 8 cohortes sociales, 3 medios y 29 actores políticos con ideología, intereses y personalidad
propios. Cada turno es un mes. Podés jugar como presidente, mirar cómo actúan los agentes, o lanzar
cientos de simulaciones y preguntar por qué algunos gobiernos sobreviven y otros colapsan.

Visor de una corrida de dos mandatos (semilla 7): reproducción mes a mes con gráficos, Congreso,
negociaciones, cohortes, memorias y noche electoral → `uv run republica viewer simulations/run.jsonl`.

---

## La regla que ordena todo

```
Python decide qué pasa en el mundo.   La IA decide qué quieren hacer los actores.   La IA nunca toca el estado.
```

Un actor (por reglas o LLM) recibe **solo la percepción de su rol**, razona y devuelve una acción
estructurada de un **catálogo cerrado**. El motor la pasa por `authorize()` (gobernanza → matriz de rol →
parámetros → condiciones de estado → cooldowns → presupuesto del turno), aplica consecuencias y recién
entonces muta el estado. Toda denegación queda registrada y es una métrica.

```json
{"type": "NEGOTIATE", "actor_id": "gov_norte", "target": "president",
 "params": {"requested_concession": "restore_transfers"},
 "reason": "El recorte deja a Norte sin presupuesto; apoyo condicionado a restaurar transferencias."}
```

---

## Qué hay construido

| Capa | Contenido | Dónde |
|---|---|---|
| **Mundo** | 20 variables de estado, transiciones mensuales en dos etapas, 12 shocks con efectos objetivos, eventos endógenos (devaluación forzada, colapso, hiperinflación), tres reglas de política | `SPEC_v0.1.md`, `world/` |
| **Juego** | `republica play`: tablero, 14 dilemas disparados por estado, consejero por reglas, guardado por replay, contrafáctico "qué hubiera pasado sin vos" | `SPEC_v0.2_play.md`, `engine/game.py` |
| **Actores** | 29 fichas YAML (ideología ≠ intereses ≠ personalidad), scoring por reglas, escalada, catálogo de 20 tipos de acción, permisos por rol, consecuencias, relaciones vivas | `ADR_003`, `actors/`, `engine/permissions.py` |
| **Capa de IA** | Esquemas JSON, prompts por rol con visibilidad restringida, cliente Ollama, backends falsos para CI (`fake:rules` reproduce `rules` byte a byte), caché, trazas por decisión | `ADR_004`, `ai/` |
| **Interacción** | Congreso con disciplina y presión, negociación en 3 rondas con acuerdos que se cumplen o se rompen, 8 cohortes con aprobación y percepción propias, medios que mueven percepción (nunca el PIB) con costo reputacional | `ADR_005`, `engine/congress.py`, `engine/negotiation.py`, `world/cohorts.py`, `world/perception.py` |
| **Memoria y elecciones** | Memoria por actor con importancia, recencia y relevancia; consolidación; elecciones a dos vueltas con D'Hondt, campaña y promesas; transición de gobierno con actores que recuerdan | `ADR_006`, `ai/memory.py`, `world/elections.py` |
| **Evals y gobernanza** | 10 métricas (ideología, intereses, consistencia temporal, memoria, alucinación, violación de autoridad, adaptación, diversidad, realismo) con baseline por reglas e IC bootstrap; juez ≠ actor; fichas de gobernanza por actor con niveles de autonomía aplicados por el motor; trazas exportables a Langfuse | `ADR_007`, `evals/`, `governance/` |
| **Experimentos** | Definición YAML con brazos y sweeps, runner paralelo con resume, DuckDB con 9 tablas, reportes con Cliff's delta y mapas de calor | `ADR_008`, `experiments/` |
| **Visor** | HTML autocontenido por corrida | `republica viewer` |
| **Sustituto y análisis** | Dataset de decisiones, sustituto sklearn por rol con active learning (`surrogate:<path>+fallback:rules`), early-warning de crisis a 12 meses, clustering de regímenes, UI Streamlit de 12 pestañas con modo jugable | `ADR_009`, `ml/`, `ui/app.py` |
| **Núcleo sin instituciones (v2)** | 10.000 agentes, 6 bienes, solo `OFFER`/`TRANSFER`, estrategia evolutiva y clasificación a posteriori; test de contaminación contra la lista de instituciones que no pueden aparecer en el código | `ADR_010`, `core/` |

194 tests, todos offline. Cada fase tiene tests de aceptación y hashes dorados que garantizan que
apagar una feature reproduce exactamente la versión anterior.

---

## Resultados que ya salieron del laboratorio

Todos con semillas fijas y reproducibles con `republica experiment run experiments/<nombre>.yaml`.

**Banco Central independiente (50 semillas × 2 brazos).** Hipótesis registrada antes de correr:
menor inflación y mayor desempleo con BC independiente, sin diferencia clara en supervivencia.

| Brazo | Inflación anual final (mediana, IC 95 %) | Desempleo final | Crecimiento medio | Crisis antes de la elección |
|---|---|---|---|---|
| Dependiente (autonomía 2) | 38.9 % [29.5, 52.3] | 8.9 % | 1.7 % | 8 de 50 |
| Independiente (autonomía 4) | 23.5 % [20.8, 26.0] | 11.0 % | 0.5 % | 0 de 50 |

Se cumplió lo previsto y apareció lo no previsto: el BC independiente evitó todas las hiperinflaciones,
a costa de dos puntos de desempleo y un punto de crecimiento. Detalle en
[`experiments/results/central_bank_independence/report.md`](experiments/results/central_bank_independence/report.md).

**Regla fiscal (sweep 3×3, 20 semillas por celda).** Supervivencia según monetización del déficit
(`c_f`) y gasto primario (% PIB):

| c_f \ gasto | 23 | 25 | 27 |
|---|---|---|---|
| 0.08 | 100 % | 100 % | 45 % |
| 0.12 | 100 % | 95 % | 5 % |
| 0.16 | 100 % | 80 % | 0 % |

Dos puntos de PIB de gasto separan un país estable de uno con 1000 % de inflación; con gasto 23 la
economía cae en deflación y desempleo del 17 %, y ningún gobierno es reelegido.
[`experiments/results/fiscal_rule/report.md`](experiments/results/fiscal_rule/report.md).

**Comportamiento emergente** (documentado con semilla y turno en [`docs/EMERGENCE_LOG.md`](docs/EMERGENCE_LOG.md)):
una trampa de inflación crónica con reservas en cero de la que un Banco Central pasivo no sale solo;
un gobierno que ajusta siempre termina en deflación con 16 % de desempleo y 19 de aprobación; los tres
medios convergían al frame "crisis" hasta que la regla de audiencia pasó a medir alineación con la
audiencia propia y a cobrar un costo reputacional por contradecir la realidad.

---

## Probarlo

```bash
uv sync --group dev
uv run republica run --seed 7 --policy taylor --months 96 --out simulations/run_7.jsonl
uv run republica narrate simulations/run_7.jsonl        # la historia mes a mes, con votos, acuerdos y elección
uv run republica viewer simulations/run_7.jsonl         # visor HTML autocontenido
uv run republica play --seed 7                          # vos sos el presidente
uv run republica emergence simulations/run_7.jsonl      # alianzas, coaliciones repetidas, acuerdos rotos
uv run republica eval --suite all --brain rules --judge fake --out evals/reports/rules
uv run pytest -q
```

Experimentos (extra `analysis`: duckdb, pandas, matplotlib):

```bash
uv sync --group dev --extra analysis
uv run republica experiment run experiments/central_bank_independence.yaml --workers 4 --out experiments/results/central_bank_independence
uv run republica experiment report experiments/results/central_bank_independence
uv run republica experiment load experiments/results/central_bank_independence --db simulations/republica.duckdb
duckdb simulations/republica.duckdb < experiments/queries/survival_by_arm.sql
```

Con Ollama local (ver [`docs/OLLAMA_SETUP.md`](docs/OLLAMA_SETUP.md)):

```bash
ollama pull qwen3:8b
uv run republica bench-parse --brain llm:ollama:qwen3:8b --n 50 --role governor   # parse rate, violaciones de autoridad, latencia
uv run republica run --seed 7 --brains data/brains.yaml                            # 3 actores IA + 26 por reglas
uv run republica compare --seed 7 --a rules --b llm:ollama:qwen3:8b --actor gov_norte
uv run republica eval --suite all --brain llm:ollama:qwen3:8b --judge llm:ollama:qwen3:32b
```

---

## Cómo se construyó

Orden obligatorio, sin saltos: **mundo → reglas → decisiones humanas → actores simples → IA → memoria →
interacción → evals → autonomía**. Cada fase con spec o ADR escrito antes de codear, tests de aceptación
como definición de "listo", revisión de código independiente entre fases (tres rondas, 32 hallazgos
verificados y cerrados: [`REVIEW_001`](docs/REVIEW_001_fases_1-3.md), [`REVIEW_002`](docs/REVIEW_002_fases_4-7.md),
[`REVIEW_003`](docs/REVIEW_003_fases_8-9.md))
y un [registro de calibración](docs/CALIBRATION_LOG.md) que explica cada coeficiente que cambió y por qué.

Los modelos usados: diseño y decisiones irreversibles con el modelo más fuerte disponible,
implementación contra spec con un modelo intermedio, tareas mecánicas con el más chico, revisión con
uno distinto del que implementó. El plan completo, con el modelo por etapa y la checklist operativa,
está en [`docs/PLAN.md`](docs/PLAN.md) y [`docs/PASO_A_PASO.md`](docs/PASO_A_PASO.md).

**Moneda emergente (v2, hito 1; 100 semillas × 2.000 agentes × 500 turnos).** En un mundo sin moneda,
Estado ni precios, donde los agentes solo pueden ofrecer y transferir bienes, en 100 de 100 semillas
emerge un medio de intercambio antes del turno 100: siempre las conchas, el único bien que nadie
consume. La abundancia de conchas (×0.3 a ×3) no cambia nada (hipótesis H3 refutada) y el costo de
transporte solo retrasa la emergencia (H4 confirmada). El control negativo dejó el hallazgo más
interesante: bajar la durabilidad de todos los bienes no impide que aparezca dinero; lo que lo impide
es que no exista ningún bien sin utilidad directa.
[`experiments/results/core_hito1/main/report.md`](experiments/results/core_hito1/main/report.md).

## Lo que viene

- **Fase 9, lo que falta** ([`ADR_009`](docs/ADR_009_surrogate_ui.md), resultados en
  [`FASE9_RESULTS.md`](docs/FASE9_RESULTS.md)): modelo sustituto entrenado sobre las decisiones de los
  actores (el acuerdo se mide contra un baseline de clase mayoritaria, no solo, porque con actores por
  reglas casi todo es `neutral` y el problema es casi trivial: 0.9986 de acuerdo agregado vs. 0.9959 de
  ese baseline, contra 0.67 en los casos donde el actor de verdad toma partido — el sustituto recién es
  informativo imitando a un LLM), active learning cuando el sustituto duda, early-warning de crisis a 12
  meses (AUC 0.996/0.998 en validación/test), clustering de regímenes políticos e interfaz Streamlit.
  Pendiente: inferencia por lote en el scheduler (el sustituto corre 34× más lento que las reglas) y
  entrenarlo sobre actores LLM, que es cuando deja de ser trivial.
- **Fase 10, hitos 2 a 5** ([`ADR_010`](docs/ADR_010_social_cpu.md)): activar de a una las once
  primitivas (`PROMISE`, `GRANT`, `CREATE_GROUP`, `AGGREGATE`, `CONDITION`, `SANCTION`, `MODIFY_RULE`…)
  y preguntar si emergen crédito, organizaciones coercitivas, procedimientos de decisión y constituciones
  que nadie programó; después, un investigador IA que proponga y corra sus propios experimentos.
- **Lo que solo podés hacer vos**: jugar tres partidas, escribir los 20 casos de eval a mano, y correr
  `bench-parse` y `compare` con Ollama local. Es lo primero que le da sentido de verdad al sustituto, a
  los evals y a la comparación entre modelos.

## Limitaciones

Los resultados describen el comportamiento de República Artificial bajo sus reglas; no son evidencia
sobre economías reales. Las 20 variables, los coeficientes y los shocks son hipótesis calibradas a mano
para que el mundo sea internamente coherente, no un modelo econométrico. Los evals de ideología pasan
al 100 % contra reglas porque los casos se generaron desde las reglas: prueban la tubería, no la verdad
de las reglas; los 20 casos escritos a mano siguen pendientes. Nada de esto se corrió todavía contra un
LLM real: toda la capa de IA está verificada con backends falsos que reproducen las reglas.

## Stack

Python 3.12+ · uv · pydantic · typer · rich · pytest · hypothesis · DuckDB · scikit-learn · numpy (solo `core/`) · Streamlit · Ollama · Langfuse (opcional) · Promptfoo (export)
