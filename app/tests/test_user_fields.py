import importlib
import re

import pytest
import yaml

from app.erd.loader import ERDValidationError, load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator
from app.tests.test_generated_project_runtime import _GeneratedProjectImporter, isolated_sys_path  # noqa: F401

FIXTURE = "app/tests/fixtures/erd/builtin_user_fields.yml"
ASYNC_FIXTURE = "app/tests/fixtures/erd/builtin_user_fields_async.yml"
CREDS = {"email": "alice@acme.com", "password": "supersecret123"}


def _erd_with_user_fields(tmp_path, user_fields, extra_entity_field=None):
    doc = yaml.safe_load(open(FIXTURE, encoding="utf-8"))
    doc["auth"]["jwt"].pop("claims", None)
    for entity in doc["entities"]:
        if entity["name"] == "User":
            entity["fields"] = user_fields
        if entity["name"] == "Widget" and extra_entity_field:
            entity["fields"].append(extra_entity_field)
    path = tmp_path / "erd.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


# --- validation -------------------------------------------------------------------------------


def test_internal_field_without_default_or_nullable_is_rejected(tmp_path):
    path = _erd_with_user_fields(
        tmp_path, [{"name": "plan", "type": "string", "nullable": False, "self_service": False}]
    )
    with pytest.raises(ERDValidationError, match="self_service: false"):
        load_erd(path)


def test_internal_field_with_default_or_nullable_is_accepted(tmp_path):
    load_erd(
        _erd_with_user_fields(
            tmp_path,
            [
                {"name": "plan", "type": "string", "nullable": False, "default": "free", "self_service": False},
                {"name": "note", "type": "string", "nullable": True, "self_service": False},
            ],
        )
    )


def test_self_service_on_a_non_user_entity_is_rejected(tmp_path):
    path = _erd_with_user_fields(
        tmp_path, [{"name": "name", "type": "string"}], {"name": "label2", "type": "string", "self_service": False}
    )
    with pytest.raises(ERDValidationError, match="only applies to fields of the auth 'User' entity"):
        load_erd(path)


def test_declared_field_colliding_with_a_reserved_one_is_still_rejected(tmp_path):
    path = _erd_with_user_fields(tmp_path, [{"name": "roles", "type": "string"}])
    with pytest.raises(ERDValidationError, match="collide"):
        load_erd(path)


# --- no declared fields: nothing new is generated ------------------------------------------


def test_no_declared_user_fields_means_no_profile_code(tmp_path):
    erd = load_erd("app/tests/fixtures/erd/builtin_invite.yml")
    codebase = CodeGenerator(output_dir=str(tmp_path / "w")).generate_project(translate(erd), force=True)
    auth = codebase / "modules" / "auth"
    assert "profile" not in (auth / "service.py").read_text(encoding="utf-8")
    assert "UpdateProfileRequest" not in (auth / "schemas.py").read_text(encoding="utf-8")
    assert '"/me"' in (auth / "routes.py").read_text(encoding="utf-8")
    assert "patch" not in (auth / "routes.py").read_text(encoding="utf-8")


# --- runtime ----------------------------------------------------------------------------------


@pytest.fixture(params=["sync", "async"])
def app_client(request, tmp_path, monkeypatch, isolated_sys_path):
    fixture, scheme = (FIXTURE, "sqlite") if request.param == "sync" else (ASYNC_FIXTURE, "sqlite+aiosqlite")
    codebase = CodeGenerator(output_dir=str(tmp_path / "w")).generate_project(translate(load_erd(fixture)), force=True)
    monkeypatch.setenv("DATABASE_URL", f"{scheme}:///{(tmp_path / 'db.db').as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret")
    with _GeneratedProjectImporter(codebase):
        from fastapi.testclient import TestClient
        from jose import jwt as jose_jwt

        server = importlib.import_module("server")
        with TestClient(server.app) as client:
            client.decode = lambda token: jose_jwt.decode(
                token, "test-only-secret", algorithms=["HS256"], options={"verify_aud": False}
            )
            yield client


def _headers(client, creds=CREDS):
    token = client.post("/auth/login", json=creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_registration_requires_the_declared_required_field(app_client):
    assert app_client.post("/auth/register", json=CREDS).status_code == 422


def test_registration_enforces_max_length(app_client):
    resp = app_client.post("/auth/register", json={**CREDS, "name": "x" * 21})
    assert resp.status_code == 422


def test_registration_stores_the_fields_and_the_token_carries_the_claim(app_client):
    resp = app_client.post("/auth/register", json={**CREDS, "name": "Alice", "nickname": "al"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["name"], body["nickname"], body["plan"]) == ("Alice", "al", "free")

    tokens = app_client.post("/auth/login", json=CREDS).json()
    assert app_client.decode(tokens["access_token"])["name"] == "Alice"
    assert app_client.get("/auth/me", headers=_headers(app_client)).json()["name"] == "Alice"


def test_internal_field_cannot_be_set_at_registration(app_client):
    resp = app_client.post("/auth/register", json={**CREDS, "name": "Alice", "plan": "enterprise"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["plan"] == "free"


def test_duplicate_unique_field_is_a_400_not_a_500(app_client):
    app_client.post("/auth/register", json={**CREDS, "name": "Alice", "nickname": "al"})
    resp = app_client.post(
        "/auth/register", json={"email": "bob@acme.com", "password": "supersecret123", "name": "Bob", "nickname": "al"}
    )
    assert resp.status_code == 400, resp.text
    assert "already in use" in resp.json()["detail"]


def test_patch_me_updates_declared_fields_and_the_next_refresh_carries_them(app_client):
    app_client.post("/auth/register", json={**CREDS, "name": "Alice"})
    tokens = app_client.post("/auth/login", json=CREDS).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = app_client.patch("/auth/me", json={"name": "Alicia", "nickname": "ali"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["name"], resp.json()["nickname"]) == ("Alicia", "ali")

    refreshed = app_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    assert app_client.decode(refreshed["access_token"])["name"] == "Alicia"


def test_patch_me_never_touches_reserved_or_internal_fields(app_client):
    app_client.post("/auth/register", json={**CREDS, "name": "Alice"})
    before = app_client.get("/auth/me", headers=_headers(app_client)).json()
    resp = app_client.patch(
        "/auth/me",
        json={"name": "Alicia", "roles": ["admin"], "email": "x@y.zz", "is_active": False, "plan": "enterprise"},
        headers=_headers(app_client),
    )
    assert resp.status_code == 200, resp.text
    after = resp.json()
    assert after["name"] == "Alicia"
    for key in ("roles", "email", "is_active", "plan"):
        assert after[key] == before[key], key


def test_patch_me_rejects_null_for_a_required_field_and_needs_authentication(app_client):
    app_client.post("/auth/register", json={**CREDS, "name": "Alice"})
    assert app_client.patch("/auth/me", json={"name": None}, headers=_headers(app_client)).status_code == 400
    assert app_client.patch("/auth/me", json={"name": "Z"}).status_code == 401


def test_nullable_field_can_be_cleared(app_client):
    app_client.post("/auth/register", json={**CREDS, "name": "Alice", "nickname": "al"})
    resp = app_client.patch("/auth/me", json={"nickname": None}, headers=_headers(app_client))
    assert resp.status_code == 200 and resp.json()["nickname"] is None


def test_invite_carries_the_required_fields(app_client, capfd):
    app_client.post("/auth/register", json={**CREDS, "name": "Admin"})
    admin = _headers(app_client)
    capfd.readouterr()

    missing = app_client.post("/auth/invite", json={"email": "new@acme.com", "roles": ["member"]}, headers=admin)
    assert missing.status_code == 422

    resp = app_client.post(
        "/auth/invite", json={"email": "new@acme.com", "roles": ["member"], "name": "Newbie"}, headers=admin
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Newbie"

    token = re.search(r"token=(\S+)", capfd.readouterr().out).group(1)
    assert (
        app_client.post("/auth/accept-invite", json={"token": token, "new_password": "longenough1"}).status_code == 200
    )
    login = app_client.post("/auth/login", json={"email": "new@acme.com", "password": "longenough1"})
    assert app_client.decode(login.json()["access_token"])["name"] == "Newbie"
