# Resultados de Fase 9 — Modelo sustituto, active learning, early-warning, clustering

Corrida real de referencia (ADR 009): 60 semillas × 48 meses, `brain = rules`, todas las features
prendidas. Los artefactos (`data/ml/*.joblib`/`*.csv`/`*.parquet`/`*.duckdb`) no se versionan (ver
`.gitignore`); se reproducen con los comandos `republica ml ...`/`republica experiment ...` reales
de cada sección (hallazgo #5 de REVIEW_003: esta sección citaba un "script" que no existe en el
repo -- son estos comandos, ejecutados a mano, uno por uno). Se commitea
`data/ml/manifest_example.json` como copia de referencia del manifest real del sustituto.

Estos resultados describen el comportamiento de República Artificial bajo sus reglas; no son
evidencia sobre economías reales.

## 1. Dataset

- Fuente: 60 corridas de `rules`, 48 meses, todas las features (`data/ml/runs_rules/<semilla>.jsonl`).
- Filas: 78.792 (60 × 48 × 28 actores no-presidente).
- Columnas: ver `docs/ADR_009_surrogate_ui.md` §2 y `ml/dataset.py::dataset_columns()`.
- Comando real (genera las 60 corridas; los defaults de `country.json` ya prenden todas las
  features):
  ```
  for s in $(seq 0 59); do
    republica run --seed "$s" --months 48 --out "data/ml/runs_rules/$s.jsonl"
  done
  republica ml dataset data/ml/runs_rules --out data/ml/decisions.csv
  ```

## 2. Sustituto (`ml/surrogate.py`)

```
republica ml train --runs data/ml/runs_rules --brain rules --out data/ml/surrogate_rules.joblib
```

Split 70/15/15 por `(fuente, semilla)` (hallazgo #2 de REVIEW_003: una sola fuente acá --
`data/ml/runs_rules/`, las 60 corridas de `rules` -- así que da lo mismo que partir por semilla
sola: 42 train seeds 0–41 / 9 val seeds 42–50 / 9 test seeds 51–59; el fix importa cuando se
combinan VARIAS fuentes, ver §5). Métricas por rol, del `manifest.json` real
(`data/ml/manifest_example.json` es una copia):

| Rol | n_train | position_acc (val) | position_f1_macro (val) | intensity_mae (val) | jaccard multilabel (val) | position_acc (test) |
|---|---:|---:|---:|---:|---:|---:|
| business | 5.850 | 0.999 | 0.928 | 0.006 | 0.999 | 0.999 |
| economy_minister | 1.950 | 1.000 | 1.000 | 0.007 | 0.999 | 1.000 |
| governor | 15.600 | 0.999 | 0.500 | 0.012 | 0.999 | 0.999 |
| social_bloc | 9.750 | 0.998 | 0.666 | 0.014 | 0.996 | 0.997 |
| union | 3.900 | 0.995 | 0.499 | 0.016 | 0.996 | 0.993 |

**Solo 5 de los 8 roles con actores no-presidente entrenaron un pipeline propio** (no 9: `president`
no tiene decisión propia vía `decision_actors`). `media`/`central_bank` se excluyen por diseño
(fórmula cerrada sin ruido, ADR 009 Notas de implementación punto 6); `party` se excluyó porque, con
`rules` y estos pesos/umbrales, **nunca** cruza los umbrales de apoyo/oposición ni junta el mínimo
para negociar en las 60 semillas de entrenamiento — `position` es `"neutral"` en 14.070/14.070 filas
de `party` (un hallazgo genuino sobre la dinámica simulada, no un error de extracción, ver ADR 009
Notas de implementación punto 6). Los 3 roles sin pipeline propio caen automáticamente a un
`RuleBasedActor` interno dentro de `SurrogateActor` (agreement = 1.0 en esos roles, por
construcción).

Notar el `position_f1_macro` bajo de `governor`/`union` pese a accuracy > 0.99: la clase `neutral`
domina fuertemente el dataset (desbalance de clases, ver §7) y F1-macro promedia sin ponderar por
soporte — las clases minoritarias (`negotiate`, a veces `oppose`) cuestan más al macro-F1 que a la
accuracy agregada.

### Agreement rate (DoD ≥ 0.85) — y por qué ese número solo no alcanza (hallazgo #1)

```
republica ml evaluate --model data/ml/surrogate_rules.joblib --seeds 1000:1015 --months 48
```

Semillas held-out 1000–1014 (nunca vistas en entrenamiento ni en val/test), 48 meses, `surrogate`
vs `rules`, comparando `position` acción a acción (actor, mes) sobre las dos corridas completas
(que divergen mes a mes: ver §7). `evaluate_surrogate` reporta CUATRO números, no uno (hallazgo #1
de REVIEW_003: contra actores por reglas, `position = neutral` en el 98.75 % de las filas del
dataset de entrenamiento -- ver §7 -- así que `agreement_rate` solo, sin baseline, es casi
trivial):

| Métrica | Valor | Sobre |
|---|---:|---|
| `agreement_rate` | **0.9986** | 20.160 pares (actor, mes), todos los roles |
| `majority_baseline` | **0.9959** | las MISMAS 20.160 (actor, mes) -- lo que lograría un predictor CONSTANTE (la posición más frecuente) |
| `agreement_ml_roles_only` | **0.9980** | 13.680 (actor, mes) de los 5 roles con pipeline propio (excluye `media`/`central_bank`/`party`, que delegan a reglas) |
| **`balanced_agreement`** | **0.6707** | **82** (actor, mes) donde `rules` dio `position != neutral` -- la métrica INFORMATIVA |

`n_missing_actor_months = 0` (hallazgo #7: ninguna de las 15 semillas tuvo divergencia de longitud
entre la corrida `rules` y la corrida `surrogate` en esta ventana -- ver `run_length_delta` más
abajo).

**Lectura honesta:** `agreement_rate` (0.9986) y `majority_baseline` (0.9959) están a 0.0027 de
distancia -- casi toda la "precisión" del sustituto en el número agregado es la clase mayoritaria
(`neutral`) sola, no algo que el modelo haya aprendido. La métrica que sí mide si el sustituto
distingue `support`/`oppose`/`negotiate` es `balanced_agreement`, restringida a las 82 (actor, mes)
donde `rules` NO fue neutral: **0.67**, bastante más abajo. Con actores por reglas (deterministas
dado el estado del mundo, sin el ruido/creatividad de un LLM) el problema de imitar `position` es
casi trivial en el caso general (predecir "neutral" casi siempre) y solo se vuelve interesante --
y bastante más difícil -- en el 0.4 % de casos donde el actor realmente toma partido. El sustituto
recién sería una prueba exigente de verdad imitando a un `brain = llm:...` (ADR 009 secc. 9,
deliverable no cubierto en esta fase: no hay Ollama en este entorno, mismo motivo que ADR 007
secc. 8 punto 20), donde `position != neutral` sería la norma, no la excepción.

Por rol (`agreement_rate` de siempre, no balanceado -- `media`/`central_bank`/`party` en 1.000 por
construcción: delegan a un `RuleBasedActor` interno):

| Rol | agreement |
|---|---:|
| business | 0.998 |
| central_bank | 1.000 |
| economy_minister | 0.997 |
| governor | 0.999 |
| media | 1.000 |
| party | 1.000 |
| social_bloc | 0.997 |
| union | 0.997 |

## 3. Active learning (`ml/active.py`)

Sin comando `republica ml` dedicado (mide `fallback_rate` variando el umbral de un
`ActiveLearningActor` sobre las mismas semillas, no una sola llamada): medido invocando
`ActiveLearningActor`/`republica.engine.simulation.run` directo desde un script Python, con el
mismo modelo de `data/ml/surrogate_rules.joblib` (§2) como brain de base y `rules` como respaldo.
`fallback_rate` a 3 umbrales de confianza, 5 semillas held-out (3000–3004), 24 meses, con el modelo
REAL de 60 semillas:

| Umbral | fallback_rate | n acciones |
|---|---:|---:|
| 0.3 | 0.000 | 3.360 |
| 0.6 | 0.000 | 3.360 |
| 0.9 | 0.000 | 3.360 |

**Con este modelo real, la confianza de `position` satura cerca de 1.0 en casi todas las
predicciones** (consistente con los `position_accuracy` > 0.99 de la tabla anterior: `rules` es casi
determinista dado el input, así que el clasificador aprende una función casi sin incertidumbre) — a
diferencia de lo que un umbral de 0.99 lograría con un modelo más incierto, acá ni 0.9 alcanza para
forzar el respaldo. **La lógica de umbral en sí está verificada por separado, de forma determinista**,
en `tests/test_ml_ui.py::test_active_learning_threshold_high_always_falls_back`/
`test_active_learning_threshold_zero_never_falls_back` (un `SurrogateActor` de prueba con confianza
controlada a mano: 0.99 de umbral → `fallback_rate = 1.0`; 0.0 de umbral → `fallback_rate = 0.0`,
cumpliendo el DoD 4 literal sobre la mecánica de `ActiveLearningActor`, independiente de qué tan
confiado esté un modelo real particular). Documentado como hallazgo, no como falla: el active
learning SÍ dispara con un umbral alto si el modelo real llega a tener casos inciertos (roles con
`position_f1_macro` más bajo, como `union`/`governor`, tienen más chances de cruzar el umbral en
casos límite que no cayeron en estas 5 semillas puntuales).

## 4. Throughput: `surrogate` vs `rules`

Tampoco tiene comando `republica ml` dedicado (es una comparación de tiempo de
`republica.engine.simulation.run` con `default_brain="rules"` vs `default_brain=f"surrogate:
{modelo}"`, cronometrada a mano con `time.perf_counter()` -- el mismo patrón que
`tests/test_ml_ui.py::test_surrogate_throughput_proxy`, a mayor escala). 30 corridas de 48 meses
cada una, modelo real de 60 semillas (semillas 2000–2029, no usadas en entrenamiento):

| | `rules` | `surrogate` |
|---|---:|---:|
| Tiempo total | 6.46 s | 220.98 s |
| Corridas/seg | 4.64 | 0.136 |
| Proyección 1.000 corridas | ~23 s | **~123 min** |

**El sustituto corre ~34× más lento que `rules`** en esta implementación — por encima del "no más de
5×" que sugiere ADR 009 secc. 3. La causa medida: `SurrogateActor.decide()` llama a
`predict`/`predict_proba` de sklearn **por actor, por mes** (no en lote de 29 actores como sugiere el
ADR); cada llamada de `HistGradientBoostingClassifier` tiene overhead fijo no despreciable sobre una
sola fila. Un fix aplicado en el camino (cachear `joblib.load` por `(ruta, mtime)`, ver ADR 009 Notas
de implementación punto 11b) ya sacó el cuello de botella dominante (cargar el modelo de 9 MB 28
veces por corrida, antes de esto una corrida de 48 meses ni terminaba en 60 s); el remanente es
overhead de predicción por-actor, que un batch real por mes eliminaría — documentado como trabajo
futuro, fuera del alcance de esta fase (ver esa misma nota). **El DoD de "10.000 corridas en < 1 h"
NO se cumple con esta implementación** (proyecta ~20 h); si el volumen real de la Fase 9 lo requiere,
la extensión natural es batchear `run_actor_turn` por mes para los actores que comparten modelo.

## 5. Early-warning (`ml/early_warning.py`)

```
republica ml early-warning train \
  --runs experiments/results/fiscal_rule \
  --runs experiments/results/central_bank_independence \
  --out data/ml/early_warning.joblib
```

Entrenado sobre `fiscal_rule` (sweep 3×3, 20 semillas, 180 corridas — la corrida canónica de ADR 008,
no la versión ampliada de 70 semillas: el intento de correrla completa no terminó dentro de esta
sesión, ver §7) + `central_bank_independence` (50 semillas × 2 brazos, Fase 8): 280 corridas, 12.710
filas, 756 positivas de `crisis_12m`.

**Corregido el hallazgo #2 de REVIEW_003**: el split ahora es 70/15/15 por `(fuente, semilla)`
(`ml/surrogate.py::_split_group_seeds`, `fuente` = el directorio del `.jsonl`, uno por brazo de cada
experimento: 9 de `fiscal_rule` + 2 de `central_bank_independence` = 11 fuentes), no por el valor
crudo de la semilla. Antes, partir sobre la UNIÓN de valores de semilla hacía que "semilla 5" de
`fiscal_rule` (seeds 0–19) y "semilla 5" de `central_bank_independence` (seeds 0–49) cayeran en el
mismo tramo por pura coincidencia numérica -- con 180 filas de `fiscal_rule` contra 100 de
`central_bank_independence`, la fuente más grande dominaba el split y val/test quedaban casi sin
`central_bank_independence`, sin las dos clases representadas (por eso `AUC(test) = nan`). Con el
split por `(fuente, semilla)`, cada una de las 11 fuentes aporta su propia porción 70/15/15 a
train/val/test:

**AUC(val) = 0.9958, AUC(test) = 0.9977** (antes: `AUC(val) = 0.996`, `AUC(test) = nan`) — cumple el
DoD (≥ 0.8) con margen amplio en LOS DOS splits, ya no solo en val. `in_sample = false` (hallazgo
#11: las 11 fuentes tienen >= 20 semillas cada una, ninguna cae en el caso degenerado de <= 2). Las
6 features más importantes (permutation importance) sobre este entrenamiento combinado:
`state_reserves`, `state_congress_support`, `state_gdp`, `state_unemployment`, `trend_reserves_6m`,
`state_government_approval` — reservas, congreso y aprobación dominan, coherente con que
`collapse`/`hyperinflation` en este motor están atados a `political_stability`/`reserves` cruzando
umbrales (ver `world/events.py::check_termination`).

## 6. Regímenes (`ml/regimes.py`)

```
rm -f simulations/republica.duckdb
republica experiment load experiments/results/fiscal_rule --db simulations/republica.duckdb
republica experiment load experiments/results/central_bank_independence --db simulations/republica.duckdb
republica experiment load experiments/results/brain_comparison --db simulations/republica.duckdb
republica ml regimes --db simulations/republica.duckdb --describe
```

Corrido sobre la unión de `fiscal_rule` (180) + `central_bank_independence` (100) +
`brain_comparison` (60) cargados en el mismo DuckDB: **340 corridas**. Reporte completo:
`experiments/results/regimes/report.md`.

**Corregido el hallazgo #3 de REVIEW_003**: k-means y silhouette corren sobre la PROYECCIÓN de PCA
(`coords`), no sobre la matriz estandarizada de 38 dimensiones -- `PCA(n_components=0.90)` retiene
**6 componentes** para llegar al **91.0 %** de la varianza. `k = 3` elegido por silhouette en
`[3, 8]`, **silhouette = 0.433** (sube de 0.378 al clusterizar en 38D crudas).

| Cluster | n | Nombre | `crisis_share` | Por qué |
|---|---:|---|---:|---|
| 2 | 79 | **Ajuste recesivo** | 0.00 | Inflación mediana −0.6 %/mes (deflación leve), crecimiento −2.8 % (recesión), aprobación 31, sin crisis en el camino — el "invierno" austero que no colapsa pero tampoco crece. |
| 1 | 80 | **Sobrecalentamiento con crisis** | 0.91 | Inflación mediana 4.8 %/mes (la más alta de los 3), crecimiento 3.8 % (el más alto), aprobación 26 (la más baja) y el 91 % de sus corridas SÍ terminó en crisis — expansión que termina mal casi siempre. |
| 0 | 181 | **Sendero moderado** | 0.00 | Inflación mediana 1.8 %/mes, crecimiento 1.3 %, aprobación 36 (la más alta de los 3), sin crisis — el grupo más numeroso (mitad de las corridas): ni ajuste duro ni sobrecalentamiento. |

Mismos 3 grupos y tamaños que antes (79/80/181) -- lo que cambia es el silhouette y que
`crisis_share` (hallazgo #12: fracción de corridas del cluster que terminó en
`collapse`/`hyperinflation`, calculada aparte de `outcome_severity`) reemplaza al corte frágil
"`outcome_severity` > 0.3" para la nota "con/sin crisis".

Nombres asignados a mano, DESPUÉS de mirar los centroides (ADR 009 secc. 6, literal: no se decidieron
de antemano).

**Hallazgo #8 (rupturas de acuerdo):** corregido el conteo (ahora cuenta eventos
`agreement_broken:...` de `MonthRecord.events`, la misma definición que
`experiments/runner.py::extract_run_metrics`, no los literales muertos `broken_by_actor`/
`broken_by_president` que nunca aparecían en `negotiations.result`), pero en este dataset puntual
**`n_agreements`/`n_broken` dan 0 constante en las 340 corridas**: la tabla `negotiations` queda
vacía (0 filas) porque ninguna de las 3 corridas canónicas llegó a emitir `NEGOTIATE` -- verificado
directo sobre los `.jsonl` commiteados, no es un efecto de la carga a DuckDB. Detalle completo en
`experiments/results/regimes/report.md`.

## 7. Desviaciones relevantes

Ver `docs/ADR_009_surrogate_ui.md` §10 ("Notas de implementación") para el detalle completo. Puntos
más importantes para leer estos números:

- El agreement rate compara dos simulaciones que DIVERGEN mes a mes (acciones distintas realimentan
  el mundo): no es la exactitud de un clasificador fijo, es fidelidad de comportamiento sobre una
  trayectoria completa.
- `media`/`central_bank`/`party` tienen agreement = 1.0 por construcción (delegan a un
  `RuleBasedActor` interno: los primeros dos por diseño -- fórmula cerrada, ADR 009 punto 6 -- y
  `party` porque `train_surrogate` lo salta al no cruzar nunca los umbrales de
  apoyo/oposición/negociación con `rules` en estas 60 semillas: `position = neutral` en
  14.070/14.070 filas de `party`).
- `n_memorias_negativas_recientes` se calcula en el dataset pero NO es una feature del modelo (no
  hay forma barata de reconstruirla desde una `Perception` viva en inferencia online).
- **Hallazgo #1 de REVIEW_003 (el más importante):** con actores por reglas, `position = neutral`
  domina el 98.75 % de las 78.792 filas de entrenamiento (§1) -- un predictor constante ya da 0.9875
  de "agreement" antes de aprender nada. `evaluate_surrogate` reporta 4 números en vez de uno
  (`agreement_rate`/`majority_baseline`/`agreement_ml_roles_only`/`balanced_agreement`, ver §2) para
  que esto quede visible en vez de escondido detrás de un `agreement_rate` alto y trivial.
- **Hallazgo #7:** las (actor, mes) de `rules` sin contraparte en la corrida `surrogate` (termina
  antes, ej. una crisis que `rules` no tuvo) ya NO se descartan -- cuentan como desacuerdo, y
  `evaluate_surrogate` reporta `run_length_delta` (diferencia de longitud entre las dos corridas,
  por semilla) para que esa divergencia quede visible. En la medición de §2 (semillas 1000-1014,
  48 meses) dio 0 en las 15 semillas: ninguna de las dos corridas terminó antes que la otra en esa
  ventana puntual.
