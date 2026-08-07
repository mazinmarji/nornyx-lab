"""Local server entry point for the browser academy."""

from __future__ import annotations

import typer
import uvicorn

cli = typer.Typer(add_completion=False, no_args_is_help=False)


@cli.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Interface to bind."),
    port: int = typer.Option(8000, min=1, max=65535, help="HTTP port."),
    reload: bool = typer.Option(False, help="Reload Python files during local development."),
) -> None:
    """Serve the academy API and built browser client."""

    uvicorn.run(
        "nornyx_lab.academy.app:app",
        host=host,
        port=port,
        reload=reload,
        access_log=True,
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
