# Relationship CRUD Exposure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose relationships through the generated CRUD API — FK fields with existence validation for many-to-one/one-to-one (and one-to-many from the FK-owning side), plus read-only many-to-many id lists — closing the gap where the DB layer wires relationships up correctly but no generated schema/route can read or write any of it.

**Architecture:** `translate.py` gains two derived lists per entity (`owned_relationships`, `many_to_many_relationships`), computed once and attached to both `data_models` (consumed by `repo.py.jinja`) and `crud_entities` (consumed by `module_schemas.py.jinja`/`module_service.py.jinja`/`module_routes.py.jinja`). Four templates then render FK fields, existence validation, a query-param list filter, and a read-only many-to-many id list, working from that shared data.

**Tech Stack:** Python 3.11, Jinja2 (trim_blocks/lstrip_blocks — see Global Constraints), SQLAlchemy 2.x (sync), Pydantic v2, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-relationship-crud-exposure-design.md`

## Global Constraints

- No new ERD YAML syntax — this behavior is automatic for every relationship, no per-relationship opt-out (spec §2).
- Many-to-many write support, nested full-object responses, and nested one-to-many collections are explicitly out of scope (spec §2, §8).
- `fk_nullable` FK fields are `Optional[int] = None` everywhere; non-nullable FK fields are `int` (required) on `Create`/`Response` but always `Optional[int] = None` on `Update` (matching the existing convention that every `Update` field is optional regardless of nullability).
- FK existence validation happens in the service layer (`raise ValueError(...)`), and generated routes map `ValueError` → `HTTPException(400, ...)` — the same convention `auth/routes.py` already uses for `register`/`login`.
- Many-to-many `Response` exposure is read-only: `<target_plural>_ids: List[int]`, populated via a `model_validator(mode="before")`. `Create`/`Update` get nothing for many-to-many.
- Every list endpoint whose entity has `owned_relationships` gets an optional query-param filter per FK; every `list`/`get` query for a model with `many_to_many_relationships` uses `selectinload` to avoid N+1.
- **Jinja whitespace (trim_blocks/lstrip_blocks are both on):** a block tag (`{% ... %}`) that shares a source line with real content and is the LAST thing before the line's newline eats that newline — collapsing what should be two output lines into one, or (if immediately followed by another bare `{% ... %}` line with nothing to compensate) deleting a blank line entirely. This codebase's fix is `{% endif +%}` / `{% endfor +%}` (the `+` disables trim for that one tag) on the trailing tag of a content line inside a loop. **Every step below that edits a `.jinja` template must be verified by actually rendering it against a real fixture and reading the output — not just eyeballing the template source** (this has bitten every template touched so far this session; `ast.parse`/`py_compile` alone does not catch a merged-together field list, it only catches syntax errors).

---

### Task 1: `translate.py` — derive `owned_relationships` / `many_to_many_relationships`

**Files:**
- Modify: `backend/erd/translate.py`
- Test: `backend/tests/test_erd_translate.py`

**Interfaces:**
- Produces: every `data_models` entry and every `crud_entities` entry gains two new keys:
  - `owned_relationships: List[{"attribute": str, "fk_column": str, "fk_nullable": bool, "target_model": str, "target_snake": str}]`
  - `many_to_many_relationships: List[{"attribute": str, "target_model": str, "target_plural_snake": str}]`
- Consumed by: Tasks 2-5 (templates), reading `entity.owned_relationships`/`entity.many_to_many_relationships` (crud_entities) and `model.owned_relationships`/`model.many_to_many_relationships` (data_models).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_erd_translate.py` (uses the existing direct-`ERDConfig`-construction style already in this file, e.g. `test_translate_one_to_many_cardinality`):

```python
def test_owned_relationships_many_to_one():
    """Post declares many-to-one to Category: Post owns the FK, Category doesn't."""
    erd = ERDConfig(
        project=ProjectMeta(name="Blog", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="blog.db"),
        entities=[
            EntitySpec(
                name="Category",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
            EntitySpec(
                name="Post",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="category", cardinality="many-to-one", target="Category")
                ],
            ),
        ],
        services=[ServiceDecl(name="content", entities=["Category", "Post"])],
    )
    state = translate(erd)

    category = next(m for m in state["data_models"] if m["name"] == "Category")
    post = next(m for m in state["data_models"] if m["name"] == "Post")
    assert category["owned_relationships"] == []
    assert post["owned_relationships"] == [
        {
            "attribute": "category",
            "fk_column": "category_id",
            "fk_nullable": True,
            "target_model": "Category",
            "target_snake": "category",
        }
    ]
    assert category["many_to_many_relationships"] == []
    assert post["many_to_many_relationships"] == []

    # crud_entities carry the identical derived lists
    post_entity = next(e for e in state["modules"][0]["entities"] if e["name"] == "Post")
    assert post_entity["owned_relationships"] == post["owned_relationships"]


def test_owned_relationships_one_to_many_equivalent_to_many_to_one():
    """Author declares one-to-many to Book: per translate.py's existing normalization
    the FK lives on Book (the target), so Book - not Author - is the owning side.
    This must produce the identical shape test_owned_relationships_many_to_one gets
    from declaring the relationship the other way around.
    """
    erd = ERDConfig(
        project=ProjectMeta(name="Library", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="library.db"),
        entities=[
            EntitySpec(
                name="Author",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="author_books", cardinality="one-to-many", target="Book")
                ],
            ),
            EntitySpec(
                name="Book",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
        ],
        services=[ServiceDecl(name="library", entities=["Author", "Book"])],
    )
    state = translate(erd)

    author = next(m for m in state["data_models"] if m["name"] == "Author")
    book = next(m for m in state["data_models"] if m["name"] == "Book")
    assert author["owned_relationships"] == []
    assert book["owned_relationships"] == [
        {
            "attribute": "author",
            "fk_column": "author_id",
            "fk_nullable": True,
            "target_model": "Author",
            "target_snake": "author",
        }
    ]


def test_owned_relationships_required_fk_not_nullable():
    erd = ERDConfig(
        project=ProjectMeta(name="Blog", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="blog.db"),
        entities=[
            EntitySpec(
                name="Category",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
            EntitySpec(
                name="Post",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(
                        name="category", cardinality="many-to-one", target="Category", nullable=False
                    )
                ],
            ),
        ],
        services=[ServiceDecl(name="content", entities=["Category", "Post"])],
    )
    state = translate(erd)
    post = next(m for m in state["data_models"] if m["name"] == "Post")
    assert post["owned_relationships"][0]["fk_nullable"] is False


def test_many_to_many_relationships_both_sides():
    erd = ERDConfig(
        project=ProjectMeta(name="Blog", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="blog.db"),
        entities=[
            EntitySpec(
                name="Post",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="tags", cardinality="many-to-many", target="Tag")
                ],
            ),
            EntitySpec(
                name="Tag",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
        ],
        services=[ServiceDecl(name="content", entities=["Post", "Tag"])],
    )
    state = translate(erd)

    post = next(m for m in state["data_models"] if m["name"] == "Post")
    tag = next(m for m in state["data_models"] if m["name"] == "Tag")

    assert post["owned_relationships"] == []
    assert post["many_to_many_relationships"] == [
        {"attribute": "tags", "target_model": "Tag", "target_plural_snake": "tags"}
    ]
    assert tag["many_to_many_relationships"] == [
        {"attribute": "posts", "target_model": "Post", "target_plural_snake": "posts"}
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_erd_translate.py -k "owned_relationships or many_to_many_relationships" -v`
Expected: FAIL with `KeyError: 'owned_relationships'` (the key doesn't exist yet).

- [ ] **Step 3: Implement**

In `backend/erd/translate.py`, add two helper functions right after `_validate_relationship_uniqueness` (before `_build_user_entity`):

```python
def _owned_relationships_for(entity_name: str, rels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Relationships where `entity_name` owns the FK column - regardless of which
    cardinality keyword declared it (a one-to-many declared from the parent side and
    the equivalent many-to-one declared from the child side both normalize to the
    same foreign_key.model in _build_relationship, so this check covers both).
    """
    owned: List[Dict[str, Any]] = []
    for rel in rels:
        fk = rel.get("foreign_key")
        if not fk or fk["model"] != entity_name:
            continue
        is_source = rel["source"]["model"] == entity_name
        other_model = rel["target"]["model"] if is_source else rel["source"]["model"]
        owned.append({
            "attribute": rel["source"]["attribute"] if is_source else rel["target"]["attribute"],
            "fk_column": fk["column"],
            "fk_nullable": fk["nullable"],
            "target_model": other_model,
            "target_snake": _snake_case(other_model),
        })
    return owned


def _many_to_many_relationships_for(entity_name: str, rels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    m2m: List[Dict[str, Any]] = []
    for rel in rels:
        if rel["cardinality"] != "many-to-many":
            continue
        is_source = rel["source"]["model"] == entity_name
        other_model = rel["target"]["model"] if is_source else rel["source"]["model"]
        m2m.append({
            "attribute": rel["source"]["attribute"] if is_source else rel["target"]["attribute"],
            "target_model": other_model,
            "target_plural_snake": _pluralize(other_model),
        })
    return m2m
```

Then in `translate()`, right after the existing block that appends relationships to `data_models` and validates uniqueness (immediately after the `for model_name, model in data_models.items(): _validate_relationship_uniqueness(...)` loop, before the `crud_entities: List[...] = []` line), add:

```python
    for model in data_models.values():
        model["owned_relationships"] = _owned_relationships_for(model["name"], model["relationships"])
        model["many_to_many_relationships"] = _many_to_many_relationships_for(model["name"], model["relationships"])
```

Then in the existing `crud_entities.append({...})` block, add two lines reusing the same already-computed lists (do not recompute):

```python
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
            "fields": [f.model_dump(mode='json') for f in entity.fields],
            "owned_relationships": data_models[entity.name]["owned_relationships"],
            "many_to_many_relationships": data_models[entity.name]["many_to_many_relationships"],
        })
```

Also add the same two keys (as empty lists) to `_build_user_entity`'s returned dict, for readability of its own contract — note this is defensive, not load-bearing: the loop above already runs over every `data_models.values()` entry including `"User"` (added to `data_models` earlier, before that loop runs) and unconditionally sets both keys on it, so `User`'s dict has correct, non-empty-if-applicable values by the time `repo.py.jinja` reads `project.data_models` regardless of what `_build_user_entity` itself returns:

```python
    return {
        "name": "User",
        "table_name": "users",
        "plural_snake": _pluralize("User"),
        "fields": fields,
        "relationships": [],
        "owned_relationships": [],
        "many_to_many_relationships": [],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_erd_translate.py -v`
Expected: PASS (all tests in the file, including the 4 new ones and every pre-existing one).

- [ ] **Step 5: Run the full suite to check nothing else broke**

Run: `uv run pytest backend/tests -q`
Expected: PASS, same count as before plus 4.

- [ ] **Step 6: Commit**

```bash
git add backend/erd/translate.py backend/tests/test_erd_translate.py
git commit -m "Derive owned_relationships and many_to_many_relationships in translate.py"
```

---

### Task 2: `module_schemas.py.jinja` — FK fields on Create/Update/Response + read-only many-to-many id list

**Files:**
- Modify: `backend/templates/Python/service/module_schemas.py.jinja`
- Create: `backend/tests/fixtures/erd/many_to_many.yml`
- Test: `backend/tests/test_crud_generation.py`

**Interfaces:**
- Consumes: `entity.owned_relationships`, `entity.many_to_many_relationships` (Task 1).
- Produces: rendered `Create`/`Update`/`Response` Pydantic classes with FK fields; `Response` classes for entities with `many_to_many_relationships` get a `_compute_m2m_ids` `model_validator(mode="before")`.

- [ ] **Step 1: Create the many-to-many fixture**

Create `backend/tests/fixtures/erd/many_to_many.yml`:

```yaml
project:
  name: M2MDemo
  version: "1.0.0"

database:
  type: sqlite
  database_name: m2m.db

entities:
  - name: Post
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: title, type: string}
    relationships:
      - name: tags
        cardinality: many-to-many
        target: Tag

  - name: Tag
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: name, type: string}

services:
  - name: content
    entities: [Post, Tag]
```

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/test_crud_generation.py`:

```python
def test_owned_relationship_fk_field_on_create_update_response(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")  # Product has many-to-one to Category
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "catalog" / "schemas.py").read_text(encoding="utf-8")
    ast.parse(schemas_src)

    create_start = schemas_src.index("class ProductCreate(BaseModel):")
    update_start = schemas_src.index("class ProductUpdate(BaseModel):")
    response_start = schemas_src.index("class ProductResponse(BaseModel):")
    create_src = schemas_src[create_start:update_start]
    update_src = schemas_src[update_start:response_start]
    response_src = schemas_src[response_start:]

    assert "category_id: Optional[int] = None" in create_src  # nullable by default
    assert "category_id: Optional[int] = None" in update_src
    assert "category_id: Optional[int] = None" in response_src


def test_many_to_many_id_list_on_response_only(tmp_path):
    erd = load_erd(f"{FIXTURES}/many_to_many.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "content" / "schemas.py").read_text(encoding="utf-8")
    ast.parse(schemas_src)

    create_start = schemas_src.index("class PostCreate(BaseModel):")
    update_start = schemas_src.index("class PostUpdate(BaseModel):")
    response_start = schemas_src.index("class PostResponse(BaseModel):")
    create_src = schemas_src[create_start:update_start]
    update_src = schemas_src[update_start:response_start]
    response_src = schemas_src[response_start:]

    assert "tag_ids" not in create_src
    assert "tag_ids" not in update_src
    assert "tag_ids: List[int] = []" in response_src
    assert "model_validator" in response_src


def test_many_to_many_response_validator_extracts_ids_from_orm_relationship(tmp_path):
    """The strongest check: actually import the rendered schemas.py and validate a
    fake ORM-like object through it, proving the model_validator works at runtime -
    not just that the text is present.
    """
    erd = load_erd(f"{FIXTURES}/many_to_many.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "generated_m2m_schemas", codebase_dir / "modules" / "content" / "schemas.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class FakeTag:
        def __init__(self, id_):
            self.id = id_

    class FakePost:
        id = 1
        title = "Hello"
        tags = [FakeTag(1), FakeTag(2)]

    result = module.PostResponse.model_validate(FakePost())
    assert result.tag_ids == [1, 2]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_crud_generation.py -k "owned_relationship_fk or many_to_many" -v`
Expected: FAIL — `category_id`/`tag_ids` not present in the generated schemas yet.

- [ ] **Step 4: Implement**

Rewrite `backend/templates/Python/service/module_schemas.py.jinja` in full:

```jinja
"""{{ project.name }} - {{ module.name }} schemas (auto-generated CRUD)"""

{% set json_fields = module.entities|map(attribute='fields')|sum(start=[])|selectattr('type', 'equalto', 'json')|list %}
{% set has_m2m = (module.entities|map(attribute='many_to_many_relationships')|map('length')|sum) > 0 %}
from typing import Optional{% if json_fields %}, Any{% endif %}{% if has_m2m %}, List{% endif +%}
from datetime import date, datetime
from pydantic import BaseModel{% if has_m2m %}, model_validator{% endif +%}

{% for entity in module.entities %}

class {{ entity.name }}Create(BaseModel):
    """Fields required to create a {{ entity.name }}."""
{% for field in entity.fields %}
{% if not field.primary_key %}
    {{ field.name }}: {% if field.nullable %}Optional[{{ get_python_type(field.type) }}]{% else %}{{ get_python_type(field.type) }}{% endif %}{% if field.default is not none %} = {{ field.default|python_value }}{% elif field.nullable %} = None{% endif +%}
{% endif %}
{% endfor %}
{% for rel in entity.owned_relationships %}
    {{ rel.fk_column }}: {% if rel.fk_nullable %}Optional[int] = None{% else %}int{% endif +%}
{% endfor %}
{% if entity.fields|rejectattr('primary_key')|list|length == 0 and not entity.owned_relationships %}
    pass
{% endif %}


class {{ entity.name }}Update(BaseModel):
    """Fields that may be updated on a {{ entity.name }} (all optional)."""
{% for field in entity.fields %}
{% if not field.primary_key %}
    {{ field.name }}: Optional[{{ get_python_type(field.type) }}] = None
{% endif %}
{% endfor %}
{% for rel in entity.owned_relationships %}
    {{ rel.fk_column }}: Optional[int] = None
{% endfor %}
{% if entity.fields|rejectattr('primary_key')|list|length == 0 and not entity.owned_relationships %}
    pass
{% endif %}


class {{ entity.name }}Response(BaseModel):
    """{{ entity.name }} as returned by the API."""
{% for field in entity.fields %}
{% if field.primary_key %}
    {{ field.name }}: {{ get_python_type(field.type) }}
{% elif field.nullable %}
    {{ field.name }}: Optional[{{ get_python_type(field.type) }}] = None
{% else %}
    {{ field.name }}: {{ get_python_type(field.type) }} = None
{% endif %}
{% endfor %}
{% for rel in entity.owned_relationships %}
    {{ rel.fk_column }}: {% if rel.fk_nullable %}Optional[int] = None{% else %}int{% endif +%}
{% endfor %}
{% for rel in entity.many_to_many_relationships %}
    {{ rel.target_plural_snake }}_ids: List[int] = []
{% endfor %}
{% if entity.many_to_many_relationships %}

    @model_validator(mode="before")
    @classmethod
    def _compute_m2m_ids(cls, data):
        if not isinstance(data, dict):
{% for rel in entity.many_to_many_relationships %}
            data.{{ rel.target_plural_snake }}_ids = [item.id for item in getattr(data, "{{ rel.attribute }}", [])]
{% endfor %}
        return data
{% endif %}

    class Config:
        from_attributes = True
{% endfor %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_crud_generation.py -v`
Expected: PASS.

- [ ] **Step 6: Render and read the output by hand**

Run:
```bash
uv run backstudio generate backend/tests/fixtures/erd/valid_full.yml --output /tmp/rc_task2a --force
uv run backstudio generate backend/tests/fixtures/erd/many_to_many.yml --output /tmp/rc_task2b --force
```
Read `/tmp/rc_task2a/ShopHub/codebase/modules/catalog/schemas.py` and `/tmp/rc_task2b/M2MDemo/codebase/modules/content/schemas.py` in full. Confirm: no fields glued onto one line (the `+%}` whitespace-control pattern from Global Constraints), correct blank-line spacing between classes, `Config`/`model_validator` correctly indented inside their class body. Fix any whitespace issues found, re-render, re-read until clean. Then `py_compile` both rendered files.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/templates/Python/service/module_schemas.py.jinja backend/tests/fixtures/erd/many_to_many.yml backend/tests/test_crud_generation.py
git commit -m "Expose owned-relationship FK fields and read-only many-to-many id lists in generated schemas"
```

---

### Task 3: `repo.py.jinja` — FK filter param + selectinload for many-to-many

**Files:**
- Modify: `backend/templates/Python/database/repo.py.jinja`
- Test: `backend/tests/test_crud_generation.py`

**Interfaces:**
- Consumes: `model.owned_relationships`, `model.many_to_many_relationships` (Task 1, on `project.data_models` entries).
- Produces: `get_all_<plural>(db, skip, limit, <fk_column>=None, ...)` filters when a FK param is given; both `get_all_<plural>` and `get_<x>_by_id` add `.options(selectinload(...))` for every many-to-many relationship on that model.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_crud_generation.py`:

```python
def test_repo_get_all_accepts_owned_relationship_filter_params(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")  # Product has many-to-one to Category
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    ast.parse(repo_src)

    func_start = repo_src.index("def get_all_products(")
    func_end = repo_src.index("\ndef ", func_start + 1)
    func_src = repo_src[func_start:func_end]
    assert "category_id: Optional[int] = None" in func_src
    assert "if category_id is not None" in func_src
    assert "Product.category_id == category_id" in func_src


def test_repo_selectinload_used_for_many_to_many(tmp_path):
    erd = load_erd(f"{FIXTURES}/many_to_many.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    ast.parse(repo_src)
    assert "from sqlalchemy.orm import Session, selectinload" in repo_src

    get_all_start = repo_src.index("def get_all_posts(")
    get_all_end = repo_src.index("\ndef ", get_all_start + 1)
    assert "selectinload(Post.tags)" in repo_src[get_all_start:get_all_end]

    get_by_id_start = repo_src.index("def get_post_by_id(")
    get_by_id_end = repo_src.index("\ndef ", get_by_id_start + 1)
    assert "selectinload(Post.tags)" in repo_src[get_by_id_start:get_by_id_end]


def test_repo_filter_and_selectinload_work_against_a_real_db(tmp_path):
    """Actually run the rendered repo functions against a real SQLite DB - the
    strongest signal, matching the lesson learned earlier this session that
    ast.parse alone doesn't catch behavioral bugs. Reuses
    _GeneratedProjectImporter from test_generated_project_runtime.py (import it
    from there rather than re-implementing sys.path/sys.modules handling here -
    see that file's isolated_sys_path fixture docstring for why a naive purge
    of every imported module is unsafe).
    """
    from backend.tests.test_generated_project_runtime import _GeneratedProjectImporter

    erd = load_erd(f"{FIXTURES}/many_to_many.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        database_base = importlib.import_module("database.base")
        database_models = importlib.import_module("database.models")
        repo = importlib.import_module("database.repo")

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        database_base.Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        tag = database_models.Tag(name="python")
        db.add(tag)
        db.commit()

        post = repo.create_post(db, {"title": "Hello"})
        post.tags.append(tag)
        db.commit()

        fetched = repo.get_post_by_id(db, post.id)
        assert [t.name for t in fetched.tags] == ["python"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_crud_generation.py -k "repo_get_all or repo_selectinload or repo_filter" -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `backend/templates/Python/database/repo.py.jinja`, change the imports line and the two function templates. The full new file:

```jinja
"""{{ project.name }} - Database repository functions"""

{% set has_any_m2m = (project.data_models|map(attribute='many_to_many_relationships')|map('length')|sum) > 0 %}
from typing import Optional, List
from sqlalchemy.orm import Session{% if has_any_m2m %}, selectinload{% endif +%}

from .models import {% for model in project.data_models %}{{ model.name|pascal_case }}{{ ", " if not loop.last else "" }}{% endfor %}

{% for model in project.data_models %}

# {{ model.name|pascal_case }} Repository Functions

def create_{{ model.name|snake_case }}(db: Session, {{ model.name|snake_case }}_data: dict) -> {{ model.name|pascal_case }}:
    """Create a new {{ model.name }}"""
    {{ model.name|snake_case }} = {{ model.name|pascal_case }}(**{{ model.name|snake_case }}_data)
    db.add({{ model.name|snake_case }})
    db.commit()
    db.refresh({{ model.name|snake_case }})
    return {{ model.name|snake_case }}


def get_{{ model.name|snake_case }}_by_id(db: Session, {{ model.name|snake_case }}_id: int) -> Optional[{{ model.name|pascal_case }}]:
    """Get {{ model.name }} by ID"""
    query = db.query({{ model.name|pascal_case }})
{% for rel in model.many_to_many_relationships %}
    query = query.options(selectinload({{ model.name|pascal_case }}.{{ rel.attribute }}))
{% endfor %}
    {% set pk_field = model.fields|selectattr('primary_key')|first %}
    {% if pk_field %}
    return query.filter({{ model.name|pascal_case }}.{{ pk_field.name }} == {{ model.name|snake_case }}_id).first()
    {%- else %}
    return query.filter({{ model.name|pascal_case }}.id == {{ model.name|snake_case }}_id).first()
    {%- endif %}


{% for field in model.fields %}
{% if field.unique and not field.primary_key %}
def get_{{ model.name|snake_case }}_by_{{ field.name }}(db: Session, {{ field.name }}: str) -> Optional[{{ model.name|pascal_case }}]:
    """Get {{ model.name }} by {{ field.name }}"""
    return db.query({{ model.name|pascal_case }}).filter({{ model.name|pascal_case }}.{{ field.name }} == {{ field.name }}).first()


{% endif %}
{%- endfor %}

def get_all_{{ model.plural_snake }}(
    db: Session,
    skip: int = 0,
    limit: int = 100,
{% for rel in model.owned_relationships %}
    {{ rel.fk_column }}: Optional[int] = None,
{% endfor %}
) -> List[{{ model.name|pascal_case }}]:
    """Get all {{ model.name }}s with pagination"""
    query = db.query({{ model.name|pascal_case }})
{% for rel in model.many_to_many_relationships %}
    query = query.options(selectinload({{ model.name|pascal_case }}.{{ rel.attribute }}))
{% endfor %}
{% for rel in model.owned_relationships %}
    if {{ rel.fk_column }} is not None:
        query = query.filter({{ model.name|pascal_case }}.{{ rel.fk_column }} == {{ rel.fk_column }})
{% endfor %}
    return query.offset(skip).limit(limit).all()


def update_{{ model.name|snake_case }}(db: Session, {{ model.name|snake_case }}_id: int, update_data: dict) -> Optional[{{ model.name|pascal_case }}]:
    """Update {{ model.name }}"""
    {{ model.name|snake_case }} = get_{{ model.name|snake_case }}_by_id(db, {{ model.name|snake_case }}_id)
    if {{ model.name|snake_case }}:
        for key, value in update_data.items():
            setattr({{ model.name|snake_case }}, key, value)
        db.commit()
        db.refresh({{ model.name|snake_case }})
    return {{ model.name|snake_case }}


def delete_{{ model.name|snake_case }}(db: Session, {{ model.name|snake_case }}_id: int) -> bool:
    """Delete {{ model.name }}"""
    {{ model.name|snake_case }} = get_{{ model.name|snake_case }}_by_id(db, {{ model.name|snake_case }}_id)
    if {{ model.name|snake_case }}:
        db.delete({{ model.name|snake_case }})
        db.commit()
        return True
    return False

{% endfor %}
```

Note `get_{{ model.name|snake_case }}_by_id` now builds a `query` variable instead of a one-line `db.query(...).filter(...).first()` — this is a deliberate, necessary change (needed to attach `.options(selectinload(...))` before filtering), not incidental churn.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_crud_generation.py -v`
Expected: PASS.

- [ ] **Step 5: Render and read the output by hand**

Run:
```bash
uv run backstudio generate backend/tests/fixtures/erd/valid_full.yml --output /tmp/rc_task3a --force
uv run backstudio generate backend/tests/fixtures/erd/many_to_many.yml --output /tmp/rc_task3b --force
uv run backstudio generate backend/tests/fixtures/erd/valid_minimal.yml --output /tmp/rc_task3c --force
```
Read all three `database/repo.py` files in full (the third has no relationships at all — confirm it's unchanged from before this task, no stray `selectinload`/filter code for an entity with none). `py_compile` all three.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/database/repo.py.jinja backend/tests/test_crud_generation.py
git commit -m "Add FK filter params and selectinload to generated repo functions"
```

---

### Task 4: `module_service.py.jinja` — FK existence validation + filter threading

**Files:**
- Modify: `backend/templates/Python/service/module_service.py.jinja`
- Test: `backend/tests/test_crud_generation.py`

**Interfaces:**
- Consumes: `entity.owned_relationships` (Task 1).
- Produces: `create_<x>`/`update_<x>` raise `ValueError` when a given FK id doesn't resolve via `repo.get_<target_snake>_by_id`; `list_<x>` gains the same FK filter params as Task 3's `repo.get_all_<plural>` and threads them through.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_crud_generation.py`:

```python
def test_service_create_validates_owned_relationship_fk_exists(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")  # Product has many-to-one to Category
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "catalog" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)

    create_start = service_src.index("def create_product(")
    create_end = service_src.index("\n    def ", create_start + 1)
    create_src = service_src[create_start:create_end]
    assert 'data.get("category_id")' in create_src
    assert "repo.get_category_by_id(db, data[" in create_src
    assert "raise ValueError(" in create_src

    update_start = service_src.index("def update_product(")
    update_end = service_src.index("\n    def ", update_start + 1)
    assert "raise ValueError(" in service_src[update_start:update_end]


def test_service_create_and_update_actually_reject_bad_fk_at_runtime(tmp_path):
    """Reuses _GeneratedProjectImporter - see the note on the analogous repo-level
    test in Task 3 for why (module purge safety)."""
    from backend.tests.test_generated_project_runtime import _GeneratedProjectImporter

    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        database_base = importlib.import_module("database.base")
        catalog_service = importlib.import_module("modules.catalog.service")

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        database_base.Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        service = catalog_service.get_catalog_service()

        import pytest
        with pytest.raises(ValueError):
            service.create_product(db, {"name": "Widget", "price": 9.99, "sku": "W1", "category_id": 999})


def test_service_list_accepts_owned_relationship_filter(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "catalog" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)

    list_start = service_src.index("def list_products(")
    list_end = service_src.index("\n    def ", list_start + 1)
    list_src = service_src[list_start:list_end]
    assert "category_id: Optional[int] = None" in list_src
    assert "category_id=category_id" in list_src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_crud_generation.py -k "service_create_validates or service_create_and_update or service_list_accepts" -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Rewrite the per-entity method block in `backend/templates/Python/service/module_service.py.jinja` (the `{% for entity in module.entities %}...{% endfor %}` loop; everything before and after it is unchanged):

```jinja
{% for entity in module.entities %}
    def create_{{ entity.snake_name }}(self, db: Session, data: dict) -> {{ entity.name }}:
{% for rel in entity.owned_relationships %}
        if data.get("{{ rel.fk_column }}") is not None and repo.get_{{ rel.target_snake }}_by_id(db, data["{{ rel.fk_column }}"]) is None:
            raise ValueError(f"{{ rel.target_model }} {data['{{ rel.fk_column }}']} not found")
{% endfor %}
        return repo.create_{{ entity.snake_name }}(db, data)

    def list_{{ entity.plural_snake }}(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
{% for rel in entity.owned_relationships %}
        {{ rel.fk_column }}: Optional[int] = None,
{% endfor %}
    ) -> List[{{ entity.name }}]:
        return repo.get_all_{{ entity.plural_snake }}(db, skip=skip, limit=limit{% for rel in entity.owned_relationships %}, {{ rel.fk_column }}={{ rel.fk_column }}{% endfor %})

    def get_{{ entity.snake_name }}(self, db: Session, item_id: int) -> Optional[{{ entity.name }}]:
        return repo.get_{{ entity.snake_name }}_by_id(db, item_id)

    def update_{{ entity.snake_name }}(self, db: Session, item_id: int, data: dict) -> Optional[{{ entity.name }}]:
{% for rel in entity.owned_relationships %}
        if data.get("{{ rel.fk_column }}") is not None and repo.get_{{ rel.target_snake }}_by_id(db, data["{{ rel.fk_column }}"]) is None:
            raise ValueError(f"{{ rel.target_model }} {data['{{ rel.fk_column }}']} not found")
{% endfor %}
        return repo.update_{{ entity.snake_name }}(db, item_id, data)

{% endfor %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_crud_generation.py -v`
Expected: PASS.

- [ ] **Step 5: Render and read the output by hand**

Run:
```bash
uv run backstudio generate backend/tests/fixtures/erd/valid_full.yml --output /tmp/rc_task4a --force
uv run backstudio generate backend/tests/fixtures/erd/valid_minimal.yml --output /tmp/rc_task4b --force
```
Read `modules/catalog/service.py` in both. Confirm `Category`'s own service methods (which has no `owned_relationships`) are untouched/normal, and `Product`'s methods have the new validation/filter code correctly indented. `py_compile` both.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/service/module_service.py.jinja backend/tests/test_crud_generation.py
git commit -m "Validate owned-relationship FKs on create/update, thread filter through list"
```

---

### Task 5: `module_routes.py.jinja` — map `ValueError` to 400, add filter query param

**Files:**
- Modify: `backend/templates/Python/service/module_routes.py.jinja`
- Test: `backend/tests/test_crud_generation.py`

**Interfaces:**
- Consumes: `entity.owned_relationships` (Task 1), `service.create_<x>`/`update_<x>` raising `ValueError` (Task 4), `service.list_<x>` accepting FK filter kwargs (Task 4).
- Produces: `create_<x>_route`/`update_<x>_route` catch `ValueError` → `HTTPException(400, ...)` only when the entity has `owned_relationships`; `list_<x>_route` gains the matching query param(s).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_crud_generation.py`:

```python
def test_routes_map_valueerror_to_400_only_when_entity_has_owned_relationships(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")  # Product owns a FK, Category doesn't
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "catalog" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)

    product_create_start = routes_src.index("def create_product_route(")
    product_create_end = routes_src.index("\n@router", product_create_start)
    product_create_src = routes_src[product_create_start:product_create_end]
    assert "except ValueError as exc:" in product_create_src
    assert "status.HTTP_400_BAD_REQUEST" in product_create_src

    category_create_start = routes_src.index("def create_category_route(")
    category_create_end = routes_src.index("\n@router", category_create_start)
    category_create_src = routes_src[category_create_start:category_create_end]
    assert "except ValueError" not in category_create_src


def test_list_route_gets_owned_relationship_query_param(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "catalog" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)

    list_start = routes_src.index("def list_product_route(")
    list_end = routes_src.index("\n@router", list_start)
    list_src = routes_src[list_start:list_end]
    assert "category_id: Optional[int] = Query(None)" in list_src
    assert "category_id=category_id" in list_src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_crud_generation.py -k "map_valueerror or query_param" -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `backend/templates/Python/service/module_routes.py.jinja`:

1. Change the imports line:

```jinja
{% set has_owned_rel = (module.entities|map(attribute='owned_relationships')|map('length')|sum) > 0 %}
from typing import List{% if has_owned_rel %}, Optional{% endif +%}
```

2. Change the `create` block:

```jinja
{% if 'create' in entity.enabled_actions %}
@router.post(
    "{{ entity.base_path }}",
    response_model={{ entity.name }}Response,
    status_code=status.HTTP_201_CREATED,
    summary="Create {{ entity.name }}",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac['create'] %}
    dependencies=[Depends(require_roles({% for role in entity.rbac['create'] %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def create_{{ entity.snake_name }}_route(
    payload: {{ entity.name }}Create,
    db: Session = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> {{ entity.name }}Response:
{% if entity.owned_relationships %}
    try:
        return service.create_{{ entity.snake_name }}(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
{% else %}
    return service.create_{{ entity.snake_name }}(db, payload.model_dump())
{% endif %}
{% endif %}
```

3. Change the `list` block:

```jinja
{% if 'list' in entity.enabled_actions %}
@router.get(
    "{{ entity.base_path }}",
    response_model=List[{{ entity.name }}Response],
    summary="List {{ entity.name }} records",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac['list'] %}
    dependencies=[Depends(require_roles({% for role in entity.rbac['list'] %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def list_{{ entity.snake_name }}_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
{% for rel in entity.owned_relationships %}
    {{ rel.fk_column }}: Optional[int] = Query(None),
{% endfor %}
    db: Session = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> List[{{ entity.name }}Response]:
    return service.list_{{ entity.plural_snake }}(db, skip=skip, limit=limit{% for rel in entity.owned_relationships %}, {{ rel.fk_column }}={{ rel.fk_column }}{% endfor %})
{% endif %}
```

4. Change the `update` block:

```jinja
{% if 'update' in entity.enabled_actions %}
@router.put(
    "{{ entity.base_path }}/{item_id}",
    response_model={{ entity.name }}Response,
    summary="Update {{ entity.name }}",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac['update'] %}
    dependencies=[Depends(require_roles({% for role in entity.rbac['update'] %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
def update_{{ entity.snake_name }}_route(
    item_id: int,
    payload: {{ entity.name }}Update,
    db: Session = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> {{ entity.name }}Response:
{% if entity.owned_relationships %}
    try:
        item = service.update_{{ entity.snake_name }}(db, item_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
{% else %}
    item = service.update_{{ entity.snake_name }}(db, item_id, payload.model_dump(exclude_unset=True))
{% endif %}
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{{ entity.name }} not found")
    return item
{% endif %}
```

The `create`/`read`/`delete` blocks not listed above (i.e. `read`, `delete`, and the schemas-import/router-setup preamble) are unchanged from the current template.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_crud_generation.py -v`
Expected: PASS.

- [ ] **Step 5: Render and read the output by hand**

Run: `uv run backstudio generate backend/tests/fixtures/erd/valid_full.yml --output /tmp/rc_task5 --force`
Read `modules/catalog/routes.py` in full. Confirm `Category`'s routes (no owned relationships) are unchanged from before this task, `Product`'s create/list/update routes have the new code correctly indented, and the entity-to-entity blank-line spacing (fixed earlier this session) is still intact. `py_compile` it.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/service/module_routes.py.jinja backend/tests/test_crud_generation.py
git commit -m "Map FK validation errors to 400 and add relationship filter query params to routes"
```

---

### Task 6: Real HTTP+DB round-trip tests

**Files:**
- Modify: `backend/tests/test_generated_project_runtime.py`

**Interfaces:**
- Consumes: the fully wired generated app from Tasks 2-5, via `TestClient` (matching the existing tests in this file).

- [ ] **Step 1: Read the existing file's fixtures/setup helpers first**

Read `backend/tests/test_generated_project_runtime.py` in full before writing anything (it is reproduced in this plan's research notes, but read the real file — it may have changed). Reuse `_GeneratedProjectImporter`, the `isolated_sys_path` fixture, `monkeypatch.setenv("DATABASE_URL", ...)`, and `importlib.import_module("server")` → `TestClient(server_module.app)` exactly as the three existing tests in that file already do. Do not invent a new helper.

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/test_generated_project_runtime.py`:

```python
def test_owned_relationship_fk_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """valid_full.yml: Product has many-to-one to Category. Covers the FK
    exposure + validation + filter query param all the way through real HTTP.
    No auth involved, so no JWT_SECRET env var needed.
    """
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "fk_runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            cat_resp = client.post("/categories", json={"name": "Electronics"})
            assert cat_resp.status_code == 201, cat_resp.text
            category_id = cat_resp.json()["id"]

            # valid FK: succeeds, response includes category_id
            ok_resp = client.post(
                "/products", json={"name": "Widget", "price": 9.99, "sku": "W1", "category_id": category_id}
            )
            assert ok_resp.status_code == 201, ok_resp.text
            assert ok_resp.json()["category_id"] == category_id

            # invalid FK: 400, not a raw 500
            bad_resp = client.post(
                "/products", json={"name": "Gadget", "price": 5.0, "sku": "G1", "category_id": 999999}
            )
            assert bad_resp.status_code == 400, bad_resp.text

            # a second category + product, to prove the filter actually filters
            cat2_resp = client.post("/categories", json={"name": "Books"})
            category2_id = cat2_resp.json()["id"]
            client.post(
                "/products", json={"name": "Novel", "price": 12.0, "sku": "N1", "category_id": category2_id}
            )

            filtered_resp = client.get(f"/products?category_id={category_id}")
            assert filtered_resp.status_code == 200, filtered_resp.text
            names = [p["name"] for p in filtered_resp.json()]
            assert names == ["Widget"]


def test_many_to_many_id_list_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """many_to_many.yml: Post<->Tag. No auth, no rbac."""
    erd = load_erd(f"{FIXTURES}/many_to_many.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "m2m_runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        database_base = importlib.import_module("database.base")
        database_models = importlib.import_module("database.models")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            post_resp = client.post("/posts", json={"title": "Hello"})
            assert post_resp.status_code == 201, post_resp.text
            post_id = post_resp.json()["id"]
            assert post_resp.json()["tag_ids"] == []

            tag1_resp = client.post("/tags", json={"name": "python"})
            tag2_resp = client.post("/tags", json={"name": "fastapi"})
            tag1_id, tag2_id = tag1_resp.json()["id"], tag2_resp.json()["id"]

            # link tags directly via the ORM - there is no write endpoint for
            # many-to-many (out of scope per spec ยง2)
            db = database_base.SessionLocal()
            try:
                post_obj = db.query(database_models.Post).filter(database_models.Post.id == post_id).first()
                tag_objs = (
                    db.query(database_models.Tag)
                    .filter(database_models.Tag.id.in_([tag1_id, tag2_id]))
                    .all()
                )
                post_obj.tags.extend(tag_objs)
                db.commit()
            finally:
                db.close()

            get_resp = client.get(f"/posts/{post_id}")
            assert get_resp.status_code == 200, get_resp.text
            assert sorted(get_resp.json()["tag_ids"]) == sorted([tag1_id, tag2_id])

            list_resp = client.get("/posts")
            assert list_resp.status_code == 200, list_resp.text
            listed_post = next(p for p in list_resp.json() if p["id"] == post_id)
            assert sorted(listed_post["tag_ids"]) == sorted([tag1_id, tag2_id])


def test_cross_module_owned_relationship_validates_against_shared_repo(tmp_path, monkeypatch, isolated_sys_path):
    """shophub_mini.yml: Order (in the 'ordering' module) has many-to-one to Product
    (in 'catalog') and to User (the auth entity) - proves FK validation works when
    the target's CRUD lives in a different module, and when the target is the
    auth-managed User entity, both via the one shared repo.py.
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "cross_module_runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            register_resp = client.post(
                "/auth/register", json={"email": "a@example.com", "password": "supersecret123"}
            )
            assert register_resp.status_code == 201, register_resp.text
            user_id = register_resp.json()["id"]

            login_resp = client.post(
                "/auth/login", json={"email": "a@example.com", "password": "supersecret123"}
            )
            admin_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

            cat_resp = client.post("/categories", json={"name": "Gadgets"}, headers=admin_headers)
            assert cat_resp.status_code == 201, cat_resp.text
            category_id = cat_resp.json()["id"]

            prod_resp = client.post(
                "/products",
                json={"name": "Thing", "price": 1.0, "sku": "T1", "category_id": category_id},
                headers=admin_headers,
            )
            assert prod_resp.status_code == 201, prod_resp.text
            product_id = prod_resp.json()["id"]

            ok_resp = client.post(
                "/orders",
                json={
                    "status": "pending",
                    "total_amount": 1.0,
                    "user_id": user_id,
                    "product_id": product_id,
                },
                headers=admin_headers,
            )
            assert ok_resp.status_code == 201, ok_resp.text

            bad_resp = client.post(
                "/orders",
                json={
                    "status": "pending",
                    "total_amount": 1.0,
                    "user_id": user_id,
                    "product_id": 999999,
                },
                headers=admin_headers,
            )
            assert bad_resp.status_code == 400, bad_resp.text
```

`shophub_mini.yml`'s `Product` RBAC config restricts `create`/`update`/`delete` to `admin` (see the fixture) — the first user registered gets every declared role including `admin` (confirmed bootstrap behavior, see `test_module_crud_round_trip_against_real_generated_app` in this same file), so `admin_headers` is sufficient for every write in this test.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_generated_project_runtime.py -k "owned_relationship_fk_round_trip or many_to_many_id_list_round_trip or cross_module_owned" -v`
Expected: FAIL if any prior task's implementation has a bug this integration test surfaces — if so, that's a real bug, go fix it in the relevant task's template (do not weaken this test). If Tasks 1-5 are fully correct, some of these may already pass on first run; that's fine, still keep them.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_generated_project_runtime.py -v`
Expected: PASS, all tests in the file (existing + 3 new).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_generated_project_runtime.py
git commit -m "Add real HTTP+DB round-trip tests for relationship CRUD exposure"
```

---

### Task 7: Documentation + backlog close-out

**Files:**
- Modify: `docs/superpowers/backlog.md`
- Modify: `README.md` (root repo README's ERD YAML reference, if it documents generated schema shape anywhere)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update the backlog**

In `docs/superpowers/backlog.md`, find the "Relationships are invisible to the generated CRUD API" item under "Architectural" and check it off, appending a short summary of what shipped (mirroring the style of other closed-out items in that file): the two new derived fields in `translate.py`, the four templates changed, and a one-line pointer to this plan file and the spec file.

- [ ] **Step 2: Check the root README for stale claims**

Search `README.md` for any prior mention of relationships not being exposed in the API, or any example output that would now be stale (e.g. a shown `PostResponse` without `category_id`, if one exists). Read the file in full first — don't grep-and-guess. Update anything that's now inaccurate; this file has historically been kept accurate against real generated output (per this session's established convention), so verify any changed example by actually generating it, not by editing from memory.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/backlog.md README.md
git commit -m "Close out relationship-CRUD-exposure backlog item, update docs"
```
