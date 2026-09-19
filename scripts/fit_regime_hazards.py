"""Estima las tasas base de salida de cada modo de régimen (ADR 015).

Ajusta, por máxima verosimilitud, un hazard mensual CONSTANTE (exponencial)
y uno WEIBULL a las duraciones reales de los regímenes argentinos
1916-2023, reconstruidas a mano de
`data/countries/argentina/politics/{regimes.csv,events.csv}` (las fechas
exactas de asunción salen de las filas `presidency_start` de `events.csv`;
las de golpe, de las filas `kind == "coup"` EXITOSAS).

Uso:

    uv run python scripts/fit_regime_hazards.py

No escribe nada: imprime los números que quedan citados en
`docs/ADR_015_endogenous_regime_transitions.md` §3 y hardcodeados como
defaults de `world/regime.py::RegimeTransitionCoefficients`. Se deja en el
repo para que esos defaults sean reproducibles (misma política que
`scripts/build_argentina_initial_states.py`).
"""

from __future__ import annotations

import math

#: Dictaduras: (etiqueta, meses entre el golpe y la asunción del primer
#: gobierno civil ELECTO que lo sucede). Ninguna está censurada: las seis
#: terminaron dentro de la ventana observada.
#:   1930-09-06 Uriburu    -> 1932-02-20 Justo      = 17.5 -> 17
#:   1943-06-04 GOU        -> 1946-06-04 Perón      = 36.0 -> 36
#:   1955-09-16 Lib.       -> 1958-05-01 Frondizi   = 31.5 -> 32
#:   1962-03-29 Guido      -> 1963-10-12 Illia      = 18.5 -> 19
#:   1966-06-28 Onganía    -> 1973-05-25 Cámpora    = 82.9 -> 83
#:   1976-03-24 Videla     -> 1983-12-10 Alfonsín   = 92.6 -> 93
DICTATORSHIP_SPELLS: list[tuple[str, int, bool]] = [
    ("1930 Uriburu", 17, False),
    ("1943 GOU", 36, False),
    ("1955 Libertadora", 32, False),
    ("1962 Guido", 19, False),
    ("1966 Revolución Argentina", 83, False),
    ("1976 Proceso", 93, False),
]

#: Traspaso final (el modo `transition` del motor, ADR 011 secc. 3): meses
#: entre la ELECCIÓN presidencial convocada por el régimen de facto y la
#: asunción del gobierno civil. Fechas de `politics/events.csv`
#: (`kind == "election_presidential"` y `presidency_start`):
#:   1931-11-08 -> 1932-02-20 = 3.4 -> 3
#:   1946-02-24 -> 1946-06-04 = 3.3 -> 3
#:   1958-02-23 -> 1958-05-01 = 2.2 -> 2
#:   1963-07-07 -> 1963-10-12 = 3.2 -> 3
#:   1973-03-11 -> 1973-05-25 = 2.5 -> 2
#:   1983-10-30 -> 1983-12-10 = 1.4 -> 1
HANDOVER_SPELLS: list[tuple[str, int, bool]] = [
    ("1931-11 -> 1932-02", 3, False),
    ("1946-02 -> 1946-06", 3, False),
    ("1958-02 -> 1958-05", 2, False),
    ("1963-07 -> 1963-10", 3, False),
    ("1973-03 -> 1973-05", 2, False),
    ("1983-10 -> 1983-12", 1, False),
]

#: Dictadura NETA del traspaso (para no contar dos veces los mismos meses:
#: en el motor la duración de un régimen de facto es
#: `dictatorship` + `transition`, así que el hazard de `dictatorship` se
#: ajusta sobre la duración total MENOS el traspaso observado).
DICTATORSHIP_NET_SPELLS: list[tuple[str, int, bool]] = [
    (label, d - h, False)
    for (label, d, _c), (_hl, h, _hc) in zip(DICTATORSHIP_SPELLS, HANDOVER_SPELLS, strict=True)
]

#: Períodos civiles: (etiqueta, meses hasta el golpe que los termina,
#: censurado). El período abierto 1983-12 -> 2023-12 es el único censurado
#: (no terminó en golpe: sigue abierto al final de la serie).
CIVILIAN_SPELLS: list[tuple[str, int, bool]] = [
    ("1916-10 Yrigoyen (democracy)", 167, False),
    ("1932-02 Justo (restricted)", 136, False),
    ("1946-06 Perón (democracy)", 111, False),
    ("1958-05 Frondizi (restricted)", 47, False),
    ("1963-10 Illia (restricted)", 33, False),
    ("1973-05 Cámpora/Perón (democracy)", 34, False),
    ("1983-12 Alfonsín-> (democracy)", 480, True),
]

RESTRICTED_LABELS = frozenset(
    {
        "1932-02 Justo (restricted)",
        "1958-05 Frondizi (restricted)",
        "1963-10 Illia (restricted)",
    }
)


def _weibull_nll(lam: float, k: float, spells: list[tuple[str, int, bool]]) -> float:
    """Menos log-verosimilitud de un Weibull con censura por derecha."""
    nll = 0.0
    for _label, t, censored in spells:
        nll += (t / lam) ** k
        if not censored:
            nll -= math.log(k / lam) + (k - 1.0) * math.log(t / lam)
    return nll


def _lambda_hat(k: float, spells: list[tuple[str, int, bool]]) -> float:
    """MLE de la escala DADO `k`, en forma cerrada:
    `lambda = (sum(t_i**k) / d)**(1/k)` con `d` = cantidad de eventos
    (vale igual con observaciones censuradas, que entran en la suma pero no
    en `d`). Asi el ajuste se reduce a una busqueda en UNA dimension y el
    script no necesita ningun optimizador externo."""
    events = sum(1 for _l, _t, c in spells if not c)
    total = sum(t**k for _l, t, _c in spells)
    return (total / events) ** (1.0 / k)


def _fit_weibull(spells: list[tuple[str, int, bool]]) -> tuple[float, float, float]:
    """`(lambda, k, nll)` por maxima verosimilitud: seccion aurea sobre `k`
    en la verosimilitud PERFILADA (`lambda` resuelto en forma cerrada para
    cada `k`)."""
    lo, hi = 0.05, 20.0
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)

    def profile(k: float) -> float:
        return _weibull_nll(_lambda_hat(k, spells), k, spells)

    fc, fd = profile(c), profile(d)
    for _ in range(200):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = profile(c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = profile(d)
    k = (a + b) / 2.0
    return _lambda_hat(k, spells), k, profile(k)


def fit(spells: list[tuple[str, int, bool]], name: str) -> None:
    events = sum(1 for _l, _t, c in spells if not c)
    exposure = sum(t for _l, t, _c in spells)
    const = events / exposure
    lam, k, nll = _fit_weibull(spells)
    nll_const = -(events * math.log(const) - const * exposure)
    print(f"== {name}")
    print(f"   n={len(spells)} spells, eventos={events}, exposición={exposure} meses")
    print(f"   hazard constante (MLE) = {const:.6f} /mes  (vida media {1 / const:.1f} meses)")
    print(f"   Weibull (MLE): lambda={lam:.2f} meses, k={k:.3f}")
    print(
        f"   nll exponencial={nll_const:.4f}  nll Weibull={nll:.4f}  "
        f"LR={2 * (nll_const - nll):.3f} (chi2_1, 5 % = 3.84)"
    )
    for years in (2, 4, 6, 8, 10):
        m = years * 12
        print(
            f"   P(salida <= {years:>2} años): exponencial={1 - math.exp(-const * m):.3f}  "
            f"Weibull={1 - math.exp(-((m / lam) ** k)):.3f}"
        )
    print()


def main() -> None:
    fit(DICTATORSHIP_SPELLS, "DICTADURAS, duración TOTAL (golpe -> gobierno civil electo)")
    fit(DICTATORSHIP_NET_SPELLS, "DICTADURAS, NETO del traspaso (`dictatorship` del motor)")
    fit(HANDOVER_SPELLS, "TRASPASO final (`transition` del motor: elección -> asunción)")
    fit(CIVILIAN_SPELLS, "CIVILES, todas (salida por golpe)")
    fit(
        [s for s in CIVILIAN_SPELLS if s[0] not in RESTRICTED_LABELS],
        "CIVILES, solo `democracy` plena",
    )
    fit(
        [s for s in CIVILIAN_SPELLS if s[0] in RESTRICTED_LABELS],
        "CIVILES, solo `restricted_democracy`",
    )


if __name__ == "__main__":
    main()
