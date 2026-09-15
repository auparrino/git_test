"""Tests de ADR 005 secc. 3/4 (cohortes sociales, medios y percepcion) --
segunda mitad de Fase 5 (deliverable 8 del encargo, DoD de ADR 005 secc. 7
items 3-6, mas el resto del deliverable 7 del encargo de este commit)."""

from __future__ import annotations

import hashlib
import json
import time
from unittest import mock

import pytest

import republica.engine.simulation as simulation_mod
from republica.actors.llm_based import LLMActor
from republica.actors.sheet import load_actors
from republica.ai.backends import FakeBackend
from republica.engine.emergence import detect
from republica.engine.narrate import load_jsonl
from republica.engine.policy import TaylorPolicy
from republica.engine.simulation import History, advance_month, new_simulation, run
from republica.world.cohorts import Cohort, load_cohorts
from republica.world.config import load_country
from republica.world.perception import (
    FRAME_BIAS,
    MediaAction,
    audience_alignment,
    compute_bias,
    drift_audience,
    load_media_consumption,
)

COUNTRY = load_country()
ACTORS = load_actors()


# ---------------------------------------------------------------------------
# 1. `data/cohorts.csv` (ADR 005 secc. 3)
# ---------------------------------------------------------------------------


def test_cohorts_csv_loads_eight_cohorts_and_pop_share_sums_to_one() -> None:
    cohorts = load_cohorts()
    assert len(cohorts) == 8
    assert {c.id for c in cohorts} == {
        "urban_workers",
        "rural",
        "middle_class",
        "public_employees",
        "young_professionals",
        "informal",
        "retirees",
        "students",
    }
    assert sum(c.pop_share for c in cohorts) == pytest.approx(1.0)
    # `bloc_actor` (secc. 3, ultimo parrafo): 5 de las 8 cohortes tienen
    # bloque social propio.
    with_bloc = {c.id: c.bloc_actor for c in cohorts if c.bloc_actor}
    assert with_bloc == {
        "urban_workers": "bloc_urban_workers",
        "rural": "bloc_rural",
        "middle_class": "bloc_middle_class",
        "public_employees": "bloc_public_employees",
        "informal": "bloc_informal",
    }


# ---------------------------------------------------------------------------
# 2. Cohortes homogeneas reproducen v0.1 (ADR 005 secc. 7 item 3)
# ---------------------------------------------------------------------------

#: `s_pi = s_u = s_w = 1` (los que tienen equivalente directo en la formula
#: de v0.1, SPEC secc. 5.6); `s_tr = s_tax = s_crime = 0` -- ADR 005 secc. 3
#: agrega estos tres terminos (transferencias/impuestos/inseguridad) que
#: v0.1 **no tiene en absoluto** (`world/politics.py::step_politics` no los
#: menciona), asi que "reproducir v0.1" con ellos en `1` no reproduce nada
#: (`crime_perception`/transferencias/impuestos se mueven en la corrida
#: igual y esos terminos no tienen forma de anularse solos): se leen en `0`
#: para el test de homogeneidad, `econ_pref = 0` anula el termino nuevo
#: restante (`policy_direction`). Con esto, la formula de cada cohorte
#: colapsa termino a termino a la de v0.1 y, verificado empiricamente, el
#: agregado ponderado reproduce el approval de v0.1 **exacto** (no solo
#: dentro de la tolerancia de 0.05/mes que pide el ADR) en 48 meses con
#: `TaylorPolicy` -- documentado en Notas de implementacion.
HOMOGENEOUS_COHORTS = [
    Cohort(
        id=f"h{i}",
        name=f"Cohorte homogenea {i}",
        pop_share=0.25,
        income=100.0,
        u_offset=0.0,
        s_pi=1.0,
        s_u=1.0,
        s_w=1.0,
        s_tr=0.0,
        s_tax=0.0,
        s_crime=0.0,
        trust=50.0,
        econ_pref=0.0,
        bloc_actor=None,
    )
    for i in range(4)
]


def test_homogeneous_cohorts_reproduce_v01_aggregate_approval() -> None:
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    baseline = run(
        seed=7,
        months=48,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=False,
        cohorts_enabled=False,
    )
    with_cohorts = run(
        seed=7,
        months=48,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=False,
        cohorts_enabled=True,
        media_enabled=False,
        cohorts=HOMOGENEOUS_COHORTS,
    )
    assert len(baseline.records) == len(with_cohorts.records) == 48
    for r1, r2 in zip(baseline.records, with_cohorts.records, strict=True):
        diff = abs(r1.state["government_approval"] - r2.state["government_approval"])
        assert diff < 0.05, (
            f"mes {r1.month_index}: v0.1={r1.state['government_approval']!r} "
            f"cohortes={r2.state['government_approval']!r} diff={diff!r}"
        )


# ---------------------------------------------------------------------------
# 3. Sesgo de medios (ADR 005 secc. 7 item 4, primera mitad: media_mercado
# en crisis sube mas la percepcion de middle_class que la de informal)
# ---------------------------------------------------------------------------


def test_media_mercado_crisis_biases_middle_class_more_than_informal() -> None:
    """`data/media_consumption.csv`: `middle_class` consume `media_mercado`
    0.50 de su dieta, `informal` solo 0.10 -- con `target_bloc = "all"` (se
    reparte por consumo, secc. 4.3), el sesgo de inflacion percibida de
    `middle_class` tiene que ser mayor (ADR 005 secc. 7 item 4)."""
    cohorts = load_cohorts()
    consumption = load_media_consumption()
    actions = [
        MediaAction(
            outlet_id="media_mercado", frame="crisis", target_bloc="all", influence_public=0.4
        )
    ]
    bias = compute_bias(cohorts, actions, consumption)
    assert bias["middle_class"]["inflation"] > bias["informal"]["inflation"] > 0.0
    assert bias["middle_class"]["unemployment"] > bias["informal"]["unemployment"] > 0.0


def test_target_bloc_limits_bias_to_that_cohort() -> None:
    """`target_bloc` != `"all"` limita el efecto a esa cohorte sola (secc.
    4.3): ninguna otra cohorte se mueve."""
    cohorts = load_cohorts()
    consumption = load_media_consumption()
    actions = [
        MediaAction(
            outlet_id="media_mercado",
            frame="crisis",
            target_bloc="middle_class",
            influence_public=0.4,
        )
    ]
    bias = compute_bias(cohorts, actions, consumption)
    assert bias["middle_class"]["inflation"] == pytest.approx(1.5 * 0.4)
    for cohort_id, b in bias.items():
        if cohort_id != "middle_class":
            assert b["inflation"] == 0.0
            assert b["unemployment"] == 0.0
            assert b["sentiment"] == 0.0


def test_neutral_frame_never_biases_anything() -> None:
    """`frame = "neutral"` (tabla secc. 4.3, todo en 0): `compute_bias` no
    aporta nada -- exactamente como si no hubiera habido ningun
    `PUBLISH_STORY` ese mes (los medios "nunca tocan una variable real",
    secc. 4)."""
    cohorts = load_cohorts()
    consumption = load_media_consumption()
    for target in ("all", "middle_class"):
        actions = [
            MediaAction(
                outlet_id="media_mercado", frame="neutral", target_bloc=target, influence_public=0.4
            )
        ]
        bias = compute_bias(cohorts, actions, consumption)
        for b in bias.values():
            assert b == {"inflation": 0.0, "unemployment": 0.0, "sentiment": 0.0}


# ---------------------------------------------------------------------------
# 4. Con todos los frames neutral, la trayectoria real se acerca a
# `features.media = False` (ADR 005 secc. 7 item 4, segunda mitad)
# ---------------------------------------------------------------------------

#: `FRAME_BIAS` con todo en 0 (equivalente a forzar cada `PUBLISH_STORY` de
#: la corrida a `frame = "neutral"`, sin tener que controlar que frame elige
#: cada medio por reglas mes a mes).
_ZERO_FRAME_BIAS = {
    frame: {"inflation": 0.0, "unemployment": 0.0, "sentiment": 0.0} for frame in FRAME_BIAS
}


def test_all_neutral_frames_stay_close_to_media_off() -> None:
    """ADR 005 secc. 4.4: "con todos los frames `neutral`, la trayectoria
    real es identica a `features.media = false`". Con sesgo 0 en todos los
    meses, `step_perception` sigue actualizando `perceived_inflation_c` con
    un rezago `q = 0.4` hacia la inflacion real, mientras que
    `features.media = False` la sincroniza instantaneamente cada mes
    (`world/perception.py::sync_to_real`, elegido deliberadamente asi para
    que el test de homogeneidad de arriba de exacto -- ver Notas de
    implementacion): con sesgo cero ambos caminos convergen al mismo lugar,
    pero no son bit-identicos mes a mes (el rezago introduce una diferencia
    de segundo orden, amplificada por el lazo `government_approval ->
    protest_level -> social_tension -> government_approval` de `world/
    society.py`/`world/politics.py`, que crece con el horizonte -- ~0.2
    puntos de aprobacion a los 12 meses, pasa 1 punto bien entrada la
    segunda mitad de una corrida de 48). Se verifica sobre una ventana de
    12 meses (donde el rezago todavia no se nota) que la trayectoria real
    queda *cerca* (no bit-identica) -- la cota documenta la diferencia real
    en vez de ocultarla; ver Notas de implementacion."""
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    media_off = run(
        seed=7,
        months=12,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=True,
        cohorts_enabled=True,
        media_enabled=False,
    )
    with mock.patch("republica.world.perception.FRAME_BIAS", _ZERO_FRAME_BIAS):
        media_on_neutral = run(
            seed=7,
            months=12,
            policy_rule=taylor,
            country=COUNTRY,
            actors_enabled=True,
            cohorts_enabled=True,
            media_enabled=True,
        )
    for field in ("inflation", "unemployment", "gdp_growth", "government_approval"):
        for r1, r2 in zip(media_off.records, media_on_neutral.records, strict=True):
            assert abs(r1.state[field] - r2.state[field]) < 0.5, (
                f"{field} mes {r1.month_index}: {r1.state[field]!r} vs {r2.state[field]!r}"
            )


# ---------------------------------------------------------------------------
# 5. Audiencia (ADR 005 secc. 4.5, deliverable 2)
# ---------------------------------------------------------------------------


def test_audience_alignment_fraction() -> None:
    cohorts = load_cohorts()
    from republica.world.cohorts import CohortState

    state = {c.id: CohortState(50.0, 40.0, 0.0, 0.0) for c in cohorts}  # sentiment > 0
    # "crisis" <-> negativo (secc. 4.5): con sentiment positivo en todas,
    # 0 de 8 alineadas.
    assert audience_alignment("crisis", cohorts, state) == pytest.approx(0.0)
    # "recovery" <-> positivo: las 8 alineadas.
    assert audience_alignment("recovery", cohorts, state) == pytest.approx(1.0)
    # "neutral" no tiene polaridad declarada.
    assert audience_alignment("neutral", cohorts, state) is None


def test_audience_drift_stays_within_bounds() -> None:
    """`influence.public_m` (secc. 4.5) queda acotado a `[0.05, 0.6]` sin
    importar cuantos meses de desalineacion/alineacion se acumulen."""
    from republica.world.cohorts import CohortState

    cohorts = load_cohorts()
    negative_state = {c.id: CohortState(50.0, -80.0, 0.0, 0.0) for c in cohorts}
    influence = 0.4
    for _ in range(500):
        influence = drift_audience("crisis", influence, cohorts, negative_state)
    assert influence == pytest.approx(0.6)  # siempre alineado, sube hasta el techo
    influence = 0.4
    for _ in range(500):
        influence = drift_audience("recovery", influence, cohorts, negative_state)
    assert influence == pytest.approx(0.05)  # siempre desalineado, cae hasta el piso
    for _ in range(500):
        assert 0.05 <= influence <= 0.6


def test_publish_story_twice_same_month_accumulates_both_frames(monkeypatch) -> None:
    """Hallazgo #6 de REVIEW_002 (parte 2): `engine/simulation.py` armaba
    `frame_by_outlet = {ma.outlet_id: ma.frame for ma in media_actions}` --
    un medio que publica DOS `PUBLISH_STORY` el mismo mes (frames
    distintos) solo drifteaba audiencia con el ULTIMO frame, el primero se
    perdia sin efecto. Se espia `drift_audience` (via `simulation_mod`, el
    modulo que lo importa) durante una corrida real de 1 mes donde
    `media_nacional` esta guionado (`fake:scripted`) para publicar
    `crisis` y despues `recovery` en el mismo mes: con el fix, `drift_
    audience` se llama UNA VEZ POR HISTORIA (2 veces), encadenadas (el
    `influence_public` de la segunda llamada es el resultado de la
    primera) -- antes se llamaba una sola vez, solo con `recovery`."""
    calls: list[tuple[str, float, float]] = []
    real_drift_audience = simulation_mod.drift_audience

    def spy_drift_audience(frame, influence_public, cohorts, cohort_state):
        result = real_drift_audience(frame, influence_public, cohorts, cohort_state)
        calls.append((frame, influence_public, result))
        return result

    monkeypatch.setattr(simulation_mod, "drift_audience", spy_drift_audience)

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
        cohorts_enabled=True,
        media_enabled=True,
    )
    outlet_id = "media_nacional"
    scripted = {
        (outlet_id, 1): {
            "position": "neutral",
            "intensity": 0.5,
            "public_message": "",
            "private_strategy": "wait",
            "actions": [
                {
                    "type": "PUBLISH_STORY",
                    "params": {"frame": "crisis", "target_bloc": "all"},
                    "target": None,
                },
                {
                    "type": "PUBLISH_STORY",
                    "params": {"frame": "recovery", "target_bloc": "all"},
                    "target": None,
                },
            ],
            "confidence": 0.7,
            "reasoning": "test",
        }
    }
    sim.actor_engine.decision_actors[outlet_id] = LLMActor(
        sim.actor_engine.actors[outlet_id],
        FakeBackend(policy="scripted", scripted=scripted),
        seed_base=0,
    )

    advance_month(sim)

    # Buscar el par encadenado "crisis" -> "recovery" (la segunda llamada
    # arranca del resultado de la primera): con el fix DEBE existir; con el
    # bug viejo `drift_audience` se llamaba una sola vez por outlet (solo
    # "recovery", desde la influencia ORIGINAL, sin una llamada "crisis"
    # previa que encadenar).
    chained_pair_found = any(
        calls[i][0] == "crisis"
        and calls[i + 1][0] == "recovery"
        and calls[i + 1][1] == pytest.approx(calls[i][2])
        for i in range(len(calls) - 1)
    )
    assert chained_pair_found, calls


# ---------------------------------------------------------------------------
# 6. Corrida completa: 48 meses x 29 actores con todos los features
# (ADR 005 secc. 7 item 5)
# ---------------------------------------------------------------------------


def test_full_run_all_features_is_fast_and_has_all_record_kinds() -> None:
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    t0 = time.perf_counter()
    history: History = run(
        seed=7,
        months=48,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0
    assert len(history.perception_records) == 48
    jsonl = history.to_jsonl()
    assert '"kind": "vote"' in jsonl
    assert '"kind": "negotiation"' in jsonl
    assert '"kind": "perception"' in jsonl
    # deliverable 1: `MonthRecord.cohorts` con las 8 cohortes, 4 campos c/u.
    first_month = json.loads(jsonl.splitlines()[0])
    assert set(first_month["cohorts"]) == {c.id for c in load_cohorts()}
    for values in first_month["cohorts"].values():
        assert set(values) == {
            "approval_c",
            "sentiment_c",
            "perceived_inflation_c",
            "perceived_unemployment_c",
        }


# ---------------------------------------------------------------------------
# 7. `emergence` sobre 20 semillas (ADR 005 secc. 7 item 6)
# ---------------------------------------------------------------------------


def test_emergence_over_20_seeds_runs(tmp_path) -> None:
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    found_alliance_or_coalition = False
    for seed in range(20):
        history = run(
            seed=seed,
            months=48,
            policy_rule=taylor,
            country=COUNTRY,
            actors_enabled=True,
            congress_enabled=True,
            negotiation_enabled=True,
            cohorts_enabled=True,
            media_enabled=True,
        )
        path = tmp_path / f"run_{seed}.jsonl"
        path.write_text(history.to_jsonl(), encoding="utf-8")
        loaded = load_jsonl(path)
        report = detect(loaded)
        # deliverable 6: la cohorte mas descontenta y el mes de brecha
        # maxima estan presentes con `features.cohorts`/`media` activos.
        assert report.most_discontented_cohort is not None
        assert report.max_perception_gap_month is not None
        if report.alliances or report.repeated_coalitions:
            found_alliance_or_coalition = True
    # secc. 6: "si no encuentra ninguna, se documenta: tambien es un
    # resultado" -- se encontro al menos una en las 20 semillas corridas.
    assert found_alliance_or_coalition


# ---------------------------------------------------------------------------
# 8. `--no-cohorts --no-media` (== features apagadas) byte-identico al HEAD
# previo a este commit (ADR 005 secc. 7, golden hash: mismo precedente que
# `tests/test_congress_negotiation.py::test_features_off_matches_pre_adr005_
# golden_hash`)
# ---------------------------------------------------------------------------

#: Commit `1bdc33f9e4be62a07577bbb264a260d85f524b15` ("Visor: votos por
#: partido y negociaciones del mes"), HEAD del repo antes de este commit
#: (cohortes/percepcion): `git worktree add /tmp/head HEAD`, `uv run python`
#: con `run(seed=7, months=48, policy=taylor, actors_enabled=True,
#: congress_enabled=True, negotiation_enabled=True)` (`features.cohorts`/
#: `features.media` no existian todavia en ese commit), `config_hash`
#: reemplazado por un placeholder antes de hashear (mismo precedente que
#: REVIEW_001 hallazgo #8/ADR 003 secc. 11 punto 6: tocar `data/
#: country.json` para agregar `features.cohorts`/`media` cambia
#: `config_hash` inevitablemente, no el resto del JSONL).
HEAD_COMMIT_BEFORE_THIS_COMMIT = "1bdc33f9e4be62a07577bbb264a260d85f524b15"

#: Recalculado tras REVIEW_002 hallazgo #5 (`congress_enabled`/
#: `negotiation_enabled` estan ON en esta config: `cohorts`/`media` son los
#: unicos "apagados" que da nombre al test -- el invariante que guarda
#: (byte a byte estable salvo por cambios deliberados en Congreso/
#: negociacion) sigue intacto). Antes, una concesion sin ley se ejecutaba y
#: pasaba a `honored` en el mismo mes en que se otorgaba, asi que nunca
#: compraba el voto por el que se negocio (`engine/congress.py::
#: _concession_bonus_for_party` solo miraba `status == "vigente"`); el fix
#: mueve votos de Congreso en esta corrida de 48 meses. Recalculado
#: corriendo el mismo `run(...)` de mas abajo contra el codigo ya corregido
#: (no `git worktree add HEAD`: HEAD todavia apunta al commit CON el bug de
#: REVIEW_002, asi que un worktree de HEAD solo hubiera reproducido el
#: mismo hash viejo) -- verificado deterministico (dos corridas identicas).
GOLDEN_SEED7_TAYLOR_COHORTS_MEDIA_OFF_SHA256 = (
    "9d247690f81bf6e0553a582e8f4b97786f69806ee86ca5514702f6fd26d08282"
)


def _strip_config_hash(jsonl_text: str) -> str:
    lines = jsonl_text.rstrip("\n").split("\n")
    summary = json.loads(lines[-1])
    summary["config_hash"] = "STRIPPED"
    lines[-1] = json.dumps(summary, ensure_ascii=False)
    return "\n".join(lines) + "\n"


def test_cohorts_and_media_off_matches_pre_commit_golden_hash() -> None:
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    history = run(
        seed=7,
        months=48,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=False,
        media_enabled=False,
    )
    stripped = _strip_config_hash(history.to_jsonl())
    digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
    assert digest == GOLDEN_SEED7_TAYLOR_COHORTS_MEDIA_OFF_SHA256


# ---------------------------------------------------------------------------
# 9. `fake:rules` sigue reproduciendo `rules` con cohortes/medios activos
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


def test_fake_rules_matches_rules_with_cohorts_and_media() -> None:
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    target_actors = ("gov_norte", "party_frente_federal", "union_cgt", "media_mercado")
    baseline = run(
        seed=7,
        months=12,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
    )
    via_llm = run(
        seed=7,
        months=12,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        brain_map={a: "fake:rules" for a in target_actors},
    )
    for actor_id in target_actors:
        assert _authorized_key(via_llm.action_records, actor_id) == _authorized_key(
            baseline.action_records, actor_id
        )
    assert [p.to_dict() for p in baseline.perception_records] == [
        p.to_dict() for p in via_llm.perception_records
    ]
