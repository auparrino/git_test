"""Backends de LLM (ADR 004 secc. 2): `LLMBackend` (protocolo),
`OllamaBackend` (real, stdlib `urllib`), `FakeBackend` (para tests y para
este entorno sin Ollama) y `CachedBackend` (cache en disco).

Desviacion respecto de la firma literal del ADR (documentada en Notas de
implementacion de ADR 004): `complete()` recibe ademas `actor_id`,
`perception` y `rng`, todos opcionales. Hacen falta para que
`FakeBackend(policy="rules")` pueda delegar en el actor por reglas real
(ADR 004 secc. 2: "delega al actor por reglas y serializa su decision") sin
romper la firma de `LLMBackend.complete(system, user, schema, temperature,
seed)` para quien no los necesita (`OllamaBackend` los ignora). `rng` es el
`random.Random` propio del actor (ADR 003 secc. 7): pasarlo permite que
`FakeBackend("rules")` consuma exactamente el mismo generador que
`RuleBasedActor.decide()` consumiria, para que la corrida completa con
`fake:rules` sea reproducible acción por acción contra la corrida
`rules` pura (test de aceptacion 1 de ADR 004 secc. 9).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from republica.engine.perception import Perception

if TYPE_CHECKING:
    from republica.world.config import Party

#: Timeout de red (ADR 004 secc. 2, literal: "Timeout 60 s").
DEFAULT_TIMEOUT_SECONDS = 60.0

#: Reintentos en error de parseo (ADR 004 secc. 2, literal: "Reintento x2").
MAX_PARSE_RETRIES = 2

#: Modo razonamiento de los modelos hibridos (qwen3, deepseek-r1, ...).
#: Por default se APAGA (`"think": false` en el payload): con el razonamiento
#: prendido el modelo gasta el presupuesto de `num_predict` en su monologo
#: antes del JSON, y el `ActorDecision` sale truncado o sucio -- medido en
#: una maquina real con `qwen3:8b`: 918 tokens de respuesta para un payload
#: que necesita ~120, y `parse_rate` 0.50. `REPUBLICA_OLLAMA_THINK=1` lo
#: vuelve a prender. Un modelo que no soporta la clave responde `400` y el
#: backend reintenta solo, sin ella (ver `complete`).
THINK_ENV = "REPUBLICA_OLLAMA_THINK"

#: `num_predict` por entorno, para subirlo sin tocar codigo.
NUM_PREDICT_ENV = "REPUBLICA_OLLAMA_NUM_PREDICT"


def _think_enabled() -> bool:
    return os.environ.get(THINK_ENV, "0").strip().lower() in ("1", "true", "yes")


#: Progreso por llamada a stderr (`REPUBLICA_OLLAMA_PROGRESS=0` lo apaga).
#: Sin esto, `bench-parse`/`run` con un modelo en CPU se quedan callados
#: varios minutos por decision y parecen colgados -- fue lo primero que se
#: reporto al correr la Fase 4 en una maquina propia. Va a stderr para no
#: ensuciar la salida que parsea `scripts/fase4_collect_results.py`.
PROGRESS_ENV = "REPUBLICA_OLLAMA_PROGRESS"


def _progress_enabled() -> bool:
    return os.environ.get(PROGRESS_ENV, "1").strip().lower() not in ("0", "false", "no")


#: `num_predict` de Ollama: tope de tokens de salida. No esta especificado
#: en el ADR (solo pide que `options` incluya `temperature`/`seed`/
#: `num_predict`); 800 alcanza de sobra para un `ActorDecision` (payload
#: chico, `public_message` <=280 y `reasoning` <=600 caracteres).
DEFAULT_NUM_PREDICT = 800


class OllamaUnavailableError(RuntimeError):
    """No se pudo hablar con el servidor de Ollama.

    Se levanta en lugar del `URLError`/`HTTPError` crudo de `urllib` para que
    la CLI pueda imprimir un mensaje accionable (host, causa y que revisar)
    en vez de un traceback de 40 lineas, que es lo que el usuario ve cuando
    Ollama no esta levantado o escucha en otra direccion."""

    def __init__(self, host: str, cause: BaseException) -> None:
        self.host = host
        self.cause = cause
        super().__init__(f"No se pudo conectar con Ollama en {host}: {cause}")


class OllamaHTTPError(RuntimeError):
    """El servidor respondio, pero con un codigo de error.

    Separada de `OllamaUnavailableError` (que es "no se pudo hablar con el
    servidor") porque aca SI hay un cuerpo de respuesta con el motivo, y
    porque el caso mas comun -- un `400` diciendo que el modelo no soporta
    `think` -- se recupera solo reintentando sin esa clave."""

    def __init__(self, host: str, status: int, body: str) -> None:
        self.host = host
        self.status = status
        self.body = body
        super().__init__(f"Ollama en {host} respondio {status}: {body[:300]}")


@dataclass
class LLMResult:
    """ADR 004 secc. 2, literal."""

    text: str
    parsed: dict[str, Any] | None
    model: str
    digest: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    attempts: int


class LLMBackend(Protocol):
    """ADR 004 secc. 2 (mas los 3 parametros opcionales de arriba)."""

    name: str

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float,
        seed: int,
        actor_id: str = "",
        perception: Perception | None = None,
        rng: random.Random | None = None,
    ) -> LLMResult: ...


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class OllamaBackend:
    """`POST /api/chat` a un servidor Ollama (ADR 004 secc. 2). No hay
    Ollama en este entorno (sin red hacia el): se prueba contra un
    `http.server` local fijo (test de aceptacion 6 de ADR 004 secc. 9)."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        host: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        num_predict: int = DEFAULT_NUM_PREDICT,
    ) -> None:
        # `host=None` (default) lee `OLLAMA_HOST` del entorno, igual que el
        # CLI oficial de Ollama; si tampoco esta seteada, el default de
        # siempre (ADR 004 secc. 2, literal). No forma parte de la firma que
        # da el ADR (`OllamaBackend(model, host="http://localhost:11434")`),
        # se agrega para no tener que instanciar el backend a mano solo para
        # apuntar a otro host (ver `docs/OLLAMA_SETUP.md`).
        self.model = model
        host = host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        self.host = host.rstrip("/")
        # `REPUBLICA_OLLAMA_TIMEOUT` (segundos) permite subir el timeout de
        # 60 s del ADR 004 sin tocar codigo cuando el modelo corre en CPU
        # (un 8B sin GPU puede tardar mas de un minuto por decision, ver
        # `docs/OLLAMA_SETUP.md`). Solo se lee si el caller dejo el default.
        env_timeout = os.environ.get("REPUBLICA_OLLAMA_TIMEOUT")
        if timeout == DEFAULT_TIMEOUT_SECONDS and env_timeout:
            try:
                timeout = float(env_timeout)
            except ValueError:
                pass
        self.timeout = timeout
        env_np = os.environ.get(NUM_PREDICT_ENV)
        if num_predict == DEFAULT_NUM_PREDICT and env_np:
            try:
                num_predict = int(env_np)
            except ValueError:
                pass
        self.num_predict = num_predict
        #: Se apaga solo si el servidor rechaza la clave `think` (modelo sin
        #: soporte): a partir de ahi esta instancia no la manda mas.
        self._send_think = not _think_enabled()
        #: Llamadas hechas y segundos acumulados, solo para el progreso.
        self._calls = 0
        self._elapsed_s = 0.0

    def _post(self, payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # el servidor contesto, con error
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - el cuerpo es opcional
                body = ""
            raise OllamaHTTPError(self.host, exc.code, body) from exc
        except (urllib.error.URLError, OSError) as exc:  # no se pudo hablar
            raise OllamaUnavailableError(self.host, exc) from exc
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self._calls += 1
        self._elapsed_s += latency_ms / 1000.0
        if _progress_enabled():
            total = self._elapsed_s
            print(
                f"[ollama] llamada {self._calls}: {latency_ms / 1000.0:.1f}s "
                f"(acumulado {int(total // 60)}m {total % 60:04.1f}s, "
                f"promedio {total / self._calls:.1f}s)",
                file=sys.stderr,
                flush=True,
            )
        return json.loads(raw), latency_ms

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float,
        seed: int,
        actor_id: str = "",  # noqa: ARG002 - no lo usa un backend real
        perception: Perception | None = None,  # noqa: ARG002
        rng: random.Random | None = None,  # noqa: ARG002
    ) -> LLMResult:
        current_user = user
        latency_ms = 0.0
        text = ""
        attempts = 0
        max_attempts = 1 + MAX_PARSE_RETRIES
        while attempts < max_attempts:
            attempts += 1
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": current_user},
                ],
                "format": schema,
                "options": {
                    "temperature": temperature,
                    "seed": seed,
                    "num_predict": self.num_predict,
                },
                "stream": False,
            }
            if self._send_think:
                payload["think"] = False
            try:
                data, latency_ms = self._post(payload)
            except OllamaHTTPError as exc:
                # Un modelo sin modo razonamiento rechaza la clave `think`
                # con un 400; se reintenta una vez sin ella y esta instancia
                # deja de mandarla. Cualquier otro error HTTP sube.
                if not (self._send_think and exc.status == 400 and "think" in exc.body.lower()):
                    raise
                self._send_think = False
                payload.pop("think", None)
                data, latency_ms = self._post(payload)
            message = data.get("message", {})
            text = message.get("content", "")
            if not text.strip() and message.get("thinking"):
                # El servidor mando el razonamiento aparte y dejo `content`
                # vacio: el JSON no llego a generarse dentro de `num_predict`.
                # Se deja el texto del razonamiento para que la traza muestre
                # que paso, en vez de un `parse_error` sobre una cadena vacia.
                text = str(message["thinking"])
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                if attempts >= max_attempts:
                    return LLMResult(
                        text=text,
                        parsed=None,
                        model=data.get("model", self.model),
                        digest=_digest(text),
                        prompt_tokens=int(data.get("prompt_eval_count", 0)),
                        completion_tokens=int(data.get("eval_count", 0)),
                        latency_ms=latency_ms,
                        attempts=attempts,
                    )
                # Reintento con el error de parseo agregado al prompt
                # (ADR 004 secc. 2, literal).
                current_user = (
                    f"{user}\n\nERROR DE PARSEO EN EL INTENTO ANTERIOR: {exc}. "
                    "Responde solo con JSON valido segun el esquema."
                )
                continue
            return LLMResult(
                text=text,
                parsed=parsed,
                model=data.get("model", self.model),
                digest=_digest(text),
                prompt_tokens=int(data.get("prompt_eval_count", 0)),
                completion_tokens=int(data.get("eval_count", 0)),
                latency_ms=latency_ms,
                attempts=attempts,
            )
        # Inalcanzable (el bucle siempre retorna dentro de `max_attempts`
        # intentos), solo para que el chequeo de tipos vea un retorno total.
        return LLMResult(
            text=text,
            parsed=None,
            model=self.model,
            digest=_digest(text),
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            attempts=attempts,
        )


def _empty_decision_payload(reasoning: str) -> dict[str, Any]:
    return {
        "position": "neutral",
        "intensity": 0.0,
        "public_message": "",
        "private_strategy": "wait",
        "actions": [],
        "requested_concession": None,
        "confidence": 0.5,
        "reasoning": reasoning,
    }


def _unauthorized_decision_payload(actor_id: str) -> dict[str, Any]:
    """Policy `unauthorized` (ADR 004 secc. 2): acciones fuera de rol, para
    probar `authorize()`. Un `governor` que emite `SET_RATE` (solo
    `central_bank`) y un `media` que emite `STRIKE` (solo `union`) son los
    dos ejemplos literales del ADR; cualquier otro rol recibe uno de los dos
    (los dos tipos existen en el catalogo asi que `to_actions` no los
    descarta por tipo desconocido, solo `authorize()` los deniega por rol)."""
    request_type = "STRIKE" if "media" not in actor_id else "SET_RATE"
    return {
        "position": "oppose",
        "intensity": 0.8,
        "public_message": "No vamos a quedarnos de brazos cruzados.",
        "private_strategy": "escalate",
        "actions": [{"type": "SET_RATE", "params": {"delta_pp": 5.0}, "target": None}]
        if request_type == "SET_RATE"
        else [
            {
                "type": "STRIKE",
                "params": {"sector": "general", "days": 2},
                "target": None,
            }
        ],
        "requested_concession": None,
        "confidence": 0.7,
        "reasoning": "probando authorize() con una accion fuera de rol (ADR 004 secc. 9, test 3)",
    }


@dataclass
class FakeBackend:
    """ADR 004 secc. 2: `policy` en `rules|scripted|malformed|unauthorized`.

    `scripted`: `dict[(actor_id, month), payload]`, con `payload` un dict
    listo para `ActorDecision.model_validate` (no lo especifica el ADR mas
    alla de "respuestas fijas por actor/mes"; se eligio la forma mas directa,
    la misma que produce `_rules_decision`)."""

    policy: str
    scripted: dict[tuple[str, int], dict[str, Any]] | None = None
    #: ADR 006 secc. 1.3 (default `False`, mismo criterio de siempre): el
    #: `RuleBasedActor` que envuelve `policy="rules"` necesita saber si
    #: `w_mem`/`trust_president` estan activos para reproducir EXACTAMENTE
    #: el mismo score que una corrida `"rules"` directa -- sin esto,
    #: `fake:rules` con `features.memory = True` divergia del `RuleBasedActor`
    #: real (que si recibe `memory_enabled` via `ai/brains.py::
    #: build_decision_actor`), rompiendo el test de aceptacion 1 de ADR 004
    #: secc. 9 en cuanto la memoria esta prendida.
    memory_enabled: bool = False
    name: str = field(default="", init=False)
    #: Cache de `RuleBasedActor` por actor (solo `policy="rules"`): evita
    #: reconstruir el actor -- y releer `data/actor_weights.yaml`/etc. -- en
    #: cada mes de una corrida de varios meses.
    _rule_actors: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        valid = {"rules", "scripted", "malformed", "unauthorized"}
        if self.policy not in valid:
            raise ValueError(f"policy desconocida para FakeBackend: {self.policy!r} (usar {valid})")
        self.name = f"fake:{self.policy}"

    def _rule_actor_for(self, actor_id: str) -> Any:
        cached = self._rule_actors.get(actor_id)
        if cached is not None:
            return cached
        # Import diferido: evita un ciclo de imports (`actors.rule_based`
        # importa `engine.perception`, que no importa `ai.*`, pero
        # `ai.backends` se importa desde `actors.llm_based`, que convive con
        # `actors.rule_based` -- mantenerlo local aca alcanza y es mas
        # barato de leer que reordenar el paquete `actors`).
        from republica.actors.rule_based import RuleBasedActor
        from republica.actors.sheet import load_actors
        from republica.world.config import load_country

        country = load_country()
        sheet = load_actors()[actor_id]
        rule_actor = RuleBasedActor(
            sheet,
            country.parties,
            country.taylor,
            country.structure.r_neutral,
            country.policy_ranges["interest_rate_target"],
            memory_enabled=self.memory_enabled,
        )
        self._rule_actors[actor_id] = rule_actor
        return rule_actor

    def refresh_parties(self, parties: list[Party]) -> None:
        """Refresca `parties_by_id` de cada `RuleBasedActor` cacheado en
        `_rule_actors` (hallazgo #1 de REVIEW_002): `_rule_actor_for` los
        arma con `load_country().parties` -- SIEMPRE la config de disco, ni
        siquiera la de la corrida -- la primera vez que se le pide una
        decision a cada actor, y los cachea para el resto de la corrida.
        Sin este refresco, `fake:rules` nunca se enteraba de una transicion
        de gobierno (llamado por `engine/scheduler.py::
        refresh_decision_actor_parties` en cada `_run_election`)."""
        for rule_actor in self._rule_actors.values():
            rule_actor.refresh_parties(parties)

    def _rules_payload(
        self, actor_id: str, perception: Perception | None, rng: random.Random | None
    ) -> dict[str, Any]:
        if perception is None or rng is None:
            raise ValueError(
                "FakeBackend(policy='rules') necesita `perception` y `rng` en complete() "
                "(ver Notas de implementacion de ADR 004: desviacion de firma)"
            )
        rule_actor = self._rule_actor_for(actor_id)
        actions = rule_actor.decide(perception, rng)
        return _actions_to_decision_payload(actions)

    def complete(
        self,
        *,
        system: str,  # noqa: ARG002 - el fake no "lee" el prompt, decide por otra via
        user: str,  # noqa: ARG002
        schema: dict[str, Any],  # noqa: ARG002
        temperature: float,  # noqa: ARG002
        seed: int,  # noqa: ARG002
        actor_id: str = "",
        perception: Perception | None = None,
        rng: random.Random | None = None,
    ) -> LLMResult:
        t0 = time.perf_counter()
        if self.policy == "malformed":
            text = '{"position": "support", "intensity": 0.5, invalid json here'
            latency_ms = (time.perf_counter() - t0) * 1000.0
            # Simula el mismo `attempts` final que tendria un `OllamaBackend`
            # que reintento 2 veces y siguio sin poder parsear (ADR 004
            # secc. 9, test 2): no hace falta reintentar de verdad, es un
            # backend fake sin red.
            return LLMResult(
                text=text,
                parsed=None,
                model=self.name,
                digest=_digest(text),
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                attempts=1 + MAX_PARSE_RETRIES,
            )

        if self.policy == "unauthorized":
            payload = _unauthorized_decision_payload(actor_id)
        elif self.policy == "scripted":
            month = perception.month if perception is not None else -1
            payload = (self.scripted or {}).get((actor_id, month))
            if payload is None:
                payload = _empty_decision_payload(f"sin guion para {actor_id}@{month}")
        else:  # "rules"
            payload = self._rules_payload(actor_id, perception, rng)

        text = json.dumps(payload, ensure_ascii=False)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return LLMResult(
            text=text,
            parsed=payload,
            model=self.name,
            digest=_digest(text),
            prompt_tokens=len(system) // 4,
            completion_tokens=len(text) // 4,
            latency_ms=latency_ms,
            attempts=1,
        )


def _actions_to_decision_payload(actions: list[Any]) -> dict[str, Any]:
    """Inverso aproximado de `ai.schemas.to_actions`: una `list[Action]`
    (la que produjo `RuleBasedActor.decide()`) -> un payload de
    `ActorDecision`. Solo lo usa `FakeBackend(policy="rules")`, para que el
    pipeline completo (LLM incluido) pueda correr sobre una decision de
    reglas real (ADR 004 secc. 2)."""
    from republica.engine.actions import ActionType

    position = "neutral"
    intensity = 0.0
    public_message = ""
    requested_concession = None
    private_strategy = "wait"
    extra: list[dict[str, Any]] = []
    reasoning_parts: list[str] = []

    for action in actions:
        reasoning_parts.append(action.reason)
        if action.type is ActionType.SUPPORT_POLICY:
            position = "support"
            intensity = float(action.params.get("intensity", intensity))
            private_strategy = "cooperate"
        elif action.type is ActionType.OPPOSE_POLICY:
            position = "oppose"
            intensity = float(action.params.get("intensity", intensity))
            private_strategy = "pressure"
        elif action.type is ActionType.NEGOTIATE:
            position = "negotiate"
            requested_concession = action.params.get("requested_concession")
            private_strategy = "cooperate"
        elif action.type is ActionType.PUBLIC_STATEMENT:
            public_message = action.reason[:280]
            intensity = float(action.params.get("intensity", intensity))
        elif action.type is ActionType.NO_ACTION:
            continue
        else:
            if action.type in (ActionType.STRIKE, ActionType.CALL_PROTEST):
                private_strategy = "escalate"
            extra.append(
                {
                    "type": action.type.value,
                    "params": dict(action.params),
                    "target": action.target,
                }
            )

    return {
        "position": position,
        "intensity": intensity,
        "public_message": public_message,
        "private_strategy": private_strategy,
        "actions": extra[:3],
        "requested_concession": requested_concession,
        "confidence": 0.9,
        "reasoning": " | ".join(reasoning_parts)[:600] or "sin razon",
    }


@dataclass
class CachedBackend:
    """ADR 004 secc. 2: cache en disco por
    `sha256(model + system + user + schema + seed)` (literal -- no incluye
    `temperature` en la clave, tal cual el ADR). Obligatorio en Fase 8 para
    reproducibilidad y costo; disponible desde ya."""

    inner: LLMBackend
    cache_dir: Path
    name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.name = f"cached:{getattr(self.inner, 'name', 'inner')}"
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def _cache_key(
        self, model: str, system: str, user: str, schema: dict[str, Any], seed: int
    ) -> str:
        h = hashlib.sha256()
        h.update(model.encode("utf-8"))
        h.update(b"\0")
        h.update(system.encode("utf-8"))
        h.update(b"\0")
        h.update(user.encode("utf-8"))
        h.update(b"\0")
        h.update(json.dumps(schema, sort_keys=True).encode("utf-8"))
        h.update(b"\0")
        h.update(str(seed).encode("utf-8"))
        return h.hexdigest()

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float,
        seed: int,
        actor_id: str = "",
        perception: Perception | None = None,
        rng: random.Random | None = None,
    ) -> LLMResult:
        model = getattr(self.inner, "model", getattr(self.inner, "name", "unknown"))
        key = self._cache_key(model, system, user, schema, seed)
        path = Path(self.cache_dir) / f"{key}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return LLMResult(**data)
        result = self.inner.complete(
            system=system,
            user=user,
            schema=schema,
            temperature=temperature,
            seed=seed,
            actor_id=actor_id,
            perception=perception,
            rng=rng,
        )
        path.write_text(json.dumps(asdict(result), ensure_ascii=False), encoding="utf-8")
        return result
