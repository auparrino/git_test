# Log de calibración — Fase 1 (v0.1)

Registro de todo ajuste hecho a `data/country.json` para cumplir el test de
aceptación 7 (distribución de outcomes: `survived` entre 50 % y 95 % en 1000
semillas con `ConstantPolicy`) y la cota de sensatez de la inflación anualizada
mediana al mes 48 (entre 5 % y 400 %). Ningún cambio tocó las fórmulas de
`world/economy.py`, `world/society.py` ni `world/politics.py`: solo valores en
`data/country.json → coefficients`.

## Diagnóstico inicial

Con los coeficientes tal cual salen de la sección 4/5 del spec, `republica
batch --seeds 300` daba:

```
survived: 16/300 (5.3 %)
hyperinflation: 284/300 (94.7 %)
mediana inflación anualizada final: ~3700 %
```

Incluso **sin shocks y sin ruido exógeno** (`shocks_enabled=False,
exogenous_noise=False`), la corrida determinista con `ConstantPolicy` diverge
a hiperinflación alrededor del mes 30-35. La causa es estructural, no un bug:
con `interest_rate` fijo en 30 (política "no hacer nada") y
`r_real = interest_rate − 12·inflation`, apenas la inflación mensual supera
`(30 − r_neutral) / 12 ≈ 2.17`, la tasa real se vuelve negativa y sigue
cayendo a medida que sube la inflación (porque la tasa nominal no reacciona).
Eso alimenta dos lazos de realimentación positiva simultáneos:

1. `r_gap` más negativo → `de_raw` sube (sección 4.2, término `−b_r·r_gap/100`)
   → `exchange_rate` se deprecia → `inflation' += c_e·de` (pass-through).
2. El mismo `r_gap` más negativo entra directo en 4.3 como `−c_r·r_gap/100`,
   que se vuelve positivo y empuja la inflación aún más.

Con la inflación inicial (2.0) ya muy cerca del punto de quiebre (2.17), el
sistema es un punto fijo casi neutro que en la práctica es repulsor: cualquier
mes con inflación por encima de 2.17 entra en la espiral. El test de estado
estacionario (sección 11, test 3) solo mira el mes 1 con tolerancia ±0.15, así
que hay margen para bajar la ganancia del lazo sin romperlo.

## Cambio aplicado

**`c_e` (pass-through cambiario, sección 4.3): `0.10 → 0.06`.**

Es exactamente uno de los "supuestos discutibles" que el spec (sección 12)
marca como candidato a calibrar ("Pass-through cambiario 0.10 por pp. Alto
para una economía cerrada, razonable para una bimonetaria."). Bajarlo reduce
la ganancia del lazo 1 de arriba sin tocar el lazo 2 (que depende de `c_r`,
no marcado como knob de calibración en la sección 12) ni ninguna fórmula.

No se tocó `c_f` (monetización del déficit) ni ningún otro coeficiente: un
solo cambio bastó para entrar en el rango pedido.

### Resultado (300 semillas, `ConstantPolicy`, seed 0..299)

```
survived: 239/300 (79.7 %)
hyperinflation: 61/300 (20.3 %)
mediana inflación anualizada final (mes 48): 31.1 %
p10 / p50 / p90 inflación anualizada: 16.9 % / 31.1 % / 1620.7 %
```

- `survived` = 79.7 % ∈ [50 %, 95 %]. ✓
- Mediana de inflación anualizada 31.1 % ∈ [5 %, 400 %] (y cerca del ~27 %
  anual que corresponde al régimen inicial de 2.0 %/mes, así que el "mundo
  tranquilo" sigue leyendo como una inflación alta pero no absurda). ✓
- Con `ConstantPolicy` ("no hacer nada") 1 de cada 5 gobiernos igual termina
  en hiperinflación en 48 meses: el mensaje del juego (la política monetaria
  pasiva es riesgosa) se mantiene.

### Verificación de que no rompió el resto de los tests de aceptación

Re-corridos con `c_e = 0.06` antes de fijar el valor:

- Test 3 (estado estacionario, semilla 1, sin shocks/ruido): `inflation'
  = 1.902` → `|1.902 − 2.0| = 0.098 < 0.15`. ✓ (con `c_e = 0.10` daba 1.981;
  el cambio no rompe la tolerancia).
- Test 4 (sequía, semilla 7, `drought@5`): reservas menores en meses 6-9 y
  aprobación menor en al menos uno de esos meses. ✓ (sin cambios, no depende
  de `c_e` de forma crítica).
- Test 5 (suba de tasa +15pp mes 1, semilla 42, sin shocks): inflación mes 12
  menor y desempleo mes 12 mayor que la corrida constante. ✓
- Test 6 (déficit, `primary_spending=32`, semilla 11, sin shocks): la corrida
  con déficit alto ahora entra en hiperinflación antes del mes 24 (mes 15),
  lo cual es una confirmación *más fuerte* que la pedida por el spec (una
  diferencia de ≥15pp de inflación anualizada al mes 24) — ver nota de
  desviación en el reporte final sobre cómo se adaptó el test para este caso.

## Knobs considerados y descartados

Antes de fijar `c_e = 0.06` se barrieron combinaciones de `c_e` y `c_f`
(script exploratorio, no versionado) sobre 120-300 semillas:

| c_e | c_f | survived | mediana infl. anualizada |
|---|---|---|---|
| 0.10 | 0.12 (default) | 5.3 % | ~3700 % |
| 0.06 | 0.09 | 98.0 % | −11.0 % (deflación: descartado, < 5 %) |
| 0.06 | 0.10 | 94.5 % | 8.2 % |
| 0.06 | 0.11 | 89.5 % | 20.7 % |
| **0.06** | **0.12 (sin tocar)** | **82.0 % (n=200) / 79.7 % (n=300)** | **31.3 % / 31.1 %** |
| 0.07 | 0.12 | 67.5 % | 43.1 % |
| 0.08 | 0.12 | 47.5 % | 1973.6 % (fuera de rango: descartado) |

Se eligió `c_e = 0.06` con `c_f` en su valor default (`0.12`, el de la
sección 4.3 del spec) por ser el cambio de un solo coeficiente que cae más
cómodo dentro de ambos rangos pedidos, sin necesidad de tocar dos knobs a la
vez.


## Segunda ronda (revisión de diseño, orquestador)

Al leer la trayectoria determinista de `ConstantPolicy` (sin shocks ni ruido) aparecieron dos
incoherencias de diseño de la spec, no de la implementación:

1. **El salario real caía 10 % en 48 meses con la inflación bajando.** Causa: `w_idx = 0.8` hace que
   los salarios pierdan el 20 % de la inflación *todos* los meses, sin importar si acelera o no.
   Cambio: `w_idx 0.8 → 1.0` (indexación completa con rezago). Ahora el salario real solo se erosiona
   con aceleración inflacionaria.
2. **Con la tasa nominal fija en 30 % y la inflación cayendo a 1 % mensual, la tasa real subía a 18 %**,
   hundía el crecimiento (desempleo 10.7 %) e inflaba las reservas por carry a USD 27.000–41.000 M.
   Cambios: `k_k 40 → 15`, `k_conf 15 → 10` (reservas ahora drenan ~20 M/mes en estado inicial), y
   saturación del efecto de la tasa real sobre la actividad: `clamp(r_gap, −10, +30)` (nuevos
   coeficientes `r_gap_min`, `r_gap_max`). La saturación inferior evita que tasas reales de −100 %
   en corridas hiperinflacionarias "estimulen" la economía hasta un desempleo del 2 %.
3. **Nuevo baseline `PassivePolicy`** (tasa = `r_neutral + 2 + 12·inflation_lag1`): "no hacer nada"
   en términos reales. Es el default de `run` y `batch`. `ConstantPolicy` sigue existiendo como lo
   que hace un jugador que no toca la tasa.

Resultado (300 semillas):

| Política | survived | hyperinflation | collapse | inflación anual final p50 | desempleo final p50 |
|---|---|---|---|---|---|
| passive | 91.7 % | 0 | 8.3 % | 32 % | 8.5 % |
| constant | 83.7 % | 14.0 % | 2.3 % | 35 % | 9.1 % |
| taylor | 100 % | 0 | 0 | — | 11.5 % |

Trayectoria determinista con `passive` (sin shocks): inflación 2.0 → 1.6 mensual, crecimiento 2.3 %,
desempleo 8.0, salario real 104, aprobación 50 → 56. Aburrido y estable, como pide la DoD.

Queda documentada una **trampa de inflación crónica**: en ~19 % de las corridas `passive`, una
secuencia de shocks agota las reservas, hunde la confianza institucional y deja la inflación en
5–14 % mensual con aprobación en 0 sin llegar al umbral de hiperinflación. Es un estado coherente
(el BC pasivo no desinfla) y es el que el jugador tiene que evitar o revertir con Taylor y ajuste.

## Tercera ronda (tras la primera partida automática de Fase 2)

`play --auto` (siempre la opción A: ajuste fiscal, retenciones, tasa nominal fija en 30) terminaba
con deflación de −2 % mensual, desempleo 17 % y **aprobación 78**. Incoherente. Causa: §5.6 premiaba
linealmente la inflación por debajo de 2 % (`−e_pi·(π − 2)` con π = −2 da +3.2 puntos por mes), lo que
tapaba el castigo por desempleo.

Cambios:
1. **Aprobación (forma de fórmula):** castigo `−e_pi·pos(π − 2)` y premio acotado
   `+e_pi_low·(2 − clamp(π, 0, 2))` con `e_pi_low = 0.3`. Bajar la inflación de 2 a 0 vale +0.6/mes;
   la deflación no suma nada.
2. **Carry de reservas saturado:** `k_k · clamp(r_gap, −10, 30)` (antes sin saturar: con tasa real
   de 54 % entraban USD 750 M/mes).
3. **Piso de inflación mensual:** −1.0 (antes −2.0). Deflaciones del 22 % anual sostenidas no son
   un estado que queramos representar en v0.1.

## Cuarta ronda (elecciones, ADR 006 secc. 2 — post-Fase 6)

Encargo: `run --seed 7 --policy taylor --months 96` daba, en la primera vuelta del mes 48, un reparto
casi uniforme (FF 19.4 %, UR 21.9 %, PS 20.0 %, ML 15.6 %, AP 23.1 %) y **Alianza Provincial** — un
partido regional de 8 bancas, sin base social propia — terminaba ganando la presidencia. Diagnóstico
completo en `docs/ADR_006_memory_elections.md` § 5.1 (resumen: `τ = 0.35` aplana un softmax cuyas
diferencias de utilidad típicas son de 0.1–0.3, y un partido centrista como AP nunca es la peor opción
de ninguna cohorte en el término ideológico, así que con τ chico igual acumula una porción pareja en
vez de chica). Solo se tocaron datos/parámetros, ninguna forma de fórmula.

### Cambio 1: `TAU_SHARE` (`world/elections.py`)

`0.35 → 0.15` (rango sugerido por el encargo: 0.12–0.2). Sin rescalar las utilidades (la otra opción
que ofrecía el encargo): la escala de `util_c,p` ya está fijada por los pesos literales del ADR
(`v_econ 0.35, v_ideo 0.25, v_appr 0.15, v_loy 0.15, v_reg 0.05, v_camp 0.03, v_evt 0.02`), tocar la
escala habría significado tocarlos a ellos (fuera de alcance: el encargo pide calibrar τ o rescalar
utilidades, y τ es la opción que no toca ningún peso del ADR).

### Cambio 2: `data/cohorts_loyalty.csv` recalibrado

Reemplaza la matriz original (Fase 6, "40 valores inventados... calibrados a mano", casi uniforme,
0.00–0.45) por una con estructura explícita por cohorte, calibrada iterativamente (script de
calibración en el scratchpad de la sesión, no versionado) contra 4 objetivos simultáneos: la línea de
base de la meta 1 (± 5pp), el resultado de `seed=7 --policy taylor` en el mes 48 (el oficialismo, con
aprobación ≈ 29, tiene que perder — pero no contra AP), y los tests de aprobación 65/25 y voto
económico ya existentes. La lealtad **no está acotada a `[0, 1]`**: es un término aditivo de
`util_c,p` (`v_loy · loyalty_c,p`, no una probabilidad), así que se usan valores > 1 (Unión
Republicana en sus cohortes más leales) y negativos (hasta −0.6, Alianza Provincial en toda cohorte
salvo `rural`, su única base regional real vía `data/provinces.csv → governor_party`) — un partido
"sin base social propia" que además es centrista necesita lealtad negativa para no beneficiarse por
default del softmax, 0 no alcanza (ver ADR § 5.1 punto 2).

| cohorte | FF | UR | PS | ML | AP | turnout |
|---|---|---|---|---|---|---|
| urban_workers | +0.65 | +0.13 | +0.13 | +0.02 | −0.60 | 0.65 |
| rural | +0.02 | +0.94 | +0.00 | +0.15 | +0.20 | 0.80 |
| middle_class | −0.03 | +1.08 | +0.00 | +0.35 | −0.60 | 0.85 |
| public_employees | +0.56 | +0.03 | +0.18 | +0.01 | −0.60 | 0.80 |
| young_professionals | +0.00 | +1.03 | +0.00 | +0.35 | −0.60 | 0.60 |
| informal | +0.65 | +0.08 | +0.01 | +0.03 | −0.60 | 0.55 |
| retirees | +0.40 | +0.67 | +0.00 | +0.03 | −0.60 | 0.85 |
| students | +0.40 | +0.06 | +0.16 | +0.03 | −0.60 | 0.50 |

El signo por cohorte respeta el encargo (urban_workers/public_employees → FF/PS; middle_class/
young_professionals → UR/ML; rural → UR/AP; informal → FF; retirees → FF/UR; students → PS/FF); `PS`
queda con lealtad chica o nula fuera de `urban_workers`/`public_employees`/`students` (su base
declarada) — necesario para que su participación nacional no se pase de la meta de 14 % (bancas
iniciales de `data/parties.json`), no porque el encargo lo pidiera explícito para esas cohortes.
`turnout` no se tocó (valores de Fase 6, no forman parte de este encargo).

### Cambio 3: `data/cohort_provinces.csv` (nuevo) + `regional_bonus_c,p` real

Resuelve la nota de implementación #10 de ADR 006 (`regional_bonus_c,p` fijo en 0 por falta de un
mapeo cohorte→provincia). Formato `cohort_id,province_id,weight` (Σ_p peso_c,p = 1 por cohorte, 8
cohortes × 8 provincias). Pesos plausibles por sector/ingreso de cada cohorte y `main_sector`/
`population_k` de `data/provinces.csv`: `rural` concentrada en Norte/Litoral/Pampa (agro, 0.28/0.24/
0.28); `public_employees`/`middle_class` con ~45 % en Capital (administración pública/servicios);
`informal` repartida entre Norte/Costa/Capital (0.30/0.25/0.25); el resto (urban_workers,
young_professionals, retirees, students) con una mezcla más pareja, sesgada a las provincias
industriales/de servicios (Capital/Centro/Litoral) o, para retirees, aproximando la distribución de
población real de `provinces.csv`.

`world/elections.py` gana `province_performance(province_records, national_unemployment) -> {province:
perf}` (calibración, sin ADR que la fije: `perf_p = clamp((income_p − 100)/20 − (unemployment_p −
unemployment_nacional)/5, −1, 1)`, escalas elegidas para que el `u_offset` más extremo de
`provinces.csv` (±4) o un shock de ingreso de ±20 puntos saturen el término a ±1, el mismo rango que
los demás sumandos de `util_c,p` antes de los pesos) y `compute_regional_bonus(cohorts, provinces,
province_records, province_weights, national_unemployment) -> {(cohort, party): bonus}` (`Σ_prov
peso_c,prov · perf_prov` para el partido que gobierna cada provincia, 0 para los demás ahí). Ambos
opcionales en `run_election`/`compute_vote_intention` (`regional_bonus={}` si no se pasan — mismo
comportamiento que antes de este cambio). `v_reg = 0.05` sin tocar.

### Resultado

**Línea de base** (`approval_c = 50`, sin cambio económico en 12 meses, `perceived_inflation = 2`, sin
campaña/eventos recientes — meta 1 del encargo), primera vuelta promediada sobre 50 semillas, contra
las bancas iniciales de `data/parties.json` (38/30/14/10/8):

| partido | promedio (50 semillas) | meta | diff |
|---|---|---|---|
| Frente Federal | 35.71 % | 38 % | −2.29pp |
| Unión Republicana | 29.55 % | 30 % | −0.45pp |
| Partido Social | 16.36 % | 14 % | +2.36pp |
| Movimiento Libertad | 8.19 % | 10 % | −1.81pp |
| Alianza Provincial | 10.20 % | 8 % | +2.20pp |

Las 5 dentro de ±5pp (margen mínimo 2.6pp sobre el borde más cercano).

**Voto económico** (meta 3): salario real +8 % vs −8 % en 12 meses (desempleo sin cambios,
`government_approval = 50`), primera vuelta del oficialismo promediada sobre 50 semillas: 64.31 % vs
10.56 % — diferencia de 53.75pp (meta: ≥ 6pp).

**Bono regional** (meta 4): con un shock de ingreso de +50 puntos concentrado en Norte (gobernada por
Alianza Provincial) y desempleo nacional sin cambios, `regional_bonus[("rural",
"alianza_provincial")] = +0.28`, `regional_bonus[("informal", "alianza_provincial")] = +0.30`; el
voto de AP en `rural` sube de 16.71 % a 18.07 % (intención de voto, antes/después del bono, mismos
demás parámetros).

**`seed=7 --policy taylor --months 96`, mes 48** (meta 6), antes/después:

| | antes (τ=0.35, lealtad Fase 6) | después (τ=0.15, recalibrado) |
|---|---|---|
| FF (primera vuelta) | 19.4 % | 23.8 % |
| UR | 21.9 % | 34.9 % |
| PS | 20.0 % | 19.9 % |
| ML | 15.6 % | 9.0 % |
| AP | 23.1 % | 12.4 % |
| spread (max−min) | 7.7pp | 25.9pp |
| ganador | Alianza Provincial | Unión Republicana |

Aprobación agregada: mes 47 ≈ 32.8, mes 48 (pre-luna de miel) ≈ 28.8 — cayendo sostenidamente desde 50
en los últimos meses del mandato (no un dato que cambie con esta calibración: `government_approval`
sale de `world/cohorts.py::step_cohorts`, ajeno a `world/elections.py`). No hay balotaje al 45 %/40 %+
10pp en primera vuelta (UR 34.9 % vs FF 23.8 %, margen 11.1pp pero UR no llega a 40 %): balotaje
UR/FF, con transferencia ideológica de PS/AP (ambos más cerca de FF en el eje económico) y ML (más
cerca de UR) — UR 50.72 % vs FF 49.28 %. El oficialismo pierde, consistente con la aprobación baja,
pero contra Unión Republicana, no contra Alianza Provincial (que queda tercera, 12.4 %). Bancas:
FF 24, UR 35, PS 20, ML 9, AP 12 (suma 100).

**Mes 96** (segundo mandato, para completar el reporte): primera vuelta FF 43.38 %, UR 5.80 %,
PS 19.53 %, ML 16.01 %, AP 15.28 % — Frente Federal gana en primera vuelta (> 40 % y > 10pp de
margen sobre Partido Social), sin balotaje; Unión Republicana (el oficialismo de este segundo mandato)
se desploma tras un mandato de aprobación igualmente débil. Bancas: FF 44, UR 5, PS 20, ML 16, AP 15
(suma 100).

### Tests agregados (`tests/test_memory_elections.py`)

- `test_baseline_reproduces_initial_party_system` (meta 1).
- `test_economic_vote_moves_incumbent_share_at_least_6pp` (meta 3).
- `test_regional_bonus_favors_governing_party_in_its_province` (meta 4).
- `test_seed7_taylor_month48_no_longer_near_uniform_and_incumbent_loses` (meta 6: spread > 10pp,
  aprobación mes 47 < 40, pierde el oficialismo, no gana Alianza Provincial, bancas suman 100).
- La meta 2 (aprobación 65/25) y la meta 5 (balotaje + D'Hondt suma 100) ya tenían test desde Fase 6
  (`test_high_approval_reelects_and_low_approval_defeats_in_at_least_90pct`,
  `test_runoff_triggers_with_three_parties_and_is_deterministic`,
  `test_dhondt_seats_always_sum_to_total_and_respects_threshold`) — siguen pasando sin cambios
  (100 %/0 % de 100 semillas a aprobación 65/25 respectivamente, incluso más nítido que el ≥90 %/≤10 %
  que pide el ADR).

### Pendiente (detectado en la cuarta ronda)
El voto económico está sobre-sensible: ±8 % de salario real en 12 meses mueve la primera vuelta
del oficialismo de 10.6 % a 64.3 % (53 pp). Un rango razonable sería 15–25 pp. Causa: `tanh(Δ·s_w/10)`
con `τ = 0.15` amplifica mucho; bajar `v_econ` de 0.35 a ~0.2 o dividir por 20 en el `tanh`.
Hacerlo junto con la calibración de la regla de audiencia de medios, sin romper los tests de
aprobación 65/25.

## Quinta ronda (regla de audiencia de medios + sensibilidad del voto económico)

Encargo de calibración con dos objetivos (B1, B2) más una re-corrida de los dos experimentos
canónicos que usan `features.media`/`features.elections` (B3). Los tres tocan solo datos/parámetros
(`world/perception.py::FRAME_BIAS`/audiencia/reputación, `world/elections.py::ECON_VOTE_DIVISOR`) y
la ventana de contradicción vive en `engine/simulation.py` (wiring, no fórmula nueva de `world/`);
ninguna fórmula de `world/economy.py`/`world/society.py`/`world/politics.py` se tocó.

### B1: regla de audiencia de medios (ADR 005 §4.5, revisado v0.8)

**Diagnóstico** (fila "convergencia de medios" de `docs/EMERGENCE_LOG.md`): con `seed=7 --policy
taylor --months 48`, los tres medios convergían a `influence.public = 0.6` (el techo) y al frame
`crisis`, con `perception_gap` uniforme entre las 8 cohortes. Causa estructural, no un bug puntual:
`audience_alignment` pesaba las 8 cohortes por igual (no por si consumían ese medio o no) y, con
`PUBLISH_STORY.target_bloc = "all"`, el sesgo de `compute_bias` se reparte por `consumption[c][m]`
que suma 1 por cohorte — si los tres medios tienen el MISMO `(frame, influence)` en un mes, el sesgo
resultante es matemáticamente idéntico para las 8 cohortes sin importar la matriz de consumo
(`Σ_m consumption[c][m] · K = K`). Una vez que los tres convergen, se quedan pegados: con
`AUDIENCE_MAX` como techo compartido y alineación perfecta sostenida, los tres terminan clampeados al
mismo valor exacto.

**Cambios** (`world/perception.py`, wiring en `engine/simulation.py`):

1. **Alineación por audiencia PROPIA** (`outlet_audience_weights`/`audience_alignment`/
   `drift_audience`, todas con un `outlet_id`/`consumption` nuevo): cada medio se mide contra sus
   propias cohortes consumidoras (`pop_share_c · consumption[c][outlet]`, normalizado), no contra las
   8 por igual.
2. **`FRAME_BIAS` acotado y asimétrico** (tabla completa y derivación en ADR 005 §4.3 revisado v0.8):
   `crisis` escalado a ~0.2× el original (`+0.30`/`+0.40` en vez de `+1.5`/`+2.0`) y `recovery` a
   ~0.55–0.65× (`−0.52`/`−0.55` en vez de `−0.8`/`−1.0`) — asimétrico a propósito: `crisis` domina la
   mayoría de los meses de la corrida de referencia, así que escalarlo chico alcanza para bajar la
   brecha promedio; dejar `recovery` más fuerte (cerca de su propia cota de 4 pp anualizadas) es lo
   que le da a un medio margen para quedarse fuera de "crisis" una fracción sustancial de los meses
   cuando la economía realmente mejora. Verificado empíricamente (script de calibración en el
   scratchpad de la sesión, no versionado) que un escalado simétrico de `crisis`/`recovery` NO puede
   cumplir los dos objetivos de abajo (brecha promedio Y ≥30 % de meses no-crisis) a la vez, para
   ningún factor único.
3. **Costo de reputación con ventana de tendencia** (`frame_contradicts_reality`/
   `update_contradiction_streak`/`reputation_penalty`, nuevas en `world/perception.py`;
   `outlet_reputation_debt` nuevo en `Simulation`): `crisis` con `gdp_growth > 2` e inflación cayendo,
   o `recovery` con desempleo subiendo e inflación acelerando, sostenido 3+ meses SEGUIDOS, cuesta
   `−0.03/mes` mientras persiste. El "cayendo"/"subiendo"/"acelerando" se mide contra el valor de hace
   `TREND_WINDOW_MONTHS = 4` meses (no el mes inmediato anterior): con `exogenous_noise=True` el delta
   mes a mes cambia de signo constantemente y casi nunca sostiene una racha real de 3+ meses; una
   ventana más ancha (y el crecimiento promediado sobre la misma ventana) sigue el criterio literal
   del encargo pero filtra ese ruido. La deuda de reputación es ACUMULATIVA (nunca se perdona): un
   medio que sostuvo un frame contradictorio no vuelve a `AUDIENCE_MAX` aunque después se alinee
   siempre con la realidad — sin este piso permanente, la deriva normal de audiencia (punto 1)
   reconverge al techo compartido en pocos meses de alineación y borra cualquier diferencia entre
   medios (el mismo problema de convergencia, solo retrasado).

**Resultado** (`seed=7 --policy taylor --months 48`, antes/después):

| métrica | antes | después | objetivo |
|---|---|---|---|
| `influence.public` final (3 medios) | 0.60 / 0.60 / 0.60 | 0.45 / 0.57 / 0.57 | spread ≥ 0.1 |
| spread (max−min) | 0.00 | 0.12 | ≥ 0.1 |
| `perception_gap` promedio (48 meses) | 0.76 pp/mes | 0.11 pp/mes | en [0.1, 0.6] |
| varianza entre cohortes de `perceived_inflation_c` (máx. de los 48 meses) | 0.0 (exacto, todos los meses) | 0.00296 (mes con más dispersión; no-cero) | no-cero |
| meses en frame ≠ `crisis`, `media_mercado` | 2/48 (4.2 %) | 2/48 (4.2 %) | — |
| meses en frame ≠ `crisis`, `media_nacional` | 8/48 (16.7 %) | 8/48 (16.7 %) | — |
| meses en frame ≠ `crisis`, `media_popular` | 8/48 (16.7 %) | **15/48 (31.3 %)** | ≥ 1 medio ≥ 30 % |

Las 4 metas del encargo B1 se cumplen con margen. Tests nuevos en
`tests/test_cohorts_perception.py` (sección 10): `test_seed7_taylor_outlets_reach_distinct_final_influence`,
`test_seed7_taylor_at_least_one_outlet_mostly_non_crisis`,
`test_seed7_taylor_perception_gap_in_target_band_with_cohort_variance`, más
`test_audience_alignment_weighs_by_outlets_own_audience_not_total_population` (unitario del cambio 1).

**Golden hashes recalculados** (legítimamente afectados: `cohorts_enabled=True, media_enabled=True`
cambia el JSONL byte a byte aunque el invariante que guarda cada test no sea sobre medios):

- `tests/test_memory_elections.py::GOLDEN_SEED7_SHA256`/`GOLDEN_SEED42_TAYLOR_SHA256`
  (`test_features_off_matches_pre_adr006_golden_hash`, `memory`/`elections` apagados pero
  `cohorts`/`media` prendidos).
- `tests/test_evals_governance.py::GOLDEN_SEED7_TAYLOR_SHA256`/`GOLDEN_SEED42_TAYLOR_SHA256`
  (`test_default_governance_matches_pre_adr007_golden_hash`, mismo motivo).
- Los golden hash de `features.cohorts=False`/`features.media=False` (p.ej.
  `tests/test_cohorts_perception.py::GOLDEN_SEED7_TAYLOR_COHORTS_MEDIA_OFF_SHA256`) **no cambiaron**
  (verificado: siguen en verde) — no dependen de `world/perception.py`.

**Efecto de segundo orden sobre `seed=7`/elecciones** (documentado, no un objetivo de B1): con menos
sesgo negativo acumulado de los medios, la aprobación del mes 47 en la corrida con actores + memoria +
elecciones activas queda más alta que antes (~42.9 en vez de <40), y el oficialismo de `seed=7` ya NO
pierde la reelección en el mes 48 (antes sí, Cuarta ronda meta 6). Esto rompía 3 tests que asumían esa
derrota como dato de la semilla:

- `tests/test_memory_elections.py::test_seed7_taylor_month48_no_longer_near_uniform_and_incumbent_loses`
  → renombrado a `test_seed7_taylor_month48_no_longer_near_uniform`, assertions ajustadas a lo que
  sigue siendo cierto (spread > 10pp, D'Hondt suma 100, no gana Alianza Provincial) y a los números
  nuevos (aprobación mes 47 < 50, no < 40).
- `tests/test_memory_elections.py::test_transition_after_defeat_changes_president_keeps_memories_clears_agreements`
  y `test_parties_by_id_refreshed_on_every_decision_actor_after_transition` → cambiados a `seed=0`
  (verificado: 29 de 30 semillas 0–29 siguen dando derrota bajo el código recalibrado; el resto de
  cada test, memorias/`parties_by_id`, no depende de la semilla en sí, solo de que HAYA una derrota).

### B2: sensibilidad del voto económico (ADR 006 §2.2)

**Diagnóstico** (pendiente de la cuarta ronda): ±8 % de salario real en 12 meses movía la primera
vuelta del oficialismo 53.75 pp (10.56 % → 64.31 %), muy por encima del rango pedido (15–25 pp).

**Cambio**: nuevo `ECON_VOTE_DIVISOR` (`world/elections.py::econ_vote`, antes `10.0` literal del ADR)
subido a `42.0` — mismo `tanh`, solo hace falta un delta de salario real más grande para acercarse a
la saturación. `v_econ` (`WEIGHTS`), `TAU_SHARE` y `data/cohorts_loyalty.csv` **sin tocar**: no hizo
falta re-tunearlos porque las metas 1 (línea de base) y 2 (aprobación 65/25) del encargo original usan
escenarios con `delta_real_wage_pct_12m = 0`, donde `econ_vote_c = tanh(0) = 0` — el divisor no les
pega en absoluto (verificado, ver tabla). Barrido empírico (script de calibración en el scratchpad de
la sesión, no versionado) sobre 50 semillas por punto de `ECON_VOTE_DIVISOR ∈ {18, 22, 26, 30, 35, 40,
41, 42, 43, 44, 45, 50, 60}`; `42` cae cerca del centro del rango pedido con margen a los dos lados.

**Resultado** (primera vuelta del oficialismo, ±8 % salario real/12 meses, 50 semillas, promedio):

| | antes (`/10`) | después (`/42`) | objetivo |
|---|---|---|---|
| +8 % salario real | 64.31 % | 46.05 % | — |
| −8 % salario real | 10.56 % | 25.70 % | — |
| diferencia | 53.75 pp | **20.36 pp** | 15–25 pp |

Tests: `tests/test_memory_elections.py::test_economic_vote_moves_incumbent_share_in_15_to_25pp_band`
(reemplaza `test_economic_vote_moves_incumbent_share_at_least_6pp`, mismo escenario, banda 15–25pp en
vez de piso ≥6pp). `test_high_approval_reelects_and_low_approval_defeats_in_at_least_90pct` y
`test_baseline_reproduces_initial_party_system` siguen en verde SIN CAMBIOS (100 %/0 % de 100 semillas
y las 5 bancas dentro de ±5pp respectivamente — idénticos a la Cuarta ronda, como predice el análisis
de arriba).

### B3: re-corrida de los experimentos canónicos

`uv run republica experiment run <yaml> --workers 4 --out experiments/results/<name>` +
`... report <dir>` para `central_bank_independence` (50 semillas/brazo, 2 brazos) y `fiscal_rule` (20
semillas/brazo, 9 brazos) — los dos con `cohorts`/`media`/`memory`/`elections` prendidos, así que los
dos quedan afectados por B1/B2. `report.md`, `metrics.csv` y `plots/*.png` sobreescritos (JSONLs
gitignored, no se versionan).

**`central_bank_independence`**: la hipótesis registrada (independiente = menor inflación mediana
final, mayor desempleo final, sin diferencia clara de supervivencia) **sigue confirmada**: inflación
anualizada final mediana 38.86 (dependiente) vs 23.48 (independiente) — Cliff's δ = −0.50 (antes:
40.27 vs 22.06, δ = −0.53); desempleo final 8.85 vs 10.96 — δ = +0.76 (antes: 8.82 vs 11.08, δ =
+0.78). `perception_gap_mean` baja fuerte en los dos brazos (0.65→0.09 dependiente, 0.80→0.16
independiente) — consistente con B1 (brecha de percepción objetivo mucho más chica). La distribución
de `outcomes` cambia bastante en magnitud (dependiente: `reelected` pasa de 6/50 a 25/50; independiente:
de 3/50 a 23/50) porque `government_approval` — una variable REAL, no solo perceptual — depende en
parte de `consumer_confidence`, que a su vez lee `perceived_inflation_agg`: con menos sesgo negativo de
medios, la aprobación agregada en ambos brazos queda más alta en promedio, y eso se refleja en más
reelecciones. **No cambia la conclusión cualitativa de la hipótesis** (la comparación ENTRE brazos es
la misma), solo el nivel absoluto de `outcomes`/`approval_final` en ambos brazos por igual.

**`fiscal_rule`**: la hipótesis (supervivencia cae e inflación sube con `c_f`/`primary_spending`
crecientes, peor cuadrante en `c_f=0.16 × primary_spending=27`, mejor en `c_f=0.08 × 
primary_spending=23`) **sigue confirmada**, mapa de calor de supervivencia IDÉNTICO (100/100/45,
100/95/5, 100/80/0 — los outcomes de hiperinflación/colapso son variables reales, no tocadas por
medios de forma directa). Las medianas de `inflation_annual_final`/`gdp_growth_mean` cambian por
fracciones de punto en varias celdas (p.ej. `c_f=0.16 × primary_spending=25`: 216.96 → 212.36;
`c_f=0.08 × primary_spending=27`: 1017.68 → 1037.48) — el mismo mecanismo indirecto que en
`central_bank_independence` (`government_approval` real, afectado por `consumer_confidence` ←
`perceived_inflation_agg`, retroalimenta congreso/actores/protestas dentro de la corrida). Diferencias
menores al 2 % en casi todas las celdas, sin cambiar el orden relativo de ningún cuadrante del mapa de
calor. **Veredicto: sin cambio en la conclusión cualitativa de ninguno de los dos experimentos.**

## Argentina A5 (ADR 012): recalibración con la estructura macro (2026-09-15)

Contexto: A4 (`data/countries/argentina/validation/a4_main/report.md`) dio negativo en las tres
hipótesis registradas, con diagnóstico mecánico (ecuación de precios contractiva, `--fx-regime peg`
inerte, reservas sin ancla de balance de pagos, calendario de shocks incompleto, ventana de
calibración reversiva). ADR 012 (implementado en una ronda previa, ver
`docs/ADR_012_argentine_macro.md`) corrigió los cuatro mecanismos DETRÁS de un flag
(`features.macro_regime`, ya prendido en `data/countries/argentina/country.json`); esta ronda (A5)
recalibra y revalida con esa estructura nueva.

### Qué cambió respecto de A3/A4

1. **Calendario de shocks completado** (`data/countries/argentina/politics/shocks_calendar.csv`,
   20 → 28 filas): crisis rusa/devaluación brasileña 1998–99, corralito (dic-2001), default
   soberano (dic-2001), salida de la convertibilidad (ene-2002), sequía de la campaña 2017/2018,
   Plan Austral (jun-1985), devaluaciones de 1981 (Sigaut) y crisis de balanza de pagos de 1962.
   Todas `source: general_knowledge`, `reviewed_by: pending`, documentadas en
   `data/countries/argentina/politics/PENDING_FACTCHECK.md` §2.7. El cepo de 2011 NO se agregó
   como shock: ya está modelado como `fx_regime = control` en `fx_regimes.csv` (deliverable 5 del
   ADR 012), no como un evento puntual.
2. **Espacio de calibración extendido** (`src/republica/calibration/parameters.py`): nuevo grupo
   `"macro"` (58 de los 60 campos de `MacroCoefficients` — se excluyen los dos enteros de duración
   institucional, `banking_crisis_months`/`ic_crisis_free_months`). Rango default `[v/3, 3v]` salvo
   siete con razón física documentada (`w_adapt∈[0,1]`, `rho_pi∈[0.5,1.0]`, `rho_slope∈[0,0.3]`,
   `rm∈[1,6]`, y tres probabilidades acotadas a `[0,1]`: `default_risk_threshold`,
   `peg_default_risk_ceiling`, `exit_banking_crisis_p`). El bloque bimonetario viejo (`BIMONETARY_TUNABLE`,
   10 coeficientes) se EXCLUYE del vector cuando se calibra con macro: `engine/simulation.py::run`
   desactiva ese canal en cuanto hay `macro_coefficients` (Notas de implementación del ADR 012), así
   que tunearlo gastaría presupuesto de CMA-ES en dimensiones sin ningún efecto. Vector final: 97
   (económicos) + 58 (macro) = **155 parámetros** (vs. 107 de `a3_main`).
3. **Ventana y pérdida nuevas** (ADR 012 §6): train `1992-01:2023-12` (incluye 2001 y 2018–2023,
   en vez del `1993-01:2015-12` reversivo de A3), holdout `1983-12:1991-12` (hiperinflación y
   convertibilidad temprana — NOTAR que el holdout es CRONOLÓGICAMENTE ANTERIOR al train, a
   propósito: es la parte de la historia que esta estructura de precios/régimen nunca vio). Meses de
   arranque anteriores a 1997 (`inflation_cpi_monthly.csv` arranca en 1997-02; antes se interpola de
   la serie anual) pesan 0.5 en el objetivo
   (`calibration/objective.py::start_month_weight`/`PRE_1997_WEIGHT`). Pérdida con cola pesada
   (`--loss heavy`): error normalizado (por el desvío de la serie real) elevado a 1.5 y agregado SIN
   volver a tomar raíz — ver el docstring de `HEAVY_TAIL_POWER` en el código para la cuenta de por
   qué la raíz final (que convertiría esto en una norma L1.5, MENOS sensible a un outlier que la
   RMSE) haría lo contrario de lo que pide el ADR ("que los episodios extremos pesen"). El reporte
   de la corrida muestra SIEMPRE las dos métricas (`rmse` y `heavy`), sin importar cuál optimizó
   CMA-ES.
4. **Hallazgo previo a la corrida (agente de ADR 013, verificado acá)**: con los coeficientes macro
   DEFAULT del paquete (sin calibrar) y `--fx-regime auto`, una corrida desde 2019-12 (48 meses,
   20 semillas) entra en `hyperinflation` en **20/20 semillas (100 %)** antes del mes 13 — la
   inflación real de 2020–2023 fue ~2–8 %/mes (picos de 25 % recién en dic-2023). Es el mismo
   mecanismo de hiperinflación espuria que el test 2b del ADR 012 (2003-06 → 0/20, ya cubierto por
   `tests/test_macro_regime.py`), pero disparado desde OTRA fecha con OTRO estado inicial (deuda/
   déficit de 2019 distintos de los de 2003). El train `1992-01:2023-12` de esta ronda SÍ incluye
   2019-12 como uno de los ~124 meses de arranque, así que la pérdida (más aún con `--loss heavy`)
   debería castigarlo. Resultado tras calibrar: ver la sección de resultados de V1/V4 más abajo.

### Identificabilidad rápida sobre sintético

`tests/test_macro_regime.py::test_quick_synthetic_identifiability_recovers_half_of_perturbed_coefficients`
(ADR 012 §7 test 6, ya existente, corrido de nuevo en esta ronda): CMA-ES directo sobre 10
coeficientes macro perturbados ±40 %, 500 evaluaciones — **7/10 recuperados** (≥ 20 % del camino
hacia el valor verdadero), sobre el umbral pedido (≥ 50 % de 10). `calibration/synthetic.py` se
extendió con `IDENTIFIABLE_MACRO_COEFFICIENTS`/`perturb_macro_parameters`/
`generate_synthetic_history_csvs_macro` (mismo patrón que `IDENTIFIABLE_COEFFICIENTS`/
`perturb_parameters` de A3) para que el pipeline de calibración completo (no solo el mecanismo
aislado de `step_macro_economy`) pueda correr el mismo tipo de chequeo; por restricción de cómputo
(los 4 CPUs de la máquina estaban ocupados con la corrida real `a5_macro` durante esta ronda) no se
corrió ese camino completo — queda como infraestructura lista para la próxima ronda, documentado
como simplificación, no como resultado verificado.

### Corrida `a5_macro` — DESCARTADA por un bug del objetivo, no usada para nada

Corrida terminada: 418 evaluaciones (presupuesto 400), 1940.8s de pared (~32.3 min), `--loss heavy`,
stride 3. **Se descarta por un bug encontrado en el propio reporte**, no se usa para calibrar ni
para validar. Queda en disco (`data/countries/argentina/calibration/a5_macro/`) como evidencia.

**Bug (grave): las corridas terminadas antes del horizonte `h` no penalizaban.**
`calibration/objective.py::score_start_month` calculaba `model_target = state_by_h.get(h, {}).get(var)
if h in state_by_h else None` y, si `model_target` era `None` (la corrida terminó por
`hyperinflation`/`collapse` antes de llegar al mes `h`), el término de error se SALTEABA
(`continue`) en vez de penalizarse. El reporte de `a5_macro` lo mostró sin ambigüedad: **"sin dato"
en TODOS los horizontes de 12 meses de la columna calibrado** (inflación, PBI, desempleo, tipo de
cambio, reservas), algo que ninguna otra columna (persistencia/Aurora sin calibrar/`a3_main`)
mostraba — 0 de 124 meses de arranque del brazo calibrado llegaban al mes 12. El optimizador quedó
premiado por hiperinflacionar/colapsar rápido: cuanto antes termina la corrida, menos términos de
error tiene que pagar. Con `--loss heavy` (que además pondera más los errores extremos) el efecto se
agrava: el escalar que minimiza CMA-ES bajó de 26.05 (aurora) a 11.12 en apenas 4 generaciones — una
mejora artificial, no una mejora real del ajuste.

**Fix**: `score_start_month` ahora, cuando la corrida terminó antes de `h`, extrapola (congela) el
último estado disponible y aplica el error normal contra ese valor extrapolado, con un PISO de
`EARLY_TERMINATION_ERROR_FLOOR_SIGMA = 3.0` (3 desvíos de la serie real, unidades normalizadas) —
terminar antes tiene que costar por lo menos tanto como un outlier grande, nunca menos. Se agregó
`MonthScore.ended_before_h`/`aggregate_scores` → `ended_before_h{1,3,6,12}` (fracción de meses de
arranque que terminaron antes de cada horizonte, por brazo) y una tabla nueva en el reporte
("Corridas que terminaron antes del horizonte"). Test de regresión:
`tests/test_calibration_macro.py::test_run_ending_before_horizon_is_penalized_not_skipped` (una
corrida canned que termina en el mes 5 recibe error ≠ 0, piso ≥ 3σ, en h=12) y
`test_floor_early_termination_error_preserves_sign_and_respects_floor` (la función del piso en
aislamiento).

**Segundo bug (holdout sin dato de inflación)**: `RealData.value("inflation", ...)` solo miraba
`inflation_cpi_monthly.csv` (arranca en 1997-02). El holdout completo (`1983-12:1991-12`) cae
ENTERO antes de esa fecha, así que **ningún brazo** (calibrado/persistencia/Aurora/`a3_main`) tenía
un solo dato de inflación en el holdout — la columna quedaba "sin dato" para los cuatro por igual,
sin que eso fuera visible como anomalía (a diferencia del bug de arriba, que SÍ se notaba porque
afectaba solo a un brazo). Fix: `RealData.inflation()` ahora cae a `inflation_cpi_annual_linked.csv`
interpolada linealmente (mismo `interpolate_annual` que ya usa `calibration/initial_states.py::
rule_inflation` para el estado inicial) y convertida a mensual equivalente
(`(1+anual/100)^(1/12)-1`), cuando no hay mes exacto. El `sigma` de normalización de "inflation"
sigue anclado SOLO a la serie mensual real (decisión documentada en el código: mezclar una serie de
bajo ruido con una interpolada mucho más suave correría la escala sin una razón clara).

**Por qué no se detectó en los smoke tests antes de la corrida real**: los tests existentes de A3/A5
(`test_quick_calibration_runs_end_to_end`, `test_cli_calibrate_quick_and_run_with_calibration`) usan
ventanas de 12-24 meses con `--quick` (stride 12, un solo mes de arranque cada uno) — la probabilidad
de que ESE único mes de arranque particular termine antes del horizonte 12 por azar es baja, y el
smoke test no compara métricas train/holdout entre sí (solo verifica que el pipeline corre de punta
a punta), así que un patrón sistemático de "sin dato" en h=12 no saltaba a la vista salvo mirando el
`report.md` de una corrida real con muchos meses de arranque — que es exactamente lo que pasó acá:
se encontró leyendo el reporte de `a5_macro`, no con un test automatizado. Los dos tests nuevos de
arriba sí lo cubren yendo hacia adelante.

### Corrida `a5b_macro` (con los dos fixes)

`republica calibrate --country argentina --train 1992-01:2023-12 --holdout 1983-12:1991-12 --loss
heavy --budget 400 --stride 3 --workers 4 --run-id a5b_macro --seed 42`. **418 evaluaciones, 1912.9s
de pared (~31.9 min, dentro del limite de 45 min pedido)**, mismo hash de datos de entrada que
`a5_macro` (`55596cc...`). Reporte completo: `data/countries/argentina/calibration/a5b_macro/
report.md` (incluye una adenda manual post-corrida con el diagnostico 2019-12 y la lectura honesta
train/holdout).

**Train** (n=124 meses de arranque, 20 con peso 0.5 pre-1997): 0 corridas terminan antes del
horizonte 12 en NINGUN brazo salvo Aurora sin calibrar (4.8 % a h=12) -- el mecanismo funciona: el
calibrado ya no "gana" terminando temprano.

| variable | h | calibrado (rmse / heavy) | persistencia (rmse / heavy) | Aurora sin calibrar (rmse / heavy) | `a3_main` (rmse / heavy) |
|---|---|---|---|---|---|
| inflación mensual | 12 | 0.797 / 0.491 | 0.687 / 0.385 | 4.902 / 8.210 | 0.821 / 0.563 |
| PBI (anualizado) | 12 | 0.982 / 0.819 | 1.404 / 1.258 | 1.214 / 1.099 | 0.965 / 0.792 |
| desempleo | 12 | 0.751 / 0.489 | 0.636 / 0.416 | 1.126 / 0.885 | 0.818 / 0.537 |
| tipo de cambio (log) | 12 | 4.360 / 6.365 | 5.017 / 8.273 | 8.257 / 19.282 | 3.421 / 4.952 |
| reservas | 12 | 0.838 / 0.635 | 0.705 / 0.494 | 1.521 / 1.617 | 0.660 / 0.460 |

**Lectura honesta (train)**: el calibrado queda A LA PAR o LEVEMENTE PEOR que la persistencia en la
mayoría de las filas (inflación, reservas: peor en h=3/6/12; PBI: peor en h=1/3, mejor en h=6/12;
desempleo/tipo de cambio: mejor en la mayoría). 155 parámetros calibrados no superan de forma
consistente al baseline ingenuo de "no cambia nada" dentro de la propia ventana de ajuste. Sí supera
claramente a Aurora sin calibrar y, en inflación/tipo de cambio/reservas a horizontes largos, también
a `a3_main` (que no tiene macro).

**Holdout** (n=29 meses de arranque, TODOS con peso 0.5: 1983-1991 es enteramente pre-1997).
Desempleo/tipo de cambio/reservas: **sin dato** en los 4 brazos (`exchange_rate_official_monthly.csv`
arranca en 1992-01; la única serie anual de tipo de cambio del paquete, `exchange_rate_annual.csv`,
termina en 1951 — no alcanza para el mismo fallback que se implementó para inflación; ver "Pendiente"
más abajo). Único bloque con dato real: inflación y PBI.

| variable | h | calibrado (rmse / heavy) | persistencia (rmse / heavy) | Aurora sin calibrar (rmse / heavy) | `a3_main` (rmse / heavy) |
|---|---|---|---|---|---|
| inflación mensual | 1 | 0.636 / 0.458 | 0.465 / 0.237 | 1.205 / 1.183 | 2.938 / 4.600 |
| inflación mensual | 3 | 1.283 / 1.165 | 1.139 / 1.003 | 6.487 / 14.768 | 5.174 / 10.841 |
| inflación mensual | 6 | 2.696 / 3.965 | 2.178 / 2.721 | 8.073 / 21.808 | 6.548 / 15.199 |
| inflación mensual | 12 | 4.369 / 8.424 | 4.005 / 7.101 | 9.752 / 28.755 | 6.691 / 15.396 |
| PBI (anualizado) | 12 | 2.354 / 3.321 | 1.050 / 0.962 | 3.000 / 5.196 | 0.880 / 0.761 |

**Corridas terminadas antes del horizonte, holdout** (hiperinflación/colapso: 1983-1991 es
justamente el tramo que ADR 012 diseñó para poder divergir): h=6, calibrado 37.9 %, Aurora sin
calibrar 75.9 %, `a3_main` 0 %; h=12, calibrado 58.6 %, Aurora sin calibrar **100 %**, `a3_main` 0 %.
Confirma el diagnóstico mecánico de A4: `a3_main` (sin macro, ecuación de precios contractiva) NUNCA
puede divergir — por diseño, no por acierto —, mientras que con macro activo la mayoría de los meses
de arranque del holdout SÍ terminan en un colapso/hiperinflación antes de 12 meses, calibrado o no
(58.6 % vs 100 %): la calibración reduce la frecuencia de divergencia temprana pero no la elimina.

**Lectura honesta (holdout)**: el calibrado mejora MUCHO a Aurora sin calibrar y a `a3_main` en
inflación (h=12 RMSE: 4.369 vs 9.752 vs 6.691) pero SIGUE POR DETRÁS de la persistencia en casi todos
los horizontes de inflación y de PBI. Excepción notable: en PBI del holdout, `a3_main` da MEJOR
resultado que `a5b_macro` en h=6/12 (0.900/0.880 contra 1.965/2.354) — el PBI no está gobernado por
la capa macro (ADR 012 no lo toca), así que calibrar 155 parámetros conjuntamente (económicos +
macro) sobre una pérdida dominada por precios/reservas/cambiario parece empeorar el ajuste de
variables que no dependen de esos mecanismos, respecto de calibrar solo el bloque económico
(`a3_main`). No se investigó más a fondo en esta ronda — queda como hallazgo para la próxima.

**Diagnóstico 2019-12 (con los coeficientes calibrados)**: desde 2019-12, 20 semillas, 48 meses,
`--fx-regime auto`: **0/20 (0 %) en `hyperinflation`** (vs. 20/20 con los coeficientes macro sin
calibrar — la calibración elimina la hiperinflación espuria de este tramo) pero **20/20 (100 %) en
`collapse`** (`political_stability < 15` tres meses seguidos), mediana de colapso en el mes 25
(rango 20-27). El fallo cambia de canal (precios → estabilidad política), no desaparece: ninguna
semilla sobrevive los 48 meses. Relevante para V4 (ver más abajo): si el colapso ocurre siempre antes
de la elección de fin de mandato, la hipótesis electoral de V4 no se puede evaluar con la misma
confianza que la de inflación.

**Pendiente, no implementado en esta ronda**: serie de tipo de cambio 1983-1991 (oficial o "dólar
bolsa" de la época; `exchange_rate_annual.csv` actual termina en 1951, `exchange_rate_parallel_
monthly_linked.csv` arranca en 2008, ninguna de las dos cubre el holdout) — si aparece, aplicar el
mismo patrón de `RealData.inflation()` (interpolación anual + fallback documentado).


### Validación `a6_macro` (V1–V4, ADR 011 §8 + A5 ADR 012 §6)

`republica validate --country argentina --calibration a5b_macro --run-id a6_macro --tests
V1,V2,V3,V4`. **52.5s de pared total** (V1 7.4s, V2 17.7s, V3 13.4s, V4 13.6s), 50 semillas por
prueba y brazo. Reporte completo: `data/countries/argentina/validation/a6_macro/report.md`.
`registration.json` escrito antes de correr, no reescrito.

**Declaración in-sample/holdout (importante, no solo V3)**: de las 4 pruebas, **solo V1 (1988→1990)
cae en el holdout real** (`1983-12:1991-12`) de esta calibración. V2 (1998-01, 54 meses → hasta
2002-06), V3 (2016→2023) y **también V4 (2019-12→2023-11)** caen DENTRO del train
(`1992-01:2023-12`) — in-sample las tres, no solo V3. Esto es más restrictivo de lo que
`PLAN_ARGENTINA.md` (antes de esta ronda) daba a entender ("V3 ahora es in-sample"): con la ventana
de train ampliada a 1992-2023, de las cuatro pruebas históricas sólo una es una prueba de
generalización real.

| prueba | hipótesis | calibrado | Aurora sin calibrar | veredicto calibrado | veredicto Aurora | muestra |
|---|---|---:|---:|---|---|---|
| V1 | hyperinflation >50% en 12-24m | 0.0% | 100.0% | **NO CUMPLIDA** | CUMPLIDA | HOLDOUT |
| V2 | default/collapse >50% en 36-54m | 56.0% [42,68] | 22.0% [12,34] | **CUMPLIDA** | NO CUMPLIDA | in-sample |
| V3 | inflación final >80%, pierde en 2019 y 2023 | 47.5% infl, 0% aciertos | 1709.8% infl, 0% aciertos | NO CUMPLIDA | NO CUMPLIDA | in-sample |
| V4 | derrota >70%, inflación final >100% | infl 56.7%, derrota 0.0% | infl 1319.4%, derrota 0.0% | NO CUMPLIDA | NO CUMPLIDA | in-sample |
| C | Aurora falla al menos 1 de 3 | — | falla 3 de 4 (V2,V3,V4) | — | **CUMPLIDA** | — |

**Hallazgo transversal, el más importante de esta ronda**: en V1, V3 y V4 el brazo CALIBRADO termina
en `collapse` en el 100% de las semillas (50/50, 50/50, 50/50) — nunca en `hyperinflation`, a
diferencia de Aurora sin calibrar (que sí hiperinflaciona: 100% en V1, 100% en V3, 94% en V4). Solo
en V2 hay un resultado mixto (37 `collapse` / 13 `survived` de 50). La calibración desplazó el modo
de falla de "precios" (hiperinflación) a "estabilidad política" (`collapse`, `political_stability <
15` tres meses seguidos) en casi toda la validación, consistente con el diagnóstico 2019-12 de
arriba (0% hyperinflation, 100% collapse). Esto es lo que hace que V1 pase de "Aurora CUMPLE, sin
calibrar" a "calibrado NO CUMPLE" — el calibrado técnicamente evita la hiperinflación específica que
pedía V1, pero mediante colapso institucional generalizado, no mediante estabilización real (la
inflación mensual final del calibrado en V1 es 14.97%, todavía alta, y las semillas nunca sobreviven
para mostrar una trayectoria completa de 24 meses).

**V4 — la hipótesis electoral NO se pudo evaluar**: 50 de 50 semillas calibradas (y 50 de 50 de
Aurora) terminan en `collapse`/`hyperinflation` antes del mes 48 (mediana calibrado: mes 29). NINGUNA
semilla, en ningún brazo, llega a celebrar la elección de fin de mandato dentro de la ventana. La
"derrota electoral 0.0%" de la tabla NO significa "el oficialismo gana": significa que no hay
denominador (cero elecciones celebradas). Coherente con el diagnóstico 2019-12 de arriba.

**V2 (único veredicto CUMPLIDO)**: el RMSE de reservas del calibrado (14 875 USD M) es MEJOR que el
de Aurora (26 098) pero mucho PEOR que el baseline de persistencia (4 342 USD M congelando el nivel
real de 1998-01) — igual patrón que el resto de la calibración: mejora respecto de Aurora, no
respecto de "no hacer nada".

**Diagnóstico `fx_regime_inertness` (V2)**: verificado empíricamente (3 semillas) que `peg` y
`float` dan trayectorias DISTINTAS con macro activo — a diferencia de A4 (ADR 011), donde `--fx-
regime peg` no tenía ningún efecto.

**Qué queda para V4 futuro**: nada pendiente de ADR 013 — la época de partidos 2015-2023 (con LLA)
cargó y corrió correctamente. Lo que falta es un modelo que sobreviva más allá del colapso
institucional temprano para poder medir la hipótesis electoral en absoluto; eso es un problema del
mecanismo de recuperación/colapso (ADR 012 secc. 5), no de la integración de partidos.

### Validación `a6b_collapse` (V4 con ADR 016, piso de legitimidad democrática)

`republica validate --country argentina --calibration a5b_macro --out
data/countries/argentina/validation/a6b_collapse --tests V4` (la CLI toma `--out`, no `--run-id`).
50 semillas por brazo, **13.6 s** de pared. Reporte completo:
`data/countries/argentina/validation/a6b_collapse/report.md`. Diseño, hipótesis registrada antes de
codear y notas de implementación: `docs/ADR_016_collapse_and_recovery.md`.

**Qué se cambió**: un piso de `political_stability` mientras corre un mandato constitucional en
democracia (`repression == 0`) y **no** hay ruptura monetaria o financiera aguda — hiperinflación
sostenida (> 15 %/mes por 3 meses), crisis bancaria, `sovereign_default`, o una salida forzada de
régimen cambiario dentro del mandato. El piso decae de `lf_base = 28` a `lf_min = 18` a lo largo del
mandato (los dos por encima de `terminal.collapse_stability = 15`). Detrás de
`features.legitimacy_floor`: off para Aurora, on para `--country argentina` con macro activo,
apagable con `--no-legitimacy-floor`.

**Por qué colapsaba** (diagnóstico con números, ADR 016 §2; semilla 1 de V4 volcada mes a mes): la
inflación NO era el canal — se queda en 3.6–3.9 %/mes (≈ 56 % anual) y nunca cruza el 20 % de
`terminal.hyper_inflation`. La cadena es política y cada eslabón satura en un extremo del `ranges`:
la tensión social arranca en 35, **por encima** del `tension_threshold` calibrado (21.25, contra 50
en Aurora), así que `−e_t·pos(tensión − 21.25)/10` domina la aprobación con −5.4 a −18.3 puntos por
mes contra un máximo de +2.35 de reversión; la aprobación toca el **piso 0** en el mes 9; eso deja
`+pr_a·approval_ref = +30.9` como constante en `protest_target`, que se va al **techo 100**; y eso
deja `+t_pr·(100 − 18.56) = +45.3` en `tension_target`, que también se va a **100**. Con los dos
términos saturados, `stability_target = 157.03 − 50.92 − 61.46 + … ≈ 29` — **por encima** del umbral
de colapso — y lo que mete la estabilidad debajo de 15 es el ruido de `shock_stability` (−4 a −8 por
mes, de acciones de actores y `agreement_broken`).

**Resultados medidos (50 semillas por celda; lo único que cambia entre columnas es el flag):**

| escenario | piso OFF | piso ON |
|---|---|---|
| 2019-12, 48m, `a5b_macro` | `collapse` 50/50, mediana mes 29 [24, 35]; **0 %** llega al mes 48 | `defeated` 50/50; **100 %** llega al mes 48 |
| ↳ inflación anual final (mediana) | 56.8 % | **128.8 %** (métrica de V4) |
| 1998-01 + `peg`, 54m, `a5b_macro` | `collapse` 37/50 (**74 %**), mediana mes 39 | `collapse` 37/50 (**74 %**), mediana mes 39 — **idéntico semilla por semilla** |
| 2019-12, 48m, Aurora sin calibrar | 47 `hyperinflation` / 3 `collapse` | idéntico |
| ADR 012 §7: 2a hiper 1988-06 (≥ 50 %) | 20/20 | 20/20 (idéntico) |
| ADR 012 §7: 2b no espuria 2003-06 (0 %) | 0/20 | 0/20 (idéntico) |
| ADR 012 §7: 3c salida del `peg` 1998-01 (≥ 50 %) | 17/20 | 17/20 (idéntico) |
| ADR 012 §7: 5 recuperación 2003-06 → 2015-12 (≥ 80 %) | 20/20 | 20/20 (idéntico) |

El mecanismo cambia **exactamente un** escenario de los seis: distingue 2020 de 2001 en vez de
eliminar el colapso. (2001-01 no tiene `initial_states` en el paquete — las ocho fechas son 1983-12,
1988-06, 1991-04, 1998-01, 2003-06, 2016-01, 2019-12, 2023-12 — así que el discriminante se mide
desde 1998-01 con `peg` y 54 meses, cuya ventana termina exactamente en 2002-06.)

**V4:**

| prueba | hipótesis | calibrado | Aurora | veredicto calibrado | antes (`a6_macro`) |
|---|---|---:|---:|---|---|
| V4 | derrota > 70 %, inflación final mediana > 100 % | infl **128.8 %** [125.7, 143.8], derrota **100.0 %** [100, 100] | infl 1 319.4 %, derrota 0.0 % | **CUMPLIDA** | NO CUMPLIDA (infl 56.7 %, derrota 0 % sin denominador) |

Semillas calibradas que terminan antes del mes 48: **0 de 50** (antes: 50 de 50). Por primera vez la
hipótesis electoral de V4 tiene denominador.

**Tres advertencias sobre ese resultado** (detalle en ADR 016, Notas de implementación):

1. V4 es **in-sample** (2019-12→2023-11 cae dentro del train `1992-01:2023-12` de `a5b_macro`).
2. El `incumbent_party` de las 50 semillas es **`cambiemos_jxc`**, no `fpv_fdt_pj`:
   `politics/parties/2015-2023.json` marca `in_government` en el partido de **apertura de la época**
   (Macri 2015) y `world/eras.py` lo aplica sin resolver por fecha de arranque. "Derrota del
   oficialismo = 100 %" significa *"JxC pierde contra el FdT"*, no *"el FdT pierde"*. Es dato/loader
   de ADR 013, no se tocó.
3. **LLA gana 0/50**, pero llega al balotaje en **50/50**: 37.66 % en primera vuelta (mediana; el
   real de oct-2023 fue 29.99 %) y 45.22 % en el balotaje contra 54.78 % del FdT — el espejo del
   55.65 % real. Confirma con número el diagnóstico de ADR 013 ("el balotaje es el cuello de
   botella"). `test_lla_wins_more_often_under_sustained_distrust` se deja en `xfail(strict=True)`:
   se verificó que sigue fallando, y corre un escenario sintético que este ADR no toca.

**Tres lecturas de la trayectoria con el piso puesto** (semilla 1, 48 meses): (i) el piso muerde
desde el mes 26 y a partir de ahí `political_stability` **es** el piso, exactamente
(`18 + 10·(1 − m/48)`: 22.58 en el mes 26, 18.00 en el 48) — deja de ser una variable del modelo y
pasa a ser la rampa de legitimidad, que es el riesgo declarado del ADR hecho visible; (ii) hallazgo
emergente no buscado: la inflación **se acelera** en la segunda mitad, de ~3.9 %/mes a 8–11 %/mes
(la corrida que antes moría en el mes 29 nunca llegaba a mostrarlo) — es lo que sube la inflación
anual final de 56.8 % a 128.8 %, en la dirección correcta contra el ~50 % → ~211 % real, todavía
subestimando; (iii) el piso **no** rescata a la confianza institucional, que cae a 0 en el mes 30 y
se queda: con `stability_base = 157.03` calibrado, el canal de vuelta
`ic_s·(estab − stability_base)/10` sigue aportando −1.7 por mes con una estabilidad de 20. El modelo
llega a la elección en un estado social (aprobación 0, tensión 100, protesta 100, confianza 0) que
sigue siendo implausible: el mecanismo consigue que la corrida LLEGUE, no que llegue en un estado
creíble.

**Lo que el diagnóstico encontró y ADR 016 NO arregló** (`src/republica/calibration/*` es de otro
agente): (a) la recuperación §5 del ADR 012 está **inerte** — `recovery_inflation_max` calibrado en
1.129 %/mes contra una inflación de 3.6–3.9 %/mes hace que el canal `t_rec` no se dispare nunca, y
`ic_target_base = 22.77` deja a `ic_rec` actuando sólo como piso en ≈ 22.8, muy por debajo de
`conf_ref = 58.29`; (b) el bucle tensión↔protesta es un **atractor absorbente**
(`tension_target ≈ 110`, `protest_target ≈ 131`, los dos sobre el techo 100) — cualquier mecanismo
aguas abajo parchea un síntoma; (c) `default_risk` sigue arrancando alto en períodos solventes, pero
se midió que **no participa** de este colapso (`default_risk_threshold` calibrado = 0.99944: el
default endógeno no se dispara en ninguna semilla, y ni `default_risk` ni `fx_gap` entran en
`stability_target` ni en la aprobación).

---

## Serie de tipo de cambio anual enlazada 1962–2012 (cierre del pendiente del holdout)

**El pendiente.** La corrida `a5b_macro` dejó anotado: "serie de tipo de cambio 1983-1991
(oficial o 'dólar bolsa' de la época; `exchange_rate_annual.csv` actual termina en 1951,
`exchange_rate_parallel_monthly_linked.csv` arranca en 2008, ninguna de las dos cubre el
holdout) — si aparece, aplicar el mismo patrón de `RealData.inflation()`". En los hechos:
`RealData.fx_log()` devolvía `None` para **todo** el holdout `1983-12:1991-12`, así que el
término `exchange_rate` del objetivo quedaba sin puntuar ahí para los cuatro brazos por igual
(calibrado, persistencia, Aurora y `a3_main`) — el mismo patrón de falla silenciosa que el
segundo bug de `a5_macro`, y por la misma causa.

**La fuente.** `PA.NUS.FCRF` del World Development Indicators del Banco Mundial ("Official
exchange rate, LCU per US$, period average"; origen declarado: IMF International Financial
Statistics), vía el mirror `ronnywang/worldbank` — el mismo repo de la fuente 17, única copia
alcanzable con `api.worldbank.org` respondiendo 403. Cobertura 1962–2012 (1960 y 1961 vienen
vacíos para Argentina en ese snapshot de diciembre de 2013). Detalle en `history/SOURCES.md`
fuente 22, `trust` A. La serie **ya viene enlazada** por el propio WDI a través de las cuatro
redenominaciones (1970, 1983, 1985, 1992): no se le aplicó ningún factor, y eso se verificó en
vez de asumirse.

**Los cruces** (`consistency.md` sección 14, reproducibles con
`uv run python scripts/build_argentina_fx_linked.py`):

| cruce | resultado |
|---|---|
| Monotonía 1962–1991 (el peso se depreció todos los años) | ninguna caída año a año |
| Empalme: anual 1991 (0.9536) vs mensual 1992-01 (0.9910) | 3.78 % (umbral 10 %) |
| Empalme: anual 1992 (0.9906) vs mensual 1992-01 | 0.04 % |
| Anual vs promedio de la mensual, 1992–2012 (n=21) | 0.77 % medio, 6.20 % máximo (2002) |
| Precios vs tipo de cambio 1962→1991 | ×10^11.66 vs ×10^11.04, brecha factor 4.2 |

La monotonía es el cruce que más importa: cualquier factor de redenominación mal aplicado habría
producido un salto hacia abajo, y no hay ninguno. La brecha contra la inflación acumulada (un
factor 4.2 en 29 años) es del orden esperable por la inflación de Estados Unidos del período más
apreciación real; un error de unidad habría dado varios órdenes de magnitud.

**El código.** `RealData.fx_level()` (nuevo) resuelve el nivel: mes exacto de
`exchange_rate_official_monthly.csv` desde 1992-01 y, si no hay, la serie anual interpolada. La
interpolación es **geométrica** (sobre `log`), a diferencia de la de inflación: entre 1962 y 1991
el nivel crece once órdenes de magnitud (1989 solo multiplica por 48), y una interpolación lineal
en niveles concentraría casi toda la depreciación de un año en sus últimos meses. `fx_log()` pasa
a usarla; `std("exchange_rate")` **no**: el `sigma` de normalización queda anclado a la serie
mensual real, por la misma razón por la que el de inflación lo está (los cambios mensuales de una
interpolación de dos promedios anuales son doce valores idénticos por año, ruido cero, y mezclarlos
correría la escala — con 1989–1990 la haría explotar).

**Lo que NO cambió, deliberadamente.** El `exchange_rate` del estado inicial sigue siendo
`assumed = 100`: `world/economy.py` solo lo mueve multiplicativamente y el objetivo compara
cambios logarítmicos contra el propio nivel inicial del modelo, así que el nivel inicial no altera
ninguna trayectoria; cargar `6e-5` (australes de 1985 expresados en ARS) como "índice"
desconectaría la escala base 100 de Aurora sin ganar fidelidad. La regla nueva
`rule_exchange_rate_index` sí deja el nivel real de referencia y su procedencia en el `note` del
estado inicial, para que quede registrado de dónde saldría el ancla si algún día el motor la usara.

**Lo que sigue faltando.** Mensual antes de 1992 no existe: esta serie es anual e interpolada, con
el corrimiento de ~6 meses que arrastra la convención de A0 (el promedio anual se fecha
`YYYY-01-01` y se trata como el valor vigente al 1 de enero, igual que la inflación anual). El
snapshot termina en 2012 y 1952–1961 sigue sin dato. **Este cierre no se midió todavía contra una
recalibración**: habilita el término cambiario en el holdout, no mejora ningún número por sí solo.
La próxima corrida completa es la que va a decir si el holdout con dato cambiario cambia la
lectura de `a5b_macro`.


## Argentina A7 (ADR 017): calibración por régimen cambiario y exclusión de coeficientes legacy

Ronda de MECANISMO: se construyeron y probaron los tres cambios de abajo con `--quick`; **la corrida
completa no está en esta entrada** (la corre el orquestador con el comando de `docs/ADR_017_
calibration_by_regime.md` §8, run-id sugerido `a7_by_regime`). Ningún número de ajuste de acá sale
de una calibración real.

### 1. Los 8 `Coefficients` legacy sin señal salen del vector

Diagnóstico completo en ADR 017 §1. Con `features.macro_regime` prendido, la función objetivo corre
siempre por `step_macro_economy` y **nunca** por `step_economy`, así que los campos de
`Coefficients` que solo lee el motor legacy no cambian la pérdida ni una décima: CMA-ES los deja
donde quiera. Medido en `a5b_macro`: `rho_pi = 2.298` contra el 0.85 de Aurora (un AR(1) de precios
con coeficiente 2.3, explosivo por construcción). Esa es la causa raíz del hallazgo de ADR 014
(las 135 ventanas anuales 1916–1960 del backtest `b1_a5b` perdieron el 100 % de sus semillas
calibradas por `OverflowError` en `(1 + g_m/100)**12`, 4050 de 4050).

La lista se obtuvo comparando por programa las referencias `coeff.<campo>` del cuerpo de las dos
funciones: `step_economy` lee 44, `step_macro_economy` lee 36, y los 36 son un subconjunto de los
44. La diferencia son 8, todos de bloques que ADR 012 reemplazó entero: `rho_pi`, `c_e`, `c_r`,
`c_g`, `c_f` (ecuación de precios legacy, §4.3 del spec), `k_w` (canal salarial, 4.4), `k_tb`
(balanza comercial, 4.5), `k_conf` (confianza institucional, 4.6).

`build_parameter_space(include_macro=True)` los excluye: el vector pasa de **155 a 147** parámetros
(89 de `Coefficients` + 58 macro). Quedan fijos en el valor de Aurora del paquete y se escriben así
en el `coefficients.json`, para que el objeto siga siendo usable por `world/annual.py`, que sí los
lee. Los otros ~53 campos de `Coefficients` (sociedad, política, elecciones, percepción) siguen en
el vector: los ejercitan `step_society`/`step_politics`, que corren igual con macro activo.

### 2. Guarda numérica del modo anual, contada

La exclusión arregla las calibraciones futuras, no las ya escritas. `world/annual.py` acota ahora
`g_m` a `[-50, +50] %` **mensual** (±50 % mensual compuesto son −99.8 % o +12.875 % anual: fuera de
ese rango es ruido numérico, no economía) antes de `(1 + g_m/100)**12`, y **cuenta** los clampeos en
`AnnualRecord.g_m_clamped` / `AnnualHistory.g_m_clamped` (también en la última línea del JSONL). El
clamp llega a `step_economy` como un parámetro opcional `g_m_clamp` cuyo default `None` deja el modo
mensual byte a byte igual que antes.

Resultado medido con `a5b_macro` (`python -m republica.backtest --country argentina --calibration
a5b_macro --from 1920 --to 1925 --horizons 12 --seeds 3`): el brazo calibrado pasa de **0 semillas
usables a 3 de 3 en las seis ventanas**. Pero el contador dice `g_m_clamped = 29` sobre 60 sub-pasos
en 5 años y el `gdp_growth` queda pegado al techo (30 %): **el brazo calibrado de 1916–1960 con
`a5b_macro` ahora tiene datos, y son datos contra la guarda, no contra el modelo**. Para eso está el
contador. Con Aurora (o con cualquier calibración hecha ya con la exclusión de arriba) da 0.

### 3. Calibración POR RÉGIMEN CAMBIARIO (`--by-regime`)

`a5b_macro` ajustó un solo vector de 155 parámetros a 124 meses de arranque que cruzan cuatro
regímenes cambiarios que `step_macro_economy` trata con **ramas de código distintas** (ADR 012 §3).
El pendiente de `PLAN_ARGENTINA` §7 pedía partir eso; `republica calibrate --by-regime` lo hace:
particiona los meses de arranque de train por el `fx_regime` real de `fx_regimes.csv` en `t0` y
corre un CMA-ES por grupo (`--budget-per-group`, default `--budget`).

**Tres grupos**, con `crawl` agrupado con `peg` porque el motor ya los trata juntos (una sola rama
`elif fx_regime in ("crawl", "peg")`) y porque en el train no hay ni un mes de arranque `crawl`.
Distribución con stride 3 y horizonte 12:

| grupo | train `1992-01:2023-12` (124) | holdout `1983-12:1991-12` (29) |
|---|---:|---:|
| `float` | 54 (43.5 %) | 0 |
| `peg` (41 `peg`, 0 `crawl`) | 41 (33.1 %) | **29** (todos `crawl`) |
| `control` | 29 (23.4 %) | 0 |

Consecuencia que hay que tener presente al leer el reporte de la corrida completa: **el holdout cae
entero en el grupo `peg`**, así que mide la generalización de ese vector a una banda `crawl` que
nunca vio, y los vectores `float` y `control` quedan sin ninguna prueba de generalización.

`coefficients.json` nuevo: `{"by_regime": {"peg": {...}, "float": {...}, "control": {...}},
"default": {...}}`, donde `default` es una COPIA del vector del grupo con más meses de arranque de
train (`float`, 54 de 124) y se usa cuando no hay fecha o el grupo no tiene vector propio. El
formato viejo (un solo vector en la raíz) se sigue leyendo sin cambios: `a3_main`, `a5_macro` y
`a5b_macro` cargan igual que siempre.

El vector se elige por el `fx_regime` de la fecha de `--start`, y `republica run` loguea cuál
eligió. Si el régimen SIMULADO sale de su grupo dentro de la corrida (`fx_regime_exit`: salida
forzada de un `peg` por reservas), el vector cambia en caliente el mes siguiente y queda el evento
`fx_vector_switch:<grupo>` en el JSONL — verificado en una corrida real desde 1998-01
(`fx_regime_exit` mes 7, `fx_vector_switch:float` mes 8). Lo que **no** cambia el vector es cruzar
una frontera de `fx_regimes.csv` por CALENDARIO: el motor tampoco cambia el régimen por calendario
(simplificación ya declarada en ADR 012), y hacerlo sería un cambio de modelo, no de calibración.

El reporte muestra las tablas de siempre (RMSE + cola pesada + "terminaron antes del horizonte",
contra persistencia, Aurora sin calibrar y `a3_main`) **por grupo Y agregadas**; en las agregadas
cada mes de arranque se puntúa con el vector de su grupo.

### 4. `--weights`: ponderación de las variables del objetivo

Sale del hallazgo de A5b de más arriba (`a3_main`, sin macro, ajusta mejor el PBI que `a5b_macro`
porque la capa macro no gobierna el PBI). `republica calibrate --weights "inflation=2,gdp_growth=0.5"`
multiplica el término de cada variable en el escalar que minimiza CMA-ES. **El default no cambia**:
sin `--weights`, todos los pesos quedan en 1.0 y el escalar es el de siempre. Los pesos se guardan
en `coefficients.json` y se imprimen en el reporte — una corrida con pesos no es comparable con una
sin pesos y tiene que verse. Las tablas siguen mostrando cada variable sin ponderar.

### Hipótesis registrada, todavía sin evaluar

> Por régimen, el calibrado iguala o supera a persistencia en inflación a h=12 en al menos 2 de 3
> grupos en train, y no empeora el holdout agregado respecto de `a5b_macro`.

Criterio operativo y referencias en ADR 017 §6, fijados antes de correr. La corrida probe de esta
ronda (`a7_quick_probe`: `--quick --by-regime --workers 2`, 40 evaluaciones por grupo, stride 12,
100 s de pared) sirvió únicamente para verificar el pipeline de punta a punta y se borró de `data/`;
con ese presupuesto sus números no significan nada y no se reportan.

---

## Corrida completa `a7_by_regime` + revalidación `a8_a7` + backtest `b3_a7` (cierre de la tercera ronda)

Las tres corridas salen del mismo estado del repo: ADR 015 (transiciones de régimen endógenas),
ADR 016 (piso de legitimidad democrática) y ADR 017 (calibración por régimen cambiario, exclusión
de coeficientes legacy, guarda del modo anual) integrados, más la serie de tipo de cambio anual
enlazada 1962–2012.

### Calibración `a7_by_regime`

`republica calibrate --country argentina --train 1992-01:2023-12 --holdout 1983-12:1991-12 --loss
heavy --by-regime --budget-per-group 400 --stride 3 --workers 4 --seed 42`. **1242 evaluaciones,
1336 s (22.3 min)**, tres grupos (`peg` 41 meses de arranque, `float` 54, `control` 29; `default` =
`float`).

**La hipótesis registrada en ADR 017 §6 NO se cumplió.** Pedía que el calibrado igualara o superara
a persistencia en inflación a h=12 en al menos 2 de 3 grupos del train. Resultado: **0 de 3**.

| grupo | calibrado | persistencia | veredicto |
|---|---:|---:|---|
| `peg` | 0.940 | 0.725 | pierde |
| `float` | 1.054 | 0.678 | pierde |
| `control` | 1.009 | 0.661 | pierde |

Y es PEOR que el vector único de `a5b_macro` en esa celda (0.797). Partir el train en tres no mejoró
la inflación: la empeoró. Lectura honesta: cada grupo se ajusta con un tercio de los meses de
arranque, y para el mecanismo de precios eso pesa más que la ganancia de especificidad por régimen.

Lo que sí mejoró en el train agregado, contra persistencia: **PBI** a h=6/12 (0.946/1.004 contra
1.046/1.404), **desempleo** en todos los horizontes con dato (0.595 contra 0.636 a h=12) y **tipo de
cambio** en todos (4.468 contra 5.017 a h=12).

**El holdout ahora tiene tipo de cambio.** Es el efecto directo de la serie anual enlazada: antes las
filas de `exchange_rate` del holdout decían "sin dato" para los cuatro brazos por igual. Con dato, el
calibrado le gana a persistencia con claridad en los cuatro horizontes (h=12: **17.311 contra
27.523**; h=6: 7.649 contra 14.399). En inflación del holdout sigue muy por detrás (8.459 contra
4.005 a h=12), aunque le gana a Aurora sin calibrar (9.752).

**La exclusión de coeficientes legacy hizo lo que prometía.** `rho_pi + c_e` queda en **0.910** —el
valor de Aurora, sin tocar— en los tres grupos, contra **2.323** en `a5b_macro`. Ese 2.323 era un
AR(1) de precios explosivo al que CMA-ES llegaba porque la función objetivo con macro activo nunca
ejercitaba esos coeficientes: no recibían señal y derivaban libres. Es la causa raíz del
`OverflowError` sistemático del modo anual documentado en ADR 014.

### Revalidación `a8_a7` (V1–V4, 50 semillas, con ADR 015 y ADR 016 activos)

50.3 s. **2 de 4 hipótesis CUMPLIDAS**, contra 1 de 4 en `a6_macro`.

| prueba | hipótesis | calibrado | Aurora | veredicto |
|---|---|---|---|---|
| V1 | hiperinflación > 50 % desde 1988-06 | 0.0 % | 100.0 % | **NO CUMPLIDA** |
| V2 | default/colapso > 50 % en 1998→2002 | 66.0 % [54, 80] | 32.0 % | **CUMPLIDA** |
| V3 | inflación final > 80 % y aciertos 2019 y 2023 | 496.2 %; 94 % / 6 % | 1 605.6 %; 0 % / 0 % | **NO CUMPLIDA** |
| V4 | derrota > 70 % e inflación final > 100 % desde 2019-12 | 383.4 %; **derrota 100 %** | 1 281.7 %; derrota 0 % | **CUMPLIDA** |

**V4 pasa de no evaluable a cumplida.** En `a6_macro` las 50 semillas terminaban en `collapse` antes
del mes 48 y la elección de fin de mandato no llegaba a celebrarse: la "derrota 0 %" de entonces no
significaba que el oficialismo ganara, significaba que no había denominador. Ahora **0 de 50**
terminan antes de los 48 meses y el oficialismo pierde en el 100 %. Es el efecto medido del piso de
legitimidad de ADR 016.

**V3 sigue sin cumplirse, y por una razón distinta a la de antes.** El acierto electoral de 2019 es
94 % pero el de **2023 es 6 %**. El modelo reproduce bien un oficialismo que pierde por deterioro
económico y mal uno que pierde ante un outsider; es el mismo cuello de botella del balotaje que
diagnosticó ADR 013. La inflación 2016→2023 da 496.2 % mediana contra 135 % real: ahora
**sobreestima** ~3.7×, donde `a5b_macro` subestimaba (47.5 %). Cambió el signo del error, no su
tamaño. Y solo el 6 % de las semillas llega al mes 96 sin colapsar: el piso de legitimidad sostiene
un mandato de cuatro años, no dos seguidos.

**V1 sigue en 0 %**, igual que `a5b_macro`: con los coeficientes calibrados la hiperinflación de 1989
no es alcanzable desde el estado real de 1988-06, aunque Aurora sin calibrar sí la produce (100 %).
El mecanismo de ADR 012 existe y los tests lo ejercitan; lo que no lo alcanza es el punto del espacio
de parámetros al que llega la calibración.

### Backtest `b3_a7` (1916–2022, 321 ventanas, 30 semillas, 2 brazos)

265 s (4.4 min) con 4 workers y transiciones de régimen activas. Contra `b1_a5b`:

| objetivo | `b1_a5b` | `b3_a7` | Δ |
|---|---:|---:|---:|
| Dirección de la inflación | 46.2 % | 46.0 % | −0.2 pp |
| Magnitud de la inflación | 30.4 % | 31.0 % | +0.6 pp |
| **Régimen** | 72.5 % | **90.4 %** | **+17.9 pp** |
| Elección | 52.6 % | 48.1 % | −4.5 pp |
| **Crisis** | 64.3 % | **72.6 %** | **+8.3 pp** |
| **Golpe (1916–1983)** | 58.0 % | **65.9 %** | **+7.9 pp** |

**El brazo calibrado ya no pierde 1916–1960.** En `b1_a5b` las 135 ventanas de modo anual tenían el
100 % de sus semillas calibradas descartadas por `OverflowError`, así que toda comparación
"calibrado vs Aurora" de esa corrida era en realidad sobre 1961–2022. Ahora los dos brazos tienen las
mismas 405 filas de modo anual. Advertencia que va con eso (ADR 017 §9.4): el modo anual corre
**contra la guarda numérica** (`g_m` clampeado), así que tiene datos, no necesariamente evidencia.

Por brazo, donde la calibración ayuda de verdad: **magnitud de la inflación** 40.5 % contra 21.5 % de
Aurora, y **crisis** 81.3 % contra 63.9 %. Donde no: **dirección de la inflación**, 44.5 % contra
47.4 % — Aurora sin calibrar le sigue ganando al signo del cambio, igual que en `b1_a5b`.

Régimen por modo inicial, que es donde se ve ADR 015: golpe **100 %** (N=18), democracia restringida
**100 %** (N=24), democracia 95.2 % (N=250), dictadura 68.1 % (N=72). Los dos primeros eran **0 %**.

La dispersión entre semillas sigue prediciendo el error: **Spearman 0.414** (era 0.433). El modelo
sabe cuándo no sabe, con la misma fuerza moderada de antes.

### Qué queda, en orden de importancia

1. **La dirección de la inflación no mejora con nada.** 46 % en las tres calibraciones probadas, y
   Aurora sin calibrar le gana. Acertar la magnitud sin acertar el signo del cambio es el límite más
   duro que tiene el modelo hoy, y ninguna de las tres rondas lo movió.
2. **El horizonte largo sigue colapsando.** 6 % de las semillas llega a 96 meses. El piso de
   legitimidad alcanza para un mandato, no para dos.
3. **La elección de 2023 (outsider) se acierta 6 %** contra 94 % de la de 2019. El balotaje de
   ADR 013 sigue sin resolverse.
4. **Partir el train por régimen empeoró la inflación.** Si se vuelve a intentar, conviene probar
   calibración jerárquica (un vector común más desvíos por régimen) antes que tres vectores
   independientes con un tercio de los datos cada uno.
5. **Nada de esto se corrió contra un LLM real todavía.** Toda la capa de IA sigue verificada solo
   con backends falsos.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de
Argentina; no son evidencia sobre lo que hubiera pasado.


## Barrido de sensibilidad al mes de arranque, 1983-12 → 1990-12 (ADR 019)

Entregable 4 de la tarea de ADR 019 (`docs/ADR_019_initial_state_sensitivity.md`): **85 arranques**,
uno por cada mes entre 1983-12 y 1990-12, **10 semillas**, **24 meses**, calibración `a7_by_regime`,
transiciones de régimen (ADR 015) y piso de legitimidad (ADR 016) activos, sin shocks forzados. Es
lo mismo que corre `republica run --country argentina --start <mes> --calibration a7_by_regime
--regime-transitions`. 85 × 10 corridas en **21 s** con 8 workers.

Lo que se mide en cada arranque es el **mes en que se cumple el criterio terminal del propio
modelo** (`terminal.hyper_inflation = 20 %/mes` durante `terminal.hyper_months = 3` meses seguidos).
La columna "real" es ese MISMO criterio evaluado sobre la serie mensual real
(`history/inflation_cpi_monthly_linked.csv`, BCRA/INDEC empalmada), no el mes de la hiperinflación
de junio de 1989: ver ADR 019 §7.0, donde se muestra que confundir las dos cosas es lo que hacía que
el criterio de éxito original ("después del mes 48 desde 1983-12") apuntara en la dirección
equivocada — el dato real cumple el criterio del modelo en el **mes 15**.

Las dos columnas de modelo son:

- **antes**: ADR 012 puro, con el estado inicial que construía A2 / `initial_state_for` (inflación
  anual convertida a mensual).
- **después**: con ADR 019 (`indexation_state` prendido) y el estado inicial tomado de la serie
  mensual REAL.

### Qué salió

**1. El síntoma que la tarea pedía buscar está, y es grande.** Con el estado inicial viejo, entre
meses de arranque contiguos:

| arranque | `pi0` (viejo) | `rho_eff` inicial | semillas | mediana |
|---|---:|---:|---:|---:|
| 1988-01 | 13.99 | 0.8536 | 3/10 | **17** |
| 1988-02 | 17.65 | 0.8696 | 9/10 | 15 |
| **1988-03** | 20.37 | 1.0065 | 10/10 | **3** |

Dos meses de diferencia en la fecha de arranque, y la mediana del mes de hiperinflación pasa de 17 a
3. La causa está aislada en ADR 019 §1.3: `rho_eff` cruza 1 en **17.4773 %/mes** con el vector
`peg`/`crawl` de `a7_by_regime`, y el dato inicial de 1983-12 lo cruzaba por **0.283 pp**.

**2. Y 1988-06 —el mes que mide la validación V1— era un outlier dentro de su propia vecindad.**
1988-05 arrancaba en 24.37, 1988-07 en 27.32, y 1988-06 en **13.99**. No es un fenómeno del modelo:
1988-06 es uno de los 8 hitos de `country.json` y usa la regla de A2 (anual del año más cercano, sin
interpolar) mientras sus vecinos caen a `initial_state_for` (anual interpolada). Para el mismo mes,
los dos constructores del proyecto difieren en **11.95 pp**. El dato mensual real es 18.0.

**3. El dato viejo tenía sesgo de anticipación.** `initial_state_for` construía la inflación de
1988-09 interpolando entre el promedio anual de 1988 y el de **1989** — que contiene la
hiperinflación de junio y julio de 1989. El "estado inicial" de septiembre de 1988 (29.66 %/mes) ya
traía adentro el dato de nueve meses después; el real de ese mes es 11.7. Toda calibración, backtest
o validación que arranque antes de 1997-02 (donde empieza `inflation_cpi_monthly.csv`) estuvo usando
estados iniciales contaminados con el futuro de la ventana que evalúa. Corregido en ADR 019 §3C:
`history/inflation_cpi_monthly_linked.csv` (1943-03+) estaba en el repo y no lo usaba nadie.

**4. Después del arreglo, el modelo sigue al dato.** Sobre los **31 arranques** donde modelo y dato
cruzan dentro de los 24 meses, el error mediano es de **3 meses**. Y hay **29 arranques donde
ninguno de los dos cruza** —entre ellos los 23 meses seguidos de 1985-07 a 1987-05, el Plan Austral
funcionando—, que el modelo acierta en bloque sin que se le haya dicho nada de ningún plan.

**5. Lo que sigue mal, medido.** Quedan 16 pares de meses contiguos donde la mediana salta más de 8
meses, contra 4 antes y **2 en el propio dato**. Casi todos son del tipo 1988-08 → 1988-09: la
inflación real cae de 27.6 a 11.7 %/mes y el modelo la sigue, mientras que el dato "sabe" que la
hiperinflación llega igual nueve meses después. El modelo no tiene cómo verlo — el Plan Primavera y
su derrumbe no están en ninguna de sus 21 variables, y 17 de esas 21 son la misma constante
`assumed` en todas las fechas (ADR 019 §1.1).

### La tabla completa

`pi0` es la inflación mensual real del mes de arranque (la columna es la misma para los dos brazos
sólo a partir del arreglo; antes del arreglo el brazo "antes" veía la conversión anual). "n/10" son
las semillas que cumplen el criterio terminal dentro de los 24 meses; la mediana es sobre esas.

| arranque | `pi0` real | antes: n/10, mediana | después: n/10, mediana | real |
|---|---:|---:|---:|---:|
| 1983-12 | 17.7 | 10/10, 6 | 8/10, 16 | 15 |
| 1984-01 | 12.5 | 10/10, 7 | 0/10, — | 14 |
| 1984-02 | 16.9 | 10/10, 6 | 10/10, 12 | 13 |
| 1984-03 | 20.3 | 10/10, 6 | 10/10, 6 | 12 |
| 1984-04 | 18.5 | 10/10, 6 | 10/10, 14 | 11 |
| 1984-05 | 17.1 | 10/10, 6 | 10/10, 16 | 10 |
| 1984-06 | 17.9 | 10/10, 6 | 10/10, 6 | 9 |
| 1984-07 | 18.3 | 10/10, 6 | 10/10, 6 | 8 |
| 1984-08 | 22.8 | 10/10, 6 | 10/10, 3 | 7 |
| 1984-09 | 27.5 | 10/10, 6 | 10/10, 3 | 6 |
| 1984-10 | 19.3 | 10/10, 6 | 10/10, 15 | 5 |
| 1984-11 | 15.0 | 10/10, 6 | 1/10, 23 | 4 |
| 1984-12 | 19.7 | 10/10, 6 | 10/10, 6 | 3 |
| 1985-01 | 25.1 | 10/10, 8 | 10/10, 3 | 3 |
| 1985-02 | 20.7 | 9/10, 12 | 10/10, 11 | 3 |
| 1985-03 | 26.5 | 7/10, 14 | 10/10, 3 | 3 |
| 1985-04 | 29.5 | 3/10, 17 | 10/10, 3 | — |
| 1985-05 | 25.1 | 1/10, 13 | 10/10, 3 | — |
| 1985-06 | 30.5 | 2/10, 18 | 10/10, 3 | — |
| 1985-07 | 6.2 | 0/10, — | 0/10, — | — |
| 1985-08 | 3.1 | 0/10, — | 0/10, — | — |
| 1985-09 | 2.0 | 0/10, — | 0/10, — | — |
| 1985-10 | 1.9 | 0/10, — | 0/10, — | — |
| 1985-11 | 2.4 | 0/10, — | 0/10, — | — |
| 1985-12 | 3.2 | 0/10, — | 0/10, — | — |
| 1986-01 | 3.0 | 0/10, — | 0/10, — | — |
| 1986-02 | 1.7 | 0/10, — | 0/10, — | — |
| 1986-03 | 4.6 | 0/10, — | 0/10, — | — |
| 1986-04 | 4.7 | 0/10, — | 0/10, — | — |
| 1986-05 | 4.0 | 0/10, — | 0/10, — | — |
| 1986-06 | 4.5 | 0/10, — | 0/10, — | — |
| 1986-07 | 6.8 | 0/10, — | 0/10, — | — |
| 1986-08 | 8.8 | 0/10, — | 0/10, — | — |
| 1986-09 | 7.2 | 0/10, — | 0/10, — | — |
| 1986-10 | 6.1 | 0/10, — | 0/10, — | — |
| 1986-11 | 5.3 | 0/10, — | 0/10, — | — |
| 1986-12 | 4.7 | 0/10, — | 0/10, — | — |
| 1987-01 | 7.6 | 0/10, — | 0/10, — | — |
| 1987-02 | 6.5 | 0/10, — | 0/10, — | — |
| 1987-03 | 8.3 | 0/10, — | 0/10, — | — |
| 1987-04 | 3.3 | 0/10, — | 0/10, — | — |
| 1987-05 | 4.2 | 0/10, — | 0/10, — | — |
| 1987-06 | 8.0 | 0/10, — | 0/10, — | 24 |
| 1987-07 | 10.1 | 1/10, 20 | 0/10, — | 23 |
| 1987-08 | 13.7 | 1/10, 20 | 1/10, 16 | 22 |
| 1987-09 | 11.7 | 2/10, 19 | 1/10, 22 | 21 |
| 1987-10 | 19.6 | 6/10, 19 | 10/10, 12 | 20 |
| 1987-11 | 10.3 | 4/10, 19 | 0/10, — | 19 |
| 1987-12 | 3.4 | 4/10, 18 | 0/10, — | 18 |
| 1988-01 | 9.1 | 3/10, 17 | 0/10, — | 17 |
| 1988-02 | 10.4 | 9/10, 15 | 0/10, — | 16 |
| 1988-03 | 14.8 | 10/10, 3 | 3/10, 18 | 15 |
| 1988-04 | 17.2 | 10/10, 3 | 1/10, 12 | 14 |
| 1988-05 | 15.7 | 10/10, 3 | 3/10, 19 | 13 |
| 1988-06 | 18.0 | 1/10, 20 | 5/10, 19 | 12 |
| 1988-07 | 25.6 | 10/10, 3 | 10/10, 3 | 11 |
| 1988-08 | 27.6 | 10/10, 3 | 10/10, 3 | 10 |
| 1988-09 | 11.7 | 10/10, 3 | 0/10, — | 9 |
| 1988-10 | 9.0 | 10/10, 3 | 0/10, — | 8 |
| 1988-11 | 5.7 | 10/10, 3 | 0/10, — | 7 |
| 1988-12 | 6.8 | 10/10, 3 | 0/10, — | 6 |
| 1989-01 | 8.9 | 10/10, 3 | 0/10, — | 5 |
| 1989-02 | 9.6 | 10/10, 3 | 0/10, — | 4 |
| 1989-03 | 17.0 | 10/10, 3 | 6/10, 16 | 3 |
| 1989-04 | 33.4 | 10/10, 3 | 10/10, 3 | 3 |
| 1989-05 | 78.5 | 10/10, 3 | 10/10, 3 | 3 |
| 1989-06 | 114.5 | 10/10, 3 | 10/10, 3 | 8 |
| 1989-07 | 196.6 | 10/10, 3 | 10/10, 3 | 7 |
| 1989-08 | 37.9 | 10/10, 3 | 10/10, 3 | 6 |
| 1989-09 | 9.4 | 10/10, 3 | 0/10, — | 5 |
| 1989-10 | 5.6 | 10/10, 3 | 0/10, — | 4 |
| 1989-11 | 6.5 | 10/10, 3 | 0/10, — | 3 |
| 1989-12 | 40.1 | 10/10, 3 | 10/10, 3 | 3 |
| 1990-01 | 79.2 | 10/10, 3 | 10/10, 3 | — |
| 1990-02 | 61.6 | 10/10, 3 | 10/10, 3 | — |
| 1990-03 | 95.5 | 10/10, 3 | 10/10, 3 | — |
| 1990-04 | 11.4 | 10/10, 3 | 1/10, 23 | — |
| 1990-05 | 13.6 | 10/10, 3 | 1/10, 19 | — |
| 1990-06 | 13.9 | 10/10, 3 | 1/10, 21 | — |
| 1990-07 | 10.8 | 10/10, 3 | 0/10, — | — |
| 1990-08 | 15.3 | 10/10, 3 | 0/10, — | — |
| 1990-09 | 15.7 | 10/10, 6 | 0/10, — | — |
| 1990-10 | 7.7 | 8/10, 16 | 0/10, — | — |
| 1990-11 | 6.2 | 3/10, 18 | 0/10, — | — |
| 1990-12 | 4.7 | 0/10, — | 0/10, — | — |

### C1 y C2 de ADR 019, medidos

| | antes | después | real |
|---|---:|---:|---:|
| **C1** 1983-12, mediana del mes de hiperinflación (15 semillas, 72 meses) | **6.5–7** | **15** (13/15) | **15** |
| **C2** 1988-06, semillas que cruzan 20 %/mes en 24 meses (V1 / ADR 012 §7 test 2a) | **0/50** | **15/20 = 75 %** | cruza (mes 12) |
| Control 2003-06 (ADR 012 §7 test 2b) | 0/20 | **0/20** | no cruza |

Las dos condiciones se cumplen a la vez, y el control de no-espuriedad de 2003-06 no se movió. El
criterio literal del enunciado de la tarea ("desde 1983-12 la hiperinflación después del mes 48")
**no se cumple y no se intentó cumplir**: ADR 019 §7.0 muestra, con la serie del propio repositorio,
que cumplirlo significaba alejarse del dato — la Argentina real estuvo tres meses seguidos arriba
del 20 % mensual en enero–marzo de **1985**, catorce meses después de diciembre de 1983. El mes 66
es el episodio de hiperinflación (114.5 %/mes), no el criterio terminal del modelo.

### El filo, aislado del cambio de dato

Moviendo SÓLO `inflation`/`inflation_lag1` del estado de 1983-12 (10 semillas, 36 meses), en la
banda de 2 pp que rodea al umbral de `rho_eff = 1`:

| | rango de la mediana entre `pi0` 17.0 y 19.0 | sensibilidad |
|---|---:|---:|
| ADR 012 (flag apagado) | 11.0 → 5.5 = **5.5 meses** | 2.75 meses por pp |
| **ADR 019 (flag prendido)** | 13.0 → 11.5 = **1.5 meses** | **0.75 meses por pp** |

**3.7 veces menos sensible**, y el nivel al que se estabiliza (11.5–13) es el del dato real (15
desde 1983-12, 12 desde 1988-06). Entre `pi0` 17.0 y 19.0 la respuesta con el flag prendido es
literalmente plana en 12 meses.

### Qué queda (se suma a la lista de la tercera ronda)

6. **El modelo sigue sin meseta de inflación alta.** Con `pi_anchor` = EMA(36) de su propia
   inflación, el ancla alcanza al nivel y el mapa de precios queda con pendiente `1 + c_e > 1` para
   cualquier nivel: toda corrida termina hiperinflacionando, lo único que cambia es cuánto tarda. La
   inercia de ADR 019 hace que el "cuánto tarda" coincida con el dato, pero no crea un punto fijo
   alto estable. Es el próximo problema del bloque de precios.
7. **Los grupos `float` y `control` de `a7_by_regime` tienen `rho_eff` máximo 0.8086 y 0.8527**, los
   dos por debajo de 1: para cualquier arranque en una ventana `float` o `control` la
   hiperinflación por ese canal es **estructuralmente inalcanzable**, sin importar el estado
   inicial. No es un problema de estructura sino del punto del espacio de parámetros al que llegó
   la calibración; se arregla recalibrando, y conviene que la próxima corrida lo mire explícito.
8. **Hay que recalibrar con el dato inicial corregido.** `a7_by_regime` se calibró con estados
   iniciales que, antes de 1997-02, salían de una interpolación anual con sesgo de anticipación
   (punto 3 de arriba). Los coeficientes de esa corrida absorbieron ese sesgo. Todo lo medido en
   esta sección usa esos coeficientes tal cual —es la comparación honesta contra la línea de base—
   pero una recalibración con el dato real es trabajo pendiente y debería mover el holdout
   1983-12:1991-12 más que ninguna otra cosa probada hasta ahora.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de
Argentina; no son evidencia sobre lo que hubiera pasado.

---

## Objetivos y umbrales fuera del rango de su propia variable (causa raíz de la saturación)

Encontrado al integrar ADR 018. El agente de ADR 018 midió que un término de recuperación
`x' += rec·pos(objetivo − x)` no puede despegar una variable saturada cuando el objetivo está por
encima de la cota: +14.4 puntos por mes de empuje contra −3.9 de recuperación. La pregunta era por
qué el objetivo estaba ahí, y la respuesta es que la calibración podía ponerlo ahí.

**Lo que `a7_by_regime` dejó**, para variables que `clamp_state` acota a `[0, 100]`:

| parámetro | grupo | valor | variable comparada | cota |
|---|---|---:|---|---|
| `approval_reversion` | `peg` | **135.0** | `government_approval` | 100 |
| `approval_ref` | `peg` | **118.5** | `government_approval` | 100 |
| `approval_ref` | `control` | **109.6** | `government_approval` | 100 |
| `crime_base` | `float` | **129.2** | `crime_perception` | 100 |
| `tension_threshold` | `peg` | **117.0** | `social_tension` | 100 |
| `tension_threshold` | `float` | **110.7** | `social_tension` | 100 |

Dos formas distintas de romperse, las dos silenciosas:

- **Objetivo por encima del techo.** `rec·(objetivo − x)` nunca cambia de signo, así que empuja la
  variable contra su cota y la deja clavada ahí para siempre. Es la saturación que la sonda de
  ADR 020 midió en seis escenarios, y es en buena parte un artefacto de calibración, no una
  propiedad del modelo.
- **Umbral por encima del techo.** `pos(x − umbral)` vale siempre 0: el término está muerto y el
  coeficiente que lo multiplica no significa nada. Es por esto que el canal tensión→aprobación de
  ADR 016 §2.3 no existía bajo `a7_by_regime`, como ADR 018 reportó sin saber la causa.

**CMA-ES no hizo nada mal**: minimizó la pérdida en un espacio donde esas regiones eran alcanzables.
El arreglo es no ofrecérselas. `COMPARED_AGAINST_STATE_VAR` en `calibration/parameters.py` mapea
siete parámetros a la variable de estado que comparan y acota su rango al de esa variable, leído de
la misma tabla `ranges` que usa `clamp_state`. Es la misma razón por la que `default_risk_threshold`
ya estaba acotado a `[0, 1]` desde A3, aplicada a una clase entera que se había pasado por alto.

**Un bug adicional que esto destapó**: de las tres ramas de `build_parameter_space`, el grupo
`coefficients` era la única que **no llamaba a `_apply_physical_bounds`**. Las cotas físicas de A3 y
A5 se aplicaban a los grupos `bimonetary` y `macro` y no al más grande de los tres.

**Sobre el test de identificabilidad.** Acotar siete dimensiones de 97 corre el punto de arranque
unas milésimas en el cubo unitario, y la corrida única de CMA-ES que el test fijaba (`seed=9`) pasó
de 6/10 a 2/10. La identificabilidad no cambió: medida sobre cinco semillas de optimizador con todo
lo demás igual da `9 → 2`, `42 → 7`, `7 → 5`, `13 → 7`, `21 → 6`; mediana 6 y la 9 es el caso
atípico. El test pasa a correr tres semillas —incluida la mala, a propósito— y a exigir que la
mediana llegue al umbral. Cuesta tres corridas en vez de una y mide la propiedad en vez de una
tirada.

**Pendiente inmediato**: recalibrar. `a7_by_regime` se ajustó con el espacio viejo y con los estados
iniciales contaminados por el sesgo de anticipación que encontró ADR 019, así que sus coeficientes
arrastran las dos cosas.

---

## Cierre de la cuarta ronda: `a9_clean`, `a10_clean`, sonda `a9`, backtest `b4_clean`

Las cuatro corridas salen del mismo estado del repo: ADR 018 (recuperación política), ADR 019
(indexación como estado y dato inicial corregido), ADR 020 (sonda), más la corrección de los
objetivos y umbrales fuera de rango. **El resultado es contradictorio entre herramientas, y esa
contradicción es lo más importante que dejó la ronda.**

### Lo que mejoró: episodios curados

Validación `a10_clean` contra `a8_a7`, 50 semillas:

| prueba | `a8_a7` | `a10_clean` | real |
|---|---|---|---|
| V1, hiperinflación desde 1988-06 | 0 % **NO CUMPLIDA** | **100 % CUMPLIDA** | ocurrió |
| V2, default/colapso 1998→2002 | 66 % CUMPLIDA | **84 % CUMPLIDA** | ocurrió |
| V3, inflación 2016→2023 | 496.2 % NO CUMPLIDA | 279.6 % NO CUMPLIDA | 135 % |
| V4, mandato y derrota 2019→2023 | 383.4 %, derrota 100 % | **201.2 %, derrota 100 %** | **211 %**, derrota |

V1 no había pasado en tres rondas. Y la inflación final de V4 queda a **diez puntos** del dato real:
es la primera vez que el modelo acierta una *magnitud* de inflación y no solo su dirección.

Sonda `a9` contra la de referencia:

| arranque | antes | después | real |
|---|---|---|---|
| 2003-06 | colapso mes 120 | **150 completos** | década de crecimiento |
| 1991-04 | colapso mes 44 | mes 96 | 120 meses estables |
| 2019-12 | derrota 9/10 | **derrota 10/10** | derrota |
| 1998-01 | colapso mes 41 | **60 completos** | default en el mes 47 |

La última fila es una regresión: el modelo dejó de colapsar de más y pasó a colapsar de menos ahí.

### Lo que empeoró: generalización

Backtest `b4_clean` (321 ventanas, 1916–2022) contra `b3_a7`, **mismo protocolo**:

| objetivo | `b3_a7` | `b4_clean` | Δ |
|---|---:|---:|---:|
| Dirección de la inflación | 46.0 % | 42.7 % | **−3.3** |
| Magnitud de la inflación | 31.0 % | 22.1 % | **−8.9** |
| Crisis | 72.6 % | 66.4 % | **−6.2** |
| Golpe | 65.9 % | 58.0 % | **−8.0** |
| Régimen | 90.4 % | 91.8 % | +1.4 |
| Elección | 48.1 % | 53.6 % | +5.4 |

**El dato más duro**: en magnitud de la inflación, el brazo calibrado pasó de **40.5 % contra 21.5 %
de Aurora** a **22.4 % contra 21.8 %**. La calibración perdió por completo su única ventaja clara
sobre el modelo sin calibrar. Era el resultado que el ADR 014 citaba como "la calibración cumple lo
que optimizó"; ya no lo cumple.

### Qué significa esto, sin adornos

Cuatro episodios elegidos a mano mejoran mucho y 321 ventanas rodantes empeoran. Las lecturas
posibles, ninguna verificada todavía:

1. **La calibración anterior acertaba por la razón equivocada.** Los parámetros fuera de rango
   (`approval_reversion = 135`) y el sesgo de anticipación en los estados iniciales daban
   grados de libertad espurios que ajustaban la magnitud de la inflación. Quitarlos quitó también
   el ajuste. Bajo esta lectura, `b3_a7` sobreestimaba la capacidad real del modelo y `b4_clean`
   la mide mejor: el número honesto es el peor.
2. **Los mecanismos nuevos ayudan donde hay dato y estorban donde no.** El backtest incluye
   1916–1960 en modo anual, donde el estado inicial es el de Aurora y no un dato real; las mejoras
   de ADR 019 dependen justamente del dato inicial.
3. **Sobreajuste a los cuatro episodios.** Es la lectura más incómoda y la menos probable de las
   tres, porque ADR 018 y ADR 019 no se ajustaron contra V1–V4 sino contra mecanismos, pero no se
   puede descartar sin estratificar el backtest.

**Cómo distinguirlas**, y es el próximo trabajo: estratificar `b4_clean` contra `b3_a7` por
`frequency` (mensual contra anual interpolado) y por década. Si la caída se concentra en las
ventanas anuales, es la lectura 2 y se arregla cubriendo el estado inicial pre-1961. Si es pareja,
es la 1, y entonces el modelo siempre fue peor de lo que decíamos.

**Nada de esto se resuelve calibrando más.** Es la tercera ronda seguida en que la calibración no
supera a persistencia, y ahora además perdió su única ventaja medible.

Estos resultados describen el comportamiento de República Artificial calibrada con datos de
Argentina; no son evidencia sobre lo que hubiera pasado.

