"""Tests de ADR 006 (memoria y elecciones, Fase 6) -- DoD secc. 3 (7 items)
mas el resto del deliverable 7 del encargo (retrieval ordering, umbral de
consolidacion, extraccion de `promised`, D'Hondt, golden hash con las dos
features apagadas, `fake:rules` con memoria prendida)."""

from __future__ import annotations

import hashlib
import json
import random

from republica.actors.rule_based import (
    compute_score,
    load_interests_config,
    load_signatures,
    load_weights,
)
from republica.actors.sheet import load_actors
from republica.ai.memory import MemoryEvent, MemoryStore, extract_promise
from republica.engine.perception import Perception
from republica.engine.policy import TaylorPolicy
from republica.engine.simulation import advance_month, new_simulation, run
from republica.world.cohorts import init_cohort_state, load_cohorts
from republica.world.config import Party, load_country
from republica.world.elections import (
    LoyaltyTable,
    dhondt,
    resolve_presidential,
    run_election,
)

COUNTRY = load_country()
ACTORS = load_actors()


def _perception(
    actor_id: str, relationships: dict[str, int], memory_score: float = 0.0
) -> Perception:
    return Perception(
        month=20,
        date="2030-01",
        months_to_election=10,
        public_indicators=dict(COUNTRY.initial_state.model_dump()),
        private_indicators={"dependence": 0.8},
        proposal=None,
        active_shocks=[],
        recent_events=[],
        relationships=relationships,
        memory_score=memory_score,
    )


# ---------------------------------------------------------------------------
# 1. Acuerdo roto en el turno 17 -> memorias recuperadas en el turno 20 +
#    score de negociacion menor que el contrafactico (ADR 006 secc. 3 item 1)
# ---------------------------------------------------------------------------


def test_broken_agreement_is_retrieved_and_lowers_negotiation_score() -> None:
    store = MemoryStore()
    store.add(
        MemoryEvent(
            turn=17,
            actor="gov_norte",
            about="president",
            kind="agreement_broken_by_government",
            summary="El gobierno no cumplio el acuerdo de restore_transfers con gov_norte.",
            importance=0.9,
            sentiment=-0.8,
        )
    )
    # Ruido: memorias irrelevantes (otro `about`) que no deberian desplazar
    # a la relevante del top-5 solo por volumen.
    for i in range(10):
        store.add(
            MemoryEvent(
                turn=18 + i,
                actor="gov_norte",
                about="party_union_republicana",
                kind="criticized_by",
                summary=f"critica menor {i}",
                importance=0.2,
                sentiment=-0.1,
            )
        )

    phrases = store.retrieve("gov_norte", now_turn=20, relevant_actors={"president"})
    assert len(phrases) <= 5
    assert any("no cumplio" in p for p in phrases)

    weights = load_weights()
    signatures = load_signatures()
    interests_cfg = load_interests_config()
    parties_by_id = {p.id: p for p in COUNTRY.parties}
    actor = ACTORS["gov_norte"]
    rng = random.Random(0)

    mem_score_broken = store.memory_term("gov_norte", 20, "president")
    counterfactual_score = 0.0
    assert mem_score_broken < counterfactual_score

    perc_broken = _perception("gov_norte", {"president": 50}, memory_score=mem_score_broken)
    perc_clean = _perception("gov_norte", {"president": 50}, memory_score=counterfactual_score)
    score_broken = compute_score(
        actor,
        perc_broken,
        parties_by_id,
        weights,
        signatures,
        interests_cfg,
        rng,
        memory_enabled=True,
    )
    rng2 = random.Random(0)
    score_clean = compute_score(
        actor,
        perc_clean,
        parties_by_id,
        weights,
        signatures,
        interests_cfg,
        rng2,
        memory_enabled=True,
    )
    assert score_broken.total < score_clean.total


# ---------------------------------------------------------------------------
# 2. Consolidacion: <= 12 entradas tras 24 turnos con 30 memorias menores,
#    ninguna importance >= 0.8 resumida (ADR 006 secc. 3 item 2)
# ---------------------------------------------------------------------------


def test_consolidation_bounds_store_and_never_summarizes_high_importance() -> None:
    store = MemoryStore()
    for about in ("president", "party_union_republicana", "party_partido_social"):
        for i in range(10):
            store.add(
                MemoryEvent(
                    turn=1,
                    actor="gov_norte",
                    about=about,
                    kind="request_refused",
                    summary=f"pedido rechazado {about} #{i}",
                    importance=0.3,
                    sentiment=-0.2,
                )
            )
    store.add(
        MemoryEvent(
            turn=1,
            actor="gov_norte",
            about="president",
            kind="agreement_broken_by_government",
            summary="ruptura grave",
            importance=0.9,
            sentiment=-0.8,
        )
    )
    assert len(store.for_owner("gov_norte")) == 31

    store.consolidate(24)
    events = store.for_owner("gov_norte")
    assert len(events) <= 12
    # la memoria grave sigue intacta, nunca resumida
    grave = [e for e in events if e.importance >= 0.8]
    assert len(grave) == 1
    assert grave[0].kind == "agreement_broken_by_government"
    assert all(e.kind != "summary" or e.importance < 0.8 for e in events)


# ---------------------------------------------------------------------------
# Retrieval: orden por score, devueltas ordenadas por turno
# ---------------------------------------------------------------------------


def test_retrieval_orders_by_score_then_returns_chronological() -> None:
    store = MemoryStore()
    # Baja importancia/recencia (turno viejo, sin relevancia): debe quedar
    # afuera del top-3.
    store.add(
        MemoryEvent(
            turn=1,
            actor="a",
            about=None,
            kind="request_refused",
            summary="vieja",
            importance=0.2,
            sentiment=-0.1,
        )
    )
    # Las 3 mejores por score (alta importancia y relevantes), en turnos
    # desordenados -- deben salir ordenadas por turno ascendente.
    store.add(
        MemoryEvent(
            turn=15,
            actor="a",
            about="president",
            kind="voted_for",
            summary="tercera",
            importance=0.5,
            sentiment=0.4,
        )
    )
    store.add(
        MemoryEvent(
            turn=5,
            actor="a",
            about="president",
            kind="concession_received",
            summary="primera",
            importance=0.9,
            sentiment=0.5,
        )
    )
    store.add(
        MemoryEvent(
            turn=10,
            actor="a",
            about="president",
            kind="agreement_honored",
            summary="segunda",
            importance=0.7,
            sentiment=0.6,
        )
    )
    phrases = store.retrieve("a", now_turn=20, relevant_actors={"president"}, k=3)
    assert phrases == ["primera", "segunda", "tercera"]


# ---------------------------------------------------------------------------
# `promised`: extraccion desde una oracion en espanol
# ---------------------------------------------------------------------------


def test_extract_promise_detects_commitment_verbs() -> None:
    assert extract_promise("Prometo bajar la inflacion antes de fin de año.")
    assert extract_promise("Nos comprometemos a no subir los impuestos.")
    assert not extract_promise("La inflacion bajo este mes segun el INDEC.")
    assert not extract_promise("")


# ---------------------------------------------------------------------------
# 3. Cohortes homogeneas + partidos con la misma ideologia -> vote_p casi
#    uniforme (ADR 006 secc. 3 item 3)
# ---------------------------------------------------------------------------


def test_uniform_ideology_and_no_loyalty_gives_near_uniform_vote_share() -> None:
    cohorts = load_cohorts()
    cohort_state = init_cohort_state(cohorts, COUNTRY.initial_state)
    parties = [
        Party(
            id=f"p{i}",
            name=f"P{i}",
            seats=20,
            economic=0.1,
            social=0.0,
            in_government=False,
            discipline=1.0,
        )
        for i in range(5)
    ]
    result = run_election(
        48,
        cohorts,
        cohort_state,
        parties,
        government_approval=50.0,
        loyalty=LoyaltyTable(),
        rng=random.Random(7),
        delta_real_wage_pct_12m=0.0,
        delta_unemployment_12m=0.0,
    )
    for pct in result.first_round.values():
        assert 17.0 <= pct <= 23.0  # 20% +- 3pp (ADR literal)


# ---------------------------------------------------------------------------
# 4. Aprobacion 65 -> oficialismo gana >= 90% de 100 semillas; 25 -> pierde
#    en >= 90% (ADR 006 secc. 3 item 4)
# ---------------------------------------------------------------------------


def _incumbent_win_rate(approval: float, n: int = 100) -> float:
    cohorts = load_cohorts()
    cohort_state = init_cohort_state(cohorts, COUNTRY.initial_state)
    incumbent = Party(
        id="inc",
        name="Inc",
        seats=50,
        economic=0.0,
        social=0.0,
        in_government=True,
        discipline=1.0,
    )
    challenger = Party(
        id="chal",
        name="Chal",
        seats=50,
        economic=0.0,
        social=0.0,
        in_government=False,
        discipline=1.0,
    )
    wins = 0
    for seed in range(n):
        result = run_election(
            48,
            cohorts,
            cohort_state,
            [incumbent, challenger],
            government_approval=approval,
            loyalty=LoyaltyTable(),
            rng=random.Random(seed),
            delta_real_wage_pct_12m=0.0,
            delta_unemployment_12m=0.0,
        )
        if result.winner == "inc":
            wins += 1
    return wins / n


def test_high_approval_reelects_and_low_approval_defeats_in_at_least_90pct() -> None:
    assert _incumbent_win_rate(65.0) >= 0.90
    assert _incumbent_win_rate(25.0) <= 0.10


# ---------------------------------------------------------------------------
# 5. Balotaje deterministico con 38/33/29 (ADR 006 secc. 3 item 5)
# ---------------------------------------------------------------------------


def test_runoff_triggers_with_three_parties_and_is_deterministic() -> None:
    parties = [
        Party(id="a", name="A", seats=38, economic=-0.5, social=0.0, in_government=True),
        Party(id="b", name="B", seats=33, economic=0.5, social=0.0, in_government=False),
        Party(id="c", name="C", seats=29, economic=0.6, social=0.0, in_government=False),
    ]
    votes = {"a": 38.0, "b": 33.0, "c": 29.0}
    winner1, runoff1 = resolve_presidential(votes, parties)
    winner2, runoff2 = resolve_presidential(votes, parties)
    assert runoff1 is not None
    assert winner1 == winner2
    assert runoff1 == runoff2
    assert set(runoff1) == {"a", "b"}
    # ideologicamente, "c" esta mas cerca de "b": la mayor parte de sus
    # votos se transfieren a "b", que termina ganando el balotaje pese a
    # haber salido segundo en primera vuelta.
    assert winner1 == "b"

    # determinismo "por semilla" end-to-end (ADR literal): misma semilla,
    # mismo resultado completo (incluido el balotaje).
    cohorts = load_cohorts()
    cohort_state = init_cohort_state(cohorts, COUNTRY.initial_state)
    r1 = run_election(
        48,
        cohorts,
        cohort_state,
        parties,
        50.0,
        LoyaltyTable(),
        random.Random(3),
        delta_real_wage_pct_12m=0.0,
        delta_unemployment_12m=0.0,
    )
    r2 = run_election(
        48,
        cohorts,
        cohort_state,
        parties,
        50.0,
        LoyaltyTable(),
        random.Random(3),
        delta_real_wage_pct_12m=0.0,
        delta_unemployment_12m=0.0,
    )
    assert r1.to_dict() == r2.to_dict()


# ---------------------------------------------------------------------------
# 6. Transicion: derrota -> president.party cambia, gov_norte conserva sus
#    memorias, el nuevo presidente no hereda agreements (ADR 006 secc. 3
#    item 6)
# ---------------------------------------------------------------------------


def test_transition_after_defeat_changes_president_keeps_memories_clears_agreements() -> None:
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    sim = new_simulation(
        seed=7,
        policy_rule=taylor,
        forced_shocks=None,
        country=COUNTRY,
        shocks_enabled=True,
        exogenous_noise=True,
        actors_enabled=True,
        rule_based_president=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
    )
    sim.country = sim.country.model_copy(update={"months": 48})
    for _ in range(48):
        advance_month(sim)

    assert len(sim.election_records) == 1
    result = sim.election_records[0]
    assert result.winner != result.incumbent_party  # seed=7/taylor: cambia de gobierno
    assert sim.actor_engine.actors["president"].party == result.winner
    assert sim.actor_engine.actors["president"].id == "president"
    assert sim.actor_engine.agreements == []

    # `gov_costa` (con esta semilla) tiene memorias `about=president` antes
    # de la transicion: conserva su historial completo (no se vacia) y esas
    # memorias quedan re-etiquetadas al presidente saliente, no colgadas de
    # `"president"` (el cargo, ahora ocupado por otro partido).
    memories = sim.actor_engine.memory_store.for_owner("gov_costa")
    assert len(memories) > 0
    assert not any(m.about == "president" for m in memories)
    assert any(m.about == f"former_president_{result.incumbent_party}" for m in memories)


# ---------------------------------------------------------------------------
# 7. `run --months 96` completa dos mandatos, 2 `election` records (ADR 006
#    secc. 3 item 7)
# ---------------------------------------------------------------------------


def test_two_terms_in_96_months_produce_two_election_records() -> None:
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    history = run(
        seed=7,
        months=96,
        policy_rule=taylor,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
    )
    assert len(history.records) == 96
    assert len(history.election_records) == 2
    assert [e.month for e in history.election_records] == [48, 96]
    assert history.outcome in ("reelected", "defeated", "collapse", "hyperinflation")
    jsonl = history.to_jsonl()
    assert jsonl.count('"kind": "election"') == 2


# ---------------------------------------------------------------------------
# D'Hondt: ejemplo de manual (Wikipedia): A 100000, B 80000, C 30000,
# D 20000 votos, 8 bancas -> A4 B3 C1 D0.
# ---------------------------------------------------------------------------


def test_dhondt_matches_textbook_example() -> None:
    total = 100_000 + 80_000 + 30_000 + 20_000
    pct = {
        "A": 100_000 / total * 100,
        "B": 80_000 / total * 100,
        "C": 30_000 / total * 100,
        "D": 20_000 / total * 100,
    }
    seats = dhondt(pct, seats_total=8, threshold_pct=3.0)
    assert seats == {"A": 4, "B": 3, "C": 1, "D": 0}
    assert sum(seats.values()) == 8


def test_dhondt_seats_always_sum_to_total_and_respects_threshold() -> None:
    pct = {"A": 60.0, "B": 38.0, "C": 2.0}
    seats = dhondt(pct, seats_total=100, threshold_pct=3.0)
    assert sum(seats.values()) == 100
    assert seats["C"] == 0  # bajo el umbral del 3%


# ---------------------------------------------------------------------------
# Golden hash: `features.memory=False`/`features.elections=False` produce el
# mismo JSONL, byte a byte, que HEAD (commit 21f9cf6, previo a esta corrida
# de ADR 006). Calculado con `git worktree add /tmp/head HEAD` +
# `run(actors_enabled=True, congress_enabled=True, negotiation_enabled=True,
# cohorts_enabled=True, media_enabled=True)` (memory/elections no existian
# en ese commit), `config_hash` reemplazado por un placeholder antes de
# hashear (mismo precedente que los golden hash previos de ADR 004/005).
# ---------------------------------------------------------------------------

GOLDEN_HEAD_COMMIT = "21f9cf67c842b6e0437ad486857e1c96c1af9a93"
GOLDEN_SEED7_SHA256 = "8db63af02a867ad3c519a8c32bd0fce1750c7f653b8ea05015503cd7e4d12a9c"
GOLDEN_SEED42_TAYLOR_SHA256 = "617bf9b425bacee08638bed963aaebee0ed8404777b0dd8309a8569e97a87f7a"


def _strip_config_hash(jsonl_text: str) -> str:
    lines = jsonl_text.rstrip("\n").split("\n")
    summary = json.loads(lines[-1])
    summary["config_hash"] = "STRIPPED"
    lines[-1] = json.dumps(summary, ensure_ascii=False)
    return "\n".join(lines) + "\n"


def test_features_off_matches_pre_adr006_golden_hash() -> None:
    h_constant = run(
        seed=7,
        months=48,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=False,
        elections_enabled=False,
    )
    stripped = _strip_config_hash(h_constant.to_jsonl())
    assert hashlib.sha256(stripped.encode("utf-8")).hexdigest() == GOLDEN_SEED7_SHA256

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
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=False,
        elections_enabled=False,
    )
    stripped42 = _strip_config_hash(h_taylor.to_jsonl())
    assert hashlib.sha256(stripped42.encode("utf-8")).hexdigest() == GOLDEN_SEED42_TAYLOR_SHA256


# ---------------------------------------------------------------------------
# `fake:rules` reproduce exactamente `rules` con `features.memory = True`
# (ADR 004 secc. 9 test 1, re-verificado con memoria prendida: ver Notas de
# implementacion de ADR 006 -- `FakeBackend`/`build_backend` ganaron un
# `memory_enabled` para no divergir).
# ---------------------------------------------------------------------------


def _authorized_key(records, actor_id):
    out = []
    for r in records:
        if r.actor != actor_id:
            continue
        params = {k: v for k, v in r.params.items() if k != "offer"}
        out.append((r.month, r.type, tuple(sorted(params.items())), r.authorized))
    return out


def test_fake_rules_matches_rule_based_with_memory_enabled() -> None:
    target_actors = ("gov_norte", "union_cgt", "central_bank")
    baseline = run(
        seed=7,
        months=48,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
    )
    via_fake = run(
        seed=7,
        months=48,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        brain_map={actor_id: "fake:rules" for actor_id in target_actors},
    )
    for actor_id in target_actors:
        assert _authorized_key(via_fake.action_records, actor_id) == _authorized_key(
            baseline.action_records, actor_id
        )
