"""BackStudio CLI entry point."""

import subprocess
import webbrowser
from pathlib import Path

import typer

from backend.erd.loader import ERDValidationError, load_erd
from backend.erd.translate import translate
from backend.erd.visualize import render_html
from backend.services.code_generator import CodeGenerator

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


@app.command()
def visualize(
    erd_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to the ERD YAML file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output HTML path"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open the diagram in a browser"),
) -> None:
    """Render an HTML ER diagram for the given ERD file."""
    try:
        erd = load_erd(erd_file)
    except ERDValidationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    html = render_html(erd)
    out_path = output or erd_file.with_name(f"{erd_file.stem}-diagram.html")
    out_path.write_text(html, encoding="utf-8")
    typer.secho(f"Diagram written to: {out_path}", fg=typer.colors.GREEN)

    if open_browser:
        webbrowser.open(out_path.resolve().as_uri())


@app.command()
def generate(
    erd_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to the ERD YAML file"),
    output: Path = typer.Option(Path("workspace"), "--output", help="Workspace directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing generated code"),
) -> None:
    """Generate a FastAPI backend from an ERD file."""
    try:
        erd = load_erd(erd_file)
    except ERDValidationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    state = translate(erd)
    generator = CodeGenerator(output_dir=str(output))

    try:
        codebase_dir = generator.generate_project(state, force=force)
    except FileExistsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        typer.secho("Use --force to overwrite.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    if (codebase_dir / "alembic.ini").exists():
        try:
            subprocess.run(
                ["alembic", "revision", "--autogenerate", "-m", "initial"],
                cwd=codebase_dir,
                check=True,
                capture_output=True,
                timeout=30,
            )
        except Exception as exc:  # best-effort: never fails `generate`
            typer.secho(
                f"Warning: could not auto-generate the initial Alembic migration ({exc}). "
                "You can run it yourself once the database is reachable.",
                fg=typer.colors.YELLOW,
            )

    typer.secho(f"Generated at: {codebase_dir}", fg=typer.colors.GREEN, bold=True)
    typer.echo("Copy this directory into your project.")


if __name__ == "__main__":
    app()
