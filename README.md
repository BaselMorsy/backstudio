<div align="center">
  <img src="./assets/logo.svg" alt="BackStudio Logo" width="200"/>

  # BackStudio

  **Generate a production-ready FastAPI backend from a YAML file describing your data model.**

  [![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
  [![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
</div>

## What it is

BackStudio's `backstudio` CLI reads a single YAML file describing your entities (an "ERD" —
entity-relationship definition) and generates a complete, runnable FastAPI application: SQLAlchemy
models, a service layer, and a full FastAPI CRUD REST API per entity — routes calling straight
into generated service functions, both wired together, not just a database schema. Optional JWT
authentication, role-based access control (RBAC), row-level security, and Alembic migration
scaffolding are wired into that same service+routes pair. Set `database.async_mode: true` and the
whole stack — models, service methods, and the route handlers themselves — becomes `async def`
end to end, not just the SQL. No server to run, no UI to click through — write a YAML file, run
one command, get a runnable codebase. Generation is also deterministic: the same ERD always
produces the same generated code. See [Feature overview](#feature-overview) below for the full
mechanics of each piece.

## Quick start

### Install

```bash
git clone <this-repo-url>
cd backstudio
uv sync
```

This installs a `backstudio` console script (see `[project.scripts]` in `pyproject.toml`) inside
`.venv` — it is **not** automatically on your shell's PATH. Prefix commands with `uv run`, or
activate the venv first (`.venv\Scripts\activate.bat` on Windows, `source .venv/bin/activate` on
macOS/Linux) and call `backstudio` directly:

```bash
$ uv run backstudio --help

Usage: backstudio [OPTIONS] COMMAND [ARGS]...

  Generate FastAPI backends from a YAML ERD.

Commands:
  generate   Generate a FastAPI backend from an ERD file.
  validate   Validate an ERD file without generating anything.
  visualize  Render an HTML ER diagram for the given ERD file.
```

### A minimal ERD

Save this as `blog.yml`:

```yaml
project:
  name: BlogAPI
  version: "1.0.0"

database:
  type: sqlite
  database_name: blog.db

entities:
  - name: Post
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: title, type: string, max_length: 200}

services:
  - name: posting
    entities: [Post]
```

For a fuller example with a relationship, JWT auth, and RBAC, see
[`examples/blog.yml`](examples/blog.yml).

**Validate it:**

```bash
$ uv run backstudio validate blog.yml
OK: 1 entities, 0 relationships, auth=off, rbac=off
```

**Generate it:**

```bash
$ uv run backstudio generate blog.yml --output workspace
Generated at: workspace/BlogAPI
Copy this directory into your project.
```

**Run it:**

```bash
cd workspace/BlogAPI
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

uvicorn server:app --reload
```

Then visit `http://localhost:8000/docs` for interactive Swagger docs covering every generated
route.

## Feature overview

- **Authentication** — optional JWT auth (`/auth/register`, `/auth/login`, `/auth/refresh`,
  `/auth/me`), bcrypt password hashing, email verification, password reset, and admin user
  management (listing, deactivating, and role management for users). See
  [docs-site/features/auth.md](docs-site/features/auth.md).
- **RBAC** — declare roles once, then restrict any CRUD action on any entity to specific roles,
  either globally (`rbac.default_permissions`) or per entity (`endpoints.rbac`). See
  [docs-site/features/rbac.md](docs-site/features/rbac.md).
- **Row-Level Security** — scope an entity's reads and writes to the resolved owner of each row
  (from the authenticated user or a request header), with bypass roles for admins. See
  [docs-site/features/rls.md](docs-site/features/rls.md).
- **Async, end to end** — set `database.async_mode: true` to generate an async SQLAlchemy stack
  (async engine/session, `select()`/`execute()`-based repo layer) — and the service methods and
  FastAPI route handlers built on top become `async def` too, so the whole request path is
  non-blocking, not just the database calls. See
  [docs-site/features/async.md](docs-site/features/async.md).

## CLI reference

Three commands:

- `backstudio validate ERD_FILE` — parse and semantically validate an ERD file without
  generating anything.
- `backstudio visualize ERD_FILE [-o/--output PATH] [--open/--no-open]` — render an HTML ER
  diagram for the given ERD file.
- `backstudio generate ERD_FILE [--output PATH] [--force]` — generate a full FastAPI backend
  from an ERD file.

Full flag-by-flag details and the ERD YAML format: [docs-site/cli-reference.md](docs-site/cli-reference.md).

## Project layout

```
backstudio/
├── app/
│   ├── cli/               # backstudio's Typer commands (main.py)
│   ├── erd/                # YAML parsing (schema.py), validation (loader.py),
│   │                          translation to the generation engine (translate.py),
│   │                          HTML/Mermaid visualization (visualize.py)
│   ├── services/             # code_generator.py — the Jinja2-based generation engine
│   ├── templates/Python/       # every Jinja2 template that produces generated-project files
│   ├── utils/                    # checksum, file-ops, and id-generation helpers
│   └── tests/                      # the test suite
├── examples/                  # example ERD files, incl. blog.yml used throughout this README
├── docs/superpowers/            # design specs and implementation plans
├── docs-site/                      # mkdocs-material documentation site source (see below)
├── assets/                            # logo and other README images
├── workspace/                           # backstudio generate's default output directory
├── mkdocs.yml                             # docs-site config — see "Documentation site" below
└── pyproject.toml
```

### Documentation site

The full documentation site (architecture notes, ERD field reference, feature deep-dives, CLI
reference) lives under `docs-site/`, configured by `mkdocs.yml`, and is built with
`mkdocs`/`mkdocs-material` — both dev dependencies, already installed via the `dev` dependency
group after `uv sync`. Preview it locally with:

```bash
uv run mkdocs serve
```

## Contributing

Contributions are welcome — templates, additional field/relationship coverage, documentation, and
tests are all useful. See `docs/superpowers/specs/` and `docs/superpowers/plans/` for the design
spec and implementation plan behind the `backstudio` CLI if you want the full rationale for how
it's put together.

## License

MIT License — see [LICENSE](LICENSE) for details.
