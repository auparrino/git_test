"""`republica.core` -- la "CPU social minima" de la Fase 10 (ADR 010).

Paquete **separado** de v1 (`republica.world`/`republica.engine`/
`republica.actors`/`republica.ai`): NO importa nada de esos paquetes ni es
importado por ellos, porque es una fisica distinta (agentes con inventario,
necesidades y primitivas de intercambio -- ADR 010 secc. 2 y 4), no una
extension del pais/gobierno de v1.

Hito 1 (unico implementado por ahora, ADR 010 secc. 7) activa solo las
primitivas `TRANSFER` y `OFFER` y pregunta si emerge un medio de intercambio
en un mundo de 10.000 agentes / 4 regiones / 6 bienes, sin nombrarlo: ver
`republica.core.classify` para donde (y solo donde) el vocabulario
institucional de la seccion 3 del ADR puede aparecer en el codigo.

`numpy` es la unica dependencia extra (`[core]`, ADR 010 secc. 7) y se
importa de forma perezosa dentro de cada funcion que lo necesita, para que
`republica.engine`/`republica.cli` sigan importando sin numpy instalado."""

from __future__ import annotations

__all__: list[str] = []
