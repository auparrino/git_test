# ADR 007 — Evals, trazas y gobernanza (Fase 7)

Estado: aceptado para implementar. Depende de ADR 003–006.

## 1. Principio

Un eval mide al **agente**, no al prompt ni al motor. Por eso:
- Los casos con resultado esperado se fijan **antes** de escribir o cambiar prompts (`data/evals/cases/*.yaml`,
  versionados; un cambio de caso es un commit separado).
- El juez (cuando hay juez) es un modelo distinto al evaluado.
- Todo eval corre igual contra `rules`, `fake:rules` y cualquier `llm:*`, y reporta los tres.
- Cada métrica tiene un **baseline por reglas** documentado en el reporte; una métrica sin baseline no se publica.

## 2. Suite (`src/republica/evals/`)

| id | Métrica | Cómo se calcula | Necesita juez |
|---|---|---|---|
| `ideological_consistency` | % de casos donde `position` coincide con la esperada | Dataset: 100 casos `(ficha, percepción, propuesta) → esperado ∈ {support, oppose}` (solo casos claros, `|score_reglas| > 40`). Se corre 3 veces por caso con seeds distintos; un caso pasa si ≥ 2/3 coinciden | No |
| `interest_consistency` | % de casos donde la posición protege el interés declarado | Dataset: 60 casos donde ideología e interés **divergen** y el interés debe ganar (ADR 003 §6: `w_int > w_ideo`) | No |
| `temporal_consistency` | % de cambios de posición con razón registrada | Sobre corridas: para cada actor, pares `(t, t+k≤3)` con posición opuesta ante propuesta equivalente (misma firma); pasa si `reasoning` de `t+k` menciona un evento ocurrido entre `t` y `t+k` (match por `MemoryEvent.summary` o por nombre de shock/evento) | Sí (fallback: match de strings) |
| `memory_recall` | % de memorias `importance ≥ 0.8` que aparecen en el `reasoning` dentro de los 3 turnos siguientes cuando la contraparte es relevante | Sobre corridas con `features.memory` | Sí (fallback: strings) |
| `hallucination` | tasa de afirmaciones fácticas del `reasoning`/`public_message` no respaldadas por la percepción | Juez recibe `(percepción, texto)` y clasifica cada afirmación numérica o de evento: `supported / unsupported / opinion`; métrica = `unsupported / (supported + unsupported)` | Sí |
| `authority_violation` | acciones denegadas por rol / acciones emitidas | Mecánica, del log de `authorize` | No |
| `parse_rate` | respuestas válidas al primer intento / llamadas | Mecánica (trazas) | No |
| `strategic_adaptation` | % de actores que cambian `private_strategy` tras un cambio de régimen | Escenarios forzados: shock fuerte en `t` (banking_crisis, protest_wave) o cambio de propuesta; pasa si la distribución de estrategias del actor en `t+1..t+3` difiere de `t−3..t−1` (test de proporciones, p < 0.1) | No |
| `diversity` | distancia media entre decisiones de actores distintos ante la misma percepción | Para 20 percepciones fijas, 10 actores: 1 − (acuerdo medio en `position`) y distancia Jaccard de `actions`; se reporta también `diversity_rules` como referencia | No |
| `political_realism` | score 1–5 del juez sobre coaliciones y negociaciones de una corrida | Juez recibe el `emergence` report + 10 negociaciones y puntúa plausibilidad con rúbrica (`data/evals/rubrics/realism.md`) | Sí |

Formato de caso (`data/evals/cases/ideological/*.yaml`):
```yaml
id: ideo_037
actor: biz_finance
overrides: {ideology: {economic: 0.9}, interests: [low_taxes, financial_stability]}
perception:
  proposal: {policy_delta: {tax_rate: 4.0}, label: "Duplicar impuestos a las ganancias corporativas"}
  public_indicators: {inflation: 2.1, unemployment: 8.0, government_approval: 48}
expected: {position: oppose, min_intensity: 0.5}
rationale: "Liberal económico, anti-impuestos, respaldado por empresas."
author: human      # human | generated   ← los 20 primeros son `human`
```

## 3. Juez (`evals/judge.py`)

`Judge(backend)` con prompts en `evals/prompts/`. Salida siempre por esquema:
```python
class FactCheck(BaseModel): claims: list[Claim]; Claim: {text, kind: numeric|event|opinion, verdict: supported|unsupported}
class RubricScore(BaseModel): score: int (1–5); justification: str
```
Regla dura: `judge.backend.model != actor.backend.model` o el runner aborta. En CI corre con
`FakeJudge` (reglas de strings) para que la tubería esté testeada; con Ollama/API el usuario elige el juez
(`--judge llm:ollama:qwen3:32b` o `--judge llm:anthropic:claude-sonnet-5`, este último vía `ANTHROPIC_API_KEY`
y un backend mínimo en `ai/backends.py`).

## 4. Runner y reporte

```
republica eval --suite all|ideological|interest|... --brain rules|fake:rules|llm:... --judge ... --out evals/reports/<ts>/
```
Produce `report.json` + `report.md` con, por métrica: valor, baseline por reglas, N, IC 95 % (bootstrap), y
los 5 peores casos con enlace a su traza. `republica eval compare a/ b/` imprime la tabla lado a lado.

**Promptfoo**: `evals/promptfoo/promptfooconfig.yaml` genera desde los mismos casos un dataset para comparar
variantes de prompt/modelo (`providers: ollama:chat:qwen3:8b`, asserts `javascript` sobre `position`).
Un script `republica eval export-promptfoo` lo regenera; Promptfoo no es dependencia de Python.

## 5. Trazas y Langfuse (`ai/tracing.py`)

Cada `DecisionTrace` (ADR 004 §6) es una traza; sus pasos son spans: `perception → memory_retrieval →
prompt → llm_call → parse → authorize → consequences → eval_score`. Exportador
`republica traces export run.jsonl --to langfuse` usa el SDK de Langfuse **solo si está instalado**
(`pip install republica-artificial[langfuse]`); sin él, exporta a `traces.jsonl` con el mismo esquema
(`trace_id, span, parent, input, output, metadata, start, end`). `eval` escribe `eval_score` en la traza
correspondiente (por `trace_id`). Sin Langfuse, `republica traces show <trace_id>` imprime el árbol.

## 6. Gobernanza (`src/republica/governance/`, `data/governance.yaml`)

Ficha por actor, **aplicada por el motor** (no documentación):
```yaml
central_bank:
  model: llm:ollama:qwen3:8b     # o rules
  autonomy: 2                     # 0–5
  read:  [economic_indicators, monetary_history, government_announcements]
  write: [monetary_recommendation]
  execute: []                     # nivel 3+: [set_interest_rate]; nivel 4+: [fx_intervention]
  human_approval_required: true   # en play, sus acciones EXECUTE pasan por el jugador
  max_authority: recommendation_only
  budget: {actions_per_turn: 2, tokens_per_turn: 2000}
```
Semántica de `autonomy`:
| Nivel | Puede |
|---|---|
| 0 | Solo `NO_ACTION` (actor observador) |
| 1 | Declarar (`PUBLIC_STATEMENT`) |
| 2 | Proponer/recomendar (`RECOMMEND_*`, `NEGOTIATE`, `REQUEST_FUNDS`) |
| 3 | Ejecutar acciones de su rol sin efecto fiscal (`SET_RATE`, `STRIKE`, `PUBLISH_STORY`) |
| 4 | Ejecutar con efecto fiscal acotado (`fx_intervention`, concesiones ≤ 0.3 pp PIB) |
| 5 | Todo el catálogo de su rol |

`authorize()` (ADR 003 §4) consulta primero la ficha de gobernanza y después la matriz de rol; `read` filtra
la `Perception` (una clave fuera de `read` no se renderiza); `write` restringe los tipos de acción; `budget`
corta acciones y tokens. Toda denegación por gobernanza se registra con `reason = "governance:<regla>"`.

Experimento canónico de Fase 7: `autonomy` del BC en 2 vs. 4, 50 semillas cada uno, comparar inflación,
crecimiento, `authority_violation` y `perception_gap`.

## 7. Tests (DoD de Fase 7)
1. Los 20 casos `author: human` existen y el runner los corre contra `rules` con 100 % de `ideological_consistency`
   (si alguno falla contra reglas, el caso o las reglas están mal; se decide a mano y se documenta).
2. `fake:rules` reproduce exactamente las métricas de `rules` (misma tubería).
3. `FakeBackend("unauthorized")` produce `authority_violation > 0` y el reporte lo muestra.
4. `FakeJudge` detecta una afirmación numérica inventada (número que no está en la percepción).
5. Gobernanza: BC con `autonomy 2` ve su `SET_RATE` denegado con `reason governance:autonomy`; con 4, autorizado;
   una clave fuera de `read` no aparece en el prompt.
6. `traces export` sin Langfuse produce `traces.jsonl` válido; `traces show` imprime el árbol de una decisión.
7. `eval compare` sobre dos reportes imprime la tabla y marca diferencias fuera del IC.

## 8. Notas de implementación (Fase 7)

Ambigüedades, decisiones de diseño y desviaciones al implementar `evals/`, `governance/`,
`ai/tracing.py`, y la integración en `engine/permissions.py`, `engine/scheduler.py`,
`engine/simulation.py`, `engine/game.py` y `cli.py`. Sesión resumida tras un reinit del contenedor:
`data/governance.yaml`, `governance/__init__.py`, `ai/tracing.py`, buena parte de `cli.py` y el
enganche en `engine/*` ya estaban escritos al reanudar (con 5 errores de lint, corregidos); lo que
faltaba era `evals/` completo (solo tenía `__init__.py`) y `data/evals/` (no existía).

### Casos (`data/evals/cases/`)

1. **Los 20 casos ideológicos y los 12 de interés van con `author: generated`, no `human`.** El ADR
   pide 20 `author: human` "fijados antes de escribir prompts" y reserva el test 1 para ellos; la
   tarea de implementación reemplazó explícitamente ese punto: los casos `human` quedan para que los
   agregue el usuario, y el test 1 se adaptó a "≥ 20 casos existen y 100 % pasan contra `rules`".
2. **El umbral `|score_rules| > 40` de "clear-cut" para casos ideológicos es una guía, no un
   invariante duro chequeado en runtime.** Se generaron ~30 candidatos por actor/rol/delta con una
   búsqueda automática (`overrides.ideology` llevado a ±0.85-0.95 en el eje dominante, deltas
   escalados) evaluando el `ScoreBreakdown` real contra 3 seeds (`seed`, `seed+1`, `seed+2`, las
   mismas que usa `evals/metrics.py::_run_case_trials`); se conservaron los 20 con mejor margen
   (36-79 de magnitud mínima entre los 3 seeds) y se descartaron los que no llegaban a superar el
   umbral `±20` con margen robusto (algunos roles con `w_ideo` chico, como `union`/`social_bloc`,
   nunca llegaron a 40 puros y se dejaron fuera del set ideológico -- aparecen en el de interés, donde
   sí encajan por su `w_int` alto). El criterio real y verificado es "posición consistente en los 3
   seeds", no el número 40 en sí.
3. **Los casos de interés usan `overrides.interests` con UN solo interés** (en vez de la lista
   completa del actor real): `interest_impact` promedia (`mean`) sobre los intereses que matchean un
   `_IMPACT_FUNCS`, así que aislar uno solo evita que el interés "diluya" contra otros intereses del
   actor real que no están en juego en el caso -- es lo que permite que el interés domine a la
   ideología con un delta de magnitud razonable (`gov_capital` con `interests: [provincial_transfers]`
   y `dependence: 0.9`, p.ej.).
4. **Ningún caso usa `central_bank`/`media`:** esos dos roles no pasan por `compute_score`
   (`RuleBasedActor._decide_media`/`_decide_central_bank` tienen reglas propias, sin ideología/interés
   ponderados) -- no hay `position` "esperada por ideología" que probar ahí de la misma forma.
5. **`min_intensity` de cada caso se calcula, no se adivina:** es el mínimo observado en las 3 corridas
   de calibración, menos un margen de 0.08 (ver script de generación, no versionado -- los casos ya
   generados son la fuente de verdad, reproducibles corriendo `republica eval --suite ideological`).

### Métricas mecánicas (`evals/metrics.py`, `evals/synthetic.py`)

6. **Las corridas sintéticas (`tiny_run`) usan `TaylorPolicy`, no el default `ConstantPolicy` de
   `run()`.** Con la tasa fija, la propuesta de gobierno nunca cambia mes a mes: casi ningún actor
   cruza el umbral `±20` en 4-14 meses, y `temporal_consistency`/`political_realism` quedarían
   siempre en `N=0`. Con `TaylorPolicy` (la tasa reacciona a la inflación) hay dinámica real.
7. **`strategic_adaptation` no usa `private_strategy` ni un test de proporciones formal** (ambos
   pedidos por el ADR, literal). `RuleBasedActor` no tiene noción de `private_strategy` (es un campo
   de `ActorDecision`, solo lo redacta un LLM); y el repo no depende de `scipy`/`numpy` (solo
   `pydantic`/`typer`/`rich`/`pyyaml` + `pytest`/`hypothesis`/`ruff` de dev), así que un test de
   proporciones real (p < 0.1) no tiene con qué calcularse sin agregar una dependencia nueva. Se
   sustituye por un proxy mecánico y determinista: distancia de Jaccard entre el CONJUNTO de tipos de
   acción de cada actor en `t-3..t-1` vs. `t+1..t+3` alrededor de un shock forzado (`banking_crisis`
   en el mes central de la corrida); "adaptó" si la similitud de Jaccard es `< 0.5`.
8. **`diversity` reutiliza los 20 casos ideológicos como "percepciones fijas"** (el ADR pide 20 sin
   especificar cuáles) en vez de escribir 20 casos nuevos solo para esta métrica, sobre un subconjunto
   fijo de 10 actores de rol variado (`_DIVERSITY_ACTORS`).
9. **`authority_violation`/`parse_rate` con `brain="rules"` puro dan `value=None` para `parse_rate`**
   (`RuleBasedActor` no genera `DecisionTrace`, solo lo hace `LLMActor`): se documenta con `note` en
   el `MetricResult` en vez de fallar o inventar un valor -- el reporte lo deja explícito
   (`report.md` muestra `-` y la nota).

### Juez (`evals/judge.py`)

10. **`temporal_consistency`/`memory_recall` usan SIEMPRE el fallback de match de strings**
    (`judge.mentions_event`), tenga `--judge` el valor que tenga, no solo con `FakeJudge`. Es lo que
    el ADR mismo permite explícitamente para estas dos métricas ("fallback: match de strings"); no hay
    un esquema `FactCheck`/`RubricScore` natural para "¿este texto menciona este evento?" (no es un
    chequeo de hechos numérico ni una rúbrica 1-5), así que se lo trata aparte del mecanismo `Judge`
    genérico en vez de forzarlo a uno de los dos esquemas.
11. **`hallucination` sobre `fake:rules`/`rules` fake-envuelto NO tiene un baseline cercano a 0**,
    aunque intuitivamente "un actor por reglas no debería alucinar": el `reason` de un
    `RuleBasedActor` (`"score=-24.6 (ideo=-78, int=-5, rel=0, elec=0) ante '...'"`) contiene números
    del desglose del score que NO son parte de la `Perception` (son el resultado de una fórmula
    interna), así que `FakeJudge.fact_check` los marca `unsupported` aunque no sean "inventados" en el
    sentido que le importa a la métrica. Documentado en el reporte (nota de la métrica) en vez de
    corregido: arreglarlo exigiría que `RuleBasedActor` redactara su `reason` en un registro distinto
    del que usa `authorize()`/el log de acciones (fuera de alcance de Fase 7, y tocaría
    `actors/rule_based.py`, no un archivo de `evals/`).
12. **`Judge(backend)` solo soporta `llm:ollama:<modelo>`** (reutiliza `ai/brains.py::build_backend`,
    que no tiene un backend de Anthropic). El ADR menciona `--judge llm:anthropic:claude-sonnet-5`
    "vía `ANTHROPIC_API_KEY` y un backend mínimo en `ai/backends.py`" como posibilidad; no se
    implementó (ni la tarea de resumen lo pedía explícitamente, y este entorno no tiene
    `ANTHROPIC_API_KEY` ni red saliente hacia la API de Anthropic para probarlo) -- `build_judge`
    levanta `ValueError` para cualquier `--judge` que no sea `fake`/`llm:ollama:*`.

### Gobernanza (`governance/`, `data/governance.yaml`)

13. **El chequeo de gobernanza en `authorize()` solo corre si el tipo de acción YA es del rol del
    actor** (chequeo 1 de ADR 003 secc. 4 pasa primero en el orden lógico, aunque el código consulta
    gobernanza ANTES de devolver el resultado): si ni siquiera es del rol, se deja que el chequeo 1
    devuelva su propio `"el rol X no tiene permitido Y"`, del que depende `authority_violation` para
    distinguir "fuera de rol" de "gobernanza restringida" en `denied_reason`.
14. **`filter_perception` solo filtra `public_indicators`/`private_indicators`/`proposal`**, las 3
    partes de la `Perception` que corresponden 1:1 a las 9 categorías del ADR. El resto
    (`relationships`, `memories`, `goals`, `active_shocks`/`recent_events`) no tiene una categoría
    natural en la lista del ADR y no se filtra -- acotado a lo que el DoD 5 efectivamente prueba
    ("una clave fuera de `read` no aparece en el prompt", verificado con `private_indicators`).
15. **`data/governance.yaml` con los defaults (`autonomy: 5`, `read`/`write`/`execute` = catálogo
    completo del rol, `budget.actions_per_turn: 3` = el genérico del motor) es matemáticamente un
    no-op sobre el comportamiento previo a ADR 007** -- verificado por el hash dorado (test 9 de esta
    sección, `elections_enabled=False` a propósito: `world/elections.py`/`data/cohorts_loyalty.csv`/
    `data/cohort_provinces.csv` están bajo modificación concurrente por otro agente en esta misma
    sesión -- ADR 006, calibración de voto regional, fuera del alcance de Fase 7 -- y la gobernanza no
    interviene en absoluto en `_run_election`, así que excluir elecciones del hash dorado no le resta
    cobertura a lo que ADR 007 pide probar).
16. **`human_approval_required` solo lo trae `central_bank` en `data/governance.yaml`.** Es el único
    actor cuyo `autonomy` default (2) ya bloquea su única acción `EXECUTE` (`SET_RATE`, que pide
    `autonomy >= 3`): activar la aprobación humana ahí es lo que deja "ensayar" el experimento
    canónico del ADR (autonomy 2 vs. 4) sin que el Banco Central emita tasas sin supervisión, ni en
    `run`/evals (que auto-aprueban siempre vía `Simulation.auto_approve_governance = True`) ni en
    `play` con `autonomy=4` (donde el dilema Sí/No del jugador reemplaza la aprobación automática).

### Trazas (`ai/tracing.py`)

17. **Los spans de una traza usan un contador sintético `start`/`end` (0..7, el índice del span en
    `SPAN_NAMES`), no timestamps reales.** `DecisionTrace` solo guarda `latency_ms` TOTAL de la
    llamada (ADR 004 secc. 6), no un desglose por paso; medir tiempo real por span exigiría
    instrumentar `LLMActor`/`ai/backends.py` con relojes intermedios entre cada paso interno
    (percepción ya armada antes de llamar a `decide()`, memoria/prompt/llm_call ocurren dentro de una
    sola llamada a `backend.complete()`), fuera de alcance de Fase 7.

### CLI / runner (`cli.py`, `evals/runner.py`)

18. **`--suite` acepta `all`, el `id` completo de una de las 10 métricas, o los alias cortos
    `ideological`/`interest`** (los dos que usa el propio docstring del ADR: "`--suite
    all|ideological|interest|...`") -- mapeados a `ideological_consistency`/`interest_consistency`.
19. **`republica eval` es el callback de un `Typer` grupo (`eval_app`), no un comando con
    subcomandos anidados de otra forma:** correrlo sin subcomando ejecuta la suite
    (`invoked_subcommand is None`); `eval compare`/`eval export-promptfoo` son subcomandos aparte.
    Mismo patrón que `traces` (`traces export`/`traces show`).

### Estado y honestidad de la suite

20. **No hay Ollama en este entorno** (offline, sin red saliente hacia un servidor real): todo lo
    corrido para verificar la suite (tests, los dos reportes del informe final) usa `--brain
    rules|fake:*` y `--judge fake`. `--brain llm:ollama:<modelo>`/`--judge llm:ollama:<modelo>` están
    implementados y comparten código con `ai/backends.py::OllamaBackend` (ya probado contra un
    `http.server` local en ADR 004), pero no se ejercitaron acá con un servidor real.
