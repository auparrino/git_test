# Log de calibración — Fase 1 (v0.1)

Registro de todo ajuste hecho a `data/country.json` para cumplir el test de
aceptación 7 (distribución de outcomes: `survived` entre 50 % y 95 % en 1000
semillas con `ConstantPolicy`) y la cota de sensatez de la inflación anualizada
mediana al mes 48 (entre 5 % y 400 %). Ningún cambio tocó las fórmulas de
`world/economy.py`, `world/society.py` ni `world/politics.py`: solo valores en
`data/country.json → coefficients`.

## Diagnóstico inicial

Con los coeficientes tal cual salen de la sección 4/5 del spec, `republica
batch --seeds 300` daba:

```
survived: 16/300 (5.3 %)
hyperinflation: 284/300 (94.7 %)
mediana inflación anualizada final: ~3700 %
```

Incluso **sin shocks y sin ruido exógeno** (`shocks_enabled=False,
exogenous_noise=False`), la corrida determinista con `ConstantPolicy` diverge
a hiperinflación alrededor del mes 30-35. La causa es estructural, no un bug:
con `interest_rate` fijo en 30 (política "no hacer nada") y
`r_real = interest_rate − 12·inflation`, apenas la inflación mensual supera
`(30 − r_neutral) / 12 ≈ 2.17`, la tasa real se vuelve negativa y sigue
cayendo a medida que sube la inflación (porque la tasa nominal no reacciona).
Eso alimenta dos lazos de realimentación positiva simultáneos:

1. `r_gap` más negativo → `de_raw` sube (sección 4.2, término `−b_r·r_gap/100`)
   → `exchange_rate` se deprecia → `inflation' += c_e·de` (pass-through).
2. El mismo `r_gap` más negativo entra directo en 4.3 como `−c_r·r_gap/100`,
   que se vuelve positivo y empuja la inflación aún más.

Con la inflación inicial (2.0) ya muy cerca del punto de quiebre (2.17), el
sistema es un punto fijo casi neutro que en la práctica es repulsor: cualquier
mes con inflación por encima de 2.17 entra en la espiral. El test de estado
estacionario (sección 11, test 3) solo mira el mes 1 con tolerancia ±0.15, así
que hay margen para bajar la ganancia del lazo sin romperlo.

## Cambio aplicado

**`c_e` (pass-through cambiario, sección 4.3): `0.10 → 0.06`.**

Es exactamente uno de los "supuestos discutibles" que el spec (sección 12)
marca como candidato a calibrar ("Pass-through cambiario 0.10 por pp. Alto
para una economía cerrada, razonable para una bimonetaria."). Bajarlo reduce
la ganancia del lazo 1 de arriba sin tocar el lazo 2 (que depende de `c_r`,
no marcado como knob de calibración en la sección 12) ni ninguna fórmula.

No se tocó `c_f` (monetización del déficit) ni ningún otro coeficiente: un
solo cambio bastó para entrar en el rango pedido.

### Resultado (300 semillas, `ConstantPolicy`, seed 0..299)

```
survived: 239/300 (79.7 %)
hyperinflation: 61/300 (20.3 %)
mediana inflación anualizada final (mes 48): 31.1 %
p10 / p50 / p90 inflación anualizada: 16.9 % / 31.1 % / 1620.7 %
```

- `survived` = 79.7 % ∈ [50 %, 95 %]. ✓
- Mediana de inflación anualizada 31.1 % ∈ [5 %, 400 %] (y cerca del ~27 %
  anual que corresponde al régimen inicial de 2.0 %/mes, así que el "mundo
  tranquilo" sigue leyendo como una inflación alta pero no absurda). ✓
- Con `ConstantPolicy` ("no hacer nada") 1 de cada 5 gobiernos igual termina
  en hiperinflación en 48 meses: el mensaje del juego (la política monetaria
  pasiva es riesgosa) se mantiene.

### Verificación de que no rompió el resto de los tests de aceptación

Re-corridos con `c_e = 0.06` antes de fijar el valor:

- Test 3 (estado estacionario, semilla 1, sin shocks/ruido): `inflation'
  = 1.902` → `|1.902 − 2.0| = 0.098 < 0.15`. ✓ (con `c_e = 0.10` daba 1.981;
  el cambio no rompe la tolerancia).
- Test 4 (sequía, semilla 7, `drought@5`): reservas menores en meses 6-9 y
  aprobación menor en al menos uno de esos meses. ✓ (sin cambios, no depende
  de `c_e` de forma crítica).
- Test 5 (suba de tasa +15pp mes 1, semilla 42, sin shocks): inflación mes 12
  menor y desempleo mes 12 mayor que la corrida constante. ✓
- Test 6 (déficit, `primary_spending=32`, semilla 11, sin shocks): la corrida
  con déficit alto ahora entra en hiperinflación antes del mes 24 (mes 15),
  lo cual es una confirmación *más fuerte* que la pedida por el spec (una
  diferencia de ≥15pp de inflación anualizada al mes 24) — ver nota de
  desviación en el reporte final sobre cómo se adaptó el test para este caso.

## Knobs considerados y descartados

Antes de fijar `c_e = 0.06` se barrieron combinaciones de `c_e` y `c_f`
(script exploratorio, no versionado) sobre 120-300 semillas:

| c_e | c_f | survived | mediana infl. anualizada |
|---|---|---|---|
| 0.10 | 0.12 (default) | 5.3 % | ~3700 % |
| 0.06 | 0.09 | 98.0 % | −11.0 % (deflación: descartado, < 5 %) |
| 0.06 | 0.10 | 94.5 % | 8.2 % |
| 0.06 | 0.11 | 89.5 % | 20.7 % |
| **0.06** | **0.12 (sin tocar)** | **82.0 % (n=200) / 79.7 % (n=300)** | **31.3 % / 31.1 %** |
| 0.07 | 0.12 | 67.5 % | 43.1 % |
| 0.08 | 0.12 | 47.5 % | 1973.6 % (fuera de rango: descartado) |

Se eligió `c_e = 0.06` con `c_f` en su valor default (`0.12`, el de la
sección 4.3 del spec) por ser el cambio de un solo coeficiente que cae más
cómodo dentro de ambos rangos pedidos, sin necesidad de tocar dos knobs a la
vez.


## Segunda ronda (revisión de diseño, orquestador)

Al leer la trayectoria determinista de `ConstantPolicy` (sin shocks ni ruido) aparecieron dos
incoherencias de diseño de la spec, no de la implementación:

1. **El salario real caía 10 % en 48 meses con la inflación bajando.** Causa: `w_idx = 0.8` hace que
   los salarios pierdan el 20 % de la inflación *todos* los meses, sin importar si acelera o no.
   Cambio: `w_idx 0.8 → 1.0` (indexación completa con rezago). Ahora el salario real solo se erosiona
   con aceleración inflacionaria.
2. **Con la tasa nominal fija en 30 % y la inflación cayendo a 1 % mensual, la tasa real subía a 18 %**,
   hundía el crecimiento (desempleo 10.7 %) e inflaba las reservas por carry a USD 27.000–41.000 M.
   Cambios: `k_k 40 → 15`, `k_conf 15 → 10` (reservas ahora drenan ~20 M/mes en estado inicial), y
   saturación del efecto de la tasa real sobre la actividad: `clamp(r_gap, −10, +30)` (nuevos
   coeficientes `r_gap_min`, `r_gap_max`). La saturación inferior evita que tasas reales de −100 %
   en corridas hiperinflacionarias "estimulen" la economía hasta un desempleo del 2 %.
3. **Nuevo baseline `PassivePolicy`** (tasa = `r_neutral + 2 + 12·inflation_lag1`): "no hacer nada"
   en términos reales. Es el default de `run` y `batch`. `ConstantPolicy` sigue existiendo como lo
   que hace un jugador que no toca la tasa.

Resultado (300 semillas):

| Política | survived | hyperinflation | collapse | inflación anual final p50 | desempleo final p50 |
|---|---|---|---|---|---|
| passive | 91.7 % | 0 | 8.3 % | 32 % | 8.5 % |
| constant | 83.7 % | 14.0 % | 2.3 % | 35 % | 9.1 % |
| taylor | 100 % | 0 | 0 | — | 11.5 % |

Trayectoria determinista con `passive` (sin shocks): inflación 2.0 → 1.6 mensual, crecimiento 2.3 %,
desempleo 8.0, salario real 104, aprobación 50 → 56. Aburrido y estable, como pide la DoD.

Queda documentada una **trampa de inflación crónica**: en ~19 % de las corridas `passive`, una
secuencia de shocks agota las reservas, hunde la confianza institucional y deja la inflación en
5–14 % mensual con aprobación en 0 sin llegar al umbral de hiperinflación. Es un estado coherente
(el BC pasivo no desinfla) y es el que el jugador tiene que evitar o revertir con Taylor y ajuste.
