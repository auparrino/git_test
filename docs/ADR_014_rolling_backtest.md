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
        "--country", country_id, "--calibration", calibration_run_id, "--run-id", run_id,
        "--from", str(from_year), "--to", str(to_year), "--horizons", horizons,
        "--seeds", str(seeds), "--workers", str(workers),
    ]
    if resume:
        args.append("--resume")
    raise SystemExit(backtest_main(args))
```

Sin identificadores de modelos de IA en el repo (regla del proyecto).
