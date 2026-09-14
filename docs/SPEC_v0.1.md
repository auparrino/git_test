# SPEC v0.1 — República de Aurora, mundo determinista

Estado: **implementado (v0.1)**; calibración registrada en `CALIBRATION_LOG.md`. Los coeficientes son hipótesis calibradas a mano para
producir un mundo *internamente coherente*, no un modelo econométrico. Viven en `data/country.json`
para poder ajustarlos sin tocar código.

> Checkpoint humano pendiente: revisar la sección 4 (fórmulas) y la sección 6 (shocks) con lápiz.
> Cualquier corrección se aplica en `data/country.json`; las fórmulas cambian solo si cambia la forma.

---

## 1. Convenciones

- **Turno = 1 mes.** Partida estándar: 48 meses desde enero 2027.
- **Unidades:** tasas mensuales en puntos porcentuales (pp) salvo indicación. `interest_rate` es anual.
  Para mostrar inflación anualizada: `((1 + π/100)^12 − 1) · 100`.
- **Determinismo:** `run(seed)` produce siempre la misma historia. Un único `random.Random(seed)`
  se consume en orden fijo (sección 7). Sin numpy en v0.1.
- **Actualización sincrónica en dos etapas:** la economía se calcula a partir del snapshot del mes `t`;
  la sociedad y la política se calculan a partir de la economía ya actualizada (`t+1`). Ver sección 7.
- **Acotación:** toda variable se recorta a su rango después de cada transición (`clamp`). Un test
  verifica que nunca aparece `NaN`/`inf`.
- **Notación:** `x` es el valor en `t`, `x'` el valor en `t+1`, `Δx = x' − x`. `pos(z) = max(0, z)`.

---

## 2. Estado del mundo (20 variables)

| Bloque | Variable | Unidad | Inicial | Rango | Significado |
|---|---|---|---|---|---|
| Economía | `gdp` | índice | 100.0 | [30, 400] | Nivel de actividad. Enero 2027 = 100. |
| | `gdp_growth` | % anual | 1.5 | [−30, 30] | Crecimiento anualizado suavizado. |
| | `inflation` | % mensual | 2.0 | [−1, 60] | Inflación m/m (2.0 ≈ 27 % anual). |
| | `unemployment` | % | 8.0 | [2, 40] | Desempleo. |
| | `real_wage` | índice | 100.0 | [30, 200] | Salario real. |
| | `interest_rate` | % anual | 30.0 | [0, 300] | Tasa de política. |
| | `exchange_rate` | índice | 100.0 | [10, 1e6] | Moneda local por USD (sube = devaluación). |
| | `reserves` | USD M | 8200 | [0, 200000] | Reservas internacionales. |
| | `public_debt` | % PIB | 60.0 | [0, 400] | Deuda pública. |
| | `fiscal_balance` | % PIB anual | −3.0 | [−30, 15] | Resultado fiscal total (negativo = déficit). |
| | `poverty` | % | 30.0 | [0, 95] | Pobreza. |
| Política | `government_approval` | 0–100 | 50 | [0, 100] | Aprobación del gobierno. |
| | `congress_support` | 0–100 | 45 | [0, 100] | % de bancas que votan con el gobierno. |
| | `political_stability` | 0–100 | 60 | [0, 100] | Estabilidad. Si cae por debajo del umbral, el gobierno cae. |
| | `social_tension` | 0–100 | 35 | [0, 100] | Tensión social latente. |
| | `institutional_confidence` | 0–100 | 45 | [0, 100] | Confianza en instituciones. |
| Sociedad | `consumer_confidence` | 0–100 | 50 | [0, 100] | Expectativas de consumo. |
| | `protest_level` | 0–100 | 15 | [0, 100] | Conflictividad visible. |
| | `inequality` | Gini | 42 | [20, 75] | Desigualdad. |
| | `crime_perception` | 0–100 | 50 | [0, 100] | Percepción de inseguridad. |

### 2.1 Exógenas (no son estado del país, pero se persisten)

| Variable | Inicial | Proceso |
|---|---|---|
| `commodity_price` | 100 | `c' = 100 + 0.9·(c − 100) + N(0, 3.0) + shocks` |
| `world_demand` | 100 | `w' = 100 + 0.9·(w − 100) + N(0, 1.5) + shocks` |

### 2.2 Parámetros estructurales (`country.json → structure`)

| Parámetro | Valor | Uso |
|---|---|---|
| `g_trend` | 0.2 | Crecimiento mensual tendencial (≈ 2.4 % anual). |
| `r_neutral` | 4.0 | Tasa real neutral anual. |
| `pi_world` | 0.25 | Inflación mensual internacional. |
| `u_nat` | 7.5 | Desempleo "natural". |
| `reserves_target` | 10000 | Nivel de reservas que el mercado considera cómodo. |
| `fx_debt_share` | 0.5 | Parte de la deuda en moneda extranjera. |

### 2.3 Instrumentos de política (`Policy`)

Son *inputs* del mes, no estado. En v0.1 los fija el jugador o una regla; en Fase 3+ los actores.

| Instrumento | Default | Rango | Efecto directo |
|---|---|---|---|
| `interest_rate_target` | 30.0 | [0, 300] | `interest_rate' = target` (ajuste inmediato). |
| `tax_rate` | 25.0 (% PIB) | [10, 45] | Ingresos fiscales. |
| `primary_spending` | 25.0 (% PIB) | [10, 45] | Gasto primario (incluye transferencias). |
| `provincial_transfers` | 6.0 (% PIB) | [0, 15] | Parte del gasto que va a provincias. Solo afecta ingresos provinciales en v0.1. |
| `fx_intervention` | 0.5 | [0, 1] | Cuánto defiende el BC el tipo de cambio con reservas. |

`PolicyRule` es una interfaz `decide(state, month) -> Policy`. v0.1 trae tres:
- `ConstantPolicy`: no hacer nada *en términos nominales* (tasa fija en 30). Es lo que hace un jugador
  que no toca nada; con inflación cambiante equivale a apretar o aflojar sin querer.
- `PassivePolicy` (**baseline de referencia y default de `run`/`batch`**): el BC sigue a la inflación
  del mes anterior manteniendo la tasa real en `r_neutral + 2`:
  `interest_rate_target = r_neutral + 2 + 12·inflation_lag1`. "No hacer nada" en términos reales.
- `TaylorPolicy`: `interest_rate_target = r_neutral + 12·π + 1.5·12·(π − 0.8)`, con `π` mensual;
  recortado al rango.

---

## 3. Variables auxiliares (se calculan cada mes, no se persisten como estado)

```
r_real        = interest_rate − 12·inflation                 # tasa real anual aproximada
r_gap         = r_real − r_neutral
g_m           = crecimiento mensual del mes (sección 4.1)
demand_gap    = g_m − g_trend
deficit       = −fiscal_balance                              # positivo = déficit
u_gap         = unemployment − u_nat
reserves_gap  = pos(reserves_target − reserves) / reserves_target   # 0 si sobran reservas
interest_cost = public_debt · 0.05                           # % PIB anual (tasa efectiva 5 %)
```

---

## 4. Transiciones económicas (etapa 1, desde el snapshot `t`)

Los coeficientes están en `country.json → coefficients` con el nombre indicado.

### 4.1 Actividad

```
g_m  = g_trend
     − a_r  · clamp(r_gap, r_gap_min, r_gap_max) / 100   # a_r = 2.0, r_gap_min = −10, r_gap_max = 30
                                                 # (10 pp de tasa real sobre neutral → −0.2 pp/mes; saturado:
                                                 #  tasas reales muy negativas no estimulan sin límite)
     + a_f  · (deficit − 3.0)                   # a_f  = 0.05  (déficit extra estimula a corto plazo)
     + a_c  · (consumer_confidence − 50) / 100  # a_c  = 0.3
     + a_x  · Δcommodity_price / 100            # a_x  = 1.0   (Δ del índice este mes)
     + a_w  · (world_demand − 100) / 100        # a_w  = 0.5
     − a_t  · pos(social_tension − 50) / 100    # a_t  = 0.4
     + shock_gdp

gdp'        = gdp · (1 + g_m / 100)
gdp_growth' = 0.7 · gdp_growth + 0.3 · (((1 + g_m/100)^12 − 1) · 100)
```

### 4.2 Tipo de cambio

```
de_raw = inflation − pi_world
       + b_res  · reserves_gap                  # b_res  = 1.5
       − b_r    · r_gap / 100                   # b_r    = 2.0
       + b_conf · (50 − institutional_confidence) / 100   # b_conf = 1.0
       − b_x    · Δcommodity_price / 100        # b_x    = 0.5
       + shock_fx                               # en pp de variación mensual

cap    = inflation + b_band                     # b_band = 1.0 (banda tolerada sobre la inflación)
excess = pos(de_raw − cap)
de     = de_raw − fx_intervention · excess
intervention_usd = b_int · fx_intervention · excess · (gdp / 100)    # b_int = 150 (USD M por pp de exceso)

exchange_rate' = exchange_rate · (1 + de / 100)
```

Si `reserves < intervention_usd`, el BC no puede intervenir: `de = de_raw`, `intervention_usd = 0`.

### 4.3 Inflación

```
inflation' = rho_pi · inflation                       # rho_pi = 0.85 (inercia)
           + c_e · de                                 # c_e    = 0.06 (pass-through; ver CALIBRATION_LOG)
           + c_g · demand_gap                         # c_g    = 0.5
           + c_f · pos(deficit − 2.0)                 # c_f    = 0.12 (déficit no financiable → emisión)
           − c_r · r_gap / 100                        # c_r    = 1.0
           + shock_pi
```

Estado estacionario de referencia: con los valores iniciales, `inflation' ≈ 2.0`. Un test lo verifica
(tolerancia ±0.15 en el mes 1 con semilla fija y shocks desactivados).

### 4.4 Desempleo

```
unemployment' = unemployment
              − d_g · demand_gap                      # d_g = 0.6  (Okun mensual)
              + d_n · (u_nat − unemployment) · (−1)   # reversión: d_n = 0.02 → u se acerca a u_nat
              + d_w · pos(real_wage − 100) / 100      # d_w = 0.05
              + shock_u
```
(Escrito explícitamente: `u' = u − d_g·demand_gap + d_n·(u − u_nat)·(−1)·(−1)`... para evitar ambigüedad:
`u' = u − d_g·demand_gap − d_n·(u − u_nat) + d_w·pos(real_wage−100)/100 + shock_u`.)

### 4.5 Salario real

```
wage_growth_nominal = w_idx · inflation_prev           # w_idx = 1.0 (indexación completa al mes anterior)
                    + w_prod                            # w_prod = 0.1 (productividad)
                    + w_g · demand_gap                  # w_g = 0.3
                    − w_u · u_gap / 10                  # w_u = 0.3
real_wage' = real_wage · (1 + (wage_growth_nominal − inflation') / 100)
```

`inflation_prev` es la inflación del mes anterior al snapshot (guardar `inflation_lag1` en el
estado interno; el primer mes usa `inflation`). Mecánica clave: **una aceleración inflacionaria
erosiona el salario real; una desinflación lo recupera.**

### 4.6 Resultado fiscal y deuda

```
revenue  = tax_rate · (1 + f_rev · demand_gap)         # f_rev = 0.3 (estabilizador automático)
spending = primary_spending + f_u · pos(u_gap)          # f_u   = 0.1
fiscal_balance' = revenue − spending − interest_cost + shock_fiscal

public_debt' = public_debt
             + deficit' / 12                            # deficit' = −fiscal_balance'
             − public_debt · g_m / 100                  # el crecimiento licúa
             + public_debt · fx_debt_share · (de − inflation) / 100   # valuación por devaluación real
             + shock_debt
```

### 4.7 Reservas

```
reserves' = reserves
          + k_tb   · (commodity_price − 100)            # k_tb   = 20   (USD M por punto)
          + k_w    · (world_demand − 100)               # k_w    = 10
          + k_k    · clamp(r_gap, r_gap_min, r_gap_max)   # k_k = 15 (carry, saturado)
          − k_conf · pos(50 − institutional_confidence) # k_conf = 10
          − intervention_usd
          + shock_reserves
```

Con valores iniciales: `+30 − 50 = −20 USD M/mes` (drenaje leve: presión para actuar).

### 4.8 Pobreza (ajuste hacia objetivo)

```
poverty_target = 30 + p_u·(unemployment' − 8) − p_w·(real_wage' − 100) + p_i·(inequality − 42)
                 # p_u = 0.8, p_w = 0.4, p_i = 0.5
poverty' = poverty + p_adj · (poverty_target − poverty)   # p_adj = 0.25
```

---

## 5. Transiciones sociales y políticas (etapa 2, usan la economía `t+1`)

Todos los `Δ` de esta sección son `x' − x` de la etapa 1.

### 5.1 Confianza del consumidor
```
cc_target = 50 + s_g·(gdp_growth' − 1.5) − s_u·(unemployment' − 8) − s_pi·pos(inflation' − 2) + s_w·(real_wage' − 100)
            # s_g = 2.0, s_u = 1.5, s_pi = 3.0, s_w = 0.3
consumer_confidence' = cc + s_adj·(cc_target − cc)      # s_adj = 0.3
```

### 5.2 Desigualdad (lenta)
```
inequality' = inequality + q_pi·pos(inflation' − 2) + q_u·(unemployment' − 8)/10 − q_w·(real_wage' − 100)/100
              − q_t·(provincial_transfers − 6)/10 + shock_ineq
              # q_pi = 0.05, q_u = 0.02, q_w = 0.5, q_t = 0.05
```

### 5.3 Tensión social
```
tension_target = 35 + t_u·(unemployment' − 8) + t_p·(poverty' − 30) + t_pi·pos(inflation' − 2)
               − t_w·(real_wage' − 100) − t_c·(institutional_confidence − 45) + t_pr·(protest_level − 15)
               # t_u = 0.8, t_p = 0.5, t_pi = 1.5, t_w = 0.3, t_c = 0.2, t_pr = 0.2
social_tension' = tension + t_adj·(tension_target − tension) + shock_tension    # t_adj = 0.2
```

### 5.4 Protesta
```
protest_target = 15 + pr_t·(social_tension' − 35) − pr_a·(government_approval − 50)
                 # pr_t = 0.8, pr_a = 0.2
protest_level' = protest + pr_adj·(protest_target − protest) + shock_protest    # pr_adj = 0.3
```

### 5.5 Percepción de inseguridad (lenta)
```
crime_target = 50 + cr_u·(unemployment' − 8) + cr_p·(poverty' − 30) + cr_t·(social_tension' − 35)
               # cr_u = 0.5, cr_p = 0.3, cr_t = 0.3
crime_perception' = crime + cr_adj·(crime_target − crime)   # cr_adj = 0.1
```

### 5.6 Aprobación del gobierno
```
approval' = approval
          + e_w  · Δreal_wage_pct                    # e_w  = 1.5   (Δ% del índice)
          − e_u  · Δunemployment                     # e_u  = 2.0
          − e_pi · pos(inflation' − 2.0)           # e_pi = 0.8 (castigo por inflación alta)
          + e_pi_low · (2.0 − clamp(inflation', 0, 2)) # e_pi_low = 0.3 (premio acotado por desinflación; la deflación no premia)
          + e_g  · demand_gap                        # e_g  = 3.0
          − e_t  · pos(social_tension' − 50) / 10    # e_t  = 1.0
          + e_rev· (45 − approval)                   # e_rev = 0.03 (reversión lenta)
          + shock_approval
```

### 5.7 Apoyo en el Congreso
```
congress_target = coalition_seats + cg_a·(government_approval' − 50)   # coalition_seats = 45 (de parties.json), cg_a = 0.3
congress_support' = congress + cg_adj·(congress_target − congress)     # cg_adj = 0.2
```

### 5.8 Confianza institucional (lenta)
```
institutional_confidence' = ic + ic_rev·(50 − ic) − ic_pi·pos(inflation' − 3) + ic_s·(political_stability − 60)/10 + shock_conf
                            # ic_rev = 0.02, ic_pi = 0.5, ic_s = 0.1
```

### 5.9 Estabilidad política
```
stability_target = 60 + st_a·(government_approval' − 50) + st_c·(congress_support' − 45)
                 − st_t·(social_tension' − 35) + st_i·(institutional_confidence' − 45)
                 # st_a = 0.3, st_c = 0.3, st_t = 0.4, st_i = 0.2
political_stability' = stability + st_adj·(stability_target − stability) + shock_stability   # st_adj = 0.15
```

---

## 6. Shocks

Cada mes, para cada shock en orden de catálogo, se sortea `U(0,1) < p(state)`. Un shock activo tiene
`duration` meses; sus efectos mensuales se suman a los términos `shock_*` de las fórmulas (o modifican
exógenas). Un shock no puede reactivarse mientras está activo. Máximo 2 shocks nuevos por mes.

| id | Nombre | p mensual | Duración | Efectos por mes (salvo indicación) |
|---|---|---|---|---|
| `drought` | Sequía | 0.02 | 3 | `shock_gdp −0.3`, `shock_reserves −400`, provincias agro: `income −10 %` |
| `commodity_boom` | Boom de commodities | 0.03 | 6 | mes 1: `commodity_price +20` (una vez); `shock_reserves +300` |
| `corruption_scandal` | Escándalo de corrupción | 0.03 | 1 | `shock_approval −6`, `shock_conf −5`, `shock_tension +5` |
| `general_strike` | Huelga general | 0.02 + 0.05·[tension > 55] | 1 | `shock_gdp −0.4`, `shock_protest +20`, `shock_approval −2` |
| `international_crisis` | Crisis internacional | 0.015 | 3 | mes 1: `world_demand −8`, `commodity_price −10`; `shock_reserves −500`, `shock_fx +5` (solo mes 1) |
| `flood` | Inundación | 0.02 | 2 | `shock_gdp −0.2`, `shock_fiscal −0.5` (3 meses), provincia Litoral `income −8 %` |
| `energy_discovery` | Descubrimiento energético | 0.005 | 12 | `shock_reserves +200`, `shock_gdp +0.1`, mes 1: `consumer_confidence +3` |
| `epidemic` | Epidemia | 0.01 | 2 | `shock_gdp −0.8`, `shock_u +0.5` (mes 1), `shock_fiscal −1.0` (3 meses) |
| `banking_crisis` | Crisis bancaria | 0.005 + 0.03·[inflation > 6 or reserves < 3000] | 2 | mes 1: `shock_reserves −800`, `shock_fx +10`, `shock_conf −8`; `shock_gdp −0.6` |
| `protest_wave` | Ola de protestas | 0.01 + 0.04·[tension > 60] | 1 | `shock_protest +25`, `shock_stability −5`, `shock_approval −3` |
| `growth_surprise` | Crecimiento inesperado | 0.03 | 2 | `shock_gdp +0.4`, mes 1: `consumer_confidence +4` |
| `trade_partner_collapse` | Caída de un socio comercial | 0.01 | 4 | mes 1: `world_demand −10`; `shock_reserves −300` |

`[cond]` vale 1 si la condición se cumple. Los efectos "mes 1" se aplican una sola vez.
Los shocks se pueden forzar desde la CLI (`--force-shock drought@5`) para tests y escenarios.

### 6.1 Eventos endógenos (no se sortean; se disparan por estado)

| Evento | Condición | Efecto |
|---|---|---|
| `forced_devaluation` | `reserves' < 500` | `exchange_rate' ·= 1.25`, `shock_pi +5` el mes siguiente, `shock_conf −10`, `reserves' += 1500` (rescate/ajuste). Máximo una vez cada 6 meses. |
| `government_collapse` | `political_stability < 15` durante 3 meses consecutivos | Fin de partida, `outcome = "collapse"`. |
| `hyperinflation` | `inflation > 20` durante 3 meses consecutivos | Fin de partida, `outcome = "hyperinflation"`. |
| `term_end` | mes 48 | Fin de partida, `outcome = "survived"`. |

---

## 7. Orden del turno (determinista)

```
1. exógenas:   commodity_price, world_demand  (consume RNG: 2 gauss)
2. shocks:     sorteo por catálogo en orden (consume RNG: 12 uniform), activación, efectos del mes
3. política:   policy = policy_rule.decide(state, month); interest_rate' = target
4. economía:   4.1 → 4.2 → 4.3 → 4.4 → 4.5 → 4.6 → 4.7 → 4.8  (todo desde el snapshot t + shocks)
5. sociedad:   5.1 → 5.2 → 5.3 → 5.4 → 5.5
6. política:   5.6 → 5.7 → 5.8 → 5.9
7. clamp de todas las variables
8. eventos endógenos (6.1) y chequeo de fin de partida
9. registro: MonthRecord (estado, exógenas, policy, shocks activos, eventos, auxiliares)
10. month += 1
```

Provincias en v0.1: solo derivadas para narración y para Fase 3. Cada provincia tiene
`unemployment_p = unemployment + u_offset` e `income_p = 100 · (1 + sector_effect + transfers_effect)`, con
`transfers_effect = 0.5·(provincial_transfers − 6)/6 · dependence` y `sector_effect` de shocks.

---

## 8. Datos (`data/`)

### `country.json`
```json
{
  "name": "República de Aurora",
  "start": {"year": 2027, "month": 1},
  "months": 48,
  "initial_state": { ...20 variables... },
  "exogenous": {"commodity_price": 100, "world_demand": 100},
  "structure": {"g_trend": 0.2, "r_neutral": 4.0, "pi_world": 0.25, "u_nat": 7.5, "reserves_target": 10000, "fx_debt_share": 0.5},
  "coefficients": { "a_r": 2.0, "a_f": 0.05, ... todos los de las secciones 4 y 5 ... },
  "default_policy": {"interest_rate_target": 30, "tax_rate": 25, "primary_spending": 25, "provincial_transfers": 6, "fx_intervention": 0.5},
  "terminal": {"collapse_stability": 15, "collapse_months": 3, "hyper_inflation": 20, "hyper_months": 3, "devaluation_reserves": 500}
}
```

### `provinces.csv`
| id | name | population_k | gdp_share | main_sector | governor_party | u_offset | dependence |
|---|---|---|---|---|---|---|---|
| norte | Norte | 900 | 0.06 | agro | alianza_provincial | +3.0 | 0.8 |
| litoral | Litoral | 1300 | 0.11 | agro | frente_federal | +1.0 | 0.6 |
| capital | Capital | 2800 | 0.34 | services | union_republicana | −1.5 | 0.1 |
| centro | Centro | 1500 | 0.14 | industry | frente_federal | 0.0 | 0.4 |
| cuyo | Cuyo | 700 | 0.06 | mining | union_republicana | +0.5 | 0.5 |
| pampa | Pampa | 1600 | 0.17 | agro | frente_federal | −0.5 | 0.3 |
| patagonia | Patagonia | 500 | 0.07 | energy | movimiento_libertad | −1.0 | 0.4 |
| costa | Costa | 700 | 0.05 | services | partido_social | +2.0 | 0.7 |

(población total 10.000 k; `gdp_share` suma 1.0)

### `parties.json`
| id | name | seats (de 100) | economic | social | in_government |
|---|---|---|---|---|---|
| frente_federal | Frente Federal | 38 | −0.3 | 0.2 | true |
| union_republicana | Unión Republicana | 30 | 0.5 | 0.1 | false |
| partido_social | Partido Social | 14 | −0.8 | 0.6 | false |
| movimiento_libertad | Movimiento Libertad | 10 | 0.9 | −0.2 | false |
| alianza_provincial | Alianza Provincial | 8 | 0.0 | 0.0 | false (aliado: `coalition_weight 0.85`) |

`coalition_seats = 38 + 0.85·8 ≈ 45`.

### `shocks.json`
El catálogo de la sección 6, con `id, name, base_p, conditional_p: [{when, add}], duration, effects: [{target, value, when: "each"|"first"}]`.

---

## 9. Interfaz de código

```python
# src/republica/world/state.py
class WorldState(BaseModel): ...20 campos + inflation_lag1 (interno)...
class Exogenous(BaseModel): commodity_price: float; world_demand: float
class Policy(BaseModel): ...5 instrumentos...

# src/republica/world/economy.py
def step_economy(state, exo, policy, shocks, params, rng) -> tuple[WorldState, Aux]

# src/republica/world/society.py / politics.py
def step_society(prev, new, shocks, params) -> WorldState
def step_politics(prev, new, shocks, params) -> WorldState

# src/republica/world/events.py
class ShockCatalog: roll(state, exo, rng, active) -> list[ActiveShock]
def endogenous_events(state, params, history) -> list[Event]

# src/republica/engine/simulation.py
@dataclass MonthRecord: month_index, date, state, exo, policy, aux, shocks, events
@dataclass History: records: list[MonthRecord], outcome: str, seed: int, config_hash: str
def run(seed: int, months: int = 48, policy_rule: PolicyRule | None = None,
        forced_shocks: dict[int, list[str]] | None = None, country: Country | None = None) -> History
def advance_month(sim: Simulation) -> MonthRecord   # para uso interactivo (Fase 2)
```

CLI (`typer`):
- `republica run --seed 7 --months 48 --policy constant|taylor --force-shock drought@5 --out simulations/run_7.jsonl`
- `republica narrate simulations/run_7.jsonl` — narración mes a mes (sección 10).
- `republica batch --seeds 1000 --summary` — corre N semillas y muestra distribución de outcomes y percentiles de inflación anual, desempleo, aprobación final.

Formato JSONL: una línea por mes con `MonthRecord` serializado + una línea final `{"outcome": ..., "seed": ..., "config_hash": ...}`.

---

## 10. Narración

`narrate` imprime por mes: fecha, tabla de 8 indicadores clave con flechas (`▲▼`), shocks nuevos y
activos, eventos endógenos, y frases automáticas por umbral (por ejemplo, "La inflación anualizada
supera el 50 %", "La aprobación cae por debajo del 30 %", "Las reservas bajan de USD 3.000 M").
Al final: outcome y resumen (inflación acumulada, variación del PIB, desempleo final, aprobación final).

---

## 11. Tests de aceptación (DoD de Fase 1)

1. **Determinismo:** `run(7) == run(7)` (igualdad de JSON completo).
2. **Cotas y NaN:** 1.000 semillas × 48 meses con `ConstantPolicy`: ninguna variable fuera de rango antes del clamp por más de 3 rangos, cero `NaN/inf`.
3. **Estado estacionario:** semilla fija, shocks desactivados, exógenas sin ruido: en el mes 1, `|inflation' − 2.0| < 0.15`, `|Δunemployment| < 0.1`, `|Δapproval| < 1.0`.
4. **Sequía:** `--force-shock drought@5` vs. misma semilla sin forzar: `reserves` menor en los meses 6–9 y `government_approval` menor en al menos uno de los meses 6–9.
5. **Tasa:** política que sube la tasa 15 pp en el mes 1 vs. constante, misma semilla, sin shocks: `inflation` menor en el mes 12 y `unemployment` mayor en el mes 12.
6. **Emisión:** `primary_spending = 32` (déficit ≈ 10 % PIB) vs. default, sin shocks: inflación anualizada del mes 24 al menos 15 pp mayor.
7. **Distribución de outcomes:** en 1.000 semillas, `survived` entre 50 % y 95 % tanto con `ConstantPolicy` como con `PassivePolicy`, y `passive ≥ constant`. (Si queda fuera, se recalibra `country.json`, no el test.)
8. **Narración legible:** `narrate` de la semilla 7 no lanza excepciones y contiene al menos una frase de umbral.

---

## 12. Supuestos discutibles (marcados para el checkpoint humano)

- **Indexación salarial completa (1.0) con un mes de rezago.** El salario real solo se erosiona cuando la inflación *acelera* y se recupera cuando desacelera. Con 0.8 (primera versión) se erosionaba un 10 % en 48 meses aun con inflación en baja: incoherente. Ver CALIBRATION_LOG.
- **Pass-through cambiario 0.10 por pp.** Alto para una economía cerrada, razonable para una bimonetaria.
- **Déficit > 2 % del PIB se monetiza.** No hay mercado de deuda en v0.1. Es una simplificación fuerte que hace que el gasto sea inflacionario casi de inmediato.
- **Tasa efectiva de la deuda 5 % fija.** Ignora que subir la tasa de política encarece la deuda. Se puede acoplar en v0.2 (`interest_cost = debt · (0.03 + 0.3·interest_rate/100)`).
- **Reversión de aprobación hacia 45.** Encarna el "desgaste" de gobernar. Sin esto, un gobierno sin shocks se estabiliza donde arrancó.
- **Colapso a estabilidad < 15 por 3 meses.** Umbral arbitrario; calibrar con la distribución de outcomes (test 7).
- **Sin mercado de deuda, sin Congreso activo, sin provincias con presupuesto propio.** Entran en Fases 3 y 5.
