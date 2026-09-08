# Modular Service Restructuring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `backstudio` CLI's one-generated-folder-per-entity output (`categories/`, `products/`, `auth/`) with one-folder-per-declared-service under `modules/` (e.g. `modules/catalog/`, `modules/auth/`), driven by a new `services:` block in the ERD YAML that assigns entities to services. Each module gets a singleton service class as the customization surface between its routes and the generic repo layer.

**Architecture:** `backend/erd/schema.py` gains a `services` field; `backend/erd/loader.py` enforces that every entity belongs to exactly one service (auth's auto-injected `User` is exempt); `backend/erd/translate.py` groups entities into modules; three new Jinja templates (`module_schemas.py.jinja`, `module_routes.py.jinja`, `module_service.py.jinja`) replace the per-entity `crud_schemas.py.jinja`/`crud_routes.py.jinja`; the existing auth templates gain a class+singleton wrapper and move under `modules/`; `server.py.jinja` and `rbac/dependency.py.jinja` are updated to import from the new locations.

**Tech Stack:** Same as the existing CLI (Python 3.11, Pydantic v2, Jinja2, pytest) — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-09-modular-services-design.md`

## Global Constraints

- `services:` block placement convention: after `entities:` in example YAML (not enforced by the parser, just the documented convention).
- Every entity (excluding the auto-injected `User`) must belong to **exactly one** service — zero or two-or-more is a hard `ERDValidationError`, no implicit fallback.
- `User` never needs a service assignment; if `auth.enabled: true` it always gets its own service, named `auth` by default. A `services:` entry containing `User` may **only** contain `User` (validation error otherwise) and only renames that service.
- `database/models.py`, `database/repo.py`, `database/base.py`, `rbac.py`, `config.py`, `server.py`, `.env`, `.gitignore`, `alembic/`, `requirements.txt` all stay at the project root — unaffected by service assignment.
- Each module's `service.py` defines one class (singleton, via a module-level instance + `get_<module>_service()` factory, mirroring the existing pattern in `backend/templates/Python/service/service.py.jinja`). Its methods never store per-request state on `self`.
- `backstudio generate --force` keeps its existing full-wipe-and-regenerate behavior — no attempt to preserve hand-edited `modules/*/service.py` content (only `.env` gets that treatment, unchanged from before this plan).
- Auth stays special-cased: register/login/refresh/me only, wrapped in a class — no generic CRUD methods/routes for `User` (unchanged scope from before this plan; Spec 2 covers auth expansion later).
- Out of scope, not touched by this plan: async support, row-level access control, `Python/README.md.jinja` (already stale/legacy-flow-only before this plan — not fixed here, flagged as a pre-existing follow-up).

---

## File Structure

```
backend/
  erd/
    schema.py        # MODIFIED: + ServiceDecl, ERDConfig.services
    loader.py         # MODIFIED: + service-assignment validation
    translate.py       # MODIFIED: + modules/auth_module_name resolution, - crud_entities (Task 4)
  services/
    code_generator.py  # MODIFIED: entity generation loop -> per-module; auth output path
  templates/Python/
    service/
      module_schemas.py.jinja   # NEW (Task 4)
      module_routes.py.jinja     # NEW (Task 4)
      module_service.py.jinja     # NEW (Task 4)
      crud_schemas.py.jinja        # DELETED (Task 4)
      crud_routes.py.jinja           # DELETED (Task 4)
    auth/
      service.py.jinja   # MODIFIED (Task 5): class + singleton wrapper
      routes.py.jinja      # MODIFIED (Task 5): singleton-based dependency
      schemas.py.jinja       # UNCHANGED (output path only, handled in code_generator.py)
    rbac/dependency.py.jinja  # MODIFIED (Task 5): import path
    server.py.jinja             # MODIFIED (Task 4 entity block, Task 5 auth block)
  tests/
    fixtures/erd/
      valid_minimal.yml   # MODIFIED (Task 2): + services block
      valid_full.yml        # MODIFIED (Task 2): + services block
      shophub_mini.yml        # MODIFIED (Task 2): + services block, split into 2 services
    test_erd_schema.py        # MODIFIED (Task 1)
    test_erd_loader.py          # MODIFIED (Task 2)
    test_erd_translate.py         # MODIFIED (Tasks 3 & 4)
    test_crud_generation.py         # REWRITTEN (Task 4)
    test_server_wiring.py             # MODIFIED (Task 4 entity assertions, Task 5 auth assertions)
    test_cli_generate.py                # MODIFIED (Task 4)
    test_auth_generation.py               # MODIFIED (Task 5)
    test_end_to_end.py                      # MODIFIED (Task 4 entity paths, Task 5 auth paths, Task 6 cross-service check)
    test_generated_project_runtime.py         # UNCHANGED (verified in Task 6 — its module-name purging logic is already generic)
    test_rbac_generation.py                     # UNCHANGED (doesn't assert on the import line)
```

---

### Task 1: ERD schema — `services` block

**Files:**
- Modify: `backend/erd/schema.py`
- Test: `backend/tests/test_erd_schema.py`

**Interfaces:**
- Produces: `ServiceDecl` (fields: `name: str`, `entities: List[str]`), `ERDConfig.services: List[ServiceDecl]` (default `[]`) — consumed by Task 2 (loader validation) and Task 3 (translate.py grouping).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_erd_schema.py`:

```python
def test_services_block_parses():
    with_services = dict(MINIMAL)
    with_services["services"] = [{"name": "widgets", "entities": ["Widget"]}]
    erd = ERDConfig(**with_services)
    assert erd.services[0].name == "widgets"
    assert erd.services[0].entities == ["Widget"]


def test_services_defaults_to_empty_list():
    erd = ERDConfig(**MINIMAL)
    assert erd.services == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_erd_schema.py -v`
Expected: FAIL — `AttributeError: 'ERDConfig' object has no attribute 'services'` (Pydantic silently ignores the unknown `services` key today since there's no `extra="forbid"` config, so `ERDConfig(**with_services)` itself won't raise — the failure is on `erd.services`)

- [ ] **Step 3: Implement the schema addition**

Edit `backend/erd/schema.py` — add after `RelationshipDecl` (or anywhere before `ERDConfig`):

```python
class ServiceDecl(BaseModel):
    """Assigns a set of entities to a named service/module."""
    name: str = Field(..., min_length=1)
    entities: List[str] = Field(..., min_length=1)
```

Edit `ERDConfig` to add the new field:

```python
class ERDConfig(BaseModel):
    project: ProjectMeta
    database: DatabaseSpec
    auth: AuthSpec = Field(default_factory=AuthSpec)
    rbac: RBACSpec = Field(default_factory=RBACSpec)
    entities: List[EntitySpec] = Field(default_factory=list)
    services: List[ServiceDecl] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_erd_schema.py -v`
Expected: PASS (5/5 — the 3 pre-existing plus these 2 new)

- [ ] **Step 5: Commit**

```bash
git add backend/erd/schema.py backend/tests/test_erd_schema.py
git commit -m "feat: add services block to ERDConfig for entity-to-service assignment"
```

---

### Task 2: Loader validation — service assignment rules

**Files:**
- Modify: `backend/erd/loader.py`
- Modify: `backend/tests/fixtures/erd/valid_minimal.yml`
- Modify: `backend/tests/fixtures/erd/valid_full.yml`
- Modify: `backend/tests/fixtures/erd/shophub_mini.yml`
- Test: `backend/tests/test_erd_loader.py`

**Interfaces:**
- Consumes: `ERDConfig.services` (Task 1).
- Produces: `load_erd()` now rejects ERDs with unassigned/multiply-assigned entities, unknown service references, duplicate service names, and malformed `User` service entries — consumed by every later task that calls `load_erd()` on a fixture.

This task **must** update all three ERD fixtures in the same commit as the loader change, since the new validation makes any fixture without a `services:` block invalid — every existing test that calls `load_erd()` on these fixtures would otherwise start failing.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_erd_loader.py`:

```python
def test_unassigned_entity_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services: []
"""
    )
    with pytest.raises(ERDValidationError, match="not assigned to any service"):
        load_erd(bad)


def test_entity_assigned_to_two_services_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: a, entities: [Widget]}
  - {name: b, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="assigned to multiple services"):
        load_erd(bad)


def test_service_referencing_unknown_entity_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: widgets, entities: [Widget, Gadget]}
"""
    )
    with pytest.raises(ERDValidationError, match="references unknown entity 'Gadget'"):
        load_erd(bad)


def test_duplicate_service_names_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
  - {name: Gadget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: dup, entities: [Widget]}
  - {name: dup, entities: [Gadget]}
"""
    )
    with pytest.raises(ERDValidationError, match="Duplicate service name"):
        load_erd(bad)


def test_user_service_with_extra_entities_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: widgets, entities: [Widget]}
  - {name: identity, entities: [User, Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="must be the only entity"):
        load_erd(bad)


def test_user_service_without_auth_enabled_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: widgets, entities: [Widget]}
  - {name: identity, entities: [User]}
"""
    )
    with pytest.raises(ERDValidationError, match="auth.enabled is false"):
        load_erd(bad)


def test_user_service_renames_auth_module_without_error():
    # valid_full.yml (updated in this task) does not rename auth; this constructs
    # an inline-equivalent valid case directly to confirm the User-only exception works.
    import tempfile
    from pathlib import Path

    content = """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: widgets, entities: [Widget]}
  - {name: identity, entities: [User]}
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ok.yml"
        path.write_text(content)
        erd = load_erd(path)  # must not raise
        assert erd.services[1].name == "identity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_erd_loader.py -v`
Expected: FAIL — the new tests fail (no validation exists yet); ALSO, every pre-existing test in this file that calls `load_erd()` on `valid_minimal.yml`/`valid_full.yml` will start failing once Step 3's validation lands, until the fixtures are updated in Step 3 too. Confirm the new tests fail for the right reason first (no `ERDValidationError` raised at all), then proceed.

- [ ] **Step 3: Implement the validation and update fixtures**

Edit `backend/erd/loader.py` — add a new function and call it from `_validate_semantics`:

```python
def _validate_services(erd: ERDConfig) -> None:
    service_names = [s.name for s in erd.services]
    dup_service_names = sorted({n for n in service_names if service_names.count(n) > 1})
    if dup_service_names:
        raise ERDValidationError(f"Duplicate service name(s): {', '.join(dup_service_names)}")

    entity_names = {e.name for e in erd.entities if e.name != "User"}
    assigned: Dict[str, List[str]] = {}
    auth_services: List[str] = []

    for svc in erd.services:
        if "User" in svc.entities:
            if not erd.auth.enabled:
                raise ERDValidationError(
                    f"Service '{svc.name}': references entity 'User', but auth.enabled is false "
                    "(there is no auto-injected User entity to reference)"
                )
            if svc.entities != ["User"]:
                raise ERDValidationError(
                    f"Service '{svc.name}': the auth entity 'User' must be the only entity in its "
                    f"service (found: {', '.join(svc.entities)})"
                )
            auth_services.append(svc.name)
            continue

        for ent_name in svc.entities:
            if ent_name not in entity_names:
                raise ERDValidationError(
                    f"Service '{svc.name}': references unknown entity '{ent_name}'"
                )
            assigned.setdefault(ent_name, []).append(svc.name)

    if len(auth_services) > 1:
        raise ERDValidationError(
            f"Entity 'User' is assigned to multiple services: {', '.join(sorted(auth_services))}"
        )

    unassigned = sorted(entity_names - set(assigned.keys()))
    if unassigned:
        raise ERDValidationError(
            f"Entity(ies) not assigned to any service: {', '.join(unassigned)} — every entity "
            "must belong to exactly one service"
        )

    multiply_assigned = {name: svcs for name, svcs in assigned.items() if len(svcs) > 1}
    if multiply_assigned:
        details = "; ".join(
            f"'{name}' in ({', '.join(svcs)})" for name, svcs in sorted(multiply_assigned.items())
        )
        raise ERDValidationError(
            f"Entity(ies) assigned to multiple services: {details} — each entity must belong to "
            "exactly one service"
        )
```

Add `from typing import Dict, List` to the existing imports at the top of `loader.py` if not already present (check — `Union` is already imported from `typing`; add `Dict, List` alongside it).

Call it from `_validate_semantics`, near the end (after the existing per-entity loop, before or after the `rbac.default_permissions` check — placement doesn't matter for correctness, add it right after the closing of the `for entity in erd.entities:` loop):

```python
    _validate_services(erd)
```

Now update the fixtures. Replace the content of `backend/tests/fixtures/erd/valid_minimal.yml`:

```yaml
project:
  name: Demo

database:
  type: sqlite
  database_name: demo.db

entities:
  - name: Widget
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: label, type: string}

services:
  - name: widgets
    entities: [Widget]
```

Replace the content of `backend/tests/fixtures/erd/valid_full.yml`:

```yaml
project:
  name: ShopHub
  version: "1.0.0"
  description: A small e-commerce sample

database:
  type: postgresql
  database_name: shophub_db

auth:
  enabled: true
  jwt:
    secret_env_var: JWT_SECRET
    algorithm: HS256
    expiration_minutes: 30

rbac:
  enabled: true
  roles: [admin, editor, viewer]
  default_permissions:
    read: [admin, editor, viewer]
    list: [admin, editor, viewer]
    create: [admin, editor]
    update: [admin, editor]
    delete: [admin]

entities:
  - name: Category
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: name, type: string, unique: true}

  - name: Product
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: name, type: string, max_length: 200}
      - {name: price, type: float}
    relationships:
      - name: category
        cardinality: many-to-one
        target: Category
    endpoints:
      enabled: [create, list, read, update, delete]
      rbac:
        create: [admin]
        delete: [admin]

services:
  - name: catalog
    entities: [Category, Product]
```

Replace the content of `backend/tests/fixtures/erd/shophub_mini.yml`:

```yaml
project:
  name: ShopHubMini
  version: "1.0.0"
  description: A minimal ShopHub-style sample exercising auth, RBAC, and relationships

database:
  type: postgresql
  database_name: shophub_mini

auth:
  enabled: true
  jwt:
    secret_env_var: JWT_SECRET
    algorithm: HS256
    expiration_minutes: 60

rbac:
  enabled: true
  roles: [admin, customer]
  default_permissions:
    read: [admin, customer]
    list: [admin, customer]
    create: [admin, customer]
    update: [admin, customer]
    delete: [admin]

entities:
  - name: Category
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: name, type: string, unique: true}

  - name: Product
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: name, type: string, max_length: 200}
      - {name: price, type: float}
      - {name: sku, type: string, unique: true}
    relationships:
      - name: category
        cardinality: many-to-one
        target: Category
        ondelete: CASCADE
    endpoints:
      rbac:
        create: [admin]
        update: [admin]
        delete: [admin]

  - name: Order
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: status, type: string, default: pending}
      - {name: total_amount, type: float}
    relationships:
      - name: user
        cardinality: many-to-one
        target: User
      - name: product
        cardinality: many-to-one
        target: Product

services:
  - name: catalog
    entities: [Category, Product]
  - name: ordering
    entities: [Order]
```

Note `shophub_mini.yml` is now deliberately split into **two** services (`catalog`, `ordering`) — `Order` (in `ordering`) has a relationship to `Product` (in `catalog`), a different service. This is intentional: it's the fixture Task 6 uses to prove models/relationships stay correctly wired across service boundaries.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_erd_loader.py -v`
Expected: PASS (all — the 7 new tests plus every pre-existing one, since the fixtures are valid again)

Also run the full suite to confirm no other test broke from the fixture content changes: `uv run pytest backend/tests/ -v`. At this point in the plan, every test that calls `load_erd()` on these fixtures should still pass (nothing yet consumes `erd.services`, so parsing succeeds and all downstream behavior — `crud_entities`, generation, etc. — is unaffected).

- [ ] **Step 5: Commit**

```bash
git add backend/erd/loader.py backend/tests/fixtures/erd backend/tests/test_erd_loader.py
git commit -m "feat: validate that every entity is assigned to exactly one service"
```

---

### Task 3: translate.py — module grouping and auth module naming

**Files:**
- Modify: `backend/erd/translate.py`
- Test: `backend/tests/test_erd_translate.py`

**Interfaces:**
- Consumes: `ERDConfig.services` (Task 1), validated ERDs from `load_erd()` (Task 2).
- Produces: `translate()`'s returned dict gains two new keys — `modules: List[{name, snake_name, entities: [<crud_entity dict>, ...]}]` (one entry per non-auth service; `crud_entity` dicts are the exact same shape already produced for `crud_entities`, just grouped) and `auth_module_name: str` (the resolved auth service name, `"auth"` by default or the name of the `services:` entry whose `entities == ["User"]`). The pre-existing `crud_entities` key is **kept unchanged** in this task — it still gets computed exactly as before, so nothing downstream breaks yet. Task 4 is what switches consumers over to `modules` and removes `crud_entities`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_erd_translate.py`:

```python
def test_translate_groups_entities_into_modules():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    assert len(state["modules"]) == 1
    module = state["modules"][0]
    assert module["name"] == "catalog"
    assert module["snake_name"] == "catalog"
    entity_names = {e["name"] for e in module["entities"]}
    assert entity_names == {"Category", "Product"}

    # Each module entity is the exact same shape as a crud_entities entry.
    product = next(e for e in module["entities"] if e["name"] == "Product")
    assert product["base_path"] == "/products"
    assert product["rbac"]["create"] == ["admin"]


def test_translate_resolves_default_auth_module_name():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")  # auth enabled, no services: entry for User
    state = translate(erd)
    assert state["auth_module_name"] == "auth"


def test_translate_resolves_renamed_auth_module_name():
    erd = ERDConfig(
        project=ProjectMeta(name="Demo", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="demo.db"),
        auth=AuthSpec(enabled=True),
        entities=[
            EntitySpec(name="Widget", fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]),
        ],
        services=[
            ServiceDecl(name="widgets", entities=["Widget"]),
            ServiceDecl(name="identity", entities=["User"]),
        ],
    )
    state = translate(erd)
    assert state["auth_module_name"] == "identity"
    # The renamed auth service must not also appear in `modules` (it's handled separately).
    assert all(m["name"] != "identity" for m in state["modules"])


def test_translate_multiple_modules_stay_distinct():
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # catalog: [Category, Product], ordering: [Order]
    state = translate(erd)

    module_names = {m["name"] for m in state["modules"]}
    assert module_names == {"catalog", "ordering"}

    catalog = next(m for m in state["modules"] if m["name"] == "catalog")
    ordering = next(m for m in state["modules"] if m["name"] == "ordering")
    assert {e["name"] for e in catalog["entities"]} == {"Category", "Product"}
    assert {e["name"] for e in ordering["entities"]} == {"Order"}
```

Add `AuthSpec, ServiceDecl` to the existing `from backend.erd.schema import ...` line at the top of the test file (it currently imports `ERDConfig, ProjectMeta, DatabaseSpec, EntitySpec, RelationshipDecl, EndpointSpec` — add `AuthSpec, ServiceDecl` to that same import).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_erd_translate.py -v`
Expected: FAIL — `KeyError: 'modules'` / `KeyError: 'auth_module_name'`

- [ ] **Step 3: Implement the grouping**

Edit `backend/erd/translate.py` — add two new functions after `_resolve_rbac` and before `translate()`:

```python
def _resolve_auth_module_name(erd: ERDConfig) -> str:
    for svc in erd.services:
        if svc.entities == ["User"]:
            return svc.name
    return "auth"


def _resolve_modules(erd: ERDConfig, crud_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_name = {e["name"]: e for e in crud_entities}
    modules: List[Dict[str, Any]] = []
    for svc in erd.services:
        if svc.entities == ["User"]:
            continue  # the auth service is resolved separately via auth_module_name
        modules.append({
            "name": svc.name,
            "snake_name": _snake_case(svc.name),
            "entities": [by_name[name] for name in svc.entities],
        })
    return modules
```

In `translate()`, after the existing `crud_entities` list is fully built (right after its `for entity in entities:` loop, before the `security_config` block), add:

```python
    modules = _resolve_modules(erd, crud_entities)
    auth_module_name = _resolve_auth_module_name(erd)
```

And add both to the returned dict (alongside the existing `"crud_entities": crud_entities,` line, which stays unchanged):

```python
        "modules": modules,
        "auth_module_name": auth_module_name,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_erd_translate.py -v`
Expected: PASS (all — the 4 new tests plus every pre-existing one, since `crud_entities` and everything else is untouched)

Run the full suite too: `uv run pytest backend/tests/ -v` — should still be fully green (nothing yet consumes the new `modules`/`auth_module_name` keys, so no other behavior changes).

- [ ] **Step 5: Commit**

```bash
git add backend/erd/translate.py backend/tests/test_erd_translate.py
git commit -m "feat: group entities into modules and resolve the auth module name in translate()"
```

---

### Task 4: Regular-entity module generation

**Files:**
- Create: `backend/templates/Python/service/module_schemas.py.jinja`
- Create: `backend/templates/Python/service/module_routes.py.jinja`
- Create: `backend/templates/Python/service/module_service.py.jinja`
- Delete: `backend/templates/Python/service/crud_schemas.py.jinja`
- Delete: `backend/templates/Python/service/crud_routes.py.jinja`
- Modify: `backend/services/code_generator.py`
- Modify: `backend/templates/Python/server.py.jinja`
- Modify: `backend/erd/translate.py` (remove `crud_entities`)
- Modify: `backend/tests/test_erd_translate.py` (3 assertions)
- Rewrite: `backend/tests/test_crud_generation.py`
- Modify: `backend/tests/test_server_wiring.py` (entity assertions only)
- Modify: `backend/tests/test_cli_generate.py` (1 path assertion)
- Modify: `backend/tests/test_end_to_end.py` (entity path assertions only)

**Interfaces:**
- Consumes: `state['modules']` (Task 3) — `[{name, snake_name, entities: [{name, snake_name, plural_snake, base_path, tags, enabled_actions, rbac, fields}, ...]}]`.
- Produces: for each module, `<output>/modules/<snake_name>/{__init__.py, schemas.py, routes.py, service.py}` — consumed by Task 5 (auth follows the same directory convention) and Task 6 (end-to-end verification).
- After this task, `state['crud_entities']` no longer exists — this task is the point where its last consumer (`code_generator.py`'s old per-entity loop) is deleted, so it's removed from `translate()`'s return dict in the same commit.

- [ ] **Step 1: Write the failing tests**

Replace the entire content of `backend/tests/test_crud_generation.py`:

```python
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_module_schemas_and_routes_for_every_entity_in_the_service(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")  # services: [{name: catalog, entities: [Category, Product]}]
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_file = codebase_dir / "modules" / "catalog" / "schemas.py"
    routes_file = codebase_dir / "modules" / "catalog" / "routes.py"
    service_file = codebase_dir / "modules" / "catalog" / "service.py"
    assert schemas_file.exists()
    assert routes_file.exists()
    assert service_file.exists()
    assert (codebase_dir / "modules" / "__init__.py").exists()
    assert (codebase_dir / "modules" / "catalog" / "__init__.py").exists()

    schemas_src = schemas_file.read_text(encoding="utf-8")
    ast.parse(schemas_src)
    assert "class ProductCreate(BaseModel):" in schemas_src
    assert "class ProductResponse(BaseModel):" in schemas_src
    assert "class CategoryCreate(BaseModel):" in schemas_src
    assert "class CategoryResponse(BaseModel):" in schemas_src

    service_src = service_file.read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "class CatalogService:" in service_src
    assert "def create_product(self, db: Session, data: dict)" in service_src
    assert "def create_category(self, db: Session, data: dict)" in service_src
    assert "def get_catalog_service()" in service_src

    routes_src = routes_file.read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "from .service import CatalogService, get_catalog_service" in routes_src
    assert '"/products"' in routes_src
    assert '"/categories"' in routes_src
    assert "def delete_product_route" in routes_src
    assert "service.create_product(db, payload.model_dump())" in routes_src


def test_multiple_services_produce_separate_module_directories(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # catalog: [Category, Product], ordering: [Order]
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert (codebase_dir / "modules" / "catalog" / "routes.py").exists()
    assert (codebase_dir / "modules" / "ordering" / "routes.py").exists()

    ordering_routes = (codebase_dir / "modules" / "ordering" / "routes.py").read_text(encoding="utf-8")
    ast.parse(ordering_routes)
    assert '"/orders"' in ordering_routes


def test_rbac_dependency_only_imported_when_rbac_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")  # rbac disabled
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "widgets" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "from rbac import require_roles" not in routes_src
```

Update `backend/tests/test_erd_translate.py` — three changes:

1. In `test_translate_minimal`, replace:
```python
    entity = state["crud_entities"][0]
```
with:
```python
    entity = state["modules"][0]["entities"][0]
```

2. In `test_translate_full_injects_user_and_relationships`, replace:
```python
    product_entity = next(e for e in state["crud_entities"] if e["name"] == "Product")
```
with:
```python
    catalog_module = next(m for m in state["modules"] if m["name"] == "catalog")
    product_entity = next(e for e in catalog_module["entities"] if e["name"] == "Product")
```

3. In `test_translate_field_types_are_strings_not_enums`, replace the final block:
```python
    # Check crud_entities fields as well
    product_entity = next(e for e in state["crud_entities"] if e["name"] == "Product")
    for field in product_entity["fields"]:
        assert isinstance(field["type"], str), (
            f"CRUD entity field {field['name']} type should be string, got {type(field['type']).__name__}"
        )
```
with:
```python
    # Check module-grouped entity fields as well
    catalog_module = next(m for m in state["modules"] if m["name"] == "catalog")
    product_entity = next(e for e in catalog_module["entities"] if e["name"] == "Product")
    for field in product_entity["fields"]:
        assert isinstance(field["type"], str), (
            f"Module entity field {field['name']} type should be string, got {type(field['type']).__name__}"
        )
```

Update `backend/tests/test_server_wiring.py` — replace the whole file:

```python
# backend/tests/test_server_wiring.py
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_server_imports_and_mounts_module_and_auth_routers(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    ast.parse(server_src)

    assert "from modules.catalog.routes import router as catalog_router" in server_src
    assert "app.include_router(catalog_router)" in server_src
    # Auth wiring is still the OLD `auth/` path at this point in the plan — Task 5 moves it.
    assert "from auth.routes import router as auth_router" in server_src
    assert 'app.include_router(auth_router, prefix="/auth"' in server_src


def test_server_skips_module_and_auth_blocks_when_absent(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    ast.parse(server_src)
    assert "from modules.widgets.routes import router as widgets_router" in server_src
    assert "from auth.routes import router as auth_router" not in server_src
```

Update `backend/tests/test_cli_generate.py` — in `test_generate_writes_codebase_and_reports_path`, replace:
```python
    assert (tmp_path / "Demo" / "codebase" / "widgets" / "routes.py").exists()
```
with:
```python
    assert (tmp_path / "Demo" / "codebase" / "modules" / "widgets" / "routes.py").exists()
```

Update `backend/tests/test_end_to_end.py` — in `test_shophub_mini_generates_a_complete_working_tree`, replace the `expected_files` list:
```python
    expected_files = [
        "server.py",
        "config.py",
        "database/models.py",
        "database/repo.py",
        "database/base.py",
        "categories/routes.py",
        "categories/schemas.py",
        "products/routes.py",
        "products/schemas.py",
        "orders/routes.py",
        "orders/schemas.py",
        "auth/routes.py",
        "auth/service.py",
        "auth/schemas.py",
        "rbac.py",
        "alembic.ini",
        "alembic/env.py",
        "requirements.txt",
    ]
```
with:
```python
    expected_files = [
        "server.py",
        "config.py",
        "database/models.py",
        "database/repo.py",
        "database/base.py",
        "modules/catalog/routes.py",
        "modules/catalog/schemas.py",
        "modules/catalog/service.py",
        "modules/ordering/routes.py",
        "modules/ordering/schemas.py",
        "modules/ordering/service.py",
        "auth/routes.py",
        "auth/service.py",
        "auth/schemas.py",
        "rbac.py",
        "alembic.ini",
        "alembic/env.py",
        "requirements.txt",
    ]
```
(auth stays at the old `auth/` path in this task's expected output — Task 5 moves it and updates this list again)

And replace:
```python
    products_routes_src = (codebase_dir / "products" / "routes.py").read_text(encoding="utf-8")
    assert "from rbac import require_roles" in products_routes_src
    assert 'require_roles("admin")' in products_routes_src
```
with:
```python
    catalog_routes_src = (codebase_dir / "modules" / "catalog" / "routes.py").read_text(encoding="utf-8")
    assert "from rbac import require_roles" in catalog_routes_src
    assert 'require_roles("admin")' in catalog_routes_src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_crud_generation.py backend/tests/test_erd_translate.py backend/tests/test_server_wiring.py backend/tests/test_cli_generate.py backend/tests/test_end_to_end.py -v`
Expected: FAIL — `jinja2.exceptions.TemplateNotFound: Python/service/module_schemas.py.jinja` (and `KeyError: 'crud_entities'` will NOT yet occur since `crud_entities` still exists at this point — the failures should all be about the new `modules/` paths/templates not existing yet)

- [ ] **Step 3: Implement the new templates and wiring**

Create `backend/templates/Python/service/module_schemas.py.jinja`:

```jinja
"""{{ project.name }} - {{ module.name }} schemas (auto-generated CRUD)"""

from typing import Any, Optional
from datetime import date, datetime
from pydantic import BaseModel

{% for entity in module.entities %}

class {{ entity.name }}Create(BaseModel):
    """Fields required to create a {{ entity.name }}."""
{% for field in entity.fields %}
{% if not field.primary_key %}
    {{ field.name }}: {% if field.nullable %}Optional[{{ get_python_type(field.type) }}]{% else %}{{ get_python_type(field.type) }}{% endif %}{% if field.default is not none %} = {{ field.default|python_value }}{% elif field.nullable %} = None{% endif %}
{% endif %}
{% endfor %}
{% if entity.fields|rejectattr('primary_key')|list|length == 0 %}
    pass
{% endif %}


class {{ entity.name }}Update(BaseModel):
    """Fields that may be updated on a {{ entity.name }} (all optional)."""
{% for field in entity.fields %}
{% if not field.primary_key %}
    {{ field.name }}: Optional[{{ get_python_type(field.type) }}] = None
{% endif %}
{% endfor %}
{% if entity.fields|rejectattr('primary_key')|list|length == 0 %}
    pass
{% endif %}


class {{ entity.name }}Response(BaseModel):
    """{{ entity.name }} as returned by the API."""
{% for field in entity.fields %}
    {{ field.name }}: {% if field.nullable and not field.primary_key %}Optional[{{ get_python_type(field.type) }}]{% else %}{{ get_python_type(field.type) }}{% endif %} = None
{% endfor %}

    class Config:
        from_attributes = True
{% endfor %}
```

Create `backend/templates/Python/service/module_service.py.jinja`:

```jinja
"""{{ project.name }} - {{ module.name }} service"""

from typing import List, Optional
from sqlalchemy.orm import Session

from database import repo
from database.models import (
{% for entity in module.entities %}
    {{ entity.name }},
{% endfor %}
)


class {{ module.name|pascal_case }}Service:
    """{{ module.name|pascal_case }}Service - business logic for {{ module.entities|map(attribute='name')|join(', ') }}.

    Singleton: constructed once per process (see get_{{ module.snake_name }}_service below).
    Do not store per-request state on self (e.g. the current user, request data) --
    pass it as a method parameter instead, or it will leak across concurrent requests
    sharing this same instance.
    """

    def __init__(self) -> None:
        pass

{% for entity in module.entities %}
    def create_{{ entity.snake_name }}(self, db: Session, data: dict) -> {{ entity.name }}:
        return repo.create_{{ entity.snake_name }}(db, data)

    def list_{{ entity.snake_name }}s(self, db: Session, skip: int = 0, limit: int = 100) -> List[{{ entity.name }}]:
        return repo.get_all_{{ entity.snake_name }}s(db, skip=skip, limit=limit)

    def get_{{ entity.snake_name }}(self, db: Session, item_id: int) -> Optional[{{ entity.name }}]:
        return repo.get_{{ entity.snake_name }}_by_id(db, item_id)

    def update_{{ entity.snake_name }}(self, db: Session, item_id: int, data: dict) -> Optional[{{ entity.name }}]:
        return repo.update_{{ entity.snake_name }}(db, item_id, data)

    def delete_{{ entity.snake_name }}(self, db: Session, item_id: int) -> bool:
        return repo.delete_{{ entity.snake_name }}(db, item_id)

{% endfor %}

_{{ module.snake_name }}_service_instance: Optional["{{ module.name|pascal_case }}Service"] = None


def get_{{ module.snake_name }}_service() -> "{{ module.name|pascal_case }}Service":
    global _{{ module.snake_name }}_service_instance
    if _{{ module.snake_name }}_service_instance is None:
        _{{ module.snake_name }}_service_instance = {{ module.name|pascal_case }}Service()
    return _{{ module.snake_name }}_service_instance
```

Create `backend/templates/Python/service/module_routes.py.jinja`:

```jinja
"""{{ project.name }} - {{ module.name }} routes (auto-generated CRUD)"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database.base import get_db
from .schemas import (
{% for entity in module.entities %}
    {{ entity.name }}Create, {{ entity.name }}Response, {{ entity.name }}Update,
{% endfor %}
)
from .service import {{ module.name|pascal_case }}Service, get_{{ module.snake_name }}_service
{% if project.rbac_enabled %}
from rbac import require_roles
{% endif %}

router = APIRouter()

{% for entity in module.entities %}
{% if 'create' in entity.enabled_actions %}
@router.post(
    "{{ entity.base_path }}",
    response_model={{ entity.name }}Response,
    status_code=status.HTTP_201_CREATED,
    summary="Create {{ entity.name }}",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac.create %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.create %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def create_{{ entity.snake_name }}_route(
    payload: {{ entity.name }}Create,
    db: Session = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> {{ entity.name }}Response:
    return service.create_{{ entity.snake_name }}(db, payload.model_dump())
{% endif %}

{% if 'list' in entity.enabled_actions %}
@router.get(
    "{{ entity.base_path }}",
    response_model=List[{{ entity.name }}Response],
    summary="List {{ entity.name }} records",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac.list %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.list %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def list_{{ entity.snake_name }}_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> List[{{ entity.name }}Response]:
    return service.list_{{ entity.snake_name }}s(db, skip=skip, limit=limit)
{% endif %}

{% if 'read' in entity.enabled_actions %}
@router.get(
    "{{ entity.base_path }}/{item_id}",
    response_model={{ entity.name }}Response,
    summary="Get {{ entity.name }} by id",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac.read %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.read %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def get_{{ entity.snake_name }}_route(
    item_id: int,
    db: Session = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> {{ entity.name }}Response:
    item = service.get_{{ entity.snake_name }}(db, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{{ entity.name }} not found")
    return item
{% endif %}

{% if 'update' in entity.enabled_actions %}
@router.put(
    "{{ entity.base_path }}/{item_id}",
    response_model={{ entity.name }}Response,
    summary="Update {{ entity.name }}",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac.update %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.update %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def update_{{ entity.snake_name }}_route(
    item_id: int,
    payload: {{ entity.name }}Update,
    db: Session = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> {{ entity.name }}Response:
    item = service.update_{{ entity.snake_name }}(db, item_id, payload.model_dump(exclude_unset=True))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{{ entity.name }} not found")
    return item
{% endif %}

{% if 'delete' in entity.enabled_actions %}
@router.delete(
    "{{ entity.base_path }}/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete {{ entity.name }}",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac.delete %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.delete %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def delete_{{ entity.snake_name }}_route(
    item_id: int,
    db: Session = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> None:
    deleted = service.delete_{{ entity.snake_name }}(db, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{{ entity.name }} not found")
{% endif %}
{% endfor %}
```

Delete `backend/templates/Python/service/crud_schemas.py.jinja` and `backend/templates/Python/service/crud_routes.py.jinja`.

Edit `backend/services/code_generator.py` — replace the entire block:

```python
        # Generate auto-CRUD entity directories from an ERD (services list is separate/legacy)
        for entity in state.get('crud_entities', []):
            entity_dir = output_dir / entity['plural_snake']
            ensure_directory(entity_dir)
            (entity_dir / "__init__.py").touch()

            entity_context = {'project': state, 'entity': entity}
            self._write_file(
                entity_dir / "schemas.py",
                self._render_template("Python/service/crud_schemas.py.jinja", entity_context)
            )
            self._write_file(
                entity_dir / "routes.py",
                self._render_template("Python/service/crud_routes.py.jinja", entity_context)
            )
```

with:

```python
        # Generate one directory per service/module from an ERD
        if state.get('modules'):
            modules_dir = output_dir / "modules"
            ensure_directory(modules_dir)
            (modules_dir / "__init__.py").touch()

        for module in state.get('modules', []):
            module_dir = output_dir / "modules" / module['snake_name']
            ensure_directory(module_dir)
            (module_dir / "__init__.py").touch()

            module_context = {'project': state, 'module': module}
            self._write_file(
                module_dir / "schemas.py",
                self._render_template("Python/service/module_schemas.py.jinja", module_context)
            )
            self._write_file(
                module_dir / "service.py",
                self._render_template("Python/service/module_service.py.jinja", module_context)
            )
            self._write_file(
                module_dir / "routes.py",
                self._render_template("Python/service/module_routes.py.jinja", module_context)
            )
```

Edit `backend/templates/Python/server.py.jinja` — replace:

```jinja
{% if project.crud_entities %}
{% for entity in project.crud_entities %}
from {{ entity.plural_snake }}.routes import router as {{ entity.plural_snake }}_router
{% endfor %}
{% endif %}
```

with:

```jinja
{% if project.modules %}
{% for module in project.modules %}
from modules.{{ module.snake_name }}.routes import router as {{ module.snake_name }}_router
{% endfor %}
{% endif %}
```

and replace:

```jinja
{% if project.crud_entities %}
{% for entity in project.crud_entities %}
app.include_router({{ entity.plural_snake }}_router, prefix="{{ entity.base_path }}", tags={{ entity.tags|tojson }})
{% endfor %}
{% endif %}
```

with:

```jinja
{% if project.modules %}
{% for module in project.modules %}
app.include_router({{ module.snake_name }}_router)
{% endfor %}
{% endif %}
```

(No `prefix=`/`tags=` at the `include_router` level anymore — each entity's own `base_path`/`tags` are now baked directly into its route decorators in `module_routes.py.jinja`, since a single module's router can contain entities with different base paths/tags.)

Do **not** touch the `{% if project.auth_enabled %}` blocks in `server.py.jinja` in this task — auth still lives at the old `auth/` path until Task 5.

Finally, edit `backend/erd/translate.py` to remove the now-dead `crud_entities` key from the returned dict — delete this line from the `return { ... }` block:

```python
        "crud_entities": crud_entities,
```

The local variable `crud_entities` itself stays (it's still used to build `modules` via `_resolve_modules(erd, crud_entities)` a few lines earlier) — only the dict *key* in the return value is removed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_crud_generation.py backend/tests/test_erd_translate.py backend/tests/test_server_wiring.py backend/tests/test_cli_generate.py backend/tests/test_end_to_end.py -v`
Expected: PASS (all)

Run the full suite: `uv run pytest backend/tests/ -v` — should be fully green. `test_auth_generation.py` and the auth half of `test_server_wiring.py`/`test_end_to_end.py` should still pass unmodified since auth generation is untouched in this task.

- [ ] **Step 5: Commit**

```bash
git add backend/templates/Python/service/module_schemas.py.jinja backend/templates/Python/service/module_routes.py.jinja backend/templates/Python/service/module_service.py.jinja backend/services/code_generator.py backend/templates/Python/server.py.jinja backend/erd/translate.py backend/tests/test_erd_translate.py backend/tests/test_crud_generation.py backend/tests/test_server_wiring.py backend/tests/test_cli_generate.py backend/tests/test_end_to_end.py
git rm backend/templates/Python/service/crud_schemas.py.jinja backend/templates/Python/service/crud_routes.py.jinja
git commit -m "feat: generate entity CRUD grouped by service under modules/, with a singleton service class per module"
```

---

### Task 5: Auth restructuring — class, singleton, moved under modules/

**Files:**
- Modify: `backend/templates/Python/auth/service.py.jinja`
- Modify: `backend/templates/Python/auth/routes.py.jinja`
- Modify: `backend/templates/Python/rbac/dependency.py.jinja`
- Modify: `backend/services/code_generator.py`
- Modify: `backend/templates/Python/server.py.jinja`
- Modify: `backend/tests/test_auth_generation.py`
- Modify: `backend/tests/test_server_wiring.py` (auth assertions)
- Modify: `backend/tests/test_end_to_end.py` (auth paths)

**Interfaces:**
- Consumes: `state['auth_module_name']` (Task 3).
- Produces: `<output>/modules/<auth_module_name>/{__init__.py, schemas.py, service.py, routes.py}` instead of `<output>/auth/...`; `AuthService` class + `get_<auth_module_name>_service()` singleton factory, with `get_current_user` as a bound method on it.

- [ ] **Step 1: Write the failing tests**

Replace the entire content of `backend/tests/test_auth_generation.py`:

```python
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_auth_module_when_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    auth_dir = codebase_dir / "modules" / "auth"
    for filename in ("schemas.py", "service.py", "routes.py"):
        path = auth_dir / filename
        assert path.exists()
        ast.parse(path.read_text(encoding="utf-8"))
    assert (auth_dir / "__init__.py").exists()
    assert not (codebase_dir / "auth").exists()  # old location must be gone

    service_src = (auth_dir / "service.py").read_text(encoding="utf-8")
    assert "class AuthService:" in service_src
    assert "def register_user(self, db: Session" in service_src
    assert "def authenticate_user(self, db: Session" in service_src
    assert "async def get_current_user(self" in service_src
    assert "def get_auth_service()" in service_src

    routes_src = (auth_dir / "routes.py").read_text(encoding="utf-8")
    assert '"/register"' in routes_src
    assert '"/login"' in routes_src
    assert '"/me"' in routes_src
    assert "_service = get_auth_service()" in routes_src
    assert "_service.register_user(" in routes_src

    # /refresh must take the token in the request body, not a bare query param.
    assert "payload: RefreshRequest" in routes_src
    assert "def refresh(refresh_token: str" not in routes_src

    schemas_src = (auth_dir / "schemas.py").read_text(encoding="utf-8")
    assert "class RefreshRequest(BaseModel):" in schemas_src

    requirements_src = (codebase_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "bcrypt==4.0.1" in requirements_src
    assert "email-validator" in requirements_src


def test_no_auth_module_when_disabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert not (codebase_dir / "modules" / "auth").exists()
    assert not (codebase_dir / "auth").exists()


def test_renamed_auth_service_uses_its_own_name(tmp_path):
    from backend.erd.schema import (
        ERDConfig, ProjectMeta, DatabaseSpec, AuthSpec, EntitySpec, ServiceDecl,
    )
    from backend.schemas.data import ModelField, FieldType

    erd = ERDConfig(
        project=ProjectMeta(name="Demo", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="demo.db"),
        auth=AuthSpec(enabled=True),
        entities=[
            EntitySpec(name="Widget", fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]),
        ],
        services=[
            ServiceDecl(name="widgets", entities=["Widget"]),
            ServiceDecl(name="identity", entities=["User"]),
        ],
    )
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert (codebase_dir / "modules" / "identity" / "service.py").exists()
    assert not (codebase_dir / "modules" / "auth").exists()

    service_src = (codebase_dir / "modules" / "identity" / "service.py").read_text(encoding="utf-8")
    assert "def get_identity_service()" in service_src

    routes_src = (codebase_dir / "modules" / "identity" / "routes.py").read_text(encoding="utf-8")
    assert "get_identity_service" in routes_src
```

Update `backend/tests/test_server_wiring.py` — in `test_server_imports_and_mounts_module_and_auth_routers`, replace:
```python
    # Auth wiring is still the OLD `auth/` path at this point in the plan — Task 5 moves it.
    assert "from auth.routes import router as auth_router" in server_src
    assert 'app.include_router(auth_router, prefix="/auth"' in server_src
```
with:
```python
    assert "from modules.auth.routes import router as auth_router" in server_src
    assert 'app.include_router(auth_router, prefix="/auth"' in server_src
```

And in `test_server_skips_module_and_auth_blocks_when_absent`, replace:
```python
    assert "from auth.routes import router as auth_router" not in server_src
```
with:
```python
    assert "from modules.auth.routes import router as auth_router" not in server_src
```

Update `backend/tests/test_end_to_end.py` — in the `expected_files` list from Task 4, replace:
```python
        "auth/routes.py",
        "auth/service.py",
        "auth/schemas.py",
```
with:
```python
        "modules/auth/routes.py",
        "modules/auth/service.py",
        "modules/auth/schemas.py",
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_auth_generation.py backend/tests/test_server_wiring.py backend/tests/test_end_to_end.py -v`
Expected: FAIL — auth files still written to the old `auth/` location, `AuthService` class doesn't exist yet, `server.py` still imports from `auth.routes`

- [ ] **Step 3: Implement the class-wrapped auth service and the wiring**

Replace the content of `backend/templates/Python/auth/service.py.jinja`:

```jinja
"""{{ project.name }} - {{ project.auth_module_name }} service"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from database.base import get_db
from database.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/{{ project.auth_module_name }}/login")


class AuthService:
    """AuthService - authentication and authorization for User.

    Singleton: constructed once per process (see get_{{ project.auth_module_name }}_service below).
    Do not store per-request state on self (e.g. the current user, request data) --
    pass it as a method parameter instead, or it will leak across concurrent requests
    sharing this same instance.
    """

    def __init__(self) -> None:
        pass

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        return pwd_context.verify(plain_password, password_hash)

    def _create_token(self, subject: str, expires_delta: timedelta, token_type: str) -> str:
        expire = datetime.utcnow() + expires_delta
        return jwt.encode(
            {"sub": subject, "exp": expire, "type": token_type},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    def create_access_token(self, user_id: int) -> str:
        return self._create_token(str(user_id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")

    def create_refresh_token(self, user_id: int) -> str:
        return self._create_token(str(user_id), timedelta(days=7), "refresh")

    def register_user(self, db: Session, email: str, password: str) -> User:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise ValueError("Email already registered")

        {% if project.rbac_roles %}
        # Bootstrap convention: RBAC locks every action behind declared roles, so with
        # roles=[] nobody could ever access anything. The very first user registered
        # is granted every declared role; every subsequent registration gets roles=[]
        # (an admin/existing user must grant roles afterwards).
        is_first_user = db.query(User).count() == 0
        roles = {{ project.rbac_roles|tojson }} if is_first_user else []
        {% else %}
        roles = []
        {% endif %}

        user = User(
            email=email,
            password_hash=self.hash_password(password),
            roles=roles,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def authenticate_user(self, db: Session, email: str, password: str) -> User:
        user = db.query(User).filter(User.email == email).first()
        if not user or not self.verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")
        if not user.is_active:
            raise ValueError("User is inactive")
        return user

    def decode_token(self, token: str, expected_type: str = "access") -> int:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        subject = payload.get("sub")
        if subject is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        if payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Expected a {expected_type} token",
            )
        return int(subject)

    async def get_current_user(self, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
        user_id = self.decode_token(token, expected_type="access")
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user


_auth_service_instance: Optional["AuthService"] = None


def get_{{ project.auth_module_name }}_service() -> "AuthService":
    global _auth_service_instance
    if _auth_service_instance is None:
        _auth_service_instance = AuthService()
    return _auth_service_instance
```

Replace the content of `backend/templates/Python/auth/routes.py.jinja`:

```jinja
"""{{ project.name }} - {{ project.auth_module_name }} routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.base import get_db
from database.models import User
from .schemas import RefreshRequest, TokenResponse, UserLogin, UserRegister, UserResponse
from .service import AuthService, get_{{ project.auth_module_name }}_service

router = APIRouter()
_service = get_{{ project.auth_module_name }}_service()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> UserResponse:
    try:
        user = _service.register_user(db, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = _service.authenticate_user(db, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return TokenResponse(
        access_token=_service.create_access_token(user.id),
        refresh_token=_service.create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user_id = _service.decode_token(payload.refresh_token, expected_type="refresh")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return TokenResponse(
        access_token=_service.create_access_token(user.id),
        refresh_token=_service.create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(_service.get_current_user)) -> UserResponse:
    return current_user
```

Replace the content of `backend/templates/Python/rbac/dependency.py.jinja`:

```jinja
"""{{ project.name }} - Role-based access control"""

from typing import Callable, List

from fastapi import Depends, HTTPException, status

from modules.{{ project.auth_module_name }}.service import get_{{ project.auth_module_name }}_service
from database.models import User

_auth_service = get_{{ project.auth_module_name }}_service()


def require_roles(*roles: str) -> Callable:
    """Build a FastAPI dependency requiring the current user to have at least one of `roles`."""

    async def dependency(current_user: User = Depends(_auth_service.get_current_user)) -> User:
        user_roles: List[str] = current_user.roles or []
        if not set(user_roles) & set(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return current_user

    return dependency
```

Edit `backend/services/code_generator.py` — replace:

```python
        # Auth service (JWT register/login/refresh/me)
        if state.get('auth_enabled'):
            auth_dir = output_dir / "auth"
            ensure_directory(auth_dir)
            (auth_dir / "__init__.py").touch()
            self._write_file(auth_dir / "schemas.py", self._render_template("Python/auth/schemas.py.jinja", context))
            self._write_file(auth_dir / "service.py", self._render_template("Python/auth/service.py.jinja", context))
            self._write_file(auth_dir / "routes.py", self._render_template("Python/auth/routes.py.jinja", context))
```

with:

```python
        # Auth service (JWT register/login/refresh/me), generated as a module
        if state.get('auth_enabled'):
            ensure_directory(output_dir / "modules")
            (output_dir / "modules" / "__init__.py").touch()
            auth_dir = output_dir / "modules" / state['auth_module_name']
            ensure_directory(auth_dir)
            (auth_dir / "__init__.py").touch()
            self._write_file(auth_dir / "schemas.py", self._render_template("Python/auth/schemas.py.jinja", context))
            self._write_file(auth_dir / "service.py", self._render_template("Python/auth/service.py.jinja", context))
            self._write_file(auth_dir / "routes.py", self._render_template("Python/auth/routes.py.jinja", context))
```

(The `ensure_directory(output_dir / "modules")` + `__init__.py` touch here is safe to repeat even if the earlier regular-modules block already did it — both are idempotent.)

Edit `backend/templates/Python/server.py.jinja` — replace:

```jinja
{% if project.auth_enabled %}
from auth.routes import router as auth_router
{% endif %}
```

with:

```jinja
{% if project.auth_enabled %}
from modules.{{ project.auth_module_name }}.routes import router as auth_router
{% endif %}
```

and replace:

```jinja
{% if project.auth_enabled %}
app.include_router(auth_router, prefix="/auth", tags=["auth"])
{% endif %}
```

with:

```jinja
{% if project.auth_enabled %}
app.include_router(auth_router, prefix="/{{ project.auth_module_name }}", tags=["{{ project.auth_module_name }}"])
{% endif %}
```

(Route prefix now follows the resolved auth module name — `/auth` by default, or `/identity` etc. if renamed — rather than a hardcoded `/auth` string, matching the `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/{{ project.auth_module_name }}/login")` in the service template above.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_auth_generation.py backend/tests/test_server_wiring.py backend/tests/test_end_to_end.py -v`
Expected: PASS (all)

Run the full suite: `uv run pytest backend/tests/ -v` — should be fully green, including `test_rbac_generation.py` (unmodified, should still pass since it only checks `rbac.py` exists and contains `def require_roles(`) and `test_cli_generate.py` (unmodified, its `.env`-related assertions are unaffected by the auth output path change).

- [ ] **Step 5: Commit**

```bash
git add backend/templates/Python/auth/service.py.jinja backend/templates/Python/auth/routes.py.jinja backend/templates/Python/rbac/dependency.py.jinja backend/services/code_generator.py backend/templates/Python/server.py.jinja backend/tests/test_auth_generation.py backend/tests/test_server_wiring.py backend/tests/test_end_to_end.py
git commit -m "feat: wrap auth in a class+singleton and move it under modules/"
```

---

### Task 6: End-to-end verification — multi-service, cross-service relationships, real runtime

**Files:**
- Modify: `backend/tests/test_end_to_end.py` (add a cross-service relationship check)
- Verify (no source changes expected): `backend/tests/test_generated_project_runtime.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: confirmation that the full restructuring works end to end, including the one architectural claim not yet directly exercised — that `database/models.py` correctly wires a relationship between two entities in *different* services (services are a generation-output/organizational concept only, not a data-modeling boundary).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_end_to_end.py`:

```python
def test_shophub_mini_relationship_crosses_service_boundary(tmp_path):
    """Order lives in the 'ordering' service, Product lives in 'catalog' — the
    FK/relationship between them must still be wired correctly in the shared,
    global database/models.py regardless of which service either entity belongs to.
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    ast.parse(models_src)

    order_class_start = models_src.index("class Order(Base):")
    next_class_start = models_src.index("\nclass ", order_class_start + 1)
    order_class_src = models_src[order_class_start:next_class_start]

    assert "product_id" in order_class_src
    assert 'ForeignKey(\'products.id\')' in order_class_src or 'ForeignKey("products.id")' in order_class_src
    assert "product = relationship(" in order_class_src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_end_to_end.py -v`
Expected: at this point in the plan (Tasks 1-5 already implemented and merged), this should most likely already PASS on the first run — `database/models.py` generation was never touched by Tasks 1-5 (only entity/auth *route/schema/service* generation and their output paths changed; `models.py.jinja` and the relationship-building logic in `translate.py` were left alone). If it fails, treat it as a genuine remaining bug (most likely in how `_resolve_modules`/`_build_relationship` interact for cross-module entities) and debug it — do not weaken the assertions to make it pass.

- [ ] **Step 3: Fix any real issue found, or confirm pass**

If Step 2 already passes, skip to Step 4. If it fails, the most likely cause is unrelated to this plan's actual changes (relationship-building in `translate.py`'s `_build_relationship`/`_validate_relationship_uniqueness` doesn't know or care about service assignment at all, by design), so investigate whether the `shophub_mini.yml` fixture's `Order.user`/`Order.product` relationships are declared correctly first before suspecting the module-grouping code.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest backend/tests/ -v`
Expected: PASS (all — this now includes `test_generated_project_runtime.py`'s two runtime tests, which should pass **unmodified**: `_top_level_module_names()` generically discovers `modules/` as one more top-level package directory via `codebase_dir.iterdir()`, so its stale-import-purging logic already handles the new structure without any code changes. Confirm this rather than assume it — if either runtime test fails, that's a real gap to fix, most likely in `_top_level_module_names()` needing to recurse into `modules/*` for sub-package purging rather than just the top level.)

Also manually confirm no stray old-path artifacts remain: `uv run python -c "from backend.erd.loader import load_erd; from backend.erd.translate import translate; from backend.services.code_generator import CodeGenerator; import tempfile; erd = load_erd('backend/tests/fixtures/erd/shophub_mini.yml'); state = translate(erd); tmp = tempfile.mkdtemp(); codebase = CodeGenerator(output_dir=tmp).generate_project(state, force=True); import os; print([p for p in os.listdir(codebase) if p in ('categories', 'products', 'orders', 'auth')])"` — expected output: `[]` (none of the old per-entity/auth directories exist any more; everything lives under `modules/`).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_end_to_end.py
git commit -m "test: verify relationships stay correctly wired across service boundaries"
```

---

## Self-Review Notes

- **Spec coverage:** §3 (YAML schema + validation) → Tasks 1-2; §4 (folder structure, path-baking) → Task 4; §5 (service class, singleton, auth special-casing) → Tasks 4-5; §6 (one-shot regeneration — no code change needed, it's the *absence* of preservation logic, confirmed unchanged from before this plan) → no task needed, already true; §7 (implementation-level translation changes) → Tasks 3-5 collectively; §8 (RBAC unaffected, async/RLS/Spec 2 deferred) → nothing implemented for these, as intended.
- **Placeholder scan:** no TODO/TBD in any task; every template is complete, working code (not stubs) matching the "works out of the box" requirement from the spec.
- **Type/name consistency checked:** `state['modules'][i]` shape (`name, snake_name, entities`) defined in Task 3 matches exactly what Task 4's `code_generator.py` changes and `module_*.jinja` templates consume. `state['auth_module_name']` defined in Task 3 matches exactly what Task 5's `code_generator.py`/`server.py.jinja`/`auth/*.jinja` changes consume. The `crud_entity` dict shape embedded in each module's `entities` list is untouched from its pre-existing shape (Task 3 explicitly reuses it via `_resolve_modules`), so no drift between what Task 4's templates expect (`entity.snake_name`, `entity.base_path`, `entity.rbac.create`, etc.) and what Task 3 actually produces.
- **Sequencing verified for green-suite-after-every-task discipline:** Task 3 is purely additive (old `crud_entities` untouched). Task 4 removes `crud_entities` and switches entity generation to `modules`, while explicitly leaving auth generation at its old `auth/` location untouched (verified by checking `test_auth_generation.py`/the auth half of `test_server_wiring.py`/`test_end_to_end.py` don't move until Task 5, whose scope is auth-only). No task leaves the suite red for a later task to fix.
