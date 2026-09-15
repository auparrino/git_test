# ADR 014 — Backtest secuencial 1916–2023 y análisis de predictibilidad

Estado: aceptado para implementar después de la recalibración (ADR 012 §6). Responde a la pregunta:
*¿en qué condiciones el modelo predice y en cuáles no?* No busca un número global de acierto; busca
las **características de la ventana** que separan aciertos de fallos.

## 1. Ventanas

Origen rodante `t0` cada 12 meses desde 1916-01 hasta 2022-12 (107 orígenes), horizonte `h` de 12, 24 y
48 meses. Para cada `(t0, h)`:
- Estado inicial real con `initial_state_for(t0)` (mensual desde 1961; antes, anual interpolado con
  `annual_mode` para 1916–1943 y mensual interpolado 1943–1960); se registran los conteos
  `source/proxy/assumed`.
- Época de partidos y actores por `select_era(t0)` (ADR 013); sin época → Aurora con marca.
- Régimen inicial real de `regimes.csv`; `fx_regime` de `fx_regimes.csv` (antes de 1983, `float`
  salvo tabla ampliada por el implementador con fuentes).
- Shocks históricos forzados **solo exógenos** (commodities, mundo, guerra, pandemia, sequía);
  nunca hiperinflación, default, golpe ni crisis bancaria: esos son lo que hay que predecir.
- 30 semillas por ventana; coeficientes de la recalibración final (`--calibration <run_id>`) y, como
  control, Aurora sin calibrar.

Costo: 107 × 3 × 30 × 2 ≈ 19.000 corridas cortas; a ~0.05 s por mes de corrida, del orden de
40 min con 4 workers. Si excede 60 min, se reduce a 15 semillas y se dice.

## 2. Qué se predice y cómo se puntúa

| Objetivo | Métrica | Acierto si |
|---|---|---|
| Dirección de la inflación a `h` | signo de `π(t0+h) − π(t0)` real vs mediana simulada | coinciden |
| Magnitud de la inflación a `h` | error normalizado (RMSE en desvíos de la serie real de la década) | < error de persistencia |
| Régimen a `h` | `regime_mode` binarizado vs V-Dem | coinciden |
| Elección dentro de la ventana | oficialismo gana/pierde (mayoría de semillas) vs real; si hay época, ganador | coincide |
| Crisis dentro de la ventana | ocurrencia de `hyperinflation`/`sovereign_default`/`collapse`/`coup` (≥ 30 % de semillas) vs `events.csv` | coincide (incluye "no crisis") |
| Golpe (1916–1983) | `coup` endógeno vs real | coincide |

Cada `(t0, h, objetivo)` produce una fila con `hit ∈ {0,1}`, el error continuo cuando aplica, y las
**características** de la sección 3. Solo se puntúan objetivos con dato real en `t0+h`.

## 3. Características candidatas (lo que se cruza con el acierto)

| Grupo | Característica |
|---|---|
| Datos | `n_source`, `n_proxy`, `n_assumed` del estado inicial; frecuencia (mensual/anual interpolado); ¿hay serie de reservas? ¿de desempleo? |
| Régimen | `regime_mode` inicial; `vdem_polyarchy`; años desde el último golpe; `fx_regime` |
| Economía | nivel de inflación en `t0` (tramos: < 1 %, 1–3 %, 3–10 %, > 10 % mensual); tendencia previa 12 m; reservas/importaciones; deuda/PIB; distancia a un default previo |
| Política | meses hasta la próxima elección; aprobación proxy; fragmentación (Herfindahl de bancas) |
| Shocks | nº de shocks exógenos forzados en la ventana; magnitud |
| Modelo | ¿la ventana está dentro del período de calibración (in-sample)? ¿hay época de partidos? horizonte `h`; dispersión entre semillas (IQR) |

## 4. Análisis

1. **Tablas estratificadas**: tasa de acierto por objetivo × cada característica (tramos), con IC
   bootstrap y N. Es lo que se lee primero.
2. **Modelo de predictibilidad**: regresión logística regularizada y un árbol de decisión de
   profundidad ≤ 3 sobre `hit` con las características; se reporta importancia por permutación y
   las 3 reglas del árbol en lenguaje llano ("con inflación inicial > 10 % mensual y sin serie de
   reservas, la dirección de la inflación se acierta el 41 %"). Validación cruzada por década para
   que las reglas no describan solo la muestra.
3. **Dispersión como señal**: ¿la IQR entre semillas predice el error? Si sí, el modelo "sabe cuándo
   no sabe" y eso se dice; si no, también.
4. **Comparación calibrado vs Aurora** por década: dónde la calibración ayuda, dónde daña.

## 5. Salidas

`data/countries/argentina/backtest/<run_id>/`: `windows.csv` (una fila por ventana-objetivo con hit,
error, características), `report.md` con las tablas, las reglas, los gráficos (acierto por década
y objetivo; acierto vs inflación inicial; IQR vs error) y las secciones obligatorias "Qué hace
funcionar una predicción", "Qué no se puede concluir" y la frase fija de `PLAN_ARGENTINA.md` §4.
CLI: `republica backtest --country argentina --calibration <id> --from 1916 --to 2022 --horizons 12,24,48 --seeds 30 --workers 4`.

## 6. Tests
1. Backtest `--from 2000 --to 2003 --horizons 12 --seeds 2`: corre, `windows.csv` con las columnas de §2–§3, sin NaN en `hit`.
2. Los objetivos sin dato real en `t0+h` no se puntúan (test con una ventana en 1930).
3. El análisis corre sobre `windows.csv` sintético y produce el árbol con ≤ 3 niveles y la tabla estratificada.
4. Ningún shock de la lista prohibida (hiper, default, golpe, crisis bancaria) aparece como forzado.
