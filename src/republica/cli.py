"""CLI de República Artificial.

Fase 0: solo scaffold. `republica run` se implementa en Fase 1.
"""

import typer
from rich.console import Console

from republica import __version__

app = typer.Typer(help="República Artificial — laboratorio político jugable.")
console = Console()


@app.command()
def version() -> None:
    """Muestra la versión instalada de República Artificial."""
    console.print(__version__)


@app.command()
def run() -> None:
    """Corre una simulación (placeholder, se implementa en Fase 1)."""
    console.print("not implemented yet")


if __name__ == "__main__":
    app()
