# Reporte hito 1 — ¿emerge un medio de intercambio? (ADR 010 secc. 7)

Corridas base analizadas: 100.

Una fila por corrida (base + barridos H3/H4) en `summary.csv`, junto a este reporte.

## Hipotesis

- **H1** (CUMPLIDA): 100/100 corridas (100.0%) con medio de intercambio emergido en < 300 turnos (umbral H1: > 60 %); 100/100 emergieron en algun momento de la corrida.
- **H2** (CUMPLIDA): distribucion del bien dominante: conchas: 100/100 (100.0%).
- **H3** (NO CUMPLIDA): abundancia=0.3: conchas gano en 30/30 (100.0%); abundancia=1.0: conchas gano en 30/30 (100.0%); abundancia=3.0: conchas gano en 30/30 (100.0%). Escasez (0.3) favorece a conchas mas que abundancia (3.0): no (H3 predice que si).
- **H4** (CUMPLIDA): transporte=0.0: mediana turno de emergencia=61.0 (30/30 emergieron); transporte=0.08: mediana turno de emergencia=65.0 (30/30 emergieron); transporte=0.18: mediana turno de emergencia=85.0 (30/30 emergieron). Mediana del turno de emergencia crece con el costo de transporte (H4 predice que si).

## Metricas de la corrida base (mediana e IC bootstrap 95 %)

| Metrica | Mediana | IC 95 % |
|---|---|---|
| Herfindahl de intermediarios | 0.2408 | [0.239, 0.242] |
| Fraccion de intercambios indirectos | 0.1089 | [0.107, 0.111] |
| Privacion media (estado estacionario) | 5.342 | [5.34, 5.35] |
| Gini de inventario (estado estacionario) | 0.2437 | [0.243, 0.244] |

## Distribucion del bien dominante (100 semillas)

| Bien | Corridas | % |
|---|---|---|
| conchas | 100 | 100.0% |

## Graficos

![medium_of_exchange_distribution](medium_of_exchange_distribution.png)
![h3_shell_abundance](h3_shell_abundance.png)
![h4_transport_cost](h4_transport_cost.png)

## Limitaciones

Estos resultados describen el comportamiento de República Artificial bajo sus reglas; no son evidencia sobre economías reales.
