import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_auth_service_when_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    auth_dir = codebase_dir / "auth"
    for filename in ("schemas.py", "service.py", "routes.py"):
        path = auth_dir / filename
        assert path.exists()
        ast.parse(path.read_text(encoding="utf-8"))

    service_src = (auth_dir / "service.py").read_text(encoding="utf-8")
    assert "def register_user(" in service_src
    assert "def authenticate_user(" in service_src
    assert "async def get_current_user(" in service_src

    routes_src = (auth_dir / "routes.py").read_text(encoding="utf-8")
    assert '"/register"' in routes_src
    assert '"/login"' in routes_src
    assert '"/me"' in routes_src


def test_no_auth_directory_when_disabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert not (codebase_dir / "auth").exists()
