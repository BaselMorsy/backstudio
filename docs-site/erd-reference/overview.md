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

```yaml
entities:
  - name: Post
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
    endpoints:
      rbac:
        delete: [admin]
```

An entity with an `owner: true` relationship also needs an `rls:` block declaring where the
owning identity comes from — see [Full field reference](fields.md#rls-row-level-security-rlsspec)
and [Row-Level Security](../features/rls.md) for the full mechanics.

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
