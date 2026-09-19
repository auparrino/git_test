# ADR 018 — Recuperación del bloque político: las cuatro variables que se clavan contra su cota

Estado: aceptado para implementar. Cierra el pendiente que dejó abierto el seguimiento de
`docs/EMERGENCE_LOG.md` ("Lo que este arreglo NO toca, y sigue siendo el problema principal":
*"darle a esas cuatro un término de recuperación, como ADR 012 §5 hizo con
`institutional_confidence` y `social_tension` pero midiéndolo contra episodios reales"*). Todo
detrás de `features.political_recovery` (default **off** para Aurora, **on** en
`data/countries/argentina/country.json`). Con el flag apagado el motor es byte a byte el de antes.

> **Numeración**: este ADR es el 018 a propósito. El 017 está tomado (calibración por régimen) y
> otros dos agentes trabajan en paralelo sobre `calibration/`, `economy.py` y `cli.py`.

Antecedentes directos: **ADR 012 §5** (recuperación de largo plazo para `institutional_confidence`
y `social_tension`) y **ADR 016** (piso de legitimidad sobre `political_stability`). Los dos
existen, corren, y los dos fallan en el mismo punto: `government_approval`, `social_tension`,
`protest_level` e `institutional_confidence` siguen clavadas contra su cota.

## 1. El hecho a explicar, medido

### 1.1 Configuración exacta de la medición

Cinco arranques reales con estado inicial del paquete, 15 semillas cada uno (1–15), calibración
`a7_by_regime` (la misma que usó la sonda de `EMERGENCE_LOG.md`, con cambio de vector en caliente
por `fx_regime_exit`), `fx_regime = pack.fx_regime_auto`, todas las features del paquete activas
(actores, congreso, negociación, cohortes, medios, memoria, elecciones), piso de legitimidad de
ADR 016 activo, **sin** `--historical-shocks` ni `--historical-exogenous`. Horizonte por arranque:
1983-12 → 72, 1991-04 → 120, 1998-01 → 60, 2003-06 → 150, 2019-12 → 48.

"Saturada" = el valor del mes toca exactamente la cota del `ranges` de `country.json`
(`government_approval` e `institutional_confidence` en el piso 0; `social_tension` y
`protest_level` en el techo 100), con tolerancia 1e-6.

### 1.2 La tabla (ANTES, 15 semillas por arranque)

| arranque | var | 1er mes en la cota (mediana) | meses saturada (mediana) | % de la corrida saturada | semillas que saturan | terminan antes del horizonte |
|---|---|---:|---:|---:|---:|---:|
| 1983-12 | `government_approval` | 4 | 0 | 0 % | 1/15 | 15/15 |
| 1983-12 | `social_tension` | - | 0 | 0 % | 0/15 | 15/15 |
| 1983-12 | `protest_level` | - | 0 | 0 % | 0/15 | 15/15 |
| 1983-12 | `institutional_confidence` | 3 | 1 | 33 % | 15/15 | 15/15 |
| 1991-04 | `government_approval` | 7 | 17 | 74 % | 15/15 | 15/15 |
| 1991-04 | `social_tension` | 6 | 17 | 77 % | 15/15 | 15/15 |
| 1991-04 | `protest_level` | 9 | 15 | 65 % | 15/15 | 15/15 |
| 1991-04 | `institutional_confidence` | 10 | 14 | 61 % | 15/15 | 15/15 |
| 1998-01 | `government_approval` | 54 | 0 | 0 % | 3/15 | 0/15 |
| 1998-01 | `social_tension` | 19 | 35 | 58 % | 15/15 | 0/15 |
| 1998-01 | `protest_level` | 28 | 3 | 5 % | 15/15 | 0/15 |
| 1998-01 | `institutional_confidence` | 60 | 0 | 0 % | 3/15 | 0/15 |
| 2003-06 | `government_approval` | 81 | 22 | 21 % | 15/15 | 15/15 |
| 2003-06 | `social_tension` | 4 | 40 | 38 % | 15/15 | 15/15 |
| 2003-06 | `protest_level` | 7 | 9 | 9 % | 15/15 | 15/15 |
| 2003-06 | `institutional_confidence` | 96 | 11 | 10 % | 15/15 | 15/15 |
| 2019-12 | `government_approval` | 22 | 10 | 31 % | 15/15 | 15/15 |
| 2019-12 | `social_tension` | - | 0 | 0 % | 0/15 | 15/15 |
| 2019-12 | `protest_level` | - | 0 | 0 % | 0/15 | 15/15 |
| 2019-12 | `institutional_confidence` | 21 | 11 | 35 % | 15/15 | 15/15 |

| arranque | outcomes | mes de fin (mediana) | horizonte | qué pasó de verdad |
|---|---|---:|---:|---|
| 1983-12 | `hyperinflation` 15 | 3 | 72 | hiperinflación en el mes 66 |
| 1991-04 | `collapse` 15 | 22 | 120 | una década de convertibilidad |
| 1998-01 | `survived` 15 | 60 | 60 | default y salida del peg en el mes 47 |
| 2003-06 | `hyperinflation` 10, `collapse` 5 | 107 | 150 | la década de mayor crecimiento reciente |
| 2019-12 | `hyperinflation` 15 | 31 | 48 | mandato completo, derrota en 2023 |

### 1.3 ¿Causa o consecuencia? Ninguna de las dos: es pérdida de información

Segunda tabla sobre las mismas corridas, con la distancia entre la primera saturación y el final:

| arranque | var | 1er mes cota | meses hasta el fin desde la 1ª cota | saturada el último mes | corridas que terminan |
|---|---|---:|---:|---:|---:|
| 1991-04 | `government_approval` | 7 | 16 | 15/15 | 15/15 |
| 1991-04 | `social_tension` | 6 | 16 | 15/15 | 15/15 |
| 1991-04 | `protest_level` | 9 | 14 | 14/15 | 15/15 |
| 1991-04 | `institutional_confidence` | 10 | 13 | 15/15 | 15/15 |
| 1998-01 | `social_tension` | 19 | 41 | 8/15 | **0/15** |
| 1998-01 | `protest_level` | 28 | 32 | 0/15 | **0/15** |
| 2003-06 | `social_tension` | 4 | **103** | 0/15 | 15/15 |
| 2003-06 | `protest_level` | 7 | 95 | 0/15 | 15/15 |
| 2019-12 | `government_approval` | 22 | 9 | 15/15 | 15/15 |
| 2019-12 | `institutional_confidence` | 21 | 10 | 15/15 | 15/15 |

Tres lecturas, todas medidas:

1. **La saturación no es suficiente para el colapso.** Desde 1998-01, `social_tension` está en el
   techo 41 meses seguidos (15/15 semillas) y **ninguna corrida termina antes del horizonte**.
2. **La saturación no es consecuencia del colapso.** Desde 1991-04 las cuatro variables tocan su
   cota entre los meses 6 y 10 y el colapso llega en el mes 22: 13 a 16 meses después.
3. **Lo que la saturación sí hace, siempre, es apagar la variable.** Desde 2003-06 la tensión
   social está en 100 durante 103 de los 107 meses de la corrida **mientras la economía crece**:
   semilla 1, meses 4 a 50, PBI +3 a +5 %, desempleo de 15,7 % a 9,8 %, inflación **negativa**
   (−1 %/mes), reservas de 14 878 a 42 276 USD M. La variable dejó de responder al mundo.

Ese tercer punto es el problema de este ADR, y es más grave que el outcome: 2003-06 es la década
de mayor crecimiento reciente, y el modelo la atraviesa con la conflictividad social clavada en su
máximo histórico posible.

### 1.4 Por qué se clavan: descomposición término a término

**1991-04, semilla 1** (el caso del `EMERGENCE_LOG`), delta mensual de `government_approval`. El
vector de coeficientes cambia de `peg` a `float` en el mes 3 (`fx_vector_switch:float`), y la tabla
usa el vector vigente en cada mes:

| mes | `e_w·Δw` | `−e_u·Δu` | `−e_pi·pos(π−pi_ref)` | `−e_t·tensión` | `+e_rev·(obj−a)` | aprob | `tension_target` | tensión | `protest_target` | protesta |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | −2.90 | +0.10 | **−13.79** | −0.00 | +0.06 | 41.9 | 78.3 | 51.1 | 6.0 | 4.7 |
| 6 | −3.43 | +0.02 | **−15.98** | −0.00 | +0.74 | 0.8 | 122.7 | 96.5 | 70.0 | 64.6 |
| 9 | −6.51 | +0.11 | **−25.67** | −0.00 | +0.77 | 0.0 | 164.2 | 100.0 | 75.1 | 100.0 |
| 15 | −6.37 | +0.03 | **−31.41** | −0.00 | +0.74 | 0.0 | 185.8 | 100.0 | 75.1 | 100.0 |
| 22 | +0.00 | −0.22 | **−41.05** | −0.00 | +0.71 | 0.0 | 207.7 | 100.0 | 75.1 | 100.0 |

Cuatro cosas que corrigen el diagnóstico de ADR 016 §2.3 para este arranque:

- **El término dominante no es la tensión: es la inflación.** `−e_pi·pos(π − pi_ref)` con
  `e_pi = 2.083` y `pi_ref = 0.894` vale −14 a −41 puntos de aprobación por mes. El término de
  tensión vale exactamente **0.00**, porque `a7_by_regime` dejó `tension_threshold = 110.70`, por
  encima del techo 100: bajo esta calibración el canal tensión→aprobación **no existe**.
- **La reversión existente es 20 a 50 veces más chica**: `+0.06` a `+0.78` por mes.
- **`tension_target` llega a 208**, muy por encima del techo 100. El empujón dominante es
  `t_p·(poverty − poverty_ref)`, y `poverty` está en el techo de su propio `ranges`: la saturación
  política de 1991-04 es *aguas abajo* de una saturación macro.
- **`protest_level` se queda en 100 aunque su propio `protest_target` valga 75.** Lo sostiene
  `shock_protest`, que viene de las acciones de actores (`engine/consequences.py`: `CALL_PROTEST`
  y `STRIKE`), no de la fórmula §5.4.

**2003-06, semilla 1** (el caso interesante), misma descomposición: `−e_pi` vale **0.00** (hay
deflación), `e_w·Δw` y `−e_u·Δu` son **positivos** todos los meses, la aprobación cae igual de 50 a
10 en 65 meses, y `tension_target` baja lentamente de 145 a 100 sin que la tensión se despegue del
techo hasta el mes 32. Acá no hay ninguna fuerza macro adversa: hay un objetivo estructuralmente
por encima del techo y ningún término que empuje de vuelta.

### 1.5 Por qué la recuperación de ADR 012 §5 no alcanza (medido, con los valores vigentes)

ADR 016 §2.5 ya lo había reportado con `a5b_macro`. Con `a7_by_regime` el diagnóstico cambia de
forma pero no de conclusión, y conviene dejarlo escrito por grupo de régimen:

| canal §5 | grupo `peg` (1983-12, 1991-04, 1998-01) | grupo `float` (2003-06) | grupo `control` (2019-12) |
|---|---|---|---|
| `t_rec` | 0.0152 | 0.0219 | 0.0205 |
| `recovery_inflation_max` | **1.44 %/mes** | 4.76 %/mes | 2.59 %/mes |
| `recovery_unemployment_max` | 27.69 % | 29.84 % | **5.37 %** |
| `ic_rec` / `ic_target_base` | 0.0235 / 48.52 | 0.0185 / **103.90** | 0.0060 / **99.94** |

- En el grupo `peg` la compuerta de `t_rec` **nunca se abre**: la inflación simulada de 1991-04 va
  de 7 a 20 %/mes, siempre por encima de 1,44.
- En el grupo `float` **sí se abre** (deflación de −1 %/mes desde el mes 3 de 2003-06), y aun así
  no alcanza: `t_rec·pos(100 − 60.59) = 0.86` puntos por mes contra
  `t_adj·(tension_target − tensión) = 0.359·(140 − 100) = +14.4`. Pierde 17 a 1.
- En el grupo `control` la compuerta de `t_rec` se cierra por el lado del **desempleo**
  (`recovery_unemployment_max = 5.37 %`, y el desempleo argentino de 2019-12 arranca en 10,4 %).
- `ic_target_base` por encima de 100 en dos de los tres grupos convierte a `ic_rec` en un empujón
  hacia arriba constante — que aun así deja a `institutional_confidence` en 0 el 35 % de la corrida
  desde 2019-12, porque `ic_pi·pos(π − pi_ref_conf)` lo domina cuando la inflación sube.

**Conclusión del diagnóstico.** La recuperación de §5 falla por tres motivos distintos y
separables: (a) sus compuertas son **umbrales absolutos** sobre inflación y desempleo, y las dos
recuperaciones argentinas documentadas arrancaron con inflación **alta pero cayendo** (abril de
1990: 11,4 %/mes, contra 95,5 % en marzo) y con desempleo **alto pero bajando** (2003: 15,7 %);
(b) sus coeficientes los fija la calibración, que los puede desactivar sin saberlo; (c) no cubre
`government_approval` ni `protest_level`.

## 2. Diseño

### 2.1 La forma

Cuatro términos con la forma literal de ADR 012 §5 (`x' += rec · pos(objetivo − x)`, condicionado
al estado), aplicados **después** de las secciones 5.3/5.4 (`world/society.py`) y 5.6/5.8
(`world/politics.py`), sobre el valor ya calculado del mes y **antes** del `clamp`:

```
si el mecanismo esta enganchado:
    government_approval'      += ap_rec · pos(ap_obj      − government_approval')
    institutional_confidence' += ic_rec · pos(ic_obj      − institutional_confidence')
    social_tension'           -= ts_rec · pos(social_tension' − ts_obj)
    protest_level'            -= pr_rec · pos(protest_level'  − pr_obj)
```

Las dos primeras empujan hacia arriba sólo si están por debajo del objetivo; las dos últimas hacia
abajo sólo si están por encima. Ninguna puede cruzar su objetivo: `pos(...)` garantiza que el
término se apaga exactamente en el valor de referencia. **El mecanismo no puede subir la aprobación
por encima de 18,85 ni bajar la tensión por debajo de 35**: no es un empujón, es un piso y un techo
blandos.

### 2.2 La compuerta: alivio macro, no nivel macro

El mecanismo se engancha cuando hay `relief_months` meses **consecutivos** de alivio. Un mes es de
alivio si **no hay ruptura aguda** y además hay **desinflación** o **reactivación**:

- **Ruptura aguda**: los mismos cuatro marcadores de ADR 016 §3 (hiperinflación sostenida por
  `lf_rupture_months` meses sobre `lf_rupture_inflation`, crisis bancaria activa, `sovereign_default`
  activo, `fx_regime_exit` en el mandato). Reusarlos es deliberado y es el primer candado contra la
  amnistía: **el mecanismo está apagado exactamente en las dos situaciones en que la Argentina real
  sí tuvo salida anticipada** (1989 y 2001).
- **Desinflación**: `inflation ≤ relief_pi_ratio · media(inflación de los relief_window meses
  previos)`. Es un criterio **relativo**, no un umbral absoluto: es el diagnóstico §1.5 (a).
- **Reactivación**: `gdp_growth ≥ relief_growth_min` **y** `unemployment ≤ unemployment(t−1)`.

Cualquier mes sin alivio reinicia la racha a cero.

### 2.3 Los coeficientes y de dónde salen

Todos viven en `src/republica/world/recovery.py::PoliticalRecoveryCoefficients`, un dataclass con
docstring por campo, separado de `MacroCoefficients` a propósito (ver §4).

| campo | valor | ancla |
|---|---:|---|
| `aprobacion_objetivo` | **18.85** | El proxy electoral que el propio paquete usa para el estado inicial (`50 + 20·(voto_oficialismo − 0.45)/0.15`, ADR 011 §2) aplicado al **peor resultado de un oficialismo post-1983**: Kirchner, 21,64 % en la primera vuelta de 2003 (`initial_states["2003-06"].government_approval = 18.850931…`, fuente `politics/sources/electorAr_presi/arg_presi_gral2003.csv`). La aprobación presidencial argentina post-1983 nunca se quedó en cero; su piso medible con la regla del propio proyecto es 18,85. |
| `aprobacion_rec` | **0.10** | `politics/events.csv`: tiempo de la ruptura aguda a la normalidad política. 1989-05 (`hyperinflation`) → 1991-04 (`currency_regime_change`, convertibilidad) = 23 meses; 2001-12 (`crisis_banking`, corralito) → 2003-05 (`presidency_start` Kirchner tras `election_presidential`) = 17 meses. Mediana 20. Cerrar el 90 % de la brecha en 20 meses ⇒ `1 − 0.1^(1/20) = 0.109`, redondeado a 0.10. Coincide con las tres recuperaciones de aprobación documentadas fuera del repo (post-1989, post-2002, post-2009), de 20 a 28 meses del piso al pico. |
| `confianza_objetivo` | **57.3** | `history/vdem_argentina.csv`, `v2x_libdem` **mínimo de la era democrática** (2011 = 0.573) × 100. Es exactamente la transformación que `scripts/build_argentina_initial_states.py` ya usa para el `institutional_confidence` inicial de las ocho fechas reales. |
| `confianza_rec` | **0.009** | Mismo archivo, `v2x_rule`: mínimo 1990 = 0.455, recuperación a 0.698 en 2000, referencia 1984 = 0.831. Cierra el 65 % de la brecha en 120 meses ⇒ `1 − 0.35^(1/120) = 0.0087`. Es un orden de magnitud más lento que la aprobación, y eso es el dato: la confianza institucional argentina tardó **una década** en volver de su piso. |
| `tension_objetivo` | **35.0** | Valor que el paquete asume para `social_tension` en las **ocho** fechas reales (`initial_states[*].social_tension`, con `assumed: true` y la nota "no hay serie de conflictividad social continua descargada"), y que coincide con el `tension_base` de Aurora. **No hay serie real detrás**: es una convención del repo, declarada como tal. |
| `protesta_objetivo` | **15.0** | Ídem `protest_level` (`assumed: true`, y `protest_ref` de Aurora). **No hay serie real detrás.** |
| `tension_rec` | **0.06** | **Valor de diseño**, acotado por el proxy de `politics/events.csv`: entre 1983-12 y 2023-12 (481 meses) hay **6 episodios de conflicto social agudo** — cuatro `coup` (levantamientos carapintadas 1987-04, 1988-01, 1988-12, 1990-12) y dos `crisis_banking` (saqueos de 1989-05, corralito de 2001-12) — y los shocks de conflicto del propio catálogo (`general_strike`, `protest_wave` en `data/countries/argentina/shocks.json`) duran **1 mes**. O sea: el techo debería ocuparse del orden del 1 % de los meses, no del 38 al 77 % medido. Una excursión al techo que decae a la mitad entre 6 y 12 meses implica `rec ∈ [0.056, 0.109]`; 0.06 es el extremo conservador de esa banda. Seis eventos no identifican un coeficiente: el valor exacto es de diseño. |
| `protesta_rec` | **0.09** | **Valor de diseño**, mismo proxy, escalado por la relación de velocidades que el propio spec le da a las dos variables en Aurora (`pr_adj/t_adj = 0.3/0.2 = 1.5`): `0.06 × 1.5 = 0.09`. |
| `relief_pi_ratio` | **0.70** | Los dos episodios reales de desinflación: 1990-04, 11,4 %/mes contra una media de 78,8 en 1990-01..03 (ratio **0.14**); 2002-09, 1,4 %/mes contra 3,0 en 2002-06..08 (ratio **0.47**). 0.70 es deliberadamente **más laxo** que los dos, para que la compuerta no dependa de reproducir exactamente la violencia de esas caídas. Serie: `history/inflation_cpi_monthly_linked.csv`. |
| `relief_window` | **6** | **Valor de diseño**: media móvil semestral, mitad de un año, suficiente para que el ratio no lo decida un mes suelto. |
| `relief_growth_min` | **0.0** | Canal de reactivación, anclado en 2009-2011: PBI −5,9 % (2009) → +10,1 % (2010) → +6,0 % (2011) con desempleo bajando. La condición es "crece y el desempleo no sube", no "crece mucho". |
| `relief_months` | **3** | **Valor de diseño**. Los dos episodios reales sugieren más (del inicio del alivio al punto de giro político: 1990-04 → 1991-04 = 12 meses; 2002-09 → 2003-05 = 8 meses), pero con 8–12 el mecanismo no llegaría a engancharse nunca en una ventana de 48 meses. Se elige 3 y se declara el sesgo: **este valor hace al mecanismo más permisivo de lo que los dos episodios reales justifican**. |

### 2.4 Lo que este diseño NO hace, dicho antes de medir

- **No toca los objetivos** (`tension_target`, `protest_target`, `stability_target`). El hallazgo de
  §1.4 —`tension_target = 208` en 1991-04, por encima del techo— es un problema de calibración del
  lazo tensión↔protesta que ADR 016 ya dejó registrado como pendiente de `calibration/*`. Un
  término de recuperación de la forma de §2.1 **no puede** despegar una variable cuyo objetivo está
  40 a 100 puntos por encima del techo: `ts_rec·pos(100 − 35) = 3.9` contra
  `t_adj·(208 − 100) = 38.8`. Se deja escrito acá para que la medición de §6 no se lea como sorpresa.
- **No toca `shock_protest`**, que es lo que sostiene la protesta en 100 en 1991-04 (§1.4).
- **No toca la macro.** Si `poverty` está en el techo y la inflación en 20 %/mes, el bloque político
  tiene razón en estar en el piso.

## 3. Hipótesis registrada (escrita ANTES de tocar código)

Todo con la configuración de §1.1 (15 semillas, `a7_by_regime`) salvo los discriminantes, que usan
los coeficientes **sin calibrar** del paquete y 20 semillas, igual que `tests/test_macro_regime.py`.

### 3.1 Mejoras esperadas

| # | Predicción | Antes | Umbral |
|---|---|---:|---|
| H1 | 2003-06: % de la corrida con `social_tension` en el techo (mediana) | 38 % | **≤ 20 %** |
| H2 | 1998-01: % de la corrida con `social_tension` en el techo (mediana) | 58 % | **≤ 30 %** |
| H3 | 2019-12: % de la corrida con `government_approval` en el piso (mediana) | 31 % | **≤ 15 %** |
| H4 | 2019-12: % de la corrida con `institutional_confidence` en el piso (mediana) | 35 % | **≤ 25 %** |
| H5 | 2003-06: `protest_level` en el techo (mediana) | 9 % | **≤ 5 %** |

### 3.2 Predicción negativa, registrada de antemano

| # | Predicción | Umbral |
|---|---|---|
| H6 | **1991-04 no mejora materialmente**: la saturación de las cuatro variables baja **menos de 15 puntos porcentuales**, y el `collapse` sigue ocurriendo en **≥ 10/15** semillas. | como se dice |

H6 no es una excusa preparada: es la consecuencia aritmética de §2.4 (`tension_target = 208`) y de
§1.4 (la saturación de 1991-04 es aguas abajo de `poverty` en el techo y de una inflación que
crece). Si H6 **falla** —es decir, si 1991-04 mejora mucho— el mecanismo es más fuerte de lo que su
diseño dice y hay que sospechar de él, no festejarlo.

### 3.3 Los tres discriminantes que no pueden romperse

| # | Discriminante | Antes | Umbral |
|---|---|---:|---|
| D1 | Hiperinflación alcanzable desde **1988-06** en ≤ 18 meses (ADR 012 §7 test 2a) | 20/20 | **≥ 50 %** |
| D1b | Hiperinflación **no espuria** desde 2003-06 (test 2b) | 0/20 | **0** |
| D2 | Desde **1998-01 con `--fx-regime peg`**, 54 meses: colapso, hiperinflación o `sovereign_default` activo | 19/20 (95 %) | **≥ 50 %** |
| D2b | ↳ `fx_regime_exit` en ese escenario (test 3c) | 17/20 | **≥ 50 %** |
| D3 | Los **seis** tests de ADR 012 §7 (`tests/test_macro_regime.py`) | verdes | **verdes** |
| D4 | Flag apagado: goldens de `test_country_pack_argentina.py`, `test_macro_regime.py` y `test_collapse_recovery.py` | — | **byte a byte** |

**D2 es el candado.** Un mecanismo que salve a todos los gobiernos es peor que el actual. Si H1–H5
se cumplen pero D2 no, el mecanismo es una amnistía general y hay que reportarlo como tal y
apagarlo. La compuerta de ruptura de §2.2 es lo único que separa los dos casos, exactamente como en
ADR 016 §3.

## 4. Implementación

Detrás de `features.political_recovery` (ausente/false = comportamiento de siempre):

- **`src/republica/world/recovery.py`** (módulo nuevo): `PoliticalRecoveryCoefficients` (dataclass
  congelado, docstring por campo, `from_dict` pensado para que la calibración lo tome después),
  `RecoveryTracker` (estado entre meses: ventana de inflación y racha de alivio, fuera de
  `WorldState`), `RecoveryContext` (lo que las dos etapas leen del mes), y las funciones puras
  `relief_this_month`, `advance_recovery`, `recover_social`, `recover_political`.
- **`src/republica/world/society.py`**: un parámetro nuevo `recovery: RecoveryContext | None = None`
  (default `None` = comportamiento de siempre). Con contexto enganchado aplica los dos términos de
  §5.3/§5.4.
- **`src/republica/world/politics.py`**: ídem para §5.6/§5.8.
- **`src/republica/engine/simulation.py`**: `Simulation` gana `political_recovery_enabled`,
  `recovery_coefficients` y `recovery_tracker`; `advance_month` arma el `RecoveryContext` justo
  después del bloque macro (es donde están los cuatro marcadores de ruptura) y lo pasa a las dos
  etapas; `run()` toma `political_recovery: bool | None = None` (`None` ⇒ lee
  `country.features["political_recovery"]`). Doble compuerta, igual que ADR 016: el mecanismo
  necesita el flag **y** `macro_coefficients` (de ahí salen los marcadores de ruptura).
- **`data/countries/argentina/country.json`**: `features.political_recovery = true`.

Los coeficientes **no** van en `MacroCoefficients` a propósito: ese dataclass es el vector de
CMA-ES (`calibration/parameters.py::MACRO_TUNABLE` se arma con todos sus campos `float`), y
`src/republica/calibration/*` es de otro agente en esta ronda. Vivir en un dataclass propio deja
`MACRO_TUNABLE` intacto y deja el grupo listo para que la calibración lo agregue cuando quiera
(ver "Lo que hace falta de otros módulos").

## 5. Tests

`tests/test_political_recovery.py`: no-op bit a bit con el flag apagado; default del flag por
paquete (off en Aurora, on en Argentina); unit tests de la forma de los cuatro términos y de que
ninguno cruza su objetivo; unit tests de la compuerta (los cuatro marcadores de ruptura la cierran;
desinflación y reactivación la abren por separado; un mes sin alivio reinicia la racha); H1–H5 y H6
sobre las corridas reales; D1/D2 como regresión.

## Notas de implementación

Implementado como se diseñó en §2/§4, **sin retunear un solo coeficiente**: los doce valores de la
tabla de §2.3 son los que se registraron antes de medir. El resultado es en su mayor parte
**negativo**, y se reporta como tal.

### Resultado en una línea

**El mecanismo funciona como está escrito y casi no mueve nada.** La compuerta discrimina
perfectamente (0 % de meses enganchados en 1991-04, 72 % en 2003-06), los cuatro términos se
aplican, los tres discriminantes quedan **idénticos** — y la saturación baja entre 3 y 10 puntos
porcentuales donde el diseño esperaba 18 a 30. De las cinco hipótesis de mejora registradas
**ninguna se cumple**; la predicción negativa registrada (H6) **sí** se cumple. La causa está
medida en "Por qué no alcanza", y no es la compuerta: es que el objetivo de la variable está por
encima de su propia cota.

### La tabla de saturación, antes y después

Misma configuración de §1.1, 15 semillas, semilla por semilla. Lo único que cambia entre columnas
es `features.political_recovery`.

| arranque | var | % saturada ANTES | % saturada DESPUÉS | 1er mes ANTES | 1er mes DESPUÉS |
|---|---|---:|---:|---:|---:|
| 1983-12 | `government_approval` | 0 % | 0 % | 4 | 4 |
| 1983-12 | `institutional_confidence` | 33 % | 33 % | 3 | 3 |
| 1991-04 | `government_approval` | 74 % | **74 %** | 7 | 7 |
| 1991-04 | `social_tension` | 77 % | **77 %** | 6 | 6 |
| 1991-04 | `protest_level` | 65 % | **65 %** | 9 | 9 |
| 1991-04 | `institutional_confidence` | 61 % | **61 %** | 10 | 10 |
| 1998-01 | `social_tension` | 58 % | **55 %** | 19 | 19 |
| 1998-01 | `protest_level` | 5 % | 5 % | 28 | 28 |
| 2003-06 | `government_approval` | 21 % | 20 % | 81 | 83 |
| 2003-06 | `social_tension` | 38 % | **28 %** | **4** | **4** |
| 2003-06 | `protest_level` | 9 % | 6 % | **7** | **101** |
| 2003-06 | `institutional_confidence` | 10 % | 10 % | 96 | 96 |
| 2019-12 | `government_approval` | 31 % | **27 %** | 22 | 23 |
| 2019-12 | `institutional_confidence` | 35 % | **32 %** | 21 | 22 |

Outcomes: **no cambia ninguno** salvo una semilla de 2003-06 que pasa de `collapse` a
`hyperinflation` (10/5 → 11/4). Los meses de fin (mediana) son idénticos en los cinco arranques.

| # | Predicción registrada | Umbral | Medido | |
|---|---|---|---:|---|
| H1 | 2003-06, `social_tension` en el techo | ≤ 20 % | **28 %** | ❌ |
| H2 | 1998-01, `social_tension` en el techo | ≤ 30 % | **55 %** | ❌ |
| H3 | 2019-12, `government_approval` en el piso | ≤ 15 % | **27 %** | ❌ |
| H4 | 2019-12, `institutional_confidence` en el piso | ≤ 25 % | **32 %** | ❌ |
| H5 | 2003-06, `protest_level` en el techo | ≤ 5 % | **6 %** | ❌ (por 1 punto) |
| H6 | 1991-04 **no** mejora (< 15 pp) y colapsa ≥ 10/15 | — | **0,0 pp**, `collapse` **15/15** | ✅ |

El único resultado cualitativo digno de mención es la fila `protest_level` de 2003-06: el primer
mes en el techo pasa del **7 al 101**. La protesta deja de tocar su cota durante los primeros ocho
años de la corrida — es decir, durante la década de crecimiento. Ese es exactamente el defecto que
el ADR se propuso arreglar, y en esa variable y ese escenario se arregló.

### Los tres discriminantes: **idénticos**

20 semillas, coeficientes **sin calibrar** del paquete, misma configuración que
`tests/test_macro_regime.py`:

| # | Discriminante | Umbral | Flag OFF | Flag ON |
|---|---|---|---:|---:|
| D1 | Hiperinflación desde 1988-06 ≤ 18 m (ADR 012 §7 test 2a) | ≥ 50 % | 20/20 | **20/20** |
| D1b | Hiperinflación espuria desde 2003-06 (test 2b) | 0 | 0/20 | **0/20** |
| D2 | 1998-01 + `peg`, 54 m: colapso, hiper o `sovereign_default` | ≥ 50 % | 19/20 (95 %) | **19/20 (95 %)** |
| D2b | ↳ `fx_regime_exit` (test 3c) | ≥ 50 % | 17/20 | **17/20** |
| D3 | ADR 012 §7 test 5 (2003-06 → 2015-12 `survived`) | ≥ 80 % | 20/20 | **20/20** |
| D3b | Los seis tests de `tests/test_macro_regime.py` | verdes | verdes | **verdes** |
| D4 | Flag off, goldens de los tres archivos | byte a byte | — | **byte a byte** |

D2 en su forma fuerte: **el escenario 1998-01 + `peg` no cambia en una sola semilla**, porque la
salida forzada de la convertibilidad ocurre en 17/20 y el `sovereign_default` en el resto, y
cualquiera de los dos mantiene la compuerta de ruptura cerrada por el resto del mandato. El
mecanismo **no es una amnistía general**: está estructuralmente apagado en los escenarios de
ruptura.

### Por qué no alcanza: la aritmética, medida

La compuerta **no** es el cuello de botella. Meses enganchados (5 semillas por arranque):

| arranque | meses de alivio | % | meses enganchados | % |
|---|---:|---:|---:|---:|
| 1983-12 | 3 / 15 | 20 % | 0 | **0 %** |
| 1991-04 | 3 / 111 | 3 % | 0 | **0 %** |
| 1998-01 | 102 / 300 | 34 % | 78 | 26 % |
| 2003-06 | 411 / 549 | 75 % | 397 | **72 %** |
| 2019-12 | 101 / 158 | 64 % | 78 | 49 % |

En 2003-06 el mecanismo corre en 72 % de los meses y la tensión baja sólo 10 puntos porcentuales de
saturación. La razón es la que el ADR anticipó en §2.4, ahora con números medidos:

```
empuje hacia el techo    t_adj · (tension_target − 100) = 0.359 · (140 − 100) = +14.4 / mes
término de recuperación  ts_rec · pos(100 − 35)         = 0.06  ·  65         =  −3.9 / mes
```

Pierde **3,7 a 1**. En 1991-04 la relación es peor todavía (`tension_target = 208` ⇒ +38.8/mes) y
además la compuerta nunca se abre. **Un término de la forma `x' += rec · pos(objetivo − x)` no
puede despegar una variable cuyo objetivo está por encima de su propia cota**, salvo con un `rec`
que ninguna ancla sostiene.

**Barrido del multiplicador** sobre los cuatro `*_rec` a la vez (15 semillas, mediana del % de la
corrida saturada):

| ×mult | `tension_rec` | 2003-06 tensión | 2003-06 protesta | 1998-01 tensión | 2019-12 aprob. | 2019-12 confI | 1991-04 tensión |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 (off) | — | 38 % | 9 % | 58 % | 31 % | 35 % | 77 % |
| **×1 (enviado)** | **0.06** | 28 % | 6 % | 55 % | 27 % | 32 % | 77 % |
| ×2 | 0.12 | 15 % | 6 % | 55 % | 27 % | 30 % | 77 % |
| ×4 | 0.24 | **10 %** | 5 % | 55 % | 27 % | 30 % | 77 % |

Tres lecturas:

1. **La banda anclada llega justo hasta el borde.** El ADR registró para `tension_rec` la banda
   [0.056, 0.109] (vida media de 6 a 12 meses desde el techo) y eligió el extremo conservador
   (0.06). El extremo **opuesto** de esa misma banda (×1.8) ya cumpliría H1. Se deja **0.06**: era
   el valor registrado antes de medir, y mover el coeficiente al otro extremo de la banda después
   de ver el resultado sería seleccionar contra la medición, que es justo lo que
   `PLAN_ARGENTINA.md` §0 regla 3 prohíbe. Queda escrito para la próxima ronda, con el número.
2. **1998-01 y la aprobación de 2019-12 no se mueven con ningún multiplicador.** No es magnitud: en
   1998-01 la compuerta sólo se engancha el 26 % de los meses, y en 2019-12 la aprobación publicada
   no es la de §5.6 (ver el punto siguiente).
3. **1991-04 es plano en todo el barrido**, como predijo H6.

### Hallazgo estructural: la aprobación publicada no es una variable que el motor integre

Con `features.cohorts` prendido —el caso de Argentina— `government_approval` **no** es el
`approval_new` de §5.6: `engine/simulation.py` lo pisa con la suma ponderada de
`CohortState.approval_c` (`world/cohorts.py::step_cohorts`), que se recalcula cada mes desde el
estado por cohorte. Un término de recuperación aplicado al agregado **no se acumula**: se vuelve a
aplicar de cero todos los meses sobre el valor que las cohortes produjeron.

Este ADR lo mitiga aplicando el término **dos veces** (una sobre el `approval_new` de §5.6, que es
lo que ven `congress_support` y `political_stability` de §5.9; otra sobre el agregado por cohorte,
que es lo que se publica y lo que `step_politics`/`step_society` leen como `prev` al mes
siguiente). Es una mitigación, no un arreglo: para que la recuperación de la aprobación se integre
de verdad, el término tiene que entrar **por cohorte** en
`world/cohorts.py::step_cohorts`, que está fuera del alcance de este ADR. **Ese es el motivo
principal por el que H3 falla**, y es una corrección barata y bien localizada para la próxima
ronda.

### Lo que este ADR NO arregla, medido (para la próxima ronda)

1. **El objetivo por encima de la cota es el problema real.** `tension_target` llega a 208 en
   1991-04 y a 145 en 2003-06; `protest_target` a 75 con la protesta en 100. Mientras los objetivos
   de §5.3/§5.4 no estén acotados o el lazo `t_pr`/`pr_t`/`pr_a` no sea contractivo, cualquier
   mecanismo aguas abajo parchea un síntoma. ADR 016 ya lo había dejado escrito; este ADR lo
   **cuantifica** (la relación de fuerzas es 3,7 a 1 en el mejor escenario y 10 a 1 en el peor). Es
   trabajo de `src/republica/calibration/*`, de otro agente en esta ronda.
2. **`crime_perception` es la variable más saturada del modelo, y entra directo en la aprobación.**
   Medido en esta misma configuración (15 semillas, mediana del % de la corrida en el techo 100):
   **97 % en 2003-06**, 77 % en 1991-04, 70 % en 1998-01. Y
   `world/cohorts.py::step_cohorts` usa `crime_term = crime_perception − 50`, o sea que clavada en
   100 es un **−50 constante disfrazado de variable** en la aprobación publicada. El mecanismo de
   este ADR **ya la cubre** (`recover_crime`, quinta variable), pero **se envía apagada**
   (`crime_rec = 0.0`): está fuera del alcance asignado y no hay ninguna serie de percepción de
   inseguridad (`calibration/initial_states.py` la marca `assumed`). Sensibilidad medida:
   `crime_rec = 0.06` no cambia nada (97 % → 97 %); `crime_rec = 0.5` la baja a **24 %** en
   2003-06 y a 57 % en 1998-01, sin cambiar los outcomes. Misma aritmética que la tensión: el
   `crime_target` también supera el techo.
3. **También hay saturación contra la cota "buena", en el bloque económico-social.** Medido acá:
   desde 2019-12, `poverty` está en su **piso (0 %)** el 35 % de la corrida y `real_wage` en su
   **techo (200)** el 29 %; desde 2003-06, `inequality` está en su piso (20) el 42 %. Una pobreza
   de 0 % sostenida es tan implausible como una aprobación de 0 sostenida, y ninguna de las tres se
   toca acá: viven en `world/economy.py`/§5.2, fuera del alcance.
4. **El término de aprobación tiene que entrar por cohorte** (ver el hallazgo estructural de
   arriba).
5. **`relief_months = 3` es más permisivo de lo que los dos episodios reales justifican** (8 y 12
   meses). Se eligió así para que el mecanismo pudiera engancharse dentro de una ventana de 48
   meses, y se declara. Si la próxima ronda sube el coeficiente `rec`, conviene subir también
   `relief_months` para no aflojar las dos cosas a la vez.

### Detalles de implementación

- **Dónde se arma el contexto.** `engine/simulation.py::advance_month`, **después** del bloque
  macro y **antes** de `step_society`. Es el único punto del mes donde están a la vez los cuatro
  marcadores de ruptura (`macro_events`, `sim.active_shocks`, `sim.macro_state`) y la economía de
  `t+1` ya calculada. Se llama **una vez por mes**: `advance_recovery` muta el `RecoveryTracker`, y
  `step_politics` reusa el mismo `RecoveryContext` que `step_society`.
- **Dónde se aplica cada término.** `social_tension` **antes** de §5.4 (para que la protesta del
  mismo mes vea la tensión ya aliviada por `pr_t`), `protest_level` después de §5.4,
  `government_approval` e `institutional_confidence` después de §5.8 y **antes** de §5.9 (para que
  `stability_target` vea los valores recuperados por `st_a` y `st_i`), y `government_approval` otra
  vez sobre el agregado por cohorte. Todo **antes** del `clamp` del motor.
- **Doble compuerta.** El mecanismo corre sólo con `features.political_recovery` **y**
  `macro_coefficients` (de ahí salen `lf_rupture_inflation`/`lf_rupture_months`,
  `banking_crisis_months_left` y el `sovereign_default`). Aurora falla las dos.
- **`fx_exit_month` se comparte con ADR 016, a propósito.** Es el mismo campo de `Simulation`, lo
  fija el primero de los dos bloques que corra en el mes (mismo valor en los dos casos) y se
  **reinicia en cada elección celebrada**: un gobierno nuevo no arrastra la ruptura cambiaria del
  anterior, ni para el piso de legitimidad ni para esta compuerta. Es la semántica de ADR 016 §3
  ("por el resto del mandato en curso"), aplicada sin duplicar estado.
- **Contador de inflación alta propio.** `RecoveryTracker.high_pi_months` duplica a
  `Simulation.rupture_high_pi_months` de ADR 016 a propósito: aquel sólo se actualiza con
  `features.legitimacy_floor` prendido, y los dos flags son independientes. Por la misma razón no
  se reusa `world/events.py::legitimacy_rupture_active`: necesita un `LegitimacyContext` que el
  motor arma **después** de la política del mes.
- **Los coeficientes no son calibrables hoy, y no por accidente.** Viven en un dataclass propio
  (`PoliticalRecoveryCoefficients`) en vez de en `MacroCoefficients`, que es el vector de CMA-ES
  (`calibration/parameters.py::MACRO_TUNABLE` se arma con todos sus campos `float`). Agregar doce
  campos ahí habría ampliado el espacio de parámetros de `src/republica/calibration/*` —de otro
  agente en esta ronda— sin avisar. `from_dict` está listo para que lo tomen cuando quieran.
  Cubierto por `test_adr_018_coefficients_stay_out_of_the_calibration_vector`.
- **`engine/simulation.py` se tocó, y es el único archivo fuera del alcance asignado.** El encargo
  listaba `world/politics.py`, `world/society.py`, `world/events.py`, `world/recovery.py`,
  `country.json`, los docs y los tests. El flag tiene que llegar de `country.features` a las dos
  etapas, y el `RecoveryContext` sólo se puede armar donde están los marcadores de ruptura: eso
  vive en `advance_month`. El cambio es de **97 líneas, todas nuevas**, ninguna modificada: tres
  campos en `Simulation`, un bloque en `advance_month`, dos `kwargs` en las llamadas existentes, la
  reaplicación sobre `cohort_approval` y ocho líneas en `run()`. No se tocó ninguno de los archivos
  que el encargo marcó como de otros agentes (`world/economy.py`, `world/regime.py`,
  `calibration/*`, `backtest/*`, `ai/*`, `cli.py`). `world/events.py` estaba en la lista de
  permitidos y **no** hizo falta tocarlo: ver "Contador de inflación alta propio".
- **`country.json` sólo trae el flag booleano**, no los coeficientes: leer un bloque nuevo del
  paquete requiere tocar `world/config.py::Country` y `world/countries.py`, que quedaron fuera del
  alcance. Los valores de §2.3 son los defaults del dataclass. Hoy no hay diferencia; cuando haya
  que sobrescribirlos por país habrá que hacer ese cambio (queda en "Lo que hace falta de otros
  módulos").

### Lo que hace falta de otros módulos (no tocados por este ADR)

- `src/republica/calibration/*`: acotar los objetivos de §5.3/§5.4 o recalibrar
  `t_pr`/`pr_t`/`pr_a` con la restricción de que el lazo tensión↔protesta sea contractivo (punto 1
  de arriba). Es **la** corrección; todo lo demás es aguas abajo. Y, si se quiere, agregar el grupo
  `political_recovery` al espacio de parámetros: `PoliticalRecoveryCoefficients.from_dict` ya está.
- `src/republica/world/cohorts.py`: el término de recuperación de la aprobación tiene que entrar
  **por cohorte** en `step_cohorts` para que se integre en vez de reaplicarse cada mes.
- `src/republica/world/config.py` + `world/countries.py`: leer
  `country.json → political_recovery.coefficients` para poder sobrescribir los doce valores por
  país sin tocar código.
- `src/republica/world/economy.py`: `poverty` en su piso y `real_wage` en su techo (punto 3).
- `src/republica/cli.py`: un `--political-recovery / --no-political-recovery`, simétrico con
  `--legitimacy-floor` de ADR 016. `run()` ya toma el parámetro; falta sólo la opción de la CLI.

### Tests

`tests/test_political_recovery.py`, 31 tests: no-op bit a bit con el flag apagado y con un paquete
que no declara el feature; doble compuerta (Aurora con el flag forzado a `True` es idéntica a
Aurora); defaults por paquete; forma de los cinco términos (ninguno cruza su referencia, identidad
sin contexto o sin enganche, tamaño del primer paso igual a `rec · brecha`); la compuerta completa
(los cuatro marcadores de ruptura, el canal de desinflación con los números reales de abril de
1990, el canal de reactivación con los de 2009-2011, el reinicio de la racha, el enganche recién en
`relief_months`, la ventana acotada); el efecto medido congelado como regresión, **incluida H6**
(0 enganches y `collapse` 15/15 desde 1991-04); y los cuatro discriminantes.

`uv run ruff check . && uv run ruff format --check .` limpios. Suite completa:
**569 passed, 1 skipped, 2 xfailed**.
