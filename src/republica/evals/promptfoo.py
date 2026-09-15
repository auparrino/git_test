"""`republica eval export-promptfoo` (ADR 007 secc. 4): genera
`evals/promptfoo/promptfooconfig.yaml` + `cases.yaml` desde
`data/evals/cases/` -- archivos nomas, Promptfoo no es una dependencia de
Python (ADR secc. 4, literal)."""

from __future__ import annotations

from pathlib import Path

import yaml

from republica.evals.cases import EvalCase, load_cases

#: Provider de ejemplo (ADR secc. 4, literal: "providers: ollama:chat:
#: qwen3:8b"). Documental: cambiarlo no afecta a `republica eval` (Promptfoo
#: corre aparte, fuera de este repo Python).
DEFAULT_PROVIDER = "ollama:chat:qwen3:8b"

PROMPT_TEMPLATE = (
    "Sos {{actor}}. Tu ideologia y tus intereses estan en tu ficha de "
    "Republica Artificial. Ante esta propuesta: {{label}} (delta: "
    "{{policy_delta}}), con estos indicadores publicos: {{public_indicators}}, "
    "respondé SOLO con un JSON {position: support|oppose|neutral|negotiate, "
    "intensity: 0-1}."
)


def _case_to_test(case: EvalCase) -> dict:
    return {
        "description": case.id,
        "vars": {
            "actor": case.actor,
            "label": case.perception.proposal.label if case.perception.proposal else "",
            "policy_delta": dict(case.perception.proposal.policy_delta)
            if case.perception.proposal
            else {},
            "public_indicators": dict(case.perception.public_indicators),
        },
        "assert": [
            {
                "type": "javascript",
                "value": (f"JSON.parse(output).position === {case.expected.position!r}"),
            }
        ],
    }


def export_promptfoo(out_dir: str | Path) -> list[Path]:
    """Escribe `promptfooconfig.yaml` + `cases.yaml` en `out_dir` (default
    `evals/promptfoo/`, ADR secc. 4). Devuelve `[config_path, cases_path]`."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    cases = load_cases()

    cases_doc = {"tests": [_case_to_test(c) for c in cases]}
    cases_path = d / "cases.yaml"
    cases_path.write_text(
        yaml.safe_dump(cases_doc, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )

    config_doc = {
        "description": "Republica Artificial -- casos de evals (ADR 007 secc. 2) como dataset "
        "de Promptfoo, para comparar variantes de prompt/modelo.",
        "prompts": [PROMPT_TEMPLATE],
        "providers": [DEFAULT_PROVIDER],
        "tests": "file://cases.yaml:tests",
    }
    config_path = d / "promptfooconfig.yaml"
    config_path.write_text(
        yaml.safe_dump(config_doc, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return [config_path, cases_path]
