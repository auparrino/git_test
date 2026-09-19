# ADR 016 — Colapso institucional y legitimidad democrática: por qué 2020 no es 2001

Estado: aceptado para implementar. Cierra el pendiente de `docs/PLAN_ARGENTINA.md` §7
("Desde 2019-12 el calibrado colapsa (100 %) antes de la elección de 2023 → revisar la terminación
por `collapse` y la recuperación §5 del ADR 012"). Todo detrás de `features.legitimacy_floor`
(default **off** para Aurora, **on** para `--country argentina` cuando `features.macro_regime` está
activo). Aurora sigue byte a byte igual con el flag apagado.

> **Numeración**: este ADR es el 016 a propósito. El 015 está tomado por otro agente en paralelo.

## 1. El hecho a explicar

Con `--calibration a5b_macro`, desde 2019-12 y 48 meses (la configuración exacta de V4 en
`src/republica/validation/argentina.py`), **20/20 semillas terminan en `collapse`**
(`political_stability < 15` tres meses seguidos; `terminal.collapse_stability = 15`,
`collapse_months = 3`), mediana en el **mes 29**, rango [24, 33]. Ninguna llega al mes 48, así que la
elección de fin de mandato nunca se celebra y la hipótesis electoral de V4 no tiene denominador
(`docs/CALIBRATION_LOG.md`, "Diagnóstico 2019-12" y "Hallazgo transversal…").

La realidad del tramo 2019-12 → 2023-12: inflación de 50 % a 211 % anual, pandemia, brecha cambiaria
de tres dígitos, reestructuración de deuda — **y el gobierno terminó el mandato**. Hubo elección en
octubre/noviembre de 2023 y la perdió el oficialismo. Un `collapse` del modelo (salida anticipada,
ruptura institucional) es 2001 — De la Rúa renuncia, cinco presidentes en once días — o 1989
— Alfonsín entrega cinco meses antes con hiperinflación. No es 2020–2023.

Argentina 1983–2023: **diez mandatos presidenciales, dos salidas anticipadas** (1989 y 2001). En las
dos hubo una **ruptura monetaria o financiera aguda** (hiperinflación de tres dígitos mensuales en
1989; corralito, default y fin de la convertibilidad en 2001). En ninguna de las otras ocho —
incluidas 2002 (Duhalde), 2014 (default técnico con inflación de 38 %) y 2018–2019 (corrida
cambiaria, FMI, inflación de 54 %) — la inflación alta o la impopularidad bastaron.

## 2. Diagnóstico cuantitativo

Comando replicado (brazo `calibrated` de V4, semilla 1, salida en `/tmp/r1.jsonl`): mismo estado
inicial real de 2019-12, mismo calendario de shocks forzados (`epidemic` 2020, `imf_program` 2022,
`drought` 2023), mismas exógenas históricas, `fx_regime = pack.fx_regime_auto` (`control`),
coeficientes de `a5b_macro`. Resultado: `collapse` en el mes 29.

### 2.1 Trayectoria mes a mes (semilla 1)

| mes | estab | aprob | confI | congr | tensión | protesta | infl %/m | desemp | PBI g | confC | default_risk | fx_gap |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 100.0 | 48.3 | 60.9 | 52.9 | 40.6 | 16.3 | 3.78 | 10.40 | −2.17 | 45.0 | 0.410 | 0.002 |
| 3 | 100.0 | 38.6 | 56.4 | 51.7 | 47.2 | 25.3 | 3.81 | 10.24 | −0.26 | 39.1 | 0.422 | 0.011 |
| 6 | 100.0 | 9.7 | 51.1 | 49.3 | 54.9 | 47.4 | 3.78 | 11.14 | −0.27 | 31.3 | 0.377 | 0.020 |
| 9 | 90.1 | **0.0** | 46.3 | 45.7 | 64.7 | 70.5 | 3.82 | 10.94 | 0.74 | 29.5 | 0.393 | 0.029 |
| 12 | 75.4 | 0.0 | 42.1 | 45.8 | 75.4 | 88.3 | 3.82 | 10.86 | 0.73 | 29.0 | 0.422 | 0.035 |
| 15 | 59.8 | 0.0 | 37.5 | 41.4 | 86.0 | **100.0** | 3.82 | 10.81 | 0.69 | 28.9 | 0.445 | 0.040 |
| 18 | 45.3 | 0.0 | 33.0 | 42.2 | 93.1 | 100.0 | 3.82 | 10.77 | 0.59 | 29.0 | 0.497 | 0.044 |
| 24 | 25.2 | 0.0 | 25.5 | 45.9 | 99.3 | 100.0 | 3.74 | 10.90 | −0.33 | 31.0 | 0.634 | 0.049 |
| 26 | 16.7 | 0.0 | 23.0 | 45.7 | **100.0** | 100.0 | 3.81 | 10.77 | 0.28 | 33.2 | 0.629 | 0.050 |
| 27 | 14.7 | 0.0 | 22.0 | 41.8 | 100.0 | 100.0 | 3.63 | 11.75 | −1.73 | 31.2 | 0.745 | 0.050 |
| 28 | 13.3 | 0.0 | 23.0 | 50.4 | 100.0 | 100.0 | 3.65 | 11.93 | −2.07 | 29.2 | 0.639 | 0.050 |
| 29 | 13.5 | 0.0 | 21.9 | 51.2 | 100.0 | 100.0 | 3.78 | 11.72 | −0.65 | 28.5 | 0.535 | 0.051 |

Lo primero que hay que notar: **la inflación no es el canal**. Se queda clavada en 3.6–3.9 % mensual
(≈ 56 % anualizada) las 29 semillas-mes, nunca cruza el 20 % de `terminal.hyper_inflation`, y el
`fx_gap` endógeno llega a 0.05 (5 %, contra una brecha real de 100–150 %). El modelo calibrado
**subestima** la crisis macro real de 2020–2023 y aun así colapsa institucionalmente.

### 2.2 Qué empuja `political_stability` debajo de 15

`step_politics` §5.9: `stability_target = stability_base + st_a·(aprob − approval_ref) +
st_c·(congr − congress_ref) − st_t·(tensión − tension_base) + st_i·(confI − conf_ref)`, y
`stability' = stability + st_adj·(target − stability) + shock_stability`.

Descomposición del `stability_target` con los coeficientes de `a5b_macro`
(`stability_base = 157.03`, `st_a = 0.879`, `st_c = 0.158`, `st_t = 1.077`, `st_i = 0.527`,
`st_adj = 0.205`, `approval_ref = 57.90`, `tension_base = 42.93`, `conf_ref = 58.29`):

| mes | base | `st_a·aprob` | `st_c·congr` | `−st_t·tensión` | `st_i·confI` | **target** | estab |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 157.0 | −11.5 | +4.0 | −1.5 | +0.2 | **148.1** | 100.0 |
| 6 | 157.0 | −42.4 | +3.7 | −12.9 | −3.8 | **101.6** | 100.0 |
| 12 | 157.0 | −50.9 | +3.1 | −34.9 | −8.5 | **65.8** | 75.4 |
| 18 | 157.0 | −50.9 | +2.6 | −54.1 | −13.3 | **41.3** | 45.3 |
| 24 | 157.0 | −50.9 | +3.2 | −60.7 | −17.3 | **31.2** | 25.2 |
| 29 | 157.0 | −50.9 | +4.0 | −61.5 | −19.2 | **29.4** | 13.5 |

**Los dos términos que hacen el trabajo están saturados en su tope**, no en un valor intermedio:

- `st_a·(aprob − approval_ref)` queda congelado en **−50.9** desde el mes 9, porque
  `government_approval` toca el **piso 0** del `ranges` y se queda ahí 20 meses seguidos.
- `−st_t·(tensión − tension_base)` queda congelado en **−61.5** desde el mes 26, porque
  `social_tension` toca el **techo 100**.

El `stability_target` asintótico es **≈ 29**, o sea **por encima** del umbral de colapso (15). Lo que
mete a la estabilidad debajo de 15 es el ruido de `shock_stability`, que en esta corrida viene de las
acciones de actores (`agreement_broken`, protestas) y vale −4 a −8 puntos en los meses 22, 25 y 27–29
— excursiones de magnitud comparable al propio margen de 14 puntos entre el equilibrio (29) y el
umbral (15). El colapso no es "la estabilidad converge a cero": es **"la estabilidad converge a 29 y
el ruido la cruza tres meses seguidos"**.

### 2.3 Por qué la aprobación se hunde a 0 y no vuelve

Descomposición de `government_approval` (§5.6), delta mensual por término:

| mes | `e_w·Δw` | `−e_u·Δu` | `−e_pi` | `e_g·gap` | **`−e_t·tensión`** | `e_rev·()` | aprob(t) → (t+1) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | +1.67 | +0.50 | −0.62 | +0.35 | **−5.36** | +0.87 | 48.3 → 44.8 |
| 4 | +2.71 | −3.15 | −0.55 | −5.94 | **−6.62** | +1.15 | 38.6 → 24.9 |
| 6 | +1.20 | +0.93 | −0.60 | +1.23 | **−7.81** | +1.89 | 14.9 → 9.7 |
| 9 | +1.80 | +0.36 | −0.61 | −0.34 | **−10.08** | +2.33 | 0.8 → 0.0 |
| 18 | +1.95 | +0.11 | −0.61 | −0.71 | **−16.25** | +2.35 | 0.0 → 0.0 |
| 29 | +1.32 | +0.64 | −0.60 | +0.15 | **−18.27** | +2.35 | 0.0 → 0.0 |

El término dominante, por un orden de magnitud, es
`−e_t · pos(social_tension − tension_threshold)/10`. La calibración `a5b_macro` puso
**`tension_threshold = 21.25`** (Aurora: 50) y **`e_t = 2.32`** (Aurora: 1.0). Con la tensión social
arrancando en 35 — **por encima del umbral desde el mes 1** — y subiendo a 100, ese término pasa de
−5.4 a −18.3 puntos de aprobación por mes. El mayor contrapeso disponible es
`e_rev·(target − aprob) = +2.35` (con `e_rev = 0.0317` y el target de la recuperación §5 del ADR 012,
`approval_reversion + e_rev_sentiment_k·(confC/100) ≈ 70.9 + 11.5·0.29 ≈ 74.3`). **La aprobación no
tiene forma de volver**: el término de tensión es 7× el de reversión.

### 2.4 Por qué la tensión social se va al techo: el bucle tensión ↔ protesta

`tension_target` (§5.3) incluye `+ t_pr·(protesta − protest_ref)` y `protest_target` (§5.4) incluye
`+ pr_t·(tensión − tension_base) − pr_a·(aprob − approval_ref)`. Con los coeficientes calibrados
(`t_pr = 0.557` vs 0.2 en Aurora; `pr_t = 1.420` vs 0.8; `pr_a = 0.533` vs 0.2), evaluados en el
estado terminal (tensión 100, protesta 100, aprobación 0, confI 22):

```
tension_target  = 42.93 + t_pr·(100 − 18.56) + (−t_c)·(22 − 58.29) + … ≈ 42.9 + 45.3 + 15.6 ≈ 110
protest_target  = 18.56 + pr_t·(100 − 42.93) + pr_a·57.90            ≈ 18.6 + 81.1 + 30.9 ≈ 131
```

Los dos objetivos están **por encima del techo 100 del `ranges`**: es un atractor absorbente. Una vez
que la aprobación toca 0, el término `+pr_a·approval_ref = +30.9` de la protesta es una constante
positiva permanente, y el bucle se cierra sobre sí mismo. No hay trayectoria de vuelta.

### 2.5 La recuperación §5 del ADR 012 está inerte bajo la calibración

Los tres canales de §5 existen en el código y se ejecutan, pero los valores que les dio `a5b_macro`
los desactivan de hecho en cualquier escenario argentino de este tramo:

| canal §5 | coeficiente ADR 012 | calibrado `a5b_macro` | efecto medido en 2019-12 |
|---|---:|---:|---|
| `t_rec` (tensión social baja si la economía va bien) | `recovery_inflation_max = 3.0 %/mes` | **1.129 %/mes** | **nunca se dispara**: la inflación del tramo es 3.6–3.9 %/mes, siempre > 1.13 |
| `ic_rec` (confianza institucional recupera hacia `ic_target`) | `ic_target_base = 45` | **22.77** | actúa sólo como **piso en ≈ 22.8**, muy por debajo de `conf_ref = 58.29`: es lo que explica que confI se estacione en 21–23 en vez de seguir a 0 |
| `e_rev_sentiment_k` (piso del desgaste de aprobación) | `10.0` | 11.52 | activo, pero vale **+2.35/mes** contra −18.3/mes del término de tensión: irrelevante |

Es decir: la afirmación de `PLAN_ARGENTINA.md` §6 ("el mecanismo de recuperación no alcanza a
compensar el punto de partida real") es correcta pero incompleta. Dos de los tres canales no
"no alcanzan": **directamente no corren**, porque la calibración ató sus disparadores a umbrales
(1.13 % mensual de inflación, 22.8 de confianza objetivo) que Argentina no cruza por el lado bueno en
ninguno de los períodos de validación.

### 2.6 `default_risk` alto en períodos solventes (hallazgo (d) de la consigna)

Confirmado, y **no se toca en este ADR**, con evidencia de por qué. `default_risk` en 2019-12 oscila
entre 0.38 y 0.75 sin tendencia clara; desde 1998-01 (período solvente pre-crisis) arranca igual de
alto, como ya documentó el ADR 012 en "Otros hallazgos honestos". Dos razones para no tocarlo acá:

1. El ADR 012 ya dejó registrado en "Probado y descartado" que inicializar `external_debt_usd` desde
   `sim.state.public_debt` (el índice por fecha) rompe el test 5 de recuperación (20/20 → 0/20) sin
   arreglar el test 3. No se repite ese experimento.
2. **`default_risk` no participa del colapso de 2019-12**. El `default_risk_threshold` calibrado es
   **0.99944**, así que el canal `sovereign_default` endógeno nunca se dispara en ninguna de las 20
   semillas; y ni `default_risk` ni `fx_gap` entran en `stability_target` ni en `approval`. Arreglar
   `default_risk_a/b/c` no movería una sola de las 20 semillas de V4. Queda para la recalibración por
   régimen (`PLAN_ARGENTINA.md` §7, fila 1), que es quien puede ajustarlo contra series reales.

### 2.7 Comparación con Aurora sin calibrar (control)

| escenario | outcomes (20 semillas) | llegan al horizonte | infl. anual final (mediana) |
|---|---|---:|---:|
| 2019-12, 48m, **calibrado `a5b_macro`** | 20 `collapse` (mediana mes 29) | 0/20 | 56.4 % |
| 2019-12, 48m, **Aurora sin calibrar** | 18 `hyperinflation`, 2 `collapse` | 0/20 | 409.9 % |
| 1998-01 + `peg`, 54m, **calibrado** | 17 `collapse` (mediana mes 38), 3 `survived` | 3/20 | 5.0 % |
| 1998-01 + `peg`, 54m, **sin calibrar** | 20 `hyperinflation` | 0/20 | 394.2 % |

El control confirma que el problema es del brazo calibrado y del canal político: Aurora sin calibrar
también falla, pero por precios (y con una inflación 7× la real). Y confirma que el modelo **no
distingue 2001 de 2020**: los dos tramos colapsan con la misma frecuencia (100 % y 85 %) por el mismo
mecanismo, aunque uno terminó en renuncia presidencial y el otro en una elección normal.

### 2.8 Resumen del diagnóstico

El colapso de 2019-12 **no viene de la macro**. Viene de una cadena política de cuatro eslabones,
toda dentro de `society.py`/`politics.py`, en la que cada eslabón satura en un extremo del `ranges`:

```
tensión inicial 35 > tension_threshold 21.25
   → −e_t·(tensión−21.25)/10 domina la aprobación (−5 → −18 por mes)
   → aprobación toca el piso 0 (mes 9) y se queda
   → pr_a·(0 − 57.90) = +30.9 constante en protest_target → protesta al techo 100
   → t_pr·(100 − 18.56) = +45.3 constante en tension_target → tensión al techo 100
   → stability_target ≈ 157 − 50.9 − 61.5 ≈ 29, y shock_stability (−4 a −8) la cruza debajo de 15
```

Y la recuperación §5 del ADR 012 no interrumpe la cadena en ningún punto (2.5).

## 3. Hipótesis registrada (escrita ANTES de tocar código)

**Mecanismo propuesto: piso de estabilidad por legitimidad democrática, con compuerta de ruptura.**

La afirmación sustantiva es: *en una democracia consolidada, un gobierno con mandato constitucional
vigente no sufre una salida anticipada por impopularidad e inflación alta; la sufre cuando hay una
ruptura monetaria o financiera aguda.* Argentina 1983–2023 la respalda: dos salidas anticipadas en
diez mandatos, las dos con ruptura (hiperinflación 1989; corralito + default + fin de la
convertibilidad 2001), ninguna en los ocho restantes pese a inflaciones de 38 %, 54 % y 211 % anual.

Formalmente, cada mes, si el régimen es `democracy` (`repression == 0`) **y no hay ruptura aguda
activa**, `political_stability` no puede caer por debajo de

```
floor = lf_min + (lf_base − lf_min) · clamp(1 − meses_de_mandato / term_length, 0, 1)
```

donde `meses_de_mandato` se cuenta desde la última elección celebrada (o desde el arranque de la
corrida). El piso decae a lo largo del mandato: la legitimidad de origen se gasta.

**Ruptura aguda** (cualquiera de las cuatro; mientras haya una, el piso no se aplica):

1. inflación mensual > `lf_rupture_inflation` durante `lf_rupture_months` meses seguidos
   (régimen hiperinflacionario: 1989);
2. crisis bancaria activa (`banking_crisis_months_left > 0`: corralito 2001);
3. `sovereign_default` activo (default 2001);
4. hubo una salida forzada de régimen cambiario (`fx_regime_exit`) **durante el mandato en curso**
   (fin de la convertibilidad, enero de 2002): el gobierno que rompió el régimen monetario no puede
   invocar su legitimidad de origen por el resto del mandato.

Por qué elijo esto y **no** las otras opciones de la consigna:

- **(b) "exigir además protesta alta o confianza muy baja para el `collapse`"**: medido en 2.1, en el
  tramo 2019-12 la protesta está en **100** y la confianza institucional en **22** — las dos en el
  extremo "colapso". La opción (b) **no discriminaría 2020 de 2001**: descartada con evidencia, no
  por gusto.
- **(c) "recalibrar la recuperación §5 contra `politics/events.csv`"**: el diagnóstico 2.5 muestra que
  los disparadores de §5 los fijó la calibración, y `src/republica/calibration/*` es de otro agente.
  Se documenta el hallazgo (2.5) y se deja la corrección al pipeline de calibración.
- **(d) `default_risk`**: descartado con evidencia en 2.6 (no participa del colapso; y el
  experimento obvio ya está en "Probado y descartado" del ADR 012).

**Hipótesis medible** (todo con `a5b_macro` salvo donde se aclara, 20–50 semillas):

| # | Predicción | Umbral |
|---|---|---|
| H1 | Desde 2019-12, 48 meses: semillas que llegan al mes 48 (elección celebrada) | **≥ 60 %** |
| H2 | Desde 2019-12, 48 meses: inflación anualizada final mediana | **> 80 %** |
| H3 | Desde 1998-01 con `--fx-regime peg`, 54 meses (ventana que termina en 2002-06): `collapse` | **≥ 50 %** |
| H4 | ADR 012 §7 test 2a: hiperinflación desde 1988-06 en ≤ 18 meses | **≥ 50 %** |
| H5 | ADR 012 §7 test 2b: hiperinflación desde 2003-06 en ≤ 18 meses | **0 %** |
| H6 | ADR 012 §7 test 3c: salida del `peg` desde 1998-01 antes del mes 54 | **≥ 50 %** |
| H7 | ADR 012 §7 test 5: 2003-06 → 2015-12 sin colapso | **≥ 80 %** |
| H8 | Flag off: golden de Aurora y de `test_country_pack_argentina.py` | **byte a byte** |

H3 es la que impide que el mecanismo sea una simple amnistía: **el modelo tiene que seguir
distinguiendo 2001 de 2020**. Si H1 se cumple pero H3 no, el mecanismo está mal y hay que reportarlo
como tal.

> **Nota sobre H3 y la fecha 2001-01.** La consigna pedía medir el discriminante "desde 2001-01 con
> `--fx-regime peg`". `data/countries/argentina/country.json` **no tiene `initial_states` para
> 2001-01**: las ocho fechas disponibles son 1983-12, 1988-06, 1991-04, 1998-01, 2003-06, 2016-01,
> 2019-12 y 2023-12, y `_select_initial_state` levanta `CountryPackError` para cualquier otra. Se usa
> **1998-01 con `peg` y 54 meses**, que es la configuración de V2 y cuya ventana **termina
> exactamente en 2002-06**, la fecha límite que pide la consigna. No se inventó un estado inicial
> para 2001-01.

**Riesgo declarado de antemano**: con un piso duro, H1 puede salir cerca del 100 %, es decir, el
mecanismo convierte "no colapsar sin ruptura" en una propiedad *por construcción*, no en un resultado
emergente. Eso es una decisión de modelado fuerte y se declara como tal: **todo el poder
discriminante del mecanismo vive en la definición de "ruptura aguda"** de arriba, no en la dinámica.
Si H3 se cumple, la definición de ruptura separa los dos casos; si no, el mecanismo es una amnistía
general y hay que decirlo.

## 4. Implementación

Detrás de `features.legitimacy_floor` (ausente/false = comportamiento de siempre):

- `world/economy.py::MacroCoefficients`: cinco campos nuevos con docstring por campo
  (`lf_base`, `lf_min`, `lf_rupture_inflation`, `lf_rupture_months`, `lf_exit_window_months`),
  replicados en `data/countries/argentina/country.json → macro.coefficients`.
- `world/events.py`: `LegitimacyContext` (dataclass) y `legitimacy_stability_floor(...)`, función
  pura y testeable por separado, más `apply_legitimacy_floor(...)`.
- `engine/simulation.py`: `Simulation` gana `legitimacy_floor_enabled`, `last_election_month`,
  `rupture_high_pi_months`, `fx_exit_month` y `current_repression`; `advance_month` aplica el piso
  sobre el estado ya clampeado, **antes** de `check_termination`; `run()` toma
  `legitimacy_floor: bool | None = None` (`None` ⇒ lee `country.features["legitimacy_floor"]`).
- `cli.py`: `--legitimacy-floor / --no-legitimacy-floor`.

El piso se aplica **sobre el estado publicado** (no es un veto sólo en la terminación): así
`political_stability` entra a `institutional_confidence` del mes siguiente por el término
`ic_s·(estab − stability_base)/10`, que es el único canal de vuelta que existe.

## Notas de implementación

Implementado como se diseñó en §3/§4, sin retunear ningún coeficiente: los cinco valores
(`lf_base = 28`, `lf_min = 18`, `lf_rupture_inflation = 15`, `lf_rupture_months = 3`,
`lf_exit_window_months = 600`) son los del diseño y las ocho hipótesis se cumplieron en la primera
medición. Eso no es mérito: es consecuencia de que el mecanismo es un piso duro (ver "riesgo
declarado" en §3) y de que los umbrales se eligieron a partir del diagnóstico §2, que ya decía
dónde estaba el equilibrio (≈ 29) y dónde el umbral (15).

### Resultados medidos

**50 semillas por celda** (semillas 1–50), mismo brazo y misma configuración en las dos columnas: lo
único que cambia es el flag.

| escenario | piso OFF | piso ON | hipótesis |
|---|---|---|---|
| **2019-12, 48m, `a5b_macro`** | `collapse` **50/50**, mediana mes 29 [24, 35]; llegan al mes 48: **0 %** | `defeated` **50/50**; llegan al mes 48: **100 %** | H1 ✅ (≥ 60 %) |
| ↳ inflación anualizada final (mediana) | 56.8 % | **102.0 %** (compuesta 12m) / **128.8 %** (anualizada del último mes, métrica de V4) | H2 ✅ (> 80 %) |
| ↳ estabilidad / aprobación / tensión / confI finales | 11.6 / 0.0 / 100.0 / 15.4 | 18.0 / 46.1 / 100.0 / 0.0 | — |
| **1998-01 + `peg`, 54m, `a5b_macro`** | `collapse` **37/50 (74 %)**, mediana mes 39 [28, 48] | `collapse` **37/50 (74 %)**, mediana mes 39 [28, 48] | H3 ✅ (≥ 50 %) |
| ↳ `fx_regime_exit` | 50/50 | 50/50 | — |
| **2019-12, 48m, Aurora sin calibrar** (control) | 47 `hyperinflation` / 3 `collapse` | 47 `hyperinflation` / 3 `collapse` (idéntico) | — |

**El mecanismo cambia exactamente un escenario de los tres.** En 1998-01 con `peg` no cambia
**nada** (mismos outcomes, mismos meses, semilla por semilla): la salida forzada de la
convertibilidad ocurre en las 50 semillas y suspende el piso por el resto del mandato. En Aurora sin
calibrar tampoco cambia nada: la hiperinflación sostenida mantiene la compuerta de ruptura abierta.
Eso es H3 cumplida en su forma fuerte — no "el colapso sigue siendo frecuente" sino "el colapso es
idéntico".

**ADR 012 §7, los cuatro escenarios estocásticos** (20 semillas, coeficientes SIN calibrar del
paquete, misma configuración que `tests/test_macro_regime.py`):

| test ADR 012 | objetivo | piso OFF | piso ON |
|---|---|---|---|
| 2a hiperinflación 1988-06 ≤ 18m | ≥ 50 % | **20/20** | **20/20** (idéntico) |
| 2b no espuria 2003-06 ≤ 18m | 0 % | **0/20** | **0/20** (idéntico) |
| 3c salida del `peg` 1998-01 < mes 54 | ≥ 50 % | **17/20** | **17/20** (idéntico) |
| 5 recuperación 2003-06 → 2015-12 | ≥ 80 % | **20/20** | **20/20** (idéntico) |

H4–H7 ✅, y no "pasan por poco": los cuatro dan resultados **idénticos**. La razón es que en ninguno
el piso llega a morder — en 1988-06 y en 1998-01 hay ruptura activa (hiperinflación / salida del
peg), y en 2003-06 no hay colapso que evitar. H8 ✅: `test_aurora_without_country_matches_golden_
hash_pre_a2` y el golden de `tests/test_country_pack_argentina.py` siguen byte a byte
(Aurora no declara `features.legitimacy_floor` y además corre sin `macro_coefficients`: doble gate).

### V4 con el mecanismo: la hipótesis electoral por fin tiene denominador

`republica validate --country argentina --calibration a5b_macro --out
data/countries/argentina/validation/a6b_collapse --tests V4` (50 semillas por brazo, 13.6 s de
pared; la CLI usa `--out`, no `--run-id`):

| métrica | calibrado (`a5b_macro`) | Aurora sin calibrar | antes (`a6_macro`) |
|---|---:|---:|---:|
| semillas que terminan antes del mes 48 | **0 / 50** | 50 / 50 | 50 / 50 |
| semillas que celebran la elección de fin de mandato | **100 %** | 0 % | 0 % |
| derrota del oficialismo | **100.0 %** IC95 [100, 100] | 0.0 % | 0.0 % (sin denominador) |
| inflación anualizada final (mediana) | **128.8 %** IC95 [125.7, 143.8] | 1 319.4 % | 56.7 % |
| veredicto | **CUMPLIDA** | NO CUMPLIDA | NO CUMPLIDA |

V4 pasa de NO CUMPLIDA a **CUMPLIDA** (pedía derrota > 70 % e inflación final mediana > 100 %).
Contra el dato real (≈ 211 % anual en dic-2023, INDEC), 128.8 % sigue siendo una subestimación de
~40 %, pero es la primera vez que la trayectoria llega entera al final de la ventana.

**Tres advertencias honestas sobre ese "100 % de derrota":**

1. **V4 es in-sample.** 2019-12→2023-11 cae dentro del train de `a5b_macro` (`1992-01:2023-12`), como
   ya declaraba `CALIBRATION_LOG.md`. No es una prueba de generalización.
2. **El oficialismo que pierde no es el que perdió en la realidad.** `incumbent_party` en las 50
   semillas es **`cambiemos_jxc`**, no `fpv_fdt_pj`. La causa está en los datos de ADR 013:
   `data/countries/argentina/politics/parties/2015-2023.json` marca `in_government: true` en el
   partido de **apertura de la época** (Macri, 2015) y `world/eras.py` lo aplica tal cual
   (`"in_government": ... if i == 0 else False`), sin resolver por fecha de arranque. Para una
   corrida que empieza en **2019-12** — cuando Fernández ya asumió, y de cuyo resultado electoral
   sale el `government_approval` inicial del propio paquete (52.66, derivado del 47 % del Frente de
   Todos en 2019) — el incumbente del modelo es el partido equivocado. Así que la métrica "pierde el
   oficialismo = 100 %" dice *"JxC pierde contra el FdT"*, no *"el FdT pierde"*. **No se corrigió
   acá**: es dato y loader de ADR 013, en curso en paralelo (ver "Lo que hace falta de otros
   módulos"). El mecanismo de este ADR es independiente de ese bug — el piso no toca quién gana —,
   pero la *lectura* de V4 sí depende de él y quedaría mal contada si no se dijera.
3. **LLA no gana ninguna** (0/50), pero por primera vez **llega al balotaje en 50/50**:

   | partido | 1ª vuelta (mediana) | balotaje (mediana) | real (oct/nov 2023) |
   |---|---:|---:|---:|
   | `fpv_fdt_pj` | 38.15 % | **54.78 %** | 36.78 % / 44.35 % |
   | `lla` | 37.66 % | 45.22 % | 29.99 % / **55.65 %** |
   | `uca_otros_2015` | 18.18 % | — | — |
   | `cambiemos_jxc` | 2.85 % | — | 23.83 % |

   Esto **confirma y precisa** el diagnóstico de ADR 013 ("el balotaje es el cuello de botella"): en
   primera vuelta LLA ya sobre-performa al dato real (37.7 % contra 29.99 %), y pierde igual el
   balotaje 45/55 — el espejo exacto del resultado histórico. Antes de este ADR la afirmación no era
   medible en V4 en absoluto, porque no se celebraba ninguna elección.

   **`tests/test_eras_argentina.py::test_lla_wins_more_often_under_sustained_distrust` se deja en
   `xfail(strict=True)`, sin tocar.** Se verificó explícitamente que sigue fallando (la suite reporta
   `1 xfailed`). Ese test no corre la ventana de V4: monta un escenario sintético con
   aprobación/confianza forzadas, que este ADR no modifica (el piso actúa sobre
   `political_stability`, no sobre la intención de voto ni sobre la regla de balotaje). Sacarle el
   marcador ahora sería falso. El cuello de botella sigue siendo la segunda vuelta, ahora con número:
   45.22 % mediana para LLA.

### La trayectoria con el piso puesto (semilla 1, misma corrida que §2.1)

`republica run --country argentina --start 2019-12 --months 48 --calibration a5b_macro --seed 1`
(outcome `defeated`, 48 meses):

| mes | estab | aprob | confI | tensión | protesta | infl %/m | default_risk |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 25 | 22.79 | 0.0 | 22.77 | 99.5 | 100.0 | 4.05 | 0.613 |
| 26 | **22.58** | 0.0 | 21.61 | 100.0 | 100.0 | 3.94 | 0.738 |
| 30 | 21.75 | 0.0 | 0.00 | 100.0 | 100.0 | 6.38 | 0.844 |
| 36 | 20.50 | 0.5 | 0.00 | 100.0 | 100.0 | 7.35 | 0.860 |
| 42 | 19.25 | 0.5 | 0.00 | 100.0 | 100.0 | 8.03 | 0.931 |
| 48 | **18.00** | 45.7 | 0.00 | 100.0 | 100.0 | 8.57 | 0.985 |

Tres lecturas:

1. **El piso muerde desde el mes 26 y a partir de ahí la estabilidad ES el piso**, exactamente:
   `18 + 10·(1 − 26/48) = 22.58` y `18 + 10·(1 − 48/48) = 18.00`. No queda margen dinámico: a partir
   de que el piso se activa, `political_stability` deja de ser una variable del modelo y pasa a ser
   la rampa de legitimidad. Es el "riesgo declarado" de §3 hecho visible, y hay que leerlo así.
2. **Hallazgo emergente no buscado: la inflación se acelera en la segunda mitad**, de ~3.9 %/mes a
   8–11 %/mes. La corrida que antes moría en el mes 29 nunca llegaba a mostrarlo. Es lo que sube la
   inflación anual final de 56.8 % a 128.8 %, y va en la dirección correcta: la Argentina real pasó
   de ~50 % anual en 2019 a ~211 % en dic-2023. Sigue subestimando (129 vs 211) pero por primera vez
   el modelo reproduce la *forma* del tramo, no sólo su nivel inicial.
3. **El piso NO rescata a la confianza institucional**: `confI` cae a 0 en el mes 30 y se queda. El
   canal de vuelta `ic_s·(estab − stability_base)/10` existe, pero con `stability_base = 157.03`
   calibrado, una estabilidad de 20 sigue aportando −1.7 por mes. La justificación de aplicar el piso
   sobre el estado publicado (§4) sigue siendo correcta como diseño, pero **medida, esa
   realimentación no alcanza**. El estado social con el que el modelo llega a la elección
   (aprobación 0, tensión 100, protesta 100, confianza 0) es implausible para la Argentina de 2023:
   el mecanismo hace que la corrida llegue a la elección, no que llegue en un estado creíble.
   Eso es exactamente el punto 1 de la lista de abajo.

### Lo que el diagnóstico encontró y este ADR NO arregla

Se documenta para que la próxima ronda no tenga que volver a medirlo:

1. **La recuperación §5 del ADR 012 sigue inerte** (§2.5): `recovery_inflation_max = 1.129 %/mes` y
   `ic_target_base = 22.77` desactivan de hecho dos de sus tres canales en cualquier escenario
   argentino. Este ADR **no** los toca — son valores que produjo la calibración, y
   `src/republica/calibration/*` es de otro agente. El piso de legitimidad **no reemplaza** a esa
   recuperación: no arregla la aprobación en 0 ni la tensión en 100, sólo impide que ese estado
   terminal se traduzca en una salida anticipada. Se ve en la tabla de arriba: con el piso, la
   tensión final sigue en 100.0 y la confianza institucional **baja** de 15.4 a 0.0 (la corrida dura
   19 meses más, así que hay más tiempo para que caiga). El modelo llega a la elección en un estado
   social que sigue siendo implausible.
2. **El bucle tensión ↔ protesta es un atractor absorbente** con los coeficientes calibrados (§2.4):
   `tension_target ≈ 110` y `protest_target ≈ 131`, los dos por encima del techo 100. Mientras eso
   siga así, cualquier mecanismo que actúe aguas abajo (como este) está parcheando un síntoma.
   La corrección natural es acotar los objetivos de §5.3/§5.4 o recalibrar `t_pr`/`pr_t`/`pr_a` con la
   restricción de que el lazo cerrado sea contractivo — trabajo de calibración, no de mecanismo.
3. **`default_risk` alto en períodos solventes** (§2.6): confirmado, sin cambios, con la razón
   medida de por qué no afecta a este pendiente (`default_risk_threshold` calibrado = 0.99944).
4. **`in_government` por época y no por fecha** (advertencia 2 de V4, arriba).

### Detalles de implementación

- **Dónde se aplica.** `engine/simulation.py::advance_month`, sobre el estado **ya clampeado** y
  **antes** de `check_termination`. Se aplica sobre el estado publicado a propósito (no es un veto
  sólo en la terminación): `political_stability` entra a la `institutional_confidence` del mes
  siguiente por el término `ic_s·(estab − stability_base)/10` de §5.8, que es el único canal de
  vuelta que existe en el motor.
- **Doble gate.** El piso corre sólo si `features.legitimacy_floor` **y** hay `macro_coefficients`
  (los `lf_*` viven ahí). Aurora falla los dos.
- **Funciones puras.** `legitimacy_rupture_active` / `legitimacy_stability_floor` /
  `apply_legitimacy_floor` en `world/events.py`, con `LegitimacyContext` como único argumento de
  contexto: testeables sin correr una simulación (`tests/test_collapse_recovery.py` §4).
- **`last_election_month` / `fx_exit_month`** se reinician en cada elección celebrada: el mandato
  nuevo recupera `lf_base` y no arrastra la ruptura cambiaria del anterior.

### Los `lf_*` no son calibrables, a propósito (y cómo se logró sin tocar `calibration/*`)

Primer intento: agregar los cinco campos a `MacroCoefficients` como `float`. Rompió
`tests/test_calibration_macro.py::test_parameter_space_includes_macro_group_with_valid_bounds`
(`61 != 58`), porque `calibration/parameters.py::MACRO_TUNABLE` se arma automáticamente con **todos**
los campos `float` de la dataclass. No es sólo un test molesto: el efecto real habría sido que CMA-ES
ajustara `lf_base`/`lf_min`/`lf_rupture_inflation` contra series — convertir la hipótesis histórica
de §3 en un parámetro ajustado hasta que dé, justo lo que prohíbe `PLAN_ARGENTINA.md` §0 regla 3. Y
habría ampliado el espacio de parámetros de otro agente sin avisarle.

Solución, sin tocar `src/republica/calibration/*`: los tres campos flotantes se anotan con el alias
`StructuralFloat = float` (`world/economy.py`). Con `from __future__ import annotations`, el
`f.type` que inspecciona `MACRO_TUNABLE` es la **cadena** de la anotación, así que `"StructuralFloat"`
no matchea `("float", float)` y los campos quedan fuera del vector. `MACRO_TUNABLE` vuelve a 58 y el
test pasa sin modificarlo. Los dos enteros (`lf_rupture_months`, `lf_exit_window_months`) ya quedaban
fuera por el filtro existente.

Efecto de segundo orden, encontrado y corregido: `calibration/run.py::load_calibrated_country`
reconstruye `MacroCoefficients(**raw["macro"])` desde un `coefficients.json` que **no** trae los
`lf_*` (`a5b_macro` guarda 60 claves, ninguna `lf_*`), así que un brazo calibrado se habría quedado
con los **defaults de la clase** en vez de los valores de `country.json → macro.coefficients`. Hoy
coinciden, así que no habría cambiado ningún número — pero editar `country.json` no habría tenido
efecto bajo `--calibration`, en silencio. Se agregó `world/economy.py::
merge_structural_coefficients`, aplicada en los dos únicos lugares que combinan una calibración con
un paquete: `cli.py` y `validation/argentina.py::run_test_arm`. Cubierto por
`test_legitimacy_coefficients_of_the_pack_survive_a_calibration`.

### Lo que hace falta de otros módulos (no tocados por este ADR)

- `src/republica/calibration/*`: `recovery_inflation_max` / `ic_target_base` (punto 1 de arriba) y el
  lazo `t_pr`/`pr_t`/`pr_a` (punto 2). Si la recalibración por régimen de `PLAN_ARGENTINA.md` §7 se
  hace, conviene agregarle la restricción de que el lazo tensión↔protesta sea contractivo.
- `src/republica/world/eras.py` + `data/.../politics/parties/*.json` (ADR 013): resolver
  `in_government` por **fecha de arranque**, no por apertura de época. Hoy hace que V4 mida "pierde
  JxC" en vez de "pierde el FdT".

### Tests

`tests/test_collapse_recovery.py`, 15 tests: golden de Aurora intacto; el flag por defecto
(off en Aurora, on en Argentina); el `collapse` de 2019-12 con el flag apagado (el diagnóstico §2
congelado como test de regresión); H1/H2 y elección celebrada desde 2019-12 (10 semillas); H3 desde
1998-01 con `peg`, más la forma fuerte (outcomes idénticos con y sin flag); unit tests de la forma
del piso y de los cuatro marcadores de ruptura; y los dos tests de que los `lf_*` quedan fuera del
vector calibrable y sobreviven a `--calibration`.

`uv run ruff check . && uv run ruff format --check .` limpios (incluido
`scripts/build_argentina_eras.py`, que el ADR 012 reportaba con 85 errores: ya fue corregido por
ADR 013).
