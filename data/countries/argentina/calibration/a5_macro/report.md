# Calibracion Argentina -- run `a5_macro`

Pais: `argentina`. Train: `1992-01:2023-12`. Holdout: `1983-12:1991-12`. El holdout (`1983-12:1991-12`) es ANTERIOR en el calendario al train (`1992-01:2023-12`) -- a proposito (A5, ADR 012 secc. 6): el holdout es la hiperinflacion/convertibilidad temprana (1983-1991), nunca vista por esta estructura de precios/regimen cambiario; el orden cronologico no importa para el protocolo de honestidad, solo que el holdout se corra UNA sola vez, DESPUES de fijar los coeficientes con train.
Presupuesto: 400 evaluaciones (usadas: 418). Stride: 3 meses. lambda_reg: 0.01. Semilla: 42. Perdida optimizada por CMA-ES: `heavy` (el reporte muestra ambas metricas, RMSE y cola pesada, para cualquier corrida -- A5, ADR 012 secc. 6).
Tiempo de pared del optimizador: 1940.8s.
Hash de los datos de entrada (`history/*.csv` + `politics/*.csv`): `55596ccc2b19d135647f8e586f2ee4fac2316423603b280cea961857629758a7`.

Vector de calibracion CON el grupo `macro` (A5, ADR 012 secc. 6): simula con `step_macro_economy` (regimen cambiario efectivo + balance de pagos), `fx_regime=pack.fx_regime_auto` (regimen real de cada fecha, `fx_regimes.csv`) y el bloque bimonetario viejo DESACTIVADO (`engine/simulation.py::run` lo apaga en cuanto hay `macro_coefficients`, ver Notas de implementacion del ADR 012).

## Shocks forzados en el periodo

Cada mes de arranque simula con `--historical-shocks --historical-exogenous`: los shocks del calendario real (`politics/shocks_calendar.csv`, ADR 011 secc. 4) estan FORZADOS -- si el modelo reproduce una crisis en un mes donde hubo un shock forzado, no es merito de la dinamica interna calibrada, es el shock. Ver `data/countries/argentina/politics/shocks_calendar.csv` para la lista completa; no se repite aca fila por fila para no duplicar la fuente de verdad.

## Train

n = 124 meses de arranque (20 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.363 | 0.365 | 0.446 | 0.341 |
| inflacion (mensual, %) | 3 | 0.631 | 0.556 | 0.897 | 0.777 |
| inflacion (mensual, %) | 6 | 0.865 | 0.685 | 1.801 | 0.731 |
| inflacion (mensual, %) | 12 | sin dato | 0.720 | 4.360 | 0.849 |
| crecimiento del PBI (anualizado, %) | 1 | 0.592 | 0.262 | 0.593 | 0.591 |
| crecimiento del PBI (anualizado, %) | 3 | 0.880 | 0.769 | 0.867 | 0.863 |
| crecimiento del PBI (anualizado, %) | 6 | 1.072 | 1.046 | 0.986 | 0.923 |
| crecimiento del PBI (anualizado, %) | 12 | sin dato | 1.404 | 1.027 | 0.965 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.307 | 0.349 | 0.338 | 0.318 |
| desempleo (%) | 6 | 0.455 | 0.492 | 0.507 | 0.441 |
| desempleo (%) | 12 | sin dato | 0.636 | 0.787 | 0.818 |
| tipo de cambio oficial (cambio log) | 1 | 0.655 | 0.772 | 0.659 | 0.661 |
| tipo de cambio oficial (cambio log) | 3 | 1.787 | 1.680 | 2.151 | 1.520 |
| tipo de cambio oficial (cambio log) | 6 | 2.813 | 2.870 | 3.825 | 2.111 |
| tipo de cambio oficial (cambio log) | 12 | sin dato | 5.017 | 7.839 | 3.421 |
| reservas (USD M) | 1 | 0.277 | 0.177 | 0.191 | 0.176 |
| reservas (USD M) | 3 | 0.764 | 0.333 | 0.491 | 0.321 |
| reservas (USD M) | 6 | 1.662 | 0.488 | 0.902 | 0.466 |
| reservas (USD M) | 12 | sin dato | 0.705 | 1.386 | 0.660 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.159 | 0.157 | 0.208 | 0.154 |
| inflacion (mensual, %) | 3 | 0.364 | 0.286 | 0.598 | 0.551 |
| inflacion (mensual, %) | 6 | 0.597 | 0.361 | 1.696 | 0.482 |
| inflacion (mensual, %) | 12 | sin dato | 0.419 | 6.917 | 0.594 |
| crecimiento del PBI (anualizado, %) | 1 | 0.354 | 0.088 | 0.356 | 0.354 |
| crecimiento del PBI (anualizado, %) | 3 | 0.665 | 0.429 | 0.647 | 0.647 |
| crecimiento del PBI (anualizado, %) | 6 | 0.939 | 0.764 | 0.811 | 0.734 |
| crecimiento del PBI (anualizado, %) | 12 | sin dato | 1.258 | 0.872 | 0.792 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.151 | 0.177 | 0.172 | 0.161 |
| desempleo (%) | 6 | 0.266 | 0.279 | 0.311 | 0.256 |
| desempleo (%) | 12 | sin dato | 0.416 | 0.528 | 0.537 |
| tipo de cambio oficial (cambio log) | 1 | 0.306 | 0.382 | 0.337 | 0.308 |
| tipo de cambio oficial (cambio log) | 3 | 1.669 | 1.353 | 2.480 | 1.343 |
| tipo de cambio oficial (cambio log) | 6 | 3.220 | 3.258 | 5.903 | 2.174 |
| tipo de cambio oficial (cambio log) | 12 | sin dato | 8.273 | 17.860 | 4.952 |
| reservas (USD M) | 1 | 0.110 | 0.052 | 0.063 | 0.052 |
| reservas (USD M) | 3 | 0.542 | 0.143 | 0.299 | 0.138 |
| reservas (USD M) | 6 | 1.713 | 0.262 | 0.761 | 0.253 |
| reservas (USD M) | 12 | sin dato | 0.494 | 1.407 | 0.460 |

## Holdout

n = 29 meses de arranque (29 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | sin dato | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 3 | sin dato | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 6 | sin dato | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 12 | sin dato | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 1 | 1.062 | 0.558 | 1.060 | 1.059 |
| crecimiento del PBI (anualizado, %) | 3 | 0.964 | 0.558 | 0.969 | 0.952 |
| crecimiento del PBI (anualizado, %) | 6 | 0.786 | 0.759 | 0.490 | 0.917 |
| crecimiento del PBI (anualizado, %) | 12 | sin dato | 1.050 | sin dato | 0.920 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 3 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 6 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 12 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | sin dato | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 3 | sin dato | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 6 | sin dato | sin dato | sin dato | sin dato |
| inflacion (mensual, %) | 12 | sin dato | sin dato | sin dato | sin dato |
| crecimiento del PBI (anualizado, %) | 1 | 1.034 | 0.273 | 1.031 | 1.029 |
| crecimiento del PBI (anualizado, %) | 3 | 0.876 | 0.273 | 0.883 | 0.858 |
| crecimiento del PBI (anualizado, %) | 6 | 0.634 | 0.503 | 0.313 | 0.803 |
| crecimiento del PBI (anualizado, %) | 12 | sin dato | 0.962 | sin dato | 0.809 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 6 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 12 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 1 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 3 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 6 | sin dato | sin dato | sin dato | sin dato |
| tipo de cambio oficial (cambio log) | 12 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 1 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 3 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 6 | sin dato | sin dato | sin dato | sin dato |
| reservas (USD M) | 12 | sin dato | sin dato | sin dato | sin dato |

## Drift de parametros (Aurora -> calibrado)

Top 15 por magnitud de drift, en unidades del RANGO permitido de cada parametro (`(calibrado - aurora) / (hi - lo)`; +-0.5 es la mitad del rango explorable). Tabla completa en `coefficients.json`.

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| dd_gap | macro | 0.15 | 0.4499 | +0.750 |
| t_c | coefficients | 0.2 | 0.5136 | +0.588 |
| conf_ref | coefficients | 45 | 110.2 | +0.543 |
| pi_ref | coefficients | 2 | 4.602 | +0.488 |
| cr_p | coefficients | 0.3 | 0.6725 | +0.466 |
| e_rev_sentiment_k | macro | 10 | 21.64 | +0.436 |
| crime_base | coefficients | 50 | 104 | +0.405 |
| t_p | coefficients | 0.5 | 1.025 | +0.394 |
| s_u | coefficients | 1.5 | 3.021 | +0.380 |
| e_t | coefficients | 1 | 1.942 | +0.353 |
| dd_persistence | macro | 0.9 | 0.6676 | -0.337 |
| gap_perception_k | macro | 0.05 | 0.09391 | +0.329 |
| md_0 | macro | 0.12 | 0.223 | +0.322 |
| im_e | macro | 0.5 | 0.9246 | +0.318 |
| k_flight_peg | macro | 3000 | 5381 | +0.298 |

## Limitaciones

> Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.

Proxies usados en el estado inicial de cada mes: ver `src/republica/calibration/initial_states.py` (docstring del modulo, reglas de interpolacion) y `initial_state_for(date)` para la procedencia `source`/`proxy`/`assumed` de cada variable en cada mes de arranque.
