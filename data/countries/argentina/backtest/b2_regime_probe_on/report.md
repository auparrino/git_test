# Backtest secuencial de predictibilidad — Argentina (ADR 014)

Rango de orígenes: 1930-01 a 1983-01. Horizontes: [12, 24, 48] meses. Semillas por ventana y brazo: 15. Calibración: `a5b_macro`. 162 ventanas, 969 filas ventana-objetivo-brazo en `windows.csv`. Tiempo de pared: 2.0 min.

Shocks forzados: SOLO exógenos (`windows.py::EXOGENOUS_ONLY`: sequía, pandemia, crisis internacional, boom de commodities, guerra). Nunca `hyperinflation_regime`, `sovereign_default`, `banking_crisis` ni golpe -- eso es lo que se predice (ADR 014 secc. 1).

## Tablas estratificadas (tasa de acierto, IC 95 % bootstrap, N)

### Dirección de la inflación
Acierto global: 45.5 % (N=231).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 162 | 45.7 % | [38.3 %, 53.7 %] |
| calibrated | 69 | 44.9 % | [33.3 %, 56.5 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 77 | 33.8 % | [23.4 %, 45.5 %] |
| 24 | 77 | 48.1 % | [35.1 %, 59.7 %] |
| 48 | 77 | 54.5 % | [42.9 %, 64.9 %] |

**por `frequency`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| annual_interpolated | 93 | 37.6 % | [26.9 %, 47.3 %] |
| monthly | 138 | 50.7 % | [42.8 %, 58.0 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 225 | 44.9 % | [37.3 %, 51.6 %] |
| True | 6 | 66.7 % | [33.3 %, 100.0 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 27 | 18.5 % | [3.7 %, 33.3 %] |
| democracy | 33 | 63.6 % | [48.5 %, 78.8 %] |
| dictatorship | 87 | 55.2 % | [43.7 %, 64.4 %] |
| restricted_democracy | 84 | 36.9 % | [26.2 %, 46.4 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 87 | 40.2 % | [29.9 %, 50.6 %] |
| 3-10 | 60 | 53.3 % | [40.0 %, 65.0 %] |
| <1 | 72 | 47.2 % | [34.7 %, 56.9 %] |
| >10 | 12 | 33.3 % | [8.3 %, 58.3 %] |

### Magnitud de la inflación
Acierto global: 33.8 % (N=231).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 162 | 28.4 % | [21.0 %, 35.2 %] |
| calibrated | 69 | 46.4 % | [36.2 %, 58.0 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 77 | 33.8 % | [24.7 %, 45.5 %] |
| 24 | 77 | 32.5 % | [22.1 %, 42.9 %] |
| 48 | 77 | 35.1 % | [23.4 %, 45.5 %] |

**por `frequency`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| annual_interpolated | 93 | 44.1 % | [33.3 %, 53.8 %] |
| monthly | 138 | 26.8 % | [19.6 %, 34.8 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 225 | 33.8 % | [27.1 %, 40.0 %] |
| True | 6 | 33.3 % | [0.0 %, 83.3 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 27 | 22.2 % | [7.4 %, 40.7 %] |
| democracy | 33 | 48.5 % | [30.3 %, 66.7 %] |
| dictatorship | 87 | 29.9 % | [20.7 %, 39.1 %] |
| restricted_democracy | 84 | 35.7 % | [26.2 %, 45.2 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 87 | 31.0 % | [21.8 %, 41.4 %] |
| 3-10 | 60 | 38.3 % | [26.7 %, 50.0 %] |
| <1 | 72 | 36.1 % | [25.0 %, 47.2 %] |
| >10 | 12 | 16.7 % | [0.0 %, 41.7 %] |

### Régimen
Acierto global: 72.5 % (N=138).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 69 | 72.5 % | [62.3 %, 84.1 %] |
| calibrated | 69 | 72.5 % | [62.3 %, 84.1 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 46 | 87.0 % | [76.1 %, 95.7 %] |
| 24 | 46 | 73.9 % | [60.9 %, 87.0 %] |
| 48 | 46 | 56.5 % | [43.5 %, 71.7 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 132 | 71.2 % | [63.6 %, 79.5 %] |
| True | 6 | 100.0 % | [100.0 %, 100.0 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 18 | 100.0 % | [100.0 %, 100.0 %] |
| democracy | 24 | 50.0 % | [29.2 %, 70.8 %] |
| dictatorship | 72 | 63.9 % | [51.4 %, 75.0 %] |
| restricted_democracy | 24 | 100.0 % | [100.0 %, 100.0 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 54 | 85.2 % | [75.9 %, 94.4 %] |
| 3-10 | 54 | 51.9 % | [38.9 %, 64.8 %] |
| <1 | 18 | 77.8 % | [55.6 %, 94.4 %] |
| >10 | 12 | 100.0 % | [100.0 %, 100.0 %] |

### Crisis
Acierto global: 76.6 % (N=231).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 162 | 81.5 % | [74.7 %, 87.7 %] |
| calibrated | 69 | 65.2 % | [53.6 %, 75.4 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 77 | 66.2 % | [55.8 %, 77.9 %] |
| 24 | 77 | 71.4 % | [61.0 %, 81.8 %] |
| 48 | 77 | 92.2 % | [85.7 %, 97.4 %] |

**por `frequency`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| annual_interpolated | 93 | 100.0 % | [100.0 %, 100.0 %] |
| monthly | 138 | 60.9 % | [53.6 %, 68.8 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 225 | 78.7 % | [72.4 %, 83.6 %] |
| True | 6 | 0.0 % | [0.0 %, 0.0 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 27 | 92.6 % | [81.5 %, 100.0 %] |
| democracy | 33 | 57.6 % | [39.4 %, 72.7 %] |
| dictatorship | 87 | 65.5 % | [55.2 %, 74.7 %] |
| restricted_democracy | 84 | 90.5 % | [83.3 %, 96.4 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 87 | 81.6 % | [73.6 %, 89.7 %] |
| 3-10 | 60 | 55.0 % | [41.7 %, 66.7 %] |
| <1 | 72 | 93.1 % | [86.1 %, 98.6 %] |
| >10 | 12 | 50.0 % | [25.0 %, 83.3 %] |

### Golpe (1916–1983)
Acierto global: 59.4 % (N=138).

**por `arm`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| aurora | 69 | 60.9 % | [49.3 %, 72.5 %] |
| calibrated | 69 | 58.0 % | [47.8 %, 69.6 %] |

**por `h`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 12 | 46 | 78.3 % | [63.0 %, 89.1 %] |
| 24 | 46 | 60.9 % | [45.7 %, 73.9 %] |
| 48 | 46 | 39.1 % | [26.1 %, 54.3 %] |

**por `has_era`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| False | 132 | 57.6 % | [49.2 %, 65.2 %] |
| True | 6 | 100.0 % | [100.0 %, 100.0 %] |

**por `regime_mode_initial`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| coup | 18 | 0.0 % | [0.0 %, 0.0 %] |
| democracy | 24 | 66.7 % | [45.8 %, 83.3 %] |
| dictatorship | 72 | 72.2 % | [62.5 %, 81.9 %] |
| restricted_democracy | 24 | 58.3 % | [37.5 %, 79.2 %] |

**por `inflation_bucket`**

| valor | N | acierto | IC 95% |
|---|---:|---:|---|
| 1-3 | 54 | 40.7 % | [27.8 %, 53.7 %] |
| 3-10 | 54 | 88.9 % | [79.6 %, 96.3 %] |
| <1 | 18 | 33.3 % | [11.1 %, 55.6 %] |
| >10 | 12 | 50.0 % | [16.7 %, 75.0 %] |

## Modelo de predictibilidad (regresión logística + árbol de profundidad ≤ 3)

### Dirección de la inflación
N=231, tasa base de acierto=45.5 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con años desde el último default ≤ 89.50 y tendencia de inflación previa 12m (%) > -0.08 y dispersión entre semillas (IQR) ≤ 0.15: se acierta el 0 % (82 ventanas-objetivo).
- con años desde el último default ≤ 89.50 y tendencia de inflación previa 12m (%) ≤ -0.08 y horizonte (meses) > 18.00: se acierta el 1 % (56 ventanas-objetivo).
- con años desde el último default ≤ 89.50 y tendencia de inflación previa 12m (%) > -0.08 y dispersión entre semillas (IQR) > 0.15: se acierta el 1 % (53 ventanas-objetivo).

Validación cruzada por década (árbol, 6 grupos): accuracy = [0.5, 0.49, 0.59, 0.77, 0.83], media 63.7 %.

**Importancia por permutación** (top, árbol):
- inflation_trend_12m: 0.105
- h: 0.055
- years_since_last_default: 0.047
- n_source: 0.000
- n_proxy: 0.000

### Magnitud de la inflación
N=231, tasa base de acierto=33.8 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con dispersión entre semillas (IQR) ≤ 0.28 y poliarquia V-Dem ≤ 0.34 y meses hasta la próxima elección ≤ 71.00: se acierta el 0 % (96 ventanas-objetivo).
- con dispersión entre semillas (IQR) > 0.28 y años desde el último default ≤ 81.50: se acierta el 0 % (38 ventanas-objetivo).
- con dispersión entre semillas (IQR) ≤ 0.28 y poliarquia V-Dem > 0.34 y tendencia de inflación previa 12m (%) > -0.40: se acierta el 2 % (30 ventanas-objetivo).

Validación cruzada por década (árbol, 6 grupos): accuracy = [0.73, 0.81, 0.43, 0.53, 0.7], media 64.0 %.

**Importancia por permutación** (top, árbol):
- vdem_polyarchy: 0.083
- iqr_seeds: 0.059
- h: 0.000
- n_source: 0.000
- n_proxy: 0.000

### Régimen
N=138, tasa base de acierto=72.5 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con magnitud acumulada de shocks ≤ 0.40 y tendencia de inflación previa 12m (%) ≤ 6.40 y dispersión entre semillas (IQR) ≤ 0.17: se acierta el 1 % (93 ventanas-objetivo).
- con magnitud acumulada de shocks ≤ 0.40 y tendencia de inflación previa 12m (%) ≤ 6.40 y dispersión entre semillas (IQR) > 0.17: se acierta el 2 % (25 ventanas-objetivo).
- con magnitud acumulada de shocks > 0.40: se acierta el 0 % (14 ventanas-objetivo).

Validación cruzada por década (árbol, 3 grupos): accuracy = [0.63, 0.78, 0.5], media 63.7 %.

**Importancia por permutación** (top, árbol):
- shocks_magnitude_sum: 0.145
- inflation_trend_12m: 0.072
- h: 0.000
- n_source: 0.000
- n_proxy: 0.000

### Elección
No se ajustó modelo: solo 0 filas (< 20).

### Crisis
N=231, tasa base de acierto=76.6 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con nº de variables con dato real (source) ≤ 2.50: se acierta el 1 % (93 ventanas-objetivo).
- con nº de variables con dato real (source) > 2.50 y horizonte (meses) ≤ 36.00 y años desde el último golpe ≤ 3.21: se acierta el 1 % (52 ventanas-objetivo).
- con nº de variables con dato real (source) > 2.50 y horizonte (meses) ≤ 36.00 y años desde el último golpe > 3.21: se acierta el 2 % (40 ventanas-objetivo).

Validación cruzada por década (árbol, 6 grupos): accuracy = [0.52, 0.56, 0.63, 1.0, 1.0], media 74.2 %.

**Importancia por permutación** (top, árbol):
- h: 0.085
- n_source: 0.085
- years_since_last_coup: 0.072
- n_proxy: 0.000
- n_assumed: 0.000

### Golpe (1916–1983)
N=138, tasa base de acierto=59.4 %.

**Las 3 reglas del árbol en lenguaje llano** (hojas con más ventanas):
- con poliarquia V-Dem > 0.09 y meses hasta la próxima elección > 16.00 y horizonte (meses) > 18.00: se acierta el 0 % (52 ventanas-objetivo).
- con poliarquia V-Dem ≤ 0.09: se acierta el 3 % (36 ventanas-objetivo).
- con poliarquia V-Dem > 0.09 y meses hasta la próxima elección > 16.00 y horizonte (meses) ≤ 18.00: se acierta el 2 % (26 ventanas-objetivo).

Validación cruzada por década (árbol, 3 grupos): accuracy = [0.73, 0.48, 0.0], media 40.5 %.

**Importancia por permutación** (top, árbol):
- vdem_polyarchy: 0.191
- h: 0.149
- months_to_next_election: 0.062
- n_source: 0.000
- n_proxy: 0.000

## Dispersión entre semillas como señal

Spearman(IQR entre semillas, error de magnitud de inflación) = 0.465 (N=231). el modelo *sabe cuándo no sabe*: a mayor dispersión entre semillas, mayor error.

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
| 1960s | Dirección de la inflación | 27 | 37.0 % | 30 | 46.7 % | -9.6 pp |
| 1960s | Magnitud de la inflación | 27 | 44.4 % | 30 | 10.0 % | +34.4 pp |
| 1960s | Régimen | 27 | 96.3 % | 27 | 96.3 % | +0.0 pp |
| 1960s | Crisis | 27 | 77.8 % | 30 | 63.3 % | +14.4 pp |
| 1960s | Golpe (1916–1983) | 27 | 40.7 % | 27 | 48.1 % | -7.4 pp |
| 1970s | Dirección de la inflación | 30 | 36.7 % | 30 | 56.7 % | -20.0 pp |
| 1970s | Magnitud de la inflación | 30 | 33.3 % | 30 | 10.0 % | +23.3 pp |
| 1970s | Régimen | 30 | 60.0 % | 30 | 60.0 % | +0.0 pp |
| 1970s | Crisis | 30 | 53.3 % | 30 | 50.0 % | +3.3 pp |
| 1970s | Golpe (1916–1983) | 30 | 56.7 % | 30 | 56.7 % | +0.0 pp |
| 1980s | Dirección de la inflación | 12 | 83.3 % | 12 | 83.3 % | +0.0 pp |
| 1980s | Magnitud de la inflación | 12 | 83.3 % | 12 | 16.7 % | +66.7 pp |
| 1980s | Régimen | 12 | 50.0 % | 12 | 50.0 % | +0.0 pp |
| 1980s | Crisis | 12 | 66.7 % | 12 | 66.7 % | +0.0 pp |
| 1980s | Golpe (1916–1983) | 12 | 100.0 % | 12 | 100.0 % | +0.0 pp |

## Qué hace funcionar una predicción

Leer primero las tablas estratificadas y las reglas del árbol de cada objetivo, arriba: en general el acierto es mayor cuando (a) el estado inicial trae más variables `source` (menos `assumed`), (b) la ventana es mensual (no `annual_interpolated`), y (c) la ventana cae dentro del período de entrenamiento de la calibración (`in_sample`). La dispersión entre semillas (sección anterior) dice si, además, el propio modelo puede señalar sus ventanas de menor confianza.

## Qué no se puede concluir

Este backtest NO mide qué habría pasado realmente en cada período (PLAN_ARGENTINA.md secc. 4): las ventanas 1916-1960 corren en modo anual (ADR 011 secc. 6, exploratorio) con el `initial_state` de Aurora, no un estado real -- para esas ventanas los objetivos `regime`/`coup` ni siquiera se puntúan (serían tautológicos, ver `scoring.py`). El objetivo `election` solo se puntúa donde hay un resultado real curado (`calibration/objective.py::REAL_ELECTION_OUTCOMES`, 1989-2019): no hay evidencia sobre elecciones anteriores. Los IC 95 % son bootstrap sobre las FILAS (ventana×objetivo×brazo, no independientes entre horizontes que comparten `t0`): no corrigen por esa correlación. El árbol y la regresión describen ESTA muestra (con CV por década, cuando hay al menos 3 décadas); no son una ley general de cuándo el modelo funciona.

> Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.
