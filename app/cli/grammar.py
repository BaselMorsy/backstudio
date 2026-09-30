"""Condensed ERD YAML grammar reference shown by `backstudio grammar`.

Hand-curated from `app/erd/schema.py` (the actual source of truth) rather than
generated from docstrings, since most models here don't carry per-field
descriptions consistently enough to build readable prose from. Keep this in
sync with schema.py/loader.py when either changes - this is a fast terminal
cheat sheet, not a replacement for `docs-site/erd-reference/`.
"""

TOP_LEVEL = """\
ERD YAML top-level keys (app/erd/schema.py: ERDConfig):

  project     required    name, version, description
  database    required    backend type + connection settings
  auth        optional    JWT auth + registration mode        (default: off)
  rbac        optional    role-based access control            (default: off)
  entities    required*   the data model: fields, relationships, endpoints, RLS
  services    required*   groups entities into modules/<name>/ directories

  * the schema allows omitting these, but the loader requires at least one
    entity, and every entity assigned to exactly one service.

Run `backstudio grammar <topic>` for one section's exact grammar. Topics:
  project | database | auth | rbac | entities | fields | relationships |
  endpoints | rls | services

Full documentation: docs-site/erd-reference/ (run `uv run mkdocs serve` to browse it)
"""

TOPICS: dict[str, str] = {
    "project": """\
project:
  name: str                # required, min length 1
  version: str              # default "1.0.0"
  description: str          # optional
""",
    "database": """\
database:
  type: sqlite | postgresql | mysql   # required
  database_name: str                   # required
  host: str = "localhost"
  port: int                            # optional, backend default used if omitted
  username: str
  use_env_vars: bool = true            # generated project reads connection settings from env vars
  pool_size: int = 10
  echo: bool = false                   # log all executed SQL
  async_mode: bool = false             # async SQLAlchemy stack (asyncpg/aiomysql/aiosqlite)

# postgresql/mysql: default DATABASE_URL is built from type/username/host/port/database_name
# + the DB_PASSWORD env var (never store a password in the ERD). DATABASE_URL env var overrides.
""",
    "auth": """\
auth:
  enabled: bool = false
  mode: builtin | external                                  # default "builtin"
  jwt:                              # mode: builtin only
    secret_env_var: str = "JWT_SECRET"
    algorithm: str = "HS256"
    expiration_minutes: int = 30
    refresh_token_expiration_minutes: int = 10080          # 7 days
    email_verification_expiration_minutes: int = 1440      # 24 hours
    password_reset_expiration_minutes: int = 30
  registration:                     # mode: builtin only
    mode: open | email_verification | admin_approval        # default "open"
  external:                         # required when mode: external, else must be omitted
    jwks_url_env_var: str                                    # required, e.g. AUTH_JWKS_URL
    issuer: str                                               # required
    audience: str                   # optional; unset -> validate-time warning, no aud check
    algorithms: [str, ...] = [RS256]  # asymmetric only - HS256/HS384/HS512 rejected
    claims:
      subject: str = "sub"
      roles: str = "roles"

# admin_approval requires rbac.enabled: true (the approve-user endpoint is admin-only RBAC-gated)
# mode: builtin generates User + register/login/refresh/me; jwt/registration only apply here.
# mode: external generates only JWKS-verifying JWT decode (no User, no auth endpoints at all) -
#   identity comes entirely from a Principal built from the verified token's claims.
""",
    "rbac": """\
rbac:
  enabled: bool = false
  roles: [str, ...]                        # e.g. [admin, author, reader]
  default_permissions:
    create: [role, ...]
    list: [role, ...]
    read: [role, ...]
    update: [role, ...]
    delete: [role, ...]

# rbac.enabled requires auth.enabled: true AND "admin" present in rbac.roles
""",
    "entities": """\
entities:
  - name: str                  # required; "User" is reserved unless auth.enabled: true
    table_name: str             # optional, overrides the generated table name
    description: str              # optional; SQL table comment
    fields: [ ModelField, ... ]
    relationships: [ RelationshipDecl, ... ]
    endpoints: EndpointSpec
    rls: RLSSpec                 # required if any relationship below has owner: true

# See `backstudio grammar fields|relationships|endpoints|rls` for each block's shape.
# Entity names must be unique. Field names within one entity must be unique.
""",
    "fields": """\
fields:                                                     # ModelField
  - name: str                                                 # required
    type: string | integer | bigint | float | decimal | boolean |
          datetime | date | text | json | uuid | enum           # required
    nullable: bool = true
    unique: bool = false
    default: any                  # decimal: number or string; enum: one of `values`
    primary_key: bool = false     # integer or bigint; not decimal/enum
    index: bool = false
    max_length: int               # string fields only
    precision: int                # decimal only; required with scale
    scale: int                    # decimal only; 0 <= scale <= precision
    values: [str, ...]            # enum only; required, unique, e.g. [PENDING, POSTED]
    timezone: bool                # datetime only; default true (timezone-aware)
    description: str              # any type: SQL comment, OpenAPI description, diagram note

# enum values: letters/digits/underscores, start with a letter, no Python keywords and no
# names that shadow str/Enum attributes (class, None, name, value, count, ...). UPPER_SNAKE is safe.
# decimal on SQLite is stored as REAL; exactness is guaranteed on PostgreSQL/MySQL.
""",
    "relationships": """\
relationships:                                              # RelationshipDecl
  - name: str                                                 # required
    cardinality: one-to-many | many-to-one |
                 one-to-one | many-to-many                     # required
    target: str                                                # required, name of the target entity
    attribute: str                # overrides this side's attribute name
    target_attribute: str         # overrides the target side's attribute name
    foreign_key_column: str
    nullable: bool = true
    unique: bool = false          # e.g. to model one-to-one
    ondelete: str                 # e.g. SET NULL, CASCADE
    lazy: select | joined | selectin | subquery | raise
    cascade: str
    association_table: str        # many-to-many only
    owner: bool = false           # marks this as the RLS ownership column (many-to-one only)
    cascades_ownership: bool = false   # inherits ownership from target (many-to-one only)

# owner and cascades_ownership are mutually exclusive on one relationship, and
# each entity may have at most one relationship with owner: true and at most
# one with cascades_ownership: true. Only one side of a relationship needs to
# be declared - translate.py fills in the other side.
# `name` only drives the attribute/FK names when the entity has 2+ relationships to the same
# target; otherwise they are derived from the target (validate/generate warn). Set `attribute:` /
# `foreign_key_column:` to choose them explicitly.
""",
    "endpoints": """\
endpoints:                                                  # EndpointSpec
  enabled: [create, list, read, update, delete]    # default: all 5; also controls which repo/service functions are generated
  base_path: str          # overrides the route prefix; always wins over services[].prefix
  tags: [str, ...]        # overrides the OpenAPI tags
  rbac:                                                       # EndpointRBAC
    create: [role, ...]   # per-action override, takes precedence over rbac.default_permissions
    list: [role, ...]
    read: [role, ...]
    update: [role, ...]
    delete: [role, ...]
""",
    "rls": """\
rls:                                                         # RLSSpec, required when an
                                                               # entity has an owner: true relationship
  identity_source:
    type: auth_user | header | jwt_claim                       # required
    header_name: str        # required when type: header, e.g. X-Tenant-Id
                             # (must not be "Authorization")
    claim: str               # required when type: jwt_claim, e.g. agency_id
                             # (per-entity - two entities may read different claims)
  owner_match_field: str     # jwt_claim only; match the claim against this field on the
                             # owner entity instead of its primary key - must be unique: true,
                             # type string|uuid|integer|bigint
  bypass_roles: [role, ...]     # roles that skip row filtering entirely; requires rbac.enabled
  read_scope: owner | any_authenticated    # default "owner"

# auth_user: owner = the JWT-authenticated User (requires auth.enabled: true)
# header: owner = the request header's value (no auth.enabled/User needed)
# jwt_claim: owner = a claim on the verified external JWT (requires auth.mode: external)
# bypass_roles: mirrors auth_user for jwt_claim (create always stamps the caller's own
#   claim, bypass or not - a claim isn't client-suppliable per-request like a header is);
#   for header identity, list/read/update/delete are bypassed, create still requires
#   the header (a new row needs a concrete owner)
# jwt_claim: a missing claim on an authenticated, non-bypass request is 403, not 422
#   (422 is reserved for the header identity's "you forgot to supply this" case)
# read_scope: any_authenticated: list/read open to any authenticated caller
#   regardless of ownership; create/update/delete stay owner- (or bypass-) scoped
""",
    "services": """\
services:                                                   # ServiceDecl
  - name: str                # required, lowercase Python identifier -> modules/<name>/
    entities: [str, ...]      # required, min 1; every entity assigned to exactly one service
    prefix: str                # optional, must start with "/" and not end with "/"
                                # an entity's own endpoints.base_path always wins over this
""",
}
