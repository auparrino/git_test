-- Supervivencia por brazo (ADR 008 secc. 3, consulta canonica 1): outcomes
-- posibles en `runs.outcome` son `collapse`/`hyperinflation` (crisis, fin
-- de partida anticipado) o `reelected`/`defeated`/`survived` (llego al fin
-- del mandato sin crisis -- con `features.elections` prendido, que es el
-- default de los 3 experimentos canonicos, una corrida que no colapsa
-- SIEMPRE termina en `reelected`/`defeated` via una eleccion en el mes
-- `term_length`, nunca en `survived` literal: `outcome = 'survived'` da
-- 0 % en experimentos con elecciones. "Supervivencia" aca es "no termino
-- en una crisis" (mismo criterio que `experiments/report.py::_survived`,
-- ver Notas de implementacion de ADR 008 secc. 8 punto 17).
-- Uso: duckdb simulations/republica.duckdb < experiments/queries/survival_by_arm.sql
SELECT
    experiment,
    arm,
    count(*) AS n,
    sum(CASE WHEN outcome NOT IN ('collapse', 'hyperinflation') THEN 1 ELSE 0 END) AS survived,
    round(
        100.0 * sum(CASE WHEN outcome NOT IN ('collapse', 'hyperinflation') THEN 1 ELSE 0 END)
        / count(*), 1
    ) AS survival_pct
FROM runs
GROUP BY experiment, arm
ORDER BY experiment, arm;
