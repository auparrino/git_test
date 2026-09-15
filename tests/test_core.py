"""Tests del hito 1 de la CPU social (ADR 010 secc. 7). Requiere el extra
opcional `core` (`uv sync --group dev --extra core`, instala `numpy`); todo
el modulo se saltea si no esta instalado, igual que `test_ml_ui.py` con
`sklearn`/`streamlit`."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy")

from republica.core.classify import BLACKLIST_WORDS  # noqa: E402
from republica.core.run import run_batch, simulate  # noqa: E402
from republica.core.world import DEFAULT_GOODS, CoreConfig  # noqa: E402

_CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "republica" / "core"


# --------------------------------------------------------------------------
# Determinismo
# --------------------------------------------------------------------------


def test_same_seed_produces_identical_run() -> None:
    cfg = CoreConfig(n_agents=200, turns=30, seed=7)
    r1 = simulate(cfg)
    r2 = simulate(cfg)
    assert r1["metrics"] == r2["metrics"]
    assert r1["classification"] == r2["classification"]


def test_different_seeds_diverge() -> None:
    cfg = CoreConfig(n_agents=200, turns=30)
    r1 = simulate(cfg, seed=1)
    r2 = simulate(cfg, seed=2)
    assert r1["metrics"] != r2["metrics"]


# --------------------------------------------------------------------------
# Rendimiento (ADR secc. 7: "1.000 agentes x 100 turnos < 5s" es el target
# de test explicito de la tarea; el target de 10.000 x 500 < 60s se
# demuestra en `experiments/results/core_hito1/` y en el reporte, no como
# assert de CI -- correrlo siempre en la suite haria el `pytest` normal
# demasiado lento).
# --------------------------------------------------------------------------


def test_performance_1000_agents_100_turns_under_5s() -> None:
    cfg = CoreConfig(n_agents=1000, turns=100, seed=3)
    start = time.monotonic()
    simulate(cfg)
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"tardo {elapsed:.2f}s (limite 5s)"


@pytest.mark.slow
def test_performance_10000_agents_500_turns_under_60s() -> None:
    cfg = CoreConfig(n_agents=10_000, turns=500, seed=7)
    start = time.monotonic()
    simulate(cfg)
    elapsed = time.monotonic() - start
    assert elapsed < 60.0, f"tardo {elapsed:.2f}s (limite 60s)"


# --------------------------------------------------------------------------
# Test de contaminacion (ADR 010 secc. 3, literal): la lista negra de
# identificadores solo puede aparecer en `classify.py` (etiquetado a
# posteriori) o en un comentario que diga explicitamente "no hardcodeado".
# --------------------------------------------------------------------------


def test_no_institutional_contamination() -> None:
    pattern = re.compile(r"\b(" + "|".join(BLACKLIST_WORDS) + r")\b", re.IGNORECASE)
    violations: list[str] = []
    for path in sorted(_CORE_DIR.glob("*.py")):
        if path.name == "classify.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "no hardcodeado" in line.lower():
                continue
            for match in pattern.finditer(line):
                violations.append(f"{path.name}:{lineno}: {match.group(0)!r} -> {line.strip()!r}")
    assert not violations, "contaminacion institucional en core/ (ADR secc. 3):\n" + "\n".join(
        violations
    )


def test_blacklist_words_used_in_docs() -> None:
    """El ADR mismo (docs) SI puede nombrar estas palabras (es la tabla de
    la seccion 3); solo el codigo de `core/` (salvo `classify.py`) esta
    restringido."""
    adr = (Path(__file__).resolve().parents[1] / "docs" / "ADR_010_social_cpu.md").read_text(
        encoding="utf-8"
    )
    assert "money" in adr


# --------------------------------------------------------------------------
# Control negativo / sanidad positiva (ADR secc. 7 DoD).
#
# Hallazgo empirico (documentado en "Notas de implementacion" al pie del
# ADR): bajar la durabilidad de los 6 bienes a 0.6 SIN mas cambios NO alcanza
# para suprimir la emergencia en esta implementacion -- conchas gana igual
# en practicamente el 100% de las semillas, porque lo que la vuelve
# candidata a intermediario no es (solo) su durabilidad sino que NADIE la
# necesita (su "surplus" nunca se consume, se acumula sea cual sea la
# durabilidad, mientras produccion la repone cada turno). El control
# negativo real -- el que efectivamente prueba la hipotesis de que hace
# falta ALGUNA ventaja fisica para que emerja un intermediario -- quita esa
# ventaja estructural (todos los bienes necesitados por todos) ADEMAS de
# aplanar la durabilidad; ver el ADR para la discusion completa.
# --------------------------------------------------------------------------

_NEGATIVE_CONTROL_GOODS = tuple(
    g.model_copy(update={"durability": 0.6, "consumed_by": "all", "need_qty": g.need_qty or 0.3})
    for g in DEFAULT_GOODS
)

_SANITY_N_AGENTS = 300
_SANITY_TURNS = 300
_SANITY_SEEDS = 20


@pytest.mark.slow
def test_negative_control_no_durable_goods_no_medium_emerges() -> None:
    no_emerged = 0
    for seed in range(_SANITY_SEEDS):
        cfg = CoreConfig(
            n_agents=_SANITY_N_AGENTS, turns=_SANITY_TURNS, seed=seed, goods=_NEGATIVE_CONTROL_GOODS
        )
        result = simulate(cfg)
        if result["classification"]["medium_of_exchange"] is None:
            no_emerged += 1
    frac = no_emerged / _SANITY_SEEDS
    assert frac >= 0.9, f"solo {no_emerged}/{_SANITY_SEEDS} corridas sin medio de intercambio"


@pytest.mark.slow
def test_positive_sanity_default_config_medium_emerges() -> None:
    emerged = 0
    for seed in range(_SANITY_SEEDS):
        cfg = CoreConfig(n_agents=_SANITY_N_AGENTS, turns=_SANITY_TURNS, seed=seed)
        result = simulate(cfg)
        if result["classification"]["medium_of_exchange"] is not None:
            emerged += 1
    frac = emerged / _SANITY_SEEDS
    assert frac >= 0.5, f"solo {emerged}/{_SANITY_SEEDS} corridas con medio de intercambio"


# --------------------------------------------------------------------------
# Conservacion de inventario en los swaps.
# --------------------------------------------------------------------------


def test_swap_conserves_total_inventory() -> None:
    """Con durabilidad 1.0, necesidades 0 (nadie consume) y produccion 0,
    lo UNICO que puede mover inventario entre turnos son los `OFFER`
    ejecutados -- son trueques, deben conservar el total exactamente."""
    from republica.core import exchange
    from republica.core.world import init_world

    no_decay_goods = tuple(
        g.model_copy(update={"durability": 1.0, "consumed_by": "none", "need_qty": 0.0})
        for g in DEFAULT_GOODS
    )
    no_production_regions = tuple(
        r.model_copy(update={"production_rate": 0.0}) for r in CoreConfig().regions
    )
    cfg = CoreConfig(
        n_agents=300,
        turns=10,
        seed=5,
        goods=no_decay_goods,
        regions=no_production_regions,
        deprivation_threshold=10_000,  # nadie muere (no hay privacion posible)
    )
    world = init_world(cfg, cfg.seed)
    rng = numpy.random.default_rng(cfg.seed)

    total_before = float(world.inventories.sum())
    for turn in range(cfg.turns):
        exchange.step(world, cfg, rng, turn)
        total_now = float(world.inventories.sum())
        assert total_now == pytest.approx(total_before, abs=1e-6), (
            f"turno {turn}: total {total_now} != {total_before}"
        )


# --------------------------------------------------------------------------
# Muerte y reemplazo: N constante.
# --------------------------------------------------------------------------


def test_dead_agents_are_replaced_population_stays_constant() -> None:
    from republica.core.world import init_world

    cfg = CoreConfig(
        n_agents=200, turns=25, seed=9, deprivation_threshold=3, deprivation_recovery=0
    )
    world = init_world(cfg, cfg.seed)
    rng = numpy.random.default_rng(cfg.seed)

    from republica.core import exchange

    total_deaths = 0
    n0 = world.inventories.shape[0]
    for turn in range(cfg.turns):
        metrics = exchange.step(world, cfg, rng, turn)
        total_deaths += metrics.deaths
        assert world.inventories.shape[0] == n0
        assert world.region.shape[0] == n0
        assert world.deprivation.shape[0] == n0

    assert total_deaths > 0, "con deprivation_threshold=3 se esperaban muertes"
    assert (world.deprivation <= cfg.deprivation_threshold).all()


# --------------------------------------------------------------------------
# El reporte contiene las 4 hipotesis con veredicto.
# --------------------------------------------------------------------------


def test_report_contains_h1_to_h4_verdicts(tmp_path: Path) -> None:
    from republica.core.classify import build_report

    main_dir = tmp_path / "main"
    shell_dir = tmp_path / "shell_sweep"
    transport_dir = tmp_path / "transport_sweep"

    cfg = CoreConfig(n_agents=150, turns=60, seed=0)
    run_batch(cfg, [0, 1, 2], main_dir, workers=1)

    for level, abundance in (("0.3", 0.3), ("1.0", 1.0), ("3.0", 3.0)):
        run_batch(
            cfg.model_copy(update={"shell_abundance": abundance}),
            [0, 1],
            shell_dir / level,
            workers=1,
        )
    for level, transport in (("0.0", 0.0), ("0.1", 0.1), ("0.2", 0.2)):
        run_batch(
            cfg.model_copy(update={"transport_cost": transport}),
            [0, 1],
            transport_dir / level,
            workers=1,
        )

    report_path = main_dir / "report.md"
    build_report(
        main_dir,
        shell_sweep_dir=shell_dir,
        transport_sweep_dir=transport_dir,
        out_path=report_path,
    )

    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    for h in ("H1", "H2", "H3", "H4"):
        assert h in text
    for label in ("CUMPLIDA", "NO CUMPLIDA"):
        assert label in text
    assert "Limitaciones" in text
    assert "no son evidencia sobre economías reales" in text


# --------------------------------------------------------------------------
# CLI batch: JSON valido por semilla.
# --------------------------------------------------------------------------


def test_run_batch_writes_one_json_per_seed(tmp_path: Path) -> None:
    cfg = CoreConfig(n_agents=100, turns=15, seed=0)
    result = run_batch(cfg, [0, 1, 2], tmp_path / "batch", workers=1)
    assert result["n_ok"] == 3
    assert result["n_failed"] == 0
    for seed in (0, 1, 2):
        path = tmp_path / "batch" / f"run_{seed}.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["seed"] == seed
        assert len(data["metrics"]) == 15
