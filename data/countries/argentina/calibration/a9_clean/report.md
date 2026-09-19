# Calibracion Argentina -- run `a9_clean`

Pais: `argentina`. Train: `1992-01:2023-12`. Holdout: `1983-12:1991-12`. El holdout (`1983-12:1991-12`) es ANTERIOR en el calendario al train (`1992-01:2023-12`) -- a proposito (A5, ADR 012 secc. 6): el holdout es la hiperinflacion/convertibilidad temprana (1983-1991), nunca vista por esta estructura de precios/regimen cambiario; el orden cronologico no importa para el protocolo de honestidad, solo que el holdout se corra UNA sola vez, DESPUES de fijar los coeficientes con train.
Presupuesto: 400 evaluaciones POR GRUPO (3 grupos; usadas en total: 1242). Stride: 3 meses. lambda_reg: 0.01. Semilla: 42. Perdida optimizada por CMA-ES: `heavy` (el reporte muestra ambas metricas, RMSE y cola pesada, para cualquier corrida -- A5, ADR 012 secc. 6).
Tiempo de pared del optimizador: 1400.3s.
Hash de los datos de entrada (`history/*.csv` + `politics/*.csv`): `fe8cbe9e4ef75bf7b31ff0df84dcd4549d84443d68399d6f8b705cbcb6b4d0b6`.

Vector de calibracion CON el grupo `macro` (A5, ADR 012 secc. 6): simula con `step_macro_economy` (regimen cambiario efectivo + balance de pagos), `fx_regime=pack.fx_regime_auto` (regimen real de cada fecha, `fx_regimes.csv`) y el bloque bimonetario viejo DESACTIVADO (`engine/simulation.py::run` lo apaga en cuanto hay `macro_coefficients`, ver Notas de implementacion del ADR 012).

Calibracion POR REGIMEN CAMBIARIO (`--by-regime`, ADR 017 secc. 3): un CMA-ES por grupo (`peg`, `float`, `control`), con 400 evaluaciones de presupuesto CADA UNO, particionando los meses de arranque por el `fx_regime` real de `fx_regimes.csv` en `t0` (`crawl` va con `peg`: `world/economy.py::step_macro_economy` los trata en la MISMA rama). Vector `default` = el del grupo con mas meses de arranque de train: `float`.

Pesos por variable del objetivo: todos en 1.0 (default, `--weights` sin usar).

## Shocks forzados en el periodo

Cada mes de arranque simula con `--historical-shocks --historical-exogenous`: los shocks del calendario real (`politics/shocks_calendar.csv`, ADR 011 secc. 4) estan FORZADOS -- si el modelo reproduce una crisis en un mes donde hubo un shock forzado, no es merito de la dinamica interna calibrada, es el shock. Ver `data/countries/argentina/politics/shocks_calendar.csv` para la lista completa; no se repite aca fila por fila para no duplicar la fuente de verdad.

## Train (AGREGADO: cada mes con el vector de su grupo)

n = 124 meses de arranque (20 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.363 | 0.348 | 0.433 | 0.328 |
| inflacion (mensual, %) | 3 | 0.618 | 0.529 | 0.862 | 0.745 |
| inflacion (mensual, %) | 6 | 0.774 | 0.652 | 1.674 | 0.716 |
| inflacion (mensual, %) | 12 | 0.927 | 0.687 | 4.487 | 0.821 |
| crecimiento del PBI (anualizado, %) | 1 | 0.571 | 0.262 | 0.591 | 0.588 |
| crecimiento del PBI (anualizado, %) | 3 | 0.835 | 0.769 | 0.866 | 0.861 |
| crecimiento del PBI (anualizado, %) | 6 | 0.926 | 1.046 | 0.986 | 0.922 |
| crecimiento del PBI (anualizado, %) | 12 | 0.982 | 1.404 | 1.206 | 0.965 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.300 | 0.349 | 0.339 | 0.318 |
| desempleo (%) | 6 | 0.425 | 0.492 | 0.509 | 0.441 |
| desempleo (%) | 12 | 0.598 | 0.636 | 1.140 | 0.818 |
| tipo de cambio oficial (cambio log) | 1 | 0.667 | 0.772 | 0.648 | 0.663 |
| tipo de cambio oficial (cambio log) | 3 | 1.681 | 1.680 | 2.065 | 1.524 |
| tipo de cambio oficial (cambio log) | 6 | 2.696 | 2.870 | 3.830 | 2.116 |
| tipo de cambio oficial (cambio log) | 12 | 4.682 | 5.017 | 8.679 | 3.426 |
| reservas (USD M) | 1 | 0.180 | 0.177 | 0.191 | 0.176 |
| reservas (USD M) | 3 | 0.367 | 0.333 | 0.414 | 0.321 |
| reservas (USD M) | 6 | 0.570 | 0.488 | 0.769 | 0.466 |
| reservas (USD M) | 12 | 1.004 | 0.705 | 1.797 | 0.660 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.170 | 0.143 | 0.198 | 0.144 |
| inflacion (mensual, %) | 3 | 0.348 | 0.260 | 0.564 | 0.512 |
| inflacion (mensual, %) | 6 | 0.476 | 0.329 | 1.524 | 0.472 |
| inflacion (mensual, %) | 12 | 0.625 | 0.385 | 7.330 | 0.563 |
| crecimiento del PBI (anualizado, %) | 1 | 0.326 | 0.088 | 0.354 | 0.352 |
| crecimiento del PBI (anualizado, %) | 3 | 0.579 | 0.429 | 0.644 | 0.644 |
| crecimiento del PBI (anualizado, %) | 6 | 0.709 | 0.764 | 0.810 | 0.733 |
| crecimiento del PBI (anualizado, %) | 12 | 0.775 | 1.258 | 1.088 | 0.792 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.141 | 0.177 | 0.173 | 0.161 |
| desempleo (%) | 6 | 0.228 | 0.279 | 0.313 | 0.256 |
| desempleo (%) | 12 | 0.344 | 0.416 | 0.907 | 0.537 |
| tipo de cambio oficial (cambio log) | 1 | 0.309 | 0.382 | 0.322 | 0.311 |
| tipo de cambio oficial (cambio log) | 3 | 1.462 | 1.353 | 2.246 | 1.350 |
| tipo de cambio oficial (cambio log) | 6 | 2.926 | 3.258 | 5.856 | 2.191 |
| tipo de cambio oficial (cambio log) | 12 | 6.647 | 8.273 | 20.650 | 4.974 |
| reservas (USD M) | 1 | 0.057 | 0.052 | 0.061 | 0.052 |
| reservas (USD M) | 3 | 0.177 | 0.143 | 0.214 | 0.138 |
| reservas (USD M) | 6 | 0.362 | 0.262 | 0.567 | 0.253 |
| reservas (USD M) | 12 | 0.841 | 0.494 | 2.068 | 0.460 |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.000 | 0.000 | 0.000 |
| 12 | 0.000 | 0.048 | 0.000 |

## Holdout (AGREGADO: cada mes con el vector de su grupo)

n = 29 meses de arranque (29 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 4.858 | 0.465 | 4.813 | 5.133 |
| inflacion (mensual, %) | 3 | 7.414 | 1.139 | 7.191 | 5.520 |
| inflacion (mensual, %) | 6 | 8.226 | 2.178 | 8.152 | 6.334 |
| inflacion (mensual, %) | 12 | 9.967 | 4.005 | 10.086 | 6.648 |
| crecimiento del PBI (anualizado, %) | 1 | 1.069 | 0.558 | 1.066 | 1.063 |
| crecimiento del PBI (anualizado, %) | 3 | 0.961 | 0.558 | 0.987 | 0.965 |
| crecimiento del PBI (anualizado, %) | 6 | 2.356 | 0.759 | 2.277 | 1.187 |
| crecimiento del PBI (anualizado, %) | 12 | 2.642 | 1.050 | 2.895 | 1.172 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | 3.335 | 2.506 | 4.238 | 2.871 |
| tipo de cambio oficial (cambio log) | 3 | 8.164 | 7.338 | 9.245 | 6.750 |
| tipo de cambio oficial (cambio log) | 6 | 10.185 | 14.399 | 10.188 | 10.966 |
| tipo de cambio oficial (cambio log) | 12 | 18.658 | 27.523 | 18.036 | 22.585 |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 8.643 | 0.237 | 8.501 | 9.672 |
| inflacion (mensual, %) | 3 | 16.532 | 1.003 | 15.817 | 11.405 |
| inflacion (mensual, %) | 6 | 19.903 | 2.721 | 20.207 | 14.211 |
| inflacion (mensual, %) | 12 | 27.371 | 7.101 | 28.618 | 15.261 |
| crecimiento del PBI (anualizado, %) | 1 | 1.042 | 0.273 | 1.038 | 1.034 |
| crecimiento del PBI (anualizado, %) | 3 | 0.873 | 0.273 | 0.910 | 0.877 |
| crecimiento del PBI (anualizado, %) | 6 | 3.318 | 0.503 | 3.094 | 1.115 |
| crecimiento del PBI (anualizado, %) | 12 | 4.097 | 0.962 | 4.839 | 1.077 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | 4.557 | 3.510 | 6.293 | 3.468 |
| tipo de cambio oficial (cambio log) | 3 | 18.665 | 17.585 | 21.066 | 14.334 |
| tipo de cambio oficial (cambio log) | 6 | 26.741 | 48.287 | 27.759 | 31.843 |
| tipo de cambio oficial (cambio log) | 12 | 65.513 | 127.661 | 68.085 | 91.119 |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.586 | 0.552 | 0.069 |
| 12 | 0.759 | 0.931 | 0.069 |

## Por grupo de regimen cambiario

Particion de los meses de arranque por el `fx_regime` REAL de `fx_regimes.csv` en `t0` (ADR 017 secc. 3). Cada grupo tiene su propio CMA-ES y su propio vector; las tablas agregadas de arriba puntuan cada mes con el vector de SU grupo.

| grupo | meses de arranque (train) | meses de arranque (holdout) |
|---|---:|---:|
| `peg` | 41 | 29 |
| `float` (default) | 54 | 0 |
| `control` | 29 | 0 |

### Grupo `peg` -- Train

n = 41 meses de arranque (20 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.286 | 0.138 | 0.189 | 0.143 |
| inflacion (mensual, %) | 3 | 0.784 | 0.595 | 0.737 | 0.680 |
| inflacion (mensual, %) | 6 | 0.923 | 0.756 | 1.033 | 0.744 |
| inflacion (mensual, %) | 12 | 0.976 | 0.725 | 2.381 | 0.669 |
| crecimiento del PBI (anualizado, %) | 1 | 0.727 | 0.000 | 0.737 | 0.735 |
| crecimiento del PBI (anualizado, %) | 3 | 0.937 | 0.598 | 0.815 | 0.816 |
| crecimiento del PBI (anualizado, %) | 6 | 1.029 | 0.846 | 0.918 | 0.856 |
| crecimiento del PBI (anualizado, %) | 12 | 1.186 | 1.197 | 0.938 | 0.924 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | 0.027 | sin dato | 4.339 | 4.421 |
| tipo de cambio oficial (cambio log) | 1 | 0.243 | 0.127 | 0.127 | 0.170 |
| tipo de cambio oficial (cambio log) | 3 | 2.302 | 2.151 | 2.266 | 1.819 |
| tipo de cambio oficial (cambio log) | 6 | 3.890 | 3.810 | 4.134 | 2.777 |
| tipo de cambio oficial (cambio log) | 12 | 6.162 | 6.062 | 9.342 | 4.045 |
| reservas (USD M) | 1 | 0.206 | 0.160 | 0.254 | 0.168 |
| reservas (USD M) | 3 | 0.313 | 0.267 | 0.500 | 0.232 |
| reservas (USD M) | 6 | 0.491 | 0.387 | 1.081 | 0.333 |
| reservas (USD M) | 12 | 0.815 | 0.640 | 2.501 | 0.595 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.142 | 0.041 | 0.069 | 0.042 |
| inflacion (mensual, %) | 3 | 0.498 | 0.263 | 0.456 | 0.340 |
| inflacion (mensual, %) | 6 | 0.624 | 0.338 | 0.751 | 0.511 |
| inflacion (mensual, %) | 12 | 0.695 | 0.352 | 2.570 | 0.361 |
| crecimiento del PBI (anualizado, %) | 1 | 0.522 | 0.000 | 0.550 | 0.550 |
| crecimiento del PBI (anualizado, %) | 3 | 0.765 | 0.272 | 0.632 | 0.652 |
| crecimiento del PBI (anualizado, %) | 6 | 0.893 | 0.545 | 0.747 | 0.711 |
| crecimiento del PBI (anualizado, %) | 12 | 1.131 | 1.090 | 0.782 | 0.801 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | 0.005 | sin dato | 9.038 | 9.294 |
| tipo de cambio oficial (cambio log) | 1 | 0.056 | 0.019 | 0.019 | 0.046 |
| tipo de cambio oficial (cambio log) | 3 | 2.006 | 1.537 | 1.819 | 1.594 |
| tipo de cambio oficial (cambio log) | 6 | 4.439 | 4.046 | 5.290 | 3.118 |
| tipo de cambio oficial (cambio log) | 12 | 9.662 | 9.104 | 20.978 | 5.924 |
| reservas (USD M) | 1 | 0.076 | 0.053 | 0.107 | 0.056 |
| reservas (USD M) | 3 | 0.153 | 0.110 | 0.311 | 0.092 |
| reservas (USD M) | 6 | 0.307 | 0.192 | 1.039 | 0.155 |
| reservas (USD M) | 12 | 0.596 | 0.425 | 3.638 | 0.380 |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.000 | 0.000 | 0.000 |
| 12 | 0.000 | 0.000 | 0.000 |

### Grupo `peg` -- Holdout

n = 29 meses de arranque (29 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 4.858 | 0.465 | 4.813 | 5.133 |
| inflacion (mensual, %) | 3 | 7.414 | 1.139 | 7.172 | 5.548 |
| inflacion (mensual, %) | 6 | 8.226 | 2.178 | 8.259 | 6.311 |
| inflacion (mensual, %) | 12 | 9.967 | 4.005 | 10.114 | 6.637 |
| crecimiento del PBI (anualizado, %) | 1 | 1.069 | 0.558 | 1.066 | 1.063 |
| crecimiento del PBI (anualizado, %) | 3 | 0.961 | 0.558 | 0.991 | 0.961 |
| crecimiento del PBI (anualizado, %) | 6 | 2.356 | 0.759 | 2.216 | 1.184 |
| crecimiento del PBI (anualizado, %) | 12 | 2.642 | 1.050 | 2.895 | 1.151 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | 3.335 | 2.506 | 4.238 | 2.871 |
| tipo de cambio oficial (cambio log) | 3 | 8.164 | 7.338 | 9.272 | 6.763 |
| tipo de cambio oficial (cambio log) | 6 | 10.185 | 14.399 | 10.311 | 11.093 |
| tipo de cambio oficial (cambio log) | 12 | 18.658 | 27.523 | 17.730 | 22.733 |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 8.643 | 0.237 | 8.501 | 9.672 |
| inflacion (mensual, %) | 3 | 16.532 | 1.003 | 15.696 | 11.465 |
| inflacion (mensual, %) | 6 | 19.903 | 2.721 | 20.753 | 14.136 |
| inflacion (mensual, %) | 12 | 27.371 | 7.101 | 28.830 | 15.214 |
| crecimiento del PBI (anualizado, %) | 1 | 1.042 | 0.273 | 1.038 | 1.034 |
| crecimiento del PBI (anualizado, %) | 3 | 0.873 | 0.273 | 0.917 | 0.872 |
| crecimiento del PBI (anualizado, %) | 6 | 3.318 | 0.503 | 2.951 | 1.107 |
| crecimiento del PBI (anualizado, %) | 12 | 4.097 | 0.962 | 4.839 | 1.044 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | 4.557 | 3.510 | 6.293 | 3.468 |
| tipo de cambio oficial (cambio log) | 3 | 18.665 | 17.585 | 21.332 | 14.282 |
| tipo de cambio oficial (cambio log) | 6 | 26.741 | 48.287 | 28.594 | 31.896 |
| tipo de cambio oficial (cambio log) | 12 | 65.513 | 127.661 | 66.391 | 91.500 |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.586 | 0.517 | 0.069 |
| 12 | 0.759 | 0.931 | 0.069 |

### Grupo `peg` -- Drift de parametros (Aurora -> calibrado)

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| dd_persistence | macro | 0.9 | 0.3105 | -0.854 |
| default_risk_c | macro | 0.3 | 0.8997 | +0.750 |
| d_g | coefficients | 0.6 | 1.782 | +0.739 |
| e_pi_low | coefficients | 0.3 | 0.8862 | +0.733 |
| ex_e | macro | 0.5 | 1.455 | +0.716 |
| t_pr | coefficients | 0.2 | 0.5582 | +0.672 |
| rho_pi | macro | 0.85 | 0.5145 | -0.671 |
| st_i | coefficients | 0.2 | 0.5539 | +0.663 |
| e_w | coefficients | 1.5 | 4.15 | +0.663 |
| dd_r | macro | 0.004 | 0.01084 | +0.642 |
| x0_m0_pct_gdp | macro | 0.18 | 0.4815 | +0.628 |
| st_adj | coefficients | 0.15 | 0.3861 | +0.590 |
| t_c | coefficients | 0.2 | 0.4847 | +0.534 |
| rho_slope | macro | 0.1 | 0.258 | +0.527 |
| md_0 | macro | 0.12 | 0.2854 | +0.517 |

### Grupo `float` -- Train

n = 54 meses de arranque (0 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.420 | 0.452 | 0.543 | 0.348 |
| inflacion (mensual, %) | 3 | 0.606 | 0.566 | 1.008 | 0.617 |
| inflacion (mensual, %) | 6 | 0.743 | 0.626 | 1.942 | 0.474 |
| inflacion (mensual, %) | 12 | 0.924 | 0.678 | 4.091 | 0.472 |
| crecimiento del PBI (anualizado, %) | 1 | 0.583 | 0.206 | 0.611 | 0.606 |
| crecimiento del PBI (anualizado, %) | 3 | 0.619 | 0.428 | 0.791 | 0.775 |
| crecimiento del PBI (anualizado, %) | 6 | 0.686 | 0.706 | 0.903 | 0.805 |
| crecimiento del PBI (anualizado, %) | 12 | 0.861 | 1.174 | 1.255 | 0.964 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.295 | 0.355 | 0.352 | 0.322 |
| desempleo (%) | 6 | 0.386 | 0.489 | 0.509 | 0.409 |
| desempleo (%) | 12 | 0.604 | 0.608 | 0.988 | 0.648 |
| tipo de cambio oficial (cambio log) | 1 | 0.932 | 1.082 | 0.914 | 0.921 |
| tipo de cambio oficial (cambio log) | 3 | 1.444 | 1.310 | 2.284 | 1.314 |
| tipo de cambio oficial (cambio log) | 6 | 2.227 | 2.038 | 4.409 | 1.692 |
| tipo de cambio oficial (cambio log) | 12 | 4.668 | 3.671 | 10.156 | 2.619 |
| reservas (USD M) | 1 | 0.198 | 0.215 | 0.198 | 0.211 |
| reservas (USD M) | 3 | 0.430 | 0.400 | 0.431 | 0.390 |
| reservas (USD M) | 6 | 0.640 | 0.589 | 0.632 | 0.567 |
| reservas (USD M) | 12 | 0.956 | 0.789 | 1.196 | 0.690 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.193 | 0.210 | 0.266 | 0.159 |
| inflacion (mensual, %) | 3 | 0.329 | 0.301 | 0.676 | 0.410 |
| inflacion (mensual, %) | 6 | 0.409 | 0.307 | 1.830 | 0.277 |
| inflacion (mensual, %) | 12 | 0.583 | 0.366 | 6.574 | 0.275 |
| crecimiento del PBI (anualizado, %) | 1 | 0.314 | 0.077 | 0.352 | 0.344 |
| crecimiento del PBI (anualizado, %) | 3 | 0.422 | 0.225 | 0.638 | 0.619 |
| crecimiento del PBI (anualizado, %) | 6 | 0.502 | 0.466 | 0.784 | 0.657 |
| crecimiento del PBI (anualizado, %) | 12 | 0.630 | 1.017 | 1.189 | 0.823 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.137 | 0.184 | 0.183 | 0.165 |
| desempleo (%) | 6 | 0.202 | 0.279 | 0.320 | 0.233 |
| desempleo (%) | 12 | 0.318 | 0.387 | 0.749 | 0.380 |
| tipo de cambio oficial (cambio log) | 1 | 0.558 | 0.687 | 0.599 | 0.552 |
| tipo de cambio oficial (cambio log) | 3 | 1.365 | 1.045 | 3.101 | 1.125 |
| tipo de cambio oficial (cambio log) | 6 | 2.504 | 2.119 | 8.163 | 1.626 |
| tipo de cambio oficial (cambio log) | 12 | 6.818 | 5.244 | 28.811 | 3.361 |
| reservas (USD M) | 1 | 0.061 | 0.068 | 0.061 | 0.065 |
| reservas (USD M) | 3 | 0.218 | 0.185 | 0.212 | 0.180 |
| reservas (USD M) | 6 | 0.419 | 0.342 | 0.407 | 0.342 |
| reservas (USD M) | 12 | 0.774 | 0.586 | 1.100 | 0.490 |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.000 | 0.000 | 0.000 |
| 12 | 0.000 | 0.056 | 0.000 |

### Grupo `float` -- Holdout

n = 0 meses de arranque en esta ventana: el grupo no tiene ningun mes de arranque aca (se imprime igual, con 'sin dato', para que la ausencia sea visible -- ADR 017 secc. 4).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar |
|---|---|---|---|---|
| inflacion (mensual, %) | 1 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 3 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 6 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 12 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 1 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 3 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 6 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 12 | sin dato | sin dato | sin dato |
| desempleo (%) | 1 | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 3 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 6 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 12 | sin dato | sin dato | sin dato |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato |

| regimen (acierto democracia/no) | - | sin dato | - | sin dato |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar |
|---|---|---|---|---|
| inflacion (mensual, %) | 1 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 3 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 6 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 12 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 1 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 3 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 6 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 12 | sin dato | sin dato | sin dato |
| desempleo (%) | 1 | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 3 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 6 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 12 | sin dato | sin dato | sin dato |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar |
|---|---|---|
| 1 | sin dato | sin dato |
| 3 | sin dato | sin dato |
| 6 | sin dato | sin dato |
| 12 | sin dato | sin dato |

### Grupo `float` -- Drift de parametros (Aurora -> calibrado)

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| pr_adj | coefficients | 0.3 | 0.8972 | +0.747 |
| t_u | coefficients | 0.8 | 2.385 | +0.743 |
| b_conf | coefficients | 1 | 2.909 | +0.716 |
| peg_default_risk_ceiling | macro | 0.3 | 0.9939 | +0.694 |
| dd_pi | macro | 0.01 | 0.02701 | +0.638 |
| cr_adj | coefficients | 0.1 | 0.268 | +0.630 |
| rho_pi | macro | 0.85 | 0.5352 | -0.630 |
| ic_target_bonus | macro | 10 | 24.88 | +0.558 |
| w_idx | coefficients | 1 | 2.4 | +0.525 |
| a_f | coefficients | 0.05 | 0.1186 | +0.515 |
| crime_base | coefficients | 50 | 92.07 | +0.505 |
| q_t | coefficients | 0.05 | 0.1154 | +0.490 |
| stability_base | coefficients | 60 | 98.43 | +0.480 |
| banking_crisis_k_k_multiplier | macro | 0 | -0.09547 | -0.477 |
| default_risk_threshold | macro | 0.5 | 0.9697 | +0.470 |

### Grupo `control` -- Train

n = 29 meses de arranque (0 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.320 | 0.272 | 0.387 | 0.418 |
| inflacion (mensual, %) | 3 | 0.402 | 0.352 | 0.672 | 0.990 |
| inflacion (mensual, %) | 6 | 0.646 | 0.576 | 1.690 | 1.003 |
| inflacion (mensual, %) | 12 | 0.877 | 0.661 | 6.474 | 1.326 |
| crecimiento del PBI (anualizado, %) | 1 | 0.291 | 0.436 | 0.308 | 0.315 |
| crecimiento del PBI (anualizado, %) | 3 | 1.045 | 1.266 | 1.035 | 1.041 |
| crecimiento del PBI (anualizado, %) | 6 | 1.167 | 1.615 | 1.185 | 1.164 |
| crecimiento del PBI (anualizado, %) | 12 | 0.954 | 1.911 | 1.359 | 1.008 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.308 | 0.338 | 0.312 | 0.311 |
| desempleo (%) | 6 | 0.491 | 0.499 | 0.509 | 0.499 |
| desempleo (%) | 12 | 0.597 | 0.687 | 1.140 | 0.686 |
| tipo de cambio oficial (cambio log) | 1 | 0.261 | 0.379 | 0.279 | 0.338 |
| tipo de cambio oficial (cambio log) | 3 | 1.247 | 1.716 | 1.254 | 1.541 |
| tipo de cambio oficial (cambio log) | 6 | 1.776 | 3.020 | 1.784 | 2.006 |
| tipo de cambio oficial (cambio log) | 12 | 2.241 | 5.879 | 3.276 | 3.986 |
| reservas (USD M) | 1 | 0.112 | 0.090 | 0.097 | 0.093 |
| reservas (USD M) | 3 | 0.263 | 0.225 | 0.287 | 0.228 |
| reservas (USD M) | 6 | 0.485 | 0.329 | 0.687 | 0.330 |
| reservas (USD M) | 12 | 1.217 | 0.575 | 1.994 | 0.657 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.160 | 0.127 | 0.209 | 0.226 |
| inflacion (mensual, %) | 3 | 0.224 | 0.183 | 0.469 | 0.884 |
| inflacion (mensual, %) | 6 | 0.442 | 0.361 | 1.781 | 0.794 |
| inflacion (mensual, %) | 12 | 0.629 | 0.454 | 13.826 | 1.314 |
| crecimiento del PBI (anualizado, %) | 1 | 0.138 | 0.203 | 0.151 | 0.157 |
| crecimiento del PBI (anualizado, %) | 3 | 0.675 | 0.978 | 0.670 | 0.681 |
| crecimiento del PBI (anualizado, %) | 6 | 0.898 | 1.554 | 0.925 | 0.899 |
| crecimiento del PBI (anualizado, %) | 12 | 0.664 | 1.885 | 1.225 | 0.724 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.148 | 0.165 | 0.153 | 0.153 |
| desempleo (%) | 6 | 0.279 | 0.278 | 0.301 | 0.300 |
| desempleo (%) | 12 | 0.408 | 0.473 | 0.923 | 0.526 |
| tipo de cambio oficial (cambio log) | 1 | 0.117 | 0.203 | 0.131 | 0.144 |
| tipo de cambio oficial (cambio log) | 3 | 1.061 | 1.728 | 1.109 | 1.509 |
| tipo de cambio oficial (cambio log) | 6 | 2.093 | 4.538 | 2.165 | 2.250 |
| tipo de cambio oficial (cambio log) | 12 | 3.107 | 13.025 | 5.102 | 6.963 |
| reservas (USD M) | 1 | 0.033 | 0.022 | 0.023 | 0.023 |
| reservas (USD M) | 3 | 0.119 | 0.092 | 0.136 | 0.098 |
| reservas (USD M) | 6 | 0.302 | 0.167 | 0.474 | 0.169 |
| reservas (USD M) | 12 | 1.178 | 0.377 | 2.515 | 0.474 |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.000 | 0.000 | 0.000 |
| 12 | 0.000 | 0.103 | 0.000 |

### Grupo `control` -- Holdout

n = 0 meses de arranque en esta ventana: el grupo no tiene ningun mes de arranque aca (se imprime igual, con 'sin dato', para que la ausencia sea visible -- ADR 017 secc. 4).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar |
|---|---|---|---|---|
| inflacion (mensual, %) | 1 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 3 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 6 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 12 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 1 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 3 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 6 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 12 | sin dato | sin dato | sin dato |
| desempleo (%) | 1 | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 3 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 6 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 12 | sin dato | sin dato | sin dato |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato |

| regimen (acierto democracia/no) | - | sin dato | - | sin dato |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar |
|---|---|---|---|---|
| inflacion (mensual, %) | 1 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 3 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 6 | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 12 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 1 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 3 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 6 | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 12 | sin dato | sin dato | sin dato |
| desempleo (%) | 1 | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 3 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 6 | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 12 | sin dato | sin dato | sin dato |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar |
|---|---|---|
| 1 | sin dato | sin dato |
| 3 | sin dato | sin dato |
| 6 | sin dato | sin dato |
| 12 | sin dato | sin dato |

### Grupo `control` -- Drift de parametros (Aurora -> calibrado)

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| x0_m0_pct_gdp | macro | 0.18 | 0.5146 | +0.697 |
| peg_capital_boost | macro | 3 | 8.563 | +0.695 |
| s_g | coefficients | 2 | 5.679 | +0.690 |
| rho_pi | macro | 0.85 | 0.5054 | -0.689 |
| dd_r | macro | 0.004 | 0.01093 | +0.650 |
| s_pi | coefficients | 3 | 8.088 | +0.636 |
| ic_rec | macro | 0.01 | 0.02487 | +0.558 |
| rm | macro | 3 | 5.712 | +0.542 |
| e_w | coefficients | 1.5 | 3.653 | +0.538 |
| banking_crisis_tension_bump | macro | 10 | 23.52 | +0.507 |
| banking_crisis_k_k_multiplier | macro | 0 | -0.09884 | -0.494 |
| approval_ref | coefficients | 50 | 90.95 | +0.491 |
| cr_adj | coefficients | 0.1 | 0.2297 | +0.486 |
| province_transfer_sensitivity | coefficients | 0.5 | 1.131 | +0.473 |
| pr_t | coefficients | 0.8 | 1.767 | +0.453 |

## Drift de parametros (Aurora -> calibrado)

Top 15 por magnitud de drift, en unidades del RANGO permitido de cada parametro (`(calibrado - aurora) / (hi - lo)`; +-0.5 es la mitad del rango explorable). Tabla completa en `coefficients.json`.

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| pr_adj | coefficients | 0.3 | 0.8972 | +0.747 |
| t_u | coefficients | 0.8 | 2.385 | +0.743 |
| b_conf | coefficients | 1 | 2.909 | +0.716 |
| peg_default_risk_ceiling | macro | 0.3 | 0.9939 | +0.694 |
| dd_pi | macro | 0.01 | 0.02701 | +0.638 |
| cr_adj | coefficients | 0.1 | 0.268 | +0.630 |
| rho_pi | macro | 0.85 | 0.5352 | -0.630 |
| ic_target_bonus | macro | 10 | 24.88 | +0.558 |
| w_idx | coefficients | 1 | 2.4 | +0.525 |
| a_f | coefficients | 0.05 | 0.1186 | +0.515 |
| crime_base | coefficients | 50 | 92.07 | +0.505 |
| q_t | coefficients | 0.05 | 0.1154 | +0.490 |
| stability_base | coefficients | 60 | 98.43 | +0.480 |
| banking_crisis_k_k_multiplier | macro | 0 | -0.09547 | -0.477 |
| default_risk_threshold | macro | 0.5 | 0.9697 | +0.470 |

## Limitaciones

> Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.

Proxies usados en el estado inicial de cada mes: ver `src/republica/calibration/initial_states.py` (docstring del modulo, reglas de interpolacion) y `initial_state_for(date)` para la procedencia `source`/`proxy`/`assumed` de cada variable en cada mes de arranque.
