"""Tests de `republica play` (SPEC_v0.2_play.md secc. 5)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from republica.cli import app

runner = CliRunner()


def test_play_interactive_completes_48_months(tmp_path, monkeypatch) -> None:
    """`play` con entrada simulada (A + Enter repetido) completa 48 meses sin
    excepcion. Hasta 2 dilemas por mes + el menu: sobra con 300 lineas."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["play", "--seed", "7", "--months", "48"], input="A\n" * 300)
    assert result.exit_code == 0, result.output
    assert "Fin de la partida" in result.output


def test_play_auto_finishes_and_saves_decisions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["play", "--seed", "7", "--months", "48", "--auto"])
    assert result.exit_code == 0, result.output
    assert "Fin de la partida" in result.output

    save_path = tmp_path / "simulations" / "game_7.json"
    assert save_path.exists()
    data = json.loads(save_path.read_text(encoding="utf-8"))
    assert data["seed"] == 7
    assert data["month"] == 48
    assert len(data["decisions"]) > 0

    history_path = tmp_path / "simulations" / "game_7.jsonl"
    assert history_path.exists()
    lines = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
    months = [r for r in lines if r.get("kind", "month") == "month" and "month_index" in r]
    assert len(months) == 48
    assert any(r.get("kind") == "action" for r in lines)  # actores activos por default en play


def test_play_load_resumes_a_saved_game(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    first = runner.invoke(app, ["play", "--seed", "7", "--months", "10", "--auto"])
    assert first.exit_code == 0, first.output

    save_path = tmp_path / "simulations" / "game_7.json"
    second = runner.invoke(app, ["play", "--load", str(save_path), "--auto"])
    assert second.exit_code == 0, second.output
    assert "Fin de la partida" in second.output
