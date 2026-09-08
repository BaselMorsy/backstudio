"""BackStudio CLI entry point."""

from pathlib import Path

import typer

from backend.erd.loader import ERDValidationError, load_erd

app = typer.Typer(name="backstudio", help="Generate FastAPI backends from a YAML ERD.")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """BackStudio CLI."""
    pass


@app.command()
def validate(
    erd_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to the ERD YAML file")
) -> None:
    """Validate an ERD file without generating anything."""
    try:
        erd = load_erd(erd_file)
    except ERDValidationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    relationship_count = sum(len(e.relationships) for e in erd.entities)
    typer.secho(
        f"OK: {len(erd.entities)} entities, {relationship_count} relationships, "
        f"auth={'on' if erd.auth.enabled else 'off'}, rbac={'on' if erd.rbac.enabled else 'off'}",
        fg=typer.colors.GREEN,
    )


if __name__ == "__main__":
    app()
