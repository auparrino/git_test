"""Reglas de politica (seccion 2.3 del spec): `PolicyRule.decide(state, month) -> Policy`."""

from __future__ import annotations

from typing import Protocol

from republica.world.config import TaylorParams
from republica.world.state import Policy, WorldState, clamp


class PolicyRule(Protocol):
    def decide(self, state: WorldState, month: int) -> Policy: ...


class ConstantPolicy:
    """Default de v0.1: no hacer nada, repetir siempre la politica default."""

    def __init__(self, default_policy: Policy):
        self._default = default_policy

    def decide(self, state: WorldState, month: int) -> Policy:
        return self._default.model_copy()


class PassivePolicy:
    """Baseline de referencia: el Banco Central sigue a la inflacion del mes anterior
    manteniendo la tasa real en `r_neutral + spread`. No reacciona de mas ni de menos:
    es "no hacer nada" en terminos reales, no nominales.
    """

    def __init__(
        self,
        default_policy: Policy,
        r_neutral: float,
        rate_range: tuple[float, float],
        spread: float = 2.0,
    ):
        self._default = default_policy
        self._r_neutral = r_neutral
        self._rate_range = rate_range
        self._spread = spread

    def decide(self, state: WorldState, month: int) -> Policy:
        target = self._r_neutral + self._spread + 12.0 * state.inflation_lag1
        lo, hi = self._rate_range
        return self._default.model_copy(update={"interest_rate_target": clamp(target, lo, hi)})


class TaylorPolicy:
    """`interest_rate_target = r_neutral + 12*pi + 1.5*12*(pi - 0.8)` (seccion 2.3),
    con `pi` mensual y recortado al rango de politica. El resto de los
    instrumentos queda en su valor default.
    """

    def __init__(
        self,
        default_policy: Policy,
        taylor: TaylorParams,
        r_neutral: float,
        rate_range: tuple[float, float],
    ):
        self._default = default_policy
        self._taylor = taylor
        self._r_neutral = r_neutral
        self._rate_range = rate_range

    def decide(self, state: WorldState, month: int) -> Policy:
        target = (
            self._r_neutral
            + self._taylor.pi_coef * state.inflation
            + self._taylor.response
            * self._taylor.pi_coef
            * (state.inflation - self._taylor.pi_target)
        )
        lo, hi = self._rate_range
        target = clamp(target, lo, hi)
        return self._default.model_copy(update={"interest_rate_target": target})
