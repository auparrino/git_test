"""Tests de aceptacion de ADR 004 (secc. 9) mas los extra de los
deliverables 1-8: esquema (`to_actions`), prompts (visibilidad), backends
(`FakeBackend`/`CachedBackend`/`OllamaBackend`) y CLI (`bench-parse`,
`compare`). Todos corren sin Ollama (sin red hacia el): el test 6 usa un
`http.server` local en un thread."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pydantic
import pytest
from typer.testing import CliRunner

import republica.actors.llm_based as llm_based_mod
from republica.actors.llm_based import LLMActor
from republica.actors.rule_based import make_actor_rng
from republica.actors.sheet import load_actors
from republica.ai.backends import CachedBackend, FakeBackend, LLMResult, OllamaBackend
from republica.ai.prompts import render_system, render_user
from republica.ai.schemas import MAX_ACTIONS_PER_TURN, ActionRequest, ActorDecision, to_actions
from republica.cli import app
from republica.engine.actions import ActionType
from republica.engine.perception import PolicyProposal, build_perception, build_provinces_table
from republica.engine.permissions import load_permissions
from republica.engine.simulation import run
from republica.governance import ActorGovernance
from republica.world.config import load_country
from republica.world.events import ShockAggregate
from republica.world.state import WorldState

COUNTRY = load_country()
ACTORS = load_actors()
runner = CliRunner()


def _perception(actor_id: str, delta: dict[str, float] | None = None, month: int = 3):
    sheet = ACTORS[actor_id]
    agg = ShockAggregate()
    table = build_provinces_table(
        COUNTRY.initial_state, COUNTRY.default_policy, COUNTRY.provinces, agg
    )
    proposal = PolicyProposal(delta=delta or {}, label="test")
    from republica.world.economy import Aux

    zero_aux = Aux(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    perception = build_perception(
        sheet,
        COUNTRY.initial_state,
        zero_aux,
        proposal,
        [],
        [],
        month,
        30,
        table,
        COUNTRY.parties,
        policy=COUNTRY.default_policy,
    )
    return sheet, perception


# 1. FakeBackend("rules") == rules, 48 meses, 3 actores ----------------------


def _authorized_key(action_records, actor_id: str) -> list[tuple]:
    """(month, type, params sin `offer`, authorized) por actor: `offer` es
    texto libre que `to_actions`/`FakeBackend("rules")` no reconstruyen
    igual que `RuleBasedActor` (no cambia que accion se autoriza)."""
    out = []
    for rec in action_records:
        d = rec.to_dict()
        if d["actor"] != actor_id:
            continue
        params = {k: v for k, v in d["params"].items() if k != "offer"}
        out.append((d["month"], d["type"], tuple(sorted(params.items())), d["authorized"]))
    return out


def test_fake_rules_matches_rule_based_over_48_months() -> None:
    """Test de aceptacion 1 (ADR 004 secc. 9): `fake:rules` para 3 actores
    produce exactamente las mismas acciones autorizadas (y las mismas
    denegadas) que `rules`, mes a mes, durante 48 meses."""
    target_actors = ("gov_norte", "union_cgt", "central_bank")
    baseline = run(seed=7, months=48, actors_enabled=True)
    via_llm = run(
        seed=7,
        months=48,
        actors_enabled=True,
        brain_map={actor_id: "fake:rules" for actor_id in target_actors},
    )
    for actor_id in target_actors:
        assert _authorized_key(via_llm.action_records, actor_id) == _authorized_key(
            baseline.action_records, actor_id
        )
    # La corrida con `fake:rules` si genera trazas (una por actor y mes).
    assert len(via_llm.trace_records) == 48 * len(target_actors)
    assert all(t.parse_error is None for t in via_llm.trace_records)


# 2. FakeBackend("malformed"): parse_error -> NO_ACTION, la corrida sigue ----


def test_fake_malformed_falls_back_to_no_action_without_breaking_the_run() -> None:
    """Test de aceptacion 2 (ADR 004 secc. 9)."""
    history = run(seed=7, months=6, actors_enabled=True, brain_map={"gov_norte": "fake:malformed"})
    assert len(history.records) == 6  # la corrida completa igual

    traces = [t for t in history.trace_records if t.actor_id == "gov_norte"]
    assert len(traces) == 6
    for trace in traces:
        assert trace.parse_error is not None
        assert trace.parsed is None
        assert trace.attempts == 3  # 1 intento + 2 reintentos (ADR 004 secc. 2)
        assert trace.actions_emitted == [{"type": "NO_ACTION", "target": None, "params": {}}]

    gov_records = [r.to_dict() for r in history.action_records if r.actor == "gov_norte"]
    assert gov_records  # NO_ACTION igual queda registrado (autorizado: todos los roles lo tienen)
    assert all(r["type"] == "NO_ACTION" and r["authorized"] for r in gov_records)


# 3. FakeBackend("unauthorized"): denegadas, con denied_reason en la traza --


def test_fake_unauthorized_actions_are_denied_and_traced() -> None:
    """Test de aceptacion 3 (ADR 004 secc. 9): un `governor` que intenta
    `STRIKE` (solo `union`) y un `media` que intenta `SET_RATE` (solo
    `central_bank`) quedan denegados por `authorize()` y la denegacion
    aparece en la `DecisionTrace`."""
    history = run(
        seed=7,
        months=3,
        actors_enabled=True,
        brain_map={"gov_norte": "fake:unauthorized", "media_nacional": "fake:unauthorized"},
    )
    gov_traces = [t for t in history.trace_records if t.actor_id == "gov_norte"]
    media_traces = [t for t in history.trace_records if t.actor_id == "media_nacional"]
    assert len(gov_traces) == 3
    assert len(media_traces) == 3

    for trace in gov_traces:
        assert trace.parse_error is None
        denied_types = [d["type"] for d in trace.actions_denied]
        assert "STRIKE" in denied_types
        strike_denial = next(d for d in trace.actions_denied if d["type"] == "STRIKE")
        assert "no tiene permitido" in strike_denial["denied_reason"]
        # El resto del `ActorDecision` (`OPPOSE_POLICY`/`PUBLIC_STATEMENT`,
        # ADR 004 secc. 3 reglas 1/2) si son de su rol: quedan autorizados.
        assert trace.actions_authorized

    for trace in media_traces:
        denied_types = [d["type"] for d in trace.actions_denied]
        assert "SET_RATE" in denied_types
        rate_denial = next(d for d in trace.actions_denied if d["type"] == "SET_RATE")
        assert "no tiene permitido" in rate_denial["denied_reason"]


# 4. Visibilidad por rol (ADR 004 secc. 5/9) ---------------------------------


def test_governor_prompt_has_no_exact_reserves_but_central_bank_does() -> None:
    _, perc_gov = _perception("gov_norte")
    _, perc_bank = _perception("central_bank")
    permissions = load_permissions()

    gov_user = render_user(perc_gov, sorted(permissions["governor"], key=lambda t: t.value))
    bank_user = render_user(perc_bank, sorted(permissions["central_bank"], key=lambda t: t.value))

    assert "reserves_exact" not in gov_user
    assert "reserves_exact" in bank_user
    # Tampoco el estado completo se filtra en el prompt de un gobernador.
    assert "public_debt" not in gov_user


def test_render_system_only_uses_the_actor_sheet() -> None:
    sheet = ACTORS["gov_norte"]
    system = render_system(sheet)
    assert sheet.name in system
    assert "REGLAS" in system
    assert len(_HARD_RULE_MARKERS) == 3
    for marker in _HARD_RULE_MARKERS:
        assert marker in system


_HARD_RULE_MARKERS = ("No inventes", "No prometas", "razon concreta")


# 5. CachedBackend: la segunda llamada no golpea el backend interno ---------


class _CountingBackend:
    name = "counting"
    model = "counting-model"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, *, system, user, schema, temperature, seed, **_kwargs) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text="{}",
            parsed={"ok": True, "call": self.calls},
            model=self.model,
            digest="deadbeef",
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1.0,
            attempts=1,
        )


def test_cached_backend_does_not_call_inner_twice(tmp_path) -> None:
    inner = _CountingBackend()
    cached = CachedBackend(inner, tmp_path)
    kwargs = {
        "system": "s",
        "user": "u",
        "schema": {"type": "object"},
        "temperature": 0.4,
        "seed": 1,
    }

    first = cached.complete(**kwargs)
    second = cached.complete(**kwargs)

    assert inner.calls == 1
    assert first.parsed == second.parsed == {"ok": True, "call": 1}

    # Una clave distinta (`seed` cambia) si pega al backend interno.
    cached.complete(**{**kwargs, "seed": 2})
    assert inner.calls == 2


# 6. OllamaBackend contra un http.server local --------------------------------


class _FixedOllamaHandler(BaseHTTPRequestHandler):
    captured_body: dict = {}
    response_payload = {
        "position": "support",
        "intensity": 0.6,
        "public_message": "Vamos bien.",
        "private_strategy": "cooperate",
        "actions": [],
        "requested_concession": None,
        "confidence": 0.8,
        "reasoning": "test",
    }

    def do_POST(self) -> None:  # noqa: N802 - metodo de http.server
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        _FixedOllamaHandler.captured_body = body
        response = {
            "model": body["model"],
            "message": {
                "role": "assistant",
                "content": json.dumps(_FixedOllamaHandler.response_payload),
            },
            "prompt_eval_count": 123,
            "eval_count": 45,
        }
        payload = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # silencia el log de acceso
        pass


@pytest.fixture
def fake_ollama_server():
    server = HTTPServer(("127.0.0.1", 0), _FixedOllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_ollama_backend_against_local_http_server(fake_ollama_server) -> None:
    port = fake_ollama_server
    backend = OllamaBackend(model="qwen3:8b", host=f"http://127.0.0.1:{port}")
    schema = ActorDecision.model_json_schema()

    result = backend.complete(
        system="sos un actor de prueba",
        user="respondé con el JSON",
        schema=schema,
        temperature=0.4,
        seed=42,
    )

    assert result.parsed == _FixedOllamaHandler.response_payload
    assert result.attempts == 1
    assert result.prompt_tokens == 123
    assert result.completion_tokens == 45

    sent = _FixedOllamaHandler.captured_body
    assert sent["format"] == schema
    assert sent["options"]["seed"] == 42
    assert sent["options"]["temperature"] == 0.4
    assert sent["stream"] is False
    assert sent["model"] == "qwen3:8b"


# 7. Inmutabilidad de WorldState tambien con un LLMActor en la mezcla -------


def test_world_state_stays_frozen_with_an_llm_actor_in_the_mix() -> None:
    """Reusa el test de ADR 003 secc. 9 (3): agregar un `LLMActor` a la
    mezcla no abre ningun camino nuevo para mutar `WorldState` fuera del
    motor."""
    history = run(seed=7, months=3, actors_enabled=True, brain_map={"gov_norte": "fake:rules"})
    state = history.records[-1]
    with pytest.raises(pydantic.ValidationError):
        WorldState.model_validate(state.state).gdp = 999.0  # type: ignore[misc]


# to_actions: tope de 3 acciones, sobrantes descartadas y logueadas ----------


def test_to_actions_caps_at_three_and_logs_extras(caplog) -> None:
    actor = ACTORS["gov_norte"]
    decision = ActorDecision(
        position="oppose",
        intensity=0.9,
        public_message="No vamos a aceptar esto.",
        private_strategy="escalate",
        actions=[
            ActionRequest(type="LOBBY_CONGRESS", params={"direction": "against", "intensity": 0.5}),
            ActionRequest(type="REQUEST_FUNDS", params={"amount_pct_gdp": 0.2}),
            ActionRequest(type="FORM_ALLIANCE", params={"with": "union_cgt"}),
        ],
        confidence=0.7,
        reasoning="test de tope",
    )
    with caplog.at_level(logging.INFO):
        actions = to_actions(decision, actor)

    assert len(actions) == MAX_ACTIONS_PER_TURN == 3
    assert "supero el presupuesto" in caplog.text


def test_to_actions_drops_unknown_action_types() -> None:
    actor = ACTORS["gov_norte"]
    decision = ActorDecision(
        position="neutral",
        intensity=0.1,
        public_message="",
        private_strategy="wait",
        actions=[ActionRequest(type="LAUNCH_MISSILES", params={})],
        confidence=0.5,
        reasoning="",
    )
    actions = to_actions(decision, actor)
    assert len(actions) == 1
    assert actions[0].type is ActionType.NO_ACTION


# LLMActor.decide: paridad de interfaz con RuleBasedActor -------------------


def test_llm_actor_decide_matches_rule_based_actor_interface() -> None:
    _, perception = _perception("gov_norte", {"provincial_transfers": -3.0})
    backend = FakeBackend(policy="rules")
    llm_actor = LLMActor(ACTORS["gov_norte"], backend, seed_base=123)
    actions = llm_actor.decide(perception, make_actor_rng(7, "gov_norte"))
    assert isinstance(actions, list)
    assert llm_actor.last_trace is not None
    assert llm_actor.last_trace.actor_id == "gov_norte"
    assert llm_actor.last_trace.brain == "llm:fake:rules"


def test_llm_actor_prompt_intersects_role_matrix_with_governance(monkeypatch) -> None:
    """Hallazgo #6 de REVIEW_002: `LLMActor.decide` listaba las acciones
    disponibles solo desde la matriz de rol (`data/permissions.yaml`), sin
    intersecar `write|execute` de la ficha de gobernanza del actor -- un
    actor con gobernanza restringida (`--governance-override`, o cualquier
    `governance.yaml` no generado 1:1 desde la matriz de rol) veia un prompt
    que le ofrecia acciones que `authorize()` le iba a denegar igual. `data/
    governance.yaml` por default espeja la matriz de rol (sin actor
    restringido de fabrica), asi que se arma una `ActorGovernance` a mano
    sin `SET_RATE` en `execute` para `central_bank` (que la matriz de rol SI
    permite) y se espia `render_user` (via `llm_based_mod`, el modulo que lo
    importa) para ver la lista de acciones que efectivamente se le ofrece."""
    captured: dict[str, list[ActionType]] = {}
    real_render_user = llm_based_mod.render_user

    def spy_render_user(perception, allowed_actions):
        captured["allowed_actions"] = list(allowed_actions)
        return real_render_user(perception, allowed_actions)

    monkeypatch.setattr(llm_based_mod, "render_user", spy_render_user)

    role_types = load_permissions()["central_bank"]
    assert ActionType.SET_RATE in role_types  # la matriz de rol SI lo permite

    sheet = ACTORS["central_bank"]
    _, perception = _perception("central_bank")
    backend = FakeBackend(policy="unauthorized")  # la respuesta no importa aca

    # Sin gobernanza (default `None`, ningun llamador existente lo pasaba):
    # comportamiento de siempre, la lista completa de la matriz de rol.
    llm_actor_unrestricted = LLMActor(sheet, backend, seed_base=1)
    llm_actor_unrestricted.decide(perception, make_actor_rng(7, "central_bank"))
    assert ActionType.SET_RATE in captured["allowed_actions"]

    # Con gobernanza restringida (`SET_RATE` fuera de `write`/`execute`):
    # la interseccion lo saca de la lista, aunque la matriz de rol lo
    # permita.
    restricted_gov = ActorGovernance(
        actor_id="central_bank",
        write=("PUBLIC_STATEMENT", "NO_ACTION", "RECOMMEND_RATE", "SUPPORT_POLICY"),
        execute=(),
    )
    llm_actor_restricted = LLMActor(sheet, backend, seed_base=1, governance=restricted_gov)
    llm_actor_restricted.decide(perception, make_actor_rng(7, "central_bank"))
    assert ActionType.SET_RATE not in captured["allowed_actions"]
    assert ActionType.PUBLIC_STATEMENT in captured["allowed_actions"]


# CLI: bench-parse --brain fake:rules imprime parse_rate 1.0 ----------------


def test_cli_bench_parse_fake_rules_reports_full_parse_rate() -> None:
    result = runner.invoke(
        app,
        [
            "bench-parse",
            "--brain",
            "fake:rules",
            "--n",
            "20",
            "--role",
            "governor",
            "--seed",
            "7",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "1.00" in result.output
    assert "parse_rate" in result.output


def test_cli_compare_runs() -> None:
    result = runner.invoke(
        app,
        [
            "compare",
            "--seed",
            "7",
            "--a",
            "rules",
            "--b",
            "fake:rules",
            "--actor",
            "gov_norte",
            "--months",
            "6",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "gov_norte" in result.output


def test_cli_run_with_brain_flag_produces_trace_lines(tmp_path) -> None:
    out = tmp_path / "run_brain.jsonl"
    result = runner.invoke(
        app,
        [
            "run",
            "--seed",
            "7",
            "--months",
            "3",
            "--actors",
            "--brain",
            "fake:rules",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    lines = out.read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line).get("kind") for line in lines[:-1]]
    assert "trace" in kinds
