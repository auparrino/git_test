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
