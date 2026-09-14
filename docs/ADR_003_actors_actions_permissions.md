# ADR 003 — Actores, catálogo de acciones y permisos (Fase 3)

Estado: aceptado para implementar. Extiende `SPEC_v0.1.md` y `SPEC_v0.2_play.md`.

## 1. Decisión

Todo actor (humano, por reglas o IA) interactúa con el mundo **solo** emitiendo `Action` de un catálogo
cerrado. El motor las pasa por `authorize()`, aplica `consequences()` y recién ahí muta el estado.
No existe ningún otro camino para modificar `WorldState`. Un test lo garantiza: `WorldState` es
inmutable (`frozen=True`) fuera de `engine/`.

```
actor.decide(Perception) -> list[Action]
engine.authorize(actor, action) -> Allowed | Denied(reason)
engine.consequences(action, state, actors) -> StateDelta + RelationshipDelta + Events
```

## 2. Actores (`data/actors/*.yaml`)

29 actores en v0.3:

| Rol | Cantidad | ids |
|---|---|---|
| `president` | 1 | `president` (humano en `play`, reglas/IA en `run`) |
| `economy_minister` | 1 | `minister_economy` |
| `central_bank` | 1 | `central_bank` |
| `governor` | 8 | `gov_<provincia>` |
| `party` | 5 | `party_<id>` |
| `union` | 2 | `union_cgt` (general), `union_public` (estatales) |
| `business` | 3 | `biz_agro`, `biz_industry`, `biz_finance` |
| `media` | 3 | `media_nacional` (centro), `media_popular` (progresista), `media_mercado` (liberal) |
| `social_bloc` | 5 | `bloc_urban_workers`, `bloc_rural`, `bloc_middle_class`, `bloc_public_employees`, `bloc_informal` |

Ficha:

```yaml
id: gov_norte
name: Elena Ferreyra
role: governor
province: norte            # governor
party: alianza_provincial  # governor, party, president
ideology:      {economic: -0.4, social: 0.2, federalism: 0.9, institutionalism: 0.5}   # [-1, 1]
personality:   {ambition: 0.8, risk_tolerance: 0.6, loyalty: 0.4, pragmatism: 0.5}    # [0, 1]
interests:     [provincial_transfers, agricultural_exports, reelection]
influence:     {public: 0.3, congress: 0.15, streets: 0.2, markets: 0.05}             # [0, 1]
relationships: {president: 35, union_cgt: 70, biz_agro: 20}                            # [0, 100], default 50
```

`ideology ≠ interests ≠ personality`: una gobernadora puede coincidir ideológicamente con el
presidente y oponerse porque la política perjudica su provincia.

## 3. Percepción (`Perception`)

Lo único que un actor recibe. Se construye por rol (`engine/perception.py`) y es lo que después será
el prompt del agente IA (Fase 4). Nunca contiene el estado completo.

```python
class Perception(BaseModel):
    month: int
    date: str
    months_to_election: int
    public_indicators: dict[str, float]  # los 8 del tablero + inflation_annual
    private_indicators: dict[
        str, float
    ]  # por rol: governor → su provincia; central_bank → reservas exactas, etc.
    proposal: (
        PolicyProposal | None
    )  # lo que el gobierno propone este mes (delta de Policy + etiqueta)
    active_shocks: list[str]
    recent_events: list[str]
    relationships: dict[str, int]  # solo las propias
    memories: list[str]  # vacío hasta Fase 6
    goals: list[str]  # derivados de interests
```

## 4. Catálogo de acciones

Cada `Action` tiene `type`, `actor_id`, `target` (opcional), `params` validados por esquema, y
`reason` (texto libre, obligatorio: es lo que se evalúa en Fase 7).

| Tipo | Params | Permitido a |
|---|---|---|
| `SUPPORT_POLICY` | `intensity` [0,1] | todos salvo `president` |
| `OPPOSE_POLICY` | `intensity` | todos salvo `president` |
| `NEGOTIATE` | `requested_concession: ConcessionType`, `offer: str` | governor, party, union, business, minister |
| `PUBLIC_STATEMENT` | `stance: support\|oppose\|neutral`, `intensity` | todos |
| `LOBBY_CONGRESS` | `direction: for\|against`, `intensity` | governor, business, union, party |
| `FORM_ALLIANCE` / `BREAK_ALLIANCE` | `with: actor_id` | governor, party, union, business |
| `CALL_PROTEST` | `intensity` | union, social_bloc, party (solo oposición) |
| `STRIKE` | `sector: general\|public`, `days` [1,5] | union |
| `REQUEST_FUNDS` | `amount_pct_gdp` [0, 1] | governor |
| `WITHHOLD_INVESTMENT` / `INVEST` | `intensity` | business |
| `PUBLISH_STORY` | `frame: crisis\|recovery\|scandal\|neutral`, `target_bloc: bloc_id\|all` | media |
| `ENDORSE` / `CRITICIZE` | `target: actor_id` | media |
| `RECOMMEND_RATE` | `delta_pp` [−20, 20] | central_bank, minister |
| `SET_RATE` | `delta_pp` | central_bank **solo si** `governance.central_bank.autonomy >= 3` |
| `PROPOSE_POLICY` | `policy_delta` | president, minister (solo instrumentos fiscales) |
| `ENACT_POLICY` | `policy_delta` | president (si requiere ley: pasa por Congreso, Fase 5) |
| `GRANT_CONCESSION` | `to: actor_id`, `concession: ConcessionType` | president |
| `NO_ACTION` | — | todos |

`ConcessionType`: `restore_transfers`, `public_works`, `wage_bonus`, `tax_exemption`, `cabinet_seat`,
`delay_policy`. Cada concesión tiene un costo fiscal/político tabulado en `data/concessions.yaml`.

**Autorización.** `authorize()` verifica en orden: (1) el tipo está en la matriz del rol, (2) los params
validan, (3) condiciones de estado (ej. `CALL_PROTEST` requiere `party.in_government == false`;
`SET_RATE` requiere autonomía), (4) cooldowns (`STRIKE` máx. 1 cada 3 meses por actor), (5) presupuesto
de acciones por turno (máx. 3 por actor). Toda denegación se registra con `reason` y cuenta como
`authority_violation` (métrica de Fase 7). El motor **nunca** corrige una acción; la rechaza.

## 5. Consecuencias (`engine/consequences.py`)

Las acciones producen deltas que entran como términos `shock_*` del mes siguiente (misma vía que los
shocks y los dilemas) más cambios de relaciones. Tabla en `data/consequences.yaml`, escalada por
`influence` del actor. Valores de referencia (intensity = 1):

| Acción | Estado | Relaciones |
|---|---|---|
| `PUBLIC_STATEMENT oppose` | `approval −1.0·influence.public` | `president −2` |
| `PUBLIC_STATEMENT support` | `approval +0.6·influence.public` | `president +2` |
| `LOBBY_CONGRESS against` | `congress_support −2·influence.congress` | — |
| `CALL_PROTEST` | `protest +8·influence.streets`, `tension +2` | `president −3` |
| `STRIKE general` | `gdp −0.15·days`, `protest +12`, `approval −1.5` | `president −5`, `biz_* −3` |
| `STRIKE public` | `gdp −0.05·days`, `protest +6` | `president −3` |
| `WITHHOLD_INVESTMENT` | `gdp −0.2·influence.markets`, `consumer_confidence −2` | `president −2` |
| `INVEST` | `gdp +0.15·influence.markets`, `consumer_confidence +1` | `president +2` |
| `PUBLISH_STORY crisis` | `consumer_confidence −1.5·influence.public` (percepción real en Fase 5) | — |
| `PUBLISH_STORY recovery` | `consumer_confidence +1.0·influence.public` | — |
| `PUBLISH_STORY scandal` | `institutional_confidence −1·influence.public`, `approval −1` | objetivo `−4` |
| `REQUEST_FUNDS` | ninguno hasta que el presidente conceda | `president −1` si se rechaza |
| `GRANT_CONCESSION` | según `concessions.yaml` (ej. `restore_transfers`: `provincial_transfers +0.5`) | `to +8` |
| `FORM_ALLIANCE` | — | `with +10`, ambos ganan `influence.congress` compartido en Fase 5 |
| `BREAK_ALLIANCE` | — | `with −15` |
| `SUPPORT/OPPOSE_POLICY` | alimenta `congress_support` vía partidos: `Δ = ±1.5·intensity·seats/100` | `president ±1` |
| `RECOMMEND_RATE` | ninguno; se muestra al presidente (consejero) | — |
| `SET_RATE` | `interest_rate_target += delta_pp` | — |

Relaciones decaen hacia 50 a razón de 0.5/mes (olvido) hasta la memoria de Fase 6.

## 6. Decisión por reglas (`actors/rule_based.py`)

Para cada actor y cada `proposal` del mes:

```
score = w_ideo · ideological_fit(proposal, actor)          # [-100, 100]
      + w_int  · interest_impact(proposal, state, actor)   # [-100, 100]
      + w_rel  · (relationships.president − 50) · 2        # [-100, 100]
      + w_elec · electoral_pressure(actor, state, months_to_election)
      + noise(rng, σ = 5 · (1 − personality.pragmatism))
```
Pesos por defecto (`data/actor_weights.yaml`, por rol): `w_ideo 0.30, w_int 0.45, w_rel 0.15, w_elec 0.10`.
Los sindicatos y bloques sociales pesan más `w_int`; los partidos más `w_elec`; los medios usan otra
regla (sección 6.3).

**Umbrales:** `score > 20 → SUPPORT`, `< −20 → OPPOSE`, entre medio `NEGOTIATE` (si el rol puede) o
`NO_ACTION`. `intensity = min(1, |score| / 80)`.

**Escalada** (solo si `OPPOSE`): con probabilidad `risk_tolerance · intensity` el actor agrega una
acción fuerte que su rol permita: unión → `STRIKE`; bloque social → `CALL_PROTEST`; gobernador →
`LOBBY_CONGRESS` + `REQUEST_FUNDS`; empresa → `WITHHOLD_INVESTMENT`; partido → `LOBBY_CONGRESS`.
Todo actor añade `PUBLIC_STATEMENT` con su postura si `ambition > 0.5` o `intensity > 0.6`.

### 6.1 `ideological_fit`
Cada instrumento tiene una firma en el espacio ideológico (`data/policy_signatures.yaml`):

| Instrumento (+1 pp) | economic | social | federalism | institutionalism |
|---|---|---|---|---|
| `interest_rate_target` | +0.3 | 0 | 0 | +0.2 |
| `tax_rate` | −0.5 | +0.2 | 0 | +0.1 |
| `primary_spending` | −0.5 | +0.3 | 0 | −0.1 |
| `provincial_transfers` | −0.2 | 0 | +0.8 | 0 |
| `fx_intervention` | −0.2 | 0 | 0 | −0.2 |

`fit = 100 · cos_sim(signature(proposal_delta), actor.ideology)`, escalado por la magnitud del delta
(`min(1, |delta|/5)`); si no hay propuesta, 0.

### 6.2 `interest_impact`
Tabla `data/interests.yaml`: cada interés es una función del delta y del estado. Ejemplos:

| Interés | Impacto |
|---|---|
| `provincial_transfers` | `+15 · Δtransfers · dependence(provincia)` |
| `agricultural_exports` | `−20 · Δtax_rate · [flag export_taxes]` `+ 10 · Δfx (devaluación favorece)` |
| `real_wages` | `−12 · pos(inflation − 2) + 8 · Δreal_wage` |
| `employment` | `−15 · Δunemployment` |
| `price_stability` | `−10 · pos(inflation − 2)`, `+5 · Δinterest_rate/5` |
| `fiscal_balance` | `+10 · Δ(tax − spending)` |
| `low_taxes` | `−15 · Δtax_rate` |
| `cheap_credit` | `−8 · Δinterest_rate/5` |
| `public_employment` | `−15 · Δprimary_spending` si negativo |
| `reelection` | `+0.5 · (approval − 50)` si aliado, `−0.5 · (approval − 50)` si oposición |
| `audience` | (medios) `+10 · |Δaprobación|` |

`interest_impact = mean` de los intereses del actor, recortado a [−100, 100].

### 6.3 Medios
No puntúan propuestas. Cada mes eligen un `frame` según su línea (`economic` de su ideología) y el
estado: si `Δapproval < −2` o `inflation > 3` → `crisis` (más probable en medios opuestos al gobierno);
si `gdp_growth > 2` → `recovery`; si `event corruption_scandal` → `scandal`; si no, `neutral`.
`ENDORSE/CRITICIZE` al presidente según `relationships.president` y su línea.

### 6.4 Banco Central
Regla `TaylorPolicy` de v0.1 → `RECOMMEND_RATE(delta)`; con autonomía ≥ 3 emite `SET_RATE`.

## 7. Orden del turno (reemplaza §7 de SPEC_v0.1)

```
1. exógenas y shocks                       (igual que v0.1)
2. presidente decide: Policy + PROPOSE_POLICY (+ GRANT_CONCESSION a pedidos del mes anterior)
   - play: humano; run: PolicyRule (constant/taylor) o actor por reglas
3. perceptions = build_perception(actor, state, proposal) para cada actor
4. actions = [a for actor in actors for a in actor.decide(perception)]
5. authorized, denied = authorize_all(actions)         # log de ambos
6. deltas = consequences(authorized)                    # shock_* del mes + relaciones
7. economía / sociedad / política                        (igual que v0.1, con deltas sumados a shock_*)
8. eventos endógenos, fin de partida
9. MonthRecord + ActionRecord por acción (propuesta, veredicto, razón, consecuencias)
```

`actor.decide()` es determinista dado `(perception, rng_actor)`; cada actor tiene su propio
`random.Random(hash(seed, actor_id))` para que agregar un actor no cambie las decisiones de los demás.

## 8. Log

`ActionRecord` en el JSONL, una línea por acción:
```json
{"kind": "action", "month": 5, "actor": "gov_norte", "type": "OPPOSE_POLICY", "params": {"intensity": 0.8},
 "reason": "cut transfers hurts Norte", "authorized": true, "denied_reason": null,
 "score": {"ideo": 12, "int": -60, "rel": -6, "elec": -8, "total": -55},
 "consequences": {"approval": -0.3, "relationships": {"president": -2}}}
```

## 9. Tests (DoD de Fase 3)

1. **Matriz de permisos:** por cada rol, al menos una acción permitida y una prohibida; cada
   prohibida queda registrada como `denied` con `reason`.
2. **Interés vence ideología:** `gov_norte` (federalism 0.9, dependence 0.8) se opone a
   `provincial_transfers −1.0` aunque el presidente sea de su ideología económica; `gov_capital`
   (dependence 0.1) no.
3. **Inmutabilidad:** intentar mutar `WorldState` fuera del motor lanza excepción.
4. **Determinismo por actor:** agregar un actor nuevo no cambia las acciones de los existentes.
5. **Escalada:** con `risk_tolerance 1.0` e `intensity 1.0`, `union_cgt` emite `STRIKE` y el mes
   siguiente `protest_level` sube y `gdp` baja respecto del contrafáctico.
6. **Cooldown:** `STRIKE` no se autoriza dos meses seguidos para el mismo actor.
7. **Presupuesto de acciones:** la cuarta acción del mes de un actor se deniega.
8. **48 meses con 29 actores por reglas** corren en < 5 s y el JSONL contiene `action` records.

## 10. Lo que queda fuera (Fases 5–6)
Votación real en el Congreso, negociación multi-ronda, percepción por cohorte, memoria persistente.

## 11. Notas de implementación (Fase 3)

Ambigüedades, decisiones de diseño y valores inventados al implementar `actors/sheet.py`,
`actors/rule_based.py`, `actors/president_rules.py`, `engine/actions.py`, `engine/permissions.py`,
`engine/perception.py`, `engine/consequences.py`, `engine/scheduler.py` y la integración en
`engine/simulation.py`, `engine/game.py` y `cli.py`.

### Motor y compatibilidad hacia atrás

1. **`WorldState.frozen=True`.** Se agregó al modelo (secc. 1); no hacía falta tocar nada más:
   ningún código del motor asignaba atributos, solo `model_copy`/`model_construct`, que no pasan
   por `__setattr__`.
2. **`shock_congress` (nuevo término de motor).** `congress_support` (secc. 5.7 de `SPEC_v0.1`) no
   tenía un término `shock_*` propio (a diferencia de las demás variables políticas). Se agregó
   `shocks.term("shock_congress")` a `step_politics` (mismo estilo que `shock_cc` en Fase 2), para que
   `LOBBY_CONGRESS`/`SUPPORT_POLICY`/`OPPOSE_POLICY` puedan mover `congress_support` por la misma vía
   que todo lo demás. Con el término ausente (`0.0` default), el comportamiento sin actores no cambia.
3. **Defaults de función vs. defaults de la CLI, para no romper los 46 tests existentes.**
   `engine.simulation.run()`, `new_simulation()` y `Game.new()` mantienen `actors_enabled=False` como
   default *de la función* (así los tests que llaman `run(seed=..., months=...)` sin pedir actores
   siguen produciendo exactamente el mismo JSON). `features.actors` en `country.json` (default `true`)
   solo lo lee la CLI (`republica run`, con `--actors/--no-actors` para forzarlo); `republica play`
   arranca con actores **apagados** por default incluso con `features.actors=true` (ver punto 15).
4. **`GRANT_CONCESSION`/`SET_RATE` sobre instrumentos de `Policy` (términos `policy_*`).** Los
   `pending_terms` (mecanismo reusado de `world/events.py`/dilemas) solo sabían sumar a variables de
   `WorldState` vía `shock_*`. Una concesión que "restaura transferencias" cambia un instrumento de
   `Policy`, no una variable de estado. Se agregó una convención: toda clave `pending_terms` con
   prefijo `policy_<campo>` no entra a `ShockAggregate.terms`, se acumula aparte
   (`Simulation.pending_policy_delta`) y se suma/recorta a la `Policy` del mes siguiente
   (`actors/president_rules.py::apply_pending_policy_delta`), antes de construir la `PolicyProposal`
   de ese mes. Es decir: una concesión otorgada el mes `t` (a partir de pedidos del mes `t-1`) modifica
   recién la `Policy` de `t+1` — mismo desfasaje de un mes que el resto de las consecuencias.
5. **`Aux` que ve la percepción es la del mes anterior, no la del mes en curso.** El orden de turno
   (secc. 7) pide construir `perceptions` (paso 3) *antes* de correr la economía (paso 7), pero
   `economy.Aux` (`deficit`, `intervention_usd`, etc.) recién se calcula en el paso 7. Se resolvió
   guardando `ActorEngine.last_aux` (el `Aux` del mes anterior, `Aux` con todo en `0.0` en el mes 1) y
   pasándolo a `build_perception`; se actualiza con el `Aux` real apenas termina `step_economy`, para
   que el mes que viene ya lo vean los actores. Documentado también en el docstring de
   `engine/perception.py::build_perception`.
6. **`ActionRecord`/`kind: "relationships"` viven fuera de `MonthRecord` para garantizar bytes
   idénticos.** `MonthRecord` (`engine/simulation.py`) no ganó ningún campo nuevo: `History` guarda
   `action_records` aparte y los intercala en `to_jsonl()` justo después del `MonthRecord` de su mes.
   Con `action_records` vacío (actores apagados), `to_jsonl()` produce el mismo texto que antes de
   ADR 003 — verificado con `run(seed=7)`/`run(seed=42, taylor)` contra el HEAD anterior a esta fase
   (`tests/test_actors.py::test_no_actors_run_is_identical_regardless_of_how_its_disabled` y
   `test_no_actors_month_record_shape_is_unchanged`). El único byte que cambia al tocar `country.json`
   (se le agregó `"features": {"actors": true}`) es `config_hash` en la línea de resumen — inevitable
   al tocar el archivo de configuración, no relacionado con que los actores estén prendidos o no.
   Se decidió **no** implementar la alternativa del ADR ("una línea `relationships` cada 6 meses"):
   con el tiempo disponible para Fase 3 no había un consumidor real para esa foto (nada la lee); se
   deja `Relationships.snapshot()` ya escrito en `engine/consequences.py` para cuando haga falta
   (Fase 6/7), documentado en el propio docstring de `Relationships`.
7. **`months_to_election`.** ADR 003/004 lo mencionan como parte de `Perception`/percepción de
   partidos, pero no hay mecánica de elecciones (Fase 6). Se usa el mismo placeholder que
   `months_left` de los dilemas (`SPEC_v0.2_play.md`): `country.months - month + 1`.

### Actores y fichas

8. **`ActorSheet.role` como `party` guarda `party == id` (con prefijo `party_`), pero `governor`
   guarda el id de `parties.json` (sin prefijo).** Verificado en las 29 fichas ya escritas: por
   ejemplo `party_frente_federal.yaml` tiene `party: party_frente_federal`, pero `gov_norte.yaml`
   tiene `party: alianza_provincial`. Donde hacía falta resolver el partido de un actor de rol
   `party` (autorización de `CALL_PROTEST`, `_in_government` para `electoral_pressure`,
   `SUPPORT/OPPOSE_POLICY` sobre `congress_support`) se usa `actor.id.removeprefix("party_")`, no
   `actor.party`, para no depender de esa inconsistencia.
9. **Relaciones simétricas, no direccionales.** Las fichas declaran `relationships` por actor (ej.
   `gov_norte.relationships.president = 35` sin que `president.relationships.gov_norte` exista o
   coincida), pero la tabla de consecuencias (secc. 5) describe efectos como "relaciones: `president
   -2`" sin aclarar si es la vista del actor sobre el presidente, la del presidente sobre el actor, o
   ambas. Se implementó `Relationships` (motor) como **un único valor por par** `{a, b}` (no una
   matriz direccional), sembrado con el promedio de los valores que declaren ambas fichas si las dos
   lo hacen, o el que exista si solo una lo declara, o `50` si ninguna. Toda consecuencia mueve ese
   valor único, leído/escrito desde cualquiera de los dos lados por igual.

### Catálogo de acciones y permisos

10. **`SUPPORT_POLICY`/`OPPOSE_POLICY` "todos salvo `president`" incluye a `media`.** La lectura
    literal de la tabla de la secc. 4 es "todos los roles salvo `president`" (9 roles − 1); se agregó
    explícitamente a `media` en `data/permissions.yaml` aunque la regla de medios (secc. 6.3) nunca
    los emita (los medios no puntúan propuestas) — la matriz de permisos y la regla de decisión son
    cosas separadas a propósito, así un actor IA de Fase 4 podría hacerlo.
11. **`SET_RATE`/`RECOMMEND_RATE` reusan el mismo rango de `delta_pp` `[-20, 20]`.** El ADR solo da el
    rango explícito para `RECOMMEND_RATE`; se aplicó el mismo a `SET_RATE` por consistencia (evita una
    intervención de tasa descontrolada) en `engine/actions.py::RateParams`.
12. **Presupuesto de 3 acciones por turno no cuenta `NO_ACTION`.** El spec habla de "3 acciones por
    turno"; contar `NO_ACTION` (un actor "no hace nada") no tendría sentido práctico — un actor que
    emite `NO_ACTION` cuatro veces no debería quedar bloqueado para el resto del mes por eso. Ver
    `engine/permissions.py::authorize` (chequeo 5).
13. **`data/concessions.yaml` (costos fiscales/políticos) y `data/governance.yaml`
    (`central_bank.autonomy = 2`) son valores inventados para v0.3** (documentado también inline en
    cada archivo): `autonomy = 2` dejó al Banco Central sin poder emitir `SET_RATE` por default
    (consistente con que en v0.1 la tasa la fija la `PolicyRule`, no un Banco Central independiente),
    y los costos de concesión se calibraron a mano para que ninguna agote sola el presupuesto mensual
    del presidente (`0.8` pp de PIB) salvo `public_works` (la más cara, a propósito).

### Percepción

14. **`public_indicators` = `narrate.KEY_INDICATORS`.** "Los 8 del tablero" no están enumerados en
    ADR 003; se reusó el conjunto de 8 ya establecido en el proyecto (`gdp_growth`, `inflation`,
    `unemployment`, `exchange_rate`, `reserves`, `government_approval`, `political_stability`,
    `poverty`), más `inflation_annual` como pide la sección 3. Solo `inflation` (0.1) y `reserves`
    (centenas) tienen redondeo especificado en ADR 004 secc. 5; el resto se redondea a 1 decimal por
    consistencia.
15. **`private_indicators` con agregados fuera de la tabla de ADR 004 secc. 5** (todos documentados
    inline en `engine/perception.py`): se agregó `interest_rate` a `central_bank` (necesario para que
    pueda comparar contra la regla de Taylor, la tabla original no lo incluye); `dependence`,
    `income_p`, `transfers_received` (proxy: `provincial_transfers · dependence`) y
    `affected_by_shocks` (booleano como `float`, no la lista de shocks que pide la tabla — un
    `dict[str, float]` no puede llevar una lista) para `governor`; `public_employment` (proxy:
    `policy.primary_spending`, no existe una variable de estado con ese nombre) solo para
    `union_public`; `poll_approval` para `party` sin el ruido `± 3` que pide ADR 004 (`build_perception`
    no recibe `rng` en su firma — el ruido de encuestas queda para cuando la perspectiva de Fase 4
    decida si conviene agregarlo al muestreo del actor en vez de a la construcción de la percepción).
16. **`goals_from_interests` con 16 entradas**, cubriendo los 16 intereses usados en las 29 fichas
    (`data/actors/*.yaml`), no solo los que aparecen en la tabla de ejemplo de ADR 003 secc. 3.

### Decisión por reglas

17. **`w_ideo`/`w_int`/`w_rel`/`w_elec` de `party` y `union`/`social_bloc` en `data/actor_weights.yaml`
    son valores inventados** (el ADR solo pide "los sindicatos y bloques sociales pesan más `w_int`;
    los partidos más `w_elec`", sin números): `union`/`social_bloc` bajan `w_ideo` y `w_rel` a favor
    de `w_int`; `party` sube `w_elec` a 0.30 a costa de `w_int`. Todos los roles no listados usan
    `default` (los valores literales del ADR).
18. **`ideological_fit`: magnitud del delta = suma de valores absolutos de los instrumentos tocados**
    (no hay una única "magnitud" cuando una propuesta toca más de un instrumento a la vez; el ADR da
    la fórmula para un delta escalar).
19. **`interest_impact` para intereses sin fórmula en el ADR** (`social_programs`,
    `industrial_protection`, `financial_stability`, `law_and_order`, `party_unity` — solo mencionados
    como intereses de fichas, sin tabla en secc. 6.2): fórmulas inventadas del mismo orden de magnitud
    que las demás, en `actors/rule_based.py` (`_impact_social_programs`, etc.) con coeficientes en
    `data/interests.yaml`, documentadas en el YAML.
20. **Proxies para términos "Δ" que no son un instrumento de `Policy`** (`Δreal_wage`,
    `Δunemployment`, `Δaprobación` de la tabla de secc. 6.2): un actor por reglas no tiene una
    simulación económica propia para anticipar esos deltas a partir de la propuesta. Se usan proxies
    declarados en cada función de `actors/rule_based.py`: `real_wages` solo usa `pos(inflation - 2)`
    (sin el término `+8·Δreal_wage`); `employment` aproxima `Δunemployment` con una elasticidad chica
    sobre `Δprimary_spending`/`Δinterest_rate_target` (`data/interests.yaml`); `audience` usa
    `|aprobación - 50| / 10` en vez de `|Δaprobación|` (no hay aprobación del mes anterior a mano en
    `Perception`, que solo trae el estado actual).
21. **`agricultural_exports`: `Δfx` se interpreta como `-Δfx_intervention`** (menos intervención
    cambiaria → más devaluación esperada → favorece exportadores), no como un delta de
    `exchange_rate` (que no es un instrumento de `Policy` y no está en la propuesta). El flag
    `[export_taxes]` de la tabla del ADR no se modela (no hay tal flag en el estado ni en la
    propuesta): se asume siempre activo para los actores con este interés.
22. **`electoral_pressure` no tiene fórmula en el ADR** (solo el peso `w_elec`): se definió como
    `signo · proximidad · (aprobación - 50)`, con `proximidad = clamp(1 - months_to_election/12, 0, 1)`
    (rampa en los últimos 12 meses antes de "la elección") y `signo = +1` si el actor está alineado
    con el gobierno, `-1` si no. Solo `governor`/`party` tienen una noción clara de "en el gobierno"
    (via `parties.json.in_government`); el resto de los roles no siente presión electoral directa
    (`electoral_pressure = 0`).
23. **Concesión pedida en `NEGOTIATE`.** ADR 003 secc. 6 no dice qué `ConcessionType` pide cada rol al
    negociar: se asignó una por rol en `actors/rule_based.py::_NEGOTIATE_CONCESSION` (`governor` →
    `restore_transfers`, `party` → `cabinet_seat`, `union` → `wage_bonus`, `business` →
    `tax_exemption`, `economy_minister` → `delay_policy`), la más afín a cada uno.
24. **Regla de medios: `Δaprobación < -2` se aproxima con `aprobación < 45`.** Mismo problema que el
    punto 20 (no hay aprobación del mes anterior en `Perception`); se usa un umbral absoluto en vez
    de un delta.
25. **`hash((seed, actor_id))` → `zlib.crc32`.** El `hash()` builtin de Python trae salt aleatorio por
    proceso (`PYTHONHASHSEED`) para `str`/`tuple`, así que `random.Random(hash((seed, actor_id)))` no
    sería determinista entre corridas (rompería el test de aceptación 1, "run(7) == run(7)", en
    cuanto hubiera un actor de por medio). Se usa `zlib.crc32(f"{seed}:{actor_id}".encode())`
    (`actors/rule_based.py::actor_seed`), estable entre procesos.
26. **RNG por actor es una única instancia por partida, no una por mes.** "cada actor tiene su propio
    `random.Random(...)`" (secc. 7) se interpretó como una instancia construida una vez al arrancar la
    `Simulation`/`Game` (`ActorEngine.actor_rngs`) y reusada (mutando) mes a mes — no
    `random.Random(hash(seed, actor_id, month))` recalculada cada mes. Esto es lo que hace que
    agregar un actor nuevo no mueva la secuencia de RNG de los demás (test de aceptación 4): cada
    actor consume su propio generador en su propio orden, sin ningún generador compartido de por
    medio.
27. **`RuleBasedActor.last_score` es un efecto de lado, no parte de la firma de `decide()`.** El ADR
    fija la interfaz `decide(perception, rng) -> list[Action]`; para poder loguear el desglose del
    score en el `ActionRecord` (secc. 8) sin ensanchar esa firma, `decide()` deja el último
    `ScoreBreakdown` en `self.last_score` (`None` para `media`/`central_bank`, que no puntúan
    propuestas) y `engine/scheduler.py` lo lee inmediatamente después de llamar `decide()`.

### Consecuencias

28. **`LOBBY_CONGRESS(direction="for")` no está en la tabla de secc. 5** (solo da el caso `against`,
    `congress_support -2·influence.congress`): se agregó simétrico
    (`congress_support +2·influence.congress`) en `data/consequences.yaml`.
29. **`ENDORSE`/`CRITICIZE` no tienen deltas de relación tabulados en secc. 5**: se usó `+5`/`-5`
    (`engine/consequences.py::ENDORSE_RELATIONSHIP_DELTA`/`CRITICIZE_RELATIONSHIP_DELTA`), más chico
    que `FORM_ALLIANCE`/`BREAK_ALLIANCE` (`+10`/`-15`) por tratarse de un gesto público, no un pacto.
30. **`SUPPORT_POLICY`/`OPPOSE_POLICY` de un actor sin bancas no mueve `congress_support`.** La fórmula
    de secc. 5 (`Δ = ±1.5·intensity·seats/100`) supone `seats`, que solo tienen los partidos
    (`parties.json`); sindicatos, empresas, bloques sociales, etc. que hacen `SUPPORT`/`OPPOSE_POLICY`
    solo mueven `relationships.president` (con el mismo signo), no `congress_support`.
31. **`REQUEST_FUNDS`/`NEGOTIATE` del mes anterior se resuelven comparando contra los
    `GRANT_CONCESSION` efectivamente autorizados este mes** (`resolve_pending_requests`), no contra
    "lo que el presidente intentó conceder": si el presidente decide conceder pero esa acción se
    deniega (no debería pasar, `president`/`GRANT_CONCESSION` siempre está en la matriz, pero es la
    semántica correcta por si alguna vez se agrega una condición de estado a esa acción), el pedido
    queda como rechazado igual.
32. **Presidente por reglas (`run`) vs. presidente humano (`play`) resuelven pedidos distinto.**
    `RuleBasedPresident.decide_grants` (usado solo en `run`, `sim.president_rule is not None`) decide
    automático: concede si `relationships[solicitante][president] >= 55` y el costo entra en el
    presupuesto mensual (`0.8` pp de PIB, en orden de llegada de la lista de pedidos, sin priorizar
    por costo ni por relación). En `play`, el jugador decide a mano por pedido
    (`Game.set_grant_decisions`, deliverable 8: dilema generado "Conceder/Rechazar" en la CLI, no un
    objeto `Dilemma` de `dilemmas.py` — esos están atados a `Policy`/`effects` de dilemas de estado,
    no a pedidos de actores) y esa decisión se graba (`Game.grant_decision_log`) y se re-ejecuta en
    `Game.load` para que `--load` siga siendo determinista.
33. **`republica play --actors` apaga por default.** El deliverable 8 pide integrar actores al modo
    juego, pero `tests/test_play_cli.py` (ya existente, sin flags nuevos) verifica que el JSONL
    guardado tenga *exactamente* 49 líneas (48 meses + resumen) — con actores prendidos por default
    esas corridas ganarían líneas `"kind": "action"`. Se agregó `--actors/--no-actors` a `republica
    play` con default `False` (a diferencia de `republica run`, que por `features.actors` en
    `country.json` arranca en `True`): un usuario que quiere ver actores en su partida lo pide
    explícitamente con `--actors`.


## 12. Revisión del orquestador (v0.3)

Tras leer los registros de la semilla 7 se corrigieron tres cosas respecto del ADR original:
1. **`ideological_fit` es una proyección, no un coseno.** El coseno saturaba en ±100 para cualquier
   actor con la componente correcta, así que un empresario tibio reaccionaba a un recorte de 5 pp de
   tasa con `ideo = −93`. Ahora `fit = 100 · ⟨unit(firma), ideología⟩ · min(1, magnitud)`, con la
   magnitud **normalizada por instrumento** (`scales` en `policy_signatures.yaml`: tasa satura a 15 pp,
   impuestos y gasto a 3 pp del PIB, transferencias a 2, intervención a 0.5).
2. **Umbrales de ruido.** `NEGOTIATE` requiere `|score| ≥ 8` y `PUBLIC_STATEMENT` requiere
   `intensity ≥ 0.15`. Antes casi todos negociaban y declaraban todos los meses con intensidad 0.05
   (738 negociaciones en 48 meses; ahora ~370 con motivo).
3. **`NO_ACTION` no es una reacción.** El tablero y `narrate` no lo muestran; si no hay nada
   destacable, se dice.
