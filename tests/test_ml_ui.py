"""Tests de aceptacion de ADR 009 (Fase 9: sustituto, active learning,
early-warning, clustering, UI), seccion 9:
1. `dataset` sobre corridas produce filas = suma de actores x meses.
2. `train`/`evaluate`: agreement >= 0.85 en `position` contra `rules`.
3. `surrogate` como brain corre y produce `ActionRecord` con `brain =
   surrogate:<path>`.
4. Active learning: umbral 0.99 -> `fallback_rate` ~= 1; umbral 0.0 -> 0;
   la cola se escribe.
5. Early-warning: AUC >= 0.8 en held-out.
6. `regimes`: k por silhouette, tabla `regimes` en DuckDB, `--describe`
   imprime >= 3 clusters.
7. `AppTest`: la app carga, muestra las 12 pestanas y avanza un mes.
8. Tiempo: proxy de throughput `surrogate` vs `rules` (un centenar de
   corridas en vez de 1.000 -- documentado en `docs/FASE9_RESULTS.md`, ver
   Notas de implementacion de ADR 009).

Los tests 2/5/8 en su escala LITERAL del ADR (30-70 semillas de train, un
`fiscal_rule` de >= 600 corridas, 1.000 corridas de timing) se corrieron a
mano una vez para `docs/FASE9_RESULTS.md` (quedan documentados ahi con sus
numeros reales); en el default de la suite corren a una escala mas chica
(mismo codigo, menos semillas) para no inflar el tiempo de CI, marcados
`slow` cuando conviene una version mas fiel al DoD -- mismo criterio que
`tests/test_bounds.py`/`test_outcome_distribution.py` (ADR 003 secc. 11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from republica.actors.sheet import load_actors
from republica.engine.simulation import run as run_simulation
from republica.world.config import load_country

try:
    import sklearn  # noqa: F401

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    import duckdb  # noqa: F401

    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

try:
    import streamlit  # noqa: F401

    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

needs_sklearn = pytest.mark.skipif(not HAS_SKLEARN, reason="requiere el extra opcional 'ml'")
needs_duckdb = pytest.mark.skipif(not HAS_DUCKDB, reason="requiere el extra opcional 'analysis'")
needs_streamlit = pytest.mark.skipif(not HAS_STREAMLIT, reason="requiere el extra opcional 'ui'")

UI_APP_PATH = Path(__file__).resolve().parents[1] / "src" / "republica" / "ui" / "app.py"


def _write_runs(tmp_path: Path, seeds: list[int], months: int = 8) -> Path:
    out_dir = tmp_path / "runs"
    out_dir.mkdir()
    country = load_country()
    for seed in seeds:
        history = run_simulation(
            seed=seed,
            months=months,
            country=country,
            actors_enabled=True,
            congress_enabled=True,
            negotiation_enabled=True,
            cohorts_enabled=True,
            media_enabled=True,
            memory_enabled=True,
            elections_enabled=True,
        )
        (out_dir / f"{seed}.jsonl").write_text(history.to_jsonl(), encoding="utf-8")
    return out_dir


# 1. dataset -----------------------------------------------------------------


def test_dataset_rows_equal_actors_times_months(tmp_path):
    from republica.ml.dataset import build_dataset

    months = 6
    seeds = [0, 1, 2, 3]
    runs_dir = _write_runs(tmp_path, seeds, months=months)
    n_actors = sum(1 for a in load_actors().values() if a.role != "president")

    result = build_dataset([runs_dir], tmp_path / "decisions.csv")
    assert result["n_runs"] == len(seeds)
    assert result["n_rows"] == len(seeds) * months * n_actors

    rows = (tmp_path / "decisions.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1 + result["n_rows"]  # header + filas


def test_dataset_accepts_history_objects_directly(tmp_path):
    from republica.ml.dataset import load_run_history, rows_from_run

    country = load_country()
    actors = load_actors()
    history = run_simulation(seed=5, months=4, country=country, actors_enabled=True)
    run = load_run_history(history)
    rows = rows_from_run(run, actors, country)
    n_actors = sum(1 for a in actors.values() if a.role != "president")
    assert len(rows) == 4 * n_actors
    assert {"position", "intensity", "role", "actor_id"} <= rows[0].keys()


# 1b. split por (fuente, semilla) -------------------------------------


def test_split_group_seeds_groups_by_source_not_raw_seed_value():
    """Hallazgo #2 de REVIEW_003: semillas coincidentes entre dos fuentes
    (ej. `fiscal_rule` 0-19 y `central_bank_independence` 0-49) no deben
    mezclarse en el mismo split -- cada fuente parte 70/15/15 POR SU
    CUENTA."""
    from republica.ml.surrogate import _split_group_seeds

    pairs = [("fiscal_rule/base", s) for s in range(20)] + [("cbi/dependent", s) for s in range(20)]
    train, val, test = _split_group_seeds(pairs)[:3]
    for source in ("fiscal_rule/base", "cbi/dependent"):
        train_n = sum(1 for s, seed in train if s == source)
        val_n = sum(1 for s, seed in val if s == source)
        test_n = sum(1 for s, seed in test if s == source)
        assert train_n == 14, (source, train_n)  # round(20*0.7)
        assert val_n == 3, (source, val_n)  # round(20*0.15)
        assert test_n == 3, (source, test_n)
        assert train_n + val_n + test_n == 20
    # las dos fuentes NO comparten (fuente, semilla): val/test de una no
    # dependen de cuantas filas trajo la otra (el bug viejo: la fuente mas
    # grande se "comia" el split de la mas chica).
    assert train.isdisjoint(val) and val.isdisjoint(test) and train.isdisjoint(test)


def test_split_group_seeds_raises_on_two_or_fewer_seeds_by_default():
    """Hallazgo #11 de REVIEW_003: antes, <=2 semillas degeneraba en
    train == val == test EN SILENCIO (metricas in-sample presentadas como
    held-out)."""
    from republica.ml.surrogate import _split_group_seeds

    with pytest.raises(ValueError, match="in_sample"):
        _split_group_seeds([("solo_una_fuente", 0), ("solo_una_fuente", 1)])


def test_split_group_seeds_allow_in_sample_flags_the_source():
    from republica.ml.surrogate import _split_group_seeds

    train, val, test, in_sample_sources = _split_group_seeds(
        [("chica", 0), ("chica", 1)], allow_in_sample=True
    )
    assert in_sample_sources == {"chica"}
    assert train == val == test == {("chica", 0), ("chica", 1)}


# 2. train / evaluate ----------------------------------------------------


@needs_sklearn
def test_train_and_evaluate_agreement(tmp_path):
    """Hallazgo #1 de REVIEW_003: `agreement_rate` solo (contra actores por
    reglas, `position = neutral` en > 98 % de las filas) es casi trivial --
    esta prueba asierta sobre `balanced_agreement` (restringido a las
    (actor, mes) donde `rules` NO dio `neutral`), la metrica informativa.
    `months=48` (no 24, como antes) en train Y eval: con 24 meses las 60
    corridas reales -y estas 30 de juguete- casi no generan posiciones no
    neutrales (ver `FASE9_RESULTS.md` §2/§7), y `balanced_agreement` queda
    `nan` sobre 0 casos -- no hay nada que asertar. Con 48 meses (semillas
    1005-1009, elegidas a mano por tener actor-meses no neutrales reales,
    ver Notas de implementacion de ADR 009) el caso de juguete SI reproduce
    el fenomeno del hallazgo #1: `agreement_rate`/`majority_baseline` casi
    empatados (~0.995-0.997, la clase mayoritaria sola ya explica casi todo)
    contra `balanced_agreement` bastante mas bajo (~0.74 medido) -- el
    umbral de abajo es ese numero medido MENOS margen, no un objetivo de
    diseno: un `balanced_agreement` mas bajo todavia es el numero honesto,
    no una falla de esta prueba."""
    from republica.ml.surrogate import evaluate_surrogate, train_surrogate

    train_seeds = list(range(30))
    runs_dir = _write_runs(tmp_path, train_seeds, months=48)
    model_path = tmp_path / "surrogate.joblib"
    result = train_surrogate([runs_dir], model_path, brain="rules")
    assert result["roles"]
    assert Path(result["manifest_path"]).exists()

    eval_result = evaluate_surrogate(model_path, list(range(1005, 1010)), months=48)
    assert eval_result["n_actor_months"] > 0
    assert eval_result["agreement_rate"] >= 0.85, eval_result
    # Piso, no techo (hallazgo #1): un predictor CONSTANTE (la posicion mas
    # frecuente) ya llega ahi -- comparar `agreement_rate` solo contra esto
    # es lo que hacia trivial al DoD viejo.
    assert eval_result["majority_baseline"] > 0.9, eval_result
    # La metrica informativa: SOLO las (actor, mes) donde `rules` no dio
    # `neutral` (la clase mayoritaria queda afuera).
    assert eval_result["n_balanced_actor_months"] > 0, eval_result
    assert eval_result["balanced_agreement"] >= 0.6, eval_result  # ~0.74 medido, con margen
    # Excluye los roles que delegan a reglas (media/central_bank/roles sin
    # variedad, ver ML_ROLES/RULE_PASSTHROUGH_ROLES): no deberia superar el
    # 1.0 (imposible) y con roles entrenados de verdad debe estar definido.
    assert eval_result["n_ml_actor_months"] > 0, eval_result
    assert 0.0 <= eval_result["agreement_ml_roles_only"] <= 1.0, eval_result


# 3. surrogate brain produce ActionRecord con brain=surrogate ---------------


@needs_sklearn
def test_surrogate_brain_produces_action_records_with_brain_field(tmp_path):
    from republica.ml.surrogate import train_surrogate

    runs_dir = _write_runs(tmp_path, list(range(6)), months=8)
    model_path = tmp_path / "surrogate.joblib"
    train_surrogate([runs_dir], model_path)

    country = load_country()
    history = run_simulation(
        seed=42,
        months=6,
        country=country,
        actors_enabled=True,
        default_brain=f"surrogate:{model_path}",
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
    )
    n_actors = sum(1 for a in load_actors().values() if a.role != "president")
    assert len(history.action_records) >= n_actors  # al menos una accion/actor/mes
    brains = {a.brain for a in history.action_records}
    assert brains == {f"surrogate:{model_path}"}

    line = json.loads(history.to_jsonl().splitlines()[1])
    assert line["kind"] == "action"
    assert line["brain"] == f"surrogate:{model_path}"


# 4. active learning -----------------------------------------------------


def _stub_action(tag: str):
    from republica.engine.actions import Action, ActionType

    return Action(type=ActionType.NO_ACTION, actor_id="gov_norte", reason=tag)


class _StubSurrogate:
    def __init__(self, confidence: float, ood: bool = False) -> None:
        self.last_confidence = confidence
        self.last_ood = ood
        self.brain_name = "surrogate:stub"
        self.calls: list[object] = []

    def decide(self, perception, rng):  # noqa: ARG002
        self.calls.append(perception)
        return [_stub_action("surrogate-action")]


class _StubFallback:
    def __init__(self) -> None:
        self.brain_name = "rules"
        self.calls: list[object] = []

    def decide(self, perception, rng):  # noqa: ARG002
        self.calls.append(perception)
        return [_stub_action("fallback-action")]


def test_active_learning_threshold_high_always_falls_back(tmp_path):
    from republica.ml.active import ActiveLearningActor

    sheet = load_actors()["gov_norte"]
    surrogate = _StubSurrogate(confidence=0.7)
    fallback = _StubFallback()
    actor = ActiveLearningActor(
        sheet=sheet,
        surrogate=surrogate,
        fallback_actor=fallback,
        confidence_threshold=0.99,
        queue_path=tmp_path / "queue.jsonl",
        country=load_country(),
    )
    for month in range(1, 6):
        perception = _fake_perception(month)
        actions = actor.decide(perception, None)
        assert [a.reason for a in actions] == ["fallback-action"]
    assert actor.fallback_rate == 1.0
    assert (tmp_path / "queue.jsonl").exists()
    lines = (tmp_path / "queue.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5


def test_active_learning_threshold_zero_never_falls_back(tmp_path):
    from republica.ml.active import ActiveLearningActor

    sheet = load_actors()["gov_norte"]
    surrogate = _StubSurrogate(confidence=0.4)  # confianza baja, pero el umbral es 0.0
    fallback = _StubFallback()
    actor = ActiveLearningActor(
        sheet=sheet,
        surrogate=surrogate,
        fallback_actor=fallback,
        confidence_threshold=0.0,
        queue_path=tmp_path / "queue.jsonl",
        country=load_country(),
    )
    for month in range(1, 6):
        actions = actor.decide(_fake_perception(month), None)
        assert [a.reason for a in actions] == ["surrogate-action"]
    assert actor.fallback_rate == 0.0
    assert not (tmp_path / "queue.jsonl").exists()


def test_active_learning_ood_forces_fallback_even_with_high_confidence(tmp_path):
    from republica.ml.active import ActiveLearningActor

    sheet = load_actors()["gov_norte"]
    surrogate = _StubSurrogate(confidence=0.99, ood=True)
    fallback = _StubFallback()
    actor = ActiveLearningActor(
        sheet=sheet,
        surrogate=surrogate,
        fallback_actor=fallback,
        confidence_threshold=0.6,
        queue_path=tmp_path / "queue.jsonl",
        country=load_country(),
    )
    actions = actor.decide(_fake_perception(1), None)
    assert [a.reason for a in actions] == ["fallback-action"]


def _fake_perception(month: int):
    from republica.engine.perception import Perception

    return Perception(
        month=month,
        date="2025-01",
        months_to_election=12,
        public_indicators={"inflation": 2.0, "government_approval": 50.0},
        private_indicators={"unemployment_p": 8.0},
        proposal=None,
        active_shocks=[],
        recent_events=[],
        relationships={"president": 50},
        memories=[],
        goals=[],
    )


@needs_sklearn
def test_parse_active_spec_threshold_segment():
    from republica.ml.active import parse_active_spec

    path, fallback, threshold = parse_active_spec(
        "surrogate:data/ml/x.joblib+fallback:rules+threshold:0.99"
    )
    assert path == "data/ml/x.joblib"
    assert fallback == "rules"
    assert threshold == pytest.approx(0.99)


# 5. early-warning ---------------------------------------------------------


@needs_sklearn
def test_early_warning_auc(tmp_path):
    """Sweep chico de `fiscal_rule` (mismo mecanismo, menos semillas que el
    DoD literal de >= 600 corridas -- ver docstring del modulo): suficiente
    para separar corridas con/sin crisis con AUC >= 0.8."""
    from republica.experiments.runner import run_experiment
    from republica.ml.early_warning import train_early_warning

    yaml_text = """
name: fiscal_rule_test
description: sweep chico para el test de early-warning.
base:
  months: 30
  features: {actors: true, congress: true, negotiation: true, cohorts: true,
    media: true, memory: true, elections: true}
  brains: rules
seeds: {start: 0, count: 12}
arms:
  base: {}
sweep:
  country.coefficients.c_f: [0.08, 0.16]
  country.default_policy.primary_spending: [23, 27]
metrics: [outcome]
"""
    yaml_path = tmp_path / "fiscal_rule_test.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    out_dir = tmp_path / "exp"
    run_experiment(yaml_path, out_dir, workers=2)

    model_path = tmp_path / "early_warning.joblib"
    result = train_early_warning([out_dir], model_path)
    assert result["n_positive"] > 0, "el sweep no produjo ninguna crisis: revisar el YAML del test"
    assert result["auc_test"] >= 0.8 or result["auc_val"] >= 0.8, result


@pytest.mark.slow
@needs_sklearn
def test_early_warning_auc_full_scale(tmp_path):
    """Version fiel al DoD literal (fiscal_rule, 3x3, 70 semillas ~ 630
    corridas): no corre por default (ver `pyproject.toml`, marker `slow`)."""
    from republica.experiments.runner import run_experiment
    from republica.ml.early_warning import train_early_warning

    out_dir = tmp_path / "exp"
    run_experiment(Path("experiments/fiscal_rule.yaml"), out_dir, workers=4)
    model_path = tmp_path / "early_warning.joblib"
    result = train_early_warning([out_dir], model_path)
    assert result["auc_test"] >= 0.8, result


# 6. regimes ---------------------------------------------------------------


@needs_sklearn
@needs_duckdb
def test_regimes_clustering(tmp_path):
    from republica.experiments.runner import run_experiment
    from republica.experiments.store import load_experiment
    from republica.ml.regimes import run_regimes

    yaml_text = """
name: regimes_test
description: sweep chico para el test de regimenes.
base:
  months: 24
  features: {actors: true, congress: true, negotiation: true, cohorts: true,
    media: true, memory: true, elections: true}
  brains: rules
seeds: {start: 0, count: 8}
arms:
  base: {}
sweep:
  country.coefficients.c_f: [0.08, 0.12, 0.16]
metrics: [outcome]
"""
    yaml_path = tmp_path / "regimes_test.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    out_dir = tmp_path / "exp"
    run_experiment(yaml_path, out_dir, workers=2)
    db_path = tmp_path / "regimes.duckdb"
    load_experiment(out_dir, db_path)

    result = run_regimes(db_path, describe=True)
    assert result["n_runs"] == 24
    assert 3 <= result["k"] <= 8
    assert len(result["descriptions"]) == result["k"]
    assert len(result["descriptions"]) >= 3

    con = duckdb.connect(str(db_path))
    n_rows = con.execute("SELECT count(*) FROM regimes").fetchone()[0]
    con.close()
    assert n_rows == 24


# 7. AppTest ----------------------------------------------------------------


@needs_streamlit
def test_app_loads_shows_12_tabs_and_advances_a_month():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(UI_APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 12
    expected = {
        "Mundo",
        "Politica",
        "Economia",
        "Congreso",
        "Actores",
        "Relaciones",
        "Medios",
        "Eventos",
        "Trazas IA",
        "Evals",
        "Experimentos",
        "Regimenes",
    }
    assert {t.label for t in at.tabs} == expected

    at.sidebar.checkbox(key="play_mode_toggle").set_value(True).run()
    assert not at.exception
    at.button(key="new_game").click().run()
    assert not at.exception
    month_before = at.session_state["game"].sim.month
    at.button(key="advance_month").click().run()
    assert not at.exception
    assert at.session_state["game"].sim.month == month_before + 1


# 8. throughput surrogate vs rules -------------------------------------


@needs_sklearn
def test_surrogate_throughput_proxy(tmp_path):
    """Proxy chico (no las 1.000/200 corridas del DoD -- ver docstring del
    modulo) que deja un numero medible de corridas/segundo para `rules` y
    `surrogate`, sin imponer un PISO de velocidad (el hardware de CI varia:
    un piso estricto en segundos absolutos seria fragil). Hallazgo #10 de
    REVIEW_003: si asierta algo, que sea un TECHO laxo sobre el ratio
    `surrogate`/`rules` -- adimensional, no depende del hardware tanto como
    un tiempo absoluto. La medicion real (`FASE9_RESULTS.md` §4, 30 corridas
    de 48 meses, modelo de 60 semillas) da ~34x; el techo de 60x deja margen
    (proxy mas chico, mas ruido) sin dejar pasar una regresion real de
    orden de magnitud. `SurrogateActor.decide()` predice por ACTOR, por MES
    (no en lote de 29 actores, ver ADR 009 secc. 3 y la nota de
    implementacion 11b de `docs/ADR_009_surrogate_ui.md`) -- batchear eso
    (la tarea de "predecir en lote" que esa nota deja como trabajo futuro,
    fuera de alcance de REVIEW_003) es lo que bajaria este ratio."""
    import time

    from republica.ml.surrogate import train_surrogate

    runs_dir = _write_runs(tmp_path, list(range(6)), months=12)
    model_path = tmp_path / "surrogate.joblib"
    train_surrogate([runs_dir], model_path)
    country = load_country()

    def _time_n_runs(brain: str, n: int) -> float:
        t0 = time.perf_counter()
        for seed in range(900, 900 + n):
            run_simulation(
                seed=seed,
                months=12,
                country=country,
                actors_enabled=True,
                default_brain=brain,
                congress_enabled=True,
                negotiation_enabled=True,
                cohorts_enabled=True,
                media_enabled=True,
                memory_enabled=True,
                elections_enabled=True,
            )
        return time.perf_counter() - t0

    n = 5
    t_rules = _time_n_runs("rules", n)
    t_surrogate = _time_n_runs(f"surrogate:{model_path}", n)
    assert t_rules > 0
    assert t_surrogate > 0
    # Techo laxo (hallazgo #10), no piso: ~34x medido a escala real
    # (FASE9_RESULTS.md §4); 60x deja margen para el ruido de un proxy
    # chico sin dejar pasar una regresion de orden de magnitud (ej. volver
    # a cargar el .joblib entero por actor, ver ADR 009 nota 11b).
    ratio = t_surrogate / t_rules
    assert ratio <= 60, f"surrogate {ratio:.1f}x mas lento que rules (techo laxo: 60x)"
