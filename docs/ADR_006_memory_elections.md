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
