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
