# Sonda exploratoria (ADR 020)

País: **argentina** · calibración: **a7_by_regime** · semillas: **10** (desde 1) · transiciones de régimen: **sí** · 10.9 s

Escenarios: `data/countries/argentina/probe_scenarios.csv` (6 filas).

Esto **no es un backtest ni una validación**. El backtest (ADR 014) puntúa objetivos contra series reales en ventanas rodantes; la validación (ADR 011 §8) puntúa hipótesis registradas antes de correr. La sonda **no puntúa nada**: corre unos pocos arranques históricos con muchas semillas y describe el comportamiento del modelo, buscando síntomas de que algo esté mal mecánicamente.

---

## Resumen

| escenario | arranque | pedidos | fin (mediana) | mín–máx | outcomes | variables saturadas | fuera de rango |
|---|---|---:|---:|---|---|---:|---:|
| `1983-12` | 1983-12 | 72 | **8** | 6–18 | `hyperinflation` 9, `collapse` 1 | 10 | 0 |
| `1991-04` | 1991-04 | 120 | **44** | 30–120 | `collapse` 9, `survived` 1 | 7 | 0 |
| `1998-01` | 1998-01 | 60 | **41** | 38–48 | `collapse` 10 | 8 | 0 |
| `2003-06` | 2003-06 | 150 | **120** | 111–140 | `collapse` 10 | 11 | 0 |
| `2015-12` | 2015-12 | 48 | **48** | 48–48 | `defeated` 10 | 8 | 0 |
| `2019-12` | 2019-12 | 48 | **48** | 48–48 | `defeated` 9, `hyperinflation` 1 | 7 | 0 |

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

Semillas usables: **10**. Outcomes: `hyperinflation` 9, `collapse` 1.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **8** | 6 | 18 | 72 | 0/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `institutional_confidence` | lo = 0 | 10/10 | 3.0 | 5.5 | 72 % |
| `protest_level` | hi = 100 | 6/10 | 6.5 | 7.5 | 58 % |
| `crime_perception` | hi = 100 | 5/10 | 7.0 | 8.0 | 57 % |
| `consumer_confidence` | lo = 0 | 10/10 | 2.0 | 4.0 | 50 % |
| `government_approval` | lo = 0 | 10/10 | 6.0 | 2.5 | 31 % |
| `social_tension` | hi = 100 | 10/10 | 6.0 | 2.5 | 31 % |
| `poverty` | hi = 95 | 2/10 | 14.5 | 3.5 | 20 % |
| `real_wage` | lo = 30 | 1/10 | 17.0 | 2.0 | 11 % |
| `interest_rate` | hi = 300 | 2/10 | 13.0 | 1.0 | 8 % |
| `reserves` | lo = 0 | 1/10 | 14.0 | 1.0 | 7 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `fx_regime_exit` | 10/10 | 4.0 |
| `fx_vector_switch:float` | 10/10 | 5.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 9/10 | 2.0 |
| `hyperinflation` | 9/10 | 6.0 |
| `forced_devaluation` | 8/10 | 3.0 |
| `agreement_honored:biz_agro:tax_exemption` | 8/10 | 4.0 |
| `agreement_honored:gov_caba:restore_transfers` | 5/10 | 5.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 3/10 | 5.0 |
| `agreement_honored:gov_mendoza:restore_transfers` | 1/10 | 3.0 |
| `agreement_broken:biz_agro:tax_exemption:actor` | 1/10 | 4.0 |

### `1991-04` — arranque 1991-04, 120 meses pedidos

**Qué pasó de verdad:** Arranque de la convertibilidad. Una decada de tipo de cambio fijo e inflacion de un digito anual; el regimen aguanto los 120 meses completos.

Semillas usables: **10**. Outcomes: `collapse` 9, `survived` 1.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **44** | 30 | 120 | 120 | 1/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `crime_perception` | hi = 100 | 10/10 | 9.0 | 35.5 | 83 % |
| `social_tension` | hi = 100 | 10/10 | 11.0 | 33.5 | 78 % |
| `government_approval` | lo = 0 | 10/10 | 18.5 | 27.5 | 62 % |
| `real_wage` | lo = 30 | 1/10 | 79.0 | 42.0 | 35 % |
| `institutional_confidence` | lo = 0 | 3/10 | 28.0 | 9.0 | 25 % |
| `poverty` | hi = 95 | 1/10 | 98.0 | 23.0 | 19 % |
| `protest_level` | hi = 100 | 10/10 | 11.5 | 6.0 | 13 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_honored:gov_buenos_aires:restore_transfers` | 10/10 | 2.0 |
| `fx_regime_exit` | 10/10 | 5.0 |
| `fx_vector_switch:float` | 10/10 | 6.0 |
| `agreement_honored:gov_caba:restore_transfers` | 9/10 | 4.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 9/10 | 5.0 |
| `agreement_honored:biz_agro:tax_exemption` | 9/10 | 10.0 |
| `collapse` | 9/10 | 42.0 |
| `agreement_broken:biz_agro:tax_exemption:actor` | 7/10 | 3.0 |
| `agreement_honored:gov_rio_negro:restore_transfers` | 7/10 | 18.0 |
| `banking_crisis` | 6/10 | 5.0 |

### `1998-01` — arranque 1998-01, 60 meses pedidos

**Qué pasó de verdad:** Ultimo ano de crecimiento antes de la recesion 1999-2001. Default y salida del peg en 2001-12, el mes 47 de esta ventana.

Semillas usables: **10**. Outcomes: `collapse` 10.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **41** | 38 | 48 | 60 | 0/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `crime_perception` | hi = 100 | 10/10 | 10.0 | 31.5 | 78 % |
| `social_tension` | hi = 100 | 10/10 | 12.5 | 28.5 | 71 % |
| `interest_rate` | lo = 0 | 4/10 | 5.5 | 15.0 | 36 % |
| `government_approval` | lo = 0 | 10/10 | 28.5 | 13.0 | 33 % |
| `reserves` | lo = 0 | 10/10 | 22.0 | 10.0 | 24 % |
| `protest_level` | hi = 100 | 10/10 | 18.0 | 8.0 | 20 % |
| `institutional_confidence` | lo = 0 | 9/10 | 35.0 | 7.0 | 18 % |
| `inflation` | lo = -1 | 3/10 | 4.0 | 2.0 | 5 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `fx_regime_exit` | 10/10 | 6.0 |
| `fx_vector_switch:float` | 10/10 | 7.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 10/10 | 8.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 10/10 | 13.0 |
| `forced_devaluation` | 10/10 | 20.5 |
| `collapse` | 10/10 | 41.0 |
| `agreement_honored:biz_agro:tax_exemption` | 9/10 | 3.0 |
| `agreement_honored:gov_caba:restore_transfers` | 9/10 | 24.0 |
| `banking_crisis` | 6/10 | 6.0 |
| `agreement_honored:gov_rio_negro:restore_transfers` | 6/10 | 27.5 |

### `2003-06` — arranque 2003-06, 150 meses pedidos

**Qué pasó de verdad:** Salida de la crisis. La decada de mayor crecimiento reciente; sin colapso ni hiperinflacion en toda la ventana.

Semillas usables: **10**. Outcomes: `collapse` 10.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **120** | 111 | 140 | 150 | 0/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `crime_perception` | hi = 100 | 10/10 | 4.0 | 117.5 | 98 % |
| `social_tension` | hi = 100 | 10/10 | 4.0 | 52.5 | 43 % |
| `inequality` | lo = 20 | 10/10 | 62.0 | 37.0 | 30 % |
| `interest_rate` | lo = 0 | 10/10 | 59.5 | 34.5 | 28 % |
| `government_approval` | lo = 0 | 10/10 | 37.0 | 28.5 | 23 % |
| `reserves` | lo = 0 | 10/10 | 91.5 | 24.0 | 19 % |
| `inflation` | lo = -1 | 10/10 | 69.0 | 20.0 | 16 % |
| `protest_level` | hi = 100 | 10/10 | 9.0 | 14.0 | 12 % |
| `institutional_confidence` | lo = 0 | 10/10 | 109.0 | 12.0 | 10 % |
| `real_wage` | lo = 30 | 9/10 | 121.0 | 3.0 | 3 % |
| `consumer_confidence` | lo = 0 | 6/10 | 114.5 | 2.0 | 2 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_broken:gov_cordoba:restore_transfers:government` | 10/10 | 7.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 10/10 | 23.5 |
| `agreement_broken:gov_rio_negro:restore_transfers:government` | 10/10 | 29.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 10/10 | 43.5 |
| `agreement_honored:gov_rio_negro:restore_transfers` | 10/10 | 44.0 |
| `election:pj_disidente` | 10/10 | 48.0 |
| `forced_devaluation` | 10/10 | 90.5 |
| `collapse` | 10/10 | 120.5 |
| `agreement_broken:gov_buenos_aires:restore_transfers:government` | 9/10 | 22.0 |
| `agreement_broken:biz_agro:tax_exemption:government` | 9/10 | 24.0 |

### `2015-12` — arranque 2015-12, 48 meses pedidos

**Qué pasó de verdad:** Cambio de gobierno con salida del cepo. Mandato completo de 48 meses y derrota del oficialismo en la eleccion de 2019.

Semillas usables: **10**. Outcomes: `defeated` 10.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **48** | 48 | 48 | 48 | 10/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `poverty` | lo = 0 | 10/10 | 25.5 | 23.5 | 49 % |
| `real_wage` | hi = 200 | 10/10 | 31.0 | 16.0 | 33 % |
| `inequality` | lo = 20 | 10/10 | 39.5 | 9.5 | 20 % |
| `reserves` | lo = 0 | 8/10 | 40.5 | 7.5 | 16 % |
| `institutional_confidence` | lo = 0 | 10/10 | 42.0 | 7.0 | 15 % |
| `crime_perception` | lo = 0 | 4/10 | 41.0 | 5.0 | 10 % |
| `government_approval` | lo = 0 | 6/10 | 44.5 | 3.5 | 7 % |
| `consumer_confidence` | hi = 100 | 1/10 | 44.0 | 1.0 | 2 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `election:fpv_fdt_pj` | 10/10 | 48.0 |
| `term_end:defeated` | 10/10 | 48.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 9/10 | 43.0 |
| `forced_devaluation` | 8/10 | 39.5 |
| `agreement_broken:gov_cordoba:restore_transfers:government` | 7/10 | 4.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 7/10 | 39.0 |
| `agreement_honored:gov_mendoza:restore_transfers` | 7/10 | 45.0 |
| `agreement_broken:gov_cordoba:restore_transfers:actor` | 6/10 | 8.0 |
| `agreement_broken:biz_agro:tax_exemption:government` | 6/10 | 10.0 |
| `agreement_broken:biz_agro:tax_exemption:actor` | 6/10 | 15.0 |

### `2019-12` — arranque 2019-12, 48 meses pedidos

**Qué pasó de verdad:** Cambio de gobierno, pandemia en 2020 y sequia en 2023. Mandato completo de 48 meses, inflacion ~211 % interanual al cierre y derrota del oficialismo en 2023.

Semillas usables: **10**. Outcomes: `defeated` 9, `hyperinflation` 1.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **48** | 48 | 48 | 48 | 10/10 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `poverty` | lo = 0 | 10/10 | 22.5 | 26.5 | 55 % |
| `real_wage` | hi = 200 | 10/10 | 26.0 | 22.0 | 46 % |
| `institutional_confidence` | lo = 0 | 10/10 | 36.0 | 13.0 | 27 % |
| `inequality` | lo = 20 | 10/10 | 37.0 | 12.0 | 25 % |
| `reserves` | lo = 0 | 10/10 | 39.0 | 9.0 | 19 % |
| `government_approval` | lo = 0 | 10/10 | 39.5 | 8.5 | 18 % |
| `crime_perception` | lo = 0 | 1/10 | 38.0 | 1.0 | 2 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `agreement_honored:gov_buenos_aires:restore_transfers` | 10/10 | 5.5 |
| `forced_devaluation` | 10/10 | 38.0 |
| `election:fpv_fdt_pj` | 10/10 | 48.0 |
| `agreement_honored:biz_agro:tax_exemption` | 9/10 | 3.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 9/10 | 3.0 |
| `agreement_broken:biz_agro:tax_exemption:government` | 9/10 | 10.0 |
| `term_end:defeated` | 9/10 | 48.0 |
| `agreement_honored:gov_caba:restore_transfers` | 8/10 | 3.0 |
| `agreement_broken:gov_buenos_aires:restore_transfers:government` | 8/10 | 10.5 |
| `agreement_broken:gov_buenos_aires:restore_transfers:actor` | 8/10 | 21.5 |

---

## Qué no se puede concluir de esto

- **No puntúa aciertos.** No hay `hit`, no hay error, no hay tasa. La columna «qué pasó de verdad» es texto para un humano; el comando no la compara programáticamente con nada.
- **No tiene hipótesis previa.** No hay `registration.json`. No reemplaza a `republica validate` (ADR 011 §8), cuyo valor está en el registro previo de la hipótesis.
- **No mide predictibilidad ni generaliza.** Unos pocos arranques elegidos a mano no son una muestra: no hay ventanas rodantes ni intervalos de confianza. Para eso está `republica backtest` (ADR 014); la sonda no lo reemplaza ni lo resume.
- **No compara calibraciones ni brazos.** Corre un solo brazo, sin control Aurora.
- **No prueba causalidad.** Que una variable sature en el mes 5 y el país termine en el 25 es una pista sobre el mecanismo, no una explicación.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.
