# backend/tests/test_server_wiring.py
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_server_imports_and_mounts_crud_and_auth_routers(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    ast.parse(server_src)

    assert "from products.routes import router as products_router" in server_src
    assert 'app.include_router(products_router, prefix="/products"' in server_src
    assert "from auth.routes import router as auth_router" in server_src
    assert 'app.include_router(auth_router, prefix="/auth"' in server_src


def test_server_skips_crud_and_auth_blocks_when_absent(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    server_src = (codebase_dir / "server.py").read_text(encoding="utf-8")
    ast.parse(server_src)
    assert "from widgets.routes import router as widgets_router" in server_src
    assert "from auth.routes import router as auth_router" not in server_src
