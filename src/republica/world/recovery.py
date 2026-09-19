"""ADR 018: recuperacion del bloque politico (`features.political_recovery`).

Cuatro terminos con la forma literal de ADR 012 secc. 5
(`x' += rec * pos(objetivo - x)`, condicionado al estado), uno por cada una
de las variables que la sonda de `docs/EMERGENCE_LOG.md` encontro clavadas
contra su cota: `government_approval` y `institutional_confidence` contra el
piso 0, `social_tension` y `protest_level` contra el techo 100.

La diferencia con ADR 012 secc. 5 no esta en la forma sino en la
**compuerta**: alla los disparadores son umbrales ABSOLUTOS sobre la
inflacion y el desempleo (`recovery_inflation_max`, `recovery_unemployment_
max`), y el diagnostico de ADR 018 secc. 1.5 muestra que la calibracion los
puede dejar en valores que la Argentina simulada no cruza nunca (1,44 %/mes
en el grupo `peg`, 5,37 % de desempleo en el grupo `control`). Aca la
compuerta es RELATIVA -- la inflacion de este mes contra la media de los
ultimos meses, el PBI creciendo con el desempleo no subiendo -- porque las
dos recuperaciones argentinas documentadas arrancaron con inflacion ALTA
pero cayendo (abril de 1990: 11,4 %/mes contra 95,5 % en marzo) y con
desempleo ALTO pero bajando (2003: 15,7 %).

Ademas, la compuerta se cierra con los MISMOS cuatro marcadores de ruptura
aguda de ADR 016 secc. 3 (hiperinflacion sostenida, crisis bancaria, default
soberano, salida forzada del regimen cambiario). Eso es deliberado y es el
candado contra la amnistia general: el mecanismo esta apagado exactamente en
las dos situaciones en que la Argentina real si tuvo una salida anticipada
(1989 y 2001).

Nada de este modulo corre con `features.political_recovery` apagado: el
motor no arma el `RecoveryContext` y las dos etapas reciben `None`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from republica.world.state import pos

#: Meses de inflacion que `RecoveryTracker` guarda como maximo. Es el mayor
#: `relief_window` razonable; mas que eso no lo usa nadie.
MAX_INFLATION_WINDOW = 24


@dataclass(frozen=True)
class PoliticalRecoveryCoefficients:
    """Coeficientes de ADR 018, con su ancla documentada campo por campo.

    Deliberadamente SEPARADO de `world/economy.py::MacroCoefficients`: ese
    dataclass es el vector de CMA-ES (`calibration/parameters.py::
    MACRO_TUNABLE` se arma con todos sus campos `float`), y agregar campos
    ahi hubiera ampliado el espacio de parametros de otro modulo sin avisar.
    `from_dict` deja el grupo listo para que la calibracion lo tome cuando
    quiera, sin que hoy entre en ningun vector.
    """

    #: Valor de referencia al que `government_approval` puede volver, y que
    #: NO puede cruzar (`pos(...)` apaga el termino ahi). ANCLA: el proxy
    #: electoral del propio paquete (`50 + 20*(voto_oficialismo - 0.45)/
    #: 0.15`, ADR 011 secc. 2) aplicado al PEOR resultado de un oficialismo
    #: post-1983 -- Kirchner, 21,64 % en la primera vuelta de 2003, de
    #: `politics/sources/electorAr_presi/arg_presi_gral2003.csv`. Es el
    #: valor que `country.json -> initial_states["2003-06"].
    #: government_approval` ya trae (18.850931...). La aprobacion
    #: presidencial argentina post-1983 nunca se quedo en cero; su piso
    #: medible con la regla del propio proyecto es 18,85.
    aprobacion_objetivo: float = 18.85
    #: Velocidad con la que `government_approval` vuelve hacia
    #: `aprobacion_objetivo`. ANCLA: `politics/events.csv`, tiempo de la
    #: ruptura aguda a la normalidad politica -- 1989-05 (`hyperinflation`)
    #: a 1991-04 (`currency_regime_change`, convertibilidad) = 23 meses;
    #: 2001-12 (`crisis_banking`, corralito) a 2003-05 (`presidency_start`
    #: de Kirchner) = 17 meses; mediana 20. Cerrar el 90 % de la brecha en
    #: 20 meses da `1 - 0.1**(1/20) = 0.109`, redondeado a 0.10.
    aprobacion_rec: float = 0.10
    #: Valor de referencia de `institutional_confidence`. ANCLA:
    #: `history/vdem_argentina.csv`, `v2x_libdem` MINIMO de la era
    #: democratica (2011 = 0.573) por 100 -- exactamente la transformacion
    #: que `scripts/build_argentina_initial_states.py` ya usa para el
    #: `institutional_confidence` inicial de las ocho fechas reales.
    confianza_objetivo: float = 57.3
    #: Velocidad de vuelta de `institutional_confidence`. ANCLA: mismo
    #: archivo, `v2x_rule` (Estado de derecho): minimo 1990 = 0.455,
    #: recuperacion a 0.698 en 2000, referencia 1984 = 0.831. Cierra el
    #: 65 % de la brecha en 120 meses: `1 - 0.35**(1/120) = 0.0087`. Es un
    #: orden de magnitud mas lento que la aprobacion, y eso ES el dato: la
    #: confianza institucional argentina tardo una decada en volver de su
    #: piso. Coincide con el `ic_rec = 0.01` que ADR 012 secc. 5 habia
    #: elegido sin ancla: el problema de aquel canal no era la velocidad.
    confianza_rec: float = 0.009
    #: Valor de referencia de `social_tension`. ANCLA DEBIL: es el valor que
    #: el paquete asume para las OCHO fechas reales (`initial_states[*].
    #: social_tension`, con `assumed: true` y la nota "no hay serie de
    #: conflictividad social continua descargada"), y coincide con el
    #: `tension_base` de Aurora. NO hay serie real detras: es una convencion
    #: del repo, declarada como tal (PLAN_ARGENTINA.md secc. 0).
    tension_objetivo: float = 35.0
    #: VALOR DE DISENO. Acotado por el proxy de `politics/events.csv`: entre
    #: 1983-12 y 2023-12 (481 meses) hay 6 episodios de conflicto social
    #: agudo -- cuatro `coup` (carapintadas 1987-04, 1988-01, 1988-12,
    #: 1990-12) y dos `crisis_banking` (saqueos de 1989-05, corralito de
    #: 2001-12) -- y los shocks de conflicto del propio catalogo
    #: (`general_strike`, `protest_wave`) duran 1 mes. El techo deberia
    #: ocuparse del orden del 1 % de los meses, no del 38-77 % medido en
    #: ADR 018 secc. 1.2. Una excursion al techo que decae a la mitad entre
    #: 6 y 12 meses implica `rec` entre 0.056 y 0.109; 0.06 es el extremo
    #: conservador. Seis eventos no identifican un coeficiente: el valor
    #: exacto es de diseno.
    tension_rec: float = 0.06
    #: Valor de referencia de `protest_level`. ANCLA DEBIL, igual que
    #: `tension_objetivo`: `initial_states[*].protest_level` con
    #: `assumed: true`, y `protest_ref` de Aurora. NO hay serie real detras.
    protesta_objetivo: float = 15.0
    #: VALOR DE DISENO. Mismo proxy de `events.csv` que `tension_rec`,
    #: escalado por la relacion de velocidades que el propio spec le da a
    #: las dos variables en Aurora (`pr_adj / t_adj = 0.3 / 0.2 = 1.5`):
    #: `0.06 * 1.5 = 0.09`.
    protesta_rec: float = 0.09
    #: Meses de inflacion que entran en la media movil contra la que se
    #: compara la inflacion del mes. VALOR DE DISENO: media semestral,
    #: suficiente para que el ratio no lo decida un mes suelto.
    relief_window: int = 6
    #: Un mes cuenta como desinflacion si `inflation <= relief_pi_ratio *
    #: media(inflacion de los `relief_window` meses previos)`. ANCLA: los
    #: dos episodios reales de `history/inflation_cpi_monthly_linked.csv` --
    #: 1990-04, 11,4 %/mes contra una media de 78,8 en 1990-01..03 (ratio
    #: 0.14); 2002-09, 1,4 %/mes contra 3,0 en 2002-06..08 (ratio 0.47).
    #: 0.70 es deliberadamente MAS LAXO que los dos, para que la compuerta
    #: no dependa de reproducir la violencia exacta de esas caidas.
    relief_pi_ratio: float = 0.70
    #: Un mes cuenta como reactivacion si `gdp_growth >= relief_growth_min`
    #: Y el desempleo no sube respecto del mes anterior. ANCLA: 2009-2011,
    #: PBI -5,9 % (2009) a +10,1 % (2010) y +6,0 % (2011) con desempleo
    #: bajando. La condicion es "crece y el desempleo no sube", no "crece
    #: mucho".
    relief_growth_min: float = 0.0
    #: QUINTA variable, APAGADA por default (`crime_rec = 0.0`). No entra en
    #: el alcance de ADR 018 -- las cuatro asignadas son las que empujan el
    #: colapso -- pero el mecanismo es parametrizable por variable y cubrirla
    #: sale gratis, asi que el termino existe y se puede prender con un
    #: coeficiente. El pendiente esta medido en ADR 018 "Lo que este ADR NO
    #: arregla": `crime_perception` es la variable MAS saturada del modelo
    #: (98 % de la corrida en el techo 100 desde 2003-06) y entra
    #: directamente en la aprobacion publicada por
    #: `world/cohorts.py::step_cohorts` (`crime_term = crime_perception -
    #: 50`), o sea que clavada en 100 es un -50 constante disfrazado de
    #: variable. Valor de referencia: 50, el punto neutro de ese mismo
    #: `crime_term` (no hay serie de percepcion de inseguridad, ver
    #: `calibration/initial_states.py`: `assumed`).
    crime_objetivo: float = 50.0
    #: Velocidad de vuelta de `crime_perception`. 0.0 = termino APAGADO, que
    #: es el default de ADR 018: no hay ancla para esta variable y esta
    #: fuera del alcance asignado. Ver `crime_objetivo`.
    crime_rec: float = 0.0
    #: Meses CONSECUTIVOS de alivio antes de que el mecanismo se enganche.
    #: VALOR DE DISENO, con su sesgo declarado: los dos episodios reales
    #: sugieren mas (del inicio del alivio al punto de giro politico,
    #: 1990-04 a 1991-04 = 12 meses; 2002-09 a 2003-05 = 8 meses), pero con
    #: 8-12 el mecanismo no llegaria a engancharse nunca en una ventana de
    #: 48 meses. Se elige 3 y se declara que eso lo hace MAS permisivo de lo
    #: que los dos episodios reales justifican (ADR 018 secc. 2.3).
    relief_months: int = 3

    @classmethod
    def from_dict(cls, raw: dict | None) -> PoliticalRecoveryCoefficients:
        """Construye desde `{"coefficients": {...}}` o desde un dict plano,
        ignorando claves desconocidas. Hoy nadie lo llama desde el paquete
        de pais (`country.json` solo trae el flag booleano): existe para que
        la calibracion pueda tomar el grupo sin tocar este modulo."""
        if not raw:
            return cls()
        coeffs = dict(raw.get("coefficients", raw))
        return cls(**{k: v for k, v in coeffs.items() if k in cls.__dataclass_fields__})


@dataclass
class RecoveryTracker:
    """Estado persistente entre meses de ADR 018, fuera de las 20 variables
    de `WorldState` (mismo patron que `economy.MacroState`). Lo crea
    `engine/simulation.py::run` cuando el flag esta prendido."""

    #: Inflacion mensual de los meses YA cerrados, del mas viejo al mas
    #: nuevo, acotada a `MAX_INFLATION_WINDOW`.
    inflation_window: list[float] = field(default_factory=list)
    #: Meses consecutivos de alivio acumulados hasta el mes anterior
    #: inclusive. Un mes sin alivio la reinicia a 0.
    relief_streak: int = 0
    #: Meses consecutivos con inflacion por encima del umbral de ruptura
    #: hiperinflacionaria. Contador propio de ADR 018: el de ADR 016
    #: (`Simulation.rupture_high_pi_months`) solo se actualiza con
    #: `features.legitimacy_floor` prendido, y los dos flags son
    #: independientes.
    high_pi_months: int = 0


@dataclass(frozen=True)
class RecoveryContext:
    """Lo que `step_society`/`step_politics` leen del mes en curso. Con
    `features.political_recovery` apagado las dos etapas reciben `None` y
    nada de esto se calcula."""

    #: Coeficientes vigentes para esta corrida.
    coeff: PoliticalRecoveryCoefficients
    #: `True` si este mes cuenta como alivio macro (sin ruptura aguda, y con
    #: desinflacion o reactivacion).
    relief: bool
    #: Meses consecutivos de alivio incluyendo este.
    streak: int
    #: `True` si la racha llego a `relief_months`: el mecanismo aplica sus
    #: cuatro terminos este mes.
    engaged: bool


def track_rupture(
    tracker: RecoveryTracker,
    inflation: float,
    rupture_inflation: float,
    rupture_months: int,
    banking_crisis: bool,
    sovereign_default: bool,
    fx_exit_in_term: bool,
) -> bool:
    """`True` si hay una ruptura monetaria o financiera aguda este mes.

    Son los MISMOS cuatro marcadores de ADR 016 secc. 3 -- hiperinflacion
    sostenida, crisis bancaria, default soberano, salida forzada del regimen
    cambiario dentro del mandato --, deliberadamente: con una ruptura activa
    el mecanismo de ADR 018 NO corre, que es lo que impide que sea una
    amnistia general. Las dos salidas anticipadas reales de la Argentina
    post-1983 (1989 y 2001) tuvieron ruptura; las otras ocho presidencias no.

    No se reusa `world/events.py::legitimacy_rupture_active` porque aquella
    necesita un `LegitimacyContext` que el motor arma DESPUES de la politica
    del mes (sobre el estado ya clampeado) y ADR 018 necesita el marcador
    ANTES de la sociedad. El contador de inflacion alta es propio (ver
    `RecoveryTracker.high_pi_months`), por la misma razon.

    MUTA `tracker.high_pi_months`: se llama una vez por mes."""
    tracker.high_pi_months = tracker.high_pi_months + 1 if inflation > rupture_inflation else 0
    if tracker.high_pi_months >= rupture_months:
        return True
    return bool(banking_crisis or sovereign_default or fx_exit_in_term)


def relief_this_month(
    tracker: RecoveryTracker,
    coeff: PoliticalRecoveryCoefficients,
    inflation: float,
    gdp_growth: float,
    unemployment: float,
    unemployment_prev: float,
    rupture: bool,
) -> bool:
    """Compuerta de ADR 018 secc. 2.2. `True` si el mes cuenta como alivio
    macro: NO hay ruptura aguda, y hay desinflacion (la inflacion cae por
    debajo de `relief_pi_ratio` veces la media de la ventana) O reactivacion
    (el PBI crece y el desempleo no sube).

    Sin historia suficiente (`inflation_window` vacia) el canal de
    desinflacion no se evalua: solo puede abrir el de reactivacion. Es a
    proposito -- el primer mes de una corrida no puede ser "desinflacion"
    respecto de nada."""
    if rupture:
        return False
    window = tracker.inflation_window[-coeff.relief_window :]
    if window:
        media = sum(window) / len(window)
        if inflation <= coeff.relief_pi_ratio * media:
            return True
    reactivacion = gdp_growth >= coeff.relief_growth_min and unemployment <= unemployment_prev
    return bool(reactivacion)


def advance_recovery(
    tracker: RecoveryTracker,
    coeff: PoliticalRecoveryCoefficients,
    inflation: float,
    gdp_growth: float,
    unemployment: float,
    unemployment_prev: float,
    rupture: bool,
) -> RecoveryContext:
    """Avanza el `tracker` un mes y devuelve el `RecoveryContext` del mes.

    MUTA el tracker (agrega la inflacion del mes a la ventana y actualiza la
    racha), asi que se llama UNA sola vez por mes, antes de `step_society`.
    `step_politics` reusa el mismo contexto."""
    relief = relief_this_month(
        tracker,
        coeff,
        inflation=inflation,
        gdp_growth=gdp_growth,
        unemployment=unemployment,
        unemployment_prev=unemployment_prev,
        rupture=rupture,
    )
    tracker.relief_streak = tracker.relief_streak + 1 if relief else 0
    tracker.inflation_window.append(inflation)
    if len(tracker.inflation_window) > MAX_INFLATION_WINDOW:
        del tracker.inflation_window[:-MAX_INFLATION_WINDOW]
    return RecoveryContext(
        coeff=coeff,
        relief=relief,
        streak=tracker.relief_streak,
        engaged=tracker.relief_streak >= coeff.relief_months,
    )


def recover_tension(social_tension: float, ctx: RecoveryContext | None) -> float:
    """`social_tension' -= ts_rec * pos(social_tension - ts_obj)` (ADR 018
    secc. 2.1, seccion 5.3). Con `pos(...)` el termino se apaga EXACTAMENTE
    en el objetivo: el mecanismo no puede bajar la tension por debajo de 35.

    Se aplica ANTES de la seccion 5.4 en `world/society.py` a proposito: la
    protesta del mismo mes ve la tension ya aliviada por el termino
    `pr_t * (social_tension - tension_base)`, que es el lazo que ADR 016
    secc. 2.4 identifico como absorbente."""
    if ctx is None or not ctx.engaged:
        return social_tension
    c = ctx.coeff
    return social_tension - c.tension_rec * pos(social_tension - c.tension_objetivo)


def recover_protest(protest_level: float, ctx: RecoveryContext | None) -> float:
    """`protest_level' -= pr_rec * pos(protest_level - pr_obj)` (ADR 018
    secc. 2.1, seccion 5.4). Se apaga exactamente en 15."""
    if ctx is None or not ctx.engaged:
        return protest_level
    c = ctx.coeff
    return protest_level - c.protesta_rec * pos(protest_level - c.protesta_objetivo)


def recover_crime(crime_perception: float, ctx: RecoveryContext | None) -> float:
    """`crime_perception' -= crime_rec * pos(crime_perception -
    crime_objetivo)` (seccion 5.5). APAGADO por default (`crime_rec = 0.0`):
    es un pendiente medido, no una decision de este ADR. Ver
    `PoliticalRecoveryCoefficients.crime_objetivo`."""
    if ctx is None or not ctx.engaged or ctx.coeff.crime_rec == 0.0:
        return crime_perception
    c = ctx.coeff
    return crime_perception - c.crime_rec * pos(crime_perception - c.crime_objetivo)


def recover_social(
    social_tension: float, protest_level: float, ctx: RecoveryContext | None
) -> tuple[float, float]:
    """Los dos terminos sociales juntos (`recover_tension` +
    `recover_protest`). El motor los aplica por separado, cada uno en su
    seccion; esta funcion existe para poder testear la forma de los dos de
    una sola vez."""
    return recover_tension(social_tension, ctx), recover_protest(protest_level, ctx)


def recover_approval(government_approval: float, ctx: RecoveryContext | None) -> float:
    """`government_approval' += ap_rec * pos(ap_obj - government_approval)`
    (ADR 018 secc. 2.1, seccion 5.6). Con `pos(...)` el termino se apaga
    EXACTAMENTE en el objetivo: el mecanismo no puede subir la aprobacion
    por encima de 18,85. No es un empujon: es un piso blando.

    Se aplica DOS veces por mes en `engine/simulation.py`, y no es un bug:
    la aprobacion que publica el motor con `features.cohorts` prendido NO es
    la de la seccion 5.6 sino la agregada por cohorte (`world/cohorts.py`),
    que pisa el campo despues de `step_politics`. La primera aplicacion es
    la que ven `congress_support` y `political_stability` de la seccion 5.9;
    la segunda es la que ve el estado publicado. Con `features.cohorts`
    apagado se aplica una sola vez."""
    if ctx is None or not ctx.engaged:
        return government_approval
    c = ctx.coeff
    return government_approval + c.aprobacion_rec * pos(c.aprobacion_objetivo - government_approval)


def recover_confidence(institutional_confidence: float, ctx: RecoveryContext | None) -> float:
    """`institutional_confidence' += ic_rec * pos(ic_obj -
    institutional_confidence)` (ADR 018 secc. 2.1, seccion 5.8). Se apaga
    exactamente en 57,3."""
    if ctx is None or not ctx.engaged:
        return institutional_confidence
    c = ctx.coeff
    return institutional_confidence + c.confianza_rec * pos(
        c.confianza_objetivo - institutional_confidence
    )


def recover_political(
    government_approval: float, institutional_confidence: float, ctx: RecoveryContext | None
) -> tuple[float, float]:
    """Los dos terminos politicos juntos (`recover_approval` +
    `recover_confidence`), como los aplica `world/politics.py`."""
    return recover_approval(government_approval, ctx), recover_confidence(
        institutional_confidence, ctx
    )


def with_coefficients(
    ctx: RecoveryContext, coeff: PoliticalRecoveryCoefficients
) -> RecoveryContext:
    """Helper para tests: el mismo contexto con otros coeficientes."""
    return replace(ctx, coeff=coeff)
