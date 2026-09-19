# Fuentes — datos históricos de Argentina

Todas las series de este directorio provienen de un archivo descargado y verificable (URL +
hash). Nada fue tipeado a mano ni estimado. Descargas hechas el **2026-09-15**, desde este
entorno (solo alcanza `raw.githubusercontent.com`, `github.com` y PyPI; `api.worldbank.org`,
`imf.org`, `indec.gob.ar`, `bcra.gob.ar`, `datos.gob.ar`, FRED y Wikipedia dan `000`/bloqueado).

Cada sección: URL, licencia (tal como la declara la fuente), fecha de descarga, sha256 del
archivo crudo, transformación aplicada, y grado de confianza (`trust`).

- **A** = snapshot oficial con origen documentado (dato publicado por el organismo oficial,
  o snapshot que declara explícitamente de qué endpoint oficial proviene).
  **B** = serie derivada/enlazada con método documentado (empalmes, deflactados,
  agregaciones, fuentes de terceros que a su vez documentan de dónde sacan el dato).
  **C** = sin documentación de origen — **no se usa**, solo se menciona como candidato
  descartado.

---

## 1. Maddison Project Database 2020 (vía OWID)

- **URL**: `https://raw.githubusercontent.com/owid/owid-datasets/master/datasets/Maddison%20Project%20Database%202020%20(Bolt%20and%20van%20Zanden%20(2020))/Maddison%20Project%20Database%202020%20(Bolt%20and%20van%20Zanden%20(2020)).csv`
- **Licencia**: no declarada en `datapackage.json` del repo `owid/owid-datasets`; el dato
  subyacente es el Maddison Project Database (Bolt, Jutta & van Zanden, 2020), de uso libre
  para investigación con atribución, según la propia documentación del proyecto Maddison
  (Groningen Growth and Development Centre).
- **Fecha de descarga**: 2026-09-15
- **sha256**: `23a67c11f70112730d74e716841350540184b1682fcffc2860bf3ea76dff92fd`
- **Transformación**: filtrado `Entity == "Argentina"`; columna `GDP per capita` → PIB per
  cápita real (2011 US$ PPP), años 1810–2018 → `gdp_per_capita_real.csv`. Columna
  `Population` → parte de `population.csv` (ver más abajo, unida con Banco Mundial).
- **source_id**: `maddison2020`
- **trust**: A

## 2. Banco Mundial — PIB nominal (vía `datasets/gdp`)

- **URL**: `https://raw.githubusercontent.com/datasets/gdp/main/data/gdp.csv`
- **Licencia**: CC-BY-4.0 (declarada en `datapackage.json` del repo `datasets/gdp`)
- **Fecha de descarga**: 2026-09-15
- **sha256**: `8d84ef6bcaccf740c01c5ed7566aae8f7b149d0e2c20001e441efd3cb5b2fa86`
- **Transformación**: filtrado `Country Name == "Argentina"` → `gdp_usd.csv` (current US$),
  1983–2023 (años sin valor omitidos).
- **source_id**: `wb_gdp`
- **trust**: A

## 3. Banco Mundial — Población (vía `datasets/population`)

- **URL**: `https://raw.githubusercontent.com/datasets/population/main/data/population.csv`
- **Licencia**: ODC-PDDL-1.0
- **Fecha de descarga**: 2026-09-15
- **sha256**: `7d2dd6a17f5ed7916de1f89a9c116791e64d207f2e2f6ce47c57e1ab46f0088a`
- **Transformación**: filtrado `Country Name == "Argentina"`, 1960–2024. Unido con la
  columna `Population` de Maddison (fuente 1) para los años 1810–1959 donde el Banco Mundial
  no tiene dato: si un año aparece en ambas fuentes, se usa el Banco Mundial (más años
  disponibles no se pisan). → `population.csv`, con `source_id` distinto por fila
  (`maddison2020` o `wb_population`) para que quede trazable qué valor vino de dónde.
- **source_id**: `wb_population` (1960+) / `maddison2020` (pre-1960)
- **trust**: A

## 4. Banco Mundial — Inflación IPC anual (vía `datasets/inflation`)

- **URL**: `https://raw.githubusercontent.com/datasets/inflation/main/data/inflation-consumer.csv`
- **Licencia**: ODC-PDDL-1.0
- **Fecha de descarga**: 2026-09-15
- **sha256**: `b47dbd6a5d44c4ea0e4eb9e9cd18548d5d2031ca250a21dd5355be952b034344`
- **Transformación**: filtrado `Country == "Argentina"` → `inflation_cpi_annual.csv`,
  1961–2023, % anual.
- **source_id**: `wb_inflation_cpi`
- **trust**: A

## 5. Banco Mundial — Deflactor del PIB (vía `datasets/inflation`) — **NO USADO**

- **URL**: `https://raw.githubusercontent.com/datasets/inflation/main/data/inflation-gdp.csv`
- **Licencia**: ODC-PDDL-1.0
- **Fecha de descarga**: 2026-09-15
- **sha256**: `346d29c904c1087ca84ffa571e8ea1c58616474281108116f5e8414fe9357e83`
- **Resultado**: el archivo se descargó correctamente pero **no contiene ninguna fila para
  Argentina** (0 de N filas). No se generó `inflation_deflator_annual.csv` — regla #1: no se
  inventa el dato. Ver `coverage.md` → Faltantes.
- **trust**: — (serie no disponible en esta fuente)

## 6. Tipo de cambio anual (vía `datasets/exchange-rates`) — **NO USADO**

- **URL**: `https://raw.githubusercontent.com/datasets/exchange-rates/main/data/annual.csv`
- **Licencia**: no verificada (archivo descargado igual para comprobar cobertura)
- **Fecha de descarga**: 2026-09-15
- **sha256**: `49b0b5dd9cd02303db57cefc6873bdf08fae6fdcbc0df3451d804041ae0fb648`
- **Resultado**: el dataset solo cubre 20 monedas (`Australia, Brazil, Canada, China,
  Denmark, Euro, Hong Kong, India, Japan, Malaysia, Mexico, New Zealand, Norway, Singapore,
  South Africa, South Korea, Sweden, Switzerland, Taiwan, Thailand, Venezuela`) — Argentina
  **no está**. No se generó `exchange_rate_annual.csv`. El tipo de cambio anual real viene de
  las series mensuales de BCRA (fuentes 9 y 12).
- **trust**: — (serie no disponible en esta fuente)

## 7. Precio del oro anual (vía `datasets/gold-prices`)

- **URL**: `https://raw.githubusercontent.com/datasets/gold-prices/main/data/annual.csv`
- **Licencia**: ODC-PDDL-1.0
- **Fecha de descarga**: 2026-09-15
- **sha256**: `9d4687185ca14851f4ec36a55810583193b935b726ec72aa35a758c53a25d4af`
- **Transformación**: sin filtrar (serie mundial de precio, US$/onza troy) → `gold_price_annual.csv`,
  1833–2025. Proxy de commodity, no específico de Argentina.
- **source_id**: `gold_prices_annual`
- **trust**: A

## 8. Precio del petróleo anual — Brent (vía `datasets/oil-prices`)

- **URL**: `https://raw.githubusercontent.com/datasets/oil-prices/main/data/brent-year.csv`
- **Licencia**: ODC-PDDL-1.0
- **Fecha de descarga**: 2026-09-15
- **sha256**: `acfd0d8a75e06d53bf204762256d515f464f7317ddf6796bbaef0f2862cec16b`
- **Nota**: `datasets/oil-prices` **no tiene** un archivo `annual.csv` genérico; sí tiene
  `brent-year.csv` y `wti-year.csv` (promedio anual). Se usó `brent-year.csv`. También se
  descargó `wti-year.csv` (sha256 `6a25a5cad40c74e8f0ae886389177538b463ebe984f4624443d0b16c3b6540b8`)
  pero no se generó un CSV tidy para WTI para no duplicar la misma señal de commodity; queda
  en el scratchpad para uso futuro si hace falta.
- **Transformación**: serie mundial (US$/barril, FOB) → `oil_price_annual.csv`, 1987–2025.
  Proxy de commodity exógeno (no específico de Argentina), útil para el sector externo/soja-petróleo.
- **source_id**: `oil_prices_brent_annual`
- **trust**: A

## 9. V-Dem v14 (vía `vdemdata`)

- **URL**: `https://raw.githubusercontent.com/vdeminstitute/vdemdata/master/data/vdem.RData`
- **Licencia**: no hay `LICENSE` en el repo (404); los términos de uso del dato V-Dem son los
  del V-Dem Institute (uso académico/no comercial libre, con cita) — ver https://www.v-dem.net.
- **Fecha de descarga**: 2026-09-15
- **sha256**: `39b412d39a061c18f20c98e4ad4d6355b05a0441df31be4ee9aec420dc3d95ea` (33.9 MB)
- **Transformación**: cargado con `pyreadr` (`uv run --with pyreadr --with pandas`), filtrado
  `country_name == "Argentina"` (237 filas, años 1789–2025), columnas conservadas: ver lista
  abajo. → `vdem_argentina.csv` (formato ancho, una fila por año).
- **Columnas solicitadas y presentes** (30 de 31):
  `v2x_polyarchy, v2x_libdem, v2x_regime, v2x_regime_amb, v2xel_frefair, v2x_corr,
  v2x_freexp_altinf, v2x_cspart, v2cademmob, v2caautmob, v2x_civlib, v2x_rule, v2xnp_pres,
  e_boix_regime, e_p_polity, e_gdppc, e_miinflat, e_total_fuel_income_pc, e_pop, e_pt_coup,
  v2x_execorr, v2elturnhog, v2eltype_0..v2eltype_6, v2elvotsml, v2ellovtsm`
- **Columna solicitada pero ausente en v14**: `e_cpi` (no existe en el dataset descargado;
  el V-Dem Institute la reemplazó/renombró en versiones recientes — no se inventa, queda
  fuera de `vdem_argentina.csv`).
- **source_id**: `vdem`
- **trust**: A

### Codebook — significado de `v2x_regime`

Variable V-Dem "Regimes of the world" (RoW), Boix–Miller–Rosato + V-Dem, categórica 0–3:

| Valor | Régimen |
|---|---|
| 0 | Autocracia cerrada (*closed autocracy*) |
| 1 | Autocracia electoral (*electoral autocracy*) |
| 2 | Democracia electoral (*electoral democracy*) |
| 3 | Democracia liberal (*liberal democracy*) |

(Fuente: V-Dem Codebook v14, variable `v2x_regime`; no descargable el PDF del codebook desde
este entorno — este resumen es conocimiento público estándar del proyecto V-Dem, se
recomienda contrastar contra el codebook oficial al usarlo para reglas de "modo de régimen".)

---

## Series mensuales — repos públicos con snapshots de INDEC/BCRA

### Corrección: `matuteiglesias/IPC-Argentina` y `ahierro/ipc_csv_processor` **sí se usan**

Una revisión anterior de este directorio había descartado estos dos repos como
"sospechosos" (contenido de un proyecto agéntico no relacionado mezclado con los datos).
Esa revisión miraba el directorio equivocado. En esta pasada se clonaron ambos repos de
nuevo, en limpio, desde `origin` (`git clone --depth 1`), y se inspeccionaron por completo
(`git ls-files`, `README.md`, cada archivo de `data/`, `AGENTS.md`, `SYSTEM.yaml`,
`DATA_STATUS.json`, `docs/PRICE_PRODUCT_FAMILIES.md`) antes de tocar ningún dato:

- **`matuteiglesias/IPC-Argentina`** (commit `9a6a54bd3d591c33ae4363e9707125efcc66f620`,
  clonado 2026-09-15): el árbol real (`git ls-files`) coincide con lo que el `README.md`
  anuncia — `data/info/indice_precios_M.csv`, `indice_precios_Q.csv`, `indice_precios_d.csv`
  existen y tienen el contenido descrito. `AGENTS.md`/`SYSTEM.yaml` son instrucciones de
  mantenimiento del propio repo para agentes que lo *mantienen* (qué pueden y no pueden
  cambiar), no instrucciones dirigidas a quien solo lee los datos desde afuera; no contienen
  nada dirigido a este proceso de ingesta. No hay `src/republica/...` ni ningún contenido de
  otro proyecto. `DATA_STATUS.json` y `docs/PRICE_PRODUCT_FAMILIES.md` documentan con
  bastante rigor qué filas son observadas/derivadas y cuáles son **proyectadas**
  (ago–dic 2025, seis meses repitiendo la última tasa mensual observada) — esas filas
  proyectadas se excluyeron explícitamente de lo que se ingiere (ver fuente 13).
- **`ahierro/ipc_csv_processor`** (commit `80988517d2663d6a6854bcd4644d514b3b6dc084`,
  clonado 2026-09-15): `git ls-files` muestra 15 archivos, todos relacionados con el
  pipeline de IPC/tipo de cambio/dólar blue que describe el `README.md` (23 KB, con
  metodología, validación cruzada contra BCRA serie 7931 y contra el archivo hecho a mano
  que reemplazó, número de filas exactas, manejo de fechas duplicadas, etc.). No hay
  ningún `src/republica/...`, ningún texto de "Fase 9/10" ni nada ajeno al proyecto. No se
  encontró la mención a "República Artificial" que la revisión anterior decía haber visto
  en este repo.
- **`thomasriveros/BCRA_Data`**, **`jmtelechea/dashboard-macro-argentina`** y
  **`DiLoretoT/estadisticas-argentinas`** ya estaban correctamente evaluados y en uso (ver
  fuentes 10-12 más abajo); no se tocaron en esta pasada.

Ninguno de los dos repos corregidos tiene `LICENSE` en el árbol; el dato subyacente
(INDEC/BCRA, o cotizaciones scrapeadas de una página pública de dólar blue) es información
pública, igual criterio que para `thomasriveros/BCRA_Data` en la fuente 10.

### 10. `thomasriveros/BCRA_Data`

- **Repo**: `https://github.com/thomasriveros/BCRA_Data`
- **Commit clonado**: `9fbf79f05bf0a526af95e4c52b1cb2d559500798` (2026-09-14)
- **Origen declarado en el README**: descarga diaria (GitHub Actions) de las 35
  "Principales Variables" que publica la API oficial del BCRA
  (`https://api.bcra.gob.ar/estadisticas/...`), guardadas en `data/bcra_monetary.csv` en
  formato largo (`id_variable, fecha, valor, descripcion, ...`).
- **Licencia**: no hay `LICENSE` en el repo; el dato de origen (BCRA) es información pública.
- **Fecha de clonado**: 2026-09-15
- **Archivo usado**: `data/bcra_monetary.csv`
- **Series extraídas**:
  - `id_variable=1` "Reservas internacionales" (diaria, USD millones, 1996-01-03 →
    2026-09-09) → **último valor de cada mes** → `reserves_monthly.csv`
    (`source_id=bcra_data_reservas`).
  - `id_variable=7` "Tasa de interés BADLAR de bancos privados" (diaria, % anual nominal,
    1999-01-04 → 2026-09-10) → **promedio mensual** (proxy de tasa de política monetaria,
    no es la TPM oficial) → `policy_rate_monthly.csv` (`source_id=bcra_data_badlar`).
- **trust**: A

### 11. `jmtelechea/dashboard-macro-argentina`

- **Repo**: `https://github.com/jmtelechea/dashboard-macro-argentina`
- **Commit clonado**: `e84819f4a0c34861d3885dc5d3d71e2009da805d` (2026-09-14)
- **Origen declarado en el README**: API `apis.datos.gob.ar/series/api/series`, API BCRA
  `api.bcra.gob.ar`, Excel de INDEC (EMAE, salarios); cada serie de `data/series.json`
  documenta su `source` y, para el IPC, el método de empalme (índices provinciales
  1997-02→2016-12, IPC nacional INDEC desde 2017-01) con una validación cruzada explícita
  contra la serie BCRA 7931 (diferencia máxima 0,05 pp sobre 110 meses, según el propio
  README).
- **Licencia**: no hay `LICENSE` en el repo; dato de origen público (INDEC/BCRA).
- **Fecha de clonado**: 2026-09-15
- **Archivo usado**: `data/series.json`
- **Series extraídas**:
  - `145.3_INGNACUAL_DICI_M_38` "IPC nacional (serie empalmada)", % variación mensual,
    1997-02 → 2026-08 → `inflation_cpi_monthly.csv` (`source_id=jmtelechea_ipc_nacional`).
    **trust B** (serie empalmada/derivada, método documentado).
  - `158.1_REPTE_0_0_5` "RIPTE real", pesos constantes de noviembre 2023, 1994-08 → 2026-07
    → `real_wage.csv` (`source_id=jmtelechea_ripte_real`). **trust B** (deflactado con el
    IPC empalmado, método documentado).
  - `143.3_NO_PR_2004_A_31` "EMAE", índice 2004=100, INDEC oficial, 2004-01 → 2026-06 →
    `emae_monthly.csv` (`source_id=jmtelechea_emae`). **trust A** (serie oficial directa,
    sin transformación más allá de la descarga). *(Bonus: no es una de las 10 series
    pedidas explícitamente por nombre, pero el enunciado la menciona como candidato de
    "actividad económica".)*
  - `379.9_RESULTADO_017__31_73_379.9_RESULTADO_017__18_38_rolling12_gdp`, línea
    "Resultado primario sin rentas", % del PIB nominal acumulado 12 meses,
    Secretaría de Hacienda, 2015-12 → 2026-03 → `fiscal_balance.csv`
    (`source_id=jmtelechea_resultado_fiscal`). **trust B** (razón acumulada/PIB, método
    documentado en el README del repo).
- **trust**: B (donde se indica; EMAE es A)

### 12. `DiLoretoT/estadisticas-argentinas`

- **Repo**: `https://github.com/DiLoretoT/estadisticas-argentinas`
- **Commit clonado**: `b4fe8efce4fadcf67dc9f62ec2191774f5e2686c` (2026-09-15)
- **Origen declarado**: `etl/sources.json` documenta, por serie, el id exacto de la API de
  `datos.gob.ar`, o el endpoint de `api.bcra.gob.ar`, o (para el dólar blue) la API de
  terceros `api.argentinadatos.com`; `etl/fetch_deuda.py` documenta que la deuda pública sale
  del Excel oficial `https://www.argentina.gob.ar/sites/default/files/deuda_publica_DD-MM-YYYY.xlsx`
  (MECON), hoja A.2.5. Cada serie tiene además un `*_summary.json` con `source.official`.
- **Licencia**: MIT (repo, `LICENSE` presente); dato de origen público (INDEC/BCRA/MECON) o,
  para el dólar blue, un agregador de terceros.
- **Fecha de clonado**: 2026-09-15
- **Archivos usados**: `data/series/*.json` (lista `[fecha, valor]`)
- **Series extraídas**:
  - `dolar_oficial_mensual.json`: tipo de cambio oficial mayorista de referencia, ARS/USD,
    fin de mes, series `168.1_T_CAMBIOR_D_0_0_26` de datos.gob.ar (con `api.bcra.gob.ar`
    como respaldo para huecos), 1992-01 → 2026-09 → `exchange_rate_official_monthly.csv`
    (`source_id=diloretot_dolar_oficial`). **trust A**.
  - `dolar_blue_mensual.json`: dólar blue/paralelo, ARS/USD, fin de mes, fuente
    `api.argentinadatos.com` (agregador de terceros, no organismo oficial, pero con origen
    documentado), 2011-01 → 2026-09 → `exchange_rate_parallel_monthly.csv`
    (`source_id=diloretot_dolar_blue`). **trust B**.
  - `tasa_desocupacion.json`: tasa de desocupación EPH, serie `42.3_EPH_PUNTUATAL_0_M_30` de
    INDEC vía datos.gob.ar, trimestral, 2003-01 → 2026-01 → `unemployment.csv`
    (`source_id=diloretot_tasa_desocupacion`). **trust A**.
  - `tasa_pobreza.json`: tasa de pobreza, serie `64.2_POBLACION_NUA_0_0_34_74` de INDEC vía
    datos.gob.ar, semestral, 2003-07 → 2026-01 → `poverty.csv`
    (`source_id=diloretot_tasa_pobreza`). **trust A**.
  - `deuda_total.json`: deuda pública bruta total, USD millones, MECON (Excel oficial citado
    arriba), `official: true` según su propio `*_summary.json`, 1992-12 → 2025-12 →
    `public_debt.csv` (`source_id=diloretot_deuda_total`). **trust A**.
- **trust**: A salvo dólar blue (B)

### 13. `matuteiglesias/IPC-Argentina` — IPC trimestral compuesto

- **Repo**: `https://github.com/matuteiglesias/IPC-Argentina`
- **Commit clonado**: `9a6a54bd3d591c33ae4363e9707125efcc66f620` (2026-08-31)
- **Origen declarado en el README/`docs/PRICE_PRODUCT_FAMILIES.md`**: índice compuesto que
  combina, según disponibilidad temporal, IPC histórico de INDEC (hasta 2007), IPC moderno
  de INDEC (desde dic-2016, vía `datos.gob.ar`), e IPC provincial de CABA, Córdoba y San
  Luis (Excel/XLSX de cada organismo, URLs embebidas en `computarInflacion.py`), enlazados
  en escala logarítmica y normalizados a enero de 2016 = 100.
- **Licencia**: no hay `LICENSE` en el repo; dato de origen público (INDEC/CABA/Córdoba/San
  Luis).
- **Fecha de clonado**: 2026-09-15
- **Archivo usado**: `data/info/indice_precios_Q.csv` (agregación trimestral, 104 filas)
- **sha256** (`data/info/indice_precios_Q.csv`):
  `588b3a1e056ac6795543957a1edc555e4eaa6ee1cf6dfe1ba4c6c03a78b1d1a0`
- **Transformación**: se excluyeron las **últimas 2 filas** (`2025-08-15`, `2025-11-15`):
  `docs/PRICE_PRODUCT_FAMILIES.md` documenta explícitamente que los dos trimestres finales
  incluyen meses **proyectados** (agosto-diciembre 2025 repiten la última tasa mensual
  observada, no son observaciones — ver `DATA_STATUS.json`: `observed_through: 2025-07-01`,
  `projected_from: 2025-08-01`). Las 102 filas restantes (`2000-02-15` a `2025-05-15`) son
  "derived" (agregación de meses derivados, no proyectados) según la misma tabla de
  clasificación de linaje del repo. → `inflation_cpi_quarterly.csv`
  (`source_id=matuteiglesias_ipc_quarterly`). Es un **índice de nivel** (no variación %),
  con período base propio (ene-2016=100) distinto del de `inflation_cpi_monthly.csv`, así
  que no se combinan en el mismo archivo.
- **source_id**: `matuteiglesias_ipc_quarterly`
- **trust**: B (compuesto/enlazado, método documentado en el propio repo)

### 14. `ahierro/ipc_csv_processor` — dólar blue diario histórico (extensión 2008-2010)

- **Repo**: `https://github.com/ahierro/ipc_csv_processor`
- **Commit clonado**: `80988517d2663d6a6854bcd4644d514b3b6dc084` (2026-08-22)
- **Origen declarado en el README (§4)**: `dolarblue.csv` es un volcado guardado de una
  página de cotización del dólar blue (fecha en castellano + importe, un registro por
  bloque); `process_cotizacion_blue.js` lo normaliza a `cotizacion_blue.csv`
  (`DD/MM/AAAA;cotizacion`, 6 decimales), documentando validaciones (nombre del día vs.
  fecha, round-trip de los 2268 registros, comparación contra el oficial). Sin URL de origen
  explícita para el volcado (no es una API), por eso se documenta como scrape de una página,
  trust B (no A).
- **Licencia**: no hay `LICENSE` en el repo; cotización pública.
- **Fecha de clonado**: 2026-09-15
- **Archivo usado**: `cotizacion_blue.csv` (2268 filas, 2008-01-02 → 2026-08-21)
- **sha256** (`cotizacion_blue.csv`):
  `79501c613ecf3f780605c2d116011c155dcbdd91d2362e60cf09d992cfa4f4d1`
- **Validación de empalme contra `exchange_rate_parallel_monthly.csv`** (existente,
  `diloretot_dolar_blue`, 2011-01+): se calculó el cierre de fin de mes de
  `cotizacion_blue.csv` y se comparó contra los 188 meses en común (2011-01 → 2026-08).
  **Diferencia absoluta media: 1.92 %**; máxima 12.5 % (2011-10: blue=4.50 vs
  existente=4.00). Ver detalle en `consistency.md` → sección 4. Por estar bajo el umbral de
  5 % del enunciado, se usó para **extender hacia atrás**: se tomaron los 36 meses
  2008-01 → 2010-12 (no cubiertos por la fuente existente) y se antepusieron, sin tocar
  `exchange_rate_parallel_monthly.csv`, en un archivo nuevo que además repite (sin
  modificar) los valores 2011-01+ existentes para dar una serie continua.
  → `exchange_rate_parallel_monthly_linked.csv` (2008-01 → 2026-09, 225 filas): filas
  2008-01 a 2010-12 con `source_id=ahierro_dolar_blue`, filas 2011-01+ con
  `source_id=diloretot_dolar_blue` (idénticas a las de `exchange_rate_parallel_monthly.csv`).
- **source_id**: `ahierro_dolar_blue` (extensión) / `diloretot_dolar_blue` (parte 2011+,
  reutilizado)
- **trust**: B

### 15. `ahierro/ipc_csv_processor` — tipo de cambio oficial diario (solo validación, sin extensión)

- Mismo repo y commit que la fuente 14. Archivo `tipo_de_cambio.csv` (6032 filas,
  2002-01-11 → 2026-08-21, cierre vendedor BCRA "Evolución de una moneda"). **No se generó
  ningún CSV nuevo con esto**: la fuente arranca en 2002, más tarde que
  `exchange_rate_official_monthly.csv` (que ya cubre desde 1992 vía DiLoretoT/BCRA), así que
  no hay período nuevo que aportar hacia atrás. Se usó únicamente como **validación
  cruzada**: fin de mes de `tipo_de_cambio.csv` vs. `exchange_rate_official_monthly.csv`
  existente, 296 meses en común (2002-01 → 2026-08): diferencia absoluta media **0.0021 %**,
  máxima 0.63 % (2026-08). Ver `consistency.md` → sección 5. Confirma que ambas fuentes
  (BCRA vía DiLoretoT, y BCRA vía este repo) están midiendo lo mismo.
- **trust**: — (no genera archivo; solo validación)

### 16. `unbalancedparentheses/forex-centuries` — Clio Infra: inflación y tipo de cambio 1879-1960

- **Repo**: `https://github.com/unbalancedparentheses/forex-centuries`
- **Commit clonado**: `f79a85bf6ae0dbad8d79ea56902caef43c7bd947` (2026-02-26)
- **Origen declarado**: mirror/compilación de 27 fuentes académicas/institucionales de datos
  monetarios de larga duración (ver tabla de fuentes en su `README.md`); los archivos
  usados acá vienen de **Clio Infra** (`https://clio-infra.eu/`, proyecto de historia
  cuantitativa de la Universidad de Utrecht/IISH), formato ancho `year, <país>, <país>, ...`,
  documentado en el propio README (`data/sources/clio_infra/`: "All Clio Infra files share
  the same wide format: first column is `year`, remaining columns are country names. Values
  are yearly averages."). Con columnas y unidades declaradas por archivo:
  `clio_infra_inflation.csv` = "Annual % change"; `clio_infra_exchange_rates.csv` = "Local
  currency per 1 USD".
- **Licencia**: repo bajo MIT (`LICENSE`); el propio README aclara que "Most Clio Infra and
  IISG datasets are CC0 (public domain)".
- **Fecha de clonado**: 2026-09-15
- **sha256**:
  - `data/sources/clio_infra/clio_infra_inflation.csv`:
    `e9752dfed4bf1c09d827506bf4da8a840c13d9b72d950865523f8c91a405c5f6`
  - `data/sources/clio_infra/clio_infra_exchange_rates.csv`:
    `48f7eca8ecd71cf96c1e9c0a33db1de79b6f1acfa4d6025d3131eec92c555636`
- **Transformación — inflación**: columna `Argentina` de `clio_infra_inflation.csv` tiene un
  tramo continuo sin huecos de **1915 a 2010** (se verificó fila a fila: sin años faltantes
  en ese rango). Se tomó **1915-1960** (anterior al arranque de
  `inflation_cpi_annual.csv`, que es 1961) y se antepuso, sin modificar el archivo
  existente, a una copia literal de `inflation_cpi_annual.csv` (1961-2023,
  `source_id=wb_inflation_cpi` preservado) para dar una serie continua 1915-2023 en un
  archivo nuevo. → `inflation_cpi_annual_linked.csv` (109 filas): 1915-1960 con
  `source_id=forexcenturies_clio_cpi`, 1961-2023 con `source_id=wb_inflation_cpi`. Esto
  cubre el pedido explícito de "inflación histórica anual 1943-1960" y bastante más atrás.
  No se pudo ir más atrás de 1915 de forma continua: antes hay huecos año a año (ver huecos
  listados en `coverage.md`), y no se interpola/rellena un hueco sin dato.
- **Transformación — tipo de cambio**: columna `Argentina` de `clio_infra_exchange_rates.csv`
  tiene valores desde 1879. **Se usó solo 1879-1951**: a partir de 1952 la serie de este
  mirror muestra artefactos claros — valores exactamente `0.0` entre 1952 y 1961, y valores
  del orden de `1e-11` a `1e-9` entre 1962 y 1974 (matemáticamente imposibles como "pesos
  por dólar" de esa época) — que reflejan, casi con certeza, un problema de escala no
  resuelto por Clio Infra al cruzar las múltiples redenominaciones del peso argentino (peso
  moneda nacional → peso ley 18.188 en 1970 [-2 ceros] → peso argentino en 1983 [-4 ceros]
  → austral en 1985 [-3 ceros] → peso convertible en 1992 [-4 ceros]). No se intentó
  "corregir" la escala (eso sería inventar un factor de conversión no documentado por la
  fuente); se **excluyó** 1952 en adelante en vez de reinterpretarlo. → `exchange_rate_annual.csv`
  (51 filas, 1879-1951, `source_id=forexcenturies_clio_fx`). Cubre el pedido de "tipo de
  cambio histórico anual 1914+" y la brecha 1810-1991 que `coverage.md` marcaba como
  faltante (parcialmente: 1879-1951 de 1810-1991).
- **source_id**: `forexcenturies_clio_cpi` (inflación 1915-1960) /
  `forexcenturies_clio_fx` (tipo de cambio 1879-1951)
- **trust**: B (compilación académica de terceros, con metodología y fuente primaria
  citadas por Clio Infra, pero sin el detalle fila-a-fila de cada dato primario)

### 17. `ronnywang/worldbank` — deflactor del PIB (World Bank WDI, mirror histórico)

- **Repo**: `https://github.com/ronnywang/worldbank`
- **Commit clonado**: `dff56f37f6cc8b763d767fe9c55f9cdb9d40054d` (2013-12-21)
- **Origen declarado**: mirror estático de "World Bank Open Data" (README: "World Bank Open
  Data"), archivos WDI parseados en `WDI_bundle/parsed/`, un CSV por indicador con el mismo
  layout ancho que usa el Banco Mundial (`Country Name, Country Code, Indicator Name,
  Indicator Code, 1960, 1961, ...`). El archivo usado es
  `WDI_bundle/parsed/NY.GDP.DEFL.KD.ZG_WDI.csv` — el **código de indicador coincide
  exactamente** con el pedido (`NY.GDP.DEFL.KD.ZG`, deflactor del PIB, % anual), a diferencia
  de `datasets/inflation/inflation-gdp.csv` (fuente 5, más arriba) que se probó primero y
  **no tenía ninguna fila para Argentina**.
- **Licencia**: no hay `LICENSE` en el repo; dato de origen es World Bank Open Data (de
  acceso libre).
- **Fecha de clonado**: 2026-09-15
- **sha256** (`WDI_bundle/parsed/NY.GDP.DEFL.KD.ZG_WDI.csv`):
  `56491bf9a372bd8b1769b8cd1c9e8d6ff497f414afafa0ab39d3e4a036b059b5`
- **Transformación**: filtrado `Country Name == "Argentina"`, columnas de año 1961-2013;
  valores no vacíos solo hasta 2006 (2007-2013 vienen vacíos para Argentina en este
  snapshot de 2013) → `gdp_deflator_annual.csv`, 1961-2006, 46 filas. Nota: este snapshot es
  de diciembre de 2013, así que no tiene revisiones posteriores del dato ni años recientes;
  se documenta como tal en `coverage.md`.
- **source_id**: `wb_gdp_deflator_mirror`
- **trust**: A (snapshot de un indicador oficial del Banco Mundial con código exacto
  declarado; la limitación es cobertura temporal del snapshot, no el origen del dato)

### 18. `thomasriveros/BCRA_Data` — IPC mensual histórico 1943-03 → hoy (variable 27), snapshot 2026-09-15

- **Repo**: `https://github.com/thomasriveros/BCRA_Data` (mismo repo que la fuente 10, clonado de
  nuevo con `git clone --depth 1` el 2026-09-15).
- **Commit clonado**: `5a394b232aa583462c1eca0617bf0b7ad15ac25e` (2026-09-15 15:37 UTC).
- **Origen declarado en el README**: descarga diaria (GitHub Actions) de las 35 "Principales
  Variables" de la API oficial de Estadísticas Monetarias del BCRA v4.0
  (`https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias/<id>`; el README enlaza el catálogo
  oficial `principales-variables-v4.pdf`). La variable **`id_variable=27` "Inflación mensual"**
  es la serie mensual de variación del IPC que el BCRA publica empalmada hacia atrás con las
  bases históricas de INDEC (arranca en **1943-03-31**), es decir, el "IPC histórico —
  empalme" que `coverage.md` buscaba en `datos.gob.ar` (bloqueado), servido por el BCRA.
- **Licencia**: no hay `LICENSE` en el repo; el dato de origen (BCRA/INDEC) es información
  pública.
- **Fecha de clonado**: 2026-09-15
- **sha256** (`data/bcra_monetary.csv`, 26.8 MB, 197.360 observaciones, 36 variables):
  `f0cf86bce5fc967b32a919817319226e2efba9f84a74f9101fd7cdf7d8dea441`
- **Extracto crudo guardado en el repo**: `raw/bcra_data/bcra_monetary_id27_inflacion_mensual.csv`
  (solo las 1002 filas de `id_variable=27`, mismas columnas), sha256
  `d7ccecc1bd8faad0f6fb76eb00e5a174dc2f45d8cadcd7294ebb0f17f613e0c7`.
- **Transformación** (`scripts/build_argentina_history_from_mirrors.py`): 1002 observaciones
  mensuales 1943-03 → 2026-08, **sin ningún mes faltante ni duplicado** (verificado). Fecha
  `YYYY-MM-último día` → `YYYY-MM-01`. Se tomaron los **647 meses 1943-03 → 1997-01**
  (anteriores al arranque de `inflation_cpi_monthly.csv`) con `source_id=bcra_data_inflacion_mensual`
  y se antepusieron, sin modificar el archivo existente, a una copia literal de
  `inflation_cpi_monthly.csv` (1997-02 → 2026-08, `source_id=jmtelechea_ipc_nacional`
  preservado) → `inflation_cpi_monthly_linked.csv` (1002 filas, 1943-03 → 2026-08).
- **Validación del solapamiento** (355 meses 1997-02 → 2026-08, ver `consistency.md` sección
  8): 1997–2006 diferencia absoluta media **0.023 pp**, ningún mes con más de 0.1 pp (las dos
  fuentes miden lo mismo); 2007–2015 **0.88 pp** con 104 de 108 meses por encima de 0.1 pp,
  siempre con el BCRA por debajo — la serie del BCRA reproduce el **IPC oficial de INDEC
  intervenido** de esos años, mientras que `inflation_cpi_monthly.csv` usa índices
  provinciales; 2016+ 0.12 pp (los desvíos se concentran en ene–abr 2016, cuando INDEC no
  publicó IPC nacional). Por eso el tramo 2007–2015 del `_linked` sigue siendo el de
  jmtelechea (no se pisa el archivo base) y el tramo BCRA es solo 1943–1997-01.
- **También verificado en este snapshot, sin generar archivo nuevo**: `id 5` tipo de cambio
  mayorista de referencia Com. A3500 (2002-03 →) contra `exchange_rate_official_monthly.csv`
  (`consistency.md` sección 10, diferencia media 0.17 %); `id 1` reservas e `id 7` BADLAR
  contra `reserves_monthly.csv`/`policy_rate_monthly.csv` (idénticos salvo la revisión del
  último mes). La **tasa de política monetaria** oficial (`id 160`, 2015-12 → 2025-07) figura
  en el catálogo `data/bcra_all_variables.csv` del mirror pero **no** en `bcra_monetary.csv`
  (el mirror solo replica la categoría "Principales Variables"), así que no se pudo cargar.
  No se usó `id 28` "Inflación interanual" (redundante con la composición de `id 27`).
- **source_id**: `bcra_data_inflacion_mensual` (1943-03 → 1997-01) / `jmtelechea_ipc_nacional`
  (1997-02 →, reutilizado)
- **trust**: A para el tramo BCRA (serie oficial publicada por el BCRA con id de variable
  exacto; la limitación conocida es que 2007–2015 en la serie del BCRA es el IPC oficial de la
  época, tramo que este archivo **no** toma del BCRA); el archivo `_linked` en conjunto es B
  (empalme de dos fuentes con método documentado).

### 19. `argendatafundar/data` — pobreza 1974-2025 (CEDLAS "Indicadores Sociales de Argentina")

- **Repo**: `https://github.com/argendatafundar/data` (Fundar, proyecto Argendata; "salida del
  proceso semi automatizado de reproductibilidad (ETL)" `https://github.com/argendata/etl`).
- **Commit clonado**: `90787c25bcfcbcfa134e02b33ce4caa2fa9d9e95` (2026-09-01). ETL:
  `argendata/etl` commit `82d8a7eefe6bc22376404ddc8f4d2e58108a8bde` (2026-02-12), clonado
  solo para leer cómo se producen las tablas.
- **Licencia**: **CC BY-NC-SA 4.0** (`LICENSE` en la raíz del repo de datos y del ETL). Uso no
  comercial con atribución a Fundar/Argendata y a CEDLAS.
- **Origen declarado**: `POBREZ/README.md` ("Fuente: Indicadores Sociales de Argentina
  (CEDLAS)", `https://www.cedlas.econo.unlp.edu.ar/wp/en/estadisticas/isa/`). Los scripts del
  ETL `scripts/subtopicos/POBREZ/{5,6,23}_ISA_pobreza_monetaria_it{1,2,3}.R` leen con
  `readxl` las fuentes crudas `R148C0`, `R149C0` y `R150C0`, que
  `scripts/descarga_fuentes/descarga_cedlas_isa_pobreza.R` baja de
  `https://www.cedlas.econo.unlp.edu.ar/wp/wp-content/uploads/...` (Excel de CEDLAS); las
  `aclaraciones` de cada `write_output` describen cada tabla ("Porcentaje de Hogares Pobres.
  Gran Buenos Aires, 1974-1989"; "Porcentaje de Personas Pobres. Gran Buenos Aires,
  1988-2003"; "Porcentaje de Personas por debajo de la linea de pobreza y de indigencia. Total
  Nacional, 1992-2023").
- **Fecha de clonado**: 2026-09-15
- **Archivos usados** (copiados tal cual a `raw/argendata/`) y **sha256**:
  - `POBREZ/ISA_pobreza_monetaria_it1.csv`:
    `1d00a376e9d89ce72272aac620610486affc5ab28a9aa82a57e8d8cd17a76d53`
  - `POBREZ/ISA_pobreza_monetaria_it2.csv`:
    `a94b147762a024eabd331f3bdbf0062ea686e0d854efb3159d88c245512a7539`
  - `POBREZ/ISA_pobreza_monetaria_it3.csv`:
    `8786770087fa9d1674f34b916dba3a8d065a7df624d272b8d50d91715f20c0bf`
- **Convención de fechas** (la que ya usa `poverty.csv`, verificada valor a valor en
  `consistency.md` sección 11): onda mensual de la EPH puntual → día 1 del mes
  (`1992-05-01`, `1992-10-01`); semestre de la EPH continua → **cierre** del semestre
  (1er semestre 2003 → `2003-07-01`, 2do semestre 2003 → `2004-01-01`).
- **Transformaciones** (`scripts/build_argentina_history_from_mirrors.py`):
  - `it2`, filas `region=national, survey=EPH-Puntual` (5 ondas: 2001-05, 2001-10, 2002-05,
    2002-10, 2003-05; % de personas, total aglomerados urbanos, INDEC) → antepuestas, sin
    modificar el archivo existente, a una copia literal de `poverty.csv` (2003-07 →,
    `source_id=diloretot_tasa_pobreza` preservado) → **`poverty_linked.csv`** (33 filas,
    2001-05 → 2026-01). Los 8 semestres nacionales 2003–2006 de la misma tabla coinciden
    **exactamente** (0.00 pp) con `poverty.csv`, lo que confirma que `it2` reproduce la serie
    oficial de INDEC y que la convención de fechas es la misma.
  - `it2`, filas `region=GBA` (EPH puntual mayo/octubre 1988-05 → 2003-05 y EPH continua
    semestral 2003 S1 → 2006 S2; % de personas, Gran Buenos Aires) → **`poverty_gba.csv`**
    (39 filas, 1988-05 → 2007-01). Geografía distinta a `poverty.csv` (solo GBA), por eso va
    en un archivo aparte y no se empalma.
  - `it1` (% de **hogares** pobres, GBA, 1974–1989, dos estimaciones académicas distintas
    identificadas por la fuente como `beccaria` y `arakaki`; no coinciden en los años en
    común, p. ej. 1974: 3.2 vs 4.6) → **`poverty_gba_households_beccaria.csv`** (6 filas:
    1974–1976, 1980, 1982, 1983) y **`poverty_gba_households_arakaki.csv`** (9 filas: 1974,
    1980–1982, 1985–1989). Fecha `YYYY-01-01`. Las celdas vacías de la fuente se omiten (no
    se interpola).
  - `it3` (serie **homogénea** de CEDLAS, total nacional, 1992-05 → 2025 S1, % de personas,
    líneas `pobreza` e `indigencia`; celdas vacías 2015 S2 y 2016 S1 omitidas) →
    **`poverty_cedlas_homogeneous.csv`** e **`indigence_cedlas_homogeneous.csv`** (65 filas
    cada uno). **No es la serie oficial de INDEC**: en 2003–2006 está ~10 pp por encima de
    `poverty.csv` (p. ej. 2003 S2: 57.7 vs 47.8) y desde 2016 S2 coincide exactamente con la
    oficial — consistente con una re-estimación hacia atrás con la canasta/metodología INDEC
    2016 (ver `consistency.md` sección 11). Se carga como serie separada, sin empalmar.
- **source_id**: `argendata_cedlas_isa_pobreza_nacional` (`poverty_linked.csv`, tramo
  2001–2003) / `argendata_cedlas_isa_pobreza_gba` / `argendata_cedlas_isa_pobreza_gba_hogares_beccaria`
  / `argendata_cedlas_isa_pobreza_gba_hogares_arakaki` / `argendata_cedlas_isa_pobreza_homogenea`
  / `argendata_cedlas_isa_indigencia_homogenea`
- **trust**: B (compilación de terceros con origen documentado; el tramo `it2` nacional se
  validó exacto contra la serie oficial ya cargada, el resto no tiene contraste independiente
  desde este entorno).

### 20. `argendatafundar/data` — desempleo anual modelado OIT (Banco Mundial `SL.UEM.TOTL.ZS`)

- **Repo / commit / licencia / fecha**: los mismos de la fuente 19.
- **Origen declarado**: `INFDES/tasa_desempleo_arg_mundial_modelada.json` (`fuentes: R109C0`)
  y el ETL `scripts/subtopicos/INFDES/11_tasa_desempleo_arg_mundial_modelada.R`
  (`fuente1 <- "R109C0" # SL.UEM.TOTL.ZS`) / `fuentes_INFDES.R` ("Unemployment, total (% of
  total labor force) (modeled ILO estimate)"): indicador del Banco Mundial
  `SL.UEM.TOTL.ZS`, estimación modelada de la OIT, filtrado a `anio > 1990`.
- **Archivo usado** (copiado a `raw/argendata/`) y **sha256**:
  `INFDES/tasa_desempleo_arg_mundial_modelada.csv`:
  `121ae2e840fc3e1589d19411abcc16e416bcc7edde6f6440f4f4aa5bc164ffcf`
- **Transformación**: filas `geocodigoFundar == "ARG"`; la fuente trae la tasa como proporción
  (`0.0544`) → ×100 (aritmética decimal exacta) → `5.44` %. **Se excluyó 2023**: el campo
  `aclaraciones` del `.json` declara que ese valor "fue corregido a mano, utilizando el valor
  de INDEC" porque la API del Banco Mundial no respondía — no es el dato de la fuente
  declarada. → `unemployment_annual_modelled.csv` (32 filas, 1991–2022).
- **Validación**: contra el promedio anual de `unemployment.csv` (EPH trimestral, INDEC) en
  2004–2022 la diferencia absoluta media es 0.03 pp (0.13 pp incluyendo 2003, único año con
  1.8 pp de desvío) — ver `consistency.md` sección 12. Es decir, desde 2004 la OIT toma la EPH
  tal cual; 1991–2002 es el tramo que agrega (modelado, no medido).
- **source_id**: `argendata_wb_ilo_desempleo`
- **trust**: B (estimación modelada de un organismo internacional, vía mirror; no es la EPH
  puntual pedida en `coverage.md`, que sigue faltando).

### 21. Candidatos evaluados y **NO usados** en esta pasada (2026-09-15)

- **`argendatafundar/data` `CRECIM/pib_corriente_constante.csv`** (sha256
  `7b0fa5da9a10ff2c7ac8428460439a88b5f93d9a4b1e0d4fe08ea2c485c1c28e`): se probó derivar el
  deflactor del PIB como variación del cociente `pib_corriente / pib_constante`. Contra
  `gdp_deflator_annual.csv` (Banco Mundial `NY.GDP.DEFL.KD.ZG`) da una diferencia media de
  **200 pp** en 1961–2006 (1989: −35 % vs 3058 %): las dos columnas están en **dólares** (PIB
  a US$ corrientes y a US$ constantes), no en pesos, así que el cociente mide tipo de cambio
  real, no el deflactor. Descartado (`consistency.md` sección 13). El hueco 2007+ del
  deflactor sigue abierto.
- **`argendatafundar/data` `PRECIO/3_tasa_de_inflacion_anual_argentina_1935_2022.csv`**
  (sha256 `89b0d90b66769e551da3550133bde0f58cdcffd985b165d554a58b95e23896dc`, inflación
  interanual a diciembre 1935–2023): solo se usó como contraste de la composición dic/dic
  de la serie mensual del BCRA (`consistency.md` sección 9); no se ingirió porque
  `inflation_cpi_annual_linked.csv` ya cubre 1915+ y la convención (dic/dic vs promedio
  anual) es distinta.
- **`argendatafundar/data` `INFDES/tasa_desempleo_eph_niveled.csv`**: desocupación por nivel
  educativo, pero solo 2003+ (EPH continua) — no cubre 1974–2002.
- **`argendata/etl`** y **`datos-Fundar/argendata`**: solo código/documentación, sin series
  adicionales.

---

### 22. `ronnywang/worldbank` — tipo de cambio oficial anual enlazado 1962-2012 (WDI `PA.NUS.FCRF`)

- **Repo**: `https://github.com/ronnywang/worldbank` (el mismo mirror de la fuente 17)
- **Archivo**: `WDI_bundle/parsed/PA.NUS.FCRF_WDI.csv`
  (`https://raw.githubusercontent.com/ronnywang/worldbank/master/WDI_bundle/parsed/PA.NUS.FCRF_WDI.csv`)
- **Origen declarado**: indicador `PA.NUS.FCRF` del World Development Indicators del Banco
  Mundial, "Official exchange rate (LCU per US$, period average)"; el propio WDI declara como
  fuente primaria el *International Financial Statistics* del FMI. El código de indicador
  coincide exactamente con el pedido. `api.worldbank.org` responde 403 desde este entorno
  (ver `coverage.md`), así que el mirror es la única copia alcanzable.
- **Licencia**: no hay `LICENSE` en el repo; el dato de origen es World Bank Open Data (CC BY 4.0).
- **Fecha de descarga**: 2026-09-19 (snapshot del repo: diciembre de 2013, igual que la fuente 17)
- **sha256** (`PA.NUS.FCRF_WDI.csv`):
  `df0101b206368fec61ab026087a3e441b92db746d58440c21d8c600f9b003b30`
  (copia cruda commiteada en `history/raw/worldbank_mirror/`)
- **Transformación**: fila `Country Code == "ARG"`, columnas de año no vacías (1962-2012; 1960 y
  1961 vienen vacíos en este snapshot) → `exchange_rate_annual_linked.csv`, 51 filas, sin
  ningún factor aplicado. **La serie del WDI ya viene enlazada** a la unidad vigente (peso
  convertible de 1992 = ARS actual) a través de las cuatro redenominaciones (1970, 1983, 1985,
  1992): por eso 1962 vale `1.4e-11` ARS/USD (≈ 140 pesos moneda nacional por dólar) y 1991
  vale `0.9536` (≈ 9 536 australes por dólar). Reproducible con
  `scripts/build_argentina_fx_linked.py`, que además imprime los cinco cruces de
  `consistency.md` sección 14.
- **source_id**: `wb_fcrf_mirror`
- **trust**: A (indicador oficial del Banco Mundial con código exacto declarado y origen FMI;
  la limitación es la cobertura del snapshot —termina en 2012— y que 1960-1961 no tienen dato,
  no el origen). Cierra el hueco 1952-1991 que la fuente 16 no pudo cubrir por el artefacto de
  escala de Clio Infra; 1952-1961 sigue sin dato.

## Resumen de `trust` por serie tidy

| Archivo | `source_id` | trust | Período |
|---|---|---|---|
| `gdp_per_capita_real.csv` | `maddison2020` | A | 1820–2018 |
| `gdp_usd.csv` | `wb_gdp` | A | 1983–2023 |
| `population.csv` | `wb_population` / `maddison2020` | A | 1820–2024 |
| `inflation_cpi_annual.csv` | `wb_inflation_cpi` | A | 1961–2023 |
| `gold_price_annual.csv` | `gold_prices_annual` | A | 1833–2025 |
| `oil_price_annual.csv` | `oil_prices_brent_annual` | A | 1987–2025 |
| `vdem_argentina.csv` | `vdem` | A | 1789–2025 |
| `reserves_monthly.csv` | `bcra_data_reservas` | A | 1996–2026 |
| `policy_rate_monthly.csv` | `bcra_data_badlar` | A (serie oficial) / proxy conceptual | 1999–2026 |
| `inflation_cpi_monthly.csv` | `jmtelechea_ipc_nacional` | B | 1997–2026 |
| `real_wage.csv` | `jmtelechea_ripte_real` | B | 1994–2026 |
| `emae_monthly.csv` | `jmtelechea_emae` | A | 2004–2026 |
| `fiscal_balance.csv` | `jmtelechea_resultado_fiscal` | B | 2015–2026 |
| `exchange_rate_official_monthly.csv` | `diloretot_dolar_oficial` | A | 1992–2026 |
| `exchange_rate_parallel_monthly.csv` | `diloretot_dolar_blue` | B | 2011–2026 |
| `unemployment.csv` | `diloretot_tasa_desocupacion` | A | 2003–2026 |
| `poverty.csv` | `diloretot_tasa_pobreza` | A | 2003–2026 |
| `public_debt.csv` | `diloretot_deuda_total` | A | 1992–2025 |
| `inflation_cpi_quarterly.csv` | `matuteiglesias_ipc_quarterly` | B | 2000 T1–2025 T2 |
| `exchange_rate_parallel_monthly_linked.csv` | `ahierro_dolar_blue` / `diloretot_dolar_blue` | B | 2008–2026 |
| `inflation_cpi_annual_linked.csv` | `forexcenturies_clio_cpi` / `wb_inflation_cpi` | B / A | 1915–2023 |
| `exchange_rate_annual.csv` | `forexcenturies_clio_fx` | B | 1879–1951 |
| `exchange_rate_annual_linked.csv` | `wb_fcrf_mirror` | A | 1962–2012 |
| `gdp_deflator_annual.csv` | `wb_gdp_deflator_mirror` | A | 1961–2006 |
| `inflation_cpi_monthly_linked.csv` | `bcra_data_inflacion_mensual` / `jmtelechea_ipc_nacional` | A / B | 1943-03–2026-08 |
| `poverty_linked.csv` | `argendata_cedlas_isa_pobreza_nacional` / `diloretot_tasa_pobreza` | B / A | 2001-05–2026-01 |
| `poverty_gba.csv` | `argendata_cedlas_isa_pobreza_gba` | B | 1988-05–2006 S2 |
| `poverty_gba_households_beccaria.csv` | `argendata_cedlas_isa_pobreza_gba_hogares_beccaria` | B | 1974–1983 (6 años) |
| `poverty_gba_households_arakaki.csv` | `argendata_cedlas_isa_pobreza_gba_hogares_arakaki` | B | 1974–1989 (9 años) |
| `poverty_cedlas_homogeneous.csv` | `argendata_cedlas_isa_pobreza_homogenea` | B | 1992-05–2025 S1 |
| `indigence_cedlas_homogeneous.csv` | `argendata_cedlas_isa_indigencia_homogenea` | B | 1992-05–2025 S1 |
| `unemployment_annual_modelled.csv` | `argendata_wb_ilo_desempleo` | B | 1991–2022 |

No se generaron (ver `coverage.md` → Faltantes): `inflation_deflator_annual.csv` (reemplazado
por `gdp_deflator_annual.csv`, ver fuente 17; la extensión 2007+ sigue pendiente, la API del
Banco Mundial da 403 también desde la sesión del 2026-09-15 y el único candidato en mirror se
descartó, fuente 21), tipo de cambio 1810–1878 y 1952–1961 (ver fuente 16 — el hueco
era 1952–1991 por un artefacto de escala en Clio Infra; la fuente 22 lo cerró desde 1962 con el
indicador `PA.NUS.FCRF` del Banco Mundial, ya enlazado a través de las redenominaciones, así que
lo que resta sin dato anual es 1952–1961), desocupación EPH
puntual 1974–2002 (solo se consiguió el modelado OIT 1991+, fuente 20), tasa de política
monetaria oficial del BCRA (fuente 18: no está en el mirror), desglose de deuda pública (MECON,
403). `inflation_cpi_monthly_linked.csv` **sí** se generó en la pasada del 2026-09-15 (fuente
18: la serie histórica empalmada 1943-03+ la sirve la API del BCRA, id 27, vía mirror).
