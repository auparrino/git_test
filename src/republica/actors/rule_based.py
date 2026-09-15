"""Decision por reglas (ADR 003 secc. 6): `RuleBasedActor.decide(perception,
rng) -> list[Action]`. Cubre el score generico (secc. 6/6.1/6.2), la regla de
medios (secc. 6.3) y la regla del Banco Central (secc. 6.4)."""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from republica.actors.sheet import ActorSheet
from republica.engine.actions import Action, ActionType, ConcessionType
from republica.engine.perception import Perception
from republica.engine.permissions import ACTION_BUDGET_PER_TURN, Governance, load_governance
from republica.world.config import Party, TaylorParams
from republica.world.state import clamp, pos

DEFAULT_WEIGHTS_PATH = Path(__file__).resolve().parents[3] / "data" / "actor_weights.yaml"
DEFAULT_SIGNATURES_PATH = Path(__file__).resolve().parents[3] / "data" / "policy_signatures.yaml"
DEFAULT_INTERESTS_PATH = Path(__file__).resolve().parents[3] / "data" / "interests.yaml"

#: Umbrales de score (ADR 003 secc. 6).
SUPPORT_THRESHOLD = 20.0
OPPOSE_THRESHOLD = -20.0
INTENSITY_SCALE = 80.0

#: Roles que pueden emitir `NEGOTIATE` (ADR 003 secc. 4) y por lo tanto son
#: candidatos a hacerlo en la zona "entre medio" del score (secc. 6).
#: Umbrales de "ruido": sin estos, casi todos los actores negociaban y declaraban
#: todos los meses con intensidad ~0.05 (revision v0.3).
NEGOTIATE_MIN_ABS_SCORE = 8.0
STATEMENT_MIN_INTENSITY = 0.15

NEGOTIATE_CAPABLE_ROLES = frozenset({"governor", "party", "union", "business", "economy_minister"})

#: Umbrales base de la regla de medios (ADR 003 secc. 6.3, literal) y cuanto
#: los desplaza la distancia ideologica del medio al partido de gobierno
#: (hallazgo #4 de REVIEW_001: `ideology.economic` no se usaba, los 3
#: medios emitian el mismo frame siempre). Un medio mas lejos del gobierno
#: en el eje economico es mas critico: le alcanza con una aprobacion mas
#: alta o una inflacion mas baja para llamar "crisis", y le hace falta mas
#: crecimiento para llamar "recovery". Coeficientes inventados para v0.3,
#: documentados en ADR 003 secc. 12 (mismo orden de magnitud que el resto
#: de los `coef` inventados del modulo).
MEDIA_CRISIS_APPROVAL_BASE = 45.0
MEDIA_CRISIS_INFLATION_BASE = 3.0
MEDIA_RECOVERY_GROWTH_BASE = 2.0
MEDIA_BIAS_APPROVAL_COEF = 10.0
MEDIA_BIAS_INFLATION_COEF = 1.0
MEDIA_BIAS_GROWTH_COEF = 1.0

#: Concesion que cada rol pide al negociar (ADR 003 secc. 4/6 no especifica
#: cual: se elige la mas afin al rol, documentado en Notas de implementacion).
_NEGOTIATE_CONCESSION: dict[str, ConcessionType] = {
    "governor": ConcessionType.RESTORE_TRANSFERS,
    "party": ConcessionType.CABINET_SEAT,
    "union": ConcessionType.WAGE_BONUS,
    "business": ConcessionType.TAX_EXEMPTION,
    "economy_minister": ConcessionType.DELAY_POLICY,
}

#: Cooldown en meses, por (actor, concesion), despues de recibir un
#: `GRANT_CONCESSION` (hallazgo #5 de REVIEW_001, documentado ahi: "agregar
#: un cooldown de 6 meses ... si hace falta"). Con la propuesta fantasma ya
#: arreglada (`Simulation.concessions_delta` persistente,
#: `engine/simulation.py::advance_month`) esto es una segunda barrera, mas
#: barata que dejarlo librado a que el score baje solo: un actor recien
#: concedido no vuelve a pedir la MISMA concesion en el corto plazo aunque
#: su score siga en zona de `NEGOTIATE`.
CONCESSION_COOLDOWN_MONTHS = 6


@lru_cache(maxsize=4)
def _load_yaml(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_weights(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    return _load_yaml(str(path) if path is not None else str(DEFAULT_WEIGHTS_PATH))


def load_signatures(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    return _load_yaml(str(path) if path is not None else str(DEFAULT_SIGNATURES_PATH))


def load_interests_config(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    return _load_yaml(str(path) if path is not None else str(DEFAULT_INTERESTS_PATH))


def actor_seed(seed: int, actor_id: str) -> int:
    """Semilla estable por actor (ADR 003 secc. 7): `hash((seed, actor_id))`
    pedia por el ADR es el `hash()` builtin de Python, que trae salt por
    proceso (no determinista entre corridas); se usa `zlib.crc32` sobre una
    representacion textual estable en su lugar (documentado en Notas de
    implementacion)."""
    return zlib.crc32(f"{seed}:{actor_id}".encode())


def make_actor_rng(seed: int, actor_id: str) -> random.Random:
    """Un `random.Random` propio por actor (ADR 003 secc. 7): agregar un
    actor nuevo no consume RNG de los demas, y quitar uno tampoco lo
    desplaza (cada semilla depende solo de `(seed, actor_id)`)."""
    return random.Random(actor_seed(seed, actor_id))


def ideological_fit(
    delta: dict[str, float], actor: ActorSheet, signatures: dict[str, dict[str, float]]
) -> float:
    """`fit = 100 * cos_sim(signature(delta), actor.ideology) *
    min(1, |delta|/5)` (ADR 003 secc. 6.1). `|delta|` = norma L1 de los
    instrumentos tocados (no hay una unica "magnitud" cuando la propuesta
    toca mas de un instrumento; se documenta como suma de valores absolutos)."""
    if not delta:
        return 0.0
    vec = [0.0, 0.0, 0.0, 0.0]
    magnitude = 0.0
    scales = signatures.get("scales", {})
    for instrument, d in delta.items():
        sig = signatures.get(instrument)
        if sig is None or instrument == "scales" or d == 0.0:
            continue
        dn = d / float(scales.get(instrument, 5.0))  # delta normalizado por instrumento
        vec[0] += dn * sig["economic"]
        vec[1] += dn * sig["social"]
        vec[2] += dn * sig["federalism"]
        vec[3] += dn * sig["institutionalism"]
        magnitude += abs(dn)
    if magnitude == 0.0:
        return 0.0
    # Proyeccion de la ideologia sobre la direccion de la firma: un actor tibio
    # (economic 0.2) no puede tener fit +-100 ante un cambio chico (ADR 003 secc. 6.1,
    # revision v0.3: antes era coseno puro y saturaba en +-100).
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return 0.0
    unit = tuple(x / norm for x in vec)
    proj = sum(u * i for u, i in zip(unit, actor.ideology.as_vector(), strict=True))
    scale = min(1.0, magnitude)
    return max(-100.0, min(100.0, 100.0 * proj * scale))


def economic_policy_direction(
    delta: dict[str, float], signatures: dict[str, dict[str, float]]
) -> float:
    """`policy_direction ∈ [-1, 1]` (ADR 005 secc. 3): componente economico
    de la firma de `delta` (mismo calculo de `dn`/`sig["economic"]` que
    `ideological_fit`, sin proyectar sobre la ideologia de ningun actor en
    particular -- es "la" direccion economica del mes, no cuanto le gusta a
    alguien), acotado a `[-1, 1]`."""
    if not delta:
        return 0.0
    scales = signatures.get("scales", {})
    total = 0.0
    for instrument, d in delta.items():
        sig = signatures.get(instrument)
        if sig is None or instrument == "scales" or d == 0.0:
            continue
        dn = d / float(scales.get(instrument, 5.0))
        total += dn * sig["economic"]
    return clamp(total, -1.0, 1.0)


def _impact_provincial_transfers(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return cfg["coef"] * delta.get("provincial_transfers", 0.0) * dependence


def _impact_agricultural_exports(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    devaluation_proxy = -delta.get("fx_intervention", 0.0)
    return cfg["coef_tax"] * delta.get("tax_rate", 0.0) + cfg["coef_fx"] * devaluation_proxy


def _impact_real_wages(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return cfg["coef_infl"] * pos(ind.get("inflation", 0.0) - 2.0)


def _impact_employment(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    proxy = cfg["unemployment_elasticity_spending"] * delta.get("primary_spending", 0.0) + cfg[
        "unemployment_elasticity_rate"
    ] * delta.get("interest_rate_target", 0.0)
    return cfg["coef"] * proxy


def _impact_price_stability(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return (
        cfg["coef_infl"] * pos(ind.get("inflation", 0.0) - 2.0)
        + cfg["coef_rate"] * delta.get("interest_rate_target", 0.0) / 5.0
    )


def _impact_fiscal_balance(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return cfg["coef"] * (delta.get("tax_rate", 0.0) - delta.get("primary_spending", 0.0))


def _impact_low_taxes(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return cfg["coef"] * delta.get("tax_rate", 0.0)


def _impact_cheap_credit(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return cfg["coef"] * delta.get("interest_rate_target", 0.0) / 5.0


def _impact_public_employment(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    d = delta.get("primary_spending", 0.0)
    return cfg["coef"] * d if d < 0.0 else 0.0


def _impact_reelection(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    sign = 1.0 if in_gov else -1.0
    return sign * cfg["coef"] * (ind.get("government_approval", 50.0) - 50.0)


def _impact_audience(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    # ADR: "+10*|Delta_aprobacion|"; sin el mes anterior a mano se usa
    # |aprobacion - 50| /10 como proxy de "cuanto hay para contar" (ver
    # Notas de implementacion).
    return cfg["coef"] * abs(ind.get("government_approval", 50.0) - 50.0) / 10.0


def _impact_social_programs(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return cfg["coef"] * delta.get("primary_spending", 0.0)


def _impact_industrial_protection(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return cfg["coef_tax"] * (-delta.get("tax_rate", 0.0)) + cfg["coef_fx"] * (
        -delta.get("fx_intervention", 0.0)
    )


def _impact_financial_stability(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    volatility = abs(delta.get("interest_rate_target", 0.0))
    return (
        cfg["coef_infl"] * pos(ind.get("inflation", 0.0) - 2.0)
        + cfg["coef_vol"] * volatility / 10.0
    )


def _impact_law_and_order(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    crime = ind.get("crime_perception", 50.0)
    protest = ind.get("protest_level", 15.0)
    return cfg["coef_crime"] * (crime - 50.0) + cfg["coef_protest"] * (protest - 15.0)


def _impact_party_unity(delta, ind, dependence, in_gov, cfg):  # noqa: ANN001, ARG001
    return cfg["coef"] * (ind.get("government_approval", 50.0) - 50.0)


_IMPACT_FUNCS = {
    "provincial_transfers": _impact_provincial_transfers,
    "agricultural_exports": _impact_agricultural_exports,
    "real_wages": _impact_real_wages,
    "employment": _impact_employment,
    "price_stability": _impact_price_stability,
    "fiscal_balance": _impact_fiscal_balance,
    "low_taxes": _impact_low_taxes,
    "cheap_credit": _impact_cheap_credit,
    "public_employment": _impact_public_employment,
    "reelection": _impact_reelection,
    "audience": _impact_audience,
    "social_programs": _impact_social_programs,
    "industrial_protection": _impact_industrial_protection,
    "financial_stability": _impact_financial_stability,
    "law_and_order": _impact_law_and_order,
    "party_unity": _impact_party_unity,
}


def interest_impact(
    actor: ActorSheet,
    delta: dict[str, float],
    indicators: dict[str, float],
    dependence: float,
    in_government: bool,
    interests_cfg: dict[str, dict[str, float]],
) -> float:
    """`interest_impact = mean` de los intereses del actor, recortado a
    [-100, 100] (ADR 003 secc. 6.2)."""
    if not actor.interests:
        return 0.0
    total = 0.0
    n = 0
    for interest in actor.interests:
        fn = _IMPACT_FUNCS.get(interest)
        if fn is None:
            continue
        total += fn(delta, indicators, dependence, in_government, interests_cfg.get(interest, {}))
        n += 1
    if n == 0:
        return 0.0
    return clamp(total / n, -100.0, 100.0)


def electoral_pressure_raw(
    in_government: bool | None, months_to_election: int, approval: float
) -> float:
    """Igual que `electoral_pressure`, pero sobre valores sueltos en vez de
    una `Perception` completa: la usa tambien `engine/congress.py` (ADR 005
    secc. 1.2) para puntuar un `Bill` sin tener que armar una `Perception`
    de partido para eso."""
    if in_government is None:
        return 0.0
    proximity = clamp(1.0 - months_to_election / 12.0, 0.0, 1.0)
    sign = 1.0 if in_government else -1.0
    return sign * proximity * (approval - 50.0)


def electoral_pressure(in_government: bool | None, perception: Perception) -> float:
    """No hay formula explicita en el ADR (solo el peso `w_elec`): se define
    como la presion de la aprobacion actual, creciente a medida que se
    acerca la eleccion (rampa en los ultimos 12 meses), con signo segun si
    el actor esta alineado con el gobierno (documentado en Notas de
    implementacion). Solo `governor`/`party` tienen una nocion clara de
    "en el gobierno"; el resto no siente presion electoral directa (0)."""
    approval = perception.public_indicators.get("government_approval", 50.0)
    return electoral_pressure_raw(in_government, perception.months_to_election, approval)


#: `w_mem` (ADR 006 secc. 1.3, literal): peso del termino de memoria sobre
#: `score` (`memory_score * 100`, ya escalado -- ver
#: `ai/memory.py::MemoryStore.score_term`, misma constante).
W_MEM = 0.15


@dataclass(frozen=True)
class ScoreBreakdown:
    ideo: float
    interest: float
    rel: float
    elec: float
    noise: float
    total: float
    #: Termino de memoria (ADR 006 secc. 1.3), `None` con `features.memory =
    #: False` -- `as_dict()` solo agrega la clave `"mem"` cuando no es
    #: `None`, para que el `score` de un `ActionRecord` con memoria apagada
    #: sea byte a byte identico al de antes de ADR 006 (ver golden hash
    #: test).
    mem: float | None = None

    def as_dict(self) -> dict[str, float]:
        out = {
            "ideo": round(self.ideo, 2),
            "int": round(self.interest, 2),
            "rel": round(self.rel, 2),
            "elec": round(self.elec, 2),
            "noise": round(self.noise, 2),
            "total": round(self.total, 2),
        }
        if self.mem is not None:
            out["mem"] = round(self.mem, 2)
        return out


def _in_government(actor: ActorSheet, parties_by_id: dict[str, Party]) -> bool | None:
    if actor.role == "governor":
        party = parties_by_id.get(actor.party or "")
        return party.in_government if party else False
    if actor.role == "party":
        party = parties_by_id.get(actor.id.removeprefix("party_"))
        return party.in_government if party else False
    return None


def compute_score(
    actor: ActorSheet,
    perception: Perception,
    parties_by_id: dict[str, Party],
    weights: dict[str, dict[str, float]],
    signatures: dict[str, dict[str, float]],
    interests_cfg: dict[str, dict[str, float]],
    rng: random.Random,
    memory_enabled: bool = False,
) -> ScoreBreakdown:
    """`score` de ADR 003 secc. 6, mas el termino de memoria de ADR 006
    secc. 1.3 (`w_mem`) cuando `memory_enabled`."""
    delta = perception.proposal.delta if perception.proposal else {}
    indicators = {**perception.public_indicators, **perception.private_indicators}
    dependence = perception.private_indicators.get("dependence", 0.5)
    in_gov = _in_government(actor, parties_by_id)

    ideo = ideological_fit(delta, actor, signatures)
    interest = interest_impact(actor, delta, indicators, dependence, bool(in_gov), interests_cfg)
    # `perception.relationships["president"]` ya es `trust_president` en vez
    # del valor crudo de `Relationships` cuando `features.memory` esta
    # activo (`engine/perception.py::build_perception`, ADR 006 secc. 1.3):
    # este termino no cambia de formula, solo de input.
    rel_president = perception.relationships.get("president", 50)
    rel = (rel_president - 50) * 2.0
    elec = electoral_pressure(in_gov, perception)
    sigma = 5.0 * (1.0 - actor.personality.pragmatism)
    noise_val = rng.gauss(0.0, sigma) if sigma > 0.0 else 0.0

    w = weights.get(actor.role, weights["default"])
    mem_term = W_MEM * perception.memory_score * 100.0 if memory_enabled else None
    total = (
        w["w_ideo"] * ideo
        + w["w_int"] * interest
        + w["w_rel"] * rel
        + w["w_elec"] * elec
        + noise_val
        + (mem_term or 0.0)
    )
    return ScoreBreakdown(
        ideo=ideo,
        interest=interest,
        rel=rel,
        elec=elec,
        noise=noise_val,
        total=total,
        mem=mem_term,
    )


def _reason_text(actor: ActorSheet, score: ScoreBreakdown, perception: Perception) -> str:
    label = perception.proposal.label if perception.proposal else "sin propuesta"
    return (
        f"score={score.total:.1f} (ideo={score.ideo:.0f}, int={score.interest:.0f}, "
        f"rel={score.rel:.0f}, elec={score.elec:.0f}) ante '{label}'"
    )


def _escalate(actor: ActorSheet, intensity: float, reason: str) -> list[Action]:
    """Escalada (ADR 003 secc. 6, solo si `OPPOSE`)."""
    role = actor.role
    if role == "union":
        days = max(1, round(intensity * 5))
        return [
            Action(
                type=ActionType.STRIKE,
                actor_id=actor.id,
                params={"sector": "general", "days": days},
                reason=reason,
            )
        ]
    if role == "social_bloc":
        return [
            Action(
                type=ActionType.CALL_PROTEST,
                actor_id=actor.id,
                params={"intensity": intensity},
                reason=reason,
            )
        ]
    if role == "governor":
        return [
            Action(
                type=ActionType.LOBBY_CONGRESS,
                actor_id=actor.id,
                params={"direction": "against", "intensity": intensity},
                reason=reason,
            ),
            Action(
                type=ActionType.REQUEST_FUNDS,
                actor_id=actor.id,
                target="president",
                params={"amount_pct_gdp": clamp(0.1 + 0.3 * intensity, 0.0, 1.0)},
                reason=reason,
            ),
        ]
    if role == "business":
        return [
            Action(
                type=ActionType.WITHHOLD_INVESTMENT,
                actor_id=actor.id,
                params={"intensity": intensity},
                reason=reason,
            )
        ]
    if role == "party":
        return [
            Action(
                type=ActionType.LOBBY_CONGRESS,
                actor_id=actor.id,
                params={"direction": "against", "intensity": intensity},
                reason=reason,
            )
        ]
    return []


class RuleBasedActor:
    """`decide(perception, rng) -> list[Action]` (ADR 003 secc. 6)."""

    def __init__(
        self,
        sheet: ActorSheet,
        parties: list[Party],
        taylor: TaylorParams,
        r_neutral: float,
        rate_range: tuple[float, float],
        weights: dict[str, dict[str, float]] | None = None,
        signatures: dict[str, dict[str, float]] | None = None,
        interests_cfg: dict[str, dict[str, float]] | None = None,
        governance: Governance | None = None,
        memory_enabled: bool = False,
    ) -> None:
        self.sheet = sheet
        self.parties_by_id = {p.id: p for p in parties}
        self.taylor = taylor
        self.r_neutral = r_neutral
        self.rate_range = rate_range
        self.weights = weights if weights is not None else load_weights()
        self.signatures = signatures if signatures is not None else load_signatures()
        self.interests_cfg = interests_cfg if interests_cfg is not None else load_interests_config()
        self.governance = governance if governance is not None else load_governance()
        #: ADR 006 secc. 1.3 (default `False`, mismo criterio que el resto
        #: de las features de ADR 005/006): si `w_mem`/`trust_president`
        #: estan activos para este actor.
        self.memory_enabled = memory_enabled
        #: Ultimo `ScoreBreakdown` calculado por `_decide_generic` (`None`
        #: para medios/banco central, que no puntuan propuestas: secc. 6.3/
        #: 6.4). Efecto de lado leido por `engine/scheduler.py` para el
        #: campo `score` del `ActionRecord` (ADR 003 secc. 8) sin cambiar la
        #: firma de `decide()` (fijada por el ADR): ver Notas de
        #: implementacion.
        self.last_score: ScoreBreakdown | None = None
        #: `{concesion: mes_hasta_el_que_esta_en_cooldown}` (hallazgo #5),
        #: poblado por `note_concession_granted` (`engine/scheduler.py`,
        #: cuando este actor recibe un `GRANT_CONCESSION` autorizado).
        self._concession_cooldowns: dict[str, int] = {}

    def note_concession_granted(self, concession: str, month: int) -> None:
        """Llamado por `engine/scheduler.py::run_actor_turn` cuando este
        actor recibe un `GRANT_CONCESSION` este `month`: bloquea `NEGOTIATE`
        por la misma `concession` los proximos `CONCESSION_COOLDOWN_MONTHS`
        meses (hallazgo #5 de REVIEW_001)."""
        self._concession_cooldowns[concession] = month + CONCESSION_COOLDOWN_MONTHS

    def decide(self, perception: Perception, rng: random.Random) -> list[Action]:
        role = self.sheet.role
        self.last_score = None
        if role == "media":
            return self._decide_media(perception)
        if role == "central_bank":
            return self._decide_central_bank(perception)
        return self._decide_generic(perception, rng)

    # -- 6: score generico -------------------------------------------------
    def _decide_generic(self, perception: Perception, rng: random.Random) -> list[Action]:
        actor = self.sheet
        score = compute_score(
            actor,
            perception,
            self.parties_by_id,
            self.weights,
            self.signatures,
            self.interests_cfg,
            rng,
            memory_enabled=self.memory_enabled,
        )
        self.last_score = score
        intensity = min(1.0, abs(score.total) / INTENSITY_SCALE)
        reason = _reason_text(actor, score, perception)
        actions: list[Action] = []

        if score.total > SUPPORT_THRESHOLD:
            stance = "support"
            actions.append(
                Action(
                    type=ActionType.SUPPORT_POLICY,
                    actor_id=actor.id,
                    params={"intensity": intensity},
                    reason=reason,
                )
            )
        elif score.total < OPPOSE_THRESHOLD:
            stance = "oppose"
            actions.append(
                Action(
                    type=ActionType.OPPOSE_POLICY,
                    actor_id=actor.id,
                    params={"intensity": intensity},
                    reason=reason,
                )
            )
            if rng.random() < actor.personality.risk_tolerance * intensity:
                actions.extend(_escalate(actor, intensity, reason))
        else:
            stance = "neutral"
            concession = _NEGOTIATE_CONCESSION.get(actor.role, ConcessionType.DELAY_POLICY)
            cooldown_until = self._concession_cooldowns.get(concession.value, -1)
            if (
                actor.role in NEGOTIATE_CAPABLE_ROLES
                and perception.proposal is not None
                and perception.proposal.delta
                and abs(score.total) >= NEGOTIATE_MIN_ABS_SCORE
                and perception.month >= cooldown_until
            ):
                actions.append(
                    Action(
                        type=ActionType.NEGOTIATE,
                        actor_id=actor.id,
                        target="president",
                        params={"requested_concession": concession, "offer": "apoyo condicionado"},
                        reason=reason,
                    )
                )
            else:
                actions.append(Action(type=ActionType.NO_ACTION, actor_id=actor.id, reason=reason))

        if intensity >= STATEMENT_MIN_INTENSITY and (
            actor.personality.ambition > 0.5 or intensity > 0.6
        ):
            actions.append(
                Action(
                    type=ActionType.PUBLIC_STATEMENT,
                    actor_id=actor.id,
                    params={"stance": stance, "intensity": intensity},
                    reason=reason,
                )
            )

        # Presupuesto de acciones por turno (hallazgo #11 de REVIEW_001,
        # ADR 003 secc. 4/9: max 3 por actor): un `governor` que se opone y
        # escala emite 4 (OPPOSE_POLICY + LOBBY_CONGRESS + REQUEST_FUNDS de
        # `_escalate` + PUBLIC_STATEMENT), y antes la 4a se perdia en
        # `authorize()` por puro orden de llegada. El actor elige que gasta:
        # descarta primero el `PUBLIC_STATEMENT` (el gesto, no la sustancia)
        # y, si todavia sobra, la ultima accion de la escalada (la mas
        # debil: `_escalate` agrega la principal primero).
        if len(actions) > ACTION_BUDGET_PER_TURN:
            actions = [a for a in actions if a.type is not ActionType.PUBLIC_STATEMENT]
            while len(actions) > ACTION_BUDGET_PER_TURN:
                actions.pop()
        return actions

    # -- 6.3: medios ---------------------------------------------------
    def _decide_media(self, perception: Perception) -> list[Action]:
        actor = self.sheet
        approval = perception.public_indicators.get("government_approval", 50.0)
        inflation = perception.public_indicators.get("inflation", 0.0)
        gdp_growth = perception.public_indicators.get("gdp_growth", 0.0)
        # Hallazgo #3 de REVIEW_001: `recent_events` (los `events` del
        # `MonthRecord` del mes pasado) nunca contiene ids de shocks -- ahi
        # solo caen `forced_devaluation`/`term_end:*`. El id de un shock
        # (p.ej. `corruption_scandal`) esta en `active_shocks`, que desde el
        # fix de `engine/simulation.py::advance_month` ya incluye los
        # `shocks_new` de este mismo mes (antes se perdian: duran 1 mes y se
        # borran de `sim.active_shocks` el mismo mes en que se sortean).
        scandal = any(
            "scandal" in e or "corruption" in e
            for e in (*perception.recent_events, *perception.active_shocks)
        )

        gov_party = next((p for p in self.parties_by_id.values() if p.in_government), None)
        # Distancia ideologica al gobierno (hallazgo #4): un medio mas lejos
        # (en cualquier direccion) es mas critico -- ve crisis mas facil, ve
        # recuperacion mas dificil. `0.0` (sin partido de gobierno resuelto,
        # no deberia pasar con `country.json` real) deja los umbrales base.
        distance = abs(actor.ideology.economic - gov_party.economic) if gov_party else 0.0
        crisis_approval = MEDIA_CRISIS_APPROVAL_BASE + distance * MEDIA_BIAS_APPROVAL_COEF
        crisis_inflation = max(
            0.5, MEDIA_CRISIS_INFLATION_BASE - distance * MEDIA_BIAS_INFLATION_COEF
        )
        recovery_growth = MEDIA_RECOVERY_GROWTH_BASE + distance * MEDIA_BIAS_GROWTH_COEF

        if scandal:
            frame = "scandal"
        elif approval < crisis_approval or inflation > crisis_inflation:
            # "si Delta_aprobacion < -2": sin el mes anterior a mano se usa
            # aprobacion < umbral (desplazado por sesgo) como proxy (ver
            # Notas de implementacion).
            frame = "crisis"
        elif gdp_growth > recovery_growth:
            frame = "recovery"
        else:
            frame = "neutral"

        reason = (
            f"linea editorial (economic={actor.ideology.economic:+.1f}) ante "
            f"aprobacion {approval:.0f}, inflacion {inflation:.1f}, PIB {gdp_growth:.1f}"
        )
        target = "president" if frame == "scandal" else None
        actions = [
            Action(
                type=ActionType.PUBLISH_STORY,
                actor_id=actor.id,
                target=target,
                params={"frame": frame, "target_bloc": "all"},
                reason=reason,
            )
        ]
        rel_president = perception.relationships.get("president", 50)
        if rel_president >= 60:
            actions.append(
                Action(
                    type=ActionType.ENDORSE,
                    actor_id=actor.id,
                    params={"target": "president"},
                    reason=reason,
                )
            )
        elif rel_president <= 40:
            actions.append(
                Action(
                    type=ActionType.CRITICIZE,
                    actor_id=actor.id,
                    params={"target": "president"},
                    reason=reason,
                )
            )
        return actions

    # -- 6.4: banco central ----------------------------------------------
    def _decide_central_bank(self, perception: Perception) -> list[Action]:
        actor = self.sheet
        pi = perception.public_indicators.get("inflation", 0.0)
        current_rate = perception.private_indicators.get("interest_rate", 30.0)
        proposed_delta = (
            perception.proposal.delta.get("interest_rate_target", 0.0)
            if perception.proposal
            else 0.0
        )
        proposed_rate = current_rate + proposed_delta

        taylor_target = (
            self.r_neutral
            + self.taylor.pi_coef * pi
            + self.taylor.response * self.taylor.pi_coef * (pi - self.taylor.pi_target)
        )
        taylor_target = clamp(taylor_target, *self.rate_range)
        delta_pp = clamp(taylor_target - proposed_rate, -20.0, 20.0)

        reason = (
            f"regla de Taylor sugiere {taylor_target:.1f} % vs. propuesta {proposed_rate:.1f} %"
        )
        if abs(delta_pp) < 0.5:
            return [Action(type=ActionType.NO_ACTION, actor_id=actor.id, reason=reason)]

        actions = [
            Action(
                type=ActionType.RECOMMEND_RATE,
                actor_id=actor.id,
                params={"delta_pp": delta_pp},
                reason=reason,
            )
        ]
        if self.governance.central_bank_autonomy >= 3:
            actions.append(
                Action(
                    type=ActionType.SET_RATE,
                    actor_id=actor.id,
                    params={"delta_pp": delta_pp},
                    reason=reason,
                )
            )
        return actions
