"""Active learning (ADR 009 secc. 4): `brain = "surrogate:<path>+fallback:
<brain>"`. Cuando la confianza de `position` del sustituto cae bajo un
umbral (default 0.6) O la percepcion queda fuera de distribucion (distancia
de Mahalanobis diagonal > percentil 99 de train, `ml/surrogate.py`), se
consulta el cerebro de respaldo, se usa SU decision, y la fila se agrega a
`data/ml/active_queue.jsonl` (formato de `ml/dataset.py::rows_from_run`,
lista para que `republica ml retrain --queue` la sume al split de
entrenamiento).

Perezoso igual que `ml/surrogate.py`: nada de esto requiere sklearn para
IMPORTARSE (el parseo del spec y la cola son puro stdlib); sklearn recien
hace falta para construir el `SurrogateActor` interno."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from republica.actors.sheet import ActorSheet
from republica.engine.actions import Action
from republica.ml import dataset as ml_dataset
from republica.world.config import Country

#: Umbral de confianza default (ADR 009 secc. 4, literal "0.6").
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

#: Cola de active learning default (ADR 009 secc. 4/8, literal
#: `data/ml/active_queue.jsonl`).
DEFAULT_QUEUE_PATH = Path(__file__).resolve().parents[3] / "data" / "ml" / "active_queue.jsonl"


def parse_active_spec(spec: str) -> tuple[str, str | None, float | None]:
    """`"surrogate:<path>"` -> `(path, None, None)`; `"surrogate:<path>
    +fallback:<brain>[+threshold:<valor>]"` -> `(path, brain, umbral)`.
    `<brain>` puede contener `:` (p.ej. `llm:ollama:qwen3:8b`) pero nunca
    `+` (ningun spec de cerebro existente lo usa), asi que se separa el
    resto por `+` primero y cada segmento `clave:valor` despues -- el
    `+threshold:<valor>` (ADR 009 secc. 4/9, deliverable 4: "con umbral
    0.99 ... con 0.0 ...") no esta en el ejemplo literal del ADR pero hace
    falta alguna forma de pasarlo desde `--brain`/`data/brains.yaml`; sin
    esto el umbral quedaria fijo en el default (0.6) sin forma de probarlo
    desde la CLI."""
    if not spec.startswith("surrogate:"):
        raise ValueError(f"spec de active learning invalido: {spec!r} (debe empezar 'surrogate:')")
    rest = spec[len("surrogate:") :]
    parts = rest.split("+")
    path = parts[0]
    fallback: str | None = None
    threshold: float | None = None
    for part in parts[1:]:
        key, _, value = part.partition(":")
        if key == "fallback":
            fallback = value
        elif key == "threshold":
            threshold = float(value)
        elif key:
            raise ValueError(f"segmento de spec de active learning desconocido: {part!r}")
    return path, fallback, threshold


@dataclass
class ActiveLearningActor:
    """Envuelve un `SurrogateActor` + un cerebro de respaldo (ADR 009 secc.
    4). Misma interfaz `decide(perception, rng) -> list[Action]`."""

    sheet: ActorSheet
    surrogate: Any  # ml.surrogate.SurrogateActor
    fallback_actor: Any  # RuleBasedActor | LLMActor
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    queue_path: Path | None = None
    country: Country | None = None
    n_calls: int = field(default=0, init=False)
    n_fallback: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.last_score = None
        self.last_confidence: float = 1.0
        self.last_used_fallback: bool = False

    @property
    def brain_name(self) -> str:
        """`ActionRecord.brain` (ADR 009 secc. 9 deliverable 3): refleja
        quien decidio ESTE turno -- el sustituto o el respaldo -- no el
        `spec` estatico completo (`surrogate:...+fallback:...`), para que
        una corrida con active learning permita distinguir, accion a
        accion, cual de los dos la produjo."""
        if self.last_used_fallback:
            return getattr(self.fallback_actor, "brain_name", "rules")
        return getattr(self.surrogate, "brain_name", "surrogate")

    def decide(self, perception: Any, rng: Any) -> list[Action]:
        self.n_calls += 1
        actions = self.surrogate.decide(perception, rng)
        confidence = getattr(self.surrogate, "last_confidence", 1.0)
        is_ood = getattr(self.surrogate, "last_ood", False)
        self.last_confidence = confidence

        if confidence >= self.confidence_threshold and not is_ood:
            self.last_used_fallback = False
            return actions

        self.n_fallback += 1
        self.last_used_fallback = True
        fallback_actions = self.fallback_actor.decide(perception, rng)
        if self.queue_path is not None:
            self._log_to_queue(perception, fallback_actions)
        return fallback_actions

    def _log_to_queue(self, perception: Any, actions: list[Action]) -> None:
        """Agrega la fila `(actor, mes)` que decidio el respaldo a
        `active_queue.jsonl` (ADR 009 secc. 4), en el mismo esquema de fila
        que produce `ml/dataset.py::rows_from_run` para que `republica ml
        retrain --queue` la pueda sumar directo al split de entrenamiento
        sin re-parsear nada."""
        country = self.country
        if country is None:
            return
        parties_by_id = {p.id: p for p in country.parties}
        row = ml_dataset.perception_features(self.sheet, perception, country, parties_by_id)
        row.update(
            {
                "run_id": "active_queue",
                "seed": -1,
                "month": perception.month,
                "actor_id": self.sheet.id,
                "role": self.sheet.role,
            }
        )
        types = {a.type.value if hasattr(a.type, "value") else str(a.type) for a in actions}
        row["position"] = ml_dataset._derive_position(types)  # noqa: SLF001
        intensities = [
            a.params.get("intensity")
            for a in actions
            if isinstance(a.params.get("intensity"), int | float)
        ]
        row["intensity"] = max(intensities) if intensities else 0.0
        for t in ml_dataset.ACTION_TYPES:
            row[f"action_{t}"] = 1 if t in types else 0
        row.pop("n_memorias_negativas_recientes", None)

        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with self.queue_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    @property
    def fallback_rate(self) -> float:
        """Metrica por corrida/actor (ADR 009 secc. 4: "fallback_rate por
        corrida y por rol")."""
        return self.n_fallback / self.n_calls if self.n_calls else 0.0


def build_active_or_surrogate_actor(
    spec: str,
    sheet: ActorSheet,
    country: Country,
    *,
    seed: int = 0,
    temperature: float = 0.4,
    cache_dir: str | Path | None = None,
    memory_enabled: bool = False,
    governance: Any | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    queue_path: str | Path | None = None,
) -> Any:
    """`ai/brains.py::build_decision_actor` delega aca para `spec` que
    empieza con `"surrogate:"` (ADR 009 secc. 3/4). Sin `+fallback:...`
    devuelve un `SurrogateActor` liso; con el, un `ActiveLearningActor` que
    lo envuelve."""
    from republica.ml.surrogate import build_surrogate_actor  # noqa: PLC0415

    path, fallback_spec, spec_threshold = parse_active_spec(spec)
    surrogate = build_surrogate_actor(path, sheet, country)
    if fallback_spec is None:
        return surrogate
    if spec_threshold is not None:
        confidence_threshold = spec_threshold

    from republica.ai.brains import build_decision_actor  # noqa: PLC0415

    fallback_actor = build_decision_actor(
        fallback_spec,
        sheet,
        country,
        seed=seed,
        temperature=temperature,
        cache_dir=cache_dir,
        memory_enabled=memory_enabled,
        governance=governance,
    )
    return ActiveLearningActor(
        sheet=sheet,
        surrogate=surrogate,
        fallback_actor=fallback_actor,
        confidence_threshold=confidence_threshold,
        queue_path=Path(queue_path) if queue_path is not None else DEFAULT_QUEUE_PATH,
        country=country,
    )


def retrain_with_queue(
    model_path: str | Path,
    out_path: str | Path,
    *,
    queue_path: str | Path | None = None,
    sources: list[str | Path] | None = None,
    country: Country | None = None,
) -> dict[str, Any]:
    """`republica ml retrain --queue` (ADR 009 secc. 4): reentrena sumando
    `active_queue.jsonl` al split de entrenamiento del dataset original.
    `sources` (default: `manifest.json` del modelo no guarda las rutas
    fuente originales -- se documenta como limitacion: hay que volver a
    pasar `--runs` en `retrain`) son las mismas corridas usadas por
    `republica ml train`; sin ellas no hay como reconstruir val/test."""
    from republica.ml.surrogate import load_surrogate_bundle, train_surrogate

    qpath = Path(queue_path) if queue_path is not None else DEFAULT_QUEUE_PATH
    queue_rows: list[dict[str, Any]] = []
    if qpath.exists():
        for line in qpath.read_text(encoding="utf-8").splitlines():
            if line.strip():
                queue_rows.append(json.loads(line))

    old_bundle = load_surrogate_bundle(model_path)
    old_metrics = old_bundle["manifest"]["metrics"]

    if not sources:
        raise ValueError(
            "retrain_with_queue necesita 'sources' (las mismas corridas de 'republica ml train')"
        )
    result = train_surrogate(
        sources,
        out_path,
        brain=old_bundle["manifest"].get("brain", "rules"),
        country=country,
        queue_rows=queue_rows,
    )
    result["n_queue_rows_added"] = len(queue_rows)
    result["metrics_before"] = old_metrics
    return result


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_QUEUE_PATH",
    "ActiveLearningActor",
    "build_active_or_surrogate_actor",
    "parse_active_spec",
    "retrain_with_queue",
]
