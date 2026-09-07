import typer

from healthvideo import __version__

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Các lệnh healthvideo."""


@app.command()
def version() -> None:
    """In phiên bản healthvideo."""
    typer.echo(__version__)
