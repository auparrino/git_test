"""Tests de ADR 013 secc. 6 (partidos, actores y lealtades argentinos por
epoca): los 5 puntos de la seccion, en orden.

Convenciones (ver el enunciado de la tarea):
- Cada `test_...` de abajo trae en su docstring/comentario el punto exacto de
  ADR 013 secc. 6 que cubre.
- Donde el criterio literal del ADR no se cumple con el motor/calibracion
  actual, el test queda en `xfail(strict=True)` con el numero medido en el
  mensaje -- la misma cifra esta transcripta en la seccion "Notas de
  implementacion" de `docs/ADR_013_argentine_parties_actors.md`. `strict=True`
  hace que el test falle la suite si algun dia empieza a pasar sin querer
  (hay que sacarle el marcador a mano, no dejarlo "pasando en secreto").
"""

from __future__ import annotations

import importlib.util
import json
import warnings
from pathlib import Path

import pytest

from republica.engine.simulation import run
from republica.world.countries import load_country_pack

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# `scripts/build_argentina_eras.py` no es un paquete (`scripts/` no tiene
# `__init__.py`): se carga por ruta, igual que el propio script hace con
# `src/` via `sys.path.insert`. Reusa sus tablas (`OPENING_*`, `COHORTS`,
# `era_1983_2001`/etc., `build_loyalty_rows`) en vez de duplicarlas: el punto
# 2 de abajo prueba el MISMO calculo que generó los CSV comiteados, no una
# reimplementacion paralela que podria divergir en silencio.
# ---------------------------------------------------------------------------


def _load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_argentina_eras", REPO_ROOT / "scripts" / "build_argentina_eras.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BUILD = _load_build_script()


# ---------------------------------------------------------------------------
# 1. `load_country_pack("argentina", "2019-12")` carga la epoca `2015-2023`;
#    `"1983-12"` la `1983-2001`; `"1900-01"` cae a Aurora con aviso.
# ---------------------------------------------------------------------------


def test_2019_12_loads_2015_2023_era() -> None:
    pack = load_country_pack("argentina", "2019-12", 12)
    assert pack.era is not None
    assert pack.era.active_era is not None
    assert pack.era.active_era.id == "2015-2023"
    assert pack.era.parties is not None
    assert {p["id"] for p in pack.era.parties} >= {
        "cambiemos_jxc",
        "fpv_fdt_pj",
        "fit_u",
        "uca_otros_2015",
        "lla",
    }
    assert pack.era.actors is not None
    assert len(pack.era.actors) >= 25
    assert pack.era.loyalty_table is not None
    # `country.parties` (lo que realmente usa `run()`) ya sale de la epoca,
    # no de Aurora (ADR 013 secc. 1: "el paquete de pais deja de usar los
    # partidos ... de Aurora").
    assert {p.id for p in pack.country.parties} == {p["id"] for p in pack.era.parties}


def test_1983_12_loads_1983_2001_era() -> None:
    pack = load_country_pack("argentina", "1983-12", 12)
    assert pack.era is not None
    assert pack.era.active_era is not None
    assert pack.era.active_era.id == "1983-2001"
    assert pack.era.parties is not None
    assert {p["id"] for p in pack.era.parties} == {
        "ucr",
        "pj",
        "ucede",
        "frepaso",
        "provinciales_1983",
    }


def test_1900_01_falls_back_to_aurora_with_warning() -> None:
    """ADR 013 secc. 1/6 punto 1: fecha sin epoca -> Aurora, con aviso, sin
    romper. `load_country_pack` exige ademas un `initial_states` para la
    fecha pedida (ADR 011 secc. 2, restriccion aparte de esta -- ninguna de
    las 8 fechas hito de Argentina cae fuera de las 3 epocas, asi que no hay
    forma de probar el fallback de epoca CON esa restriccion puesta al mismo
    tiempo): se usa `initial_state_override` con un estado prestado de
    1983-12 para saltearla, igual que hace `calibration/initial_states.py`
    para cualquier mes (ver el docstring de `initial_state_override` en
    `world/countries.py::load_country_pack`)."""
    borrowed_state = load_country_pack(
        "argentina", "1983-12", 12
    ).country.initial_state.model_dump()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pack = load_country_pack("argentina", "1900-01", 12, initial_state_override=borrowed_state)
    assert any("1900-01" in str(w.message) for w in caught)
    assert pack.era is not None
    assert pack.era.active_era is None
    assert pack.era.parties is None
    assert pack.era.warning is not None
    # Fallback real: `country.parties` sigue siendo el universo de Aurora
    # (`data/parties.json`), no una epoca.
    aurora_party_ids = {
        p["id"] for p in json.loads((REPO_ROOT / "data" / "parties.json").read_text())
    }
    assert {p.id for p in pack.country.parties} == aurora_party_ids


# ---------------------------------------------------------------------------
# 2. Eleccion de apertura reproducida +-3pp con utilidad neutra, por epoca
#    (ADR 013 secc. 4/6 punto 2).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "era_builder_name",
    ["era_1983_2001", "era_2003_2015", "era_2015_2023"],
)
def test_opening_election_reproduced_within_3pp(era_builder_name: str) -> None:
    era = getattr(BUILD, era_builder_name)()
    _rows, errors = BUILD.build_loyalty_rows(era)
    assert errors, f"{era['id']}: sin partidos activos en la eleccion de apertura"
    for party_id, error_pp in errors.items():
        assert abs(error_pp) <= 3.0, (
            f"{era['id']}/{party_id}: error de reproduccion {error_pp:+.2f}pp fuera de "
            "+-3pp (ADR 013 secc. 4/6 punto 2)"
        )


def test_cohorts_loyalty_csv_on_disk_matches_the_reproducible_build() -> None:
    """`scripts/build_argentina_eras.py` es reproducible (ADR 013 secc. 4,
    literal): lo que esta comiteado en `cohorts_loyalty.csv` es exactamente
    lo que el script recalcula ahora, celda por celda."""
    for era_builder_name in ("era_1983_2001", "era_2003_2015", "era_2015_2023"):
        era = getattr(BUILD, era_builder_name)()
        rows, _errors = BUILD.build_loyalty_rows(era)
        on_disk = (BUILD.ERAS_DIR / era["id"] / "cohorts_loyalty.csv").read_text(encoding="utf-8")
        recomputed = "cohort_id,party_id,loyalty,turnout\r\n" + "".join(
            f"{r['cohort_id']},{r['party_id']},{r['loyalty']},{r['turnout']}\r\n" for r in rows
        )
        # Comparacion por filas (no por bytes: `csv.DictWriter` decide el
        # line-ending) -- lo que importa es "mismo contenido", no el CRLF/LF.
        on_disk_rows = [line for line in on_disk.replace("\r\n", "\n").splitlines() if line]
        recomputed_rows = [line for line in recomputed.replace("\r\n", "\n").splitlines() if line]
        assert on_disk_rows == recomputed_rows, era["id"]


# ---------------------------------------------------------------------------
# 3. Corrida 2019-12 -> 2023-12: LLA existe desde 2021-01; con aprobacion <
#    30 y confianza < 35 sostenidas, gana en >= 30% de 20 semillas; con
#    aprobacion 55, en < 5% (ADR 013 secc. 5/6 punto 3).
# ---------------------------------------------------------------------------

N_SEEDS_LLA = 20


def _run_2019_to_2023(seed: int, approval: float, confidence: float):
    pack = load_country_pack("argentina", "2019-12", 48)
    country = pack.country.model_copy(
        update={
            "initial_state": pack.country.initial_state.model_copy(
                update={
                    "government_approval": approval,
                    "institutional_confidence": confidence,
                }
            )
        }
    )
    return run(
        seed=seed,
        months=48,
        country=country,
        actors=pack.era.actors,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
        loyalty_table=pack.era.loyalty_table,
        regime_calendar=pack.regime_calendar,
        macro_coefficients=pack.macro_coefficients,
        macro_x0=pack.macro_x0,
        macro_m0=pack.macro_m0,
        fx_regime=pack.fx_regime_auto,
    )


def _lla_win_rate(approval: float, confidence: float, n_seeds: int = N_SEEDS_LLA) -> float:
    wins = 0
    for seed in range(1, n_seeds + 1):
        history = _run_2019_to_2023(seed, approval, confidence)
        if history.election_records and history.election_records[-1].winner == "lla":
            wins += 1
    return wins / n_seeds


def test_lla_does_not_exist_before_its_founding() -> None:
    """ADR 013 secc. 5, literal: "no existe hasta su fundacion" (2021-01)."""
    pack = load_country_pack("argentina", "2019-12", 48)
    country = pack.country
    history = run(
        seed=1,
        months=13,  # 2019-12 .. 2020-12: LLA (2021-01) no fundado en toda la corrida.
        country=country,
        actors=pack.era.actors,
        actors_enabled=True,
        cohorts_enabled=True,
        elections_enabled=True,
        loyalty_table=pack.era.loyalty_table,
    )
    # Ningun `VoteRecord`/eleccion de esta corrida corta puede tener a LLA
    # (no hay eleccion dentro de 13 meses de un mandato de 48, asi que lo que
    # se prueba es el gate de `is_active`, directo):
    from republica.world.eras import party_exists

    assert party_exists(2021, "2019-12") is False
    assert party_exists(2021, "2020-12") is False
    assert party_exists(2021, "2021-01") is True
    assert history.records  # la corrida corrio igual (no rompe nada)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ADR 013 secc. 6 punto 3: medido en este entorno, LLA gana 0/20 semillas incluso con "
        "aprobacion=confianza=10 sostenidas (vs. el >=30% pedido); con aprobacion=confianza=55 "
        "gana 0/20 (cumple el <5%, pero el punto exigido es el primero). Ver 'Notas de "
        "implementacion' de docs/ADR_013_argentine_parties_actors.md para el mecanismo (el "
        "balotaje, no el termino outsider, es el cuello de botella)."
    ),
)
def test_lla_wins_more_often_under_sustained_distrust() -> None:
    neutral_rate = _lla_win_rate(approval=55.0, confidence=55.0)
    assert neutral_rate < 0.05, f"LLA gano {neutral_rate:.0%} de {N_SEEDS_LLA} semillas neutras"
    bad_rate = _lla_win_rate(approval=25.0, confidence=30.0)
    assert bad_rate >= 0.30, (
        f"LLA gano solo {bad_rate:.0%} de {N_SEEDS_LLA} semillas con aprobacion/confianza bajas "
        "(ADR 013 secc. 6 punto 3 pide >= 30%)"
    )


# ---------------------------------------------------------------------------
# 4. Cambio de epoca en la eleccion de 2015 en una corrida 2011-12 ->
#    2019-12: los partidos de la epoca siguiente aparecen y el JSONL
#    registra `era_change` (ADR 013 secc. 1/6 punto 4).
# ---------------------------------------------------------------------------


def test_era_change_at_the_2015_boundary_election() -> None:
    # 2011-12 no es una de las 8 fechas hito de `initial_states` (ADR 011
    # secc. 2): `initial_state_override` con el estado de 1998-01 (misma
    # epoca, 2003-2015 la cubre igual desde 2003 -- el estado prestado solo
    # necesita sobrevivir la corrida, no ser el real de 2011-12; lo que este
    # test prueba es el mecanismo de cruce de epoca, no macro real).
    borrowed_state = load_country_pack(
        "argentina", "1998-01", 12
    ).country.initial_state.model_dump()
    pack = load_country_pack("argentina", "2011-12", 96, initial_state_override=borrowed_state)
    assert pack.era.active_era is not None
    assert pack.era.active_era.id == "2003-2015"
    assert pack.era.era_boundaries == {48: "2015-2023"}
    # Union de partidos de las dos epocas ya en el overlay (ADR 013 secc. 1:
    # "los partidos nuevos entran con seats 0").
    party_ids = {p["id"] for p in pack.era.parties}
    assert party_ids >= {"fpv_pj", "ucr", "pj_disidente", "ari_cc"}  # 2003-2015
    assert party_ids >= {"cambiemos_jxc", "fpv_fdt_pj", "fit_u", "uca_otros_2015"}  # 2015-2023
    crossing = next(p for p in pack.era.parties if p["id"] == "cambiemos_jxc")
    assert crossing["seats"] == 0  # nunca tuvo bancas EN ESTA corrida, aunque ya existiera

    history = run(
        seed=1,
        months=96,
        country=pack.country,
        actors=pack.era.actors,
        actors_enabled=True,
        congress_enabled=True,
        negotiation_enabled=True,
        cohorts_enabled=True,
        media_enabled=True,
        memory_enabled=True,
        elections_enabled=True,
        loyalty_table=pack.era.loyalty_table,
        regime_calendar=pack.regime_calendar,
        fx_regime=pack.fx_regime_auto,
    )
    assert len(history.records) >= 48, "la corrida deberia sobrevivir hasta la eleccion de 2015"
    crossing_elections = [e for e in history.election_records if e.era_change]
    assert crossing_elections, "ninguna eleccion registro era_change"
    boundary_election = crossing_elections[0]
    assert boundary_election.month == 48
    assert boundary_election.era_change == "2015-2023"
    assert set(boundary_election.first_round) == {
        "cambiemos_jxc",
        "fpv_fdt_pj",
        "fit_u",
        "uca_otros_2015",
    }

    # El mismo registro en el JSONL (no solo en el objeto en memoria).
    all_dicts = [json.loads(line) for line in history.to_jsonl().splitlines()]
    election_dicts = [d for d in all_dicts if d.get("kind") == "election"]
    boundary_dict = next(d for d in election_dicts if d["month"] == 48)
    assert boundary_dict["era_change"] == "2015-2023"
    # Ninguna eleccion DESPUES de la frontera (ya establecida, sin otra por
    # cruzar en esta corrida de 96 meses) trae la clave (ADR 012, fix de
    # golden documentado en docs/ADR_012_argentine_macro.md: se omite cuando
    # es `None`, no se serializa como `null`).
    post_boundary = [d for d in election_dicts if d["month"] > 48]
    assert post_boundary and all("era_change" not in d for d in post_boundary)


# ---------------------------------------------------------------------------
# 5. Golden de Aurora intacto (ADR 013 secc. 6 punto 5).
# ---------------------------------------------------------------------------


def test_aurora_golden_hash_still_intact() -> None:
    from tests.test_country_pack_argentina import (
        test_aurora_without_country_matches_golden_hash_pre_a2 as _golden_test,
    )

    _golden_test()
