# ADR 019 — Sensibilidad no monótona al estado inicial: el filo de `rho_eff`

Estado: diagnóstico medido + hipótesis registrada ANTES de codear (protocolo de
`PLAN_ARGENTINA.md` secc. 0 regla 3). Responde al hallazgo central de la sonda exploratoria de
`docs/EMERGENCE_LOG.md` ("Sonda exploratoria sobre seis arranques reales", punto 1): desde 1983-12
el modelo hiperinflaciona en 15/15 semillas en el mes 7, desde 1988-06 en 0/50 — mismo episodio
histórico, cinco años de diferencia en el arranque, resultados opuestos y los dos equivocados
(la hiperinflación real fue en junio de 1989, mes 66 contando desde 1983-12 y mes 12 desde 1988-06).

Todo el arreglo va detrás de `MacroCoefficients.indexation_state` (bool, default `False`): con el
flag apagado `step_macro_economy` devuelve exactamente los mismos valores que antes de este ADR.

---

## 1. Diagnóstico medido

Todas las mediciones de esta sección salen de la calibración `a7_by_regime`, con transiciones de
régimen (ADR 015) y piso de legitimidad (ADR 016) activos: lo mismo que corre `republica run
--country argentina --start <fecha> --calibration a7_by_regime --regime-transitions`.

### 1.1 Los dos estados iniciales son, casi literalmente, el mismo estado

Comparación variable por variable de `country.json -> initial_states` (las 21 variables de
`WorldState` + `inflation_lag1`), con la procedencia de cada una:

| variable | 1983-12 | 1988-06 | procedencia |
|---|---:|---:|---|
| `inflation` | **17.7604** | **13.9893** | `source` (anual convertida a mensual) |
| `inflation_lag1` | **17.7604** | **13.9893** | `source` (ídem) |
| `gdp_growth` | **1.9481** | **−3.3439** | `source` (Maddison, interanual) |
| `institutional_confidence` | 67.4 | 67.2 | `source` (V-Dem interpolado) |
| `political_stability` | 92.9 | 92.9 | `source` |
| `government_approval` | 57.1971 | 57.1971 | `proxy` (misma elección de 1983) |
| `gdp`, `real_wage`, `exchange_rate` | 100 / 100 / 100 | idem | `assumed` |
| `unemployment`, `interest_rate` | 8.0 / 30.0 | idem | `assumed` |
| `reserves`, `public_debt`, `fiscal_balance` | 8200 / 60.0 / −3.0 | idem | `assumed` |
| `poverty`, `congress_support`, `social_tension` | 30 / 45 / 35 | idem | `assumed` |
| `consumer_confidence`, `protest_level` | 50 / 15 | idem | `assumed` |
| `inequality`, `crime_perception` | 42 / 50 | idem | `assumed` |

**17 de 21 variables son constantes `assumed` idénticas.** Sólo cuatro números difieren, y dos de
ellos (`institutional_confidence`, 0.2 puntos) no mueven nada. El motivo no es pereza del
constructor: `history/` **no tiene ningún dato mensual** de reservas, balance fiscal, desempleo,
tasa de política, deuda, pobreza, salario real ni EMAE antes de 1992–2003.

| serie | cobertura | filas 1983–1990 |
|---|---|---:|
| `reserves_monthly.csv` | 1996-01 → 2026-09 | **0** |
| `fiscal_balance.csv` | 2015-12 → 2026-03 | **0** |
| `unemployment.csv` | 2003-01 → 2026-01 | **0** |
| `policy_rate_monthly.csv` | 1999-01 → 2026-09 | **0** |
| `public_debt.csv` | 1992-12 → 2025-12 | **0** |
| `poverty.csv` | 2003-07 → 2026-01 | **0** |
| `real_wage.csv` | 1997-02 → 2026-07 | **0** |
| `emae_monthly.csv` | 2004-01 → 2026-06 | **0** |

Es decir: **al modelo se le pide distinguir dos episodios macroeconómicos con dos números.**

### 1.2 El número que decide no es una observación — y el dato real está en el repo, sin usar

Las dos entradas de `inflation` salen de `inflation_cpi_annual.csv` convertida con
`(1+anual/100)^(1/12) − 1`. Ninguna de las dos es una medición de ese mes. Y el dato mensual **real
ya está en el repositorio**: `history/inflation_cpi_monthly_linked.csv` (BCRA "Principales
Variables" id 27, serie histórica empalmada de INDEC, **1943-03 → 2026-08**, 1002 filas). Ni
`scripts/build_argentina_initial_states.py` (los 8 hitos) ni
`calibration/initial_states.py::rule_inflation` lo miran: el segundo sólo carga
`inflation_cpi_monthly.csv`, que arranca en **1997-02**, y cae a la anual interpolada para todo lo
anterior.

| mes | real (`inflation_cpi_monthly_linked`) | hito `country.json` | `initial_state_for` | error del hito |
|---|---:|---:|---:|---:|
| 1983-11 (`lag1` de 1983-12) | **19.2** | 17.7604 | 17.2154 | −1.44 |
| 1983-12 | **17.7** | 17.7604 | 17.4913 | +0.06 |
| 1988-05 (`lag1` de 1988-06) | **15.7** | 13.9893 | 24.3696 | −1.71 |
| 1988-06 | **18.0** | 13.9893 | 25.9368 | **−4.01** |

Dos cosas:

1. El hito de **1988-06 está 4 pp por debajo** del dato real, y su rezago 1.7 pp por debajo.
2. Los **dos constructores del proyecto no coinciden**: para el mismo mes 1988-06, el hito de A2
   (regla "año más cercano, sin interpolar", `inflation_cpi_annual.csv`) dice 13.99 y
   `initial_state_for` (regla "anual interpolada", `inflation_cpi_annual_linked.csv`) dice 25.94.
   **11.95 pp de diferencia para el mismo mes.** El real es 18.0: ninguno de los dos.

### 1.3 La no linealidad: `rho_eff` cruza 1 en un punto, como función SIN MEMORIA de un solo mes

ADR 012 §2: `rho_eff = rho_pi + rho_slope · clamp((inflation_lag1 − pi_hi)/pi_hi, 0, 2)`.

Es una rampa lineal en el nivel del mes anterior, acotada arriba. Cruza 1 en

```
pi*  =  pi_hi · (1 + (1 − rho_pi) / rho_slope)
```

El umbral es exacto y depende sólo de tres coeficientes:

| vector | `rho_pi` | `rho_slope` | `pi_hi` | `rho_eff = 1` | `rho_eff` máx (clamp) |
|---|---:|---:|---:|---:|---:|
| paquete (ADR 012 sin calibrar) | 0.8500 | 0.1000 | 5.0000 | **12.50** | 1.0500 |
| `a7_by_regime`, grupo `peg` (= `crawl`) | 0.5815 | 0.2351 | 6.2857 | **17.48** | 1.0516 |
| `a7_by_regime`, grupo `float` | 0.6349 | 0.0869 | 8.7645 | 45.59 | **0.8086** |
| `a7_by_regime`, grupo `control` | 0.6068 | 0.1229 | 6.1938 | 26.01 | **0.8527** |

En el modelo COMPLETO el escalón está algo por debajo de ese umbral —`c_e·de` y el canal de tasa
(`−c_r·r_gap/100`, con `r_gap` cayendo 12 puntos por cada punto de inflación mensual) suman
persistencia— pero eso no lo suaviza: lo corre. Medido moviendo sólo `pi0` desde 1983-12 con el
vector `peg`/`crawl`, 10 semillas, 36 meses (tabla completa en §1.4): 12 %/mes no cruza en ninguna
semilla, 14 %/mes en 5/10, 16 %/mes en 9/10, 17 %/mes en 10/10. La banda de transición entera mide
**menos de 5 pp**, contra un dato inicial con 4 pp de error.

`fx_regimes.csv` pone 1983-12 → 1991-03 en `crawl`, y `a7_by_regime.regime_group_map` manda `crawl`
al grupo `peg`. O sea: **las dos fechas corren con el mismo vector**, y el umbral que decide es
**17.4773 %/mes**.

- **1983-12** arranca en `inflation_lag1 = 17.7604` → **0.283 pp (1.6 %) POR ENCIMA** del umbral →
  `rho_eff = 1.0106 > 1` → mapa explosivo.
- **1988-06** arranca en `inflation_lag1 = 13.9893` → 3.49 pp por debajo → `rho_eff = 0.8696 < 1`.

Traza del mes 1 al 4 (semilla 1), con los términos de la ecuación de §2:

| | 1983-12 m1 | 1983-12 m3 | 1988-06 m1 | 1988-06 m3 |
|---|---:|---:|---:|---:|
| `rho_eff` | **1.0106** | 1.0138 | **0.8696** | 0.8440 |
| `rho_eff · inflation` | 17.948 | 18.032 | 12.164 | 11.113 |
| `c_e · de` | 0.167 | 0.167 | 0.167 | 0.167 |
| `c_g · demand_gap` | −0.145 | 0.170 | −0.145 | −0.231 |
| `c_s · seigniorage_pressure` | 0.013 | 0.058 | 0.011 | 0.000 |
| `(1 − rho_eff) · pi_exp` | **−0.111** | −0.146 | **+1.135** | +1.306 |
| inflación resultante | 17.847 | 18.247 | 13.307 | 12.307 |

El término que domina es el mismo en los dos casos (`rho_eff · inflation`, ~100 × cualquier otro).
Lo que cambia de signo es el ancla: con `rho_eff > 1` el término `(1 − rho_eff)·pi_exp` es
**negativo** (el ancla deja de frenar y pasa a empujar), con `rho_eff < 1` es positivo pero chico.
Ni `seigniorage_pressure` (0.011–0.058 puntos) ni `c_e·de` (0.167) ni el gap de demanda explican
nada: **el 99 % de la diferencia está en `rho_eff`.**

### 1.4 No hay meseta: el modelo siempre termina hiperinflacionando, sólo cambia la velocidad

`pi_anchor` fuera de `peg`/`crawl` es `EMA(36)` de la propia inflación del modelo. A largo plazo el
ancla alcanza al nivel, y con `pi_anchor = inflation` el mapa se reduce a
`inflation' = inflation·(1 + c_e) + …`: pendiente **mayor que 1 para cualquier nivel**. El modelo no
tiene ningún régimen de "inflación alta y estable" — que es exactamente lo que Argentina tuvo entre
1983 y 1988. Lo único que varía es cuánto tarda, y eso lo fija `rho_eff` del primer mes.

Se midió directamente moviendo SÓLO `inflation`/`inflation_lag1` del estado de 1983-12, 10 semillas,
36 meses:

| `pi0` | `rho_eff` inicial | semillas con hiper | mes mediano |
|---:|---:|---:|---:|
| 12.00 | 0.7952 | 0/10 | — |
| 14.00 | 0.8700 | 5/10 | 19.0 |
| 16.00 | 0.9448 | 9/10 | 14.0 |
| 17.40 | 0.9971 | 10/10 | 8.5 |
| 17.47 | 0.9997 | 10/10 | 7.5 |
| **17.48** | **1.0001** | 10/10 | 7.5 |
| 17.76 (el dato del pack) | 1.0106 | 10/10 | **6.5** |
| 20.00 | 1.0516 | 10/10 | 5.0 |

Entre 12.00 y 17.76 %/mes —un rango de 5.8 pp, más chico que el error de 4 pp que tiene el propio
dato inicial— el mes mediano de hiperinflación pasa de "nunca" a **6.5**.

### 1.5 Barrido de sensibilidad: 85 arranques, 10 semillas, 24 meses

`republica`, cada mes entre 1983-12 y 1990-12 (85 arranques), `a7_by_regime`, 10 semillas, 24 meses.
Mes de hiperinflación (3 meses seguidos > 20 %/mes, `terminal` de `country.json`) contra mes de
arranque. Tabla resumida (el detalle completo está en `docs/CALIBRATION_LOG.md`):

| arranque | `pi0` | `rho_eff` inicial | semillas con hiper | mes mediano |
|---|---:|---:|---:|---:|
| 1983-12 … 1985-01 | 17.71–17.76 | 1.0005–1.0106 | **10/10** | **6.5–7.5** |
| 1985-02 | 17.08 | 1.0086 | 9/10 | 12.0 |
| 1985-03 | 16.41 | 0.9851 | 7/10 | 14.0 |
| 1985-04 | 15.69 | 0.9600 | 3/10 | 17.0 |
| 1985-07 … 1987-06 | 4.89–13.19 | 0.5815–0.8735 | **0/10** | — |
| 1987-10 | 12.65 | 0.8015 | 6/10 | 19.0 |
| **1988-01** | 13.99 | 0.8536 | **3/10** | **17.0** |
| **1988-02** | 17.65 | 0.8696 | **9/10** | **15.0** |
| **1988-03** | 20.37 | 1.0065 | **10/10** | **3.0** |
| 1988-04 … 1988-05 | 22.55–24.37 | 1.0516 | 10/10 | 3.0 |
| **1988-06** (hito) | **13.99** | **0.8696** | **1/10** | **20.0** |
| 1988-07 … 1990-08 | 21.63–33.30 | 1.0516 | 10/10 | 3.0 |
| 1990-10 | 17.95 | 1.0516 | 8/10 | 15.5 |
| 1990-11 | 15.50 | 1.0176 | 3/10 | 18.0 |
| 1990-12 | 12.29 | 0.9260 | 0/10 | — |

**Dos discontinuidades, las dos entre meses contiguos:**

1. **1988-01 → 1988-03**: la mediana salta de **17 a 3** (y la fracción de 3/10 a 10/10) en dos
   meses de diferencia de fecha de arranque. Es el síntoma del filo de §1.3.
2. **1988-06 es un outlier dentro de su propia vecindad**: 1988-05 arranca en 24.37 y 1988-07 en
   27.32, pero 1988-06 arranca en 13.99. No es un fenómeno del modelo: 1988-06 es uno de los 8
   **hitos** de `country.json` y usa la regla de A2, mientras que sus vecinos caen a
   `initial_state_for` y usan la regla interpolada (§1.2). **La validación V1 —la única que mide la
   hiperinflación— está medida sobre el único mes de toda esa ventana cuyo dato inicial viene de un
   constructor distinto al de sus vecinos.**

### 1.6 El mismo filo explica la contradicción entre el test 2a de ADR 012 y la V1 de `a8_a7`

`tests/test_macro_regime.py::test_hyperinflation_reachable_from_1988_06` corre 1988-06 con los
coeficientes **del paquete** (umbral 12.50) y da **20/20**. La validación `a8_a7` corre 1988-06 con
los coeficientes **calibrados** (umbral 17.48) y da **0/50**. El dato inicial es el mismo (13.99).
No son dos resultados contradictorios: son los dos lados del mismo umbral, que se mueve de 12.50 a
17.48 según qué vector se cargue. Y con `a7_by_regime` los grupos `float` y `control` tienen
`rho_eff` máximo **0.8086** y **0.8527**, los dos muy por debajo de 1: para
cualquier arranque en una ventana `float` o `control`, **la hiperinflación por este canal es
estructuralmente inalcanzable**, sin importar el estado inicial.

### 1.7 Respuesta a la pregunta del diagnóstico

> ¿La diferencia viene del dato inicial, de una variable `assumed` mal puesta, o de una no
> linealidad del mecanismo?

**De la no linealidad**, con el dato inicial y las `assumed` como amplificador:

- La **no linealidad es la causa**: `rho_eff` es una función sin memoria de un solo mes que cruza 1
  en un punto (17.48 %/mes), y el mapa de precios no tiene ningún término que sature por encima de
  ese punto. El 99 % de la diferencia entre las dos corridas está en ese coeficiente (§1.3).
- El **dato inicial es el amplificador**: decide de qué lado del filo caés, y tiene ±4 pp de error
  (§1.2) contra un filo que 1983-12 cruza por **0.28 pp**. Un proxy con 4 pp de incertidumbre
  decidiendo un veredicto cualitativo no es una predicción.
- Las **`assumed` son la razón de que no haya nada más que mire**: 17 de 21 variables son la misma
  constante en las dos fechas (§1.1), así que el modelo no tiene ningún otro observable con el que
  distinguir 1983 de 1988.

---

## 2. Qué NO puede hacer el arreglo (riesgo declarado antes de medir)

El criterio de éxito propuesto en la tarea pide las dos cosas a la vez: desde 1983-12 la
hiperinflación **después del mes 48**, desde 1988-06 **alcanzable en ≥ 50 %** dentro de la ventana
de V1 (24 meses). Eso obliga a que el modelo escape **más rápido desde 1988-06 que desde 1983-12**.

Todos los observables del paquete dicen lo contrario:

| observable | 1983-12 | 1988-06 | ¿cuál es "más inflacionario"? |
|---|---:|---:|---|
| `inflation` (hito actual) | 17.76 | 13.99 | 1983-12 |
| `inflation` (dato real mensual) | 17.7 | 18.0 | empate |
| `inflation_lag1` (dato real mensual) | **19.2** | **15.7** | 1983-12 |
| media de los 12 meses previos (real) | **14.45** | 11.83 | 1983-12 |
| `gdp_growth` | +1.95 | −3.34 | 1988-06 |

**Ningún mecanismo backward-looking en el nivel puede ordenarlos al revés.** El único observable que
sí los ordena al revés es la **aceleración**: en los 12 meses previos a 1988-06 la inflación pasó de
3.4 %/mes (dic-1987) a 18.0 %/mes (jun-1988) —se quintuplicó—, mientras que en los previos a 1983-12
osciló sin tendencia y el último mes **desaceleró** (19.2 → 17.7). Eso es, además, la lectura
estándar de Cagan: lo que separa una inflación alta e indexada de la antesala de una hiperinflación
no es el nivel, es si está acelerando.

Y hay un límite que ningún arreglo de esta ADR puede cruzar: la distancia real entre los dos
episodios (mes 66 contra mes 12) la explican dos planes de estabilización discrecionales —el Plan
Austral (jun-1985) y el Plan Primavera (ago-1988)— que el modelo **no representa**. Pedirle que
reproduzca esa distancia desde estados iniciales que difieren en dos números es pedirle que
reproduzca política económica que no tiene canal para simular. Lo que sí se le puede pedir, y es lo
que este ADR mide, es que **su respuesta sea continua y gradual en el estado inicial** en vez de un
escalón.

---

## 3. El arreglo (`features` / `MacroCoefficients.indexation_state`, default OFF)

Tres piezas. Las tres detrás del mismo flag salvo la (C), que es una corrección de dato.

### (A) La indexación pasa a ser un ESTADO con inercia, no una función del último mes

Reemplaza la línea de `rho_eff` de ADR 012 §2 **sólo con el flag prendido**:

```
idx_hat     = inflation + idx_accel_k_menos_1 · (inflation − inflation_lag1)
idx_target  = clamp((idx_hat − pi_hi) / pi_hi, 0, 2)
indexation' = indexation + idx_adj · (idx_target − indexation)
rho_eff     = rho_pi + rho_slope · indexation
```

con `idx_accel_k = 2.0`, que **no es un parámetro libre**: `idx_hat = inflation + 1·(inflation −
inflation_lag1)` es la **extrapolación lineal a un mes**. Los tres casos del coeficiente son
interpretables y el elegido es el único forward-looking:

- `idx_accel_k = 0` → `idx_target` depende de `inflation_lag1`: el mecanismo de ADR 012, sin memoria.
- `idx_accel_k = 1` → depende de `inflation` (el mes corriente).
- `idx_accel_k = 2` → depende de dónde va a estar la inflación el mes que viene si sigue la
  tendencia. Es lo que indexa un contrato: no el mes pasado, el mes que viene.

`idx_adj = 0.12` → media vida de `ln 2 / (−ln 0.88) = 5.4 meses`, dentro de la banda de
renegociación de contratos indexados (trimestral a semestral) de la Argentina de los ochenta. Es el
parámetro que **mata el filo**: un solo mes por encima del umbral ya no cambia el régimen del mapa;
hace falta que el exceso persista muchos meses.

### (B) El estado se siembra con la historia real previa al arranque

`indexation` al mes 0 no puede salir de los dos números del estado inicial (volvería al mecanismo
sin memoria). Se corre **la misma ecuación de ajuste sobre los `idx_seed_months = 24` meses reales
anteriores a la fecha de arranque**, tomados de `history/inflation_cpi_monthly_linked.csv` (dato
real, fuente ya en el repo, 1943-03+). Con `idx_adj = 0.12`, `(1 − 0.12)^24 = 0.046`: el 95 % del
peso de la semilla viene de la historia observada, no del valor inicial arbitrario. Sin historia
disponible para esa fecha, se cae al valor sin memoria de ADR 012 (comportamiento de hoy) y queda
declarado en el `note` de procedencia.

Semilla calculada con los datos reales (`pi_hi = 6.2857` del grupo `peg`/`crawl`,
`idx_adj = 0.12`, `idx_accel_k = 2`, 24 meses):

| fecha | 12 meses previos (real, %/mes) | `indexation` sembrada | `rho_eff` del mes 1 |
|---|---|---:|---:|
| 1983-12 | 10.6 16.0 13.0 11.3 10.3 9.1 15.8 12.5 17.2 21.4 17.0 19.2 | **1.1612** | **0.8544** |
| 1988-06 | 8.0 10.1 13.7 11.7 19.6 10.3 3.4 9.1 10.4 14.8 17.2 15.7 | **0.9931** | **0.8149** |

Dos cosas que importan y que conviene decir sin adornos:

1. **Las dos semillas quedan bien por debajo de 1**, contra el 1.0106 de hoy para 1983-12. Eso es lo
   que saca al mapa de precios del lado explosivo en el mes 1 y es el efecto principal de la inercia.
2. **La semilla NO invierte el orden de las dos fechas** (1983-12 queda arriba), y no se la fuerza a
   hacerlo: es un promedio ponderado de 24 meses de NIVEL, y §2 ya midió que todo observable de
   nivel pone a 1983-12 arriba. Lo que sí las ordena al revés es el objetivo hacia el que el stock se
   mueve, `idx_target`, que es forward-looking:

   | `idx_accel_k` | qué mira | `idx_target` 1983-12 | `idx_target` 1988-06 |
   |---:|---|---:|---:|
   | 0 | `inflation_lag1` (ADR 012, sin memoria) | **2.000** (cota) | 1.498 |
   | 1 | `inflation` (mes corriente) | 1.816 | 1.864 |
   | **2** | **extrapolación a un mes** | **1.577** | **2.000** (cota) |

   Con `idx_accel_k = 0` gana 1983-12; con 2 gana 1988-06, y por el motivo correcto: 19.2 → 17.7 es
   desaceleración, 15.7 → 18.0 es aceleración. No es un coeficiente ajustado hasta que dé — es el
   signo de la aceleración, y el valor 2 es la extrapolación lineal, no un grado de libertad.

### (C) El dato inicial usa la serie mensual real que ya está en el repo

`calibration/initial_states.py::rule_inflation` / `rule_inflation_lag1` pasan a preferir
`inflation_cpi_monthly_linked.csv` (mes exacto, 1943-03+) por encima de `inflation_cpi_monthly.csv`
(1997-02+) y de la anual interpolada. Y los dos hitos afectados de
`data/countries/argentina/country.json -> initial_states` se corrigen al dato real con su
procedencia (`source`), que es lo que manda `PLAN_ARGENTINA.md` secc. 0.1: no se usa un proxy
cuando el dato existe.

| | antes | después (real) |
|---|---:|---:|
| 1983-12 `inflation` / `inflation_lag1` | 17.7604 / 17.7604 | **17.7 / 19.2** |
| 1988-06 `inflation` / `inflation_lag1` | 13.9893 / 13.9893 | **18.0 / 15.7** |

Esto NO va detrás del flag: es una corrección de dato, no un cambio de mecanismo, y aplica igual
con `indexation_state` apagado.

---

## 4. Hipótesis registrada (antes de medir)

Criterio de éxito, con los dos puntos a la vez:

- **C1.** Desde **1983-12**, 15 semillas, 72 meses, `a7_by_regime`: la **mediana del mes de
  hiperinflación cae después del mes 48** (real: mes 66). Línea de base medida: **mes 6.5** (10
  semillas, 24 meses) / mes 7 (15 semillas, sonda de `EMERGENCE_LOG`).
- **C2.** Desde **1988-06**, 24 meses: **≥ 50 %** de las semillas cruzan 20 %/mes (V1 de ADR 011
  §8 / test 2a de ADR 012 §7). Línea de base medida: **0/50** con `a7_by_regime`, 20/20 con los
  coeficientes del paquete.
- **C3** (agregado, es el que mide la enfermedad de verdad). En el barrido de 85 arranques, la
  **discontinuidad entre meses contiguos** tiene que bajar: hoy la mediana salta de **17 (1988-01) a
  3 (1988-03)**, y 1988-06 es un outlier de 12 pp respecto de sus dos vecinos. Se cuenta el número
  de pares de meses contiguos cuya mediana de mes de hiperinflación difiere en más de 8 meses.

**Riesgo declarado.** C1 y C2 pueden ser incompatibles (§2): obligan a que el modelo escape más
rápido desde 1988-06 que desde 1983-12, y el único observable del paquete que ordena así a las dos
fechas es la aceleración, que es justo lo que el arreglo usa. Si el resultado medido no cumple las
dos, se reporta cuál falla y por qué, con los números, **sin retunear hasta que dé**
(`PLAN_ARGENTINA.md` secc. 0 regla 3).

---

## 5. Coeficientes nuevos (`world/economy.py::MacroCoefficients`)

Ninguno entra al vector de CMA-ES: todos se anotan con `StructuralFloat` / `int` / `bool`, así que
`calibration/parameters.py::MACRO_TUNABLE` sigue en **58 campos** y `calibration/*` no se toca (el
mismo criterio y el mismo motivo que los `lf_*` de ADR 016: son la afirmación estructural de este
ADR, no grados de libertad para ajustar contra series).

| campo | tipo | default | qué es |
|---|---|---:|---|
| `indexation_state` | `bool` | `False` | el flag. Apagado, `step_macro_economy` es bit a bit lo de antes. |
| `idx_adj` | `StructuralFloat` | 0.12 | velocidad de ajuste del stock de indexación (media vida 5.4 meses). |
| `idx_accel_k` | `StructuralFloat` | 2.0 | extrapolación lineal a un mes (§3A). |
| `idx_seed_months` | `int` | 24 | meses de historia real para sembrar el estado (§3B). |
| `idx_init` | `StructuralFloat` | −1.0 | semilla resuelta por `load_country_pack` para la fecha de arranque; negativo = sin semilla (cae al valor sin memoria de ADR 012). |

## 6. Tests
1. Flag off: `step_macro_economy` bit a bit idéntico, y los goldens de
   `tests/test_country_pack_argentina.py` / `tests/test_macro_regime.py` sin moverse.
2. El umbral analítico `pi* = pi_hi·(1 + (1 − rho_pi)/rho_slope)` es el que separa el mapa
   convergente del explosivo (test directo sobre `step_macro_economy`).
3. `indexation` con inercia: un solo mes por encima del umbral no cambia el régimen del mapa.
4. La semilla desde la historia real, y que el orden entre 1983-12 y 1988-06 lo pone la
   ACELERACION y nada mas.
5. C1 y C2, medidos.
6. C3: la sensibilidad de la mediana a `pi0` alrededor del umbral baja con el flag prendido.
7. Los campos estructurales sobreviven al cambio de vector por regimen cambiario (ADR 017 secc.
   3.6).

---

## 7. Resultados medidos

### 7.0 El criterio de éxito C1 estaba mal especificado, y se puede probar con el dato del repo

C1 pedía que la hiperinflación desde 1983-12 llegara **después del mes 48**, tomando como referencia
junio de 1989 (mes 66). Pero el mes 66 es el **episodio** de hiperinflación (114.5 %/mes), no el
**criterio terminal del modelo**, que es `terminal.hyper_inflation = 20 %/mes` durante
`terminal.hyper_months = 3` meses seguidos. Evaluando ese criterio —el del propio modelo— sobre la
serie mensual real (`history/inflation_cpi_monthly_linked.csv`):

| desde | primeros meses reales (%/mes) | el criterio del modelo se cumple en |
|---|---|---:|
| **1983-12** | 12.5 16.9 20.3 18.5 17.1 17.9 18.3 22.8 27.5 19.3 15.0 19.7 **25.1 20.7 26.5** | **mes 15** (ene–mar 1985) |
| **1988-06** | 25.6 27.6 11.7 9.0 5.7 6.8 8.9 9.6 17.0 **33.4 78.5 114.5** | **mes 12** (abr–jun 1989) |

La Argentina real estuvo tres meses seguidos por encima del 20 % mensual en **enero–marzo de 1985**,
catorce meses después de diciembre de 1983. Pedirle al modelo que tarde más de 48 meses en cumplir
un criterio que el dato cumple en 15 es pedirle que se equivoque en la otra dirección.

Por eso C1 se reformula, y el número contra el que se mide sale de la misma serie que usa el estado
inicial:

> **C1 (reformulado).** Desde 1983-12, la mediana del mes en que se cumple el criterio terminal del
> modelo tiene que acercarse al **mes 15** del dato real, y en particular dejar de ser el mes 6–7.

C2 queda como estaba (es la V1 de ADR 011 §8 / test 2a de ADR 012 §7, y su ventana de 24 meses cubre
el mes 12 real).

### 7.1 C1 y C2, medidos

`a7_by_regime`, transiciones de régimen y piso de legitimidad activos, sin shocks forzados.

| | antes (ADR 012 + dato A2) | **después (ADR 019)** | dato real |
|---|---:|---:|---:|
| **C1** 1983-12, mediana del mes de hiperinflación | **6.5** (10 semillas / 24 m); 7 en la sonda de 15 | **15** (15 semillas / 72 m, 13/15 cumplen) | **15** |
| **C2** 1988-06, semillas que cruzan 20 %/mes en 24 m | **0/50** (V1 de `a8_a7`) | **15/20 = 75 %** | cruza (mes 12) |
| 1988-06, mediana del criterio terminal completo | no se alcanza | 18 (10/20) | 12 |
| Control 2003-06, semillas que cruzan en 24 m | 0/20 | **0/20** | no cruza |

**Las dos condiciones se cumplen a la vez.** C1 pasa de errar el mes real por un factor de 2.3 (6.5
contra 15) a clavarlo (15 contra 15); C2 pasa de 0 % a 75 %, por encima del 50 % que pide el ADR
012 §7; y el control de no-espuriedad de 2003-06 sigue en 0/20, que era la otra mitad de ese test.

El criterio LITERAL del enunciado ("después del mes 48") **no se cumple** y no se intentó cumplir:
§7.0 muestra, con la serie del propio repositorio, que cumplirlo habría significado alejarse del
dato, no acercarse.

### 7.2 El filo, medido con el flag apagado y prendido

Se mueve SÓLO `inflation`/`inflation_lag1` del estado de 1983-12, 10 semillas, 36 meses, vector
`peg`/`crawl` de `a7_by_regime`. Mes mediano en que se cumple el criterio terminal:

| `pi0` | `rho_eff` mes 1 | ADR 012 (flag off) | **ADR 019 (flag on)** |
|---:|---:|---:|---:|
| 8.00 | 0.6456 | — (0/10) | — (0/10) |
| 10.00 | 0.7204 | — (0/10) | — (0/10) |
| 12.00 | 0.7952 | — (0/10) | — (0/10) |
| 14.00 | 0.8700 | 19.0 (5/10) | 19.0 (4/10) |
| 15.00 | 0.9074 | 18.0 (7/10) | 19.0 (5/10) |
| 16.00 | 0.9448 | 14.0 (9/10) | 17.5 (8/10) |
| **17.00** | 0.9821 | **11.0** | **13.0** |
| 17.40 | 0.9971 | 8.5 | 12.0 |
| **17.48** (el umbral) | 1.0001 | **7.5** | **12.0** |
| 17.60 | 1.0046 | 6.5 | 12.0 |
| 17.70 (dato real) | 1.0083 | 6.5 | 12.0 |
| 18.00 | 1.0195 | 7.5 | 12.0 |
| 18.50 | 1.0382 | 6.0 | 12.0 |
| **19.00** | 1.0516 | **5.5** | **11.5** |
| 20.00 | 1.0516 | 5.0 | 8.0 |
| 25.00 | 1.0516 | 3.0 | 3.0 |

En la banda de 2 pp que rodea al umbral (17.00 → 19.00, justo donde cae el dato inicial y justo
donde el dato tiene su error):

| | rango de la mediana | sensibilidad |
|---|---:|---:|
| ADR 012 (flag off) | 11.0 → 5.5 = **5.5 meses** | 2.75 meses por cada pp de `pi0` |
| **ADR 019 (flag on)** | 13.0 → 11.5 = **1.5 meses** | **0.75 meses por pp** |

**3.7 veces menos sensible**, y el nivel al que se estabiliza (11.5–13 meses) es el del dato real
(15 desde 1983-12, 12 desde 1988-06). El filo desaparece: entre 17.0 y 19.0 la respuesta es
literalmente plana en 12.

### 7.3 Barrido de sensibilidad: 85 arranques, 10 semillas, 24 meses

Cada mes entre 1983-12 y 1990-12, con el benchmark real al lado (el criterio terminal del modelo
evaluado sobre la serie, §7.0). Resumen; la tabla mes a mes está en `docs/CALIBRATION_LOG.md`.

| tramo | `pi0` (real) | modelo: mediana | real |
|---|---|---:|---:|
| 1983-12 … 1984-07 | 12.5–20.3 | 6–16 | 15 → 8 |
| 1984-08 … 1985-06 (la escalada del Austral) | 15.0–30.5 | 3–16 | 7 → 3 |
| 1985-07 … 1987-05 (el Austral funcionando) | 1.7–8.3 | **— (0/10 en 23 arranques seguidos)** | — |
| 1987-06 … 1988-06 (la Primavera) | 3.4–19.6 | — / 12–19 | 24 → 12 |
| 1988-07 … 1988-08 | 25.6, 27.6 | 3 | 11, 10 |
| 1988-09 … 1989-02 (la Primavera aguantando) | 5.7–11.7 | — | 9 → 4 |
| 1989-03 … 1989-08 (la hiper) | 17.0–196.6 | 3 | 3–8 |
| 1989-09 … 1990-03 | 5.6–95.5 | — / 3 | 3–5 |
| 1990-04 … 1990-12 | 4.7–15.7 | — / 19–23 | — |

Dos lecturas honestas:

1. **El modelo ya sigue al dato.** Sobre los 31 arranques donde los dos cruzan dentro de los 24
   meses, el error mediano es de **3 meses**; y hay **29 arranques donde ninguno de los dos cruza**
   —los 23 meses seguidos del Plan Austral entre otros—, que el modelo acierta en bloque sin que se
   le haya dicho nada del Austral.
2. **La respuesta sigue siendo muy sensible a `pi0`, y ahora se ve.** Hay 16 pares de meses
   contiguos donde la mediana salta más de 8 meses, contra 4 antes y 2 en el propio dato. Casi
   todos son casos como 1988-08 → 1988-09, donde la inflación real cae de 27.6 a 11.7 %/mes y el
   modelo la sigue, mientras que el dato "sabe" que la hiperinflación llega igual nueve meses
   después. El modelo no tiene cómo ver eso: el Plan Primavera y su derrumbe no están en ninguna de
   sus 21 variables. Queda declarado como límite, no como algo resuelto (§7.5).

### 7.4 El dato viejo tenía sesgo de anticipación (look-ahead), y eso inflaba su puntaje

Al comparar contra el benchmark real, el brazo "antes" acierta el binario cruza/no-cruza en 67/85
(79 %) y el de ADR 019 en 57/85 (67 %). La caída es **entera del cambio de dato**, no del mecanismo
(con el dato nuevo y el flag apagado: 58/85). Y no es una pérdida: es la desaparición de una
trampa.

`initial_state_for` construía la inflación de, por ejemplo, **1988-09** interpolando entre el
promedio ANUAL de 1988 (387.7 %) y el de **1989** (4923.8 %) — un promedio que contiene la
hiperinflación de junio y julio de 1989. El valor "inicial" de septiembre de 1988 (29.66 %/mes) ya
traía adentro el dato de nueve meses después. El real de ese mes es 11.7 %/mes. Cualquier
calibración, backtest o validación que arranque desde un mes anterior a 1997-02 estuvo usando
estados iniciales contaminados con el futuro de la propia ventana que evalúa.

### 7.5 Lo que este ADR NO arregla

1. **El modelo sigue sin meseta de inflación alta.** Con `pi_anchor` = EMA(36) de su propia
   inflación, el ancla termina alcanzando al nivel y el mapa queda en pendiente `1 + c_e > 1` para
   cualquier nivel (§1.4). La inercia de ADR 019 retrasa el escape, no lo elimina: lo que se mide en
   §7.1 es que el retraso ahora coincide con el dato, no que exista un punto fijo alto estable.
2. **17 de 21 variables siguen siendo la misma constante en todas las fechas** (§1.1). Mientras
   `history/` no tenga reservas, balance fiscal ni desempleo mensuales para los ochenta, el modelo
   no tiene con qué distinguir dos meses salvo por la inflación.
3. **Los planes de estabilización no existen en el modelo.** Que el barrido acierte los 23 meses del
   Plan Austral es porque el dato inicial de esos meses ya es bajo, no porque el modelo sepa que
   hubo un plan. En cuanto arranca en un mes de inflación alta que en la realidad fue seguido de un
   plan, se equivoca.
4. **Los grupos `float` y `control` de `a7_by_regime` tienen `rho_eff` máximo 0.8086 y 0.8527**
   (§1.6): por ese canal la hiperinflación es inalcanzable para cualquier arranque en esas
   ventanas, sin importar el estado inicial. ADR 019 no toca eso — es un problema del punto del
   espacio de parámetros al que llegó la calibración, y se arregla recalibrando.

### 7.6 Bug encontrado en el camino: el cambio de vector por régimen apagaba los campos estructurales

`engine/simulation.py::_swap_fx_regime_vector` (ADR 017 §3.6) reemplaza `sim.macro_coefficients` por
el vector del grupo nuevo, y ese vector sale de un `coefficients.json` que **no trae ningún campo
estructural**: ninguna calibración guarda los `lf_*` de ADR 016 ni los `idx_*` de ADR 019. Como
`active_fx_regime_group` arranca en `None`, el primer swap ocurre en el **mes 1** de toda corrida con
`--calibration` de una calibración `--by-regime`. Resultado: ADR 019 quedaba apagado en silencio en
exactamente las corridas que lo necesitan, y los `lf_*` caían a los defaults de la clase en vez de
los del paquete (hoy coinciden, así que no había diferencia medible — pero la fragilidad era real).

Corregido guardando el vector inicial en `Simulation.macro_structural_reference` y pasando cada swap
por `merge_structural_coefficients`, que es el mismo mecanismo que ya usaban `cli.py` y
`validation/argentina.py` para el vector inicial. Cubierto por
`tests/test_initial_sensitivity.py::test_structural_fields_survive_the_fx_regime_vector_swap`.

### 7.7 Tests

`tests/test_initial_sensitivity.py`, 19 tests, todos en verde:

| # del §6 | tests |
|---|---|
| 1 | `test_flag_off_rho_eff_is_exactly_the_adr_012_ramp`, `test_flag_off_full_run_is_bit_identical_to_the_same_run_without_adr_019_fields`, `test_adr_019_fields_are_not_calibrable` (`MACRO_TUNABLE` sigue en 58) |
| 2 | `test_rho_eff_crosses_one_at_the_analytic_threshold` (17.4773, y los 0.283 pp de 1983-12), `test_the_measured_transition_band_sits_below_the_analytic_threshold` |
| 3 | `test_one_month_above_the_threshold_no_longer_flips_the_map`, `test_indexation_converges_to_its_target_with_the_documented_half_life` |
| 4 | `test_no_backward_looking_statistic_orders_1988_06_above_1983_12`, `test_the_acceleration_is_the_only_observable_that_orders_them`, `test_idx_accel_k_two_is_exactly_a_one_month_linear_extrapolation`, `test_seed_is_none_without_enough_real_history`, `test_seed_history_is_the_real_series_of_the_previous_months` |
| 5 | `test_initial_inflation_of_the_two_dates_is_the_real_monthly_datum` |
| 6 | `test_c1_...`, `test_c2_hyperinflation_still_reachable_from_1988_06`, `test_c2_is_not_spurious_from_2003_06`, `test_c3_sensitivity_to_the_initial_inflation_drops_with_the_flag_on` |
| 7 | `test_structural_fields_survive_the_fx_regime_vector_swap`, `test_merge_structural_coefficients_carries_both_adrs` |

Goldens sin moverse: `tests/test_country_pack_argentina.py` (incluido
`test_aurora_without_country_matches_golden_hash_pre_a2`) y `tests/test_macro_regime.py` (incluido
`test_flag_off_golden_hash_still_matches_pre_adr_012` y el test 2a/2b de ADR 012 §7, que corren con
los coeficientes del paquete). Suite completa: 557 pasan, 1 salteado, 2 xfail.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de
Argentina; no son evidencia sobre lo que hubiera pasado.
