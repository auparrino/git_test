"""Test de humo: el paquete se importa y expone una versión."""

import republica


def test_version() -> None:
    assert republica.__version__ == "0.1.0"
