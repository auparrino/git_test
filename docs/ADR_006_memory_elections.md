# ADR 006 — Memoria de actores y elecciones (Fase 6)

Estado: aceptado para implementar. Depende de ADR 003–005.

## 1. Memoria (`ai/memory.py`)

### 1.1 Qué se recuerda
El motor genera `MemoryEvent` para cada actor **afectado** (no todos ven todo):

| Fuente | Evento | Actores que lo reciben | importance | sentiment |
|---|---|---|---|---|
| Acuerdo cumplido | `agreement_honored` | contraparte | 0.6 | +0.6 |
| Acuerdo roto por gobierno | `agreement_broken_by_government` | contraparte, partidos aliados | 0.9 | −0.8 |
| Acuerdo roto por actor | `agreement_broken_by_actor` | presidente, ministro | 0.8 | −0.7 |
| Concesión recibida | `concession_received` | receptor | 0.5 | +0.5 |
| Pedido rechazado | `request_refused` | solicitante | 0.5 | −0.4 |
| Ley clave votada | `voted_for` / `voted_against` | presidente, partido, gobernadores del partido | 0.5 | ±0.4 |
| Huelga / protesta | `strike_called`, `protest_called` | presidente, empresas, medios | 0.6 | −0.5 (presidente) |
| Ataque público | `criticized_by`, `endorsed_by` | objetivo | 0.4 | ∓0.4 |
| Shock que golpeó su provincia/sector | `shock_hit` | gobernador, empresa, cohorte | 0.7 | −0.5 |
| Devaluación / colapso | `forced_devaluation` | todos | 0.8 | −0.6 |
| Promesa pública | `promised` (de `public_message` con verbo de compromiso) | emisor y audiencia | 0.6 | 0 |

```python
class MemoryEvent(BaseModel):
    turn: int
    actor: str
    about: str | None
    kind: str
    summary: str  # una frase, en español, con nombres propios
    importance: float  # [0, 1]
    sentiment: float  # [−1, 1]
```

### 1.2 Almacenamiento y recuperación
`MemoryStore` por actor, lista en memoria + JSONL (`kind: "memory"`). Recuperación para un prompt o una
decisión por reglas:
```
score = 0.5 · importance + 0.3 · recency + 0.2 · relevance
recency   = exp(−(turn_now − turn) / 12)
relevance = 1 si `about` ∈ {contraparte de la propuesta, actores mencionados}; 0.5 si mismo `kind` que la situación; 0 si no
```
Se devuelven las `k = 5` mejores, ordenadas por turno, como frases. Presupuesto de tokens: 400.

### 1.3 Efecto en actores por reglas
`w_mem · Σ sentiment_i · importance_i · recency_i` (sobre memorias con `about = president`) se suma al
`score` de ADR 003 §6, con `w_mem = 0.15` (rango [−100, 100] tras escalar por 100). Un acuerdo roto reciente
baja el score en ≈ −10 durante meses. Además `trust_president = 50 + 30 · tanh(Σ ...)` reemplaza el decaimiento
de relaciones hacia 50 de ADR 003 §5 cuando `features.memory = true`.

### 1.4 Consolidación
Cada 12 turnos, las memorias con `importance < 0.5` y `turn < now − 12` se resumen en una sola
`MemoryEvent(kind="summary")` por contraparte (por reglas: conteo de positivos/negativos → frase
plantilla; con LLM: el mismo backend del actor, prompt de resumen, máx. 60 palabras). Ninguna memoria
con `importance ≥ 0.8` se resume nunca.

---

## 2. Elecciones (`world/elections.py`)

### 2.1 Cuándo
Mes 48 de cada mandato (`term_length` en `country.json`, default 48). La partida deja de terminar en el
mes 48: el `outcome` pasa a ser `reelected | defeated | collapse | hyperinflation`, y `run --months 96`
simula dos mandatos. La campaña ocupa los meses 45–48: `campaign_effect` activo.

### 2.2 Intención de voto por cohorte y partido
```
util_c,p = v_econ · econ_vote_c                     · [p es oficialismo]      # voto económico
         + v_ideo · (1 − |econ_pref_c − ideology_p.economic|)                 # afinidad
         + v_appr · (approval_c − 50)/50            · [p es oficialismo]      # aprobación
         + v_loy  · loyalty_c,p                                               # lealtad (data/cohorts_loyalty.csv, inicial)
         + v_reg  · regional_bonus_c,p                                        # gobernadores del partido con approval alta en la región
         + v_camp · campaign_p                                                # gasto/foco de campaña (acción CAMPAIGN, Fase 6)
         + v_evt  · recent_events_c                                           # shocks/escándalos últimos 6 meses (memoria de cohorte)
econ_vote_c = tanh((Δreal_wage_12m · s_w_c − Δunemployment_12m · s_u_c − pos(perceived_inflation_c − 2) · s_pi_c) / 10)
share_c,p = softmax_p(util_c,p / τ)                  # τ = 0.35
vote_p = Σ_c pop_share_c · turnout_c · share_c,p  (+ ruido N(0, 1.5) por partido, renormalizado)
```
Pesos por defecto: `v_econ 0.35, v_ideo 0.25, v_appr 0.15, v_loy 0.15, v_reg 0.05, v_camp 0.03, v_evt 0.02`.

### 2.3 Sistema electoral (v0.5: uno solo; parametrizable en Fase 8+)
Presidencial a dos vueltas: gana en primera vuelta con > 45 % o > 40 % y 10 pp de ventaja; si no,
balotaje entre los dos primeros con transferencia de votos por afinidad ideológica
(`share_second = softmax` sobre los dos con `τ = 0.5`). Congreso: 100 bancas por proporcional
(D'Hondt) sobre `vote_p`, umbral 3 %.

### 2.4 Transición de gobierno
- Ganador ≠ oficialismo: `president` cambia de partido, `minister_economy` se reemplaza por una ficha
  del nuevo partido (`data/actors/ministers/<party>.yaml`), `in_government` se actualiza, la `Policy`
  arranca en el default, `approval` inicial = `vote_p` del ganador + 8 (luna de miel), relaciones del
  nuevo presidente = las del partido.
- Los demás actores **persisten con su memoria**. Memorias `about = president` se re-etiquetan como
  `about = former_president_<party>`; siguen contando para el partido.
- Ganador = oficialismo: `approval = vote_p + 5`, todo sigue.
- `ElectionRecord` (JSONL `kind: "election"`): intención por cohorte, resultado, balotaje, bancas.

### 2.5 Reglas de campaña (acciones nuevas, ADR 003 §4)
`CAMPAIGN(focus: cohort_id | all, intensity)`: president y parties, solo meses 45–48; efecto
`campaign_p += 0.5 · intensity` (concentrado en `focus`). `PROMISE(text, target: cohort_id)`:
genera memoria `promised` para la cohorte; si en los 6 meses posteriores a la elección el
`policy_direction` contradice la promesa (firma económica opuesta), memoria `promise_broken`
(importance 0.8, −0.7) para esa cohorte → `loyalty −0.1`.

---

## 3. Tests (DoD de Fase 6)
1. Acuerdo roto en el turno 17 aparece entre las 5 memorias recuperadas de `gov_norte` en el turno 20 y
   su `score` de negociación es menor que en el contrafáctico sin ruptura.
2. Consolidación: tras 24 turnos con 30 memorias menores, el store tiene ≤ 12 entradas y ninguna
   `importance ≥ 0.8` fue resumida.
3. Cohortes homogéneas y partidos con la misma ideología → `vote_p` ≈ uniforme (±3 pp).
4. Elección con `approval = 65` durante 12 meses → oficialismo gana en ≥ 90 % de 100 semillas;
   con `approval = 25` → pierde en ≥ 90 %.
5. Balotaje: con tres partidos en 38/33/29 se dispara segunda vuelta y el resultado es determinista por semilla.
6. Transición: tras derrota, `president.party` cambia, `gov_norte` conserva sus memorias, y el nuevo
   presidente no hereda `agreements` del anterior.
7. `run --months 96` completa dos mandatos con todos los features; el JSONL tiene 2 `election` records.

---

## 4. Notas de implementación (Fase 6)

Ambigüedades, decisiones de diseño y desviaciones al implementar `ai/memory.py`, `world/elections.py`,
`data/cohorts_loyalty.csv`, `data/actors/ministers/*.yaml`, y la integración en `actors/rule_based.py`,
`ai/backends.py`, `ai/brains.py`, `ai/tracing.py`, `actors/llm_based.py`, `engine/perception.py`,
`engine/scheduler.py`, `engine/permissions.py`, `engine/actions.py`, `engine/simulation.py`,
`engine/game.py`, `engine/narrate.py`, `ui/viewer.py`, `world/config.py` y `cli.py`.

### Memoria

1. **`generate_month_memories()` es un único punto de entrada, no hooks esparcidos por el motor.**
   El encargo pedía "hook into the places where..."; en la práctica, `engine/simulation.py::
   advance_month` ya reúne, al final de cada mes, todo lo que las 11 filas de la tabla de secc. 1.1
   necesitan (`ActionRecord`s, los eventos `agreement_honored`/`agreement_broken:*` de
   `engine/negotiation.py`, el `VoteRecord`, el `ShockAggregate`, el evento de devaluación forzada).
   Centralizar la generación en una función pura (`ai/memory.py::generate_month_memories`, llamada una
   vez por mes) cubre la tabla completa con mucha menos superficie de cambio en Congreso/negociación/
   consecuencias que esparcir `store.add(...)` en cada uno de esos módulos, y es más fácil de testear
   (los tests de aceptación construyen un `MemoryContext` a mano, sin correr una simulación completa).
2. **Presupuesto de 400 "tokens" de la sección 1.2 se interpreta como 400 caracteres.** El proyecto no
   tiene un tokenizer (ni de OpenAI ni de ningún LLM real: `ai/backends.py` manda texto plano a Ollama);
   aproximar 1 token ≈ 1 carácter es conservador (sobrestima cuánto se recorta) pero es lo único
   verificable sin una dependencia nueva.
3. **`about` de cada `MemoryEvent` es una convención por tipo, no está tabulada en el ADR.** Documentado
   inline en `ai/memory.py::generate_month_memories`: por ejemplo, el propio partido que votó una ley
   guarda `about=None` (memoria "sobre sí mismo" no tiene sentido), pero el presidente y los
   gobernadores de ese partido la guardan con `about=<party_id>`; un `criticized_by`/`endorsed_by` usa
   `about=<autor de la crítica>`, no el objetivo (que es el dueño de la memoria).
4. **`w_mem`/`trust_president` (secc. 1.3) modifican la *vista* de percepción, no `Relationships`.**
   Precisando la consigna del encargo: `Relationships` (el store del motor, ADR 003 secc. 5/11 punto 9)
   sigue siendo la única fuente persistente y sigue decayendo hacia 50/mes sin cambios. Lo que cambia,
   solo cuando `features.memory`, es `engine/perception.py::build_perception`: la entrada
   `relationships["president"]` que ve CADA actor (nunca la de otro actor sobre un tercero) se
   reemplaza por `MemoryStore.trust_president(actor.id, month)` antes de armar la `Perception`. Como
   `actors/rule_based.py::compute_score` lee `perception.relationships.get("president")` (nunca
   `Relationships` directo) para el término `w_rel`, ese término automáticamente pasa a usar
   `trust_president` sin duplicar ningún estado. El término `w_mem` (secc. 1.3, `Σ sentiment·importance·
   recency` sobre memorias `about="president"`, escalado `× w_mem × 100`) viaja aparte, en un campo
   nuevo `Perception.memory_score` (default `0.0`), y se suma en `compute_score` con un flag explícito
   `memory_enabled` (no inferido del valor de `memory_score`, que puede ser `0.0` legítimamente con la
   memoria prendida: ver el punto 5). **Nota importante:** `engine/congress.py::_rule_score` (el mismo
   score de ADR 003 secc. 6, pero re-implementado ahí para puntuar un `Bill` sin armar una `Perception`
   completa) NO se tocó — sigue usando el valor crudo de `Relationships`, sin `trust_president` ni
   `w_mem`. El ADR 006 secc. 1.3 dice literalmente "rule_based scoring" (`actors/rule_based.py`), y
   extenderlo a Congreso habría significado rehacer `_rule_score` para que reciba un `MemoryStore` y una
   `Perception` de partido — fuera de alcance para esta fase, documentado para Fase 7+.
5. **`ScoreBreakdown.mem`/`as_dict()["mem"]` solo existen con `features.memory = True`.** Necesario para
   el golden hash: si `mem` siempre apareciera en el diccionario (aunque fuera `0.0`), el `score` de
   cada `ActionRecord` cambiaría de forma incluso con la feature apagada, rompiendo el byte a byte
   idéntico con HEAD. `compute_score` recibe `memory_enabled: bool` explícito (no lo infiere), seteado
   una sola vez por actor al construir el `RuleBasedActor` (`memory_enabled` en su constructor, leído
   desde `Simulation.memory_enabled` vía `engine/scheduler.py::build_actor_engine` → `ai/brains.py::
   build_decision_actor`).
6. **`FakeBackend`/`build_backend` ganaron un parámetro `memory_enabled` (ai/backends.py, ai/brains.py)
   que no pedía ningún ADR anterior.** Sin él, `fake:rules` (que envuelve un `RuleBasedActor` real,
   ADR 004 secc. 2) construía ese `RuleBasedActor` con `memory_enabled=False` siempre, aunque la corrida
   tuviera `features.memory = True` — divergiendo de un `RuleBasedActor` "rules" directo (que sí ve el
   flag correcto) y rompiendo el test de aceptación 1 de ADR 004 en cuanto la memoria se prende. Se
   verifica con un test nuevo (`test_fake_rules_matches_rule_based_with_memory_enabled`).
7. **Consolidación (secc. 1.4) resume TODO grupo elegible, incluso de una sola memoria.** El ADR no
   pone un mínimo de memorias para resumir; se prefirió no ponerle uno a mano (documentado como
   simplificación): así el tamaño del store queda acotado de forma predecible (a lo sumo un `summary`
   por `(dueño, contraparte)` cada 12 turnos, más las memorias que todavía no llegaron a los 12 meses o
   tienen `importance ≥ 0.5`), en vez de depender de cuántas memorias menores se acumularon. Un
   `summary` ya existente nunca vuelve a resumirse (se excluye explícitamente por `kind != "summary"`),
   así que actúa como un contador acumulado permanente por contraparte, no se pierde información de
   "cuántas veces pasó" con el tiempo.
8. **Con los pesos por defecto del proyecto, casi ninguna fila de la tabla de secc. 1.1 tiene
   `importance < 0.5`** (solo `criticized_by`/`endorsed_by`, en 0.4): en una corrida real (`run --seed 7
   --policy taylor --months 96`, ver reporte final) la consolidación casi nunca encuentra candidatos
   (0 `summary` generados en esa corrida particular, porque ningún medio emitió `CRITICIZE`/`ENDORSE`).
   Es un resultado legítimo de los pesos literales del ADR, no un bug: el test de aceptación 2 se
   verifica con memorias sintéticas de `importance = 0.3`, no con una corrida completa.
9. **`promised` casi nunca se genera en `run` (reglas), porque el `reason` de un `PUBLIC_STATEMENT` por
   reglas es la frase formulaica de `_reason_text` ("score=... ante..."), nunca contiene un verbo de
   compromiso.** Es fiel a la letra del ADR ("de `public_message` con verbo de compromiso"): un actor
   por reglas no tiene `public_message` en lenguaje natural, solo un `LLMActor` (cuyo `reason` de
   `PUBLIC_STATEMENT` SÍ es el `public_message` real, ver `ai/schemas.py::_public_statement`) o la
   acción `PROMISE` (secc. 2.5, jugable en `play`) lo disparan de verdad.

### Elecciones

10. **`regional_bonus_c,p` (secc. 2.2) se deja en `0.0` para todas las cohortes.** `data/cohorts.csv`
    (ADR 005 secc. 3) no tiene una columna de provincia por cohorte, así que no hay forma de calcular
    "gobernadores del partido con approval alta en la región" de una cohorte sin inventar esa tabla de
    mapeo también. Con `v_reg = 0.05` (el peso más chico de los 7), el impacto de dejarlo en 0 es
    marginal; se documenta como el hueco más notorio de la fórmula.
11. **`recent_events_c` (secc. 2.2) se define como `-min(1, count/3)`**, con `count` = memorias de la
    cohorte con `sentiment < 0` en los últimos 6 meses (`ai/memory.py::MemoryStore.for_owner`, usando el
    `cohort_id` como "dueño" de memoria — el mismo `MemoryStore` sirve para actores y cohortes, sin una
    clase separada). El ADR no da una fórmula, solo la fuente ("memoria de cohorte"); se inventó una
    acotada a `[-1, 0]` del mismo orden que los demás términos del util (que están en `[-1, 1]` antes de
    los pesos).
12. **`turnout_c` vive en `data/cohorts_loyalty.csv` (columna `turnout`), no como constante global
    `0.75`.** El encargo dejaba la elección abierta ("tu decisión, documéntalo"): una constante única
    para las 8 cohortes habría ignorado que un jubilado vota mucho más que un estudiante en la realidad
    (y el propio ADR trae `trust`/`econ_pref` diferenciados por cohorte en la tabla de ADR 005 secc. 3,
    mismo espíritu). `DEFAULT_TURNOUT = 0.75` sigue existiendo como fallback si el CSV no trae la
    columna (`LoyaltyTable.get_turnout`).
13. **`data/cohorts_loyalty.csv` (40 valores de lealtad + 8 de turnout) son inventados**, calibrados a
    mano por signo de afinidad ideológica (cohortes con `econ_pref` negativo → más lealtad a
    Frente Federal/Partido Social; positivo → más a Unión Republicana/Movimiento Libertad;
    `alianza_provincial` con lealtad pareja y baja en todas, como partido regional sin base social
    propia) y turnout más alto en jubilados/rurales/clase media, más bajo en estudiantes/informales
    (mismo orden que la participación electoral real en democracias comparables, sin pretender
    precisión). Documentado también como comentario en el propio CSV... **corrección**: el CSV no
    admite comentarios (es puramente tabular, `csv.DictReader`); la documentación de los valores vive
    acá y en `world/elections.py::load_loyalty`.
14. **`resolve_presidential` transfiere votos del balotaje solo por el eje `economic` de `Party`.** El
    ADR dice "afinidad ideológica" sin especificar los 4 ejes; `Party` (`world/config.py`) solo trae
    `economic`/`social`, no `federalism`/`institutionalism` (esos son atributos de `ActorSheet.ideology`,
    no de `Party`) — usar el único eje disponible en ambos lados es la opción consistente con el resto
    del módulo (`compute_vote_intention` también usa solo `economic` para `v_ideo`).
15. **D'Hondt sin partidos que superen el umbral del 3 % cae a repartir igual entre todos** (`dhondt`,
    rama `if not eligible: eligible = dict(vote_pct)`): evita un Congreso de 0 bancas si, por ruido o una
    elección muy fragmentada, ningún partido llega al 3 % — caso de borde no cubierto por el ADR.
16. **CAMPAIGN/PROMISE no las emite ningún actor por reglas en `run`.** `actors/rule_based.py` no gana
    ninguna rama nueva para decidir cuándo campañar: el ADR pide la acción y sus consecuencias
    (deliverable 5), no una regla de decisión para emitirla (a diferencia del resto del catálogo de ADR
    003 secc. 6, que sí tiene una regla explícita por rol). Consecuencia: en `republica run`, `vote_p`
    nunca ve el término `v_camp` (siempre `0`, `sim.campaign_state` queda vacío) — la elección se decide
    por economía/ideología/lealtad/aprobación/eventos, no por campaña. Es jugable de verdad solo en
    `play` (deliverable 6, pantalla de campaña, presidente humano). Documentado para que no sorprenda:
    "por qué `run --seed 7` nunca genera un `CAMPAIGN` en el JSONL" es una pregunta legítima y la
    respuesta es esta, no un bug.
17. **`Game.apply_campaign` actualiza `sim.campaign_state`/`sim.promises` directo, sin pasar por
    `authorize()`/`apply_consequences`.** A diferencia de `GRANT_CONCESSION` en `set_grant_decisions`
    (que sí arma una `Action` real), no hay una `Perception`/decisión de un actor de por medio que
    justifique el viaje completo por el pipeline de acciones para un presidente humano que ya está dentro
    de la ventana de campaña (la propiedad `Game.campaign_window_active` ya replica el chequeo 3 de
    `authorize()` antes de aceptar la llamada). Ver también el punto 20 (no se persiste en el save).
18. **`PromiseParams.direction` es un campo estructurado (`"expansive"|"restrictive"`), no se infiere del
    texto libre de la promesa.** El ADR solo pide comparar la promesa contra la "firma económica" del
    delta de política del mes; inferir esa firma desde lenguaje natural (sin LLM en el camino de
    `run`/reglas) habría necesitado un parser de intención que no existe en el proyecto. Se prefirió un
    campo explícito, documentado en `engine/actions.py::PromiseParams`, con la misma convención de signo
    que `data/policy_signatures.yaml` (`economic` positivo = más ortodoxo/restrictivo).
19. **Transición de gobierno: el reset completo (política al default, `agreements` vaciados, memorias
    `about=president` re-etiquetadas, relaciones del presidente re-sembradas) solo ocurre si
    `winner != incumbent_party`.** Con reelección ("Ganador = oficialismo: `approval = vote_p + 5`, todo
    sigue", ADR literal) solo cambian `approval`/`cohort_state` (luna de miel) y las bancas/`in_government`
    de `parties.json` para el próximo mandato (eso sí, siempre, gane quien gane: el ADR lo pide aparte,
    "las bancas... reemplazan las de parties.json"). El párrafo intermedio del ADR ("los demás actores
    persisten con su memoria... memorias re-etiquetadas") se interpretó como parte del caso de cambio de
    gobierno únicamente (es el que tiene sentido: sin cambio de presidente no hay "presidente saliente" al
    que re-etiquetar memorias).
20. **Tras cualquier elección, `is_ally` se resetea a `False` en todos los partidos** (`build_post_election_
    parties`): no hay forma de derivar del resultado electoral solo qué coalición arma el partido ganador;
    se deja que `FORM_ALLIANCE` (ADR 003 secc. 4/5) la reconstruya durante el mandato que empieza.
21. **Solo se re-siembran las relaciones de `"president"` en la transición, no las de `minister_economy`.**
    El ADR es literal ("relaciones del nuevo presidente = las del partido") y no menciona al ministro;
    `data/actors/ministers/<party>.yaml` sí trae sus propias `relationships` (usadas como semilla si
    alguna vez se reconstruyera `Relationships` desde cero, pero no se re-siembran en caliente durante
    una transición).
22. **`data/actors/ministers/*.yaml` (4 fichas, para `union_republicana`/`partido_social`/
    `movimiento_libertad`/`alianza_provincial`) tienen ideología tomada de `parties.json` (`economic`/
    `social`) y el resto de los campos (`federalism`/`institutionalism`/`personality`/`interests`/
    `influence`/`relationships`/`bio`) inventados para v0.6**, del mismo orden de magnitud que
    `minister_economy.yaml` original — documentado también inline en cada YAML.
23. **La elección consume `sim.rng` (el mismo RNG compartido de shocks/exógenas), no un RNG propio.** A
    diferencia de `congress_rng`/los RNG por actor (ADR 003 secc. 7, un `random.Random` propio para no
    desincronizar a los demás), la elección es un evento raro (una vez cada `term_length` meses) y
    reutilizar `sim.rng` es consistente con cómo ya se sortean los shocks/exógenas del mismo mes. Efecto
    colateral: activar `features.elections` cambia el consumo de aleatoriedad de TODOS los meses
    posteriores a la primera elección (no solo el resultado electoral en sí) — irrelevante para el golden
    hash (que corre con `elections_enabled=False`) pero documentado para quien compare dos corridas con
    la feature prendida en momentos distintos del desarrollo.
24. **`Game.save()`/`Game.load()` no persisten `campaign_state`/`promises` ni un log de llamadas a
    `apply_campaign`** (no hay un `campaign_decision_log` análogo a `grant_decision_log`): recargar una
    partida guardada que incluyó decisiones de campaña las pierde (se reproduce desde `decisions`/
    `instrument_edits`/`grant_decisions`, que no las registran). Mismo precedente que ADR 004 secc. 10
    punto 20 (`play --load` tampoco restaura `brain_map`): se documenta en vez de resolverse, fuera de
    alcance de esta fase.
25. **`term_length` (default 48) es un campo nuevo de `Country`/`country.json`, no de `features`.** Vive
    aparte de `features.elections` porque tiene sentido incluso con elecciones apagadas (p. ej., para
    narrar "mandato" en algún momento futuro); `engine/permissions.py::AuthContext` lo necesita para el
    chequeo de ventana de campaña de `CAMPAIGN`/`PROMISE` sin depender de que `features.elections` esté
    prendido (un `CAMPAIGN` con elecciones apagadas simplemente no tiene efecto real — `sim.campaign_
    state` no se usa en ninguna elección — pero la ventana de permisos sigue aplicando igual).

### Golden hash

26. **Calculado contra el commit `21f9cf67c842b6e0437ad486857e1c96c1af9a93`** (`git worktree add
    /tmp/head HEAD` desde ese commit, el HEAD real de la rama al empezar Fase 6 — un commit de solo
    visor, posterior a "Fase 5b: cohortes sociales, medios y percepción"), con
    `run(seed=7, months=48, actors_enabled=True, congress_enabled=True, negotiation_enabled=True,
    cohorts_enabled=True, media_enabled=True)` (constant) y la misma corrida con `TaylorPolicy` en
    `seed=42` — mismo precedente que los golden hash de ADR 004/005 (`config_hash` reemplazado por un
    placeholder antes de hashear, es el único byte que cambia al tocar `data/country.json`/`data/
    parties.json`, inevitable al agregarles `term_length`/`features.memory`/`features.elections`). Ver
    `tests/test_memory_elections.py::test_features_off_matches_pre_adr006_golden_hash`.

---

## 5. Nota de calibración (encargo de calibración post-Fase 6)

Estado: aplicada. Ver `docs/CALIBRATION_LOG.md` para el detalle numérico completo (tabla de
lealtad, τ, línea de base de 50 semillas, mes 48/96 de `seed=7 --policy taylor` antes/después). Esta
sección resume el diagnóstico y las decisiones; **ningún cambio tocó la forma de las fórmulas de
`world/elections.py`** (`compute_vote_intention`, `resolve_presidential`, `dhondt`), solo datos
(`data/cohorts_loyalty.csv`, `data/cohort_provinces.csv` nuevo) y un parámetro (`TAU_SHARE`) — con la
única excepción documentada de `regional_bonus_c,p` (nota de implementación #10, que dejaba el bono
regional fijo en 0 por falta de datos): esa nota se da por **resuelta**, no por invalidada, agregando
`data/cohort_provinces.csv` y una fórmula de `perf_p` (sin ADR previo que la fije — documentada inline
en `world/elections.py::province_performance`, es calibración pura, no una desviación de un texto ya
escrito).

### 5.1 Diagnóstico

`run --seed 7 --policy taylor --months 96` daba, en la primera vuelta del mes 48: FF 19.4 %, UR
21.9 %, PS 20.0 %, ML 15.6 %, AP 23.1 % — casi uniforme, y **Alianza Provincial** (un partido regional
de 8 bancas, sin base social propia según la nota de implementación #13 original) terminaba ganando la
presidencia. Dos causas, ambas de calibración, no de fórmula:

1. **`τ = 0.35` (secc. 2.2, literal) aplana el softmax.** Con los pesos por defecto (`v_ideo = 0.25`,
   `v_loy = 0.15` son los términos dominantes en una línea de base sin campaña/economía/eventos), la
   diferencia de utilidad típica entre dos partidos para una misma cohorte es de apenas 0.1–0.3. Dividir
   eso por `τ = 0.35` produce razones de softmax cercanas a 1 entre las 5 opciones — casi uniforme por
   construcción, sin que ningún partido tenga que ser "malo" para que el reparto sea parejo.
2. **La matriz de lealtad original (`data/cohorts_loyalty.csv` de Fase 6) era casi uniforme (todas las
   cohortes con lealtad 0.05–0.45 hacia cada partido, sin estructura por cohorte) y `alianza_provincial`,
   con `economic = 0.0` (el único partido centrista de `data/parties.json`), nunca queda última en el
   término ideológico de ninguna cohorte (`v_ideo · (1 − |econ_pref_c − economic_p|)`, `economic_p = 0.0`
   minimiza esa distancia para cualquier `econ_pref_c` de magnitud media) — un partido "sin base propia"
   pero que nunca es la peor opción de nadie termina, bajo softmax con τ chico, acumulando una porción
   pareja de cada cohorte en vez de una porción chica: exactamente lo opuesto al "partido regional
   marginal" que describe la ficha de `alianza_provincial`.

### 5.2 Cambios

- **`TAU_SHARE`: `0.35 → 0.15`** (rango sugerido 0.12–0.2, ver `world/elections.py` para la
  justificación completa inline). Mantiene el softmax dentro de un rango razonable
  (`exp(0.2/0.15) ≈ 3.8`) sin volverlo casi determinista.
- **`data/cohorts_loyalty.csv` recalibrado de cero**, con estructura explícita por cohorte (urban_workers/
  public_employees → FF/PS; middle_class/young_professionals → UR/ML; rural → UR/AP; informal → FF;
  retirees → FF/UR; students → PS/FF, según el encargo) — tabla completa en
  `docs/CALIBRATION_LOG.md`. La lealtad **no está acotada a `[0, 1]`**: es un término aditivo más de
  `util_c,p` (`v_loy · loyalty_c,p`), no una probabilidad — se usan valores hasta ~1.08 (UR en sus
  cohortes más leales) y negativos (hasta −0.6, `alianza_provincial` en toda cohorte salvo `rural`) para
  compensar la ventaja ideológica estructural de un partido centrista (punto 2 de 5.1) sin tocar la
  fórmula de `v_ideo`. Un partido "sin base social" necesita lealtad genuinamente negativa para no ganar
  por default en un softmax de τ chico — 0 (neutral) no alcanza.
- **`data/cohort_provinces.csv` (nuevo)**: peso de población de cada cohorte por provincia (Σ = 1 por
  cohorte), resuelve la nota de implementación #10 (`regional_bonus_c,p` fijo en 0). `world/elections.py`
  gana `load_province_weights`, `province_performance` (`perf_p`, calibración: escala `income_p`/
  `unemployment_p` de `world/provinces.py` contra el promedio nacional, sin fórmula previa que fijar) y
  `compute_regional_bonus`. Opcional (`{}` si el CSV no existe → mismo comportamiento que antes).
  `v_reg = 0.05` sin tocar (el encargo lo pide explícito).

### 5.3 Resultado

Línea de base (50 semillas, `approval_c = 50`, sin cambio económico, sin campaña/eventos): FF 35.7 %,
UR 29.6 %, PS 16.4 %, ML 8.2 %, AP 10.2 % — las 5 dentro de ±5pp de las bancas iniciales de
`data/parties.json` (38/30/14/10/8). `seed=7 --policy taylor`, mes 48: FF 23.8 %, UR 34.9 %, PS 19.9 %,
ML 9.0 %, AP 12.4 % (spread 25.9pp, ya no uniforme); balotaje UR 50.7 % vs FF 49.3 % — el oficialismo
(aprobación ≈ 29 en el mes 48, cayendo desde 50) pierde, pero contra Unión Republicana, no contra
Alianza Provincial. Detalle completo (incluida la segunda elección, mes 96) en
`docs/CALIBRATION_LOG.md`. Tests nuevos: `tests/test_memory_elections.py::
test_baseline_reproduces_initial_party_system`, `::test_economic_vote_moves_incumbent_share_at_least_6pp`,
`::test_regional_bonus_favors_governing_party_in_its_province`,
`::test_seed7_taylor_month48_no_longer_near_uniform_and_incumbent_loses` (los tests de la secc. 3 ya
existentes, incluidos los 2 de aprobación 65/25, siguen pasando sin cambios).
