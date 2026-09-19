# Fase 4 con Ollama local en Windows (ADR 004, docs/OLLAMA_SETUP.md).
# Puerto de `scripts/fase4_ollama.sh` a PowerShell: mismos pasos, mismos
# comandos de `republica`, mismos archivos de salida en
# `simulations/fase4_logs/` (incluido el formato "real XmY.Zs" del tiempo de
# pared, que `scripts/fase4_collect_results.py` sabe leer).
#
#   .\scripts\fase4_ollama.ps1
#   .\scripts\fase4_ollama.ps1 -Model qwen3:4b          # maquina chica
#   .\scripts\fase4_ollama.ps1 -Steps bench             # solo el benchmark
#   .\scripts\fase4_ollama.ps1 -Steps aurora,argentina  # solo las corridas
#   .\scripts\fase4_ollama.ps1 -TimeoutSeconds 180      # CPU lenta, sin GPU
#
# Requisitos: Ollama corriendo (el instalador de Windows lo deja como
# servicio), `ollama pull <modelo>` hecho, `uv sync --all-extras` corrido en
# la carpeta del repo.
#
# Si PowerShell se niega a ejecutar el script ("no se puede cargar porque la
# ejecucion de scripts esta deshabilitada"), corre una vez:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

[CmdletBinding()]
param(
    [string]$Model = "qwen3:8b",
    [int]$Seed = 7,
    [int]$Months = 48,
    [int]$NBench = 50,
    [string[]]$Steps = @("bench", "aurora", "argentina", "evals", "compare", "collect"),
    [int]$TimeoutSeconds = 120,
    [string]$Calibration = ""
)

# `Continue`, no `Stop`: con `Stop`, CUALQUIER linea que un comando nativo
# escriba en stderr (un traceback, un warning de Python, una barra de
# progreso) se convierte en `NativeCommandError` y PowerShell corta el script
# mostrando SOLO la primera linea -- justo la parte inutil del error. Los
# fallos reales se detectan por `$LASTEXITCODE` en `Invoke-Logged`.
$ErrorActionPreference = "Continue"

# Ubicarse en la raiz del repo (este script vive en scripts/).
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$brain = "llm:ollama:$Model"
$logs = Join-Path "simulations" "fase4_logs"
New-Item -ItemType Directory -Force -Path "simulations", $logs | Out-Null

# Timeout por decision del backend (60 s es el literal del ADR 004; en CPU
# sin GPU un modelo de 8B puede necesitar mas).
$env:REPUBLICA_OLLAMA_TIMEOUT = "$TimeoutSeconds"

# `--calibration <id>`: la mejor calibracion disponible, en orden de
# preferencia (ver docs/CALIBRATION_LOG.md).
$calibArgs = @()
foreach ($cand in @($Calibration, "a7_by_regime", "a5b_macro", "a5_macro", "a3_main")) {
    if ([string]::IsNullOrWhiteSpace($cand)) { continue }
    if (Test-Path "data/countries/argentina/calibration/$cand/coefficients.json") {
        $calibArgs = @("--calibration", $cand)
        break
    }
}

function Write-Log([string]$Message) {
    Write-Host ""
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message) -ForegroundColor Cyan
}

function Test-Step([string]$Name) {
    return $Steps -contains $Name
}

# Corre `uv run <args>`, muestra la salida, la guarda en $LogFile y agrega al
# final la linea "real XmY.Zs" con el mismo formato que `time` en bash, que es
# lo que lee `scripts/fase4_collect_results.py`.
function Invoke-Logged([string]$LogFile, [string[]]$UvArgs) {
    $started = Get-Date
    # `-Variable` (no `-FilePath`) para que la salida se vea en vivo y el
    # archivo se escriba despues con codificacion explicita: `Tee-Object
    # -FilePath` no acepta `-Encoding` en Windows PowerShell 5.1 y guardaria
    # UTF-16, que el recolector no lee bien.
    # `ForEach-Object { "$_" }` fuerza cada registro de error de un comando
    # nativo a texto plano ANTES del Tee: sin eso, PowerShell los renderiza
    # como `ErrorRecord` y el log guarda el objeto, no el mensaje.
    & uv run @UvArgs 2>&1 | ForEach-Object { "$_" } | Tee-Object -Variable captured | Out-Host
    $code = $LASTEXITCODE
    $elapsed = (Get-Date) - $started
    $line = "real {0}m{1:F3}s" -f [int]$elapsed.TotalMinutes, ($elapsed.TotalSeconds % 60)
    ($captured + $line) | Out-File -FilePath $LogFile -Encoding utf8
    Write-Host $line
    if ($code -ne 0) {
        Write-Host ""
        Write-Host "El paso fallo (codigo $code). Salida completa en: $LogFile" -ForegroundColor Red
        Write-Host "Si dice 'No se pudo conectar con Ollama', arranca el servicio y volve a correr." -ForegroundColor Red
        exit $code
    }
}

$calibLabel = if ($calibArgs.Count -gt 0) { $calibArgs[1] } else { "ninguna" }
Write-Log "modelo=$Model brain=$brain seed=$Seed meses=$Months calibracion=$calibLabel timeout=${TimeoutSeconds}s"

# Hardware y modelo, para la tabla "Entorno" del documento de resultados.
$hardware = Join-Path $logs "hardware.txt"
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
@(
    "$($os.Caption) $($os.Version) ($($os.OSArchitecture))"
    "CPU: $($cpu.Name) -- $($env:NUMBER_OF_PROCESSORS) procesadores logicos"
    "RAM total: {0:N1} GiB" -f ($cs.TotalPhysicalMemory / 1GB)
    "PowerShell: $($PSVersionTable.PSVersion)"
) | Set-Content -Path $hardware -Encoding utf8
try { & nvidia-smi --query-gpu=name,memory.total --format=csv 2>&1 | Add-Content -Path $hardware } catch { }
try { & ollama --version 2>&1 | Add-Content -Path $hardware } catch { }
$modelSlug = $Model -replace '[:/\\]', '_'
try { & ollama show $Model 2>&1 | Set-Content -Path (Join-Path $logs "model_$modelSlug.txt") } catch { }

if (Test-Step "bench") {
    foreach ($role in @("governor", "president", "union", "media")) {
        Write-Log "bench-parse role=$role"
        Invoke-Logged (Join-Path $logs "bench_$role.txt") @(
            "republica", "bench-parse", "--brain", $brain,
            "--n", "$NBench", "--role", $role, "--seed", "$Seed"
        )
    }
}

if (Test-Step "aurora") {
    Write-Log "Aurora rules"
    Invoke-Logged (Join-Path $logs "run_rules_aurora.txt") @(
        "republica", "run", "--seed", "$Seed", "--months", "$Months",
        "--brain", "rules", "--out", "simulations/run_rules_aurora.jsonl"
    )
    Write-Log "Aurora $brain"
    Invoke-Logged (Join-Path $logs "run_llm_aurora.txt") @(
        "republica", "run", "--seed", "$Seed", "--months", "$Months",
        "--brain", $brain, "--out", "simulations/run_llm_aurora.jsonl"
    )
}

if (Test-Step "argentina") {
    Write-Log "Argentina 2019-12 rules"
    Invoke-Logged (Join-Path $logs "run_rules_ar_2019.txt") (@(
        "republica", "run", "--country", "argentina", "--start", "2019-12",
        "--months", "$Months", "--fx-regime", "auto"
    ) + $calibArgs + @(
        "--seed", "$Seed", "--brain", "rules", "--out", "simulations/run_rules_ar_2019.jsonl"
    ))
    Write-Log "Argentina 2019-12 $brain"
    Invoke-Logged (Join-Path $logs "run_llm_ar_2019.txt") (@(
        "republica", "run", "--country", "argentina", "--start", "2019-12",
        "--months", "$Months", "--fx-regime", "auto"
    ) + $calibArgs + @(
        "--seed", "$Seed", "--brain", $brain, "--out", "simulations/run_llm_ar_2019.jsonl"
    ))
}

if (Test-Step "evals") {
    Write-Log "evals rules"
    Invoke-Logged (Join-Path $logs "eval_rules.txt") @(
        "republica", "eval", "--suite", "all", "--brain", "rules",
        "--judge", "fake", "--seed", "$Seed", "--out", "simulations/evals_rules"
    )
    Write-Log "evals $brain (juez fake: el juez LLM no puede ser el mismo modelo que el actor)"
    Invoke-Logged (Join-Path $logs "eval_llm.txt") @(
        "republica", "eval", "--suite", "all", "--brain", $brain,
        "--judge", "fake", "--seed", "$Seed", "--out", "simulations/evals_llm"
    )
    Invoke-Logged (Join-Path $logs "eval_compare.txt") @(
        "republica", "eval", "compare", "simulations/evals_rules", "simulations/evals_llm"
    )
}

if (Test-Step "compare") {
    Write-Log "comparacion de corridas (acciones, posiciones, denegadas, trazas)"
    & uv run python scripts/fase4_compare_runs.py `
        simulations/run_rules_aurora.jsonl simulations/run_llm_aurora.jsonl `
        --label-a rules --label-b $brain --out (Join-Path $logs "compare_aurora.md")
    & uv run python scripts/fase4_compare_runs.py `
        simulations/run_rules_ar_2019.jsonl simulations/run_llm_ar_2019.jsonl `
        --label-a rules --label-b $brain --out (Join-Path $logs "compare_ar_2019.md")
}

if (Test-Step "collect") {
    Write-Log "recolectando resultados"
    & uv run python scripts/fase4_collect_results.py --logs $logs --model $Model
}

Write-Log "listo: ver $logs (resumen en $logs\RESULTADOS.md)"
