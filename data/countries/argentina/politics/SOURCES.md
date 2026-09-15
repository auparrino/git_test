# Fuentes descargadas — `data/countries/argentina/politics/`

## 1. Resultados electorales presidenciales 1946-2019 (`sources/electorAr_presi/`)

- **Repositorio**: [PoliticaArgentina/data_warehouse](https://github.com/PoliticaArgentina/data_warehouse)
  (subcarpeta `electorAr/data/escrutinios_definitivos/` y `electorAr/data/escrutinios_provisorios/`).
- **Licencia**: MIT (Juan Pablo Ruiz Nicolini, 2021; ver `LICENSE.md` del repo).
- **Fecha de descarga**: 2026-09-15, vía `git clone --depth 1 https://github.com/PoliticaArgentina/data_warehouse.git`.
- **Archivos usados** (copiados a `sources/electorAr_presi/`, con su hash SHA-256):

| Archivo | SHA-256 |
|---|---|
| arg_presi_gral1946.csv | `08cfd195f1d0f585a94c397d366025596f6721afb0758d31ed516a8c994e5c80` |
| arg_presi_gral1951.csv | `1cb9032382f987fb0cb9b7ff9608b0f7dddc39d180d7443b22cfb2a0fe7c9ad0` |
| arg_presi_gral1958.csv | `d5408b6c373f89d20f7e4f41d13704efaaf47c1c5da6cad6136a4d04346c6d6d` |
| arg_presi_gral1963.csv | `b5ed5ff148dd9b87e9b4d5e14d5ee85a400a5ca6054cc4e0e5ecded6ab3b68d8` |
| arg_presi_gral1983.csv | `347a50b8cab3257bb2b75f8717c0ae0493cd10775ff7c4234d8118903358a4d4` |
| arg_presi_gral1989.csv | `d32d869fb9de8bf86551993d34ccf1f46451e4b342c4ceb595e5c1e2a3de26f7` |
| arg_presi_gral1995.csv | `4b84f83732161c7f3b9b59927bfde6eb89a99a0ffe6622561a3683693a7f1e68` |
| arg_presi_gral1999.csv | `53f30d953ae2167b2b7c4bfff0a08fac6af1ecd914bc4bacbd8c861792babb19` |
| arg_presi_gral2003.csv | `d21182612c64195c7266f0ac6e8150613873af70ef7d5b85fff80e852dd486c3` |
| arg_presi_gral2007.csv | `806bf5c82b4e69a3dae28d77054dc20ac97f0e7e4a8b54ba5956df77160c3f02` |
| arg_presi_gral2011.csv | `a35a780a7a44f966eaff241063b15fa60d18b1fcd12f76471d346cffafcc5164` |
| arg_presi_gral2015.csv | `34f39f5cb8305d4a87d00b59979e0fbb6ab3b42adf20d7ec9bbdb05fd513f824` |
| arg_presi_gral2019.csv | `8aaaa6943e2687246b6838ecdf93e64bb8dfee70e0e66accf1861d1c3872e1d7` |
| arg_presi_balota2015.csv | `6ae4f579e6fde074896e990d1d73cda0daf642f54db684e18b9f9961a3ce0475` |

- **Contenido**: cada archivo trae, para una elección presidencial dada, el total nacional de votos por
  fórmula/lista y el padrón nacional (`electores`), ya agregados desde las actas de mesa por el propio
  repositorio (proyecto "Política Argentina", construido sobre datos de escrutinios definitivos de la
  Dirección Nacional Electoral / Cámara Nacional Electoral).
- **Procesamiento**: `scripts` de agregación corridos en el entorno de trabajo (no versionados en el
  repo del proyecto) calculan `turnout_pct = 100 * total_votos / electores` y el porcentaje de cada
  fórmula sobre **votos válidos** (excluyendo blancos y nulos) para las tres primeras fórmulas de cada
  elección. Estos números pueblan las filas `kind=election_presidential` de `events.csv` para los años
  1946, 1951, 1958, 1963, 1983, 1989, 1995, 1999, 2003, 2007, 2011, 2015 (1ra vuelta y balotaje) y 2019.
  `confidence: high`, `source` apunta a este documento.
- **Cobertura**: el repositorio **no** tiene datos consolidados para 1916, 1922, 1928, 1931, 1937, 1973
  (2 elecciones) ni 2023 — esos años se completaron con `source: general_knowledge` (ver `PENDING_FACTCHECK.md`).
- **No usado pero explorado**: `PoliticaArgentina/electorAr` (paquete R) — sus funciones descargan datos
  en vivo desde la infraestructura oficial de la DNE, no alcanzable desde este entorno; el repo en sí no
  trae los CSV embebidos (solo un dataset de ejemplo de Tucumán 2017). `legislAr/` dentro de
  `data_warehouse` solo contiene logs de verificación (`data_check/*.csv`), no resultados legislativos
  consolidados: por eso `seats_share` en `parties/*.json` es `general_knowledge`.

## 2. Búsquedas sin resultado (documentadas para no repetirlas)

- **Censo 2022 por provincia (población total)**: se buscó `RodriDuran/censo2022arg` (paquete R que
  procesa microdatos REDATAM descargados de `censo.gob.ar`, bloqueado desde este entorno) y repos de
  `datosgobar`; ningún mirror de GitHub trae los totales definitivos por provincia como archivo plano.
  `provinces.csv.population_2022` queda en `source: general_knowledge`, `confidence: medium`.
- **Composición histórica del Congreso (bancas por bloque)**: sin archivo descargable encontrado.
  `parties/*.json.seats_share` queda en `general_knowledge`, `confidence: low` — el campo más débil de
  este entregable.
- **PBG (producto bruto geográfico) por provincia/región**: sin archivo descargable encontrado.
  `regions.csv.gdp_share_approx` es una estimación del analista (`confidence: low`), no una serie oficial.

## 3. V-Dem (referencia, NO descargado por este agente)

`regimes.csv.vdem_regime` se deja vacío a propósito: según §2 (fila A0/A1) del plan, la serie V-Dem
completa (1810+) la descarga y normaliza el agente que trabaja en paralelo sobre
`data/countries/argentina/history/`. Este agente no escribió en esa carpeta (regla explícita de la
tarea). El cruce `regime_mode` (este dataset) vs. `v2x_regime`/similar (V-Dem) queda pendiente para el
revisor una vez que ese archivo exista.
