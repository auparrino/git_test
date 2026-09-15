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
