"""Tests de CLI de ADR 003 (deliverables 8 y 9): `actors list`, `run
--no-actors`, `narrate` con acciones, y `play --actors`."""

from __future__ import annotations

import json

from rich.console import Console
from typer.testing import CliRunner

from republica.cli import app
from republica.engine import narrate as narrate_mod
from republica.engine.simulation import run

runner = CliRunner()


def test_actors_list_shows_the_29_actors() -> None:
    result = runner.invoke(app, ["actors", "list"])
    assert result.exit_code == 0, result.output
    for actor_id in ("president", "gov_norte", "union_cgt", "media_mercado", "central_bank"):
        assert actor_id in result.output


def test_run_cli_no_actors_flag_has_no_action_lines(tmp_path) -> None:
    out = tmp_path / "run_7.jsonl"
    result = runner.invoke(
        app, ["run", "--seed", "7", "--months", "6", "--no-actors", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 7  # 6 meses + resumen
    for line in lines[:-1]:
        assert json.loads(line).get("kind") is None


def test_run_cli_actors_flag_produces_action_lines(tmp_path) -> None:
    out = tmp_path / "run_7.jsonl"
    result = runner.invoke(
        app, ["run", "--seed", "7", "--months", "6", "--actors", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    lines = out.read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line).get("kind") for line in lines[:-1]]
    assert "action" in kinds


def test_narrate_shows_actor_reactions_when_present() -> None:
    history = run(seed=7, months=3, actors_enabled=True)
    console = Console(record=True, width=140)
    loaded_records = [r.to_dict() for r in history.records]
    actions_by_month: dict[int, list] = {}
    for a in history.action_records:
        actions_by_month.setdefault(a.month, []).append(a.to_dict())
    summary = {"outcome": history.outcome, "seed": history.seed, "config_hash": history.config_hash}
    narrate_mod.render(loaded_records, summary, console, actions_by_month)
    text = console.export_text()
    assert "Actores (3 mas intensos)" in text


def test_top_actions_prefers_authorized_and_more_intense() -> None:
    rows = [
        {"authorized": True, "params": {"intensity": 0.2}, "score": None},
        {"authorized": True, "params": {"intensity": 0.9}, "score": None},
        {"authorized": False, "params": {"intensity": 1.0}, "score": None},
    ]
    top = narrate_mod.top_actions(rows, n=2)
    assert top[0]["params"]["intensity"] == 0.9
    assert all(r["authorized"] for r in top)


def test_play_with_actors_shows_reactions_and_completes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["play", "--seed", "7", "--months", "6", "--auto", "--actors"])
    assert result.exit_code == 0, result.output
    assert "Fin de la partida" in result.output
    assert (
        "Reacciones de los actores" in result.output or "Sin reacciones destacadas" in result.output
    )
