# ADR 020 — Sonda exploratoria: `republica probe`

Estado: aceptado. Responde a una pregunta que ninguna de las dos herramientas existentes hace:
*¿el modelo se está comportando como un modelo, o hay algo roto mecánicamente?*

No es un backtest ni una validación. Es una **tercera herramienta**, deliberadamente sin hipótesis
previa, que corre unos pocos arranques históricos con muchas semillas y reporta **el comportamiento
del modelo**: cuándo termina, qué variables quedan clavadas contra su cota, qué valores salen del
rango físico, qué eventos aparecen y qué semillas revientan.

---

## 1. Por qué hace falta una tercera herramienta

El proyecto ya tiene dos instrumentos de medición y los dos puntúan **aciertos**:

| Herramienta | Qué hace | Qué se pregunta |
|---|---|---|
| `republica backtest` (ADR 014) | 107 orígenes rodantes × 3 horizontes × 30 semillas × 2 brazos; puntúa 6 objetivos contra series reales en `t0 + h` y cruza el acierto con características de la ventana | *¿en qué condiciones el modelo predice?* |
| `republica validate` (ADR 011 §8, A4) | 4 pruebas con la hipótesis **registrada antes de correr** (V1 1988-06, V2 1998-01, V3 2016-01, V4 2019-12) más el control Aurora | *¿se cumple esta hipótesis histórica concreta?* |
| `republica probe` (este ADR) | Unos pocos arranques históricos × N semillas; **no puntúa nada**: describe el comportamiento del modelo y busca síntomas de falla mecánica | *¿hay algo roto?* |

La diferencia no es de grado. Un objetivo puntuado exige un dato real contra el cual comparar y una
hipótesis o una métrica definida de antemano; **lo que no está en la lista de objetivos no se mira**.
Una sonda exploratoria mira lo que hay, sin lista.

### La evidencia: lo que la sonda ad hoc encontró en una sola pasada

La primera vez que se corrió esta idea a mano (`docs/EMERGENCE_LOG.md`, "Sonda exploratoria sobre
seis arranques reales") aparecieron, en una pasada, dos problemas que **ni V1–V4 ni el backtest de
ADR 014 habían visto**:

1. **El modelo termina demasiado pronto en casi todo arranque, y el error no es de un signo.** Desde
   1983-12 hiperinflaciona en el mes 9 (real: mes 66); desde 1991-04 colapsa en el mes 25 (real:
   una década de convertibilidad); desde 2003-06 colapsa en el mes 59 (real: crecimiento). Solo
   1998-01 cae cerca (mes 44 contra 47 real) — y es justamente el arranque que V2 puntúa.
   **V1 mide 1988-06 y da 0 % de hiperinflación; 1983-12, cinco años antes y el mismo episodio, da
   100 % en el mes 9.** El modelo no es "demasiado explosivo" ni "demasiado contractivo": es
   extremadamente sensible al estado inicial, de forma no monótona. Ninguna validación podía ver
   esto porque **cada una mira un solo arranque**: la contradicción vive entre arranques.
2. **Cuatro variables políticas terminan clavadas exactamente en su cota** (`government_approval`
   0.00, `social_tension` 100.0, `protest_level` 100.0, `institutional_confidence` 0.00; en
   2019-12 también `real_wage` 200.00 y `reserves` 0.00). Un valor final que coincide con el borde
   del rango en **todas** las semillas no es un resultado: es saturación. A partir de ese mes la
   variable deja de transportar información y todo término que dependa de ella queda congelado.

El backtest no podía ver ninguno de los dos. El punto 1 se le escapa porque el backtest puntúa
*dirección y magnitud de la inflación, régimen, elección, crisis y golpe* — la **terminación
temprana** aparece ahí sólo indirectamente (como un `hit` perdido) y nunca como un mes concreto
comparado contra el mes real del episodio. El punto 2 se le escapa porque **ninguna variable de
estado excepto inflación, reservas y desempleo entra en el scoring**, y ninguna se mira *contra su
propia cota*: un `government_approval` clavado en 0 durante 40 meses produce exactamente el mismo
`hit` que uno que se mueve.

El seguimiento del hallazgo confirmó el valor del instrumento: rastrear el punto 1 en 1991-04 mes a
mes llevó al proxy de importaciones (`0.18 · PIB / 12`, ADR 012 §4) que hacía salir la
convertibilidad en el **mes 1** porque el modelo creía que Argentina importaba tres veces más de lo
real. **No era un coeficiente mal calibrado: era un dato que faltaba.** Ninguna función objetivo lo
hubiera encontrado, porque ninguna función objetivo puntúa importaciones.

### Por qué un comando y no otro script ad hoc

Porque la sonda ad hoc no es reproducible, no deja salida versionada, y sus seis arranques vivían en
un archivo temporal. El valor de la sonda es **comparar la corrida de hoy con la de la ronda
pasada**: "1983-12 pasó del mes 9 al mes 7", "2003-06 casi duplicó su horizonte". Eso exige una
salida estable en disco y un formato fijo. Además la conclusión del propio hallazgo fue explícita:
*"una sonda de este tipo debería correr en cada ronda"*.

---

## 2. Qué mide exactamente

Por escenario (un arranque histórico real) y sobre N semillas:

### 2.1 Terminación

`outcome` de cada semilla y **mes de terminación** (mediana, mínimo, máximo) contra dos referencias:

- los **meses pedidos** (`months` del escenario): cuántas semillas llegan enteras;
- **lo que pasó de verdad**, en texto libre en la tabla de escenarios (`expected`). La sonda **no
  puntúa** esa comparación: la imprime al lado para que la lea un humano. Puntuarla la convertiría
  en una validación con hipótesis implícita, que es justo lo que no es.

### 2.2 Saturación (el síntoma más valioso)

Para **cada una de las 21 variables de estado** y cada semilla: en qué mes toca por primera vez su
cota inferior o superior (las de `country.json → ranges`, las mismas que aplica
`world/state.py::clamp_state`) y **cuántos meses pasa ahí**. Se agrega por escenario como: fracción
de semillas que saturan, mes mediano del primer toque, meses medianos pegados a la cota y fracción
de la corrida que eso representa.

Es la medición que encontró el problema actual y es la razón principal de existir del comando. Una
variable que pasa la mitad de la corrida contra su cota, en todas las semillas, es una ecuación sin
término de recuperación, no un resultado del modelo.

### 2.3 Valores fuera de rango físico

Una tabla aparte, con cotas **deliberadamente más anchas** que las de `ranges` (desempleo > 40 %,
salario real fuera de `[10, 400]`, inflación mensual fuera de `[-100, 1000]`, PIB o reservas
negativos, porcentajes fuera de `[0, 100]`). Como `clamp_state` corre todos los meses, **estas cotas
no se pueden violar salvo que algo esté roto**: una violación es un bug (un camino que saltea el
clamp, un modo anual que clampea sólo al final del año, un `model_construct` sin validar), no un
resultado que discutir. Se reporta con variable, mes, semilla y valor.

### 2.4 Eventos y excepciones

Los eventos más frecuentes por escenario (fracción de semillas en las que aparecen, mes mediano de
la primera aparición) y **toda excepción**: una semilla que revienta se registra con su tipo y
mensaje y **no tumba el escenario**; un escenario que no arranca (fecha fuera del rango con series)
se registra y **no tumba la corrida**.

---

## 3. Qué NO mide

Esto es tan importante como lo anterior, porque la sonda es fácil de confundir con las otras dos:

- **No puntúa aciertos.** No hay `hit`, no hay error, no hay tasa. La columna "qué pasó de verdad"
  es texto para un humano; el comando no la compara programáticamente con nada.
- **No tiene hipótesis previa ni registro de hipótesis.** No hay `registration.json`: no hay nada
  que registrar antes de correr, porque no se está poniendo a prueba ninguna afirmación. Por eso
  **no reemplaza a `republica validate`**, cuyo valor está justamente en el protocolo de registro
  previo (`PLAN_ARGENTINA.md` §0.3).
- **No mide predictibilidad ni generaliza.** Unos pocos arranques elegidos a mano no son una
  muestra; no hay ventanas rodantes, no hay estratificación por características, no hay intervalos
  de confianza sobre ninguna tasa. Para eso está `republica backtest` (ADR 014), que corre cientos
  de ventanas. **La sonda no lo reemplaza ni lo resume.**
- **No compara calibraciones ni brazos.** Corre un solo brazo (los coeficientes que se le pidan).
  No hay control Aurora: el "valor de la calibración" lo mide A4, no esto.
- **No dice nada sobre Argentina.** Todo lo que sale describe el comportamiento del simulador
  arrancado desde estados iniciales argentinos. Vale la frase fija de `PLAN_ARGENTINA.md` §4, que
  el reporte imprime.
- **No prueba causalidad.** Que una variable sature en el mes 5 y el país colapse en el 25 es una
  pista sobre el mecanismo, no una explicación. El seguimiento de 1991-04 dejó claro que confirmar
  una de estas pistas requiere trazar la corrida a mano.

---

## 4. Los escenarios van en datos, no en código

`data/countries/<pais>/probe_scenarios.csv`, versionado, con cuatro columnas:

| columna | qué es |
|---|---|
| `label` | identificador corto del escenario (se usa en los nombres de archivo) |
| `start` | mes de arranque `YYYY-MM` |
| `months` | horizonte pedido |
| `expected` | **texto libre**: qué pasó de verdad |

Agregar un escenario es agregar una fila. No hay lista de escenarios en Python, ni siquiera como
default: sin el archivo, el comando falla y dice cuál falta. `expected` es deliberadamente texto y
no un campo estructurado: en cuanto se estructure, alguien va a querer puntuarlo, y entonces esto
deja de ser una sonda.

Los seis escenarios iniciales son los de la sonda ad hoc de `EMERGENCE_LOG.md`.

## 5. Salidas

`data/countries/<pais>/probe/<run_id>/`, igual que `backtest/<run_id>/` y `validation/<run_id>/`:

- `report.md` — las tablas de §2, la frase fija de honestidad y una sección "Qué no se puede
  concluir de esto";
- `summary.json` — lo mismo en estructurado, para diffear entre rondas;
- `series/<label>__seed<n>.csv` — **un CSV por semilla-escenario**, una fila por mes con las 21
  variables de estado, el `regime_mode`, los shocks activos y los eventos. Es lo que permite el
  trabajo de seguimiento (trazar mes a mes la corrida que más se aleja) sin volver a correr nada.

CLI:

```
republica probe --country argentina --calibration a7_by_regime --seeds 10 --run-id <id>
```

### Fechas fuera de rango

`republica run --country argentina --start` acepta cualquier mes desde 1961 (hay un fallback que
construye el estado inicial desde las series: `calibration/initial_states.py::flat_initial_state`),
pero fuera de ese rango falla. La sonda **maneja el error por escenario**: el escenario queda
marcado como `ERROR` con su mensaje en `report.md` y en `summary.json`, y los demás escenarios
corren igual. Un archivo de escenarios con una fecha inválida no tumba la corrida.

## 6. Tests

`tests/test_probe.py`, por debajo de 60 s:

1. El comando corre de punta a punta sobre un escenario chico (2 semillas, 12 meses) y produce
   `report.md`, `summary.json` y los CSV por semilla.
2. La detección de saturación marca una variable que satura y no marca una que no (sobre series
   sintéticas, sin correr el modelo).
3. Un escenario con fecha inválida se reporta como `ERROR` sin tumbar la corrida (se corre junto a
   uno válido y el válido termina bien).
4. Los escenarios se leen del CSV: un CSV con una fila nueva produce un escenario nuevo sin tocar
   Python.
5. La detección de rango físico marca un valor imposible y no marca uno normal.

---

## Notas de implementación

`src/republica/probe/` (`__init__.py`, `runner.py`, `report.py`, `__main__.py`), siguiendo el patrón
de `src/republica/backtest/`, más el subcomando `republica probe` en `cli.py` (que delega en el
mismo `run_probe`/`write_report` que `python -m republica.probe`). Tests en `tests/test_probe.py`
(11 tests, 1.5 s: solo uno corre el modelo, con 2 semillas y 12 meses).

El runner **no toca `world/`, `calibration/`, `backtest/`, `validation/` ni `ai/`**: arma la corrida
con `load_country_pack` + `flat_initial_state` + `load_calibrated_country` /
`load_calibrated_vectors_by_group` + `merge_structural_coefficients` + `historical_exogenous_series`
exactamente como lo hace `cli.py::run` con `--country/--start`, y reusa `HONESTY_SENTENCE` de
`calibration/run.py`. Lo único propio es la medición (`detect_saturation`,
`detect_physical_violations`) y el formato del reporte.

Dos niveles de tolerancia a fallas, los dos ejercitados por tests: una **semilla** que revienta se
registra con su excepción y no tumba el escenario (mismo criterio que `backtest/runner.py`); un
**escenario** que no arranca — típicamente `--start` fuera de 1961–2023 — se registra con su error
y no tumba la corrida. El path del archivo de escenarios se guarda relativo al repo, para que una
corrida de referencia commiteada no lleve la ruta del worktree de quien la corrió.

### Corrida de referencia

`data/countries/argentina/probe/main/`, generada con:

```
republica probe --country argentina --calibration a7_by_regime --seeds 10 \
    --run-id main --regime-transitions
```

10 semillas × 6 escenarios, **10,9 s** en total (498 meses-escenario). Estado del modelo en
`50da2e9` (el commit que reemplazó el proxy de importaciones por las series reales):

| escenario | pedidos | fin (mediana) | mín–máx | enteras | outcomes | qué pasó de verdad |
|---|---:|---:|---|---:|---|---|
| 1983-12 | 72 | **8** | 6–18 | 0/10 | `hyperinflation` 9, `collapse` 1 | hiperinflación en el mes 66 |
| 1991-04 | 120 | **44** | 30–120 | 1/10 | `collapse` 9, `survived` 1 | década de convertibilidad estable |
| 1998-01 | 60 | **41** | 38–48 | 0/10 | `collapse` 10 | default en el mes 47 |
| 2003-06 | 150 | **120** | 111–140 | 0/10 | `collapse` 10 | década de crecimiento |
| 2015-12 | 48 | **48** | 48–48 | 10/10 | `defeated` 10 | mandato completo, derrota en 2019 |
| 2019-12 | 48 | **48** | 48–48 | 10/10 | `defeated` 9, `hyperinflation` 1 | mandato completo, derrota en 2023 |

El diagnóstico del punto 1 de `EMERGENCE_LOG.md` **sigue en pie**: 1983-12 hiperinflaciona en el mes
8 contra el mes 66 real, y 1991-04 colapsa en el mes 44 contra 120 de convertibilidad. Las dos
ventanas de mandato (2015-12, 2019-12) llegan enteras en las 10 semillas. **Cero valores fuera de
rango físico en toda la corrida**, en los seis escenarios: no hay ningún camino que saltee
`clamp_state`. **Cero excepciones.**

**Saturación** (lo más clavado por escenario; mediana sobre 10 semillas):

| escenario | variable | cota | semillas | 1er mes | meses pegada | % de la corrida |
|---|---|---|---:|---:|---:|---:|
| 1983-12 | `institutional_confidence` | 0 | 10/10 | 3,0 | 5,5 | **72 %** |
| 1983-12 | `consumer_confidence` | 0 | 10/10 | 2,0 | 4,0 | 50 % |
| 1991-04 | `crime_perception` | 100 | 10/10 | 9,0 | 35,5 | **83 %** |
| 1991-04 | `social_tension` | 100 | 10/10 | 11,0 | 33,5 | 78 % |
| 1991-04 | `government_approval` | 0 | 10/10 | 18,5 | 27,5 | 62 % |
| 1998-01 | `crime_perception` | 100 | 10/10 | 10,0 | 31,5 | 78 % |
| 1998-01 | `social_tension` | 100 | 10/10 | 12,5 | 28,5 | 71 % |
| 2003-06 | `crime_perception` | 100 | 10/10 | 4,0 | 117,5 | **98 %** |
| 2003-06 | `social_tension` | 100 | 10/10 | 4,0 | 52,5 | 43 % |
| 2003-06 | `inequality` | 20 | 10/10 | 62,0 | 37,0 | 30 % |
| 2015-12 | `poverty` | 0 | 10/10 | 25,5 | 23,5 | 49 % |
| 2015-12 | `real_wage` | 200 | 10/10 | 31,0 | 16,0 | 33 % |
| 2019-12 | `poverty` | 0 | 10/10 | 22,5 | 26,5 | **55 %** |
| 2019-12 | `real_wage` | 200 | 10/10 | 26,0 | 22,0 | 46 % |

La primera pasada del comando ya agrega tres cosas que la sonda ad hoc no había visto:

1. **`crime_perception` clavada en 100 es la peor saturación del modelo**, no las cuatro variables
   del hallazgo original: 98 % de la corrida en 2003-06 (desde el mes 4, en las 10 semillas), 83 %
   en 1991-04, 78 % en 1998-01. Esa variable deja de transportar información casi en cuanto arranca
   la corrida.
2. **La saturación empieza mucho antes del final.** El hallazgo original solo miraba el valor
   *final*; con el primer mes de contacto se ve que en 1983-12 `institutional_confidence` toca 0 en
   el **mes 3** de una corrida que termina en el 8, y en 2003-06 `crime_perception` y
   `social_tension` tocan su cota en el **mes 4** de 120. La pregunta abierta del punto 2 de
   `EMERGENCE_LOG.md` ("habría que ver si la aprobación toca 0 **antes** del mes de terminación")
   queda contestada: sí, y por mucho.
3. **Hay saturación contra la cota "buena" también**, que nadie estaba mirando: en los dos
   escenarios que llegan enteros (2015-12 y 2019-12) `poverty` se clava en su **piso** (0) la mitad
   de la corrida y `real_wage` en su **techo** (200) un tercio, con `inequality` en su piso (20). No
   es solo que el bloque político se hunda: el bloque social también se va al otro borde y se queda
   ahí.

Nada de esto es una conclusión sobre Argentina ni sobre el mecanismo: son síntomas, que es
exactamente lo que la sonda produce (§3).
