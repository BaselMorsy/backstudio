# Installation

## Requirements

- **Python 3.11 or 3.12** — the project's `pyproject.toml` pins
  `requires-python = ">=3.11,<3.13"`; Python 3.13+ isn't supported yet (`pydantic-core`'s pinned
  version has no prebuilt wheel for 3.13, which would need a Rust toolchain to build from
  source). The `.python-version` file pins 3.11 as the primary/tested development interpreter,
  but 3.12 is also verified working.
- **[uv](https://docs.astral.sh/uv/)** — used to manage the virtual environment and
  dependencies. `uv` will provision a matching Python interpreter for you if you don't already
  have one on your PATH.

## Install from a fresh clone

```bash
git clone <this-repo-url>
cd backstudio
uv sync
```

`uv sync` creates a `.venv` in the repo root and installs the pinned dependencies from
`pyproject.toml`, including a `backstudio` console script — declared as
`[project.scripts]` → `backstudio = "app.cli.main:app"` — inside that `.venv`.

## Running the CLI

The `backstudio` script lives inside `.venv` and is **not** automatically on your
shell's PATH. You have two options:

**Option 1 — prefix every command with `uv run` (recommended):**

```bash
uv run backstudio --help
```

**Option 2 — activate the virtual environment first, then call `backstudio` directly:**

```bash
# Windows (cmd.exe)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

backstudio --help
```

Either way, you should see:

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

Commands:
  generate   Generate a FastAPI backend from an ERD file.
  validate   Validate an ERD file without generating anything.
  visualize  Render an HTML ER diagram for the given ERD file.
```

(this exact output was captured by running `uv run backstudio --help` against the
current repo).

## Next step

Continue to the **[Quick start](quick-start.md)** to validate and generate your first
backend from an ERD file.
