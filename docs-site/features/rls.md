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

- **`jwt_claim`** (requires `auth.mode: external` — see [Authentication → External JWT
  verification](auth.md#external-jwt-verification-authmode-external)): resolved from a claim on
  the verified token, mirroring `auth_user`'s bypass ternary exactly rather than `header`'s. A
  claim is read from `current_user.claims`, not a request header, so there's nothing for a client
  to "supply" per request the way a header value is — the caller either has the claim (from
  whoever issued their token) or doesn't:

  ```python
  if set(current_user.roles or []).intersection(entity.rls.bypass_roles):
      owner_id = None
  else:
      _claim_value = current_user.claims.get(entity.rls.identity_source.claim)
      if _claim_value is None:
          raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required claim: ...")
      owner_id = _typed_jwt_claim(_claim_value, entity.rls.owner_id_type, entity.rls.identity_source.claim)
  ```

  A missing claim on an authenticated, non-bypass request is **403**, not the `header` identity's
  422 — see [Error handling](#error-handling). `_typed_jwt_claim` (generated once per module,
  guarded on at least one entity using `jwt_claim`) casts the raw claim string to whatever type
  `owner_match_field` needs (`int`/`UUID`/plain `str`); a claim that doesn't parse as that type is
  treated the same as a missing one — 403, never a 500.

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

**`create` is never bypass-aware, for any identity source.** A bypass-role caller creating a
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

`jwt_claim` identity mirrors this exactly, for the same reason: `create` always stamps the
caller's own claim value, unconditionally, never checking `bypass_roles` first — see
`app/templates/Python/service/module_routes.py.jinja`'s `create` block for the identical
"Deliberately NOT bypass-aware" comment repeated there.

For `header` identity, `create` always keeps the header **required**
(`Header(..., alias="<header_name>")`, never `Optional`) and stamps `owner_id = rls_owner_header`
regardless of `bypass_roles` — a bypass-role caller can still create a row for any tenant, they
just have to say which one via the header, same as anyone else.

So today: `list`/`read`/`update`/`delete` treat a bypass role as "see/act on everyone's rows"
(for every identity source), while `create` always stamps a concrete owner — the creating
caller's own id for `auth_user` identity, their own claim value for `jwt_claim` identity, or the
caller-supplied header value for `header` identity — bypass role or not. There is no way, through
the generated API, to create a row with a `NULL` owner.

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

**Except under `owner_match_field`** (see [below](#owner_match_field-matching-a-claim-against-a-non-pk-column)),
where `owner_id` is a claim value matched against a *different* unique column on the owner entity,
not that entity's own primary key. There, `create_<entity>` first resolves the actual owner row via
the already-generated `get_<owner>_by_<match_field>` repo lookup, then stamps the entity's real FK
column with that row's real primary key — never the raw claim value itself:

```python
_owner_row = repo.get_agency_by_agency_ref(db, owner_id)
if _owner_row is None:
    raise ValueError(f"Agency with agency_ref={owner_id!r} not found")
data["agency_id"] = _owner_row.id
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
`list`/`read`/`update`/`delete`. Valid with **any** `identity_source.type`: an `auth_user` bypass
role sees across every owner; a `jwt_claim` bypass role sees across every claim value (e.g. every
tenant/agency) without the token needing the claim at all; a `header` bypass role sees across
every tenant without needing to supply the tenant header at all. As covered above, bypassing never
applies to `create`: every created row is always owned by whoever (or whatever tenant) created it.

Real, tested example: `examples/multi_tenant_saas.yml`'s `Project` entity (`identity_source:
{type: header, header_name: X-Tenant-Id}`, `bypass_roles: [admin]`) — an `admin` caller sees and
acts on every tenant's projects with no `X-Tenant-Id` header at all, while a non-admin caller
stays fully isolated to whichever tenant its header names. `Task`, which inherits `Project`'s
ownership via `cascades_ownership: true`, gets the same bypass behavior automatically.

## `owner_match_field`: matching a claim against a non-PK column

By default, root-owned RLS matches the resolved `owner_id` against the owner entity's own primary
key (`WHERE <Owner>.id == owner_id`). `jwt_claim` identity can instead set `owner_match_field` to
match against any other **unique** column on the owner entity — the case where the claim in the
token is some external identifier (a tenant UUID from an identity provider, say) that isn't, and
was never meant to be, this project's own auto-increment primary key.

Real, tested example — `app/tests/fixtures/erd/jwt_claim_multi_tenant.yml` (the same fixture
`test_jwt_claim_rls_end_to_end_cross_tenant_isolation_and_bypass` runs a full HTTP round trip
against):

```yaml
entities:
  - name: Agency
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: agency_ref, type: uuid, unique: true}   # what the JWT actually names
      - {name: name, type: string}

  - name: Project
    relationships:
      - {name: agency, cardinality: many-to-one, target: Agency, owner: true}
    rls:
      identity_source: {type: jwt_claim, claim: agency_id}
      owner_match_field: agency_ref
      bypass_roles: [admin]
```

`agency_id` claim values are matched against `Agency.agency_ref` (a unique `uuid` column), never
`Agency.id` — a caller's token never needs to know or carry this project's internal integer
primary keys. Mechanically, this adds exactly one extra `.join()` hop into the same repo-layer
`WHERE`-clause-building described [above](#repo-layer-an-owner_id-parameter-none-means-unfiltered):
`Project.agency_id == Agency.id` then `Agency.agency_ref == owner_id`. A `cascades_ownership`
entity below `Project` (e.g. `Task`) composes with this automatically — the cascade branch that
builds its own join chain has no special-casing for `owner_match_field` at all, it just inherits
whatever root/join-chain the owner resolved to and prepends its own hop.

`owner_match_field` requires the named field to be `unique: true` and of type `string`, `uuid`,
`integer`, or `bigint` (enforced by the loader at validate time, not generation time). The matched
column's Python type also drives how the raw claim string gets cast before comparison — see
`_typed_jwt_claim` [above](#route-layer-resolving-owner_id-including-the-bypass-role-and-public-read-fixes).

## Error handling

Non-owner access to a single row (`GET`/`PUT`/`DELETE`) — root-owned or cascade-owned — returns
**404**, indistinguishable from the row not existing, so a non-owner can't distinguish "not mine"
from "doesn't exist" (no existence-leak). The same reasoning applies to a cascaded `create`/
`update` whose linking FK references a row that exists but isn't owned by the caller: it gets the
same 400 as a genuinely nonexistent FK. A missing required identity header (`header` identity
source) is a native FastAPI 422 — no custom error handling needed. A missing (or wrongly-typed,
under `owner_match_field`) claim on an authenticated, non-bypass request (`jwt_claim` identity) is
a **403** instead — deliberately different from `header`'s 422, since a claim's absence means "you
are not authorized for this," not "you forgot to pass a parameter": there is no way for the caller
to simply add the missing claim to their next request the way they could add a header. `list`
never errors for RLS reasons; a filtered caller just sees a smaller (possibly empty) result set.

## Non-goals

Carried over from the RLS design spec, §8, and still accurate against current scope: arbitrary
declarative predicates beyond ownership (e.g. `status == 'published' OR owner_id == user.id`),
field/column-level visibility restrictions, ownership via one-to-one or many-to-many
relationships, audit logging of denied (404'd) access, runtime-configurable bypass beyond
declared roles, and any identity-source mechanism beyond JWT-`auth_user`, JWT-claim, and
trusted-header (e.g. API-key-to-tenant mapping).
