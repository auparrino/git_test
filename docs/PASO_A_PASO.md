# Paso a paso: qué tenés que hacer vos

Checklist operativa para ejecutar `PLAN.md`. Cada paso dice qué hacés, qué le pedís a Claude Code
(y con qué modelo), y cómo verificás que quedó bien antes de seguir.

Convención: `[vos]` lo hacés a mano · `[cc: modelo]` se lo pedís a Claude Code con ese modelo.

---

## Semana 0 — Preparar tu máquina (1 tarde)

1. `[vos]` Instalar herramientas base:
   ```bash
   # Python + uv
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # Ollama
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen3:8b
   ollama pull qwen3:4b
   # Docker (para Langfuse, recién en Fase 7; podés dejarlo para después)
   ```
2. `[vos]` Verificar que Ollama responde con JSON schema:
   ```bash
   curl http://localhost:11434/api/chat -d '{
     "model": "qwen3:4b", "stream": false,
     "messages": [{"role":"user","content":"Respondé {\"ok\": true}"}],
     "format": {"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}
   }'
   ```
   Si tu máquina no aguanta `qwen3:8b`, quedate con `qwen3:4b` para todo hasta Fase 8.
3. `[vos]` Clonar el repo y pararte en la rama del plan; mergeala a `main` cuando estés conforme:
   ```bash
   git clone https://github.com/auparrino/git_test republica-artificial
   cd republica-artificial
   git checkout claude/republica-artificial-plan-wwtepf
   ```
4. `[vos]` Leer `docs/PLAN.md` entero una vez. Anotá lo que no te cierra: se corrige ahora, no en Fase 5.

---

## Paso 1 — Fase 0: scaffold (1 sesión)

1. `[cc: Sonnet 5]` Pedile:
   > Ejecutá la Fase 0 de docs/PLAN.md: pyproject con uv, estructura `src/republica/...` con `__init__.py`,
   > ruff, pytest con un test trivial, CLI `republica --help` con typer, GitHub Actions con ruff + pytest,
   > `.gitignore` con `simulations/`. Borrá `hello_world.txt`. Dejá `docs/SPEC_v0.1.md` con las secciones vacías.
2. `[vos]` Verificar:
   ```bash
   uv sync && uv run pytest && uv run republica --help
   ```
3. `[vos]` Commit, push, abrir PR, mergear a `main`. A partir de acá, **una rama por fase**.

---

## Paso 2 — Fase 1: la spec de v0.1 (2 sesiones, sin código)

Este es el paso donde más vale tu criterio. No dejes que Claude decida solo los valores.

1. `[cc: Fable 5.1, plan mode]` Pedile:
   > Escribí docs/SPEC_v0.1.md para la República de Aurora según docs/PLAN.md Fase 1: las 20 variables
   > con valor inicial, rango y unidad; fórmulas de transición mensual con coeficientes nombrados;
   > 8 provincias, 5 partidos, 12 shocks con efectos numéricos y duración; orden del turno; y qué
   > tests de propiedades lo verifican. Marcá explícitamente cada supuesto discutible.
2. `[vos]` Leer la spec con lápiz. Preguntas que tenés que poder responder vos:
   - ¿Qué pasa si subo la tasa 10 puntos? ¿Baja inflación en cuántos meses? ¿A qué costo en desempleo?
   - ¿Qué pasa si no hago nada durante 48 meses? (tiene que ser aburrido pero no explotar)
   - ¿Un shock de sequía se nota en aprobación 3 meses después?
   Si no podés responderlas leyendo la spec, la spec está incompleta.
3. `[cc: Fable 5.1]` Segunda vuelta con tus correcciones. Recién cuando la aprobás, pasás a implementar.

---

## Paso 3 — Fase 1: implementar el mundo (3–4 sesiones)

1. `[cc: Sonnet 5]` Una sesión por módulo, en este orden, siempre "contra la spec":
   - `world/state.py` + tests de cotas.
   - `world/economy.py` + tests.
   - `world/politics.py`, `world/society.py` + tests.
   - `world/events.py` (shocks) + `engine/simulation.py` + CLI `republica run`.
   - Test de propiedades: 1.000 semillas, sin NaN, todo acotado, determinismo.
2. `[vos]` Verificar la DoD de Fase 1:
   ```bash
   uv run republica run --seed 7 --months 48 --out simulations/run_7.jsonl
   uv run republica narrate simulations/run_7.jsonl
   ```
   Leé la narración. Si algo es absurdo (inflación 2 % con emisión récord, aprobación que sube en recesión), volvés a la spec, no al código.
3. `[cc: Opus 5]` `/code-review` antes de mergear.
4. `[vos]` Tag `v0.1`. Poné la narración de una corrida en el README.

---

## Paso 4 — Fase 2: jugar (2 sesiones)

1. `[cc: Opus 5]` Pedile que diseñe 10–15 dilemas mensuales (situación, opciones A/B/C, efectos) y los deje en `data/scenarios/`.
2. `[cc: Sonnet 5]` Implementar `republica play` con los dilemas y el consejero por reglas.
3. `[vos]` Jugar **tres partidas completas**. Anotá dónde te aburriste y dónde una decisión no tuvo consecuencias visibles. Eso vuelve como issues.
4. `[vos]` Tag `v0.2`.

---

## Paso 5 — Fase 3: actores por reglas y permisos (3–4 sesiones)

1. `[cc: Opus 5, plan mode]` Pedile un ADR con: catálogo de acciones por rol, estructura de `authorize()`,
   fórmula de scoring de los actores por reglas, y esquema del log JSONL por turno.
2. `[vos]` Revisar el catálogo: ¿hay algún rol que puede hacer algo que no debería? Corregilo ahora.
3. `[cc: Haiku 4.5]` Generar las 25 fichas YAML de actores. `[vos]` leer 5 al azar y ajustar personalidades: es donde va a salir la política interesante.
4. `[cc: Sonnet 5]` Implementar `actors/rule_based.py`, `engine/permissions.py`, `engine/consequences.py`, `scheduler.py`, tests por rol.
5. `[vos]` Verificar DoD: correr 48 meses con todos los actores y confirmar que un gobernador aliado se opone a un recorte a su provincia. Confirmar que una acción prohibida queda registrada como rechazada.

---

## Paso 6 — Fase 4: los primeros tres agentes IA (3–4 sesiones)

1. `[cc: Opus 5]` Diseñar `ai/schemas.py`, política de visibilidad por rol y los tres prompts. Pedile explícitamente que el prompt no contenga información que el actor no conocería.
2. `[cc: Sonnet 5]` Implementar `ai/ollama_client.py` (schema, reintentos, cache por hash, trazas) y `actors/llm_based.py` con la misma interfaz que las reglas.
3. `[vos]` Medir parse rate:
   ```bash
   uv run republica bench-parse --brain ollama:qwen3:8b --n 50
   ```
   Si es menor a 95 %, cambiás de modelo o de prompt, no seguís.
4. `[vos]` Correr la misma semilla con `--brain rules` y con `--brain ollama:qwen3:8b` y comparar las decisiones del gobernador lado a lado. Anotá las tres diferencias más interesantes: son el material del primer post técnico.
5. `[vos]` Tag `v0.3`.

---

## Paso 7 — Fase 5: negociación, Congreso, medios, cohortes (5–7 sesiones)

Un subsistema por rama. Orden: Congreso → negociación → cohortes → medios y percepción.

1. `[cc: Fable 5.1, plan mode]` Un diseño por subsistema, con gemelo por reglas y tests.
2. `[cc: Sonnet 5]` Implementar. `[cc: Opus 5]` review por rama.
3. `[vos]` Después de cada subsistema, jugar una partida. Verificar DoD: conseguir 9 votos negociando, y dos medios que producen percepciones distintas en cohortes distintas.
4. `[vos]` Buscar la primera alianza emergente en los logs y documentarla en `docs/EMERGENCE_LOG.md`.

---

## Paso 8 — Fase 6: memoria y elecciones (3–4 sesiones)

1. `[cc: Opus 5]` Diseño de recuperación de memoria (relevancia + recencia + importancia) y del modelo electoral.
2. `[cc: Sonnet 5]` Implementar `ai/memory.py` y elecciones.
3. `[vos]` Verificar: romper un acuerdo en el turno 17 y confirmar que aparece en el prompt del gobernador en el turno 20. Correr 100 elecciones y mirar la distribución de ganadores.
4. `[vos]` Tag `v0.5`. Streamlit básico opcional acá (`[cc: Sonnet 5]`).

---

## Paso 9 — Fase 7: evals, Langfuse, gobernanza (4–6 sesiones)

1. `[vos]` Antes de que Claude escriba nada: escribí a mano **20 casos de eval** con resultado esperado (actor, situación, propuesta, decisión esperada). Son el ancla que evita que el eval mida el prompt.
2. `[cc: Fable 5.1]` Diseño de la suite de 8 evals a partir de tus 20 casos; que genere los 80 restantes con Sonnet y vos revisás una muestra.
3. `[vos]` Levantar Langfuse:
   ```bash
   git clone https://github.com/langfuse/langfuse && cd langfuse && docker compose up -d
   ```
4. `[cc: Sonnet 5]` Integrar trazas, Promptfoo y las fichas de gobernanza aplicadas por el motor.
5. `[vos]` Correr `republica eval --suite all` con `rules` y con `ollama`. Abrir tres decisiones raras en Langfuse y explicarlas. Subir la autonomía del Banco Central de 2 a 4 y ver qué cambia.
6. `[vos]` Tag `v0.8`. Reescribir el README en modo portfolio.

---

## Paso 10 — Fase 8: experimentos (3–4 sesiones)

1. `[cc: Sonnet 5]` Runner de experimentos, esquema DuckDB, paralelismo.
2. `[vos]` Definir los dos experimentos canónicos en YAML y correrlos (100 corridas cada uno; dejá la máquina toda la noche).
3. `[cc: Opus 5]` Análisis en notebook. Pedile que **discuta** tus conclusiones, no que las confirme.
4. `[vos]` Commitear notebooks con semillas fijas. Segundo post técnico.

---

## Paso 11 — Fase 9: sustituto y UI (5–8 sesiones)

1. `[cc: Fable 5.1]` Diseño del sustituto y del criterio de active learning.
2. `[cc: Sonnet 5]` Pipeline de entrenamiento, `brain = surrogate`, early-warning, clustering, Streamlit completo.
3. `[vos]` Verificar: 10.000 corridas en menos de una hora; sustituto ≥85 % de acuerdo con el LLM en held-out.
4. `[vos]` Tag `v1.0`.

---

## Paso 12 — Fase 10: v2, CPU social (sin fecha)

1. `[vos]` Escribí vos primero, en una página, tu lista de primitivas y tu lista de "cosas que no quiero que estén hardcodeadas".
2. `[cc: Fable 5.1, plan mode]` ADR "Physics vs. Institutions" a partir de tu página. Pedile que busque supuestos escondidos (democracia, capitalismo, partidos, moneda).
3. Recién después: intérprete, loop evolutivo, clasificación a posteriori, investigador IA.

---

## Reglas de trabajo que te van a ahorrar meses

- **No arranques la fase N+1 sin la DoD de la fase N.** Está escrita en PLAN.md para eso.
- **Diseño en plan mode con modelo fuerte, implementación con Sonnet contra la spec, review con Opus.** No al revés.
- **Una rama por fase, un PR por subsistema.** `/code-review` antes de mergear.
- **Jugá una partida después de cada fase.** Si dejó de ser divertido, algo se rompió aunque los tests pasen.
- **Todo lo que te sorprenda va a `docs/EMERGENCE_LOG.md`** con semilla y turno. Eso es el contenido del portfolio.
- **Cada sesión de Claude Code empieza con:** "Leé docs/PLAN.md y docs/SPEC_v0.1.md. Estamos en la Fase X, paso Y."
