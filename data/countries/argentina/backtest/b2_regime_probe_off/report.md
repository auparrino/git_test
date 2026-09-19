# Backtest secuencial de predictibilidad — Argentina (ADR 014)

Rango de orígenes: 1930-01 a 1983-01. Horizontes: [12, 24, 48] meses. Semillas por ventana y brazo: 15. Calibración: `a5b_macro`. 162 ventanas, 969 filas ventana-objetivo-brazo en `windows.csv`. Tiempo de pared: 1.9 min.

Shocks forzados: SOLO exógenos (`windows.py::EXOGENOUS_ONLY`: sequía, pandemia, crisis internacional, boom de commodities, guerra). Nunca `hyperinflation_regime`, `sovereign_default`, `banking_crisis` ni golpe -- eso es lo que se predice (ADR 014 secc. 1).

## Tablas estratificadas (tasa de acierto, IC 95 % bootstrap, N)

### Dirección de la inflación
Acierto global: 47.6 % (N=231).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 162 | 45.7 % | [37.7 %, 53.7 %] |
| calibrated | 69 | 52.2 % | [40.6 %, 65.2 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 77 | 37.7 % | [27.3 %, 49.4 %] |
| 24 | 77 | 48.1 % | [36.4 %, 59.7 %] |
| 48 | 77 | 57.1 % | [45.5 %, 68.8 %] |

**por `frequency`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| annual_interpolated | 93 | 37.6 % | [26.9 %, 47.3 %] |
| monthly | 138 | 54.3 % | [46.4 %, 63.0 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 225 | 47.1 % | [40.9 %, 54.2 %] |
| True | 6 | 66.7 % | [33.3 %, 100.0 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 27 | 22.2 % | [7.4 %, 37.0 %] |
| democracy | 33 | 63.6 % | [48.5 %, 78.8 %] |
| dictatorship | 87 | 57.5 % | [47.1 %, 66.7 %] |
| restricted_democracy | 84 | 39.3 % | [29.8 %, 48.8 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 87 | 46.0 % | [34.5 %, 56.3 %] |
| 3-10 | 60 | 53.3 % | [40.0 %, 65.0 %] |
| <1 | 72 | 47.2 % | [36.1 %, 58.3 %] |
| >10 | 12 | 33.3 % | [8.3 %, 58.3 %] |

### Magnitud de la inflación
Acierto global: 34.2 % (N=231).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 162 | 27.8 % | [19.8 %, 34.6 %] |
| calibrated | 69 | 49.3 % | [39.1 %, 62.3 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 77 | 33.8 % | [24.7 %, 45.5 %] |
| 24 | 77 | 31.2 % | [20.8 %, 42.9 %] |
| 48 | 77 | 37.7 % | [26.0 %, 48.1 %] |

**por `frequency`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| annual_interpolated | 93 | 44.1 % | [34.4 %, 54.8 %] |
| monthly | 138 | 27.5 % | [20.3 %, 34.8 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 225 | 34.2 % | [27.6 %, 40.0 %] |
| True | 6 | 33.3 % | [0.0 %, 83.3 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 27 | 22.2 % | [7.4 %, 40.7 %] |
| democracy | 33 | 48.5 % | [30.3 %, 66.7 %] |
| dictatorship | 87 | 31.0 % | [21.8 %, 40.2 %] |
| restricted_democracy | 84 | 35.7 % | [26.2 %, 46.4 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 87 | 33.3 % | [24.1 %, 43.7 %] |
| 3-10 | 60 | 36.7 % | [25.0 %, 48.3 %] |
| <1 | 72 | 36.1 % | [23.6 %, 48.6 %] |
| >10 | 12 | 16.7 % | [0.0 %, 41.7 %] |

### Régimen
Acierto global: 27.5 % (N=138).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 69 | 27.5 % | [17.4 %, 37.7 %] |
| calibrated | 69 | 27.5 % | [17.4 %, 37.7 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 46 | 21.7 % | [8.7 %, 34.8 %] |
| 24 | 46 | 26.1 % | [13.0 %, 39.1 %] |
| 48 | 46 | 34.8 % | [21.7 %, 47.8 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 132 | 24.2 % | [17.4 %, 31.8 %] |
| True | 6 | 100.0 % | [100.0 %, 100.0 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 18 | 0.0 % | [0.0 %, 0.0 %] |
| democracy | 24 | 50.0 % | [29.2 %, 70.8 %] |
| dictatorship | 72 | 36.1 % | [25.0 %, 48.6 %] |
| restricted_democracy | 24 | 0.0 % | [0.0 %, 0.0 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 54 | 11.1 % | [3.7 %, 20.4 %] |
| 3-10 | 54 | 40.7 % | [27.8 %, 55.6 %] |
| <1 | 18 | 22.2 % | [5.6 %, 44.4 %] |
| >10 | 12 | 50.0 % | [16.7 %, 75.0 %] |

### Crisis
Acierto global: 76.2 % (N=231).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 162 | 81.5 % | [74.7 %, 87.7 %] |
| calibrated | 69 | 63.8 % | [53.6 %, 75.4 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 77 | 66.2 % | [55.8 %, 76.6 %] |
| 24 | 77 | 70.1 % | [59.7 %, 80.5 %] |
| 48 | 77 | 92.2 % | [85.7 %, 97.4 %] |

**por `frequency`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| annual_interpolated | 93 | 100.0 % | [100.0 %, 100.0 %] |
| monthly | 138 | 60.1 % | [52.2 %, 68.1 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 225 | 78.2 % | [72.0 %, 83.1 %] |
| True | 6 | 0.0 % | [0.0 %, 0.0 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 27 | 92.6 % | [81.5 %, 100.0 %] |
| democracy | 33 | 57.6 % | [39.4 %, 72.7 %] |
| dictatorship | 87 | 65.5 % | [56.3 %, 74.7 %] |
| restricted_democracy | 84 | 89.3 % | [82.1 %, 95.2 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 87 | 79.3 % | [70.1 %, 87.4 %] |
| 3-10 | 60 | 56.7 % | [45.0 %, 68.3 %] |
| <1 | 72 | 93.1 % | [86.1 %, 98.6 %] |
| >10 | 12 | 50.0 % | [25.0 %, 83.3 %] |

### Golpe (1916–1983)
Acierto global: 58.7 % (N=138).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 69 | 58.0 % | [47.8 %, 69.6 %] |
| calibrated | 69 | 59.4 % | [49.3 %, 71.0 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 46 | 78.3 % | [63.0 %, 89.1 %] |
| 24 | 46 | 60.9 % | [45.7 %, 73.9 %] |
| 48 | 46 | 37.0 % | [23.9 %, 52.2 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 132 | 56.8 % | [49.2 %, 64.4 %] |
| True | 6 | 100.0 % | [100.0 %, 100.0 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 18 | 0.0 % | [0.0 %, 0.0 %] |
| democracy | 24 | 66.7 % | [45.8 %, 83.3 %] |
| dictatorship | 72 | 72.2 % | [62.5 %, 81.9 %] |
| restricted_democracy | 24 | 54.2 % | [33.3 %, 75.0 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 54 | 38.9 % | [25.9 %, 53.7 %] |
| 3-10 | 54 | 88.9 % | [79.6 %, 96.3 %] |
| <1 | 18 | 33.3 % | [11.1 %, 55.6 %] |
| >10 | 12 | 50.0 % | [16.7 %, 75.0 %] |

## Modelo de predictibilidad (regresión logística + árbol de profundidad ≤ 3)

### Dirección de la inflación
N=231, tasa base de acierto=47.6 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con años desde el último default ≤ 89.50 y tendencia de inflación previa 12m (%) > -0.08 y poliarquia V-Dem > 0.13: se acierta el 0 % (99 ventanas-objetivo).
- con años desde el último default ≤ 89.50 y tendencia de inflación previa 12m (%) ≤ -0.08 y horizonte (meses) > 18.00: se acierta el 1 % (56 ventanas-objetivo).
- con años desde el último default ≤ 89.50 y tendencia de inflación previa 12m (%) > -0.08 y poliarquia V-Dem ≤ 0.13: se acierta el 2 % (36 ventanas-objetivo).

Validación cruzada por década (árbol, 6 grupos): accuracy = [0.68, 0.6, 0.61, 0.57, 0.73], media 63.8 %.

**Importancia por permutación** (top, árbol):
- inflation_trend_12m: 0.116
- vdem_polyarchy: 0.087
- h: 0.044
- years_since_last_default: 0.016
- n_source: 0.000

### Magnitud de la inflación
N=231, tasa base de acierto=34.2 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con dispersión entre semillas (IQR) ≤ 0.19 y poliarquia V-Dem ≤ 0.34 y meses hasta la próxima elección ≤ 71.00: se acierta el 0 % (97 ventanas-objetivo).
- con dispersión entre semillas (IQR) > 0.19 y dispersión entre semillas (IQR) ≤ 2.66 y poliarquia V-Dem ≤ 0.50: se acierta el 0 % (46 ventanas-objetivo).
- con dispersión entre semillas (IQR) ≤ 0.19 y poliarquia V-Dem > 0.34 y horizonte (meses) > 18.00: se acierta el 3 % (26 ventanas-objetivo).

Validación cruzada por década (árbol, 6 grupos): accuracy = [0.67, 0.77, 0.43, 0.53, 0.37], media 55.3 %.

**Importancia por permutación** (top, árbol):
- vdem_polyarchy: 0.072
- iqr_seeds: 0.051
- h: 0.022
- n_source: 0.000
- n_proxy: 0.000

### Régimen
N=138, tasa base de acierto=27.5 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con magnitud acumulada de shocks ≤ 0.40 y meses hasta la próxima elección > 28.00 y inflación mensual inicial (%) > 0.72: se acierta el 0 % (76 ventanas-objetivo).
- con magnitud acumulada de shocks ≤ 0.40 y meses hasta la próxima elección ≤ 28.00 y aprobación proxy ≤ 35.98: se acierta el 3 % (24 ventanas-objetivo).
- con magnitud acumulada de shocks > 0.40: se acierta el 7 % (14 ventanas-objetivo).

Validación cruzada por década (árbol, 3 grupos): accuracy = [0.27, 0.59, 0.33], media 39.8 %.

**Importancia por permutación** (top, árbol):
- months_to_next_election: 0.213
- shocks_magnitude_sum: 0.110
- approval_proxy: 0.083
- h: 0.000
- n_source: 0.000

### Elección
No se ajustó modelo: solo 0 filas (< 20).

### Crisis
N=231, tasa base de acierto=76.2 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con nº de variables con dato real (source) ≤ 2.50: se acierta el 1 % (93 ventanas-objetivo).
- con nº de variables con dato real (source) > 2.50 y horizonte (meses) ≤ 36.00 y años desde el último golpe ≤ 3.21: se acierta el 1 % (52 ventanas-objetivo).
- con nº de variables con dato real (source) > 2.50 y horizonte (meses) ≤ 36.00 y años desde el último golpe > 3.21: se acierta el 2 % (40 ventanas-objetivo).

Validación cruzada por década (árbol, 6 grupos): accuracy = [0.68, 0.37, 0.85, 1.0, 1.0], media 78.1 %.

**Importancia por permutación** (top, árbol):
- n_source: 0.087
- h: 0.087
- years_since_last_coup: 0.078
- n_proxy: 0.000
- n_assumed: 0.000

### Golpe (1916–1983)
N=138, tasa base de acierto=58.7 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con poliarquia V-Dem > 0.09 y meses hasta la próxima elección > 16.00 y horizonte (meses) > 18.00: se acierta el 0 % (52 ventanas-objetivo).
- con poliarquia V-Dem ≤ 0.09: se acierta el 3 % (36 ventanas-objetivo).
- con poliarquia V-Dem > 0.09 y meses hasta la próxima elección > 16.00 y horizonte (meses) ≤ 18.00: se acierta el 2 % (26 ventanas-objetivo).

Validación cruzada por década (árbol, 3 grupos): accuracy = [0.67, 0.5, 0.08], media 41.7 %.

**Importancia por permutación** (top, árbol):
- vdem_polyarchy: 0.193
- h: 0.150
- months_to_next_election: 0.062
- n_source: 0.000
- n_proxy: 0.000

## Dispersión entre semillas como señal

Spearman(IQR entre semillas, error de magnitud de inflación) = 0.495 (N=231). el modelo *sabe cuándo no sabe*: a mayor dispersión entre semillas, mayor error.

## Calibrado vs. Aurora por década

| década | objetivo | N calibrado | acierto calibrado | N Aurora | acierto Aurora | diferencia |
|---:|---|---:|---:|---:|---:|---:|
| 1930s | Dirección de la inflación | 0 | sin dato | 30 | 30.0 % | sin dato |
| 1930s | Magnitud de la inflación | 0 | sin dato | 30 | 20.0 % | sin dato |
| 1930s | Crisis | 0 | sin dato | 30 | 100.0 % | sin dato |
| 1940s | Dirección de la inflación | 0 | sin dato | 30 | 50.0 % | sin dato |
| 1940s | Magnitud de la inflación | 0 | sin dato | 30 | 50.0 % | sin dato |
| 1940s | Crisis | 0 | sin dato | 30 | 100.0 % | sin dato |
| 1950s | Dirección de la inflación | 0 | sin dato | 30 | 30.0 % | sin dato |
| 1950s | Magnitud de la inflación | 0 | sin dato | 30 | 56.7 % | sin dato |
| 1950s | Crisis | 0 | sin dato | 30 | 100.0 % | sin dato |
| 1960s | Dirección de la inflación | 27 | 44.4 % | 30 | 46.7 % | -2.2 pp |
| 1960s | Magnitud de la inflación | 27 | 44.4 % | 30 | 10.0 % | +34.4 pp |
| 1960s | Régimen | 27 | 3.7 % | 27 | 3.7 % | +0.0 pp |
| 1960s | Crisis | 27 | 74.1 % | 30 | 63.3 % | +10.7 pp |
| 1960s | Golpe (1916–1983) | 27 | 44.4 % | 27 | 40.7 % | +3.7 pp |
| 1970s | Dirección de la inflación | 30 | 46.7 % | 30 | 56.7 % | -10.0 pp |
| 1970s | Magnitud de la inflación | 30 | 40.0 % | 30 | 6.7 % | +33.3 pp |
| 1970s | Régimen | 30 | 30.0 % | 30 | 30.0 % | +0.0 pp |
| 1970s | Crisis | 30 | 53.3 % | 30 | 50.0 % | +3.3 pp |
| 1970s | Golpe (1916–1983) | 30 | 56.7 % | 30 | 56.7 % | +0.0 pp |
| 1980s | Dirección de la inflación | 12 | 83.3 % | 12 | 83.3 % | +0.0 pp |
| 1980s | Magnitud de la inflación | 12 | 83.3 % | 12 | 16.7 % | +66.7 pp |
| 1980s | Régimen | 12 | 75.0 % | 12 | 75.0 % | +0.0 pp |
| 1980s | Crisis | 12 | 66.7 % | 12 | 66.7 % | +0.0 pp |
| 1980s | Golpe (1916–1983) | 12 | 100.0 % | 12 | 100.0 % | +0.0 pp |

## Qué hace funcionar una predicción

Leer primero las tablas estratificadas y las reglas del árbol de cada objetivo, arriba: en general el acierto es mayor cuando (a) el estado inicial trae más variables `source` (menos `assumed`), (b) la ventana es mensual (no `annual_interpolated`), y (c) la ventana cae dentro del período de entrenamiento de la calibración (`in_sample`). La dispersión entre semillas (sección anterior) dice si, además, el propio modelo puede señalar sus ventanas de menor confianza.

## Qué no se puede concluir

Este backtest NO mide qué habría pasado realmente en cada período (PLAN_ARGENTINA.md secc. 4): las ventanas 1916-1960 corren en modo anual (ADR 011 secc. 6, exploratorio) con el `initial_state` de Aurora, no un estado real -- para esas ventanas los objetivos `regime`/`coup` ni siquiera se puntúan (serían tautológicos, ver `scoring.py`). El objetivo `election` solo se puntúa donde hay un resultado real curado (`calibration/objective.py::REAL_ELECTION_OUTCOMES`, 1989-2019): no hay evidencia sobre elecciones anteriores. Los IC 95 % son bootstrap sobre las FILAS (ventana×objetivo×brazo, no independientes entre horizontes que comparten `t0`): no corrigen por esa correlación. El árbol y la regresión describen ESTA muestra (con CV por década, cuando hay al menos 3 décadas); no son una ley general de cuándo el modelo funciona.

> Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.
