import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_module_schemas_and_routes_for_every_entity_in_the_service(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")  # services: [{name: catalog, entities: [Category, Product]}]
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_file = codebase_dir / "modules" / "catalog" / "schemas.py"
    routes_file = codebase_dir / "modules" / "catalog" / "routes.py"
    service_file = codebase_dir / "modules" / "catalog" / "service.py"
    assert schemas_file.exists()
    assert routes_file.exists()
    assert service_file.exists()
    assert (codebase_dir / "modules" / "__init__.py").exists()
    assert (codebase_dir / "modules" / "catalog" / "__init__.py").exists()

    schemas_src = schemas_file.read_text(encoding="utf-8")
    ast.parse(schemas_src)
    assert "class ProductCreate(BaseModel):" in schemas_src
    assert "class ProductResponse(BaseModel):" in schemas_src
    assert "class CategoryCreate(BaseModel):" in schemas_src
    assert "class CategoryResponse(BaseModel):" in schemas_src

    service_src = service_file.read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "class CatalogService:" in service_src
    assert "def create_product(self, db: Session, data: dict)" in service_src
    assert "def create_category(self, db: Session, data: dict)" in service_src
    assert "def get_catalog_service()" in service_src

    routes_src = routes_file.read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "from .service import CatalogService, get_catalog_service" in routes_src
    assert '"/products"' in routes_src
    assert '"/categories"' in routes_src
    assert "def delete_product_route" in routes_src
    assert "service.create_product(db, payload.model_dump())" in routes_src


def test_multiple_services_produce_separate_module_directories(tmp_path):
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # catalog: [Category, Product], ordering: [Order]
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert (codebase_dir / "modules" / "catalog" / "routes.py").exists()
    assert (codebase_dir / "modules" / "ordering" / "routes.py").exists()

    ordering_routes = (codebase_dir / "modules" / "ordering" / "routes.py").read_text(encoding="utf-8")
    ast.parse(ordering_routes)
    assert '"/orders"' in ordering_routes


def test_rbac_dependency_only_imported_when_rbac_enabled(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")  # rbac disabled
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "widgets" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "from rbac import require_roles" not in routes_src


def test_custom_table_name_overrides_pluralized_default(tmp_path):
    erd = load_erd(f"{FIXTURES}/overrides.yml")  # Category declares table_name: cats
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    ast.parse(models_src)
    assert '__tablename__ = "cats"' in models_src
    assert '__tablename__ = "categories"' not in models_src


def test_custom_base_path_and_tags_used_in_routes(tmp_path):
    erd = load_erd(f"{FIXTURES}/overrides.yml")  # Category overrides base_path and tags
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "stuff" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert '"/my-categories"' in routes_src
    assert '"/categories"' not in routes_src
    assert 'tags=["custom-tag"]' in routes_src


def test_all_actions_disabled_entity_gets_schemas_and_service_but_no_routes(tmp_path):
    """AuditLog declares endpoints.enabled: [] - it should still get full CRUD
    schemas and service methods (those don't look at enabled_actions), but zero
    route decorators in the shared module routes.py.
    """
    erd = load_erd(f"{FIXTURES}/overrides.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    schemas_src = (codebase_dir / "modules" / "stuff" / "schemas.py").read_text(encoding="utf-8")
    ast.parse(schemas_src)
    assert "class AuditLogCreate(BaseModel):" in schemas_src
    assert "class AuditLogResponse(BaseModel):" in schemas_src

    service_src = (codebase_dir / "modules" / "stuff" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)
    assert "def create_audit_log(self, db: Session, data: dict)" in service_src

    routes_src = (codebase_dir / "modules" / "stuff" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    for action in ("create", "list", "get", "update", "delete"):
        assert f"def {action}_audit_log_route" not in routes_src
    assert '"/audit_logs"' not in routes_src
    assert 'summary="Create AuditLog"' not in routes_src
