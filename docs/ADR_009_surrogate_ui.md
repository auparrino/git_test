# ADR 009 — Modelo sustituto, active learning, early-warning, clustering y UI (Fase 9)

Estado: aceptado para implementar. Depende de ADR 003–008.

## 1. Objetivo

Escalar de cientos a decenas de miles de corridas sin una decisión de LLM por turno, y poder
*mirar* el laboratorio desde el navegador. Dos advertencias que gobiernan el diseño:
- El sustituto imita **al actor que se le muestre**. En este entorno se entrena sobre `rules` (y
  `fake:rules`); con Ollama disponible, sobre `llm:*`. El pipeline es el mismo; la validez del
  sustituto se mide siempre contra el cerebro que imita, nunca "contra la realidad".
- Sin numpy/sklearn en el núcleo. Todo lo de esta fase vive detrás del extra `[analysis]`
  (`duckdb`, `pandas`, `matplotlib`) más `scikit-learn` en un extra nuevo `[ml]`; el motor sigue
  siendo stdlib + pydantic.

## 2. Dataset de decisiones (`src/republica/ml/dataset.py`)

De cada corrida (JSONL) se extrae una fila por `(actor, mes)`:

| Bloque | Features |
|---|---|
| Percepción pública | los 9 `public_indicators` |
| Percepción privada | los `private_indicators` del rol, con `NaN` donde no aplica (one-hot de rol) |
| Propuesta | `policy_delta` por instrumento (5 columnas, 0 si no hay) + magnitud normalizada |
| Actor | 4 ejes de ideología, 4 de personalidad, `influence` (4), one-hot de rol |
| Relación y memoria | `relationships.president` (vista), `trust_president`, `n_memorias_negativas_recientes` |
| Contexto | `months_to_election`, shocks activos (12 booleanos), `in_government` del partido |
| **Target** | `position ∈ {support, oppose, negotiate, neutral}`, `intensity`, y el multilabel de tipos de acción emitidos |

`republica ml dataset simulations/exp/<dir> --out data/ml/decisions.parquet` (o CSV si no hay pyarrow).
Solo se usan filas cuya traza existe (`llm:*`) o el `ActionRecord` (`rules`); las denegadas se
incluyen con `authorized=false` como feature del target multilabel (el sustituto también debe
aprender qué intenta y le deniegan).

## 3. Sustituto (`src/republica/ml/surrogate.py`)

- Modelo: `HistGradientBoostingClassifier` para `position` + `HistGradientBoostingRegressor` para
  `intensity` + un clasificador one-vs-rest para el multilabel de acciones (sklearn). Un pipeline
  por **rol** (9 modelos), porque las features privadas difieren.
- Split por **semilla** (no por fila) para medir generalización a mundos no vistos: 70/15/15.
- Métricas: accuracy y F1 macro de `position`, MAE de `intensity`, Jaccard del multilabel, todo
  por rol; y **agreement rate** contra el cerebro imitado en corridas held-out completas
  (re-simular con `brain = surrogate` y comparar acción a acción con `brain = rules`).
- Serialización: `data/ml/surrogate_<brain>_<hash>.joblib` + `manifest.json` (dataset hash,
  métricas, versión del paquete). El motor lo carga con `brain = "surrogate:<path>"`.
- `SurrogateActor.decide(perception, rng) -> list[Action]` con la misma interfaz; incluye
  `confidence = max proba de position`.

DoD: agreement rate ≥ 0.85 en `position` sobre semillas held-out contra `rules`; 10.000 corridas
de 48 meses con `surrogate` en < 1 h en 4 cores (medir; el rules ya corre en ~0.1 s/corrida, el
sustituto no debería ser más lento que 5× eso: la inferencia se hace por lote de 29 actores por mes).

## 4. Active learning (`src/republica/ml/active.py`)

Cuando `brain = "surrogate:<path>+fallback:<brain>"`:
- si `confidence < umbral` (0.6) **o** la percepción cae fuera de distribución (distancia de
  Mahalanobis diagonal sobre las features numéricas > percentil 99 del train), se consulta el
  cerebro de respaldo (`rules` acá, `llm:*` con Ollama), se usa su decisión y la fila se agrega a
  `data/ml/active_queue.jsonl`.
- `republica ml retrain --queue` reentrena con el dataset + la cola y registra en el manifest
  cuántas filas vinieron de active learning y cómo cambió el agreement rate.
- Métrica reportada: `fallback_rate` por corrida y por rol.

## 5. Early-warning (`src/republica/ml/early_warning.py`)

Target: `collapse | hyperinflation` dentro de los 12 meses siguientes al mes `t`. Features: el
estado completo en `t` más tendencias a 3 y 6 meses, `perception_gap`, `agreements_broken`
acumulados, `protest_level`, `congress_support`, fragmentación (índice de Herfindahl de bancas).
Modelo: gradient boosting con calibración isotónica. Salida: probabilidad y las 6 features más
importantes (permutation importance). Se expone en `narrate` y en la UI como
"Riesgo de crisis a 12 meses: 73 %" con sus drivers. DoD: AUC ≥ 0.8 en semillas held-out sobre
un experimento de ≥ 2.000 corridas con variación de `c_f`, `primary_spending` y autonomía del BC.

## 6. Clustering de regímenes (`src/republica/ml/regimes.py`)

Por corrida, un vector de trayectoria: percentiles (10/50/90) y pendiente de 8 variables clave,
outcome, nº de acuerdos y rupturas, `perception_gap` medio, `authority_violations`,
turnover electoral. Estandarizar → PCA (o UMAP si está instalado) → k-means con k elegido por
silhouette en [3, 8]. Cada cluster recibe un nombre **después**, por sus centroides
(`republica ml regimes --describe` imprime la tabla y una frase plantilla por cluster).
Los clusters se guardan en la tabla `regimes` de DuckDB y son la base de la sección
"Regímenes" del README.

## 7. UI Streamlit (`src/republica/ui/app.py`, extra `[ui]` = `streamlit`)

`republica ui` lanza `streamlit run`. Pestañas (ADR original §23):
`Mundo · Política · Economía · Congreso · Actores · Relaciones · Medios · Eventos · Trazas IA ·
Evals · Experimentos · Regímenes`. Reglas:
- La UI **lee** JSONL/DuckDB y llama a `Game` para el modo jugable; no duplica lógica.
- Modo jugable: mismo `Game` que la CLI, con dilemas como tarjetas y los instrumentos como sliders
  con las mismas cotas mensuales; el estado vive en `st.session_state` y se guarda con
  `Game.save`.
- "Relaciones" es un grafo (networkx opcional; si no, matriz).
- Tests con `streamlit.testing.v1.AppTest` (sin navegador): la app carga una corrida de ejemplo,
  cambia de pestaña y avanza un mes en modo jugable.
- El visor HTML autocontenido (`republica viewer`) sigue existiendo para compartir una corrida sin
  instalar nada.

## 8. CLI
```
republica ml dataset <dir|jsonl...> --out data/ml/decisions.parquet
republica ml train --dataset ... --brain rules --out data/ml/surrogate_rules.joblib
republica ml evaluate --model ... --seeds 100:130          # agreement rate en held-out
republica run --brain surrogate:data/ml/surrogate_rules.joblib[+fallback:rules]
republica ml retrain --queue
republica ml early-warning train|predict
republica ml regimes --db simulations/republica.duckdb [--describe]
republica ui
```

## 9. Tests (DoD de Fase 9)
1. `dataset` sobre 4 corridas produce filas = Σ actores × meses con las columnas del §2.
2. `train` sobre 30 semillas y `evaluate` sobre 10 held-out: agreement ≥ 0.85 en `position` contra `rules`.
3. `surrogate` como brain corre 48 meses × 29 actores y produce `ActionRecord` con `brain = surrogate`.
4. Active learning: con umbral 0.99 el `fallback_rate` es ≈ 1; con 0.0 es 0; la cola se escribe.
5. Early-warning: AUC ≥ 0.8 en held-out sobre el experimento `fiscal_rule` ampliado (≥ 600 corridas).
6. `regimes`: k por silhouette, tabla `regimes` en DuckDB, `--describe` imprime ≥ 3 clusters.
7. `AppTest`: la app carga, muestra las 12 pestañas y avanza un mes.
8. Tiempo: 1.000 corridas con `surrogate` en < 6 min en CI (proxy del objetivo de 10.000 en < 1 h).

## 10. Notas de implementación (Fase 9)

Ambigüedades, decisiones de diseño y desviaciones al implementar `ml/{dataset,surrogate,active,
early_warning,regimes}.py`, `ui/app.py`, la integración en `ai/brains.py`/`engine/scheduler.py` y
las corridas reales de `data/ml/`. Todo lo corrido para verificarlas usa `rules` (el cerebro que
imita el sustituto en este entorno, ADR literal secc. 1): no hay Ollama real ni red hacia él aquí
(mismo motivo documentado en ADR 004/007/008).

### Dataset (`ml/dataset.py`)

1. **El JSONL de una corrida por reglas NO persiste la `Perception` de cada actor** (ADR 004 secc.
   6: solo `LLMActor` traza eso, vía `DecisionTrace`). `rows_from_run` reconstruye `private_indicators`/
   `policy_delta` a partir de lo que sí persiste `MonthRecord` (`state`/`policy`/`aux`/`provinces`),
   no leyéndolos tal cual: `policy_delta` se aproxima como `policy[mes] − policy[mes−1]` (no el delta
   interno exacto que ve el actor, que corre antes del recorte de Congreso/topes mensuales);
   `affected_by_shocks`/`sector_affected_by_shocks` (necesitan el `ShockAggregate` del mes, no
   persistido) quedan en `0.0`; `trust_president` se iguala a `relationship_president` (la vista de
   memoria tampoco se persiste). Documentado en detalle, punto por punto, en el docstring de
   `ml/dataset.py` (5 aproximaciones numeradas) para no duplicarlo aquí.
2. **`position` se deriva del catálogo de acciones emitidas ese mes** (`SUPPORT_POLICY→support`,
   `OPPOSE_POLICY→oppose`, `NEGOTIATE→negotiate`, si no `neutral`), literal como pide la tarea de
   implementación: un `RuleBasedActor` no declara una `position` explícita como lo haría un LLM (ADR
   004 secc. 3, `ActorDecision.position`), así que se infiere de qué `ActionType` intentó. Un actor
   nunca emite dos de esas tres en el mismo mes con las reglas actuales (`_decide_generic` arma UNA
   sola rama support/oppose/negotiate/no-accion, ADR 003 secc. 6), pero el orden de precedencia de
   `_derive_position` queda fijado igual para no dejar una ambigüedad latente: `support` > `oppose` >
   `negotiate` > `neutral`, en el mismo orden en que aparecen en la tabla del §2.
3. **El multilabel de tipos de acción es "qué intenta", no cruzado con `authorized`.** El ADR dice
   "las denegadas se incluyen con `authorized=false` como feature del target multilabel": se
   interpretó como que el *dataset* (no necesariamente el target del clasificador) debe dejar
   constancia de las denegadas -- cada fila tiene `authorized` (0/1: si TODAS las acciones del mes
   fueron autorizadas) y `n_denied` (cuántas no); el multilabel `action_<TIPO>` es 1 si el actor
   *intentó* ese tipo ese mes, autorizado o no. Cruzar cada tipo con su propio autorizado/denegado en
   un solo vector (44 columnas en vez de 22 + 2) se dejó de lado por simplicidad: el sustituto (ver
   más abajo) igual "aprende qué le deniegan" indirectamente, porque entrena sobre datos donde la
   política de `rules` ya incorpora esas denegaciones (un actor cuyo `STRIKE` siempre se deniega por
   cooldown simplemente no lo intenta seguido en los datos de entrenamiento).
4. **`n_memorias_negativas_recientes` cuenta eventos `kind: "memory"` con `sentiment < 0` en los
   últimos 6 meses** (ventana inventada: el ADR no da un número, se reusa `TREND_WINDOW_MONTHS` de
   `world/perception.py`, ya establecida como "reciente" en el proyecto). `engine.narrate.load_jsonl`
   no agrupa esas líneas (solo las excluye de `records`): `ml/dataset.py` tiene su propio parser
   mínimo (`load_run_jsonl`) que sí las agrupa por mes.
5. **`seats`/`in_government` usan `country.parties` (la config INICIAL del país, sin actualizar por
   `ElectionResult`)**: una corrida con `features.elections` puede cambiar bancas/partido de gobierno
   a mitad de camino; no se rastrean las elecciones mes a mes para actualizar esta feature (el
   sustituto sigue viendo `months_to_election`/`congress_support` reales, que sí cambian). Documentado,
   no bloqueante para el DoD.

### Sustituto (`ml/surrogate.py`)

6. **Como mucho 8 pipelines entrenados, no 9 -- y en la corrida real de referencia, 5.**
   `president` nunca pasa por `decision_actors` (ADR 003 secc. 7: es una regla/humano aparte); no
   hay filas de entrenamiento para ese rol. `media`/`central_bank` (ADR 003 secc. 6.3/6.4) deciden
   con una fórmula **cerrada y sin ruido** (umbrales de aprobación/inflación/PIB; regla de Taylor):
   `SurrogateActor.decide()` los delega SIEMPRE a un `RuleBasedActor` interno embebido (agreement
   exacto = 1.0 en esos dos roles, por construcción, no por aprendizaje) -- se prefirió esto a
   entrenar un clasificador para aproximar una función ya determinista y barata de
   evaluar (no hay fidelidad que ganar, y si hay una degradación innecesaria posible).
   Además, `_fit_role` salta cualquier rol cuyo split de train tenga MENOS DE 2 clases distintas de
   `position` (`HistGradientBoostingClassifier` no puede entrenar con una sola clase) -- en la
   corrida real de 60 semillas (`docs/FASE9_RESULTS.md`), a `media`/`central_bank` se les sumó
   `party`: con `rules`, un `party` nunca cruza los umbrales de `SUPPORT_THRESHOLD`/
   `OPPOSE_THRESHOLD` NI junta el mínimo de `NEGOTIATE_MIN_ABS_SCORE` con un `NEGOTIATE` autorizado
   en las 60 semillas entrenadas (`position` es SIEMPRE `"neutral"`, 14.070/14.070 filas) -- una
   propiedad genuina de la dinámica simulada con estos pesos/umbrales, no un error de extracción.
   `SurrogateActor.decide()` ya maneja este caso solo (`role not in self.bundle["models"]` cae al
   mismo `RuleBasedActor` interno que `media`/`central_bank`), sin necesitar una lista hardcodeada de
   "roles sin suficiente variedad": el fallback es automático para CUALQUIER rol que termine sin
   modelo entrenado, sea por diseño (fórmula cerrada) o por falta empírica de variedad en los datos.
7. **La construcción de `Action` a partir de `position`/`intensity` predichos reusa literal la lógica
   de `RuleBasedActor._decide_generic`** (mismos umbrales `STATEMENT_MIN_INTENSITY`, la misma función
   `_escalate`, la misma tabla `_NEGOTIATE_CONCESSION`, el mismo recorte a `ACTION_BUDGET_PER_TURN`)
   en vez de usar el multilabel entrenado para elegir qué acciones emitir. El multilabel SÍ se
   entrena y se reporta (Jaccard, deliverable explícito del ADR) pero no gobierna la decisión: medido
   empíricamente, reconstruir determinísticamente desde `position` reproduce mejor `rules` (que es
   literalmente lo que mide el DoD 2/3: "agreement rate ... contra `rules`") que dejar que un
   clasificador aparte elija acciones sueltas sin la consistencia interna que tiene la regla real.
8. **Split 70/15/15 por semilla, SECUENCIAL (no mezclado)** sobre la lista de semillas ordenada: con
   pocas semillas (tests) cada tramo mínimo es 1 (si hay ≥ 3 semillas). No se barajan al azar antes
   de partir: reproducible sin necesitar una semilla propia de split, a costa de que "semillas bajas
   entrenan, semillas altas evalúan" no sea un muestreo aleatorio -- para el volumen real (60
   semillas) no hay razón para esperar que las semillas bajas sean sistemáticamente distintas.
9. **OOD (Mahalanobis diagonal) excluye columnas sin varianza en train** (constantes, o enteramente
   `NaN` para ese rol -- las `pi_*` de otro rol, siempre `NaN` dentro del subconjunto de un rol
   específico): además de no aportar señal, `HistGradientBoostingClassifier` no puede binarizar una
   columna con menos de 2 valores distintos (revienta con `ValueError` en muestras chicas, se
   encontró así con los primeros smoke tests). Las mismas columnas "activas" (`active_idx`) se
   guardan en el bundle y las reusa `SurrogateActor` en inferencia.
10. **`ActionRecord` gana un campo `brain: str = "rules"`** (`engine/scheduler.py`), agregado
    unicamente porque el DoD 3 literal pide "produce `ActionRecord` con `brain = surrogate`" y ese
    campo no existía (solo `DecisionTrace`, exclusivo de `LLMActor`, lo tenía). `to_dict()` solo
    agrega la clave `"brain"` cuando NO es `"rules"` (mismo patrón que `MonthRecord.cohorts`/
    `trace_records`, ADR 003/004/005): una corrida enteramente por reglas produce el mismo JSONL byte
    a byte que antes de esta fase (verificado: los 169 tests de Fases 1-8 siguen pasando sin tocarlos).
    Se lee DESPUÉS de `decide()` (no antes) porque un `ActiveLearningActor` solo sabe si cayó al
    respaldo una vez que decidió ese turno.
11. **`SurrogateActor`/`ActiveLearningActor` no llevan un `last_score`/`ScoreBreakdown` real**
    (`last_score = None` siempre, paridad de interfaz con `LLMActor`, ADR 003 secc. 11 punto 27):
    `engine/scheduler.py` ya lee ese atributo con `getattr(..., None)`, sin distinguir el tipo de
    actor.
11b. **`load_surrogate_bundle` cachea por `(ruta, mtime)`** (`functools.lru_cache`), hallazgo de
    rendimiento medido, no una optimización especulativa: sin esto, `build_actor_engine` arma un
    `SurrogateActor` POR ACTOR (28 no presidente) y cada uno releía el `.joblib` completo del disco
    (deserializando 8 × 3 modelos sklearn) -- una corrida de 48 meses pasó de no terminar en 60 s a
    ~11 s tras el fix (medido con un modelo real de 60 semillas, ~9 MB). El `mtime` en la clave evita
    servir un bundle viejo si `republica ml retrain` reescribe el mismo archivo dentro del mismo
    proceso largo-vivo (ver `ui/app.py`). Con esto, el sustituto queda ~20× más lento que `rules` por
    corrida (medido en `docs/FASE9_RESULTS.md` §4) -- por encima del "no más de 5×" que sugiere la
    secc. 3 del ADR, porque la inferencia sigue siendo POR ACTOR (`SurrogateActor.decide()` llama a
    `predict`/`predict_proba` una vez por actor por mes), no en lote de 29 por mes como sugiere el
    ADR. La tarea de implementación permite explícitamente esta opción ("per-actor es aceptable pero
    medirlo"): un batch real requeriría reestructurar el loop de `engine/scheduler.py::run_actor_turn`
    en dos pasadas (recolectar percepciones, predecir en lote, recién ahí armar acciones) para los
    actores que comparten el mismo `SurrogateActor`/modelo -- cambio de mayor alcance que se dejó
    fuera de esta fase, documentado como trabajo futuro si el volumen real (10.000 corridas) lo exige.

### Active learning (`ml/active.py`)

12. **El spec gana un tercer segmento opcional, `+threshold:<valor>`** (`"surrogate:<path>+fallback:
    <brain>+threshold:0.99"`), que no está en el ejemplo literal del ADR (`surrogate:<path>+fallback:
    <brain>`). Sin esto no había forma de pasar un umbral distinto del default (0.6) desde
    `--brain`/`data/brains.yaml`, y el DoD 4 pide explícitamente probar dos umbrales distintos (0.99
    y 0.0) -- necesita alguna vía de configuración. El orden de los segmentos no importa
    (`fallback`/`threshold` se parsean por clave, no por posición).
13. **La OOD fuerza el respaldo AUNQUE la confianza sea alta**: `confidence >= umbral AND NOT
    is_ood`. El ADR los conecta con una "o" ("si `confidence < umbral` **o** la percepción cae fuera
    de distribución"): un actor puede estar muy seguro de una predicción que igual está fuera de la
    distribución de entrenamiento (ej. un shock nunca visto en 60 semillas de train): la confianza
    del clasificador no es evidencia de que el input se parezca a lo que vio en entrenamiento.
14. **La fila que va a la cola es la DECISIÓN DEL RESPALDO**, no la del sustituto descartado: tiene
    sentido para reentrenar (el respaldo es, por definición en este entorno, `rules`, el cerebro que
    se imita) -- agregar la predicción fallida del sustituto a su propio set de entrenamiento no
    tendría sentido pedagógico. El esquema de la fila reusa `dataset.perception_features` +
    `_derive_position`, para que `republica ml retrain --queue` la sume directo al split de train sin
    reparsear nada.
15. **`retrain_with_queue` pide `sources` explícito** (las mismas corridas que uso `ml train`): el
    manifest de un modelo guarda semillas/métricas, no las rutas de origen (podrían no existir más,
    o haberse movido) -- documentado como limitación conocida, no un bug: `republica ml retrain
    --queue` en la CLI pide `--runs` de nuevo.

### Early-warning (`ml/early_warning.py`)

16. **`perception_gap` sale de `engine.narrate.load_jsonl` (no de `ml.dataset.load_run_jsonl`)**: el
    parser propio de `dataset.py` no agrupa líneas `kind: "perception"` (no las necesita para el
    dataset de decisiones); se relee el archivo una segunda vez con el parser de `narrate` -- costo
    aceptado (un archivo más grande hoy es el `fiscal_rule` ampliado, aun así corre en su totalidad
    en menos de un minuto, ver más abajo).
17. **`crisis_12m` se deriva de `outcome`/longitud de `records`, no de un chequeo mes a mes de
    `WorldState`**: una corrida termina temprano exactamente en el mes de la crisis
    (`engine/simulation.py::run`, `OUTCOMES`), así que "crisis dentro de los 12 meses de `t`" es
    simplemente "el `outcome` de la corrida es de crisis Y el mes final cae en `[t+1, t+12]`" --
    más simple y sin ambigüedad que reconstruir la condición de colapso/hiperinflación a mano.
18. **Calibración isotónica solo si hay ≥ 3 positivos y ≥ 3 negativos en train** (si no,
    `CalibratedClassifierCV(cv=3)` revienta con muy pocos ejemplos de una clase): con datasets chicos
    (tests) cae a `HistGradientBoostingClassifier` sin calibrar. La corrida real (ver §11 abajo) sí
    tiene suficientes positivos para calibrar.
19. **`fragmentation_herfindahl` usa `country.parties` (config inicial, no las bancas post-elección)**
    -- misma limitación que el punto 5 del dataset de decisiones, mismo motivo.

### Regímenes (`ml/regimes.py`)

20. **`republica ml regimes --db ...` NO toma `--runs`**: opera sobre lo que ya esté cargado en la
    base (`runs`/`months`/`negotiations`/`actions`/`perception`/`elections`, ADR 008 secc. 3) -- así
    corre sobre la UNIÓN de varios experimentos cargados en el mismo `.duckdb`, literal como pide el
    deliverable ("Correrlo sobre la unión de resultados de experimentos").
21. **La tabla `regimes` se reescribe entera en cada corrida** (`DELETE FROM regimes` + insert), a
    diferencia de `runs`/`months`/etc. de `experiment load` (`ON CONFLICT DO NOTHING`, append-only):
    un re-cluster puede cambiar `k`/las etiquetas de corridas ya vistas (no es un log de eventos, es
    un resultado derivado que se recalcula).
22. **`outcome` entra al vector de trayectoria como `outcome_severity`** (`collapse`/
    `hyperinflation`→1.0, `defeated`→0.3, `reelected`/`survived`→0.0) en vez de one-hot: un solo
    número real que aporta a la distancia euclídea sin inflar la dimensión del vector con columnas
    dispersas.
23. **Los nombres de los clusters los pone quien lee `--describe`** (`describe_cluster` arma una
    frase con los rasgos del centroide -- inflación/crecimiento/aprobación/estabilidad medianas y si
    hay crisis en el camino -- pero NO bautiza el cluster): literal el ADR, "reciben un nombre
    DESPUÉS, por sus centroides". Los nombres reales que se le dieron a los clusters de la corrida
    real quedan en `docs/FASE9_RESULTS.md`.

### UI (`ui/app.py`)

24. **La corrida de ejemplo se genera EN MEMORIA** (`run_simulation` cacheado con `st.cache_data`,
    `engine.narrate.loads_jsonl` -- función nueva, refactor de `load_jsonl` que separa "leer texto de
    un archivo" de "parsear texto ya en memoria", sin cambiar el comportamiento de `load_jsonl`
    existente ni sus tests): así la UI funciona apenas se instala `[ui]`, sin depender de que exista
    algún archivo `.jsonl` en el repo.
25. **"Modo jugable" no es una pestaña de las 12**: es un panel aparte, activado por un checkbox en
    la barra lateral, que se muestra ANTES de las 12 pestañas (que siguen mostrando la corrida
    elegida en la fuente de datos, independiente de la partida jugable). El ADR describe las 12
    pestañas de solo lectura y el modo jugable como dos cosas separadas (secc. 7, dos párrafos
    distintos); no hay una pestaña "jugar" en la lista literal de 12.
26. **Crear la partida y mostrar sus controles (dilemas/instrumentos/"Avanzar mes") ocurre en la
    MISMA corrida del script**, sin un `return` temprano tras el botón "Nueva partida": Streamlit no
    re-ejecuta el script automáticamente después de mutar `st.session_state` dentro del mismo run
    (`AppTest.run()` ejecuta el script UNA vez por invocación); con un `return` inmediato el DoD 7
    ("carga, muestra las 12 pestañas y avanza un mes") necesitaría un tercer paso de interacción sin
    ninguna ganancia de UX real -- el botón "Nueva partida" ya deja la partida lista para jugar en la
    misma pantalla.
27. **"Relaciones" usa la ficha estática (`ActorSheet.relationship`), no las `Relationships` vivas
    del motor** (que no se serializan en el JSONL: son estado interno de `ActorEngine`, ADR 003 secc.
    5/7): igual que el dataset de decisiones (punto 1), la UI solo puede mostrar lo que el JSONL
    realmente persiste.
28. **`networkx` es opcional de verdad**: si no está instalado, la pestaña "Relaciones" cae a la
    matriz sola (ni siquiera se importa `networkx` a nivel de módulo) -- no es una dependencia
    agregada a `[ui]`, es puramente "si ya está en el entorno, se arma el grafo".

### CLI (`cli.py`)

29. **`republica ml regimes`/`republica ui` fallan con un mensaje en castellano si falta el extra**,
    no con un `ImportError` crudo (mismo patrón que `republica experiment load` de ADR 008): se
    intenta el import dentro del comando y se atrapa `ImportError` antes de llamar a la función real.
30. **`republica ml retrain` pide `--runs` (repetible) además de `--queue`**: ver punto 15 arriba
    (limitación documentada de `retrain_with_queue`).

### Corridas reales (`data/ml/`)

31. Los números medidos (métricas del sustituto por rol, agreement rate en semillas held-out,
    `fallback_rate` a 3 umbrales, AUC de early-warning con sus features más importantes, la tabla de
    regímenes con los nombres asignados y por qué) están en `docs/FASE9_RESULTS.md`, no acá --
    evita duplicar números que van a cambiar si se vuelve a correr el pipeline. `data/ml/*.joblib`/
    `*.csv`/`*.parquet`/`*.duckdb` quedan fuera de git (`.gitignore`); se commitea
    `data/ml/manifest_example.json` (copia del `manifest.json` real de `surrogate_rules.joblib`, el
    deliverable explícito del ADR) para que quede un ejemplo concreto de métricas sin repetir la
    corrida completa.
