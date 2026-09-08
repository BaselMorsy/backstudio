"""BackStudio CLI entry point."""

import typer

app = typer.Typer(name="backstudio", help="Generate FastAPI backends from a YAML ERD.")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """BackStudio CLI."""
    pass


if __name__ == "__main__":
    app()
