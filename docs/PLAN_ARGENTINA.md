# República Artificial: Argentina — plan del proyecto paralelo

> Transformar Aurora en Argentina **sin romper Aurora**: un "paquete de país" con datos históricos reales
> (1810–2023), un modo de régimen (democracia, golpe, dictadura), un pipeline de calibración contra series
> reales y un protocolo de validación que diga con números hasta dónde el modelo reproduce la historia
> y dónde no. Aurora sigue siendo el laboratorio; Argentina es el banco de pruebas contra la realidad.

## 0. Tres reglas que no se negocian

1. **Ningún número histórico se inventa.** Cada serie de `data/countries/argentina/history/` viene de
   un archivo descargado, con URL, licencia, fecha de descarga y hash en `SOURCES.md`. Lo que no se
   pudo descargar queda `NaN` y aparece en `coverage.md` como faltante, con el script para cargarlo
   desde tu máquina (INDEC, BCRA, datos.gob.ar están bloqueados desde este entorno; GitHub no).
2. **La cronología política (presidentes, golpes, elecciones) se escribe con fuente.** V-Dem da el
   régimen año a año desde 1810; los nombres y fechas se cargan como hechos públicos con
   `source: general_knowledge` y pasan por una revisión de hechos independiente antes de usarse.
3. **Calibrar ≠ ajustar hasta que dé.** Se calibra en un período, se valida en otro que el modelo no
   vio, y se publica el error en ambos. Un modelo que reproduce 1989 porque se le forzó el shock de
   1989 no "predijo" nada: lo que se mide es si, dado el estado de 1988 y los shocks exógenos reales,
   la dinámica interna (inflación, salarios, aprobación, elección) va en la dirección y magnitud correctas.

## 1. Qué cambia respecto de Aurora (ADR 011)

| Aurora | Argentina |
|---|---|
| 8 provincias inventadas | 24 jurisdicciones agrupadas en 8 regiones (CABA, GBA, Pampeana, NOA, NEA, Cuyo, Patagonia, Córdoba–Santa Fe) con población y peso económico reales por censo |
| 5 partidos fijos | Sistema de partidos **por época**: 1916–1930 (UCR, conservadores, PS), 1946–1955 (peronismo, UCR), 1983–2001 (PJ, UCR, FREPASO, UCeDé, provinciales), 2003–2023 (FpV/PJ, PRO/JxC, UCR, FIT, LLA) |
| Elecciones cada 48 meses, siempre | **Modo de régimen**: `democracy` (elecciones), `coup` (evento que suspende elecciones y reemplaza al presidente), `dictatorship` (sin Congreso ni elecciones; represión como variable), `transition`. V-Dem provee la serie real para validar cuándo el modelo debería estar en cada modo |
| Shocks aleatorios | **Shocks históricos forzados** (crisis del 30, 1975 Rodrigazo, 1982 Malvinas/deuda, 1989 hiper, 1991 convertibilidad, 2001 corralito/default, 2008 soja y crisis global, 2018 corrida, 2020 pandemia, 2023 sequía) como calendario, más shocks aleatorios calibrados a la frecuencia observada |
| Sector externo simple | Bimonetarismo (demanda de dólares como variable), deuda en USD con default posible, acuerdos con el FMI como concesión/condicionalidad, precio de commodities real (soja, trigo, petróleo) como exógena |
| Turno mensual desde 2027 | Turno mensual con calendario real; para 1810–1943 se corre en **modo anual** (12 turnos agregados) porque solo hay datos anuales |
| Un mandato de 48 meses | Mandatos de 6 años (1853–1994) o 4 (1994+) según la Constitución vigente; reelección según la época |

Lo que **no** cambia: el motor, el catálogo de acciones, los permisos, la memoria, los evals. Un
país es datos y un puñado de reglas de régimen, no otro simulador.

## 2. Fases, agentes y modelos

| Fase | Qué | Modelo Claude Code | Runtime |
|---|---|---|---|
| **A0 Datos** | Descargar y normalizar todo lo alcanzable: Maddison (PIB pc 1810+), Banco Mundial (PIB, IPC, deflactor, población 1960+), tipos de cambio anuales, oro/petróleo, V-Dem completo (régimen, libertades, 1810+), series mensuales de repos públicos con snapshots de INDEC/BCRA (IPC, tipo de cambio oficial y paralelo, reservas, tasa). `history/*.csv` tidy + `SOURCES.md` + `coverage.md` | **Sonnet 5** descarga y normaliza; **Opus 5** audita procedencia y consistencia (¿el IPC mensual anualizado coincide con el anual del BM?) | — |
| **A1 Cronología** | `events.csv` (presidentes, golpes, elecciones con resultados, crisis, acuerdos FMI), `regimes.csv` por año cruzado con V-Dem, `parties_<época>.json`, `provinces.csv` con censos | **Sonnet 5** redacta con fuentes; **Opus 5** verifica hechos y marca lo dudoso | — |
| **A2 Paquete de país** (ADR 011) | `data/countries/argentina/` con loader; `republica run --country argentina --start 1983-12 --months 72`; modo de régimen; calendario de shocks; sector externo; partidos por época; modo anual para 1810–1943 | **Fable 5.1** diseña el ADR y las fórmulas nuevas (bimonetarismo, default, régimen); **Sonnet 5** implementa; golden hashes de Aurora intactos | reglas |
| **A3 Calibración** | `republica calibrate --country argentina --train 1993-01:2015-12 --holdout 2016-01:2023-12`: ajuste de los ~90 coeficientes por optimización sin gradiente (CMA-ES o Nelder-Mead sobre el error de simulación con shocks exógenos reales), con regularización hacia Aurora; reporte con RMSE por variable en train y holdout, signos de respuesta a shocks, y comparación con un baseline ingenuo (persistencia) | **Fable 5.1** diseña la función objetivo y el protocolo; **Sonnet 5** implementa; **Opus 5** revisa que no haya fuga de información del holdout | reglas (miles de corridas) |
| **A4 Validación histórica** | Tres pruebas con hipótesis registradas antes: (1) 1988→1990: ¿la dinámica interna produce hiperinflación dado el estado de 1988 y los shocks exógenos? (2) 1998→2002: ¿colapso con convertibilidad rígida? (3) 2016→2023: ¿la inflación se acelera y el oficialismo pierde? Más un control: Aurora sin calibrar sobre los mismos períodos | **Opus 5** analiza y redacta; **Fable 5.1** revisa la epistemología | reglas |
| **A5 Actores argentinos** | Fichas por época (presidentes, ministros, CGT, UIA, Sociedad Rural, Clarín/La Nación/Página 12, gobernadores clave) con ideología e intereses; los mismos evals de Aurora; comparación `rules` vs `llm` con Ollama en tu máquina | **Haiku 4.5** fichas; **Opus 5** revisión; **Sonnet 5** integración | Ollama local (tuyo) |
| **A6 Contrafácticos** | `experiments/argentina/*.yaml`: convertibilidad hasta 2005, BC independiente desde 1991, sin default 2001, etc. Con la frase de limitaciones en cada reporte | **Sonnet 5** corre; **Opus 5** discute | reglas / sustituto |
| **A7 1810–1943** | Modo anual con Maddison + V-Dem; sin cohortes ni Congreso detallado; solo régimen, actividad, precios (donde haya), golpes. Exploratorio, marcado como tal | **Sonnet 5** | reglas |

Orden: A0 y A1 en paralelo → A2 → A3 → A4 → A5 → A6 → A7. A4 es el hito: sin validación publicada, no
hay contrafácticos.

## 3. Datos: qué se puede cargar desde dónde

| Serie | Período | Fuente alcanzable | Estado |
|---|---|---|---|
| PIB per cápita real | 1810–2018 | Maddison Project 2020 (vía OWID en GitHub) | descargable |
| PIB nominal USD, crecimiento, población | 1960–2023 | Banco Mundial (vía `datasets/gdp`, `datasets/population` en GitHub) | descargable |
| Inflación anual (IPC y deflactor) | 1960–2023 | Banco Mundial (vía `datasets/inflation`) | descargable |
| Tipo de cambio anual | 1960–2023 | `datasets/exchange-rates` | descargable |
| Régimen, elecciones, libertades, corrupción, protesta | 1810–2023 | V-Dem v14 completo (`vdemdata` en GitHub, RData) | descargable |
| IPC mensual, dólar oficial y paralelo, reservas, tasa | 1943+/1990+ | Repos públicos con snapshots de INDEC/BCRA/Cavallo–Bertolotto | verificar repo por repo |
| Desempleo, pobreza, salario real | 1974+ (EPH), 1983+ | INDEC / datos.gob.ar | **bloqueado**: script para tu máquina |
| Deuda pública, resultado fiscal | 1960+ | MECON / FMI WEO | **bloqueado**: script para tu máquina |
| Aprobación presidencial | 1983+ | encuestadoras (no hay serie libre) | proxy: V-Dem + resultados electorales |

## 4. Protocolo de honestidad

Cada reporte de A3–A7 incluye: período de calibración y de holdout; error del modelo y del baseline
ingenuo en ambos; qué shocks fueron forzados (y por lo tanto no son mérito del modelo); qué variables
son proxies; y la frase fija: *"Estos resultados describen el comportamiento de República Artificial
calibrada con datos de Argentina; no son evidencia sobre lo que hubiera pasado."*

## 5. Primer entregable

`data/countries/argentina/history/` con todo lo descargable, `SOURCES.md`, `coverage.md`, `events.csv`
y `regimes.csv` auditados, y el ADR 011 aprobado. Recién entonces se toca código.

## 6. Estado al cierre de la primera iteración y qué sigue

A0–A4 ejecutadas. Datos y cronología: 23 series reales con procedencia, cronología 1810–2023 verificada
contra V-Dem. Paquete de país, calibración y validación: hechos y corridos. **Resultado de la
validación: negativo en las tres pruebas**, con diagnóstico mecánico en
`data/countries/argentina/validation/a4_main/report.md`. Lo que aprendimos manda los próximos pasos:

| Causa estructural encontrada (A4) | Cambio en el motor (ADR 012) | Estado tras A5 (recalibración, este reporte) |
|---|---|---|
| La ecuación de precios es contractiva (`rho_pi + c_e < 1`): la hiperinflación endógena es algebraicamente imposible | Expectativas con régimen: `rho_eff = rho_pi + rho_slope·clamp(...)`, dominancia fiscal no lineal (`c_s·seigniorage_pressure/money_demand`) | **Resuelto a nivel de mecanismo** (`tests/test_macro_regime.py`, ADR 012 §7 test 2: hiperinflación alcanzable desde 1988-06 en 20/20 semillas, no espuria desde 2003-06 en 0/20) — con los coeficientes SIN calibrar, el mismo mecanismo genera hiperinflación **espuria** desde 2019-12 (20/20 semillas, hallazgo del agente de ADR 013). Con los coeficientes CALIBRADOS de `a5b_macro`: 0/20 en `hyperinflation` desde 2019-12, pero **20/20 en `collapse`** (política, no precios) antes del mes 27 — la calibración desplaza el modo de falla, no lo elimina (ver `data/countries/argentina/calibration/a5b_macro/report.md` y V1/V3/V4 abajo). |
| `--fx-regime peg` es inerte: `fx_regime` no entra en `step_economy` | `fx_regime` gobierna `de`, la intervención y `k_k`; salida forzada con reservas bajo `R_min` | **Resuelto** (ADR 012 §7 test 3: `peg` y `float` dan trayectorias distintas; salida forzada en 17/20 semillas desde 1998-01). `validation/argentina.py::run_test_arm` usa `fx_regime=pack.fx_regime_auto` (el régimen real por fecha) en vez de un default fijo; verificado de nuevo en A6 (`fx_regime_inertness` de V2: `peg` ≠ `float`). |
| Reservas sin ancla de balance de pagos | `reserves' = reserves + current_account + capital_account − intervention_usd`, con `exports`/`imports` reales y `default_risk` sobre deuda USD/exportaciones | **Resuelto a nivel de mecanismo** (ADR 012 §7 test 4). `default_risk` arranca alto incluso en períodos solventes (documentado como hallazgo honesto en las Notas de implementación del ADR 012); no se corrigió porque el intento rompía el test de recuperación — pendiente de la próxima ronda. |
| Calendario incompleto: sin crisis 1998–99, sin corralito/default 2001, sin sequía 2018 | — | **Resuelto** (A5, punto 1 de esta recalibración): 8 filas nuevas en `shocks_calendar.csv` (1962, 1981, Plan Austral 1985, crisis 1998–99, corralito/default/salida de la convertibilidad dic-2001/ene-2002, sequía 2018), todas `reviewed_by: pending` en `politics/PENDING_FACTCHECK.md`. |
| Calibrar sobre 1993–2015 (ventana reversiva) empeora los episodios extremos | Ventana con episodios extremos + pérdida ponderada por colas | **Implementado, con resultado mixto y honesto** (A5, punto 3): train `1992-01:2023-12`, holdout `1983-12:1991-12`, `--loss heavy`. En TRAIN el calibrado queda a la par o levemente peor que la persistencia en la mayoría de las variables. En HOLDOUT mejora mucho a Aurora sin calibrar y a `a3_main` en inflación (h=12 RMSE: 4.37 vs 9.75 vs 6.69) pero sigue por detrás de la persistencia (4.37 vs 4.01) — 155 parámetros calibrados no baten al baseline ingenuo. Detalle completo: `docs/CALIBRATION_LOG.md` sección "Corrida `a5b_macro`". |
| Aprobación cae a 0 y 50/50 corridas colapsan antes de 2023 | Recuperación de largo plazo de confianza/tensión (ADR 012 §5) | **Mecanismo presente pero NO evita el colapso en la validación** (ADR 012 §7 test 5 aislado: 20/20 semillas de 2003-06 a 2015-12 sin colapso — pero en A6, arrancando de estados iniciales REALES con shocks forzados reales, V1/V3/V4 dan 50/50 `collapse` cada una). El mecanismo de recuperación no alcanza a compensar el punto de partida real (aprobación/confianza/tensión de 1988, 2016 o 2019) combinado con la calibración actual. |

**A6 (`data/countries/argentina/validation/a6_macro/`): V1–V4 corridas, 52.5s de pared, 50 semillas.**

| prueba | veredicto calibrado | veredicto Aurora | muestra (train/holdout de `a5b_macro`) |
|---|---|---|---|
| V1 (1988→1990, hiperinflación) | NO CUMPLIDA (0% vs. pedido >50%) | CUMPLIDA (100%) | **HOLDOUT** (única prueba genuina de generalización) |
| V2 (1998→2002, default/colapso) | **CUMPLIDA** (56% vs. pedido >50%) | NO CUMPLIDA (22%) | in-sample |
| V3 (2016→2023, inflación+elecciones) | NO CUMPLIDA (47.5% infl. vs. pedido >80%) | NO CUMPLIDA (1710%, pero 0% aciertos) | in-sample |
| V4 (2019-12→2023, partidos por época ADR 013) | NO CUMPLIDA (infl. 56.7% vs. >100%; derrota 0% vs. >70%) | NO CUMPLIDA | in-sample |
| C (control) | — | **CUMPLIDA** (Aurora falla 3 de 4) | — |

De las cuatro pruebas, **solo V1 cae en el holdout real** (`1983-12:1991-12`) de `a5b_macro`; V2, V3
Y V4 caen dentro del train (`1992-01:2023-12`) — más restrictivo de lo que se pensaba antes de correr
A6 (no solo V3). Hallazgo transversal: en V1/V3/V4 el brazo calibrado termina en `collapse` en el
**100 % de las semillas** (nunca en `hyperinflation`, a diferencia de Aurora); en V4 esto significa
que NINGUNA semilla (calibrada ni Aurora) llega a celebrar la elección de fin de mandato — la
hipótesis electoral de V4 no se pudo evaluar por falta de denominador, no porque el oficialismo haya
ganado. Detalle completo, incluida la lectura mecánica de por qué, en
`data/countries/argentina/validation/a6_macro/report.md` y `docs/CALIBRATION_LOG.md`.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de
Argentina; no son evidencia sobre lo que hubiera pasado.

## 7. Estado al cierre de la segunda iteración (ADR 012–014) y qué sigue

Hecho: ADR 012 (macro con régimen, 6/6 tests), ADR 013 (tres épocas de partidos/actores/lealtades;
LLA no gana en el modelo: test en `xfail` con diagnóstico), A5 (`a5b_macro`, tras descartar `a5_macro`
por el bug del objetivo), A6 (V1–V4) y ADR 014 (backtest 1916–2022, `b1_a5b`). Después, ADR 015
(transiciones de régimen endógenas, `features.regime_endogenous_transitions`, default off).

| Hallazgo de esta ronda | Qué sigue |
|---|---|
| El calibrado no supera a persistencia ni en train ni en holdout | **Mecanismo hecho** (ADR 017): `republica calibrate --by-regime` corre un CMA-ES por grupo de régimen cambiario (`peg`+`crawl` / `float` / `control`; train stride 3 → 41 / 54 / 29 meses de arranque) y escribe `{by_regime, default}`; el vector se elige por el `fx_regime` de `--start` y cambia en caliente si el régimen simulado sale de su grupo. Falta la corrida completa (`a7_by_regime`, comando en ADR 017 §8) y evaluar la hipótesis registrada |
| Desde 2019-12 el calibrado colapsa (100 %) antes de la elección de 2023 | Revisar la terminación por `collapse` y la recuperación §5 del ADR 012 con datos de aprobación reales (no hay serie) |
| Brazo calibrado sin dato 1916–1960: los `Coefficients` legacy no reciben señal del objetivo macro y desbordan en modo anual | **Hecho** (ADR 017 §1–2): `build_parameter_space(include_macro=True)` excluye los 8 que `step_macro_economy` no lee (`rho_pi`, `c_e`, `c_r`, `c_g`, `c_f`, `k_w`, `k_tb`, `k_conf`) y los fija en el valor de Aurora; `world/annual.py` acota `g_m` a `[-50, +50] %` mensual con contador (`g_m_clamped`). Con `a5b_macro` el backtest anual pasa de descartar el 100 % de las semillas calibradas a 0 — pero corre CONTRA la guarda (`g_m_clamped > 0`), así que 1916–1960 con `a5b_macro` sigue sin ser evidencia sobre el modelo; hace falta recalibrar |
| ~~Régimen: 0 % de acierto cuando la ventana arranca en golpe o democracia restringida~~ **RESUELTO (ADR 015)** | Causa real: el motor arrancaba SIEMPRE en `democracy` (nunca se le pasaba el régimen inicial real). Se agregó un modelo de riesgo (hazard) mensual Weibull por transición, con las tasas base estimadas por máxima verosimilitud de las 6 dictaduras y los 7 períodos civiles 1916-2023, más `restricted_democracy` como quinto modo, detrás de `features.regime_endogenous_transitions` (default off). Medido (`b2_regime_probe_{off,on}`, 1961-1983, N=138): golpe **0 % → 100 %**, democracia restringida **0 % → 100 %**, dictadura 36,1 % → 63,9 %, democracia 50,0 % → 50,0 % (sin empeorar); total del objetivo régimen **27,5 % → 72,5 % (+44,9 pp)**. Sigue abierto: el 36 % restante del estrato dictadura son las ventanas donde el objetivo es volver a democracia, y ahí el límite es que la corrida termina por `collapse` al mes 10-17 (ver la fila de la terminación por `collapse`), no el hazard |
| Holdout sin tipo de cambio mensual antes de 1992 | **Resuelto** (2026-09-19): `exchange_rate_annual_linked.csv` 1962–2012 desde el indicador `PA.NUS.FCRF` del Banco Mundial vía mirror (SOURCES.md fuente 22, `trust` A), ya enlazado a través de las cuatro redenominaciones y validado con cinco cruces (`consistency.md` §14: monotonía 1962–1991 sin caídas, empalme con 1992-01 al 3.78 %, anual vs mensual 1992–2012 al 0.77 % medio). `RealData.fx_level()` la interpola geométricamente, no linealmente. Falta todavía: mensual real antes de 1992, y 1952–1961 sin dato. |
| Fase 4 con Ollama y APIs oficiales: bloqueadas también desde la sesión en la nube | Correr `scripts/fase4_ollama.sh` y `scripts/fetch_argentina_local.py` desde una red sin proxy |

Estos resultados describen el comportamiento de República Artificial calibrada con datos de
Argentina; no son evidencia sobre lo que hubiera pasado.
