# Reporte de experimento -- fiscal_rule

**Hipotesis / descripcion registrada:** Hipotesis: la supervivencia cae y la inflacion anualizada final sube a medida que aumenta `c_f` (mas traspaso de deficit a precios) y/o `primary_spending` (mas gasto primario, a igual `tax_rate`) -- el mapa de calor deberia mostrar el peor cuadrante en c_f=0.16 x primary_spending=27 y el mejor en c_f=0.08 x primary_spending=23.


Semillas: 0..19 (20 por brazo). Brazos: 9. Version del paquete: 0.1.0.

## Por brazo

| brazo | N | outcomes | inflation_annual_final | gdp_growth_mean | unemployment_final | approval_final | stability_min | reserves_min |
|---|---|---|---|---|---|---|---|---|
| base__c_f=0.08__primary_spending=23 | 20 | defeated=20 | -11.36 [-11.36, -11.36] | -2.90 [-3.16, -2.76] | 17.38 [16.83, 17.59] | 44.03 [43.49, 45.00] | 43.75 [40.68, 45.71] | 8000.72 [7877.47, 8171.33] |
| base__c_f=0.08__primary_spending=25 | 20 | defeated=20 | -11.36 [-11.36, -11.32] | -1.56 [-1.87, -1.40] | 15.34 [14.80, 15.51] | 44.30 [43.63, 44.88] | 45.90 [43.03, 48.27] | 7929.22 [7405.13, 8139.94] |
| base__c_f=0.08__primary_spending=27 | 20 | hyperinflation=11, defeated=9 | 1017.68 [713.91, 1321.07] | 4.01 [3.79, 4.54] | 5.86 [4.80, 6.25] | 0.00 [0.00, 44.56] | 19.78 [16.64, 25.14] | 0.00 [0.00, 19.10] |
| base__c_f=0.12__primary_spending=23 | 20 | defeated=20 | -8.23 [-10.65, -3.12] | -2.83 [-2.95, -2.71] | 17.07 [16.75, 17.34] | 45.64 [45.01, 46.32] | 39.69 [36.86, 41.35] | 7985.14 [7842.06, 8146.67] |
| base__c_f=0.12__primary_spending=25 | 20 | defeated=18, hyperinflation=1, reelected=1 | 36.52 [28.88, 53.10] | 1.61 [0.98, 1.93] | 8.72 [8.20, 10.44] | 43.90 [42.76, 44.76] | 46.00 [42.64, 48.73] | 5644.77 [3821.50, 7655.80] |
| base__c_f=0.12__primary_spending=27 | 20 | hyperinflation=17, collapse=2, defeated=1 | 1225.06 [1061.08, 1445.60] | 3.95 [3.70, 4.53] | 6.26 [5.34, 7.02] | 0.00 [0.00, 0.00] | 15.16 [13.69, 16.17] | 0.00 [0.00, 0.00] |
| base__c_f=0.16__primary_spending=23 | 20 | defeated=20 | 16.24 [13.70, 18.78] | -1.98 [-2.19, -1.68] | 14.84 [14.29, 15.49] | 45.61 [44.48, 46.39] | 38.65 [37.48, 40.87] | 7966.17 [7797.43, 8139.42] |
| base__c_f=0.16__primary_spending=25 | 20 | defeated=14, hyperinflation=4, reelected=2 | 216.96 [51.91, 662.95] | 2.63 [2.53, 2.80] | 7.58 [7.10, 8.03] | 43.84 [41.22, 47.01] | 36.17 [23.51, 45.34] | 677.62 [0.00, 5560.11] |
| base__c_f=0.16__primary_spending=27 | 20 | hyperinflation=17, collapse=3 | 1398.19 [1231.96, 1764.38] | 3.96 [3.70, 4.13] | 6.50 [6.06, 6.99] | 0.00 [0.00, 0.00] | 13.32 [11.84, 15.37] | 0.00 [0.00, 0.00] |

## Mapa de calor (country.coefficients.c_f x country.default_policy.primary_spending)

Supervivencia (%):

| c_f \ primary_spending | 23 | 25 | 27 |
|---|---|---|---|
| 0.08 | 100 % | 100 % | 45 % |
| 0.12 | 100 % | 95 % | 5 % |
| 0.16 | 100 % | 80 % | 0 % |

![supervivencia](plots/survival_rate.png)

inflation_annual_final (mediana):

| c_f \ primary_spending | 23 | 25 | 27 |
|---|---|---|---|
| 0.08 | -11.36 | -11.36 | 1017.68 |
| 0.12 | -8.23 | 36.52 | 1225.06 |
| 0.16 | 16.24 | 216.96 | 1398.19 |

![inflation_annual_final](plots/inflation_annual_final.png)

gdp_growth_mean (mediana):

| c_f \ primary_spending | 23 | 25 | 27 |
|---|---|---|---|
| 0.08 | -2.90 | -1.56 | 4.01 |
| 0.12 | -2.83 | 1.61 | 3.95 |
| 0.16 | -1.98 | 2.63 | 3.96 |

![gdp_growth_mean](plots/gdp_growth_mean.png)

## Limitaciones

Estos resultados describen el comportamiento de República Artificial bajo sus reglas; no son evidencia sobre economías reales.
