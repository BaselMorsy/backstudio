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

- [ ] Missing blank lines between entities in generated `routes.py` (cosmetic).
- [ ] Auth service uses a different DI pattern (module-level singleton call)
  than regular modules (`Depends(get_X_service)`) — inconsistent, not wrong.
- [ ] Validation error messages could suggest the YAML fix inline.
- [ ] Unused `Any` import + naive pluralization (`list_categorys`) —
  pre-existing, not introduced by modular-services.
- [ ] A user-declared `User` entity combined with `auth.enabled: false` is
  silently excluded with no clear error message.

## Minor findings — original ERD-CLI final review

- [ ] Generated CRUD schemas can't express relationships. Confirmed this
  matches the original spec's documented scope — not a bug, a known
  limitation worth revisiting if relationship-aware schemas become valuable.
- [ ] No test coverage (though manually confirmed working) for: all-actions
  -disabled entity, zero-entity ERD, auth-enabled/rbac-disabled generation,
  one-to-one relationship generation specifically, custom `table_name`,
  `base_path`/`tags` overrides.

## Documentation

- [ ] `backend/templates/Python/README.md.jinja` (the generated project's own
  README template) is still written for the old REST-API-driven flow —
  renders empty "Services" / "Implementation Guide" sections since
  `project.services` is always `[]` in the CLI pipeline. Only the actively
  -misleading "your service implementations are preserved" line was patched
  during the modular-services fix wave; the rest was never rewritten for the
  `modules/` structure.
