import ast
import subprocess
import sys
from pathlib import Path

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def _assert_all_python_files_parse(root: Path) -> None:
    for path in root.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_shophub_mini_generates_a_complete_working_tree(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    expected_files = [
        "server.py",
        "config.py",
        "database/models.py",
        "database/repo.py",
        "database/base.py",
        "modules/catalog/routes.py",
        "modules/catalog/schemas.py",
        "modules/catalog/service.py",
        "modules/ordering/routes.py",
        "modules/ordering/schemas.py",
        "modules/ordering/service.py",
        "modules/auth/routes.py",
        "modules/auth/service.py",
        "modules/auth/schemas.py",
        "rbac.py",
        "alembic.ini",
        "alembic/env.py",
        "requirements.txt",
    ]
    for rel_path in expected_files:
        assert (codebase_dir / rel_path).exists(), f"missing {rel_path}"

    _assert_all_python_files_parse(codebase_dir)

    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    assert "class User(Base):" in models_src
    assert "class Product(Base):" in models_src
    assert "class Order(Base):" in models_src

    catalog_routes_src = (codebase_dir / "modules" / "catalog" / "routes.py").read_text(encoding="utf-8")
    assert "from rbac import require_roles" in catalog_routes_src
    assert 'require_roles("admin")' in catalog_routes_src


def test_shophub_mini_relationship_crosses_service_boundary(tmp_path):
    """Order lives in the 'ordering' service, Product lives in 'catalog' — the
    FK/relationship between them must still be wired correctly in the shared,
    global database/models.py regardless of which service either entity belongs to.
    """
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    ast.parse(models_src)

    order_class_start = models_src.index("class Order(Base):")
    next_class_start = models_src.index("\nclass ", order_class_start + 1)
    order_class_src = models_src[order_class_start:next_class_start]

    assert "product_id" in order_class_src
    assert 'ForeignKey(\'products.id\')' in order_class_src or 'ForeignKey("products.id")' in order_class_src
    assert "product = relationship(" in order_class_src


def test_shophub_mini_byte_compiles(tmp_path):
    """A stronger check than ast.parse: byte-compile every generated module."""
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(codebase_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
