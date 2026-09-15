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
