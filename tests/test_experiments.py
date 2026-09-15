"""Tests de aceptacion de ADR 008 (Fase 8: experimentos en lote, DuckDB,
comparacion de modelos), seccion 7: 2 brazos x 4 semillas con --workers 2
escribe 8 JSONL + runs.meta; resume corre exactamente los 2 borrados; load
crea las tablas con count(*) = 8 y recargar no duplica; report tiene
"Limitaciones" y una tabla por brazo; sweep 2x2 -> 4 brazos deterministas;
un override dot-path cambia el valor esperado y el config_hash del brazo.
Mas: el extractor de metricas sobre una corrida chica, y Cliff's delta
sobre un ejemplo conocido."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from republica.cli import app
from republica.experiments.config import ExperimentConfig
from republica.experiments.report import LIMITATIONS_SENTENCE, build_report, cliffs_delta
from republica.experiments.runner import (
    experiment_status,
    extract_run_metrics,
    resume_experiment,
    run_experiment,
)
from republica.world.config import load_country

runner = CliRunner()

try:
    import duckdb  # noqa: F401

    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False


def _write_yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "exp.yaml"
    p.write_text(textwrap.dedent(text))
    return p


_TWO_ARM_YAML = """\
    name: dod_test
    description: hipotesis de prueba para el DoD de ADR 008
    base:
      months: 6
      brains: rules
    seeds: {start: 0, count: 4}
    arms:
      dependent: {governance: {central_bank: {autonomy: 2}}}
      independent: {governance: {central_bank: {autonomy: 4}}}
    metrics: [outcome, inflation_annual_final, unemployment_final]
    """


# ---------------------------------------------------------------------------
# 1. 2 brazos x 4 semillas, --workers 2 -> 8 JSONL + runs.meta.
# ---------------------------------------------------------------------------


def test_run_writes_8_jsonl_and_meta(tmp_path: Path) -> None:
    yaml_path = _write_yaml(tmp_path, _TWO_ARM_YAML)
    out = tmp_path / "out"
    result = run_experiment(yaml_path, out, workers=2)

    assert result["n_tasks"] == 8
    assert result["n_ok"] == 8
    assert result["n_failed"] == 0
    jsonl_files = sorted(out.glob("*/*.jsonl"))
    assert len(jsonl_files) == 8
    assert (out / "runs.meta.json").exists()
    meta = json.loads((out / "runs.meta.json").read_text())
    assert meta["experiment_name"] == "dod_test"
    assert set(meta["arms"]) == {"dependent", "independent"}
    assert (out / "metrics.csv").exists()


# ---------------------------------------------------------------------------
# 2. resume tras borrar 2 JSONL vuelve a correr exactamente esos 2.
# ---------------------------------------------------------------------------


def test_resume_reruns_exactly_the_missing_pair(tmp_path: Path) -> None:
    yaml_path = _write_yaml(tmp_path, _TWO_ARM_YAML)
    out = tmp_path / "out"
    run_experiment(yaml_path, out, workers=2)

    (out / "dependent" / "1.jsonl").unlink()
    (out / "independent" / "3.jsonl").unlink()
    status = experiment_status(out)
    assert status["arms"]["dependent"]["missing"] == [1]
    assert status["arms"]["independent"]["missing"] == [3]

    result = resume_experiment(out, workers=2)
    assert result["n_tasks"] == 2
    assert result["n_ok"] == 2

    status_after = experiment_status(out)
    assert status_after["arms"]["dependent"]["missing"] == []
    assert status_after["arms"]["independent"]["missing"] == []
    assert len(list(out.glob("*/*.jsonl"))) == 8


# ---------------------------------------------------------------------------
# 3. load crea las tablas, count(*) FROM runs = 8; recargar no duplica.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DUCKDB, reason="duckdb no esta instalado (extra opcional 'analysis')")
def test_load_creates_tables_and_is_idempotent(tmp_path: Path) -> None:
    from republica.experiments.store import load_experiment, open_db

    yaml_path = _write_yaml(tmp_path, _TWO_ARM_YAML)
    out = tmp_path / "out"
    run_experiment(yaml_path, out, workers=2)

    db_path = tmp_path / "test.duckdb"
    result = load_experiment(out, db_path)
    assert result["runs_seen"] == 8

    con = open_db(db_path)
    try:
        assert con.execute("SELECT count(*) FROM runs").fetchone()[0] == 8
        for table in ("months", "actions", "negotiations", "votes", "elections", "traces", "evals"):
            con.execute(f"SELECT count(*) FROM {table}")  # no lanza: la tabla existe
    finally:
        con.close()

    load_experiment(out, db_path)  # recargar
    con = open_db(db_path)
    try:
        assert con.execute("SELECT count(*) FROM runs").fetchone()[0] == 8
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 4. report produce report.md con "Limitaciones" y una tabla por brazo.
# ---------------------------------------------------------------------------


def test_report_has_limitaciones_and_per_arm_table(tmp_path: Path) -> None:
    yaml_path = _write_yaml(tmp_path, _TWO_ARM_YAML)
    out = tmp_path / "out"
    run_experiment(yaml_path, out, workers=2)

    report_path = build_report(out)
    text = report_path.read_text(encoding="utf-8")
    assert "## Limitaciones" in text
    assert LIMITATIONS_SENTENCE in text
    assert "## Por brazo" in text
    assert "dependent" in text
    assert "independent" in text


def test_cli_experiment_commands_end_to_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    yaml_path = _write_yaml(tmp_path, _TWO_ARM_YAML)
    out = tmp_path / "out"

    r = runner.invoke(
        app, ["experiment", "run", str(yaml_path), "--out", str(out), "--workers", "2"]
    )
    assert r.exit_code == 0, r.output
    assert "fallidas=0" in r.output

    r = runner.invoke(app, ["experiment", "status", str(out)])
    assert r.exit_code == 0, r.output

    r = runner.invoke(app, ["experiment", "report", str(out)])
    assert r.exit_code == 0, r.output
    assert (out / "report.md").exists()


# ---------------------------------------------------------------------------
# 5. sweep 2x2 -> 4 brazos con nombres deterministas.
# ---------------------------------------------------------------------------


def test_sweep_2x2_yields_4_deterministic_arm_names(tmp_path: Path) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        name: sweep_dod
        description: prueba del DoD de sweep
        base: {months: 4}
        seeds: {start: 0, count: 1}
        arms:
          base: {}
        sweep:
          country.coefficients.c_f: [0.08, 0.12]
          country.default_policy.primary_spending: [23, 25]
        metrics: [outcome]
        """,
    )
    config = ExperimentConfig.load(yaml_path)
    arms = config.resolve_arms()
    names = [a.name for a in arms]
    assert len(names) == 4
    assert len(set(names)) == 4  # deterministas y unicos
    assert names == [
        "base__c_f=0.08__primary_spending=23",
        "base__c_f=0.08__primary_spending=25",
        "base__c_f=0.12__primary_spending=23",
        "base__c_f=0.12__primary_spending=25",
    ]
    # Resolverlo de nuevo produce EXACTAMENTE los mismos nombres (determinismo).
    assert [a.name for a in config.resolve_arms()] == names


# ---------------------------------------------------------------------------
# 6. Un override dot-path cambia el valor esperado y el config_hash del brazo.
# ---------------------------------------------------------------------------


def test_dot_path_override_changes_value_and_config_hash(tmp_path: Path) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        name: override_dod
        description: prueba del DoD de overrides
        base: {months: 4}
        seeds: {start: 0, count: 1}
        arms:
          base: {}
          bumped:
            country: {coefficients: {c_f: 0.5}}
        metrics: [outcome]
        """,
    )
    config = ExperimentConfig.load(yaml_path)
    arms = {a.name: a for a in config.resolve_arms()}

    base_country = load_country()
    assert arms["base"].country.coefficients.c_f == base_country.coefficients.c_f
    assert arms["bumped"].country.coefficients.c_f == 0.5
    assert arms["bumped"].country.coefficients.c_f != arms["base"].country.coefficients.c_f

    assert arms["base"].config_hash != arms["bumped"].config_hash


def test_governance_override_changes_governance_overrides_dict(tmp_path: Path) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        name: gov_override_dod
        description: prueba de override de gobernanza
        base: {months: 4}
        seeds: {start: 0, count: 1}
        arms:
          low: {governance: {central_bank: {autonomy: 1}}}
          high: {governance: {central_bank: {autonomy: 5}}}
        metrics: [outcome]
        """,
    )
    config = ExperimentConfig.load(yaml_path)
    arms = {a.name: a for a in config.resolve_arms()}
    assert arms["low"].governance_overrides == {"central_bank.autonomy": "1"}
    assert arms["high"].governance_overrides == {"central_bank.autonomy": "5"}
    assert arms["low"].config_hash != arms["high"].config_hash


# ---------------------------------------------------------------------------
# Extra: extractor de metricas sobre una corrida chica.
# ---------------------------------------------------------------------------


def test_extract_run_metrics_on_tiny_run(tmp_path: Path) -> None:
    from republica.engine.simulation import run as run_simulation

    history = run_simulation(seed=7, months=6, actors_enabled=True, cohorts_enabled=True)
    jsonl_path = tmp_path / "tiny.jsonl"
    jsonl_path.write_text(history.to_jsonl(), encoding="utf-8")

    metrics = extract_run_metrics(jsonl_path)
    assert metrics["outcome"] == history.outcome
    assert isinstance(metrics["inflation_annual_final"], float)
    assert isinstance(metrics["gdp_growth_mean"], float)
    assert metrics["unemployment_final"] == history.records[-1].state["unemployment"]
    assert metrics["approval_final"] == history.records[-1].state["government_approval"]
    assert metrics["stability_min"] == min(r.state["political_stability"] for r in history.records)
    assert metrics["reserves_min"] == min(r.state["reserves"] for r in history.records)
    assert metrics["authority_violations"] >= 0
    assert metrics["agreements_broken"] >= 0


# ---------------------------------------------------------------------------
# Extra: Cliff's delta sobre un ejemplo conocido.
# ---------------------------------------------------------------------------


def test_cliffs_delta_known_example() -> None:
    # b totalmente mayor que a -> delta = +1 (dominancia total).
    assert cliffs_delta([1, 2, 3], [4, 5, 6]) == 1.0
    # a totalmente mayor que b -> delta = -1.
    assert cliffs_delta([4, 5, 6], [1, 2, 3]) == -1.0
    # Mismos valores -> delta = 0 (sin dominancia estocastica).
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == 0.0
    # Ejemplo parcial (ver docstring de cliffs_delta): a=[1,2,3], b=[2,3,4] -> 5/9.
    assert cliffs_delta([1, 2, 3], [2, 3, 4]) == pytest.approx(5 / 9)


def test_failed_run_does_not_stop_the_batch(tmp_path: Path, monkeypatch) -> None:
    """Un brazo con un campo de gobernanza inexistente rompe recien al
    CORRER la simulacion (`load_governance` se llama dentro de
    `run_simulation`, ADR 007 secc. 6): produce una corrida fallida en
    `failed.jsonl`, sin frenar el resto del lote."""
    yaml_path = _write_yaml(
        tmp_path,
        """\
        name: failing_dod
        description: prueba de que un fallo no frena el lote
        base: {months: 4}
        seeds: {start: 0, count: 2}
        arms:
          ok: {}
          broken:
            governance: {central_bank: {campo_inexistente: 4}}
        metrics: [outcome]
        """,
    )
    out = tmp_path / "out"
    result = run_experiment(yaml_path, out, workers=1)
    assert result["n_ok"] == 2  # el brazo "ok" corre las 2 semillas
    assert result["n_failed"] == 2  # el brazo "broken" falla las 2 semillas
    failed_path = out / "failed.jsonl"
    assert failed_path.exists()
    lines = [json.loads(line) for line in failed_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 2
    assert all(line["arm"] == "broken" for line in lines)
    assert all("traceback" in line for line in lines)
