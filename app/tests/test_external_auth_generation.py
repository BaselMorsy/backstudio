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
        monkeypatch.setattr(service_module, "_fetch_jwks", lambda: {"keys": [jwk_dict]})

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
        monkeypatch.setattr(service_module, "_fetch_jwks", lambda: {"keys": [jwk_dict]})

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

        # unknown kid: one refetch, then 401
        fetch_calls = []

        def fetch_once_more():
            fetch_calls.append(1)
            return {"keys": []}

        monkeypatch.setattr(service_module, "_fetch_jwks", fetch_once_more)
        try:
            asyncio.run(service_module._verify_token(_make_token(priv_pem, kid="unknown-kid")))
            assert False, "unknown kid should have raised"
        except HTTPException as exc:
            assert exc.status_code == 401
        assert len(fetch_calls) == 1
