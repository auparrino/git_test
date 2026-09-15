-- Violaciones de autoridad por modelo (ADR 008 secc. 3, consulta canonica
-- 3): une `actions` con `traces` por `(run_id, month, actor)` -- el
-- `trace_id` de una traza es `<run_id>:<mes con 3 digitos>:<actor_id>`
-- (`ai/tracing.py::DecisionTrace.trace_id`) -- para saber que MODELO tomo
-- cada decision denegada por rol ("no tiene permitido", el marcador de
-- `authority_violation`, ver `cli.py::_AUTHORITY_VIOLATION_MARKER`).
-- Sin trazas (brazo por reglas puro, `RuleBasedActor` no traza nada) esta
-- consulta no devuelve filas para ese brazo -- correrla junto con
-- `survival_by_arm.sql` para tener el panorama completo.
-- Uso: duckdb simulations/republica.duckdb < experiments/queries/authority_violations_by_model.sql
SELECT
    t.model,
    count(*) AS total_decisions,
    sum(
        CASE WHEN a.authorized = false AND a.denied_reason LIKE '%no tiene permitido%'
        THEN 1 ELSE 0 END
    ) AS violations,
    round(
        100.0 * sum(
            CASE WHEN a.authorized = false AND a.denied_reason LIKE '%no tiene permitido%'
            THEN 1 ELSE 0 END
        ) / count(*), 2
    ) AS violation_pct
FROM actions a
JOIN traces t
    ON t.run_id = a.run_id
    AND t.trace_id = a.run_id || ':' || lpad(CAST(a.month AS VARCHAR), 3, '0') || ':' || a.actor
GROUP BY t.model
ORDER BY violation_pct DESC;
