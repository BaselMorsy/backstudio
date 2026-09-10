import ast

from app.erd.loader import load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator

FIXTURES = "app/tests/fixtures/erd"


def test_email_dot_py_generated_whenever_auth_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # open mode, no registration gating at all
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    email_path = codebase_dir / "modules" / "auth" / "email.py"
    assert email_path.exists()
    email_src = email_path.read_text(encoding="utf-8")
    ast.parse(email_src)
    assert "def send_email(to: str, subject: str, body: str) -> None:" in email_src
    assert "print(" in email_src


def test_refresh_token_uses_configurable_lifetime_not_hardcoded_seven_days(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    assert "timedelta(days=7)" not in service_src
    assert "settings.REFRESH_TOKEN_EXPIRE_MINUTES" in service_src

    config_src = (codebase_dir / "config.py").read_text(encoding="utf-8")
    assert "REFRESH_TOKEN_EXPIRE_MINUTES: int = 10080" in config_src
    assert "EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 1440" in config_src
    assert "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30" in config_src


def test_email_verification_mode_service_has_verification_methods(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "def create_email_verification_token(self, user_id: int) -> str:" in service_src
    assert 'token_type="email_verification"' in service_src
    assert "EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES" in service_src
    assert "def verify_email(self, db: Session, token: str) -> None:" in service_src
    assert "is_verified = True" in service_src
    assert "from .email import send_email" in service_src

    # authenticate_user must reject an unverified user
    auth_start = service_src.index("def authenticate_user(")
    auth_end = service_src.index("\n    def decode_token(")
    auth_src = service_src[auth_start:auth_end]
    assert "if not user.is_verified:" in auth_src
    assert 'raise ValueError("Email not verified")' in auth_src
    assert "is_approved" not in auth_src  # admin_approval's check must NOT be compiled in


def test_admin_approval_mode_service_has_approve_and_pending_check(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "def approve_user(self, db: Session, user_id: int) -> Optional[User]:" in service_src
    assert "is_approved = True" in service_src

    auth_start = service_src.index("def authenticate_user(")
    auth_end = service_src.index("\n    def decode_token(")
    auth_src = service_src[auth_start:auth_end]
    assert "if not user.is_approved:" in auth_src
    assert 'raise ValueError("Account pending approval")' in auth_src
    assert "is_verified" not in auth_src  # email_verification's check must NOT be compiled in

    # create_email_verification_token must NOT exist under this mode
    assert "create_email_verification_token" not in service_src


def test_open_mode_service_has_neither_gate_but_has_forgot_reset(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    auth_start = service_src.index("def authenticate_user(")
    auth_end = service_src.index("\n    def decode_token(")
    auth_src = service_src[auth_start:auth_end]
    assert "is_verified" not in auth_src
    assert "is_approved" not in auth_src
    assert "create_email_verification_token" not in service_src
    assert "approve_user" not in service_src

    # forgot/reset-password is unconditional, present regardless of mode
    assert "def create_password_reset_token(self, user_id: int, password_hash: str) -> str:" in service_src
    assert "pwd_fp" in service_src
    assert "def verify_password_reset_token(self, db: Session, token: str) -> int:" in service_src


def test_rbac_enabled_service_has_admin_methods(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # rbac.enabled: true, roles: [admin, customer]
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "def list_users(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:" in service_src
    assert "def get_user(self, db: Session, user_id: int) -> Optional[User]:" in service_src
    assert "def set_user_roles(self, db: Session, user_id: int, roles: List[str]) -> Optional[User]:" in service_src
    assert "def deactivate_user(self, db: Session, user_id: int) -> Optional[User]:" in service_src
    assert "def reactivate_user(self, db: Session, user_id: int) -> Optional[User]:" in service_src
    # this fixture is open mode - approve_user must NOT exist even though rbac is enabled
    assert "approve_user" not in service_src


def test_no_rbac_service_has_no_admin_methods(tmp_path):
    # rls_no_rbac_action.yml (from the RLS plan): auth.enabled: true, no rbac: block at all.
    erd = load_erd(f"{FIXTURES}/rls_no_rbac_action.yml")
    state = translate(erd)
    assert state["auth_enabled"] is True
    assert state["rbac_enabled"] is False

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "list_users" not in service_src
    assert "get_user" not in service_src
    assert "set_user_roles" not in service_src
    assert "deactivate_user" not in service_src
    assert "reactivate_user" not in service_src
    assert "approve_user" not in service_src


def test_set_user_roles_rejects_unknown_role(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "auth" / "service.py").read_text(encoding="utf-8")
    roles_start = service_src.index("def set_user_roles(")
    roles_end = service_src.index("\n    def deactivate_user(")
    roles_src = service_src[roles_start:roles_end]
    assert "ValueError" in roles_src
    assert "rbac_roles" not in roles_src  # the ALLOWED roles list is baked in at render time, not read from a runtime attribute
    assert '["admin", "customer"]' in roles_src or "'admin', 'customer'" in roles_src.replace('"', "'")


def test_email_verification_blocks_login_until_verified(tmp_path):
    """The core email_verification security property, proven against a real
    DB: register -> login rejected -> verify -> login succeeds. Also proves
    the token round-trips through create_email_verification_token/verify_email
    correctly (not just that the methods exist).
    """
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "email_verif_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            user = service.register_user(db, "alice@example.com", "supersecret123")
            assert user.is_verified is False

            import pytest as _pytest
            with _pytest.raises(ValueError, match="Email not verified"):
                service.authenticate_user(db, "alice@example.com", "supersecret123")

            token = service.create_email_verification_token(user.id)
            service.verify_email(db, token)

            db.refresh(user)
            assert user.is_verified is True

            authed = service.authenticate_user(db, "alice@example.com", "supersecret123")
            assert authed.id == user.id
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_admin_approval_blocks_login_until_approved(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "admin_approval_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            # the first user registered is the bootstrap admin, auto-approved
            # (symmetric with the RBAC roles bootstrap) so admin_approval mode
            # has a way to bootstrap its first admin at all; register it first
            # so "bob" below exercises the genuine non-first-user gating path.
            admin = service.register_user(db, "admin@example.com", "supersecret123")
            assert admin.is_approved is True

            user = service.register_user(db, "bob@example.com", "supersecret123")
            assert user.is_approved is False

            import pytest as _pytest
            with _pytest.raises(ValueError, match="Account pending approval"):
                service.authenticate_user(db, "bob@example.com", "supersecret123")

            approved = service.approve_user(db, user.id)
            assert approved.is_approved is True

            authed = service.authenticate_user(db, "bob@example.com", "supersecret123")
            assert authed.id == user.id
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_password_reset_token_is_genuinely_single_use(tmp_path):
    """The single most important test in this entire plan: proves the SHA256
    fingerprint mechanism actually gives single-use semantics on a plain
    stateless JWT, not just that expiry works.
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "pwd_reset_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            user = service.register_user(db, "carol@example.com", "originalpassword1")
            old_hash = user.password_hash

            token = service.create_password_reset_token(user.id, old_hash)

            # first use: succeeds, verifies subject and updates the hash
            user_id = service.verify_password_reset_token(db, token)
            assert user_id == user.id
            user.password_hash = service.hash_password("newpassword2")
            db.commit()
            db.refresh(user)
            new_hash = user.password_hash
            assert new_hash != old_hash

            # second use of the SAME token: must fail now, since password_hash changed
            import pytest as _pytest
            with _pytest.raises(ValueError, match="Invalid or expired token"):
                service.verify_password_reset_token(db, token)

            # old password no longer authenticates, new one does
            with _pytest.raises(ValueError, match="Invalid email or password"):
                service.authenticate_user(db, "carol@example.com", "originalpassword1")
            authed = service.authenticate_user(db, "carol@example.com", "newpassword2")
            assert authed.id == user.id
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_password_reset_token_rejects_malformed_or_wrong_type_token(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "pwd_reset_malformed_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            user = service.register_user(db, "dave@example.com", "supersecret123")

            import pytest as _pytest
            with _pytest.raises(ValueError, match="Invalid or expired token"):
                service.verify_password_reset_token(db, "not-a-real-token")

            # an access token (wrong type) must also be rejected, not just garbage
            access_token = service.create_access_token(user.id)
            with _pytest.raises(ValueError, match="Invalid or expired token"):
                service.verify_password_reset_token(db, access_token)
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_admin_service_methods_actually_work_against_a_real_db(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "admin_methods_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            admin_user = service.register_user(db, "admin@example.com", "supersecret123")
            other_user = service.register_user(db, "other@example.com", "supersecret123")

            listed = service.list_users(db)
            assert {u.id for u in listed} == {admin_user.id, other_user.id}

            fetched = service.get_user(db, other_user.id)
            assert fetched.id == other_user.id
            assert service.get_user(db, 999999) is None

            updated = service.set_user_roles(db, other_user.id, ["customer"])
            assert updated.roles == ["customer"]

            import pytest as _pytest
            with _pytest.raises(ValueError):
                service.set_user_roles(db, other_user.id, ["not_a_real_role"])

            deactivated = service.deactivate_user(db, other_user.id)
            assert deactivated.is_active is False
            reactivated = service.reactivate_user(db, other_user.id)
            assert reactivated.is_active is True

            assert service.deactivate_user(db, 999999) is None
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_unconditional_new_schemas_always_present(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # open mode
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "auth" / "schemas.py").read_text(encoding="utf-8")
    ast.parse(schemas_src)
    assert "class SetUserRolesRequest(BaseModel):" in schemas_src
    assert "class ForgotPasswordRequest(BaseModel):" in schemas_src
    assert "class ResetPasswordRequest(BaseModel):" in schemas_src
    assert "class MessageResponse(BaseModel):" in schemas_src

    # open mode: email_verification-only schemas must be absent
    assert "class VerifyEmailRequest(BaseModel):" not in schemas_src
    assert "class ResendVerificationRequest(BaseModel):" not in schemas_src

    # open mode: UserResponse must not have is_verified/is_approved
    resp_start = schemas_src.index("class UserResponse(")
    resp_src = schemas_src[resp_start:]
    assert "is_verified" not in resp_src
    assert "is_approved" not in resp_src


def test_email_verification_mode_schemas(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "auth" / "schemas.py").read_text(encoding="utf-8")
    ast.parse(schemas_src)
    assert "class VerifyEmailRequest(BaseModel):" in schemas_src
    assert "class ResendVerificationRequest(BaseModel):" in schemas_src

    resp_start = schemas_src.index("class UserResponse(")
    resp_end = schemas_src.index("\n    class Config:", resp_start)
    resp_src = schemas_src[resp_start:resp_end]
    assert "is_verified: bool" in resp_src
    assert "is_approved" not in resp_src


def test_admin_approval_mode_user_response_schema(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "auth" / "schemas.py").read_text(encoding="utf-8")
    resp_start = schemas_src.index("class UserResponse(")
    resp_end = schemas_src.index("\n    class Config:", resp_start)
    resp_src = schemas_src[resp_start:resp_end]
    assert "is_approved: bool" in resp_src
    assert "is_verified" not in resp_src

    # admin_approval mode has no email flow - these two must still be absent
    assert "class VerifyEmailRequest(BaseModel):" not in schemas_src
    assert "class ResendVerificationRequest(BaseModel):" not in schemas_src


def test_email_verification_mode_routes_present_admin_routes_absent(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")  # also rbac.enabled: true
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert '"/verify-email"' in routes_src
    assert '"/resend-verification"' in routes_src
    assert '"/forgot-password"' in routes_src
    assert '"/reset-password"' in routes_src
    assert '"/users"' in routes_src  # rbac.enabled is true on this fixture too
    assert '"/users/{user_id}/approve"' not in routes_src  # not admin_approval mode


def test_admin_approval_mode_approve_route_present(tmp_path):
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    assert '"/users/{user_id}/approve"' in routes_src
    assert '"/verify-email"' not in routes_src
    assert '"/resend-verification"' not in routes_src
    # forgot/reset-password is unconditional regardless of mode
    assert '"/forgot-password"' in routes_src
    assert '"/reset-password"' in routes_src


def test_open_mode_no_rbac_has_only_forgot_reset(tmp_path):
    from app.erd.schema import ERDConfig, ProjectMeta, DatabaseSpec, AuthSpec, EntitySpec, ServiceDecl
    from app.erd.schema import ModelField, FieldType

    erd = ERDConfig(
        project=ProjectMeta(name="OpenNoRbac", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="o.db"),
        auth=AuthSpec(enabled=True),
        entities=[
            EntitySpec(name="Widget", fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]),
        ],
        services=[ServiceDecl(name="widgets", entities=["Widget"])],
    )
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert '"/forgot-password"' in routes_src
    assert '"/reset-password"' in routes_src
    assert '"/verify-email"' not in routes_src
    assert '"/users"' not in routes_src
    assert "require_roles" not in routes_src
    assert "from rbac import require_roles" not in routes_src


def test_admin_routes_gated_with_require_roles_admin(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    assert "from rbac import require_roles" in routes_src
    list_start = routes_src.index('"/users"')
    list_block = routes_src[list_start:list_start + 400]
    assert 'dependencies=[Depends(require_roles("admin"))]' in list_block


def test_list_users_route_has_pagination_query_params(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    list_start = routes_src.index("def list_users_route(")
    list_end = routes_src.index("\n@router.get", list_start)
    list_src = routes_src[list_start:list_end]
    assert "skip: int = Query(0, ge=0)" in list_src
    assert "limit: int = Query(100, ge=1, le=500)" in list_src


def test_reset_password_request_enforces_min_length(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "auth" / "schemas.py").read_text(encoding="utf-8")
    reset_start = schemas_src.index("class ResetPasswordRequest(")
    reset_end = schemas_src.index("\n\n\n", reset_start)
    reset_src = schemas_src[reset_start:reset_end]
    assert "min_length=8" in reset_src
