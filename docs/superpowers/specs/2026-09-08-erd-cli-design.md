# ERD-driven CLI Code Generator — Design Spec

Date: 2026-09-08
Status: Approved for implementation planning

## 1. Motivation

BackStudio currently generates FastAPI backends by building up a `ProjectState`
through a REST API (driven either by hand-written scripts like
`examples/example_project_generator.py`, or the React UI), one granular
call per model/relationship/service/schema/function/endpoint. This works but
is verbose: a modest e-commerce example takes ~1100 lines of Python calling
~40 REST endpoints to describe 6 entities and 3 services.

The goal of this change is a much terser entry point: a single YAML file
describing an ERD (entities, fields, relationships) plus a handful of
config blocks (database, auth, RBAC), fed through a CLI that generates:

1. SQLAlchemy data models
2. Generic repository (CRUD) functions
3. A CRUD REST API surface per entity
4. An optional, fully generated JWT auth service
5. RBAC enforcement on generated endpoints
6. A pre-generation visualization of the ERD

The CLI reports where generated code lands in the workspace so it can be
copied into a real project.

## 2. Scope boundary

- `backend/` (schemas, `CodeGenerator`, Jinja2 templates) is repurposed as
  the **generation engine**, used as a library. It keeps working exactly as
  today for anyone still calling it directly.
- The REST API in `backend/api/routes.py` and the granular per-model/service
  Pydantic schemas remain in the repo (not deleted) but are no longer the
  primary interface. No new work is done to keep them in sync with new CLI
  features.
- `frontend/` and `mcp_server/` are untouched — out of scope for this change,
  left as unmaintained but present.
- New code lives under a new `backend/cli/` (CLI commands) and `backend/erd/`
  (YAML parsing, validation, and translation into the existing engine's
  data structures) — plus new Jinja2 templates under `backend/templates/Python/`.
- Generated projects continue to use **sync SQLAlchemy** (`Session`,
  `db.query(...)`), matching what the existing templates actually implement
  today (the `use_async` config flag exists but was never wired up — this
  spec does not change that).
- `DatabaseType` for the CLI is restricted to `postgresql | mysql | sqlite`.
  `mongodb`/`redis` remain in the shared enum (used elsewhere) but the CLI
  rejects them at validation time with a clear error, since the generator
  only ever produces SQLAlchemy declarative models.

## 3. YAML ERD schema

Top-level file (conventionally `erd.yml`), parsed into a new Pydantic model
`ERDConfig` (in `backend/erd/schema.py`):

```yaml
project:
  name: ShopHub
  version: "1.0.0"
  description: "A modern e-commerce platform"

database:
  type: postgresql              # postgresql | mysql | sqlite
  host: localhost
  database_name: shophub_db
  pool_size: 10
  # remaining fields match today's DatabaseConfig (username, use_env_vars, echo, ...)

auth:
  enabled: true
  jwt:
    secret_env_var: JWT_SECRET
    algorithm: HS256
    expiration_minutes: 30

rbac:
  enabled: true
  roles: [admin, editor, viewer]
  default_permissions:            # optional, applied when an entity doesn't override
    read: [admin, editor, viewer]
    list: [admin, editor, viewer]
    create: [admin, editor]
    update: [admin, editor]
    delete: [admin]

entities:
  - name: Product
    table_name: products          # optional, defaults to snake_case(name) + 's'
    fields:
      - {name: name, type: string, max_length: 200}
      - {name: description, type: text, nullable: true}
      - {name: price, type: float}
      - {name: sku, type: string, unique: true}
    relationships:
      - name: category_products
        cardinality: many-to-one   # one-to-many | many-to-one | one-to-one | many-to-many
        target: Category
        foreign_key:
          column: category_id
          references: categories.id
          nullable: false
          ondelete: CASCADE
    endpoints:
      enabled: [create, list, read, update, delete]   # any subset; default: all
      base_path: /products         # optional, defaults to /{kebab-plural(name)}
      tags: [products]             # optional, defaults to [snake_case(name)]
      rbac:                        # optional, overrides rbac.default_permissions for this entity
        create: [admin]
        update: [admin, editor]
        delete: [admin]

  - name: Category
    fields:
      - {name: name, type: string, unique: true}
      - {name: slug, type: string, unique: true}

  - name: User                     # optional: merge extra fields into the auto-injected User entity
    fields:
      - {name: display_name, type: string, nullable: true}
```

### Field/relationship shape

Reuses the existing `ModelField`, `RelationshipSpec`, `ForeignKeySpec`,
`Cardinality` shapes from `backend/schemas/data.py` — no schema changes
needed there. `ERDConfig.entities[].relationships[]` is translated into the
existing `RelationshipSpec` list expected by `CodeGenerator` (source/target
sides, association tables for many-to-many, etc.) during the YAML → engine
translation step, so entity authors write a flatter, single-sided
relationship declaration and the translator fills in both sides.

### Auth-injected `User` entity

When `auth.enabled: true`, the translator injects a `User` entity with:
`id` (PK), `email` (unique), `password_hash`, `roles` (JSON list of role
names, only present if `rbac.enabled`), `is_active`, `created_at`,
`updated_at`. If the YAML declares its own `entities[].name: User` block,
its `fields` are merged in (appended) rather than replacing the built-in
ones; a name collision with a reserved field (`id`, `password_hash`, etc.)
is a validation error.

### RBAC resolution

For each entity + CRUD action (`create`/`list`/`read`/`update`/`delete`):
1. If the entity's `endpoints.rbac` sets that action, use it.
2. Else if `rbac.default_permissions` sets it, use it.
3. Else if `rbac.enabled: true`, default to "any authenticated user" (all
   declared roles).
4. Else (`rbac.enabled: false` or `auth.enabled: false`), the action is
   public — no dependency applied.

## 4. Generation pipeline

`backend/erd/` responsibilities:
- `schema.py` — `ERDConfig` and nested Pydantic models.
- `loader.py` — read YAML, parse into `ERDConfig`, raise
  `ERDValidationError` with human-readable messages (entity/field name,
  what's wrong) on: unknown relationship targets, duplicate entity/field
  names, reserved `User` field collisions, disallowed `database.type`,
  RBAC role references not present in `rbac.roles`.
- `translate.py` — `ERDConfig` → the existing engine's `ProjectState`-shaped
  dict (`data_models`, `relationships`, `services` list containing one
  auto-built "CRUD service" per entity plus an "AuthService" when enabled,
  `database_config`, `security_config`). This is the seam between the new
  YAML world and the existing `CodeGenerator`.

`backend/cli/` responsibilities (Typer-based, entry point `backstudio`):

- `backstudio validate <erd.yml>`
  Loads + validates only. Exit code 0/1. Prints a summary (entity count,
  relationship count, warnings) or the validation errors.

- `backstudio visualize <erd.yml> [-o diagram.html]`
  Loads + validates, then renders a self-contained HTML file with a Mermaid
  `erDiagram` (entities/fields/relationships, PK/FK markers) built from the
  parsed `ERDConfig` — no dependency on the FastAPI/React app. Opens it in
  the default browser (`webbrowser.open`). Default output path:
  `<erd-file-stem>-diagram.html` next to the source YAML unless `-o` given.

- `backstudio generate <erd.yml> [--output ./workspace] [--force]`
  Loads + validates, translates, calls `CodeGenerator.generate_project(...)`
  (existing engine, unchanged), then:
  - Runs the new templates (CRUD schemas/routes, auth service, RBAC
    dependency, Alembic scaffolding — see §5) as part of that same
    `_generate_fastapi_project` pass.
  - Attempts `alembic revision --autogenerate -m "initial"` against the
    generated project. Best-effort: if the DB isn't reachable or the
    command fails, prints a warning and continues (does not fail the
    command) — `alembic.ini`/`env.py` scaffolding is still written either
    way, and the user can run migration generation themselves later.
  - Prints the final output path prominently, e.g.:
    ```
    Generated at: workspace/ShopHub/codebase
    Copy this directory into your project.
    ```

## 5. New templates / generation logic

Added under `backend/templates/Python/`:

- `service/crud_schemas.py.jinja` — per-entity `{Entity}Create`,
  `{Entity}Update`, `{Entity}Response` Pydantic schemas derived directly
  from `fields` (required/optional per `nullable`, types mapped the same
  way `models.py.jinja` maps them).
- `service/crud_routes.py.jinja` — per-entity CRUD routes wired to the
  existing generic `repo.py` functions (`create_x`, `get_x_by_id`,
  `get_all_xs`, `update_x`, `delete_x` — already generated, unchanged).
  Honors `endpoints.enabled`, `base_path`, `tags`, and applies
  `Depends(require_roles(...))` per action per the RBAC resolution in §3.
- `auth/models.py.jinja`, `auth/service.py.jinja`, `auth/schemas.py.jinja`,
  `auth/routes.py.jinja` — the `User` model (merged into the main
  `database/models.py` output, not a separate table file), password
  hashing (passlib/bcrypt), `register`/`login`/`refresh`/`me` functions and
  routes, JWT issuing/verification using `security_config`.
- `rbac/dependency.py.jinja` — one `require_roles(*roles: str)` dependency
  factory generated once per project (only when `rbac.enabled`), used by
  `crud_routes.py.jinja` and any auth-protected routes.
- `alembic/alembic.ini.jinja`, `alembic/env.py.jinja` — wired to the
  generated `Base.metadata` and `database_config`; `alembic/versions/`
  created empty (populated by the best-effort autogenerate step above, or
  manually by the user).

`backend/services/code_generator.py` gains a new branch in
`_generate_fastapi_project` that, when the translated state marks an entity
as "CRUD-generated" (as opposed to a hand-authored service), uses the new
templates above instead of the existing `service/service.py.jinja` /
`schemas.py.jinja` / `routes.py.jinja` trio. Hand-authored services (for
projects still using the old REST/API path) are unaffected.

## 6. CLI packaging

- New `[project.scripts]` entry in `pyproject.toml`: `backstudio = "backend.cli.main:app"`.
- New dependencies: `typer`, `pyyaml`, `passlib[bcrypt]`, `python-jose` (or
  `pyjwt`) for the auth service, `alembic`.
- `backend/cli/main.py` — Typer app wiring the three commands above.

## 7. Error handling

- YAML parse errors (malformed YAML) surface the underlying `yaml.YAMLError`
  location (line/column) directly.
- `ERDValidationError` messages always name the offending entity/field/role
  and the rule violated (e.g. `Entity 'Order': relationship target 'Custmer' not found among declared entities`).
- `generate` refuses to overwrite an existing output directory unless
  `--force`, matching current `CodeGenerator.generate_project` behavior.
- Alembic autogenerate failure is a warning, not an error (see §4).

## 8. Testing

- `backend/erd/` unit tests: valid/invalid YAML fixtures under
  `backend/tests/fixtures/erd/`, covering the validation rules in §3/§7.
- Generation smoke tests: a small fixture ERD (2-3 entities, one
  relationship, auth + RBAC enabled) generated into a temp dir; assert
  expected files exist and parse cleanly (`ast.parse`), and that specific
  expected symbols appear (e.g. `require_roles` import in a protected
  route's file).
- One larger end-to-end fixture approximating the existing ShopHub example,
  to catch regressions across relationships + auth + RBAC together.
- CLI tests via Typer's `CliRunner` for `validate`/`visualize`/`generate`
  exit codes and key output strings (including the "Generated at: ..."
  message).

## 9. Out of scope (explicitly deferred)

- Fully custom hand-declared endpoints via YAML (beyond enable/disable +
  path/tag/RBAC overrides on the auto-CRUD).
- Per-field RBAC visibility.
- Non-JWT auth strategies (session/OAuth2/API key) — `AuthStrategy` enum
  stays as-is but the CLI only implements `jwt`.
- MongoDB/Redis-backed generation.
- Async SQLAlchemy.
- Deleting/repurposing `frontend/` or `mcp_server/`.
