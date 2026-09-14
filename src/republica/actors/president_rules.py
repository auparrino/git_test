"""Presidente por reglas para `republica run` (ADR 003 secc. 6 parrafo final,
secc. 7 paso 2): envuelve la `PolicyRule` de Fase 1 en una `PolicyProposal`
(delta + etiqueta) y decide que pedidos pendientes (`REQUEST_FUNDS`/
`NEGOTIATE` del mes anterior) conceder. Regla simple: la negociacion
completa (multironda) es Fase 5."""

from __future__ import annotations

from dataclasses import dataclass, field

from republica.engine.actions import Action, ActionType, ConcessionType
from republica.engine.consequences import Relationships, load_concessions
from republica.engine.perception import PolicyProposal
from republica.engine.policy import PolicyRule
from republica.world.state import Policy, WorldState, clamp

#: Presupuesto fiscal mensual para conceder pedidos (ADR 003 secc. 6: "regla
#: simple") en pp de PIB. Valor inventado para v0.3, del mismo orden que
#: `deficit > 5` (umbral de alarma del consejero, SPEC_v0.2 secc. 3): 0.8 pp
#: deja margen para una concesion cara (`public_works`, 0.8) o un par de
#: baratas por mes, sin descontrolar el fiscal.
MONTHLY_FISCAL_BUDGET_PCT_GDP = 0.8

#: Umbral de relacion para conceder (ADR 003 secc. 6, literal: "si
#: relationships con el solicitante son >= 55").
GRANT_RELATIONSHIP_THRESHOLD = 55


def _label_for_delta(delta: dict[str, float]) -> str:
    if not delta:
        return "sin cambios de politica"
    parts = [f"{k} {v:+.1f}" for k, v in delta.items() if abs(v) > 1e-9]
    return "; ".join(parts) if parts else "sin cambios de politica"


def compute_policy_proposal(current: Policy, previous: Policy) -> PolicyProposal:
    """`PolicyProposal` = delta de `current` vs. `previous` (ADR 003 secc. 3),
    etiquetada. Vale tanto para el presidente por reglas (`decide_policy`)
    como para el humano de `play` (`engine/simulation.py::advance_month`
    la llama con la `Policy` que decidio el jugador, para que los actores
    vean la misma nocion de "propuesta" en run y en play)."""
    cur = current.model_dump()
    prev = previous.model_dump()
    delta = {
        name: value - prev[name] for name, value in cur.items() if abs(value - prev[name]) > 1e-9
    }
    return PolicyProposal(delta=delta, label=_label_for_delta(delta))


def apply_pending_policy_delta(
    policy: Policy, pending: dict[str, float], ranges: dict[str, tuple[float, float]]
) -> Policy:
    """Aplica los terminos `policy_*` pendientes (ADR 003 secc. 5:
    `GRANT_CONCESSION`/`SET_RATE` que tocan un instrumento de `Policy`) al
    mes siguiente, recortados a su rango (ver Notas de implementacion de
    ADR 003: estos terminos no pasan por `shock_*`, son un ajuste directo)."""
    if not pending:
        return policy
    updates = policy.model_dump()
    for field_name, delta in pending.items():
        if field_name not in updates:
            continue
        lo, hi = ranges[field_name]
        updates[field_name] = clamp(updates[field_name] + delta, lo, hi)
    return policy.model_copy(update=updates)


def concession_for_request(action: Action) -> ConcessionType:
    """El ADR no aclara que `ConcessionType` otorga un `REQUEST_FUNDS` (solo
    trae `amount_pct_gdp`, sin tipo de concesion): se usa `restore_transfers`
    (la concesion "por defecto" para un gobernador que pide fondos). Un
    `NEGOTIATE` ya trae su propia `requested_concession` explicita, y se
    respeta (documentado en Notas de implementacion)."""
    if action.type is ActionType.NEGOTIATE:
        return ConcessionType(action.params["requested_concession"])
    return ConcessionType.RESTORE_TRANSFERS


@dataclass
class RuleBasedPresident:
    """Presidente por reglas de `run` (ADR 003 secc. 6): la `Policy` la
    sigue fijando la `PolicyRule` de Fase 1 (constant/passive/taylor); esto
    solo la envuelve en una `PolicyProposal` y decide concesiones."""

    policy_rule: PolicyRule
    concessions: dict = field(default_factory=load_concessions)

    def decide_policy(
        self, state: WorldState, month: int, current_policy: Policy
    ) -> tuple[Policy, PolicyProposal]:
        """`Policy` del mes (de la `PolicyRule`) + `PolicyProposal` (delta
        vs. `current_policy`, etiquetada)."""
        proposed = self.policy_rule.decide(state, month)
        return proposed, compute_policy_proposal(proposed, current_policy)

    def decide_grants(
        self, pending_requests: list[Action], relationships: Relationships
    ) -> list[Action]:
        """Concede pedidos del mes anterior con `relationships[solicitante][president]
        >= 55` cuyo costo fiscal entra en el presupuesto mensual de
        `MONTHLY_FISCAL_BUDGET_PCT_GDP` (orden de llegada; regla simple)."""
        budget_left = MONTHLY_FISCAL_BUDGET_PCT_GDP
        grants: list[Action] = []
        for req in pending_requests:
            if relationships.get(req.actor_id, "president") < GRANT_RELATIONSHIP_THRESHOLD:
                continue
            concession = concession_for_request(req)
            cost = self.concessions[concession.value]["fiscal_cost_pct_gdp"]
            if cost > budget_left + 1e-9:
                continue
            budget_left -= cost
            grants.append(
                Action(
                    type=ActionType.GRANT_CONCESSION,
                    actor_id="president",
                    target=req.actor_id,
                    params={"to": req.actor_id, "concession": concession.value},
                    reason=(
                        f"conceder a {req.actor_id}: relacion >= {GRANT_RELATIONSHIP_THRESHOLD}, "
                        f"costo {cost:.2f} pp PIB entra en presupuesto mensual"
                    ),
                )
            )
        return grants
