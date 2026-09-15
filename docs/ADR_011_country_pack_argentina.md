# ADR 011 — Paquete de país: Argentina sobre el motor de Aurora (fases A2–A4)

Estado: aceptado para implementar tras la entrega de A0/A1. Depende de ADR 003–008.

## 1. Decisión

Un **país es datos más un puñado de reglas de régimen**, no otro simulador. `data/countries/<id>/`
contiene todo lo que Aurora tiene hoy en `data/` (país, provincias, partidos, actores, shocks,
cohortes, gobernanza) más tres cosas nuevas: una **historia** (series reales), una **cronología**
(eventos y régimen por año) y una **calibración** (coeficientes ajustados con su reporte). El motor
gana cuatro capacidades genéricas, cada una detrás de un feature flag y con golden hash de Aurora:
modo de régimen, calendario de shocks forzados, sector externo bimonetario con default, y calendario
real con mandatos variables. Aurora sigue corriendo byte a byte igual con los flags apagados.

```
data/countries/argentina/
├── country.json            # estado inicial POR FECHA (initial_states: {"1983-12": {...}, "1991-04": {...}, ...})
├── provinces.csv, regions.csv, cohorts.csv, cohorts_loyalty.csv, media_consumption.csv
├── parties/<era>.json      # sistema de partidos por época; el loader elige por fecha
├── actors/<era>/*.yaml     # fichas por época (A5)
├── shocks.json             # catálogo Aurora + shocks nuevos
├── governance.yaml
├── history/*.csv           # series reales tidy (A0) + SOURCES.md + coverage.md
├── politics/events.csv, regimes.csv, shocks_calendar.csv   # (A1)
└── calibration/<run_id>/   # coeficientes ajustados + reporte (A3)
```

CLI: `republica run --country argentina --start 1983-12 --months 72 [--calibration <run_id>]
[--historical-shocks] [--regime-mode auto|democracy]`. Sin `--country`, todo es Aurora.

## 2. Estado inicial por fecha

`country.json → initial_states` es un diccionario fecha → las 20 variables. Cada valor trae
`source` (serie de `history/` de la que sale, con la transformación: por ejemplo
`inflation = (1 + ipc_anual/100)^(1/12) − 1`) o `proxy` con la regla (`government_approval` no tiene
serie: proxy = 50 + 20·(voto del oficialismo en la última elección − 0.45)/0.15, acotado; documentado).
Las variables sin serie ni proxy razonable (`crime_perception`, `consumer_confidence` antes de 2001)
arrancan en el valor de Aurora y se marcan `assumed: true`. El loader rechaza fechas sin estado inicial.

## 3. Reglas de régimen (`world/regime.py`, flag `features.regime`)

| Modo | Elecciones | Congreso | Actores | Cómo se entra | Cómo se sale |
|---|---|---|---|---|---|
| `democracy` | según Constitución vigente | activo | todos | elección o transición | golpe (evento) o `stability < 15` × 3 meses (Aurora) |
| `coup` (1 mes) | suspendidas | disuelto | presidente reemplazado por `military_junta` (ficha), partidos a `in_government=false` | evento `coup` del calendario **o** endógeno: `stability < 20` y `institutional_confidence < 30` y `regime_era` con `coup_propensity > 0` (calibrado con V-Dem: la propensión es la frecuencia observada de golpes por década) | inmediato a `dictatorship` |
| `dictatorship` | no | no | sindicatos y partidos con `write` restringido por gobernanza (`autonomy 1`); variable `repression ∈ [0,1]` que baja `protest_level` y sube `social_tension` latente y baja `institutional_confidence` | desde `coup` | `transition` cuando `social_tension > 70` o derrota externa (evento) o calendario |
| `transition` (≤ 24 meses) | se convoca | se reinstala | partidos vuelven | desde `dictatorship` | elección → `democracy` |

`term_length` y `reelection_allowed` se leen de `politics/constitutions.csv` por fecha (1853–1994: 6
años sin reelección inmediata; 1994+: 4 años con una reelección). La variable de salida
`regime_mode` se registra por mes y se compara con V-Dem `v2x_regime` en validación (matriz de
confusión democracia/no democracia por año).

## 4. Calendario de shocks forzados (`features.historical_shocks`)

`politics/shocks_calendar.csv` se convierte en `forced_shocks` (ya soportado) más los shocks nuevos:

| id | Efecto objetivo (por mes, salvo indicación) |
|---|---|
| `sovereign_default` | mes 1: `reserves −30 %`, `institutional_confidence −10`, `shock_fx +20`; durante 24 meses: acceso a crédito cerrado (`k_k = 0`), `interest_cost` de la deuda ×0.5 (no se paga) |
| `currency_run` | `shock_fx +8` por mes durante `duration`, `reserves −k·gdp` |
| `war` | `shock_fiscal −2`, `approval +10` el mes 1 y `−15` al terminar si `outcome = lost` |
| `imf_program` | `reserves + monto`, `primary_spending −1.5` forzado (condicionalidad), `approval −3`, `institutional_confidence +2` |
| `hyperinflation_regime` | no es shock: es el estado endógeno de Aurora (`inflation > 20` × 3 meses); se **espera** que el modelo lo produzca solo. Si hay que forzarlo, la validación falla y se documenta |

Regla de honestidad: en cada reporte, la lista de shocks forzados en el período va antes que los
resultados.

## 5. Sector externo bimonetario (`features.bimonetary`)

Tres variables nuevas (fuera de las 20 de Aurora, en un bloque `external`):
- `dollar_demand ∈ [0, 1]`: sube con inflación esperada, con `institutional_confidence` baja y con la
  brecha; baja con tasa real positiva. Multiplica la presión cambiaria: `de_raw += x_d · dollar_demand`.
- `fx_gap`: brecha oficial/paralelo cuando hay control de cambios (`fx_regime = control`); alimenta
  la percepción de inflación de las cohortes (percibida sube con la brecha) y baja reservas por
  `k_gap`.
- `external_debt_usd` (% PIB) con `fx_share`: la devaluación real la revalúa (ya existe en Aurora
  parcialmente); `default_risk = f(reserves / external_debt, fiscal_balance)`; si `default_risk > umbral`
  y el presidente no consigue `imf_program`, el motor dispara `sovereign_default` endógeno.
- `fx_regime ∈ {float, crawl, peg, control}` como instrumento de política nuevo (la convertibilidad es
  `peg` con `fx_intervention = 1` y `k_k` alto mientras haya reservas).
- Exógenas reales: `commodity_price` pasa a ser el índice real de soja/trigo/petróleo ponderado (de
  `history/`), `world_demand` el crecimiento de Brasil+socios (proxy: PIB mundial del BM).

## 6. Modo anual (1810–1943, `features.annual_mode`)

Un turno = un año; las fórmulas mensuales se aplican 12 veces con exógenas constantes dentro del año
y sin actores mensuales (solo el presidente por reglas y el régimen). Cohortes, medios y Congreso
apagados. Es exploratorio y se marca así en cada salida.

## 7. Calibración (`republica calibrate`, A3)

- **Parámetros**: los ~90 coeficientes de `country.json → coefficients` más los nuevos de §5. Cada uno
  con rango permitido (±3× el valor de Aurora, o físico si aplica).
- **Objetivo**: para cada mes del período de entrenamiento, simular con el estado inicial real de
  ese mes y los shocks exógenos reales de los siguientes `h = 12` meses, y medir el error de
  `inflation`, `gdp_growth`, `unemployment`, `exchange_rate`, `reserves` a 1, 3, 6 y 12 meses contra
  la serie real (RMSE normalizado por la desviación de cada serie), más un término de régimen (acierto
  del modo) y de elecciones (acierto del ganador y error de vote share en las elecciones del período).
  Regularización L2 hacia los valores de Aurora (para no perder la coherencia interna).
- **Optimizador**: CMA-ES (`cma` en PyPI, extra `[calibration]`) o Nelder-Mead reiniciado; presupuesto
  de evaluaciones fijo; semillas fijas; paralelo por meses de inicio.
- **Protocolo**: `--train 1993-01:2015-12 --holdout 2016-01:2023-12`; se reporta train y holdout por
  variable y horizonte, contra dos baselines: persistencia (`x_{t+h} = x_t`) y Aurora sin calibrar.
  El holdout se corre **una vez**, al final; cualquier recalibración posterior usa otro holdout o se
  declara in-sample.
- **Salida**: `calibration/<run_id>/coefficients.json`, `report.md`, `plots/`, con el hash de los
  datos de entrada.

## 8. Validación histórica (A4), hipótesis registradas antes de correr

| Prueba | Estado inicial | Shocks forzados | Hipótesis | Métrica |
|---|---|---|---|---|
| V1 1988→1990 | 1988-06 real | solo exógenos (commodities, mundo) — **no** se fuerza la hiper | el modelo entra en `hyperinflation` en 12–24 meses en > 50 % de semillas | fracción de semillas, mes mediano |
| V2 1998→2002 | 1998-01 real, `fx_regime = peg` | crisis internacional 1998–99 (Rusia, Brasil) | `sovereign_default` o `collapse` en 36–54 meses en > 50 % | idem + trayectoria de reservas vs real |
| V3 2016→2023 | 2016-01 real | sequía 2018, pandemia 2020, sequía 2023 | inflación anual final > 80 % en la mediana y el oficialismo pierde en 2019 y 2023 | error de inflación, aciertos electorales |
| C Control | los tres anteriores | los mismos | Aurora sin calibrar falla al menos una de las tres | la diferencia con el calibrado es el "valor" de la calibración |

Cada reporte cierra con: shocks forzados, proxies usados, baselines, y la frase fija de
`PLAN_ARGENTINA.md` §4.

## 9. Tests (DoD de A2)
1. `run --country argentina --start 1983-12 --months 12` corre; sin `--country`, JSONL de Aurora byte a byte igual (golden).
2. Loader: estado inicial por fecha con `source`/`proxy`/`assumed` obligatorio por variable; fecha sin estado → error claro.
3. Régimen: evento `coup` en el calendario suspende elecciones y disuelve el Congreso; `transition` reinstala; `regime_mode` mensual en el JSONL.
4. Golpe endógeno: con `coup_propensity > 0` y estabilidad < 20 sostenida, ocurre en ≥ 50 % de 20 semillas; con propensión 0, nunca.
5. `sovereign_default` forzado cierra el crédito 24 meses y revalúa la deuda; endógeno se dispara con `default_risk` alto sin `imf_program`.
6. Bimonetario: `dollar_demand` sube con inflación y baja con tasa real; `fx_gap > 0` solo en `control`.
7. Mandato de 6 años en 1989 y de 4 en 1999 según `constitutions.csv`.
8. Modo anual: 1880→1930 corre en < 5 s y produce 50 registros anuales con `regime_mode`.
9. `calibrate` sobre un período sintético (Aurora generando "datos reales" con coeficientes conocidos) recupera los coeficientes dentro del 20 % en al menos la mitad de ellos (test de identificabilidad).
