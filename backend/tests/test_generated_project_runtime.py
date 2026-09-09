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
    """Restore sys.path after the test.

    Deliberately does NOT also purge every module newly imported during the
    test from sys.modules (an earlier version of this fixture did). That
    blanket purge evicts third-party compiled-extension modules too -
    `cryptography` (via python-jose) chief among them - and reimporting those
    from a cleared sys.modules state does not give you a clean reload: the
    Rust/C extension bindings underneath stay initialized process-wide, so
    the freshly re-created Python-level classes (e.g.
    `cryptography.hazmat.primitives.hashes.HashAlgorithm`) are no longer the
    same objects other still-cached code compares against, and `isinstance`
    checks that used to pass start failing (`jose.exceptions.JWSError:
    Expected instance of hashes.HashAlgorithm`) - which only surfaces once a
    second in-process test in the same session also drives a JWT-signing
    code path. `_GeneratedProjectImporter` above already purges exactly the
    generated project's own module names (on both __enter__ and __exit__),
    which is what actually needs fresh reimporting between tests/projects;
    third-party libraries are safe, and necessary, to leave warm in
    sys.modules across tests.
    """
    original_path = list(sys.path)
    try:
        yield
    finally:
        sys.path[:] = original_path


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


def test_module_crud_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """Generate a project from shophub_mini.yml (auth + RBAC + a multi-entity
    `catalog` module), stand up the real app via TestClient, and drive a full
    CRUD round trip through the module-singleton service/routes code path that
    (before this test) only ever had string/ast.parse coverage - never actually
    ran: POST -> GET by id -> PUT -> GET list -> DELETE -> GET (404).

    Also confirms a role-less second user gets a real 403 (not just "some
    non-2xx code") from an RBAC-restricted action, exercising the module
    router's baked-in `Depends(require_roles(...))`.
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "crud_runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # Bootstrap admin: first user registered gets every declared role
            # (shophub_mini.yml declares roles: [admin, customer]).
            register_resp = client.post(
                "/auth/register",
                json={"email": "admin@example.com", "password": "supersecret123"},
            )
            assert register_resp.status_code == 201, register_resp.text
            assert set(register_resp.json()["roles"]) == {"admin", "customer"}

            login_resp = client.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "supersecret123"},
            )
            assert login_resp.status_code == 200, login_resp.text
            admin_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

            # --- create ---
            create_resp = client.post(
                "/categories", json={"name": "Books"}, headers=admin_headers
            )
            assert create_resp.status_code == 201, create_resp.text
            category = create_resp.json()
            assert category["name"] == "Books"
            category_id = category["id"]
            assert isinstance(category_id, int)

            # --- read by id ---
            get_resp = client.get(f"/categories/{category_id}", headers=admin_headers)
            assert get_resp.status_code == 200, get_resp.text
            assert get_resp.json() == {"id": category_id, "name": "Books"}

            # --- update ---
            update_resp = client.put(
                f"/categories/{category_id}",
                json={"name": "Fiction"},
                headers=admin_headers,
            )
            assert update_resp.status_code == 200, update_resp.text
            assert update_resp.json()["name"] == "Fiction"

            # --- list, confirm the update is reflected ---
            list_resp = client.get("/categories", headers=admin_headers)
            assert list_resp.status_code == 200, list_resp.text
            listed = list_resp.json()
            assert any(item["id"] == category_id and item["name"] == "Fiction" for item in listed)

            # --- delete ---
            delete_resp = client.delete(f"/categories/{category_id}", headers=admin_headers)
            assert delete_resp.status_code == 204, delete_resp.text

            # --- confirm gone ---
            gone_resp = client.get(f"/categories/{category_id}", headers=admin_headers)
            assert gone_resp.status_code == 404, gone_resp.text

            # --- a role-less second user gets 403 on an RBAC-restricted action ---
            second_register_resp = client.post(
                "/auth/register",
                json={"email": "roleless@example.com", "password": "supersecret123"},
            )
            assert second_register_resp.status_code == 201, second_register_resp.text
            assert second_register_resp.json()["roles"] == []

            second_login_resp = client.post(
                "/auth/login",
                json={"email": "roleless@example.com", "password": "supersecret123"},
            )
            assert second_login_resp.status_code == 200, second_login_resp.text
            second_headers = {
                "Authorization": f"Bearer {second_login_resp.json()['access_token']}"
            }

            forbidden_resp = client.post(
                "/categories", json={"name": "Should not be allowed"}, headers=second_headers
            )
            assert forbidden_resp.status_code == 403, forbidden_resp.text


def test_renamed_auth_module_serves_over_real_http_and_old_auth_path_is_gone(
    tmp_path, monkeypatch, isolated_sys_path
):
    """Generate a project whose auth service is renamed via a `services:` entry
    ({name: identity, entities: [User]}), stand up the real app, and confirm
    the 3-way name sync between rbac.py's import, server.py's route prefix,
    and service.py's OAuth2PasswordBearer(tokenUrl=...) actually works over
    real HTTP - and that the default /auth/* paths no longer exist.
    """
    erd = load_erd(f"{FIXTURES}/renamed_auth.yml")
    state = translate(erd)
    assert state["auth_module_name"] == "identity"

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    # Sanity-check on disk before even importing: the auth module was written
    # under modules/identity/, not modules/auth/.
    assert (codebase_dir / "modules" / "identity" / "routes.py").exists()
    assert not (codebase_dir / "modules" / "auth").exists()

    db_path = tmp_path / "renamed_auth_runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            register_resp = client.post(
                "/identity/register",
                json={"email": "alice@example.com", "password": "supersecret123"},
            )
            assert register_resp.status_code == 201, register_resp.text
            assert register_resp.json()["email"] == "alice@example.com"

            login_resp = client.post(
                "/identity/login",
                json={"email": "alice@example.com", "password": "supersecret123"},
            )
            assert login_resp.status_code == 200, login_resp.text
            access_token = login_resp.json()["access_token"]

            me_resp = client.get(
                "/identity/me", headers={"Authorization": f"Bearer {access_token}"}
            )
            assert me_resp.status_code == 200, me_resp.text
            assert me_resp.json()["email"] == "alice@example.com"

            # The old default /auth/* paths must not exist at all.
            assert client.post(
                "/auth/register", json={"email": "bob@example.com", "password": "supersecret123"}
            ).status_code == 404
            assert client.post(
                "/auth/login", json={"email": "alice@example.com", "password": "supersecret123"}
            ).status_code == 404
            assert client.get(
                "/auth/me", headers={"Authorization": f"Bearer {access_token}"}
            ).status_code == 404


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


def test_owned_relationship_fk_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """valid_full.yml: Product has many-to-one to Category. Covers the FK
    exposure + validation + filter query param all the way through real HTTP.

    Unlike the brief's original description, valid_full.yml actually has
    auth+RBAC enabled (rbac.default_permissions gates create/list on every
    entity, including Category/Product, which don't override it), so this
    still needs a JWT_SECRET and an authenticated admin bearer token for
    every write and list call - same bootstrap-admin pattern as the
    shophub_mini.yml tests above.
    """
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "fk_runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # Bootstrap admin: first user registered gets every declared role
            # (valid_full.yml declares roles: [admin, editor, viewer]).
            register_resp = client.post(
                "/auth/register", json={"email": "admin@example.com", "password": "supersecret123"}
            )
            assert register_resp.status_code == 201, register_resp.text
            assert set(register_resp.json()["roles"]) == {"admin", "editor", "viewer"}

            login_resp = client.post(
                "/auth/login", json={"email": "admin@example.com", "password": "supersecret123"}
            )
            assert login_resp.status_code == 200, login_resp.text
            admin_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

            cat_resp = client.post("/categories", json={"name": "Electronics"}, headers=admin_headers)
            assert cat_resp.status_code == 201, cat_resp.text
            category_id = cat_resp.json()["id"]

            # valid FK: succeeds, response includes category_id
            ok_resp = client.post(
                "/products",
                json={"name": "Widget", "price": 9.99, "sku": "W1", "category_id": category_id},
                headers=admin_headers,
            )
            assert ok_resp.status_code == 201, ok_resp.text
            assert ok_resp.json()["category_id"] == category_id

            # invalid FK: 400, not a raw 500
            bad_resp = client.post(
                "/products",
                json={"name": "Gadget", "price": 5.0, "sku": "G1", "category_id": 999999},
                headers=admin_headers,
            )
            assert bad_resp.status_code == 400, bad_resp.text

            # a second category + product, to prove the filter actually filters
            cat2_resp = client.post("/categories", json={"name": "Books"}, headers=admin_headers)
            assert cat2_resp.status_code == 201, cat2_resp.text
            category2_id = cat2_resp.json()["id"]
            second_product_resp = client.post(
                "/products",
                json={"name": "Novel", "price": 12.0, "sku": "N1", "category_id": category2_id},
                headers=admin_headers,
            )
            assert second_product_resp.status_code == 201, second_product_resp.text

            filtered_resp = client.get(f"/products?category_id={category_id}", headers=admin_headers)
            assert filtered_resp.status_code == 200, filtered_resp.text
            names = [p["name"] for p in filtered_resp.json()]
            assert names == ["Widget"]


def test_many_to_many_id_list_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """many_to_many.yml: Post<->Tag. No auth block in the fixture, so
    auth/rbac are both disabled - no JWT_SECRET needed.
    """
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
            assert tag1_resp.status_code == 201, tag1_resp.text
            tag2_resp = client.post("/tags", json={"name": "fastapi"})
            assert tag2_resp.status_code == 201, tag2_resp.text
            tag1_id, tag2_id = tag1_resp.json()["id"], tag2_resp.json()["id"]

            # link tags directly via the ORM - there is no write endpoint for
            # many-to-many (out of scope per spec)
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
            assert login_resp.status_code == 200, login_resp.text
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
            assert ok_resp.json()["user_id"] == user_id
            assert ok_resp.json()["product_id"] == product_id

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


def test_self_referential_relationships_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """self_referential.yml: Employee.manager (many-to-one) and Category.children
    (one-to-many), both self-referential. No auth/rbac in this fixture. Covers the
    full stack for a self-referential FK: create, read back the FK, filter by it,
    and reject a nonexistent FK - exactly like the non-self-referential
    owned-relationship test above, but with source and target being the same
    entity, which is exactly the case that used to make `generate` emit an
    unimportable project (duplicate FK column / duplicate relationship() /
    duplicate keyword argument).
    """
    erd = load_erd(f"{FIXTURES}/self_referential.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "self_ref_runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # --- Employee.manager (many-to-one self-referential) ---
            boss_resp = client.post("/employees", json={"name": "Boss"})
            assert boss_resp.status_code == 201, boss_resp.text
            boss_id = boss_resp.json()["id"]
            assert boss_resp.json()["manager_id"] is None

            report_resp = client.post("/employees", json={"name": "Alice", "manager_id": boss_id})
            assert report_resp.status_code == 201, report_resp.text
            report_id = report_resp.json()["id"]
            assert report_resp.json()["manager_id"] == boss_id

            # a second, unrelated employee, to prove the filter actually filters
            client.post("/employees", json={"name": "Nobody"})

            filtered_resp = client.get(f"/employees?manager_id={boss_id}")
            assert filtered_resp.status_code == 200, filtered_resp.text
            names = [e["name"] for e in filtered_resp.json()]
            assert names == ["Alice"]

            bad_manager_resp = client.post("/employees", json={"name": "Bob", "manager_id": 999999})
            assert bad_manager_resp.status_code == 400, bad_manager_resp.text

            get_report_resp = client.get(f"/employees/{report_id}")
            assert get_report_resp.status_code == 200, get_report_resp.text
            assert get_report_resp.json()["manager_id"] == boss_id

            # --- Category.children (one-to-many self-referential) ---
            root_resp = client.post("/categories", json={"label": "Root"})
            assert root_resp.status_code == 201, root_resp.text
            root_id = root_resp.json()["id"]
            assert root_resp.json()["children_id"] is None

            child_resp = client.post("/categories", json={"label": "Child", "children_id": root_id})
            assert child_resp.status_code == 201, child_resp.text
            assert child_resp.json()["children_id"] == root_id

            bad_parent_resp = client.post("/categories", json={"label": "Orphan", "children_id": 999999})
            assert bad_parent_resp.status_code == 400, bad_parent_resp.text


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
