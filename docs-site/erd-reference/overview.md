# ERD schema overview

An ERD file is a single YAML document validated against the `ERDConfig` Pydantic model in
`app/erd/schema.py`. `ERDConfig` has six top-level keys:

| Key | Required? | Meaning |
|---|---|---|
| `project` | required | Name, version, and description of the generated project. |
| `database` | required | Which database backend to target and how to connect to it. |
| `auth` | optional (defaults off) | JWT authentication and registration mode. |
| `rbac` | optional (defaults off) | Role-based access control: declared roles and default per-action permissions. |
| `entities` | optional at the schema level, but the loader requires at least one | The data model: one entry per table, with its fields, relationships, generated endpoints, and (if owned) row-level security. |
| `services` | optional at the schema level, but the loader requires every entity to be assigned to exactly one | Groups entities into named modules — each becomes a `modules/<name>/` directory in the generated project. |

This page shows the shape of each key with one short snippet. For every field's exact name,
type, default value, and validation rule, see the
[Full field reference](fields.md).

## Constraints at a glance

These keys aren't independent — several have real dependencies on each other, enforced by
`app/erd/loader.py` at generate time (not just the schema). The full field reference explains
each one in depth, with the exact loader code; this is the cheat sheet.

!!! warning "RBAC needs auth, and an `admin` role"
    `rbac.enabled: true` requires **both** `auth.enabled: true` (RBAC needs a way to identify
    the current user) **and** `"admin"` present in `rbac.roles` (the auto-generated admin
    user-management endpoints are gated to that exact role name).

!!! warning "`admin_approval` registration needs RBAC"
    `auth.registration.mode: admin_approval` requires `rbac.enabled: true` — the
    `POST /users/{id}/approve` endpoint that approves a pending registration is itself an
    admin-only, RBAC-gated route.

!!! warning "Does row-level security need a `User` entity?"
    Only if you use `identity_source.type: auth_user` — that resolves row ownership from the
    JWT-authenticated `User`, so it requires `auth.enabled: true`. `identity_source.type: header`
    needs **neither** `auth.enabled` nor a `User` entity — it resolves ownership from a request
    header instead (e.g. for multi-tenant setups with no per-row user auth). Either way,
    `bypass_roles` (if you use it) still requires `rbac.enabled: true`, since bypass roles are
    RBAC roles.

!!! warning "Every entity belongs to exactly one service"
    `services:` isn't optional bookkeeping — the loader rejects an ERD where any declared
    entity (other than the auto-injected `User`) isn't assigned to exactly one `services:`
    entry's `entities:` list. Zero or more-than-one is an error, not a default.

## `project`

```yaml
project:
  name: BlogAPI
  version: "1.0.0"
  description: A small blog API demonstrating auth, RBAC, and relationships
```

## `database`

```yaml
database:
  type: sqlite
  database_name: blog.db
```

## `auth`

```yaml
auth:
  enabled: true
  jwt:
    secret_env_var: BLOG_JWT_SECRET
    algorithm: HS256
    expiration_minutes: 60
  registration:
    mode: open
```

## `rbac`

```yaml
rbac:
  enabled: true
  roles: [admin, author, reader]
  default_permissions:
    read: [admin, author, reader]
    list: [admin, author, reader]
    create: [admin, author]
    update: [admin, author]
    delete: [admin]
```

## `entities`

Every entry is more than just fields — it can also declare relationships, restrict which CRUD
endpoints exist, override RBAC per action, and (if it's owned by a user) declare row-level
security. This example showcases the full shape, not just the common case:

```yaml
entities:
  - name: Post
    table_name: blog_posts          # optional: override the generated table name
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: title, type: string, max_length: 200}
      - {name: body, type: text}
    relationships:
      - name: category
        cardinality: many-to-one
        target: Category
        ondelete: SET NULL
        nullable: true
      - name: author
        cardinality: many-to-one
        target: User
        owner: true                 # this relationship IS Post's ownership column
    endpoints:
      enabled: [create, list, read, update, delete]   # restrict this list to disable an action entirely
      rbac:
        delete: [admin]              # per-action override, takes precedence over rbac.default_permissions
    rls:                             # required because a relationship above has owner: true
      identity_source:
        type: auth_user              # resolve the owner from the JWT-authenticated User
      bypass_roles: [admin]          # admins see/write every row, not just their own
```

`owner: true`/`cascades_ownership: true` (row-level ownership), `rls:` (where the owning identity
comes from), and `endpoints.enabled`/`endpoints.rbac` (which actions exist and who can call them)
are all real, independent capabilities — see
[Full field reference](fields.md#rls-row-level-security-rlsspec) and
[Row-Level Security](../features/rls.md) for the full mechanics.

## `services`

```yaml
services:
  - name: posting
    entities: [Category, Post]
```

Every entity declared under `entities:` must appear in exactly one `services:` entry's
`entities:` list (enforced by `app/erd/loader.py`, not by the schema itself).

## Next: full field reference

The [Full field reference](fields.md) documents every Pydantic model in `app/erd/schema.py`
field-by-field — name, type, required-or-default, description — plus the cross-field validation
rules enforced by `app/erd/loader.py` (e.g. what `rbac.enabled` requires, what
`auth.registration.mode: admin_approval` requires, and the row-level-security ownership rules).
