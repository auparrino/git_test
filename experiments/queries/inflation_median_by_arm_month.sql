-- Inflacion (anualizada) mediana por brazo y mes (ADR 008 secc. 3,
-- consulta canonica 2): sirve para graficar la trayectoria de cada brazo.
-- Uso: duckdb simulations/republica.duckdb < experiments/queries/inflation_median_by_arm_month.sql
SELECT
    r.arm,
    m.month,
    median(
        (
            power(1.0 + CAST(json_extract(m.state_json, '$.inflation') AS DOUBLE) / 100.0, 12) - 1.0
        ) * 100.0
    ) AS inflation_annual_median
FROM months m
JOIN runs r USING (run_id)
GROUP BY r.arm, m.month
ORDER BY r.arm, m.month;
