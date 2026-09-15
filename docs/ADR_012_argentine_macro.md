# ADR 012 — Macro con régimen: expectativas, tipo de cambio efectivo y balance de pagos

Estado: aceptado para implementar. Responde al diagnóstico de la validación A4
(`data/countries/argentina/validation/a4_main/report.md`). Todo detrás de `features.macro_regime`
(default off); Aurora sigue byte a byte igual con el flag apagado.

## 1. Diagnóstico que este ADR corrige

| Hallazgo A4 | Consecuencia |
|---|---|
| Persistencia total de precios `rho_pi + c_e < 1` | La inflación revierte a la media por construcción: hiperinflación imposible sin forzarla |
| `fx_regime` no entra en `step_economy` | `peg` y `float` producen la misma trayectoria: la convertibilidad no se puede simular |
| Reservas sin ancla de balance de pagos (`reserves_target` fijo) | Con reservas reales altas el término no muerde; el default endógeno nunca se dispara |
| Aprobación cae a 0 y todo colapsa antes de 2023 | Sin recuperación de largo plazo, cualquier corrida > 5 años termina en colapso |

## 2. Precios con expectativas y dominancia fiscal (`features.macro_regime`)

Reemplaza §4.3 de SPEC v0.1 **solo con el flag**:

```
pi_exp   = w_adapt · inflation_lag1 + (1 − w_adapt) · pi_anchor      # expectativas adaptativas + ancla
pi_anchor: si fx_regime ∈ {peg, crawl}: la tasa de crawl (0 para peg) + pi_world; si no: EMA(36) de la inflación
rho_eff  = rho_pi + rho_slope · clamp((inflation_lag1 − pi_hi) / pi_hi, 0, 2)   # rho_pi=0.85, rho_slope=0.10, pi_hi=5
           # con inflación mensual > 5 % la indexación se acorta y la persistencia sube hasta 1.05
money_demand = md_0 · exp(−md_pi · inflation_lag1)                             # md_0=0.12 (M/PIB), md_pi=0.08
seigniorage_pressure = pos(deficit − financeable) / money_demand                # financeable = f(default_active, reserves): 2 normal, 0 en default
inflation' = rho_eff · inflation
           + c_e · de
           + c_g · demand_gap
           + c_s · seigniorage_pressure                                          # c_s = 0.06, reemplaza a c_f·pos(deficit−2)
           − c_r · r_gap / 100
           + (1 − rho_eff) · pi_exp                                             # el ancla solo pesa cuando la persistencia es baja
           + shock_pi
```
Propiedad: con déficit financiable y ancla creíble converge; con déficit no financiable y demanda de
dinero cayendo, `seigniorage_pressure` crece de forma convexa y `rho_eff` supera 1: la hiperinflación
es un régimen alcanzable, no un shock. Test: desde 1988-06 real, sin shocks forzados, ≥ 50 % de
semillas cruzan 20 % mensual en ≤ 18 meses; desde 2003-06 real, ninguna.

## 3. Régimen cambiario efectivo

`fx_regime` pasa a gobernar §4.2:

| Régimen | `de` | Intervención | Salida |
|---|---|---|---|
| `float` | `de_raw + x_d · dollar_demand` | `fx_intervention` del jugador | — |
| `crawl(rate)` | `rate` mientras `reserves > R_min` | vende `k_int · pos(de_raw − rate) · gdp` | si `reserves < R_min`: salto a `float` con `de = de_raw` acumulado (devaluación forzada), evento `fx_regime_exit` |
| `peg` | 0 mientras `reserves > R_min` | vende toda la presión: `intervention = k_int · pos(de_raw) · gdp`; además `k_k` alto (entra capital) mientras `default_risk < 0.3` | idem; la salida del peg dispara `shock_conf −15`, `banking_crisis` con p = 0.5 |
| `control` | `de = de_admin` (crawl administrado) y `fx_gap` = brecha endógena: `gap' = gap + g1·(dollar_demand − g2·r_real) − g3·gap`; la brecha entra en precios (`c_gap · fx_gap`), en reservas (`−k_gap · gap`) y en percepción | mínima | levantamiento de controles: `de` salta `+fx_gap` |

`R_min = rm · importaciones mensuales` (3 meses). `dollar_demand` (ya existe) pasa a alimentar `de_raw`.

## 4. Balance de pagos

Reemplaza §4.7:

```
exports  = X0 · (commodity_price/100)^ex_c · (rer/100)^ex_e          # rer = tipo de cambio real (índice)
imports  = M0 · (gdp/100)^im_y · (rer/100)^(−im_e) · (1 + im_gap·fx_gap)
current_account = exports − imports − interest_paid_usd
capital_account = k_k · r_gap · [default_risk < 0.5] − k_flight · dollar_demand − amortizations + disbursements(imf_program, sovereign_default=0)
reserves' = reserves + current_account + capital_account − intervention_usd + shock_reserves
default_risk = sigmoid(a·(external_debt_usd/exports_12m) − b·(reserves/imports_3m) + c·pos(deficit−2))
```
`X0`, `M0` se leen del estado inicial real cuando existen (`history/` tiene PIB en USD y, vía el script
local, exportaciones e importaciones; hasta entonces `X0 = M0 = 0.18·gdp_usd/12`, documentado como proxy).
Test: desde 1998-01 real con `peg`, reservas caen y el peg sale antes del mes 54 en ≥ 50 % de semillas.

## 5. Recuperación de largo plazo (también para Aurora, detrás del mismo flag)

```
institutional_confidence' += ic_rec · pos(ic_target − ic)     # ic_rec = 0.01; ic_target = 45 + 10·[12 meses sin crisis]
social_tension' −= t_rec · pos(tension − tension_base) · [inflation < 3 y unemployment < 10]   # t_rec = 0.02
government_approval: e_rev hacia 45 pasa a ser hacia 45 + 10·(economic_sentiment/100)         # el desgaste tiene piso si la economía va bien
```
Test: desde 2003-06 real, ≥ 80 % de semillas llegan a 2015-12 sin colapso.

## 6. Calibración y validación (protocolo nuevo)

- **Ventana de entrenamiento 1992-01:2023-12** (incluye 2001 y 2018–2023). **Holdout 1983-12:1991-12**
  (hiperinflación y convertibilidad temprana): nunca visto por esta estructura. Series mensuales
  antes de 1997 se interpolan de anuales y se pesan a 0.5 (documentado).
- Pérdida con **cola pesada**: error en unidades normalizadas elevado a 1.5, para que los episodios
  extremos pesen.
- Se repiten V1, V2, V3 con las mismas hipótesis del ADR 011 §8 (V3 ahora es in-sample y se declara),
  más **V4 2019-12→2023-12** con partidos argentinos (ADR 013): hipótesis registrada: el oficialismo
  pierde en > 70 % de semillas y la inflación final mediana supera 100 %.

## 7. Tests
1. Flag off: Aurora golden byte a byte.
2. Hiperinflación alcanzable (§2) y no espuria (2003-06 → 0 %).
3. `peg` ≠ `float` (trayectorias distintas) y salida forzada con reservas bajas.
4. Balance de pagos: commodities +20 % sube reservas; devaluación real sube exportaciones.
5. Recuperación: 2003-06 → 2015-12 sin colapso en ≥ 80 %.
6. Calibración quick sobre sintético con la nueva estructura recupera ≥ 50 % de 10 coeficientes perturbados.
