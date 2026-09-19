#!/usr/bin/env bash
# Fase 4 con Ollama local (ADR 004, docs/OLLAMA_SETUP.md): benchmark de parseo
# por rol + corridas Aurora y Argentina 2019-12 con actores LLM y sus gemelas
# por reglas + evals + comparacion de trazas. Todo lo que sale va a
# `simulations/` (gitignored); las salidas de consola se guardan en
# `simulations/fase4_logs/` para pasarlas a docs/FASE4_BENCH_OLLAMA.md y
# docs/FASE4_RESULTS_OLLAMA.md.
#
#   MODEL=qwen3:8b ./scripts/fase4_ollama.sh            # default
#   MODEL=qwen3:4b ./scripts/fase4_ollama.sh            # maquina chica
#   STEPS=bench ./scripts/fase4_ollama.sh               # solo el paso 2
#   STEPS="aurora argentina" ./scripts/fase4_ollama.sh  # solo corridas
#   CALIBRATION=a5b_macro ./scripts/fase4_ollama.sh     # forzar una calibracion
#   REPUBLICA_OLLAMA_TIMEOUT=180 ./scripts/fase4_ollama.sh  # CPU lenta
#   En Windows: correrlo desde WSL o Git Bash (usa bash, time, tee).
#
# Requisitos: `ollama serve` corriendo (OLLAMA_HOST si no es localhost:11434),
# `ollama pull $MODEL`, `uv sync --all-extras`.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:-qwen3:8b}"
BRAIN="llm:ollama:${MODEL}"
SEED="${SEED:-7}"
MONTHS="${MONTHS:-48}"
N_BENCH="${N_BENCH:-50}"
STEPS="${STEPS:-bench aurora argentina evals compare collect}"
LOGS=simulations/fase4_logs
mkdir -p simulations "$LOGS"

# `--calibration <id>`: la mejor calibracion disponible en el repo, en orden
# de preferencia (ver docs/CALIBRATION_LOG.md); CALIBRATION=<id> la fuerza.
CALIB=()
for cand in "${CALIBRATION:-}" a7_by_regime a5b_macro a5_macro a3_main; do
  if [[ -n "$cand" && -f "data/countries/argentina/calibration/$cand/coefficients.json" ]]; then
    CALIB=(--calibration "$cand")
    break
  fi
done

# Timeout por decision del backend Ollama (segundos). 60 s es el literal del
# ADR 004; en CPU sin GPU un 8B puede necesitar mas: REPUBLICA_OLLAMA_TIMEOUT=180.
export REPUBLICA_OLLAMA_TIMEOUT="${REPUBLICA_OLLAMA_TIMEOUT:-120}"

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
has_step() { [[ " $STEPS " == *" $1 "* ]]; }

log "modelo=$MODEL brain=$BRAIN seed=$SEED meses=$MONTHS calibracion=${CALIB[*]:-ninguna} timeout=${REPUBLICA_OLLAMA_TIMEOUT}s"
{ uname -a; nproc; free -g | head -2; (nvidia-smi --query-gpu=name,memory.total --format=csv 2>/dev/null || true); ollama --version; } \
  > "$LOGS/hardware.txt" 2>&1 || true
ollama show "$MODEL" > "$LOGS/model_${MODEL//[:\/]/_}.txt" 2>&1 || true

if has_step bench; then
  for role in governor president union media; do
    log "bench-parse role=$role"
    { time uv run republica bench-parse --brain "$BRAIN" --n "$N_BENCH" --role "$role" --seed "$SEED"; } \
      2>&1 | tee "$LOGS/bench_${role}.txt"
  done
fi

if has_step aurora; then
  log "Aurora rules"
  { time uv run republica run --seed "$SEED" --months "$MONTHS" --brain rules \
      --out simulations/run_rules_aurora.jsonl; } 2>&1 | tee "$LOGS/run_rules_aurora.txt"
  log "Aurora $BRAIN"
  { time uv run republica run --seed "$SEED" --months "$MONTHS" --brain "$BRAIN" \
      --out simulations/run_llm_aurora.jsonl; } 2>&1 | tee "$LOGS/run_llm_aurora.txt"
fi

if has_step argentina; then
  log "Argentina 2019-12 rules"
  { time uv run republica run --country argentina --start 2019-12 --months "$MONTHS" --fx-regime auto \
      "${CALIB[@]}" --seed "$SEED" --brain rules --out simulations/run_rules_ar_2019.jsonl; } \
    2>&1 | tee "$LOGS/run_rules_ar_2019.txt"
  log "Argentina 2019-12 $BRAIN"
  { time uv run republica run --country argentina --start 2019-12 --months "$MONTHS" --fx-regime auto \
      "${CALIB[@]}" --seed "$SEED" --brain "$BRAIN" --out simulations/run_llm_ar_2019.jsonl; } \
    2>&1 | tee "$LOGS/run_llm_ar_2019.txt"
fi

if has_step evals; then
  log "evals rules"
  uv run republica eval --suite all --brain rules --judge fake --seed "$SEED" \
    --out simulations/evals_rules 2>&1 | tee "$LOGS/eval_rules.txt"
  log "evals $BRAIN (juez fake: el juez LLM no puede ser el mismo modelo que el actor, ADR 007 secc. 3)"
  { time uv run republica eval --suite all --brain "$BRAIN" --judge fake --seed "$SEED" \
      --out simulations/evals_llm; } 2>&1 | tee "$LOGS/eval_llm.txt"
  uv run republica eval compare simulations/evals_rules simulations/evals_llm 2>&1 \
    | tee "$LOGS/eval_compare.txt"
fi

if has_step compare; then
  log "comparacion de corridas (acciones, posiciones, denegadas, trazas)"
  uv run python scripts/fase4_compare_runs.py simulations/run_rules_aurora.jsonl \
    simulations/run_llm_aurora.jsonl --label-a rules --label-b "$BRAIN" \
    --out "$LOGS/compare_aurora.md"
  uv run python scripts/fase4_compare_runs.py simulations/run_rules_ar_2019.jsonl \
    simulations/run_llm_ar_2019.jsonl --label-a rules --label-b "$BRAIN" \
    --out "$LOGS/compare_ar_2019.md"
fi

if has_step collect; then
  log "recolectando resultados en $LOGS/RESULTADOS.md"
  uv run python scripts/fase4_collect_results.py --logs "$LOGS" --model "$MODEL"
fi

log "listo: ver $LOGS/ (resumen en $LOGS/RESULTADOS.md)"
