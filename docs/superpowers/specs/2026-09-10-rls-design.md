# Row-Level Access Control (RLS) — Design Spec

Date: 2026-09-10
Status: Approved for implementation planning
Extends: `docs/superpowers/specs/2026-09-08-erd-cli-design.md`,
`docs/superpowers/specs/2026-09-09-modular-services-design.md`,
`docs/superpowers/specs/2026-09-09-async-support-design.md` (built directly
against the async shape that spec produces — see §4 for how each mechanism
branches per `database.async_mode`, mirroring that spec's established
patterns rather than inventing new ones).

## 1. Motivation

Generated projects today have two access-control mechanisms, both
endpoint-level: authentication (`auth.enabled`, JWT-based, "who are you")
and RBAC (`rbac.enabled`, "does your role allow this action on this
entity"). Neither answers "does this specific *row* belong to you." A
`customer` role with `read` permission on `Order` can read every order in
the table, not just their own — RBAC gates the action, not the rows the
action touches.

This spec adds row-level filtering: entities can declare that their rows
are scoped to an owner (a `User`, a `Tenant`, an `Agency` — any entity), and
every generated CRUD operation on that entity is automatically filtered to
rows the current caller owns, with an explicit opt-in for roles that bypass
the filter entirely (e.g. `admin`).

## 2. Scope boundary

**In scope:**
- Ownership-only filtering: a row is visible/mutable by the caller who owns
  it (or a caller with a declared bypass role). No arbitrary predicates
  (`status == 'published' OR ...`) — that is a materially larger feature
  and explicitly out of scope for this pass (see §8).
- Direct ownership: an entity declares one of its many-to-one relationships
  as the ownership column (`owner: true`).
- Transitive (cascaded) ownership: an entity related to an owned entity
  only indirectly (e.g. `OrderItem` → `Order` → owner) can opt in to
  inheriting that ownership (`cascades_ownership: true`), to arbitrary
  depth.
- Two identity sources for "who is the current owner": the JWT-authenticated
  `User` (reuses the existing auth module), or a trusted request header —
  for services that scope rows to an entity (e.g. `Tenant`) without running
  their own login flow.
- An opt-in, per-entity list of roles that bypass row filtering entirely
  (requires RBAC, which requires auth — see §3).
- Full propagation through both the sync and async generated stacks (repo,
  service, routes, schemas), per `database.async_mode`.

**Out of scope (see §8 for the complete list):** arbitrary declarative
predicates, field/column-level visibility, ownership via one-to-one or
many-to-many relationships, audit logging of denied access.

## 3. ERD schema additions

A relationship gains two new, mutually exclusive, optional boolean flags —
valid only on **many-to-one** relationships (an entity can have exactly one
owner; one-to-many/many-to-many don't resolve to a single owning row):

```yaml
entities:
  - name: Order
    relationships:
      - name: user
        cardinality: many-to-one
        target: User            # or Tenant, Agency, any entity
        owner: true              # this FK IS the ownership column (root)

  - name: OrderItem
    relationships:
      - name: order
        cardinality: many-to-one
        target: Order
        cascades_ownership: true # ownership flows from Order, transitively
```

An entity with `owner: true` on one of its relationships must also declare
an entity-level `rls:` block:

```yaml
entities:
  - name: Order
    rls:
      bypass_roles: [admin]      # optional; requires rbac.enabled
      identity_source:
        type: auth_user          # "auth_user" | "header"
        # type: header
        # header_name: X-Tenant-Id
```

A `cascades_ownership: true` entity does **not** declare its own `rls:`
block — it inherits the resolved root's `identity_source` and
`bypass_roles` (§5).

### 3.1 Validation rules (enforced at ERD load time, alongside the existing
checks in `backend/erd/loader.py`)

1. At most one `owner: true` relationship per entity, and at most one
   `cascades_ownership: true` relationship per entity. An entity may have
   neither, or exactly one of the two — never both.
2. `owner: true` and `cascades_ownership: true` are valid only on
   many-to-one relationships.
3. Any entity carrying `owner: true` must declare an `rls:` block with
   `identity_source`.
4. `identity_source.type: auth_user` requires `auth.enabled: true` **and**
   the `owner: true` relationship's `target` to be exactly `User` (the
   reserved auth entity name — see `backend/erd/translate.py:251`).
5. `identity_source.type: header` requires `header_name` to be set.
   Independent of `auth.enabled`; `target` can be any entity, `User`
   included.
6. `header_name` must not case-insensitively equal `Authorization` (the one
   header this codebase's generated auth already relies on, via the
   `Bearer <token>` scheme in `oauth2_scheme`/`get_current_user`).
7. `rls.bypass_roles`, if present, requires `rbac.enabled: true`. Per the
   existing constraint at `backend/erd/loader.py:46-48`
   (`rbac.enabled requires auth.enabled: true`), this transitively means
   `bypass_roles` is only reachable through the `auth_user` identity
   source — a `header`-sourced entity can never declare `bypass_roles`.
   Every role listed must be a declared role in `rbac.roles`.
8. `cascades_ownership: true` chains must terminate at an `owner: true`
   entity with no cycles, and every entity must resolve to at most one
   ownership path (ambiguous multi-path chains are rejected).

## 4. Mechanics

Each piece below branches on `database.async_mode` using the same
established patterns from the async-support spec: surgical inline tokens
(`{{ 'await ' if is_async }}`) in files that interleave real business logic
(`repo.py.jinja`'s query-building, `module_service.py.jinja`,
`module_routes.py.jinja`), consistent with how those files already handle
the sync/async split.

### 4.1 Ownership resolution (translate-time, `backend/erd/translate.py`)

For every entity, resolve one of: *unowned*, *root-owned* (`owner: true`
present), or *cascade-owned* (reachable via a `cascades_ownership: true`
chain to a root-owned entity). For a cascade-owned entity, resolution
produces:
- The ordered list of join hops from this entity up to the root (each hop:
  child entity, FK column, parent entity, parent PK column).
- The root entity's owner FK column name.
- The root's `identity_source` and `bypass_roles`, inherited unchanged.

This resolved structure is what `repo.py.jinja`, `module_service.py.jinja`,
`module_routes.py.jinja`, and `module_schemas.py.jinja` consume; none of
them re-derive it.

### 4.2 Repo layer (`repo.py.jinja`)

- **Root-owned entity**: `get_<entity>_by_id` and `get_all_<entities>` gain
  an `owner_id: Optional[int] = None` parameter. `None` means unfiltered
  (bypass); otherwise add `.where(Model.<owner_fk_column> == owner_id)` —
  identical mechanism to the existing `owned_relationships` filter already
  generated for client-supplied FK query params, just server-sourced
  instead of client-supplied.
- **Cascade-owned entity**: same `owner_id` parameter and semantics, but
  the `WHERE` is preceded by one `.join(...)` per resolved hop, ending on
  the root's owner FK column — e.g. for `OrderItem → Order → owner`:
  `select(OrderItem).join(Order, OrderItem.order_id == Order.id).where(Order.user_id == owner_id)`.
  Each additional hop in a deeper chain adds one more `.join(...)`.
- `update_<entity>` / `delete_<entity>` need **no direct changes** on
  either kind — both already call `get_<entity>_by_id` first, so threading
  `owner_id` through automatically makes a non-owner's update/delete hit
  the exact same "row not found" path as a bad id.
- This composes with an entity's existing `owned_relationships` filters
  (client-supplied query-param FKs) — they are orthogonal `WHERE` clauses
  on the same query.

### 4.3 Service layer (`module_service.py.jinja`)

- Threads `owner_id` through to the repo call on every filtered operation.
- **Create, root-owned entity**: injects the owner value into the payload
  dict from the resolved `owner_id` before calling `repo.create_<entity>`
  — the client never supplies it (§4.5).
- **Create/update, cascade-owned entity, when the cascade-linking FK is
  being set or changed**: reuses the *parent's own* `owner_id`-filtered
  `get_<parent>_by_id` call — already present as this codebase's existing
  FK-existence validation — passing `owner_id` through. A parent that
  exists but isn't owned by the caller now fails that same existing check,
  raising the same `ValueError` → 400 as a genuinely nonexistent parent
  (§6). This recursively enforces the whole chain for free: validating the
  immediate parent's ownership already validated *its* parent, and so on,
  because the parent's own `get_by_id` is itself ownership-filtered if the
  parent is itself cascade- or root-owned.

### 4.4 Route layer (`module_routes.py.jinja`)

Resolves the `owner_id` value passed down to the service, based on the
entity's (or, for cascaded entities, the inherited root's)
`identity_source`:

- **`auth_user`**: reuse `Depends(require_roles(...))` when RBAC already
  gates that action on that entity (it already returns the authenticated
  `User`); otherwise add a bare `Depends(get_current_user)`. Then
  `owner_id = None if current_user's roles intersect bypass_roles else current_user.id`.
- **`header`**: a required FastAPI `Header(..., alias="<header_name>")`
  parameter — FastAPI validates presence natively (422 if missing, no
  custom code). `owner_id` is that value directly; no bypass path exists
  for header-sourced entities (§3.1 rule 7).

### 4.5 Schema layer (`module_schemas.py.jinja`)

For a root-owned entity, the owner FK field is dropped from
`<Entity>Create` entirely — the server always sets it from the resolved
`owner_id`, never from client input. Cascade-owned entities are unaffected
here (their linking FK, e.g. `order_id` on `OrderItem`, stays a normal,
client-supplied field — subject to the ownership-aware FK validation in
§4.3, not schema-level omission).

## 5. RLS config inheritance for cascaded entities

A cascade-owned entity has no `rls:` block of its own. Its generated
routes/service/repo code uses the **resolved root's** `identity_source` and
`bypass_roles` (§4.1) — e.g. if `Order` bypasses `admin`, `OrderItem` and
`OrderLineDiscount` (if cascade-owned through `Order`) also bypass `admin`,
with no separate declaration required.

## 6. Error handling & edge cases

- Non-owner access to a single row (`GET`/`PUT`/`DELETE`) — root-owned or
  cascade-owned — returns **404**, indistinguishable from the row not
  existing, consistent with not leaking cross-tenant existence information.
- A cascade-owned `create`/`update` whose parent-linking FK references a
  row that exists but isn't owned by the caller gets the **same 400** as a
  genuinely nonexistent FK (§4.3) — same reasoning: don't leak existence.
- A missing required identity header is a native FastAPI 422 — no custom
  error handling needed.
- `list` endpoints for a filtered entity return only owned (or, for a
  bypass-role caller, all) rows — no error case, just a smaller result set.

## 7. Testing plan

Concrete test code belongs in the implementation plan, not this spec.
Coverage this plan must include:
- Direct-ownership filtering on `list`/`get`/`update`/`delete`, over real
  HTTP against a real generated app, for both sync and async projects.
- Cascaded-ownership filtering at 2+ hops (mirroring the
  `OrderItem`/`OrderLineDiscount` shape), same real-HTTP style.
- `bypass_roles` genuinely bypassing filtering for a role that has it, and
  genuinely NOT bypassing for a role that doesn't.
- `header`-sourced identity end to end, including the native 422 on a
  missing header.
- `create` auto-injecting the owner value for a root-owned entity, with a
  test proving a client-supplied owner value in the payload is ignored/
  rejected by the schema, not silently accepted.
- A cascaded `create`/`update` rejecting an FK that references an unowned
  parent, asserting the same 400 shape as a nonexistent FK.
- Composition with an existing `owned_relationships` filter on the same
  entity (both filters active on one query).
- ERD-load-time validation: each rule in §3.1 gets a rejection test.
- Sync/async parity for every scenario above, per the established pattern
  from the async-support plan (paired fixtures, or a single fixture
  generated both ways).

## 8. Non-goals

- Arbitrary declarative predicates per entity/action (e.g.
  `status == 'published' OR owner_id == user.id`) — a materially larger
  feature; ownership-only for this pass.
- Field/column-level visibility restrictions (this spec governs which
  *rows* are reachable, not which *fields* within a reachable row are
  visible).
- Ownership via one-to-one or many-to-many relationships.
- Audit logging of denied (404'd) access attempts.
- Runtime-configurable bypass beyond declared roles (e.g. a per-request
  override header).
- A second, richer identity-source mechanism beyond JWT-`auth_user` and
  trusted-header (e.g. API-key-to-tenant mapping) — `header` already covers
  the "no built-in login" case this spec set out to support; anything
  fancier is a separate feature.
