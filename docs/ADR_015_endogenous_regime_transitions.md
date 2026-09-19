# ADR 015 — Transiciones de régimen endógenas (modelo de riesgo mensual)

Estado: **aceptado e implementado** (flag `features.regime_endogenous_transitions`, default `False`).
Depende de ADR 011 §3 (máquina de estados del régimen) y ADR 014 (backtest secuencial).

Resuelve el pendiente de `docs/PLAN_ARGENTINA.md` §7: *"Régimen: 0 % de acierto cuando la ventana
arranca en golpe o democracia restringida — el modelo persiste el régimen inicial; falta un mecanismo
de transición endógeno"*.

## 1. Diagnóstico con números

Fuente: `data/countries/argentina/backtest/b1_a5b/windows.csv`, objetivo `regime`, 364 filas
(182 ventanas × 2 brazos; sólo ventanas mensuales, `t0 ≥ 1961`, ver ADR 014).

| `regime_mode_initial` (real) | N | aciertos | tasa |
|---|---:|---:|---:|
| `coup` | 18 | 0 | **0,0 %** |
| `restricted_democracy` | 24 | 0 | **0,0 %** |
| `dictatorship` | 72 | 26 | **36,1 %** |
| `democracy` | 250 | 238 | **95,2 %** |
| **total** | **364** | **264** | **72,5 %** |

Las tasas son IDÉNTICAS en los dos brazos (`calibrated` 132/182, `aurora` 132/182): el régimen no
lee los coeficientes económicos (ya documentado en ADR 014).

**La causa real no es "el modelo persiste el régimen inicial": es que el modelo NUNCA CONOCE el
régimen inicial.** `engine/simulation.py::run()` hace `regime_state = RegimeState()` — y
`RegimeState.mode` tiene default `"democracy"`. Toda ventana del backtest arranca la máquina de
estados en `democracy`, aunque el régimen real en `t0` sea una dictadura, un golpe o una democracia
restringida. El ADR 014 §1 dice *"Régimen inicial real de `regimes.csv`"*, pero ese dato nunca se
cablea al motor. Verificación directa sobre `windows.csv`: las 12 fallas del estrato `democracy`
(250 − 238) son exactamente 6 ventanas por brazo — `1973-01` h48, `1974-01` h24/h48 y `1975-01`
h12/h24/h48, las seis con objetivo en 1976-1979 (golpe/dictadura reales); todas las demás aciertan
porque el modelo dice `democracy` y la realidad también. Es decir: **el modelo de hoy es, para este objetivo, el predictor constante "democracia
siempre"**, y su 72,5 % agregado es enteramente el peso de la posguerra de 1983 en la muestra.

Además, la máquina de estados de ADR 011 §3 tiene tres límites que impiden reproducir el ciclo real
aunque se le diera el modo inicial correcto:

1. **Golpe endógeno con umbrales duros**: `stability < 20` **y** `confidence < 30` **y**
   `rng < propensión de la década`. Es un gate binario (0 riesgo por encima del umbral, riesgo
   plano por debajo), y la propensión es constante dentro de cada década.
2. **Salida de dictadura sólo si `social_tension > 70`**: sin dependencia de la duración. Una
   dictadura con tensión contenida dura para siempre; una con tensión alta sale el primer mes.
3. **`restricted_democracy` no existe en el motor.** Está en `politics/regimes.csv` (74 de 214 años,
   el modo MÁS frecuente de la serie argentina) pero no en `REGIME_MODES`.

## 2. Decisión de diseño

Detrás del flag nuevo `features.regime_endogenous_transitions` (default `False`, byte a byte
idéntico apagado):

**(a) El modo inicial se siembra del dato real.** `world/regime.py::initial_regime_state(regimes_csv,
year, month)` lee `politics/regimes.csv` y devuelve el modo del motor y los `months_in_mode` ya
transcurridos en ese período. No es hacer trampa: es el mismo estatuto que el `initial_state`
económico real que el backtest ya le da al modelo (ADR 014 §1). Lo que se predice es el modo en
`t0 + h`, no el de `t0`.

**(b) `restricted_democracy` pasa a ser un QUINTO modo del motor**, no un alias de `democracy`.

Se evaluaron las dos opciones del enunciado:

| Opción | Consecuencia |
|---|---|
| Mapear a `democracy` con una bandera que sube la propensión de golpe | `scoring.py` binariza `mode == "democracy"`, y `regimes.csv` codifica `restricted_democracy` como NO democracia. El estrato quedaría **garantizado en 0 %** por construcción: el modelo diría "democracia" cuando la realidad dice "no". |
| Quinto modo | Cuesta una entrada en `REPRESSION_BY_MODE`, `elections_allowed` y `congress_active`, todas triviales. Concuerda con la binarización que el propio repo ya declaró correcta. |

Se elige el **quinto modo**. `data/countries/argentina/politics/REGIME_CROSSCHECK.md` §3 ya zanjó
conceptualmente la cuestión: *"`restricted_democracy` es, por definición de este dataset, «hay
elecciones pero con fraude o proscripción» — exactamente lo que V-Dem llama autocracia electoral
(`v2x_regime = 1`)"*, y el test de `tests/test_argentina_politics.py` usa esa binarización (B).
El modo nuevo tiene elecciones y Congreso activos (las hubo: 1931, 1937, 1963 son elecciones reales)
pero `repression = 0.35` (proscripción, fraude, estado de sitio) y su propio hazard de golpe, mucho
más alto que el de la democracia plena (§3).

Como `REGIME_MODES` es público, se agrega `REGIME_MODES_ENDOGENOUS` (los cinco) y se deja
`REGIME_MODES` intacto: con el flag apagado el modo nuevo es inalcanzable.

**(c) Hazard mensual por transición.** Para cada mes, cada transición `A → B` tiene una probabilidad

```
p = 1 − exp( −[ H(t+1) − H(t) ] · m )      H(t) = (t / λ)^k      (Weibull acumulado)
m = clamp( exp( offset + Σ βᵢ·zᵢ ), m_min, m_max )
```

con `t = months_in_mode`, `λ`/`k` **estimados por máxima verosimilitud de los datos reales** (§3) y
`βᵢ` coeficientes de DISEÑO (sólo el signo está justificado; ver §4). `p` se recorta a
`max_monthly_hazard`. Las covariables se centran para que 0 sea el estado "neutro" de Aurora (el
`offset` NO es 0: corre el centro del multiplicador al estado típico MEDIDO de cada modo — ver §4 y
el punto 4 de las Notas de implementación):

| `zᵢ` | definición |
|---|---|
| `z_stability` | `(political_stability − 50) / 50` |
| `z_confidence` | `(institutional_confidence − 50) / 50` |
| `z_tension` | `(social_tension − 50) / 50` |
| `z_inflation` | `clamp(inflation, −5, 50) / 10` (inflación MENSUAL en %) |
| `z_growth` | `clamp(gdp_growth, −20, 20) / 10` |
| `z_repression` | `repression − 0.85` (centrada en el nivel de `dictatorship`) |

**(d) Grafo de transiciones bajo el flag:**

```
democracy ──coup hazard──► coup ──1 mes (fijo, ADR 011)──► dictatorship
restricted_democracy ──coup hazard (más alto)──► coup
dictatorship ──exit hazard──► transition ──handover hazard──► democracy | restricted_democracy
```

El destino de la salida (`democracy` o `restricted_democracy`) se sortea con una logística en la
duración del régimen de facto (§3.4). `democracy → restricted_democracy` sin golpe y
`restricted_democracy → democracy` (liberalización) existen como coeficientes pero valen **0 por
defecto**: la serie real no los sostiene (§3.5).

**(e) `coup_propensity` del calendario deja de gobernar el golpe cuando el flag está prendido** (el
hazard lo reemplaza), con UNA excepción deliberada: `coup_propensity == 0.0` —lo que produce
`--regime-mode democracy`— sigue desactivando el golpe endógeno por completo, para no romper la
garantía de ADR 011 §9 test 4 ("con propensión 0, nunca").

## 3. Parámetros estimados de los datos reales

Todo lo de esta sección lo reproduce `uv run python scripts/fit_regime_hazards.py` (en el repo).
Las duraciones se reconstruyeron a mano de `politics/events.csv` (filas `presidency_start`,
`election_presidential` y `kind == "coup"` EXITOSAS) y se cotejaron contra `politics/regimes.csv`.

### 3.1 Duraciones usadas

**Seis regímenes de facto** (del golpe a la asunción del gobierno civil electo), ninguno censurado:

| # | Golpe | Gobierno civil | meses | traspaso (elección→asunción) | neto |
|---|---|---|---:|---:|---:|
| 1 | 1930-09-06 Uriburu | 1932-02-20 Justo | 17 | 1931-11-08 → 3 | 14 |
| 2 | 1943-06-04 GOU | 1946-06-04 Perón | 36 | 1946-02-24 → 3 | 33 |
| 3 | 1955-09-16 Libertadora | 1958-05-01 Frondizi | 32 | 1958-02-23 → 2 | 30 |
| 4 | 1962-03-29 Guido | 1963-10-12 Illia | 19 | 1963-07-07 → 3 | 16 |
| 5 | 1966-06-28 Rev. Argentina | 1973-05-25 Cámpora | 83 | 1973-03-11 → 2 | 81 |
| 6 | 1976-03-24 Proceso | 1983-12-10 Alfonsín | 93 | 1983-10-30 → 1 | 92 |

La columna "neto" es la que ajusta el hazard de `dictatorship`, y la de "traspaso" la del modo
`transition` del motor: **si no se restara, los mismos meses se contarían dos veces** (en el motor la
duración de un régimen de facto es `coup` + `dictatorship` + `transition`).

**Siete períodos civiles** (de la asunción al golpe que los termina; el último, censurado):

| Período | meses | termina en | codificación `regimes.csv` |
|---|---:|---|---|
| 1916-10 Yrigoyen | 167 | golpe 1930-09 | `democracy` |
| 1932-02 Justo | 136 | golpe 1943-06 | `restricted_democracy` |
| 1946-06 Perón | 111 | golpe 1955-09 | `democracy` (1946-48) / `restricted` (1949-54) |
| 1958-05 Frondizi | 47 | golpe 1962-03 | `restricted_democracy` |
| 1963-10 Illia | 33 | golpe 1966-06 | `restricted_democracy` |
| 1973-05 Cámpora/Perón | 34 | golpe 1976-03 | `democracy` |
| 1983-12 Alfonsín → 2023-12 | 480 | **censurado** | `democracy` |

El período 1946-1955 se asigna entero a `democracy` para el ajuste (el modo de la asunción, y el
único de los siete que cambia de codificación a mitad de camino): decisión declarada, mueve la tasa
de la democracia plena de 0,00379 a lo sumo unas décimas.

### 3.2 Estimaciones por máxima verosimilitud

| Transición | n | eventos | exposición | hazard constante | Weibull λ | Weibull k | LR vs. exp. |
|---|---:|---:|---:|---:|---:|---:|---:|
| `dictatorship` → `transition` (neto) | 6 | 6 | 266 m | 0,02256 /mes | **49,51** | **1,514** | 1,40 |
| `transition` → civil (traspaso) | 6 | 6 | 14 m | 0,42857 /mes | **2,59** | **3,803** | **8,97** |
| `democracy` → `coup` | 4 | 3 | 792 m | 0,00379 /mes | **263,17** | **0,893** | 0,06 |
| `restricted_democracy` → `coup` | 3 | 3 | 216 m | 0,01389 /mes | **81,49** | **1,705** | 1,13 |

(χ²₁ al 5 % = 3,84.)

**Resultado negativo, declarado**: el test de razón de verosimilitud **NO rechaza** el hazard
constante contra el Weibull en tres de las cuatro transiciones (1,40 / 0,06 / 1,13 < 3,84). Con n=6,
n=4 y n=3 spells no hay potencia para establecer dependencia de la duración. **Se usan igual las
estimaciones Weibull** —son las estimaciones puntuales, y la dependencia de la duración es
justamente el mecanismo que este ADR necesita (un régimen viejo y agotado debe salir antes que uno
recién instalado, que es lo que distingue 1982 de 1977)— pero queda escrito que **la forma
`k ≠ 1` no está estadísticamente establecida**: sólo el traspaso la rechaza claramente (k = 3,8,
LR = 8,97), y ahí es casi tautológico (los seis traspasos duraron entre 1 y 3 meses).

La diferencia empírica que sí es grande y la que más importa para el pendiente: **la democracia
restringida tiene 3,7 veces el riesgo de golpe de la democracia plena** (0,01389 vs. 0,00379
mensual). Los tres períodos `restricted_democracy` terminaron los tres en golpe, en 216 meses; los
tres períodos `democracy` cerrados también, pero en 792 meses de exposición.

### 3.3 Probabilidades acumuladas implicadas (base, multiplicador 1)

| | 2 años | 4 años | 6 años | 8 años | 10 años |
|---|---:|---:|---:|---:|---:|
| salida de `dictatorship` | 0,284 | 0,615 | 0,828 | **0,934** | 0,978 |
| golpe desde `democracy` | 0,111 | **0,197** | 0,270 | 0,334 | 0,391 |
| golpe desde `restricted_democracy` | 0,117 | 0,333 | 0,555 | 0,733 | 0,855 |

### 3.4 Destino de la salida: `democracy` vs. `restricted_democracy`

De las seis salidas, tres van a `restricted_democracy` (1932 Justo, 1958 Frondizi, 1963 Illia) y tres
a `democracy` (1946 Perón, 1973 Cámpora, 1983 Alfonsín). Un 50/50 constante sería la lectura
inmediata, pero los seis casos se separan **perfectamente por duración**:

| destino | duraciones (meses) |
|---|---|
| `restricted_democracy` | 17, 19, 32 |
| `democracy` | 36, 83, 93 |

Historia interpretable: un régimen de facto corto entrega el poder en sus propios términos (con el
peronismo o el radicalismo proscriptos); uno largo llega agotado y no puede imponer condiciones.
Se implementa como logística en la duración:

```
P(restricted | D) = 1 / (1 + exp((D − 34) / 8))
```

`D₅₀ = 34` meses es el punto medio de la separación (32 y 36) y `s = 8` meses es un suavizado
**elegido a mano, no ajustado**: la máxima verosimilitud de una logística perfectamente separada
diverge (`s → 0`, un escalón). Con `s = 8` los dos casos más cercanos al corte (32 y 36 meses)
quedan en 0,56 y 0,44 en vez de 1 y 0.

**Advertencia explícita, no enterrada**: esto es una separación perfecta sobre **seis** observaciones.
No es un resultado estadístico; es una regularidad descriptiva con una historia detrás. Se expone
como dos coeficientes (`restricted_duration_midpoint`, `restricted_duration_smoothing`) para que la
calibración pueda revisarlos, y `restricted_duration_smoothing → ∞` recupera el 50/50 constante.

### 3.5 Lo que los datos dicen que NO pasa

- **`restricted_democracy → democracy` nunca ocurrió** en la serie: los cuatro períodos de democracia
  restringida (1932-42, 1949-54, 1958-61, 1963-65) terminaron los cuatro en golpe, ninguno en una
  apertura hacia democracia plena. `restricted_to_democracy_monthly` queda en **0,0**.
- **`democracy → restricted_democracy` sin golpe** ocurrió una vez (1948 → 1949, la recodificación
  del segundo peronismo). Una observación en 1008 meses no sostiene una tasa;
  `democracy_to_restricted_monthly` queda en **0,0**.

Ambos son campos del dataclass, no constantes: si una calibración futura los quiere distintos de 0,
puede.

## 4. Coeficientes de covariables (DISEÑO, no estimados)

Con seis golpes y seis dictaduras no hay grados de libertad para estimar un Cox con cinco
covariables. Los `βᵢ` fijan el SIGNO y un orden de magnitud; la tasa BASE es lo que está estimado.
Queda escrito acá para que nadie los lea como medidos.

| coeficiente | valor | signo justificado por |
|---|---:|---|
| `coup_beta_stability` | −1,6 | ADR 011 §3 ya usaba `stability` como gate del golpe |
| `coup_beta_confidence` | −1,2 | ídem `institutional_confidence` |
| `coup_beta_tension` | +0,8 | conflicto social como antesala del golpe |
| `coup_beta_inflation` | +0,25 | 1975-76 (Rodrigazo → Proceso) |
| `coup_beta_growth` | −0,20 | recesión como agravante |
| `exit_beta_tension` | +0,9 | ADR 011 §3 ya usaba `social_tension > 70` como ÚNICA salida |
| `exit_beta_repression` | −1,0 | más represión, más capacidad de permanecer |
| `exit_beta_inflation` | +0,25 | Rodrigazo 1975, hiper del final del Proceso |
| `exit_beta_growth` | −0,25 | crecimiento sostiene al régimen |
| `exit_beta_confidence` | 0,0 | sin signo claro a priori; se deja en 0 |

Los tres `*_log_offset` NO son de diseño ni cero: se calculan para que el multiplicador valga
exactamente 1 en el estado TÍPICO que el motor produce bajo cada modo (medido, no elegido: ver el
punto 4 de las Notas de implementación). Sin ese centrado la tasa base estimada —que es una tasa
INCONDICIONAL— quedaría multiplicada por ~2 y las duraciones del modelo dejarían de parecerse a las
seis reales.

Guardas: `m ∈ [0,01, 5,0]` y `p ≤ 0,5` mensual, para que ninguna combinación extrema de estado
(el motor puede llevar `social_tension` a 100 bajo represión) produzca un hazard absurdo.

## 5. Hipótesis registrada ANTES de correr

Medición: `python -m republica.backtest --country argentina --calibration a5b_macro
--from 1930 --to 1983 --horizons 12,24,48 --seeds 15 --workers 2`, con y sin el flag. Sólo las
ventanas mensuales (`t0 ≥ 1961`, ADR 014) puntúan `regime`: 23 orígenes × 3 horizontes × 2 brazos.

Composición del objetivo en esa muestra (calculada de `regimes.csv` antes de correr): **las 9
configuraciones que arrancan en `coup` y las 12 que arrancan en `restricted_democracy` tienen las 21
un objetivo NO-democracia**; el estrato `dictatorship` tiene 23 de 36 no-democracia.

| Estrato | Antes (`b1_a5b`) | Hipótesis |
|---|---:|---|
| `coup` | 0,0 % | **≥ 80 %** |
| `restricted_democracy` | 0,0 % | **≥ 90 %** |
| `dictatorship` | 36,1 % | **≥ 60 %** |
| `democracy` | 95,2 % | **no baja más de 5 pp respecto del brazo con el flag apagado de la MISMA muestra** |

(La columna "antes" son las tasas de `b1_a5b`, que cubre 1961-2022. La muestra de esta medición
llega sólo hasta 1983, así que el punto de partida de cada estrato se vuelve a medir corriendo el
mismo backtest con el flag apagado; los tres primeros estratos no tienen orígenes después de 1983 y
no cambian, el de `democracy` sí.)

Razonamiento de cada una: `coup` y `restricted_democracy` sólo necesitan que el modelo NO esté en
`democracy` en `t0+h`, y sembrado el modo inicial real eso es casi automático (de ahí los umbrales
altos); `dictatorship` exige además que el hazard de salida acierte el MOMENTO (13 de 36 objetivos
son democracia, y caen todos en 1972-1973 y 1981-1983), por eso el umbral más bajo; `democracy`
puede empeorar porque el hazard de golpe ahora puede disparar donde antes nunca disparaba —el
riesgo que se acota en 5 pp.

Riesgo conocido de antemano: el estrato `dictatorship` es el único donde la hipótesis puede fallar
por el lado del mecanismo (y no del sembrado), porque depende de la forma Weibull que §3.2 declara
no establecida.

## 6. Tests (DoD)

`tests/test_regime_transitions.py`, todo junto < 60 s:

1. Flag apagado → `step_regime` idéntico a antes (goldens de `test_macro_regime.py` y
   `test_country_pack_argentina.py` intactos, más una comparación directa de trayectorias).
2. Desde `dictatorship` con `months_in_mode` grande: P(salida acumulada a 8 años) > 80 %
   (Monte Carlo, semillas fijas).
3. Desde `democracy` con estabilidad alta: P(golpe a 4 años) < 5 %.
4. Ventana 1976-03 → 1984 sin golpes forzados: ≥ 50 % de semillas vuelven a `democracy` antes de
   1984-12.
5. Ventana que arranca en 1930-09 (`coup`): el modo a +24 meses no es `coup`.

## Notas de implementación

Implementado: `world/regime.py` (todo lo nuevo), `world/countries.py::load_country_pack`
(parámetro `regime_transitions`), `engine/simulation.py::run` (ningún camino nuevo: el flag viaja
dentro del `RegimeCalendar` que `run` ya recibía), `cli.py` (`--regime-transitions/
--no-regime-transitions` en `run` y `validate`), `validation/argentina.py`,
`backtest/{__main__,runner}.py`, `scripts/fit_regime_hazards.py`, `tests/test_regime_transitions.py`.

**El flag viaja dentro de `RegimeCalendar`, no como parámetro nuevo de `run()`.** `run()` ya tiene
17 parámetros opcionales; agregarle dos más (`regime_transitions` y
`regime_transition_coefficients`) hubiera ensanchado una firma que ADR 011/012 ya declararon
sobrecargada. `RegimeCalendar` gana cinco campos con default (`endogenous_transitions=False`,
`transition_coefficients=None`, `initial_mode="democracy"`, `initial_months_in_mode=0`,
`initial_de_facto_months=0`) más dos métodos (`resolved_coefficients()`,
`initial_regime_state()`), y `run()` sólo cambia `RegimeState()` por
`regime_calendar.initial_regime_state()` y le pasa los coeficientes a `step_regime`. Con el flag
apagado esos defaults reproducen literalmente el código anterior: `initial_regime_state()` devuelve
`RegimeState()` y `resolved_coefficients()` devuelve `None`, que es el camino de ADR 011 sin tocar
el RNG.

**El golpe forzado del calendario sigue teniendo prioridad sobre el hazard** (con el flag prendido y
`--regime-mode auto`, un golpe de `events.csv` ocurre igual). En el backtest eso es irrelevante:
`runner.py::backtest_regime_calendar` deja `forced_coup_months` vacío SIEMPRE (ADR 014, "Desviación
deliberada del calendario"), y el flag nuevo no lo toca — el mecanismo corre sin golpes forzados,
como pide esa nota.

**Siembra del modo inicial y granularidad anual.** `regimes.csv` es ANUAL. `initial_regime_state`
resuelve el modo del año de `t0` y cuenta `months_in_mode` desde enero del primer año del bloque
contiguo del mismo modo, con una excepción: un bloque `dictatorship` se extiende hacia atrás sobre
el año `coup` que lo precede (así el Proceso arranca en 1976-01 y no en 1977-01, y `months_in_mode`
de 1982-01 da 72 en vez de 60). Consecuencia declarada: una ventana que arranca en `1962-01` entra
al motor en modo `coup` aunque el golpe real fue en marzo, y el motor pasa a `dictatorship` en
1962-02. Es el error de redondeo que impone el dato anual, no una decisión.
`civil_war_or_state_building` (28 años, todos ≤ 1861) se mapea a `dictatorship` — sin elecciones ni
Congreso es lo más cercano de los cinco modos; no afecta a ninguna ventana puntuada (el backtest
puntúa `regime` sólo desde 1961).

**Sorteos de RNG.** Con el flag prendido, `step_regime` consume SIEMPRE 2 valores de
`rng.random()` por mes (0 en `coup`, que es determinista), INCLUSO cuando el coeficiente que
gobierna ese sorteo vale 0 — así el flujo del RNG no depende del valor de los coeficientes y una
calibración futura puede comparar vectores sin que se le mueva la secuencia de shocks debajo. Con
el flag apagado no se consume ninguno (de ahí que el golden siga valiendo). Contrapartida honesta:
al correr el RNG, el flag cambia los shocks aleatorios de cada semilla, y por eso
`inflation_direction` se mueve ±2 pp sin que haya ninguna relación causal (ver la medición).

**`TRANSITION_MAX_MONTHS = 24` sobrevive como tope** con el flag prendido, pero prácticamente nunca
liga: con λ = 2,59 / k = 3,8 el traspaso dura 1-4 meses. Se deja porque está en el texto del ADR 011.

### Medición: backtest con y sin el flag

```
python -m republica.backtest --country argentina --calibration a5b_macro \
    --from 1930 --to 1983 --horizons 12,24,48 --seeds 15 --workers 2 --no-plots \
    --run-id b2_regime_probe_off   [--regime-transitions -> b2_regime_probe_on]
```

162 ventanas por brazo, 116 s cada corrida. Sólo las 23 mensuales (`t0` 1961-1983) puntúan
`regime`, como anticipaba §5: 23 × 3 horizontes × 2 brazos = **138 filas**. IC 95 % de Wilson.
Salidas en `data/countries/argentina/backtest/b2_regime_probe_{off,on}/`.

| `regime_mode_initial` | N | antes (flag off) | después (flag on) | Δ | hipótesis §5 |
|---|---:|---|---|---:|---|
| `coup` | 18 | 0,0 % [0,0-17,6] | **100,0 % [82,4-100,0]** | +100,0 pp | ≥ 80 % — **cumplida** |
| `restricted_democracy` | 24 | 0,0 % [0,0-13,8] | **100,0 % [86,2-100,0]** | +100,0 pp | ≥ 90 % — **cumplida** |
| `dictatorship` | 72 | 36,1 % [26,0-47,6] | **63,9 % [52,4-74,0]** | +27,8 pp | ≥ 60 % — **cumplida** |
| `democracy` | 24 | 50,0 % [31,4-68,6] | **50,0 % [31,4-68,6]** | 0,0 pp | no baja 5 pp — **cumplida** |
| **total `regime`** | **138** | **27,5 % [20,8-35,5]** | **72,5 % [64,5-79,2]** | **+44,9 pp** | — |

Las cuatro hipótesis registradas se cumplen. El estrato `democracy` de esta muestra son sólo los
orígenes 1973, 1974, 1975 y 1983 (los de 1984-2022 quedan fuera del rango `--to 1983`), por eso
parte de 50,0 % y no del 95,2 % de `b1_a5b`: de las 12 ventanas por brazo que quedan, las 6 con
objetivo en 1976-1979 son exactamente las que el predictor constante "democracia siempre" falla
(§1), y son la mitad de la muestra en vez de 6 sobre 125. Con el flag prendido el modelo tampoco
produce el golpe de 1976 en esas seis: no gana nada, pero tampoco pierde.

Los otros objetivos del backtest, para que se vea que la mejora no salió de mover otra cosa:

| objetivo | N | flag off | flag on | Δ |
|---|---:|---:|---:|---:|
| `coup` | 138 | 58,7 % | 59,4 % | +0,7 pp |
| `crisis` | 231 | 76,2 % | 76,6 % | +0,4 pp |
| `inflation_direction` | 231 | 47,6 % | 45,5 % | **−2,2 pp** |
| `inflation_magnitude` | 231 | 34,2 % | 33,8 % | −0,4 pp |

### Lo que NO mejora, con los números

**1. El objetivo `coup` no se mueve (+0,7 pp).** Esperable y no se tocó nada para taparlo: `coup`
premia producir un golpe DENTRO de la ventana, y el hazard desde `democracy` es, por construcción,
la frecuencia histórica (0,0038 mensual). Un modelo que acierta la frecuencia base no acierta las
fechas.

**2. `inflation_direction` pierde 2,2 pp.** El flag cambia cuántos valores consume `step_regime` del
RNG, así que la secuencia de shocks aleatorios de cada semilla se corre: parte de esos ±2 pp es
ruido de resorteo, no una degradación causal. No se investigó más allá porque el objetivo de este
ADR es el régimen; queda anotado como costo observado, no como cero.

**3. El estrato `dictatorship` se queda en 63,9 %, y el patrón de fallas es perfectamente nítido.**
Con el flag prendido el modelo acierta **23 de 23** ventanas cuyo objetivo NO es democracia y falla
**13 de 13** cuyo objetivo SÍ lo es (1969-h48, 1970-h48, 1971-h24/h48, 1972-h12/h24, 1979-h48,
1980-h48, 1981-h24/h48, 1982-h12/h24/h48). Es decir: bajo el flag el modelo es un predictor
"el régimen de facto persiste", exacto al revés del "democracia siempre" de §1.

La causa NO es el hazard de salida, y conviene decirlo con el dato: **estas corridas terminan solas
mucho antes del horizonte**. Medido sobre las mismas ventanas (15 semillas, brazo `aurora`):

| ventana | meses corridos (mediana) | `outcome` | modo final (15 semillas) |
|---|---:|---|---|
| 1972-01 h=24 y h=48 | 17 | 10 `collapse`, 5 `hyperinflation` | 6 dict., 6 dem., 3 trans. |
| 1979-01 h=24 y h=48 | 12 | 11 `collapse`, 4 `hyperinflation` | 10 dict., 3 trans., 1 restr., 1 dem. |
| 1982-01 h=24 y h=48 | 10 | 13 `hyperinflation`, 2 `collapse` | 8 dict., 4 dem., 3 trans. |

`h=24` y `h=48` son literalmente la MISMA corrida (termina antes de los 24 meses en los dos casos) y
`scoring.py` lee el último registro, así que "el modo a 48 meses" es en realidad el modo al mes 10-17.
El hazard de salida ni llega a jugarse: con λ = 49,5 y k = 1,5, a 10 meses la probabilidad acumulada
de salida es 0,08. Cerrar ese 63,9 % no pide un hazard distinto sino que el motor no termine por
`collapse` a los 10 meses en 1977-1983 — un pendiente que `PLAN_ARGENTINA.md` §7 ya tiene abierto por
su cuenta ("Revisar la terminación por `collapse`"), y que no se toca acá.

En 1982-01, la ventana más cercana a darse vuelta, 4 de 15 semillas ya están en `democracy` al mes 10
y 3 más en `transition`: la mayoría (el criterio de `scoring.py`) queda en 8/15 dictadura. No se
ajustó ningún coeficiente para dar vuelta ese 8-7, que es exactamente el tipo de cosa que la regla de
honestidad de `PLAN_ARGENTINA.md` §0.3 prohíbe.

**4. Los coeficientes se centraron en dos pasos, y el segundo usa el motor.** Las tasas base del §3
son INCONDICIONALES (el MLE sobre toda la historia), así que el multiplicador tiene que valer 1 en el
estado TÍPICO, no en un 50/50/50 arbitrario. El estado típico se midió corriendo el motor con el flag
prendido y los offsets en 0 (t0 = 1961..1983, h = 48, 5 semillas) y tomando la mediana por modo:

| modo | `political_stability` | `institutional_confidence` | `social_tension` | `inflation` | `gdp_growth` |
|---|---:|---:|---:|---:|---:|
| `democracy` | 30,4 | 0,0 | 59,3 | 11,9 | 1,9 |
| `restricted_democracy` | 42,6 | 8,2 | 54,9 | 6,0 | 1,8 |
| `dictatorship` | 24,2 | 0,0 | 66,6 | 8,1 | 1,3 |

De ahí salen `coup_log_offset_democracy = −2,236`, `coup_log_offset_restricted = −1,434` y
`exit_log_offset = −0,471`. Dos consecuencias que hay que leer juntas: (a) es una iteración sola, no
un punto fijo — el estado típico con los offsets puestos difiere algo del medido con offsets en 0;
(b) `institutional_confidence` da **0,0 en la mediana** bajo `democracy` y `dictatorship` en
1961-1983, es decir está contra su piso: como covariable no discrimina nada en ese período, sólo
aporta una constante que el offset absorbe. Sin este centrado el multiplicador quedaba en ~2 bajo
dictadura y la mediana de duración de las dictaduras del modelo caía a 24 meses (contra 38 del ajuste
y 17-93 del dato real) — se corrigió antes de medir nada, no después de ver el resultado.
