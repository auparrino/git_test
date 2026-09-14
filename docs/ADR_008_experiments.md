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
