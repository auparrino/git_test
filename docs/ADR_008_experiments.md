# ADR 008 — Experimentos en lote, DuckDB y comparación de modelos (Fase 8)

Estado: aceptado para implementar. Depende de ADR 003–007.

## 1. Definición declarativa (`experiments/*.yaml`)

```yaml
name: central_bank_independence
description: ¿Qué cambia cuando el BC puede fijar la tasa sin pasar por el presidente?
base:
  months: 48
  features: {congress: true, negotiation: true, cohorts: true, media: true, memory: true}
  brains: rules                    # o data/brains.yaml
seeds: {start: 0, count: 50}       # mismas semillas en todos los brazos
arms:
  dependent:   {governance: {central_bank: {autonomy: 2}}}
  independent: {governance: {central_bank: {autonomy: 4}}}
sweep:                             # opcional: producto cartesiano sobre arms
  country.coefficients.c_f: [0.08, 0.12, 0.16]
metrics: [outcome, inflation_annual_final, gdp_growth_mean, unemployment_final, approval_final,
          stability_min, reserves_min, authority_violations, perception_gap_mean, agreements_broken]
```
`arms` son overrides (dot-path) sobre `country.json`, `governance.yaml`, `brains.yaml` y `features`.
Un experimento es reproducible por `(yaml, config_hash de cada archivo de datos, versión del paquete)`;
todo eso se guarda en `runs.meta`.

## 2. Runner (`experiments/runner.py`)

```
republica experiment run experiments/central_bank_independence.yaml --workers 4 --out simulations/exp/<name>/
republica experiment status <dir>          # progreso, corridas fallidas
republica experiment resume <dir>          # reanuda por (arm, seed) faltante
```
- `multiprocessing.Pool` para `rules`/`fake`/`surrogate`. Para `llm:ollama:*`, cola con `--workers 1`
  (Ollama serializa) y `CachedBackend` obligatorio.
- Cada corrida escribe su JSONL en `<out>/<arm>/<seed>.jsonl`; un fallo no detiene el lote (queda en
  `failed.jsonl` con traceback).
- Tiempo objetivo: 100 corridas × 48 meses × 29 actores por reglas en < 2 min con 4 workers.

## 3. DuckDB (`experiments/store.py`)

`republica experiment load <dir> --db simulations/republica.duckdb` crea/actualiza:

| Tabla | Clave | Contenido |
|---|---|---|
| `runs` | `run_id` | experimento, brazo, semilla, outcome, meses, config_hash, paquete, timestamp |
| `months` | `run_id, month` | las 20 variables + exógenas + policy + aux (una columna por variable) |
| `actions` | `run_id, month, seq` | actor, tipo, params (JSON), razón, autorizada, motivo de denegación, score |
| `negotiations` | `run_id, month, actor` | rondas (JSON), resultado, concesión |
| `votes` | `run_id, month, bill` | por partido (JSON), total, aprobada |
| `perception` | `run_id, month, cohort` | percibidas vs. reales |
| `elections` | `run_id, month` | resultado (JSON) |
| `traces` | `trace_id` | modelo, tokens, latencia, parse_error, eval_score |
| `evals` | `report_id, metric` | valor, baseline, IC |

Carga idempotente (`INSERT ... ON CONFLICT DO NOTHING` por clave). `duckdb` es dependencia opcional
(`[analysis]`) junto con `pandas`/`matplotlib` para notebooks; el runner no la necesita.

Consultas canónicas en `experiments/queries/*.sql` (supervivencia por brazo, inflación mediana por
brazo y mes, violaciones de autoridad por modelo, `perception_gap` por medio dominante).

## 4. Reporte (`experiments/report.py`)

`republica experiment report <dir>` → `report.md` con: tabla por brazo (N, outcomes, mediana e IC
bootstrap de cada métrica), diferencia entre brazos con IC y tamaño de efecto (Cliff's delta), y
gráficos PNG (`matplotlib` si está instalado; si no, tablas). Sección obligatoria **"Limitaciones"**
con la frase fija: "Estos resultados describen el comportamiento de República Artificial bajo sus
reglas; no son evidencia sobre economías reales."

## 5. Experimentos canónicos

1. **`central_bank_independence`** (arriba). Hipótesis registrada antes de correr: el brazo
   independiente tiene menor inflación final mediana y mayor desempleo, sin diferencia clara en
   supervivencia.
2. **`brain_comparison`**: mismo país, mismos shocks (semillas 0–29), brazos `rules`, `fake:rules`,
   `llm:ollama:<A>`, `llm:ollama:<B>`; métricas de ADR 007 más `diversity`, `agreements_total`,
   `agreements_broken`, `strikes`. El reporte incluye la matriz de acuerdo entre brazos por actor y mes.
   Requiere Ollama; en CI corre solo con los dos primeros brazos.
3. **`fiscal_rule`** (sweep): `c_f ∈ {0.08, 0.12, 0.16}` × `primary_spending ∈ {23, 25, 27}`;
   mapa de calor supervivencia × inflación.

## 6. Notebooks
`notebooks/01_cb_independence.ipynb`, `02_brain_comparison.ipynb`: leen del DuckDB, semillas fijas,
se ejecutan con `uv run jupyter nbconvert --execute` en un job manual de CI (no en cada push).

## 7. Tests (DoD de Fase 8)
1. Un experimento de 2 brazos × 4 semillas corre con `--workers 2`, escribe 8 JSONL y `runs.meta`.
2. `resume` tras borrar 2 JSONL vuelve a correr exactamente esos 2.
3. `load` sobre el resultado crea las tablas y `SELECT count(*) FROM runs` = 8; recargar no duplica.
4. `report` produce `report.md` con la sección "Limitaciones" y una tabla por brazo.
5. `sweep` de 2×2 genera 4 brazos con nombres deterministas.
6. Overrides por dot-path modifican el valor esperado y el `config_hash` del brazo difiere del base.

## 8. Notas de implementación (Fase 8)

Ambigüedades, decisiones de diseño y desviaciones al implementar `experiments/`
(`config.py`/`runner.py`/`store.py`/`report.py`), los 3 YAML canónicos, las 4 consultas SQL, el
subcomando `republica experiment` y las 3 corridas reales de `experiments/results/`.

### Formato del override (`experiments/config.py`)

1. **`arms` se escribe como YAML anidado, no como texto `"actor.campo=valor"`.** El ADR dice "arms
   son overrides (dot-path)" y el ejemplo de §1 lo escribe como
   `{governance: {central_bank: {autonomy: 2}}}` -- YAML anidado, no una cadena con puntos. Se
   interpretaron los dos como la MISMA cosa: `_flatten_overrides` convierte la forma anidada de
   `arms` a la forma plana `"governance.central_bank.autonomy"` antes de aplicar nada, así termina en
   el mismo mecanismo que ya usa `sweep` (que sí trae la clave plana, literal del ADR:
   `country.coefficients.c_f`). Un `arms` que ya trajera una clave plana con puntos también
   funcionaría (`_flatten_overrides` no toca strings), pero los 3 YAML canónicos usan la forma
   anidada por legibilidad.
2. **4 namespaces fijos, primer segmento del dot-path:** `country.*` (dot-path dentro del `dict`
   crudo de `country.json`, antes de tipar a `Country`), `governance.<actor_id>.<campo>` (mismo
   formato que ya definía `governance.parse_governance_overrides`/`_apply_override`, ADR 007 secc.
   6 -- se reusa tal cual, sin reimplementar el parseo), `brains.default` / `brains.actors.<id>`, y
   `features.<nombre>`. Una clave que no empieza con uno de los 4 (o que no trae una sub-clave
   después del namespace) levanta `ValueError` al resolver el brazo -- se prefirió fallar temprano
   (en `resolve_arms()`, antes de lanzar ninguna corrida) a silenciar un typo de YAML.
3. **`config_hash` de un brazo = `sha256(base_hash + overrides)`, no solo el hash de los archivos en
   disco.** `world.config._compute_config_hash` (ADR 003, hallazgo #8 de REVIEW_001) hashea
   `country.json`/`provinces.csv`/etc. tal como están en `data/` -- un override en memoria (que
   nunca se escribe a disco) no cambia ese hash. `_arm_config_hash` combina ese hash base con el
   `dict` de overrides del brazo (JSON canónico, `sort_keys=True`) para que DOS brazos que leen los
   mismos archivos pero difieren en un override (p.ej. `autonomy=2` vs. `autonomy=4`) tengan
   `config_hash` distinto -- el DoD 6 literal ("el `config_hash` del brazo difiere del base") no se
   cumpliría si solo se hasheara el disco, porque ningún override lo toca.
4. **`_build_country` duplica el cuerpo de `world.config.load_country`** (mismos `Country(...)`,
   mismos `_load_provinces`/`_load_parties`/`_coalition_seats` importados directo del módulo) en vez
   de agregarle un parámetro `overrides` a `load_country` -- `load_country()` sin argumentos es la
   ruta "sin overrides" que usan 156 tests existentes y toda la CLI de `run`/`play`/`eval`; tocarla
   para aceptar un `raw` en memoria hubiera sido un cambio más grande e innecesario fuera de
   `experiments/`. El precio es que un campo nuevo de `Country` hay que agregarlo en los dos lugares
   -- documentado acá para el próximo ADR que le agregue un campo a `Country`.
5. **`base.brains` acepta un spec de cerebro (`"rules"`, `"fake:rules"`) O una ruta a un YAML** (el
   comentario literal del ADR: `brains: rules  # o data/brains.yaml`). Se distingue por si el string
   tiene `/` o termina en `.yaml`/`.yml`; si es ruta relativa y no existe tal cual, se prueba contra
   la raíz del repo (`data_dir.parent / spec`) antes de usarla literal -- así `base: {brains:
   data/brains.yaml}` funciona corriendo `republica experiment run` desde cualquier directorio.
6. **La resolución de `features` efectivas (qué depende de qué) copia la lógica de
   `cli.py::run`** (`cohorts` independiente de `actors`; `media`/`elections` dependen de `actors` Y
   `cohorts`; `congress`/`negotiation`/`memory` dependen solo de `actors`) en vez de extraer una
   función común -- la CLI resuelve sobre banderas `bool | None` (tri-estado, "no la pasaron") y
   `experiments/config.py` sobre un `dict[str, bool]` ya mergeado (`_DEFAULT_FEATURES` <
   `country.features` < `base.features` < override del brazo); unificar los dos hubiera significado
   tocar `cli.py` fuera del alcance de esta fase.

### Runner (`experiments/runner.py`)

7. **`--workers` se ignora SOLO para las tareas de brazos `llm:*`, no para el lote entero.** El ADR
   dice "para `llm:ollama:*`, cola con `--workers 1`" -- se interpretó como una propiedad de esas
   tareas puntuales (Ollama serializa sus llamadas, no tiene sentido pedirle 4 a la vez), no como
   "si HAY un brazo `llm:*` en el experimento, todo el lote se degrada a serie": las tareas
   `rules`/`fake:*` del mismo experimento siguen corriendo en el `Pool` con el `--workers` pedido: el
   experimento se particiona en `parallel_tasks`/`serial_tasks` por `_uses_llm(arm)` antes de correr
   nada.
8. **`extract_run_metrics`/`metrics.csv` es una funcionalidad de `runner.py`, no un módulo
   `experiments/metrics.py` aparte** -- la tarea de implementación lista exactamente 4 archivos
   (`config`/`runner`/`store`/`report`) para `src/republica/experiments/`; el extractor se coloca en
   `runner.py` porque `run_experiment`/`resume_experiment` ya lo llaman al final de cada corrida
   (`write_metrics_csv`, sobre TODOS los JSONL que existan en `<out>`, no solo los de esa invocación
   puntual -- así `resume` dos veces seguidas deja `metrics.csv` completo sin re-leer todo a mano).
9. **`authority_violations` reusa el mismo marcador de string que `cli.py::_AUTHORITY_VIOLATION_MARKER`**
   (`"no tiene permitido"`, la `denied_reason` que pone el chequeo 1 de `authorize()`, ADR 004 secc.
   8) en vez de contar TODA acción no autorizada -- una denegación por cooldown/presupuesto/gobernanza
   no es una violación de autoridad en el sentido de "el actor pidió algo fuera de su rol".
10. **`perception_gap_mean` promedia el `perception_gap` de CADA línea `kind: "perception"`** (una
    por mes, no por cohorte -- `PerceptionRecord` es un registro mensual con un `dict` de cohortes
    adentro, ADR 005 secc. 4): con `features.cohorts=False` no hay ninguna línea así, y la métrica
    queda `None` (columna vacía en `metrics.csv`), no `0.0` -- "sin datos" y "gap perfecto" son cosas
    distintas.
11. **Un brazo `broken` (gobernanza con un campo inexistente, o cualquier excepción de
    `run_simulation`) SÍ detiene el `resolve_arms()` si el error ocurre construyendo la `Country`/el
    `Arm` (p.ej. un override de tipo incorrecto que `pydantic` rechaza) -- solo un error que ocurre
    DENTRO de `run_simulation()` (governance overrides mal formados los valida `load_governance()`
    recién al armar el `ActorEngine`, ADR 007 secc. 6) cae en `failed.jsonl` sin frenar el resto del
    lote.** Ver el test `test_failed_run_does_not_stop_the_batch`: usa un campo de gobernanza
    inexistente (falla adentro de `_run_task`), no un override de tipo (que fallaría antes, al
    resolver los brazos, y frenaría el comando entero -- un YAML con overrides mal tipados es un
    error de configuración del experimento, no de una corrida puntual).

### DuckDB (`experiments/store.py`)

12. **La tabla `perception` (clave `run_id, month, cohort`, literal del ADR) se llena expandiendo
    CADA `PerceptionRecord` (una línea por MES, con un `dict` de cohortes adentro) en una fila por
    `(mes, cohorte)`** -- el JSONL no trae una línea por cohorte (ver punto 10); `real_json` repite
    `real_inflation`/`real_unemployment`/`perception_gap` (comunes a todas las cohortes de ese mes)
    en cada fila, y agrega `outlet_influence` (el `dict` completo de influencia por medio ese mes,
    ADR 005 secc. 4.5) -- la tabla del ADR no tiene columna de "medio dominante", así que la consulta
    canónica 4 (`perception_gap_by_dominant_outlet.sql`) lo calcula de acá con `json_keys`/`unnest`.
13. **Los nombres de columna de `negotiations`/`votes` siguen los campos REALES de
    `NegotiationRecord`/`VoteRecord`** (`engine/negotiation.py`/`engine/congress.py`), no la
    paráfrasis en español de la tabla del ADR ("rondas"/"resultado"/"concesión" -> `turns`/`outcome`/
    `agreement`; "por partido"/"total"/"aprobada" -> `by_party_json`/`yes_total`/`passed`) -- se
    prefirió la fuente de verdad del `to_dict()` de cada dataclass a adivinar un nombre nuevo.
14. **`run_id = "<experimento>:<brazo>:<semilla>"`** (no el `sha256(seed + config_hash)[:12]` de
    `ai/tracing.py::make_run_id`, que ya existe para otra cosa -- identificar una `DecisionTrace`
    dentro de un JSONL): la clave de `runs` necesita ser legible y estable entre `load` sucesivos del
    MISMO experimento (para que `ON CONFLICT (run_id) DO NOTHING` sea la idempotencia que pide el
    ADR), y única entre experimentos distintos cargados en el mismo `.duckdb` -- `sha256(seed +
    config_hash)` colisionaría entre dos brazos con overrides que casualmente producen el mismo
    `config_hash` para semillas coincidentes en experimentos distintos, cosa que `<experimento>:
    <brazo>:<semilla>` no puede hacer por construcción.
15. **La tabla `evals` se crea (con su clave `report_id, metric`) pero nunca se llena desde
    `experiment load`.** El ADR la lista en la misma tabla de §3 pero sus filas vienen de
    `republica eval`/`evals/report.py` (ADR 007 secc. 4, un reporte JSON con métricas de agente), un
    concepto distinto de "una corrida de experimento" -- conectar los dos (cargar un
    `evals/reports/<ts>/report.json` a esta misma base) queda fuera de esta fase; se documenta el
    hueco en vez de improvisar un `report_id` sin una fuente real.

### Reporte (`experiments/report.py`)

16. **El IC bootstrap es de la MEDIANA, no del promedio.** El ADR dice literal "mediana e IC
    bootstrap de cada métrica" -- `evals/metrics.py::bootstrap_ci` (ADR 007) resamplea y promedia,
    porque ahí la métrica típica es una tasa (0/1 por caso); acá se resamplea y se toma la MEDIANA de
    cada resample (`bootstrap_ci_median`), consistente con qué estadístico se está reportando en la
    tabla.
17. **"Supervivencia" en el mapa de calor de `fiscal_rule` NO es `outcome == "survived"` literal.**
    Con `features.elections` prendido (el default de los 3 canónicos) y `months == term_length`
    (48 = 48), TODA corrida que no termina antes en `collapse`/`hyperinflation` llega al mes 48 con
    una elección esperándola: el resultado es siempre `reelected`/`defeated`, nunca `survived` (ver
    `engine.simulation.OUTCOMES`) -- calcular el mapa de calor con `outcome == "survived"` literal
    daba 0 % en las 9 celdas de `fiscal_rule` (se detectó así, corriendo el experimento real: ver
    más abajo). Se redefinió "supervivencia" para el mapa de calor y su PNG como "no terminó en una
    crisis" (`outcome not in {"collapse", "hyperinflation"}`, `_survived()`), que es la lectura que
    tiene sentido para "sensibilidad fiscal x inflación" y la que efectivamente varía entre celdas
    (100 % -> 0 % de `c_f=0.08,primary_spending=23` a `c_f=0.16,primary_spending=27`).
18. **Con `sweep` de 2 dimensiones se muestra un mapa de calor en vez de la tabla de diferencia entre
    brazos** (que sería `C(9,2) = 36` filas para `fiscal_rule`, ilegible); sin `sweep` de 2
    dimensiones (0 o >2 claves) se muestra la tabla de diferencia par a par, para TODOS los pares de
    brazos (no solo si son exactamente 2) -- con 2 brazos (los 3 canónicos que no son `fiscal_rule`)
    es una sola fila por métrica; con más brazos sin `sweep` de 2D, la tabla crece pero sigue siendo
    la lectura más directa de "todas las diferencias" que pide el ADR.
19. **`cliffs_delta(a, b)` está firmado "`b` vs. `a`"**: positivo = `b` estocásticamente mayor que
    `a`. En la tabla de diferencia entre brazos, `a` es siempre el primer brazo listado y `b` el
    segundo (mismo orden que la columna "IC diferencia (b-a)"), así el signo del Cliff's delta y el
    signo del IC de la diferencia siempre apuntan para el mismo lado.
20. **No se implementaron los notebooks de ADR §6** (`notebooks/01_cb_independence.ipynb`,
    `02_brain_comparison.ipynb`) -- la tarea de implementación de esta fase no los pide en su lista
    de entregables (sí pide `experiments/{config,runner,store,report}.py`, los YAML, las consultas
    SQL y las 3 corridas reales) y el DuckDB que deja `experiment load` ya es consultable directo con
    `duckdb simulations/republica.duckdb < experiments/queries/<consulta>.sql` sin Jupyter. Queda
    para una fase futura si hace falta la versión notebook.

### Corridas reales (`experiments/results/`)

21. **`central_bank_independence` (50 semillas x 2 brazos, 48 meses, todas las features,
    `--workers 4`) corrió en ~6 s** (no ~2 min: el motor por reglas es liviano, ver el objetivo de
    tiempo de la secc. 2 -- "100 corridas... en < 2 min" resultó muy conservador para actores por
    reglas). La hipótesis registrada en el YAML se cumplió PARCIALMENTE: inflación anualizada final
    mediana más baja en el brazo independiente (22.06 vs. 40.27, IC de la diferencia
    `[-33.24, -5.86]`, Cliff's delta -0.53) y desempleo final más alto (11.08 vs. 8.82, IC
    `[1.53, 2.82]`, delta +0.78) -- las dos direcciones previstas. Lo que NO se cumplió es "sin
    diferencia clara en supervivencia": el brazo dependiente tuvo 8/50 corridas que terminaron en
    crisis (`collapse`+`hyperinflation`) antes de llegar a una elección, el independiente 0/50 --
    una diferencia real, documentada tal cual en `report.md` en vez de forzarla a calzar con la
    hipótesis.
22. **`brain_comparison` corre solo `rules`/`fake_rules`** (30 semillas, `--workers 4`, ~23 s): los
    brazos `llm:ollama:qwen3:8b`/`llm:ollama:qwen3:32b` quedan comentados en el YAML (este entorno no
    tiene Ollama ni red saliente hacia un servidor real, mismo motivo documentado en ADR 007 secc. 8
    punto 20) -- `fake_rules` reprodujo EXACTAMENTE las métricas de `rules` (Cliff's delta 0.00 en
    las 9 métricas), el resultado esperado (misma tubería de decisión, ADR 007 secc. 7 punto 2).
23. **`fiscal_rule` (9 brazos x 20 semillas, 48 meses, `--workers 4`) corrió en ~10 s.** El mapa de
    calor confirma la hipótesis con margen: supervivencia 100 % en `c_f=0.08..0.16, primary_spending=23`
    (gasto primario en línea con `tax_rate=25`), cayendo a 45 %/5 %/0 % en `primary_spending=27` a
    medida que sube `c_f`; inflación anualizada mediana pasa de -11.36 % (deflación leve, el brazo
    más austero) a 1398.19 % (hiperinflación) en la celda `c_f=0.16, primary_spending=27`.
