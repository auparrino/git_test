"""Tests de A2 (ADR 011 secc. 9, items 1-8; el item 9 es de A3).

Cubre el paquete de pais Argentina: el loader (`world/countries.py`), el modo
de regimen (`world/regime.py`), el bloque bimonetario (`world/bimonetary.py`),
el modo anual (`world/annual.py`) y el golden hash de Aurora sin `--country`.
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest

from republica.engine.policy import PassivePolicy
from republica.engine.simulation import run
from republica.world.annual import load_annual_regime, run_annual
from republica.world.bimonetary import BimonetaryCoefficients, ExternalState, step_bimonetary
from republica.world.config import load_country
from republica.world.countries import (
    CountryPackError,
    country_pack_dir,
    historical_shocks_calendar,
    load_country_pack,
    load_country_pack_annual,
    term_length_months_for,
)
from republica.world.regime import (
    RegimeState,
    build_regime_calendar,
    congress_active,
    elections_allowed,
    step_regime,
)
from republica.world.state import WorldState

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = REPO_ROOT / "data" / "countries" / "argentina"


# ---------------------------------------------------------------------------
# 1. `run --country argentina --start 1983-12 --months 12` corre; sin
#    `--country`, JSONL de Aurora byte a byte igual (golden).
# ---------------------------------------------------------------------------


def test_run_with_country_argentina_produces_a_history() -> None:
    pack = load_country_pack("argentina", "1983-12", 12)
    history = run(seed=7, months=12, country=pack.country, actors_enabled=True)
    # Puede terminar antes de los 12 meses (`collapse`/`hyperinflation`, ver
    # `world/events.py::check_termination`): es un resultado valido, no un
    # error -- lo que se prueba es que la corrida arranca y produce
    # registros con el estado inicial de la fecha pedida.
    assert 1 <= len(history.records) <= 12
    assert history.records[0].date == "1983-12"
    assert history.outcome in ("survived", "collapse", "hyperinflation")


def test_cli_run_with_country_argentina(tmp_path: Path) -> None:
    out = tmp_path / "arg.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "republica.cli",
            "run",
            "--seed",
            "1",
            "--out",
            str(out),
            "--country",
            "argentina",
            "--start",
            "1983-12",
            "--months",
            "6",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["date"] == "1983-12"


#: Golden hash de Aurora (SIN `--country`), calculado en un
#: `git worktree add /tmp/head HEAD` limpio (commit `244f1792e0c99d9af8564f2
#: 64e407d63dc1c6a61`, HEAD antes de A2) con
#: `run(seed=7, months=48, country=load_country(), actors_enabled=True,
#: congress_enabled=True, negotiation_enabled=True, cohorts_enabled=True,
#: media_enabled=True, memory_enabled=True, elections_enabled=True)`,
#: `config_hash` reemplazado por un placeholder antes de hashear (mismo
#: precedente que `tests/test_cohorts_perception.py`). Todos los parametros
#: nuevos de A2 (`regime_calendar`/`bimonetary_coefficients`/
#: `historical_exogenous`) quedan en su default `None`: este test verifica
#: que agregarlos a `run()` no cambio un solo byte del camino existente.
GOLDEN_SEED7_NO_COUNTRY_SHA256 = "b4bbfe09e6bb0a6b0b7e66306e0dc99b664592411a613d62947581b342e5013a"


def _strip_config_hash(jsonl_text: str) -> str:
    lines = jsonl_text.rstrip("\n").split("\n")
    summary = json.loads(lines[-1])
    summary["config_hash"] = "STRIPPED"
    lines[-1] = json.dumps(summary, ensure_ascii=False)
    return "\n".join(lines) + "\n"


def test_aurora_without_country_matches_golden_hash_pre_a2() -> None:
    country = load_country()
    history = run(
        seed=7,
        months=48,
        country=country,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
    )
    stripped = _strip_config_hash(history.to_jsonl())
    digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
    assert digest == GOLDEN_SEED7_NO_COUNTRY_SHA256


# ---------------------------------------------------------------------------
# 2. Loader: estado inicial por fecha con source/proxy/assumed obligatorio
#    por variable; fecha sin estado -> error claro.
# ---------------------------------------------------------------------------


def test_loader_rejects_unsupported_start_date_with_clear_error() -> None:
    with pytest.raises(CountryPackError, match="1975-01"):
        load_country_pack("argentina", "1975-01", 12)


def test_loader_rejects_unknown_country_with_clear_error() -> None:
    with pytest.raises(CountryPackError, match="no_existe"):
        load_country_pack("no_existe", "1983-12", 12)


@pytest.mark.parametrize(
    "date",
    ["1983-12", "1988-06", "1991-04", "1998-01", "2003-06", "2016-01", "2019-12", "2023-12"],
)
def test_every_supported_date_has_full_provenance(date: str) -> None:
    raw = json.loads((PACK_DIR / "country.json").read_text(encoding="utf-8"))
    entry = raw["initial_states"][date]
    variables = set(WorldState.model_fields)
    assert variables <= set(entry)
    for var, prov in entry.items():
        assert prov.get("assumed") or "source" in prov or "proxy" in prov, (date, var)
        assert "value" in prov, (date, var)


def test_loader_builds_a_valid_world_state_for_every_supported_date() -> None:
    dates = ["1983-12", "1988-06", "1991-04", "1998-01", "2003-06", "2016-01", "2019-12", "2023-12"]
    for date in dates:
        pack = load_country_pack("argentina", date, 12)
        assert isinstance(pack.country.initial_state, WorldState)


# ---------------------------------------------------------------------------
# 3. Regimen: evento `coup` en el calendario suspende elecciones y disuelve
#    Congreso; `transition` reinstala; `regime_mode` mensual en el JSONL.
# ---------------------------------------------------------------------------


def test_forced_coup_suspends_congress_and_elections_then_transition_reinstates() -> None:
    events_csv = PACK_DIR / "politics" / "events.csv"
    # 1976-01 -> el golpe del 24-mar-1976 cae en el mes 3 de esta corrida.
    calendar = build_regime_calendar(events_csv, 1976, 1, 40, mode="auto")
    assert 3 in calendar.forced_coup_months

    country = load_country()
    history = run(
        seed=3,
        months=40,
        country=country,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        elections_enabled=True,
        regime_calendar=calendar,
    )
    modes = [r.regime_mode for r in history.records]
    assert modes[0] == "democracy"
    assert modes[2] == "coup"
    assert modes[3] == "dictatorship"
    assert "transition" in modes or "democracy" in modes[4:]

    # Congreso disuelto: ningun `VoteRecord` cae en un mes de coup/dictatorship.
    dictatorship_months = {
        r.month_index for r in history.records if r.regime_mode in ("coup", "dictatorship")
    }
    assert dictatorship_months, "el escenario no llego a coup/dictatorship"
    vote_months = {v.month for v in history.vote_records}
    assert not (vote_months & dictatorship_months)

    # Elecciones suspendidas: ninguna cae en coup/dictatorship (is_election_month
    # de por si no coincidiria en esta ventana corta, pero el flag es lo que
    # se esta probando: `elections_enabled` queda False esos meses).
    election_months = {e.month for e in history.election_records}
    assert not (election_months & dictatorship_months)


def test_regime_mode_recorded_in_every_month_record_when_enabled() -> None:
    events_csv = PACK_DIR / "politics" / "events.csv"
    calendar = build_regime_calendar(events_csv, 1983, 12, 12, mode="auto")
    country = load_country()
    history = run(seed=1, months=12, country=country, regime_calendar=calendar)
    assert all(r.regime_mode for r in history.records)
    valid_modes = ("democracy", "coup", "dictatorship", "transition")
    assert all(r.regime_mode in valid_modes for r in history.records)


def test_regime_mode_absent_from_jsonl_when_feature_off() -> None:
    country = load_country()
    history = run(seed=1, months=6, country=country)
    for line in history.to_jsonl().splitlines()[:6]:
        d = json.loads(line)
        assert "regime_mode" not in d
        assert "external" not in d


def test_elections_allowed_and_congress_active_by_mode() -> None:
    assert elections_allowed("democracy") and congress_active("democracy")
    assert elections_allowed("transition") and congress_active("transition")
    assert not elections_allowed("coup") and not congress_active("coup")
    assert not elections_allowed("dictatorship") and not congress_active("dictatorship")


# ---------------------------------------------------------------------------
# 4. Golpe endogeno: con `coup_propensity > 0` y estabilidad < 20 sostenida,
#    ocurre en >= 50% de 20 semillas; con propension 0, nunca.
# ---------------------------------------------------------------------------


def _unstable_state() -> WorldState:
    base = load_country().initial_state
    return base.model_copy(update={"political_stability": 10.0, "institutional_confidence": 10.0})


def test_endogenous_coup_never_fires_with_zero_propensity() -> None:
    state = _unstable_state()
    for seed in range(20):
        rng = random.Random(seed)
        rs = RegimeState()
        for _month in range(24):
            step_regime(rs, state, rng, forced_coup=False, coup_propensity=0.0)
        assert rs.mode == "democracy"


def test_endogenous_coup_fires_in_at_least_half_of_20_seeds_with_high_propensity() -> None:
    state = _unstable_state()
    coups = 0
    for seed in range(20):
        rng = random.Random(seed)
        rs = RegimeState()
        happened = False
        for _month in range(24):
            result = step_regime(rs, state, rng, forced_coup=False, coup_propensity=0.15)
            if result.event == "coup":
                happened = True
                break
        coups += int(happened)
    assert coups >= 10, f"solo {coups}/20 semillas tuvieron golpe endogeno"


def test_coup_propensity_by_decade_from_real_calendar() -> None:
    from republica.world.regime import coup_propensity_by_decade

    propensities = coup_propensity_by_decade(PACK_DIR / "politics" / "events.csv")
    assert propensities.get(1970, 0.0) > 0.0
    assert all(0.0 <= p <= 1.0 for p in propensities.values())


# ---------------------------------------------------------------------------
# 5. `sovereign_default` forzado cierra el credito 24 meses y revalua la
#    deuda; endogeno se dispara con `default_risk` alto sin `imf_program`.
# ---------------------------------------------------------------------------


#: `sovereign_default`/`currency_run`/`war`/`imf_program` (ADR 011 secc. 4)
#: solo estan en el catalogo del paquete Argentina (`data/countries/
#: argentina/shocks.json`), no en el de Aurora.
def _aurora_with_argentina_shocks():
    """Estado inicial ESTABLE de Aurora (no el de 1983-12, que ya arranca
    con inflacion de dos digitos mensual y entra en hiperinflacion en pocos
    meses con o sin `sovereign_default` encima) + el catalogo de shocks de
    Argentina: aisla el efecto del shock de la fragilidad del estado
    inicial, para probar los 24 meses completos de duracion."""
    argentina_shocks = json.loads((PACK_DIR / "shocks.json").read_text(encoding="utf-8"))
    return load_country().model_copy(update={"shocks": argentina_shocks})


def test_sovereign_default_forced_stays_active_24_months() -> None:
    country = _aurora_with_argentina_shocks()
    history = run(seed=5, months=30, country=country, forced_shocks={1: ["sovereign_default"]})
    active_by_month = {r.month_index: r.shocks_active for r in history.records}
    new_by_month = {r.month_index: r.shocks_new for r in history.records}
    # `duration=24`: activo (en `shocks_active`) los meses 1-23; en el mes 24
    # dispara su ULTIMO efecto y se desactiva en el mismo `apply_month` (
    # mismo comportamiento de siempre para cualquier shock de duracion N,
    # ver `world/events.py::ShockCatalog.apply_month` y el comentario sobre
    # shocks de 1 mes en `engine/simulation.py::advance_month`): ya no
    # aparece en `shocks_active` de ESE mes, pero se puede verificar que
    # disparo con `shocks_new` (mes 1, cuando se activa).
    assert new_by_month[1] == ["sovereign_default"]
    for m in range(1, 24):
        assert "sovereign_default" in active_by_month[m], m
    # P2 (A3): con el credito cerrado (k_k=0) 24 meses, la corrida puede
    # terminar antes de los 30 meses pedidos (`collapse` por reservas -- un
    # default deberia ser mas duro que la aproximacion aditiva de A2, ver
    # Notas de implementacion): se verifica "no activo" solo en los meses
    # que sí llegaron a tener registro.
    for m in range(24, 31):
        if m in active_by_month:
            assert "sovereign_default" not in active_by_month[m], m


def test_sovereign_default_revalues_public_debt_via_devaluation() -> None:
    country = _aurora_with_argentina_shocks()
    baseline = run(seed=5, months=3, country=country)
    shocked = run(seed=5, months=3, country=country, forced_shocks={1: ["sovereign_default"]})
    assert shocked.records[0].state["public_debt"] > baseline.records[0].state["public_debt"]


def test_endogenous_sovereign_default_fires_without_imf_program() -> None:
    country = _aurora_with_argentina_shocks()
    coeffs = BimonetaryCoefficients(default_risk_threshold=0.0, default_risk_init=0.9)
    history = run(seed=2, months=6, country=country, bimonetary_coefficients=coeffs)
    triggered = any("sovereign_default" in r.shocks_new for r in history.records)
    assert triggered


# ---------------------------------------------------------------------------
# P1 (A3): solo golpes EXITOSOS disparan un `coup` de calendario; los
# fallidos ("FALLIDO"/"fallido"/"failed" en title/notes) son un shock de 1
# mes (stability -5, institutional_confidence -3), no un cambio de regimen.
# ---------------------------------------------------------------------------


def test_failed_coup_excluded_from_calendar_coup_months() -> None:
    from republica.world.regime import load_coup_dates, load_failed_coup_dates

    events_csv = PACK_DIR / "politics" / "events.csv"
    successful = load_coup_dates(events_csv)
    failed = load_failed_coup_dates(events_csv)
    # Los 3 carapintadas de 1987-1990 durante Alfonsin, todos "(fallido)" en
    # el title y "FALLIDO." en las notes.
    assert (1987, 4) in failed
    assert (1988, 1) in failed
    assert (1988, 12) in failed
    assert (1990, 12) in failed
    assert (1987, 4) not in successful
    assert (1988, 12) not in successful
    # El golpe exitoso de 1976 si sigue en `successful`.
    assert (1976, 3) in successful
    assert (1976, 3) not in failed


def test_start_1988_06_no_longer_enters_coup_in_1988_12() -> None:
    """DoD de P1: `--start 1988-06` ya no entra en `coup` en 1988-12 (el
    alzamiento de Villa Martelli, fallido, era el bug de A2)."""
    events_csv = PACK_DIR / "politics" / "events.csv"
    calendar = build_regime_calendar(events_csv, 1988, 6, 12, mode="auto")
    # 1988-12 es el mes 7 de una corrida que arranca en 1988-06.
    assert 7 not in calendar.forced_coup_months


def test_failed_coup_becomes_a_one_month_shock_in_forced_shocks() -> None:
    from republica.world.countries import failed_coup_shock_months

    pack_dir = PACK_DIR
    months = failed_coup_shock_months(pack_dir, 1988, 6, 12)
    assert months[7] == "failed_coup"


def test_failed_coup_shock_moves_stability_and_confidence_down() -> None:
    country = _aurora_with_argentina_shocks()
    baseline = run(seed=9, months=2, country=country)
    shocked = run(seed=9, months=2, country=country, forced_shocks={1: ["failed_coup"]})
    assert (
        shocked.records[0].state["political_stability"]
        < baseline.records[0].state["political_stability"]
    )
    assert (
        shocked.records[0].state["institutional_confidence"]
        < baseline.records[0].state["institutional_confidence"]
    )
    # Es un shock de 1 mes: no queda activo el mes 2.
    assert "failed_coup" not in shocked.records[1].shocks_active


def test_load_country_pack_merges_failed_coup_shocks_into_historical_forced() -> None:
    pack = load_country_pack("argentina", "1988-06", 12)
    assert pack.historical_forced_shocks.get(7) == ["failed_coup"]


# ---------------------------------------------------------------------------
# P2 (A3): efectos proporcionales de `sovereign_default` (k_k=0,
# debt_interest_rate*0.5 mientras esta activo) e `imf_program`
# (primary_spending -1.5 mientras esta activo), sin tocar la firma de
# `step_economy`.
# ---------------------------------------------------------------------------


def test_apply_historical_shock_effects_is_identity_without_those_shocks() -> None:
    from republica.world.economy import apply_historical_shock_effects

    country = load_country()
    coeff, policy = apply_historical_shock_effects(
        country.coefficients, country.default_policy, frozenset({"drought", "general_strike"})
    )
    assert coeff is country.coefficients
    assert policy is country.default_policy


def test_apply_historical_shock_effects_sovereign_default_zeroes_k_k_and_halves_interest() -> None:
    from republica.world.economy import apply_historical_shock_effects

    country = load_country()
    coeff, policy = apply_historical_shock_effects(
        country.coefficients, country.default_policy, frozenset({"sovereign_default"})
    )
    assert coeff.k_k == 0.0
    assert coeff.debt_interest_rate == pytest.approx(country.coefficients.debt_interest_rate * 0.5)
    assert policy is country.default_policy


def test_apply_historical_shock_effects_imf_program_cuts_primary_spending() -> None:
    from republica.world.economy import apply_historical_shock_effects

    country = load_country()
    coeff, policy = apply_historical_shock_effects(
        country.coefficients, country.default_policy, frozenset({"imf_program"})
    )
    assert coeff is country.coefficients
    assert policy.primary_spending == pytest.approx(country.default_policy.primary_spending - 1.5)


def test_sovereign_default_halves_interest_cost_relative_to_baseline() -> None:
    # A nivel de `step_economy` (aislado de la revaluacion cambiaria de la
    # deuda y de los efectos aditivos del mes 1 del shock, que dominan una
    # corrida completa via `run()`): mismo estado/exogenas/politica, el
    # unico cambio es el `coeff` ajustado por `apply_historical_shock_effects`.
    from republica.world.economy import apply_historical_shock_effects, step_economy

    country = load_country()
    state = country.initial_state
    policy = country.default_policy
    coeff, _ = apply_historical_shock_effects(
        country.coefficients, policy, frozenset({"sovereign_default"})
    )
    from republica.world.events import ShockAggregate

    agg = ShockAggregate()
    _, aux_baseline = step_economy(
        state,
        country.exogenous,
        country.exogenous,
        policy,
        agg,
        country.structure,
        country.coefficients,
    )
    _, aux_shocked = step_economy(
        state, country.exogenous, country.exogenous, policy, agg, country.structure, coeff
    )
    assert aux_shocked.interest_cost == pytest.approx(aux_baseline.interest_cost * 0.5)


def test_imf_program_reduces_primary_spending_effect_only_while_active() -> None:
    country = _aurora_with_argentina_shocks()
    baseline = run(seed=5, months=26, country=country)
    shocked = run(seed=5, months=26, country=country, forced_shocks={1: ["imf_program"]})
    # Mientras el programa esta activo (meses 1-24), el deficit fiscal del
    # shocked deberia estar mas aliviado por el recorte de gasto primario
    # que en la corrida base (con todo lo demas igual salvo los efectos
    # aditivos del propio shock): public_debt crece menos.
    assert shocked.records[5].state["public_debt"] < baseline.records[5].state["public_debt"]


# ---------------------------------------------------------------------------
# 6. Bimonetario: `dollar_demand` sube con inflacion y baja con tasa real;
#    `fx_gap > 0` solo en `control`.
# ---------------------------------------------------------------------------


def test_dollar_demand_rises_with_inflation() -> None:
    coeff = BimonetaryCoefficients()
    prev = ExternalState(0.3, 0.0, 30.0, 0.05, "float")
    state_low_pi = load_country().initial_state.model_copy(update={"inflation": 2.0})
    state_high_pi = load_country().initial_state.model_copy(update={"inflation": 20.0})
    low = step_bimonetary(prev, state_low_pi, real_rate=5.0, coeff=coeff)
    high = step_bimonetary(prev, state_high_pi, real_rate=5.0, coeff=coeff)
    assert high.dollar_demand > low.dollar_demand


def test_dollar_demand_falls_with_positive_real_rate() -> None:
    coeff = BimonetaryCoefficients()
    prev = ExternalState(0.5, 0.0, 30.0, 0.05, "float")
    state = load_country().initial_state.model_copy(update={"inflation": 2.0})
    low_real_rate = step_bimonetary(prev, state, real_rate=0.0, coeff=coeff)
    high_real_rate = step_bimonetary(prev, state, real_rate=20.0, coeff=coeff)
    assert high_real_rate.dollar_demand <= low_real_rate.dollar_demand


def test_fx_gap_only_positive_under_control() -> None:
    coeff = BimonetaryCoefficients()
    state = load_country().initial_state
    prev_float = ExternalState(0.6, 0.0, 30.0, 0.05, "float")
    prev_control = ExternalState(0.6, 0.0, 30.0, 0.05, "control")
    out_float = step_bimonetary(prev_float, state, real_rate=5.0, coeff=coeff)
    out_control = step_bimonetary(prev_control, state, real_rate=5.0, coeff=coeff)
    assert out_float.fx_gap == 0.0
    assert out_control.fx_gap > 0.0


def test_external_block_appears_in_jsonl_when_bimonetary_enabled() -> None:
    country = load_country()
    coeffs = BimonetaryCoefficients()
    history = run(seed=1, months=3, country=country, bimonetary_coefficients=coeffs)
    for line in history.to_jsonl().splitlines()[:3]:
        d = json.loads(line)
        assert "external" in d
        assert set(d["external"]) == {
            "dollar_demand",
            "fx_gap",
            "external_debt_usd",
            "default_risk",
            "fx_regime",
        }


# ---------------------------------------------------------------------------
# 7. Mandato de 6 anos en 1989 y de 4 en 1999 segun constitutions.csv.
# ---------------------------------------------------------------------------


def test_term_length_six_years_before_1994_reform() -> None:
    months, reelection = term_length_months_for(PACK_DIR / "constitutions.csv", "1989-01")
    assert months == 72
    assert reelection is False


def test_term_length_four_years_after_1994_reform() -> None:
    months, reelection = term_length_months_for(PACK_DIR / "constitutions.csv", "1999-01")
    assert months == 48
    assert reelection is True


def test_term_length_resolved_for_supported_start_dates() -> None:
    pack_1983 = load_country_pack("argentina", "1983-12", 12)
    assert pack_1983.country.term_length == 72
    pack_2016 = load_country_pack("argentina", "2016-01", 12)
    assert pack_2016.country.term_length == 48


# ---------------------------------------------------------------------------
# 8. Modo anual: 1880->1930 corre en < 5s y produce 50 registros anuales con
#    `regime_mode`.
# ---------------------------------------------------------------------------


def test_annual_mode_runs_fast_and_produces_50_records_with_regime_mode() -> None:
    country = load_country_pack_annual("argentina", 1880, 50)
    regime_lookup = load_annual_regime(PACK_DIR / "politics" / "regimes.csv")
    rate_range = country.policy_ranges["interest_rate_target"]
    policy_rule = PassivePolicy(country.default_policy, country.structure.r_neutral, rate_range)
    t0 = time.perf_counter()
    history = run_annual(
        seed=1,
        years=50,
        country=country,
        policy_rule=policy_rule,
        start_year=1880,
        annual_regime=regime_lookup,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0
    assert len(history.records) == 50
    assert all(r.regime_mode for r in history.records)
    assert history.records[0].year == 1880
    assert history.records[-1].year == 1929


def test_annual_mode_covers_1930_coup_as_dictatorship() -> None:
    country = load_country_pack_annual("argentina", 1928, 6)
    regime_lookup = load_annual_regime(PACK_DIR / "politics" / "regimes.csv")
    rate_range = country.policy_ranges["interest_rate_target"]
    policy_rule = PassivePolicy(country.default_policy, country.structure.r_neutral, rate_range)
    history = run_annual(
        seed=1,
        years=6,
        country=country,
        policy_rule=policy_rule,
        start_year=1928,
        annual_regime=regime_lookup,
    )
    by_year = {r.year: r.regime_mode for r in history.records}
    assert by_year[1930] == "coup"
    assert by_year[1931] == "dictatorship"


# ---------------------------------------------------------------------------
# Calendario de shocks historicos (ADR 011 secc. 4): hyperinflation_regime
# nunca se fuerza.
# ---------------------------------------------------------------------------


def test_hyperinflation_regime_never_forced_from_shocks_calendar() -> None:
    forced = historical_shocks_calendar(PACK_DIR, 1988, 1, 36)
    all_ids = {sid for ids in forced.values() for sid in ids}
    assert "hyperinflation_regime" not in all_ids


def test_historical_shocks_calendar_maps_known_events_to_month_index() -> None:
    forced = historical_shocks_calendar(PACK_DIR, 1982, 1, 24)
    all_ids = {sid for ids in forced.values() for sid in ids}
    assert "war" in all_ids  # Malvinas, abril de 1982
    assert "sovereign_default" in all_ids  # crisis de deuda de 1982


# ---------------------------------------------------------------------------
# `republica country info` (deliverable 7).
# ---------------------------------------------------------------------------


def test_cli_country_info_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "republica.cli", "country", "info", "argentina"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "1983-12" in result.stdout
    assert "features" in result.stdout


def test_country_pack_dir_lists_available_countries_on_error() -> None:
    with pytest.raises(CountryPackError, match="argentina"):
        country_pack_dir("does_not_exist")
