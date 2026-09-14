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
