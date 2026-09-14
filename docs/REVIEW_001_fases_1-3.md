# Revisión 001 — Fases 1 a 3 (Opus, solo lectura)

Hallazgos verificados con sondas sobre HEAD `44ef167`. Orden: más severo primero. Estado de cada uno
se actualiza en el commit que lo cierra.

| # | Severidad | Hallazgo | Fix mínimo | Estado |
|---|---|---|---|---|
| 1 | **alta** | `Perception.relationships` toma la ficha estática (`perception.py:295`); `Relationships` (consecuencias, decaimiento) nunca se lee de vuelta. `score.rel` tiene un solo valor por actor en 48 meses. Fase 5 (negociación) sería inútil. | Pasar `engine.relationships` a `build_perception` y usar `view_of(actor.id)`; la ficha solo siembra. | cerrado (Perception usa Relationships vivas via view_of) |
| 2 | **alta** | Shocks de duración 1 se borran el mismo mes (`events.py:197`) y los triggers `shock_active:` se evalúan después de `advance_month` (`game.py:170`): `scandal_response`, `general_strike_response`, `protest_wave_response` nunca aparecen (0 veces en 120 semillas). | Evaluar triggers con `set(records[-1].shocks_new) \| active_shocks`. | cerrado (triggers de dilemas suman shocks_new del mes) |
| 3 | media | El frame `scandal` de medios nunca se dispara: `recent_events` no contiene ids de shocks (`rule_based.py:528`, `simulation.py:302`). | Mirar también `perception.active_shocks` (incluyendo `shocks_new` del mes). | cerrado (medios miran active_shocks, incluye shocks_new) |
| 4 | media | Los tres medios emiten frames idénticos; `ideology.economic` no se usa (`rule_based.py:523-544`). | Desplazar umbrales por sesgo del medio respecto del partido de gobierno. | cerrado (umbrales de medios desplazados por sesgo) |
| 5 | **alta** | Las concesiones `policy_*` duran un mes y generan una propuesta fantasma inversa al mes siguiente (`simulation.py:220-238`, `last_policy`): los actores ven un recorte de transferencias después de cada concesión y renegocian para siempre (370 NEGOTIATE / 78 GRANT en 48 meses). | `pending_policy_delta` acumulativo y persistente; la propuesta se calcula desde la policy previa al bump. | cerrado (concesión persistente + cooldown de renegociación) |
| 6 | media | Test "interés vence ideología" usa −5.0 en vez de −1.0 y pasa por la razón contraria (`ideo` domina). `gov_capital` no tiene el interés `provincial_transfers`. | Asertar sobre el desglose (`w_int·int` domina) en −1.0; dar el interés a `gov_capital`. Probablemente subir `coef` de `provincial_transfers` en `interests.yaml`. | cerrado (test a −1.0 asertando que interés domina) |
| 7 | media | Determinismo no se asierta con actores (`test_determinism.py` usa `actors_enabled=False`). | Test con actores, idealmente en subproceso con otro `PYTHONHASHSEED`. | cerrado (determinismo probado entre PYTHONHASHSEED distintos) |
| 8 | baja | `config_hash` solo cubre `country.json` (`config.py:286`). | Hashear todos los archivos de datos cargados, en orden de ruta. | cerrado (hash cubre todos los datos del motor) |
| 9 | baja | El efecto relacional de `GRANT_CONCESSION` no llega al `ActionRecord` (`scheduler.py:229`); además se re-ejecuta `apply_consequences` por acción solo para loguear. | Matchear `action.actor_id in (a2, b)`; una sola pasada. | cerrado (relación de GRANT_CONCESSION ahora se loguea) |
| 10 | baja | Los `effects` de dilemas caen en el mes jugado, no en el siguiente (`game.py:245`), fuera de fase con las consecuencias de actores. Docstring y SPEC dicen "mes siguiente". | Elegir una convención: dejar el comportamiento y corregir docstring + SPEC §2 (recomendado). | cerrado (docstring y SPEC corregidos, sin tocar código) |
| 11 | baja | La escalada de gobernadores siempre excede el presupuesto de 3 acciones; la cuarta se descarta por accidente de orden. | Que `_decide_generic` elija qué 3 gasta (descarta `PUBLIC_STATEMENT` o la escalada más débil). | cerrado (actor elige qué 3 acciones gasta) |
| 12 | baja | Código muerto: `_cosine`, `_impact_audience`, `_impact_law_and_order`, `view_of`, `snapshot`; `Perception.date` siempre vacío; `sector` ausente en la percepción de empresas; nota 33 del ADR 003 desactualizada (`play --actors` default True); `allowed_ids` por `id()`. | Limpiar; poblar `date` y `sector`. | cerrado (`_cosine` removido; `date`/`sector`/nota 33/`id()` arreglados) |

Verificado y correcto: orden del turno y consumo del RNG (2 gauss + 12 uniform), todas las fórmulas
§4–§5 contra `country.json`, catálogo de shocks contra §6, `clamp_state`, `authorize()` en orden con
presupuesto por mes y cooldown de `STRIKE`, `WorldState` congelado, RNG por actor estable, los 8
tests de aceptación de SPEC §11 existen.

## Nota de cierre (commit que resuelve los 12 hallazgos)

Los 12 quedaron cerrados. Una precisión sobre el hallazgo #12: de la lista de "código muerto" se
removió `_cosine` (sin ningún caller, superado por la proyección de `ideological_fit` desde la
revisión de §12 del ADR 003), pero se **conservaron** `_impact_audience`/`_impact_law_and_order`:
siguen sin ejecutarse en la práctica (solo actores `media` tienen esos intereses, y `media` nunca
pasa por `interest_impact`), pero forman parte de la tabla `_IMPACT_FUNCS`, que cubre los 16 intereses
completos de `interests.yaml` — removerlos dejaría esos dos intereses silenciosamente sin efecto si
algún día una ficha no-`media` los declara. Mismo criterio que `Relationships.snapshot()` (ADR 003
§11.6): se deja escrito para cuando haga falta, documentado en el propio código.

Contador de tipos de acción, 48 meses, semilla 7, `TaylorPolicy`, antes/después del fix del
hallazgo #5 (`pending_policy_delta` → `concessions_delta` persistente + cooldown de 6 meses en
`RuleBasedActor`): `NEGOTIATE` 370 → 159, `GRANT_CONCESSION` 78 → 39.
