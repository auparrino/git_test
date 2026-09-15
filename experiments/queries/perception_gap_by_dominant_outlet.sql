-- perception_gap por medio dominante (ADR 008 secc. 3, consulta canonica
-- 4): para cada mes de cada corrida, el medio con mayor
-- `influence.public` ese mes (`outlet_influence`, guardado dentro de
-- `real_json` -- la tabla `perception` es por `(run_id, month, cohort)`,
-- sin columna de outlet, ver `experiments/store.py::_load_one_run`) y el
-- `perception_gap` de ese mes. Requiere `features.cohorts`/`features.media`
-- (si no, `outlet_influence`/`perception_gap` no existen y la consulta no
-- devuelve filas).
-- Uso: duckdb simulations/republica.duckdb < experiments/queries/perception_gap_by_dominant_outlet.sql
WITH month_gaps AS (
    SELECT DISTINCT
        run_id,
        month,
        CAST(json_extract(real_json, '$.perception_gap') AS DOUBLE) AS perception_gap,
        json_extract(real_json, '$.outlet_influence') AS outlet_influence_json
    FROM perception
),
outlets AS (
    SELECT
        run_id,
        month,
        unnest(json_keys(outlet_influence_json)) AS outlet_id
    FROM month_gaps
    WHERE outlet_influence_json IS NOT NULL
),
dominant AS (
    SELECT
        o.run_id,
        o.month,
        g.perception_gap,
        o.outlet_id,
        CAST(json_extract(g.outlet_influence_json, '$.' || o.outlet_id) AS DOUBLE) AS influence
    FROM outlets o
    JOIN month_gaps g USING (run_id, month)
    QUALIFY row_number() OVER (
        PARTITION BY o.run_id, o.month ORDER BY influence DESC
    ) = 1
)
SELECT
    outlet_id AS dominant_outlet,
    count(*) AS n,
    round(avg(perception_gap), 4) AS perception_gap_mean
FROM dominant
GROUP BY outlet_id
ORDER BY perception_gap_mean DESC;
