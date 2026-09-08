<div align="center">
  <img src="./assets/logo.svg" alt="BackStudio Logo" width="200"/>

  # BackStudio

  **Generate a production-ready FastAPI backend from a YAML file describing your data model.**

  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
  [![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
</div>

## Overview

BackStudio's `backstudio` CLI reads a single YAML file describing your entities (an "ERD" —
entity-relationship definition) and generates a complete, runnable FastAPI backend: SQLAlchemy
models, generic repository functions, a full CRUD REST API per entity, an optional JWT auth
service, role-based access control (RBAC), and Alembic migration scaffolding. No server to run,
no UI to click through — write a YAML file, run one command, get a codebase.

This README is a full tutorial: installation, the ERD file format, every CLI command, a worked
example with real output, and how to run what gets generated.

> This repo also ships an older, UI-driven way to build backends (a React app talking to a REST
> API) — see [Legacy: Visual UI](#legacy-visual-ui-unmaintained) at the bottom. The CLI documented
> below is the actively maintained, tested path.

### What you get from one YAML file

- **SQLAlchemy models** — tables, columns, foreign keys, relationships (one-to-many, many-to-one,
  one-to-one, many-to-many), all with correct types and constraints.
- **A full CRUD REST API per entity** — `POST`/`GET`/`PUT`/`DELETE` routes wired to generic
  repository functions, not stubs — the generated code works without you writing anything.
- **JWT authentication** (optional) — `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`,
  bcrypt password hashing, access/refresh token separation.
- **RBAC** (optional) — declare roles once, restrict any CRUD action on any entity to specific
  roles, globally or per-entity.
- **Alembic migrations** — scaffolded and (best-effort) an initial migration generated for you.
- **An HTML ER diagram** — visualize your entities and relationships before you generate anything.

## Prerequisites

- **Python 3.11** (this repo pins `>=3.11,<3.12`)
- A package manager: [uv](https://docs.astral.sh/uv/) (recommended) or `pip`

## Installation

```bash
git clone <this-repo-url>
cd backstudio

# with uv (recommended)
uv sync

# or with pip
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e .
```

Either way this installs a `backstudio` console script (see `[project.scripts]` in
`pyproject.toml`) *inside that virtual environment* — `uv sync` does **not** put it on your
shell's PATH. Running `backstudio --help` straight after `uv sync`, in a fresh terminal, will
fail with `'backstudio' is not recognized...` (Windows) or `command not found` (macOS/Linux). Use
one of:

```bash
# 1. prefix every command with `uv run` (simplest, no activation needed)
uv run backstudio --help

# 2. or activate the venv once per session, then call it directly
.venv\Scripts\activate.bat      # Windows cmd.exe
.venv\Scripts\Activate.ps1      # Windows PowerShell
source .venv/bin/activate       # macOS/Linux
backstudio --help

# 3. or call the executable inside .venv directly, no activation
.venv\Scripts\backstudio.exe --help   # Windows
.venv/bin/backstudio --help           # macOS/Linux
```

If you installed with plain `pip install -e .` into a venv you already activated, `backstudio` is
already on PATH for that session — no prefix needed. Confirm it's working:

```bash
$ backstudio --help          # or `uv run backstudio --help`

Usage: backstudio [OPTIONS] COMMAND [ARGS]...

  Generate FastAPI backends from a YAML ERD.

Commands:
  generate   Generate a FastAPI backend from an ERD file.
  validate   Validate an ERD file without generating anything.
  visualize  Render an HTML ER diagram for the given ERD file.
```

Every command in the rest of this README assumes one of the three approaches above is in effect —
prefix with `uv run` (or activate the venv) as needed.

## Quick Start

Save this as `blog.yml` — a small blog API with two entities, a relationship, JWT auth, and RBAC
(this exact file is also checked into the repo at [`examples/blog.yml`](examples/blog.yml)):

```yaml
project:
  name: BlogAPI
  version: "1.0.0"
  description: A small blog API demonstrating auth, RBAC, and relationships

database:
  type: sqlite
  database_name: blog.db

auth:
  enabled: true
  jwt:
    secret_env_var: BLOG_JWT_SECRET
    algorithm: HS256
    expiration_minutes: 60

rbac:
  enabled: true
  roles: [admin, author, reader]
  default_permissions:
    read: [admin, author, reader]
    list: [admin, author, reader]
    create: [admin, author]
    update: [admin, author]
    delete: [admin]

entities:
  - name: Category
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: name, type: string, unique: true, max_length: 100}

  - name: Post
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: title, type: string, max_length: 200}
      - {name: body, type: text}
      - {name: published, type: boolean, default: false}
    relationships:
      - name: category
        cardinality: many-to-one
        target: Category
        ondelete: SET NULL
        nullable: true
    endpoints:
      rbac:
        delete: [admin]     # only admins can delete a Post; create/update inherit
                            # the global default_permissions above
```

**1. Validate it** — catches schema and semantic errors (unknown relationship targets, bad role
references, RBAC without auth, etc.) without generating anything:

```bash
$ backstudio validate examples/blog.yml
OK: 2 entities, 1 relationships, auth=on, rbac=on
```

**2. Visualize it** — renders a Mermaid ER diagram as a standalone HTML file and opens it in your
browser:

```bash
$ backstudio visualize examples/blog.yml
Diagram written to: examples/blog-diagram.html
```

(Pass `-o path.html` to control the output path, `--no-open` to skip auto-opening the browser.)

**3. Generate it.** Whenever `auth.enabled: true`, the JWT secret env var named in your ERD
(`BLOG_JWT_SECRET` here) must be set first — set it *before* running `generate`, otherwise the
codebase is still generated correctly, but the best-effort "create an initial migration for me"
step fails with a `RuntimeError` (see [Troubleshooting](#troubleshooting)):

```bash
export BLOG_JWT_SECRET="dev-secret-change-me"          # macOS/Linux/Git Bash
set BLOG_JWT_SECRET=dev-secret-change-me                # Windows cmd.exe
$env:BLOG_JWT_SECRET = "dev-secret-change-me"             # Windows PowerShell

backstudio generate examples/blog.yml --output workspace
```
```
Generated at: workspace/BlogAPI/codebase
Copy this directory into your project.
```

That's it — `workspace/BlogAPI/codebase` is a complete, runnable FastAPI project. Jump to
[Running the generated project](#running-the-generated-project) to start it, or keep reading for
the full YAML reference and CLI options.

## The ERD YAML format

An ERD file has five top-level sections. Only `project` and `database` are required.

### `project`

```yaml
project:
  name: BlogAPI          # required — also the generated project's directory/package name
  version: "1.0.0"        # optional, default "1.0.0"
  description: "..."       # optional
```

### `database`

```yaml
database:
  type: sqlite            # required: postgresql | mysql | sqlite (mongodb/redis are rejected —
                           # the generator only produces SQLAlchemy relational models)
  database_name: blog.db  # required
  host: localhost          # optional, default "localhost"
  port: 5432                # optional
  username: myuser            # optional
  use_env_vars: true           # optional, default true
  pool_size: 10                  # optional, default 10
  echo: false                     # optional, default false — echo SQL to stdout
```

### `auth` (optional, default disabled)

```yaml
auth:
  enabled: true
  jwt:
    secret_env_var: BLOG_JWT_SECRET   # name of the env var holding your JWT signing secret
    algorithm: HS256                    # default HS256
    expiration_minutes: 30                # access-token lifetime; default 30
```

When enabled, a `User` entity is automatically added to your model (`id`, `email`,
`password_hash`, `roles`, `is_active`, `created_at`, `updated_at`) and a full auth service is
generated (`/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`) — see
[Auth & RBAC in depth](#auth--rbac-in-depth) below. You can add your own extra fields to `User`
by declaring an entity literally named `User` in `entities:` (see below); you cannot redeclare the
reserved fields listed above.

### `rbac` (optional, default disabled — **requires `auth.enabled: true`**)

```yaml
rbac:
  enabled: true
  roles: [admin, author, reader]
  default_permissions:            # optional — applied to every entity unless overridden
    read: [admin, author, reader]
    list: [admin, author, reader]
    create: [admin, author]
    update: [admin, author]
    delete: [admin]
```

If you don't set `default_permissions` for an action, and an entity doesn't override it either,
that action defaults to "any authenticated user" (all declared roles) when RBAC is on. Setting
`rbac.enabled: true` without `auth.enabled: true` is rejected at validation time — RBAC needs a
way to identify the current user.

### `entities`

```yaml
entities:
  - name: Post                      # required, PascalCase by convention
    table_name: blog_posts           # optional, defaults to a pluralized snake_case of name
    fields: [...]                      # see below
    relationships: [...]                 # see below
    endpoints: {...}                       # see below
```

#### `fields`

```yaml
fields:
  - name: id
    type: integer          # string | integer | float | boolean | datetime | date | text | json | uuid
    primary_key: true       # optional, default false
    nullable: false           # optional, default true
    unique: true                # optional, default false
    index: true                   # optional, default false
    max_length: 200                 # optional — only meaningful for type: string
    default: 0                        # optional — a literal default value
```

#### `relationships`

One side declares the relationship; the other side is filled in automatically.

```yaml
relationships:
  - name: category               # relationship name — also used to derive attribute/column
                                    # names when two relationships target the same entity
    cardinality: many-to-one       # one-to-many | many-to-one | one-to-one | many-to-many
    target: Category                 # the other entity
    attribute: my_category              # optional override for this side's attribute name
    target_attribute: posts               # optional override for the other side's attribute name
    foreign_key_column: category_id         # optional override for the FK column name
    nullable: true                            # optional, default true
    unique: false                               # optional, default false
    ondelete: SET NULL                            # optional: CASCADE | SET NULL | RESTRICT | ...
    lazy: selectin                                  # optional SQLAlchemy lazy-loading strategy
    cascade: "all, delete-orphan"                     # optional SQLAlchemy cascade string
    association_table: post_tags                        # optional table name, many-to-many only
```

An entity with two relationships to the same target (e.g. a `Message` with a `sender` and a
`recipient`, both pointing at `Person`) is fully supported — attribute and column names are
derived from each relationship's own `name`, and the loader raises a clear error if two
relationships on the same entity would still collide.

#### `endpoints`

```yaml
endpoints:
  enabled: [create, list, read, update, delete]   # optional — subset of CRUD actions to generate;
                                                     # default is all five
  base_path: /posts                                 # optional override, default /{pluralized-name}
  tags: [posts]                                        # optional OpenAPI tags, default [pluralized-name]
  rbac:                                                  # optional, only meaningful when rbac.enabled
    create: [admin]                                        # overrides rbac.default_permissions
    delete: [admin]                                           # per action, per entity
```

## CLI commands reference

### `backstudio validate ERD_FILE`

Parses and semantically validates the file (duplicate names, dangling relationship targets,
unknown RBAC role references, `rbac.enabled` without `auth.enabled`, reserved `User` field
collisions, disallowed database types, and more). Exits `0` and prints a one-line summary on
success; exits `1` and prints the error on failure.

### `backstudio visualize ERD_FILE [OPTIONS]`

| Option | Description |
|---|---|
| `-o, --output PATH` | Output HTML path (default: `<erd-file-stem>-diagram.html` next to the source file) |
| `--open` / `--no-open` | Open the diagram in a browser (default: `--open`) |

### `backstudio generate ERD_FILE [OPTIONS]`

| Option | Description |
|---|---|
| `--output PATH` | Workspace directory (default: `workspace`) |
| `--force` | Overwrite an existing generated codebase at that path |

Runs validation, translates the ERD, generates the full codebase under
`<output>/<project.name>/codebase`, then makes a **best-effort** attempt to run
`alembic revision --autogenerate -m "initial"` inside the generated project — if that fails (no
reachable database, `alembic` not resolvable, etc.) a warning is printed with the underlying error
and generation still succeeds. Prints `Generated at: <path>` on success.

## Full worked example (with real output)

This is an actual transcript — every command below was run against `examples/blog.yml`. First,
`backstudio generate` (with the JWT secret already exported, so the Alembic autogenerate step
succeeds too):

```
$ export BLOG_JWT_SECRET="dev-secret-change-me"
$ backstudio generate examples/blog.yml --output workspace
Generated at: workspace/BlogAPI/codebase
Copy this directory into your project.
```

The generated tree:

```
workspace/BlogAPI/codebase/
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 8287127062cf_initial.py     # auto-generated by the best-effort step above
├── auth/
│   ├── routes.py                       # /auth/register /auth/login /auth/refresh /auth/me
│   ├── schemas.py
│   └── service.py
├── categories/
│   ├── routes.py                       # full CRUD for Category
│   └── schemas.py
├── posts/
│   ├── routes.py                       # full CRUD for Post, RBAC-restricted delete
│   └── schemas.py
├── database/
│   ├── base.py                         # engine, session, Base, get_db()
│   ├── models.py                       # Category, Post, User (auto-injected — auth is on)
│   └── repo.py                         # generic create/get/list/update/delete per entity
├── rbac.py                             # require_roles() dependency factory
├── config.py                           # Settings — reads DATABASE_URL, BLOG_JWT_SECRET, ...
├── server.py                           # FastAPI app, mounts every router above
├── dependencies.py
├── middleware.py
├── requirements.txt
└── README.md
```

Now drive the running application (this uses FastAPI's `TestClient`, but it's the same API you'd
hit with `curl` against a real running server — see the next section):

```
>>> POST /auth/register -> 201
{
  "id": 1, "email": "alice@example.com",
  "roles": ["admin", "author", "reader"],   # <- the FIRST registered user gets every declared
  "is_active": true                          #    role automatically; see Auth & RBAC below
}

>>> POST /auth/register (same email again) -> 400
{"detail": "Email already registered"}

>>> POST /auth/login -> 200
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}

>>> GET /auth/me  (Authorization: Bearer <access_token>) -> 200
{"id": 1, "email": "alice@example.com", "roles": ["admin","author","reader"], "is_active": true}

>>> POST /categories {"name": "Engineering"}  -> 201
{"id": 1, "name": "Engineering"}

>>> POST /posts {"title": "Hello, BackStudio", "body": "Generated from an ERD.",
                 "published": true, "category_id": 1}  -> 201
{"id": 1, "title": "Hello, BackStudio", "body": "Generated from an ERD.", "published": true}

>>> GET /posts  (with token) -> 200
[{"id": 1, "title": "Hello, BackStudio", "body": "Generated from an ERD.", "published": true}]

>>> GET /posts  (no token) -> 401
{"detail": "Not authenticated"}

>>> POST /auth/login (wrong password) -> 401
{"detail": "Invalid email or password"}
```

## Running the generated project

```bash
cd workspace/BlogAPI/codebase
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# whatever env vars your ERD's auth.jwt.secret_env_var / database config need, e.g.
# (macOS/Linux/Git Bash: export VAR=value | Windows cmd.exe: set VAR=value |
#  Windows PowerShell: $env:VAR = "value"):
export BLOG_JWT_SECRET="use-a-long-random-value-in-production"
export DATABASE_URL="sqlite:///./blog.db"          # or a postgres/mysql URL

uvicorn server:app --reload
```

Then visit `http://localhost:8000/docs` for interactive Swagger docs covering every generated
route. To apply migrations instead of relying on the app's own `init_db()` table-creation on
startup:

```bash
alembic upgrade head
```

## Auth & RBAC in depth

- **Password hashing**: bcrypt via `passlib`. Plaintext passwords are never stored or compared.
- **Tokens**: access tokens (short-lived, per `auth.jwt.expiration_minutes`) and refresh tokens
  (7 days) are distinct — each carries a `type` claim (`"access"` / `"refresh"`) and each endpoint
  rejects the wrong type, so a leaked access token can't be used to mint fresh refresh tokens.
- **First-user bootstrap**: when RBAC is enabled, the very first user to register is granted every
  declared role — otherwise nobody could ever pass an RBAC check on a fresh database. Every
  subsequent registration gets no roles by default; assign roles to later users directly in your
  database (or add your own role-management endpoint on top of the generated code).
- **JWT secret is required, not defaulted**: `config.py`'s `Settings` reads the env var you named
  in `auth.jwt.secret_env_var` and **raises at startup** if it's unset — there is no insecure
  built-in fallback secret. Set it before starting the server or running Alembic.
- **RBAC enforcement**: each generated CRUD route conditionally carries a
  `Depends(require_roles(...))` per action, resolved from (in order) the entity's own
  `endpoints.rbac` override, then `rbac.default_permissions`, then "any authenticated user" if
  RBAC is on and neither is set.

## Database configuration

For local development, `type: sqlite` (as in the example above) needs nothing else — the
generated project defaults `DATABASE_URL` to a local `.db` file if you don't set one. For
PostgreSQL or MySQL:

```yaml
database:
  type: postgresql
  host: db.example.com
  port: 5432
  database_name: blog_production
  username: blog_app
```

Then set `DATABASE_URL` yourself in the generated project's environment, e.g.
`postgresql://blog_app:PASSWORD@db.example.com:5432/blog_production` — the ERD's `database:`
block documents the connection *shape*, credentials are always supplied via environment variables
at runtime, never written into generated source.

## Troubleshooting

- **`'backstudio' is not recognized...` / `command not found`** right after `uv sync`** — the
  console script was installed into `.venv`, not onto your shell's PATH. Use `uv run backstudio
  ...`, or activate the venv first (`.venv\Scripts\activate.bat` on Windows,
  `source .venv/bin/activate` on macOS/Linux) — see [Installation](#installation).
- **`RuntimeError: Required environment variable '...' is not set`** — set the env var named in
  your ERD's `auth.jwt.secret_env_var` *before* running `backstudio generate` (so the best-effort
  Alembic step can succeed too), and again before running the generated app or Alembic yourself
  later (each new shell needs it set fresh — it isn't persisted anywhere). `export VAR=value` on
  macOS/Linux/Git Bash, `set VAR=value` on Windows `cmd.exe`, `$env:VAR = "value"` on PowerShell.
- **`Warning: could not auto-generate the initial Alembic migration`** during `backstudio
  generate`** — this is the best-effort autogenerate step failing (commonly: the JWT secret env
  var wasn't set yet at generate-time, since `alembic/env.py` imports the same `config.py`). The
  warning includes the underlying error. Generation itself still succeeded; export the right env
  vars and run `alembic revision --autogenerate -m "initial"` yourself inside the generated
  project once they're set.
- **`ERD schema validation failed` / a specific "Entity '...' ..." error** from `validate` or
  `generate`** — the error names the offending entity, field, or role and the rule that was
  violated; fix the YAML and re-run `validate`.
- **`rbac.enabled requires auth.enabled`** — RBAC has no way to identify the current user without
  auth; set `auth.enabled: true` too.

## Repository layout

```
backstudio/
├── backend/
│   ├── erd/              # YAML parsing (schema.py), validation (loader.py),
│   │                        translation to the generation engine (translate.py),
│   │                        HTML/Mermaid visualization (visualize.py)
│   ├── cli/               # backstudio's Typer commands (main.py)
│   ├── services/            # code_generator.py — the Jinja2-based generation engine
│   ├── templates/Python/      # every Jinja2 template that produces generated-project files
│   ├── schemas/                 # Pydantic models shared by the CLI and the legacy REST API
│   └── api/                       # the legacy REST API (see Legacy: Visual UI below)
├── examples/                # example ERD files, incl. blog.yml used throughout this README
├── workspace/                 # `backstudio generate`'s default output directory
├── frontend/                    # the legacy React UI (see below)
└── mcp_server/                    # Model Context Protocol server for the legacy REST API
```

## Legacy: Visual UI (unmaintained)

Before the `backstudio` CLI existed, this repo's only interface was a FastAPI backend
(`backend/api/routes.py`, `backend/services/project_service.py`) paired with a React frontend
(`frontend/`) where you built up a project's models/services/endpoints one REST call at a time
(see `examples/example_project_generator.py` for what that looked like — roughly 1,100 lines of
Python to describe a 6-model e-commerce API). It still runs, and shares the same underlying
Jinja2 templates and `CodeGenerator` the CLI uses for the parts of the pipeline that predate the
ERD/YAML approach (`database/models.py`, `database/repo.py`), but it is **not** part of this
repo's test suite and receives no further development. If you want to try it anyway:

```bash
# Terminal 1
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2
cd frontend && npm install && npm run dev
```

- Frontend UI: http://localhost:5173
- Backend API + docs: http://localhost:8000/docs

New projects should use the CLI documented above.

## Checksum system

Both the CLI and legacy paths use the same underlying `CodeGenerator`, which is deterministic —
the same specification always produces the same generated code.

## Contributing

Contributions are welcome — templates, additional field/relationship coverage, documentation, and
tests are all useful. See `docs/superpowers/specs/` and `docs/superpowers/plans/` for the design
spec and implementation plan behind the `backstudio` CLI if you want the full rationale for how
it's put together.

## License

MIT License — see [LICENSE](LICENSE) for details.
