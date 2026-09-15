"""Fase 9 (ADR 009): modelo sustituto, active learning, early-warning y
clustering de regimenes. Todo lo que vive aca importa `numpy`/`sklearn` de
forma perezosa (dentro de cada funcion que los usa), nunca a nivel de
modulo: el motor (`engine/`, `actors/`, `ai/`) y la CLI base siguen
funcionando sin el extra `[ml]` instalado. Un `import republica.ml.*` sin
sklearn instalado no falla; recien falla, con un mensaje en castellano, la
funcion puntual que lo necesita (ver cada modulo)."""

from __future__ import annotations
