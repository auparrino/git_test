# Registro de emergencia

Todo comportamiento que no fue programado explícitamente y sorprendió, con semilla y turno para
reproducirlo. Es la materia prima del portfolio y de los evals de realismo político.

| Fecha | Versión | Semilla | Turno | Qué pasó | Por qué es interesante | Reproducir |
|---|---|---|---|---|---|---|
| 2026-09 | v0.1 | varias | 20–48 | Trampa de inflación crónica: shocks agotan reservas, cae la confianza institucional y la inflación queda en 5–14 % mensual con aprobación 0 sin llegar a hiperinflación. El BC pasivo no sale solo. | Estado absorbente coherente que no estaba diseñado; obliga al jugador a actuar. | `republica batch --seeds 300 --policy passive` y mirar las corridas con aprobación final < 5 |
| 2026-09 | v0.2 | 7 | 13–48 | Un gobierno que ajusta siempre (opción A en todos los dilemas) con tasa nominal fija termina en deflación, desempleo 16 % y aprobación 19. | Sobreajuste castigado sin que nadie lo programara: emerge de tasa real alta + indexación salarial. | `republica play --seed 7 --auto` |
| 2026-09 | v0.5 | 7 (taylor) | 10–48 | Los tres medios convergen al frame "crisis" y a la influencia máxima (0,6); todas las cohortes perciben ~10 pp más de inflación anual que la real, sin diferencias entre cohortes. | La regla de audiencia premia alinearse con el humor social; cuando todos están descontentos, "crisis" siempre gana y la pluralidad de medios desaparece. **RESUELTO en v0.8** (Quinta ronda de calibración, encargo B1 — ver `docs/CALIBRATION_LOG.md` y ADR 005 §4.5 "revisado v0.8"): alineación de audiencia ponderada por la audiencia PROPIA de cada medio, tabla de sesgo por frame acotada a <= ~4 pp anualizadas/medio, y costo de reputación acumulativo cuando un medio sostiene un frame que contradice la macro real 3+ meses seguidos. Con `seed=7 --policy taylor --months 48` los medios ya no convergen (influencias finales distintas, spread >= 0,1; al menos un medio pasa >= 30 % de los meses fuera de "crisis"; `perception_gap` promedio cae de ~0,9 a ~0,11 pp/mes, con varianza no nula entre cohortes). | `republica run --seed 7 --policy taylor` y mirar `perception_gap` y `outlet_influence` (o `tests/test_cohorts_perception.py`, sección 10, para la reproducción determinista) |
| 2026-09 | v2 hito 1 | 0–99 (core) | 40–90 | En un mundo sin moneda ni Estado, 100 de 100 semillas convergen a las conchas como medio de intercambio; la abundancia de conchas (×0.3 a ×3) no cambia el resultado (H3 refutada) y el costo de transporte solo retrasa la emergencia (H4). Bajar la durabilidad de todos los bienes a 0.6 **no** impide la emergencia; solo se suprime cuando además ningún bien queda sin utilidad directa. | La condición necesaria en esta física no es la durabilidad diferencial (que solo decide entre candidatos) sino la existencia de al menos un bien que nadie consume: su excedente nunca se agota. Hipótesis registrada antes de correr, resultado documentado tal cual. | `republica core batch --seeds 100 --turns 500 --agents 2000` y `republica core classify experiments/results/core_hito1/main` |
| 2026-09 | v0.8 | 1810–1821 (taylor, todo activo) | 60–216 | Corridas de 213 años (2.556 meses): las 12 semillas colapsan entre el año 5 y el 18 (mediana 14). En las 35 elecciones que llegan a celebrarse alternan Unión Republicana (19) y Frente Federal (16); solo 4 reelecciones. Ningún partido menor gana nunca. | El mundo fue calibrado para 48 meses: la confianza institucional y la tensión social no tienen mecanismos de recuperación de largo plazo, así que la estabilidad se erosiona monótonamente hasta el colapso. Es una limitación conocida para horizontes largos, no un hallazgo sobre ningún país real. | `republica run --seed 1810 --policy taylor --months 2556` |
| 2026-09 | A4 (argentina, `a3_main`) | 1–50 | 48 (2019-12) | Calibrar los 107 coeficientes contra series **macro** de 1993–2015 mejoró un resultado **electoral** que la función objetivo nunca puntuó: en V3 (2016→2023) el modelo calibrado acierta la derrota del oficialismo en 2019 en 96 % de las semillas (IC95 90–100 %) contra 4 % (IC95 0–10 %) de Aurora sin calibrar. El término de elecciones del objetivo de A3 figura como "sin dato" en train y holdout (`calibration/a3_main/report.md`): no aportó ninguna señal. | El acierto viene por un camino no diseñado: el drift de coeficientes económicos (`c_f` +81 %, `f_u` +67 %, `st_a` +76 %, `protest_ref` 15→37,8) acelera la cadena aprobación↓ → tensión↑ → voto, y eso alcanza para que las cohortes castiguen al oficialismo. Es el único lugar donde la calibración de A3 "vale" algo, y es en el bloque que no calibró. | `republica validate --country argentina --calibration a3_main --seeds 50 --out data/countries/argentina/validation/a4_main` y mirar `results.json → tests[2].metrics.*.elections["2019-12"]` |
| 2026-09 | A4 (argentina, `a3_main`) | 1–50 | 24 | Calibrar contra datos argentinos reales alejó al modelo del episodio argentino más característico: arrancando del estado real de 1988-06 (inflación 13,99 %/mes), el modelo **calibrado** termina en 1,41 %/mes a los 24 meses y Aurora **sin calibrar** en 4,39 %/mes, con la real en ~33 %/mes (jul-1989). Ninguno de los dos brazos entra nunca en `hyperinflation` (0/50 en ambos). | La calibración de A3 bajó `rho_pi` de 0,85 a 0,45 porque el período de ajuste (1993–2015: convertibilidad + post-2003) es fuertemente reversivo. El coeficiente total sobre la inflación del mes anterior queda en `rho_pi + c_e` = 0,51 < 1: la ecuación es una contracción y una hiperinflación endógena es **algebraicamente imposible** sin forzar un shock. Calibrar sobre una ventana estable puede destruir la capacidad de representar el régimen inestable del mismo país. | misma corrida; `results.json → tests[0]` y `inflation_persistence` |
| 2026-09 | A4 (argentina, `a3_main`) | 1–50 | 69–70 | Las **50 de 50** semillas calibradas de V3 (2016-01 + 96 meses) terminan en `collapse` (`political_stability < 15` × 3 meses) alrededor del mes 70 (≈ 2021-09), mientras las 50 de Aurora sin calibrar llegan enteras al mes 96. La elección de 2023 no se celebra en ninguna corrida calibrada. | Versión acelerada y unánime de la erosión de largo plazo ya registrada para Aurora a 213 años (fila `v0.8`, 1810): con coeficientes calibrados y el estado inicial real de 2016 la erosión tarda 6 años en vez de 14 y no deja ninguna semilla en pie. Cualquier contrafáctico argentino (A6) de más de ~5 años choca contra esto antes que contra la economía. | misma corrida; `results.json → tests[2].metrics.calibrated.outcomes` |
| 2026-09 | Argentina A4 extra | 0–49, inicio 2019-12 real, 48 meses, pandemia y sequía forzadas | 48 | Elección de 2023: el oficialismo pierde en 36 de 36 elecciones celebradas (calibrado; las otras 14 semillas colapsan antes) y en 49 de 50 (Aurora sin calibrar). La inflación final mediana queda en 29 % (calibrado) y 56 % (sin calibrar) contra ~211 % interanual real. | El bloque político acierta el signo del resultado sin acertar la economía que lo causó: la derrota sale de la erosión de aprobación y tensión, no de la inflación. El modelo no sabe quién gana: sus partidos son los de Aurora (`union_republicana` = "la oposición principal"). | ver `docs/EMERGENCE_LOG.md`; reproducir con `run_test_arm` sobre `ValidationTest(start="2019-12", months=48)` |

---

## Sonda exploratoria sobre seis arranques reales (sin hipótesis previa)

Primera pasada de "mirar el modelo andando" en vez de puntuar una hipótesis: seis fechas reales,
15 semillas cada una, calibración `a7_by_regime`, con transiciones de régimen y piso de legitimidad
activos, por CLI (lo mismo que corre un usuario). El hallazgo central no es ninguno de los que las
validaciones V1–V4 estaban midiendo.

### 1. El modelo termina demasiado pronto en casi todo arranque, y el error no es de un signo

| arranque | qué pasó de verdad | outcome del modelo (15 semillas) | mes de fin (mediana) | de |
|---|---|---|---:|---:|
| 1983-12 | hiperinflación en 1989 (mes 66) | `hyperinflation` 15/15 | **9** | 72 |
| 1991-04 | una década de convertibilidad estable | `collapse` 15/15 | **25** | 120 |
| 1998-01 | default y salida del peg en 2001-12 (mes 47) | `collapse` 11/15, `survived` 4 | 44 | 60 |
| 2003-06 | la década de mayor crecimiento reciente | `collapse` 15/15 | **59** | 150 |
| 2019-12 | mandato completo, derrota en 2023 | `hyperinflation` 12/15, `defeated` 3 | 47 | 48 |

Solo **1998-01** cae cerca de la realidad (mes 44 contra 47 real), y es justamente la ventana que V2
puntúa: la única hipótesis histórica que el modelo viene cumpliendo. Las otras cuatro fallan, y de
maneras contradictorias entre sí: desde 1983 hiperinflación **cinco años y medio antes** de tiempo,
desde 1991 y 2003 colapso donde la historia tuvo estabilidad y crecimiento.

Lo importante: **V1 mide 1988-06 y da 0 % de hiperinflación**, mientras que 1983-12 —cinco años
antes, el mismo episodio— da **100 % en el mes 9**. El modelo no es "demasiado explosivo" ni
"demasiado contractivo": es extremadamente sensible al estado inicial, de forma no monótona. Ese
diagnóstico no aparece en ninguna de las cuatro validaciones porque cada una mira un solo arranque.

### 2. Tres variables terminan clavadas exactamente en su cota

En las seis corridas, la mediana final de `government_approval` es **0.00 exacto**. En 2019-12,
`real_wage` termina en **200.00 exacto** y `reserves` en **0.00 exacto**. Un valor final que coincide
con el borde del rango en todas las semillas no es un resultado: es saturación. Las ecuaciones
empujan a la variable contra la cota y el `clamp` la sostiene ahí, así que a partir de ese mes la
variable deja de transportar información y cualquier término que dependa de ella queda congelado.
Es una hipótesis sobre el mecanismo del colapso temprano del punto 1, no una conclusión: habría que
ver si la aprobación toca 0 **antes** del mes de terminación en las corridas que colapsan.

### 3. `--start` aceptaba 8 fechas cuando el dato existía para cualquier mes desde 1961

La sonda pidió `--start 2015-12` (un mes antes del hito 2016-01) y `republica run` lo rechazó con
"no hay estado inicial para esa fecha". Pero `calibration/initial_states.py::flat_initial_state`
construye un estado inicial **real** para cualquier mes con series, y es lo que ya usaban la
calibración y el backtest desde hace dos rondas. Era una inconsistencia entre lo que el proyecto
sabe hacer y lo que el comando dejaba hacer. Corregido: `run` cae a ese constructor cuando la fecha
no es un hito, avisa que el estado se construyó desde las series, y mantiene el error original
—con la lista de fechas— cuando el mes cae fuera del rango con datos (probado con 1950-01).

### Qué hacer con esto

El punto 1 dice que el próximo trabajo **no** es seguir calibrando coeficientes: es entender por qué
el mismo mecanismo hiperinflaciona en el mes 9 desde 1983 y nunca desde 1988. El punto 2 da la
primera pista concreta y es barato de verificar. Ninguno de los dos se ve desde las validaciones
V1–V4, que puntúan un arranque cada una; una sonda de este tipo debería correr en cada ronda.

### Seguimiento: el proxy de importaciones hacía salir la convertibilidad en el mes 1

Siguiendo el punto 1 de la sonda, se trazó mes a mes la corrida que más se aleja de la historia:
1991-04, donde el modelo colapsa en el mes 25 y la realidad tuvo una década de convertibilidad.

**La cascada, con números.** En el **mes 1** —abril de 1991, el mes en que la convertibilidad
empezó— se disparan a la vez `fx_regime_exit` y `banking_crisis`. A partir de ahí:

| mes | aprobación | estabilidad | confianza inst. | tensión | protesta |
|---:|---:|---:|---:|---:|---:|
| 1 | 52.9 | 82.9 | 56.2 | 35.7 | 24.9 |
| 3 | 11.1 | 72.0 | 42.6 | 76.8 | 63.3 |
| 5 | **0.00** | 63.9 | 31.2 | **100.0** | 89.0 |
| 12 | 0.00 | 29.1 | **0.00** | 100.0 | 100.0 |
| 21 | 0.00 | 5.8 | 0.00 | 100.0 | 100.0 | → `collapse` |

Cuatro variables saturan contra su cota entre los meses 5 y 12 y se quedan ahí. Lo decisivo: en los
meses 15 a 21 **las reservas se recuperan** (3 019 → 8 389 USD M), la inflación se mantiene plana en
8–9 % y el desempleo en 8.3 %. La economía se estabiliza y el país colapsa igual, porque el bloque
político ya está clavado en el piso y no tiene término de recuperación que lo despegue.

**La causa raíz.** `R_min`, el piso de reservas que fuerza la salida de un `peg`, son tres meses de
importaciones. Las importaciones salían del proxy `0.18 · PIB / 12` que ADR 012 §4 dejó como
provisorio ("se leen del estado inicial real cuando existen"), y que nunca se reemplazó:

| | valor |
|---|---:|
| Importaciones 1991 según el proxy | 2 850 USD M/mes |
| Importaciones 1991 reales (WDI) | **961** USD M/mes |
| `R_min` con el proxy | 8 550 USD M |
| Reservas reales de abril de 1991 | 7 844 USD M |
| `R_min` con el dato real | **2 883** USD M |

El peg salía en el mes 1 porque el modelo creía que Argentina importaba tres veces más de lo que
importaba. No era un coeficiente mal calibrado: era un dato que faltaba.

**Corregido** con `exports_annual_usd.csv`/`imports_annual_usd.csv` (SOURCES.md fuente 23, `trust`
A, tres cruces en `consistency.md` §15). Efecto medido, misma sonda, 15 semillas:

| arranque | antes (mes de fin) | después | de | real |
|---|---:|---:|---:|---|
| 1983-12 | 9 | 7 | 72 | hiperinflación en el mes 66 |
| 1991-04 | 25 | 30 | 120 | estable |
| 1998-01 | 44 | 41 | 60 | default en el mes 47 |
| 2003-06 | 59 | **105** | 150 | crecimiento |
| 2015-12 | (no corría) | **48 completos, `defeated` 15/15** | 48 | derrota del oficialismo |
| 2019-12 | 47, `hyperinflation` 12/15 | 48, `defeated` 7 / `hyper` 8 | 48 | derrota |

En 1991 el peg ya no sale en el mes 1: aguanta tres meses y la aprobación **sube** de 53 a 73 antes
de que el régimen cambie. 2003-06 casi duplica su horizonte. 2015-12 acierta el resultado electoral
real en las 15 semillas. 2019-12 más que duplica las semillas que terminan en derrota del
oficialismo en vez de en hiperinflación.

**Lo que este arreglo NO toca, y sigue siendo el problema principal.** 1983-12 hiperinflaciona en el
mes 7 (peor que antes) contra el mes 66 real, y 1991-04 sigue colapsando en el mes 30 contra 120. La
saturación del punto 2 sigue intacta: una vez que aprobación, tensión, protesta y confianza tocan
sus cotas, no hay fuerza que las devuelva. El piso de legitimidad de ADR 016 sostiene
`political_stability`, pero no a las cuatro variables que la empujan. **Ese es el próximo trabajo, y
no es calibrar: es darle a esas cuatro un término de recuperación, como ADR 012 §5 hizo con
`institutional_confidence` y `social_tension` pero midiéndolo contra episodios reales.**


---

## La saturación política no es la causa del colapso, y un término de recuperación no la despega

Seguimiento directo del punto 2 de la sonda y del pendiente que quedó arriba ("darle a esas cuatro
un término de recuperación"). Diseño, hipótesis registrada y medición completa en
`docs/ADR_018_political_recovery.md`; acá va lo que **no** estaba previsto.

**Configuración**: cinco arranques reales (1983-12, 1991-04, 1998-01, 2003-06, 2019-12), 15
semillas, calibración `a7_by_regime` con cambio de vector en caliente, todas las features del
paquete, piso de legitimidad activo, sin shocks ni exógenas históricas.

### 1. La saturación no es causa ni consecuencia del colapso: es pérdida de información

La sonda había dejado abierta la pregunta ("habría que ver si la aprobación toca 0 **antes** del mes
de terminación"). Medida, la respuesta es que ninguna de las dos lecturas simples es correcta:

| | evidencia |
|---|---|
| **No es consecuencia** | Desde 1991-04 las cuatro variables tocan su cota entre los meses 6 y 10 y el `collapse` llega en el 22: 13 a 16 meses después. |
| **No es causa suficiente** | Desde 1998-01, `social_tension` está en el techo **41 meses seguidos** en 15/15 semillas y **ninguna** corrida termina antes del horizonte. |
| **Lo que sí es** | Desde 2003-06 la tensión está en 100 durante **103 de los 107 meses** de la corrida *mientras la economía crece*: PBI +3 a +5 %, desempleo de 15,7 % a 9,8 %, inflación −1 %/mes, reservas de 14 878 a 42 276 USD M. La variable dejó de responder al mundo. |

La década de mayor crecimiento reciente, atravesada con la conflictividad social clavada en su
máximo posible, es un defecto peor que el outcome.

### 2. El canal de aprobación que ADR 016 identificó **no existe** bajo la calibración por régimen

ADR 016 §2.3 concluyó, con `a5b_macro`, que el término dominante de la aprobación era
`−e_t·pos(tensión − tension_threshold)`. Con `a7_by_regime` ese término vale **exactamente 0.00
todos los meses de las cinco corridas**, porque la calibración dejó `tension_threshold` en 110,70
(grupo `peg`) y 110,70/117,05 — **por encima del techo 100 del `ranges`**. El término dominante es
otro: `−e_pi·pos(π − 0,894)` con `e_pi = 2,083`, que vale **−14 a −41 puntos de aprobación por mes**
en 1991-04, contra +0,06 a +0,78 de la reversión. Dos calibraciones del mismo modelo producen dos
diagnósticos incompatibles del mismo colapso. Cualquier hallazgo sobre "qué canal domina" hay que
fecharlo por calibración.

### 3. El objetivo por encima de la cota: la aritmética que apaga cualquier recuperación aguas abajo

`tension_target` llega a **208** en 1991-04 y a 145 en 2003-06; el techo es 100. Medido, la relación
de fuerzas contra un término de recuperación de la forma de ADR 012 §5:

```
empuje al techo          t_adj · (tension_target − 100) = 0.359 · (140 − 100) = +14.4 / mes
término de recuperación  ts_rec · pos(100 − 35)         = 0.06  ·  65         =  −3.9 / mes
```

3,7 a 1 en el **mejor** escenario, 10 a 1 en el peor. El mecanismo de ADR 018 se engancha el 72 % de
los meses en 2003-06 y aun así la saturación sólo baja de 38 % a 28 %. La conclusión, medida: **un
término `x' += rec·pos(objetivo − x)` no puede despegar una variable cuyo objetivo está por encima
de su propia cota**, para ningún `rec` que un ancla real sostenga. La corrección no está aguas
abajo: está en acotar los objetivos de §5.3/§5.4 o en recalibrar el lazo `t_pr`/`pr_t`/`pr_a` con la
restricción de que sea contractivo.

### 4. `government_approval` no es una variable que el motor integre

Con `features.cohorts` prendido, la aprobación publicada **no** es el `approval_new` de §5.6:
`engine/simulation.py` la pisa con la suma ponderada de `CohortState.approval_c`, que se recalcula
cada mes desde el estado por cohorte. Cualquier término aplicado al agregado **se vuelve a aplicar
de cero todos los meses en vez de acumularse**. No estaba documentado en ningún lado y explica por
qué la aprobación de 2019-12 no se mueve con ningún coeficiente: para que una recuperación de la
aprobación se integre tiene que entrar **por cohorte**, en `world/cohorts.py::step_cohorts`.

### 5. `crime_perception` es la variable más saturada del modelo, y es un −50 constante en la aprobación

Confirmado con 15 semillas en esta configuración: `crime_perception` está en el techo 100 el **97 %**
de la corrida desde 2003-06, 77 % desde 1991-04 y 70 % desde 1998-01 — más que ninguna de las cuatro
variables del encargo. Y `world/cohorts.py::step_cohorts` la consume como `crime_term =
crime_perception − 50`: clavada en 100 es una **penalización constante de −50 disfrazada de
variable** sobre la aprobación publicada. El término de recuperación de ADR 018 la cubre
(`recover_crime`) pero se envía apagado (`crime_rec = 0.0`): no hay serie de percepción de
inseguridad y está fuera del alcance. Sensibilidad medida: con `crime_rec = 0.5` la saturación de
2003-06 cae de 97 % a 24 % sin cambiar un solo outcome.

En el mismo barrido aparecen tres saturaciones contra la cota **buena**, no documentadas hasta acá:
desde 2019-12 `poverty` está en su **piso (0 %)** el 35 % de la corrida y `real_wage` en su **techo
(200)** el 29 %; desde 2003-06 `inequality` está en su piso (20) el 42 %. Una pobreza de 0 %
sostenida es tan implausible como una aprobación de 0 sostenida.

### 6. Lo que el mecanismo sí logró, y el único candado que funcionó de verdad

La compuerta —tres meses consecutivos de alivio macro, con los cuatro marcadores de ruptura de
ADR 016 cerrándola— **discrimina exactamente como se diseñó**: se engancha el 72 % de los meses
desde 2003-06 y **cero veces** desde 1991-04 o 1983-12. Por eso los tres discriminantes salen
**idénticos** con el flag prendido y apagado: hiperinflación desde 1988-06 20/20, no espuria desde
2003-06 0/20, colapso/default desde 1998-01 con `peg` 19/20, salida del `peg` 17/20. El escenario
1998-01 + `peg` no cambia **en una sola semilla**. El mecanismo no es una amnistía; es, por ahora,
casi un no-op.

El único cambio cualitativo: desde 2003-06 la protesta deja de tocar su techo durante los primeros
ocho años (primer mes en la cota, del **7 al 101**). Es decir, durante la década de crecimiento.

`republica run --country argentina --start 2003-06 --months 150 --calibration a7_by_regime --seed 1`
con y sin `features.political_recovery`; o `tests/test_political_recovery.py`, secciones 4 y 5, para
la reproducción determinista.
