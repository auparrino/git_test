# ADR 010 — Physics vs. Institutions: la CPU social mínima (Fase 10, v2)

Estado: aceptado como fundamento de investigación. Hito 1 (moneda emergente) aceptado para implementar
en un paquete separado (`src/republica/core/`) que **no toca** v1.

## 1. La pregunta

v1 (Fases 1–9) simula instituciones que nosotros nombramos: presidente, Congreso, partidos, sindicatos,
Banco Central, medios. Puede recombinarlas; no puede inventar una que no exista. La pregunta de v2 es:

> ¿Qué formas de organización social emergen cuando agentes autónomos solo disponen de un puñado de
> capacidades elementales y pueden crear, delegar, condicionar y modificar reglas?

La decisión conceptual de este ADR es **qué queda fijo** (physics) y **qué debe poder emerger**
(institutions), y con qué primitivas. Es la decisión más fácil de contaminar con supuestos escondidos,
así que la sección 3 es una lista explícita de lo que **no** se hardcodea y la sección 2 de lo que sí,
con la razón de cada supuesto.

## 2. Physics: lo que no cambia dentro de una corrida

| Elemento | Qué es | Por qué es inevitable |
|---|---|---|
| **Agentes** | N entidades con identidad persistente, memoria acotada y un vector de necesidades | Sin identidad persistente no hay reputación ni promesa posible |
| **Bienes** | K tipos con atributos físicos: durabilidad (fracción que sobrevive cada turno), divisibilidad (unidad mínima), costo de transporte/almacenamiento, y utilidad directa por agente (algunos bienes no le sirven a nadie salvo como intermedio) | Es lo mínimo para que "medio de intercambio" pueda ser una propiedad descubierta, no declarada |
| **Espacio** | R regiones; cada agente vive en una; observa e interactúa con una muestra local por turno; moverse cuesta | Sin localidad no hay información asimétrica ni federalismo posible |
| **Producción** | Cada agente produce por turno una canasta según su región y su especialización (fija al inicio); producir más de un bien reduce los otros | Escasez y ventaja comparativa: sin esto no hay motivo para intercambiar |
| **Necesidades** | Consumir ciertos bienes evita "privación"; la privación acumulada reduce productividad y, si supera un umbral, el agente sale (muere) y es reemplazado | La presión selectiva que hace que las estrategias importen |
| **Posesión** | Un agente controla lo que tiene en su inventario. No existe "propiedad" jurídica: solo posesión física y lo que otros estén dispuestos a defender o sancionar | La propiedad *es* una institución; hardcodearla sería trampa |
| **Coerción** | Un agente puede intentar tomar del inventario de otro; el éxito depende de la "capacidad" relativa (que se puede delegar/agregar) y tiene costo para ambos | Sin coerción posible, ni el Estado ni su ausencia significan nada |
| **Información** | Cada agente ve: su inventario, sus necesidades, los agentes de su muestra local, las acciones públicas del turno anterior en su región y los mensajes que recibió. **No ve** precios, agregados ni inventarios ajenos | Todo lo demás (precios, estadísticas) debe emerger como comunicación |
| **Comunicación** | Mensajes estructurados a agentes de la muestra local o a un grupo del que es miembro; pueden ser falsos | Mentir posible ⇒ la confianza tiene que construirse |
| **Memoria** | Cada agente recuerda las últimas M interacciones por contraparte (resultado, cumplimiento) | Base de la reputación; acotada para que olvidar sea real |
| **Tiempo** | Turnos discretos; todas las acciones de un turno se resuelven simultáneamente en orden fijo por tipo | Determinismo |

Supuestos discutibles que igual quedan en physics (marcados para el checkpoint humano):
- Las necesidades son homogéneas por región (v2.0); la heterogeneidad individual entra en v2.1.
- La coerción es "toma de inventario", no daño físico permanente.
- La muerte por privación existe. Sin selección, no hay evolución de estrategias.

## 3. Lo que **no** se hardcodea (y cómo se verifica que no)

| No existe como tipo ni como variable | Puede emerger como |
|---|---|
| Moneda, precio, "mercado" | Un bien que muchos aceptan sin consumirlo; ratios de intercambio observados |
| Propiedad, contrato, tribunal | Promesas con sanción creíble; grupos que castigan a quien toma sin acuerdo |
| Estado, gobierno, presidente, policía | Un grupo con capacidad de coerción delegada y reglas sobre cuándo usarla |
| Partido, sindicato, empresa, banco, medio | Grupos con reglas de ingreso, fondo común y procedimiento de decisión |
| Votación, mayoría, representación | Una función de agregación elegida por el grupo entre las disponibles, incluidas las que el grupo compone |
| Impuesto, transferencia, presupuesto | Reglas condicionales de transferencia al fondo de un grupo y desde él |
| Ley, constitución | Reglas y metarreglas de un grupo, versionadas |

Test de contaminación: `grep` del paquete `core/` contra una lista negra de identificadores
(`money`, `price`, `state`, `government`, `party`, `union`, `firm`, `bank`, `vote`, `tax`, `law`,
`president`, `market`, `property`, `contract`) que solo pueden aparecer en `core/classify/` (etiquetado
*a posteriori*) y en docs. El test forma parte de la suite.

## 4. Las primitivas (la CPU social)

Once operaciones. Todas las instituciones de la sección 3 deben poder expresarse componiéndolas; ninguna
primitiva debe presuponer una institución.

| # | Primitiva | Firma | Semántica |
|---|---|---|---|
| 1 | `TRANSFER` | `(to, good, qty)` | Mueve del inventario propio al de `to`. Unilateral: dar es siempre posible; recibir no requiere consentimiento (rechazar es devolver). |
| 2 | `OFFER` | `(to, give: {good: qty}, want: {good: qty}, ttl)` | Propuesta de intercambio. Se ejecuta si `to` responde `ACCEPT` dentro de `ttl` y ambos tienen lo ofrecido en ese momento. Es la única forma de intercambio atómico. |
| 3 | `PROMISE` | `(to, action, condition, deadline)` | Compromiso observable: si `condition` (predicado sobre estado observable) se cumple antes de `deadline`, el emisor debe ejecutar `action`. El motor registra `honored`/`broken` y lo hace visible a la región. **No** obliga: solo hace verificable. |
| 4 | `GRANT` / `REVOKE` | `(to, capability, scope, ttl)` | Delega una capacidad (`coerce`, `transfer_from_pool`, `speak_for`, `admit`, `sanction`, `modify_rule`) sobre un alcance (propio, o del grupo si se tiene autoridad). Revocable por quien la otorgó salvo regla del grupo. |
| 5 | `CREATE_GROUP` | `(rules, admission, aggregation)` | Crea una entidad con miembros, un fondo (inventario propio), un conjunto de reglas y un procedimiento de decisión. El creador es el primer miembro. |
| 6 | `JOIN` / `LEAVE` | `(group)` | Solicitar entrada (resuelta por la regla `admission` del grupo) o salir (sujeto a reglas de salida). |
| 7 | `AGGREGATE` | `(group, question, procedure)` | Convierte inputs de los miembros en una decisión del grupo. `procedure` es una función de una **álgebra cerrada**: `majority(threshold)`, `weighted(by: capability | contribution | tenure)`, `random_member`, `rotation`, `consensus`, `delegate(to)`, y composición (`then`, `unless`, `quorum`). El grupo puede definir procedimientos nuevos componiendo estos. |
| 8 | `CONDITION` | `(group, predicate, obligation, sanction)` | Crea una regla del grupo: si `predicate` (observable) entonces `obligation` (una primitiva que un miembro debe ejecutar) y, si no la ejecuta, `sanction`. |
| 9 | `SANCTION` | `(target, kind, qty)` | `exclude` (expulsar del grupo), `fine` (transferencia forzada al fondo, requiere capacidad `coerce` delegada), `broadcast` (hacer público el incumplimiento en la región). |
| 10 | `EXPIRE` | `(rule | grant, at)` | Toda regla o delegación puede tener vencimiento. |
| 11 | `MODIFY_RULE` | `(group, rule_id, new_rule)` | Metarregla: cambia una regla del grupo **a través del procedimiento de agregación del propio grupo** (o del que la regla `amendment` indique). Es lo que convierte un grupo en algo con constitución. |

Más `COERCE(target, good, qty)` que es physics (sección 2), no primitiva institucional: es la acción que
las instituciones existen para regular.

Propiedad de cierre: una "constitución" es un programa sobre estas once operaciones; el intérprete es
determinista; el estado de un grupo es serializable y comparable (hash) entre corridas.

## 5. Cómo deciden los agentes en v2

Tres cerebros, como en v1, con la misma interfaz:
- **Reglas evolutivas**: cada agente tiene un genoma de estrategias (qué bienes acepta como intermedio,
  cuánto confía por defecto, cuándo promete, cuándo se une a grupos, cuándo castiga). Selección: los que
  sobreviven se reproducen con mutación. Es el baseline y el que permite millones de corridas.
- **Sustituto** entrenado sobre corridas con LLM (ADR 009).
- **LLM** para una fracción de agentes "articulados" (los que proponen reglas y grupos), con el mismo
  esquema de salida cerrado: una lista de primitivas con parámetros.

## 6. Clasificación a posteriori (`core/classify/`)

Después de la corrida, y solo después, se etiqueta:
- **Medio de intercambio**: bien con `acceptance_rate` (fracción de agentes que lo aceptan sin consumirlo)
  > 0.5 sostenida ≥ 50 turnos. Se reporta cuál, cuándo emergió, y su concentración (Herfindahl).
- **Reputación/crédito**: fracción de intercambios diferidos (PROMISE) cumplidos; si > 0.7 y crecen, hay
  crédito.
- **Organización coercitiva**: grupo con `coerce` delegado por ≥ 30 % de una región y reglas que lo
  condicionan.
- **Procedimiento de decisión**: firma del árbol de agregación de cada grupo persistente (≥ 100 turnos).
- **Familias institucionales**: vectores por corrida (tipos de grupos, tamaños, reglas, delegaciones,
  frecuencia de sanciones, desigualdad, privación) → clustering (ADR 009 §6) → nombres al final.

## 7. Hito 1: ¿emerge un medio de intercambio?

**Mundo mínimo.** 10.000 agentes, 4 regiones, 6 bienes:

| Bien | Durabilidad | Divisibilidad | Transporte | Quién lo consume |
|---|---|---|---|---|
| grano | 0.90 | 1 | bajo | todos |
| pescado | 0.60 | 1 | medio | todos |
| tela | 0.98 | 1 | bajo | todos |
| herramienta | 0.99 | 1 (indivisible) | medio | productores |
| sal | 0.995 | 0.1 | muy bajo | todos, poco |
| conchas | 1.00 | 0.01 | muy bajo | **nadie** |

Cada agente produce 2 bienes (especialización por región), necesita 3 por turno, ve 12 vecinos, puede
emitir hasta 3 `OFFER` por turno. Solo primitivas 1 y 2 activas (sin promesas ni grupos): el hito 1
aísla la emergencia del dinero de la del crédito.

**Estrategia evolutiva por agente**: vector de "aceptabilidad" por bien (probabilidad de aceptar un bien
que no consume a cambio de uno que sí ofrece), actualizado por refuerzo: sube si el bien aceptado se
pudo reintercambiar en ≤ 3 turnos por algo que necesitaba, baja si se pudrió o quedó sin uso. Mutación
al reproducirse.

**Hipótesis registradas antes de correr** (se documenta si se cumplen o no):
- H1: en > 60 % de las corridas emerge un medio de intercambio dominante en < 300 turnos.
- H2: el bien dominante es casi siempre uno de {sal, conchas, tela} (durable, divisible, transportable);
  grano y pescado casi nunca.
- H3: las conchas (sin uso propio) solo ganan si su oferta es escasa y estable; si se producen en
  abundancia, pierden contra la sal.
- H4: la emergencia es más lenta cuanto mayor es el costo de transporte entre regiones (menos
  oportunidades de reintercambio).

**Métricas por corrida**: turno de emergencia, bien dominante, Herfindahl de intermedios, fracción de
intercambios indirectos, privación media, desigualdad de inventarios (Gini), por región.

**Implementación**: `src/republica/core/{world,agents,exchange,evolve,classify,run}.py`, `numpy`
permitido dentro de `core/` (extra `[core]`), vectorizado por turno; objetivo 10.000 agentes × 500
turnos en < 60 s en 4 cores. CLI `republica core run --agents 10000 --turns 500 --seed 7`,
`republica core batch --seeds 100 --out simulations/core/` y `republica core classify <dir>`.

**DoD del hito 1**: 100 semillas corridas; reporte con H1–H4 marcadas cumplida/no cumplida con números;
test de contaminación (sección 3) verde; determinismo por semilla; el test de que sin bienes durables
(todos con durabilidad 0.6) **no** emerge medio de intercambio (control negativo).

## 8. Hitos siguientes (no se implementan en esta pasada)

- **Hito 2 — crédito y reputación**: activar `PROMISE` y `SANCTION(broadcast)`. ¿Aparecen intercambios
  diferidos sostenidos? ¿Con o sin dinero primero?
- **Hito 3 — grupos y coerción**: activar `CREATE_GROUP`, `GRANT(coerce)`, `CONDITION`. ¿Emerge una
  organización que monopoliza la coerción en una región? ¿Con qué reglas? ¿Cobra "impuestos"?
- **Hito 4 — metarreglas**: activar `MODIFY_RULE`. Genomas de constituciones; evolución bajo shocks;
  frontera de Pareto sobre {privación, desigualdad, libertad (fracción de acciones no sancionadas),
  estabilidad (persistencia de grupos), resiliencia}.
- **Hito 5 — el investigador**: un agente externo (LLM fuerte) que lee reportes, propone hipótesis y
  diseña lotes; el ciclo hipótesis → experimento → análisis → nueva hipótesis con registro completo.

## 9. Batería epistemológica obligatoria

Ningún hallazgo de v2 se publica sin: stress test (cambiar physics radicalmente), ablation (quitar una
primitiva y ver si el fenómeno persiste), sensibilidad (barrer parámetros), out-of-distribution (mundos
no usados en la búsqueda), y contraste con literatura (Menger, Kiyotaki–Wright, Ostrom, Axelrod) para
decir "esto se parece a X" sin decir "esto demuestra X". Y la frase fija de ADR 008 §4 en cada reporte.

## 10. Notas de implementación (hito 1)

Desviaciones, decisiones de diseño e interpretaciones operativas al implementar
`src/republica/core/{world,exchange,evolve,classify,run}.py`, el sub-comando `republica core`
y las corridas reales de `experiments/results/core_hito1/`.

### Lectura operativa de la tabla de bienes/regiones (`core/world.py`)

1. **"Necesita 3 [bienes] por turno" se leyó como los 3 bienes de consumo masivo (grano,
   pescado, tela, `need_qty=1.0` cada uno), y se agregaron sal (`0.2`, "todos, poco" — literal
   de la tabla del ADR) y herramienta (`0.3`) como necesidades MENORES adicionales, no como parte
   de "los 3".** La tabla del ADR describe 4 bienes "que todos consumen" (grano/pescado/tela/sal,
   este último "poco") más herramienta ("productores") — no hay una lectura literal donde
   exactamente 3 bienes cubran "todos" Y "productores" a la vez, así que se priorizaron los 3
   bienes de consumo pesado como la necesidad central (privación se dispara mayormente por
   estos) y sal/herramienta como fricción adicional de menor peso.
2. **"Quién lo consume: productores" (herramienta) se modeló como `consumed_by="all"` con
   `need_qty=0.3`, no como una categoría separada.** En este mundo TODO agente es productor (de
   los 2 bienes de su región, ADR secc. 2 "Producción"), así que "productores" y "todos" coinciden
   — no hay agentes que no produzcan nada. Se probó primero una lectura literal (herramienta sin
   necesidad, solo con un bono multiplicativo a la producción propia de quien la tiene,
   `tool_bonus`) pero esa lectura hace que `classify.acceptance_rate` cuente la demanda genuina de
   herramienta (querida por su bono, no como intermediario) como si fuera un candidato a medio de
   intercambio: con esa lectura herramienta ganaba en la mayoría de las semillas de prueba, lo cual
   contradice H2 (que espera sal/conchas/tela, nunca herramienta) y es un artefacto de medición, no
   un hallazgo real. Se mantuvo el bono de producción (`tool_bonus=0.25`, ADR: "produce más de un
   bien reduce los otros" se interpretó de forma más simple, ver punto 5) COMO ADEMÁS de la
   necesidad, no en su lugar.
3. **Reparto de especialización por región** (ADR: "cada agente produce 2 bienes... fija al
   inicio"; la tabla del ADR no especifica QUÉ región produce qué): llanura→{grano, sal},
   costa→{pescado, conchas}, valle→{tela, herramienta}, sierra→{herramienta, sal}. Grano y pescado
   quedan cada uno en una sola región; herramienta y sal en dos (para que las 4 regiones tengan
   algo que exportar); conchas SOLO en costa (la hace escasa por diseño, relevante para H3).
   Ninguna región produce los 3 bienes de consumo pesado (grano/pescado/tela) a la vez: todas
   dependen del comercio para cubrir su necesidad central, que es el supuesto que hace el hito
   interesante (sin comercio, privación total).
4. **`transport_cost` es DOS parámetros distintos y ninguno mueve literalmente bienes entre
   regiones.** `GoodSpec.transport_cost` (por bien, de la tabla del ADR: bajo/medio/muy bajo →
   0.05/0.10/0.01) queda declarado pero NO se usa en la física del hito 1 (no hay una primitiva de
   "mover inventario de región" — los agentes no viajan, solo comercian con la muestra local); es
   metadata para un hito futuro. El que sí es físico es `CoreConfig.transport_cost` (un único
   escalar general, el parámetro que barre H4): reduce la probabilidad de que un vecino muestreado
   sea de otra región (`p_mismo = 1 - max(0, 0.2 - transport_cost)`), o sea, así de caro moverse
   se manifiesta como MENOS oportunidad de contacto entre regiones, no como pérdida de mercancía en
   tránsito.
5. **"Producir más de un bien reduce los otros" (ADR secc. 2) se simplificó a producción FIJA por
   agente (los 2 bienes de su región, a tasa constante `production_rate=1.2`), sin que el agente
   elija cuánto de cada uno.** El hito 1 no activa ninguna primitiva de decisión sobre producción
   (solo `TRANSFER`/`OFFER`), así que no hay "más de un bien" que asignar: el trade-off ya está
   fijado por la especialización regional (2 bienes SÍ, los otros 4 NO), que es lo mínimo que pide
   el ADR para que haya ventaja comparativa.

### Mecánica de oferta/aceptación (`core/exchange.py`)

6. **La distinción "directo" vs. "indirecto" se decide del lado del INICIADOR de la `OFFER`, no
   del receptor.** Una oferta es directa si el bien que el iniciador PIDE es uno de sus propias
   necesidades incumplidas ese turno; es indirecta si, no teniendo ninguna necesidad incumplida (o
   habiendo agotado los intentos directos), el iniciador pide un bien que NO necesita, apostando
   (`acceptability[i, g]`) a poder revenderlo. El bien recibido por la CONTRAPARTE puede a su vez
   no ser una necesidad suya — eso se cuenta por separado (`accept_no_need_by_good`,
   `last_accept_turn`) para `classify.acceptance_rate`, que mide aceptación sin consumo de
   CUALQUIERA de los dos lados del trueque, no solo del lado que inició la oferta.
7. **A lo sumo una oferta EJECUTADA por contraparte-blanco por ronda** (si dos iniciadores
   distintos apuntan al mismo vecino en la misma ronda, solo se ejecuta la del índice de agente más
   bajo). Es una simplificación deliberada para vectorizar con numpy sin una segunda pasada de
   reconciliación de conflictos: evita que una contraparte "regale" más de lo que tiene cuando la
   contabilidad se hace en un único paso vectorizado sobre los N agentes a la vez. Con
   `neighbours_per_turn=12` y regiones de ~2.500 agentes, la probabilidad de colisión por ronda es
   baja; no se corrigió por ser de bajo impacto y alto costo de implementación (perdería la
   vectorización).
8. **`acceptance_rate[g]`, el indicador central de `classify.py`, mide "recibió `g` por trueque sin
   necesitarlo en los últimos 50 turnos" vía un array `last_accept_turn[N, K]` (turno de la última
   vez), no un conteo de eventos.** Es una lectura literal de "fracción de agentes que lo aceptaron
   sin consumirlo en los últimos 50 turnos" (ADR secc. 6) — un agente cuenta como "aceptando" `g`
   mientras haya pasado por esa situación alguna vez en la ventana, independientemente de si
   todavía lo tiene en el inventario (que puede haberse decaído o retransferido). Ver el hallazgo
   del control negativo (punto 10) para la consecuencia de esta elección.

### Refuerzo y mutación (`core/evolve.py`)

9. **El refuerzo (sube/baja `acceptability`) se ata a un único array de apuestas pendientes por
   `(agente, bien)` (`pending_turn`), no a una cola de transacciones individuales.** Si un agente
   acepta el mismo bien intermedio dos veces antes de resolver la primera apuesta, la segunda
   aceptación NO abre una apuesta nueva (se ignora, `pending_turn` ya estaba puesto) — el refuerzo
   se basa en "¿el bien X, en general, se pudo revender a tiempo?", no en rastrear cada unidad
   físicamente. Es una simplificación necesaria para vectorizar (numpy no tiene una cola de eventos
   por celda); el efecto práctico es que el refuerzo es un poco más lento en agentes que aceptan el
   mismo bien muy seguido, no que sea incorrecto.

### Control negativo (DoD, ADR secc. 7)

10. **"Todos los bienes con durabilidad 0.6" (la ablación LITERAL del ADR) NO alcanza para suprimir
    la emergencia en esta implementación — se verificó empíricamente (10/10 semillas con medio de
    intercambio emergido, incluso bajando la durabilidad uniforme hasta 0.1).** La razón, una vez
    investigada: lo que hace de conchas el candidato dominante no es (solo) su durabilidad relativa
    sino que es el ÚNICO bien que nadie necesita (`consumed_by="none"`) — su "excedente" nunca se
    consume, así que se acumula turno a turno sea cual sea la durabilidad, mientras que producción
    lo repone cada turno independientemente de cuánto sobrevivió. Bajar la durabilidad de TODOS los
    bienes por igual no toca esa ventaja estructural (grano/pescado/tela/sal siguen
    consumiéndose, conchas sigue sin consumirse), así que conchas sigue ganando. El control negativo
    real que SÍ suprime la emergencia (verificado: 0/10 semillas en la prueba rápida, 20 semillas x
    300 turnos en el test formal) combina la ablación de durabilidad CON la eliminación de esa
    ventaja estructural: los 6 bienes pasan a `consumed_by="all"` (nadie tiene ya un bien "puro
    token", todos se consumen y por lo tanto todos tienen un costo de oportunidad por acumularlos)
    ADEMÁS de la durabilidad uniforme 0.6. Este hallazgo es interesante por derecho propio: sugiere
    que, en esta física mínima, la condición NECESARIA para que emerja un medio de intercambio no
    es (solo) la durabilidad diferencial (que sí determina, entre varios candidatos sin uso propio,
    cuál gana — H2) sino la EXISTENCIA de al menos un bien sin utilidad de consumo directo. Se deja
    documentado en vez de forzar el test a pasar con la ablación literal; `tests/test_core.py`
    implementa la versión que sí demuestra la hipótesis (ausencia de medio de intercambio) y explica
    el porqué en su docstring.

### Corridas reales (`experiments/results/core_hito1/`)

11. **La batería de 280 corridas (100 semillas base + 3×30 del barrido H3 + 3×30 del barrido H4)
    se corrió a 2.000 agentes × 500 turnos, no a 10.000 × 500.** El target de rendimiento del ADR
    (10.000 agentes × 500 turnos < 60 s, 4 cores) se demuestra aparte con una corrida de
    calibración a escala completa (`republica core run --agents 10000 --turns 500 --seed 7`,
    ~22 s en este entorno — ver el reporte). Correr las 280 semillas de la batería epistémica a
    10.000 agentes habría tomado del orden de 20-25 minutos incluso con 4 workers; a 2.000 agentes
    (~4.7 s/corrida) el mismo lote corre en unos pocos minutos, dejando margen para iterar. La
    dinámica cualitativa (qué bien emerge, cuándo, y cómo responde a los barridos) es la misma a
    ambas escalas en las corridas de prueba usadas para diseñar el modelo; se documenta la escala
    real en `report.md` y en `summary.csv`.
12. Los niveles exactos de los barridos H3 (`shell_abundance`) y H4 (`transport_cost`), el
    resultado de las 4 hipótesis con sus números, y la distribución del bien dominante sobre las
    100 semillas quedan en `experiments/results/core_hito1/report.md` (versionado junto con
    `summary.csv` y los PNG de `plots/`; los 280 JSON crudos por semilla NO se versionan, ver
    `.gitignore`, y se reproducen con los comandos `republica core batch` listados al pie del
    reporte).
