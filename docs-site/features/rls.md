# Row-level security (RLS)

RBAC (see [RBAC](rbac.md)) answers "may this caller `create`/`list`/`read`/`update`/`delete` on
this **entity** at all." RLS answers the question RBAC can't: "does this specific **row** belong
to this caller." A `customer` role with RBAC `read` permission on `Order` can, without RLS, read
*every* order in the table — RBAC gates the action, not which rows it touches. RLS closes that
gap with owner-based row filtering, generated into the repo/service/route/schema layers.

For the exact YAML shape (`rls.identity_source`, `rls.bypass_roles`, the `owner`/
`cascades_ownership` relationship flags) see the
[Full field reference → RLS](../erd-reference/fields.md#rls-row-level-security-rlsspec). This
page covers the generated mechanics, cross-checked against the current
`app/templates/Python/database/repo.py.jinja`, `app/templates/Python/service/module_service.py.jinja`,
and `app/templates/Python/service/module_routes.py.jinja` templates (the RLS-generating template
code is spread across these three files plus `module_schemas.py.jinja`, not a single dedicated
template) and against `docs/superpowers/specs/2026-09-10-rls-design.md`.

## Declaring ownership

An entity opts into RLS with an `owner: true` relationship plus an entity-level `rls:` block:

```yaml
entities:
  - name: Order
    relationships:
      - {name: user, cardinality: many-to-one, target: User, owner: true}
    rls:
      bypass_roles: [admin]
      identity_source:
        type: auth_user
```

A related entity that doesn't own rows directly but should still be scoped to the same owner
opts in with `cascades_ownership: true` instead, and declares **no** `rls:` block of its own — it
inherits the resolved root's `identity_source` and `bypass_roles`:

```yaml
  - name: OrderItem
    relationships:
      - {name: order, cardinality: many-to-one, target: Order, cascades_ownership: true}
```

(Both snippets are the real `app/tests/fixtures/erd/rls_async_full.yml` fixture, used by this
codebase's own generation tests.)

## How filtering is generated

### Repo layer: an `owner_id` parameter, `None` means unfiltered

Every RLS-scoped entity's `get_<entity>_by_id` and `get_all_<entities>` repo functions
(`database/repo.py.jinja`) gain an `owner_id: Optional[int] = None` parameter. When it's not
`None`, a `WHERE` clause is added filtering to that owner's rows:

```python
if owner_id is not None:
    query = query.filter({{ model.rls.root_model }}.{{ model.rls.owner_fk_column }} == owner_id)
```

`update_<entity>`/`delete_<entity>` need no separate filtering logic — both already call
`get_<entity>_by_id` first, so threading `owner_id` through makes a non-owner's update/delete hit
the exact same "row not found" path as a bad id (404, not 403 — see
[Error handling](#error-handling), below).

### Cascade-ownership: joins up the chain to the root's owner column

For a `cascades_ownership: true` entity (e.g. `OrderItem`), the same `owner_id` parameter and
`None`-means-unfiltered semantics apply, but the `WHERE` is preceded by one `.join(...)` per
resolved hop up to the root:

```python
if owner_id is not None:
    query = query.join(Order, OrderItem.order_id == Order.id)
    query = query.filter(Order.user_id == owner_id)
```

A deeper chain (e.g. `OrderLineDiscount → OrderItem → Order → owner`) adds one `.join(...)` per
additional hop — resolved once at generation time from the declared `cascades_ownership` chain,
not re-derived per request.

### Route layer: resolving `owner_id`, including the bypass-role and public-read fixes

`module_routes.py.jinja` resolves `owner_id` differently depending on `identity_source.type`,
whether `bypass_roles` is set, and — for `list`/`read` only — `read_scope`:

- **`auth_user`**: resolved from the JWT-authenticated caller's roles. A bypass role gets
  `owner_id = None` (unfiltered):

  ```python
  owner_id = None if set(current_user.roles or []).intersection(entity.rls.bypass_roles) else current_user.id
  ```

- **`header`, no `bypass_roles`**: `owner_id` is the required `Header(..., alias="<header_name>")`
  value directly, exactly as before.

- **`header`, with `bypass_roles`**: the `Header` param becomes *optional* (FastAPI can't make one
  param's requiredness depend on which caller is calling), and the route resolves `owner_id`
  itself — a bypass-role caller may omit the header entirely, but a non-bypass caller still must
  supply it, enforced manually with a `422` rather than relying on FastAPI's own required-param
  check:

  ```python
  if set(current_user.roles or []).intersection(entity.rls.bypass_roles):
      owner_id = None
  elif rls_owner_header is None:
      raise HTTPException(
          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
          detail="Missing required header: <header_name>",
      )
  else:
      owner_id = rls_owner_header
  ```

  This applies to `list`/`read`/`update`/`delete`. **`create` is excluded from this bypass path
  entirely** — see below.

**`create` is never bypass-aware, for either identity source.** A bypass-role caller creating a
row under the same "`owner_id = None` means unfiltered" logic used everywhere else would write a
`NULL` owner — a row invisible to every non-bypass caller *forever*, since it belongs to nobody.
The current `module_routes.py.jinja` template fixes this with an explicit comment documenting why
`create` is deliberately **not** bypass-aware:

```python
# Deliberately NOT bypass-aware, unlike list/get/update/delete below: there,
# owner_id=None means "don't filter - this caller may act on everyone's rows",
# which is exactly what a bypass role should grant. On create there is no row to
# filter yet, only a row to stamp, and "I may act on everyone's rows" must never
# become "the row I create belongs to nobody" (a NULL owner is invisible to every
# non-bypass caller forever). So create always stamps the caller's own id.
owner_id = current_user.id   # auth_user identity
```

For `header` identity, `create` always keeps the header **required**
(`Header(..., alias="<header_name>")`, never `Optional`) and stamps `owner_id = rls_owner_header`
regardless of `bypass_roles` — a bypass-role caller can still create a row for any tenant, they
just have to say which one via the header, same as anyone else.

So today: `list`/`read`/`update`/`delete` treat a bypass role as "see/act on everyone's rows"
(for either identity source), while `create` always stamps a concrete owner — the creating
caller's own id for `auth_user` identity, or the caller-supplied header value for `header`
identity — bypass role or not. There is no way, through the generated API, to create a row with a
`NULL` owner.

## Public read: `read_scope`

`rls.read_scope: "any_authenticated"` (default `"owner"`) makes `list`/`read` visible to **any**
authenticated caller, regardless of row ownership — the classic "public blog post, owner-only
edit" pattern that plain per-owner filtering can't express. It only ever affects `list`/`read`;
`create`/`update`/`delete` stay owner- (or bypass-) scoped exactly as with the default
`"owner"`:

```python
if entity.rls.read_scope == 'any_authenticated':
    owner_id = None
```

This check runs *before* any bypass-role check on `list`/`read`, so it applies unconditionally —
`bypass_roles`, if also set, only has independent effect on `update`/`delete` in that case (`list`/
`read` are already unfiltered for everyone).

What "any authenticated caller" requires depends on `identity_source.type`:

- **`auth_user`**: the caller just needs a valid JWT — the normal `Depends(get_current_user)` (or
  `require_roles(...)` if RBAC gates the action) dependency already provides that.
- **`header`**: normally the request needs no authentication at all for `header` identity — but
  `read_scope: "any_authenticated"` changes that for `list`/`read` specifically. The route drops
  the header parameter entirely and instead requires a valid JWT
  (`Depends(_auth_service.get_current_user)`), which is why this combination requires
  `auth.enabled: true` (enforced by `app/erd/loader.py` — otherwise there'd be no `_auth_service`
  to authenticate against).

Real, tested example: `examples/ecommerce.yml`'s `Review` entity (`identity_source: {type:
auth_user}`, `read_scope: any_authenticated`, `bypass_roles: [admin]`) — any authenticated
customer can list/read every review, but only the review's own author (or an admin, via bypass)
can update or delete it.

### Service and schema layers

`module_service.py.jinja`'s `create_<entity>` for a root-owned entity injects the resolved
`owner_id` straight into the payload dict server-side:

```python
data["{{ entity.rls.owner_fk_column }}"] = owner_id
```

and `module_schemas.py.jinja` drops that owner FK field from `<Entity>Create`/`<Entity>Update`
entirely for a root-owned entity — the client can never supply it, so there's no "client-supplied
owner value silently overridden" ambiguity to test for; the field doesn't exist on the schema.
Cascade-owned entities are unaffected at the schema layer — their linking FK (e.g. `order_id` on
`OrderItem`) stays a normal, client-supplied field, but is ownership-checked: `create`/`update`
validate that FK by calling the parent's own `owner_id`-filtered `get_<parent>_by_id`, so setting
`order_id` to an `Order` that exists but isn't owned by the caller fails the same way as a
genuinely nonexistent order — recursively enforcing the whole chain for free, since validating
the immediate parent's ownership already validated *its* parent.

## Bypass roles

`rls.bypass_roles` (requires `rbac.enabled: true`, since a bypass role is an RBAC role) lets
specific roles — typically `admin` — see and act on every row, not just their own, for
`list`/`read`/`update`/`delete`. Valid with **either** `identity_source.type`: an `auth_user`
bypass role sees across every owner; a `header` bypass role sees across every tenant without
needing to supply the tenant header at all. As covered above, bypassing never applies to
`create`: every created row is always owned by whoever (or whatever tenant) created it.

Real, tested example: `examples/multi_tenant_saas.yml`'s `Project` entity (`identity_source:
{type: header, header_name: X-Tenant-Id}`, `bypass_roles: [admin]`) — an `admin` caller sees and
acts on every tenant's projects with no `X-Tenant-Id` header at all, while a non-admin caller
stays fully isolated to whichever tenant its header names. `Task`, which inherits `Project`'s
ownership via `cascades_ownership: true`, gets the same bypass behavior automatically.

## Error handling

Non-owner access to a single row (`GET`/`PUT`/`DELETE`) — root-owned or cascade-owned — returns
**404**, indistinguishable from the row not existing, so a non-owner can't distinguish "not mine"
from "doesn't exist" (no existence-leak). The same reasoning applies to a cascaded `create`/
`update` whose linking FK references a row that exists but isn't owned by the caller: it gets the
same 400 as a genuinely nonexistent FK. A missing required identity header (`header` identity
source) is a native FastAPI 422 — no custom error handling needed. `list` never errors for RLS
reasons; a filtered caller just sees a smaller (possibly empty) result set.

## Non-goals

Carried over from the RLS design spec, §8, and still accurate against current scope: arbitrary
declarative predicates beyond ownership (e.g. `status == 'published' OR owner_id == user.id`),
field/column-level visibility restrictions, ownership via one-to-one or many-to-many
relationships, audit logging of denied (404'd) access, runtime-configurable bypass beyond
declared roles, and any identity-source mechanism beyond JWT-`auth_user` and trusted-header (e.g.
API-key-to-tenant mapping).
