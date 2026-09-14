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
