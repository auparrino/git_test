# Sonda exploratoria (ADR 020)

País: **argentina** · calibración: **a9_clean** · semillas: **40** (desde 1) · transiciones de régimen: **sí** · 4.5 s

Escenarios: `data/countries/argentina/probe_scenarios_2027.csv` (1 filas).

Esto **no es un backtest ni una validación**. El backtest (ADR 014) puntúa objetivos contra series reales en ventanas rodantes; la validación (ADR 011 §8) puntúa hipótesis registradas antes de correr. La sonda **no puntúa nada**: corre unos pocos arranques históricos con muchas semillas y describe el comportamiento del modelo, buscando síntomas de que algo esté mal mecánicamente.

---

## Resumen

| escenario | arranque | pedidos | fin (mediana) | mín–máx | outcomes | variables saturadas | fuera de rango |
|---|---|---:|---:|---|---|---:|---:|
| `2023-12` | 2023-12 | 48 | **32** | 27–36 | `collapse` 40 | 8 | 0 |

## Escenarios y lo que pasó de verdad

| escenario | arranque | meses | qué pasó de verdad |
|---|---|---:|---|
| `2023-12` | 2023-12 | 48 | Mandato en curso; la eleccion presidencial real es octubre de 2027. NO hay epoca de partidos para 2023+: el modelo solo distingue si el oficialismo retiene o pierde, no que partido gana. |

La comparación con esa columna la hace un humano: la sonda la imprime al lado del resultado y **no la puntúa** (ADR 020 §2.1).

---

## Detalle por escenario

### `2023-12` — arranque 2023-12, 48 meses pedidos

**Qué pasó de verdad:** Mandato en curso; la eleccion presidencial real es octubre de 2027. NO hay epoca de partidos para 2023+: el modelo solo distingue si el oficialismo retiene o pierde, no que partido gana.

Semillas usables: **40**. Outcomes: `collapse` 40.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **32** | 27 | 36 | 48 | 0/40 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `consumer_confidence` | lo = 0 | 40/40 | 1.0 | 32.0 | 100 % |
| `interest_rate` | hi = 300 | 40/40 | 2.0 | 31.0 | 97 % |
| `government_approval` | lo = 0 | 40/40 | 3.0 | 30.0 | 94 % |
| `institutional_confidence` | lo = 0 | 40/40 | 3.0 | 30.0 | 94 % |
| `social_tension` | hi = 100 | 40/40 | 6.0 | 27.0 | 85 % |
| `protest_level` | hi = 100 | 40/40 | 7.0 | 25.0 | 80 % |
| `reserves` | lo = 0 | 40/40 | 6.0 | 23.0 | 71 % |
| `inequality` | hi = 75 | 40/40 | 19.0 | 14.0 | 43 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `forced_devaluation` | 40/40 | 5.0 |
| `collapse` | 40/40 | 32.0 |
| `agreement_broken:gov_buenos_aires:restore_transfers:government` | 38/40 | 4.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 13/40 | 2.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 12/40 | 2.0 |
| `agreement_broken:gov_buenos_aires:restore_transfers:actor` | 7/40 | 9.0 |
| `agreement_honored:gov_caba:restore_transfers` | 6/40 | 2.0 |
| `agreement_broken:gov_caba:restore_transfers:government` | 6/40 | 5.5 |
| `agreement_broken:biz_agro:tax_exemption:government` | 6/40 | 8.0 |
| `agreement_broken:gov_mendoza:restore_transfers:government` | 2/40 | 8.0 |

---

## Qué no se puede concluir de esto

- **No puntúa aciertos.** No hay `hit`, no hay error, no hay tasa. La columna «qué pasó de verdad» es texto para un humano; el comando no la compara programáticamente con nada.
- **No tiene hipótesis previa.** No hay `registration.json`. No reemplaza a `republica validate` (ADR 011 §8), cuyo valor está en el registro previo de la hipótesis.
- **No mide predictibilidad ni generaliza.** Unos pocos arranques elegidos a mano no son una muestra: no hay ventanas rodantes ni intervalos de confianza. Para eso está `republica backtest` (ADR 014); la sonda no lo reemplaza ni lo resume.
- **No compara calibraciones ni brazos.** Corre un solo brazo, sin control Aurora.
- **No prueba causalidad.** Que una variable sature en el mes 5 y el país termine en el 25 es una pista sobre el mecanismo, no una explicación.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.
