"""Tests de ADR 005 secc. 1/2 (Congreso, negociacion) -- primera mitad de
Fase 5 (deliverable 8 del encargo, DoD parcial de ADR 005 secc. 7: items 1,
2, 5 sin `perception`)."""

from __future__ import annotations

import hashlib
import json
import random
import time

import pytest

from republica.actors.sheet import load_actors
from republica.engine.actions import Action, ActionType
from republica.engine.congress import CONCESSION_BONUS, Bill, requires_law, vote
from republica.engine.consequences import Relationships
from republica.engine.negotiation import (
    Agreement,
    apply_execution_results,
    check_actor_compliance,
    run_month_negotiations,
)
from republica.engine.policy import ConstantPolicy, TaylorPolicy
from republica.engine.scheduler import ActionRecord, build_actor_engine
from republica.engine.simulation import History, VoteRecord, advance_month, new_simulation, run
from republica.world.config import load_country

COUNTRY = load_country()
ACTORS = load_actors()

# ---------------------------------------------------------------------------
# 1. `requires_law` (ADR 005 secc. 1.1)
# ---------------------------------------------------------------------------


def test_requires_law_table() -> None:
    assert requires_law({"interest_rate_target": 5.0}) == {}
    assert requires_law({"fx_intervention": 0.3}) == {}
    assert requires_law({"primary_spending": 0.5}) == {}  # borde: |delta| > 0.5, no >=
    assert requires_law({"primary_spending": 0.51}) == {"primary_spending": 0.51}
    assert requires_law({"primary_spending": -0.6}) == {"primary_spending": -0.6}
    assert requires_law({"tax_rate": 0.01}) == {"tax_rate": 0.01}
    assert requires_law({"provincial_transfers": 0.01}) == {"provincial_transfers": 0.01}
    assert requires_law({}) == {}
    # combinado: solo la parte que requiere ley
    mixed = requires_law({"interest_rate_target": 5.0, "tax_rate": 1.0, "primary_spending": 0.1})
    assert mixed == {"tax_rate": 1.0}


# ---------------------------------------------------------------------------
# 2. Voto: disciplina, ley que falla y despues pasa (ADR 005 secc. 7 item 1)
# ---------------------------------------------------------------------------


def test_discipline_one_votes_as_a_bloc() -> None:
    """Con `discipline = 1.0`, un partido vota todas sus bancas de un lado
    (`yes_prob >= 0.5` -> todas si; si no, ninguna) -- nunca una cantidad
    fraccionaria intermedia (ADR 005 secc. 1.2: `discipline * [yes_prob >=
    0.5] + (1 - discipline) * yes_prob`, que con `discipline = 1` colapsa al
    primer termino).

    Hallazgo #8 de REVIEW_002: la version original solo asertaba `yes_seats
    in (0, seats)`, invariante que la aritmetica de la formula garantiza
    SIEMPRE para `discipline = 1.0` (`seats * bloc` con `bloc` binario) sin
    importar si el resto esta bien implementado -- el test no podia fallar.
    Se compara contra `discipline = 0.0` (voto proporcional) con el MISMO
    `rng`: `score`/`pressure`/`yes_prob` no dependen de `discipline`, asi que
    ambas corridas ven el mismo `yes_prob` -- si la formula ignorara
    `discipline` por completo, ambas darian el mismo `yes_seats` entero; con
    el fix, difieren (38 vs 23 bancas para este partido/bill/seed)."""
    party_bloc = next(p for p in COUNTRY.parties if p.id == "frente_federal").model_copy(
        update={"discipline": 1.0}
    )
    party_proportional = party_bloc.model_copy(update={"discipline": 0.0})
    relationships = Relationships.from_actors(ACTORS)
    bill = Bill(id="b_bloc", month=1, policy_delta={"tax_rate": 1.0})

    rec_bloc = vote(
        bill,
        [party_bloc],
        ACTORS,
        [],
        COUNTRY.initial_state,
        relationships,
        [],
        24,
        random.Random(3),
    )
    rec_proportional = vote(
        bill,
        [party_proportional],
        ACTORS,
        [],
        COUNTRY.initial_state,
        relationships,
        [],
        24,
        random.Random(3),
    )
    pv_bloc = rec_bloc.parties[0]
    pv_proportional = rec_proportional.parties[0]

    assert pv_bloc.yes_prob == pytest.approx(pv_proportional.yes_prob)
    # Caso borde del fixture, no de la formula: si `yes_prob` cayera
    # exactamente en {0, 1} el test de abajo seria trivial (bloc y
    # proporcional darian el mismo entero de casualidad).
    assert 0.0 < pv_bloc.yes_prob < 1.0

    expected_bloc_seats = party_bloc.seats if pv_bloc.yes_prob >= 0.5 else 0
    assert pv_bloc.yes_seats == expected_bloc_seats
    assert pv_proportional.yes_seats == round(party_proportional.seats * pv_proportional.yes_prob)
    # El punto del hallazgo: para el MISMO `yes_prob`, bloc y proporcional
    # dan resultados distintos -- si `discipline` se ignorara, coincidirian.
    assert pv_bloc.yes_seats != pv_proportional.yes_seats


def test_bill_fails_then_passes_with_agreement_and_lobby() -> None:
    """ADR 005 secc. 7 item 1 (adaptado: el bill de referencia del ADR es
    "ley de impuestos", aca un recorte de `provincial_transfers` -- el
    mecanismo que se prueba es el mismo: falla sola, pasa con
    `concession_bonus` + `LOBBY_CONGRESS` a favor). Un recorte de
    transferencias (`-2.0`, requiere ley siempre: tabla secc. 1.1) falla
    solo (oposicion alineada, `gobernadores`/partidos federalistas en
    contra); con un acuerdo vigente (`concession_bonus_p = +25`) y dos
    `LOBBY_CONGRESS(direction=for)` de gobernadores/partidos, pasa."""
    relationships = Relationships.from_actors(ACTORS)
    bill = Bill(id="b_transfers", month=5, policy_delta={"provincial_transfers": -2.0})

    rec_alone = vote(
        bill,
        COUNTRY.parties,
        ACTORS,
        [],
        COUNTRY.initial_state,
        relationships,
        [],
        30,
        random.Random(1),
    )
    assert not rec_alone.passed
    assert rec_alone.yes_total < rec_alone.threshold

    agreements = [
        Agreement(
            actor_id="gov_norte",
            concession="restore_transfers",
            in_exchange="vote_yes",
            scale=1.0,
            granted_month=4,
            law_required=True,
        ),
        Agreement(
            actor_id="party_alianza_provincial",
            concession="cabinet_seat",
            in_exchange="vote_yes",
            scale=1.0,
            granted_month=4,
            law_required=False,
        ),
    ]
    lobby = [
        ActionRecord(
            month=5,
            actor=actor_id,
            type="LOBBY_CONGRESS",
            params={"direction": "for", "intensity": 1.0},
            target=None,
            reason="test",
            authorized=True,
            denied_reason=None,
            score=None,
            consequences={},
        )
        for actor_id in (
            "gov_norte",
            "gov_costa",
            "party_frente_federal",
            "party_union_republicana",
        )
    ]
    rec_supported = vote(
        bill,
        COUNTRY.parties,
        ACTORS,
        lobby,
        COUNTRY.initial_state,
        relationships,
        agreements,
        30,
        random.Random(1),
    )
    assert rec_supported.passed
    assert rec_supported.yes_total >= rec_supported.threshold
    assert rec_supported.yes_total > rec_alone.yes_total


def test_failed_bill_leaves_policy_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el Congreso rechaza el `Bill`: la parte legislativa del delta NO
    se aplica (`policy` queda en el valor efectivo del mes pasado), aunque
    la `PolicyRule` haya propuesto el cambio (ADR 005 secc. 1.3)."""
    import republica.engine.simulation as sim_mod

    def _always_fails(bill, *args, **kwargs):  # noqa: ANN001, ARG001
        return VoteRecord(
            month=bill.month,
            bill_id=bill.id,
            policy_delta=bill.policy_delta,
            threshold=bill.threshold,
            parties=[],
            yes_total=0,
            passed=False,
        )

    monkeypatch.setattr(sim_mod, "congress_vote", _always_fails)

    class JumpPolicy:
        def __init__(self, default):
            self.default = default

        def decide(self, state, month):  # noqa: ARG002
            return self.default.model_copy(update={"tax_rate": self.default.tax_rate + 3.0})

    baseline_tax = COUNTRY.default_policy.tax_rate
    sim = new_simulation(
        7,
        JumpPolicy(COUNTRY.default_policy),
        None,
        COUNTRY,
        True,
        True,
        actors_enabled=True,
        actors={},
        congress_enabled=True,
        negotiation_enabled=True,
    )
    record = advance_month(sim)
    assert record.policy["tax_rate"] == pytest.approx(baseline_tax)
    assert len(sim.vote_records) == 1
    assert not sim.vote_records[0].passed
    # penalidad diferida (secc. 1.3): approval -1 / institutional_confidence
    # +0.5, sumada a `pending_terms` para el mes que viene.
    assert sim.pending_terms.get("shock_approval") == pytest.approx(-1.0)
    assert sim.pending_terms.get("shock_conf") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 3. Negociacion: acuerdo honrado vs. roto (ADR 005 secc. 7 item 2)
# ---------------------------------------------------------------------------


def test_non_law_agreement_executes_immediately_and_is_honored() -> None:
    """Una concesion que no requiere ley (`cabinet_seat`, sin `policy_field`)
    se ejecuta en el acto: `Agreement.executed = True`, `status =
    "honored"` ya en el mes de la negociacion (ADR 005 secc. 2)."""
    engine = build_actor_engine(7, COUNTRY, ACTORS)
    actor = ACTORS["party_frente_federal"]  # 38 bancas: leverage >> 0.3, GRANT directo
    rel_before = engine.relationships.get(actor.id, "president")
    action = Action(
        type=ActionType.NEGOTIATE,
        actor_id=actor.id,
        target="president",
        params={"requested_concession": "cabinet_seat", "offer": "banca en el gabinete"},
        reason="test",
    )
    records, pending = run_month_negotiations(
        engine, [action], COUNTRY, month=1, congress_enabled=True
    )
    assert len(records) == 1
    assert records[0].outcome == "agreement"
    assert len(engine.agreements) == 1
    agreement = engine.agreements[0]
    assert agreement.law_required is False
    assert agreement.executed is True
    assert agreement.status == "honored"
    # +8 de relacion "mientras este vigente" (ADR 005 secc. 2), acotado a 100.
    assert engine.relationships.get(actor.id, "president") == pytest.approx(
        min(100.0, rel_before + 8.0)
    )


def test_honored_agreement_this_month_still_earns_concession_bonus() -> None:
    """Hallazgo #5 de REVIEW_002: una concesion sin ley (como `cabinet_seat`,
    ver el test anterior) se ejecuta de inmediato y pasa a `honored` en el
    MISMO mes en que se otorga -- antes, `_concession_bonus_for_party`
    (`engine/congress.py`) solo miraba `status == "vigente"`, asi que esa
    concesion nunca llegaba a comprar el voto por el que se negocio (22 de
    56 acuerdos en una corrida de 96 meses, ver docs/REVIEW_002_fases_4-7.md
    hallazgo #5). Un `honored` otorgado ESTE mes suma el mismo
    `concession_bonus_p = +25` que un `vigente`; uno de un mes anterior ya
    "cobro" su voto (o nunca lo iba a cobrar) y no debe seguir sumando."""
    relationships = Relationships.from_actors(ACTORS)
    bill = Bill(id="b_seat", month=5, policy_delta={"provincial_transfers": -2.0})
    party = next(p for p in COUNTRY.parties if p.id == "alianza_provincial")

    def pressure_for(agreements: list[Agreement]) -> float:
        rec = vote(
            bill,
            [party],
            ACTORS,
            [],
            COUNTRY.initial_state,
            relationships,
            agreements,
            30,
            random.Random(1),
        )
        return rec.parties[0].pressure

    no_agreement = pressure_for([])
    vigente = pressure_for(
        [
            Agreement(
                actor_id="party_alianza_provincial",
                concession="cabinet_seat",
                in_exchange="vote_yes",
                scale=1.0,
                granted_month=4,
                law_required=True,
                status="vigente",
            )
        ]
    )
    honored_this_month = pressure_for(
        [
            Agreement(
                actor_id="party_alianza_provincial",
                concession="cabinet_seat",
                in_exchange="vote_yes",
                scale=1.0,
                granted_month=bill.month,
                law_required=False,
                status="honored",
                executed=True,
            )
        ]
    )
    honored_last_month = pressure_for(
        [
            Agreement(
                actor_id="party_alianza_provincial",
                concession="cabinet_seat",
                in_exchange="vote_yes",
                scale=1.0,
                granted_month=bill.month - 1,
                law_required=False,
                status="honored",
                executed=True,
            )
        ]
    )

    assert vigente == pytest.approx(no_agreement + CONCESSION_BONUS)
    assert honored_this_month == pytest.approx(no_agreement + CONCESSION_BONUS)
    assert honored_last_month == pytest.approx(no_agreement)


def test_law_required_agreement_breaks_by_government_after_grace_period() -> None:
    """Una concesion que si requiere ley (`restore_transfers`) queda
    `vigente` sin ejecutar hasta que el Congreso la vote; si pasan 2 meses
    sin que el `Bill` correspondiente pase, `broken_by_government`,
    relacion -15, evento `agreement_broken` (ADR 005 secc. 2)."""
    engine = build_actor_engine(7, COUNTRY, ACTORS)
    actor = ACTORS["party_frente_federal"]
    action = Action(
        type=ActionType.NEGOTIATE,
        actor_id=actor.id,
        target="president",
        params={"requested_concession": "restore_transfers", "offer": "mas transferencias"},
        reason="test",
    )
    run_month_negotiations(engine, [action], COUNTRY, month=1, congress_enabled=True)
    agreement = engine.agreements[0]
    assert agreement.law_required is True
    assert agreement.status == "vigente"
    assert agreement.executed is False

    rel_before = engine.relationships.get(actor.id, "president")
    pending1, events1 = apply_execution_results(engine, False, [agreement], engine.concessions, 2)
    assert pending1 == {}
    assert events1 == []
    assert agreement.status == "vigente"
    assert agreement.months_pending == 1

    pending2, events2 = apply_execution_results(engine, False, [agreement], engine.concessions, 3)
    assert agreement.status == "broken_by_government"
    assert any(e.startswith("agreement_broken:") and e.endswith(":government") for e in events2)
    assert engine.relationships.get(actor.id, "president") == pytest.approx(rel_before - 15.0)


def test_law_required_agreement_honored_when_bill_passes() -> None:
    """Si el `Bill` pasa antes de agotar los 2 meses de gracia, la concesion
    se ejecuta (`policy_*`/`shock_fiscal` para el mes siguiente) y el
    acuerdo queda `honored`."""
    engine = build_actor_engine(7, COUNTRY, ACTORS)
    actor = ACTORS["party_frente_federal"]
    action = Action(
        type=ActionType.NEGOTIATE,
        actor_id=actor.id,
        target="president",
        params={"requested_concession": "restore_transfers", "offer": "mas transferencias"},
        reason="test",
    )
    run_month_negotiations(engine, [action], COUNTRY, month=1, congress_enabled=True)
    agreement = engine.agreements[0]

    pending, events = apply_execution_results(engine, True, [agreement], engine.concessions, 2)
    assert agreement.status == "honored"
    assert agreement.executed is True
    assert pending["policy_provincial_transfers"] == pytest.approx(0.5)
    assert pending["shock_fiscal"] == pytest.approx(-0.5)
    assert any(e.startswith("agreement_honored:") for e in events)


def test_agreement_broken_by_actor_when_it_opposes_anyway() -> None:
    """Si el actor tiene un acuerdo `vigente` a cambio de `vote_yes` pero
    igual emite `OPPOSE_POLICY` este mes: `broken_by_actor`, relacion -10, y
    6 meses sin renegociar (ADR 005 secc. 2)."""
    engine = build_actor_engine(7, COUNTRY, ACTORS)
    engine.agreements.append(
        Agreement(
            actor_id="gov_norte",
            concession="restore_transfers",
            in_exchange="vote_yes",
            scale=1.0,
            granted_month=1,
            law_required=True,
        )
    )
    rel_before = engine.relationships.get("gov_norte", "president")
    opposing = ActionRecord(
        month=3,
        actor="gov_norte",
        type="OPPOSE_POLICY",
        params={"intensity": 0.6},
        target=None,
        reason="test",
        authorized=True,
        denied_reason=None,
        score=None,
        consequences={},
    )
    events = check_actor_compliance(engine, [opposing], month=3)
    assert engine.agreements[0].status == "broken_by_actor"
    assert any(e.endswith(":actor") for e in events)
    assert engine.relationships.get("gov_norte", "president") == pytest.approx(rel_before - 10.0)
    assert engine.no_renegotiate_until["gov_norte"] == 9  # 3 + 6


# ---------------------------------------------------------------------------
# 4. `fake:rules` reproduce `rules` con Congreso/negociacion activos
# ---------------------------------------------------------------------------


def _authorized_key(action_records, actor_id: str):
    out = []
    for rec in action_records:
        d = rec.to_dict()
        if d["actor"] != actor_id:
            continue
        params = {k: v for k, v in d["params"].items() if k != "offer"}
        out.append((d["month"], d["type"], tuple(sorted(params.items())), d["authorized"]))
    return out


def test_fake_rules_matches_rules_with_congress_and_negotiation() -> None:
    policy_rule = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    target_actors = ("gov_norte", "party_frente_federal", "union_cgt")
    baseline = run(
        seed=7,
        months=12,
        policy_rule=policy_rule,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
    )
    via_llm = run(
        seed=7,
        months=12,
        policy_rule=policy_rule,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        brain_map={a: "fake:rules" for a in target_actors},
    )
    for actor_id in target_actors:
        assert _authorized_key(via_llm.action_records, actor_id) == _authorized_key(
            baseline.action_records, actor_id
        )
    baseline_votes = [v.to_dict() for v in baseline.vote_records]
    llm_votes = [v.to_dict() for v in via_llm.vote_records]
    assert baseline_votes == llm_votes


# ---------------------------------------------------------------------------
# 5. DoD parcial de ADR 005 secc. 7 item 5: registros `vote`/`negotiation`
# presentes, corrida rapida.
# ---------------------------------------------------------------------------


def test_full_run_has_vote_and_negotiation_records_and_is_fast() -> None:
    policy_rule = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    t0 = time.perf_counter()
    history: History = run(
        seed=7,
        months=48,
        policy_rule=policy_rule,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0
    assert len(history.vote_records) > 0
    assert len(history.negotiation_records) > 0
    jsonl = history.to_jsonl()
    assert '"kind": "vote"' in jsonl
    assert '"kind": "negotiation"' in jsonl


# ---------------------------------------------------------------------------
# 6. `--no-congress --no-negotiation` byte-identico a HEAD (commit bc3a3b2,
# previo a esta corrida de ADR 005): golden hash del JSONL de
# `run(actors_enabled=True)` sin las features nuevas, con `config_hash`
# (el unico byte que cambia al tocar `data/country.json`/`data/parties.json`,
# mismo precedente que REVIEW_001 hallazgo #8/ADR 003 secc. 11 punto 6)
# reemplazado por un placeholder antes de hashear.
# ---------------------------------------------------------------------------

GOLDEN_SEED7_CONSTANT_SHA256 = "981de307cb935ce23ef4a3a057b8ef07e2267b5b37b8afee4a5e4ea90e385b7c"
GOLDEN_SEED42_TAYLOR_SHA256 = "e6e72f5ff16735e6ec4ee2e5ad48e02a82a963a34964a0dfd6d54204d947b64d"


def _strip_config_hash(jsonl_text: str) -> str:
    lines = jsonl_text.rstrip("\n").split("\n")
    summary = json.loads(lines[-1])
    summary["config_hash"] = "STRIPPED"
    lines[-1] = json.dumps(summary, ensure_ascii=False)
    return "\n".join(lines) + "\n"


def test_features_off_matches_pre_adr005_golden_hash() -> None:
    h_constant = run(
        seed=7,
        months=48,
        policy_rule=ConstantPolicy(COUNTRY.default_policy),
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=False,
        negotiation_enabled=False,
    )
    stripped = _strip_config_hash(h_constant.to_jsonl())
    assert hashlib.sha256(stripped.encode("utf-8")).hexdigest() == GOLDEN_SEED7_CONSTANT_SHA256

    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    h_taylor = run(
        seed=42,
        months=48,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=False,
        negotiation_enabled=False,
    )
    stripped42 = _strip_config_hash(h_taylor.to_jsonl())
    assert hashlib.sha256(stripped42.encode("utf-8")).hexdigest() == GOLDEN_SEED42_TAYLOR_SHA256
