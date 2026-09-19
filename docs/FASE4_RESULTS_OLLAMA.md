# Fase 4 con Ollama local — resultados (actores por reglas vs. actores LLM)

**Estado: PARCIAL.** Este documento tiene los números reales de la mitad "por reglas" de cada
comparación (Aurora seed 7 y Argentina 2019-12, mismas semillas y configuración que pide el plan) y
deja **vacías, marcadas como pendientes, las columnas LLM**: en el entorno donde se intentó correr
esto (sesión remota, ver "Entorno y bloqueo") no se pudieron bajar los pesos de ningún modelo. No hay
ningún número inventado ni simulado con `fake:*` presentado como resultado LLM.

Para completar las columnas pendientes en una máquina con Ollama alcanza con un comando (ver
"Cómo completar este documento"): `scripts/fase4_ollama.sh` corre todo el plan en orden, deja las
salidas en `simulations/fase4_logs/` y termina con `scripts/fase4_collect_results.py`, que arma
`simulations/fase4_logs/RESULTADOS.md` con todas las tablas de este documento y de
`FASE4_BENCH_OLLAMA.md` listas para pegar.

## Entorno y bloqueo

| | |
|---|---|
| Máquina | contenedor remoto, Intel Xeon @ 2.80 GHz, 4 vCPU (avx2/avx512), 15 GiB RAM, sin GPU |
| Ollama | v0.12.0 (binario bajado del release oficial en GitHub, levantado con `ollama serve`, CPU-only) |
| Modelo | **ninguno**: `qwen3:8b` y `qwen3:4b` no se pudieron bajar |
| Python | `uv sync --all-extras` OK; `uv run pytest -q -m "not slow"` verde; `ruff check .` limpio |

Qué se intentó para obtener pesos, en orden, y por qué falló (todo bloqueado por la política de
egreso del entorno, respuesta `403` al `CONNECT` del proxy):

1. `ollama pull qwen3:8b` → `registry.ollama.ai` y `ollama.com` bloqueados.
2. GGUF desde Hugging Face (`huggingface.co`, `hf.co`, `cas-bridge.xethub.hf.co`), ModelScope,
   Kaggle, gpt4all.io: bloqueados.
3. GGUF como artefacto OCI en Docker Hub (`ai/qwen3:8b`, que es exactamente `Qwen3-8B-Q4_K_M.gguf`,
   5.0 GB): el manifiesto se lee, pero el blob redirige a `production.cloudfront.docker.com`, bloqueado.
   Lo mismo con `ghcr.io` (blobs en `pkg-containers.githubusercontent.com`), `quay.io` y `jozu.ml`.
4. Paquetes de PyPI/npm que embeban pesos: no existe ninguno con un Qwen3 (los que hay los bajan de
   Hugging Face en el postinstall).

Lo único alcanzable son releases de GitHub (de ahí salió el binario de Ollama), PyPI y npm. Con
pesos a mano, el resto del pipeline está verificado: `bench-parse`, `run --brain llm:...`,
`eval --brain ...` y el script de comparación corren de punta a punta con `fake:rules` (cero LLM,
misma tubería `Perception → prompt → ActorDecision → to_actions → authorize`).

**Aviso para la máquina local:** `OllamaBackend` tiene timeout de 60 s por llamada (ADR 004 secc.
2). Un `qwen3:8b` en CPU (sin GPU) puede tardar más que eso por decisión (prompt de ~700–800
tokens, hasta 800 de salida); si aparecen `URLError`/timeout, correr con GPU, usar `qwen3:4b`, o
subir `DEFAULT_TIMEOUT_SECONDS` en `ai/backends.py` para la corrida (anotarlo en este documento si
se hace).

## Cómo completar este documento

```bash
ollama pull qwen3:8b            # o qwen3:4b; anotar cuál en la tabla de arriba
uv sync --all-extras
MODEL=qwen3:8b ./scripts/fase4_ollama.sh
```

El script deja en `simulations/fase4_logs/`:

| archivo | va a |
|---|---|
| `bench_{governor,president,union,media}.txt` | `docs/FASE4_BENCH_OLLAMA.md` (tabla por rol) |
| `run_llm_aurora.txt`, `run_llm_ar_2019.txt` | tiempos de corrida (sección "Tiempos") |
| `eval_llm.txt`, `eval_compare.txt` | tabla de evals (sección "Evals") |
| `compare_aurora.md`, `compare_ar_2019.md` | tablas de acciones/posiciones/denegadas/trazas (pegar tal cual) |
| `hardware.txt`, `model_*.txt` | tabla "Entorno" |

`scripts/fase4_compare_runs.py` (lo que genera `compare_*.md`) lee dos JSONL de `republica run` y
saca, para cada corrida: estado final (aprobación, inflación, desempleo, salario real, reservas,
tipo de cambio, protesta, apoyo en el Congreso), distribución de tipos de acción, posición por actor
(share de meses en SUPPORT/OPPOSE/NEGOTIATE/neutral) con la coincidencia mes a mes contra la gemela,
acciones denegadas por `authorize()` (total y fuera de rol, con motivos), y sobre las `DecisionTrace`:
`parse_rate`, intentos, `authority_violation_rate`, latencia p50/p90, tokens y ejemplos de fallos.

## Aurora, seed 7, 48 meses

Comandos (ADR 004 secc. 8):

```
uv run republica run --seed 7 --months 48 --brain rules --out simulations/run_rules_aurora.jsonl
uv run republica run --seed 7 --months 48 --brain llm:ollama:qwen3:8b --out simulations/run_llm_aurora.jsonl
```

### Estado final

| | `rules` | `llm:ollama:qwen3:8b` |
|---|---:|---:|
| meses simulados / outcome | 48 / `reelected` | pendiente |
| acciones registradas | 1383 | pendiente |
| `government_approval` final | 47.33 | pendiente |
| `inflation` final (% mensual) | 1.43 | pendiente |
| `unemployment` final | 7.61 | pendiente |
| `real_wage` final | 106.71 | pendiente |
| `reserves` final | 13830.76 | pendiente |
| `exchange_rate` final | 188.36 | pendiente |
| `protest_level` final | 10.58 | pendiente |
| `congress_support` final | 50.14 | pendiente |
| tiempo de corrida | 0.8 s | pendiente |

### Distribución de acciones (`rules`)

| tipo | n | % |
|---|---:|---:|
| NO_ACTION | 1108 | 80.1% |
| PUBLISH_STORY | 144 | 10.4% |
| RECOMMEND_RATE | 48 | 3.5% |
| PUBLIC_STATEMENT | 39 | 2.8% |
| SUPPORT_POLICY | 30 | 2.2% |
| NEGOTIATE | 14 | 1.0% |

Denegadas por `authorize()`: 0 de 1383 (0 fuera de rol). Con `rules`, Aurora seed 7 es una corrida
muy quieta: 27 de 28 actores están en `neutral` los 48 meses; solo `gov_patagonia` se mueve
(62 % de los meses en SUPPORT, 27 % en NEGOTIATE) y `party_movimiento_libertad` negocia una vez. Es
el contraste más interesante que puede ofrecer la columna LLM: cuánto de esa quietud es propiedad
del escenario y cuánto de las reglas.

### Posición por actor y coincidencia con la gemela LLM

Pendiente (`simulations/fase4_logs/compare_aurora.md`, sección "Posicion por actor").

### Trazas LLM (parse_rate, no autorizadas, latencia)

Pendiente (`compare_aurora.md`, sección "Trazas de llm:ollama:...").

## Argentina desde 2019-12, 48 meses, `--fx-regime auto`

`data/countries/argentina/calibration/a5_macro/coefficients.json` **no existe** en esta rama (solo
`a3_main`), así que las corridas van sin `--calibration` (el script lo agrega solo si aparece).

```
uv run republica run --country argentina --start 2019-12 --months 48 --fx-regime auto --seed 7 --brain rules --out simulations/run_rules_ar_2019.jsonl
uv run republica run --country argentina --start 2019-12 --months 48 --fx-regime auto --seed 7 --brain llm:ollama:qwen3:8b --out simulations/run_llm_ar_2019.jsonl
```

### Estado final

| | `rules` | `llm:ollama:qwen3:8b` |
|---|---:|---:|
| meses simulados / outcome | 25 / `hyperinflation` (corte terminal antes de los 48) | pendiente |
| acciones registradas | 916 | pendiente |
| `government_approval` final | 0.00 | pendiente |
| `inflation` final (% mensual) | 30.97 | pendiente |
| `unemployment` final | 11.66 | pendiente |
| `real_wage` final | 59.02 | pendiente |
| `reserves` final | 0.00 | pendiente |
| `exchange_rate` final | 327.15 | pendiente |
| `protest_level` final | 97.56 | pendiente |
| `congress_support` final | 37.72 | pendiente |
| tiempo de corrida | 0.8 s | pendiente |

### Distribución de acciones (`rules`)

| tipo | n | % |
|---|---:|---:|
| NO_ACTION | 365 | 39.8% |
| PUBLIC_STATEMENT | 183 | 20.0% |
| NEGOTIATE | 116 | 12.7% |
| OPPOSE_POLICY | 96 | 10.5% |
| PUBLISH_STORY | 75 | 8.2% |
| RECOMMEND_RATE | 25 | 2.7% |
| SUPPORT_POLICY | 23 | 2.5% |
| CALL_PROTEST | 11 | 1.2% |
| LOBBY_CONGRESS | 8 | 0.9% |
| REQUEST_FUNDS | 8 | 0.9% |
| STRIKE | 5 | 0.5% |
| WITHHOLD_INVESTMENT | 1 | 0.1% |

Denegadas: 2 de 916 (0.2 %), ambas `STRIKE` de `union_public` en cooldown; 0 fuera de rol.

### Posición por actor (`rules`, share de meses SUP/OPP/NEG/neutral)

| actor | SUP/OPP/NEG/neutral | actor | SUP/OPP/NEG/neutral |
|---|---|---|---|
| biz_agro | 4/0/20/76 | gov_norte | 0/8/24/68 |
| biz_finance | 4/16/20/60 | gov_pampa | 0/48/12/40 |
| biz_industry | 0/0/32/68 | gov_patagonia | 28/0/44/28 |
| bloc_informal | 0/36/0/64 | media_* (3) | 0/0/0/100 |
| bloc_middle_class | 0/16/0/84 | minister_economy | 0/4/28/68 |
| bloc_public_employees | 0/32/0/68 | party_alianza_provincial | 0/0/0/100 |
| bloc_rural | 0/0/0/100 | party_frente_federal | 0/0/0/100 |
| bloc_urban_workers | 0/32/0/68 | party_movimiento_libertad | 16/0/28/56 |
| central_bank | 0/0/0/100 | party_partido_social | 0/0/24/76 |
| gov_capital | 32/0/36/32 | party_union_republicana | 4/0/32/64 |
| gov_centro | 0/0/0/100 | union_cgt | 0/32/52/16 |
| gov_costa | 0/60/32/8 | union_public | 0/36/48/16 |
| gov_cuyo | 4/4/24/68 | | |
| gov_litoral | 0/60/8/32 | | |

Nota: los ids de actor de la corrida son los genéricos de Aurora (`gov_costa`,
`party_frente_federal`...), no los de la época 2015–2023 (`gov_buenos_aires`, `party_fpv_fdt_pj`...):
`republica run --country argentina --start 2019-12` carga el paquete de país (macro, régimen, series,
lealtades) pero no reemplaza el elenco por el de `eras/2015-2023/actors/` (eso hoy lo hace el backtest
de ADR 014 vía `pack.era.actors`, no `run`). Vale para las dos columnas por igual, así que la
comparación sigue siendo entre pares, pero hay que tenerlo en cuenta antes de leer "coherencia
ideológica" como coherencia con actores argentinos reales.

Columna LLM, coincidencia y trazas: pendiente (`simulations/fase4_logs/compare_ar_2019.md`).

## Evals (ADR 007), suite `all`, juez `fake`, seed 7

`uv run republica eval --suite all --brain rules --judge fake --seed 7 --out simulations/evals_rules`
(reporte en `simulations/evals_rules/report.md`). El juez tiene que ser `fake` o un modelo
**distinto** al del actor (ADR 007 secc. 3: `build_judge` rechaza el mismo modelo), así que con un
solo modelo en Ollama las 4 métricas con juez se comparan con juez `fake` en ambas columnas.

| métrica | `rules` | IC 95 % | N | `llm:ollama:qwen3:8b` |
|---|---:|---|---:|---:|
| ideological_consistency | 1.000 | [1.000, 1.000] | 20 | pendiente |
| interest_consistency | 1.000 | [1.000, 1.000] | 12 | pendiente |
| authority_violation | 0.000 | - | 153 | pendiente |
| parse_rate | - (reglas no trazan) | - | 0 | pendiente |
| strategic_adaptation | 0.308 | - | 13 | pendiente |
| diversity | 0.693 | [0.662, 0.724] | 20 | pendiente |
| temporal_consistency | 0.000 | [0.000, 0.000] | 6 | pendiente |
| memory_recall | - (sin memorias ≥ 0.8) | - | 0 | pendiente |
| hallucination | - (reglas no redactan) | - | 0 | pendiente |
| political_realism | 4.000 | - | 1 | pendiente |

`uv run republica eval compare simulations/evals_rules simulations/evals_llm` marca qué métricas
difieren fuera del IC 95 % (pendiente).

## Tiempos

| paso | `rules` | LLM |
|---|---:|---:|
| Aurora 48 meses (28 actores, 1344 decisiones) | 0.8 s | pendiente |
| Argentina 2019-12 (25 meses, 700 decisiones) | 0.8 s | pendiente |
| `bench-parse` ×4 roles (200 llamadas) | n/a | pendiente |
| evals suite `all` | 14 s | pendiente |

Orden de magnitud para dimensionar la máquina: cada decisión LLM es una llamada con un prompt
(system + user renderizados) de ~2.8k caracteres de media y ~3.0k en p90 en las trazas `fake:rules`
de estas dos corridas, o sea del orden de 700–800 tokens (estimación chars/4; el `tokens.prompt` que
guarda `FakeBackend` cuenta solo el system, no sirve para esto), y hasta `num_predict=800` de salida.
Aurora completa son 1344 llamadas, Argentina hasta 1344 (700 si vuelve a cortar en el mes 25). En CPU
sin GPU hay que contar horas (decenas con un 8B) por corrida completa; con GPU, del orden de 1–3 s
por llamada.

## Verificación de la tubería sin LLM (no es un resultado LLM)

Con `--brain fake:rules` (mismo pipeline `Perception → prompt → JSON → ActorDecision → to_actions →
authorize`, decisión delegada a las reglas) y el mismo seed:

- Aurora: estado final idéntico a `rules` en los 8 indicadores, 1383/1383 acciones, 1344 trazas con
  `parse_rate` 1.000 y 0 violaciones de rol, coincidencia de posición 100 % en los 28 actores.
- Argentina: estado final idéntico, 700 trazas, `parse_rate` 1.000, 0 violaciones, coincidencia 100 %.
  Única diferencia: 890 acciones registradas vs. 916, porque tres bloques sociales
  (`bloc_informal`, `bloc_urban_workers`, `bloc_public_employees`) registran menos `NO_ACTION` por el
  camino LLM (7–9 vs. 16–17). No cambia ninguna acción autorizada ni el estado; queda anotado por si
  a alguien le llama la atención el conteo al comparar con la columna LLM.

Esto valida el script de comparación y los comandos, no dice nada sobre el modelo.

## Qué no se puede concluir

- **Nada sobre el LLM todavía**: las columnas LLM están vacías. Todo lo de arriba describe las
  reglas y el escenario, no al modelo.
- **Una semilla no es evidencia.** Aunque se completen las columnas, Aurora seed 7 y Argentina
  2019-12 seed 7 son una realización cada una. Con reglas, otra semilla cambia el outcome (ADR 008
  corre cientos por experimento). Cualquier diferencia LLM vs. reglas en un indicador final puede ser
  ruido de la trayectoria, no propiedad del cerebro; hace falta el barrido de ADR 008 (`republica
  experiment run`) con ≥ 30 semillas y `CachedBackend` para decir algo.
- **La coincidencia de posición mes a mes no mide exactitud.** Solo el mes 1 arranca de la misma
  percepción en las dos corridas; después divergen y cada actor reacciona a mundos distintos.
- **`ideological_consistency`/`interest_consistency` de las reglas valen 1.000 por construcción**
  (las reglas son la definición de la métrica); que el LLM dé menos no significa que sea "menos
  coherente" en un sentido humano, sino que se aparta del baseline por reglas.
- **`authority_violation` con `rules` es 0 por construcción** (el catálogo del rol es el input de las
  reglas). Para el LLM es la métrica de interés: mide cuántas veces pide acciones fuera de rol, que
  `authorize()` deniega sin romper la corrida.
- **El elenco de Argentina es el genérico de Aurora** (ver nota arriba): "coherencia ideológica en
  Argentina 2019" es coherencia con fichas genéricas, no con actores de la época.
- **Argentina corta en el mes 25 por hiperinflación con reglas**: si la corrida LLM también corta,
  la comparación es sobre 25 meses; si no corta, no son comparables mes a mes después del 25.
- **Sin `a5_macro`** las corridas argentinas van con coeficientes sin calibrar (los del paquete),
  así que los niveles absolutos de inflación/tipo de cambio no se comparan con la historia real.
