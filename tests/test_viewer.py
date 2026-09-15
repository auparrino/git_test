"""Visor HTML autocontenido (src/republica/ui/viewer.py)."""

from __future__ import annotations

import json
from pathlib import Path

from republica.engine.simulation import run
from republica.ui.viewer import build_html, export, load_run


def _write_run(tmp_path: Path) -> Path:
    history = run(seed=3, months=12, actors_enabled=True)
    path = tmp_path / "run.jsonl"
    path.write_text(history.to_jsonl(), encoding="utf-8")
    return path


def test_load_run_groups_months_and_actions(tmp_path: Path) -> None:
    data = load_run(_write_run(tmp_path))
    assert len(data["months"]) == 12
    assert data["outcome"] in {"survived", "collapse", "hyperinflation"}
    first = data["months"][0]
    assert "inflation_annual" in first["state"]
    assert all(a["type"] != "NO_ACTION" for m in data["months"] for a in m["actions"])


def test_export_is_self_contained_html(tmp_path: Path) -> None:
    src = _write_run(tmp_path)
    out = export(src, tmp_path / "viewer.html")
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<title>")
    assert "__RUN_JSON__" not in html
    assert '"months"' in html
    # el JSON embebido no puede cerrar el script por accidente
    payload = json.dumps(load_run(src), ensure_ascii=False)
    assert "</script>" not in payload or "<\\/script>" in html


def test_build_html_escapes_script_close() -> None:
    run_data = {
        "seed": 1,
        "outcome": "survived",
        "months": [],
        "indicators": [],
        "config_hash": "</script><b>",
    }
    html = build_html(run_data)
    assert "</script><b>" not in html.split("__")[0]
    assert "<\\/script><b>" in html


def test_cli_viewer_writes_html(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from republica.cli import app

    src = _write_run(tmp_path)
    result = CliRunner().invoke(app, ["viewer", str(src), "--out", str(tmp_path / "v.html")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "v.html").read_text(encoding="utf-8").startswith("<title>")


def test_side_records_align_with_month_regardless_of_index_base(tmp_path: Path) -> None:
    history = run(seed=5, months=6, actors_enabled=True)
    path = tmp_path / "r.jsonl"
    path.write_text(history.to_jsonl(), encoding="utf-8")
    data = load_run(path)
    raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    first_action_month = min(int(r["month"]) for r in raw if r.get("kind") == "action")
    first_with_actions = next(m for m in data["months"] if m["actions"] or m["denied"])
    assert data["months"].index(first_with_actions) == first_action_month - 1
