# Resultados de Fase 9 — Modelo sustituto, active learning, early-warning, clustering

Corrida real de referencia (ADR 009): 60 semillas × 48 meses, `brain = rules`, todas las features
prendidas. Los artefactos (`data/ml/*.joblib`/`*.csv`/`*.parquet`/`*.duckdb`) no se versionan (ver
`.gitignore`); se reproducen con el script de esta sección o `republica ml ...` a mano. Se commitea
`data/ml/manifest_example.json` como copia de referencia del manifest real del sustituto.

Estos resultados describen el comportamiento de República Artificial bajo sus reglas; no son
evidencia sobre economías reales.

## 1. Dataset

- Fuente: 60 corridas de `rules`, 48 meses, todas las features.
- Filas: 78.792 (60 × 48 × 28 actores no-presidente).
- Columnas: ver `docs/ADR_009_surrogate_ui.md` §2 y `ml/dataset.py::dataset_columns()`.

## 2. Sustituto (`ml/surrogate.py`)

Split 70/15/15 por semilla (42 train seeds 0–41 / 9 val seeds 42–50 / 9 test seeds 51–59). Métricas
por rol, del `manifest.json` real (`data/ml/manifest_example.json` es una copia):

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

### Agreement rate (DoD ≥ 0.85)

Semillas held-out 1000–1014 (nunca vistas en entrenamiento ni en val/test), 48 meses, `surrogate`
vs `rules`, comparando `position` acción a acción (actor, mes) sobre las dos corridas completas
(que divergen mes a mes: ver §7):

**`agreement_rate = 0.999`** sobre 20.160 pares (actor, mes) de 15 semillas held-out. Cumple el DoD
(≥ 0.85) con amplio margen. Por rol:

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

30 corridas de 48 meses cada una, modelo real de 60 semillas (semillas 2000–2029, no usadas en
entrenamiento):

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

Entrenado sobre `fiscal_rule` (sweep 3×3, 20 semillas, 180 corridas — la corrida canónica de ADR 008,
no la versión ampliada de 70 semillas: el intento de correrla completa no terminó dentro de esta
sesión, ver §7) + `central_bank_independence` (50 semillas × 2 brazos, Fase 8). Split 70/15/15 por
semilla (35 train / 8 val / 7 test de las semillas combinadas).

**AUC(val) = 0.996** sobre 12.710 filas (756 positivas de `crisis_12m`); cumple el DoD (≥ 0.8) con
margen amplio. `AUC(test)` salió `nan` en esta combinación puntual de semillas (el split de test no
tenía las dos clases representadas — documentado, no oculto). Una corrida solo sobre `fiscal_rule`
(sin combinar con `central_bank_independence`) sí dio ambos splits con las dos clases:
**AUC(val) = 0.996, AUC(test) = 0.997**, con las 6 features más importantes (permutation importance):
`state_reserves`, `state_government_approval`, `state_congress_support`, `trend_reserves_6m`,
`state_inflation_lag1`, `trend_government_approval_6m` — reservas y aprobación (nivel y tendencia)
dominan, coherente con que `collapse`/`hyperinflation` en este motor están atados a
`political_stability`/`reserves` cruzando umbrales (ver `world/events.py::check_termination`).

## 6. Regímenes (`ml/regimes.py`)

Corrido sobre la unión de `fiscal_rule` (180) + `central_bank_independence` (100) +
`brain_comparison` (60) cargados en el mismo DuckDB: **340 corridas**. `k = 3` elegido por silhouette
en `[3, 8]` (silhouette = 0.378).

| Cluster | n | Nombre | Por qué |
|---|---:|---|---|
| 0 | 79 | **Ajuste recesivo** | Inflación mediana −0.6 %/mes (deflación leve), crecimiento −2.8 % (recesión), aprobación 31, sin crisis en el camino — el "invierno" austero que no colapsa pero tampoco crece. |
| 1 | 80 | **Sobrecalentamiento con crisis** | Inflación mediana 4.8 %/mes (la más alta de los 3), crecimiento 3.8 % (el más alto), aprobación 26 (la más baja) y SÍ crisis en el camino — expansión que termina mal. |
| 2 | 181 | **Sendero moderado** | Inflación mediana 1.8 %/mes, crecimiento 1.3 %, aprobación 36 (la más alta de los 3), sin crisis — el grupo más numeroso (mitad de las corridas): ni ajuste duro ni sobrecalentamiento. |

Nombres asignados a mano, DESPUÉS de mirar los centroides (ADR 009 secc. 6, literal: no se decidieron
de antemano).

## 7. Desviaciones relevantes

Ver `docs/ADR_009_surrogate_ui.md` §10 ("Notas de implementación") para el detalle completo. Puntos
más importantes para leer estos números:

- El agreement rate compara dos simulaciones que DIVERGEN mes a mes (acciones distintas realimentan
  el mundo): no es la exactitud de un clasificador fijo, es fidelidad de comportamiento sobre una
  trayectoria completa.
- `media`/`central_bank` tienen agreement = 1.0 por construcción (delegan a reglas, no a ML).
- `n_memorias_negativas_recientes` se calcula en el dataset pero NO es una feature del modelo (no
  hay forma barata de reconstruirla desde una `Perception` viva en inferencia online).
