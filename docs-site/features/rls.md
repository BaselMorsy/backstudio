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

### Route layer: resolving `owner_id`, including the bypass-role fix

`module_routes.py.jinja` resolves `owner_id` differently depending on `identity_source.type`:

- **`header`**: `owner_id` is the required `Header(..., alias="<header_name>")` value directly.
  No bypass path exists for header-sourced entities (a bypass role has no meaning without an
  authenticated user to hold it).
- **`auth_user`**: resolved from the JWT-authenticated caller's roles.

For `list`/`get`/`update`/`delete`, a caller with a declared bypass role gets `owner_id = None`
(unfiltered — see all rows, not just their own):

```python
owner_id = None if set(current_user.roles or []).intersection(entity.rls.bypass_roles) else current_user.id
```

**`create` is handled differently, and this is the fixed Critical bug.** The RLS design spec's
own final whole-branch review caught that a bypass-role caller creating a row would, under the
same `owner_id = None if bypass else current_user.id` logic used everywhere else, write a `NULL`
owner — a row invisible to every non-bypass caller *forever*, since it belongs to nobody. The
current `module_routes.py.jinja` template (lines 63–70) fixes this with an explicit comment
documenting why `create` is deliberately **not** bypass-aware:

```python
# Deliberately NOT bypass-aware, unlike list/get/update/delete below: there,
# owner_id=None means "don't filter - this caller may act on everyone's rows",
# which is exactly what a bypass role should grant. On create there is no row to
# filter yet, only a row to stamp, and "I may act on everyone's rows" must never
# become "the row I create belongs to nobody" (a NULL owner is invisible to every
# non-bypass caller forever). So create always stamps the caller's own id.
owner_id = current_user.id
```

So today: `list`/`get`/`update`/`delete` treat a bypass role as "see/act on everyone's rows,"
while `create` always stamps the creating caller's own id as owner, bypass role or not — there is
no way, through the generated API, to create a row with a `NULL` or other-caller owner.

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

`rls.bypass_roles` (only valid with `identity_source.type: auth_user`, and requires
`rbac.enabled: true`, since a bypass role is an RBAC role) lets specific roles — typically
`admin` — see and act on every row, not just their own, for `list`/`get`/`update`/`delete`. As
covered above, bypassing never applies to `create`: every created row is always owned by whoever
created it.

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
