# Sonda exploratoria (ADR 020)

País: **argentina** · calibración: **a9_clean** · semillas: **40** (desde 1) · transiciones de régimen: **sí** · 1.5 s

Escenarios: `data/countries/argentina/probe_scenarios_2027.csv` (1 filas).

Esto **no es un backtest ni una validación**. El backtest (ADR 014) puntúa objetivos contra series reales en ventanas rodantes; la validación (ADR 011 §8) puntúa hipótesis registradas antes de correr. La sonda **no puntúa nada**: corre unos pocos arranques históricos con muchas semillas y describe el comportamiento del modelo, buscando síntomas de que algo esté mal mecánicamente.

---

## Resumen

| escenario | arranque | pedidos | fin (mediana) | mín–máx | outcomes | variables saturadas | fuera de rango |
|---|---|---:|---:|---|---|---:|---:|
| `2023-12` | 2023-12 | 48 | **3** | 3–3 | `hyperinflation` 40 | 4 | 0 |

## Escenarios y lo que pasó de verdad

| escenario | arranque | meses | qué pasó de verdad |
|---|---|---:|---|
| `2023-12` | 2023-12 | 48 | Mandato en curso; la eleccion presidencial real es octubre de 2027. NO hay epoca de partidos para 2023+: el modelo solo distingue si el oficialismo retiene o pierde, no que partido gana. |

La comparación con esa columna la hace un humano: la sonda la imprime al lado del resultado y **no la puntúa** (ADR 020 §2.1).

---

## Detalle por escenario

### `2023-12` — arranque 2023-12, 48 meses pedidos

**Qué pasó de verdad:** Mandato en curso; la eleccion presidencial real es octubre de 2027. NO hay epoca de partidos para 2023+: el modelo solo distingue si el oficialismo retiene o pierde, no que partido gana.

Semillas usables: **40**. Outcomes: `hyperinflation` 40.

| mes de fin (mediana) | mín | máx | meses pedidos | semillas que llegan enteras |
|---:|---:|---:|---:|---:|
| **3** | 3 | 3 | 48 | 0/40 |

**Saturación contra la cota** (ADR 020 §2.2):

| variable | cota | semillas | 1er mes (mediana) | meses pegada (mediana) | % de la corrida |
|---|---|---:|---:|---:|---:|
| `consumer_confidence` | lo = 0 | 40/40 | 1.0 | 3.0 | 100 % |
| `interest_rate` | hi = 300 | 40/40 | 2.0 | 2.0 | 67 % |
| `government_approval` | lo = 0 | 38/40 | 3.0 | 1.0 | 33 % |
| `institutional_confidence` | lo = 0 | 34/40 | 3.0 | 1.0 | 33 % |

**Valores fuera de rango físico** (ADR 020 §2.3 — una violación es un bug):

Ninguno.

**Eventos más frecuentes:**

| evento | semillas | 1ra aparición (mes mediano) |
|---|---:|---:|
| `hyperinflation` | 40/40 | 3.0 |
| `agreement_honored:gov_buenos_aires:restore_transfers` | 13/40 | 2.0 |
| `agreement_honored:gov_cordoba:restore_transfers` | 12/40 | 2.0 |
| `agreement_honored:gov_caba:restore_transfers` | 6/40 | 2.0 |
| `agreement_broken:gov_buenos_aires:restore_transfers:government` | 6/40 | 3.0 |
| `agreement_broken:gov_caba:restore_transfers:government` | 3/40 | 3.0 |
| `agreement_honored:gov_mendoza:restore_transfers` | 1/40 | 2.0 |

---

## Qué no se puede concluir de esto

- **No puntúa aciertos.** No hay `hit`, no hay error, no hay tasa. La columna «qué pasó de verdad» es texto para un humano; el comando no la compara programáticamente con nada.
- **No tiene hipótesis previa.** No hay `registration.json`. No reemplaza a `republica validate` (ADR 011 §8), cuyo valor está en el registro previo de la hipótesis.
- **No mide predictibilidad ni generaliza.** Unos pocos arranques elegidos a mano no son una muestra: no hay ventanas rodantes ni intervalos de confianza. Para eso está `republica backtest` (ADR 014); la sonda no lo reemplaza ni lo resume.
- **No compara calibraciones ni brazos.** Corre un solo brazo, sin control Aurora.
- **No prueba causalidad.** Que una variable sature en el mes 5 y el país termine en el 25 es una pista sobre el mecanismo, no una explicación.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado.
