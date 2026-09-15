"""Dataset de decisiones (ADR 009 secc. 2): una fila por `(actor, mes)`,
extraida de corridas ya guardadas en JSONL (`republica run --out ...`) o de
objetos `History` en memoria (p.ej. corridas de un experimento que todavia
no se volcaron a disco).

No requiere sklearn/pandas: el CSV se escribe con el modulo `csv` de la
stdlib. `pandas`+`pyarrow` (extra `[analysis]`) son opcionales, solo para el
parquet -- si no estan, `build_dataset` escribe unicamente el CSV y lo dice.

Aproximaciones (documentadas en detalle en "Notas de implementacion" de
`docs/ADR_009_surrogate_ui.md`, porque el JSONL de una corrida NO persiste
la `Perception` de los actores por reglas -- solo LLM traza eso, ADR 004
secc. 6 -- asi que las features privadas/de propuesta se RECONSTRUYEN desde
lo que si esta en el JSONL, no se leen tal cual):

1. `policy_delta` de la propuesta que vio el actor este mes se aproxima como
   `policy[mes] - policy[mes-1]` de los 5 instrumentos (no el delta interno
   exacto que arma `compute_policy_proposal`, que corre ANTES del recorte
   de Congreso/topes mensuales).
2. `private_indicators` reconstruye la formula de `engine/perception.py`
   sobre los campos que SI persiste `MonthRecord` (`state`/`policy`/`aux`/
   `provinces`); `affected_by_shocks`/`sector_affected_by_shocks` (que
   necesitan el `ShockAggregate` del mes, no persistido) quedan en `0.0`.
3. `trust_president` se iguala a `relationship_president` (la vista de
   memoria que reemplaza el valor crudo, ADR 006 secc. 1.3, tampoco se
   persiste para actores por reglas): mismo numero en las dos columnas.
4. `relationship_president`/`trust_president` de un actor que puntua
   propuestas (todos salvo `media`/`central_bank`) se recupera invirtiendo
   `score.rel = (relacion - 50) * 2` del `ActionRecord` de ese mes (ADR 003
   secc. 6, `rule_based.compute_score`); para `media`/`central_bank` (que no
   puntuan) se usa el valor ESTATICO de la ficha (`ActorSheet.relationship`,
   no decae/no refleja la corrida real).
5. `seats`/`in_government` usan `country.parties` (config INICIAL del
   pais): una corrida con `features.elections` puede cambiar bancas/partido
   de gobierno a mitad de camino; no se rastrean los `ElectionResult` mes a
   mes para actualizarlos (documentado, no bloqueante: el sustituto igual
   ve `months_to_election`/`congress_support` reales, que si cambian).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from republica.actors.sheet import ActorSheet, load_actors
from republica.engine.actions import ActionType
from republica.engine.narrate import KEY_INDICATORS
from republica.world.config import Country, load_country

#: Los 9 `public_indicators` (ADR 009 secc. 2): los 8 del tablero
#: (`narrate.KEY_INDICATORS`) + `inflation_annual`.
PUBLIC_COLUMNS: tuple[str, ...] = tuple(key for key, _, _ in KEY_INDICATORS) + ("inflation_annual",)

#: Redondeo de `public_indicators` (ADR 004 secc. 5, mismos umbrales que
#: `engine/perception.py::_ROUNDING`): reproducido aca porque ese modulo
#: opera sobre `WorldState` vivo, no sobre el `dict` de `MonthRecord.state`.
_PUBLIC_ROUNDING: dict[str, int] = {"inflation": 1, "reserves": -2}

#: Los 5 instrumentos de `Policy` (ADR 003 secc. 1/SPEC_v0.1 secc. 2.3).
POLICY_INSTRUMENTS: tuple[str, ...] = (
    "interest_rate_target",
    "tax_rate",
    "primary_spending",
    "provincial_transfers",
    "fx_intervention",
)

IDEOLOGY_AXES: tuple[str, ...] = ("economic", "social", "federalism", "institutionalism")
PERSONALITY_AXES: tuple[str, ...] = ("ambition", "risk_tolerance", "loyalty", "pragmatism")
INFLUENCE_AXES: tuple[str, ...] = ("public", "congress", "streets", "markets")
ROLES: tuple[str, ...] = (
    "president",
    "economy_minister",
    "central_bank",
    "governor",
    "party",
    "union",
    "business",
    "media",
    "social_bloc",
)

#: Union de las claves de `private_indicators` de los 9 roles (ADR 004 secc.
#: 5): una fila solo llena las que le corresponden a `role`, el resto queda
#: `NaN` -- exactamente lo que pide el ADR ("con NaN donde no aplica (one-hot
#: de rol)": el one-hot de `role_*` es la senal para el modelo de "cuales de
#: estas columnas son reales").
PRIVATE_COLUMNS: tuple[str, ...] = (
    "deficit",
    "reserves_exact",
    "intervention_usd",
    "exchange_rate",
    "inflation_lag1",
    "public_debt",
    "interest_rate",
    "unemployment_p",
    "income_p",
    "dependence",
    "transfers_received",
    "affected_by_shocks",
    "seats",
    "congress_support",
    "approval",
    "poll_approval",
    "real_wage",
    "unemployment",
    "inflation",
    "protest_level",
    "public_employment",
    "gdp_growth",
    "tax_rate",
    "consumer_confidence",
    "sector_affected_by_shocks",
    "institutional_confidence",
    "events_this_month",
    "poverty",
    "crime_perception",
)

#: Los 22 tipos del catalogo (ADR 003 secc. 4 + CAMPAIGN/PROMISE de ADR 006):
#: base del multilabel "que tipos de accion intenta" (ADR 009 secc. 2).
ACTION_TYPES: tuple[str, ...] = tuple(t.value for t in ActionType)

POSITIONS: tuple[str, ...] = ("support", "oppose", "negotiate", "neutral")

#: Ventana de "recientes" para `n_memorias_negativas_recientes` (ADR 009
#: secc. 2 no da un numero: se usa la misma ventana que
#: `world/perception.py::TREND_WINDOW_MONTHS` -- ya establecida en el
#: proyecto como "reciente" para tendencias de indicadores).
_RECENT_MEMORY_WINDOW = 6


def _load_shock_ids(country: Country) -> tuple[str, ...]:
    return tuple(s["id"] for s in country.shocks)


def _round_public(key: str, value: float) -> float:
    return round(value, _PUBLIC_ROUNDING.get(key, 1))


def _derive_position(types: set[str]) -> str:
    """`position` (ADR 009 secc. 2, deliverable 1): derivada de los tipos de
    accion que el actor emitio este mes -- las reglas no declaran una
    `position` explicita como si lo haria un LLM (ADR 004 secc. 3), asi que
    se infiere del catalogo de acciones (documentado en el ADR)."""
    if "SUPPORT_POLICY" in types:
        return "support"
    if "OPPOSE_POLICY" in types:
        return "oppose"
    if "NEGOTIATE" in types:
        return "negotiate"
    return "neutral"


def _derive_intensity(actions: list[dict[str, Any]]) -> float:
    intensities = [
        float(a["params"]["intensity"])
        for a in actions
        if isinstance(a.get("params"), dict) and "intensity" in a["params"]
    ]
    if intensities:
        return max(intensities)
    for a in actions:
        score = a.get("score")
        if score is not None:
            return max(0.0, min(1.0, abs(score.get("total", 0.0)) / 80.0))
    return 0.0


def _relationship_president(actions: list[dict[str, Any]], sheet: ActorSheet) -> float:
    for a in actions:
        score = a.get("score")
        if score is not None and "rel" in score:
            return score["rel"] / 2.0 + 50.0
    return float(sheet.relationship("president"))


def in_government(sheet: ActorSheet, parties_by_id: dict[str, Any]) -> float:
    if sheet.role == "governor":
        party = parties_by_id.get(sheet.party or "")
    elif sheet.role == "party":
        party = parties_by_id.get(sheet.id.removeprefix("party_"))
    else:
        return float("nan")
    return float(bool(party.in_government)) if party is not None else 0.0


def _months_to_election(month: int, term_length: int) -> float:
    if term_length <= 0:
        return 0.0
    return float(((month - 1) // term_length + 1) * term_length - month)


def _private_indicators(
    sheet: ActorSheet,
    state: dict[str, float],
    policy: dict[str, float],
    aux: dict[str, float],
    events_this_month: int,
    provinces_by_id: dict[str, Any],
    province_records: dict[str, dict[str, float]],
    parties_by_id: dict[str, Any],
) -> dict[str, float]:
    """Aproximacion de `engine/perception.py::build_perception` (visibilidad
    por rol, ADR 004 secc. 5) sobre lo que persiste `MonthRecord` -- ver
    aproximaciones 2 en el docstring del modulo."""
    role = sheet.role
    values: dict[str, float] = {}
    if role in ("president", "economy_minister"):
        values["deficit"] = -state["fiscal_balance"]
        values["reserves_exact"] = state["reserves"]
        values["intervention_usd"] = aux.get("intervention_usd", 0.0)
    elif role == "central_bank":
        values["reserves_exact"] = state["reserves"]
        values["exchange_rate"] = state["exchange_rate"]
        values["inflation_lag1"] = state["inflation_lag1"]
        values["intervention_usd"] = aux.get("intervention_usd", 0.0)
        values["public_debt"] = state["public_debt"]
        values["interest_rate"] = state["interest_rate"]
    elif role == "governor":
        province = provinces_by_id.get(sheet.province or "")
        prec = province_records.get(sheet.province or "")
        if province is not None and prec is not None:
            values["unemployment_p"] = prec["unemployment_p"]
            values["income_p"] = prec["income_p"]
            values["dependence"] = province.dependence
            values["transfers_received"] = policy["provincial_transfers"] * province.dependence
            values["affected_by_shocks"] = 0.0
    elif role == "party":
        party = parties_by_id.get(sheet.id.removeprefix("party_"))
        values["seats"] = float(party.seats) if party else 0.0
        values["congress_support"] = state["congress_support"]
        values["approval"] = state["government_approval"]
        values["poll_approval"] = state["government_approval"]
    elif role == "union":
        values["real_wage"] = state["real_wage"]
        values["unemployment"] = state["unemployment"]
        values["inflation"] = state["inflation"]
        values["protest_level"] = state["protest_level"]
        if sheet.id == "union_public":
            values["public_employment"] = policy["primary_spending"]
    elif role == "business":
        values["gdp_growth"] = state["gdp_growth"]
        values["interest_rate"] = state["interest_rate"]
        values["exchange_rate"] = state["exchange_rate"]
        values["tax_rate"] = policy["tax_rate"]
        values["consumer_confidence"] = state["consumer_confidence"]
        if sheet.sector:
            values["sector_affected_by_shocks"] = 0.0
    elif role == "media":
        values["approval"] = state["government_approval"]
        values["protest_level"] = state["protest_level"]
        values["institutional_confidence"] = state["institutional_confidence"]
        values["events_this_month"] = float(events_this_month)
    else:  # social_bloc
        values["real_wage"] = state["real_wage"]
        values["unemployment"] = state["unemployment"]
        values["poverty"] = state["poverty"]
        values["inflation"] = state["inflation"]
        values["crime_perception"] = state["crime_perception"]
    return values


@dataclass
class _RunRows:
    run_id: str
    seed: int
    records: list[dict[str, Any]]
    actions_by_month: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    memory_by_month: dict[int, list[dict[str, Any]]] = field(default_factory=dict)


def _group_sidecars(
    parsed: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]]]:
    records: list[dict[str, Any]] = []
    actions_by_month: dict[int, list[dict[str, Any]]] = {}
    memory_by_month: dict[int, list[dict[str, Any]]] = {}
    sidecar_kinds = ("action", "vote", "negotiation", "perception", "memory", "election", "trace")
    for r in parsed:
        kind = r.get("kind")
        if kind is None:
            records.append(r)
        elif kind == "action":
            actions_by_month.setdefault(r["month"], []).append(r)
        elif kind == "memory":
            memory_by_month.setdefault(r["month"], []).append(r)
        elif kind not in sidecar_kinds:
            records.append(r)
    return records, actions_by_month, memory_by_month


def load_run_jsonl(path: str | Path) -> _RunRows:
    """Lee un JSONL de `republica run`/`experiment run` a `_RunRows`. Propio
    (no `engine.narrate.load_jsonl`) porque ese parser descarta las lineas
    `kind: "memory"` sin agruparlas (solo las usa para no contarlas como
    `MonthRecord`, ver `narrate.Loaded`) y ac aca hacen falta para
    `n_memorias_negativas_recientes`."""
    p = Path(path)
    lines = [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"{p} esta vacio")
    parsed = [json.loads(line) for line in lines[:-1]]
    summary = json.loads(lines[-1])
    records, actions_by_month, memory_by_month = _group_sidecars(parsed)
    seed = int(summary.get("seed", 0))
    return _RunRows(
        run_id=f"{p.stem}:{seed}",
        seed=seed,
        records=records,
        actions_by_month=actions_by_month,
        memory_by_month=memory_by_month,
    )


def load_run_history(history: Any, run_id: str | None = None) -> _RunRows:
    """Idem `load_run_jsonl` pero para un `engine.simulation.History` ya en
    memoria (deliverable 1: "de JSONL o de objetos `History`")."""
    records = [r.to_dict() for r in history.records]
    actions_by_month: dict[int, list[dict[str, Any]]] = {}
    for a in history.action_records:
        actions_by_month.setdefault(a.month, []).append(a.to_dict())
    memory_by_month: dict[int, list[dict[str, Any]]] = {}
    for m in history.memory_records:
        d = m.to_dict()
        memory_by_month.setdefault(d["month"], []).append(d)
    return _RunRows(
        run_id=run_id or f"history:{history.seed}",
        seed=history.seed,
        records=records,
        actions_by_month=actions_by_month,
        memory_by_month=memory_by_month,
    )


def _count_recent_negative_memories(
    memory_by_month: dict[int, list[dict[str, Any]]], actor_id: str, month: int
) -> int:
    count = 0
    for m in range(max(1, month - _RECENT_MEMORY_WINDOW + 1), month + 1):
        for ev in memory_by_month.get(m, []):
            if ev.get("owner") == actor_id and float(ev.get("sentiment", 0.0)) < 0.0:
                count += 1
    return count


def rows_from_run(
    run: _RunRows, actors: dict[str, ActorSheet], country: Country
) -> list[dict[str, Any]]:
    """El nucleo de ADR 009 secc. 2: una fila por `(actor, mes)` presente en
    `run.actions_by_month` (todo actor no-presidente decide -y por lo tanto
    emite al menos un `ActionRecord`, aunque sea `NO_ACTION`- todos los
    meses via `engine/scheduler.py::run_actor_turn`)."""
    parties_by_id = {p.id: p for p in country.parties}
    provinces_by_id = {p.id: p for p in country.provinces}
    shock_ids = _load_shock_ids(country)
    rows: list[dict[str, Any]] = []
    prev_policy: dict[str, float] | None = None

    for rec in run.records:
        month = rec["month_index"]
        state = rec["state"]
        policy = rec["policy"]
        aux = rec.get("aux", {})
        actions = run.actions_by_month.get(month, [])
        by_actor: dict[str, list[dict[str, Any]]] = {}
        for a in actions:
            by_actor.setdefault(a["actor"], []).append(a)

        if prev_policy is not None:
            policy_delta = {
                instr: policy.get(instr, 0.0) - prev_policy.get(instr, 0.0)
                for instr in POLICY_INSTRUMENTS
            }
        else:
            policy_delta = dict.fromkeys(POLICY_INSTRUMENTS, 0.0)
        magnitude = sum(abs(v) for v in policy_delta.values()) / len(POLICY_INSTRUMENTS)

        active_shocks = set(rec.get("shocks_active", [])) | set(rec.get("shocks_new", []))
        province_records = {p["id"]: p for p in rec.get("provinces", [])}
        events_this_month = len(rec.get("events", []))

        for actor_id, actor_actions in by_actor.items():
            sheet = actors.get(actor_id)
            if sheet is None or sheet.role == "president":
                continue
            types = {a["type"] for a in actor_actions}
            row: dict[str, Any] = {
                "run_id": run.run_id,
                "seed": run.seed,
                "month": month,
                "actor_id": actor_id,
                "role": sheet.role,
            }
            for key in PUBLIC_COLUMNS:
                if key == "inflation_annual":
                    from republica.engine.narrate import annualized_inflation

                    row[f"pub_{key}"] = round(annualized_inflation(state["inflation"]), 1)
                else:
                    row[f"pub_{key}"] = _round_public(key, state[key])

            private = _private_indicators(
                sheet,
                state,
                policy,
                aux,
                events_this_month,
                provinces_by_id,
                province_records,
                parties_by_id,
            )
            for key in PRIVATE_COLUMNS:
                row[f"pi_{key}"] = private.get(key, math.nan)

            for instr in POLICY_INSTRUMENTS:
                row[f"policy_delta_{instr}"] = policy_delta[instr]
            row["policy_delta_magnitude"] = magnitude

            for axis in IDEOLOGY_AXES:
                row[f"ideology_{axis}"] = getattr(sheet.ideology, axis)
            for axis in PERSONALITY_AXES:
                row[f"personality_{axis}"] = getattr(sheet.personality, axis)
            for axis in INFLUENCE_AXES:
                row[f"influence_{axis}"] = getattr(sheet.influence, axis)
            for role in ROLES:
                row[f"role_{role}"] = 1 if sheet.role == role else 0

            rel = _relationship_president(actor_actions, sheet)
            row["relationship_president"] = rel
            row["trust_president"] = rel
            row["n_memorias_negativas_recientes"] = _count_recent_negative_memories(
                run.memory_by_month, actor_id, month
            )
            row["months_to_election"] = _months_to_election(month, country.term_length)
            for sid in shock_ids:
                row[f"shock_{sid}"] = 1 if sid in active_shocks else 0
            row["in_government"] = in_government(sheet, parties_by_id)

            # targets (ADR 009 secc. 2)
            row["position"] = _derive_position(types)
            row["intensity"] = _derive_intensity(actor_actions)
            for t in ACTION_TYPES:
                row[f"action_{t}"] = 1 if t in types else 0
            denied = [a for a in actor_actions if not a.get("authorized", True)]
            row["authorized"] = 0 if denied else 1
            row["n_denied"] = len(denied)

            rows.append(row)
        prev_policy = policy
    return rows


def feature_columns(country: Country) -> list[str]:
    """Columnas de `X` para entrenar/inferir el sustituto (ADR 009 secc. 3):
    subconjunto de `dataset_columns()` sin metadata (`run_id`/`seed`/`month`/
    `actor_id`/`role`, `role_*` -- el rol ya segmenta que pipeline se usa),
    sin targets, y SIN `n_memorias_negativas_recientes` -- ver el docstring
    del modulo, aproximacion 3/desviacion documentada: no hay forma barata
    de reconstruir esa cuenta desde una `Perception` viva en inferencia
    online (`SurrogateActor.decide`, `ml/surrogate.py`) sin releer el
    `MemoryStore` completo, asi que se excluye de `X` en vez de aproximarla
    con ruido -- sigue viviendo en el CSV del dataset como columna de
    inspeccion, nunca como feature del modelo."""
    cols = [f"pub_{k}" for k in PUBLIC_COLUMNS]
    cols += [f"pi_{k}" for k in PRIVATE_COLUMNS]
    cols += [f"policy_delta_{k}" for k in POLICY_INSTRUMENTS]
    cols += ["policy_delta_magnitude"]
    cols += [f"ideology_{k}" for k in IDEOLOGY_AXES]
    cols += [f"personality_{k}" for k in PERSONALITY_AXES]
    cols += [f"influence_{k}" for k in INFLUENCE_AXES]
    cols += ["relationship_president", "trust_president", "months_to_election"]
    cols += [f"shock_{sid}" for sid in _load_shock_ids(country)]
    cols += ["in_government"]
    return cols


def perception_features(
    actor: ActorSheet,
    perception: Any,
    country: Country,
    parties_by_id: dict[str, Any],
) -> dict[str, Any]:
    """Version "online" de una fila de `rows_from_run` (ADR 009 secc. 3):
    arma el mismo esquema de `feature_columns(country)` a partir de una
    `Perception` VIVA (`engine/perception.py`), no de un JSONL ya escrito --
    la usa `ml/surrogate.py::SurrogateActor.decide()` en cada turno. A
    diferencia de la reconstruccion offline (`_private_indicators` arriba,
    aproximada), esta lee `perception.public_indicators`/
    `private_indicators`/`proposal`/`relationships` DIRECTO: son mas
    precisos que la aproximacion offline (esa es la fuente real que vio el
    actor), documentado como una pequena asimetria train/infer aceptada en
    "Notas de implementacion"."""
    row: dict[str, Any] = {}
    for key in PUBLIC_COLUMNS:
        row[f"pub_{key}"] = perception.public_indicators.get(key, math.nan)
    for key in PRIVATE_COLUMNS:
        row[f"pi_{key}"] = perception.private_indicators.get(key, math.nan)
    delta = perception.proposal.delta if perception.proposal else {}
    for instr in POLICY_INSTRUMENTS:
        row[f"policy_delta_{instr}"] = delta.get(instr, 0.0)
    row["policy_delta_magnitude"] = (
        sum(abs(v) for v in delta.values()) / len(POLICY_INSTRUMENTS) if delta else 0.0
    )
    for axis in IDEOLOGY_AXES:
        row[f"ideology_{axis}"] = getattr(actor.ideology, axis)
    for axis in PERSONALITY_AXES:
        row[f"personality_{axis}"] = getattr(actor.personality, axis)
    for axis in INFLUENCE_AXES:
        row[f"influence_{axis}"] = getattr(actor.influence, axis)
    rel = float(perception.relationships.get("president", 50))
    row["relationship_president"] = rel
    row["trust_president"] = rel
    row["months_to_election"] = float(perception.months_to_election)
    for sid in _load_shock_ids(country):
        row[f"shock_{sid}"] = 1 if sid in perception.active_shocks else 0
    row["in_government"] = in_government(actor, parties_by_id)
    return row


def dataset_columns() -> list[str]:
    """El orden de columnas del CSV/parquet (deliverable 1): meta, publicas,
    privadas, propuesta, actor, relacion/memoria, contexto, targets."""
    cols = ["run_id", "seed", "month", "actor_id", "role"]
    cols += [f"pub_{k}" for k in PUBLIC_COLUMNS]
    cols += [f"pi_{k}" for k in PRIVATE_COLUMNS]
    cols += [f"policy_delta_{k}" for k in POLICY_INSTRUMENTS]
    cols += ["policy_delta_magnitude"]
    cols += [f"ideology_{k}" for k in IDEOLOGY_AXES]
    cols += [f"personality_{k}" for k in PERSONALITY_AXES]
    cols += [f"influence_{k}" for k in INFLUENCE_AXES]
    cols += [f"role_{k}" for k in ROLES]
    cols += ["relationship_president", "trust_president", "n_memorias_negativas_recientes"]
    cols += ["months_to_election"]
    cols += [f"shock_{i}" for i in range(12)]  # nombre generico si no hay country a mano
    cols += ["in_government"]
    cols += ["position", "intensity"]
    cols += [f"action_{t}" for t in ACTION_TYPES]
    cols += ["authorized", "n_denied"]
    return cols


def _iter_jsonl_paths(sources: list[str | Path]) -> list[Path]:
    paths: list[Path] = []
    for src in sources:
        p = Path(src)
        if p.is_dir():
            paths.extend(
                sorted(
                    f
                    for f in p.rglob("*.jsonl")
                    if f.name not in ("failed.jsonl",) and not f.name.startswith(".")
                )
            )
        elif p.is_file():
            paths.append(p)
        else:
            raise FileNotFoundError(f"{p} no existe (ni archivo ni directorio)")
    return paths


def build_dataset(
    sources: list[str | Path],
    out: str | Path,
    *,
    actors: dict[str, ActorSheet] | None = None,
    country: Country | None = None,
) -> dict[str, Any]:
    """`republica ml dataset <dir|jsonl...> --out data/ml/decisions.csv`
    (ADR 009 secc. 2). `sources` puede mezclar directorios (recorridos con
    `rglob("*.jsonl")`, como `simulations/exp/<experimento>/<brazo>/`) y
    archivos `.jsonl` sueltos. Escribe siempre el CSV; el parquet solo si
    `pandas`+`pyarrow` estan instalados (extra `[analysis]`)."""
    actors = actors if actors is not None else load_actors()
    country = country if country is not None else load_country()
    paths = _iter_jsonl_paths(sources)
    if not paths:
        raise ValueError(f"ningun .jsonl encontrado en {sources!r}")

    all_rows: list[dict[str, Any]] = []
    n_runs = 0
    n_failed = 0
    for path in paths:
        try:
            run = load_run_jsonl(path)
        except (ValueError, json.JSONDecodeError, KeyError):
            n_failed += 1
            continue
        all_rows.extend(rows_from_run(run, actors, country))
        n_runs += 1

    columns = dataset_columns()
    # Los nombres genericos `shock_0..11` de `dataset_columns()` se
    # reemplazan por los ids reales del `country` que efectivamente se uso
    # (`data/shocks.json`, ADR 009 secc. 2: "shocks activos (12 booleanos)").
    shock_ids = _load_shock_ids(country)
    columns = [c for c in columns if not c.startswith("shock_")]
    idx = columns.index("in_government")
    for i, sid in enumerate(shock_ids):
        columns.insert(idx + i, f"shock_{sid}")

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    parquet_path: str | None = None
    try:
        import pandas as pd  # noqa: PLC0415

        df = pd.DataFrame(all_rows, columns=columns)
        pq_path = out_path.with_suffix(".parquet")
        df.to_parquet(pq_path)
        parquet_path = str(pq_path)
    except ImportError:
        pass

    return {
        "out_csv": str(out_path),
        "out_parquet": parquet_path,
        "n_runs": n_runs,
        "n_failed_runs": n_failed,
        "n_rows": len(all_rows),
        "columns": columns,
    }


__all__ = [
    "ACTION_TYPES",
    "IDEOLOGY_AXES",
    "INFLUENCE_AXES",
    "PERSONALITY_AXES",
    "POLICY_INSTRUMENTS",
    "POSITIONS",
    "PRIVATE_COLUMNS",
    "PUBLIC_COLUMNS",
    "ROLES",
    "build_dataset",
    "dataset_columns",
    "feature_columns",
    "in_government",
    "load_run_history",
    "load_run_jsonl",
    "perception_features",
    "rows_from_run",
]
