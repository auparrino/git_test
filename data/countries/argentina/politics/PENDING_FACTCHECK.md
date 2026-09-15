# PENDING_FACTCHECK.md — estado después de la revisión independiente

Revisor: **Opus 5**, 2026-09-15. Reemplaza la versión generada automáticamente (499 filas
marcadas, una por cada fila con `confidence != high` o `source: general_knowledge`). Esa
lista mecánica no era útil: marcaba por igual "Perón asume el 4-jun-1946" y un
`seats_share` inventado de memoria. Esta versión separa **lo que quedó verificado** de
**lo que sigue necesitando una fuente externa**, que es la única distinción que importa
para calibrar el motor.

El cruce completo de `regimes.csv` contra V-Dem está en **`REGIME_CROSSCHECK.md`**.

## Resumen

| Archivo | Filas | Verificadas / corregidas | Siguen pendientes |
|---|---:|---|---|
| `events.csv` | 217 | 187 `confidence: high`; 48 con `reviewed_by: opus` | 13 filas sin revisar + 17 revisadas que siguen en `medium` |
| `regimes.csv` | 214 | `vdem_regime` completo (199/214); 6 años corregidos | 1810-1824 sin contraste; 1825-1899 con `vdem_regime` derivado |
| `provinces.csv` | 24 | Córdoba corregida; suma a 0,08 % del total INDEC | los 23 valores restantes siguen sin archivo oficial |
| `regions.csv` | 8 | población recalculada desde `provinces.csv` | `gdp_share_approx` sigue siendo estimación del analista |
| `shocks_calendar.csv` | 20 | 2 notas corregidas (hiper-1989, FMI-2018) | `magnitude` es y seguirá siendo juicio del analista |
| `parties/*.json` | 33 | ejes revisados: **sin errores groseros** | los 33 `seats_share` siguen sin fuente |

---

## 1. Correcciones aplicadas

### `regimes.csv`
- **1949-1954**: `democracy` → `restricted_democracy`. Fundamento y corte en 1949 en
  `REGIME_CROSSCHECK.md` §5.
- `vdem_regime` completado para 199 de 214 años; nuevas columnas `vdem_regime_source` y
  `reviewed_by`.

### `events.csv`
- **1815-01-09** (era 1815-04-09): renuncia de Posadas y asunción de Alvear. El archivo
  daba a Alvear un gobierno de 9 días; gobernó ~3 meses.
- **1816-04-16** (era 1816-02-16): renuncia de Álvarez Thomas.
- **1816-05-03** (era 1816-02-16): designación de Pueyrredón por el Congreso de Tucumán.
- **1826-02-08** (era 1824-05-08): cierre de la vacancia de poder nacional, que la propia
  nota de la fila fechaba en 1826.
- **1962-09-01** (era 1962-04-01): primer choque azules/colorados.
- **Elección de sep-1973**: Manrique 3,6 % → ~12,2 %. Con sólo tres fórmulas y ~1,6 % de
  votos en blanco, 61,9 + 24,4 + 3,6 dejaba ~10 % sin explicar.
- **Elección de 1916**: se eliminaron dos atribuciones incorrectas (el segundo puesto no
  fue de "Ángel Rojas (PDP)" —el candidato del PDP fue Lisandro de la Torre— y Estanislao
  Zeballos no fue candidato). No se reemplazaron por porcentajes nuevos.
- **Hiperinflación de 1989**: el pico mensual fue ~197 % (jul-1989), no ">200 %". Misma
  corrección en `shocks_calendar.csv`.
- **FMI 2018**: el Stand-By aprobado el 20-jun-2018 fue por ~USD 50.000 M; los 57.000 M
  son el monto ampliado en oct-2018. Misma corrección en `shocks_calendar.csv`.
- **3 filas `coup` nuevas** (1955-11-13, 1970-06-08, 1971-03-23): golpes palaciegos que
  estaban en el archivo sólo como `presidency_end` con `Modo de salida: coup`. Reconcilian
  el conteo con `e_pt_coup` de V-Dem (`REGIME_CROSSCHECK.md` §7).
- Notas aclaratorias sin cambio de fecha en: reforma de 1860, reforma de 1957, FMI 1991,
  Monte Caseros 1988, default de 1982, elecciones de 1922/1928/1931/1937.

### `provinces.csv` / `regions.csv`
- **Córdoba: 3.840.905 → 3.978.984**. Estaba ~138.000 por debajo del resultado del Censo
  2022. Con la corrección la suma de las 24 jurisdicciones da **46.009.897** contra el
  total nacional provisional de INDEC de **46.044.703** (−34.806, −0,08 %).
- `regions.csv`: población de Córdoba–Santa Fe recalculada (7.397.427 → 7.535.506).
- Las otras cuatro jurisdicciones grandes verificadas contra las cifras difundidas:
  Buenos Aires 17.569.053, CABA 3.120.612, Santa Fe 3.556.522, Mendoza 2.014.533.

---

## 2. Sigue pendiente (requiere fuente externa)

### 2.1 Elecciones sin escrutinio descargado — lo que falta es la DNE/CNE

De las 9 elecciones sin archivo, **1973 (marzo) y las dos vueltas de 2023 quedaron
verificadas** (`confidence: high`). Las otras seis siguen pendientes:

| Elección | Qué está verificado | Qué falta |
|---|---|---|
| 1916-04-02 | fecha, ganador, fórmulas en competencia | todos los porcentajes salvo el ~45 % de Yrigoyen |
| 1922-04-02 | fecha, ganador, segundo (Piñero) | porcentajes de los perdedores; si Crotto fue fórmula presidencial |
| 1928-04-01 | fecha, ganador, segundo (Melo) | **el 57,4 % de Yrigoyen**: la cifra más citada es ~61,8 % sobre votos válidos (838.583 votos). No se reemplazó sin escrutinio primario |
| 1931-11-08 | fecha, ganador, fórmula de la Alianza Civil | **el 20,6 % de la Alianza Civil parece subestimado**; las fuentes secundarias habituales la ubican en ~34-40 % |
| 1937-09-05 | fecha, fórmulas, orden de llegada, porcentajes dentro de rango | confirmación primaria de 55,7 / 43,0 |
| 1973-09-23 | fecha, ganador, tres fórmulas | confirmación primaria del ~12,2 % de Manrique (corregido desde 3,6 %) |

Dónde buscarlo: escrutinios definitivos de la Dirección Nacional Electoral / Cámara
Nacional Electoral. El repo `PoliticaArgentina/data_warehouse` ya usado en `SOURCES.md`
**no** los tiene para estos años (confirmado).

### 2.2 `events.csv` — 13 filas sin revisar

- **10 filas `imf_agreement` con `date_precision: year` o fecha sin confirmar**: 1958,
  1967, 1976, 1984, 1989, 1991, 2000-03-10, 2003-01-24. Que hubo un programa con el FMI en
  cada uno de esos años es un hecho público; lo que falta es la **fecha de aprobación del
  Directorio y el monto**. Fuente: histórico de acuerdos del FMI por país
  (`imf.org`, bloqueado desde este entorno). Además, la fila de 1991 está rotulada
  "Facilidad Ampliada" pero en 1991 el acuerdo vigente fue un Stand-By (el EFF es de
  marzo de 1992).
- **Filas compuestas de 1820-1862**: "sin autoridad nacional" (1820), "Vicente López y
  Planes / Manuel Dorrego / guerra civil" (1827-1829), "Balcarce / Viamonte / interinatos"
  (1832-1835, `confidence: low`) y "Pedernera / Mitre" (1861). Agregan varios gobernantes
  en una fila, así que sus fechas de corte son convencionales, no verificables como tales.
  Si el motor necesita esos años con precisión, hay que desagregarlas.

### 2.3 `events.csv` — 17 filas revisadas que siguen en `medium`

Todas tienen una nota `REVISOR:` explicando exactamente qué no se pudo cerrar. Las tres
que más conviene mirar:

- **1860-09-21, reforma constitucional**: la Convención Nacional ad hoc de Santa Fe
  sancionó las reformas el **23-sep-1860** y fueron juradas el 21-oct-1860. La fecha del
  archivo (21-sep) no coincide con ninguna de las dos.
- **1988-01-14, Monte Caseros**: el alzamiento fue del 15 al 18 de enero de 1988.
- **1815-04-18, caída de Alvear / asunción de Álvarez Thomas**: las fuentes ubican la
  caída entre el 15 y el 18 de abril y la designación de Álvarez Thomas el 20 o 21.

### 2.4 Presidentes interinos ausentes de la cronología

No se agregaron (requeriría desagregar filas compuestas), pero conviene saber que faltan:
**Antonio González Balcarce** (interino, abr-jul 1816), **Carlos Lacoste** (interino,
11-22 dic 1981) y **Alfredo Saint-Jean** (interino, 18-jun a 1-jul 1982). Las fechas de
`presidency_start`/`presidency_end` de los titulares que los rodean sí son correctas.

### 2.5 `parties/*.json` — sin errores groseros en los ejes, `seats_share` sin resolver

Se revisaron los 33 partidos en los tres ejes (`economic`, `social`, `federalism`)
buscando signos invertidos. **No hay ninguno**: ningún partido está del lado equivocado de
ningún eje. Los ejes son y seguirán siendo `assessment: analyst` por diseño.

Dos observaciones de grado (no errores, no se modificaron):
- `1946-1955` peronismo, `federalism: -0.1`: dado el uso sistemático de la intervención
  federal y la centralización de la reforma de 1949, un valor más negativo (~−0,4)
  describiría mejor el período.
- `1916-1930` UCR, `federalism: 0.0`: los gobiernos de Yrigoyen intervinieron provincias
  con mucha frecuencia; también apunta a un valor negativo.

**`seats_share` sigue sin fuente descargable en los 33 casos** (`confidence: low`). Dos
valores que llaman la atención y deberían verificarse primero:
- `1958-1966` UCRI **0,53**: en la elección de 1958 la UCRI obtuvo 133 de 187 diputados
  (≈0,71), con 52 para la UCRP (≈0,28). Los valores cargados (0,53 / 0,25) no cuadran.
- `1973-1976` FREJULI **0,62**: el FREJULI tuvo ~145 de 243 diputados (≈0,60), plausible,
  pero sin confirmar.
- Contraste positivo: `1983-2001` UCR 0,51 / PJ 0,44 **sí** coincide con la composición
  real de Diputados en 1983 (129 y 111 de 254).

### 2.6 `provinces.csv` / `regions.csv`

- Los 23 valores de población distintos de Córdoba siguen cargados de memoria
  (`general_knowledge`, `confidence: medium`). El residuo de −34.806 contra el total
  nacional (−0,08 %) indica que queda algún desvío chico repartido entre una o dos
  jurisdicciones, o la diferencia entre el provisional (46.044.703) y el definitivo
  (~46,2 M). Fuente: cuadros por jurisdicción del Censo 2022 de INDEC (`censo.gob.ar`,
  bloqueado desde este entorno).
- Ojo con la versión anterior de este archivo: daba el total nacional del Censo 2022 como
  **"~47,3 M"**. Es incorrecto — el provisional es 46.044.703 y el definitivo ~46,2 M.
- `dependence_on_transfers`, `main_sector` y `gdp_share_approx` son evaluación del
  analista; no hay serie de PBG provincial descargable.

### 2.7 `regimes.csv`

- **1810-1824**: V-Dem no tiene `v2x_regime`, `e_boix_regime` ni `e_p_polity`.
  `vdem_regime` queda vacío a propósito y la periodización de esos 15 años no tiene
  contraste externo.
- **1825-1899**: `vdem_regime` es **derivado por el revisor** a partir de
  `e_boix_regime` + `e_p_polity`, no un valor nativo de V-Dem (columna
  `vdem_regime_source`). Quien use esos 75 años para calibrar debería saberlo.
- **1964-1965**: desacuerdo genuinamente ambiguo con V-Dem, sin resolver
  (`REGIME_CROSSCHECK.md` §4).

---

## 3. Prioridad sugerida para la próxima pasada

1. Escrutinios de la DNE/CNE para 1928 y 1931 — son las dos filas con un número que
   probablemente esté mal, no sólo sin confirmar.
2. `seats_share` de `parties/1958-1966.json` (UCRI/UCRP), que parece directamente
   equivocado, y luego el resto de los 33.
3. Cuadros por jurisdicción del Censo 2022 de INDEC, para cerrar el residuo de −0,08 %.
4. Fechas de aprobación y montos de los 10 acuerdos con el FMI.
5. Desagregar las filas compuestas de presidentes 1820-1862 si el motor necesita esos años.
