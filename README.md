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

services:
  - name: posting
    entities: [Category, Post]
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

**3. Generate it:**

```bash
$ backstudio generate examples/blog.yml --output workspace
Generated a random BLOG_JWT_SECRET for local development and wrote it to
workspace/BlogAPI/codebase/.env. Replace it with a securely-managed secret before deploying.
Generated at: workspace/BlogAPI/codebase
Copy this directory into your project.
```

You don't need to set anything by hand for a local first run: whenever `auth.enabled: true` and
the JWT secret env var named in your ERD (`BLOG_JWT_SECRET` here) isn't already set,
`generate` writes a fresh, cryptographically random one straight into
`<codebase>/.env` — the generated `config.py` loads that file automatically, so the app, Alembic,
and everything else just works. **Replace that value with your own securely-managed secret before
deploying anywhere real** — treat it exactly like any other `.env`-committed credential (it's
already covered by the generated project's `.gitignore`). If you'd rather supply your own value
from the start, set the env var yourself *before* running `generate` and it's used as-is (a `.env`
that already exists in a target directory is never overwritten, including across `--force`
regenerations — see [Auth & RBAC in depth](#auth--rbac-in-depth)).

That's it — `workspace/BlogAPI/codebase` is a complete, runnable FastAPI project. Jump to
[Running the generated project](#running-the-generated-project) to start it, or keep reading for
the full YAML reference and CLI options.

## The ERD YAML format

An ERD file has six top-level sections. `project` and `database` are always required; `services`
is required as soon as you declare any entities (which is to say, in practice, always — see
[`services`](#services) below).

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
  async_mode: false              # optional, default false — when true, generates an async
                                   # SQLAlchemy stack (async engine/session, select()/execute()-based
                                   # repo layer, async def service/route/auth handlers) instead of sync.
                                   # For non-SQLite databases, DATABASE_URL needs an async-driver-qualified
                                   # scheme: sqlite+aiosqlite:/// for SQLite, postgresql+asyncpg:// for
                                   # PostgreSQL, mysql+aiomysql:// for MySQL
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
generated. **Every auth route — the four above and every one added by `registration`/`rbac` below
— is mounted under a single `/auth` prefix** (`/auth/register`, `/auth/login`, `/auth/refresh`,
`/auth/me`, ...; the prefix follows `auth_module_name`, which defaults to `auth` and can be
renamed — see [`services`](#services)) — see [Auth & RBAC in depth](#auth--rbac-in-depth) below.
You can add your own extra fields to `User` by declaring an entity literally named `User` in
`entities:` (see below); you cannot redeclare the reserved fields listed above (which fields are
reserved depends on `registration.mode` — see immediately below).

#### `auth.registration` (optional, default `open`)

```yaml
auth:
  enabled: true
  registration:
    mode: open   # open | email_verification | admin_approval — default "open"
```

Three mutually exclusive modes govern what happens between `POST /auth/register` and a user being
able to actually log in. In every mode, registering itself always succeeds and creates the row —
the gate is enforced at **login** (`POST /auth/login` / `authenticate_user`), not at registration:

| Mode | Requires | Gates |
|---|---|---|
| `open` (default) | nothing | nothing — a freshly registered user can log in immediately. |
| `email_verification` | nothing extra | adds `is_verified: bool` (default `false`) to `User`/`UserResponse`; login is rejected with `401 Email not verified` until it's `true`; adds `POST /auth/verify-email` and `POST /auth/resend-verification`. |
| `admin_approval` | `rbac.enabled: true` (checked at load time — approval is an admin-gated endpoint) | adds `is_approved: bool` (default `false`) to `User`/`UserResponse`; login is rejected with `401 Account pending approval` until it's `true`; adds `POST /auth/users/{id}/approve`. |

#### `auth.jwt`'s other three lifetimes

Beyond `algorithm` and `expiration_minutes` (the access-token lifetime, shown above), three more
independently configurable token lifetimes live on `auth.jwt`:

```yaml
auth:
  jwt:
    expiration_minutes: 30                        # access token — default 30
    refresh_token_expiration_minutes: 10080        # refresh token — default 10080 (7 days)
    email_verification_expiration_minutes: 1440    # email-verification token — default 1440 (24h)
    password_reset_expiration_minutes: 30           # password-reset token — default 30
```

Each is used for exactly one token `type` claim (`access` / `refresh` / `email_verification` /
`password_reset`); an endpoint that decodes a token rejects it if the `type` doesn't match what
that endpoint expects. `email_verification_expiration_minutes` only does anything when
`auth.registration.mode: email_verification` is set — the other three are always in effect.

#### New auth endpoints

**Admin user management** — generated whenever `rbac.enabled: true` (which itself requires
`admin` to be declared in `rbac.roles`, checked at load time). Every route below is gated to the
`admin` role:

| Method & path | Description |
|---|---|
| `GET /auth/users` | List users (`skip`/`limit` query params). |
| `GET /auth/users/{id}` | Get one user by id — `404` if it doesn't exist. |
| `PUT /auth/users/{id}/roles` | Replace a user's roles — `400` on an unknown role, `404` on a missing user. |
| `POST /auth/users/{id}/deactivate` | Set `is_active: false`. |
| `POST /auth/users/{id}/reactivate` | Set `is_active: true`. |
| `POST /auth/users/{id}/approve` | Set `is_approved: true` — only generated when `auth.registration.mode: admin_approval`. |

There's no hard delete — `deactivate`/`reactivate` are the only lifecycle controls.

**Email verification** — generated whenever `auth.registration.mode: email_verification`:

| Method & path | Description |
|---|---|
| `POST /auth/verify-email` | Body `{"token": "..."}` — marks the user verified; `400` on an invalid/expired token. |
| `POST /auth/resend-verification` | Body `{"email": "..."}` — always returns the same generic message, whether or not that email is registered or already verified (avoids leaking which emails exist). |

**Forgot / reset password** — always generated, regardless of `registration.mode` or
`rbac.enabled`:

| Method & path | Description |
|---|---|
| `POST /auth/forgot-password` | Body `{"email": "..."}` — always returns the same generic message (enumeration-safe); if the email exists, a reset token is generated and handed to the dev-mode `send_email()` stub. |
| `POST /auth/reset-password` | Body `{"token": "...", "new_password": "..."}` — `400` on an invalid, expired, or already-used token. |

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

A relationship targeting its own entity (e.g. `Employee` → `Employee` for a `manager`) is
rejected with a clear error — self-referential relationships are not supported yet.

**What a relationship adds to the generated API.** Declaring a relationship doesn't just wire
up `database/models.py`; it also changes the generated schemas, service and routes:

- **`many-to-one` / `one-to-one`** (and `one-to-many` seen from the FK-owning side) — the
  entity that holds the FK column gets that column as a real field on all three of its
  schemas. For `examples/blog.yml`'s `Post` → `Category`, `PostCreate`, `PostUpdate` and
  `PostResponse` each gain `category_id: Optional[int] = None` (it's `int` instead when the
  relationship is `nullable: false`, and named after `foreign_key_column` if you override it).
  So `POST /posts` with `{"title": "Hi", "body": "...", "category_id": 3}` now sets the
  category, and `category_id` comes back in the response body.
- **A nonexistent id returns `400`.** The service checks the referenced row exists before
  writing, so `POST /posts` with `{"category_id": 999}` returns
  `400 {"detail": "Category 999 not found"}` rather than a raw DB error (or, on SQLite, a
  silently dangling reference). The check is advisory, not transactional.
- **The owning entity's list endpoint gains a filter.** `list_post_route` picks up an optional
  `category_id` query param, so `GET /posts?category_id=3` returns only that category's posts —
  the read direction of a one-to-many, without a nested collection on `CategoryResponse`.
- **`many-to-many`** — the `Response` schema (only) gains a read-only id list named after the
  **target model in singular snake_case** plus `_ids`: a `Post` with a many-to-many to `Tag`
  gets `tag_ids: List[int] = []` on `PostResponse`, and `Tag` gets `post_ids` on
  `TagResponse`. It's populated from the loaded association (via `selectinload`, so listing
  posts costs one extra query, not one per row). There is no write path for it yet — sending
  `tag_ids` to `POST`/`PUT` does nothing; associate rows in your own code for now.

##### Row-level access control (`owner`, `cascades_ownership`, `rls`)

A `many-to-one` relationship can additionally opt into ownership:

```yaml
relationships:
  - {name: user, cardinality: many-to-one, target: User, owner: true}
    # marks this FK as the entity's ownership column — Order.user_id, here

  - {name: order, cardinality: many-to-one, target: Order, cascades_ownership: true}
    # OrderItem has no owner column of its own; it inherits Order's ownership through
    # this FK instead — to arbitrary depth (an entity owned via a chain of
    # cascades_ownership relationships is filtered the same way a direct owner is)
```

`owner: true` and `cascades_ownership: true` are mutually exclusive per relationship, and an
entity may declare at most one ownership path (one `owner: true` relationship, or one
`cascades_ownership: true` relationship, not both and not more than one of either).

Declaring either one only marks *which* column carries ownership — enforcement is opted into
separately, per entity, with an `rls:` block:

```yaml
entities:
  - name: Order
    relationships:
      - {name: user, cardinality: many-to-one, target: User, owner: true}
    rls:
      identity_source:
        type: auth_user            # auth_user | header
        # header_name: X-Tenant-Id   # required when type: header — see below
      bypass_roles: [admin]        # optional; requires rbac.enabled — these roles see every row
```

- **`identity_source: {type: auth_user}`** resolves ownership from the authenticated caller
  (`current_user.id`, via the existing auth dependency) — requires `auth.enabled: true`. Every
  generated route for the entity gains `current_user: User = Depends(...)` and a
  `owner_id = None if <caller has a bypass role> else current_user.id` line before calling into
  the service; `owner_id=None` means "no filter" (only reachable via `bypass_roles`).
- **`identity_source: {type: header, header_name: X-Tenant-Id}`** resolves ownership from a
  required request header instead of the authenticated user — no `auth.enabled` needed. Every
  generated route gains `rls_owner_header: int = Header(..., alias="X-Tenant-Id")`; a request
  missing that header gets FastAPI's own native `422`, with no custom error handling involved.
  A `header`-sourced entity can still coexist with `auth.enabled`/`rbac.enabled: true` elsewhere
  in the same project (e.g. RBAC gating who may call the route at all, while the header — not
  the caller — still governs ownership); `rls_header_owned_with_rbac.yml` is exactly this
  combination, and it's real and tested. `bypass_roles`, however, is only ever consulted from the
  *authenticated caller's* roles, so it has no source to read from on a `header`-sourced entity —
  **combining the two is rejected at load time** with a validation error rather than silently
  doing nothing. (RBAC-gating a header-sourced entity's *endpoints* is unaffected: that's
  `endpoints.rbac` / `rbac.default_permissions`, not `rls.bypass_roles`.)
- **`bypass_roles: [admin, ...]`** lets listed roles see and act on every row, unfiltered. It
  requires `rbac.enabled: true`, and is only valid on an `identity_source: {type: auth_user}`
  entity (where `current_user`'s roles are available to check) — pairing it with
  `identity_source: {type: header}` is a load-time error.
  Bypass applies to reads and to acting on existing rows (`list`/`read`/`update`/`delete`); it
  does **not** change who owns a row the bypass caller *creates*. `POST` always stamps the
  caller's own id as the owner, so an admin's newly created row belongs to that admin, never to
  nobody.

**What it changes elsewhere:**
- The `owner: true` FK column (e.g. `user_id`) is **omitted from `Create`/`Update` schemas** —
  a client-supplied value for it is silently dropped by Pydantic, not read — but still appears
  on the `Response` schema. A `cascades_ownership: true` FK (e.g. `OrderItem.order_id`) is an
  ordinary field on all three schemas, same as any other relationship FK.
  `OrderCreate` from `rls_root_owned.yml`, rendered, has only
  `status: Optional[str] = 'pending'` — no `user_id` field at all.
- **List and single-row reads are filtered to the resolved owner** (or unfiltered, for a
  bypass-role caller). A non-owner's `GET`/`PUT`/`DELETE` on someone else's row returns a plain
  **`404`**, identical to a nonexistent id — ownership is never distinguishable from
  nonexistence.
- **A cascaded write against a parent you don't own returns `400`**, the same status (and the
  same code path) as a nonexistent FK — `POST /order_items` with an `order_id` belonging to
  another owner fails exactly like `order_id: 999999` would.
- **A `header`-sourced create with an owner id that doesn't exist returns `400`** — the header
  is raw client input, so `POST /orders` with `X-Tenant-Id: 999999` is validated against the
  `Tenant` table and rejected exactly like any other nonexistent FK, rather than writing a
  dangling owner column. (No such check is needed — or generated — for `auth_user`, where the
  owner id comes from the JWT-authenticated `User`.)
- RLS-affected entities always require a resolved identity to write, so `cascades_ownership`
  entities also gain a `current_user` (or header) dependency on every route even when RBAC
  imposes no role restriction on the action — the owner filter has to run either way.
- All of the above is generated identically for `database.async_mode: true` — the RLS filter is
  applied in the same `async def` repo/service/route functions the rest of the async stack uses.

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

### `services`

```yaml
services:
  - name: posting              # required — lowercase, must be a valid Python identifier
                                  # (it becomes the generated modules/<name>/ directory
                                  # and function-name segment, e.g. get_posting_service)
    entities: [Category, Post]     # required, non-empty — entities generated under this module
  - name: ordering
    entities: [Order]
```

Every declared entity must be assigned to **exactly one** service — `validate`/`generate` reject
an ERD that leaves any entity unassigned, or assigns one to more than one service. Each service
becomes one `modules/<name>/` directory in the generated project, containing that service's
`schemas.py`, `service.py`, and `routes.py` for every entity it owns (see
[Full worked example](#full-worked-example-with-real-output) below for what that looks like on
disk).

`User` is the one exception: when `auth.enabled: true`, the auto-injected `User` entity does
**not** need to appear in any `services:` entry — it gets its own auto-created module named
`auth` (i.e. `modules/auth/`) for free. If you want to rename that module (e.g. to avoid a
naming clash with one of your own services, or just for taste), declare a `services:` entry whose
`entities` is *exactly* `[User]`:

```yaml
services:
  - name: identity        # renames the auth module: modules/identity/, /identity/register, ...
    entities: [User]
  - name: posting
    entities: [Category, Post]
```

A regular (non-`User`) service is not allowed to reuse whatever name the auth module resolves to
(`auth` by default, or your renamed one) — that collision would silently overwrite the auth
module's generated files with the regular service's files (or vice versa), so it's rejected at
validation time instead.

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

**`--force` fully overwrites, with no preservation of hand-edited code**: `generate --force`
deletes the entire `<output>/<project.name>/codebase` directory (via `shutil.rmtree`) and
regenerates it from scratch. The **only** thing preserved across a `--force` regeneration is an
existing `.env` file — anything else you've hand-edited, including business logic you've added to
`modules/*/service.py` (the intended customization surface — see
[Full worked example](#full-worked-example-with-real-output)), is destroyed and replaced with
freshly generated code. Treat `backstudio generate` as a one-time scaffold, not a tool that keeps
your codebase in sync with the ERD — back up and reapply any hand-written changes yourself before
running it again with `--force`.

## Full worked example (with real output)

This is an actual transcript — every command below was run against `examples/blog.yml`, with no
env vars set beforehand:

```
$ backstudio generate examples/blog.yml --output workspace
Generated a random BLOG_JWT_SECRET for local development and wrote it to
workspace/BlogAPI/codebase/.env. Replace it with a securely-managed secret before deploying.
Generated at: workspace/BlogAPI/codebase
Copy this directory into your project.
```

The generated tree:

```
workspace/BlogAPI/codebase/
├── .env                                # auto-generated random secret — see above
├── .gitignore                          # ignores .env, __pycache__, *.db, venv/, ...
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 8287127062cf_initial.py     # auto-generated by the best-effort step above
├── modules/
│   ├── auth/
│   │   ├── routes.py                   # /auth/register /auth/login /auth/refresh /auth/me
│   │   ├── schemas.py
│   │   └── service.py
│   └── posting/                        # from services: [{name: posting, entities: [Category, Post]}]
│       ├── routes.py                   # full CRUD for Category and Post, RBAC-restricted delete
│       ├── schemas.py
│       └── service.py                  # PostingService — your customization surface
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
{"id": 1, "title": "Hello, BackStudio", "body": "Generated from an ERD.", "published": true,
 "category_id": 1}

>>> GET /posts  (with token) -> 200
[{"id": 1, "title": "Hello, BackStudio", "body": "Generated from an ERD.", "published": true,
  "category_id": 1}]

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

uvicorn server:app --reload
```

That's it if auth is enabled — the `.env` `generate` wrote already has a working (random, dev-only)
JWT secret, and `config.py` loads it automatically. Override anything by editing `.env` directly,
or by exporting a real env var (which always wins over `.env`):

```bash
# (macOS/Linux/Git Bash: export VAR=value | Windows cmd.exe: set VAR=value |
#  Windows PowerShell: $env:VAR = "value"):
export DATABASE_URL="postgresql://user:pass@host:5432/blog_production"
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
  (per `auth.jwt.refresh_token_expiration_minutes`, default 10080 minutes = 7 days) are distinct
  — each carries a `type` claim (`"access"` / `"refresh"`) and each endpoint rejects the wrong
  type, so a leaked access token can't be used to mint fresh refresh tokens. Email-verification
  and password-reset tokens are separate JWTs the same way (`"email_verification"` /
  `"password_reset"` type claims, their own `auth.jwt.*_expiration_minutes` lifetimes) — see
  [`auth.registration`](#authregistration-optional-default-open) and
  [New auth endpoints](#new-auth-endpoints) above.
- **Password-reset tokens are single-use, with no new database table**: `create_password_reset_token`
  embeds a truncated SHA-256 fingerprint of the user's *current* `password_hash` as an extra JWT
  claim. `verify_password_reset_token(db, token)` decodes the token, looks up that same user's
  *current* `password_hash` fresh from the database (by the id the token itself decodes to — never
  a caller-supplied hash), and rejects the token unless the fingerprint still matches. Since
  `POST /auth/reset-password` changes `password_hash` before returning, using the token once
  invalidates it for any replay — a stateless JWT achieving genuine single-use semantics with no
  server-side revocation list. Note this covers only the reset token itself: any access/refresh
  token already issued before the reset stays valid until it naturally expires — resetting a
  password does not evict existing sessions.
- **First-user bootstrap**: when RBAC is enabled, the very first user to register is granted every
  declared role — otherwise nobody could ever pass an RBAC check on a fresh database. Every
  subsequent registration gets no roles by default; an admin grants roles to later users via
  `PUT /auth/users/{id}/roles` (see [New auth endpoints](#new-auth-endpoints) above).
- **JWT secret is required, not defaulted**: `config.py`'s `Settings` reads the env var you named
  in `auth.jwt.secret_env_var` (via a `.env` file, or the real process environment — an exported
  env var always takes priority over `.env`) and **raises at startup** if neither provides it —
  there is no insecure built-in fallback secret. `backstudio generate` writes a random one to
  `.env` for you on a project's first generation (see [Quick Start](#quick-start)); it's never
  regenerated or overwritten on later `--force` regenerations, so treat that `.env` as the
  project's real local secret from that point on — rotate it yourself if you want a new one.
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
- **`RuntimeError: Required environment variable '...' is not set`** — this should be rare on a
  fresh `backstudio generate` (it auto-writes a `.env` with a random secret for you), but it can
  still happen if: you deleted `.env` from the generated project, you're running against a
  *different* copy of the codebase than the one `.env` was written into, or you're setting a
  different env var name than the one in `auth.jwt.secret_env_var`. Set it (in `.env`, or
  `export VAR=value` / `set VAR=value` / `$env:VAR = "value"`) and re-run.
- **`Warning: could not auto-generate the initial Alembic migration`** during `backstudio
  generate`** — the best-effort autogenerate step failed for some other reason (commonly: no
  reachable database for a non-sqlite `database.type`, or `alembic` unavailable in your
  environment). The warning includes the underlying error. Generation itself still succeeded; fix
  whatever the error names and run `alembic revision --autogenerate -m "initial"` yourself inside
  the generated project.
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
