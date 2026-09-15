# ADR 013 — Partidos, actores y lealtades argentinos por época (fase A5)

Estado: aceptado para implementar. Independiente del ADR 012 (archivos disjuntos); se integran en la
recalibración.

## 1. Decisión

El paquete de país deja de usar los partidos, actores y lealtades de Aurora cuando existe una
**época** que cubre la fecha de inicio. Una época es un directorio `data/countries/argentina/eras/<id>/`
con `parties.json`, `actors/*.yaml`, `cohorts_loyalty.csv` y `governance.yaml`; el loader elige la
época por `--start` y, en corridas largas, **cambia de época en la elección** que cruza la frontera
(los partidos nuevos entran con `seats` = 0 y lealtad inicial baja; los que desaparecen se retiran).
Sin época que cubra la fecha → fallback a Aurora, con aviso.

Épocas iniciales: `1983-2001`, `2003-2015`, `2015-2023` (las de `politics/parties/*.json`, que ya
tienen ejes ideológicos; ahora se completan con actores y lealtades).

## 2. `parties.json` por época

Campos de Aurora (`id, name, seats, economic, social, federalism, discipline, in_government,
coalition_weight`) más `founded` (año), `loyalty_seed` (lealtad inicial por cohorte, sección 4) y
`personalism` [0,1] (peso del candidato sobre el partido en el voto). `seats` = bancas reales de
Diputados al inicio de la época (fuente: `politics/PENDING_FACTCHECK.md` marca cuáles siguen sin
escrutinio; se usa la mejor cifra disponible con `confidence`).

Sistema 2015–2023 (100 bancas normalizadas): Unión por la Patria / Frente de Todos, Juntos por el
Cambio (PRO + UCR + CC como coalición con `discipline` menor), La Libertad Avanza (`founded 2021`,
`seats 0` en 2019, `loyalty_seed` ≈ 0, `personalism 0.9`), Frente de Izquierda, provinciales.

## 3. Actores por época (`actors/*.yaml`, mismo esquema que ADR 003)

Mínimo 25 por época: presidente y ministro de Economía del gobierno vigente al inicio, Banco Central,
8 gobernadores por región (el de cada región más poblada), los partidos, CGT y sindicato estatal
(ATE), UIA, Sociedad Rural, sector financiero, tres medios (Clarín/La Nación como `media_mercado`
o `media_nacional` según época, Página/12 o C5N como `media_popular`) y los 5 bloques sociales de
Aurora mapeados a las cohortes. Ideología e intereses son **evaluación del analista** (`assessment:
analyst`) con una línea de justificación; nombres de personas reales solo para cargos públicos
(presidentes, ministros, gobernadores) con fecha; nada de atributos de personalidad sobre personas
reales más allá de lo público (`ambition`, `risk_tolerance` se fijan en 0.5 salvo justificación
documentada).

## 4. Lealtades por cohorte (`cohorts_loyalty.csv` por época)

Misma estructura que Aurora (cohorte × partido, aditivo en la utilidad, más `turnout`). Se estiman
a partir de los resultados reales descargados (`politics/sources/electorAr_presi/*.csv`) por el
procedimiento inverso: dados los shares nacionales reales de la primera elección de la época y la
composición de cohortes (`cohorts.csv` de Argentina: participación real de informales, jubilados,
empleados públicos por EPH cuando exista; si no, la de Aurora con `note`), se resuelven las
lealtades que reproducen esos shares bajo utilidad neutra (aprobación 50, economía plana) con el
mismo softmax y τ del motor. Test: la elección de apertura de cada época se reproduce ±3 pp con
utilidad neutra.

## 5. Partidos nuevos

Un partido con `founded` posterior al inicio de la corrida no existe hasta su fundación; al entrar,
`loyalty_seed` (bajo) más un término `outsider_bonus · pos(50 − government_approval) · (1 −
institutional_confidence/100)` en la utilidad de todas las cohortes con `econ_pref` del lado del
partido: el voto anti-sistema crece con el descontento y la desconfianza. `outsider_bonus` es un
coeficiente calibrable (default 0.3). Es la única forma en que LLA puede ganar en 2023 dentro del
modelo, y se dice así.

## 6. Tests
1. `load_country_pack("argentina", "2019-12")` carga la época `2015-2023` (partidos, actores, lealtades); `"1983-12"` la `1983-2001`; `"1900-01"` cae a Aurora con aviso.
2. Elección de apertura reproducida ±3 pp con utilidad neutra, por época.
3. Corrida 2019-12 → 2023-12: LLA existe desde 2021-01; con aprobación < 30 y confianza < 35 sostenidas, gana en ≥ 30 % de semillas; con aprobación 55, en < 5 %.
4. Cambio de época en la elección de 2015 en una corrida 2011-12 → 2019-12: los partidos de la época siguiente aparecen y el JSONL registra `era_change`.
5. Golden de Aurora intacto; corridas de Argentina sin época cambian solo con aviso.

## Notas de implementación

Retomado de un WIP ya comiteado en HEAD (partidos/actores/lealtades de las 3 épocas, `world/eras.py`,
integración en `world/countries.py`/`world/elections.py`, `scripts/build_argentina_eras.py`), con
tests verdes pero lint pendiente. Esta pasada: (1) lint, (2) auditoría §1–§5 y un gap real que
encontró (la CLI no pasaba los actores/lealtades de época a `run()`), (3) `tests/test_eras_argentina.py`
nuevo, (4) esta sección, (5) README.

### 1. Lint

`ruff format .` resolvió 84 de los 86 `E501` solo reordenando líneas (nada de contenido cambió); los
2 restantes eran un `Era(...)` de una sola línea en `world/eras.py` y una comprehension en
`estimate_loyalties`'s vecino `_neutral_shares` — se partieron a mano. El `B007` (`for era_id,
builder in ERA_BUILDERS.items()` con `era_id` sin usar) se corrigió a `for builder in
ERA_BUILDERS.values()`. Quedaron 6 `assessment_note`/`bio` de una sola línea larga en
`scripts/build_argentina_eras.py` (sindicatos/empresarios/gobernadores) que `ruff format` no puede
partir por ser literales de string: se partieron a mano en `"..." "..."` concatenado, sin cambiar el
texto. `ruff check .` y `ruff format --check .` quedan verdes.

### 2. Gap encontrado: la CLI no usaba los actores/lealtades de época

`load_country_pack` ya escribía los partidos de la época en `merged/parties.json` (así que
`country.parties` salía correcto), pero el comando `republica run` nunca leía `pack.era.actors`/
`pack.era.loyalty_table`: `run_simulation()` se llamaba sin `actors=`/`loyalty_table=`, así que
`new_simulation` caía a sus defaults (los 29 actores y la `LoyaltyTable` de **Aurora**, con `id`s que
no coinciden con los de la época — `gov_norte` en vez de `gov_buenos_aires`, lealtad 0.0 para todo
partido de época por no tener entrada en el CSV de Aurora, sin `era_boundaries`/`outsider_bonus`).
Es decir: `republica run --country argentina --start 2019-12 ...` (el comando de ejemplo del ADR y
del README) corría con el universo de partidos correcto pero los actores y la elección equivocados,
sin ningún error ni aviso. Se corrigió en `src/republica/cli.py::run` (no es `engine/simulation.py`
ni `world/*.py`, así que no viola la restricción de la tarea): si `pack.era is not None and
pack.era.parties is not None`, `era_actors`/`era_loyalty_table` se resuelven de `pack.era.actors`/
`pack.era.loyalty_table` y se pasan a `run_simulation(actors=..., loyalty_table=...)`; sin época
(fallback a Aurora) quedan en `None`, mismo comportamiento que antes. Verificado con una corrida real
(`republica run --country argentina --start 2019-12 --months 48 --fx-regime auto`): el JSONL trae
`biz_agro`/`gov_caba`/`media_nacional`/etc. (ids de la época 2015-2023), no `gov_norte`/etc. de
Aurora. El golden de Aurora (que nunca pasa `--country`, así que `era_actors`/`era_loyalty_table`
quedan `None` de entrada) se re-verificó después de este cambio: sigue byte a byte igual.

Un segundo gap de la misma familia, encontrado auditando §1 ("`governance.yaml` propios"): nada leía
`pack.era.governance_path` tampoco — `engine/scheduler.py::build_actor_engine` siempre llama
`load_governance(overrides=governance_overrides)` con el `path` default (`data/governance.yaml` de
Aurora), y ningún actor de época tiene entrada ahí (`id`s distintos), así que cada uno caía a
`Governance._default_governance`: `autonomy: 5`, `read`/`write`/`execute` sin restringir — lo
opuesto de lo que su propio `governance.yaml` generado declara (p. ej. `central_bank` con
`autonomy: 2`, `execute: [SET_RATE]` pero `human_approval_required: true`,
`max_authority: recommendation_only`, ADR 003 secc. 6.4: "solo recomienda, no fija la tasa"). Agregar
un parámetro `governance_path` a `run()`/`new_simulation()` para esto hubiera violado la restricción
de la tarea sobre `engine/simulation.py` (solo se permite tocarlo para `era_change`), así que se usó
el mecanismo que YA viaja de punta a punta sin tocarlo: `--governance-override` (ADR 007 deliverable
6, `dict[str, str]` de `actor.campo=valor`). `world/eras.py::era_governance_overrides` convierte el
`governance.yaml` completo de la época a ese formato (261-270 claves según la época); `cli.py::run`
lo mergea con cualquier `--governance-override` explícito del usuario (que pisa, en la clave que
coincida) antes de pasarlo a `run_simulation`. Verificado cargando `Governance` con el resultado para
las 3 épocas: `central_bank.autonomy == 2`/`max_authority == "recommendation_only"` en las 3.

### 3. Auditoría §1–§5: qué ya cumplía, qué se corrigió

- **§1/§2 (carga por fecha, `founded`/`loyalty_seed`/`personalism`/`seats`)**: cumplía. `seats` de
  cada partido trae `seats_confidence`/`seats_source` (`low`/`medium`/`n/a`, todos derivados de
  `politics/parties/<era>.json:seats_share`, que ya estaba documentado como `confidence: low` /
  `general_knowledge` en `politics/PENDING_FACTCHECK.md` antes de este WIP — no hay ningún número de
  bancas inventado nuevo en esta pasada). La suma de `seats` por época da 100/65/94 (1983-2001,
  2003-2015, 2015-2023): NO es un error — es 100 menos la porción de `seats_share` que le
  correspondería a un partido todavía no fundado a la fecha de apertura de esa época (`pro`/`fit`
  fundados 2005/2011, cero bancas en la apertura 2003-05 de "2003-2015"; `lla` fundado 2021, cero en
  la apertura 2015-12 de "2015-2023"), consistente con §5 aplicado también a `seats`, no solo a la
  ventana activa de la elección.
- **§3 (actores)**: cumplía. Las 3 épocas traen 29/30/29 actores (≥ 25), todos con `assessment:
  analyst` y `assessment_note`; verificado por grep que ningún YAML de época falta ninguno de los
  dos campos. `ambition`/`risk_tolerance` de las fichas con nombre de persona real (presidente,
  ministro de Economía, gobernadores, Banco Central) son 0.5/0.5 exacto en las 3 épocas
  (`REAL_PERSON_PERSONALITY` en el script); las fichas institucionales (partido/sindicato/empresa/
  medio/bloque social, que NO son personas) sí varían — la sección 3 del ADR restringe el 0.5 "salvo
  justificación documentada" a **personas reales** ("nada de atributos de personalidad sobre personas
  reales"), no a instituciones ficticias, así que esto se interpretó como cumplimiento, no como
  desviación.
- **§4 (lealtades por el procedimiento inverso)**: cumplía y se verificó reproducible:
  `uv run python scripts/build_argentina_eras.py` regenera los 3 `cohorts_loyalty.csv` sin diff
  (`git status` limpio después de correrlo). Error de reproducción de la elección de apertura, con
  utilidad neutra, medido en esta pasada (`tests/test_eras_argentina.py::
  test_opening_election_reproduced_within_3pp`): **< 0.01pp en las 3 épocas y los 12 partidos**
  (redondea a 0.00pp; la tolerancia de bisección de `estimate_loyalties` es mucho más fina que el
  ±3pp pedido). Ningún `xfail` hizo falta en este punto.
- **§5 (partidos nuevos, `outsider_bonus`)**: cumplía a nivel de mecanismo — LLA trae `founded: 2021`,
  `seats: 0` en `parties.json` de 2015-2023, `loyalty_seed: -0.5`, `outsider_bonus: 0.3` (el default
  del ADR), y `world/elections.py::compute_vote_intention` aplica el término
  `outsider_bonus · pos(50 − government_approval) · (1 − institutional_confidence/100)` solo a
  cohortes del mismo signo de `econ_pref`. `party_exists`/`LoyaltyTable.is_active` excluyen a LLA de
  toda elección anterior a 2021-01 (`tests/test_eras_argentina.py::
  test_lla_does_not_exist_before_its_founding`).

### 4. Test 3 del ADR (§6 punto 3): `xfail(strict=True)`, con el número medido

Este es el hallazgo más importante de esta pasada. Midiendo la corrida real 2019-12 → 2023-12 (con
`pack.era.actors`/`pack.era.loyalty_table`/`macro_coefficients` del paquete, igual que
`tests/test_macro_regime.py`), **LLA gana 0 de 20 semillas tanto con aprobación=confianza=55
(neutral) como con aprobación=confianza=25/30 (mal, el caso del ADR) — y hasta con
aprobación=confianza=10 (extremo, probado aparte, 0/30)**. La condición "< 5 % con aprobación 55" se
cumple trivialmente; la condición "≥ 30 % con aprobación/confianza bajas" NO se cumple, así que
`test_lla_wins_more_often_under_sustained_distrust` queda en `xfail(strict=True)`. Dos causas
distintas, ambas medidas:

1. **Con `macro_coefficients` activo (`features.macro_regime: true`, el default de Argentina — el
   mismo que usa el comando de ejemplo del README/CLI), la corrida real de 2019-12 entra en
   `hyperinflation` alrededor del mes 13 en el 100 % de las semillas probadas (30/30), mucho antes
   del mes 48 en que ocurriría la elección**: no hay elección que ganar. Esto coincide con el
   hallazgo ya registrado en `EMERGENCE_LOG` ("elección 2023 desde el estado real de 2019-12 ...
   inflación 4–7× subestimada") — es un problema de calibración de `world/economy.py`
   (`step_macro_economy`, ADR 012), no de ADR 013, y la tarea prohíbe tocar `economy.py`.
2. **Sin `macro_coefficients` (para poder medir el mecanismo de ADR 013 aislado de (1)), la elección
   sí ocurre (8–18 de 20 semillas según la semilla de aprobación/confianza), y el término
   `outsider_bonus` SÍ mueve el voto de forma sustancial**: en una corrida de ejemplo (semilla 1,
   aprobación=confianza=20), LLA saca 37.2 % en primera vuelta (contra 39.5 % de fpv_fdt_pj, sin
   ganador directo) — pero pierde el balotaje. La razón, verificada leyendo
   `world/elections.py::resolve_presidential`: el balotaje reparte los votos de los partidos que NO
   llegaron a la segunda vuelta por cercanía ideológica en el eje `economic` (`TAU_RUNOFF = 0.5`).
   LLA (`economic: 0.95`) ya absorbió casi todo el electorado de `cambiemos_jxc` (`economic: 0.6`,
   mismo signo) en la primera vuelta vía `outsider_bonus` — a `cambiemos_jxc` le queda casi nada de
   voto propio para transferirle en el balotaje — mientras que el bloque moderado
   `uca_otros_2015` (`economic: 0.0`, ~18–24 % del padrón) está ideológicamente más cerca del
   finalista de centroizquierda que del outsider de derecha extrema, así que ese bloque transfiere
   mayoritariamente al rival de LLA. El mecanismo de §5 (el voto de primera vuelta responde al
   descontento/desconfianza) funciona tal como está escrito; lo que falta para que LLA pueda ganar en
   ≥ 30 % de las semillas es o bien un `outsider_bonus`/`personalism` mayor (fuera del rango
   calibrado por este ADR, que fija el default en 0.3), o una regla de balotaje que no castigue tanto
   a un outsider que ya "canibalizó" a su competidor más cercano en primera vuelta — ninguna de las
   dos se tocó en esta pasada (serían cambios de calibración/mecanismo de `world/elections.py` más
   allá del alcance de completar ADR 013 con los defaults ya literales del ADR).

Pendiente para quien retome esto: recalibrar `outsider_bonus`/`TAU_RUNOFF` específicamente contra el
resultado real de 2023 (LLA ganó el balotaje con 55.7 %) sería el próximo paso natural, pero requiere
decidir si se toca `TAU_RUNOFF` (un coeficiente de Aurora, ADR 006, no de este ADR) o si el remedio
vive enteramente del lado de `outsider_bonus`/`personalism` de LLA.

### 5. Test 4 (§6 punto 4, cambio de época) y test 5 (golden)

Ambos cumplen sin `xfail`. El test 4 usa una corrida 2011-12 → 2019-12 (96 meses, `initial_state_override`
con el estado real de 1998-01 — 2011-12 no es una de las 8 fechas hito de `initial_states`, ver el
docstring del test para por qué eso no compromete lo que se está probando): la elección del mes 48
trae `era_change: "2015-2023"` tanto en el `ElectionResult` en memoria como en el JSONL, y el
universo de partidos de esa elección ya es el de 2015-2023 (`cambiemos_jxc`/`fpv_fdt_pj`/`fit_u`/
`uca_otros_2015`), no el de 2003-2015. El test 5 delega en
`tests/test_country_pack_argentina.py::test_aurora_without_country_matches_golden_hash_pre_a2` (se
corrió aparte, `-k golden`, después de cada cambio a `cli.py`/`elections.py`/`countries.py` de esta
pasada, como pide la tarea) — sigue pasando.

### 6. Pendiente

- El punto 1 del `xfail` de la sección 4 (colapso por hiperinflación antes de la elección de 2023
  bajo `macro_coefficients`) es un problema de calibración de ADR 012, fuera del alcance de esta
  tarea (no se tocó `economy.py`). Bloquea medir el mecanismo de LLA en las condiciones EXACTAS que
  pide ADR 013 §6 punto 3 (corrida completa con `macro_coefficients`, que es lo que usa
  `republica run --country argentina --start 2019-12` por default).
- El punto 2 (balotaje penaliza al outsider que ya canibalizó a su competidor más cercano) necesitaría
  una decisión explícita sobre si se recalibra `outsider_bonus`/`personalism` de LLA o `TAU_RUNOFF`
  de Aurora — no se decidió en esta pasada, se dejó documentado con el mecanismo exacto y un ejemplo
  numérico.
- `seats_share` de `politics/parties/*.json` (bancas reales de Diputados) sigue en `confidence: low`
  para los 33 partidos de las 3 épocas (heredado, ya en `politics/PENDING_FACTCHECK.md` antes de este
  WIP) — no se descargó una fuente primaria de composición histórica del Congreso en este entorno.
