import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_crud_schemas_and_routes(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_file = codebase_dir / "products" / "schemas.py"
    routes_file = codebase_dir / "products" / "routes.py"
    assert schemas_file.exists()
    assert routes_file.exists()

    schemas_src = schemas_file.read_text(encoding="utf-8")
    ast.parse(schemas_src)  # must be syntactically valid Python
    assert "class ProductCreate(BaseModel):" in schemas_src
    assert "class ProductResponse(BaseModel):" in schemas_src

    routes_src = routes_file.read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "from database.repo import" in routes_src
    assert 'router.post(\n    "",' in routes_src or '@router.post("")' in routes_src
    assert "def delete_product_route" in routes_src
