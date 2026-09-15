# Reporte de experimento -- central_bank_independence

**Hipotesis / descripcion registrada:** Hipotesis: el brazo independiente (autonomy=4, el Banco Central fija la tasa sin pasar por el presidente) tiene menor inflacion anualizada final mediana y mayor desempleo final que el brazo dependiente (autonomy=2, solo recomienda), sin diferencia clara en la tasa de supervivencia entre los dos brazos.


Semillas: 0..49 (50 por brazo). Brazos: 2. Version del paquete: 0.1.0.

## Por brazo

| brazo | N | outcomes | inflation_annual_final | gdp_growth_mean | unemployment_final | approval_final | stability_min | reserves_min | authority_violations | perception_gap_mean | agreements_broken |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dependent | 50 | defeated=36, hyperinflation=7, reelected=6, collapse=1 | 40.27 [29.94, 57.07] | 1.65 [1.29, 1.96] | 8.82 [8.30, 9.51] | 42.86 [41.38, 44.07] | 44.99 [40.03, 47.86] | 5378.88 [2821.68, 7595.22] | 0.00 [0.00, 0.00] | 0.65 [0.58, 0.68] | 0.00 [0.00, 0.00] |
| independent | 50 | defeated=47, reelected=3 | 22.06 [21.07, 25.25] | 0.47 [0.28, 0.60] | 11.08 [10.78, 11.32] | 44.08 [43.24, 44.73] | 43.70 [41.97, 45.82] | 8108.98 [6978.78, 8141.83] | 0.00 [0.00, 0.00] | 0.80 [0.78, 0.81] | 0.00 [0.00, 0.00] |

## Diferencia entre brazos

| brazos | metrica | mediana(a) | mediana(b) | IC diferencia (b-a) | Cliff's delta |
|---|---|---|---|---|---|
| dependent vs independent | inflation_annual_final | 40.27 | 22.06 | [-33.24, -5.86] | -0.53 |
| dependent vs independent | gdp_growth_mean | 1.65 | 0.47 | [-1.55, -0.79] | -0.83 |
| dependent vs independent | unemployment_final | 8.82 | 11.08 | [1.53, 2.82] | +0.78 |
| dependent vs independent | approval_final | 42.86 | 44.08 | [-0.40, 2.90] | +0.20 |
| dependent vs independent | stability_min | 44.99 | 43.70 | [-5.18, 3.63] | +0.01 |
| dependent vs independent | reserves_min | 5378.88 | 8108.98 | [165.13, 5077.30] | +0.40 |
| dependent vs independent | authority_violations | 0.00 | 0.00 | [0.00, 0.00] | +0.00 |
| dependent vs independent | perception_gap_mean | 0.65 | 0.80 | [0.11, 0.22] | +0.72 |
| dependent vs independent | agreements_broken | 0.00 | 0.00 | [0.00, 0.00] | +0.00 |

Graficos: `plots/inflation_annual_final.png`, `plots/gdp_growth_mean.png`, `plots/unemployment_final.png`, `plots/approval_final.png`, `plots/stability_min.png`, `plots/reserves_min.png`, `plots/authority_violations.png`, `plots/perception_gap_mean.png`, `plots/agreements_broken.png`

## Limitaciones

Estos resultados describen el comportamiento de República Artificial bajo sus reglas; no son evidencia sobre economías reales.
