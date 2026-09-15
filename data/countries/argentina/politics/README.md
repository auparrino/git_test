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

214 filas. Cubre: todos los presidentes/jefes de Estado desde 1810 y cómo dejaron el cargo (`presidency_start`/`presidency_end`); los 6 golpes exitosos pedidos (1930, 1943, 1955, 1962, 1966, 1976) más 6 intentos fallidos documentados (1951, 1962-63 azules/colorados, y los 4 alzamientos carapintada de 1987-1990); las reformas constitucionales de 1853/1860/1949/1957/1994; 23 elecciones presidenciales desde 1916 (13 con datos descargados 1946-2019 + balotaje 2015, el resto `general_knowledge`); los 5 defaults pedidos (1890, 1982, 2001, 2014, 2020); los 10 acuerdos con el FMI pedidos (1958 a 2022); hiperinflación 1989-90 (2 filas); Malvinas 1982 (2 filas); convertibilidad (inicio 1991, fin 2002); corralito (2001); pandemia (2020); sequía (2023).

### `regimes.csv`
Una fila por año, 1810-2023 (214 filas exactas — verificado en `tests/test_argentina_politics.py`).
`regime_mode` ∈ `{democracy, restricted_democracy, coup, dictatorship, transition, civil_war_or_state_building}`
según la periodización del plan. `head_of_state` es quien ejercía el cargo al **31 de diciembre** de ese
año (convención elegida para que los años de golpe muestren al gobernante de facto resultante, no al
depuesto). `how_selected` ∈ `{election, coup, succession, congress, junta}`. `elections_held` es booleano.
`vdem_regime` se deja **vacío a propósito**: lo completa el revisor cruzando con la serie V-Dem que
entrega el agente de `history/` (no escrita por este agente). Toda la columna `source` es
`general_knowledge` (periodización propia, ver `PENDING_FACTCHECK.md`) porque no hay un archivo de
régimen año a año descargable en este entorno aparte de V-Dem, que es responsabilidad del otro agente.

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
como se difundieron públicamente, cargadas de memoria (`general_knowledge`, `confidence: medium`) — se
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
Generado automáticamente a partir de los CSV/JSON de esta carpeta: lista **toda fila** con
`confidence != high` o `source` que empieza con `general_knowledge`. 499 filas al cierre de este
entregable (de un total de ~214 eventos + 214 años de régimen + 24 provincias + 8 regiones + 20 shocks +
~33 partidos — casi todo excepto los 14 archivos de elecciones descargados termina ahí, porque
`regimes.csv` entero y todos los partidos son `general_knowledge`/`assessment: analyst` por diseño de
estos entregables). Incluye una prioridad sugerida de revisión al final.

## Cómo debería usarlo el revisor

1. Leer `SOURCES.md` primero para saber qué ya tiene respaldo de archivo descargado (no hace falta
   volver a verificar los 14 archivos de `sources/electorAr_presi/`, sí vale la pena spot-check).
2. Recorrer `PENDING_FACTCHECK.md` de arriba hacia abajo, empezando por la prioridad sugerida al final
   del archivo.
3. Para cada fila, decidir: **OK** (el hecho es correcto, subir `confidence` a `high` si corresponde),
   **corregir** (arreglar el dato en el CSV/JSON y bajar la nota de por qué), o **eliminar** (si no se
   puede verificar y no vale la pena mantenerlo).
4. Una vez que `data/countries/argentina/history/vdem.csv` (u homólogo) exista, cruzar
   `regimes.csv.regime_mode` contra la serie V-Dem y completar `vdem_regime` — no está en el alcance de
   este agente.
5. Correr `uv run pytest -q tests/test_argentina_politics.py` después de cualquier edición: valida
   estructura (una fila por año en `regimes.csv`, cada `presidency_start` con su `presidency_end` o ser
   el actual, fechas monótonas por `kind`, y que cada `parties/*.json` valide contra el modelo pydantic
   definido en el test).
