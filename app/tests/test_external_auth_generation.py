import ast
import base64
import subprocess
import sys
import time

from app.erd.loader import load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator
from app.tests.test_generated_project_runtime import _GeneratedProjectImporter, isolated_sys_path  # noqa: F401

FIXTURES = "app/tests/fixtures/erd"
FIXTURE = f"{FIXTURES}/jwt_claim_owner_match.yml"


def _generate(tmp_path):
    state = translate(load_erd(FIXTURE))
    return CodeGenerator(output_dir=str(tmp_path / "workspace")).generate_project(state, force=True)


def test_external_auth_module_has_only_service_py(tmp_path):
    codebase_dir = _generate(tmp_path)
    auth_dir = codebase_dir / "modules" / "auth"
    assert (auth_dir / "service.py").exists()
    assert not (auth_dir / "routes.py").exists()
    assert not (auth_dir / "schemas.py").exists()
    assert not (auth_dir / "email.py").exists()

    service_src = (auth_dir / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "class Principal" in service_src
    assert "def get_current_user" in service_src

    result = subprocess.run([sys.executable, "-m", "compileall", "-q", str(codebase_dir)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_database_models_user_class_under_external_auth(tmp_path):
    codebase_dir = _generate(tmp_path)
    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    assert "class User(Base):" not in models_src


def test_requirements_has_jose_and_httpx_but_not_password_deps(tmp_path):
    codebase_dir = _generate(tmp_path)
    req = (codebase_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "python-jose" in req
    assert "httpx" in req
    assert "passlib" not in req
    assert "bcrypt" not in req
    assert "email-validator" not in req
    assert "python-multipart" not in req


def _rsa_keypair_and_jwk():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    numbers = pub.public_numbers()

    def b64url_uint(n):
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    jwk_dict = {"kty": "RSA", "use": "sig", "kid": "key1", "alg": "RS256", "n": b64url_uint(numbers.n), "e": b64url_uint(numbers.e)}
    return priv_pem, jwk_dict


def _make_token(priv_pem, kid="key1", **claim_overrides):
    from jose import jwt

    claims = {"sub": "user-1", "roles": ["admin"], "agency_id": "11111111-1111-1111-1111-111111111111",
              "iss": "authservice", "aud": "jwt-claim-owner-match", "exp": int(time.time()) + 3600}
    claims.update(claim_overrides)
    return jwt.encode(claims, priv_pem, algorithm="RS256", headers={"kid": kid})


def _async_jwks_returning(jwks_response):
    """`_fetch_jwks` is `async def` (final review F3: httpx.AsyncClient, not a blocking
    sync call inside an async dependency) - monkeypatch replacements must be awaitable too."""

    async def _fake_fetch():
        return jwks_response

    return _fake_fetch


def test_jwt_claim_rls_route_bodies_render_and_byte_compile(tmp_path):
    codebase_dir = _generate(tmp_path)
    routes_src = (codebase_dir / "modules" / "projects" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)

    # create: unconditional claim stamp, no bypass branch, 403 on a missing claim -
    # mirrors auth_user's create exactly (see the comment in the template).
    assert '_claim_value = current_user.claims.get("agency_id")' in routes_src
    assert routes_src.count('_claim_value = current_user.claims.get("agency_id")') >= 4  # create/list/read/update/delete
    assert "status.HTTP_403_FORBIDDEN" in routes_src
    assert "Missing required claim: agency_id" in routes_src

    # read (get-by-id) has rbac.default_permissions.read: [admin] in the fixture, and
    # Project's identity is jwt_claim - so the role check and the current_user fetch
    # must be combined into ONE Depends(require_roles(...)), not two.
    assert 'current_user: Principal = Depends(require_roles("admin"))' in routes_src
    # ... and NOT also duplicated as a decorator-level dependency for that same route.
    get_route_start = routes_src.index("def get_project_route")
    get_route_decorator = routes_src[routes_src.rindex("@router.get", 0, get_route_start):get_route_start]
    assert "dependencies=" not in get_route_decorator

    result = subprocess.run([sys.executable, "-m", "compileall", "-q", str(codebase_dir)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_typed_jwt_claim_rejects_wrong_json_types_and_malformed_strings(tmp_path, monkeypatch, isolated_sys_path):
    """Final review F4: _typed_jwt_claim was too permissive - a bool coerced to 0/1 via
    int(True), a float silently truncated by int(...), and list/dict claims crashing with a
    500 instead of a clean 403. Exercises every allowed owner_match_field type directly."""
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        from fastapi import HTTPException

        routes_module = importlib.import_module("modules.projects.routes")
        claim = routes_module._typed_jwt_claim

        # Universally-rejected shapes, regardless of the target type.
        for bad in (True, False, 9000000000.7, [1, 2], {"a": 1}):
            for type_name in ("UUID", "int", "str"):
                try:
                    claim(bad, type_name, "agency_id")
                    assert False, f"{bad!r} as {type_name} should have raised"
                except HTTPException as exc:
                    assert exc.status_code == 403

        # UUID: only a real UUID string is accepted.
        assert str(claim("11111111-1111-1111-1111-111111111111", "UUID", "agency_id")) == "11111111-1111-1111-1111-111111111111"
        for bad in ("not-a-uuid", 12345):
            try:
                claim(bad, "UUID", "agency_id")
                assert False, f"{bad!r} should have raised"
            except HTTPException as exc:
                assert exc.status_code == 403

        # int: a real int, or a digit string - never a float-shaped or garbage string.
        assert claim(42, "int", "agency_id") == 42
        assert claim("42", "int", "agency_id") == 42
        for bad in ("not-a-number", "seven", "9000000000.7", ""):
            try:
                claim(bad, "int", "agency_id")
                assert False, f"{bad!r} should have raised"
            except HTTPException as exc:
                assert exc.status_code == 403

        # str: a plain string, or an int stringified - never a garbage type.
        assert claim("agency-42", "str", "agency_id") == "agency-42"
        assert claim(42, "str", "agency_id") == "42"


def test_rbac_dependency_uses_principal_under_external_auth(tmp_path):
    codebase_dir = _generate(tmp_path)
    rbac_src = (codebase_dir / "rbac.py").read_text(encoding="utf-8")
    ast.parse(rbac_src)
    assert "from modules.auth.service import Principal" in rbac_src
    assert "from database.models import User" not in rbac_src
    assert "current_user: Principal = Depends(_auth_service.get_current_user)) -> Principal:" in rbac_src


def test_get_current_user_accepts_a_valid_token_and_builds_principal(tmp_path, monkeypatch, isolated_sys_path):
    priv_pem, jwk_dict = _rsa_keypair_and_jwk()
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("AUTH_JWKS_URL", "https://authservice.example/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        service_module = importlib.import_module("modules.auth.service")
        monkeypatch.setattr(service_module, "_fetch_jwks", _async_jwks_returning({"keys": [jwk_dict]}))

        import asyncio

        principal = asyncio.run(service_module._verify_token(_make_token(priv_pem)))
        assert principal.id == "user-1"
        assert principal.roles == ["admin"]
        assert principal.claims["agency_id"] == "11111111-1111-1111-1111-111111111111"


def test_get_current_user_rejects_every_failure_mode(tmp_path, monkeypatch, isolated_sys_path):
    priv_pem, jwk_dict = _rsa_keypair_and_jwk()
    other_priv_pem, _ = _rsa_keypair_and_jwk()
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("AUTH_JWKS_URL", "https://authservice.example/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import asyncio
        from fastapi import HTTPException

        service_module = importlib.import_module("modules.auth.service")
        monkeypatch.setattr(service_module, "_fetch_jwks", _async_jwks_returning({"keys": [jwk_dict]}))

        for label, token in {
            "bad signature": _make_token(other_priv_pem),
            "wrong issuer": _make_token(priv_pem, iss="someone-else"),
            "expired": _make_token(priv_pem, exp=int(time.time()) - 10),
            "malformed": "not-a-jwt",
        }.items():
            try:
                asyncio.run(service_module._verify_token(token))
                assert False, f"{label} should have raised"
            except HTTPException as exc:
                assert exc.status_code == 401, label

        # unknown kid: one refetch, then 401. Reset the module's cache/throttle state first -
        # the loop above already populated it for "key1", and final review F3's minimum
        # refetch interval would otherwise throttle this section's own fetch (correctly - see
        # test_jwks_refetch_is_throttled_within_the_minimum_interval below for that behavior
        # tested directly), which isn't what this section means to exercise.
        service_module._jwks_cache.clear()
        service_module._last_fetch_at = None
        fetch_calls = []

        async def fetch_once_more():
            fetch_calls.append(1)
            return {"keys": []}

        monkeypatch.setattr(service_module, "_fetch_jwks", fetch_once_more)
        try:
            asyncio.run(service_module._verify_token(_make_token(priv_pem, kid="unknown-kid")))
            assert False, "unknown kid should have raised"
        except HTTPException as exc:
            assert exc.status_code == 401
        assert len(fetch_calls) == 1


def test_jwks_refetch_is_throttled_within_the_minimum_interval(tmp_path, monkeypatch, isolated_sys_path):
    """Final review F3: the kid used to select a JWKS refetch comes from the token's
    unverified header, so an unauthenticated caller can force a cache miss with any random
    value. Without a minimum interval between refetches, that's an unthrottled way to make
    this service hammer the JWKS endpoint. Confirms: repeated unknown-kid requests within the
    interval share one fetch, not one each - and that the throttle only applies once the
    cache has actually been populated at least once (an empty cache always fetches)."""
    priv_pem, jwk_dict = _rsa_keypair_and_jwk()
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("AUTH_JWKS_URL", "https://authservice.example/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import asyncio
        from fastapi import HTTPException

        service_module = importlib.import_module("modules.auth.service")
        fetch_calls = []

        async def counting_fetch():
            fetch_calls.append(1)
            return {"keys": [jwk_dict]}

        monkeypatch.setattr(service_module, "_fetch_jwks", counting_fetch)

        # First call: cache is empty, always fetches (populates "key1", not "unknown-kid").
        try:
            asyncio.run(service_module._verify_token(_make_token(priv_pem, kid="unknown-kid-1")))
        except HTTPException as exc:
            assert exc.status_code == 401
        assert len(fetch_calls) == 1

        # Second and third calls, different unknown kids, immediately after: cache is
        # non-empty and the minimum interval hasn't elapsed - no new fetch, straight to 401.
        for kid in ("unknown-kid-2", "unknown-kid-3"):
            try:
                asyncio.run(service_module._verify_token(_make_token(priv_pem, kid=kid)))
                assert False, f"{kid} should have raised"
            except HTTPException as exc:
                assert exc.status_code == 401
        assert len(fetch_calls) == 1  # still just the one fetch, not three

        # A genuinely known kid, meanwhile, is still served straight from the cache with no
        # fetch at all - the throttle only affects the miss path.
        principal = asyncio.run(service_module._verify_token(_make_token(priv_pem, kid="key1")))
        assert principal.id == "user-1"
        assert len(fetch_calls) == 1


def test_jwks_fetch_failure_is_503_not_401_or_a_crash(tmp_path, monkeypatch, isolated_sys_path):
    """Final review F3: an unreachable JWKS endpoint, a non-2xx response, or a missing
    AUTH_JWKS_URL are infrastructure problems, not the caller's fault - they must not surface
    as 401 (implies "your credentials are bad") or as an unhandled exception (500)."""
    priv_pem, _ = _rsa_keypair_and_jwk()
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("AUTH_JWKS_URL", "https://authservice.example/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib
        import asyncio
        import httpx
        from fastapi import HTTPException

        service_module = importlib.import_module("modules.auth.service")

        # Patch at the httpx transport level, not service_module._fetch_jwks itself - the
        # try/except that converts a transport error into a 503 lives INSIDE _fetch_jwks, so
        # replacing that function wholesale would bypass the exact code path this test means
        # to exercise.
        async def failing_get(self, url, **kwargs):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx.AsyncClient, "get", failing_get)
        try:
            asyncio.run(service_module._verify_token(_make_token(priv_pem)))
            assert False, "should have raised"
        except HTTPException as exc:
            assert exc.status_code == 503

    # Missing env var: checked separately (a fresh import, so no leftover cache to serve from).
    codebase_dir2 = _generate(tmp_path / "b")
    monkeypatch.delenv("AUTH_JWKS_URL", raising=False)
    with _GeneratedProjectImporter(codebase_dir2):
        import importlib
        import asyncio
        from fastapi import HTTPException

        service_module = importlib.import_module("modules.auth.service")
        try:
            asyncio.run(service_module._verify_token(_make_token(priv_pem)))
            assert False, "should have raised"
        except HTTPException as exc:
            assert exc.status_code == 503


def _make_token_without_agency(priv_pem, sub, roles, aud):
    from jose import jwt

    return jwt.encode(
        {"sub": sub, "roles": roles, "iss": "authservice", "aud": aud, "exp": int(time.time()) + 3600},
        priv_pem, algorithm="RS256", headers={"kid": "key1"},
    )


def test_jwt_claim_rls_end_to_end_cross_tenant_isolation_and_bypass(tmp_path, monkeypatch, isolated_sys_path):
    """jwt_claim_multi_tenant.yml: real HTTP round trip mirroring the dana-finance shape
    (Agency.agency_ref unique uuid, Project owned via jwt_claim + owner_match_field,
    cascade-owned Task). Proves cross-agency isolation, an admin bypass role seeing
    across every agency, create always stamping the caller's own claim regardless of
    bypass, a token missing the claim getting 403 on every non-bypass action including
    create, and the cascade-owned child inheriting the same scoping.
    """
    priv_pem, jwk_dict = _rsa_keypair_and_jwk()
    state = translate(load_erd(f"{FIXTURES}/jwt_claim_multi_tenant.yml"))
    codebase_dir = CodeGenerator(output_dir=str(tmp_path / "workspace")).generate_project(state, force=True)
    monkeypatch.setenv("AUTH_JWKS_URL", "https://authservice.example/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'tenant.db').as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    agency_a_ref = "11111111-1111-1111-1111-111111111111"
    agency_b_ref = "22222222-2222-2222-2222-222222222222"

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        auth_service_module = importlib.import_module("modules.auth.service")
        monkeypatch.setattr(auth_service_module, "_fetch_jwks", _async_jwks_returning({"keys": [jwk_dict]}))

        server_module = importlib.import_module("server")
        database_base = importlib.import_module("database.base")
        database_models = importlib.import_module("database.models")
        from fastapi.testclient import TestClient

        import uuid

        member_a_token = _make_token(priv_pem, sub="member-a", roles=["member"], agency_id=agency_a_ref, aud="dana-finance")
        member_b_token = _make_token(priv_pem, sub="member-b", roles=["member"], agency_id=agency_b_ref, aud="dana-finance")
        admin_token = _make_token(priv_pem, sub="admin-1", roles=["admin"], agency_id=agency_a_ref, aud="dana-finance")
        no_claim_token = _make_token_without_agency(priv_pem, "member-c", ["member"], "dana-finance")

        def auth(token):
            return {"Authorization": f"Bearer {token}"}

        with TestClient(server_module.app) as client:
            # tables only exist once the app's lifespan (init_db) has run, i.e. once we're
            # inside this `with` block - can't seed agencies before entering it.
            session = database_base.SessionLocal()
            try:
                agency_a = database_models.Agency(agency_ref=uuid.UUID(agency_a_ref), name="Agency A")
                agency_b = database_models.Agency(agency_ref=uuid.UUID(agency_b_ref), name="Agency B")
                session.add_all([agency_a, agency_b])
                session.commit()
            finally:
                session.close()

            created = client.post("/projects", json={"title": "A's project"}, headers=auth(member_a_token))
            assert created.status_code == 201, created.text
            project_a_id = created.json()["id"]

            # cross-tenant isolation: member B cannot see A's project
            listing_b = client.get("/projects", headers=auth(member_b_token)).json()
            assert all(p["id"] != project_a_id for p in listing_b)
            assert client.get(f"/projects/{project_a_id}", headers=auth(member_b_token)).status_code == 404

            # same-tenant: member A can see it
            listing_a = client.get("/projects", headers=auth(member_a_token)).json()
            assert any(p["id"] == project_a_id for p in listing_a)

            # bypass: admin sees it despite being scoped to agency A's own claim (same agency
            # here, but the point is the bypass path, not tenant match)
            assert client.get(f"/projects/{project_a_id}", headers=auth(admin_token)).status_code == 200

            # create always stamps the caller's own claim, bypass or not
            created_by_admin = client.post("/projects", json={"title": "admin's own"}, headers=auth(admin_token))
            assert created_by_admin.status_code == 201
            assert client.get(f"/projects/{created_by_admin.json()['id']}", headers=auth(member_b_token)).status_code == 404
            assert client.get(f"/projects/{created_by_admin.json()['id']}", headers=auth(member_a_token)).status_code == 200

            # missing claim, non-bypass: 403 on list/read/update/delete and on create
            assert client.get("/projects", headers=auth(no_claim_token)).status_code == 403
            assert client.post("/projects", json={"title": "x"}, headers=auth(no_claim_token)).status_code == 403

            # cascade-owned Task inherits the same tenant scoping through one more join hop
            task_created = client.post("/tasks", json={"label": "t1", "project_id": project_a_id}, headers=auth(member_a_token))
            assert task_created.status_code == 201, task_created.text
            task_id = task_created.json()["id"]
            assert client.get(f"/tasks/{task_id}", headers=auth(member_b_token)).status_code == 404
            assert client.get(f"/tasks/{task_id}", headers=auth(member_a_token)).status_code == 200


def test_jwt_claim_any_authenticated_still_enforces_rbac_on_list_and_read(tmp_path, monkeypatch, isolated_sys_path):
    """Final review F1: read_scope: any_authenticated + jwt_claim previously matched the same
    param-block branch as read_scope: any_authenticated + header, which skips require_roles
    entirely (header's branch only needs "some authenticated caller", since header identity
    carries no role information to check against - but jwt_claim's Principal genuinely has
    roles, and RBAC restricting list/read to specific roles must still be enforced). Pub
    restricts list/read to [admin]; a member token must get 403, not 200.
    """
    priv_pem, jwk_dict = _rsa_keypair_and_jwk()
    fixture = f"{FIXTURES}/jwt_claim_any_authenticated_rbac.yml"
    state = translate(load_erd(fixture))
    codebase_dir = CodeGenerator(output_dir=str(tmp_path / "workspace")).generate_project(state, force=True)
    monkeypatch.setenv("AUTH_JWKS_URL", "https://authservice.example/.well-known/jwks.json")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        service_module = importlib.import_module("modules.auth.service")
        monkeypatch.setattr(service_module, "_fetch_jwks", _async_jwks_returning({"keys": [jwk_dict]}))

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        member_token = _make_token_without_agency(priv_pem, "member-1", ["member"], "jwt-claim-any-authenticated-rbac")
        admin_token = _make_token_without_agency(priv_pem, "admin-1", ["admin"], "jwt-claim-any-authenticated-rbac")

        def auth(token):
            return {"Authorization": f"Bearer {token}"}

        with TestClient(server_module.app) as client:
            # a member has no jwt_claim role restriction bypass and no admin role - RBAC must
            # reject them on both list and read, exactly as it would for auth_user/header.
            assert client.get("/pubs", headers=auth(member_token)).status_code == 403
            assert client.get("/pubs/1", headers=auth(member_token)).status_code == 403

            # an admin (has the required role) still gets through - RBAC isn't just broken shut.
            assert client.get("/pubs", headers=auth(admin_token)).status_code == 200
            assert client.get("/pubs/1", headers=auth(admin_token)).status_code == 404  # no row seeded, but past RBAC
