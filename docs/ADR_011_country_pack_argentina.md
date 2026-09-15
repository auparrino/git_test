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

## Notas de implementación (A2)

Implementado: `src/republica/world/countries.py` (loader), `world/regime.py`, `world/bimonetary.py`,
`world/annual.py`; hooks nuevos y opcionales (default `None`/`False`) en `engine/simulation.py::run()`
(`regime_calendar`, `bimonetary_coefficients`, `fx_regime`, `historical_exogenous`) y dos campos nuevos
en `MonthRecord` (`regime_mode`, `external`), ausentes de `to_dict()`/el JSONL cuando están vacíos
(mismo patrón que `cohorts`, ADR 005). `republica run/batch --country <id> --start YYYY-MM`,
`republica country info <id>`, `experiment` (`base: {country, start}`). Golden hash de Aurora sin
`--country` verificado byte a byte contra un `git worktree add /tmp/head HEAD` del commit
`244f1792e0c99d9af8564f264e407d63dc1c6a61` (antes de A2): `tests/test_country_pack_argentina.py::
test_aurora_without_country_matches_golden_hash_pre_a2`.

Cada desviación de esta lista existe porque implementarla al pie de la letra exigía tocar el núcleo del
motor (`step_economy`/`WorldState`/`advance_month`) de un modo que arriesgaba el hash de Aurora, o
requería un dato que no está descargado a la fecha de A2 — nunca porque "diera mejor" en algún período
particular (regla de honestidad del proyecto, PLAN_ARGENTINA.md §0.3).

**Paquete de país / loader**
- `load_country_pack` arma una carpeta "fusionada" (symlinks a `data/` de Aurora + symlinks a
  `data/countries/<id>/` encima, en `tempfile.gettempdir()`) y reusa `world.config.load_country` tal
  cual sobre esa carpeta — así el fallback a Aurora es automático y genérico para *cualquier* archivo
  que el paquete no traiga (`provinces.csv`, `parties.json`, `governance.yaml`, `permissions.yaml`,
  `consequences.yaml`, `concessions.yaml`, `interests.yaml`, `policy_signatures.yaml`,
  `actor_weights.yaml`, `data/actors/*.yaml` salvo `junta.yaml`), sin necesidad de una lista de
  archivos hardcodeada. El paquete de Argentina de A2 sólo define en su raíz lo que pide el enunciado
  de la tarea (`country.json`, `constitutions.csv`, `cohorts*.csv`/`media_consumption.csv`,
  `shocks.json`, `actors/junta.yaml`): un `provinces.csv`/`parties/<era>.json`/`governance.yaml`
  propios de Argentina (sistema de partidos por época, 24 jurisdicciones reales en vez de las 8 de
  Aurora) quedan fuera de alcance de A2 y son candidatos naturales para A5.
- `country.json` del paquete usa `initial_states` (por fecha) en vez de `initial_state`: el loader NO
  delega en `world.config.load_country` para parsear ese archivo — resuelve la fecha pedida, arma un
  `initial_state` plano, y recién ahí escribe un `country.json` efectivo (con el mismo esquema que
  Aurora) en la carpeta fusionada antes de invocar `load_country`. Un bug real de esta implementación,
  encontrado y corregido en el camino: `merged / "country.json"` es un *symlink* al `country.json` real
  del paquete (puesto ahí por el fusionado) — escribirle directo sin desengancharlo primero seguía el
  symlink y pisaba el archivo fuente. El código ahora hace `unlink()` antes de `write_text()`
  (`world/countries.py::load_country_pack`, comentado en el propio archivo) para que esto no pueda
  volver a pasar.
- `término_length`/`reelection_allowed` se resuelven **una sola vez, contra la fecha de `--start`**
  (`constitutions.csv`), y quedan fijos para toda la corrida: una corrida que arranca en 1990 y pasa
  los 96 meses sigue con mandato de 6 años sin reelección aunque cruce la reforma de 1994 en el medio
  (tal como pide el enunciado: "no tratar de calzar exactamente las fechas históricas de elección,
  documentarlo"). Las elecciones caen en múltiplos de `term_length` desde `--start`, no en las fechas
  reales de octubre/diciembre. `reelection_allowed` se calcula y se expone (`CountryPack
  .reelection_allowed`) pero **no se aplica**: `world/elections.py::run_election` no tiene noción de
  "candidato saliente inelegible" — implementarlo tocaría la selección de candidatos de una forma que
  no entra en el presupuesto de A2. Documentado como pendiente para A3/A5.

**Régimen (`world/regime.py`)**
- El "reemplazo del presidente por la `military_junta`" y la restricción de `write` a partidos/
  sindicatos (columna "Actores" de la tabla del ADR) **no** se implementan como cambios al
  `ActorEngine`: `data/countries/argentina/actors/junta.yaml` existe como ficha de datos válida
  (`ActorSheet`, con su propio test), pero `engine/scheduler.py`/`engine/game.py` siguen cargando
  siempre `data/actors/*.yaml` de Aurora sin ningún mecanismo de override por país. En su lugar, el
  régimen actúa envolviendo el loop de `run()` desde afuera (sin tocar `advance_month`): antes de cada
  mes, si hay `regime_calendar`, se recalculan `sim.congress_enabled`/`sim.elections_enabled` (`AND`
  con lo que ya venían siendo) según el modo, y se le aplica a `sim.state` la variable `repression`
  (baja `protest_level`, sube `social_tension`, baja `institutional_confidence` — coeficientes de
  diseño, sin calibrar). Es más honesto llamar a esto "suspensión de instituciones + represión social"
  que "sustitución de actor", que es lo que realmente pasa.
- Un golpe **fallido** (marcado `"FALLIDO"` en `notes` de `events.csv`, p.ej. los carapintadas de
  1987-1990) mueve igual `regime_mode` a `coup` por 1 mes: el motor no tiene una noción de "intento"
  separada de "ocurrencia". Es una simplificación deliberada, no un error de lectura del calendario.
- `coup_propensity` por década = (golpes con fecha en esa década) / 120 meses, **uniforme dentro de la
  década** (no varía mes a mes ni pondera por cercanía a los golpes reales).
- La transición fuerza la vuelta a `democracy` a los 24 meses (tope del ADR), pero **no** fuerza una
  elección exacta ese mismo mes: sólo reactiva `elections_enabled`, y la elección cae en el próximo
  múltiplo de `term_length` de la corrida (mismo criterio de "no calzar fechas exactas" que el resto
  del calendario).

**Shocks históricos (ADR §4)**
- `sovereign_default`/`currency_run`/`war`/`imf_program` se implementan **enteramente** con el
  mecanismo aditivo que ya existía en `world/events.py` (`shocks.json` + `shock_*`/`field_bumps`): cero
  cambios al núcleo económico. Esto significa que "reservas −30 %"/"interest_cost ×0.5"/"k_k = 0" del
  ADR, que son efectos *proporcionales* o *anulan un coeficiente*, se aproximan con términos aditivos
  de magnitud fija (`data/countries/argentina/shocks.json`, cada uno con su propio `_note` explicando
  la aproximación): `sovereign_default` resta un monto fijo de reservas y suma un alivio fiscal fijo
  cada uno de los 24 meses en vez de anular `k_k`/reducir a la mitad `debt_interest_rate`; `imf_program`
  aproxima "`primary_spending` −1.5 forzado" como un término `shock_fiscal` (no toca el instrumento de
  `Policy` en sí) y usa un monto fijo de reservas (no el monto real de cada acuerdo, que varía);
  `currency_run` usa una duración fija de 6 meses (las instancias reales del calendario duran entre 4 y
  8); `war` no implementa el "−15 de aprobación si `outcome = lost`" porque el motor no modela un
  resultado de guerra como variable.
- `hyperinflation_regime` **nunca** se fuerza (`world/countries.py::NEVER_FORCED_SHOCK_IDS`): ni
  siquiera está en el catálogo de shocks (forzarlo tiraría `KeyError` en
  `ShockCatalog.apply_month`) — se espera que emerja solo, tal como pide el ADR.
- Un shock con `duration = N` deja de aparecer en `shocks_active` a partir del mes `N` (no `N+1`): el
  último efecto se dispara y el shock se desactiva en el mismo `apply_month`, mismo comportamiento que
  cualquier shock de Aurora (documentado ya para los de 1 mes en `engine/simulation.py`). No es
  específico de los shocks nuevos.

**Bimonetario (ADR §5)**
- El bloque `dollar_demand`/`fx_gap`/`external_debt_usd`/`default_risk`/`fx_regime` vive en
  `MonthRecord.external` (un `dict`, fuera de `WorldState`), no como campos nuevos del `WorldState` de
  20 variables: `WorldState` es un modelo `pydantic` `frozen=True` que entra en `ranges`/`clamp_state`/
  el hash de cada corrida de Aurora, y agregarle campos rompería esa superficie para el 100 % de las
  corridas que no usan el feature. Vive aparte, igual que `cohorts`/`vote_records`/etc. de ADR 005.
- Los coeficientes de `country.json → bimonetary` son de **diseño**, no calibrados contra series reales
  (eso es A3, fuera de alcance): sólo se verificó la *dirección* de cada relación (sube/baja con qué),
  no la magnitud.
- `external_debt_usd` se revaloriza con la misma forma funcional que ya usa Aurora para `public_debt`
  (vía `fx_share` y la devaluación real), no con una contabilidad real en dólares (que no cambia de
  valor en dólares al devaluar en pesos — lo que cambia es su peso relativo sobre variables en pesos).
- `fx_regime` es una **constante por corrida** (`--fx-regime`), no un calendario real: no hay
  detección automática de la ventana de convertibilidad 1991-2001 — hay que pasarla a mano
  (`--fx-regime peg` con `--start 1991-04`, por ejemplo).
- `--historical-exogenous` **ancla** `sim.exo` (la base del AR(1)+ruido de Aurora) al nivel real de
  cada mes, en vez de reemplazar exactamente el `exo_new` que usan las fórmulas de ese mes (eso hubiera
  exigido tocar `advance_month`). El resultado sigue de cerca la serie real sin ser una sustitución
  exacta mes a mes — documentado en el propio `engine/simulation.py::run()`.
- Proxy de `commodity_price`: no hay ninguna serie agropecuaria (soja/trigo) en `history/` a la fecha
  de A2, así que se usa el promedio simple de `gold_price_annual`/`oil_price_annual` (tal como permite
  el ADR: "usar gold/oil sólo si no existe una serie agropecuaria"), reescalado a base 100 en el primer
  año de la corrida. `world_demand` queda constante en 100 (no hay PIB mundial del Banco Mundial en
  `history/`), también tal como permite el ADR.
- El disparo endógeno de `sovereign_default` (`default_risk ≥ default_risk_threshold` sin
  `imf_program`/`sovereign_default` ya activo) se agrega a `forced_shocks` del mes siguiente desde el
  mismo loop de `run()`, reusando el mecanismo de shocks forzados — no hace falta ningún camino nuevo
  en `world/events.py`.

**Modo anual (ADR §6)**
- El estado inicial de una corrida anual usa el `initial_state` **de Aurora**, no `initial_states` del
  paquete (que sólo cubre 1983+, la única ventana con series mensuales suficientes): no hay un
  "estado real de 1880" con 20 variables que reconstruir. El ADR ya marca el modo anual como
  "exploratorio" en cada salida; este es el motivo concreto.
- El `regime_mode` de cada año se lee **directo de `politics/regimes.csv`** (remapeado a los 4 modos
  del motor), no se deriva con la máquina de estados de `world/regime.py`: a escala anual, sin datos
  mensuales que disparen `coup_propensity`/umbrales de estabilidad, reimplementar la lógica endógena
  hubiera sido menos fiel que usar el dato real de entrada que ya existe para ese período.
  `1930 -> coup`, `1931 -> dictatorship` verificado contra el golpe de Uriburu (test dedicado).
  Cohortes/medios/Congreso/elecciones apagados (ADR literal).
- Shocks aleatorios apagados por default en modo anual (`shocks_enabled=False`): el catálogo de
  `shocks.json` está calibrado en duraciones de MESES; sortear/aplicar un catálogo pensado para 12
  activaciones por año, a razón de una por año, no está re-escalado y produciría duraciones
  equivocadas. Los shocks *forzados* (`--historical-shocks`, vía `forced_shocks`) sí funcionan, tratando
  cada uno como si durara exactamente 1 turno-año.

**Estado inicial por fecha (ADR §2)** — ver también `scripts/build_argentina_initial_states.py`
(documenta cada regla en el propio código) y `country.json → initial_states_notes`.
- `gdp`/`real_wage`/`exchange_rate` son siempre `assumed = 100` (el valor neutro de Aurora) en las 8
  fechas: son índices de *nivel* sin unidad real (base 100 en Aurora), y no hay forma de mapear un
  nivel de PBI/salario/tipo de cambio real de una fecha a esa escala sin fijar una normalización
  arbitraria — sobre todo el tipo de cambio, con 5 monedas distintas entre 1810 y 2023
  (peso moneda nacional → ley 18.188 → argentino → austral → convertible).
- `gdp_growth` prioriza `gdp_per_capita_real` (Maddison, real) sobre `gdp_usd` (nominal, USD
  corrientes): la primera versión del script usaba `gdp_usd` primero y daba un +16 %/año para
  1988 — un artefacto de mezclar crecimiento real con inflación en dólares y variación cambiaria, no
  una medición real de actividad. Corregido antes de generar el `country.json` final.
- `government_approval` implementa la fórmula literal del ADR (`50 + 20·(voto_oficialismo − 0.45) /
  0.15`, acotada) con el resultado de la última elección presidencial de
  `politics/sources/electorAr_presi/*.csv` (archivo de otro agente, sólo lectura) para 7 de las 8
  fechas; `2023-12` queda `assumed` porque no hay `arg_presi_gral2023.csv`/`balota2023.csv`
  descargado en ese directorio a la fecha de A2.
- `institutional_confidence`/`political_stability` usan `v2x_libdem`/`v2x_civlib` de V-Dem (×100,
  acotado a [0,100]) como *proxy* — un correlato razonable, no una medición de esas variables
  específicas de Aurora (que no tienen análogo directo en V-Dem).
- `congress_support`, `social_tension`, `consumer_confidence`, `protest_level`, `inequality`,
  `crime_perception`: siempre `assumed` en las 8 fechas — no hay serie descargada ni un proxy que este
  agente considere razonable dentro del alcance de A2 (ver el `note` de cada una en el script).

**CLI / experimentos**
- `--historical-shocks`/`--historical-exogenous`/`--regime-mode`/`--fx-regime` sólo tienen efecto con
  `--country`; sin él, son ignorados silenciosamente en la lectura del código (no hay CLI que los
  acepte sin `--country` en primer lugar, `typer` los valida igual).
- `republica batch --country <id> --start <fecha>` resuelve el paquete para una corrida por semilla,
  pero no expone `--historical-shocks`/`--regime-mode`/modo anual (no pedidos para `batch` en el
  enunciado de esta tarea).
- `experiment` (`base: {country: ..., start: ..., months: ...}`) construye `data_dir` apuntando a la
  misma carpeta fusionada de `load_country_pack`: los overrides `country.*` de `arms`/`sweep` siguen
  funcionando sin cambios (es un `country.json` real en disco). No hay soporte de `regime`/
  `historical_shocks`/`bimonetary`/modo anual desde `experiment` en A2 (no pedidos para `experiment`
  en el enunciado, sólo la clave `country`).
