# `cohorts.csv` / `cohorts_loyalty.csv` / `media_consumption.csv` — nota

Copia sin ajustar de los archivos homónimos de Aurora (`data/cohorts.csv`,
`data/cohorts_loyalty.csv`, `data/media_consumption.csv`), deliverable de A2
(ADR 011, ítem 1). Son las 8 cohortes sociales, la matriz de lealtad inicial
por cohorte/partido y el consumo de medios por cohorte de la República de
Aurora tal cual, **no** calibradas contra ninguna encuesta ni censo real de
Argentina: no hay una fuente pública descargable de composición socioeconómica
por cohorte, lealtad partidaria histórica por bloque social ni consumo de
medios por segmento para el período 1983-2023 dentro del alcance de A2.

No se agregó una columna `note` al CSV: `world/perception.py::
load_media_consumption` interpreta TODAS las columnas menos `cohort` como
`float` (share de audiencia), así que una columna de texto ahí rompería el
loader. Este archivo cumple el mismo rol de documentación sin tocar el
esquema.

Ajustar estos tres archivos a datos reales de Argentina (encuesta de
opinión pública por segmento, panel electoral, medición de audiencias) queda
fuera de alcance de A2 y es candidato natural para A3 (calibración) o A5
(actores argentinos).
