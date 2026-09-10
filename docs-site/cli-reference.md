# CLI Reference

The `backstudio` CLI is a [Typer](https://typer.tiangolo.com/) application defined in
`app/cli/main.py`. It exposes three commands: `validate`, `visualize`, and `generate`. Run any
command with `uv run backstudio ...`, or activate `.venv` first and drop the `uv run` prefix
(see [Installation](getting-started/installation.md)).

## Global options

```
Usage: backstudio [OPTIONS] COMMAND [ARGS]...

  Generate FastAPI backends from a YAML ERD.

Options:
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell, to
                                  copy it or customize the installation.
  --help                          Show this message and exit.
```

`--install-completion` and `--show-completion` are provided by Typer/Click automatically and
apply to the `backstudio` command as a whole, not to any individual subcommand.

---

## `backstudio validate`

Validate an ERD file without generating anything.

```
Usage: backstudio validate [OPTIONS] ERD_FILE

  Validate an ERD file without generating anything.

Arguments:
  ERD_FILE  Path to the ERD YAML file  [required]

Options:
  --help  Show this message and exit.
```

### Arguments

| Name | Type | Required | Help text |
|---|---|---|---|
| `ERD_FILE` | `Path` (positional argument) | yes | "Path to the ERD YAML file" — must exist and be readable (Typer's `exists=True, readable=True` are set on the argument; a missing or unreadable file fails before the ERD is even parsed) |

### Behavior

Loads and semantically validates the ERD via `app.erd.loader.load_erd`. On success, prints a
one-line summary (entity count, relationship count, whether `auth` and `rbac` are enabled) in
green and exits `0`. On an `ERDValidationError`, prints the error in red and exits with code `1`.

### Example

```bash
$ uv run backstudio validate blog.yml
OK: 1 entities, 0 relationships, auth=off, rbac=off
```

---

## `backstudio visualize`

Render an HTML ER diagram for the given ERD file.

```
Usage: backstudio visualize [OPTIONS] ERD_FILE

  Render an HTML ER diagram for the given ERD file.

Arguments:
  ERD_FILE  Path to the ERD YAML file  [required]

Options:
  -o, --output PATH   Output HTML path
  --open / --no-open  Open the diagram in a browser  [default: open]
  --help               Show this message and exit.
```

### Arguments and options

| Name | Flag forms | Type | Default | Help text |
|---|---|---|---|---|
| `ERD_FILE` | positional | `Path` | — (required) | "Path to the ERD YAML file"; must exist and be readable |
| `output` | `-o`, `--output` | `Path` (optional) | `None` — falls back to `<erd_file stem>-diagram.html` next to the ERD file | "Output HTML path" |
| `open_browser` | `--open` / `--no-open` | `bool` | `True` (i.e. `--open`) | "Open the diagram in a browser" |

### Behavior

Loads the ERD the same way `validate` does (failing the same way on an invalid file), renders
it to a self-contained HTML page via `app.erd.visualize.render_html`, writes it to `--output` (or
the default `<stem>-diagram.html` path), prints the path in green, and — unless `--no-open` was
passed — opens it in the system's default web browser via Python's `webbrowser` module.

### Example

```bash
uv run backstudio visualize blog.yml --output diagram.html --no-open
```

---

## `backstudio generate`

Generate a FastAPI backend from an ERD file.

```
Usage: backstudio generate [OPTIONS] ERD_FILE

  Generate a FastAPI backend from an ERD file.

Arguments:
  ERD_FILE  Path to the ERD YAML file  [required]

Options:
  --output PATH  Workspace directory  [default: workspace]
  --force        Overwrite existing generated code
  --help         Show this message and exit.
```

### Arguments and options

| Name | Flag forms | Type | Default | Help text |
|---|---|---|---|---|
| `ERD_FILE` | positional | `Path` | — (required) | "Path to the ERD YAML file"; must exist and be readable |
| `output` | `--output` | `Path` | `workspace` | "Workspace directory" |
| `force` | `--force` | `bool` flag | `False` | "Overwrite existing generated code" |

### Behavior

1. Loads and validates the ERD (same failure mode as `validate`/`visualize` on an invalid file).
2. Translates the ERD into generator state via `app.erd.translate.translate`.
3. Generates the project into `<output>/<project.name>/codebase` via
   `app.services.code_generator.CodeGenerator`. If that directory already exists and `--force`
   was not passed, generation fails with exit code `1` and a message telling you to pass
   `--force`; passing `--force` deletes and recreates the whole codebase directory.
4. **`.env` handling:** if a previous run's `.env` file exists under the output codebase
   directory, its content is preserved across a `--force` regeneration (so your secret isn't
   silently rotated). Otherwise, if the ERD has `auth` enabled and the relevant secret
   environment variable (`erd.auth.jwt.secret_env_var`) isn't already set in the current
   process, a random secret is generated and written to a new `.env` file, with a message
   telling you where.
5. **Alembic autogeneration:** if the generated project has an `alembic.ini` (i.e. a database is
   configured), `generate` best-effort runs `alembic revision --autogenerate -m initial` in the
   generated codebase directory (30s timeout). A failure here only prints a yellow warning — it
   never fails the `generate` command itself — and tells you to run the migration yourself once
   the database is reachable.
6. On success, prints the generated codebase path in bold green and a reminder to copy the
   directory into your project.

### Example

```bash
$ uv run backstudio generate blog.yml --output workspace
Generated at: workspace/BlogAPI/codebase
Copy this directory into your project.
```

Regenerating over an existing output without `--force` fails safely:

```bash
$ uv run backstudio generate blog.yml --output workspace
<error message>
Use --force to overwrite.
```
