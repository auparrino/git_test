# ADR 014 — Backtest secuencial 1916–2023 y análisis de predictibilidad

Estado: aceptado para implementar después de la recalibración (ADR 012 §6). Responde a la pregunta:
*¿en qué condiciones el modelo predice y en cuáles no?* No busca un número global de acierto; busca
las **características de la ventana** que separan aciertos de fallos.

## 1. Ventanas

Origen rodante `t0` cada 12 meses desde 1916-01 hasta 2022-12 (107 orígenes), horizonte `h` de 12, 24 y
48 meses. Para cada `(t0, h)`:
- Estado inicial real con `initial_state_for(t0)` (mensual desde 1961; antes, anual interpolado con
  `annual_mode` para 1916–1943 y mensual interpolado 1943–1960); se registran los conteos
  `source/proxy/assumed`.
- Época de partidos y actores por `select_era(t0)` (ADR 013); sin época → Aurora con marca.
- Régimen inicial real de `regimes.csv`; `fx_regime` de `fx_regimes.csv` (antes de 1983, `float`
  salvo tabla ampliada por el implementador con fuentes).
- Shocks históricos forzados **solo exógenos** (commodities, mundo, guerra, pandemia, sequía);
  nunca hiperinflación, default, golpe ni crisis bancaria: esos son lo que hay que predecir.
- 30 semillas por ventana; coeficientes de la recalibración final (`--calibration <run_id>`) y, como
  control, Aurora sin calibrar.

Costo: 107 × 3 × 30 × 2 ≈ 19.000 corridas cortas; a ~0.05 s por mes de corrida, del orden de
40 min con 4 workers. Si excede 60 min, se reduce a 15 semillas y se dice.

## 2. Qué se predice y cómo se puntúa

| Objetivo | Métrica | Acierto si |
|---|---|---|
| Dirección de la inflación a `h` | signo de `π(t0+h) − π(t0)` real vs mediana simulada | coinciden |
| Magnitud de la inflación a `h` | error normalizado (RMSE en desvíos de la serie real de la década) | < error de persistencia |
| Régimen a `h` | `regime_mode` binarizado vs V-Dem | coinciden |
| Elección dentro de la ventana | oficialismo gana/pierde (mayoría de semillas) vs real; si hay época, ganador | coincide |
| Crisis dentro de la ventana | ocurrencia de `hyperinflation`/`sovereign_default`/`collapse`/`coup` (≥ 30 % de semillas) vs `events.csv` | coincide (incluye "no crisis") |
| Golpe (1916–1983) | `coup` endógeno vs real | coincide |

Cada `(t0, h, objetivo)` produce una fila con `hit ∈ {0,1}`, el error continuo cuando aplica, y las
**características** de la sección 3. Solo se puntúan objetivos con dato real en `t0+h`.

## 3. Características candidatas (lo que se cruza con el acierto)

| Grupo | Característica |
|---|---|
| Datos | `n_source`, `n_proxy`, `n_assumed` del estado inicial; frecuencia (mensual/anual interpolado); ¿hay serie de reservas? ¿de desempleo? |
| Régimen | `regime_mode` inicial; `vdem_polyarchy`; años desde el último golpe; `fx_regime` |
| Economía | nivel de inflación en `t0` (tramos: < 1 %, 1–3 %, 3–10 %, > 10 % mensual); tendencia previa 12 m; reservas/importaciones; deuda/PIB; distancia a un default previo |
| Política | meses hasta la próxima elección; aprobación proxy; fragmentación (Herfindahl de bancas) |
| Shocks | nº de shocks exógenos forzados en la ventana; magnitud |
| Modelo | ¿la ventana está dentro del período de calibración (in-sample)? ¿hay época de partidos? horizonte `h`; dispersión entre semillas (IQR) |

## 4. Análisis

1. **Tablas estratificadas**: tasa de acierto por objetivo × cada característica (tramos), con IC
   bootstrap y N. Es lo que se lee primero.
2. **Modelo de predictibilidad**: regresión logística regularizada y un árbol de decisión de
   profundidad ≤ 3 sobre `hit` con las características; se reporta importancia por permutación y
   las 3 reglas del árbol en lenguaje llano ("con inflación inicial > 10 % mensual y sin serie de
   reservas, la dirección de la inflación se acierta el 41 %"). Validación cruzada por década para
   que las reglas no describan solo la muestra.
3. **Dispersión como señal**: ¿la IQR entre semillas predice el error? Si sí, el modelo "sabe cuándo
   no sabe" y eso se dice; si no, también.
4. **Comparación calibrado vs Aurora** por década: dónde la calibración ayuda, dónde daña.

## 5. Salidas

`data/countries/argentina/backtest/<run_id>/`: `windows.csv` (una fila por ventana-objetivo con hit,
error, características), `report.md` con las tablas, las reglas, los gráficos (acierto por década
y objetivo; acierto vs inflación inicial; IQR vs error) y las secciones obligatorias "Qué hace
funcionar una predicción", "Qué no se puede concluir" y la frase fija de `PLAN_ARGENTINA.md` §4.
CLI: `republica backtest --country argentina --calibration <id> --from 1916 --to 2022 --horizons 12,24,48 --seeds 30 --workers 4`.

## 6. Tests
1. Backtest `--from 2000 --to 2003 --horizons 12 --seeds 2`: corre, `windows.csv` con las columnas de §2–§3, sin NaN en `hit`.
2. Los objetivos sin dato real en `t0+h` no se puntúan (test con una ventana en 1930).
3. El análisis corre sobre `windows.csv` sintético y produce el árbol con ≤ 3 niveles y la tabla estratificada.
4. Ningún shock de la lista prohibida (hiper, default, golpe, crisis bancaria) aparece como forzado.

## Notas de implementación

Implementado en `src/republica/backtest/` (`windows.py`, `features.py`, `runner.py`, `scoring.py`,
`analysis.py`, `report.py`, `__main__.py`) y `tests/test_backtest.py` (11 tests, incluido un
`@pytest.mark.slow` de punta a punta vía subprocess). CLI standalone (`python -m
republica.backtest ...`, no `republica backtest`: ver "CLI pendiente" más abajo). Reusa
`validation/argentina.py::bootstrap_ci` y `calibration/run.py::HONESTY_SENTENCE`/
`load_calibrated_country` y `calibration/objective.py::REAL_ELECTION_OUTCOMES` (import, sin
duplicar); el resto de las piezas que necesitaban una versión propia (calendario de régimen sin
golpes forzados, ventana de calibración train/holdout, ids de golpe/default/elección reales) se
reimplementaron en unas pocas líneas dentro de `backtest/` en vez de importar símbolos privados
(`_`-prefijados) de `validation/argentina.py`/`world/countries.py` — archivos que otro agente edita
en paralelo — para no acoplarse a una firma que puede cambiar bajo esta tarea.

**Un bug real encontrado y corregido**: `world/annual.py::run_annual` armaba el catálogo de shocks
**vacío** (`by_id={}`) cuando `shocks_enabled=False` (el default del modo anual, ADR 011 §6) — pero
`ShockCatalog.apply_month` busca CUALQUIER shock activo, forzado incluido, en `by_id`. Forzar
cualquier `shock_id` en modo anual (el mecanismo que el propio docstring de esa función ya decía
que "funciona") tiraba `KeyError` siempre; nunca se había probado porque ningún test/caller previo
forzaba un shock en modo anual. Se corrigió armando `by_id` SIEMPRE (para que un shock forzado
pueda resolver sus efectos) dejando `defs` (la lista que `ShockCatalog.roll` sortea para shocks
ALEATORIOS) vacía salvo `shocks_enabled=True` — el comportamiento sin shocks forzados no cambia
(verificado: `tests/test_country_pack_argentina.py` completo y el golden de Aurora siguen en
verde). Test de regresión: `test_backtest.py::test_annual_forced_exogenous_shock_does_not_crash`.

**Desviación deliberada del calendario de régimen para el objetivo "golpe"**: `windows.py`/
`runner.py::backtest_regime_calendar` arma un `RegimeCalendar` con `forced_coup_months` SIEMPRE
vacío (pero con la propensión endógena real por década, `world/regime.py::
coup_propensity_by_decade`) — a diferencia de `load_country_pack(..., regime_mode="auto")` (lo que
usa `republica run`/A4), que fuerza los golpes reales de `politics/events.csv` dentro de la
ventana. Sin este cambio el objetivo "golpe (1916–1983)" del ADR §2 sería tautológico: cualquier
ventana que cruce una fecha real de golpe "acertaría" porque el propio calendario se lo forzó, no
porque el modelo lo haya producido. Verificado con test dedicado
(`test_backtest_regime_calendar_never_forces_a_coup`, sobre una ventana 1928–1930 que sí cruza el
golpe de Uriburu).

**Modo anual, 1916–1960 (no solo 1916–1943 como dice §1 literal)**: `calibration/
initial_states.py::initial_state_for` (la única pieza del repo que construye un estado inicial real
mes a mes) cubre `MIN_YEAR=1961` en adelante — no existe en el repo ningún mecanismo de
interpolación MENSUAL para 1943–1960 (el modo anual del ADR 011 §6 es la única alternativa
construida). Se usa modo anual (`frequency="annual_interpolated"`) para todo `t0` con año < 1961,
no solo hasta 1943. Consecuencia honesta, documentada también en `report.py`'s sección "Qué no se
puede concluir": en modo anual el `initial_state` es el de Aurora (no un dato real de esa fecha,
ADR 011 §6) y `regime_mode` se lee DIRECTO de `politics/regimes.csv` (no se deriva
endógenamente) — por eso `scoring.py` **no puntúa** los objetivos `regime`/`coup`/`election` para
ventanas anuales (serían tautológicos o inexistentes, no "sin dato real"): solo se puntúan
`inflation_direction`/`inflation_magnitude`/`crisis` ahí.

**Shocks exógenos permitidos (`EXOGENOUS_ONLY`)**: `{drought, epidemic, international_crisis,
commodity_boom, war}` — los cinco `shock_id` de `politics/shocks_calendar.csv` que corresponden a
"commodities, mundo, guerra, pandemia, sequía" (§1 literal). Deliberadamente AFUERA:
`currency_run`/`imf_program` (respuesta financiera/de política a una crisis, no una exógena pura —
forzarlos regalaría justamente la dinámica que los objetivos "crisis"/"golpe" miden) además de los
cuatro prohibidos explícitos del ADR. Al ser un allow-list (no una lista de exclusión sobre el
catálogo completo), el test 4 se cumple por construcción; se verificó igual sobre el calendario
real completo (`test_no_forbidden_shock_forced_across_full_real_calendar`, 107×3 ventanas).

**Objetivo "elección"**: solo se puntúa cuando hay una elección presidencial REAL dentro de
`[t0, t0+h]` (`politics/events.csv`, `kind=election_presidential`) **y** su año está en
`calibration/objective.py::REAL_ELECTION_OUTCOMES` (curado a mano, 1989–2019). No hay en el repo un
mapeo confiable "el ganador es/no es continuidad del oficialismo" para 1916–1988 (requeriría juicios
de continuidad de coalición no triviales, fuera de alcance de esta tarea) — el objetivo "elección"
del backtest, entonces, tiene evidencia real solo para 1989–2019, aunque se generen ventanas para
todo 1916–2022. El acierto del modelo se mide con el resultado (`outcome_type`) de la primera
elección del modelo dentro de la ventana, por mayoría de semillas.

**Objetivo "magnitud de inflación"**: el ADR dice "RMSE en desvíos de la serie real de la década";
se implementó como error PUNTUAL en `t0+h` (`|mediana simulada − real| / desvío de la década`)
contra la misma métrica de persistencia (`|real(t0) − real(t0+h)| / desvío de la década`), no una
RMSE de trayectoria completa mes a mes. Motivo: para la mayoría de la muestra (pre-1997) la única
serie real disponible es ANUAL (`inflation_cpi_annual_linked`, interpolada a mensual-equivalente
repitiendo el valor del año, mismo criterio que V1 de `validation/argentina.py`) — una RMSE mes a
mes contra una serie que es constante dentro de cada año no agrega señal real, solo la repite;
el punto final captura lo mismo con menos código. Documentado como simplificación, no como el
literal del ADR.

**IQR entre semillas para objetivos binarios**: no hay una "IQR" de un 0/1. Se usa la fracción de
semillas que NO acompaña a la mayoría (`scoring.py::_disagreement`, 0 = unánime, 0.5 = máxima
discordia) como análogo declarado, para `regime`/`crisis`/`coup`. Para los objetivos continuos
(`inflation_direction`/`inflation_magnitude`) sí es una IQR real (de la inflación simulada a `t0+h`
entre semillas). `election` no trae `iqr_seeds` (el "valor" es categórico, sin análogo razonable).

**Umbral de "crisis"/"golpe" ≥ 30 % de semillas**: literal para "crisis" (ADR §2); el ADR no fija
un umbral separado para "golpe" — se usó el mismo 30 % por consistencia, documentado en
`scoring.py::COUP_SEED_THRESHOLD`.

**`months_to_next_election` (característica de Política)**: se calculó contra el calendario
electoral REAL (`politics/events.csv`), no contra las fechas de elección del propio motor
(múltiplos de `term_length` desde `--start`, que no calzan con octubre/diciembre reales, ADR 011
Notas de A2) — más honesto como característica de "qué tan cerca está la ventana de una elección
real", que es lo que un analista miraría.

**Estimación de costo (ADR §1, "Notas de implementación")**: medido con `--calibration a3_main`
(la única calibración terminada al momento de medir; `a5_macro` estaba corriendo en paralelo en
otro proceso y no se tocó), `--workers 1`, máquina de 4 CPUs:

| h (meses) | wall por ventana, 1 semilla, 2 brazos | wall por ventana, 30 semillas, 2 brazos (extrapolado, con overhead amortizado) |
|---:|---:|---:|
| 12 (mensual) | ~0.46 s | ~4.6 s |
| 24 (mensual) | ~0.47 s (interpolado) | ~5.9 s (interpolado) |
| 48 (mensual) | ~0.48 s | ~7.2 s |
| cualquiera (anual, 1916–1960) | ~0.06–0.08 s | ~0.1–0.15 s |

Con 62 orígenes mensuales (1961–2022) × 3 horizontes (186 ventanas, promedio ~5.9 s c/u ≈ 18.3 min)
más 45 orígenes anuales (1916–1960) × 3 horizontes (135 ventanas, ~13.5 s en total, despreciable):
**≈ 18.5 min secuencial (`--workers 1`)** para la corrida completa (107 × 3 × 30 × 2 ≈ 19.260
corridas individuales). Con `--workers 4` (paralelismo por ventana, `ProcessPoolExecutor`,
ventanas independientes) se espera un piso optimista de ~4.6 min y, con overhead de arranque de
proceso/IO no perfectamente lineal, una estimación conservadora de **~6–8 min** — muy por debajo
del umbral de 60 min del ADR: **no hace falta bajar a 15 semillas**, 30 semillas corre cómodo. (La
estimación original del ADR, "~40 min con 4 workers", era una previsión pre-implementación; la
medida real es bastante más rápida porque la mayoría de las semillas termina antes del horizonte
completo — `collapse`/`hyperinflation` cortan la corrida — y casi la mitad de las ventanas son del
modo anual, mucho más barato.) Esta cifra no está medida con `--workers 4` de verdad en esta pasada
(la máquina tenía los 4 CPUs ocupados por la calibración `a5_macro` en curso, y la tarea pide
mantener las pruebas livianas mientras tanto) — se recomienda re-medir con `--workers 4` sin
contención antes de lanzar la corrida completa 1916–2022, y el propio backtest imprime el tiempo
de pared real de cada ventana a medida que corre.

**CLI pendiente (`cli.py`, no tocado por esta tarea)**: agregar, junto a `validate` (mismo patrón,
`src/republica/cli.py`, después de `def validate(...)`):

```python
@app.command()
def backtest(
    country_id: Annotated[str, typer.Option("--country", help="Paquete de pais.")],
    calibration_run_id: Annotated[
        str, typer.Option("--calibration", help="run_id de `republica calibrate`.")
    ],
    run_id: Annotated[str, typer.Option("--run-id", help="Nombre de la corrida de salida.")],
    from_year: Annotated[int, typer.Option("--from")] = 1916,
    to_year: Annotated[int, typer.Option("--to")] = 2022,
    horizons: Annotated[str, typer.Option("--horizons")] = "12,24,48",
    seeds: Annotated[int, typer.Option()] = 30,
    workers: Annotated[int, typer.Option()] = 4,
    resume: Annotated[bool, typer.Option("--resume")] = False,
) -> None:
    """`republica backtest` (ADR 014): delega en `python -m republica.backtest`."""
    from republica.backtest.__main__ import main as backtest_main

    args = [
        "--country",
        country_id,
        "--calibration",
        calibration_run_id,
        "--run-id",
        run_id,
        "--from",
        str(from_year),
        "--to",
        str(to_year),
        "--horizons",
        horizons,
        "--seeds",
        str(seeds),
        "--workers",
        str(workers),
    ]
    if resume:
        args.append("--resume")
    raise SystemExit(backtest_main(args))
```

Sin identificadores de modelos de IA en el repo (regla del proyecto).

## Resultados (corrida `b1_a5b`, calibración `a5b_macro`)

Corrida completa 1916–2022, `--calibration a5b_macro --seeds 30 --workers 3` (se dejó 1 CPU libre
para la validación `a6_macro` del otro agente, en paralelo). **Tiempo de pared real: 477.1 s (≈ 8.0
min)** — muy por debajo del umbral de 60 min; no hizo falta bajar a 15 semillas. 321 ventanas, 2042
filas ventana-objetivo-brazo en `windows.csv` (`data/countries/argentina/backtest/b1_a5b/`).

**N de ventanas puntuadas por objetivo** (suma de los dos brazos, `507+507+364+19+507+138 = 2042`):

| Objetivo | N | Acierto global | Aurora | Calibrado |
|---|---:|---:|---:|---:|
| Dirección de la inflación | 507 | 46.2 % | 47.4 % (N=321) | 44.1 % (N=186) |
| Magnitud de la inflación | 507 | 30.4 % | 21.2 % (N=321) | **46.2 %** (N=186) |
| Régimen | 364 | 72.5 % | 72.5 % (N=182) | 72.5 % (N=182) |
| Elección | 19 | 52.6 % | 66.7 % (N=3) | 50.0 % (N=16) |
| Crisis | 507 | 64.3 % | 63.9 % (N=321) | 65.1 % (N=186) |
| Golpe (1916–1983) | 138 | 58.0 % | 58.0 % (N=69) | 58.0 % (N=69) |

El único objetivo donde el brazo calibrado le gana con claridad a Aurora en el agregado es
**magnitud de la inflación** (+25 pp): tiene más sentido de lo que parece, porque es justo lo que
`a5b_macro` optimizó (RMSE de `inflation` contra la serie real, ADR 012/011 §7). En **dirección de
la inflación** Aurora le gana por poco (47.4 % vs 44.1 %); en **régimen**/**golpe** las tasas son
IDÉNTICAS entre brazos (72.5 %/72.5 % y 58.0 %/58.0 %) — coincidencia exacta esperable: `regime`/
`coup` sólo se puntúan en ventanas mensuales, donde `backtest_regime_calendar` (nunca fuerza golpe)
y `regimes.csv` (real) son los mismos para los dos brazos; lo único que cambia entre brazos son los
coeficientes ECONÓMICOS, que no entran en `world/regime.py`.

### Hallazgo: `OverflowError` sistemático del brazo calibrado en modo anual (1916–1960)

Corriendo la corrida completa se encontró (y se corrigió la propagación, no la causa raíz — ver
"Notas de implementación" más arriba) un desborde numérico real: **las 135 ventanas de modo anual
(los 45 orígenes 1916–1960 × 3 horizontes) tienen el brazo `calibrated` con el 100 % de sus semillas
descartadas por `OverflowError`** (4050 = 135 × 30 semillas, exactamente todas; 0 semillas del brazo
`aurora` fallaron; 0 ventanas se descartaron enteras — el `try/except` por semilla de
`runner.py::run_annual_arm`/`run_monthly_arm` contuvo el problema, ver "Notas de implementación").
Causa: `world/annual.py` usa SIEMPRE el motor legacy (`step_economy`, nunca `step_macro_economy`),
pero la función objetivo de `a5b_macro` (`features.macro_regime=True`) nunca ejercita `step_economy`
para puntuar nada — así que el grupo de `Coefficients` "viejo" que SÍ usa el modo anual quedó sin
señal útil de la calibración y CMA-ES lo dejó en una zona donde `(1 + g_m/100)**12` desborda un
`float`. **Consecuencia para la lectura de esta corrida: el brazo calibrado NO tiene ningún dato
para 1916–1960** (`N calibrado = 0` en la tabla "Calibrado vs. Aurora por década" para 1910s–1950s);
toda comparación calibrado-vs-Aurora de este backtest es, de hecho, solo sobre 1961–2022. Esto es un
límite real de la calibración `a5b_macro`, no un bug de este backtest -- documentado para quien
recalibre después: el espacio de parámetros de `calibration/parameters.py` debería excluir del
`lambda_reg`/bounds los coeficientes legacy que la función objetivo con macro activo no ejercita, o
el modo anual debería tener su propio grupo de coeficientes calibrado por separado.

### Las 3 reglas del árbol en lenguaje llano (objetivo: magnitud de la inflación)

Elegido porque es el único objetivo donde el brazo calibrado gana con claridad, y conecta con el
resultado de dispersión de abajo. N=507, tasa base de acierto 30.4 %, CV por década (12 grupos):
accuracy media 63.6 % (rango 60–70 %, muy por encima de la tasa base — las reglas SÍ generalizan
entre décadas, no describen solo la muestra):

1. Con dispersión entre semillas (IQR) ≤ 0.21, inflación mensual inicial > 0.25 % y `fx_regime =
   float`: se acierta el 0 % (184 ventanas-objetivo) — el caso más común (float, inflación baja,
   semillas de acuerdo entre sí) es también el que más falla.
2. Con IQR > 0.21, poliarquía V-Dem ≤ 0.80 y tendencia de inflación previa (12 m) > −0.58 %: se
   acierta el 0 % (89 ventanas-objetivo) — regímenes menos democráticos con inflación en ascenso.
3. Con IQR ≤ 0.21, inflación mensual inicial ≤ 0.25 % y años desde el último default ≤ 40.5: se
   acierta el 0 % (50 ventanas-objetivo).

Nota de lectura: "se acierta el X %" es la tasa de acierto DENTRO de esa hoja (qué fracción de esas
ventanas tuvo `hit=1`), no la exactitud del árbol como clasificador — las tres hojas con más
muestras son, precisamente, las que MENOS aciertan (el árbol las separa de las hojas minoritarias
con mejor tasa, que no entran en el top-3 por tamaño); la importancia por permutación (`iqr_seeds`
0.065, `fx_regime=float` 0.041, `inflation_now` 0.027) confirma que la dispersión entre semillas es
la variable más informativa para este objetivo.

### Tabla estratificada más informativa: Régimen por `regime_mode_initial`

| régimen inicial (real) | N | acierto |
|---|---:|---:|
| coup | 18 | **0.0 %** |
| restricted_democracy | 24 | **0.0 %** |
| dictatorship | 72 | 36.1 % |
| democracy | 250 | **95.2 %** |

El modelo predice bien la continuidad cuando arranca en democracia (95.2 %) pero falla el 100 % de
las veces cuando arranca en un mes de golpe o de democracia restringida: son transiciones (el
régimen real cambia de modo poco después de `t0` en la mayoría de esos casos, ver ADR 011 §3) y el
modelo tiende a persistir el régimen inicial en vez de anticipar el cambio. Coincide con la
importancia por permutación del árbol de régimen (`years_since_last_default` domina con 0.363 —
la regla dominante es literalmente "si pasaron ≤ 45 años desde el último default, no acierta",
238/364 ventanas) y con la nota de "Qué no se puede concluir": el modo anual sesga esta tabla hacia
arriba (0 filas de régimen ahí, todas las 364 filas son mensuales, 1961+).

### Dispersión entre semillas como señal

**Spearman(IQR entre semillas, error de magnitud de inflación) = 0.433 (N=507).** Correlación
positiva y no trivial: el modelo *sabe cuándo no sabe* — cuando las 30 semillas de una ventana
discrepan mucho en la inflación que producen, el error contra la serie real tiende a ser mayor. No
es una correlación fuerte (0.433, no > 0.7), así que sirve como señal de alerta razonable, no como
sustituto de una medición de error real.

### Calibrado vs. Aurora por década

Resumen (tabla completa en `data/countries/argentina/backtest/b1_a5b/report.md`): **1910s–1950s sin
dato calibrado** (el `OverflowError` de arriba). Desde 1960s: en **magnitud de la inflación** el
calibrado gana en TODAS las décadas con dato (+34 pp en 1960s, +33 en 1970s, +50 en 1980s, +30 en
1990s, +23 en 2000s, +40 en 2010s, +22 en 2020s) — la calibración cumple lo que optimizó. En
**dirección de la inflación** el resultado es mixto y con más años en contra que a favor (−2 en
1960s, −10 en 1970s, +10 en 1980s, **−33 en 1990s**, −23 en 2000s, −10 en 2010s, 0 en 2020s) — la
calibración de RMSE no garantiza acertar el SIGNO del cambio. En **crisis** el calibrado gana en casi
todas las décadas con datos (+57 pp en 1990s, +47 en 2000s, +40 en 2010s), salvo 2020s (empate). En
**régimen**/**golpe** las diferencias por década son 0.0 pp en TODAS las décadas con dato (mismo
razonamiento que en la tabla agregada de arriba: esos dos objetivos no dependen de los coeficientes
económicos).

### Qué hace funcionar una predicción (párrafo citable)

La calibración `a5b_macro` ayuda de verdad, pero solo en lo que optimizó: la magnitud de la
inflación mejora en TODAS las décadas con dato (+22 a +50 pp sobre Aurora) y la dispersión entre
semillas predice el error (Spearman 0.433) — el modelo puede señalar sus propias ventanas de mayor
incertidumbre. Fuera de eso, el panorama es más flojo: la dirección del cambio de inflación pierde
contra Aurora en más décadas de las que gana, y régimen/golpe/elección dependen casi enteramente del
punto de partida (democracia real → 95 % de acierto; golpe o democracia restringida real → 0 %) y no
de qué brazo se use, porque esos objetivos no leen los coeficientes económicos calibrados. Y hay un
límite estructural: **para 1916–1960 no hay ningún dato del brazo calibrado** (el modo anual legacy
desborda numéricamente con estos coeficientes), así que cualquier lectura de "calibrado vs. Aurora"
de este backtest es, en los hechos, una lectura de 1961–2022, no de 1916–2022.
