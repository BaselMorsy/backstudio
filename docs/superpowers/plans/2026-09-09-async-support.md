# Async Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a whole-project, opt-in `database.async_mode` toggle that generates a real async SQLAlchemy stack — async engine/session, a repo layer rewritten onto the 2.0-style `select()`/`execute()` API, and `async def`/`await` propagated through service methods, route handlers, and the auth module — while leaving today's sync output byte-for-byte unchanged when the flag is omitted.

**Architecture:** One new boolean ERD field (`database.async_mode`, default `false`) flows unchanged through `translate.py` into every template as `project.database_config.async_mode`. `database/repo.py.jinja` gets a full per-function sync/async branch (the query APIs are genuinely different, not just decorated). `module_service.py.jinja`, `module_routes.py.jinja`, and the auth templates get *surgical* inline branches (`{{ 'async ' if is_async }}`, `{{ 'await ' if is_async }}`) rather than full duplication, since those files interleave real business logic (RBAC dependencies, FK-existence validation, password hashing) that should never exist as two independently-maintained copies. `database/base.py.jinja` and `alembic/env.py.jinja` get full top-level sync/async splits (no shared logic there worth preserving un-duplicated). `translate.py` and `database/models.py.jinja` need zero changes.

**Tech Stack:** Python 3.11, Jinja2 (trim_blocks/lstrip_blocks — see Global Constraints), SQLAlchemy 2.0.23 (both the legacy `Query` API and the `sqlalchemy.ext.asyncio` extension, already installed), `aiosqlite`/`asyncpg`/`aiomysql`, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-async-support-design.md`

## Global Constraints

- `database.async_mode` is a whole-project boolean, default `false`. Every existing ERD/fixture/generated project must keep producing byte-identical sync output when it's omitted — this is the load-bearing guarantee behind calling the feature "opt-in", and every task below includes a check for it.
- `translate.py` and `database/models.py.jinja` get **zero** changes in this plan. If a task's implementer finds themselves wanting to touch either file, stop and report — that means something in this plan's understanding of the data flow is wrong.
- The inline-conditional-expression idiom `{{ "async " if is_async }}` / `{{ "await " if is_async }}` renders as an empty string when `is_async` is false (verified directly against this codebase's exact Jinja environment settings before this plan was written — not assumed). Use it for `module_service.py.jinja`, `module_routes.py.jinja`, and the auth templates. Do **not** introduce Jinja macros anywhere (this codebase has never used them).
- `database/repo.py.jinja` uses a full `{% if project.database_config.async_mode %}...{% else %}...{% endif %}` pair **per function** (not a whole-file split) — its query-building logic is genuinely different between the two APIs, so this isn't duplicating shared logic, it's two real implementations of the same operation.
- `database/base.py.jinja` and `alembic/env.py.jinja` use a full top-level `{% if %}...{% else %}...{% endif %}` split (their sync/async engine setup shares nothing worth preserving un-duplicated).
- **`AsyncSession.delete(x)` must be awaited** — verified directly against a real SQLAlchemy async engine before this plan was written: without `await`, the delete call returns an un-awaited coroutine whose body never runs, so the row silently never gets deleted (Python only emits a `RuntimeWarning`, never an error). `db.add(x)` stays a plain synchronous call in both APIs — do not await it.
- **Engine disposal on shutdown is a correctness requirement, not optional cleanup.** Verified directly: the async engine's driver (`aiosqlite` specifically) leaves a background thread running unless the engine is explicitly disposed, which — left unaddressed — hangs not one test but the entire `pytest` process at the very end of a full suite run, after every individual test has already passed. `server.py.jinja`'s `lifespan` context manager already has an empty shutdown section reserved for exactly this; async mode fills it with `await engine.dispose()`.
- Every template task's Jinja changes must be verified by actually rendering against a real fixture and reading the output — not just eyeballing the template source (this has bitten every template touched in this codebase's history so far; `ast.parse`/`py_compile` alone does not catch a merged-together field list or a missing `await`, only outright syntax errors).
- `aiosqlite` is already a real dev dependency of this repo (both `[project.optional-dependencies].dev` and `[dependency-groups].dev` in `pyproject.toml`) — needed because `backend/tests/test_generated_project_runtime.py` imports and runs generated code directly against this repo's own venv, not a fresh install of the generated project's own `requirements.txt`.

---

### Task 1: ERD schema field + data-flow confirmation

**Files:**
- Modify: `backend/erd/schema.py`
- Test: `backend/tests/test_erd_schema.py`, `backend/tests/test_erd_translate.py`

**Interfaces:**
- Produces: `DatabaseSpec.async_mode: bool` (default `False`), which `translate()` already passes through unchanged as `state["database_config"]["async_mode"]` (via the existing `erd.database.model_dump(mode='json')` call — no `translate.py` edit needed, this task just proves that's true).
- Consumed by: every later task's templates, as `project.database_config.async_mode`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_erd_schema.py` (check the file first for its exact existing style/imports and match them):

```python
def test_database_async_mode_defaults_to_false():
    spec = DatabaseSpec(type="sqlite", database_name="d.db")
    assert spec.async_mode is False


def test_database_async_mode_can_be_enabled():
    spec = DatabaseSpec(type="sqlite", database_name="d.db", async_mode=True)
    assert spec.async_mode is True
```

Add to `backend/tests/test_erd_translate.py` (uses the existing direct-`ERDConfig`-construction style already in this file):

```python
def test_translate_passes_database_async_mode_through():
    erd = ERDConfig(
        project=ProjectMeta(name="Demo", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="d.db", async_mode=True),
        entities=[
            EntitySpec(
                name="Widget",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
        ],
        services=[ServiceDecl(name="widgets", entities=["Widget"])],
    )
    state = translate(erd)
    assert state["database_config"]["async_mode"] is True


def test_translate_database_async_mode_defaults_false():
    erd = ERDConfig(
        project=ProjectMeta(name="Demo", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="d.db"),
        entities=[
            EntitySpec(
                name="Widget",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
        ],
        services=[ServiceDecl(name="widgets", entities=["Widget"])],
    )
    state = translate(erd)
    assert state["database_config"]["async_mode"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_erd_schema.py backend/tests/test_erd_translate.py -k "async_mode" -v`
Expected: FAIL — `DatabaseSpec` has no `async_mode` field yet (Pydantic will reject the keyword argument, or `state["database_config"]` won't have the key).

- [ ] **Step 3: Implement**

In `backend/erd/schema.py`, add `async_mode: bool = False` to `DatabaseSpec`:

```python
class DatabaseSpec(BaseModel):
    type: CliDatabaseType
    host: Optional[str] = "localhost"
    port: Optional[int] = None
    database_name: str
    username: Optional[str] = None
    use_env_vars: bool = True
    pool_size: int = 10
    echo: bool = False
    async_mode: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_erd_schema.py backend/tests/test_erd_translate.py -v`
Expected: PASS (all tests in both files).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS, same count as before plus 4.

- [ ] **Step 6: Commit**

```bash
git add backend/erd/schema.py backend/tests/test_erd_schema.py backend/tests/test_erd_translate.py
git commit -m "Add database.async_mode ERD field, confirm it flows through translate() unchanged"
```

---

### Task 2: Database connection layer — engine, session, config, drivers, shutdown

**Files:**
- Modify: `backend/templates/Python/database/base.py.jinja`
- Modify: `backend/templates/Python/config.py.jinja`
- Modify: `backend/templates/Python/requirements.txt.jinja`
- Modify: `backend/templates/Python/server.py.jinja`
- Create: `backend/tests/fixtures/erd/async_minimal.yml`
- Create: `backend/tests/fixtures/erd/async_postgresql.yml`
- Create: `backend/tests/fixtures/erd/async_mysql.yml`
- Test: `backend/tests/test_crud_generation.py` (or a new `backend/tests/test_async_generation.py` — see Step 1, this task creates that file since it's the first async-specific generation test)

**Interfaces:**
- Consumes: `project.database_config.async_mode`, `project.database_config.type` (Task 1, already merged).
- Produces: the `engine`/`get_db`/`init_db` symbols every later task's templates depend on (`database.base` module), and the `DATABASE_URL` default/example every later task's docs reference.

- [ ] **Step 1: Create the fixtures**

Create `backend/tests/fixtures/erd/async_minimal.yml`:

```yaml
project:
  name: AsyncMinimal
  version: "1.0.0"

database:
  type: sqlite
  database_name: async_minimal.db
  async_mode: true

entities:
  - name: Widget
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: label, type: string}

services:
  - name: widgets
    entities: [Widget]
```

Create `backend/tests/fixtures/erd/async_postgresql.yml`:

```yaml
project:
  name: AsyncPostgres
  version: "1.0.0"

database:
  type: postgresql
  database_name: async_pg.db
  async_mode: true

entities:
  - name: Widget
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: label, type: string}

services:
  - name: widgets
    entities: [Widget]
```

Create `backend/tests/fixtures/erd/async_mysql.yml`:

```yaml
project:
  name: AsyncMysql
  version: "1.0.0"

database:
  type: mysql
  database_name: async_mysql.db
  async_mode: true

entities:
  - name: Widget
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: label, type: string}

services:
  - name: widgets
    entities: [Widget]
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_async_generation.py`:

```python
import ast
import subprocess
import sys

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_sync_output_unchanged_when_async_mode_omitted(tmp_path):
    """valid_minimal.yml has no async_mode key at all - this is the load-bearing
    'opt-in' regression check for this task's four touched files.
    """
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)
    assert state["database_config"]["async_mode"] is False

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    base_src = (codebase_dir / "database" / "base.py").read_text(encoding="utf-8")
    assert "create_async_engine" not in base_src
    assert "AsyncSession" not in base_src
    assert "def get_db():" in base_src
    assert "async def get_db():" not in base_src

    config_src = (codebase_dir / "config.py").read_text(encoding="utf-8")
    assert "sqlite:///./demo.db" in config_src
    assert "aiosqlite" not in config_src

    requirements_src = (codebase_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "aiosqlite" not in requirements_src

    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    assert "engine.dispose()" not in server_src
    assert "init_db()" in server_src
    assert "await init_db()" not in server_src


def test_async_sqlite_base_py_renders_async_engine_and_session(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    base_src = (codebase_dir / "database" / "base.py").read_text(encoding="utf-8")
    ast.parse(base_src)
    assert "from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker" in base_src
    assert "create_async_engine(settings.DATABASE_URL" in base_src
    assert "async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)" in base_src
    assert "async def get_db():" in base_src
    assert "async with AsyncSessionLocal() as session:" in base_src
    assert "async def init_db():" in base_src
    assert "await conn.run_sync(Base.metadata.create_all)" in base_src
    assert "db.query(" not in base_src

    config_src = (codebase_dir / "config.py").read_text(encoding="utf-8")
    ast.parse(config_src)
    assert "sqlite+aiosqlite:///./async_minimal.db" in config_src

    requirements_src = (codebase_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "aiosqlite" in requirements_src

    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    ast.parse(server_src)
    assert "await init_db()" in server_src
    assert "from database.base import engine, init_db" in server_src
    assert "await engine.dispose()" in server_src


def test_async_postgresql_requirements_use_asyncpg_not_psycopg2(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_postgresql.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    requirements_src = (codebase_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "asyncpg" in requirements_src
    assert "psycopg2-binary" not in requirements_src

    config_src = (codebase_dir / "config.py").read_text(encoding="utf-8")
    assert "postgresql+asyncpg" not in config_src  # only the sqlite default fallback is templated; see Step 3 note


def test_async_mysql_requirements_use_aiomysql_not_pymysql(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_mysql.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    requirements_src = (codebase_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "aiomysql" in requirements_src
    assert "pymysql" not in requirements_src
    assert "cryptography" not in requirements_src


def test_async_minimal_byte_compiles(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(codebase_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_async_minimal_engine_actually_runs_and_disposes_cleanly(tmp_path):
    """The strongest check for this task: actually import the rendered database/base.py
    and drive it against a real aiosqlite engine - create a table, insert a row via
    a raw model instance, query it back, and dispose the engine. This is exactly the
    sequence that hung a real Python process during this plan's own design verification
    when engine.dispose() was missing - if base.py.jinja's async branch is wrong in a way
    that leaves the engine undisposed, this test's own process will hang, not just fail.
    """
    import asyncio

    erd = load_erd(f"{FIXTURES}/async_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "engine_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        database_models = importlib.import_module("database.models")

        async def run():
            await database_base.init_db()
            async with database_base.AsyncSessionLocal() as session:
                widget = database_models.Widget(label="test")
                session.add(widget)
                await session.commit()
                await session.refresh(widget)
                assert widget.id is not None
            await database_base.engine.dispose()

        asyncio.run(run())
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "config":
                sys.modules.pop(mod_name, None)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_async_generation.py -v`
Expected: all FAIL except `test_sync_output_unchanged_when_async_mode_omitted` (which should already PASS, since nothing's changed yet — if it fails, stop and report, that means Task 1 or the current baseline is broken).

- [ ] **Step 4: Implement — `database/base.py.jinja`**

Full new file:

```jinja
"""{{ project.name }} - Database base configuration"""

{% if project.database_config.async_mode %}
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from config import settings

# Create async database engine
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

# Create async session factory
#
# expire_on_commit=False is required, not cosmetic: without it, accessing an
# attribute on a committed object outside an active `async with` block (e.g.
# after `await db.refresh(x)` returns) can trigger SQLAlchemy's implicit-IO
# path, which raises under AsyncSession (no implicit greenlet-free IO is
# allowed) instead of transparently re-fetching the way sync Session would.
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Create declarative base
Base = declarative_base()


async def get_db():
    """
    Dependency to get an async database session

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize database - create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
{% else %}
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from config import settings

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base
Base = declarative_base()


def get_db():
    """
    Dependency to get database session

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database - create all tables"""
    Base.metadata.create_all(bind=engine)
{% endif %}
```

- [ ] **Step 5: Implement — `config.py.jinja`**

Change only the `DATABASE_URL` default. Current line (inside the `Settings` class):

```python
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./{{ project.name|snake_case }}.db"  # Default to SQLite for easy testing
    )
```

New:

```python
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "{% if project.database_config.async_mode %}sqlite+aiosqlite{% else %}sqlite{% endif %}:///./{{ project.name|snake_case }}.db"  # Default to SQLite for easy testing
    )
```

(This default fallback is always SQLite regardless of `project.database_config.type` — that's pre-existing behavior, unrelated to this plan; only the driver-qualification of that SQLite fallback changes. A user with `database.type: postgresql`/`mysql` already has to set `DATABASE_URL` themselves via `.env`/env var, same as today — the async-driver-qualified scheme for THEIR chosen type is documented in Task 9's README update, not templated here.)

- [ ] **Step 6: Implement — `requirements.txt.jinja`**

Current database-dependencies block:

```jinja
{% if project.database_config %}
# Database dependencies
{% if project.database_config.type == 'postgresql' %}
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
alembic==1.13.0
{% elif project.database_config.type == 'mysql' %}
sqlalchemy==2.0.23
pymysql==1.1.0
cryptography==41.0.7
alembic==1.13.0
{% elif project.database_config.type == 'sqlite' %}
sqlalchemy==2.0.23
aiosqlite==0.19.0
alembic==1.13.0
{% elif project.database_config.type == 'mongodb' %}
motor==3.3.2
pymongo==4.6.1
{% endif %}
{% endif %}
```

New (the `sqlite` branch's `aiosqlite` line moves under the `async_mode` conditional instead of being unconditional dead weight on the sync path; `postgresql`/`mysql` branch on `async_mode` between their sync and async driver):

```jinja
{% if project.database_config %}
# Database dependencies
{% if project.database_config.type == 'postgresql' %}
sqlalchemy==2.0.23
{% if project.database_config.async_mode %}
asyncpg==0.29.0
{% else %}
psycopg2-binary==2.9.9
{% endif %}
alembic==1.13.0
{% elif project.database_config.type == 'mysql' %}
sqlalchemy==2.0.23
{% if project.database_config.async_mode %}
aiomysql==0.2.0
{% else %}
pymysql==1.1.0
cryptography==41.0.7
{% endif %}
alembic==1.13.0
{% elif project.database_config.type == 'sqlite' %}
sqlalchemy==2.0.23
{% if project.database_config.async_mode %}
aiosqlite==0.19.0
{% endif %}
alembic==1.13.0
{% elif project.database_config.type == 'mongodb' %}
motor==3.3.2
pymongo==4.6.1
{% endif %}
{% endif %}
```

(The `mongodb` branch is pre-existing dead code from the legacy UI flow — `CliDatabaseType` doesn't even include `mongodb` as a valid CLI value, so this branch is unreachable from the ERD CLI pipeline. Leave it untouched; it's in scope for the repo-cleanup backlog item, not this plan.)

- [ ] **Step 7: Implement — `server.py.jinja`**

Current:

```python
from database.base import init_db
...
# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown (if cleanup needed)
    pass
```

New:

```jinja
from database.base import {% if project.database_config.async_mode %}engine, {% endif %}init_db
...
# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    {{ 'await ' if project.database_config.async_mode }}init_db()
    yield
    # Shutdown
{% if project.database_config.async_mode %}
    await engine.dispose()
{% else %}
    pass
{% endif %}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_async_generation.py -v`
Expected: PASS, all 6 tests (the live-engine test in particular must complete without hanging — if it hangs, `engine.dispose()` isn't wired correctly; do not weaken the test, fix the template).

- [ ] **Step 9: Render and read the output by hand**

Run:
```bash
uv run backstudio generate backend/tests/fixtures/erd/async_minimal.yml --output /tmp/rc_async_task2a --force
uv run backstudio generate backend/tests/fixtures/erd/valid_minimal.yml --output /tmp/rc_async_task2b --force
```
Read `database/base.py`, `config.py`, `requirements.txt`, and `server.py` in full for both. Confirm the async render has no leftover sync `Query`-API text and no whitespace glue damage (blank-line structure matches the original sync template's spacing); confirm the sync render (`valid_minimal.yml`, no `async_mode` key at all) is completely unchanged from before this task. `py_compile` both.

- [ ] **Step 10: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add backend/templates/Python/database/base.py.jinja backend/templates/Python/config.py.jinja backend/templates/Python/requirements.txt.jinja backend/templates/Python/server.py.jinja backend/tests/fixtures/erd/async_minimal.yml backend/tests/fixtures/erd/async_postgresql.yml backend/tests/fixtures/erd/async_mysql.yml backend/tests/test_async_generation.py
git commit -m "Add async engine/session/config/driver/shutdown support behind database.async_mode"
```

---

### Task 3: Repo layer rewrite — `database/repo.py.jinja`

**Files:**
- Modify: `backend/templates/Python/database/repo.py.jinja`
- Create: `backend/tests/fixtures/erd/async_relationships.yml`
- Test: `backend/tests/test_async_generation.py`

**Interfaces:**
- Consumes: `project.database_config.async_mode` (Task 1); `model.owned_relationships`/`model.many_to_many_relationships` (pre-existing, from the relationship-CRUD-exposure work — unchanged by this plan).
- Produces: every `repo.py` function's async signature/behavior that Tasks 4 and 6 call into.

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/erd/async_relationships.yml` (mirrors `combined_relationships.yml`'s shape — one entity with both an owned relationship and a many-to-many — plus `async_mode: true`, so this one fixture exercises every branch `repo.py.jinja` has: the plain CRUD path, the owned-relationship FK filter, and the many-to-many `selectinload`):

```yaml
project:
  name: AsyncRelationships
  version: "1.0.0"

database:
  type: sqlite
  database_name: async_relationships.db
  async_mode: true

entities:
  - name: Author
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: name, type: string}

  - name: Tag
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: name, type: string}

  - name: Post
    fields:
      - {name: id, type: integer, primary_key: true}
      - {name: title, type: string, max_length: 200}
    relationships:
      - name: author
        cardinality: many-to-one
        target: Author
      - name: tags
        cardinality: many-to-many
        target: Tag

services:
  - name: content
    entities: [Author, Tag, Post]
```

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/test_async_generation.py`:

```python
def test_async_repo_uses_select_execute_not_query(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_relationships.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    ast.parse(repo_src)

    assert "from sqlalchemy import select" in repo_src
    assert "from sqlalchemy.ext.asyncio import AsyncSession" in repo_src
    assert ".query(" not in repo_src
    assert "db.query" not in repo_src

    create_start = repo_src.index("async def create_post(")
    create_end = repo_src.index("\nasync def get_post_by_id(")
    create_src = repo_src[create_start:create_end]
    assert "db.add(post)" in create_src
    assert "await db.commit()" in create_src
    assert "await db.refresh(post)" in create_src

    get_by_id_start = repo_src.index("async def get_post_by_id(")
    get_by_id_end = repo_src.index("\nasync def get_all_posts(")
    get_by_id_src = repo_src[get_by_id_start:get_by_id_end]
    assert "select(Post)" in get_by_id_src
    assert "selectinload(Post.tags)" in get_by_id_src
    assert "await db.execute(stmt)" in get_by_id_src
    assert "result.scalar_one_or_none()" in get_by_id_src

    get_all_start = repo_src.index("async def get_all_posts(")
    get_all_end = repo_src.index("\nasync def update_post(")
    get_all_src = repo_src[get_all_start:get_all_end]
    assert "author_id: Optional[int] = None" in get_all_src
    assert "selectinload(Post.tags)" in get_all_src
    assert "Post.author_id == author_id" in get_all_src
    assert "result.scalars().all()" in get_all_src

    delete_start = repo_src.index("async def delete_post(")
    delete_src = repo_src[delete_start:]
    assert "await db.delete(post)" in delete_src


def test_sync_repo_still_unchanged_when_async_mode_omitted(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    assert "from sqlalchemy.orm import Session" in repo_src
    assert "AsyncSession" not in repo_src
    assert "db.query(" in repo_src
    assert "select(" not in repo_src


def test_async_repo_functions_actually_run_against_a_real_db(tmp_path):
    """Live proof, matching the sync-path equivalent tests in this repo: create via
    the generated async repo, link a many-to-many tag, filter by the owned FK, then
    delete and confirm the row is actually gone - the exact case that would silently
    no-op if AsyncSession.delete() were called without await.
    """
    import asyncio

    erd = load_erd(f"{FIXTURES}/async_relationships.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "repo_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        database_models = importlib.import_module("database.models")
        repo = importlib.import_module("database.repo")

        async def run():
            await database_base.init_db()
            async with database_base.AsyncSessionLocal() as db:
                author1 = await repo.create_author(db, {"name": "Ada"})
                author2 = await repo.create_author(db, {"name": "Grace"})
                tag = await repo.create_tag(db, {"name": "python"})

                post = await repo.create_post(db, {"title": "Hello", "author_id": author1.id})
                await repo.create_post(db, {"title": "Other", "author_id": author2.id})

                fetched = await repo.get_post_by_id(db, post.id)
                assert fetched.title == "Hello"

                filtered = await repo.get_all_posts(db, author_id=author1.id)
                assert [p.title for p in filtered] == ["Hello"]

                # link the tag directly via the ORM relationship (no repo function
                # for many-to-many writes - matches the sync-path design)
                post_obj = await repo.get_post_by_id(db, post.id)
                post_obj.tags.append(tag)
                await db.commit()
                refetched = await repo.get_post_by_id(db, post.id)
                assert [t.name for t in refetched.tags] == ["python"]

                deleted = await repo.delete_post(db, post.id)
                assert deleted is True
                gone = await repo.get_post_by_id(db, post.id)
                assert gone is None
            await database_base.engine.dispose()

        asyncio.run(run())
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "config":
                sys.modules.pop(mod_name, None)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_async_generation.py -k "repo" -v`
Expected: FAIL (except the sync-unchanged test, which should already pass).

- [ ] **Step 4: Implement**

Full new file:

```jinja
"""{{ project.name }} - Database repository functions"""

{% set has_any_m2m = (project.data_models|map(attribute='many_to_many_relationships')|map('length')|sum) > 0 %}
from typing import Optional, List
{% if project.database_config.async_mode %}
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession{% if has_any_m2m %}
from sqlalchemy.orm import selectinload{% endif +%}
{% else %}
from sqlalchemy.orm import Session{% if has_any_m2m %}, selectinload{% endif +%}
{% endif %}

from .models import {% for model in project.data_models %}{{ model.name|pascal_case }}{{ ", " if not loop.last else "" }}{% endfor %}

{% for model in project.data_models %}

# {{ model.name|pascal_case }} Repository Functions

{% if project.database_config.async_mode %}
async def create_{{ model.name|snake_case }}(db: AsyncSession, {{ model.name|snake_case }}_data: dict) -> {{ model.name|pascal_case }}:
    """Create a new {{ model.name }}"""
    {{ model.name|snake_case }} = {{ model.name|pascal_case }}(**{{ model.name|snake_case }}_data)
    db.add({{ model.name|snake_case }})
    await db.commit()
    await db.refresh({{ model.name|snake_case }})
    return {{ model.name|snake_case }}
{% else %}
def create_{{ model.name|snake_case }}(db: Session, {{ model.name|snake_case }}_data: dict) -> {{ model.name|pascal_case }}:
    """Create a new {{ model.name }}"""
    {{ model.name|snake_case }} = {{ model.name|pascal_case }}(**{{ model.name|snake_case }}_data)
    db.add({{ model.name|snake_case }})
    db.commit()
    db.refresh({{ model.name|snake_case }})
    return {{ model.name|snake_case }}
{% endif %}


{% if project.database_config.async_mode %}
async def get_{{ model.name|snake_case }}_by_id(db: AsyncSession, {{ model.name|snake_case }}_id: int) -> Optional[{{ model.name|pascal_case }}]:
    """Get {{ model.name }} by ID"""
    stmt = select({{ model.name|pascal_case }})
{% for rel in model.many_to_many_relationships %}
    stmt = stmt.options(selectinload({{ model.name|pascal_case }}.{{ rel.attribute }}))
{% endfor %}
    {% set pk_field = model.fields|selectattr('primary_key')|first %}
    {% if pk_field %}
    stmt = stmt.where({{ model.name|pascal_case }}.{{ pk_field.name }} == {{ model.name|snake_case }}_id)
    {%- else %}
    stmt = stmt.where({{ model.name|pascal_case }}.id == {{ model.name|snake_case }}_id)
    {%- endif %}
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
{% else %}
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
{% endif %}


{% for field in model.fields %}
{% if field.unique and not field.primary_key %}
{% if project.database_config.async_mode %}
async def get_{{ model.name|snake_case }}_by_{{ field.name }}(db: AsyncSession, {{ field.name }}: str) -> Optional[{{ model.name|pascal_case }}]:
    """Get {{ model.name }} by {{ field.name }}"""
    stmt = select({{ model.name|pascal_case }}).where({{ model.name|pascal_case }}.{{ field.name }} == {{ field.name }})
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
{% else %}
def get_{{ model.name|snake_case }}_by_{{ field.name }}(db: Session, {{ field.name }}: str) -> Optional[{{ model.name|pascal_case }}]:
    """Get {{ model.name }} by {{ field.name }}"""
    return db.query({{ model.name|pascal_case }}).filter({{ model.name|pascal_case }}.{{ field.name }} == {{ field.name }}).first()
{% endif %}


{% endif %}
{%- endfor %}

{% if project.database_config.async_mode %}
async def get_all_{{ model.plural_snake }}(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
{% for rel in model.owned_relationships %}
    {{ rel.fk_column }}: Optional[int] = None,
{% endfor %}
) -> List[{{ model.name|pascal_case }}]:
    """Get all {{ model.name }}s with pagination"""
    stmt = select({{ model.name|pascal_case }})
{% for rel in model.many_to_many_relationships %}
    stmt = stmt.options(selectinload({{ model.name|pascal_case }}.{{ rel.attribute }}))
{% endfor %}
{% for rel in model.owned_relationships %}
    if {{ rel.fk_column }} is not None:
        stmt = stmt.where({{ model.name|pascal_case }}.{{ rel.fk_column }} == {{ rel.fk_column }})
{% endfor %}
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
{% else %}
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
{% endif %}


{% if project.database_config.async_mode %}
async def update_{{ model.name|snake_case }}(db: AsyncSession, {{ model.name|snake_case }}_id: int, update_data: dict) -> Optional[{{ model.name|pascal_case }}]:
    """Update {{ model.name }}"""
    {{ model.name|snake_case }} = await get_{{ model.name|snake_case }}_by_id(db, {{ model.name|snake_case }}_id)
    if {{ model.name|snake_case }}:
        for key, value in update_data.items():
            setattr({{ model.name|snake_case }}, key, value)
        await db.commit()
        await db.refresh({{ model.name|snake_case }})
    return {{ model.name|snake_case }}
{% else %}
def update_{{ model.name|snake_case }}(db: Session, {{ model.name|snake_case }}_id: int, update_data: dict) -> Optional[{{ model.name|pascal_case }}]:
    """Update {{ model.name }}"""
    {{ model.name|snake_case }} = get_{{ model.name|snake_case }}_by_id(db, {{ model.name|snake_case }}_id)
    if {{ model.name|snake_case }}:
        for key, value in update_data.items():
            setattr({{ model.name|snake_case }}, key, value)
        db.commit()
        db.refresh({{ model.name|snake_case }})
    return {{ model.name|snake_case }}
{% endif %}


{% if project.database_config.async_mode %}
async def delete_{{ model.name|snake_case }}(db: AsyncSession, {{ model.name|snake_case }}_id: int) -> bool:
    """Delete {{ model.name }}"""
    {{ model.name|snake_case }} = await get_{{ model.name|snake_case }}_by_id(db, {{ model.name|snake_case }}_id)
    if {{ model.name|snake_case }}:
        await db.delete({{ model.name|snake_case }})
        await db.commit()
        return True
    return False
{% else %}
def delete_{{ model.name|snake_case }}(db: Session, {{ model.name|snake_case }}_id: int) -> bool:
    """Delete {{ model.name }}"""
    {{ model.name|snake_case }} = get_{{ model.name|snake_case }}_by_id(db, {{ model.name|snake_case }}_id)
    if {{ model.name|snake_case }}:
        db.delete({{ model.name|snake_case }})
        db.commit()
        return True
    return False
{% endif %}

{% endfor %}
```

Note: `async def delete_{{ model.name|snake_case }}` uses `await db.delete(...)` — per the Global Constraints, this is required, not optional.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_async_generation.py -v`
Expected: PASS, all tests (the live-DB test in particular proves the delete-await requirement empirically, not just via a text assertion).

- [ ] **Step 6: Render and read the output by hand**

Run:
```bash
uv run backstudio generate backend/tests/fixtures/erd/async_relationships.yml --output /tmp/rc_async_task3a --force
uv run backstudio generate backend/tests/fixtures/erd/valid_full.yml --output /tmp/rc_async_task3b --force
```
Read `database/repo.py` in full for both. Confirm no whitespace glue damage, no leftover `Query`-API calls in the async render, and that the sync render is completely unchanged. `py_compile` both.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/templates/Python/database/repo.py.jinja backend/tests/fixtures/erd/async_relationships.yml backend/tests/test_async_generation.py
git commit -m "Rewrite repo.py.jinja onto select()/execute() for async_mode"
```

---

### Task 4: Service layer propagation — `module_service.py.jinja`

**Files:**
- Modify: `backend/templates/Python/service/module_service.py.jinja`
- Test: `backend/tests/test_async_generation.py`

**Interfaces:**
- Consumes: `project.database_config.async_mode` (Task 1); `repo.create_<x>`/`get_<x>_by_id`/`get_all_<plural>`/`update_<x>`/`delete_<x>` now being `async def` when `async_mode` (Task 3, already merged).
- Produces: the async service methods Task 5's routes call into.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_async_generation.py`:

```python
def test_async_service_methods_are_async_and_await_repo(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_relationships.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "content" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)

    assert "from sqlalchemy.ext.asyncio import AsyncSession" in service_src
    assert "from sqlalchemy.orm import Session" not in service_src

    create_start = service_src.index("async def create_post(")
    create_end = service_src.index("\n    async def list_posts(")
    create_src = service_src[create_start:create_end]
    assert "db: AsyncSession" in create_src
    assert "await repo.get_author_by_id(" in create_src
    assert "return await repo.create_post(db, data)" in create_src

    delete_start = service_src.index("async def delete_post(")
    delete_src = service_src[delete_start:]
    assert "return await repo.delete_post(db, item_id)" in delete_src


def test_sync_service_still_unchanged_when_async_mode_omitted(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "catalog" / "service.py").read_text(encoding="utf-8")
    assert "from sqlalchemy.orm import Session" in service_src
    assert "async def" not in service_src
    assert "await " not in service_src


def test_async_service_fk_validation_and_delete_actually_work(tmp_path):
    import asyncio

    import pytest

    erd = load_erd(f"{FIXTURES}/async_relationships.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "service_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        content_service = importlib.import_module("modules.content.service")

        async def run():
            await database_base.init_db()
            service = content_service.get_content_service()
            async with database_base.AsyncSessionLocal() as db:
                with pytest.raises(ValueError):
                    await service.create_post(db, {"title": "Bad", "author_id": 999})

                author = await service.create_author(db, {"name": "Ada"})
                post = await service.create_post(db, {"title": "Good", "author_id": author.id})

                deleted = await service.delete_post(db, post.id)
                assert deleted is True
                assert await service.get_post(db, post.id) is None
            await database_base.engine.dispose()

        asyncio.run(run())
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_async_generation.py -k "service" -v`
Expected: FAIL (except the sync-unchanged test).

- [ ] **Step 3: Implement**

Full new file:

```jinja
"""{{ project.name }} - {{ module.name }} service"""

{% set is_async = project.database_config.async_mode %}
from typing import List, Optional
{% if is_async %}
from sqlalchemy.ext.asyncio import AsyncSession
{% else %}
from sqlalchemy.orm import Session
{% endif %}

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
    {{ 'async ' if is_async }}def create_{{ entity.snake_name }}(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, data: dict) -> {{ entity.name }}:
{% for rel in entity.owned_relationships %}
        if data.get("{{ rel.fk_column }}") is not None and {{ 'await ' if is_async }}repo.get_{{ rel.target_snake }}_by_id(db, data["{{ rel.fk_column }}"]) is None:
            raise ValueError(f"{{ rel.target_model }} {data['{{ rel.fk_column }}']} not found")
{% endfor %}
        return {{ 'await ' if is_async }}repo.create_{{ entity.snake_name }}(db, data)

    {{ 'async ' if is_async }}def list_{{ entity.plural_snake }}(
        self,
        db: {{ 'AsyncSession' if is_async else 'Session' }},
        skip: int = 0,
        limit: int = 100,
{% for rel in entity.owned_relationships %}
        {{ rel.fk_column }}: Optional[int] = None,
{% endfor %}
    ) -> List[{{ entity.name }}]:
        return {{ 'await ' if is_async }}repo.get_all_{{ entity.plural_snake }}(db, skip=skip, limit=limit{% for rel in entity.owned_relationships %}, {{ rel.fk_column }}={{ rel.fk_column }}{% endfor %})

    {{ 'async ' if is_async }}def get_{{ entity.snake_name }}(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, item_id: int) -> Optional[{{ entity.name }}]:
        return {{ 'await ' if is_async }}repo.get_{{ entity.snake_name }}_by_id(db, item_id)

    {{ 'async ' if is_async }}def update_{{ entity.snake_name }}(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, item_id: int, data: dict) -> Optional[{{ entity.name }}]:
{% for rel in entity.owned_relationships %}
{% if not rel.fk_nullable %}
        if "{{ rel.fk_column }}" in data and data["{{ rel.fk_column }}"] is None:
            raise ValueError("{{ rel.fk_column }} cannot be null")
{% endif %}
        if data.get("{{ rel.fk_column }}") is not None and {{ 'await ' if is_async }}repo.get_{{ rel.target_snake }}_by_id(db, data["{{ rel.fk_column }}"]) is None:
            raise ValueError(f"{{ rel.target_model }} {data['{{ rel.fk_column }}']} not found")
{% endfor %}
        return {{ 'await ' if is_async }}repo.update_{{ entity.snake_name }}(db, item_id, data)

    {{ 'async ' if is_async }}def delete_{{ entity.snake_name }}(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, item_id: int) -> bool:
        return {{ 'await ' if is_async }}repo.delete_{{ entity.snake_name }}(db, item_id)

{% endfor %}

_{{ module.snake_name }}_service_instance: Optional["{{ module.name|pascal_case }}Service"] = None


def get_{{ module.snake_name }}_service() -> "{{ module.name|pascal_case }}Service":
    global _{{ module.snake_name }}_service_instance
    if _{{ module.snake_name }}_service_instance is None:
        _{{ module.snake_name }}_service_instance = {{ module.name|pascal_case }}Service()
    return _{{ module.snake_name }}_service_instance
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_async_generation.py -v`
Expected: PASS.

- [ ] **Step 5: Render and read the output by hand**

Run:
```bash
uv run backstudio generate backend/tests/fixtures/erd/async_relationships.yml --output /tmp/rc_async_task4a --force
uv run backstudio generate backend/tests/fixtures/erd/valid_full.yml --output /tmp/rc_async_task4b --force
```
Read `modules/content/service.py` and `modules/catalog/service.py` in full. Confirm correct `async def`/`await` placement (especially that `Author`'s methods, which have no `owned_relationships`, still render correctly with no stray blank lines from the now-empty FK-validation loop), and that the sync render is byte-identical to before this task. `py_compile` both.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/service/module_service.py.jinja backend/tests/test_async_generation.py
git commit -m "Propagate async/await through module_service.py.jinja for async_mode"
```

---

### Task 5: Routes layer propagation — `module_routes.py.jinja`

**Files:**
- Modify: `backend/templates/Python/service/module_routes.py.jinja`
- Test: `backend/tests/test_async_generation.py`

**Interfaces:**
- Consumes: `project.database_config.async_mode` (Task 1); `service.create_<x>`/`list_<x>`/`get_<x>`/`update_<x>`/`delete_<x>` now being `async def` when `async_mode` (Task 4, already merged).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_async_generation.py`:

```python
def test_async_routes_are_async_and_await_service(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_relationships.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "content" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)

    assert "from sqlalchemy.ext.asyncio import AsyncSession" in routes_src
    assert "from sqlalchemy.orm import Session" not in routes_src

    create_start = routes_src.index("def create_post_route(")
    create_end = routes_src.index("\n@router", create_start)
    create_src = routes_src[create_start:create_end]
    assert "async def create_post_route(" in create_src
    assert "db: AsyncSession = Depends(get_db)" in create_src
    assert "await service.create_post(db, payload.model_dump())" in create_src

    list_start = routes_src.index("def list_post_route(")
    list_end = routes_src.index("\n@router", list_start)
    list_src = routes_src[list_start:list_end]
    assert "async def list_post_route(" in list_src
    assert "await service.list_posts(" in list_src


def test_sync_routes_still_unchanged_when_async_mode_omitted(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "catalog" / "routes.py").read_text(encoding="utf-8")
    assert "from sqlalchemy.orm import Session" in routes_src
    assert "async def" not in routes_src
    assert "await " not in routes_src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_async_generation.py -k "routes" -v`
Expected: FAIL (except the sync-unchanged test).

- [ ] **Step 3: Implement**

Full new file:

```jinja
"""{{ project.name }} - {{ module.name }} routes (auto-generated CRUD)"""

{% set is_async = project.database_config.async_mode %}
{% set has_owned_rel = (module.entities|map(attribute='owned_relationships')|map('length')|sum) > 0 %}
from typing import List{% if has_owned_rel %}, Optional{% endif +%}
from fastapi import APIRouter, Depends, HTTPException, Query, status
{% if is_async %}
from sqlalchemy.ext.asyncio import AsyncSession
{% else %}
from sqlalchemy.orm import Session
{% endif %}

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
{% if project.rbac_enabled and entity.rbac['create'] %}
    dependencies=[Depends(require_roles({% for role in entity.rbac['create'] %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
{{ 'async ' if is_async }}def create_{{ entity.snake_name }}_route(
    payload: {{ entity.name }}Create,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> {{ entity.name }}Response:
{% if entity.owned_relationships %}
    try:
        return {{ 'await ' if is_async }}service.create_{{ entity.snake_name }}(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
{% else %}
    return {{ 'await ' if is_async }}service.create_{{ entity.snake_name }}(db, payload.model_dump())
{% endif %}
{% endif %}

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
{{ 'async ' if is_async }}def list_{{ entity.snake_name }}_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
{% for rel in entity.owned_relationships %}
    {{ rel.fk_column }}: Optional[int] = Query(None),
{% endfor %}
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> List[{{ entity.name }}Response]:
    return {{ 'await ' if is_async }}service.list_{{ entity.plural_snake }}(db, skip=skip, limit=limit{% for rel in entity.owned_relationships %}, {{ rel.fk_column }}={{ rel.fk_column }}{% endfor %})
{% endif %}

{% if 'read' in entity.enabled_actions %}
@router.get(
    "{{ entity.base_path }}/{item_id}",
    response_model={{ entity.name }}Response,
    summary="Get {{ entity.name }} by id",
    tags={{ entity.tags|tojson }},
{% if project.rbac_enabled and entity.rbac['read'] %}
    dependencies=[Depends(require_roles({% for role in entity.rbac['read'] %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
{{ 'async ' if is_async }}def get_{{ entity.snake_name }}_route(
    item_id: int,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> {{ entity.name }}Response:
    item = {{ 'await ' if is_async }}service.get_{{ entity.snake_name }}(db, item_id)
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
{% if project.rbac_enabled and entity.rbac['update'] %}
    dependencies=[Depends(require_roles({% for role in entity.rbac['update'] %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
{{ 'async ' if is_async }}def update_{{ entity.snake_name }}_route(
    item_id: int,
    payload: {{ entity.name }}Update,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> {{ entity.name }}Response:
{% if entity.owned_relationships %}
    try:
        item = {{ 'await ' if is_async }}service.update_{{ entity.snake_name }}(db, item_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
{% else %}
    item = {{ 'await ' if is_async }}service.update_{{ entity.snake_name }}(db, item_id, payload.model_dump(exclude_unset=True))
{% endif %}
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
{% if project.rbac_enabled and entity.rbac['delete'] %}
    dependencies=[Depends(require_roles({% for role in entity.rbac['delete'] %}"{{ role }}"{{ ", " if not loop.last else "" }}{% endfor %}))],
{% endif %}
)
{{ 'async ' if is_async }}def delete_{{ entity.snake_name }}_route(
    item_id: int,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: {{ module.name|pascal_case }}Service = Depends(get_{{ module.snake_name }}_service),
) -> None:
    deleted = {{ 'await ' if is_async }}service.delete_{{ entity.snake_name }}(db, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{{ entity.name }} not found")
{% endif %}

{% endfor %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_async_generation.py -v`
Expected: PASS.

- [ ] **Step 5: Render and read the output by hand**

Run: `uv run backstudio generate backend/tests/fixtures/erd/async_relationships.yml --output /tmp/rc_async_task5 --force`
Read `modules/content/routes.py` in full. Confirm the entity-to-entity blank-line spacing (fixed in an earlier plan this session) is intact, RBAC/owned-relationship conditional blocks render correctly with the new inline async tokens, and no whitespace glue damage. `py_compile` it. Also regenerate `valid_full.yml` and confirm the sync render is unchanged.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/service/module_routes.py.jinja backend/tests/test_async_generation.py
git commit -m "Propagate async/await through module_routes.py.jinja for async_mode"
```

---

### Task 6: Auth module propagation — `auth/service.py.jinja` + `auth/routes.py.jinja`

**Files:**
- Modify: `backend/templates/Python/auth/service.py.jinja`
- Modify: `backend/templates/Python/auth/routes.py.jinja`
- Create: `backend/tests/fixtures/erd/async_shophub_mini.yml`
- Test: `backend/tests/test_async_generation.py`

**Interfaces:**
- Consumes: `project.database_config.async_mode` (Task 1).
- Produces: the async `AuthService`/auth routes that Task 8's full round-trip test drives.

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/erd/async_shophub_mini.yml` (identical to the existing `shophub_mini.yml` — same entities, auth, RBAC, cross-module relationships — with `async_mode: true` added under `database:`; this fixture also serves Task 7's Alembic test and Task 8's full round-trip test):

```yaml
project:
  name: AsyncShopHubMini
  version: "1.0.0"
  description: A minimal ShopHub-style sample exercising auth, RBAC, and relationships, async

database:
  type: postgresql
  database_name: async_shophub_mini
  async_mode: true

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

(`database.type: postgresql` is declared but never actually connected to in this plan's tests — every runtime test in this repo overrides `DATABASE_URL` to a real `tmp_path` SQLite file regardless of a fixture's nominal `database.type`, exactly matching `shophub_mini.yml`'s own existing usage in the sync-path tests. `async_mode: true` only affects what `generate` renders, not what the tests connect to.)

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/test_async_generation.py`:

```python
def test_async_auth_service_and_routes_are_async(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "from sqlalchemy.ext.asyncio import AsyncSession" in service_src
    assert "from sqlalchemy import select, func" in service_src

    register_start = service_src.index("async def register_user(")
    register_end = service_src.index("\n    async def authenticate_user(")
    register_src = service_src[register_start:register_end]
    assert "select(User).where(User.email == email)" in register_src
    assert "await db.execute(" in register_src
    assert "await db.scalar(select(func.count()).select_from(User))" in register_src
    assert "await db.commit()" in register_src

    get_current_user_start = service_src.index("async def get_current_user(")
    get_current_user_src = service_src[get_current_user_start:]
    assert "select(User).where(User.id == user_id)" in get_current_user_src

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "async def register(" in routes_src
    assert "async def login(" in routes_src
    assert "async def refresh(" in routes_src
    assert "async def me(" in routes_src
    assert "await service.register_user(" in routes_src
    assert "await service.authenticate_user(" in routes_src
    assert "select(User).where(User.id == user_id)" in routes_src  # refresh's own raw query


def test_sync_auth_still_unchanged_when_async_mode_omitted(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    assert "from sqlalchemy.orm import Session" in service_src
    assert "async def register_user" not in service_src
    assert "db.query(User)" in service_src

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    assert "async def register(" not in routes_src
    assert "async def me(" not in routes_src


def test_async_auth_register_and_login_actually_work(tmp_path):
    import asyncio

    erd = load_erd(f"{FIXTURES}/async_shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "auth_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        async def run():
            await database_base.init_db()
            service = auth_service.get_auth_service()
            async with database_base.AsyncSessionLocal() as db:
                user = await service.register_user(db, "alice@example.com", "supersecret123")
                assert set(user.roles) == {"admin", "customer"}  # bootstrap: first user gets every role

                authed = await service.authenticate_user(db, "alice@example.com", "supersecret123")
                assert authed.id == user.id
            await database_base.engine.dispose()

        asyncio.run(run())
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_async_generation.py -k "auth" -v`
Expected: FAIL (except the sync-unchanged test).

- [ ] **Step 4: Implement — `auth/service.py.jinja`**

Full new file:

```jinja
"""{{ project.name }} - {{ project.auth_module_name }} service"""

{% set is_async = project.database_config.async_mode %}
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
{% if is_async %}
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
{% else %}
from sqlalchemy.orm import Session
{% endif %}

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

    {{ 'async ' if is_async }}def register_user(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, email: str, password: str) -> User:
{% if is_async %}
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
{% else %}
        existing = db.query(User).filter(User.email == email).first()
{% endif %}
        if existing:
            raise ValueError("Email already registered")

        {% if project.rbac_roles %}
        # Bootstrap convention: RBAC locks every action behind declared roles, so with
        # roles=[] nobody could ever access anything. The very first user registered
        # is granted every declared role; every subsequent registration gets roles=[]
        # (an admin/existing user must grant roles afterwards).
{% if is_async %}
        is_first_user = (await db.scalar(select(func.count()).select_from(User))) == 0
{% else %}
        is_first_user = db.query(User).count() == 0
{% endif %}
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
{% if is_async %}
        await db.commit()
        await db.refresh(user)
{% else %}
        db.commit()
        db.refresh(user)
{% endif %}
        return user

    {{ 'async ' if is_async }}def authenticate_user(self, db: {{ 'AsyncSession' if is_async else 'Session' }}, email: str, password: str) -> User:
{% if is_async %}
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
{% else %}
        user = db.query(User).filter(User.email == email).first()
{% endif %}
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

    async def get_current_user(self, token: str = Depends(oauth2_scheme), db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db)) -> User:
        user_id = self.decode_token(token, expected_type="access")
{% if is_async %}
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
{% else %}
        user = db.query(User).filter(User.id == user_id).first()
{% endif %}
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

Note `get_current_user` was already `async def` unconditionally in both branches before this task — that's unchanged; only its `db` type hint and internal query gained the conditional.

- [ ] **Step 5: Implement — `auth/routes.py.jinja`**

Full new file:

```jinja
"""{{ project.name }} - {{ project.auth_module_name }} routes"""

{% set is_async = project.database_config.async_mode %}
from fastapi import APIRouter, Depends, HTTPException, status
{% if is_async %}
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
{% else %}
from sqlalchemy.orm import Session
{% endif %}

from database.base import get_db
from database.models import User
from .schemas import RefreshRequest, TokenResponse, UserLogin, UserRegister, UserResponse
from .service import AuthService, get_{{ project.auth_module_name }}_service

router = APIRouter()
# Module-level singleton, resolved once at import time: `/me` (and rbac.py's
# require_roles) needs a *bound method* to pass to Depends(), and FastAPI
# evaluates a route's Depends() arguments at definition time - not per-request
# - so the instance has to already exist here. The other routes below don't
# need that and use the regular per-request Depends(get_..._service) pattern,
# consistent with every other module's routes.py.
_service = get_{{ project.auth_module_name }}_service()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
{{ 'async ' if is_async }}def register(
    payload: UserRegister,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> UserResponse:
    try:
        user = {{ 'await ' if is_async }}service.register_user(db, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return user


@router.post("/login", response_model=TokenResponse)
{{ 'async ' if is_async }}def login(
    payload: UserLogin,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> TokenResponse:
    try:
        user = {{ 'await ' if is_async }}service.authenticate_user(db, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return TokenResponse(
        access_token=service.create_access_token(user.id),
        refresh_token=service.create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
{{ 'async ' if is_async }}def refresh(
    payload: RefreshRequest,
    db: {{ 'AsyncSession' if is_async else 'Session' }} = Depends(get_db),
    service: AuthService = Depends(get_{{ project.auth_module_name }}_service),
) -> TokenResponse:
    user_id = service.decode_token(payload.refresh_token, expected_type="refresh")
{% if is_async %}
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
{% else %}
    user = db.query(User).filter(User.id == user_id).first()
{% endif %}
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return TokenResponse(
        access_token=service.create_access_token(user.id),
        refresh_token=service.create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
{{ 'async ' if is_async }}def me(current_user: User = Depends(_service.get_current_user)) -> UserResponse:
    return current_user
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_async_generation.py -v`
Expected: PASS.

- [ ] **Step 7: Render and read the output by hand**

Run:
```bash
uv run backstudio generate backend/tests/fixtures/erd/async_shophub_mini.yml --output /tmp/rc_async_task6a --force
uv run backstudio generate backend/tests/fixtures/erd/shophub_mini.yml --output /tmp/rc_async_task6b --force
```
Read `modules/auth/service.py` and `modules/auth/routes.py` in full for both. Confirm no whitespace glue damage (this file has more deeply-nested conditionals than most — check the RBAC-bootstrap block especially), and the sync render is unchanged. `py_compile` both.

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/templates/Python/auth/service.py.jinja backend/templates/Python/auth/routes.py.jinja backend/tests/fixtures/erd/async_shophub_mini.yml backend/tests/test_async_generation.py
git commit -m "Propagate async/await through the auth module for async_mode"
```

---

### Task 7: Alembic migrations — `alembic/env.py.jinja`

**Files:**
- Modify: `backend/templates/Python/alembic/env.py.jinja`
- Test: `backend/tests/test_async_generation.py`

**Interfaces:**
- Consumes: `project.database_config.async_mode` (Task 1).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_async_generation.py`:

```python
def test_async_alembic_env_uses_async_engine_and_run_sync(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    env_src = (codebase_dir / "alembic" / "env.py").read_text(encoding="utf-8")
    ast.parse(env_src)
    assert "from sqlalchemy.ext.asyncio import async_engine_from_config" in env_src
    assert "import asyncio" in env_src
    assert "async def run_migrations_online() -> None:" in env_src
    assert "await connection.run_sync(do_run_migrations)" in env_src
    assert "asyncio.run(run_migrations_online())" in env_src
    assert "engine_from_config(" not in env_src.replace("async_engine_from_config(", "")


def test_sync_alembic_env_still_unchanged_when_async_mode_omitted(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    env_src = (codebase_dir / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "async_engine_from_config" not in env_src
    assert "asyncio" not in env_src
    assert "def run_migrations_online() -> None:" in env_src


def test_async_alembic_autogenerate_runs_against_real_generated_project(tmp_path):
    """Mirrors the existing sync-path test - this is the exact command that would
    fail if the async-Alembic run_sync() pattern is subtly wrong, which the design
    spec explicitly flagged as having 'a well-earned reputation for looking right
    and failing at the asyncio.run()-inside-a-context boundary in practice.'
    """
    erd = load_erd(f"{FIXTURES}/async_shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "async_alembic_test.db"
    env = {
        **__import__("os").environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path.as_posix()}",
        "JWT_SECRET": "test-only-secret-do-not-use-in-production",
        "DEBUG": "True",
    }

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "test"],
        cwd=str(codebase_dir),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"

    versions_dir = codebase_dir / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    assert len(migration_files) == 1, f"expected exactly one migration file, found {migration_files}"

    migration_src = migration_files[0].read_text(encoding="utf-8")
    assert "create_table('users'" in migration_src or 'create_table("users"' in migration_src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_async_generation.py -k "alembic" -v`
Expected: FAIL (except the sync-unchanged test).

- [ ] **Step 3: Implement**

Full new file:

```jinja
"""{{ project.name }} - Alembic environment"""

from logging.config import fileConfig

from alembic import context
{% if project.database_config.async_mode %}
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
import asyncio
{% else %}
from sqlalchemy import engine_from_config, pool
{% endif %}

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


{% if project.database_config.async_mode %}
def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
{% else %}
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
{% endif %}
```

Note the `if context.is_offline_mode(): ... else: ...` dispatch moved inside each branch (rather than staying as one shared block at the bottom calling a branch-conditional `run_migrations_online`), because the async branch's online path must be wrapped in `asyncio.run(...)` at the call site, not inside the function-definition — keeping the dispatch itself un-duplicated while wrapping only the call would require a `{{ 'asyncio.run(' if ... }}` split across two separate lines, which is exactly the kind of fragile inline-across-statement-boundary Jinja this plan's Global Constraints steer away from for files like this one (full top-level split instead, matching `base.py.jinja`'s approach).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_async_generation.py -v`
Expected: PASS. The `test_async_alembic_autogenerate_runs_against_real_generated_project` test is the one to watch most carefully — if it fails, read the actual `stdout`/`stderr` in the assertion message rather than guessing; async-Alembic failures are almost always a specific, informative traceback (e.g. a missing driver, or a mis-scoped `asyncio.run()` call), not a mysterious hang.

- [ ] **Step 5: Render and read the output by hand**

Run:
```bash
uv run backstudio generate backend/tests/fixtures/erd/async_shophub_mini.yml --output /tmp/rc_async_task7a --force
uv run backstudio generate backend/tests/fixtures/erd/shophub_mini.yml --output /tmp/rc_async_task7b --force
```
Read `alembic/env.py` in full for both. Confirm the sync render is unchanged. `py_compile` both.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/Python/alembic/env.py.jinja backend/tests/test_async_generation.py
git commit -m "Add async-Alembic run_sync() migration support for async_mode"
```

---

### Task 8: Real HTTP+DB round-trip tests

**Files:**
- Modify: `backend/tests/test_generated_project_runtime.py`

**Interfaces:**
- Consumes: the fully wired generated async app from Tasks 2-6, via `TestClient`.

- [ ] **Step 1: Read the existing file's fixtures/setup helpers first**

Read `backend/tests/test_generated_project_runtime.py` in full before writing anything — reuse its existing `_GeneratedProjectImporter`/`isolated_sys_path` fixtures and `monkeypatch.setenv(...)`/`TestClient(server_module.app)` pattern exactly, matching every existing test in that file.

- [ ] **Step 2: Write the failing test**

Add to `backend/tests/test_generated_project_runtime.py`:

```python
def test_async_mode_full_stack_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """async_shophub_mini.yml driven through real HTTP + a real (aiosqlite) DB - the
    final proof that routes -> service -> repo -> DB compose correctly end to end in
    async_mode, exactly mirroring what test_module_crud_round_trip_against_real_generated_app
    already proves for the sync path. Uses TestClient as a context manager specifically
    because that's what actually exercises server.py's lifespan startup/shutdown -
    including the engine.dispose() call this plan's design work found was necessary to
    avoid hanging the whole pytest process on exit, not just this one test.
    """
    erd = load_erd(f"{FIXTURES}/async_shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "async_full_stack_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # --- auth: register/login, bootstrap admin gets every role ---
            register_resp = client.post(
                "/auth/register", json={"email": "admin@example.com", "password": "supersecret123"}
            )
            assert register_resp.status_code == 201, register_resp.text
            assert set(register_resp.json()["roles"]) == {"admin", "customer"}

            login_resp = client.post(
                "/auth/login", json={"email": "admin@example.com", "password": "supersecret123"}
            )
            assert login_resp.status_code == 200, login_resp.text
            admin_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

            me_resp = client.get("/auth/me", headers=admin_headers)
            assert me_resp.status_code == 200, me_resp.text
            assert me_resp.json()["email"] == "admin@example.com"

            # --- module CRUD through the async stack ---
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
            assert prod_resp.json()["category_id"] == category_id

            # FK validation returning 400 through the full async stack
            bad_prod_resp = client.post(
                "/products",
                json={"name": "Bad", "price": 1.0, "sku": "T2", "category_id": 999999},
                headers=admin_headers,
            )
            assert bad_prod_resp.status_code == 400, bad_prod_resp.text

            # the owned-relationship filter query param
            filtered_resp = client.get(f"/products?category_id={category_id}", headers=admin_headers)
            assert filtered_resp.status_code == 200, filtered_resp.text
            assert [p["name"] for p in filtered_resp.json()] == ["Thing"]

            # update
            update_resp = client.put(
                f"/products/{product_id}", json={"name": "Renamed"}, headers=admin_headers
            )
            assert update_resp.status_code == 200, update_resp.text
            assert update_resp.json()["name"] == "Renamed"

            # cross-module FK (Order -> Product in a different module, and Order -> User)
            user_id = register_resp.json()["id"]
            order_resp = client.post(
                "/orders",
                json={
                    "status": "pending",
                    "total_amount": 1.0,
                    "user_id": user_id,
                    "product_id": product_id,
                },
                headers=admin_headers,
            )
            assert order_resp.status_code == 201, order_resp.text
            assert order_resp.json()["product_id"] == product_id

            # delete, then confirm actually gone (proves await db.delete(x) worked)
            delete_resp = client.delete(f"/products/{product_id}", headers=admin_headers)
            assert delete_resp.status_code == 204, delete_resp.text
            gone_resp = client.get(f"/products/{product_id}", headers=admin_headers)
            assert gone_resp.status_code == 404, gone_resp.text

            # a role-less second user gets a real 403 on an RBAC-restricted action
            second_register_resp = client.post(
                "/auth/register", json={"email": "roleless@example.com", "password": "supersecret123"}
            )
            assert second_register_resp.status_code == 201, second_register_resp.text
            assert second_register_resp.json()["roles"] == []
            second_login_resp = client.post(
                "/auth/login", json={"email": "roleless@example.com", "password": "supersecret123"}
            )
            second_headers = {"Authorization": f"Bearer {second_login_resp.json()['access_token']}"}
            forbidden_resp = client.post(
                "/categories", json={"name": "Should not be allowed"}, headers=second_headers
            )
            assert forbidden_resp.status_code == 403, forbidden_resp.text

    # The `with TestClient(...)` block above has already exited by this point, which
    # ran server.py's lifespan shutdown (await engine.dispose()). If that's missing or
    # wrong, this test - or, worse, the whole pytest process at the very end of a full
    # suite run - would hang here rather than fail cleanly. Reaching this line at all
    # is part of what this test proves.
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_generated_project_runtime.py -k "async_mode_full_stack" -v --timeout=60`
Expected: FAIL for a real reason if any of Tasks 2-6 has a defect this integration level surfaces (some assertions may already pass if everything is fully correct — that's fine, keep the test as written per the same principle used in the relationship-CRUD-exposure plan's equivalent task). If a genuine bug in already-merged Task 2-6 code surfaces here, that is a real finding — fix the template, don't weaken the test. If `pytest-timeout` isn't installed, omit `--timeout=60` and instead run with a background timeout wrapper, since a hang here is exactly the failure mode this test exists to catch and it should not be allowed to hang the dispatch silently.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_generated_project_runtime.py -v`
Expected: PASS, all tests in the file (existing sync-path tests + this new one).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest backend/tests -q`
Expected: PASS. Watch the wall-clock time and the process's actual exit — this is the first point in the whole plan where the full suite runs with an async app that went through a complete real startup+shutdown lifecycle; if the suite hangs after printing its final summary line, that is a real (if late-surfacing) defect in engine disposal, not a fluke — do not re-run hoping it passes, investigate.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_generated_project_runtime.py
git commit -m "Add full-stack async HTTP+DB round-trip test"
```

---

### Task 9: Documentation + backlog close-out

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/backlog.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update the root README**

Read `README.md` in full first. Add a `database.async_mode` row/entry to the `### database` YAML reference section (find it — it documents `type`, `host`, `port`, `database_name`, etc.), describing: default `false`; when `true`, generates an async SQLAlchemy stack (async engine/session, `select()`/`execute()` repo layer, `async def` service/route/auth handlers) instead of sync; the `DATABASE_URL` needs an async-driver-qualified scheme for your chosen `database.type` when connecting to a real (non-default-SQLite) database — give the three scheme examples from the spec's §3 table (`sqlite+aiosqlite://`, `postgresql+asyncpg://`, `mysql+aiomysql://`), verified against real generated output (actually run `backstudio generate` on an async fixture and confirm the example matches, per this session's established convention — don't write example output from memory).

- [ ] **Step 2: Close out the backlog item**

In `docs/superpowers/backlog.md`, find the "Async support" item under "Architectural" and check it off, appending a "Fixed 2026-09-09:" summary in the style of the other closed-out items in the file: what shipped (opt-in `database.async_mode`, the four-layer propagation, the `delete()`-must-be-awaited and engine-disposal findings), a pointer to the spec (`docs/superpowers/specs/2026-09-09-async-support-design.md`) and this plan file, and a note that RLS (next up) is now unblocked to be designed directly against this async shape.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/backlog.md
git commit -m "Document database.async_mode in README, close out the async-support backlog item"
```
