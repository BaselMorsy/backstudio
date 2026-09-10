# Adding a new ERD-configurable feature

BackStudio's pipeline (see [Pipeline overview](pipeline.md)) is layered enough that adding a new
ERD-configurable feature touches a predictable, ordered set of files — each layer only knows
about the layer directly below it. This page is a concrete walkthrough of that order, grounded
in how a real feature was actually built in this codebase's own history: **auth registration
modes and configurable JWT lifetimes** (`auth.registration.mode`, `auth.jwt.*`). The row-level
security feature (`owner`/`cascades_ownership`/`rls:`) followed the identical shape and is
referenced alongside it below.

## The order, with the real commits that did it

1. **`app/erd/schema.py`** — add the new field(s) to the Pydantic model(s) that define the ERD's
   YAML shape. For registration modes, this meant adding `RegistrationSpec` (a `mode: Literal["open",
   "email_verification", "admin_approval"]`) and the configurable-duration fields on `JWTSpec`
   (`expiration_minutes`, `refresh_token_expiration_minutes`, etc.) — commit `300ec52`, "Add
   configurable JWT lifetimes and registration.mode to the ERD schema". (RLS's equivalent:
   commit `b617c59`, adding the `owner`/`cascades_ownership` bools to `RelationshipDecl` and the
   new `RLSSpec`/`RLSIdentitySource` models.) If the new field needs its own single-field
   validation (a `Literal`, a regex, an enum), add it here with a `field_validator` — this is the
   layer for validation that only needs the one field's own value.

2. **`app/erd/loader.py`** — add whatever *cross-field* validation the new feature needs to
   `_validate_semantics()` (or a dedicated helper it calls, e.g. `_validate_rls()`). This is the
   layer for rules that read more than one field, or more than one entity, at once. For
   registration modes: `auth.registration.mode: admin_approval` requires `rbac.enabled: true`
   (the approve endpoint is admin-gated) — commit `73ae5d1`. (RLS's equivalent: commit
   `42abf8a`, validating identity-source/auth requirements, bypass-role/RBAC requirements, and
   that every `cascades_ownership` chain terminates at an `owner: true` entity.) Raise
   `ERDValidationError` with a message that explains *why* the combination is invalid, not just
   that it is — this codebase's existing messages are the model to match.

3. **`app/erd/translate.py`** — wire the new field(s) into `translate()`'s output so the
   information reaches the `state` dict templates render against. For registration modes: adding
   the mode-aware `is_verified`/`is_approved` fields onto the synthetic `User` entity in
   `_build_user_entity()`, and passing `registration_mode` and the JWT durations through into
   `security_config` and the top-level `state` dict — commit `49bf618`. (RLS's equivalent:
   commit `cec6076`, adding `_resolve_rls()` to attach an `rls` dict to every model.) This is
   also where you decide the *shape* the new data takes in `state` — a new top-level key (like
   `registration_mode`), a new nested dict (like `security_config`), or a new per-model key (like
   `rls`) — driven by whether the templates that need it want it project-wide or per-entity (see
   [Template system: the two context shapes](templates.md#the-two-context-shapes)).

4. **The `.jinja` templates** — add or modify whatever templates need to branch on the new
   `state` field(s). For registration modes: `auth/schemas.py.jinja` and `auth/service.py.jinja`
   (new request/response schemas and service methods for admin approval, forgot/reset password)
   in commits `5ff44c4` and `1639a24`, then `auth/routes.py.jinja` wiring those into new
   endpoints in commit `1b7ca20`. (RLS's equivalent: `database/repo.py.jinja` gaining an
   `owner_id` parameter in commit `4affaad`, then `service/module_service.py.jinja` threading it
   through in commit `1401c5d`, then `service/module_routes.py.jinja` resolving it from the
   request in commit `42a7f4a`.) Check
   [Template system](templates.md) first for which context shape (`{'project': state}` vs.
   `{'project': state, 'module': module}`) the template you're touching actually receives —
   getting this wrong is the most common way to introduce a bug here.

5. **Tests** — add coverage that exercises the new field end-to-end: a loader-level test for the
   new validation rule (reject/accept), and a full-stack generation + HTTP round-trip test
   proving the generated code actually behaves as configured. For registration modes: commit
   `a37f688`, "Add full HTTP+DB round-trip tests for email verification, admin approval, and
   forgot/reset password". (RLS's equivalent: commit `7d162a9`, a positive-path test for a
   successful `cascades_ownership` chain, plus `d3bd514`'s async-mode RLS round-trip test.) This
   codebase generates a real project into a temp workspace and runs real HTTP requests against
   it rather than asserting on rendered template strings — match that pattern rather than
   snapshot-testing the `.jinja` output directly.

## Why this order, not another

Each layer only reads the layer immediately below it and knows nothing about the layers above —
`loader.py` doesn't know templates exist; `translate.py` doesn't know Jinja2 exists; templates
never see a raw `ERDConfig`. Working top-down (schema → loader → translate → templates → tests)
means every step compiles/validates against a shape that already exists by the time you write
it, instead of discovering a mismatch after building the last layer first.
