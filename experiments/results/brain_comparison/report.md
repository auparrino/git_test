# Reporte de experimento -- brain_comparison

**Hipotesis / descripcion registrada:** Hipotesis: `fake:rules` reproduce las metricas de `rules` (misma tuberia de decision, solo mediada por un `FakeBackend`) -- sirve de control del experimento. Los brazos `llm:ollama:qwen3:8b`/`llm:ollama:qwen3:32b` (comentados: necesitan un servidor Ollama local, ADR 008 secc. 5.2) miden si un modelo mas grande produce mas `diversity`/menos `authority_violations` que las reglas, a costo de mas `agreements_broken`.


Semillas: 0..29 (30 por brazo). Brazos: 2. Version del paquete: 0.1.0.

## Por brazo

| brazo | N | outcomes | inflation_annual_final | gdp_growth_mean | unemployment_final | approval_final | stability_min | reserves_min | authority_violations | perception_gap_mean | agreements_broken |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rules | 30 | defeated=23, hyperinflation=4, reelected=2, collapse=1 | 36.52 [26.54, 53.10] | 1.75 [1.13, 2.01] | 8.65 [8.18, 9.90] | 43.55 [41.63, 44.44] | 44.92 [40.03, 48.89] | 5378.88 [3358.55, 7429.26] | 0.00 [0.00, 0.00] | 0.67 [0.61, 0.70] | 0.00 [0.00, 0.00] |
| fake_rules | 30 | defeated=23, hyperinflation=4, reelected=2, collapse=1 | 36.52 [26.54, 53.10] | 1.75 [1.13, 2.01] | 8.65 [8.18, 9.90] | 43.55 [41.63, 44.44] | 44.92 [40.03, 48.89] | 5378.88 [3358.55, 7429.26] | 0.00 [0.00, 0.00] | 0.67 [0.61, 0.70] | 0.00 [0.00, 0.00] |

## Diferencia entre brazos

| brazos | metrica | mediana(a) | mediana(b) | IC diferencia (b-a) | Cliff's delta |
|---|---|---|---|---|---|
| rules vs fake_rules | inflation_annual_final | 36.52 | 36.52 | [-19.44, 18.80] | +0.00 |
| rules vs fake_rules | gdp_growth_mean | 1.75 | 1.75 | [-0.67, 0.62] | +0.00 |
| rules vs fake_rules | unemployment_final | 8.65 | 8.65 | [-1.33, 1.34] | +0.00 |
| rules vs fake_rules | approval_final | 43.55 | 43.55 | [-1.97, 2.10] | +0.00 |
| rules vs fake_rules | stability_min | 44.92 | 44.92 | [-6.44, 6.78] | +0.00 |
| rules vs fake_rules | reserves_min | 5378.88 | 5378.88 | [-3023.90, 3113.26] | +0.00 |
| rules vs fake_rules | authority_violations | 0.00 | 0.00 | [0.00, 0.00] | +0.00 |
| rules vs fake_rules | perception_gap_mean | 0.67 | 0.67 | [-0.06, 0.07] | +0.00 |
| rules vs fake_rules | agreements_broken | 0.00 | 0.00 | [0.00, 0.00] | +0.00 |

Graficos: `plots/inflation_annual_final.png`, `plots/gdp_growth_mean.png`, `plots/unemployment_final.png`, `plots/approval_final.png`, `plots/stability_min.png`, `plots/reserves_min.png`, `plots/authority_violations.png`, `plots/perception_gap_mean.png`, `plots/agreements_broken.png`

## Limitaciones

Estos resultados describen el comportamiento de República Artificial bajo sus reglas; no son evidencia sobre economías reales.
