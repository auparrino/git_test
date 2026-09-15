#!/usr/bin/env python3
"""Genera `data/countries/argentina/eras/<id>/{parties.json,actors/*.yaml,
governance.yaml,cohorts_loyalty.csv}` (ADR 013).

Regenerable: `python scripts/build_argentina_eras.py` sobreescribe las 3
epocas desde cero a partir de:
- `data/countries/argentina/politics/parties/<id>.json` (ejes ideologicos
  `economic`/`social`/`federalism`, ya escritos a mano en A? -- este script
  SOLO les agrega los campos de ADR 013 secc. 2: `seats` real, `founded`,
  `personalism`, `loyalty_seed`, `outsider_bonus`).
- Los shares nacionales reales de la eleccion de apertura de cada epoca
  (1983-12, 2003-05, 2015-12 -- primera vuelta en los 3 casos, ADR 013 secc.
  4/6 punto 2), leidos a mano de `data/countries/argentina/politics/sources/
  electorAr_presi/arg_presi_gral{1983,2003,2015}.csv` y transcriptos aca como
  `OPENING_ELECTION_VOTES` (ver el comentario de cada uno para el mapeo a
  partidos de la epoca y que se excluyo).
- `data/countries/argentina/cohorts.csv` (`world.cohorts.load_cohorts`), para
  `world/eras.py::estimate_loyalties` (ADR 013 secc. 4).

Los actores (presidente/ministro/Banco Central/gobernadores/partidos/CGT-ATE/
UIA/Sociedad Rural/sector financiero/3 medios/5 bloques, ADR 013 secc. 3) y
`governance.yaml` (ADR 013 secc. 1: "copia de la de Aurora con ids
remapeados") son tablas de datos de este script, no derivadas de ningun CSV
-- estan documentadas linea a linea con su `assessment_note` (ideologia/
intereses) y, para presidente/ministro/gobernadores (los unicos con nombre de
persona real, ADR 013 secc. 3), la fuente/confianza de esa asignacion."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from republica.world.cohorts import load_cohorts  # noqa: E402
from republica.world.config import DEFAULT_DATA_DIR  # noqa: E402
from republica.world.eras import estimate_loyalties, reproduction_errors  # noqa: E402

ARG_DIR = DEFAULT_DATA_DIR / "countries" / "argentina"
ERAS_DIR = ARG_DIR / "eras"
POLITICS_PARTIES_DIR = ARG_DIR / "politics" / "parties"

COHORTS = load_cohorts(ARG_DIR / "cohorts.csv")
#: Turnout por cohorte (ADR 013 secc. 4: "si no [hay EPH real], la de
#: Aurora con `note`" -- no se descargo microdato de EPH de participacion
#: electoral por cohorte en este entorno; se usa el turnout ya calibrado de
#: `data/cohorts_loyalty.csv` de Aurora, documentado aca UNA vez para las
#: 3 epocas en vez de repetido por fila del CSV de cada una).
TURNOUT_NOTE = (
    "turnout: no se hallo/descargo microdato de EPH de participacion electoral por "
    "cohorte en este entorno; se reusa el turnout ya calibrado de data/cohorts_loyalty.csv "
    "de Aurora (ADR 013 secc. 4, fallback documentado)."
)
TURNOUT = {
    "urban_workers": 0.65,
    "rural": 0.80,
    "middle_class": 0.85,
    "public_employees": 0.80,
    "young_professionals": 0.60,
    "informal": 0.55,
    "retirees": 0.85,
    "students": 0.50,
}

#: Lealtad uniforme "baja" (ADR 013 secc. 1/5, literal) para un partido que
#: no existe aun en la eleccion de apertura de su propia epoca (recien
#: fundado a mitad de epoca): mismo orden de magnitud que el minimo de
#: Aurora (`alianza_provincial: -0.6`, el partido que menos le gusta a la
#: mayoria de las cohortes en `data/cohorts_loyalty.csv`), sin llegar a ese
#: extremo salvo el caso mas personalista/outsider (LLA).
LOW_SEED = -0.4

# ---------------------------------------------------------------------------
# Elecciones de apertura (ADR 013 secc. 4/6 punto 2): votos reales de
# `politics/sources/electorAr_presi/arg_presi_gral{1983,2003,2015}.csv`,
# mapeados a los partidos de `parties.json` de cada epoca. Partidos NO
# fundados aun a la fecha de apertura (frepaso 1994, pro 2005/fit 2011, lla
# 2021) quedan afuera del mapeo por construccion (`party_exists` los excluye
# de la eleccion de todos modos). Los votos de partidos SIN equivalente en
# la epoca (terceras fuerzas ideologicamente dispersas, sin bancas) se
# EXCLUYEN y el share objetivo se renormaliza sobre los partidos mapeados
# -- documentado caso por caso, es la mayor fuente de imprecision de la
# reproduccion de +-3pp (ADR 013 secc. 4/6 punto 2).
# ---------------------------------------------------------------------------

#: 1983-12 (`arg_presi_gral1983.csv`): 14.904.507 votos validos (excluye
#: 326.678 en blanco + 95.984 nulos). Mapeados: UCR (Alfonsin) 7.724.559,
#: PJ (Luder) 5.995.402, UCEDE (Alsogaray) 25.263, "Partidos De Distrito"
#: 384.302 -> provinciales_1983. Excluidos (774.981 votos, 5.2% de los
#: validos, sin equivalente en la epoca): Intransigente, MID, Alianza
#: Federal, Alianza Democrata Socialista, Democrata Cristiano, MAS,
#: Socialista Popular, FIP, Obrero, Confederacion Nacional De Centro,
#: Conservador Popular. FREPASO no existe (fundado 1994).
OPENING_1983 = {
    "mapped_votes": {
        "ucr": 7_724_559,
        "pj": 5_995_402,
        "ucede": 25_263,
        "provinciales_1983": 384_302,
    },
    "excluded_votes": 774_981,
    "total_valid_votes": 14_904_507,
}

#: 2003-05 (`arg_presi_gral2003.csv`, primera vuelta -- Menem se bajo antes
#: del balotaje real, pero la ADR 013 secc. 4/6 punto 2 pide "primera
#: vuelta" para las 3 epocas): 19.387.895 votos validos (excluye 196.574
#: blanco + 345.642 nulos). Mapeados: FPV (Kirchner) 4.312.517 -> fpv_pj;
#: UCR (Moreau) 453.360 -> ucr; Menem (FpL-UCeDe) 4.740.907 + Rodriguez Saa
#: (Frente Mov. Popular) 2.735.829 = 7.476.736 -> pj_disidente (la nota de
#: `politics/parties/2003-2015.json` nombra explicitamente a ambos: "Menem,
#: Rodriguez Saa, Duhalde"); Carrio (ARI) 2.723.574 -> ari_cc. Excluidos
#: (4.421.708 votos, 22.8% de los validos -- la eleccion mas fragmentada de
#: las 3 anclas, sin equivalente en la epoca): Lopez Murphy (Recrear,
#: 3.173.475 -- el mas cercano ideologicamente seria PRO, que no existe
#: hasta 2005), Izquierda Unida, Socialista, Obrero (el antecedente de FIT,
#: que no existe hasta 2011) y el resto de terceras fuerzas menores. PRO y
#: FIT no existen (fundados 2005/2011).
OPENING_2003 = {
    "mapped_votes": {
        "fpv_pj": 4_312_517,
        "ucr": 453_360,
        "pj_disidente": 4_740_907 + 2_735_829,
        "ari_cc": 2_723_574,
    },
    "excluded_votes": 19_387_895 - (4_312_517 + 453_360 + 4_740_907 + 2_735_829 + 2_723_574),
    "total_valid_votes": 19_387_895,
}

#: 2015-12 (`arg_presi_gral2015.csv`, primera vuelta -- Macri gano el
#: balotaje de nov-2015, pero la ADR pide primera vuelta): 25.184.257 votos
#: validos (excluye 664.740 blanco + 199.449 nulos). Mapeados: Cambiemos
#: (Macri) 8.601.131; FPV (Scioli) 9.338.490 -> fpv_fdt_pj; FIT (Del Cano)
#: 812.530 -> fit_u; Massa (UNA) 5.386.977 + Rodriguez Saa (Compromiso
#: Federal) 412.578 = 5.799.555 -> uca_otros_2015 (la nota de
#: `politics/parties/2015-2023.json` nombra explicitamente "UNA/Massa,
#: Compromiso Federal"). Excluido (632.551 votos, 2.5% de los validos):
#: Stolbizer (Progresistas), sin equivalente en la epoca. LLA no existe
#: (fundado 2021).
OPENING_2015 = {
    "mapped_votes": {
        "cambiemos_jxc": 8_601_131,
        "fpv_fdt_pj": 9_338_490,
        "fit_u": 812_530,
        "uca_otros_2015": 5_386_977 + 412_578,
    },
    "excluded_votes": 632_551,
    "total_valid_votes": 25_184_257,
}


def _targets(opening: dict) -> dict[str, float]:
    mapped_total = sum(opening["mapped_votes"].values())
    return {pid: v / mapped_total for pid, v in opening["mapped_votes"].items()}


# ---------------------------------------------------------------------------
# Gobernanza por rol (ADR 013 secc. 1: "copia de la de Aurora con ids
# remapeados"): un template por ROL, transcripto de `data/governance.yaml`
# (ADR 007 secc. 6) -- las 29 fichas de Aurora comparten `read`/`write`/
# `execute`/`max_authority`/`budget` por rol, `autonomy`/
# `human_approval_required` distinguen solo a `central_bank`.
# ---------------------------------------------------------------------------

GOVERNANCE_BY_ROLE: dict[str, dict] = {
    "president": {
        "autonomy": 5,
        "read": [
            "economic_indicators",
            "monetary_history",
            "government_announcements",
            "provincial_finances",
            "party_polls",
            "labour_market",
            "sector",
            "media_events",
            "cohort_view",
        ],
        "write": ["CAMPAIGN", "NO_ACTION", "PROMISE", "PROPOSE_POLICY", "PUBLIC_STATEMENT"],
        "execute": ["ENACT_POLICY", "GRANT_CONCESSION"],
        "human_approval_required": False,
        "max_authority": "full_catalog",
        "tokens_per_turn": 4000,
    },
    "economy_minister": {
        "autonomy": 5,
        "read": [
            "economic_indicators",
            "monetary_history",
            "government_announcements",
            "provincial_finances",
            "party_polls",
            "labour_market",
            "sector",
            "media_events",
            "cohort_view",
        ],
        "write": [
            "NEGOTIATE",
            "NO_ACTION",
            "OPPOSE_POLICY",
            "PROPOSE_POLICY",
            "PUBLIC_STATEMENT",
            "RECOMMEND_RATE",
            "SUPPORT_POLICY",
        ],
        "execute": [],
        "human_approval_required": False,
        "max_authority": "full_catalog",
        "tokens_per_turn": 3000,
    },
    "central_bank": {
        "autonomy": 2,
        "read": ["economic_indicators", "monetary_history", "government_announcements"],
        "write": [
            "NO_ACTION",
            "OPPOSE_POLICY",
            "PUBLIC_STATEMENT",
            "RECOMMEND_RATE",
            "SUPPORT_POLICY",
        ],
        "execute": ["SET_RATE"],
        "human_approval_required": True,
        "max_authority": "recommendation_only",
        "tokens_per_turn": 2000,
    },
    "governor": {
        "autonomy": 5,
        "read": ["economic_indicators", "provincial_finances", "government_announcements"],
        "write": [
            "BREAK_ALLIANCE",
            "FORM_ALLIANCE",
            "LOBBY_CONGRESS",
            "NEGOTIATE",
            "NO_ACTION",
            "OPPOSE_POLICY",
            "PUBLIC_STATEMENT",
            "REQUEST_FUNDS",
            "SUPPORT_POLICY",
        ],
        "execute": [],
        "human_approval_required": False,
        "max_authority": "full_catalog",
        "tokens_per_turn": 2000,
    },
    "party": {
        "autonomy": 5,
        "read": ["economic_indicators", "party_polls", "government_announcements"],
        "write": [
            "BREAK_ALLIANCE",
            "CALL_PROTEST",
            "CAMPAIGN",
            "FORM_ALLIANCE",
            "LOBBY_CONGRESS",
            "NEGOTIATE",
            "NO_ACTION",
            "OPPOSE_POLICY",
            "PROMISE",
            "PUBLIC_STATEMENT",
            "SUPPORT_POLICY",
        ],
        "execute": [],
        "human_approval_required": False,
        "max_authority": "full_catalog",
        "tokens_per_turn": 2000,
    },
    "union": {
        "autonomy": 5,
        "read": ["economic_indicators", "labour_market", "government_announcements"],
        "write": [
            "BREAK_ALLIANCE",
            "CALL_PROTEST",
            "FORM_ALLIANCE",
            "LOBBY_CONGRESS",
            "NEGOTIATE",
            "NO_ACTION",
            "OPPOSE_POLICY",
            "PUBLIC_STATEMENT",
            "SUPPORT_POLICY",
        ],
        "execute": ["STRIKE"],
        "human_approval_required": False,
        "max_authority": "full_catalog",
        "tokens_per_turn": 2000,
    },
    "business": {
        "autonomy": 5,
        "read": ["economic_indicators", "sector", "government_announcements"],
        "write": [
            "BREAK_ALLIANCE",
            "FORM_ALLIANCE",
            "LOBBY_CONGRESS",
            "NEGOTIATE",
            "NO_ACTION",
            "OPPOSE_POLICY",
            "PUBLIC_STATEMENT",
            "SUPPORT_POLICY",
        ],
        "execute": ["INVEST", "WITHHOLD_INVESTMENT"],
        "human_approval_required": False,
        "max_authority": "full_catalog",
        "tokens_per_turn": 2000,
    },
    "media": {
        "autonomy": 5,
        "read": ["economic_indicators", "media_events", "government_announcements"],
        "write": [
            "CRITICIZE",
            "ENDORSE",
            "NO_ACTION",
            "OPPOSE_POLICY",
            "PUBLIC_STATEMENT",
            "SUPPORT_POLICY",
        ],
        "execute": ["PUBLISH_STORY"],
        "human_approval_required": False,
        "max_authority": "full_catalog",
        "tokens_per_turn": 2000,
    },
    "social_bloc": {
        "autonomy": 5,
        "read": ["economic_indicators", "cohort_view", "government_announcements"],
        "write": [
            "CALL_PROTEST",
            "NO_ACTION",
            "OPPOSE_POLICY",
            "PUBLIC_STATEMENT",
            "SUPPORT_POLICY",
        ],
        "execute": [],
        "human_approval_required": False,
        "max_authority": "full_catalog",
        "tokens_per_turn": 1500,
    },
}


def _governance_entry(role: str) -> dict:
    t = GOVERNANCE_BY_ROLE[role]
    return {
        "model": "rules",
        "autonomy": t["autonomy"],
        "read": list(t["read"]),
        "write": list(t["write"]),
        "execute": list(t["execute"]),
        "human_approval_required": t["human_approval_required"],
        "max_authority": t["max_authority"],
        "budget": {"actions_per_turn": 3, "tokens_per_turn": t["tokens_per_turn"]},
    }


# ---------------------------------------------------------------------------
# Actores institucionales comunes a las 3 epocas (ADR 013 secc. 3: "los 5
# bloques sociales de Aurora mapeados a las cohortes", CGT + ATE, UIA +
# Sociedad Rural + sector financiero): nombres reales de INSTITUCION (no de
# persona -- ADR 013 secc. 3 solo exige nombre de persona real para
# presidente/ministro/gobernador), ideologia/intereses `assessment: analyst`.
# ---------------------------------------------------------------------------

BLOCS = [
    {
        "id": "bloc_urban_workers",
        "name": "Bloque de Trabajadores Urbanos",
        "ideology": {"economic": -0.7, "social": 0.5, "federalism": 0.1, "institutionalism": 0.3},
        "personality": {"ambition": 0.6, "risk_tolerance": 0.65, "loyalty": 0.7, "pragmatism": 0.5},
        "interests": ["real_wages", "employment", "social_programs"],
        "influence": {"public": 0.4, "congress": 0.0, "streets": 0.7, "markets": 0.0},
        "assessment_note": (
            "Obreros de industria/servicios urbanos, cohorte urban_workers de cohorts.csv "
            "(econ_pref -0.5): ideologia distributiva, interes salarial/de empleo directo."
        ),
        "bio": "Trabajadores de fabricas y servicios urbanos, base sindical. Demanda salarios, "
        "empleo y programas sociales; poder de movilizacion callejero.",
    },
    {
        "id": "bloc_rural",
        "name": "Bloque de Productores Rurales",
        "ideology": {"economic": 0.5, "social": 0.0, "federalism": 0.6, "institutionalism": 0.5},
        "personality": {"ambition": 0.55, "risk_tolerance": 0.6, "loyalty": 0.5, "pragmatism": 0.6},
        "interests": ["agricultural_exports", "low_taxes"],
        "influence": {"public": 0.25, "congress": 0.05, "streets": 0.35, "markets": 0.15},
        "assessment_note": (
            "Chacareros/productores agropecuarios, cohorte rural de cohorts.csv (econ_pref 0.4): "
            "interes exportador y de baja presion tributaria sobre el campo."
        ),
        "bio": "Productores agropecuarios del interior. Sensibles a retenciones/tipo de cambio, "
        "capacidad de corte de rutas y protesta sectorial.",
    },
    {
        "id": "bloc_middle_class",
        "name": "Bloque de Clase Media",
        "ideology": {"economic": 0.3, "social": 0.1, "federalism": 0.0, "institutionalism": 0.6},
        "personality": {
            "ambition": 0.55,
            "risk_tolerance": 0.45,
            "loyalty": 0.4,
            "pragmatism": 0.6,
        },
        "interests": ["price_stability", "financial_stability"],
        "influence": {"public": 0.45, "congress": 0.0, "streets": 0.3, "markets": 0.1},
        "assessment_note": (
            "Profesionales/cuentapropistas urbanos, cohorte middle_class (econ_pref 0.5): "
            "prioridad antiinflacionaria y de estabilidad financiera (ahorros en pesos/dolares)."
        ),
        "bio": "Clase media urbana profesional y de servicios. Muy sensible a inflacion y "
        "estabilidad cambiaria; voto volatil entre eleccion y eleccion.",
    },
    {
        "id": "bloc_public_employees",
        "name": "Bloque de Empleados Publicos",
        "ideology": {"economic": -0.6, "social": 0.2, "federalism": -0.2, "institutionalism": 0.5},
        "personality": {"ambition": 0.5, "risk_tolerance": 0.4, "loyalty": 0.65, "pragmatism": 0.5},
        "interests": ["public_employment", "real_wages"],
        "influence": {"public": 0.3, "congress": 0.0, "streets": 0.4, "markets": 0.0},
        "assessment_note": (
            "Planta del Estado nacional/provincial, cohorte public_employees (econ_pref -0.6): "
            "interes directo en el nivel de empleo publico y el salario real estatal."
        ),
        "bio": "Empleo publico nacional y provincial. Defiende planta y salario estatal, "
        "capacidad de protesta gremial via ATE.",
    },
    {
        "id": "bloc_informal",
        "name": "Bloque de Trabajadores Informales",
        "ideology": {"economic": -0.5, "social": 0.3, "federalism": 0.1, "institutionalism": 0.1},
        "personality": {
            "ambition": 0.45,
            "risk_tolerance": 0.55,
            "loyalty": 0.55,
            "pragmatism": 0.45,
        },
        "interests": ["employment", "social_programs"],
        "influence": {"public": 0.2, "congress": 0.0, "streets": 0.55, "markets": 0.0},
        "assessment_note": (
            "Trabajadores sin relacion de dependencia formal, cohorte informal (econ_pref -0.3, "
            "el trust mas bajo de cohorts.csv, 30): interes en empleo y contencion social directa, "
            "bajo apego institucional."
        ),
        "bio": "Economia informal/changas, el segmento de menor ingreso y mayor precariedad. "
        "Muy sensible a planes sociales y al empleo, bajo apego institucional.",
    },
]

UNIONS = [
    {
        "id": "union_cgt",
        "name": "Confederacion General del Trabajo",
        "ideology": {"economic": -0.6, "social": 0.3, "federalism": 0.0, "institutionalism": 0.5},
        "personality": {"ambition": 0.6, "risk_tolerance": 0.6, "loyalty": 0.6, "pragmatism": 0.55},
        "interests": ["real_wages", "employment", "social_programs"],
        "influence": {"public": 0.4, "congress": 0.25, "streets": 0.65, "markets": 0.05},
        "assessment_note": "Central sindical general, historicamente alineada al PJ/peronismo; "
        "negociadora pero con alta capacidad de movilizacion callejera.",
        "bio": "Confederacion General del Trabajo. Central sindical general, negocia paritarias "
        "y moviliza contra ajustes al salario real.",
    },
    {
        "id": "union_public",
        "name": "Asociacion de Trabajadores del Estado (ATE)",
        "ideology": {"economic": -0.7, "social": 0.4, "federalism": -0.1, "institutionalism": 0.4},
        "personality": {
            "ambition": 0.55,
            "risk_tolerance": 0.55,
            "loyalty": 0.6,
            "pragmatism": 0.5,
        },
        "interests": ["public_employment", "real_wages"],
        "influence": {"public": 0.25, "congress": 0.1, "streets": 0.5, "markets": 0.0},
        "assessment_note": "Sindicato del empleo publico estatal; defiende planta y salario del "
        "Estado, opositor natural a ajustes fiscales via despidos.",
        "bio": "Asociacion de Trabajadores del Estado. Sindicato estatal, defiende empleo publico "
        "y salario de la administracion nacional y provincial.",
    },
]

BUSINESS = [
    {
        "id": "biz_agro",
        "name": "Sociedad Rural Argentina",
        "ideology": {"economic": 0.7, "social": -0.1, "federalism": 0.4, "institutionalism": 0.5},
        "personality": {"ambition": 0.6, "risk_tolerance": 0.55, "loyalty": 0.5, "pragmatism": 0.5},
        "interests": ["agricultural_exports", "low_taxes"],
        "influence": {"public": 0.3, "congress": 0.15, "streets": 0.2, "markets": 0.2},
        "assessment_note": "Entidad patronal del agro pampeano; opone retenciones/controles de "
        "cambio, favorece apertura exportadora.",
        "bio": "Sociedad Rural Argentina. Representa a los grandes productores agropecuarios, "
        "opositora historica a retenciones y controles de cambio.",
    },
    {
        "id": "biz_industry",
        "name": "Union Industrial Argentina",
        "ideology": {"economic": 0.2, "social": 0.0, "federalism": -0.1, "institutionalism": 0.5},
        "personality": {"ambition": 0.6, "risk_tolerance": 0.5, "loyalty": 0.5, "pragmatism": 0.6},
        "interests": ["industrial_protection", "cheap_credit"],
        "influence": {"public": 0.3, "congress": 0.2, "streets": 0.1, "markets": 0.25},
        "assessment_note": "Camara fabril nacional; interes en proteccion arancelaria/credito "
        "barato, mas heterogenea ideologicamente que el agro exportador.",
        "bio": "Union Industrial Argentina. Camara empresaria de la industria manufacturera, "
        "busca proteccion arancelaria y credito accesible.",
    },
    {
        "id": "biz_finance",
        "name": "Asociacion de Bancos de la Argentina (ADEBA)",
        "ideology": {"economic": 0.8, "social": 0.1, "federalism": -0.1, "institutionalism": 0.6},
        "personality": {
            "ambition": 0.65,
            "risk_tolerance": 0.6,
            "loyalty": 0.4,
            "pragmatism": 0.55,
        },
        "interests": ["financial_stability", "cheap_credit"],
        "influence": {"public": 0.15, "congress": 0.15, "streets": 0.0, "markets": 0.55},
        "assessment_note": "Sector financiero/banca privada de capital nacional; maxima "
        "sensibilidad a estabilidad monetaria y riesgo cambiario.",
        "bio": "Asociacion de bancos privados de capital nacional. Sector financiero, alta "
        "sensibilidad a estabilidad monetaria y riesgo de default.",
    },
]

#: `media_mercado`/`media_nacional` (Clarin/La Nacion segun epoca, ADR 013
#: secc. 3) + `media_popular` (Pagina/12 o C5N segun epoca).
MEDIA_BY_ERA = {
    "1983-2001": {
        "media_nacional": (
            "Clarin",
            "Diario de mayor tirada, linea editorial centrista/establishment; "
            "cobertura institucional con creciente peso economico propio.",
        ),
        "media_mercado": (
            "La Nacion",
            "Diario liberal-conservador tradicional, linea editorial "
            "pro-mercado y critica del intervencionismo estatal.",
        ),
        "media_popular": (
            "Pagina/12",
            "Diario de centroizquierda fundado en 1987, cercano a "
            "movimientos sociales y critico del ajuste ortodoxo.",
        ),
    },
    "2003-2015": {
        "media_mercado": (
            "Clarin",
            "Multimedios de mayor alcance del pais; durante el kirchnerismo "
            "se convierte en el principal antagonista editorial del gobierno "
            "(conflicto por la Ley de Medios de 2009).",
        ),
        "media_nacional": (
            "La Nacion",
            "Diario tradicional centroderecha/institucional, critico del "
            "gobierno pero con linea editorial mas moderada que Clarin en este periodo.",
        ),
        "media_popular": (
            "Pagina/12",
            "Diario alineado editorialmente con el kirchnerismo, cobertura "
            "favorable a las politicas de Nestor y Cristina Fernandez de Kirchner.",
        ),
    },
    "2015-2023": {
        "media_nacional": (
            "Clarin",
            "Multimedios de mayor alcance del pais, linea editorial "
            "establishment/centroderecha moderada en este periodo.",
        ),
        "media_mercado": (
            "La Nacion",
            "Diario liberal-conservador, linea editorial pro-mercado, "
            "favorable a Cambiemos/Juntos por el Cambio.",
        ),
        "media_popular": (
            "C5N",
            "Senal de noticias de linea editorial cercana al kirchnerismo/Frente "
            "de Todos, contrapeso de la agenda de Clarin/La Nacion en este periodo.",
        ),
    },
}


def _media_actors(era_id: str) -> list[dict]:
    out = []
    base_ideology_by_slot = {
        "media_mercado": {
            "economic": 0.7,
            "social": 0.0,
            "federalism": -0.1,
            "institutionalism": 0.6,
        },
        "media_nacional": {
            "economic": 0.2,
            "social": 0.1,
            "federalism": -0.1,
            "institutionalism": 0.7,
        },
        "media_popular": {
            "economic": -0.5,
            "social": 0.4,
            "federalism": 0.0,
            "institutionalism": 0.3,
        },
    }
    for slot, (name, note) in MEDIA_BY_ERA[era_id].items():
        out.append(
            {
                "id": slot,
                "name": name,
                "ideology": base_ideology_by_slot[slot],
                "personality": {
                    "ambition": 0.6,
                    "risk_tolerance": 0.5,
                    "loyalty": 0.3,
                    "pragmatism": 0.6,
                },
                "interests": ["audience"],
                "influence": {"public": 0.65, "congress": 0.1, "streets": 0.05, "markets": 0.15},
                "assessment_note": note,
                "bio": note,
            }
        )
    return out


def _actor_sheet(
    id_: str,
    name: str,
    role: str,
    ideology: dict,
    personality: dict,
    interests: list[str],
    influence: dict,
    assessment_note: str,
    bio: str,
    *,
    party: str | None = None,
    province: str | None = None,
    relationships: dict[str, int] | None = None,
) -> dict:
    d = {
        "id": id_,
        "name": name,
        "role": role,
        "ideology": ideology,
        "personality": personality,
        "interests": interests,
        "influence": influence,
        "relationships": relationships or {},
        "bio": bio,
        "assessment": "analyst",
        "assessment_note": assessment_note,
    }
    if party is not None:
        d["party"] = party
    if province is not None:
        d["province"] = province
    return d


#: Personalidad "sin atributos mas alla de lo publico" (ADR 013 secc. 3) para
#: presidente/ministro/gobernador -- personas reales.
REAL_PERSON_PERSONALITY = {
    "ambition": 0.5,
    "risk_tolerance": 0.5,
    "loyalty": 0.5,
    "pragmatism": 0.5,
}
#: Influencia estandar por rol de persona real (misma escala que Aurora).
PRESIDENT_INFLUENCE = {"public": 0.8, "congress": 0.7, "streets": 0.2, "markets": 0.3}
MINISTER_INFLUENCE = {"public": 0.4, "congress": 0.5, "streets": 0.1, "markets": 0.6}
CENTRAL_BANK_INFLUENCE = {"public": 0.2, "congress": 0.1, "streets": 0.0, "markets": 0.7}
GOVERNOR_INFLUENCE = {"public": 0.4, "congress": 0.2, "streets": 0.25, "markets": 0.1}


# ---------------------------------------------------------------------------
# Roster de cada epoca.
# ---------------------------------------------------------------------------


def era_1983_2001() -> dict:
    parties_extra = {
        "ucr": {
            "seats": 51,
            "founded": 1891,
            "personalism": 0.35,
            "discipline": 0.7,
            "seats_confidence": "medium",
            "seats_note": "129/254 bancas reales de Diputados 1983 (~0.51); cruzado en "
            "politics/PENDING_FACTCHECK.md secc. 2.5 contra la composicion real.",
        },
        "pj": {
            "seats": 44,
            "founded": 1946,
            "personalism": 0.6,
            "discipline": 0.75,
            "seats_confidence": "medium",
            "seats_note": "111/254 bancas reales de Diputados 1983 (~0.44); mismo cruce que UCR.",
        },
        "ucede": {
            "seats": 2,
            "founded": 1982,
            "personalism": 0.55,
            "discipline": 0.6,
            "seats_confidence": "low",
            "seats_note": "politics/parties/1983-2001.json (seats_share=0.02).",
        },
        "frepaso": {
            "seats": 0,
            "founded": 1994,
            "personalism": 0.5,
            "discipline": 0.55,
            "loyalty_seed": LOW_SEED,
            "seats_confidence": "n/a",
            "seats_note": "No fundado al inicio de la epoca (ADR 013 secc. 2: seats=0).",
        },
        "provinciales_1983": {
            "seats": 3,
            "founded": None,
            "personalism": 0.4,
            "discipline": 0.4,
            "seats_confidence": "low",
            "seats_note": "politics/parties/1983-2001.json (seats_share=0.03).",
        },
    }
    governors = {
        "buenos_aires": {
            "name": "Alejandro Armendariz",
            "party": "ucr",
            "ideology": {
                "economic": -0.05,
                "social": -0.2,
                "federalism": 0.6,
                "institutionalism": 0.6,
            },
            "interests": ["provincial_transfers", "reelection"],
            "confidence": "alta",
            "bio": "Gobernador de Buenos Aires (UCR), asume el 10-dic-1983.",
        },
        "cordoba": {
            "name": "Eduardo Cesar Angeloz",
            "party": "ucr",
            "ideology": {
                "economic": 0.1,
                "social": -0.1,
                "federalism": 0.5,
                "institutionalism": 0.6,
            },
            "interests": ["provincial_transfers", "industrial_protection"],
            "confidence": "alta",
            "bio": "Gobernador de Cordoba (UCR), asume el 10-dic-1983 (reelecto hasta 1995).",
        },
        "entre_rios": {
            "name": "Bruno Quijano",
            "party": "ucr",
            "ideology": {
                "economic": -0.1,
                "social": -0.1,
                "federalism": 0.5,
                "institutionalism": 0.55,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "media",
            "bio": "Gobernador de Entre Rios (UCR), asume el 10-dic-1983. Confianza media, sin "
            "fuente primaria verificada en este entorno.",
        },
        "tucuman": {
            "name": "Fernando Riera",
            "party": "pj",
            "ideology": {
                "economic": -0.2,
                "social": 0.1,
                "federalism": 0.5,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "employment"],
            "confidence": "media",
            "bio": "Gobernador de Tucuman (PJ), asume el 10-dic-1983. Confianza media, sin "
            "fuente primaria verificada en este entorno.",
        },
        "misiones": {
            "name": "Ricardo Barrios Arrechea",
            "party": "ucr",
            "ideology": {
                "economic": -0.05,
                "social": -0.1,
                "federalism": 0.5,
                "institutionalism": 0.55,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "media",
            "bio": "Gobernador de Misiones (UCR), asume el 10-dic-1983. Confianza media, sin "
            "fuente primaria verificada en este entorno.",
        },
        "mendoza": {
            "name": "Santiago Felipe Llaver",
            "party": "ucr",
            "ideology": {
                "economic": 0.0,
                "social": -0.1,
                "federalism": 0.5,
                "institutionalism": 0.55,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "media",
            "bio": "Gobernador de Mendoza (UCR), asume el 10-dic-1983. Confianza media, sin "
            "fuente primaria verificada en este entorno.",
        },
        "rio_negro": {
            "name": "Osvaldo Alvarez Guerrero",
            "party": "ucr",
            "ideology": {
                "economic": -0.1,
                "social": 0.0,
                "federalism": 0.5,
                "institutionalism": 0.55,
            },
            "interests": ["provincial_transfers", "reelection"],
            "confidence": "media",
            "bio": "Gobernador de Rio Negro (UCR), asume el 10-dic-1983. Confianza media, sin "
            "fuente primaria verificada en este entorno.",
        },
        "caba": {
            "name": "Intendencia de la Ciudad de Buenos Aires (cargo no electivo hasta 1996)",
            "party": "ucr",
            "ideology": {
                "economic": 0.0,
                "social": -0.1,
                "federalism": -0.3,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers"],
            "confidence": "alta (sobre el status institucional, "
            "no sobre un nombre de intendente especifico)",
            "bio": "Antes de la reforma de 1994/la eleccion de 1996, el intendente de la Ciudad "
            "era designado por el Poder Ejecutivo Nacional, no un cargo electivo: se modela el "
            "puesto sin atribuir un nombre individual no verificado.",
        },
    }
    return {
        "id": "1983-2001",
        "parties_extra": parties_extra,
        "targets": _targets(OPENING_1983),
        "opening": OPENING_1983,
        "president": {
            "name": "Raul Alfonsin",
            "party": "ucr",
            "took_office": "1983-12-10",
            "ideology": {
                "economic": -0.1,
                "social": -0.3,
                "federalism": 0.0,
                "institutionalism": 0.8,
            },
            "interests": ["price_stability", "reelection"],
            "bio": "Presidente electo en 1983, primer gobierno democratico tras la dictadura. "
            "Asume el 10-dic-1983.",
        },
        "minister": {
            "name": "Bernardo Grinspun",
            "took_office": "1983-12-10",
            "left_office": "1985-02-19",
            "ideology": {
                "economic": -0.3,
                "social": -0.2,
                "federalism": 0.0,
                "institutionalism": 0.5,
            },
            "interests": ["employment", "real_wages"],
            "bio": "Ministro de Economia (10-dic-1983 a 19-feb-1985), linea desarrollista/"
            "heterodoxa, previo al Plan Austral.",
        },
        "central_bank": {
            "name": "Enrique Garcia Vazquez",
            "took_office": "1983-12-10",
            "left_office": "1985-02",
            "ideology": {
                "economic": -0.1,
                "social": 0.0,
                "federalism": 0.0,
                "institutionalism": 0.6,
            },
            "interests": ["price_stability", "financial_stability"],
            "bio": "Presidente del Banco Central (dic-1983 a feb-1985). Confianza media sobre la "
            "fecha exacta de salida, sin fuente primaria verificada en este entorno.",
        },
        "governors": governors,
    }


def era_2003_2015() -> dict:
    parties_extra = {
        "fpv_pj": {
            "seats": 35,
            "founded": 2003,
            "personalism": 0.65,
            "discipline": 0.8,
            "seats_confidence": "low",
            "seats_note": "politics/parties/2003-2015.json (seats_share=0.35).",
        },
        "ucr": {
            "seats": 15,
            "founded": 1891,
            "personalism": 0.3,
            "discipline": 0.6,
            "seats_confidence": "low",
            "seats_note": "politics/parties/2003-2015.json (seats_share=0.15).",
        },
        "pj_disidente": {
            "seats": 10,
            "founded": 1999,
            "personalism": 0.6,
            "discipline": 0.4,
            "seats_confidence": "low",
            "seats_note": "politics/parties/2003-2015.json (seats_share=0.10).",
        },
        "ari_cc": {
            "seats": 5,
            "founded": 2002,
            "personalism": 0.7,
            "discipline": 0.5,
            "seats_confidence": "low",
            "seats_note": "politics/parties/2003-2015.json (seats_share=0.05).",
        },
        "pro": {
            "seats": 0,
            "founded": 2005,
            "personalism": 0.6,
            "discipline": 0.65,
            "loyalty_seed": LOW_SEED,
            "seats_confidence": "n/a",
            "seats_note": "No fundado al inicio de la epoca (ADR 013 secc. 2: seats=0).",
        },
        "fit": {
            "seats": 0,
            "founded": 2011,
            "personalism": 0.25,
            "discipline": 0.85,
            "loyalty_seed": LOW_SEED,
            "seats_confidence": "n/a",
            "seats_note": "No fundado al inicio de la epoca (ADR 013 secc. 2: seats=0).",
        },
    }
    governors = {
        "buenos_aires": {
            "name": "Felipe Sola",
            "party": "fpv_pj",
            "ideology": {
                "economic": -0.2,
                "social": 0.0,
                "federalism": 0.3,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "reelection"],
            "confidence": "alta",
            "bio": "Gobernador de Buenos Aires (PJ/FPV), en el cargo desde ene-2002, en funciones "
            "en 2003-05.",
        },
        "cordoba": {
            "name": "Jose Manuel de la Sota",
            "party": "pj_disidente",
            "ideology": {
                "economic": 0.1,
                "social": 0.0,
                "federalism": 0.5,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "industrial_protection"],
            "confidence": "alta",
            "bio": "Gobernador de Cordoba (PJ, linea no kirchnerista), primer mandato 1999-2003, "
            "en funciones en 2003-05.",
        },
        "entre_rios": {
            "name": "Jorge Busti",
            "party": "fpv_pj",
            "ideology": {
                "economic": -0.1,
                "social": 0.0,
                "federalism": 0.4,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "media",
            "bio": "Gobernador de Entre Rios (PJ), en funciones en 2003-05. Confianza media, sin "
            "fuente primaria verificada en este entorno.",
        },
        "tucuman": {
            "name": "Julio Cesar Miranda",
            "party": "fpv_pj",
            "ideology": {
                "economic": -0.15,
                "social": 0.1,
                "federalism": 0.4,
                "institutionalism": 0.4,
            },
            "interests": ["provincial_transfers", "employment"],
            "confidence": "baja",
            "bio": "Gobernador de Tucuman (PJ) tras la etapa de Bussi. Confianza baja sobre la "
            "fecha exacta de asuncion respecto de mayo de 2003, sin fuente primaria verificada.",
        },
        "misiones": {
            "name": "Carlos Rovira",
            "party": "fpv_pj",
            "ideology": {
                "economic": -0.1,
                "social": 0.0,
                "federalism": 0.4,
                "institutionalism": 0.4,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "media",
            "bio": "Gobernador de Misiones (PJ), primer mandato 1999-2003, en funciones en "
            "2003-05. Confianza media, sin fuente primaria verificada en este entorno.",
        },
        "mendoza": {
            "name": "Roberto Iglesias",
            "party": "ucr",
            "ideology": {
                "economic": 0.0,
                "social": -0.1,
                "federalism": 0.4,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "media",
            "bio": "Gobernador de Mendoza (UCR), 1999-2003, en funciones en 2003-05. Confianza "
            "media, sin fuente primaria verificada en este entorno.",
        },
        "rio_negro": {
            "name": "Pablo Verani",
            "party": "ucr",
            "ideology": {
                "economic": -0.05,
                "social": -0.1,
                "federalism": 0.4,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "reelection"],
            "confidence": "media",
            "bio": "Gobernador de Rio Negro (UCR/Alianza), 1999-2003, en funciones en 2003-05. "
            "Confianza media, sin fuente primaria verificada en este entorno.",
        },
        "caba": {
            "name": "Anibal Ibarra",
            "party": "ari_cc",
            "ideology": {
                "economic": -0.3,
                "social": -0.3,
                "federalism": -0.1,
                "institutionalism": 0.4,
            },
            "interests": ["provincial_transfers"],
            "confidence": "alta",
            "bio": "Jefe de Gobierno de la Ciudad de Buenos Aires, electo en 2000, en funciones "
            "en 2003-05.",
        },
    }
    return {
        "id": "2003-2015",
        "parties_extra": parties_extra,
        "targets": _targets(OPENING_2003),
        "opening": OPENING_2003,
        "president": {
            "name": "Nestor Kirchner",
            "party": "fpv_pj",
            "took_office": "2003-05-25",
            "ideology": {
                "economic": -0.5,
                "social": -0.3,
                "federalism": -0.1,
                "institutionalism": 0.4,
            },
            "interests": ["employment", "reelection"],
            "bio": "Presidente electo en 2003 (25% en primera vuelta, Menem se retira antes del "
            "balotaje). Asume el 25-may-2003.",
        },
        "minister": {
            "name": "Roberto Lavagna",
            "took_office": "2002-04-27",
            "left_office": "2005-11-28",
            "ideology": {
                "economic": -0.1,
                "social": -0.1,
                "federalism": 0.0,
                "institutionalism": 0.6,
            },
            "interests": ["price_stability", "fiscal_balance"],
            "bio": "Ministro de Economia desde abr-2002 (gobierno de Duhalde), continua con "
            "Kirchner hasta nov-2005. En funciones el 25-may-2003.",
        },
        "central_bank": {
            "name": "Alfonso Prat-Gay",
            "took_office": "2002-12-11",
            "left_office": "2004-09-23",
            "ideology": {
                "economic": 0.1,
                "social": 0.0,
                "federalism": 0.0,
                "institutionalism": 0.6,
            },
            "interests": ["price_stability", "financial_stability"],
            "bio": "Presidente del Banco Central desde dic-2002, continua con Kirchner. En "
            "funciones el 25-may-2003.",
        },
        "governors": governors,
    }


def era_2015_2023() -> dict:
    parties_extra = {
        "cambiemos_jxc": {
            "seats": 36,
            "founded": 2015,
            "personalism": 0.55,
            "discipline": 0.55,
            "seats_confidence": "low",
            "seats_note": "politics/parties/2015-2023.json (seats_share=0.36).",
        },
        "fpv_fdt_pj": {
            "seats": 35,
            "founded": 2003,
            "personalism": 0.6,
            "discipline": 0.75,
            "seats_confidence": "low",
            "seats_note": "politics/parties/2015-2023.json (seats_share=0.35); "
            "renombrado Frente de Todos en 2019, misma linea kirchnerista-PJ.",
        },
        "fit_u": {
            "seats": 3,
            "founded": 2015,
            "personalism": 0.25,
            "discipline": 0.85,
            "seats_confidence": "medium",
            "seats_note": "3.31% real de 2015 (ver OPENING_2015) coincide "
            "con seats_share=0.03 de politics/parties/2015-2023.json.",
        },
        "uca_otros_2015": {
            "seats": 20,
            "founded": None,
            "personalism": 0.45,
            "discipline": 0.35,
            "seats_confidence": "low",
            "seats_note": "politics/parties/2015-2023.json (seats_share=0.20).",
        },
        "lla": {
            "seats": 0,
            "founded": 2021,
            "personalism": 0.9,
            "discipline": 0.85,
            "loyalty_seed": -0.5,
            "outsider_bonus": 0.3,
            "seats_confidence": "n/a",
            "seats_note": "ADR 013 secc. 2, literal: founded 2021, seats 0 en 2019.",
        },
    }
    governors = {
        "buenos_aires": {
            "name": "Maria Eugenia Vidal",
            "party": "cambiemos_jxc",
            "ideology": {
                "economic": 0.4,
                "social": 0.1,
                "federalism": 0.2,
                "institutionalism": 0.6,
            },
            "interests": ["provincial_transfers", "reelection"],
            "confidence": "alta",
            "bio": "Gobernadora de Buenos Aires (PRO/Cambiemos), asume el 10-dic-2015 (primera "
            "gobernadora no peronista de la provincia en decadas).",
        },
        "cordoba": {
            "name": "Juan Schiaretti",
            "party": "fpv_fdt_pj",
            "ideology": {
                "economic": 0.1,
                "social": 0.0,
                "federalism": 0.5,
                "institutionalism": 0.55,
            },
            "interests": ["provincial_transfers", "industrial_protection"],
            "confidence": "alta",
            "bio": "Gobernador de Cordoba (PJ, linea cordobesista/no kirchnerista), asume el "
            "10-dic-2015.",
        },
        "entre_rios": {
            "name": "Gustavo Bordet",
            "party": "fpv_fdt_pj",
            "ideology": {
                "economic": -0.1,
                "social": 0.0,
                "federalism": 0.4,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "media",
            "bio": "Gobernador de Entre Rios (PJ/FPV), asume el 10-dic-2015.",
        },
        "tucuman": {
            "name": "Juan Manzur",
            "party": "fpv_fdt_pj",
            "ideology": {
                "economic": -0.15,
                "social": 0.0,
                "federalism": 0.4,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "employment"],
            "confidence": "alta",
            "bio": "Gobernador de Tucuman (PJ), asume el 10-dic-2015.",
        },
        "misiones": {
            "name": "Hugo Passalacqua",
            "party": "uca_otros_2015",
            "ideology": {
                "economic": 0.0,
                "social": 0.0,
                "federalism": 0.6,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "media",
            "bio": "Gobernador de Misiones (Frente Renovador de la Concordia, provincial), asume "
            "el 10-dic-2015. Confianza media, sin fuente primaria verificada en este entorno.",
        },
        "mendoza": {
            "name": "Alfredo Cornejo",
            "party": "cambiemos_jxc",
            "ideology": {
                "economic": 0.3,
                "social": -0.1,
                "federalism": 0.4,
                "institutionalism": 0.55,
            },
            "interests": ["provincial_transfers", "agricultural_exports"],
            "confidence": "alta",
            "bio": "Gobernador de Mendoza (UCR/Cambiemos), asume el 10-dic-2015.",
        },
        "rio_negro": {
            "name": "Alberto Weretilneck",
            "party": "uca_otros_2015",
            "ideology": {
                "economic": 0.0,
                "social": 0.0,
                "federalism": 0.6,
                "institutionalism": 0.5,
            },
            "interests": ["provincial_transfers", "reelection"],
            "confidence": "media",
            "bio": "Gobernador de Rio Negro (Juntos Somos Rio Negro, provincial), reelecto para "
            "el periodo que arranca el 10-dic-2015.",
        },
        "caba": {
            "name": "Horacio Rodriguez Larreta",
            "party": "cambiemos_jxc",
            "ideology": {
                "economic": 0.4,
                "social": 0.1,
                "federalism": -0.1,
                "institutionalism": 0.6,
            },
            "interests": ["provincial_transfers"],
            "confidence": "alta",
            "bio": "Jefe de Gobierno de la Ciudad de Buenos Aires (PRO/Cambiemos), asume el "
            "10-dic-2015.",
        },
    }
    return {
        "id": "2015-2023",
        "parties_extra": parties_extra,
        "targets": _targets(OPENING_2015),
        "opening": OPENING_2015,
        "president": {
            "name": "Mauricio Macri",
            "party": "cambiemos_jxc",
            "took_office": "2015-12-10",
            "ideology": {
                "economic": 0.6,
                "social": 0.1,
                "federalism": 0.1,
                "institutionalism": 0.6,
            },
            "interests": ["financial_stability", "reelection"],
            "bio": "Presidente electo en el balotaje de nov-2015. Asume el 10-dic-2015.",
        },
        "minister": {
            "name": "Alfonso Prat-Gay",
            "took_office": "2015-12-10",
            "left_office": "2017-01-02",
            "ideology": {
                "economic": 0.5,
                "social": 0.0,
                "federalism": 0.0,
                "institutionalism": 0.6,
            },
            "interests": ["financial_stability", "price_stability"],
            "bio": "Ministro de Hacienda y Finanzas Publicas (10-dic-2015 a 2-ene-2017).",
        },
        "central_bank": {
            "name": "Federico Sturzenegger",
            "took_office": "2015-12-10",
            "left_office": "2018-06-14",
            "ideology": {
                "economic": 0.6,
                "social": 0.0,
                "federalism": 0.0,
                "institutionalism": 0.6,
            },
            "interests": ["price_stability", "financial_stability"],
            "bio": "Presidente del Banco Central (10-dic-2015 a 14-jun-2018), adopta metas de "
            "inflacion.",
        },
        "governors": governors,
    }


ERA_BUILDERS = {"1983-2001": era_1983_2001, "2003-2015": era_2003_2015, "2015-2023": era_2015_2023}


def _governor_id(province_id: str) -> str:
    return f"gov_{province_id}"


def build_actors(era: dict) -> list[dict]:
    actors: list[dict] = []
    p = era["president"]
    actors.append(
        _actor_sheet(
            "president",
            p["name"],
            "president",
            p["ideology"],
            REAL_PERSON_PERSONALITY,
            p["interests"],
            PRESIDENT_INFLUENCE,
            f"Ideologia/intereses asignados por el analista para el momento de asuncion "
            f"({p['took_office']}); nombre y fecha son un hecho publico verificable.",
            p["bio"],
            party=p["party"],
        )
    )
    m = era["minister"]
    actors.append(
        _actor_sheet(
            "minister_economy",
            m["name"],
            "economy_minister",
            m["ideology"],
            REAL_PERSON_PERSONALITY,
            m["interests"],
            MINISTER_INFLUENCE,
            f"Ideologia/intereses asignados por el analista para el periodo "
            f"{m['took_office']}/{m['left_office']}; nombre y fechas son un hecho "
            "publico verificable.",
            m["bio"],
        )
    )
    cb = era["central_bank"]
    actors.append(
        _actor_sheet(
            "central_bank",
            cb["name"],
            "central_bank",
            cb["ideology"],
            REAL_PERSON_PERSONALITY,
            cb["interests"],
            CENTRAL_BANK_INFLUENCE,
            f"Ideologia/intereses asignados por el analista para el periodo "
            f"{cb['took_office']}/{cb['left_office']}; nombre y fechas son un hecho "
            "publico verificable.",
            cb["bio"],
        )
    )
    for province_id, g in era["governors"].items():
        actors.append(
            _actor_sheet(
                _governor_id(province_id),
                g["name"],
                "governor",
                g["ideology"],
                REAL_PERSON_PERSONALITY,
                g["interests"],
                GOVERNOR_INFLUENCE,
                f"Ideologia/intereses asignados por el analista (confianza {g['confidence']} sobre "
                "el nombre/fecha de asuncion, ver bio); provincia = la mas poblada de su region "
                "(politics/regions.csv, Censo 2022) segun ADR 013 secc. 3.",
                g["bio"],
                party=g["party"],
                province=province_id,
            )
        )
    raw_parties = json.loads(
        (POLITICS_PARTIES_DIR / f"{era['id']}.json").read_text(encoding="utf-8")
    )
    for rp in raw_parties:
        pid = rp["id"]
        actors.append(
            _actor_sheet(
                f"party_{pid}",
                rp["name"],
                "party",
                {
                    "economic": rp["economic"],
                    "social": rp["social"],
                    "federalism": rp["federalism"],
                    "institutionalism": 0.5,
                },
                {"ambition": 0.6, "risk_tolerance": 0.5, "loyalty": 0.55, "pragmatism": 0.55},
                ["reelection", "party_unity"],
                {"public": 0.5, "congress": 0.5, "streets": 0.25, "markets": 0.15},
                f"economic/social/federalism de politics/parties/{era['id']}.json (assessment: "
                "analyst en el origen); institutionalism/personality/interests/influence de este "
                "script, mismo criterio.",
                rp.get("notes") or rp["name"],
                party=pid,
            )
        )
    for b in BLOCS + UNIONS + BUSINESS + _media_actors(era["id"]):
        role = (
            "social_bloc"
            if b["id"].startswith("bloc_")
            else "union"
            if b["id"].startswith("union_")
            else "business"
            if b["id"].startswith("biz_")
            else "media"
        )
        actors.append(
            _actor_sheet(
                b["id"],
                b["name"],
                role,
                b["ideology"],
                b["personality"],
                b["interests"],
                b["influence"],
                b["assessment_note"],
                b["bio"],
            )
        )
    return actors


def build_parties_json(era: dict) -> list[dict]:
    raw_parties = json.loads(
        (POLITICS_PARTIES_DIR / f"{era['id']}.json").read_text(encoding="utf-8")
    )
    out = []
    for rp in raw_parties:
        pid = rp["id"]
        extra = era["parties_extra"][pid]
        entry = {
            "id": pid,
            "name": rp["name"],
            "seats": extra["seats"],
            "economic": rp["economic"],
            "social": rp["social"],
            "federalism": rp["federalism"],
            "discipline": extra["discipline"],
            "in_government": bool(rp.get("in_government", False)),
            "coalition_weight": 1.0,
            "founded": extra["founded"],
            "personalism": extra["personalism"],
            "loyalty_seed": extra.get("loyalty_seed", 0.0),
            "outsider_bonus": extra.get("outsider_bonus", 0.0),
            "assessment": "analyst",
            "seats_confidence": extra["seats_confidence"],
            "seats_source": extra["seats_note"],
            "notes": rp.get("notes", ""),
        }
        out.append(entry)
    return out


def build_loyalty_rows(era: dict) -> tuple[list[dict], dict[str, float]]:
    raw_parties = json.loads(
        (POLITICS_PARTIES_DIR / f"{era['id']}.json").read_text(encoding="utf-8")
    )
    all_ids = [rp["id"] for rp in raw_parties]
    active_ids = [pid for pid in all_ids if pid in era["targets"]]
    party_economic = {rp["id"]: rp["economic"] for rp in raw_parties}

    loyalty = estimate_loyalties(COHORTS, active_ids, party_economic, era["targets"], TURNOUT)
    errors = reproduction_errors(
        COHORTS, active_ids, party_economic, loyalty, era["targets"], TURNOUT
    )

    rows = []
    for pid in all_ids:
        seed = era["parties_extra"][pid].get("loyalty_seed")
        for c in COHORTS:
            value = loyalty[(c.id, pid)] if pid in active_ids else seed
            rows.append(
                {
                    "cohort_id": c.id,
                    "party_id": pid,
                    "loyalty": round(value, 4),
                    "turnout": TURNOUT[c.id],
                }
            )
    return rows, errors


def write_era(era: dict) -> dict:
    era_dir = ERAS_DIR / era["id"]
    (era_dir / "actors").mkdir(parents=True, exist_ok=True)

    parties = build_parties_json(era)
    (era_dir / "parties.json").write_text(
        json.dumps(parties, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    actors = build_actors(era)
    for a in actors:
        path = era_dir / "actors" / f"{a['id']}.yaml"
        path.write_text(
            yaml.safe_dump(a, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
        )

    governance = {}
    role_by_id = {a["id"]: a["role"] for a in actors}
    for aid, role in sorted(role_by_id.items()):
        governance[aid] = _governance_entry(role)
    (era_dir / "governance.yaml").write_text(
        "# Gobernanza por actor de la epoca "
        f"{era['id']} (ADR 013 secc. 1): copia de data/governance.yaml de Aurora con ids\n"
        "# remapeados a los actores de esta epoca (mismo template por ROL, ver\n"
        "# scripts/build_argentina_eras.py::GOVERNANCE_BY_ROLE). Ver data/governance.yaml para\n"
        "# el significado de cada campo (ADR 007 secc. 6).\n"
        + yaml.safe_dump(governance, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )

    rows, errors = build_loyalty_rows(era)
    with (era_dir / "cohorts_loyalty.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["cohort_id", "party_id", "loyalty", "turnout"])
        w.writeheader()
        w.writerows(rows)

    print(f"== {era['id']} == (ancla: eleccion de apertura, primera vuelta)")
    print(f"   parties.json: {len(parties)} partidos, actors/: {len(actors)} fichas")
    print(f"   {TURNOUT_NOTE}")
    print("   errores de reproduccion (utilidad neutra, pp):")
    for pid, err in errors.items():
        print(f"     {pid:20s} target={era['targets'][pid] * 100:6.2f}%  error={err:+.2f}pp")
    return {"parties": len(parties), "actors": len(actors), "errors": errors}


def main() -> None:
    ERAS_DIR.mkdir(parents=True, exist_ok=True)
    for builder in ERA_BUILDERS.values():
        write_era(builder())


if __name__ == "__main__":
    main()
