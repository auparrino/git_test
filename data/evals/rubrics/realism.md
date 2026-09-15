# Rúbrica de `political_realism` (ADR 007 secc. 2/3)

El juez recibe el `emergence` report de una corrida (`republica.engine.emergence`)
más hasta 10 negociaciones (`kind: "negotiation"`) de esa misma corrida, y
puntúa **1 a 5** qué tan plausibles son las coaliciones y negociaciones que
produjo el agente evaluado, comparadas con lo que produciría un analista
político humano mirando la misma corrida.

No hay número "correcto" (no hay baseline por reglas exacto: `rules` mismo
es el sistema de referencia informal, ver `ADR 007 secc. 1`: "cada métrica
tiene un baseline por reglas"; acá el baseline es la corrida `rules` del
mismo escenario, puntuada con la misma rúbrica). El juez debe fijarse en:

1. **Coherencia ideológica de las alianzas** (1 punto): ¿los actores que se
   alían/niegan tienen ideologías compatibles/incompatibles con lo que hacen
   (`FORM_ALLIANCE`/`BREAK_ALLIANCE`), o el agente arma alianzas
   arbitrarias sin relación con `ideology`/`interests`?
2. **Consistencia de intereses en las negociaciones** (1 punto): ¿las
   concesiones pedidas (`requested_concession`) y las contraofertas
   (`counter_concession`) se corresponden con el rol/interés del actor
   (un gobernador pide `restore_transfers`, un sindicato `wage_bonus`), o
   son incoherentes con su ficha?
3. **Progresión temporal creíble** (1 punto): ¿las coaliciones evolucionan
   de forma gradual y explicable entre meses (rupturas tras eventos
   negativos, acercamientos tras concesiones), o cambian sin razón aparente
   mes a mes?
4. **Diversidad de estrategias entre actores** (1 punto): ¿actores distintos
   (sindicato vs. empresa vs. gobernador) reaccionan de forma distinta ante
   el mismo escenario, o todos convergen a la misma `private_strategy`
   (señal de un agente que no diferencia roles)?
5. **Ausencia de comportamiento absurdo** (1 punto): ¿ninguna
   negociación/alianza contradice abiertamente el interés declarado del
   actor (p. ej. un actor que pide una concesión que le perjudica), y las
   magnitudes (montos, intensidades) son razonables para el contexto
   descrito en el `emergence` report?

**Puntaje final**: suma de los 5 puntos anteriores (`score` en 1-5, nunca 0:
un `score` de 1 es el piso, "ninguna de las 5 señales presente pero corrida
válida"). `justification` (2-4 oraciones) debe citar al menos un ejemplo
concreto (un actor, una alianza o negociación puntual) que sostenga el
puntaje, no una impresión general.

Formato de salida: `RubricScore {score: int, justification: str}` (ADR 007
secc. 3, `ai/schemas`-like, ver `evals/judge.py::RubricScore`).
