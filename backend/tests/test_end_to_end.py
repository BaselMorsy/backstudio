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


def test_one_to_one_relationship_generates_and_compiles(tmp_path):
    """One-to-one cardinality is unit-tested at the translate() level in
    test_erd_translate.py; this exercises the full generation pipeline
    (rendered models.py + byte-compile), which wasn't covered before.
    """
    erd = load_erd(f"{FIXTURES}/one_to_one.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    ast.parse(models_src)

    author_start = models_src.index("class Author(Base):")
    profile_start = models_src.index("class Profile(Base):")
    author_src = models_src[author_start:profile_start]

    # FK lives on the source (Author) for one-to-one, and must be unique.
    assert "profile_id" in author_src
    assert "ForeignKey('profiles.id')" in author_src or 'ForeignKey("profiles.id")' in author_src
    assert "unique=True" in author_src
    assert "profile = relationship(" in author_src
    assert "uselist=False" in author_src

    profile_src = models_src[profile_start:]
    assert "author = relationship(" in profile_src
    assert "uselist=False" in profile_src

    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(codebase_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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


def test_self_referential_relationships_generate_and_byte_compile(tmp_path):
    """self_referential.yml: Employee.manager (many-to-one) and Category.children
    (one-to-many), both targeting their own entity. Each must produce exactly one
    FK column and exactly two distinct relationship() attributes per model - a
    duplicated FK column or relationship() here fails as a SyntaxError at
    byte-compile time (ast.parse alone would not catch a duplicate keyword
    argument), which is exactly the bug this fixture guards against.
    """
    erd = load_erd(f"{FIXTURES}/self_referential.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    ast.parse(models_src)

    class_starts = sorted(
        [models_src.index("class Employee(Base):"), models_src.index("class Category(Base):")]
    )
    boundaries = class_starts + [len(models_src)]
    employee_start = models_src.index("class Employee(Base):")
    category_start = models_src.index("class Category(Base):")
    employee_end = boundaries[boundaries.index(employee_start) + 1]
    category_end = boundaries[boundaries.index(category_start) + 1]
    employee_src = models_src[employee_start:employee_end]
    category_src = models_src[category_start:category_end]

    assert employee_src.count("manager_id = Column(") == 1
    assert employee_src.count("remote_side=[id]") == 1
    assert "manager = relationship(" in employee_src
    assert "manager_employees = relationship(" in employee_src

    assert category_src.count("children_id = Column(") == 1
    assert category_src.count("remote_side=[id]") == 1
    assert "children = relationship(" in category_src
    assert "children_category = relationship(" in category_src

    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(codebase_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
