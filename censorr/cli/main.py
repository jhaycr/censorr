import typer

from censorr import __version__

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Censorr — censors profanity in media audio and subtitles."""


@app.command()
def version() -> None:
    """Print the installed censorr version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
