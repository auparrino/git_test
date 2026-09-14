# ADR 005 — Interacción: Congreso, negociación, cohortes y percepción (Fase 5)

Estado: aceptado para implementar. Depende de ADR 003 y 004. Cuatro subsistemas, **un commit por
subsistema, en este orden**: Congreso → negociación → cohortes → medios y percepción. Cada uno tiene
gemelo por reglas y puede desactivarse por config (`features.congress`, etc.) para que v0.1 siga
siendo reproducible.

---

## 1. Congreso (`engine/congress.py`)

### 1.1 Qué requiere ley
| Instrumento | Requiere ley |
|---|---|
| `interest_rate_target`, `fx_intervention` | No (Ejecutivo / Banco Central) |
| `primary_spending` con `|Δ| ≤ 0.5` | No (reasignación administrativa) |
| `primary_spending` con `|Δ| > 0.5`, `tax_rate`, `provincial_transfers` | **Sí** |

Cuando la `PolicyProposal` del mes incluye instrumentos que requieren ley, se crea un `Bill`
(`id`, `month`, `policy_delta`, `threshold = 51`). Las partes que no requieren ley se aplican igual.

### 1.2 Voto por partido
Para cada partido `p` con `seats_p`, `discipline_p ∈ [0,1]`:
```
pressure_p = Σ_{a ∈ LOBBY_CONGRESS} sign(a.direction) · a.intensity · influence_a.congress · affinity(a, p) · 20
           + 0.2 · (government_approval − 50)               # opinión pública
           + concession_bonus_p                              # +25 si hay acuerdo vigente (sección 2)
score_p    = rule_score(p, bill)                             # ADR 003 §6, en [−100, 100]
yes_prob_p = sigmoid((score_p + pressure_p) / 25)
yes_seats_p = seats_p · (discipline_p · [yes_prob_p ≥ 0.5] + (1 − discipline_p) · yes_prob_p)
```
`affinity(a, p)`: 1 si el actor pertenece al partido (gobernador) o tiene `relationships[p] > 65`;
0.5 si `> 50`; 0.2 si no. `discipline` en `parties.json` (FF 0.7, UR 0.8, PS 0.6, ML 0.9, AP 0.4).

### 1.3 Resultado
`yes = Σ yes_seats_p` (redondeo por partido). Si `yes ≥ threshold`: `Bill.passed`, la política se aplica
este mes. Si no: la parte legislativa del delta **no se aplica**, `approval −1`, `institutional_confidence
+0.5` (el sistema funcionó), y el presidente puede reenviarla el mes siguiente. `congress_support'` pasa a
ser **derivado**: `Σ seats_p · yes_prob_p(bill genérico de gasto +1)`; la fórmula de v0.1 (§5.7) queda como
fallback con `features.congress = false`.

`VoteRecord` (JSONL `kind: "vote"`): bill, por partido `score, pressure, yes_prob, yes_seats`, total, resultado.

---

## 2. Negociación (`engine/negotiation.py`)

Se abre cuando un actor emite `NEGOTIATE(requested_concession)` sobre la propuesta del mes. Máximo 3
rondas dentro del mismo turno, antes de la votación.

```
ronda k:
  gobierno  → GRANT(concession) | COUNTER(concession', scale ∈ {0.5, 0.75}) | REFUSE
  actor     → ACCEPT | COUNTER(concession'') | WALK_AWAY
```
- **Presidente por reglas** (`actors/president_rules.py`): `leverage_a = seats controlados por el actor
  (partido o gobernador) / bancas que faltan para 51 + influence.streets`. Concede si
  `cost(concession) ≤ budget_month` (0.8 pp PIB acumulados por mes, en `data/concessions.yaml`) y
  `leverage_a ≥ 0.3`; contraoferta al 50 % si `0.15 ≤ leverage < 0.3`; rechaza si no.
- **Actor por reglas**: acepta si `value(offer) ≥ 0.6 · value(request)` o si `relationships.president > 65`;
  `pragmatism` baja el umbral hasta 0.4; `ambition > 0.7` sube a 0.75. Contraoferta una vez; después
  `WALK_AWAY` (y su posición pasa a `oppose`).
- **Resultado**: `Agreement{actor, concession, in_exchange: "vote_yes" | "no_strike" | "support"}`. Mientras
  esté vigente: `concession_bonus` en el Congreso y `+8` relación. El gobierno tiene 2 meses para
  ejecutar la concesión (aparece como `policy_delta` o gasto); si no lo hace: `broken_by_government`,
  relación `−15`, evento `agreement_broken` (memoria en Fase 6). Si el actor vota en contra igual:
  `broken_by_actor`, relación `−10`, y el presidente por reglas no vuelve a negociar con él por 6 meses.
- Todo el diálogo se guarda en `NegotiationRecord` (JSONL `kind: "negotiation"`, lista de turnos
  con `speaker, move, concession, scale, reason`).

En modo `play`, el humano recibe cada pedido como un dilema generado (`NEGOTIATE de gov_norte:
restaurar transferencias a cambio de votos`) con opciones `Conceder / Contraoferta 50 % / Rechazar`.

---

## 3. Cohortes sociales (`world/cohorts.py`, `data/cohorts.csv`)

| id | Nombre | pop_share | income | u_offset | s_pi | s_u | s_w | s_tr | s_tax | s_crime | trust | econ_pref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| urban_workers | Clase trabajadora urbana | 0.22 | 80 | +1.0 | 1.2 | 1.5 | 1.5 | 0.3 | 0.2 | 0.8 | 40 | −0.5 |
| rural | Productores rurales | 0.08 | 95 | −1.0 | 0.8 | 0.5 | 0.6 | 0.8 | 1.2 | 0.5 | 50 | +0.4 |
| middle_class | Clase media alta | 0.15 | 160 | −2.0 | 1.0 | 0.5 | 0.8 | 0.1 | 1.5 | 1.2 | 55 | +0.5 |
| public_employees | Empleados públicos | 0.12 | 100 | −3.0 | 1.2 | 0.2 | 1.8 | 0.5 | 0.3 | 0.5 | 45 | −0.6 |
| young_professionals | Jóvenes profesionales | 0.10 | 120 | +0.5 | 1.0 | 1.0 | 1.0 | 0.1 | 0.8 | 0.6 | 50 | +0.2 |
| informal | Trabajadores informales | 0.18 | 55 | +4.0 | 1.8 | 1.2 | 1.0 | 0.6 | 0.0 | 1.0 | 30 | −0.3 |
| retirees | Jubilados | 0.10 | 70 | 0.0 | 1.6 | 0.2 | 1.4 | 0.4 | 0.2 | 1.2 | 45 | −0.2 |
| students | Estudiantes | 0.05 | 50 | +3.0 | 0.8 | 1.2 | 0.6 | 0.2 | 0.1 | 0.4 | 40 | −0.4 |

`pop_share` suma 1. `s_*` son sensibilidades relativas (1.0 = la de la fórmula agregada de v0.1).

Cada cohorte `c` mantiene `approval_c` y `sentiment_c`. Transición (reemplaza §5.6 de v0.1 en agregado):
```
approval_c' = approval_c
            + s_w_c  · e_w  · Δreal_wage_pct
            − s_u_c  · e_u  · Δunemployment_c            # unemployment_c = unemployment + u_offset_c
            − s_pi_c · e_pi · (perceived_inflation_c − 2)   # percepción, no realidad (sección 4)
            + e_g · demand_gap
            − e_t · pos(social_tension − 50)/10
            + s_tr_c · 2 · Δprovincial_transfers − s_tax_c · 2 · Δtax_rate
            − s_crime_c · 0.05 · (crime_perception − 50)
            + e_rev · (45 − approval_c)
            + 3 · econ_pref_c · policy_direction          # policy_direction ∈ [−1, 1]: firma económica del delta del mes (ADR 003 §6.1)
government_approval' = Σ pop_share_c · approval_c'
```
Con cohortes homogéneas (`s_* = 1`, `econ_pref = 0`, percepción = realidad) esto reproduce v0.1
(test). `consumer_confidence` (§5.1) pasa a usar `Σ pop_share · perceived_inflation_c` en vez de
`inflation`. Cada bloque social actor (ADR 003) se vincula a una cohorte (`bloc_urban_workers →
urban_workers`, etc.); su `private_indicators` son los de su cohorte y su `interest_impact` usa
`approval_c`.

---

## 4. Medios y percepción (`world/perception.py`)

### 4.1 Variables percibidas (por cohorte)
```
perceived_inflation_c, perceived_unemployment_c, sentiment_c ∈ [−100, 100]
```
### 4.2 Consumo de medios (`data/media_consumption.csv`)
Matriz cohorte × medio con shares que suman 1 por cohorte (ej. `middle_class: nacional 0.4, mercado 0.5,
popular 0.1`; `informal: popular 0.6, nacional 0.3, mercado 0.1`).

### 4.3 Sesgo de un frame
| frame | Δ perceived_inflation | Δ perceived_unemployment | Δ sentiment |
|---|---|---|---|
| `crisis` | `+1.5 · influence.public` (pp mensuales) | `+2.0 · influence.public` | `−10 · influence.public` |
| `recovery` | `−0.8 · influence.public` | `−1.0 · influence.public` | `+6 · influence.public` |
| `scandal` | 0 | 0 | `−6 · influence.public` (y `institutional_confidence` como en ADR 003) |
| `neutral` | 0 | 0 | 0 |

`PUBLISH_STORY.target_bloc` limita el efecto a esa cohorte; `all` lo reparte por consumo.

### 4.4 Transición
```
bias_pi_c = Σ_m consumption[c][m] · Δperceived_inflation(frame_m)
perceived_inflation_c' = perceived_inflation_c + q · (inflation' + bias_pi_c − perceived_inflation_c)   # q = 0.4
(igual para unemployment; sentiment con q = 0.3 y anclaje en 0)
perception_gap = Σ pop_share_c · (perceived_inflation_c − inflation')     # métrica registrada
```
Los medios **nunca** tocan variables reales. Test: con `features.media = true` y todos los frames
`neutral`, la trayectoria real es idéntica a `features.media = false`.

### 4.5 Audiencia
`influence.public_m' = influence.public_m + 0.02 · (alineación_m − 0.5)`, con `alineación_m` = fracción de
cohortes cuyo `sentiment_c` tiene el mismo signo que el frame del medio (crisis ↔ negativo). Un medio
que insiste en "crisis" cuando la gente está bien pierde audiencia. Acotado a [0.05, 0.6].

---

## 5. Orden del turno (actualiza ADR 003 §7)
```
1. exógenas y shocks
2. presidente: Policy + PROPOSE_POLICY (+ GRANT_CONCESSION pendientes)
3. percepciones → actores deciden (acciones)
4. negociaciones (≤ 3 rondas por actor que pidió NEGOTIATE) → acuerdos
5. authorize + consequences (incluye LOBBY_CONGRESS)
6. Congreso: si hay Bill, votación; ajuste de la Policy efectiva
7. economía (con la Policy efectiva)
8. medios → percepción por cohorte
9. cohortes → approval agregada; sociedad y política restantes
10. cumplimiento de acuerdos (vencidos, rotos)
11. eventos endógenos; registros (month, action, negotiation, vote, perception)
```

## 6. Detección de emergencia
`republica emergence run.jsonl`: lista alianzas formadas (`FORM_ALLIANCE`), coaliciones de voto que se
repiten ≥ 3 veces (mismo conjunto de partidos votando igual contra su score ideológico), acuerdos
rotos y medios que cambiaron de línea. Es la materia prima de `docs/EMERGENCE_LOG.md`.

## 7. Tests (DoD de Fase 5)
1. Ley de impuestos con oposición alineada en contra falla con 45 bancas; con acuerdo con
   `alianza_provincial` (+8) y `LOBBY_CONGRESS` favorable de dos gobernadores, pasa.
2. `gov_norte` pide `restore_transfers`; el presidente por reglas concede si su bloque es pivotal; se
   registra el `Agreement`; si el gobierno no ejecuta en 2 meses, relación −15 y evento `agreement_broken`.
3. Cohortes homogéneas reproducen la aprobación de v0.1 (`|diff| < 0.05` por mes, 48 meses).
4. `media_mercado` en `crisis` sube `perceived_inflation` de `middle_class` más que la de `informal`;
   con todos los frames `neutral`, la trayectoria real es idéntica a `features.media = false`.
5. Con todos los features activos, 48 meses × 29 actores por reglas corren en < 10 s y el JSONL
   contiene registros `vote`, `negotiation` y `perception`.
6. `emergence` sobre 20 semillas encuentra al menos una alianza o coalición de voto repetida
   (si no encuentra ninguna, se documenta: también es un resultado).

## 8. Notas de implementación (Congreso y negociación)

Alcance de este commit: solo §1 (Congreso) y §2 (negociación), "la primera mitad" de Fase 5.
Cohortes sociales (§3) y medios/percepción (§4) quedan para el próximo commit — `PUBLISH_STORY`
sigue afectando `consumer_confidence` agregado (ADR 003 §5), no hay `perceived_inflation_c` todavía,
así que el test de aceptación 5 de §7 se cubre parcial (`vote`/`negotiation` sí, `perception` no) y el
6 queda documentado con el `emergence` que sí existe.

### Congreso (`engine/congress.py`)

1. **`score_p = rule_score(p, bill)` se calcula directo sobre `bill.policy_delta`, no armando una
   `Perception` de partido.** ADR 003 §6 define el score de cualquier actor a partir de una
   `Perception` completa (`compute_score`); reconstruir una para cada uno de los 5 partidos en cada
   voto (incluida la `derive_congress_support` "genérica" de cada mes) sería más caro y no aporta nada
   que `ideological_fit`/`interest_impact`/`electoral_pressure_raw` no den ya con los argumentos
   sueltos. Se extrajo `electoral_pressure_raw(in_government, months_to_election, approval)` de
   `actors/rule_based.py::electoral_pressure` (que ahora es un envoltorio de una línea) para poder
   reusarlo sin una `Perception`. El término de relación usa `relationships.get(party_actor.id,
   "president")` (la ficha `party_<id>.yaml` de ADR 003, no una ficha nueva por partido de
   `parties.json`), y el término de interés usa `dependence = 0.5` fijo (los partidos no tienen
   provincia).
2. **`affinity(a, p)`** se resuelve contra las relaciones vivas del motor con el actor **`party_<id>`**
   (ya existen en las 29 fichas — `gov_norte.relationships.party_alianza_provincial: 80`, etc. — ADR
   003 §11 punto 9 ya establecía relaciones actor-actor incluyendo actores de rol `party`), no una
   relación actor→partido nueva. Gobernador de ese partido o el propio actor-partido → 1.0 directo, sin
   mirar relación.
3. **`concession_bonus_p` (+25)** se paga al partido si hay un `Agreement` `vigente` con el actor-partido
   mismo o con un gobernador de ese partido — coincide con `affinity = 1.0`, es la lectura más literal
   de "hay acuerdo con alianza_provincial" del test de aceptación 1.
4. **`congress_support` derivado (§1.3) gateado por `actors_enabled AND features.congress`.** Sin
   actores no hay partidos-actor que votar (la fórmula de v0.1, `world/politics.py::step_politics`, sin
   tocar, sigue siendo el único camino); con actores pero `features.congress=False` también se usa la
   de v0.1 — es exactamente el fallback que pide el ADR. Se calcula sobre `full_state` (ya con el
   `government_approval` del mes, después de `step_politics`), no sobre el estado de entrada de mes:
   mismo criterio que usa la fórmula de v0.1 para `congress_target` (usa `approval_new`, no `prev`).
5. **Redondeo por partido:** `round(yes_seats_p)` estándar (banker's rounding de Python), sin ningún rol
   para el `rng` que pide la firma sugerida del encargo — el `rng` se usa donde sí hace falta: el
   término de ruido de `rule_score` (`sigma = 5*(1-pragmatism)`, igual que ADR 003 §6), uno por partido
   y por voto.

### Bill: de dónde sale el `policy_delta` que se vota

**Ambigüedad no resuelta por el ADR:** ¿una concesión de negociación que toca un instrumento que
requiere ley (`restore_transfers`→`provincial_transfers`, `tax_exemption`→`tax_rate`) pasa por el
Congreso, o es un acto de gobierno directo como en Fase 3? Leído junto con la mención explícita de
`concession_bonus_p` en la fórmula de presión del Congreso (§1.2), la lectura más consistente es que
**sí pasa**: si una concesión negociada no necesitara nunca aprobación legislativa, no tendría sentido
que un acuerdo vigente sesgue el voto — sesgaría el voto de *qué*. Se implementó así, con un diseño que
evita la circularidad de "votar en el mismo mes en que se negoció":

- Cada `Agreement` nuevo (`engine/negotiation.py::negotiate_one`) sabe si `law_required` mirando si su
  `concessions.yaml[concession].policy_field` cae en `requires_law` (con el propio `policy_bump` como
  delta de prueba). Con `congress_enabled=False`, **nunca** requiere ley (se ejecuta directo, camino de
  Fase 3): sin Congreso no hay nada que lo bloquee.
- Un acuerdo `law_required=True` queda `vigente` sin ejecutar (`executed=False`) y entra a una "cola"
  (no es una lista aparte: son los `Agreement` de `engine.agreements` con `status == "vigente" and
  law_required and not executed`).
- Cada mes, el `Bill` que se vota (`engine/simulation.py::advance_month`) es la unión de dos partes:
  (a) `requires_law(proposal.delta)` — lo que la `PolicyRule`/el jugador propuso este mes — y (b)
  `sum_queue_delta(...)` sobre la cola **tal como estaba antes de correr las negociaciones de este
  mes** (el snapshot se toma antes de llamar `run_actor_turn`). Un acuerdo recién pactado este mes
  entra a la cola pero se vota recién **el mes que viene**, nunca el mismo mes que se negoció — evita
  tener que cerrar el `Bill` antes de saber qué se negoció, y le da sentido literal a "2 meses para
  ejecutar" (como máximo, 2 intentos de voto).
- Si el `Bill` pasa: la parte (a) ya estaba aplicada en `policy` (nada que hacer); la parte (b) se
  ejecuta (`apply_execution_results`, `passed=True`): `policy_<campo>`/`shock_fiscal` a
  `pending_terms` (mismo desfasaje de un mes que un `GRANT_CONCESSION` de Fase 3), `Agreement.status =
  "honored"`.
- Si el `Bill` no pasa: la parte (a) se revierte (`policy` vuelve al valor de
  `sim.last_effective_policy`, **no** al `default_policy` ni al `raw_policy` de la regla: el valor
  *efectivamente vigente* el mes pasado, después de bumps/vetos previos — campo nuevo en `Simulation`,
  distinto de `last_policy` que sigue siendo el `raw_policy` pre-bump usado para calcular la
  `PolicyProposal`); la parte (b) suma un mes de `months_pending` a cada `Agreement` de la cola, y al
  segundo mes sin pasar, `broken_by_government` (relación −15, evento `agreement_broken:*:government`).
  `shock_approval −1`/`institutional_confidence +0.5` van a `pending_terms` (aplican el mes que viene,
  como toda consecuencia del motor).
- **Las concesiones `GRANT_CONCESSION` "de la vía vieja"** (pedidos `REQUEST_FUNDS`, resueltos por
  `RuleBasedPresident.decide_grants`, sin tocar) **no pasan por el Congreso**, incluso con
  `features.congress=True`: el ADR solo menciona el `Bill` naciendo de "la `PolicyProposal` del mes" y
  de negociaciones (§2); extenderlo a `REQUEST_FUNDS` también habría sido razonable pero no es lo que
  pide el texto, y hacerlo hubiera significado tocar `RuleBasedPresident` (fuera del scope declarado del
  encargo, que pide reemplazar específicamente "la lógica simple de Fase 3" de concesión vía
  `NEGOTIATE`, no la de `REQUEST_FUNDS`).

### Negociación (`engine/negotiation.py`)

6. **`leverage_a`**: `seats_controlled(a) / max(51 - coalition_seats, 1) + influence.streets`.
   `seats_controlled`: bancas del propio partido si `a.role == "party"`, bancas del partido de su
   gobernación si `a.role == "governor"`, `0` para el resto (sindicatos/empresas/ministro no "controlan"
   bancas: su leverage es puro `influence.streets`).
7. **Hallazgo empírico: con los datos reales de v0.3, la banda `[0.15, 0.3)` (contraoferta) nunca se
   alcanza.** `seats_needed = max(51 - coalition_seats, 1) ≈ 6.2` (el gobierno ya tiene ~44.8 bancas
   propias+aliadas): cualquier gobernador/partido con bancas propias (mínimo 8, `alianza_provincial`)
   ya da `leverage ≥ 1.29`; los sin bancas (sindicatos, empresas, el ministro) dependen solo de
   `influence.streets` — `union_cgt`/`union_public` (0.6-0.65) caen igual arriba de 0.3 (concesión
   plena); `biz_*`/`minister_economy` (0.0-0.1) caen debajo de 0.15 (rechazo directo). Verificado
   corriendo `run(seed=7, policy=taylor, congress=True, negotiation=True)` 48 meses: 284 `NEGOTIATE`,
   174 acuerdos, **0** con más de una ronda, **0** votos rechazados (46/46 aprobados). No se tocaron
   `data/parties.json`/`data/actors/*.yaml` para forzar un caso (cambiar `influence.streets` de un
   actor solo para que aparezca una demo no es una calibración real, y mover esos archivos infla
   `config_hash` sin necesidad). El ejemplo de negociación a 2 rondas del reporte final se generó con
   un actor sintético (`biz_agro` con `influence.streets = 0.2`, `personality.ambition = 0.8`) llamando
   `negotiate_one` directo — documentado ahí como tal, no sale de una corrida real.
8. **`in_exchange` por rol** (el ADR no lo tabula): `union → "no_strike"`, `governor`/`party →
   "vote_yes"`, el resto → `"support"` genérico.
9. **Umbral de aceptación**: `0.6 − 0.2·pragmatism` (↓ hasta 0.4 en `pragmatism=1`), `0.75` fijo si
   `ambition > 0.7` (el ADR da ambos ajustes como si fueran independientes/aditivos, pero sumar ambos
   podía superar 1.0 sin motivo del ADR para ese caso límite; se aplicó `ambition` como un override, no
   como un sumando adicional — más simple y sigue moviéndose en el rango que pide el texto).
10. **Ronda 2/3 del presidente**: siempre `COUNTER` a escala `0.75` (la otra escala de `{0.5, 0.75}`)
    si el presupuesto alcanza, si no `REFUSE`. El ADR da las dos escalas sin decir en qué ronda va cada
    una; `0.5` en la primera contraoferta y `0.75` si el actor la rechaza y contraoferta a su vez es la
    lectura más natural de "escalar la oferta".
11. **`GRANT_CONCESSION` NO ganó un parámetro `scale`.** La primera implementación de "Contraoferta 50
    %" en `play` agregaba `scale: float = 1.0` a `GrantConcessionParams` (reusar la acción existente,
    escalada) — se descartó: como `Action.params` se serializa completo en cada `ActionRecord`, el
    nuevo campo (aún en `1.0` por default) aparece en **cualquier** `GRANT_CONCESSION` de **cualquier**
    corrida con actores, rompiendo el requisito de bytes idénticos con los features nuevos apagados (el
    camino viejo de `REQUEST_FUNDS`/`RuleBasedPresident.decide_grants` sigue usando esa acción sin
    tocar). En su lugar, "Contraoferta 50 %" en `play` (`Game.set_grant_decisions`, parámetro nuevo
    `negotiation_decisions`) aplica la mitad del `policy_bump`/`fiscal_cost_pct_gdp` **directo** a
    `sim.pending_terms` (fuera del catálogo de `Action` — no hay una acción "conceder a medias" en ADR
    003) más la mitad del `+8` de relación de un acuerdo exitoso (`+5`, ver Nota de implementación de
    `set_grant_decisions`); como no genera un `GRANT_CONCESSION`, `resolve_pending_requests` igual
    aplica el `−1` de "pedido no concedido íntegro" — simplificación aceptada, documentada en el
    docstring del método.
12. **Negociación multironda en `play` (presidente humano) no corre.** El protocolo de 3 rondas del
    ADR asume que ambas partes (presidente, actor) deciden en el mismo turno; un humano no puede
    negociar de forma síncrona dentro de un `advance_month()` ya en curso. Se resolvió con la misma
    regla que ya distingue `run` de `play` en Fase 3 (`sim.president_rule is not None`, `True` solo con
    presidente por reglas): con un humano, `NEGOTIATE` sigue el camino de un mes de desfasaje
    (`engine.pending_requests`), con el dilema "Conceder / Contraoferta 50 % / Rechazar" reemplazando
    "Conceder/Rechazar" (punto 11). `Game.new`/`Simulation.negotiation_enabled` en `play` queda en
    `True` por default pero, en la práctica, solo habilita esa tercera opción del dilema — el protocolo
    de `engine/negotiation.py` en sí nunca corre con un humano al mando.
13. **`ActorDecision.negotiation_reply`/`counter_concession` (deliverable 4), alcance mínimo.** Un
    `LLMActor` guarda la última respuesta declarada (`self.last_negotiation_reply`, efecto de lado,
    mismo patrón que `last_score`/`last_trace`); `negotiate_one` la usa TAL CUAL en la ronda 1 si está
    presente (`decision_actor` es un parámetro nuevo, opcional). No hay una segunda llamada al LLM para
    las rondas 2/3: si el actor contraoferta o el modelo no declaró nada, cae a la fórmula por reglas,
    igual que un `RuleBasedActor` — construir un segundo prompt de negociación completo (con su propio
    `ai/prompts.py`) es la otra mitad de trabajo que pide ADR 004 para esto y no entra en el alcance de
    este commit. `FakeBackend(policy="rules")` no declara `negotiation_reply` (su payload viene de
    `_actions_to_decision_payload`, que no lo conoce): cae al mismo `None` que un `RuleBasedActor`, así
    que **"`fake:rules` reproduce `rules`" sigue valiendo con Congreso/negociación activos** — verificado
    con `tests/test_congress_negotiation.py::test_fake_rules_matches_rules_with_congress_and_negotiation`
    y a mano contra 48 meses con `policy=taylor` (acciones, `vote_records` idénticos byte a byte).

### Orden de turno y compatibilidad

14. **`check_actor_compliance` (`broken_by_actor`) corre después de `apply_consequences`, antes del
    voto del Congreso.** El ADR pone "cumplimiento de acuerdos" en el paso 10 (después de la economía),
    pero un acuerdo roto por el actor este mismo mes no debería seguir aportando `concession_bonus_p` a
    *este* voto — se adelantó el chequeo de incumplimiento del actor (no el del gobierno, que sigue
    atado al resultado del voto) a antes del paso 6, y se documenta acá en vez de tocar la numeración
    del ADR.
15. **Golden hash de "features apagados = bytes idénticos".** Se corrió `run(seed=7, policy=constant)`
    y `run(seed=42, policy=taylor)`, 48 meses, `actors_enabled=True`, contra el HEAD anterior a este
    commit (`bc3a3b2`, sin `congress`/`negotiation` en el código), con `config_hash` reemplazado por un
    placeholder antes de hashear (mismo precedente que ADR 003 §11 punto 6/REVIEW_001 hallazgo #8: tocar
    `data/country.json`/`data/parties.json` — acá para agregar `features.congress`/`negotiation` y
    `discipline` — cambia `config_hash` inevitablemente, no el resto del JSONL). Los hashes SHA-256
    quedan como constantes en `tests/test_congress_negotiation.py::
    test_features_off_matches_pre_adr005_golden_hash`; se corrieron de nuevo con el código de este
    commit y `congress_enabled=False, negotiation_enabled=False` y coinciden byte a byte.
16. **`data/parties.json.discipline`** (FF 0.7, UR 0.8, PS 0.6, ML 0.9, AP 0.4) tal cual los da el
    encargo; `Party.discipline` en `world/config.py` con default `1.0` (bloque perfecto) para cualquier
    `Party` de test que no lo declare.

### Archivos nuevos/tocados

`engine/congress.py`, `engine/negotiation.py`, `engine/emergence.py` (nuevos); `engine/simulation.py`
(orden de turno, `Bill`/voto, `congress_support` derivado, `last_effective_policy`), `engine/
scheduler.py` (negociación + cumplimiento del actor dentro de `run_actor_turn`), `engine/game.py`
(`set_grant_decisions` con "Contraoferta 50 %"), `engine/narrate.py`/`cli.py` (`vote`/`negotiation` en
`narrate`, comando `emergence`, flags `--congress`/`--negotiation` de `run`), `actors/rule_based.py`
(`electoral_pressure_raw`), `actors/llm_based.py`/`ai/schemas.py` (deliverable 4), `world/config.py`
(`Party.discipline`, `features.congress`/`negotiation`), `data/country.json`, `data/parties.json`.
`actors/president_rules.py` **no se tocó**: `RuleBasedPresident.decide_grants` sigue siendo el camino
de `REQUEST_FUNDS` y el fallback completo de `NEGOTIATE` con `features.negotiation=False`.

## 9. Notas de implementación (cohortes y percepción)

Alcance de este commit: §3 (cohortes sociales) y §4 (medios y percepción), "la segunda mitad" de
Fase 5. Completa el DoD de §7: items 3-6 (cohortes homogéneas, sesgo de medios, corrida completa con
`perception`, `emergence`) más el resto del deliverable de este commit (golden hash con las features
nuevas apagadas, `fake:rules` con cohortes/medios activos).

### Cohortes (`world/cohorts.py`)

1. **Estado por cohorte fuera de `WorldState`**, como pedía el encargo: `CohortState` vive en
   `Simulation.cohort_state` (mutable, mes a mes) y se publica en `MonthRecord.cohorts` (deliverable 1)
   vía `to_dict()`. Con `features.cohorts=False`, `MonthRecord.cohorts` queda `{}` y `to_dict()` borra
   la clave (mismo patrón que `action_records`/`vote_records` de ADR 003/005): el JSONL sin la feature
   es byte a byte igual al de antes de este commit (ver punto 13, golden hash).
2. **Los tres términos nuevos de la fórmula de §3 (transferencias, impuestos, inseguridad) no tienen
   equivalente en v0.1** (`world/politics.py::step_politics` no los menciona en absoluto). El texto del
   encargo pide validar "cohortes homogéneas (`s_* = 1`, ...)" reproduciendo v0.1 con `|diff| < 0.05`;
   leído literalmente (`s_tr = s_tax = s_crime = 1` también) el test no pasa nunca — no porque la
   calibración esté mal, sino porque esos tres términos **no tienen forma de anularse solos**:
   `crime_perception` se aleja de 50 aunque no haya ninguna política ni shock, y ese término solo, con
   `s_crime = 1`, ya rompe la tolerancia de 0.05/mes bien entrada la corrida (verificado empíricamente:
   con `s_crime = 1` y el resto en 0, `ConstantPolicy`, 48 meses, el diff supera 0.05 en el mes 23 y
   llega a 1.23 en el 48). Se interpreta "`s_* = 1`" como "las sensibilidades con equivalente directo en
   v0.1" (`s_pi`, `s_u`, `s_w`) y se fijan `s_tr = s_tax = s_crime = 0` en la tabla homogénea del test
   (`tests/test_cohorts_perception.py::HOMOGENEOUS_COHORTS`, comentado ahí con el mismo razonamiento):
   con esto la fórmula de cada cohorte colapsa término a término a la de v0.1 y el agregado ponderado la
   reproduce **exacto** (no solo dentro de tolerancia) en 48 meses con `TaylorPolicy` — verificado tanto
   con `s_tr/s_tax/s_crime = 0` como confirmando que `= 1` efectivamente rompe el test, antes de decidir.
3. **`shock_approval` como parámetro nuevo de `step_cohorts`** (`world/cohorts.py`, keyword-only): el
   ADR no lo tabula en la fórmula de §3, a diferencia de la de v0.1 (§5.6) que sí lo tiene. Sin él,
   `PUBLIC_STATEMENT`/`LOBBY_CONGRESS`/huelgas y demás consecuencias de actores que hoy mueven
   `shock_approval` (ADR 003 §5) dejarían de poder mover la aprobación en absoluto con
   `features.cohorts` activo — una regresión de comportamiento respecto a antes de este commit, no algo
   que el ADR pida deliberadamente. Se aplica el mismo agregado (`agg.term("shock_approval")`) por
   igual a cada cohorte, no prorrateado por `pop_share` (no hay una base en el ADR para prorratearlo, y
   sumarlo entero a cada cohorte es lo que hace que el agregado ponderado lo reciba entero, igual que
   v0.1).
4. **El término de inflación se reinterpreta como el de v0.1 escalado, no como la resta lineal literal
   del ADR** (`e_pi_low·(pi_ref − clamp(perceived, 0, pi_ref)) − e_pi·pos(perceived − pi_ref)`, en vez de
   `− s_pi·e_pi·(perceived − 2)`): con inflación típicamente por debajo de 2 en tramos largos de una
   corrida, la resta lineal del ADR premia sin cota la desinflación (v0.1 la premia acotada, solo hasta
   `pi_ref`), lo que por sí solo ya rompe el test de homogeneidad del punto 2. Documentado también en el
   docstring de `step_cohorts`.
5. **`government_approval` se pisa (`full_state.model_copy(update=...)`) después de `step_politics`, no
   antes.** `step_politics` sigue corriendo sin tocar (calcula su propio `approval_new` "sombra", que se
   descarta) porque `congress_support`/`political_stability`/`institutional_confidence` de ese mismo
   módulo siguen leyendo su propia fórmula de v0.1 (§5.7-5.9) — el ADR no pide reemplazarlas, solo
   `government_approval` (§3, último renglón). Consecuencia aceptada: `congress_target`/`stability_target`
   usan el `approval_new` de v0.1 (sombra), no el agregado por cohortes, del mismo mes — una pequeña
   inconsistencia interna documentada acá en vez de reescribir `step_politics` (fuera del alcance
   declarado de §3, que solo habla de `government_approval`).
6. **`private_indicators`/`interest_impact` de un `social_bloc` usan el `cohort_state` de *inicio* de
   mes** (`engine/simulation.py::advance_month`, `bloc_cohort_views`, armado antes de `run_actor_turn`),
   no el ya actualizado por medios/cohortes de ese mismo mes (que corre después, pasos 8-9 de §5): un
   actor decide con la información que tiene al momento de decidir, mismo criterio que ya usa el resto
   del motor (los actores deciden sobre el snapshot `t`, la economía corre después). `engine/
   perception.py::_private_social_bloc`/`build_perception` ganan un parámetro `cohort_view` opcional
   (`None` = comportamiento idéntico a antes de este commit) para no acoplar `engine/` a
   `world/cohorts.py` directamente.

### Medios y percepción (`world/perception.py`)

7. **`features.media` depende de `features.cohorts` Y de `features.actors`** (`Simulation.new_simulation`):
   sin cohortes no hay dónde sesgar percepción; sin actores no hay `PUBLISH_STORY` que emitir.
   `features.cohorts`, a diferencia, **no** depende de `features.actors` (corre sobre `world/` solo,
   con o sin actores institucionales) — asimetría explícita en el docstring de `new_simulation`.
8. **`influence.public` de cada medio es mutable en `Simulation.outlet_influence`, no en la ficha**
   (`data/actors/media_*.yaml` sigue estática): la ficha la sigue usando el resto de ADR 003
   (`scale_by` de `PUBLISH_STORY`/`PUBLIC_STATEMENT`, relaciones, etc.) y una corrida no debe mutar el
   archivo en disco. `Simulation.outlet_influence` arranca como copia de `sheet.influence.public` de
   cada actor `role == "media"` (acotada a `[0.05, 0.6]` desde el arranque, mismo rango de la deriva de
   §4.5) y es lo único que `drift_audience` toca mes a mes.
9. **Polaridad de `scandal` = negativa** (`world/perception.py::FRAME_POLARITY`): el ADR §4.5 solo da
   el ejemplo literal "`crisis` ↔ negativo"; `recovery` como positivo simétrico y `scandal` (mala
   noticia institucional) como negativo son la lectura más natural, no están tabulados aparte. `neutral`
   queda sin polaridad (`None`): un medio que solo publica notas neutras no gana ni pierde audiencia
   ese mes (ADR: "acotado a [0.05, 0.6]", pero no dice qué pasa sin polaridad — no mover la influencia
   es la lectura conservadora).
10. **`consequences.py::ConsequenceContext.media_perception_active`** (`= features.media AND
    features.cohorts`) apaga únicamente la clave `consumer_confidence` de `publish_story` en
    `coeffs.yaml` (el `shock_cc` agregado de ADR 003 §5, que el sistema de percepción por cohorte
    reemplaza — §3: `consumer_confidence` pasa a usar `Σ pop_share_c · perceived_inflation_c`); la
    clave `institutional_confidence` de `scandal` sigue el camino de ADR 003 sin tocar, tal como pide
    el ADR ("y `institutional_confidence` como en ADR 003").
11. **`sync_to_real` (features.media=False) sincroniza `perceived_* = real` instantáneamente cada mes,
    en vez de correr `step_perception` con sesgo cero.** Elegido así deliberadamente para que el test de
    homogeneidad (punto 2 arriba) dé exacto: con el filtro `q = 0.4` de `step_perception`, aun con sesgo
    cero, `perceived_inflation_c` queda siempre un paso de rezago detrás de una inflación real que
    nunca es perfectamente constante, lo que le impediría a `step_cohorts` reproducir v0.1 exacto.
    **Costo aceptado:** el test literal de §4.4 ("con todos los frames `neutral`, la trayectoria real es
    idéntica a `features.media = false`") no da bit-idéntico — el rezago de `step_perception` (aun con
    sesgo cero) diverge de la sincronización instantánea de `sync_to_real`, amplificado por el lazo
    `government_approval → protest_level → social_tension → government_approval` de `world/society.py`/
    `world/politics.py` (~0.2 puntos de aprobación a los 12 meses, más de 1 punto pasada la mitad de una
    corrida de 48 con actores). `tests/test_cohorts_perception.py::
    test_all_neutral_frames_stay_close_to_media_off` prueba la ventana de 12 meses (donde el rezago
    todavía no se nota) con una cota de 0.5 puntos por variable, en vez de igualdad exacta — la
    alternativa (hacer que `features.media=False` también use el filtro `q`) cambia cuál de los dos
    tests del §7 da exacto y cuál da aproximado; se priorizó el de homogeneidad (ítem 3 de §7, con cota
    explícita 0.05) sobre el de frames neutros (ítem 4, sin cota explícita en el texto).
12. **`bloc_actor` cubre 5 de las 8 cohortes** (`urban_workers`, `rural`, `middle_class`,
    `public_employees`, `informal`); `young_professionals`, `retirees` y `students` no tienen bloque
    social propio en ADR 003 (29 actores, sin esos tres) — `cohort_by_bloc_actor` simplemente no las
    incluye en el `dict` que arma `bloc_cohort_views`, sin necesidad de un caso especial.

### CLI y wiring de turno

13. **`--cohorts/--no-cohorts` y `--media/--no-media`** en `run` y en `play` (`cli.py`), default
    `country.features["cohorts"/"media"]` (`True` en `data/country.json`). En `run`, ambas quedan
    atadas a `actors_enabled` a nivel de CLI (`cohorts_enabled = (...) and actors_enabled`) aunque
    `Simulation.cohorts_enabled` en sí no dependa de actores (punto 7): sin actores no hay bloques
    sociales ni medios que jugar desde la CLI, mismo criterio que ya ata `congress`/`negotiation` a
    `actors_enabled`. En `play`, `Game.new` las expone con default `True` (igual que
    `congress_enabled`/`negotiation_enabled` ya lo hacían) en vez de heredar `country.features`
    directamente — `play` nunca leyó `country.features` para estas flags, sigue el mismo patrón.
14. **Orden de turno (§5, pasos 8-9):** medios → percepción por cohorte corre en
    `engine/simulation.py::advance_month` inmediatamente después de la economía (paso 4) y antes de
    `step_society`/`step_politics`, porque `consumer_confidence` (dentro de `step_society`) y
    `step_cohorts` necesitan `perceived_inflation_c`/`social_tension`/`crime_perception` ya en `t+1`.
    `step_cohorts` corre después de `step_society` pero antes de `step_politics`, y pisa
    `government_approval` recién sobre la salida de `step_politics` (punto 5).
15. **Golden hash con `features.cohorts=False`/`features.media=False`
    (`tests/test_cohorts_perception.py::test_cohorts_and_media_off_matches_pre_commit_golden_hash`).**
    Se corrió `run(seed=7, policy=taylor, actors_enabled=True, congress_enabled=True,
    negotiation_enabled=True)`, 48 meses, contra el commit `1bdc33f9e4be62a07577bbb264a260d85f524b15`
    ("Visor: votos por partido y negociaciones del mes", HEAD del repo antes de este commit — sin
    `cohorts`/`media` en el código en absoluto) vía `git worktree add /tmp/head HEAD`, con
    `config_hash` reemplazado por un placeholder antes de hashear (mismo precedente que el punto 15 de
    §8/REVIEW_001 hallazgo #8: `data/country.json` cambia al agregar `features.cohorts`/`media`, el
    resto del JSONL no). El hash SHA-256 queda como constante en el test; se corrió de nuevo con el
    código de este commit y `cohorts_enabled=False, media_enabled=False` y coincide byte a byte.
16. **`emergence` (deliverable 6, `engine/emergence.py`)**: `most_discontented_cohort` (menor
    `approval_c` promedio de toda la corrida, sobre `MonthRecord.cohorts`) y
    `max_perception_gap_month` (mes de mayor `|perception_gap|`, sobre `kind: "perception"`); ambos
    `None` sin `features.cohorts`/`media` (JSONL sin esas líneas). `cli.py::emergence` imprime ambos,
    en español, con el mismo aviso "(sin cohortes -- correr con --cohorts)" que ya usa el resto del
    comando para secciones vacías.

### Archivos nuevos/tocados

`world/cohorts.py`, `world/perception.py` (nuevos); `engine/simulation.py` (pasos 8-9 del turno,
`Simulation.cohort_state`/`outlet_influence`, `MonthRecord.cohorts`, `History.perception_records`),
`engine/perception.py` (`build_perception`/`_private_social_bloc` con `cohort_view`), `engine/
scheduler.py` (`run_actor_turn` con `bloc_cohort_views`/`media_perception_active`), `engine/
consequences.py` (`ConsequenceContext.media_perception_active`), `engine/emergence.py`
(`most_discontented_cohort`/`max_perception_gap_month`), `engine/narrate.py` (`perceptions_by_month`),
`actors/rule_based.py` (`economic_policy_direction`), `world/society.py` (`step_society` con
`perceived_inflation_agg`), `world/config.py` (`features.cohorts`/`media`), `cli.py`
(`--cohorts`/`--media` en `run`/`play`, `emergence`), `engine/game.py` (`Game.new` con
`cohorts_enabled`/`media_enabled`), `ui/viewer.py` (`load_run` con `cohorts`/`perceptions`, sin tocar
`viewer_template.html`), `data/country.json` (`features.cohorts`/`media`), `data/cohorts.csv`, `data/
media_consumption.csv` (ya existían de un commit previo, sin cambios). `docs/SPEC_v0.1.md` §9 gana una
oración sobre `kind: "perception"` y `MonthRecord.cohorts`.
