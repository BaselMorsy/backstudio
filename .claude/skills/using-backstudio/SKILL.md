---
name: using-backstudio
description: Use when building a new FastAPI backend service, or adding entities, auth, RBAC, or row-level security to one, in a repo that uses or could use backstudio to generate it from an ERD YAML file.
---

# Using Backstudio

## Overview

Backstudio generates a FastAPI backend (SQLAlchemy models, Pydantic schemas, routes, auth, RBAC, RLS, Alembic) from one ERD YAML file. Workflow: design the ERD -> validate -> generate. Never guess YAML syntax from memory or an old example file — the schema evolves; always check the live grammar first.

## Workflow

1. `backstudio grammar` (no args) — lists every top-level key and topic.
2. `backstudio grammar <topic>` **before** writing any block for that topic: project, database, auth, rbac, entities, fields, relationships, endpoints, rls, services. It's generated from the live schema (`app/erd/schema.py`), so it's more reliable than recalling syntax or copying an old example.
3. Write/edit the ERD YAML.
4. `uv run backstudio validate <file>` — fix errors, re-run.
5. `uv run backstudio generate <file> -o <dir>` — fix errors, re-run.
6. Optional: `uv run backstudio visualize <file>` to sanity-check the ERD diagram before generating.

## Key decisions

| Need | Choice |
|---|---|
| This service owns user accounts/passwords/login | `auth.mode: builtin` |
| This service only verifies JWTs issued elsewhere, no local accounts | `auth.mode: external` — then no `User` entity may be declared; identity is a `Principal` built from the verified token's claims |
| Row ownership = the logged-in builtin User | `rls.identity_source.type: auth_user` |
| Row ownership = a request header value, no auth needed | `rls.identity_source.type: header` |
| Row ownership = a claim on an externally-verified JWT | `rls.identity_source.type: jwt_claim` (requires `auth.mode: external`) |
| Owner entity's match column isn't its primary key (e.g. a UUID claim vs. an int PK) | set `rls.owner_match_field` to that column — see gotcha #2 below |
| Exact-to-the-cent money | `type: decimal` with `precision`/`scale`; pick `database.type: postgresql`/`mysql` for the exactness guarantee (SQLite stores decimal as REAL) |
| Fixed set of string values | `type: enum`, `values: [...]` (UPPER_SNAKE, no Python-keyword collisions) |

## Two gotchas worth knowing by heart (also now in `backstudio grammar rbac`/`rls`, and in `docs-site/features/rbac.md`/`rls.md`)

1. **RBAC: no override ≠ "any authenticated user."** With `rbac.enabled: true`, an action with no per-entity `endpoints.rbac` override and no matching `rbac.default_permissions` entry resolves to **every declared role**, not "anyone logged in." To open an action to any authenticated caller, override it with an **explicit empty list**: `endpoints.rbac.<action>: []`.
2. **Owner-match type coercion defaults to `int`.** When `rls.owner_match_field` is unset, generated code assumes the owner's primary key is an int. If the RLS claim should match a non-integer column (e.g. a UUID), you must set `owner_match_field` to that column explicitly — otherwise every request 403s (the claim never parses as an int).

## Common mistakes

- `owner: true` on a relationship with no `rls:` block (required whenever any relationship has `owner: true`).
- Declaring a `User` entity under `auth.mode: external` (rejected — identity comes from `Principal`, not a `User` row).
- `rbac.enabled: true` without `admin` in `rbac.roles`, or without `auth.enabled: true`.
- An entity not assigned to exactly one `services[].entities` group.
- `owner_match_field` target missing `unique: true`.
- HS256/384/512 under `auth.mode: external` (rejected — asymmetric algorithms only; this mode never holds a signing secret).
- An entity with no `primary_key: true` field, or more than one (rejected at `validate` time — every entity needs exactly one, except `User`, whose PK is always the auto-injected `id`).

## Reference

Full documentation: `docs-site/` (`uv run mkdocs serve`) — `erd-reference/` and `features/` have the complete prose. This skill is the fast path for the decisions above; it is not a substitute for reading `backstudio grammar <topic>` output for exact field names.
