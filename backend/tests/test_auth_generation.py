import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_auth_module_when_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    auth_dir = codebase_dir / "modules" / "auth"
    for filename in ("schemas.py", "service.py", "routes.py"):
        path = auth_dir / filename
        assert path.exists()
        ast.parse(path.read_text(encoding="utf-8"))
    assert (auth_dir / "__init__.py").exists()
    assert not (codebase_dir / "auth").exists()  # old location must be gone

    service_src = (auth_dir / "service.py").read_text(encoding="utf-8")
    assert "class AuthService:" in service_src
    assert "def register_user(self, db: Session" in service_src
    assert "def authenticate_user(self, db: Session" in service_src
    assert "async def get_current_user(self" in service_src
    assert "def get_auth_service()" in service_src

    routes_src = (auth_dir / "routes.py").read_text(encoding="utf-8")
    assert '"/register"' in routes_src
    assert '"/login"' in routes_src
    assert '"/me"' in routes_src
    assert "_service = get_auth_service()" in routes_src  # needed for Depends(_service.get_current_user)
    assert "service: AuthService = Depends(get_auth_service)" in routes_src
    assert "service.register_user(" in routes_src

    # /refresh must take the token in the request body, not a bare query param.
    assert "payload: RefreshRequest" in routes_src
    assert "def refresh(refresh_token: str" not in routes_src

    schemas_src = (auth_dir / "schemas.py").read_text(encoding="utf-8")
    assert "class RefreshRequest(BaseModel):" in schemas_src

    requirements_src = (codebase_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "bcrypt==4.0.1" in requirements_src
    assert "email-validator" in requirements_src


def test_no_auth_module_when_disabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert not (codebase_dir / "modules" / "auth").exists()
    assert not (codebase_dir / "auth").exists()


def test_renamed_auth_service_uses_its_own_name(tmp_path):
    from backend.erd.schema import (
        ERDConfig, ProjectMeta, DatabaseSpec, AuthSpec, EntitySpec, ServiceDecl,
    )
    from backend.schemas.data import ModelField, FieldType

    erd = ERDConfig(
        project=ProjectMeta(name="Demo", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="demo.db"),
        auth=AuthSpec(enabled=True),
        entities=[
            EntitySpec(name="Widget", fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]),
        ],
        services=[
            ServiceDecl(name="widgets", entities=["Widget"]),
            ServiceDecl(name="identity", entities=["User"]),
        ],
    )
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert (codebase_dir / "modules" / "identity" / "service.py").exists()
    assert not (codebase_dir / "modules" / "auth").exists()

    service_src = (codebase_dir / "modules" / "identity" / "service.py").read_text(encoding="utf-8")
    assert "def get_identity_service()" in service_src

    routes_src = (codebase_dir / "modules" / "identity" / "routes.py").read_text(encoding="utf-8")
    assert "get_identity_service" in routes_src
