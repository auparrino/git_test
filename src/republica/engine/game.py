"""Modo juego (SPEC_v0.2_play.md secc. 1 y 4): envuelve `Simulation` con el
estado propio de una partida interactiva (dilemas disparados, flags,
cooldowns, decisiones tomadas) y sabe guardarse/recargarse."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from republica.actors.president_rules import concession_for_request
from republica.engine.actions import Action, ActionType
from republica.engine.dilemmas import (
    Dilemma,
    PendingEffect,
    apply_option,
    compute_aux_vars,
    evaluate_triggers,
)
from republica.engine.policy import PassivePolicy, PolicyRule
from republica.engine.simulation import (
    History,
    MonthRecord,
    Simulation,
    advance_month,
    new_simulation,
)
from republica.engine.simulation import run as run_simulation
from republica.world.config import Country, load_country
from republica.world.state import Policy, WorldState, clamp

#: Topes de cambio mensual por instrumento (seccion 1, paso 3): tasa +-15pp,
#: gasto/impuestos/transferencias +-2pp de PIB. `fx_intervention` no tiene
#: tope mensual ("intervencion libre"), solo el rango absoluto [0, 1].
CAPPED_INSTRUMENTS: dict[str, float] = {
    "interest_rate_target": 15.0,
    "tax_rate": 2.0,
    "primary_spending": 2.0,
    "provincial_transfers": 2.0,
}
#: Igual que `CAPPED_INSTRUMENTS` pero incluye `fx_intervention` con tope
#: `None` (sin limite), pensado para mostrarle el tope al jugador en la CLI.
MONTHLY_CAPS: dict[str, float | None] = {**CAPPED_INSTRUMENTS, "fx_intervention": None}


def _apply_monthly_caps(
    baseline: Policy, proposed: Policy, ranges: dict[str, tuple[float, float]]
) -> tuple[Policy, dict[str, tuple[float, float]]]:
    """Recorta el cambio de `baseline` a `proposed` en cada instrumento
    limitado (seccion 1, paso 3) y despues aplica el rango absoluto de cada
    instrumento (seccion 2.3 del SPEC_v0.1). Devuelve la `Policy` final y un
    reporte `{instrumento: (delta_pedido, delta_aplicado)}` solo con los
    instrumentos efectivamente recortados.
    """
    base = baseline.model_dump()
    proposed_values = proposed.model_dump()
    clip_report: dict[str, tuple[float, float]] = {}
    result = dict(proposed_values)
    for field_name, cap in CAPPED_INSTRUMENTS.items():
        requested = proposed_values[field_name] - base[field_name]
        applied = clamp(requested, -cap, cap)
        if abs(applied - requested) > 1e-9:
            clip_report[field_name] = (requested, applied)
        result[field_name] = base[field_name] + applied
    for field_name, (lo, hi) in ranges.items():
        result[field_name] = clamp(result[field_name], lo, hi)
    return Policy(**result), clip_report


class _MutablePolicyRule:
    """`PolicyRule` que devuelve siempre la ultima `Policy` que fijo el
    juego: permite reusar `Simulation`/`advance_month` (Fase 1) desde el loop
    interactivo sin duplicar el motor."""

    def __init__(self, initial: Policy) -> None:
        self.policy = initial

    def decide(self, state: WorldState, month: int) -> Policy:  # noqa: ARG002
        return self.policy.model_copy()


@dataclass
class Game:
    """Una partida en curso: `Simulation` + estado del modo juego."""

    country: Country
    seed: int
    sim: Simulation
    policy: Policy
    flags: dict[str, bool] = field(default_factory=dict)
    cooldowns: dict[str, float] = field(default_factory=dict)
    pending_effects: list[PendingEffect] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    instrument_edit_log: list[dict[str, Any]] = field(default_factory=list)
    pending_dilemmas: list[Dilemma] = field(default_factory=list)
    clip_report: dict[str, tuple[float, float]] = field(default_factory=dict)
    shocks_enabled: bool = True
    actors_enabled: bool = False
    grant_decision_log: list[dict[str, Any]] = field(default_factory=list)
    _rule: _MutablePolicyRule | None = field(default=None, repr=False)

    @classmethod
    def new(
        cls,
        seed: int,
        months: int = 48,
        country: Country | None = None,
        shocks_enabled: bool = True,
        actors_enabled: bool = False,
        brain_map: dict[str, str] | None = None,
        default_brain: str = "rules",
        llm_temperature: float = 0.4,
        llm_cache_dir: str | None = None,
    ) -> Game:
        """Arranca una partida nueva en el mes 0 (antes de jugar el mes 1).

        `actors_enabled` (default `False`, deliverable 8 de ADR 003): prende
        los 29 actores por reglas en `play` sin presidente por reglas (el
        presidente es el jugador humano: `sim.president_rule` queda `None`,
        ver `engine/simulation.py::advance_month`). Default apagado para no
        romper `tests/test_play_cli.py` (que verifica exactamente 49 lineas
        de JSONL sin flags nuevos): ver Notas de implementacion.

        `brain_map`/`default_brain`/`llm_temperature`/`llm_cache_dir` (ADR
        004 secc. 7): idem `engine.simulation.new_simulation`, default
        `"rules"` para todos."""
        base_country = (country or load_country()).model_copy(update={"months": months})
        rule = _MutablePolicyRule(base_country.default_policy.model_copy())
        sim = new_simulation(
            seed,
            rule,
            None,
            base_country,
            shocks_enabled,
            True,
            actors_enabled=actors_enabled,
            brain_map=brain_map,
            default_brain=default_brain,
            llm_temperature=llm_temperature,
            llm_cache_dir=llm_cache_dir,
        )
        game = cls(
            country=base_country,
            seed=seed,
            sim=sim,
            policy=rule.policy,
            shocks_enabled=shocks_enabled,
            actors_enabled=actors_enabled,
            _rule=rule,
        )
        game._refresh_pending_dilemmas()
        return game

    @property
    def pending_actor_requests(self) -> list:
        """`REQUEST_FUNDS`/`NEGOTIATE` del mes pasado, pendientes de que el
        jugador conceda o rechace este mes (deliverable 8: dilema generado
        "Conceder/Rechazar"). Vacio si `actors_enabled=False`."""
        if self.sim.actor_engine is None:
            return []
        return list(self.sim.actor_engine.pending_requests)

    def set_grant_decisions(self, granted_actor_ids: set[str]) -> None:
        """Fija que pedidos pendientes concede el jugador este mes (el resto
        se toma como rechazado: `relationships.president -1`, ver ADR 003
        secc. 5). Debe llamarse antes de `step()`."""
        grants = []
        for req in self.pending_actor_requests:
            if req.actor_id not in granted_actor_ids:
                continue
            concession = concession_for_request(req)
            grants.append(
                Action(
                    type=ActionType.GRANT_CONCESSION,
                    actor_id="president",
                    target=req.actor_id,
                    params={"to": req.actor_id, "concession": concession.value},
                    reason=f"el jugador concede a {req.actor_id}",
                )
            )
        self.sim.pending_grant_override = grants
        if self.pending_actor_requests:
            self.grant_decision_log.append(
                {"month": self.sim.month + 1, "granted": sorted(granted_actor_ids)}
            )

    def _refresh_pending_dilemmas(self) -> None:
        """Recalcula los dilemas disparados para el proximo mes a jugar
        (`sim.month + 1`), a partir del estado ya asentado de `sim`."""
        month = self.sim.month + 1
        aux = compute_aux_vars(self.sim.state, month, self.country.months)
        last_events = (
            [e.split(":")[0] for e in self.sim.records[-1].events] if self.sim.records else []
        )
        # Un shock de duracion 1 (p.ej. `corruption_scandal`) se borra de
        # `sim.active_shocks` en el mismo mes en que se sortea
        # (`ShockCatalog.apply_month`): sin sumar `shocks_new` del ultimo
        # `MonthRecord`, un trigger `shock_active:<id>` sobre uno de esos
        # nunca se cumplia -- `scandal_response`/`general_strike_response`/
        # `protest_wave_response` (REVIEW_001 hallazgo #2) no aparecian
        # nunca en 120 semillas.
        shocks_for_triggers = set(self.sim.active_shocks) | (
            set(self.sim.records[-1].shocks_new) if self.sim.records else set()
        )
        self.pending_dilemmas = evaluate_triggers(
            self.sim.state,
            aux,
            month,
            shocks_for_triggers,
            last_events,
            self.flags,
            self.cooldowns,
        )

    def _consume_pending_effects(self) -> dict[str, float]:
        """Suma este mes de cada efecto pendiente (nuevos y arrastrados) y
        descarta los que se agotan; devuelve `{termino: valor}` listo para
        sumar a `sim.pending_terms`."""
        terms: dict[str, float] = {}
        remaining: list[PendingEffect] = []
        for eff in self.pending_effects:
            terms[eff.term] = terms.get(eff.term, 0.0) + eff.value
            left = eff.remaining - 1
            if left > 0:
                remaining.append(replace(eff, remaining=left))
        self.pending_effects = remaining
        return terms

    def step(
        self,
        choices: dict[str, str] | None = None,
        instrument_edits: dict[str, float] | None = None,
    ) -> MonthRecord:
        """Juega un mes: aplica las opciones elegidas (`choices`, por id de
        dilema) y los ajustes manuales de instrumentos (`instrument_edits`,
        valores absolutos), recorta todo a los topes mensuales, y avanza el
        motor un mes (seccion 1, pasos 3-5)."""
        if self.sim.outcome is not None:
            raise RuntimeError("la partida ya termino")
        choices = choices or {}
        instrument_edits = instrument_edits or {}
        next_month = self.sim.month + 1

        baseline = self.policy.model_copy()
        working = self.policy
        for dilemma in self.pending_dilemmas:
            option_key = choices.get(dilemma.id)
            if option_key is None:
                continue
            option = next((o for o in dilemma.options if o.key == option_key), None)
            if option is None:
                raise ValueError(f"opcion {option_key!r} invalida para el dilema {dilemma.id!r}")
            working, self.pending_effects, self.flags = apply_option(
                option, working, self.pending_effects, self.flags
            )
            self.decisions.append(
                {"month": next_month, "dilemma_id": dilemma.id, "option": option_key}
            )

        if instrument_edits:
            updates = working.model_dump()
            updates.update(instrument_edits)
            working = working.model_copy(update=updates)
            self.instrument_edit_log.append({"month": next_month, "edits": dict(instrument_edits)})

        self.policy, self.clip_report = _apply_monthly_caps(
            baseline, working, self.country.policy_ranges
        )
        assert self._rule is not None
        self._rule.policy = self.policy

        for term, value in self._consume_pending_effects().items():
            self.sim.pending_terms[term] = self.sim.pending_terms.get(term, 0.0) + value

        record = advance_month(self.sim)
        self._refresh_pending_dilemmas()
        return record

    def save(self, path: str | Path) -> None:
        """Guarda la partida (seccion 4): `{seed, month, policy, flags,
        cooldowns, history_path, decisions}`. El historial completo se
        escribe aparte, en JSONL, al lado del save (mismo nombre, `.jsonl`),
        con el mismo formato que `republica run`/`narrate`. `instrument_edits`
        extiende el formato del spec: sin registrar los ajustes manuales de
        instrumentos, `--load` no podria reproducir una partida donde el
        jugador toco instrumentos a mano (ver "Notas de implementacion" en
        `docs/SPEC_v0.2_play.md`)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        history_path = path.with_suffix(".jsonl")
        history = History(
            records=self.sim.records,
            outcome=self.sim.outcome or "en_curso",
            seed=self.seed,
            config_hash=self.country.config_hash,
            action_records=self.sim.action_records,
        )
        history_path.write_text(history.to_jsonl(), encoding="utf-8")
        data = {
            "seed": self.seed,
            "month": self.sim.month,
            "months": self.country.months,
            "shocks_enabled": self.shocks_enabled,
            "actors_enabled": self.actors_enabled,
            "policy": self.policy.model_dump(),
            "flags": self.flags,
            "cooldowns": self.cooldowns,
            "history_path": str(history_path),
            "decisions": self.decisions,
            "instrument_edits": self.instrument_edit_log,
            "grant_decisions": self.grant_decision_log,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, country: Country | None = None) -> Game:
        """Reconstruye la partida re-ejecutando `decisions`/`instrument_edits`
        desde el mes 0 (seccion 4): determinista porque `Game.step` no usa
        mas azar que el de `sim.rng`, sembrado por `seed`."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        game = cls.new(
            seed=data["seed"],
            months=data.get("months", 48),
            country=country,
            shocks_enabled=data.get("shocks_enabled", True),
            actors_enabled=data.get("actors_enabled", False),
        )
        by_month: dict[int, dict[str, str]] = {}
        for dec in data["decisions"]:
            by_month.setdefault(dec["month"], {})[dec["dilemma_id"]] = dec["option"]
        edits_by_month: dict[int, dict[str, float]] = {
            e["month"]: e["edits"] for e in data.get("instrument_edits", [])
        }
        grants_by_month: dict[int, set[str]] = {
            g["month"]: set(g["granted"]) for g in data.get("grant_decisions", [])
        }
        target_month = data["month"]
        for m in range(1, target_month + 1):
            if game.pending_actor_requests:
                game.set_grant_decisions(grants_by_month.get(m, set()))
            game.step(by_month.get(m, {}), edits_by_month.get(m, {}))
        return game

    def counterfactual_impact(self) -> dict[str, Any]:
        """Corrida contrafactica de la misma semilla con `PassivePolicy` y
        sin decisiones (seccion 1, paso 6): diferencia de aprobacion final y,
        por mes de decision, el delta de aprobacion 3 meses despues contra el
        contrafactico (top 5 por |delta|)."""
        passive_rule: PolicyRule = PassivePolicy(
            self.country.default_policy,
            self.country.structure.r_neutral,
            self.country.policy_ranges["interest_rate_target"],
        )
        cf = run_simulation(
            seed=self.seed,
            months=self.country.months,
            policy_rule=passive_rule,
            country=self.country,
            shocks_enabled=self.shocks_enabled,
        )
        played = self.sim.records
        played_final = (
            played[-1].state["government_approval"]
            if played
            else self.country.initial_state.government_approval
        )
        cf_final = (
            cf.records[-1].state["government_approval"]
            if cf.records
            else self.country.initial_state.government_approval
        )

        impacts: list[dict[str, Any]] = []
        for dec in self.decisions:
            target = dec["month"] + 3
            if target <= len(played) and target <= len(cf.records):
                delta = (
                    played[target - 1].state["government_approval"]
                    - cf.records[target - 1].state["government_approval"]
                )
                impacts.append({**dec, "approval_delta_3m": delta})
        impacts.sort(key=lambda item: abs(item["approval_delta_3m"]), reverse=True)

        return {
            "approval_diff_final": played_final - cf_final,
            "counterfactual_outcome": cf.outcome,
            "played_outcome": self.sim.outcome or "en_curso",
            "top_decisions": impacts[:5],
        }
