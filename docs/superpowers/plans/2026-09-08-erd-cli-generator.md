# ERD-driven CLI Code Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `backstudio` CLI that reads a YAML ERD file and generates a working FastAPI backend (SQLAlchemy models, generic repo CRUD, an auto-generated CRUD REST API per entity, an optional JWT auth service, RBAC enforcement, and Alembic scaffolding), plus a pre-generation HTML ERD visualization — all built on top of the existing `backend/services/code_generator.py` engine and Jinja2 templates.

**Architecture:** New `backend/erd/` package parses and validates the YAML into a Pydantic `ERDConfig`, then translates it into the same state-dict shape `CodeGenerator.generate_project()` already consumes. New `backend/cli/` package (Typer) exposes `validate` / `visualize` / `generate` commands. New Jinja2 templates add auto-generated (non-stub) CRUD schemas/routes, a JWT auth service, and an RBAC dependency; `server.py.jinja` gets small additive blocks to wire the new routers in. The existing REST API (`backend/api/routes.py`), `frontend/`, and `mcp_server/` are untouched.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (sync), Pydantic v2, Jinja2, Typer, PyYAML, passlib[bcrypt], python-jose, Alembic, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-erd-cli-design.md`

## Global Constraints

- Generated projects use **sync SQLAlchemy** (`Session`, `db.query(...)`) — no async engine work.
- `database.type` in the ERD YAML is restricted to `postgresql | mysql | sqlite`.
- The Alembic `revision --autogenerate` step in `generate` is **best-effort**: on failure it prints a warning and continues; it never fails the command.
- `frontend/`, `mcp_server/`, and `backend/api/routes.py` are not modified.
- Reuse the existing `CodeGenerator`, `database/base.py.jinja`, `database/models.py.jinja`, and `database/repo.py.jinja` templates unchanged — new work is additive.
- `rbac.enabled: true` requires `auth.enabled: true` in the ERD (RBAC has no meaning without a way to identify the current user) — enforced as a validation error, not stated verbatim in the spec but required for the RBAC design in §3/§5 of the spec to be sound.

---

## File Structure

```
backend/
  erd/
    __init__.py
    schema.py        # ERDConfig and nested Pydantic models
    loader.py         # YAML -> ERDConfig, validation
    translate.py       # ERDConfig -> CodeGenerator state dict
    visualize.py        # ERDConfig -> Mermaid/HTML
  cli/
    __init__.py
    main.py            # Typer app: validate / visualize / generate
  services/
    code_generator.py  # MODIFIED: new generation branches
  templates/Python/
    service/
      crud_schemas.py.jinja   # NEW
      crud_routes.py.jinja     # NEW
    auth/
      schemas.py.jinja          # NEW
      service.py.jinja           # NEW
      routes.py.jinja              # NEW
    rbac/
      dependency.py.jinja           # NEW
    alembic/
      alembic.ini.jinja               # NEW
      env.py.jinja                     # NEW
    server.py.jinja    # MODIFIED: additive router wiring
  tests/
    __init__.py
    fixtures/erd/        # sample .yml fixtures used across tasks
    test_cli_skeleton.py
    test_erd_schema.py
    test_erd_loader.py
    test_erd_translate.py
    test_cli_validate.py
    test_erd_visualize.py
    test_cli_visualize.py
    test_crud_generation.py
    test_rbac_generation.py
    test_auth_generation.py
    test_server_wiring.py
    test_alembic_generation.py
    test_cli_generate.py
    test_end_to_end.py
pyproject.toml    # MODIFIED: new deps + [project.scripts]
```

---

### Task 1: CLI packaging skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/cli/__init__.py`
- Create: `backend/cli/main.py`
- Create: `backend/tests/__init__.py`
- Test: `backend/tests/test_cli_skeleton.py`

**Interfaces:**
- Produces: `backend.cli.main.app` — a `typer.Typer` instance every later CLI task adds commands to.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cli_skeleton.py
from typer.testing import CliRunner

from backend.cli.main import app

runner = CliRunner()


def test_cli_shows_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "backstudio" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_cli_skeleton.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.cli'`

- [ ] **Step 3: Add dependencies and the CLI entry point**

Edit `pyproject.toml` — add to `[project] dependencies` and add `[project.scripts]`:

```toml
dependencies = [
    "fastapi==0.104.1",
    "uvicorn[standard]==0.24.0",
    "pydantic==2.5.0",
    "pydantic-settings==2.1.0",
    "jinja2==3.1.2",
    "python-multipart==0.0.6",
    "typer==0.9.0",
    "pyyaml==6.0.1",
    "passlib[bcrypt]==1.7.4",
    "python-jose[cryptography]==3.3.0",
    "alembic==1.13.0",
    "sqlalchemy==2.0.23",
]

[project.scripts]
backstudio = "backend.cli.main:app"
```

Create `backend/tests/__init__.py` (empty).

Create `backend/cli/__init__.py` (empty).

Create `backend/cli/main.py`:

```python
"""BackStudio CLI entry point."""

import typer

app = typer.Typer(name="backstudio", help="Generate FastAPI backends from a YAML ERD.")


if __name__ == "__main__":
    app()
```

Install the new dependencies: run `uv sync` (or `pip install -e .` if not using uv) from the repo root.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_cli_skeleton.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml backend/cli/__init__.py backend/cli/main.py backend/tests/__init__.py backend/tests/test_cli_skeleton.py
git commit -m "feat: add backstudio CLI skeleton and new dependencies"
```

---

### Task 2: ERD schema module

**Files:**
- Create: `backend/erd/__init__.py`
- Create: `backend/erd/schema.py`
- Test: `backend/tests/test_erd_schema.py`

**Interfaces:**
- Consumes: `ModelField`, `Cardinality`, `LazyStrategy` from `backend/schemas/data.py` (existing).
- Produces: `ERDConfig`, `ProjectMeta`, `DatabaseSpec`, `CliDatabaseType`, `AuthSpec`, `JWTSpec`, `RBACSpec`, `RelationshipDecl`, `EndpointSpec`, `EndpointRBAC`, `EntitySpec`, `ALL_ACTIONS` — all consumed by Tasks 3, 4, 6.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_erd_schema.py
import pytest
from pydantic import ValidationError

from backend.erd.schema import ERDConfig, ALL_ACTIONS


MINIMAL = {
    "project": {"name": "Demo"},
    "database": {"type": "sqlite", "database_name": "demo.db"},
    "entities": [
        {
            "name": "Widget",
            "fields": [
                {"name": "id", "type": "integer", "primary_key": True},
                {"name": "label", "type": "string"},
            ],
        }
    ],
}


def test_minimal_config_parses_with_defaults():
    erd = ERDConfig(**MINIMAL)
    assert erd.project.version == "1.0.0"
    assert erd.auth.enabled is False
    assert erd.rbac.enabled is False
    assert erd.entities[0].endpoints.enabled == ALL_ACTIONS


def test_unknown_endpoint_action_rejected():
    bad = dict(MINIMAL)
    bad["entities"] = [
        {
            "name": "Widget",
            "fields": [{"name": "id", "type": "integer", "primary_key": True}],
            "endpoints": {"enabled": ["create", "explode"]},
        }
    ]
    with pytest.raises(ValidationError):
        ERDConfig(**bad)


def test_unknown_default_permission_action_rejected():
    bad = dict(MINIMAL)
    bad["rbac"] = {"enabled": True, "roles": ["admin"], "default_permissions": {"fly": ["admin"]}}
    with pytest.raises(ValidationError):
        ERDConfig(**bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_erd_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.erd'`

- [ ] **Step 3: Implement the schema**

Create `backend/erd/__init__.py` (empty).

Create `backend/erd/schema.py`:

```python
"""Pydantic schema for the YAML ERD configuration consumed by the backstudio CLI."""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.schemas.data import Cardinality, LazyStrategy, ModelField

ALL_ACTIONS = ["create", "list", "read", "update", "delete"]


class CliDatabaseType(str, Enum):
    """Database backends the CLI's SQLAlchemy code generation supports."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class ProjectMeta(BaseModel):
    name: str = Field(..., min_length=1)
    version: str = "1.0.0"
    description: Optional[str] = None


class DatabaseSpec(BaseModel):
    type: CliDatabaseType
    host: Optional[str] = "localhost"
    port: Optional[int] = None
    database_name: str
    username: Optional[str] = None
    use_env_vars: bool = True
    pool_size: int = 10
    echo: bool = False


class JWTSpec(BaseModel):
    secret_env_var: str = "JWT_SECRET"
    algorithm: str = "HS256"
    expiration_minutes: int = 30


class AuthSpec(BaseModel):
    enabled: bool = False
    jwt: JWTSpec = Field(default_factory=JWTSpec)


class RBACSpec(BaseModel):
    enabled: bool = False
    roles: List[str] = Field(default_factory=list)
    default_permissions: Dict[str, List[str]] = Field(default_factory=dict)

    @field_validator("default_permissions")
    @classmethod
    def actions_are_known(cls, v: Dict[str, List[str]]) -> Dict[str, List[str]]:
        for action in v:
            if action not in ALL_ACTIONS:
                raise ValueError(
                    f"rbac.default_permissions: unknown action '{action}' (expected one of {ALL_ACTIONS})"
                )
        return v


class RelationshipDecl(BaseModel):
    """A relationship declared from one entity to another.

    Only one side needs to declare it; `translate.py` fills in the other side.
    """
    name: str
    cardinality: Cardinality
    target: str
    attribute: Optional[str] = None
    target_attribute: Optional[str] = None
    foreign_key_column: Optional[str] = None
    nullable: bool = True
    unique: bool = False
    ondelete: Optional[str] = None
    lazy: Optional[LazyStrategy] = None
    cascade: Optional[str] = None
    association_table: Optional[str] = None


class EndpointRBAC(BaseModel):
    create: Optional[List[str]] = None
    list: Optional[List[str]] = None
    read: Optional[List[str]] = None
    update: Optional[List[str]] = None
    delete: Optional[List[str]] = None


class EndpointSpec(BaseModel):
    enabled: List[str] = Field(default_factory=lambda: list(ALL_ACTIONS))
    base_path: Optional[str] = None
    tags: Optional[List[str]] = None
    rbac: Optional[EndpointRBAC] = None

    @field_validator("enabled")
    @classmethod
    def actions_are_known(cls, v: List[str]) -> List[str]:
        for action in v:
            if action not in ALL_ACTIONS:
                raise ValueError(f"endpoints.enabled: unknown action '{action}' (expected one of {ALL_ACTIONS})")
        return v


class EntitySpec(BaseModel):
    name: str = Field(..., min_length=1)
    table_name: Optional[str] = None
    fields: List[ModelField] = Field(default_factory=list)
    relationships: List[RelationshipDecl] = Field(default_factory=list)
    endpoints: EndpointSpec = Field(default_factory=EndpointSpec)


class ERDConfig(BaseModel):
    project: ProjectMeta
    database: DatabaseSpec
    auth: AuthSpec = Field(default_factory=AuthSpec)
    rbac: RBACSpec = Field(default_factory=RBACSpec)
    entities: List[EntitySpec] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_erd_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/erd/__init__.py backend/erd/schema.py backend/tests/test_erd_schema.py
git commit -m "feat: add ERDConfig Pydantic schema for the YAML ERD format"
```

---

### Task 3: ERD loader and semantic validation

**Files:**
- Create: `backend/erd/loader.py`
- Create: `backend/tests/fixtures/erd/valid_minimal.yml`
- Create: `backend/tests/fixtures/erd/valid_full.yml`
- Test: `backend/tests/test_erd_loader.py`

**Interfaces:**
- Consumes: `ERDConfig`, `ALL_ACTIONS` from `backend.erd.schema` (Task 2).
- Produces: `load_erd(path) -> ERDConfig`, `ERDValidationError` — consumed by Tasks 5, 7, 13.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/fixtures/erd/valid_minimal.yml`:

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
```

Create `backend/tests/fixtures/erd/valid_full.yml`:

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
```

Create `backend/tests/test_erd_loader.py`:

```python
import pytest

from backend.erd.loader import ERDValidationError, load_erd

FIXTURES = "backend/tests/fixtures/erd"


def test_loads_minimal_valid_erd():
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    assert erd.project.name == "Demo"
    assert len(erd.entities) == 1


def test_loads_full_valid_erd():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    assert erd.auth.enabled is True
    assert erd.rbac.enabled is True
    assert len(erd.entities) == 2


def test_missing_file_raises():
    with pytest.raises(ERDValidationError, match="not found"):
        load_erd(f"{FIXTURES}/does_not_exist.yml")


def test_duplicate_entity_names_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
"""
    )
    with pytest.raises(ERDValidationError, match="Duplicate entity name"):
        load_erd(bad)


def test_unknown_relationship_target_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Product
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: category, cardinality: many-to-one, target: Category}
"""
    )
    with pytest.raises(ERDValidationError, match="not found among declared entities"):
        load_erd(bad)


def test_rbac_without_auth_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
rbac: {enabled: true, roles: [admin]}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
"""
    )
    with pytest.raises(ERDValidationError, match="rbac.enabled requires auth.enabled"):
        load_erd(bad)


def test_unknown_role_reference_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
rbac: {enabled: true, roles: [admin]}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
    endpoints:
      rbac: {delete: [superadmin]}
"""
    )
    with pytest.raises(ERDValidationError, match="unknown role"):
        load_erd(bad)


def test_invalid_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("project: [unterminated")
    with pytest.raises(ERDValidationError, match="Invalid YAML"):
        load_erd(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_erd_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.erd.loader'`

- [ ] **Step 3: Implement the loader**

Create `backend/erd/loader.py`:

```python
"""Load and validate a YAML ERD file into an ERDConfig."""

from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError

from backend.erd.schema import ERDConfig

RESERVED_USER_FIELDS = {"id", "email", "password_hash", "roles", "is_active", "created_at", "updated_at"}


class ERDValidationError(Exception):
    """Raised when an ERD file fails to parse or fails semantic validation."""


def load_erd(path: Union[str, Path]) -> ERDConfig:
    path = Path(path)
    if not path.exists():
        raise ERDValidationError(f"ERD file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ERDValidationError(f"Invalid YAML in {path}: {exc}") from exc

    if raw is None:
        raise ERDValidationError(f"ERD file is empty: {path}")
    if not isinstance(raw, dict):
        raise ERDValidationError(f"ERD file must contain a mapping at the top level: {path}")

    try:
        erd = ERDConfig(**raw)
    except ValidationError as exc:
        raise ERDValidationError(f"ERD schema validation failed:\n{exc}") from exc

    _validate_semantics(erd)
    return erd


def _validate_semantics(erd: ERDConfig) -> None:
    if erd.rbac.enabled and not erd.auth.enabled:
        raise ERDValidationError(
            "rbac.enabled requires auth.enabled: true (RBAC needs a way to identify the current user)"
        )

    entity_names = [e.name for e in erd.entities]
    duplicates = sorted({n for n in entity_names if entity_names.count(n) > 1})
    if duplicates:
        raise ERDValidationError(f"Duplicate entity name(s): {', '.join(duplicates)}")

    known_entities = set(entity_names) | ({"User"} if erd.auth.enabled else set())

    for entity in erd.entities:
        field_names = [f.name for f in entity.fields]
        dup_fields = sorted({n for n in field_names if field_names.count(n) > 1})
        if dup_fields:
            raise ERDValidationError(
                f"Entity '{entity.name}': duplicate field name(s): {', '.join(dup_fields)}"
            )

        if entity.name == "User" and erd.auth.enabled:
            collide = sorted(set(field_names) & RESERVED_USER_FIELDS)
            if collide:
                raise ERDValidationError(
                    f"Entity 'User': field(s) {', '.join(collide)} collide with auto-injected auth fields"
                )

        for rel in entity.relationships:
            if rel.target not in known_entities:
                raise ERDValidationError(
                    f"Entity '{entity.name}': relationship '{rel.name}' target "
                    f"'{rel.target}' not found among declared entities"
                )

        if erd.rbac.enabled and entity.endpoints.rbac is not None:
            overrides = entity.endpoints.rbac.model_dump(exclude_none=True)
            for action, roles in overrides.items():
                unknown = sorted(set(roles) - set(erd.rbac.roles))
                if unknown:
                    raise ERDValidationError(
                        f"Entity '{entity.name}': endpoints.rbac.{action} references "
                        f"unknown role(s): {', '.join(unknown)}"
                    )

    if erd.rbac.enabled:
        for action, roles in erd.rbac.default_permissions.items():
            unknown = sorted(set(roles) - set(erd.rbac.roles))
            if unknown:
                raise ERDValidationError(
                    f"rbac.default_permissions.{action} references unknown role(s): {', '.join(unknown)}"
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_erd_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/erd/loader.py backend/tests/fixtures/erd backend/tests/test_erd_loader.py
git commit -m "feat: add YAML ERD loader with semantic validation"
```

---

### Task 4: ERD to engine translation

**Files:**
- Create: `backend/erd/translate.py`
- Test: `backend/tests/test_erd_translate.py`

**Interfaces:**
- Consumes: `ERDConfig` and nested models (Task 2), fixtures from Task 3.
- Produces: `translate(erd: ERDConfig) -> dict` with keys `name, description, version, framework, checksum, data_models, relationships, services, middlewares, dependencies, database_config, security_config, crud_entities, auth_enabled, rbac_enabled, rbac_roles` — consumed by Tasks 8-13 (fed straight into `CodeGenerator.generate_project`).
- Each `crud_entities[i]` has keys: `name, snake_name, plural_snake, base_path, tags, enabled_actions, rbac (dict of action -> list[str]), fields`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_erd_translate.py
from backend.erd.loader import load_erd
from backend.erd.translate import translate

FIXTURES = "backend/tests/fixtures/erd"


def test_translate_minimal():
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    assert state["name"] == "Demo"
    assert state["framework"] == "fastapi"
    assert state["auth_enabled"] is False
    assert state["rbac_enabled"] is False
    assert [m["name"] for m in state["data_models"]] == ["Widget"]

    entity = state["crud_entities"][0]
    assert entity["name"] == "Widget"
    assert entity["plural_snake"] == "widgets"
    assert entity["base_path"] == "/widgets"
    assert entity["enabled_actions"] == ["create", "list", "read", "update", "delete"]
    assert entity["rbac"] == {a: [] for a in ["create", "list", "read", "update", "delete"]}


def test_translate_full_injects_user_and_relationships():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    model_names = {m["name"] for m in state["data_models"]}
    assert model_names == {"Category", "Product", "User"}
    assert state["auth_enabled"] is True
    assert state["rbac_enabled"] is True
    assert state["rbac_roles"] == ["admin", "editor", "viewer"]

    user_model = next(m for m in state["data_models"] if m["name"] == "User")
    user_field_names = {f["name"] for f in user_model["fields"]}
    assert {"id", "email", "password_hash", "roles", "is_active"} <= user_field_names

    product = next(m for m in state["data_models"] if m["name"] == "Product")
    assert len(product["relationships"]) == 1
    rel = product["relationships"][0]
    assert rel["foreign_key"]["model"] == "Product"
    assert rel["foreign_key"]["column"] == "category_id"
    assert rel["foreign_key"]["references"] == "category.id" or rel["foreign_key"]["references"].endswith(".id")

    category = next(m for m in state["data_models"] if m["name"] == "Category")
    assert len(category["relationships"]) == 1  # same relationship appears on both sides

    product_entity = next(e for e in state["crud_entities"] if e["name"] == "Product")
    assert product_entity["rbac"]["create"] == ["admin"]
    assert product_entity["rbac"]["delete"] == ["admin"]
    assert product_entity["rbac"]["read"] == ["admin", "editor", "viewer"]  # from rbac.default_permissions

    assert state["security_config"]["auth_strategy"] == "jwt"
    assert state["security_config"]["jwt_expiration_minutes"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_erd_translate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.erd.translate'`

- [ ] **Step 3: Implement the translator**

Create `backend/erd/translate.py`:

```python
"""Translate a validated ERDConfig into the state dict CodeGenerator.generate_project expects."""

import re
from typing import Any, Dict, List

from backend.erd.schema import ALL_ACTIONS, ERDConfig, EntitySpec, RelationshipDecl
from backend.schemas.data import ModelField

AUTH_USER_FIELDS: List[Dict[str, Any]] = [
    {"name": "id", "type": "integer", "primary_key": True, "nullable": False},
    {"name": "email", "type": "string", "unique": True, "nullable": False, "max_length": 255},
    {"name": "password_hash", "type": "string", "nullable": False, "max_length": 255},
    {"name": "roles", "type": "json", "nullable": False, "default": []},
    {"name": "is_active", "type": "boolean", "nullable": False, "default": True},
    {"name": "created_at", "type": "datetime", "nullable": False},
    {"name": "updated_at", "type": "datetime", "nullable": False},
]


def _snake_case(text: str) -> str:
    text = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text).lower()


def _pluralize(word: str) -> str:
    snake = _snake_case(word)
    if snake.endswith("y") and snake[-2:-1] not in "aeiou":
        return snake[:-1] + "ies"
    if snake.endswith(("s", "x", "z", "ch", "sh")):
        return snake + "es"
    return snake + "s"


def _table_name(erd: ERDConfig, entity_name: str) -> str:
    entity = next((e for e in erd.entities if e.name == entity_name), None)
    if entity and entity.table_name:
        return entity.table_name
    return _pluralize(entity_name)


def _build_relationship(erd: ERDConfig, entity: EntitySpec, rel: RelationshipDecl) -> Dict[str, Any]:
    entity_table = _table_name(erd, entity.name)
    target_table = _table_name(erd, rel.target)

    if rel.cardinality == "one-to-many":
        source_attribute = rel.attribute or _pluralize(rel.target)
        target_attribute = rel.target_attribute or _snake_case(entity.name)
    elif rel.cardinality == "many-to-one":
        source_attribute = rel.attribute or _snake_case(rel.target)
        target_attribute = rel.target_attribute or _pluralize(entity.name)
    elif rel.cardinality == "one-to-one":
        source_attribute = rel.attribute or _snake_case(rel.target)
        target_attribute = rel.target_attribute or _snake_case(entity.name)
    else:  # many-to-many
        source_attribute = rel.attribute or _pluralize(rel.target)
        target_attribute = rel.target_attribute or _pluralize(entity.name)

    rel_dict: Dict[str, Any] = {
        "id": rel.name,
        "name": rel.name,
        "cardinality": rel.cardinality,
        "source": {"model": entity.name, "attribute": source_attribute, "lazy": rel.lazy},
        "target": {"model": rel.target, "attribute": target_attribute},
    }

    if rel.cardinality == "many-to-many":
        table_name = rel.association_table or f"{_snake_case(entity.name)}_{_snake_case(rel.target)}"
        rel_dict["association_table"] = {
            "table_name": table_name,
            "left_foreign_key": {
                "model": entity.name,
                "column": f"{_snake_case(entity.name)}_id",
                "references": f"{entity_table}.id",
            },
            "right_foreign_key": {
                "model": rel.target,
                "column": f"{_snake_case(rel.target)}_id",
                "references": f"{target_table}.id",
            },
        }
        return rel_dict

    if rel.cardinality == "one-to-many":
        fk_model = rel.target
        fk_column = rel.foreign_key_column or f"{_snake_case(entity.name)}_id"
        fk_references = f"{entity_table}.id"
    else:  # many-to-one or one-to-one: this entity owns the FK column
        fk_model = entity.name
        fk_column = rel.foreign_key_column or f"{_snake_case(rel.target)}_id"
        fk_references = f"{target_table}.id"

    rel_dict["foreign_key"] = {
        "model": fk_model,
        "column": fk_column,
        "references": fk_references,
        "nullable": rel.nullable,
        "unique": rel.unique or rel.cardinality == "one-to-one",
        "ondelete": rel.ondelete,
    }
    if rel.cascade:
        rel_dict["behavior"] = {"cascade": rel.cascade}
    return rel_dict


def _build_user_entity(erd: ERDConfig) -> Dict[str, Any]:
    declared = next((e for e in erd.entities if e.name == "User"), None)
    fields = [dict(f) for f in AUTH_USER_FIELDS]
    if declared:
        fields.extend(f.model_dump() for f in declared.fields)
    return {"name": "User", "table_name": "users", "fields": fields, "relationships": []}


def _resolve_rbac(erd: ERDConfig, entity: EntitySpec) -> Dict[str, List[str]]:
    resolved: Dict[str, List[str]] = {}
    overrides = entity.endpoints.rbac.model_dump(exclude_none=True) if entity.endpoints.rbac else {}
    for action in ALL_ACTIONS:
        if action in overrides:
            resolved[action] = overrides[action]
        elif action in erd.rbac.default_permissions:
            resolved[action] = erd.rbac.default_permissions[action]
        elif erd.rbac.enabled:
            resolved[action] = list(erd.rbac.roles)
        else:
            resolved[action] = []
    return resolved


def translate(erd: ERDConfig) -> Dict[str, Any]:
    entities = [e for e in erd.entities if e.name != "User"]

    data_models: Dict[str, Dict[str, Any]] = {
        entity.name: {
            "name": entity.name,
            "table_name": _table_name(erd, entity.name),
            "fields": [f.model_dump() for f in entity.fields],
            "relationships": [],
        }
        for entity in entities
    }

    if erd.auth.enabled:
        data_models["User"] = _build_user_entity(erd)

    relationships: List[Dict[str, Any]] = []
    for entity in entities:
        for rel in entity.relationships:
            rel_dict = _build_relationship(erd, entity, rel)
            relationships.append(rel_dict)
            if entity.name in data_models:
                data_models[entity.name]["relationships"].append(rel_dict)
            if rel.target in data_models:
                data_models[rel.target]["relationships"].append(rel_dict)

    crud_entities: List[Dict[str, Any]] = []
    for entity in entities:
        plural_snake = _pluralize(entity.name)
        crud_entities.append({
            "name": entity.name,
            "snake_name": _snake_case(entity.name),
            "plural_snake": plural_snake,
            "base_path": entity.endpoints.base_path or f"/{plural_snake}",
            "tags": entity.endpoints.tags or [plural_snake],
            "enabled_actions": entity.endpoints.enabled,
            "rbac": _resolve_rbac(erd, entity),
            "fields": [f.model_dump() for f in entity.fields],
        })

    security_config = None
    if erd.auth.enabled:
        security_config = {
            "auth_strategy": "jwt",
            "jwt_secret_env_var": erd.auth.jwt.secret_env_var,
            "jwt_algorithm": erd.auth.jwt.algorithm,
            "jwt_expiration_minutes": erd.auth.jwt.expiration_minutes,
        }

    return {
        "name": erd.project.name,
        "description": erd.project.description,
        "version": erd.project.version,
        "framework": "fastapi",
        "checksum": "",
        "data_models": list(data_models.values()),
        "relationships": relationships,
        "services": [],
        "middlewares": [],
        "dependencies": [],
        "database_config": erd.database.model_dump(),
        "security_config": security_config,
        "crud_entities": crud_entities,
        "auth_enabled": erd.auth.enabled,
        "rbac_enabled": erd.rbac.enabled,
        "rbac_roles": erd.rbac.roles,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_erd_translate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/erd/translate.py backend/tests/test_erd_translate.py
git commit -m "feat: translate ERDConfig into CodeGenerator state dict"
```

---

### Task 5: `backstudio validate` command

**Files:**
- Modify: `backend/cli/main.py`
- Test: `backend/tests/test_cli_validate.py`

**Interfaces:**
- Consumes: `load_erd`, `ERDValidationError` from `backend.erd.loader` (Task 3).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cli_validate.py
from typer.testing import CliRunner

from backend.cli.main import app

runner = CliRunner()
FIXTURES = "backend/tests/fixtures/erd"


def test_validate_valid_file_exits_zero():
    result = runner.invoke(app, ["validate", f"{FIXTURES}/valid_full.yml"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_validate_invalid_file_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("project: [unterminated")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 1
    assert "Invalid YAML" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_cli_validate.py -v`
Expected: FAIL with a Typer "No such command 'validate'" error

- [ ] **Step 3: Add the command**

Edit `backend/cli/main.py`, replacing its contents with:

```python
"""BackStudio CLI entry point."""

from pathlib import Path

import typer

from backend.erd.loader import ERDValidationError, load_erd

app = typer.Typer(name="backstudio", help="Generate FastAPI backends from a YAML ERD.")


@app.command()
def validate(
    erd_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to the ERD YAML file")
) -> None:
    """Validate an ERD file without generating anything."""
    try:
        erd = load_erd(erd_file)
    except ERDValidationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    relationship_count = sum(len(e.relationships) for e in erd.entities)
    typer.secho(
        f"OK: {len(erd.entities)} entities, {relationship_count} relationships, "
        f"auth={'on' if erd.auth.enabled else 'off'}, rbac={'on' if erd.rbac.enabled else 'off'}",
        fg=typer.colors.GREEN,
    )


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_cli_validate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/cli/main.py backend/tests/test_cli_validate.py
git commit -m "feat: add backstudio validate command"
```

---

### Task 6: ERD visualization renderer

**Files:**
- Create: `backend/erd/visualize.py`
- Test: `backend/tests/test_erd_visualize.py`

**Interfaces:**
- Consumes: `ERDConfig` (Task 2).
- Produces: `render_mermaid(erd) -> str`, `render_html(erd) -> str` — consumed by Task 7.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_erd_visualize.py
from backend.erd.loader import load_erd
from backend.erd.visualize import render_html, render_mermaid

FIXTURES = "backend/tests/fixtures/erd"


def test_render_mermaid_includes_entities_and_relationship():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    diagram = render_mermaid(erd)

    assert "erDiagram" in diagram
    assert "Product" in diagram
    assert "Category" in diagram
    assert "User" in diagram  # auto-injected since auth is enabled
    assert "many-to-one" not in diagram  # cardinality rendered as symbols, not the word
    assert "category" in diagram  # relationship label


def test_render_html_wraps_diagram_and_loads_mermaid():
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    html = render_html(erd)

    assert "<title>Demo - ERD</title>" in html
    assert "mermaid" in html.lower()
    assert "erDiagram" in html
    assert "Widget" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_erd_visualize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.erd.visualize'`

- [ ] **Step 3: Implement the renderer**

Create `backend/erd/visualize.py`:

```python
"""Render a standalone HTML page with a Mermaid ER diagram for an ERDConfig."""

from html import escape
from typing import List

from backend.erd.schema import ERDConfig
from backend.schemas.data import ModelField

_MERMAID_TYPE_MAP = {
    "string": "string", "integer": "int", "float": "float", "boolean": "bool",
    "datetime": "datetime", "date": "date", "text": "text", "json": "json", "uuid": "uuid",
}

_CARDINALITY_SYMBOLS = {
    "one-to-many": ("||", "o{"),
    "many-to-one": ("}o", "||"),
    "one-to-one": ("||", "||"),
    "many-to-many": ("}o", "o{"),
}

_AUTH_USER_DISPLAY_FIELDS: List[ModelField] = [
    ModelField(name="id", type="integer", primary_key=True),
    ModelField(name="email", type="string", unique=True),
    ModelField(name="roles", type="json"),
]


def _entity_block(name: str, fields: List[ModelField]) -> str:
    lines = [f"    {name} {{"]
    for field in fields:
        mtype = _MERMAID_TYPE_MAP.get(str(field.type).lower(), "string")
        markers = []
        if field.primary_key:
            markers.append("PK")
        if field.unique and not field.primary_key:
            markers.append("UK")
        marker = " " + ",".join(markers) if markers else ""
        lines.append(f"        {mtype} {field.name}{marker}")
    lines.append("    }")
    return "\n".join(lines)


def render_mermaid(erd: ERDConfig) -> str:
    lines = ["erDiagram"]
    for entity in erd.entities:
        lines.append(_entity_block(entity.name, entity.fields))

    if erd.auth.enabled:
        lines.append(_entity_block("User", _AUTH_USER_DISPLAY_FIELDS))

    for entity in erd.entities:
        for rel in entity.relationships:
            left, right = _CARDINALITY_SYMBOLS[str(rel.cardinality)]
            lines.append(f'    {entity.name} {left}--{right} {rel.target} : "{rel.name}"')

    return "\n".join(lines)


def render_html(erd: ERDConfig) -> str:
    diagram = render_mermaid(erd)
    title = escape(erd.project.name)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title} - ERD</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body {{ font-family: sans-serif; margin: 2rem; background: #fafafa; }}
  h1 {{ font-size: 1.25rem; }}
  .mermaid {{ background: white; padding: 1rem; border-radius: 8px; }}
</style>
</head>
<body>
<h1>{title} &mdash; Entity Relationship Diagram</h1>
<pre class="mermaid">
{escape(diagram)}
</pre>
<script>mermaid.initialize({{ startOnLoad: true }});</script>
</body>
</html>
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_erd_visualize.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/erd/visualize.py backend/tests/test_erd_visualize.py
git commit -m "feat: render Mermaid ER diagrams from an ERDConfig"
```

---

### Task 7: `backstudio visualize` command

**Files:**
- Modify: `backend/cli/main.py`
- Test: `backend/tests/test_cli_visualize.py`

**Interfaces:**
- Consumes: `render_html` from `backend.erd.visualize` (Task 6), `load_erd`/`ERDValidationError` (Task 3).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cli_visualize.py
from typer.testing import CliRunner

from backend.cli.main import app

runner = CliRunner()
FIXTURES = "backend/tests/fixtures/erd"


def test_visualize_writes_html_file(tmp_path, monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda *_args, **_kwargs: True)
    out_file = tmp_path / "diagram.html"

    result = runner.invoke(
        app, ["visualize", f"{FIXTURES}/valid_minimal.yml", "--output", str(out_file), "--no-open"]
    )

    assert result.exit_code == 0
    assert out_file.exists()
    assert "erDiagram" in out_file.read_text(encoding="utf-8")
    assert "Diagram written to" in result.output


def test_visualize_invalid_file_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("project: [unterminated")
    result = runner.invoke(app, ["visualize", str(bad), "--no-open"])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_cli_visualize.py -v`
Expected: FAIL with "No such command 'visualize'"

- [ ] **Step 3: Add the command**

Edit `backend/cli/main.py` — add imports and the new command:

```python
import webbrowser

from backend.erd.visualize import render_html
```

Add after the `validate` command:

```python
@app.command()
def visualize(
    erd_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to the ERD YAML file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output HTML path"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open the diagram in a browser"),
) -> None:
    """Render an HTML ER diagram for the given ERD file."""
    try:
        erd = load_erd(erd_file)
    except ERDValidationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    html = render_html(erd)
    out_path = output or erd_file.with_name(f"{erd_file.stem}-diagram.html")
    out_path.write_text(html, encoding="utf-8")
    typer.secho(f"Diagram written to: {out_path}", fg=typer.colors.GREEN)

    if open_browser:
        webbrowser.open(out_path.resolve().as_uri())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_cli_visualize.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/cli/main.py backend/tests/test_cli_visualize.py
git commit -m "feat: add backstudio visualize command"
```

---

### Task 8: Auto-generated CRUD schemas and routes

**Files:**
- Create: `backend/templates/Python/service/crud_schemas.py.jinja`
- Create: `backend/templates/Python/service/crud_routes.py.jinja`
- Modify: `backend/services/code_generator.py`
- Test: `backend/tests/test_crud_generation.py`

**Interfaces:**
- Consumes: `CodeGenerator` (existing), `state['crud_entities']` shape from Task 4.
- Produces: for each `crud_entities[i]`, files at `<output>/<plural_snake>/schemas.py` and `<output>/<plural_snake>/routes.py` — consumed by Task 11 (server wiring) and Task 14 (end-to-end).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crud_generation.py
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_crud_schemas_and_routes(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_file = codebase_dir / "products" / "schemas.py"
    routes_file = codebase_dir / "products" / "routes.py"
    assert schemas_file.exists()
    assert routes_file.exists()

    schemas_src = schemas_file.read_text(encoding="utf-8")
    ast.parse(schemas_src)  # must be syntactically valid Python
    assert "class ProductCreate(BaseModel):" in schemas_src
    assert "class ProductResponse(BaseModel):" in schemas_src

    routes_src = routes_file.read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "from database.repo import" in routes_src
    assert 'router.post(\n    "",' in routes_src or '@router.post("")' in routes_src
    assert "def delete_product_route" in routes_src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_crud_generation.py -v`
Expected: FAIL (`jinja2.exceptions.TemplateNotFound: Python/service/crud_schemas.py.jinja`, since neither template nor wiring exists yet)

- [ ] **Step 3: Add templates and wiring**

Create `backend/templates/Python/service/crud_schemas.py.jinja`:

```jinja
"""{{ project.name }} - {{ entity.name }} schemas (auto-generated CRUD)"""

from typing import Any, Optional
from datetime import date, datetime
from pydantic import BaseModel


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
```

Create `backend/templates/Python/service/crud_routes.py.jinja`:

```jinja
"""{{ project.name }} - {{ entity.name }} routes (auto-generated CRUD)"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database.base import get_db
from database.repo import (
    create_{{ entity.snake_name }},
    get_{{ entity.snake_name }}_by_id,
    get_all_{{ entity.snake_name }}s,
    update_{{ entity.snake_name }},
    delete_{{ entity.snake_name }},
)
from .schemas import {{ entity.name }}Create, {{ entity.name }}Response, {{ entity.name }}Update
{% if project.rbac_enabled %}
from rbac import require_roles
{% endif %}

router = APIRouter()

{% if 'create' in entity.enabled_actions %}
@router.post(
    "",
    response_model={{ entity.name }}Response,
    status_code=status.HTTP_201_CREATED,
    summary="Create {{ entity.name }}",
{% if project.rbac_enabled and entity.rbac.create %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.create %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def create_{{ entity.snake_name }}_route(payload: {{ entity.name }}Create, db: Session = Depends(get_db)) -> {{ entity.name }}Response:
    return create_{{ entity.snake_name }}(db, payload.model_dump())
{% endif %}

{% if 'list' in entity.enabled_actions %}
@router.get(
    "",
    response_model=List[{{ entity.name }}Response],
    summary="List {{ entity.name }} records",
{% if project.rbac_enabled and entity.rbac.list %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.list %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def list_{{ entity.snake_name }}_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[{{ entity.name }}Response]:
    return get_all_{{ entity.snake_name }}s(db, skip=skip, limit=limit)
{% endif %}

{% if 'read' in entity.enabled_actions %}
@router.get(
    "/{item_id}",
    response_model={{ entity.name }}Response,
    summary="Get {{ entity.name }} by id",
{% if project.rbac_enabled and entity.rbac.read %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.read %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def get_{{ entity.snake_name }}_route(item_id: int, db: Session = Depends(get_db)) -> {{ entity.name }}Response:
    item = get_{{ entity.snake_name }}_by_id(db, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{{ entity.name }} not found")
    return item
{% endif %}

{% if 'update' in entity.enabled_actions %}
@router.put(
    "/{item_id}",
    response_model={{ entity.name }}Response,
    summary="Update {{ entity.name }}",
{% if project.rbac_enabled and entity.rbac.update %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.update %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def update_{{ entity.snake_name }}_route(item_id: int, payload: {{ entity.name }}Update, db: Session = Depends(get_db)) -> {{ entity.name }}Response:
    item = update_{{ entity.snake_name }}(db, item_id, payload.model_dump(exclude_unset=True))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{{ entity.name }} not found")
    return item
{% endif %}

{% if 'delete' in entity.enabled_actions %}
@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete {{ entity.name }}",
{% if project.rbac_enabled and entity.rbac.delete %}
    dependencies=[Depends(require_roles({% for role in entity.rbac.delete %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def delete_{{ entity.snake_name }}_route(item_id: int, db: Session = Depends(get_db)) -> None:
    deleted = delete_{{ entity.snake_name }}(db, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{{ entity.name }} not found")
{% endif %}
```

Edit `backend/services/code_generator.py`:

1. In `_register_filters`, after `self.jinja_env.globals['get_sqlalchemy_type'] = self._get_sqlalchemy_type`, add:

```python
        self.jinja_env.globals['get_python_type'] = self._get_python_type
```

2. Add the new method next to `_get_sqlalchemy_type`:

```python
    def _get_python_type(self, field_type: str) -> str:
        """Map FieldType enum values to Python/Pydantic type annotations."""
        type_map = {
            'string': 'str', 'integer': 'int', 'float': 'float', 'boolean': 'bool',
            'datetime': 'datetime', 'date': 'date', 'text': 'str', 'json': 'Any', 'uuid': 'str',
        }
        return type_map.get(str(field_type).lower(), 'str')
```

3. In `_generate_fastapi_project`, right after the `for service in state.get('services', []):` loop finishes and before "Generate main application files", add:

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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_crud_generation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/templates/Python/service/crud_schemas.py.jinja backend/templates/Python/service/crud_routes.py.jinja backend/services/code_generator.py backend/tests/test_crud_generation.py
git commit -m "feat: auto-generate working CRUD schemas and routes per entity"
```

---

### Task 9: RBAC dependency

**Files:**
- Create: `backend/templates/Python/rbac/dependency.py.jinja`
- Modify: `backend/services/code_generator.py`
- Test: `backend/tests/test_rbac_generation.py`

**Interfaces:**
- Consumes: `state['rbac_enabled']` (Task 4), `CodeGenerator` (Task 8's edits).
- Produces: `<output>/rbac.py` exposing `require_roles(*roles)`, imported by `crud_routes.py.jinja` (Task 8) and `dependency.py.jinja` (Task 10, auth).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_rbac_generation.py
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_rbac_module_when_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    rbac_file = codebase_dir / "rbac.py"
    assert rbac_file.exists()
    src = rbac_file.read_text(encoding="utf-8")
    ast.parse(src)
    assert "def require_roles(" in src


def test_no_rbac_module_when_disabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert not (codebase_dir / "rbac.py").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_rbac_generation.py -v`
Expected: FAIL — `rbac.py` is never written yet

- [ ] **Step 3: Add the template and wiring**

Create `backend/templates/Python/rbac/dependency.py.jinja`:

```jinja
"""{{ project.name }} - Role-based access control"""

from typing import Callable, List

from fastapi import Depends, HTTPException, status

from auth.service import get_current_user
from database.models import User


def require_roles(*roles: str) -> Callable:
    """Build a FastAPI dependency requiring the current user to have at least one of `roles`."""

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        user_roles: List[str] = current_user.roles or []
        if not set(user_roles) & set(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return current_user

    return dependency
```

Edit `backend/services/code_generator.py` — in `_generate_fastapi_project`, right after the CRUD entity loop added in Task 8, add:

```python
        # RBAC dependency (only meaningful once auth exists, enforced at the ERD validation layer)
        if state.get('rbac_enabled'):
            self._write_file(
                output_dir / "rbac.py",
                self._render_template("Python/rbac/dependency.py.jinja", context)
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_rbac_generation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/templates/Python/rbac/dependency.py.jinja backend/services/code_generator.py backend/tests/test_rbac_generation.py
git commit -m "feat: generate an RBAC require_roles dependency when rbac.enabled"
```

---

### Task 10: Auth service

**Files:**
- Create: `backend/templates/Python/auth/schemas.py.jinja`
- Create: `backend/templates/Python/auth/service.py.jinja`
- Create: `backend/templates/Python/auth/routes.py.jinja`
- Modify: `backend/services/code_generator.py`
- Test: `backend/tests/test_auth_generation.py`

**Interfaces:**
- Consumes: `state['auth_enabled']`, `state['security_config']` (Task 4).
- Produces: `<output>/auth/{schemas,service,routes}.py`; `auth.service.get_current_user` is consumed by `rbac.py` (Task 9).

**Note:** `dependencies.py.jinja` also emits `create_access_token`/`verify_token` helpers whenever `security_config.auth_strategy == 'jwt'` (pre-existing, unrelated to this feature). Those go unused by the new `auth/service.py` module, which implements its own JWT helpers scoped to `User.id`. This is a small, harmless duplication in generated output — not addressed here since `dependencies.py.jinja` also serves the older hand-authored-service flow.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_auth_generation.py
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_auth_service_when_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    auth_dir = codebase_dir / "auth"
    for filename in ("schemas.py", "service.py", "routes.py"):
        path = auth_dir / filename
        assert path.exists()
        ast.parse(path.read_text(encoding="utf-8"))

    service_src = (auth_dir / "service.py").read_text(encoding="utf-8")
    assert "def register_user(" in service_src
    assert "def authenticate_user(" in service_src
    assert "async def get_current_user(" in service_src

    routes_src = (auth_dir / "routes.py").read_text(encoding="utf-8")
    assert '"/register"' in routes_src
    assert '"/login"' in routes_src
    assert '"/me"' in routes_src


def test_no_auth_directory_when_disabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert not (codebase_dir / "auth").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_auth_generation.py -v`
Expected: FAIL — `auth/` directory is never written yet

- [ ] **Step 3: Add templates and wiring**

Create `backend/templates/Python/auth/schemas.py.jinja`:

```jinja
"""{{ project.name }} - Auth schemas"""

from typing import List
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    roles: List[str] = []
    is_active: bool

    class Config:
        from_attributes = True
```

Create `backend/templates/Python/auth/service.py.jinja`:

```jinja
"""{{ project.name }} - Authentication service"""

from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from database.base import get_db
from database.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def _create_token(subject: str, expires_delta: timedelta) -> str:
    expire = datetime.utcnow() + expires_delta
    return jwt.encode(
        {"sub": subject, "exp": expire},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(user_id: int) -> str:
    return _create_token(str(user_id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: int) -> str:
    return _create_token(str(user_id), timedelta(days=7))


def register_user(db: Session, email: str, password: str) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("Email already registered")
    user = User(email=email, password_hash=hash_password(password), roles=[], is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password")
    if not user.is_active:
        raise ValueError("User is inactive")
    return user


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    return int(subject)


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user_id = decode_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
```

Create `backend/templates/Python/auth/routes.py.jinja`:

```jinja
"""{{ project.name }} - Auth routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.base import get_db
from database.models import User
from .schemas import TokenResponse, UserLogin, UserRegister, UserResponse
from .service import authenticate_user, create_access_token, create_refresh_token, decode_token, get_current_user, register_user

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> UserResponse:
    try:
        user = register_user(db, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = authenticate_user(db, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return TokenResponse(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


@router.post("/refresh", response_model=TokenResponse)
def refresh(refresh_token: str, db: Session = Depends(get_db)) -> TokenResponse:
    user_id = decode_token(refresh_token)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return TokenResponse(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return current_user
```

Edit `backend/services/code_generator.py` — in `_generate_fastapi_project`, right after the CRUD entity loop from Task 8 (before the RBAC block from Task 9, order doesn't matter but keep RBAC after auth since `rbac.py` imports from `auth.service`), add:

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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_auth_generation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/templates/Python/auth backend/services/code_generator.py backend/tests/test_auth_generation.py
git commit -m "feat: generate a JWT auth service when auth.enabled"
```

---

### Task 11: Wire CRUD and auth routers into server.py

**Files:**
- Modify: `backend/templates/Python/server.py.jinja`
- Test: `backend/tests/test_server_wiring.py`

**Interfaces:**
- Consumes: `state['crud_entities']`, `state['auth_enabled']` (Task 4).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_server_wiring.py
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_server_imports_and_mounts_crud_and_auth_routers(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    ast.parse(server_src)

    assert "from products.routes import router as products_router" in server_src
    assert 'app.include_router(products_router, prefix="/products"' in server_src
    assert "from auth.routes import router as auth_router" in server_src
    assert 'app.include_router(auth_router, prefix="/auth"' in server_src


def test_server_skips_crud_and_auth_blocks_when_absent(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    ast.parse(server_src)
    assert "from widgets.routes import router as widgets_router" in server_src
    assert "from auth.routes import router as auth_router" not in server_src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_server_wiring.py -v`
Expected: FAIL — `server.py` has no CRUD/auth router imports yet

- [ ] **Step 3: Extend the template**

Edit `backend/templates/Python/server.py.jinja` — after the existing services import block:

```jinja
{% if project.services %}
{% for service in project.services %}
from {{ service.name|snake_case }}.routes import router as {{ service.name|snake_case }}_router
{% endfor %}
{% endif %}
```

add:

```jinja
{% if project.crud_entities %}
{% for entity in project.crud_entities %}
from {{ entity.plural_snake }}.routes import router as {{ entity.plural_snake }}_router
{% endfor %}
{% endif %}
{% if project.auth_enabled %}
from auth.routes import router as auth_router
{% endif %}
```

And after the existing include_router block:

```jinja
{% if project.services %}
{% for service in project.services %}
app.include_router(
    {{ service.name|snake_case }}_router,
    prefix="/api/{{ service.name|kebab_case }}"
)
{% endfor %}
{% endif %}
```

add:

```jinja
{% if project.crud_entities %}
{% for entity in project.crud_entities %}
app.include_router({{ entity.plural_snake }}_router, prefix="{{ entity.base_path }}", tags={{ entity.tags|tojson }})
{% endfor %}
{% endif %}
{% if project.auth_enabled %}
app.include_router(auth_router, prefix="/auth", tags=["auth"])
{% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_server_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/templates/Python/server.py.jinja backend/tests/test_server_wiring.py
git commit -m "feat: mount auto-generated CRUD and auth routers in server.py"
```

---

### Task 12: Alembic scaffolding

**Files:**
- Create: `backend/templates/Python/alembic/alembic.ini.jinja`
- Create: `backend/templates/Python/alembic/env.py.jinja`
- Modify: `backend/services/code_generator.py`
- Test: `backend/tests/test_alembic_generation.py`

**Interfaces:**
- Consumes: `CodeGenerator` (Task 8/9/10 edits already in place).
- Produces: `<output>/alembic.ini`, `<output>/alembic/env.py`, `<output>/alembic/versions/` (empty dir) — always generated, independent of auth/rbac; consumed by Task 13's best-effort autogenerate step.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_alembic_generation.py
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_alembic_scaffolding(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert (codebase_dir / "alembic.ini").exists()
    env_path = codebase_dir / "alembic" / "env.py"
    assert env_path.exists()
    assert (codebase_dir / "alembic" / "versions").is_dir()

    env_src = env_path.read_text(encoding="utf-8")
    ast.parse(env_src)
    assert "target_metadata = Base.metadata" in env_src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_alembic_generation.py -v`
Expected: FAIL — Alembic files are never written yet

- [ ] **Step 3: Add templates and wiring**

Create `backend/templates/Python/alembic/alembic.ini.jinja`:

```ini
[alembic]
script_location = alembic
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `backend/templates/Python/alembic/env.py.jinja`:

```jinja
"""{{ project.name }} - Alembic environment"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import settings
from database.base import Base
import database.models  # noqa: F401  registers all models on Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Edit `backend/services/code_generator.py` — in `_generate_fastapi_project`, after the auth/RBAC blocks added in Tasks 9-10, add (unconditional — every generated project gets Alembic scaffolding):

```python
        # Alembic scaffolding
        alembic_dir = output_dir / "alembic"
        ensure_directory(alembic_dir / "versions")
        self._write_file(
            output_dir / "alembic.ini",
            self._render_template("Python/alembic/alembic.ini.jinja", context)
        )
        self._write_file(
            alembic_dir / "env.py",
            self._render_template("Python/alembic/env.py.jinja", context)
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_alembic_generation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/templates/Python/alembic backend/services/code_generator.py backend/tests/test_alembic_generation.py
git commit -m "feat: scaffold Alembic migrations in generated projects"
```

---

### Task 13: `backstudio generate` command

**Files:**
- Modify: `backend/cli/main.py`
- Test: `backend/tests/test_cli_generate.py`

**Interfaces:**
- Consumes: `load_erd`/`ERDValidationError` (Task 3), `translate` (Task 4), `CodeGenerator` (existing + Tasks 8-12).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cli_generate.py
from typer.testing import CliRunner

from backend.cli.main import app

runner = CliRunner()
FIXTURES = "backend/tests/fixtures/erd"


def test_generate_writes_codebase_and_reports_path(tmp_path):
    result = runner.invoke(
        app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Generated at:" in result.output
    assert (tmp_path / "Demo" / "codebase" / "server.py").exists()
    assert (tmp_path / "Demo" / "codebase" / "widgets" / "routes.py").exists()


def test_generate_refuses_to_overwrite_without_force(tmp_path):
    runner.invoke(app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)])
    result = runner.invoke(app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)])
    assert result.exit_code == 1
    assert "--force" in result.output


def test_generate_force_overwrites(tmp_path):
    runner.invoke(app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)])
    result = runner.invoke(
        app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path), "--force"]
    )
    assert result.exit_code == 0


def test_generate_invalid_erd_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("project: [unterminated")
    result = runner.invoke(app, ["generate", str(bad), "--output", str(tmp_path)])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_cli_generate.py -v`
Expected: FAIL with "No such command 'generate'"

- [ ] **Step 3: Add the command**

Edit `backend/cli/main.py` — add imports:

```python
import subprocess

from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator
```

Add the command after `visualize`:

```python
@app.command()
def generate(
    erd_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to the ERD YAML file"),
    output: Path = typer.Option(Path("workspace"), "--output", help="Workspace directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing generated code"),
) -> None:
    """Generate a FastAPI backend from an ERD file."""
    try:
        erd = load_erd(erd_file)
    except ERDValidationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    state = translate(erd)
    generator = CodeGenerator(output_dir=str(output))

    try:
        codebase_dir = generator.generate_project(state, force=force)
    except FileExistsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        typer.secho("Use --force to overwrite.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    if (codebase_dir / "alembic.ini").exists():
        try:
            subprocess.run(
                ["alembic", "revision", "--autogenerate", "-m", "initial"],
                cwd=codebase_dir,
                check=True,
                capture_output=True,
                timeout=30,
            )
        except Exception as exc:  # best-effort: never fails `generate`
            typer.secho(
                f"Warning: could not auto-generate the initial Alembic migration ({exc}). "
                "You can run it yourself once the database is reachable.",
                fg=typer.colors.YELLOW,
            )

    typer.secho(f"Generated at: {codebase_dir}", fg=typer.colors.GREEN, bold=True)
    typer.echo("Copy this directory into your project.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_cli_generate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/cli/main.py backend/tests/test_cli_generate.py
git commit -m "feat: add backstudio generate command"
```

---

### Task 14: End-to-end fixture test

**Files:**
- Create: `backend/tests/fixtures/erd/shophub_mini.yml`
- Test: `backend/tests/test_end_to_end.py`

**Interfaces:**
- Consumes: everything from Tasks 1-13.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/fixtures/erd/shophub_mini.yml`:

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
```

Create `backend/tests/test_end_to_end.py`:

```python
import ast
import subprocess
import sys
from pathlib import Path

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def _assert_all_python_files_parse(root: Path) -> None:
    for path in root.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_shophub_mini_generates_a_complete_working_tree(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

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
    for rel_path in expected_files:
        assert (codebase_dir / rel_path).exists(), f"missing {rel_path}"

    _assert_all_python_files_parse(codebase_dir)

    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    assert "class User(Base):" in models_src
    assert "class Product(Base):" in models_src
    assert "class Order(Base):" in models_src

    products_routes_src = (codebase_dir / "products" / "routes.py").read_text(encoding="utf-8")
    assert "from rbac import require_roles" in products_routes_src
    assert 'require_roles("admin")' in products_routes_src


def test_shophub_mini_byte_compiles(tmp_path):
    """A stronger check than ast.parse: byte-compile every generated module."""
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(codebase_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_end_to_end.py -v`
Expected: at this point in the plan it should actually PASS or reveal a real integration bug, since Tasks 1-13 are already implemented — if it fails, this is genuine regression-hunting, not a scaffolding gap. Treat any failure as a real bug to fix in the relevant template/module from Tasks 4, 8-12, not as an excuse to weaken the test.

- [ ] **Step 3: Fix any integration issues found**

If Step 2 fails, the most likely causes and where to fix them:
- Relationship translation shape mismatch (`Order` referencing the auto-injected `User`) → `backend/erd/translate.py` (`_build_relationship`, `_build_user_entity`).
- A Jinja template referencing a field that isn't present in `state` → the specific `*.jinja` file from Tasks 8-12.
- Import ordering / naming collisions between `products`/`categories`/`orders` directories and `auth`/`rbac.py` → `backend/services/code_generator.py`'s new generation block order (Tasks 8-12).

Make the minimal fix in the appropriate file; do not modify the test to hide a real bug.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests -v`
Expected: PASS (full suite, all tasks)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/erd/shophub_mini.yml backend/tests/test_end_to_end.py
git commit -m "test: add end-to-end ERD generation fixture covering auth, rbac, and relationships"
```

---

## Self-Review Notes

- **Spec coverage:** §2 scope boundary → Tasks 1, 2, 4; §3 YAML schema → Tasks 2-4; §4 pipeline/CLI → Tasks 5, 7, 13; §5 templates → Tasks 8-12; §6 packaging → Task 1; §7 error handling → Tasks 3, 13; §8 testing → every task's Test file plus Task 14; §9 out-of-scope items are not implemented anywhere in this plan.
- **Added beyond the spec:** the `rbac.enabled requires auth.enabled` validation rule (Task 3) is not spelled out verbatim in the spec but is necessary for the RBAC design in spec §3/§5 to be sound (there is no other way to identify "the current user" to check roles against) — flagged in Global Constraints.
- **Type/name consistency checked across tasks:** `crud_entities[i]` keys (`name, snake_name, plural_snake, base_path, tags, enabled_actions, rbac, fields`) defined in Task 4 are used identically in Tasks 8, 9, 11, 14. `state` top-level keys (`crud_entities, auth_enabled, rbac_enabled, rbac_roles, security_config`) defined in Task 4 match every consumer in Tasks 8-13. `get_python_type`/`get_sqlalchemy_type` globals registered once in Task 8, used only in Task 8's templates. `auth.service.get_current_user` defined in Task 10, imported in Task 9's `rbac.py`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-08-erd-cli-generator.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
