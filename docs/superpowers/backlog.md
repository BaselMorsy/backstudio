# Backlog — parked items

Tracking doc for work identified but deliberately deferred during the ERD-CLI
and modular-services builds. Each item below should be checked off (or moved
into a proper spec/plan under `docs/superpowers/`) as it's addressed, not
deleted, so we keep a record of what was considered and when.

## Architectural (need their own brainstorm → spec → plan cycle)

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

- [ ] Generated CRUD schemas can't express relationships. Confirmed this
  matches the original spec's documented scope — not a bug, a known
  limitation worth revisiting if relationship-aware schemas become valuable.
- [ ] No test coverage (though manually confirmed working) for: all-actions
  -disabled entity, zero-entity ERD, auth-enabled/rbac-disabled generation,
  one-to-one relationship generation specifically, custom `table_name`,
  `base_path`/`tags` overrides.

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
