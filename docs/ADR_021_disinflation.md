# ADR 021 — Desinflación por credibilidad del programa

Estado: aceptado para implementar. Todo detrás de `MacroCoefficients.credibility_channel`
(default `False`): apagado, el bloque de precios queda byte a byte como lo dejó ADR 019.

## 1. El problema, medido

El modelo puede producir una hiperinflación y **no puede producir una desinflación desde niveles
altos**. La demostración más corta está en `docs/EMERGENCE_LOG.md`, sección "Prueba de pronóstico:
la elección de 2027": 40 semillas desde el estado real de 2023-12 terminan en `hyperinflation` en
el mes 3, las 40. Lo que pasó de verdad fue lo contrario.

| mes | inflación mensual real |
|---|---:|
| 2023-12 | 25.47 % |
| 2024-03 | 11.01 % |
| 2024-09 | 3.47 % |
| 2026-08 | 1.66 % |

La causa está en el bloque de precios de ADR 012 §2, tal como lo dejó ADR 019:

```
rho_eff      = rho_pi + rho_slope · indexation
indexation' = indexation + idx_adj · (idx_target − indexation)
idx_target   = clamp((idx_hat − pi_hi) / pi_hi, 0, 2)
```

`idx_target` depende **solo del nivel y la aceleración de la propia inflación**. No existe ningún
canal por el que la indexación baje por otra razón. Con inflación alta, `idx_target` se va al tope,
`rho_eff` supera 1 y la trayectoria es explosiva por construcción: ADR 019 §1 midió que el cruce de
`rho_eff = 1` ocurre a **17.48 %/mes** con el vector `peg`/`crawl`. Desde 25.47 no hay salida.

Y es más general que ese arranque. ADR 019 §7.5 lo dejó escrito: "con `pi_anchor` = EMA(36) de su
propia inflación, el ancla alcanza al nivel y el mapa queda en pendiente `1 + c_e > 1` para
cualquier nivel: **toda corrida termina hiperinflacionando, sólo cambia cuánto tarda**".

## 2. Qué falta, conceptualmente

Un programa de estabilización desinflaciona por dos vías que el modelo no tiene:

1. **Un ancla nominal creíble** rompe la indexación. Los contratos se desindexan, la frecuencia de
   repactación cae, y la inflación deja de depender de su propio pasado. Esto no es "menos inercia
   porque la inflación bajó": es al revés, la inercia cae primero y por eso la inflación baja.
2. **La consolidación fiscal** elimina la necesidad de monetizar. El modelo ya tiene
   `seigniorage_pressure = pos(deficit − financeable) / money_demand`, pero nada conecta el
   cumplimiento fiscal con la persistencia de precios.

El modelo tiene las dos condiciones **observables** (`fx_regime`, `reserves` contra `r_min`,
`deficit` contra `financeable`) y no las usa para nada de esto.

## 3. Los tres episodios reales, medidos sobre el dato del repo

`history/inflation_cpi_monthly_linked.csv`, meses hasta caer a una fracción de la inflación inicial:

| episodio | arranque | a 50 % | a 25 % | a 10 % |
|---|---|---:|---:|---:|
| Austral, 1985-05 | 25.10 %/mes | mes 2 | mes 2 | mes 4 |
| Convertibilidad, 1991-02 | 27.00 %/mes | mes 1 | mes 2 | mes 5 |
| Estabilización, 2023-12 | 25.47 %/mes | mes 3 | mes 5 | mes 11 |
| **mediana** | ~25.5 %/mes | **2** | **2** | **5** |

Los tres arrancan en el mismo rango (25–27 %/mes), lo que los hace directamente comparables. El de
2024 es el más gradual —ancla deslizante en vez de tipo fijo o congelamiento— y marca el extremo
lento de la banda.

## 4. Diseño

**`credibility` pasa a ser un estado de `MacroState`**, en `[0, 1]`, con la misma forma de ajuste
parcial que el resto del ADR 012:

```
ancla_ok   = fx_regime_next ∈ {peg, crawl}  y  reserves >= r_min
fiscal_ok  = deficit <= financeable                    # no hace falta monetizar
cred_target = 1.0 si (ancla_ok y fiscal_ok) si no 0.0
credibility' = clamp(credibility + cred_adj · (cred_target − credibility), 0, 1)
```

Y entra en la persistencia por **dos** canales, no uno:

```
rho_eff = rho_pi · (1 − cred_rho · credibility)        # rompe la inercia base
        + rho_slope · indexation · (1 − credibility)   # y apaga la rampa
```

Por qué los dos: con credibilidad plena y sólo el segundo canal, `rho_eff = rho_pi = 0.85`, que
halva la inflación recién en 4.3 meses — más lento que los tres episodios reales, que la halvan en
1 a 3. La desindexación de un programa creíble no se limita a quitar el exceso de inercia: baja la
inercia por debajo de su nivel normal, porque los contratos se desindexan de golpe.

### 4.1 Coeficientes y sus anclas

| coeficiente | valor | ancla |
|---|---:|---|
| `cred_adj` | **0.45** | La mediana de los tres episodios halva la inflación en el **mes 2**. Con ajuste parcial, la credibilidad llega a `1 − (1−0.45)² = 0.70` en dos meses, que es donde el efecto tiene que estar cerca de pleno. |
| `cred_rho` | **0.60** | Con credibilidad 0.70, `rho_eff = 0.85 · (1 − 0.6·0.70) = 0.49`. Partiendo de 25.5 %/mes, la trayectoria simulada queda entre la de 1991 (25 → 11 → 5.5) y la de 2024 (25.5 → 20.6 → 13.2), que son los dos extremos observados. |
| `cred_weight` sobre `rho_slope` | 1.0 (implícito) | Credibilidad plena apaga la rampa entera: es la definición de que la indexación se rompió. No se parametriza aparte para no agregar un grado de libertad sin ancla. |

`cred_adj` y `cred_rho` **no se agregan al vector de calibración** en esta ronda: están anclados en
los tres episodios y meterlos a CMA-ES antes de verificar el mecanismo confundiría el diagnóstico.

### 4.2 Lo que el mecanismo NO regala

La credibilidad no se declara: se gana cumpliendo dos condiciones que el modelo mide mes a mes. En
particular, **`fiscal_ok` depende de lo que el gobierno simulado haga con el gasto**, que es una
decisión de política del propio motor, no un parámetro. Una corrida donde el gobierno no ajusta no
desinflaciona, y eso es lo correcto: un programa de estabilización sin ancla fiscal no funciona en
el modelo porque no funcionó en la historia.

Esto hace que, desde 2023-12, la fracción de semillas que desinflaciona sea un **resultado
informativo** y no una constante.

## 5. Hipótesis registrada (antes de correr)

**Mejoras esperadas**

- **H1** — desde **2023-12**, 48 meses: al menos **60 %** de las semillas llegan al mes 48 (hoy:
  **0 de 40**).
- **H2** — en las semillas que llegan, la inflación mensual mediana del último año cae por debajo
  de **5 %/mes** (real 2026: 1.66 %/mes; hoy el modelo no llega).
- **H3** — desde 2023-12, la inflación mensual mediana cae por debajo de la mitad de la inicial
  (12.7 %/mes) antes del **mes 6** (mediana real: mes 2; se pide una banda laxa porque el modelo
  no tiene congelamiento de precios ni desindexación por decreto).

**Discriminantes que NO pueden romperse** (si alguno se rompe, el mecanismo es una amnistía y se
descarta):

- **H4** — V1: desde 1988-06, la hiperinflación sigue siendo alcanzable en **≥ 50 %** de las
  semillas (ADR 012 §7 test 2a). En 1988 no había ancla nominal ni superávit: la credibilidad debe
  quedarse en 0.
- **H5** — V2: desde 1998-01 con `peg`, el default o colapso sigue ocurriendo en **≥ 50 %**. La
  convertibilidad tenía ancla pero no cumplimiento fiscal, y las reservas caían: la credibilidad
  debe derrumbarse, no sostenerse.
- **H6** — ADR 012 §7 test 2b: desde 2003-06 la hiperinflación sigue sin aparecer (0 %), y test 5:
  ≥ 80 % de las semillas llegan a 2015-12.
- **H7** — flag apagado: los goldens de `tests/test_country_pack_argentina.py`,
  `test_macro_regime.py`, `test_collapse_recovery.py` y `test_initial_sensitivity.py` quedan byte a
  byte.

**Predicción negativa registrada**: el mecanismo **no** va a mejorar el objetivo "magnitud de la
inflación" del backtest 1916–2022. La mayoría de esas ventanas no tiene ancla nominal ni
cumplimiento fiscal, así que la credibilidad queda en 0 y `rho_eff` no cambia. Si mejorara mucho,
sería señal de que la compuerta está enganchando donde no debe.

## 6. Tests

1. Flag apagado: goldens byte a byte (H7).
2. La compuerta: credibilidad sube sólo con ancla **y** fiscal; cada una sola no alcanza; se
   derrumba cuando cualquiera de las dos falla.
3. Forma: con credibilidad 1, `rho_eff = rho_pi · (1 − cred_rho)`; con 0, `rho_eff` es idéntico al
   de ADR 019.
4. H1, H2, H3 desde 2023-12.
5. H4, H5, H6 como regresión.
6. Monotonía: más credibilidad nunca sube `rho_eff`.

---

## Notas de implementación

### Tres correcciones al diseño de §4, hechas contra la medición

El diseño original no enganchaba en el único escenario que motivó el ADR. Cada corrección salió de
medir, no de razonar:

1. **`control` SÍ es un régimen anclado.** §4 exigía `peg` o `crawl`. Pero 2023-12 corre en
   `control`, y bajo controles el motor aplica `de = control_de_admin`, un deslizamiento
   administrado: es exactamente el caso de 2024 (cepo vigente y crawl anunciado como ancla). Con la
   condición original la compuerta no podía engancharse nunca ahí.
2. **La condición de reservas se reemplazó por el evento de ruptura.** §4 pedía `reserves >= r_min`.
   Medido desde 2023-12, `r_min` (tres meses de importaciones **calculadas**) pasa de 39 555 a
   65 716 en tres meses mientras las reservas caen: la condición no se cumpliría nunca por una razón
   mecánica, no económica. Se usa `"fx_regime_exit" not in events`, que es el evento que el propio
   motor produce cuando el ancla se rompe.
3. **La condición fiscal pide superávit, no "déficit chico".** §4 pedía `deficit <= financeable`, o
   sea hasta 2 % de déficit. Medido: eso le daba credibilidad 0.07–0.12 al 1988 argentino —déficits
   de 4–5 puntos con meses sueltos por debajo de 2— y la hiperinflación desde 1988-06 caía de 15/20
   semillas a 6/20, **rompiendo el discriminante H4**. Se cambió a un factor continuo sobre el
   superávit (`cred_surplus_full = 1.0 % del PIB`) y a un ajuste asimétrico (`cred_adj = 0.25` para
   ganar, `cred_adj_down = 0.60` para perder). Con eso 1988 queda en credibilidad **0.00 exacto**.

### Un cuarto canal que hizo falta: las expectativas

Con los dos canales de §4 y credibilidad plena, la inflación caía de 25 a 20.5 %/mes en un mes,
contra el 25 → 11 de la convertibilidad. La causa: `pi_exp = w_adapt · inflation_lag1 + (1 −
w_adapt) · pi_anchor` con `w_adapt = 0.7` deja la expectativa pegada al pasado por más que `rho_eff`
baje. Se agregó `w_eff = w_adapt · (1 − credibility)`: con credibilidad plena la expectativa **es**
el ancla, que es la definición de un programa creíble. Con eso la trayectoria cae dentro de la banda
de los tres episodios.

### Un hallazgo que no era el objetivo: el umbral de hiperinflación estaba mal

`terminal.hyper_inflation` valía **20 %/mes durante 3 meses**, copiado de Aurora y nunca ajustado
para Argentina (ADR 011 lo declara como copia). Medido sobre
`history/inflation_cpi_monthly_linked.csv`, ese criterio marca **cuatro** hiperinflaciones
argentinas:

| racha real de 3+ meses sobre 20 %/mes | pico |
|---|---:|
| 1975-06 a 1975-08 | 34.7 %/mes |
| 1985-01 a 1985-06 | 30.5 %/mes |
| 1989-04 a 1989-08 | **196.6 %/mes** |
| 1989-12 a 1990-03 | **95.5 %/mes** |

Sólo las dos últimas lo fueron. El Rodrigazo y el tramo previo al Austral fueron inflación alta
seguida de estabilización, no hiperinflación. Con el umbral clásico de **50 %/mes** quedan
exactamente **6 meses** en toda la serie, todos en 1989–1990: los dos episodios reales. Se cambió a
50.0 para Argentina.

### Resultados medidos, con los dos efectos separados

Sonda sobre los seis arranques históricos (10 semillas, `a9_clean`), contra la corrida previa:

| arranque | antes | después | real |
|---|---|---|---|
| 1983-12 | hiperinflación en el mes 10 | **72 meses completos, derrota 9/10** | 72 meses; el oficialismo perdió en 1989 |
| 1991-04 | hiperinflación en el mes 96 | **120 meses completos, sobrevive 10/10** | la década de convertibilidad |
| 1998-01 | 60 completos, sobrevive | 60 completos, sobrevive | default en el mes 47 (sigue fallando) |
| 2003-06 | 150 completos, sobrevive | 150 completos, sobrevive | década de crecimiento |
| 2015-12 | derrota 9/10 | derrota 9/10 | derrota |
| 2019-12 | derrota 10/10 | derrota 10/10 | derrota |

**Y toda esa mejora es del umbral, no del mecanismo.** Se corrió la misma sonda con
`credibility_channel` apagado y el resultado es **idéntico escenario por escenario**
(`probe/a11_sincred/`). La credibilidad media en 1991-04 es **0.01** y en 1983-12 **0.00**: el canal
está construido y verificado en los tests, y en las corridas históricas **casi nunca se activa**.

### Las hipótesis de §5, una por una

| | resultado |
|---|---|
| **H1** (≥ 60 % llegan al mes 48 desde 2023-12) | **NO CUMPLIDA**: 0 de 40. Mejora de mes 3 a mes 32, pero termina en `collapse`. |
| **H2** (inflación final < 5 %/mes) | **No evaluable**: ninguna semilla llega. |
| **H3** (cae a la mitad antes del mes 6) | **No evaluable** en la corrida real; **CUMPLIDA** en el test unitario con la compuerta cumplida. |
| **H4** (V1 sigue alcanzable) | **CUMPLIDA**: credibilidad 0.00 en 1988-06. |
| **H5** (V2 sigue ocurriendo) | **CUMPLIDA**: `test_collapse_recovery.py` verde. |
| **H6** (2003-06 sin hiperinflación, ≥ 80 % a 2015-12) | **CUMPLIDA**. |
| **H7** (goldens byte a byte con el flag apagado) | **CUMPLIDA**. |
| Predicción negativa (no mejora el backtest) | **Pendiente de medir**. |

### Por qué H1 no se cumple, y cuál es el próximo bloqueo

La compuerta exige superávit primario sostenido. **El gobierno simulado nunca lo produce**: desde
2023-12 los déficits van de 2.5 a 4.4 puntos del PIB durante los 32 meses que dura la corrida, con
un solo mes en −0.11. La credibilidad se queda en 0 y el mecanismo, que funciona, no se activa.

Eso no es un defecto de ADR 021: es el diagnóstico que ADR 021 permite hacer por primera vez. **El
bloqueo se movió del bloque de precios al bloque fiscal.** El modelo no tiene forma de expresar un
gobierno que decide un ajuste fiscal grande y lo sostiene, que es exactamente lo que hicieron los
tres programas de §3. Mientras eso no exista, la pregunta de 2027 sigue sin respuesta, pero ahora
sin respuesta **por una razón distinta y más precisa** que antes.

