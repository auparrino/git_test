# ADR 004 — Capa de IA: esquemas, prompts, visibilidad y cliente Ollama (Fase 4)

Estado: aceptado para implementar. Depende de ADR 003.

## 1. Decisión

Un actor IA es un `Actor` con `brain = "llm:<backend>:<model>"` que implementa la **misma interfaz**
que `rule_based`: `decide(Perception) -> list[Action]`. El LLM nunca ve `WorldState`, solo la
`Perception` de su rol; nunca devuelve código ni funciones, solo un `ActorDecision` validado contra un
JSON Schema. La conversión `ActorDecision → list[Action]` es determinista y vive en el motor.

```
Perception ──render_prompt(role)──▶ prompt ──backend.complete(schema)──▶ JSON
        ──ActorDecision.model_validate──▶ decision ──to_actions()──▶ Action[] ──authorize()──▶ ...
```

## 2. Backends (`ai/backends.py`)

```python
class LLMBackend(Protocol):
    name: str
    def complete(self, *, system: str, user: str, schema: dict, temperature: float, seed: int) -> LLMResult
```
- `OllamaBackend(model, host="http://localhost:11434")`: `POST /api/chat` con `format=<json schema>`,
  `options={"temperature", "seed", "num_predict"}`, `stream=False`. Reintento ×2 en error de parseo con
  el error añadido al prompt. Timeout 60 s. `urllib` de stdlib (sin dependencia nueva).
- `FakeBackend(policy)`: para tests y para este entorno sin Ollama. `policy` puede ser
  `"rules"` (delega al actor por reglas y serializa su decisión, así los tests del pipeline completo
  corren sin LLM), `"scripted"` (respuestas fijas por actor/mes), `"malformed"` (devuelve JSON roto
  para probar reintentos) o `"unauthorized"` (devuelve acciones fuera de rol para probar `authorize`).
- `CachedBackend(inner, path)`: cache en disco por `sha256(model + system + user + schema + seed)`.
  Obligatorio en experimentos (Fase 8) para reproducibilidad y para no volver a pagar tokens.

`LLMResult`: `text, parsed: dict | None, model, digest, prompt_tokens, completion_tokens, latency_ms, attempts`.

## 3. Esquema de salida (`ai/schemas.py`)

```python
class ActorDecision(BaseModel):
    position: Literal["support", "oppose", "negotiate", "neutral"]
    intensity: float = Field(ge=0, le=1)
    public_message: str = Field(max_length=280)
    private_strategy: Literal["cooperate", "pressure", "wait", "escalate"]
    actions: list[ActionRequest] = Field(max_length=3)
    requested_concession: ConcessionType | None = None
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(max_length=600)


class ActionRequest(BaseModel):
    type: str  # se valida contra el catálogo DESPUÉS, en authorize (no en el schema)
    params: dict[str, float | str | int] = {}
    target: str | None = None
```

Deliberadamente `type` es `str` y no un `Literal` del catálogo del rol: queremos **medir** cuántas
veces el modelo intenta acciones que no le corresponden (`authority_violation`), no impedírselo por
construcción. El JSON Schema que se envía a Ollama es `ActorDecision.model_json_schema()`.

`to_actions(decision, actor)`:
1. `PUBLIC_STATEMENT(stance=position, intensity)` si `public_message` no está vacío.
2. `SUPPORT_POLICY / OPPOSE_POLICY / NEGOTIATE(requested_concession)` según `position`.
3. Cada `ActionRequest` → `Action` (params validados por el esquema de ese tipo; si no validan, se
   genera igual y `authorize` la deniega con `reason="invalid_params"`).
Máximo 3 acciones por turno (ADR 003 §4); las sobrantes se descartan y se registran.

## 4. Prompts (`ai/prompts.py`)

Un `system` por rol y un `user` renderizado desde `Perception` con plantillas Jinja-like simples
(`str.format` con secciones opcionales; sin dependencia nueva). Reglas:

- **Solo lo que la `Perception` contiene.** El renderer no tiene acceso al estado. Test: el prompt
  de un gobernador no contiene el valor exacto de `reserves` si `reserves` no está en sus
  `private_indicators`.
- **Idioma:** español rioplatense en los mensajes públicos; el `reasoning` puede ser en cualquier idioma.
- **Estructura del user prompt:**
  ```
  FECHA / MESES HASTA LA ELECCIÓN
  INDICADORES PÚBLICOS (tabla)
  TU SITUACIÓN (private_indicators, en lenguaje del rol)
  PROPUESTA DEL GOBIERNO (o "no hay propuesta este mes")
  SHOCKS ACTIVOS / EVENTOS RECIENTES
  TUS OBJETIVOS (goals, numerados)
  TUS RELACIONES (solo las propias, con etiqueta: hostil < 35, fría, neutral, buena > 65)
  MEMORIAS RELEVANTES (Fase 6; vacío ahora)
  ACCIONES DISPONIBLES PARA TU ROL (lista con params)  ← se incluye, pero authorize sigue mandando
  INSTRUCCIÓN: respondé solo con el JSON del esquema.
  ```
- **System prompt por rol:** identidad (nombre, rol, provincia/partido), ideología en palabras
  (mapeo de los 4 ejes a frases), personalidad en palabras, y tres reglas: no inventar hechos que no
  estén en el mensaje, no prometer lo que el rol no puede ejecutar, dar una razón concreta.
- Versionado: `PROMPT_VERSION = "v4.0"` en cada traza; cualquier cambio de plantilla lo incrementa.

## 5. Visibilidad por rol (`engine/perception.py`, completa ADR 003 §3)

| Rol | `private_indicators` |
|---|---|
| president, economy_minister | todo el estado + policy actual + deficit + reserves exactas |
| central_bank | reserves exactas, exchange_rate, inflation_lag1, intervention del mes, deuda |
| governor | `unemployment_p`, `income_p`, `transfers_received`, `dependence`, shocks que afectan su provincia |
| party | `seats`, `congress_support`, `approval`, `months_to_election`, encuestas (= approval ± ruido 3) |
| union | `real_wage`, `unemployment`, `inflation`, `protest_level`, `public_employment` (si es estatal) |
| business | `gdp_growth`, `interest_rate`, `exchange_rate`, `tax_rate`, `consumer_confidence`, su sector |
| media | `approval`, `protest_level`, eventos del mes, `institutional_confidence` |
| social_bloc | `real_wage`, `unemployment`, `poverty`, `inflation`, `crime_perception` |

Los `public_indicators` son los 8 del tablero con **redondeo** (inflación a 0.1, reservas a centenas)
para que el modelo no vea más precisión de la que un actor real tendría.

## 6. Trazas (`ai/tracing.py`)

Cada llamada produce un `DecisionTrace` (una línea JSONL, `kind: "trace"`):
```
run_id, month, actor_id, brain, prompt_version, model, digest, temperature, seed,
perception (dict), system, user, raw_response, parsed (ActorDecision | null), parse_error,
attempts, actions_emitted, actions_authorized, actions_denied (con reason), consequences,
latency_ms, tokens
```
Fase 7 exporta estas líneas a Langfuse; en v0.3 alcanza con el JSONL. Un `eval_score` vacío queda
reservado.

## 7. Configuración de cerebros

`data/brains.yaml` (o `--brain` en CLI):
```yaml
default: rules
actors:
  president: rules
  minister_economy: llm:ollama:qwen3:8b
  gov_norte: llm:ollama:qwen3:8b
llm:
  temperature: 0.4
  cache: simulations/cache/
```
`--brain rules` fuerza reglas para todos (baseline). `--brain fake:rules` usa el `FakeBackend` con
delegación a reglas: **misma tubería completa, cero LLM**, y es lo que corre en CI.

## 8. CLI

- `republica run --seed 7 --brains data/brains.yaml` (o `--brain llm:ollama:qwen3:8b` para todos).
- `republica bench-parse --brain llm:ollama:qwen3:8b --n 50 --role governor`: renderiza 50
  percepciones reales (de una corrida por reglas) y mide `parse_rate`, `authority_violation_rate`,
  latencia p50/p90, tokens. Umbral de Fase 4: `parse_rate ≥ 0.95`.
- `republica compare --seed 7 --a rules --b llm:ollama:qwen3:8b --actor gov_norte`: corre ambas y
  muestra, mes a mes, posición/intensidad/acciones de ese actor en cada una, lado a lado.

## 9. Tests (DoD de Fase 4, ejecutables sin Ollama)

1. `FakeBackend("rules")`: 48 meses con 3 actores `llm:fake:rules` producen exactamente las mismas
   acciones autorizadas que `rules` (la tubería no altera nada).
2. `FakeBackend("malformed")`: reintenta 2 veces, registra `parse_error`, y el actor cae a
   `NO_ACTION` sin romper la corrida.
3. `FakeBackend("unauthorized")`: las acciones fuera de rol se denieguen y aparecen en la traza.
4. Visibilidad: el prompt del gobernador no contiene `reserves` exactas; el del BC sí.
5. `CachedBackend`: segunda llamada idéntica no invoca al backend interno.
6. `OllamaBackend` contra un servidor HTTP falso en `localhost` (thread + `http.server`) que devuelve
   un JSON fijo: verifica el request (`format`, `options.seed`) y el parseo.
7. Ninguna mutación de estado ocurre fuera de `engine/` (reutiliza el test de ADR 003).
