import asyncio
import importlib

import pytest
import yaml
from fastapi import HTTPException

from app.erd.loader import ERDValidationError, load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator
from app.tests.test_generated_project_runtime import _GeneratedProjectImporter, isolated_sys_path  # noqa: F401

FIXTURES = "app/tests/fixtures/erd"
NAME_FIELD = [{"name": "name", "type": "string", "nullable": True}]


def _erd_text(*, jwt_claims=None, user_fields=None, registration="open", external_claims=None):
    doc = {
        "project": {"name": "ClaimsDemo"},
        "database": {"type": "sqlite", "database_name": "claims.db"},
        "auth": {"enabled": True},
        "entities": [{"name": "Widget", "fields": [{"name": "id", "type": "integer", "primary_key": True}]}],
        "services": [{"name": "widgets", "entities": ["Widget"]}],
    }
    if external_claims is not None:
        doc["auth"].update(
            {
                "mode": "external",
                "external": {
                    "verification": "shared_secret",
                    "secret_env_var": "SHARED_SECRET",
                    "issuer": "authservice",
                    "algorithms": ["HS256"],
                    "claims": external_claims,
                },
            }
        )
    else:
        doc["auth"]["registration"] = {"mode": registration}
        if jwt_claims is not None:
            doc["auth"]["jwt"] = {"claims": jwt_claims}
        if user_fields:
            doc["entities"].append({"name": "User", "fields": user_fields})
    return yaml.safe_dump(doc)


def _load(tmp_path, **kwargs):
    path = tmp_path / "erd.yml"
    path.write_text(_erd_text(**kwargs), encoding="utf-8")
    return load_erd(path)


# --- validation (acceptance 4) ---------------------------------------------------------------


@pytest.mark.parametrize("claim", ["sub", "exp", "iat", "nbf", "type", "roles", "iss", "aud", "jti", "pwd_fp"])
def test_reserved_claim_names_are_rejected(tmp_path, claim):
    with pytest.raises(ERDValidationError, match="reserved token claim"):
        _load(tmp_path, jwt_claims={claim: "email"})


def test_unknown_user_field_is_rejected(tmp_path):
    with pytest.raises(ERDValidationError, match="no field 'nickname'"):
        _load(tmp_path, jwt_claims={"nick": "nickname"})


def test_password_hash_is_rejected(tmp_path):
    with pytest.raises(ERDValidationError, match="password_hash"):
        _load(tmp_path, jwt_claims={"secret": "password_hash"})


@pytest.mark.parametrize("field", ["created_at", "roles"])
def test_field_types_without_a_token_encoding_are_rejected(tmp_path, field):
    with pytest.raises(ERDValidationError, match="no unambiguous token encoding"):
        _load(tmp_path, jwt_claims={"x": field})


def test_mode_gated_field_is_only_available_in_its_mode(tmp_path):
    _load(tmp_path, jwt_claims={"verified": "is_verified"}, registration="email_verification")
    with pytest.raises(ERDValidationError, match="no field 'is_verified'"):
        _load(tmp_path, jwt_claims={"verified": "is_verified"}, registration="open")


def test_builtin_and_custom_fields_are_accepted(tmp_path):
    erd = _load(tmp_path, jwt_claims={"email": "email", "name": "name"}, user_fields=NAME_FIELD)
    assert erd.auth.jwt.claims == {"email": "email", "name": "name"}


def test_jwt_claims_are_rejected_under_external_mode(tmp_path):
    path = tmp_path / "erd.yml"
    doc = yaml.safe_load(_erd_text(external_claims={}))
    doc["auth"]["jwt"] = {"claims": {"email": "email"}}
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ERDValidationError, match="external"):
        load_erd(path)


@pytest.mark.parametrize("name", ["id", "claims", "not valid", "class"])
def test_external_attribute_names_must_be_usable(tmp_path, name):
    with pytest.raises(ERDValidationError):
        _load(tmp_path, external_claims={name: "email"})


# --- generation is unchanged without claims -------------------------------------------------


def test_no_claims_means_no_claim_code(tmp_path):
    erd = load_erd(f"{FIXTURES}/builtin_shared_secret_issuer.yml")
    codebase = CodeGenerator(output_dir=str(tmp_path / "w")).generate_project(translate(erd), force=True)
    auth = codebase / "modules" / "auth"
    assert "user_claims" not in (auth / "service.py").read_text(encoding="utf-8")
    assert "claims=" not in (auth / "routes.py").read_text(encoding="utf-8")


# --- issuer runtime (acceptance 1, 2, 3, 5) --------------------------------------------------


def test_issued_access_tokens_carry_the_mapped_claims_and_refresh_reads_current_values(
    tmp_path, monkeypatch, isolated_sys_path
):
    erd = _load(tmp_path, jwt_claims={"email": "email", "name": "name"}, user_fields=NAME_FIELD)
    codebase = CodeGenerator(output_dir=str(tmp_path / "w")).generate_project(translate(erd), force=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret")

    with _GeneratedProjectImporter(codebase):
        from fastapi.testclient import TestClient
        from jose import jwt as jose_jwt

        server = importlib.import_module("server")
        base = importlib.import_module("database.base")
        models = importlib.import_module("database.models")

        def decode(token):
            return jose_jwt.decode(token, "test-only-secret", algorithms=["HS256"], options={"verify_aud": False})

        with TestClient(server.app) as client:
            creds = {"email": "alice@acme.com", "password": "supersecret123"}
            assert client.post("/auth/register", json=creds).status_code == 201
            tokens = client.post("/auth/login", json=creds).json()
            access = decode(tokens["access_token"])

            # name is still NULL: one rule - a null field leaves the claim out (acceptance 5)
            assert access["email"] == "alice@acme.com"
            assert "name" not in access
            assert {"sub", "exp", "type", "roles"} <= access.keys()

            # only access tokens carry the extra claims (acceptance 3)
            refresh = decode(tokens["refresh_token"])
            assert "email" not in refresh and "name" not in refresh

            db = base.SessionLocal()
            try:
                user = db.query(models.User).filter_by(email="alice@acme.com").one()
                user.name = "Alice A."
                db.commit()
            finally:
                db.close()

            refreshed = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
            assert decode(refreshed["access_token"])["name"] == "Alice A."  # current value (acceptance 2)
            assert "name" not in decode(refreshed["refresh_token"])


# --- verifier (acceptance 6) -----------------------------------------------------------------


def _verifier_codebase(tmp_path, external_claims):
    erd = _load(tmp_path, external_claims=external_claims)
    return CodeGenerator(output_dir=str(tmp_path / "w")).generate_project(translate(erd), force=True)


def _principal_for(token_claims, monkeypatch):
    from jose import jwt as jose_jwt

    monkeypatch.setenv("SHARED_SECRET", "test-only-shared-secret")
    service = importlib.import_module("modules.auth.service")
    token = jose_jwt.encode({"sub": "u1", "iss": "authservice", **token_claims}, "test-only-shared-secret", "HS256")
    return asyncio.run(service._verify_token(token))


def test_verifier_exposes_mapped_claims_as_principal_attributes(tmp_path, monkeypatch, isolated_sys_path):
    codebase = _verifier_codebase(
        tmp_path, {"email": "email", "display_name": {"claim": "name"}, "tenant": {"claim": "tid"}}
    )
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")
    with _GeneratedProjectImporter(codebase):
        principal = _principal_for({"email": "alice@acme.com", "name": "Alice"}, monkeypatch)
        assert principal.email == "alice@acme.com"
        assert principal.display_name == "Alice"
        assert principal.tenant is None  # absent claim: None, not a 401 (acceptance 6)
        assert principal.claims["email"] == "alice@acme.com"


def test_verifier_rejects_a_token_missing_a_required_claim(tmp_path, monkeypatch, isolated_sys_path):
    codebase = _verifier_codebase(tmp_path, {"email": {"claim": "email", "required": True}})
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'db.db').as_posix()}")
    with _GeneratedProjectImporter(codebase):
        assert _principal_for({"email": "a@b.co"}, monkeypatch).email == "a@b.co"
        with pytest.raises(HTTPException) as exc:
            _principal_for({}, monkeypatch)
        assert exc.value.status_code == 401
        assert "email" in exc.value.detail
