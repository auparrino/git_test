# Reporte de clustering de regímenes -- `ml/regimes.py`

`republica ml regimes --db simulations/republica.duckdb --describe` sobre la unión de los 3
experimentos canónicos ya cargados en el mismo `.duckdb` (`republica experiment load` sobre
`experiments/results/{fiscal_rule,central_bank_independence,brain_comparison}`, ADR 008 secc. 3):
**340 corridas** (180 + 100 + 60). Reproduce exactamente `FASE9_RESULTS.md` §6.

Corregido contra hallazgo #3 de REVIEW_003: el k-means y el silhouette corren sobre la
PROYECCIÓN de PCA (`coords`), no sobre la matriz estandarizada de 38 dimensiones -- **6
componentes** retienen el **91.0 %** de la varianza (`PCA(n_components=0.90)`, elegido para
llegar a >= 90 %). `k = 3` por silhouette en `[3, 8]`, **silhouette = 0.433** (sube desde 0.378 al
clusterizar en 38 dimensiones crudas: la proyección de PCA saca ruido/colinealidad que empujaba el
silhouette para abajo).

## Clusters

| Cluster | n | Nombre | `crisis_share` | Por qué |
|---|---:|---|---:|---|
| 2 | 79 | **Ajuste recesivo** | 0.00 | Inflación mediana −0.6 %/mes (deflación leve), crecimiento −2.8 % (recesión), aprobación 31, estabilidad 54, sin ninguna corrida en crisis -- el "invierno" austero que no colapsa pero tampoco crece. |
| 1 | 80 | **Sobrecalentamiento con crisis** | 0.91 | Inflación mediana 4.8 %/mes (la más alta de los 3), crecimiento 3.8 % (el más alto), aprobación 26 (la más baja), estabilidad 53, y el 91 % de sus corridas terminó en `collapse`/`hyperinflation` -- expansión que termina mal casi siempre. |
| 0 | 181 | **Sendero moderado** | 0.00 | Inflación mediana 1.8 %/mes, crecimiento 1.3 %, aprobación 36 (la más alta de los 3), estabilidad 55, sin crisis -- el grupo más numeroso (mitad de las corridas): ni ajuste duro ni sobrecalentamiento. |

Mismos 3 grupos y mismos tamaños (79/80/181) que la versión anterior (clustering en 38D); lo que
cambia es el silhouette (0.378 -> 0.433) y que `crisis_share` (hallazgo #12: fracción de corridas
del cluster que terminaron en `collapse`/`hyperinflation`, calculada aparte de
`outcome_severity`) reemplaza al corte frágil "`outcome_severity` > 0.3" para decidir la nota "con
crisis"/"sin crisis" -- acá da lo mismo en los 3 clusters (0.00/0.91/0.00 no cruzan ambigüedad
cerca de 0.3), pero ya no depende de que `defeated` (que pesa 0.3 en `outcome_severity`) no se
acumule por casualidad hasta pasar el corte.

Nombres asignados a mano, DESPUÉS de mirar los centroides (ADR 009 secc. 6, literal: no se
decidieron de antemano).

## Hallazgo #8: `n_agreements`/`n_broken` salen constantes en 0 en este dataset

Corregido el conteo de rupturas (hallazgo #8: ahora cuenta eventos `agreement_broken:...` de
`MonthRecord.events`, la misma definición que `experiments/runner.py::extract_run_metrics` /
columna `agreements_broken` de `metrics.csv`, no los literales muertos `broken_by_actor`/
`broken_by_president` que nunca aparecían en `negotiations.result`), pero en este dataset
específico **tanto `n_agreements` como `n_broken` dan 0 en las 340 corridas**: la tabla
`negotiations` está vacía (0 filas) y ningún `MonthRecord.events` de estas 340 corridas trae un
evento `agreement_broken:` -- verificado directo sobre los `.jsonl` commiteados (0 líneas
`"kind": "negotiation"` en, por ejemplo, `experiments/results/fiscal_rule/.../0.jsonl`), no es un
efecto de la carga a DuckDB. Documentado como hallazgo genuino sobre estas 3 corridas concretas
(`fiscal_rule`/`central_bank_independence`/`brain_comparison`, mismo fenómeno que ya nota
`FASE9_RESULTS.md` §2 para `party` con `rules`: los umbrales de `NEGOTIATE_MIN_ABS_SCORE` no se
cruzan en estos mundos), no una corrección incompleta del hallazgo -- el fix en sí (usar
`agreement_broken:` en vez de los literales viejos) es correcto y se puede verificar contando
manualmente esos eventos en cualquier corrida que sí los tenga.

`authority_violations` también da constante 0 en estas 340 corridas (ADR 008 secc. 2, ya
documentado ahí como "el motor por reglas casi no viola autoridad"), así que de las 38 dimensiones
del vector de trayectoria, 3 (`n_agreements`, `n_broken`, `authority_violations`) son constantes en
este dataset puntual -- no aportan al PCA/clustering pero tampoco lo rompen (varianza 0 se
mantiene en 0 tras `StandardScaler`).

## Reproducir

```
rm -f simulations/republica.duckdb
republica experiment load experiments/results/fiscal_rule --db simulations/republica.duckdb
republica experiment load experiments/results/central_bank_independence --db simulations/republica.duckdb
republica experiment load experiments/results/brain_comparison --db simulations/republica.duckdb
republica ml regimes --db simulations/republica.duckdb --describe
```
