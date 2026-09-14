"""Prompts del actor IA (ADR 004 secc. 4).

`render_system(actor)` construye el prompt de sistema (identidad + ideologia
en palabras + personalidad en palabras + las 3 reglas duras) SOLO desde el
`ActorSheet`. `render_user(perception, allowed_actions)` arma el prompt de
usuario SOLO desde la `Perception` del actor (mas la lista de acciones
permitidas de su rol, que no es informacion de estado sino la matriz de
permisos -- ver `engine/permissions.py` -- por eso se pasa aparte y no rompe
la regla "solo lo que la Perception contiene"): nunca ven `WorldState`
completo. `str.format`/f-strings simples, sin dependencia nueva de
templating (ADR 004 secc. 4: "plantillas Jinja-like simples").
"""

from __future__ import annotations

from republica.actors.sheet import ActorSheet
from republica.engine.actions import PARAM_SCHEMAS, ActionType
from republica.engine.perception import Perception

#: Version del prompt (ADR 004 secc. 4): se registra en cada `DecisionTrace`;
#: cualquier cambio de plantilla la incrementa.
PROMPT_VERSION = "v4.0"

ROLE_LABELS: dict[str, str] = {
    "president": "presidente/a",
    "economy_minister": "ministro/a de Economia",
    "central_bank": "presidente/a del Banco Central",
    "governor": "gobernador/a",
    "party": "lider de un partido politico",
    "union": "secretario/a general de un sindicato",
    "business": "empresario/a",
    "media": "director/a de un medio de comunicacion",
    "social_bloc": "vocero/a de un bloque social",
}


def _bucket(
    value: float, low: float, high: float, low_label: str, mid_label: str, high_label: str
) -> str:
    if value < low:
        return low_label
    if value > high:
        return high_label
    return mid_label


def _ideology_phrases(actor: ActorSheet) -> list[str]:
    """Mapeo de los 4 ejes de `ideology` a frases (ADR 004 secc. 4). Umbrales
    (+-0.3) inventados para v0.4, del mismo orden que otros umbrales
    "tibio/marcado" del proyecto (ver ADR 003 secc. 11 punto 1, revision
    v0.3 de `ideological_fit`)."""
    ideo = actor.ideology
    return [
        _bucket(
            ideo.economic,
            -0.3,
            0.3,
            "En economia, favorece un Estado activo (mas gasto, mas regulacion).",
            "En economia, no tiene una posicion extrema; evalua caso por caso.",
            "En economia, favorece el libre mercado (menos gasto, menos regulacion).",
        ),
        _bucket(
            ideo.social,
            -0.3,
            0.3,
            "En lo social, tiene una agenda conservadora/tradicional.",
            "En lo social, tiene una agenda moderada.",
            "En lo social, tiene una agenda progresista.",
        ),
        _bucket(
            ideo.federalism,
            -0.3,
            0.3,
            "Prioriza al gobierno central por sobre las provincias.",
            "No tiene una postura marcada sobre el reparto de poder entre Nacion y provincias.",
            "Es fuertemente federalista: defiende la autonomia provincial.",
        ),
        _bucket(
            ideo.institutionalism,
            -0.3,
            0.3,
            "Prefiere resultados rapidos aunque se salteen formalidades institucionales.",
            "Respeta las instituciones sin ser rigido al respecto.",
            "Es fuertemente institucionalista: le importan las formas y los procedimientos.",
        ),
    ]


def _personality_phrases(actor: ActorSheet) -> list[str]:
    """Mapeo de `personality` a frases (ADR 004 secc. 4). Umbral 0.6/0.4
    (alto/bajo) inventado, simetrico sobre el punto medio 0.5."""
    p = actor.personality
    phrases = [
        _bucket(
            p.ambition,
            0.4,
            0.6,
            "Tiene bajo perfil publico; prefiere no exponerse.",
            "Tiene un perfil publico moderado.",
            "Es ambicioso/a y busca protagonismo publico.",
        ),
        _bucket(
            p.risk_tolerance,
            0.4,
            0.6,
            "Es cauto/a: evita confrontaciones abiertas.",
            "Tiene una tolerancia al riesgo moderada.",
            "Esta dispuesto/a a escalar un conflicto si hace falta.",
        ),
        _bucket(
            p.loyalty,
            0.4,
            0.6,
            "Cambia de bando con facilidad si le conviene.",
            "Tiene una lealtad moderada a sus alianzas.",
            "Es leal a sus alianzas aun cuando le cueste.",
        ),
        _bucket(
            p.pragmatism,
            0.4,
            0.6,
            "Actua mas por conviccion que por calculo.",
            "Combina conviccion y calculo politico.",
            "Es muy pragmatico/a: prioriza lo que funciona por sobre la doctrina.",
        ),
    ]
    return phrases


#: Las 3 reglas duras (ADR 004 secc. 4, literal).
_HARD_RULES = (
    "1. No inventes hechos que no esten en este mensaje (ni cifras, ni eventos, ni citas).",
    "2. No prometas nada que tu rol no pueda ejecutar (revisa la lista de ACCIONES DISPONIBLES).",
    "3. Da siempre una razon concreta y especifica para lo que decidas, no una frase generica.",
)


def render_system(actor: ActorSheet) -> str:
    """System prompt por rol (ADR 004 secc. 4): identidad + ideologia en
    palabras + personalidad en palabras + las 3 reglas duras. Solo usa el
    `ActorSheet`, nunca el estado del mundo."""
    role_label = ROLE_LABELS.get(actor.role, actor.role)
    lugar = ""
    if actor.province:
        lugar = f" de la provincia {actor.province}"
    elif actor.party:
        lugar = f" del espacio {actor.party}"

    lines = [
        f"Sos {actor.name}, {role_label}{lugar} en la Republica Artificial.",
        "Jugas este rol en una simulacion politica: tus decisiones tienen consecuencias "
        "reales dentro del juego, pero no sos una IA generica dando consejos: sos este "
        "personaje, con esta ideologia y esta personalidad.",
        "",
        "IDEOLOGIA:",
        *(f"- {p}" for p in _ideology_phrases(actor)),
        "",
        "PERSONALIDAD:",
        *(f"- {p}" for p in _personality_phrases(actor)),
        "",
        "REGLAS:",
        *_HARD_RULES,
        "",
        "Respondes siempre en espanol rioplatense en `public_message` (tu declaracion "
        "publica); `reasoning` (tu razonamiento interno) puede ser en el idioma que "
        "prefieras.",
    ]
    return "\n".join(lines)


def _fmt_indicator_table(indicators: dict[str, float]) -> str:
    if not indicators:
        return "(sin datos)"
    return "\n".join(f"- {key}: {value}" for key, value in indicators.items())


def _fmt_proposal(perception: Perception) -> str:
    proposal = perception.proposal
    if proposal is None or not proposal.delta:
        return "No hay propuesta de gobierno este mes."
    label = proposal.label or "sin etiqueta"
    deltas = ", ".join(f"{k}: {v:+.2f}" for k, v in proposal.delta.items())
    return f"El gobierno propone: {label} ({deltas})."


def _fmt_shocks_events(perception: Perception) -> str:
    lines = []
    if perception.active_shocks:
        lines.append("Shocks activos: " + ", ".join(perception.active_shocks))
    else:
        lines.append("Sin shocks activos.")
    if perception.recent_events:
        lines.append("Eventos recientes: " + ", ".join(perception.recent_events))
    else:
        lines.append("Sin eventos recientes.")
    return "\n".join(lines)


def _fmt_goals(perception: Perception) -> str:
    if not perception.goals:
        return "(sin objetivos declarados)"
    return "\n".join(f"{i + 1}. {g}" for i, g in enumerate(perception.goals))


def _relationship_label(value: int) -> str:
    """Etiquetas de relacion (ADR 004 secc. 4, literal: "hostil < 35, fria,
    neutral, buena > 65"). El ADR no da el corte fria/neutral: se usa el
    punto medio de la ficha (50, `ActorSheet.DEFAULT_RELATIONSHIP`) como
    frontera, documentado como umbral inventado."""
    if value < 35:
        return "hostil"
    if value < 50:
        return "fria"
    if value <= 65:
        return "neutral"
    return "buena"


def _fmt_relationships(perception: Perception) -> str:
    if not perception.relationships:
        return "(sin relaciones registradas)"
    return "\n".join(
        f"- {other}: {value} ({_relationship_label(value)})"
        for other, value in perception.relationships.items()
    )


def _fmt_memories(perception: Perception) -> str:
    if not perception.memories:
        return "(sin memorias todavia -- llega en una fase futura)"
    return "\n".join(f"- {m}" for m in perception.memories)


def _fmt_allowed_actions(allowed_actions: list[ActionType]) -> str:
    if not allowed_actions:
        return "(tu rol no tiene acciones disponibles este mes)"
    lines = []
    for action_type in allowed_actions:
        schema = PARAM_SCHEMAS[action_type]
        params = ", ".join(schema.model_fields.keys())
        params_txt = f" (params: {params})" if params else " (sin params)"
        lines.append(f"- {action_type.value}{params_txt}")
    return "\n".join(lines)


def render_user(perception: Perception, allowed_actions: list[ActionType]) -> str:
    """User prompt (ADR 004 secc. 4), orden exacto de secciones. Solo usa la
    `Perception` (mas `allowed_actions`, la matriz de permisos del rol, que
    no es estado del mundo -- ver docstring del modulo). Test de aceptacion
    4 de ADR 004 secc. 9: el prompt de un gobernador no contiene `reserves`
    exactas (no estan en `private_indicators` de ese rol); el del Banco
    Central si."""
    sections = [
        f"FECHA: {perception.date} (mes {perception.month}) -- "
        f"{perception.months_to_election} meses hasta la eleccion.",
        "",
        "INDICADORES PUBLICOS:",
        _fmt_indicator_table(perception.public_indicators),
        "",
        "TU SITUACION:",
        _fmt_indicator_table(perception.private_indicators),
        "",
        "PROPUESTA DEL GOBIERNO:",
        _fmt_proposal(perception),
        "",
        "SHOCKS ACTIVOS / EVENTOS RECIENTES:",
        _fmt_shocks_events(perception),
        "",
        "TUS OBJETIVOS:",
        _fmt_goals(perception),
        "",
        "TUS RELACIONES:",
        _fmt_relationships(perception),
        "",
        "MEMORIAS RELEVANTES:",
        _fmt_memories(perception),
        "",
        "ACCIONES DISPONIBLES PARA TU ROL:",
        _fmt_allowed_actions(allowed_actions),
        "",
        "INSTRUCCION: respondé solo con el JSON del esquema (ActorDecision), "
        "sin texto adicional antes ni despues.",
    ]
    return "\n".join(sections)
