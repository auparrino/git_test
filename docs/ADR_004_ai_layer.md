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

## 10. Notas de implementación (Fase 4)

Ambigüedades, decisiones de diseño y desviaciones al implementar `ai/backends.py`, `ai/schemas.py`,
`ai/prompts.py`, `ai/tracing.py`, `ai/brains.py`, `actors/llm_based.py` y la integración en
`engine/scheduler.py`, `engine/simulation.py`, `engine/game.py` y `cli.py`. Todo lo corrido para
verificarlas usa `fake:*`/`OllamaBackend` contra un `http.server` local: no hay Ollama real en este
entorno ni red hacia él.

### Backends

1. **`LLMBackend.complete()` gana tres parámetros opcionales sobre la firma literal del ADR**:
   `actor_id: str = ""`, `perception: Perception | None = None`, `rng: random.Random | None = None`
   (`ai/backends.py`). Hacen falta para que `FakeBackend(policy="rules")` pueda cumplir la sección 2
   ("delega al actor por reglas y serializa su decisión"): sin ellos, `complete()` solo ve texto ya
   renderizado (`system`/`user`), no la `Perception` estructurada ni el `actor_id` que necesitaría
   para reconstruir un `RuleBasedActor` y llamar a `decide()`. `OllamaBackend`/`CachedBackend` los
   aceptan pero no los usan (un backend real no necesita la `Perception`, solo el prompt ya
   renderizado); `CachedBackend` los reenvía al backend interno tal cual pero **no** los incluye en la
   clave de cache (la clave sigue siendo exactamente `sha256(model+system+user+schema+seed)`, literal
   del ADR).
2. **`LLMActor` no consume el `rng` del actor para derivar el `seed` que le pasa a `backend.complete()`.**
   La semilla sale de `zlib.crc32(f"{seed_base}:{month}")` (`actors/llm_based.py::_derive_call_seed`),
   no de `rng.getrandbits(...)`. Es necesario para el test de aceptación 1: si `LLMActor.decide()`
   consumiera el `rng` compartido del actor antes de delegar en `FakeBackend("rules")` (que sí necesita
   consumir ese mismo `rng` para llamar a `RuleBasedActor.decide()` con exactamente la misma secuencia
   de azar que una corrida `rules` pura), las dos secuencias divergirían a partir del segundo mes y
   `fake:rules` dejaría de producir "exactamente las mismas acciones" que `rules`.
3. **`FakeBackend(policy="rules")` reconstruye un `RuleBasedActor` por actor (cacheado en la instancia)
   y llama a `decide(perception, rng)` real**, después convierte la `list[Action]` resultante a un
   payload de `ActorDecision` (`ai/backends.py::_actions_to_decision_payload`, el inverso aproximado de
   `to_actions`). No hay otra forma de "delegar en el actor por reglas y serializar su decisión" sin
   tener acceso a la decisión real. El campo `offer` de un eventual `NEGOTIATE` no se reconstruye
   idéntico al literal `"apoyo condicionado"` que usa `RuleBasedActor` (se pierde en la ronda de ida y
   vuelta); no importa para el test de aceptación 1 porque compara acciones autorizadas sin ese campo
   de texto libre (ver punto 8).
4. **`FakeBackend(policy="malformed")` no reintenta de verdad.** Devuelve directamente
   `parsed=None, attempts=1+MAX_PARSE_RETRIES` (3): es un backend fake sin red, reintentar de verdad
   no agregaría información (siempre va a fallar); lo que importa para el test de aceptación 2 es que
   `LLMActor` vea el mismo `LLMResult` final (`parsed=None`, `attempts=3`) que produciría un
   `OllamaBackend` real que reintentó dos veces y siguió sin poder parsear.
5. **`FakeBackend(policy="unauthorized")` devuelve un `governor`→`STRIKE` o un `media`→`SET_RATE`**
   según si `"media"` aparece en el `actor_id` (los dos ejemplos literales del ADR secc. 2); cualquier
   otro rol recibe el caso `STRIKE`. No cubre los 9 roles individualmente (no hace falta: el objetivo
   del test de aceptación 3 es probar que `authorize()` deniega una acción fuera de rol y que la
   denegación llega a la traza, no enumerar las 9 combinaciones posibles).
6. **`OllamaBackend(model, host=None)` lee `OLLAMA_HOST` del entorno si no se pasa `host` explícito**
   (default final `http://localhost:11434` si tampoco está seteada) — no está en la firma literal del
   ADR (`host="http://localhost:11434"`), se agrega porque el deliverable de `docs/OLLAMA_SETUP.md`
   pide explicar "cómo setear `OLLAMA_HOST`", y sin esto no haría nada.
7. **`OllamaBackend` no distingue un error de red de un error de parseo.** El ADR solo especifica
   reintento "en error de parseo"; un `URLError`/timeout se propaga tal cual (no hay reintento, no hay
   fallback) — no hay señal en el ADR de que un error de conexión deba tratarse igual que una
   respuesta mal formada, y silenciarlo devolviendo `NO_ACTION` ocultaría un problema de
   infraestructura (Ollama caído, host mal configurado) detrás de una métrica de `parse_rate`.

### Esquema y conversión

8. **Orden de salida de `to_actions()` distinto del orden 1/2/3 literal del ADR.** El ADR numera las
   3 reglas de conversión (declaración pública, acción de posición, pedidos de acción) pero no dice en
   qué orden queda la lista final; `to_actions()` (`ai/schemas.py`) arma
   `[acción de posición, *pedidos de acción, declaración pública]` — postura primero, escalada
   después, declaración al final — porque es el mismo orden en que `RuleBasedActor._decide_generic`
   arma su propia lista (ADR 003 secc. 6). Importa para el tope de 3 acciones: con este orden, cuando
   sobran acciones se descarta la declaración pública primero, exactamente como descartaría
   `authorize_all` la cuarta acción de un actor por reglas que llega al presupuesto de turno
   (`engine/permissions.py::ACTION_BUDGET_PER_TURN`, ADR 003 secc. 4/9) — necesario para que el test
   de aceptación 1 valga incluso en el caso `governor` opositor con escalada (`OPPOSE_POLICY` +
   `LOBBY_CONGRESS` + `REQUEST_FUNDS` + `PUBLIC_STATEMENT`, 4 candidatas).
9. **Un `ActionRequest.type` que no es ningún `ActionType` del catálogo se descarta en `to_actions()`**
   (con `logger.info`), no llega a `authorize()`. `ActionRecord` (ADR 003 secc. 8) da por sentado
   `action.type.value` al loguear cada acción; un `str` arbitrario no tiene ese atributo y rompería la
   corrida. Un `type` que **sí** es un `ActionType` real pero de otro rol (el caso que mide
   `authority_violation`, el propósito declarado de que `type` sea `str` libre) sí llega a
   `authorize()` sin tocar, vía `Action.model_construct` (bypassea la validación de `params` del
   constructor normal de `Action`, que si no el ADR pide "params inválidos → se genera igual y
   `authorize()` la deniega" sería imposible: el constructor normal de `Action` levanta
   `pydantic.ValidationError` en vez de construir la acción).
10. **`position="negotiate"` sin `requested_concession` cae a `ConcessionType.DELAY_POLICY`** (no hay
   default "genérico" en el ADR); es la misma concesión que `RuleBasedActor` usa para
   `economy_minister` (`_NEGOTIATE_CONCESSION`, ADR 003 secc. 11 punto 23), la menos "regalada" de las
   6. `position="negotiate"` también mapea a `stance="neutral"` en el `PUBLIC_STATEMENT` que arme la
   regla 1 (no "negotiate", que no es un valor válido de `PublicStatementParams.stance`): mismo mapeo
   que ya hace `RuleBasedActor._decide_generic`, que deja `stance = "neutral"` tanto en el caso
   "negocia" como en el caso "no hace nada" (ver ADR 003 secc. 11 puntos 20/23).

### Prompts

11. **Umbrales de las frases de ideología/personalidad (`±0.3`, `0.4/0.6`) inventados**, documentados
    inline en `ai/prompts.py`, del mismo orden que otros umbrales "tibio/marcado" ya inventados en el
    proyecto (ADR 003 secc. 11 punto 1: revisión v0.3 de `ideological_fit`).
12. **Corte `fría`/`neutral` en las etiquetas de relación inventado en 50** (el ADR da "hostil < 35,
    fría, neutral, buena > 65" sin el corte intermedio): se usa el punto medio de la ficha (el default
    de `ActorSheet.relationship`, ADR 003 secc. 2) como frontera.
13. **`allowed_actions` (la sección "ACCIONES DISPONIBLES") no sale de la `Perception`, sale de la
    matriz de permisos del rol** (`engine/permissions.py::load_permissions()`), pasada aparte a
    `render_user(perception, allowed_actions)`. No contradice "el renderer solo usa la `Perception`"
    (ADR secc. 4/9, test de visibilidad): la matriz de permisos no es información de estado del mundo,
    es una propiedad estática del rol, igual de visible para un actor real que las reglas del juego
    mismo.

### `LLMActor` y trazas

14. **`LLMActor.last_score` existe y vale siempre `None`.** Es puro carril de paridad de interfaz con
    `RuleBasedActor.last_score` (ADR 003 secc. 11 punto 27): `engine/scheduler.py` lee
    `getattr(decision_actor, "last_score", None)` sin distinguir el tipo del actor, y un `LLMActor` no
    calcula ningún `ScoreBreakdown`.
15. **`DecisionTrace.run_id`/`actions_authorized`/`actions_denied`/`consequences` quedan vacíos al
    construirse en `LLMActor.decide()`** y los completa `engine/scheduler.py::run_actor_turn` después
    de `authorize_all`/`apply_consequences` (mismo patrón que `last_score`, punto 13 arriba): en el
    momento en que el actor decide, ninguno de esos cuatro datos existe todavía.

### Cerebros (`ai/brains.py`, sección 7 del ADR)

16. **`ai/brains.py` es un módulo nuevo, no uno de los 4 que pide el deliverable 1 del ADR.** Hace
    falta un lugar central para parsear specs de cerebro (`"rules"`, `"fake:<policy>"`,
    `"llm:ollama:<modelo>"`) y cargar `data/brains.yaml`/`--brains` sin duplicar ese parseo entre
    `engine/scheduler.py` y `cli.py`.
17. **`ActorEngine.rule_actors` se renombra a `decision_actors`** (`RuleBasedActor | LLMActor`, tipo
    `DecisionActor`) en vez de agregar un diccionario paralelo: cada actor tiene exactamente un
    cerebro, no dos. Nada fuera de `engine/scheduler.py` leía `rule_actors` (solo lo usaba
    `run_actor_turn`), así que el rename no rompe ningún llamador existente.
18. **`run_actor_turn()` mantiene su firma de 2-tupla `(records, pending_terms)`** — no devuelve las
    trazas del mes. Se guardan en `engine.last_traces` (mismo patrón que `engine.last_records`, ya
    existente) y `engine/simulation.py::advance_month` las junta en `sim.trace_records`. Cambiar la
    firma habría roto `tests/test_actors.py::test_adding_a_new_actor_does_not_change_existing_actors_first_month`
    (llama a `run_actor_turn` directo y desempaqueta 2 valores) sin necesidad: el mismo patrón que ya
    usa `last_records` alcanza.
19. **Traza solo si el actor usa un cerebro no-`"rules"`.** Con `default_brain="rules"` (el default de
    todo, ADR 004 secc. 7) ningún actor genera `DecisionTrace`, `History.trace_records` queda vacío y
    `to_jsonl()` produce exactamente el mismo texto que antes de ADR 004 — igual que ya garantizaba
    ADR 003 secc. 11 punto 6 para `action_records`. Verificado corriendo los 64 tests de Fases 1-3 sin
    tocarlos.
20. **`republica play --load` no restaura `brain_map`/`default_brain`.** `Game.save()` no persiste la
    configuración de cerebros (solo `actors_enabled`); `Game.load()` siempre reconstruye con el default
    `"rules"`. Fuera de alcance de Fase 4 (el ADR no menciona guardar/cargar cerebros); una partida
    jugada con actores IA y después cargada vuelve a actores por reglas. Se
    documenta acá para que no sorprenda en Fase 6/8 cuando se retome `play`.

### CLI

21. **`bench-parse` no arma percepciones sintéticas: corre una simulación real donde todos los actores
    son `"rules"` salvo el primero (orden alfabético de id) que tenga `role == --role`, al que se le
    asigna `--brain`.** Es lo más simple que cumple "perceptions reales... de una corrida por reglas"
    (ADR 004 secc. 8) sin reimplementar un trozo de `advance_month` para reconstruir percepciones
    históricas fuera de una corrida real. `--n` es la cantidad de meses (y por lo tanto de trazas: el
    actor elegido decide una vez por mes).
22. **`authority_violation_rate` en `bench-parse` cuenta acciones denegadas cuya `denied_reason`
    contiene el literal `"no tiene permitido"`** (el mensaje exacto que arma
    `engine/permissions.py::authorize`, chequeo 1), sobre el total de acciones emitidas por el actor
    en la corrida — no distingue esa denegación de otras (`invalid_params`, cooldown, presupuesto): el
    ADR no da una fórmula exacta, solo el nombre de la métrica (secc. 8).
23. **`compare --a`/`--b` son el `default_brain` de TODA la corrida (los 28 actores no-presidente),
    no solo de `--actor`.** Correr dos simulaciones completas es más caro que una sola con el cerebro
    bajo prueba solo en `--actor`, pero es lo que permite que las relaciones/consecuencias del actor
    comparado reaccionen igual en ambas corridas a lo que hacen los demás — comparar un actor aislado
    del resto del mundo sería menos representativo.
