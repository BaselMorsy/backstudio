# Modular Service Restructuring — Design Spec

Date: 2026-09-09
Status: Approved for implementation planning
Supersedes/extends: `docs/superpowers/specs/2026-09-08-erd-cli-design.md` (this spec assumes
that CLI/engine already exists and is shipped)

## 1. Motivation

The `backstudio` CLI currently generates one top-level directory per **entity**
(`categories/`, `posts/`, `auth/`), each with `routes.py` (calling
`database/repo.py` functions directly) and `schemas.py`. This conflates
"entity" with "service" — a real backend's service boundaries rarely map
1:1 to its tables, and a generated project with one folder per table doesn't
read as a coherent, deployable unit of business logic. It also gives users
no natural place to add custom logic: today's CRUD routes call
`database/repo.py` directly, so there's no per-service surface to extend
without editing the (nominally reusable/regenerable) route file itself.

This spec introduces an explicit **service** grouping concept in the ERD
YAML — you declare which entities belong to which service — and changes
generation output from one-folder-per-entity to one-folder-per-service under
a new `modules/` directory, with each service getting a real class (the
customization surface) sitting between its routes and the generic repo
layer. This also sets up a natural home for two things explicitly deferred
out of this spec: async support and row-level access control (both would
live in/interact with the service layer this spec introduces).

## 2. Scope boundary

- This spec covers **only** the module/service restructuring. It does not
  change RBAC semantics, does not add async support, does not add row-level
  access control, and does not expand auth's capabilities beyond what it has
  today (register/login/refresh/me). Those are explicitly out of scope —
  see §8.
- A follow-up spec ("Spec 2: Auth Service Expansion" — admin user
  management, registration gating, forgot/reset password) will be designed
  and implemented **after** this spec ships, against the real restructured
  code, not designed further ahead of ground truth now.
- Existing, already-shipped generation logic that this spec reuses
  unchanged where possible: `database/models.py.jinja`, `database/repo.py.jinja`,
  `database/base.py.jinja`, `rbac/dependency.py.jinja` (`rbac.py`), all
  top-level project files (`config.py`, `server.py` gets additive changes
  only, `.env`/`.gitignore` generation, `alembic/`, `requirements.txt`).
- The **existing singleton+factory pattern** already present (but unused by
  the CLI pipeline) in the legacy `backend/templates/Python/service/service.py.jinja`
  template is reused as the model for the new per-module `service.py`
  generation — not reinvented.

## 3. YAML schema addition: `services`

A new top-level, optional `services` block, conventionally written **after**
`entities:` in the file:

```yaml
entities:
  - name: Category
    fields: [...]
  - name: Post
    fields: [...]
    relationships: [...]

services:
  - name: posting
    entities: [Category, Post]
```

```python
class ServiceDecl(BaseModel):
    name: str = Field(..., min_length=1)
    entities: List[str] = Field(..., min_length=1)
```

### Validation rules (all hard errors — no implicit fallback/guessing)

1. Every entity declared in `entities:` (excluding the auto-injected `User`,
   see below) must appear in **exactly one** service's `entities` list.
   - Appearing in zero services → `ERDValidationError`: "Entity 'X' is not
     assigned to any service — every entity must belong to exactly one
     service."
   - Appearing in two or more services → `ERDValidationError`: "Entity 'X'
     is assigned to multiple services (A, B) — each entity must belong to
     exactly one service."
2. A service's `entities` list may not reference an unknown entity name
   (same class of error as today's relationship-target validation).
3. Two services may not share the same `name`.
4. If `services:` is entirely omitted while `entities:` is non-empty, this
   is **also a hard error** (per rule 1 — there is no implicit "one service
   per entity" fallback that reproduces today's behavior). Callers
   migrating an existing ERD must add a `services:` block.

### The `User` / auth exception

When `auth.enabled: true`, the auto-injected `User` entity is **exempt**
from rule 1: it does not need to appear in any `services` entry, and always
gets its own generated service. That service's name defaults to `auth`.

If the ERD's `services:` block *does* include an entry whose `entities`
list contains `User`, that entry's `name` becomes the auth service's name
instead of the default (e.g. `identity`) — this is the **only** effect of
declaring it explicitly. It does not change any of the auth-specific
behavior in §5. It is a validation error for such an entry to list *other*
entities alongside `User` (auth's service is always exactly `{User}` — see
§5 for why it isn't treated as a generic per-entity service).

## 4. Generated folder structure

```
modules/
├── <service_name>/                # one directory per declared service,
│   ├── __init__.py                 # plus the auth service (default name "auth")
│   ├── routes.py                    # every entity in this service, one shared APIRouter
│   ├── schemas.py                    # every entity's Create/Update/Response, one file
│   └── service.py                     # the <PascalCase>Service class + singleton factory
└── auth/  (or renamed)
    ├── __init__.py
    ├── routes.py                       # register/login/refresh/me only (§5)
    ├── schemas.py
    └── service.py                       # AuthService class + singleton factory

database/            # UNCHANGED — stays global (base.py, models.py, repo.py)
rbac.py               # UNCHANGED — stays global, shared by every module needing RBAC
config.py, server.py, .env, .gitignore, alembic/, requirements.txt, README.md   # UNCHANGED locations
```

`database/models.py` and `database/repo.py` stay centralized regardless of
service assignment: relationships cross-reference entities that may belong
to different services, and the generic CRUD functions in `repo.py` are
reused by every module's `service.py` — splitting them per-module would
require cross-module imports for every foreign-key relationship and gains
nothing.

### Path/tag handling within a shared module router

Today, `crud_routes.py.jinja` renders route decorators with **relative**
paths (`""`, `"/{item_id}"`), and `server.py.jinja` applies each entity's
`base_path` as a `prefix=` argument to `include_router()`. Since a single
service's `routes.py` can now contain entities with *different*
`base_path`es (e.g. `/categories` and `/posts` both live in
`modules/posting/routes.py`), a single router-level prefix no longer works.

**Change:** each entity's full `base_path` is now baked directly into that
entity's own route decorators within the shared file (e.g.
`@router.post("/posts", ...)`, `@router.get("/categories/{item_id}", ...)`).
`server.py.jinja` then does one `include_router()` per **module** with no
prefix (paths are already absolute). Each route's `tags` stays exactly as
today (still per-route, from that entity's own `endpoints.tags`) — no
per-module tag behavior needed.

## 5. `service.py`: the class, the singleton, the customization surface

For a non-auth service, `service.py` defines one class named
`{PascalCase(service.name)}Service`, with one method per (entity × enabled
CRUD action) for every entity assigned to that service. Each method's
default body is a thin delegation straight to the corresponding
`database/repo.py` function — **fully working out of the box**, not a
`NotImplementedError` stub:

```python
class PostingService:
    """PostingService — business logic for Category, Post.

    Singleton: constructed once per process (see get_posting_service below).
    Do not store per-request state on self — pass it as a method parameter
    instead (e.g. the db session, the current user), or it will leak across
    concurrent requests sharing this same instance.
    """

    def __init__(self) -> None:
        pass

    def create_post(self, db: Session, data: dict) -> Post:
        return create_post(db, data)

    def list_posts(self, db: Session, skip: int = 0, limit: int = 100) -> List[Post]:
        return get_all_posts(db, skip=skip, limit=limit)

    # ...get_post / update_post / delete_post, then the same for Category...


_posting_service_instance: Optional[PostingService] = None


def get_posting_service() -> PostingService:
    global _posting_service_instance
    if _posting_service_instance is None:
        _posting_service_instance = PostingService()
    return _posting_service_instance
```

`routes.py` depends on the singleton and calls its methods instead of
calling `database.repo` functions directly:

```python
@router.post("/posts", response_model=PostResponse, status_code=201, ...)
def create_post_route(
    payload: PostCreate,
    db: Session = Depends(get_db),
    service: PostingService = Depends(get_posting_service),
) -> PostResponse:
    return service.create_post(db, payload.model_dump())
```

RBAC dependencies (`Depends(require_roles(...))`) are unaffected — they
stay on the route decorator exactly as today, resolved per entity per
action exactly as today (§8 confirms this explicitly).

### Auth is special-cased, not generic CRUD

The auth service's `service.py` gets the same class+singleton treatment
(`AuthService`, `get_auth_service()`), but its methods are **today's
existing bespoke logic** — `register_user`, `authenticate_user`,
`hash_password`, `verify_password`, `create_access_token`,
`create_refresh_token`, `decode_token`, `get_current_user` — now as methods
on a class instead of flat module functions, not a generic per-entity CRUD
set. `User` never gets auto-generated `list`/`create`/`update`/`delete`
routes or methods in this spec: the response schema built from all of
`User`'s fields would leak `password_hash`, and "manage users" isn't
shaped like generic CRUD anyway (soft-deactivate vs. hard delete, role
assignment vs. arbitrary field PATCH). This is deliberately deferred to
Spec 2.

`rbac.py`'s `require_roles()` dependency currently does
`from auth.service import get_current_user`; this import path moves to
`from modules.{auth_service_name}.service import get_current_user`
(using whatever the auth service's actual configured/default name is).

## 6. Regeneration semantics (one-shot scaffold)

`backstudio generate --force` keeps its existing behavior: the whole
`codebase_dir` is wiped and regenerated, exactly as today. **No attempt is
made to preserve hand-edited `service.py` content** — unlike `.env`, which
already has preserve-across-`--force` logic (see the `_ensure_dev_env_secret`
/ preserved-`.env` mechanism in `backend/cli/main.py`), `modules/*/service.py`
is not given equivalent treatment in this spec.

This is a deliberate, accepted limitation: the mental model is "run
`generate` once per project to scaffold your services, then own
customization from there." Building selective/partial regeneration
(diffing which modules changed, merging hand-edits) is a substantially
larger feature with its own design questions and is out of scope here. This
limitation is documented in both this repo's README and the generated
project's own `README.md`.

## 7. Implementation-level translation changes (for the plan, not a user-facing decision)

- `backend/erd/schema.py`: add `ServiceDecl`, add `services: List[ServiceDecl]`
  to `ERDConfig`.
- `backend/erd/loader.py`: add the validation rules from §3.3 to
  `_validate_semantics`.
- `backend/erd/translate.py`: `translate()` currently produces a flat
  `crud_entities` list (one entry per entity). It now additionally groups
  entities by their resolved service name (including the auto-created/
  possibly-renamed auth service) into a new `state['modules']` structure:
  `[{name, snake_name, entities: [<crud_entity dict>, ...]}]`. The
  already-existing per-entity `crud_entities` shape (name, snake_name,
  plural_snake, base_path, tags, enabled_actions, rbac, fields) is reused
  unchanged as the element shape within each module's `entities` list —
  only the grouping is new.
- `backend/services/code_generator.py`: replace the per-entity CRUD
  generation loop (one `crud_schemas.py.jinja` / `crud_routes.py.jinja`
  render per entity, writing to `<plural_snake>/`) with a per-module loop
  (one `module_schemas.py.jinja` / `module_routes.py.jinja` /
  `module_service.py.jinja` render per module, writing to
  `modules/<module_snake_name>/`, each template iterating its module's
  entity list internally). Auth generation moves from `auth/` to
  `modules/<auth_module_name>/` and gains the class+singleton wrapper.
- `backend/templates/Python/server.py.jinja`: replace the per-entity
  import/include block with a per-module one (§4's path-baking change).
- New templates: `service/module_schemas.py.jinja`, `service/module_routes.py.jinja`,
  `service/module_service.py.jinja` (replacing today's
  `service/crud_schemas.py.jinja` / `service/crud_routes.py.jinja`, which
  can be deleted once the new ones are proven — no other consumer depends
  on the old per-entity template names). `auth/service.py.jinja` /
  `auth/routes.py.jinja` gain the class+singleton wrapper described in §5;
  `auth/schemas.py.jinja` is unaffected.
- `backend/templates/Python/rbac/dependency.py.jinja`: update the
  `get_current_user` import path per §5.
- Existing fixtures (`valid_full.yml`, `valid_minimal.yml`,
  `shophub_mini.yml`) and every test that consumes them need a `services:`
  block added (§3 rule 4 makes this a breaking change for any ERD without
  one) — this is expected, tracked in the implementation plan, not a
  design question.

## 8. Explicitly unaffected / explicitly deferred

- **RBAC** (`endpoints.rbac`, `rbac.default_permissions`, `require_roles()`
  resolution) — completely unchanged. Confirmed during design discussion:
  RBAC is keyed on (entity, action), entirely independent of which physical
  file a route lives in; multiple entities' independently-RBAC'd routes
  coexisting in one shared `routes.py` file introduces no new interaction.
- **Async support** — a separate, future spec. Nothing in this spec
  precludes it; the service layer this spec introduces is in fact where
  async/sync boundary decisions would naturally live later.
- **Row-level access control** — a separate, future spec, planned for
  after (or alongside) the async spec. The `service.py` layer this spec
  introduces is the natural home for ownership checks
  (e.g. `update_post(db, post_id, data, current_user)` comparing
  `post.author_id == current_user.id`) once designed.
- **Spec 2 (Auth Service Expansion)** — admin user management
  (list/get/set-roles/deactivate/reactivate, RBAC-gated to `admin`,
  `rbac.enabled: true` only), registration gating (email-verification and
  admin-approval modes), forgot/reset password (with a dev-mode
  `send_email()` stub that logs instead of sending, swappable for a real
  provider). Designed and implemented after this spec ships.
