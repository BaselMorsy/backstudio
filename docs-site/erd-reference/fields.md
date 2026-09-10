# Full field reference

Exhaustive, field-by-field reference for every Pydantic model in `app/erd/schema.py`, the
single source of truth for the ERD YAML format. Organized by the same top-level sections as the
[Schema overview](overview.md).

Cross-field validation rules (rules that depend on more than one field, sometimes across
sections) are called out separately — most live in `app/erd/loader.py`'s `_validate_semantics`,
`_validate_rls`, and `_validate_services` functions and run *after* the YAML has already passed
Pydantic's own per-field validation.

!!! note "Reading the tables"
    "Required/default" shows the literal default value from `app/erd/schema.py` if the field is
    optional, or **required** if the model raises a validation error when it's omitted.

## Top level (`ERDConfig`)

| Field | Type | Required/default | Description |
|---|---|---|---|
| `project` | `ProjectMeta` | required | Project metadata. |
| `database` | `DatabaseSpec` | required | Database backend and connection settings. |
| `auth` | `AuthSpec` | default `AuthSpec()` (auth off) | JWT authentication and registration. |
| `rbac` | `RBACSpec` | default `RBACSpec()` (RBAC off) | Role-based access control. |
| `entities` | `List[EntitySpec]` | default `[]` | The data model. |
| `services` | `List[ServiceDecl]` | default `[]` | Entity-to-module grouping. |

**Cross-field rule (loader):** an ERD must declare at least one entity —
`app/erd/loader.py`'s `_validate_semantics` raises `"ERD must declare at least one entity"` if
`entities` is empty, even though the schema itself allows an empty list.

## `project` (`ProjectMeta`)

| Field | Type | Required/default | Description |
|---|---|---|---|
| `name` | `str` (min length 1) | required | Project name. |
| `version` | `str` | default `"1.0.0"` | Project version string. |
| `description` | `Optional[str]` | default `None` | Project description. |

## `database` (`DatabaseSpec`)

| Field | Type | Required/default | Description |
|---|---|---|---|
| `type` | `CliDatabaseType` enum: `postgresql`, `mysql`, `sqlite` | required | Database backend the CLI's SQLAlchemy code generation targets. |
| `host` | `Optional[str]` | default `"localhost"` | Database host. |
| `port` | `Optional[int]` | default `None` | Database port (backend-specific default is used by the generated project if omitted). |
| `database_name` | `str` | required | Database/schema name. |
| `username` | `Optional[str]` | default `None` | Database username. |
| `use_env_vars` | `bool` | default `True` | Whether the generated project reads connection settings from environment variables rather than hardcoding them. |
| `pool_size` | `int` | default `10` | SQLAlchemy connection pool size. |
| `echo` | `bool` | default `False` | Whether SQLAlchemy logs all executed SQL (`echo=True`). |
| `async_mode` | `bool` | default `False` | When `true`, generates an async SQLAlchemy engine/session stack (`asyncpg`/`aiomysql`/`aiosqlite` driver, async-aware Alembic `env.py` using `run_sync()`, async repository/service/route layers) instead of the default sync stack. See [Async database support](../features/async.md) for the full generated-code mechanics. |

## `auth` (`AuthSpec`)

| Field | Type | Required/default | Description |
|---|---|---|---|
| `enabled` | `bool` | default `False` | Turns on JWT authentication and the auto-injected `User` entity. Most other auth/RBAC/RLS behavior is gated on this. |
| `jwt` | `JWTSpec` | default `JWTSpec()` | JWT signing and token-lifetime settings — see below. |
| `registration` | `RegistrationSpec` | default `RegistrationSpec()` | Registration mode — see below. |

### `auth.jwt` (`JWTSpec`)

Verified directly against `app/erd/schema.py` (lines 79–85):

| Field | Type | Required/default | Description |
|---|---|---|---|
| `secret_env_var` | `str` | default `"JWT_SECRET"` | Name of the environment variable the generated project reads the JWT signing secret from. |
| `algorithm` | `str` | default `"HS256"` | JWT signing algorithm. |
| `expiration_minutes` | `int` | default `30` | Access token lifetime, in minutes. |
| `refresh_token_expiration_minutes` | `int` | default `10080` | Refresh token lifetime, in minutes (10080 minutes = 7 days). |
| `email_verification_expiration_minutes` | `int` | default `1440` | Email-verification token lifetime, in minutes (1440 minutes = 24 hours). |
| `password_reset_expiration_minutes` | `int` | default `30` | Password-reset token lifetime, in minutes. |

These are the 4 JWT lifetime fields the model declares: `expiration_minutes`,
`refresh_token_expiration_minutes`, `email_verification_expiration_minutes`, and
`password_reset_expiration_minutes` (plus the non-lifetime `secret_env_var` and `algorithm`
fields on the same model).

### `auth.registration` (`RegistrationSpec`)

| Field | Type | Required/default | Description |
|---|---|---|---|
| `mode` | `Literal["open", "email_verification", "admin_approval"]` | default `"open"` | Registration flow. See below for what each mode requires and gates. |

!!! warning "`admin_approval` requires RBAC"
    `mode: admin_approval` requires `rbac.enabled: true` — and since `rbac.enabled: true`
    itself requires `"admin"` in `rbac.roles` (see [`rbac`](#rbac-rbacspec) below),
    `admin_approval` transitively requires an `admin` role to exist.

**`mode` values, verified against `app/erd/loader.py`:**

- **`open`** — no extra requirements. New users are active immediately on registration.
- **`email_verification`** — adds a reserved `is_verified` field to the auto-injected `User`
  entity (`MODE_GATED_RESERVED_USER_FIELDS["email_verification"] = {"is_verified"}` in
  `app/erd/loader.py`); a declared `User` entity's own fields cannot use that name. No RBAC
  dependency.
- **`admin_approval`** — adds a reserved `is_approved` field to `User`
  (`MODE_GATED_RESERVED_USER_FIELDS["admin_approval"] = {"is_approved"}`), **and requires
  `rbac.enabled: true`**. From `app/erd/loader.py`'s `_validate_semantics`:

  ```python
  if erd.auth.registration.mode == "admin_approval" and not erd.rbac.enabled:
      raise ERDValidationError(
          "auth.registration.mode: admin_approval requires rbac.enabled: true — the "
          "'POST /users/{id}/approve' endpoint that approves a pending registration is "
          "gated to the 'admin' role, which requires RBAC to exist."
      )
  ```

  Because `rbac.enabled: true` itself requires `"admin"` in `rbac.roles` (see below),
  `admin_approval` transitively requires an `admin` role to be declared.

**Cross-field rule (loader, `User` entity field collisions):** if you declare your own `User`
entity (only possible when `auth.enabled: true`), its field names must not collide with the
auto-injected auth fields: `id`, `email`, `password_hash`, `roles`, `is_active`, `created_at`,
`updated_at` (always reserved), plus `is_verified` (only reserved when
`registration.mode: email_verification`) or `is_approved` (only reserved when
`registration.mode: admin_approval`).

## `rbac` (`RBACSpec`)

| Field | Type | Required/default | Description |
|---|---|---|---|
| `enabled` | `bool` | default `False` | Turns on role-based access control. |
| `roles` | `List[str]` | default `[]` | The set of valid role names for this project. |
| `default_permissions` | `Dict[str, List[str]]` | default `{}` | Maps a CRUD action (`create`, `list`, `read`, `update`, `delete`) to the list of roles allowed to perform it on any entity that doesn't override it via `endpoints.rbac`. Schema-level validation (`RBACSpec.actions_are_known`) rejects any key that isn't one of those 5 actions. |

!!! warning "RBAC needs auth, and an `admin` role"
    `rbac.enabled: true` requires **both**: `auth.enabled: true` (RBAC needs a way to identify
    the current user) **and** `"admin"` present in `rbac.roles` (the auto-generated admin
    user-management endpoints — list/get/set-roles/deactivate/reactivate users — are gated to
    that exact role name).

**Cross-field rules (loader, `app/erd/loader.py` `_validate_semantics`):**

- `rbac.enabled: true` requires `auth.enabled: true`:

  ```python
  if erd.rbac.enabled and not erd.auth.enabled:
      raise ERDValidationError(
          "rbac.enabled requires auth.enabled: true (RBAC needs a way to identify the current user)"
      )
  ```

- `rbac.enabled: true` requires `"admin"` to be present in `rbac.roles`:

  ```python
  if erd.rbac.enabled and "admin" not in erd.rbac.roles:
      raise ERDValidationError(
          "rbac.enabled requires 'admin' to be declared in rbac.roles — the auto-generated "
          "admin user-management endpoints (list/get/set-roles/deactivate/reactivate users) "
          "are gated to that specific role name, exactly like 'User' is a reserved entity "
          f"name. Declared roles: {', '.join(erd.rbac.roles) or 'none'}."
      )
  ```

- When `rbac.enabled: true`, every role named in `rbac.default_permissions` values must be a
  role declared in `rbac.roles` (unknown roles raise an error naming the declared set).
- When `rbac.enabled: true`, every role named in a per-entity `endpoints.rbac` override (see
  `entities` below) must likewise be declared in `rbac.roles`.

## `entities` (`List[EntitySpec]`)

Each entry is an `EntitySpec`:

| Field | Type | Required/default | Description |
|---|---|---|---|
| `name` | `str` (min length 1) | required | Entity name (becomes the table/model name). `"User"` is reserved for the auto-injected auth entity — declaring your own `User` entity is only valid when `auth.enabled: true`. |
| `table_name` | `Optional[str]` | default `None` | Overrides the generated table name (defaults to a derivation of `name` if omitted). |
| `fields` | `List[ModelField]` | default `[]` | The entity's columns — see `ModelField` below. |
| `relationships` | `List[RelationshipDecl]` | default `[]` | Relationships to other entities — see `RelationshipDecl` below. |
| `endpoints` | `EndpointSpec` | default `EndpointSpec()` | Which CRUD endpoints to generate and their RBAC overrides — see `EndpointSpec` below. |
| `rls` | `Optional[RLSSpec]` | default `None` | Row-level security identity source, required when the entity has an `owner: true` relationship — see `RLSSpec` below. |

**Cross-field rules (loader):**

- Entity names must be unique across the ERD.
- If `auth.enabled: false`, no entity may be named `"User"` (it would be silently dropped from
  generation since there's no auth entity to merge it into).
- Field names within one entity must be unique.
- A relationship's `target` must name a known entity (a declared entity, or `"User"` when
  `auth.enabled: true`).
- A self-referential (`target == entity.name`) `many-to-many` relationship is rejected —
  not supported by the code generator.

### `ModelField`

| Field | Type | Required/default | Description |
|---|---|---|---|
| `name` | `str` | required | Field name. |
| `type` | `FieldType` enum: `string`, `integer`, `float`, `boolean`, `datetime`, `date`, `text`, `json`, `uuid` | required | Field data type. |
| `nullable` | `bool` | default `True` | Whether field can be null. |
| `unique` | `bool` | default `False` | Whether field must be unique. |
| `default` | `Optional[Any]` | default `None` | Default value. |
| `primary_key` | `bool` | default `False` | Whether this is a primary key. |
| `index` | `bool` | default `False` | Whether to create an index. |
| `max_length` | `Optional[int]` | default `None` | Max length for string fields. |

### `RelationshipDecl`

Only one side of a relationship needs to declare it — `translate.py` fills in the other side.

| Field | Type | Required/default | Description |
|---|---|---|---|
| `name` | `str` | required | Relationship attribute name. |
| `cardinality` | `Cardinality` enum: `one-to-many`, `many-to-one`, `one-to-one`, `many-to-many` | required | Relationship cardinality. |
| `target` | `str` | required | Name of the target entity. |
| `attribute` | `Optional[str]` | default `None` | Overrides the attribute name on this side. |
| `target_attribute` | `Optional[str]` | default `None` | Overrides the attribute name on the target side. |
| `foreign_key_column` | `Optional[str]` | default `None` | Overrides the generated foreign-key column name. |
| `nullable` | `bool` | default `True` | Whether the foreign key is nullable. |
| `unique` | `bool` | default `False` | Whether the foreign key is unique (e.g. to model one-to-one). |
| `ondelete` | `Optional[str]` | default `None` | SQL `ON DELETE` behavior (e.g. `SET NULL`, `CASCADE`). |
| `lazy` | `Optional[LazyStrategy]` enum: `select`, `joined`, `selectin`, `subquery`, `raise` | default `None` | SQLAlchemy lazy-loading strategy. |
| `cascade` | `Optional[str]` | default `None` | SQLAlchemy `cascade` string. |
| `association_table` | `Optional[str]` | default `None` | Overrides the association table name for `many-to-many`. |
| `owner` | `bool` | default `False` | Marks this relationship's target as the entity that owns rows of this entity, for row-level security. At most one relationship per entity may set this. Only valid on `many-to-one`. |
| `cascades_ownership` | `bool` | default `False` | Marks that this entity's ownership is inherited transitively through this relationship's target, rather than declared directly. At most one relationship per entity may set this. Only valid on `many-to-one`. Mutually exclusive with `owner` on the same relationship. |

**Cross-field rules (schema-level, `RelationshipDecl.owner_and_cascades_ownership_are_valid`):**

- `owner: true` and `cascades_ownership: true` cannot both be set on the same relationship.
- `owner: true` or `cascades_ownership: true` is only valid when `cardinality: many-to-one`.

**Cross-field rules (schema-level, `EntitySpec.at_most_one_owner_and_one_cascades_ownership_relationship`):**

- An entity may have at most one relationship with `owner: true`.
- An entity may have at most one relationship with `cascades_ownership: true`.

### `endpoints` (`EndpointSpec`)

| Field | Type | Required/default | Description |
|---|---|---|---|
| `enabled` | `List[str]` | default `["create", "list", "read", "update", "delete"]` | Which CRUD actions to generate endpoints for. Values are validated against that same 5-action set. |
| `base_path` | `Optional[str]` | default `None` | Overrides the generated route prefix. |
| `tags` | `Optional[List[str]]` | default `None` | Overrides the OpenAPI tags for this entity's routes. |
| `rbac` | `Optional[EndpointRBAC]` | default `None` | Per-action role overrides for this entity, taking precedence over `rbac.default_permissions` — see `EndpointRBAC` below. |

#### `EndpointRBAC`

| Field | Type | Required/default | Description |
|---|---|---|---|
| `create` | `Optional[List[str]]` | default `None` | Roles allowed to create, overriding the default. |
| `list` | `Optional[List[str]]` | default `None` | Roles allowed to list, overriding the default. |
| `read` | `Optional[List[str]]` | default `None` | Roles allowed to read, overriding the default. |
| `update` | `Optional[List[str]]` | default `None` | Roles allowed to update, overriding the default. |
| `delete` | `Optional[List[str]]` | default `None` | Roles allowed to delete, overriding the default. |

**Cross-field rule (loader):** when `rbac.enabled: true`, every role listed in an entity's
`endpoints.rbac` overrides must already be declared in `rbac.roles`.

### RLS: row-level security (`RLSSpec`)

| Field | Type | Required/default | Description |
|---|---|---|---|
| `identity_source` | `RLSIdentitySource` | required | Where the "current owner" identity is resolved from — see below. |
| `bypass_roles` | `List[str]` | default `[]` | Roles that bypass row-level filtering entirely for this entity. |

!!! warning "Do you need a `User` entity for RLS?"
    Only if `identity_source.type: auth_user` — that resolves ownership from the
    JWT-authenticated `User`, so it requires `auth.enabled: true`. `identity_source.type:
    header` needs **neither** `auth.enabled` nor a `User` entity at all — it resolves ownership
    from a request header instead. Either way, `bypass_roles` (if used) still requires
    `rbac.enabled: true`.

#### `RLSIdentitySource`

| Field | Type | Required/default | Description |
|---|---|---|---|
| `type` | `Literal["auth_user", "header"]` | required | `auth_user` resolves ownership from the JWT-authenticated `User`; `header` resolves it from a request header value (e.g. for multi-tenant setups without per-row user auth). |
| `header_name` | `Optional[str]` | default `None` | Required when `type: header` (e.g. `X-Tenant-Id`); must not be `Authorization` (case-insensitive) since that header is already reserved for the `Bearer <token>` JWT scheme. |

**Cross-field rules (loader, `app/erd/loader.py` `_validate_rls`, plus one schema-level
validator on `RLSIdentitySource`):**

- Schema-level: `type: header` requires `header_name` to be set, and `header_name` must not be
  `"Authorization"` (case-insensitive).
- Any entity that has a relationship with `owner: true` **must** declare an `rls:` block.
- `identity_source.type: auth_user` requires `auth.enabled: true`.
- `identity_source.type: auth_user` requires the owning relationship's `target` to be `"User"`
  (a different owner entity must use `type: header` instead).
- `bypass_roles` has no effect (and is rejected) when `identity_source.type: header` — the
  header identity source carries no role information for a bypass role to plug into.
- `bypass_roles` requires `rbac.enabled: true` (bypass roles are RBAC roles), and every listed
  role must already be declared in `rbac.roles`.
- An entity whose ownership is declared via `cascades_ownership: true` (rather than `owner:
  true` directly) must have a chain of `cascades_ownership` relationships that terminates at
  some entity with `owner: true`, with no cycles.

Full row-level-security mechanics, including how the owning column and query filtering are
generated: [Row-Level Security](../features/rls.md).

## `services` (`List[ServiceDecl]`)

Each entry is a `ServiceDecl`:

| Field | Type | Required/default | Description |
|---|---|---|---|
| `name` | `str` (min length 1) | required | Service/module name. Must be a valid lowercase Python identifier (letters, digits, underscores; not starting with a digit) — it becomes the generated `modules/<name>/` directory and function-name segment. |
| `entities` | `List[str]` (min length 1) | required | Names of the entities assigned to this service. |

**Cross-field rules (loader, `app/erd/loader.py` `_validate_services`):**

- Service names must be unique.
- If `auth.enabled: true`, `"User"` may be referenced by at most one service, and that
  service's `entities` list must contain `"User"` and nothing else. If a different service
  happens to be named the same as the (implicit or explicit) auth module name, that's rejected
  as a naming collision.
- Every entity name referenced in a service's `entities` list must be a declared entity (other
  than `"User"`, which is handled by the rule above).
- Every declared entity (other than `"User"`) must be assigned to **exactly one** service — not
  zero, not more than one.

## Enums reference

Quick lookup for every `Enum`/`Literal` type used above:

| Type | Values |
|---|---|
| `CliDatabaseType` (`database.type`) | `postgresql`, `mysql`, `sqlite` |
| `RegistrationSpec.mode` | `open`, `email_verification`, `admin_approval` |
| `RLSIdentitySource.type` | `auth_user`, `header` |
| `Cardinality` (`relationships[].cardinality`) | `one-to-many`, `many-to-one`, `one-to-one`, `many-to-many` |
| `LazyStrategy` (`relationships[].lazy`) | `select`, `joined`, `selectin`, `subquery`, `raise` |
| `FieldType` (`fields[].type`) | `string`, `integer`, `float`, `boolean`, `datetime`, `date`, `text`, `json`, `uuid` |
| CRUD actions (`endpoints.enabled`, `rbac.default_permissions` keys, `endpoints.rbac` fields) | `create`, `list`, `read`, `update`, `delete` |
