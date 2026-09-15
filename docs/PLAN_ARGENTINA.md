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

| Causa estructural encontrada | Cambio necesario en el motor (ADR 012, pendiente) |
|---|---|
| La ecuación de precios es contractiva (`rho_pi + c_e < 1`): la hiperinflación endógena es algebraicamente imposible | Expectativas con régimen: indexación y persistencia que suben con la inflación pasada (`rho_pi` función de π), o un término de dominancia fiscal no lineal (emisión ∝ déficit / demanda de dinero, con demanda de dinero que cae con π) |
| `--fx-regime peg` es inerte: `fx_regime` no entra en `step_economy` | Que el régimen cambiario gobierne `de_raw`, la intervención y `k_k`; un `peg` con reservas cayendo debe terminar en salida forzada (devaluación) |
| Reservas sin ancla de balance de pagos: `reserves_target` fijo de Aurora (10.000) no muerde con 27.914 reales | Reservas = cuenta corriente (exportaciones ∝ commodities y tipo de cambio real, importaciones ∝ PIB) + cuenta capital (∝ tasa real, riesgo, `dollar_demand`); `default_risk` sobre deuda en USD / exportaciones |
| Calendario incompleto: sin crisis 1998–99, sin corralito/default 2001, sin sequía 2018 | Completar `shocks_calendar.csv` desde `events.csv` (ya tiene los eventos) |
| Calibrar sobre 1993–2015 (ventana reversiva) empeora los episodios extremos | Calibrar con ventanas que incluyan al menos un episodio extremo y con pérdida ponderada por colas; o calibrar por regímenes |
| Aprobación cae a 0 y 50/50 corridas colapsan antes de 2023 | Mecanismos de recuperación de largo plazo de confianza y tensión (también pendiente en Aurora) |

Orden sugerido: ADR 012 (precios con expectativas, régimen cambiario efectivo, balance de pagos) →
completar calendario → recalibrar con ventana 1975–2023 y holdout por episodios → repetir A4 con las
mismas hipótesis. Después, A5 (actores argentinos) y A6 (contrafácticos) tienen sentido; antes, no.
