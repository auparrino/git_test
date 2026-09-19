# Sonda exploratoria (ADR 020)

País: **argentina** · calibración: **a9_clean** · semillas: **10** (desde 1) · transiciones de régimen: **sí** · 17.9 s

Escenarios: `data/countries/argentina/probe_scenarios.csv` (6 filas).

Esto **no es un backtest ni una validación**. El backtest (ADR 014) puntúa objetivos contra series reales en ventanas rodantes; la validación (ADR 011 §8) puntúa hipótesis registradas antes de correr. La sonda **no puntúa nada**: corre unos pocos arranques históricos con muchas semillas y describe el comportamiento del modelo, buscando síntomas de que algo esté mal mecánicamente.

---

## Resumen

| escenario | arranque | pedidos | fin (mediana) | mín–máx | outcomes | variables saturadas | fuera de rango |
|---|---|---:|---:|---|---|---:|---:|
| `1983-12` | 1983-12 | 72 | **72** | 71–72 | `defeated` 9, `hyperinflation` 1 | 13 | 0 |
| `1991-04` | 1991-04 | 120 | **120** | 120–120 | `survived` 10 | 13 | 0 |
| `1998-01` | 1998-01 | 60 | **60** | 60–60 | `survived` 10 | 8 | 0 |
| `2003-06` | 2003-06 | 150 | **150** | 150–150 | `survived` 10 | 14 | 0 |
| `2015-12` | 2015-12 | 48 | **48** | 45–48 | `defeated` 9, `collapse` 1 | 7 | 0 |
| `2019-12` | 2019-12 | 48 | **48** | 48–48 | `defeated` 10 | 7 | 0 |

## Escenarios y lo que pasó de verdad

| escenario | arranque | meses | qué pasó de verdad |
|---|---|---:|---|
| `1983-12` | 1983-12 | 72 | Vuelta a la democracia. Plan Austral (1985) y despues el Austral II; la hiperinflacion llego recien en 1989, en el mes 66 de esta ventana. |
| `1991-04` | 1991-04 | 120 | Arranque de la convertibilidad. Una decada de tipo de cambio fijo e inflacion de un digito anual; el regimen aguanto los 120 meses completos. |
| `1998-01` | 1998-01 | 60 | Ultimo ano de crecimiento antes de la recesion 1999-2001. Default y salida del peg en 2001-12, el mes 47 de esta ventana. |
| `2003-06` | 2003-06 | 150 | Salida de la crisis. La decada de mayor crecimiento reciente; sin colapso ni hiperinflacion en toda la ventana. |
| `2015-12` | 2015-12 | 48 | Cambio de gobierno con salida del cepo. Mandato completo de 48 meses y derrota del oficialismo en la eleccion de 2019. |
| `2019-12` | 2019-12 | 48 | Cambio de gobierno, pandemia en 2020 y sequia en 2023. Mandato completo de 48 meses, inflacion ~211 % interanual al cierre y derrota del oficialismo en 2023. |

La comparación con esa columna la hace un humano: la sonda la imprime al lado del resultado y **no la puntúa** (ADR 020 §2.1).

---

## Detalle por escenario

### `1983-12` — arranque 1983-12, 72 meses pedidos

**Qué pasó de verdad:** Vuelta a la democracia. Plan Austral (1985) y despues el Austral II; la hiperinflacion llego recien en 1989, en el mes 66 de esta ventana.

Semillas usables: **10**. Outcomes: `defeated` 9, `hyperinflation` 1.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **72** | 71 | 72 | 72 | 9/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `institutional_confidence` | lo = 0 | 10/10 | 7.0 | 66.0 | 92 % |
| `political_stability` | hi = 100 | 10/10 | 11.0 | 62.0 | 86 % |
| `real_wage` | hi = 200 | 10/10 | 11.0 | 62.0 | 86 % |
| `government_approval` | hi = 100 | 10/10 | 13.5 | 58.5 | 81 % |
| `interest_rate` | hi = 300 | 10/10 | 15.5 | 57.0 | 79 % |
| `exchange_rate` | hi = 1e+06 | 10/10 | 35.0 | 38.0 | 53 % |
| `poverty` | lo = 0 | 10/10 | 38.0 | 35.0 | 49 % |
| `consumer_confidence` | lo = 0 | 9/10 | 34.0 | 31.0 | 43 % |
| `inequality` | lo = 20 | 10/10 | 49.0 | 24.0 | 33 % |
| `protest_level` | lo = 0 | 10/10 | 32.0 | 19.5 | 27 % |
| `crime_perception` | hi = 100 | 10/10 | 8.0 | 15.0 | 21 % |
| `social_tension` | lo = 0 | 10/10 | 4.5 | 6.5 | 9 % |
| `reserves` | lo = 0 | 10/10 | 11.0 | 6.5 | 9 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_honored:gov_buenos_aires:restore_transfers` | 10/10 | 2.0 |
| `agreement_honored:biz_agro:tax_exemption` | 10/10 | 4.0 |
| `fx_regime_exit` | 10/10 | 5.0 |
| `fx_vector_switch:float` | 10/10 | 6.0 |
| `forced_devaluation` | 10/10 | 7.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 9/10 | 10.0 |
| `election:pj` | 9/10 | 72.0 |
| `term_end:defeated` | 9/10 | 72.0 |
| `agreement_honored:gov_caba:restore_transfers` | 8/10 | 9.5 |
| `agreement_honored:gov_mendoza:restore_transfers` | 5/10 | 11.0 |

### `1991-04` — arranque 1991-04, 120 meses pedidos

**Qué pasó de verdad:** Arranque de la convertibilidad. Una decada de tipo de cambio fijo e inflacion de un digito anual; el regimen aguanto los 120 meses completos.

Semillas usables: **10**. Outcomes: `survived` 10.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **120** | 120 | 120 | 120 | 10/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `political_stability` | hi = 100 | 10/10 | 1.0 | 104.0 | 87 % |
| `institutional_confidence` | lo = 0 | 10/10 | 17.5 | 103.5 | 86 % |
| `real_wage` | hi = 200 | 10/10 | 20.0 | 101.0 | 84 % |
| `government_approval` | hi = 100 | 10/10 | 27.0 | 92.0 | 77 % |
| `social_tension` | lo = 0 | 10/10 | 39.5 | 78.5 | 65 % |
| `poverty` | lo = 0 | 10/10 | 48.5 | 72.5 | 60 % |
| `inequality` | lo = 20 | 10/10 | 49.0 | 72.0 | 60 % |
| `protest_level` | lo = 0 | 10/10 | 30.0 | 65.5 | 55 % |
| `unemployment` | lo = 2 | 10/10 | 65.0 | 52.0 | 43 % |
| `exchange_rate` | hi = 1e+06 | 10/10 | 79.5 | 41.5 | 35 % |
| `crime_perception` | hi = 100 | 10/10 | 10.0 | 16.0 | 13 % |
| `interest_rate` | hi = 300 | 8/10 | 112.5 | 8.5 | 7 % |
| `reserves` | lo = 0 | 4/10 | 21.5 | 2.0 | 2 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_honored:gov_buenos_aires:restore_transfers` | 10/10 | 2.0 |
| `agreement_honored:biz_agro:tax_exemption` | 10/10 | 4.0 |
| `fx_regime_exit` | 10/10 | 7.0 |
| `fx_vector_switch:float` | 10/10 | 8.0 |
| `agreement_honored:gov_rio_negro:restore_transfers` | 10/10 | 12.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 10/10 | 12.5 |
| `forced_devaluation` | 10/10 | 17.5 |
| `election:ucr` | 10/10 | 72.0 |
| `term_end:survived` | 10/10 | 120.0 |
| `agreement_honored:gov_caba:restore_transfers` | 9/10 | 21.0 |

### `1998-01` — arranque 1998-01, 60 meses pedidos

**Qué pasó de verdad:** Ultimo ano de crecimiento antes de la recesion 1999-2001. Default y salida del peg en 2001-12, el mes 47 de esta ventana.

Semillas usables: **10**. Outcomes: `survived` 10.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **60** | 60 | 60 | 60 | 10/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `crime_perception` | hi = 100 | 10/10 | 13.0 | 30.5 | 51 % |
| `political_stability` | hi = 100 | 10/10 | 1.0 | 29.5 | 49 % |
| `real_wage` | hi = 200 | 10/10 | 40.5 | 20.5 | 34 % |
| `government_approval` | lo = 0 | 10/10 | 13.0 | 16.5 | 28 % |
| `protest_level` | lo = 0 | 10/10 | 47.0 | 13.5 | 22 % |
| `institutional_confidence` | lo = 0 | 10/10 | 32.0 | 7.5 | 12 % |
| `reserves` | lo = 0 | 9/10 | 28.0 | 4.0 | 7 % |
| `social_tension` | lo = 0 | 9/10 | 56.0 | 4.0 | 7 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_honored:biz_agro:tax_exemption` | 10/10 | 4.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 10/10 | 9.5 |
| `fx_regime_exit` | 10/10 | 9.5 |
| `fx_vector_switch:float` | 10/10 | 10.5 |
| `forced_devaluation` | 10/10 | 26.0 |
| `agreement_honored:gov_caba:restore_transfers` | 10/10 | 29.0 |
| `election:ucr` | 10/10 | 48.0 |
| `term_end:survived` | 10/10 | 60.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 9/10 | 28.0 |
| `agreement_honored:gov_rio_negro:restore_transfers` | 8/10 | 17.0 |

### `2003-06` — arranque 2003-06, 150 meses pedidos

**Qué pasó de verdad:** Salida de la crisis. La decada de mayor crecimiento reciente; sin colapso ni hiperinflacion en toda la ventana.

Semillas usables: **10**. Outcomes: `survived` 10.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **150** | 150 | 150 | 150 | 10/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `political_stability` | hi = 100 | 10/10 | 39.0 | 112.0 | 75 % |
| `real_wage` | hi = 200 | 10/10 | 46.0 | 105.0 | 70 % |
| `social_tension` | lo = 0 | 10/10 | 47.0 | 104.0 | 69 % |
| `protest_level` | lo = 0 | 10/10 | 43.0 | 100.0 | 67 % |
| `government_approval` | hi = 100 | 10/10 | 48.5 | 93.5 | 62 % |
| `inequality` | lo = 20 | 10/10 | 70.0 | 81.0 | 54 % |
| `poverty` | lo = 0 | 10/10 | 71.0 | 80.0 | 53 % |
| `unemployment` | lo = 2 | 10/10 | 58.0 | 78.0 | 52 % |
| `reserves` | hi = 200000 | 10/10 | 93.5 | 57.5 | 38 % |
| `institutional_confidence` | lo = 0 | 10/10 | 96.0 | 55.0 | 37 % |
| `crime_perception` | hi = 100 | 10/10 | 5.0 | 35.0 | 23 % |
| `gdp` | hi = 400 | 10/10 | 137.0 | 14.0 | 9 % |
| `congress_support` | hi = 100 | 10/10 | 145.0 | 6.0 | 4 % |
| `exchange_rate` | hi = 1e+06 | 1/10 | 150.0 | 1.0 | 1 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_broken:biz_agro:tax_exemption:government` | 10/10 | 6.0 |
| `agreement_broken:biz_agro:tax_exemption:actor` | 10/10 | 10.0 |
| `agreement_honored:gov_rio_negro:restore_transfers` | 10/10 | 33.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 10/10 | 36.5 |
| `agreement_honored:biz_agro:tax_exemption` | 10/10 | 39.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 10/10 | 44.0 |
| `election:fpv_pj` | 10/10 | 48.0 |
| `election:fpv_fdt_pj` | 10/10 | 144.0 |
| `term_end:survived` | 10/10 | 150.0 |
| `agreement_broken:gov_buenos_aires:restore_transfers:government` | 9/10 | 15.0 |

### `2015-12` — arranque 2015-12, 48 meses pedidos

**Qué pasó de verdad:** Cambio de gobierno con salida del cepo. Mandato completo de 48 meses y derrota del oficialismo en la eleccion de 2019.

Semillas usables: **10**. Outcomes: `defeated` 9, `collapse` 1.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **48** | 45 | 48 | 48 | 9/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `government_approval` | lo = 0 | 10/10 | 11.0 | 35.0 | 74 % |
| `social_tension` | hi = 100 | 10/10 | 17.0 | 32.0 | 67 % |
| `consumer_confidence` | lo = 0 | 10/10 | 20.5 | 23.5 | 49 % |
| `institutional_confidence` | lo = 0 | 10/10 | 29.5 | 19.5 | 41 % |
| `reserves` | lo = 0 | 10/10 | 35.0 | 12.0 | 25 % |
| `protest_level` | hi = 100 | 10/10 | 21.0 | 7.5 | 16 % |
| `inequality` | hi = 75 | 9/10 | 46.0 | 3.0 | 6 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_broken:gov_cordoba:restore_transfers:government` | 10/10 | 4.0 |
| `agreement_broken:gov_rio_negro:restore_transfers:government` | 10/10 | 16.0 |
| `forced_devaluation` | 10/10 | 34.0 |
| `agreement_broken:gov_buenos_aires:restore_transfers:government` | 9/10 | 15.0 |
| `agreement_broken:gov_buenos_aires:restore_transfers:actor` | 9/10 | 18.0 |
| `agreement_honored:biz_agro:tax_exemption` | 9/10 | 42.0 |
| `election:fpv_fdt_pj` | 9/10 | 48.0 |
| `term_end:defeated` | 9/10 | 48.0 |
| `agreement_broken:gov_cordoba:restore_transfers:actor` | 8/10 | 8.0 |
| `agreement_broken:biz_agro:tax_exemption:government` | 8/10 | 20.5 |

### `2019-12` — arranque 2019-12, 48 meses pedidos

**Qué pasó de verdad:** Cambio de gobierno, pandemia en 2020 y sequia en 2023. Mandato completo de 48 meses, inflacion ~211 % interanual al cierre y derrota del oficialismo en 2023.

Semillas usables: **10**. Outcomes: `defeated` 10.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **48** | 48 | 48 | 48 | 10/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `government_approval` | lo = 0 | 10/10 | 12.5 | 34.5 | 72 % |
| `social_tension` | hi = 100 | 10/10 | 17.0 | 32.0 | 67 % |
| `consumer_confidence` | lo = 0 | 10/10 | 17.5 | 30.5 | 64 % |
| `institutional_confidence` | lo = 0 | 10/10 | 24.5 | 24.5 | 51 % |
| `reserves` | lo = 0 | 10/10 | 35.0 | 12.0 | 25 % |
| `protest_level` | hi = 100 | 10/10 | 21.0 | 8.0 | 17 % |
| `inequality` | hi = 75 | 10/10 | 46.0 | 3.0 | 6 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_honored:biz_agro:tax_exemption` | 10/10 | 3.0 |
| `agreement_honored:gov_caba:restore_transfers` | 10/10 | 21.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 10/10 | 21.0 |
| `agreement_broken:gov_buenos_aires:restore_transfers:actor` | 10/10 | 25.5 |
| `agreement_honored:gov_rio_negro:restore_transfers` | 10/10 | 25.5 |
| `forced_devaluation` | 10/10 | 34.0 |
| `election:fpv_fdt_pj` | 10/10 | 48.0 |
| `term_end:defeated` | 10/10 | 48.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 9/10 | 3.0 |
| `agreement_broken:biz_agro:tax_exemption:government` | 9/10 | 9.0 |

---

## Qué no se puede concluir de esto

- **No puntúa aciertos.** No hay `hit`, no hay error, no hay tasa. La columna «qué pasó de verdad» es texto para un humano; el comando no la compara programáticamente con nada.
- **No tiene hipótesis previa.** No hay `registration.json`. No reemplaza a `republica validate` (ADR 011 §8), cuyo valor está en el registro previo de la hipótesis.
- **No mide predictibilidad ni generaliza.** Unos pocos arranques elegidos a mano no son una muestra: no hay ventanas rodantes ni intervalos de confianza. Para eso está `republica backtest` (ADR 014); la sonda no lo reemplaza ni lo resume.
- **No compara calibraciones ni brazos.** Corre un solo brazo, sin control Aurora.
- **No prueba causalidad.** Que una variable sature en el mes 5 y el país termine en el 25 es una pista sobre el mecanismo, no una explicación.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.
