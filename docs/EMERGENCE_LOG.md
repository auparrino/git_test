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

