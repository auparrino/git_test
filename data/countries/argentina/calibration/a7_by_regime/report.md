# Calibracion Argentina -- run `a7_by_regime`

Pais: `argentina`. Train: `1992-01:2023-12`. Holdout: `1983-12:1991-12`. El holdout (`1983-12:1991-12`) es ANTERIOR en el calendario al train (`1992-01:2023-12`) -- a proposito (A5, ADR 012 secc. 6): el holdout es la hiperinflacion/convertibilidad temprana (1983-1991), nunca vista por esta estructura de precios/regimen cambiario; el orden cronologico no importa para el protocolo de honestidad, solo que el holdout se corra UNA sola vez, DESPUES de fijar los coeficientes con train.
Presupuesto: 400 evaluaciones POR GRUPO (3 grupos; usadas en total: 1242). Stride: 3 meses. lambda_reg: 0.01. Semilla: 42. Perdida optimizada por CMA-ES: `heavy` (el reporte muestra ambas metricas, RMSE y cola pesada, para cualquier corrida -- A5, ADR 012 secc. 6).
Tiempo de pared del optimizador: 1336.2s.
Hash de los datos de entrada (`history/*.csv` + `politics/*.csv`): `f90b17f882f6a7b47f4286e67fda8217fcf5e71a00471a580ab83361a0ce5055`.

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
| inflacion (mensual, %) | 1 | 0.365 | 0.348 | 0.428 | 0.327 |
| inflacion (mensual, %) | 3 | 0.635 | 0.529 | 0.861 | 0.747 |
| inflacion (mensual, %) | 6 | 0.786 | 0.652 | 1.728 | 0.716 |
| inflacion (mensual, %) | 12 | 1.013 | 0.687 | 4.902 | 0.821 |
| crecimiento del PBI (anualizado, %) | 1 | 0.573 | 0.262 | 0.593 | 0.591 |
| crecimiento del PBI (anualizado, %) | 3 | 0.841 | 0.769 | 0.867 | 0.863 |
| crecimiento del PBI (anualizado, %) | 6 | 0.946 | 1.046 | 0.986 | 0.923 |
| crecimiento del PBI (anualizado, %) | 12 | 1.004 | 1.404 | 1.214 | 0.965 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.307 | 0.349 | 0.338 | 0.318 |
| desempleo (%) | 6 | 0.425 | 0.492 | 0.507 | 0.441 |
| desempleo (%) | 12 | 0.595 | 0.636 | 1.126 | 0.818 |
| tipo de cambio oficial (cambio log) | 1 | 0.663 | 0.772 | 0.659 | 0.661 |
| tipo de cambio oficial (cambio log) | 3 | 1.520 | 1.680 | 2.151 | 1.520 |
| tipo de cambio oficial (cambio log) | 6 | 2.387 | 2.870 | 3.825 | 2.111 |
| tipo de cambio oficial (cambio log) | 12 | 4.468 | 5.017 | 8.257 | 3.421 |
| reservas (USD M) | 1 | 0.224 | 0.177 | 0.191 | 0.176 |
| reservas (USD M) | 3 | 0.380 | 0.333 | 0.491 | 0.321 |
| reservas (USD M) | 6 | 0.620 | 0.488 | 0.902 | 0.466 |
| reservas (USD M) | 12 | 1.120 | 0.705 | 1.521 | 0.660 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.171 | 0.143 | 0.194 | 0.143 |
| inflacion (mensual, %) | 3 | 0.360 | 0.260 | 0.557 | 0.514 |
| inflacion (mensual, %) | 6 | 0.485 | 0.329 | 1.574 | 0.472 |
| inflacion (mensual, %) | 12 | 0.713 | 0.385 | 8.210 | 0.563 |
| crecimiento del PBI (anualizado, %) | 1 | 0.331 | 0.088 | 0.356 | 0.354 |
| crecimiento del PBI (anualizado, %) | 3 | 0.602 | 0.429 | 0.647 | 0.647 |
| crecimiento del PBI (anualizado, %) | 6 | 0.754 | 0.764 | 0.811 | 0.734 |
| crecimiento del PBI (anualizado, %) | 12 | 0.837 | 1.258 | 1.099 | 0.792 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.150 | 0.177 | 0.172 | 0.161 |
| desempleo (%) | 6 | 0.240 | 0.279 | 0.311 | 0.256 |
| desempleo (%) | 12 | 0.344 | 0.416 | 0.885 | 0.537 |
| tipo de cambio oficial (cambio log) | 1 | 0.308 | 0.382 | 0.337 | 0.308 |
| tipo de cambio oficial (cambio log) | 3 | 1.307 | 1.353 | 2.480 | 1.343 |
| tipo de cambio oficial (cambio log) | 6 | 2.603 | 3.258 | 5.903 | 2.174 |
| tipo de cambio oficial (cambio log) | 12 | 6.361 | 8.273 | 19.282 | 4.952 |
| reservas (USD M) | 1 | 0.078 | 0.052 | 0.063 | 0.052 |
| reservas (USD M) | 3 | 0.180 | 0.143 | 0.299 | 0.138 |
| reservas (USD M) | 6 | 0.389 | 0.262 | 0.761 | 0.253 |
| reservas (USD M) | 12 | 0.946 | 0.494 | 1.617 | 0.460 |



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
| inflacion (mensual, %) | 1 | 1.546 | 0.465 | 1.205 | 2.938 |
| inflacion (mensual, %) | 3 | 5.491 | 1.139 | 6.487 | 5.182 |
| inflacion (mensual, %) | 6 | 6.637 | 2.178 | 8.073 | 6.563 |
| inflacion (mensual, %) | 12 | 8.459 | 4.005 | 9.752 | 6.707 |
| crecimiento del PBI (anualizado, %) | 1 | 1.057 | 0.558 | 1.060 | 1.059 |
| crecimiento del PBI (anualizado, %) | 3 | 0.959 | 0.558 | 0.969 | 0.945 |
| crecimiento del PBI (anualizado, %) | 6 | 2.404 | 0.759 | 2.624 | 0.904 |
| crecimiento del PBI (anualizado, %) | 12 | 2.737 | 1.050 | 3.000 | 0.888 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | 1.359 | 2.506 | 2.267 | 1.188 |
| tipo de cambio oficial (cambio log) | 3 | 4.930 | 7.338 | 6.009 | 3.575 |
| tipo de cambio oficial (cambio log) | 6 | 7.649 | 14.399 | 7.935 | 8.637 |
| tipo de cambio oficial (cambio log) | 12 | 17.311 | 27.523 | 16.825 | 20.630 |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 1.715 | 0.237 | 1.183 | 4.600 |
| inflacion (mensual, %) | 3 | 11.300 | 1.003 | 14.768 | 10.879 |
| inflacion (mensual, %) | 6 | 15.515 | 2.721 | 21.808 | 15.237 |
| inflacion (mensual, %) | 12 | 22.797 | 7.101 | 28.755 | 15.449 |
| crecimiento del PBI (anualizado, %) | 1 | 1.023 | 0.273 | 1.031 | 1.029 |
| crecimiento del PBI (anualizado, %) | 3 | 0.856 | 0.273 | 0.883 | 0.847 |
| crecimiento del PBI (anualizado, %) | 6 | 3.424 | 0.503 | 4.018 | 0.787 |
| crecimiento del PBI (anualizado, %) | 12 | 4.357 | 0.962 | 5.196 | 0.770 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | 1.210 | 3.510 | 2.937 | 1.057 |
| tipo de cambio oficial (cambio log) | 3 | 9.047 | 17.585 | 12.413 | 5.670 |
| tipo de cambio oficial (cambio log) | 6 | 18.389 | 48.287 | 20.425 | 21.553 |
| tipo de cambio oficial (cambio log) | 12 | 60.576 | 127.661 | 57.717 | 78.857 |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.621 | 0.759 | 0.000 |
| 12 | 0.828 | 1.000 | 0.000 |

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
| inflacion (mensual, %) | 1 | 0.288 | 0.138 | 0.165 | 0.133 |
| inflacion (mensual, %) | 3 | 0.825 | 0.595 | 0.704 | 0.685 |
| inflacion (mensual, %) | 6 | 0.928 | 0.756 | 0.960 | 0.744 |
| inflacion (mensual, %) | 12 | 0.940 | 0.725 | 2.111 | 0.669 |
| crecimiento del PBI (anualizado, %) | 1 | 0.753 | 0.000 | 0.743 | 0.742 |
| crecimiento del PBI (anualizado, %) | 3 | 0.805 | 0.598 | 0.823 | 0.823 |
| crecimiento del PBI (anualizado, %) | 6 | 0.923 | 0.846 | 0.917 | 0.859 |
| crecimiento del PBI (anualizado, %) | 12 | 1.091 | 1.197 | 1.007 | 0.924 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | 0.097 | sin dato | 4.314 | 4.421 |
| tipo de cambio oficial (cambio log) | 1 | 0.234 | 0.127 | 0.260 | 0.142 |
| tipo de cambio oficial (cambio log) | 3 | 1.805 | 2.151 | 2.377 | 1.808 |
| tipo de cambio oficial (cambio log) | 6 | 2.917 | 3.810 | 3.718 | 2.763 |
| tipo de cambio oficial (cambio log) | 12 | 4.769 | 6.062 | 6.748 | 4.029 |
| reservas (USD M) | 1 | 0.374 | 0.160 | 0.248 | 0.167 |
| reservas (USD M) | 3 | 0.319 | 0.267 | 0.414 | 0.231 |
| reservas (USD M) | 6 | 0.454 | 0.387 | 0.751 | 0.332 |
| reservas (USD M) | 12 | 0.924 | 0.640 | 1.042 | 0.595 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.144 | 0.041 | 0.059 | 0.038 |
| inflacion (mensual, %) | 3 | 0.533 | 0.263 | 0.412 | 0.349 |
| inflacion (mensual, %) | 6 | 0.630 | 0.338 | 0.658 | 0.510 |
| inflacion (mensual, %) | 12 | 0.649 | 0.352 | 1.766 | 0.361 |
| crecimiento del PBI (anualizado, %) | 1 | 0.567 | 0.000 | 0.555 | 0.556 |
| crecimiento del PBI (anualizado, %) | 3 | 0.622 | 0.272 | 0.646 | 0.662 |
| crecimiento del PBI (anualizado, %) | 6 | 0.761 | 0.545 | 0.751 | 0.715 |
| crecimiento del PBI (anualizado, %) | 12 | 0.983 | 1.090 | 0.868 | 0.801 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | 0.030 | sin dato | 8.961 | 9.294 |
| tipo de cambio oficial (cambio log) | 1 | 0.056 | 0.019 | 0.072 | 0.036 |
| tipo de cambio oficial (cambio log) | 3 | 1.373 | 1.537 | 2.224 | 1.568 |
| tipo de cambio oficial (cambio log) | 6 | 2.951 | 4.046 | 4.251 | 3.057 |
| tipo de cambio oficial (cambio log) | 12 | 6.861 | 9.104 | 11.817 | 5.843 |
| reservas (USD M) | 1 | 0.207 | 0.053 | 0.106 | 0.056 |
| reservas (USD M) | 3 | 0.147 | 0.110 | 0.248 | 0.092 |
| reservas (USD M) | 6 | 0.240 | 0.192 | 0.626 | 0.154 |
| reservas (USD M) | 12 | 0.660 | 0.425 | 0.984 | 0.379 |



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
| inflacion (mensual, %) | 1 | 1.546 | 0.465 | 1.205 | 2.938 |
| inflacion (mensual, %) | 3 | 5.480 | 1.139 | 6.487 | 5.182 |
| inflacion (mensual, %) | 6 | 6.597 | 2.178 | 8.073 | 6.553 |
| inflacion (mensual, %) | 12 | 8.436 | 4.005 | 9.752 | 6.696 |
| crecimiento del PBI (anualizado, %) | 1 | 1.057 | 0.558 | 1.060 | 1.059 |
| crecimiento del PBI (anualizado, %) | 3 | 0.958 | 0.558 | 0.969 | 0.950 |
| crecimiento del PBI (anualizado, %) | 6 | 2.345 | 0.759 | 2.624 | 0.912 |
| crecimiento del PBI (anualizado, %) | 12 | 2.737 | 1.050 | 3.000 | 0.895 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | 1.359 | 2.506 | 2.267 | 1.188 |
| tipo de cambio oficial (cambio log) | 3 | 4.860 | 7.338 | 6.009 | 3.643 |
| tipo de cambio oficial (cambio log) | 6 | 7.364 | 14.399 | 7.935 | 8.770 |
| tipo de cambio oficial (cambio log) | 12 | 17.088 | 27.523 | 16.825 | 20.840 |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 1.715 | 0.237 | 1.183 | 4.600 |
| inflacion (mensual, %) | 3 | 11.251 | 1.003 | 14.768 | 10.880 |
| inflacion (mensual, %) | 6 | 15.349 | 2.721 | 21.808 | 15.201 |
| inflacion (mensual, %) | 12 | 22.708 | 7.101 | 28.755 | 15.413 |
| crecimiento del PBI (anualizado, %) | 1 | 1.023 | 0.273 | 1.031 | 1.029 |
| crecimiento del PBI (anualizado, %) | 3 | 0.856 | 0.273 | 0.883 | 0.855 |
| crecimiento del PBI (anualizado, %) | 6 | 3.280 | 0.503 | 4.018 | 0.798 |
| crecimiento del PBI (anualizado, %) | 12 | 4.357 | 0.962 | 5.196 | 0.783 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | 1.210 | 3.510 | 2.937 | 1.057 |
| tipo de cambio oficial (cambio log) | 3 | 8.800 | 17.585 | 12.413 | 6.026 |
| tipo de cambio oficial (cambio log) | 6 | 17.346 | 48.287 | 20.425 | 22.286 |
| tipo de cambio oficial (cambio log) | 12 | 59.680 | 127.661 | 57.717 | 79.961 |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.586 | 0.759 | 0.000 |
| 12 | 0.828 | 1.000 | 0.000 |

### Grupo `peg` -- Drift de parametros (Aurora -> calibrado)

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| approval_reversion | coefficients | 45 | 135 | +0.750 |
| d_g | coefficients | 0.6 | 1.799 | +0.750 |
| c_g | macro | 0.5 | 1.5 | +0.750 |
| md_0 | macro | 0.12 | 0.3598 | +0.749 |
| t_p | coefficients | 0.5 | 1.454 | +0.716 |
| ic_pi | coefficients | 0.5 | 1.425 | +0.694 |
| recovery_unemployment_max | macro | 10 | 27.69 | +0.664 |
| b_band | coefficients | 1 | 2.624 | +0.609 |
| rm | macro | 3 | 6 | +0.600 |
| s_g | coefficients | 2 | 5.017 | +0.566 |
| pr_adj | coefficients | 0.3 | 0.7432 | +0.554 |
| s_pi | coefficients | 3 | 7.366 | +0.546 |
| rho_pi | macro | 0.85 | 0.5815 | -0.537 |
| r_gap_max | coefficients | 30 | 72.5 | +0.531 |
| t_u | coefficients | 0.8 | 1.92 | +0.525 |

### Grupo `float` -- Train

n = 54 meses de arranque (0 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.425 | 0.452 | 0.539 | 0.348 |
| inflacion (mensual, %) | 3 | 0.615 | 0.566 | 1.018 | 0.617 |
| inflacion (mensual, %) | 6 | 0.777 | 0.626 | 2.040 | 0.474 |
| inflacion (mensual, %) | 12 | 1.054 | 0.678 | 4.430 | 0.472 |
| crecimiento del PBI (anualizado, %) | 1 | 0.568 | 0.206 | 0.611 | 0.606 |
| crecimiento del PBI (anualizado, %) | 3 | 0.723 | 0.428 | 0.789 | 0.775 |
| crecimiento del PBI (anualizado, %) | 6 | 0.810 | 0.706 | 0.904 | 0.805 |
| crecimiento del PBI (anualizado, %) | 12 | 0.976 | 1.174 | 1.239 | 0.964 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.308 | 0.355 | 0.351 | 0.322 |
| desempleo (%) | 6 | 0.392 | 0.489 | 0.506 | 0.409 |
| desempleo (%) | 12 | 0.623 | 0.608 | 0.965 | 0.648 |
| tipo de cambio oficial (cambio log) | 1 | 0.925 | 1.082 | 0.914 | 0.921 |
| tipo de cambio oficial (cambio log) | 3 | 1.472 | 1.310 | 2.383 | 1.314 |
| tipo de cambio oficial (cambio log) | 6 | 2.332 | 2.038 | 4.609 | 1.692 |
| tipo de cambio oficial (cambio log) | 12 | 5.133 | 3.671 | 10.550 | 2.619 |
| reservas (USD M) | 1 | 0.188 | 0.215 | 0.192 | 0.211 |
| reservas (USD M) | 3 | 0.462 | 0.400 | 0.543 | 0.390 |
| reservas (USD M) | 6 | 0.751 | 0.589 | 0.841 | 0.567 |
| reservas (USD M) | 12 | 1.229 | 0.789 | 1.183 | 0.690 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.195 | 0.210 | 0.264 | 0.159 |
| inflacion (mensual, %) | 3 | 0.340 | 0.301 | 0.687 | 0.410 |
| inflacion (mensual, %) | 6 | 0.438 | 0.307 | 1.958 | 0.277 |
| inflacion (mensual, %) | 12 | 0.726 | 0.366 | 7.448 | 0.275 |
| crecimiento del PBI (anualizado, %) | 1 | 0.299 | 0.077 | 0.352 | 0.344 |
| crecimiento del PBI (anualizado, %) | 3 | 0.548 | 0.225 | 0.635 | 0.619 |
| crecimiento del PBI (anualizado, %) | 6 | 0.670 | 0.466 | 0.786 | 0.657 |
| crecimiento del PBI (anualizado, %) | 12 | 0.832 | 1.017 | 1.162 | 0.823 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.154 | 0.184 | 0.182 | 0.165 |
| desempleo (%) | 6 | 0.218 | 0.279 | 0.316 | 0.233 |
| desempleo (%) | 12 | 0.340 | 0.387 | 0.717 | 0.380 |
| tipo de cambio oficial (cambio log) | 1 | 0.551 | 0.687 | 0.599 | 0.552 |
| tipo de cambio oficial (cambio log) | 3 | 1.384 | 1.045 | 3.362 | 1.125 |
| tipo de cambio oficial (cambio log) | 6 | 2.652 | 2.119 | 8.858 | 1.626 |
| tipo de cambio oficial (cambio log) | 12 | 7.813 | 5.244 | 30.866 | 3.361 |
| reservas (USD M) | 1 | 0.055 | 0.068 | 0.059 | 0.065 |
| reservas (USD M) | 3 | 0.239 | 0.185 | 0.339 | 0.180 |
| reservas (USD M) | 6 | 0.532 | 0.342 | 0.686 | 0.342 |
| reservas (USD M) | 12 | 1.084 | 0.586 | 1.091 | 0.490 |



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
| recovery_unemployment_max | macro | 10 | 29.84 | +0.744 |
| p_i | coefficients | 0.5 | 1.458 | +0.718 |
| b_band | coefficients | 1 | 2.753 | +0.657 |
| pr_adj | coefficients | 0.3 | 0.7905 | +0.613 |
| e_pi | coefficients | 0.8 | 2.083 | +0.602 |
| crime_base | coefficients | 50 | 129.2 | +0.594 |
| x0_m0_pct_gdp | macro | 0.18 | 0.4477 | +0.558 |
| b_conf | coefficients | 1 | 2.481 | +0.555 |
| ic_pi | coefficients | 0.5 | 1.221 | +0.541 |
| t_p | coefficients | 0.5 | 1.199 | +0.524 |
| e_rev_sentiment_k | macro | 10 | 23.93 | +0.522 |
| control_de_admin | macro | 3 | 7.04 | +0.505 |
| banking_crisis_k_k_multiplier | macro | 0 | -0.09844 | -0.492 |
| ic_target_base | macro | 45 | 103.9 | +0.491 |
| amort_rate | macro | 0.004 | 0.008959 | +0.465 |

### Grupo `control` -- Train

n = 29 meses de arranque (0 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.314 | 0.272 | 0.387 | 0.418 |
| inflacion (mensual, %) | 3 | 0.390 | 0.352 | 0.673 | 0.990 |
| inflacion (mensual, %) | 6 | 0.620 | 0.576 | 1.733 | 1.003 |
| inflacion (mensual, %) | 12 | 1.009 | 0.661 | 7.291 | 1.326 |
| crecimiento del PBI (anualizado, %) | 1 | 0.290 | 0.436 | 0.308 | 0.315 |
| crecimiento del PBI (anualizado, %) | 3 | 1.054 | 1.266 | 1.036 | 1.041 |
| crecimiento del PBI (anualizado, %) | 6 | 1.176 | 1.615 | 1.184 | 1.164 |
| crecimiento del PBI (anualizado, %) | 12 | 0.959 | 1.911 | 1.360 | 1.008 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.303 | 0.338 | 0.312 | 0.311 |
| desempleo (%) | 6 | 0.483 | 0.499 | 0.509 | 0.499 |
| desempleo (%) | 12 | 0.546 | 0.687 | 1.139 | 0.686 |
| tipo de cambio oficial (cambio log) | 1 | 0.273 | 0.379 | 0.279 | 0.338 |
| tipo de cambio oficial (cambio log) | 3 | 1.251 | 1.716 | 1.254 | 1.541 |
| tipo de cambio oficial (cambio log) | 6 | 1.778 | 3.020 | 1.784 | 2.006 |
| tipo de cambio oficial (cambio log) | 12 | 2.258 | 5.879 | 3.473 | 3.986 |
| reservas (USD M) | 1 | 0.086 | 0.090 | 0.129 | 0.093 |
| reservas (USD M) | 3 | 0.228 | 0.225 | 0.443 | 0.228 |
| reservas (USD M) | 6 | 0.441 | 0.329 | 1.104 | 0.330 |
| reservas (USD M) | 12 | 1.062 | 0.575 | 2.254 | 0.657 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.155 | 0.127 | 0.209 | 0.226 |
| inflacion (mensual, %) | 3 | 0.211 | 0.183 | 0.469 | 0.884 |
| inflacion (mensual, %) | 6 | 0.418 | 0.361 | 1.838 | 0.794 |
| inflacion (mensual, %) | 12 | 0.758 | 0.454 | 16.519 | 1.314 |
| crecimiento del PBI (anualizado, %) | 1 | 0.138 | 0.203 | 0.151 | 0.157 |
| crecimiento del PBI (anualizado, %) | 3 | 0.682 | 0.978 | 0.671 | 0.681 |
| crecimiento del PBI (anualizado, %) | 6 | 0.903 | 1.554 | 0.924 | 0.899 |
| crecimiento del PBI (anualizado, %) | 12 | 0.688 | 1.885 | 1.228 | 0.724 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.143 | 0.165 | 0.153 | 0.153 |
| desempleo (%) | 6 | 0.283 | 0.278 | 0.300 | 0.300 |
| desempleo (%) | 12 | 0.365 | 0.473 | 0.920 | 0.526 |
| tipo de cambio oficial (cambio log) | 1 | 0.126 | 0.203 | 0.131 | 0.144 |
| tipo de cambio oficial (cambio log) | 3 | 1.093 | 1.728 | 1.109 | 1.509 |
| tipo de cambio oficial (cambio log) | 6 | 2.138 | 4.538 | 2.165 | 2.250 |
| tipo de cambio oficial (cambio log) | 12 | 3.124 | 13.025 | 5.692 | 6.963 |
| reservas (USD M) | 1 | 0.020 | 0.022 | 0.038 | 0.023 |
| reservas (USD M) | 3 | 0.097 | 0.092 | 0.265 | 0.098 |
| reservas (USD M) | 6 | 0.247 | 0.167 | 1.011 | 0.169 |
| reservas (USD M) | 12 | 0.935 | 0.377 | 3.143 | 0.474 |



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
| dd_gap | macro | 0.15 | 0.4484 | +0.746 |
| conf_ref | coefficients | 45 | 130.3 | +0.711 |
| peg_default_risk_ceiling | macro | 0.3 | 0.9996 | +0.700 |
| x0_m0_pct_gdp | macro | 0.18 | 0.4997 | +0.666 |
| f_u | coefficients | 0.1 | 0.2683 | +0.631 |
| k_flight_peg | macro | 3000 | 7662 | +0.583 |
| ic_target_bonus | macro | 10 | 25.23 | +0.571 |
| st_c | coefficients | 0.3 | 0.6926 | +0.491 |
| rho_pi | macro | 0.85 | 0.6068 | -0.486 |
| ic_target_base | macro | 45 | 99.94 | +0.458 |
| rm | macro | 3 | 5.263 | +0.453 |
| approval_ref | coefficients | 50 | 109.6 | +0.447 |
| md_0 | macro | 0.12 | 0.2623 | +0.445 |
| e_u | coefficients | 2 | 4.182 | +0.409 |
| w_g | coefficients | 0.3 | 0.6225 | +0.403 |

## Drift de parametros (Aurora -> calibrado)

Top 15 por magnitud de drift, en unidades del RANGO permitido de cada parametro (`(calibrado - aurora) / (hi - lo)`; +-0.5 es la mitad del rango explorable). Tabla completa en `coefficients.json`.

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| recovery_unemployment_max | macro | 10 | 29.84 | +0.744 |
| p_i | coefficients | 0.5 | 1.458 | +0.718 |
| b_band | coefficients | 1 | 2.753 | +0.657 |
| pr_adj | coefficients | 0.3 | 0.7905 | +0.613 |
| e_pi | coefficients | 0.8 | 2.083 | +0.602 |
| crime_base | coefficients | 50 | 129.2 | +0.594 |
| x0_m0_pct_gdp | macro | 0.18 | 0.4477 | +0.558 |
| b_conf | coefficients | 1 | 2.481 | +0.555 |
| ic_pi | coefficients | 0.5 | 1.221 | +0.541 |
| t_p | coefficients | 0.5 | 1.199 | +0.524 |
| e_rev_sentiment_k | macro | 10 | 23.93 | +0.522 |
| control_de_admin | macro | 3 | 7.04 | +0.505 |
| banking_crisis_k_k_multiplier | macro | 0 | -0.09844 | -0.492 |
| ic_target_base | macro | 45 | 103.9 | +0.491 |
| amort_rate | macro | 0.004 | 0.008959 | +0.465 |

## Limitaciones

> Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.

Proxies usados en el estado inicial de cada mes: ver `src/republica/calibration/initial_states.py` (docstring del modulo, reglas de interpolacion) y `initial_state_for(date)` para la procedencia `source`/`proxy`/`assumed` de cada variable en cada mes de arranque.
