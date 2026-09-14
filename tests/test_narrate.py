"""Test de aceptacion 8 (secc. 11): `narrate` no lanza y produce frases de umbral."""

from __future__ import annotations

from rich.console import Console

from republica.engine import narrate
from republica.engine.simulation import run


def test_narrate_seed_7_runs_without_exception(tmp_path) -> None:
    history = run(seed=7, months=48)
    out_path = tmp_path / "run_7.jsonl"
    out_path.write_text(history.to_jsonl(), encoding="utf-8")

    loaded = narrate.load_jsonl(out_path)
    console = Console(record=True, width=120)
    narrate.render(loaded.records, loaded.summary, console)
    text = console.export_text()

    assert "Resumen final" in text
    assert loaded.summary["outcome"] in text


def test_narrate_produces_at_least_one_threshold_sentence() -> None:
    """Con `primary_spending` alto el pais entra en hiperinflacion, lo que
    dispara varias frases de umbral (inflacion, reservas, aprobacion, etc.)."""
    from republica.engine.policy import ConstantPolicy
    from republica.world.config import load_country

    country = load_country()
    big_spend = country.default_policy.model_copy(update={"primary_spending": 32.0})
    history = run(seed=11, months=24, policy_rule=ConstantPolicy(big_spend), shocks_enabled=False)

    sentences = [s for r in history.records for s in narrate.threshold_sentences(r.to_dict())]
    assert len(sentences) >= 1
