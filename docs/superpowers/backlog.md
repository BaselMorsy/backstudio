# Backlog — parked items

Tracking doc for work identified but deliberately deferred during the ERD-CLI
and modular-services builds. Each item below should be checked off (or moved
into a proper spec/plan under `docs/superpowers/`) as it's addressed, not
deleted, so we keep a record of what was considered and when.

## Architectural (need their own brainstorm → spec → plan cycle)

- [x] **Relationships are invisible to the generated CRUD API.** Promoted
  2026-09-09 from a "minor finding" after actually generating and
  runtime-testing three patterns (many-to-one, many-to-many, and the
  "association object" junction-entity pattern) — this is a real usability
  gap, not just a documented scope limitation.
  - **Confirmed working today, at the DB/model layer, for all three
    patterns** (verified with live in-memory SQLite round-trips, not just
    `ast.parse`):
    - many-to-one/one-to-one: FK column + `relationship()` render correctly.
    - many-to-many (`cardinality: many-to-many`): auto-generates a bare
      SQLAlchemy Core `Table` (not a mapped entity) used as `secondary=`;
      `post.tags.append(tag)` etc. works.
    - **The junction-table pattern the user asked about** — declaring 3
      ordinary entities (e.g. `Student`, `Course`, `Enrollment` with its own
      `grade` field plus two `many-to-one` relationships) — works exactly
      like it would hand-written in SQLAlchemy (the "association object"
      pattern). `Enrollment(grade='A', student=s, course=c)` round-trips
      correctly. This is the right way to model a many-to-many that needs
      extra fields on the join (timestamps, a role, quantity, etc.) — plain
      `cardinality: many-to-many` can't carry extra fields, since a bare
      `secondary=` Core `Table` isn't a mapped class.
  - **The actual gap:** `translate.py`'s `crud_entities` (what
    `module_schemas.py.jinja`/`module_routes.py.jinja` render from) only
    carries `entity.fields`, never `entity.relationships`. So every
    generated `Create`/`Update`/`Response` schema — and therefore every
    route, since routes just pass `payload.model_dump()` through — is
    blind to relationships entirely, regardless of cardinality. Concretely:
    you cannot set a `Post`'s `category` through the API, you cannot create
    an `Enrollment` linked to a `Student`/`Course` through the API (no
    `student_id`/`course_id` in `EnrollmentCreate`), and a many-to-many's
    `tags`/`posts` never appear in any response. The DB layer is fully
    wired; the generated HTTP API cannot touch any of it.
  - **Known workaround** (verified working, no generator change needed):
    manually re-declare the FK column as an ordinary field on the owning
    entity (e.g. add `{name: student_id, type: integer}` to `Enrollment`'s
    `fields:`, matching the relationship's auto-derived FK column name).
    `models.py.jinja` already deduplicates this correctly (skips the plain
    `Column()` when a relationship's FK column has the same name), and
    since `crud_entities` fields = `entity.fields` verbatim, the FK becomes
    a normal settable/readable schema field. Only gives the FK id, not
    nested objects or many-to-many list fields, but makes the
    association-object pattern usable via the API today.
  - **Design direction for the real fix** (not committed to): likely
    auto-add `<rel>_id` fields to `Create`/`Update` for every
    many-to-one/one-to-one relationship an entity owns (so the workaround
    isn't needed), and consider optional nested `Response` fields for the
    read side. Needs a real design pass — how to avoid N+1 queries on read,
    and whether many-to-many collections belong in the base entity schema
    or a separate sub-resource endpoint (e.g. `POST /posts/{id}/tags`).
  Fixed 2026-09-09: designed and implemented per
  `docs/superpowers/specs/2026-09-09-relationship-crud-exposure-design.md`
  and `docs/superpowers/plans/2026-09-09-relationship-crud-exposure.md`.
  `backend/erd/translate.py` now derives `owned_relationships` (every
  many-to-one/one-to-one, plus one-to-many from the FK-owning side) and
  `many_to_many_relationships` per entity. Four templates consume them:
  `module_schemas.py.jinja` adds `<rel>_id` fields to `Create`/`Update`/
  `Response` for owned relationships and a read-only `<target>_ids: List[int]`
  field (via a `model_validator`) to `Response` for many-to-many;
  `repo.py.jinja` adds an optional FK-filter kwarg to `get_all_<plural>` and
  uses `selectinload` for many-to-many reads to avoid N+1 queries;
  `module_service.py.jinja` validates a given FK id exists before
  create/update (raises `ValueError` otherwise) and threads the filter
  through `list_<x>`; `module_routes.py.jinja` returns HTTP 400 on that
  `ValueError` and exposes the FK filter as an optional query param (e.g.
  `GET /products?category_id=5`). You can now set/validate FKs and read
  many-to-many id lists through the generated HTTP API — none of that was
  possible before. Still explicitly out of scope: many-to-many writes
  (`tag_ids` stays read-only), nested full-object responses (e.g.
  `category: CategoryResponse`), and nested one-to-many collections (use the
  `?category_id=` filter instead). Real HTTP+DB round-trip tests added in
  `backend/tests/test_generated_project_runtime.py`; full suite 96 passed,
  no regressions.

- [ ] **Row-level access control (RLS).** RBAC (role → action) already
  exists; RLS (does this user own *this* row) does not. Flagged by the user
  as "extremely important." To be designed after/alongside async support,
  since both touch the repo/service call chain.
- [ ] **Async support.** Repo functions and API handlers are sync-only today,
  deliberately deferred during the modular-services restructuring. Needs its
  own design pass — whether repo functions become async too, or only the
  route/service layer.
- [ ] **Spec 2 — Auth service expansion.** Agreed scope, never yet written as
  a formal spec:
  - Admin user management: `list_users` / `get_user` / `set_user_roles` /
    `deactivate_user` / `reactivate_user`, RBAC-gated to admin, only
    generated when `rbac.enabled: true`, no hard delete.
  - Registration gating: email-verification and admin-approval modes
    (invite-only deferred further, no concrete design yet).
  - Forgot/reset password: dev-mode `send_email()` stub, generic response
    on request to avoid email enumeration.

## Minor findings — modular-services final review

- [x] Missing blank lines between entities in generated `routes.py` (cosmetic).
  Fixed 2026-09-09: `module_routes.py.jinja` now emits a blank line after each
  entity's last route (matching the spacing already used between actions
  within one entity), verified against the rendered blog example.
- [x] Auth service uses a different DI pattern (module-level singleton call)
  than regular modules (`Depends(get_X_service)`) — inconsistent, not wrong.
  Fixed 2026-09-09: `/register`, `/login`, `/refresh` now take
  `service: AuthService = Depends(get_..._service)` like every other module's
  routes. `/me` (and `rbac.py`'s `require_roles`) keep the module-level
  `_service = get_..._service()` singleton — unavoidable, since `Depends()`
  needs a bound method at route-definition time, not per-request. Verified
  via the real HTTP round-trip test in `test_generated_project_runtime.py`.
- [x] Validation error messages could suggest the YAML fix inline.
  Fixed 2026-09-09: added actionable suggestions to the `loader.py` messages
  that lacked them — reserved-field collisions, unknown relationship targets
  (now lists valid targets), unknown RBAC roles (now lists declared roles),
  and unassigned/multiply-assigned entities (now names the YAML fix). Schema
  -level messages (`schema.py`) already had suggestions and were left as-is.
- [x] Unused `Any` import + naive pluralization (`list_categorys`) —
  pre-existing, not introduced by modular-services.
  Fixed 2026-09-09: added `plural_snake` (the same `_pluralize()` used for
  `crud_entities`) to `translate.py`'s `data_models` entries too, and swapped
  every naive `{{ entity.snake_name }}s` / `{{ model.name|snake_case }}s` in
  `repo.py.jinja`, `module_service.py.jinja`, `module_routes.py.jinja` for it
  (`list_categories`/`get_all_categories`, not `list_categorys`). The `Any`
  import in `module_schemas.py.jinja` is now conditional on the module
  actually containing a `json`-typed field.
- [x] A user-declared `User` entity combined with `auth.enabled: false` is
  silently excluded with no clear error message.
  Fixed 2026-09-09: `loader.py` now raises a clear `ERDValidationError` for
  this case ("Entity 'User' is reserved for the auto-managed auth entity...")
  instead of silently dropping the entity in `translate.py`.

## Minor findings — original ERD-CLI final review

- [x] No test coverage (though manually confirmed working) for: all-actions
  -disabled entity, zero-entity ERD, auth-enabled/rbac-disabled generation,
  one-to-one relationship generation specifically, custom `table_name`,
  `base_path`/`tags` overrides.
  Addressed 2026-09-09: zero-entity ERD turned out to already be covered
  (`test_empty_entities_rejected`/`test_missing_entities_key_rejected` in
  `test_erd_loader.py`). Added 5 new tests for the rest, with 3 new fixtures
  (`overrides.yml`, `auth_no_rbac.yml`, `one_to_one.yml`):
  `test_custom_table_name_overrides_pluralized_default`,
  `test_custom_base_path_and_tags_used_in_routes`,
  `test_all_actions_disabled_entity_gets_schemas_and_service_but_no_routes`
  (all in `test_crud_generation.py`),
  `test_auth_enabled_rbac_disabled_generates_auth_without_rbac_gating`
  (`test_rbac_generation.py`), and
  `test_one_to_one_relationship_generates_and_compiles` (`test_end_to_end.py`,
  byte-compiles the rendered project). Full suite: 78 passed.

## Documentation

- [x] `backend/templates/Python/README.md.jinja` (the generated project's own
  README template) is still written for the old REST-API-driven flow —
  renders empty "Services" / "Implementation Guide" sections since
  `project.services` is always `[]` in the CLI pipeline. Only the actively
  -misleading "your service implementations are preserved" line was patched
  during the modular-services fix wave; the rest was never rewritten for the
  `modules/` structure.
  Fixed 2026-09-09: Project Structure/Modules/Implementation Guide/Migrations
  sections now reflect `project.modules`, `auth_module_name`, `rbac_enabled`,
  and the unconditional Alembic scaffolding; old `project.services` blocks
  kept alongside (still rendered by the legacy UI flow — see the repo-cleanup
  item below, which will eventually let these be deleted outright).

## Repo cleanup — CLI-only (requested 2026-09-09, do last)

- [ ] **Strip the repo down to just the CLI tool.** The repo started as a
  UI-driven backend generator and was pivoted to an ERD-driven CLI this
  session, but the old UI-serving subsystem was never removed — it still
  exists alongside the CLI and the two share some templates/state shape
  (e.g. `README.md.jinja`'s `project.services` blocks, `code_generator.py`'s
  per-entity `services` loop). User wants no frontend, no MCP server, no
  other fluff — CLI only.
  - Candidates identified by survey (confirm final list before deleting):
    `frontend/`, `mcp_server/`, `backend/api/` (`routes.py`), `backend/main.py`
    (the old FastAPI app entrypoint serving the UI/API), `backend/services/project_service.py`
    (old UI project-state service), `setup.bat`/`setup.sh`, `start.bat`/`start.sh`,
    `stop.bat`/`stop.sh` (old UI dev-server scripts).
  - Once the old UI flow is gone, `code_generator.py`'s `state.get('services', [])`
    per-entity generation branch and the `service.py.jinja`/`schemas.py.jinja`/
    `routes.py.jinja` templates it uses become dead code too — remove them, and
    simplify `README.md.jinja` back down to only the `modules`/`auth` sections
    (the legacy `project.services` blocks added there this session can go).
  - Also sweep: root `README.md`/`RELEASE_NOTES.md` for any remaining UI-flow
    references, `pyproject.toml`/`backend/requirements.txt` for now-unused
    dependencies (e.g. anything only the FastAPI UI server needed), and any
    tests under `backend/tests/` that only exercise the old UI/API/MCP path.
  - Do this last, after the other backlog items that still assume the old
    flow's templates/state shape are settled, to avoid rebasing cleanup work
    on top of moving targets.
  - Also noticed while doing the README fix: there's no root `.gitignore` in
    this repo at all (only the `.gitignore.jinja` template for *generated*
    projects), so `backend/**/__pycache__/`, `venv/`, `workspace/` show up as
    untracked noise in every `git status`. Add one as part of this cleanup.
