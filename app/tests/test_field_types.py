import pytest

from app.erd import field_types as ft
from app.erd.schema import FieldType
from app.services.code_generator import CodeGenerator

LEGACY_SA = {
    "string": "String", "integer": "Integer", "float": "Float", "boolean": "Boolean",
    "datetime": "DateTime", "date": "Date", "text": "Text", "json": "JSON", "uuid": "String",
}
LEGACY_PY = {
    "string": "str", "integer": "int", "float": "float", "boolean": "bool",
    "datetime": "datetime", "date": "date", "text": "str", "json": "Any", "uuid": "str",
}
LEGACY_MERMAID = {
    "string": "string", "integer": "int", "float": "float", "boolean": "bool",
    "datetime": "datetime", "date": "date", "text": "text", "json": "json", "uuid": "uuid",
}


@pytest.mark.parametrize("type_value", sorted(LEGACY_SA))
def test_simple_type_maps_match_the_legacy_maps(type_value):
    assert ft.sa_type_for(type_value) == LEGACY_SA[type_value]
    assert ft.py_type_for(type_value) == LEGACY_PY[type_value]
    assert ft.mermaid_type(type_value) == LEGACY_MERMAID[type_value]
    member = FieldType(type_value)
    assert ft.sa_type_for(member) == LEGACY_SA[type_value]
    assert ft.py_type_for(member) == LEGACY_PY[type_value]
    assert ft.mermaid_type(member) == LEGACY_MERMAID[type_value]


def test_unknown_types_fall_back_like_the_legacy_maps():
    assert ft.sa_type_for("nonsense") == "String"
    assert ft.py_type_for("nonsense") == "str"
    assert ft.mermaid_type("nonsense") == "string"


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, "True"), (False, "False"), (None, "None"), (3, "3"), (2.5, "2.5"),
        ([], "[]"), ("plain", "'plain'"), ("O'Brien's", '"O\'Brien\'s"'),
    ],
)
def test_python_literal_matches_the_old_python_value_filter(value, expected):
    assert ft.python_literal(value) == expected


@pytest.mark.parametrize(
    "text", ["Order", "order_item", "orderItem", "AuditLog", "audit_log", "x", "", "HTTPServer", "my_2nd_thing"]
)
def test_pascal_case_matches_the_codegen_filter(text, tmp_path):
    """Enum class names are built by field_types.pascal_case but referenced from templates
    that use the Jinja `pascal_case` filter for model class names; the two must not drift."""
    generator = CodeGenerator(output_dir=str(tmp_path))
    assert ft.pascal_case(text) == generator.jinja_env.filters["pascal_case"](text)


def test_code_generator_delegates_to_the_registry(tmp_path):
    generator = CodeGenerator(output_dir=str(tmp_path))
    assert generator.jinja_env.filters["python_value"] is ft.python_literal
    assert generator._get_sqlalchemy_type("integer") == "Integer"
    assert generator._get_python_type("json") == "Any"
    assert generator._get_python_type(FieldType.FLOAT) == "float"
