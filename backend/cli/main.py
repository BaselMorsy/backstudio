"""BackStudio CLI entry point."""

import webbrowser
from pathlib import Path
import functools

import click
import typer
from typer.core import TyperArgument, TyperOption

# Monkey patch to fix Click 8.x/Typer compatibility with make_metavar
# The issue: Click 8.x expects make_metavar(ctx) but Typer's make_metavar() doesn't accept ctx
import inspect
from click.core import Option as ClickOption

if hasattr(TyperOption, 'make_metavar'):
    _orig_make_metavar = TyperOption.make_metavar.__func__ if isinstance(TyperOption.make_metavar, classmethod) else TyperArgument.make_metavar

    # Check how many arguments the original method expects
    sig = inspect.signature(_orig_make_metavar)
    accepts_ctx = len(sig.parameters) > 1  # More than just 'self'

    # Create a wrapper that handles both signatures
    def _make_metavar_wrapper(self, ctx=None):
        try:
            if accepts_ctx:
                return _orig_make_metavar(self, ctx)
            else:
                return _orig_make_metavar(self)
        except TypeError:
            # Fallback
            if hasattr(self, 'name'):
                return f"<{self.name}>"
            elif hasattr(self, 'type'):
                return getattr(self.type, 'name', 'TEXT')
            return 'TEXT'

    TyperOption.make_metavar = _make_metavar_wrapper
    if hasattr(TyperArgument, 'make_metavar'):
        TyperArgument.make_metavar = _make_metavar_wrapper

from backend.erd.loader import ERDValidationError, load_erd
from backend.erd.visualize import render_html

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
    erd_file: str = typer.Argument(..., help="Path to the ERD YAML file"),
    output: Path = typer.Option(None, "--output", help="Output HTML path"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open the diagram in a browser"),
) -> None:
    """Render an HTML ER diagram for the given ERD file."""
    erd_path = Path(erd_file)
    try:
        erd = load_erd(erd_path)
    except ERDValidationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    html = render_html(erd)
    out_path = Path(output) if output else erd_path.with_name(f"{erd_path.stem}-diagram.html")
    out_path.write_text(html, encoding="utf-8")
    typer.secho(f"Diagram written to: {out_path}", fg=typer.colors.GREEN)

    if not no_open:
        webbrowser.open(out_path.resolve().as_uri())


if __name__ == "__main__":
    app()
