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
