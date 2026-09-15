# Calibracion Argentina -- run `a3_main`

Pais: `argentina`. Train: `1993-01:2015-12`. Holdout: `2016-01:2023-12` (corrido UNA SOLA VEZ, al final, despues de fijar los coeficientes con train -- protocolo de honestidad, PLAN_ARGENTINA.md #0.3/#4).
Presupuesto: 300 evaluaciones (usadas: 306). Stride: 3 meses. lambda_reg: 0.01. Semilla: 42.
Tiempo de pared del optimizador: 790.4s.
Hash de los datos de entrada (`history/*.csv` + `politics/*.csv`): `20c0af61efe5611dee55822b5d26754d20f0d52915b01584c1d71bf978469bd4`.

## Shocks forzados en el periodo

Cada mes de arranque simula con `--historical-shocks --historical-exogenous`: los shocks del calendario real (`politics/shocks_calendar.csv`, ADR 011 secc. 4) estan FORZADOS -- si el modelo reproduce una crisis en un mes donde hubo un shock forzado, no es merito de la dinamica interna calibrada, es el shock. Ver `data/countries/argentina/politics/shocks_calendar.csv` para la lista completa; no se repite aca fila por fila para no duplicar la fuente de verdad.

## Train

n = 88 meses de arranque.

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar |
|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.268 | 0.349 | 0.359 |
| inflacion (mensual, %) | 3 | 0.616 | 0.561 | 0.673 |
| inflacion (mensual, %) | 6 | 0.584 | 0.709 | 0.886 |
| inflacion (mensual, %) | 12 | 0.550 | 0.711 | 1.149 |
| crecimiento del PBI (anualizado, %) | 1 | 0.688 | 0.152 | 0.692 |
| crecimiento del PBI (anualizado, %) | 3 | 0.800 | 0.497 | 0.830 |
| crecimiento del PBI (anualizado, %) | 6 | 0.818 | 0.748 | 0.915 |
| crecimiento del PBI (anualizado, %) | 12 | 0.865 | 1.101 | 0.900 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.296 | 0.323 | 0.340 |
| desempleo (%) | 6 | 0.375 | 0.442 | 0.514 |
| desempleo (%) | 12 | 0.930 | 0.596 | 1.069 |
| tipo de cambio oficial (cambio log) | 1 | 0.303 | 0.354 | 0.303 |
| tipo de cambio oficial (cambio log) | 3 | 1.620 | 1.471 | 1.726 |
| tipo de cambio oficial (cambio log) | 6 | 2.728 | 2.502 | 3.183 |
| tipo de cambio oficial (cambio log) | 12 | 4.223 | 3.982 | 6.034 |
| reservas (USD M) | 1 | 0.112 | 0.110 | 0.112 |
| reservas (USD M) | 3 | 0.227 | 0.230 | 0.228 |
| reservas (USD M) | 6 | 0.362 | 0.356 | 0.362 |
| reservas (USD M) | 12 | 0.632 | 0.590 | 0.676 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato |

## Holdout

n = 28 meses de arranque.

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar |
|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.494 | 0.420 | 0.469 |
| inflacion (mensual, %) | 3 | 1.147 | 0.565 | 0.599 |
| inflacion (mensual, %) | 6 | 0.934 | 0.583 | 0.636 |
| inflacion (mensual, %) | 12 | 1.256 | 0.713 | 0.877 |
| crecimiento del PBI (anualizado, %) | 1 | 0.355 | 0.450 | 0.349 |
| crecimiento del PBI (anualizado, %) | 3 | 1.069 | 1.295 | 1.073 |
| crecimiento del PBI (anualizado, %) | 6 | 1.210 | 1.659 | 1.225 |
| crecimiento del PBI (anualizado, %) | 12 | 1.248 | 2.081 | 1.297 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.352 | 0.398 | 0.352 |
| desempleo (%) | 6 | 0.495 | 0.571 | 0.475 |
| desempleo (%) | 12 | 0.586 | 0.668 | 0.528 |
| tipo de cambio oficial (cambio log) | 1 | 1.226 | 1.423 | 1.234 |
| tipo de cambio oficial (cambio log) | 3 | 1.105 | 1.879 | 1.227 |
| tipo de cambio oficial (cambio log) | 6 | 1.583 | 3.343 | 1.796 |
| tipo de cambio oficial (cambio log) | 12 | 3.929 | 6.750 | 3.986 |
| reservas (USD M) | 1 | 0.288 | 0.293 | 0.286 |
| reservas (USD M) | 3 | 0.493 | 0.515 | 0.497 |
| reservas (USD M) | 6 | 0.684 | 0.733 | 0.694 |
| reservas (USD M) | 12 | 0.946 | 0.966 | 0.877 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato |

## Drift de parametros (Aurora -> calibrado)

Top 15 por magnitud de drift, en unidades del RANGO permitido de cada parametro (`(calibrado - aurora) / (hi - lo)`; +-0.5 es la mitad del rango explorable). Tabla completa en `coefficients.json`.

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| protest_ref | coefficients | 15 | 37.8 | +0.570 |
| r_gap_max | coefficients | 30 | 63.92 | +0.424 |
| ic_pi | coefficients | 0.5 | 0.9787 | +0.359 |
| crime_base | coefficients | 50 | 92.82 | +0.321 |
| conf_ref | coefficients | 45 | 83.35 | +0.320 |
| cr_u | coefficients | 0.5 | 0.9095 | +0.307 |
| c_f | coefficients | 0.12 | 0.2176 | +0.305 |
| p_i | coefficients | 0.5 | 0.899 | +0.299 |
| st_a | coefficients | 0.3 | 0.5274 | +0.284 |
| q_w | coefficients | 0.5 | 0.8776 | +0.283 |
| s_g | coefficients | 2 | 3.393 | +0.261 |
| s_u | coefficients | 1.5 | 2.535 | +0.259 |
| f_u | coefficients | 0.1 | 0.1667 | +0.250 |
| d_w | coefficients | 0.05 | 0.01678 | -0.249 |
| cr_adj | coefficients | 0.1 | 0.1662 | +0.248 |

## Limitaciones

> Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.

Proxies usados en el estado inicial de cada mes: ver `src/republica/calibration/initial_states.py` (docstring del modulo, reglas de interpolacion) y `initial_state_for(date)` para la procedencia `source`/`proxy`/`assumed` de cada variable en cada mes de arranque.
