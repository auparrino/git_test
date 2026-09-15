"""Tests de aceptacion de ADR 007 (Fase 7: evals, trazas, gobernanza),
seccion 7 adaptada por la tarea de implementacion (los 20 casos `author:
human` quedan reservados para el usuario -- ver `docs/ADR_007_evals_
governance.md`, Notas de implementacion): al menos 20 casos ideologicos +
12 de interes, 100 % contra `rules`; `fake:rules` reproduce `rules` (para
actores puntuales, mismo precedente que ADR 004 secc. 9 test 1);
`fake:unauthorized` produce `authority_violation > 0`; `FakeJudge` detecta
un numero inventado; gobernanza (autonomy/read/budget); trazas
(export/show); `eval compare`; cada metrica mecanica en una corrida
sintetica chica; forma del IC bootstrap; hash dorado de gobernanza default
contra HEAD `eaed2a8`."""

from __future__ import annotations

import hashlib
import json

import yaml
from typer.testing import CliRunner

from republica.actors.sheet import load_actors
from republica.ai.tracing import read_traces_jsonl
from republica.cli import app
from republica.engine.actions import Action, ActionType
from republica.engine.permissions import AuthContext, authorize, load_permissions
from republica.engine.policy import TaylorPolicy
from republica.engine.simulation import run as run_simulation
from republica.evals.cases import load_cases
from republica.evals.judge import FakeJudge, build_judge
from republica.evals.metrics import bootstrap_ci
from republica.evals.promptfoo import export_promptfoo
from republica.evals.report import compare_reports
from republica.evals.runner import run_suite
from republica.governance import ActorGovernance, Governance, GovernanceBudget, filter_perception
from republica.governance import load_governance as load_gov
from republica.world.config import load_country

runner = CliRunner()
COUNTRY = load_country()
ACTORS = load_actors()
PERMISSIONS = load_permissions()

# ---------------------------------------------------------------------------
# 1. Casos: >= 20 ideologicos + 12 de interes, 100 % contra `rules`.
# ---------------------------------------------------------------------------


def test_at_least_20_ideological_and_12_interest_cases_exist() -> None:
    ideological = load_cases("ideological")
    interest = load_cases("interest")
    assert len(ideological) >= 20
    assert len(interest) >= 12
    for case in ideological + interest:
        assert case.author == "generated"
        assert case.actor in ACTORS


def test_ideological_and_interest_cases_pass_100pct_against_rules() -> None:
    report_ideo = run_suite(suite="ideological", brain="rules", judge="fake", seed=7)
    report_int = run_suite(suite="interest", brain="rules", judge="fake", seed=7)
    ideo = report_ideo.metrics[0]
    interest = report_int.metrics[0]
    assert ideo.value == 1.0, ideo.worst_cases
    assert interest.value == 1.0, interest.worst_cases


# ---------------------------------------------------------------------------
# 2. `fake:rules` reproduce `rules` para actores puntuales (mismo
#    precedente que ADR 004 secc. 9 test 1: `authorize`/`denied_reason`
#    identicos mes a mes).
# ---------------------------------------------------------------------------


def _authorized_key(records, actor_id: str) -> list:
    return [
        (r.month, r.type, r.authorized, r.denied_reason) for r in records if r.actor == actor_id
    ]


def test_fake_rules_matches_rules_for_target_actors() -> None:
    target_actors = ("gov_norte", "union_cgt")
    baseline = run_simulation(seed=7, months=12, actors_enabled=True)
    via_llm = run_simulation(
        seed=7,
        months=12,
        actors_enabled=True,
        brain_map={actor_id: "fake:rules" for actor_id in target_actors},
    )
    for actor_id in target_actors:
        assert _authorized_key(via_llm.action_records, actor_id) == _authorized_key(
            baseline.action_records, actor_id
        )


# ---------------------------------------------------------------------------
# 3. `FakeBackend("unauthorized")` -> `authority_violation > 0`.
# ---------------------------------------------------------------------------


def test_fake_unauthorized_shows_authority_violation_in_report() -> None:
    report = run_suite(suite="authority_violation", brain="fake:unauthorized", judge="fake", seed=7)
    metric = report.metrics[0]
    assert metric.value is not None
    assert metric.value > 0.0
    assert metric.n > 0


# ---------------------------------------------------------------------------
# 4. `FakeJudge` detecta una afirmacion numerica inventada.
# ---------------------------------------------------------------------------


def test_fake_judge_detects_a_fabricated_number() -> None:
    judge = FakeJudge()
    perception_numbers = [2.1, 8.0, 48.0]
    text = "La inflacion esta en 2.1 pero el desempleo se disparo a 55.5 puntos."
    fact_check = judge.fact_check(perception_numbers, text)
    verdicts = {c.text: c.verdict for c in fact_check.claims}
    assert verdicts["2.1"] == "supported"
    assert verdicts["55.5"] == "unsupported"
    assert fact_check.unsupported_rate == 0.5


def test_build_judge_rejects_same_model_as_actor() -> None:
    import pytest

    with pytest.raises(ValueError, match="MISMO modelo"):
        build_judge("llm:ollama:qwen3:8b", actor_brain="llm:ollama:qwen3:8b")
    # Distinto modelo: no levanta (no construye un backend real -- offline).
    build_judge("fake", actor_brain="llm:ollama:qwen3:8b")


# ---------------------------------------------------------------------------
# 5. Gobernanza: autonomy 2 deniega `SET_RATE` (reason governance:autonomy),
#    autonomy 4 lo autoriza; `read` filtra una clave del prompt.
# ---------------------------------------------------------------------------


def test_central_bank_set_rate_denied_at_autonomy_2_allowed_at_4() -> None:
    cb = ACTORS["central_bank"]
    parties_by_id = {p.id: p for p in COUNTRY.parties}
    action = Action(
        type=ActionType.SET_RATE, actor_id="central_bank", params={"delta_pp": 1.0}, reason="test"
    )

    gov2 = load_gov()  # default de data/governance.yaml: central_bank.autonomy = 2
    assert gov2.for_actor("central_bank").autonomy == 2
    ctx2 = AuthContext(
        state=COUNTRY.initial_state,
        month=1,
        parties_by_id=parties_by_id,
        governance=gov2,
        permissions=PERMISSIONS,
    )
    denied = authorize(cb, action, ctx2)
    assert denied.__class__.__name__ == "Denied"
    assert denied.reason.startswith("governance:autonomy")

    gov4 = load_gov(overrides={"central_bank.autonomy": "4"})
    assert gov4.for_actor("central_bank").autonomy == 4
    ctx4 = AuthContext(
        state=COUNTRY.initial_state,
        month=1,
        parties_by_id=parties_by_id,
        governance=gov4,
        permissions=PERMISSIONS,
    )
    allowed = authorize(cb, action, ctx4)
    assert allowed.__class__.__name__ == "Allowed"


def test_read_filter_removes_a_key_from_the_prompt() -> None:
    from republica.ai.prompts import render_user
    from republica.engine.perception import Perception

    cb = ACTORS["central_bank"]
    perception = Perception(
        month=1,
        date="2030-01",
        months_to_election=30,
        public_indicators={"inflation": 5.0},
        private_indicators={"reserves_exact": 12345.0},
        proposal=None,
        active_shocks=[],
        recent_events=[],
        relationships={},
        memories=[],
        goals=[],
    )
    allowed_types = sorted(PERMISSIONS[cb.role], key=lambda t: t.value)

    gov_full = ActorGovernance(
        actor_id="central_bank", read=("economic_indicators", "monetary_history")
    )
    filtered_full = filter_perception(cb, perception, gov_full)
    assert "reserves_exact" in filtered_full.private_indicators
    assert "reserves_exact" in render_user(filtered_full, allowed_types)

    gov_restricted = ActorGovernance(actor_id="central_bank", read=("economic_indicators",))
    filtered = filter_perception(cb, perception, gov_restricted)
    assert "reserves_exact" not in filtered.private_indicators
    prompt = render_user(filtered, allowed_types)
    assert "reserves_exact" not in prompt


def test_governance_budget_cuts_the_third_action() -> None:
    actor = ACTORS["biz_finance"]
    parties_by_id = {p.id: p for p in COUNTRY.parties}
    all_types = tuple(t.value for t in ActionType)
    gov = Governance(
        actors={
            "biz_finance": ActorGovernance(
                actor_id="biz_finance",
                write=all_types,
                execute=all_types,
                budget=GovernanceBudget(actions_per_turn=2),
            )
        }
    )
    action = Action(
        type=ActionType.PUBLIC_STATEMENT,
        actor_id="biz_finance",
        params={"stance": "support", "intensity": 0.5},
        reason="test",
    )
    # 1a y 2a accion: autorizadas (budget de gobernanza = 2).
    ctx0 = AuthContext(
        state=COUNTRY.initial_state,
        month=1,
        parties_by_id=parties_by_id,
        governance=gov,
        permissions=PERMISSIONS,
        action_counts={"biz_finance": 0},
    )
    assert authorize(actor, action, ctx0).__class__.__name__ == "Allowed"
    ctx1 = AuthContext(
        state=COUNTRY.initial_state,
        month=1,
        parties_by_id=parties_by_id,
        governance=gov,
        permissions=PERMISSIONS,
        action_counts={"biz_finance": 1},
    )
    assert authorize(actor, action, ctx1).__class__.__name__ == "Allowed"
    # 3a accion: el generico (ACTION_BUDGET_PER_TURN=3) la dejaria pasar,
    # pero la gobernanza (budget=2) la corta antes.
    ctx2 = AuthContext(
        state=COUNTRY.initial_state,
        month=1,
        parties_by_id=parties_by_id,
        governance=gov,
        permissions=PERMISSIONS,
        action_counts={"biz_finance": 2},
    )
    denied = authorize(actor, action, ctx2)
    assert denied.__class__.__name__ == "Denied"
    assert denied.reason.startswith("governance:budget")


def test_run_cli_governance_override_dot_path(tmp_path) -> None:
    out = tmp_path / "run.jsonl"
    result = runner.invoke(
        app,
        [
            "run",
            "--seed",
            "7",
            "--months",
            "3",
            "--governance-override",
            "central_bank.autonomy=4",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


# ---------------------------------------------------------------------------
# 6. Trazas: `traces export` sin Langfuse produce `traces.jsonl` valido;
#    `traces show` imprime el arbol.
# ---------------------------------------------------------------------------


def test_traces_export_and_show(tmp_path) -> None:
    history = run_simulation(seed=7, months=2, actors_enabled=True, default_brain="fake:rules")
    run_path = tmp_path / "run.jsonl"
    run_path.write_text(history.to_jsonl(), encoding="utf-8")

    result = runner.invoke(app, ["traces", "export", str(run_path)])
    assert result.exit_code == 0, result.output
    traces_path = run_path.with_suffix(".traces.jsonl")
    assert traces_path.exists()
    lines = [json.loads(line) for line in traces_path.read_text(encoding="utf-8").splitlines()]
    assert lines
    required = {"trace_id", "span", "parent", "input", "output", "metadata", "start", "end"}
    for row in lines:
        assert row["kind"] == "span"
        assert required <= set(row)

    trace_id = lines[0]["trace_id"]
    result_show = runner.invoke(app, ["traces", "show", str(run_path), trace_id])
    assert result_show.exit_code == 0, result_show.output
    assert trace_id in result_show.output
    assert "perception" in result_show.output


def test_eval_writes_eval_score_back_by_trace_id(tmp_path) -> None:
    from republica.ai.tracing import write_eval_scores

    history = run_simulation(seed=7, months=1, actors_enabled=True, default_brain="fake:rules")
    run_path = tmp_path / "run.jsonl"
    run_path.write_text(history.to_jsonl(), encoding="utf-8")
    traces = read_traces_jsonl(run_path)
    assert traces
    tid = f"{traces[0]['run_id']}:{int(traces[0]['month']):03d}:{traces[0]['actor_id']}"
    updated = write_eval_scores(run_path, {tid: 0.75})
    assert updated == 1
    traces_after = read_traces_jsonl(run_path)
    match = next(t for t in traces_after if t["actor_id"] == traces[0]["actor_id"])
    assert match["eval_score"] == 0.75


# ---------------------------------------------------------------------------
# 7. `eval compare` imprime la tabla y marca diferencias fuera del IC.
# ---------------------------------------------------------------------------


def test_eval_compare_marks_differences_outside_ci(tmp_path) -> None:
    report_a = run_suite(suite="ideological_consistency", brain="rules", judge="fake", seed=7)
    report_b = run_suite(
        suite="ideological_consistency", brain="fake:unauthorized", judge="fake", seed=7
    )
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    report_a.write(a_dir)
    report_b.write(b_dir)

    rows, differing = compare_reports(a_dir, b_dir)
    assert "ideological_consistency" in differing
    assert any(r["metric"] == "ideological_consistency" and r["differs"] for r in rows)

    result = runner.invoke(app, ["eval", "compare", str(a_dir), str(b_dir)])
    assert result.exit_code == 0, result.output
    assert "ideological_consistency" in result.output


def test_export_promptfoo_writes_files_only(tmp_path) -> None:
    paths = export_promptfoo(tmp_path)
    assert len(paths) == 2
    for p in paths:
        assert p.exists()
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert doc


# ---------------------------------------------------------------------------
# 8. Cada metrica mecanica corre en una corrida sintetica chica; forma del
#    IC bootstrap.
# ---------------------------------------------------------------------------


def test_bootstrap_ci_shape() -> None:
    ci = bootstrap_ci([1.0, 0.0, 1.0, 1.0, 0.0, 1.0], seed=1)
    assert ci is not None
    lo, hi = ci
    assert 0.0 <= lo <= hi <= 1.0
    assert bootstrap_ci([1.0]) is None
    assert bootstrap_ci([]) is None


def test_each_mechanical_metric_runs_on_a_tiny_synthetic_run() -> None:
    mechanical = (
        "ideological_consistency",
        "interest_consistency",
        "authority_violation",
        "parse_rate",
        "strategic_adaptation",
        "diversity",
    )
    for suite in mechanical:
        report = run_suite(suite=suite, brain="fake:rules", judge="fake", seed=7)
        assert len(report.metrics) == 1
        metric = report.metrics[0]
        assert metric.id == suite
        assert metric.n >= 0
        assert isinstance(metric.worst_cases, list)


def test_full_suite_runs_end_to_end_for_rules_and_writes_report(tmp_path) -> None:
    report = run_suite(suite="all", brain="rules", judge="fake", seed=7)
    assert len(report.metrics) == 10
    paths = report.write(tmp_path / "out")
    assert all(p.exists() for p in paths)
    data = json.loads(paths[0].read_text(encoding="utf-8"))
    assert len(data["metrics"]) == 10


# ---------------------------------------------------------------------------
# 9. Hash dorado: gobernanza default (sin overrides) reproduce byte a byte
# HEAD `eaed2a8` ("Fase 6: memoria de actores y elecciones (ADR 006)",
# commit previo a esta corrida de ADR 007). Calculado con `git worktree add
# /tmp/head eaed2a8` + `run(seed=..., months=48, policy=taylor,
# actors_enabled=True, congress_enabled=True, negotiation_enabled=True,
# cohorts_enabled=True, media_enabled=True, memory_enabled=True,
# elections_enabled=False)`. `elections_enabled=False` a proposito: otro
# agente esta modificando `world/elections.py`/`data/cohorts_loyalty.csv`/
# `data/cohort_provinces.csv` EN PARALELO (calibracion de ADR 006, fuera del
# alcance de esta tarea) -- el hash dorado de GOBERNANZA (ADR 007) no debe
# depender de ese trabajo concurrente todavia sin terminar; gobernanza no
# interviene en absoluto en la logica de elecciones (`_run_election` no
# llama a `authorize()`), asi que `elections_enabled=False` no le resta
# cobertura a lo que este test prueba. `config_hash` reemplazado por un
# placeholder antes de hashear (mismo precedente que los golden hash
# previos de ADR 004/005/006).
# ---------------------------------------------------------------------------

GOLDEN_HEAD_COMMIT = "eaed2a8"
GOLDEN_SEED7_TAYLOR_SHA256 = "a2448cdb4c3146accef89bdc1d815d4abc8f404d9f0f0a41937d77637104681f"
GOLDEN_SEED42_TAYLOR_SHA256 = "78a8f85a923421e9d9cae3ef8f64efd397d83fd7cf39f74402491d2a4fe0a533"


def _strip_config_hash(jsonl_text: str) -> str:
    lines = jsonl_text.rstrip("\n").split("\n")
    summary = json.loads(lines[-1])
    summary["config_hash"] = "STRIPPED"
    lines[-1] = json.dumps(summary, ensure_ascii=False)
    return "\n".join(lines) + "\n"


def test_default_governance_matches_pre_adr007_golden_hash() -> None:
    taylor = TaylorPolicy(
        COUNTRY.default_policy,
        COUNTRY.taylor,
        COUNTRY.structure.r_neutral,
        COUNTRY.policy_ranges["interest_rate_target"],
    )
    h7 = run_simulation(
        seed=7,
        months=48,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=False,
    )
    digest7 = hashlib.sha256(_strip_config_hash(h7.to_jsonl()).encode("utf-8")).hexdigest()
    assert digest7 == GOLDEN_SEED7_TAYLOR_SHA256

    h42 = run_simulation(
        seed=42,
        months=48,
        policy_rule=taylor,
        country=COUNTRY,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=False,
    )
    digest42 = hashlib.sha256(_strip_config_hash(h42.to_jsonl()).encode("utf-8")).hexdigest()
    assert digest42 == GOLDEN_SEED42_TAYLOR_SHA256
