"""Tests de aceptacion de ADR 003 (secc. 9) mas la corrida sin actores
byte-identica y el rechazo de params desconocidos de `Action`."""

from __future__ import annotations

import time

import pydantic
import pytest

from republica.actors.rule_based import RuleBasedActor, load_weights, make_actor_rng
from republica.actors.sheet import ActorSheet, load_actors
from republica.engine.actions import Action, ActionType
from republica.engine.consequences import ConsequenceContext, apply_consequences
from republica.engine.perception import PolicyProposal, build_perception, build_provinces_table
from republica.engine.permissions import (
    AuthContext,
    authorize,
    authorize_all,
    load_governance,
    load_permissions,
)
from republica.engine.policy import TaylorPolicy
from republica.engine.scheduler import build_actor_engine, run_actor_turn
from republica.engine.simulation import advance_month, new_simulation, run
from republica.world.config import load_country
from republica.world.economy import Aux
from republica.world.events import ShockAggregate

COUNTRY = load_country()
ACTORS = load_actors()
_ZERO_AUX = Aux(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def _perception(actor_id: str, delta: dict[str, float], **kwargs) -> tuple:
    sheet = ACTORS[actor_id]
    agg = ShockAggregate()
    table = build_provinces_table(
        COUNTRY.initial_state, COUNTRY.default_policy, COUNTRY.provinces, agg
    )
    proposal = PolicyProposal(delta=delta, label="test")
    perception = build_perception(
        sheet,
        COUNTRY.initial_state,
        _ZERO_AUX,
        proposal,
        kwargs.get("active_shocks", []),
        kwargs.get("recent_events", []),
        kwargs.get("month", 3),
        kwargs.get("months_to_election", 30),
        table,
        COUNTRY.parties,
        policy=COUNTRY.default_policy,
    )
    return sheet, perception


# 1. Matriz de permisos -------------------------------------------------


def test_permission_matrix_has_an_allowed_and_a_denied_action_per_role() -> None:
    permissions = load_permissions()
    governance = load_governance()
    parties_by_id = {p.id: p for p in COUNTRY.parties}
    ctx = AuthContext(
        state=COUNTRY.initial_state,
        month=1,
        parties_by_id=parties_by_id,
        governance=governance,
        permissions=permissions,
    )
    all_types = set(ActionType)
    for role, allowed_types in permissions.items():
        actor = next(a for a in ACTORS.values() if a.role == role)
        assert allowed_types, f"rol {role} sin acciones permitidas"

        # `sorted(..., key=.value)` en vez de iterar el `set` tal cual: el
        # orden de un `set` de `StrEnum` depende del hash de `str`, que
        # Python aleatoriza por proceso (`PYTHONHASHSEED`); sin esto el test
        # podria elegir un tipo distinto (y ser flaky) en cada corrida.
        allowed_type = sorted(allowed_types, key=lambda t: t.value)[0]
        forbidden_candidates = all_types - allowed_types
        assert forbidden_candidates, f"rol {role} tiene permitidos todos los tipos"
        forbidden_type = sorted(forbidden_candidates, key=lambda t: t.value)[0]

        allowed_action = _fill_minimal_params(allowed_type, actor)
        result = authorize(actor, allowed_action, ctx)
        assert result.__class__.__name__ == "Allowed", (
            f"{role}/{allowed_type} deberia estar permitido"
        )

        forbidden_action = _fill_minimal_params(forbidden_type, actor)
        denied = authorize(actor, forbidden_action, ctx)
        assert denied.__class__.__name__ == "Denied"
        assert denied.reason


def _fill_minimal_params(action_type: ActionType, actor: ActorSheet) -> Action:
    params: dict = {}
    if action_type in (
        ActionType.SUPPORT_POLICY,
        ActionType.OPPOSE_POLICY,
        ActionType.CALL_PROTEST,
    ):
        params = {"intensity": 0.5}
    elif action_type is ActionType.PUBLIC_STATEMENT:
        params = {"stance": "support", "intensity": 0.5}
    elif action_type is ActionType.LOBBY_CONGRESS:
        params = {"direction": "for", "intensity": 0.5}
    elif action_type in (ActionType.FORM_ALLIANCE, ActionType.BREAK_ALLIANCE):
        params = {"with": "president"}
    elif action_type is ActionType.STRIKE:
        params = {"sector": "general", "days": 2}
    elif action_type is ActionType.REQUEST_FUNDS:
        params = {"amount_pct_gdp": 0.2}
    elif action_type in (ActionType.WITHHOLD_INVESTMENT, ActionType.INVEST):
        params = {"intensity": 0.5}
    elif action_type is ActionType.PUBLISH_STORY:
        params = {"frame": "neutral", "target_bloc": "all"}
    elif action_type in (ActionType.ENDORSE, ActionType.CRITICIZE):
        params = {"target": "president"}
    elif action_type in (ActionType.RECOMMEND_RATE, ActionType.SET_RATE):
        params = {"delta_pp": 1.0}
    elif action_type in (ActionType.PROPOSE_POLICY, ActionType.ENACT_POLICY):
        params = {"policy_delta": {"tax_rate": 1.0}}
    elif action_type is ActionType.GRANT_CONCESSION:
        params = {"to": "gov_norte", "concession": "restore_transfers"}
    elif action_type is ActionType.NEGOTIATE:
        params = {"requested_concession": "wage_bonus", "offer": "algo"}
    return Action(type=action_type, actor_id=actor.id, reason="test", params=params)


# 2. Interes vence ideologia ---------------------------------------------


def test_provincial_dependence_beats_shared_ideology() -> None:
    """REVIEW_001 hallazgo #6: con un recorte MODERADO de `provincial_transfers`
    (−1.0, no el −5.0 original: a −5.0 la ideologia ya opone por si sola, lo
    que hacia pasar el test por la razon contraria), `gov_norte` (federalism
    0.85, dependence 0.8) se opone porque el INTERES (`w_int·int`) domina el
    score, no la ideologia -- se asierta sobre el desglose. `gov_capital`
    (dependence 0.1) tiene el MISMO interes (`provincial_transfers`, agregado
    a su ficha por este mismo hallazgo) pero el impacto es 8x mas chico por
    su baja dependencia: ahi la ideologia (alineada con el ajuste fiscal)
    domina y no se opone."""
    delta = {"provincial_transfers": -1.0}
    sheet_norte, perc_norte = _perception("gov_norte", delta)
    sheet_capital, perc_capital = _perception("gov_capital", delta)

    ra_norte = RuleBasedActor(
        sheet_norte,
        COUNTRY.parties,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    ra_capital = RuleBasedActor(
        sheet_capital,
        COUNTRY.parties,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )

    norte_actions = ra_norte.decide(perc_norte, make_actor_rng(7, "gov_norte"))
    capital_actions = ra_capital.decide(perc_capital, make_actor_rng(7, "gov_capital"))

    assert any(a.type is ActionType.OPPOSE_POLICY for a in norte_actions)
    assert not any(a.type is ActionType.OPPOSE_POLICY for a in capital_actions)

    score_norte = ra_norte.last_score
    assert score_norte is not None
    w = load_weights()["default"]  # "governor" no tiene entrada propia, cae al default
    assert abs(w["w_int"] * score_norte.interest) > abs(w["w_ideo"] * score_norte.ideo), (
        "el interes deberia dominar la ideologia en el desglose del score, no al reves"
    )


# 3. Inmutabilidad ---------------------------------------------------------


def test_world_state_is_frozen() -> None:
    state = COUNTRY.initial_state
    with pytest.raises(pydantic.ValidationError):
        state.gdp = 999.0  # type: ignore[misc]


# 4. Determinismo por actor -------------------------------------------------


def test_adding_a_new_actor_does_not_change_existing_actors_first_month() -> None:
    base_actors = {k: v for k, v in ACTORS.items() if k in ("gov_norte", "union_cgt", "president")}
    extra_actor = ACTORS["gov_norte"].model_copy(
        update={"id": "gov_synthetic", "province": "litoral"}
    )
    extended_actors = {**base_actors, "gov_synthetic": extra_actor}

    engine_base = build_actor_engine(7, COUNTRY, base_actors)
    engine_extended = build_actor_engine(7, COUNTRY, extended_actors)

    proposal = PolicyProposal(delta={"tax_rate": -2.0}, label="baja de impuestos")
    agg = ShockAggregate()
    common_args = (
        COUNTRY,
        COUNTRY.initial_state,
        COUNTRY.default_policy,
        agg,
        [],
        [],
        1,
        40,
        proposal,
    )

    records_base, _ = run_actor_turn(engine_base, *common_args, [])
    records_extended, _ = run_actor_turn(engine_extended, *common_args, [])

    def _key(records):
        return sorted(
            (r.actor, r.type, tuple(sorted(r.params.items())), r.authorized)
            for r in records
            if r.actor != "gov_synthetic"
        )

    assert _key(records_base) == _key(records_extended)


# 5. Escalada: STRIKE sube protesta y baja PIB -----------------------------


def test_strike_escalation_raises_protest_and_lowers_gdp() -> None:
    sheet = ACTORS["union_cgt"].model_copy(
        update={
            "personality": ACTORS["union_cgt"].personality.model_copy(
                update={"risk_tolerance": 1.0, "pragmatism": 1.0}
            )
        }
    )
    ra = RuleBasedActor(
        sheet,
        COUNTRY.parties,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    _, perception = _perception("union_cgt", {"primary_spending": -30.0})
    perception = perception.model_copy(update={"relationships": sheet.relationships})

    import random

    strike_action = None
    for seed in range(30):
        actions = ra.decide(perception, random.Random(seed))
        strike_action = next((a for a in actions if a.type is ActionType.STRIKE), None)
        if strike_action is not None:
            break
    assert strike_action is not None, "STRIKE deberia disparar con risk_tolerance=1.0"

    ctx = ConsequenceContext(
        state=COUNTRY.initial_state, policy=COUNTRY.default_policy, parties_by_id={}
    )
    pending, _rel, _events = apply_consequences([strike_action], {sheet.id: sheet}, ctx)
    assert pending["shock_gdp"] < 0.0
    assert pending["shock_protest"] > 0.0

    # Efecto real: dos corridas identicas salvo que una arranca con estos
    # `pending_terms` ya cargados en el mes 1 (como si `union_cgt` hubiera
    # hecho STRIKE el mes anterior).
    sim_struck = new_simulation(7, None, None, COUNTRY, True, True)
    sim_struck.pending_terms.update(pending)
    sim_baseline = new_simulation(7, None, None, COUNTRY, True, True)

    rec_struck = advance_month(sim_struck)
    rec_baseline = advance_month(sim_baseline)

    assert rec_struck.state["protest_level"] > rec_baseline.state["protest_level"]
    assert rec_struck.state["gdp"] < rec_baseline.state["gdp"]


# 6. Cooldown de STRIKE -----------------------------------------------------


def test_strike_cooldown_blocks_two_consecutive_months() -> None:
    permissions = load_permissions()
    governance = load_governance()
    parties_by_id = {p.id: p for p in COUNTRY.parties}
    ctx = AuthContext(
        state=COUNTRY.initial_state,
        month=1,
        parties_by_id=parties_by_id,
        governance=governance,
        permissions=permissions,
    )
    actor = ACTORS["union_cgt"]
    strike = Action(
        type=ActionType.STRIKE,
        actor_id=actor.id,
        params={"sector": "general", "days": 2},
        reason="r",
    )

    allowed, denied = authorize_all([strike], ACTORS, ctx)
    assert len(allowed) == 1 and not denied

    ctx.month = 2
    strike2 = Action(
        type=ActionType.STRIKE,
        actor_id=actor.id,
        params={"sector": "general", "days": 2},
        reason="r",
    )
    allowed2, denied2 = authorize_all([strike2], ACTORS, ctx)
    assert not allowed2 and len(denied2) == 1
    assert "cooldown" in denied2[0].reason

    ctx.month = 4
    strike3 = Action(
        type=ActionType.STRIKE,
        actor_id=actor.id,
        params={"sector": "general", "days": 2},
        reason="r",
    )
    allowed3, denied3 = authorize_all([strike3], ACTORS, ctx)
    assert len(allowed3) == 1 and not denied3


# 7. Presupuesto de acciones por turno ---------------------------------------


def test_fourth_action_of_the_month_is_denied_by_budget() -> None:
    permissions = load_permissions()
    governance = load_governance()
    parties_by_id = {p.id: p for p in COUNTRY.parties}
    ctx = AuthContext(
        state=COUNTRY.initial_state,
        month=1,
        parties_by_id=parties_by_id,
        governance=governance,
        permissions=permissions,
    )
    actor = ACTORS["gov_norte"]
    actions = [
        Action(
            type=ActionType.PUBLIC_STATEMENT,
            actor_id=actor.id,
            params={"stance": "oppose", "intensity": 0.1},
            reason="r",
        )
        for _ in range(4)
    ]
    allowed, denied = authorize_all(actions, ACTORS, ctx)
    assert len(allowed) == 3
    assert len(denied) == 1
    assert "presupuesto" in denied[0].reason


# 8. 48 meses con 29 actores por reglas, < 5s --------------------------------


def test_48_months_29_actors_under_5_seconds() -> None:
    t0 = time.perf_counter()
    history = run(seed=7, months=48, actors_enabled=True)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"tardo {elapsed:.2f}s"
    assert len(history.records) == 48
    assert any(a.to_dict()["kind"] == "action" for a in history.action_records)
    assert len(history.action_records) > 0


# byte-identico sin actores ---------------------------------------------


def test_no_actors_run_is_identical_regardless_of_how_its_disabled() -> None:
    h_default = run(seed=7, months=6)
    h_explicit = run(seed=7, months=6, actors_enabled=False)
    assert h_default.to_jsonl() == h_explicit.to_jsonl()
    assert h_default.action_records == []


def test_no_actors_month_record_shape_is_unchanged() -> None:
    """Sin actores, cada linea del JSONL (salvo la de resumen) es un
    `MonthRecord` puro: mismas 11 claves de siempre, sin `"kind"`."""
    history = run(seed=7, months=5, actors_enabled=False)
    lines = history.to_jsonl().splitlines()
    assert len(lines) == 5 + 1
    import json

    expected_keys = {
        "month_index",
        "date",
        "state",
        "exo",
        "policy",
        "aux",
        "shocks_new",
        "shocks_active",
        "events",
        "provinces",
        "overflow",
    }
    for line in lines[:-1]:
        row = json.loads(line)
        assert set(row.keys()) == expected_keys
        assert "kind" not in row


# Action: rechaza params desconocidos ----------------------------------------


def test_action_rejects_unknown_params_for_a_typed_action() -> None:
    with pytest.raises(pydantic.ValidationError):
        Action(
            type=ActionType.PUBLIC_STATEMENT,
            actor_id="gov_norte",
            params={"stance": "oppose", "intensity": 0.5, "unexpected_field": 123},
            reason="r",
        )


def test_action_rejects_out_of_range_params() -> None:
    with pytest.raises(pydantic.ValidationError):
        Action(
            type=ActionType.STRIKE,
            actor_id="union_cgt",
            params={"sector": "general", "days": 99},
            reason="r",
        )


# REVIEW_001 hallazgo #1: relationships vivas, no la ficha -------------------


def test_relationships_change_between_months_after_a_strike() -> None:
    """`build_perception` debe leer `engine.relationships` (vivas: mutan con
    las consecuencias) y no solo sembrar desde la ficha estatica: el
    `score.rel` de `union_cgt` en el mes siguiente a un STRIKE (que le baja
    la relacion con `president`) tiene que ser distinto del mes 1."""
    actors = {k: v for k, v in ACTORS.items() if k in ("union_cgt", "president", "gov_norte")}
    engine = build_actor_engine(7, COUNTRY, actors)
    proposal = PolicyProposal(delta={}, label="sin cambios")
    agg = ShockAggregate()

    def _union_rel_score(month: int) -> float:
        records, _ = run_actor_turn(
            engine,
            COUNTRY,
            COUNTRY.initial_state,
            COUNTRY.default_policy,
            agg,
            [],
            [],
            month,
            40,
            proposal,
            [],
        )
        return next(r.score["rel"] for r in records if r.actor == "union_cgt" and r.score)

    rel_score_month1 = _union_rel_score(1)

    strike = Action(
        type=ActionType.STRIKE,
        actor_id="union_cgt",
        params={"sector": "general", "days": 3},
        reason="test",
    )
    ctx = ConsequenceContext(
        state=COUNTRY.initial_state, policy=COUNTRY.default_policy, parties_by_id={}
    )
    _, rel_deltas, _events = apply_consequences([strike], ACTORS, ctx)
    for a, b, delta in rel_deltas:
        engine.relationships.bump(a, b, delta)

    rel_score_month2 = _union_rel_score(2)

    assert rel_score_month1 != rel_score_month2


# REVIEW_001 hallazgos #3/#4: medios ven active_shocks y se diferencian -----


def test_media_outlets_diverge_in_frame_sequences_over_48_months() -> None:
    """Los 3 medios (economic +0.7/-0.6/+0.1) no deberian emitir la misma
    secuencia de frames en 48 meses: `_decide_media` ahora desplaza sus
    umbrales `crisis`/`recovery` segun la distancia ideologica al partido de
    gobierno (hallazgo #4) ademas de mirar `active_shocks` para `scandal`
    (hallazgo #3, antes solo miraba `recent_events`, que nunca trae ids de
    shocks)."""
    policy_rule = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    history = run(seed=7, months=48, policy_rule=policy_rule, actors_enabled=True)

    frames: dict[str, list[str]] = {"media_mercado": [], "media_popular": [], "media_nacional": []}
    for rec in history.action_records:
        if rec.actor in frames and rec.type == "PUBLISH_STORY":
            frames[rec.actor].append(rec.params["frame"])

    assert all(len(seq) == 48 for seq in frames.values())
    assert not (frames["media_mercado"] == frames["media_popular"] == frames["media_nacional"])


# REVIEW_001 hallazgo #5: concesion persistente, sin propuesta fantasma -----


def test_granted_concession_persists_and_does_not_trigger_phantom_renegotiation() -> None:
    """Una concesion `restore_transfers` otorgada el mes 1 debe quedar
    "pegada" a `provincial_transfers` (+0.5) en los meses 2 y 3 -- no
    revertirse el mes 2 y desaparecer el 3 (el bug original) -- y no debe
    generar un `NEGOTIATE` de `gov_norte` pidiendo la misma concesion en los
    meses siguientes (cooldown de `RuleBasedActor`, ver `rule_based.py::
    CONCESSION_COOLDOWN_MONTHS`)."""
    actors = {k: v for k, v in ACTORS.items() if k in ("gov_norte", "president")}
    sim = new_simulation(7, None, None, COUNTRY, True, True, actors_enabled=True, actors=actors)
    baseline_transfers = COUNTRY.default_policy.provincial_transfers

    grant = Action(
        type=ActionType.GRANT_CONCESSION,
        actor_id="president",
        target="gov_norte",
        params={"to": "gov_norte", "concession": "restore_transfers"},
        reason="test",
    )
    sim.pending_grant_override = [grant]
    advance_month(sim)  # mes 1: se otorga la concesion (efecto recien mes 2)
    rec2 = advance_month(sim)  # mes 2
    rec3 = advance_month(sim)  # mes 3

    assert rec2.policy["provincial_transfers"] == pytest.approx(baseline_transfers + 0.5)
    assert rec3.policy["provincial_transfers"] == pytest.approx(baseline_transfers + 0.5)

    negotiate_months = {
        r.month
        for r in sim.action_records
        if r.actor == "gov_norte"
        and r.type == "NEGOTIATE"
        and r.params.get("requested_concession") == "restore_transfers"
        and r.month in (2, 3)
    }
    assert not negotiate_months


# REVIEW_001 hallazgo #11: escalada de gobernadores respeta el presupuesto --


def test_governor_escalation_never_exceeds_the_action_budget() -> None:
    """OPPOSE_POLICY + escalada (LOBBY_CONGRESS + REQUEST_FUNDS) +
    PUBLIC_STATEMENT son 4 acciones: el actor debe elegir cuales de las 3
    del presupuesto por turno gasta (ADR 003 secc. 4/9), no dejar que
    `authorize()` descarte la ultima por puro orden de llegada."""
    sheet = ACTORS["gov_norte"].model_copy(
        update={
            "personality": ACTORS["gov_norte"].personality.model_copy(
                update={"risk_tolerance": 1.0, "ambition": 1.0, "pragmatism": 1.0}
            )
        }
    )
    ra = RuleBasedActor(
        sheet,
        COUNTRY.parties,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    _, perception = _perception("gov_norte", {"provincial_transfers": -5.0, "tax_rate": 3.0})

    import random

    escalated_at_least_once = False
    for seed in range(30):
        actions = ra.decide(perception, random.Random(seed))
        types = [a.type for a in actions]
        if ActionType.OPPOSE_POLICY in types and ActionType.LOBBY_CONGRESS in types:
            escalated_at_least_once = True
            assert len(actions) <= 3, f"seed {seed}: {len(actions)} acciones, {types}"
    msg = "el escenario deberia disparar OPPOSE + escalada al menos una vez"
    assert escalated_at_least_once, msg
