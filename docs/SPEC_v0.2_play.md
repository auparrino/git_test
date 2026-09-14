# SPEC v0.2 — Modo juego: vos sos el presidente

Extiende `SPEC_v0.1.md`. No cambia el motor: agrega un loop interactivo, dilemas disparados por
estado, un consejero por reglas y guardado de partida.

## 1. Loop mensual

```
republica play --seed 7 [--months 48] [--load simulations/game_7.json]

┌────────────────────────────────────────────┐
│ REPÚBLICA DE AURORA · MARZO 2027 · mes 3/48│
│ Inflación 2.1 % m/m (28 % anual) ▲         │
│ Desempleo 8.3 % ▲   Reservas USD 7.900 M ▼  │
│ Aprobación 47 ▼     Estabilidad 58 ▼        │
│ PIB (anual) 1.2 % ▼ Salario real 99.4 ▼     │
│ Déficit 3.4 % PIB   Deuda 61 % PIB          │
├────────────────────────────────────────────┤
│ HOY                                        │
│ ⚠ Sequía (mes 2 de 3)                      │
│ ● El Banco Central recomienda subir tasas  │
├────────────────────────────────────────────┤
│ DILEMA: Reclamo salarial de estatales      │
│  A) Conceder 10 % (gasto +0.8 % PIB)       │
│  B) Ofrecer 4 % y negociar                 │
│  C) Rechazar                               │
│ [I] instrumentos  [S] guardar  [Q] salir   │
└────────────────────────────────────────────┘
```

Cada mes:
1. Mostrar tablero (8 indicadores con flecha vs. mes anterior), shocks activos, eventos del mes anterior.
2. Mostrar **hasta 2 dilemas** disparados (sección 2). Si no hay, solo el menú de instrumentos.
3. El jugador elige una opción por dilema, y opcionalmente ajusta instrumentos (`[I]`): tasa, gasto primario, impuestos, transferencias, intervención cambiaria. Cada ajuste tiene un rango de cambio máximo por mes (tasa ±15 pp, gasto/impuestos ±2 pp PIB, transferencias ±2, intervención libre).
4. Consejero (sección 3) comenta antes de confirmar.
5. `advance_month()` con la `Policy` resultante y los efectos puntuales de las opciones.
6. Al terminar (48 meses o colapso): pantalla final con outcome, resumen y las 5 decisiones con mayor impacto estimado (diferencia contra "no hacer nada" en aprobación, calculada con una corrida contrafáctica de la misma semilla).

## 2. Dilemas (`data/scenarios/dilemmas.yaml`)

```yaml
- id: cb_recommends_hike
  title: El Banco Central recomienda subir la tasa
  text: >
    La inflación anualizada llegó a {inflation_annual:.0f} %. El presidente del Banco Central
    sostiene que las expectativas se están desanclando.
  trigger:
    all: [{var: inflation_annual, gt: 35}]
    cooldown: 6           # meses mínimos entre apariciones
    once: false
  options:
    - key: A
      label: Subir la tasa 5 puntos
      policy_delta: {interest_rate_target: 5}
    - key: B
      label: Mantener
    - key: C
      label: Bajar 3 puntos para sostener la actividad
      policy_delta: {interest_rate_target: -3}
      effects: {institutional_confidence: -1}
```

Vocabulario:
- `trigger.all` / `trigger.any`: lista de condiciones `{var, gt|lt|gte|lte|eq}` sobre el estado, las
  auxiliares (`inflation_annual`, `deficit`, `months_left`) y `shock_active:<id>`, `event_last:<id>`.
- `cooldown` (meses), `once` (bool), `priority` (int; se muestran los 2 de mayor prioridad).
- `policy_delta`: suma al instrumento (persistente hasta que el jugador lo cambie).
- `policy_set`: fija el instrumento.
- `effects`: efectos puntuales del mes siguiente sobre estado, mapeados a los términos `shock_*`
  (`approval`, `tension`, `protest`, `institutional_confidence`, `consumer_confidence`, `reserves`,
  `fiscal` (pp PIB por N meses: `{fiscal: -0.8, months: 3}`), `gdp`).
- `flags`: marcas booleanas persistentes (`promised_no_devaluation`) consultables por triggers
  (`flag:<name>`) y por la Fase 3 (memoria).

Los 14 dilemas iniciales están en el YAML; cubren: recomendación del BC, reclamo de estatales,
huelga general (respuesta), gobernadores piden fondos (sequía/inundación), presión para devaluar
(reservas bajas), FMI/crédito externo (reservas < 3000), escándalo (respuesta), presupuesto anual
(mes 10, 22, 34), ola de protestas (respuesta), boom de commodities (retenciones sí/no), crisis bancaria
(rescate), reforma impositiva (mes 6), obra pública (aprobación < 40), último año (mes 36: expansión
preelectoral sí/no).

## 3. Consejero por reglas (`engine/advisor.py`)

Devuelve una lista de `Advice(source, text, severity)`:
- **Banco Central:** compara la tasa con `TaylorPolicy`; si difiere en más de 10 pp, recomienda.
- **Ministro de Economía:** advierte si `deficit > 5`, si `public_debt > 90`, si `reserves < 3000`.
- **Jefe de Gabinete:** advierte si `approval < 35`, si `political_stability < 30`, si `protest_level > 50`.
- **Gobernadores (colectivo):** protestan si `provincial_transfers < 5`.

## 4. Guardado

`simulations/game_<seed>.json`: `{seed, month, policy, flags, cooldowns, history_path, decisions: [{month, dilemma_id, option}]}`.
El historial se sigue escribiendo al JSONL de siempre. `--load` reconstruye la partida re-ejecutando
las decisiones desde el mes 0 (determinismo), lo que también sirve de test.

## 5. Tests
- `play` con entrada simulada (`typer.testing.CliRunner`, input "A\n\n" repetido) completa 48 meses sin excepción.
- Un dilema con `cooldown 6` no reaparece antes de 6 meses; `once` aparece una vez.
- `--load` reproduce exactamente el mismo estado que la partida original.
- Los `policy_delta` respetan los rangos máximos por mes.

## Notas de implementación (Fase 2)

Ambigüedades y desviaciones resueltas al implementar `engine/dilemmas.py`, `engine/advisor.py`,
`engine/game.py` y `republica play`:

1. **`shock_cc` (nuevo término de motor).** El efecto `consumer_confidence` de una opción necesita
   viajar por el mismo mecanismo `pending`/`shock_*` que todos los demás (para aplicarse recién el
   mes siguiente, igual que `shock_pi`/`shock_conf` en `check_forced_devaluation`). El motor v0.1 solo
   soportaba un bump *directo* de `consumer_confidence` vía `ShockAggregate.field_bumps` (para shocks
   del catálogo, que se aplican el mismo mes que se sortean), sin un término acumulable equivalente.
   Se agregó `shock_cc` en `world/society.py` (`consumer_confidence_new`, sumado igual que los demás
   `shocks.term(...)`), en el mismo estilo que el resto de la sección 5.1. El resto de las claves de
   `effects` (`approval`, `tension`, `protest`, `institutional_confidence`, `reserves`, `gdp`, `fx`,
   `stability`, `inequality`, `fiscal`) se mapean 1:1 a términos `shock_*` que ya existían.
2. **`new_simulation` pública.** Se renombró `simulation._new_simulation` a `simulation.new_simulation`
   (sigue siendo la misma función; solo se le sacó el guion bajo) para que `engine/game.py::Game.new`
   la reuse sin duplicar la construcción de `Simulation`, en vez de reimplementarla.
3. **`instrument_edits` en el save.** El esquema de guardado del spec (`{seed, month, policy, flags,
   cooldowns, history_path, decisions}`) no tiene dónde registrar los ajustes manuales de instrumentos
   (`[I]`). Sin registrarlos, `--load` no podría reproducir una partida donde el jugador tocó un
   instrumento a mano: la política final quedaría guardada, pero no el camino mes a mes que hace falta
   para "re-ejecutar las decisiones desde el mes 0". Se agregó `instrument_edits: [{month, edits}]` al
   JSON de guardado, además de (no en lugar de) `decisions`.
4. **Historial JSONL del save.** "El historial se sigue escribiendo al JSONL de siempre": `Game.save`
   escribe el historial completo al lado del save, con el mismo nombre pero extensión `.jsonl`
   (`simulations/game_7.json` + `simulations/game_7.jsonl`), reusando `History.to_jsonl()` tal cual
   (mismo formato que `republica run`/`narrate`).
5. **Cooldown/`once` con un solo diccionario.** `evaluate_triggers` no recibe un parámetro aparte para
   "ya apareció una vez": reusa `cooldowns` guardando `math.inf` como mes de última aparición cuando
   `once` es verdadero, en vez de un mes finito. Como `month - inf` es `-inf`, la condición de cooldown
   nunca se vuelve a cumplir. Esto también implica que el cooldown/`once` se consume solo para los
   dilemas efectivamente mostrados (los 2 de mayor prioridad), no para los que dispararon pero no
   entraron en el tope: esos siguen disponibles el mes que viene.
6. **Topes de cambio mensual, combinados por instrumento.** La sección 1, paso 3 dice que cada ajuste
   tiene un rango de cambio máximo por mes, sin aclarar qué pasa si un dilema y una edición manual
   tocan el mismo instrumento el mismo mes. `Game.step` aplica primero todos los `policy_delta`/
   `policy_set` de los dilemas elegidos y después la edición manual, y recién al final recorta el
   cambio *neto* contra el valor con el que arrancó el mes (por instrumento, sumando todas las fuentes)
   — no cada fuente por separado. `fx_intervention` no tiene tope mensual ("intervención libre"), pero
   sí se recorta a su rango absoluto [0, 1], igual que el resto de los instrumentos a sus rangos de
   `policy_ranges` (`world/config.py`), algo que el spec no pide explícitamente pero que evita partidas
   con impuestos o tasas fuera de todo rango razonable.
7. **`months_left`.** Se define como `country.months - month + 1` (`month` = el mes que se está por
   jugar, 1-based), es decir, incluye el mes actual.
8. **8 indicadores del tablero.** El mockup de la sección 1 muestra 9 valores pero solo 7 con flecha
   (inflación, desempleo, reservas, aprobación, estabilidad, PIB, salario real); déficit y deuda se
   muestran sin flecha, como contexto. `republica play` sigue el mockup literal en vez de forzar
   exactamente 8 indicadores con flecha.
9. **Elecciones/ediciones que no aplican, se ignoran.** Si `choices`/`instrument_edits` en `Game.step`
   traen un id de dilema que no está entre los disparados ese mes, o no cambian nada, se ignoran en vez
   de levantar una excepción — mantiene `Game.load` tolerante y el menú de la CLI simple (una
   respuesta que no es exactamente A/B/C usa la primera opción; una que no es I/S/Q se toma como
   Enter/continuar).
