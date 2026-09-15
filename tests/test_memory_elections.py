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
from republica.engine.perception import (
    Perception,
    PolicyProposal,
    build_perception,
    build_provinces_table,
)
from republica.engine.policy import TaylorPolicy
from republica.engine.simulation import (
    advance_month,
    compute_months_to_election,
    new_simulation,
    run,
)
from republica.world.cohorts import Cohort, CohortState, init_cohort_state, load_cohorts
from republica.world.config import Party, load_country
from republica.world.economy import Aux
from republica.world.elections import (
    LoyaltyTable,
    compute_regional_bonus,
    compute_vote_intention,
    dhondt,
    load_loyalty,
    load_province_weights,
    resolve_presidential,
    run_election,
)
from republica.world.events import ShockAggregate
from republica.world.provinces import compute_provinces

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
    """Hallazgo #8 de REVIEW_002: el test original solo prueba una entrada
    simetrica por construccion (5 partidos IDENTICOS) contra una salida
    ~uniforme -- eso pasaria igual con un `v_ideo` roto que ignorara la
    ideologia por completo (todas las entradas siguen siendo iguales entre
    si). Se agrega un caso de contraste: una cohorte con `econ_pref` fijo y
    dos partidos que SI difieren en `economic` (uno cerca, uno lejos), sin
    `discipline`/loyalty/campana/bancas de por medio (`compute_vote_
    intention` a bajo nivel, ninguno de los dos partidos gobierna: la unica
    diferencia entre ambos es `v_ideo`). Si `v_ideo` respondiera a
    `|c.econ_pref - p.economic|` como declara ADR 006 secc. 2.2, el partido
    mas cercano debe llevarse una mayoria clara del share."""
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

    # Contraste (hallazgo #8): mismo mecanismo, entrada deliberadamente NO
    # simetrica -- confirma que `v_ideo` esta realmente atado a la distancia
    # ideologica, no que la funcion sea un no-op que da uniforme siempre.
    contrast_cohort = Cohort(
        id="c_left",
        name="Cohorte izquierda",
        pop_share=1.0,
        income=1.0,
        u_offset=0.0,
        s_pi=0.0,
        s_u=0.0,
        s_w=0.0,
        s_tr=0.0,
        s_tax=0.0,
        s_crime=0.0,
        trust=50.0,
        econ_pref=-1.0,
        bloc_actor=None,
    )
    contrast_state = {
        contrast_cohort.id: CohortState(
            approval=50.0, sentiment=0.0, perceived_inflation=0.0, perceived_unemployment=0.0
        )
    }
    party_close = Party(
        id="left", name="Left", seats=10, economic=-1.0, social=0.0, in_government=False
    )
    party_far = Party(
        id="right", name="Right", seats=10, economic=1.0, social=0.0, in_government=False
    )
    contrast_shares = compute_vote_intention(
        [contrast_cohort],
        contrast_state,
        [party_close, party_far],
        government_approval=50.0,
        loyalty=LoyaltyTable(),
        delta_real_wage_pct_12m=0.0,
        delta_unemployment_12m=0.0,
    )[contrast_cohort.id]
    assert contrast_shares[party_close.id] > contrast_shares[party_far.id] + 0.5


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
# 6.bis. Hallazgo #1 de REVIEW_002: `parties_by_id` de CADA `decision_actor`
# refleja las bancas/`in_government` de la eleccion recien corrida -- antes
# quedaba con las de ANTES de la transicion todo el mandato siguiente
# (`_in_government()` invertia el signo de `electoral_pressure`/
# `_impact_reelection`/la distancia editorial de medios).
# ---------------------------------------------------------------------------


def test_parties_by_id_refreshed_on_every_decision_actor_after_transition() -> None:
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

    # Cada decision_actor por reglas quedo con la MISMA tabla de partidos
    # que `sim.country.parties` (la de la eleccion recien corrida), no la de
    # `build_actor_engine` al principio de la corrida.
    expected_parties_by_id = {p.id: p for p in sim.country.parties}
    assert expected_parties_by_id[result.winner].in_government is True
    for actor_id, decision_actor in sim.actor_engine.decision_actors.items():
        assert decision_actor.parties_by_id == expected_parties_by_id, actor_id

    # Un gobernador del partido ganador: `electoral_pressure` (via
    # `compute_score`, el mismo camino que corre `decide()`) ahora da
    # positivo cerca de SU proxima eleccion con aprobacion > 50 -- antes del
    # fix, `parties_by_id` seguia diciendo que este partido NO gobernaba
    # (el oficialismo saliente), invirtiendo el signo.
    winner_governor_id = next(
        aid
        for aid, sheet in sim.actor_engine.actors.items()
        if sheet.role == "governor" and sheet.party == result.winner
    )
    winner_governor = sim.actor_engine.actors[winner_governor_id]
    decision_actor = sim.actor_engine.decision_actors[winner_governor_id]
    agg = ShockAggregate()
    aux = Aux(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    table = build_provinces_table(sim.state, sim.last_effective_policy, sim.country.provinces, agg)
    high_approval_state = sim.state.model_copy(update={"government_approval": 65.0})
    perception = build_perception(
        winner_governor,
        high_approval_state,
        aux,
        PolicyProposal(delta={}, label="test"),
        [],
        [],
        sim.month,
        2,  # months_to_election: cerca de la proxima eleccion (proximity > 0)
        table,
        sim.country.parties,
        policy=sim.last_effective_policy,
    )
    decision_actor.decide(perception, random.Random(0))
    assert decision_actor.last_score is not None
    assert decision_actor.last_score.elec > 0


# ---------------------------------------------------------------------------
# Hallazgo #3 de REVIEW_002: `months_to_election` real (`term_length`), no
# el placeholder de Fase 3 (`country.months − month + 1`, que cuenta hasta
# el FIN DE LA CORRIDA). En una corrida de 96 meses (`term_length=48`)
# nadie sentia presion electoral antes del mes 48 con el placeholder.
# ---------------------------------------------------------------------------


def test_months_to_election_uses_term_length_not_total_run_length() -> None:
    term_length = COUNTRY.term_length
    assert term_length == 48
    # Mes 50 (segundo mandato, arranca en el 49): faltan 46 para la proxima
    # eleccion (mes 96), no 96 - 50 + 1 = 47 del placeholder ni algo que
    # dependa de `total_months` en absoluto.
    assert compute_months_to_election(50, 96, term_length, elections_enabled=True) == 46
    # Mes de la eleccion misma: 0 meses para la proxima (arranca el conteo
    # del mandato siguiente).
    assert compute_months_to_election(48, 96, term_length, elections_enabled=True) == 0
    assert compute_months_to_election(96, 96, term_length, elections_enabled=True) == 0
    # `elections_enabled=False`: el placeholder de siempre, SIN tocar (golden
    # hashes de corridas sin elecciones intactos).
    assert compute_months_to_election(50, 96, term_length, elections_enabled=False) == 47


def test_seed7_taylor_96_months_elec_score_nonzero_before_first_election() -> None:
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
    sim.country = sim.country.model_copy(update={"months": 96})
    for _ in range(46):
        advance_month(sim)
    assert sim.month == 46

    # Con el placeholder viejo (`96 - 46 + 1 = 51`), `proximity` (`clamp(1 -
    # months_to_election/12, 0, 1)`) saturaba a 0 y `elec` daba SIEMPRE 0
    # para cualquier partido/gobernador, sin importar aprobacion/signo. Con
    # el fix (`months_to_election = 2`, `is_election_month(48, 48)`),
    # `elec != 0` para el partido de gobierno.
    gov_party_id = next(p.id for p in sim.country.parties if p.in_government)
    party_actor_id = f"party_{gov_party_id}"
    scores = sim.actor_engine.decision_actors[party_actor_id].last_score
    assert scores is not None
    assert scores.elec != 0.0


# ---------------------------------------------------------------------------
# 7. `run --months 96` completa dos mandatos, 2 `election` records (ADR 006
#    secc. 3 item 7)
# ---------------------------------------------------------------------------


def test_two_terms_in_96_months_produce_two_election_records() -> None:
    """Hallazgo #8 de REVIEW_002: la version original solo contaba
    registros (`len(...) == 2`, meses `[48, 96]`) sin mirar su CONTENIDO --
    eso pasaria igual aunque las dos elecciones dieran resultados
    incoherentes entre si (p.ej. el `incumbent_party` de la segunda sin
    relacion con el `winner` de la primera, o bancas que no suman el total).
    Se agregan invariantes de continuidad entre mandatos y de las bancas de
    CADA eleccion."""
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

    party_ids = {p.id for p in COUNTRY.parties}
    total_seats = sum(p.seats for p in COUNTRY.parties)
    first, second = history.election_records
    # Continuidad entre mandatos: quien gana la primera eleccion es el
    # oficialismo saliente que la segunda evalua (`in_government` se
    # actualiza en la transicion, `_run_election` en `engine/simulation.py`).
    assert second.incumbent_party == first.winner
    for election in (first, second):
        assert election.winner in party_ids
        assert election.incumbent_party in party_ids
        assert set(election.seats) == party_ids
        assert sum(election.seats.values()) == total_seats
        assert all(s >= 0 for s in election.seats.values())
        reelected = election.winner == election.incumbent_party
        expected_outcome_type = "reelected" if reelected else "defeated"
        assert election.outcome_type == expected_outcome_type


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
# Calibracion (encargo de calibracion, mes 48 de `run --seed 7 --policy
# taylor --months 96` casi uniforme y Alianza Provincial ganando la
# presidencia): 6 metas, cada una como test, mas la recalibracion de
# `data/cohorts_loyalty.csv`/`TAU_SHARE`/`data/cohort_provinces.csv` que las
# hace pasar (ver docs/CALIBRATION_LOG.md para el detalle numerico completo).
# ---------------------------------------------------------------------------

#: Bancas iniciales de `data/parties.json` (38/30/14/10/8 sobre 100), meta
#: de la calibracion 1 (linea de base).
INITIAL_SEAT_SHARE_PCT = {
    "frente_federal": 38.0,
    "union_republicana": 30.0,
    "partido_social": 14.0,
    "movimiento_libertad": 10.0,
    "alianza_provincial": 8.0,
}


def _baseline_intention_and_avg_first_round(n_seeds: int = 50) -> dict[str, float]:
    """Linea de base de la meta 1: `approval_c = 50` (default de
    `init_cohort_state`), sin cambio economico en 12 meses
    (`Δreal_wage = Δunemployment = 0`), `perceived_inflation = 2`
    (tambien el default de `init_cohort_state` con `COUNTRY.initial_state`),
    sin campana ni eventos recientes (`campaign_state`/`memory_store` en
    blanco, los defaults de `run_election`) -- primera vuelta promediada
    sobre `n_seeds` semillas (el ruido de `aggregate_vote` es lo unico que
    varia entre semillas; la intencion de voto en si es determinista)."""
    cohorts = load_cohorts()
    cohort_state = init_cohort_state(cohorts, COUNTRY.initial_state)
    loyalty = load_loyalty()
    totals = dict.fromkeys(INITIAL_SEAT_SHARE_PCT, 0.0)
    for seed in range(n_seeds):
        result = run_election(
            48,
            cohorts,
            cohort_state,
            COUNTRY.parties,
            government_approval=50.0,
            loyalty=loyalty,
            rng=random.Random(seed),
            delta_real_wage_pct_12m=0.0,
            delta_unemployment_12m=0.0,
        )
        for pid, v in result.first_round.items():
            totals[pid] += v
    return {pid: v / n_seeds for pid, v in totals.items()}


def test_baseline_reproduces_initial_party_system() -> None:
    """Meta 1 del encargo de calibracion: la linea de base (secc. arriba)
    reproduce las bancas iniciales de `data/parties.json` (38/30/14/10/8)
    dentro de +-5pp, promediado sobre 50 semillas -- logrado calibrando
    `data/cohorts_loyalty.csv` y `TAU_SHARE` (ver docs/CALIBRATION_LOG.md),
    no la forma de `compute_vote_intention`."""
    avg = _baseline_intention_and_avg_first_round(50)
    for party_id, target_pct in INITIAL_SEAT_SHARE_PCT.items():
        assert abs(avg[party_id] - target_pct) <= 5.0, (
            f"{party_id}: avg={avg[party_id]:.2f} target={target_pct} "
            f"(fuera de +-5pp, ver docs/CALIBRATION_LOG.md)"
        )


def test_economic_vote_moves_incumbent_share_at_least_6pp() -> None:
    """Meta 3 del encargo de calibracion: entre dos lineas de base
    identicas salvo el salario real (`+8%` vs `-8%` en 12 meses, desempleo
    sin cambios), la primera vuelta del oficialismo debe moverse >= 6pp
    (`econ_vote_c`/`v_econ`, ADR 006 secc. 2.2 -- formula sin tocar, el
    salto sale de la calibracion de `TAU_SHARE`/lealtad que ya no aplasta
    las diferencias de util)."""
    cohorts = load_cohorts()
    cohort_state = init_cohort_state(cohorts, COUNTRY.initial_state)
    loyalty = load_loyalty()
    incumbent = next(p.id for p in COUNTRY.parties if p.in_government)

    def avg_incumbent_share(delta_wage: float, n_seeds: int = 50) -> float:
        total = 0.0
        for seed in range(n_seeds):
            result = run_election(
                48,
                cohorts,
                cohort_state,
                COUNTRY.parties,
                government_approval=50.0,
                loyalty=loyalty,
                rng=random.Random(seed),
                delta_real_wage_pct_12m=delta_wage,
                delta_unemployment_12m=0.0,
            )
            total += result.first_round[incumbent]
        return total / n_seeds

    good = avg_incumbent_share(8.0)
    bad = avg_incumbent_share(-8.0)
    assert good - bad >= 6.0, f"good={good:.2f} bad={bad:.2f} diff={good - bad:.2f}"


def test_negative_cohort_memories_lower_incumbent_share() -> None:
    """Hallazgo #2 de REVIEW_002: `v_evt * recent_events_c` (`world/
    elections.py::compute_vote_intention`) se sumaba FUERA del `if
    p.in_government`, un termino IDENTICO para todos los partidos de la
    cohorte -- constante aditiva que el softmax cancela exactamente (no
    mueve ningun `share`). Con memorias, sin memorias: shares byte a byte
    iguales. Aplicado solo al oficialismo (como `v_econ`/`v_appr`), 5
    memorias negativas recientes de una cohorte (`shock_hit`/
    `forced_devaluation`, ADR 006 secc. 2.2) deben bajar el `share` del
    oficialismo en esa cohorte."""
    cohorts = load_cohorts()
    cohort_state = init_cohort_state(cohorts, COUNTRY.initial_state)
    loyalty = load_loyalty()
    incumbent = next(p.id for p in COUNTRY.parties if p.in_government)
    cohort_id = cohorts[0].id

    store = MemoryStore()
    for i in range(5):
        store.add(
            MemoryEvent(
                turn=44 + i,
                actor=cohort_id,
                kind="shock_hit",
                summary=f"shock {i}",
                importance=0.7,
                sentiment=-0.5,
            )
        )

    common = dict(
        cohorts=cohorts,
        cohort_state=cohort_state,
        parties=COUNTRY.parties,
        government_approval=50.0,
        loyalty=loyalty,
        delta_real_wage_pct_12m=0.0,
        delta_unemployment_12m=0.0,
        now_turn=48,
    )
    share_without = compute_vote_intention(**common, memory_store=None)
    share_with = compute_vote_intention(**common, memory_store=store)
    # Sin memorias/con memorias positivas o fuera de ventana, `share` no
    # deberia moverse en absoluto para NINGUNA cohorte SIN memorias (el
    # termino sigue siendo 0 ahi, `recent_events_term` devuelve 0.0 sin
    # eventos): confirma que el fix no introduce ruido en cohortes
    # no afectadas.
    other_cohort_ids = [c.id for c in cohorts if c.id != cohort_id]
    for other_id in other_cohort_ids:
        assert share_with[other_id] == share_without[other_id]
    assert share_with[cohort_id][incumbent] < share_without[cohort_id][incumbent]


def test_regional_bonus_favors_governing_party_in_its_province() -> None:
    """Meta 4 del encargo de calibracion: `regional_bonus_c,p` (ADR 006
    secc. 2.2, antes fijo en 0 -- nota de implementacion #10) ahora es real.
    `data/cohort_provinces.csv` (peso de poblacion de cada cohorte por
    provincia) + `compute_regional_bonus` (calibracion, formula documentada
    en `world/elections.py::province_performance`: sin ADR que la fije) le
    dan a Alianza Provincial (gobernadora de `norte`, `data/provinces.csv`)
    una ventaja medible en `rural`/`informal` (las cohortes con mas peso en
    `norte`, ver `data/cohort_provinces.csv`) cuando esa provincia le va
    mejor que al pais -- y ninguna ventaja cuando no hay datos de provincia
    (`regional_bonus=None`, comportamiento anterior)."""
    cohorts = load_cohorts()
    cohort_state = init_cohort_state(cohorts, COUNTRY.initial_state)
    loyalty = load_loyalty()
    province_weights = load_province_weights()
    assert province_weights, "data/cohort_provinces.csv no cargo ningun peso"

    # Shock economico grande y localizado en `norte` (gobernada por AP):
    # income_p sube bien por encima del resto del pais, unemployment_p sin
    # cambios -- `province_performance` debe leerlo como un gobierno
    # provincial que le va mejor que el promedio nacional.
    agg = ShockAggregate()
    agg.province_id["norte"] = 50.0
    provinces = compute_provinces(
        COUNTRY.initial_state,
        COUNTRY.default_policy,
        COUNTRY.provinces,
        COUNTRY.coefficients.province_transfer_sensitivity,
        COUNTRY.coefficients.transfers_ref,
        agg,
    )
    bonus = compute_regional_bonus(
        cohorts, COUNTRY.provinces, provinces, province_weights, COUNTRY.initial_state.unemployment
    )
    assert bonus[("rural", "alianza_provincial")] > 0.0
    assert bonus[("informal", "alianza_provincial")] > 0.0

    intention_with = compute_vote_intention(
        cohorts,
        cohort_state,
        COUNTRY.parties,
        government_approval=50.0,
        loyalty=loyalty,
        delta_real_wage_pct_12m=0.0,
        delta_unemployment_12m=0.0,
        regional_bonus=bonus,
    )
    intention_without = compute_vote_intention(
        cohorts,
        cohort_state,
        COUNTRY.parties,
        government_approval=50.0,
        loyalty=loyalty,
        delta_real_wage_pct_12m=0.0,
        delta_unemployment_12m=0.0,
        regional_bonus=None,
    )
    assert (
        intention_with["rural"]["alianza_provincial"]
        > intention_without["rural"]["alianza_provincial"]
    )
    assert (
        intention_with["informal"]["alianza_provincial"]
        > intention_without["informal"]["alianza_provincial"]
    )


def test_seed7_taylor_month48_no_longer_near_uniform_and_incumbent_loses() -> None:
    """Meta 6 del encargo de calibracion: el mes 48 de `run --seed 7
    --policy taylor --months 96` (el caso que reporta el encargo: FF 19.4 %,
    UR 21.9 %, PS 20.0 %, ML 15.6 %, AP 23.1 %, gana Alianza Provincial) ya
    no es casi uniforme y la aprobacion agregada del mes 47 (baja: el
    oficialismo viene cayendo) es consistente con el resultado -- pierde,
    pero contra un partido mayoritario, no Alianza Provincial (ver
    docs/CALIBRATION_LOG.md para los numeros completos antes/despues)."""
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
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
    )
    er48 = history.election_records[0]
    assert er48.month == 48
    shares = er48.first_round
    spread = max(shares.values()) - min(shares.values())
    assert spread > 10.0, f"primera vuelta casi uniforme otra vez: {shares}"

    approval_month47 = history.records[46].state["government_approval"]
    assert approval_month47 < 40.0  # oficialismo cayendo, consistente con perder

    assert er48.winner != er48.incumbent_party  # aprobacion baja -> pierde
    assert er48.winner != "alianza_provincial"  # pero no gana el partido regional
    assert sum(er48.seats.values()) == 100  # D'Hondt sigue sumando 100 bancas


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

#: Recalculado tras REVIEW_002 hallazgo #5 (misma causa que los golden de
#: `tests/test_cohorts_perception.py`/`tests/test_evals_governance.py`:
#: `congress_enabled`/`negotiation_enabled` ON con `policy=taylor` produjo
#: al menos una concesion sin ley honrada en el mismo mes de un `Bill`,
#: cambiando ese voto; el invariante de este test -- "elecciones apagadas
#: reproduce el comportamiento de antes de ADR 006" -- no depende de la
#: formula de negociacion/Congreso, sigue intacto). El `seed=7`/
#: `ConstantPolicy` de arriba (`GOLDEN_SEED7_SHA256`) no cambio: verificado
#: recalculandolo igual, mismo hash -- esa corrida en particular no llega a
#: tener una concesion honrada-en-el-mes-del-bill en 48 meses. Recalculado
#: corriendo el mismo `run(...)` de mas abajo contra el codigo ya corregido
#: (no `git worktree add HEAD`: HEAD apunta al commit CON el bug, un
#: worktree de HEAD solo reproduce el hash viejo) -- verificado
#: deterministico.
GOLDEN_SEED42_TAYLOR_SHA256 = "1e25a3e9077d7b47e698f3f0cdb2a622dc926f10f276a1bcfba86e4090124675"


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
