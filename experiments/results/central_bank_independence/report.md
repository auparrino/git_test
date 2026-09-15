# Reporte de experimento -- central_bank_independence

**Hipotesis / descripcion registrada:** Hipotesis: el brazo independiente (autonomy=4, el Banco Central fija la tasa sin pasar por el presidente) tiene menor inflacion anualizada final mediana y mayor desempleo final que el brazo dependiente (autonomy=2, solo recomienda), sin diferencia clara en la tasa de supervivencia entre los dos brazos.


Semillas: 0..49 (50 por brazo). Brazos: 2. Version del paquete: 0.1.0.

## Por brazo

| brazo | N | outcomes | inflation_annual_final | gdp_growth_mean | unemployment_final | approval_final | stability_min | reserves_min | authority_violations | perception_gap_mean | agreements_broken |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dependent | 50 | reelected=25, defeated=17, hyperinflation=8 | 38.86 [29.51, 52.26] | 1.66 [1.30, 1.96] | 8.85 [8.27, 9.51] | 35.18 [33.04, 40.50] | 49.06 [43.69, 52.25] | 5553.28 [3133.33, 7595.38] | 0.00 [0.00, 0.00] | 0.09 [0.08, 0.11] | 0.00 [0.00, 0.00] |
| independent | 50 | defeated=27, reelected=23 | 23.48 [20.78, 26.00] | 0.49 [0.29, 0.63] | 10.96 [10.77, 11.31] | 40.49 [34.20, 41.47] | 47.72 [46.12, 49.70] | 8095.43 [6978.81, 8141.83] | 0.00 [0.00, 0.00] | 0.16 [0.16, 0.17] | 0.00 [0.00, 0.00] |

## Diferencia entre brazos

| brazos | metrica | mediana(a) | mediana(b) | IC diferencia (b-a) | Cliff's delta |
|---|---|---|---|---|---|
| dependent vs independent | inflation_annual_final | 38.86 | 23.48 | [-29.07, -4.94] | -0.50 |
| dependent vs independent | gdp_growth_mean | 1.66 | 0.49 | [-1.52, -0.77] | -0.82 |
| dependent vs independent | unemployment_final | 8.85 | 10.96 | [1.46, 2.82] | +0.76 |
| dependent vs independent | approval_final | 35.18 | 40.49 | [-2.89, 7.91] | +0.11 |
| dependent vs independent | stability_min | 49.06 | 47.72 | [-4.98, 4.00] | +0.01 |
| dependent vs independent | reserves_min | 5553.28 | 8095.43 | [175.17, 4677.49] | +0.39 |
| dependent vs independent | authority_violations | 0.00 | 0.00 | [0.00, 0.00] | +0.00 |
| dependent vs independent | perception_gap_mean | 0.09 | 0.16 | [0.05, 0.09] | +0.76 |
| dependent vs independent | agreements_broken | 0.00 | 0.00 | [0.00, 0.00] | +0.00 |

Graficos: `plots/inflation_annual_final.png`, `plots/gdp_growth_mean.png`, `plots/unemployment_final.png`, `plots/approval_final.png`, `plots/stability_min.png`, `plots/reserves_min.png`, `plots/authority_violations.png`, `plots/perception_gap_mean.png`, `plots/agreements_broken.png`

## Limitaciones

Estos resultados describen el comportamiento de República Artificial bajo sus reglas; no son evidencia sobre economías reales.
