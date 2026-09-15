# Consistencia — cruces entre fuentes

Tres cruces, corridos con `python3` sobre los CSV ya escritos (script en
`/tmp/.../scratchpad/build/consistency.py` de esta sesión; reproducible leyendo los CSV de
este directorio con cualquier herramienta). Ninguno de estos números se usó para ajustar las
series — son un chequeo posterior, no una calibración.

## 1. IPC mensual compuesto a anual vs. IPC anual del Banco Mundial

`inflation_cpi_monthly.csv` (fuente: jmtelechea, IPC nacional empalmado) se agregó a
variación % anual componiendo los 12 meses de cada año calendario con datos completos
(`∏(1+r_m) - 1`), y se comparó contra `inflation_cpi_annual.csv` (Banco Mundial,
`datasets/inflation`, 1961–2023). Años en común con los 12 meses disponibles: 1998–2023
(26 años; el CSV mensual arranca en 1997-02, así que 1997 queda incompleto y se excluyó).

| Período | diferencia absoluta media (pp) | n años |
|---|---|---|
| 1998–2006 | 4.4 | 9 |
| 2007–2015 (INDEC intervenido) | 2.9 | 9 |
| 2016–2021 | 3.3 | 6 |
| 2022–2023 | **50.5** | 2 |
| **Todo el período** | **7.2** | 26 |

Detalle 2022–2023 (el desvío grande):

| Año | compuesto mensual (%) | Banco Mundial anual (%) | diferencia (pp) |
|---|---|---|---|
| 2022 | 94.8 | 69.9 | +24.9 |
| 2023 | 211.4 | 135.4 | +76.0 |

**Discrepancia detectada y marcada**: para 2022–2023 el IPC mensual compuesto da una
inflación mucho más alta que la cifra anual del Banco Mundial. Es consistente con que el
indicador del Banco Mundial (`FP.CPI.TOTL.ZG`, típico de estos datasets) mide variación del
**promedio anual del índice**, no diciembre-contra-diciembre, mientras que componer 12 meses
da la variación **diciembre-contra-diciembre** — ambas son formas legítimas de resumir un
año de inflación, pero no son la misma cifra y la brecha crece exactamente cuando la
inflación acelera dentro del año (como 2022–2023), que es cuando promedio-anual y
diciembre-a-diciembre más se separan. No es necesariamente un error en ninguna de las dos
series; queda señalado para que el pipeline de calibración (Fase A3) no mezcle ambas
convenciones sin ajustar.

Para 2007–2015 (período de intervención de INDEC ampliamente documentado, aunque esa
documentación no se pudo descargar desde este entorno) la diferencia media (2.9 pp) es
similar a la de 1998–2006 y 2016–2021 — el IPC "empalmado" que usamos evita precisamente el
IPC oficial manipulado de esos años (lo reemplaza por provinciales), así que no muestra el
quiebre esperado si el IPC del Banco Mundial en esos años fuera el oficial-manipulado en
vez de una revisión posterior. Esto sugiere que la serie del Banco Mundial en
`datasets/inflation` ya incorpora una revisión/corrección para 2007–2015, no el dato
oficial original — dato a tener en cuenta, no confirmado con una tercera fuente desde este
entorno.

## 2. Maddison (PIB per cápita real) vs. Banco Mundial (PIB nominal / población)

No son la misma magnitud (Maddison: 2011 US$ PPP, real; Banco Mundial: US$ corrientes,
nominal), así que no deberían coincidir en nivel — esto es un chequeo de **orden de magnitud
y dirección**, no de igualdad.

| Año | Maddison GDP pc (2011 US$ PPP) | Banco Mundial GDP/población (US$ corrientes) |
|---|---|---|
| 1983 | 11,775 | 3,725 |
| 1988 | 11,244 | 3,994 |
| 1993 | 12,927 | 6,932 |
| 1998 | 15,186 | 8,219 |
| 2003 | 13,089 | 3,320 |
| 2008 | 18,520 | 8,944 |
| 2013 | 19,873 | 12,964 |
| 2018 | 18,556 | 11,753 |

CAGR 1983–2018: Maddison (real, PPP) = **1.31 %/año**; Banco Mundial (nominal, US$
corrientes) = **3.34 %/año**. La diferencia es esperable: el segundo mezcla crecimiento real
con inflación en dólares (apreciación/depreciación del propio dólar y de precios en
dólares), además de las devaluaciones grandes del período (1989, 2002, 2018) que bajan el
PIB en US$ corrientes sin que caiga en términos reales-PPP en la misma proporción. La
caída de 1998→2003 en la columna del Banco Mundial (de 8,219 a 3,320) frente a la caída
mucho más chica de Maddison (15,186→13,089) es exactamente la firma esperada de la
devaluación de 2002 (el PIB en dólares corrientes se derrumba con el tipo de cambio; el PIB
real no cae tanto). Confirma que ambas series están capturando la crisis 2001–2002 en la
dirección correcta, aunque con magnitudes muy distintas por diseño.

## 3. V-Dem `e_miinflat` vs. Banco Mundial IPC anual

`vdem_argentina.csv` trae `e_miinflat` ("inflación", variable externa importada por V-Dem
desde otras bases). Se comparó contra `inflation_cpi_annual.csv` para 1961–2010 (años en
común con dato en ambas).

- n = 50 años, diferencia absoluta media = **14.9 pp**.
- Coincide en signo y orden de magnitud en episodios clave: hiperinflación 1989
  (V-Dem 3,079.5 % vs. Banco Mundial 3,046.1 %, diff 33.4 pp — **muy cercano**) y 1990
  (V-Dem 2,314.0 % vs. Banco Mundial 2,078.3 %, diff 235.6 pp — mismo orden de magnitud,
  ambas ">2000 %").
- Los años con mayor desvío relativo están en la segunda mitad de los 2000 (2004: V-Dem 4.4 %
  vs. Banco Mundial 18.4 %, diff −13.9 pp; 2008: 8.6 % vs. 23.2 %, diff −14.6 pp) — la misma
  ventana señalada en el cruce 1 como sospechosa de reflejar el IPC oficial manipulado en una
  de las dos fuentes (probablemente `e_miinflat`, que documentación de V-Dem describe como
  tomada de fuentes externas que en esos años pudieron seguir el IPC oficial de INDEC sin
  corregir).

**Conclusión de los tres cruces**: las series coinciden razonablemente bien en los episodios
extremos (hiperinflación 1989–1990, crisis 2001–2002) que son los que más importan para
validar la dinámica del modelo (Fase A4), y divergen sobre todo en 2007–2015 (INDEC
intervenido — se sospecha que alguna de las fuentes no corrigió el dato oficial de esos años)
y en 2022–2023 (probable diferencia de convención promedio-anual vs. diciembre-a-diciembre,
no necesariamente un error). Ninguna discrepancia se "corrigió": quedan las tres series tal
como se descargaron, con esta nota.

## 4. Dólar blue: `ahierro/ipc_csv_processor` (`cotizacion_blue.csv`) vs. `exchange_rate_parallel_monthly.csv` (DiLoretoT/argentinadatos.com)

Se calculó el cierre de fin de mes de `cotizacion_blue.csv` (2268 cotizaciones diarias,
2008-01-02 → 2026-08-21) y se comparó, mes a mes, contra `exchange_rate_parallel_monthly.csv`
existente (2011-01 → 2026-09).

- **Meses en común**: 188 (2011-01 → 2026-08).
- **Diferencia absoluta media**: **1.92 %**.
- **Diferencia absoluta máxima**: **12.5 %**, en 2011-10 (blue=4.50 vs. existente=4.00 —
  ambas fuentes muestran el arranque del "cepo cambiario" de fines de 2011, con cotizaciones
  ARS/USD entre 4 y 4.5, el desvío es de fin-de-mes exacto vs. cotización de una plataforma
  distinta, no un error de escala).
- Ejemplos de los extremos de la serie: 2011-01 (blue 4.15 vs. existente 4.00), 2026-04
  (blue 1430.0 vs. existente 1400.0), 2026-08 (blue 1550.0 vs. existente 1555.0).

**Umbral del enunciado**: 1.92 % < 5 %, así que se usó `cotizacion_blue.csv` para
**extender hacia atrás** los 36 meses 2008-01 → 2010-12 (no cubiertos por la fuente
existente), en `exchange_rate_parallel_monthly_linked.csv` (ver `SOURCES.md` fuente 14).
No se "corrigieron" los 188 meses en común: la parte 2011+ del archivo `_linked` repite
exactamente los valores de `exchange_rate_parallel_monthly.csv`, no los de
`cotizacion_blue.csv`.

## 5. Tipo de cambio oficial: `ahierro/ipc_csv_processor` (`tipo_de_cambio.csv`) vs. `exchange_rate_official_monthly.csv` (DiLoretoT/BCRA)

Mismo ejercicio para el oficial: fin de mes de `tipo_de_cambio.csv` (6032 cotizaciones
diarias BCRA "cierre vendedor", 2002-01-11 → 2026-08-21) contra
`exchange_rate_official_monthly.csv` existente.

- **Meses en común**: 296 (2002-01 → 2026-08).
- **Diferencia absoluta media**: **0.0021 %** — prácticamente idéntico.
- **Diferencia absoluta máxima**: **0.63 %**, en 2026-08 (tipo_de_cambio.csv=1499.0 vs.
  existente=1508.5 — la única fecha con una diferencia visible, probablemente el último
  cierre disponible en cada fuente al momento del snapshot).
- Todos los demás meses coinciden al centavo o con diferencias de redondeo.

Esto es la validación más fuerte de las tres: dos repos completamente independientes,
descargando el mismo dato BCRA por caminos distintos, coinciden casi exactamente. No se
generó ningún archivo nuevo acá porque `tipo_de_cambio.csv` no cubre ningún período anterior
a 1992 (arranca en 2002, después que la fuente ya usada) — ver `SOURCES.md` fuente 15.

## 6. Tipo de cambio anual Clio Infra: por qué se cortó en 1951

`clio_infra_exchange_rates.csv` (vía `unbalancedparentheses/forex-centuries`, fuente 16)
declara valores de Argentina para 1879-2013, pero no todos son usables:

| Rango | Valores | Interpretación |
|---|---|---|
| 1879–1951 | 1.04 → 7.50 (crecimiento gradual, consistente con la historia conocida del peso moneda nacional/oro) | usable, es lo que se ingirió |
| 1952–1961 | `0.0` exacto en los 10 años | artefacto: un tipo de cambio no puede ser cero |
| 1962–1974 | `8.7e-12` → `5.0e-11` | artefacto de escala: 11-12 órdenes de magnitud por debajo de cualquier cotización real de la época |
| 1975–1988 | `3.7e-10` → `8.8e-4` | sigue creciendo exponencialmente pero nunca alcanza una escala interpretable como "pesos por dólar" de esos años |
| 1989–2001 | 0.042 → 0.9995 | vuelve a ser interpretable (1991-1992: convertibilidad 1 peso = 1 USD, valores ≈0.99-1.00, correcto) |
| 2002–2013 | 2.90 → 5.46 | interpretable (post-devaluación 2002), pero se excluyó igual por prudencia: no hay forma de verificar, sin más trabajo, que la transición 2001→2002 en **esta fuente específica** esté en la misma escala que 1992-2001, dado que el tramo intermedio (1952-1988) está roto |

La lectura más probable es que Clio Infra (o el pipeline de `forex-centuries` al bajarlo)
aplicó un único factor de conversión "a pesos actuales" pensado para des-hacer las
redenominaciones de 1970/1983/1985/1992 sobre una serie más larga, y ese factor no es
correcto (o no se aplicó) en el tramo 1952-1988. No se intentó adivinar el factor correcto
para recuperar esos años: se excluyeron. `exchange_rate_annual.csv` termina en 1951; el
hueco 1952-1991 queda documentado en `coverage.md` → Faltantes, y 1992 en adelante ya está
cubierto (mensual) por `exchange_rate_official_monthly.csv`.

## 7. Inflación anual Clio Infra vs. Banco Mundial (y por qué se parece tanto al cruce 3)

`clio_infra_inflation.csv` tiene 50 años en común con `inflation_cpi_annual.csv` (1961-2010).
Comparados directamente:

- diferencia absoluta media = **14.94 pp**, máxima **235.6 pp** en 1990 (Clio 2313.96 % vs.
  Banco Mundial 2078.32 %).
- 1989: Clio 3079.46 % vs. Banco Mundial 3046.09 % (diff 33.4 pp).

Estos números son, hasta el redondeo, **los mismos** que el cruce 3 (`e_miinflat` de V-Dem
vs. Banco Mundial: 1989 diff 33.4 pp, 1990 diff 235.6 pp, media 14.9 pp sobre los mismos 50
años). Eso no es casualidad: la variable `e_miinflat` de V-Dem es una variable **importada**
de fuentes externas, y todo indica que para Argentina 1961-2010 esa fuente es, directa o
indirectamente, la misma serie de Clio Infra usada acá (o una fuente común de la que derivan
ambas). En la práctica esto quiere decir que el cruce 3 (`consistency.md` arriba) y este
cruce 7 **no son dos validaciones independientes** de `inflation_cpi_annual.csv` — son la
misma comparación vista desde dos vendors distintos. La única validación genuinamente
independiente de `inflation_cpi_annual.csv` (Banco Mundial) que queda en este directorio es
el cruce 1 (mensual empalmado, jmtelechea, compuesto a anual).

---

## Pasada del 2026-09-15 (mirrors de GitHub; secciones 8–13)

Cruces corridos con `scripts/check_argentina_history_consistency.py --bcra-data <clon> --argendata <clon>`
(reproducible: lee solo los CSV tidy de este directorio, `raw/` y los dos clones a los
commits de `SOURCES.md` fuentes 18–19). Ninguno de estos números se usó para ajustar series.

## 8. IPC mensual del BCRA (variable 27) vs `inflation_cpi_monthly.csv` (jmtelechea)

355 meses en común (1997-02 → 2026-08):

| Período | diferencia absoluta media (pp) | máxima (pp) | meses con > 0.1 pp | n |
|---|---|---|---|---|
| 1997–2006 | **0.023** | 0.05 (2002-09) | **0** | 119 |
| 2007–2015 (INDEC intervenido) | **0.881** | 2.39 (2007-08: 2.99 vs 0.60) | 104 | 108 |
| 2016–2026 | 0.122 | 2.84 (2016-04: 6.24 vs 3.40) | 14 | 128 |
| Todo | 0.320 | 2.84 | 118 | 355 |

- 1997–2006: las dos fuentes miden lo mismo (dentro del ±0.1 pp pedido, en los 119 meses).
- 2007–2015: el BCRA está **siempre por debajo** (los seis peores meses del solapamiento
  completo son 2007-08, 2008-03, 2008-04, 2013-11 y ene–abr 2016): la serie del BCRA es el
  **IPC oficial de INDEC de la época**, sin corregir; `inflation_cpi_monthly.csv` usa índices
  provinciales justamente para evitarlo. Es la firma esperada de la intervención de INDEC,
  ahora sí visible con una fuente oficial (el cruce 1 no la mostraba porque el IPC anual del
  Banco Mundial ya venía revisado).
- ene–abr 2016: INDEC no publicó IPC nacional (emergencia estadística); el BCRA usa otra
  serie para esos meses y jmtelechea otra. Desvío grande pero acotado a 4 meses.
- **Decisión**: `inflation_cpi_monthly_linked.csv` toma del BCRA solo 1943-03 → 1997-01 y deja
  1997-02+ idéntico al archivo existente. El empalme (1997-01: 0.5 % BCRA → 1997-02: 0.38 %
  jmtelechea) no tiene salto de escala.

## 9. IPC mensual del BCRA compuesto a anual (dic/dic) vs series anuales

Componiendo los 12 meses de cada año (`∏(1+r_m) − 1`):

- Contra `PRECIO/3_tasa_de_inflacion_anual_argentina_1935_2022.csv` de argendata
  ("inflación interanual a diciembre", INDEC): 79 años en común (1944–2022), diferencia
  absoluta media 2.0 pp, **máxima 21.3 pp en 2013** (argendata 31.9 % vs BCRA 10.7 %). Fuera
  de 2007–2015 coinciden al décimo (1959: 101.6 vs 101.8; 1975: 335.0 vs 334.9; 1989: 4923.7
  vs 4928.6): misma serie histórica de INDEC, y otra vez argendata usa un IPC alternativo en
  2007–2015 y el BCRA el oficial.
- Contra `inflation_cpi_annual_linked.csv` (Clio Infra 1915–1960 / Banco Mundial 1961+,
  ambas **promedio anual**, no dic/dic): 80 años, diferencia media 48 pp; 1959: 101.8 (dic/dic)
  vs 123.6 (promedio); 1989: 4928.6 vs 3046.1; 1990: 1344.5 vs 2078.3; 2023: 211.2 vs 135.4.
  No es un error: es la misma diferencia de convención señalada en el cruce 1 (promedio anual
  vs diciembre-contra-diciembre), que se agranda cuando la inflación acelera o desacelera
  dentro del año. Confirma que la serie mensual 1943+ del BCRA es consistente con las anuales
  ya cargadas en los episodios extremos, y que **no hay que mezclar** ambas convenciones en la
  calibración.

## 10. Snapshot BCRA_Data del 2026-09-15 vs series ya cargadas

- **Tipo de cambio mayorista A3500 (variable 5, último dato de cada mes)** vs
  `exchange_rate_official_monthly.csv` (DiLoretoT, datos.gob.ar `168.1_T_CAMBIOR_D_0_0_26`):
  295 meses (2002-03 → 2026-09), diferencia porcentual absoluta media **0.17 %**, máxima 4.9 %
  en 2002-03 (3.00 vs 2.85, primer mes de la serie A3500, que arranca el 4 de marzo de 2002);
  25 meses por encima de 0.5 %. Es la misma cotización de referencia con distinto día de
  cierre; no se generó archivo nuevo (el existente ya cubre desde 1992).
- **Reservas (variable 1, último dato del mes)** vs `reserves_monthly.csv` (misma fuente,
  snapshot del 2026-09-14): 369 meses idénticos salvo 2026-09 (50.617 → 50.506 USD millones,
  un día más de datos). **BADLAR (variable 7, promedio mensual)** vs `policy_rate_monthly.csv`:
  333 meses idénticos salvo 2026-09 (mismo motivo). No se regeneraron.
- La **tasa de política monetaria** (variable 160 del catálogo, 2015-12 → 2025-07) no está en
  el archivo de observaciones del mirror; `policy_rate_monthly.csv` sigue siendo BADLAR
  (proxy declarado).

## 11. Pobreza: CEDLAS ISA (vía argendata) vs `poverty.csv` (INDEC vía datos.gob.ar)

- **Convención de fechas de `poverty.csv`**: los 8 semestres nacionales 2003 S1 → 2006 S2 de
  `ISA_pobreza_monetaria_it2.csv` (EPH continua, INDEC) coinciden **exactamente** (0.00 pp) con
  `poverty.csv` cuando el semestre se fecha a su **cierre** (2003 S1 = 54.0 → `2003-07-01`;
  2003 S2 = 47.8 → `2004-01-01`; … 2006 S2 = 26.9 → `2007-01-01`). Por lo tanto `poverty.csv`
  está fechado a cierre de semestre (no a inicio), y los archivos nuevos siguen esa convención.
- **Empalme `poverty_linked.csv`**: 2003-05 (EPH puntual, 54.7 %) → 2003-07 (EPH continua 1er
  semestre, 54.0 %): sin salto.
- **Serie homogénea de CEDLAS (`it3`) vs `poverty.csv`**: 25 fechas en común.

  | Período | diferencia absoluta media (pp) | máxima (pp) | n |
  |---|---|---|---|
  | 2003–2006 (fechas en común 2004-01 → 2007-01) | **10.4** | 11.1 (2007-01: 26.9 vs 38.0) | 7 |
  | 2016 S2 → 2025 S1 | **0.00** | 0.00 | 18 |

  La serie homogénea está ~10 pp por encima de la oficial hasta 2015 y es idéntica a la
  oficial desde 2016 S2: es una re-estimación hacia atrás con la metodología/canasta 2016 de
  INDEC (que da niveles más altos que la canasta anterior). **No se empalma** con
  `poverty.csv`; se carga aparte (`poverty_cedlas_homogeneous.csv`) para quien quiera una
  serie metodológicamente uniforme 1992–2025, con esta advertencia.
- **GBA vs nacional** (`poverty_gba.csv` vs `poverty_linked.csv`, 13 fechas 2001-05 → 2007-01):
  diferencia media 2.3 pp, máxima 3.3 pp (2002-05: nacional 53.0 vs GBA 49.7). No deberían
  coincidir (geografías distintas); el orden de magnitud y la dirección son los esperados
  (GBA algo por debajo del total de aglomerados).
- **Hogares 1974–1989 (`it1`)**: dos estimaciones académicas (Beccaria y Arakaki) que no
  coinciden entre sí en los años en común (1974: 3.2 vs 4.6; 1980: 7.9 vs 7.1; 1982: 23.6 vs
  21.6) — por eso van en dos archivos, no se promedian ni se elige una.

## 12. Desempleo modelado OIT (anual) vs `unemployment.csv` (EPH trimestral, promedio anual)

18 años con los 4 trimestres de EPH disponibles (2003–2022, faltan 2015–2016 por el apagón
estadístico): diferencia absoluta media **0.13 pp**; sin 2003 (EPH 17.2 vs OIT 15.4, único año
con más de 0.2 pp; en 2003 la EPH cambió de puntual a continua a mitad de año) es **0.03 pp**
y 16 de 17 años están dentro de ±0.1 pp. Es decir, desde 2004 la estimación "modelada" de la
OIT es la EPH tal cual; lo que `unemployment_annual_modelled.csv` agrega es el tramo
**1991–2002** (modelado), que no reemplaza a la EPH puntual 1974–2002 (sigue faltando).

## 13. Deflactor implícito de argendata (`CRECIM/pib_corriente_constante.csv`) — descartado

Variación anual de `pib_corriente / pib_constante` (ARG) vs `gdp_deflator_annual.csv`
(Banco Mundial `NY.GDP.DEFL.KD.ZG`, 1961–2006): 46 años, diferencia absoluta media **200 pp**,
máxima 3093 pp en 1989 (implícito −35 % vs deflactor oficial 3058 %). Las dos columnas de
argendata están en **dólares** (ARG 1960 `pib_corriente = 1.59e10`, escala de US$
corrientes), así que el cociente es un deflactor en dólares (≈ tipo de cambio real), no el
deflactor en moneda local que pide el indicador. No se usó; el hueco 2007+ del deflactor sigue
en `coverage.md`.
