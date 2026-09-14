"""Tests de `engine/dilemmas.py` (SPEC_v0.2_play.md secc. 2, y secc. 5)."""

from __future__ import annotations

import math

import pytest

from republica.engine.dilemmas import (
    Dilemma,
    PendingEffect,
    _resolve_var,
    apply_option,
    compute_aux_vars,
    evaluate_triggers,
    load_dilemmas,
    render_text,
)
from republica.world.config import load_country

COUNTRY = load_country()
DILEMMAS = load_dilemmas()


def test_all_14_dilemmas_load_and_validate() -> None:
    assert len(DILEMMAS) == 14
    ids = [d.id for d in DILEMMAS]
    assert len(ids) == len(set(ids))
    for d in DILEMMAS:
        assert d.options, f"{d.id} no tiene opciones"
        assert d.trigger.all_ or d.trigger.any_, f"{d.id} no tiene condiciones"


def test_every_trigger_var_used_in_the_yaml_is_resolvable() -> None:
    state = COUNTRY.initial_state.model_copy()
    aux = compute_aux_vars(state, month=36, months_total=COUNTRY.months)
    active_ids = {
        "general_strike",
        "drought",
        "flood",
        "corruption_scandal",
        "protest_wave",
        "commodity_boom",
        "banking_crisis",
    }
    for d in DILEMMAS:
        for clause in (*d.trigger.all_, *d.trigger.any_):
            # No debe levantar KeyError.
            _resolve_var(clause.var, state, aux, 36, active_ids, [], {})


def test_render_text_interpolates_state_and_aux() -> None:
    d = next(d for d in DILEMMAS if d.id == "cb_recommends_hike")
    state = COUNTRY.initial_state.model_copy(update={"inflation": 3.0})
    aux = compute_aux_vars(state, month=5, months_total=COUNTRY.months)
    text = render_text(d, state, aux, 5)
    assert f"{aux.inflation_annual:.0f}" in text


def _synthetic_dilemma(
    id_: str, cooldown: int = 0, once: bool = False, priority: int = 0
) -> Dilemma:
    return Dilemma.model_validate(
        {
            "id": id_,
            "title": id_,
            "text": "texto",
            "trigger": {
                "all": [{"var": "month", "gte": 1}],
                "cooldown": cooldown,
                "once": once,
                "priority": priority,
            },
            "options": [{"key": "A", "label": "opcion A"}],
        }
    )


def _ctx(month: int):
    state = COUNTRY.initial_state.model_copy()
    aux = compute_aux_vars(state, month, COUNTRY.months)
    return state, aux


def test_cooldown_prevents_reappearance_before_n_months() -> None:
    d = _synthetic_dilemma("cooldown_test", cooldown=6)
    cooldowns: dict[str, float] = {}
    seen_months = []
    for month in range(1, 15):
        state, aux = _ctx(month)
        shown = evaluate_triggers(state, aux, month, {}, [], {}, cooldowns, catalog=[d])
        if shown:
            seen_months.append(month)
    assert seen_months[0] == 1
    assert seen_months[1] == 7  # 1 + cooldown(6)
    for a, b in zip(seen_months, seen_months[1:], strict=False):
        assert b - a >= 6


def test_once_dilemma_appears_only_once() -> None:
    d = _synthetic_dilemma("once_test", once=True)
    cooldowns: dict[str, float] = {}
    seen_months = []
    for month in range(1, 25):
        state, aux = _ctx(month)
        shown = evaluate_triggers(state, aux, month, {}, [], {}, cooldowns, catalog=[d])
        if shown:
            seen_months.append(month)
    assert seen_months == [1]
    assert cooldowns["once_test"] == math.inf


def test_at_most_two_dilemmas_shown_ordered_by_priority() -> None:
    catalog = [_synthetic_dilemma(f"d{i}", priority=i) for i in range(5)]
    state, aux = _ctx(1)
    shown = evaluate_triggers(state, aux, 1, {}, [], {}, {}, catalog=catalog)
    assert [d.id for d in shown] == ["d4", "d3"]


def test_dilemmas_not_shown_this_month_keep_their_cooldown_free() -> None:
    """Un dilema disparado pero que no entra en el tope de 2 no consume
    cooldown: sigue disponible (y puede competir por prioridad) el mes que
    viene."""
    high = [_synthetic_dilemma(f"high{i}", priority=10) for i in range(2)]
    low = _synthetic_dilemma("low", priority=1, cooldown=6)
    catalog = [*high, low]
    cooldowns: dict[str, float] = {}
    state, aux = _ctx(1)
    shown1 = evaluate_triggers(state, aux, 1, {}, [], {}, cooldowns, catalog=catalog)
    assert "low" not in [d.id for d in shown1]
    assert "low" not in cooldowns

    state, aux = _ctx(2)
    catalog2 = [low]  # los "high" ya no disparan este mes
    shown2 = evaluate_triggers(state, aux, 2, {}, [], {}, cooldowns, catalog=catalog2)
    assert [d.id for d in shown2] == ["low"]


def test_apply_option_policy_delta_is_additive() -> None:
    d = next(d for d in DILEMMAS if d.id == "public_wage_claim")
    option = next(o for o in d.options if o.key == "A")
    policy = COUNTRY.default_policy.model_copy()
    new_policy, pending, flags = apply_option(option, policy, [], {})
    assert new_policy.primary_spending == pytest.approx(policy.primary_spending + 0.8)
    assert flags == {}


def test_apply_option_policy_set_overrides() -> None:
    d = next(d for d in DILEMMAS if d.id == "devaluation_pressure")
    option = next(o for o in d.options if o.key == "B")
    policy = COUNTRY.default_policy.model_copy(update={"fx_intervention": 0.2})
    new_policy, _pending, _flags = apply_option(option, policy, [], {})
    assert new_policy.fx_intervention == 1.0


def test_apply_option_fiscal_effect_queues_n_months() -> None:
    d = next(d for d in DILEMMAS if d.id == "governors_request_funds")
    option = next(o for o in d.options if o.key == "A")  # fiscal -0.6 por 3 meses
    policy = COUNTRY.default_policy.model_copy()
    new_policy, pending, flags = apply_option(option, policy, [], {})
    fiscal_effects = [p for p in pending if p.term == "shock_fiscal"]
    assert fiscal_effects == [PendingEffect(term="shock_fiscal", value=-0.6, remaining=3)]
    approval_effects = [p for p in pending if p.term == "shock_approval"]
    assert approval_effects == [PendingEffect(term="shock_approval", value=1.0, remaining=1)]
    assert flags == {"helped_provinces": True}


def test_apply_option_flags_persist_and_are_overridable() -> None:
    d = next(d for d in DILEMMAS if d.id == "general_strike_response")
    option = next(o for o in d.options if o.key == "A")
    _policy, _pending, flags = apply_option(option, COUNTRY.default_policy, [], {"other": True})
    assert flags == {"other": True, "dialogue_table": True}
