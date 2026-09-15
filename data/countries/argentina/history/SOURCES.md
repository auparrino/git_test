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

### Repos evaluados y **rechazados** (no se muestrean sus datos)

Se buscaron candidatos con `WebSearch` (`matuteiglesias/IPC-Argentina`,
`thomasriveros/BCRA_Data`, `jmtelechea/dashboard-macro-argentina`,
`DiLoretoT/estadisticas-argentinas`, `ahierro/ipc_csv_processor`). Dos de los cinco
resultaron **sospechosos** y se descartaron sin usar ningún dato ni ejecutar ningún código:

- **`matuteiglesias/IPC-Argentina`**: el `README.md` describe archivos
  (`data/info/indice_precios_M.csv`, etc.) que **no existen** en el repo. El contenido real
  del repo es una copia de un proyecto de simulación agéntica no relacionado (con
  `src/republica/...`, `.venv` compilado, `AGENTS.md`, documentos `CODEX_BATCH3_*`) — es
  decir, contenido que no coincide con lo que el README anuncia. Se trata como repositorio
  no confiable (posible *decoy*/inyección dirigida a un agente que hace justamente esta
  tarea). **No se clonó ningún dato de acá para las series; el clon se borró del
  scratchpad.**
- **`ahierro/ipc_csv_processor`**: el inicio del `README.md` (secciones 1–2, IPC y tipo de
  cambio) es específico y verificable (URLs de `datos.gob.ar` y `bcra.gob.ar`, validación
  cruzada contra la serie 7931 del BCRA). Pero el resto del repo contiene, otra vez, una
  copia de un proyecto no relacionado (`src/republica/...`) y el propio `README.md` deriva,
  sin transición, hacia texto sobre "Fase 9", "Fase 10", "República Artificial" — contenido
  ajeno al proyecto que dice ser. Por la misma razón que el anterior, se descarta
  **el repo completo**, incluidas sus CSV de dólar blue e IPC que a primera vista parecían
  utilizables: no se puede confiar en el resto del repo si una parte fue adulterada.
  **trust: C (descartado, no usado).**

Ninguno de los dos aporta filas a ningún CSV de este directorio.

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

---

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

No se generaron (ver `coverage.md` → Faltantes): `inflation_deflator_annual.csv`,
`exchange_rate_annual.csv` (1810–1991, previo a la cobertura BCRA).
