# `data/countries/argentina/politics/` — cronología política 1810-2023

Entregable de la fase **A1** de `docs/PLAN_ARGENTINA.md` (ver §0, §1 y la fila A1 de §2). Cubre la
política argentina — presidentes, golpes, elecciones, reformas constitucionales, crisis, acuerdos con el
FMI y sistema de partidos por época — desde la Revolución de Mayo (1810) hasta el fin de 2023. **No**
escribe en `data/countries/argentina/history/` (series económicas cuantitativas), que es responsabilidad
de otro agente en paralelo.

## Regla de oro (§0 del plan)

Todo número o fecha con `source` que empieza con `general_knowledge` es un **hecho público cargado sin
archivo descargado**, no verificado por este agente contra una fuente primaria. **No implica que el dato
sea incorrecto** — son hechos ampliamente documentados de historiografía argentina estándar — pero
**debe pasar por la revisión de hechos independiente** (Opus 5, según el plan) antes de usarse para
calibrar o validar el motor. `PENDING_FACTCHECK.md` lista automáticamente cada fila en esa situación.

Donde existió un archivo descargable con números reales, se usó y se cita con URL + hash en
`SOURCES.md`. Ver esa sección para el detalle exacto de qué se descargó y qué se buscó sin éxito.

## Archivos

### `events.csv`
Un evento político por fila. Columnas:

| Columna | Significado |
|---|---|
| `date` | ISO `YYYY-MM-DD`. Si no se conoce el día, se usa el día 1 del mes o el 1 de enero, y `date_precision` lo indica. |
| `date_precision` | `day`, `month` o `year`: qué tan preciso es `date`. |
| `kind` | Uno de: `presidency_start`, `presidency_end`, `coup`, `election_presidential`, `election_legislative`, `constitutional_reform`, `default`, `imf_agreement`, `hyperinflation`, `crisis_banking`, `war`, `pandemic`, `currency_regime_change`, `other`. |
| `title` | Descripción corta del evento. |
| `actor` | Persona, partido o institución protagonista. |
| `notes` | Contexto; para elecciones con archivo descargado, incluye padrón, participación y el top 3 sobre votos válidos. |
| `source` | URL/documento de origen, o `general_knowledge (...)`. |
| `confidence` | `high`, `medium` o `low` — criterio del analista sobre qué tan sólido es el dato, independiente de si tiene archivo descargado o no (un hecho de `general_knowledge` muy consensuado puede ser `confidence: high`). |
| `reviewed_by` | `opus` si la fila pasó por la revisión de hechos independiente; vacío si todavía no. Las filas revisadas llevan una nota `REVISOR:` en `notes` cuando algo no se pudo cerrar. |

217 filas. Cubre: todos los presidentes/jefes de Estado desde 1810 y cómo dejaron el cargo (`presidency_start`/`presidency_end`); 9 golpes exitosos (1930, 1943, 1955 ×2 —incluido el desplazamiento de Lonardi por Aramburu—, 1962, 1966, 1970, 1971 y 1976: los tres últimos agregados por el revisor para reconciliar con `e_pt_coup` de V-Dem) más 6 intentos fallidos documentados (1951, 1962-63 azules/colorados, y los 4 alzamientos carapintada de 1987-1990); las reformas constitucionales de 1853/1860/1949/1957/1994; 23 elecciones presidenciales desde 1916 (13 con datos descargados 1946-2019 + balotaje 2015, el resto `general_knowledge`); los 5 defaults pedidos (1890, 1982, 2001, 2014, 2020); los 10 acuerdos con el FMI pedidos (1958 a 2022); hiperinflación 1989-90 (2 filas); Malvinas 1982 (2 filas); convertibilidad (inicio 1991, fin 2002); corralito (2001); pandemia (2020); sequía (2023).

### `regimes.csv`
Una fila por año, 1810-2023 (214 filas exactas — verificado en `tests/test_argentina_politics.py`).
`regime_mode` ∈ `{democracy, restricted_democracy, coup, dictatorship, transition, civil_war_or_state_building}`
según la periodización del plan. `head_of_state` es quien ejercía el cargo al **31 de diciembre** de ese
año (convención elegida para que los años de golpe muestren al gobernante de facto resultante, no al
depuesto). `how_selected` ∈ `{election, coup, succession, congress, junta}`. `elections_held` es booleano.
`vdem_regime` **ya está completo** (199 de 214 años): lo llenó la revisión independiente cruzando con
`history/vdem_argentina.csv`. `vdem_regime_source` dice de dónde sale cada valor (`v2x_regime` nativo
desde 1900; `derived:e_boix_regime+e_p_polity` para 1825-1899) y queda vacío en 1810-1824, donde V-Dem
no tiene ninguna de las tres variables. `reviewed_by` es `opus` en toda la tabla. El cruce año por año,
la matriz de confusión y el veredicto de cada desacuerdo están en **`REGIME_CROSSCHECK.md`**; la única
corrección de `regime_mode` fue 1949-1954 (`democracy` → `restricted_democracy`). La columna `source`
sigue siendo `general_knowledge` (periodización propia) porque no hay un archivo de régimen año a año
descargable en este entorno aparte de V-Dem.

### `parties/<era>.json`
Un array de partidos por cada una de las 7 eras pedidas (`1916-1930`, `1946-1955`, `1958-1966`,
`1973-1976`, `1983-2001`, `2003-2015`, `2015-2023`). Cada partido:

```
{
  "id": "...", "name": "...",
  "economic": -1..1, "social": -1..1, "assessment": "analyst",
  "federalism": -1..1,
  "seats_share": 0..1, "seats_share_source": "...", "seats_share_confidence": "low|medium|high",
  "in_government": true|false,
  "notes": "..."
}
```

`economic`/`social`/`federalism` son **siempre** juicio del analista (`assessment: analyst`): no existe
una serie descargable de posicionamiento ideológico partidario para Argentina en este entorno, y el plan
pide explícitamente "tu juicio". `seats_share` es la composición aproximada de la Cámara de Diputados al
**inicio** de la era; no se encontró un archivo descargable con series históricas de bancas por bloque
(se buscó en `legislAr/` de `PoliticaArgentina/data_warehouse`, que solo trae logs de verificación), así
que es `general_knowledge`/`confidence: low` en todos los casos — el campo más débil de este entregable.

### `provinces.csv` / `regions.csv`
24 jurisdicciones (23 provincias + CABA) agrupadas en las 8 regiones del plan (CABA, GBA, Pampeana,
Córdoba–Santa Fe, NOA, NEA, Cuyo, Patagonia). `population_2022` son cifras del Censo Nacional 2022 tal
como se difundieron públicamente, cargadas de memoria (`general_knowledge`, `confidence: medium`); el
revisor corrigió Córdoba (3.840.905 → 3.978.984), con lo que la suma de las 24 jurisdicciones queda a
−0,08 % del total nacional provisional de INDEC (46.044.703) — se
buscó un mirror de GitHub con los totales definitivos (`RodriDuran/censo2022arg` procesa microdatos
REDATAM pero requiere el sitio oficial `censo.gob.ar`, bloqueado) sin encontrar un archivo plano
descargable. `dependence_on_transfers` (0-1) y `main_sector` son evaluación del analista con
`dependence_reasoning` explicando el criterio en cada fila. `regions.csv` agrega población real (suma de
`provinces.csv`) y un `gdp_share_approx` que es estimación del analista (`confidence: low`), no una serie
oficial de PBG.

### `shocks_calendar.csv`
El calendario de shocks históricos del plan §1, mapeado a IDs del motor. Columnas: `shock_id`, `date`,
`duration_months`, `magnitude` (0-1, evaluación del analista), `title`, `notes`, `source`, `confidence`.
Usa IDs existentes del motor (`drought`, `commodity_boom`, `international_crisis`, `banking_crisis`,
`epidemic`) donde hay match, y agrega los IDs nuevos que el plan pide para Argentina y que Aurora no
tiene: `sovereign_default`, `currency_run`, `war`, `imf_program`, `hyperinflation_regime`. 20 filas, desde
la Gran Depresión (1930) hasta la sequía de 2023. `magnitude` es siempre evaluación del analista; fechas
y ocurrencia de cada shock son hechos públicos ampliamente documentados.

### `SOURCES.md`
Detalle de qué se descargó (URL, licencia, fecha, hash SHA-256 de cada archivo fuente en
`sources/electorAr_presi/`) y qué se buscó sin encontrar un archivo descargable, para no repetir la
búsqueda.

### `PENDING_FACTCHECK.md`
**Reescrito por la revisión independiente** (Opus 5). Ya no es la lista mecánica de 499 filas con
`confidence != high`: separa lo que quedó verificado o corregido de lo que sigue necesitando una fuente
externa, con la prioridad sugerida para la próxima pasada al final.

### `REGIME_CROSSCHECK.md`
Cruce de `regimes.csv` contra V-Dem año por año: cómo se llenó `vdem_regime`, la matriz de confusión,
los 21 años en desacuerdo con su veredicto (corregir / mantener con razón / ambiguo), el contraste de
`e_pt_coup` contra nuestras filas `coup`, y por qué la tasa de desacuerdo real (16,9 % sobre 1900-2023)
queda por encima del objetivo del 15 % sin falsear la periodización.

## Cómo debería usarlo el revisor

1. Leer `SOURCES.md` primero para saber qué ya tiene respaldo de archivo descargado (no hace falta
   volver a verificar los 14 archivos de `sources/electorAr_presi/`, sí vale la pena spot-check).
2. Recorrer `PENDING_FACTCHECK.md` de arriba hacia abajo, empezando por la prioridad sugerida al final
   del archivo.
3. Para cada fila, decidir: **OK** (el hecho es correcto, subir `confidence` a `high` si corresponde),
   **corregir** (arreglar el dato en el CSV/JSON y bajar la nota de por qué), o **eliminar** (si no se
   puede verificar y no vale la pena mantenerlo).
4. El cruce contra V-Dem ya está hecho: leer `REGIME_CROSSCHECK.md` antes de tocar `regimes.csv`.
5. Correr `uv run pytest -q tests/test_argentina_politics.py` después de cualquier edición: valida
   estructura (una fila por año en `regimes.csv`, cada `presidency_start` con su `presidency_end` o ser
   el actual, fechas monótonas por `kind`, y que cada `parties/*.json` valide contra el modelo pydantic
   definido en el test).
