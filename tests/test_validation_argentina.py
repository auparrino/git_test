"""Tests de A4 (ADR 011 secc. 8): validacion historica de Argentina.

Cubren (a) que las hipotesis registradas en el codigo sean LITERALMENTE las
de la tabla del ADR 011 secc. 8 -- si alguien edita el ADR despues de correr
A4, el test falla y obliga a re-registrar en vez de reescribir la hipotesis
para que de --, (b) un smoke test por prueba de `republica validate
--seeds 2 --months-cap 6`, y (c) que el reporte generado traiga los cuatro
veredictos y la frase fija de `PLAN_ARGENTINA.md` secc. 4.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from republica.calibration.run import HONESTY_SENTENCE
from republica.validation.argentina import (
    ADR_FORCED_SHOCKS,
    HYPOTHESES,
    METRICS,
    TESTS,
    TESTS_BY_ID,
    bootstrap_ci,
    build_registration,
    control_verdict,
    month_date,
    resolve_forced_shocks,
    run_validation,
)
from republica.world.countries import country_pack_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = REPO_ROOT / "docs" / "ADR_011_country_pack_argentina.md"
PLAN_PATH = REPO_ROOT / "docs" / "PLAN_ARGENTINA.md"


def _adr_section_8_rows() -> dict[str, list[str]]:
    """Filas de la tabla de ADR 011 secc. 8, indexadas por prueba
    (`V1`/`V2`/`V3`/`C`): `[estado inicial, shocks forzados, hipotesis,
    metrica]`."""
    text = ADR_PATH.read_text(encoding="utf-8")
    section = text.split("## 8. Validación histórica")[1].split("## 9.")[0]
    rows: dict[str, list[str]] = {}
    for line in section.splitlines():
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] == "Prueba":
            continue
        test_id = cells[0].split()[0]
        rows[test_id] = cells[1:]
    return rows


def test_hypotheses_match_adr_text() -> None:
    """Las hipotesis del codigo son el texto literal del ADR (deliverable 4:
    "hypotheses in the code equal the ADR text")."""
    rows = _adr_section_8_rows()
    assert set(rows) == {"V1", "V2", "V3", "C"}
    for test_id, cells in rows.items():
        assert HYPOTHESES[test_id] == cells[2], (
            f"La hipotesis de {test_id} en el codigo no coincide con el ADR 011 secc. 8.\n"
            f"codigo: {HYPOTHESES[test_id]!r}\nADR:    {cells[2]!r}"
        )
        assert METRICS[test_id] == cells[3]
        assert ADR_FORCED_SHOCKS[test_id] == cells[1]


def test_honesty_sentence_matches_plan() -> None:
    """La frase fija sale de `PLAN_ARGENTINA.md` secc. 4, no de una copia a
    mano."""
    plan = PLAN_PATH.read_text(encoding="utf-8")
    normalized = " ".join(plan.split())
    assert " ".join(HONESTY_SENTENCE.split()) in normalized


def test_tests_match_adr_start_dates_and_regime() -> None:
    """Estado inicial y `fx_regime` de cada prueba, tambien contra el ADR."""
    rows = _adr_section_8_rows()
    assert TESTS_BY_ID["V1"].start in rows["V1"][0]
    assert TESTS_BY_ID["V2"].start in rows["V2"][0]
    assert "peg" in rows["V2"][0] and TESTS_BY_ID["V2"].fx_regime == "peg"
    assert TESTS_BY_ID["V3"].start in rows["V3"][0]
    # V4 (A5, ADR 012 secc. 6) no viene del ADR 011: se compara aparte.
    assert [t.months for t in TESTS if t.test_id != "V4"] == [24, 54, 96]
    assert TESTS_BY_ID["V4"].start == "2019-12"
    assert TESTS_BY_ID["V4"].months == 48


def test_month_date_indexes_from_one() -> None:
    assert month_date("2016-01", 1) == "2016-01"
    assert month_date("2016-01", 48) == "2019-12"
    assert month_date("2016-01", 96) == "2023-12"
    assert month_date("1988-06", 24) == "1990-05"


def test_resolve_forced_shocks_never_invents_a_row() -> None:
    """El resolvedor consulta `politics/shocks_calendar.csv`: lo que el
    calendario no tiene, no se fuerza (PLAN_ARGENTINA.md secc. 0.1). Desde
    A5 (ADR 012 secc. 6, "completar el calendario de shocks") el calendario
    SI tiene las filas que V2/V3 piden -- a diferencia de A4, donde
    quedaban `unmatched` (diagnostico que motivo esta ronda)."""
    pack_dir = country_pack_dir("argentina")

    v1 = resolve_forced_shocks(pack_dir, TESTS_BY_ID["V1"], 24)
    assert v1.forced == {}, "V1 no debe forzar ningun shock (ADR: solo exogenos)"

    v2 = resolve_forced_shocks(pack_dir, TESTS_BY_ID["V2"], 54)
    # A5 agrego `international_crisis` 1998-08-17 (contagio ruso/brasileño)
    # al calendario: ya no queda `unmatched`.
    assert v2.forced == {8: ["international_crisis"]}
    assert month_date("1998-01", 8) == "1998-08"
    assert v2.unmatched == []

    v3 = resolve_forced_shocks(pack_dir, TESTS_BY_ID["V3"], 96)
    applied = {m: ids for m, ids in sorted(v3.forced.items())}
    # A5 agrego la sequia de la campaña 2017/2018 (mes 25); la de 2023 (mes
    # 85) y la pandemia (mes 51) ya estaban desde A1.
    assert applied == {25: ["drought"], 51: ["epidemic"], 85: ["drought"]}
    assert month_date("2016-01", 25) == "2018-01"
    assert month_date("2016-01", 51) == "2020-03"
    assert month_date("2016-01", 85) == "2023-01"
    assert v3.unmatched == []


def test_hyperinflation_is_never_forced_in_any_test() -> None:
    """ADR 011 secc. 4: `hyperinflation_regime` se espera que emerja solo."""
    pack_dir = country_pack_dir("argentina")
    for test in TESTS:
        plan = resolve_forced_shocks(pack_dir, test, test.months)
        forced_ids = {sid for ids in plan.forced.values() for sid in ids}
        assert "hyperinflation_regime" not in forced_ids


def test_bootstrap_ci_brackets_the_point_estimate() -> None:
    import statistics

    values = [0.0] * 40 + [1.0] * 10
    lo, hi = bootstrap_ci(values, statistics.mean, resamples=500, seed=7)
    assert lo is not None and hi is not None
    assert lo <= statistics.mean(values) <= hi
    assert bootstrap_ci([], statistics.mean) == (None, None)


def test_registration_is_built_without_running_anything() -> None:
    """El registro previo trae hipotesis, shocks forzados y procedencia del
    estado inicial (deliverable 1: "record BEFORE the run")."""
    reg = build_registration([TESTS_BY_ID[t] for t in ("V1", "V2", "V3")], None, "a3_main", 50)
    assert reg["registered_before_running"] is True
    assert reg["honesty_sentence"] == HONESTY_SENTENCE
    by_id = {e["test_id"]: e for e in reg["tests"]}
    assert set(by_id) == {"V1", "V2", "V3"}
    for test_id, entry in by_id.items():
        assert entry["hypothesis"] == HYPOTHESES[test_id]
        counts = entry["initial_state_provenance"]["counts"]
        assert sum(counts.values()) == entry["initial_state_provenance"]["n_variables"] == 21
        assert counts["source"] >= 1
    assert by_id["V1"]["initial_state_provenance"]["counts"] == {
        "source": 5,
        "proxy": 1,
        "assumed": 15,
    }
    assert by_id["V2"]["fx_regime"] == "peg"


@pytest.mark.parametrize("test_id", ["V1", "V2", "V3"])
def test_validate_smoke_per_test(test_id: str, tmp_path: Path) -> None:
    """Smoke test por prueba: `validate --seeds 2 --months-cap 6`."""
    out = tmp_path / test_id
    payload = run_validation(
        out,
        seeds=2,
        months_cap=6,
        test_ids=[test_id],
        resamples=50,
        make_plots=False,
    )
    assert (out / "registration.json").exists()
    assert (out / "results.json").exists()
    assert (out / "report.md").exists()
    assert len(payload["tests"]) == 1
    entry = payload["tests"][0]
    assert entry["test_id"] == test_id
    assert entry["months"] == 6
    for arm in ("calibrated", "aurora"):
        assert "passes" in entry["metrics"][arm]
    registration = json.loads((out / "registration.json").read_text(encoding="utf-8"))
    assert registration["tests"][0]["hypothesis"] == HYPOTHESES[test_id]


def test_report_has_four_verdicts_and_the_fixed_sentence(tmp_path: Path) -> None:
    """El reporte trae los cuatro veredictos (V1, V2, V3, C) y la frase fija
    de `PLAN_ARGENTINA.md` secc. 4 (deliverable 4)."""
    out = tmp_path / "all"
    payload = run_validation(out, seeds=2, months_cap=6, resamples=50, make_plots=False)
    report = (out / "report.md").read_text(encoding="utf-8")

    header, *rows = [
        line for line in report.splitlines() if line.startswith("| V") or line.startswith("| C")
    ]
    assert header.startswith("| V1")
    for test_id in ("V1", "V2", "V3"):
        assert re.search(rf"^\| {test_id} \|.*\*\*(NO )?CUMPLIDA\*\*", report, re.M), test_id
    assert "**C Control.**" in report
    assert HYPOTHESES["C"] in report
    assert report.count("CUMPLIDA") >= 4

    assert "## Qué aprendimos del modelo" in report
    assert "## Qué NO se puede concluir" in report
    assert report.rstrip().endswith(HONESTY_SENTENCE)
    assert payload["honesty_sentence"] == HONESTY_SENTENCE
    assert "passes" in payload["control_verdict"]


def test_control_verdict_counts_aurora_failures() -> None:
    class _Fake:
        def __init__(self, test_id: str, cal: bool, aur: bool) -> None:
            self.test_id = test_id
            self.metrics_by_arm = {"calibrated": {"passes": cal}, "aurora": {"passes": aur}}

    verdict = control_verdict(
        [_Fake("V1", False, False), _Fake("V2", True, True), _Fake("V3", False, True)]  # type: ignore[list-item]
    )
    assert verdict["aurora_failed_tests"] == ["V1"]
    assert verdict["calibrated_passed_tests"] == ["V2"]
    assert verdict["passes"] is True

    none_failed = control_verdict([_Fake("V1", True, True)])  # type: ignore[list-item]
    assert none_failed["passes"] is False


def test_validate_cli_smoke(tmp_path: Path) -> None:
    """La CLI `republica validate` corre de punta a punta y escribe todo."""
    out = tmp_path / "cli"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "republica.cli",
            "validate",
            "--country",
            "argentina",
            "--calibration",
            "a3_main",
            "--seeds",
            "2",
            "--months-cap",
            "6",
            "--tests",
            "V1",
            "--no-plots",
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "report.md").exists()
    assert "NO CUMPLIDA" in result.stdout or "CUMPLIDA" in result.stdout


def test_validate_cli_rejects_other_countries(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "republica.cli",
            "validate",
            "--country",
            "aurora",
            "--out",
            str(tmp_path / "x"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode != 0
    assert "argentina" in (result.stdout + result.stderr)
