# Revisión 003 — Fases 8 y 9 (Opus, solo lectura)

Hallazgos verificados con sondas sobre HEAD `da5bce5`. Orden: más severo primero.

| # | Severidad | Hallazgo | Fix mínimo | Estado |
|---|---|---|---|---|
| 1 | **alta** | El acuerdo del sustituto (0.999) está por debajo de lo informativo: en los 30 runs `rules` el 98.75 % de las filas son `position = neutral` (solo `neutral` y `oppose` ocurren); un predictor constante daría 0.9875. Además `party`/`media`/`central_bank` (32 % de actores) delegan a reglas y suman 1.0 por construcción. `FASE9_RESULTS.md` lo presenta como "cumple con amplio margen" sin baseline; el test pasa trivialmente. | Reportar baseline de clase mayoritaria; acuerdo solo sobre roles con modelo; métrica balanceada sobre actor-meses con `position ≠ neutral`; asertar esa. | pendiente |
| 2 | **alta** | El split held-out del early-warning se degenera: `_split_seeds` sobre la unión de valores de semilla; `fiscal_rule` usa 0–19 y `central_bank_independence` 0–49, así que los 180 runs de `fiscal_rule` caen en train y val/test solo tienen CBI (16 y 14 runs); `AUC(test) = nan` es síntoma de eso. | Split por grupo `(fuente/brazo, semilla)` o 70/15/15 por fuente y concatenar. | pendiente |
| 3 | media | `regimes` hace k-means y silhouette sobre la matriz estandarizada (38 dims), no sobre la proyección PCA como dicen el ADR y el docstring. | Agrupar sobre `coords` o corregir ADR y docstring. | pendiente |
| 4 | baja | ADR 008 §8 punto 21 cita números viejos (22.06 vs 40.27) que contradicen el reporte commiteado (23.48 vs 38.86). | Refrescar la nota. | pendiente |
| 5 | baja | `FASE9_RESULTS.md:5` apunta a un "script de esta sección" inexistente. | Poner los comandos `republica ml ...` reales (reproducen §5 y §6 exactamente). | pendiente |
| 6 | baja | Los `except ImportError` de los comandos `ml`/`experiment` son código muerto: los módulos importan sklearn/duckdb perezosamente, así que un extra faltante termina en traceback `RuntimeError`, no en el mensaje en español. | Envolver la llamada con `except RuntimeError`; sacar el guard de import. | pendiente |
| 7 | media | `evaluate_surrogate` descarta en silencio los actor-meses que faltan cuando la corrida con sustituto termina antes (crisis): excluye justamente la mayor divergencia. | Contar los faltantes como desacuerdo o reportar la diferencia de longitud. | pendiente |
| 8 | baja | `regimes` cuenta rupturas con literales que nunca ocurren (`broken_by_actor`/`broken_by_president`); las rupturas reales son eventos `agreement_broken:`; dos de 38 dimensiones son constantes. | Usar la definición de `experiments/runner.py:95`. | pendiente |
| 9 | baja | El modo jugable de Streamlit omite `fx_intervention` (4 sliders en vez de 5). | Iterar `MONTHLY_CAPS`. | pendiente |
| 10 | tests | El test de throughput solo asierta `t > 0`. | Asertar un techo de ratio laxo o eliminarlo. | pendiente |
| 11 | baja | `_split_seeds` devuelve train == val == test con ≤ 2 semillas (métricas in-sample presentadas como validación). | Levantar excepción o marcar `in_sample` en el manifest. | pendiente |
| 12 | baja | `80.0` duplicado en `dataset.py`; rama `NEGOTIATE` del sustituto sin los guards de `_decide_generic`; `severity > 0.3` frágil en `regimes`; `runs.meta.json` guarda ruta absoluta del YAML. | Limpiar. | pendiente |

Verificado y correcto: determinismo con 1 y 4 workers (JSONL idéntico), idempotencia DuckDB, mismas
semillas por brazo y `config_hash` distinto por brazo, `resume` exacto, definición de supervivencia
consistente en reporte/heatmap/SQL, bootstrap y Cliff's delta, extracción de métricas, sin fuga de
semillas entre splits ni de target en features, early-warning sin fuga terminal, `AppTest` asierta el
avance de mes, y las secciones §5 y §6 de `FASE9_RESULTS.md` se reproducen exactamente.

Consecuencia para el README: la frase sobre el sustituto debe decir que el acuerdo se mide contra un
baseline de clase mayoritaria y que, con actores por reglas, el problema es casi trivial; el sustituto
recién se vuelve informativo imitando a un LLM.
