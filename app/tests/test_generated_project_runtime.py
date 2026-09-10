# app/tests/test_generated_project_runtime.py
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
import ast
import subprocess
import sys
from pathlib import Path
from typing import Iterator, Set

import pytest

from app.erd.loader import load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator

FIXTURES = "app/tests/fixtures/erd"


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


def test_rls_bypass_role_sees_all_rows_non_bypass_sees_only_own(tmp_path, monkeypatch, isolated_sys_path):
    """rls_root_owned.yml: admin (bypass_roles) sees every order via list and can read/
    update/delete anyone's; customer (no bypass) only ever sees their own, and a
    customer's attempt to touch another user's order gets a plain 404, not 403.
    """
    erd = load_erd(f"{FIXTURES}/rls_root_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_bypass_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            admin_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'admin@example.com', 'password': 'supersecret123'}).json()['access_token']}"}
            assert set(admin_resp.json()["roles"]) == {"admin", "customer"}  # bootstrap: first user gets every role
            admin_id = admin_resp.json()["id"]

            cust_resp = client.post("/auth/register", json={"email": "cust@example.com", "password": "supersecret123"})
            assert cust_resp.json()["roles"] == []
            # give the second user the customer role directly via the ORM (no role-grant
            # endpoint exists - out of this plan's scope) so it can exercise a real,
            # non-bypass RLS path rather than being blocked by RBAC entirely
            db_path_for_grant = db_path
            import sqlite3
            conn = sqlite3.connect(str(db_path_for_grant))
            conn.execute("UPDATE users SET roles = '[\"customer\"]' WHERE email = 'cust@example.com'")
            conn.commit()
            conn.close()
            cust_login = client.post("/auth/login", json={"email": "cust@example.com", "password": "supersecret123"})
            cust_headers = {"Authorization": f"Bearer {cust_login.json()['access_token']}"}
            cust_id = cust_resp.json()["id"]

            order_admin = client.post("/orders", json={"status": "pending"}, headers=admin_headers).json()
            order_cust = client.post("/orders", json={"status": "pending"}, headers=cust_headers).json()

            # FINAL-REVIEW FIX 1: a bypass-role caller's own POST must be stamped with ITS
            # OWN id, never NULL. Bypass means "I may see and act on everyone's rows", not
            # "the rows I create belong to nobody" - a NULL owner here would be permanently
            # invisible to every non-bypass caller (and a 500 on a non-nullable owner FK).
            # This assertion is the regression guard: before the fix, order_admin["user_id"]
            # came back None and every other assertion in this test still passed.
            assert order_admin["user_id"] == admin_id
            assert order_cust["user_id"] == cust_id

            # ...and it is genuinely persisted that way, not just echoed back
            assert client.get(f"/orders/{order_admin['id']}", headers=admin_headers).json()["user_id"] == admin_id

            # admin (bypass) sees both via list
            admin_list = client.get("/orders", headers=admin_headers).json()
            assert {o["id"] for o in admin_list} == {order_admin["id"], order_cust["id"]}

            # customer (no bypass) sees only their own via list
            cust_list = client.get("/orders", headers=cust_headers).json()
            assert [o["id"] for o in cust_list] == [order_cust["id"]]

            # customer's own order is fully accessible
            assert client.get(f"/orders/{order_cust['id']}", headers=cust_headers).status_code == 200
            assert client.put(f"/orders/{order_cust['id']}", json={"status": "shipped"}, headers=cust_headers).status_code == 200

            # customer cannot see, update, or delete admin's order - plain 404, not 403
            assert client.get(f"/orders/{order_admin['id']}", headers=cust_headers).status_code == 404
            assert client.put(f"/orders/{order_admin['id']}", json={"status": "shipped"}, headers=cust_headers).status_code == 404
            assert client.delete(f"/orders/{order_admin['id']}", headers=cust_headers).status_code == 404

            # admin (bypass) CAN touch customer's order
            assert client.get(f"/orders/{order_cust['id']}", headers=admin_headers).status_code == 200
            assert client.delete(f"/orders/{order_cust['id']}", headers=admin_headers).status_code == 204


def test_rls_header_identity_isolates_tenants_and_422s_on_missing_header(tmp_path, monkeypatch, isolated_sys_path):
    erd = load_erd(f"{FIXTURES}/rls_header_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_header_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            tenant1 = client.post("/tenants", json={"name": "Acme"}).json()
            tenant2 = client.post("/tenants", json={"name": "Globex"}).json()

            # missing header -> native FastAPI 422, no custom error handling involved
            missing_header_resp = client.get("/orders")
            assert missing_header_resp.status_code == 422

            order1 = client.post("/orders", json={"status": "pending"}, headers={"X-Tenant-Id": str(tenant1["id"])}).json()
            client.post("/orders", json={"status": "pending"}, headers={"X-Tenant-Id": str(tenant2["id"])})

            list_t1 = client.get("/orders", headers={"X-Tenant-Id": str(tenant1["id"])}).json()
            assert [o["id"] for o in list_t1] == [order1["id"]]

            # tenant2's header cannot see tenant1's order - 404, not 403
            cross_tenant_resp = client.get(f"/orders/{order1['id']}", headers={"X-Tenant-Id": str(tenant2["id"])})
            assert cross_tenant_resp.status_code == 404


def test_rls_header_create_rejects_an_owner_id_that_does_not_exist(tmp_path, monkeypatch, isolated_sys_path):
    """FINAL-REVIEW FIX 4, over real HTTP. X-Tenant-Id is raw client input with nothing
    vouching for it (unlike an auth_user-sourced owner id, which the JWT auth flow has
    already resolved to a real User row). Before this fix the generated create skipped the
    owner-existence check entirely for the header case, so `X-Tenant-Id: 999999` wrote a
    dangling tenant_id and returned 201. It must instead be rejected with the same
    ValueError->400 shape any other nonexistent FK gets - and no row may be written.
    """
    erd = load_erd(f"{FIXTURES}/rls_header_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_header_owner_check_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            tenant = client.post("/tenants", json={"name": "Acme"}).json()

            # a real tenant id still works, unchanged
            ok_resp = client.post(
                "/orders", json={"status": "pending"}, headers={"X-Tenant-Id": str(tenant["id"])}
            )
            assert ok_resp.status_code == 201, ok_resp.text
            assert ok_resp.json()["tenant_id"] == tenant["id"]

            # a tenant id that does not exist is rejected exactly like any other bad FK
            bad_resp = client.post(
                "/orders", json={"status": "pending"}, headers={"X-Tenant-Id": "999999"}
            )
            assert bad_resp.status_code == 400, bad_resp.text
            assert "999999" in bad_resp.json()["detail"]

            # ...and nothing was written for the bogus tenant
            assert client.get("/orders", headers={"X-Tenant-Id": "999999"}).json() == []
            assert len(client.get("/orders", headers={"X-Tenant-Id": str(tenant["id"])}).json()) == 1


def test_rls_header_with_rbac_gates_action_but_header_still_governs_ownership(tmp_path, monkeypatch, isolated_sys_path):
    """rls_header_owned_with_rbac.yml: RBAC gates the action (a valid admin JWT is required
    to call these routes at all), but the header - not the authenticated user - still
    determines ownership. The same admin user, authenticated once, sees a different slice
    of /orders depending purely on which tenant's X-Tenant-Id header it sends, proving RBAC
    and header-RLS compose independently rather than one silently overriding the other.
    """
    erd = load_erd(f"{FIXTURES}/rls_header_owned_with_rbac.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_header_rbac_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # bootstrap admin: first user registered gets every declared role (here, just "admin")
            register_resp = client.post(
                "/auth/register", json={"email": "admin@example.com", "password": "supersecret123"}
            )
            assert register_resp.status_code == 201, register_resp.text
            assert set(register_resp.json()["roles"]) == {"admin"}

            login_resp = client.post(
                "/auth/login", json={"email": "admin@example.com", "password": "supersecret123"}
            )
            assert login_resp.status_code == 200, login_resp.text
            admin_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

            tenant1 = client.post("/tenants", json={"name": "Acme"}, headers=admin_headers).json()
            tenant2 = client.post("/tenants", json={"name": "Globex"}, headers=admin_headers).json()

            order1 = client.post(
                "/orders",
                json={"status": "pending"},
                headers={**admin_headers, "X-Tenant-Id": str(tenant1["id"])},
            ).json()
            client.post(
                "/orders",
                json={"status": "pending"},
                headers={**admin_headers, "X-Tenant-Id": str(tenant2["id"])},
            )

            # same admin JWT, tenant1's header -> only tenant1's order (not both, even though
            # the same RBAC-authorized user created both rows)
            list_t1 = client.get(
                "/orders", headers={**admin_headers, "X-Tenant-Id": str(tenant1["id"])}
            ).json()
            assert [o["id"] for o in list_t1] == [order1["id"]]

            # same admin JWT, tenant2's header -> cannot see tenant1's order: 404, not 403
            # (RBAC already let the request through - the header's ownership filter is what
            # denies it, independently of the caller's role)
            cross_tenant_resp = client.get(
                f"/orders/{order1['id']}", headers={**admin_headers, "X-Tenant-Id": str(tenant2["id"])}
            )
            assert cross_tenant_resp.status_code == 404

            # missing header entirely -> native FastAPI 422, even with valid RBAC credentials
            missing_header_resp = client.get("/orders", headers=admin_headers)
            assert missing_header_resp.status_code == 422


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


def test_async_many_to_many_id_list_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """async_relationships.yml: Author/Tag/Post (Post has a many-to-one to Author and a
    many-to-many to Tag). No auth block in the fixture, so no JWT_SECRET needed - same
    shape as test_many_to_many_id_list_round_trip_against_real_generated_app above, but
    generated in async_mode.

    This is the regression test for the async create_<model>() m2m bug: async create()
    committed and refreshed the new row but never eagerly loaded its many-to-many
    relationship attributes, so module_schemas.py.jinja's response model_validator
    (which does `getattr(data, "<rel.attribute>", [])` to compute `<target>_ids`)
    triggered a lazy load during response serialization - which raises
    sqlalchemy.exc.MissingGreenlet under AsyncSession and turns POST into a 500 (after
    the row has already been written). POST /tags and POST /posts returning 201 with
    the correct id-list field is exactly what used to fail here.
    """
    erd = load_erd(f"{FIXTURES}/async_relationships.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "async_m2m_runtime_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import asyncio
        import importlib

        server_module = importlib.import_module("server")
        database_base = importlib.import_module("database.base")
        database_models = importlib.import_module("database.models")
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # --- the critical assertions: these 500'd before the fix ---
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
            # many-to-many (out of scope per spec). Async session, so this needs its
            # own event loop rather than the sync SessionLocal()/db.query() pattern
            # used by the sync many-to-many test; selectinload eagerly loads the m2m
            # collection before it's touched, mirroring get_post_by_id's own pattern,
            # so this helper itself doesn't hit the same lazy-load-outside-greenlet
            # trap this test exists to catch on the create() path.
            async def _link_tags():
                async with database_base.AsyncSessionLocal() as db:
                    post_result = await db.execute(
                        select(database_models.Post)
                        .options(selectinload(database_models.Post.tags))
                        .where(database_models.Post.id == post_id)
                    )
                    post_obj = post_result.scalar_one()
                    tags_result = await db.execute(
                        select(database_models.Tag).where(database_models.Tag.id.in_([tag1_id, tag2_id]))
                    )
                    tag_objs = tags_result.scalars().all()
                    post_obj.tags.extend(tag_objs)
                    await db.commit()

            asyncio.run(_link_tags())

            get_resp = client.get(f"/posts/{post_id}")
            assert get_resp.status_code == 200, get_resp.text
            assert sorted(get_resp.json()["tag_ids"]) == sorted([tag1_id, tag2_id])

            list_resp = client.get("/posts")
            assert list_resp.status_code == 200, list_resp.text
            listed_post = next(p for p in list_resp.json() if p["id"] == post_id)
            assert sorted(listed_post["tag_ids"]) == sorted([tag1_id, tag2_id])


def test_rls_create_schema_silently_ignores_client_supplied_owner_field(tmp_path, monkeypatch, isolated_sys_path):
    """The schema-level guarantee, proven over real HTTP: a client that includes
    user_id in the POST /orders payload gets it silently dropped by Pydantic (unknown
    field, not part of OrderCreate) - the created row's owner is still exactly the
    resolved owner_id, matching test_root_owned_create_service_actually_ignores_client_supplied_owner's
    proof one layer down, now proven at the HTTP boundary too.

    rls_root_owned.yml's Order.rls.bypass_roles is [admin], and (per the bootstrap
    convention exercised elsewhere in this file) the FIRST user ever registered gets
    every declared role, including admin - so registering only one user and using it
    as "the real owner" would make module_routes.py.jinja's
    `owner_id = None if <bypass role> else current_user.id` resolve owner_id to None on
    create, defeating the very thing this test wants to prove. So: register a bootstrap
    admin first (discarded), then a second user granted only the non-bypass "customer"
    role directly via the DB (same technique as
    test_rls_bypass_role_sees_all_rows_non_bypass_sees_only_own above) - that second
    user is "real_owner_id" here, and its create call resolves a real, non-None owner_id.
    """
    erd = load_erd(f"{FIXTURES}/rls_root_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_schema_http_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # bootstrap admin (gets every role, including the bypass role) - registered
            # only so the "real" owner below isn't the first user, and discarded.
            client.post("/auth/register", json={"email": "bootstrap@example.com", "password": "supersecret123"})

            register_resp = client.post("/auth/register", json={"email": "real@example.com", "password": "supersecret123"})
            assert register_resp.json()["roles"] == []
            real_owner_id = register_resp.json()["id"]

            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.execute("UPDATE users SET roles = '[\"customer\"]' WHERE email = 'real@example.com'")
            conn.commit()
            conn.close()

            login_resp = client.post("/auth/login", json={"email": "real@example.com", "password": "supersecret123"})
            headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

            order_resp = client.post(
                "/orders", json={"status": "pending", "user_id": real_owner_id + 999}, headers=headers
            )
            assert order_resp.status_code == 201, order_resp.text
            assert order_resp.json()["user_id"] == real_owner_id


def test_async_mode_rls_full_stack_round_trip_against_real_generated_app(tmp_path, monkeypatch, isolated_sys_path):
    """rls_async_full.yml driven through real HTTP + a real aiosqlite DB - proves root
    ownership, one-hop cascade, and admin bypass all compose correctly through the full
    async stack (routes -> service -> repo -> DB), mirroring what the sync-path tests in
    Tasks 4-8 already proved individually, now proven together in async_mode. Uses
    TestClient as a context manager to exercise server.py's async lifespan
    (await init_db() / await engine.dispose()), per the async-support plan's precedent.
    """
    erd = load_erd(f"{FIXTURES}/rls_async_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_async_full_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            assert admin_resp.status_code == 201, admin_resp.text
            assert set(admin_resp.json()["roles"]) == {"admin", "customer"}  # bootstrap
            admin_id = admin_resp.json()["id"]
            admin_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'admin@example.com', 'password': 'supersecret123'}).json()['access_token']}"}

            cust_resp = client.post("/auth/register", json={"email": "cust@example.com", "password": "supersecret123"})
            assert cust_resp.json()["roles"] == []
            cust_id = cust_resp.json()["id"]
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.execute("UPDATE users SET roles = '[\"customer\"]' WHERE email = 'cust@example.com'")
            conn.commit()
            conn.close()
            cust_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'cust@example.com', 'password': 'supersecret123'}).json()['access_token']}"}

            # root ownership: each user's own order, async create injects owner correctly
            order_admin = client.post("/orders", json={"status": "pending"}, headers=admin_headers).json()
            order_cust = client.post("/orders", json={"status": "pending"}, headers=cust_headers).json()

            # FINAL-REVIEW FIX 1 (async parity): the bypass-role caller's own created row is
            # owned by that caller, not NULL. See the sync twin of this assertion in
            # test_rls_bypass_role_sees_all_rows_non_bypass_sees_only_own.
            assert order_admin["user_id"] == admin_id
            assert order_cust["user_id"] == cust_id
            assert client.get(f"/orders/{order_admin['id']}", headers=admin_headers).json()["user_id"] == admin_id

            # customer (no bypass) sees only their own order via async list
            cust_orders = client.get("/orders", headers=cust_headers).json()
            assert [o["id"] for o in cust_orders] == [order_cust["id"]]

            # admin (bypass) sees both
            admin_orders = client.get("/orders", headers=admin_headers).json()
            assert {o["id"] for o in admin_orders} == {order_admin["id"], order_cust["id"]}

            # 1-hop cascade: customer creates an OrderItem on their own order (async)
            item_resp = client.post(
                "/order_items", json={"quantity": 2, "order_id": order_cust["id"]}, headers=cust_headers
            )
            assert item_resp.status_code == 201, item_resp.text

            # customer cannot attach an OrderItem to admin's order - same 400 as a bad FK
            bad_item_resp = client.post(
                "/order_items", json={"quantity": 1, "order_id": order_admin["id"]}, headers=cust_headers
            )
            assert bad_item_resp.status_code == 400, bad_item_resp.text

            # customer cannot read/update/delete admin's order - 404, not 403
            assert client.get(f"/orders/{order_admin['id']}", headers=cust_headers).status_code == 404
            assert client.delete(f"/orders/{order_admin['id']}", headers=cust_headers).status_code == 404

    # `with TestClient(...)` has already exited here, running the async lifespan
    # shutdown (await engine.dispose()) - reaching this line without a hang is itself
    # part of what this test proves, per the async-support plan's established pattern.


def test_admin_user_management_403_then_200_round_trip(tmp_path, monkeypatch, isolated_sys_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "admin_routes_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            assert set(admin_resp.json()["roles"]) == {"admin", "customer"}  # bootstrap
            admin_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'admin@example.com', 'password': 'supersecret123'}).json()['access_token']}"}

            cust_resp = client.post("/auth/register", json={"email": "cust@example.com", "password": "supersecret123"})
            assert cust_resp.json()["roles"] == []
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.execute("UPDATE users SET roles = '[\"customer\"]' WHERE email = 'cust@example.com'")
            conn.commit()
            conn.close()
            cust_login = client.post("/auth/login", json={"email": "cust@example.com", "password": "supersecret123"})
            cust_headers = {"Authorization": f"Bearer {cust_login.json()['access_token']}"}
            cust_id = cust_resp.json()["id"]

            # non-admin gets 403 on every admin endpoint
            #
            # DEVIATION FROM BRIEF (documented per task-6-brief.md's own instruction to
            # fix, not silently deviate, when literal test code and literal implementation
            # code disagree): the brief's literal test code here calls bare "/users", but
            # these admin routes are appended to auth/routes.py.jinja's single `router =
            # APIRouter()` (per the brief's own Step 3.6, "Add the admin routes ... at the
            # end of the file"), and server.py.jinja (out of scope for this task - the
            # task's file-touch list does not include it) mounts that whole router with
            # `app.include_router(auth_router, prefix="/{{ project.auth_module_name }}",
            # ...)`, exactly like /register, /login, /refresh and /me above it in the same
            # file. So in a correctly-generated project these routes are only ever
            # reachable at /auth/users..., never bare /users - a bare-path call 404s
            # unconditionally, which is exactly what the un-prefixed brief literal test
            # code hit here (404, not the 403 it asserted). Prefixed every /users call in
            # this test with /auth to match real generated behavior.
            assert client.get("/auth/users", headers=cust_headers).status_code == 403
            assert client.get(f"/auth/users/{cust_id}", headers=cust_headers).status_code == 403
            assert client.put(f"/auth/users/{cust_id}/roles", json={"roles": ["admin"]}, headers=cust_headers).status_code == 403
            assert client.post(f"/auth/users/{cust_id}/deactivate", headers=cust_headers).status_code == 403

            # admin succeeds on all of them
            list_resp = client.get("/auth/users", headers=admin_headers)
            assert list_resp.status_code == 200
            assert cust_id in [u["id"] for u in list_resp.json()]

            get_resp = client.get(f"/auth/users/{cust_id}", headers=admin_headers)
            assert get_resp.status_code == 200
            assert get_resp.json()["id"] == cust_id

            roles_resp = client.put(f"/auth/users/{cust_id}/roles", json={"roles": ["admin", "customer"]}, headers=admin_headers)
            assert roles_resp.status_code == 200
            assert set(roles_resp.json()["roles"]) == {"admin", "customer"}

            bad_roles_resp = client.put(f"/auth/users/{cust_id}/roles", json={"roles": ["not_a_real_role"]}, headers=admin_headers)
            assert bad_roles_resp.status_code == 400

            deact_resp = client.post(f"/auth/users/{cust_id}/deactivate", headers=admin_headers)
            assert deact_resp.status_code == 200
            assert deact_resp.json()["is_active"] is False

            react_resp = client.post(f"/auth/users/{cust_id}/reactivate", headers=admin_headers)
            assert react_resp.status_code == 200
            assert react_resp.json()["is_active"] is True

            assert client.get("/auth/users/999999", headers=admin_headers).status_code == 404


def test_deactivated_user_access_and_refresh_tokens_are_rejected(tmp_path, monkeypatch, isolated_sys_path):
    """Regression test for the final-review Critical finding: deactivating a user
    must not just block future logins (already covered by test_login... elsewhere) -
    it must also invalidate that user's ALREADY-ISSUED access and refresh tokens.
    Before the fix, get_current_user (used by /auth/me and every RBAC-protected
    route) and /auth/refresh never re-checked is_active after initial login, so a
    deactivated user's existing access token kept working forever and /auth/refresh
    kept minting fresh token pairs for them indefinitely.
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "deactivate_token_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            # bootstrap admin (first user registered gets every declared role)
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            assert set(admin_resp.json()["roles"]) == {"admin", "customer"}
            admin_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'admin@example.com', 'password': 'supersecret123'}).json()['access_token']}"}

            # target user whose tokens we'll capture and then invalidate
            target_resp = client.post("/auth/register", json={"email": "target@example.com", "password": "supersecret123"})
            target_id = target_resp.json()["id"]

            target_login = client.post("/auth/login", json={"email": "target@example.com", "password": "supersecret123"})
            assert target_login.status_code == 200, target_login.text
            old_access_token = target_login.json()["access_token"]
            old_refresh_token = target_login.json()["refresh_token"]
            target_headers = {"Authorization": f"Bearer {old_access_token}"}

            # the not-yet-deactivated token works, as a control
            assert client.get("/auth/me", headers=target_headers).status_code == 200

            deact_resp = client.post(f"/auth/users/{target_id}/deactivate", headers=admin_headers)
            assert deact_resp.status_code == 200, deact_resp.text
            assert deact_resp.json()["is_active"] is False

            # the OLD access token, issued before deactivation, must now be rejected
            me_resp = client.get("/auth/me", headers=target_headers)
            assert me_resp.status_code == 401, me_resp.text

            # the OLD refresh token must also be rejected - no minting fresh tokens
            # for a deactivated user
            refresh_resp = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
            assert refresh_resp.status_code == 401, refresh_resp.text

            # reactivating restores normal access: a fresh login works again
            react_resp = client.post(f"/auth/users/{target_id}/reactivate", headers=admin_headers)
            assert react_resp.status_code == 200, react_resp.text
            assert react_resp.json()["is_active"] is True

            new_login = client.post("/auth/login", json={"email": "target@example.com", "password": "supersecret123"})
            assert new_login.status_code == 200, new_login.text


def test_forgot_password_and_resend_verification_are_enumeration_safe(tmp_path, monkeypatch, isolated_sys_path):
    """The one test that would catch a status-code or body-shape leak of
    'does this email exist' - the single most important correctness property
    Task 6 must preserve.
    """
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "enum_safe_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            client.post("/auth/register", json={"email": "real@example.com", "password": "supersecret123"})

            real_resp = client.post("/auth/forgot-password", json={"email": "real@example.com"})
            fake_resp = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
            assert real_resp.status_code == fake_resp.status_code == 200
            assert real_resp.json() == fake_resp.json()

            real_resend = client.post("/auth/resend-verification", json={"email": "real@example.com"})
            fake_resend = client.post("/auth/resend-verification", json={"email": "nobody@example.com"})
            assert real_resend.status_code == fake_resend.status_code == 200
            assert real_resend.json() == fake_resend.json()


def test_full_email_verification_flow_over_http(tmp_path, monkeypatch, isolated_sys_path, capfd):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "email_verif_http_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import re

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            register_resp = client.post("/auth/register", json={"email": "eve@example.com", "password": "supersecret123"})
            assert register_resp.status_code == 201, register_resp.text

            login_resp = client.post("/auth/login", json={"email": "eve@example.com", "password": "supersecret123"})
            assert login_resp.status_code == 401, login_resp.text  # unverified

            captured = capfd.readouterr()
            match = re.search(r"Your verification token: (\S+)", captured.out)
            assert match, f"no verification token found in captured stdout: {captured.out}"
            token = match.group(1)

            verify_resp = client.post("/auth/verify-email", json={"token": token})
            assert verify_resp.status_code == 200, verify_resp.text

            login_resp2 = client.post("/auth/login", json={"email": "eve@example.com", "password": "supersecret123"})
            assert login_resp2.status_code == 200, login_resp2.text

            bad_verify_resp = client.post("/auth/verify-email", json={"token": "garbage"})
            assert bad_verify_resp.status_code == 400


def test_full_admin_approval_flow_over_http(tmp_path, monkeypatch, isolated_sys_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "admin_approval_http_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            assert set(admin_resp.json()["roles"]) == {"admin", "customer"}  # bootstrap gets every role
            # bootstrap (first-user) admin is auto-approved, symmetric with the existing
            # roles bootstrap - admin_approval mode would otherwise ship unbootstrappable,
            # since nobody could ever reach the /users/{id}/approve endpoint that only an
            # already-approved admin can call
            assert admin_resp.json()["is_approved"] is True
            admin_id = admin_resp.json()["id"]

            admin_login = client.post("/auth/login", json={"email": "admin@example.com", "password": "supersecret123"})
            assert admin_login.status_code == 200, admin_login.text
            admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

            pending_resp = client.post("/auth/register", json={"email": "pending@example.com", "password": "supersecret123"})
            assert pending_resp.status_code == 201, pending_resp.text
            pending_id = pending_resp.json()["id"]
            assert pending_resp.json()["is_approved"] is False

            pending_login = client.post("/auth/login", json={"email": "pending@example.com", "password": "supersecret123"})
            assert pending_login.status_code == 401, pending_login.text

            # DEVIATION FROM BRIEF (documented per the task-6 precedent in
            # test_admin_user_management_403_then_200_round_trip above, which found and
            # fixed the identical issue): the admin routes live on the same
            # `router = APIRouter()` as /register, /login, /me in auth/routes.py.jinja, and
            # server.py.jinja mounts that whole router under the /auth prefix - so this
            # route is only ever reachable as /auth/users/{id}/approve in a real generated
            # app, never bare /users/{id}/approve. Prefixed with /auth to match real
            # generated behavior (brief's literal text has the bare path).
            approve_resp = client.post(f"/auth/users/{pending_id}/approve", headers=admin_headers)
            assert approve_resp.status_code == 200, approve_resp.text
            assert approve_resp.json()["is_approved"] is True

            pending_login2 = client.post("/auth/login", json={"email": "pending@example.com", "password": "supersecret123"})
            assert pending_login2.status_code == 200, pending_login2.text


def test_full_forgot_reset_password_flow_over_http(tmp_path, monkeypatch, isolated_sys_path, capfd):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "forgot_reset_http_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import re

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            client.post("/auth/register", json={"email": "frank@example.com", "password": "originalpass1"})

            forgot_resp = client.post("/auth/forgot-password", json={"email": "frank@example.com"})
            assert forgot_resp.status_code == 200, forgot_resp.text

            captured = capfd.readouterr()
            match = re.search(r"Your password reset token: (\S+)", captured.out)
            assert match, f"no reset token found in captured stdout: {captured.out}"
            token = match.group(1)

            reset_resp = client.post("/auth/reset-password", json={"token": token, "new_password": "newpassword2"})
            assert reset_resp.status_code == 200, reset_resp.text

            old_login = client.post("/auth/login", json={"email": "frank@example.com", "password": "originalpass1"})
            assert old_login.status_code == 401

            new_login = client.post("/auth/login", json={"email": "frank@example.com", "password": "newpassword2"})
            assert new_login.status_code == 200

            # reusing the SAME token a second time must fail - the single-use proof, now at the HTTP layer
            reuse_resp = client.post("/auth/reset-password", json={"token": token, "new_password": "thirdpassword3"})
            assert reuse_resp.status_code == 400, reuse_resp.text

            # a genuinely nonexistent email gets the identical generic response (already covered
            # by test_forgot_password_and_resend_verification_are_enumeration_safe in Task 6, not
            # re-asserted here to avoid duplicating that test's exact purpose)


def test_async_mode_auth_expansion_full_stack_round_trip(tmp_path, monkeypatch, isolated_sys_path, capfd):
    """auth_expansion_async_full.yml driven through real HTTP + a real aiosqlite
    DB - proves admin_approval gating, admin endpoints, and forgot/reset
    password all compose correctly through the full async stack, mirroring
    what the sync-path tests in Tasks 6-7 already proved individually.
    """
    erd = load_erd(f"{FIXTURES}/auth_expansion_async_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "auth_expansion_async_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-do-not-use-in-production")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import re

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            admin_resp = client.post("/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
            assert admin_resp.status_code == 201, admin_resp.text
            # bootstrap (first-user) admin is auto-approved, symmetric with the existing
            # roles bootstrap, so it can log in directly with no SQL workaround
            assert admin_resp.json()["is_approved"] is True
            admin_id = admin_resp.json()["id"]

            admin_login = client.post("/auth/login", json={"email": "admin@example.com", "password": "supersecret123"})
            assert admin_login.status_code == 200, admin_login.text
            admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

            # admin_approval flow
            pending_resp = client.post("/auth/register", json={"email": "pending@example.com", "password": "supersecret123"})
            pending_id = pending_resp.json()["id"]
            assert client.post("/auth/login", json={"email": "pending@example.com", "password": "supersecret123"}).status_code == 401

            # DEVIATION FROM BRIEF (documented per the Task-6/Task-7 precedent - see
            # test_admin_user_management_403_then_200_round_trip and
            # test_full_admin_approval_flow_over_http above, which independently found
            # and fixed the identical issue): the admin routes live on the same
            # `router = APIRouter()` as /register, /login, /me in auth/routes.py.jinja,
            # and server.py.jinja mounts that whole router under the /auth prefix - so
            # these routes are only ever reachable as /auth/users/{id}/approve and
            # /auth/users in a real generated app, never bare /users/... . Prefixed
            # both call sites with /auth to match real generated behavior (brief's
            # literal text has the bare paths).
            approve_resp = client.post(f"/auth/users/{pending_id}/approve", headers=admin_headers)
            assert approve_resp.status_code == 200, approve_resp.text

            assert client.post("/auth/login", json={"email": "pending@example.com", "password": "supersecret123"}).status_code == 200

            # admin endpoints
            list_resp = client.get("/auth/users", headers=admin_headers)
            assert list_resp.status_code == 200
            assert {u["id"] for u in list_resp.json()} >= {admin_id, pending_id}

            # forgot/reset password
            forgot_resp = client.post("/auth/forgot-password", json={"email": "pending@example.com"})
            assert forgot_resp.status_code == 200
            captured = capfd.readouterr()
            match = re.search(r"Your password reset token: (\S+)", captured.out)
            assert match
            token = match.group(1)
            reset_resp = client.post("/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"})
            assert reset_resp.status_code == 200, reset_resp.text
            assert client.post("/auth/login", json={"email": "pending@example.com", "password": "brandnewpass1"}).status_code == 200

    # `with TestClient(...)` has already exited here, running the async lifespan
    # shutdown (await engine.dispose()) - reaching this line without a hang is
    # itself part of what this test proves, per the established precedent from
    # the async-support and RLS plans.


def test_free_text_project_fields_with_quotes_backslashes_and_unicode_generate_and_byte_compile(tmp_path):
    """Regression test for the free-text-ERD-field escaping bug fixed by this task:
    `project.name`, `project.description`, and a `ModelField.default` used to be
    embedded unescaped into generated Python source (`title="{{ project.name }}"`,
    a raw f"'{value}'" for field defaults, etc.), so any value containing a `"`
    (or, for a field default, a `'`) broke the generated project outright with a
    SyntaxError. quote_stress.yml's project.name/description each carry a literal
    `"`, a backslash `\\`, and a non-ASCII character; Item.label's default carries
    a literal `'`.

    Generation is driven via `CodeGenerator._generate_fastapi_project(...)`
    directly, passing an already-created safe `tmp_path` subdirectory as the
    output directory, rather than the public `generate_project()` - which
    computes its output directory as `self.output_dir / project_state['name']`,
    i.e. the very same unsanitized free-text value under test. `"` is also an
    illegal NTFS/Windows filename character, so a project.name containing one
    makes `generate_project()` raise `OSError` (WinError 123) at the directory-
    creation step, before any template is even rendered. That is a real, but
    separate and pre-existing, bug (unsanitized free text used as a filesystem
    path segment - not free text embedded in generated Python source) which is
    out of this task's template-escaping scope; see the task report. Calling
    `_generate_fastapi_project` directly exercises exactly the template
    rendering this test needs to cover without tripping that unrelated bug.
    """
    erd = load_erd(f"{FIXTURES}/quote_stress.yml")
    state = translate(erd)

    # Sanity: the fixture actually carries the dangerous characters under test.
    assert '"' in state["name"] and "\\" in state["name"] and "café" in state["name"]
    assert '"' in state["description"] and "\\" in state["description"]
    label_field = state["data_models"][0]["fields"][1]
    assert label_field["name"] == "label"
    assert label_field["default"] == "O'Brien's"

    generator = CodeGenerator(output_dir=str(tmp_path / "workspace"))
    codebase_dir = tmp_path / "codebase"
    codebase_dir.mkdir()
    generator._generate_fastapi_project(state, codebase_dir)

    # 1. Every generated .py file must byte-compile - this is what used to raise
    # SyntaxError (or worse, silently produce a project that imports with a
    # semantically wrong string) before the fix.
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(codebase_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    # 2. server.py: title=/description=/"name": must parse AND round-trip the
    # original quote/backslash/unicode content exactly - not just "doesn't crash".
    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(server_src)  # would raise SyntaxError before the fix

    title_line = next(l for l in server_src.splitlines() if l.strip().startswith("title="))
    title_value = ast.literal_eval(title_line.strip()[len("title="):].rstrip(","))
    assert title_value == state["name"]

    description_line = next(
        l for l in server_src.splitlines() if l.strip().startswith("description=")
    )
    description_value = ast.literal_eval(
        description_line.strip()[len("description="):].rstrip(",")
    )
    assert description_value == state["description"]

    name_field_line = next(l for l in server_src.splitlines() if l.strip().startswith('"name":'))
    name_field_value = ast.literal_eval(name_field_line.strip()[len('"name":'):].rstrip(",").strip())
    assert name_field_value == state["name"]

    # Module docstring (the |replace('"', '\\"') fix): the raw name is still
    # fully recoverable, not stripped or mangled.
    docstring = ast.get_docstring(tree)
    assert docstring == f"{state['name']} - Main server application"

    # 3. config.py: APP_NAME and the DATABASE_URL default must also round-trip.
    config_src = (codebase_dir / "config.py").read_text(encoding="utf-8")
    ast.parse(config_src)
    app_name_line = next(l for l in config_src.splitlines() if l.strip().startswith("APP_NAME:"))
    app_name_value = ast.literal_eval(app_name_line.split("=", 1)[1].strip())
    assert app_name_value == state["name"]

    # 4. database/models.py: the ModelField.default containing a literal `'` must
    # render via repr() (which picks the non-colliding quote character), not the
    # old unescaped f"'{value}'".
    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    ast.parse(models_src)
    assert "default=\"O'Brien's\"" in models_src
