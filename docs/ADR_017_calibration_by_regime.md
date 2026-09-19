# ADR 017 — Calibración por régimen cambiario, exclusión de coeficientes legacy sin señal y guarda numérica del modo anual

Estado: aceptado para implementar. Escrito ANTES de codear (convención del proyecto). Responde a dos
pendientes registrados en `docs/PLAN_ARGENTINA.md` §7 al cierre de la segunda iteración:

1. *"Los `Coefficients` legacy no reciben señal del objetivo macro y desbordan en modo anual →
   excluirlos del vector cuando macro está activo, o dar al modo anual su propio grupo"*.
2. *"El calibrado no supera a persistencia ni en train ni en holdout → calibrar por regímenes
   (peg/float/control) o por época, no un solo vector para 32 años"*.

Más un tercer pendiente menor que sale del `CALIBRATION_LOG` de A5b (`a3_main`, sin macro, ajusta
MEJOR el PBI que `a5b_macro` porque el PBI no está gobernado por la capa macro): una opción para
**ponderar las variables del objetivo**, sin cambiar el default.

Este ADR NO corre la calibración completa: define el mecanismo y deja el comando exacto (§8).

---

## 1. Diagnóstico 1 — los `Coefficients` legacy sin señal

`calibration/objective.py::simulate_from` corre SIEMPRE con `macro_coefficients` distinto de `None`
cuando el paquete tiene `features.macro_regime` (Argentina desde ADR 012). Con eso,
`engine/simulation.py::advance_month` llama a `world/economy.py::step_macro_economy` y **nunca** a
`step_economy`. Pero `build_parameter_space(include_macro=True)` mete igual los 97 campos de
`world/config.py::Coefficients` en el vector de CMA-ES.

Los campos de `Coefficients` que `step_macro_economy` NO lee y `step_economy` SÍ quedan, entonces,
**sin ninguna restricción del objetivo**: CMA-ES los mueve libremente (solo los frena la
regularización L2 con `lambda_reg = 0.01`, que es débil) porque no cambian ni una décima de la
pérdida. El resultado está medido: en `a5b_macro`, `rho_pi` (persistencia de la inflación del motor
legacy) terminó en **2.298** contra el 0.85 de Aurora — un AR(1) con coeficiente 2.3, o sea
explosivo por construcción.

Eso no importa mientras se corra en modo mensual con macro. Importa en `world/annual.py`, que usa
SIEMPRE `step_economy` (nunca el macro): el hallazgo de `docs/ADR_014_rolling_backtest.md`
("`OverflowError` sistemático del brazo calibrado en modo anual") es exactamente esto — las 135
ventanas anuales 1916–1960 del backtest `b1_a5b` perdieron el 100 % de sus semillas calibradas
(4050 de 4050) por `OverflowError` en `(1 + g_m/100)**12`.

**La lista concreta** (obtenida comparando las referencias `coeff.<campo>` del cuerpo de
`step_economy` contra las del cuerpo de `step_macro_economy`, y verificando que ningún otro módulo
del motor las lea — `society.py`/`politics.py`/`elections.py`/`perception.py` no las tocan):

| coeficiente | qué es en el motor legacy (`step_economy`, §4 del spec) |
|---|---|
| `rho_pi` | persistencia (AR(1)) de la inflación en la ecuación de precios legacy (§4.3) |
| `c_e` | pass-through del tipo de cambio a la inflación (§4.3) |
| `c_r` | efecto de `r_gap` sobre la inflación (§4.3) |
| `c_g` | efecto del `demand_gap` sobre la inflación (§4.3) |
| `c_f` | efecto del déficit sobre la inflación (§4.3) |
| `k_conf` | ganancia de la confianza institucional del bloque legacy (§4.6) |
| `k_tb` | ganancia del canal de balanza comercial legacy (§4.5) |
| `k_w` | ganancia del canal salarial legacy (§4.4) |

Son 8, y son todos de bloques que ADR 012 reemplazó entero: la ecuación de precios (`rho_pi`, `c_*`)
y los canales legacy de confianza/balanza/salarios (`k_*`). `step_economy` lee 44 campos de
`Coefficients`; `step_macro_economy` lee 36; la intersección (36) **se queda en el vector** — la
comparten los dos motores, así que la calibración con macro sí les da señal y sacarlos sería regalar
ajuste. Los ~53 campos restantes de `Coefficients` (sociedad, política, elecciones, percepción)
tampoco se tocan: los ejercitan `step_society`/`step_politics`/etc., que corren igual con macro
activo.

**Decisión 1**: `build_parameter_space(include_macro=True)` **excluye** esos 8. El vector pasa de
155 (97 + 58) a **147** (89 + 58). Los 8 excluidos quedan FIJOS en el valor de Aurora del paquete
(`data/countries/argentina/country.json → coefficients`) y se escriben con ese valor en el
`coefficients.json` de la corrida, para que una calibración macro siga siendo un objeto completo que
`world/annual.py` pueda usar sin desbordar.

Se eligió "excluirlos del vector" y no "darle al modo anual su propio grupo" (la otra opción del
PLAN) porque el modo anual no tiene función objetivo propia: el objetivo de la calibración puntúa
`h ∈ {1,3,6,12}` MESES contra series mensuales, y darle un grupo propio exigiría una segunda función
objetivo anual (otra ventana, otras series, otro protocolo de holdout) — un ADR entero, no un ajuste
del espacio de parámetros. Costo declarado de la opción elegida: **el modo anual corre con los
coeficientes legacy de Aurora, sin calibrar**, y eso hay que decirlo cada vez que se lea un backtest
anual.

## 2. Diagnóstico 2 — guarda numérica del modo anual

La exclusión de §1 arregla las calibraciones FUTURAS, no las ya escritas: `a5b_macro` tiene
`rho_pi = 2.298` grabado en su `coefficients.json` y sigue desbordando. Además, nada garantiza que
otra combinación de coeficientes (incluso de Aurora, con un estado inicial raro) no vuelva a hacerlo.

**Decisión 2**: guarda numérica explícita y CONTADA en `world/annual.py`. El modo anual aplica
`step_economy` 12 veces por turno-año y recién clampea el estado (`clamp_state`) al final del año —
o sea, dentro del año el estado puede crecer sin cota, a diferencia del modo mensual, que clampea
todos los meses. Se acota `g_m` (crecimiento mensual del producto, §4.1) a un **rango físico
`[-50, +50] % mensual`**: ±50 % mensual ya es absurdo (compuesto son −99.8 % o +12.875 % anual), así
que cualquier valor fuera de ese rango es ruido numérico, no economía.

El clamp NO es silencioso: se cuenta. `AnnualRecord.g_m_clamped` (clampeos de ese turno-año, sobre
12 sub-pasos posibles) y `AnnualHistory.g_m_clamped` (total de la corrida, también en la última
línea del JSONL). Una corrida anual con `g_m_clamped > 0` está corriendo contra la guarda, no contra
el modelo, y hay que leerla así.

**Dónde vive el clamp**: la expresión `(1 + g_m/100)**12` está en `world/economy.py`, no en
`world/annual.py`. Para no cambiar el modo mensual ni un byte (golden hashes de Aurora), se agrega a
`step_economy` un parámetro OPCIONAL `g_m_clamp: tuple[float, float] | None = None`, default `None`
= comportamiento idéntico al de siempre. La política (el rango, la constante, el contador y la
documentación) vive entera en `world/annual.py`; `economy.py` solo recibe una cota que por default
no existe. Es la intervención mínima que deja el clamp donde el pendiente lo pedía.

## 3. Diagnóstico 3 — un solo vector para 32 años

`a5b_macro` calibró 155 parámetros sobre 124 meses de arranque que cubren cuatro regímenes
cambiarios distintos (convertibilidad 1991–2002, flotación administrada 2002–2011, cepo 2011–2015,
flotación 2016–2019, cepo 2019–2023). `step_macro_economy` **ya trata esos regímenes con ramas de
código distintas** (ADR 012 §3: `float` interviene sobre la banda, `peg`/`crawl` defienden la
paridad y pueden salir forzados, `control` genera brecha). Pedirle a un solo vector que ajuste bien
las tres ramas a la vez es pedirle un promedio que no sirve para ninguna; el resultado medido es que
no supera a persistencia ni en train ni en holdout.

**Decisión 3**: `republica calibrate --by-regime` particiona los meses de arranque de train por el
régimen cambiario REAL de `data/countries/argentina/fx_regimes.csv` en `t0` y corre **un CMA-ES por
grupo**.

### 3.1 Grupos y por qué `crawl` va con `peg`

`fx_regimes.csv` tiene cuatro etiquetas: `crawl`, `peg`, `float`, `control`. Se usan **tres grupos**:

| grupo | etiquetas de `fx_regimes.csv` |
|---|---|
| `peg` | `peg`, `crawl` |
| `float` | `float` |
| `control` | `control` |

`crawl` se agrupa con `peg` **porque el motor ya los trata juntos**: `step_macro_economy` tiene una
sola rama `elif fx_regime in ("crawl", "peg")` (mini-devaluación administrada y paridad fija son el
mismo mecanismo de defensa con reservas, con `crawl` deslizando la paridad). No es una decisión de
gusto: calibrarlos por separado sería calibrar dos vectores para una única rama de código. Argumento
secundario: en el train `1992-01:2023-12` **no hay un solo mes de arranque `crawl`** (la banda
`crawl` del paquete es 1983-12:1991-03, entera en el holdout), así que un grupo `crawl` propio se
quedaría sin datos de entrenamiento.

### 3.2 Distribución de meses de arranque (stride 3, horizonte 12)

Train `1992-01:2023-12`, **124 meses de arranque**:

| grupo | meses de arranque | % |
|---|---:|---:|
| `float` | 54 | 43.5 % |
| `peg` (41 `peg`, 0 `crawl`) | 41 | 33.1 % |
| `control` | 29 | 23.4 % |

Holdout `1983-12:1991-12`, **29 meses de arranque**: los 29 son `crawl` → **el holdout completo cae
en el grupo `peg`**. Consecuencia declarada, importante para leer el reporte: el holdout NO evalúa
los vectores `float` ni `control`; mide la generalización del vector `peg` a una banda `crawl` que
nunca vio. Los otros dos vectores quedan SIN prueba de generalización alguna en este protocolo.

### 3.3 `default`

`coefficients.json` guarda además un vector `default`, que es **una copia del vector del grupo con
más meses de arranque de train** — con esta ventana y este stride, `float` (54 de 124). Se usa
cuando no se puede resolver un régimen para la fecha pedida (sin `--start`, sin `fx_regimes.csv`, o
una fecha fuera de todas las bandas). Se elige "el grupo con más meses" y no un promedio de los tres
porque un promedio de vectores no es un vector calibrado de nada: el punto medio entre dos óptimos
de ramas de código distintas no optimiza ninguna de las dos.

### 3.4 Estructura de `coefficients.json`

```jsonc
{
  "run_id": "...", "country_id": "argentina",
  "by_regime_groups": ["peg", "float", "control"],
  "default_group": "float",                  // el de más meses de train (§3.3)
  "regime_group_map": {"peg": "peg", "crawl": "peg", "float": "float", "control": "control"},
  "n_start_months_by_group": {"float": 54, "peg": 41, "control": 29},
  "by_regime": {
    "peg":     {"coefficients": {...}, "bimonetary": {...}, "macro": {...}},
    "float":   {"coefficients": {...}, "bimonetary": {...}, "macro": {...}},
    "control": {"coefficients": {...}, "bimonetary": {...}, "macro": {...}}
  },
  "default": {"coefficients": {...}, "bimonetary": {...}, "macro": {...}}
}
```

El formato VIEJO (un solo vector: `"coefficients"`/`"bimonetary"`/`"macro"` en la raíz) se sigue
leyendo tal cual: `load_calibrated_country` mira si existe la clave `"by_regime"` y elige el camino.
`a3_main`, `a5_macro` y `a5b_macro` cargan sin cambios.

### 3.5 Cómo se elige el vector

`load_calibrated_country(country_id, run_id, start=None)`:

- `coefficients.json` viejo → el único vector, siempre (el `start` se ignora).
- `coefficients.json` nuevo y `start = "YYYY-MM"` → `fx_regime_for(pack_dir, start)` →
  `fx_regime_group(...)` (§3.1) → ese vector; si el grupo no está en el archivo, `default`.
- `coefficients.json` nuevo y `start = None` → `default`.

`republica run --calibration <run_id>` pasa su `--start` y **loguea qué vector eligió** (grupo,
régimen de `fx_regimes.csv` y si cayó al `default`). Lo mismo hacen `backtest/runner.py` —que ya
tiene el `t0` de cada ventana, y en modo anual usa el `<year>-01` correspondiente— y
`validation/argentina.py` (con el `start` de cada prueba V1–V4).

### 3.6 Cambio de vector en caliente

El régimen cambiario SIMULADO puede cambiar dentro de una corrida: `step_macro_economy` fuerza la
salida de un `peg`/`crawl` con reservas bajas (`fx_regime_exit`, ADR 012 §3) y la corrida sigue en
`float`. Cuando eso pasa, seguir con el vector `peg` es usar coeficientes calibrados para una rama
de código que ya no se está ejecutando.

**Decisión**: intervención mínima en `engine/simulation.py`. `run()` acepta
`coefficients_by_fx_regime: dict[str, tuple[Coefficients, MacroCoefficients | None]] | None`
(default `None` = cero cambios en el camino de siempre). Con ese dict, al empezar cada mes
`advance_month` compara `fx_regime_group(sim.macro_state.fx_regime)` contra el grupo activo y, si
cambió, reemplaza `sim.country.coefficients` y `sim.macro_coefficients` por los del grupo nuevo y
deja el evento `fx_vector_switch:<grupo>` en el `MonthRecord` de ese mes. Son ~20 líneas y no tocan
ninguna fórmula de `world/`.

**Lo que NO se implementa, y su costo**: el cruce de una frontera de `fx_regimes.csv` por CALENDARIO
(p. ej. una corrida que arranca en 2011-01 bajo `float` y sigue después de 2011-11, cuando lo real
fue `control`) NO cambia el vector. La razón es que el motor tampoco cambia el régimen por
calendario: `world/countries.py::fx_regime_for` resuelve el régimen INICIAL y `MacroState.fx_regime`
solo se mueve por el mecanismo endógeno de salida (simplificación ya declarada en ADR 012). Hacerlo
cambiaría la DINÁMICA del modelo (qué rama de `step_macro_economy` corre), no solo qué coeficientes
usa: es un cambio de modelo, no de calibración, y no entra acá. **Costo**: en una corrida larga que
cruza una frontera histórica, el vector sigue al régimen simulado y no al real; una corrida de 48
meses desde 2011-01 usa el vector `float` los 48 meses aunque lo histórico haya virado a `control`
en el mes 11.

## 4. Reporte

`calibration/report.py` muestra, con las MISMAS tablas de hoy (RMSE normalizada + cola pesada +
"terminaron antes del horizonte", contra persistencia, Aurora sin calibrar y `a3_main`):

- **Una sección por grupo**, train y holdout, con el `n` de cada uno (un grupo sin meses de arranque
  en el holdout se imprime igual, con "sin dato", para que la ausencia sea visible).
- **Una sección agregada**, train y holdout, donde cada mes de arranque se puntúa con el vector de
  SU grupo y se agregan todos juntos — que es lo que hay que comparar contra `a5b_macro`.

## 5. Ponderación de variables del objetivo (`--weights`)

Hallazgo de `CALIBRATION_LOG` (A5b, holdout): `a3_main` (sin macro) ajusta MEJOR el PBI que
`a5b_macro` (h=12: 0.880 vs 2.354) porque la capa macro de ADR 012 no gobierna el PBI, y calibrar
155 parámetros sobre una pérdida dominada por precios/reservas/cambiario empeora las variables que
no dependen de esos mecanismos.

`republica calibrate --weights "inflation=2,gdp_growth=0.5"` multiplica el término de cada variable
en `scalar_objective` por su peso. **Default: todos los pesos en 1.0**, es decir, el escalar es byte
a byte el de hoy si no se pasa `--weights`. Los pesos se guardan en `coefficients.json` y se
imprimen en el reporte (una corrida con pesos no es comparable con una sin pesos, y tiene que
verse). Solo afecta el escalar que minimiza CMA-ES; las tablas del reporte siguen mostrando cada
variable sin ponderar.

## 6. Hipótesis registrada ANTES de correr

> **Por régimen, el calibrado iguala o supera a persistencia en inflación a h=12 en al menos 2 de 3
> grupos en train, y no empeora el holdout agregado respecto de `a5b_macro`.**

Operativa: "iguala o supera" = RMSE normalizada del brazo calibrado ≤ RMSE de persistencia en la
fila `inflación mensual / h=12` de la tabla de ese grupo, en train. "No empeora el holdout agregado"
= la RMSE de `inflación mensual / h=12` de la tabla agregada del holdout no es mayor que 4.369 (el
valor de `a5b_macro`, `docs/CALIBRATION_LOG.md`). Referencia de train de `a5b_macro`: calibrado
0.797 vs persistencia 0.687 (peor).

La hipótesis puede fallar y se reporta igual. Contra qué se la compara queda fijado acá, antes de
correr, para que no se elija el criterio después de ver el número.

**Advertencia de comparabilidad**: entre `a5b_macro` y esta ronda entró `exchange_rate_annual_
linked.csv` (A0c, otra rama), que le da dato de tipo de cambio al holdout `1983-12:1991-12` donde
antes los cuatro brazos quedaban "sin dato". La fila de inflación h=12 del holdout que fija la
hipótesis NO cambia por eso (la inflación ya tenía su propio fallback anual desde A5b), pero el
ESCALAR del objetivo y las filas de tipo de cambio del holdout sí: no son comparables uno a uno con
los de `a5b_macro`.

## 7. Tests

1. `build_parameter_space(include_macro=True)` NO contiene los 8 nombres de §1 y SÍ contiene los que
   ambos motores leen (assert sobre nombres concretos: `rho_pi`/`c_e`/`k_w` fuera, `a_r`/`b_res`/
   `p_i` dentro); `include_macro=False` los sigue teniendo todos.
2. Un `coefficients.json` de calibración macro trae los 8 excluidos con el valor de Aurora.
3. `coefficients.json` VIEJO (un vector) y NUEVO (`by_regime`) cargan los dos por
   `load_calibrated_country`.
4. Elección de vector por fecha: `1998-01` → `peg`, `2005-01` → `float`, `2013-01` → `control`,
   `1988-06` (`crawl`) → `peg`, `start=None` → `default`.
5. Clamp del modo anual: una corrida anual con el `rho_pi` explosivo de `a5b_macro` NO tira
   `OverflowError` y devuelve `g_m_clamped > 0`; con los coeficientes de Aurora, `g_m_clamped == 0`
   y la trayectoria es idéntica a la de antes del cambio.
6. `--weights` con todos los pesos en 1.0 da el MISMO escalar que sin pesos; con un peso distinto,
   uno distinto.

## 8. Corrida completa recomendada (la corre el orquestador, no este ADR)

```
uv run republica calibrate --country argentina \
  --train 1992-01:2023-12 --holdout 1983-12:1991-12 \
  --loss heavy --by-regime --budget-per-group 400 --stride 3 \
  --workers 4 --seed 42 --run-id a7_by_regime
```

**Tiempo estimado: ~45–60 min de pared con 4 workers.** La cuenta: `a5b_macro` hizo 418 evaluaciones
× 124 meses de arranque en 1913 s, o sea ~0.037 s por `(candidato, mes)` con 4 workers. Con
`--budget-per-group 400` son tres corridas de ~418 evaluaciones sobre 54 / 41 / 29 meses:
`418 × (54 + 41 + 29) × 0.037 ≈ 1918 s` (~32 min) de CMA-ES — el mismo trabajo total que
`a5b_macro`, porque la suma de los tres grupos es el train entero. El extra respecto de `a5b_macro`
es el REPORTE: cuatro bloques de tablas (tres grupos + agregado) × (train + holdout) × 4 brazos, en
vez de uno, más el holdout por grupo. Si hace falta que entre en menos de 30 min,
`--budget-per-group 250` y se declara.

`--quick` (`budget-per-group = 40`, `stride = 12`) es la prueba de humo del mecanismo, no una
calibración: con stride 12 los grupos quedan en 11 (`peg`) / 13 (`float`) / 7 (`control`)
meses de arranque de train y 8 / 0 / 0 de holdout (medido).

**Corrida probe de esta rama**: `a7_quick_probe` (ese mismo `--quick`, `--workers 2`) se corrió solo
para verificar el pipeline de punta a punta y se BORRÓ de `data/` antes del commit. No hay ningún
número de calibración en este ADR que venga de una corrida completa.

## 9. Notas de implementación

Escritas después de codear. Lo que salió distinto de lo planeado, y lo que no se hizo.

1. **La lista de los 8 se verificó, no se supuso.** Se extrajeron por programa las referencias
   `coeff.<campo>` del cuerpo de `step_economy` (44 campos) y de `step_macro_economy` (36), y la
   diferencia dio exactamente los 8 de §1 — con la intersección de 36 contenida en los 44 (el macro
   no lee ningún coeficiente que el legacy no lea). Después se grepearon los 8 en todo `src/` para
   confirmar que ningún otro módulo los toca.

2. **Colisión de nombres `rho_pi`.** `Coefficients.rho_pi` (ecuación de precios LEGACY, excluido) y
   `MacroCoefficients.rho_pi` (persistencia de ADR 012 §2, que SÍ se calibra) se llaman igual. En el
   código no hay ambigüedad porque `coefficients_from_vector`/`macro_from_vector` filtran por
   `Parameter.group`, pero sí la hubo al escribir el test: comparar el conjunto de NOMBRES del vector
   entero da un falso negativo. El test compara solo los nombres del grupo `"coefficients"`, con un
   comentario que lo explica.

3. **Dónde se fijan los 8 excluidos.** No alcanza con sacarlos del vector: `calibration/run.py` usa
   `load_country().coefficients` (el `country.json` de Aurora, no el de Argentina) como `base` de
   `coefficients_from_vector`, así que los excluidos habrían heredado el valor de Aurora genérico.
   `coefficients_from_vector` ahora los pisa con `excluded_legacy_values()` (el `country.json` de
   Argentina, cacheado) **cuando el espacio de parámetros es de modo macro** — detectado por la
   presencia del grupo `"macro"` en `params`, que es la misma señal que ya usaba
   `macro_from_vector`. Verificado en la corrida probe: los tres grupos salen con
   `rho_pi = 0.85`.

4. **El clamp anual arregla el `OverflowError` incluso con `a5b_macro` ya grabado.** Verificado:
   `python -m republica.backtest --country argentina --calibration a5b_macro --from 1920 --to 1925
   --horizons 12 --seeds 3` pasa de descartar el 100 % de las semillas del brazo calibrado a
   descartar 0 (`n_seeds = 3` en las seis ventanas). Con `a5b_macro` el contador da
   `g_m_clamped = 29` sobre 60 sub-pasos en 5 años, y el `gdp_growth` resultante queda pegado al
   techo (30 %) — es decir, el brazo calibrado de 1916–1960 **ahora tiene datos, pero son datos
   contra la guarda, no contra el modelo**. Es exactamente lo que el contador está para decir, y hay
   que leerlo así en cualquier backtest anual que use `a5b_macro`. Con una calibración hecha con la
   exclusión de §1 (o con Aurora) el contador da 0.

5. **Detección del clamp sin tocar `Aux`.** Se evaluó devolver un flag desde `step_economy`, pero
   `Aux` se serializa dentro del `MonthRecord` del modo mensual (`asdict(macro_aux)` y el bloque
   `aux`), así que agregarle un campo cambiaría el contenido del JSONL de todas las corridas. Se
   detecta comparando `aux.g_m` contra los bordes del rango. Falso positivo posible (un `g_m` que
   caiga exactamente en ±50.0 sin haber sido clampeado) y documentado en `_g_m_was_clamped`.

6. **El cambio de vector en caliente ocurre el mes SIGUIENTE a la salida de régimen.** El régimen
   nuevo se resuelve al final del mes en que `step_macro_economy` fuerza la salida, y el vector se
   evalúa al empezar cada mes, así que el mes de la salida se corre entero con el vector viejo.
   Medido en una corrida real desde 1998-01 con `--fx-regime auto`: `fx_regime_exit` en el mes 7,
   `fx_vector_switch:float` en el mes 8. Es deliberado (a principio de mes no hay forma de saber que
   la salida va a pasar) y está documentado en `_swap_fx_regime_vector`.

7. **El primer mes NO emite evento.** `_swap_fx_regime_vector` fija el grupo del régimen inicial en
   silencio: el llamador ya eligió el vector de arranque con `load_calibrated_country(start=...)`, y
   un `fx_vector_switch` en el mes 1 sería ruido en todas las corridas.

8. **`load_calibrated_vectors_by_group` devuelve `(Coefficients, MacroCoefficients)`, sin el
   `BimonetaryCoefficients`.** Con macro activo el canal bimonetario viejo está apagado, así que
   intercambiarlo no haría nada; y `BimonetaryCoefficients` lleva además `fx_regime_default`, que es
   estado inicial de la corrida y no se debe pisar a mitad de camino.

9. **Lo que NO se implementó** (ya anunciado en §3.6, repetido acá porque es la simplificación más
   grande de este ADR): el cruce de una frontera de `fx_regimes.csv` por CALENDARIO no cambia el
   vector. El vector sigue al régimen SIMULADO, no al histórico.

10. **El `budget` del `coefficients.json` con `--by-regime`** guarda el `--budget` nominal y agrega
    `budget_per_group`; `evaluations` y `wall_seconds` son la SUMA de los tres grupos. La
    `history.csv` de la raíz y el gráfico de convergencia son los del grupo `default`; cada grupo
    tiene su `history_<grupo>.csv`. Mezclar las tres curvas en una sola serie daría un gráfico sin
    sentido: son optimizaciones independientes con escalares no comparables entre sí (cada grupo
    suma sobre un conjunto distinto de meses).

11. **Corrida probe, borrada antes del commit.** `a7_quick_probe`
    (`--quick --by-regime --workers 2`, 40 evaluaciones por grupo, stride 12): **100 s de pared**,
    162 evaluaciones totales, grupos `peg` 11 / `float` 13 / `control` 7 meses de arranque de train
    y `peg` 8 / `float` 0 / `control` 0 de holdout. Sirvió para verificar el pipeline (el
    `coefficients.json` nuevo, el reporte con las cuatro secciones, `republica run --calibration` y
    el backtest), NO para sacar ninguna conclusión sobre el ajuste: con 40 evaluaciones y stride 12
    los números no significan nada. Se borró de `data/` junto con los dos backtests probe
    (`probe_annual`, `probe_byregime`).

12. **No se corrió la calibración completa.** La corre el orquestador con el comando de §8. La
    hipótesis de §6 sigue sin evaluar.
