"""Consejero por reglas (SPEC_v0.2_play.md secc. 3)."""

from __future__ import annotations

from dataclasses import dataclass

from republica.engine.dilemmas import AuxVars
from republica.engine.policy import TaylorPolicy
from republica.world.config import Country
from republica.world.state import Policy, WorldState

#: Diferencia de tasa (pp) contra la regla de Taylor a partir de la cual el
#: Banco Central recomienda un cambio (seccion 3).
TAYLOR_GAP_THRESHOLD = 10.0


@dataclass(frozen=True)
class Advice:
    """Una linea del consejero: `severity` es "info" | "warning" | "alert"."""

    source: str
    text: str
    severity: str = "info"


def _central_bank(state: WorldState, policy: Policy, country: Country) -> Advice | None:
    taylor = TaylorPolicy(
        country.default_policy,
        country.taylor,
        country.structure.r_neutral,
        country.policy_ranges["interest_rate_target"],
    )
    target = taylor.decide(state, month=0).interest_rate_target
    gap = policy.interest_rate_target - target
    if abs(gap) <= TAYLOR_GAP_THRESHOLD:
        return None
    accion = "bajar" if gap > 0 else "subir"
    return Advice(
        source="Banco Central",
        text=(
            f"La tasa de referencia ({policy.interest_rate_target:.1f}) se aleja mas de "
            f"{TAYLOR_GAP_THRESHOLD:.0f} pp de la que recomienda la regla de Taylor "
            f"({target:.1f}); convendria {accion}la."
        ),
        severity="warning",
    )


def _economy_minister(state: WorldState, aux: AuxVars) -> list[Advice]:
    advice: list[Advice] = []
    if aux.deficit > 5.0:
        advice.append(
            Advice(
                "Ministro de Economia",
                f"El deficit primario ({aux.deficit:.1f} % del PIB) es insostenible en el tiempo.",
                "warning",
            )
        )
    if state.public_debt > 90.0:
        advice.append(
            Advice(
                "Ministro de Economia",
                f"La deuda publica llego a {state.public_debt:.0f} % del PIB.",
                "alert",
            )
        )
    if state.reserves < 3000.0:
        advice.append(
            Advice(
                "Ministro de Economia",
                f"Las reservas cayeron a USD {state.reserves:.0f} M, el riesgo de "
                "devaluacion forzada es alto.",
                "alert",
            )
        )
    return advice


def _chief_of_staff(state: WorldState) -> list[Advice]:
    advice: list[Advice] = []
    if state.government_approval < 35.0:
        advice.append(
            Advice(
                "Jefe de Gabinete",
                f"La aprobacion esta en {state.government_approval:.0f}, muy debil para "
                "sostener la agenda legislativa.",
                "warning",
            )
        )
    if state.political_stability < 30.0:
        advice.append(
            Advice(
                "Jefe de Gabinete",
                f"La estabilidad politica ({state.political_stability:.0f}) esta al borde "
                "del colapso.",
                "alert",
            )
        )
    if state.protest_level > 50.0:
        advice.append(
            Advice(
                "Jefe de Gabinete",
                f"La conflictividad social ({state.protest_level:.0f}) es muy alta.",
                "warning",
            )
        )
    return advice


def _governors(policy: Policy) -> Advice | None:
    if policy.provincial_transfers < 5.0:
        return Advice(
            "Gobernadores",
            f"Las transferencias a provincias ({policy.provincial_transfers:.1f} % del PIB) "
            "son insuficientes; amenazan con retirar apoyo legislativo.",
            "warning",
        )
    return None


def advise(state: WorldState, aux: AuxVars, policy: Policy, country: Country) -> list[Advice]:
    """Devuelve las recomendaciones/advertencias activas este mes (seccion 3):
    Banco Central (regla de Taylor), Ministro de Economia (deficit/deuda/
    reservas), Jefe de Gabinete (aprobacion/estabilidad/protesta) y
    Gobernadores (transferencias)."""
    advice: list[Advice] = []
    cb = _central_bank(state, policy, country)
    if cb is not None:
        advice.append(cb)
    advice.extend(_economy_minister(state, aux))
    advice.extend(_chief_of_staff(state))
    governors = _governors(policy)
    if governors is not None:
        advice.append(governors)
    return advice
