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
| Two backstudio services on the same trust boundary, no need for real issuer/verifier separation | `auth.external.verification: shared_secret` — simpler than JWKS, no key management, no published endpoint |
| Two backstudio services that genuinely need separation (different deploys, a third party you don't control) | `auth.external.verification: jwks` + `auth.jwt.algorithm: RS256`/etc. on the issuer, with `private_key_path_env_var`/`public_key_path_env_var` pointing at a key pair you generate yourself |
| Admin creates accounts directly (B2B, controlled onboarding) rather than self-registration | `auth.invite.enabled: true` (requires `rbac.enabled: true`) — the user exists with a role immediately, but can't log in until they set a password via `/accept-invite` |
| Need invite/email-verification/password-reset to actually deliver somewhere, not just print to console | `auth.webhook.url_env_var` pointing at an env var holding the URL your own email service listens on — backstudio never sends email itself |

## Two gotchas worth knowing by heart (also now in `backstudio grammar rbac`/`rls`, and in `docs-site/features/rbac.md`/`rls.md`)

1. **RBAC: no override ≠ "any authenticated user."** With `rbac.enabled: true`, an action with no per-entity `endpoints.rbac` override and no matching `rbac.default_permissions` entry resolves to **every declared role**, not "anyone logged in." To open an action to any authenticated caller, override it with an **explicit empty list**: `endpoints.rbac.<action>: []`.
2. **Owner-match type coercion defaults to `int`.** When `rls.owner_match_field` is unset, generated code assumes the owner's primary key is an int. If the RLS claim should match a non-integer column (e.g. a UUID), you must set `owner_match_field` to that column explicitly — otherwise every request 403s (the claim never parses as an int).

## Common mistakes

- `owner: true` on a relationship with no `rls:` block (required whenever any relationship has `owner: true`).
- Declaring a `User` entity under `auth.mode: external` (rejected — identity comes from `Principal`, not a `User` row).
- `rbac.enabled: true` without `admin` in `rbac.roles`, or without `auth.enabled: true`.
- An entity not assigned to exactly one `services[].entities` group.
- `owner_match_field` target missing `unique: true`.
- HS256/384/512 under `auth.mode: external` with `verification: jwks` (rejected — asymmetric algorithms only; under `verification: shared_secret` it's the reverse — only HS256/384/512 are accepted).
- An entity with no `primary_key: true` field, or more than one (rejected at `validate` time — every entity needs exactly one, except `User`, whose PK is always the auto-injected `id`).
- Two services meant to interoperate (one issuing, one verifying) where `validate` passes on both but they still 401 each other at runtime: mismatched secret *value* (same env var name ≠ same value), mismatched `kid`, or the issuer forgetting to set `auth.jwt.issuer`/`auth.jwt.audience` to match the verifier's `auth.external.issuer`/`audience` (no `iss`/`aud` claim at all fails the same as a wrong one). `validate` can never catch this — it only ever sees one ERD file at a time.
- Setting only one of `private_key_path_env_var`/`public_key_path_env_var` on an asymmetric builtin service (both are required together), or setting either one on a symmetric service (both must be unset — rejected, not silently ignored). Same for `kid` on a symmetric service and `secret_env_var` on an asymmetric one.
- A key file that parses but is the wrong family/curve for the configured algorithm (RSA key + `ES256`, P-256 key + `ES384`) — rejected at startup with a clear message, not a 500 the first time something signs with it.
- Expecting a refresh/password-reset/email-verification token to work as a bearer credential on another service — only access tokens carry `iss`/`aud`/`roles`; the others never leave the issuing service as a credential.
- `auth.invite.enabled: true` without `rbac.enabled: true` (rejected at `validate` time — an invite always assigns a role).
- Expecting `auth.webhook` delivery to turn on/off by flipping the env var at runtime — the webhook-vs-print-stub choice is baked in at **generation** time; changing it means regenerating, not just editing `.env`.
- Calling `/auth/resend-invite` for an invite that's already been accepted, expecting it to work like a no-op — it 400s ("Invite already accepted"), since silently swallowing that would hide a real "this account is already set up" mistake.
- Treating `webhook_delivered: false` in an `/auth/invite` or `/auth/resend-invite` response as a failure to create the account — the user and role already exist; only the notification did not go out (webhook down or misconfigured). Fix the webhook and call `/auth/resend-invite`.
- A `project.name` that is only dots/spaces (`.`, `..`) or otherwise cannot be a directory name — rejected at `validate` time. Path separators and characters invalid in file names are replaced with `_` in the generated folder name, so `generate` can never write or delete outside `-o <dir>`.
- Assuming generated projects run on older Pythons — they pin current dependency versions and need Python 3.11+ (3.11, 3.12 and 3.13 are tested).

## Reference

Full documentation: `docs-site/` (`uv run mkdocs serve`) — `erd-reference/` and `features/` have the complete prose. This skill is the fast path for the decisions above; it is not a substitute for reading `backstudio grammar <topic>` output for exact field names.
