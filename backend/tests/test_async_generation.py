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
