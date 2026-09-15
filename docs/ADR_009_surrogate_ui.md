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
