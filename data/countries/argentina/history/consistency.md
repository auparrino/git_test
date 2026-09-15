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
