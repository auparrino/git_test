"""Tests de `engine/game.py` (SPEC_v0.2_play.md secc. 4 y 5)."""

from __future__ import annotations

import pytest

from republica.engine.game import Game
from republica.world.config import load_country

COUNTRY = load_country()


def _auto_choices(game: Game) -> dict[str, str]:
    return {d.id: d.options[0].key for d in game.pending_dilemmas}


def test_full_game_completes_48_months_auto() -> None:
    game = Game.new(seed=7, months=48)
    for _ in range(48):
        if game.sim.outcome is not None:
            break
        game.step(_auto_choices(game), {})
    assert len(game.sim.records) <= 48
    assert game.sim.outcome is not None


def test_once_and_cooldown_dilemmas_fire_as_expected_over_a_full_game() -> None:
    """Con la semilla 7 y --auto (primera opcion siempre), `tax_reform` y
    `preelectoral_year` (once=true) aparecen exactamente una vez, y
    `annual_budget` (meses 10/22/34, cooldown 11) las tres veces."""
    game = Game.new(seed=7, months=48)
    for _ in range(48):
        game.step(_auto_choices(game), {})

    by_id: dict[str, list[int]] = {}
    for dec in game.decisions:
        by_id.setdefault(dec["dilemma_id"], []).append(dec["month"])

    assert len(by_id.get("tax_reform", [])) == 1
    assert len(by_id.get("preelectoral_year", [])) == 1
    assert by_id["preelectoral_year"] == [36]
    assert by_id.get("annual_budget", []) == [10, 22, 34]


def test_policy_delta_respects_the_monthly_cap() -> None:
    game = Game.new(seed=1, months=1, shocks_enabled=False)
    baseline_rate = game.policy.interest_rate_target
    # cb_recommends_hike sube 5pp (dentro del tope); forzamos ademas una
    # edicion manual grande que si debe recortarse.
    game.step({}, {"interest_rate_target": baseline_rate + 100.0})
    assert game.clip_report["interest_rate_target"] == pytest.approx((100.0, 15.0))
    assert game.policy.interest_rate_target == pytest.approx(baseline_rate + 15.0)


def test_policy_delta_from_dilemma_is_also_capped() -> None:
    """Un `policy_delta` de un dilema que por si solo respeta el tope, sumado
    a una edicion manual del mismo instrumento el mismo mes, se recorta en
    conjunto (seccion 1, paso 3: el tope es por instrumento y por mes, sin
    importar la fuente)."""
    game = Game.new(seed=1, months=1, shocks_enabled=False)
    baseline_spending = game.policy.primary_spending
    from republica.engine.dilemmas import Dilemma

    synthetic = Dilemma.model_validate(
        {
            "id": "synthetic_spend",
            "title": "t",
            "text": "t",
            "trigger": {"all": [{"var": "month", "gte": 1}]},
            "options": [
                {"key": "A", "label": "a", "policy_delta": {"primary_spending": 1.5}},
            ],
        }
    )
    game.pending_dilemmas = [synthetic]
    # El jugador pide, ademas del +1.5 del dilema, otro +1.5 manual: el valor
    # absoluto final pedido es base+3.0, un delta total de +3.0 sobre el
    # valor de arranque del mes, que se recorta al tope de +2.0.
    game.step({"synthetic_spend": "A"}, {"primary_spending": baseline_spending + 3.0})
    assert game.clip_report["primary_spending"][1] == pytest.approx(2.0)
    assert game.policy.primary_spending == pytest.approx(baseline_spending + 2.0)


def test_save_and_load_reproduce_the_same_state(tmp_path) -> None:
    game = Game.new(seed=7, months=15)
    for _ in range(15):
        game.step(_auto_choices(game), {})
    save_path = tmp_path / "game_7.json"
    game.save(save_path)

    loaded = Game.load(save_path)
    assert loaded.sim.state.model_dump() == game.sim.state.model_dump()
    assert loaded.policy.model_dump() == game.policy.model_dump()
    assert loaded.decisions == game.decisions
    assert loaded.cooldowns == game.cooldowns
    assert loaded.flags == game.flags
    assert loaded.sim.month == game.sim.month


def test_save_and_load_reproduce_manual_instrument_edits(tmp_path) -> None:
    game = Game.new(seed=3, months=6, shocks_enabled=False)
    for m in range(6):
        edits = {"interest_rate_target": game.policy.interest_rate_target + 4.0} if m == 2 else {}
        game.step(_auto_choices(game), edits)
    save_path = tmp_path / "game_3.json"
    game.save(save_path)

    loaded = Game.load(save_path)
    assert loaded.sim.state.model_dump() == game.sim.state.model_dump()
    assert loaded.policy.model_dump() == game.policy.model_dump()


def test_rate_hike_at_month_one_lowers_inflation_by_month_twelve() -> None:
    """Analogo interactivo del test de aceptacion 5 (SPEC_v0.1 secc. 11):
    +15pp de tasa en el mes 1 via `instrument_edits`, sin dilemas ni shocks,
    baja la inflacion al mes 12 contra no tocar nada."""

    def _play(hike: bool) -> Game:
        game = Game.new(seed=42, months=12, shocks_enabled=False)
        for m in range(12):
            edits = {}
            if hike and m == 0:
                edits = {"interest_rate_target": game.policy.interest_rate_target + 15.0}
            game.step({}, edits)
        return game

    base = _play(hike=False)
    hiked = _play(hike=True)

    assert hiked.sim.records[11].state["inflation"] < base.sim.records[11].state["inflation"]


def test_scandal_response_dilemma_appears_after_forced_corruption_scandal() -> None:
    """REVIEW_001 hallazgo #2: `corruption_scandal` dura 1 mes y se borra de
    `sim.active_shocks` en el mismo mes en que se sortea (`ShockCatalog.
    apply_month`); los triggers `shock_active:` de los dilemas se evaluaban
    DESPUES de `advance_month`, sobre ese `active_shocks` ya vacio de shocks
    de 1 mes, asi que `scandal_response` (y `general_strike_response`/
    `protest_wave_response`, los otros dos disparados por un shock de 1 mes)
    nunca aparecian. `Game._refresh_pending_dilemmas` ahora mira tambien
    `records[-1].shocks_new`. Se fuerza `corruption_scandal` en el mes 5
    (`sim.forced_shocks`, sin pasar por la CLI) y se juega con --auto
    (primera opcion de cada dilema, via `_auto_choices`, usando la API de
    `Game` directamente)."""
    game = Game.new(seed=7, months=8, actors_enabled=False)
    game.sim.forced_shocks[5] = ["corruption_scandal"]

    months_offered: list[int] = []
    for _ in range(8):
        if any(d.id == "scandal_response" for d in game.pending_dilemmas):
            months_offered.append(game.sim.month + 1)
        game.step(_auto_choices(game), {})

    assert months_offered, "scandal_response nunca se ofrecio"
    assert all(m in (5, 6) for m in months_offered)


def test_counterfactual_impact_reports_final_diff_and_top_decisions() -> None:
    game = Game.new(seed=7, months=12)
    for _ in range(12):
        game.step(_auto_choices(game), {})
    impact = game.counterfactual_impact()
    assert "approval_diff_final" in impact
    assert isinstance(impact["approval_diff_final"], float)
    assert len(impact["top_decisions"]) <= 5
    for dec in impact["top_decisions"]:
        assert "approval_delta_3m" in dec
