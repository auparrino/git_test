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
