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


def test_async_routes_are_async_and_await_service(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_relationships.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "content" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)

    assert "from sqlalchemy.ext.asyncio import AsyncSession" in routes_src
    assert "from sqlalchemy.orm import Session" not in routes_src

    create_start = routes_src.index("async def create_post_route(")
    create_end = routes_src.index("\n@router", create_start)
    create_src = routes_src[create_start:create_end]
    assert "async def create_post_route(" in create_src
    assert "db: AsyncSession = Depends(get_db)" in create_src
    assert "await service.create_post(db, payload.model_dump())" in create_src

    list_start = routes_src.index("async def list_post_route(")
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


def test_async_postgresql_readme_documents_asyncpg_database_url(tmp_path):
    """README.md.jinja is the *generated project's* README (distinct from this repo's
    root README.md, which Task 9 already correctly updated). Following its DATABASE_URL
    instructions verbatim must not produce a broken app: an async+postgresql project
    ships asyncpg (not psycopg2) in requirements.txt, so the README must document the
    postgresql+asyncpg:// scheme, not a bare postgresql:// one.
    """
    erd = load_erd(f"{FIXTURES}/async_postgresql.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    readme_src = (codebase_dir / "README.md").read_text(encoding="utf-8")
    assert "DATABASE_URL=postgresql+asyncpg://" in readme_src
    assert "DATABASE_URL=postgresql://" not in readme_src


def test_async_mysql_readme_documents_aiomysql_database_url(tmp_path):
    erd = load_erd(f"{FIXTURES}/async_mysql.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    readme_src = (codebase_dir / "README.md").read_text(encoding="utf-8")
    assert "DATABASE_URL=mysql+aiomysql://" in readme_src
    assert "DATABASE_URL=mysql://" not in readme_src


def test_sync_readme_database_url_unchanged(tmp_path):
    """valid_full.yml is sync (no async_mode key) with database.type postgresql - the
    opt-in regression guard for README.md.jinja: a sync project's DATABASE_URL line must
    render byte-identical to how it did before this fix (bare scheme, no +asyncpg/
    +aiomysql/+aiosqlite anywhere in the README).
    """
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)
    assert state["database_config"]["async_mode"] is False

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    readme_src = (codebase_dir / "README.md").read_text(encoding="utf-8")
    assert "DATABASE_URL=postgresql://user:password@localhost/shophub_db" in readme_src
    assert "+asyncpg" not in readme_src
    assert "+aiomysql" not in readme_src
    assert "+aiosqlite" not in readme_src
