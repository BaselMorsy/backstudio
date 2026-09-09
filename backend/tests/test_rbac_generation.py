import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_rbac_module_when_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    rbac_file = codebase_dir / "rbac.py"
    assert rbac_file.exists()
    src = rbac_file.read_text(encoding="utf-8")
    ast.parse(src)
    assert "def require_roles(" in src


def test_no_rbac_module_when_disabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert not (codebase_dir / "rbac.py").exists()


def test_auth_enabled_rbac_disabled_generates_auth_without_rbac_gating(tmp_path):
    """auth.enabled: true with rbac left at its default (disabled) is a distinct
    case from valid_minimal.yml (both off) - the auth module and its JWT flow
    must still be generated, just with no role-gating anywhere.
    """
    erd = load_erd(f"{FIXTURES}/auth_no_rbac.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert not (codebase_dir / "rbac.py").exists()

    auth_routes_src = (codebase_dir / "modules" / "auth" / "routes.py").read_text(encoding="utf-8")
    ast.parse(auth_routes_src)
    assert '"/register"' in auth_routes_src
    assert '"/login"' in auth_routes_src
    assert '"/me"' in auth_routes_src

    notes_routes_src = (codebase_dir / "modules" / "notes" / "routes.py").read_text(encoding="utf-8")
    ast.parse(notes_routes_src)
    assert "from rbac import require_roles" not in notes_routes_src
    assert "require_roles" not in notes_routes_src
    assert "dependencies=" not in notes_routes_src
