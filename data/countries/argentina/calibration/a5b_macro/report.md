# Calibracion Argentina -- run `a5b_macro`

Pais: `argentina`. Train: `1992-01:2023-12`. Holdout: `1983-12:1991-12`. El holdout (`1983-12:1991-12`) es ANTERIOR en el calendario al train (`1992-01:2023-12`) -- a proposito (A5, ADR 012 secc. 6): el holdout es la hiperinflacion/convertibilidad temprana (1983-1991), nunca vista por esta estructura de precios/regimen cambiario; el orden cronologico no importa para el protocolo de honestidad, solo que el holdout se corra UNA sola vez, DESPUES de fijar los coeficientes con train.
Presupuesto: 400 evaluaciones (usadas: 418). Stride: 3 meses. lambda_reg: 0.01. Semilla: 42. Perdida optimizada por CMA-ES: `heavy` (el reporte muestra ambas metricas, RMSE y cola pesada, para cualquier corrida -- A5, ADR 012 secc. 6).
Tiempo de pared del optimizador: 1912.9s.
Hash de los datos de entrada (`history/*.csv` + `politics/*.csv`): `55596ccc2b19d135647f8e586f2ee4fac2316423603b280cea961857629758a7`.

Vector de calibracion CON el grupo `macro` (A5, ADR 012 secc. 6): simula con `step_macro_economy` (regimen cambiario efectivo + balance de pagos), `fx_regime=pack.fx_regime_auto` (regimen real de cada fecha, `fx_regimes.csv`) y el bloque bimonetario viejo DESACTIVADO (`engine/simulation.py::run` lo apaga en cuanto hay `macro_coefficients`, ver Notas de implementacion del ADR 012).

## Shocks forzados en el periodo

Cada mes de arranque simula con `--historical-shocks --historical-exogenous`: los shocks del calendario real (`politics/shocks_calendar.csv`, ADR 011 secc. 4) estan FORZADOS -- si el modelo reproduce una crisis en un mes donde hubo un shock forzado, no es merito de la dinamica interna calibrada, es el shock. Ver `data/countries/argentina/politics/shocks_calendar.csv` para la lista completa; no se repite aca fila por fila para no duplicar la fuente de verdad.

## Train

n = 124 meses de arranque (20 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.350 | 0.348 | 0.428 | 0.327 |
| inflacion (mensual, %) | 3 | 0.583 | 0.529 | 0.861 | 0.747 |
| inflacion (mensual, %) | 6 | 0.714 | 0.652 | 1.728 | 0.716 |
| inflacion (mensual, %) | 12 | 0.797 | 0.687 | 4.902 | 0.821 |
| crecimiento del PBI (anualizado, %) | 1 | 0.597 | 0.262 | 0.593 | 0.591 |
| crecimiento del PBI (anualizado, %) | 3 | 0.848 | 0.769 | 0.867 | 0.863 |
| crecimiento del PBI (anualizado, %) | 6 | 0.933 | 1.046 | 0.986 | 0.923 |
| crecimiento del PBI (anualizado, %) | 12 | 0.982 | 1.404 | 1.214 | 0.965 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.305 | 0.349 | 0.338 | 0.318 |
| desempleo (%) | 6 | 0.436 | 0.492 | 0.507 | 0.441 |
| desempleo (%) | 12 | 0.751 | 0.636 | 1.126 | 0.818 |
| tipo de cambio oficial (cambio log) | 1 | 0.656 | 0.772 | 0.659 | 0.661 |
| tipo de cambio oficial (cambio log) | 3 | 1.585 | 1.680 | 2.151 | 1.520 |
| tipo de cambio oficial (cambio log) | 6 | 2.407 | 2.870 | 3.825 | 2.111 |
| tipo de cambio oficial (cambio log) | 12 | 4.360 | 5.017 | 8.257 | 3.421 |
| reservas (USD M) | 1 | 0.178 | 0.177 | 0.191 | 0.176 |
| reservas (USD M) | 3 | 0.388 | 0.333 | 0.491 | 0.321 |
| reservas (USD M) | 6 | 0.603 | 0.488 | 0.902 | 0.466 |
| reservas (USD M) | 12 | 0.838 | 0.705 | 1.521 | 0.660 |

| regimen (acierto democracia/no) | - | 1.000 | - | 1.000 | 1.000 |
| elecciones (acierto reelegido/derrotado) | - | sin dato | - | sin dato | sin dato |



### Pérdida cola pesada (`|error/sigma|^1.5`, A5/ADR 012 secc. 6)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.145 | 0.143 | 0.194 | 0.143 |
| inflacion (mensual, %) | 3 | 0.293 | 0.260 | 0.557 | 0.514 |
| inflacion (mensual, %) | 6 | 0.387 | 0.329 | 1.574 | 0.472 |
| inflacion (mensual, %) | 12 | 0.491 | 0.385 | 8.210 | 0.563 |
| crecimiento del PBI (anualizado, %) | 1 | 0.354 | 0.088 | 0.356 | 0.354 |
| crecimiento del PBI (anualizado, %) | 3 | 0.616 | 0.429 | 0.647 | 0.647 |
| crecimiento del PBI (anualizado, %) | 6 | 0.747 | 0.764 | 0.811 | 0.734 |
| crecimiento del PBI (anualizado, %) | 12 | 0.819 | 1.258 | 1.099 | 0.792 |
| desempleo (%) | 1 | sin dato | sin dato | sin dato | sin dato |
| desempleo (%) | 3 | 0.153 | 0.177 | 0.172 | 0.161 |
| desempleo (%) | 6 | 0.258 | 0.279 | 0.311 | 0.256 |
| desempleo (%) | 12 | 0.489 | 0.416 | 0.885 | 0.537 |
| tipo de cambio oficial (cambio log) | 1 | 0.305 | 0.382 | 0.337 | 0.308 |
| tipo de cambio oficial (cambio log) | 3 | 1.371 | 1.353 | 2.480 | 1.343 |
| tipo de cambio oficial (cambio log) | 6 | 2.620 | 3.258 | 5.903 | 2.174 |
| tipo de cambio oficial (cambio log) | 12 | 6.365 | 8.273 | 19.282 | 4.952 |
| reservas (USD M) | 1 | 0.054 | 0.052 | 0.063 | 0.052 |
| reservas (USD M) | 3 | 0.196 | 0.143 | 0.299 | 0.138 |
| reservas (USD M) | 6 | 0.397 | 0.262 | 0.761 | 0.253 |
| reservas (USD M) | 12 | 0.635 | 0.494 | 1.617 | 0.460 |



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.000 | 0.000 | 0.000 |
| 12 | 0.000 | 0.048 | 0.000 |

## Holdout

n = 29 meses de arranque (29 con peso 0.5: series mensuales interpoladas de anuales antes de 1997, A5/ADR 012 secc. 6).



### RMSE normalizada (misma formula que `a3_main`)

| variable | horizonte | calibrado | persistencia | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|---|---|
| inflacion (mensual, %) | 1 | 0.636 | 0.465 | 1.205 | 2.938 |
| inflacion (mensual, %) | 3 | 1.283 | 1.139 | 6.487 | 5.174 |
| inflacion (mensual, %) | 6 | 2.696 | 2.178 | 8.073 | 6.548 |
| inflacion (mensual, %) | 12 | 4.369 | 4.005 | 9.752 | 6.691 |
| crecimiento del PBI (anualizado, %) | 1 | 1.057 | 0.558 | 1.060 | 1.059 |
| crecimiento del PBI (anualizado, %) | 3 | 0.957 | 0.558 | 0.969 | 0.946 |
| crecimiento del PBI (anualizado, %) | 6 | 1.965 | 0.759 | 2.624 | 0.900 |
| crecimiento del PBI (anualizado, %) | 12 | 2.354 | 1.050 | 3.000 | 0.880 |
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
| inflacion (mensual, %) | 1 | 0.458 | 0.237 | 1.183 | 4.600 |
| inflacion (mensual, %) | 3 | 1.165 | 1.003 | 14.768 | 10.841 |
| inflacion (mensual, %) | 6 | 3.965 | 2.721 | 21.808 | 15.199 |
| inflacion (mensual, %) | 12 | 8.424 | 7.101 | 28.755 | 15.396 |
| crecimiento del PBI (anualizado, %) | 1 | 1.022 | 0.273 | 1.031 | 1.029 |
| crecimiento del PBI (anualizado, %) | 3 | 0.861 | 0.273 | 0.883 | 0.850 |
| crecimiento del PBI (anualizado, %) | 6 | 2.427 | 0.503 | 4.018 | 0.779 |
| crecimiento del PBI (anualizado, %) | 12 | 3.321 | 0.962 | 5.196 | 0.761 |
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



### Corridas que terminaron antes del horizonte (hiperinflacion/colapso)

| horizonte | calibrado | Aurora sin calibrar | `a3_main` (sin macro) |
|---|---|---|---|
| 1 | 0.000 | 0.000 | 0.000 |
| 3 | 0.000 | 0.000 | 0.000 |
| 6 | 0.379 | 0.759 | 0.000 |
| 12 | 0.586 | 1.000 | 0.000 |

## Drift de parametros (Aurora -> calibrado)

Top 15 por magnitud de drift, en unidades del RANGO permitido de cada parametro (`(calibrado - aurora) / (hi - lo)`; +-0.5 es la mitad del rango explorable). Tabla completa en `coefficients.json`.

| parametro | grupo | Aurora | calibrado | drift (unidades del rango) |
|---|---|---|---|---|
| p_i | coefficients | 0.5 | 1.5 | +0.750 |
| st_a | coefficients | 0.3 | 0.8794 | +0.724 |
| x0_m0_pct_gdp | macro | 0.18 | 0.5165 | +0.701 |
| e_w | coefficients | 1.5 | 4.189 | +0.672 |
| t_pr | coefficients | 0.2 | 0.5569 | +0.669 |
| md_0 | macro | 0.12 | 0.3317 | +0.661 |
| rho_pi | coefficients | 0.85 | 2.298 | +0.639 |
| st_t | coefficients | 0.4 | 1.077 | +0.635 |
| pr_a | coefficients | 0.2 | 0.5327 | +0.624 |
| st_i | coefficients | 0.2 | 0.5269 | +0.613 |
| stability_base | coefficients | 60 | 157 | +0.606 |
| e_g | coefficients | 3 | 7.679 | +0.585 |
| province_transfer_sensitivity | coefficients | 0.5 | 1.257 | +0.568 |
| rho_pi | macro | 0.85 | 0.5852 | -0.530 |
| ic_target_bonus | macro | 10 | 23.83 | +0.519 |

## Limitaciones

> Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.

Proxies usados en el estado inicial de cada mes: ver `src/republica/calibration/initial_states.py` (docstring del modulo, reglas de interpolacion) y `initial_state_for(date)` para la procedencia `source`/`proxy`/`assumed` de cada variable en cada mes de arranque.

### Adenda manual (post-corrida): diagnostico 2019-12 y lectura honesta

**Diagnostico 2019-12 (hallazgo del agente de ADR 013, verificado antes y despues de esta corrida):**
con los coeficientes macro DEFAULT (sin calibrar) y `--fx-regime auto`, una corrida desde 2019-12 (48
meses, `--country argentina`) entraba en `hyperinflation` en **20/20 semillas (100 %)** antes del mes
13. Con los coeficientes CALIBRADOS de esta corrida (`a5b_macro`), el mismo escenario (20 semillas,
1-20) da **0/20 (0 %) en `hyperinflation`** -- pero **20/20 (100 %) en `collapse`** (`political_
stability < 15` tres meses seguidos), con mediana de colapso en el mes 25 (rango 20-27, es decir entre
~2021-08 y ~2022-03). Lectura honesta: la calibracion elimina la hiperinflacion espuria de este tramo
(el mecanismo `rho_eff`/`seigniorage_pressure` ya no diverge desde este estado inicial), pero NINGUNA
semilla sobrevive los 48 meses -- el fallo cambia de canal (precios -> estabilidad politica), no
desaparece. Esto es relevante para V4 (2019-12->2023-12, ver `data/countries/argentina/validation/
a6_macro/`): si el `collapse` ocurre sistematicamente antes de la eleccion de fin de mandato, la
hipotesis electoral de V4 no se puede evaluar con la misma confianza que la de inflacion.

**Tipo de cambio sin dato en el holdout completo:** las 20 filas "sin dato" de tipo de cambio/reservas/
desempleo en la tabla de Holdout de arriba no son un bug: `exchange_rate_official_monthly.csv`
arranca en 1992-01 (el holdout es enteramente `1983-12:1991-12`, ANTES de esa fecha) y, a diferencia
de la inflacion (que si tiene `inflation_cpi_annual_linked.csv` cubriendo hasta el presente, usado para
el fallback de A5b), la unica serie ANUAL de tipo de cambio del paquete (`exchange_rate_annual.csv`,
compilacion Clio Infra) **termina en 1951** -- no cubre 1983-1991, asi que NO se puede aplicar el mismo
fallback de interpolacion sin conseguir un dato nuevo (BCRA historico, fuera de este entorno). La serie
paralela (`exchange_rate_parallel_monthly_linked.csv`) arranca recien en 2008, tampoco sirve. Pendiente,
no implementado en esta ronda: conseguir una serie de tipo de cambio 1983-1991 (oficial o "dolar bolsa"
de la epoca) y aplicar el mismo patron de `RealData.inflation()` (interpolacion anual + fallback) si
aparece.

**Lectura honesta del train vs. holdout (pedida explicitamente, sin adornos):** en TRAIN, el brazo
calibrado queda A LA PAR o LEVEMENTE PEOR que la persistencia en la mayoria de las filas (inflacion:
peor en h=3/6/12, ~igual en h=1; reservas: peor en h=3/6/12; PBI: peor en h=1/3, mejor en h=6/12;
desempleo/tipo de cambio: mejor en la mayoria de los horizontes) -- 107+58 parametros calibrados no
superan de forma consistente al baseline ingenuo de "no cambia nada" dentro de la propia ventana de
ajuste. En HOLDOUT, el calibrado mejora MUCHO a Aurora sin calibrar y a `a3_main` en inflacion (p.ej.
h=12 RMSE: calibrado 4.369 vs Aurora 9.752 vs `a3_main` 6.691) pero SIGUE POR DETRAS de la persistencia
en casi todos los horizontes de inflacion (h=1: 0.636 vs 0.465; h=3: 1.283 vs 1.139; h=6: 2.696 vs
2.178; h=12: 4.369 vs 4.005) y de PBI (calibrado peor que persistencia en los 4 horizontes). Una
excepcion notable: en PBI del holdout, `a3_main` (sin macro, sin recalibrar con la ventana nueva) da
MEJOR resultado que el calibrado de esta corrida en h=6/12 (0.900/0.880 contra 1.965/2.354) -- el
PBI no esta gobernado por la capa macro (ADR 012 no la toca), asi que esto sugiere que calibrar 155
parametros conjuntamente (economicos + macro) sobre una perdida dominada por precios/reservas/cambiario
puede empeorar el ajuste de variables que no dependen de esos mecanismos, respecto de calibrar el
bloque economico solo (`a3_main`). No se investigo mas a fondo en esta ronda.
