# backend/tests/test_generated_project_runtime.py
"""End-to-end runtime tests: actually import and execute generated code.

Every other test in this suite renders templates and checks the resulting
source text (or, at most, that it parses/byte-compiles). None of them ever
imports or runs the generated project, which is exactly why two critical bugs
shipped undetected:

  - `register_user()` never set `created_at`/`updated_at`, so every real
    registration attempt raised `IntegrityError` and returned 500.
  - The generated Alembic scaffolding was missing `prepend_sys_path` and
    `script.py.mako`, so `alembic revision --autogenerate` could not run.

These tests generate a real project onto disk, actually run it (import the
FastAPI app and drive it with TestClient; actually invoke the `alembic`
CLI), and would have caught both regressions.
"""
import subprocess
import sys
from pathlib import Path
from typing import Iterator, Set

import pytest

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def _top_level_module_names(codebase_dir: Path) -> Set[str]:
    """Names that `import server` (and everything it pulls in) will register
    in sys.modules for a generated project rooted at `codebase_dir`.
    """
    names: Set[str] = set()
    for item in codebase_dir.iterdir():
        if item.is_dir() and (item / "__init__.py").exists():
            names.add(item.name)
        elif item.is_file() and item.suffix == ".py":
            names.add(item.stem)
    return names


def _purge_modules(names: Set[str]) -> None:
    """Remove `names` and any dotted submodules of them from sys.modules.

    Generated projects across different tests/tmp_path directories reuse the
    same top-level module names (server, config, database, auth, rbac, ...).
    Without this, the second project generated in a test session would silently
    reuse the first project's already-imported (and differently-configured)
    modules instead of importing its own.
    """
    for mod_name in list(sys.modules):
        if mod_name in names or any(mod_name.startswith(f"{n}.") for n in names):
            del sys.modules[mod_name]


class _GeneratedProjectImporter:
    """Context manager that puts a generated project's root on sys.path,
    imports it cleanly (purging any stale same-named modules first), and
    restores sys.path / sys.modules on exit.
    """

    def __init__(self, codebase_dir: Path):
        self.codebase_dir = codebase_dir
        self._module_names = _top_level_module_names(codebase_dir)
        self._path_str = str(codebase_dir)

    def __enter__(self):
        _purge_modules(self._module_names)
        sys.path.insert(0, self._path_str)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._path_str in sys.path:
            sys.path.remove(self._path_str)
        _purge_modules(self._module_names)


@pytest.fixture
def isolated_sys_path() -> Iterator[None]:
    original_path = list(sys.path)
    original_modules = set(sys.modules)
    try:
        yield
    finally:
        sys.path[:] = original_path
        for mod_name in list(sys.modules):
            if mod_name not in original_modules:
                del sys.modules[mod_name]


def test_register_login_me_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """Generate an auth+RBAC-enabled project, actually run it, and drive
    /auth/register -> /auth/login -> /auth/me through a real FastAPI TestClient
    backed by a real (throwaway) sqlite database.
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    # shophub_mini.yml declares auth.jwt.secret_env_var: JWT_SECRET
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        database_base = importlib.import_module("database.base")

        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # --- register: this is the call that used to raise IntegrityError
            # and return 500 because created_at/updated_at were never set. ---
            register_resp = client.post(
                "/auth/register",
                json={"email": "alice@example.com", "password": "supersecret123"},
            )
            assert register_resp.status_code == 201, register_resp.text
            body = register_resp.json()
            assert body["email"] == "alice@example.com"
            assert body["is_active"] is True

            # RBAC bootstrap: the first user registered must get every declared
            # role (shophub_mini.yml declares roles: [admin, customer]), or
            # nobody could ever pass a require_roles(...) check afterwards.
            assert set(body["roles"]) == {"admin", "customer"}

            # created_at/updated_at aren't in the API response schema, so verify
            # directly against the database that they were actually populated.
            db = database_base.SessionLocal()
            try:
                database_models = importlib.import_module("database.models")
                user_row = db.query(database_models.User).filter_by(email="alice@example.com").first()
                assert user_row is not None
                assert user_row.created_at is not None
                assert user_row.updated_at is not None
            finally:
                db.close()

            # --- login ---
            login_resp = client.post(
                "/auth/login",
                json={"email": "alice@example.com", "password": "supersecret123"},
            )
            assert login_resp.status_code == 200, login_resp.text
            tokens = login_resp.json()
            assert "access_token" in tokens
            assert "refresh_token" in tokens

            # --- me ---
            me_resp = client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            assert me_resp.status_code == 200, me_resp.text
            assert me_resp.json()["email"] == "alice@example.com"

            # A refresh token must NOT work as an access token (I4: token type
            # enforcement) - /auth/me must reject it.
            me_with_refresh_resp = client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
            )
            assert me_with_refresh_resp.status_code == 401

            # A second user registered afterwards must NOT get bootstrap roles.
            second_resp = client.post(
                "/auth/register",
                json={"email": "bob@example.com", "password": "supersecret123"},
            )
            assert second_resp.status_code == 201, second_resp.text
            assert second_resp.json()["roles"] == []


def test_alembic_autogenerate_runs_against_real_generated_project(tmp_path):
    """Generate a project onto real disk and actually invoke
    `alembic revision --autogenerate` against it - this is the exact command
    that used to fail with:
      - ModuleNotFoundError: No module named 'config' (missing prepend_sys_path)
      - FileNotFoundError: 'alembic/script.py.mako' (template never written)
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "alembic_test.db"
    env = {
        **__import__("os").environ,
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
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
    assert "create_table('categories'" in migration_src or 'create_table("categories"' in migration_src
